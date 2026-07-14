"""Chargement et validation de la configuration JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .i18n import _


@dataclass
class ChannelConfig:
    label: str
    supply: str
    channel: int
    default_voltage: float = 0.0
    default_current: float = 0.1
    max_voltage: float = 32.0
    max_current: float = 10.0
    # polarity = +1 (normal) ou -1 (voie câblée en inverse pour une rail NÉGATIVE).
    # Le HMP4040 ne sort que du positif : on programme la magnitude et on travaille
    # côté logiciel en valeurs SIGNÉES (tension vue par le circuit).
    polarity: float = 1.0


@dataclass
class GroupConfig:
    """Groupe de voies mises en SÉRIE (la tension s'additionne, le courant est
    commun). Manipulé comme une voie logique via son label ``name``."""
    name: str
    members: List[str]
    mode: str = "series"
    split: str = "equal"             # "equal" (équilibrée) ou "fill" (remplissage)
    max_voltage: float = 0.0          # 0 => somme des max des membres
    max_current: float = 0.0          # 0 => min des max des membres


@dataclass
class TempSensorConfig:
    name: str
    channel: str
    converter: Dict[str, Any]
    warning: float
    critical: float
    # Voies qui doivent être ON pour que la mesure soit valide (sinon le capteur
    # est « en attente » : affiché mais exclu de la sécurité). Utile quand le
    # capteur n'est alimenté/conditionné qu'une fois une voie allumée.
    requires: List[str] = field(default_factory=list)
    # Plage de température PLAUSIBLE. Une mesure hors [valid_min, valid_max]
    # (ou NaN) signale un capteur en DÉFAUT (ex. thermocouple débranché).
    # None = pas de contrôle de cette borne.
    valid_min: Optional[float] = None
    valid_max: Optional[float] = None
    # Plage d'entrée analogique du module NI pour cette voie (V). Par défaut ±10 V
    # (pleine échelle usuelle) au lieu du ±5 V par défaut de nidaqmx.
    ai_min: float = -10.0
    ai_max: float = 10.0
    # Contrôle OPTIONNEL de la tension de référence du pont : ``ref_channel`` est
    # une voie (typiquement dans ``requires``) qui ALIMENTE le pont diviseur. Sa
    # tension MESURÉE est comparée à la tension de référence ATTENDUE ; si l'écart
    # dépasse ``ref_tol`` (relatif), le capteur est marqué en DÉFAUT (mesure non
    # fiable -> exclu de la sécurité). None = pas de contrôle.
    # La référence attendue est ``ref_voltage`` si renseignée (utile pour les
    # convertisseurs sans v_ref : table, poly, identity), sinon ``converter.v_ref``.
    ref_channel: Optional[str] = None
    ref_voltage: Optional[float] = None
    ref_tol: float = 0.05

    @property
    def expected_vref(self) -> Optional[float]:
        """Tension de référence attendue : ``ref_voltage`` sinon ``converter.v_ref``."""
        if self.ref_voltage is not None:
            return self.ref_voltage
        if isinstance(self.converter, dict):
            return self.converter.get("v_ref")
        return None


def _legacy_to_instruments(supplies: Dict[str, Any],
                           daq: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Traduit les sections héritées ``supplies``+``daq`` vers la section unifiée
    ``instruments`` (chaque entrée : un ``driver`` + ses paramètres). Une alim
    ``{"model": M, ...}`` devient ``{"driver": M, ...}`` ; le module NI devient un
    instrument de driver ``NI-DAQ`` nommé d'après ``daq.name`` (défaut « TEMP »)."""
    instruments: Dict[str, Dict[str, Any]] = {}
    for name, s in (supplies or {}).items():
        entry = {k: v for k, v in (s or {}).items() if k != "model"}
        instruments[name] = {"driver": str((s or {}).get("model", "HMP4040")), **entry}
    d = dict(daq or {})
    tname = str(d.pop("name", "") or "TEMP")
    while tname in instruments:
        tname += "_"
    instruments[tname] = {"driver": "NI-DAQ", **d}
    return instruments


