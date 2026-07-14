"""Test report, generated from the artifacts of a test folder.

Three clearly separated layers, none depending on Qt:

1. **Data** (pure Python) — :func:`stats_voies`, :func:`stats_capteurs`,
   :func:`evenements`, :func:`trip_info` read ``essai.json``, ``mesures.csv``,
   ``sequence.seq``, ``journal.log`` and ``config.json``. Testable with no
   dependency.
2. **Charts** — :func:`rendre_graphiques` (V/I and temperature plots with
   **matplotlib**, Agg backend, from the CSV → PNG). Imports local to the function.
3. **Renderers** sharing the data layer:
   - :func:`construire_html` — self-contained HTML (browser preview), pure Python;
   - :func:`exporter_pdf` — PDF **via ReportLab** (pure Python, professional layout:
     centered tables, colored headers, pagination). No dependency on Qt.

:func:`generer_rapport` orchestrates all of it and writes ``rapport.html`` +
``rapport.pdf`` into the folder. The report is ALWAYS generated from the folder,
never from the GUI's live state: it is regenerable months later. It issues NO
compliance verdict — the conclusion is the operator's.
"""

from __future__ import annotations

import csv
import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import i18n
from .i18n import _

# Sober, print-friendly palette (white background).
ACCENT = "#1F4E79"        # dark blue: titles, rules
ACCENT_LIGHT = "#DCE6F1"  # very light blue: table header backgrounds
OK_GREEN = "#2E7D32"
NEUTRAL = "#555555"
DANGER = "#C62828"        # red: RESERVED for safety events
SIM_BG = "#FFF3CD"        # simulation banner
SIM_FG = "#7A5B00"


# --------------------------------------------------------------------- reading
def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_csv(dossier: Path) -> Tuple[List[str], List[List[str]]]:
    p = dossier / "mesures.csv"
    if not p.exists():
        return [], []
    with p.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _f(x: str) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _finite(vals: List[float]) -> List[float]:
    return [v for v in vals if v == v and not math.isinf(v)]


# ----------------------------------------------------------------- statistics
def _sensor_names(header: List[str]) -> List[str]:
    return [h[:-2] for h in header if h.endswith("_C")]


def _channel_labels(header: List[str]) -> List[str]:
    return [h[:-6] for h in header if h.endswith("_Vmeas")]


def stats_voies(header: List[str], rows: List[List[str]]) -> Dict[str, dict]:
    """Per channel: min/max/average V and I, time in current limiting (CC),
    and start/end setpoints of the test.

    CC criterion: active output (``_out`` = 1) AND ``Imeas >= 0.98·Iset`` with
    ``Iset > 0``. Time integrated over the CSV's ``dt``; percentage reported over
    the active-output time."""
    idx = {h: i for i, h in enumerate(header)}
    t_i = idx.get("t_s")
    out: Dict[str, dict] = {}
    for label in _channel_labels(header):
        vi, ii = idx[f"{label}_Vmeas"], idx[f"{label}_Imeas"]
        iseti, outi = idx.get(f"{label}_Iset"), idx.get(f"{label}_out")
        vseti = idx.get(f"{label}_Vset")
        vs = _finite([_f(r[vi]) for r in rows if vi < len(r)])
        is_ = _finite([_f(r[ii]) for r in rows if ii < len(r)])
        cc_s = active_s = 0.0
        prev_t = None
        for r in rows:
            t = _f(r[t_i]) if (t_i is not None and t_i < len(r)) else float("nan")
            dt = (t - prev_t) if (prev_t is not None and t == t and t >= prev_t) else 0.0
            prev_t = t if t == t else prev_t
            on = outi is not None and outi < len(r) and str(r[outi]).strip() in ("1", "True", "true")
            if on:
                active_s += dt
                im = _f(r[ii]) if ii < len(r) else float("nan")
                iset = _f(r[iseti]) if (iseti is not None and iseti < len(r)) else float("nan")
                if im == im and iset == iset and iset > 0 and im >= 0.98 * iset:
                    cc_s += dt
        def _setpoint(row):
            v = _f(row[vseti]) if (vseti is not None and vseti < len(row)) else float("nan")
            i = _f(row[iseti]) if (iseti is not None and iseti < len(row)) else float("nan")
            return (v, i)
        out[label] = {
            "v": _mmm(vs), "i": _mmm(is_),
            "cc_s": cc_s, "active_s": active_s,
            "cc_pct": (100.0 * cc_s / active_s) if active_s > 0 else None,
            "consigne_debut": _setpoint(rows[0]) if rows else None,
            "consigne_fin": _setpoint(rows[-1]) if rows else None,
        }
    return out


def stats_capteurs(header: List[str], rows: List[List[str]],
                   warnings: Dict[str, float],
                   criticals: Optional[Dict[str, float]] = None) -> Dict[str, dict]:
    """Per sensor: min/max/average °C, **excursions** (number of crossings above
    the warning threshold), and cumulated durations above the warning AND the
    critical threshold (integration over the CSV's ``dt``)."""
    criticals = criticals or {}
    idx = {h: i for i, h in enumerate(header)}
    t_i = idx.get("t_s")
    out: Dict[str, dict] = {}
    for name in _sensor_names(header):
        ci = idx[f"{name}_C"]
        temps = _finite([_f(r[ci]) for r in rows if ci < len(r)])
        warn = warnings.get(name)
        crit = criticals.get(name)
        alerte_s = crit_s = 0.0
        count = 0            # number of RISES above the warning threshold
        was_over = False
        prev_t = None
        for r in rows:
            if ci >= len(r) or t_i is None or t_i >= len(r):
                continue
            t = _f(r[t_i])
            c = _f(r[ci])
            dt = (t - prev_t) if (prev_t is not None and t == t and t >= prev_t) else 0.0
            prev_t = t if t == t else prev_t
            if c != c:
                continue
            if warn is not None:
                if c >= warn:
                    alerte_s += dt
                    if not was_over:
                        count += 1
                    was_over = True
                else:
                    was_over = False
            if crit is not None and c >= crit:
                crit_s += dt
        out[name] = {"c": _mmm(temps), "alerte_s": alerte_s, "critique_s": crit_s,
                     "excursions": count, "warning": warn, "critical": crit}
    return out


def _mmm(vals: List[float]) -> Optional[Tuple[float, float, float]]:
    if not vals:
        return None
    return (min(vals), max(vals), sum(vals) / len(vals))


# Keywords marking a SAFETY event (red line). Shared by the timeline, the event
# extraction for the plots and the zoom. journal.log is written in whatever language
# was active at run time, so we match the language-independent "!!!" prefix first,
# plus both English and (legacy) French markers — reports of old FR test folders
# stay readable.
_DANGER_KW = ("!!!", "TRIP", "hard cut-off", "Emergency", "emergency", "lost", "Lost",
              "DÉCLENCHEMENT", "Coupure dure", "coupure dure", "Perte", "urgence")


def _fr(x: Optional[float], nd: int = 2) -> str:
    """Format a number for the active report language. '—' if None/NaN.
    Single function so the decimal separator (comma in French, dot elsewhere) is
    applied consistently, avoiding scattered replace('.', ',')."""
    if x is None or (isinstance(x, float) and (x != x or math.isinf(x))):
        return "—"
    s = f"{x:.{nd}f}"
    return s.replace(".", ",") if i18n.current_language() == "fr" else s


