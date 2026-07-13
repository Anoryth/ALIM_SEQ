"""Drivers d'acquisition (mesure de température via le module NI).

- :class:`BaseDAQ`  : interface ; ``read_temperatures()`` renvoie {nom: °C}.
- :class:`NIDaq`    : module National Instruments via nidaqmx. Lit une **tension**
                      par voie puis applique le convertisseur configuré (-> °C).
- :class:`MockDAQ`  : modèle thermique du 1er ordre piloté par la puissance
                      délivrée par les alimentations (la carte chauffe quand on
                      l'alimente), pour tester la chaîne de sécurité sans matériel.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Dict, List

from .config import TempSensorConfig
from .instrument import Instrument, MesureTemperature
from .temperature import build_converter


class BaseDAQ(Instrument, MesureTemperature):
    """Module d'acquisition : un :class:`~alim_seq.instrument.Instrument` exposant la
    capacité :class:`~alim_seq.instrument.MesureTemperature`."""

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def read_temperatures(self) -> Dict[str, float]: ...

    def read_voltages(self) -> Dict[str, float]:
        """Tensions BRUTES (V) lues au dernier ``read_temperatures`` (avant
        conversion en °C). Vide par défaut (ex. acquisition simulée)."""
        return {}


class NIDaq(BaseDAQ):
    """Module NI : lit des tensions analogiques et les convertit en °C."""

    def __init__(self, device: str, sensors: Dict[str, TempSensorConfig]):
        self.device = device
        self.sensors = sensors
        self._converters = {
            name: build_converter(s.converter) for name, s in sensors.items()
        }
        self._task = None
        self._order: List[str] = list(sensors.keys())
        # Dernières tensions brutes lues (conservées pour l'enregistrement CSV).
        self._last_voltages: Dict[str, float] = {}

    def connect(self) -> None:
        import nidaqmx  # import paresseux : non requis en mode simulation

        self._task = nidaqmx.Task()
        for name in self._order:
            s = self.sensors[name]
            phys = f"{self.device}/{s.channel}"
            # Plage d'entrée configurable : nidaqmx crée sinon la voie en ±5 V, alors
            # que le module supporte souvent ±10 V (voir 'ai_min'/'ai_max' du capteur).
            self._task.ai_channels.add_ai_voltage_chan(
                phys, min_val=s.ai_min, max_val=s.ai_max)

    def close(self) -> None:
        if self._task is not None:
            self._task.close()
            self._task = None

    def read_temperatures(self) -> Dict[str, float]:
        values = self._task.read()
        if not isinstance(values, list):  # une seule voie -> scalaire
            values = [values]
        out: Dict[str, float] = {}
        volts: Dict[str, float] = {}
        for name, v in zip(self._order, values):
            fv = float(v)
            volts[name] = fv  # tension brute conservée (filet de sécurité)
            out[name] = self._converters[name].to_celsius(fv)
        self._last_voltages = volts
        return out

    def read_voltages(self) -> Dict[str, float]:
        return dict(self._last_voltages)


class MockDAQ(BaseDAQ):
    """Acquisition simulée avec modèle thermique du 1er ordre.

    ``power_provider`` doit retourner la puissance totale (W) délivrée par les
    alimentations. La température cible est ``ambient + gain * puissance`` et la
    température réelle la rejoint avec une constante de temps ``tau``.
    """

    def __init__(
        self,
        sensors: Dict[str, TempSensorConfig],
        power_provider: Callable[[], float],
        ambient_c: float = 25.0,
        thermal_gain_c_per_w: float = 6.0,
        thermal_tau_s: float = 8.0,
        noise_c: float = 0.15,
    ):
        self.sensors = sensors
        self.power_provider = power_provider
        self.ambient = ambient_c
        self.gain = thermal_gain_c_per_w
        self.tau = max(thermal_tau_s, 0.1)
        self.noise = noise_c
        # Coefficient de couplage par capteur : crée une légère diversité.
        self._coupling = {}
        for i, name in enumerate(sensors):
            self._coupling[name] = 1.0 + 0.25 * i
        self._temp: Dict[str, float] = {n: ambient_c for n in sensors}
        self._last_t = time.monotonic()

    def connect(self) -> None:
        self._last_t = time.monotonic()

    def close(self) -> None:
        pass

    def read_temperatures(self) -> Dict[str, float]:
        now = time.monotonic()
        dt = now - self._last_t
        self._last_t = now
        power = max(0.0, float(self.power_provider()))
        out: Dict[str, float] = {}
        for name in self.sensors:
            target = self.ambient + self.gain * self._coupling[name] * power
            cur = self._temp[name]
            # Réponse exponentielle du 1er ordre vers la cible.
            alpha = 1.0 - pow(2.718281828, -dt / self.tau) if dt > 0 else 0.0
            cur += (target - cur) * alpha
            self._temp[name] = cur
            out[name] = cur + random.uniform(-self.noise, self.noise)
        return out
