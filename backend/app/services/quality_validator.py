"""Structured data-quality validation powered by Pandera.

Replaces hand-written (condition, error_message) tuples with declarative
Pandera schemas, yielding per-record / per-field structured failure reports.
"""

from __future__ import annotations

import re

from app.core.utils import dedupe_notes
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import pandera as pa
from pandera.typing import DataFrame, Series

from app.models.schemas import TrafficRecord

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
_VALID_DST_PORTS = {80, 443, 8080, 8443}
_SCRIPT_UA_TOKENS = {"python", "curl", "go", "scrapy", "urllib", "httpx"}

# Map Pandera check names → human-readable Chinese labels
_CHECK_LABELS: dict[str, str] = {
    # format
    "id_non_empty": "id 为空",
    "isin({'GET', 'POST', 'PUT', 'DELETE'})": "HTTP 方法不在白名单",
    "url_https": "URL 非 https 开头",
    "src_ip_valid_ipv4": "源IP格式非法",
    "dst_ip_valid_ipv4": "目标IP格式非法",
    "user_agent_non_empty": "User-Agent 为空",
    "isin({'real', 'fake', 'anomaly'})": "身份标签非法",
    "in_range(100, 599)": "状态码不在 100–599",
    "in_range(1024, 65535)": "源端口超出 ephemeral 范围(1024-65535)",
    "isin([80, 443, 8080, 8443])": "目标端口非标准服务端口",
    "duration_non_negative": "duration 缺失或为负",
    "timestamp_not_future": "时间戳不合理(未来时间)",
    "header_is_dict": "header 非 JSON 对象",
    # business (dataframe checks)
    "get_no_body": "GET 请求不应带 body",
    "post_put_has_body": "POST/PUT 请求不应缺少 body",
    "delete_no_200_with_body": "DELETE 成功应为 204/404，不应返回 200 且带 body",
    "fake_has_script_ua": "标记为 fake 时 User-Agent 未体现脚本特征",
    "anomaly_has_features": "标记为 anomaly 但缺少异常特征",
    "rtt_non_negative": "RTT 为负或非法",
}


def _label_for(check_name: str) -> str:
    """Resolve a Pandera check name to a Chinese label."""
    # direct match first
    if check_name in _CHECK_LABELS:
        return _CHECK_LABELS[check_name]
    # try partial match for built-in checks like "isin({...})", "in_range(a, b)"
    for key, label in _CHECK_LABELS.items():
        if key in check_name or check_name in key:
            return label
    return check_name  # fallback: raw check name


def _records_to_df(records: list[TrafficRecord]) -> pd.DataFrame:
    df = pd.DataFrame([r.model_dump() for r in records])
    # Pandera expects datetime64[ns]; pandas 3.x creates datetime64[us, UTC]
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None).astype("datetime64[ns]")
    return df


def _check_to_failure_count(
    df: pd.DataFrame,
    schema: pa.DataFrameSchema,
) -> tuple[list[str], int, int]:
    """Run *lazy* validation and return (notes, passed, total)."""
    notes: list[str] = []
    try:
        schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        fc = exc.failure_cases
        schema_name = schema.name or ""
        # Track dataframe-check failures (column == schema name) by (index, check)
        df_failures: set[tuple[int, str]] = set()
        for _, row in fc.iterrows():
            raw_idx = row.get("index", -1)
            idx = int(raw_idx) if pd.notna(raw_idx) else -1
            col = str(row.get("column", "?"))
            chk = str(row.get("check", "?"))
            label = _label_for(chk)
            prefix = f"记录 {idx + 1}：" if idx >= 0 else ""
            # Dataframe-level checks: column == schema class name
            if col == schema_name:
                key = (idx, chk)
                if key in df_failures:
                    continue
                df_failures.add(key)
                notes.append(f"{prefix}{label}")
            else:
                notes.append(f"{prefix}{label}")
    # count: column checks + dataframe checks, per row
    col_checks_per_row = sum(len(col.checks) for col in schema.columns.values())
    df_checks_per_row = len(schema.checks)
    total_checks = (col_checks_per_row + df_checks_per_row) * max(len(df), 1)
    if total_checks == 0:
        total_checks = 1
    passed_checks = total_checks - len(notes)
    return notes, passed_checks, total_checks


