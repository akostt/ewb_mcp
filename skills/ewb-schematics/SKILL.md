---
name: ewb-schematics
description: Read, validate, edit, render and create Electronics Workbench 5.x (.ewb) schematics with the ewb512 MCP tools. Use whenever a task involves an .ewb file, EWB 5.12, Electronics Workbench circuits, adding or moving components and wires, building a new circuit, or producing an SVG preview. Russian triggers: "EWB", "Electronics Workbench", "схема EWB", ".ewb", "собери схему", "добавь резистор", "соедини выводы", "проверь схему".
---

# EWB 5.12 schematics

Use the `ewb512` MCP server. It preserves the native `.ewb` container
(`EncryptionType: 2`) and the `Project_5_1` document format, so every saved
file remains editable in Electronics Workbench 5.12.

Do not install, launch or automate EWB itself. Everything is done by reading
and writing the file format.

## Tool map

| Tool | Use it for |
|---|---|
| `ewb_list_parts` | Discover supported parts, PartNum values, pin counts and known rotations. Start here when unsure about a part name. |
| `ewb_read_schematic` | Inspect elements, absolute pin coordinates, wires, nets, warnings. |
| `ewb_validate` | Check container, document structure, element fields, wire indices, pin geometry, routing and checksum. |
| `ewb_render_svg` | Produce an SVG preview for visual verification. |
| `ewb_create_schematic` | Create a new `.ewb`, optionally with components and wires in one call. |
| `ewb_add_component` | Add one catalog component. |
| `ewb_add_wire` | Connect two pins. |
| `ewb_update_component` | Move, rotate, rename, or change value/model. |
| `ewb_update_wire` | Change route, net label, colour or wire id. |
| `ewb_remove_component` | Delete a component and, by default, its wires. |
| `ewb_remove_wire` | Delete one wire by index. |

## Mandatory workflow

1. **Inspect before editing.** Call `ewb_read_schematic` with `include_pins: true`
   and `include_wires: true`. Use the returned element indices and pin numbers.
   Never guess a pin number from a symbol drawing.
2. **Check the baseline.** For an unfamiliar file call `ewb_validate` first.
   A file with `document_roundtrip_exact: false` is not safe to edit; stop and
   report it.
3. **Edit.** Prefer element indices over reference designators. Ground symbols
   all share `refid: "0"`, so a `ref` lookup for ground is ambiguous. Numeric
   strings such as `"2"` mean a reference designator, not an index; pass a JSON
   number for an index.
4. **Validate again.** Call `ewb_validate` after every edit and fix all errors.
   Warnings are informational unless they describe a wrong route or unknown pin.
5. **Render and look.** Call `ewb_render_svg` and inspect the SVG for overlapping
   labels, disconnected-looking wires or misplaced parts. The preview is
   approximate, not a pixel-accurate EWB rendering.

Edits are atomic and create `<name>.ewb.bak`. Never overwrite the user's
original file unless they explicitly asked to edit that path. When exploring,
copy it first or edit the copy.

## Creating a circuit

`ewb_create_schematic` accepts catalog parts, positions and wires. Wire
endpoints are either zero-based indices into the `components` array or unique
reference designators.

```json
{
  "path": "/absolute/path/rc_led.ewb",
  "overwrite": false,
  "description": "RC + LED",
  "components": [
    {"part": "GROUND", "x": 400, "y": 620},
    {"part": "GROUND", "x": 730, "y": 620},
    {"part": "BATTERY", "ref": "V1", "x": 400, "y": 500, "value": 9},
    {"part": "RESISTOR", "ref": "R1", "x": 500, "y": 460, "rotation": 1, "value": "1k"},
    {"part": "CAPACITOR", "ref": "C1", "x": 600, "y": 480, "value": "1u"},
    {"part": "LED", "ref": "D1", "x": 700, "y": 480, "rotation": 2}
  ],
  "wires": [
    {"from": "V1", "from_pin": 1, "to": "R1", "to_pin": 0},
    {"from": "R1", "from_pin": 1, "to": "C1", "to_pin": 0},
    {"from": "C1", "from_pin": 1, "to": "D1", "to_pin": 1},
    {"from": "D1", "from_pin": 0, "to": 1, "to_pin": 0},
    {"from": "V1", "from_pin": 0, "to": 0, "to_pin": 0}
  ]
}
```

Notes:

- Values accept numbers or strings with SI suffixes: `k`, `M`, `u`, `n`, `p`.
  A JSON array sets all value fields; a scalar sets the primary value.
- `rotation` is `0..7`. Only some part/rotation combinations have known pin
  geometry; `ewb_list_parts` reports them. Unknown geometry is allowed, but
  automatic wire routing is limited.
- `route` defaults to `"auto"` (orthogonal route). `route: "none"` writes no
  segment list and lets EWB route the wire when the file is opened.
- `node` is a net label (default `"0"`). It is metadata, not an electrical
  connection: connectivity comes from the wire endpoints.
- Node/junction markers are part `NODE` (PartNum 39).

## Coordinates and pins

`Position` is the element's anchor, not its body centre. Absolute pin position:

```text
pin_abs = Position + pin_offset(PartNum, rotation, pin)
```

Offsets are intentionally asymmetric. Always use pin coordinates reported by
`ewb_read_schematic` or the `pins` object returned by `ewb_add_component`.
When moving a component, the server re-routes attached wires automatically if
the pin geometry is known. Verify with `ewb_read_schematic` afterwards.

Wire segments are stored as `[direction, length]` pairs:

| Code | Direction |
|---:|---|
| 1 | +X |
| 2 | +Y |
| 4 | −X |
| 8 | −Y |
| 3, 6, 9, 12 | diagonals |

## Component catalog

Supported PartNum range is `0..39`: AC/DC voltage and current sources, battery,
resistor, capacitor, inductor, diode, Zener, LED, bulb, fuse, relay, NPN/PNP
transistors, JFETs, depletion/enhancement MOSFETs, op-amp, transformer,
ammeter, voltmeter, connector, ground, switches, time-delay switch, controlled
sources, and node. Use `ewb_list_parts` for exact names and aliases instead of
guessing.

Ground is special: EWB stores every ground symbol as reference `0`. Multiple
grounds are normal and expected.

## Reporting results

Report the file path, element count, wire count, net count, and the validation
result. If `ewb_validate` returns errors, quote them and do not claim success.
If a requested part or rotation has unknown pin geometry, say so explicitly
instead of silently producing a possibly wrong layout.

The SVG is a preview. Never present it as an EWB screenshot or as proof that
the circuit simulates correctly; the server performs structural validation
only, not electrical simulation or ERC.
