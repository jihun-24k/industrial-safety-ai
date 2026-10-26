import ast
import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from pipeline.query_translation import normalize_query


SOURCE_PATH = Path(__file__).parents[1] / "rag-code-template_ext" / "rag_external-web_pdf_closed_llm.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def load_functions(*names, namespace=None):
    selected = [node for node in TREE.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in names]
    module = ast.Module(body=selected, type_ignores=[])
    scope = {"translate_input": normalize_query, **(namespace or {})}
    exec(compile(module, str(SOURCE_PATH), "exec"), scope)
    return [scope[name] for name in names]


class FakeEncoder:
    def encode(self, value):
        return list(value)

    def decode(self, tokens):
        return "".join(tokens)


class FakeMappings:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class FakeResult:
    def __init__(self, rows=(), rowcount=1):
        self.rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return FakeMappings(self.rows)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_):
        return False


class ChatPersistenceTests(unittest.TestCase):
    def test_complete_turn_order_and_context_query(self):
        complete_turns, contextual_search_question = load_functions(
            "complete_turns", "contextual_search_question"
        )
        messages = [
            {"id": 1, "role": "user", "content": "염산을 쏟았어"},
            {"id": 2, "role": "assistant", "content": "접근을 통제하세요"},
            {"id": 3, "role": "user", "content": "보호구는?"},
            {"id": 4, "role": "assistant", "content": "보안경을 쓰세요"},
            {"id": 5, "role": "user", "content": "미완성 질문"},
        ]
        turns = complete_turns(messages)
        self.assertEqual([[m["id"] for m in turn] for turn in turns], [[1, 2], [3, 4]])
        query = contextual_search_question("그 다음은?", "염산 누출", messages)
        self.assertLess(query.index("염산을 쏟았어"), query.index("보호구는?"))
        self.assertTrue(query.endswith("현재 질문: 그 다음은?"))

    def test_summary_cutoff_keeps_only_complete_recent_turns(self):
        message_tokens, complete_turns, split_history = load_functions(
            "_message_tokens", "complete_turns", "split_history_for_summary",
            namespace={"_TOKEN_ENCODER": FakeEncoder(), "HISTORY_TOKEN_BUDGET": 10,
                       "RECENT_HISTORY_TOKEN_BUDGET": 10, "SUMMARY_TOKEN_BUDGET": 10},
        )
        split_history.__globals__["_message_tokens"] = message_tokens
        split_history.__globals__["complete_turns"] = complete_turns
        messages = [
            {"id": 1, "role": "user", "content": "aaaa"},
            {"id": 2, "role": "assistant", "content": "bbbb"},
            {"id": 3, "role": "user", "content": "cccc"},
            {"id": 4, "role": "assistant", "content": "dddd"},
        ]
        old, recent = split_history(messages, budget=30, recent_budget=20)
        self.assertEqual([m["id"] for m in old[0]], [1, 2])
        self.assertEqual([m["id"] for m in recent[0]], [3, 4])

    def test_summary_budget_caps_summary_and_excludes_oversized_latest_turn(self):
        text_tokens, bounded, message_tokens, complete_turns, split_history = load_functions(
            "_text_tokens", "_bounded_summary", "_message_tokens", "complete_turns",
            "split_history_for_summary",
            namespace={"_TOKEN_ENCODER": FakeEncoder(), "HISTORY_TOKEN_BUDGET": 20,
                       "RECENT_HISTORY_TOKEN_BUDGET": 20, "SUMMARY_TOKEN_BUDGET": 8},
        )
        split_history.__globals__.update(
            _message_tokens=message_tokens, complete_turns=complete_turns)
        self.assertEqual(bounded("abcdefghijk"), "abcdefgh")
        messages = [
            {"id": 1, "role": "user", "content": "a"},
            {"id": 2, "role": "assistant", "content": "b"},
            {"id": 3, "role": "user", "content": "c"},
            {"id": 4, "role": "assistant", "content": "d"},
        ]
        old, recent = split_history(messages, summary_tokens=text_tokens("12345678"))
        self.assertEqual([[m["id"] for m in turn] for turn in old], [[1, 2]])
        self.assertEqual([[m["id"] for m in turn] for turn in recent], [[3, 4]])
        oversized = [
            {"id": 5, "role": "user", "content": "x" * 20},
            {"id": 6, "role": "assistant", "content": "y" * 20},
        ]
        old, recent = split_history(oversized)
        self.assertEqual([[m["id"] for m in turn] for turn in old], [[5, 6]])
        self.assertEqual(recent, [])

    def test_owner_filter_is_part_of_conversation_lookup(self):
        captured = {}

        class Connection:
            async def execute(self, statement, params):
                captured.update(sql=str(statement), params=params)
                return FakeResult([{"id": "c1"}])

        owned, = load_functions("_owned_conversation", namespace={"text": lambda value: value})
        row = asyncio.run(owned(Connection(), "c1", "alice"))
        self.assertEqual(row["id"], "c1")
        self.assertIn("owner_username = :username", captured["sql"])
        self.assertEqual(captured["params"], {"conversation_id": "c1", "username": "alice"})

    def test_database_queries_define_stable_ordering(self):
        self.assertIn("ORDER BY updated_at DESC, id DESC", SOURCE)
        self.assertIn("ORDER BY id ASC", SOURCE)

    def test_summary_failure_preserves_summary_and_cursor(self):
        conversation = {"id": "c1", "title": "기존 대화", "summary": "기존 요약",
                        "summary_through_message_id": 2}
        rows = [{"id": 3, "role": "user", "content": "질문"},
                {"id": 4, "role": "assistant", "content": "답변"}]

        class Connection:
            async def execute(self, *_):
                return FakeResult(rows)

        class Engine:
            begin_calls = 0

            def connect(self):
                return AsyncContext(Connection())

            def begin(self):
                self.begin_calls += 1
                return AsyncContext(Connection())

        async def owned(*_):
            return conversation

        async def fail_summary(*_):
            raise RuntimeError("summary unavailable")

        def split(*_args, **_kwargs):
            turn = [[rows[0], rows[1]]]
            return (turn, turn)

        engine = Engine()
        class FakeHTTPException(Exception):
            pass

        prepare_chat, = load_functions("prepare_chat", namespace={
            "engine": engine, "_owned_conversation": owned, "text": lambda value: value,
            "split_history_for_summary": split, "_summarize_turns": fail_summary,
            "contextual_search_question": lambda q, summary, messages: f"{summary}|{q}",
            "_bounded_summary": lambda value: value, "_text_tokens": lambda value: len(value or ""),
            "HTTPException": FakeHTTPException, "uuid": __import__("uuid"),
            "RAGRequest": object,
            "RECENT_HISTORY_TOKEN_BUDGET": 10,
        })
        rag_request = SimpleNamespace(conversation_id="c1", prompt="후속 질문")
        chat = asyncio.run(prepare_chat("alice", rag_request))
        self.assertEqual(chat["summary"], "기존 요약")
        self.assertEqual(conversation["summary_through_message_id"], 2)
        self.assertEqual(engine.begin_calls, 0)

    def test_summary_success_defers_cursor_until_final_storage(self):
        conversation = {"id": "c1", "title": "기존 대화", "summary": "기존 요약",
                        "summary_through_message_id": 2}
        rows = [{"id": 3, "role": "user", "content": "질문"},
                {"id": 4, "role": "assistant", "content": "답변"}]
        class Connection:
            async def execute(self, statement, params):
                return FakeResult(rows)

        class Engine:
            begin_calls = 0

            def connect(self):
                return AsyncContext(Connection())

            def begin(self):
                self.begin_calls += 1
                return AsyncContext(Connection())

        async def owned(*_):
            return conversation

        async def summarize(*_):
            return "새 요약"

        engine = Engine()
        prepare_chat, = load_functions("prepare_chat", namespace={
            "engine": engine, "_owned_conversation": owned, "text": lambda value: value,
            "split_history_for_summary": lambda *_args, **_kwargs: ([[rows[0], rows[1]]], []),
            "_summarize_turns": summarize,
            "contextual_search_question": lambda q, summary, messages: f"{summary}|{q}",
            "_bounded_summary": lambda value: value, "_text_tokens": lambda value: len(value or ""),
            "HTTPException": RuntimeError, "uuid": __import__("uuid"),
            "RAGRequest": object,
            "RECENT_HISTORY_TOKEN_BUDGET": 10,
        })
        chat = asyncio.run(prepare_chat("alice", SimpleNamespace(conversation_id="c1", prompt="후속")))
        self.assertEqual(engine.begin_calls, 0)
        self.assertEqual(chat["summary"], "새 요약")
        self.assertEqual(chat["pending_summary_cursor"], 4)
        self.assertEqual(chat["pending_summary"], "새 요약")

    def test_final_storage_is_one_transaction_and_ordered_pair(self):
        executed = []

        class Connection:
            async def execute(self, statement, params):
                executed.append((str(statement), params))
                if "summary_through_message_id" in str(statement):
                    return FakeResult(rowcount=0)
                return FakeResult()

        class Engine:
            begin_calls = 0

            def begin(self):
                self.begin_calls += 1
                return AsyncContext(Connection())

        async def owned(*_):
            return {"id": "c1"}

        engine = Engine()
        save_turn, = load_functions("save_turn", namespace={
            "engine": engine, "text": lambda value: value, "json": json,
            "HTTPException": RuntimeError, "_owned_conversation": owned,
        })
        chat = {"is_new": False, "conversation_id": "c1", "title": "첫 질문",
                "pending_summary": "새 요약", "pending_summary_cursor": 4}
        result = {"prompt": "질문", "answer": "답변", "sources": ["manual"],
                  "needs_review": True, "handoff": False, "clarifying_questions": ["어디인가요?"]}
        asyncio.run(save_turn("alice", chat, result))
        self.assertEqual(engine.begin_calls, 1)
        roles = [params.get("content") for sql, params in executed if "INSERT INTO chat_messages" in sql]
        self.assertEqual(roles, ["질문", "답변"])
        summary_update = [params for sql, params in executed if "summary_through_message_id" in sql][0]
        self.assertEqual((summary_update["summary"], summary_update["cutoff"]), ("새 요약", 4))
        summary_sql = [sql for sql, _ in executed if "summary_through_message_id" in sql][0]
        self.assertIn("summary_through_message_id < :cutoff", summary_sql)
        assistant_params = [params for sql, params in executed if "clarifying_questions" in sql][0]
        self.assertEqual(json.loads(assistant_params["sources"]), ["manual"])

    def test_all_successful_response_paths_use_shared_finalizer(self):
        functions = {node.name: node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef)}
        self.assertEqual(sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id == "save_turn" for node in ast.walk(functions["finalize_turn"])), 1)
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id == "save_turn"
                             for name in ("rag_query", "rag_query_stream") for node in ast.walk(functions[name])))
        finalizer_calls = [node for name in ("rag_query", "rag_query_stream")
                           for node in ast.walk(functions[name])
                           if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                           and node.func.id == "finalize_turn"]
        self.assertEqual(len(finalizer_calls), 3)
        self.assertTrue(all(isinstance(call.args[0], ast.Name) and call.args[0].id == "request"
                            for call in finalizer_calls))

    def test_disconnected_request_skips_shared_final_storage(self):
        saved = []

        class DisconnectedRequest:
            async def is_disconnected(self):
                return True

        async def save(*args):
            saved.append(args)

        finalize, = load_functions("finalize_turn", namespace={
            "Request": object, "asyncio": asyncio,
            "finish_rag": lambda _state, _raw: {"answer": "완료"},
            "save_turn": save,
        })
        chat = {"conversation_id": "c1", "title": "대화"}
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(finalize(DisconnectedRequest(), "alice", chat, {}, "raw"))
        self.assertEqual(saved, [])


if __name__ == "__main__":
    unittest.main()


class IndependentIncidentTests(unittest.TestCase):
    def test_prior_material_is_not_carried_into_new_incident(self):
        (contextual,) = load_functions('contextual_search_question')
        q = '화학약품이 누출됐고 한 사람이 어지러움을 호소해. 사람 보호, 현장 대응, 보고 순서로 설명해줘.'
        history = [{'role':'user', 'content':'염산을 쏟았어'}]
        self.assertEqual(contextual(q, '염화수소 위험', history), q)
        self.assertIn('염산', contextual('그 다음은?', None, history))
        self.assertEqual(contextual('그럼 물질을 모르겠어', None, history), '그럼 물질을 모르겠어')
