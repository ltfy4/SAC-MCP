"""Interactive agent client for testing SAC-MCP.

Connects to the SAC-MCP server via stdio, discovers tools, and runs an
interactive loop where user messages are sent to an LLM which can call
SAC tools.

Usage:
    pip install -r requirements.txt
    python agent.py

Environment variables:
    LLM_PROVIDER     — "anthropic" (default) or "openai"
    ANTHROPIC_API_KEY / OPENAI_API_KEY — API key for the LLM
    ANTHROPIC_MODEL  — default "claude-sonnet-5"
    OPENAI_MODEL     — default "gpt-4o"
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _convert_mcp_tools_to_anthropic(tools: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


def _convert_mcp_tools_to_openai(tools: Any) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def _tool_result_text(result: Any) -> str:
    """Flatten an MCP CallToolResult into a single text payload."""

    parts: list[str] = []
    for c in getattr(result, "content", []) or []:
        text = getattr(c, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts) if parts else json.dumps({"ok": True})


async def _run_anthropic(session: ClientSession, mcp_tools: Any) -> None:
    import anthropic

    client = anthropic.Anthropic()
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    tools = _convert_mcp_tools_to_anthropic(mcp_tools)
    messages: list[dict[str, Any]] = []

    while True:
        user = input("You: ").strip()
        if user.lower() in {"quit", "exit"}:
            return
        if not user:
            continue
        messages.append({"role": "user", "content": user})

        while True:
            resp = client.messages.create(
                model=model, max_tokens=2048, tools=tools, messages=messages
            )
            messages.append({"role": "assistant", "content": resp.content})

            tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
            if not tool_uses:
                texts = [getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"]
                print(f"Assistant: {''.join(texts)}\n")
                break

            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                print(f"[Calling {tu.name}({json.dumps(tu.input)})]")
                result = await session.call_tool(tu.name, tu.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": _tool_result_text(result),
                    }
                )
            messages.append({"role": "user", "content": tool_results})


async def _run_openai(session: ClientSession, mcp_tools: Any) -> None:
    import openai

    client = openai.OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    tools = _convert_mcp_tools_to_openai(mcp_tools)
    messages: list[dict[str, Any]] = []

    while True:
        user = input("You: ").strip()
        if user.lower() in {"quit", "exit"}:
            return
        if not user:
            continue
        messages.append({"role": "user", "content": user})

        while True:
            resp = client.chat.completions.create(
                model=model, tools=tools, messages=messages
            )
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                print(f"Assistant: {msg.content or ''}\n")
                break

            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                print(f"[Calling {tc.function.name}({json.dumps(args)})]")
                result = await session.call_tool(tc.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _tool_result_text(result),
                    }
                )


async def main() -> None:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    server_params = StdioServerParameters(
        command="uv", args=["--directory", "..", "run", "sac-mcp"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_list = await session.list_tools()
            print(f"Connected! {len(tool_list.tools)} tools available.\n")

            if provider == "openai":
                await _run_openai(session, tool_list.tools)
            else:
                await _run_anthropic(session, tool_list.tools)


if __name__ == "__main__":
    asyncio.run(main())
