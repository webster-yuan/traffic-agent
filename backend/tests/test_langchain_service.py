"""Tests for app.services.langchain_service — LLM hint generation."""

from unittest.mock import MagicMock, patch

from app.services.langchain_service import build_generation_hint


class TestBuildGenerationHint:
    """Tests for build_generation_hint() — generates LLM-based strategy hints."""

    def test_returns_llm_content_on_success(self):
        """build_generation_hint returns LLM-generated hint string."""
        mock_response = MagicMock()
        mock_response.content = "优先使用POST和PUT方法模拟业务操作"
        mock_llm = MagicMock()
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_response
        mock_llm.__or__ = MagicMock(return_value=mock_chain)

        with patch("app.services.langchain_service.get_ollama_llm", return_value=mock_llm):
            with patch("app.services.langchain_service.ChatPromptTemplate") as mock_template:
                mock_template.from_messages.return_value = MagicMock()
                mock_template.from_messages.return_value.__or__ = MagicMock(return_value=mock_chain)

                result = build_generation_hint("ecommerce", "flash_sale", 100)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_default_on_empty_content(self):
        """build_generation_hint returns default hint when LLM returns empty."""
        mock_response = MagicMock()
        mock_response.content = ""
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_response

        with patch("app.services.langchain_service.get_ollama_llm") as mock_llm:
            mock_prompt = MagicMock()
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            with patch("app.services.langchain_service.ChatPromptTemplate") as mock_tpl:
                mock_tpl.from_messages.return_value = mock_prompt

                result = build_generation_hint("ecommerce", "flash_sale", 100)

        assert result == "按场景规则生成并保证分布多样性"

    def test_returns_default_on_no_content_attr(self):
        """build_generation_hint returns default when result has no content attr."""
        mock_response = MagicMock(spec=[])  # no 'content' attribute
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_response

        with patch("app.services.langchain_service.get_ollama_llm") as mock_llm:
            mock_prompt = MagicMock()
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            with patch("app.services.langchain_service.ChatPromptTemplate") as mock_tpl:
                mock_tpl.from_messages.return_value = mock_prompt

                result = build_generation_hint("ecommerce", "flash_sale", 100)

        assert result == "按场景规则生成并保证分布多样性"

    def test_returns_default_on_exception(self):
        """build_generation_hint returns default hint when LLM call fails."""
        with patch("app.services.langchain_service.get_ollama_llm", side_effect=RuntimeError("Ollama down")):
            result = build_generation_hint("ecommerce", "flash_sale", 100)

        assert result == "按场景规则生成并保证分布多样性"
