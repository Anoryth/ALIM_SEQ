"""Convertisseurs tension -> température.

Le module d'acquisition NI mesure des **tensions**. Selon le capteur utilisé,
la relation tension -> température n'est pas linéaire. Ce module fournit
plusieurs convertisseurs interchangeables, choisis dans la configuration via
le champ ``converter.type`` :

    - "table"    : interpolation linéaire par morceaux d'une courbe d'étalonnage
    - "poly"     : polynôme  T = c0 + c1*v + c2*v^2 + ...
    - "ntc"      : thermistance NTC (pont diviseur) via l'équation Beta
    - "ptc"/"rtd": thermistance PTC linéaire / RTD (PT100, PT1000)
    - "thermocouple" : types K/J (NIST ITS-90 + compensation soudure froide)
    - "identity" : la valeur lue est déjà une température (°C)

Pour ajouter un capteur, écrire une sous-classe de :class:`TemperatureConverter`
et l'enregistrer dans :data:`_CONVERTERS`.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple


def _rail_fault(voltage: float, v_ref: float, fault_margin: float) -> bool:
    """Vrai si la tension d'un pont diviseur colle à un rail (0 ou v_ref) à
    ``fault_margin`` (fraction de v_ref) près -> capteur débranché ou en
    court-circuit. ``fault_margin <= 0`` désactive la détection."""
    if fault_margin <= 0 or v_ref <= 0:
        return False
    m = fault_margin * v_ref
    return voltage <= m or voltage >= v_ref - m


class TemperatureConverter:
    """Interface : transforme une tension (V) en température (°C)."""

    def to_celsius(self, voltage: float) -> float:  # pragma: no cover - interface
        raise NotImplementedError


class IdentityConverter(TemperatureConverter):
    """La valeur lue est déjà une température (°C)."""

    def to_celsius(self, voltage: float) -> float:
        return voltage


class PolynomialConverter(TemperatureConverter):
    """T = c0 + c1*v + c2*v^2 + ...  (coefficients dans l'ordre croissant)."""

    def __init__(self, coeffs: List[float]):
        if not coeffs:
            raise ValueError("PolynomialConverter: 'coeffs' ne peut pas être vide")
        self.coeffs = [float(c) for c in coeffs]

    def to_celsius(self, voltage: float) -> float:
        result = 0.0
        power = 1.0
        for c in self.coeffs:
            result += c * power
            power *= voltage
        return result


class TableConverter(TemperatureConverter):
    """Interpolation linéaire par morceaux d'une table d'étalonnage.

    ``points`` est une liste de couples [tension_V, temperature_C]. La table est
    triée par tension croissante ; en dehors des bornes, la valeur est
    extrapolée à partir du segment de bord le plus proche.
    """

    def __init__(self, points: List[Tuple[float, float]]):
        if len(points) < 2:
            raise ValueError("TableConverter: au moins 2 points sont nécessaires")
        pts = sorted(((float(v), float(t)) for v, t in points), key=lambda p: p[0])
        self.v = [p[0] for p in pts]
        self.t = [p[1] for p in pts]

    def to_celsius(self, voltage: float) -> float:
        v, t = self.v, self.t
        # Sous la borne basse : extrapolation sur le premier segment.
        if voltage <= v[0]:
            return self._interp(voltage, v[0], v[1], t[0], t[1])
        # Au-dessus de la borne haute : extrapolation sur le dernier segment.
        if voltage >= v[-1]:
            return self._interp(voltage, v[-2], v[-1], t[-2], t[-1])
        # Recherche du segment encadrant.
        for i in range(1, len(v)):
            if voltage <= v[i]:
                return self._interp(voltage, v[i - 1], v[i], t[i - 1], t[i])
        return t[-1]  # ne devrait pas arriver

    @staticmethod
    def _interp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
        if x1 == x0:
            return y0
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


class NTCConverter(TemperatureConverter):
    """Thermistance NTC lue via un pont diviseur, équation Beta.

    Hypothèse de câblage (pullup_to_vref=True) :
        v_ref --[ R_series ]--+--[ NTC ]-- GND
                              |
                            mesure (ai)
    La tension mesurée est donc aux bornes de la NTC. On en déduit la résistance
    de la NTC puis la température via l'équation Beta :

        1/T = 1/T0 + (1/Beta) * ln(R/R0)     (T en kelvin)

    Si ``pullup_to_vref`` est False, la NTC est côté v_ref et R_series côté GND.

    ``fault_margin`` (fraction de v_ref, défaut 0.02) détecte un capteur
    débranché/en court-circuit : si la tension mesurée colle à un rail (0 ou
    v_ref) à cette marge près, le pont diviseur est défaillant et
    :meth:`to_celsius` renvoie ``NaN`` (traité comme un DÉFAUT, jamais comme un
    « très froid »/« très chaud » plausible). Mettre 0 désactive la détection.
    """

    def __init__(
        self,
        r_series: float,
        v_ref: float,
        r0: float,
        t0: float,
        beta: float,
        pullup_to_vref: bool = True,
        fault_margin: float = 0.02,
    ):
        self.r_series = float(r_series)
        self.v_ref = float(v_ref)
        self.r0 = float(r0)
        self.t0_k = float(t0) + 273.15
        self.beta = float(beta)
        # Garde-fous : ces paramètres apparaissent en dénominateur (ou dans un log) ;
        # une valeur nulle/négative produirait une division par zéro EN COURS d'essai,
        # dans la boucle de sécurité. On refuse à la construction (= à la validation).
        if self.beta == 0:
            raise ValueError("NTCConverter: 'beta' ne peut pas être 0.")
        if self.r_series <= 0 or self.v_ref <= 0 or self.r0 <= 0:
            raise ValueError("NTCConverter: 'r_series', 'v_ref' et 'r0' doivent être > 0.")
        self.pullup_to_vref = bool(pullup_to_vref)
        self.fault_margin = float(fault_margin)

    def _resistance(self, voltage: float) -> float:
        # Garde-fous numériques pour éviter division par zéro / log négatif.
        v = min(max(voltage, 1e-6), self.v_ref - 1e-6)
        if self.pullup_to_vref:
            # v aux bornes de la NTC (vers GND) : R_ntc = R_series * v / (v_ref - v)
            return self.r_series * v / (self.v_ref - v)
        # NTC côté v_ref : R_ntc = R_series * (v_ref - v) / v
        return self.r_series * (self.v_ref - v) / v

    def to_celsius(self, voltage: float) -> float:
        if _rail_fault(voltage, self.v_ref, self.fault_margin):
            return float("nan")
        r = self._resistance(voltage)
        if r <= 0:
            r = 1e-6
        inv_t = (1.0 / self.t0_k) + (1.0 / self.beta) * math.log(r / self.r0)
        return (1.0 / inv_t) - 273.15


class PTCConverter(TemperatureConverter):
    """Thermistance PTC/CTP **linéaire** (silistor type KTY, ou RTD PT100/PT1000),
    lue via le même pont diviseur que la NTC.

    Contrairement à la NTC, la résistance AUGMENTE avec la température. On utilise
    une loi linéaire :

        R(T) = R0 * (1 + alpha * (T - T0))   ->   T = T0 + (R/R0 - 1) / alpha

    où ``alpha`` est le coefficient de température (par °C). Exemples :
        - PT100  : r0 = 100,  t0 = 0,  alpha = 0.00385
        - PT1000 : r0 = 1000, t0 = 0,  alpha = 0.00385
        - silistor KTY : voir la datasheet (alpha ~ 0.007–0.008 / °C, peu linéaire).

    Pour une CTP très non linéaire, préfère le convertisseur 'table'. Une CTP
    céramique « à seuil » (BaTiO3) ne convient PAS à la mesure de température.
    Si ``pullup_to_vref`` est False, la PTC est côté v_ref et r_series côté GND.

    ``fault_margin`` (fraction de v_ref, défaut 0.02) : voir :class:`NTCConverter`.
    Une tension collée à un rail -> capteur débranché/court-circuit -> ``NaN``.
    """

    def __init__(
        self,
        r_series: float,
        v_ref: float,
        r0: float,
        t0: float,
        alpha: float,
        pullup_to_vref: bool = True,
        fault_margin: float = 0.02,
    ):
        self.r_series = float(r_series)
        self.v_ref = float(v_ref)
        self.r0 = float(r0)
        self.t0 = float(t0)
        self.alpha = float(alpha)
        # Garde-fous : alpha est en dénominateur de to_celsius — un alpha nul
        # provoquerait une ZeroDivisionError à la 1re mesure, dans la boucle de
        # sécurité. Refusé à la construction (= détecté dès la validation de config).
        if self.alpha == 0:
            raise ValueError("PTCConverter: 'alpha' ne peut pas être 0.")
        if self.r_series <= 0 or self.v_ref <= 0 or self.r0 <= 0:
            raise ValueError("PTCConverter: 'r_series', 'v_ref' et 'r0' doivent être > 0.")
        self.pullup_to_vref = bool(pullup_to_vref)
        self.fault_margin = float(fault_margin)

    def _resistance(self, voltage: float) -> float:
        v = min(max(voltage, 1e-6), self.v_ref - 1e-6)
        if self.pullup_to_vref:
            return self.r_series * v / (self.v_ref - v)
        return self.r_series * (self.v_ref - v) / v

    def to_celsius(self, voltage: float) -> float:
        if _rail_fault(voltage, self.v_ref, self.fault_margin):
            return float("nan")
        r = self._resistance(voltage)
        return self.t0 + (r / self.r0 - 1.0) / self.alpha


class ThermocoupleConverter(TemperatureConverter):
    """Thermocouple types **K** ou **J** : tension thermo-électrique -> °C.

    La tension lue (V) est convertie en emf (mV), compensée de la **soudure froide**
    (``cjc_c``, °C, approximation linéaire au coefficient de Seebeck), puis inversée
    par le polynôme NIST ITS-90. ``gain`` si la voie passe par un ampli, ``offset_mv``
    pour un décalage. Plage utile ~0–500 °C (K) / 0–760 °C (J).

    **Détection de défaut.** Un résultat hors de la plage de validité du polynôme
    (``t_min``/``t_max``, défauts par type) retourne ``NaN`` -> capteur en DÉFAUT :
    cela attrape une entrée flottante/collée à un rail (emf aberrante). ⚠ Limite
    assumée : un thermocouple **coupé dont l'entrée lit ~0 V** est indiscernable
    d'un objet à la température de soudure froide — la détection fiable du TC
    ouvert est matérielle (module avec open-TC detect) ; en logiciel, définir
    ``valid_min``/``valid_max`` au niveau du capteur (exigé par la validation).
    """

    # Coefficients inverses NIST ITS-90 (emf en mV -> °C).
    _INV = {
        "K": [0.0, 2.508355e1, 7.860106e-2, -2.503131e-1, 8.315270e-2,
              -1.228034e-2, 9.804036e-4, -4.413030e-5, 1.057734e-6, -1.052755e-8],
        "J": [0.0, 1.978425e1, -2.001204e-1, 1.036969e-2, -2.549687e-4,
              3.585153e-6, -5.344285e-8, 5.099890e-10],
    }
    # Sensibilité moyenne près de l'ambiante (µV/°C), pour la soudure froide.
    _SEEBECK_UV = {"K": 41.276, "J": 52.0}
    # Plage de validité du polynôme inverse par type (°C) : au-delà, le polynôme
    # diverge et la valeur n'a aucun sens -> NaN (défaut), jamais une valeur plausible.
    _T_RANGE = {"K": (-50.0, 520.0), "J": (-50.0, 780.0)}

    def __init__(self, tc_type: str = "K", cjc_c: float = 25.0,
                 gain: float = 1.0, offset_mv: float = 0.0,
                 t_min: Optional[float] = None, t_max: Optional[float] = None):
        self.tc = str(tc_type).upper()
        if self.tc not in self._INV:
            raise ValueError(f"Thermocouple: type {tc_type!r} non supporté (K ou J).")
        self.cjc_c = float(cjc_c)
        self.gain = float(gain) or 1.0
        self.offset_mv = float(offset_mv)
        lo, hi = self._T_RANGE[self.tc]
        self.t_min = lo if t_min is None else float(t_min)
        self.t_max = hi if t_max is None else float(t_max)

    def to_celsius(self, voltage: float) -> float:
        emf_mv = voltage * 1000.0 / self.gain - self.offset_mv
        emf_mv += self._SEEBECK_UV[self.tc] * self.cjc_c / 1000.0  # soudure froide
        t, p = 0.0, 1.0
        for c in self._INV[self.tc]:
            t += c * p
            p *= emf_mv
        # Hors plage de validité du polynôme (entrée flottante, rail, ampli saturé) :
        # DÉFAUT plutôt qu'une température extravagante mais « numérique ».
        if not (self.t_min <= t <= self.t_max):
            return float("nan")
        return t


# Presets de capteurs courants pour l'assistant (paramètres dépendant du capteur ;
# r_series / v_ref dépendent du câblage et restent à renseigner).
# Presets NTC : r0 = résistance à t0=25 °C, beta = coefficient B25/85 (datasheet).
# Réfère un capteur réel courant ; AJUSTE r_series / v_ref selon TON câblage.
NTC_PRESETS: Dict[str, Dict[str, float]] = {
    "NTC 10k B3950 (générique/EPCOS)": {"r0": 10000, "t0": 25, "beta": 3950},
    "NTC 10k B3435 (Murata NCP18WB)": {"r0": 10000, "t0": 25, "beta": 3435},
    "NTC 10k B3380 (Murata NCP18XH)": {"r0": 10000, "t0": 25, "beta": 3380},
    "NTC 10k B3977 (Vishay NTCLE100)": {"r0": 10000, "t0": 25, "beta": 3977},
    "NTC 100k B4250": {"r0": 100000, "t0": 25, "beta": 4250},
    "NTC 4.7k B3950": {"r0": 4700, "t0": 25, "beta": 3950},
    "NTC 2.2k B3977 (Vishay)": {"r0": 2200, "t0": 25, "beta": 3977},
}
# Presets PTC/RTD : loi linéaire R(T)=r0·(1+alpha·(T-t0)) ; alpha 0.00385/°C (norme EN).
PTC_PRESETS: Dict[str, Dict[str, float]] = {
    "PT100 (EN 60751)": {"r0": 100, "t0": 0, "alpha": 0.00385},
    "PT1000 (EN 60751)": {"r0": 1000, "t0": 0, "alpha": 0.00385},
    "KTY81-210 (~2k @25°C)": {"r0": 2000, "t0": 25, "alpha": 0.0079},
}


def parse_table_csv(text: str) -> List[List[float]]:
    """Parse une table d'étalonnage CSV ``tension,°C`` (un point par ligne).

    Séparateurs acceptés : virgule, point-virgule, tabulation ou espace ; décimale
    au point. Les lignes vides, commentaires (# //) et l'en-tête sont ignorés.
    """
    pts: List[List[float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = re.split(r"[,;\t ]+", line)
        if len(parts) < 2:
            continue
        try:
            pts.append([float(parts[0]), float(parts[1])])
        except ValueError:
            continue  # ligne d'en-tête / non numérique
    if len(pts) < 2:
        raise ValueError("CSV: au moins 2 points 'tension,°C' attendus.")
    return pts


_CONVERTERS = {
    "identity": lambda c: IdentityConverter(),
    "thermocouple": lambda c: ThermocoupleConverter(
        tc_type=c.get("tc_type", "K"), cjc_c=c.get("cjc_c", 25.0),
        gain=c.get("gain", 1.0), offset_mv=c.get("offset_mv", 0.0),
        t_min=c.get("t_min"), t_max=c.get("t_max")),
    "poly": lambda c: PolynomialConverter(c["coeffs"]),
    "polynomial": lambda c: PolynomialConverter(c["coeffs"]),
    "table": lambda c: TableConverter(c["points"]),
    "ntc": lambda c: NTCConverter(
        r_series=c["r_series"],
        v_ref=c["v_ref"],
        r0=c["r0"],
        t0=c["t0"],
        beta=c["beta"],
        pullup_to_vref=c.get("pullup_to_vref", True),
        fault_margin=c.get("fault_margin", 0.02),
    ),
    "ptc": lambda c: PTCConverter(
        r_series=c["r_series"],
        v_ref=c["v_ref"],
        r0=c["r0"],
        t0=c["t0"],
        alpha=c["alpha"],
        pullup_to_vref=c.get("pullup_to_vref", True),
        fault_margin=c.get("fault_margin", 0.02),
    ),
}
_CONVERTERS["rtd"] = _CONVERTERS["ptc"]  # alias (PT100/PT1000)
_CONVERTERS["tc"] = _CONVERTERS["thermocouple"]  # alias


def build_converter(cfg: Dict[str, Any]) -> TemperatureConverter:
    """Construit un convertisseur à partir d'un dict de configuration."""
    ctype = str(cfg.get("type", "identity")).lower()
    factory = _CONVERTERS.get(ctype)
    if factory is None:
        raise ValueError(
            f"Type de convertisseur inconnu : {ctype!r}. "
            f"Disponibles : {sorted(_CONVERTERS)}"
        )
    return factory(cfg)
