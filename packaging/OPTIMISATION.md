# Dégraissage du build PyInstaller

Objectif : réduire la taille du build Windows (`dist/ALIM_SEQ/`, mode **onedir**)
sans changer le comportement. L'application n'utilise que **QtCore/QtGui/QtWidgets**
et **matplotlib backend Agg** (graphiques du rapport). `matplotlib` est une
dépendance **voulue** ; on n'embarque que le strict nécessaire.

## Méthode de mesure (reproductible)

```bash
# build optimisé (défaut) puis baseline, et comparaison :
pyinstaller --noconfirm --clean packaging/ALIM_SEQ.spec
python packaging/taille_dist.py dist/ALIM_SEQ            # -> tailles "après"

ALIM_SLIM=0 pyinstaller --noconfirm --clean packaging/ALIM_SEQ.spec
python packaging/taille_dist.py dist/ALIM_SEQ            # -> tailles "avant" (baseline)
```

`ALIM_SLIM=0` désactive **uniquement** le dégraissage de cette mission (backends
matplotlib, filtrage `mpl-data`, DLL/plugins Qt) ; les exclusions Qt de base
(`_QT_HEAVY` : WebEngine, Quick/Qml, Multimedia, Charts, QtNetwork, QtSql, QtPdf…)
restent dans les deux cas (elles étaient déjà validées sur la version onefile).

La CI imprime `taille_dist.py` à chaque build (étape « Rapport de tailles du build »)
et exécute un **canari de démarrage** (l'exe doit se lancer en simulation sans
planter — garde-fou contre une exclusion trop agressive).

## Familles d'exclusions (dans `packaging/ALIM_SEQ.spec`)

| Famille | Ce qui est retiré | Pourquoi c'est sûr |
|---|---|---|
| **matplotlib backends** | tous les backends interactifs et ponts (`backend_qtagg`, `qt5agg`, `qt6agg`, `tkagg`, `gtk*`, `wx*`, `macosx`, `webagg`, `nbagg`, `qt_compat`) | le code n'importe que `matplotlib.figure` + `FigureCanvasAgg`. `backend_agg` **conservé**. |
| **tkinter** | `tkinter`, `_tkinter` | aspirés par le hook matplotlib (`backend_tkagg`) ; l'app empaquetée est **Qt-only** (le launcher force `--gui qt`). |
| **tests** | `matplotlib.tests`, `numpy.tests` | jamais exécutés au runtime. |
| **mpl-data** | `sample_data/`, `fonts/pdfcorefonts/`, `fonts/afm/` | métriques des backends PostScript/PDF (non utilisés par Agg) + jeux d'exemple. **Toutes les polices `fonts/ttf/` sont conservées** : ne garder que DejaVu Sans cassait le rendu matplotlib sur le build installé (v1.1.0 → corrigé en 1.1.1). |
| **Qt modules** | `_QT_HEAVY` + `QtUiTools` ; `QtPdf` exclu (⚠ `QPdfWriter` est dans **QtGui**, vérifié) ; `QtNetwork` exclu (rien ne l'aspire) | déjà validé sur la version onefile testée. |
| **DLL Qt** | `opengl32sw.dll` (repli OpenGL logiciel), `d3dcompiler_47.dll` (compilateur D3D) | l'IHM n'utilise pas OpenGL. *Si un poste labo a un rendu cassé avec des drivers exotiques, les réintégrer.* |
| **Traductions Qt** | `PySide6/translations/*` | application monolingue, aucun `QTranslator`. |
| **Plugins Qt** | `imageformats` sauf **qico/qpng/qjpeg** ; `multimedia`, `sqldrivers`, `qml`, `qmltooling`, `tls`, `networkinformation`, … | icône `.ico` (qico) + PNG du rapport (qpng/qjpeg). **Conservés** : `platforms/` (qwindows **vital**), `styles/`, `iconengines/`. |

### Choix délibérés
- **UPX : NON.** UPX compresse les DLL mais provoque des **faux positifs antivirus**
  et casse certaines DLL Qt. Gain de taille non justifié face au risque. `upx=False`.
- **numpy conservé** : dépendance dure de matplotlib.
- **onedir** (dossier) plutôt que onefile : démarrage plus rapide, pas d'auto-
  extraction temporaire (moins de faux positifs AV), et taille **mesurable**.

## Mesures avant / après

Builds Windows produits en CI (`taille_dist.py`). Baseline = `ALIM_SLIM=0`.

| | Baseline | Optimisé | Gain |
|---|---|---|---|
| **Total `dist/ALIM_SEQ/`** | **180,7 Mio** (1999 fichiers) | **139,2 Mio** (848 fichiers) | **−41,5 Mio (~23 %)**, −1151 fichiers |

> Mesure ci-dessus faite en v1.1.0. En **1.1.1**, le jeu de polices `mpl-data`
> complet (40 `.ttf`) est réintégré (correctif « polices manquantes ») :
> total **143,8 Mio**, soit un gain net ramené à **~−20 %** (−36,9 Mio).
| Installateur (`ALIM_SEQ-Setup.exe`, lzma2) | — | **≈ 46 Mo** | (79 Mo en onefile avant la mission) |

Détail par famille (sous-dossiers de `_internal/`) :

| Sous-dossier | Baseline | Optimisé | Gain | Cause |
|---|---|---|---|---|
| `PySide6` | 90,3 Mio | 62,9 Mio | **−27,4 Mio** | `opengl32sw.dll` (~20 Mio) + `d3dcompiler_47.dll`, traductions (97 `.qm`), plugins inutiles |
| `tcl`/`tk` (`_tcl_data`, `tcl86t.dll`, `tk86t.dll`, `_tk_data`) | ≈ 7,1 Mio | **0** | exclusion complète de **tkinter** (app Qt-only) |
| `matplotlib` (`mpl-data`) | 13,7 Mio | 7,3 Mio | **−6,4 Mio** | fonts `afm`/`pdfcorefonts`/`sample_data` + `ttf` non-DejaVu |

Inchangés (dépendances dures) : `numpy.libs` (OpenBLAS, 20 Mio), `numpy`, `PIL`,
`python312.dll`, `libcrypto`. `PIL` (10,7 Mio) est tiré par matplotlib —
candidat à un dégraissage ultérieur (non fait : non validé).

## Validation — check-list Windows (à dérouler sur la version installée)

Le dégraissage peut casser **silencieusement** (l'app démarre mais une fonction
périphérique meurt). À valider après installation, sur un vrai Windows :

1. **Démarrage** : l'exe s'ouvre en **simulation** (badge bleu), bascule de thème
   (sombre/clair) OK, chaque onglet s'ouvre (Contrôle, Configuration, Éditeur,
   Graphe). *(Le canari CI couvre déjà « l'exe démarre ».)*
2. **Icône de fenêtre présente** dans la barre des tâches et le titre — **canari
   des `imageformats`** (l'icône `.ico` doit se charger).
3. **Enregistrement + séquence** : lancer un enregistrement, exécuter
   `exemple.seq`, la laisser finir.
4. **Rapport** : générer le rapport d'essai → le **PDF contient les graphiques**
   V/I et températures (**canari des exclusions matplotlib / mpl-data**) et
   s'ouvre correctement, texte lisible (police DejaVu).
5. Si l'exe **ne démarre plus** après une exclusion : suspecter `QtNetwork` (le
   réintégrer et le noter ici). Si un **rendu est cassé** : suspecter un plugin
   `imageformats`/`iconengines` ou une DLL OpenGL retirés.
