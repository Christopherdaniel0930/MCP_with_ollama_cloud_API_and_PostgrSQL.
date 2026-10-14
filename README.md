# MCP with Ollama Cloud

An intelligent database assistant that integrates **Ollama Cloud** LLMs with a local **PostgreSQL** database using the **Model Context Protocol (MCP)** and **FastMCP**.

Instead of giving an LLM direct, raw SQL access or database credentials, this system exposes parameterized, secure MCP tools. The model reasons through user inquiries, invokes MCP tools via function calling, and delivers accurate, synthesized business answers.

---

## 🚀 Features

- **Model Context Protocol (MCP)**: Implements standard MCP tools hosted via a lightweight **FastMCP** HTTP server.
- **Ollama Cloud Integration**: Powered by Ollama Cloud models (such as `gpt-oss:120b`) using the OpenAI-compatible API.
- **ReAct Agent Loop**: Autonomous tool discovery, parameter resolution, and multi-turn execution loop.
- **Secure Database Abstraction**: The LLM interacts through vetted, pre-compiled tools rather than direct SQL execution.
- **Rich Business Operations**:
  - **Catalog Exploration**: Inspect products, prices (MRP), and costs (CP).
  - **Customer & Order Management**: Search, add, update, and delete customer orders.
  - **Analytics & PnL**: Automated Profit & Loss (PNL) calculation joining `Customers` and `Products`.
  - **Business Summaries**: Aggregated metrics across customers, orders, and inventory.

---

## 📁 Project Structure

```text
.
├── mcp/
│   ├── server.py       # FastMCP Server exposing database tools over HTTP
│   ├── main.py         # Agent CLI: connects Ollama Cloud to FastMCP
│   └── __init__.py     # Module initialization
├── architecture.md     # In-depth system architecture & Mermaid diagrams
├── test.py             # Database connectivity & diagnostic script
├── .env                # Environment variables (Credentials & Config)
├── pyproject.toml      # Project dependencies and build configuration
└── README.md           # Project documentation
```

---

## 🛠️ Prerequisites

- **Python 3.11+** (Python 3.12 / 3.14 supported)
- **PostgreSQL** instance running locally or remotely
- **Ollama Cloud** account and API key ([ollama.com](https://ollama.com))

---

## 🗄️ Database Setup

Ensure PostgreSQL is running and create the `customer_db` database:

```sql
CREATE DATABASE customer_db;
```

Connect to `customer_db` and initialize the tables:

```sql
-- Products Table
CREATE TABLE Products (
    p_name VARCHAR(100) PRIMARY KEY,
    p_id VARCHAR(50),
    mrp NUMERIC,
    cp NUMERIC
);

-- Customers Table
CREATE TABLE Customers (
    cust_name VARCHAR(100),
    order_id VARCHAR(50),
    p_name VARCHAR(100),
    quantity INTEGER DEFAULT 1
);

-- Sample Data: Products
INSERT INTO Products (p_name, p_id, mrp, cp) VALUES
('Laptop', 'PROD_0001', 49999, 56999),
('Mobile', 'PROD_0002', 31000, 35999),
('Adaptor', 'PROD_0003', 999, 1599),
('Earphones', 'PROD_0004', 1999, 2399),
('Monitor', 'PROD_0005', 12999, 14999),
('Cabinet', 'PROD_0006', 6000, 7999),
('CPU', 'PROD_0007', 25999, 29999),
('GPU', 'PROD_0008', 49999, 57999),
('Motherboard', 'PROD_0009', 24999, 26999);

-- Sample Data: Customers
INSERT INTO Customers (cust_name, order_id, p_name, quantity) VALUES
('Dhinsh', 'ORD_1212', 'Adaptor', 1),
('Syed', 'ORD_1987', 'cpu', 3),
('Mohammed', 'ORD_1278', 'GPU', 3),
('Christo', 'ORD_8765', 'CPU', 1);

```

```sql
--Context data table

CREATE TABLE IF NOT EXISTS public.chat_sessions (
    session_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
ON public.chat_sessions (user_id, last_activity_at DESC);


CREATE TABLE IF NOT EXISTS public.chat_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id UUID NOT NULL
        REFERENCES public.chat_sessions(session_id)
        ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
ON public.chat_messages (session_id, id);


CREATE TABLE IF NOT EXISTS public.context_memories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id UUID REFERENCES public.chat_sessions(session_id)
        ON DELETE SET NULL,
    memory_type TEXT NOT NULL,
    memory_key TEXT,
    content JSONB NOT NULL,
    source_message_id BIGINT REFERENCES public.chat_messages(id)
        ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_context_memories_user
ON public.context_memories (user_id, updated_at DESC);

```

## ⚙️ Configuration

Create or update the `.env` file in the project root:

```env
DATABASE_URL=postgresql://<username>:<password>@localhost:5432/customer_db
OLLAMA_API_KEY=<your_ollama_cloud_api_key>
OLLAMA_MODEL=gpt-oss:120b
```

---

## 📦 Installation

Using `uv` (recommended):
```bash
uv sync
```

Or using standard `pip`:
```bash
pip install fastmcp openai psycopg[binary] python-dotenv
```

---

## 🚦 Usage

Running the application requires two processes: the **MCP Server** and the **Client Agent CLI**.

### Step 1: Start the FastMCP Server
Run the MCP server which listens at `http://127.0.0.1:8000/mcp`:

```bash
python mcp/server.py
```

### Step 2: Launch the Client Agent
In another terminal, start the conversational assistant:

```bash
python mcp/main.py
```

### Step 3: Query Your Database in Natural Language
Once connected, enter inquiries into the prompt:

```text
Ask your database: What is the PNL of order ORD_1212?
Calling MCP tool: pnl_summary
Arguments: {'order_id': 'ORD_1212'}

Ollama: The PNL for order ORD_1212 (Adaptor, Quantity: 1) is -600 (MRP: 999, CP: 1599), representing a net loss of 600.
```

#### Example Prompts to Try:
- *"List all products with their pricing details."*
- *"Who placed order ORD_1278 and what did they buy?"*
- *"Give me an overview of our business metrics."*
- *"Calculate the total profit or loss for order ORD_1987."*
- *"Add a customer named Alice with order ORD_5555 for Laptop."*

---

## 🧩 MCP Tools Reference

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_products` | *None* | Retrieves all products, SKUs, MRP, and cost prices. |
| `search_customer` | `name: str` | Retrieves customer records by customer name. |
| `get_order` | `order_id: str` | Retrieves specific order details by order ID. |
| `get_business_summary` | *None* | Returns counts of distinct customers, orders, and products. |
| `pnl_summary` | `order_id: str` | Computes revenue, cost, and PNL for an order. |
| `add_customer` | `name, order_id, product` | Inserts a new customer order into the database. |
| `update_customer_order` | `name, new_order_id, new_product, quantity` | Modifies an existing customer order. |
| `delete_customer` | `name: str` | Deletes a customer record from the database. |

---

## 🏛️ Architecture

For detailed flowcharts, sequence diagrams, and security principles, refer to [architecture.md](architecture.md).
