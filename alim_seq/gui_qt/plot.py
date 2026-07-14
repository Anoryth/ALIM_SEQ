"""Graphes dessinés au QPainter (sans dépendance) : courbe tension→°C de
l'assistant (CurveView) et strip-chart température temps réel (TempPlotQt).

Le cœur du tracé multi-courbes est extrait dans :func:`dessiner_series`, réutilisé
à l'identique par le widget vivant (thème sombre/clair) ET par le rapport d'essai
(rendu ``dark=False`` sur une ``QImage``) — pas de duplication du code de tracé."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ..controller import FAULT, NA, OK
from . import theme


class CurveView(QtWidgets.QWidget):
    """Mini-graphe tension→°C dessiné au QPainter : aucune dépendance externe,
    couleurs issues de la palette (lisible en thème clair et sombre).
    ``markers`` = points à mettre en évidence (points d'une table d'étalonnage)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(340, 240)
        self._xs: List[float] = []
        self._ys: List[float] = []
        self._mk: List[list] = []
        self.xlabel = QtCore.QCoreApplication.translate("plot", "Voltage (V)")
        self.ylabel = QtCore.QCoreApplication.translate("plot", "Temperature (°C)")

    def set_data(self, xs, ys, markers=None) -> None:
        self._xs, self._ys = list(xs), list(ys)
        self._mk = [list(m) for m in (markers or [])]
        self.update()

    def paintEvent(self, _evt) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        fg = self.palette().color(QtGui.QPalette.WindowText)
        L, R, T, B = 76, self.width() - 14, 12, self.height() - 30
        if R <= L or B <= T:
            return
        p.setPen(QtGui.QPen(fg, 1))
        p.drawRect(L, T, R - L, B - T)
        # Titre d'axe Y (vertical).
        f0 = p.font(); f0.setPointSize(8); p.setFont(f0)
        p.save()
        p.translate(14, (T + B) / 2)
        p.rotate(-90)
        p.drawText(-((B - T) // 2), -2, B - T, 14,
                   QtCore.Qt.AlignCenter, self.ylabel)
        p.restore()
        allx = self._xs + [m[0] for m in self._mk]
        ally = self._ys + [m[1] for m in self._mk]
        if not allx:
            return
        xmin, xmax = min(allx), max(allx)
        ymin, ymax = min(ally), max(ally)
        if xmax == xmin:
            xmax += 1.0
        if ymax == ymin:
            ymax += 1.0
        pad = (ymax - ymin) * 0.08
        ymin -= pad; ymax += pad

        def X(v):
            return L + (v - xmin) / (xmax - xmin) * (R - L)

        def Y(v):
            return B - (v - ymin) / (ymax - ymin) * (B - T)

        grid = QtGui.QColor(fg); grid.setAlpha(45)
        f = p.font(); f.setPointSize(8); p.setFont(f)
        for i in range(5):
            gx = xmin + (xmax - xmin) * i / 4
            sx = int(X(gx))
            p.setPen(QtGui.QPen(grid, 1)); p.drawLine(sx, T, sx, B)
            p.setPen(fg)
            p.drawText(sx - 22, B + 2, 44, 16,
                       QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, f"{gx:.2f}")
            gy = ymin + (ymax - ymin) * i / 4
            sy = int(Y(gy))
            p.setPen(QtGui.QPen(grid, 1)); p.drawLine(L, sy, R, sy)
            p.setPen(fg)
            p.drawText(24, sy - 8, L - 30, 16,
                       QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, f"{gy:.0f}")
        p.setPen(fg)
        p.drawText(L, B + 12, R - L, 16,
                   QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom, f"{self.xlabel} →")

        if len(self._xs) >= 2:
            p.setPen(QtGui.QPen(QtGui.QColor(theme.pair("plot.curve")[1]), 2))
            path = QtGui.QPainterPath()
            path.moveTo(X(self._xs[0]), Y(self._ys[0]))
            for vx, vy in zip(self._xs[1:], self._ys[1:]):
                path.lineTo(X(vx), Y(vy))
            p.drawPath(path)
        if self._mk:
            marker = QtGui.QColor(theme.pair("plot.marker")[1])
            p.setPen(QtGui.QPen(marker, 1))
            p.setBrush(marker)
            for mx, my in self._mk:
                p.drawEllipse(QtCore.QPointF(X(mx), Y(my)), 4, 4)
            p.setBrush(QtCore.Qt.NoBrush)


_PLOT_COLORS = ["#1565c0", "#e53935", "#2e7d32", "#f9a825", "#6a1b9a", "#00838f", "#d84315"]


@dataclass
class PlotGeom:
    """Géométrie renvoyée par :func:`dessiner_series` : rectangle de tracé,
    fenêtre temporelle et rectangles de légende, pour que le widget vivant pose
    ses surcouches interactives (marqueurs, curseur) dans le même repère."""
    L: float
    R: float
    T: float
    B: float
    tmin: float
    tmax: float
    legend_rects: List[Tuple[QtCore.QRect, str]] = field(default_factory=list)
    empty: bool = False

    def X(self, t: float) -> float:
        return self.L + (self.R - self.L) * (t - self.tmin) / max(1e-6, self.tmax - self.tmin)


def dessiner_series(painter: QtGui.QPainter, rect: QtCore.QRect,
                    series: Dict[str, List[Tuple[float, float]]],
                    axes: dict, seuils: Dict[str, Tuple], dark: bool = False) -> PlotGeom:
    """Trace un strip-chart multi-courbes dans ``rect`` (fond transparent).

    ``series`` : ``{nom: [(t, valeur), …]}`` (NaN = rupture du trait) ;
    ``axes``   : ``xlabel``, ``ylabel``, ``unit``, ``temp_mode`` (bool),
    ``window_s``, ``colors`` (``{nom: hex}``), ``hidden`` (``set``) ;
    ``seuils``  : ``{nom: (warning, critical)}`` (tracés en mode température) ;
    ``dark``    : rendu sombre (widget) ou clair (impression du rapport).

    Retourne un :class:`PlotGeom` pour les surcouches interactives (le rapport
    l'ignore)."""
    p = painter
    fg = QtGui.QColor("#E6E6E6" if dark else "#222222")
    L = rect.left() + 58
    R = rect.right() - 12
    T = rect.top() + 12
    B = rect.bottom() - 42
    if R <= L or B <= T:
        return PlotGeom(L, R, T, B, 0.0, 1.0, [], empty=True)
    p.setPen(QtGui.QPen(fg, 1))
    p.drawRect(L, T, R - L, B - T)

    names = list(series.keys())
    hidden = axes.get("hidden") or set()
    colors = axes.get("colors") or {}
    temp_mode = bool(axes.get("temp_mode", False))
    unit = axes.get("unit", "")
    window_s = float(axes.get("window_s", 120.0))

    allpts = [pt for n in names if n not in hidden
              for pt in series[n] if pt[1] == pt[1]]
    if not allpts:
        p.setPen(fg)
        p.drawText(L, T, R - L, B - T, QtCore.Qt.AlignCenter,
                   QtCore.QCoreApplication.translate("plot", "Waiting for data…"))
        return PlotGeom(L, R, T, B, 0.0, 1.0, [], empty=True)
    tmax = max(pt[0] for pt in allpts)
    tmin = max(0.0, tmax - window_s)
    vis = [pt[1] for n in names if n not in hidden for pt in series[n]
           if pt[1] == pt[1] and pt[0] >= tmin]
    vmin, vmax = (min(vis), max(vis)) if vis else (0.0, 1.0)
    if temp_mode:
        for n in names:
            if n in hidden:
                continue
            for thr in seuils.get(n, ()):
                if thr is not None:
                    vmin, vmax = min(vmin, thr), max(vmax, thr)
    span = vmax - vmin
    floor = 5 if temp_mode else 0.1
    if span < floor:
        mid = (vmax + vmin) / 2
        vmin, vmax = mid - floor / 2, mid + floor / 2
    pad = (vmax - vmin) * 0.1
    vmin -= pad; vmax += pad

    def X(t):
        return L + (R - L) * (t - tmin) / max(1e-6, tmax - tmin)

    def Y(v):
        return B - (B - T) * (v - vmin) / max(1e-6, vmax - vmin)

    grid = QtGui.QColor(fg); grid.setAlpha(45)
    f = p.font(); f.setPointSize(8); p.setFont(f)
    for k in range(5):
        gv = vmin + (vmax - vmin) * k / 4
        sy = int(Y(gv))
        p.setPen(QtGui.QPen(grid, 1)); p.drawLine(L, sy, R, sy)
        p.setPen(fg)
        fmt = f"{gv:.0f}" if temp_mode else f"{gv:.2f}"
        p.drawText(0, sy - 8, L - 6, 16,
                   QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, fmt)
    p.setPen(fg)
    p.drawText(L, B + 4, R - L, 16, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop,
               axes.get("xlabel", ""))
    p.save(); p.translate(rect.left() + 12, (T + B) / 2); p.rotate(-90)
    p.drawText(-((B - T) // 2), -2, B - T, 14, QtCore.Qt.AlignCenter,
               axes.get("ylabel", ""))
    p.restore()

    legend_rects: List[Tuple[QtCore.QRect, str]] = []
    ly = T + 4
    for n in names:
        col = QtGui.QColor(colors.get(n, "#1565c0"))
        is_hidden = n in hidden
        if temp_mode and not is_hidden:
            for thr, style in zip(seuils.get(n, (None, None)),
                                  (QtCore.Qt.DashLine, QtCore.Qt.DotLine)):
                if thr is not None and vmin <= thr <= vmax:
                    p.setPen(QtGui.QPen(col, 1, style)); sy = int(Y(thr)); p.drawLine(L, sy, R, sy)
        last = None
        if not is_hidden:
            p.setPen(QtGui.QPen(col, 2))
            path = QtGui.QPainterPath(); down = False
            seen = []
            for t, v in series[n]:
                if t < tmin or v != v:
                    down = False; continue
                seen.append(v)
                x, y = X(t), Y(v)
                if down:
                    path.lineTo(x, y)
                else:
                    path.moveTo(x, y); down = True
            p.drawPath(path)
            last = seen[-1] if seen else None
        if last is not None:
            txt = f"{n}  {last:.1f}{unit}" if temp_mode else f"{n}  {last:.3f} {unit}"
        else:
            txt = n
        swatch = QtGui.QColor(col)
        if is_hidden:
            swatch.setAlpha(60)
        p.fillRect(QtCore.QRectF(L + 8, ly + 3, 14, 4), swatch)
        legend_fg = QtGui.QColor(fg)
        if is_hidden:
            legend_fg.setAlpha(110)
        p.setPen(legend_fg)
        p.drawText(L + 26, ly - 2, 260, 14, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, txt)
        legend_rects.append((QtCore.QRect(L + 6, ly - 2, 280, 16), n))
        ly += 16

    return PlotGeom(L, R, T, B, tmin, tmax, legend_rects)


class TempPlotQt(QtWidgets.QWidget):
    """Strip-chart temps réel (multi-courbes) au QPainter, thème-aware.

    Trois grandeurs commutables (combo « Grandeur ») : **Températures** (°C, avec
    seuils warning/critical), **Courants** (A) et **Tensions** (V) par voie.
    Fenêtre glissante, une couleur par courbe, marqueurs de séquence, curseur de
    lecture au survol, légende cliquable (masquer/afficher une courbe)."""

    # mode -> (axis title, unit suffix)
    @staticmethod
    def _modes():
        return {
            "temp": (QtCore.QCoreApplication.translate("plot", "Temperature (°C)"), "°C"),
            "current": (QtCore.QCoreApplication.translate("plot", "Current (A)"), "A"),
            "voltage": (QtCore.QCoreApplication.translate("plot", "Voltage (V)"), "V"),
        }

    def __init__(self, sensors, warnings=None, criticals=None, window_s=120.0,
                 channels=None, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.setMouseTracking(True)          # curseur de lecture au survol
        self.window_s = window_s
        self.warnings = warnings or {}
        self.criticals = criticals or {}
        self.mode = "temp"
        self._channels = list(channels or [])
        self._hidden = set()                 # noms de courbes masqués (session)
        self._cursor_px = None               # abscisse pixel du curseur, ou None
        self._legend_rects = []              # [(QRect, nom)] pour la légende cliquable
        self.set_sensors(sensors)

    # ------------------------------------------------------------- données
    def set_sensors(self, sensors, channels=None) -> None:
        from collections import deque
        self.sensors = list(sensors)
        if channels is not None:
            self._channels = list(channels)
        names = list(dict.fromkeys(list(self.sensors) + list(self._channels)))
        self.color = {n: _PLOT_COLORS[i % len(_PLOT_COLORS)] for i, n in enumerate(names)}
        # Un buffer par grandeur et par nom de courbe.
        self._series = {
            "temp": {s: deque() for s in self.sensors},
            "current": {c: deque() for c in self._channels},
            "voltage": {c: deque() for c in self._channels},
        }
        self._marks: List[Tuple[float, str]] = []
        self._t0 = None
        self.update()

    def set_mode(self, mode: str) -> None:
        if mode in self._modes():
            self.mode = mode
            self.update()

    def _names(self):
        return self.sensors if self.mode == "temp" else self._channels

    def mark(self, text: str) -> None:
        """Pose un marqueur vertical horodaté (ex. début/fin de séquence)."""
        if self._t0 is not None:
            import time as _t
            self._marks.append((_t.monotonic() - self._t0, text))

    def push(self, temps, status, channels=None) -> None:
        """Ajoute un point à chaque courbe. ``temps``/``status`` alimentent les
        températures ; ``channels`` (dict label -> (V, I)) alimente tension/courant."""
        import time as _t
        now = _t.monotonic()
        if self._t0 is None:
            self._t0 = now
        t = now - self._t0
        for s in self.sensors:
            v = temps.get(s, float("nan"))
            if status.get(s, OK) in (NA, FAULT):
                v = float("nan")  # ne trace pas une valeur non fiable
            self._series["temp"][s].append((t, v))
        channels = channels or {}
        for c in self._channels:
            vi = channels.get(c)
            volt = vi[0] if vi else float("nan")
            cur = vi[1] if vi else float("nan")
            self._series["voltage"][c].append((t, volt))
            self._series["current"][c].append((t, cur))
        self._trim(t)
        self.update()

    def _trim(self, t_now: float) -> None:
        """Borne les buffers à la fenêtre + marge (évite la fuite mémoire sur les
        essais longs)."""
        horizon = t_now - (self.window_s + 30.0)
        for grp in self._series.values():
            for dq in grp.values():
                while dq and dq[0][0] < horizon:
                    dq.popleft()

    def export_csv(self, path: str) -> None:
        import csv as _csv
        temp = self._series["temp"]
        cur = self._series["current"]
        volt = self._series["voltage"]
        rows = max([len(temp[s]) for s in self.sensors]
                   + [len(cur[c]) for c in self._channels] + [0])
        header = ["t_s"] + list(self.sensors)
        for c in self._channels:
            header += [f"{c}_V", f"{c}_I"]
        cols = {("temp", s): list(temp[s]) for s in self.sensors}
        cols.update({("V", c): list(volt[c]) for c in self._channels})
        cols.update({("I", c): list(cur[c]) for c in self._channels})
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(header)
            for i in range(rows):
                t = ""
                for key in cols:
                    if i < len(cols[key]):
                        t = cols[key][i][0]
                        break
                line = [f"{t:.3f}" if t != "" else ""]
                for s in self.sensors:
                    col = cols[("temp", s)]
                    line.append(f"{col[i][1]:.3f}" if i < len(col) else "")
                for c in self._channels:
                    cv, ci = cols[("V", c)], cols[("I", c)]
                    line.append(f"{cv[i][1]:.4f}" if i < len(cv) else "")
                    line.append(f"{ci[i][1]:.4f}" if i < len(ci) else "")
                w.writerow(line)

    # ----------------------------------------------------- souris (curseur/légende)
    def mouseMoveEvent(self, event) -> None:
        self._cursor_px = event.position().x()
        self.update()

    def leaveEvent(self, event) -> None:
        self._cursor_px = None
        self.update()

    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()
        for rect, name in self._legend_rects:
            if rect.contains(pos):
                if name in self._hidden:
                    self._hidden.discard(name)
                else:
                    self._hidden.add(name)
                self.update()
                return

    @staticmethod
    def _nearest(points, t):
        """Valeur (finie) du point le plus proche du temps ``t``, sinon None."""
        best = None
        bestd = None
        for pt, val in points:
            if val != val:   # NaN
                continue
            d = abs(pt - t)
            if bestd is None or d < bestd:
                bestd, best = d, val
        return best

    def _seuils(self, names) -> Dict[str, Tuple]:
        """Seuils (warning, critical) par capteur, en mode température."""
        if self.mode != "temp":
            return {}
        return {n: (self.warnings.get(n), self.criticals.get(n)) for n in names}

    # ------------------------------------------------------------- rendu
    def paintEvent(self, _evt) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        series = self._series[self.mode]
        names = [n for n in self._names() if n in series]
        ylabel, unit = self._modes()[self.mode]
        temp_mode = self.mode == "temp"
        axes = {"xlabel": QtCore.QCoreApplication.translate("plot", "time (s) — window {} s").format(int(self.window_s)),
                "ylabel": ylabel, "unit": unit, "temp_mode": temp_mode,
                "window_s": self.window_s, "colors": self.color, "hidden": self._hidden}
        geom = dessiner_series(p, self.rect(), {n: series[n] for n in names},
                               axes, self._seuils(names), dark=theme.is_dark())
        self._legend_rects = geom.legend_rects
        if geom.empty:
            return

        fg = QtGui.QColor("#E6E6E6" if theme.is_dark() else "#222222")
        # Marqueurs verticaux (début/fin de séquence…), sur TOUTES les grandeurs.
        markcol = QtGui.QColor(fg); markcol.setAlpha(120)
        for mt, label in self._marks:
            if mt < geom.tmin:
                continue
            mx = int(geom.X(mt))
            p.setPen(QtGui.QPen(markcol, 1, QtCore.Qt.DashLine)); p.drawLine(mx, geom.T, mx, geom.B)
            p.setPen(markcol)
            p.drawText(mx + 2, geom.T + 2, 80, 14, QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, label)

        # Curseur de lecture : ligne verticale + cadre des valeurs au temps pointé.
        if self._cursor_px is not None and geom.L <= self._cursor_px <= geom.R:
            cx = int(self._cursor_px)
            ct = geom.tmin + (cx - geom.L) / max(1e-6, (geom.R - geom.L)) * (geom.tmax - geom.tmin)
            cur = QtGui.QColor(fg); cur.setAlpha(160)
            p.setPen(QtGui.QPen(cur, 1, QtCore.Qt.DashLine)); p.drawLine(cx, geom.T, cx, geom.B)
            lines = [f"t = {ct:.1f} s"]
            for n in names:
                if n in self._hidden:
                    continue
                val = self._nearest(series[n], ct)
                if val is not None:
                    lines.append(f"{n}: {val:.3f} {unit}")
            fm = p.fontMetrics()
            w = max(fm.horizontalAdvance(s) for s in lines) + 12
            h = len(lines) * (fm.height() + 1) + 6
            bx = min(cx + 8, geom.R - w)
            by = geom.T + 4
            bg = self.palette().color(QtGui.QPalette.Base); bg.setAlpha(230)
            p.fillRect(QtCore.QRectF(bx, by, w, h), bg)
            p.setPen(QtGui.QPen(cur, 1)); p.drawRect(QtCore.QRectF(bx, by, w, h))
            p.setPen(fg)
            yy = by + 3
            for s in lines:
                p.drawText(int(bx + 6), int(yy), w - 10, fm.height(),
                           QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, s)
                yy += fm.height() + 1