def _relay_outputs(instruments: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Sorties de relais déclarées par la section ``instruments``, sous la forme
    ``{label: {"instrument": nom, "safe_state": bool, ...}}``.

    Le champ ``outputs`` d'un instrument actionneur peut être une **liste** de labels
    (état de repos OFF par défaut) ou un **dict** ``{label: {safe_state, line, ...}}``
    pour préciser l'état de sécurité ou le mappage physique (usage futur des drivers
    réels)."""
    from .instrument import driver_role
    out: Dict[str, Dict[str, Any]] = {}
    for iname, e in instruments.items():
        if driver_role(str((e or {}).get("driver", ""))) != "actuator":
            continue
        outs = (e or {}).get("outputs", [])
        if isinstance(outs, dict):
            for lbl, meta in outs.items():
                out[str(lbl)] = {"instrument": iname, **(meta or {})}
        else:
            for lbl in (outs or []):
                out[str(lbl)] = {"instrument": iname}
    return out


def _instruments_to_legacy(instruments: Dict[str, Any]):
    """Dérive les sections héritées ``supplies`` (sources) et ``daq`` (température)
    depuis la section unifiée ``instruments``. Miroir de :func:`_legacy_to_instruments`,
    pour la rétrocompatibilité des lecteurs qui consultent encore ``supplies``/``daq``.
    Les actionneurs (relais) n'ont pas de représentation legacy et sont ignorés ici."""
    from .instrument import driver_role
    supplies: Dict[str, Dict[str, Any]] = {}
    daq: Dict[str, Any] = {}
    for name, e in instruments.items():
        entry = {k: v for k, v in (e or {}).items() if k != "driver"}
        driver = str((e or {}).get("driver", "HMP4040"))
        role = driver_role(driver)
        if role == "source":
            supplies[name] = {"model": driver, **entry}
        elif role == "temperature":
            daq = {"name": name, **entry}
        # actionneur / inconnu : aucune section legacy (supplies/daq).
    return supplies, daq


@dataclass
class AppConfig:
    simulate: bool
    supplies: Dict[str, Dict[str, Any]]
    channels: Dict[str, ChannelConfig]
    temperatures: Dict[str, TempSensorConfig]
    daq: Dict[str, Any]
    safety: Dict[str, Any]
    groups: Dict[str, GroupConfig] = field(default_factory=dict)
    simulation: Dict[str, Any] = field(default_factory=dict)
    # Section unifiée **canonique** décrivant la chaîne d'appareils (chaque entrée :
    # un ``driver`` + ses paramètres). ``supplies``/``daq`` en sont le sucre
    # rétrocompatible : ``__post_init__`` maintient les deux vues cohérentes, la
    # section ``instruments`` faisant foi si elle est fournie.
    instruments: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Backend VISA : "" = VISA système (Keysight IO Libs / NI-VISA), "@py" = pyvisa-py.
    visa_backend: str = ""
    # Délai write->read (s) appliqué à chaque query SCPI. 0 convient en USB-TMC et
    # VXI-11 ; passe à ~0.02 si un HMP renvoie des "input protocol violation".
    visa_query_delay: float = 0.0
    # Lire le CV/CC depuis le registre d'état du HMP (STAT:QUES:INST:ISUM<n>:COND?,
    # vérifié sur le manuel HMP). Repli automatique sur l'inférence V/I si le
    # firmware ne répond pas. Met à False pour économiser une requête SCPI/voie.
    cc_status: bool = True
    # Chemin d'origine du fichier chargé (renseigné par load_config, résolu en
    # absolu). None pour une config construite en code. Exclu de toute validation
    # (sert au modèle « document » de l'IHM : savoir quel fichier éditer/écrire).
    source_path: Optional[Path] = None

    def __post_init__(self) -> None:
        """Maintient ``instruments`` (canonique) et ``supplies``/``daq`` (sucre)
        cohérents, quel que soit le format fourni à la construction :

        - ``instruments`` fourni -> (re)dérive ``supplies``/``daq`` compat ;
        - sinon (legacy ou config construite en code) -> dérive ``instruments``.
        """
        if self.instruments:
            # Fusionne les instruments explicites avec ceux dérivés de ``supplies``/
            # ``daq`` : une config peut ainsi combiner des sources décrites en
            # ``supplies`` ET des instruments ``instruments`` (ex. des relais) sans en
            # perdre. Les entrées explicites priment sur le legacy.
            from .instrument import driver_role
            base = (_legacy_to_instruments(self.supplies, self.daq)
                    if (self.supplies or self.daq) else {})
            if any(driver_role(str((e or {}).get("driver", ""))) == "temperature"
                   for e in self.instruments.values()):
                # Un module de température explicite prime : on retire le TEMP
                # synthétisé par la dérivation legacy (au plus un module de température).
                base = {n: e for n, e in base.items()
                        if driver_role(str((e or {}).get("driver", ""))) != "temperature"}
            merged = dict(base)
            merged.update(self.instruments)
            self.instruments = merged
        else:
            self.instruments = _legacy_to_instruments(self.supplies, self.daq)
        # ``instruments`` fait foi -> (re)dérive ``supplies``/``daq`` compat, toujours
        # normalisés (mêmes deux vues quel que soit le format d'entrée). On préserve un
        # ``daq`` legacy explicite si aucun instrument de température n'est déclaré.
        self.supplies, daq = _instruments_to_legacy(self.instruments)
        self.daq = daq or self.daq

    @property
    def channel_labels(self) -> List[str]:
        return list(self.channels.keys())

    @property
    def all_labels(self) -> List[str]:
        """Voies physiques + groupes série (tous les labels pilotables)."""
        return list(self.channels.keys()) + list(self.groups.keys())

    @property
    def relay_labels(self) -> List[str]:
        """Labels de sorties de relais (espace de noms distinct des voies)."""
        return list(_relay_outputs(self.instruments).keys())

    @property
    def relay_map(self) -> Dict[str, Dict[str, Any]]:
        """Routage des sorties de relais : ``{label: {"instrument", "safe_state", …}}``."""
        return _relay_outputs(self.instruments)


