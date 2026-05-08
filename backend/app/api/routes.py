import asyncio
import json
import time
import uuid
import logging
from datetime import date
from pathlib import Path
from typing import Any, AsyncGenerator, Literal

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from app.models.schemas import (
    BatchGenerateRequest,
    BatchStatusResponse,
    BatchTaskStatus,
    CheckpointItem,
    CheckpointListResponse,
    SessionStatus,
    Stage,
    TrafficGenerateRequest,
    TrafficGenerateResponse,
    TrafficReplayRequest,
    TrafficResumeRequest,
)
from app.graph.workflow import get_traffic_graph
from app.services.generator import write_csv, write_traffic_json, write_traffic_parquet
from app.services.graph_runner import (
    build_initial_state,
    replay_from_checkpoint,
    run_generation_graph_async as run_graph,
)
from app.services.tracing_config import build_graph_config
from app.services.session_service import (
    add_batch_task,
    complete_session,
    create_batch,
    create_session,
    delete_session,
    fail_session,
    get_batch_tasks,
    get_session_file,
    list_history,
    update_batch_task_status,
    update_status,
)
from app.services.report_service import generate_report_html
from app.data.industries import get_industries_for_frontend
from app.core.state import add_cancelled, is_cancelled, remove_cancelled
from app.services.system_metrics import get_metrics
from app.services.token_counter import get_token_counter

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])

_semaphore = asyncio.Semaphore(3)


async def _acquire() -> None:
    await _semaphore.acquire()


def _release() -> None:
    _semaphore.release()


