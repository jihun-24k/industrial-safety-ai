import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('JWT_SECRET', 'test-live-stt-secret-not-for-deployment')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from jose import jwt
from app.routers import stt_stream_router as module


class LiveSttTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(module.router,prefix='/stt')
        self.client=TestClient(app)
        token=jwt.encode({'sub':'fixture','username':'test','iss':'simple-auth-server','exp':int(time.time())+3600},module.JWT_SECRET,algorithm='HS256')
        self.headers={'origin':'http://127.0.0.1:5173','cookie':'ACCESS_TOKEN='+token}

    def connect(self, headers=None):
        return self.client.websocket_connect('/stt/stream',headers=headers or self.headers)

    def start(self,socket):
        socket.send_json({'type':'start','sample_rate':16000,'format':'pcm_s16le'})
        self.assertEqual(socket.receive_json(),{'type':'ready'})

    def test_partial_arrives_before_finish_and_final_uses_latest_audio(self):
        calls=[]
        def transcribe(data,final):
            calls.append((len(data),final));return '최종 질문' if final else '중간 질문'
        with patch.object(module,'get_transcriber',return_value=transcribe):
            with self.connect() as socket:
                self.start(socket)
                socket.send_bytes(bytes(32000))
                self.assertEqual(socket.receive_json(),{'type':'partial','text':'중간 질문'})
                socket.send_bytes(bytes(3200));socket.send_json({'type':'finish'})
                self.assertEqual(socket.receive_json(),{'type':'final','text':'최종 질문'})
        self.assertEqual(calls,[(32000,False),(35200,True)])

    def test_empty_audio_has_no_transcription_and_does_not_leak_previous_session(self):
        with patch.object(module,'get_transcriber') as factory:
            with self.connect() as socket:
                self.start(socket);socket.send_json({'type':'finish'})
                self.assertEqual(socket.receive_json(),{'type':'final','text':''})
            factory.return_value.assert_not_called()

    def test_cookie_and_origin_are_checked(self):
        for headers,code in [({'origin':'http://127.0.0.1:5173'},4401),
                             ({**self.headers,'origin':'https://untrusted.example'},4403)]:
            with self.connect(headers) as socket:
                with self.assertRaises(WebSocketDisconnect) as raised:socket.receive_json()
                self.assertEqual(raised.exception.code,code)

    def test_invalid_format_and_oversized_frames_are_rejected(self):
        with self.connect() as socket:
            socket.send_json({'type':'start','sample_rate':48000,'format':'pcm_s16le'})
            self.assertEqual(socket.receive_json()['type'],'error')
        with patch.object(module,'get_transcriber') as factory:
            with self.connect() as socket:
                self.start(socket);socket.send_bytes(bytes(64000))
                self.assertEqual(socket.receive_json()['type'],'error')
            factory.return_value.assert_not_called()

    def test_provider_failure_is_sanitized(self):
        def broken(*args):raise RuntimeError('PRIVATE_ERROR_BODY')
        with patch.object(module,'get_transcriber',return_value=broken):
            with self.connect() as socket:
                self.start(socket);socket.send_bytes(bytes(3200));socket.send_json({'type':'finish'})
                result=socket.receive_json()
                self.assertEqual(result['type'],'error');self.assertNotIn('PRIVATE',str(result))


if __name__=='__main__':unittest.main()
