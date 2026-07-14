# Changelog

All notable changes to ALIM_SEQ are recorded here.
Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning [SemVer](https://semver.org/).

## [1.3.1] — 2026-07-14

### Added
- **Bilingual interface (English / French).** The whole application is now
  internationalized with **English as the base language** and French provided via
  translation catalogs. The language is selectable at runtime via *View → Language*
  (persisted, default = system locale, English fallback). GUI strings go through Qt
  `tr()` (`.ts`/`.qm`), the non-Qt domain layer through gettext (`alim_seq/i18n.py`,
  `.po`/`.mo`); the test report and its charts, logs, and all error messages are
  localized (decimal separator follows the language). Tooling: `tools/build-i18n.sh`
  (extract + compile) and `tools/compile_catalogs.py` (compile-only, cross-platform,
  used by the Windows CI). Documentation is English-canonical; the README and user
  manual are bilingual (`README.md`/`README.fr.md`,
  `docs/USER_MANUAL.md`/`docs/MANUEL_UTILISATEUR.md`).

## [1.3.0] — 2026-07-13

### Added
- **Demo configuration and sequences** shipped by default: a complete simulation
  scenario (rails, series group, thermal sensor, gate→drain coupling for the SERVO,
  relay) and several sequences (`demo.seq`, `servo_bias.seq`,
  `balayage_polarisation.seq`, `arret.seq` — orderly shutdown) to discover the tool
  immediately.
- **Configuration wizard** (on first launch, or *File → Configuration wizard…*):
  **simulation** path (config without hardware), **VISA scan** (USB-TMC / LAN VXI-11)
  or **manual address entry** — essential for the **LAN socket mode**
  (`::5025::SOCKET`) that a scan cannot discover: the address is tested (`*IDN?`) then
  added. Generates `supplies` + pre-filled channels, loaded into the editor for review
  before applying. New `psu.probe_instrument`.
- **Test replay** (*File → Reopen a test*): a window replaying the curves of a
  `logs/essais/…` folder — Temperatures/Currents/Voltages toggle, value **read
  cursor**, numbered **event markers** (📌 markers, warnings, safety), PNG export and
  PDF report generation. The application becomes an **analysis** tool, not just a
  recorder.
- **Comparison of two tests** (*File → Compare two tests*): overlays the curves of two
  folders (aligned on t=0, series `A·`/`B·`, one color per series) to visualize a
  **before/after drift** after a change to the board.
- **Two-step switch-on (real hardware)**: in real mode, the 1st click on ON shows "⚠
  Arm?", a 2nd click (within 3 s) switches on — a net against the unfortunate click.
  Direct in simulation; `Shift+click` forces immediate switch-on.
- **Stale-state indicator**: when a channel's instrument stops responding (frozen
  link), its measured V/I are **greyed out** and the mode shows "⏱ frozen" — no more
  "ghost OFF" nor a frozen measurement passing as live (complements the timeout-locked
  V/I loop fix).
- **Operator marker (📌 / Ctrl+M)**: places a timestamped note in the log, reused as a
  vertical marker on the real-time chart **and** as a numbered badge in the test report
  ("this is where…").
- **Live lint of the sequence editor**: validation as you type (300 ms debounce), ✓/✗
  status and **red underline of the faulty line**, without waiting for the "Check"
  button.
- **GUI smoke tests** (`tests/test_gui_smoke.py`): an offscreen test net on the
  construction, tabs, refresh and key interactions of the GUI.

### Changed (technical)
- **Decomposition of `controller.py`** (god object, 1830 → 1479 lines) into **mixins**,
  **safety core intact**: extraction of CSV/test-folder recording
  (`controller_recording.py`), servo control (`controller_servo.py`) and simulated
  couplings + live tuning (`controller_simtune.py`). Pure code move (same `self`
  state), zero behavior change.

### Fixed / safety
- **Network safety** note added to the manual (SCPI/TCPIP without authentication →
  isolated bench).
- `stop_polling` only joins threads that actually started (guard `t.ident`) —
  robustness if a `start()` fails.

## [1.2.1] — 2026-07-12

### Security
- **Thermocouples: fault detection.** An emf outside the NIST polynomial's validity
  range (floating input, rail, saturated amplifier) now returns **NaN → FAULT** instead
  of an extravagant but "numeric" temperature. Validation **requires**
  `valid_min`/`valid_max` for a thermocouple (the only software net against a
  disconnected TC — an open TC reading ~0 V stays undetectable in software: documented
  limitation, prefer a module with *open-TC detect*).
- **Emergency stop: relays set to the safe state AFTER arming the trip** — a concurrent
  relay closing can no longer slip between the isolation and the locking; `set_relay`
  also re-checks the trip under the instrument lock.

