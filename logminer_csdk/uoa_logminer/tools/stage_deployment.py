"""Create an ignored runtime-only SDK project; never prints configuration."""

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".deploy"


def stage() -> Path:
    TARGET.mkdir(mode=0o700, exist_ok=True)
    for path in ROOT.glob("*.py"):
        shutil.copy2(path, TARGET / path.name)
    for name in ("logminer", "schema_evolution"):
        shutil.copytree(
            ROOT / name,
            TARGET / name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    shutil.copy2(ROOT / "requirements.txt", TARGET / "requirements.txt")
    (TARGET / ".gitignore").write_text(
        "configuration.json\n.venv/\nfiles/\n__pycache__/\n"
    )
    config = ROOT / "configuration.json"
    if config.exists():
        shutil.copy2(config, TARGET / config.name)
        os.chmod(TARGET / config.name, 0o600)
    environment = TARGET / ".venv"
    if (ROOT / ".venv").exists() and not environment.exists():
        environment.symlink_to(ROOT / ".venv", target_is_directory=True)
    return TARGET


if __name__ == "__main__":
    print(f"Runtime-only SDK project: {stage()}")
