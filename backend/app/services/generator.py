import asyncio
import csv
import json
import random
import uuid
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from langchain_ollama import ChatOllama

from app.core.config import settings
from app.models.schemas import QualityScore, Stage, TrafficRecord


def _fix_json(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("Empty content")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text)
        text = text.strip("`")
    text = text.replace("'", '"')
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def infer_scenario(industry: str) -> str:
    mapping = {
        "government": "工作日办公时间",
        "ecommerce": "全天候配送",
        "short_video": "内容创作时段",
        "ride_hailing": "通勤高峰",
        "logistics": "夜间运输",
        "delivery": "饭点高峰",
        "finance": "交易高峰",
        "healthcare": "门诊就诊时段",
        "media": "晚间播放高峰",
        "social": "内容互动高峰",
        "gaming": "在线对战时段",
    }
    scenario = mapping.get(industry, "自定义场景")
    logger.info(f"推断场景: industry={industry} -> scenario={scenario}")
    return scenario


def _industry_context(industry: str) -> str:
    mapping = {
        "government": "政务办公、审批流转、用户资料查询",
        "ecommerce": "商品浏览、购物车、订单创建、库存查询",
        "short_video": "视频推荐、点赞评论、创作者上传",
        "ride_hailing": "司机定位、订单匹配、支付结算",
        "logistics": "运单创建、轨迹查询、车辆定位",
        "delivery": "骑手状态、取餐派送、订单更新",
        "finance": "账户查询、支付转账、风控校验、交易确认",
        "healthcare": "预约挂号、电子病历、检查报告、影像查询",
        "media": "播放鉴权、CDN 分片、观看进度、推荐列表",
        "social": "动态信息流、关注关系、私信、图片上传",
        "gaming": "登录鉴权、匹配队列、战斗同步、心跳上报",
    }
    return mapping.get(industry, "自定义业务接口")


def _random_ip() -> str:
    return f"192.168.{random.randint(1, 255)}.{random.randint(1, 255)}"


def _random_port() -> int:
    return random.randint(1024, 65535)


def _random_url(industry: str) -> str:
    paths = _industry_paths()
    path = random.choice(paths.get(industry, ["/api/endpoint"]))
    return f"https://api.{industry}.com{path}"


def _industry_paths() -> dict[str, list[str]]:
    return {
        "government": ["/api/office/doc", "/api/approval/send", "/api/user/info"],
        "ecommerce": ["/api/product/list", "/api/order/create", "/api/cart/add"],
        "short_video": ["/api/video/feed", "/api/like", "/api/comment/list"],
        "ride_hailing": ["/api/driver/location", "/api/order/match", "/api/payment"],
        "logistics": ["/api/track/query", "/api/waybill/create", "/api/truck/position"],
        "delivery": ["/api/order/pickup", "/api/rider/status", "/api/delivery/update"],
        "finance": ["/api/account/balance", "/api/payment/transfer", "/api/risk/check"],
        "healthcare": ["/api/appointment/book", "/api/emr/detail", "/api/report/query"],
        "media": ["/api/play/auth", "/api/cdn/segment", "/api/watch/progress"],
        "social": ["/api/feed/timeline", "/api/relation/follow", "/api/message/send"],
        "gaming": ["/api/matchmaking/join", "/api/battle/sync", "/api/player/heartbeat"],
    }


def _random_body(industry: str) -> dict[str, Any]:
    bodies = {
        "government": {"doc_id": str(uuid.uuid4()), "approval_step": random.randint(1, 5)},
        "ecommerce": {"sku_id": f"SKU{random.randint(10000, 99999)}", "quantity": random.randint(1, 5)},
        "short_video": {"video_id": str(uuid.uuid4()), "action": random.choice(["like", "comment", "share"])},
        "ride_hailing": {"order_id": str(uuid.uuid4()), "city_code": random.choice(["010", "021", "0755"])},
        "logistics": {"waybill_no": f"WB{random.randint(100000, 999999)}", "truck_id": f"TRK{random.randint(100, 999)}"},
        "delivery": {"order_id": str(uuid.uuid4()), "rider_id": random.randint(10000, 99999)},
        "finance": {"account_id": random.randint(100000, 999999), "amount": round(random.uniform(10, 5000), 2)},
        "healthcare": {"patient_id": random.randint(100000, 999999), "department": random.choice(["cardiology", "radiology", "general"])},
        "media": {"asset_id": str(uuid.uuid4()), "bitrate": random.choice([720, 1080, 2160])},
        "social": {"post_id": str(uuid.uuid4()), "visibility": random.choice(["public", "friends", "private"])},
        "gaming": {"player_id": random.randint(100000, 999999), "room_id": f"room-{random.randint(1000, 9999)}"},
    }
    return bodies.get(industry, {"request_id": str(uuid.uuid4())})