@router.post("/generate", response_model=TrafficGenerateResponse)
async def generate_traffic(payload: TrafficGenerateRequest) -> TrafficGenerateResponse:
    await _acquire()
    start_at = time.perf_counter()
    session_id = uuid.uuid4().hex[:12]
    graph_config = build_graph_config(session_id=session_id, payload=payload)
    await create_session(
        session_id=session_id,
        industry=payload.industry,
        scenario="",
        stage=payload.stage,
        status=SessionStatus.processing,
        requested_count=payload.count,
        record_count=0,
        quality_score=None,
        file_path=None,
        trace_thread_id=graph_config["configurable"]["thread_id"],
        trace_metadata=graph_config["metadata"],
    )
    try:
        graph_result = await run_graph(session_id=session_id, payload=payload)
        scenario = graph_result["scenario"]
        quality = graph_result["quality_score"]
        records = graph_result["generated_records"]
        file_path = write_csv(session_id, records, payload.industry)
        write_traffic_json(
            session_id,
            records,
            payload.industry,
            scenario=scenario,
            quality=quality,
            stage=payload.stage,
        )
        write_traffic_parquet(session_id, records, payload.industry)
        await complete_session(
            session_id=session_id,
            scenario=scenario,
            record_count=len(records),
            file_path=file_path,
            quality=quality,
        )
        # ── Record metrics ────────────────────────────────────────────
        processing_time = int((time.perf_counter() - start_at) * 1000)
        get_metrics().record_request(
            session_id=session_id,
            industry=payload.industry,
            stage=payload.stage.value,
            record_count=len(records),
            processing_time_ms=processing_time,
            success=True,
        )
        return TrafficGenerateResponse(
            success=True,
            session_id=session_id,
            total_count=len(records),
            quality_score=quality,
            generated_data=records,
            processing_time_ms=processing_time,
        )
    except GraphInterrupt as gi:
        # Human-in-the-Loop: graph paused — non-streaming mode cannot handle this
        # Return a response indicating approval is needed
        interrupt_data = gi.value if hasattr(gi, 'value') else gi.args[0] if gi.args else {}
        await update_status(session_id, SessionStatus.processing)
        _release()
        return TrafficGenerateResponse(
            success=False,
            session_id=session_id,
            total_count=0,
            quality_score=None,
            generated_data=[],
            processing_time_ms=int((time.perf_counter() - start_at) * 1000),
        )
    except Exception as e:
        logger.exception("session_id=%s generation failed", session_id)
        get_metrics().record_request(
            session_id=session_id,
            industry=payload.industry,
            stage=payload.stage.value,
            record_count=0,
            processing_time_ms=int((time.perf_counter() - start_at) * 1000),
            success=False,
            error=str(e),
        )
        await fail_session(session_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        _release()


@router.post("/generate/stream")
async def generate_traffic_stream(payload: TrafficGenerateRequest) -> StreamingResponse:
    logger.info("Stream request received: industry=%s, stage=%s, count=%s", payload.industry, payload.stage, payload.count)
    await _acquire()
    session_id = uuid.uuid4().hex[:12]
    graph_config = build_graph_config(session_id=session_id, payload=payload)
    await create_session(
        session_id=session_id,
        industry=payload.industry,
        scenario="",
        stage=payload.stage,
        status=SessionStatus.processing,
        requested_count=payload.count,
        record_count=0,
        quality_score=None,
        file_path=None,
        trace_thread_id=graph_config["configurable"]["thread_id"],
        trace_metadata=graph_config["metadata"],
    )
    logger.info("session_id=%s lock acquired", session_id)

    async def event_stream() -> AsyncGenerator[str, None]:
        stream_start = time.perf_counter()
        try:
            logger.info("session_id=%s started stream processing", session_id)
            graph = get_traffic_graph()
            logger.info("session_id=%s graph instance acquired", session_id)
            
            stage_name_map = {
                "rag": "RAG检索",
                "generate": "流量生成",
                "eval": "质量评估",
                "identity": "身份校验",
                "approval": "人工审核",
            }
            stage_progress_map = {
                "rag": 25,
                "generate": 60,
                "eval": 82,
                "identity": 92,
                "approval": 95,
            }
            seen_start: set[str] = set()
            stage_started_at: dict[str, float] = {}
            final_state: dict | None = None

            # Send start event
            yield f"event: start\ndata: {{\"session_id\": \"{session_id}\"}}\n\n"
            logger.info("session_id=%s start event sent", session_id)

            # Build initial state
            initial_state = build_initial_state(session_id=session_id, payload=payload)
            logger.info("session_id=%s initial state built: industry=%s, stage=%s, count=%s", session_id, payload.industry, payload.stage, payload.count)

            # Listen to graph event stream (P3.3 — stream_mode=custom for progress)
            logger.info("session_id=%s listening to graph event stream", session_id)
            event_count = 0
            async for (mode, data) in graph.astream(
                initial_state,
                config=graph_config,
                stream_mode=["updates", "custom"],
            ):
                event_count += 1

                # ── Custom events from get_stream_writer() ─────────────
                if mode == "custom":
                    evt_type = data.get("type", "") if isinstance(data, dict) else ""

                    if evt_type == "stage_start":
                        node = data.get("node", "")
                        if node not in seen_start:
                            seen_start.add(node)
                            stage_started_at[node] = time.perf_counter()
                            logger.info(f"session_id={session_id} 阶段开始: {node}")
                            yield (
                                "event: stage_start\n"
                                f"data: {json.dumps({'stage': node, 'name': data.get('name', node), 'progress': stage_progress_map.get(node, max(stage_progress_map.get(node, 15) - 15, 10))}, ensure_ascii=False, separators=(',', ':'))}\n\n"
                            )

                    elif evt_type == "thought":
                        yield (
                            "event: thought\n"
                            f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
                        )

                    elif evt_type == "generate_progress":
                        yield (
                            "event: generate_progress\n"
                            f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
                        )

                    elif evt_type == "token_usage":
                        yield (
                            "event: token_usage\n"
                            f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
                        )

                    continue

                # ── mode == "updates" — node output (replaces on_chain_end) ──
                # data is a dict like {"supervisor": {...}} — iterate over entries
                for node_name, state_update in data.items():

                    # ── HITL: detect interrupt in stream ────────────────────
                    # LangGraph's astream() suppresses GraphInterrupt and emits
                    # {"__interrupt__": (Interrupt(value=...),)} as an updates event.
                    if node_name == "__interrupt__":
                        interrupt_data_raw = state_update
                        # state_update is tuple of Interrupt objects
                        if interrupt_data_raw and len(interrupt_data_raw) > 0:
                            first = interrupt_data_raw[0]
                            interrupt_payload = getattr(first, 'value', first)
                            logger.info(f"session_id={session_id} HITL interrupt detected in stream: {interrupt_payload}")
                            await update_status(session_id, SessionStatus.processing)
                            yield (
                                "event: waiting_for_approval\n"
                                f"data: {json.dumps(interrupt_payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
                            )
                        return  # exit stream — client will resume via POST /resume

                    # ── Supervisor decision extraction ────────────────────
                    if node_name == "supervisor":
                        msgs = state_update.get("messages", []) or []
                        decision_text = None
                        for m in msgs:
                            content = None
                            if isinstance(m, dict):
                                content = m.get("content")
                            elif hasattr(m, "content"):
                                content = m.content
                            if content and "[Supervisor]" in str(content):
                                decision_text = str(content)
                                break
                        if not decision_text:
                            nw = state_update.get("next_worker", "")
                            if nw:
                                decision_text = f"[Supervisor] → {nw}"
                        if decision_text:
                            yield (
                                "event: thought_decision\n"
                                f"data: {json.dumps({'decision': decision_text}, ensure_ascii=False, separators=(',', ':'))}\n\n"
                            )

                    # Skip non-stage nodes
                    if node_name not in stage_name_map:
                        continue

                    # ── Stage complete ─────────────────────────────────────
                    # Merge state updates (each node only returns changed keys)
                    if final_state is None:
                        final_state = dict(state_update)
                    else:
                        final_state.update(state_update)

                    # Eval-specific stage_progress event
                    if node_name == "eval":
                        retries = state_update.get("retries", 0)
                        logger.info(f"session_id={session_id} 评估阶段进度: 第 {retries} 次重试")
                        yield (
                            "event: stage_progress\n"
                            f"data: {json.dumps({'stage': 'eval', 'retry': retries, 'progress': stage_progress_map['eval']}, ensure_ascii=False, separators=(',', ':'))}\n\n"
                        )

                    logger.info(f"session_id={session_id} 阶段完成: {node_name}")
                    elapsed_ms = None
                    if node_name in stage_started_at:
                        elapsed_ms = int((time.perf_counter() - stage_started_at[node_name]) * 1000)
                    yield (
                        "event: stage_complete\n"
                        f"data: {json.dumps({'stage': node_name, 'status': 'success', 'progress': stage_progress_map[node_name], 'elapsed_ms': elapsed_ms}, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    )

                # 每50个事件记录一次调试信息
                if event_count % 50 == 0:
                    logger.debug(f"session_id={session_id} 已处理 {event_count} 个事件")

            logger.info(f"session_id={session_id} 事件流处理完成，共处理 {event_count} 个事件")

            # 检查是否被取消
            if is_cancelled(session_id):
                logger.warning(f"session_id={session_id} 任务被取消")
                await update_status(session_id, SessionStatus.cancelled)
                yield "event: cancelled\ndata: {\"message\":\"任务已取消\"}\n\n"
                return

            # 检查最终状态 — 依赖 on_chain_end 可能不完整（节点只返回 partial update）
            if final_state is None or "quality_score" not in final_state:
                logger.warning(f"session_id={session_id} final_state 不完整 (quality_score 缺失)，回退同步调用")
                final_state = await run_graph(session_id=session_id, payload=payload)
                logger.info(f"session_id={session_id} 同步调用完成，获取到最终状态")

            # 处理最终结果
            logger.info(f"session_id={session_id} 开始处理最终结果")
            quality = final_state["quality_score"]
            records = final_state["generated_records"]
            scenario = final_state["scenario"]
            
            # 记录结果统计
            real_count = sum(1 for r in records if r.identity_label == "real")
            fake_count = sum(1 for r in records if r.identity_label == "fake")
            logger.info(f"session_id={session_id} 结果统计: 总计 {len(records)} 条, 真实流量 {real_count} 条, 脚本流量 {fake_count} 条, 质量分数 {quality.total_score}")
            
            # 写入CSV文件
            logger.info(f"session_id={session_id} 开始写入CSV文件")
            file_path = write_csv(session_id, records, payload.industry)
            logger.info(f"session_id={session_id} CSV文件写入完成: {file_path}")
            write_traffic_json(
                session_id,
                records,
                payload.industry,
                scenario=scenario,
                quality=quality,
                stage=payload.stage,
            )
            logger.info(f"session_id={session_id} JSON 文件写入完成")
            write_traffic_parquet(session_id, records, payload.industry)
            logger.info(f"session_id={session_id} Parquet 文件写入完成")
            
            # 创建会话记录
            logger.info(f"session_id={session_id} 创建会话记录")
            await complete_session(
                session_id=session_id,
                scenario=scenario,
                record_count=len(records),
                file_path=file_path,
                quality=quality,
            )
            
            # ── Record metrics ────────────────────────────────────────
            processing_time = int((time.perf_counter() - stream_start) * 1000)
            get_metrics().record_request(
                session_id=session_id,
                industry=payload.industry,
                stage=payload.stage.value,
                record_count=len(records),
                processing_time_ms=processing_time,
                success=True,
            )
            
            # 发送完成事件
            logger.info(f"session_id={session_id} 任务完成，发送完成事件")
            yield (
                "event: finalize\n"
                f"data: {{\"download_url\":\"/api/v1/traffic/download/{session_id}\"}}\n\n"
            )
            yield "event: complete\ndata: {\"success\":true}\n\n"
        except GraphInterrupt as gi:
            # Human-in-the-Loop: graph paused for approval
            interrupt_data = gi.value if hasattr(gi, 'value') else gi.args[0] if gi.args else {}
            logger.info(f"session_id={session_id} HITL interrupt: {interrupt_data}")
            await update_status(session_id, SessionStatus.processing)  # still processing, waiting for human
            yield (
                "event: waiting_for_approval\n"
                f"data: {json.dumps(interrupt_data, ensure_ascii=False, separators=(',', ':'))}\n\n"
            )
        except Exception as e:
            logger.exception(f"session_id={session_id} 发生异常: {e}")
            await fail_session(session_id, str(e))
            yield f"event: error\ndata: {{\"message\":\"{str(e)}\"}}\n\n"
        finally:
            remove_cancelled(session_id)
            _release()
            logger.info(f"session_id={session_id} 释放锁")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete("/generate/{session_id}")
async def cancel_generate(session_id: str) -> dict[str, str | bool]:
    add_cancelled(session_id)
    await update_status(session_id, SessionStatus.cancelled)
    return {"success": True, "session_id": session_id, "message": "任务已终止"}


@router.post("/resume/{session_id}")
async def resume_generate(
    session_id: str,
    payload: TrafficResumeRequest,
) -> dict[str, Any]:
    """Resume a HITL-paused graph with the human's decision.

    Called by the frontend after the user clicks Approve or Reject.
    Uses ``Command(resume=...)`` to feed the decision back into
    the ``interrupt()`` call inside ``approval_worker``.
    """
    await _acquire()
    try:
        graph = get_traffic_graph()
        thread_id = f"traffic_{session_id}"
        config = {"configurable": {"thread_id": thread_id}}

        decision = {"action": payload.action, "hint": payload.hint}
        logger.info(
            "session_id=%s resume with decision: %s",
            session_id, decision,
        )

        # Resume the graph from the interrupt point
        result = await graph.ainvoke(
            Command(resume=decision),
            config=config,
        )

        # Process final results (same logic as normal completion)
        quality = result.get("quality_score")
        records = result.get("generated_records", [])
        scenario = result.get("scenario", "")

        if quality and records:
            file_path = write_csv(session_id, records, result.get("industry", ""))
            write_traffic_json(
                session_id, records, result.get("industry", ""),
                scenario=scenario, quality=quality,
                stage=result.get("stage", Stage.standard),
            )
            write_traffic_parquet(session_id, records, result.get("industry", ""))
            await complete_session(
                session_id=session_id,
                scenario=scenario,
                record_count=len(records),
                file_path=file_path,
                quality=quality,
            )
            return {
                "success": True,
                "session_id": session_id,
                "download_url": f"/api/v1/traffic/download/{session_id}",
                "record_count": len(records),
            }

        # If quality missing, the graph may have been interrupted again (re-generate case)
        return {
            "success": False,
            "session_id": session_id,
            "message": "Graph did not complete — may need re-approval",
        }

    except GraphInterrupt as gi:
        # The graph was interrupted again (e.g., after re-generate → re-approval)
        interrupt_data = gi.value if hasattr(gi, 'value') else gi.args[0] if gi.args else {}
        logger.info(f"session_id={session_id} re-interrupted for approval: {interrupt_data}")
        return {
            "success": False,
            "session_id": session_id,
            "status": "pending_approval",
            "interrupt": interrupt_data,
        }
    except Exception as e:
        logger.exception(f"session_id={session_id} resume failed: {e}")
        await fail_session(session_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _release()


# ---------------------------------------------------------------------------
# Checkpoint Replay endpoints (P4.1 — Time Travel)
# ---------------------------------------------------------------------------


@router.get(
    "/checkpoints/{session_id}",
    response_model=CheckpointListResponse,
)
async def list_checkpoints(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
) -> CheckpointListResponse:
    """List checkpoints for a completed session with cursor pagination."""
    graph = get_traffic_graph()
    thread_id = f"traffic_{session_id}"
    config: dict = {"configurable": {"thread_id": thread_id}}

    items: list[CheckpointItem] = []
    kwargs: dict = {"limit": limit}
    if before:
        kwargs["before"] = {"configurable": {"thread_id": thread_id, "checkpoint_id": before}}
    async for snapshot in graph.aget_state_history(config, **kwargs):
        metadata = snapshot.metadata or {}
        cid = snapshot.config.get("configurable", {}).get("checkpoint_id", "")
        items.append(
            CheckpointItem(
                checkpoint_id=str(cid),
                step=metadata.get("step", 0),
                node_name=metadata.get("source", "unknown"),
                timestamp=str(metadata.get("timestamp", "")),
            )
        )

    return CheckpointListResponse(session_id=session_id, checkpoints=items)


@router.post("/replay", response_model=TrafficGenerateResponse)
async def replay_traffic(payload: TrafficReplayRequest) -> TrafficGenerateResponse:
    """Replay a session from a specific checkpoint node."""
    await _acquire()
    start_at = time.perf_counter()
    new_session_id = ""
    try:
        graph_result = await replay_from_checkpoint(
            original_session_id=payload.session_id,
            from_node=payload.from_node,
            hint_override=payload.hint_override,
        )
        new_session_id = graph_result["session_id"]
        scenario = graph_result["scenario"]
        quality = graph_result["quality_score"]
        records = graph_result["generated_records"]

        # Build a graph config for session tracking
        dummy_payload = TrafficGenerateRequest(
            industry=graph_result["industry"],
            count=graph_result["count"],
            stage=graph_result["stage"],
        )
        graph_config = build_graph_config(
            session_id=new_session_id, payload=dummy_payload,
        )
        await create_session(
            session_id=new_session_id,
            industry=graph_result["industry"],
            scenario=scenario,
            stage=graph_result["stage"],
            status=SessionStatus.processing,
            requested_count=graph_result["count"],
            record_count=0,
            quality_score=None,
            file_path=None,
            trace_thread_id=graph_config["configurable"]["thread_id"],
            trace_metadata=graph_config["metadata"],
        )

        file_path = write_csv(new_session_id, records, graph_result["industry"])
        write_traffic_json(
            new_session_id, records, graph_result["industry"],
            scenario=scenario, quality=quality, stage=graph_result["stage"],
        )
        write_traffic_parquet(new_session_id, records, graph_result["industry"])
        await complete_session(
            session_id=new_session_id,
            scenario=scenario,
            record_count=len(records),
            file_path=file_path,
            quality=quality,
        )

        return TrafficGenerateResponse(
            success=True,
            session_id=new_session_id,
            total_count=len(records),
            quality_score=quality,
            generated_data=records,
            processing_time_ms=int((time.perf_counter() - start_at) * 1000),
        )
    except Exception as e:
        if new_session_id:
            await fail_session(new_session_id, str(e))
        raise
    finally:
        _release()


@router.get("/download/{session_id}")
async def download_traffic(
    session_id: str,
    file_format: Literal["csv", "json", "parquet"] = Query("csv", alias="format"),
) -> FileResponse:
    file_path = await get_session_file(session_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if file_format == "json":
        path = path.with_suffix(".json")
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail="JSON 文件不存在，该任务可能为旧数据或需重新生成",
            )
        return FileResponse(
            path=path,
            filename=path.name,
            media_type="application/json",
        )
    if file_format == "parquet":
        path = path.with_suffix(".parquet")
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail="Parquet 文件不存在，该任务可能为旧数据或需重新生成",
            )
        return FileResponse(
            path=path,
            filename=path.name,
            media_type="application/vnd.apache.parquet",
        )
    return FileResponse(path=path, filename=path.name, media_type="text/csv")


@router.get("/history")
async def get_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, description="搜索关键字 (session_id/行业/场景/错误)"),
    industry: str | None = Query(default=None, description="行业过滤"),
    stage: str | None = Query(default=None, description="阶段过滤 (quick/standard/full)"),
    status: str | None = Query(default=None, description="状态过滤 (completed/failed/cancelled)"),
    date_from: date | None = Query(default=None, description="起始日期 (YYYY-MM-DD)"),
    date_to: date | None = Query(default=None, description="结束日期 (YYYY-MM-DD)"),
    min_quality: float | None = Query(default=None, ge=0, le=100, description="最低评分 (0-100)"),
) -> dict:
    total, items = await list_history(
        page, page_size,
        keyword=keyword,
        industry=industry,
        stage=stage,
        status=status,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        min_quality=min_quality,
    )
    total_pages = (total + page_size - 1) // page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": [item.model_dump() for item in items],
    }


