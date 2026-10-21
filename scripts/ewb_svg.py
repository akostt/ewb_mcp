"""SVG rendering for EWB documents (schematic preview, no external deps)."""

import html
import math

import ewb_parts as P

WIRE_COLOR = "#0b7a3b"
BODY_COLOR = "#1f2933"
PIN_COLOR = "#c0392b"
TEXT_COLOR = "#111827"


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return ("%.6g" % v)
    return str(v)


# Value layouts differ per part; only the leading entry is the quantity the
# user edits in EWB.  The remaining entries are secondary fields (unit code,
# rating, ...), so the preview deliberately shows only the first one.
_VALUE_UNITS = {
    0: "V",    # AC voltage source
    1: "Ω",    # resistor
    2: "V",    # battery
    3: "F",    # capacitor
    6: "H",    # inductor
    7: "A",    # AC current source
    10: "A",   # DC current source
    12: "A",   # ammeter
    13: "V",   # voltmeter
    18: "V",   # bulb
    19: "A",   # fuse
    32: "V",   # VCVS
    33: "A",   # CCCS
    34: "A",   # VCCS
    35: "V",   # CCVS
}
_SI_STEPS = ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""),
             (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"))

# EWB keeps the leading Value in the unit selected by ModelUnits[0].  Only
# combinations observed in application-produced files are mapped; unknown
# codes keep the base-SI interpretation above.
_MODEL_UNITS = {
    0: {2: ("mV", 1e-3), 3: ("V", 1.0)},   # AC voltage source
    3: {0: ("µF", 1e-6)},                   # capacitor
    13: {2: ("mV", 1e-3)},                  # voltmeter
}


def _si(v, unit):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v == 0:
        return "0"
    factor, prefix = _SI_STEPS[-1]
    for f, p in _SI_STEPS:
        if abs(v) >= f:
            factor, prefix = f, p
            break
    scaled = v / factor
    if scaled == int(scaled):
        text = str(int(scaled))
    else:
        text = "%.3g" % scaled
    return text + prefix + unit


def _display_value(e):
    unit = _VALUE_UNITS.get(e.partnum)
    if unit is None or not e.value:
        return ""
    units = e.model_units or []
    spec = _MODEL_UNITS.get(e.partnum, {}).get(units[0] if units else None)
    if spec is not None:
        label, scale = spec
        if label == "µF":
            # Keep the engineering notation used on the schematic: 0.5 µF
            # reads better than the auto-scaled 500 nF.
            return _fmt(float(e.value[0])) + label
        return _si(float(e.value[0]) * scale, unit)
    return _si(e.value[0], unit)


def _pts_for_element(e):
    ps = []
    if e.pins:
        for pin in sorted(e.pins):
            p = e.pin_position(pin)
            if p:
                ps.append(p)
    if not ps:
        ps.append((e.x, e.y))
    return ps


# How far the drawn body extends past the pins, in schematic units.
_SYMBOL_MARGIN = {
    0: 16, 2: 16, 7: 16, 10: 16, 32: 16, 33: 16, 34: 16, 35: 16,
    1: 8, 3: 13, 4: 13, 16: 13, 17: 28, 6: 8,
    8: 18, 9: 5, 12: 16, 13: 16, 18: 16, 19: 12,
    21: 14, 38: 14, 15: 24, 5: 24, 11: 24, 14: 24, 20: 20,
    22: 24, 23: 24, 24: 24, 25: 24, 26: 24, 27: 24,
    28: 24, 29: 24, 30: 24, 31: 24, 36: 20, 37: 20, 39: 4,
}


def _element_bbox(e):
    pts = _pts_for_element(e)
    m = _SYMBOL_MARGIN.get(e.partnum, 20)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m


def render_svg(doc, width=1200, height=800):
    els = doc.elements()
    wires = doc.wires()
    allpts = []
    for e in els:
        minx, miny, maxx, maxy = _element_bbox(e)
        allpts.extend([(minx, miny), (maxx, maxy)])
    wire_paths = []
    for w in wires:
        pts = w.path_points()
        if pts:
            wire_paths.append(pts)
            allpts.extend(pts)
    if not allpts:
        allpts = [(0, 0), (400, 300)]
    xs = [p[0] for p in allpts]
    ys = [p[1] for p in allpts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    spanx = max(maxx - minx, 80)
    spany = max(maxy - miny, 80)
    pad = 50
    scale = min((width - 2 * pad) / spanx, (height - 2 * pad) / spany)
    scale = max(min(scale, 4.0), 0.02)
    vx = minx - pad / scale
    vy = miny - pad / scale
    vw = width / scale
    vh = height / scale
    fs = 13 / scale
    sw = 1.8 / scale
    pinr = 3.0 / scale

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
               'viewBox="%.2f %.2f %.2f %.2f" preserveAspectRatio="xMidYMid meet">'
               % (width, height, vx, vy, vw, vh))
    out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="#ffffff"/>'
               % (vx, vy, vw, vh))
    out.append('<g stroke-linecap="round" stroke-linejoin="round" fill="none">')

    # wires
    for pts in wire_paths:
        d = " ".join("%.2f,%.2f" % (x, y) for x, y in pts)
        out.append('<polyline points="%s" stroke="%s" stroke-width="%.3f"/>'
                   % (d, WIRE_COLOR, sw))
    # junction dots
    counts = {}
    for w in wires:
        for p in (w.path_points() or [])[:1] + (w.path_points() or [])[-1:]:
            counts[p] = counts.get(p, 0) + 1
    for (x, y), n in counts.items():
        if n >= 2:
            out.append('<circle cx="%.2f" cy="%.2f" r="%.3f" fill="%s" stroke="none"/>'
                       % (x, y, pinr * 1.3, WIRE_COLOR))

    # elements
    for e in els:
        _draw_element(out, e, sw, pinr, fs)

    out.append('</g>')
    out.append('</svg>')
    return "\n".join(out)


