"""
Single source of truth for industry configuration.

All industry metadata (label, scenario, context, API paths) lives here.
Backend services import directly; frontend fetches via /api/v1/traffic/industries.

To add a new industry: add one entry to INDUSTRIES dict + add key to schemas.py Industry Literal.
"""

from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IndustryConfig:
    """Full industry configuration — single source of truth."""

    key: str
    label: str  # Chinese display name for UI
    scenario: str  # Default business scenario description
    context: str  # Business context summary for LLM prompts
    api_paths: list[str] = field(default_factory=list)  # Mock API paths
    body_template: dict[str, str] = field(default_factory=dict)  # Random request body templates


# ── Ordered list of all industry keys (drives UI order + Literal type) ──
INDUSTRY_KEYS: list[str] = [
    "government",
    "ecommerce",
    "short_video",
    "ride_hailing",
    "logistics",
    "delivery",
    "finance",
    "healthcare",
    "media",
    "social",
    "gaming",
    "custom",
]


# ── Complete industry registry ──
INDUSTRIES: dict[str, IndustryConfig] = {
    "government": IndustryConfig(
        key="government",
        label="政府机关",
        scenario="工作日办公时间",
        context="政务办公、审批流转、用户资料查询",
        api_paths=["/api/office/doc", "/api/approval/send", "/api/user/info"],
        body_template={"doc_id": "{uuid}", "approval_step": "{randint:1-5}"},
    ),
    "ecommerce": IndustryConfig(
        key="ecommerce",
        label="电商物流",
        scenario="全天候配送",
        context="商品浏览、购物车、订单创建、库存查询",
        api_paths=["/api/product/list", "/api/order/create", "/api/cart/add"],
        body_template={"sku_id": "SKU{randint:10000-99999}", "quantity": "{randint:1-5}"},
    ),
    "short_video": IndustryConfig(
        key="short_video",
        label="短视频",
        scenario="内容创作时段",
        context="视频推荐、点赞评论、创作者上传",
        api_paths=["/api/video/feed", "/api/like", "/api/comment/list"],
        body_template={"video_id": "{uuid}", "action": "{choice:like,comment,share}"},
    ),
    "ride_hailing": IndustryConfig(
        key="ride_hailing",
        label="网约车",
        scenario="通勤高峰",
        context="司机定位、订单匹配、支付结算",
        api_paths=["/api/driver/location", "/api/order/match", "/api/payment"],
        body_template={"order_id": "{uuid}", "city_code": "{choice:010,021,0755}"},
    ),
    "logistics": IndustryConfig(
        key="logistics",
        label="货运物流",
        scenario="夜间运输",
        context="运单创建、轨迹查询、车辆定位",
        api_paths=["/api/track/query", "/api/waybill/create", "/api/truck/position"],
        body_template={"waybill_no": "WB{randint:100000-999999}", "truck_id": "TRK{randint:100-999}"},
    ),
    "delivery": IndustryConfig(
        key="delivery",
        label="即时配送",
        scenario="饭点高峰",
        context="骑手状态、取餐派送、订单更新",
        api_paths=["/api/order/pickup", "/api/rider/status", "/api/delivery/update"],
        body_template={"order_id": "{uuid}", "rider_id": "{randint:10000-99999}"},
    ),
    "finance": IndustryConfig(
        key="finance",
        label="金融交易",
        scenario="交易高峰",
        context="账户查询、支付转账、风控校验、交易确认",
        api_paths=["/api/account/balance", "/api/payment/transfer", "/api/risk/check"],
        body_template={"account_id": "{randint:100000-999999}", "amount": "{uniform:10-5000-2}"},
    ),
    "healthcare": IndustryConfig(
        key="healthcare",
        label="医疗系统",
        scenario="门诊就诊时段",
        context="预约挂号、电子病历、检查报告、影像查询",
        api_paths=["/api/appointment/book", "/api/emr/detail", "/api/report/query"],
        body_template={"patient_id": "{randint:100000-999999}", "department": "{choice:cardiology,radiology,general}"},
    ),
    "media": IndustryConfig(
        key="media",
        label="流媒体",
        scenario="晚间播放高峰",
        context="播放鉴权、CDN 分片、观看进度、推荐列表",
        api_paths=["/api/play/auth", "/api/cdn/segment", "/api/watch/progress"],
        body_template={"asset_id": "{uuid}", "bitrate": "{choice:720,1080,2160}"},
    ),
    "social": IndustryConfig(
        key="social",
        label="社交媒体",
        scenario="内容互动高峰",
        context="动态信息流、关注关系、私信、图片上传",
        api_paths=["/api/feed/timeline", "/api/relation/follow", "/api/message/send"],
        body_template={"post_id": "{uuid}", "visibility": "{choice:public,friends,private}"},
    ),
    "gaming": IndustryConfig(
        key="gaming",
        label="游戏服务",
        scenario="在线对战时段",
        context="登录鉴权、匹配队列、战斗同步、心跳上报",
        api_paths=["/api/matchmaking/join", "/api/battle/sync", "/api/player/heartbeat"],
        body_template={"player_id": "{randint:100000-999999}", "room_id": "room-{randint:1000-9999}"},
    ),
    "custom": IndustryConfig(
        key="custom",
        label="自定义",
        scenario="自定义场景",
        context="自定义业务接口",
        api_paths=["/api/endpoint"],
        body_template={"request_id": "{uuid}"},
    ),
}


