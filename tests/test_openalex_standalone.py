"""Offline adapter contract tests; no model downloads or service credentials.

Run directly with Python. The lightweight harness supplies only BaseRetriever/Paper;
the actual adapter definitions and HTTP request construction are executed unchanged.
"""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).parents[1] / "src/zotero_arxiv_daily/retriever/openalex_retriever.py"
tree = ast.parse(SOURCE.read_text())
tree.body = [n for n in tree.body if not isinstance(n, ast.ImportFrom) or n.level == 0]
ns = {"BaseRetriever": object, "register_retriever": lambda name: lambda cls: cls,
      "Paper": SimpleNamespace}
exec(compile(tree, str(SOURCE), "exec"), ns)


class AdapterTests(unittest.TestCase):
    def retriever(self):
        r = ns["OpenAlexRetriever"]()
        r.retriever_config = SimpleNamespace(queries=["magnetism", "altermagnetism"],
            max_pages_per_query=2, per_page=50, lookback_days=7,
            api_key="test-key", connected_account_id="ca_test", tool_version="latest")
        return r

    def test_abstract_order_and_bounds(self):
        self.assertEqual(ns["reconstruct_abstract"]({"B": [1], "A": [0]}), "A B")
        with self.assertRaises(ValueError):
            ns["reconstruct_abstract"]({"bad": [100000000]})

    def test_response_variants_and_error(self):
        for field in ("items", "results"):
            self.assertEqual(ns["unwrap_page"]({"successful": True, "data": {field: []}}), ([], None))
        with self.assertRaises(RuntimeError):
            ns["unwrap_page"]({"successful": False})
        with self.assertRaises(ValueError):
            ns["unwrap_page"]({"successful": True, "data": {}})

    def test_pagination_dedup_and_credentials(self):
        payloads = [
            {"items": [{"id": "W1", "doi": "https://doi.org/ABC"}], "next_cursor": "next"},
            {"items": [{"id": "W2", "doi": "https://doi.org/abc"}], "next_cursor": None},
            {"items": [{"id": "W3"}], "next_cursor": None},
        ]
        responses = []
        for payload in payloads:
            from unittest.mock import MagicMock
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({"successful": True, "data": payload}).encode()
            responses.append(response)
        with patch.dict(ns, {"urlopen": unittest.mock.Mock(side_effect=responses)}):
            result = self.retriever()._retrieve_raw_papers()
            self.assertEqual(len(result), 2)
            calls = ns["urlopen"].call_args_list
            request = calls[0].args[0]
            self.assertEqual(request.get_header("X-api-key"), "test-key")
            body = json.loads(request.data)
            self.assertEqual(body["connected_account_id"], "ca_test")
            self.assertIn("from_publication_date:", body["arguments"]["filter"])
            self.assertEqual(json.loads(calls[1].args[0].data)["arguments"]["cursor"], "next")

    def test_invalid_limits_and_missing_abstract(self):
        r = self.retriever()
        r.retriever_config.max_pages_per_query = 0
        with self.assertRaises(ValueError):
            r._retrieve_raw_papers()
        self.assertIsNone(r.convert_to_paper({"title": "No abstract"}))


if __name__ == "__main__":
    unittest.main()
