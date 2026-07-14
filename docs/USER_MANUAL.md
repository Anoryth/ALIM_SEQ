---
title: "ALIM_SEQ — User manual"
subtitle: "R&S HMP4040 power-supply sequencer with thermal monitoring"
lang: en-US
---

*(Français : [MANUEL_UTILISATEUR.md](MANUEL_UTILISATEUR.md))*

## 1. Overview

ALIM_SEQ drives one or more Rohde & Schwarz laboratory power supplies (HMP4040,
HMP4030, HMP2030, HMP2020) and continuously monitors temperatures measured by a
National Instruments acquisition module. It provides:

- **manual control** of the channels (voltage, current limit, on/off);
- execution of **automatic sequences** written in a simple language (ramps, current
  servo control, conditional waits, loops);
- **thermal safety monitoring**: when a critical threshold is exceeded, the
  application powers down the board under test in an orderly way, with an abrupt
  cut-off as a last resort;
- **recording** of measurements (voltages, currents, temperatures) in CSV format, and
  generation of a **PDF test report**.

The application runs in two modes, permanently indicated by a badge:

| Badge | Meaning |
|---|---|
| **SIMULATION** (blue) | No hardware is driven. Supplies and sensors are simulated (with a thermal model). Recommended mode to learn, develop sequences and the configuration. |
| **REAL HARDWARE** (orange) | Orders are sent to the real supplies. |

The mode is set by the `simulate` key of the configuration file (§9). **At install
time, the application starts in simulation**: no hardware is required to explore it.

## 2. Safety instructions

> ⚠ **Read before any use on real hardware.**

- **Check the configuration before each test campaign**: voltage and current limits
  of each channel (`V max`, `I max`), warning and critical thresholds of the sensors.
  The application refuses any setpoint beyond these limits, but the configuration is
  authoritative — a wrongly filled limit protects nothing.
- **The EMERGENCY STOP button** is permanently visible, on every tab. It **cuts off
  all channels immediately and abruptly**, without confirmation, including during a
  sequence. Shortcut: `Ctrl+Shift+X`.
- **The safety power-down is not interruptible.** If a critical threshold is reached,
  the power-down sequence runs to completion; the "Stop sequence" button is ignored
  during this phase.
- After any safety incident, the application enters a **locked ("trip")** state: no
  channel can be switched back on before a deliberate **Rearm** (§8.3). Identify and
  fix the cause before rearming.
