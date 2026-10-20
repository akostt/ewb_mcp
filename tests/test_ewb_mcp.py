"""Tests for the EWB container codec, document model and MCP tools.

Run from the repository root:

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ewb_blank
import ewb_codec as codec
import ewb_doc as docmod
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
