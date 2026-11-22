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


@dataclass(frozen=True)
class Settings:
    corpus_dir: Path
    model_cache: Path
    embedding_model: str
    fixed_today: date | None  # set for the eval, so date-dependent answers don't drift

    def today(self) -> date:
        return self.fixed_today or date.today()


def get_settings() -> Settings:
    load_dotenv()
    today = os.environ.get("HANDBOOK_TODAY")
    return Settings(
        corpus_dir=Path(os.environ.get("HANDBOOK_CORPUS", DEFAULT_CORPUS)),
        model_cache=Path(os.environ.get("HANDBOOK_MODEL_CACHE", DEFAULT_MODEL_CACHE)),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        fixed_today=date.fromisoformat(today) if today else None,
    )
