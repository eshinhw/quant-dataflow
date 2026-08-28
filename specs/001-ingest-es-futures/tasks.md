---

description: "Task list template for feature implementation"
---

# Tasks: Ingest Daily ES Futures Data from Polygon.io to S3

**Input**: Design documents from `/specs/001-ingest-es-futures/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the constitution requires CI to run data-validation checks as a
merge gate (not merely unit tests) and requires changes to be exercised against
sample/replayed data before production, so contract and integration tests are part
of every user story phase.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) to
enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths are relative to the repository root, per plan.md's Project Structure

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create project skeleton: `src/es_futures_ingest/__init__.py`, `infra/`,
  `tests/unit/`, `tests/contract/`, `tests/integration/` per plan.md's Project
  Structure
- [X] T002 Initialize Python 3.12 project (`pyproject.toml`) with dependencies
  `polygon-api-client`, `boto3`, `pydantic`, `tenacity`, `pandas-market-calendars`,
  and dev dependencies `pytest`, `moto`
- [X] T003 [P] Configure linting/formatting (`ruff`) and `pytest` configuration in
  `pyproject.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be
implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 [P] Implement config loading (env vars `RAW_BUCKET_NAME`, retry limits;
  Polygon.io API key from `POLYGON_API_KEY` env var or AWS Secrets Manager per
  research.md #10) in `src/es_futures_ingest/config.py`
- [X] T005 [P] Implement `RawDailyBar` and `IngestionRunRecord` pydantic models per
  data-model.md, matching field constraints and validation rules (OHLC
  consistency, non-negative volume, trade_date/contract_ticker cross-check hook,
  `run_id` linkage between the two entities) in `src/es_futures_ingest/schema.py`
- [X] T006 [P] Implement CME trading-day recognition (`is_trading_day(date)`,
  `most_recent_completed_trading_day()`) using `pandas-market-calendars` per
  research.md #4 in `src/es_futures_ingest/trading_calendar.py`
- [X] T007 [P] Implement `ContractRollSchedule` front-month resolution
  (`resolve_front_month(date) -> (ticker, expiration_date)`) for the standard ES
  quarterly H/M/U/Z cycle per data-model.md and research.md #3 in
  `src/es_futures_ingest/contract_roll.py`
- [X] T008 [P] Implement structured JSON logging setup (`get_logger(name)`) per the
  Observability & Auditability principle in `src/es_futures_ingest/logging_setup.py`
- [X] T009 Implement append-only S3 writer (`write_raw_bar`, `write_run_record`)
  using the Hive-style partition layout from research.md #5, never overwriting an
  existing `ingested_at` partition, in `src/es_futures_ingest/s3_writer.py`
  (depends on T005)
- [X] T010 Implement Polygon.io client wrapper
  (`fetch_daily_bar(ticker, trade_date)`) using `polygon-api-client` with
  `tenacity` bounded retry/backoff per research.md #2 and #7, raising on
  exhausted retries, in `src/es_futures_ingest/polygon_client.py` (depends on
  T004, T005)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Automated Daily Ingestion (Priority: P1) 🎯 MVP

**Goal**: Automatically fetch the front-month ES daily bar for a completed trading
day, validate it, and land it in S3 as an immutable, lineage-tracked artifact —
idempotently, and failing loudly when source data isn't ready.

**Independent Test**: Run the ingestion function for a single known past trading
day; verify exactly one correctly formatted `RawDailyBar` object appears in S3 with
a matching `IngestionRunRecord`; re-running produces no duplicate; running for a
date whose data Polygon.io hasn't published yet fails loudly with no partial write.

### Tests for User Story 1

- [X] T011 [P] [US1] Contract test validating `schema.py`'s `RawDailyBar` against
  `contracts/raw-daily-bar.schema.json` in
  `tests/contract/test_raw_daily_bar_schema.py`
- [X] T012 [P] [US1] Contract test validating `schema.py`'s `IngestionRunRecord`
  against `contracts/ingestion-run-record.schema.json` in
  `tests/contract/test_ingestion_run_record_schema.py`
- [X] T013 [P] [US1] Contract test for the daily job handler's success and
  fail-loud paths per `contracts/daily-job.md` in
  `tests/contract/test_daily_job_contract.py`
- [X] T014 [P] [US1] Integration test for quickstart.md Scenario 1 (single-day
  ingestion + idempotent re-run) using `moto` S3 and a mocked Polygon.io client in
  `tests/integration/test_single_day_ingestion.py`
- [X] T015 [P] [US1] Integration test for quickstart.md Scenario 4 (source not yet
  published → fail loud, zero objects written) in
  `tests/integration/test_unpublished_data_failure.py`

### Implementation for User Story 1

- [X] T016 [US1] Implement the core ingestion function (resolve front-month
  contract → fetch → validate → idempotency check → write `RawDailyBar` +
  `IngestionRunRecord`) in `src/es_futures_ingest/ingest.py` (depends on T005,
  T006, T007, T009, T010)
- [X] T017 [US1] Implement the daily job Lambda handler wrapping `ingest.py` for
  "the most recently completed trading day" per `contracts/daily-job.md` in
  `src/es_futures_ingest/daily_job.py` (depends on T016)
- [X] T018 [US1] Wire structured logging and fail-loud (raise, never
  catch-and-suppress) exception propagation through `ingest.py` and
  `daily_job.py` per the Observability & Auditability principle (depends on
  T016, T017, T008)

**Checkpoint**: User Story 1 is fully functional and independently testable — this
is the MVP.

---

## Phase 4: User Story 2 - Front-Month Contract Roll Handling (Priority: P2)

**Goal**: Guarantee the pipeline always tracks the correct front-month contract
across quarterly rolls, and fails loudly instead of guessing when the front month
cannot be unambiguously determined.

**Independent Test**: Run ingestion across a set of dates spanning a known
historical ES quarterly expiration and verify the contract ticker switches at the
correct roll point; run against a constructed ambiguous case and verify a loud
failure rather than a silent guess.

### Tests for User Story 2

- [X] T019 [P] [US2] Unit tests for `contract_roll.py` covering multiple quarterly
  cycles and exact roll-boundary dates (day before/on/after expiration) in
  `tests/unit/test_contract_roll.py`
- [X] T020 [P] [US2] Integration test for quickstart.md Scenario 3 (contract roll
  across a date range) in `tests/integration/test_contract_roll_transition.py`
- [X] T021 [P] [US2] Unit test for quickstart.md Scenario 6 asserting a fail-loud
  outcome when the locally resolved front-month ticker disagrees with Polygon.io's
  contract reference data (ambiguous determination, per spec.md Edge Cases) in
  `tests/unit/test_contract_roll_ambiguity.py`

### Implementation for User Story 2

- [X] T022 [US2] Add secondary cross-validation of the locally resolved
  front-month ticker against Polygon.io's contract reference data, per research.md
  #3, in `src/es_futures_ingest/contract_roll.py` (depends on T007, T010)
- [X] T023 [US2] Wire an ambiguous-contract fail-loud path (flag date for manual
  review rather than guessing, per the Edge Cases in spec.md) into `ingest.py` in
  `src/es_futures_ingest/ingest.py` (depends on T022, T016)

**Checkpoint**: User Stories 1 AND 2 both work independently — roll transitions are
verified correct and ambiguity is caught rather than guessed.

---

## Phase 5: User Story 3 - On-Demand Historical Backfill (Priority: P3)

**Goal**: Let an operator re-run ingestion for an explicit past date or date range,
with each date processed independently so one failure doesn't block the rest.

**Independent Test**: Invoke the backfill CLI for a past date (and separately, a
range spanning a non-trading day and a deliberately-failing date) not previously
ingested, and verify per-date outcomes match `contracts/backfill-cli.md`.

### Tests for User Story 3

- [X] T024 [P] [US3] Contract test for the backfill CLI (single date, date range,
  exit codes, output format) per `contracts/backfill-cli.md` in
  `tests/contract/test_backfill_cli_contract.py`
- [X] T025 [P] [US3] Integration test for quickstart.md Scenario 2 (non-trading day
  is skipped, not treated as a failure) in
  `tests/integration/test_non_trading_day_skip.py`
- [X] T026 [P] [US3] Integration test for a multi-date range where one date fails
  and the rest still succeed (spec.md User Story 3, Acceptance Scenario 2) in
  `tests/integration/test_backfill_partial_failure.py`

### Implementation for User Story 3

- [X] T027 [US3] Implement the backfill CLI (`--start-date`/`--end-date` parsing,
  per-date independent invocation of the core ingestion function, aggregated
  `IngestionRunRecord`, exit codes) per `contracts/backfill-cli.md` in
  `src/es_futures_ingest/backfill_cli.py` (depends on T016)
- [X] T028 [US3] Wire non-trading-day skip handling into the backfill loop,
  recording `skipped_non_trading_day` per date, in
  `src/es_futures_ingest/backfill_cli.py` (depends on T027, T006)

**Checkpoint**: All three user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Deployment packaging and delivery-readiness that spans all user
stories

- [X] T029 [P] Write the AWS SAM template (Lambda function, EventBridge Scheduler
  daily rule at 8:00 PM ET, IAM role scoped to the raw S3 prefix and the
  Polygon.io Secrets Manager secret, CloudWatch Alarm on Lambda `Errors`) per
  research.md #8–#10 and `contracts/daily-job.md` in `infra/template.yaml`
- [X] T030 [P] Register the `ingest-es-futures` console script entry point for the
  backfill CLI in `pyproject.toml`
- [X] T031 [P] Document local usage (env vars, CLI invocation) and deployment
  (`sam build`/`sam deploy`) in `README.md`
- [X] T032 [P] Add a CI workflow that runs the unit/contract/integration test suite
  as a merge gate, per the Development Workflow & Quality Gates constitution
  section, in `.github/workflows/test.yml`
- [ ] T033 Execute the full quickstart.md validation (all 6 scenarios) end-to-end
  against a deployed non-production stack
- [X] T034 [P] Add a CloudWatch alarm on "no successful daily-job invocation
  recorded by 9:00 PM ET" (distinct from the `Errors` alarm in T029 — this catches
  a missed/never-triggered run, not just a failed one, per SC-001) in
  `infra/template.yaml`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational; extends `contract_roll.py`
  and `ingest.py` from User Story 1 (T007, T016) but is independently testable on
  its own scenarios
