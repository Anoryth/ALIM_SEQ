# Device driver integration guide

This guide is for **contributors** who want to wire a new device (power supply,
measurement module, relay, or any other instrument) into ALIM_SEQ. The architecture is
designed so that **the rest of the application adapts automatically**: config, GUI,
sequencer, simulation, validation.

For the overall architecture and the design of the capability model, see
[ARCHITECTURE.md](ARCHITECTURE.md) (§5, *Hardware drivers and simulation*).

---

## 1. The mental model: **capabilities**, not categories

A device is not "a supply" or "a DAQ". It is an
[`Instrument`](../alim_seq/instrument.py) (lifecycle `connect`/`close` + identity)
that **declares the capabilities** it exposes:

| Capability | What it promises | Examples |
|---|---|---|
| `SourceTension` | impose a voltage + current limit, cut off | supply, sink load |
| `MesureVI` | measure V/I (+ CV/CC mode, faults) | supply, multimeter |
| `MesureTemperature` | provide °C per point + raw voltages | NI module, I²C sensor |
| `Actionneur` | open/close a logical output | relay, GPIO |

A power supply implements **`SourceTension` + `MesureVI`**. The controller only talks
to capabilities (`isinstance(instr, MesureTemperature)`), never to concrete types. A
device may combine unprecedented capabilities.

Each instrument is built by a **unified registry**:
[`create_instrument(driver, simulate, name, **params)`](../alim_seq/instrument.py).

