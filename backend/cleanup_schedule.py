"""会话文件自动清理调度脚本

使用 schedule 库定期清理旧会话
"""
import asyncio
import schedule
import time
from datetime import datetime

from app.core.config import settings
from app.db.database import get_connection
from app.core.state import get_cancelled_sessions


async def cleanup_old_sessions() -> dict[str, int]:
    """清理超过保留天数的旧会话"""
    days = getattr(settings, "cleanup_days", 30)
    cutoff_date = datetime.now(timezone.utc) - time.timedelta(days=days)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, file_path, created_at
            FROM traffic_sessions
            WHERE created_at < ?
            """,
            (cutoff_date.isoformat(),)
        ).fetchall()

        deleted_files = []
        deleted_count = 0

        for row in rows:
            session_id = row["id"]
            file_path = row["file_path"]

            if file_path:
                try:
                    path = Path(file_path)
                    if path.exists():
                        path.unlink()
                        deleted_files.append(str(path))
                except Exception as e:
                    print(f"删除文件失败 {file_path}: {e}")

            try:
                conn.execute(
                    "DELETE FROM traffic_sessions WHERE id = ?",
                    (session_id,)
                )
                deleted_count += 1
            except Exception as e:
                print(f"删除会话记录失败 {session_id}: {e}")

        conn.commit()

    return {"deleted_count": deleted_count, "deleted_files": deleted_files}


def cleanup_cancelled_sessions() -> int:
    """清理已取消的会话标记"""
    cancelled = get_cancelled_sessions()
    cancelled.clear()
    return len(cancelled)


def scheduled_cleanup():
    """调度清理任务"""
    print(f"[{datetime.now()}] 执行清理任务")
    stats = asyncio.run(cleanup_old_sessions())
    cancelled_count = cleanup_cancelled_sessions()
    print(f"清理完成: 删除 {stats['deleted_count']} 个会话, {cancelled_count} 个取消标记")


def main():
    """主函数"""
    # 从配置读取清理间隔
    schedule_interval = getattr(settings, "cleanup_interval_hours", 24)

    # 添加调度任务
    schedule.every(schedule_interval).hours.do(scheduled_cleanup)

    print(f"会话清理调度器已启动，清理间隔: {schedule_interval} 小时")
    print("按 Ctrl+C 停止调度器")

    # 立即执行一次
    scheduled_cleanup()

    # 持续运行
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n调度器已停止")
            break


if __name__ == "__main__":
    main()
