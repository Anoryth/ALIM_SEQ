"""Séquenceur : analyse et exécution d'un fichier de séquence.

Format du fichier : une **action par ligne**. Les lignes vides et celles
commençant par ``#`` (ou ``//``) sont ignorées. Les mots-clés sont insensibles
à la casse ; les *labels* de voies et noms de capteurs respectent la casse de la
configuration.

Commandes disponibles
---------------------
    SET <voie> <tension_V> [courant_A]   Règle tension (et limite courant).
    VOLTAGE <voie> <tension_V>           Règle uniquement la tension.
    CURRENT <voie> <courant_A>           Règle uniquement la limite de courant.
    SETV <voie> = <expression>           Règle la tension à partir d'une formule
                                         (ex: SETV VG2 = (VD/2)+VG1). Un nom de
                                         voie = sa consigne de tension ; fonctions
                                         V(x), Vmeas(x), Iset(x), I(x) disponibles.
    SETI <voie> = <expression>           Idem pour la limite de courant.
    ON <voie>                            Allume la voie.
    OFF <voie>                           Éteint la voie.
    WAIT <secondes>                      Pause (interruptible).
    RAMP <voie> <v_fin> <duree_s>                   Rampe DEPUIS la valeur
                                         actuelle de la voie jusqu'à <v_fin>.
    RAMP <voie> <v_debut> <v_fin> <duree_s> [pas]   Rampe avec départ explicite.
                                         [pas] = NOMBRE de pas (entier >= 2), pas
                                         une taille de pas.
    SERVO_LIN <voie_reglee> <voie_mesuree> <courant_cible_A> [clé=valeur ...]
                                         Asservit la tension de <voie_reglee>
                                         jusqu'au courant cible sur <voie_mesuree>,
                                         à PAS FIXE (|step| par itération).
                                         Clés: step, min, max, tol, timeout, settle,
                                         invert. ('SERVO' = alias de SERVO_LIN.)
    SERVO_ADAPT <voie_reglee> <voie_mesuree> <courant_cible_A> [clé=valeur ...]
                                         Idem mais à PAS ADAPTATIF (sécante/Newton :
                                         pente dI/dV mesurée -> grand loin, fin près).
                                         'step' devient un PLAFOND. Clé en plus:
                                         damping (défaut 0.7).
    WAIT_CURRENT <voie> <op> <valeur> [timeout=<s>]   Attend une condition courant.
    WAIT_TEMP <capteur> <op> <valeur> [timeout=<s>]   Attend une condition temp.
                                         op ∈ { < <= > >= == != }
    LOG <message...>                     Écrit un message dans le journal.
    ALL_OFF                              Éteint toutes les voies.
    RELAY <sortie> ON|OFF                Ferme (ON) / ouvre (OFF) une sortie de relais.
    REPEAT <n>  …  END                   Répète n fois le bloc (imbrication OK).

Exemple
-------
    # Mise sous tension
    SET VCC 3.3 1.0
    ON VCC
    WAIT 1.0
    SERVO_ADAPT VBIAS VCC 0.5 step=0.5 max=5.0 tol=0.005
    WAIT 2
    ALL_OFF
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional, Set

from .expressions import ExprError, references

if TYPE_CHECKING:  # évite un cycle d'import (controller importe sequencer)
    from .controller import Controller

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: abs(a - b) < 1e-9,
    "!=": lambda a, b: abs(a - b) >= 1e-9,
}


class SequenceError(Exception):
    """Erreur de syntaxe/validation dans le fichier de séquence."""


@dataclass
class Action:
    """Une action de séquence analysée.

    ``lineno`` = ligne source (conservée après expansion des boucles, pour le
    surlignage de l'éditeur) ; ``cmd`` = mot-clé en MAJUSCULES ; ``args`` = les
    arguments bruts (str, convertis à l'exécution) ; ``raw`` = la ligne d'origine
    (affichée dans le journal)."""
    lineno: int
    cmd: str
    args: List[str]
    raw: str


# --------------------------------------------------------------------- parser
def parse_sequence(
    text: str,
    valid_labels: Set[str],
    valid_sensors: Set[str],
    valid_relays: Set[str] = frozenset(),
) -> List[Action]:
    """Analyse le texte d'une séquence et valide les références (voies/capteurs/relais)."""
    actions: List[Action] = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        # On retire un éventuel commentaire en fin de ligne.
        for marker in ("#", "//"):
            if marker in stripped and not stripped.upper().startswith("LOG"):
                stripped = stripped.split(marker, 1)[0].strip()
        parts = stripped.split()
        cmd = parts[0].upper()
        args = parts[1:]
        action = Action(lineno=i, cmd=cmd, args=args, raw=line.strip())
        _validate_action(action, valid_labels, valid_sensors, valid_relays)
        actions.append(action)
    return _expand_loops(actions)


def _expand_loops(actions: List[Action]) -> List[Action]:
    """Déroule les blocs ``REPEAT n … END`` (imbrications gérées) en une liste plate.

    Les actions conservent leur ``lineno`` source (le surlignage de l'éditeur reste
    correct). Garde-fou contre une expansion démesurée.
    """
    stack: List[List[Action]] = [[]]
    counts: List[int] = []
    for a in actions:
        if a.cmd == "REPEAT":
            stack.append([])
            counts.append(int(a.args[0]))
        elif a.cmd == "END":
            if len(stack) == 1:
                raise SequenceError(f"Ligne {a.lineno}: 'END' sans 'REPEAT' correspondant.")
            block, n = stack.pop(), counts.pop()
            stack[-1].extend(block * n)
            if len(stack[-1]) > 200000:
                raise SequenceError("Séquence trop longue après expansion des boucles "
                                    "(REPEAT trop grand).")
        else:
            stack[-1].append(a)
    if len(stack) != 1:
        raise SequenceError("'REPEAT' sans 'END' correspondant.")
    return stack[0]


def estimate_duration(actions: List[Action]) -> float:
    """Durée minimale estimée (s) : somme des WAIT/DELAY et des durées de RAMP.

    Les SERVO / WAIT_CURRENT / WAIT_TEMP (durée non bornée) ne sont pas comptés."""
    total = 0.0
    for a in actions:
        try:
            if a.cmd in ("WAIT", "DELAY"):
                total += float(a.args[0])
            elif a.cmd == "RAMP":
                total += float(a.args[3] if len(a.args) >= 4 else a.args[2])
        except (IndexError, ValueError):
            pass
    return total


def _need(action: Action, n: int) -> None:
    if len(action.args) < n:
        raise SequenceError(
            f"Ligne {action.lineno}: '{action.cmd}' attend au moins {n} argument(s) "
            f"-> {action.raw!r}"
        )


def _check_label(action: Action, label: str, valid_labels: Set[str]) -> None:
    if label not in valid_labels:
        raise SequenceError(
            f"Ligne {action.lineno}: voie inconnue {label!r}. "
            f"Voies valides : {sorted(valid_labels)}"
        )


# Clés autorisées pour les arguments clé=valeur des servos et attentes.
_SERVO_KEYS: Set[str] = {"step", "min", "max", "tol", "timeout", "settle", "invert"}
_SERVO_ADAPT_KEYS: Set[str] = _SERVO_KEYS | {"damping"}
_WAIT_KEYS: Set[str] = {"timeout"}


def _ramp_steps(action: Action, raw: str) -> int:
    """Valide l'argument optionnel ``[pas]`` de RAMP : c'est un NOMBRE DE PAS,
    donc un entier >= 2 (``0.1`` est refusé : ce n'est pas une taille de pas)."""
    try:
        n = int(raw)
    except ValueError:
        raise SequenceError(
            f"Ligne {action.lineno}: RAMP [pas] est le nombre de pas (entier >= 2), "
            f"reçu {raw!r} -> {action.raw!r}")
    if n < 2:
        raise SequenceError(
            f"Ligne {action.lineno}: RAMP [pas] (nombre de pas) doit être >= 2 "
            f"(reçu {n}).")
    return n


def _num(action: Action, idx: int, name: str, *, non_neg: bool = False,
         positive: bool = False) -> float:
    """Convertit ``args[idx]`` en float, sinon lève une SequenceError explicite."""
    try:
        v = float(action.args[idx])
    except (IndexError, ValueError):
        raise SequenceError(
            f"Ligne {action.lineno}: '{action.cmd}' attend un nombre pour {name} "
            f"-> {action.raw!r}")
    if positive and not v > 0:
        raise SequenceError(
            f"Ligne {action.lineno}: {name} doit être > 0 (reçu {v}).")
    if non_neg and v < 0:
        raise SequenceError(
            f"Ligne {action.lineno}: {name} doit être >= 0 (reçu {v}).")
    return v


def _check_kwargs(action: Action, start: int, allowed: Set[str]) -> None:
    """Valide les arguments ``clé=valeur`` : forme correcte, clé connue, valeur
    numérique. Toute clé hors liste blanche est rejetée à l'analyse."""
    for a in action.args[start:]:
        if "=" not in a:
            raise SequenceError(
                f"Ligne {action.lineno}: '{action.cmd}' attend des paires clé=valeur, "
                f"reçu {a!r} -> {action.raw!r}")
        k, v = a.split("=", 1)
        key = k.strip().lower()
        if key not in allowed:
            raise SequenceError(
                f"Ligne {action.lineno}: clé inconnue {key!r} pour '{action.cmd}'. "
                f"Clés valides : {sorted(allowed)}")
        try:
            float(v)
        except ValueError:
            raise SequenceError(
                f"Ligne {action.lineno}: valeur non numérique pour {key!r} : {v!r}")


def _validate_action(action: Action, valid_labels: Set[str], valid_sensors: Set[str],
                     valid_relays: Set[str] = frozenset()) -> None:
    c = action.cmd
    if c == "SET":
        _need(action, 2)
        _check_label(action, action.args[0], valid_labels)
        _num(action, 1, "la tension")
        if len(action.args) >= 3:
            _num(action, 2, "le courant", non_neg=True)
    elif c in ("VOLTAGE", "VOLT"):
        _need(action, 2)
        _check_label(action, action.args[0], valid_labels)
        _num(action, 1, "la tension")
    elif c in ("CURRENT", "CURR"):
        _need(action, 2)
        _check_label(action, action.args[0], valid_labels)
        _num(action, 1, "le courant", non_neg=True)
    elif c in ("ON", "OFF"):
        _need(action, 1)
        _check_label(action, action.args[0], valid_labels)
    elif c in ("WAIT", "DELAY"):
        _need(action, 1)
        _num(action, 0, "la durée", non_neg=True)
    elif c == "RAMP":
        # 2 formes : "RAMP <voie> <v_fin> <duree>" (départ = valeur actuelle)
        #         ou "RAMP <voie> <v_debut> <v_fin> <duree> [pas]".
        _need(action, 3)
        _check_label(action, action.args[0], valid_labels)
        if len(action.args) >= 4:
            _num(action, 1, "la tension de départ")
            _num(action, 2, "la tension finale")
            _num(action, 3, "la durée", positive=True)
            if len(action.args) >= 5:
                _ramp_steps(action, action.args[4])
        else:
            _num(action, 1, "la tension finale")
            _num(action, 2, "la durée", positive=True)
    elif c in ("SERVO", "SERVO_LIN", "SERVO_ADAPT"):
        _need(action, 3)
        _check_label(action, action.args[0], valid_labels)
        _check_label(action, action.args[1], valid_labels)
        _num(action, 2, "le courant cible")
        allowed = _SERVO_ADAPT_KEYS if c == "SERVO_ADAPT" else _SERVO_KEYS
        _check_kwargs(action, 3, allowed)
    elif c == "WAIT_CURRENT":
        _need(action, 3)
        _check_label(action, action.args[0], valid_labels)
        if action.args[1] not in _OPS:
            raise SequenceError(f"Ligne {action.lineno}: opérateur invalide {action.args[1]!r}")
        _num(action, 2, "la valeur")
        _check_kwargs(action, 3, _WAIT_KEYS)
    elif c == "WAIT_TEMP":
        _need(action, 3)
        if action.args[0] not in valid_sensors:
            raise SequenceError(
                f"Ligne {action.lineno}: capteur inconnu {action.args[0]!r}. "
                f"Capteurs : {sorted(valid_sensors)}"
            )
        if action.args[1] not in _OPS:
            raise SequenceError(f"Ligne {action.lineno}: opérateur invalide {action.args[1]!r}")
        _num(action, 2, "la valeur")
        _check_kwargs(action, 3, _WAIT_KEYS)
    elif c in ("SETV", "SETI"):
        _need(action, 2)
        _check_label(action, action.args[0], valid_labels)
        expr = _expr_from_args(action.args[1:])
        try:
            refs = references(expr)
        except ExprError as exc:
            raise SequenceError(f"Ligne {action.lineno}: {exc}") from exc
        for r in refs:
            if r not in valid_labels:
                raise SequenceError(
                    f"Ligne {action.lineno}: voie inconnue {r!r} dans l'expression. "
                    f"Voies valides : {sorted(valid_labels)}"
                )
    elif c == "REPEAT":
        _need(action, 1)
        try:
            n = int(action.args[0])
        except ValueError:
            raise SequenceError(
                f"Ligne {action.lineno}: 'REPEAT' attend un entier -> {action.raw!r}")
        if n < 1:
            raise SequenceError(f"Ligne {action.lineno}: 'REPEAT' doit être >= 1.")
    elif c == "RELAY":
        _need(action, 2)
        if action.args[0] not in valid_relays:
            raise SequenceError(
                f"Ligne {action.lineno}: sortie de relais inconnue {action.args[0]!r}. "
                f"Sorties : {sorted(valid_relays)}"
            )
        if action.args[1].upper() not in ("ON", "OFF"):
            raise SequenceError(
                f"Ligne {action.lineno}: 'RELAY' attend ON ou OFF -> {action.raw!r}")
    elif c == "END":
        pass
    elif c in ("LOG", "ALL_OFF", "SHUTDOWN"):
        pass
    else:
        raise SequenceError(f"Ligne {action.lineno}: commande inconnue {c!r} -> {action.raw!r}")


def _expr_from_args(args: List[str]) -> str:
    """Reconstruit l'expression à partir des arguments (un '=' de tête optionnel
    est ignoré : ``SETV VG2 = (VD/2)+VG1``)."""
    expr = " ".join(args).strip()
    if expr.startswith("="):
        expr = expr[1:].strip()
    return expr


def _kwargs(args: List[str]) -> dict:
    """Extrait les paires clé=valeur d'une liste d'arguments (valeurs numériques).

    Défensif : une valeur non numérique lève une ``SequenceError`` (les clés sont
    déjà validées à l'analyse par :func:`_check_kwargs`)."""
    out = {}
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            try:
                out[k.strip().lower()] = float(v)
            except ValueError:
                raise SequenceError(f"Valeur non numérique pour {k.strip()!r} : {v!r}")
    return out


# --------------------------------------------------------------------- runner
class SequenceRunner:
    """Exécute une liste d'actions dans un thread dédié, de façon interruptible."""

    def __init__(self, controller: "Controller"):
        self.ctrl = controller
        self._thread: Optional[threading.Thread] = None
        # Deux intentions d'arrêt distinctes :
        #  - _user_stop : arrêt demandé par l'opérateur (bouton Stop). REFUSÉ pendant
        #    une désalimentation de sécurité (sinon des voies resteraient alimentées).
        #  - _stop      : arrêt INCONDITIONNEL (force_stop), usage interne (fermeture
        #    de l'appli, coupure dure), qui interrompt même une désalim de sécurité.
        self._stop = threading.Event()
        self._user_stop = threading.Event()
        self._pause = threading.Event()  # set = exécution en pause
        # Sérialise start() : ferme la fenêtre TOCTOU entre le test de _running et
        # le démarrage du thread (deux start() concurrents -> une seule séquence).
        self._start_lock = threading.Lock()
        self._running = False
        # safety_mode : séquence de désalimentation lancée par la sécurité. Elle
        # doit s'exécuter MÊME quand le verrou de sécurité est armé (tripped) ;
        # elle n'écoute donc que son propre _stop, pas abort_event/tripped.
        self._safety_mode = False
        # Progression (index de l'action courante, total) — attributs simples lus
        # par l'IHM via son timer, même modèle que le reste.
        self.progress = (0, 0)
        # Mode pas-à-pas : l'exécution attend step_event avant CHAQUE action (hors
        # désalimentation de sécurité, qui ne doit jamais être bloquée).
        self.step_mode = False
        self.step_event = threading.Event()
        self.on_line: Optional[Callable[[int, str], None]] = None
        self.on_finish: Optional[Callable[[bool, str], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def set_step_mode(self, on: bool) -> None:
        """Active/désactive le pas-à-pas. En le désactivant, on libère une éventuelle
        attente en cours (l'exécution reprend en continu)."""
        self.step_mode = bool(on)
        if not on:
            self.step_event.set()

    def step_once(self) -> None:
        """Autorise l'exécution de la prochaine action en attente (pas-à-pas)."""
        self.step_event.set()

    def start(self, actions: List[Action], safety_mode: bool = False) -> None:
        """Démarre l'exécution des ``actions`` dans un thread dédié.

        ``safety_mode=True`` marque une désalimentation de sécurité : elle s'exécute
        même verrou de sécurité armé, ignore l'arrêt utilisateur et la pause, et ne
        réinitialise pas ``abort_event``. Lève ``RuntimeError`` si une séquence tourne
        déjà."""
        # Verrou : le test-puis-armement de _running doit être atomique.
        with self._start_lock:
            if self._running:
                raise RuntimeError("Une séquence est déjà en cours.")
            self._running = True
        self._stop.clear()
        self._user_stop.clear()
        self._pause.clear()
        self.step_event.clear()
        self.progress = (0, len(actions))
        self._safety_mode = safety_mode
        if not safety_mode:
            self.ctrl.abort_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(actions,), name="sequence", daemon=True
        )
        self._thread.start()

    def stop(self) -> bool:
        """Arrêt demandé par l'OPÉRATEUR (interrompt WAIT/SERVO). REFUSÉ pendant une
        désalimentation de sécurité. Retourne True si pris en compte, False si refusé."""
        if self._safety_mode:
            return False
        self._user_stop.set()
        self.ctrl.abort_event.set()
        return True

    def force_stop(self) -> None:
        """Arrêt INCONDITIONNEL (usage interne : fermeture de l'appli, coupure dure).
        Interrompt même une désalimentation de sécurité."""
        self._stop.set()
        self.ctrl.abort_event.set()

    def pause(self) -> None:
        if not self._safety_mode:   # une désalimentation de sécurité ne se met pas en pause
            self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    @property
    def is_paused(self) -> bool:
        return self._pause.is_set()

    def _paused(self) -> bool:
        return self._pause.is_set() and not self._safety_mode

    def _aborted(self) -> bool:
        """Faut-il interrompre l'exécution ? En mode sécurité, SEUL ``force_stop``
        (``_stop``) compte : ni l'arrêt utilisateur, ni le verrou armé, ni
        ``abort_event`` ne doivent stopper une désalimentation en cours. Sinon,
        n'importe lequel de ces signaux avorte la séquence utilisateur."""
        if self._safety_mode:
            # Une désalim de sécurité n'écoute QUE force_stop (_stop), jamais l'arrêt
            # utilisateur ni le verrou : elle doit aller au bout de l'extinction.
            return self._stop.is_set()
        return (self._stop.is_set() or self._user_stop.is_set()
                or self.ctrl.abort_event.is_set() or self.ctrl.tripped)

    def _sleep(self, seconds: float) -> bool:
        """Pause interruptible (et suspendable). Retourne False si interrompue.
        Le décompte est gelé tant que la séquence est en pause."""
        remaining = seconds
        last = time.monotonic()
        while remaining > 0:
            if self._aborted():
                return False
            now = time.monotonic()
            if not self._paused():
                remaining -= now - last
            last = now
            time.sleep(0.05)
        return not self._aborted()

    def _run(self, actions: List[Action]) -> None:
        """Corps du thread d'exécution : parcourt les actions une à une.

        Gère à chaque tour la pause, l'avortement et le pas-à-pas, surligne la ligne
        courante (``on_line``), journalise, puis délègue à :meth:`_execute`. Sort au
        premier échec/interruption. Le bloc ``finally`` remet ``_running`` à False,
        ajuste l'issue si la sécurité a tranché, et notifie ``on_finish(ok, message)``."""
        ok = True
        message = "Séquence terminée."
        total = len(actions)
        try:
            for idx, action in enumerate(actions):
                self.progress = (idx, total)
                while self._paused() and not self._aborted():
                    time.sleep(0.05)   # suspendue entre deux actions
                if self._aborted():
                    ok = False
                    message = "Séquence interrompue."
                    break
                # On surligne la PROCHAINE action AVANT l'attente pas-à-pas.
                if self.on_line:
                    self.on_line(action.lineno, action.raw)
                # Pas-à-pas : on attend l'autorisation (jamais en désalim de sécurité).
                if self.step_mode and not self._safety_mode:
                    self.step_event.clear()
                    while not self.step_event.is_set():
                        if self._aborted():
                            break
                        time.sleep(0.05)
                    self.step_event.clear()
                    if self._aborted():
                        ok = False
                        message = "Séquence interrompue."
                        break
                self.ctrl.log(f"> L{action.lineno}: {action.raw}")
                if not self._execute(action):
                    ok = False
                    message = f"Échec/interruption ligne {action.lineno}."
                    break
            else:
                self.progress = (total, total)
        except Exception as exc:
            ok = False
            message = f"Erreur ligne : {exc}"
            self.ctrl.log(f"Erreur séquence : {exc}")
        finally:
            self._running = False
            if self.ctrl.tripped and not self._safety_mode:
                ok = False
                message = "Séquence avortée par la sécurité."
            self.ctrl.log(message)
            if self.on_finish:
                self.on_finish(ok, message)

    def _execute(self, action: Action) -> bool:
        """Exécute UNE action en la routant vers la primitive du contrôleur.

        Retourne True si l'action a réussi et qu'on peut enchaîner, False en cas
        d'échec ou d'interruption (WAIT/RAMP/SERVO/WAIT_* retournent False s'ils sont
        avortés). Les valeurs sont déjà validées à l'analyse : on peut convertir les
        arguments sans re-vérifier."""
        c = action.cmd
        a = action.args
        if c == "SET":
            self.ctrl.set_voltage(a[0], float(a[1]))
            if len(a) >= 3:
                self.ctrl.set_current(a[0], float(a[2]))
            return True
        if c in ("VOLTAGE", "VOLT"):
            self.ctrl.set_voltage(a[0], float(a[1]))
            return True
        if c in ("CURRENT", "CURR"):
            self.ctrl.set_current(a[0], float(a[1]))
            return True
        if c == "SETV":
            expr = _expr_from_args(a[1:])
            value = self.ctrl.eval_expression(expr)
            self.ctrl.set_voltage(a[0], value)
            self.ctrl.log(f"SETV {a[0]} = {expr} = {value:.4f} V")
            return True
        if c == "SETI":
            expr = _expr_from_args(a[1:])
            value = self.ctrl.eval_expression(expr)
            self.ctrl.set_current(a[0], value)
            self.ctrl.log(f"SETI {a[0]} = {expr} = {value:.4f} A")
            return True
        if c == "ON":
            self.ctrl.set_output(a[0], True)
            return True
        if c == "OFF":
            self.ctrl.set_output(a[0], False)
            return True
        if c in ("WAIT", "DELAY"):
            return self._sleep(float(a[0]))
        if c == "RAMP":
            return self._ramp(a)
        if c in ("SERVO", "SERVO_LIN"):  # 'SERVO' = alias rétrocompatible
            kw = _kwargs(a[3:])
            return self.ctrl.servo(
                adjust_label=a[0],
                measure_label=a[1],
                target_current=float(a[2]),
                step=kw.get("step", 0.02),
                v_min=kw.get("min"),
                v_max=kw.get("max"),
                tol=kw.get("tol", 0.01),
                timeout=kw.get("timeout", 30.0),
                settle=kw.get("settle", 0.3),
                invert=bool(kw.get("invert", 0.0)),
                should_abort=self._aborted,
            )
        if c == "SERVO_ADAPT":
            kw = _kwargs(a[3:])
            return self.ctrl.servo_adaptive(
                adjust_label=a[0],
                measure_label=a[1],
                target_current=float(a[2]),
                step=kw.get("step", 0.5),
                v_min=kw.get("min"),
                v_max=kw.get("max"),
                tol=kw.get("tol", 0.01),
                timeout=kw.get("timeout", 30.0),
                settle=kw.get("settle", 0.3),
                invert=bool(kw.get("invert", 0.0)),
                damping=kw.get("damping", 0.7),
                should_abort=self._aborted,
            )
        if c == "WAIT_CURRENT":
            return self._wait_current(a)
        if c == "WAIT_TEMP":
            return self._wait_temp(a)
        if c == "LOG":
            self.ctrl.log("SEQ: " + " ".join(a))
            return True
        if c in ("ALL_OFF", "SHUTDOWN"):
            for label in self.ctrl.cfg.channels:
                self.ctrl.set_output(label, False)
            return True
        if c == "RELAY":
            self.ctrl.set_relay(a[0], a[1].upper() == "ON")
            return True
        return False

    def _ramp(self, a: List[str]) -> bool:
        """Exécute une rampe de tension linéaire par paliers (interruptible).

        Deux formes (cf. grammaire RAMP) : sans tension de départ, on part de la
        consigne ACTUELLE de la voie ; sinon départ explicite avec un nombre de pas
        optionnel. Durée <= 0 -> application directe de la valeur finale. Retourne
        False si la rampe est avortée en cours."""
        label = a[0]
        if len(a) == 3:
            # RAMP <voie> <v_fin> <duree> : départ = consigne ACTUELLE de la voie.
            v0 = self.ctrl.get_setpoint(label).set_voltage
            v1, duration = float(a[1]), float(a[2])
            steps = max(2, int(duration / 0.1))
        else:
            # RAMP <voie> <v_debut> <v_fin> <duree> [pas] : [pas] = NOMBRE de pas.
            v0, v1, duration = float(a[1]), float(a[2]), float(a[3])
            steps = int(a[4]) if len(a) >= 5 else max(2, int(duration / 0.1))
        steps = max(1, steps)
        if duration <= 0:
            # Durée nulle/négative : on applique directement la valeur finale.
            self.ctrl.set_voltage(label, v1)
            return True
        dt = duration / steps
        for k in range(1, steps + 1):
            if self._aborted():
                return False
            v = v0 + (v1 - v0) * k / steps
            self.ctrl.set_voltage(label, v)
            if not self._sleep(dt):
                return False
        return True

    def _wait_current(self, a: List[str]) -> bool:
        """Attend qu'une voie satisfasse ``courant <op> valeur`` (défaut timeout 30 s).
        Retourne True si la condition est remplie, False sur timeout ou avortement."""
        label, op, value = a[0], a[1], float(a[2])
        kw = _kwargs(a[3:])
        timeout = kw.get("timeout", 30.0)
        cmp = _OPS[op]
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self._aborted():
                return False
            i = self.ctrl.snapshot().channels[label].meas_current
            if cmp(i, value):
                return True
            time.sleep(0.1)
        self.ctrl.log(f"WAIT_CURRENT timeout ({label} {op} {value}).")
        return False

    def _wait_temp(self, a: List[str]) -> bool:
        """Attend qu'un capteur satisfasse ``température <op> valeur`` (défaut timeout
        60 s). Une mesure ``NaN`` (capteur en défaut) ne valide jamais la condition.
        Retourne True si remplie, False sur timeout ou avortement."""
        sensor, op, value = a[0], a[1], float(a[2])
        kw = _kwargs(a[3:])
        timeout = kw.get("timeout", 60.0)
        cmp = _OPS[op]
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self._aborted():
                return False
            t = self.ctrl.snapshot().temperatures.get(sensor, float("nan"))
            if t == t and cmp(t, value):  # t==t écarte NaN
                return True
            time.sleep(0.2)
        self.ctrl.log(f"WAIT_TEMP timeout ({sensor} {op} {value}).")
        return False


# ------------------------------------------------------- séquence d'arrêt
def build_shutdown_actions(labels: List[str], delay: float = 0.5) -> List[Action]:
    """Construit une séquence de désalimentation ordonnée.

    Les voies sont éteintes dans l'ordre **inverse** de ``labels`` (donc inverse
    de l'ordre d'allumage défini dans la configuration), avec une temporisation
    ``delay`` entre chaque extinction. Utilisée par le bouton *Séquentiel
    d'arrêt* ET par la sécurité thermique (extinction douce plutôt que coupure
    brutale, pour ne pas abîmer la carte).
    """
    actions: List[Action] = []
    ln = 0
    for label in list(labels)[::-1]:
        ln += 1
        actions.append(Action(lineno=ln, cmd="OFF", args=[label], raw=f"OFF {label}"))
        if delay > 0:
            ln += 1
            actions.append(
                Action(lineno=ln, cmd="WAIT", args=[str(delay)], raw=f"WAIT {delay}")
            )
    return actions


def load_shutdown_actions(
    path, labels: List[str], valid_labels: Set[str], valid_sensors: Set[str],
    delay: float = 0.5, valid_relays: Set[str] = frozenset(),
) -> List[Action]:
    """Charge la séquence d'arrêt depuis un fichier si fourni/existant, sinon
    construit une extinction ordonnée par défaut."""
    from pathlib import Path

    if path:
        p = Path(path)
        if p.exists():
            return parse_sequence(p.read_text(encoding="utf-8"), valid_labels,
                                  valid_sensors, valid_relays)
    return build_shutdown_actions(labels, delay)
