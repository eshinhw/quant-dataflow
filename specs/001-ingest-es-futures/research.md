# Phase 0 Research: Ingest Daily ES Futures Data from Polygon.io to S3

This is a greenfield feature in an empty repository (no existing language, framework,
or infra conventions to inherit). Each unknown from the plan's Technical Context is
resolved below with a decision, rationale, and alternatives considered.

## 1. Language & Runtime

- **Decision**: Python 3.12
- **Rationale**: Dominant language for quant/data-engineering pipelines; first-class
  AWS SDK (boto3) and Polygon.io client support; strong ecosystem for schema
  validation, retry/backoff, and market-calendar libraries needed here; matches the
  project's own name and domain ("quant-dataflow").
- **Alternatives considered**: Node.js/TypeScript (weaker quant-data ecosystem, no
  strong advantage for this workload); Go (fast and simple to deploy, but weaker
  library support for market calendars and rapid iteration is less valuable here
  than Python's ecosystem fit).

## 2. Source API Access (Polygon.io / Massive)

- **Original decision (superseded)**: Use Polygon.io's official `polygon-api-client`
  Python SDK to call the Futures Aggregates (daily bars) endpoint for a given
  contract ticker and date.
- **What actually happened**: During live integration testing (2026-08-28), every
  `polygon-api-client` futures call (`/futures/vX/aggs/...`, `/futures/vX/contracts`,
  `/futures/vX/products`) returned a plain-text `404 page not found` from the API
  gateway itself — confirmed via raw HTTP with the same key that worked fine on
  non-futures endpoints, ruling out an auth/entitlement problem. The account's
  actual working futures API lives at a different host and version path entirely:
  `https://api.massive.com/futures/v1/...`. The SDK's hardcoded `vX` paths are dead.
- **Revised decision**: Make direct HTTP calls (via `requests`) to
  `https://api.massive.com/futures/v1/...` instead of depending on
  `polygon-api-client` for futures endpoints. Two behaviors specific to this API,
  also discovered during that testing:
  - Ticker format uses a **single-digit year** (e.g. `ESZ5` for December 2025), not
    2- or 4-digit.
  - A session's `window_start` filter value and its `session_end_date` in the
    response can differ by a day (CME futures run ~24h overnight/Globex sessions),
    so a single-date fetch queries a 2-day window and matches `session_end_date`
    client-side.
  - "No data yet" is a normal `200` response with `{"results": [], "status": "OK"}`,
    not an HTTP error.
- **Rationale**: Once the SDK's assumptions were proven wrong, there was no
  remaining benefit to keeping it as a dependency for futures calls — a thin direct
  HTTP wrapper (`polygon_client.py`) is simpler and now the only thing that has
  actually been verified against the real API.
- **Alternatives considered**: Continuing to use the SDK's non-futures methods
  (e.g. for stocks) was not evaluated further since this project only needs futures
  data. Raw HTTP was originally deferred in favor of the SDK "unless the SDK proves
  insufficient" — it did.

## 3. Front-Month Contract Resolution

- **Decision**: Encode the standard ES quarterly expiration cycle (March, June,
  September, October — actually H/M/U/Z: March, June, September, December) and the
  CME's published expiration rule (third Friday of the contract month, trading
  ceases at a fixed time) as a small internal lookup/calculation module, independent
  of Polygon.io. Roll to the next contract a configurable number of trading days
  before expiration (default: on expiration day itself, per FR-003's "currently
  active" wording) unless a data gap forces earlier resolution.
- **Rationale**: The contract roll schedule is a well-known, publicly documented CME
  rule that changes on a fixed quarterly cadence — it does not need to be fetched
  from an external service and is exactly the kind of stable domain logic Simplicity
  & YAGNI favors keeping in-repo rather than adding a dependency for.
- **Alternatives considered**: Querying Polygon.io's reference/contracts endpoint at
  runtime to determine the "current" front month dynamically. Rejected as the
  primary mechanism because it makes contract selection depend on the same
  third-party source being ingested (a circular trust/failure dependency), but
  retained as a secondary validation check (see data-model.md) to catch
  encoding errors in the local roll calendar.

## 4. Trading Calendar (Holidays/Non-Trading Days)

- **Decision**: Use the `pandas-market-calendars` library's CME calendar to
  determine valid ES trading days.
- **Rationale**: Purpose-built, maintained library for exchange trading calendars;
  avoids hand-maintaining a holiday list that silently goes stale.
- **Alternatives considered**: Hand-rolled holiday list (rejected: maintenance
  burden, silent staleness risk violates Observability & Auditability); deriving
  trading days from Polygon.io responses alone (rejected: cannot distinguish "no
  data because holiday" from "no data because of an outage" without an independent
  source of truth).

## 5. Storage Format & Layout

- **Decision**: Store each raw daily bar as a single JSON object in S3 at:
  `s3://<bucket>/raw/source=polygon/asset_class=futures/product=ES/contract=<TICKER>/
  year=<YYYY>/month=<MM>/day=<DD>/ingested_at=<ISO8601>/bar.json`. A differing later
  fetch for the same contract/date writes a new `ingested_at=` partition rather than
  overwriting. (Revised 2026-08-28 from an earlier flatter `.../daily/contract=<T>/
  date=<YYYY-MM-DD>/...` layout, to make the source/asset-class/product boundary
  explicit and split the date into separate year/month/day partitions — friendlier
  to partition projection in Athena/Glue. `RawDailyBar` embeds its own `run_id`,
  `code_version`, and `config_version`, so it is fully self-describing lineage on
  its own; there is no separate per-bar sidecar file.)
- **Rationale**: Hive-style partitioning by source/asset-class/product/contract/
  date/ingestion-time keeps the raw zone append-only (satisfies FR-005/FR-006),
  makes "latest" vs "historical" values queryable, and is directly compatible with
  downstream tools (Athena,
  Spark) without requiring a database for this feature's scope.
- **Alternatives considered**: A DynamoDB table for raw bars (rejected: adds a
  stateful service for a workload that is fundamentally file-based and low-volume —
  violates Simplicity & YAGNI); overwriting a single `latest.json` per contract/date
  (rejected: violates the no-mutation-of-raw-data principle).

## 6. Schema Validation

- **Decision**: Define the raw daily bar schema with `pydantic` and validate every
  fetched record before writing to S3.
- **Rationale**: Pydantic gives explicit, testable field/type/nullability
  constraints (FR-013) with minimal boilerplate and clear validation errors for the
  "fail loudly" requirement (FR-010).
- **Alternatives considered**: JSON Schema validated via `jsonschema` (viable
  alternative, slightly more verbose in Python call sites; pydantic chosen for
  ergonomics, but the JSON Schema contract is still published in `contracts/` as the
  language-agnostic interface description).

## 7. Retry / Backoff

- **Decision**: Use the `tenacity` library for bounded retries with exponential
  backoff around Polygon.io API calls.
- **Rationale**: Well-established, declarative retry library; avoids hand-rolled
  retry loops scattered across the codebase.
- **Alternatives considered**: Hand-rolled retry loop (rejected: more code to
  maintain and test for no added benefit over a well-tested library).

## 8. Compute & Scheduling

- **Decision**: Run the daily ingestion as an AWS Lambda function triggered by an
  Amazon EventBridge Scheduler rule, scheduled daily at 8:00 PM ET (after ES
  market close and Polygon.io's typical end-of-day finalization, and comfortably
  inside the SC-001 9:00 PM ET availability window). The same Lambda code is
  invoked directly (via CLI/SDK invocation) for on-demand backfill of an explicit
  date or date range.
- **Rationale**: The workload is small (one record per trading day), bursty only
  during backfill, and needs no persistent infrastructure — Lambda + EventBridge is
  the simplest AWS-native option that satisfies "runs automatically once per
  trading day" without operating a server or an orchestrator (Simplicity & YAGNI).
- **Alternatives considered**: A workflow orchestrator (Airflow/Step Functions)
  (rejected for this scope: no existing orchestrator in this project, and a single
  daily task with retry/backoff already handled in-process does not need DAG
  orchestration); a long-running container/cron on ECS (rejected: pays for idle
  compute for a job that runs for seconds once a day).

## 9. Deployment Packaging

- **Decision**: Package and deploy the Lambda function and its EventBridge schedule
  using AWS SAM (Serverless Application Model).
- **Rationale**: Lightweight, purpose-built for exactly this shape (one function +
  one schedule + one IAM role), with a low learning/config curve appropriate for a
  new project with no existing IaC convention.
- **Alternatives considered**: AWS CDK (more powerful but adds a full
  programming-language IaC layer for a single-function deployment — more than this
  scope needs); Terraform (viable, but introduces a second toolchain/language for a
  Python-first project with no existing Terraform usage).

## 10. Credentials & Configuration

- **Decision**: Store the Polygon.io API key in AWS Secrets Manager; the Lambda
  execution role is granted read access to that specific secret at deploy time.
  Non-secret configuration (S3 bucket name, retry limits) is passed as Lambda
  environment variables set by the SAM template.
- **Rationale**: Satisfies FR-012 and the constitution's requirement that
  credentials never be committed to the repository; Secrets Manager is the
  AWS-native mechanism for this and integrates directly with Lambda/IAM.
- **Alternatives considered**: SSM Parameter Store (SecureString) (a viable, cheaper
  alternative; Secrets Manager chosen for built-in rotation support, but Parameter
  Store remains an acceptable substitution at implementation time if cost becomes a
  concern — noted here rather than left ambiguous).

## 11. Testing Strategy

- **Decision**: `pytest` for all test levels; `moto` to mock S3 for
  contract/integration tests; a fake/mock Polygon.io client (recorded fixture
  responses) for contract and integration tests so tests do not depend on live
  network access or real API quota.
- **Rationale**: Matches the constitution's requirement to validate against
  sample/replayed data before production, without consuming real API quota or
  requiring live credentials in CI.
- **Alternatives considered**: Live API calls against a Polygon.io sandbox/test key
  in CI (rejected: introduces flakiness and external dependency into the merge
  gate; live validation is still done manually/in a staging run before first
  production deploy, but is not the CI contract-test mechanism).

## Outstanding Unknowns

None. All Technical Context items are resolved above.
