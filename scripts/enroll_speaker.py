#!/usr/bin/env python3
"""CLI tool to enroll the owner's (`[HOST]`) voiceprint from a WAV file or synthetic sample."""
import argparse
from pathlib import Path
import numpy as np
import soundfile as sf
from backend.audio_engine.speaker_id import get_speaker_identifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Enroll HOST voiceprint for EchoMind.")
    parser.add_argument("--wav", type=Path, help="Path to a 10~30s 16kHz WAV file of your voice")
    parser.add_argument("--demo", action="store_true", help="Enroll a synthetic demo host voiceprint")
    args = parser.parse_args()

    identifier = get_speaker_identifier()
    if args.wav and args.wav.exists():
        samples, sr = sf.read(str(args.wav), dtype="float32")
        if samples.ndim > 1:
            samples = samples[:, 0]
        emb = identifier.enroll_host_voice(samples, sample_rate=sr)
        print(f"[✓] Enrolled HOST voiceprint from {args.wav} (dim={len(emb)}) -> {identifier.voiceprint_path}")
    elif args.demo:
        t = np.linspace(0, 3.0, 16000 * 3, endpoint=False, dtype=np.float32)
        demo_wave = 0.5 * np.sin(2 * np.pi * 180.0 * t) + 0.25 * np.sin(2 * np.pi * 360.0 * t)
        emb = identifier.enroll_host_voice(demo_wave, sample_rate=16000)
        print(f"[✓] Enrolled demo HOST voiceprint (dim={len(emb)}) -> {identifier.voiceprint_path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
