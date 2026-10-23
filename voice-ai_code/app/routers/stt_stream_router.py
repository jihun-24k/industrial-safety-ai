"""Authenticated PCM streaming to local Whisper; no paid transcription API."""
import asyncio
import json
import os
from contextlib import suppress
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.config import JWT_SECRET

router = APIRouter()
SAMPLE_RATE = 16000
MAX_BYTES = SAMPLE_RATE * 2 * 61


def get_transcriber():
    from app.services.stt_service import transcribe_pcm16
    return transcribe_pcm16


def valid_origin(origin):
    allowed = os.getenv('STT_ALLOWED_ORIGINS') or 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8008,http://127.0.0.1:8008'
    return origin in {item.strip() for item in allowed.split(',') if item.strip()}


@router.websocket('/stream')
async def live_stt(websocket: WebSocket):
    await websocket.accept()
    if not valid_origin(websocket.headers.get('origin')):
        await websocket.close(code=4403, reason='Origin not allowed')
        return
    try:
        payload = jwt.decode(websocket.cookies.get('ACCESS_TOKEN', ''), JWT_SECRET,
                             algorithms=['HS256'], issuer='simple-auth-server')
        if not payload.get('sub') or not payload.get('username'):
            raise ValueError('Invalid user')
    except (JWTError, ValueError):
        await websocket.close(code=4401, reason='Login required')
        return

    worker = None
    changed = asyncio.Event()
    finishing = False
    audio = bytearray()
    try:
        start = await asyncio.wait_for(websocket.receive_json(), 10)
        if start != {'type': 'start', 'sample_rate': SAMPLE_RATE, 'format': 'pcm_s16le'}:
            raise ValueError('Invalid audio format')
        transcribe = get_transcriber()
        await websocket.send_json({'type': 'ready'})

        async def update_text():
            last_size, previous = 0, ''
            while True:
                await changed.wait()
                changed.clear()
                if finishing:
                    return
                # Coalesce incoming frames; never queue one inference per frame.
                if len(audio) - last_size < SAMPLE_RATE * 2:
                    continue
                snapshot = bytes(audio)
                last_size = len(snapshot)
                text = await asyncio.to_thread(transcribe, snapshot, False)
                if text and text != previous:
                    previous = text
                    await websocket.send_json({'type': 'partial', 'text': text})

        worker = asyncio.create_task(update_text())
        while True:
            message = await asyncio.wait_for(websocket.receive(), 20)
            if message['type'] == 'websocket.disconnect':
                raise WebSocketDisconnect(message.get('code', 1000))
            if worker.done():
                worker.result()
            packet = message.get('bytes')
            if packet is not None:
                if not packet or len(packet) % 2 or len(packet) > SAMPLE_RATE * 2 or len(audio) + len(packet) > MAX_BYTES:
                    raise ValueError('Audio limit exceeded')
                audio.extend(packet)
                changed.set()
            elif message.get('text') is not None:
                command = json.loads(message['text'])
                if command != {'type': 'finish'}:
                    raise ValueError('Unknown command')
                finishing = True
                changed.set()
                await asyncio.wait_for(worker, 60)
                text = await asyncio.wait_for(asyncio.to_thread(transcribe, bytes(audio), True), 60) if audio else ''
                await websocket.send_json({'type': 'final', 'text': text})
                await websocket.close()
                return
    except WebSocketDisconnect:
        pass
    except Exception:
        with suppress(Exception):
            await websocket.send_json({'type': 'error', 'message': '실시간 음성 인식을 완료하지 못했습니다. 다시 시도해 주세요.'})
            await websocket.close(code=1011)
    finally:
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await worker
        audio.clear()