- The application is an aid, not a certified protection: it replaces neither the
  hardware protections (supplies' OVP/fuses), nor human supervision of a risky test.

## 3. Installation and launch

### 3.1 Installed version (Windows)

Install ALIM_SEQ with `ALIM_SEQ-Setup.exe`, then launch the application from the
Start menu or the created shortcut. On first launch, the application creates its
**data folder** — the one you chose during installation (by default
`Documents\ALIM_SEQ`) — and puts a sample configuration and sequence in it. **In that
folder** you will find:

```
<data folder chosen at install time>\
├── config.json     # the configuration (editable from the app)
├── sequences\       # your .seq sequences
└── logs\            # application log and test folders (measurements, reports)
```

This way the edited configuration, logs and tests **persist** even if the
application is installed read-only (Program Files). A **portable** version
(`ALIM_SEQ.exe`, no installation) also exists; it stores its data in
`Documents\ALIM_SEQ`.

### 3.2 From source (Python)

Requirements: Python 3.10+, then `pip install pyvisa PySide6` (and `nidaqmx` for NI
acquisition in real mode; not needed in simulation).

```
python main.py [options]

  --config PATH   Configuration file (default: config.json)
```

Examples:

```
python main.py
python main.py --config bench_A.json
```

The interface is **Qt** (PySide6); it is the application's only GUI. The language
follows the system locale on first launch (English fallback) and can be changed under
*View → Language*.

### 3.3 Connecting the instruments (real mode)

- **HMP supply — recommended link: LAN in socket mode**, VISA address of the form
  `TCPIP0::192.168.0.11::5025::SOCKET` (robust and fast).
- **USB: set the supply to TMC mode, never CDC** (supply menu). CDC / virtual serial
  port mode is very slow and causes desynchronizations. Address of the form
  `USB0::0x0AAD::0x…::<serial number>::INSTR`.
- If the supply returns "input protocol violation" errors, set `visa_query_delay:
  0.02` at the root of the configuration file.
- The **Scan** button of the Configuration tab lists the detected VISA instruments
  and their identification; **Test the connection** validates an address.

> **⚠ Network safety — isolated bench mandatory.** The SCPI/TCPIP protocol has **no
> authentication**: any host on the network can open a session and **drive the
> supplies in parallel** with the application (change a setpoint, switch a channel
> on), which invalidates the software's safety assumptions. Connect the instruments
> on an **isolated bench network** (VLAN or dedicated segment, with no gateway to the
> office network/Internet). Never expose a power supply on an open network.

## 4. Getting to know the interface

From top to bottom:

1. **Safety banner** — global state in color: OK (green), WARNING (yellow), CRITICAL
   (red), sensor FAULT (purple). Shows the offending sensor and the action in
   progress (power-down…).
2. **Vital command bar** — visible on every tab: **EMERGENCY STOP**, **Shutdown
   sequence** (manual orderly power-down), **Rearm**, **All OFF**, and the **mode
   badge** SIMULATION / REAL HARDWARE. The Rearm button turns orange when a rearm is
   needed.
3. **Tabs**:
   - **Control** — manual control, temperatures, sequence launch, recording;
   - **Configuration** — editing the configuration file (§9);
   - **Sequence editor** — writing, checking and running `.seq` files;
   - **Chart** — temperature, current and voltage curves.
4. **Status bar** — connection dot, current configuration file, actual measurement
   rate, total delivered power, REC indicator during a recording.

## 5. Quick start

*In simulation (`"simulate": true`), no hardware is required. The default shipped
configuration defines two generic channels `CH1` and `CH2`.*

1. Launch the application (or `python main.py`). Check the **SIMULATION** badge
   (blue).
2. **Control** tab: on channel `CH1`, enter a voltage in the "V setpoint" field (the
   wheel is deliberately inactive — type it or use the arrows). The field turns
   yellow: the entered setpoint is not applied yet.
3. Click **Apply** (or press `Enter` in the field). The yellow background disappears.
4. Click **OFF** — the button switches to **ON** (green): the channel delivers. The
   "V measured / I measured" columns come alive.
5. **Sequence editor** tab: open `sequences/demo.seq`, click **Check** (full check of
   the syntax, channels and values), then **Run**. Follow the progress (progress bar,
   current line highlighted in the editor).
6. Test the **EMERGENCY STOP** button: all channels drop, the state goes to "trip".
   Click **Rearm** to regain control.

## 6. Manual channel control

### 6.1 Channel table

Each row shows: the channel label, the voltage setpoint, the current limit, the
**Apply** button, the **ON/OFF** output button, the measurements (V, I) and the
regulation **mode**:

- **CV** (green): voltage regulation — normal operation;
- **CC** (red): the channel is in **current limiting** — the load requests more than
  the set limit. Check the setup or the limit;
- a purple mention indicates a supply hardware fault (OVP, fuse, overtemperature).

The setpoint fields are **bounded by the configuration**: you cannot enter a value
beyond the channel's `V max` / `I max`. Both comma and dot decimal separators are
accepted.

**Yellow background = setpoint entered but not applied.** The application never
overwrites an entry in progress; click **Apply** (or `Enter`) to send it.

**Two-step switch-on (real hardware).** To avoid an accidental switch-on, in real
mode the **1st click** on ON shows **"⚠ Arm?"**; a **2nd click** (within 3 s)
actually switches on. In simulation, switch-on is direct. `Shift+click` forces
immediate switch-on even in real mode. Switch-off is always immediate.

**⏱ frozen = stale measurement.** If a channel's instrument stops responding (frozen
link), its **measured V/I are greyed out** and the mode shows **"⏱ frozen"**: the
value shown is no longer refreshed (see also the banner on a communication loss).

### 6.2 Series channels (groups)

A **group** ties together several channels wired in **series**: the group voltage is
the sum of the members' voltages, the current is common. Wiring: "−" terminal of the
first channel to the "+" terminal of the next; the load connects between the "+" of
the first and the "−" of the last (HMP outputs are isolated, this setup is allowed).

