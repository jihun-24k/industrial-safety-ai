#### 다음 실습 코드는 학습 목적으로만 사용 바랍니다. 문의 : audit@korea.ac.kr 임성열 Ph.D.

import hashlib
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.engine import URL
from sqlalchemy import text
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from pydantic import AwareDatetime, BaseModel, Field
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from pypdf import PdfReader
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# 패키지는 저자 업데이트에 맞춰 해당 버전으로 맞추는 것을 권장
# 직접 저자의 site-packages/패키지명/을 직접 수정하는 것은 추천하지 않음
# 추후 pip install -U 시 원상 복구되며 버전 충돌 가능성 있음angchain.text_splitter 
# 참고로 다음은 Deprecated 패키지 또는 미사용 패키지 목록
# from langchain_community.embeddings import HuggingFaceEmbeddings
# from langchain.vectorstores import FAISS
# from langchain.chat_models import ChatOpenAI
# from langchain.embeddings import OpenAIEmbeddings
# from langchain_openai import OpenAIEmbeddings, ChatOpenAI
# from langchain_community.embeddings import OpenAIEmbeddings
# from langchain.chat_models import ChatOpenAI
# from langchain.schema import HumanMessage
# from langchain.embeddings import HuggingFaceEmbeddings  
# from pydantic import BaseModel

from typing import List, Dict, Any, Optional, Literal
import os
import re
import json
import asyncio
import tempfile
import uuid
import httpx
import tiktoken
from datetime import datetime, UTC
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import os
from pathlib import Path
from dotenv import load_dotenv

# 현재 Python 파일과 같은 위치에 있는 .env 파일 로드
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

# ✅ RAG 설정 (.env로 변경 가능)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
MAX_DISTANCE = float(os.getenv("RAG_MAX_DISTANCE", "0"))          # 0이면 거리 필터 끔
RESET_PDF_ON_UPLOAD = os.getenv("RESET_PDF_ON_UPLOAD", "false").lower() == "true"  # true면 업로드마다 교체

# ✅ 조원 데이터 파이프라인(pipeline/) 인덱스 연결
#   - 인덱스는 프로젝트 루트에서 `python -m pipeline.pdf_pipeline prepare` → `build` 로 만든다
#   - pipeline_artifacts/current.json 이 있으면 PDF 검색은 이 인덱스를 사용한다
import sys
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from pipeline.retrieval_context import path_text, select_context_rows
from pipeline.safety_workflow import assemble as assemble_safety, ANSWER_POLICY, generation_requirements, ensure_contact_details, is_information_only
from pipeline.knowledge_graph import evidence_eligible
try:
    from pipeline import pdf_pipeline as team_pipeline
    TEAM_CFG = team_pipeline.config_at(PROJECT_ROOT / "pipeline" / "config.json")
    USE_TEAM_INDEX = (TEAM_CFG["output_root"] / "current.json").exists()
    TEAM_EMBEDDER = team_pipeline.embeddings(TEAM_CFG) if USE_TEAM_INDEX else None
except Exception as e:
    print(f"⚠️ 팀 파이프라인을 불러오지 못했습니다: {e}")
    USE_TEAM_INDEX = False
print("✅ PDF 검색: 팀 파이프라인 인덱스 사용" if USE_TEAM_INDEX else "ℹ️ PDF 검색: faiss_db/pdf 사용")

# ✅ 검색 계획(Query Planning): 사고 질문을 최대 8개 검색어로 나눠서 찾기
SEARCH_PLAN_FILE = BASE_DIR / "prompts" / "search_plan.txt"
SEARCH_PLAN_PROMPT = SEARCH_PLAN_FILE.read_text(encoding="utf-8") if SEARCH_PLAN_FILE.exists() else ""
USE_SEARCH_PLAN = os.getenv("USE_SEARCH_PLAN", "true").lower() == "true" and bool(SEARCH_PLAN_PROMPT)
MAX_PLAN_QUERIES = 8      # 프롬프트 규칙: 최대 8개 질의
PLAN_TOP_K = 3            # 계획 검색어 하나당 가져올 청크 수
MAX_CONTEXT_DOCS = 20     # LLM에게 넘길 최대 청크 수
print("✅ 검색 계획 사용" if USE_SEARCH_PLAN else "ℹ️ 검색 계획 끔 (prompts/search_plan.txt 없음 또는 USE_SEARCH_PLAN=false)")

# ✅ DB 연결 정보
ASYNC_DB_URL = os.getenv("ASYNC_DB_URL") or (
    URL.create("mysql+aiomysql", username=os.getenv("DB_USER", "root"),
               password=os.getenv("DB_PASSWORD"), host=os.environ["DB_HOST"],
               port=int(os.getenv("DB_PORT", "3306")), database=os.getenv("DB_NAME", "sql_db"),
               query={"charset": "utf8mb4"})
    if os.getenv("DB_HOST") else "mysql+aiomysql://root:password@127.0.0.1:53301/sql_db?charset=utf8mb4"
)
engine = create_async_engine(ASYNC_DB_URL)
AUTH_CHECK_URL = os.getenv("AUTH_CHECK_URL", "http://127.0.0.1:8080/api/auth/check")
HISTORY_TOKEN_BUDGET = int(os.getenv("HISTORY_TOKEN_BUDGET", "6000"))
RECENT_HISTORY_TOKEN_BUDGET = int(os.getenv("RECENT_HISTORY_TOKEN_BUDGET", "3000"))
SUMMARY_TOKEN_BUDGET = 1500

# ✅ FastAPI 인스턴스
app = FastAPI(
    title="RAG 기반 Closed Source LLM API Server",
    description="외부 정보 기반 벡터화 + LLM 질의 응답",
    version="1.0.0"
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174",
                   "http://127.0.0.1:5174",
                   "http://[::1]:5174",         # IPv6도 허용
                   "http://localhost:8001","*"],
    allow_methods=["*"], allow_headers=["*"], allow_credentials=True,
)

