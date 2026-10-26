"""Generate MP3 speech with configurable model and voice."""
import os
from pathlib import Path
import requests

MAX_SPEECH_LENGTH = 4096


def text_to_speech(text: str, output_path: str = "output.mp3"):
    if not text.strip() or len(text) > MAX_SPEECH_LENGTH:
        raise ValueError("음성으로 읽을 내용은 1~4,096자여야 합니다. 답변을 짧게 나누어 주세요.")
    response = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": os.getenv("TTS_MODEL", "tts-1"),
            "input": text,
            "voice": os.getenv("TTS_VOICE", "nova"),
            "response_format": "mp3",
        },
        timeout=(10, 40),
    )
    if response.status_code != 200 or not response.content:
        raise RuntimeError("Speech provider failed")
    Path(output_path).write_bytes(response.content)
    return output_path
