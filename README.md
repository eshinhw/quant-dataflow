# Quant Dataflow

## ES Futures Daily Ingestion (Polygon.io → S3)

Ingests the front-month E-mini S&P 500 (ES) futures daily OHLCV bar from
Polygon.io into S3 as an immutable, lineage-tracked raw artifact. See
[`specs/001-ingest-es-futures/`](specs/001-ingest-es-futures/) for the full
spec, plan, and design docs.

### Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Required environment variables:

| Variable | Required | Purpose |
|---|---|---|
| `RAW_BUCKET_NAME` | yes | S3 bucket the raw zone is written to |
| `POLYGON_API_KEY` | one of these two | Polygon.io API key (local dev) |
| `POLYGON_API_KEY_SECRET_ARN` | one of these two | Secrets Manager secret ARN holding the key (deployed) |
| `RETRY_MAX_ATTEMPTS` | no (default `5`) | Bounded retry attempts for transient Polygon.io failures |
| `RETRY_BACKOFF_BASE_SECONDS` | no (default `1.0`) | Base seconds for exponential backoff between retries |
| `CODE_VERSION` | no (default `unknown`) | Recorded on every artifact for lineage |

Also requires AWS credentials in the standard credential chain (env vars,
`~/.aws/credentials`, or an assumed role) with S3 write access to
`RAW_BUCKET_NAME`.

### Running the backfill CLI

```bash
ingest-es-futures backfill --start-date 2025-12-10
ingest-es-futures backfill --start-date 2025-12-01 --end-date 2025-12-31
```

Exits `0` if every requested date reached a non-failed outcome, `1` if any
date failed. Prints the resulting `IngestionRunRecord` as JSON to stdout. See
[`contracts/backfill-cli.md`](specs/001-ingest-es-futures/contracts/backfill-cli.md).

### Running the tests

```bash
pytest
ruff check src/ tests/
```

Tests use `moto` to mock S3 and a fake Polygon.io client (`tests/conftest.py`)
— no live network calls or real credentials required.

### Deployment (AWS SAM)

The scheduled daily job is packaged as a Lambda function triggered by an
EventBridge Scheduler rule (`infra/template.yaml`). See
[`contracts/daily-job.md`](specs/001-ingest-es-futures/contracts/daily-job.md).

```bash
sam build --template-file infra/template.yaml
sam deploy \
  --template-file infra/template.yaml \
  --stack-name es-futures-ingest \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
      RawBucketName=<your-bucket> \
      PolygonApiKeySecretArn=<secret-arn> \
      CodeVersion=$(git rev-parse HEAD) \
      AlarmNotificationTopicArn=<sns-topic-arn>
```

This creates the Lambda function, its daily EventBridge schedule (default
8:00 PM ET), and two CloudWatch alarms: one on Lambda invocation errors, and
one that fires if the job is never invoked at all for a full day (a broken
schedule, distinct from a failed run).

### Validating end-to-end

Run through [`quickstart.md`](specs/001-ingest-es-futures/quickstart.md)'s six
scenarios against a deployed non-production stack before promoting to
production, per the project constitution's requirement to validate against
sample/replayed data before production.
