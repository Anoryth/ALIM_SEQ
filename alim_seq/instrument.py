"""Abstraction des appareils **par capacités** (cf. docs/DESIGN_INSTRUMENTS.md).

Un appareil n'est plus catégorisé (« une alim », « un DAQ ») : il **déclare les
capacités** qu'il expose. Le contrôleur ne parle qu'aux capacités et découvre « qui
sait faire quoi » par ``isinstance(instr, MesureTemperature)`` — pas de registre de
capacités, pas d'usine d'usines.

Ce module est **volontairement mince** (garde-fou anti sur-abstraction) :

- :class:`Instrument`        : cycle de vie commun (``connect``/``close``) + identité.
- Capacités (marqueurs fins) : :class:`SourceTension`, :class:`MesureVI`,
  :class:`MesureTemperature`, :class:`Actionneur`.
- :data:`INSTRUMENTS` / :func:`create_instrument` : registre unifié + fabrique,
  généralisation de ``PSU_MODELS`` / ``create_psu`` (dont ils restent une façade).

Il ne dépend PAS de ``psu``/``daq`` au niveau module (imports paresseux dans la
fabrique) : ``psu`` et ``daq`` importent leurs capacités d'ici, sans cycle.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional


# --------------------------------------------------------------- cycle de vie
class Instrument:
    """Appareil de la chaîne de mesure : un cycle de vie + une identité.

    Ce n'est PAS une catégorie fonctionnelle : ce que l'appareil *sait faire* est
    porté par les capacités qu'il mélange en plus (voir ci-dessous). ``name`` est le
    nom logique (clé de config et clé de verrou côté contrôleur) ; ``model`` est le
    modèle réel (« HMP4040 », « MockPSU »…).
    """

    name: str = ""
    model: str = ""

    def connect(self) -> None: ...
    def close(self) -> None: ...


# ------------------------------------------------------------------ capacités
# Marqueurs d'interface FINS : les méthodes ne sont que le contrat (corps ``...``),
# implémenté par les drivers concrets. On les garde comme classes simples (et non
# @abstractmethod) pour ne jamais empêcher l'instanciation d'un driver partiel et
# pour rester cohérent avec le style de stub déjà présent dans psu.py/daq.py.

class Capability:
    """Racine des capacités (sert de marqueur commun et de point de documentation)."""


class SourceTension(Capability):
    """Sait imposer une tension et une **limite de courant** par voie, et couper.

    La limite de courant est portée ici (et non dans une capacité distincte) : sur
    une alimentation de laboratoire, source de tension et limite de courant sont
    indissociables. Les voies sont numérotées à partir de 1.
    """

    def set_voltage(self, channel: int, voltage: float) -> None: ...
    def set_current(self, channel: int, current: float) -> None: ...
    def set_output(self, channel: int, on: bool) -> None: ...


class MesureVI(Capability):
    """Sait mesurer tension/courant (et l'état CV/CC + défauts) par voie."""

    def measure_voltage(self, channel: int) -> float: ...
    def measure_current(self, channel: int) -> float: ...
    def measure_status(self, channel: int) -> Dict[str, object]: ...


class MesureTemperature(Capability):
    """Sait fournir des températures (°C) par point nommé, et les tensions brutes.

    ``read_temperatures`` renvoie ``{point: °C}`` ; ``read_voltages`` les tensions
    brutes correspondantes (avant conversion), pour le filet de sécurité et le CSV.
    """

    def read_temperatures(self) -> Dict[str, float]: ...
    def read_voltages(self) -> Dict[str, float]: ...


class Actionneur(Capability):
    """Sait ouvrir/fermer une sortie logique par label (relais, GPIO, commutateur).

    Réservé à ROADMAP §4. Peut participer à la désalimentation ordonnée (ouvrir un
    relais pour isoler la carte fait partie de l'extinction sûre).
    """

    def set_state(self, label: str, on: bool) -> None: ...
    def get_state(self, label: str) -> Optional[bool]: ...


def capabilities_of(instr: object) -> List[str]:
    """Noms des capacités exposées par un instrument (pour l'introspection/IHM)."""
    return [cap.__name__ for cap in (SourceTension, MesureVI,
                                     MesureTemperature, Actionneur)
            if isinstance(instr, cap)]


# ------------------------------------------------------------ registre unifié
# Un driver est identifié par un nom (« HMP4040 », « NI-DAQ »…). Les **sources**
# réutilisent le registre PSU existant (PSU_MODELS) via une façade ; les autres
# familles s'ajoutent ici. La fabrique importe psu/daq PARESSEUSEMENT (aucun cycle).

# Alias de driver pour le module de température NI (insensible à la casse/tirets).
_NIDAQ_ALIASES = {"NI-DAQ", "NIDAQ", "NI", "NI-DAQMX", "NIDAQMX"}
# Drivers d'actionneurs (relais). Seul le mock est fourni pour l'instant ; un modèle
# matériel réel s'ajoutera ici (cf. relay.py, ROADMAP §4).
_RELAY_DRIVERS = {"MOCK-RELAY", "MOCKRELAY"}


def available_instruments() -> List[str]:
    """Liste des drivers connus (sources PSU + familles enregistrées ici)."""
    from .psu import available_models
    return sorted(set(available_models()) | {"NI-DAQ", "MOCK-RELAY"})


def driver_role(driver: str) -> Optional[str]:
    """Rôle (capacité principale) d'un driver, sans instancier de pilote :
    ``"source"`` (alim), ``"temperature"`` (module NI), ``"actuator"`` (relais), ou
    ``None`` si inconnu. Sert au contrôleur et à la validation pour router chaque
    instrument vers sa capacité."""
    from .psu import PSU_MODELS
    d = str(driver).upper().strip()
    if d in PSU_MODELS:
        return "source"
    if d in _NIDAQ_ALIASES:
        return "temperature"
    if d in _RELAY_DRIVERS:
        return "actuator"
    return None


def create_instrument(driver: str, simulate: bool = True, name: str = "",
                      **params) -> Instrument:
    """Fabrique un instrument (réel ou simulé) à partir du nom de driver.

    Généralise :func:`alim_seq.psu.create_psu`. En simulation, retourne le mock
    correspondant (parité). Les ``params`` dépendent de la famille :

    - **source de tension** (drivers de ``PSU_MODELS``) : ``resource``, ``loads``,
      ``visa_backend``, ``use_cc_status``, ``query_delay_s``, ``log`` — délégués tels
      quels à :func:`create_psu`.
    - **température** (``NI-DAQ``) : ``sensors`` (obligatoire) et, en simulation,
      ``power_provider`` + paramètres du modèle thermique (``ambient_c``…) ; en réel
      ``device``.
    """
    key = str(driver).upper().strip()

    # --- Sources de tension : on réutilise la fabrique PSU existante (façade). ----
    from .psu import PSU_MODELS
    if key in PSU_MODELS:
        from .psu import create_psu
        return create_psu(model=driver, simulate=simulate, name=name, **params)

    # --- Module de température NI (ou son mock thermique). -----------------------
    if key in _NIDAQ_ALIASES:
        sensors = params.get("sensors")
        if sensors is None:
            raise ValueError("Driver NI-DAQ : paramètre 'sensors' requis.")
        if simulate:
            from .daq import MockDAQ
            provider = params.get("power_provider") or (lambda: 0.0)
            thermal = {k: params[k] for k in
                       ("ambient_c", "thermal_gain_c_per_w", "thermal_tau_s", "noise_c")
                       if k in params}
            inst: Instrument = MockDAQ(sensors=sensors, power_provider=provider, **thermal)
        else:
            from .daq import NIDaq
            inst = NIDaq(device=params.get("device", "Dev1"), sensors=sensors)
        if name:
            inst.name = name
        return inst

    # --- Actionneur (relais). Le mock sert la simulation ET de relais « virtuel ». --
    if key in _RELAY_DRIVERS:
        from .relay import MockRelay
        outputs = params.get("outputs") or []
        # Un modèle matériel réel se brancherait ici en mode réel ; pour l'instant
        # seul le mock existe (piloté à la main tant qu'aucun modèle n'est câblé).
        return MockRelay(name=name or "RELAY", outputs=list(outputs))

    raise ValueError(
        f"Driver d'instrument inconnu : {driver!r}. "
        f"Connus : {available_instruments()}")


# Registre déclaratif (driver -> capacités exposées), pour l'introspection et la
# future validation de config §3. La FABRIQUE reste create_instrument ; ce dict ne
# construit rien, il décrit. Les sources sont ajoutées dynamiquement depuis PSU_MODELS.
INSTRUMENTS: Dict[str, tuple] = {
    "NI-DAQ": (MesureTemperature,),
    "MOCK-RELAY": (Actionneur,),
}
