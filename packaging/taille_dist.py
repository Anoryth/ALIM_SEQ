#!/usr/bin/env python3
"""Rapport de tailles d'un build PyInstaller onedir (`dist/ALIM_SEQ/`).

Sert à mesurer l'effet du dégraissage (voir packaging/OPTIMISATION.md) :
    python packaging/taille_dist.py [chemin_dist]     (défaut: dist/ALIM_SEQ)

Imprime : total, tailles par sous-dossier (1er niveau sous _internal), et les
25 plus gros fichiers. Format stable pour copier-coller dans OPTIMISATION.md.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _human(n: int) -> str:
    x = float(n)
    for u in ("o", "Kio", "Mio", "Gio"):
        if x < 1024 or u == "Gio":
            return f"{x:7.1f} {u}" if u != "o" else f"{int(x):7d} o"
        x /= 1024
    return f"{x:.1f} Gio"


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("dist/ALIM_SEQ")
    if not root.is_dir():
        print(f"Dossier introuvable : {root}", file=sys.stderr)
        print("Construire d'abord (pyinstaller packaging/ALIM_SEQ.spec).", file=sys.stderr)
        return 1

    files = [p for p in root.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)

    # Regroupe par 1er composant de chemin relatif (ex. _internal, _internal/PySide6…).
    # On descend d'un cran dans _internal pour distinguer PySide6 / matplotlib / etc.
    groups: dict[str, int] = {}
    for p in files:
        rel = p.relative_to(root)
        parts = rel.parts
        if parts and parts[0] == "_internal" and len(parts) >= 2:
            key = f"_internal/{parts[1]}"
        else:
            key = parts[0] if len(parts) > 1 else "(racine)"
        groups[key] = groups.get(key, 0) + p.stat().st_size

    print(f"=== Build : {root}  ({len(files)} fichiers) ===")
    print(f"TOTAL : {_human(total)}  ({total} octets)\n")

    print("--- Par sous-dossier (décroissant) ---")
    for key, sz in sorted(groups.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {_human(sz)}   {key}")

    print("\n--- 25 plus gros fichiers ---")
    for p in sorted(files, key=lambda q: q.stat().st_size, reverse=True)[:25]:
        print(f"  {_human(p.stat().st_size)}   {p.relative_to(root)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