### Fixed
- **Validation: temperature converters are built as soon as the configuration is
  loaded** — an aberrant parameter (`alpha=0`, `beta=0`, missing key, empty table…) is
  refused at validation instead of causing an error (up to a `ZeroDivisionError`) at
  the **first measurement**, in the safety loop.
- **Test folders: collision guard.** Two tests started in the same second (fast
  stop/start) shared the same folder and the second one **overwrote** `mesures.csv`.
  `_2`, `_3`… suffix + atomic creation.
- **V/I measurement loop: no more silent blocking.** Each supply's lock is acquired
  **with a timeout**: a frozen VISA link (dead socket) no longer blocks the reading of
  the other supplies nor the whole loop — the unavailable supply is skipped (last
  values kept, no false 0 V in the CSV) and the anomaly logged.
- **Serialized reconnection**: the watchdog (`auto_reconnect`) and the "Reconnect"
  button could rebuild the instruments **at the same time**; the second request is now
  cleanly refused.
- **Sequences: `!=` operator accepted** (`WAIT_CURRENT`/`WAIT_TEMP`) — the editor help
  announced it but validation refused it; `==` documented everywhere.
- **Relay GUI: no more "ghost OFF"** — the display reuses the last successful reading
  when the instrument lock is momentarily busy.
- **Config editor: an output "closed at shutdown" absent from the Outputs column** is
  added to the outputs instead of being silently ignored.

## [1.2.0] — 2026-07-12

### Added
- **GUI — Simulation tab (live tuning).** In simulation mode, a **🧪 Simulation** tab
  lets you tune **live** the resistive loads per channel, the thermal model (ambient,
  °C/W gain, time constant, noise) and the gate→drain couplings (gm, vth, imax), with
  an immediate effect visible in the *Control* tab. Controller primitives
  `sim_params`/`sim_set_load`/`sim_set_thermal`/`sim_set_couplings` (applied to the
  mocks and to `cfg.simulation`, hence kept across reconnect; no effect outside
  simulation). Goal: faithfully reproduce a setup's behavior without hardware.
- **GUI — relay support.** *Control* tab: a **Relays** frame with each output's state
  and an ON/OFF button (same guards as the channels: closing refused under armed
  safety, commands frozen during a (re)connection). *Configuration* tab: a **Relays**
  sub-tab to declare relay instruments and their outputs (including the safe state).
  Help/completion of the `RELAY` command in the sequence editor.
- **Configuration — merge of `instruments` + `supplies`/`daq`.** A config can combine
  sources described in `supplies` (legacy) AND instruments in `instruments` (e.g.
  relays) without one masking the other: both are merged
  (`AppConfig.__post_init__`), explicit `instruments` entries taking precedence.
- **Relay / actuator control** (`Actionneur` capability). New driver
  `alim_seq/relay.py` (`BaseRelay`/`MockRelay`). A relay is declared as an instrument
  of the `instruments` section (driver `MOCK-RELAY`) with its `outputs`; each output
  has a `safe_state` (default OFF/open). New sequence command **`RELAY <output>
  ON|OFF`**; controller primitives `set_relay`/`relay_state` and states exposed in the
  `snapshot`. Relays **take part in the safety power-down**: they are brought back to
  their `safe_state` on the emergency stop and at the end of an orderly power-down
  (opening a relay isolates the board). The `MockRelay` serves the simulation and as a
  "virtual" relay as long as no hardware model is wired.
- **Configuration: unified `instruments` section.** The device chain can now be
  described in a single `instruments` section (each entry: a `driver` + its
  parameters), without presuming categories. The historical `supplies`/`daq` sections
  stay accepted (**backward-compatible sugar**): `instruments` is authoritative and
  both views are kept consistent (`AppConfig.__post_init__`). Existing `config.json`
  and test configs reload without modification.

### Changed (technical)
- **Capability-based device abstraction — phases 1 to 3** (structuring, no behavior
  change). New module `alim_seq/instrument.py`: an `Instrument` (lifecycle
  `connect`/`close` + identity) declares the **capabilities** it exposes —
  `SourceTension` (voltage + current limit), `MesureVI`, `MesureTemperature`,
  `Actionneur` — instead of being frozen as a "supply" or "DAQ". The existing drivers
  adopt these capabilities (`BasePSU` → `SourceTension`+`MesureVI`, `BaseDAQ` →
  `MesureTemperature`) and a **unified registry** `INSTRUMENTS` / `create_instrument`
  generalizes `PSU_MODELS`/`create_psu`. The **controller** is generalized: one **lock
  per instrument** (`_instr_locks`, replaces `_psu_locks`+`_daq_lock`, invariant order
  widened to the alphabetical order of names), control and loops **by capability**,
  centralized label→(instrument, channel) routing; `PSUManager` is **removed**. The
  controller now builds its instruments from the `instruments` section (each entry
  classified by capability via its `driver`), which will allow adding relays without
  touching the core. Prepares the modularity of the device chain.

