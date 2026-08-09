"""Authenticated live-stack smoke for the bounded graduation demo workflow."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import hmac
import os
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from sqlalchemy.engine.url import make_url


@dataclass
class AuthenticatedClient:
    """One in-memory authenticated session; tokens are never serialized."""

    username: str
    client: httpx.Client

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: int | tuple[int, ...] = 200,
        **kwargs: Any,
    ) -> Any:
        response = self.client.request(method, path, **kwargs)
        expected_values = (expected,) if isinstance(expected, int) else expected
        if response.status_code not in expected_values:
            detail = _safe_error_detail(response)
            raise RuntimeError(
                f"{self.username}: {method} {path} returned "
                f"{response.status_code}, expected {expected_values}: {detail}"
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


def run_smoke(
    *,
    base_url: str,
    frontend_url: str,
    database_url: str,
    password: str,
    asset_id: str = "GENERATOR_002",
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """Execute a real multi-role workflow against an attested `_test` API."""

    expected_fingerprint = _validate_test_database_url(database_url)
    _validate_loopback_url(base_url, "API")
    _validate_loopback_url(frontend_url, "frontend")
    run_id = uuid4().hex[:12]
    clients: list[AuthenticatedClient] = []
    anonymous = httpx.Client(base_url=base_url, timeout=timeout_seconds)
    try:
        health = _response_json(anonymous.get("/health/live"), expected=200)
        actual_fingerprint = health.get("test_database_fingerprint")
        if not isinstance(actual_fingerprint, str) or not hmac.compare_digest(
            actual_fingerprint, expected_fingerprint
        ):
            raise RuntimeError("API is not attested to the supplied `_test` database.")

        frontend_routes = _verify_frontend(frontend_url, timeout_seconds)
        for username in (
            "manager.demo",
            "engineer.demo",
            "technician.demo",
            "storekeeper.demo",
        ):
            clients.append(_login(base_url, username, password, timeout_seconds))
        sessions = {session.username: session for session in clients}
        manager = sessions["manager.demo"]
        engineer = sessions["engineer.demo"]
        technician = sessions["technician.demo"]
        storekeeper = sessions["storekeeper.demo"]

        catalog = manager.request("GET", "/assets/catalog", params={"page": 1, "page_size": 100})
        if asset_id not in {item.get("asset_id") for item in catalog.get("items", [])}:
            raise RuntimeError(f"Demo asset {asset_id} is missing from the live catalog.")
        profile = manager.request("GET", f"/assets/{asset_id}/profile")
        details = manager.request("GET", f"/assets/{asset_id}/details", params={"limit": 10})

        options = manager.request("GET", "/ticketing/options")
        technician_option = next(
            item for item in options["assignees"] if item.get("technician_id") == "TECH_002"
        )
        category = next(item for item in options["categories"] if item["code"] == "general")
        subcategory = next(
            item for item in options["subcategories"] if item.get("category_id") == category["id"]
        )
        intake_source = next(item for item in options["intake_sources"] if item["code"] == "web")
        support_group = next(
            item for item in options["support_groups"] if item["code"] == "ENGINEERING"
        )
        ticket = manager.request(
            "POST",
            "/tickets/intake",
            expected=201,
            json={
                "asset_id": asset_id,
                "issue_description": (
                    f"Runtime verification {run_id}: máy phát có điện áp không ổn định."
                ),
                "failure_category": "electrical_issue",
                "category_id": category["id"],
                "subcategory_id": subcategory["id"],
                "impact": "high",
                "urgency": "high",
                "intake_source_id": intake_source["id"],
                "support_group_id": support_group["id"],
                "assigned_user_id": technician_option["id"],
                "manager_note": f"Graduation runtime smoke {run_id}.",
            },
        )
        ticket_id = ticket["ticket_id"]
        ticket = technician.request(
            "POST",
            f"/tickets/{ticket_id}/acknowledge",
            json={"expected_version": ticket["version"]},
        )
        ticket = technician.request(
            "POST",
            f"/tickets/{ticket_id}/start",
            json={"expected_version": ticket["version"]},
        )

        grounded = manager.request(
            "POST",
            "/copilot/ask",
            json={
                "question": "Máy phát điện không khởi động thì cần kiểm tra những gì?",
                "asset_id": asset_id,
                "top_k": 5,
            },
        )
        _validate_grounded_copilot(grounded)
        mismatch = manager.request(
            "POST",
            "/copilot/ask",
            json={
                "question": "Máy bơm nước bị rung thì cần kiểm tra gì?",
                "asset_id": asset_id,
                "top_k": 5,
            },
        )
        if mismatch.get("retrieval_status") != "asset_context_mismatch":
            raise RuntimeError("Copilot did not reject the asset-type mismatch.")
        insufficient = manager.request(
            "POST",
            "/copilot/ask",
            json={
                "question": "Máy phát điện không khởi động thì cần kiểm tra gì?",
                "asset_id": asset_id,
                "failure_category": "cooling_issue",
                "top_k": 5,
            },
        )
        if insufficient.get("evidence_status") != "insufficient":
            raise RuntimeError("Copilot did not expose the insufficient-evidence state.")

        work_order = manager.request(
            "POST",
            f"/tickets/{ticket_id}/work-orders",
            expected=201,
            json={
                "title": f"Runtime verification {run_id}",
                "description": "Kiểm tra máy phát từ ticket runtime cô lập.",
                "assigned_to_user_id": technician_option["id"],
                "priority": "high",
                "due_date": (date.today() + timedelta(days=1)).isoformat(),
                "local_timezone": "Asia/Ho_Chi_Minh",
                "grace_period_days": 0,
                "estimated_duration_minutes": 60,
            },
        )
        work_order_id = work_order["id"]

        balances = storekeeper.request(
            "GET",
            "/inventory/balances",
            params={"search": "GEN-FILTER-FUEL", "page": 1, "page_size": 100},
        )
        balance = next(
            item
            for item in balances["items"]
            if item["part_number"] == "GEN-FILTER-FUEL" and item["stock_location_code"] == "MAIN"
        )
        requirement = engineer.request(
            "POST",
            f"/work-orders/{work_order_id}/part-requirements",
            expected=201,
            json={
                "part_id": balance["part_id"],
                "planned_quantity": 1,
                "required_by_date": (date.today() + timedelta(days=1)).isoformat(),
                "source_stock_location_id": balance["stock_location_id"],
                "notes": f"Runtime smoke {run_id}.",
            },
        )
        reservation = storekeeper.request(
            "POST",
            f"/work-order-part-requirements/{requirement['id']}/reservations",
            expected=201,
            headers={"Idempotency-Key": f"runtime-{run_id}-reserve"},
            json={
                "quantity": 1,
                "expected_requirement_version": requirement["version"],
                "reason": "Giữ phụ tùng cho runtime verification.",
            },
        )
        issue = storekeeper.request(
            "POST",
            f"/work-orders/{work_order_id}/part-issues",
            expected=201,
            headers={"Idempotency-Key": f"runtime-{run_id}-issue"},
            json={
                "part_id": balance["part_id"],
                "stock_location_id": balance["stock_location_id"],
                "quantity": 1,
                "requirement_id": requirement["id"],
                "reservation_id": reservation["id"],
                "issued_to_user_id": technician_option["id"],
                "reason": "Xuất phụ tùng cho runtime verification.",
            },
        )

        work_order = technician.request("GET", f"/work-orders/{work_order_id}")
        work_order = technician.request(
            "POST",
            f"/work-orders/{work_order_id}/transition",
            json={
                "target_status": "in_progress",
                "expected_version": work_order["version"],
            },
        )
        work_order = technician.request(
            "POST",
            f"/work-orders/{work_order_id}/complete",
            json={
                "expected_version": work_order["version"],
                "maintenance_date": date.today().isoformat(),
                "inspection_result": "Đã kiểm tra đầu nối và hệ thống khởi động.",
                "actions_taken": "Siết đầu nối và chạy thử có kiểm soát.",
                "parts_replaced": "Lọc nhiên liệu đã xuất riêng qua sổ kho.",
                "technician_note": "Không ghi nhận dấu hiệu mất an toàn sau chạy thử.",
                "maintenance_result": "resolved",
                "follow_up_required": False,
                "completion_summary": "Hoàn tất runtime verification có kiểm soát.",
                "safety_notes": "Đã tuân thủ cô lập năng lượng theo quy trình demo.",
                "labor_minutes": 30,
            },
        )
        work_order = manager.request(
            "POST",
            f"/work-orders/{work_order_id}/verify",
            json={"expected_version": work_order["version"]},
        )
        if work_order.get("status") != "verified":
            raise RuntimeError("Work order did not reach the verified state.")
        ticket_after = manager.request("GET", f"/tickets/{ticket_id}")
        if ticket_after.get("status") != "in_progress":
            raise RuntimeError("Work-order verification changed the ticket implicitly.")

        audits = manager.request(
            "GET",
            "/audit-logs",
            params={"action": "work_order.verified", "page": 1, "page_size": 100},
        )
        if not audits.get("items"):
            raise RuntimeError("Verified work-order audit evidence is missing.")
        metrics = manager.request(
            "GET",
            "/work-orders/metrics",
            params={"as_of_date": date.today().isoformat()},
        )
        worker = manager.request("GET", "/health/worker")
        if not worker.get("ready"):
            raise RuntimeError("Background worker is not ready after the workflow.")

        return {
            "status": "passed",
            "run_id": run_id,
            "frontend_routes": frontend_routes,
            "asset": {
                "asset_id": asset_id,
                "profile_loaded": profile.get("asset_id") == asset_id,
                "risk_rows": len(details.get("risk_history", [])),
                "anomaly_rows": len(details.get("recent_anomalies", [])),
            },
            "ticket": {"ticket_id": ticket_id, "status": ticket_after["status"]},
            "copilot": {
                "response_mode": grounded["response_mode"],
                "provider": grounded["llm_provider"],
                "model": grounded["llm_model"],
                "source_aliases": sorted(
                    {
                        chunk["citation_id"]
                        for chunk in grounded["retrieved_chunks"]
                        if chunk.get("citation_id")
                    }
                ),
                "mismatch_status": mismatch["retrieval_status"],
                "insufficient_status": insufficient["retrieval_status"],
            },
            "inventory": {
                "requirement_id": requirement["id"],
                "reservation_id": reservation["id"],
                "issue_id": issue["id"],
            },
            "work_order": {
                "id": work_order_id,
                "number": work_order["work_order_number"],
                "status": work_order["status"],
            },
            "audit_count": audits["total"],
            "metrics_verified": metrics.get("verified", metrics.get("verified_count")),
            "worker_status": worker.get("status"),
        }
    finally:
        anonymous.close()
        for session in clients:
            session.client.close()


def _login(
    base_url: str, username: str, password: str, timeout_seconds: float
) -> AuthenticatedClient:
    client = httpx.Client(base_url=base_url, timeout=timeout_seconds)
    response = client.post("/auth/login", json={"identifier": username, "password": password})
    payload = _response_json(response, expected=200)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        client.close()
        raise RuntimeError(f"Login for {username} did not return an access token.")
    client.headers["Authorization"] = f"Bearer {token}"
    return AuthenticatedClient(username=username, client=client)


def _validate_grounded_copilot(payload: dict[str, Any]) -> None:
    if payload.get("response_mode") != "llm_grounded":
        raise RuntimeError(
            f"Copilot did not return a grounded LLM answer: {payload.get('fallback_reason')}"
        )
    validation = payload.get("citation_validation") or {}
    if validation.get("valid") is not True or validation.get("invalid_source_ids"):
        raise RuntimeError("Copilot citation validation did not pass.")
    aliases = {
        chunk.get("citation_id")
        for chunk in payload.get("retrieved_chunks", [])
        if chunk.get("citation_id")
    }
    displayed = {
        citation_id
        for source in payload.get("sources", [])
        for citation_id in source.get("citation_ids", [])
    }
    structured = payload.get("structured_answer") or {}
    structured_ids = set(structured.get("source_ids", []))
    if not aliases or not displayed.issubset(aliases) or not structured_ids.issubset(aliases):
        raise RuntimeError("Copilot source aliases do not map to this response's chunks.")
    if not payload.get("safety_notice"):
        raise RuntimeError("Copilot safety notice is missing.")


def _verify_frontend(frontend_url: str, timeout_seconds: float) -> list[str]:
    routes = ["/login", "/copilot"]
    with httpx.Client(base_url=frontend_url, timeout=timeout_seconds) as client:
        for route in routes:
            response = client.get(route)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Frontend route {route} returned {response.status_code}, expected 200."
                )
    return routes


def _validate_test_database_url(database_url: str) -> str:
    try:
        parsed = make_url(database_url)
    except Exception as exc:  # noqa: BLE001 - never render credential-bearing URLs
        raise ValueError("A valid PostgreSQL test database URL is required.") from exc
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("Test database URL must use postgresql+psycopg://.")
    database_name = parsed.database or ""
    if not database_name.endswith("_test"):
        raise ValueError("Graduation smoke database name must end with _test.")
    return hashlib.sha256(f"pm9-test-database:{database_name}".encode("utf-8")).hexdigest()


def _validate_loopback_url(value: str, label: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError(f"{label} URL must be an explicit loopback HTTP(S) target.")


def _response_json(response: httpx.Response, *, expected: int) -> dict[str, Any]:
    if response.status_code != expected:
        raise RuntimeError(
            f"HTTP request returned {response.status_code}, expected {expected}: "
            f"{_safe_error_detail(response)}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("HTTP response did not contain a JSON object.")
    return payload


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "non-JSON response"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return str(detail)[:300] if detail is not None else "unexpected response"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://127.0.0.1:3000")
    parser.add_argument("--asset-id", default="GENERATOR_002")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    database_url = os.getenv("TEST_DATABASE_URL", "")
    password = os.getenv("DEMO_USER_PASSWORD", "")
    if not database_url or not password:
        raise SystemExit("TEST_DATABASE_URL and DEMO_USER_PASSWORD are required.")
    report = run_smoke(
        base_url=args.base_url,
        frontend_url=args.frontend_url,
        database_url=database_url,
        password=password,
        asset_id=args.asset_id,
        timeout_seconds=args.timeout_seconds,
    )
    import json

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
