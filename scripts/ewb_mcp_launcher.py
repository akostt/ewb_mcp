#!/usr/bin/env python3
"""Start the EWB MCP server with home-directory access enabled.

Some plugin hosts (Muse is the current example) do not expose an ``env`` map
for MCP servers in their manifest.  This tiny launcher keeps schematics in the
user's home directory reachable without changing the server's default policy
for clients that can pass environment variables themselves.
"""

import os
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

os.environ.setdefault("EWB_MCP_ALLOW_HOME", "1")
runpy.run_path(str(ROOT / "server.py"), run_name="__main__")