### Changed
- **Removal of the Tkinter GUI.** The **Qt (PySide6)** interface becomes the only GUI:
  `alim_seq/gui.py` is removed and the `--gui` option disappears (the application
  always launches Qt). Consequence: PySide6 is now required to launch the application,
  including in simulation — the **tests**, however, require no GUI (they drive the
  `Controller` directly). Goal: remove the maintenance entropy of two interfaces and
  prepare the modularization of the devices.

## [1.1.2] — 2026-07-11

### Changed
- **Test report — readability and layout overhaul.**
  - **Charts**: fixed, validated categorical palette (one channel = one color on the V
    and I panels), status colors reserved for the thresholds (warning/critical) and the
    trip, and above all a **numbered-badge event strip with anti-collision** replacing
    the labels that overlapped and made the chart unreadable. Title renamed
    "Measurements during the test".
  - **PDF layout**: **one page per part**, centered full-width tables with colored
    headers and zebra stripes, paginated "page X / N" footer, running header (test
    name), legend notes below the tables. "Excursions" column clarified.

### Changed (technical)
- **PDF generation: move from Qt (`QTextDocument`/`QPdfWriter`) to ReportLab** (pure
  Python). The report no longer depends on PySide6: the data layer stays testable
  without a dependency, `construire_html` remains for the browser preview, and the
  charts are still plotted by matplotlib (Agg backend). New dependency `reportlab`
  (bundled at PyInstaller build).

## [1.1.1] — 2026-07-06

### Fixed
- **Report: missing matplotlib fonts on the installed build.** The `mpl-data`
  slimming kept only the DejaVu Sans font, which broke the rendering of the report
  charts ("fonts are missing"). **All** the `fonts/ttf/` fonts are now bundled (the
  ~2 MB saving did not justify the regression). Validated on real hardware.

## [1.1.0] — 2026-07-05

### Added
- **Enriched test report** (`rapport.py`):
  - log events (sequence `LOG` messages, warnings, safety events) **materialized on the
    curves** V/I and temperatures, aligned on the CSV time axis;
  - **zoom chart on the safety trip** (±30 s window around the trip, offending sensor
    in a thick line, warning/critical thresholds, shaded critical zone);
  - **enriched statistics**: time in current limiting (CC) per channel (in s and %),
    start/end setpoints; temperature excursions (number of warning crossings, cumulated
    durations above warning and critical); a summary line (points, actual rate, CSV
    size);
  - **layout**: logo in the header, **paginated footer**, operator sign-off area,
    readable configuration appendix (channel/sensor tables before the raw JSON).
- **Build toolchain**: building the executables via a self-hosted CI (Forgejo +
  **on-demand** Windows VM), single command `tools/lab-build.sh <tag>`, documentation
  in `docs/ARCHITECTURE.md`.
- **Built-in help**: user manual viewable in the application (**F1** key) and provided
  as `.md`/`.docx`/`.pdf` (`docs/`).

### Changed
- **Slimmed build** (`packaging/ALIM_SEQ.spec`): move to **onedir** and targeted
  exclusions — matplotlib **Agg backend** only, no tkinter or software OpenGL, useless
  Qt translations and plugins removed, `mpl-data` filtered (DejaVu Sans font kept).
  **≈ −23 %** (180.7 → 139.2 MiB), installer ≈ 46 MB. Details and validation checklist:
  `packaging/OPTIMISATION.md`.
- Shipped configuration made **neutral** (generic channels `CH1`/`CH2`, startup in
  **simulation**), single example sequence.

## [1.0.0] — 2026-07-05

First complete version.

### Security
- Decoupled thermal monitoring (fast loop): **non-interruptible orderly power-down** at
  the critical threshold, last-resort **hard cut-off** (`critical + margin`, or time
  budget exceeded), **per-device locks** serializing instrument accesses, locked
  **"trip"** state and deliberate **rearm**.
- Disconnected-sensor detection (voltage stuck to a rail → FAULT), HMP hardware faults
  (OVP / fuse / overtemperature), communication losses.

### Qt GUI
- Permanent safety bar (emergency stop, shutdown sequence, rearm, all OFF), **mode
  badge** SIMULATION / REAL HARDWARE, light/dark themes, inputs **bounded** by the
  configuration, **background hardware workers** (no GUI freeze), sequence editor with
  check and auto-completion, chart tab (temperatures / currents / voltages).

### Traceability
- **Self-contained test folders** (`logs/essais/…`: `mesures.csv`, configuration copy,
  sequence, log, metadata + test outcome) and a **regenerable HTML/PDF test report**
  from the folder alone.
