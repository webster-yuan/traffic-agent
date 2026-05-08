"""会话文件自动清理脚本

定期清理超过指定天数的旧会话文件和数据库记录
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.core.state import get_cancelled_sessions
from app.db.database import get_connection

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def cleanup_old_sessions(days: int = 30) -> dict[str, int]:
    """
    清理超过指定天数的旧会话

    Args:
        days: 保留天数，超过此天数的会话将被清理

    Returns:
        清理统计信息
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    conn = await get_connection()
    cursor = await conn.execute(
        """
        SELECT id, file_path, created_at
        FROM traffic_sessions
        WHERE created_at < ?
        """,
        (cutoff_date.isoformat(),)
    )
    rows = await cursor.fetchall()

    deleted_files = []
    deleted_count = 0

    for row in rows:
        session_id = row["id"]
        file_path = row["file_path"]

        # 删除 CSV 文件
        if file_path:
            try:
                path = Path(file_path)
                if path.exists():
                    path.unlink()
                    deleted_files.append(str(path))
            except Exception as e:
                logger.error(f"删除文件失败 {file_path}: {e}")

        # 删除数据库记录
        try:
            await conn.execute(
                "DELETE FROM traffic_sessions WHERE id = ?",
                (session_id,)
            )
            deleted_count += 1
        except Exception as e:
            logger.error(f"删除会话记录失败 {session_id}: {e}")

    await conn.commit()

    logger.info(f"清理完成: 删除 {deleted_count} 个会话记录, {len(deleted_files)} 个文件")
    return {
        "deleted_count": deleted_count,
        "deleted_files": deleted_files
    }


async def _dry_run_cleanup(days: int) -> list[dict]:
    """干运行模式 — 查询但不删除."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT id, file_path, created_at FROM traffic_sessions WHERE created_at < ?",
        (cutoff_date.isoformat(),)
    )
    return [dict(row) for row in await cursor.fetchall()]


def cleanup_cancelled_sessions() -> int:
    """清理已取消的会话标记"""
    cancelled = get_cancelled_sessions()
    cancelled.clear()
    return len(cancelled)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="清理 Traffic Agent 旧会话文件和记录"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="保留天数（默认：30）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示将要清理的内容，不实际删除"
    )

    args = parser.parse_args()

    logger.info(f"开始清理会话，保留天数: {args.days}, 干运行: {args.dry_run}")

    if args.dry_run:
        logger.info("干运行模式 - 不实际删除任何文件或记录")
        rows = asyncio.run(_dry_run_cleanup(days=args.days))
        logger.info(f"将删除 {len(rows)} 个会话记录")
        for row in rows:
            logger.info(f"  - {row['id']}: {row.get('file_path') or '无文件'}")
    else:
        # 清理旧会话
        stats = asyncio.run(cleanup_old_sessions(days=args.days))

        # 清理取消标记
        cancelled_count = cleanup_cancelled_sessions()
        logger.info(f"清理 {cancelled_count} 个取消标记")

    logger.info("清理完成")


if __name__ == "__main__":
    main()
