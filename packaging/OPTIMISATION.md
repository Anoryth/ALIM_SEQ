# Slimming the PyInstaller build

Goal: reduce the size of the Windows build (`dist/ALIM_SEQ/`, **onedir** mode) without
changing behavior. The application only uses **QtCore/QtGui/QtWidgets** and
**matplotlib Agg backend** (report charts). `matplotlib` is a **wanted** dependency;
only the strict minimum is bundled.

## Measurement method (reproducible)

```bash
# optimized build (default) then baseline, and comparison:
pyinstaller --noconfirm --clean packaging/ALIM_SEQ.spec
python packaging/taille_dist.py dist/ALIM_SEQ            # -> "after" sizes

ALIM_SLIM=0 pyinstaller --noconfirm --clean packaging/ALIM_SEQ.spec
python packaging/taille_dist.py dist/ALIM_SEQ            # -> "before" sizes (baseline)
```

`ALIM_SLIM=0` disables **only** the optional slimming described here (matplotlib
backends, `mpl-data` filtering, Qt DLLs/plugins); the base Qt exclusions (`_QT_HEAVY`:
WebEngine, Quick/Qml, Multimedia, Charts, QtNetwork, QtSql, QtPdf…) stay in both cases
(they were already validated on the onefile version).

The CI prints `taille_dist.py` on every build ("Build size report" step) and runs a
**startup canary** (the exe must launch in simulation without crashing — a guard
against an overly aggressive exclusion).

## Exclusion families (in `packaging/ALIM_SEQ.spec`)

| Family | What is removed | Why it is safe |
|---|---|---|
| **matplotlib backends** | all interactive backends and bridges (`backend_qtagg`, `qt5agg`, `qt6agg`, `tkagg`, `gtk*`, `wx*`, `macosx`, `webagg`, `nbagg`, `qt_compat`) | the code only imports `matplotlib.figure` + `FigureCanvasAgg`. `backend_agg` **kept**. |
| **tkinter** | `tkinter`, `_tkinter` | pulled in by the matplotlib hook (`backend_tkagg`); the packaged app is **Qt-only**. |
| **tests** | `matplotlib.tests`, `numpy.tests` | never run at runtime. |
| **mpl-data** | `sample_data/`, `fonts/pdfcorefonts/`, `fonts/afm/` | metrics of the PostScript/PDF backends (not used by Agg) + example datasets. **All `fonts/ttf/` fonts are kept**: keeping only DejaVu Sans broke matplotlib rendering on the installed build (v1.1.0 → fixed in 1.1.1). |
| **Qt modules** | `_QT_HEAVY` + `QtUiTools`; `QtPdf` excluded (⚠ `QPdfWriter` is in **QtGui**, verified); `QtNetwork` excluded (nothing pulls it) | already validated on the tested onefile version. |
| **Qt DLLs** | `opengl32sw.dll` (software OpenGL fallback), `d3dcompiler_47.dll` (D3D compiler) | the GUI does not use OpenGL. *If a lab machine has broken rendering with exotic drivers, put them back.* |
| **Qt translations** | `PySide6/translations/*` | these are Qt's own built-in dialog translations; the app ships its **own** catalogs (`.qm`/`.mo` under `alim_seq/`) and does not rely on Qt's standard-dialog localization. |
| **Qt plugins** | `imageformats` except **qico/qpng/qjpeg**; `multimedia`, `sqldrivers`, `qml`, `qmltooling`, `tls`, `networkinformation`, … | `.ico` icon (qico) + report PNGs (qpng/qjpeg). **Kept**: `platforms/` (qwindows **vital**), `styles/`, `iconengines/`. |

### Deliberate choices
- **UPX: NO.** UPX compresses the DLLs but causes **antivirus false positives** and
  breaks some Qt DLLs. The size saving is not worth the risk. `upx=False`.
- **numpy kept**: hard dependency of matplotlib.
- **onedir** (folder) rather than onefile: faster startup, no temporary
  self-extraction (fewer AV false positives), and a **measurable** size.

## Before / after measurements

Windows builds produced in CI (`taille_dist.py`). Baseline = `ALIM_SLIM=0`.

| | Baseline | Optimized | Saving |
|---|---|---|---|
| **Total `dist/ALIM_SEQ/`** | **180.7 MiB** (1999 files) | **139.2 MiB** (848 files) | **−41.5 MiB (~23 %)**, −1151 files |

> The measurement above was done in v1.1.0. In **1.1.1**, the full `mpl-data` font set
> (40 `.ttf`) is reintegrated ("missing fonts" fix): total **143.8 MiB**, so a net
> saving brought back to **~−20 %** (−36.9 MiB).

| Installer (`ALIM_SEQ-Setup.exe`, lzma2) | — | **≈ 46 MB** | (79 MB in onefile before slimming) |

Detail per family (subfolders of `_internal/`):

| Subfolder | Baseline | Optimized | Saving | Cause |
|---|---|---|---|---|
| `PySide6` | 90.3 MiB | 62.9 MiB | **−27.4 MiB** | `opengl32sw.dll` (~20 MiB) + `d3dcompiler_47.dll`, translations (97 `.qm`), useless plugins |
| `tcl`/`tk` (`_tcl_data`, `tcl86t.dll`, `tk86t.dll`, `_tk_data`) | ≈ 7.1 MiB | **0** | complete exclusion of **tkinter** (Qt-only app) |
| `matplotlib` (`mpl-data`) | 13.7 MiB | 7.3 MiB | **−6.4 MiB** | `afm`/`pdfcorefonts`/`sample_data` fonts + non-DejaVu `ttf` |

Unchanged (hard dependencies): `numpy.libs` (OpenBLAS, 20 MiB), `numpy`, `PIL`,
`python312.dll`, `libcrypto`. `PIL` (10.7 MiB) is pulled by matplotlib — a candidate
for later slimming (not done: not validated).

## Validation — Windows checklist (run on the installed version)

Slimming can break **silently** (the app starts but a peripheral function dies). To
validate after installation, on a real Windows:

1. **Startup**: the exe opens in **simulation** (blue badge), theme toggle (dark/light)
   OK, each tab opens (Control, Configuration, Editor, Chart). *(The CI canary already
   covers "the exe starts".)*
2. **Window icon present** in the taskbar and the title — **`imageformats` canary**
   (the `.ico` icon must load).
3. **Recording + sequence**: start a recording, run `demo.seq`, let it finish.
4. **Report**: generate the test report → the **PDF contains the charts** V/I and
   temperatures (**matplotlib / mpl-data exclusion canary**) and opens correctly, with
   readable text (DejaVu font).
5. **Language**: switch *View → Language* to English/French and restart — the UI must
   be fully translated (**canary for the bundled `.qm`/`.mo` catalogs**).
6. If the exe **no longer starts** after an exclusion: suspect `QtNetwork` (put it back
   and note it here). If **rendering is broken**: suspect a removed `imageformats`/
   `iconengines` plugin or an OpenGL DLL.
