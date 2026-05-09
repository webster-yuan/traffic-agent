import json
import logging
import time
import uuid

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from app.models.schemas import (
    SessionStatus,
    Stage,
    TrafficGenerateRequest,
    TrafficGenerateResponse,
    TrafficResumeRequest,
)
from app.graph.workflow import get_traffic_graph
from app.services.generator import write_csv, write_traffic_json, write_traffic_parquet
from app.services.graph_runner import (
    build_initial_state,
    run_generation_graph_async as run_graph,
)
from app.services.tracing_config import build_graph_config
from app.services.session_service import (
    complete_session,
    create_session,
    fail_session,
    update_status,
)
from app.core.state import add_cancelled, is_cancelled, remove_cancelled
from app.services.system_metrics import get_metrics
from app.api.deps import _acquire, _release

router = APIRouter()


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
    except GraphInterrupt:
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

    async def event_stream():
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

            yield f"event: start\ndata: {{\"session_id\": \"{session_id}\"}}\n\n"
            logger.info("session_id=%s start event sent", session_id)

            initial_state = build_initial_state(session_id=session_id, payload=payload)
            logger.info("session_id=%s initial state built: industry=%s, stage=%s, count=%s", session_id, payload.industry, payload.stage, payload.count)

            logger.info("session_id=%s listening to graph event stream", session_id)
            event_count = 0
            async for (mode, data) in graph.astream(
                initial_state,
                config=graph_config,
                stream_mode=["updates", "custom"],
            ):
                event_count += 1

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

                for node_name, state_update in data.items():

                    if node_name == "__interrupt__":
                        interrupt_data_raw = state_update
                        if interrupt_data_raw and len(interrupt_data_raw) > 0:
                            first = interrupt_data_raw[0]
                            interrupt_payload = getattr(first, 'value', first)
                            logger.info(f"session_id={session_id} HITL interrupt detected in stream: {interrupt_payload}")
                            await update_status(session_id, SessionStatus.processing)
                            yield (
                                "event: waiting_for_approval\n"
                                f"data: {json.dumps(interrupt_payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
                            )
                        return

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

                    if node_name not in stage_name_map:
                        continue

                    if final_state is None:
                        final_state = dict(state_update)
                    else:
                        final_state.update(state_update)

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

                if event_count % 50 == 0:
                    logger.debug(f"session_id={session_id} 已处理 {event_count} 个事件")

            logger.info(f"session_id={session_id} 事件流处理完成，共处理 {event_count} 个事件")

            if is_cancelled(session_id):
                logger.warning(f"session_id={session_id} 任务被取消")
                await update_status(session_id, SessionStatus.cancelled)
                yield "event: cancelled\ndata: {\"message\":\"任务已取消\"}\n\n"
                return

            if final_state is None or "quality_score" not in final_state:
                logger.warning(f"session_id={session_id} final_state 不完整 (quality_score 缺失)，回退同步调用")
                final_state = await run_graph(session_id=session_id, payload=payload)
                logger.info(f"session_id={session_id} 同步调用完成，获取到最终状态")

            logger.info(f"session_id={session_id} 开始处理最终结果")
            quality = final_state["quality_score"]
            records = final_state["generated_records"]
            scenario = final_state["scenario"]

            real_count = sum(1 for r in records if r.identity_label == "real")
            fake_count = sum(1 for r in records if r.identity_label == "fake")
            logger.info(f"session_id={session_id} 结果统计: 总计 {len(records)} 条, 真实流量 {real_count} 条, 脚本流量 {fake_count} 条, 质量分数 {quality.total_score}")

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

            logger.info(f"session_id={session_id} 创建会话记录")
            await complete_session(
                session_id=session_id,
                scenario=scenario,
                record_count=len(records),
                file_path=file_path,
                quality=quality,
            )

            processing_time = int((time.perf_counter() - stream_start) * 1000)
            get_metrics().record_request(
                session_id=session_id,
                industry=payload.industry,
                stage=payload.stage.value,
                record_count=len(records),
                processing_time_ms=processing_time,
                success=True,
            )

            logger.info(f"session_id={session_id} 任务完成，发送完成事件")
            yield (
                "event: finalize\n"
                f"data: {{\"download_url\":\"/api/v1/traffic/download/{session_id}\"}}\n\n"
            )
            yield "event: complete\ndata: {\"success\":true}\n\n"
        except GraphInterrupt:
            await update_status(session_id, SessionStatus.processing)
            yield "event: waiting_for_approval\ndata: {}\n\n"
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
) -> dict:
    """Resume a HITL-paused graph with the human's decision."""
    await _acquire()
    try:
        graph = get_traffic_graph()
        thread_id = f"traffic_{session_id}"
        config = {"configurable": {"thread_id": thread_id}}

        decision = {"action": payload.action, "hint": payload.hint}
        logger.info("session_id=%s resume with decision: %s", session_id, decision)

        result = await graph.ainvoke(Command(resume=decision), config=config)

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

        return {
            "success": False,
            "session_id": session_id,
            "message": "Graph did not complete — may need re-approval",
        }

    except GraphInterrupt as gi:
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
