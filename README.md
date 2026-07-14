**English** · [Français](README.fr.md)

# Power-supply sequencer — R&S HMP + National Instruments acquisition

Python application to **sequence the power supply of an electronic board** safely:
channel control (R&S HMP40xx / 20xx over **SCPI**), voltage → current **servo
control**, **temperature** measurement (NI module), **thermal safety**, recording and
**test reports**. **Qt** GUI (PySide6), **bilingual EN/FR**. Runs in **simulation**
(no hardware) as well as on **real hardware** — the same code.

> ⚠️ **Safety.** This software drives **power supplies**: its protections are
> **software** and do not replace a hardware safety device nor the operator's
> judgement. Provided **without warranty** (GPL‑3.0), **not certified**, use **at your
> own risk**. Connect the instruments on an **isolated bench network** (SCPI/TCPIP has
> no authentication). See [SECURITY.md](SECURITY.md).

## Overview

<p align="center"><img src="docs/img/demo.gif" alt="Demo: temperature rise then safety trip" width="840"></p>

> **Safety in action** *(simulation)* — the board heats up under power, monitoring
> crosses the **warning** threshold, then at **critical** the **safety power-down**
> triggers (red banner) and the temperature drops. No hardware required.

<p align="center"><img src="docs/img/01-controle.png" alt="Control tab" width="840"></p>

> **Control** tab — power channels and series group, temperature monitoring
> (thresholds), **permanent safety bar** (emergency stop, shutdown sequence, rearm),
> mode badge and log. *(simulation scenario)*

<p align="center"><img src="docs/img/02-graphe.png" alt="Chart tab" width="840"></p>

> **Chart** tab — real-time curves switchable between **°C / A / V**, warning/critical
> thresholds, **read cursor** for values, event markers, **PNG / CSV** export.

<p align="center"><img src="docs/img/03-editeur.png" alt="Sequence editor" width="840"></p>

> **Sequence editor** tab — syntax highlighting, **live lint** (✓/✗ + faulty line),
> auto-completion and a clickable command palette.

## Features

- **Power channels** — voltage / current-limit setting, ON/OFF, **series groups**,
  negative rails, labels (`VCC`, `VDRAIN`…).
- **Servo control** — drives one channel until a **target current** measured on
  another is reached, with fixed or **adaptive** step (secant/Newton).
- **Thermal safety** — warning/critical thresholds per sensor; at critical, an
  **orderly power-down** (soft switch-off), **hard cut-off** as a last resort,
  **emergency stop**, state locked until rearmed.
- **Temperatures** — voltage → °C conversion (table, polynomial, NTC, PTC/RTD, K/J
  thermocouple) with **faulty-sensor detection**.
- **`.seq` sequences** (one action per line: `SET`, `ON/OFF`, `WAIT`, `RAMP`, `SERVO`,
  `WAIT_CURRENT/TEMP`, `RELAY`, `REPEAT`…) — built-in editor with **live lint** and
  auto-completion.
- **Relays / actuators** and simulated **couplings** (test a servo without hardware).
- **Traceability** — self-contained test folders (CSV + config + sequence + log),
  **regenerable PDF report**, test **replay** and **comparison**.
- **Configuration wizard** — simulation, VISA scan, manual address entry.
- **Bilingual** — French / English, selectable in *View → Language*.
- **Simulation / real parity** — faithful mocks (thermal model, loads, couplings).

## Getting started

```bash
pip install -r requirements-qt.txt    # Qt GUI — required, even in simulation
python3 main.py                        # starts in simulation (demo config + sequences)

pip install -r requirements.txt        # + REAL-HARDWARE drivers (pyvisa, nidaqmx)
python3 main.py --config config.json   # set "simulate": false in the JSON
```

A **demo configuration** and several **sequences** ship with the app: launch it, open
`sequences/demo.seq`, run — everything happens in simulation, no hardware. On first
launch the language follows the system locale (English fallback); change it under
*View → Language*.

> **Windows**: `ALIM_SEQ-Setup.exe` installer in the
> [Releases](https://github.com/Anoryth/ALIM_SEQ/releases) (starts in simulation, no
> dependency to install).

## Documentation

- **[User manual](docs/USER_MANUAL.md)** — full usage (also in the app:
  *Help → User manual*, `F1`). *(French: [Manuel utilisateur](docs/MANUEL_UTILISATEUR.md))*
- **[Architecture](docs/ARCHITECTURE.md)** — internals (threads, safety, data flow).
- **[Developer guide](docs/DEVELOPMENT.md)** — picking up the code: setup, recipes,
  pitfalls.
- **[Integrate a device driver](docs/GUIDE_DRIVERS.md)** ·
  **[Contributing](CONTRIBUTING.md)** · **[Changelog](CHANGELOG.md)**.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest                       # the whole suite, in simulation (no hardware, no network)
```

## License

**GNU General Public License v3.0** — see [LICENSE](LICENSE). You are free to use,
study, modify and redistribute; any distributed version stays **open** under the same
license and is provided **without any warranty**.
