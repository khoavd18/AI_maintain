# Final Release Checklist

This checklist governs a future approved Stage 12 checkpoint and optional public
release. Completing Stage 12 documentation does not authorize a commit, tag,
push, deployment, or cloud mutation.

## 1. Source and documentation review

- [ ] README is readable, professional English, and links to canonical detail.
- [ ] `docs/architecture.md` is the canonical system/data/control-flow source.
- [ ] Demo and operations runbooks are safe in PowerShell and have offline
  fallback paths.
- [ ] Portfolio summary, CV bullets, interview guide, and handover use the same
  source metrics.
- [ ] No duplicate document makes a conflicting architecture, operations, or
  performance claim.
- [ ] No license or unverifiable badge was added.

## 2. Metrics traceability

- [ ] Stage 9 public metrics match `docs/benchmark-results-1m.json`.
- [ ] Stage 10 domain/generation/dbt/test metrics match
  `docs/benchmark-results-domain-scale.json` and
  `docs/benchmark-manifest-domain-scale.json`.
- [ ] Stage 11 API metrics match `docs/benchmark-results-api-stage11.json`.
- [ ] `docs/release-manifest.json` contains numeric values and valid evidence
  paths.
- [ ] Historical metrics are labeled synthetic/historical and not relabeled as
  a Stage 12 rerun.
- [ ] No production SLA, uptime, adoption, business-impact, or prevented-failure
  claim appears.

## 3. Generated-artifact exclusions

- [ ] No `data/scale/` file is tracked.
- [ ] No dbt `target/`, `logs/`, or package artifact is tracked.
- [ ] No `.env`, credential file, cache, dump, backup, attachment, report, or
  runtime evidence became tracked.
- [ ] `.gitignore` retains the scale/runtime/recovery boundaries.

## 4. Security and privacy review

- [ ] High-confidence secret scan reports zero findings.
- [ ] Public-IP and unexpected credential/connection-URI scan reports zero
  findings in release material.
- [ ] No personal email, account ID, endpoint, secret ARN/value, password,
  token, cookie, or Authorization value is documented.
- [ ] Analytics authorization/site/cache boundaries are described accurately.
- [ ] Historical AWS RDS lab is labeled torn down; no live RDS claim exists.

## 5. Git lineage and protected files

- [ ] Branch is `release/stage12-final-portfolio`.
- [ ] Base is Stage 11 commit
  `33ac82efbe5f37ed07d412ba2554fd94bde0b6f3`.
- [ ] Stage 9/10/11 lineage in the manifest matches Git.
- [ ] `src/llm/prompt_builder.py` and
  `tests/test_grounded_generation_repair.py` remain excluded from Stage 9-12
  scope and retain their approved hashes.
- [ ] Staging contains only explicitly reviewed Stage 12 paths.
- [ ] A future checkpoint creates exactly one commit only after approval.

## 6. Validation evidence

- [ ] `git diff --check` passes.
- [ ] PowerShell parser accepts `scripts/verify_final_release.ps1`.
- [ ] `scripts/verify_final_release.ps1 -Mode Offline` exits zero.
- [ ] Stage 12 focused documentation/tooling tests pass.
- [ ] Markdown internal links and Mermaid fences pass.
- [ ] Release manifest JSON and source-evidence consistency pass.
- [ ] Compose configs parse or missing CLI is reported as an explicit SKIP.
- [ ] Airflow DagBag/dbt parse run only when dependencies are already available;
  otherwise historical evidence is cited as SKIP.
- [ ] Expensive Stage 9-11 pipelines and load tests were not rerun merely for
  release formatting.

## 7. Docker-unavailable behavior

- [ ] Offline verification succeeds without Docker daemon.
- [ ] No verifier path starts, stops, recreates, or deletes a container.
- [ ] Live health/watermark/reconciliation gates are labeled SKIP when
  unavailable, not silently treated as pass.
- [ ] No volume deletion or prune command was executed.

## 8. Commit review — future approval gate

- [ ] Owner approves the exact Stage 12 path list.
- [ ] Protected files and generated artifacts are excluded from the index.
- [ ] Complete staged diff, name/status, and additions/deletions are reviewed.
- [ ] Staged-blob secret/public-IP scan passes.
- [ ] Commit subject is separately approved.
- [ ] Git hooks run normally; none is bypassed.
- [ ] Post-commit tree contains only expected protected modifications or is
  explicitly clean for release.

## 9. Optional tag and push — separate future gates

- [ ] Release owner approves a version and annotated tag name.
- [ ] Tag points to the reviewed Stage 12 commit only.
- [ ] Remote, branch, and repository visibility are reviewed before push.
- [ ] Public repository scan confirms no secrets, personal data, generated
  datasets, or private infrastructure details.
- [ ] Push/tag commands are executed only after explicit approval.

## 10. Rollback guidance

- [ ] Keep the Stage 11 base commit and committed evidence available.
- [ ] For a bad future Stage 12 commit, prefer a reviewed `git revert` that
  records history; do not rewrite shared history.
- [ ] Database/schema rollback is a separately rehearsed operational decision,
  never implied by reverting documentation.
- [ ] Preserve benchmark volumes/evidence during rollback analysis.
- [ ] Re-run Offline verification after rollback or correction.

## 11. Post-release verification

- [ ] Confirm branch/tag/commit identity and remote visibility.
- [ ] Run Offline verification with `-RequireCleanCommit`.
- [ ] Validate public README links and Mermaid rendering.
- [ ] Re-scan committed blobs and release archives.
- [ ] If deploying, run target-environment migration, health, auth/site-scope,
  backup/restore, monitoring, and representative load gates.
- [ ] Record observed live results separately from historical lab evidence.
- [ ] Do not begin another project stage; future work is production evolution
  under separately approved scope.