def _line(out, a, b, sw, color=BODY_COLOR, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    out.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="%.3f"%s/>'
               % (a[0], a[1], b[0], b[1], color, sw, d))


def _poly(out, pts, sw, color=BODY_COLOR, fill="none"):
    d = " ".join("%.2f,%.2f" % p for p in pts)
    out.append('<polyline points="%s" stroke="%s" stroke-width="%.3f" fill="%s"/>'
               % (d, color, sw, fill))


def _circle(out, c, r, sw, color=BODY_COLOR, fill="none"):
    out.append('<circle cx="%.2f" cy="%.2f" r="%.2f" stroke="%s" stroke-width="%.3f" fill="%s"/>'
               % (c[0], c[1], r, color, sw, fill))


def _text(out, p, s, fs, color=TEXT_COLOR, anchor="middle", weight="normal"):
    # Draw a white outline first, then the glyphs on top.  Two passes work in
    # every SVG renderer, unlike paint-order, and keep labels readable where a
    # wire or a pin dot passes underneath them in dense schematics.
    escaped = html.escape(s)
    common = ('x="%.2f" y="%.2f" font-family="Menlo, Consolas, monospace" '
              'font-size="%.2f" text-anchor="%s" font-weight="%s"'
              % (p[0], p[1], fs, anchor, weight))
    out.append('<text %s fill="none" stroke="#ffffff" stroke-width="%.2f" '
               'stroke-linejoin="round">%s</text>'
               % (common, fs * 0.32, escaped))
    out.append('<text %s fill="%s" stroke="none">%s</text>'
               % (common, color, escaped))


def _axis(p0, p1):
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1.0
    u = (dx / L, dy / L)
    n = (-u[1], u[0])
    return u, n, L


def _at(p0, u, n, t, off=0.0):
    return (p0[0] + u[0] * t + n[0] * off, p0[1] + u[1] * t + n[1] * off)