def _random_header(is_script: bool) -> dict:
    if is_script:
        return {
            "Content-Type": random.choice(["application/json", "application/x-www-form-urlencoded"]),
            "Accept": "application/json",
            "User-Agent": random.choice([
                "python-requests/2.28.0",
                "python-urllib/3.10",
                "Go-http-client/1.18",
                "curl/7.68.0",
                "Scrapy/2.7.1 (+https://scrapy.org)",
                "Python/3.10 requests/2.31.0",
            ]),
        }
    return {
        "Content-Type": random.choice(["application/json", "application/x-www-form-urlencoded"]),
        "Accept": "application/json",
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]),
    }


def _get_examples() -> list[dict[str, Any]]:
    return [
        {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "method": "GET",
            "url": "https://api.ecommerce.com/api/product/list?page=1&size=20",
            "status_code": 200,
            "timestamp": "2026-04-18T10:30:00+00:00",
            "src_ip": "192.168.1.105",
            "src_port": 54321,
            "dst_ip": "10.0.0.10",
            "dst_port": 443,
            "header": {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            "req_body": None,
            "resp_body": {"code": 0, "message": "success", "data": {"products": []}},
            "rtt": 125.5,
            "duration": 180.2,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "referer": "https://ecommerce.com/",
            "identity_label": "real",
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440002",
            "method": "POST",
            "url": "https://api.ecommerce.com/api/order/create",
            "status_code": 200,
            "timestamp": "2026-04-18T10:30:15+00:00",
            "src_ip": "192.168.1.108",
            "src_port": 12345,
            "dst_ip": "10.0.0.12",
            "dst_port": 443,
            "header": {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "python-requests/2.28.0"},
            "req_body": {"sku_id": "SKU12345", "quantity": 2, "user_id": 10001},
            "resp_body": {"code": 0, "message": "order created", "order_id": "ORD20260418001"},
            "rtt": 89.3,
            "duration": 150.8,
            "user_agent": "python-requests/2.28.0",
            "referer": None,
            "identity_label": "fake",
        },
    ]


def _get_llm_timeout() -> int:
    """获取 LLM 调用超时时间（秒）"""
    return getattr(settings, "llm_timeout", 300)


def generate_records_by_llm(count: int, stage: Stage, industry: str, scenario: str) -> list[TrafficRecord]:
    """生成流量记录（同步函数，用于 LangGraph 节点）"""
    try:
        logger.info(f"开始调用LLM生成流量: count={count}, industry={industry}, scenario={scenario}")

        examples = _get_examples()
        examples_str = "\n".join([json.dumps(e, ensure_ascii=False) for e in examples])

        system_prompt = f"""你是网络流量数据生成助手。根据以下行业和场景信息，生成真实的流量数据。

行业: {industry}
场景: {scenario}
典型接口特征: {_industry_context(industry)}

输出格式要求:
生成 {count} 条流量记录，每条包含以下字段:
- id: UUID格式字符串
- method: HTTP方法 (GET/POST/PUT/DELETE)
- url: 完整的HTTPS URL
- status_code: HTTP状态码
- timestamp: ISO格式时间
- src_ip: 客户端IP (192.168.x.x)
- src_port: 客户端端口 (1024-65535)
- dst_ip: 服务端IP (10.0.x.x)
- dst_port: 服务端端口 (80/443/8080/8443)
- header: HTTP请求头 (JSON格式)
- req_body: 请求体 (JSON格式，可为null)
- resp_body: 响应体 (JSON格式)
- rtt: 往返时延(毫秒，可为null)
- duration: 请求耗时(毫秒)
- user_agent: User-Agent字符串
- referer: Referer头 (可为null)
- identity_label: 身份标签 (real=真人, fake=自动化脚本)

重要要求:
1. 约25%流量为自动化脚本(fake)，User-Agent包含python/go/curl/scrapy
2. 约75%为正常浏览器流量(real)
3. 直接输出JSON数组，不要其他文字

参考样例:
{examples_str}"""

        llm = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.3,
            timeout=_get_llm_timeout(),
        )

        response = llm.invoke(f"{system_prompt}\n\n请生成流量数据")
        content = getattr(response, "content", "")

        if not content:
            raise ValueError("LLM返回为空")

        try:
            result = json.loads(content.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败，尝试修复: {e}")
            fixed = _fix_json(content.strip())
            result = json.loads(fixed)

        if not isinstance(result, list):
            result = [result]

        now = datetime.now(timezone.utc)
        records = []
        for i, item in enumerate(result[:count]):
            record = TrafficRecord(
                id=item.get("id", str(uuid.uuid4())),
                method=item.get("method", "GET"),
                url=item.get("url", "https://api.example.com/test"),
                status_code=item.get("status_code", 200),
                timestamp=datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")) if item.get("timestamp") else now - timedelta(seconds=i),
                src_ip=item.get("src_ip", _random_ip()),
                src_port=item.get("src_port", _random_port()),
                dst_ip=item.get("dst_ip", f"10.0.{random.randint(1, 255)}.{random.randint(1, 255)}"),
                dst_port=item.get("dst_port", 443),
                header=item.get("header", {}),
                req_body=item.get("req_body"),
                resp_body=item.get("resp_body"),
                rtt=item.get("rtt"),
                duration=item.get("duration"),
                user_agent=item.get("user_agent", "Mozilla/5.0"),
                referer=item.get("referer"),
                identity_label=item.get("identity_label", "real"),
            )
            records.append(record)

        real_count = sum(1 for r in records if r.identity_label == "real")
        fake_count = sum(1 for r in records if r.identity_label == "fake")
        logger.info(f"LLM流量生成完成: 共 {len(records)} 条, 真实 {real_count} 条, 脚本 {fake_count} 条")

        return records
    except Exception as e:
        logger.exception(f"LLM生成流量失败: {e}")
        raise RuntimeError(f"LLM生成流量失败: {e}") from e


def generate_records(count: int, stage: Stage, industry: str) -> list[TrafficRecord]:
    now = datetime.now(timezone.utc)
    is_script = random.random() < 0.25
    identity = "fake" if is_script else ("real" if stage != Stage.quick else "anomaly")
    methods = ["GET", "POST", "PUT", "DELETE"]
    status_codes = [200, 201, 400, 401, 403, 404, 500] if identity != "fake" else [200, 400, 500]
    result: list[TrafficRecord] = []
    for i in range(count):
        is_script = random.random() < 0.25
        is_script_record = is_script
        identity_label = "fake" if is_script_record else ("real" if stage != Stage.quick else "anomaly")
        result.append(
            TrafficRecord(
                id=str(uuid.uuid4()),
                method=random.choice(methods),
                url=_random_url(industry),
                status_code=random.choice(status_codes),
                timestamp=now - timedelta(seconds=i * 15),
                src_ip=_random_ip(),
                src_port=_random_port(),
                dst_ip=f"10.0.{random.randint(1, 255)}.{random.randint(1, 255)}",
                dst_port=random.choice([80, 443, 8080, 8443]),
                header=_random_header(is_script_record),
                req_body=_random_body(industry) if random.random() > 0.3 else None,
                resp_body={"code": random.randint(0, 1), "message": "success"} if random.random() > 0.3 else None,
                rtt=round(random.uniform(10, 500), 2) if random.random() > 0.5 else None,
                duration=round(random.uniform(50, 2000), 2),
                user_agent=random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                ]) if not is_script_record else random.choice([
                    "python-requests/2.28.0",
                    "python-urllib/3.10",
                    "Go-http-client/1.18",
                    "curl/7.68.0",
                    "Scrapy/2.7.1 (+https://scrapy.org)",
                    "Python/3.10 requests/2.31.0",
                ]),
                referer=f"https://{industry}.com/" if random.random() > 0.5 else None,
                identity_label=identity_label,
            )
        )
    return result


