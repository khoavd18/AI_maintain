"""Capability modules for the bounded multi-domain ELT workflow.

The historical :mod:`data_platform.domain_pipeline` module remains the public
CLI/import facade.  New implementation code belongs in this package so each
pipeline responsibility has one obvious owner.
"""

from data_platform.ingestion.domains.catalog import DOMAINS, DomainSpec, domain_spec

__all__ = [
    "DOMAINS",
    "DomainSpec",
    "domain_spec",
]
