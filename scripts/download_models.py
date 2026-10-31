#!/usr/bin/env python3
"""On-demand downloader for EchoMind's pure-CPU ONNX models (Sherpa-ONNX).

Keeps the Git repository 100% pure MIT code without bundling heavy binary weights.
Downloads:
1. SenseVoice-Small (int8 quantized)
2. Silero-VAD v4 ONNX
3. Alibaba 3D-Speaker ERes2Net (16kHz Chinese/English speaker verification)
"""
import argparse
from pathlib import Path
import tarfile
import urllib.request

SENSEVOICE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
)
SILERO_VAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
)
SPEAKER_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
    "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
)


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"[✓] Already exists: {dest}")
        return
    print(f"[↓] Downloading {url} -> {dest} ...")
    urllib.request.urlretrieve(url, str(dest))
    print(f"[✓] Saved {dest} ({dest.stat().st_size // (1024 * 1024)} MB)")


def setup_models(models_dir: Path, dry_run: bool = False) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    vad_dest = models_dir / "vad" / "silero_vad.onnx"
    spk_dest = models_dir / "speaker" / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
    sv_dir = models_dir / "sensevoice"

    if dry_run:
        print("=== EchoMind ONNX Model Manifest (Dry Run) ===")
        print(f"1. Silero-VAD      : {SILERO_VAD_URL} -> {vad_dest}")
        print(f"2. 3D-Speaker      : {SPEAKER_MODEL_URL} -> {spk_dest}")
        print(f"3. SenseVoice-Small: {SENSEVOICE_URL} -> {sv_dir}/")
        return

    download_file(SILERO_VAD_URL, vad_dest)
    download_file(SPEAKER_MODEL_URL, spk_dest)

    if not (sv_dir / "model.int8.onnx").exists():
        archive_path = models_dir / "sensevoice.tar.bz2"
        download_file(SENSEVOICE_URL, archive_path)
        print("[*] Extracting SenseVoice-Small (int8) ...")
        with tarfile.open(archive_path, "r:bz2") as tar:
            tar.extractall(path=models_dir)
        extracted_folder = models_dir / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
        if extracted_folder.exists():
            extracted_folder.rename(sv_dir)
        archive_path.unlink(missing_ok=True)
        print(f"[✓] SenseVoice ready at {sv_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download EchoMind ONNX models.")
    parser.add_argument("--models-dir", type=Path, default=Path("./models"))
    parser.add_argument("--dry-run", action="store_true", help="Print model URLs without downloading")
    args = parser.parse_args()
    setup_models(args.models_dir, dry_run=args.dry_run)
