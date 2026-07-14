# Contributing to ALIM_SEQ

Thanks for your interest in the project. ALIM_SEQ is a **safe bench-test automaton**:
safety and simulation/real parity come before everything else.

## Where to start

- **Understand the system**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Pick up development**: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
  (setup, tests, conventions, step-by-step recipes, **pitfalls to know**).
- **Wire a new device**: [docs/GUIDE_DRIVERS.md](docs/GUIDE_DRIVERS.md).
- **Use the application**: [docs/USER_MANUAL.md](docs/USER_MANUAL.md).

## Getting set up

```bash
pip install -r requirements-dev.txt      # pytest, pdoc
python -m pytest                          # the whole suite (simulation, no hardware)
pip install -r requirements-qt.txt        # PySide6 + matplotlib + reportlab (GUI)
python3 main.py                           # launch the app (simulation by default)
```

**Simulation** mode works without any hardware: develop and test that way, use real
hardware only for final validation.

## Non-negotiable rules

1. **Safety first.** Any change touching power must preserve the invariant: *the board
   is never left powered when something goes wrong*. When in doubt, cut off. The
   thermal loop and the lock ordering are critical — read
   [DEVELOPMENT.md §6](docs/DEVELOPMENT.md) **before** touching the controller.
2. **Simulation / real parity.** Every real driver has a mock; the test suite runs
   without hardware or network.
3. **Tests.** Write a test for any business behavior or safety fix. The suite must stay
   green (`python -m pytest`).
4. **Docs.** Update the relevant documentation (docstrings, guides, `CHANGELOG.md`)
   when visible behavior changes.

## Contribution flow

1. Create a branch off `main`.
2. Develop and **test in simulation**.
3. Validate on **real hardware** if you touch a driver or the safety logic.
4. Update [CHANGELOG.md](CHANGELOG.md).
5. Open a Pull Request describing the *why* (not just the *what*) and, for a driver,
   the targeted device and what was validated.

## Language

The application, GUI and documentation are **bilingual (English / French)** with
English as the base language; configuration keys are in English. User-facing strings
go through the translation catalogs (`tools/build-i18n.sh` — see
[DEVELOPMENT.md](docs/DEVELOPMENT.md)). Follow the style of the file you edit.

## License

By contributing, you agree that your contribution is distributed under the project
license, **GNU GPL-3.0** (see [LICENSE](LICENSE)).