- **User Story 3 (Phase 5)**: Depends on Foundational; reuses the core ingestion
  function from User Story 1 (T016) but is independently testable on its own
  scenarios
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Within Each User Story

- Tests are written before implementation and should fail first
- Core logic before handler/CLI wiring
- Story complete and independently checkpointed before moving to the next priority

### Parallel Opportunities

- T003 can run alongside T001/T002 once the skeleton exists
- T004–T008 (five foundational modules) can all run in parallel — different files,
  no interdependencies
- T011–T015 (all US1 tests) can run in parallel
- T019–T021 (all US2 tests) can run in parallel
- T024–T026 (all US3 tests) can run in parallel
- T029–T032 and T034 (Polish) can all run in parallel; T033 runs last (depends on
  everything else in Polish)

---

## Parallel Example: Foundational Phase

```bash
Task: "Implement config loading in src/es_futures_ingest/config.py"
Task: "Implement RawDailyBar and IngestionRunRecord models in src/es_futures_ingest/schema.py"
Task: "Implement CME trading-day recognition in src/es_futures_ingest/trading_calendar.py"
Task: "Implement ContractRollSchedule resolution in src/es_futures_ingest/contract_roll.py"
Task: "Implement structured logging setup in src/es_futures_ingest/logging_setup.py"
```

