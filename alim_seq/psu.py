"""Drivers d'alimentation et gestionnaire de voies.

- :class:`BasePSU`     : interface commune (nombre de voies via ``n_channels``).
- :class:`HMP4040` et variantes HMP4030 / HMP2030 / HMP2020 : drivers réels R&S
                          via SCPI (pyvisa), même famille, nombre de voies différent.
- :class:`MockPSU`     : simulation (charge résistive + bruit), nombre de voies
                          paramétrable (``MockHMP4040`` = alias).
- :data:`PSU_MODELS` / :func:`create_psu` : registre des modèles + fabrique. Pour
                          ajouter un modèle, écrire son driver et l'y enregistrer.

Une alimentation est un :class:`~alim_seq.instrument.Instrument` exposant les
capacités :class:`~alim_seq.instrument.SourceTension` et
:class:`~alim_seq.instrument.MesureVI`. Le routage label→(instrument, canal) et la
sérialisation des accès (un verrou par instrument) sont gérés par le contrôleur.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .instrument import Instrument, MesureVI, SourceTension


def scan_instruments(model_filter: str = "", visa_backend: str = "",
                     timeout_ms: int = 1500) -> List[Dict[str, str]]:
    """Liste les instruments VISA disponibles et interroge leur ``*IDN?``.

    Retourne une liste de dicts ``{'resource': ..., 'idn': ...}``. Si
    ``model_filter`` est non vide, ne garde que les ressources dont l'IDN (ou la
    ressource) contient ce texte (ex. 'HMP4040').

    Très fiable en USB-TMC (énumération native) ; en LAN la découverte dépend de
    la VISA (NI/Keysight la font, pyvisa-py est limité). Lève ``RuntimeError`` si
    pyvisa n'est pas installé.
    """
    try:
        import pyvisa
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement
        raise RuntimeError("pyvisa requis pour le scan VISA") from exc

    rm = pyvisa.ResourceManager(visa_backend) if visa_backend else pyvisa.ResourceManager()
    found: List[Dict[str, str]] = []
    try:
        resources = rm.list_resources()
    except Exception:
        resources = ()
    mf = model_filter.upper()
    for res in resources:
        idn = ""
        try:
            inst = rm.open_resource(res)
            inst.timeout = timeout_ms
            inst.read_termination = "\n"
            inst.write_termination = "\n"
            idn = str(inst.query("*IDN?")).strip()
            inst.close()
        except Exception:
            pass  # ressource muette ou occupée : on la garde sans IDN
        if not mf or mf in idn.upper() or mf in res.upper():
            found.append({"resource": res, "idn": idn})
    return found


def probe_instrument(resource: str, visa_backend: str = "",
                     timeout_ms: int = 2000) -> str:
    """Ouvre une **ressource VISA précise** et renvoie son ``*IDN?`` (SCPI).

    Complète :func:`scan_instruments` (qui, lui, ne peut énumérer un **socket TCP
    brut** ``TCPIP0::IP::5025::SOCKET`` — le mode LAN recommandé pour les HMP) :
    ici l'adresse est CONNUE, on la teste directement. Lève ``RuntimeError`` si
    pyvisa manque, si l'ouverture échoue ou si la liaison ne répond pas à ``*IDN?``.
    """
    try:
        import pyvisa
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement
        raise RuntimeError("pyvisa requis pour tester une adresse VISA") from exc
    rm = pyvisa.ResourceManager(visa_backend) if visa_backend else pyvisa.ResourceManager()
    try:
        inst = rm.open_resource(resource)
    except Exception as exc:
        raise RuntimeError(f"ouverture impossible : {exc}") from exc
    try:
        inst.timeout = timeout_ms
        inst.read_termination = "\n"
        inst.write_termination = "\n"
        idn = str(inst.query("*IDN?")).strip()
        if not idn:
            raise RuntimeError("réponse vide à '*IDN?'")
        return idn
    except Exception as exc:
        raise RuntimeError(f"pas de réponse à '*IDN?' : {exc}") from exc
    finally:
        try:
            inst.close()
        except Exception:
            pass


@dataclass
class ChannelState:
    """Consigne courante d'une voie (ce qui a été demandé à l'alim)."""
    set_voltage: float = 0.0
    set_current: float = 0.1
    output: bool = False


class BasePSU(Instrument, SourceTension, MesureVI):
    """Interface d'une alimentation multi-voies (canaux numérotés à partir de 1).

    Une alimentation est un :class:`~alim_seq.instrument.Instrument` qui expose les
    capacités :class:`~alim_seq.instrument.SourceTension` (tension + limite de
    courant) et :class:`~alim_seq.instrument.MesureVI` (mesure V/I).
    """

    n_channels = 4

    def connect(self) -> None: ...
    def close(self) -> None: ...

    def set_voltage(self, channel: int, voltage: float) -> None: ...
    def set_current(self, channel: int, current: float) -> None: ...
    def set_output(self, channel: int, on: bool) -> None: ...

    def measure_voltage(self, channel: int) -> float: ...
    def measure_current(self, channel: int) -> float: ...

    def measure_mode(self, channel: int) -> Optional[str]:
        """Renvoie 'CV', 'CC' ou None (inconnu) lu depuis l'appareil."""
        return self.measure_status(channel).get("mode")

    def measure_status(self, channel: int) -> Dict[str, object]:
        """État complet d'une voie : mode CV/CC + défauts matériels.

        Retourne {'mode': 'CV'|'CC'|None, 'faults': [...]} où faults peut contenir
        'OVP' (surtension), 'FUSE' (fusible électronique), 'OTP' (surchauffe).
        """
        return {"mode": None, "faults": []}

    def all_outputs_off(self) -> None:
        for ch in range(1, self.n_channels + 1):
            self.set_output(ch, False)


