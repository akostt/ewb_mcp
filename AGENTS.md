# EWB 5.12 schematics

This package is an MCP server plus an agent skill for Electronics Workbench
5.x `.ewb` files. It reads, validates, edits, renders and creates schematics
while preserving the native container and `Project_5_1` document format.

For any task involving `.ewb` files, follow `skills/ewb-schematics/SKILL.md`.
The practical rules are:

- inspect with `ewb_read_schematic` before editing;
- use element indices, not ambiguous references such as ground `"0"`;
- validate after each change with `ewb_validate`;
- render with `ewb_render_svg` and inspect the result;
- never install, launch or automate EWB itself;
- never overwrite the user's original file unless explicitly asked.

The MCP server is `server.py`, is written for Python 3.8+ and has no external
dependencies. It is registered by the plugin manifests in this directory.
