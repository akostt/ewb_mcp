"""EWB 5.12 component catalog, element/wire accessors and editing helpers.

Part numbers and names come from the runtime part table built by
COMPDAT.DLL (sub_410293).  Pin offsets were derived from the wire geometry
of application-produced files used during reverse engineering (a single
consistent coordinate frame, normalised so that offsets are small, readable
numbers).

New wires are written without a ``segs`` field: the application itself does
this for wires whose route has not been stored yet, so the schematic stays in
a format EWB accepts.
"""

import re

from ewb_doc import Block, Document, format_value

# ---------------------------------------------------------------------------
# Part catalog
# ---------------------------------------------------------------------------
# name, reference prefix, Value (count, default values) or None,
# ModelUnits (count, default values), default ModelName (None = no field),
# description.  "extra" is handled in make_component_block.
PARTS = {
    0: ("AC_VOLTAGE_SOURCE", "V", (5, [12, 60, 0, 0, 0]), (5, [2, 0, 0, 0, 0]), "", "AC voltage source"),
    1: ("RESISTOR", "R", (5, [1, 0, 0, 0, 0]), (5, [1, 0, 0, 0, 0]), "", "Resistor"),
    2: ("BATTERY", "V", (3, [12, 0, 0]), (3, [2, 0, 0]), "", "Battery / DC voltage source"),
    3: ("CAPACITOR", "C", (3, [1, 0, 0]), (3, [2, 0, 0]), "", "Capacitor"),
    4: ("DIODE", "D", None, (1, [0]), "ideal", "Diode"),
    5: ("NPN_TRANSISTOR", "Q", None, (1, [0]), "ideal", "NPN transistor"),
    6: ("INDUCTOR", "L", (3, [1, 0, 0]), (1, [0]), "", "Inductor"),
    7: ("AC_CURRENT_SOURCE", "I", (5, [1, 1, 0, 0, 0]), (5, [0, 1, 0, 0, 0]), "", "AC current source"),
    8: ("GROUND", "0", (1, [0]), (1, [0]), None, "Ground"),
    9: ("CONNECTOR", "CONN", (1, [0]), (1, [0]), None, "Connector"),
    10: ("DC_CURRENT_SOURCE", "I", (3, [1, 0, 0]), (3, [2, 0, 0]), "", "DC current source"),
    11: ("PNP_TRANSISTOR", "Q", None, (1, [0]), "ideal", "PNP transistor"),
    12: ("AMMETER", "M", (2, [1, 0]), (2, [3, 0]), "", "Ammeter"),
    13: ("VOLTMETER", "M", (2, [1, 0]), (2, [2, 0]), "", "Voltmeter"),
    14: ("TRANSFORMER", "T", None, (1, [0]), "ideal", "Transformer"),
    15: ("OPAMP", "AR", None, (1, [0]), "ideal", "Operational amplifier"),
    16: ("ZENER_DIODE", "D", None, (1, [0]), "ideal", "Zener diode"),
    17: ("LED", "D", None, (1, [0]), "ideal", "Light-emitting diode"),
    18: ("BULB", "R", (2, [10, 25]), (1, [0]), "", "Bulb"),
    19: ("FUSE", "R", (1, [1]), (1, [0]), "", "Fuse"),
    20: ("RELAY", "R", (4, [0.001, 0.01, 0.005, 1e-06]), (1, [0]), "", "Relay"),
    21: ("TIME_DELAY_SWITCH", "S", (4, [0, 1, 0.001, 0]), (1, [0]), "", "Time-delay switch"),
    22: ("N_CHANNEL_JFET", "Q", None, (1, [0]), "ideal", "N-channel JFET"),
    23: ("P_CHANNEL_JFET", "Q", None, (1, [0]), "ideal", "P-channel JFET"),
    24: ("3_TERMINAL_DEPLETION_N_MOSFET", "Q", None, (1, [0]), "ideal", "3-terminal depletion N-MOSFET"),
    25: ("3_TERMINAL_DEPLETION_P_MOSFET", "Q", None, (1, [0]), "ideal", "3-terminal depletion P-MOSFET"),
    26: ("4_TERMINAL_DEPLETION_N_MOSFET", "Q", None, (1, [0]), "ideal", "4-terminal depletion N-MOSFET"),
    27: ("4_TERMINAL_DEPLETION_P_MOSFET", "Q", None, (1, [0]), "ideal", "4-terminal depletion P-MOSFET"),
    28: ("3_TERMINAL_ENHANCEMENT_N_MOSFET", "Q", None, (1, [0]), "ideal", "3-terminal enhancement N-MOSFET"),
    29: ("3_TERMINAL_ENHANCEMENT_P_MOSFET", "Q", None, (1, [0]), "ideal", "3-terminal enhancement P-MOSFET"),
    30: ("4_TERMINAL_ENHANCEMENT_N_MOSFET", "Q", None, (1, [0]), "ideal", "4-terminal enhancement N-MOSFET"),
    31: ("4_TERMINAL_ENHANCEMENT_P_MOSFET", "Q", None, (1, [0]), "ideal", "4-terminal enhancement P-MOSFET"),
    32: ("VOLTAGE_CONTROLLED_VOLTAGE_SOURCE", "V", (1, [1]), (1, [0]), "", "Voltage-controlled voltage source"),
    33: ("CURRENT_CONTROLLED_CURRENT_SOURCE", "I", (1, [1]), (1, [0]), "", "Current-controlled current source"),
    34: ("VOLTAGE_CONTROLLED_CURRENT_SOURCE", "I", (1, [1]), (1, [0]), "", "Voltage-controlled current source"),
    35: ("CURRENT_CONTROLLED_VOLTAGE_SOURCE", "V", (1, [1]), (1, [0]), "", "Current-controlled voltage source"),
    36: ("VOLTAGE_CONTROLLED_SWITCH", "S", (5, [1, 0, 1, 1e12, 1]), (1, [0]), "", "Voltage-controlled switch"),
    37: ("CURRENT_CONTROLLED_SWITCH", "S", (5, [1, 0, 1, 1e12, 1]), (1, [0]), "", "Current-controlled switch"),
    38: ("SWITCH", "S", (1, [32]), (1, [0]), "", "Switch"),
    39: ("NODE", "", (1, [0]), (1, [0]), None, "Node / junction marker"),
}