A group is driven like a channel, by its name (in the GUI and in sequences). The
voltage split between members is configurable: **balanced** (`equal`) or **fill**
(`fill`, the first channel to its maximum then the next). The right-hand column
recalls the composition (e.g. `= VD1 + VD2`).

*(The default shipped configuration defines no group; declare them as needed in the
Configuration tab, §9.4.)*

### 6.3 Temperatures

The Temperatures area shows each sensor with its value, colored by state: green
(OK), yellow (≥ warning threshold), red (≥ critical threshold), purple (**FAULT**:
measurement out of the plausible range or disconnected sensor), grey ("pending": the
sensor is monitored only when its associated channels are on, see `Required
channels`, §9.5).

### 6.4 Relays

If the configuration declares relays (§9.6), a **Relays** frame appears: each output
shows its state (open/closed) and an **ON/OFF** button to drive it by hand. Relays
are also driveable in a sequence (`RELAY <output> ON|OFF`, §7) and are brought back
to their safe state on a shutdown. Closing a relay is refused while the safety is
armed.

### 6.5 Simulation tab (simulation mode only)

In simulation mode, a **🧪 Simulation** tab lets you tune the virtual bench's behavior
**live**, to faithfully reproduce your setup without hardware. The effect is
immediate in the *Control* tab:

- **Resistive loads** per channel (Ω): set the relation I = V/R (hence the measured
  current, and the transition into current limiting).
- **Thermal model**: ambient temperature, gain (°C per dissipated watt), time
  constant τ (rise speed) and measurement noise — to exercise monitoring and safety
  thresholds.
- **Channel couplings (gate → drain)**: add/remove couplings where a *gate* channel's
  voltage drives the current drawn on *drain* channels (`Id = gm·(Vg − vth)`, capped
  at `imax`) — to test servo control (SERVO). Without coupling, each channel is a
  plain resistive load.

These settings concern only the simulation and are applied immediately; they never
affect real hardware.

## 7. Automatic sequences

### 7.1 Principle

A sequence is a `.seq` text file: **one action per line**, executed top to bottom.
Empty lines and comments (`#` or `//`) are ignored. Keywords are case-insensitive;
channel and sensor names respect the configuration's case. The full command
reference is in **Appendix A** (also available in the app: Help → Sequence command
reference).

Commented example (illustrative — adapt the channel/sensor names to your
configuration):

```
# Gradual power-up
SET CH1 20 1.0           # setpoint 20 V, limit 1 A
ON CH1
RAMP CH1 0 20 5 50       # ramp 0 → 20 V over 5 s, 50 steps
WAIT 1
SERVO_ADAPT CH2 CH1 0.500 step=0.5 tol=0.005 timeout=30
LOG Bias point reached
WAIT_TEMP T1 < 60 timeout=120
ALL_OFF
```

### 7.2 Built-in editor

The **Sequence editor** tab offers: syntax highlighting (**unknown** channel names
**stay neutral** — typos stand out), auto-completion of commands, channels and
sensors, a clickable cheat sheet (inserts the command at the cursor), and the
estimated duration shown on load.

**Always click "Check" before running**: the check verifies the syntax, the
existence of the channels/sensors, the **numeric** validity of all arguments and the
servo keywords. A checked sequence will not stop midway because of a typo.

### 7.3 Run, pause, step-by-step

- **Run** launches the sequence in a dedicated thread: the interface stays available
  (monitoring, chart, emergency stop).
- The **progress** is shown in the Control tab; the current line is highlighted in
  the editor.
- **Pause / Resume** suspends the sequence between two actions.
- **Step-by-step mode**: check "Step-by-step" then use "Next step" to run the
  sequence action by action — valuable for tuning on real hardware. (This mode has no
  effect on a safety power-down.)
- **Stop** cleanly interrupts the sequence (channels stay in their current state). To
  cut everything: **All OFF** or the emergency stop.
