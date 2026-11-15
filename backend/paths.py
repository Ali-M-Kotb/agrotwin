"""Where AgroTwin reads and writes its data folder.

Locally this is agrotwin/data. On Vercel the deployed code is read-only, so the
bundled data folder is mirrored into /tmp at start-up: small files are copied
(they may be rewritten), large caches are linked (they are only ever replaced
atomically). New downloads and sessions then live in /tmp for the life of the
server instance.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLED = ROOT / "data"
_SMALL = 1_000_000  # bytes

def _mirror(src: Path, dst: Path) -> None:
    for dirpath, _dirs, files in os.walk(src):
        rel = Path(dirpath).relative_to(src)
        out = dst / rel
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            s, t = Path(dirpath) / f, out / f
            if t.exists() or t.is_symlink():
                continue
            if s.stat().st_size < _SMALL:
                shutil.copy2(s, t)
            else:
                t.symlink_to(s)

if os.environ.get("VERCEL"):
    DATA = Path(os.environ.get("AGROTWIN_DATA_DIR", "/tmp/agrotwin-data"))
    _mirror(BUNDLED, DATA)
else:
    DATA = BUNDLED
