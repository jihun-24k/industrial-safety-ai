# SafeOps PDF RAG 검증 노트북

Git에 관리하는 원본은 [safepath_question_validation.ipynb](safepath_question_validation.ipynb) 하나다. 20문항의 검색·답변 생성·인용 검사·RAGAS를 재현하며, 출력과 개인별 실행 캐시는 Git에 포함하지 않는다. 상세 설계와 이전 측정 결과는 [GraphRAG 안내](../docs/GRAPH_RAG.md)에서 확인한다.

저장된 결과가 없는 새 체크아웃에서도 00~07절은 오프라인으로 실행할 수 있다. PDF 준비·그래프 생성은 로컬에서 수행하고, 실제 임베딩·답변·채점은 실행 플래그를 켰을 때만 호출한다. 08절 이후는 선택적 과거 실험 부록으로, 별도 실험 산출물이 필요할 수 있다.

로컬의 `safepath_improvement_results.ipynb` 및 바탕화면 사본은 실행 출력이 포함된 열람용 보고서다. 원본 노트북과 내용이 겹치는 생성 결과이므로 삭제하지 않고 Git에서 제외한다.

| 파일 | 역할 | 서비스 실행에 필요 |
|---|---|---|
| `pipeline/knowledge_graph.py` | 출처 기반 관계 그래프 생성·탐색 | 필요 |
| `pipeline/retrieval_context.py` | 공통 근거 병합·문맥 선택 | 필요 |
| `pipeline/safety_workflow.py` | 항목별 근거 확보·웹 보완·답변 정책 | 필요 |
| `pipeline/official_web.py` | 공식 건강·대응 정보 조회 | 웹 보완 사용 시 필요 |
| `pipeline/notebook_evaluation.py` | 질문 실행·비교·평가 입력 관리 | 평가용 |
| `pipeline/ragas_evaluation.py` | 저장 답변의 RAGAS 채점 | 평가용 |
| `pipeline/run_notebook_evaluation.py` | 노트북 00~07절 실행 자동화 | 선택적 실행 도구 |

평가 도구가 두 번째 서비스 파이프라인을 만드는 것은 아니다. 공통 검색·근거 선택 코드를 호출하고, 별도로 생성·채점 설정과 실행 기록을 관리한다. API는 노트북/Jupyter/RAGAS 모듈을 불러오지 않는다.

## 실행

현재 GraphRAG 평가를 명령으로 실행할 수도 있다. 원본 노트북의 00~07절을 실행하며, 결과가 포함된 사본은 `pipeline_artifacts/evaluation/notebooks/<실행ID>/`에 저장한다. 뒤쪽 청킹·이미지 부록은 별도 실험이다.

```bash
# API 호출 없이 노트북 구조·그래프·미실행 표시 검증
.venv/bin/python -m pipeline.run_notebook_evaluation --offline

# 최초 인덱스 구축 + 현재 20문항 답변 생성 + RAGAS 평가
.venv/bin/python -m pipeline.run_notebook_evaluation --live --build-index

# 인덱스 구축 후 재실행: 현재 버전 캐시 재사용
.venv/bin/python -m pipeline.run_notebook_evaluation --live
```

키는 프로젝트 `.env`의 `OPENAI_API_KEY`로 읽으며 `--env-file`로 다른 로컬 파일을 지정할 수 있다. 노트북에는 키 값을 저장하지 않는다. `--live`는 문서/질문 임베딩·답변 생성·평가 API 비용을 발생시킨다. LangSmith 업로드는 이 실행에 포함하지 않는다.

벡터·문서 연결·그래프 근거를 생성과 평가에 포함한다. 이 노트북은 `gpt-4o`, temperature 0의 평가용 생성 경로를 사용하며, 서비스 API와 근거 선택·컨텍스트 제한을 공유한다. 서비스의 선택적 검색 계획 및 temperature 0.2는 노트북과 다르다.

- 필요한 패키지: `notebooks/requirements.txt`. RAGAS 0.4.3 및 instructor 1.12.0을 사용한다.
- 위에서부터 실행하면 저장된 실제 답변과 RAGAS 평가 결과를 읽는다. 기본적으로 추가 API 호출하지 않는다.
- `RUN_LIVE=True`는 답변 생성, `RUN_RAGAS=True`는 평가 실행이다. 서로 다른 설정이다.
- 모범답안은 원래 답변 생성에 전달하지 않으며 평가자에게만 전달한다.
- `UPLOAD_RAGAS=True`는 LangSmith 등록이다. 기존 성공 기록이 있으면 재등록하지 않는다.
- 환경 변수는 `LANGSMITH_*`를 사용한다. 노트북의 자동 추적은 꺼져 있다.

## 평가 기준

Q01~Q04와 S01~S15는 RAGAS Faithfulness, Answer Relevancy, Context Precision, Context Recall을 계산한다. 검색 정밀도와 재현율은 미검토 AI 모범답안을 사용하므로 `draft`로 표시하며 공식 정확도로 해석하지 않는다. 모델은 gpt-4o-mini, 관련성 평가 임베딩은 text-embedding-3-small이다.

