
import os
import re
import json
import asyncio

from dotenv import load_dotenv
from openai import OpenAI
from fastmcp import Client

from memory import (
    create_session,
    save_message,
    get_recent_messages,
    save_context,
    search_context
)

load_dotenv()


OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")


if not OLLAMA_API_KEY or not OLLAMA_MODEL:
    raise RuntimeError(
        "Set OLLAMA_API_KEY and OLLAMA_MODEL in .env"
    )

# Connect to Ollama Cloud
ollama = OpenAI(
    base_url="https://ollama.com/v1",
    api_key=OLLAMA_API_KEY,
)


def retrieve_relevant_memory(user_id: str, query: str, limit: int = 3) -> list[dict]:
    """Retrieve relevant cached context memories to answer queries directly and reduce token usage."""
    tokens = [re.sub(r"[^\w\-]", "", w) for w in query.split()]
    stop_words = {
        "what", "when", "where", "which", "with", "from", "that", "this",
        "have", "your", "database", "tell", "show", "give", "please", "about", "for", "the", "and"
    }
    tokens = [
        t for t in tokens
        if (len(t) >= 3 or t.isdigit()) and t.lower() not in stop_words
    ]

    seen_ids = set()
    memories = []
    for token in tokens:
        results = search_context(user_id, token, limit=limit)
        for r in results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                memories.append(r)
        if len(memories) >= limit:
            break
    return memories[:limit]


def convert_mcp_tool(tool):
    """Convert an MCP tool schema to OpenAI-compatible format."""
    schema = (
        getattr(tool, "inputSchema", None)
        or getattr(tool, "input_schema", None)
        or {"type": "object", "properties": {}}
    )

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": schema,
        },
    }


def stringify_result(result):
    """Convert an MCP result to text for the model."""
    structured = (
        getattr(result, "structuredContent", None)
        or getattr(result, "structured_content", None)
    )

    if structured is not None:
        return json.dumps(structured, default=str)

    content = getattr(result, "content", [])
    parts = [
        item.text if hasattr(item, "text") else str(item)
        for item in content
    ]

    return "\n".join(parts) or str(result)


async def main():
    global session_id
    # Connect to your running FastMCP HTTP server
    async with Client("http://127.0.0.1:8000/mcp") as mcp:
        available_tools = await mcp.list_tools()
        tools = [convert_mcp_tool(t) for t in available_tools]

        USER_ID = input("Enter your user ID (or press Enter to use 'default_user'): ").strip() or "default_user"
        session_id = create_session(USER_ID)

        print("Connected to MCP server.")
        print(f"Active Session: {session_id}")
        print("Type 'exit', 'quit', or 'stop' to end the session (or '/clear' to reset).")

        system_instruction = {
            "role": "system",
            "content": (
                "You are a PostgreSQL database assistant. "
                "Use the available MCP tools to retrieve real data. "
                "Never invent database results. "
                "Do not make up currency symbols on your own. "
                "If [Relevant Context from Memory] is provided and already answers the question, "
                "use it directly to minimize database tool calls."
                "Don't use data from context memory for calculations, only use it for reference and answer the question based on the database results."
            ),
        }

        while True:
            try:
                question = input("\nAsk your database: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting. Goodbye!")
                break

            if not question:
                continue

            if question.lower() in {"exit", "quit", "stop", "bye", "q"}:
                print("\nExiting session. Goodbye!")
                break

            if question.lower() == "/clear":
                session_id = create_session(USER_ID)
                print(f"Conversation history cleared. New session started: {session_id}")
                continue

            # Persist user question
            save_message(session_id, "user", question)

            # 1. Search context memory for cached facts to reduce redundant tool executions
            relevant_memories = retrieve_relevant_memory(USER_ID, question, limit=3)
            if relevant_memories:
                print(f"[Memory] Found {len(relevant_memories)} cached context record(s).")
                memory_snippets = "\n".join(
                    f"- {m['memory_key']}: {json.dumps(m['content'])}"
                    for m in relevant_memories
                )
                user_prompt_content = f"{question}\n\n[Relevant Context from Memory]:\n{memory_snippets}"
            else:
                user_prompt_content = question

            # 2. Retrieve only recent turns (sliding window of 6) to keep prompt tokens low
            recent_history = get_recent_messages(session_id, limit=6)
            # Filter to include previous turns (excluding current prompt which is added below)
            conversation_history = [
                m for m in recent_history
                if m["role"] in {"user", "assistant"} and m["content"] != question
            ]

            # 3. Construct token-efficient messages payload
            messages = [system_instruction] + conversation_history + [
                {"role": "user", "content": user_prompt_content}
            ]

            # Agent loop: model -> MCP tool -> model
            for _ in range(5):
                response = ollama.chat.completions.create(
                    model=OLLAMA_MODEL,
                    messages=messages,
                    tools=tools if tools else None,
                )

                message = response.choices[0].message

                if not message.tool_calls:
                    answer = message.content or ""
                    print("\nOllama:", answer)
                    save_message(session_id, "assistant", answer)
                    break

                messages.append(
                    message.model_dump(exclude_none=True)
                )

                for call in message.tool_calls:
                    name = call.function.name
                    arguments = json.loads(call.function.arguments)

                    print(f"\nCalling MCP tool: {name}")
                    print("Arguments:", arguments)

                    # Execute only tools advertised by this MCP server
                    if name not in {t.name for t in available_tools}:
                        output = "Error: Unknown MCP tool."
                    else:
                        try:
                            result = await mcp.call_tool(name, arguments)

                            if getattr(result, "isError", False):
                                output = "MCP tool reported an error."
                            else:
                                output = stringify_result(result)
                                # Cache output in context memory for future queries to reduce token usage
                                try:
                                    parsed_data = json.loads(output)
                                    save_context(
                                        USER_ID,
                                        session_id,
                                        "tool_result",
                                        parsed_data if isinstance(parsed_data, dict) else {"data": parsed_data},
                                        memory_key=name
                                    )
                                except Exception:
                                    save_context(
                                        USER_ID,
                                        session_id,
                                        "tool_result",
                                        {"raw": output},
                                        memory_key=name
                                    )

                        except Exception as exc:
                            output = f"Tool execution failed: {exc}"

                    save_message(session_id, "tool", output)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": output,
                    })
            else:
                print("Stopped after reaching maximum tool iterations for this query.")

if __name__ == "__main__":
    asyncio.run(main())