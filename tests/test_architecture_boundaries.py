"""Static checks for the refactor's dependency direction."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
RELIABILITY_ROOT = REPOSITORY_ROOT / "src" / "reliability"


def _module_name(path: Path, *, repository_root: Path = REPOSITORY_ROOT) -> str:
    relative = path.relative_to(repository_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _repository_module_names(repository_root: Path = REPOSITORY_ROOT) -> frozenset[str]:
    return frozenset(
        _module_name(path, repository_root=repository_root)
        for path in (repository_root / "src").rglob("*.py")
    )


REPOSITORY_MODULE_NAMES = _repository_module_names()


def _imported_modules(
    path: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    known_modules: frozenset[str] = REPOSITORY_MODULE_NAMES,
) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    source_module = _module_name(path, repository_root=repository_root)
    source_package = (
        source_module if path.name == "__init__.py" else source_module.rpartition(".")[0]
    )
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = source_package.split(".") if source_package else []
                parent_count = node.level - 1
                if not package_parts or parent_count >= len(package_parts):
                    continue
                base_parts = package_parts[: len(package_parts) - parent_count]
                import_base = ".".join(
                    (*base_parts, *((node.module or "").split(".") if node.module else ()))
                )
            else:
                import_base = node.module or ""

            if node.module and import_base:
                modules.add(import_base)
            for alias in node.names:
                candidate = ".".join(part for part in (import_base, alias.name) if part)
                if candidate in known_modules:
                    modules.add(candidate)
    return modules


HISTORICAL_RELIABILITY_FACADES = frozenset(
    {
        "src.reliability.drills",
        "src.reliability.load_harness",
        "src.reliability.post_start_validation",
        "src.reliability.profiles",
        "src.reliability.pilot_contract.environment",
        "src.reliability.pilot_contract.manifest",
        "src.reliability.pilot_contract.ownership",
        "src.reliability.pilot_contract.release",
        "src.reliability.pilot_contract.runtime",
    }
)

TRANSITIONAL_IMPLEMENTATION_FILES = (
    "artifact_io.py",
    "attachment_archives.py",
    "backup_artifacts.py",
    "disk_capacity.py",
    "drill_labels.py",
    "load_contracts.py",
    "load_metrics.py",
    "load_reporting.py",
    "load_safety.py",
    "load_telemetry.py",
    "post_start_preflight.py",
)

IMPLEMENTATION_PACKAGE_PATHS = (
    RELIABILITY_ROOT / "operator_drills",
    RELIABILITY_ROOT / "load",
    RELIABILITY_ROOT / "post_start",
    RELIABILITY_ROOT / "pilot_contract" / "deployment_manifest",
    RELIABILITY_ROOT / "pilot_contract" / "runtime_environment",
    RELIABILITY_ROOT / "pilot_contract" / "release_record",
    RELIABILITY_ROOT / "pilot_contract" / "runtime_policy",
    RELIABILITY_ROOT / "pilot_contract" / "operational_governance",
)

PROTECTED_REPOSITORY_AST_SHA256 = {
    "src/repositories/postgres_inventory.py": (
        "71ca7d16c572d9f15c1355a5ca89a2de0c24df0e9d7ae3f268e1d3775613e91f"
    ),
    "src/repositories/postgres_maintenance.py": (
        "85bbe06b4bb1231976e693d453de85a5456a2e9d13086f9b79c4edd49db13be4"
    ),
    "src/repositories/postgres_operations.py": (
        "c57aef33797d073d326f41863daad1100da4cf0c58ac876deb4660cce9683a65"
    ),
    "src/repositories/postgres_tickets.py": (
        "4b0bae4b97cb097b9fade45bd710699875ae1a129d7f164b46706e02ca73e28e"
    ),
}


def _implementation_paths(*, transitional: tuple[str, ...] = ()) -> tuple[Path, ...]:
    paths = [
        path
        for root in IMPLEMENTATION_PACKAGE_PATHS
        if root.exists()
        for path in root.rglob("*.py")
    ]
    paths.extend(
        RELIABILITY_ROOT / name for name in transitional if (RELIABILITY_ROOT / name).exists()
    )
    return tuple(sorted(paths))


def _dependency_graph(
    paths: tuple[Path, ...],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    known_modules: frozenset[str] = REPOSITORY_MODULE_NAMES,
) -> dict[str, set[str]]:
    modules = {_module_name(path, repository_root=repository_root) for path in paths}
    return {
        _module_name(path, repository_root=repository_root): {
            imported
            for imported in _imported_modules(
                path,
                repository_root=repository_root,
                known_modules=known_modules,
            )
            if imported in modules
        }
        for path in paths
    }


def _reliability_dependency_graph() -> dict[str, set[str]]:
    paths = _implementation_paths(transitional=TRANSITIONAL_IMPLEMENTATION_FILES)
    return _dependency_graph(paths)


def _reverse_facade_imports(
    paths: tuple[Path, ...],
    facades: frozenset[str],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    known_modules: frozenset[str] = REPOSITORY_MODULE_NAMES,
) -> dict[str, list[str]]:
    return {
        str(path.relative_to(repository_root)): sorted(imported_facades)
        for path in paths
        if (
            imported_facades := _imported_modules(
                path,
                repository_root=repository_root,
                known_modules=known_modules,
            ).intersection(facades)
        )
    }


def _cycle_from(graph: dict[str, set[str]]) -> tuple[str, ...] | None:
    visited: set[str] = set()
    active: list[str] = []

    def visit(module: str) -> tuple[str, ...] | None:
        if module in active:
            start = active.index(module)
            return tuple((*active[start:], module))
        if module in visited:
            return None
        visited.add(module)
        active.append(module)
        for dependency in sorted(graph[module]):
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        active.pop()
        return None

    for module in sorted(graph):
        cycle = visit(module)
        if cycle is not None:
            return cycle
    return None


def _write_synthetic_modules(tmp_path: Path, sources: dict[str, str]) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for module_name, source in sources.items():
        parts = module_name.split(".")
        for index in range(1, len(parts)):
            package_path = tmp_path.joinpath(*parts[:index], "__init__.py")
            package_path.parent.mkdir(parents=True, exist_ok=True)
            package_path.touch()
            paths.add(package_path)
        module_path = tmp_path.joinpath(*parts).with_suffix(".py")
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text(source, encoding="utf-8")
        paths.add(module_path)
    return tuple(sorted(paths))


def _synthetic_graph(tmp_path: Path, sources: dict[str, str]) -> dict[str, set[str]]:
    paths = _write_synthetic_modules(tmp_path, sources)
    known_modules = frozenset(_module_name(path, repository_root=tmp_path) for path in paths)
    return _dependency_graph(
        paths,
        repository_root=tmp_path,
        known_modules=known_modules,
    )


def test_relative_import_cycle_is_detected(tmp_path: Path) -> None:
    graph = _synthetic_graph(
        tmp_path,
        {
            "sample.alpha": "from . import beta\n",
            "sample.beta": "from . import alpha\n",
        },
    )

    cycle = _cycle_from(graph)
    assert cycle is not None
    assert set(cycle[:-1]) == {"sample.alpha", "sample.beta"}


def test_relative_parent_import_detects_historical_facade(tmp_path: Path) -> None:
    paths = _write_synthetic_modules(
        tmp_path,
        {
            "sample.runtime": "RUNTIME = True\n",
            "sample.implementation.worker": "from .. import runtime\n",
        },
    )
    known_modules = frozenset(_module_name(path, repository_root=tmp_path) for path in paths)

    assert _reverse_facade_imports(
        paths,
        frozenset({"sample.runtime"}),
        repository_root=tmp_path,
        known_modules=known_modules,
    ) == {str(Path("sample") / "implementation" / "worker.py"): ["sample.runtime"]}


def test_relative_sibling_import_adds_actual_module_edge(tmp_path: Path) -> None:
    graph = _synthetic_graph(
        tmp_path,
        {
            "sample.consumer": "from . import sibling\n",
            "sample.sibling": "VALUE = True\n",
        },
    )

    assert "sample.sibling" in graph["sample.consumer"]


def test_valid_acyclic_relative_import_has_no_false_positive(tmp_path: Path) -> None:
    graph = _synthetic_graph(
        tmp_path,
        {
            "sample.consumer": "from .provider import VALUE\n",
            "sample.provider": "VALUE = True\n",
        },
    )

    assert graph["sample.consumer"] == {"sample.provider"}
    assert _cycle_from(graph) is None


def test_absolute_import_still_adds_the_same_module_edge(tmp_path: Path) -> None:
    graph = _synthetic_graph(
        tmp_path,
        {
            "sample.consumer": "import sample.provider\n",
            "sample.provider": "VALUE = True\n",
        },
    )

    assert graph["sample.consumer"] == {"sample.provider"}


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


def test_maintenance_application_services_keep_outer_dependency_direction() -> None:
    application_root = Path(__file__).parents[1] / "src" / "maintenance_management" / "application"
    forbidden_prefixes = (
        "fastapi",
        "sqlalchemy",
        "src.api",
        "src.composition",
        "src.maintenance_management.service",
        "src.repositories.postgres",
    )
    violations = {
        str(path): module
        for path in application_root.glob("*.py")
        if path.name != "__init__.py"
        for module in _imported_modules(path)
        if module == "" or module.startswith(forbidden_prefixes)
    }
    assert violations == {}


def test_reliability_drill_capabilities_do_not_reverse_into_the_facade_or_application() -> None:
    capability_names = (
        "attachment_archives.py",
        "artifact_io.py",
        "backup_artifacts.py",
        "disk_capacity.py",
        "drill_labels.py",
    )
    paths = _implementation_paths(transitional=capability_names)
    forbidden_prefixes = (
        "fastapi",
        "httpx",
        "sqlalchemy",
        "src.api",
        "src.composition",
        "src.database",
        "src.repositories",
        "src.reliability.drills",
    )
    violations = {
        str(path.relative_to(REPOSITORY_ROOT)): module
        for path in paths
        if "operator_drills" in path.parts or path.name in capability_names
        for module in _imported_modules(path)
        if module.startswith(forbidden_prefixes)
    }
    assert violations == {}


def test_load_safety_capabilities_are_pure_and_do_not_reverse_into_the_harness() -> None:
    capability_names = (
        "load_contracts.py",
        "load_metrics.py",
        "load_reporting.py",
        "load_safety.py",
    )
    packaged_names = {"contracts.py", "metrics.py", "reporting.py", "safety.py"}
    paths = _implementation_paths(transitional=capability_names)
    forbidden_prefixes = (
        "fastapi",
        "httpx",
        "sqlalchemy",
        "src.api",
        "src.composition",
        "src.database",
        "src.repositories",
        "src.reliability.load_harness",
    )
    violations = {
        str(path.relative_to(REPOSITORY_ROOT)): module
        for path in paths
        if path.name in capability_names or ("load" in path.parts and path.name in packaged_names)
        for module in _imported_modules(path)
        if module.startswith(forbidden_prefixes)
    }
    assert violations == {}


def test_load_telemetry_depends_only_on_http_and_pure_load_capabilities() -> None:
    candidates = (
        RELIABILITY_ROOT / "load" / "telemetry.py",
        RELIABILITY_ROOT / "load_telemetry.py",
    )
    path = next(candidate for candidate in candidates if candidate.exists())
    forbidden_prefixes = (
        "fastapi",
        "sqlalchemy",
        "src.api",
        "src.composition",
        "src.database",
        "src.repositories",
        "src.reliability.load_harness",
    )
    violations = {
        module for module in _imported_modules(path) if module.startswith(forbidden_prefixes)
    }
    assert violations == set()


def test_post_start_preflight_has_no_network_or_runner_reverse_dependency() -> None:
    candidates = (
        RELIABILITY_ROOT / "post_start" / "preflight.py",
        RELIABILITY_ROOT / "post_start_preflight.py",
    )
    path = next(candidate for candidate in candidates if candidate.exists())
    forbidden_prefixes = (
        "fastapi",
        "httpx",
        "sqlalchemy",
        "src.api",
        "src.composition",
        "src.database",
        "src.repositories",
        "src.reliability.post_start_validation",
    )
    violations = {
        module for module in _imported_modules(path) if module.startswith(forbidden_prefixes)
    }
    assert violations == set()


def test_reliability_implementations_never_import_historical_facades() -> None:
    facades = HISTORICAL_RELIABILITY_FACADES
    if not (RELIABILITY_ROOT / "load" / "profiles.py").exists():
        # ``profiles.py`` is still the implementation owner at the pre-move checkpoint.
        facades = facades - {"src.reliability.profiles"}
    violations = _reverse_facade_imports(
        _implementation_paths(transitional=TRANSITIONAL_IMPLEMENTATION_FILES),
        facades,
    )
    assert violations == {}


def test_reliability_implementation_packages_are_acyclic() -> None:
    assert _cycle_from(_reliability_dependency_graph()) is None


def test_reliability_implementations_do_not_reverse_into_outer_application_layers() -> None:
    forbidden_prefixes = (
        "fastapi",
        "sqlalchemy",
        "src.api",
        "src.composition",
        "src.database",
        "src.repositories",
        "src.operations.worker",
    )
    violations = {
        str(path.relative_to(REPOSITORY_ROOT)): module
        for path in _implementation_paths(transitional=TRANSITIONAL_IMPLEMENTATION_FILES)
        for module in _imported_modules(path)
        if module.startswith(forbidden_prefixes)
    }
    assert violations == {}


def test_reliability_implementation_packages_have_capability_specific_names() -> None:
    prohibited_names = {
        "common.py",
        "factory.py",
        "helpers.py",
        "manager.py",
        "utils.py",
        "validators.py",
    }
    violations = sorted(
        str(path.relative_to(REPOSITORY_ROOT))
        for path in _implementation_paths()
        if path.name in prohibited_names
    )
    assert violations == []


def test_superseded_flat_reliability_implementation_owners_are_absent() -> None:
    assert [
        name for name in TRANSITIONAL_IMPLEMENTATION_FILES if (RELIABILITY_ROOT / name).exists()
    ] == []
    assert not (RELIABILITY_ROOT / "pilot_contract" / "support.py").exists()
    assert not (RELIABILITY_ROOT / "load" / "runner.py").exists()


def test_reliability_has_no_module_package_name_collisions() -> None:
    collisions = sorted(
        str(path.relative_to(REPOSITORY_ROOT))
        for path in RELIABILITY_ROOT.rglob("*.py")
        if path.name != "__init__.py" and path.with_suffix("").is_dir()
    )
    assert collisions == []


def test_protected_transaction_repository_executable_ast_is_unchanged() -> None:
    observed: dict[str, str] = {}
    for relative_path in PROTECTED_REPOSITORY_AST_SHA256:
        tree = ast.parse(
            (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"),
            filename=relative_path,
        )
        observed[relative_path] = hashlib.sha256(
            ast.dump(tree, annotate_fields=True, include_attributes=False).encode("utf-8")
        ).hexdigest()
    assert observed == PROTECTED_REPOSITORY_AST_SHA256
