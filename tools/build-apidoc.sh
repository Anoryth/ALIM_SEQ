#!/usr/bin/env bash
# Generate the HTML API documentation (from the docstrings) into docs/api/.
#
#   tools/build-apidoc.sh          # -> docs/api/index.html
#   python -m pdoc alim_seq        # (alternative) live server http://localhost:8080
#
# Requires pdoc:  pip install -r requirements-dev.txt
# The docs/api/ output is a regenerable artifact, git-ignored.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! python -m pdoc --version >/dev/null 2>&1; then
  echo "pdoc missing — install with: pip install -r requirements-dev.txt" >&2
  exit 1
fi

OUT="docs/api"
echo "Generating the API doc -> $OUT/ …"
python -m pdoc alim_seq -o "$OUT"
echo "OK: open $OUT/index.html"
