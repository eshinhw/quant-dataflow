# Feature Specification: Ingest Daily ES Futures Data from Polygon.io to S3

**Feature Branch**: `001-ingest-es-futures`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "Ingest daily raw ES futures data from Polygon.io into AWS S3"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Daily Ingestion (Priority: P1)

As a quant researcher/pipeline operator, I need the front-month E-mini S&P 500 (ES)
futures daily bar to be automatically pulled from Polygon.io and landed in S3 every
day, so that downstream research and trading systems always have an up-to-date,
trustworthy raw dataset without anyone manually fetching it.

**Why this priority**: This is the core value of the feature — without reliable,
unattended daily ingestion, there is no pipeline. Every other capability (backfill,
lineage, alerting) exists to support this primary flow.

**Independent Test**: Can be fully tested by running the ingestion job for a single
trading day and verifying that exactly one correctly formatted raw ES daily bar
object appears in the expected S3 location, matching what Polygon.io reports for
that day and that contract.

**Acceptance Scenarios**:

1. **Given** a completed trading day with the front-month ES contract identified,
   **When** the daily ingestion job runs, **Then** a single raw daily OHLCV record
   for that contract and date is written to S3 with source, contract, and date
   metadata attached.
2. **Given** the ingestion job has already successfully written a day's data,
   **When** the job is re-run for that same day, **Then** the same output is
   produced without creating duplicate or conflicting objects (idempotent re-run).
3. **Given** Polygon.io has not yet published data for the requested day (e.g. job
   runs before market data finalizes), **When** the ingestion job runs, **Then** the
   job fails loudly with a clear error rather than writing an empty or partial
   record.

---

### User Story 2 - Front-Month Contract Roll Handling (Priority: P2)

As a quant researcher, I need the pipeline to automatically track which ES contract
is currently the front month, so that the daily data I receive always reflects the
most liquid, actively-traded contract without manual intervention at each quarterly
expiration.

**Why this priority**: ES futures expire quarterly and liquidity shifts to the next
contract before expiration. Without automatic roll handling, the pipeline silently
starts ingesting a stale, thinly-traded contract — a correctness problem that is
easy to miss and directly undermines data trustworthiness.

**Independent Test**: Can be tested independently by running the ingestion job on
dates spanning a known historical contract roll and verifying the pipeline switches
which contract ticker it requests from Polygon.io at the expected roll point.

**Acceptance Scenarios**:

1. **Given** the current date is before a quarterly ES expiration, **When** the
   ingestion job determines the front-month contract, **Then** it selects the
   currently active front-month ticker.
2. **Given** the current date crosses the front-month roll point, **When** the
   ingestion job runs on and after that date, **Then** it selects the new
   front-month ticker going forward, and the prior day's data remains attributed to
   the previous contract.

---

### User Story 3 - On-Demand Historical Backfill (Priority: P3)

As a pipeline operator, I need to be able to re-run ingestion for an arbitrary past
date or range of dates, so that I can recover from an outage, fix a data gap, or
extend the dataset backward without waiting for a new automated run.

**Why this priority**: Gaps and outages happen. Manual backfill capability is
important for operability but is not required for the pipeline to deliver its core
daily value, so it is lower priority than the automated daily flow and roll
handling.

**Independent Test**: Can be tested independently by invoking the ingestion job with
an explicit past date (or date range) not previously ingested and verifying the
correct historical front-month contract's data is fetched and written to S3 for
each requested date.

**Acceptance Scenarios**:

1. **Given** a specific past trading date, **When** an operator triggers a manual
   backfill for that date, **Then** the pipeline resolves the correct historical
   front-month contract for that date and writes the corresponding raw daily bar to
   S3.
2. **Given** a range of past trading dates, **When** an operator triggers a backfill
   for that range, **Then** each trading day in the range is ingested independently
   and a failure on one date does not block ingestion of the other dates in the
   range.

---

### Edge Cases

- What happens when Polygon.io returns no data for a given date because it was a
  market holiday or non-trading day? The pipeline must recognize non-trading days
  (via an exchange calendar) and skip them without raising a false failure.
- How does the system handle a Polygon.io API error (rate limit, timeout, 5xx)? The
  job must retry with backoff a bounded number of times, then fail loudly and
  surface the error rather than silently skipping the day.
- How does the system handle Polygon.io returning a value for the same
  contract/date that differs from a previously ingested value (a source-side
  correction)? The new value must be written as a new versioned artifact rather
  than silently overwriting the prior one, per the project's data integrity
  principle.
- What happens if the front-month contract cannot be unambiguously determined for a
  given date (e.g. during an unusual liquidity transition)? The job must fail loudly
  and flag the date for manual review rather than guessing.
