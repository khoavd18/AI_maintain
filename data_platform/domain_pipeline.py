"""Historical facade for the capability-owned multi-domain ELT workflow.

Airflow and documented commands continue to invoke
``python -m data_platform.domain_pipeline``.  The implementation is organized
under :mod:`data_platform.ingestion.domains` for clear ownership and handoff.
"""

from __future__ import annotations

from data_platform.ingestion.domains.catalog import (
    DOMAINS,
    DOMAIN_SPECS as _SPECS,
    DomainSpec,
    domain_spec as _domain,
)
from data_platform.ingestion.domains.cli import main as _main
from data_platform.ingestion.domains.extraction import (
    EPOCH,
    LOGGER,
    UTC,
    ZERO_ID,
    existing_batch as _existing_batch,
    extract_domain,
    watermark as _watermark,
)
from data_platform.ingestion.domains.raw_loading import (
    InjectedDomainFailure,
    copy_raw_object as _copy_raw_object,
    load_raw_domain,
)
from data_platform.ingestion.domains.reconciliation import (
    finalize_watermarks,
    reconcile_run,
    relation_count as _relation_count,
)
from data_platform.ingestion.domains.run_tracking import (
    complete_run,
    fail_run,
    pipeline_state,
    retry_run,
    start_run,
)
from data_platform.ingestion.domains.safety import (
    sanitize_audit_message as _sanitize,
    validate_run_id as _validated_run_id,
)
from data_platform.ingestion.domains.source_validation import (
    domain_source_counts,
    validate_domain_integrity,
)

# Keep explicit imports used by historical tests and callers without exposing
# these private compatibility aliases through ``from ... import *``.
_COMPATIBILITY_PRIVATE_ALIASES = (
    _SPECS,
    _copy_raw_object,
    _domain,
    _existing_batch,
    _relation_count,
    _sanitize,
    _validated_run_id,
    _watermark,
)

__all__ = [
    "DOMAINS",
    "DomainSpec",
    "EPOCH",
    "InjectedDomainFailure",
    "LOGGER",
    "UTC",
    "ZERO_ID",
    "complete_run",
    "domain_source_counts",
    "extract_domain",
    "fail_run",
    "finalize_watermarks",
    "load_raw_domain",
    "main",
    "pipeline_state",
    "reconcile_run",
    "retry_run",
    "start_run",
    "validate_domain_integrity",
]


def main() -> None:
    """Run the historical CLI entrypoint."""

    _main()


if __name__ == "__main__":
    main()
