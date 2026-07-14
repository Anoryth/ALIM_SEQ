#!/usr/bin/env bash
# Build the user manual as .pdf and .docx from the .md sources (single source).
#
#   tools/build-manual.sh          # -> docs/{USER_MANUAL,MANUEL_UTILISATEUR}.{pdf,docx}
#
# Requires pandoc (and a PDF engine, e.g. weasyprint or a LaTeX engine). The
# .pdf/.docx outputs are REGENERABLE artifacts, git-ignored: only the .md is
# versioned (and serves the built-in F1 help). The Windows build embeds the .pdf
# if present (packaging/ALIM_SEQ.spec) — run this script before a build to ship an
# up-to-date PDF. Both the English (USER_MANUAL) and French (MANUEL_UTILISATEUR)
# manuals are built.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc missing — install pandoc (+ a PDF engine)." >&2
  exit 1
fi

# PDF engine: prefer a UNICODE-COMPATIBLE engine (the manual contains ⚠, °C…).
# pdflatex (pandoc's default) fails on those; weasyprint (HTML→PDF, no LaTeX deps)
# or xelatex work.
engine=""
for e in weasyprint xelatex lualatex tectonic; do
  command -v "$e" >/dev/null 2>&1 && { engine="$e"; break; }
done

for name in USER_MANUAL MANUEL_UTILISATEUR; do
  src="docs/${name}.md"
  [ -f "$src" ] || { echo "Skipping missing: $src" >&2; continue; }
  echo "Generating $src -> .docx …"
  pandoc "$src" -o "docs/${name}.docx" --toc
  if [ -z "$engine" ]; then
    echo "No Unicode PDF engine found (weasyprint / xelatex / lualatex / tectonic)." >&2
    echo ".docx generated for $name; install one of these engines for the PDF." >&2
    continue
  fi
  echo "Generating $src -> .pdf  (engine: $engine) …"
  if pandoc "$src" -o "docs/${name}.pdf" --toc --pdf-engine="$engine" 2>/dev/null; then
    echo "OK: docs/${name}.{docx,pdf}"
  else
    echo "PDF generation failed for $name with $engine — .docx OK." >&2
  fi
done
