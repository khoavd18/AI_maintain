from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BI_ROOT = ROOT / "data_platform" / "bi" / "powerbi"
PROJECT_ROOT = BI_ROOT / "MaintenanceAnalytics"
REPORT_ROOT = PROJECT_ROOT / "MaintenanceAnalytics.Report"


def test_powerbi_project_matches_deterministic_generator() -> None:
    completed = subprocess.run(
        [sys.executable, str(BI_ROOT / "build_project.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_powerbi_report_has_expected_pages_and_bound_visuals() -> None:
    pages_root = REPORT_ROOT / "definition" / "pages"
    pages = json.loads((pages_root / "pages.json").read_text(encoding="utf-8"))

    assert len(pages["pageOrder"]) == 3
    assert pages["activePageName"] == pages["pageOrder"][0]

    display_names: list[str] = []
    bound_visual_count = 0
    for page_name in pages["pageOrder"]:
        page_root = pages_root / page_name
        page = json.loads((page_root / "page.json").read_text(encoding="utf-8"))
        display_names.append(page["displayName"])
        for visual_path in (page_root / "visuals").glob("*/visual.json"):
            visual = json.loads(visual_path.read_text(encoding="utf-8"))["visual"]
            if visual.get("query", {}).get("queryState"):
                bound_visual_count += 1

    assert display_names == [
        "Tổng quan điều hành",
        "Độ tin cậy & khối lượng",
        "SLA & phụ tùng",
    ]
    assert bound_visual_count >= 20


def test_powerbi_project_contains_no_credentials_or_forbidden_scope() -> None:
    tracked_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in BI_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".tmdl", ".py", ".pbip", ".pbir", ".pbism"}
    ).lower()

    assert "maintenance_scale_local_only" not in tracked_text
    assert "password=" not in tracked_text
    assert '"password"' not in tracked_text
    assert "analytics_marts.maintenance_cost" not in tracked_text
    assert "frontend/src" not in tracked_text