def _event_t_s(stamp: str, t0: Optional[datetime], t0_ts: float) -> Optional[float]:
    """Time (s) of a log timestamp, realigned on the CSV's axis: ``t0`` is the
    ABSOLUTE timestamp of the CSV's 1st row, ``t0_ts`` its ``t_s``. ``stamp`` can
    be a full ISO string (safety events) or ``hh:mm:ss`` (log)."""
    if t0 is None:
        return None
    ev = _parse_iso(stamp)
    if ev is not None:
        return (ev - t0).total_seconds() + t0_ts
    try:
        h, m, s = (int(x) for x in stamp.split(":"))
    except (ValueError, AttributeError):
        return None
    delta = (h * 3600 + m * 60 + s) - (t0.hour * 3600 + t0.minute * 60 + t0.second)
    if delta < -12 * 3600:            # midnight rollover
        delta += 86400
    return delta + t0_ts


def _csv_t0(header: List[str], rows: List[List[str]]):
    """(absolute timestamp, t_s) of the CSV's 1st row — realignment base."""
    idx = {h: i for i, h in enumerate(header)}
    hi, ti = idx.get("horodatage"), idx.get("t_s")
    if not rows or hi is None or ti is None or hi >= len(rows[0]):
        return None, 0.0
    return _parse_iso(rows[0][hi]), (_f(rows[0][ti]) if ti < len(rows[0]) else 0.0)


def evenements(dossier, header: List[str], rows: List[List[str]]) -> List[dict]:
    """Timestamped events from ``journal.log``, realigned on the CSV's time axis.
    Returns a sorted ``[{"t_s", "msg", "danger"}]``. ``danger`` = safety event
    (same keywords as the timeline)."""
    jp = Path(dossier) / "journal.log"
    t0, t0_ts = _csv_t0(header, rows)
    if not jp.exists() or t0 is None:
        return []
    out: List[dict] = []
    for line in jp.read_text(encoding="utf-8").splitlines():
        if not (line.startswith("[") and "]" in line):
            continue
        stamp, _mid, rest = line[1:].partition("]")
        t_s = _event_t_s(stamp.strip(), t0, t0_ts)
        if t_s is None:
            continue
        msg = rest.strip()
        out.append({"t_s": t_s, "msg": msg,
                    "danger": any(k in msg for k in _DANGER_KW)})
    out.sort(key=lambda e: e["t_s"])
    return out


def trip_info(meta: dict, header: List[str], rows: List[List[str]]) -> Optional[dict]:
    """If the outcome is a safety trip: ``{"t_s", "capteur", "cause"}``.
    ``t_s`` = 1st safety event, realigned; ``capteur`` = sensor name found in the
    cause (None if not found). Returns None otherwise."""
    issue = meta.get("issue") or {}
    if issue.get("issue") != "declenchement_securite":
        return None
    t0, t0_ts = _csv_t0(header, rows)
    t_trip = None
    for ev in (meta.get("evenements_securite") or []):
        ts = _event_t_s(str(ev.get("horodatage", "")), t0, t0_ts)
        if ts is not None:
            t_trip = ts
            break
    if t_trip is None:                # fallback: 1st danger line of the log
        for e in evenements("", header, rows):
            if e["danger"]:
                t_trip = e["t_s"]
                break
    cause = issue.get("cause", "") or ""
    capteur = next((n for n in _sensor_names(header) if n in cause), None)
    return {"t_s": t_trip, "capteur": capteur, "cause": cause}


# ------------------------------------------------------------------- formatting
def _esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _duree(meta: dict) -> str:
    a, b = _parse_iso(meta.get("debut", "")), _parse_iso(meta.get("fin", ""))
    if not a or not b:
        return "—"
    secs = max(0, int((b - a).total_seconds()))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h} h {m:02d} min {s:02d} s" if h else f"{m} min {s:02d} s"


def _mmm_cells(m: Optional[Tuple[float, float, float]], nd: int, unit: str) -> str:
    if m is None:
        return "<td>—</td><td>—</td><td>—</td>"
    lo, hi, avg = m
    return (f"<td align='right'>{_fr(lo, nd)}&nbsp;{unit}</td>"
            f"<td align='right'>{_fr(hi, nd)}&nbsp;{unit}</td>"
            f"<td align='right'>{_fr(avg, nd)}&nbsp;{unit}</td>")


# ------------------------------------------------------------ outcome / banners
def _issue_html(meta: dict) -> str:
    issue = (meta.get("issue") or {}).get("issue", "en_cours")
    cause = (meta.get("issue") or {}).get("cause", "")
    if issue == "termine":
        return (f"<span style='color:{OK_GREEN}; font-weight:bold;'>"
                f"{_('Completed without safety event')}</span>")
    if issue == "arret_utilisateur":
        return (f"<span style='color:{NEUTRAL}; font-weight:bold;'>"
                f"{_('Interrupted by the user')}</span>")
    if issue == "declenchement_securite":
        return (f"<span style='color:{DANGER}; font-weight:bold;'>"
                f"{_('SAFETY TRIP')}&nbsp;: {_esc(cause)}</span>")
    return f"<span style='color:{NEUTRAL};'>{_('In progress')}</span>"


def _sim_bandeau() -> str:
    return (f"<table width='100%' cellpadding='6' style='margin:6px 0;'>"
            f"<tr><td bgcolor='{SIM_BG}' align='center'>"
            f"<span style='color:{SIM_FG}; font-weight:bold;'>"
            f"{_('⚠ SIMULATION TEST — no real hardware driven')}</span>"
            "</td></tr></table>")


def _section(titre: str) -> str:
    # ``titre`` is always a literal label (never user data).
    return (f"<h2 style='color:{ACCENT}; border-bottom:2px solid {ACCENT}; "
            f"padding-bottom:2px; margin-top:22px;'>{titre}</h2>")


def _th_row(cells: List[str]) -> str:
    tds = "".join(f"<td bgcolor='{ACCENT_LIGHT}'><b>{c}</b></td>" for c in cells)
    return f"<tr>{tds}</tr>"