# ---------------------------------------------------------------------------
# Pandera schemas
# ---------------------------------------------------------------------------

class TrafficFormatSchema(pa.DataFrameModel):
    """Per-field format / validity checks for traffic records."""

    # -- string fields -------------------------------------------------------
    id: str = pa.Field(nullable=False)

    @pa.check("id", name="id_non_empty")
    @classmethod
    def id_not_empty(cls, s: Series[str]) -> Series[bool]:
        return s.str.strip().str.len() > 0

    method: str = pa.Field(isin={"GET", "POST", "PUT", "DELETE"})

    url: str = pa.Field()

    @pa.check("url", name="url_https")
    @classmethod
    def url_starts_https(cls, s: Series[str]) -> Series[bool]:
        return s.str.startswith("https://")

    src_ip: str = pa.Field()

    @pa.check("src_ip", name="src_ip_valid_ipv4")
    @classmethod
    def src_ip_valid(cls, s: Series[str]) -> Series[bool]:
        return s.apply(lambda ip: bool(_IPV4_RE.match(ip) and all(0 <= int(g) <= 255 for g in _IPV4_RE.match(ip).groups())) if _IPV4_RE.match(ip) else False)

    dst_ip: str = pa.Field()

    @pa.check("dst_ip", name="dst_ip_valid_ipv4")
    @classmethod
    def dst_ip_valid(cls, s: Series[str]) -> Series[bool]:
        return s.apply(lambda ip: bool(_IPV4_RE.match(ip) and all(0 <= int(g) <= 255 for g in _IPV4_RE.match(ip).groups())) if _IPV4_RE.match(ip) else False)

    user_agent: str = pa.Field(nullable=True)

    @pa.check("user_agent", name="user_agent_non_empty")
    @classmethod
    def ua_not_empty(cls, s: Series[str]) -> Series[bool]:
        return s.fillna("").str.strip().str.len() > 0

    identity_label: str = pa.Field(isin={"real", "fake", "anomaly"})

    referer: str | None = pa.Field(nullable=True)

    # -- integer fields ------------------------------------------------------
    status_code: int = pa.Field(in_range={"min_value": 100, "max_value": 599})

    src_port: int = pa.Field(in_range={"min_value": 1024, "max_value": 65535})

    dst_port: int = pa.Field(isin=list(_VALID_DST_PORTS))

    # -- float fields --------------------------------------------------------
    duration: float | None = pa.Field(nullable=True)

    @pa.check("duration", name="duration_non_negative")
    @classmethod
    def duration_ge_0(cls, s: Series[float]) -> Series[bool]:
        return s.fillna(0.0) >= 0.0

    rtt: float | None = pa.Field(nullable=True)

    # -- datetime ------------------------------------------------------------
    timestamp: datetime

    @pa.check("timestamp", name="timestamp_not_future")
    @classmethod
    def ts_not_future(cls, s: Series[datetime]) -> Series[bool]:
        limit = datetime.now(timezone.utc) + timedelta(days=1)
        return s <= limit

    # -- object (dict) columns -----------------------------------------------
    header: object

    @pa.check("header", name="header_is_dict")
    @classmethod
    def header_dict(cls, s: Series[Any]) -> Series[bool]:
        return s.apply(lambda x: isinstance(x, dict))

    req_body: object | None = pa.Field(nullable=True)
    resp_body: object | None = pa.Field(nullable=True)


