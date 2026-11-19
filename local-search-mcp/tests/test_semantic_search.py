import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from openai import OpenAI


SOURCE = Path(__file__).resolve().parents[1] / "src"
with patch.object(sys, "path", [str(SOURCE), *sys.path]):
    from indexer import build_index
    from search import filter_index, search_index
    from semantic_search import EMBEDDING_MODEL, SemanticSearchError, search_semantic


class SemanticSearchTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.root = Path(directory).resolve()
        self.relevant = self.root / "arquivo.txt"
        self.relevant.write_text(
            "x" * 1500 + "\nMenor consumo de gasolina.",
            encoding="utf-8",
        )
        (self.root / "receitas.md").write_text("Receita de bolo e ovos.", encoding="utf-8")
        (self.root / "imagem.png").write_bytes(b"\x89PNG")
        self.query = "economizar combustível"
        self.files = build_index((self.root,))
        self.enterContext(patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}))

    def test_semantic_search_ranks_a_match_without_shared_words(self):
        self.assertEqual(search_index(self.files, self.query)["count"], 0)
        requests = []

        def handler(request):
            self.assertEqual(request.url.path, "/v1/embeddings")
            body = json.loads(request.content)
            self.assertEqual(body["model"], EMBEDDING_MODEL)
            requests.append(body["input"])
            data = []
            for index, text in enumerate(body["input"]):
                relevant = text == self.query or "gasolina" in text
                data.append(
                    {
                        "object": "embedding",
                        "index": index,
                        "embedding": [2.0, 0.0] if relevant else [0.0, 3.0],
                    }
                )
            return httpx.Response(200, json={"object": "list", "data": data[::-1], "model": EMBEDDING_MODEL})

        client = OpenAI(
            api_key="test-key", base_url="https://api.openai.com/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        with patch("semantic_search.OpenAI", return_value=client), patch("semantic_search.BATCH_SIZE", 2):
            result = search_semantic(self.files, self.query)

        self.assertEqual(requests[0], [self.query])
        self.assertEqual(len(requests), 3)
        self.assertEqual([item["name"] for item in result["results"]], ["arquivo.txt", "receitas.md"])
        best = result["results"][0]
        self.assertEqual(best["similarity"], 1.0)
        self.assertIn("gasolina", best["snippet"])
        self.assertEqual(best["path"], str(self.relevant))

    def test_metadata_filters_avoid_embedding_ineligible_files(self):
        files = filter_index(self.files, extension="png")
        with patch("semantic_search.OpenAI") as client:
            self.assertEqual(search_semantic(files, self.query)["results"], [])
            client.assert_not_called()

    def test_provider_error_is_reported_without_response_body(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": {"message": "private response"}})
        )
        client = OpenAI(
            api_key="test-key", base_url="https://api.openai.com/v1",
            http_client=httpx.Client(transport=transport),
        )
        with patch("semantic_search.OpenAI", return_value=client):
            with self.assertRaisesRegex(SemanticSearchError, r"returned HTTP 401\.$"):
                search_semantic(self.files, self.query)