class HMP4040(BasePSU):
    """Driver SCPI pour Rohde & Schwarz HMP4040 (via pyvisa).

    Les commandes SCPI suivent la documentation HMP. La sélection de la voie
    active se fait avec ``INST OUT<n>`` ; chaque voie possède son interrupteur
    ``OUTP:SEL`` et l'alimentation un interrupteur général ``OUTP:GEN``.
    """

    # Limites SOA par voie (datasheet HMP4040). Bornes hautes de la famille : un
    # modèle plus petit limite davantage côté firmware. Sert à VALIDER la config.
    max_voltage = 32.0
    max_current = 10.0
    max_power = 160.0

    def __init__(self, resource: str, timeout_ms: int = 5000, use_opc: bool = True,
                 visa_backend: str = "", use_cc_status: bool = False,
                 query_delay_s: float = 0.0, log: Optional[Callable[[str], None]] = None):
        self.resource = resource
        self.timeout_ms = timeout_ms
        # Callback de journalisation (étapes de connexion). Inoffensif si None.
        self._log = log or (lambda _m: None)
        self.idn = ""
        # use_opc=True : on attend *OPC? après chaque commande de réglage pour
        # garantir que l'alimentation a fini de la traiter avant de continuer.
        self.use_opc = use_opc
        # Backend VISA : "" = VISA système (Keysight IO Libs, NI-VISA…) détectée
        # automatiquement ; "@py" = pyvisa-py (pur Python).
        self.visa_backend = visa_backend
        # Lecture CV/CC via le registre d'état (SCPI à confirmer sur ton HMP).
        # Désactivé par défaut : on retombe sur l'inférence côté contrôleur.
        self.use_cc_status = use_cc_status
        self._cc_status_ok = use_cc_status
        # Délai write->read appliqué à chaque query (pyvisa.query_delay). 0 convient
        # en USB-TMC / VXI-11 (messages délimités) ; mets ~0.02 si le firmware
        # renvoie des "input protocol violation" sporadiques.
        self.query_delay_s = query_delay_s
        # Détecté depuis la chaîne resource : un socket brut (::5025::SOCKET) EXIGE
        # des terminaisons et ne supporte pas toujours clear().
        self._is_socket = "SOCKET" in resource.upper()
        self._inst = None
        self._selected: Optional[int] = None

    def connect(self) -> None:
        try:
            import pyvisa  # import paresseux : non requis en mode simulation
        except ImportError as exc:  # pragma: no cover - dépend de l'environnement
            raise RuntimeError(
                "pyvisa n'est pas installé (requis en mode matériel réel). "
                "Installer pyvisa, ou passer en simulation ('simulate': true)."
            ) from exc

        # 1) Ouverture de la session VISA.
        self._log(f"[{self.resource}] ouverture VISA "
                  f"(backend={self.visa_backend or 'système'})…")
        try:
            rm = pyvisa.ResourceManager(self.visa_backend) if self.visa_backend \
                else pyvisa.ResourceManager()
            self._inst = rm.open_resource(self.resource)
        except Exception as exc:
            raise RuntimeError(
                f"[{self.resource}] ouverture VISA impossible : {exc}. "
                f"Vérifier la chaîne 'resource' et le backend VISA installé."
            ) from exc
        self._inst.timeout = self.timeout_ms

        # 2) Terminaisons explicites : le HMP4040 répond par un '\n' aux commandes
        # comme aux requêtes. En USB-TMC / VXI-11 (::INSTR) les messages sont
        # auto-délimités (inoffensif) ; en socket brut (::5025::SOCKET) c'est
        # OBLIGATOIRE, sinon chaque query bloque jusqu'au timeout. Tout est ASCII ici.
        self._inst.read_termination = "\n"
        self._inst.write_termination = "\n"
        if self.query_delay_s:
            self._inst.query_delay = self.query_delay_s

        # 3) PURGE du buffer. Correctif clé de l'« inversion » tension/courant en TMC :
        # un run précédent interrompu (Ctrl-C pendant une query) laisse une réponse en
        # attente ; la 1re lecture du nouveau run la récupère et tout se décale d'un cran.
        self._safe_clear()

        # 4) Sonde *IDN? : échec RAPIDE et EXPLICITE si la liaison ne répond pas,
        # AVANT d'enchaîner les commandes de configuration (sinon on timeoute sans dire où).
        try:
            self.idn = str(self._query("*IDN?")).strip()
        except Exception as exc:
            raise RuntimeError(
                f"[{self.resource}] pas de réponse à '*IDN?' : {exc}.\n"
                f"  Pistes : socket brut -> la 'resource' doit finir par '::5025::SOCKET' ; "
                f"USB -> régler l'alim en mode TMC (PAS CDC) ; vérifier IP/câble/pare-feu ; "
                f"VXI-11 (::inst0::INSTR) peut timeouter selon la VISA."
            ) from exc
        self._log(f"[{self.resource}] IDN: {self.idn}")
        if "HMP" not in self.idn.upper():
            self._log(f"[{self.resource}] ATTENTION : '{self.idn}' ne ressemble pas à "
                      f"un R&S HMP — vérifier que c'est la bonne ressource.")

        # 5) Configuration : on désélectionne TOUTES les voies (OUTP:SEL OFF) AVANT
        # d'activer l'interrupteur général, pour qu'aucune sortie ne s'active à la
        # connexion (modèle OUTP:SEL par voie + OUTP:GEN général, manuel §8.6).
        try:
            self._inst.write("*CLS")
            for ch in range(1, self.n_channels + 1):
                self._write(f"INST OUT{ch}")
                self._write("OUTP:SEL OFF")
            self._selected = self.n_channels
            self._write("OUTP:GEN ON")
        except Exception as exc:
            raise RuntimeError(
                f"[{self.resource}] échec d'initialisation SCPI : {exc}. "
                f"L'instrument répond à *IDN? mais pas aux commandes de configuration."
            ) from exc
        self._log(f"[{self.resource}] {self.model} prêt ({self.n_channels} voies).")

    def _safe_clear(self) -> None:
        """Vide le buffer d'E/S de l'instrument, quel que soit le transport.

        VISA ``clear()`` (Device Clear) fonctionne en USB-TMC et VXI-11. Sur un
        socket brut il peut échouer : on draine alors les octets en attente avec
        un timeout très court.
        """
        if self._inst is None:
            return
        if not self._is_socket:
            try:
                self._inst.clear()
                return
            except Exception:
                pass
        old_timeout = self._inst.timeout
        try:
            self._inst.timeout = 60
            while True:
                self._inst.read()  # lève une exception quand le buffer est vide
        except Exception:
            pass
        finally:
            self._inst.timeout = old_timeout

    def close(self) -> None:
        if self._inst is not None:
            # Fermeture : on veut couper les sorties SANS rester bloqué si l'alim
            # ne répond plus. On raccourcit le timeout VISA et on désactive l'attente
            # *OPC? le temps de l'extinction, puis on restaure (au cas où l'instance
            # serait réutilisée), et on ferme la session quoi qu'il arrive.
            old_timeout = None
            old_use_opc = self.use_opc
            try:
                old_timeout = self._inst.timeout
                self._inst.timeout = min(old_timeout, 1000)
            except Exception:
                pass
            self.use_opc = False
            try:
                self.all_outputs_off()
            except Exception:
                pass
            finally:
                self.use_opc = old_use_opc
                try:
                    if old_timeout is not None:
                        self._inst.timeout = old_timeout
                except Exception:
                    pass
                try:
                    self._inst.close()
                finally:
                    self._inst = None

    def _write(self, cmd: str) -> None:
        """Envoie une commande et, si use_opc, bloque jusqu'à *OPC?.

        Sur les HMP, ``*OPC?`` renvoie 1 lorsque toutes les commandes en attente
        sont terminées : c'est le moyen fiable de s'assurer qu'un VOLT/CURR/OUTP
        a bien été pris en compte avant d'enchaîner. Le couple write+query garde
        aussi les E/S équilibrées (autant de lectures que d'écritures), ce qui
        évite tout décalage du buffer.
        """
        self._inst.write(cmd)
        if self.use_opc:
            self._query("*OPC?")

    def _query(self, cmd: str) -> str:
        """Query avec UNE reprise : si une erreur d'E/S survient (réponse en
        attente, désync, 'input protocol violation' sporadique du HMP), on purge
        le buffer et on retente une fois avant de propager l'erreur.
        """
        import pyvisa
        try:
            return self._inst.query(cmd)
        except pyvisa.errors.VisaIOError:
            self._safe_clear()
            return self._inst.query(cmd)

    def _select(self, channel: int) -> None:
        if channel != self._selected:
            self._write(f"INST OUT{channel}")
            self._selected = channel

    def set_voltage(self, channel: int, voltage: float) -> None:
        self._select(channel)
        self._write(f"VOLT {voltage:.4f}")

    def set_current(self, channel: int, current: float) -> None:
        self._select(channel)
        self._write(f"CURR {current:.4f}")

    def set_output(self, channel: int, on: bool) -> None:
        self._select(channel)
        self._write(f"OUTP:SEL {'ON' if on else 'OFF'}")

    def measure_voltage(self, channel: int) -> float:
        self._select(channel)
        return float(self._query("MEAS:VOLT?"))

    def measure_current(self, channel: int) -> float:
        self._select(channel)
        return float(self._query("MEAS:CURR?"))

    def measure_mode(self, channel: int) -> Optional[str]:
        return self.measure_status(channel).get("mode")

    def measure_status(self, channel: int) -> Dict[str, object]:
        """Mode CV/CC + défauts matériels, lus sur le registre Questionable du HMP.

        Conforme au manuel HMP (§7.1.5.2, table 7-2) :
        ``STAT:QUES:INST:ISUM<voie>:COND?`` -> bit 0 = CC, bit 1 = CV,
        bit 4 = surchauffe (OTP), bit 9 = OVP déclenchée, bit 10 = fusible
        électronique déclenché (FUSE). Une seule requête sert tout.
        En cas d'échec (firmware non compatible), on se désactive (repli inférence).
        """
        if not self._cc_status_ok:
            return {"mode": None, "faults": []}
        try:
            self._select(channel)
            cond = int(self._query(f"STAT:QUES:INST:ISUM{channel}:COND?"))
        except Exception:
            self._cc_status_ok = False  # non supporté -> on n'insiste pas
            return {"mode": None, "faults": []}
        mode = "CC" if (cond & 0b01) else ("CV" if (cond & 0b10) else None)
        faults = []
        if cond & (1 << 4):
            faults.append("OTP")    # surchauffe
        if cond & (1 << 9):
            faults.append("OVP")    # surtension déclenchée
        if cond & (1 << 10):
            faults.append("FUSE")   # fusible électronique déclenché
        return {"mode": mode, "faults": faults}


