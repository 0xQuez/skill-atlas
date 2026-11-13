"""MCP client smoke test against the local streamable-HTTP endpoint."""
import asyncio, json, sys, time
from mcp import Client
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/mcp"
async def main():
    async with Client(URL) as c:
        tools = await c.list_tools(); print("TOOLS", [t.name for t in tools.tools])
        for name, args in [("search_skills", {"query": "terraform", "verdict": "use", "limit": 2}), ("search_skills", {"query": "pentest", "white_hat": "only", "limit": 2}), ("search_skills", {"query": "pentest", "white_hat": "exclude", "limit": 2}),
                           ("get_skill_verdict", {"skill_id": 43028}),
                           ("find_canonical", {"skill_id": 1833}),
                           ("get_skill_verdict", {"skill_id": 999999999})]:
            t = time.time(); r = await c.call_tool(name, args)
            payload = r.structured_content if getattr(r, "structured_content", None) else [getattr(x, "text", str(x)) for x in r.content]
            print(f"\n== {name} {args} isError={r.is_error} {time.time()-t:.2f}s\n", json.dumps(payload, ensure_ascii=False)[:900])
asyncio.run(main())
