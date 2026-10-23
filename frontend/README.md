# 세이프메이트 프론트엔드

Vue 3 + Vite 기반 로그인·채팅 UI입니다. Java·Python 서버 코드는 수정하지 않습니다.

`frontend` 디렉터리에서 실행합니다.

```sh
cd frontend
npm ci
npm run dev
```

`http://127.0.0.1:5173/`로 접속합니다. 진입점은 `frontend/index.html`입니다. 이전의 `python -m http.server` 대신 Vite를 사용해야 합니다. 로그인 화면의 **화면 미리보기**는 서버 없이 예시 대화와 브라우저 TTS를 제공합니다. 실제 로그인과 구분하며, 실제 자료 검색이나 업로드를 하지 않습니다.

## 디렉터리 구조

```text
frontend/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── api/          # HTTP 요청 및 서비스별 API 연결
    ├── components/   # 재사용 가능한 화면 요소
    ├── pages/        # 로그인·채팅 페이지
    ├── styles/       # 전역 스타일
    ├── App.vue       # 인증 상태와 페이지 전환
    └── main.js       # Vue 진입점
```

## 기존 서비스 연결

Vite 개발 프록시가 브라우저의 같은 출처 요청과 인증 쿠키를 기존 서버에 전달합니다.

| 프론트 경로 | 기존 서비스 |
| --- | --- |
| `/auth-api/*` | `http://localhost:8080/api/*` |
| `/rag-api/*` | `http://localhost:8001/*` |
| `/voice-api/*` | `http://localhost:8008/*` |

로그인은 기존 `POST /api/login`, 상태 확인은 `GET /api/auth/check`를 사용합니다. 서버의 음성 화면 리다이렉트 대신 현재 Vue 채팅 화면을 엽니다. 비밀번호와 토큰은 브라우저 저장소에 저장하지 않습니다.

채팅은 `POST /rag-query`에 `{ prompt, source, top_k: 5 }`를 전송합니다. 현재 API는 단일 질문만 받으므로 화면의 이전 대화 내용은 다음 요청에 포함되지 않습니다. 대화 기록은 메모리에만 유지되고 새로고침 또는 로그아웃하면 사라집니다.

PDF 첨부는 `POST /upload-paper`를 사용하고 검색 대상을 PDF로 전환합니다. 웹 자료는 기존에 수집된 FAISS 인덱스를 사용하며 뉴스 수집은 기존 `POST /upload-topic?topic=검색어` API를 별도로 호출해야 합니다. 기존 백엔드의 웹/PDF 인덱스는 서버 전체에서 공유되며 사용자별 격리는 지원하지 않습니다. 내부 RAG 백엔드는 현재 저장소에 없어 연결하지 않았습니다.

답변 아래 **답변 듣기**는 `POST /tts/`에 `text` 폼을 보내고, 반환된 `/uploads/…` 음성을 재생합니다. 클릭하면 재생을 중지할 수 있습니다. 기존 서버가 동일한 음성 파일명을 사용하므로 다중 사용자 동시 재생은 별도 백엔드 개선이 필요합니다. 음성 오류는 화면에 표시합니다.

## 빌드

```sh
npm run build
```

`dist/`를 생성합니다. Vite 프록시는 개발 전용입니다. 배포 시 웹 서버에서 위 세 경로의 리버스 프록시를 설정해야 합니다. `npm run preview`는 정적 빌드 확인용이며 실제 API 프록시를 제공하지 않습니다.

실제 로그인에는 인증 서버의 `DB_PASSWORD`, `JWT_SECRET` 실행 환경 설정이 필요합니다. Java 인증 서버의 JWT 키는 기존 음성 서버의 검증 키와 일치해야 합니다. 로컬 실행용 `.cache/runtime/` 스크립트·설정은 Git에 포함되지 않습니다.
