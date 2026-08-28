# Phase 1 Data Model: Ingest Daily ES Futures Data from Polygon.io to S3

## RawDailyBar

Represents one day's OHLCV record for one ES futures contract, exactly as received
from Polygon.io (no transformation).

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `contract_ticker` | string | required, matches Polygon.io ES futures ticker format (e.g. `ESZ5`) | The contract this bar belongs to |
| `trade_date` | date (ISO 8601 `YYYY-MM-DD`) | required | The trading session this bar covers |
| `open` | decimal | required, > 0 | |
| `high` | decimal | required, > 0, >= `low`, >= `open`, >= `close` | |
| `low` | decimal | required, > 0, <= `high`, <= `open`, <= `close` | |
| `close` | decimal | required, > 0 | |
| `volume` | integer | required, >= 0 | |
| `source` | string | required, constant `"polygon.io"` | |
| `ingested_at` | timestamp (ISO 8601, UTC) | required | When this fetch occurred; forms the S3 partition that makes re-fetches append-only |
| `code_version` | string | required | Git commit SHA of the code that produced this record |
| `config_version` | string | required | Identifier/hash of the configuration in effect for this run |
| `run_id` | string (UUID) | required | Foreign key to the `IngestionRunRecord` that produced this artifact — makes lineage resolvable from the artifact alone (SC-004) |

**Validation rules** (enforced before write, per FR-013):
- All required fields present and non-null.
- `high`/`low`/`open`/`close` internally consistent (`low <= open,close <= high`).
- `volume >= 0`.
- `trade_date` must be a valid CME ES trading day (cross-checked against the
  trading calendar from research.md item 4).
- `contract_ticker` must match the front-month ticker resolved for `trade_date` by
  the Contract Roll Schedule below; a mismatch is a hard validation failure, not a
  warning (supports Edge Case: "front-month contract cannot be unambiguously
  determined").

**Identity / uniqueness**: The tuple (`contract_ticker`, `trade_date`,
`ingested_at`) is unique. (`contract_ticker`, `trade_date`) is *not* unique by
design — multiple `ingested_at` versions may exist for the same contract/date if
Polygon.io later publishes a corrected value (FR-005).

## ContractRollSchedule

Not a stored/persisted entity — a deterministic function/lookup, computed from the
standard CME ES quarterly expiration rule (research.md item 3), mapping a calendar
date to the front-month contract ticker active on that date.

| Field | Type | Notes |
|---|---|---|
| `as_of_date` | date | Input: the date to resolve |
| `front_month_ticker` | string | Output: e.g. `ESZ5` |
| `expiration_date` | date | The resolved contract's expiration date, for auditability |

**Rule**: ES contracts expire quarterly (March/H, June/M, September/U, December/Z),
on the third Friday of the contract month. The front-month contract for a given
date is the nearest quarterly contract whose expiration date has not yet passed.

## IngestionRunRecord

Lineage/audit metadata for one execution of the ingestion job (automated daily run
or manual backfill invocation).

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `run_id` | string (UUID) | required | Unique per invocation |
| `trigger` | enum(`scheduled`, `manual_backfill`) | required | |
| `requested_dates` | list[date] | required, non-empty | One or more trading dates targeted by this run |
| `started_at` | timestamp (UTC) | required | |
| `completed_at` | timestamp (UTC) | optional | Absent if the run failed before completion |
| `code_version` | string | required | Git commit SHA |
| `config_version` | string | required | |
| `outcome_by_date` | map[date -> enum(`success`, `failed`, `skipped_non_trading_day`)] | required | Per-date result; a failure on one date must not block others (per User Story 3, Acceptance Scenario 2) |
| `error_detail` | map[date -> string] | optional | Present only for dates with `failed` outcome |

**Relationships**: Each `success` entry in `outcome_by_date` corresponds to exactly
one `RawDailyBar` written during that run (identifiable via matching
`code_version`/`config_version` and `ingested_at` falling within
`[started_at, completed_at]`).

**State transitions**: A run is created at `started_at` with all requested dates
implicitly pending; each date transitions independently to `success`, `failed`, or
`skipped_non_trading_day`; the run itself has no further state once every requested
date has a terminal outcome.
