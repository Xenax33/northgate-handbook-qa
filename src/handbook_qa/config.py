"""Settings, read from environment variables and an optional `.env` file in the project root.

Nothing here is secret except the API key, which is only ever read, never logged or printed.
"""

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

def _project_root() -> Path:
    """The repository folder. Found from this file when the package is installed in editable mode
    (what `uv sync` does); otherwise the folder the command is run from."""
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "pyproject.toml").is_file() else Path.cwd()


PROJECT_ROOT = _project_root()
DEFAULT_CORPUS = PROJECT_ROOT / "data" / "corpus"
DEFAULT_MODEL_CACHE = PROJECT_ROOT / ".cache" / "models"
DEFAULT_UPLOADS = PROJECT_ROOT / "data" / "uploads"


def load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    """Copy KEY=value lines from `.env` into os.environ, without overriding variables already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


@dataclass(frozen=True)
class Settings:
    corpus_dir: Path
    model_cache: Path
    embedding_model: str
    fixed_today: date | None  # set for the eval, so date-dependent answers don't drift
    llm_base_url: str  # any OpenAI-compatible endpoint (D13); Gemini by default
    llm_model: str
    llm_api_key: str | None  # never logged or printed
    uploads_dir: Path | None = None  # None: uploads switched off (the eval uses the official handbook only)
    upload_token: str | None = None  # if set, uploads need it (D26); never logged or printed

    def today(self) -> date:
        return self.fixed_today or date.today()


def get_settings() -> Settings:
    load_dotenv()
    today = os.environ.get("HANDBOOK_TODAY")
    try:
        fixed_today = date.fromisoformat(today) if today else None
    except ValueError as error:
        raise ValueError(f"HANDBOOK_TODAY must be YYYY-MM-DD, got {today!r}") from error
    return Settings(
        corpus_dir=Path(os.environ.get("HANDBOOK_CORPUS", DEFAULT_CORPUS)),
        model_cache=Path(os.environ.get("HANDBOOK_MODEL_CACHE", DEFAULT_MODEL_CACHE)),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        fixed_today=fixed_today,
        llm_base_url=os.environ.get("LLM_BASE_URL", GEMINI_OPENAI_URL),
        llm_model=os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite"),
        llm_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        uploads_dir=Path(os.environ.get("HANDBOOK_UPLOADS", DEFAULT_UPLOADS)),
        upload_token=os.environ.get("UPLOAD_TOKEN") or None,
    )
