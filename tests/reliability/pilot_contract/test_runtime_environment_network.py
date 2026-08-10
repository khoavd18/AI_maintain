"""Runtime-environment tests grouped by validation capability."""

from __future__ import annotations

from ._runtime_environment_scenarios import (
    _finding,
    _findings,
    _only,
    _ready_environment,
    pytest,
)


@pytest.mark.parametrize(
    "origins",
    [
        "http://pilot.example",
        "https://user:pass@pilot.example",
        "https://pilot.example/path",
        "not-a-url",
    ],
)
def test_cors_origins_require_safe_https_origins(origins: str) -> None:
    environment = _ready_environment()
    environment["CORS_ALLOWED_ORIGINS"] = origins

    assert _only(_findings(environment=environment)[1], {"pilot_cors_origin_invalid"}) == [
        _finding(
            "pilot_cors_origin_invalid",
            "environment.CORS_ALLOWED_ORIGINS",
            "Mỗi pilot CORS origin phải là HTTPS origin không chứa credential.",
        )
    ]


@pytest.mark.parametrize("name", ["FRONTEND_BASE_URL", "NEXT_PUBLIC_API_BASE_URL", "QDRANT_URL"])
def test_service_urls_reject_paths_queries_fragments_and_credentials(name: str) -> None:
    environment = _ready_environment()
    environment[name] = "https://user:password@pilot.example/path?query=1#fragment"

    assert _only(_findings(environment=environment)[1], {"service_url_invalid"}) == [
        _finding(
            "service_url_invalid",
            f"environment.{name}",
            f"{name} phải là http(s) URL không chứa credential.",
        )
    ]


def test_frontend_local_http_accumulates_development_and_tls_findings() -> None:
    environment = _ready_environment()
    environment["FRONTEND_BASE_URL"] = "http://localhost:3000"

    assert _only(
        _findings(environment=environment)[1],
        {"development_network_default", "pilot_tls_origin_required"},
    )[-2:] == [
        _finding(
            "development_network_default",
            "environment.FRONTEND_BASE_URL",
            "FRONTEND_BASE_URL vẫn dùng development host.",
        ),
        _finding(
            "pilot_tls_origin_required",
            "environment.FRONTEND_BASE_URL",
            "FRONTEND_BASE_URL phải dùng HTTPS cho pilot.",
        ),
    ]


def test_qdrant_allows_http_but_must_match_internal_manifest_url() -> None:
    environment = _ready_environment()
    environment["QDRANT_URL"] = "http://localhost:6333"

    assert _only(_findings(environment=environment)[1], {"qdrant_internal_url_mismatch"}) == [
        _finding(
            "qdrant_internal_url_mismatch",
            "environment.QDRANT_URL",
            "QDRANT_URL phải dùng địa chỉ service nội bộ đã khai báo.",
        )
    ]