# ── Convenience accessors ──

def get_industry_config(key: str) -> IndustryConfig | None:
    """Get full config for an industry key. Returns None for unknown keys."""
    return INDUSTRIES.get(key)


def infer_scenario(key: str) -> str:
    """Infer scenario from industry key. Falls back to '自定义场景'."""
    cfg = INDUSTRIES.get(key)
    return cfg.scenario if cfg else "自定义场景"


def get_industry_context(key: str) -> str:
    """Get business context description for LLM prompt building."""
    cfg = INDUSTRIES.get(key)
    return cfg.context if cfg else "自定义业务接口"


def get_industry_paths(key: str) -> list[str]:
    """Get mock API paths for an industry."""
    cfg = INDUSTRIES.get(key)
    return cfg.api_paths if cfg else ["/api/endpoint"]


def get_industries_for_frontend() -> list[dict[str, str]]:
    """Return simplified industry list for the frontend API."""
    return [
        {"key": cfg.key, "label": cfg.label, "scenario": cfg.scenario}
        for cfg in INDUSTRIES.values()
    ]


# ── Body template renderer ──

_TEMPLATE_RE = re.compile(r"\{(\w+)(?::(.+?))?\}")


def _render_template_value(template: str) -> Any:
    """Render a single template string into a concrete value.

    Supported placeholders:
        {uuid}              → str(uuid.uuid4())
        {randint:min-max}   → random.randint(min, max)
        {choice:a,b,c}      → random.choice([a, b, c])
        {uniform:min-max-d} → round(random.uniform(min, max), d)
    """
    parts: list[str] = []
    result_type: str = "string"  # 'string' | 'int' | 'float'
    last_end = 0
    prefix_empty = True  # True if all text before first placeholder is empty

    for m in _TEMPLATE_RE.finditer(template):
        prefix = template[last_end:m.start()]
        parts.append(prefix)
        if prefix:
            prefix_empty = False
        kind = m.group(1)
        args_str = m.group(2) or ""

        if kind == "uuid":
            parts.append(str(uuid.uuid4()))
        elif kind == "randint":
            lo, hi = args_str.split("-", 1)
            val = str(random.randint(int(lo), int(hi)))
            parts.append(val)
            result_type = "int" if prefix_empty else result_type
        elif kind == "choice":
            options = [o for o in args_str.split(",")]
            parts.append(random.choice(options))
        elif kind == "uniform":
            lo, hi, dp = args_str.split("-", 2)
            parts.append(str(round(random.uniform(float(lo), float(hi)), int(dp))))
            result_type = "float" if prefix_empty else result_type
        else:
            parts.append(m.group(0))  # unknown → keep literal

        last_end = m.end()

    parts.append(template[last_end:])
    result = "".join(parts)

    # If the ENTIRE value was a single placeholder, return the native type
    if len(parts) == 2 and parts[0] == "" and result_type == "int":
        return int(result)
    if len(parts) == 2 and parts[0] == "" and result_type == "float":
        return float(result)
    return result


def get_random_body(industry: str) -> dict[str, Any]:
    """Generate a random request body for the given industry.

    Uses the declarative ``body_template`` from IndustryConfig
    so that adding a new industry only requires touching this file.
    """
    cfg = INDUSTRIES.get(industry)
    if not cfg or not cfg.body_template:
        return {"request_id": str(uuid.uuid4())}
    return {k: _render_template_value(v) for k, v in cfg.body_template.items()}
