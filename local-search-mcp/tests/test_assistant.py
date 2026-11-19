import asyncio
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI


SOURCE = Path(__file__).resolve().parents[1] / "src"
with patch.object(sys, "path", [str(SOURCE), *sys.path]):
    from assistant import DEFAULT_MODEL, FILE_TOOLS, MAX_TOOL_ROUNDS, AssistantError, ask, main


def function_call(call_id, name, arguments):
    return {
        "type": "function_call",
        "name": name,
        "arguments": arguments,
        "call_id": call_id,
        "status": "completed",
    }


def message(text):
    return {
        "type": "message",
        "id": "msg_test",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


class AssistantTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.root = Path(directory).resolve() / "files"
        self.root.mkdir()
        self.report = self.root / "relatorio.txt"
        self.text = "Orçamento de infraestrutura 2025."
        self.report.write_text(self.text, encoding="utf-8")
        self.enterContext(
            patch.dict(
                os.environ,
                {"LOCAL_SEARCH_ROOTS": str(self.root), "LOCAL_SEARCH_POSTGRES_DSN": ""},
            )
        )
        self.requests = []

    def run_question(self, question, reply):
        def handler(request):
            self.assertEqual(request.url.path, "/v1/responses")
            body = json.loads(request.content)
            self.requests.append(body)
            return httpx.Response(
                200,
                json={
                    "id": f"resp_{len(self.requests)}",
                    "object": "response",
                    "created_at": 0,
                    "model": DEFAULT_MODEL,
                    "status": "completed",
                    "output": reply(body, len(self.requests)),
                },
            )

        async def run():
            transport = httpx.MockTransport(handler)
            async with AsyncOpenAI(
                api_key="test-key",
                base_url="https://api.openai.com/v1",
                http_client=httpx.AsyncClient(transport=transport),
                max_retries=0,
            ) as client:
                return await ask(client, question, DEFAULT_MODEL)

        return asyncio.run(run())

    def test_search_then_read_via_mcp(self):
        question = "Encontre o relatório de infraestrutura e leia o conteúdo."
        reasoning = {
            "type": "reasoning",
            "id": "rs_test",
            "summary": [],
            "encrypted_content": "encrypted-test-content",
        }

        def reply(body, turn):
            self.assertEqual(body["model"], DEFAULT_MODEL)
            self.assertFalse(body["store"])
            self.assertEqual({tool["name"] for tool in body["tools"]}, FILE_TOOLS)
            if turn == 1:
                self.assertEqual(body["input"], [{"role": "user", "content": question}])
                return [
                    reasoning,
                    function_call("call_search", "search_files", '{"query":"infraestrutura"}'),
                ]
            self.assertIn(reasoning, body["input"])
            output = body["input"][-1]
            self.assertEqual(output["type"], "function_call_output")
            payload = json.loads(output["output"])
            self.assertFalse(payload["is_error"])
            if turn == 2:
                self.assertEqual(output["call_id"], "call_search")
                results = json.loads(payload["content"][0])
                self.assertEqual(results["results"][0]["path"], str(self.report))
                return [
                    function_call("call_read", "read_file", json.dumps({"path": str(self.report)}))
                ]
            self.assertEqual(turn, 3)
            self.assertEqual(output["call_id"], "call_read")
            self.assertEqual(payload["content"], [self.text])
            return [message("Encontrei o relatório.")]

        self.assertEqual(self.run_question(question, reply), "Encontrei o relatório.")
        self.assertEqual(len(self.requests), 3)

    def test_invalid_calls_and_unauthorized_paths_return_tool_errors(self):
        (self.root.parent / "outside.txt").write_text("outside", encoding="utf-8")

        def reply(body, turn):
            if turn == 1:
                return [function_call("call_bad", "read_file", "[]")]
            result = json.loads(body["input"][-1]["output"])
            self.assertTrue(result["is_error"])
            if turn == 2:
                self.assertIn("objeto JSON", result["content"][0])
                return [function_call("call_unknown", "unknown_tool", "{}")]
            if turn == 3:
                self.assertIn("indisponível", result["content"][0])
                return [function_call("call_outside", "read_file", '{"path":"../outside.txt"}')]
            self.assertEqual(turn, 4)
            self.assertIn("outside the authorized folders", result["content"][0])
            return [message("O arquivo não está nas pastas autorizadas.")]

        self.assertIn("pastas autorizadas", self.run_question("Leia outside.txt", reply))

    def test_default_folder_when_no_roots_are_configured(self):
        os.environ.pop("LOCAL_SEARCH_ROOTS")

        def reply(body, turn):
            if turn == 1:
                return [function_call("call_folders", "list_indexed_roots", "{}")]
            result = json.loads(body["input"][-1]["output"])
            self.assertFalse(result["is_error"])
            folders = json.loads(result["content"][0])["roots"]
            self.assertEqual([folder["path"] for folder in folders], [str(SOURCE.parent / "data")])
            return [message("Pasta padrão consultada.")]

        self.assertEqual(self.run_question("Liste as pastas.", reply), "Pasta padrão consultada.")

    def test_tool_round_limit(self):
        def reply(body, turn):
            return [function_call(f"call_{turn}", "unknown_tool", "{}")]

        with self.assertRaises(ExceptionGroup) as error:
            self.run_question("Teste o limite.", reply)
        self.assertIsNotNone(error.exception.subgroup(AssistantError))
        self.assertEqual(len(self.requests), MAX_TOOL_ROUNDS + 1)

    def test_cli_requires_api_key(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SOURCE / "assistant.py"), "Liste os arquivos."],
            env={**os.environ, "OPENAI_API_KEY": ""},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("OPENAI_API_KEY", result.stderr)

    def test_cli_distinguishes_openai_429_errors(self):
        for code, error_type, expected_code, expected_message in (
            ("credit_balance_exhausted", "insufficient_quota", "credit_balance_exhausted", "saldo de créditos"),
            ("project_spend_limit_exceeded", "insufficient_quota", "project_spend_limit_exceeded", "limite de gastos"),
            (None, "insufficient_quota", "insufficient_quota", "cota da API"),
            ("rate_limit_exceeded", "rate_limit_error", "rate_limit_exceeded", "limite temporário"),
        ):
            with self.subTest(code=code, error_type=error_type):
                transport = httpx.MockTransport(
                    lambda request: httpx.Response(
                        429, json={"error": {"code": code, "type": error_type, "message": "private response"}}
                    )
                )
                client = AsyncOpenAI(
                    api_key="test-key",
                    base_url="https://api.openai.com/v1",
                    http_client=httpx.AsyncClient(transport=transport),
                    max_retries=0,
                )
                stderr = StringIO()
                with (
                    patch("assistant.AsyncOpenAI", return_value=client),
                    patch.object(sys, "argv", ["assistant.py", "Liste as pastas."]),
                    patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
                    redirect_stderr(stderr),
                ):
                    self.assertEqual(main(), 1)
                self.assertIn(f"HTTP 429 ({expected_code})", stderr.getvalue())
                self.assertIn(expected_message, stderr.getvalue())
                self.assertNotIn("private response", stderr.getvalue())
