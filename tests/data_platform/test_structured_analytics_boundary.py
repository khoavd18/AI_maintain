from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[2]
ADAPTER_PATH = REPOSITORY_ROOT / "src" / "analytics" / "maintenance_adapter.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_structured_adapter_has_no_rag_qdrant_llm_or_embedding_dependency() -> None:
    forbidden_prefixes = ("qdrant", "src.rag", "src.llm")
    imports = _imports(ADAPTER_PATH)

    assert {
        imported
        for imported in imports
        if imported.startswith(forbidden_prefixes) or "embedding" in imported
    } == set()


def test_rag_modules_do_not_depend_on_the_structured_aggregate_adapter() -> None:
    violations = {
        str(path.relative_to(REPOSITORY_ROOT)): imported
        for path in (REPOSITORY_ROOT / "src" / "rag").rglob("*.py")
        for imported in _imports(path)
        if imported == "src.analytics.maintenance_adapter"
        or imported.startswith("src.analytics.maintenance_adapter.")
    }

    assert violations == {}


def test_structured_adapter_queries_only_postgresql_analytics_relations() -> None:
    source = ADAPTER_PATH.read_text(encoding="utf-8").lower()

    assert "analytics_warehouse." in source
    assert "analytics_marts." in source
    assert "qdrant" not in source
    assert "vector_store" not in source
