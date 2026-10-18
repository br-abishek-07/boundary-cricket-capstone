"""Allowlisted source downloads: no runtime state or real credentials."""

from pathlib import Path
import io, zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    "app.py",
    "match_data.py",
    "prediction.py",
    "README.md",
    "requirements.txt",
    "requirements-docs.txt",
    "start.bat",
    "start.sh",
    ".gitignore",
}
DIRECTORIES = {"boundary_core", "assets", "data", "docs", "tests", "tools"}
SUFFIXES = {
    ".py",
    ".json",
    ".csv",
    ".gz",
    ".md",
    ".pdf",
    ".docx",
    ".pptx",
    ".svg",
    ".txt",
    ".png",
}


def source_files():
    files = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink():
            continue
        if any(
            part.startswith(".") or part in {"__pycache__", "node_modules"}
            for part in rel.parts
        ):
            continue
        if str(rel) in ROOT_FILES or (
            rel.parts[0] in DIRECTORIES and path.suffix in SUFFIXES
        ):
            files.append(path)
    for name in (
        ".streamlit/config.toml",
        ".streamlit/secrets.example.toml",
        ".gitignore",
        ".python-version",
    ):
        path = ROOT / name
        if path.is_file() and not path.is_symlink():
            files.append(path)
    return sorted(set(files))


def source_signature():
    return tuple(
        (str(p.relative_to(ROOT)), p.stat().st_mtime_ns, p.stat().st_size)
        for p in source_files()
    )


def source_zip():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_files():
            archive.write(path, "boundary/" + str(path.relative_to(ROOT)))
    return out.getvalue()
