"""Static checks for the refactor's dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_canonical_rag_has_no_api_reverse_dependency() -> None:
    rag_root = Path(__file__).parents[1] / "src" / "rag"
    violations = {
        str(path): module
        for path in rag_root.rglob("*.py")
        for module in _imported_modules(path)
        if module == "src.api" or module.startswith("src.api.")
    }
    assert violations == {}


def test_api_composition_is_the_only_legacy_copilot_bridge() -> None:
    composition = Path(__file__).parents[1] / "src" / "api" / "composition.py"
    assert _imported_modules(composition) == {"src.application.copilot_factory"}