# ------------------------------------------------------------- layer 1 (HTML)
def construire_html(dossier, conclusion: str = "", images: Dict[str, str] = {}) -> str:
    """Builds the HTML report of a test folder (pure Python, no Qt).

    ``conclusion``: the operator's free-text field (the report itself issues no
    verdict). ``images`` maps ``courbes_vi``/``courbes_temp`` to PNG paths to
    reference; the function does not generate the images.
    """
    dossier = Path(dossier)
    meta = _read_json(dossier / "essai.json")
    cfg = _read_json(dossier / "config.json")
    header, rows = _read_csv(dossier)
    sim = meta.get("mode") == "simulation"
    warnings = {name: (t.get("warning") if isinstance(t, dict) else None)
                for name, t in (cfg.get("temperatures") or {}).items()}
    criticals = {name: (t.get("critical") if isinstance(t, dict) else None)
                 for name, t in (cfg.get("temperatures") or {}).items()}

    parts: List[str] = []
    parts.append(
        "<html><head><meta charset='utf-8'>"
        "<style>body{font-family:sans-serif; color:#222; font-size:11pt;} "
        "table{border-collapse:collapse;} "
        "td{border:1px solid #BBB; padding:3px 7px;} "
        "h1{color:%s;} .muted{color:%s;}</style></head><body>" % (ACCENT, NEUTRAL))

    # --- Header ---
    badge_bg, badge_txt = (SIM_BG, _("SIMULATION")) if sim else ("#E2EFDA", _("REAL HARDWARE"))
    # Logo (copied into the folder by generer_rapport -> the HTML stays self-contained).
    if (dossier / "logo.png").exists():
        parts.append("<p style='margin:0 0 4px;'><img src='logo.png' height='90'></p>")
    parts.append(
        f"<h1 style='margin-bottom:2px;'>{_('Test report — ALIM_SEQ')}</h1>"
        f"<span style='background:{badge_bg}; padding:2px 8px; font-weight:bold;'>"
        f"{badge_txt}</span>")
    parts.append("<table width='100%' style='margin-top:10px;'>")
    nom_txt = _esc(meta.get('nom')) or f"<i>{_('(unnamed)')}</i>"
    op_txt = _esc(meta.get('operateur')) or f"<i>{_('(not provided)')}</i>"
    parts.append(f"<tr><td bgcolor='{ACCENT_LIGHT}'><b>{_('Test name')}</b></td>"
                 f"<td>{nom_txt}</td>"
                 f"<td bgcolor='{ACCENT_LIGHT}'><b>{_('Operator')}</b></td>"
                 f"<td>{op_txt}</td></tr>")
    parts.append(f"<tr><td bgcolor='{ACCENT_LIGHT}'><b>{_('Start')}</b></td>"
                 f"<td>{_esc(meta.get('debut'))}</td>"
                 f"<td bgcolor='{ACCENT_LIGHT}'><b>{_('Duration')}</b></td>"
                 f"<td>{_duree(meta)}</td></tr>")
    parts.append(f"<tr><td bgcolor='{ACCENT_LIGHT}'><b>{_('ALIM_SEQ version')}</b></td>"
                 f"<td>{_esc(meta.get('version'))}</td>"
                 f"<td bgcolor='{ACCENT_LIGHT}'><b>{_('Mode')}</b></td>"
                 f"<td>{badge_txt}</td></tr>")
    parts.append("</table>")

    if sim:
        parts.append(_sim_bandeau())

    # --- Summary ---
    parts.append(_section(_("Summary")))
    sha = str(meta.get("config_sha256") or "")
    sha_short = (sha[:12] + "…") if sha else "—"
    src = meta.get("config_source") or _("in-memory configuration (serialized)")
    # General summary: number of points, actual rate, CSV size.
    idx_t = {h: i for i, h in enumerate(header)}.get("t_s")
    span = None
    if rows and idx_t is not None and idx_t < len(rows[0]) and idx_t < len(rows[-1]):
        span = _f(rows[-1][idx_t]) - _f(rows[0][idx_t])
    cad = (len(rows) / span) if (span and span > 0) else None
    try:
        csv_kio = (dossier / "mesures.csv").stat().st_size / 1024
    except OSError:
        csv_kio = None
    parts.append("<table width='100%'>")
    parts.append(f"<tr><td bgcolor='{ACCENT_LIGHT}'><b>{_('Test outcome')}</b></td>"
                 f"<td>{_issue_html(meta)}</td></tr>")
    csv_note = "" if csv_kio is None else _(" · CSV {} KiB").format(_fr(csv_kio, 0))
    pts = _("{} points · {} pt/s").format(len(rows), _fr(cad, 2))
    parts.append(f"<tr><td bgcolor='{ACCENT_LIGHT}'><b>{_('Measurement points')}</b></td>"
                 f"<td>{pts}{csv_note}</td></tr>")
    parts.append(f"<tr><td bgcolor='{ACCENT_LIGHT}'><b>{_('Configuration')}</b></td>"
                 f"<td>{_esc(src)}<br><span class='muted'>SHA-256 : {_esc(sha_short)}</span></td></tr>")
    parts.append("</table>")

    # --- Operator conclusion ---
    parts.append(_section(_("Operator conclusion")))
    if conclusion.strip():
        parts.append(f"<p style='white-space:pre-wrap;'>{_esc(conclusion)}</p>")
    else:
        parts.append(f"<p class='muted'><i>{_('(not provided)')}</i></p>")
    # Sign-off area (labs sign it by hand).
    parts.append(
        "<table width='60%' style='margin-top:12px;'>"
        f"<tr><td bgcolor='{ACCENT_LIGHT}' width='55%'><b>{_('Operator sign-off')}</b></td>"
        f"<td bgcolor='{ACCENT_LIGHT}'><b>{_('Date')}</b></td></tr>"
        "<tr><td style='height:52px;'>&nbsp;</td><td>&nbsp;</td></tr></table>")

    # --- Charts ---
    if images:
        parts.append(_section(_("Charts")))
        if sim:
            parts.append(_sim_bandeau())
        captions = {"courbes": _("Measurements during the test (with events)"),
                    "courbes_zoom": _("Zoom on the safety trip"),
                    "courbes_vi": _("Voltages and currents"), "courbes_temp": _("Temperatures")}
        for key, src_img in images.items():
            if not src_img:
                continue
            cap = captions.get(key, "")
            if cap:
                parts.append(f"<p><b>{_esc(cap)}</b></p>")
            # The actual width is fixed at print time (see exporter_pdf); this
            # value is only used for the HTML preview in a browser.
            parts.append(f"<p><img src='{_esc(src_img)}' width='620'></p>")
            # Legend of the numbered markers carried on the measurements chart.
            if key == "courbes":
                parts.append(_reperes_evenements_html(dossier, header, rows))

    # --- Per-channel statistics ---
    parts.append(_section(_("Per-channel statistics")))
    if sim:
        parts.append(_sim_bandeau())
    sv = stats_voies(header, rows)
    if sv:
        parts.append("<table width='100%'>")
        parts.append(_th_row([_("Channel"), _("V min"), _("V max"), _("V avg"),
                              _("I min"), _("I max"), _("I avg"), _("CC time"),
                              _("End setpoint")]))
        for label, s in sv.items():
            cc = "—"
            if s["cc_s"] > 0:
                cc = f"{_fr(s['cc_s'], 1)}&nbsp;s"
                if s["cc_pct"] is not None:
                    cc += f" ({_fr(s['cc_pct'], 0)}&nbsp;%)"
            cc_col = f" style='color:{DANGER};'" if s["cc_s"] > 0 else ""
            cf = s["consigne_fin"]
            cf_txt = "—" if cf is None else f"{_fr(cf[0], 2)}&nbsp;V / {_fr(cf[1], 3)}&nbsp;A"
            parts.append(
                "<tr><td><b>%s</b></td>%s%s<td align='right'%s>%s</td>"
                "<td align='right'>%s</td></tr>" % (
                    _esc(label), _mmm_cells(s["v"], 3, "V"), _mmm_cells(s["i"], 3, "A"),
                    cc_col, cc, cf_txt))
        parts.append("</table>")
    else:
        parts.append(f"<p class='muted'>{_('No channel recorded.')}</p>")

    # --- Per-sensor statistics ---
    sc = stats_capteurs(header, rows, warnings, criticals)
    if sc:
        parts.append(_section(_("Per-sensor statistics")))
        if sim:
            parts.append(_sim_bandeau())
        parts.append("<table width='100%'>")
        parts.append(_th_row([_("Sensor"), _("min"), _("max"), _("avg"), _("Warning"),
                              _("Excursions"), _("Time &gt; warning"), _("Time &gt; critical")]))

        def _dur(v):
            return f"{_fr(v, 1)}&nbsp;s" if v and v > 0 else "—"

        for name, s in sc.items():
            warn = s["warning"]
            crit_col = f" style='color:{DANGER};'" if s["critique_s"] > 0 else ""
            parts.append(
                "<tr><td><b>%s</b></td>%s<td align='right'>%s</td>"
                "<td align='right'>%s</td><td align='right'>%s</td>"
                "<td align='right'%s>%s</td></tr>" % (
                    _esc(name), _mmm_cells(s["c"], 1, "°C"),
                    (f"{_fr(warn, 0)}&nbsp;°C" if warn is not None else "—"),
                    (str(s["excursions"]) if s["excursions"] else "—"),
                    _dur(s["alerte_s"]), crit_col, _dur(s["critique_s"])))
        parts.append("</table>")

    # --- Timeline ---
    parts.append(_section(_("Timeline")))
    parts.append(_chronologie_html(dossier, meta))

    # --- Appendices ---
    parts.append(_section(_("Appendix A — Executed sequence")))
    seq = dossier / "sequence.seq"
    if seq.exists():
        parts.append("<pre style='font-family:monospace; background:#F5F5F5; "
                     "border:1px solid #DDD; padding:6px; white-space:pre-wrap;'>"
                     f"{_esc(seq.read_text(encoding='utf-8'))}</pre>")
    else:
        parts.append(f"<p class='muted'>{_('No sequence (manual control).')}</p>")

    parts.append(_section(_("Appendix B — Configuration")))
    # Readable summary BEFORE the raw JSON.
    chans = cfg.get("channels") or {}
    if chans:
        parts.append(f"<p><b>{_('Channels')}</b></p><table width='100%'>")
        parts.append(_th_row([_("Label"), _("Supply / Channel"), _("V max"), _("I max")]))
        for lbl, c in chans.items():
            if not isinstance(c, dict):
                continue
            parts.append("<tr><td><b>%s</b></td><td>%s / %s</td>"
                         "<td align='right'>%s&nbsp;V</td>"
                         "<td align='right'>%s&nbsp;A</td></tr>" % (
                             _esc(lbl), _esc(c.get("supply")), _esc(c.get("channel")),
                             _fr(c.get("max_voltage"), 1), _fr(c.get("max_current"), 3)))
        parts.append("</table>")
    temps_cfg = cfg.get("temperatures") or {}
    if temps_cfg:
        parts.append(f"<p style='margin-top:8px;'><b>{_('Sensors')}</b></p><table width='100%'>")
        parts.append(_th_row([_("Name"), _("Warning"), _("Critical"), _("Converter")]))
        for nm, t in temps_cfg.items():
            if not isinstance(t, dict):
                continue
            conv = (t.get("converter") or {}).get("type", "identity")
            parts.append("<tr><td><b>%s</b></td><td align='right'>%s&nbsp;°C</td>"
                         "<td align='right'>%s&nbsp;°C</td><td>%s</td></tr>" % (
                             _esc(nm), _fr(t.get("warning"), 0),
                             _fr(t.get("critical"), 0), _esc(conv)))
        parts.append("</table>")
    parts.append(f"<p style='margin-top:8px;'><b>{_('Full JSON')}</b></p>")
    parts.append("<pre style='font-family:monospace; background:#F5F5F5; "
                 "border:1px solid #DDD; padding:6px; white-space:pre-wrap;'>"
                 f"{_esc(json.dumps(cfg, indent=2, ensure_ascii=False))}</pre>")

    parts.append("</body></html>")
    return "".join(parts)


