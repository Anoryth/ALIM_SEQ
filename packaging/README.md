# Windows installer — ALIM_SEQ

Produces two deliverables:

- **`dist\ALIM_SEQ.exe`** — **portable** executable (single file, Qt GUI, no Python
  installation required).
- **`packaging\Output\ALIM_SEQ-Setup.exe`** — **installer** with Start menu / desktop
  shortcuts and an uninstaller.

## Admin / non-admin choice
The installer asks for the install mode at startup:

- **All users** (**admin** rights) → installed in *Program Files*;
- **This user only** (**no admin**) → installed in `%LOCALAPPDATA%\Programs`.

In both cases, the **edited configuration and the logs** are written in a per-user
**writable** folder: `%LOCALAPPDATA%\ALIM_SEQ` (seeded on first launch with the default
`config.json` and `sequences/`). A read-only installation (Program Files) therefore
works without any issue.

## Building (recommended: CI, on a real Windows)
The **GitHub Actions** workflow [`.github/workflows/windows-build.yml`](../.github/workflows/windows-build.yml)
builds everything on `windows-latest` and publishes the artifacts:
- run *Actions → Build Windows installer → Run workflow*, or push a `vX.Y.Z` tag.

## Building locally (Windows)
Requirements: **Python 3.10+** and **Inno Setup 6** (https://jrsoftware.org/isdl.php).
```bat
packaging\build_windows.bat
```
(installs PySide6/pyvisa/pyinstaller in a venv, runs PyInstaller then Inno Setup.)

## Notes
- **NI-DAQmx** (temperature acquisition in real mode) is **not** bundled: it requires
  the NI runtime installed separately. The app starts and works without it (NI
  acquisition is then unavailable, with an explicit message).
- VISA: `pyvisa` + `pyvisa-py` (pure Python) are included. For better hardware
  performance, install a system VISA (NI-VISA / Keysight IO Libraries).
- Translations: the compiled catalogs (`.qm`/`.mo`) are bundled; run
  `python tools\compile_catalogs.py` before building (the CI does this automatically).
- Icon: drop `packaging\icon.ico` to customize the exe (optional).
