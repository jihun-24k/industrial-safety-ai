"""SafeOps 운영 로그 · 지표 · 검증 Q&A

교수님 피드백(현장 적용) 반영:
- 로그 쌓기: 질의 하나마다 질문·검색 질문·답변·출처·handoff·긴급·응답 시간 등을 rag_query_logs에 기록
- 맥락 보존: 대화 제목·요약, 이전 대화 참고 여부를 로그와 함께 보여줌
- 질의응답 누적 → RAG 반영: 운영자가 확인한 답변을 verified_qa로 저장, 비슷한 질문에 근거로 함께 제공
- 지표: 누적 현황·일별 추이·handoff율·응답 시간·만족도를 /ops/metrics로 제공

DB 접근 함수는 SQLAlchemy AsyncConnection을 받고, 집계(summarize)는 DB 없이 테스트할 수 있는 순수 함수다.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

try:  # 대시보드 날짜는 현장 시간(기본 한국 시간) 기준으로 나눈다
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(os.getenv("OPS_TIMEZONE", "Asia/Seoul"))
except Exception:  # tzdata가 없는 환경
    LOCAL_TZ = timezone(timedelta(hours=9))

OPS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS rag_query_logs (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      username VARCHAR(100) NOT NULL,
      conversation_id CHAR(36) NULL,
      assistant_message_id BIGINT UNSIGNED NULL,
      question LONGTEXT NOT NULL,
      normalized_question LONGTEXT NULL,
      search_question LONGTEXT NULL,
      source_language VARCHAR(3) NULL,
      answer LONGTEXT NOT NULL,
      sources JSON NULL,
      handoff BOOLEAN NOT NULL DEFAULT FALSE,
      needs_review BOOLEAN NOT NULL DEFAULT FALSE,
      is_incident BOOLEAN NOT NULL DEFAULT FALSE,
      used_history BOOLEAN NOT NULL DEFAULT FALSE,
      typo_fixes JSON NULL,
      search_queries JSON NULL,
      matched_materials JSON NULL,
      verified_qa_ids JSON NULL,
      latency_ms INT UNSIGNED NULL,
      streaming BOOLEAN NOT NULL DEFAULT FALSE,
      feedback TINYINT NULL,
      feedback_note VARCHAR(500) NULL,
      feedback_at TIMESTAMP NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_rag_query_logs_created (created_at),
      KEY idx_rag_query_logs_conversation (conversation_id),
      KEY idx_rag_query_logs_message (assistant_message_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS verified_qa (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      question LONGTEXT NOT NULL,
      answer LONGTEXT NOT NULL,
      sources JSON NULL,
      source_log_id BIGINT UNSIGNED NULL,
      created_by VARCHAR(100) NOT NULL,
      status VARCHAR(16) NOT NULL DEFAULT 'active',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_verified_qa_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)

MAX_WINDOW_ROWS = 5000   # 지표 계산에 읽는 최대 로그 수 (프로젝트 규모 기준)
JSON_FIELDS = ("sources", "typo_fixes", "search_queries", "matched_materials", "verified_qa_ids")
BOOL_FIELDS = ("handoff", "needs_review", "is_incident", "used_history", "streaming")


def _json(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _dump(value) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def material_names(materials) -> list[str]:
    """그래프가 찾은 물질(카탈로그 항목 dict 또는 문자열)을 이름 목록으로 바꾼다."""
    names = []
    for item in materials or []:
        if isinstance(item, dict):
            name = item.get("name_raw") or item.get("name") or item.get("label")
            if name:
                names.append(re.sub(r"\s*\(.*\)$", "", str(name)).strip() or str(name))
        elif item:
            names.append(str(item))
    return list(dict.fromkeys(names))


def build_log_record(*, username: str, chat: dict, state: dict, result: dict,
                     latency_ms: int | None, is_incident: bool, assistant_message_id: int | None) -> dict:
    """finalize_turn에서 받은 정보로 로그 한 줄을 만든다 (DB 없이 테스트 가능)."""
    graph = result.get("graph_retrieval") or state.get("graph_retrieval") or {}
    return {
        "username": username,
        "conversation_id": result.get("conversation_id") or chat.get("conversation_id"),
        "assistant_message_id": assistant_message_id,
        "question": result.get("prompt") or state.get("q", ""),
        "normalized_question": result.get("normalized_prompt") or state.get("q"),
        "search_question": chat.get("search_question"),
        "source_language": result.get("source_language"),
        "answer": result.get("answer", ""),
        "sources": _dump(result.get("sources", [])),
        "handoff": bool(result.get("handoff")),
        "needs_review": bool(result.get("needs_review")),
        "is_incident": bool(is_incident),
        "used_history": bool(state.get("use_history")),
        "typo_fixes": _dump([list(pair) for pair in state.get("typo_fixes", [])]),
        "search_queries": _dump(result.get("search_queries", [])),
        "matched_materials": _dump(material_names(graph.get("matched_materials"))),
        "verified_qa_ids": _dump(state.get("verified_qa_ids", [])),
        "latency_ms": None if latency_ms is None else max(0, int(latency_ms)),
        "streaming": bool(chat.get("streaming")),
    }


async def create_tables(connection):
    for statement in OPS_SCHEMA:
        await connection.execute(text(statement))


async def insert_log(connection, record: dict) -> int | None:
    result = await connection.execute(text("""
        INSERT INTO rag_query_logs
          (username, conversation_id, assistant_message_id, question, normalized_question, search_question,
           source_language, answer, sources, handoff, needs_review, is_incident, used_history, typo_fixes,
           search_queries, matched_materials, verified_qa_ids, latency_ms, streaming)
        VALUES
          (:username, :conversation_id, :assistant_message_id, :question, :normalized_question, :search_question,
           :source_language, :answer, :sources, :handoff, :needs_review, :is_incident, :used_history, :typo_fixes,
           :search_queries, :matched_materials, :verified_qa_ids, :latency_ms, :streaming)
    """), record)
    return getattr(result, "lastrowid", None)


async def set_feedback(connection, log_id: int, username: str, rating: int, note: str | None) -> bool:
    """본인 질문에만 평가할 수 있다. 다시 누르면 덮어쓴다."""
    result = await connection.execute(text("""
        UPDATE rag_query_logs
        SET feedback = :rating, feedback_note = :note, feedback_at = CURRENT_TIMESTAMP
        WHERE id = :log_id AND username = :username
    """), {"rating": rating, "note": (note or None), "log_id": log_id, "username": username})
    return (getattr(result, "rowcount", 0) or 0) > 0


async def feedback_for_messages(connection, message_ids: list[int]) -> dict[int, dict]:
    """저장된 대화를 다시 열 때 답변별 로그 ID·평가를 붙이기 위한 조회."""
    if not message_ids:
        return {}
    params = {f"m{i}": mid for i, mid in enumerate(message_ids)}
    placeholders = ", ".join(f":{key}" for key in params)
    result = await connection.execute(text(f"""
        SELECT id, assistant_message_id, feedback FROM rag_query_logs
        WHERE assistant_message_id IN ({placeholders})
    """), params)
    return {int(row["assistant_message_id"]): {"log_id": int(row["id"]), "feedback": row["feedback"]}
            for row in result.mappings()}


def _normalize_row(row) -> dict:
    item = dict(row)
    if item.get("created_ts") is not None:  # DB 시간대와 무관하게 UTC로 맞춘다
        item["created_at"] = datetime.fromtimestamp(float(item.pop("created_ts")), timezone.utc)
    for key in JSON_FIELDS:
        if key in item:
            item[key] = _json(item[key], [])
    for key in BOOL_FIELDS:
        if key in item:
            item[key] = bool(item[key])
    return item


def window_start(days: int, now: datetime | None = None) -> datetime:
    """'오늘'=오늘 0시부터, '7일'=6일 전 0시부터 (현장 시간 기준)."""
    local = _as_utc(now or datetime.now(timezone.utc)).astimezone(LOCAL_TZ)
    start = (local - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


async def fetch_window(connection, since: datetime) -> list[dict]:
    result = await connection.execute(text(f"""
        SELECT l.id, l.username, l.conversation_id, l.question, l.normalized_question, l.answer, l.sources,
               l.handoff, l.needs_review, l.is_incident, l.used_history, l.typo_fixes, l.search_queries,
               l.matched_materials, l.verified_qa_ids, l.latency_ms, l.streaming, l.feedback, l.feedback_note,
               UNIX_TIMESTAMP(l.created_at) AS created_ts, c.title AS conversation_title, c.summary AS conversation_summary
        FROM rag_query_logs l
        LEFT JOIN chat_conversations c ON c.id = l.conversation_id
        WHERE l.created_at >= FROM_UNIXTIME(:since_ts)
        ORDER BY l.id DESC
        LIMIT {MAX_WINDOW_ROWS}
    """), {"since_ts": int(_as_utc(since).timestamp())})
    return [_normalize_row(row) for row in result.mappings()]


async def fetch_log(connection, log_id: int) -> dict | None:
    result = await connection.execute(text("""
        SELECT id, username, question, normalized_question, answer, sources FROM rag_query_logs WHERE id = :id
    """), {"id": log_id})
    row = result.mappings().first()
    return _normalize_row(row) if row else None


async def count_all_logs(connection) -> int:
    result = await connection.execute(text("SELECT COUNT(*) AS n FROM rag_query_logs"))
    return int(result.mappings().first()["n"])


async def list_verified(connection, include_retired: bool = False) -> list[dict]:
    where = "" if include_retired else "WHERE status = 'active'"
    result = await connection.execute(text(f"""
        SELECT id, question, answer, sources, source_log_id, created_by, status, created_at, updated_at
        FROM verified_qa {where} ORDER BY id DESC
    """))
    return [_normalize_row(row) for row in result.mappings()]


async def create_verified(connection, *, question: str, answer: str, sources: list, source_log_id: int | None,
                          created_by: str) -> int | None:
    result = await connection.execute(text("""
        INSERT INTO verified_qa (question, answer, sources, source_log_id, created_by)
        VALUES (:question, :answer, :sources, :source_log_id, :created_by)
    """), {"question": question, "answer": answer, "sources": _dump(sources),
           "source_log_id": source_log_id, "created_by": created_by})
    return getattr(result, "lastrowid", None)


async def retire_verified(connection, qa_id: int) -> bool:
    result = await connection.execute(text("""
        UPDATE verified_qa SET status = 'retired' WHERE id = :id AND status = 'active'
    """), {"id": qa_id})
    return (getattr(result, "rowcount", 0) or 0) > 0


# ---------------------------------------------------------------- 집계 (순수 함수)

def percentile(values: list[float], p: float) -> int | None:
    """최근린 방식 백분위수 (p=95 → p95)."""
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    rank = max(1, math.ceil(p / 100 * len(data)))
    return int(data[rank - 1])


def _question_key(question: str) -> str:
    return re.sub(r"[\s?!.,~]+", " ", (question or "").strip().lower()).strip()


def _as_utc(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _preview(value: str, limit: int = 160) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _log_card(row: dict) -> dict:
    return {
        "id": row["id"],
        "created_at": _as_utc(row["created_at"]).isoformat(),  # 화면에서 브라우저 시간으로 표시
        "username": row["username"],
        "conversation_title": row.get("conversation_title"),
        "conversation_summary": _preview(row.get("conversation_summary") or "", 220) or None,
        "question": row["question"],
        "normalized_question": row.get("normalized_question"),
        "answer": row.get("answer") or "",
        "answer_preview": _preview(row.get("answer") or ""),
        "sources": row.get("sources", [])[:3],
        "handoff": row.get("handoff", False),
        "needs_review": row.get("needs_review", False),
        "used_history": row.get("used_history", False),
        "typo_fixes": row.get("typo_fixes", []),
        "verified_qa_ids": row.get("verified_qa_ids", []),
        "matched_materials": row.get("matched_materials", []),
        "latency_ms": row.get("latency_ms"),
        "feedback": row.get("feedback"),
        "feedback_note": row.get("feedback_note"),
    }


def summarize(rows: list[dict], *, all_time_total: int, verified: list[dict], days: int,
              now: datetime | None = None) -> dict:
    """기간(days) 안의 로그로 대시보드 지표를 만든다."""
    now = _as_utc(now or datetime.now(timezone.utc))
    total = len(rows)
    handoff = sum(1 for r in rows if r.get("handoff"))
    needs_review = sum(1 for r in rows if r.get("needs_review"))
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    up = sum(1 for r in rows if r.get("feedback") == 1)
    down = sum(1 for r in rows if r.get("feedback") == -1)
    verified_sources = {v.get("source_log_id") for v in verified if v.get("source_log_id")}

    daily_map = {}
    for offset in range(days - 1, -1, -1):
        day = (now.astimezone(LOCAL_TZ) - timedelta(days=offset)).date().isoformat()
        daily_map[day] = {"date": day, "questions": 0, "handoff": 0, "needs_review": 0, "_lat": []}
    for r in rows:
        day = _as_utc(r["created_at"]).astimezone(LOCAL_TZ).date().isoformat()
        bucket = daily_map.get(day)
        if bucket is None:
            continue
        bucket["questions"] += 1
        bucket["handoff"] += int(bool(r.get("handoff")))
        bucket["needs_review"] += int(bool(r.get("needs_review")))
        if r.get("latency_ms") is not None:
            bucket["_lat"].append(r["latency_ms"])
    daily = []
    for bucket in daily_map.values():
        lat = bucket.pop("_lat")
        bucket["avg_latency_ms"] = int(sum(lat) / len(lat)) if lat else None
        daily.append(bucket)

    materials = Counter(name for r in rows for name in r.get("matched_materials", []))
    questions, examples, handoffs = Counter(), {}, Counter()
    for r in rows:
        key = _question_key(r.get("normalized_question") or r.get("question"))
        if not key:
            continue
        questions[key] += 1
        examples.setdefault(key, r.get("normalized_question") or r.get("question"))
        handoffs[key] += int(bool(r.get("handoff")))

    recent = [_log_card(r) for r in rows[:15]]
    attention = [_log_card(r) for r in rows
                 if (r.get("handoff") or r.get("feedback") == -1) and r["id"] not in verified_sources][:15]
    candidates = [_log_card(r) for r in rows
                  if r.get("feedback") == 1 and not r.get("handoff") and r["id"] not in verified_sources][:10]

    return {
        "window_days": days,
        "generated_at": now.isoformat(),
        "totals": {
            "questions_all_time": all_time_total,
            "questions": total,
            "conversations": len({r.get("conversation_id") for r in rows if r.get("conversation_id")}),
            "users": len({r.get("username") for r in rows}),
            "handoff": handoff,
            "handoff_rate": round(handoff / total, 4) if total else None,
            "needs_review": needs_review,
            "incident": sum(1 for r in rows if r.get("is_incident")),
            "used_history": sum(1 for r in rows if r.get("used_history")),
            "typo_fixed": sum(1 for r in rows if r.get("typo_fixes")),
            "verified_hits": sum(1 for r in rows if r.get("verified_qa_ids")),
            "verified_active": len(verified),
            "feedback_up": up,
            "feedback_down": down,
            "satisfaction": round(up / (up + down), 4) if (up + down) else None,
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
            "p95_latency_ms": percentile(latencies, 95),
        },
        "daily": daily,
        "top_materials": [{"name": n, "count": c} for n, c in materials.most_common(8)],
        "frequent_questions": [{"question": examples[k], "count": c, "handoff": handoffs[k]}
                               for k, c in questions.most_common(8)],
        "recent": recent,
        "attention": attention,
        "candidates": candidates,
    }
