"""HTML report generation for traffic generation sessions."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from app.db.database import get_connection
from app.models.schemas import QualityScore, SessionStatus, Stage
from app.core.config import settings

_UTC = timezone.utc

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fmt_dt(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso[:19] if len(iso) >= 19 else iso

def _badge(status: str) -> str:
    colour = {
        "completed": "#22c55e", "failed": "#ef4444",
        "cancelled": "#f59e0b", "processing": "#3b82f6",
        "pending": "#6b7280",
    }
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
        f'background:{colour.get(status,"#6b7280")};color:#fff;font-size:13px;">'
        f'{status}</span>'
    )


def _chart_div(chart_id: str, height: int = 300) -> str:
    return f'<div id="{chart_id}" style="width:100%;height:{height}px;"></div>'


def _embed_data(varname: str, data: object) -> str:
    return f"<script>window.{varname} = {json.dumps(data, ensure_ascii=False)};</script>"


def _init_chart(chart_id: str, option_js: str) -> str:
    return (
        f"<script>document.addEventListener('DOMContentLoaded',function(){{"
        f"var c=echarts.init(document.getElementById('{chart_id}'));"
        f"c.setOption({option_js});"
        f"window.addEventListener('resize',function(){{c.resize();}});"
        f"}});</script>"
    )

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def generate_report_html(session_id: str) -> str | None:
    """Return a self-contained HTML report string for the given session, or None."""
    # 1. query session from DB
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id, industry, scenario, stage, status, requested_count,
               record_count, quality_score, quality_detail, trace_thread_id,
               error_message, started_at, completed_at, created_at, updated_at,
               file_path
            FROM traffic_sessions WHERE id = ?""",
            (session_id,),
        ).fetchone()

    if not row:
        return None

    status = SessionStatus(row["status"])
    stage = Stage(row["stage"]) if row["stage"] else None
    quality_detail: QualityScore | None = None
    if row["quality_detail"]:
        try:
            quality_detail = QualityScore.model_validate_json(row["quality_detail"])
        except (ValueError, TypeError):
            pass

    # 2. read records from JSON file (if exists)
    records: list[dict] = []
    file_path = row["file_path"]
    if file_path:
        json_path = Path(file_path).with_suffix(".json")
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                records = data.get("records", [])
            except (json.JSONDecodeError, OSError):
                pass

    # 3. compute statistics
    total_records = len(records)
    identity_counter = Counter(r.get("identity_label", "unknown") for r in records)
    method_counter = Counter(r.get("method", "?") for r in records)
    status_counter = Counter(str(r.get("status_code", "?")) for r in records)
    rtts = [r["rtt"] for r in records if r.get("rtt") is not None]
    avg_rtt = mean(rtts) if rtts else 0

    # 4. build HTML
    industry = row["industry"]
    scenario = row["scenario"] or "-"
    created_at = _fmt_dt(row["created_at"])
    started_at = _fmt_dt(row["started_at"])
    completed_at = _fmt_dt(row["completed_at"])
    quality_score = row["quality_score"] if "quality_score" in row.keys() else None

    # header
    real_cnt = identity_counter.get("real", 0)
    fake_cnt = identity_counter.get("fake", 0)
    anomaly_cnt = identity_counter.get("anomaly", 0)

    html_parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="UTF-8">',
        "<title>Traffic Agent 生成报告</title>",
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"></script>',
        "<style>",
        "*{box-sizing:border-box;margin:0;padding:0;}",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;",
        "  color:#1f2937;background:#f9fafb;padding:40px;}",
        ".report{max-width:860px;margin:0 auto;background:#fff;border-radius:12px;",
        "  box-shadow:0 1px 3px rgba(0,0,0,.1);padding:36px 40px;}",
        "h1{font-size:22px;margin-bottom:6px;}",
        "h2{font-size:17px;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid #e5e7eb;}",
        "h3{font-size:15px;margin:18px 0 8px;color:#4b5563;}",
        ".meta{color:#6b7280;font-size:13px;margin-bottom:24px;}",
        "table{width:100%;border-collapse:collapse;font-size:13px;}",
        "th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #f3f4f6;}",
        "th{background:#f9fafb;font-weight:600;color:#4b5563;}",
        "tr:hover{background:#fafafa;}",
        ".info-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;font-size:13px;}",
        ".info-grid dt{color:#6b7280;} .info-grid dd{font-weight:500;}",
        ".chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;",
        "  font-weight:500;}",
        ".chip-real{background:#dbeafe;color:#1d4ed8;}",
        ".chip-fake{background:#fef3c7;color:#b45309;}",
        ".chip-anomaly{background:#fee2e2;color:#dc2626;}",
        ".footer{margin-top:32px;padding-top:16px;border-top:1px solid #e5e7eb;",
        "  color:#9ca3af;font-size:12px;text-align:center;}",
        "@media print{body{background:#fff;padding:0;}",
        "  .report{box-shadow:none;border-radius:0;}}",
        "</style></head><body><div class='report'>",
        f"<h1>🚦 Traffic Agent 生成报告</h1>",
        f"<p class='meta'>生成时间：{created_at}</p>",

        # session info
        "<h2>会话信息</h2>",
        '<dl class="info-grid">',
        f"<dt>Session ID</dt><dd>{session_id}</dd>",
        f"<dt>行业</dt><dd>{industry}</dd>",
        f"<dt>场景</dt><dd>{scenario}</dd>",
        f"<dt>阶段</dt><dd>{stage.value if stage else '-'}</dd>",
        f"<dt>状态</dt><dd>{_badge(status.value)}</dd>",
        f"<dt>请求数量</dt><dd>{row['requested_count']}</dd>",
        f"<dt>生成数量</dt><dd>{total_records or row['record_count']}</dd>",
        f"<dt>质量评分</dt><dd>{quality_score if quality_score is not None else '-'}</dd>",
        f"<dt>开始时间</dt><dd>{started_at}</dd>",
        f"<dt>完成时间</dt><dd>{completed_at}</dd>",
        "</dl>",
    ]

    # error
    if row["error_message"]:
        html_parts.append(
            f'<div style="margin:12px 0;padding:10px;background:#fef2f2;'
            f'border-left:3px solid #ef4444;font-size:13px;color:#dc2626;">'
            f'<strong>错误信息：</strong>{row["error_message"]}</div>'
        )

    # quality detail
    if quality_detail:
        html_parts.append("<h2>质量评估</h2>")
        passed_text = "✅ 通过（≥70）" if quality_detail.passed else "❌ 未通过（<70）"
        html_parts.append(f'<p style="font-size:13px;margin-bottom:12px;">{passed_text}</p>')
        html_parts.append(_chart_div("chart-quality", 320))
        html_parts.append(_init_chart("chart-quality", (
            "{tooltip:{},radar:{indicator:["
            "{name:'格式评分',max:100},"
            "{name:'业务评分',max:100},"
            "{name:'多样性评分',max:100},"
            "{name:'综合评分',max:100}"
            "],shape:'circle',center:['50%','55%'],radius:'65%'},"
            "series:[{type:'radar',data:[{value:["
            f"{quality_detail.format_score},"
            f"{quality_detail.business_score},"
            f"{quality_detail.diversity_score},"
            f"{quality_detail.total_score}"
            "],name:'评分',areaStyle:{opacity:0.3}}]}]}"
        )))

        # dimension notes
        if quality_detail.format_notes:
            html_parts.append("<h3>格式维度扣分说明</h3><ul>")
            for note in quality_detail.format_notes:
                html_parts.append(f"<li style='font-size:13px;margin:2px 0;'>{note}</li>")
            html_parts.append("</ul>")
        if quality_detail.business_notes:
            html_parts.append("<h3>业务维度扣分说明</h3><ul>")
            for note in quality_detail.business_notes:
                html_parts.append(f"<li style='font-size:13px;margin:2px 0;'>{note}</li>")
            html_parts.append("</ul>")
        if quality_detail.diversity_notes:
            html_parts.append("<h3>多样性维度扣分说明</h3><ul>")
            for note in quality_detail.diversity_notes:
                html_parts.append(f"<li style='font-size:13px;margin:2px 0;'>{note}</li>")
            html_parts.append("</ul>")

    # identity distribution
    if total_records > 0:
        html_parts.append("<h2>身份分布</h2>")
        html_parts.append(_chart_div("chart-identity", 280))
        html_parts.append(_init_chart("chart-identity", (
            "{tooltip:{trigger:'item'},"
            "series:[{type:'pie',radius:['45%','70%'],center:['50%','55%'],"
            "label:{formatter:'{b}\\n{d}%'},"
            "data:["
            f"{{value:{real_cnt},name:'真实流量',itemStyle:{{color:'#3b82f6'}}}},"
            f"{{value:{fake_cnt},name:'脚本流量',itemStyle:{{color:'#f59e0b'}}}},"
            f"{{value:{anomaly_cnt},name:'异常流量',itemStyle:{{color:'#ef4444'}}}}"
            "]}]}"
        )))

    # http method distribution
    if method_counter:
        html_parts.append("<h2>HTTP 方法分布</h2>")
        html_parts.append(_chart_div("chart-methods", 250))
        methods_data = json.dumps([
            {"name": m, "value": c}
            for m, c in method_counter.most_common()
        ], ensure_ascii=False)
        html_parts.append(_init_chart("chart-methods", (
            "{tooltip:{trigger:'axis'},"
            f"xAxis:{{type:'category',data:{json.dumps([m for m,_ in method_counter.most_common()],ensure_ascii=False)}}},"
            "yAxis:{type:'value'},"
            f"series:[{{type:'bar',data:{json.dumps([c for _,c in method_counter.most_common()])},barWidth:'40%',"
            "itemStyle:{color:'#3b82f6',borderRadius:[4,4,0,0]}}}]}"
        )))

    # status code distribution
    if status_counter:
        html_parts.append("<h2>状态码分布</h2>")
        html_parts.append(_chart_div("chart-status", 250))
        codes = sorted(status_counter.keys(), key=lambda x: int(x))
        html_parts.append(_init_chart("chart-status", (
            "{tooltip:{trigger:'axis'},"
            f"xAxis:{{type:'category',data:{json.dumps(codes)}}},"
            "yAxis:{type:'value'},"
            f"series:[{{type:'bar',data:{json.dumps([status_counter[c] for c in codes])},barWidth:'40%',"
            "itemStyle:{color:'#22c55e',borderRadius:[4,4,0,0]}}}]}"
        )))

    # performance
    if rtts:
        html_parts.append("<h2>性能统计</h2>")
        html_parts.append(
            f'<p style="font-size:13px;margin:6px 0;">平均RTT: <strong>{avg_rtt:.2f} ms</strong>'
            f' &nbsp;|&nbsp; 最小: <strong>{min(rtts):.2f} ms</strong>'
            f' &nbsp;|&nbsp; 最大: <strong>{max(rtts):.2f} ms</strong></p>'
        )

    # sample records table
    if records:
        html_parts.append("<h2>样本记录（前10条）</h2>")
        html_parts.append(
            "<table><thead><tr>"
            "<th>#</th><th>方法</th><th>URL</th><th>状态码</th>"
            "<th>源IP</th><th>RTT(ms)</th><th>身份</th>"
            "</tr></thead><tbody>"
        )
        for i, r in enumerate(records[:10]):
            ident = r.get("identity_label", "-")
            chip_cls = f"chip chip-{ident}" if ident in ("real", "fake", "anomaly") else "chip"
            html_parts.append(
                f"<tr>"
                f"<td>{i + 1}</td>"
                f"<td>{r.get('method','-')}</td>"
                f"<td style='max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{r.get('url','-')}</td>"
                f"<td>{r.get('status_code','-')}</td>"
                f"<td>{r.get('src_ip','-')}</td>"
                f"<td>{r.get('rtt','-')}</td>"
                f"<td><span class='{chip_cls}'>{ident}</span></td>"
                f"</tr>"
            )
        html_parts.append("</tbody></table>")

    html_parts.append(
        "<div class='footer'>Traffic Agent &copy; "
        f"{datetime.now(_UTC).year} &mdash; 智能流量生成平台</div>"
        "</div></body></html>"
    )

    return "\n".join(html_parts)