**Two golden, non-negotiable rules** (they define the project's identity):

1. **Simulation / real parity.** Every real driver has a **mock** with plausible
   behavior. The same code must run in simulation (no hardware) and on real hardware.
2. **Safety first.** `close()` must **cut off the outputs** even if the device is
   slow/unwell; an unreliable measurement must report a **fault**, never return a
   falsely plausible value. The driver **takes no lock**: serialization is done by the
   controller (one lock per instrument).

---

## 2. Most frequent case: a new **power supply**

### 2.1 Same SCPI family as the R&S HMP

If the device speaks the same dialect as the HMP40xx (many R&S/HMC supplies),
subclass [`HMP4040`](../alim_seq/psu.py) and adjust what differs:

```python
# alim_seq/psu.py
class HMP2020(HMP4040):
    """R&S HMP2020 — same SCPI family, 2 channels."""
    n_channels = 2
    model = "HMP2020"
    # Per-channel SOA limits (datasheet) — used to VALIDATE the config:
    max_voltage = 32.0
    max_current = 10.0
    max_power = 80.0
```

### 2.2 A different dialect (new brand)

Subclass [`BasePSU`](../alim_seq/psu.py) directly (which is already `Instrument +
SourceTension + MesureVI`) and implement the contract:

```python
class NGP804(BasePSU):
    """Example: R&S NGP804 (4 channels). Adapt to YOUR device."""
    n_channels = 4
    model = "NGP804"
    max_voltage, max_current, max_power = 64.0, 20.0, 200.0   # SOA / channel

    def __init__(self, resource, visa_backend="", use_cc_status=False,
                 query_delay_s=0.0, log=None, **_):
        self.resource = resource
        self.visa_backend = visa_backend
        self._log = log or (lambda _m: None)
        self._inst = None

    # --- lifecycle -------------------------------------------------------
    def connect(self):
        import pyvisa                                   # LAZY import
        rm = pyvisa.ResourceManager(self.visa_backend) if self.visa_backend \
            else pyvisa.ResourceManager()
        self._inst = rm.open_resource(self.resource)
        self._inst.read_termination = self._inst.write_termination = "\n"
        self.idn = str(self._inst.query("*IDN?")).strip()   # FAST failure if mute

    def close(self):
        # MANDATORY: cut off the outputs, without blocking if the device no longer
        # responds (short timeout), then close the session whatever happens.
        if self._inst is None:
            return
        try:
            self.all_outputs_off()
        except Exception:
            pass
        finally:
            try:
                self._inst.close()
            finally:
                self._inst = None

    # --- SourceTension capability ---------------------------------------
    def set_voltage(self, channel, voltage):
        self._inst.write(f"INST:NSEL {channel}"); self._inst.write(f"VOLT {voltage:.4f}")

    def set_current(self, channel, current):
        self._inst.write(f"INST:NSEL {channel}"); self._inst.write(f"CURR {current:.4f}")

    def set_output(self, channel, on):
        self._inst.write(f"INST:NSEL {channel}"); self._inst.write(f"OUTP {int(on)}")

    # --- MesureVI capability ---------------------------------------------
    def measure_voltage(self, channel):
        self._inst.write(f"INST:NSEL {channel}"); return float(self._inst.query("MEAS:VOLT?"))

    def measure_current(self, channel):
        self._inst.write(f"INST:NSEL {channel}"); return float(self._inst.query("MEAS:CURR?"))

    def measure_status(self, channel):
        """Return {'mode': 'CV'|'CC'|None, 'faults': [...]}. If the device cannot
        tell, return {'mode': None, 'faults': []}: the controller infers the mode
        from V/I. 'faults' may contain 'OVP', 'FUSE', 'OTP'."""
        return {"mode": None, "faults": []}
```

> `set_voltage` receives a **positive magnitude**: the software handles the polarity
> of negative rails (supplies only output positive). Do not reinvent the sign.

### 2.3 Register the model

Add the class to the registry — **that's all**:

```python
# alim_seq/psu.py, at the bottom
PSU_MODELS = {..., "NGP804": NGP804}
```

`create_psu` then builds a `MockPSU` (right channel count) in simulation and your
driver on hardware; config validation accepts the model and checks channels/limits;
the GUI offers it in the drop-down and the configuration wizard.

**Simulation is already covered**: `MockPSU` (resistive load + noise, configurable
channel count) serves as the mock for *any* source model. You have nothing to write
for parity.

---

## 3. Other capabilities

### 3.1 Temperature measurement module

Subclass [`BaseDAQ`](../alim_seq/daq.py) (`Instrument + MesureTemperature`):

```python
class MyDAQ(BaseDAQ):
    def __init__(self, device, sensors): ...
    def connect(self): ...
    def close(self): ...
    def read_temperatures(self) -> dict:   # {sensor_name: °C}
        ...
    def read_voltages(self) -> dict:       # {sensor_name: raw V}  (safety net)
        ...
```

**Mandatory fault detection**: an unreliable measurement (disconnected sensor, input
stuck to a rail) must produce `float("nan")` — the controller classifies it as `FAULT`
and excludes it from safety. **Never** return an invented plausible temperature (see
the converter logic in [temperature.py](../alim_seq/temperature.py), which returns
`NaN` on a fault).

Registration (temperature branch of `create_instrument`): add an alias in
`_NIDAQ_ALIASES` (or a dedicated driver key) and instantiate your class in the
matching branch of [instrument.py](../alim_seq/instrument.py). Provide a mock (simple
model) for the simulation, like `MockDAQ`.

### 3.2 Relay / actuator

Subclass [`BaseRelay`](../alim_seq/relay.py) (`Instrument + Actionneur`):

```python
class MyRelay(BaseRelay):
    def connect(self): ...
    def close(self): self.all_off()        # safe rest state
    def set_state(self, label, on): ...     # close/open an output
    def get_state(self, label): ...         # read back the state (or None)
```

Registration: add the driver name to `_RELAY_DRIVERS`, build the class in the actuator
branch of `create_instrument`, and add it to the `INSTRUMENTS` dict +
`available_instruments()`. The `MockRelay` mock serves the simulation. The rest (config
`instruments.<name>.outputs`, the `RELAY` sequence command, the `set_relay` controller
primitive, the safe state, the GUI display) is **already wired**.

### 3.3 An entirely new capability

Define a **thin mixin** in [instrument.py](../alim_seq/instrument.py) (methods as
`...`, no over-abstraction), have your driver inherit it, expose it via `driver_role`,
and have the controller iterate `isinstance(instr, MyCapability)` where relevant —
**without breaking the lock ordering invariant** (see
[DEVELOPMENT.md §6](DEVELOPMENT.md)).

---

## 4. The contract, spelled out

Every driver MUST respect:

- **`connect()`**: fail **fast and clearly** if the link does not respond (probe
  `*IDN?` early), with an actionable message. Hardware imports (`pyvisa`, `nidaqmx`)
  **lazy** (not required in simulation).
- **`close()`**: **cut off the outputs** then close, without blocking if the device is
  mute (shorten the timeout). This is a safety point, not a courtesy.
- **Fault detection**: report (fault / `NaN`) an unreliable measurement; never return
  a falsely plausible value.
- **SOA limits** (`max_voltage/current/power`) filled from the datasheet — they are
  used to **reject** a dangerous config at validation.
- **No locking** in the driver: the controller serializes (one lock per instrument).
  Your methods are called under that lock; do not spawn threads.
- **Simulation parity**: provide/reuse a mock. `MockPSU`/`MockDAQ`/`MockRelay` already
  cover the three existing capabilities.

---

## 5. Testing

- Add a test in the module's file (`tests/test_psu.py`, `tests/test_instrument.py`,
  `tests/test_relay.py`…). The suite runs **exclusively in simulation** (no hardware,
  no network).
- Check at least: the exposed **capabilities** (`isinstance` / `capabilities_of`), the
  **factory** (`create_instrument("YOUR-DRIVER", simulate=True)` returns the mock), and
  config **validation** (known model, consistent channels/limits).
- Validate **on real hardware** before proposing the driver for critical use —
  simulation does not prove the SCPI dialect nor the real safety behavior.

```bash
python -m pytest tests/test_instrument.py -v
```

---

## 6. Summary: integrate a driver in 4 steps

1. Write the class (subclass of `BasePSU` / `BaseDAQ` / `BaseRelay` / new capability),
   respecting the **contract §4**.
2. **Register** it (`PSU_MODELS` for a source; a branch of `create_instrument` +
   `available_instruments()`/`INSTRUMENTS` for the other families).
3. Ensure **simulation parity** (reuse an existing mock, or write one).
4. **Test** in simulation, then validate on real hardware.

The rest — config, GUI, sequencer, wizard, report — adapts **on its own**.

> Known roughness: registering a **source** takes only one line in `PSU_MODELS`; a
> **temperature/actuator** capability still requires editing the matching branch of
> `create_instrument`. Unifying this (a metadata-driven family registry) is a welcome
> open task.
