# Contribuer à ALIM_SEQ

Merci de l'intérêt porté au projet. ALIM_SEQ est un **automate de test de banc sûr** :
la sûreté et la parité simulation/réel priment sur tout le reste.

## Par où commencer

- **Comprendre le système** : [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Reprendre le développement** : [docs/DEVELOPPEMENT.md](docs/DEVELOPPEMENT.md)
  (installation, tests, conventions, recettes pas-à-pas, **pièges à connaître**).
- **Brancher un nouvel appareil** : [docs/GUIDE_DRIVERS.md](docs/GUIDE_DRIVERS.md).
- **Utiliser l'application** : [docs/MANUEL_UTILISATEUR.md](docs/MANUEL_UTILISATEUR.md).

## Mise en route

```bash
pip install -r requirements-dev.txt      # pytest, pdoc
python -m pytest                          # toute la suite (simulation, sans matériel)
pip install -r requirements-qt.txt        # PySide6 + matplotlib + reportlab (IHM)
python3 main.py                           # lance l'app (simulation par défaut)
```

Le mode **simulation** fonctionne sans aucun matériel : développez et testez ainsi,
n'utilisez le matériel réel que pour la validation finale.

## Règles non négociables

1. **Sûreté d'abord.** Toute modification touchant la puissance doit préserver
   l'invariant : *on ne laisse jamais la carte alimentée en cas de problème*. En cas
   de doute, on coupe. La boucle thermique et l'ordre des verrous sont critiques —
   lire [DEVELOPPEMENT.md §6](docs/DEVELOPPEMENT.md) **avant** de toucher au contrôleur.
2. **Parité simulation / réel.** Tout driver réel a un mock ; la suite de tests tourne
   sans matériel ni réseau.
3. **Tests.** Écrivez un test pour tout comportement métier ou correctif de sécurité.
   La suite doit rester verte (`python -m pytest`).
4. **Docs.** Mettez à jour la doc concernée (docstrings, guides, `CHANGELOG.md`) quand
   le comportement visible change.

## Flux de contribution

1. Créez une branche à partir de `main`.
2. Développez et **testez en simulation**.
3. Validez sur **matériel réel** si vous touchez un driver ou la sécurité.
4. Mettez à jour [CHANGELOG.md](CHANGELOG.md).
5. Ouvrez une Pull Request décrivant le *pourquoi* (pas seulement le *quoi*) et, pour
   un driver, l'appareil ciblé et ce qui a été validé.

## Langue

Application, IHM et documentation en **français** ; les clés de configuration sont en
anglais. Respectez le style du fichier que vous modifiez.

## Licence

En contribuant, vous acceptez que votre contribution soit distribuée sous la licence
du projet, **GNU GPL-3.0** (voir [LICENSE](LICENSE)).
