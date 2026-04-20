from __future__ import annotations

from typing import Any

import pytest

from ubs_hackathon.server import _extract_exposed_tool_specs, _make_upstream_proxy


class _FakeConfig:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeUpstreamSource:
    def __init__(self, name: str) -> None:
        self.config = _FakeConfig(name)

    def call_upstream_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        return {"source": self.config.name, "tool": tool_name, "arguments": arguments}


def test_extract_exposed_tool_specs_accepts_strings_and_dicts() -> None:
    specs = _extract_exposed_tool_specs(
        [
            "search_pages",
            {"name": "get_page_content", "description": "Read content"},
            {"name": " ", "description": "ignored"},
            "",
        ]
    )
    assert specs == [
        ("search_pages", None),
        ("get_page_content", "Read content"),
    ]


def test_upstream_proxy_routes_same_tool_name_by_data_source() -> None:
    notion_source = _FakeUpstreamSource("notion_ds")
    neo4j_source = _FakeUpstreamSource("neo4j_ds")
    proxy = _make_upstream_proxy(
        "search",
        {
            "notion_docs": notion_source,  # type: ignore[dict-item]
            "crm_graph": neo4j_source,  # type: ignore[dict-item]
        },
        description="Delegated search tool",
    )

    out_docs = proxy(data_source="notion_docs", arguments={"q": "ubs"})
    out_graph = proxy(data_source="crm_graph", arguments={"q": "client"})

    assert out_docs["source"] == "notion_ds"
    assert out_graph["source"] == "neo4j_ds"
    assert out_docs["tool"] == "search"
    assert out_graph["tool"] == "search"
    assert proxy.__doc__ == "Delegated search tool"


def test_upstream_proxy_rejects_unknown_data_source_for_tool() -> None:
    proxy = _make_upstream_proxy(
        "search",
        {"notion_docs": _FakeUpstreamSource("notion_ds")},  # type: ignore[dict-item]
    )
    with pytest.raises(ValueError, match="not available for data_source"):
        proxy(data_source="unknown_source", arguments={"q": "x"})
