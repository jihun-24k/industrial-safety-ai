# SafeOps PDF RAG 검증 노트북

`safepath_question_validation.ipynb`를 열고 프로젝트 `.venv/bin/python` 또는 `SafeOps 프로젝트 (Python 3.11)` 커널을 선택한다. 파일명은 기존 링크 호환을 위해 유지한다.

## 실행

- 필요한 패키지: `notebooks/requirements.txt`. RAGAS 0.4.3 및 instructor 1.12.0을 사용한다.
- 위에서부터 실행하면 저장된 실제 답변과 RAGAS 평가 결과를 읽는다. 기본적으로 추가 API 호출하지 않는다.
- `RUN_LIVE=True`는 답변 생성, `RUN_RAGAS=True`는 평가 실행이다. 서로 다른 설정이다.
- 모범답안은 원래 답변 생성에 전달하지 않으며 평가자에게만 전달한다.
- `UPLOAD_RAGAS=True`는 LangSmith 등록이다. 기존 성공 기록이 있으면 재등록하지 않는다.
- 환경 변수는 `LANGSMITH_*`를 사용한다. 노트북의 자동 추적은 꺼져 있다.

## 평가 기준

Q01~Q04는 RAGAS Faithfulness, Answer Relevancy, Context Precision, Context Recall을 계산한다. 검색 정밀도와 재현율은 미검토 AI 모범답안을 사용하므로 `draft`로 표시하며 공식 정확도로 해석하지 않는다. 모델은 gpt-4o-mini, 관련성 평가 임베딩은 text-embedding-3-small이다.

Q05a~c는 자료 밖 질문이다. 일반 RAG 평균에서 제외하고 RAGAS RubricsScoreWithoutReference로 보류 응답을 1~5점 평가한다. 기준은 `pipeline/ragas_evaluation.py`의 POLICY에 명시한다. 이는 사용자 정의 루브릭이며 표준 RAGAS 정답률이 아니다.

임의 종합 정답률을 만들지 않는다. 실패·측정 불가 값은 0점으로 대체하지 않는다. 과거 후보 Hit/Recall과 출처 ID 검사는 보조 진단이며 RAGAS 점수가 아니다. 이전 사람 채점 파일과 LangSmith 실험은 보존하고 새 RAGAS 실험과 구분한다.

평가에는 질문, 실제 답변, PDF 검색 구간, 모범답안 초안의 OpenAI 전송과 평가 비용이 발생한다. 2026-10-23 사용자가 이 범위 및 LangSmith 결과 등록에 명시적으로 동의했다. 기록은 `pipeline_artifacts/evaluation/`에 저장하며 Git에서 제외한다.

공식 지표 설명: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/

## 통합 파이프라인 검토 (10~11절)

10절은 절차도/연락망과 평일·주말 시간 규칙, 11절은 379청크 인덱스의 실제 검색 검증과 가상 사고의 근거 묶음이다. 공휴일 기능은 사용자 요청으로 제거했다. 두 절은 로컬 실행을 완료했으며 외부 API를 호출하지 않는다. 기존 답변/평가 출력은 보존했고, 새로운 LLM 답변이나 RAGAS 점수로 표시하지 않는다. 자세한 구현과 제한은 `docs/STRUCTURED_SAFETY_PIPELINE.md`를 참조한다.
