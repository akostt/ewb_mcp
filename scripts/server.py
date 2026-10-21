"""MCP server for Electronics Workbench 5.x schematics (.ewb).

The server speaks JSON-RPC 2.0 over stdio (newline-delimited, with optional
Content-Length framing) and has no external dependencies.  It can read,
render, validate, edit and create schematics while keeping the container and
the Project_5_1 document in the format produced by EWB 5.12.

Run directly from the repository root:

    python3 scripts/server.py

or register it in an MCP client with this command and the project directory as
the working directory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ewb_codec as codec          # noqa: E402
import ewb_doc as docmod           # noqa: E402
import ewb_parts as parts          # noqa: E402  (also registers Document helpers)
import ewb_svg as svgmod           # noqa: E402

SERVER_NAME = "ewb512-schematic"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2024-11-05"

DIRECTION_CODES = {1, 2, 3, 4, 6, 8, 9, 12}
ROUTE_NAMES = {"auto", "none"}


# ---------------------------------------------------------------------------
# Errors, paths and file I/O
# ---------------------------------------------------------------------------
class ToolError(Exception):
    pass


def log(message):
    sys.stderr.write("[ewb-mcp] %s\n" % message)
    sys.stderr.flush()


_ALLOWED_ROOTS = None


def allowed_roots():
    global _ALLOWED_ROOTS
    if _ALLOWED_ROOTS is not None:
        return _ALLOWED_ROOTS
    roots = [Path.cwd(), ROOT, Path("/tmp"), Path("/private/tmp")]
    if os.environ.get("EWB_MCP_ALLOW_HOME", "").strip().lower() in (
            "1", "true", "yes", "on"):
        # Plugin installs often run with their own directory as the working
        # directory.  The flag is set by the shipped plugin configs so that
        # schematics anywhere in the user's home remain reachable.
        roots.append(Path.home())
    env = os.environ.get("EWB_MCP_ALLOWED_DIRS", "")
    for item in env.split(os.pathsep):
        if item.strip():
            roots.append(Path(item.strip()).expanduser())
    out = []
    for root in roots:
        try:
            real = root.resolve()
        except OSError:
            continue
        if real not in out:
            out.append(real)
    _ALLOWED_ROOTS = out
    return out


def resolve_path(raw, suffix=None, must_exist=False):
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("path must be a non-empty string")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    real = p.resolve(strict=False)
    roots = allowed_roots()
    if not any(real == root or root in real.parents for root in roots):
        raise ToolError(
            "path %r is outside the allowed directories: %s"
            % (str(real), ", ".join(str(r) for r in roots))
        )
    if suffix and real.suffix.lower() != suffix:
        raise ToolError("expected a %s file, got %r" % (suffix, real.name))
    if must_exist and not real.is_file():
        raise ToolError("file not found: %s" % real)
    return real


def atomic_write(path, data, backup=True):
    """Write bytes atomically; keep the previous version as '<name>.bak'."""
    path = Path(path)
    parent = path.parent
    if not parent.is_dir():
        parent.mkdir(parents=True, exist_ok=True)
    mode = None
    if path.exists():
        if backup:
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Header and document inspection
# ---------------------------------------------------------------------------
def header_info(header):
    text = header.decode("latin1", "replace")
    info = {
        "version": None,
        "charset": None,
        "description": "",
        "encryption_type": None,
        "vector_graphics": None,
    }
    m = re.search(r"\r\nVersion:\s*([^\r\n]+)", text)
    if m:
        info["version"] = m.group(1).strip()
    m = re.search(r"\r\nCharset:\s*([^\r\n]+)", text)
    if m:
        info["charset"] = m.group(1).strip()
    m = re.search(r"\r\nDescription:\s*\r\n\"(.*?)\"\s*\r\n", text, re.S)
    if m:
        info["description"] = m.group(1)
    m = re.search(r"\r\nEncryptionType:\s*(\d+)", text)
    if m:
        info["encryption_type"] = int(m.group(1))
    m = re.search(r"\r\nUsingVectorGraphics:\s*(\d+)", text)
    if m:
        info["vector_graphics"] = int(m.group(1))
    return info


def load_document(raw_path, for_edit=False):
    p = resolve_path(raw_path, suffix=".ewb", must_exist=True)
    try:
        info = codec.read_ewb(str(p))
    except Exception as exc:
        hint = ""
        try:
            head = p.read_bytes()[:4096]
            m = re.search(br"EncryptionType:\s*(\d+)", head)
            if m and m.group(1) != b"2":
                hint = (" (EncryptionType %s is an older container variant; "
                        "this server supports EncryptionType 2)"
                        % m.group(1).decode("ascii", "replace"))
        except OSError:
            pass
        raise ToolError("cannot decode %s: %s%s" % (p, exc, hint))
    meta = header_info(info["header"])
    if meta["encryption_type"] not in (None, 2):
        raise ToolError(
            "%s uses EncryptionType %s; only EncryptionType 2 is supported"
            % (p, meta["encryption_type"])
        )
    try:
        doc = docmod.Document.parse(info["document"])
    except Exception as exc:
        raise ToolError("cannot parse Project_5_1 document in %s: %s" % (p, exc))
    if for_edit and doc.to_bytes() != info["document"]:
        raise ToolError(
            "refusing to edit %s: the parser does not reproduce this document "
            "byte-for-byte" % p
        )
    return p, info, doc


def inspect_document(doc, info=None):
    """Structural checks that do not modify the document."""
    errors = []
    warnings = []
    els = doc.elements()
    wires = doc.wires()

    if doc.root.name != "Project_5_1":
        errors.append("root block is %r, expected 'Project_5_1'" % doc.root.name)
    if doc.circuit is None:
        errors.append("Circuit block is missing")
    if doc.elements_block is None:
        errors.append("Circuit/Elements block is missing")
    if doc.wires_block is None:
        errors.append("Circuit/Wires block is missing")

    unknown_parts = []
    missing_geometry = []
    refids = {}
    for e in els:
        try:
            idx = e.index
        except Exception:
            idx = None
        pn = e.partnum
        if e.kind in ("Comp", "Instrument") and pn is None:
            errors.append("element %s (%s) has no PartNum" % (idx, e.kind))
        elif e.kind == "ExtComp":
            if not e.name or e.name == "UNKNOWN":
                warnings.append("ExtComp %s has no Name" % idx)
        if pn is not None and pn not in parts.PARTS:
            unknown_parts.append({"index": idx, "partnum": pn, "refid": e.refid})
        if e.position is None:
            errors.append("element %s (%s) has no Position" % (idx, e.refid))
        if pn in parts.PARTS:
            known = parts.PINS.get(pn)
            if known and e.rot not in known:
                missing_geometry.append(
                    {"index": idx, "refid": e.refid, "partnum": pn,
                     "rotation": e.rot, "known_rotations": sorted(known)}
                )
        rid = e.refid
        if rid:
            refids.setdefault(rid, []).append(idx)

    if unknown_parts:
        warnings.append("%d element(s) use PartNum values outside the catalog"
                        % len(unknown_parts))
    if missing_geometry:
        warnings.append("%d element(s) use a rotation whose pin geometry was "
                        "not observed in application samples" % len(missing_geometry))
    duplicates = {r: v for r, v in refids.items() if len(v) > 1 and r != "0"}
    if duplicates:
        warnings.append("duplicate reference designators: %s"
                        % ", ".join("%s at %s" % (r, v) for r, v in sorted(duplicates.items())))
    # EWB names every ground symbol "0"; use the element index when a caller
    # needs to address one of several grounds.  This is normal, not a defect.
    ground_count = len(refids.get("0", []))

    pin_mismatch = []
    unknown_pin_geometry = 0
    duplicate_wires = set()
    seen_wires = set()
    for w in wires:
        idx = w.index
        pos = w.pos
        if pos is None:
            errors.append("wire %s has no valid pos field" % idx)
            continue
        a, pa, b, pb = pos
        for side, eidx, pin in (("from", a, pa), ("to", b, pb)):
            if not (0 <= eidx < len(els)):
                errors.append("wire %s %s endpoint references element %s, but "
                              "there are %d elements" % (idx, side, eidx, len(els)))
                continue
            e = els[eidx]
            count = parts.terminal_count(e.partnum) if e.partnum is not None else None
            if count is not None and not (0 <= pin < count):
                errors.append("wire %s %s pin %s is out of range for %s "
                              "(part has %d pins)" % (idx, side, pin, e.refid, count))
        key = tuple(sorted(((a, pa), (b, pb))))
        if key in seen_wires:
            warnings.append("wire %s duplicates another wire between the same pins" % idx)
        seen_wires.add(key)
        duplicate_wires.add(key)

        raw_segs = w.block.field("segs")
        if w.block.field_line("segs") is not None:
            if not isinstance(raw_segs, list) or len(raw_segs) % 2:
                errors.append("wire %s has a malformed segs field" % idx)
            else:
                for d, n in w.segs or []:
                    if d not in DIRECTION_CODES:
                        errors.append("wire %s has unknown segment direction %s" % (idx, d))
                    if n <= 0:
                        warnings.append("wire %s has a non-positive segment length %s" % (idx, n))
        if w.segs and 0 <= a < len(els) and 0 <= b < len(els):
            ea, eb = els[a], els[b]
            pa_pos = ea.pin_position(pa)
            pb_pos = eb.pin_position(pb)
            if pa_pos is None or pb_pos is None:
                unknown_pin_geometry += 1
            else:
                try:
                    pts = w.path_points()
                    end = tuple(pts[-1]) if pts else None
                except Exception:
                    end = None
                if end != tuple(pb_pos):
                    pin_mismatch.append(
                        {"wire": idx, "computed_end": list(end) if end else None,
                         "pin_position": list(pb_pos)}
                    )
    if unknown_pin_geometry:
        warnings.append("%d routed wire(s) touch pins whose geometry is not in "
                        "the catalog" % unknown_pin_geometry)
    if pin_mismatch:
        warnings.append("%d routed wire(s) do not end at the computed pin "
                        "position (pin geometry or route may be stale)"
                        % len(pin_mismatch))

    checks = {}
    if info is not None:
        doc_bytes = info["document"]
        doc_exact = doc.to_bytes() == doc_bytes
        checks["document_roundtrip_exact"] = doc_exact
        if not doc_exact:
            errors.append("parser round-trip is not byte-exact for this file; "
                          "editing is disabled")
        try:
            checks["container_roundtrip_exact"] = (
                codec.build_ewb(doc_bytes, header=info["header"]) == info["raw"]
            )
        except Exception:
            checks["container_roundtrip_exact"] = False
        # The document body is what matters: a different but valid implode
        # stream still opens in EWB 5.12, so a non-identical container is
        # reported in checks only, not as a warning.
        try:
            checks["checksum_matches"] = (
                codec.document_checksum(doc_bytes) == info["checksum"]
            )
        except Exception:
            checks["checksum_matches"] = None
        if checks.get("checksum_matches") is False:
            warnings.append("stored checksum does not match the document")

    return {
        "errors": errors,
        "warnings": warnings,
        "details": {
            "unknown_parts": unknown_parts[:50],
            "missing_pin_geometry": missing_geometry[:50],
            "pin_mismatches": pin_mismatch[:50],
            "duplicate_refids": duplicates,
            "ground_count": ground_count,
        },
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Argument helpers
# ---------------------------------------------------------------------------
ALIASES = {
    "res": 1, "r": 1, "resistor": 1,
    "cap": 3, "c": 3, "capacitor": 3,
    "battery": 2, "vdc": 2, "dc_voltage_source": 2,
    "vac": 0, "ac_source": 0, "ac_voltage_source": 0,
    "idc": 10, "dc_current_source": 10,
    "iac": 7, "ac_current_source": 7,
    "gnd": 8, "ground": 8, "0": 8,
    "led": 17,
    "diode": 4,
    "zener": 16, "zener_diode": 16,
    "npn": 5, "npn_transistor": 5, "pnp": 11, "pnp_transistor": 11,
    "inductor": 6, "l": 6, "coil": 6,
    "opamp": 15, "op_amp": 15, "op-amp": 15,
    "voltmeter": 13, "vm": 13,
    "ammeter": 12, "am": 12,
    "switch": 38, "sw": 38,
    "connector": 9, "conn": 9,
    "transformer": 14, "xfmr": 14,
    "fuse": 19,
    "bulb": 18, "lamp": 18,
    "relay": 20,
    "njfet": 22, "pjfet": 23,
    "nmos": 28, "pmos": 29,
    "node": 39, "junction": 39,
    "timer": 21, "time_delay_switch": 21,
    "vcvs": 32, "cccs": 33, "vccs": 34, "ccvs": 35,
    "vswitch": 36, "cswitch": 37,
}
for _pn, _spec in parts.PARTS.items():
    ALIASES.setdefault(_spec[0].lower(), _pn)


def resolve_part(value):
    if isinstance(value, bool):
        raise ToolError("part must be a part number or part name")
    if isinstance(value, int):
        pn = value
    elif isinstance(value, float) and value.is_integer():
        pn = int(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            raise ToolError("part must not be empty")
        if s.isdigit():
            pn = int(s)
        else:
            key = s.lower().replace(" ", "_")
            pn = ALIASES.get(key)
            if pn is None:
                raise ToolError(
                    "unknown part %r; use ewb_list_parts to see supported names"
                    % value
                )
    else:
        raise ToolError("part must be a part number or part name")
    if pn not in parts.PARTS:
        raise ToolError("unsupported PartNum %s (supported: 0..39)" % pn)
    return pn


def as_int(value, name, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ToolError("%s must be an integer" % name)
    if isinstance(value, float) and not value.is_integer():
        raise ToolError("%s must be an integer" % name)
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ToolError("%s must be an integer" % name)
    if minimum is not None and result < minimum:
        raise ToolError("%s must be >= %s" % (name, minimum))
    if maximum is not None and result > maximum:
        raise ToolError("%s must be <= %s" % (name, maximum))
    return result


_NUMBER_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Zµμ]*)\s*$"
)
_MULTIPLIERS = {
    "": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
    "m": 1e-3, "k": 1e3, "K": 1e3, "meg": 1e6, "M": 1e6, "g": 1e9, "G": 1e9,
}


def as_number(value, name):
    if isinstance(value, bool):
        raise ToolError("%s must be a number" % name)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = _NUMBER_RE.match(value)
        if m:
            mult = _MULTIPLIERS.get(m.group(2))
            if mult is not None:
                return float(m.group(1)) * mult
    raise ToolError("%s must be a number (plain or with p/n/u/m/k/M/G suffix)" % name)


def as_value_list(value, name="value"):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            raise ToolError("%s must not be an empty list" % name)
        return [as_number(v, "%s[%d]" % (name, i)) for i, v in enumerate(value)]
    return as_number(value, name)


def resolve_element(doc, index=None, ref=None):
    els = doc.elements()
    if index is None and ref is None:
        raise ToolError("provide either 'index' or 'ref'")
    if index is not None:
        idx = as_int(index, "index", 0)
        if idx >= len(els):
            raise ToolError("element index %s is out of range (0..%d)"
                            % (idx, len(els) - 1) if els else
                            "element index %s is out of range (schematic is empty)" % idx)
        return els[idx]
    key = str(ref)
    matches = [e for e in els if e.refid == key]
    if not matches:
        raise ToolError("no element with reference %r" % key)
    if len(matches) > 1:
        raise ToolError(
            "reference %r is ambiguous; %d elements match at indices %s. "
            "Use 'index' to select one."
            % (key, len(matches), ", ".join(str(e.index) for e in matches))
        )
    return matches[0]


def resolve_endpoint(doc, value, field_name):
    if isinstance(value, bool):
        raise ToolError("%s must be an element index or a reference designator" % field_name)
    if isinstance(value, int):
        return resolve_element(doc, index=value)
    if isinstance(value, float) and value.is_integer():
        return resolve_element(doc, index=int(value))
    if isinstance(value, str):
        return resolve_element(doc, ref=value)
    raise ToolError("%s must be an element index or a reference designator" % field_name)


def parse_route(value):
    if value is None:
        return "auto"
    if isinstance(value, str):
        v = value.strip().lower()
        if v == "auto":
            return "auto"
        if v in ("none", "off", "no"):
            return None
        raise ToolError("route must be 'auto', 'none', or a list of [direction, length]")
    if isinstance(value, (list, tuple)):
        out = []
        for i, item in enumerate(value):
            if isinstance(item, dict):
                d = as_int(item.get("direction"), "route[%d].direction" % i)
                n = as_int(item.get("length"), "route[%d].length" % i, 1)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                d = as_int(item[0], "route[%d][0]" % i)
                n = as_int(item[1], "route[%d][1]" % i, 1)
            else:
                raise ToolError("route[%d] must be [direction, length]" % i)
            if d not in DIRECTION_CODES:
                raise ToolError("route[%d] direction %s is invalid (allowed: %s)"
                                % (i, d, sorted(DIRECTION_CODES)))
            out.append((d, n))
        if not out:
            raise ToolError("route list must not be empty")
        return out
    raise ToolError("route must be 'auto', 'none', or a list of [direction, length]")


def element_selector_schema():
    return {
        "index": {"type": "integer", "minimum": 0,
                  "description": "Zero-based element index (preferred for ambiguous refs such as grounds)."},
        "ref": {"type": ["string", "integer"],
                "description": "Reference designator, e.g. 'R1'. Numeric strings refer to the designator, not the index."},
    }


# ---------------------------------------------------------------------------
# Editing helpers
# ---------------------------------------------------------------------------
def create_component(doc, spec, warnings):
    if not isinstance(spec, dict):
        raise ToolError("component must be an object")
    if "part" not in spec:
        raise ToolError("component.part is required")
    pn = resolve_part(spec["part"])
    x = as_int(spec.get("x"), "x")
    y = as_int(spec.get("y"), "y")
    rot = spec.get("rotation")
    if rot is not None:
        rot = as_int(rot, "rotation", 0, 7)
    ref = spec.get("ref")
    if ref is not None:
        ref = str(ref).strip()
        if not ref:
            raise ToolError("component.ref must not be empty")
        if ref in [e.refid for e in doc.elements()] and not (pn == 8 and ref == "0"):
            raise ToolError("reference %r is already used" % ref)
    value = as_value_list(spec.get("value"), "value")
    model = spec.get("model")
    if model is not None:
        model = str(model)
        if parts.PARTS[pn][4] is None:
            raise ToolError("%s has no ModelName field" % parts.PARTS[pn][0])
    if value is not None and parts.PARTS[pn][2] is None:
        raise ToolError("%s has no Value field" % parts.PARTS[pn][0])
    element = doc.add_component(pn, ref, x=x, y=y, rot=rot,
                                value=value, model=model)
    if not element.pins:
        if parts.PINS.get(pn):
            warnings.append(
                "%s uses rotation %s, for which pin geometry is not known; wires "
                "will be stored without an explicit route" %
                (element.refid, element.rot)
            )
        else:
            warnings.append(
                "%s has no observed pin geometry; wires will be stored without "
                "an explicit route" % element.refid
            )
    return element


def add_wire_checked(doc, a, pa, b, pb, route="auto", node="0",
                     colour=0, wire_id=0, allow_duplicate=False):
    warnings = []
    pa = as_int(pa, "pin", 0)
    pb = as_int(pb, "pin", 0)
    if a is b and pa == pb:
        raise ToolError("cannot connect a pin to itself")
    for e, pin in ((a, pa), (b, pb)):
        count = parts.terminal_count(e.partnum) if e.partnum is not None else None
        if count is not None and pin >= count:
            raise ToolError("%s pin %s is out of range (part has %d pins)"
                            % (e.refid, pin, count))
    if not allow_duplicate:
        for w in doc.wires():
            pos = w.pos
            if pos and tuple(sorted(((pos[0], pos[1]), (pos[2], pos[3])))) == \
                    tuple(sorted(((a.index, pa), (b.index, pb)))):
                raise ToolError("a wire already connects %s.%s to %s.%s"
                                % (a.refid, pa, b.refid, pb))
    parsed = parse_route(route)
    wire = doc.add_wire(a, pa, b, pb, node_p=str(node),
                        colour=as_int(colour, "colour"),
                        wire_id=as_int(wire_id, "wire_id"), route=parsed)
    if parsed == "auto" and wire.segs is None:
        warnings.append("pin geometry is unknown; wire %s was stored without "
                        "an explicit route" % wire.index)
    if wire.segs is not None:
        apos = a.pin_position(pa)
        bpos = b.pin_position(pb)
        if apos and bpos:
            pts = wire.path_points()
            if not pts or tuple(pts[-1]) != tuple(bpos):
                doc.wires_block.remove_child(wire.block)
                raise ToolError("explicit route does not end at the target pin")
    return wire, warnings


def build_summary(doc):
    els = doc.elements()
    wires = doc.wires()
    return {
        "element_count": len(els),
        "wire_count": len(wires),
        "net_count": len(doc.nets()) if wires else 0,
        "elements": [e.to_dict() for e in els],
        "wires": [w.to_dict() for w in wires],
    }


def save_edited(path, info, doc):
    data = codec.build_ewb(doc.to_bytes(), header=info["header"])
    atomic_write(path, data)
    return len(data)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------
def tool_list_parts(args):
    query = (args.get("query") or "").strip().lower()
    only_with_pins = bool(args.get("only_with_pins"))
    include_rotations = args.get("include_rotations", True)
    out = []
    for item in parts.supported_parts():
        pn = item["partnum"]
        if only_with_pins and not parts.PINS.get(pn):
            continue
        haystack = " ".join([
            str(pn), item["name"], item["ref_prefix"], item["description"] or ""
        ]).lower()
        if query and query not in haystack:
            continue
        item["default_rotation"] = parts.default_rot(pn)
        item["terminal_count"] = parts.terminal_count(pn)
        if not include_rotations:
            item.pop("rotations", None)
        out.append(item)
    return {"count": len(out), "parts": out}


def tool_read_schematic(args):
    p, info, doc = load_document(args.get("path"))
    include_pins = args.get("include_pins", True)
    include_wires = args.get("include_wires", True)
    include_nets = args.get("include_nets", True)
    elements = []
    for e in doc.elements():
        item = e.to_dict()
        if not include_pins:
            item.pop("pins", None)
        elements.append(item)
    result = {
        "path": str(p),
        "format": {
            "container": "Electronics Workbench Circuit File",
            "header": header_info(info["header"]),
            "document_bytes": len(info["document"]),
            "payload_blocks": len(info["blocks"]),
            "checksum": info["checksum"],
            "document_roundtrip_exact": doc.to_bytes() == info["document"],
        },
        "counts": {
            "elements": len(elements),
            "wires": len(doc.wires()),
        },
        "elements": elements,
    }
    if include_wires:
        result["wires"] = [w.to_dict() for w in doc.wires()]
    if include_nets:
        result["nets"] = doc.nets()
    if args.get("include_text"):
        result["text"] = info["document"].decode("latin1")
    diag = inspect_document(doc, info)
    result["errors"] = diag["errors"]
    result["warnings"] = diag["warnings"]
    result["counts"]["nets"] = len(result.get("nets", []))
    return result


def tool_render_svg(args):
    p, info, doc = load_document(args.get("path"))
    width = as_int(args.get("width", 1400), "width", 200, 20000)
    height = as_int(args.get("height", 900), "height", 200, 20000)
    output = args.get("output_path")
    if output:
        out = resolve_path(output, suffix=".svg")
    else:
        out = resolve_path(str(p.with_suffix(".svg")), suffix=".svg")
    svg = svgmod.render_svg(doc, width=width, height=height)
    atomic_write(out, svg.encode("utf-8"), backup=False)
    result = {
        "path": str(out),
        "bytes": out.stat().st_size,
        "width": width,
        "height": height,
        "element_count": len(doc.elements()),
        "wire_count": len(doc.wires()),
    }
    if args.get("inline"):
        result["svg"] = svg
    return result


def _blank_document():
    return docmod.Document.blank()


def tool_create_schematic(args):
    p = resolve_path(args.get("path"), suffix=".ewb")
    overwrite = bool(args.get("overwrite", False))
    if p.exists() and not overwrite:
        raise ToolError("%s already exists; pass overwrite=true to replace it" % p)
    description = str(args.get("description") or "")
    components = args.get("components") or []
    wire_specs = args.get("wires") or []
    if not isinstance(components, list) or not isinstance(wire_specs, list):
        raise ToolError("components and wires must be arrays")

    doc = _blank_document()
    warnings = []
    created = []
    for spec in components:
        created.append(create_component(doc, spec, warnings))
    for i, spec in enumerate(wire_specs):
        if not isinstance(spec, dict):
            raise ToolError("wire %d must be an object" % i)
        for key in ("from", "from_pin", "to", "to_pin"):
            if key not in spec:
                raise ToolError("wire %d is missing %r" % (i, key))
        a = resolve_endpoint(doc, spec["from"], "wire[%d].from" % i)
        b = resolve_endpoint(doc, spec["to"], "wire[%d].to" % i)
        _, ww = add_wire_checked(
            doc, a, spec["from_pin"], b, spec["to_pin"],
            route=spec.get("route", "auto"),
            node=spec.get("node", "0"),
            colour=spec.get("colour", 0),
            wire_id=spec.get("wire_id", 0),
            allow_duplicate=bool(spec.get("allow_duplicate", False)),
        )
        warnings.extend(ww)
    diag = inspect_document(doc)
    if diag["errors"]:
        raise ToolError("generated schematic failed validation: %s"
                        % "; ".join(diag["errors"]))
    data = codec.build_ewb(doc.to_bytes(),
                           header=codec.make_header(description=description))
    atomic_write(p, data, backup=True)
    result = build_summary(doc)
    result.update({
        "path": str(p),
        "created": True,
        "description": description,
        "warnings": warnings + diag["warnings"],
        "errors": diag["errors"],
    })
    return result


def tool_add_component(args):
    p, info, doc = load_document(args.get("path"), for_edit=True)
    spec = {
        "part": args.get("part"),
        "ref": args.get("ref"),
        "x": args.get("x"),
        "y": args.get("y"),
        "rotation": args.get("rotation"),
        "value": args.get("value"),
        "model": args.get("model"),
    }
    for key in ("part", "x", "y"):
        if spec[key] is None:
            raise ToolError("%s is required" % key)
    warnings = []
    element = create_component(doc, spec, warnings)
    diag = inspect_document(doc)
    if diag["errors"]:
        raise ToolError("edit would make the schematic invalid: %s"
                        % "; ".join(diag["errors"]))
    size = save_edited(p, info, doc)
    return {
        "path": str(p),
        "bytes": size,
        "element": element.to_dict(),
        "element_count": len(doc.elements()),
        "wire_count": len(doc.wires()),
        "warnings": warnings + diag["warnings"],
    }


def tool_add_wire(args):
    p, info, doc = load_document(args.get("path"), for_edit=True)
    for key in ("from", "from_pin", "to", "to_pin"):
        if key not in args:
            raise ToolError("%s is required" % key)
    a = resolve_endpoint(doc, args["from"], "from")
    b = resolve_endpoint(doc, args["to"], "to")
    wire, warnings = add_wire_checked(
        doc, a, args["from_pin"], b, args["to_pin"],
        route=args.get("route", "auto"),
        node=args.get("node", "0"),
        colour=args.get("colour", 0),
        wire_id=args.get("wire_id", 0),
        allow_duplicate=bool(args.get("allow_duplicate", False)),
    )
    diag = inspect_document(doc)
    if diag["errors"]:
        raise ToolError("edit would make the schematic invalid: %s"
                        % "; ".join(diag["errors"]))
    size = save_edited(p, info, doc)
    return {
        "path": str(p),
        "bytes": size,
        "wire": wire.to_dict(),
        "element_count": len(doc.elements()),
        "wire_count": len(doc.wires()),
        "warnings": warnings + diag["warnings"],
    }


def tool_update_component(args):
    p, info, doc = load_document(args.get("path"), for_edit=True)
    element = resolve_element(doc, index=args.get("index"), ref=args.get("ref"))
    warnings = []
    changes = {}

    if args.get("refid") is not None:
        new_ref = str(args["refid"]).strip()
        if not new_ref:
            raise ToolError("refid must not be empty")
        if new_ref != element.refid:
            if new_ref in [e.refid for e in doc.elements() if e is not element] \
                    and not (element.partnum == 8 and new_ref == "0"):
                raise ToolError("reference %r is already used" % new_ref)
            element.set_refid(new_ref)
            changes["refid"] = new_ref

    if args.get("value") is not None:
        element.set_value(as_value_list(args["value"]))
        changes["value"] = element.value

    if args.get("model") is not None:
        element.set_model(str(args["model"]))
        changes["model"] = element.model

    position_fields = [k for k in ("x", "y", "rotation") if args.get(k) is not None]
    if position_fields:
        x = as_int(args["x"], "x") if args.get("x") is not None else element.x
        y = as_int(args["y"], "y") if args.get("y") is not None else element.y
        rot = as_int(args["rotation"], "rotation", 0, 7) \
            if args.get("rotation") is not None else element.rot
        element.set_position(x, y, rot)
        changes["position"] = {"x": element.x, "y": element.y, "rotation": element.rot}
        rerouted = []
        for w in doc.wires_touching(element.index):
            segs = parts.reroute_wire(w)
            rerouted.append({"wire": w.index, "routed": segs is not None})
            if segs is None:
                warnings.append("wire %s now touches a pin with unknown "
                                "geometry and has no stored route" % w.index)
        changes["rerouted_wires"] = rerouted

    if not changes:
        raise ToolError("no changes requested")
    diag = inspect_document(doc)
    if diag["errors"]:
        raise ToolError("edit would make the schematic invalid: %s"
                        % "; ".join(diag["errors"]))
    size = save_edited(p, info, doc)
    return {
        "path": str(p),
        "bytes": size,
        "element": element.to_dict(),
        "changes": changes,
        "warnings": warnings + diag["warnings"],
    }


def tool_update_wire(args):
    p, info, doc = load_document(args.get("path"), for_edit=True)
    index = as_int(args.get("index"), "index", 0)
    wires = doc.wires()
    if index >= len(wires):
        raise ToolError("wire index %s is out of range (0..%d)"
                        % (index, len(wires) - 1) if wires else
                        "wire index %s is out of range (no wires)" % index)
    wire = wires[index]
    warnings = []
    changes = {}
    if args.get("route") is not None:
        route = parse_route(args["route"])
        if route == "auto":
            segs = parts.reroute_wire(wire)
            if segs is None:
                warnings.append("pin geometry is unknown; wire has no stored route")
        elif route is None:
            wire.set_route(None)
        else:
            wire.set_route(route)
            a, pa, b, pb = wire.endpoints
            apos = a.pin_position(pa) if a else None
            bpos = b.pin_position(pb) if b else None
            if apos and bpos:
                pts = wire.path_points()
                if not pts or tuple(pts[-1]) != tuple(bpos):
                    raise ToolError("explicit route does not end at the target pin")
        changes["route"] = wire.segs
    if args.get("node") is not None:
        wire.set_node_p(str(args["node"]))
        changes["node"] = wire.node_p
    if args.get("colour") is not None:
        wire.block.set_field("colour", [as_int(args["colour"], "colour")])
        changes["colour"] = wire.colour
    if args.get("wire_id") is not None:
        wire.block.set_field("wire_id", [as_int(args["wire_id"], "wire_id")])
        changes["wire_id"] = wire.wire_id
    if not changes:
        raise ToolError("no changes requested")
    diag = inspect_document(doc)
    if diag["errors"]:
        raise ToolError("edit would make the schematic invalid: %s"
                        % "; ".join(diag["errors"]))
    size = save_edited(p, info, doc)
    return {
        "path": str(p),
        "bytes": size,
        "wire": wire.to_dict(),
        "changes": changes,
        "warnings": warnings + diag["warnings"],
    }


def tool_remove_component(args):
    p, info, doc = load_document(args.get("path"), for_edit=True)
    element = resolve_element(doc, index=args.get("index"), ref=args.get("ref"))
    remove_wires = bool(args.get("remove_wires", True))
    touching = doc.wires_touching(element.index)
    if not remove_wires and touching:
        raise ToolError(
            "component has %d attached wire(s); remove them first or pass "
            "remove_wires=true" % len(touching)
        )
    removed = element.to_dict()
    removed_wires = [w.index for w in touching]
    doc.remove_element(element, remove_wires=remove_wires)
    diag = inspect_document(doc)
    if diag["errors"]:
        raise ToolError("edit would make the schematic invalid: %s"
                        % "; ".join(diag["errors"]))
    size = save_edited(p, info, doc)
    return {
        "path": str(p),
        "bytes": size,
        "removed_element": removed,
        "removed_wires": removed_wires,
        "element_count": len(doc.elements()),
        "wire_count": len(doc.wires()),
        "warnings": diag["warnings"],
    }


def tool_remove_wire(args):
    p, info, doc = load_document(args.get("path"), for_edit=True)
    index = as_int(args.get("index"), "index", 0)
    wires = doc.wires()
    if index >= len(wires):
        raise ToolError("wire index %s is out of range (0..%d)"
                        % (index, len(wires) - 1) if wires else
                        "wire index %s is out of range (no wires)" % index)
    wire = wires[index]
    removed = wire.to_dict()
    doc.remove_wire(wire)
    diag = inspect_document(doc)
    if diag["errors"]:
        raise ToolError("edit would make the schematic invalid: %s"
                        % "; ".join(diag["errors"]))
    size = save_edited(p, info, doc)
    return {
        "path": str(p),
        "bytes": size,
        "removed_wire": removed,
        "element_count": len(doc.elements()),
        "wire_count": len(doc.wires()),
        "warnings": diag["warnings"],
    }


def tool_validate(args):
    try:
        p, info, doc = load_document(args.get("path"))
    except ToolError as exc:
        return {
            "valid": False,
            "path": str(args.get("path")),
            "errors": [str(exc)],
            "warnings": [],
            "checks": {},
        }
    diag = inspect_document(doc, info)
    meta = header_info(info["header"])
    return {
        "valid": not diag["errors"],
        "path": str(p),
        "format": {
            "header": meta,
            "document_bytes": len(info["document"]),
            "payload_blocks": len(info["blocks"]),
        },
        "errors": diag["errors"],
        "warnings": diag["warnings"],
        "checks": diag["checks"],
        "details": diag["details"],
        "counts": {
            "elements": len(doc.elements()),
            "wires": len(doc.wires()),
            "nets": len(doc.nets()) if doc.wires() else 0,
        },
    }


# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------
def _schema(properties, required=None, any_of=None):
    s = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        "required": required or [],
    }
    if any_of:
        s["anyOf"] = any_of
    return s


PATH_PROP = {"type": "string", "description": "Path to an .ewb file (workspace or /tmp)."}
ROUTE_PROP = {
    "oneOf": [
        {"type": "string", "enum": ["auto", "none"]},
        {"type": "array", "minItems": 1,
         "items": {"type": "array", "minItems": 2, "maxItems": 2,
                   "items": {"type": "integer"}}},
    ],
    "description": "Wire route: 'auto' (orthogonal L), 'none' (let EWB route), "
                   "or explicit [direction, length] pairs (1=+x, 2=+y, 4=-x, 8=-y).",
}
COMPONENT_ITEM = {
    "type": "object",
    "properties": {
        "part": {"type": ["string", "integer"],
                 "description": "Part name (e.g. 'RESISTOR', 'LED') or PartNum."},
        "ref": {"type": ["string", "integer"],
                "description": "Reference designator; generated when omitted."},
        "x": {"type": "integer"},
        "y": {"type": "integer"},
        "rotation": {"type": "integer", "minimum": 0, "maximum": 7},
        "value": {"type": ["number", "string", "array"],
                  "items": {"type": "number"},
                  "description": "Value or value list; suffixes k/M/u/n/p are accepted."},
        "model": {"type": "string"},
    },
    "required": ["part", "x", "y"],
    "additionalProperties": False,
}
WIRE_ITEM = {
    "type": "object",
    "properties": {
        "from": {"type": ["string", "integer"],
                 "description": "Source: component index in this call, or reference designator."},
        "from_pin": {"type": "integer", "minimum": 0},
        "to": {"type": ["string", "integer"],
               "description": "Target: component index in this call, or reference designator."},
        "to_pin": {"type": "integer", "minimum": 0},
        "route": ROUTE_PROP,
        "node": {"type": "string"},
        "colour": {"type": "integer"},
        "wire_id": {"type": "integer"},
        "allow_duplicate": {"type": "boolean"},
    },
    "required": ["from", "from_pin", "to", "to_pin"],
    "additionalProperties": False,
}

TOOLS = [
    {
        "name": "ewb_list_parts",
        "description": "List the component types supported by the EWB 5.12 catalog, "
                       "including PartNum, name, default value, pin count and known rotations.",
        "inputSchema": _schema({
            "query": {"type": "string", "description": "Optional substring filter."},
            "only_with_pins": {"type": "boolean",
                               "description": "Only parts with known pin geometry."},
            "include_rotations": {"type": "boolean", "default": True},
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
        "handler": tool_list_parts,
    },
    {
        "name": "ewb_read_schematic",
        "description": "Read an EWB 5.x .ewb schematic: components, positions, values, "
                       "pins, wires, nets and structural warnings.",
        "inputSchema": _schema({
            "path": PATH_PROP,
            "include_pins": {"type": "boolean", "default": True},
            "include_wires": {"type": "boolean", "default": True},
            "include_nets": {"type": "boolean", "default": True},
            "include_text": {"type": "boolean", "default": False,
                             "description": "Also return the decoded Project_5_1 text."},
        }, required=["path"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
        "handler": tool_read_schematic,
    },
    {
        "name": "ewb_render_svg",
        "description": "Render a schematic to an SVG preview file.",
        "inputSchema": _schema({
            "path": PATH_PROP,
            "output_path": {"type": "string",
                            "description": "SVG output path; defaults to the .ewb path with .svg."},
            "width": {"type": "integer", "minimum": 200, "maximum": 20000, "default": 1400},
            "height": {"type": "integer", "minimum": 200, "maximum": 20000, "default": 900},
            "inline": {"type": "boolean", "default": False,
                       "description": "Include the SVG markup in the tool result."},
        }, required=["path"]),
        "annotations": {"readOnlyHint": False, "idempotentHint": True},
        "handler": tool_render_svg,
    },
    {
        "name": "ewb_create_schematic",
        "description": "Create a new EWB 5.12-compatible .ewb file, optionally populating "
                       "it with components and wires in one call.",
        "inputSchema": _schema({
            "path": PATH_PROP,
            "overwrite": {"type": "boolean", "default": False},
            "description": {"type": "string",
                            "description": "Circuit description stored in the file header."},
            "components": {"type": "array", "items": COMPONENT_ITEM, "default": []},
            "wires": {"type": "array", "items": WIRE_ITEM, "default": []},
        }, required=["path"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
        "handler": tool_create_schematic,
    },
    {
        "name": "ewb_add_component",
        "description": "Add one component to an existing schematic using a catalog part "
                       "(name or PartNum) and position.",
        "inputSchema": _schema({
            "path": PATH_PROP,
            "part": {"type": ["string", "integer"]},
            "ref": {"type": ["string", "integer"]},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "rotation": {"type": "integer", "minimum": 0, "maximum": 7},
            "value": {"type": ["number", "string", "array"], "items": {"type": "number"}},
            "model": {"type": "string"},
        }, required=["path", "part", "x", "y"]),
        "annotations": {"readOnlyHint": False},
        "handler": tool_add_component,
    },
    {
        "name": "ewb_add_wire",
        "description": "Connect two component pins with a wire. Endpoints can be element "
                       "indices or unique reference designators.",
        "inputSchema": _schema({
            "path": PATH_PROP,
            "from": {"type": ["string", "integer"]},
            "from_pin": {"type": "integer", "minimum": 0},
            "to": {"type": ["string", "integer"]},
            "to_pin": {"type": "integer", "minimum": 0},
            "route": ROUTE_PROP,
            "node": {"type": "string", "description": "Net label stored in node_p (default '0')."},
            "colour": {"type": "integer"},
            "wire_id": {"type": "integer"},
            "allow_duplicate": {"type": "boolean"},
        }, required=["path", "from", "from_pin", "to", "to_pin"]),
        "annotations": {"readOnlyHint": False},
        "handler": tool_add_wire,
    },
    {
        "name": "ewb_update_component",
        "description": "Move, rotate, rename or change the value/model of a component. "
                       "Touching wires are re-routed automatically when pin geometry is known.",
        "inputSchema": _schema(dict(element_selector_schema(), **{
            "path": PATH_PROP,
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "rotation": {"type": "integer", "minimum": 0, "maximum": 7},
            "refid": {"type": ["string", "integer"]},
            "value": {"type": ["number", "string", "array"], "items": {"type": "number"}},
            "model": {"type": "string"},
        }), required=["path"], any_of=[{"required": ["index"]}, {"required": ["ref"]}]),
        "annotations": {"readOnlyHint": False},
        "handler": tool_update_component,
    },
    {
        "name": "ewb_update_wire",
        "description": "Change a wire's route, net label, colour or wire id.",
        "inputSchema": _schema({
            "path": PATH_PROP,
            "index": {"type": "integer", "minimum": 0},
            "route": ROUTE_PROP,
            "node": {"type": "string"},
            "colour": {"type": "integer"},
            "wire_id": {"type": "integer"},
        }, required=["path", "index"]),
        "annotations": {"readOnlyHint": False},
        "handler": tool_update_wire,
    },
    {
        "name": "ewb_remove_component",
        "description": "Remove a component and, by default, all wires attached to it.",
        "inputSchema": _schema(dict(element_selector_schema(), **{
            "path": PATH_PROP,
            "remove_wires": {"type": "boolean", "default": True},
        }), required=["path"], any_of=[{"required": ["index"]}, {"required": ["ref"]}]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
        "handler": tool_remove_component,
    },
    {
        "name": "ewb_remove_wire",
        "description": "Remove one wire by its zero-based index.",
        "inputSchema": _schema({
            "path": PATH_PROP,
            "index": {"type": "integer", "minimum": 0},
        }, required=["path", "index"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
        "handler": tool_remove_wire,
    },
    {
        "name": "ewb_validate",
        "description": "Validate the container, document structure, element data, wire "
                       "indices, pins, routes and checksum. Returns errors and warnings.",
        "inputSchema": _schema({"path": PATH_PROP}, required=["path"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
        "handler": tool_validate,
    },
]

TOOL_MAP = {t["name"]: t for t in TOOLS}


# ---------------------------------------------------------------------------
# JSON-RPC / MCP transport
# ---------------------------------------------------------------------------
class Transport:
    def __init__(self, stdin, stdout):
        self.stdin = stdin
        self.stdout = stdout
        self.framing = "line"

    def read_message(self):
        line = self.stdin.readline()
        if not line:
            return None
        while line in (b"\r\n", b"\n"):
            line = self.stdin.readline()
            if not line:
                return None
        if line.lower().startswith(b"content-length:"):
            self.framing = "lsp"
            try:
                length = int(line.split(b":", 1)[1].strip())
            except ValueError:
                return ""
            while True:
                h = self.stdin.readline()
                if h in (b"\r\n", b"\n", b""):
                    break
            body = self.stdin.read(length)
            return body.decode("utf-8", "replace")
        self.framing = "line"
        return line.decode("utf-8", "replace").strip()

    def write_message(self, message):
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if self.framing == "lsp":
            self.stdout.write(b"Content-Length: %d\r\n\r\n" % len(body))
            self.stdout.write(body)
        else:
            self.stdout.write(body + b"\n")
        self.stdout.flush()


def rpc_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def rpc_error(req_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def tool_result(data):
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    result = {
        "content": [{"type": "text", "text": text}],
        "isError": False,
        "structuredContent": data,
    }
    return result


def tool_error(message, data=None):
    payload = {"error": str(message)}
    if data is not None:
        payload["details"] = data
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": True,
    }


def handle_initialize(params):
    params = params or {}
    requested = params.get("protocolVersion")
    version = requested if isinstance(requested, str) and requested else DEFAULT_PROTOCOL
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": (
            "Tools for reading, rendering, validating, editing and creating "
            "Electronics Workbench 5.x .ewb schematics. Paths are restricted to "
            "the workspace, /tmp and directories allowed by the server "
            "configuration. New files use EncryptionType 2 and the Project_5_1 "
            "document format used by EWB 5.12."
        ),
    }


def handle_tools_call(params):
    params = params or {}
    name = params.get("name")
    if not name:
        raise ToolError("tools/call requires a tool name")
    tool = TOOL_MAP.get(name)
    if tool is None:
        raise ToolError("unknown tool %r" % name)
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        raise ToolError("tool arguments must be an object")
    try:
        data = tool["handler"](args)
    except ToolError as exc:
        return tool_error(exc)
    except (KeyError, ValueError, OSError, TypeError) as exc:
        return tool_error("%s: %s" % (type(exc).__name__, exc))
    except Exception as exc:
        if os.environ.get("EWB_MCP_DEBUG"):
            log(traceback.format_exc())
        return tool_error("internal error: %s: %s" % (type(exc).__name__, exc))
    return tool_result(data)


def dispatch(message):
    if not isinstance(message, dict):
        return rpc_error(None, -32600, "Invalid Request")
    method = message.get("method")
    req_id = message.get("id")
    is_notification = "id" not in message
    params = message.get("params")

    if method == "initialize":
        result = handle_initialize(params)
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {
            "tools": [
                {k: v for k, v in t.items() if k in
                 ("name", "description", "inputSchema", "annotations")}
                for t in TOOLS
            ]
        }
    elif method == "tools/call":
        result = handle_tools_call(params)
    elif method in ("notifications/initialized", "notifications/cancelled",
                    "notifications/roots/list_changed"):
        return None
    elif method == "resources/list":
        result = {"resources": []}
    elif method == "prompts/list":
        result = {"prompts": []}
    elif method == "logging/setLevel":
        result = {}
    else:
        if is_notification:
            return None
        return rpc_error(req_id, -32601, "Method not found: %s" % method)

    if is_notification:
        return None
    return rpc_result(req_id, result)


def main():
    transport = Transport(sys.stdin.buffer, sys.stdout.buffer)
    log("%s %s ready (allowed roots: %s)"
        % (SERVER_NAME, SERVER_VERSION,
           ", ".join(str(r) for r in allowed_roots())))
    while True:
        try:
            raw = transport.read_message()
        except (KeyboardInterrupt, EOFError):
            break
        if raw is None:
            break
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            transport.write_message(rpc_error(None, -32700, "Parse error: %s" % exc))
            continue
        try:
            if isinstance(message, list):
                responses = [r for r in (dispatch(m) for m in message) if r is not None]
                if responses:
                    transport.write_message(responses)
            else:
                response = dispatch(message)
                if response is not None:
                    transport.write_message(response)
        except Exception as exc:
            if os.environ.get("EWB_MCP_DEBUG"):
                log(traceback.format_exc())
            req_id = message.get("id") if isinstance(message, dict) else None
            transport.write_message(rpc_error(req_id, -32603,
                                              "Internal error: %s" % exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
