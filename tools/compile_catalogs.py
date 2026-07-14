#!/usr/bin/env python3
"""Compile translation catalogs, cross-platform (no bash / gettext needed).

Compiles the *versioned* sources into the runtime artifacts:
    alim_seq/locale/<lang>/LC_MESSAGES/*.po  ->  *.mo   (pure-Python msgfmt)
    alim_seq/gui_qt/i18n/*.ts                ->  *.qm   (pyside6-lrelease)

Meant for the packaging step (the Windows CI runs this before PyInstaller), where
the bash `tools/build-i18n.sh` and GNU gettext are not available. Unlike
build-i18n.sh it does NOT re-extract strings (no lupdate/xgettext) — it only
compiles what is already in the .po/.ts sources.
"""
from __future__ import annotations

import array
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse_po(text: str) -> dict[str, str]:
    """Minimal .po parser: returns {msgid: msgstr} for translated entries."""
    entries: dict[str, str] = {}
    msgid = msgstr = None
    target = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if line.startswith("msgid "):
            if msgid is not None and msgstr:
                entries[msgid] = msgstr
            msgid, target = _unquote(line[6:]), "id"
            msgstr = ""
        elif line.startswith("msgstr "):
            msgstr, target = _unquote(line[7:]), "str"
        elif line.startswith('"'):
            if target == "id":
                msgid += _unquote(line)
            elif target == "str":
                msgstr += _unquote(line)
    if msgid is not None and msgstr:
        entries[msgid] = msgstr
    # Keep the "" header entry: gettext reads Content-Type from it for the charset.
    return entries


def _unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def _write_mo(entries: dict[str, str], path: Path) -> None:
    """Write a binary .mo (GNU format) from {msgid: msgstr}."""
    keys = sorted(entries)
    offsets, ids, strs = [], b"", b""
    for k in keys:
        kb = k.encode("utf-8")
        vb = entries[k].encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\x00"
        strs += vb + b"\x00"
    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    output = struct.pack("Iiiiiii", 0x950412de, 0, len(keys),
                         7 * 4, 7 * 4 + len(keys) * 8, 0, 0)
    output += array.array("i", koffsets).tobytes()
    output += array.array("i", voffsets).tobytes()
    output += ids + strs
    path.write_bytes(output)


def main() -> int:
    # --- domain gettext .po -> .mo ---
    for po in (ROOT / "alim_seq" / "locale").glob("*/LC_MESSAGES/*.po"):
        entries = _parse_po(po.read_text(encoding="utf-8"))
        mo = po.with_suffix(".mo")
        _write_mo(entries, mo)
        print(f"domain -> {mo.relative_to(ROOT)} ({len(entries)} entries)")

    # --- GUI Qt .ts -> .qm (needs pyside6-lrelease) ---
    lrelease = None
    for cand in ("pyside6-lrelease", "lrelease"):
        try:
            subprocess.run([cand, "-help"], capture_output=True)
            lrelease = cand
            break
        except FileNotFoundError:
            continue
    ts_files = list((ROOT / "alim_seq" / "gui_qt" / "i18n").glob("*.ts"))
    if lrelease:
        for ts in ts_files:
            subprocess.run([lrelease, str(ts)], check=True,
                           stdout=subprocess.DEVNULL)
            print(f"GUI    -> {ts.with_suffix('.qm').relative_to(ROOT)}")
    elif ts_files:
        print("WARN: pyside6-lrelease not found — GUI .qm not compiled.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
