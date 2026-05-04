import logging
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.services.llm_factory import get_ollama_llm

logger = logging.getLogger(__name__)


def build_generation_hint(industry: str, scenario: str, count: int) -> str:
    logger.info(f"构建生成提示: industry={industry}, scenario={scenario}, count={count}")
    
    try:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你是网络流量生成助手，请给出一句简洁的生成策略建议。"),
                (
                    "human",
                    "行业={industry}，场景={scenario}，数量={count}。请返回不超过30字。",
                ),
            ]
        )
        
        llm = get_ollama_llm(temperature=0.1)
        
        chain = prompt | llm
        result = chain.invoke(
            {"industry": industry, "scenario": scenario, "count": count}
        )
        
        content = getattr(result, "content", "")
        hint = str(content).strip() if content else "按场景规则生成并保证分布多样性"
        
        return hint
    except Exception as e:
        logger.warning(f"LLM生成提示失败，使用默认提示: {e}")
        return "按场景规则生成并保证分布多样性"
