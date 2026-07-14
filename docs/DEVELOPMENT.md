# Developer guide — ALIM_SEQ

This document helps a **new developer** pick up the project: setup, tests,
conventions, and above all **step-by-step recipes** for common changes. To
*understand* the system (threads, safety, data flow), read
[ARCHITECTURE.md](ARCHITECTURE.md) first; to *use* it, see
[USER_MANUAL.md](USER_MANUAL.md). Building the executables (self-hosted CI) is
covered in §8.

---

## 1. Get going in 2 minutes

The **tests** require no GUI (they drive the `Controller` directly): Python 3.9+ is
enough. **Running the application**, on the other hand, requires the Qt GUI.

```bash
pip install -r requirements-dev.txt   # = pytest, pdoc
python -m pytest                      # the whole suite (simulation mode, no hardware)
python -m pytest tests/test_controller.py -v   # a single file, verbose
```

To launch the GUI (Qt) — required in all cases — and real hardware:

```bash
pip install -r requirements-qt.txt    # PySide6 + matplotlib + reportlab (GUI, charts, PDF)
python3 main.py                       # simulation by default ("simulate": true)

pip install -r requirements.txt       # pyvisa/nidaqmx (real hardware)
python3 main.py --config config.json  # 'simulate': false in the JSON
```

**The same code runs in simulation and on real hardware**: only the drivers change
(`MockPSU`/`MockDAQ` ↔ `HMP40xx`/`NIDaq`). Develop and test in simulation; use
hardware only for final validation.

---

## 2. Code map: where to find what

| Need | File |
|---|---|
| Add/validate a config field | [alim_seq/config.py](../alim_seq/config.py) |
| Device capabilities + unified registry | [alim_seq/instrument.py](../alim_seq/instrument.py) |
| Supply driver, model registry | [alim_seq/psu.py](../alim_seq/psu.py) |
| Temperature acquisition (NI / thermal mock) | [alim_seq/daq.py](../alim_seq/daq.py) |
| Relays / actuators (Actionneur capability) | [alim_seq/relay.py](../alim_seq/relay.py) |
| Voltage→°C conversion (NTC, PT100, table…) | [alim_seq/temperature.py](../alim_seq/temperature.py) |
| Sequence language (parser + runner) | [alim_seq/sequencer.py](../alim_seq/sequencer.py) |
| Orchestration, loops, safety (core) | [alim_seq/controller.py](../alim_seq/controller.py) |
| CSV recording / test folder (mixin) | [alim_seq/controller_recording.py](../alim_seq/controller_recording.py) |
| Servo control (mixin) | [alim_seq/controller_servo.py](../alim_seq/controller_servo.py) |
| Simulated couplings + live tuning (mixin) | [alim_seq/controller_simtune.py](../alim_seq/controller_simtune.py) |
| `SETV`/`SETI` expression evaluator | [alim_seq/expressions.py](../alim_seq/expressions.py) |
| Translation layer (domain, gettext) | [alim_seq/i18n.py](../alim_seq/i18n.py) |
| Test folder (CSV + artifacts) | [alim_seq/essai.py](../alim_seq/essai.py) |
| Test report (data, HTML, ReportLab PDF) | [alim_seq/rapport.py](../alim_seq/rapport.py) |
| Qt GUI (the only interface) | [alim_seq/gui_qt/](../alim_seq/gui_qt/) |
| Test fixtures | [tests/conftest.py](../tests/conftest.py) |

Layers (bottom → top): **drivers** (`psu`, `daq`) → **domain** (`config`,
`temperature`, `expressions`, `sequencer`) → **orchestration** (`controller`) →
**GUI** + **outputs** (`essai`, `rapport`). A lower layer never imports a higher one.
The core (`alim_seq/`) **does not depend on Qt** (testable and scriptable without a
GUI).

---

## 3. Conventions

- **Language / i18n.** The application is **bilingual (English / French)** with
  **English as the base language**; **configuration keys are in English**. User-facing
  strings are wrapped for translation — see §4.6. Documentation is English-canonical
  (the README and user manual are bilingual). Variable names and any not-yet-migrated
  comments may still mix French and English; follow the style of the file you edit.
- **Docstrings = the *why*.** The signature already says the *what*. A useful docstring
  explains the contract, the side effects (locks taken, threads), and the non-obvious
  decisions. Do not document a trivial getter or an interface stub (`...`): that would
  be noise.
- **Safety first.** Any change touching power must preserve the invariant: *the board
  is never left powered when something goes wrong*. When in doubt, cut off.
- **Threads and locks.** See §6 — it is pitfall #1. Never invert the lock acquisition
  order.
- **No new dependency without a reason.** Simulation mode must stay install-free. A
  heavy dependency (Qt, matplotlib) stays **optional** and lazily imported.

---

## 4. "How to add…" recipes

### 4.1 A new supply model