def _reperes_evenements_html(dossier, header: List[str], rows: List[List[str]]) -> str:
    """Legend of the **numbered markers** carried on the measurements chart.

    Uses the SAME list (and the same chronological order) as the chart's badges
    (:func:`evenements`): the table's number ``n`` matches the chart's badge
    ``n``. Empty if there is no event."""
    evs = evenements(dossier, header, rows)
    if not evs:
        return ""
    out = [f"<p class='muted' style='margin:6px 0 4px;'>"
           f"{_('Event markers (numbers refer to the chart badges):')}</p>",
           "<table width='100%'>"]
    for i, e in enumerate(evs, start=1):
        mm, ss = divmod(int(e["t_s"]), 60)
        col = f" style='color:{DANGER}; font-weight:bold;'" if e["danger"] else ""
        out.append(f"<tr><td align='center' width='34'><b>{i}</b></td>"
                   f"<td align='right' width='70'>+{mm}:{ss:02d}</td>"
                   f"<td{col}>{_esc(e['msg'])}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _chronologie_html(dossier: Path, meta: dict) -> str:
    """Log events, timestamped relative to the start of the test."""
    jp = dossier / "journal.log"
    if not jp.exists():
        return f"<p class='muted'>{_('Log unavailable.')}</p>"
    debut = _parse_iso(meta.get("debut", ""))
    lines = jp.read_text(encoding="utf-8").splitlines()
    rows_html: List[str] = []
    for line in lines:
        rel = ""
        msg = line
        if line.startswith("[") and "]" in line:
            stamp, _mid, rest = line[1:].partition("]")
            msg = rest.strip()
            rel = _relatif(stamp.strip(), debut)
        danger = any(k in msg for k in _DANGER_KW)
        col = f" style='color:{DANGER}; font-weight:bold;'" if danger else ""
        rows_html.append(f"<tr><td align='right' width='90'>{_esc(rel)}</td>"
                         f"<td{col}>{_esc(msg)}</td></tr>")
    if not rows_html:
        return f"<p class='muted'>{_('No event.')}</p>"
    return "<table width='100%'>" + "".join(rows_html) + "</table>"


def _relatif(hms: str, debut: Optional[datetime]) -> str:
    """'hh:mm:ss' offset of the log entry relative to the start of the test, as
    +M:SS."""
    if debut is None:
        return hms
    try:
        h, m, s = (int(x) for x in hms.split(":"))
    except ValueError:
        return hms
    log_secs = h * 3600 + m * 60 + s
    base = debut.hour * 3600 + debut.minute * 60 + debut.second
    delta = log_secs - base
    if delta < 0:              # midnight rollover: realigns on 24 h
        delta += 24 * 3600
    mm, ss = divmod(delta, 60)
    return f"+{mm}:{ss:02d}"


# ------------------------------------------------------ layer 2 (charts + PDF)
def _series_from_csv(header, rows, suffix):
    """Builds ``{label: [(t, value)]}`` from the columns ending in ``suffix``."""
    idx = {h: i for i, h in enumerate(header)}
    t_i = idx.get("t_s")
    labels = [h[:-len(suffix)] for h in header if h.endswith(suffix)]
    series = {}
    for label in labels:
        ci = idx[label + suffix]
        pts = []
        for r in rows:
            if t_i is None or ci >= len(r) or t_i >= len(r):
                continue
            pts.append((_f(r[t_i]), _f(r[ci])))
        series[label] = pts
    return series


def rendre_graphiques(dossier, out_dir) -> Dict[str, str]:
    """Plots V/I (two stacked panels) and temperatures with **matplotlib** (Agg
    backend, no window), from ``mesures.csv``, and writes two PNGs into
    ``out_dir``. Returns ``{"courbes_vi": name, "courbes_temp": name}`` (names
    relative to ``out_dir``).

    Uses the ``Figure``/``FigureCanvasAgg`` object API (not ``pyplot``): no global
    state -> safe from a worker thread. If matplotlib is absent, does not raise:
    returns ``{}`` and the report is generated without charts."""
    try:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
    except ImportError:
        return {}

    dossier, out_dir = Path(dossier), Path(out_dir)
    header, rows = _read_csv(dossier)
    cfg = _read_json(dossier / "config.json")
    if not header or not rows:
        return {}
    meta = _read_json(dossier / "essai.json")
    evs = evenements(dossier, header, rows)
    trip = trip_info(meta, header, rows)

    volts = _series_from_csv(header, rows, "_Vmeas")
    currents = _series_from_csv(header, rows, "_Imeas")
    temps = _series_from_csv(header, rows, "_C")

    # FIXED categorical palette, not cycled (data-viz reference, validated: CVD
    # ΔE 24.2 on white; contrast relief is carried by each panel's legend).
    # One entity = one color: a rail keeps ITS color on the V and I panels.
    # Red (#e34948) placed LAST: reserved for the "critical" status below, it only
    # serves as a series color if there are more than 7 channels (rare case).
    _CAT = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e87ba4",
            "#eb6834", "#e34948"]
    _MUTED = "#898781"      # discreet ink (axes, non-danger events)
    _WARN = "#d98c00"       # "warning" STATUS (warning threshold) — reserved, never a series
    _CRIT = "#d03b3b"       # "critical" STATUS (threshold + trip) — reserved
    accent = "#1F4E79"

    def _palette(labels):
        return {lab: _CAT[i % len(_CAT)] for i, lab in enumerate(labels)}

    col_ch = _palette(list(volts) or list(currents))   # shared V <-> I (same rail)
    col_ts = _palette(list(temps))

    def _xy(series, label):
        pts = series[label]
        return [t for t, _v in pts], [v for _t, v in pts]

    def _style(ax):
        ax.grid(True, which="major", alpha=0.30, linewidth=0.6, color="#c9c8c2")
        ax.grid(True, which="minor", alpha=0.14, linewidth=0.4, color="#d8d7d1")
        ax.minorticks_on()
        ax.set_axisbelow(True)
        ax.margins(x=0.0)
        ax.tick_params(labelsize=9, colors="#52514e")
        for s in ax.spines.values():
            s.set_edgecolor("#c3c2b7")
            s.set_linewidth(0.8)
        ax.yaxis.label.set_size(10.5)
        ax.xaxis.label.set_size(10.5)

    def _legend(ax, handles=None, labels=None):
        # Legend placed OUTSIDE to the right: never hides the curves (bbox_inches
        # tight on save includes it without cropping).
        args = (handles, labels) if handles is not None else ()
        ax.legend(*args, loc="upper left", bbox_to_anchor=(1.012, 1.0),
                  fontsize=8.5, frameon=True, framealpha=0.96, edgecolor="#d8d7d1",
                  borderaxespad=0.0, handlelength=1.6)

    def _trace(ax, series, colors, ylabel):
        # White outline under each stroke: visually separates crossing curves
        # (the "surface ring" rule for overlapping marks).
        import matplotlib.patheffects as pe
        stroke = [pe.Stroke(linewidth=3.4, foreground="white", alpha=0.7), pe.Normal()]
        for label in series:
            xs, ys = _xy(series, label)
            ax.plot(xs, ys, lw=2.0, solid_capstyle="round", color=colors[label],
                    label=label, path_effects=stroke)
        ax.set_ylabel(ylabel)
        _style(ax)
        if series:
            _legend(ax)

    # --- Anti-collision placement of events BEFORE sizing the figure.
    # Each event gets a number (chronological order) reported in the report
    # ("Event markers"): the chart only carries the NUMBER, no more overlapping
    # text running across it.
    for i, e in enumerate(evs, start=1):
        e["_n"] = i
    _allt = [t for s in (volts, currents, temps) for pts in s.values() for t, _v in pts]
    t0v, t1v = (min(_allt), max(_allt)) if _allt else (0.0, 1.0)
    min_dx = max(t1v - t0v, 1e-9) * 0.022      # two closer badges -> stacked
    ev_row: List[int] = []
    row_last: List[float] = []
    for e in evs:
        placed = next((r for r in range(len(row_last))
                       if e["t_s"] - row_last[r] >= min_dx), -1)
        if placed < 0:
            placed = len(row_last)
            row_last.append(e["t_s"])
        else:
            row_last[placed] = e["t_s"]
        ev_row.append(placed)
    n_rows = max(len(row_last), 1)

    # A SINGLE multi-panel figure: event strip (optional) + V + I + temperatures.
    # Shared time axis; held on a dedicated PDF page.
    has_temp = bool(temps)
    n_panels = 3 if has_temp else 2
    strip_h = (0.34 + 0.24 * n_rows) if evs else 0.0
    heights = ([strip_h] if evs else []) + [3.0] * n_panels
    fig = Figure(figsize=(11, sum(heights) + 1.1), dpi=200)
    fig.set_facecolor("white")
    gs = fig.add_gridspec(len(heights), 1, height_ratios=heights, hspace=0.17)

    off = 1 if evs else 0
    ax_v = fig.add_subplot(gs[off])
    ax_i = fig.add_subplot(gs[off + 1], sharex=ax_v)
    _trace(ax_v, volts, col_ch, _("Measured voltage (V)"))
    _trace(ax_i, currents, col_ch, _("Measured current (A)"))
    ax_v.tick_params(labelbottom=False)
    axes = [ax_v, ax_i]

    if has_temp:
        seuils = {name: (t.get("warning"), t.get("critical"))
                  for name, t in (cfg.get("temperatures") or {}).items()
                  if isinstance(t, dict)}
        ax_t = fig.add_subplot(gs[off + 2], sharex=ax_v)
        import matplotlib.patheffects as pe
        stroke = [pe.Stroke(linewidth=3.4, foreground="white", alpha=0.7), pe.Normal()]
        for label in temps:
            xs, ys = _xy(temps, label)
            ax_t.plot(xs, ys, lw=2.0, solid_capstyle="round", color=col_ts[label],
                      label=label, path_effects=stroke)
        # Thresholds plotted in STATUS colors (never a series color): read as
        # LIMITS. One line per distinct level (deduplicated).
        for w in sorted({s[0] for s in seuils.values() if s[0] is not None}):
            ax_t.axhline(w, color=_WARN, ls="--", lw=1.0, alpha=0.85, zorder=1)
        for c in sorted({s[1] for s in seuils.values() if s[1] is not None}):
            ax_t.axhline(c, color=_CRIT, ls=":", lw=1.3, alpha=0.9, zorder=1)
        ax_t.set_ylabel(_("Temperature (°C)"))
        _style(ax_t)
        from matplotlib.lines import Line2D
        h, lab = ax_t.get_legend_handles_labels()
        h += [Line2D([0], [0], color=_WARN, ls="--", lw=1.3),
              Line2D([0], [0], color=_CRIT, ls=":", lw=1.6)]
        lab += [_("warning threshold"), _("critical threshold")]
        _legend(ax_t, h, lab)
        ax_i.tick_params(labelbottom=False)
        axes.append(ax_t)

    axes[-1].set_xlabel(_("Time (s)"))

    # Vertical event guides on the panels (WITHOUT text): solid red (safety) or
    # dashed grey (log), in the background.
    for ax in axes:
        for e in evs:
            if e["danger"]:
                ax.axvline(e["t_s"], color=_CRIT, lw=1.2, alpha=0.75, zorder=0)
            else:
                ax.axvline(e["t_s"], color=_MUTED, ls=(0, (2, 2)), lw=0.8,
                           alpha=0.45, zorder=0)

    # Event strip: NUMBERED badges stacked so they never overlap.
    if evs:
        ax_ev = fig.add_subplot(gs[0], sharex=ax_v)
        ax_ev.set_ylim(-0.6, n_rows - 0.4)
        ax_ev.set_yticks([])
        for spn in ax_ev.spines.values():
            spn.set_visible(False)
        ax_ev.tick_params(labelbottom=False, length=0)
        for e, r in zip(evs, ev_row):
            y = n_rows - 1 - r
            col = _CRIT if e["danger"] else _MUTED
            ax_ev.plot([e["t_s"]], [y], marker="o", ms=13, mfc=col, mec="white",
                       mew=1.0, zorder=4)
            ax_ev.annotate(str(e["_n"]), xy=(e["t_s"], y), ha="center", va="center",
                           fontsize=7.2, color="white", fontweight="bold", zorder=5)
        title_ax = ax_ev
    else:
        title_ax = ax_v
    title_ax.set_title(_("Measurements during the test"), fontsize=15, fontweight="bold",
                       color=accent, pad=10)

    fig.align_ylabels(axes)
    fig.subplots_adjust(left=0.10, right=0.83, top=0.955, bottom=0.055)
    FigureCanvasAgg(fig)
    fig.savefig(str(out_dir / "courbes.png"), facecolor="white",
                bbox_inches="tight", pad_inches=0.15)
    out = {"courbes": "courbes.png"}

    # Zoom on the trip: ONLY if the outcome is a safety trip.
    if trip and trip.get("t_s") is not None and temps:
        z = _rendre_zoom(out_dir, temps, cfg, trip)
        if z:
            out["courbes_zoom"] = z
    return out


