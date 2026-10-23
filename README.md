# industrial-safety-ai
RAG 기반 산업안전 매뉴얼 검색, 다국어 음성 질의응답 및 재난 대응을 지원하는 AI 서비스

한국어 PDF 데이터 파이프라인의 실행 방법과 검증 범위는 [데이터 파이프라인 안내](docs/DATA_PIPELINE.md)를 참고하세요. 현재는 두 PDF의 개발용 추출, FAISS 구축과 근거 검색 단계이며 서비스 API와의 연결은 후속 작업입니다.

[질문별 답변 검증 노트북](notebooks/safepath_question_validation.ipynb)에서 7개 질문의 근거, 모범답안 초안과 생성 답변을 비교하고 RAGAS로 자동 평가합니다. 검색 정밀도·재현율은 모범답안 초안 기준의 잠정 점수이며, 자료 밖 질문은 별도 보류 루브릭으로 평가합니다. VS Code에서 이 프로젝트의 `.venv/bin/python` 커널을 선택하세요. 실제 답변 생성은 `RUN_LIVE=True`, RAGAS 평가 실행은 `RUN_RAGAS=True`입니다. 기본값은 저장 결과 재사용이며 새 실행에는 API 비용이 발생합니다.

## 표·GHS 이미지 인식

[이미지 판독 파이프라인](docs/VISION_PIPELINE.md)을 추가했습니다. 노트북 09절에서 전체 페이지 판독과 개별 그림 확대 판독의 실제 결과를 비교합니다. `data/SafeOps_GHS_인식참고_v1.pdf`는 인식 사전용 파생자료이며 `recognition_references`에 등록되어 기본 RAG 색인에서는 제외합니다. 확인된 GHS 그림, 사고 절차와 연락망을 포함해 379개 청크를 구축하며, 문서 간 연결 근거는 별도로 보존합니다.

## 팀원 실행 안내

Python 3.11 환경에서 실행합니다. 원본 PDF와 인식 참고자료는 `data/`에 포함돼 있습니다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r notebooks/requirements.txt
.venv/bin/python -m pipeline.pdf_pipeline prepare
.venv/bin/python -m unittest discover -s tests -q
# OPENAI_API_KEY를 로컬 .env에 설정한 뒤 실행 (임베딩 비용 발생)
.venv/bin/python -m pipeline.pdf_pipeline --env-file .env build
```

`.env`, `.harness/`, `pipeline_artifacts/`와 노트북 실행 출력은 커밋하지 않습니다. 따라서 새로 받은 저장소에는 과거 생성 답변/점수/이미지 캐시가 없습니다. 노트북 전체 실행 전에 해당 자료를 생성해야 하며, 미실행 상태를 실제 답변으로 간주하지 않습니다. 문서 연결과 상황별 근거 묶음의 범위 및 한계는 [통합 파이프라인 안내](docs/STRUCTURED_SAFETY_PIPELINE.md)를 참고하세요.