Everything goes through the **registry** of [psu.py](../alim_seq/psu.py). The rest of
the app (config, GUI, validation, simulation) adapts automatically.

1. Write a subclass of `BasePSU` (or of `HMP4040` if the same SCPI family). Implement
   `set_voltage/current/output`, `measure_voltage/current`, and preferably
   `measure_status` (CV/CC mode + faults). Set `n_channels`, `model`, and the SOA
   limits `max_voltage/max_current/max_power`.
2. Register it in `PSU_MODELS`:
   ```python
   PSU_MODELS = {..., "NGP804": NGP804}
   ```
3. That's all. `create_psu` builds a `MockPSU` (right channel count) in simulation and
   the real driver on hardware; config validation accepts the new model and checks the
   channels/limits.
4. Add a test in [tests/test_psu.py](../tests/test_psu.py).

### 4.2 A new temperature converter

In [temperature.py](../alim_seq/temperature.py):

1. Subclass `TemperatureConverter`, implement `to_celsius(voltage) -> float`. **Fault
   convention**: if the measurement is not trustworthy (disconnected sensor, voltage
   stuck to a rail), return `float("nan")` — the controller classifies it as `FAULT`
   and excludes it from safety (never a falsely plausible value).
2. Register it in `_CONVERTERS` (factory lambda reading the config dict):
   ```python
   _CONVERTERS["my_type"] = lambda c: MyConverter(param=c["param"])
   ```
3. If config guard rails are needed (e.g. a mandatory plausibility band), add them in
   `_validate` of [config.py](../alim_seq/config.py).
4. Test in [tests/test_temperature.py](../tests/test_temperature.py).

### 4.3 A new sequence command

In [sequencer.py](../alim_seq/sequencer.py), a command lives in **three** places:

1. **Validation** — add a case in `_validate_action` (argument count via `_need`,
   labels via `_check_label`, numbers via `_num`, `key=value` keys via `_check_kwargs`
   with a whitelist). *A validated sequence must never fail midway for a syntax error.*
   Error messages are wrapped in `_(…)` (see §4.6).
2. **Execution** — add a case in `SequenceRunner._execute`, routing to a `Controller`
   primitive. Return `True` (success, continue) or `False` (failure/interruption). For
   any wait, use `self._sleep()` (interruptible) and check `self._aborted()`.
3. **Documentation** — update the module header docstring (grammar), Appendix A of the
   manual, and the app's built-in help.

### 4.4 A new relay model (or any new actuator)

The **capability-based** abstraction ([instrument.py](../alim_seq/instrument.py))
makes the addition local: the core (locks, loops, safety) is untouched.

1. Subclass `BaseRelay` in [relay.py](../alim_seq/relay.py): implement `connect/close`,
   `set_state(label, on)`, `get_state(label)`. Set `model`.
2. Register it: add the driver name to `_RELAY_DRIVERS` and build it in
   `create_instrument` (actuator branch) of
   [instrument.py](../alim_seq/instrument.py) — mock in simulation, real driver on
   hardware (parity). Also add it to `available_instruments()` and the `INSTRUMENTS`
   dict.
