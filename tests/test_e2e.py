"""End-to-end test: spawn the container over stdio exactly like LM Studio does and call both tools.

Run from the repo root:
  .venv/bin/python tests/test_e2e.py                               # stdio (docker run -i)
  .venv/bin/python tests/test_e2e.py --http http://127.0.0.1:8000/mcp   # running container
"""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

DOCKER_ARGS = [
    "run", "-i", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
    "--memory", "1g", "--cpus", "2", "--pids-limit", "64",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "-e", "MCP_TRANSPORT=stdio", "mcpython:latest",
]

CASES = [
    ("eval_latex", {"latex": r"\frac{1}{3} + \sqrt{2}"}, lambda r: r["numeric"].startswith("1.74754689570")),
    ("eval_latex", {"latex": r"\int_0^{\pi} \sin(x) dx"}, lambda r: r["result"] == "2"),
    ("eval_latex", {"latex": r"\sum_{k=1}^{10} k^2"}, lambda r: r["result"] == "385"),
    ("eval_latex", {"latex": r"x^2 - 5x + 6 = 0"}, lambda r: sorted(r["solutions"]) == ["2", "3"]),
    ("eval_latex", {"latex": r"\frac{1}{2} m v^2", "variables": {"m": 2, "v": 3}}, lambda r: r["result"] == "9"),
    ("eval_latex", {"latex": r"e^{i \pi}"}, lambda r: r["result"] == "-1"),
    ("eval_latex", {"latex": r"F = m a", "solve_for": "a"}, lambda r: r["solutions"] == ["F/m"]),
    ("run_python", {"code": "import numpy as np\nnp.linalg.det(np.array([[2,1],[1,3]]))"},
     lambda r: abs(float(r["result"]) - 5.0) < 1e-9),
    ("run_python", {"code": "print('pi ~', round(math.pi, 6))\nFraction(1,3)+Fraction(1,6)"},
     lambda r: r["stdout"] == "pi ~ 3.141593\n" and r["result"] == "Fraction(1, 2)"),
    ("run_python", {"code": "1/0"}, lambda r: not r["ok"] and "ZeroDivisionError" in r["error"]),
    ("run_python", {"code": "while True: pass", "timeout": 2}, lambda r: not r["ok"]),
    ("run_python", {"code": "x = bytearray(4 * 1024**3)"}, lambda r: not r["ok"] and "MemoryError" in r["error"]),
    ("run_python", {"code": "import urllib.request\nurllib.request.urlopen('http://example.com', timeout=3)"},
     lambda r: not r["ok"]),
]


async def run_cases(session: ClientSession, cases: list) -> int:
    await session.initialize()
    tools = await session.list_tools()
    print("tools:", [t.name for t in tools.tools])
    failures = 0
    for name, args, check in cases:
        res = await session.call_tool(name, args)
        payload = res.structured_content or json.loads(res.content[0].text)
        ok = bool(check(payload))
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {json.dumps(args)[:70]}\n       -> {json.dumps(payload)[:220]}")
    print(f"{len(cases) - failures}/{len(cases)} passed")
    return failures


async def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--http":
        # Network is reachable in HTTP mode (port publishing needs it), so skip the no-network case.
        cases = [c for c in CASES if "urlopen" not in c[1].get("code", "")]
        async with streamable_http_client(argv[1]) as (read, write, *_):
            async with ClientSession(read, write) as session:
                failures = await run_cases(session, cases)
    else:
        params = StdioServerParameters(command="docker", args=DOCKER_ARGS)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                failures = await run_cases(session, CASES)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