HMP4040.model = "HMP4040"


class HMP4030(HMP4040):
    """R&S HMP4030 — même famille SCPI, 3 voies."""
    n_channels = 3
    model = "HMP4030"


class HMP2030(HMP4040):
    """R&S HMP2030 — même famille SCPI, 3 voies (5 A/voie)."""
    n_channels = 3
    model = "HMP2030"
    max_current = 5.0
    max_power = 80.0


class HMP2020(HMP4040):
    """R&S HMP2020 — même famille SCPI, 2 voies."""
    n_channels = 2
    model = "HMP2020"


class MockPSU(BasePSU):
    """Alimentation simulée (nombre de voies paramétrable).

    Modèle simple : chaque voie alimente une charge résistive. Le courant mesuré
    vaut V/R, écrêté par la limite de courant (mode CC). Permet de tester l'IHM,
    le séquenceur et l'asservissement sans matériel, pour n'importe quel modèle.
    """

    # Résistance de charge par défaut (ohms) par canal — modifie pour tes essais.
    DEFAULT_LOADS = {1: 5.0, 2: 6.0, 3: 8.0, 4: 12.0}

    def __init__(self, name: str = "MOCK", n_channels: int = 4,
                 loads: Optional[Dict[int, float]] = None):
        self.name = name
        self.n_channels = int(n_channels)
        self.loads = {ch: self.DEFAULT_LOADS.get(ch, 10.0)
                      for ch in range(1, self.n_channels + 1)}
        if loads:
            self.loads.update(loads)
        self._state: Dict[int, ChannelState] = {
            ch: ChannelState() for ch in range(1, self.n_channels + 1)
        }
        # Source de courant pilotée (modèle transistor) : si défini pour un canal,
        # la charge devient un puits de courant Id=callable() au lieu d'une
        # résistance fixe. Utilisé pour le couplage grille->drain en simulation.
        self._current_source: Dict[int, "Callable[[], float]"] = {}

    def set_current_source(self, channel: int, source) -> None:
        """Installe (ou retire si None) une source de courant pilotée sur un canal."""
        if source is None:
            self._current_source.pop(channel, None)
        else:
            self._current_source[channel] = source

    def set_load(self, channel: int, ohms: float) -> None:
        """Change la charge résistive simulée d'un canal (Ω). Réglage à chaud utilisé
        par l'interface de configuration de la simulation."""
        self.loads[channel] = max(0.0, float(ohms))

    def connect(self) -> None:
        pass

    def close(self) -> None:
        self.all_outputs_off()

    def set_voltage(self, channel: int, voltage: float) -> None:
        self._state[channel].set_voltage = float(voltage)

    def set_current(self, channel: int, current: float) -> None:
        self._state[channel].set_current = float(current)

    def set_output(self, channel: int, on: bool) -> None:
        self._state[channel].output = bool(on)

    def _operating_point(self, channel: int) -> Tuple[float, float]:
        """Retourne (tension, courant) au point de fonctionnement simulé."""
        st = self._state[channel]
        if not st.output:
            return 0.0, 0.0
        # Canal piloté en courant (puits de courant type transistor).
        src = self._current_source.get(channel)
        if src is not None:
            i_demand = max(0.0, float(src()))
            i = min(i_demand, st.set_current)   # écrêté par la limite de courant
            return st.set_voltage, i            # CV à la tension de consigne
        # Charge résistive classique.
        r = self.loads.get(channel, 10.0)
        i_cv = st.set_voltage / r if r > 0 else st.set_current
        if i_cv > st.set_current:
            # Limitation de courant (mode CC) : la tension chute.
            i = st.set_current
            v = i * r
        else:
            i = i_cv
            v = st.set_voltage
        return v, i

    def measure_voltage(self, channel: int) -> float:
        v, _ = self._operating_point(channel)
        return v * (1.0 + random.uniform(-0.002, 0.002))

    def measure_current(self, channel: int) -> float:
        _, i = self._operating_point(channel)
        return i * (1.0 + random.uniform(-0.005, 0.005))

    def measure_mode(self, channel: int) -> Optional[str]:
        st = self._state[channel]
        if not st.output:
            return None
        src = self._current_source.get(channel)
        if src is not None:
            return "CC" if max(0.0, float(src())) > st.set_current else "CV"
        r = self.loads.get(channel, 10.0)
        i_cv = st.set_voltage / r if r > 0 else st.set_current
        return "CC" if i_cv > st.set_current else "CV"

    def measure_status(self, channel: int) -> Dict[str, object]:
        # Pas de défaut matériel simulé (OVP/fusible/surchauffe gérés par le HMP réel).
        return {"mode": self.measure_mode(channel), "faults": []}

    def output_power(self, channel: int) -> float:
        v, i = self._operating_point(channel)
        return v * i


