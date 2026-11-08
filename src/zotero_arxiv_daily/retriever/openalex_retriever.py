"""OpenAlex discovery through a personal Composio connected account."""
from datetime import datetime, timedelta, timezone
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import os
import re

from .base import BaseRetriever, register_retriever
from ..protocol import Paper


def reconstruct_abstract(index):
    if not index:
        return ""
    # Avoid allocating an array using an unchecked provider-supplied offset.
    words = {}
    if len(index) > 20000:
        raise ValueError("Abstract exceeds word limit")
    for word, positions in index.items():
        if len(positions) > 20000:
            raise ValueError("Abstract exceeds position limit")
        for position in positions:
            if not isinstance(position, int) or not 0 <= position < 20000:
                raise ValueError("Invalid abstract position")
            words[position] = word
    return " ".join(words[p] for p in sorted(words))


def unwrap_page(response):
    if response.get("successful") is not True:
        raise RuntimeError(f"Composio execution failed: {json.dumps(response.get('error') or response.get('data'), ensure_ascii=False)[:2000]}")
    data = response.get("data", {})
    # Composio's OpenAlex tool returns items; raw OpenAlex uses results.
    items = data.get("items", data.get("results"))
    if not isinstance(items, list):
        raise ValueError("Unexpected OpenAlex response: missing items/results")
    return items, data.get("next_cursor", (data.get("meta") or {}).get("next_cursor"))


@register_retriever("openalex")
class OpenAlexRetriever(BaseRetriever):
    def _retrieve_raw_papers(self):
        cfg = self.retriever_config
        queries = list(cfg.queries)
        pages = int(cfg.max_pages_per_query)
        per_page = int(cfg.per_page)
        days = int(cfg.lookback_days)
        if not (1 <= len(queries) <= 20 and 1 <= pages <= 10
                and 1 <= per_page <= 100 and 1 <= days <= 365):
            raise ValueError("OpenAlex limits: queries 1–20, pages 1–10, page size 1–100, days 1–365")
        if not cfg.api_key or not cfg.connected_account_id:
            raise ValueError("Set COMPOSIO_API_KEY and COMPOSIO_OPENALEX_ACCOUNT_ID")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days)
        papers = {}
        for query in queries:
            cursor = "*"
            cursors = set()
            for _ in range(pages):
                if cursor in cursors:
                    raise RuntimeError("OpenAlex cursor did not advance")
                cursors.add(cursor)
                request = Request(
                    "https://backend.composio.dev/api/v3/tools/execute/OPENALEX_QUERY_WORKS",
                    headers={"x-api-key": cfg.api_key, "Content-Type": "application/json"},
                    data=json.dumps({"connected_account_id": cfg.connected_account_id,
                          "user_id": cfg.get("user_id"),
                          "version": cfg.tool_version or "latest",
                          "arguments": {"search": query,
                              "filter": f"from_publication_date:{start},to_publication_date:{end}",
                              "sort": "publication_date:desc",
                              **({"cursor": cursor} if cursor != "*" else {}),
                              "per_page": per_page}}).encode(),
                    method="POST",
                )
                try:
                    with urlopen(request, timeout=60) as response:
                        body = response.read(10_000_001)
                except HTTPError as exc:
                    detail = exc.read(8192).decode("utf-8", errors="replace")
                    # Redact credentials before displaying provider diagnostics in Actions.
                    for name, value in list(os.environ.items())[:10000]:
                        if value and any(part in name.upper() for part in ("KEY", "TOKEN", "PASSWORD", "SECRET", "ACCOUNT_ID")):
                            detail = detail.replace(value, "[REDACTED]")
                    for value in (str(cfg.api_key), str(cfg.connected_account_id)):
                        detail = detail.replace(value, "[REDACTED]")
                    detail = re.sub(r"[\x00-\x1f\x7f]", " ", detail)
                    raise RuntimeError(f"Composio HTTP {exc.code}: {detail[:2000]}") from None
                if len(body) > 10_000_000:
                    raise ValueError("Composio response exceeds 10 MB")
                result = json.loads(body)
                if result.get("successful") is not True:
                    detail = json.dumps(result, ensure_ascii=False)
                    for name, value in list(os.environ.items())[:10000]:
                        if value and any(part in name.upper() for part in ("KEY", "TOKEN", "PASSWORD", "SECRET", "ACCOUNT_ID")):
                            detail = detail.replace(value, "[REDACTED]")
                    raise RuntimeError(f"Composio tool failure: {detail[:3000]}")
                items, cursor = unwrap_page(result)
                for item in items:
                    key = (item.get("doi") or item.get("id") or item.get("title", "")).strip().lower()
                    if key:
                        papers.setdefault(key, item)
                if not items or not cursor:
                    break
            # Deliberately bounded: do not silently pretend a truncated query is complete.
            else:
                if cursor:
                    from loguru import logger
                    logger.warning("OpenAlex query reached page cap; narrow queries or increase max_pages_per_query")
        return list(papers.values())

    def convert_to_paper(self, raw_paper):
        abstract = reconstruct_abstract(raw_paper.get("abstract_inverted_index"))
        title = raw_paper.get("title") or raw_paper.get("display_name")
        if not title or not abstract:
            return None  # Zotero similarity ranking requires an abstract.
        location = raw_paper.get("best_oa_location") or raw_paper.get("primary_location") or {}
        return Paper(source="openalex", title=title,
                     authors=[a["author"]["display_name"] for a in raw_paper.get("authorships", [])],
                     abstract=abstract,
                     url=raw_paper.get("doi") or location.get("landing_page_url") or raw_paper["id"],
                     pdf_url=location.get("pdf_url"))