# Pin offsets per (PartNum, rotation code).  These are relative to Position,
# in one consistent frame (same frame for every part).  Only combinations
# observed in application-produced files are present.
PINS = {
    0: {
        0: {0: (0, 40), 1: (0, -20)},
        1: {0: (-20, 0), 1: (40, 0)},
        2: {0: (0, 40), 1: (0, -20)},
    },
    1: {
        0: {0: (-20, -10), 1: (40, -10)},
        1: {0: (-10, -20), 1: (-10, 40)},
        4: {0: (-20, -10), 1: (40, -10)},
        5: {0: (-10, 40), 1: (-10, -20)},
        7: {0: (-10, 40), 1: (-10, -20)},
    },
    2: {
        0: {0: (0, 30), 1: (0, -20)},
        6: {0: (0, -20), 1: (0, 30)},
    },
    3: {
        0: {0: (-20, 0), 1: (10, 0)},
        1: {0: (0, -20), 1: (0, 10)},
        2: {0: (10, 0), 1: (-20, 0)},
        7: {0: (0, 10), 1: (0, -20)},
    },
    4: {
        0: {0: (-20, 0), 1: (20, 0)},
        1: {0: (0, -20), 1: (0, 20)},
        2: {0: (20, 0), 1: (-20, 0)},
        7: {0: (0, 20), 1: (0, -20)},
    },
    5: {
        0: {0: (-20, 10), 1: (10, 40), 2: (10, -20)},
        2: {0: (10, 10), 1: (-20, 40), 2: (-20, -20)},
    },
    6: {0: {0: (-20, -20), 1: (40, -20)}},
    8: {0: {0: (0, 20)}},
    9: {0: {0: (-20, -10), 1: (-15, -5), 2: (-10, -10), 3: (-15, -15)}},
    11: {
        0: {0: (-20, 10), 1: (10, -20), 2: (10, 40)},
        2: {0: (10, 10), 1: (-20, -20), 2: (-20, 40)},
    },
    12: {
        0: {0: (120, 0), 1: (-20, 0)},
        7: {0: (40, -20), 1: (40, 40)},
    },
    13: {
        0: {0: (40, -20), 1: (40, 40)},
        1: {0: (120, 0), 1: (-20, 0)},
    },
    15: {
        0: {0: (-20, 0), 1: (-20, 20), 2: (50, 10)},
        4: {0: (-20, 20), 1: (-20, 0), 2: (50, 10)},
    },
    17: {
        2: {0: (30, 0), 1: (-10, 0)},
        7: {0: (0, 30), 1: (0, -10)},
    },
    22: {3: {0: (-10, -20), 1: (40, 20), 2: (-20, 20)}},
    38: {
        0: {0: (-20, 0), 1: (30, -10)},
        1: {0: (0, -20), 1: (10, 30)},
    },
    39: {0: {0: (0, 0)}},
}


