# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — construit dist/ALIM_SEQ/ (mode ONEDIR, IHM Qt).
# Usage (sous Windows, depuis la racine du dépôt) :
#     pyinstaller packaging/ALIM_SEQ.spec
#
# Dégraissage : voir packaging/OPTIMISATION.md. L'app n'utilise que QtCore/QtGui/
# QtWidgets et matplotlib backend Agg uniquement (graphes du rapport). Le PDF du
# rapport est produit par reportlab (pur Python, sans Qt). numpy est une
# dépendance dure de matplotlib (gardée). UPX désactivé (faux positifs AV + DLL
# Qt fragiles).
import os
from PyInstaller.utils.hooks import (collect_submodules, copy_metadata,
                                     collect_data_files)

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))   # racine du dépôt
PKG = SPECPATH                                          # dossier packaging/

# Dégraissage activé par défaut. Mettre ALIM_SLIM=0 pour construire la BASELINE
# (mêmes exclusions Qt de base, mais SANS le retrait des backends matplotlib, du
# filtrage mpl-data et des DLL/plugins) -> sert à mesurer le gain (OPTIMISATION.md).
SLIM = os.environ.get("ALIM_SLIM", "1") != "0"

hidden = []
# nidaqmx (pilotage NI) + pyvisa/pyvisa-py (VISA) si présents au build ; pyvisa-py
# charge ses backends dynamiquement (serial/psutil paresseux) -> collecte + ajout.
for opt in ("nidaqmx", "pyvisa", "pyvisa_py", "psutil", "serial"):
    try:
        __import__(opt)
        hidden.append(opt)
        hidden += collect_submodules(opt)
    except Exception:
        pass
# matplotlib : rapport d'essai, backend Agg UNIQUEMENT (import paresseux dans
# rapport.py). On sécurise le backend Agg ; les backends interactifs sont exclus.
hidden += ["matplotlib", "matplotlib.backends.backend_agg", "serial.tools.list_ports"]
hidden += collect_submodules("alim_seq.gui_qt")
# reportlab : génération PDF du rapport (import paresseux dans rapport.py, pur
# Python, sans Qt). Sous-modules + données (polices AFM/Type-1, glyphes) requis
# à l'exécution -> embarqués. rl_datas est ajouté à `datas` plus bas.
rl_datas = []
try:
    import reportlab  # noqa: F401
    hidden += ["reportlab"] + collect_submodules("reportlab")
    rl_datas += collect_data_files("reportlab")
except Exception:
    pass
# nidaqmx lit la version de nitypes/hightime via importlib.metadata -> métadonnées.
meta_datas = []
for opt in ("nidaqmx", "nitypes", "hightime"):
    try:
        __import__(opt)
        meta_datas += copy_metadata(opt)
        hidden += collect_submodules(opt)
    except Exception:
        pass

# ------------------------------------------------------------------ excludes
# (1) Modules Qt inutilisés (l'app n'importe que QtCore/QtGui/QtWidgets). QtPdf
#     est exclu : QPdfWriter est dans QtGui, pas dans QtPdf. QtNetwork exclu (rien
#     ne l'aspire ; déjà validé sur la version onefile testée).
_QT_HEAVY = [
    "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebEngine",
    "QtMultimedia", "QtMultimediaWidgets", "QtQuick", "QtQuick3D", "QtQuickWidgets",
    "QtQml", "QtCharts", "QtDataVisualization", "Qt3DCore", "Qt3DRender",
    "Qt3DInput", "Qt3DAnimation", "Qt3DExtras", "QtNetwork", "QtSql", "QtPdf",
    "QtPdfWidgets", "QtPositioning", "QtLocation", "QtBluetooth", "QtNfc",
    "QtDesigner", "QtUiTools", "QtTest", "QtOpenGL", "QtOpenGLWidgets", "QtSensors",
    "QtSerialPort", "QtWebSockets", "QtWebChannel", "QtRemoteObjects",
    "QtScxml", "QtSpatialAudio", "QtTextToSpeech", "QtHelp",
]
# (2) Backends matplotlib interactifs + ponts (le hook matplotlib les aspire s'ils
#     sont présents sur la machine de build). On NE garde QUE Agg. tkinter est tiré
#     par backend_tkagg : l'app empaquetée est Qt-only, on l'exclut. + tests.
_MPL_TK = [
    "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qt6agg", "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_tkcairo",
    "matplotlib.backends.backend_gtk3agg", "matplotlib.backends.backend_gtk3cairo",
    "matplotlib.backends.backend_gtk4agg", "matplotlib.backends.backend_gtk4cairo",
    "matplotlib.backends.backend_wx", "matplotlib.backends.backend_wxagg",
    "matplotlib.backends.backend_wxcairo", "matplotlib.backends.backend_macosx",
    "matplotlib.backends.backend_webagg", "matplotlib.backends.backend_webagg_core",
    "matplotlib.backends.backend_nbagg", "matplotlib.backends.qt_compat",
    "tkinter", "_tkinter", "matplotlib.tests", "numpy.tests",
]
excludes = [f"PySide6.{m}" for m in _QT_HEAVY] + (_MPL_TK if SLIM else [])

