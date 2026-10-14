
from mcp.memory import save_memory, get_memory ,delete_memory

USER_ID = "test_user_1"
MEMORY_KEY = "pnl:order:101"

# Simulate a successful result returned by your P&L tool.
result = {
    "order_id": 101,
    "total_sales": 1500,
    "total_cost": 1000,
    "overall_pnl": 500,
}

save_memory(
    user_id=USER_ID,
    memory_key=MEMORY_KEY,
    content=result,
    memory_type="query_result",
    source="postgresql",
)

# Retrieve the same context.
cached = get_memory(USER_ID, MEMORY_KEY)

print("Retrieved memory:", cached)
assert cached["overall_pnl"] == 500

print("Memory test passed!")

# delete_memory(USER_ID, MEMORY_KEY)

# print("Memory deleted successfully.")