- What happens when the daily job runs but the exact trading day it targets is still
  in progress or not yet finalized upstream? The job must fail loudly rather than
  ingest incomplete data (see User Story 1, Acceptance Scenario 3).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST fetch one daily OHLCV (open, high, low, close, volume)
  bar per trading day for the current front-month ES futures contract from
  Polygon.io.
- **FR-002**: System MUST run the ingestion automatically once per trading day,
  after that day's data is expected to be finalized at the source.
- **FR-003**: System MUST determine the correct front-month ES contract for any
  given date based on the ES quarterly expiration schedule, without manual
  configuration for each roll.
- **FR-004**: System MUST write each ingested daily bar to S3 as a new, raw,
  unmodified artifact, tagged with its source, contract ticker, and trade date.
- **FR-005**: System MUST NOT overwrite or mutate a previously written raw artifact
  for a given contract and date; a differing value received later for the same
  contract/date MUST be stored as an additional versioned artifact.
- **FR-006**: System MUST be idempotent — re-running ingestion for a
  contract/date that was already successfully ingested MUST NOT create duplicate
  or conflicting "current" output.
- **FR-007**: System MUST recognize exchange non-trading days (weekends, market
  holidays) and skip ingestion for those days without raising a failure.
- **FR-008**: System MUST support ingesting an explicit past date or range of past
  dates on demand (manual backfill), independent of the automated daily run.
- **FR-009**: System MUST retry transient Polygon.io API failures (timeouts, rate
  limits, 5xx errors) a bounded number of times with backoff before failing.
- **FR-010**: System MUST fail loudly (raise/alert, not silently skip or write
  partial data) when: the source has not yet published data for the requested
  day, the front-month contract cannot be unambiguously determined, or retries are
  exhausted.
- **FR-011**: System MUST record, for every ingestion run, structured lineage
  information (source, contract, date, run timestamp, code/config version) needed
  to trace any stored artifact back to how and when it was produced.
- **FR-012**: System MUST keep Polygon.io API credentials out of the repository,
  sourced from environment configuration or a secrets manager.
- **FR-013**: System MUST validate each fetched record against an explicit schema
  (expected fields, types, non-null constraints) before writing it to S3, and MUST
  fail loudly if a record does not conform.

### Key Entities

- **Raw Daily Bar**: A single day's OHLCV record for one ES futures contract, as
  received from Polygon.io. Attributes: contract ticker, trade date, open, high,
  low, close, volume, source, ingestion timestamp, code/config version.
- **Contract Roll Schedule**: The mapping of calendar dates to the front-month ES
  contract ticker active on that date, derived from the ES quarterly expiration
  calendar.
- **Ingestion Run Record**: Lineage/audit metadata for one execution of the
  ingestion job — what date(s)/contract(s) it targeted, when it ran, what code and
  configuration version it used, and its outcome (success, failure, retried).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every completed trading day, the corresponding front-month ES
  raw daily bar is available in S3 by 9:00 PM ET the same trading day, with no
  manual intervention, at least 99% of the time over a rolling 30-day period.
- **SC-002**: Re-running ingestion for any already-ingested date never produces a
  duplicate or conflicting record — verified by zero duplicate "current" artifacts
  found across repeated runs.
- **SC-003**: A manual backfill for any valid past trading date completes and
  produces a correctly attributed record within minutes, without requiring code
  changes.
- **SC-004**: 100% of ingested records carry lineage metadata sufficient to answer
  "what source, contract, and run produced this value" without consulting anything
  outside the stored artifact and its metadata.
- **SC-005**: Every quarterly ES contract roll is reflected in ingested data with
  zero manual configuration changes required at the roll date.
- **SC-006**: Any Polygon.io fetch failure or missing/ambiguous data condition
  results in a visible, actionable failure signal — zero silent data gaps in a
  rolling 30-day period.

## Assumptions

- Polygon.io's futures API (or equivalent product tier the account has access to)
  provides daily aggregate bars for individual ES futures contract tickers,
  including historical dates, under the account's current subscription/entitlement.
- "Raw" means the data is stored as received from Polygon.io (no transformation,
  aggregation, or cleansing applied), consistent with the project's data integrity
  principle of not mutating source data in place.
- An external, authoritative ES quarterly expiration/roll calendar (standard
  quarterly cycle: March, June, September, December) is available or can be
  encoded, and does not require ingestion from Polygon.io itself.
- A standard market holiday/trading calendar for the CME (where ES trades) is
  available for determining non-trading days.
- "Daily" ingestion cadence means one run per trading day, scheduled after that
  day's session and data finalization; the exact run time is an implementation
  detail to be resolved during planning.
- Historical backfill is triggered manually/on-demand rather than automatically
  bulk-loading a fixed historical window as part of this feature.
- Downstream consumers of this raw data (research notebooks, other pipeline
  stages) are out of scope for this feature; this feature's boundary ends at
  durably, traceably landing raw daily bars in S3.
