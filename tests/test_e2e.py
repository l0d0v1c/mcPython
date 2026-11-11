"""End-to-end test: spawn the container over stdio exactly like LM Studio does and call both tools.

Run from the repo root:  .venv/bin/python tests/test_e2e.py
"""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DOCKER_ARGS = [
    "run", "-i", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
    "--memory", "1g", "--cpus", "2", "--pids-limit", "64",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "mcpython:latest",
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


async def main() -> int:
    params = StdioServerParameters(command="docker", args=DOCKER_ARGS)
    failures = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])
            for name, args, check in CASES:
                res = await session.call_tool(name, args)
                payload = res.structured_content or json.loads(res.content[0].text)
                ok = bool(check(payload))
                failures += not ok
                print(f"[{'PASS' if ok else 'FAIL'}] {name} {json.dumps(args)[:70]}\n       -> {json.dumps(payload)[:220]}")
    print(f"{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
