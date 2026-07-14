# Architecture — ALIM_SEQ

Technical document describing the application's internals. Audience: developers and
maintainers. For usage, see [USER_MANUAL.md](USER_MANUAL.md). The Windows executables
are produced by a self-hosted CI (see §13).

## 1. Overview

ALIM_SEQ sequences the power supply of an electronic board: it drives power channels
(R&S HMP40xx/20xx over SCPI), measures temperatures (NI module), runs scripted
sequences, and applies **thermal safety monitoring**. It runs on **real hardware** or
in **simulation** (same code paths, drivers replaced by mocks).

Design principles:

- **Core decoupled from the GUI.** All the logic (control, measurement, safety,
  sequences, reports) lives in the `alim_seq/` package and does not depend on Qt. The
  Qt GUI (`gui_qt/`) plugs into it; the core stays testable and scriptable without it.
- **Safety first.** A fast, independent safety loop can power down the board at any
  time, including by overriding the running sequence.
- **Abstract + simulable hardware.** The drivers (`PSU`, `DAQ`) share a common
  interface and a faithful mock implementation (thermal model), to test everything
  without a bench.
- **Serialized hardware access.** All instrument exchanges go through a **single
  lock**, avoiding SCPI interleaving and desynchronizations.

## 2. Module map

```
main.py                  entry point: arguments, GUI choice, config loading
alim_seq/
  config.py              schema (dataclasses) + load_config + validation
  instrument.py          capability-based abstraction (SourceTension/MesureVI/…),
                         INSTRUMENTS registry + create_instrument factory
  psu.py                 supply drivers: BasePSU, HMP4040 & variants,
                         MockPSU, PSU_MODELS registry, label routing
  daq.py                 NI acquisition: NIDaq (nidaqmx) + MockDAQ (thermal model)
  relay.py               actuators (BaseRelay/MockRelay), outputs by label + safe_state
  temperature.py         voltage→°C converters (table/poly/ntc/ptc/identity/tc)
  expressions.py         safe expression evaluator (SETV/SETI)
  sequencer.py           parse + run .seq sequences (interruptible)
  controller.py          orchestration: measurement & safety loops, trip, lifecycle
  controller_recording.py  RecordingMixin: test recording (start/stop, CSV rows)
  controller_servo.py    ServoMixin: linear / adaptive servo control
  controller_simtune.py  SimTuneMixin: live tuning of the simulated bench (loads, couplings)
  essai.py               self-contained test folder (CSV + artifacts)
  rapport.py             test report: data + HTML (pure Python) → PDF (ReportLab) + charts (matplotlib)
  gui_qt/                Qt/PySide6 GUI (the only interface)
    main_window.py       window, tabs, menus, safety bar, help (F1)
    config_tab.py        config editing (forms + advanced JSON)
    config_wizard.py     configuration wizard (offered on first launch)
    editor.py            sequence editor (highlighting, auto-completion, live lint)
    plot.py              Chart tab (temperatures/currents/voltages)
    replay.py            replay of a recorded test + comparison of two tests
    sim_tab.py           Simulation tab: live tuning of the virtual bench (SimMixin)
    converter.py         temperature converter assistant (live curve)
    workers.py           background hardware tasks (connection, VISA scan)
    theme.py, widgets.py dark theme, bounded widgets (inputs, two-step arming)
packaging/launcher.py    packaged entry point: data folder + chdir
```

Layers (bottom to top): **drivers** (`psu`, `daq`) → **domain** (`config`,
`temperature`, `expressions`, `sequencer`) → **orchestration** (`controller`) →
**GUI** (`gui`, `gui_qt`) + **outputs** (`essai`, `rapport`).

## 3. Threading model and data flow

The application is multi-threaded; the GUI never blocks on the hardware.