def _rendre_zoom(out_dir, temps, cfg, trip) -> Optional[str]:
    """Zoom chart ±30 s around the trip: offending sensor in a thick line, its
    warning/critical thresholds, shaded critical zone, trip instant. Window
    bounded to the test. Writes ``courbes_zoom.png``."""
    try:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
    except ImportError:
        return None
    t_trip = trip["t_s"]
    capteur = trip.get("capteur")
    all_t = [t for pts in temps.values() for t, _v in pts]
    if not all_t:
        return None
    lo = max(t_trip - 30, min(all_t))
    hi = min(t_trip + 30, max(all_t))
    if hi - lo < 2:                     # test too short -> nominal ±30 s window
        lo, hi = t_trip - 30, t_trip + 30
    seuils = {n: (t.get("warning"), t.get("critical"))
              for n, t in (cfg.get("temperatures") or {}).items() if isinstance(t, dict)}

    fig = Figure(figsize=(11, 4.2), dpi=200)
    fig.set_facecolor("white")
    ax = fig.add_subplot(111)
    for label, pts in temps.items():
        xs = [t for t, _v in pts if lo <= t <= hi]
        ys = [v for t, v in pts if lo <= t <= hi]
        if not xs:
            continue
        thick = (label == capteur)
        ax.plot(xs, ys, lw=(3.0 if thick else 1.2), alpha=(1.0 if thick else 0.45),
                solid_capstyle="round",
                label=(label + _(" (cause)")) if thick else label)
    warn, crit = seuils.get(capteur, (None, None)) if capteur else (None, None)
    # Reserved STATUS colors (same as the main chart).
    _WARN, _CRIT = "#d98c00", "#d03b3b"
    if warn is not None:
        ax.axhline(warn, color=_WARN, ls="--", lw=1.2, label=_("warning threshold"))
    if crit is not None:
        top = max(ax.get_ylim()[1], crit + 1)
        ax.axhspan(crit, top, color=_CRIT, alpha=0.06)
        ax.axhline(crit, color=_CRIT, ls=":", lw=1.6, label=_("critical threshold"))
    ax.axvline(t_trip, color=_CRIT, lw=1.8)
    ax.annotate(_("trip"), xy=(t_trip, ax.get_ylim()[1]), xytext=(3, -2),
                textcoords="offset points", color=_CRIT, fontsize=8, va="top")
    ax.set_xlim(lo, hi)
    ax.set_xlabel(_("Time (s)"))
    ax.set_ylabel(_("Temperature (°C)"))
    ax.set_title(_("Zoom on the trip"), fontsize=13, fontweight="bold",
                 color="#1F4E79", pad=10)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="best", framealpha=0.9)
    FigureCanvasAgg(fig)
    fig.savefig(str(Path(out_dir) / "courbes_zoom.png"), facecolor="white",
                bbox_inches="tight", pad_inches=0.15)
    return "courbes_zoom.png"


