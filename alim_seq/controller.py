"""Contrôleur : orchestration matériel, boucle de mesure et sécurité.

Le contrôleur est le point d'entrée unique de toute la logique métier. Il :

- construit les **instruments** (réels ou simulés) déclarés par la config, chacun
  exposant ses **capacités** (source de tension, mesure V/I, mesure température… —
  cf. ``alim_seq/instrument.py``) ; il les pilote *par capacité*, jamais par type ;
- sérialise les accès matériels par **un verrou par instrument** (``_instr_locks[nom]``,
  alims comme module de température). Ainsi un timeout VISA sur un instrument ne bloque
  ni la boucle température ni la coupure des autres. **Ordre d'acquisition invariant**
  (ne jamais l'inverser) :

      verrou(s) instrument (ordre alphabétique du nom)  ->  _state_lock

  La boucle de sécurité ne prend QUE le verrou de l'instrument de température (jamais
  un verrou de source) : une source figée ne peut pas retarder une coupure. Pour un
  groupe série, on verrouille TOUTES les alims de ses membres, triées par nom, avant
  toute action (context manager ``_lock_for``).
- fait tourner une **boucle de mesure** en tâche de fond qui lit tensions,
  courants et températures, puis évalue la sécurité ;
- au seuil **critique**, déclenche une **désalimentation ordonnée** (extinction
  douce des voies, plutôt qu'une coupure brutale) ; une coupure dure n'intervient
  qu'en dernier recours au-delà de critique + ``hard_margin_c`` ;
- enregistre les mesures dans un **fichier CSV** au cours du temps ;
- expose un *snapshot* thread-safe de l'état pour l'IHM ;
- fournit la primitive d'**asservissement** (servo) réutilisée par le séquenceur.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Tuple

from .config import AppConfig
from .controller_recording import RecordingMixin
from .controller_servo import ServoMixin
from .controller_simtune import SimTuneMixin
from .essai import DossierEssai, ISSUE_ARRET_UTILISATEUR, ISSUE_DECLENCHEMENT
from .instrument import Instrument, create_instrument, driver_role
from .sequencer import Action, SequenceRunner, load_shutdown_actions

# Niveaux de sécurité
OK = "OK"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
NA = "NA"        # capteur « en attente » : non valide (voie requise pas encore ON)
FAULT = "FAULT"  # capteur en DÉFAUT (hors plage / débranché) ou perte de comm


@dataclass
class ChannelView:
    """État d'une voie (ou d'un groupe) vu par l'IHM et le séquenceur.

    Réunit les **consignes** (``set_voltage`` SIGNÉE, ``set_current``, ``output``) et
    les dernières **mesures** (``meas_voltage`` SIGNÉE, ``meas_current``, ``mode``
    CV/CC, ``faults`` matériels HMP). Les tensions sont signées côté logiciel : une
    rail négative porte une consigne/mesure négative, la magnitude seule est
    programmée sur l'alimentation (voir :meth:`Controller.set_voltage`)."""
    label: str
    set_voltage: float = 0.0
    set_current: float = 0.1
    output: bool = False
    meas_voltage: float = 0.0
    meas_current: float = 0.0
    mode: str = ""  # "CV", "CC" ou "" (voie OFF / inconnu)
    faults: tuple = ()  # défauts matériels HMP : 'OVP', 'FUSE', 'OTP'


@dataclass
class Snapshot:
    """Instantané cohérent et thread-safe de tout l'état, produit par
    :meth:`Controller.snapshot`. L'IHM le lit à sa cadence d'affichage sans jamais
    toucher au matériel : voies, températures et statut par capteur, état de
    sécurité global, connexion/communication, défaut matériel et cadences réelles
    des deux boucles."""
    channels: Dict[str, ChannelView]
    temperatures: Dict[str, float]
    temp_status: Dict[str, str]
    safety_status: str
    safety_message: str
    tripped: bool
    connected: bool = True
    comm_lost: bool = False
    hw_fault: str = ""  # défaut matériel HMP (OVP/fusible/surchauffe), vide si aucun
    meas_period: float = 0.0
    temp_period: float = 0.0
    relays: Dict[str, bool] = field(default_factory=dict)  # sorties de relais (label->état)
    # Voies dont l'instrument source n'a pas pu être lu au dernier cycle (liaison
    # figée) : leurs V/I affichés sont PÉRIMÉS -> l'IHM les grise (« ⏱ figé »).
    stale_labels: set = field(default_factory=set)
    timestamp: float = field(default_factory=time.monotonic)


