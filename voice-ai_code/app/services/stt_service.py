import os
import subprocess
from faster_whisper import WhisperModel
import threading
import numpy as np

TRANSCRIPTION_LOCK = threading.Lock()

# 1) Do not use GPU/MPS: fixed to CPU
DEVICE = "cpu"

# 2) Load model
#    Adjust to "base", "small", "medium", etc. as needed
#    On CPU, int8 provides better speed/memory stability.
MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type="int8")


def convert_webm_to_wav(webm_path: str, wav_path: str) -> None:
    """
    Converts a webm file to a wav file.
    Calls ffmpeg directly. (More stable for installation/runtime than pydub)
    Sets mono channel + 16kHz for STT stability.
    """
    if not os.path.exists(webm_path):
        raise FileNotFoundError(f"Input not found: {webm_path}")

    out_dir = os.path.dirname(wav_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",                # overwrite
        "-i", webm_path,
        "-ac", "1",          # mono
        "-ar", "16000",      # 16kHz
        "-vn",               # no video
        wav_path,
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg convert failed: {proc.stderr.strip()}")


def transcribe_audio_file_local(file_path: str) -> str:
    """
    Performs STT using the local Whisper model.
    (Uses faster-whisper)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input not found: {file_path}")

    # faster-whisper returns a segments generator.
    with TRANSCRIPTION_LOCK:
        segments, info = model.transcribe(file_path, beam_size=5, vad_filter=True)
        text = "".join(seg.text for seg in segments).strip()
    return text


def transcribe_pcm16(audio: bytes, final: bool = False) -> str:
    """PCM s16le, mono 16 kHz. Consume the lazy segment iterator under the lock."""
    if not audio:
        return ''
    samples = np.frombuffer(audio, dtype='<i2').astype(np.float32) / 32768.0
    with TRANSCRIPTION_LOCK:
        segments, _ = model.transcribe(samples, beam_size=5 if final else 1, vad_filter=True)
        return ''.join(segment.text for segment in segments).strip()


def transcribe_audio_file(file_path: str) -> str:
    """
    Wrapper for backward compatibility with existing code.
    (Ensures compatibility with code that previously used transcribe_audio_file)
    """
    return transcribe_audio_file_local(file_path)