def config_to_dict(cfg: AppConfig) -> Dict[str, Any]:
    """Sérialise une :class:`AppConfig` vers un dict JSON-compatible.

    Miroir de :func:`load_config` : le dict produit se recharge à l'identique.
    Utilisé pour archiver la configuration active d'un essai lorsqu'elle a été
    construite en mémoire (``source_path`` absent) et ne peut donc être copiée
    telle quelle depuis un fichier d'origine.
    """
    def channel(c: ChannelConfig) -> Dict[str, Any]:
        return {
            "supply": c.supply,
            "channel": c.channel,
            "default_voltage": c.default_voltage,
            "default_current": c.default_current,
            "max_voltage": c.max_voltage,
            "max_current": c.max_current,
            "polarity": c.polarity,
        }

    def group(g: GroupConfig) -> Dict[str, Any]:
        return {
            "members": list(g.members),
            "mode": g.mode,
            "split": g.split,
            "max_voltage": g.max_voltage,
            "max_current": g.max_current,
        }

    def sensor(t: TempSensorConfig) -> Dict[str, Any]:
        return {
            "channel": t.channel,
            "converter": t.converter,
            "warning": t.warning,
            "critical": t.critical,
            "requires": list(t.requires),
            "valid_min": t.valid_min,
            "valid_max": t.valid_max,
            "ai_min": t.ai_min,
            "ai_max": t.ai_max,
            "ref_channel": t.ref_channel,
            "ref_voltage": t.ref_voltage,
            "ref_tol": t.ref_tol,
        }

    return {
        "simulate": cfg.simulate,
        # Section canonique unifiée + son sucre rétrocompatible (dérivé, cohérent) :
        # au rechargement, ``instruments`` fait foi (cf. AppConfig.__post_init__).
        "instruments": cfg.instruments,
        "supplies": cfg.supplies,
        "channels": {label: channel(c) for label, c in cfg.channels.items()},
        "groups": {name: group(g) for name, g in cfg.groups.items()},
        "temperatures": {name: sensor(t) for name, t in cfg.temperatures.items()},
        "daq": cfg.daq,
        "safety": cfg.safety,
        "simulation": cfg.simulation,
        "visa_backend": cfg.visa_backend,
        "visa_query_delay": cfg.visa_query_delay,
        "cc_status": cfg.cc_status,
    }


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    channels: Dict[str, ChannelConfig] = {}
    for label, c in raw.get("channels", {}).items():
        channels[label] = ChannelConfig(
            label=label,
            supply=c["supply"],
            channel=int(c["channel"]),
            default_voltage=float(c.get("default_voltage", 0.0)),
            default_current=float(c.get("default_current", 0.1)),
            max_voltage=float(c.get("max_voltage", 32.0)),
            max_current=float(c.get("max_current", 10.0)),
            polarity=(-1.0 if (c.get("negative") or float(c.get("polarity", 1.0)) < 0)
                      else 1.0),
        )

    temperatures: Dict[str, TempSensorConfig] = {}
    for name, t in raw.get("temperatures", {}).items():
        req = t.get("requires", [])
        if isinstance(req, str):
            req = [req]
        temperatures[name] = TempSensorConfig(
            name=name,
            channel=t["channel"],
            converter=t.get("converter", {"type": "identity"}),
            warning=float(t["warning"]),
            critical=float(t["critical"]),
            requires=list(req),
            valid_min=(None if t.get("valid_min") is None else float(t["valid_min"])),
            valid_max=(None if t.get("valid_max") is None else float(t["valid_max"])),
            ref_channel=(t.get("ref_channel") or None),
            ref_voltage=(None if t.get("ref_voltage") is None else float(t["ref_voltage"])),
            ref_tol=float(t.get("ref_tol", 0.05)),
            ai_min=float(t.get("ai_min", -10.0)),
            ai_max=float(t.get("ai_max", 10.0)),
        )

    groups: Dict[str, GroupConfig] = {}
    for name, g in raw.get("groups", {}).items():
        groups[name] = GroupConfig(
            name=name,
            members=list(g["members"]),
            mode=str(g.get("mode", "series")),
            split=str(g.get("split", "equal")),
            max_voltage=float(g.get("max_voltage", 0.0)),
            max_current=float(g.get("max_current", 0.0)),
        )

    cfg = AppConfig(
        simulate=bool(raw.get("simulate", True)),
        supplies=raw.get("supplies", {}),
        channels=channels,
        temperatures=temperatures,
        daq=raw.get("daq", {}),
        safety=raw.get("safety", {}),
        groups=groups,
        instruments=raw.get("instruments", {}),
        simulation=raw.get("simulation", {}),
        visa_backend=str(raw.get("visa_backend", "")),
        visa_query_delay=float(raw.get("visa_query_delay", 0.0)),
        cc_status=bool(raw.get("cc_status", True)),
        source_path=path.resolve(),
    )
    _validate(cfg)
    return cfg