datas = [
    (os.path.join(ROOT, "config.json"), "."),
    (os.path.join(ROOT, "sequences"), "sequences"),
    (os.path.join(ROOT, "README.md"), "."),
] + meta_datas + rl_datas
for _doc in ("MANUEL_UTILISATEUR.md", "MANUEL_UTILISATEUR.pdf",
             "USER_MANUAL.md", "USER_MANUAL.pdf"):
    _p = os.path.join(ROOT, "docs", _doc)
    if os.path.exists(_p):
        datas.append((_p, "docs"))
# Logo embarqué (en-tête du rapport d'essai) — résolu comme l'icône.
for _img in ("logo.png", "icon.ico"):
    _p = os.path.join(PKG, _img)
    if os.path.exists(_p):
        datas.append((_p, "."))

# Compiled translation catalogs (regenerate with tools/build-i18n.sh before building):
#   domain gettext .mo -> alim_seq/locale/<lang>/LC_MESSAGES/  (i18n.py resolves this)
#   GUI Qt .qm         -> alim_seq/gui_qt/i18n/                 (main_window.py resolves this)
import glob as _glob
for _mo in _glob.glob(os.path.join(ROOT, "alim_seq", "locale", "*", "LC_MESSAGES", "*.mo")):
    _rel = os.path.relpath(os.path.dirname(_mo), ROOT)
    datas.append((_mo, _rel))
for _qm in _glob.glob(os.path.join(ROOT, "alim_seq", "gui_qt", "i18n", "*.qm")):
    datas.append((_qm, os.path.join("alim_seq", "gui_qt", "i18n")))

icon = os.path.join(PKG, "icon.ico")
icon = icon if os.path.exists(icon) else None

a = Analysis(
    [os.path.join(PKG, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)

# ---------------------------------------------------- filtrage binaires/datas
def _n(dest):
    # préfixe "/" pour que les motifs "/pyside6/..." matchent aussi les chemins
    # de 1er niveau (ex. PySide6/translations/ n'a pas de parent).
    return "/" + str(dest).replace("\\", "/").lower()

# (3) mpl-data : on purge le strict inutile au backend Agg — sample_data (jeux
#     d'exemple), afm + pdfcorefonts (métriques des backends PostScript/PDF, PAS
#     utilisées par Agg qui écrit du PNG). On CONSERVE TOUTES les polices
#     fonts/ttf/ : ne garder que DejaVu Sans cassait le rendu matplotlib sur le
#     build installé ("il manque des polices") — le gain (~2 Mo) ne le valait pas.
def _drop_data(dest):
    d = _n(dest)
    if "/mpl-data/sample_data/" in d:
        return True
    if "/mpl-data/fonts/pdfcorefonts/" in d or "/mpl-data/fonts/afm/" in d:
        return True
    # Traductions Qt : app monolingue, aucun QTranslator chargé.
    if "/pyside6/translations/" in d:
        return True
    return False

# (4) Binaires : DLL de repli OpenGL logiciel + compilateur D3D (pas d'OpenGL dans
#     l'IHM), et plugins Qt inutilisés. On GARDE platforms/ (qwindows vital),
#     styles/, iconengines/, et imageformats qico/qpng/qjpeg (icône .ico + PNG du
#     rapport). tls exclu (QtNetwork exclu).
_IMGFMT_KEEP = ("qico", "qpng", "qjpeg")
_PLUGIN_DROP = ("/plugins/multimedia/", "/plugins/sqldrivers/", "/plugins/qml/",
                "/plugins/qmltooling/", "/plugins/tls/", "/plugins/networkinformation/",
                "/plugins/webview/", "/plugins/position/", "/plugins/sceneparsers/",
                "/plugins/renderers/", "/plugins/geometryloaders/")

def _drop_binary(dest):
    d = _n(dest)
    base = os.path.basename(d)
    if base in ("opengl32sw.dll", "d3dcompiler_47.dll"):
        return True
    if "/plugins/imageformats/" in d:
        stem = os.path.splitext(base)[0]
        return not any(stem == k or stem == k + "d" for k in _IMGFMT_KEEP)
    return any(marker in d for marker in _PLUGIN_DROP)

if SLIM:
    a.datas = [t for t in a.datas if not _drop_data(t[0]) and not _drop_binary(t[0])]
    a.binaries = [t for t in a.binaries if not _drop_binary(t[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,        # ONEDIR : les dépendances vont dans COLLECT
    name="ALIM_SEQ",
    console=False,                # application fenêtrée
    icon=icon,
    upx=False,                    # délibéré : faux positifs AV + DLL Qt fragiles
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="ALIM_SEQ",
)
