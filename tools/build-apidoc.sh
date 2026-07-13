#!/usr/bin/env bash
# Génère la documentation d'API HTML (depuis les docstrings) dans docs/api/.
#
#   tools/build-apidoc.sh          # -> docs/api/index.html
#   python -m pdoc alim_seq        # (alternative) serveur live http://localhost:8080
#
# Requiert pdoc :  pip install -r requirements-dev.txt
# La sortie docs/api/ est un artefact régénérable, ignoré par git.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! python -m pdoc --version >/dev/null 2>&1; then
  echo "pdoc absent — installer avec : pip install -r requirements-dev.txt" >&2
  exit 1
fi

OUT="docs/api"
echo "Génération de la doc API -> $OUT/ …"
python -m pdoc alim_seq -o "$OUT"
echo "OK : ouvrir $OUT/index.html"