## Parallel Example: User Story 1 Tests

```bash
Task: "Contract test for RawDailyBar schema in tests/contract/test_raw_daily_bar_schema.py"
Task: "Contract test for IngestionRunRecord schema in tests/contract/test_ingestion_run_record_schema.py"
Task: "Contract test for daily job handler in tests/contract/test_daily_job_contract.py"
Task: "Integration test for single-day ingestion in tests/integration/test_single_day_ingestion.py"
Task: "Integration test for unpublished-data failure in tests/integration/test_unpublished_data_failure.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenarios 1 and 4 independently
5. This is a deployable MVP — daily ingestion works end-to-end without roll
   hardening or backfill

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. User Story 1 → validate → MVP deployable
3. User Story 2 → validate roll-boundary correctness and ambiguity handling →
   deploy
4. User Story 3 → validate backfill → deploy
5. Polish (SAM template, CI gate, missed-run alarm, docs) → full quickstart.md
   validation

## Notes

- [P] tasks touch different files with no unmet dependencies
- Commit after each task or logical group
- Every fetched record must pass schema validation (T005/T011) before any S3 write
  — no task should bypass this gate
- Avoid: silently catching exceptions anywhere in `ingest.py`, `daily_job.py`, or
  `backfill_cli.py` — the constitution requires loud failure, not graceful
  degradation, for this pipeline