- CSV recording can be started automatically with the sequence ("Record during the
  sequence" checkbox).

### 7.4 Expressions (SETV / SETI)

`SETV` and `SETI` accept an arithmetic formula:

```
SETV CH2 = (CH1/2) + 0.6
SETI CH1 = I(CH2) * 10
```

In an expression: a **channel name** evaluates to its **voltage setpoint**; available
functions: `V(x)` voltage setpoint, `Vmeas(x)` measured voltage, `Iset(x)` current
limit, `I(x)` measured current. Operators `+ - * /`, parentheses, and common
functions (`min`, `max`, `abs`). No other code is evaluated (deliberately restricted
language).

## 8. Thermal safety and incident handling

### 8.1 Monitoring

The safety loop reads temperatures at a fast rate (`temp_poll_interval`, 0.2 s by
default), independently of the V/I measurement loop. Each sensor has a **warning**
threshold and a **critical** threshold.

### 8.2 Reaction on a critical overshoot

1. **Orderly power-down**: the application runs the shutdown sequence —
   `sequences/shutdown.seq` if such a file exists (or the one designated by
   `safety.shutdown_sequence`), otherwise a channel-by-channel switch-off generated
   automatically (in the reverse order of the configuration, with a `shutdown_delay`
   between channels). This phase is **priority and non-interruptible**: it takes over
   the running user sequence and ignores the Stop button.
2. **Last-resort hard cut-off**: if the temperature keeps rising and reaches
   `critical + hard_margin_c` (15 °C by default), or if the orderly power-down fails
   or exceeds its time budget, **all outputs are cut off abruptly**.

The same orderly power-down can be triggered manually at any time by the **Shutdown
sequence** button.

### 8.3 "Trip" state and rearming

After an incident (critical, emergency stop, communication loss depending on the
configuration), the application is **locked**: any switch-on attempt is refused. The
**Rearm** button (highlighted in orange) unlocks it, after fixing the cause. The log
(bottom of the Control tab, and the `logs/alim_seq.log` file) details the incident
timeline.

### 8.4 Communication losses and faults

- **Supply loss** (after `comm_fail_limit` consecutive failures): safety cut-off,
  then automatic reconnection attempts. Outputs are **not** restored after
  reconnection.
- **Loss of temperature measurement** while channels are delivering: orderly
  power-down (configurable, `shutdown_on_temp_lost`).
- **Sensor in FAULT** (value out of the plausible range, disconnected sensor — an
  open circuit is detected, it never appears as a falsely low temperature): flagged
  in purple; optional power-down (`shutdown_on_sensor_fault`).
- **HMP hardware fault** (OVP, fuse, internal overtemperature): flagged on the
  channel; optional power-down (`shutdown_on_hw_fault`).

## 9. Configuration

### 9.0 Configuration wizard (quick start)

On **first launch**, the application offers a **wizard** (also available via *File →
Configuration wizard…*). Two paths:

- **Simulation configuration**: generates a config without hardware (one HMP4040,
  channels CH1/CH2) — ideal to discover the application.
- **Scan VISA hardware**: detects the connected supplies (USB-TMC, LAN VXI-11),
  offers to check the ones to include (editable name and model) and **generates
  `supplies` + channels** pre-filled.
- **Add a manual address**: ⚠ the scan **does not discover** supplies in **LAN socket
  mode** (`TCPIP0::IP::5025::SOCKET`, yet recommended §3.3) — there is nothing to
  enumerate without knowing the IP. Enter the address directly: it is **tested**
  (`*IDN?`) then added (or added without a test, on confirmation, to prepare an
  offline config).

The generated configuration is **loaded into the editor** (§9.2) for review: adjust
the names/limits/sensors, then **✓ Apply**. The wizard never drives the hardware
directly.

### 9.1 Configuration files (profiles)

The application works on the "document" model:

- the **current file** is shown in the status bar and in the Configuration tab;
- menu **File → Load a configuration**: switches to the chosen profile (the old file
  is not modified) and reconnects the hardware;
- **Save** (Configuration tab) writes to the current file;
- **File → Save configuration as…**: saves the current state to a new file, which
  becomes the working file;
- **Reopen the last profile at startup** option (menu), disabled by default; an
  explicit `--config` on the command line stays authoritative.

A typical use case: one profile per bench or per board under test (`bench_A.json`,
`proto2_board.json`…).

### 9.2 Supplies tab

One row per supply: **Name** (free), **Model** (HMP4040, HMP4030, HMP2030, HMP2020),
**VISA address** (§3.3). The **Scan** and **Test the connection** buttons help to
find and validate the address.

### 9.3 Channels tab

| Column | Role |
|---|---|
| Label | Working name of the channel (used everywhere: GUI, sequences, expressions) |
| Supply / Channel | Physical channel (supply + output number) |
| Negative rail | Check if the channel supplies a negative rail (display and terminals reversed) |
| Initial V / Initial I | Setpoints applied on connection (outputs **off**) |
| V max / I max | **Safety limits**: bounds of the entries and ceiling of any setpoint |

### 9.4 Groups tab

Declaration of series channels (§6.2): name, member channels, split (balanced /
fill), group limits (0 = automatic: sum of the V max, minimum of the I max).

### 9.5 Temperatures tab

| Column | Role |
|---|---|
| Name | Sensor name |
| NI channel | Analog input of the NI module (e.g. `ai0`) |
| Warning / Critical threshold (°C) | Monitoring thresholds (§8) |
| Required channels | The sensor is monitored only if these channels are on (avoids false alerts when the board is unpowered) |
| Plausible T min/max (°C) | Plausibility range: beyond → **FAULT** |
| Converter | Voltage → °C conversion (Appendix C). Double-click or "Converter…" button: graphical assistant with a response curve |
| Reference channel / Expected ref V / Tolerance | Optional check of a conditioning reference voltage (divider bridge…): out of tolerance → FAULT |
| NI input min/max (V) | Analog input range |

To use the application **with no temperature measurement at all** (and without the NI
module), leave the Temperatures section **empty**: no thermal loop, the NI module is
neither connected nor queried. This is the case of the default shipped configuration.

### 9.6 Relays tab

Declares **relays / actuators**: each instrument exposes **outputs** that can be
driven individually (by label).

| Column | Role |
|---|---|
| Instrument | Name of the relay instrument |
| Driver | Driver; only `MOCK-RELAY` (simulated relay) exists for now |
| Outputs | Output labels, comma-separated (e.g. `K1, K2`) |
| Closed at shutdown | Outputs left **closed** in the safe state (the others are open). Empty = all open |

The declared outputs appear in a **Relays** frame of the *Control* tab (state +
ON/OFF button) and are driveable in a sequence by `RELAY <output> ON|OFF`. On an
emergency stop and at the end of an orderly power-down, each output is brought back
to its safe state (opening a relay isolates the board). Closing a relay is refused
while the safety is armed.

### 9.7 Advanced tab (JSON)

Free editing of the full file, synced with the forms (the tab where the change is
made is authoritative on save). Reserved for keys that have no form: `safety`
(Appendix B), `daq` (NI device, rate), `simulation` (thermal model of the simulation
mode), `visa_query_delay`.

The **Check** button validates the whole; **Apply** saves then reconnects the
hardware with the new configuration (not possible during a sequence).

## 10. Chart and measurement recording

### 10.1 Chart

The **Chart** tab plots, over a sliding window: the **temperatures**, the
**currents** or the **voltages** ("Quantity" selector). Features: clickable legend
(hide/show a curve), **read cursor** on hover (value of each curve at the pointed
instant), sequence event markers, image and data export.

### 10.2 CSV recording and test folder

The **Record** button (or `Ctrl+R`, or the "Record during the sequence" checkbox)
starts a recording. A small optional dialog asks for the **test name** and the
**operator**. The **REC** indicator is shown in the status bar during recording.

Each recording creates a **self-contained test folder**:

```
logs\essais\YYYYMMDD_HHMMSS[_<name>]\
├── mesures.csv    # timestamp, setpoints and measurements (V, I) per channel, temperatures, safety state
├── config.json    # exact copy of the active configuration
├── sequence.seq   # executed sequence (absent for manual control)
├── journal.log    # controller events during the test
├── essai.json     # metadata: mode, timestamps, test outcome…
├── rapport.html   # regenerable report
└── rapport.pdf
```

The benefit: a third party can **regenerate the PDF report from this folder alone**,
without the application open on the test, including months later. The `mesures.csv`
(one line per measurement cycle, flushed live) opens in a spreadsheet or is processed
in Python/MATLAB.

### 10.3 Test report

The report includes a header, a **summary** (outcome in plain text and color — red
for a safety trip), the **operator conclusion** (optional free field, re-editable),
**charts** (V/I and temperatures with thresholds), **statistics** per channel and per
sensor, the **timeline** of events and **appendices** (sequence and configuration).
The report **issues no compliance verdict**: the conclusion is the operator's.

- **End of recording**: if the option *View → Generate the report at end of test* is
  checked (default), the conclusion is prompted then the report is generated.
- **Safety trip** with a test in progress: the report is generated **automatically**
  as soon as the power-down finishes.
- **On-demand regeneration**: *File → Generate a test report…* lists the folders of
  `logs\essais\` and regenerates with entry/editing of the conclusion. *Help → Where
  are my files?* opens `logs\essais\` in the file explorer.

### 10.4 Test replay

*File → Reopen a test (replay)…* replays a recorded test in a dedicated window:
**curves** of the whole test (toggle Temperatures / Currents / Voltages), value
**read cursor** on hover, numbered **event markers** (📌 markers, warnings, safety),
**clickable legend** (hide/show a curve), **PNG export** and a **Generate the PDF
report** button. Handy to analyze a test *after the fact*.

*File → Compare two tests…* **overlays** the curves of two tests (aligned on t = 0,
series prefixed `A·`/`B·`, one color per series) in a single view: ideal to visualize
a **before/after drift** after a change to the board. Quantity toggle and PNG export
as in replay.

## 11. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+X` | Emergency stop |
| `Ctrl+Enter` | Load and run the editor's sequence |
| `Ctrl+S` | Save the sequence |
| `Ctrl+O` | Open a sequence |
| `Ctrl+R` | Start / stop the CSV recording |
| `Ctrl+M` | Place an operator marker (timestamped note) |

(List also available in the application: Help → Keyboard shortcuts.)

## 12. Troubleshooting

| Symptom | Probable cause / remedy |
|---|---|
| "Connection failed" at startup | Check the VISA address (Scan / Test the connection), the cable, that the supply is in **TMC** mode if USB. The GUI stays usable during the attempts; **Reconnect** button after fixing. |
| Inconsistent measurements / "input protocol violation" | USB link in CDC mode (switch to TMC) or dialog too fast: set `visa_query_delay: 0.02`. |
| Channel shown **CC** in red | The load requests more than the current limit: check the setup, the setpoint or the limit. |
| Sensor shown **FAULT** (purple) | Measurement out of the plausible range: disconnected sensor, wiring, reference voltage out of tolerance. Check the conditioning; the detail is in the log. |
| Cannot switch a channel on | "trip" state after an incident: fix the cause then **Rearm**. |
| The Stop button does not respond during a power-down | Normal behavior: the safety power-down is not interruptible (§8.2). |
| "Stop the sequence first." | Rearming, reconnection and configuration change are blocked during a sequence: stop it first. |
| Setpoint cannot be entered | The value exceeds the channel's `V max` / `I max`: the bound is deliberate (configuration, §9.3). |
| Window slow to start in real mode | The connection is established in the background; hardware commands are greyed out meanwhile, the emergency stop stays active. |

For an unlisted problem, attach `logs\alim_seq.log` and the configuration file to any
report.

---

## Appendix A — Sequence command reference

One action per line. `#` and `//` introduce a comment. Keywords are case-insensitive;
channel/sensor labels are case-sensitive. `<channel>` denotes a channel **or a
group**.

| Command | Effect |
|---|---|
| `SET <channel> <V> [A]` | Voltage setpoint (and current limit) |
| `VOLTAGE <channel> <V>` | Voltage setpoint only |
| `CURRENT <channel> <A>` | Current limit only |
| `SETV <channel> = <expression>` | Voltage computed by a formula (§7.4) |
| `SETI <channel> = <expression>` | Computed current limit |
| `ON <channel>` / `OFF <channel>` | Switch the channel on / off |
| `WAIT <s>` | Pause (interruptible) |
| `RAMP <channel> <v_end> <duration_s>` | Ramp from the **current** value to `v_end` |
| `RAMP <channel> <v_start> <v_end> <duration_s> [n_steps]` | Ramp with explicit start. `n_steps` = **number of steps** (integer ≥ 2), not a step size |
| `SERVO_LIN <set> <measured> <I_target_A> [key=val …]` | Servo the *set* channel's voltage until the target current is reached on the *measured* channel, with **fixed step**. `SERVO` = alias |
| `SERVO_ADAPT <set> <measured> <I_target_A> [key=val …]` | Same with **adaptive step** (large step far from target, fine near it); `step` becomes a ceiling |
| `WAIT_CURRENT <channel> <op> <A> [timeout=<s>]` | Wait until the measured current satisfies the condition. `op` ∈ `<  <=  >  >=  ==  !=` |
| `WAIT_TEMP <sensor> <op> <°C> [timeout=<s>]` | Wait for a temperature condition |
| `LOG <message…>` | Write a message to the log (and the CSV) |
| `ALL_OFF` | Switch off all channels |
| `RELAY <output> ON\|OFF` | Close (ON) / open (OFF) a relay output |
| `SHUTDOWN` | Run the orderly power-down (§8.2) |
| `REPEAT <n>` … `END` | Repeat the block *n* times (nesting allowed) |

**Servo keywords**: `step` (step, V), `min` / `max` (voltage bounds, V), `tol`
(tolerance on the current, A), `timeout` (s), `settle` (settling time between steps,
s), `invert=1` (reversed action: the current decreases as the voltage rises), and
`damping` (damping, `SERVO_ADAPT` only, default 0.7).

## Appendix B — Safety parameters (`safety` in the configuration file)

| Key | Default | Role |
|---|---|---|
| `poll_interval` | 0.5 s | V/I measurement rate of the supplies |
| `temp_poll_interval` | 0.2 s | Rate of the thermal safety loop |
| `auto_shutdown_on_critical` | `true` | Orderly power-down at the critical threshold |
| `shutdown_sequence` | `null` | Path of a custom shutdown sequence; `null` → `sequences/shutdown.seq` if present, otherwise an automatically generated switch-off |
| `shutdown_delay` | 0.5 s | Delay between channels (automatic switch-off) |
| `hard_margin_c` | 15 °C | Margin beyond the critical threshold triggering the **hard cut-off** |
| `shutdown_takeover_wait_s` | 3 s | Maximum wait for the user sequence to stop before the power-down |
| `shutdown_timeout` | auto | Time budget of the orderly power-down; exceeded → hard cut-off |
| `comm_fail_limit` | 3 | Consecutive failures before declaring an instrument lost |
| `shutdown_on_temp_lost` | `true` | Power down if the temperature measurement is lost with channels on |
| `shutdown_on_sensor_fault` | `false` | Power down if a sensor goes to FAULT |
| `shutdown_on_hw_fault` | `false` | Power down on an HMP hardware fault (OVP, fuse, overtemperature) |

## Appendix C — Temperature converters

Each sensor converts the voltage read by the NI module into °C. Available types
(built-in graphical assistant, with a plot of the response curve):

| Type | Use |
|---|---|
| `identity` | The voltage **is** the temperature (conditioned sensor, e.g. 10 mV/°C with external gain) |
| `polynomial` | Polynomial `T = c0 + c1·V + c2·V² + …` (linear sensors like the LM35, or calibration) |
| `table` | Linear interpolation between calibration points (V, °C) |
| `ntc` | NTC thermistor (β or Steinhart-Hart model) in a divider bridge — parameters: nominal R, β, bridge R, reference voltage, bridge orientation |
| `ptc` | PTC/RTD probe (e.g. conditioned PT100/PT1000) in a divider bridge |
| `thermocouple` | Thermocouple (common types) with approximate cold-junction compensation |

For `ntc` and `ptc`, a measured voltage stuck to a rail (disconnected sensor, short
circuit) is detected and flagged as **FAULT** — never interpreted as an extreme
temperature. Also fill in `Plausible T min/max` (§9.5) as a belt-and-braces measure.

**⚠ Thermocouples — a limit to know.** An aberrant emf (floating input, rail,
saturated amplifier) is flagged as **FAULT** (result outside the polynomial's
validity range). However, a **broken thermocouple whose input reads ~0 V** is
*indistinguishable in software* from an object at ambient temperature: reliable
open-TC detection is **hardware** (acquisition module with *open-TC detect*). This is
why the configuration **requires** `Plausible T min/max` for a thermocouple — and for
critical monitoring, prefer a module with open detection or duplicate the sensor.

---