def _score_format(records: list[TrafficRecord]) -> float:
    if not records:
        return 0

    checks = []
    for record in records:
        checks.extend(
            [
                bool(record.id),
                record.method in {"GET", "POST", "PUT", "DELETE"},
                record.url.startswith("https://"),
                100 <= record.status_code <= 599,
                record.src_port > 0,
                record.dst_port > 0,
                isinstance(record.header, dict),
                record.duration is not None and record.duration >= 0,
                bool(record.user_agent),
                record.identity_label in {"real", "fake", "anomaly"},
            ]
        )

    return round(sum(1 for item in checks if item) / len(checks) * 100, 1)


def _score_business(records: list[TrafficRecord], industry: str) -> float:
    if not records:
        return 0

    known_paths = _industry_paths().get(industry, [])
    checks = []
    for record in records:
        checks.append(f"api.{industry}.com" in record.url if industry != "custom" else record.url.startswith("https://"))
        if known_paths:
            checks.append(any(path in record.url for path in known_paths))
        checks.append(record.method != "GET" or record.req_body is None)
        checks.append(record.identity_label != "fake" or any(token in (record.user_agent or "").lower() for token in ["python", "curl", "go", "scrapy"]))
        checks.append(record.rtt is None or record.rtt >= 0)

    return round(sum(1 for item in checks if item) / len(checks) * 100, 1)