class Controller(RecordingMixin, ServoMixin, SimTuneMixin):
    """Orchestrateur central : matériel, boucles de mesure/sécurité, séquenceur.

    La périphérie cohésive est portée par des mixins (pur déplacement de code, même
    état ``self``) : :class:`~alim_seq.controller_recording.RecordingMixin`
    (enregistrement CSV / dossier d'essai),
    :class:`~alim_seq.controller_servo.ServoMixin` (asservissement) et
    :class:`~alim_seq.controller_simtune.SimTuneMixin` (couplages simulés + réglage à
    chaud). Le cœur sûreté (boucles, verrous, cycle de vie, arrêts, escalade) reste
    ici, cohésif et auditable.

    Construit à partir d'une :class:`~alim_seq.config.AppConfig`. Cycle de vie type :
    ``Controller(cfg)`` → :meth:`connect` (démarre les boucles) → pilotage via
    :meth:`set_voltage` / :meth:`set_output` / :meth:`servo` ou une séquence
    (:meth:`start_user_sequence`) → :meth:`snapshot` pour l'affichage →
    :meth:`close`. Tout accès matériel est sérialisé par les verrous décrits dans la
    docstring du module ; aucune méthode ne suppose de tourner dans le thread IHM."""

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        # Un verrou matériel PAR alimentation + un pour le module NI (voir docstring
        # module pour l'ordre d'acquisition invariant).
        # Nom interne de l'instrument de température (module NI / mock), garanti
        # distinct des noms d'alimentations : sert de clé de verrou et de routage.
        self._daq_name = self._pick_daq_name()
        # Un verrou matériel PAR instrument (sources + température). Voir la docstring
        # du module pour l'ordre d'acquisition invariant (alphabétique par nom). Les
        # noms viennent de la section unifiée ``instruments`` (+ l'instrument de
        # température, synthétisé si la config n'en déclare aucun).
        self._instr_locks: Dict[str, threading.RLock] = {
            name: threading.RLock()
            for name in set(cfg.instruments) | {self._daq_name}
        }
        self._state_lock = threading.Lock()
        self._logs: Deque[str] = deque(maxlen=1000)
        self._log_lock = threading.Lock()
        # Abonnés au journal (le dossier d'essai s'y branche le temps d'un essai).
        # Appelés dans log() hors du verrou du journal, exceptions avalées.
        self._log_listeners: List[Callable[[str], None]] = []
        self._log_listeners_lock = threading.Lock()

        # Consignes courantes (ce qui a été demandé), indexées par label.
        self._set: Dict[str, ChannelView] = {
            label: ChannelView(
                label=label,
                set_voltage=ch.default_voltage,
                set_current=ch.default_current,
            )
            for label, ch in cfg.channels.items()
        }

        # Dernières mesures connues (mises à jour par la boucle de mesure).
        self._temperatures: Dict[str, float] = {n: float("nan") for n in cfg.temperatures}
        self._temp_voltages: Dict[str, float] = {n: float("nan") for n in cfg.temperatures}
        self._temp_status: Dict[str, str] = {n: OK for n in cfg.temperatures}
        self._safety_status = OK
        self._safety_message = ""
        self._tripped = False
        self._hard_cut_done = False

        # État de connexion / communication.
        self._connected = False
        self._connect_error = ""
        self._comm_lost = False
        self._psu_fail = 0
        self._daq_fail = 0

        # Défauts matériels HMP (OVP / fusible / surchauffe) remontés du registre.
        self._hw_fault_msg = ""
        self._hw_fault_seen: set = set()

        # Cadence réelle mesurée (période effective entre deux cycles, en s).
        self._meas_period = 0.0
        self._temp_period = 0.0
        # Cycles de mesure V/I consécutifs où l'instrument n'a pas pu être verrouillé
        # (liaison figée ?) — sert à journaliser l'anomalie sans bloquer la boucle.
        self._meas_skip: Dict[str, int] = {}
        # Derniers états de relais lus avec succès (relay_states est non bloquant :
        # si un verrou est occupé, on ressert la dernière valeur connue plutôt que rien).
        self._relay_states_cache: Dict[str, bool] = {}

        self._build_instruments()
        # Surveillance température : désactivée si aucun capteur n'est défini
        # ('temperatures': {}). On n'utilise alors PAS le module NI.
        self._temp_enabled = bool(self.cfg.temperatures)

        # Deux boucles : températures (sécurité, rapide) et mesures V/I (lente).
        self._temp_thread: Optional[threading.Thread] = None
        self._meas_thread: Optional[threading.Thread] = None
        self._stop_poll = threading.Event()
        # Drapeau d'avortement utilisé par le séquenceur (sécurité / arrêt).
        self.abort_event = threading.Event()

        # Reconnexion automatique (opt-in) : un chien de garde tente de rouvrir la
        # liaison après une perte de communication, avec back-off exponentiel.
        # _reconnect_lock sérialise reconnect() : le chien de garde ET le bouton
        # « Reconnecter » de l'IHM peuvent le demander au même instant — sans ce
        # verrou, deux reconstructions d'instruments s'entrelaceraient.
        self._reconnect_lock = threading.Lock()
        self._auto_reconnect = bool(cfg.safety.get("auto_reconnect", False))
        self._reconnect_max_delay = float(cfg.safety.get("reconnect_max_delay", 30.0))
        self._wd_thread: Optional[threading.Thread] = None
        self._wd_stop = threading.Event()

        # Séquenceur (exécution des fichiers de séquence et de la désalimentation).
        self.runner = SequenceRunner(self)
        # Le contrôleur intercepte la fin de séquence pour marquer l'issue de
        # l'essai, puis relaie à l'IHM via ``on_seq_finish`` (que l'IHM branche).
        self.runner.on_finish = self._runner_finished
        self.on_seq_finish: Optional[Callable[[bool, str], None]] = None
        self._shutdown_inflight = threading.Event()  # évite un double déclenchement
        # Chemin du fichier de séquentiel d'arrêt (None = extinction auto ordonnée).
        self._shutdown_path: Optional[str] = cfg.safety.get("shutdown_sequence")

        # Enregistrement CSV.
        self._csv_file = None
        self._csv_writer = None
        self._csv_path: Optional[Path] = None
        self._csv_t0: float = 0.0
        self._rec_lock = threading.Lock()
        # Dossier d'essai en cours (None hors enregistrement, ou enregistrement
        # « CSV brut » vers un chemin explicite sans dossier).
        self._essai: Optional[DossierEssai] = None

        # Journal applicatif (fichier) — désactivé tant que enable_file_logging
        # n'est pas appelé (les tests ne créent donc pas de fichier).
        self._file_logger: Optional[logging.Logger] = None

    # ------------------------------------------------------------------ build
    def _pick_daq_name(self) -> str:
        """Nom de l'instrument de température : le premier instrument déclaré qui n'est
        ni une source ni un actionneur (relais), sinon un nom synthétique distinct
        (le contrôleur a toujours un instrument de température, même sans capteur)."""
        for name, e in self.cfg.instruments.items():
            if driver_role(str((e or {}).get("driver", "HMP4040"))) not in ("source", "actuator"):
                return name
        name = "TEMP"
        while name in self.cfg.instruments:
            name += "_"
        return name

    def _build_instruments(self) -> None:
        """Construit tous les instruments depuis la section unifiée ``instruments``, et
        le routage label→(instrument, canal). Chaque entrée est classée **par capacité**
        via son ``driver`` (source de tension vs température) et fabriquée par le
        **registre unifié** ``create_instrument``.

        ``self._instruments`` mappe nom→instrument, ``self._source_names`` liste les
        sources, et ``self._daq`` pointe l'instrument *MesureTemperature*. En
        simulation, applique les charges résistives ``simulation.loads`` à chaque voie."""
        self._routing: Dict[str, Tuple[str, int]] = {
            label: (ch.supply, ch.channel) for label, ch in self.cfg.channels.items()
        }

        # Charges simulées par voie (ohms), depuis simulation.loads (label -> ohms).
        # Convertis vers {nom_alim: {canal: ohms}} pour chaque mock.
        loads_cfg = self.cfg.simulation.get("loads", {}) if self.cfg.simulate else {}
        per_supply_loads: Dict[str, Dict[int, float]] = {}
        for label, ohms in loads_cfg.items():
            if label in self._routing:
                sname, ch = self._routing[label]
                per_supply_loads.setdefault(sname, {})[ch] = float(ohms)

        # Routage des sorties de relais : label -> (instrument, état de sécurité).
        relay_map = self.cfg.relay_map
        outs_by_instr: Dict[str, List[str]] = {}
        for lbl, meta in relay_map.items():
            outs_by_instr.setdefault(meta["instrument"], []).append(lbl)

        instruments: Dict[str, Instrument] = {}
        self._source_names: List[str] = []
        self._relay_names: List[str] = []
        self._relay_routing: Dict[str, Tuple[str, bool]] = {}
        for name, entry in self.cfg.instruments.items():
            driver = str((entry or {}).get("driver", "HMP4040"))
            role = driver_role(driver)
            if role == "source":
                instruments[name] = create_instrument(
                    driver, simulate=self.cfg.simulate, name=name,
                    resource=(entry or {}).get("resource", ""),
                    loads=per_supply_loads.get(name),
                    visa_backend=self.cfg.visa_backend,
                    use_cc_status=self.cfg.cc_status,
                    query_delay_s=self.cfg.visa_query_delay,
                    log=self.log,
                )
                self._source_names.append(name)
            elif role == "actuator":
                instruments[name] = create_instrument(
                    driver, simulate=self.cfg.simulate, name=name,
                    outputs=outs_by_instr.get(name, []),
                )
                self._relay_names.append(name)
                for lbl in outs_by_instr.get(name, []):
                    self._relay_routing[lbl] = (name, bool(relay_map[lbl].get("safe_state", False)))
            else:  # capacité MesureTemperature (un seul instrument, cf. validation)
                instruments[name] = self._make_daq_instrument(name, entry or {})
        # Filet : si aucun instrument de température n'est déclaré, on en synthétise un
        # (le contrôleur en a toujours un, même sans capteur configuré).
        if self._daq_name not in instruments:
            instruments[self._daq_name] = self._make_daq_instrument(self._daq_name, {})
        self._instruments = instruments
        self._daq = instruments[self._daq_name]

    def _make_daq_instrument(self, name: str, entry: Dict[str, object]) -> Instrument:
        """Instrument de température : ``MockDAQ`` (modèle thermique piloté par la
        puissance dissipée) en simulation, module NI réel sinon — via ``create_instrument``.
        Les capteurs viennent de ``temperatures`` ; ``entry`` porte les paramètres du
        driver (ex. ``device`` en réel)."""
        if self.cfg.simulate:
            sim = self.cfg.simulation
            return create_instrument(
                "NI-DAQ", simulate=True, name=name,
                sensors=self.cfg.temperatures,
                power_provider=self._total_output_power,
                ambient_c=sim.get("ambient_c", 25.0),
                thermal_gain_c_per_w=sim.get("thermal_gain_c_per_w", 6.0),
                thermal_tau_s=sim.get("thermal_tau_s", 8.0),
                noise_c=sim.get("noise_c", 0.15),
            )
        return create_instrument(
            "NI-DAQ", simulate=False, name=name,
            sensors=self.cfg.temperatures,
            device=str(entry.get("device", self.cfg.daq.get("device", "Dev1"))),
        )

    def _sources(self):
        """Itère ``(nom, instrument)`` des sources de tension, dans l'ordre des noms."""
        for name in self._source_names:
            yield name, self._instruments[name]

    def _route(self, label: str) -> Tuple[Instrument, int]:
        """Instrument (source) et canal physique d'une voie logique."""
        name, ch = self._routing[label]
        return self._instruments[name], ch

    def _total_output_power(self) -> float:
        """Puissance totale délivrée (utilisée par le modèle thermique simulé).

        Volontairement SANS verrou : ``output_power`` ne lit qu'un état mémoire du
        mock (aucune I/O VISA) et cette fonction est appelée par le fournisseur de
        puissance du MockDAQ *sous* le verrou de l'instrument température. Prendre un
        verrou de source ici inverserait l'ordre invariant et pourrait deadlocker.
        """
        total = 0.0
        for _name, psu in self._sources():
            if hasattr(psu, "output_power"):
                for ch in range(1, psu.n_channels + 1):
                    total += psu.output_power(ch)  # type: ignore[attr-defined]
        return total

    # --------------------------------------------------------- verrous matériels
    def _supply_names_for(self, label: str) -> List[str]:
        """Alims concernées par un label (voie ou groupe), triées par nom (ordre
        d'acquisition déterministe -> pas de deadlock)."""
        if label in self.cfg.groups:
            names = {self._routing[m][0] for m in self.cfg.groups[label].members
                     if m in self._routing}
        elif label in self._routing:
            names = {self._routing[label][0]}
        else:
            names = set()
        return sorted(names)

    @contextmanager
    def _lock_for(self, label: str):
        """Verrouille toutes les alims d'un label (voie/groupe), dans l'ordre trié."""
        acquired = []
        try:
            for name in self._supply_names_for(label):
                lk = self._instr_locks[name]
                lk.acquire()
                acquired.append(lk)
            yield
        finally:
            for lk in reversed(acquired):
                lk.release()

    @contextmanager
    def _all_instr_locked(self):
        """Verrouille TOUS les instruments (ordre trié par nom). Réservé aux opérations
        globales exécutées polling ARRÊTÉ (connect/reconnect/close) : deadlock-free par
        l'ordre, et sans contention car aucune boucle ne tourne à ces moments-là."""
        acquired = []
        try:
            for name in sorted(self._instr_locks):
                lk = self._instr_locks[name]
                lk.acquire()
                acquired.append(lk)
            yield
        finally:
            for lk in reversed(acquired):
                lk.release()

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> bool:
        """Tente la connexion. Ne lève PAS d'exception : retourne True/False et
        renseigne ``connect_error`` pour que l'IHM reste vivante en cas d'échec."""
        errors = []
        # Connexion : polling arrêté (ou pas encore démarré) -> on peut prendre tous
        # les verrous (ordre trié + daq), deadlock-free.
        with self._all_instr_locked():
            try:
                for _name, psu in self._sources():
                    psu.connect()
            except Exception as exc:
                errors.append(f"Alimentations : {exc}")
            if self._temp_enabled:
                try:
                    self._daq.connect()
                except Exception as exc:
                    errors.append(f"Acquisition NI : {exc}")
            if not errors:
                # Consignes par défaut (magnitude tenant compte de la polarité), OFF.
                try:
                    for label, view in self._set.items():
                        pol = self.cfg.channels[label].polarity
                        inst, ch = self._route(label)
                        inst.set_voltage(ch, pol * view.set_voltage)
                        inst.set_current(ch, view.set_current)
                        inst.set_output(ch, False)
                except Exception as exc:
                    errors.append(f"Initialisation des voies : {exc}")

        if errors:
            self._connected = False
            self._connect_error = "\n".join(errors)
            self.log("Échec de connexion :\n  " + "\n  ".join(errors))
            return False

        self._install_sim_couplings()
        self._connected = True
        self._connect_error = ""
        self._comm_lost = False
        self._psu_fail = 0
        self._daq_fail = 0
        self.log("Matériel connecté (%s)." % ("SIMULATION" if self.cfg.simulate else "RÉEL"))
        self.start_polling()
        self._start_watchdog()
        return True

    def _start_watchdog(self) -> None:
        if not self._auto_reconnect or (self._wd_thread and self._wd_thread.is_alive()):
            return
        self._wd_stop.clear()
        self._wd_thread = threading.Thread(target=self._watchdog_loop, name="watchdog",
                                           daemon=True)
        self._wd_thread.start()

    def _watchdog_loop(self) -> None:
        """Chien de garde de reconnexion : tente de rouvrir la liaison après une
        perte de communication, avec back-off exponentiel (hors séquence en cours)."""
        delay = 2.0
        while not self._wd_stop.wait(1.0):
            if self._comm_lost and not self.runner.is_running:
                self.log(f"Auto-reconnexion dans {delay:.0f} s…")
                if self._wd_stop.wait(delay):
                    break
                if self._comm_lost and self.reconnect():
                    delay = 2.0
                else:
                    delay = min(delay * 2.0, self._reconnect_max_delay)

    def reconnect(self) -> bool:
        """Ferme et rouvre des sessions matérielles neuves (après défaut/débranchement).

        Sérialisé par ``_reconnect_lock`` : le chien de garde et le bouton
        « Reconnecter » peuvent appeler en même temps — la seconde demande est
        refusée (False) plutôt que d'entrelacer deux reconstructions d'instruments."""
        if not self._reconnect_lock.acquire(blocking=False):
            self.log("Reconnexion déjà en cours — demande ignorée.")
            return False
        try:
            self.log("Tentative de reconnexion…")
            self.stop_polling()
            with self._all_instr_locked():
                for name in list(self._source_names) + [self._daq_name]:
                    try:
                        self._instruments[name].close()
                    except Exception:
                        pass
            # Sessions VISA/NI neuves (mêmes noms -> les verrous restent valides).
            self._build_instruments()
            return self.connect()
        finally:
            self._reconnect_lock.release()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def connect_error(self) -> str:
        return self._connect_error

    @property
    def comm_lost(self) -> bool:
        return self._comm_lost

    # Simulation : couplages grille->drain + réglage à chaud -> SimTuneMixin
    # (alim_seq/controller_simtune.py).

    def close(self) -> None:
        """Arrêt propre de l'application : stoppe le chien de garde, interrompt toute
        séquence (même une désalimentation de sécurité), arrête les boucles et
        l'enregistrement, coupe toutes les voies et ferme les sessions matérielles.
        Best-effort : chaque étape est protégée pour que la fermeture aille au bout."""
        self._wd_stop.set()
        if self._wd_thread:
            self._wd_thread.join(timeout=2.0)
        self.runner.force_stop()   # fermeture appli : interrompt tout, même une désalim
        self.stop_polling()
        self.stop_recording()
        with self._all_instr_locked():
            for _name, psu in self._sources():
                try:
                    psu.all_outputs_off()
                except Exception:
                    pass
            for name in list(self._source_names) + [self._daq_name]:
                try:
                    self._instruments[name].close()
                except Exception:
                    pass
        self._connected = False
        self.log("Matériel déconnecté.")

    # ----------------------------------------------------------------- logs
    def enable_file_logging(self, path: Optional[str] = None,
                            max_bytes: int = 2_000_000, backups: int = 3) -> Path:
        """Active l'écriture du journal applicatif dans un fichier (rotation).

        À appeler une fois au démarrage (main.py). Sans effet si déjà actif.
        Retourne le chemin du fichier journal.
        """
        from logging.handlers import RotatingFileHandler

        if self._file_logger is not None:
            return Path(self._file_logger.handlers[0].baseFilename)  # déjà actif

        if path is None:
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            path = logs_dir / "alim_seq.log"
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger(f"alim_seq.{id(self)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups,
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        self._file_logger = logger
        self.log(f"Journal applicatif : {path}")
        return Path(path)

    def add_log_listener(self, cb: Callable[[str], None]) -> None:
        """Abonne ``cb`` au journal : il reçoit chaque ligne formatée. Utilisé par
        le dossier d'essai pour écrire ``journal.log``."""
        with self._log_listeners_lock:
            if cb not in self._log_listeners:
                self._log_listeners.append(cb)

    def remove_log_listener(self, cb: Callable[[str], None]) -> None:
        with self._log_listeners_lock:
            if cb in self._log_listeners:
                self._log_listeners.remove(cb)

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        with self._log_lock:
            self._logs.append(line)
        if self._file_logger is not None:
            try:
                self._file_logger.info(message)
            except Exception:
                pass
        # Abonnés notifiés hors verrou (un abonné lent/en erreur ne bloque pas le
        # journal ; ses exceptions sont avalées).
        with self._log_listeners_lock:
            listeners = list(self._log_listeners)
        for cb in listeners:
            try:
                cb(line)
            except Exception:
                pass

    def drain_logs(self) -> list[str]:
        with self._log_lock:
            out = list(self._logs)
            self._logs.clear()
        return out

    # ---------------------------------------------------------- commandes voie
    def _clamp(self, label: str, voltage=None, current=None):
        ch = self.cfg.channels[label]
        if voltage is not None:
            voltage = float(voltage)
            # Tension SIGNÉE : [0, max] si polarité +, [-max, 0] si polarité -.
            if ch.polarity >= 0:
                voltage = max(0.0, min(voltage, ch.max_voltage))
            else:
                voltage = max(-ch.max_voltage, min(voltage, 0.0))
        if current is not None:
            current = max(0.0, min(float(current), ch.max_current))
        return voltage, current

    def set_voltage(self, label: str, voltage: float) -> None:
        """Règle la tension SIGNÉE d'une voie (ou répartit sur un groupe série).

        La valeur est bornée par le clamp (``[0,max]`` ou ``[-max,0]`` selon la
        polarité) ; seule la **magnitude** est programmée sur l'alimentation (le
        HMP ne sort que du positif), le signe restant géré côté logiciel. Prend le
        verrou de la/des alim(s) concernée(s)."""
        if label in self.cfg.groups:
            return self._set_group_voltage(label, voltage)
        voltage, _ = self._clamp(label, voltage=voltage)
        # On programme la MAGNITUDE sur l'alim (positive), on garde le signe côté soft.
        magnitude = self.cfg.channels[label].polarity * voltage
        with self._lock_for(label):
            inst, ch = self._route(label)
            inst.set_voltage(ch, magnitude)
        with self._state_lock:
            self._set[label].set_voltage = voltage

    def set_current(self, label: str, current: float) -> None:
        """Règle la limite de courant d'une voie (bornée à ``[0, max]``).

        Pour un groupe série, applique la MÊME limite à chaque membre, bornée par la
        limite du groupe (un empilement série se refroidit moins bien : sa limite
        peut être plus basse que celle des voies individuelles)."""
        if label in self.cfg.groups:
            # Voies en série : même limite de courant sur chaque membre, bornée
            # par la limite du GROUPE (GroupConfig.max_current) qui peut être plus
            # basse que celle des membres (empilement série moins bien refroidi).
            g = self.cfg.groups[label]
            current = max(0.0, min(float(current), self._group_max_current(g)))
            for m in g.members:
                self.set_current(m, current)
            return
        _, current = self._clamp(label, current=current)
        with self._lock_for(label):
            inst, ch = self._route(label)
            inst.set_current(ch, current)
        with self._state_lock:
            self._set[label].set_current = current

    def set_output(self, label: str, on: bool) -> None:
        """Allume/éteint une voie (ou un groupe série).

        Un groupe s'allume dans l'ordre de ses membres et s'éteint dans l'ordre
        inverse. Tout allumage est REFUSÉ tant que la sécurité est armée
        (``tripped``) : il faut réarmer d'abord."""
        if label in self.cfg.groups:
            # Allumage dans l'ordre des membres, extinction en ordre inverse.
            members = self.cfg.groups[label].members
            for m in (members if on else list(reversed(members))):
                self.set_output(m, on)
            self.log(f"Groupe série {label} {'ON' if on else 'OFF'}")
            return
        if on and self._tripped:
            self.log("Refusé : sécurité active (tripped). Réarmer avant d'allumer.")
            return
        with self._lock_for(label):
            inst, ch = self._route(label)
            inst.set_output(ch, bool(on))
        with self._state_lock:
            self._set[label].output = bool(on)
        self.log(f"Voie {label} {'ON' if on else 'OFF'}")

    def get_setpoint(self, label: str) -> ChannelView:
        """Consignes courantes (tension/courant/état) d'une voie ou d'un groupe, sans
        toucher au matériel. Pour l'état complet mesuré, préférer :meth:`snapshot`."""
        if label in self.cfg.groups:
            return self._group_view(label)
        with self._state_lock:
            v = self._set[label]
            return ChannelView(v.label, v.set_voltage, v.set_current, v.output)

    # ----------------------------------------------------------- relais (actionneurs)
    def set_relay(self, label: str, on: bool) -> None:
        """Ferme (``on=True``) ou ouvre une sortie de relais, sous le verrou de son
        instrument. Tout **fermeture** (ON) est refusée tant que la sécurité est armée
        (``tripped``), comme pour l'allumage d'une voie : un relais peut ré-alimenter
        la carte. La mise à l'état de sécurité (:meth:`_drive_relays_safe`) contourne
        ce garde-fou puisqu'elle fait partie de l'extinction."""
        if label not in self._relay_routing:
            raise KeyError(f"Sortie de relais inconnue : {label!r}")
        if on and self._tripped:
            self.log("Refusé : sécurité active (tripped). Réarmer avant de fermer un relais.")
            return
        name, _safe = self._relay_routing[label]
        with self._instr_locks[name]:
            # Re-vérification SOUS le verrou : un trip survenu entre le test ci-dessus
            # et l'acquisition ne doit pas laisser passer une fermeture.
            if on and self._tripped:
                self.log("Refusé : sécurité active (tripped). Réarmer avant de fermer un relais.")
                return
            self._instruments[name].set_state(label, bool(on))
        self.log(f"Relais {label} {'ON (fermé)' if on else 'OFF (ouvert)'}")

    def relay_state(self, label: str) -> Optional[bool]:
        """État courant d'une sortie de relais (``None`` si inconnu)."""
        if label not in self._relay_routing:
            raise KeyError(f"Sortie de relais inconnue : {label!r}")
        name, _safe = self._relay_routing[label]
        with self._instr_locks[name]:
            return self._instruments[name].get_state(label)

    def relay_states(self) -> Dict[str, bool]:
        """État de toutes les sorties de relais (``{label: bool}``), pour l'IHM.

        Non bloquant : un instrument au verrou occupé est resservi depuis la
        **dernière lecture réussie** (cache) plutôt qu'omis — l'IHM n'affiche jamais
        un OFF fantôme pour un relais réellement fermé."""
        out: Dict[str, bool] = dict(self._relay_states_cache)
        for name in self._relay_names:
            lk = self._instr_locks.get(name)
            got = lk.acquire(blocking=False) if lk else False
            if not got:
                continue   # verrou occupé : on garde la dernière valeur connue
            try:
                out.update(self._instruments[name].states())
            except Exception:
                pass
            finally:
                lk.release()
        self._relay_states_cache = dict(out)
        return out

    def _drive_relays_safe(self) -> None:
        """Met chaque sortie de relais à son **état de sécurité** configuré (défaut
        OFF/ouvert). Utilisée par la désalimentation ordonnée et l'arrêt d'urgence :
        ouvrir un relais isole la carte. Verrou pris en NON bloquant (la sécurité ne
        doit jamais être retardée par un instrument figé) ; best-effort."""
        for name in sorted(self._relay_names):
            lk = self._instr_locks.get(name)
            got = lk.acquire(blocking=False) if lk else False
            try:
                inst = self._instruments[name]
                for lbl, (iname, safe) in self._relay_routing.items():
                    if iname == name:
                        inst.set_state(lbl, safe)
            except Exception as exc:
                self.log(f"Relais {name} état sûr en erreur : {exc}")
            finally:
                if got:
                    lk.release()

    # ----------------------------------------------- groupes (voies en série)
    def _group_max_voltage(self, g) -> float:
        if g.max_voltage > 0:
            return g.max_voltage
        return sum(self.cfg.channels[m].max_voltage for m in g.members)

    def _group_max_current(self, g) -> float:
        """Limite de courant du groupe : ``max_current`` explicite (> 0) sinon le
        plus petit des ``max_current`` des membres (série -> même courant partout)."""
        if g.max_current > 0:
            return g.max_current
        return min(self.cfg.channels[m].max_current for m in g.members)

    def _split_voltage(self, g, total: float) -> List[float]:
        """Répartit la tension totale entre les membres (caps par voie respectés)."""
        members = g.members
        maxes = [self.cfg.channels[m].max_voltage for m in members]
        total = max(0.0, min(total, sum(maxes)))
        alloc = [0.0] * len(members)
        if g.split == "fill":
            # Remplit chaque voie jusqu'à son max, dans l'ordre.
            remaining = total
            for i, mx in enumerate(maxes):
                alloc[i] = min(mx, remaining)
                remaining -= alloc[i]
            return alloc
        # "equal" : partage équilibré avec débordement (water-filling).
        remaining = total
        active = list(range(len(members)))
        while remaining > 1e-9 and active:
            share = remaining / len(active)
            progressed = False
            for i in list(active):
                give = min(share, maxes[i] - alloc[i])
                alloc[i] += give
                remaining -= give
                if give > 1e-9:
                    progressed = True
                if alloc[i] >= maxes[i] - 1e-9:
                    active.remove(i)
            if not progressed:
                break
        return alloc

    def _set_group_voltage(self, label: str, total: float) -> None:
        g = self.cfg.groups[label]
        total = max(0.0, min(float(total), self._group_max_voltage(g)))
        alloc = self._split_voltage(g, total)
        for m, av in zip(g.members, alloc):
            self.set_voltage(m, av)  # voie physique : clamp + suivi consigne

    def _group_view(self, label: str) -> ChannelView:
        """Vue agrégée d'un groupe série, dérivée de l'état des voies membres."""
        g = self.cfg.groups[label]
        with self._state_lock:
            views = [self._set[m] for m in g.members]
            set_v = sum(v.set_voltage for v in views)
            set_i = min(v.set_current for v in views)
            output = all(v.output for v in views)
            meas_v = sum(v.meas_voltage for v in views)
            currents = [v.meas_current for v in views]
            modes = [v.mode for v in views]
        meas_i = sum(currents) / len(currents) if currents else 0.0
        # Le groupe est en CC si au moins une voie membre l'est.
        if not output:
            mode = ""
        elif "CC" in modes:
            mode = "CC"
        else:
            mode = "CV"
        return ChannelView(label, set_v, set_i, output, meas_v, meas_i, mode)

    def _read_current(self, label: str) -> float:
        """Courant mesuré d'une voie/groupe (auto-verrouillant : prend le/les
        verrou(s) PSU du label)."""
        with self._lock_for(label):
            if label in self.cfg.groups:
                members = self.cfg.groups[label].members
                vals = []
                for m in members:
                    inst, ch = self._route(m)
                    vals.append(inst.measure_current(ch))
                return sum(vals) / len(vals) if vals else 0.0
            inst, ch = self._route(label)
            return inst.measure_current(ch)

    def _read_current_median(self, label: str, n: int = 3) -> float:
        """Médiane de ``n`` lectures de courant espacées de ~10 ms. Le bruit de
        mesure sur une lecture UNIQUE fait osciller l'asservissement autour de la
        cible ; la médiane l'atténue sans introduire de retard notable."""
        if n <= 1:
            return self._read_current(label)
        vals = [self._read_current(label)]
        for _ in range(n - 1):
            time.sleep(0.01)
            vals.append(self._read_current(label))
        vals.sort()
        return vals[len(vals) // 2]

    def _max_voltage(self, label: str) -> float:
        if label in self.cfg.groups:
            return self._group_max_voltage(self.cfg.groups[label])
        return self.cfg.channels[label].max_voltage

    def _polarity(self, label: str) -> float:
        if label in self.cfg.groups:
            first = self.cfg.groups[label].members[0]
            return self.cfg.channels[first].polarity
        return self.cfg.channels[label].polarity

    def voltage_bounds(self, label: str) -> Tuple[float, float]:
        """Bornes de tension SIGNÉE d'une voie/groupe pour l'IHM : ``[0, +max]`` si
        polarité positive, ``[-max, 0]`` si négative. Le clamp du contrôleur reste
        l'autorité ; ces bornes ne sont qu'une aide de saisie."""
        mx = self._max_voltage(label)
        return (0.0, mx) if self._polarity(label) >= 0 else (-mx, 0.0)

    def current_bounds(self, label: str) -> Tuple[float, float]:
        """Bornes de limite de courant d'une voie/groupe pour l'IHM : ``[0, max]``
        (groupe : ``max_current`` du groupe sinon le plus petit des membres)."""
        if label in self.cfg.groups:
            return 0.0, self._group_max_current(self.cfg.groups[label])
        return 0.0, self.cfg.channels[label].max_current

    def eval_expression(self, expr: str) -> float:
        """Évalue une expression de consigne (ex. ``(VD/2)+VG1``) sur l'état
        courant. Un nom de voie nu vaut sa consigne de tension."""
        from .expressions import evaluate

        snap = self.snapshot()

        def resolver(kind: str, label: str) -> float:
            if label not in snap.channels:
                raise KeyError(f"voie inconnue dans l'expression : {label!r}")
            cv = snap.channels[label]
            if kind == "V":
                return cv.set_voltage
            if kind == "Vmeas":
                return cv.meas_voltage
            if kind == "Iset":
                return cv.set_current
            if kind == "Imeas":
                return cv.meas_current
            raise ValueError(f"grandeur inconnue : {kind}")

        return evaluate(expr, resolver)

    # ------------------------------------------------- séquence (orchestration)
    @property
    def is_sequence_running(self) -> bool:
        return self.runner.is_running

    def start_user_sequence(self, actions: List[Action], text: str = "") -> None:
        """Lance une séquence utilisateur (refusée si sécurité armée).

        ``text`` est le texte exact de la séquence : s'il est fourni et qu'un
        enregistrement est en cours, il est archivé dans ``sequence.seq``."""
        if not self._connected or self._comm_lost:
            self.log("Refusé : matériel non connecté. Vérifier la liaison avant de "
                     "lancer une séquence.")
            return
        if self._tripped:
            self.log("Refusé : sécurité active. Réarmer avant de lancer une séquence.")
            return
        if text and self._essai is not None:
            self._essai.write_sequence(text)
        self.runner.start(actions)

    def stop_sequence(self) -> None:
        """Interrompt la séquence utilisateur en cours (sans couper les voies).
        Sans effet — et journalisé — pendant une désalimentation de sécurité."""
        if self._essai is not None:
            self._essai.set_issue(ISSUE_ARRET_UTILISATEUR)
        if not self.runner.stop():
            self.log("Stop refusé : désalimentation de sécurité en cours.")

    def set_shutdown_sequence(self, path: Optional[str], log: bool = True) -> None:
        """Définit le fichier de séquentiel d'arrêt (None/"" = extinction auto
        ordonnée des voies). Utilisé par le bouton *Séquentiel d'arrêt* ET par la
        désalimentation de sécurité."""
        self._shutdown_path = path or None
        if not log:
            return
        if self._shutdown_path:
            self.log(f"Séquentiel d'arrêt : {self._shutdown_path}")
        else:
            self.log("Séquentiel d'arrêt : extinction auto ordonnée.")

    @property
    def shutdown_path(self) -> Optional[str]:
        return self._shutdown_path

    @property
    def is_shutting_down(self) -> bool:
        """Vrai pendant une désalimentation (ordonnée ou de sécurité) en cours."""
        return self._shutdown_inflight.is_set()

    def start_shutdown_sequence(self, reason: Optional[str] = None, trip: bool = False) -> None:
        """Déclenche la **désalimentation ordonnée** (extinction douce des voies).

        Utilisée par le bouton *Séquentiel d'arrêt* (``trip=False``) et par la
        sécurité thermique (``trip=True`` : on arme le verrou pour empêcher tout
        rallumage, mais on éteint proprement plutôt que d'un coup).
        """
        if self._shutdown_inflight.is_set():
            return
        self._shutdown_inflight.set()
        if trip:
            with self._state_lock:
                self._tripped = True
                self._safety_status = CRITICAL
                self._safety_message = reason or "Désalimentation de sécurité"
            self.log(f"!!! {reason} — désalimentation ordonnée en cours.")
            self._mark_safety_issue("trip", reason or "Désalimentation de sécurité")
        else:
            self.log("Séquentiel d'arrêt déclenché.")
        threading.Thread(target=self._shutdown_worker, daemon=True).start()

    def _shutdown_worker(self) -> None:
        """Exécute la désalimentation ordonnée. NE laisse JAMAIS la carte alimentée :
        tout échec (séquence utilisateur bloquée, ``runner.start`` qui lève, timeout de
        la désalimentation, exception imprévue) bascule en coupure dure via
        :meth:`emergency_stop` (idempotent, best-effort)."""
        try:
            # 1) Reprend la main sur une éventuelle séquence utilisateur (force_stop :
            #    on va lancer NOTRE séquence à la place, l'intention est inconditionnelle).
            self.runner.force_stop()
            wait_s = float(self.cfg.safety.get("shutdown_takeover_wait_s", 3.0))
            deadline = time.monotonic() + max(0.0, wait_s)
            while self.runner.is_running and time.monotonic() < deadline:
                time.sleep(0.05)
            if self.runner.is_running:
                # La séquence refuse de sortir (thread bloqué dans une query VISA en
                # timeout ?) : impossible de lancer la désalimentation ordonnée
                # (runner.start lèverait) -> coupure dure immédiate.
                self.log("Séquence utilisateur bloquée : bascule en coupure dure.")
                self.emergency_stop(
                    "Désalimentation ordonnée impossible (séquence bloquée) — coupure dure")
                return

            # 2) Charge les actions d'arrêt (repli sur extinction auto si invalide).
            try:
                actions = load_shutdown_actions(
                    self._shutdown_path,
                    labels=list(self.cfg.channels),
                    valid_labels=set(self.cfg.all_labels),
                    valid_sensors=set(self.cfg.temperatures),
                    delay=float(self.cfg.safety.get("shutdown_delay", 0.5)),
                    valid_relays=set(self.cfg.relay_labels),
                )
            except Exception as exc:
                from .sequencer import build_shutdown_actions
                self.log(f"Séquentiel d'arrêt invalide ({exc}) — extinction auto.")
                actions = build_shutdown_actions(
                    list(self.cfg.channels), float(self.cfg.safety.get("shutdown_delay", 0.5))
                )

            # 3) Exécute avec un garde-fou temporel : au-delà du budget, coupure dure.
            from .sequencer import estimate_duration
            budget = float(self.cfg.safety.get(
                "shutdown_timeout", estimate_duration(actions) + 30.0))
            self.runner.start(actions, safety_mode=True)  # s'exécute même verrou armé
            deadline = time.monotonic() + max(1.0, budget)
            while self.runner.is_running:
                if time.monotonic() > deadline:
                    self.log(f"Désalimentation trop longue (> {budget:.0f}s) — coupure dure.")
                    self.emergency_stop(
                        "Désalimentation ordonnée en timeout — coupure dure")
                    break
                time.sleep(0.05)
        except Exception as exc:
            # Dernier recours : quoi qu'il arrive, on tente de couper les voies.
            self.log(f"Échec désalimentation ordonnée : {exc}")
            try:
                self.emergency_stop(
                    f"Désalimentation ordonnée impossible ({exc}) — coupure dure")
            except Exception:
                pass
        finally:
            # Quel que soit le dénouement, les relais finissent à l'état de sécurité
            # (les sources sont coupées à ce stade -> on isole).
            self._drive_relays_safe()
            self._shutdown_inflight.clear()

    # ------------------------------------------------------------- sécurité
    def _mark_safety_issue(self, kind: str, message: str) -> None:
        """Inscrit un événement de sécurité et l'issue « déclenchement » dans le
        dossier d'essai en cours (sans effet hors enregistrement)."""
        essai = self._essai
        if essai is None:
            return
        essai.set_issue(ISSUE_DECLENCHEMENT, cause=message)
        essai.add_safety_event(kind, message)

    def emergency_stop(self, reason: str = "Arrêt d'urgence") -> None:
        """Coupe IMMÉDIATEMENT toutes les voies et arme le verrou de sécurité.

        Coupure brutale réservée à l'arrêt d'urgence opérateur et à la coupure
        dure de dernier recours. Pour un arrêt en douceur, voir
        :meth:`start_shutdown_sequence`.
        """
        self.abort_event.set()
        self.runner.force_stop()   # interrompt même une désalim de sécurité en cours
        # Coupure alim par alim, verrou pris en NON bloquant : une alim morte (VISA
        # figé, verrou tenu par une lecture bloquée) ne doit PAS retarder la coupure
        # des autres. La sécurité prime : on tente l'extinction même sans le verrou.
        for name in sorted(self._source_names):
            lk = self._instr_locks.get(name)
            got = lk.acquire(blocking=False) if lk else False
            try:
                self._instruments[name].all_outputs_off()
            except Exception as exc:
                self.log(f"Coupure {name} en erreur : {exc}")
            finally:
                if got:
                    lk.release()
        with self._state_lock:
            for v in self._set.values():
                v.output = False
            self._tripped = True
            self._hard_cut_done = True
            self._safety_status = CRITICAL
            self._safety_message = reason
        # Relais à l'état de sécurité (isolement) APRÈS l'armement du trip : une
        # fermeture concurrente arrivée entre-temps est ainsi soit refusée (tripped),
        # soit écrasée ici — jamais un relais laissé fermé pendant un trip.
        self._drive_relays_safe()
        self.log(f"!!! {reason} — toutes les voies coupées.")
        self._mark_safety_issue("coupure_dure", reason)

    def reset_safety(self) -> None:
        """Réarme après un déclenchement (à n'utiliser qu'une fois le défaut levé)."""
        with self._state_lock:
            self._tripped = False
            self._hard_cut_done = False
            self._comm_lost = False
            self._psu_fail = 0
            self._daq_fail = 0
            self._hw_fault_msg = ""
            self._hw_fault_seen = set()
            self._safety_status = OK
            self._safety_message = ""
        self.abort_event.clear()
        self.log("Sécurité réarmée.")

    @property
    def tripped(self) -> bool:
        return self._tripped

    # Enregistrement CSV / dossier d'essai : voir RecordingMixin
    # (alim_seq/controller_recording.py).

    # --------------------------------------- boucles de mesure / sécurité
    def start_polling(self) -> None:
        """Démarre les deux threads de fond : température (sécurité, rapide) et
        mesures V/I (affichage, plus lent). La boucle température n'est lancée que si
        des capteurs sont configurés. Idempotent (ne relance pas un thread vivant)."""
        self._stop_poll.clear()
        if self._temp_enabled and not (self._temp_thread and self._temp_thread.is_alive()):
            self._temp_thread = threading.Thread(target=self._temp_loop, name="temp", daemon=True)
            self._temp_thread.start()
        if not (self._meas_thread and self._meas_thread.is_alive()):
            self._meas_thread = threading.Thread(target=self._meas_loop, name="meas", daemon=True)
            self._meas_thread.start()

    def stop_polling(self) -> None:
        """Arrête les deux boucles de fond et attend la fin des threads (join borné)."""
        self._stop_poll.set()
        for t in (self._temp_thread, self._meas_thread):
            # ``ident`` est None tant que le thread n'a pas démarré : ne JOINDRE que les
            # threads réellement lancés (un ``start()`` qui aurait échoué laisserait
            # sinon un objet non démarré -> join() lèverait « before it is started »).
            if t is not None and t.ident is not None:
                t.join(timeout=2.0)

    # --- Boucle TEMPÉRATURE (sécurité, cadence rapide) ----------------------
    def _temp_loop(self) -> None:
        """Boucle de sécurité thermique (thread ``temp``). Lit les températures à
        ``temp_poll_interval`` (rapide), mesure la cadence réelle, et sur erreur
        répétée déclenche la gestion de perte de mesure. Indépendante des alims : un
        VISA figé ne peut pas la ralentir."""
        interval = float(self.cfg.safety.get(
            "temp_poll_interval", self.cfg.safety.get("poll_interval", 0.5)))
        last = None
        while not self._stop_poll.is_set():
            t0 = time.monotonic()
            if last is not None:
                self._temp_period = t0 - last
            last = t0
            try:
                self._temp_cycle()
                self._daq_fail = 0
            except Exception as exc:
                self._daq_fail += 1
                self.log(f"Erreur lecture température : {exc}")
                self._handle_temp_failure()
            self._stop_poll.wait(max(0.0, interval - (time.monotonic() - t0)))

    def _temp_cycle(self) -> None:
        """Un cycle de sécurité : lit les températures, classe chaque capteur, calcule
        le statut global, puis applique l'escalade de sécurité — (1) coupure DURE si
        un capteur dépasse critique + ``hard_margin_c``, (2) désalimentation ORDONNÉE
        au seuil critique, (3) désalimentation sur capteur en défaut si configuré."""
        # Boucle thermique : ne dépend QUE de l'instrument de température. Aucun verrou
        # de source tenu ici -> un VISA figé sur une alim ne peut pas retarder la sécurité.
        with self._instr_locks[self._daq_name]:
            temps = self._daq.read_temperatures()
            volts = self._daq.read_voltages()  # tensions brutes NI (filet de sécurité)
        ready = {n: self._sensor_ready(s) for n, s in self.cfg.temperatures.items()}
        per_sensor = {
            n: self._classify_sensor(n, temps.get(n, float("nan")), ready[n])
            for n in self.cfg.temperatures
        }
        status, message, crit_sensor, fault_sensor = self._overall_temp_status(temps, per_sensor)

        with self._state_lock:
            self._temperatures = temps
            self._temp_voltages = volts
            self._temp_status = per_sensor
            if not self._tripped and not self._comm_lost:
                self._safety_status = status
                self._safety_message = message

        # 1) Coupure DURE de dernier recours (capteurs NA/FAULT exclus).
        hard_margin = float(self.cfg.safety.get("hard_margin_c", 15.0))
        for name, t in temps.items():
            if per_sensor[name] in (NA, FAULT):
                continue
            if t == t and t >= self.cfg.temperatures[name].critical + hard_margin:
                if not self._hard_cut_done:
                    self.emergency_stop(
                        f"Coupure dure : {name} = {t:.1f}°C "
                        f"(> critique + {hard_margin:.0f}°C)"
                    )
                return

        # 2) Seuil critique -> désalimentation ORDONNÉE (douce).
        if status == CRITICAL and not self._tripped:
            if self.cfg.safety.get("auto_shutdown_on_critical", True):
                self.start_shutdown_sequence(
                    reason=f"Température critique {crit_sensor} = {temps[crit_sensor]:.1f}°C",
                    trip=True,
                )
            return

        # 3) Capteur en DÉFAUT -> désalimentation seulement si configuré.
        if fault_sensor and not self._tripped \
                and self.cfg.safety.get("shutdown_on_sensor_fault", False):
            self.start_shutdown_sequence(
                reason=f"Capteur en défaut : {fault_sensor}", trip=True)

    def _handle_temp_failure(self) -> None:
        """Après ``comm_fail_limit`` erreurs de lecture température consécutives,
        déclare la perte de mesure. Comme les alims répondent probablement encore, la
        désalimentation peut être DOUCE (si des voies sont ON et ``shutdown_on_temp_lost``)."""
        limit = int(self.cfg.safety.get("comm_fail_limit", 3))
        if self._daq_fail < limit or self._comm_lost:
            return
        any_on = any(self._set[l].output for l in self.cfg.channels)
        msg = "Perte de la mesure de température (module NI)"
        # Les alims communiquent sans doute encore -> désalimentation DOUCE possible.
        gentle = any_on and self.cfg.safety.get("shutdown_on_temp_lost", True)
        self._declare_comm_lost(msg, gentle=gentle, shutdown=any_on)

    # --- Boucle MESURES V/I (affichage / logs, cadence plus lente) ----------
    def _meas_loop(self) -> None:
        """Boucle de mesure V/I (thread ``meas``). Lit tensions/courants/mode à
        ``poll_interval`` (plus lent, latence SCPI), alimente l'affichage et le CSV,
        et sur erreur répétée déclenche la gestion de perte de communication alim."""
        interval = float(self.cfg.safety.get("poll_interval", 0.5))
        last = None
        while not self._stop_poll.is_set():
            t0 = time.monotonic()
            if last is not None:
                self._meas_period = t0 - last
            last = t0
            try:
                self._meas_cycle()
                self._psu_fail = 0
            except Exception as exc:
                self._psu_fail += 1
                self.log(f"Erreur mesure alimentation : {exc}")
                self._handle_psu_failure()
            self._stop_poll.wait(max(0.0, interval - (time.monotonic() - t0)))

    def _meas_cycle(self) -> None:
        """Un cycle de mesure : lit V/I/mode/défauts de chaque voie (alim par alim,
        chacune sous son seul verrou, acquis **avec timeout** — une alim au verrou
        indisponible est sautée ce cycle, jamais bloquante), met à jour l'état,
        remonte les défauts matériels HMP et écrit une ligne CSV si un
        enregistrement est en cours."""
        with self._state_lock:
            sp = {l: (self._set[l].set_voltage, self._set[l].set_current,
                      self._set[l].output, self._set[l].mode)
                  for l in self.cfg.channels}
        meas: Dict[str, Tuple[float, float]] = {}
        modes: Dict[str, str] = {}
        faults: Dict[str, tuple] = {}
        # On mesure alim par alim, chacune sous SON verrou. Acquisition AVEC TIMEOUT :
        # un verrou tenu par un appel VISA suspendu (socket mort, timeout inopérant)
        # bloquerait sinon la boucle ENTIÈRE en silence — aucune exception, donc pas
        # de détection de perte de comm. Une alim indisponible est SAUTÉE ce cycle
        # (dernières valeurs conservées) et journalisée après plusieurs cycles ratés.
        by_supply: Dict[str, List[str]] = {}
        for label in self.cfg.channels:
            name = self._routing[label][0]
            by_supply.setdefault(name, []).append(label)
        skipped: List[str] = []
        for name in sorted(by_supply):
            lk = self._instr_locks[name]
            if not lk.acquire(timeout=1.0):
                skipped.extend(by_supply[name])
                n = self._meas_skip.get(name, 0) + 1
                self._meas_skip[name] = n
                if n == 5:
                    self.log(f"!!! Mesures {name} : instrument indisponible depuis "
                             f"{n} cycles (liaison VISA figée ?) — valeurs figées.")
                continue
            try:
                inst = self._instruments[name]
                for label in by_supply[name]:
                    ch = self._routing[label][1]
                    v = self.cfg.channels[label].polarity * inst.measure_voltage(ch)
                    i = inst.measure_current(ch)
                    st = inst.measure_status(ch)  # 1 requête : mode + défauts
                    meas[label] = (v, i)
                    modes[label] = st.get("mode") or self._infer_mode(sp[label], v, i)
                    faults[label] = tuple(st.get("faults") or ())
            finally:
                lk.release()
            if self._meas_skip.get(name, 0) >= 5:
                self.log(f"Mesures {name} : instrument de nouveau disponible.")
            self._meas_skip[name] = 0
        with self._state_lock:
            for label, (v, i) in meas.items():
                self._set[label].meas_voltage = v
                self._set[label].meas_current = i
                self._set[label].mode = modes[label]
                self._set[label].faults = faults[label]
            # Voies sautées : on complète avec les DERNIÈRES valeurs connues pour que
            # le CSV et les défauts restent continus (pas de faux 0 V / 0 A).
            for label in skipped:
                meas[label] = (self._set[label].meas_voltage,
                               self._set[label].meas_current)
                faults[label] = self._set[label].faults
            temps = dict(self._temperatures)
            volts = dict(self._temp_voltages)
            status = self._safety_status
        self._handle_hw_faults(faults)
        self._record_row(meas, temps, volts, status)

    def _handle_hw_faults(self, faults: Dict[str, tuple]) -> None:
        """Remonte les défauts matériels du HMP (OVP/fusible/surchauffe).

        Journalise chaque nouveau défaut, met à jour la bannière, et déclenche
        une désalimentation ordonnée si ``safety.shutdown_on_hw_fault`` est vrai.
        """
        active = {label: f for label, f in faults.items() if f}
        labels = ["{} [{}]".format(label, "/".join(f)) for label, f in active.items()]
        with self._state_lock:
            self._hw_fault_msg = "Défaut alim : " + ", ".join(labels) if labels else ""
        # Journalise les nouveaux couples (voie, défaut).
        current = {(label, code) for label, fs in active.items() for code in fs}
        for label, code in current - self._hw_fault_seen:
            self.log(f"!!! Défaut matériel {code} sur la voie {label}")
        self._hw_fault_seen = current
        if active and not self._tripped \
                and self.cfg.safety.get("shutdown_on_hw_fault", False):
            self.start_shutdown_sequence(
                reason="Défaut matériel alim : " + ", ".join(labels), trip=True)

    def _handle_psu_failure(self) -> None:
        """Après ``comm_fail_limit`` erreurs de mesure alim consécutives, déclare la
        perte de communication. L'alim étant injoignable, une rampe propre est
        impossible → coupure d'urgence (best effort)."""
        limit = int(self.cfg.safety.get("comm_fail_limit", 3))
        if self._psu_fail < limit or self._comm_lost:
            return
        # Alim injoignable : on ne peut pas faire une rampe propre -> coupure
        # d'urgence (best effort, elle échouera peut-être mais on tente).
        self._declare_comm_lost(
            "Perte de communication avec une alimentation", gentle=False, shutdown=True)

    def _declare_comm_lost(self, msg: str, gentle: bool, shutdown: bool) -> None:
        """Bascule en état perte de communication (``FAULT``) et, si ``shutdown``,
        désalimente : en douceur (``gentle=True``, les alims répondent encore) ou par
        coupure dure (``gentle=False``, alim injoignable — best effort)."""
        with self._state_lock:
            self._comm_lost = True
            self._safety_status = FAULT
            self._safety_message = msg
        self.log(f"!!! {msg}")
        self._mark_safety_issue("perte_comm", msg)
        if not shutdown:
            return
        if gentle:
            self.start_shutdown_sequence(reason=msg, trip=True)
        else:
            self.emergency_stop(msg)

    @staticmethod
    def _infer_mode(sp: Tuple[float, float, bool, str], v: float, i: float) -> str:
        """Infère CV/CC à partir des consignes et des mesures (V signée).

        Le HMP4040 n'exposant pas d'état CC/CV en SCPI, on déduit le mode de deux
        signaux : courant proche de la limite, et/ou tension mesurée nettement
        sous la consigne. Une **hystérésis** (seuils 'forts' distincts pour entrer
        et sortir du CC) évite que l'affichage clignote au point de bascule.
        """
        vset, iset, out, prev = sp
        if not out:
            return ""
        vmag = abs(vset)
        vdrop = vmag - abs(v)
        cc_strong = (iset > 0 and i >= iset * 0.99) or \
                    (vmag > 0.05 and vdrop > max(0.07 * vmag, 0.05))
        cv_strong = (iset <= 0 or i <= iset * 0.90) and \
                    (vmag <= 0.05 or vdrop < max(0.03 * vmag, 0.02))
        if prev == "CC":
            return "CV" if cv_strong else "CC"
        if prev == "CV":
            return "CC" if cc_strong else "CV"
        return "CC" if cc_strong else "CV"

    def _classify_sensor(self, name: str, temp: float, ready: bool) -> str:
        """Classe un capteur : ``NA`` (voie requise pas encore ON), ``FAULT`` (NaN,
        hors bande de plausibilité, ou tension de référence du pont hors tolérance),
        sinon niveau thermique ``OK``/``WARNING``/``CRITICAL``. Un capteur ``NA`` ou
        ``FAULT`` est exclu du calcul de sécurité (jamais une fausse valeur plausible)."""
        if not ready:
            return NA
        s = self.cfg.temperatures[name]
        if temp != temp:  # NaN
            return FAULT
        if (s.valid_min is not None and temp < s.valid_min) or \
           (s.valid_max is not None and temp > s.valid_max):
            return FAULT
        # Contrôle optionnel de la tension de référence du pont : si la voie qui
        # l'alimente s'écarte trop du v_ref attendu, la mesure n'est pas fiable.
        if s.ref_channel:
            vref = s.expected_vref
            if vref:
                meas = abs(self._measured_voltage(s.ref_channel))
                if meas == meas and abs(meas - vref) > s.ref_tol * abs(vref):
                    return FAULT
        return self._sensor_level(name, temp)

    def _measured_voltage(self, label: str) -> float:
        """Tension MESURÉE (signée) d'une voie ou d'un groupe (somme des membres)."""
        with self._state_lock:
            if label in self.cfg.groups:
                return sum(self._set[m].meas_voltage for m in self.cfg.groups[label].members)
            v = self._set.get(label)
            return v.meas_voltage if v else float("nan")

    def _sensor_level(self, name: str, temp: float) -> str:
        s = self.cfg.temperatures[name]
        if temp >= s.critical:
            return CRITICAL
        if temp >= s.warning:
            return WARNING
        return OK

    def _channel_is_on(self, label: str) -> bool:
        if label in self.cfg.groups:
            return all(self._set[m].output for m in self.cfg.groups[label].members)
        v = self._set.get(label)
        return bool(v and v.output)

    def _sensor_ready(self, sensor) -> bool:
        """Le capteur est valide si toutes ses voies 'requires' sont ON."""
        return all(self._channel_is_on(req) for req in sensor.requires)

    def _overall_temp_status(self, temps, per_sensor):
        """Retourne (status, message, capteur_critique, capteur_defaut).
        Rang croissant de gravité : OK < WARNING < FAULT < CRITICAL."""
        order = {OK: 0, WARNING: 1, FAULT: 2, CRITICAL: 3}
        worst, message = OK, ""
        crit_sensor = fault_sensor = None
        for name, lvl in per_sensor.items():
            if lvl == NA:
                continue
            if lvl == FAULT and fault_sensor is None:
                fault_sensor = name
            if lvl == CRITICAL and crit_sensor is None:
                crit_sensor = name
            if order.get(lvl, 0) > order.get(worst, 0):
                worst = lvl
                if lvl == FAULT:
                    message = f"{name} : capteur en défaut"
                elif lvl == CRITICAL:
                    message = f"{name} = {temps[name]:.1f}°C >= critique"
                elif lvl == WARNING:
                    message = f"{name} = {temps[name]:.1f}°C >= alerte"
        return worst, message, crit_sensor, fault_sensor

    # ------------------------------------------------------------- snapshot
    def snapshot(self) -> Snapshot:
        """Retourne un :class:`Snapshot` cohérent de tout l'état (voies, groupes,
        températures, sécurité, connexion). Thread-safe et sans I/O matérielle :
        c'est l'unique point de lecture pour l'IHM et pour ``eval_expression``."""
        with self._state_lock:
            channels = {
                label: ChannelView(
                    v.label, v.set_voltage, v.set_current, v.output,
                    v.meas_voltage, v.meas_current, v.mode, v.faults,
                )
                for label, v in self._set.items()
            }
        # Vues agrégées des groupes série (hors verrou : _group_view le reprend).
        for gname in self.cfg.groups:
            channels[gname] = self._group_view(gname)
        # États des relais (hors _state_lock : prend les verrous instrument des relais).
        relays = self.relay_states() if self._relay_names else {}
        # Voies dont l'instrument source a été sauté au dernier cycle de mesure
        # (liaison VISA figée) : leurs V/I sont périmés.
        stale = {label for label in self.cfg.channels
                 if self._meas_skip.get(self._routing[label][0], 0) > 0}
        with self._state_lock:
            return Snapshot(
                channels=channels,
                temperatures=dict(self._temperatures),
                temp_status=dict(self._temp_status),
                safety_status=self._safety_status,
                safety_message=self._safety_message,
                tripped=self._tripped,
                connected=self._connected,
                comm_lost=self._comm_lost,
                hw_fault=self._hw_fault_msg,
                meas_period=self._meas_period,
                temp_period=self._temp_period,
                relays=relays,
                stale_labels=stale,
            )

    # Asservissement (servo / servo_adaptive) : voir ServoMixin
    # (alim_seq/controller_servo.py).
