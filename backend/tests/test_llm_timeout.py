import sys
from pathlib import Path

import pytest

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.generator import _get_llm_timeout


class TestLLMTimeout:
    """测试 LLM 超时配置"""

    def test_llm_timeout_config(self):
        """测试 LLM 超时配置"""
        assert settings.llm_timeout > 0
        assert settings.llm_timeout == 300

    def test_get_llm_timeout_function(self):
        """测试超时时间获取函数"""
        timeout = _get_llm_timeout()
        assert timeout > 0
        assert timeout == 300
