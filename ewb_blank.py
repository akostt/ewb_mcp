"""Synthetic blank Project_5_1 documents.

The text below is written from the documented block/field layout and contains
no bytes copied from an application-generated blank file.  Only the blocks
that affect a new schematic immediately are emitted.  EWB fills the remaining
optional blocks (instrument settings, window geometry, analysis options) with
its own defaults when it opens or saves the file.
"""

CRLF = "\r\n"

# Formatting follows the Project_5_1 text tree: block headers and opening
# braces end in a space, field lines end in a space, closing braces do not.
_BLANK_LINES = [
    "Project_5_1 ",
    "{ ",
    "  CircuitHeader ",
    "  { ",
    "    InternalCircuitVersion i 511 ",
    "    ZoomFactor i 100 ",
    "    VersionSpecific ",
    "    { ",
    "      SerialNo R \"\" ",
    "      Version R \"Version 5.12\" ",
    "    }",
    "    Library ",
    "    { ",
    "      Name R \"$\" ",
    "    }",
    "    PrintSettings ",
    "    { ",
    "      Choices i:13 0 0 0 0 0 0 0 0 0 0 0 0 0 ",
    "      WkSpacePageBrk i 0 ",
    "      MacroPageBrk i 0 ",
    "      PrintZoom i 2000 ",
    "    }",
    "  }",
    "  Circuit ",
    "  { ",
    "    Preferences ",
    "    { ",
    "      Mode i 16 ",
    "      Info i:10 1 0 100 1 0 1 1 1 10485760 0 ",
    "      ShowNodes i 0 ",
    "      Fonts ",
    "      { ",
    "        Label ",
    "        { ",
    "          Name R \"Arial\" ",
    "          Size i -15 ",
    "          Type i 0 ",
    "          Color i 16711680 ",
    "        }",
    "        Model ",
    "        { ",
    "          Name R \"Arial\" ",
    "          Size i -15 ",
    "          Type i 0 ",
    "          Color i 16711680 ",
    "        }",
    "      }",
    "      Wiring ",
    "      { ",
    "        Manual i 0 ",
    "        Auto i 1 ",
    "        AutoModed i 0 ",
    "        Reroute i 1 ",
    "        Still i 0 ",
    "        AutoDelete i 1 ",
    "      }",
    "    }",
    "    Elements ",
    "    { ",
    "    }",
    "    Wires ",
    "    { ",
    "    }",
    "  }",
    "}",
]


def blank_document_text():
    """Return a minimal, valid Project_5_1 document with CRLF line endings."""
    return CRLF.join(_BLANK_LINES) + CRLF