MockHMP4040 = MockPSU  # alias rétrocompatible


# --------------------------------------------------------------- registre modèles
# Pour ajouter un nouveau modèle d'alimentation : écrire son driver (sous-classe de
# BasePSU implémentant set_voltage/current/output + measure_*), puis l'enregistrer
# ici. Le reste de l'application (config, IHM, contrôleur) le prend en charge
# automatiquement (dropdown de modèle, validation du nombre de voies, simulation).
PSU_MODELS: Dict[str, type] = {
    "HMP4040": HMP4040,
    "HMP4030": HMP4030,
    "HMP2030": HMP2030,
    "HMP2020": HMP2020,
}


def available_models() -> List[str]:
    return sorted(PSU_MODELS)


def psu_channel_count(model: str) -> int:
    """Nombre de voies d'un modèle (0 si le modèle est inconnu)."""
    cls = PSU_MODELS.get(str(model).upper())
    return cls.n_channels if cls else 0


def psu_model_limits(model: str) -> Optional[Tuple[float, float, float]]:
    """Limites SOA (max_voltage, max_current, max_power) par voie, ou None si inconnu."""
    cls = PSU_MODELS.get(str(model).upper())
    if cls is None:
        return None
    return (cls.max_voltage, cls.max_current, cls.max_power)


def create_psu(model: str, resource: str = "", simulate: bool = True,
               name: str = "PSU", loads: Optional[Dict[int, float]] = None,
               visa_backend: str = "", use_cc_status: bool = False,
               query_delay_s: float = 0.0,
               log: Optional[Callable[[str], None]] = None) -> BasePSU:
    """Fabrique une alimentation (réelle ou simulée) à partir du nom de modèle."""
    cls = PSU_MODELS.get(str(model).upper())
    if cls is None:
        raise ValueError(
            f"Modèle d'alimentation inconnu : {model!r}. Connus : {available_models()}")
    if simulate:
        return MockPSU(name=name, n_channels=cls.n_channels, loads=loads)
    return cls(resource=resource, visa_backend=visa_backend,
               use_cc_status=use_cc_status, query_delay_s=query_delay_s, log=log)