@router.delete("/history/{session_id}")
async def remove_history(session_id: str) -> dict[str, str | bool]:
    file_path = await get_session_file(session_id)
    if file_path:
        file = Path(file_path)
        if file.exists():
            file.unlink()
    await delete_session(session_id)
    return {"success": True, "session_id": session_id, "message": "删除成功"}


async def _run_single_task(
    batch_id: str,
    task_index: int,
    session_id: str,
    industry: str,
    stage: str,
    count: int,
) -> None:
    """Run a single generation task as part of a batch."""
    await _acquire()
    try:
        from app.models.schemas import Stage

        payload = TrafficGenerateRequest(
            industry=industry,
            count=count,
            stage=Stage(stage),
        )
        graph_config = build_graph_config(session_id=session_id, payload=payload)
        await create_session(
            session_id=session_id,
            industry=industry,
            scenario="",
            stage=Stage(stage),
            status=SessionStatus.processing,
            requested_count=count,
            record_count=0,
            quality_score=None,
            file_path=None,
            trace_thread_id=graph_config["configurable"]["thread_id"],
            trace_metadata=graph_config["metadata"],
        )
        await update_batch_task_status(batch_id, task_index, "processing")

        graph_result = await run_graph(session_id=session_id, payload=payload)
        scenario = graph_result["scenario"]
        quality = graph_result["quality_score"]
        records = graph_result["generated_records"]
        file_path = write_csv(session_id, records, industry)
        write_traffic_json(
            session_id, records, industry,
            scenario=scenario, quality=quality, stage=Stage(stage),
        )
        write_traffic_parquet(session_id, records, industry)
        await complete_session(
            session_id=session_id,
            scenario=scenario,
            record_count=len(records),
            file_path=file_path,
            quality=quality,
        )
        await update_batch_task_status(batch_id, task_index, "completed")
    except Exception as e:
        await fail_session(session_id, str(e))
        await update_batch_task_status(batch_id, task_index, "failed", str(e))
    finally:
        _release()