# Orientation used when a new part is placed without an explicit rotation.
# Chosen among orientations observed in application-produced circuits.
DEFAULT_ROT = {
    0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
    10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 2, 18: 0,
    19: 0, 20: 0, 21: 0, 22: 3, 23: 0, 24: 0, 25: 0, 26: 0, 27: 0,
    28: 3, 29: 0, 30: 0, 31: 0, 32: 0, 33: 0, 34: 0, 35: 0, 36: 0,
    37: 0, 38: 0, 39: 0,
}


def default_rot(partnum):
    return DEFAULT_ROT.get(partnum, 0)


def terminal_count(partnum):
    """Number of pins, when the pin geometry for the part is known."""
    rots = PINS.get(partnum)
    if not rots:
        return None
    pins = {p for r in rots.values() for p in r}
    return max(pins) + 1


def part_name(partnum):
    p = PARTS.get(partnum)
    return p[0] if p else "UNKNOWN"


def part_ref(partnum):
    p = PARTS.get(partnum)
    return p[1] if p else "X"


def part_pins(partnum, rot):
    return PINS.get(partnum, {}).get(rot)


def supported_parts():
    out = []
    for pn in sorted(PARTS):
        name, ref, value, mu, model, desc = PARTS[pn]
        out.append({
            "partnum": pn,
            "name": name,
            "ref_prefix": ref,
            "description": desc,
            "value_count": value[0] if value else 0,
            "value_default": list(value[1]) if value else None,
            "model_units_count": mu[0],
            "model_units_default": list(mu[1]),
            "model_default": model,
            "rotations": {str(r): {str(p): list(v) for p, v in pins.items()}
                          for r, pins in PINS.get(pn, {}).items()},
        })
    return out