def exporter_pdf(dossier, out_pdf, conclusion: str = "", images=None) -> None:
    """Generates the report's PDF via **ReportLab** (pure Python, no Qt).

    Builds the complete report (header, summary, conclusion, charts, statistics,
    timeline, appendices) from the test folder's artifacts alone and the
    ``images`` already produced by :func:`rendre_graphiques` (dict
    ``{key: filename}``). Professional layout: centered full-width tables,
    colored headers, zebra stripes, paginated footer. Raises ``RuntimeError`` if
    reportlab is not installed."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, Image, Preformatted,
                                        HRFlowable, PageBreak)
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(_("reportlab is required to generate the report PDF "
                             "(pip install reportlab).")) from exc
    import xml.sax.saxutils as _sx

    dossier, out_pdf = Path(dossier), Path(out_pdf)
    images = images or {}
    meta = _read_json(dossier / "essai.json")
    cfg = _read_json(dossier / "config.json")
    header, rows = _read_csv(dossier)
    sim = meta.get("mode") == "simulation"
    warnings = {n: (t.get("warning") if isinstance(t, dict) else None)
                for n, t in (cfg.get("temperatures") or {}).items()}
    criticals = {n: (t.get("critical") if isinstance(t, dict) else None)
                 for n, t in (cfg.get("temperatures") or {}).items()}

    ACC = colors.HexColor(ACCENT)
    ZEB = colors.HexColor("#EEF3F9")
    LINE = colors.HexColor("#E0E0E0")
    RED = colors.HexColor(DANGER)
    CW = A4[0] - 30 * mm
    def esc(s):
        return _sx.escape("" if s is None else str(s))

    base = getSampleStyleSheet()
    st_h1 = ParagraphStyle("t1", parent=base["Title"], textColor=ACC, fontSize=19,
                           alignment=0, spaceAfter=1)
    st_h2 = ParagraphStyle("t2", parent=base["Heading2"], textColor=ACC,
                           fontSize=12.5, spaceBefore=2, spaceAfter=2)
    st_b = ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=13)
    st_m = ParagraphStyle("m", parent=st_b, textColor=colors.HexColor("#6b6b6b"),
                          fontSize=8.6)
    st_cell = ParagraphStyle("c", parent=base["Normal"], fontSize=8.6, leading=11)
    st_cell_d = ParagraphStyle("cd", parent=st_cell, textColor=RED,
                               fontName="Helvetica-Bold")
    st_mono = ParagraphStyle("mono", parent=base["Code"], fontSize=7.6, leading=9.5)

    story = []

    def section(title, new_page=False):
        # ``new_page``: each major part starts at the top of a dedicated page
        # (cover page = Information + Summary + Conclusion grouped together).
        story.append(PageBreak() if new_page else Spacer(1, 9))
        story.append(Paragraph(esc(title), st_h2))
        story.append(HRFlowable(width="100%", thickness=1.4, color=ACC,
                                spaceBefore=1, spaceAfter=5))

    def sim_banner():
        if not sim:
            return
        p = Paragraph(f"<b>{_('SIMULATION TEST — no real hardware driven')}</b>",
                      ParagraphStyle("s", parent=st_b, alignment=1,
                                     textColor=colors.HexColor(SIM_FG)))
        t = Table([[p]], colWidths=[CW])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SIM_BG)),
                               ("TOPPADDING", (0, 0), (-1, -1), 5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.append(t)
        story.append(Spacer(1, 4))

    st_th = ParagraphStyle("th", parent=st_cell, textColor=colors.white,
                           fontName="Helvetica-Bold", fontSize=8.1, leading=9.6)

    def data_table(headers, data, widths, right_from=1, red_cells=()):
        # Headers as Paragraph: wrap onto two lines rather than being truncated
        # when the column is narrow (e.g. "Time > critical").
        head = [Paragraph(esc(h), st_th) for h in headers]
        body = [[c if isinstance(c, Paragraph) else esc(c) for c in r] for r in data]
        t = Table([head] + body, colWidths=widths, repeatRows=1)
        s = [
            ("BACKGROUND", (0, 0), (-1, 0), ACC),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 1), (0, -1), ACC),
            ("ALIGN", (right_from, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEB]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]
        for (r, c) in red_cells:
            s.append(("TEXTCOLOR", (c, r + 1), (c, r + 1), RED))
            s.append(("FONTNAME", (c, r + 1), (c, r + 1), "Helvetica-Bold"))
        t.setStyle(TableStyle(s))
        return t

    def colored_box(markup, fg_hex, bg_hex):
        p = Paragraph(markup, ParagraphStyle("box", parent=st_b,
                                             textColor=colors.HexColor(fg_hex)))
        t = Table([[p]], colWidths=[CW])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_hex)),
                               ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(fg_hex)),
                               ("TOPPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                               ("LEFTPADDING", (0, 0), (-1, -1), 10),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 10)]))
        story.append(t)

    def image_flow(name):
        p = dossier / name
        if not p.exists():
            return
        im = Image(str(p))
        im._restrictSize(CW, 235 * mm)   # fits on one page, never cropped
        im.hAlign = "CENTER"
        story.append(im)
        story.append(Spacer(1, 4))

    # ---- Header ----
    if (dossier / "logo.png").exists():
        logo = Image(str(dossier / "logo.png"))
        logo._restrictSize(60 * mm, 22 * mm)
        logo.hAlign = "LEFT"
        story.append(logo)
    story.append(Paragraph(_("Test report — ALIM_SEQ"), st_h1))
    badge_txt = _("SIMULATION") if sim else _("REAL HARDWARE")
    badge = Table([[Paragraph(f"<b>{badge_txt}</b>", ParagraphStyle(
        "bd", parent=st_b, textColor=colors.white, fontSize=8.5))]],
        colWidths=[len(badge_txt) * 5.6 + 18])
    badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2b6cb0")),
                               ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    badge.hAlign = "LEFT"
    story.append(Spacer(1, 3))
    story.append(badge)

    # ---- Information ----
    section(_("Information"))
    info = [
        [_("Test name"), meta.get("nom") or _("(unnamed)"),
         _("Operator"), meta.get("operateur") or _("(not provided)")],
        [_("Start"), meta.get("debut", ""), _("Duration"), _duree(meta)],
        [_("ALIM_SEQ version"), meta.get("version", ""), _("Mode"), badge_txt],
    ]
    it = Table([[esc(a), esc(b), esc(c), esc(d)] for a, b, c, d in info],
               colWidths=[CW * x for x in (0.18, 0.32, 0.18, 0.32)])
    it.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(ACCENT_LIGHT)),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor(ACCENT_LIGHT)),
        ("TEXTCOLOR", (0, 0), (0, -1), ACC), ("TEXTCOLOR", (2, 0), (2, -1), ACC),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(it)

    # ---- Summary ----
    section(_("Summary"))
    sim_banner()
    issue = (meta.get("issue") or {}).get("issue", "en_cours")
    cause = (meta.get("issue") or {}).get("cause", "")
    if issue == "termine":
        colored_box(f"<b>{_('Outcome: Completed without safety event')}</b>", OK_GREEN, "#EAF5EA")
    elif issue == "arret_utilisateur":
        colored_box(f"<b>{_('Outcome: Interrupted by the user')}</b>", NEUTRAL, "#F0F0F0")
    elif issue == "declenchement_securite":
        colored_box(f"<b>{_('Outcome: SAFETY TRIP:')} {esc(cause)}</b>",
                    DANGER, "#FDECEC")
    else:
        colored_box(f"<b>{_('Outcome: In progress')}</b>", NEUTRAL, "#F0F0F0")
    idx_t = {h: i for i, h in enumerate(header)}.get("t_s")
    span = None
    if rows and idx_t is not None and idx_t < len(rows[0]) and idx_t < len(rows[-1]):
        span = _f(rows[-1][idx_t]) - _f(rows[0][idx_t])
    cad = (len(rows) / span) if (span and span > 0) else None
    try:
        csv_kio = (dossier / "mesures.csv").stat().st_size / 1024
    except OSError:
        csv_kio = None
    sha = str(meta.get("config_sha256") or "")
    sha_short = (sha[:12] + "…") if sha else "—"
    src = meta.get("config_source") or _("in-memory configuration (serialized)")
    story.append(Spacer(1, 4))
    pts = (_("{} points · {} pt/s").format(len(rows), _fr(cad, 2))
           + ("" if csv_kio is None else _(" · CSV {} KiB").format(_fr(csv_kio, 0))))
    story.append(Paragraph(f"<b>{_('Measurement points:')}</b> {esc(pts)}", st_b))
    story.append(Paragraph(f"<b>{_('Configuration:')}</b> {esc(src)} "
                           f"<font color='#6b6b6b'>(SHA-256 : {esc(sha_short)})</font>", st_b))

    # ---- Operator conclusion ----
    section(_("Operator conclusion"))
    if conclusion.strip():
        story.append(Paragraph(esc(conclusion).replace("\n", "<br/>"), st_b))
    else:
        story.append(Paragraph(f"<i>{_('(not provided)')}</i>", st_m))
    story.append(Spacer(1, 8))
    visa = Table([[Paragraph(f"<b>{_('Operator sign-off')}</b>", st_b),
                   Paragraph(f"<b>{_('Date')}</b>", st_b)],
                  ["", ""]], colWidths=[CW * 0.4, CW * 0.2], rowHeights=[None, 46])
    visa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(ACCENT_LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    visa.hAlign = "LEFT"
    story.append(visa)

    # ---- Charts ----
    if images:
        section(_("Measurements during the test"), new_page=True)
        sim_banner()
        if images.get("courbes"):
            image_flow(images["courbes"])
            evs = evenements(dossier, header, rows)
            if evs:
                story.append(Paragraph(_("Event markers (numbers refer to the chart "
                                         "badges):"), st_m))
                ev_data, red = [], []
                for i, e in enumerate(evs):
                    mm2, ss = divmod(int(e["t_s"]), 60)
                    style = st_cell_d if e["danger"] else st_cell
                    ev_data.append([str(i + 1), f"+{mm2}:{ss:02d}",
                                    Paragraph(esc(e["msg"]), style)])
                    if e["danger"]:
                        red.append((i, 1))
                story.append(data_table([_("No."), _("Time"), _("Event")], ev_data,
                                        [CW * 0.07, CW * 0.11, CW * 0.82],
                                        right_from=99, red_cells=red))
        if images.get("courbes_zoom"):
            story.append(Spacer(1, 6))
            image_flow(images["courbes_zoom"])

    def _mmm3(m, nd, unit):
        if m is None:
            return ["—", "—", "—"]
        return [f"{_fr(m[0], nd)} {unit}", f"{_fr(m[1], nd)} {unit}",
                f"{_fr(m[2], nd)} {unit}"]

    # ---- Per-channel statistics ----
    section(_("Per-channel statistics"), new_page=True)
    sim_banner()
    sv = stats_voies(header, rows)
    if sv:
        data, red = [], []
        for k, (label, s) in enumerate(sv.items()):
            cc = "—"
            if s["cc_s"] > 0:
                cc = f"{_fr(s['cc_s'], 1)} s"
                if s["cc_pct"] is not None:
                    cc += f" ({_fr(s['cc_pct'], 0)} %)"
                red.append((k, 7))
            cf = s["consigne_fin"]
            cf_txt = "—" if cf is None else f"{_fr(cf[0], 2)} V / {_fr(cf[1], 3)} A"
            data.append([label, *_mmm3(s["v"], 3, "V"), *_mmm3(s["i"], 3, "A"), cc, cf_txt])
        w = [CW * x for x in (.10, .108, .108, .108, .108, .108, .108, .12, .132)]
        story.append(data_table(
            [_("Channel"), _("V min"), _("V max"), _("V avg"), _("I min"), _("I max"),
             _("I avg"), _("CC time"), _("End setpoint")], data, w, red_cells=red))
        story.append(Paragraph(
            _("“CC time” = time spent in current limiting (CC mode); "
              "“End setpoint” = voltage / current requested at end of test."), st_m))
    else:
        story.append(Paragraph(_("No channel recorded."), st_m))

    # ---- Per-sensor statistics ----
    sc = stats_capteurs(header, rows, warnings, criticals)
    if sc:
        section(_("Per-sensor statistics"), new_page=True)
        sim_banner()

        def _dur(v):
            return f"{_fr(v, 1)} s" if v and v > 0 else "—"

        data, red = [], []
        for k, (name, s) in enumerate(sc.items()):
            if s["critique_s"] > 0:
                red.append((k, 7))
            data.append([name, *_mmm3(s["c"], 1, "°C"),
                         (f"{_fr(s['warning'], 0)} °C" if s["warning"] is not None else "—"),
                         (str(s["excursions"]) if s["excursions"] else "—"),
                         _dur(s["alerte_s"]), _dur(s["critique_s"])])
        w = [CW * x for x in (.15, .105, .105, .105, .11, .14, .13, .155)]
        story.append(data_table(
            [_("Sensor"), _("min"), _("max"), _("avg"), _("Warning threshold"),
             _("Excursions"), _("Time > warning"), _("Time > critical")], data, w, red_cells=red))
        story.append(Paragraph(
            _("“Excursions” = number of times the temperature crossed the warning "
              "threshold (rises); durations are cumulative over the whole test."),
            st_m))

    # ---- Timeline ----
    section(_("Timeline"), new_page=True)
    debut = _parse_iso(meta.get("debut", ""))
    jp = dossier / "journal.log"
    chr_rows = []
    if jp.exists():
        for line in jp.read_text(encoding="utf-8").splitlines():
            rel, msg = "", line
            if line.startswith("[") and "]" in line:
                stamp, _mid, rest = line[1:].partition("]")
                msg = rest.strip()
                rel = _relatif(stamp.strip(), debut)
            danger = any(k in msg for k in _DANGER_KW)
            chr_rows.append([rel, Paragraph(esc(msg), st_cell_d if danger else st_cell)])
    if chr_rows:
        story.append(data_table([_("Time"), _("Event")], chr_rows,
                                [CW * 0.12, CW * 0.88], right_from=99))
    else:
        story.append(Paragraph(_("No event."), st_m))

    # ---- Appendix A — Sequence ----
    section(_("Appendix A — Executed sequence"), new_page=True)
    seq = dossier / "sequence.seq"
    if seq.exists():
        story.append(Preformatted(seq.read_text(encoding="utf-8"), st_mono))
    else:
        story.append(Paragraph(_("No sequence (manual control)."), st_m))

    # ---- Appendix B — Configuration ----
    section(_("Appendix B — Configuration"), new_page=True)
    chans = cfg.get("channels") or {}
    if chans:
        story.append(Paragraph(f"<b>{_('Channels')}</b>", st_b))
        data = [[lbl, f"{c.get('supply')} / {c.get('channel')}",
                 f"{_fr(c.get('max_voltage'), 1)} V", f"{_fr(c.get('max_current'), 3)} A"]
                for lbl, c in chans.items() if isinstance(c, dict)]
        story.append(data_table([_("Label"), _("Supply / Channel"), _("V max"), _("I max")], data,
                                [CW * 0.25, CW * 0.35, CW * 0.2, CW * 0.2], right_from=2))
    tcfg = cfg.get("temperatures") or {}
    if tcfg:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>{_('Sensors')}</b>", st_b))
        data = [[nm, f"{_fr(t.get('warning'), 0)} °C", f"{_fr(t.get('critical'), 0)} °C",
                 (t.get("converter") or {}).get("type", "identity")]
                for nm, t in tcfg.items() if isinstance(t, dict)]
        story.append(data_table([_("Name"), _("Warning"), _("Critical"), _("Converter")], data,
                                [CW * 0.28, CW * 0.2, CW * 0.2, CW * 0.32], right_from=1))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>{_('Full JSON')}</b>", st_b))
    story.append(Preformatted(json.dumps(cfg, indent=2, ensure_ascii=False), st_mono))

    # ---- Assembly: numbered canvas (footer "page X / N" + running header) ----
    from . import __version__
    from reportlab.pdfgen import canvas as _canvas

    nom_essai = meta.get("nom") or ""
    # Cited version = the one that PRODUCED the test (consistent with the
    # "ALIM_SEQ version" box), otherwise the tool's current version.
    version_str = meta.get("version") or __version__

    class _NumberedCanvas(_canvas.Canvas):
        """Two-pass canvas: knows the TOTAL page count (for "X / N") and lays
        out a running header on pages ≥ 2."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._chrome(total)
                super().showPage()
            super().save()

        def _chrome(self, total):
            self.setFillColor(colors.HexColor("#8a8a8a"))
            self.setFont("Helvetica", 8)
            self.drawCentredString(
                A4[0] / 2, 9 * mm,
                _("ALIM_SEQ v{} — page {} / {}").format(
                    version_str, self._pageNumber, total))
            if self._pageNumber > 1:      # running header (not on the cover page)
                self.setFont("Helvetica", 7.5)
                self.setFillColor(colors.HexColor("#a0a09a"))
                self.drawString(15 * mm, A4[1] - 8 * mm, _("Test report — ALIM_SEQ"))
                if nom_essai:
                    self.drawRightString(A4[0] - 15 * mm, A4[1] - 8 * mm, nom_essai)
                self.setStrokeColor(colors.HexColor("#E0E0E0"))
                self.setLineWidth(0.4)
                self.line(15 * mm, A4[1] - 10 * mm, A4[0] - 15 * mm, A4[1] - 10 * mm)

    doc = SimpleDocTemplate(str(out_pdf), pagesize=A4, topMargin=16 * mm,
                            bottomMargin=15 * mm, leftMargin=15 * mm, rightMargin=15 * mm,
                            title=_("Test report — ALIM_SEQ"))
    doc.build(story, canvasmaker=_NumberedCanvas)


