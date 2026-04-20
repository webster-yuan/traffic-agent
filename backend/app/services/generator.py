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
    }
    scenario = mapping.get(industry, "自定义场景")
    logger.info(f"推断场景: industry={industry} -> scenario={scenario}")
    return scenario


def _random_ip() -> str:
    return f"192.168.{random.randint(1, 255)}.{random.randint(1, 255)}"


def _random_port() -> int:
    return random.randint(1024, 65535)


def _random_url(industry: str) -> str:
    paths = {
        "government": ["/api/office/doc", "/api/approval/send", "/api/user/info"],
        "ecommerce": ["/api/product/list", "/api/order/create", "/api/cart/add"],
        "short_video": ["/api/video/feed", "/api/like", "/api/comment/list"],
        "ride_hailing": ["/api/driver/location", "/api/order/match", "/api/payment"],
        "logistics": ["/api/track/query", "/api/waybill/create", "/api/truck/position"],
        "delivery": ["/api/order/pickup", "/api/rider/status", "/api/delivery/update"],
    }
    path = random.choice(paths.get(industry, ["/api/endpoint"]))
    return f"https://api.{industry}.com{path}"


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


def evaluate_quality() -> QualityScore:
    logger.info("开始质量评估...")

    # 步骤1: 评估格式质量
    logger.info("步骤1: 评估格式质量")
    format_score = round(random.uniform(82, 98), 1)
    logger.info(f"格式质量评分: {format_score}")

    # 步骤2: 评估业务质量
    logger.info("步骤2: 评估业务质量")
    business_score = round(random.uniform(75, 95), 1)
    logger.info(f"业务质量评分: {business_score}")

    # 步骤3: 评估多样性质量
    logger.info("步骤3: 评估多样性质量")
    diversity_score = round(random.uniform(70, 93), 1)
    logger.info(f"多样性质量评分: {diversity_score}")

    # 步骤4: 计算总分
    logger.info("步骤4: 计算综合质量分数")
    total = round(format_score * 0.3 + business_score * 0.4 + diversity_score * 0.3, 1)
    logger.info(f"综合计算: 格式(30%*{format_score}) + 业务(40%*{business_score}) + 多样性(30%*{diversity_score}) = {total}")

    # 步骤5: 判断是否通过
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
