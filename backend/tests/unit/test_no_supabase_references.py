from pathlib import Path

_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".uv-cache-task4",
    ".uv-cache-task5",
    ".uv-cache-task6",
    "dist",
    "build",
    ".vs",
    "graphify-out",
    "output",
    ".superpowers",
    "coverage",
    ".docs",
    ".planning",
}
_SKIP_FILES = {
    "package-lock.json",
    "uv.lock",
    "0002-supabase-postgres-system-of-record.md",
}
_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".env",
    ".example",
    ".sh",
    ".txt",
    ".html",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _candidate_files():
    for path in _repo_root().rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.name in _SKIP_FILES or path.name == Path(__file__).name:
            continue
        if path.suffix.lower() in _TEXT_SUFFIXES:
            yield path


def test_repository_contains_no_supabase_reference() -> None:
    """Phase 2B removes Supabase. This test keeps it removed.

    A stray reference means either dead code or, worse, a live credential
    surface for a service the product no longer uses.
    """
    offenders = []
    for path in _candidate_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "supabase" in text.lower():
            offenders.append(str(path.relative_to(_repo_root())))

    assert offenders == [], f"Supabase references remain in: {offenders}"