def _validate(cfg: AppConfig) -> None:
    errors: List[str] = []
    from .psu import PSU_MODELS, psu_channel_count, psu_model_limits
    from .instrument import available_instruments, driver_role

    # Section unifiée : driver connu, et au plus un instrument de température (le
    # modèle actuel n'en gère qu'un ; les capteurs 'temperatures' lui sont rattachés).
    known = {d.upper() for d in available_instruments()}
    n_temp = 0
    for name, e in cfg.instruments.items():
        driver = str((e or {}).get("driver", "HMP4040"))
        if driver.upper() not in known:
            errors.append(
                _("Instrument {!r}: unknown driver {!r} (known: {}).").format(
                    name, driver, available_instruments())
            )
        elif driver_role(driver) == "temperature":
            n_temp += 1
    if n_temp > 1:
        errors.append(
            _("{} temperature instruments declared: only one is supported "
              "(the 'temperatures' sensors attach to the single NI module).").format(n_temp)
        )

    for name, s in cfg.supplies.items():
        model = str(s.get("model", "HMP4040"))
        if model.upper() not in PSU_MODELS:
            errors.append(
                _("Supply {!r}: unknown model {!r} (known: {}).").format(
                    name, model, sorted(PSU_MODELS))
            )

    seen_phys: Dict[tuple, str] = {}
    for label, ch in cfg.channels.items():
        if ch.supply not in cfg.supplies:
            errors.append(
                _("Channel {!r}: unknown supply {!r} (defined in 'supplies'?)").format(
                    label, ch.supply)
            )
        else:
            model = str(cfg.supplies[ch.supply].get("model", "HMP4040"))
            count = psu_channel_count(model)
            if count and (ch.channel < 1 or ch.channel > count):
                errors.append(
                    _("Channel {!r}: channel {} out of range 1-{} (model {} of {!r}).").format(
                        label, ch.channel, count, model, ch.supply)
                )
            limits = psu_model_limits(model)
            if limits:
                max_v, max_i, _imax = limits
                if ch.max_voltage > max_v:
                    errors.append(_("Channel {!r}: max_voltage {} V > {} V (limit {}).").format(
                        label, ch.max_voltage, max_v, model))
                if ch.max_current > max_i:
                    errors.append(_("Channel {!r}: max_current {} A > {} A (limit {}).").format(
                        label, ch.max_current, max_i, model))
        key = (ch.supply, ch.channel)
        if key in seen_phys:
            errors.append(
                _("Channel {!r}: channel {} of {!r} is already assigned to channel {!r} "
                  "(one physical channel = one channel only).").format(
                      label, ch.channel, ch.supply, seen_phys[key])
            )
        else:
            seen_phys[key] = label
    for name, t in cfg.temperatures.items():
        if t.critical <= t.warning:
            errors.append(
                _("Sensor {!r}: 'critical' threshold ({}) must be > 'warning' ({})").format(
                    name, t.critical, t.warning)
            )
        if t.ai_min >= t.ai_max:
            errors.append(
                _("Sensor {!r}: 'ai_min' ({}) must be < 'ai_max' ({}).").format(
                    name, t.ai_min, t.ai_max)
            )
        for req in t.requires:
            if req not in cfg.channels and req not in cfg.groups:
                errors.append(
                    _("Sensor {!r}: unknown required channel {!r} (in 'requires').").format(
                        name, req)
                )
        conv = t.converter if isinstance(t.converter, dict) else {}
        ctype = str(conv.get("type", "identity")).lower()
        # Le convertisseur doit être CONSTRUISIBLE dès la validation : une clé
        # manquante ou un paramètre aberrant (alpha=0, beta=0, table vide…) doit
        # être signalé ici, pas à la première mesure dans la boucle de sécurité.
        try:
            from .temperature import build_converter
            build_converter(conv)
        except Exception as exc:
            errors.append(_("Sensor {!r}: invalid converter — {}").format(name, exc))
        if ctype in ("ntc", "ptc", "rtd"):
            fm = conv.get("fault_margin")
            no_band = t.valid_min is None and t.valid_max is None
            if no_band and fm is not None and float(fm) == 0:
                errors.append(
                    _("Sensor {!r}: converter {!r} without disconnection guard -> set "
                      "'valid_min'/'valid_max' or leave a 'fault_margin' > 0 (0 disables "
                      "disconnected-sensor detection).").format(name, ctype)
                )
        if ctype in ("thermocouple", "tc"):
            # Un thermocouple n'a pas de détection de débranchement par pont
            # diviseur : la bande de plausibilité au niveau du capteur est le seul
            # filet logiciel (un TC ouvert lisant ~0 V reste indétectable — préférer
            # un module avec open-TC detect, cf. docstring ThermocoupleConverter).
            if t.valid_min is None or t.valid_max is None:
                errors.append(
                    _("Sensor {!r}: a thermocouple requires 'valid_min' AND 'valid_max' "
                      "(plausible temperature band) — the only software net against a "
                      "disconnected/floating-input TC.").format(name)
                )
        if t.ref_channel is not None:
            if t.ref_channel not in cfg.channels and t.ref_channel not in cfg.groups:
                errors.append(
                    _("Sensor {!r}: unknown 'ref_channel' {!r} (channel or group expected).").format(
                        name, t.ref_channel)
                )
            if t.expected_vref is None:
                errors.append(
                    _("Sensor {!r}: 'ref_channel' set but no expected reference voltage "
                      "('ref_voltage' at sensor level, or 'v_ref' in the converter).").format(name)
                )

    seen_members: Dict[str, str] = {}
    for name, g in cfg.groups.items():
        if name in cfg.channels:
            errors.append(_("Group {!r}: the name conflicts with a channel.").format(name))
        if g.mode != "series":
            errors.append(_("Group {!r}: only 'series' mode is supported for now.").format(name))
        if len(g.members) < 2:
            errors.append(_("Group {!r}: at least 2 member channels required.").format(name))
        if len(set(g.members)) != len(g.members):
            errors.append(_("Group {!r}: duplicate member channel.").format(name))
        for m in g.members:
            if m not in cfg.channels:
                errors.append(_("Group {!r}: unknown member channel {!r}.").format(name, m))
            elif m in seen_members:
                errors.append(
                    _("Group {!r}: channel {!r} already belongs to group {!r}.").format(
                        name, m, seen_members[m])
                )
            else:
                seen_members[m] = name
        if g.split not in ("equal", "fill"):
            errors.append(_("Group {!r}: 'split' must be 'equal' or 'fill'.").format(name))

    # Sorties de relais : labels uniques et sans collision avec voies/groupes (espaces
    # de noms distincts côté séquenceur, mais un nom partagé prêterait à confusion).
    taken = set(cfg.channels) | set(cfg.groups)
    seen_out: Dict[str, str] = {}
    for lbl, meta in _relay_outputs(cfg.instruments).items():
        if lbl in taken:
            errors.append(
                _("Relay output {!r} ({!r}): the name conflicts with a channel or group.").format(
                    lbl, meta['instrument'])
            )
        elif lbl in seen_out:
            errors.append(
                _("Relay output {!r}: already declared by {!r}.").format(lbl, seen_out[lbl])
            )
        else:
            seen_out[lbl] = meta["instrument"]

    if errors:
        raise ValueError(_("Invalid configuration:") + "\n  - " + "\n  - ".join(errors))
