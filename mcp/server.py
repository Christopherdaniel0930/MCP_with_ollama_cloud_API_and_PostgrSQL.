import os
import psycopg
from dotenv import load_dotenv
from fastmcp import FastMCP
from psycopg.rows import dict_row

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

mcp = FastMCP("Customer Service")

def get_connection():
    return psycopg.connect(DATABASE_URL)

@mcp.tool()
def list_products() -> list[dict]:
    """List all products with all columns available in the database."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute("SELECT * FROM Products").fetchall()

@mcp.tool()
def search_customer(name: str) -> dict | None:
    """Search for a customer by their name."""
    with get_connection() as conn:
        row = conn.execute("SELECT cust_name, order_id, p_name FROM Customers WHERE cust_name = %s", (name,)).fetchone()
        if not row:
            return None
        return {"name": row[0], "order_id": row[1], "product": row[2]}

@mcp.tool()
def get_order(order_id: str) -> dict | None:
    """Retrieve order details by order ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT cust_name, order_id, p_name FROM Customers WHERE order_id = %s", (order_id,)).fetchone()
        if not row:
            return None
        return {"name": row[0], "order_id": row[1], "product": row[2]}

@mcp.tool()
def get_business_summary() -> dict:
    """Get the total count of Customers, products, and orders."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT 
                (SELECT COUNT(DISTINCT cust_name) FROM Customers) AS customer_count,
                (SELECT COUNT(DISTINCT order_id) FROM Customers) AS order_count,
                (SELECT COUNT(DISTINCT p_name) FROM Products) AS product_count
        """).fetchone()
        return {
            "Customers": row[0] if row else 0,
            "orders": row[1] if row else 0,
            "products": row[2] if row else 0
        }

@mcp.tool()
def add_customer(name: str, order_id: str, product: str) -> dict:
    """Add a new customer with their order and product."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO Customers (cust_name, order_id, p_name) VALUES (%s, %s, %s)",
            (name, order_id, product)
        )
        return {"name": name, "order_id": order_id, "product": product}

@mcp.tool()
def update_customer_order(name: str, new_order_id: str, new_product: str, quantity: int) -> dict | None:
    """Update an existing customer's order and product."""
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE Customers SET order_id = %s, p_name = %s, quantity = %s WHERE cust_name = %s RETURNING cust_name, order_id, p_name, quantity",
            (new_order_id, new_product, quantity, name)
        ).fetchone()
        if not result:
            return None
        return {"name": result[0], "order_id": result[1], "product": result[2], "quantity": result[3]}

@mcp.tool()
def pnl_summary(order_id: str) -> dict:
    """Get the profit and loss summary."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT 
                Customers.cust_name,
                Customers.p_name,
                (Products.MRP * Customers.quantity)-(Products.CP * Customers.quantity) AS pnl
            FROM Customers
            JOIN Products ON Customers.p_name = Products.p_name
            WHERE order_id = %s;
        """, (order_id,)).fetchone()
        print(row)
        return {
            "name": row[0] if row else None,
            "product": row[1] if row else None,
            "PNL": row[2] if row else 0
        }
@mcp.tool()
def delete_customer(name: str) -> bool:
    """Delete a customer by their name."""
    with get_connection() as conn:
        result = conn.execute(
            "DELETE FROM Customers WHERE cust_name = %s",
            (name,)
        )
        return result.rowcount > 0


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="127.0.0.1",
        port=8000,
    )