"""Build a client archive from an explicit source/test/doc allowlist."""

import hashlib
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / ".dist"
NAME = "oracle-logminer-connector-client"


def package() -> Path:
    directory = OUTPUT / NAME
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    files = [*ROOT.glob("*.py")]
    files += [
        ROOT / name
        for name in (
            "README.md",
            ".gitignore",
            "pytest.ini",
            "configuration.example.json",
            "requirements.txt",
            "requirements-dev.txt",
        )
    ]
    for name in ("logminer", "schema_evolution", "tests", "tools"):
        files += list((ROOT / name).rglob("*.py"))
    files += list((ROOT / "docs").glob("*.md"))
    manifest = []
    for source in sorted(files):
        relative = source.relative_to(ROOT)
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest.append(
            f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {relative}"
        )
    (directory / "MANIFEST.sha256").write_text("\n".join(manifest) + "\n")
    archive = OUTPUT / (NAME + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                zipped.write(path, Path(NAME) / path.relative_to(directory))
    return archive


if __name__ == "__main__":
    print(package())
