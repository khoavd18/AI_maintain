"""Deployment-topology tests grouped by topology dimension."""

# ruff: noqa: F811 - imported pytest fixture is named by test parameters

from __future__ import annotations

from ._topology_scenarios import (
    REQUIRED_VOLUME_PURPOSES,
    _finding,
    _ready_manifest,
    _topology_findings,
    _valid_port,
    deepcopy,
    isolate_downstream,  # noqa: F401 - registers the split-suite fixture
    pytest,
)


@pytest.mark.parametrize("ports", [None, {}, "ports", 1, True])
def test_non_list_ports_have_one_exact_collection_finding(
    isolate_downstream: None,
    ports: object,
) -> None:
    document = _ready_manifest()
    document["ports"] = ports

    assert _topology_findings(document) == [
        _finding("invalid_ports", "manifest.ports", "ports phải là list.")
    ]


def test_scalar_port_row_reports_index_without_hiding_valid_rows(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["ports"].insert(1, 42)

    assert _topology_findings(document) == [
        _finding(
            "list_entry_not_object",
            "manifest.ports.1",
            "Mỗi phần tử trong danh sách contract phải là JSON object.",
        )
    ]


def test_missing_port_name_uses_unknown_scope_for_later_valid_row(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    row = _valid_port("temporary")
    row.pop("name")
    document["ports"].append(row)

    assert _topology_findings(document) == [
        _finding(
            "port_name_missing",
            "manifest.ports",
            "Mỗi port phải có name.",
        )
    ]


def test_duplicate_port_name_and_host_collision_are_distinct_findings(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    duplicate = deepcopy(document["ports"][0])
    document["ports"].append(duplicate)
    name = duplicate["name"]

    assert _topology_findings(document) == [
        _finding(
            "duplicate_port",
            f"manifest.ports.{name}",
            "port bị khai báo trùng.",
        ),
        _finding(
            "duplicate_port",
            f"manifest.ports.{name}",
            "Hai service không được dùng trùng host port và protocol.",
        ),
    ]


def test_unknown_port_service_is_exact(isolate_downstream: None) -> None:
    document = _ready_manifest()
    document["ports"].append({**_valid_port("unknown-service"), "service": "missing"})

    assert _topology_findings(document) == [
        _finding(
            "port_service_unknown",
            "manifest.ports.unknown-service",
            "Port tham chiếu service không tồn tại.",
        )
    ]


@pytest.mark.parametrize("protocol", [None, "", "TCP", " tcp", 1, True])
def test_port_protocol_is_exact(
    isolate_downstream: None,
    protocol: object,
) -> None:
    document = _ready_manifest()
    document["ports"].append(_valid_port("protocol", protocol=protocol))

    assert _topology_findings(document) == [
        _finding(
            "invalid_port_protocol",
            "manifest.ports.protocol",
            "Port protocol phải là tcp hoặc udp.",
        )
    ]


@pytest.mark.parametrize("environment_name", [None, "", "lowercase", " PORT", "PORT ", 1, True])
def test_port_environment_names_are_strict(
    isolate_downstream: None,
    environment_name: object,
) -> None:
    document = _ready_manifest()
    row = _valid_port("environment")
    row["bind_address_environment"] = environment_name
    row["host_port_environment"] = environment_name
    document["ports"].append(row)

    assert _topology_findings(document) == [
        _finding(
            "port_environment_missing",
            "manifest.ports.environment.bind_address_environment",
            "Mỗi host port phải tham chiếu biến môi trường bind và port.",
        ),
        _finding(
            "port_environment_missing",
            "manifest.ports.environment.host_port_environment",
            "Mỗi host port phải tham chiếu biến môi trường bind và port.",
        ),
    ]


@pytest.mark.parametrize("port", [None, True, False, 0, 65536, 1.0, "8000"])
def test_host_port_requires_strict_integer_range(
    isolate_downstream: None,
    port: object,
) -> None:
    document = _ready_manifest()
    document["ports"].append(_valid_port("host-range", host_port=port))

    assert _topology_findings(document) == [
        _finding(
            "invalid_port",
            "manifest.ports.host-range.host_port",
            "Port phải là số nguyên trong khoảng 1..65535.",
        )
    ]


@pytest.mark.parametrize("port", [None, True, False, 0, 65536, 1.0, "8000"])
def test_container_port_requires_strict_integer_range(
    isolate_downstream: None,
    port: object,
) -> None:
    document = _ready_manifest()
    row = _valid_port("container-range")
    row["container_port"] = port
    document["ports"].append(row)

    assert _topology_findings(document) == [
        _finding(
            "invalid_port",
            "manifest.ports.container-range.container_port",
            "Port phải là số nguyên trong khoảng 1..65535.",
        )
    ]


@pytest.mark.parametrize("port", [1, 65535])
def test_port_boundaries_are_inclusive(
    isolate_downstream: None,
    port: int,
) -> None:
    document = _ready_manifest()
    document["ports"].append(_valid_port(f"boundary-{port}", host_port=port))

    assert _topology_findings(document) == []


def test_duplicate_host_port_is_scoped_by_protocol(isolate_downstream: None) -> None:
    document = _ready_manifest()
    first = document["ports"][0]
    document["ports"].append(
        _valid_port("same-host", host_port=first["host_port"], protocol=first["protocol"])
    )

    assert _topology_findings(document) == [
        _finding(
            "duplicate_port",
            "manifest.ports.same-host",
            "Hai service không được dùng trùng host port và protocol.",
        )
    ]


def test_same_host_port_with_other_protocol_is_accepted(isolate_downstream: None) -> None:
    document = _ready_manifest()
    first = document["ports"][0]
    other_protocol = "udp" if first["protocol"] == "tcp" else "tcp"
    document["ports"].append(
        _valid_port("other-protocol", host_port=first["host_port"], protocol=other_protocol)
    )

    assert _topology_findings(document) == []


def test_boolean_host_ports_still_participate_in_legacy_collision_tracking(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["ports"].extend(
        [_valid_port("bool-one", host_port=True), _valid_port("bool-two", host_port=True)]
    )

    assert _topology_findings(document) == [
        _finding(
            "invalid_port",
            "manifest.ports.bool-one.host_port",
            "Port phải là số nguyên trong khoảng 1..65535.",
        ),
        _finding(
            "invalid_port",
            "manifest.ports.bool-two.host_port",
            "Port phải là số nguyên trong khoảng 1..65535.",
        ),
        _finding(
            "duplicate_port",
            "manifest.ports.bool-two",
            "Hai service không được dùng trùng host port và protocol.",
        ),
    ]


@pytest.mark.parametrize("volumes", [None, {}, "volumes", 1, True])
def test_non_list_volumes_fail_closed_with_legacy_purpose_order(
    isolate_downstream: None,
    volumes: object,
) -> None:
    document = _ready_manifest()
    document["volumes"] = volumes

    assert _topology_findings(document) == [
        _finding("invalid_volumes", "manifest.volumes", "volumes phải là list."),
        *[
            _finding(
                "required_volume_missing",
                f"manifest.volumes.{purpose}",
                f"Thiếu persistent volume cho {purpose}.",
            )
            for purpose in REQUIRED_VOLUME_PURPOSES
        ],
    ]