3. That's all. The config declares it in `instruments` (`{"driver": "<NAME>",
   "outputs": {…}}`), the sequencer (`RELAY`), the controller (`set_relay`, safe
   state) and the `snapshot` handle it automatically.
4. Test in [tests/test_relay.py](../tests/test_relay.py).

For an **entirely new capability** (neither source, temperature, nor actuator), define
a thin mixin in `instrument.py`, expose it via `driver_role`, and have the controller
iterate `isinstance(instr, MyCapability)` where relevant — without breaking the lock
ordering invariant (§6).

### 4.5 A new configuration field

In [config.py](../alim_seq/config.py):

1. Add the field to the relevant `@dataclass` (with a default value → backward
   compatibility of existing configs).
2. Read it in `load_config` (`raw.get("...", default)`, with a type conversion).
3. Write it in `config_to_dict` (exact mirror: *what load reads, dict must write*, so
   that a test's config archive reloads identically).
4. Validate it in `_validate` if constraints apply.
5. Test in [tests/test_config.py](../tests/test_config.py).

### 4.6 A translatable string (i18n)

The app is bilingual; every user-facing string must go through a translation function.
Two catalogs, one per layer:

- **GUI** (`alim_seq/gui_qt/*`) — use `self.tr("English text")` inside a `QObject`
  (windows, mixins on the main window). For a non-`QObject` helper (plain classes,
  module functions), use `QtCore.QCoreApplication.translate("Context", "English
  text")`. ⚠ Do **not** alias `QCoreApplication.translate` (`tr = ...`): `lupdate`
  cannot follow the alias and mis-extracts the string — call it fully.
- **Domain layer** (non-Qt: `controller`, `rapport`, `sequencer`, `config`…) — import
  `from .i18n import _` and wrap with `_("English text")`. For interpolation, wrap the
  template and `.format()` afterwards: `_("Channel {} {}").format(label, state)`.

Do **not** wrap technical tokens (config/JSON keys, CSV headers, SCPI, `"ON"/"OFF"`
values that are not shown as labels). After adding or changing strings:

```bash
tools/build-i18n.sh        # extract (lupdate/xgettext) + compile FR catalogs
```

Then fill the French translations in `alim_seq/gui_qt/i18n/alim_seq_fr.ts` (Qt
Linguist) and `alim_seq/locale/fr/LC_MESSAGES/alim_seq.po`, and re-run the script to
recompile. `python tools/compile_catalogs.py` compiles only (cross-platform, no bash/
gettext — used by the Windows CI). The compiled `.qm`/`.mo` are git-ignored.

Note: `journal.log` is written in the runtime language, so the report's event parsing
(`rapport.py`) keys off the language-independent `!!!` prefix plus a bilingual keyword
set — keep that when adding safety log messages.

---

## 5. Tests

- The suite runs **exclusively in simulation** (mocks): no hardware, no network.
- The fixtures are in [tests/conftest.py](../tests/conftest.py): a config built **in
  code** (independent of `config.json`) covering the tricky cases — negative channel,
  series group, group spanning two supplies, gate→drain coupling, channel-conditioned
  sensor.
- The tests' controller is connected but **polling stopped** for full determinism (no
  background threads interfering).
- pytest config: [pytest.ini](../pytest.ini).

Write a test for any business behavior or safety fix. Match the existing style (shared
fixtures, one file per module). Assertions on user-facing strings use the **English**
base text (the translation fallback returns English when no catalog is loaded).

---

## 6. Pitfalls to know (⚠️ read before touching the controller)

- **Lock ordering — invariant.** One `RLock` **per instrument** (`_instr_locks[name]`,
  supplies and the temperature instrument) + one for the state. Acquisition order is
  **always**: `instrument lock(s) (alphabetical by name) → _state_lock`. Inverting it
  can deadlock. For a group / a multi-supply action, use the `_lock_for(label)` context
  manager (locks all sorted supplies); `_all_instr_locked()` locks all instruments
  (connect/reconnect/close).
- **The safety loop takes NO source lock.** It only locks the temperature instrument,
  so a frozen VISA on a supply can never delay a cut-off.
- **Two independent loops.** Temperature (fast, safety) and V/I (slow, display) run
  separately. Do not merge them.
- **The safety power-down takes precedence over everything.** It runs even with the
  lock armed, ignores the user stop and the pause. Do not "fix" this behavior.
- **Signed voltage vs magnitude.** The software reasons in **signed** voltages
  (negative rail = negative value); only the **magnitude** is programmed on the HMP
  (which only outputs positive). The `_clamp` clamp respects the polarity.
- **`config_to_dict` is the mirror of `load_config`.** If you add a field to one, add
  it to the other, otherwise a test's config archive diverges.

---

## 7. API documentation (pdoc)

The code docstrings generate a **navigable HTML doc** via [pdoc](https://pdoc.dev)
(lightweight, no configuration):

```bash
pip install -r requirements-dev.txt   # includes pdoc
tools/build-apidoc.sh                  # -> docs/api/index.html
# or directly:
python -m pdoc alim_seq -o docs/api
python -m pdoc alim_seq                # live server at http://localhost:8080
```

`docs/api/` is a regenerable artifact (git-ignored). Regenerate it after a notable API
change.

**User manual.** The single sources are [USER_MANUAL.md](USER_MANUAL.md) (English) and
[MANUEL_UTILISATEUR.md](MANUEL_UTILISATEUR.md) (French), which also serve the built-in
**F1** help (in the current language). The `.pdf`/`.docx` formats are **regenerable**
artifacts (git-ignored) produced by `tools/build-manual.sh` (pandoc). The Windows
build embeds the `.pdf` if present: regenerate it before a build to ship an up-to-date
manual.

---

## 8. Building the Windows executables

The installer and portable exe are produced by a self-hosted CI (Forgejo + on-demand
Windows VM): `tools/lab-build.sh <tag>`, which triggers `pip → PyInstaller → Inno
Setup` (`packaging/ALIM_SEQ.spec` and `packaging/ALIM_SEQ.iss`). The detailed
build-box setup (SSH host, on-demand VM, secrets) is kept in an internal doc, not part
of the public repository.

---

## 9. Contribution cycle

1. Develop and **test in simulation** (`python -m pytest`).
2. Update the relevant docs: docstrings, this guide, ARCHITECTURE.md, the manual and
   the built-in help if visible behavior changes. If you touched user-facing strings,
   run `tools/build-i18n.sh` and fill the French catalogs (§4.6).
3. Validate on **real hardware** if the change touches a driver or the safety logic.
4. Update [CHANGELOG.md](../CHANGELOG.md).
5. Tag `v*` to trigger a build (see §8).
