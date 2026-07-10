#!/usr/bin/env python3
"""Generate static/ivr-menu.mp3 for the Twilio Gather IVR prompt.

Prefers ElevenLabs (same voice as ConversationRelay) when ELEVENLABS_API_KEY
is set. Falls back to OpenAI TTS so demos still work without an ElevenLabs key.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from scripts.seed import IVR_PROMPT

# Must match the voice id embedded in api/twilio_voice.py MIRA_TTS_VOICE.
ELEVENLABS_VOICE_ID = "tnSpp4vdxKPjI9w0GnoV"
OUT_PATH = ROOT / "static" / "ivr-menu.mp3"


def _generate_elevenlabs(text: str, api_key: str) -> bytes:
    import urllib.error
    import urllib.request
    import json

    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        f"?output_format=mp3_44100_128"
    )
    body = json.dumps(
        {
            "text": text,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs TTS failed ({exc.code}): {detail}") from exc


def _generate_openai(text: str, api_key: str) -> bytes:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    # Temporary stand-in when ELEVENLABS_API_KEY is missing.
    speech = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="coral",
        input=text,
        response_format="mp3",
    )
    return speech.content


def main() -> None:
    # Brief lead-in so the first word isn't clipped on some handsets.
    text = f"... {IVR_PROMPT}"
    eleven_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if eleven_key:
        print(f"Generating IVR audio with ElevenLabs voice {ELEVENLABS_VOICE_ID}...")
        audio = _generate_elevenlabs(text, eleven_key)
        source = "elevenlabs"
    elif openai_key:
        print(
            "ELEVENLABS_API_KEY not set — generating with OpenAI TTS (coral). "
            "Add ELEVENLABS_API_KEY and re-run for an exact ConversationRelay voice match."
        )
        audio = _generate_openai(text, openai_key)
        source = "openai"
    else:
        raise SystemExit("Set ELEVENLABS_API_KEY or OPENAI_API_KEY to generate IVR audio.")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_bytes(audio)
    print(f"Wrote {OUT_PATH} ({len(audio)} bytes, source={source})")


if __name__ == "__main__":
    main()
