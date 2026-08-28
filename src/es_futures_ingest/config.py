"""Environment/Secrets Manager configuration loading.

Non-secret configuration comes from environment variables (set as Lambda
environment variables by the SAM template in production). The Polygon.io API
key is read directly from POLYGON_API_KEY when set (local development); in
deployed environments it is instead resolved from AWS Secrets Manager via
POLYGON_API_KEY_SECRET_ARN, per research.md item 10.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache

import boto3


@dataclass(frozen=True)
class Config:
    raw_bucket_name: str
    polygon_api_key: str
    retry_max_attempts: int
    retry_backoff_base_seconds: float
    code_version: str
    config_version: str


def _resolve_polygon_api_key() -> str:
    direct = os.environ.get("POLYGON_API_KEY")
    if direct:
        return direct

    secret_arn = os.environ.get("POLYGON_API_KEY_SECRET_ARN")
    if not secret_arn:
        raise RuntimeError(
            "No Polygon.io API key available: set POLYGON_API_KEY or "
            "POLYGON_API_KEY_SECRET_ARN"
        )

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    return response["SecretString"]


def _compute_config_version(
    raw_bucket_name: str,
    retry_max_attempts: int,
    retry_backoff_base_seconds: float,
) -> str:
    """Deterministic hash of non-secret config, for lineage traceability."""
    fingerprint = (
        f"{raw_bucket_name}|{retry_max_attempts}|{retry_backoff_base_seconds}"
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]


@lru_cache(maxsize=1)
def get_config() -> Config:
    raw_bucket_name = os.environ.get("RAW_BUCKET_NAME")
    if not raw_bucket_name:
        raise RuntimeError("RAW_BUCKET_NAME environment variable is required")

    retry_max_attempts = int(os.environ.get("RETRY_MAX_ATTEMPTS", "5"))
    retry_backoff_base_seconds = float(
        os.environ.get("RETRY_BACKOFF_BASE_SECONDS", "1.0")
    )
    code_version = os.environ.get("CODE_VERSION", "unknown")

    return Config(
        raw_bucket_name=raw_bucket_name,
        polygon_api_key=_resolve_polygon_api_key(),
        retry_max_attempts=retry_max_attempts,
        retry_backoff_base_seconds=retry_backoff_base_seconds,
        code_version=code_version,
        config_version=_compute_config_version(
            raw_bucket_name, retry_max_attempts, retry_backoff_base_seconds
        ),
    )
