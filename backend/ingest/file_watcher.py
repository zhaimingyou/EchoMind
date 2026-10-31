"""Local Audio Inbox Watcher (Plaud Note / Voice Recorder / iPhone Shortcut Sync).

Monitors `data/audio_inbox/` for dropped `.wav` or `.txt` transcript files,
processes them through the VAD + Speaker ID + SenseVoice + Episode Segmenter pipeline,
and archives processed files into `data/audio_archive/`.
"""
import logging
from pathlib import Path
import shutil
from typing import List, Optional
import numpy as np
import soundfile as sf
from backend.audio_engine.vad_buffer import VADStreamBuffer
from backend.config import settings
from backend.ingest.ws_stream import get_stream_gateway
from backend.memory_core.segmenter import get_segmenter
from backend.storage.models import Episode, Utterance

logger = logging.getLogger("echomind.file_watcher")


class AudioInboxProcessor:
    """Processes audio files dropped into `data/audio_inbox/`."""

    def __init__(
        self,
        inbox_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
    ) -> None:
        self.inbox_dir = inbox_dir or settings.audio_inbox_dir
        self.archive_dir = archive_dir or settings.audio_archive_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    async def process_file(self, file_path: Path) -> Optional[Episode]:
        """Process a single `.wav` audio file and trigger Episode extraction."""
        if not file_path.exists():
            return None

        gateway = get_stream_gateway()
        device_id = f"inbox_{file_path.stem}"

        if file_path.suffix.lower() == ".wav":
            samples, sr = sf.read(str(file_path), dtype="float32")
            if samples.ndim > 1:
                samples = samples[:, 0]
            vad = VADStreamBuffer(sample_rate=sr)
            chunks = vad.accept_float_samples(samples) + vad.flush()
            if not chunks and len(samples) > 0:
                await gateway.ingest_audio_chunk(
                    samples=samples,
                    duration_ms=int(len(samples) * 1000 / max(sr, 1)),
                    device_id=device_id,
                    sample_rate=sr,
                )
            else:
                for ch in chunks:
                    await gateway.ingest_audio_chunk(
                        samples=ch.samples,
                        duration_ms=ch.duration_ms,
                        device_id=device_id,
                        sample_rate=sr,
                    )

        dest = self.archive_dir / file_path.name
        shutil.move(str(file_path), str(dest))
        logger.info("Processed and archived inbox file: %s -> %s", file_path.name, dest)
        return await get_segmenter().inspect_and_segment(force_flush=True)

    async def scan_inbox_once(self) -> List[Episode]:
        """Scan `data/audio_inbox/` for any pending `.wav` files and process them."""
        created: List[Episode] = []
        for wav_file in sorted(self.inbox_dir.glob("*.wav")):
            ep = await self.process_file(wav_file)
            if ep:
                created.append(ep)
        return created


_default_inbox: Optional[AudioInboxProcessor] = None


def get_inbox_processor() -> AudioInboxProcessor:
    global _default_inbox
    if _default_inbox is None:
        _default_inbox = AudioInboxProcessor()
    return _default_inbox
