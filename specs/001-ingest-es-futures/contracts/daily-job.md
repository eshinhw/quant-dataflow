# Contract: Scheduled Daily Ingestion Job (Lambda Handler)

Supports User Story 1 (automated daily ingestion). Triggered by an Amazon
EventBridge Scheduler rule once per trading day, after ES market close and
Polygon.io's typical end-of-day finalization window.

## Trigger Input

EventBridge Scheduler invokes the handler with no meaningful payload; the target
trading date defaults to "the most recently completed trading day" as of
invocation time, resolved via the trading calendar
(data-model.md — non-trading days are skipped, not treated as the target).

## Behavior

1. Resolve the target trading date's front-month contract
   (data-model.md#ContractRollSchedule).
2. Fetch that contract/date's daily bar from Polygon.io with bounded retry/backoff
   (research.md item 7).
3. Validate the fetched record against `raw-daily-bar.schema.json`.
4. If Polygon.io has not yet published the day's data, or validation fails, or
   retries are exhausted: fail loudly (raise) — no partial or empty record is
   written (FR-010, User Story 1 Acceptance Scenario 3).
5. Write the validated record to S3 at the path defined in research.md item 5.
6. Write the corresponding `IngestionRunRecord` (this contract's lineage output).

## Output / Failure Signaling

- Success: handler returns normally; the `IngestionRunRecord` for this invocation
  has `outcome_by_date` = `{ "<date>": "success" }`.
- Failure: handler raises an exception (surfaced by Lambda as an invocation error),
  which MUST trigger the deployed alerting mechanism (e.g. a CloudWatch Alarm on
  Lambda `Errors`) — satisfies SC-006 ("visible, actionable failure signal").
- The handler MUST NOT catch-and-suppress a failure to force a "successful"
  invocation; per the Observability & Auditability principle, partial failures are
  never absorbed into a successful run.
