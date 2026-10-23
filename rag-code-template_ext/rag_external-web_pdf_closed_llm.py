#### 다음 실습 코드는 학습 목적으로만 사용 바랍니다. 문의 : audit@korea.ac.kr 임성열 Ph.D.

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from sqlalchemy.ext.asyncio import create_async_engine
from fastapi.responses import JSONResponse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from pypdf import PdfReader
from langchain_core.messages import HumanMessage

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
from datetime import datetime, UTC
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import os
from pathlib import Path
from dotenv import load_dotenv

# 현재 Python 파일과 같은 위치에 있는 .env 파일 로드
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

# ✅ RAG 설정 (.env로 변경 가능)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
MAX_DISTANCE = float(os.getenv("RAG_MAX_DISTANCE", "0"))          # 0이면 거리 필터 끔
RESET_PDF_ON_UPLOAD = os.getenv("RESET_PDF_ON_UPLOAD", "false").lower() == "true"  # true면 업로드마다 교체

# ✅ DB 연결 정보
ASYNC_DB_URL = os.getenv("ASYNC_DB_URL", "mysql+aiomysql://root:password@127.0.0.1:53301/sql_db?charset=utf8mb4")
engine = create_async_engine(ASYNC_DB_URL)

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
                Document(page_content=t, metadata={"source": file.filename, "page": i + 1})
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
    prompt: str = Field(default=..., min_length=2, max_length=1000, description="질문 프롬프트")
    source: Literal["web", "pdf"] = Field(default=..., description="web | pdf")
    top_k: int = Field(default=5, ge=1, le=20, description="검색할 결과 수 (기본값 5)")

    class Config:
        validate_by_name = True

# ✅ 응답 모델: 교재 Day2 REST API 스키마 (answer · sources · needs_review · handoff)
class AnswerResponse(BaseModel):
    prompt: str
    answer: str
    sources: List[str] = []
    needs_review: bool = False   # 긴급·부상 상황 → 사람(안전관리자) 확인 필요
    handoff: bool = False        # 근거 없음 → 답변 대신 담당자에게 넘김

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
                   "감전", "화재", "불이", "폭발", "누출", "유출", "질식", "호흡"]
EMERGENCY_LINE = "⚠️ 사람이 다쳤거나 위험이 계속되면 즉시 119에 신고하고 현장 비상절차를 따르세요."

def is_emergency(q: str) -> bool:
    return any(w in q for w in EMERGENCY_WORDS)

def doc_label(doc) -> str:
    m = doc.metadata or {}
    name = m.get("source") or "업로드 문서"
    return f"{name} p.{m['page']}" if m.get("page") else str(name)

def build_prompt(context: str, question: str) -> str:
    return (
        "당신은 산업 현장 안전사고 대응 도우미입니다.\n"
        "규칙:\n"
        "- 반드시 아래 [검색 내용]에 근거해서만 한국어로 답하세요.\n"
        f"- [검색 내용]에 근거가 없으면 다른 말 없이 정확히 'N/A'라고만 답하세요.\n"
        "- 문서에 없는 수치·절차를 지어내지 마세요.\n"
        "- 문장 끝에 근거 문서 번호를 괄호로 붙이세요. 예: (문서 2)\n\n"
        "답변 형식(해당 내용이 문서에 있을 때만 작성):\n"
        "1. 즉시 조치\n2. 원인 또는 위험요인\n3. 예방 대책\n\n"
        f"[검색 내용]\n{context}\n\n"
        f"[질문] {question}\n\n"
        "### ANSWER_START\n<답변>\n### ANSWER_END"
    )

def make_context(docs, limit_chars: int = 12000) -> str:
    chunks, total = [], 0
    for i, doc in enumerate(docs, start=1):
        content = (doc.page_content or "").strip()
        if not content:
            continue
        excerpt = content[: max(0, limit_chars - total)]
        if not excerpt:
            break
        chunks.append(f"[문서 {i}] ({doc_label(doc)})\n{excerpt}")
        total += len(excerpt)
    return "\n\n".join(chunks)

@app.post("/rag-query", response_model=AnswerResponse, summary="Closed Source LLM + 벡터 DB 질의", tags=["질의 응답"])
async def rag_query(rag_request: RAGRequest = Body(...)):
    q = rag_request.prompt.strip()
    emergency = is_emergency(q)

    # 1. 벡터스토어 선택
    vectorstore = VECTORSTORE_PDF if rag_request.source == "pdf" else VECTORSTORE_WEB
    if vectorstore is None:
        raise HTTPException(
            status_code=503,
            detail=f"❗ {rag_request.source.upper()} 지식베이스가 준비되지 않았습니다. 먼저 자료를 업로드해 주세요.",
        )
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0.2, timeout=30)

    try:
        # 2. 검색 (거리 점수 포함)
        docs_scores = vectorstore.similarity_search_with_score(q, k=rag_request.top_k)
        for i, (doc, score) in enumerate(docs_scores, start=1):
            print(f"[{rag_request.source.upper()} 검색 {i}] 거리={score:.4f}, 출처={doc_label(doc)}, 내용={doc.page_content[:120]!r}")
        if MAX_DISTANCE > 0:  # 선택: 거리 임계값으로 관련 없는 문서 제외
            docs_scores = [(d, s) for d, s in docs_scores if s <= MAX_DISTANCE]
        docs = [d for d, _ in docs_scores]
        context = make_context(docs)

        # 3. 근거 없음 → LLM 호출하지 않고 handoff
        if not context.strip():
            answer = (EMERGENCY_LINE + "\n\n" if emergency else "") + NOT_FOUND_MSG
            return AnswerResponse(prompt=q, answer=answer, sources=[], needs_review=emergency, handoff=True)

        # 4. LLM 답변 생성
        raw = llm.invoke([HumanMessage(content=build_prompt(context, q))]).content
        raw = raw.strip() if isinstance(raw, str) else str(raw).strip()
        print(f"[LLM 원본 응답] {raw[:800]}")
        final = (extract_by_marker(raw) or raw).strip()

        # 5. LLM이 근거 없다고 판단 → handoff
        if not final or final.upper().startswith("N/A"):
            answer = (EMERGENCY_LINE + "\n\n" if emergency else "") + NOT_FOUND_MSG
            return AnswerResponse(prompt=q, answer=answer, sources=[], needs_review=emergency, handoff=True)

        # 6. 출처 정리: LLM이 실제로 인용한 (문서 N)만 표시, 인용이 없으면 검색된 문서 전체
        cited = [int(n) for n in re.findall(r"문서\s*(\d+)", final)]
        used = [docs[n - 1] for n in cited if 1 <= n <= len(docs)] or docs
        sources = list(dict.fromkeys(doc_label(d) for d in used))
        if emergency:
            final = EMERGENCY_LINE + "\n\n" + final
        return AnswerResponse(prompt=q, answer=final, sources=sources, needs_review=emergency, handoff=False)

    except HTTPException:
        raise
    except Exception as e:
        # 타임아웃·모델 오류 등은 503으로 안내 (교재 API 규칙)
        raise HTTPException(status_code=503, detail=f"LLM 또는 검색 처리 중 오류: {e}")


# 실행 명령어 예시:
# python -m uvicorn rag_external-web_pdf_closed_llm:app --port 8001 --reload