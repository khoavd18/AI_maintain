from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

from evaluation.phase2_v2.allocation import _category_slots, _language_slots, _risk_slots
from evaluation.phase2_v2.assembly import build_dataset
from evaluation.phase2_v2.baseline import load_v1_cases
from evaluation.phase2_v2.build_dataset import build_dataset as facade_build_dataset
from evaluation.phase2_v2.case_factory import _build_cases, _build_evidence
from evaluation.phase2_v2.dataset_spec import CATEGORY_QUOTA, FAMILIES
from evaluation.phase2_v2.integrity import _write_checksums
from evaluation.validate_phase2_dataset import validate_dataset

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "evaluation" / "datasets" / "phase2_document_derived_v2"
V1 = ROOT / "evaluation" / "datasets" / "phase2_document_derived_v1"
SEMANTIC_CALIBRATION = ROOT / "evaluation" / "datasets" / "phase2_semantic_calibration_v1"

# These are the only paths written directly by assembly.build_dataset().
BUILDER_OWNED_ARTIFACTS = (
    "QA_REPORT.md",
    "README.md",
    "cases.jsonl",
    "checksums.sha256",
    "conversation_sequences.jsonl",
    "corpus_documents.csv",
    "evidence_spans.jsonl",
    "manifest.json",
    "retrieval_questions.jsonl",
    "review_queue.xlsx",
    "schema.json",
    "source_registry.jsonl",
)

# These reports are produced after the builder: the validator writes the first
# pair and evaluation.run_evaluation writes the second pair. Their timings are
# intentionally not reconstructed during builder-parity tests.
RUNTIME_REPORT_ARTIFACTS = (
    "deterministic_report.json",
    "deterministic_report.md",
    "validation_report.json",
    "validation_report.md",
)


def _build_package(workspace: Path) -> Path:
    """Build a temporary package without regenerating runtime-owned reports.

    The committed checksum manifest covers both builder and runtime artifacts.
    Copying the immutable tracked reports here before recomputing checksums lets
    the test prove the builder output without fabricating latency measurements.
    """

    dataset_dir = workspace / "evaluation" / "datasets" / "phase2_document_derived_v2"
    build_dataset(dataset_dir)
    assert {path.name for path in dataset_dir.iterdir()} == set(BUILDER_OWNED_ARTIFACTS)
    for name in RUNTIME_REPORT_ARTIFACTS:
        copyfile(COMMITTED / name, dataset_dir / name)
    _write_checksums(dataset_dir)
    return dataset_dir


def _hashes(directory: Path, artifacts: tuple[str, ...]) -> dict[str, str]:
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in artifacts}


def _assert_matches_head(path: Path) -> None:
    relative_path = path.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative_path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert path.read_bytes() == result.stdout


def _assert_path_is_unchanged_from_head(path: Path) -> None:
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", str(path.relative_to(ROOT))],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0


