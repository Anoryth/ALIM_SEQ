#!/usr/bin/env bash
# Rebuild the translation catalogs for both layers of the app:
#
#   tools/build-i18n.sh            # update + compile FR catalogs
#
# English is the SOURCE language (strings are written in English in the code), so
# only non-English catalogs are generated here. Two toolchains, one per layer:
#
#   * GUI  (alim_seq/gui_qt/*.py, self.tr) -> Qt Linguist .ts/.qm
#       alim_seq/gui_qt/i18n/alim_seq_<lang>.ts   (edit translations here)
#       alim_seq/gui_qt/i18n/alim_seq_<lang>.qm   (compiled, loaded at runtime)
#
#   * domain (alim_seq/*.py, _() from alim_seq.i18n) -> gettext .po/.mo
#       alim_seq/locale/<lang>/LC_MESSAGES/alim_seq.po   (edit translations here)
#       alim_seq/locale/<lang>/LC_MESSAGES/alim_seq.mo   (compiled, loaded at runtime)
#
# The .qm/.mo files are regenerable build artifacts (git-ignored); the .ts/.po
# sources are versioned. Run this after adding or changing any translatable string.
set -euo pipefail
cd "$(dirname "$0")/.."

LANGS=(fr)

# --- GUI layer: Qt Linguist -------------------------------------------------
GUI_I18N="alim_seq/gui_qt/i18n"
mkdir -p "$GUI_I18N"
lupdate=""
for c in pyside6-lupdate lupdate; do command -v "$c" >/dev/null 2>&1 && { lupdate="$c"; break; }; done
lrelease=""
for c in pyside6-lrelease lrelease; do command -v "$c" >/dev/null 2>&1 && { lrelease="$c"; break; }; done

if [ -n "$lupdate" ] && [ -n "$lrelease" ]; then
  for lang in "${LANGS[@]}"; do
    ts="$GUI_I18N/alim_seq_${lang}.ts"
    echo "GUI  -> updating $ts"
    "$lupdate" alim_seq/gui_qt/*.py -ts "$ts" -no-obsolete >/dev/null
    echo "GUI  -> compiling ${ts%.ts}.qm"
    "$lrelease" "$ts" >/dev/null
  done
else
  echo "WARN: pyside6-lupdate/lrelease not found — skipping GUI catalogs." >&2
  echo "      Install via 'pip install -r requirements-qt.txt' (PySide6 ships them)." >&2
fi

# --- Domain layer: gettext --------------------------------------------------
POT="alim_seq/locale/alim_seq.pot"
mkdir -p "alim_seq/locale"
if command -v xgettext >/dev/null 2>&1; then
  echo "domain -> extracting $POT"
  # Domain modules only (the GUI package uses Qt tr, not gettext).
  mapfile -t DOMAIN_PY < <(find alim_seq -maxdepth 1 -name '*.py')
  xgettext --language=Python --keyword=_ --keyword=gettext \
           --from-code=UTF-8 --package-name=ALIM_SEQ \
           -o "$POT" "${DOMAIN_PY[@]}" main.py
  for lang in "${LANGS[@]}"; do
    po="alim_seq/locale/${lang}/LC_MESSAGES/alim_seq.po"
    mkdir -p "$(dirname "$po")"
    if [ -f "$po" ]; then
      echo "domain -> merging $po"
      msgmerge --update --backup=none "$po" "$POT" >/dev/null
    else
      echo "domain -> creating $po"
      msginit --no-translator --locale="$lang" -i "$POT" -o "$po" >/dev/null
    fi
    echo "domain -> compiling ${po%.po}.mo"
    msgfmt "$po" -o "${po%.po}.mo"
  done
else
  echo "WARN: xgettext/gettext tools not found — skipping domain catalogs." >&2
  echo "      Install the 'gettext' package for your OS." >&2
fi

echo "i18n build done."
