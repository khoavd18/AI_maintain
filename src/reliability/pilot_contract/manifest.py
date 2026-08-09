"""Manifest structure and deployment-contract validation."""

from __future__ import annotations

import json
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from src.release import APPLICATION_VERSION, CANONICAL_SCHEMA_REVISION

from .constants import (
    SUPPORTED_JOBS,
    REQUIRED_SERVICES,
    REQUIRED_PILOT_ENVIRONMENT,
    SECRET_ENVIRONMENT_NAMES,
    _EXACT_TAG_TARGET_COMMIT_RESOLUTION,
    _ENV_NAME_RE,
    _COMPOSE_REQUIRED_ENV_RE,
)

from .runtime import _validate_runtime_settings
from .schemas import Finding
from .support import (
    _safe_relative_path,
    _safe_container_path,
    _non_placeholder_text,
    _versioned,
    _mapping,
    _list_of_mappings,
    _require_keys,
    _check_unique_names,
    _add,
)


def _validate_manifest_structure(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    _require_keys(
        document,
        {
            "schema_version",
            "manifest_kind",
            "compose_file",
            "release",
            "versions",
            "images",
            "services",
            "ports",
            "volumes",
            "storage",
            "required_environment_variables",
            "health_endpoints",
            "scheduled_jobs",
            "worker",
            "retry_and_dead_letter",
            "operational_alerts",
            "database",
            "restore_prerequisites",
            "rollback",
            "production_readiness_claim",
        },
        "manifest",
        findings,
    )
    if not _versioned(document):
        _add(
            findings,
            "invalid_schema_version",
            "manifest",
            "Deployment manifest phải có schema_version rõ ràng.",
        )
    if document.get("manifest_kind") != "ai_maintenance_copilot_internal_pilot":
        _add(
            findings,
            "invalid_manifest_kind",
            "manifest",
            "Deployment manifest không đúng loại internal pilot.",
        )
    if document.get("production_readiness_claim") is not False:
        _add(
            findings,
            "production_readiness_claim_forbidden",
            "manifest",
            "Contract internal pilot không được tuyên bố production readiness.",
        )

    release = _mapping(document.get("release"))
    _require_keys(
        release,
        {
            "release_id",
            "commit_resolution",
            "tag_recommendation",
            "tag_status",
            "alembic_revision",
        },
        "manifest.release",
        findings,
    )
    commit_resolution = release.get("commit_resolution")
    if commit_resolution != _EXACT_TAG_TARGET_COMMIT_RESOLUTION:
        code = "invalid_commit_resolution"
        _add(
            findings,
            code,
            "manifest.release.commit_resolution",
            "Release commit phải được resolve từ exact Git tag target.",
        )
    if release.get("tag_status") not in {"checkpointed", "verified"}:
        _add(
            findings,
            "release_tag_pending",
            "manifest.release",
            "Git tag recommendation chưa được xác nhận tại checkpoint.",
        )
    for key in ("release_id", "tag_recommendation", "alembic_revision"):
        if not _non_placeholder_text(release.get(key)):
            _add(
                findings,
                "missing_release_identity",
                f"manifest.release.{key}",
                "Release identity còn thiếu hoặc đang là placeholder.",
            )

    versions = _mapping(document.get("versions"))
    required_versions = {
        "application",
        "frontend",
        "python",
        "node",
        "postgresql",
        "qdrant",
    }
    _require_keys(versions, required_versions, "manifest.versions", findings)
    for name in required_versions:
        if not _non_placeholder_text(versions.get(name)):
            _add(
                findings,
                "missing_component_version",
                f"manifest.versions.{name}",
                "Mọi runtime bắt buộc phải có version không phải placeholder.",
            )

    images = _mapping(document.get("images"))
    required_images = {
        "application",
        "frontend",
        "python_base",
        "node_base",
        "postgresql",
        "qdrant",
    }
    _require_keys(images, required_images, "manifest.images", findings)
    for name in required_images:
        value = images.get(name)
        invalid_digest = (
            isinstance(value, str)
            and "@sha256:" in value
            and len(value.rsplit("@sha256:", 1)[1]) != 64
        )
        if not _non_placeholder_text(value) or str(value).endswith(":latest") or invalid_digest:
            _add(
                findings,
                "invalid_image_reference",
                f"manifest.images.{name}",
                "Image reference phải rõ ràng và không được dùng thẻ latest.",
            )

    services = _list_of_mappings(
        document.get("services"),
        findings=findings,
        scope="manifest.services",
    )
    if not isinstance(document.get("services"), list):
        _add(findings, "invalid_services", "manifest.services", "services phải là list.")
    service_names = _check_unique_names(services, "name", "service", findings)
    missing_services = REQUIRED_SERVICES - service_names
    unsupported_services = service_names - REQUIRED_SERVICES
    for name in sorted(missing_services):
        _add(
            findings,
            "required_service_missing",
            f"manifest.services.{name}",
            f"Thiếu service bắt buộc: {name}.",
        )
    for name in sorted(unsupported_services):
        _add(
            findings,
            "unsupported_service",
            f"manifest.services.{name}",
            f"Service ngoài contract PM9: {name}.",
        )
    for service in services:
        name = service.get("name")
        if service.get("required") is not True:
            _add(
                findings,
                "service_not_required",
                f"manifest.services.{name}",
                "Mỗi service trong closed pilot topology phải được đánh dấu required=true.",
            )
        version_ref = service.get("version_ref")
        if version_ref not in versions:
            _add(
                findings,
                "service_version_reference_invalid",
                f"manifest.services.{name}",
                "Service phải tham chiếu component version đã khai báo.",
            )

    ports = _list_of_mappings(
        document.get("ports"),
        findings=findings,
        scope="manifest.ports",
    )
    if not isinstance(document.get("ports"), list):
        _add(findings, "invalid_ports", "manifest.ports", "ports phải là list.")
    _check_unique_names(ports, "name", "port", findings)
    occupied: dict[tuple[str, int], str] = {}
    for port in ports:
        name = str(port.get("name", "unknown"))
        service = port.get("service")
        protocol = port.get("protocol")
        host_port = port.get("host_port")
        container_port = port.get("container_port")
        if service not in service_names:
            _add(
                findings,
                "port_service_unknown",
                f"manifest.ports.{name}",
                "Port tham chiếu service không tồn tại.",
            )
        if protocol not in {"tcp", "udp"}:
            _add(
                findings,
                "invalid_port_protocol",
                f"manifest.ports.{name}",
                "Port protocol phải là tcp hoặc udp.",
            )
        for field in ("bind_address_environment", "host_port_environment"):
            environment_name = port.get(field)
            if not isinstance(environment_name, str) or not _ENV_NAME_RE.fullmatch(
                environment_name
            ):
                _add(
                    findings,
                    "port_environment_missing",
                    f"manifest.ports.{name}.{field}",
                    "Mỗi host port phải tham chiếu biến môi trường bind và port.",
                )
        for field, value in (("host_port", host_port), ("container_port", container_port)):
            if type(value) is not int or not 1 <= value <= 65535:
                _add(
                    findings,
                    "invalid_port",
                    f"manifest.ports.{name}.{field}",
                    "Port phải là số nguyên trong khoảng 1..65535.",
                )
        if isinstance(host_port, int) and isinstance(protocol, str):
            key = (protocol, host_port)
            if key in occupied:
                _add(
                    findings,
                    "duplicate_port",
                    f"manifest.ports.{name}",
                    "Hai service không được dùng trùng host port và protocol.",
                )
            else:
                occupied[key] = name

    volumes = _list_of_mappings(
        document.get("volumes"),
        findings=findings,
        scope="manifest.volumes",
    )
    if not isinstance(document.get("volumes"), list):
        _add(findings, "invalid_volumes", "manifest.volumes", "volumes phải là list.")
    _check_unique_names(volumes, "name", "volume", findings)
    purposes = {
        volume.get("purpose") for volume in volumes if isinstance(volume.get("purpose"), str)
    }
    for purpose in {
        "transactional_database",
        "rag_document_index",
        "local_attachment_bytes",
        "batch_analytics_contracts",
        "validated_backup_archives",
    } - purposes:
        _add(
            findings,
            "required_volume_missing",
            f"manifest.volumes.{purpose}",
            f"Thiếu persistent volume cho {purpose}.",
        )
    for volume in volumes:
        if volume.get("service") not in service_names:
            _add(
                findings,
                "volume_service_unknown",
                "manifest.volumes",
                "Volume tham chiếu service không tồn tại.",
            )
        kind = volume.get("kind")
        if kind not in {
            "compose_named_volume",
            "host_bind",
            "operator_managed_directory",
        }:
            _add(
                findings,
                "invalid_volume_kind",
                f"manifest.volumes.{volume.get('name')}",
                "Persistent storage phải khai báo loại volume được hỗ trợ.",
            )
        if kind in {"host_bind", "operator_managed_directory"}:
            storage_path_ref = volume.get("storage_path_ref")
            if storage_path_ref not in _mapping(_mapping(document.get("storage")).get("paths")):
                _add(
                    findings,
                    "volume_storage_path_unknown",
                    f"manifest.volumes.{volume.get('name')}",
                    "Host storage phải tham chiếu storage path đã khai báo.",
                )
        mounted_by = volume.get("mounted_by")
        if mounted_by is not None and (
            not isinstance(mounted_by, list)
            or not mounted_by
            or any(service not in service_names for service in mounted_by)
        ):
            _add(
                findings,
                "volume_mount_service_unknown",
                f"manifest.volumes.{volume.get('name')}",
                "mounted_by chỉ được tham chiếu service trong closed topology.",
            )
        if volume.get("persistent") is not True:
            _add(
                findings,
                "volume_not_persistent",
                "manifest.volumes",
                "Volume pilot phải được đánh dấu persistent=true.",
            )

    _validate_storage(document, repository_root, findings)
    _validate_environment_declarations(document, findings)
    _validate_repository_contract(document, repository_root, findings)
    _validate_health_endpoints(document, service_names, findings)
    _validate_job_catalog(document, findings)
    _validate_runtime_settings(document, findings)


def _validate_storage(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    storage = _mapping(document.get("storage"))
    roots = _mapping(storage.get("allowed_roots"))
    paths = _mapping(storage.get("paths"))
    if not roots:
        _add(
            findings,
            "allowed_roots_missing",
            "manifest.storage",
            "Storage contract phải khai báo allowed_roots.",
        )
    resolved_roots: dict[str, Path] = {}
    for name, root_value in roots.items():
        root_contract = _mapping(root_value)
        environment_name = root_contract.get("environment_variable")
        if (
            not isinstance(environment_name, str)
            or not _ENV_NAME_RE.fullmatch(environment_name)
            or root_contract.get("scope") != "host"
            or root_contract.get("outside_repository") is not True
            or set(root_contract) != {"environment_variable", "scope", "outside_repository"}
        ):
            _add(
                findings,
                "invalid_allowed_root",
                f"manifest.storage.allowed_roots.{name}",
                "Allowed root phải tham chiếu biến môi trường host nằm ngoài repository.",
            )
            continue
        resolved_roots[str(name)] = repository_root

    for required_path in ("attachments", "analytics_source", "analytics_output", "backups"):
        row = _mapping(paths.get(required_path))
        if not row:
            _add(
                findings,
                "required_storage_path_missing",
                f"manifest.storage.paths.{required_path}",
                "Thiếu storage path bắt buộc.",
            )
            continue
        root_name = row.get("root")
        relative_path = row.get("relative_path")
        if root_name not in resolved_roots:
            _add(
                findings,
                "storage_root_unknown",
                f"manifest.storage.paths.{required_path}",
                "Storage path tham chiếu allowed root không tồn tại.",
            )
            continue
        if not _safe_relative_path(relative_path):
            _add(
                findings,
                "path_containment_violation",
                f"manifest.storage.paths.{required_path}",
                "Storage path phải là đường dẫn tương đối nằm trong allowed root.",
            )
            continue
        target = (resolved_roots[str(root_name)] / str(relative_path)).resolve()
        if not target.is_relative_to(resolved_roots[str(root_name)]):
            _add(
                findings,
                "path_containment_violation",
                f"manifest.storage.paths.{required_path}",
                "Storage path thoát khỏi allowed root.",
            )
        if required_path != "backups":
            container_path = row.get("container_path")
            configuration_environment = row.get("configuration_environment")
            if (
                not _safe_container_path(container_path)
                or not isinstance(configuration_environment, str)
                or not _ENV_NAME_RE.fullmatch(configuration_environment)
            ):
                _add(
                    findings,
                    "invalid_container_storage_path",
                    f"manifest.storage.paths.{required_path}",
                    "Application storage phải có container path tuyệt đối và biến cấu hình.",
                )
        else:
            retention = row.get("retention_keep_count")
            if type(retention) is not int or not 1 <= retention <= 365:
                _add(
                    findings,
                    "invalid_backup_retention",
                    "manifest.storage.paths.backups.retention_keep_count",
                    "Số bản backup giữ lại phải nằm trong khoảng 1..365.",
                )


def _validate_environment_declarations(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    raw = document.get("required_environment_variables")
    rows = _list_of_mappings(
        raw,
        findings=findings,
        scope="manifest.required_environment_variables",
    )
    if not isinstance(raw, list):
        _add(
            findings,
            "invalid_environment_contract",
            "manifest.required_environment_variables",
            "required_environment_variables phải là list chỉ chứa tên và secret flag.",
        )
    names: set[str] = set()
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str) or not _ENV_NAME_RE.fullmatch(name):
            _add(
                findings,
                "invalid_environment_name",
                "manifest.required_environment_variables",
                "Environment variable phải có tên uppercase hợp lệ.",
            )
            continue
        if name in names:
            _add(
                findings,
                "duplicate_environment_name",
                f"manifest.required_environment_variables.{name}",
                "Environment variable bị khai báo trùng.",
            )
        names.add(name)
        if set(row) - {"name", "secret"}:
            _add(
                findings,
                "environment_value_in_manifest",
                f"manifest.required_environment_variables.{name}",
                "Manifest chỉ được ghi tên environment variable và secret flag.",
            )
        if type(row.get("secret")) is not bool:
            _add(
                findings,
                "environment_secret_flag_missing",
                f"manifest.required_environment_variables.{name}",
                "Mỗi environment variable phải có secret flag kiểu boolean.",
            )
    for name in sorted(REQUIRED_PILOT_ENVIRONMENT - names):
        _add(
            findings,
            "required_environment_name_missing",
            f"manifest.required_environment_variables.{name}",
            f"Thiếu tên environment variable bắt buộc: {name}.",
        )
    flags = {row.get("name"): row.get("secret") for row in rows if isinstance(row.get("name"), str)}
    for name in sorted(SECRET_ENVIRONMENT_NAMES):
        if flags.get(name) is not True:
            _add(
                findings,
                "secret_environment_not_marked",
                f"manifest.required_environment_variables.{name}",
                f"{name} phải được đánh dấu secret=true.",
            )


def _validate_repository_contract(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    """Bind the manifest to the checked-in Compose and runtime release sources."""

    compose_relative = document.get("compose_file")
    if not _safe_relative_path(compose_relative):
        _add(
            findings,
            "invalid_compose_file",
            "manifest.compose_file",
            "Compose file phải là đường dẫn tương đối nằm trong repository.",
        )
        return
    compose_path = (repository_root / str(compose_relative)).resolve()
    if not compose_path.is_relative_to(repository_root) or not compose_path.is_file():
        _add(
            findings,
            "compose_file_missing",
            "manifest.compose_file",
            "Không tìm thấy Compose file đã khai báo.",
        )
        return
    try:
        compose_text = compose_path.read_text(encoding="utf-8")
    except OSError:
        _add(
            findings,
            "compose_file_unreadable",
            "manifest.compose_file",
            "Không thể đọc Compose file đã khai báo.",
        )
        return

    declarations = _list_of_mappings(document.get("required_environment_variables"))
    declared_names = {row.get("name") for row in declarations if isinstance(row.get("name"), str)}
    compose_required = set(_COMPOSE_REQUIRED_ENV_RE.findall(compose_text))
    for name in sorted(compose_required - declared_names):
        _add(
            findings,
            "compose_environment_not_declared",
            f"manifest.required_environment_variables.{name}",
            f"Biến bắt buộc của Compose chưa có trong manifest: {name}.",
        )

    release = _mapping(document.get("release"))
    versions = _mapping(document.get("versions"))
    if versions.get("application") != APPLICATION_VERSION:
        _add(
            findings,
            "application_version_mismatch",
            "manifest.versions.application",
            "Application version trong manifest không khớp runtime.",
        )
    if release.get("alembic_revision") != CANONICAL_SCHEMA_REVISION:
        _add(
            findings,
            "canonical_migration_revision_mismatch",
            "manifest.release.alembic_revision",
            "Alembic revision trong manifest không khớp schema head của ứng dụng.",
        )

    images = _mapping(document.get("images"))
    source_expectations = (
        (
            repository_root / "Dockerfile",
            f"FROM {images.get('python_base', '')}",
            "manifest.images.python_base",
        ),
        (
            repository_root / "frontend" / "Dockerfile",
            f"FROM {images.get('node_base', '')}",
            "manifest.images.node_base",
        ),
        (
            compose_path,
            f"image: {images.get('postgresql', '')}",
            "manifest.images.postgresql",
        ),
        (
            compose_path,
            f"image: {images.get('qdrant', '')}",
            "manifest.images.qdrant",
        ),
    )
    for source_path, expected_text, scope in source_expectations:
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except OSError:
            _add(
                findings,
                "runtime_source_unreadable",
                scope,
                "Không thể đọc runtime source để đối chiếu version.",
            )
            continue
        if not expected_text.strip() or expected_text not in source_text:
            _add(
                findings,
                "runtime_image_mismatch",
                scope,
                "Image trong manifest không khớp deployment source.",
            )

    package_path = repository_root / "frontend" / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _add(
            findings,
            "frontend_package_unreadable",
            "manifest.versions.frontend",
            "Không thể đọc frontend package metadata để đối chiếu version.",
        )
        return
    dependencies = _mapping(package.get("dependencies"))
    if package.get("version") != versions.get("frontend"):
        _add(
            findings,
            "frontend_version_mismatch",
            "manifest.versions.frontend",
            "Frontend version trong manifest không khớp package metadata.",
        )
    if dependencies.get("next") != versions.get("nextjs"):
        _add(
            findings,
            "nextjs_version_mismatch",
            "manifest.versions.nextjs",
            "Next.js version trong manifest không khớp package metadata.",
        )


def _validate_health_endpoints(
    document: dict[str, Any],
    service_names: set[str],
    findings: list[Finding],
) -> None:
    endpoints = _list_of_mappings(
        document.get("health_endpoints"),
        findings=findings,
        scope="manifest.health_endpoints",
    )
    kinds = {endpoint.get("kind") for endpoint in endpoints}
    for kind in {"liveness", "readiness", "worker_readiness"} - kinds:
        _add(
            findings,
            "health_endpoint_missing",
            f"manifest.health_endpoints.{kind}",
            f"Thiếu endpoint {kind}.",
        )
    seen: set[tuple[Any, Any]] = set()
    for endpoint in endpoints:
        key = (endpoint.get("service"), endpoint.get("path"))
        if key in seen:
            _add(
                findings,
                "duplicate_health_endpoint",
                "manifest.health_endpoints",
                "Health endpoint bị khai báo trùng.",
            )
        seen.add(key)
        if endpoint.get("service") not in service_names:
            _add(
                findings,
                "health_service_unknown",
                "manifest.health_endpoints",
                "Health endpoint tham chiếu service không tồn tại.",
            )
        path = endpoint.get("path")
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or "://" in path
            or ".." in PurePosixPath(path).parts
        ):
            _add(
                findings,
                "invalid_health_path",
                "manifest.health_endpoints",
                "Health endpoint phải là URL path tương đối theo host.",
            )
        statuses = endpoint.get("expected_status")
        if (
            not isinstance(statuses, list)
            or not statuses
            or any(type(status) is not int or not 100 <= status <= 599 for status in statuses)
        ):
            _add(
                findings,
                "invalid_health_status",
                "manifest.health_endpoints",
                "Health endpoint phải khai báo expected HTTP status.",
            )


def _validate_job_catalog(document: dict[str, Any], findings: list[Finding]) -> None:
    raw = document.get("scheduled_jobs")
    jobs = _list_of_mappings(
        raw,
        findings=findings,
        scope="manifest.scheduled_jobs",
    )
    if not isinstance(raw, list):
        _add(
            findings,
            "invalid_job_catalog",
            "manifest.scheduled_jobs",
            "scheduled_jobs phải là list.",
        )
    names: set[str] = set()
    for job in jobs:
        name = job.get("job_type")
        if not isinstance(name, str):
            _add(
                findings,
                "invalid_job_type",
                "manifest.scheduled_jobs",
                "Mỗi job phải có job_type.",
            )
            continue
        if name in names:
            _add(
                findings,
                "duplicate_job",
                f"manifest.scheduled_jobs.{name}",
                "Job bị khai báo trùng.",
            )
        names.add(name)
        if type(job.get("enabled")) is not bool:
            _add(
                findings,
                "job_enabled_not_explicit",
                f"manifest.scheduled_jobs.{name}",
                "Mỗi job phải có enabled kiểu boolean.",
            )
        if set(job) != {"job_type", "enabled"}:
            _add(
                findings,
                "job_configuration_not_closed",
                f"manifest.scheduled_jobs.{name}",
                "Deployment manifest không được nhận cấu hình executable tùy ý.",
            )
    for name in sorted(names - SUPPORTED_JOBS):
        _add(
            findings,
            "unsupported_job",
            f"manifest.scheduled_jobs.{name}",
            f"Job ngoài closed catalog: {name}.",
        )
    for name in sorted(SUPPORTED_JOBS - names):
        _add(
            findings,
            "supported_job_missing",
            f"manifest.scheduled_jobs.{name}",
            f"Closed catalog phải khai báo job {name} với enabled rõ ràng.",
        )