def _checksum_paths(dataset_dir: Path) -> set[str]:
    return {
        line.partition("  ")[2]
        for line in (dataset_dir / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    }


def _package_members(path: Path) -> list[tuple[str, bytes]]:
    with ZipFile(path) as archive:
        return [(member.filename, archive.read(member.filename)) for member in archive.infolist()]


def test_builder_facade_remains_public_and_cli_compatible() -> None:
    assert facade_build_dataset is build_dataset
    cli = subprocess.run(
        [sys.executable, "-m", "evaluation.phase2_v2.build_dataset", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Phase 2 v2 dataset builder" in cli.stdout


def test_allocation_preserves_exact_family_quotas_and_ordering() -> None:
    baseline = load_v1_cases()
    cases = _build_cases(baseline, _build_evidence())

    assert [case["case_id"] for case in cases] == [
        f"P2-{family.code}-{index:03d}" for family in FAMILIES for index in range(1, 101)
    ]
    for family in FAMILIES:
        family_cases = [case for case in cases if case["case_id"].startswith(f"P2-{family.code}-")]
        original = [case for case in baseline if case["case_id"].startswith(f"P2-{family.code}-")]
        assert Counter(case["primary_category"] for case in family_cases) == dict(CATEGORY_QUOTA)
        assert Counter(case["risk_level"] for case in family_cases) == {
            "critical": 15,
            "high": 25,
            "medium": 35,
            "low": 25,
        }
        assert Counter(case["language_variant"] for case in family_cases) == {
            "vi_diacritics": 60,
            "vi_no_diacritics": 15,
            "en": 15,
            "mixed_vi_en": 10,
        }
        assert _category_slots(family.code)[:10] == [
            case["primary_category"] for case in family_cases[:10]
        ]
        assert _risk_slots(original)[:10] == [case["risk_level"] for case in family_cases[:10]]
        assert _language_slots(original)[:10] == [
            case["language_variant"] for case in family_cases[:10]
        ]


def test_split_modules_have_one_builder_owner_and_no_internal_cycles() -> None:
    package_dir = ROOT / "evaluation" / "phase2_v2"
    modules = {path.stem: path for path in package_dir.glob("*.py")}
    dependency_graph: dict[str, set[str]] = {name: set() for name in modules}
    builder_owners: list[str] = []
    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_dataset"
            for node in ast.walk(tree)
        ):
            builder_owners.append(name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            prefix = "evaluation.phase2_v2."
            if node.module.startswith(prefix):
                dependency = node.module.removeprefix(prefix).split(".")[0]
                if dependency in modules:
                    dependency_graph[name].add(dependency)

    assert builder_owners == ["assembly"]
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(module: str) -> None:
        assert module not in visiting, f"internal import cycle includes {module}"
        if module in visited:
            return
        visiting.add(module)
        for dependency in dependency_graph[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in dependency_graph:
        visit(module)


def test_builder_artifacts_have_two_build_and_tracked_byte_parity(tmp_path: Path) -> None:
    first = _build_package(tmp_path / "first")
    second = _build_package(tmp_path / "second")

    assert _hashes(first, BUILDER_OWNED_ARTIFACTS) == _hashes(COMMITTED, BUILDER_OWNED_ARTIFACTS)
    assert _hashes(second, BUILDER_OWNED_ARTIFACTS) == _hashes(COMMITTED, BUILDER_OWNED_ARTIFACTS)
    for name in BUILDER_OWNED_ARTIFACTS:
        assert (first / name).read_bytes() == (second / name).read_bytes()

    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    committed_manifest = json.loads((COMMITTED / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["readiness"] == "DRAFT_SME_REVIEW_REQUIRED"
    assert manifest["counts"] == committed_manifest["counts"]
    assert manifest["quotas"] == committed_manifest["quotas"]
    assert manifest["files"] == committed_manifest["files"]
    assert manifest["limitations"] == committed_manifest["limitations"]


def test_workbook_canonicalization_preserves_deterministic_package_content(tmp_path: Path) -> None:
    first = _build_package(tmp_path / "first")
    second = _build_package(tmp_path / "second")
    workbook = "review_queue.xlsx"

    assert (first / workbook).read_bytes() == (second / workbook).read_bytes()
    assert (first / workbook).read_bytes() == (COMMITTED / workbook).read_bytes()
    assert _package_members(first / workbook) == _package_members(COMMITTED / workbook)


def test_runtime_reports_remain_immutable_and_validate_as_completed_package() -> None:
    for name in RUNTIME_REPORT_ARTIFACTS:
        _assert_matches_head(COMMITTED / name)

    manifest = json.loads((COMMITTED / "manifest.json").read_text(encoding="utf-8"))
    validation_report = json.loads(
        (COMMITTED / "validation_report.json").read_text(encoding="utf-8")
    )
    deterministic_report = json.loads(
        (COMMITTED / "deterministic_report.json").read_text(encoding="utf-8")
    )
    assert _checksum_paths(COMMITTED) == {
        *set(BUILDER_OWNED_ARTIFACTS),
        *set(RUNTIME_REPORT_ARTIFACTS),
    } - {"checksums.sha256"}
    assert validation_report["dataset_directory"] == COMMITTED.name
    assert validation_report["status"] == "PASS_WITH_WARNINGS"
    assert validation_report["error_count"] == 0
    assert validation_report["warning_count"] == 3
    assert deterministic_report["dataset_id"] == manifest["dataset_id"]
    assert deterministic_report["dataset_version"] == manifest["version"]
    assert deterministic_report["provenance_type"] == manifest["provenance_type"]
    assert deterministic_report["readiness"] == manifest["readiness"]
    assert deterministic_report["dataset_size"] == manifest["counts"]["cases"]
    assert deterministic_report["case_counts"]["manual_review_only"] == 3

    report = validate_dataset(COMMITTED)
    assert report["status"] == "PASS_WITH_WARNINGS"
    assert report["error_count"] == 0
    assert report["warning_count"] == 3


def test_protected_dataset_trees_bm25_and_sme_states_remain_unchanged() -> None:
    for dataset_tree in (V1, COMMITTED, SEMANTIC_CALIBRATION):
        _assert_path_is_unchanged_from_head(dataset_tree)
    _assert_path_is_unchanged_from_head(ROOT / "src" / "rag")

    v2_cases = [
        json.loads(line)
        for line in (COMMITTED / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {case["sme_review_status"] for case in v2_cases} == {"pending"}
    assert not any(case["promotion_eligible"] for case in v2_cases)
    assert {
        case["source_currentness_status"]
        for case in v2_cases
        if case["case_id"].startswith(("P2-PUMP-", "P2-GEN-"))
    } == {"VERSION_AMBIGUOUS"}
