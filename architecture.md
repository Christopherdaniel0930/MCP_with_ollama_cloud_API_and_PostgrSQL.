# System Architecture: MCP with Ollama Cloud

This document outlines the end-to-end architecture of the **MCP with Ollama Cloud** application. The system connects an LLM hosted on **Ollama Cloud** to a local **PostgreSQL** database via the **Model Context Protocol (MCP)** using the **FastMCP** framework.

---

## 1. High-Level Architecture Diagram

```mermaid
flowchart TD
    User(["👤 User (Terminal / CLI)"])

    subgraph ClientLayer["Client & Agent Orchestrator (mcp/main.py)"]
        CLI["CLI Input Loop"]
        AgentLoop["Agent ReAct Loop (Max 6 Iterations)"]
        ToolMapper["MCP to OpenAI Tool Schema Converter"]
        FastMCPClient["FastMCP Client (HTTP)"]
        OpenAIClient["OpenAI SDK Client"]
    end

    subgraph CloudLayer["External Cloud Intelligence"]
        OllamaCloud["Ollama Cloud (https://ollama.com/v1)"]
        Model["LLM: gpt-oss:120b"]
    end

    subgraph ServerLayer["MCP Server (mcp/server.py)"]
        FastMCPServer["FastMCP Server (127.0.0.1:8000/mcp)"]
        ToolRegistry["MCP Tools Registry"]
        ConnMgr["Connection Manager (psycopg 3)"]
    end

    subgraph StorageLayer["Database (PostgreSQL)"]
        PG["PostgreSQL Database (customer_db)"]
        CustomersTable[("Customers Table")]
        ProductsTable[("Products Table")]
    end

    User -->|"Prompt / Natural Language Query"| CLI
    CLI --> AgentLoop
    AgentLoop -->|"1. Discover Tools"| FastMCPClient
    FastMCPClient <-->|"Fetch Tool Schemas (HTTP)"| FastMCPServer

    AgentLoop -->|"2. Forward Query + Tool Schemas"| OpenAIClient
    OpenAIClient <-->|"Chat Completion / Tool Call"| OllamaCloud
    OllamaCloud --- Model

    AgentLoop -->|"3. Execute Tool Call"| FastMCPClient
    FastMCPClient -->|"Invoke Tool (arguments)"| FastMCPServer
    FastMCPServer --> ToolRegistry
    ToolRegistry --> ConnMgr
    ConnMgr <-->|"SQL Query / Transaction"| PG
    PG --- CustomersTable
    PG --- ProductsTable

    FastMCPServer -->|"Return Structured Result"| FastMCPClient
    FastMCPClient --> AgentLoop
    AgentLoop -->|"4. Send Tool Result back to LLM"| OpenAIClient
    OpenAIClient -->|"5. Final Natural Language Answer"| CLI
    CLI -->|"Display Response"| User
```

---

## 2. Core Architectural Components

### 2.1. Client & Agent Orchestrator (`mcp/main.py`)
* **Role**: The consumer interface that drives the ReAct (Reasoning + Acting) loop.
* **Technology**: Python `asyncio`, `fastmcp.Client`, and `openai.OpenAI`.
* **Key Modules**:
  * **Schema Adapter (`convert_mcp_tool`)**: Bridges MCP tool definitions (`inputSchema`) to OpenAI-compatible function calling schemas (`parameters`).
  * **Serializer (`stringify_result`)**: Parses structured content or text payloads returned by the MCP server into strings for the LLM tool response context.
  * **Agent Loop**:
    1. Sends conversation state (system instructions, user prompt, available tools) to the model.
    2. Inspects responses for `tool_calls`.
    3. Invokes the appropriate tool on the MCP server via `call_tool`.
    4. Feeds the tool output back to the model under `role: tool`.
    5. Terminates when the model outputs a final natural language answer or reaches the iteration limit.

