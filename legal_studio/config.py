"""Application configuration and safe defaults."""
from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlsplit
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', override=False)


def flag(value: str | None, default=False) -> bool:
    return default if value is None else value.lower().strip() in {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class Settings:
    law_oc: str = ''
    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = ''
    enable_llm: bool = False
    demo_mode: bool = False
    db_path: str = 'data/legal_studio.sqlite3'
    cache_sources: bool = True
    embedding_model: str = ''
    allow_remote_ollama: bool = False

    @classmethod
    def from_env(cls):
        return cls(
            law_oc=os.getenv('LAW_OC', '').strip(),
            ollama_base_url=os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').strip(),
            ollama_model=os.getenv('OLLAMA_MODEL', '').strip(),
            enable_llm=flag(os.getenv('ENABLE_LLM')),
            demo_mode=flag(os.getenv('DEMO_MODE')),
            db_path=os.getenv('DB_PATH', 'data/legal_studio.sqlite3'),
            cache_sources=flag(os.getenv('CACHE_SOURCE_DOCUMENTS'), True),
            embedding_model=os.getenv('OLLAMA_EMBED_MODEL','').strip(),
            allow_remote_ollama=flag(os.getenv('ALLOW_REMOTE_OLLAMA')),
        )

    def ollama_allowed(self):
        try:
            parsed = urlsplit(self.ollama_base_url)
            return (parsed.scheme in {'http','https'} and not parsed.username and not parsed.password
                    and bool(parsed.hostname) and not parsed.query and not parsed.fragment
                    and (parsed.hostname in {'localhost','127.0.0.1','::1'} or self.allow_remote_ollama))
        except ValueError:
            return False

    def resolved_db_path(self):
        p = Path(self.db_path)
        return p if p.is_absolute() else ROOT / p
