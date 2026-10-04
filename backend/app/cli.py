"""Maintenance commands.

    python -m app.cli download-asr-model small   # needs internet (huggingface.co)
    python -m app.cli capabilities
    python -m app.cli retention
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    dl = sub.add_parser("download-asr-model", help="Download a faster-whisper model into the cache")
    dl.add_argument("model", nargs="?", default=None)
    sub.add_parser("capabilities", help="Show which engines are available")
    sub.add_parser("retention", help="Apply the retention policy now")
    args = parser.parse_args()
    settings = get_settings()

    if args.cmd == "download-asr-model":
        from faster_whisper.utils import download_model
        model = args.model or settings.whisper_model
        path = download_model(model, cache_dir=settings.whisper_download_root or None)
        print(f"Model '{model}' tersimpan di: {path}")
    elif args.cmd == "capabilities":
        from .services import build_services
        s = build_services(settings)
        print(json.dumps({
            "ocr": s.ocr.describe() if s.ocr else None,
            "tts": [asdict(e.info()) for e in s.tts.values()],
            "asr": asdict(s.asr.info()),
            "diarization": asdict(s.diarization.info()),
            "intelligence": s.intelligence.info(),
        }, indent=2, ensure_ascii=False))
    elif args.cmd == "retention":
        from .services import apply_retention, build_services
        print(apply_retention(build_services(settings)))


if __name__ == "__main__":
    main()
