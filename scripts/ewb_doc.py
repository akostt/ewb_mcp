"""Exact parser/serializer for Electronics Workbench 5.x Project_5_1 documents.

The document is a CRLF text tree.  Every block is:

    <indent><name> \r\n
    <indent>{ \r\n
    ...children...
    <indent>}

Children are either nested blocks or raw text lines (fields, continuation
lines, ...).  Raw lines are preserved verbatim, which makes serialization
byte-exact for untouched content.
"""

import re

CRLF = "\r\n"

RE_FIELD = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(?: ([A-Za-z])(?::(\d+))? (.*?))? ?$")


class Block:
    __slots__ = ("header", "open_line", "children", "close_line", "parent")

    def __init__(self, header, open_line, children=None, close_line=None):
        self.header = header
        self.open_line = open_line
        self.children = children if children is not None else []
        self.close_line = close_line if close_line is not None else ""
        self.parent = None
        for c in self.children:
            if isinstance(c, Block):
                c.parent = self

    # ------------------------------------------------------------------ names
    @property
    def name(self):
        return self.header.strip()

    @property
    def indent(self):
        return len(self.header) - len(self.header.lstrip(" "))

    def blocks(self):
        return [c for c in self.children if isinstance(c, Block)]

    def lines(self):
        return [c for c in self.children if isinstance(c, str)]

    def child(self, name):
        for c in self.children:
            if isinstance(c, Block) and c.name == name:
                return c
        return None

    def children_named(self, name):
        return [c for c in self.children if isinstance(c, Block) and c.name == name]

    def find(self, path):
        node = self
        for name in path.split("/"):
            if node is None:
                return None
            node = node.child(name)
        return node

    def path(self):
        parts = []
        node = self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return "/".join(reversed(parts))

    # ------------------------------------------------------------------ fields
    def field_line(self, name):
        for c in self.children:
            if isinstance(c, str):
                m = RE_FIELD.match(c)
                if m and m.group(2) == name:
                    return c
        return None

    def field(self, name):
        line = self.field_line(name)
        if line is None:
            return None
        m = RE_FIELD.match(line)
        if not m or m.group(3) is None:
            return True
        typ = m.group(3)
        count = int(m.group(4)) if m.group(4) else 1
        raw = m.group(5)
        return parse_values(typ, count, raw)

    def set_field(self, name, values, typ=None, count=None):
        """Replace a direct field line.  values: str or list of scalars."""
        line = self.field_line(name)
        if line is None:
            raise KeyError("field %s not found in %s" % (name, self.name))
        m = RE_FIELD.match(line)
        old_typ = m.group(3)
        old_count = int(m.group(4)) if m.group(4) else 1
        if typ is None:
            typ = old_typ
        if typ is None:
            # A block-valued field such as "Common": cannot set here.
            raise ValueError("field %s has no value type" % name)
        if count is None:
            count = old_count if isinstance(values, (list, tuple)) else 1
        if not isinstance(values, (list, tuple)):
            values = [values]
        if len(values) != count:
            raise ValueError("field %s expects %d values" % (name, count))
        indent = m.group(1)
        type_part = " %s" % typ
        if m.group(4) is not None:
            type_part += ":%d" % count
        text = "%s%s%s %s " % (indent, name, type_part, " ".join(format_value(typ, v) for v in values))
        self.replace_child(line, text)
        return text

    # ---------------------------------------------------------------- editing
    def replace_child(self, old, new):
        for i, c in enumerate(self.children):
            if c is old:
                self.children[i] = new
                if isinstance(new, Block):
                    new.parent = self
                return
        raise ValueError("child not found")

    def insert_child(self, index, node):
        self.children.insert(index, node)
        if isinstance(node, Block):
            node.parent = self

    def append_child(self, node):
        self.insert_child(len(self.children), node)

    def remove_child(self, node):
        self.children.remove(node)

    def make_block(self, name, indent=None, fields=None):
        """Create a new block with EWB formatting (trailing spaces)."""
        if indent is None:
            indent = self.indent + 2
        pad = " " * indent
        b = Block(pad + name + " ", pad + "{ ", [], pad + "}")
        b.parent = self
        for f in fields or []:
            b.append_child(f)
        return b

    def text(self):
        out = [self.header, self.open_line]
        for c in self.children:
            if isinstance(c, Block):
                out.extend(c.text().split(CRLF))
            else:
                out.append(c)
        out.append(self.close_line)
        return CRLF.join(out)