def _logo_source() -> Optional[Path]:
    """Path of the logo (report header): PyInstaller bundle or source tree
    (``packaging/logo.png``). Resolved like the application's icon."""
    import sys
    cands = []
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        cands.append(Path(mp) / "logo.png")
    cands.append(Path(__file__).resolve().parents[1] / "packaging" / "logo.png")
    return next((p for p in cands if p.exists()), None)


def generer_rapport(dossier, conclusion=None):
    """Generates ``rapport.html`` + ``rapport.pdf`` INTO the test folder, from its
    artifacts alone (regenerable). ``conclusion`` (str) is persisted in
    ``essai.json`` for later regenerations; ``None`` reuses the one already
    stored. Returns the PDF's path."""
    dossier = Path(dossier)
    meta = _read_json(dossier / "essai.json")
    # Copies the logo INTO the folder -> the HTML stays self-contained (no external ref).
    src_logo = _logo_source()
    if src_logo is not None and not (dossier / "logo.png").exists():
        try:
            import shutil
            shutil.copyfile(src_logo, dossier / "logo.png")
        except OSError:
            pass
    if conclusion is None:
        conclusion = meta.get("conclusion", "")
    else:
        meta["conclusion"] = conclusion
        try:
            (dossier / "essai.json").write_text(
                json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass

    images = rendre_graphiques(dossier, dossier)
    html = construire_html(dossier, conclusion=conclusion, images=images)
    (dossier / "rapport.html").write_text(html, encoding="utf-8")
    pdf = dossier / "rapport.pdf"
    exporter_pdf(dossier, pdf, conclusion=conclusion, images=images)
    return pdf
