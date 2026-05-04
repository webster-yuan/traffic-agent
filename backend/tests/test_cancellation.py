import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.state import add_cancelled, is_cancelled
from app.graph.shared import check_cancelled


class TestCancellation:
    """测试取消功能"""

    def test_add_cancelled_marks_session(self):
        """测试添加取消标记"""
        session_id = "test-cancel-123"

        # 验证初始状态
        assert not is_cancelled(session_id)

        # 添加取消标记
        add_cancelled(session_id)
        assert is_cancelled(session_id)

        # 再次添加
        add_cancelled(session_id)
        assert is_cancelled(session_id)

        # 取消标记仍然存在
        assert is_cancelled(session_id)

    def test_node_raises_on_cancelled(self):
        """测试被取消的节点抛出异常"""
        session_id = "test-cancel-node"
        add_cancelled(session_id)

        # 模拟节点取消检查
        with pytest.raises(RuntimeError, match="Task cancelled"):
            check_cancelled(session_id)
