# EWB 5.12 schematics

This extension provides MCP tools and instructions for Electronics Workbench
5.x `.ewb` schematics. Read `skills/ewb-schematics/SKILL.md` before working
with a schematic.

Core rules:

- inspect the file first and use the reported element indices and pin numbers;
- ground symbols share reference `"0"`, so prefer indices for them;
- validate after every edit and render an SVG preview;
- preserve the `.ewb` container and `Project_5_1` format;
- do not launch or automate EWB;
- do not overwrite the user's original file unless explicitly asked.