# ---------------------------------------------------------------------------
# Elements and wires
# ---------------------------------------------------------------------------
class Element:
    def __init__(self, doc, block, index=None):
        self.doc = doc
        self.block = block
        self._index = index

    @property
    def index(self):
        eb = self.doc.elements_block
        n = 0
        for c in eb.blocks():
            if c.name in ("Comp", "Instrument", "ExtComp"):
                if c is self.block:
                    return n
                n += 1
        raise ValueError("element block is no longer in the document")

    @property
    def kind(self):
        return self.block.name

    @property
    def name(self):
        pn = self.partnum
        if pn is not None:
            return part_name(pn)
        v = self.block.field("Name")
        return v if isinstance(v, str) else "UNKNOWN"

    @property
    def partnum(self):
        v = self.block.field("PartNum")
        if isinstance(v, list):
            return v[0] if v else None
        return v

    @property
    def position(self):
        v = self.block.field("Position") or self.block.field("Pos")
        if isinstance(v, list) and len(v) >= 3:
            return v[0], v[1], v[2]
        return None

    @property
    def rot(self):
        p = self.position
        return p[0] if p else 0

    @property
    def x(self):
        p = self.position
        return p[1] if p else 0

    @property
    def y(self):
        p = self.position
        return p[2] if p else 0

    @property
    def common(self):
        return self.block.child("Common")

    @property
    def refid(self):
        c = self.common
        if c is None:
            return None
        v = c.field("RefID")
        if isinstance(v, list):
            return v[0] if v else None
        return v

    @property
    def value(self):
        v = self.block.field("Value")
        return v if isinstance(v, list) else None

    @property
    def model_units(self):
        v = self.block.field("ModelUnits")
        return v if isinstance(v, list) else None

    @property
    def model(self):
        v = self.block.field("ModelName")
        return v if isinstance(v, str) else None

    @property
    def label(self):
        v = self.block.field("Label")
        return v if isinstance(v, str) else None

    @property
    def pins(self):
        return part_pins(self.partnum, self.rot)

    def pin_position(self, pin):
        pins = self.pins
        if not pins:
            return None
        off = pins.get(int(pin))
        if off is None:
            return None
        return self.x + off[0], self.y + off[1]

    def set_position(self, x=None, y=None, rot=None):
        line = self.block.field_line("Position") or self.block.field_line("Pos")
        if line is None:
            raise ValueError("element has no Position")
        name = "Position" if self.block.field_line("Position") else "Pos"
        cur = self.position
        rot = cur[0] if rot is None else int(rot)
        x = cur[1] if x is None else int(x)
        y = cur[2] if y is None else int(y)
        self.block.set_field(name, [rot, x, y])
        for w in self.doc.wires_touching(self.index):
            w.remove_segs()

    def set_refid(self, refid):
        c = self.common
        if c is None:
            raise ValueError("element has no Common block")
        if c.field_line("RefID") is None:
            raise ValueError("element has no RefID")
        c.set_field("RefID", str(refid))

    def set_value(self, values):
        if self.block.field_line("Value") is None:
            raise ValueError("part %s has no Value field" % self.partnum)
        if not isinstance(values, (list, tuple)):
            values = [values]
        cur = self.value or []
        if not isinstance(values, (list, tuple)):
            values = [values]
        values = list(values)
        if len(values) < len(cur):
            values += cur[len(values):]
        values = values[:len(cur)]
        self.block.set_field("Value", values)

    def set_model_units(self, values):
        if self.block.field_line("ModelUnits") is None:
            raise ValueError("part %s has no ModelUnits field" % self.partnum)
        if not isinstance(values, (list, tuple)):
            values = [values]
        if not values:
            raise ValueError("ModelUnits must not be empty")
        self.block.set_field("ModelUnits", list(values), count=len(values))

    def set_model(self, model):
        if self.block.field_line("ModelName") is None:
            raise ValueError("part %s has no ModelName field" % self.partnum)
        self.block.set_field("ModelName", str(model))

    def to_dict(self):
        pn = self.partnum
        pins = {}
        if self.pins:
            for pin in sorted(self.pins):
                pos = self.pin_position(pin)
                pins[str(pin)] = list(pos) if pos else None
        return {
            "index": self.index,
            "kind": self.kind,
            "partnum": pn,
            "name": self.name,
            "refid": self.refid,
            "position": {"x": self.x, "y": self.y, "rotation": self.rot},
            "value": self.value,
            "model_units": self.model_units,
            "model": self.model,
            "label": self.label,
            "pins": pins,
            "pin_geometry_known": bool(self.pins),
        }


