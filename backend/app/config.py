"""
Configuration loading for the backend application.
"""

import os

from dotenv import load_dotenv


APP_ROOT = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(APP_ROOT, "../.."))
PROJECT_ROOT_ENV = os.path.join(PROJECT_ROOT, ".env")

def reload_project_env(override: bool = False) -> None:
    if os.path.exists(PROJECT_ROOT_ENV):
        load_dotenv(PROJECT_ROOT_ENV, override=override)
        return
    load_dotenv(override=override)


reload_project_env()


def _project_path(raw: str) -> str:
    if os.path.isabs(raw):
        return raw
    return os.path.abspath(os.path.join(PROJECT_ROOT, raw))


class Config:
    """Flask configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "mirofish-secret-key")
    DEBUG = os.environ.get("FLASK_DEBUG", "True").lower() == "true"

    JSON_AS_ASCII = False

    LLM_API_KEY = os.environ.get("LLM_API_KEY")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")
    LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://127.0.0.1:8283/v1")
    LETTA_SERVER_API_KEY = os.environ.get("LETTA_SERVER_API_KEY")
    LETTA_API_KEY = os.environ.get("LETTA_API_KEY")
    LETTA_EMBEDDING_MODEL = os.environ.get(
        "LETTA_EMBEDDING_MODEL",
        "openai/text-embedding-3-small",
    )

    ZEP_API_KEY = os.environ.get("ZEP_API_KEY")

    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "../uploads")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 50

    LOTTERY_DATA_ROOT = _project_path(
        os.environ.get("LOTTERY_DATA_ROOT", os.path.join(PROJECT_ROOT, "ziweidoushu")),
    )
    AGENT_FABRIC_ROOT = _project_path(
        os.environ.get("AGENT_FABRIC_ROOT", os.path.join(LOTTERY_DATA_ROOT, "agent_fabric")),
    )
    AGENT_FABRIC_GENERATED_ROOT = _project_path(
        os.environ.get("AGENT_FABRIC_GENERATED_ROOT", os.path.join(LOTTERY_DATA_ROOT, "generated")),
    )
    KUZU_GRAPH_ROOT = _project_path(
        os.environ.get("KUZU_GRAPH_ROOT", os.path.join(LOTTERY_DATA_ROOT, ".kuzu_graph")),
    )
    LOTTERY_WORLD_STATE_ROOT = _project_path(
        os.environ.get("LOTTERY_WORLD_STATE_ROOT", os.path.join(LOTTERY_DATA_ROOT, ".world_state")),
    )
    LOTTERY_RUNTIME_MODE = os.environ.get("LOTTERY_RUNTIME_MODE", "legacy")
    EXECUTION_CONFIG_PATH = os.environ.get(
        "EXECUTION_CONFIG_PATH",
        os.path.join(os.path.dirname(__file__), "services", "lottery", "execution_config.yaml"),
    )

    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get("OASIS_DEFAULT_MAX_ROUNDS", "10"))
    OASIS_SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__),
        "../uploads/simulations",
    )

    OASIS_TWITTER_ACTIONS = [
        "CREATE_POST",
        "LIKE_POST",
        "REPOST",
        "FOLLOW",
        "DO_NOTHING",
        "QUOTE_POST",
    ]
    OASIS_REDDIT_ACTIONS = [
        "LIKE_POST",
        "DISLIKE_POST",
        "CREATE_POST",
        "CREATE_COMMENT",
        "LIKE_COMMENT",
        "DISLIKE_COMMENT",
        "SEARCH_POSTS",
        "SEARCH_USER",
        "TREND",
        "REFRESH",
        "DO_NOTHING",
        "FOLLOW",
        "MUTE",
    ]

    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get("REPORT_AGENT_MAX_TOOL_CALLS", "5"))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(
        os.environ.get("REPORT_AGENT_MAX_REFLECTION_ROUNDS", "2")
    )
    REPORT_AGENT_TEMPERATURE = float(os.environ.get("REPORT_AGENT_TEMPERATURE", "0.5"))

    @classmethod
    def validate(cls) -> list[str]:
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY is not configured")
        return errors
