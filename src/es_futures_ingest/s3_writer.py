"""Append-only S3 writer for RawDailyBar and IngestionRunRecord.

Raw bars are stored Hive-partitioned as
`raw/source=polygon/asset_class=futures/product=ES/contract=<ticker>/
year=<YYYY>/month=<MM>/day=<DD>/ingested_at=<ts>/bar.json` (research.md item 5)
so the raw zone is append-only: a value differing from the most recently
written one for the same contract/date gets a new `ingested_at` partition
rather than overwriting anything (FR-005). A value identical to the most
recent one is not rewritten at all, so re-running ingestion for an
already-ingested date is idempotent (FR-006).

Each RawDailyBar embeds its own `run_id`/`code_version`/`config_version`
(schema.py), so it is fully self-describing lineage on its own — no separate
per-bar sidecar file is written. IngestionRunRecord is written once per
ingestion run at a run-level key instead.
"""

from __future__ import annotations

import json
from datetime import date

from .schema import IngestionRunRecord, RawDailyBar

_RAW_PREFIX = "raw/source=polygon/asset_class=futures/product=ES"
_RUN_PREFIX = "lineage/es_futures_ingest_runs"
_COMPARABLE_FIELDS = ("open", "high", "low", "close", "volume")


def _bar_partition_prefix(contract_ticker: str, trade_date: date) -> str:
    return (
        f"{_RAW_PREFIX}/contract={contract_ticker}/"
        f"year={trade_date.year:04d}/month={trade_date.month:02d}/day={trade_date.day:02d}/"
    )


def _bar_key(bar: RawDailyBar) -> str:
    ingested_at_key = bar.ingested_at.strftime("%Y%m%dT%H%M%S.%fZ")
    prefix = _bar_partition_prefix(bar.contract_ticker, bar.trade_date)
    return f"{prefix}ingested_at={ingested_at_key}/bar.json"


def _run_record_key(record: IngestionRunRecord) -> str:
    return f"{_RUN_PREFIX}/run_id={record.run_id}/run.json"


def _existing_bar_matches(
    s3_client, bucket: str, prefix: str, bar: RawDailyBar
) -> bool:
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            body = s3_client.get_object(Bucket=bucket, Key=obj["Key"])[
                "Body"
            ].read()
            existing = json.loads(body)
            if all(
                existing.get(field) == getattr(bar, field)
                for field in _COMPARABLE_FIELDS
            ):
                return True
    return False


def write_raw_bar(
    s3_client, bucket: str, bar: RawDailyBar
) -> tuple[str, bool]:
    """Write `bar` to S3 unless an identical value already exists.

    Returns (key, was_written). When was_written is False, `key` is the
    existing matching object's prefix (idempotent no-op).
    """
    prefix = _bar_partition_prefix(bar.contract_ticker, bar.trade_date)
    if _existing_bar_matches(s3_client, bucket, prefix, bar):
        return prefix, False

    key = _bar_key(bar)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=bar.model_dump_json().encode("utf-8"),
        ContentType="application/json",
    )
    return key, True


def write_run_record(
    s3_client, bucket: str, record: IngestionRunRecord
) -> str:
    key = _run_record_key(record)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=record.model_dump_json().encode("utf-8"),
        ContentType="application/json",
    )
    return key