class Wire:
    def __init__(self, doc, block, index=None):
        self.doc = doc
        self.block = block
        self._index = index

    @property
    def index(self):
        wb = self.doc.wires_block
        n = 0
        for c in wb.blocks():
            if c.name == "wire":
                if c is self.block:
                    return n
                n += 1
        raise ValueError("wire block is no longer in the document")

    @property
    def pos(self):
        v = self.block.field("pos")
        return v if isinstance(v, list) and len(v) == 4 else None

    @property
    def segs(self):
        if self.block.field_line("segs") is None:
            return None
        v = self.block.field("segs")
        if not isinstance(v, list):
            return None
        return [(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]

    @property
    def colour(self):
        v = self.block.field("colour")
        return v[0] if isinstance(v, list) and v else 0

    @property
    def wire_id(self):
        v = self.block.field("wire_id")
        return v[0] if isinstance(v, list) and v else 0

    @property
    def node_p(self):
        v = self.block.field("node_p")
        if isinstance(v, list):
            return v[0] if v else ""
        return v if isinstance(v, str) else ""

    @property
    def endpoints(self):
        pos = self.pos
        if not pos:
            return (None, None, None, None)
        a, pa, b, pb = pos
        els = self.doc.elements()
        ea = els[a] if 0 <= a < len(els) else None
        eb = els[b] if 0 <= b < len(els) else None
        return ea, pa, eb, pb

    def set_pos(self, a, pa, b, pb):
        self.block.set_field("pos", [int(a), int(pa), int(b), int(pb)])

    def remove_segs(self):
        line = self.block.field_line("segs")
        if line is not None:
            self.block.remove_child(line)

    def set_route(self, segs):
        """Replace the stored route (``None`` removes it)."""
        if not segs:
            self.remove_segs()
            return
        vals = [int(v) for seg in segs for v in seg]
        line = self.block.field_line("segs")
        if line is not None:
            self.block.set_field("segs", vals, typ="i", count=len(vals))
            return
        pos_line = self.block.field_line("pos")
        if pos_line is None:
            raise ValueError("wire has no pos field")
        idx = self.block.children.index(pos_line) + 1
        self.block.insert_child(idx, _field(self.block.indent + 2, "segs", "i",
                                            vals, len(vals)))

    def set_node_p(self, value):
        self.block.set_field("node_p", str(value))

    def path_points(self):
        a, pa, b, pb = self.endpoints
        pa_pos = a.pin_position(pa) if a else None
        pb_pos = b.pin_position(pb) if b else None
        segs = self.segs
        if segs is None:
            if pa_pos and pb_pos:
                return [pa_pos, pb_pos]
            if a and b:
                return [(a.x, a.y), (b.x, b.y)]
            return []
        # Prefer anchoring the stored route at a known pin; if neither pin is
        # known, use the element position (best effort).
        if pa_pos:
            pts = [pa_pos]
            x, y = pa_pos
            for d, n in segs:
                x, y = _step(d, n, x, y)
                pts.append((x, y))
            return pts
        if pb_pos:
            pts = [pb_pos]
            x, y = pb_pos
            for d, n in reversed(segs):
                x, y = _step(_opposite(d), n, x, y)
                pts.append((x, y))
            return list(reversed(pts))
        if not (a and b):
            return []
        pts = [(a.x, a.y)]
        x, y = a.x, a.y
        for d, n in segs:
            x, y = _step(d, n, x, y)
            pts.append((x, y))
        return pts

    def to_dict(self):
        a, pa, b, pb = self.endpoints
        pos = self.pos
        return {
            "index": self.index,
            "from": {"index": pos[0] if pos else None, "refid": a.refid if a else None, "pin": pa},
            "to": {"index": pos[2] if pos else None, "refid": b.refid if b else None, "pin": pb},
            "node": self.node_p,
            "colour": self.colour,
            "has_route": self.segs is not None,
            "segs": self.segs,
        }


def _step(d, n, x, y):
    if d == 1:
        return x + n, y
    if d == 2:
        return x, y + n
    if d == 4:
        return x - n, y
    if d == 8:
        return x, y - n
    if d == 3:
        return x + n, y + n
    if d == 6:
        return x - n, y + n
    if d == 9:
        return x + n, y - n
    if d == 12:
        return x - n, y - n
    return x, y


def _opposite(d):
    return {1: 4, 4: 1, 2: 8, 8: 2, 3: 12, 12: 3, 6: 9, 9: 6}.get(d, 0)


# ---------------------------------------------------------------------------
# Editing operations
# ---------------------------------------------------------------------------
def _element_indent(doc):
    eb = doc.elements_block
    for c in eb.blocks():
        if c.name in ("Comp", "Instrument", "ExtComp"):
            return c.indent
    return eb.indent + 2


def _wire_indent(doc):
    wb = doc.wires_block
    for c in wb.blocks():
        if c.name == "wire":
            return c.indent
    return wb.indent + 2


def _field(indent, name, typ, values, count=None):
    if not isinstance(values, (list, tuple)):
        values = [values]
    if count is not None:
        values = list(values)[:count]
        values += [0] * (count - len(values))
    text = " " * indent + name + " "
    if typ is not None:
        text += typ
        # EWB always writes the element count for Value/ModelUnits, and omits
        # it for scalar fields (RefID A "x", ModelName R "y", node_p A "n").
        if count is not None and (count > 1 or name in ("Value", "ModelUnits")):
            text += ":%d" % count
        text += " "
    text += " ".join(format_value(typ or "A", v) for v in values)
    return text + " "


def _common_block(elem_indent, refid):
    pad = " " * (elem_indent + 2)
    b = Block(pad + "Common ", pad + "{ ", [], pad + "}")
    b.append_child(_field(elem_indent + 4, "RefID", "A", [str(refid)]))
    return b


def make_component_block(doc, partnum, refid, x, y, rot=0, value=None, model=None,
                         model_units=None):
    if partnum not in PARTS:
        raise ValueError("unsupported PartNum %r (supported: 0..39)" % partnum)
    name, ref, vdef, mu, mdef, desc = PARTS[partnum]
    ind = _element_indent(doc)
    pad = " " * ind
    b = Block(pad + "Comp ", pad + "{ ", [], pad + "}")
    b.append_child(_field(ind + 2, "PartNum", "i", [partnum]))
    b.append_child(_field(ind + 2, "Position", "i", [int(rot), int(x), int(y)], 3))
    if vdef is not None:
        defaults = list(vdef[1])
        if value is None:
            vals = defaults
        elif isinstance(value, (list, tuple)):
            vals = list(value)[:vdef[0]]
            vals += defaults[len(vals):]
        else:
            vals = [value] + defaults[1:]
        vals = vals[:vdef[0]]
        b.append_child(_field(ind + 2, "Value", "r", vals, vdef[0]))
    if model_units is None:
        mu_values, mu_count = list(mu[1]), mu[0]
    else:
        mu_values, mu_count = list(model_units), len(model_units)
    b.append_child(_field(ind + 2, "ModelUnits", "i", mu_values, mu_count))
    b.append_child(_common_block(ind, refid))
    if mdef is not None:
        m = mdef if model is None else str(model)
        b.append_child(_field(ind + 2, "ModelName", "R", [m]))
    b.append_child(_field(ind + 2, "Status", "i", [0]))
    if partnum == 7:
        p = " " * (ind + 2)
        src = Block(p + "IndependentSourceParameters ", p + "{ ", [], p + "}")
        for nm, typ, vals in (
            ("ac", "i", [1]), ("acMag", "r", [1]), ("acPhase", "r", [0]),
            ("distoF1", "i", [1]), ("f1Mag", "r", [1]), ("f1Phase", "r", [0]),
            ("distoF2", "i", [1]), ("f2Mag", "r", [1]), ("f2Phase", "r", [0]),
        ):
            src.append_child(_field(ind + 4, nm, typ, vals))
        b.append_child(src)
    if partnum == 39:
        b.append_child(_field(ind + 2, "m_tptrElem", "A", ["Scope^1"]))
        b.append_child(_field(ind + 2, "m_flags", "i", [8]))
        b.append_child(_field(ind + 2, "m_i_cond", "r", [0]))
        b.append_child(_field(ind + 2, "m_i_nri", "r", [0]))
    return b


def _existing_refids(doc):
    return [e.refid for e in doc.elements() if e.refid]

def next_refid(doc, partnum):
    ref = part_ref(partnum)
    if partnum == 8:
        return "0"
    if partnum == 39:
        nums = [int(r) for r in _existing_refids(doc) if r.isdigit()]
        return str(max(nums) + 1 if nums else 1)
    used = []
    for r in _existing_refids(doc):
        m = re.fullmatch(re.escape(ref) + r"(\d+)", r)
        if m:
            used.append(int(m.group(1)))
    return "%s%d" % (ref, max(used) + 1 if used else 1)


def add_component(doc, partnum, refid=None, x=0, y=0, rot=None, value=None, model=None,
                  model_units=None):
    partnum = int(partnum)
    if rot is None:
        rot = default_rot(partnum)
    if refid is None:
        refid = next_refid(doc, partnum)
    blk = make_component_block(doc, partnum, refid, x, y, rot, value, model, model_units)
    doc.elements_block.append_child(blk)
    return Element(doc, blk)


def _pins_bbox(e):
    pts = []
    if e.pins:
        for pin in e.pins:
            p = e.pin_position(pin)
            if p:
                pts.append(p)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def element_body_bbox(e):
    """Approximate the drawn body of an element, for wire-route scoring.

    This is intentionally coarse: routing only needs to know which side of a
    component is occupied, not the exact outline of every symbol.
    """
    pb = _pins_bbox(e)
    if pb is None:
        return None
    pn = e.partnum
    xmin, ymin, xmax, ymax = pb
    if pn in (8, 9, 39):
        return None
    if pn in (0, 2, 7, 10, 32, 33, 34, 35, 12, 13, 18):
        pins = [e.pin_position(p) for p in e.pins]
        pa, pb2 = pins[0], pins[-1]
        midx, midy = (pa[0] + pb2[0]) / 2.0, (pa[1] + pb2[1]) / 2.0
        length = ((pb2[0] - pa[0]) ** 2 + (pb2[1] - pa[1]) ** 2) ** 0.5
        if pn in (12, 13):
            r = min(16, length * 0.25)
        elif pn == 18:
            r = min(14, length * 0.25)
        else:
            r = min(18, length * 0.3)
        return midx - r, midy - r, midx + r, midy + r
    if pn == 1:
        return xmin - 8, ymin - 8, xmax + 8, ymax + 8
    if pn == 3:
        return xmin - 13, ymin - 13, xmax + 13, ymax + 13
    if pn in (4, 16, 17):
        return xmin - 14, ymin - 14, xmax + 14, ymax + 14
    if pn == 6:
        return xmin - 8, ymin - 8, xmax + 8, ymax + 8
    if pn == 19:
        return xmin - 11, ymin - 11, xmax + 11, ymax + 11
    if pn in (21, 38):
        return xmin - 12, ymin - 12, xmax + 12, ymax + 12
    return xmin - 20, ymin - 20, xmax + 20, ymax + 20


def _trim_segment(p0, p1, clear):
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 2 * clear:
        return None
    ux, uy = dx / length, dy / length
    return ((p0[0] + ux * clear, p0[1] + uy * clear),
            (p1[0] - ux * clear, p1[1] - uy * clear))


def _segment_hits(p0, p1, bbox):
    if bbox is None:
        return False
    xmin, ymin, xmax, ymax = bbox
    sxmin, sxmax = min(p0[0], p1[0]), max(p0[0], p1[0])
    symin, symax = min(p0[1], p1[1]), max(p0[1], p1[1])
    return not (sxmax <= xmin or sxmin >= xmax or symax <= ymin or symin >= ymax)


def _route_score(points, bboxes):
    score = 0
    for p0, p1 in zip(points, points[1:]):
        trimmed = _trim_segment(p0, p1, 14)
        if trimmed is None:
            continue
        for bbox in bboxes:
            if _segment_hits(trimmed[0], trimmed[1], bbox):
                score += 1
    return score


def route_segments(a_pos, b_pos, a_element=None, b_element=None):
    """Orthogonal L route from a_pos to b_pos as ``(direction, length)`` pairs.

    Direction codes are the ones EWB stores: 1=+x, 2=+y, 4=-x, 8=-y.
    When the endpoint elements are supplied, the horizontal-first and
    vertical-first candidates are scored against their bodies and the cleaner
    one is used.  This keeps a wire from running along a symbol the way a
    plain horizontal-first route does when it enters a rotated part from the
    wrong side.
    """
    if not a_pos or not b_pos:
        return None
    ax, ay = int(a_pos[0]), int(a_pos[1])
    bx, by = int(b_pos[0]), int(b_pos[1])
    dx, dy = bx - ax, by - ay
    hseg = (1 if dx > 0 else 4, abs(dx)) if dx else None
    vseg = (2 if dy > 0 else 8, abs(dy)) if dy else None
    hv = [s for s in (hseg, vseg) if s]
    vh = [s for s in (vseg, hseg) if s]
    if a_element is not None or b_element is not None:
        bboxes = []
        for e in (a_element, b_element):
            if e is not None:
                b = element_body_bbox(e)
                if b is not None:
                    bboxes.append(b)
        if bboxes:
            def points(segs):
                pts = [(ax, ay)]
                x, y = ax, ay
                for d, n in segs:
                    x += (1 if d == 1 else -1 if d == 4 else 0) * n
                    y += (1 if d == 2 else -1 if d == 8 else 0) * n
                    pts.append((x, y))
                return pts
            if _route_score(points(vh), bboxes) < _route_score(points(hv), bboxes):
                return vh or None
    return hv or None


def add_wire(doc, a, pa, b, pb, node_p="0", colour=0, wire_id=0, route="auto"):
    """Connect pin pa of element a to pin pb of element b.

    route="auto" stores an orthogonal route when both pin positions are known;
    route=None (or "none") stores no route, which is also valid EWB output.
    A list of [direction, length] pairs is stored verbatim.
    """
    if not isinstance(a, Element):
        a = doc.find_element(a)
    if not isinstance(b, Element):
        b = doc.find_element(b)
    for e, pin in ((a, pa), (b, pb)):
        count = terminal_count(e.partnum) if e.partnum is not None else None
        if count is not None and not (0 <= int(pin) < count):
            raise ValueError("%s pin %s is out of range (part has %d pins)"
                             % (e.refid, pin, count))
    ind = _wire_indent(doc)
    pad = " " * ind
    bblk = Block(pad + "wire ", pad + "{ ", [], pad + "}")
    bblk.append_child(_field(ind + 2, "pos", "i", [a.index, int(pa), b.index, int(pb)], 4))
    if route == "auto":
        segs = route_segments(a.pin_position(pa), b.pin_position(pb), a, b)
    elif route in (None, "none"):
        segs = None
    else:
        segs = [(int(d), int(n)) for d, n in route]
    if segs:
        bblk.append_child(_field(ind + 2, "segs", "i",
                                 [v for seg in segs for v in seg], 2 * len(segs)))
    bblk.append_child(_field(ind + 2, "colour", "i", [int(colour)]))
    bblk.append_child(_field(ind + 2, "wire_id", "i", [int(wire_id)]))
    bblk.append_child(_field(ind + 2, "node_p", "A", [str(node_p)]))
    bblk.append_child(_field(ind + 2, "x_factor", "r", [1]))
    bblk.append_child(_field(ind + 2, "y_factor", "r", [1]))
    doc.wires_block.append_child(bblk)
    return Wire(doc, bblk)


def reroute_wire(wire):
    """Recompute an orthogonal route from the current pin positions.

    Returns the stored segments, or None when a pin position is unknown (in
    which case the route is cleared and the application can re-route it).
    """
    a, pa, b, pb = wire.endpoints
    segs = None
    if a and b:
        segs = route_segments(a.pin_position(pa), b.pin_position(pb), a, b)
    wire.set_route(segs)
    return segs


def remove_wire(doc, wire):
    if not isinstance(wire, Wire):
        wire = doc.wires()[wire]
    doc.wires_block.remove_child(wire.block)


def remove_element(doc, element, remove_wires=True):
    if not isinstance(element, Element):
        element = doc.find_element(element)
    idx = element.index
    if remove_wires:
        for w in list(doc.wires_touching(idx)):
            doc.wires_block.remove_child(w.block)
    doc.elements_block.remove_child(element.block)
    # renumber wire position indices above the removed element
    for w in doc.wires():
        pos = w.pos
        if not pos:
            continue
        a, pa, b, pb = pos
        if a > idx:
            a -= 1
        if b > idx:
            b -= 1
        if [a, pa, b, pb] != pos:
            w.set_pos(a, pa, b, pb)


# ---------------------------------------------------------------------------
# Document-level helpers (monkey-patched onto Document for convenience)
# ---------------------------------------------------------------------------
def _wires_touching(self, element_index):
    return [w for w in self.wires() if w.pos and element_index in (w.pos[0], w.pos[2])]


def _add_component(self, *args, **kw):
    return add_component(self, *args, **kw)


def _add_wire(self, *args, **kw):
    return add_wire(self, *args, **kw)


def _remove_element(self, *args, **kw):
    return remove_element(self, *args, **kw)


def _remove_wire(self, *args, **kw):
    return remove_wire(self, *args, **kw)


def _nets(self):
    return compute_nets(self)


Document.wires_touching = _wires_touching
Document.add_component = _add_component
Document.add_wire = _add_wire
Document.remove_element = _remove_element
Document.remove_wire = _remove_wire
Document.nets = _nets


# ---------------------------------------------------------------------------
# Nets / connectivity
# ---------------------------------------------------------------------------
def compute_nets(doc):
    par = {}

    def find(x):
        par.setdefault(x, x)
        root = x
        while par[root] != root:
            root = par[root]
        while par[x] != root:
            par[x], x = root, par[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[rb] = ra

    wires = doc.wires()
    for w in wires:
        pos = w.pos
        if not pos:
            continue
        a, pa, b, pb = pos
        if a >= 0 and b >= 0:
            union((a, pa), (b, pb))
    groups = {}
    for key in par:
        groups.setdefault(find(key), []).append(key)
    els = doc.elements()
    out = []
    for i, members in enumerate(sorted(groups.values(), key=lambda g: (g[0][0], g[0][1])), 1):
        labels = sorted({w.node_p for w in wires if w.pos and (
            (w.pos[0], w.pos[1]) in members or
            (w.pos[2], w.pos[3]) in members)})
        pins = []
        for a, pa in sorted(set(members)):
            e = els[a] if 0 <= a < len(els) else None
            pins.append({"refid": e.refid if e else None, "pin": pa})
        out.append({"net": i, "node_labels": labels, "pins": pins})
    return out
