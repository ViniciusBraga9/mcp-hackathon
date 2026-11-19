import asyncio
import json
import os
import runpy
import sys
import unittest
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SOURCE = Path(__file__).resolve().parents[1] / "src"


class PythonFilesTest(unittest.TestCase):
    def test_source_files_compile(self):
        for path in sorted(SOURCE.glob("*.py")):
            with self.subTest(file=path.name):
                compile(path.read_bytes(), str(path), "exec")

    def test_indexer_and_search_load(self):
        with patch.object(sys, "path", [str(SOURCE), *sys.path]):
            for name in ("indexer.py", "search.py"):
                with self.subTest(file=name):
                    runpy.run_path(str(SOURCE / name))


def with_mcp_session(test):
    @wraps(test)
    def run(self):
        async def exercise():
            async with stdio_client(self.params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    self.session = session
                    await session.initialize()
                    await test(self)

        asyncio.run(exercise())

    return run


class MCPServerTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.base = Path(directory).resolve()
        self.root = self.base / "authorized"
        self.root.mkdir()
        self.report = self.root / "relatorio.txt"
        self.content = "Orçamento de infraestrutura 2025"
        self.report.write_text(self.content, encoding="utf-8")
        image = self.root / "imagem.png"
        image.write_bytes(b"\x89PNG")
        for path, day in ((self.report, 15), (image, 16)):
            timestamp = datetime(2025, 5, day, 23, 30, tzinfo=timezone.utc).timestamp()
            os.utime(path, (timestamp, timestamp))
        self.outside = self.base / "outside.txt"
        self.outside.write_text("outside", encoding="utf-8")

        self.params = StdioServerParameters(
            command=sys.executable,
            args=["-B", str(SOURCE / "server.py")],
            env={**os.environ, "LOCAL_SEARCH_ROOTS": str(self.root), "OPENAI_API_KEY": ""},
        )

    async def call_tool(self, tool, *, error=None, **arguments):
        result = await self.session.call_tool(tool, arguments)
        message = result.content[0].text
        if error is None:
            self.assertFalse(result.is_error, message)
        else:
            self.assertTrue(result.is_error, message)
            self.assertIn(error, message)
        return message

    @with_mcp_session
    async def test_tool_registration_and_folder_listing(self):
        tools = await self.session.list_tools()
        self.assertEqual(
            {tool.name for tool in tools.tools},
            {
                "search_files", "get_file_info", "read_file", "get_file_path", "get_folder_tree",
                "refresh_index", "list_indexed_roots", "list_indexed_folders",
            },
        )
        expected = [{"path": str(self.root), "indexed_files": 2}]
        self.assertEqual(
            json.loads(await self.call_tool("list_indexed_roots")), {"roots": expected}
        )
        self.assertEqual(
            json.loads(await self.call_tool("list_indexed_folders")), {"folders": expected}
        )

    @with_mcp_session
    async def test_get_file_path_resolves_exact_names_and_disambiguates_paths(self):
        subfolder = self.root / "projetos"
        subfolder.mkdir()
        nested = subfolder / "notas.txt"
        nested.touch()
        await self.call_tool("refresh_index")
        for name in (nested.name, str(nested), "projetos/notas.txt"):
            with self.subTest(name=name):
                result = json.loads(await self.call_tool("get_file_path", name=name))
                self.assertEqual(result, {"path": str(nested)})

        duplicate = self.root / nested.name
        duplicate.touch()
        await self.call_tool("refresh_index")
        await self.call_tool("get_file_path", name=nested.name, error="Multiple files")
        result = json.loads(await self.call_tool("get_file_path", name="projetos/notas.txt"))
        self.assertEqual(result, {"path": str(nested)})
        result = json.loads(await self.call_tool("get_file_path", name="./notas.txt"))
        self.assertEqual(result, {"path": str(duplicate)})
        for name in (str(self.outside), "../outside.txt"):
            await self.call_tool("get_file_path", name=name, error="outside the authorized folders")

    @with_mcp_session
    async def test_get_folder_tree_lists_nested_and_empty_folders(self):
        project = self.root / "projetos"
        project.mkdir()
        empty = project / "vazia"
        empty.mkdir()
        notes = project / "notas.txt"
        notes.touch()

        result = json.loads(await self.call_tool("get_folder_tree"))
        root = result["roots"][0]
        self.assertEqual(root["path"], str(self.root))
        self.assertFalse(result["truncated"])
        children = {item["name"]: item for item in root["children"]}
        self.assertEqual(set(children), {"projetos", "imagem.png", "relatorio.txt"})
        nested = {item["name"]: item for item in children["projetos"]["children"]}
        self.assertEqual(nested["notas.txt"]["path"], str(notes))
        self.assertEqual(nested["notas.txt"]["type"], "file")
        self.assertEqual(nested["vazia"]["children"], [])

        result = json.loads(await self.call_tool("get_folder_tree", path="projetos", max_depth=0))
        self.assertEqual(result["roots"][0]["path"], str(project))
        self.assertEqual(result["roots"][0]["children"], [])
        result = json.loads(await self.call_tool("get_folder_tree", path=str(project), max_entries=1))
        self.assertEqual(len(result["roots"][0]["children"]), 1)
        self.assertTrue(result["truncated"])

    @with_mcp_session
    async def test_get_folder_tree_rejects_outside_roots_and_invalid_arguments(self):
        for path in (str(self.base), ".."):
            await self.call_tool("get_folder_tree", path=path, error="outside the authorized folders")
        await self.call_tool("get_folder_tree", path=self.report.name, error="not a directory")
        await self.call_tool("get_folder_tree", max_depth=11, error="between 0 and 10")
        await self.call_tool("get_folder_tree", max_entries=0, error="between 1 and 1000")

    @with_mcp_session
    async def test_search_by_name_extension_and_content(self):
        for query, name in (
            ("RELATORIO", self.report.name),
            ("png", "imagem.png"),
            ("infraestrutura", self.report.name),
        ):
            with self.subTest(query=query):
                result = json.loads(await self.call_tool("search_files", query=query))
                self.assertEqual(result["count"], 1)
                self.assertEqual(result["results"][0]["name"], name)
                if query == "infraestrutura":
                    self.assertIn(query, result["results"][0]["snippet"])
        result = json.loads(await self.call_tool("search_files", query="semcorrespondencia"))
        self.assertEqual(result["results"], [])

    @with_mcp_session
    async def test_search_filters_by_extension_and_inclusive_utc_dates(self):
        for arguments, expected in (
            ({"extension": ".PNG"}, ["imagem.png"]),
            ({"modified_to": "2025-05-15"}, ["relatorio.txt"]),
            ({"modified_from": "2025-05-16"}, ["imagem.png"]),
            (
                {
                    "query": "infraestrutura",
                    "extension": "TXT",
                    "modified_from": "2025-05-15",
                    "modified_to": "2025-05-15",
                },
                ["relatorio.txt"],
            ),
            ({"query": "infraestrutura", "extension": "png"}, []),
        ):
            with self.subTest(arguments=arguments):
                response = json.loads(await self.call_tool("search_files", **arguments))
                self.assertEqual([item["name"] for item in response["results"]], expected)

    @with_mcp_session
    async def test_search_validates_query_and_limit(self):
        await self.call_tool("search_files", query=" ", error="cannot be empty")
        await self.call_tool("search_files", query="?!", error="searchable word")
        for limit in (0, 51):
            with self.subTest(limit=limit):
                await self.call_tool(
                    "search_files", query="relatorio", limit=limit, error="between 1 and 50"
                )
        await self.call_tool(
            "search_files", modified_from="2025-02-30", error="YYYY-MM-DD"
        )
        await self.call_tool(
            "search_files", modified_from="2025-06-01", modified_to="2025-05-01",
            error="on or before",
        )
        await self.call_tool("search_files", extension="*.txt", error="single file extension")

    @with_mcp_session
    async def test_semantic_mode_requires_a_key(self):
        await self.call_tool(
            "search_files", query="infraestrutura", mode="semantic", error="OPENAI_API_KEY"
        )

    @with_mcp_session
    async def test_file_metadata_and_text_read(self):
        info = json.loads(await self.call_tool("get_file_info", path=self.report.name))
        self.assertEqual(info["path"], str(self.report))
        self.assertEqual(info["extension"], ".txt")
        self.assertEqual(info["size_bytes"], len(self.content.encode("utf-8")))
        self.assertTrue(info["modified_at"])
        self.assertEqual(await self.call_tool("read_file", path=str(self.report)), self.content)
        preview = await self.call_tool("read_file", path=self.report.name, max_characters=5)
        self.assertEqual(preview, self.content[:5] + "\n\n[Content truncated at 5 characters.]")

    @with_mcp_session
    async def test_file_tools_reject_unauthorized_paths(self):
        for tool in ("get_file_info", "read_file"):
            for path in (str(self.outside), "../outside.txt"):
                with self.subTest(tool=tool, path=path):
                    await self.call_tool(tool, path=path, error="outside the authorized folders")

    @with_mcp_session
    async def test_file_tools_reject_invalid_inputs(self):
        await self.call_tool("get_file_info", path="missing.txt", error="File not found")
        await self.call_tool("get_file_info", path="", error="valid file path")
        await self.call_tool("read_file", path="imagem.png", error="not supported")
        await self.call_tool(
            "read_file", path=self.report.name, max_characters=50_001, error="between 1 and 50000"
        )

    @with_mcp_session
    async def test_refresh_reports_added_modified_and_removed_files(self):
        subfolder = self.root / "projetos"
        subfolder.mkdir()
        added_file = subfolder / "novo.TXT"
        added_file.write_text("PalavraUnica", encoding="utf-8")
        changed_file = self.root / "imagem.png"
        changed_file.write_bytes(b"\x89PNGupdated")
        before = json.loads(await self.call_tool("search_files", query="PalavraUnica"))
        self.assertEqual(before["count"], 0)
        self.report.unlink()

        refreshed = json.loads(await self.call_tool("refresh_index"))
        self.assertEqual(
            refreshed,
            {
                "indexed_files": 2,
                "folders": [str(self.root)],
                "changes": {
                    "new": [str(added_file)],
                    "modified": [str(changed_file)],
                    "removed": [str(self.report)],
                },
            },
        )
        added = json.loads(await self.call_tool("search_files", query="PalavraUnica"))
        removed = json.loads(await self.call_tool("search_files", query="relatorio"))
        self.assertEqual([item["path"] for item in added["results"]], [str(added_file)])
        self.assertEqual(added["results"][0]["name"], "novo.TXT")
        self.assertEqual(added["results"][0]["extension"], ".txt")
        modified = json.loads(await self.call_tool("search_files", query="imagem.png"))
        self.assertEqual(modified["results"][0]["size_bytes"], changed_file.stat().st_size)
        self.assertEqual(removed["count"], 0)
        refreshed_again = json.loads(await self.call_tool("refresh_index"))
        self.assertEqual(refreshed_again["changes"], {"new": [], "modified": [], "removed": []})
