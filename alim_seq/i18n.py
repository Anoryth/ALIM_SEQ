"""Lightweight i18n for the non-Qt domain layer.

The domain modules (``controller``, ``rapport``, ``essai``, ``sequencer``,
``psu``, ``daq``, ``temperature``…) must stay free of any Qt dependency so they
remain testable and so reports can be regenerated headless. They therefore use
the Python standard :mod:`gettext` instead of ``QObject.tr()`` (which is reserved
for the ``gui_qt`` layer).

English is the **base** language: source strings are written in English and wrapped
in :func:`_`. Other languages are supplied as compiled ``.mo`` catalogs under
``alim_seq/locale/<lang>/LC_MESSAGES/alim_seq.mo``. When no catalog is available
(e.g. ``en``, or during tests before ``build-i18n.sh`` has run) the identity
fallback returns the English source unchanged, so the app never breaks.

The Qt language selector calls :func:`set_language` so the whole app — GUI *and*
domain — follows a single language setting.
"""

from __future__ import annotations

import gettext as _gettext
from pathlib import Path

_LOCALE_DIR = Path(__file__).resolve().parent / "locale"
_DOMAIN = "alim_seq"

# Current translation object. NullTranslations is the identity fallback: it
# returns the English source string unchanged (used for English and whenever a
# catalog is missing).
_translation: _gettext.NullTranslations = _gettext.NullTranslations()

# Currently active language code (e.g. "fr", "en"), for callers that need it.
_current_language: str = "en"


def set_language(lang: str | None) -> str:
    """Activate the translation catalog for ``lang`` (e.g. ``"fr"``, ``"en"``).

    English (or ``None``/unknown) falls back to the identity translation, i.e.
    the English source strings. Returns the language code actually applied.
    """
    global _translation, _current_language

    code = (lang or "en").split("_")[0].split("-")[0].lower()
    if code and code != "en":
        try:
            _translation = _gettext.translation(
                _DOMAIN, localedir=str(_LOCALE_DIR), languages=[code]
            )
            _current_language = code
            return code
        except (FileNotFoundError, OSError):
            # No compiled catalog for this language — fall back to English.
            pass

    _translation = _gettext.NullTranslations()
    _current_language = "en" if not code else code
    return _current_language


def current_language() -> str:
    """Return the currently active language code."""
    return _current_language


def gettext(message: str) -> str:
    """Translate ``message`` into the active language (identity if unavailable)."""
    return _translation.gettext(message)


# Conventional short alias used throughout the domain layer.
_ = gettext
