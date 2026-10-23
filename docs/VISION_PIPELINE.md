# SafeOps 표·기호 인식 파이프라인

## 문제와 해결

기존 pypdf 추출문에는 그림 의미가 없고 표의 열 관계도 명시적이지 않다. 이미지와 native text를 같이 판독하고, 빨간 테두리 기반 후보 검출 후 개별 그림 확대 분류를 추가했다. 이는 학습된 전용 검출기가 아니라 초기 문서용 휴리스틱이다. 흑백 이미지에서는 후보 검출이 실패할 수 있다.

`pipeline/vision_extraction.py`의 `recognize`는 OpenAI gpt-4o-2024-08-06으로 표/NFPA/기호를 구조화한다. `refine_icons`는 같은 페이지에서 얻은 후보 영역을 분류한다. 실제 응답 ID·모델·사용량·원본 응답·입력 해시·모델이 제안한 좌표와 로컬 검출 좌표를 결과에 보존한다. 최종 공식 코드는 `pipeline/ghs_dictionary.json`에서 연결한다.

## 자료 구분

- 원본: 매뉴얼과 폐기물관리법 두 PDF. 원본 해시 유지. 인덱스는 검토된 보충자료 추가 시 새 버전으로 발행한다.
- 인식 참고: books/data/SafeOps_GHS_인식참고_v1.pdf. 그림은 매뉴얼 PDF 105쪽에서 직접 추출했다. 코드 대조 출처는 Safe Work Australia 공식 GHS 안내다. 공식 배포 원본 이미지라고 표시하지 않는다.
- `recognition_references` 설정에 해시와 `rag_ingest:false`로 등록한다. 참고 PDF가 자동 RAG 문서로 혼입되지 않으며, 미등록 PDF는 계속 거부한다.
- `evaluation/vision_cases.json`은 두 페이지의 개발용 비교 기준이다. 사용자 확인과 어시스턴트 원문 전사가 혼합돼 있으며 독립 시험용 정답이 아니다. 판독 프롬프트에 전달하지 않는다.

## 실행

노트북 09절은 기본적으로 저장 결과만 읽는다. 새 외부 전송은 RUN_VISION=True를 명시해야 한다.

```bash
.venv/bin/python -m pipeline.vision_extraction --pages 54 55
.venv/bin/python -m pipeline.vision_extraction --live --refine --pages 54 55
```

첫 명령은 로컬 준비/캐시 조회, 두 번째는 미저장 판독에 한해 이미지 API를 사용한다. 2026-10-23 사용자가 매뉴얼 54·55쪽 이미지·추출문·기호 참고 이미지 전송과 두 페이지 판독 비용에 동의했다. 이 범위를 넘어서는 일괄 실행은 하지 않았다. LangSmith에 이미지 판독 결과를 업로드하지 않는다.

원시 판독 결과는 pipeline_artifacts/vision에 needs_human_review 상태로 보존한다. 사용자 승인은 별도 기록으로 관리하며 원시 응답이나 native 텍스트를 덮어쓰지 않는다.

## 평가

그림 개수, 순서별 공식 코드 일치, 기본 정보 5개와 NFPA 4개 항목을 비교한다. 좌표 정확도는 아직 측정하지 않았으며 안전성·현행 SDS 적합성 검증도 아니다. 비교 점수는 RAGAS가 아니라 구조화 추출의 정확 일치 검사다. 추출 개선 후 답변 품질은 별도의 RAGAS 실험으로 검증한다.

공식 근거:
- https://www.safeworkaustralia.gov.au/safety-topic/hazards/chemicals/classifying-chemicals/using-ghs
- https://docinfofiles.nfpa.org/files/AboutTheCodes/704/NFPA704_HC2012_QCard.pdf
- https://developers.openai.com/api/docs/guides/images-vision

## 사용자 확인 후 검색 반영 (2026-10-23)

사용자가 PDF 54쪽 2개, 55쪽 4개 그림의 종류와 순서를 확인하고 반영을 승인했다. `pipeline/reviewed_pictograms.json`에 승인 범위, 원본 해시, 판독 응답 ID, 공식 코드와 원문 범례 번호를 기록했다. 표 수치, NFPA, 좌표 정확도와 절차도는 이번 승인에 포함되지 않는다.

`prepare`는 검토 기록과 사전의 해시를 검사하고, 본문 366개 청크에 페이지별 그림 보충 청크 2개를 추가한다. 보충 청크에는 원문 문자 오프셋을 만들지 않으며 `content_type=reviewed_pictogram_supplement`로 구분한다. 인식 참고 PDF 자체는 여전히 검색 대상에서 제외된다.

`build`는 기존 인덱스의 무결성과 임베딩 모델, 차원을 확인해 같은 텍스트의 벡터를 재사용한다. 추가 텍스트만 임베딩하고 368개 청크의 새 인덱스를 검증한 뒤 활성 포인터를 교체한다. 이전 인덱스는 남긴다. 재실행 시 같은 보충자료가 중복 추가되지 않는다.

검증 결과는 `pipeline_artifacts/vision/ingestion-verification.json`에 기록한다. 이전 답변 캐시와 RAGAS 점수는 이전 인덱스의 결과이며 이번 인덱스의 평가로 간주하지 않는다.
