import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rag-code-template_ext"))
import ops_dashboard as ops  # noqa: E402

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def row(i, day, **extra):
    base = {
        "id": i, "created_at": datetime(2026, 10, day, 9, 0), "username": "kim",
        "conversation_id": f"c{i % 2}", "question": "염산 누출 시 조치?", "normalized_question": None,
        "answer": "환기하고 대피하세요.", "sources": [], "handoff": False, "needs_review": False,
        "is_incident": False, "used_history": False, "typo_fixes": [], "matched_materials": ["염화수소"],
        "verified_qa_ids": [], "latency_ms": 1000 * i, "feedback": None,
    }
    base.update(extra)
    return base


class BuildLogRecordTest(unittest.TestCase):
    def test_collects_turn_signals(self):
        record = ops.build_log_record(
            username="kim", chat={"conversation_id": "c1", "search_question": "염산 누출", "streaming": True},
            state={"q": "염산 누출", "use_history": True, "typo_fixes": [("염화수수", "염화수소")],
                   "verified_qa_ids": [3]},
            result={"answer": "대피", "handoff": False, "needs_review": True,
                    "graph_retrieval": {"matched_materials": [{"name_raw": "염화수소 (HCl)"}]}},
            latency_ms=-5, is_incident=True, assistant_message_id=10)
        self.assertEqual(record["conversation_id"], "c1")
        self.assertTrue(record["used_history"] and record["streaming"] and record["is_incident"])
        self.assertEqual(record["latency_ms"], 0)
        self.assertIn("염화수소", record["matched_materials"])
        self.assertNotIn("HCl", record["matched_materials"])
        self.assertEqual(record["typo_fixes"], '[["염화수수", "염화수소"]]')


class SummarizeTest(unittest.TestCase):
    def test_totals_daily_and_queues(self):
        rows = [
            row(1, 26, feedback=1),
            row(2, 26, handoff=True, question="모르는 물질?"),
            row(3, 25, feedback=-1, used_history=True, typo_fixes=[["a", "b"]]),
            row(4, 24, feedback=1, verified_qa_ids=[7]),
        ]
        result = ops.summarize(rows, all_time_total=40, verified=[{"id": 7, "source_log_id": 4}], days=7, now=NOW)
        totals = result["totals"]
        self.assertEqual(totals["questions_all_time"], 40)
        self.assertEqual(totals["questions"], 4)
        self.assertEqual(totals["conversations"], 2)
        self.assertEqual(totals["handoff_rate"], 0.25)
        self.assertEqual(totals["satisfaction"], round(2 / 3, 4))
        self.assertEqual(totals["p95_latency_ms"], 4000)
        self.assertEqual(totals["verified_hits"], 1)
        self.assertEqual(len(result["daily"]), 7)
        self.assertEqual(result["daily"][-1], {"date": "2026-10-26", "questions": 2, "handoff": 1,
                                               "needs_review": 0, "avg_latency_ms": 1500})
        self.assertEqual([c["id"] for c in result["attention"]], [2, 3])
        # 이미 검증 Q&A로 등록된 로그(4)는 후보에서 빠진다
        self.assertEqual([c["id"] for c in result["candidates"]], [1])
        self.assertEqual(result["frequent_questions"][0]["count"], 3)
        self.assertEqual(result["top_materials"][0], {"name": "염화수소", "count": 4})

    def test_empty_window(self):
        result = ops.summarize([], all_time_total=0, verified=[], days=1, now=NOW)
        self.assertIsNone(result["totals"]["handoff_rate"])
        self.assertIsNone(result["totals"]["p95_latency_ms"])
        self.assertEqual(result["daily"][0]["questions"], 0)


if __name__ == "__main__":
    unittest.main()
