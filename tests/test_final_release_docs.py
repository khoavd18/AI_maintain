from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "release-manifest.json"
RELEASE_MARKDOWN = (
    ROOT / "README.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "demo-runbook.md",
    ROOT / "docs" / "operations-runbook.md",
    ROOT / "docs" / "portfolio" / "project-summary.md",
    ROOT / "docs" / "portfolio" / "cv-bullets.md",
    ROOT / "docs" / "portfolio" / "interview-guide.md",
    ROOT / "docs" / "project-handover.md",
    ROOT / "docs" / "final-release-checklist.md",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_required_release_package_exists() -> None:
    required = (*RELEASE_MARKDOWN, MANIFEST_PATH, ROOT / "scripts" / "verify_final_release.ps1")
    assert all(path.is_file() for path in required)


def test_release_manifest_matches_machine_evidence() -> None:
    release = _json(MANIFEST_PATH)
    stage9 = _json(ROOT / "docs" / "benchmark-results-1m.json")
    stage10 = _json(ROOT / "docs" / "benchmark-results-domain-scale.json")
    stage10_manifest = _json(ROOT / "docs" / "benchmark-manifest-domain-scale.json")
    stage11 = _json(ROOT / "docs" / "benchmark-results-api-stage11.json")

    assert release["stage"] == 12
    assert release["base_commit"] == "33ac82efbe5f37ed07d412ba2554fd94bde0b6f3"
    assert release["dataset"]["stage9"]["unique_work_orders"] == stage9["counts"][
        "source_work_orders"
    ]
    assert release["dataset"]["stage9"]["raw_work_order_versions"] == stage9[
        "counts"
    ]["raw_work_order_versions"]
    assert release["dataset"]["stage10"]["domains"] == stage10["counts"]
    assert release["dataset"]["stage10"]["generated_chunks"] == (
        stage10_manifest["baseline"]["file_count"]
        + stage10_manifest["incremental"]["file_count"]
    )
    assert release["dataset"]["stage10"]["generated_and_copied_rows"] == (
        stage10_manifest["baseline"]["copy_result"]["rows"]
        + stage10_manifest["incremental"]["copy_result"]["rows"]
    )
    final_50 = next(row for row in stage11["median_comparison"] if row["clients"] == 50)
    assert release["performance"]["stage11_api"]["clients_50"]["final_rps"] == final_50[
        "final"
    ]["requests_per_second"]
    assert release["performance"]["stage11_api"]["clients_50"]["final_p95_ms"] == (
        final_50["final"]["p95_ms"]
    )


def test_manifest_evidence_and_protected_exclusions_are_explicit() -> None:
    release = _json(MANIFEST_PATH)
    for path in release["evidence_documents"].values():
        assert (ROOT / path).exists(), path

    exclusions = release["protected_file_exclusions"]
    assert [entry["path"] for entry in exclusions] == [
        "src/llm/prompt_builder.py",
        "tests/test_grounded_generation_repair.py",
    ]
    assert all(entry["included_in_stage9_to_stage12_lineage"] is False for entry in exclusions)
    assert "stage12_commit" not in release


def test_canonical_documents_share_required_metrics_and_caveat() -> None:
    canonical = (
        ROOT / "README.md",
        ROOT / "docs" / "portfolio" / "project-summary.md",
        ROOT / "docs" / "project-handover.md",
    )
    for path in canonical:
        text = path.read_text(encoding="utf-8")
        for token in ("7,728,467", "1,100,000", "459/459", "2,052", "774/774", "33 to 23"):
            assert token in text, (path, token)
        assert "synthetic" in text.lower()
        assert "production" in text.lower()


def test_release_markdown_links_and_fences_are_valid() -> None:
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for path in RELEASE_MARKDOWN:
        text = path.read_text(encoding="utf-8")
        assert sum(line.startswith("```") for line in text.splitlines()) % 2 == 0, path
        for target in link_pattern.findall(text):
            target = target.strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = target.split("#", 1)[0]
            if relative:
                assert (path.parent / relative).exists(), (path, target)


def test_verifier_is_offline_first_and_has_no_mutating_commands() -> None:
    script = (ROOT / "scripts" / "verify_final_release.ps1").read_text(encoding="utf-8")
    assert '[string]$Mode = "Offline"' in script
    assert 'ValidateSet("Offline", "LocalReadOnly", "ScaleReadOnly")' in script
    assert "$RequireCleanCommit" in script
    assert "SUMMARY PASS=" in script
    assert not re.search(r"(?im)^\s*(?:&\s*)?docker\s+(?:compose\s+)?(?:up|start|stop|down|rm|prune)\b", script)
    assert not re.search(r"(?im)^\s*(?:&\s*)?aws\b", script)
    assert "generate_scale_data" not in script
    assert "generate_domain_scale_data" not in script
    assert "data_platform.api_benchmark" not in script


def test_no_generated_scale_or_runtime_artifacts_are_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden = (
        "data/scale/",
        ".venv/",
        ".pytest_cache/",
        ".ruff_cache/",
        "data_platform/dbt/maintenance_analytics/target/",
        "data_platform/dbt/maintenance_analytics/logs/",
    )
    assert not [path for path in tracked if path.startswith(forbidden)]
