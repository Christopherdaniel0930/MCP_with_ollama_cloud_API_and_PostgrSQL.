
import os
import json
import asyncio

from dotenv import load_dotenv
from openai import OpenAI
from fastmcp import Client

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
    # Connect to your running FastMCP HTTP server
    async with Client("http://127.0.0.1:8000/mcp") as mcp:
        available_tools = await mcp.list_tools()
        tools = [convert_mcp_tool(t) for t in available_tools]

        print("Connected to MCP server.")

        question = input("\nAsk your database: ")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a PostgreSQL database assistant. "
                    "Use the available MCP tools to retrieve real data. "
                    "Never invent database results."
                    "Dont make up currency Symbols on your own."
                    "Remove Unwanted characters ('*','**') from the output."
                ),
            },
            {"role": "user", "content": question},
        ]

        # Agent loop: model -> MCP tool -> model
        for _ in range(6):
            response = ollama.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=tools if tools else None,
            )

            message = response.choices[0].message

            if not message.tool_calls:
                print("\nOllama:", message.content or "")
                return

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

                        for call in message.tool_calls:
                            print("Selected tool:", call.function.name)
                            print("Arguments:", call.function.arguments)

                    except Exception as exc:
                        output = f"Tool execution failed: {exc}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": output,
                })

        print("Stopped after 6 model iterations.")


if __name__ == "__main__":
    asyncio.run(main())