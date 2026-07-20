from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_no_template_identifiers_remain():
    stale = ("lab_backend_template", "lab-backend-template", "ECHO::")
    for path in ROOT.rglob("*"):
        if (
            path.is_file()
            and path.suffix in {".py", ".toml", ".yaml", ".yml", ".md"}
            and ".git" not in path.parts
            and path.resolve() != Path(__file__).resolve()
        ):
            text = path.read_text("utf-8")
            assert not any(item in text for item in stale), path


def test_repository_text_files_use_lf_only():
    for path in ROOT.rglob("*"):
        if (
            path.is_file()
            and path.suffix in {".py", ".toml", ".yaml", ".yml", ".md", ".txt"}
            and not {
                ".git",
                "dist",
                "build",
                ".pytest_cache",
                ".ruff_cache",
            }.intersection(path.parts)
        ):
            assert b"\r\n" not in path.read_bytes(), path


def test_template_document_was_removed_and_safety_design_kept():
    assert not (ROOT / "docs" / "USING_THIS_TEMPLATE.md").exists()
    assert (ROOT / "docs" / "SAFETY_DESIGN.md").is_file()
