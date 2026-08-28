# Implementation Plan: Ingest Daily ES Futures Data from Polygon.io to S3

**Branch**: `001-ingest-es-futures` | **Date**: 2026-08-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ingest-es-futures/spec.md`

## Summary

Automatically fetch each trading day's front-month ES futures daily OHLCV bar from
Polygon.io and land it as an immutable, versioned, schema-validated raw artifact in
S3, with lineage recorded for every run. A scheduled AWS Lambda function (triggered
daily via EventBridge Scheduler) handles the automated flow; the same code is
exposed as a CLI for on-demand backfill of past dates. Front-month contract
selection and CME trading-day recognition are computed locally (not sourced from
Polygon.io itself) to avoid a circular trust dependency on the ingested source.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: `polygon-api-client` (Polygon.io SDK), `boto3` (S3),
`pydantic` (schema validation), `tenacity` (retry/backoff),
`pandas-market-calendars` (CME trading calendar)

**Storage**: AWS S3 (raw zone, Hive-style partitioned JSON objects — see
research.md item 5)

**Testing**: `pytest`, with `moto` for S3 mocking and recorded-fixture mocking of
the Polygon.io client (no live network calls in CI)

**Target Platform**: AWS Lambda (scheduled via Amazon EventBridge Scheduler),
packaged/deployed with AWS SAM

**Project Type**: Single project — a Python library/CLI package plus its Lambda
deployment packaging

**Performance Goals**: Single-date ingestion (fetch + validate + write) completes
in well under Lambda's default timeout; not throughput-sensitive (one record per
trading day in normal operation)

**Constraints**: Idempotent re-runs (FR-006); append-only raw storage — no
in-place mutation of previously written artifacts (FR-005); credentials never
committed to the repository (FR-012)

**Scale/Scope**: One front-month contract, one bar per trading day, ~252 trading
days/year in steady state; backfill workload is bounded by operator-requested date
ranges, not continuous

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Data Integrity & Reproducibility (NON-NEGOTIABLE) | Deterministic/idempotent re-runs; raw data never mutated in place; every artifact traceable to input/code/config version | **PASS** — append-only `ingested_at`-partitioned S3 layout (research.md #5), `code_version`/`config_version`/`run_id` on every `RawDailyBar` and `IngestionRunRecord` (data-model.md) |
| II. Observability & Auditability | Structured logs; queryable lineage; loud failure on partial/bad data | **PASS** — `IngestionRunRecord` lineage entity (data-model.md); `contracts/daily-job.md` and `contracts/backfill-cli.md` both mandate raising/non-zero-exit on failure, never silent suppression |
| III. Simplicity & YAGNI | No unjustified new services/infra/abstractions | **PASS** — Lambda + EventBridge chosen over an orchestrator (research.md #8); front-month/calendar logic kept as local computation rather than an external service dependency (research.md #3–4) |
| Data & Pipeline Standards | Explicit schema contract at boundaries; secrets out of repo; validated against sample/replayed data pre-production | **PASS** — `contracts/raw-daily-bar.schema.json`; Secrets Manager for Polygon.io key (research.md #10); fixture-based contract/integration tests (research.md #11) |
| Development Workflow & Quality Gates | Spec Kit workflow; PR review; CI data-validation gate; explicit Constitution Check | **PASS** — this document; CI test suite (unit/contract/integration) is the merge gate defined under Project Structure below |

No violations identified. Complexity Tracking table is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-ingest-es-futures/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── raw-daily-bar.schema.json
│   ├── ingestion-run-record.schema.json
│   ├── backfill-cli.md
│   └── daily-job.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
└── es_futures_ingest/
    ├── __init__.py
    ├── config.py              # Env/Secrets Manager config loading
    ├── polygon_client.py      # Polygon.io API wrapper (retry/backoff via tenacity)
    ├── contract_roll.py       # ContractRollSchedule: front-month resolution
    ├── trading_calendar.py    # CME trading-day recognition
    ├── schema.py               # Pydantic models: RawDailyBar, IngestionRunRecord
    ├── s3_writer.py             # Append-only S3 writes for bars + lineage records
    ├── daily_job.py              # Lambda handler (contracts/daily-job.md)
    └── backfill_cli.py            # CLI entry point (contracts/backfill-cli.md)

infra/
└── template.yaml           # AWS SAM template: Lambda + EventBridge Scheduler + IAM + CloudWatch Alarm

tests/
├── contract/                # Validates schema.py output against contracts/*.schema.json,
│                             # and daily_job/backfill_cli behavior against contracts/*.md
├── integration/              # End-to-end flows (moto S3 + mocked Polygon client) per quickstart.md
└── unit/                      # contract_roll, trading_calendar, schema validation logic
```

**Structure Decision**: Single Python project (no frontend/backend or mobile split
applies). Ingestion logic lives in `src/es_futures_ingest/` as a plain importable
package so the Lambda handler and CLI are thin wrappers over the same tested code
path, per Simplicity & YAGNI. Deployment definition lives in `infra/` as a single
SAM template, kept separate from application source since it changes for
different reasons (infra/ops vs. logic).

## Complexity Tracking

*No Constitution Check violations — this section is not applicable.*