CHAT_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS chat_conversations (
      id CHAR(36) NOT NULL,
      owner_username VARCHAR(100) NOT NULL,
      title VARCHAR(255) NOT NULL,
      summary LONGTEXT NULL,
      summary_through_message_id BIGINT UNSIGNED NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_chat_conversations_owner_updated (owner_username, updated_at),
      CONSTRAINT fk_chat_conversations_owner FOREIGN KEY (owner_username)
        REFERENCES users (username) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      conversation_id CHAR(36) NOT NULL,
      role VARCHAR(16) NOT NULL,
      text LONGTEXT NOT NULL,
      sources JSON NULL,
      needs_review BOOLEAN NOT NULL DEFAULT FALSE,
      handoff BOOLEAN NOT NULL DEFAULT FALSE,
      clarifying_questions JSON NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_chat_messages_conversation_id (conversation_id, id),
      CONSTRAINT fk_chat_messages_conversation FOREIGN KEY (conversation_id)
        REFERENCES chat_conversations (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


@app.on_event("startup")
async def create_chat_tables():
    """기존 MariaDB 볼륨에도 대화 저장용 테이블을 안전하게 추가한다."""
    async with engine.begin() as connection:
        for statement in CHAT_SCHEMA:
            await connection.execute(text(statement))

# ✅ 전역 벡터 저장소
VECTORSTORE_WEB = None
VECTORSTORE_PDF = None

# 벡터 스토어 전역 변수
VECTORSTORE_WEB = None
VECTORSTORE_PDF = None

# ✅ 외부 (웹검색, OpenAI 전용)
web_path = "faiss_db/web"
if os.path.exists(f"{web_path}/index.faiss") and os.path.exists(f"{web_path}/index.pkl"):
    VECTORSTORE_WEB = FAISS.load_local(
        web_path,
        embeddings=OpenAIEmbeddings(),
        allow_dangerous_deserialization=True
    )
    print("✅ VECTORSTORE_WEB 로드 완료")
else:
    print("❌ VECTORSTORE_WEB 벡터화된 파일이 없습니다.")

# ✅ PDF (업로드용, OpenAI 전용)
pdf_path = "faiss_db/pdf"
if os.path.exists(f"{pdf_path}/index.faiss") and os.path.exists(f"{pdf_path}/index.pkl"):
    VECTORSTORE_PDF = FAISS.load_local(
        pdf_path,
        embeddings=OpenAIEmbeddings(),  # ← 오타 수정
        allow_dangerous_deserialization=True
    )
    print("✅ VECTORSTORE_PDF 로드 완료")
else:
    print("❌ VECTORSTORE_PDF 벡터화된 파일이 없습니다.")

# ✅ PDF 텍스트 추출
def load_paper(file_path: str) -> str:
    reader = PdfReader(file_path)
    return "\n".join(text for page in reader.pages if (text := page.extract_text()))

# ✅ 웹 검색 → 외부 정보 벡터화
@app.post("/upload-topic", summary="웹 검색 → 외부 정보 벡터화", tags=["외부 정보"])
async def upload_topic(topic: str = Query(..., description="검색할 주제")):
    try:
        import os, re, aiohttp
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_community.vectorstores import FAISS
        from langchain_openai import OpenAIEmbeddings

        # ---- 1) 네이버 뉴스 검색: headers/params 전달 + 페이지네이션 ----
        NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
        NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

        search_url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        }

        want = 20          # 수집 목표 건수
        display = 20       # 요청 건수(최대 100 가능, 요금/정책 고려)
        start = 1
        items = []

        async with aiohttp.ClientSession() as session:
            while len(items) < want:
                params = {
                    "query": topic,
                    "display": display,
                    "start": start,     # 1, 21, 41 … (display에 맞춰 증가)
                    "sort": "date",
                }
                async with session.get(search_url, headers=headers, params=params) as resp:
                    # 상태 코드 확인 (401/429 등 조기 감지)
                    resp.raise_for_status()
                    data = await resp.json()

                batch = data.get("items", [])
                if not batch:
                    break

                # 네이버는 <b>…</b> 태그를 포함 → 제거
                def strip_tags(s: str) -> str:
                    return re.sub(r"</?b>", "", s or "")

                for it in batch:
                    it["title"] = strip_tags(it.get("title", ""))
                    it["description"] = strip_tags(it.get("description", ""))
                items.extend(batch)

                start += display
                if start > 1000:  # API 한계 보호
                    break

        if not items:
            return {"message": "검색 결과가 없습니다.", "collected": 0}

        # ---- 2) 텍스트 구성(제목+요약 위주) ----
        texts = [
            f"title: {it.get('title','')}\nlink: {it.get('link','')}\ndesc: {it.get('description','')}"
            for it in items
        ]
        # 너무 긴 텍스트는 잘라서 임베딩 안정화
        texts = [t[:3000] for t in texts]

        # ---- 3) 텍스트 분할 ----
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=80)
        docs = splitter.create_documents(texts)

        if not docs:
            return {"message": "벡터화할 문서가 없습니다.", "collected": len(items)}

        # ---- 4) 벡터화 ----
        global VECTORSTORE_WEB
        VECTORSTORE_WEB = FAISS.from_documents(docs, OpenAIEmbeddings())

        # ---- 5) 디스크 저장 ----
        save_path = "faiss_db/web"
        os.makedirs(save_path, exist_ok=True)
        VECTORSTORE_WEB.save_local(save_path)

        return {
            "message": f"{len(docs)}개의 웹 문서(청크) 벡터화 및 저장 완료",
            "collected": len(items),
            "sample_titles": [it.get("title", "") for it in items[:3]],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ PDF 업로드 및 벡터화
@app.post("/upload-paper", summary="PDF 업로드 및 벡터화", tags=["PDF 처리"]) 
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 허용됩니다.")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        try:
            reader = PdfReader(tmp_path)
            # 페이지별로 Document를 만들어 출처(문서명·페이지)를 메타데이터로 보존
            page_docs = [
                # 정제: PDF 레이아웃에서 생긴 탭·연속 공백을 공백 하나로
                Document(page_content=re.sub(r"[ \t]+", " ", t).strip(), metadata={"source": file.filename, "page": i + 1})
                for i, page in enumerate(reader.pages)
                if (t := (page.extract_text() or "")).strip()
            ]
        finally:
            os.unlink(tmp_path)
        paper_text = "\n".join(d.page_content for d in page_docs)
        if not paper_text.strip():
            raise HTTPException(status_code=422, detail="PDF에서 텍스트를 추출하지 못했습니다. 스캔 PDF라면 OCR이 필요합니다.")
        # [Q01] PDF 청크 설계: 1000자 단위, 100자 중첩 (페이지 메타데이터는 청크에 그대로 상속)
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.split_documents(page_docs)

        global VECTORSTORE_PDF
        # [Q02] OpenAI 임베딩 → FAISS. 기존 PDF 지식베이스가 있으면 교체하지 않고 누적
        if VECTORSTORE_PDF is None or RESET_PDF_ON_UPLOAD:
            VECTORSTORE_PDF = FAISS.from_documents(docs, OpenAIEmbeddings())
        else:
            VECTORSTORE_PDF.add_documents(docs)

        # ✅ 디스크에 저장
        os.makedirs("faiss_db/pdf", exist_ok=True)
        VECTORSTORE_PDF.save_local("faiss_db/pdf")

        return JSONResponse(content={
            "message": f"{len(docs)}개의 PDF 청크 벡터화 및 저장 완료",
            "extracted_characters": len(paper_text),
            "preview": paper_text[:300]
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 질의 요청/응답 모델 정의
# ✅ 질의 요청 모델
class RAGRequest(BaseModel):
    prompt: str = Field(default=..., min_length=2, max_length=6000, description="질문 프롬프트")
    source: Literal["web", "pdf"] = Field(default=..., description="web | pdf")
    top_k: int = Field(default=5, ge=1, le=20, description="검색할 결과 수 (기본값 5)")
    conversation_id: Optional[str] = Field(default=None, max_length=36)
    institution_scope: Optional[str] = Field(default=None, max_length=200)
    accident_classification: Optional[Literal["major", "non_major"]] = None
    contact_at: Optional[AwareDatetime] = Field(default=None, description="연락 시간 필터: 시간대 포함 ISO datetime")

    class Config:
        validate_by_name = True

# ✅ 응답 모델: 교재 Day2 REST API 스키마 (answer · sources · needs_review · handoff)
class AnswerResponse(BaseModel):
    prompt: str
    answer: str
    sources: List[str] = []
    needs_review: bool = False   # 긴급·부상 상황 → 사람(안전관리자) 확인 필요
    handoff: bool = False        # 근거 없음 → 답변 대신 담당자에게 넘김
    search_queries: List[str] = []        # 검색 계획으로 만든 검색어 (확인·디버깅용)
    clarifying_questions: List[str] = []  # 판단에 필요한 추가 질문 (검색 계획이 제안)
    graph_retrieval: dict = Field(default_factory=dict)
    conversation_id: str
    title: str


def _json_value(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


async def authenticated_username(request: Request) -> str:
    cookie = request.headers.get("cookie")
    if not cookie:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(AUTH_CHECK_URL, headers={"cookie": cookie})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="인증 서비스를 사용할 수 없습니다.") from exc
    if response.status_code in (401, 403):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    if not response.is_success:
        raise HTTPException(status_code=503, detail="인증 서비스를 사용할 수 없습니다.")
    try:
        username = response.json().get("username")
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="인증 서비스 응답이 올바르지 않습니다.") from exc
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return str(username)


async def _owned_conversation(connection, conversation_id: str, username: str):
    result = await connection.execute(text("""
        SELECT id, title, summary, summary_through_message_id, created_at, updated_at
        FROM chat_conversations
        WHERE id = :conversation_id AND owner_username = :username
    """), {"conversation_id": conversation_id, "username": username})
    return result.mappings().first()


@app.get("/conversations", tags=["대화"])
async def list_conversations(request: Request):
    username = await authenticated_username(request)
    async with engine.connect() as connection:
        result = await connection.execute(text("""
            SELECT id, title, created_at, updated_at
            FROM chat_conversations
            WHERE owner_username = :username
            ORDER BY updated_at DESC, id DESC
        """), {"username": username})
        return [dict(row) for row in result.mappings()]


@app.get("/conversations/{conversation_id}/messages", tags=["대화"])
async def get_conversation_messages(conversation_id: str, request: Request):
    username = await authenticated_username(request)
    async with engine.connect() as connection:
        conversation = await _owned_conversation(connection, conversation_id, username)
        if not conversation:
            raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
        result = await connection.execute(text("""
            SELECT id, role, text, sources, needs_review, handoff,
                   clarifying_questions, created_at
            FROM chat_messages
            WHERE conversation_id = :conversation_id
            ORDER BY id ASC
        """), {"conversation_id": conversation_id})
        messages = []
        for row in result.mappings():
            item = dict(row)
            item["sources"] = _json_value(item["sources"], [])
            item["clarifying_questions"] = _json_value(item["clarifying_questions"], [])
            item["needs_review"] = bool(item["needs_review"])
            item["handoff"] = bool(item["handoff"])
            messages.append(item)
        return {"conversation": dict(conversation), "messages": messages}


_TOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")


def _message_tokens(message: dict) -> int:
    return len(_TOKEN_ENCODER.encode(message.get("content", ""))) + 4


def _text_tokens(value: str | None) -> int:
    return len(_TOKEN_ENCODER.encode(value or ""))


def _bounded_summary(value: str | None) -> str | None:
    if not value:
        return value
    tokens = _TOKEN_ENCODER.encode(value)
    return _TOKEN_ENCODER.decode(tokens[:SUMMARY_TOKEN_BUDGET])


def complete_turns(messages: list[dict]) -> list[list[dict]]:
    """완성된 user/assistant 쌍만 문맥 압축 대상으로 삼는다."""
    turns, pending = [], None
    for message in messages:
        if message["role"] == "user":
            pending = message
        elif message["role"] == "assistant" and pending is not None:
            turns.append([pending, message])
            pending = None
    return turns


def split_history_for_summary(messages: list[dict], budget: int = HISTORY_TOKEN_BUDGET,
                              recent_budget: int = RECENT_HISTORY_TOKEN_BUDGET,
                              summary_tokens: int = 0):
    turns = complete_turns(messages)
    if summary_tokens + sum(_message_tokens(m) for turn in turns for m in turn) <= budget:
        return [], turns
    available_recent = min(recent_budget, max(0, budget - max(summary_tokens, SUMMARY_TOKEN_BUDGET)))
    recent, used = [], 0
    for turn in reversed(turns):
        cost = sum(_message_tokens(m) for m in turn)
        if used + cost > available_recent:
            break
        recent.insert(0, turn)
        used += cost
    old_count = len(turns) - len(recent)
    return turns[:old_count], recent


def contextual_search_question(question: str, summary: str | None, messages: list[dict],
                               limit_chars: int = 4000) -> str:
    followup = question.strip().startswith(('그 다음', '그다음', '그럼', '그러면', '이어서', '아까', '방금', '그 물질', '이 물질', '해당 물질', '그 경우', '그 상황'))
    if not followup or any(word in question for word in ('모르는', '모르겠', '미확인', '알 수 없는', '다른 사고', '새로운 사고')):
        return question
    prior_users = [m["content"] for m in messages if m["role"] == "user"][-6:]
    parts = ([f"이전 대화 요약: {summary}"] if summary else [])
    parts += [f"이전 사용자 질문: {content}" for content in prior_users]
    parts.append(f"현재 질문: {question}")
    return "\n".join(parts)[-limit_chars:]


def history_messages(summary: str | None, turns: list[list[dict]]):
    messages = []
    if summary:
        messages.append(SystemMessage(content=(
            "다음은 이전 대화의 요약입니다. 대화 맥락으로만 사용하고 안전 근거로 인용하지 마세요.\n" + summary
        )))
    for turn in turns:
        messages.extend([HumanMessage(content=turn[0]["content"]), AIMessage(content=turn[1]["content"])])
    return messages


async def _summarize_turns(existing_summary: str | None, turns: list[list[dict]]) -> str:
    transcript = "\n".join(
        f"{message['role']}: {message['content']}" for turn in turns for message in turn
    )
    prompt = (
        "산업안전 대화의 사실, 사용자 상황, 이미 안내한 내용을 한국어로 간결하게 요약하세요. "
        "추측하거나 새로운 안전 근거를 추가하지 마세요.\n"
        f"기존 요약:\n{existing_summary or '(없음)'}\n\n추가 대화:\n{transcript}"
    )
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0, timeout=30)
    response = await asyncio.to_thread(llm.invoke, [HumanMessage(content=prompt)])
    return _bounded_summary(chunk_text(response.content).strip()) or ""


async def prepare_chat(username: str, rag_request: RAGRequest) -> dict:
    conversation_id = rag_request.conversation_id
    if not conversation_id:
        return {
            "conversation_id": str(uuid.uuid4()), "title": rag_request.prompt.strip()[:60],
            "summary": None, "turns": [], "search_question": rag_request.prompt.strip(), "is_new": True,
            "pending_summary": None, "pending_summary_cursor": None,
        }
    async with engine.connect() as connection:
        conversation = await _owned_conversation(connection, conversation_id, username)
        if not conversation:
            raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
        result = await connection.execute(text("""
            SELECT id, role, text AS content FROM chat_messages
            WHERE conversation_id = :conversation_id
              AND (:cursor IS NULL OR id > :cursor)
            ORDER BY id ASC
        """), {"conversation_id": conversation_id, "cursor": conversation["summary_through_message_id"]})
        unsummarized = [dict(row) for row in result.mappings()]

    stored_summary = conversation["summary"]
    summary = _bounded_summary(stored_summary)
    pending_summary = None
    pending_summary_cursor = None
    old_turns, recent_turns = split_history_for_summary(
        unsummarized, summary_tokens=_text_tokens(summary))
    if old_turns:
        try:
            new_summary = await _summarize_turns(summary, old_turns)
            if new_summary:
                summary = new_summary
                pending_summary = new_summary
                pending_summary_cursor = old_turns[-1][-1]["id"]
        except HTTPException:
            raise
        except Exception as exc:
            print(f"⚠️ 대화 요약 실패, 기존 요약과 최근 대화로 계속합니다: {exc}")

    recent_messages = [message for turn in recent_turns for message in turn]
    return {
        "conversation_id": conversation_id, "title": conversation["title"], "summary": summary,
        "turns": recent_turns,
        "search_question": contextual_search_question(rag_request.prompt.strip(), summary, recent_messages),
        "is_new": False, "pending_summary": pending_summary,
        "pending_summary_cursor": pending_summary_cursor,
    }


async def save_turn(username: str, chat: dict, result: dict):
    """완성된 최종 결과 하나만 사용자/assistant 쌍으로 원자적으로 저장한다."""
    async with engine.begin() as connection:
        if chat["is_new"]:
            await connection.execute(text("""
                INSERT INTO chat_conversations (id, owner_username, title)
                VALUES (:id, :username, :title)
            """), {"id": chat["conversation_id"], "username": username, "title": chat["title"]})
        else:
            owned = await _owned_conversation(connection, chat["conversation_id"], username)
            if not owned:
                raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
        if chat.get("pending_summary"):
            await connection.execute(text("""
                UPDATE chat_conversations
                SET summary = :summary, summary_through_message_id = :cutoff
                WHERE id = :conversation_id AND owner_username = :username
                  AND (summary_through_message_id IS NULL OR summary_through_message_id < :cutoff)
            """), {"summary": chat["pending_summary"], "cutoff": chat["pending_summary_cursor"],
                   "conversation_id": chat["conversation_id"], "username": username})
        await connection.execute(text("""
            INSERT INTO chat_messages (conversation_id, role, text)
            VALUES (:conversation_id, 'user', :content)
        """), {"conversation_id": chat["conversation_id"], "content": result["prompt"]})
        await connection.execute(text("""
            INSERT INTO chat_messages
              (conversation_id, role, text, sources, needs_review, handoff, clarifying_questions)
            VALUES
              (:conversation_id, 'assistant', :content, :sources, :needs_review, :handoff, :clarifying_questions)
        """), {
            "conversation_id": chat["conversation_id"], "content": result["answer"],
            "sources": json.dumps(result["sources"], ensure_ascii=False),
            "needs_review": result["needs_review"], "handoff": result["handoff"],
            "clarifying_questions": json.dumps(result["clarifying_questions"], ensure_ascii=False),
        })
        await connection.execute(text("""
            UPDATE chat_conversations SET updated_at = CURRENT_TIMESTAMP
            WHERE id = :conversation_id AND owner_username = :username
        """), {"conversation_id": chat["conversation_id"], "username": username})


async def finalize_turn(request: Request, username: str, chat: dict, state: dict, raw: str) -> dict:
    result = finish_rag(state, raw)
    result.update(conversation_id=chat["conversation_id"], title=chat["title"])
    if await request.is_disconnected():
        raise asyncio.CancelledError
    await save_turn(username, chat, result)
    return result

# ✅ RAG 기반 질의 응답 처리
from fastapi import Body

# 유틸
def extract_by_marker(text: str,
                      start: str = "### ANSWER_START",
                      end: str = "### ANSWER_END") -> str | None:
    i = text.find(start)
    if i == -1:
        return None
    j = text.find(end, i + len(start))
    if j == -1:
        return None
    return text[i + len(start): j].strip()

# 컨텍스트가 "id:\n title:\n content:" 형태일 때의 간단 백업 파서(옵션)
import re
def fallback_extract_from_context(context: str, question: str) -> str | None:
    q = re.sub(r"[^\w가-힣A-Za-z0-9 ]", "", question).strip()
        # []: 문자 클래스 (이 안의 문자 중 하나와 매칭)
        # ^: 문자 클래스 앞에 있으면 "not"의 의미 → 이 안에 포함되지 않은 문자를 의미
        # \w: 알파벳 + 숫자 + 밑줄 → [A-Za-z0-9_]와 동일
        # 가-힣: 한글 완성형 유니코드 범위
        # A-Za-z0-9: 영문자와 숫자 (중복이긴 하지만 명시적 표현)
        # 공백( ): 띄어쓰기 허용
    blocks = re.split(r"\n\s*\n", context.strip())
    for b in blocks:
        m_title = re.search(r"^title:\s*(.+)$", b, flags=re.MULTILINE | re.IGNORECASE)
        m_content = re.search(r"^content:\s*(.+)$", b, flags=re.MULTILINE | re.IGNORECASE)
                    # ^content:
                    # → 줄의 처음이 content:로 시작해야 함
                    # (줄의 시작임을 의미하는 ^는 re.MULTILINE이 설정된 경우 각 줄마다 적용됨)
                    # \s*
                    # → content: 뒤에 공백이 0개 이상 있어도 허용
                    # (.+)
                    # → 공백을 제외한 내용이 최소 1자 이상 존재해야 함
                    # → 이 부분이 캡처 그룹 1번으로 추출됨
                    # $
                    # → 줄의 끝까지 매칭
        if m_title and m_content:
            t = re.sub(r"[^\w가-힣A-Za-z0-9 ]", "", m_title.group(1)).strip()
            if q.lower() in t.lower():
                return m_content.group(1).strip()
    m_any = re.search(r"^content:\s*(.+)$", context, flags=re.MULTILINE | re.IGNORECASE)
    return m_any.group(1).strip() if m_any else None

# ✅ 질의 응답 라우터
NOT_FOUND_MSG = "매뉴얼에서 관련 근거를 찾을 수 없습니다. 현장 안전관리자에게 문의하세요."
EMERGENCY_WORDS = ["다쳤", "부상", "쓰러", "의식", "출혈", "피가", "화상", "데었", "골절", "끼였", "끼임",
                   "감전", "화재", "불이", "폭발", "누출", "유출", "새고", "샜", "질식", "호흡"]
EMERGENCY_LINE = "⚠️ 사람이 다쳤거나 위험이 계속되면 즉시 119에 신고하고 현장 비상절차를 따르세요."

def is_emergency(q: str) -> bool:
    return not is_information_only(q) and any(w in q for w in EMERGENCY_WORDS)

INCIDENT_WORDS = EMERGENCY_WORDS + ["사고", "쏟", "엎질", "깨졌", "깨진", "노출", "흡입", "튀었", "터졌", "냄새"]

def is_incident(q: str) -> bool:
    """사고 상황 질문인지 (단순 용어·기준 질문에는 검색 계획을 쓰지 않음)"""
    return not is_information_only(q) and any(w in q for w in INCIDENT_WORDS)

# ✅ 물질명 오탈자 보정 (예: 영화수소 → 염화수소)
#   조원 파이프라인의 물질 목록(material_catalog.json)에 있는 이름과 "자모 단위"로 비교한다
import difflib
JOSA = ("으로", "에서", "에게", "이랑", "을", "를", "이", "가", "은", "는", "에", "의", "도", "와", "과", "로", "랑")
TYPO_MIN_RATIO = 0.85   # 이 이상 비슷하면 오탈자로 봄
TYPO_MIN_LEN = 3        # 3글자 이상 물질명만 보정 (짧은 이름은 오보정 위험)

def to_jamo(text: str) -> str:
    """한글을 자모로 분해: 염 → ㅇㅕㅁ (한 글자 차이를 더 정밀하게 비교하려고)"""
    CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
    JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
    JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out += [CHO[code // 588], JUNG[(code % 588) // 28], JONG[code % 28].strip()]
        else:
            out.append(ch)
    return "".join(out)

def load_material_names() -> list[str]:
    """현재 팀 인덱스의 물질 목록에서 한글 물질명(3글자 이상)만 모은다"""
    if not USE_TEAM_INDEX:
        return []
    try:
        folder = team_pipeline.resolve_pointer(TEAM_CFG["output_root"], "current.json")
        catalog = json.loads((folder / "material_catalog.json").read_text(encoding="utf-8"))
        names = {a for e in catalog for a in e.get("aliases_from_source", [])
                 if re.fullmatch(r"[가-힣]+", a) and len(a) >= TYPO_MIN_LEN}
        return sorted(names)
    except Exception as e:
        print(f"⚠️ 물질 목록을 불러오지 못했습니다: {e}")
        return []

def correct_material_typos(question: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    """반환: (보정된 질문, [(원래 단어, 보정 이름)], [헷갈리는 후보 안내])
    - 후보가 1개만 아주 비슷하면 → 자동 보정 + 사용자에게 알림
    - 비슷한 후보가 여러 개면 → 보정하지 않고 되묻기"""
    names = load_material_names()
    if not names:
        return question, [], []
    fixed, corrections, ambiguous = question, [], []
    for token in re.findall(r"[가-힣]+", question):
        word = token
        for j in JOSA:                       # 조사 떼기: 영화수소가 → 영화수소
            if word.endswith(j) and len(word) - len(j) >= TYPO_MIN_LEN:
                word = word[: -len(j)]
                break
        if len(word) < TYPO_MIN_LEN or word in names:
            continue
        scored = sorted(((difflib.SequenceMatcher(None, to_jamo(word), to_jamo(n)).ratio(), n) for n in names
                         if abs(len(n) - len(word)) <= 1), reverse=True)
        close = [(r, n) for r, n in scored if r >= TYPO_MIN_RATIO]
        if len(close) == 1 or (len(close) > 1 and close[0][0] - close[1][0] >= 0.05):
            fixed = fixed.replace(word, close[0][1])
            corrections.append((word, close[0][1]))
        elif len(close) > 1:
            ambiguous.append(f"'{word}'은(는) {', '.join(n for _, n in close[:3])} 중 어떤 물질인가요?")
    if corrections:
        print(f"[오탈자 보정] {corrections}")
    return fixed, corrections, ambiguous

def make_search_plan(question: str) -> dict | None:
    """검색 계획 프롬프트로 JSON 계획을 받는다. 실패하면 None → 원래 질문 하나로만 검색"""
    try:
        planner = ChatOpenAI(model=LLM_MODEL, temperature=0, timeout=30,
                             model_kwargs={"response_format": {"type": "json_object"}})
        raw = planner.invoke([SystemMessage(content=SEARCH_PLAN_PROMPT), HumanMessage(content=question)]).content
        plan = json.loads(raw)
        if not isinstance(plan.get("search_plan"), list):
            return None
        print(f"[검색 계획] {len(plan['search_plan'])}개 질의")
        for item in plan["search_plan"]:
            print(f"  - {item.get('id')} [{item.get('category')}] {item.get('query')} ({item.get('applicability')})")
        return plan
    except Exception as e:
        print(f"⚠️ 검색 계획 실패 → 원래 질문으로만 검색: {e}")
        return None

# 물질 필터를 쓸 검색 묶음: 물질 MSDS에서 찾아야 하는 것만 (보고·연락망·일반 대응은 매뉴얼 전체에서 찾기)
MATERIAL_FILTER_CATEGORIES = ("물질", "소화")

def retrieve_one(source: str, use_team: bool, vectorstore, query: str, k: int, category: str | None = None):
    """검색어 하나 → [(Document, 거리)]
    category가 None(원래 질문)이거나 물질·소화 묶음이면 조원 search()(물질 필터 포함),
    그 밖의 묶음(사고 대응·보고·연락망)은 필터 없이 매뉴얼 전체에서 검색"""
    if use_team:
        # Graph traversal runs once on the original/contextual question in prepare_rag.
        filter_material = not category or any(w in category for w in MATERIAL_FILTER_CATEGORIES)
        result = team_pipeline.search(TEAM_CFG, TEAM_EMBEDDER, query, k,
                                      include_graph=False, material_filter=filter_material)
        if result.get("material_filter_applied"):
            print(f"[팀 검색] 물질 필터 적용: {query!r}")
        return [(Document(page_content=r["text"], metadata={kk: v for kk, v in r.items() if kk != "text"}), r["distance"])
                for r in result["results"]]
    return vectorstore.similarity_search_with_score(query, k=k)

def doc_label(doc) -> str:
    m = doc.metadata or {}
    if m.get("source_url"):
        return f"{m.get('filename', '공식 웹')} [{m['source_url']}]"
    name = m.get("filename") or m.get("source") or "업로드 문서"
    page = m.get("pdf_page_start") or m.get("page")
    label = f"{name} p.{page}" if page else str(name)
    extra = m.get("article_number") or m.get("section_title")
    if extra:
        extra = str(extra).strip()
        label += f" · {extra[:30]}{'…' if len(extra) > 30 else ''}"
    return label

def resolve_document_citations(answer, docs):
    """생성 당시 검색 순번으로만 출처를 해석한다. 축약·반복 표기를 모두 처리한다."""
    pattern = r"[\(\[]\s*문서\s*\d+(?:\s*,\s*(?:문서\s*)?\d+)*\s*[\)\]]"
    cited = []

    def replace(match):
        labels = []
        for number in map(int, re.findall(r"\d+", match.group(0))):
            if 1 <= number <= len(docs):
                cited.append(number)
                labels.append(doc_label(docs[number - 1]).split(" · ")[0].replace(".pdf", ""))
            else:
                # 없는 번호를 다른 문서로 대체하거나 근거가 있는 것처럼 숨기지 않는다.
                labels.append("출처 확인 필요")
        return "(" + ", ".join(dict.fromkeys(labels)) + ")"

    resolved = re.sub(pattern, replace, answer)
    sources = list(dict.fromkeys(doc_label(docs[n - 1]) for n in cited))
    return resolved, sources


def build_prompt(context: str, question: str, include_markers: bool = True) -> str:
    ending = ("### ANSWER_START\n<답변>\n### ANSWER_END" if include_markers
              else "답변 본문만 출력하세요.")
    return (
        "당신은 산업 현장 안전사고 대응 도우미입니다. 아래 [검색 내용]은 매뉴얼과 출처가 표시된 공식 참고자료입니다.\n" +
        ANSWER_POLICY + ("\n이 질문은 정보 조회·비교다. 요청한 비교와 출처만 답하고 사고 대응·연락처·현장 확인 질문은 추가하지 않는다.\n" if is_information_only(question) else "") + "\n규칙:\n"
        "- [검색 내용]에 근거해서 한국어로 친절하고 구체적으로 답하세요.\n"
        "- 질문과 관련된 내용을 정리하고 그래프 경로에 표시된 절차 분기·기관·업무 관계를 함께 설명하세요.\n"
        "- 그래프의 related_work는 관련 업무이고, 조건이 다른 절차 경로는 구분해서 설명하세요. 검색 주제는 실제 발생 사실과 구분하세요.\n"
        "- 문서에 없는 수치·절차는 지어내지 마세요.\n"        "- 연락처는 어느 기관(문서) 자료인지 함께 쓰고, 사용자 소속 기관의 번호로 단정하지 마세요.\n"
        "- 각 문장 끝에 근거 문서 번호를 괄호로 붙이세요. 예: (문서 2)\n"
        "- 질문과 관련된 내용이 [검색 내용]에 전혀 없을 때만 'N/A' 한 단어로 답하세요.\n\n"
        "답변 형식:\n"
        "- 사고가 난 상황을 묻는 질문이면: 1. 즉시 조치 / 2. 물질 위험성·주의사항 / 3. 소화 방법·주의(화재 관련 근거가 있을 때) / 4. 보고·후속 처리 / 5. 담당 부서·연락처\n"
        "  (실제로 일어나지 않은 상황(예: 화재)의 근거는 '해당 시 참고'라고 구분해서 쓰세요.)\n"
        "- 기준·방법·수칙을 묻는 질문이면: 핵심 내용을 번호 목록으로\n"
        "- 필요한 항목의 근거가 없으면 누락 항목과 추가 확인 정보를 짧게 쓰세요.\n\n"
        f"[검색 내용]\n{context}\n\n"
        f"[질문] {question}\n\n"
        f"{ending}"
    )

def make_context(docs, limit_chars: int = 24000) -> str:
    chunks, total = [], 0
    for i, doc in enumerate(docs, start=1):
        content = (doc.page_content or "").strip()
        if not content:
            continue
        excerpt = content[: max(0, limit_chars - total)]
        if not excerpt:
            break
        cat = (doc.metadata or {}).get("plan_category")
        provenance = path_text(doc.metadata or {})
        block = f"[문서 {i}] ({doc_label(doc)})" + (f" [검색 묶음: {cat}]" if cat else "") + f"\n{provenance}\n{excerpt}"
        chunks.append(block)
        total += len(block)
    return "\n\n".join(chunks)

async def prepare_rag(rag_request: RAGRequest, search_question: str | None = None) -> dict:
    """공통 검색 단계. 일반 JSON 응답과 스트리밍 응답이 같은 근거를 사용하게 한다."""
    q, typo_fixes, typo_questions = correct_material_typos(rag_request.prompt.strip())   # 물질명 오탈자 보정
    emergency = is_emergency(q)
    use_team = rag_request.source == "pdf" and USE_TEAM_INDEX
    vectorstore = VECTORSTORE_PDF if rag_request.source == "pdf" else VECTORSTORE_WEB
    if vectorstore is None and not use_team:
        raise HTTPException(
            status_code=503,
            detail=f"❗ {rag_request.source.upper()} 지식베이스가 준비되지 않았습니다. 먼저 자료를 업로드해 주세요.",
        )
    retrieval_q = search_question or q
    for wrong, right in typo_fixes:   # 이전 대화가 붙은 검색 질문에도 같은 보정 적용
        retrieval_q = retrieval_q.replace(wrong, right)

    unknown_material = False
    plan = await asyncio.to_thread(make_search_plan, retrieval_q) if (USE_SEARCH_PLAN and is_incident(q)) else None
    queries = [(None, retrieval_q)]
    if plan:
        queries += [(it.get("category"), it["query"]) for it in plan["search_plan"][:MAX_PLAN_QUERIES]
                    if isinstance(it, dict) and it.get("query")]
    k_each = rag_request.top_k if len(queries) == 1 else PLAN_TOP_K

    found_all = await asyncio.gather(*[
        asyncio.to_thread(retrieve_one, rag_request.source, use_team, vectorstore, query, k_each, cat)
        for cat, query in queries
    ])
    seen, docs_scores = set(), []
    for (cat, _), found in zip(queries, found_all):
        for doc, score in found:
            key = (doc.metadata or {}).get("chunk_id") or doc.page_content[:200]
            if key in seen:
                continue
            seen.add(key)
            if cat:
                doc.metadata["plan_category"] = cat
            docs_scores.append((doc, score))
    for i, (doc, score) in enumerate(docs_scores, start=1):
        print(f"[{rag_request.source.upper()} 검색 {i}] 거리={score:.4f}, 출처={doc_label(doc)}, 내용={doc.page_content[:120]!r}")
    if MAX_DISTANCE > 0:
        docs_scores = [(d, s) for d, s in docs_scores if s <= MAX_DISTANCE]
    graph = {'enabled': False, 'results': []}
    if use_team:
        graph = await asyncio.to_thread(
            team_pipeline.graph_search, TEAM_CFG, retrieval_q,
            institution_scope=rag_request.institution_scope,
            accident_classification=rag_request.accident_classification, at=rag_request.contact_at)
    vector_rows = [{**doc.metadata, 'text': doc.page_content, 'distance': float(score),
                    'chunk_id': doc.metadata.get('chunk_id') or hashlib.sha256(doc.page_content.encode()).hexdigest()}
                   for doc, score in docs_scores]
    if use_team:
        vector_rows = [r for r in vector_rows if evidence_eligible(
            r, institution_scope=rag_request.institution_scope,
            accident_classification=rag_request.accident_classification, timing=graph.get('timing'))]
    if use_team and is_incident(q) and not graph.get('matched_materials'):
        unknown_material = True
        folder = team_pipeline.resolve_pointer(TEAM_CFG['output_root'], 'current.json')
        catalog = team_pipeline.read_json(folder / 'material_catalog.json')
        material_pages = {item['pdf_page'] for item in catalog}
        def general_evidence(row):
            return not (row.get('doc_id') == 'lab_safety_manual' and row.get('pdf_page_start') in material_pages) and row.get('content_type') != 'reviewed_pictogram_supplement' and row.get('doc_type') != 'official_web'
        vector_rows = [row for row in vector_rows if general_evidence(row)]
        graph['results'] = [row for row in graph.get('results', []) if general_evidence(row)]
    selected, workflow = await asyncio.to_thread(
        assemble_safety, vector_rows, graph, max_docs=MAX_CONTEXT_DOCS,
        web_enabled=use_team and TEAM_CFG.get('official_web', {}).get('enabled', True))
    docs = [Document(page_content=r['text'], metadata={k: v for k, v in r.items() if k != 'text'}) for r in selected]
    graph_metadata = {k: v for k, v in graph.items() if k != 'results'}
    graph_metadata['safety_workflow'] = workflow
    graph_metadata['context_paths'] = [
        {'chunk_id': r['chunk_id'], 'paths': r['graph_paths']} for r in selected if r.get('graph_paths')]
    context = make_context(docs)
    if context:
        context += "\n[근거 확보 현황]\n" + json.dumps(workflow, ensure_ascii=False)
        context += "\n[필수 답변 구성]\n" + generation_requirements(
            selected, graph.get("matched_materials", []), citation_style="number", question=q)
    if unknown_material:
        context += "\n[물질 확인 상태] 물질 미확인. 검색 문서나 이전 답변의 물질명을 사고 물질로 추정하지 않는다. 일반 사고 대응 근거만 사용해 사용자가 요청한 사람 보호 → 현장 대응 → 보고 순서로 설명한다. 개별 물질 반응·중화·소화법을 확정하지 않는다. 물질명·제품 라벨/SDS 확인을 요청하되 확인 전에도 근거 있는 일반 대응을 안내한다."
        plan = {**(plan or {}), 'clarifying_questions': ['누출된 화학약품의 이름이나 제품 라벨/SDS를 확인할 수 있나요?']}
    return {
        "use_history": retrieval_q != q and not unknown_material,
        "q": q,
        "emergency": emergency,
        "plan": plan,
        "queries": queries,
        "docs": docs,
        "context": context,
        "graph_retrieval": graph_metadata,
        "typo_fixes": typo_fixes,
        "typo_questions": typo_questions,
    }


def finish_rag(state: dict, raw: str) -> dict:
    """LLM 출력을 후처리하고 일반·스트리밍 API에 공통으로 쓸 결과를 만든다."""
    q, docs, emergency = state["q"], state["docs"], state["emergency"]
    plan, queries = state["plan"], state["queries"]
    final = (extract_by_marker(raw) or raw).strip()
    final = re.sub(r"###\s*ANSWER_(START|END)|<답변>", "", final).strip()
    base = {
        "prompt": q,
        "needs_review": emergency,
        "search_queries": [query for _, query in queries[1:]],
                        "clarifying_questions": state.get("typo_questions", []) + ([] if is_information_only(q) else (plan or {}).get("clarifying_questions", [])),
        "graph_retrieval": state.get("graph_retrieval", {}),
    }
    if not final or final.upper().startswith("N/A"):
        answer = (EMERGENCY_LINE + "\n\n" if emergency else "") + NOT_FOUND_MSG
        return {**base, "answer": answer, "sources": [], "handoff": True}

    final, completion_source_ids = ensure_contact_details(
        final, [{**d.metadata, "text": d.page_content} for d in docs], citation_style="number",
        enabled=not is_information_only(q) and bool(state.get("graph_retrieval", {}).get("matched_materials")),
        materials=state.get("graph_retrieval", {}).get("matched_materials", []))
    base["graph_retrieval"]["completion_source_ids"] = completion_source_ids
    final, sources = resolve_document_citations(final, docs)
    if emergency:
        final = EMERGENCY_LINE + "\n\n" + final
    if state.get("typo_fixes"):   # 어떻게 고쳐 이해했는지 알림
        note = ", ".join(f"'{a}' → '{b}'" for a, b in state["typo_fixes"])
        final = f"※ 질문의 {note}(으)로 이해하고 답했습니다. 다른 물질이면 다시 알려주세요.\n\n" + final
    return {**base, "answer": final, "sources": sources, "handoff": False}


def chunk_text(content) -> str:
    """LangChain이 문자열 또는 content block 목록으로 준 토큰을 문자열로 바꾼다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item if isinstance(item, str) else str(item.get("text", ""))
            for item in content if isinstance(item, (str, dict))
        )
    return "" if content is None else str(content)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/rag-query", response_model=AnswerResponse, summary="Closed Source LLM + 벡터 DB 질의", tags=["질의 응답"])
async def rag_query(request: Request, rag_request: RAGRequest = Body(...)):
    try:
        username = await authenticated_username(request)
        chat = await prepare_chat(username, rag_request)
        state = await prepare_rag(rag_request, chat["search_question"])
        if not state["context"].strip():
            raw = "N/A"
        else:
            llm = ChatOpenAI(model=LLM_MODEL, temperature=0.2, timeout=30)
            messages = history_messages(chat["summary"], chat["turns"]) if state.get("use_history", False) else []
            messages.append(HumanMessage(content=build_prompt(state["context"], state["q"])))
            message = await asyncio.to_thread(llm.invoke, messages)
            raw = chunk_text(message.content).strip()
            print(f"[LLM 원본 응답] {raw[:800]}")
        result = await finalize_turn(request, username, chat, state, raw)
        return AnswerResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM 또는 검색 처리 중 오류: {e}")


@app.post("/rag-query/stream", summary="Closed Source LLM + 벡터 DB 스트리밍 질의", tags=["질의 응답"])
async def rag_query_stream(request: Request, rag_request: RAGRequest = Body(...)):
    username = await authenticated_username(request)
    chat = await prepare_chat(username, rag_request)

    async def generate():
        try:
            yield sse_event("status", {"phase": "retrieving", "message": "관련 자료를 찾고 있어요…"})
            state = await prepare_rag(rag_request, chat["search_question"])
            if not state["context"].strip():
                result = await finalize_turn(request, username, chat, state, "N/A")
                yield sse_event("token", {"text": result["answer"]})
                yield sse_event("done", result)
                return

            yield sse_event("status", {"phase": "generating", "message": "답변을 작성하고 있어요…"})
            llm = ChatOpenAI(model=LLM_MODEL, temperature=0.2, timeout=30)
            parts = []
            messages = history_messages(chat["summary"], chat["turns"]) if state.get("use_history", False) else []
            messages.append(HumanMessage(content=build_prompt(
                state["context"], state["q"], include_markers=False)))
            async for chunk in llm.astream(messages):
                text = chunk_text(chunk.content)
                if text:
                    parts.append(text)
                    yield sse_event("token", {"text": text})

            raw = "".join(parts).strip()
            print(f"[LLM 스트리밍 원본 응답] {raw[:800]}")
            result = await finalize_turn(request, username, chat, state, raw)
            yield sse_event("done", result)
        except asyncio.CancelledError:
            raise
        except HTTPException as e:
            yield sse_event("error", {"message": str(e.detail)})
        except Exception as e:
            print(f"⚠️ 스트리밍 응답 오류: {e}")
            yield sse_event("error", {"message": f"LLM 또는 검색 처리 중 오류: {e}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# 실행 명령어 예시:
# python -m uvicorn rag_external-web_pdf_closed_llm:app --port 8001 --reload
