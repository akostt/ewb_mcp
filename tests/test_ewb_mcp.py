"""Tests for the EWB container codec, document model and MCP tools.

Run from the repository root:

    python3 -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ewb_blank
import ewb_codec as codec
import ewb_doc as docmod
import ewb_parts
import server


class CodecTests(unittest.TestCase):
    def test_blank_document_roundtrip(self):
        raw = ewb_blank.blank_document_text().encode("latin1")
        doc = docmod.Document.parse(raw)
        self.assertEqual(doc.root.name, "Project_5_1")
        self.assertEqual(doc.elements(), [])
        self.assertEqual(doc.wires(), [])
        self.assertEqual(doc.to_bytes(), raw)

    def test_compress_explode_roundtrip(self):
        samples = [b"", b"a", b"abcabcabc" * 20, bytes(range(256)) * 4]
        for sample in samples:
            with self.subTest(size=len(sample)):
                self.assertEqual(
                    codec.explode_block(codec.compress_lz_block(sample)), sample)
                self.assertEqual(
                    codec.explode_block(codec.compress_literal_block(sample)), sample)

    def test_container_roundtrip(self):
        document = docmod.Document.blank().to_bytes()
        container = codec.build_ewb(document, description="unit test")
        header, blocks, plains, decoded, checksum = codec.split_file(container)
        self.assertEqual(decoded, document)
        self.assertEqual(b"".join(plains), document)
        self.assertEqual(codec.document_checksum(document), checksum)
        self.assertEqual(header, codec.make_header(description="unit test"))
        self.assertTrue(blocks)
        self.assertEqual(
            codec.decode_payload(
                codec.encode_payload(blocks, checksum).encode("latin1")),
            blocks,
        )

    def test_split_file_rejects_garbage(self):
        with self.assertRaises(ValueError):
            codec.split_file(b"not an ewb file")


class ServerToolTests(unittest.TestCase):
    COMPONENTS = [
        {"part": "GROUND", "x": 400, "y": 620},
        {"part": "GROUND", "x": 730, "y": 620},
        {"part": "BATTERY", "ref": "V1", "x": 400, "y": 500, "value": 9},
        {"part": "RESISTOR", "ref": "R1", "x": 500, "y": 460,
         "rotation": 1, "value": "1k"},
        {"part": "CAPACITOR", "ref": "C1", "x": 600, "y": 480, "value": "1u"},
        {"part": "LED", "ref": "D1", "x": 700, "y": 480, "rotation": 2},
    ]
    WIRES = [
        {"from": "V1", "from_pin": 1, "to": "R1", "to_pin": 0},
        {"from": "R1", "from_pin": 1, "to": "C1", "to_pin": 0},
        {"from": "C1", "from_pin": 1, "to": "D1", "to_pin": 1},
        {"from": "D1", "from_pin": 0, "to": 1, "to_pin": 0},
        {"from": "V1", "from_pin": 0, "to": 0, "to_pin": 0},
    ]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self._old_allowed = os.environ.get("EWB_MCP_ALLOWED_DIRS")
        self._old_home = os.environ.pop("EWB_MCP_ALLOW_HOME", None)
        os.environ["EWB_MCP_ALLOWED_DIRS"] = str(self.root)
        server._ALLOWED_ROOTS = None

    def tearDown(self):
        self._tmp.cleanup()
        if self._old_allowed is None:
            os.environ.pop("EWB_MCP_ALLOWED_DIRS", None)
        else:
            os.environ["EWB_MCP_ALLOWED_DIRS"] = self._old_allowed
        if self._old_home is not None:
            os.environ["EWB_MCP_ALLOW_HOME"] = self._old_home
        server._ALLOWED_ROOTS = None

    def _create(self, name="rc_led.ewb"):
        path = self.root / name
        result = server.tool_create_schematic({
            "path": str(path),
            "description": "RC + LED",
            "components": self.COMPONENTS,
            "wires": self.WIRES,
        })
        return path, result

    def test_create_and_validate(self):
        path, created = self._create()
        self.assertTrue(created["created"])
        self.assertEqual(created["element_count"], 6)
        self.assertEqual(created["wire_count"], 5)
        self.assertEqual(created["net_count"], 5)
        self.assertTrue(path.is_file())

        result = server.tool_validate({"path": str(path)})
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["counts"],
                         {"elements": 6, "wires": 5, "nets": 5})
        for check in ("document_roundtrip_exact",
                      "container_roundtrip_exact",
                      "checksum_matches"):
            self.assertTrue(result["checks"][check], check)

        read = server.tool_read_schematic({"path": str(path)})
        self.assertEqual(read["counts"]["elements"], 6)
        self.assertEqual(read["counts"]["wires"], 5)
        self.assertEqual(read["format"]["header"]["description"], "RC + LED")
        self.assertEqual([e["refid"] for e in read["elements"]],
                         ["0", "0", "V1", "R1", "C1", "D1"])

    def test_all_catalog_parts_are_supported(self):
        components = [
            {"part": pn,
             "x": 100 + (pn % 8) * 120,
             "y": 100 + (pn // 8) * 120}
            for pn in sorted(ewb_parts.PARTS)
        ]
        path = self.root / "all_parts.ewb"
        result = server.tool_create_schematic({
            "path": str(path),
            "description": "catalog",
            "components": components,
        })
        self.assertEqual(result["element_count"], 40)
        self.assertEqual([e["partnum"] for e in result["elements"]],
                         sorted(ewb_parts.PARTS))
        self.assertEqual(len(result["warnings"]),
                         len(ewb_parts.PARTS) - len(ewb_parts.PINS))
        valid = server.tool_validate({"path": str(path)})
        self.assertTrue(valid["valid"], valid["errors"])

    def test_edits_keep_file_valid_and_create_backup(self):
        path, _ = self._create()
        backup = Path(str(path) + ".bak")

        added = server.tool_add_component({
            "path": str(path), "part": "RESISTOR", "ref": "R2",
            "x": 800, "y": 500, "rotation": 0, "value": "2k",
        })
        self.assertEqual(added["element_count"], 7)
        self.assertTrue(backup.is_file())

        moved = server.tool_update_component({
            "path": str(path), "ref": "R2", "x": 820, "y": 520,
        })
        self.assertEqual(moved["element"]["position"]["x"], 820)
        self.assertEqual(moved["element"]["position"]["y"], 520)

        removed = server.tool_remove_component({
            "path": str(path), "ref": "R2",
        })
        self.assertEqual(removed["element_count"], 6)
        self.assertEqual(removed["wire_count"], 5)

        result = server.tool_validate({"path": str(path)})
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["counts"]["elements"], 6)

    def test_grounds_require_index(self):
        path, _ = self._create()
        with self.assertRaises(server.ToolError):
            server.tool_update_component({
                "path": str(path), "ref": "0", "x": 1, "y": 1,
            })

        moved = server.tool_update_component({
            "path": str(path), "index": 0, "x": 410, "y": 620,
        })
        self.assertEqual(moved["element"]["position"]["x"], 410)
        self.assertTrue(server.tool_validate({"path": str(path)})["valid"])

    def test_rejects_bad_paths(self):
        missing = server.tool_validate({"path": str(self.root / "missing.ewb")})
        self.assertFalse(missing["valid"])
        self.assertTrue(missing["errors"])
        wrong_suffix = server.tool_validate({"path": str(self.root / "file.txt")})
        self.assertFalse(wrong_suffix["valid"])
        self.assertTrue(wrong_suffix["errors"])
        with self.assertRaises(server.ToolError):
            server.tool_create_schematic({
                "path": str(self.root / "x.ewb"),
                "components": [{"part": "NOPE", "x": 0, "y": 0}],
            })

    def test_render_svg(self):
        path, _ = self._create()
        out = self.root / "preview.svg"
        result = server.tool_render_svg({
            "path": str(path), "output_path": str(out),
        })
        self.assertEqual(result["element_count"], 6)
        self.assertTrue(out.is_file())
        text = out.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("<?xml"))
        self.assertIn("<svg ", text)
        self.assertIn("</svg>", text)


class ManifestTests(unittest.TestCase):
    """Keep the per-client plugin manifests mutually consistent."""

    JSON_FILES = [
        "plugin.json",
        "mcp.json",
        ".mcp.json",
        "mcp_config.json",
        "mcp_config.example.json",
        "gemini-extension.json",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        ".codex-plugin/plugin.json",
        ".cursor-plugin/plugin.json",
        ".devin-plugin/plugin.json",
        ".kimi-plugin/plugin.json",
        ".muse-plugin/plugin.json",
        ".muse-plugin/marketplace.json",
        ".antigravity-plugin/plugin.json",
        ".agents/plugins/marketplace.json",
        ".vscode/mcp.json",
    ]

    def setUp(self):
        self.core = self._load("plugin.json")

    def _load(self, rel):
        path = ROOT / rel
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _assert_exists(self, rel):
        path = (ROOT / rel).resolve()
        self.assertTrue(
            path.exists(),
            "%s is referenced by a manifest but does not exist" % rel,
        )

    def _assert_server(self, server, command="python3"):
        self.assertEqual(server["command"], command)
        self.assertIsInstance(server["args"], list)
        self.assertTrue(server["args"])

    def test_all_json_manifests_are_valid(self):
        for rel in self.JSON_FILES:
            with self.subTest(manifest=rel):
                data = self._load(rel)
                self.assertIsInstance(data, dict)

    def test_core_identity_is_consistent(self):
        for rel in self.JSON_FILES:
            data = self._load(rel)
            if "name" not in data or rel.endswith("marketplace.json"):
                continue
            with self.subTest(manifest=rel):
                self.assertEqual(data["name"], self.core["name"])
                self.assertEqual(data["version"], self.core["version"])

    def test_agent_plugins_mcp_manifest(self):
        data = self._load("mcp.json")
        self.assertEqual(
            data["$schema"],
            "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        )
        server = data["mcpServers"]["ewb512"]
        self._assert_server(server)
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["args"], ["${PLUGIN_ROOT}/scripts/server.py"])
        self.assertEqual(server["cwd"], "${PLUGIN_ROOT}")
        self.assertEqual(server["env"]["EWB_MCP_ALLOW_HOME"], "1")
        self.assertNotIn("${", server["command"])
        self.assertNotEqual(server["cwd"], ".")

    def test_claude_manifest_and_mcp(self):
        plugin = self._load(".claude-plugin/plugin.json")
        for rel in plugin.get("skills", []):
            self._assert_exists(rel)
        market = self._load(".claude-plugin/marketplace.json")
        self.assertEqual(market["plugins"][0]["name"], self.core["name"])
        server = self._load(".mcp.json")["mcpServers"]["ewb512"]
        self.assertEqual(server["args"], ["${CLAUDE_PLUGIN_ROOT}/scripts/server.py"])
        self.assertEqual(server["env"]["EWB_MCP_ALLOW_HOME"], "1")

    def test_codex_manifest_paths(self):
        plugin = self._load(".codex-plugin/plugin.json")
        self._assert_exists(plugin["skills"])
        self._assert_exists(plugin["mcpServers"])
        server = self._load(plugin["mcpServers"])["mcpServers"]["ewb512"]
        self._assert_server(server)
        self.assertEqual(server["type"], "stdio")
        self.assertIn("${PLUGIN_ROOT}/scripts/server.py", server["args"])

    def test_cursor_uses_cursor_root(self):
        plugin = self._load(".cursor-plugin/plugin.json")
        self._assert_exists(plugin["skills"])
        server = plugin["mcpServers"]["ewb512"]
        self._assert_server(server)
        self.assertEqual(server["type"], "stdio")
        self.assertIn("${CURSOR_PLUGIN_ROOT}/scripts/server.py", server["args"])
        self.assertNotIn("${PLUGIN_ROOT}", server["args"])
        self.assertEqual(server["env"]["EWB_MCP_ALLOW_HOME"], "1")

    def test_devin_declares_mcp_inline(self):
        plugin = self._load(".devin-plugin/plugin.json")
        self._assert_exists(plugin["skills"])
        self.assertIsInstance(plugin["mcpServers"], dict)
        server = plugin["mcpServers"]["ewb512"]
        self._assert_server(server)
        self.assertIn("./scripts/server.py", server["args"])
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", server["args"])
        self.assertEqual(server["env"]["EWB_MCP_ALLOW_HOME"], "1")

    def test_kimi_manifest(self):
        plugin = self._load(".kimi-plugin/plugin.json")
        self._assert_exists(plugin["skills"])
        self.assertEqual(plugin["sessionStart"]["skill"], "ewb-schematics")
        self._assert_exists("skills/ewb-schematics/SKILL.md")
        server = plugin["mcpServers"]["ewb512"]
        self._assert_server(server)
        self.assertEqual(server["cwd"], "./")
        self.assertEqual(server["env"]["EWB_MCP_ALLOW_HOME"], "1")

    def test_muse_manifest_and_launcher(self):
        plugin = self._load(".muse-plugin/plugin.json")
        self.assertEqual(plugin["schemaVersion"], 1)
        self.assertEqual(plugin["compat"]["manifestDir"], ".muse-plugin")
        skills = plugin["capabilities"]["skills"]
        self.assertEqual(skills[0]["id"], "ewb-schematics")
        self._assert_exists(skills[0]["path"])
        server = plugin["capabilities"]["mcpServers"][0]
        self.assertEqual(server["transport"], "stdio")
        self.assertEqual(server["command"][0], "python3")
        self.assertEqual(server["command"][1], "scripts/ewb_mcp_launcher.py")
        self._assert_exists(server["command"][1])
        launcher = (ROOT / "scripts" / "ewb_mcp_launcher.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("EWB_MCP_ALLOW_HOME", launcher)
        market = self._load(".muse-plugin/marketplace.json")
        self.assertEqual(market["plugins"][0]["name"], self.core["name"])

    def test_antigravity_manifest_and_mcp(self):
        plugin = self._load(".antigravity-plugin/plugin.json")
        self.assertEqual(plugin["name"], self.core["name"])
        server = self._load("mcp_config.json")["mcpServers"]["ewb512"]
        self._assert_server(server)
        self.assertEqual(server["args"], ["scripts/server.py"])
        self.assertEqual(server["cwd"], ".")
        self.assertEqual(server["env"]["EWB_MCP_ALLOW_HOME"], "1")

    def test_gemini_extension(self):
        data = self._load("gemini-extension.json")
        self._assert_exists(data["contextFileName"])
        server = data["mcpServers"]["ewb512"]
        self._assert_server(server)
        self.assertEqual(server["args"], ["${extensionPath}/scripts/server.py"])

    def test_vscode_mcp(self):
        data = self._load(".vscode/mcp.json")
        server = data["servers"]["ewb512"]
        self._assert_server(server)
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["args"], ["${workspaceFolder}/scripts/server.py"])

    def test_marketplace_names(self):
        for rel in (".claude-plugin/marketplace.json",
                    ".agents/plugins/marketplace.json",
                    ".muse-plugin/marketplace.json"):
            with self.subTest(manifest=rel):
                market = self._load(rel)
                self.assertEqual(market["name"], "ewb512-plugins")
                self.assertEqual(market["plugins"][0]["name"], self.core["name"])
                self.assertEqual(
                    market["plugins"][0]["version"], self.core["version"])

    def test_skill_frontmatter(self):
        text = (ROOT / "skills" / "ewb-schematics" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(text.startswith("---\n"))
        front = text.split("---\n", 2)[1]
        self.assertIn("name: ewb-schematics", front)
        self.assertIn("description:", front)

    def test_documentation_files_exist(self):
        for rel in ("README.md", "docs/README.md", "docs/INSTALL.md",
                    "docs/TOOLS.md", "docs/CATALOG.md", "docs/FORMAT.md",
                    "docs/TROUBLESHOOTING.md", ".opencode/INSTALL.md"):
            with self.subTest(path=rel):
                path = ROOT / rel
                self.assertTrue(path.is_file(), rel)
                self.assertGreater(path.stat().st_size, 200, rel)

    def test_catalog_document_covers_every_part(self):
        text = (ROOT / "docs" / "CATALOG.md").read_text(encoding="utf-8")
        self.assertEqual(len(ewb_parts.PARTS), 40)
        self.assertEqual(len(ewb_parts.PINS), 17)
        for partnum, spec in ewb_parts.PARTS.items():
            with self.subTest(partnum=partnum):
                self.assertIn("| %d | `%s` |" % (partnum, spec[0]), text)


ORIGINAL = ROOT / "local" / "examples" / "лаба 4.ewb"


@unittest.skipUnless(ORIGINAL.is_file(),
                     "original validation schematic is not present")
class OriginalSchematicTests(unittest.TestCase):
    def test_original_file_validates(self):
        result = server.tool_validate({"path": str(ORIGINAL)})
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["counts"]["elements"], 97)
        self.assertEqual(result["counts"]["wires"], 98)
        self.assertTrue(result["checks"]["document_roundtrip_exact"])
        self.assertTrue(result["checks"]["checksum_matches"])


if __name__ == "__main__":
    unittest.main()
