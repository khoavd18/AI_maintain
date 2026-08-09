"""Keep repository-local Markdown links valid."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_local_documentation_links_resolve() -> None:
    documents = [ROOT / "README.md", ROOT / "frontend" / "README.md"]
    documents.extend(sorted((ROOT / "docs").glob("*.md")))
    broken: list[str] = []

    for document in documents:
        content = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(content):
            target = raw_target.strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative_path = target.split("#", maxsplit=1)[0]
            if not relative_path:
                continue
            resolved = (document.parent / relative_path).resolve()
            if not resolved.exists():
                broken.append(f"{document.relative_to(ROOT)} -> {target}")

    assert not broken, "Broken documentation links:\n" + "\n".join(broken)
