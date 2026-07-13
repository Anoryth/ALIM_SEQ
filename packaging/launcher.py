"""Point d'entrée de l'application empaquetée (PyInstaller).

- Place le répertoire de travail dans un dossier de données **inscriptible**
  (``%LOCALAPPDATA%\\ALIM_SEQ``) et y dépose au premier lancement les fichiers par
  défaut (``config.json``, ``sequences/``) extraits du bundle. Ainsi la config
  éditée et les logs persistent, même si l'app est installée en lecture seule
  (Program Files).
"""

import os
import shutil
import sys


def _documents_dir() -> str:
    """Dossier « Documents » de l'utilisateur (gère la redirection OneDrive via
    l'API Windows ; repli sur ~/Documents)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                        ("d3", wintypes.WORD), ("d4", ctypes.c_byte * 8)]

        # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        fid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                   (ctypes.c_byte * 8)(-83, -76, 108, -123, 72, 3, 105, -57))
        ptr = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(fid), 0, 0, ctypes.byref(ptr)) == 0:
            path = ptr.value
            ctypes.windll.ole32.CoTaskMemFree(ptr)
            if path:
                return path
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _registry_data_dir():
    """Dossier de données choisi par l'utilisateur à l'installation (Inno écrit
    ``HKCU/HKLM\\Software\\ALIM_SEQ\\DataDir``). Renvoie None si absent."""
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, r"Software\ALIM_SEQ") as k:
                    val, _ = winreg.QueryValueEx(k, "DataDir")
                    if val:
                        return os.path.expandvars(val)
            except OSError:
                continue
    except Exception:
        pass
    return None


def _data_dir() -> str:
    # Données utilisateur (config éditée, séquences, logs) : dossier choisi à
    # l'installation, sinon repli sur Documents\ALIM_SEQ (ex. exe portable).
    d = _registry_data_dir() or os.path.join(_documents_dir(), "ALIM_SEQ")
    os.makedirs(d, exist_ok=True)
    return d


def _seed(res: str, dd: str) -> None:
    cfg = os.path.join(dd, "config.json")
    if not os.path.exists(cfg) and os.path.exists(os.path.join(res, "config.json")):
        shutil.copy(os.path.join(res, "config.json"), cfg)
    seq_dst = os.path.join(dd, "sequences")
    seq_src = os.path.join(res, "sequences")
    if not os.path.isdir(seq_dst) and os.path.isdir(seq_src):
        shutil.copytree(seq_src, seq_dst)


if getattr(sys, "frozen", False):
    _res = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    _dd = _data_dir()
    _seed(_res, _dd)
    os.chdir(_dd)

from main import main  # noqa: E402  (après ajustement de sys.path par PyInstaller)

sys.exit(main())