def _score_diversity(records: list[TrafficRecord]) -> float:
    if not records:
        return 0

    count = len(records)

    def ratio(values: set[Any], expected: int) -> float:
        return min(len(values) / max(1, min(count, expected)), 1.0)

    url_score = ratio({record.url for record in records}, 3) * 40
    method_score = ratio({record.method for record in records}, 3) * 25
    status_score = ratio({record.status_code for record in records}, 3) * 20
    identity_score = ratio({record.identity_label for record in records}, 2) * 15
    return round(url_score + method_score + status_score + identity_score, 1)


def evaluate_quality(records: list[TrafficRecord], industry: str) -> QualityScore:
    logger.info("开始质量评估...")

    format_score = _score_format(records)
    logger.info(f"格式质量评分: {format_score}")

    business_score = _score_business(records, industry)
    logger.info(f"业务质量评分: {business_score}")

    diversity_score = _score_diversity(records)
    logger.info(f"多样性质量评分: {diversity_score}")

    total = round(format_score * 0.3 + business_score * 0.4 + diversity_score * 0.3, 1)
    logger.info(f"综合计算: 格式(30%*{format_score}) + 业务(40%*{business_score}) + 多样性(30%*{diversity_score}) = {total}")

    passed = total >= 70
    logger.info(f"质量评估完成，总分: {total}, 通过标准: >=70, 结果: {'通过' if passed else '未通过'}")

    return QualityScore(
        format_score=format_score,
        business_score=business_score,
        diversity_score=diversity_score,
        total_score=total,
        passed=passed,
    )


def write_csv(session_id: str, records: list[TrafficRecord], industry: str) -> str:
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"traffic_{industry}_{session_id}.csv"
    with file_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "id",
                "method",
                "url",
                "status_code",
                "timestamp",
                "src_ip",
                "src_port",
                "dst_ip",
                "dst_port",
                "header",
                "req_body",
                "resp_body",
                "rtt",
                "duration",
                "user_agent",
                "referer",
                "identity_label",
            ]
        )
        for row in records:
            writer.writerow(
                [
                    row.id,
                    row.method,
                    row.url,
                    row.status_code,
                    row.timestamp.isoformat(),
                    row.src_ip,
                    row.src_port,
                    row.dst_ip,
                    row.dst_port,
                    json.dumps(row.header, ensure_ascii=False),
                    json.dumps(row.req_body, ensure_ascii=False) if row.req_body else "",
                    json.dumps(row.resp_body, ensure_ascii=False) if row.resp_body else "",
                    row.rtt,
                    row.duration,
                    row.user_agent,
                    row.referer,
                    row.identity_label,
                ]
            )
    return str(file_path)


def write_traffic_json(
    session_id: str,
    records: list[TrafficRecord],
    industry: str,
    *,
    scenario: str,
    quality: QualityScore,
    stage: Stage,
) -> str:
    """Write a JSON bundle with metadata and records (for debugging and downstream tooling)."""
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"traffic_{industry}_{session_id}.json"
    created_at = datetime.now(timezone.utc).isoformat()
    body = {
        "metadata": {
            "session_id": session_id,
            "created_at": created_at,
            "industry": industry,
            "scenario": scenario,
            "stage": stage.value,
            "quality": quality.model_dump(),
            "total_records": len(records),
        },
        "records": [r.model_dump(mode="json") for r in records],
    }
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    return str(file_path)
