# 음성 서비스

Docker 실행은 프로젝트 루트의 `compose.yaml`을 사용합니다.

```bash
# 프로젝트 루트에서 실행
docker compose up -d --build voice
docker compose logs -f voice
```

루트 `.env`에 `OPENAI_API_KEY`, 인증 서버와 동일한 `JWT_SECRET`을 설정합니다. 실제 채팅과 함께 사용하려면 루트에서 `docker compose up -d --build`로 전체 구성을 실행합니다. 자세한 내용은 [전체 Compose 안내](../docs/DOCKER_COMPOSE.md)를 참고하세요.

## 호스트에서 직접 실행할 때 필요한 준비

# Install ffmpeg (Linux Ubuntu)
sudo apt update
sudo apt install -y ffmpeg pkg-config

# Install ffmpeg (MacOS)
brew install ffmpeg
ffmpeg -version

# With virtual environment activated
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt