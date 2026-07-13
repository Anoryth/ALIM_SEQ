# Installateur Windows — ALIM_SEQ

Produit deux livrables :

- **`dist\ALIM_SEQ.exe`** — exécutable **portable** (un seul fichier, IHM Qt, aucune
  installation de Python requise).
- **`packaging\Output\ALIM_SEQ-Setup.exe`** — **installateur** avec raccourcis
  menu Démarrer / bureau et désinstallateur.

## Choix admin / sans droits admin
L'installateur demande au démarrage le mode d'installation :

- **Tous les utilisateurs** (droits **admin**) → installé dans *Program Files* ;
- **Cet utilisateur uniquement** (**sans admin**) → installé dans
  `%LOCALAPPDATA%\Programs`.

Dans les deux cas, la **configuration éditée et les journaux** sont écrits dans un
dossier **inscriptible** par utilisateur : `%LOCALAPPDATA%\ALIM_SEQ` (semé au
premier lancement avec `config.json` et `sequences/` par défaut). L'installation
en lecture seule (Program Files) fonctionne donc sans souci.

## Construire (recommandé : CI, sur un vrai Windows)
Le workflow **GitHub Actions** [`.github/workflows/windows-build.yml`](../.github/workflows/windows-build.yml)
construit tout sur `windows-latest` et publie les artefacts :
- lancer *Actions → Build Windows installer → Run workflow*, ou pousser un tag `vX.Y.Z`.

## Construire en local (Windows)
Prérequis : **Python 3.10+** et **Inno Setup 6** (https://jrsoftware.org/isdl.php).
```bat
packaging\build_windows.bat
```
(installe PySide6/pyvisa/pyinstaller dans un venv, lance PyInstaller puis Inno Setup.)

## Notes
- **NI-DAQmx** (acquisition température en mode réel) n'est **pas** embarqué : il
  requiert le runtime NI installé séparément. L'app démarre et fonctionne sans
  (l'acquisition NI est alors indisponible, message explicite).
- VISA : `pyvisa` + `pyvisa-py` (pur Python) sont inclus. Pour de meilleures perfs
  matériel, installer une VISA système (NI-VISA / Keysight IO Libraries).
- Icône : déposez `packaging\icon.ico` pour personnaliser l'exe (optionnel).