Q05a 한 문항이 자료 밖 질문이다. 일반 RAG 평균에서 제외하고 RAGAS RubricsScoreWithoutReference로 보류 응답을 1~5점 평가한다. 기준은 `pipeline/ragas_evaluation.py`의 POLICY에 명시한다. 이는 사용자 정의 루브릭이며 표준 RAGAS 정답률이 아니다.

임의 종합 정답률을 만들지 않는다. 실패·측정 불가 값은 0점으로 대체하지 않는다. 과거 후보 Hit/Recall과 출처 ID 검사는 보조 진단이며 RAGAS 점수가 아니다. 이전 사람 채점 파일과 LangSmith 실험은 보존하고 새 RAGAS 실험과 구분한다.

평가에는 질문, 실제 답변, PDF 검색 구간, 모범답안 초안의 OpenAI 전송과 평가 비용이 발생한다. 2026-10-23 사용자가 이 범위 및 LangSmith 결과 등록에 명시적으로 동의했다. 기록은 `pipeline_artifacts/evaluation/`에 저장하며 Git에서 제외한다.

공식 지표 설명: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/

## 통합 파이프라인 검토 (10~11절)

10절은 절차도/연락망과 평일·주말 시간 규칙, 11절은 379청크 인덱스의 실제 검색 검증과 가상 사고의 근거 묶음이다. 공휴일 기능은 사용자 요청으로 제거했다. 두 절은 로컬 실행을 완료했으며 외부 API를 호출하지 않는다. 기존 답변/평가 출력은 보존했고, 새로운 LLM 답변이나 RAGAS 점수로 표시하지 않는다. 자세한 구현과 제한은 `docs/STRUCTURED_SAFETY_PIPELINE.md`를 참조한다.

## 위험 상황 질문 세트 v2

현재 `evaluation/notebook_cases.json`은 기본 4문항, 상황 15문항, Outside 1문항이다. 이전 7문항은 `evaluation/notebook_cases_v1.json`에 보존한다. Q01 기준 답안은 원문 43쪽의 밸브·조정기·캡 운반 지침을 추가했다.

| ID | 검증 주제 |
| --- | --- |
| S01~S02 | 염산 유출: 불완전한 일상 질문과 CAS가 주어진 질문 |
| S03~S05 | 피부·실험복 오염, 눈 노출, 암모니아 흡입 |
| S06~S07 | 톨루엔 누출의 화재 위험, 메틸 알코올 실제 화재 |
| S08~S09 | 나트륨 화재와 황산 누출의 물 반응 조건 |
| S10~S11 | 과산화수소·질산암모늄의 가연물/열 접촉 |
| S12 | 라벨 없는 혼합 폐액과 추가 정보 확인 |
| S13~S14 | 비중대 보고 경로, 야간 연락망 업무 구분 |
| S15 | 암모니아·황산 복수 물질과 혼합금지 |

질문별 `risk_tags`, `evaluation_focus`, `required_points`, `forbidden_claims`, 원문 `evidence`를 평가 전용으로 저장한다. 생성 모델에는 질문·검색 근거만 전달한다. S01/S12는 공통 대응을 제공하면서 추가 정보를 묻는 `answered` 또는 `needs_clarification` 상태를 허용한다.

비교 화면은 벡터 검색 근거 포함률과 그래프/전체 문맥 포함률을 따로 표시한다. RAGAS 결과에는 유형별 집계도 저장한다. 새 질문 세트와 기존 7문항의 평균은 동일 조건의 전후 비교가 아니다.

이전 실행을 별도로 확인하려면 다음처럼 이전 질문 파일을 지정한다.

```bash
.venv/bin/python -m pipeline.ragas_evaluation --run <이전-run.json> --cases evaluation/notebook_cases_v1.json
```

새 20문항 추가 후에는 원문 근거 일치 검사와 로컬 그래프 진단을 수행했다. 확장한 20문항의 실제 답변·RAGAS 평가 실행은 사용자 추가 동의를 받아 수행한다.

현재 평가 프롬프트는 `safeops-safety-workflow-v7-internal-pictograms`이며 API와 공통 근거 선택·답변 구성·연락처 보완을 사용한다. 공식 웹 발췌가 포함될 수 있으며 실제 모델에 전달된 `context_results`만 RAGAS 근거로 평가한다. 재평가에는 20개 질문과 PDF·공식 웹 근거의 OpenAI 전송 및 비용 사용에 추가 동의를 받았다. 이번 실행은 LangSmith 업로드 없이 로컬에 저장한다. 평가의 `details`에는 관련성 역생성 질문과 개별 판정 결과를 보존한다.

웹 검색 조건: 위험기호 미확보만으로는 검색하지 않는다. 신체 주의사항·대응 정보의 공식 근거 보완은 유지한다. 노트북의 저장된 평가 출력은 이 조건 변경 전 기록이며 별도 재평가하지 않았다.

위험기호는 위험성·신체 주의사항을 연결하는 내부 근거로만 사용한다. 답변에는 기호명·GHS 코드·위험기호 확인/미확보 안내를 출력하지 않는다. 노트북의 답변 표시에서도 과거 위험기호 부록을 제외했으며, 평가 원본과 기존 점수는 변경하지 않았다.
