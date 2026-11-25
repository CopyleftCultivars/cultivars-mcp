"""Release guard: the tag, pyproject.toml and server.json must name one version.

Usage: python scripts/release_check.py v0.2.0 [--notes OUT]

With --notes, writes the CHANGELOG section headed "## [0.2.0]" to OUT and fails
if there is no such section, so a release never goes out without notes.
"""
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv):
    tag = argv[1]
    version = tag.removeprefix("v")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    server = json.loads((ROOT / "server.json").read_text())
    found = {
        "tag": version,
        "pyproject.toml": pyproject,
        "server.json version": server["version"],
        "server.json package version": server["packages"][0]["version"],
    }
    if len(set(found.values())) != 1:
        for where, v in found.items():
            print(f"{where}: {v}")
        sys.exit("Versions differ. Bump pyproject.toml and both server.json fields to match the tag.")
    print(f"Version {version} matches in the tag, pyproject.toml and server.json.")

    if "--notes" in argv:
        out = Path(argv[argv.index("--notes") + 1])
        text = (ROOT / "CHANGELOG.md").read_text()
        m = re.search(rf"^## \[{re.escape(version)}\].*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
        if not m or not m.group(1).strip():
            sys.exit(f"CHANGELOG.md has no '## [{version}]' section.")
        out.write_text(m.group(1).strip() + "\n")
        print(f"Release notes written to {out} ({len(m.group(1).strip())} characters).")


if __name__ == "__main__":
    main(sys.argv)
