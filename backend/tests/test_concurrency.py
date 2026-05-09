import asyncio
import sys
from pathlib import Path

import pytest

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.deps import _semaphore, _acquire, _release


class TestConcurrency:
    """测试并发控制"""

    def test_concurrent_requests_accepted(self):
        """测试多个并发请求应该被接受（并发池模式）"""
        async def make_request():
            await _acquire()
            await asyncio.sleep(0.1)  # 模拟处理时间
            _release()

        async def run_all() -> None:
            tasks = [make_request() for _ in range(5)]
            await asyncio.gather(*tasks)

        asyncio.run(run_all())

    def test_semaphore_count_reaches_zero(self):
        """测试当获取 3 个信号量后，计数器应该为 0"""
        async def test():
            await _acquire()
            await _acquire()
            await _acquire()
            # 此时应该有 0 个可用槽位
            assert _semaphore._value == 0
            _release()
            assert _semaphore._value == 1

        asyncio.run(test())