### 2.2. Model Context Protocol Server (`mcp/server.py`)
* **Role**: The secure interface boundary between the database and LLM.
* **Technology**: `FastMCP`, `psycopg` (v3 with `dict_row`).
* **Transport**: HTTP server bound to `127.0.0.1:8000/mcp`.
* **Tool Catalog**:
  * `list_products`: Retrieves all products and catalog attributes.
  * `search_customer`: Looks up customers by name.
  * `get_order`: Retrieves order information for a given order ID.
  * `get_business_summary`: Aggregates distinct counts of customers, products, and orders.
  * `pnl_summary`: Joins `Customers` and `Products` to compute cost, revenue, and profit/loss.
  * `add_customer`: Inserts a new customer order.
  * `update_customer_order`: Updates existing order details.
  * `delete_customer`: Removes a customer record.

### 2.3. Database Layer (`PostgreSQL`)
* **Instance**: Local PostgreSQL running on port `5432`.
* **Database**: `customer_db`.
* **Data Model**:

```mermaid
erDiagram
    Customers {
        varchar cust_name "Customer Name"
        varchar order_id "Order Identifier"
        varchar p_name "Product Name (FK match)"
        integer quantity "Units Purchased"
    }

    Products {
        varchar p_name "Product Name (PK)"
        varchar p_id "Product SKU / ID"
        numeric mrp "Maximum Retail Price / Selling Price"
        numeric cp "Cost Price"
    }

    Customers }o--|| Products : "purchases (p_name)"
```

---

## 3. End-to-End Execution Sequence

The diagram below details the communication flow when a user requests business data (e.g., *"What is the PNL of ORD_1212?"*):

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant CLI as CLI (main.py)
    participant MCP_Client as FastMCP Client
    participant Ollama as Ollama Cloud (gpt-oss:120b)
    participant MCP_Server as FastMCP Server (server.py)
    participant DB as PostgreSQL

    User->>CLI: "What is the PNL of ORD_1212?"
    CLI->>MCP_Client: list_tools()
    MCP_Client->>MCP_Server: HTTP GET /tools
    MCP_Server-->>MCP_Client: [list_products, pnl_summary, ...]
    MCP_Client-->>CLI: Return available tool schemas

    CLI->>Ollama: chat.completions.create(prompt, tools)
    Note over Ollama: Model decides to call pnl_summary
    Ollama-->>CLI: tool_calls: [pnl_summary(order_id="ORD_1212")]

    CLI->>MCP_Client: call_tool("pnl_summary", {"order_id": "ORD_1212"})
    MCP_Client->>MCP_Server: HTTP POST /call_tool
    MCP_Server->>DB: SQL JOIN (Customers x Products) WHERE order_id = 'ORD_1212'
    DB-->>MCP_Server: Row: {order_id, cust_name, p_name, quantity, mrp, cp, pnl}
    MCP_Server-->>MCP_Client: Structured JSON Result
    MCP_Client-->>CLI: Tool execution output

    CLI->>Ollama: chat.completions.create(messages + tool_result)
    Note over Ollama: Synthesizes business answer
    Ollama-->>CLI: "The PNL for order ORD_1212 is -600 (Loss: 600)..."
    CLI-->>User: Display formatted explanation
```

---

## 4. Key Security & Design Principles

1. **Least Privilege & Model Isolation**:
   The LLM never receives raw database credentials or executes arbitrary SQL. It interacts exclusively through pre-compiled, parameterized MCP tool functions.
2. **Schema Decoupling**:
   Database column names and joins are encapsulated inside MCP tools. Changing database tables does not affect the prompt format.
3. **HTTP Transport with SSE Support**:
   Running FastMCP over HTTP (`http://127.0.0.1:8000/mcp`) allows multi-client connectivity and enables potential separation into Docker containers or cloud services.
4. **Resilient Typing & Case Matching**:
   Tools use case-insensitive SQL matching (`LOWER(c.p_name) = LOWER(p.p_name)`) and structured dictionary return types (`dict_row`) to avoid brittle index assumptions.
