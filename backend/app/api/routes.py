import asyncio
import time
import uuid
import logging
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.models.schemas import (
    SessionStatus,
    TrafficGenerateRequest,
    TrafficGenerateResponse,
)
from app.graph.workflow import get_traffic_graph
from app.services.generator import write_csv
from app.services.graph_runner import build_initial_state, run_generation_graph
from app.services.tracing_config import build_graph_config
from app.services.session_service import (
    create_session,
    delete_session,
    get_session_file,
    list_history,
    update_status,
)
from app.core.state import add_cancelled, is_cancelled, remove_cancelled

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
    try:
        graph_result = run_generation_graph(session_id=session_id, payload=payload)
        scenario = graph_result["scenario"]
        quality = graph_result["quality_score"]
        records = graph_result["generated_records"]
        file_path = write_csv(session_id, records, payload.industry)
        create_session(
            session_id=session_id,
            industry=payload.industry,
            scenario=scenario,
            stage=payload.stage,
            status=SessionStatus.completed,
            record_count=len(records),
            quality_score=quality.total_score,
            file_path=file_path,
        )
        return TrafficGenerateResponse(
            success=True,
            session_id=session_id,
            total_count=len(records),
            quality_score=quality,
            generated_data=records,
            processing_time_ms=int((time.perf_counter() - start_at) * 1000),
        )
    finally:
        _release()


@router.post("/generate/stream")
async def generate_traffic_stream(payload: TrafficGenerateRequest) -> StreamingResponse:
    logger.info(f"收到流式请求: industry={payload.industry}, stage={payload.stage}, count={payload.count}")
    await _acquire()
    session_id = uuid.uuid4().hex[:12]
    logger.info(f"session_id={session_id} 获取锁成功")

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            logger.info(f"session_id={session_id} 开始流式处理流程")
            graph = get_traffic_graph()
            logger.info(f"session_id={session_id} Graph实例获取成功")
            
            stage_name_map = {
                "rag": "RAG检索",
                "generate": "流量生成",
                "eval": "质量评估",
                "identity": "身份校验",
            }
            seen_start: set[str] = set()
            final_state: dict | None = None

            # 发送开始事件
            yield f"event: start\ndata: {{\"session_id\": \"{session_id}\"}}\n\n"
            logger.info(f"session_id={session_id} 开始事件已发送")

            # 初始化状态
            initial_state = build_initial_state(session_id=session_id, payload=payload)
            logger.info(f"session_id={session_id} 初始状态构建完成: industry={payload.industry}, stage={payload.stage}, count={payload.count}")

            # 监听graph事件流
            logger.info(f"session_id={session_id} 开始监听graph事件流")
            event_count = 0
            async for event in graph.astream_events(
                initial_state,
                config=build_graph_config(session_id=session_id, payload=payload),
                version="v1",
            ):
                event_count += 1
                event_type = event.get("event")
                metadata = event.get("metadata", {}) or {}
                node = metadata.get("langgraph_node")
                
                # 只处理我们关心的节点事件
                if node not in stage_name_map:
                    continue

                # 阶段开始事件
                if event_type == "on_chain_start" and node not in seen_start:
                    seen_start.add(node)
                    logger.info(f"session_id={session_id} 阶段开始: {node}")
                    yield (
                        "event: stage_start\n"
                        f"data: {{\"stage\":\"{node}\",\"name\":\"{stage_name_map[node]}\"}}\n\n"
                    )

                # 阶段结束事件
                if event_type == "on_chain_end":
                    output = (event.get("data", {}) or {}).get("output")
                    if isinstance(output, dict):
                        final_state = output

                    # 评估阶段的特殊进度事件
                    if node == "eval" and isinstance(output, dict):
                        retries = output.get("retries", 0)
                        logger.info(f"session_id={session_id} 评估阶段进度: 第 {retries} 次重试")
                        yield (
                            "event: stage_progress\n"
                            f"data: {{\"stage\":\"eval\",\"retry\":{retries}}}\n\n"
                        )

                    logger.info(f"session_id={session_id} 阶段完成: {node}")
                    yield (
                        "event: stage_complete\n"
                        f"data: {{\"stage\":\"{node}\",\"status\":\"success\"}}\n\n"
                    )
                
                # 每50个事件记录一次调试信息
                if event_count % 50 == 0:
                    logger.debug(f"session_id={session_id} 已处理 {event_count} 个事件")

            logger.info(f"session_id={session_id} 事件流处理完成，共处理 {event_count} 个事件")

            # 检查是否被取消
            if is_cancelled(session_id):
                logger.warning(f"session_id={session_id} 任务被取消")
                update_status(session_id, SessionStatus.cancelled)
                yield "event: cancelled\ndata: {\"message\":\"任务已取消\"}\n\n"
                return

            # 检查最终状态
            if final_state is None:
                logger.warning(f"session_id={session_id} 事件流未获取到最终状态，回退同步调用")
                final_state = run_generation_graph(session_id=session_id, payload=payload)
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
            
            # 创建会话记录
            logger.info(f"session_id={session_id} 创建会话记录")
            create_session(
                session_id=session_id,
                industry=payload.industry,
                scenario=scenario,
                stage=payload.stage,
                status=SessionStatus.completed,
                record_count=len(records),
                quality_score=quality.total_score,
                file_path=file_path,
            )
            
            # 发送完成事件
            logger.info(f"session_id={session_id} 任务完成，发送完成事件")
            yield (
                "event: finalize\n"
                f"data: {{\"download_url\":\"/api/v1/traffic/download/{session_id}\"}}\n\n"
            )
            yield "event: complete\ndata: {\"success\":true}\n\n"
        except Exception as e:
            logger.exception(f"session_id={session_id} 发生异常: {e}")
            yield f"event: error\ndata: {{\"message\":\"{str(e)}\"}}\n\n"
        finally:
            remove_cancelled(session_id)
            _release()
            logger.info(f"session_id={session_id} 释放锁")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete("/generate/{session_id}")
async def cancel_generate(session_id: str) -> dict[str, str | bool]:
    add_cancelled(session_id)
    update_status(session_id, SessionStatus.cancelled)
    return {"success": True, "session_id": session_id, "message": "任务已终止"}


@router.get("/download/{session_id}")
async def download_csv(session_id: str) -> FileResponse:
    file_path = get_session_file(session_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    file = Path(file_path)
    if not file.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path=file, filename=file.name, media_type="text/csv")


@router.get("/history")
async def get_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    total, items = list_history(page, page_size)
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
    file_path = get_session_file(session_id)
    if file_path:
        file = Path(file_path)
        if file.exists():
            file.unlink()
    delete_session(session_id)
    return {"success": True, "session_id": session_id, "message": "删除成功"}