- **GUI thread (main)** — Qt. Never calls the hardware directly for a long operation.
- **Measurement loop** (the `Controller`'s thread) — reads the supplies' V/I at the
  `safety.poll_interval` rate (SCPI, slower), pushes samples to the GUI
  (signals/callbacks) and the CSV.
- **Safety loop** — reads temperatures at `safety.temp_poll_interval` (fast, 0.2 s)
  **independently** of the V/I measurement: protection stays reactive even if the
  supplies respond slowly.
- **Sequencer thread** — runs a sequence action by action, interruptible at any time
  (pause, stop, emergency stop).
- **Hardware workers** (`gui_qt/workers.py`) — connection, reconnection, VISA scan
  and test run in the background; a hardware timeout does not freeze the window, and
  the emergency stop stays clickable.

All instrument accesses (measurement, sequence, safety, GUI) converge on the
`Controller` and are **serialized by a per-instrument lock**. Nominal flow:

```
config.json → load_config → Controller ── creates ─▶ instruments (by capability)
                                                       · sources (real/mock supply)
                                                       · temperature (NI/mock)
Controller.measurement_loop → V/I → GUI + CSV        (MesureVI instruments)
Controller.safety_loop      → °C  → thresholds → power-down (MesureTemperature instruments)
sequencer                   → actions → Controller (SET/ON/RAMP/SERVO…) → sources
```

## 4. The Controller

`controller.py` is the conductor. It:

- builds the drivers according to `simulate` (real or mocks) and the **fault-tolerant
  connections** (the GUI opens even if an instrument is absent, with a *Reconnect*
  button);
- runs the two loops (V/I measurement, thermal safety);
- exposes the control primitives called by the GUI **and** the sequencer: voltage/
  current setting, ON/OFF, ramps, **servo control**;
- holds the **safety state** (normal / warning / critical / fault / trip) and triggers
  the power-downs;
- logs (`enable_file_logging` → `logs/alim_seq.log`, rotation) and feeds the test
  recording.

**Mixin decomposition.** The safety core (measurement/safety loops, locks,
connect/reconnect lifecycle, escalation, `emergency_stop`, `snapshot`) stays in
`controller.py`. The cohesive periphery is extracted into **mixins** sharing the same
`self` — hence with no behavior change (`class Controller(RecordingMixin, ServoMixin,
SimTuneMixin)`): `RecordingMixin` (test recording), `ServoMixin` (servo control) and
`SimTuneMixin` (live tuning of the simulated bench).

**Servo control.** Raises/lowers the voltage of a *set* channel until a target
current is reached on a *measured* channel. Two strategies: `SERVO_LIN` (fixed step)
and `SERVO_ADAPT` (adaptive step, secant/Newton type — large step far from the
target, fine near it, with damping). The servo knows the **polarity** of negative
rails and the action direction (`invert` option).

**HMP state reading.** CV/CC and the faults (OVP, electronic fuse, overtemperature)
are read from the HMP's **status register** (`STAT:QUES:INST:ISUM<n>:COND?`) when
`cc_status` is active, with a fallback to a V/I inference (hysteresis) if the firmware
does not respond.

## 5. Hardware drivers and simulation

**`instrument.py`** — **capability-based** abstraction: an `Instrument` declares what
it can do (`SourceTension`, `MesureVI`, `MesureTemperature`, `Actionneur`) instead of
being categorized. Unified `INSTRUMENTS` registry / `create_instrument` factory. The
`Controller` drives *by capability* and routes each channel **label** to a physical
`(instrument, channel)`. To **integrate a new device**, see
[GUIDE_DRIVERS.md](GUIDE_DRIVERS.md).

`psu.py` — common `BasePSU` interface (`SourceTension`+`MesureVI` capabilities);
`HMP4040` (and subclasses `HMP4030` / `HMP2030` / `HMP2020`: same SCPI commands,
different channel count). SCPI hardening: explicit `\n` terminations (raw socket),
buffer purge on connection, `*OPC?` after each setting (balanced I/O), optional
`visa_query_delay` against *input protocol violation*.

`daq.py` — `NIDaq` (via `nidaqmx`, analog inputs `ai0…`, ±10 V range by default);
`MockDAQ` in simulation.

`relay.py` — actuators (`Actionneur` capability): `BaseRelay`/`MockRelay`, outputs
addressed by **label**. A relay is declared in `instruments` (driver `MOCK-RELAY`)
with its `outputs`; each output carries a `safe_state` (default OFF/open) applied on
an emergency stop and at the end of an orderly power-down. Driven by `RELAY <output>
ON|OFF` (sequence) and `Controller.set_relay`. No real hardware model is integrated
yet (the `MockRelay` acts as a "virtual" relay).

**Simulation.** `MockPSU` models a **per-channel load** (`simulation.loads`, `I =
V/R`, transition into CC if `V/R` exceeds the limit) and, optionally, **gate→drain
couplings** (`simulation.couplings`, transconductance `Id = gm·(Vg−vth)`) to make a
servo converge without a bench. `MockDAQ` applies a **thermal model** (the board
heats up with the dissipated power: gain, time constant, noise), which allows
**validating the safety trip**.

## 6. The sequencer

`sequencer.py` — a sequence is a text file, **one action per line**.

- `parse_sequence(text, valid_labels, valid_sensors) -> List[Action]`: parses and
  **validates** (syntax, existence of channels/sensors, numeric validity of the
  arguments, `key=value` keys whitelisted per command, `RAMP` with an integer step
  count ≥ 2). A checked sequence does not stop midway because of a typo.
- `REPEAT n … END` loops (nesting possible) expanded at parse time.
- `estimate_duration(actions)`: estimated duration (shown on the check).
- **Interruptible** execution in the sequencer thread: freezable `WAIT`
  (pause/resume), **step-by-step** mode, clean **stop**.
- Computed setpoints `SETV`/`SETI`: delegate to `expressions.py`, a **restricted**
  evaluator (channel names = voltage setpoint; functions `V/Vmeas/Iset/I`; arithmetic
  operators; **no** arbitrary code). The result is bounded by the
  `max_voltage`/`max_current`.

Commands: `SET/VOLTAGE/CURRENT`, `SETV/SETI`, `ON/OFF`, `WAIT`, `RAMP`,
`SERVO_LIN/SERVO_ADAPT`, `WAIT_CURRENT`, `WAIT_TEMP`, `RELAY`, `LOG`, `ALL_OFF`,
`SHUTDOWN`, `REPEAT/END`. Full reference: Appendix A of the manual (and the app's Help
menu).

## 7. Configuration

`config.py` — `load_config(path)` reads the JSON into typed **dataclasses**
(`AppConfig`, `ChannelConfig`, `GroupConfig`, `TempSensorConfig`) then `_validate()`
checks **consistency**: known supply model, channel within the model's range,
uniqueness of channel↔physical channel, `critical > warning` thresholds, group
members that exist and are not shared (≥ 2, series only), sensor guard rails
(plausibility band or `fault_margin`), resolved `ref_channel`. Validation **rejects**
an inconsistent configuration (orphan references, limits out of the model…).

Sections: `simulate`, `instruments`, `channels`, `groups`, `temperatures`, `safety`,
`simulation`, plus `visa_backend`, `visa_query_delay`, `cc_status`.

**Unified `instruments` section** (canonical) — describes the device chain without
presuming a category: each entry is `"<name>": {"driver": "…", …params}` (e.g.
`{"driver": "HMP4040", "resource": "…"}`, `{"driver": "NI-DAQ", "device": "Dev1"}`).
The controller classifies each instrument **by capability** via its `driver`. The
historical **`supplies`** (supplies) and **`daq`** (NI module) sections stay accepted
as **backward-compatible sugar**: `AppConfig.__post_init__` keeps both views
consistent (`instruments` is authoritative). `config_to_dict()` does the reverse path
(archiving) and emits both. The **default shipped** config is neutral (1 HMP4040,
channels `CH1`/`CH2`, `simulate: true`).

## 8. Temperatures and converters

`temperature.py` — each sensor converts an **NI voltage** into °C according to
`converter.type`: `identity`, `polynomial`, `table` (interpolation), `ntc`
(β / Steinhart-Hart equation), `ptc`/`rtd` (linear, PT100/PT1000), `thermocouple`.
For `ntc`/`ptc`, a voltage **stuck to a rail** (disconnected sensor / short circuit)
is detected → **FAULT** (never a falsely plausible extreme temperature). A sensor can
be **conditioned on channels** (`requires`): "pending" (excluded from safety) as long
as these channels are not ON. Optional check of the bridge's **reference voltage**
(`ref_channel`).

## 9. Safety — state machine

Global state: **OK → WARNING → CRITICAL**, plus **sensor FAULT** and **TRIP**
(locked). On a **critical** overshoot (or temperature/comm loss depending on the
config):

1. **Orderly power-down** — runs `sequences/shutdown.seq` if it exists (or
   `safety.shutdown_sequence`), otherwise a channel-by-channel switch-off in the
   reverse order of the config (`shutdown_delay` between channels). **Priority and
   non-interruptible**: it overrides the user sequence (after
   `shutdown_takeover_wait_s`) and ignores *Stop*.
2. **Last-resort hard cut-off** — if the temperature reaches `critical +
   hard_margin_c`, or if the power-down exceeds `shutdown_timeout`, or on a supply
   communication loss: all outputs drop immediately.

After an incident → **TRIP** state: any switch-on is refused until a deliberate
**Rearm** (after fixing). The running recording **does not close**: it captures the
power-down (valuable for analysis) and marks the outcome. HMP hardware faults
(OVP/fuse/overtemperature) and sensor faults can, optionally, trigger the power-down
(`shutdown_on_*`).

## 10. Recording: test folder and report

`essai.py` — each recording creates a **self-contained folder**
`logs/essais/YYYYMMDD_HHMMSS[_<name>]/` containing `mesures.csv` (one line per cycle,
flushed live: timestamp, °C + raw NI voltage per sensor, Vset/Iset/Vmeas/Imeas/out
per channel, safety state), a **copy of the active config** (+ hash), the executed
`sequence.seq`, `journal.log`, and `essai.json` (metadata + **outcome**: `termine` /
`arret_utilisateur` / `declenchement_securite` / `en_cours`).

`rapport.py` — three Qt-free layers: (1) **data** (`stats_*`, `evenements`,
`trip_info`, pure Python, testable); (2) **charts** plotted by **matplotlib** (Agg
backend) from `mesures.csv`; (3) **renderers** sharing the data — `construire_html`
(browser preview) and `exporter_pdf` **via ReportLab** (pure Python: one page per
part, colored-header tables, paginated footer). Benefit: the report **regenerates
from the test folder alone**, without live state, even long after. Without
matplotlib, the report is produced without the charts.

## 11. GUI

The **Qt/PySide6** GUI (`gui_qt/`) is the only interface, plugged into the
`Controller`: Control / Configuration / Sequence editor / Chart / **Simulation** tabs
(the last one in simulated mode); a **permanent safety bar** (Emergency stop,
Shutdown sequence, Rearm, All OFF, mode badge); inputs **bounded** by the config
(yellow = not applied); **two-step arming** of ON on real hardware (1st click = arm,
2nd = switch on; bypassed with Shift); configuration editable via synced **forms +
advanced JSON**; a **converter assistant** (live curve); a chart switchable between
°C/A/V with a read cursor, thresholds, event markers and an **operator marker**
(`Ctrl+M`); background workers; built-in help (**F1** → manual, command reference,
shortcuts). The whole UI is **bilingual** (English/French, *View → Language*).

- **Sequence editor** — highlighting, auto-completion, clickable palette and **live
  lint** (check as you type, faulty line underlined, ✓/✗ status).
- **Test replay and comparison** (*File* menu) — reopens a recorded test folder and
  **replays its curves** (`replay.py`, reusing the chart cursor), with PDF report
  regeneration; or **overlays two tests** aligned on t = 0.
- **Configuration wizard** (`config_wizard.py`) — offered **on the very first launch**
  (once) and available in the *File* menu: simulation, VISA scan or manual address
  entry.

## 12. Packaging and user data

- **`packaging/launcher.py`** (the exe's entry point): forces the Qt GUI, resolves
  the **writable data folder** — the one chosen at install time (registry
  `HKCU/HKLM\Software\ALIM_SEQ\DataDir`), otherwise `Documents\ALIM_SEQ` —, **drops**
  `config.json` + `sequences/` there on first launch, then **`chdir`** into it. This
  way all relative paths (`config.json`, `logs/…`) fall into that folder, even with a
  read-only installation.
- **PyInstaller** (`packaging/ALIM_SEQ.spec`): **onefile** exe, bundles PySide6
  (heavy Qt modules excluded), pyvisa/pyvisa-py + backends, nidaqmx (+ metadata),
  matplotlib (Agg backend), the translation catalogs (`.qm`/`.mo`), and the data
  (`config.json`, `sequences/`, `docs/USER_MANUAL.*`, `docs/MANUEL_UTILISATEUR.*`).
  As the Forgejo runner has no official Windows binary, it is cross-compiled (see
  TOOLCHAIN).
- **Inno Setup** (`packaging/ALIM_SEQ.iss`): installer with an admin/non-admin
  choice, a logo in the wizard, and a **data-folder choice page** (writes the registry
  key read by the launcher). The **NI-DAQmx** driver still has to be installed
  separately on the target machine for real acquisition.

## 13. Toolchain (build)

The Windows executables are produced by a self-hosted CI (Forgejo + on-demand Windows
VM). A `git push` of a `v*` tag — or `tools/lab-build.sh <tag>` — triggers `pip →
PyInstaller → Inno Setup`. The build entry points are `packaging/ALIM_SEQ.spec`
(PyInstaller) and `packaging/ALIM_SEQ.iss` (Inno Setup).
