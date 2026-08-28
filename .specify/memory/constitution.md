<!--
Sync Impact Report
- Version change: [TEMPLATE] → 1.0.0 (initial ratification; no prior concrete version existed)
- Modified principles: none (first concrete adoption of the template scaffold)
- Added sections:
  - I. Data Integrity & Reproducibility (NON-NEGOTIABLE)
  - II. Observability & Auditability
  - III. Simplicity & YAGNI
  - Data & Pipeline Standards (Section 2)
  - Development Workflow & Quality Gates (Section 3)
  - Governance
- Removed sections: Principle slots IV and V from the template scaffold (this project
  defines 3 core principles by explicit choice, not 5)
- Templates requiring follow-up: none outstanding — plan/spec/tasks templates read this
  file at runtime and do not embed principle text themselves
- Deferred placeholders: none; all bracketed tokens resolved
-->

# Quant Dataflow Constitution

## Core Principles

### I. Data Integrity & Reproducibility (NON-NEGOTIABLE)
All pipeline transformations MUST be deterministic and idempotent: given the same input
data, configuration, and code version, re-running a pipeline MUST produce identical output.
Raw source data MUST NOT be mutated in place — transformations MUST produce new, versioned
artifacts or datasets, leaving the original input intact and re-runnable. Every dataset and
pipeline run MUST be traceable to the exact input data version, code version (commit SHA),
and configuration that produced it.
**Rationale**: this project moves and transforms market/financial data that feeds downstream
trading and research decisions. Silent corruption, non-reproducible transformations, or
untraceable outputs are not recoverable after the fact and can propagate directly into bad
decisions — they must be structurally prevented, not caught later.

### II. Observability & Auditability
Every pipeline stage MUST emit structured (not free-text) logs capturing its inputs, outputs,
record counts, and timing. Data lineage — source → transformation → destination — MUST be
recorded and queryable for any dataset the pipeline produces. Failures MUST fail loudly:
raising, alerting, or halting the pipeline rather than silently dropping, defaulting, or
skipping bad records. Partial failures MUST be flagged as such, never absorbed into a
"successful" run.
**Rationale**: operators and downstream consumers must be able to answer "where did this
number come from and is it trustworthy" for any value in the system, and data quality
problems must surface before they reach a downstream consumer, not after.

### III. Simplicity & YAGNI
New abstractions, frameworks, services, or infrastructure MUST be justified by a current,
concrete need — not by an anticipated future requirement. The simplest pipeline design that
satisfies the Data Integrity and Observability principles above MUST be preferred; added
complexity (a new service, queue, orchestrator, or abstraction layer) MUST be explicitly
justified in the relevant plan or PR description. Duplicate logic MUST be consolidated, and
unused code paths MUST be removed rather than kept "just in case."
**Rationale**: unnecessary complexity in data pipelines is a leading source of silent bugs
and materially slows incident response when data quality issues do occur.

## Data & Pipeline Standards

Every pipeline or dataset MUST define an explicit schema contract (field names, types,
nullability) at its boundaries, and breaking schema changes MUST be versioned rather than
applied in place. External data feed credentials and connection secrets MUST NOT be
committed to the repository and MUST be sourced from environment configuration or a secrets
manager. Before a pipeline change reaches production, it MUST be exercised against sample or
replayed historical data to validate correctness, not only unit-level logic.

## Development Workflow & Quality Gates

Changes MUST follow the Spec Kit workflow (specify → plan → tasks → implement) for
non-trivial features, so that intent, design, and task breakdown are recorded before code is
written. Every pull request MUST be reviewed by at least one other contributor before merge.
CI MUST run data validation checks (schema, integrity, lineage smoke tests where applicable)
as a merge gate, not merely unit tests. `/speckit-plan` and `/speckit-implement` runs MUST
include an explicit Constitution Check against the principles above; any deviation MUST be
recorded and justified in the plan's Complexity Tracking section rather than silently
introduced.

## Governance

This constitution supersedes ad hoc team practices and prior undocumented conventions for
this repository. Amendments are made by editing `.specify/memory/constitution.md` directly
(via `/speckit-constitution`), describing the change and rationale, and bumping the version
according to semantic versioning: MAJOR for backward-incompatible principle removals or
redefinitions, MINOR for adding a new principle or materially expanding guidance, PATCH for
clarifications and non-semantic wording fixes. Every amendment MUST update the Sync Impact
Report at the top of this file and the version/date line below.

All plans and implementations MUST verify compliance with these principles at the
Constitution Check gate; unjustified complexity or violations MUST block progress until
resolved or explicitly justified. This file is the source of truth for project governance —
where other guidance documents conflict with it, this constitution wins.

**Version**: 1.0.0 | **Ratified**: 2026-08-26 | **Last Amended**: 2026-08-26
