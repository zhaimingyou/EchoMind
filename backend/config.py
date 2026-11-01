"""Global configuration management for EchoMind.

Uses `pydantic-settings` when installed, and seamlessly falls back to standard
library `os.environ` + `dataclasses` so CLI simulations and unit tests run even
in bare Python environments prior to `pip install`.
"""
from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _load_dotenv_into_environ(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv_into_environ()


@dataclass
class Settings:
    """Application settings loaded from environment variables or .env file."""

    # Server
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "EchoMind"))
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    # Pluggable Providers ("sherpa_onnx", "default", "local_ngram", "rms_energy", or custom)
    asr_provider: str = field(default_factory=lambda: os.getenv("ASR_PROVIDER", "sherpa_onnx"))
    speaker_provider: str = field(default_factory=lambda: os.getenv("SPEAKER_PROVIDER", "sherpa_onnx"))
    vad_provider: str = field(default_factory=lambda: os.getenv("VAD_PROVIDER", "rms_energy"))
    extractor_provider: str = field(default_factory=lambda: os.getenv("EXTRACTOR_PROVIDER", "default"))
    embedding_provider: str = field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "local_ngram"))

    # HUD Attention Budget Policy ("verbose" | "action_only" | "silent_record")
    # Inspired by dsh-superagent 000-philosophy: "Take as little human attention as possible"
    hud_attention_policy: str = field(
        default_factory=lambda: os.getenv("HUD_ATTENTION_POLICY", "verbose")
    )

    # Background Passes & Runtime Daemon
    runtime_pass_interval_sec: float = field(
        default_factory=lambda: float(os.getenv("RUNTIME_PASS_INTERVAL_SEC", "5.0"))
    )
    enable_background_passes: bool = field(
        default_factory=lambda: os.getenv("ENABLE_BACKGROUND_PASSES", "true").lower() == "true"
    )
    effect_max_attempts: int = field(
        default_factory=lambda: int(os.getenv("EFFECT_MAX_ATTEMPTS", "3"))
    )

    # Voiceprint & VAD Parameters
    host_similarity_threshold: float = field(
        default_factory=lambda: float(os.getenv("HOST_SIMILARITY_THRESHOLD", "0.65"))
    )
    guest_cluster_threshold: float = field(
        default_factory=lambda: float(os.getenv("GUEST_CLUSTER_THRESHOLD", "0.60"))
    )
    short_utterance_ms: int = field(
        default_factory=lambda: int(os.getenv("SHORT_UTTERANCE_MS", "1200"))
    )
    inherit_speaker_window_sec: float = field(
        default_factory=lambda: float(os.getenv("INHERIT_SPEAKER_WINDOW_SEC", "3.0"))
    )
    max_guest_centroids: int = field(
        default_factory=lambda: int(os.getenv("MAX_GUEST_CENTROIDS", "5"))
    )

    # Episode Segmenter State Machine
    silence_split_seconds: int = field(
        default_factory=lambda: int(os.getenv("SILENCE_SPLIT_SECONDS", "180"))
    )
    max_episode_duration_seconds: int = field(
        default_factory=lambda: int(os.getenv("MAX_EPISODE_DURATION_SECONDS", "1500"))
    )
    overlap_context_utterances: int = field(
        default_factory=lambda: int(os.getenv("OVERLAP_CONTEXT_UTTERANCES", "5"))
    )
    meeting_bystander_mode: bool = field(
        default_factory=lambda: os.getenv("MEETING_BYSTANDER_MODE", "false").lower() == "true"
    )

    # Cognitive LLM Engine & Custom Domain Prompt
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
    )
    llm_api_key: Optional[str] = field(default_factory=lambda: os.getenv("LLM_API_KEY"))
    llm_api_base: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1")
    )
    custom_extraction_prompt: Optional[str] = field(
        default_factory=lambda: os.getenv("CUSTOM_EXTRACTION_PROMPT") or None
    )
    custom_extraction_prompt_file: Optional[str] = field(
        default_factory=lambda: os.getenv("CUSTOM_EXTRACTION_PROMPT_FILE") or None
    )

    # Proactive Daily Memo Schedule
    morning_memo_cron_hour: int = field(
        default_factory=lambda: int(os.getenv("MORNING_MEMO_CRON_HOUR", "8"))
    )
    morning_memo_cron_minute: int = field(
        default_factory=lambda: int(os.getenv("MORNING_MEMO_CRON_MINUTE", "30"))
    )
    evening_memo_cron_hour: int = field(
        default_factory=lambda: int(os.getenv("EVENING_MEMO_CRON_HOUR", "21"))
    )
    evening_memo_cron_minute: int = field(
        default_factory=lambda: int(os.getenv("EVENING_MEMO_CRON_MINUTE", "30"))
    )

    # Directories & Connectors
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "./data")))
    models_dir: Path = field(default_factory=lambda: Path(os.getenv("MODELS_DIR", "./models")))
    obsidian_sync_enabled: bool = field(
        default_factory=lambda: os.getenv("OBSIDIAN_SYNC_ENABLED", "true").lower() == "true"
    )
    webhook_url: Optional[str] = field(default_factory=lambda: os.getenv("WEBHOOK_URL") or None)

    def model_dump(self) -> Dict[str, Any]:
        d = asdict(self)
        d["data_dir"] = str(self.data_dir)
        d["models_dir"] = str(self.models_dir)
        return d

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "sqlite.db"

    @property
    def voiceprint_path(self) -> Path:
        vp_dir = self.data_dir / "voiceprint"
        vp_dir.mkdir(parents=True, exist_ok=True)
        return vp_dir / "host_embedding.json"

    @property
    def audio_inbox_dir(self) -> Path:
        inbox = self.data_dir / "audio_inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        return inbox

    @property
    def audio_archive_dir(self) -> Path:
        archive = self.data_dir / "audio_archive"
        archive.mkdir(parents=True, exist_ok=True)
        return archive

    @property
    def obsidian_vault_dir(self) -> Path:
        vault = self.data_dir / "obsidian_vault"
        vault.mkdir(parents=True, exist_ok=True)
        return vault


settings = Settings()
