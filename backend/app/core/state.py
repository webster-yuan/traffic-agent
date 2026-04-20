"""全局状态管理，用于取消标记等"""

_cancelled_sessions = set()


def add_cancelled(session_id: str) -> None:
    """添加取消标记"""
    _cancelled_sessions.add(session_id)


def is_cancelled(session_id: str) -> bool:
    """检查是否被取消"""
    return session_id in _cancelled_sessions


def remove_cancelled(session_id: str) -> None:
    """移除取消标记"""
    _cancelled_sessions.discard(session_id)


def get_cancelled_sessions() -> set[str]:
    """获取所有取消的会话"""
    return set(_cancelled_sessions)