@router.post("/batch")
async def start_batch(payload: BatchGenerateRequest) -> dict:
    batch_id = uuid.uuid4().hex[:8]
    await create_batch(batch_id)

    session_ids: list[str] = [uuid.uuid4().hex[:12] for _ in payload.tasks]

    for idx, task in enumerate(payload.tasks):
        await add_batch_task(
            batch_id=batch_id,
            task_index=idx,
            session_id=session_ids[idx],
            industry=task.industry,
            stage=task.stage.value,
            count=task.count,
        )

    for idx, task in enumerate(payload.tasks):
        asyncio.create_task(
            _run_single_task(
                batch_id=batch_id,
                task_index=idx,
                session_id=session_ids[idx],
                industry=task.industry,
                stage=task.stage.value,
                count=task.count,
            )
        )

    return {"success": True, "batch_id": batch_id}


@router.get("/batch/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str) -> BatchStatusResponse:
    tasks_rows = await get_batch_tasks(batch_id)
    if not tasks_rows:
        raise HTTPException(status_code=404, detail="批次不存在")

    tasks = []
    all_done = True
    for row in tasks_rows:
        status = SessionStatus(row["status"])
        if status not in (SessionStatus.completed, SessionStatus.failed, SessionStatus.cancelled):
            all_done = False
        progress = 100 if status == SessionStatus.completed else (50 if status == SessionStatus.processing else 0)

        from app.models.schemas import Stage as StageEnum

        tasks.append(
            BatchTaskStatus(
                index=row["task_index"],
                industry=row["industry"],
                stage=StageEnum(row["stage"]),
                count=row["count"],
                session_id=row["session_id"],
                status=status,
                progress=progress,
                error_message=row.get("error_message"),
            )
        )

    return BatchStatusResponse(batch_id=batch_id, tasks=tasks, finished=all_done)


@router.get("/report/{session_id}")
async def get_report(session_id: str):
    """Return an HTML report for a completed session."""
    from fastapi.responses import HTMLResponse

    html = await generate_report_html(session_id)
    if html is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return HTMLResponse(content=html, status_code=200)


@router.get("/industries")
async def get_industries():
    """Return industry configuration list for frontend consumption.

    Single source of truth: backend/app/data/industries.py.
    Frontend fetches this on mount — no hardcoded industry data duplication.
    """
    from app.models.schemas import IndustryItem
    data = get_industries_for_frontend()
    return [IndustryItem(**item) for item in data]


# ---------------------------------------------------------------------------
# Observability endpoints
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def get_system_metrics() -> dict:
    """Return system performance metrics.

    Includes throughput, latency percentiles (P50/P95/P99),
    success rate, token statistics, and uptime.
    """
    metrics = get_metrics().stats()
    token_stats = get_token_counter().stats()
    return {
        **metrics,
        "token_usage": token_stats,
        "concurrency": {
            "max_slots": 3,
        },
    }


@router.get("/model-info")
async def get_model_info() -> dict:
    """Return current LLM model configuration and capabilities.

    Useful for monitoring which model serves traffic generation
    and its operational parameters.
    """
    from app.core.config import settings
    return {
        "model_name": settings.ollama_model,
        "model": settings.ollama_model,
        "provider": f"Ollama ({settings.ollama_base_url})",
        "base_url": settings.ollama_base_url,
        "context_window": 32768,
        "context_window_estimate": 32768,
        "max_retries": settings.max_retry_count,
        "llm_timeout_seconds": settings.llm_timeout,
        "capabilities": [
            "structured_output_json_mode",
            "streaming",
            "tool_calling_via_langgraph",
        ],
        "supported_stages": ["quick", "standard", "full"],
        "stages": ["quick", "standard", "full"],
        "quality_dimensions": ["format", "business", "diversity"],
        "quality_threshold": 70,
    }


@router.post("/batch/{batch_id}/retry-failed")
async def retry_failed_batch_tasks(batch_id: str) -> dict:
    """Retry all failed tasks in a batch.

    Only retries tasks with status 'failed' — completed tasks are left untouched.
    """
    tasks_rows = await get_batch_tasks(batch_id)
    if not tasks_rows:
        raise HTTPException(status_code=404, detail="批次不存在")

    failed_tasks = [row for row in tasks_rows if row["status"] == "failed"]
    if not failed_tasks:
        return {"success": True, "batch_id": batch_id, "retried": 0, "message": "没有失败的任务"}

    for row in failed_tasks:
        from app.models.schemas import Stage as StageEnum

        payload = TrafficGenerateRequest(
            industry=row["industry"],
            count=row["count"],
            stage=StageEnum(row["stage"]),
        )
        asyncio.create_task(
            _run_single_task(
                batch_id=batch_id,
                task_index=row["task_index"],
                session_id=row["session_id"],
                industry=row["industry"],
                stage=row["stage"],
                count=row["count"],
            )
        )

    return {
        "success": True,
        "batch_id": batch_id,
        "retried": len(failed_tasks),
        "message": f"已重试 {len(failed_tasks)} 个失败任务",
    }
