# Contract: Manual Backfill CLI

Supports User Story 3 (on-demand backfill). Invoked by a pipeline operator; also the
same entry point a manual "replay a single day" operation would use.

## Invocation

```text
ingest-es-futures backfill --start-date YYYY-MM-DD [--end-date YYYY-MM-DD]
```

- `--start-date` (required): first trading date to ingest, inclusive.
- `--end-date` (optional): last trading date to ingest, inclusive. Defaults to
  `--start-date` (single-day backfill) when omitted.

## Behavior

- Resolves the front-month contract independently for each date in the requested
  range (per data-model.md#ContractRollSchedule) — a range spanning a roll is
  expected and MUST be handled correctly.
- Non-trading days within the range are skipped and recorded as
  `skipped_non_trading_day` in the resulting `IngestionRunRecord`, not treated as
  errors.
- Each date is ingested independently: a failure on one date is recorded as
  `failed` in `outcome_by_date` and does not stop processing of the remaining
  dates (FR-008, User Story 3 Acceptance Scenario 2).
- Re-running for a date already successfully ingested is idempotent per FR-006 (see
  data-model.md — a new `ingested_at` version is only written if the fetched value
  differs from the most recent existing one for that contract/date; otherwise no
  new object is written).

## Exit Behavior

- Exit code `0`: every requested date reached a terminal non-`failed` outcome.
- Exit code `1`: one or more requested dates ended `failed`. The `IngestionRunRecord`
  (written to S3 and printed to stdout as JSON) enumerates which dates and why via
  `error_detail`.

## Output

On completion, prints the `IngestionRunRecord` JSON
(see `ingestion-run-record.schema.json`) to stdout.
