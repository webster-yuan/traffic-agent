import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class Settings(BaseModel):
    langchain_tracing_v2: bool = False
    langsmith_project: Optional[str] = None
    app_name: str = "Traffic Agent API"
    app_version: str = "0.1.0"
    sqlite_path: str = "data/traffic_agent.db"
    checkpoint_db_path: str = "data/checkpoints.db"
    output_dir: str = "data/outputs"
    max_retry_count: int = 3
    single_concurrency: int = 1
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct-q4_K_M"
    identity_service_enabled: bool = True


settings = Settings()