class Document:
    def __init__(self, root, tail=None):
        self.root = root
        self.tail = tail if tail is not None else []

    # ---------------------------------------------------------------- parsing
    @classmethod
    def parse(cls, data):
        if isinstance(data, bytes):
            text = data.decode("latin1")
        else:
            text = data
        if text.startswith("\ufeff"):
            text = text[1:]
        lines = text.split(CRLF)
        i = 0
        # tolerate leading blank lines
        while i < len(lines) and lines[i] == "":
            i += 1
        root, i = cls._parse_block(lines, i)
        return cls(root, lines[i:])

    @classmethod
    def _parse_block(cls, lines, i):
        if i + 1 >= len(lines) or lines[i + 1].strip() != "{":
            raise ValueError("expected block at line %d: %r" % (i, lines[i]))
        header = lines[i]
        open_line = lines[i + 1]
        i += 2
        children = []
        while True:
            if i >= len(lines):
                raise ValueError("unterminated block %r" % header.strip())
            s = lines[i].strip()
            if s == "}":
                close = lines[i]
                i += 1
                break
            if i + 1 < len(lines) and lines[i + 1].strip() == "{":
                child, i = cls._parse_block(lines, i)
                child.parent = None
                children.append(child)
            else:
                children.append(lines[i])
                i += 1
        b = Block(header, open_line, children, close)
        for c in children:
            if isinstance(c, Block):
                c.parent = b
        return b, i

    # ------------------------------------------------------------ serializing
    def text(self):
        parts = [self.root.text()]
        parts.extend(self.tail)
        return CRLF.join(parts)

    def to_bytes(self):
        return self.text().encode("latin1")

    # ---------------------------------------------------------------- helpers
    @property
    def circuit(self):
        return self.root.child("Circuit")

    @property
    def elements_block(self):
        c = self.circuit
        return c.child("Elements") if c else None

    @property
    def wires_block(self):
        c = self.circuit
        return c.child("Wires") if c else None

    def elements(self):
        from ewb_parts import Element
        eb = self.elements_block
        if eb is None:
            return []
        out = []
        idx = 0
        for c in eb.blocks():
            if c.name in ("Comp", "Instrument", "ExtComp"):
                out.append(Element(self, c, idx))
                idx += 1
        return out

    def wires(self):
        from ewb_parts import Wire
        wb = self.wires_block
        if wb is None:
            return []
        return [Wire(self, c, i) for i, c in enumerate(wb.blocks()) if c.name == "wire"]

    def find_element(self, key):
        els = self.elements()
        if isinstance(key, int):
            return els[key]
        found = [e for e in els if e.refid == key]
        if not found:
            raise KeyError(key)
        if len(found) > 1:
            raise KeyError("reference %r is ambiguous (%d elements); use an "
                           "element index instead" % (key, len(found)))
        return found[0]

    # ---------------------------------------------------------------- creation
    @classmethod
    def blank(cls):
        """Create an empty Project_5_1 document generated from the format spec."""
        from ewb_blank import blank_document_text
        return cls.parse(blank_document_text())


# ------------------------------------------------------------------- values
def parse_values(typ, count, raw):
    if typ == "A" or typ == "R":
        # quoted string, or several quoted strings; keep escapes verbatim
        vals = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
        if not vals:
            vals = [""]
        return vals if count != 1 else vals[0]
    if typ == "i":
        return [int(x) for x in raw.split()][:count]
    if typ == "r":
        try:
            return [float(x) for x in raw.split()][:count]
        except ValueError:
            return raw
    return raw


def format_value(typ, v):
    if typ in ("A", "R"):
        s = str(v)
        if not s.startswith('"'):
            s = '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return s
    if typ == "i":
        return str(int(v))
    if typ == "r":
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return ("%g" % float(v))
    return str(v)


def load(path):
    with open(path, "rb") as f:
        return Document.parse(f.read())


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.stderr.write("usage: python3 scripts/ewb_doc.py DOCUMENT.txt\n")
        raise SystemExit(2)
    with open(sys.argv[1], "rb") as f:
        raw = f.read()
    d = Document.parse(raw)
    out = d.to_bytes()
    exact = raw == out
    print("bytes %d -> %d, exact %s" % (len(raw), len(out), exact))
    if not exact:
        for i, (a, b) in enumerate(zip(raw, out)):
            if a != b:
                print("first diff at %d: %r != %r"
                      % (i, raw[max(0, i - 30):i + 30],
                         out[max(0, i - 30):i + 30]))
                break
    raise SystemExit(0 if exact else 1)
