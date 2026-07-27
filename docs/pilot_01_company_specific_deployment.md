# Pilot 01 — Company-Specific Deployment

## Status

This is the next external engagement after PM9. It is not Product Milestone 10
and no part of it has started.

Pilot 01 may begin only when all of the following exist:

- a sponsoring organization;
- an approved pilot or pilot-equivalent host;
- a pilot business owner and company operational owner;
- an approved incident communication and escalation path;
- pilot-grade secrets and an approved secret-handling process;
- representative company data with authorization to use it;
- identified pilot users;
- organizational review of the documented limitations;
- authorization to run bounded load, failure, and recovery drills.

Until then, the real-company pilot gate remains:

```text
BLOCKED — EXTERNAL DEPENDENCY
```

and the overall external pilot decision remains:

```text
NO-GO / WAITING FOR PILOT SPONSOR
```

## Engagement Scope

When the prerequisites are satisfied, Pilot 01 should cover:

1. approved environment configuration and release identity;
2. company data mapping, validation, and authorized import;
3. user bootstrap, role assignment, and RBAC verification;
4. deployment on the approved host;
5. PostgreSQL and attachment backup/restore rehearsal;
6. signing-key and database-credential rotation;
7. bounded soak, mutation-bearing, and capacity/degradation testing;
8. user and operator training;
9. monitored pilot use under confirmed support coverage;
10. feedback, incident, and issue triage;
11. final organizational limitation review and go/no-go decision.

## Boundary

Pilot 01 is company-specific execution of the PM9 design and runbooks. It does
not authorize new application features, PM10 work, production-readiness claims,
or expansion into prohibited domains. Scope changes must be evaluated
separately from pilot verification.

No owner, user, secret, approval, workload, or outcome may be inferred before a
real sponsor supplies it. Evidence must identify the approved environment and
executed profile without committing credentials, personal contact details, raw
company data, or local private paths.

See [pilot deployment](pilot_deployment.md),
[operational ownership](operational_ownership.md),
[known limitations](known_limitations_acceptance.md), and the
[PM9 release note](releases/product_milestone_9.md).