class TrafficBusinessSchema(pa.DataFrameModel):
    """Cross-field business-consistency checks."""

    method: str
    url: str
    status_code: int
    req_body: object | None = pa.Field(nullable=True)
    resp_body: object | None = pa.Field(nullable=True)
    user_agent: str | None = pa.Field(nullable=True)
    identity_label: str
    rtt: float | None = pa.Field(nullable=True)
    duration: float | None = pa.Field(nullable=True)
    src_port: int
    dst_port: int

    @pa.dataframe_check(name="get_no_body")
    @classmethod
    def get_no_body(cls, df: pd.DataFrame) -> Series[bool]:
        return (df["method"] != "GET") | df["req_body"].isna()

    @pa.dataframe_check(name="post_put_has_body")
    @classmethod
    def post_has_body(cls, df: pd.DataFrame) -> Series[bool]:
        return ~df["method"].isin(["POST", "PUT"]) | df["req_body"].notna()

    @pa.dataframe_check(name="delete_no_200_with_body")
    @classmethod
    def delete_status_ok(cls, df: pd.DataFrame) -> Series[bool]:
        return (df["method"] != "DELETE") | ~((df["status_code"] == 200) & df["resp_body"].notna())

    @pa.dataframe_check(name="fake_has_script_ua")
    @classmethod
    def fake_script_ua(cls, df: pd.DataFrame) -> Series[bool]:
        def _check(row: pd.Series) -> bool:
            if row["identity_label"] != "fake":
                return True
            ua = str(row.get("user_agent", "") or "").lower()
            return any(tok in ua for tok in _SCRIPT_UA_TOKENS)
        return df.apply(_check, axis=1)

    @pa.dataframe_check(name="anomaly_has_features")
    @classmethod
    def anomaly_features(cls, df: pd.DataFrame) -> Series[bool]:
        def _check(row: pd.Series) -> bool:
            if row["identity_label"] != "anomaly":
                return True
            return any([
                row["status_code"] >= 500,
                row["status_code"] == 0,
                row["rtt"] is not None and row["rtt"] > 5000,
                row["duration"] is not None and row["duration"] > 10000,
                row["src_port"] < 1024,
                row["dst_port"] not in _VALID_DST_PORTS,
            ])
        return df.apply(_check, axis=1)

    @pa.dataframe_check(name="rtt_non_negative")
    @classmethod
    def rtt_non_negative(cls, df: pd.DataFrame) -> Series[bool]:
        return df["rtt"].isna() | (df["rtt"] >= 0)


# ---------------------------------------------------------------------------
# adapter: same (score, notes) contract as old hand-written functions
# ---------------------------------------------------------------------------

def validate_format(records: list[TrafficRecord]) -> tuple[float, list[str]]:
    """Pandera-backed format validation → (score, notes)."""
    if not records:
        return 0.0, ["无记录可评"]
    df = _records_to_df(records)
    schema = TrafficFormatSchema.to_schema()
    notes, passed, total = _check_to_failure_count(df, schema)
    score = round(passed / total * 100, 1)
    return score, dedupe_notes(notes)


def validate_business(records: list[TrafficRecord], industry: str) -> tuple[float, list[str]]:
    """Pandera-backed business-consistency validation → (score, notes)."""
    if not records:
        return 0.0, ["无记录可评"]
    df = _records_to_df(records)
    schema = TrafficBusinessSchema.to_schema()
    notes, passed, total = _check_to_failure_count(df, schema)

    # --- industry-specific URL / path checks (not in schema) ---
    from app.services.generator import _industry_paths  # avoid circular import

    known_paths = _industry_paths().get(industry, [])
    extra_notes: list[str] = []
    extra_checks_total = 0
    extra_checks_passed = 0

    for i, (_, row) in enumerate(df.iterrows()):
        prefix = f"记录 {i + 1}：" if len(records) > 1 else ""
        url = str(row["url"])
        if industry == "custom":
            ok = url.startswith("https://")
            extra_checks_total += 1
            if not ok:
                extra_notes.append(f"{prefix}行业 custom 时 URL 须为 https 开头")
            else:
                extra_checks_passed += 1
        else:
            ok = f"api.{industry}.com" in url
            extra_checks_total += 1
            if not ok:
                extra_notes.append(f"{prefix}URL 未包含该行业域 api.{industry}.com")
            else:
                extra_checks_passed += 1
        if known_paths:
            extra_checks_total += 1
            if any(path in url for path in known_paths):
                extra_checks_passed += 1
            else:
                extra_notes.append(
                    f"{prefix}未命中该行业常见路径 {known_paths[:3]}{'…' if len(known_paths) > 3 else ''}"
                )

    total_all = total + extra_checks_total
    passed_all = passed + extra_checks_passed
    all_notes = notes + extra_notes
    score = round(passed_all / max(total_all, 1) * 100, 1)
    return score, dedupe_notes(all_notes)



