#!/usr/bin/env bash
# Génère le manuel utilisateur aux formats .pdf et .docx depuis le .md (source unique).
#
#   tools/build-manual.sh          # -> docs/MANUEL_UTILISATEUR.{pdf,docx}
#
# Requiert pandoc (et un moteur LaTeX pour le PDF, ex. tectonic ou texlive).
# Les sorties .pdf/.docx sont des artefacts RÉGÉNÉRABLES, ignorés par git : seul le
# .md est versionné (et sert l'aide intégrée F1). Le build Windows embarque le .pdf
# s'il est présent (packaging/ALIM_SEQ.spec) — lancer ce script avant un build pour
# livrer un PDF à jour.
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="docs/MANUEL_UTILISATEUR.md"
[ -f "$SRC" ] || { echo "Introuvable : $SRC" >&2; exit 1; }
if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc absent — installer pandoc (+ un moteur LaTeX pour le PDF)." >&2
  exit 1
fi

echo "Génération $SRC -> .docx …"
pandoc "$SRC" -o "docs/MANUEL_UTILISATEUR.docx" --toc

# Moteur PDF : on privilégie un moteur COMPATIBLE UNICODE (le manuel contient ⚠, °C…).
# pdflatex (défaut de pandoc) échoue sur ces caractères ; weasyprint (HTML→PDF, sans
# dépendances LaTeX) ou xelatex conviennent.
echo "Génération $SRC -> .pdf …"
engine=""
for e in weasyprint xelatex lualatex tectonic; do
  command -v "$e" >/dev/null 2>&1 && { engine="$e"; break; }
done
if [ -z "$engine" ]; then
  echo "Aucun moteur PDF Unicode trouvé (weasyprint / xelatex / lualatex / tectonic)." >&2
  echo ".docx généré ; installer un de ces moteurs pour le PDF." >&2
  exit 0
fi
echo "  (moteur : $engine)"
if pandoc "$SRC" -o "docs/MANUEL_UTILISATEUR.pdf" --toc --pdf-engine="$engine" 2>/dev/null; then
  echo "OK : docs/MANUEL_UTILISATEUR.{docx,pdf}"
else
  echo "Échec de la génération PDF avec $engine — .docx OK." >&2
  exit 1
fi