def _draw_element(out, e, sw, pinr, fs):
    pn = e.partnum
    pins = {}
    if e.pins:
        for pin in sorted(e.pins):
            p = e.pin_position(pin)
            if p:
                pins[pin] = p
    pts = list(pins.values())
    if not pts:
        pts = [(e.x, e.y)]
    # Pin dots mark electrical endpoints; each symbol draws its own lead from
    # the pin to the body so the lead never crosses the body interior.
    for p in pts:
        out.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s" stroke="none"/>'
                   % (p[0], p[1], pinr, PIN_COLOR))
    refid = e.refid or ""
    val = e.value

    if pn == 39:  # node
        out.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s" stroke="none"/>'
                   % (e.x, e.y, pinr * 1.6, WIRE_COLOR))
        if refid:
            _text(out, (e.x + 10 * fs / 13, e.y - 8 * fs / 13), refid, fs * 0.8, "#6b7280")
        return

    if pn == 8:  # ground
        p = pins.get(0, (e.x, e.y))
        u, n, L = _axis((e.x, e.y), p)
        _line(out, (e.x, e.y), p, sw * 0.8, "#6b7280")
        base = p
        for i, wdt in enumerate((16, 10, 5)):
            q = (base[0] + u[0] * i * 5, base[1] + u[1] * i * 5)
            _line(out, (q[0] - n[0] * wdt, q[1] - n[1] * wdt),
                  (q[0] + n[0] * wdt, q[1] + n[1] * wdt), sw)
        if refid:
            _text(out, (e.x + 8 * fs / 13, e.y), refid, fs * 0.8, "#6b7280",
                  anchor="start")
        return

    if pn == 9:  # connector: 4-pin junction cluster
        if len(pins) >= 2:
            c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            _circle(out, c, 4, sw * 0.9, WIRE_COLOR, WIRE_COLOR)
        _text(out, (e.x + 8 * fs / 13, e.y - 8 * fs / 13), refid, fs * 0.7, "#6b7280", anchor="start")
        return

    if len(pins) >= 2 and pn in (1, 3, 4, 5, 6, 11, 14, 15, 16, 17, 18, 19, 20, 21, 38,
                                 12, 13, 0, 2, 7, 10, 32, 33, 34, 35, 36, 37):
        pa = pins[0]
        pb = pins[max(pins)]
        u, n, L = _axis(pa, pb)
        mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
        if pn == 1:  # resistor zigzag
            q = []
            steps = 7
            for i in range(steps + 1):
                t = L * i / steps
                off = 0 if i in (0, steps) else (7 if i % 2 else -7)
                q.append(_at(pa, u, n, t, off))
            _poly(out, q, sw)
        elif pn == 3:  # capacitor
            t0, t1 = L * 0.42, L * 0.58
            for t in (t0, t1):
                q = _at(pa, u, n, t)
                _line(out, (q[0] - n[0] * 12, q[1] - n[1] * 12),
                      (q[0] + n[0] * 12, q[1] + n[1] * 12), sw)
            _line(out, pa, _at(pa, u, n, t0), sw * 0.8, "#6b7280")
            _line(out, _at(pa, u, n, t1), pb, sw * 0.8, "#6b7280")
        elif pn in (4, 16, 17):  # diode / zener / LED
            t0, t1 = L * 0.38, L * 0.62
            base = _at(pa, u, n, t1)
            tip = _at(pa, u, n, t0)
            _line(out, pa, tip, sw * 0.8, "#6b7280")
            _line(out, base, pb, sw * 0.8, "#6b7280")
            _poly(out, [(base[0] - n[0] * 11, base[1] - n[1] * 11),
                        (base[0] + n[0] * 11, base[1] + n[1] * 11), tip,
                        (base[0] - n[0] * 11, base[1] - n[1] * 11)], sw, BODY_COLOR)
            bar1 = (base[0] - n[0] * 12, base[1] - n[1] * 12)
            bar2 = (base[0] + n[0] * 12, base[1] + n[1] * 12)
            _line(out, bar1, bar2, sw)
            if pn == 17:
                for k in (0, 1):
                    a = _at(pa, u, n, L * (0.42 + 0.1 * k), 14)
                    b = (a[0] + 10, a[1] - 12)
                    _line(out, a, b, sw * 0.7)
        elif pn in (0, 2, 32, 35, 7, 10, 33, 34):  # sources
            r = min(18, L * 0.3)
            _line(out, pa, _at(pa, u, n, L * 0.5 - r), sw * 0.8, "#6b7280")
            _line(out, _at(pa, u, n, L * 0.5 + r), pb, sw * 0.8, "#6b7280")
            _circle(out, mid, r, sw)
            _text(out, (mid[0], mid[1] + fs * 0.35), "+", fs * 1.2)
            _line(out, _at(pa, u, n, L * 0.5 - 6, 8), _at(pa, u, n, L * 0.5 + 6, 8), sw * 0.8)
        elif pn in (12, 13):  # meters
            r = min(16, L * 0.25)
            _line(out, pa, _at(pa, u, n, L * 0.5 - r), sw * 0.8, "#6b7280")
            _line(out, _at(pa, u, n, L * 0.5 + r), pb, sw * 0.8, "#6b7280")
            _circle(out, mid, r, sw)
            _text(out, (mid[0], mid[1] + fs * 0.35), "A" if pn == 12 else "V", fs)
        elif pn in (21, 38):  # switch
            c1 = _at(pa, u, n, L * 0.38)
            c2 = _at(pa, u, n, L * 0.62)
            _line(out, _at(pa, u, n, 0), c1, sw)
            _line(out, c2, _at(pa, u, n, L), sw)
            _line(out, c1, _at(pa, u, n, L * 0.66, 10), sw * 1.2)
        elif pn == 6:  # inductor
            q = []
            for i in range(25):
                t = L * i / 24
                off = 7 * abs(math.sin(i / 24 * 3 * math.pi))
                q.append(_at(pa, u, n, t, off))
            _poly(out, q, sw)
        elif pn == 18:  # bulb
            r = min(14, L * 0.25)
            _line(out, pa, _at(pa, u, n, L * 0.5 - r), sw * 0.8, "#6b7280")
            _line(out, _at(pa, u, n, L * 0.5 + r), pb, sw * 0.8, "#6b7280")
            _circle(out, mid, r, sw)
            _line(out, (mid[0] - 10, mid[1] - 10), (mid[0] + 10, mid[1] + 10), sw * 0.8)
            _line(out, (mid[0] - 10, mid[1] + 10), (mid[0] + 10, mid[1] - 10), sw * 0.8)
        elif pn == 19:  # fuse
            _line(out, pa, _at(pa, u, n, L * 0.5 - 10), sw * 0.8, "#6b7280")
            _line(out, _at(pa, u, n, L * 0.5 + 10), pb, sw * 0.8, "#6b7280")
            _poly(out, [(mid[0] - n[0] * 7 - u[0] * 10, mid[1] - n[1] * 7 - u[1] * 10),
                        (mid[0] + n[0] * 7 - u[0] * 10, mid[1] + n[1] * 7 - u[1] * 10),
                        (mid[0] + n[0] * 7 + u[0] * 10, mid[1] + n[1] * 7 + u[1] * 10),
                        (mid[0] - n[0] * 7 + u[0] * 10, mid[1] - n[1] * 7 + u[1] * 10),
                        (mid[0] - n[0] * 7 - u[0] * 10, mid[1] - n[1] * 7 - u[1] * 10)], sw)
        elif pn == 15:  # opamp triangle
            p0 = pins.get(0, pa)
            p1 = pins.get(1, pb)
            p2 = pins.get(2)
            if p2:
                # inputs on the left, output right
                top = p0 if p0[1] < p1[1] else p1
                bot = p1 if p0[1] < p1[1] else p0
                _poly(out, [top, bot, p2, top], sw)
                _text(out, (top[0] + 12, top[1] + fs * 0.3), "-", fs)
                _text(out, (bot[0] + 12, bot[1] + fs * 0.3), "+", fs)
            else:
                _poly(out, [(mid[0] - 18, mid[1] - 20), (mid[0] - 18, mid[1] + 20),
                            (mid[0] + 22, mid[1]), (mid[0] - 18, mid[1] - 20)], sw)
        else:  # transistor / generic two-terminal body
            r = min(20, L * 0.3)
            for p in pts:
                dx, dy = p[0] - mid[0], p[1] - mid[1]
                d = math.hypot(dx, dy)
                if d > r:
                    q = (mid[0] + dx / d * r, mid[1] + dy / d * r)
                    _line(out, p, q, sw * 0.8, "#6b7280")
            _circle(out, mid, r, sw)
            _line(out, _at(pa, u, n, L * 0.45, -9), _at(pa, u, n, L * 0.45, 9), sw)
            _line(out, _at(pa, u, n, L * 0.45, 0), _at(pa, u, n, L * 0.7, 10), sw)
            _line(out, _at(pa, u, n, L * 0.45, 0), _at(pa, u, n, L * 0.7, -10), sw)
    else:
        # generic body at position
        c = (e.x, e.y)
        w, h = 44, 30
        out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="4" '
                   'stroke="%s" stroke-width="%.3f" fill="#f8fafc"/>'
                   % (c[0] - w / 2, c[1] - h / 2, w, h, BODY_COLOR, sw))
        _text(out, (c[0], c[1] + fs * 0.35), refid, fs, TEXT_COLOR, weight="bold")
        text = _display_value(e)
        if text:
            _text(out, (c[0], c[1] + h / 2 + fs * 1.1), text, fs * 0.9, "#475569")
        return

    # Labels sit outside the drawn body, not at the placement origin: the
    # origin is a pin reference for several parts (resistor, capacitor, ...).
    minx, miny, maxx, maxy = _element_bbox(e)
    cx = (minx + maxx) / 2
    midy = (miny + maxy) / 2
    pa, pb = pins[min(pins)], pins[max(pins)]
    vertical = abs(pa[0] - pb[0]) < abs(pa[1] - pb[1])
    source = e.partnum in (0, 2, 7, 10, 32, 33, 34, 35)
    if refid:
        if vertical and source:
            # A lead may leave the top pin straight up; a label above the
            # body would sit on it.  Put the reference beside the body.
            _text(out, (minx - 4 * fs / 13, midy + fs * 0.35),
                  refid, fs, TEXT_COLOR, weight="bold", anchor="end")
        elif vertical:
            # Keep the reference clear of a lead leaving the top pin.
            _text(out, (cx + 8 * fs / 13, miny - 6 * fs / 13),
                  refid, fs, TEXT_COLOR, weight="bold", anchor="start")
        else:
            _text(out, (cx, miny - 6 * fs / 13), refid, fs, TEXT_COLOR,
                  weight="bold")
    text = _display_value(e)
    if text:
        if vertical:
            # Wires leave vertical parts through the top and bottom pins, so
            # the free space for the value is beside the body.
            _text(out, (maxx + 6 * fs / 13, midy + fs * 0.35), text,
                  fs * 0.85, "#475569", anchor="start")
        else:
            _text(out, (cx, maxy + 6 * fs / 13 + fs * 0.7), text,
                  fs * 0.85, "#475569")


def write_svg(doc, path, width=1200, height=800):
    svg = render_svg(doc, width, height)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path
