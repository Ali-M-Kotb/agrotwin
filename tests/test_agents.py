"""The coordination files exist and point at real paths.
(Idea from Yaseen Abdelal's tests/test_agents.py.)"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def test_board_files_exist():
    for f in ("AGENTS.md", "CONTINUE.md", "agents/README.md", "agents/STATUS.md",
              "agents/TASKS.md", "agents/DECISIONS.md", "agents/MESSAGES.md"):
        assert (ROOT / f).exists(), f

def test_ownership_map_paths_exist():
    text = (ROOT / "AGENTS.md").read_text()
    table = text.split("## 3. Ownership map")[1].split("## 4.")[0]
    paths = [p for p in re.findall(r"`([\w./*-]+)`", table) if not p.startswith("/") and "/" in p or p.endswith(".py")]
    missing = []
    for p in paths:
        if "*" in p:
            if not list(ROOT.glob(p)):
                missing.append(p)
            continue
        cands = [ROOT / p, ROOT / "backend" / p]
        if not any(c.exists() for c in cands):
            missing.append(p)
    assert not missing, missing

def test_version_matches_changelog_and_status():
    v = (ROOT / "VERSION").read_text().strip()
    assert f"## {v}" in (ROOT / "CHANGELOG.md").read_text()
    assert v in (ROOT / "agents" / "STATUS.md").read_text()
    assert v in (ROOT / "CONTINUE.md").read_text()
