"""
PDF 적재 스크립트 (데이터 파이프라인)
data/pdfs/ 폴더의 PDF를 모두 읽어 → 페이지별 추출·정제 → 청크 → OpenAI 임베딩 → FAISS 저장

사용법 (rag-code-template_ext 폴더에서, 가상환경 켠 상태):
    python build_index.py                # ../data/pdfs 의 PDF 전부 적재
    python build_index.py 다른/폴더/경로   # 다른 폴더를 쓰고 싶을 때

결과물: faiss_db/pdf/index.faiss, index.pkl
→ RAG 서버(uvicorn)를 켜면 자동으로 불러옵니다. (서버가 켜져 있었다면 재시작 필요)
"""
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

BASE_DIR = Path(__file__).resolve().parent              # .../rag-code-template_ext
load_dotenv(BASE_DIR / ".env")                          # OPENAI_API_KEY 읽기

PDF_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR.parent / "data" / "pdfs"
SAVE_DIR = BASE_DIR / "faiss_db" / "pdf"                # 서버가 불러오는 위치와 같아야 함

CHUNK_SIZE = 1000      # 서버 /upload-paper 와 같은 값
CHUNK_OVERLAP = 100


def load_pdf_pages(path: Path) -> list[Document]:
    """PDF 한 개 → 페이지별 Document (출처: 파일명 + 페이지 번호)"""
    reader = PdfReader(str(path))
    docs = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = re.sub(r"[ \t]+", " ", text).strip()     # 정제: 탭·연속 공백 → 공백 하나
        if text:
            docs.append(Document(page_content=text, metadata={"source": path.name, "page": i + 1}))
    return docs


def main():
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"❌ PDF가 없습니다: {PDF_DIR}")

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    all_chunks = []
    for pdf in pdfs:
        pages = load_pdf_pages(pdf)
        chunks = splitter.split_documents(pages)
        all_chunks.extend(chunks)
        print(f"📄 {pdf.name}: {len(pages)}쪽 → {len(chunks)}개 청크")

    print(f"🔢 임베딩 중... (총 {len(all_chunks)}개 청크)")
    db = FAISS.from_documents(all_chunks, OpenAIEmbeddings())
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    db.save_local(str(SAVE_DIR))
    print(f"✅ 저장 완료: {SAVE_DIR}")
    print("   → RAG 서버를 (재)시작하면 이 인덱스를 불러옵니다.")


if __name__ == "__main__":
    main()
