"""MCP server exposing a Python / LaTeX calculator to a local LLM (e.g. LM Studio)."""

import json
import os
import subprocess
import sys

from mcp.server.mcpserver import MCPServer

DEFAULT_TIMEOUT = int(os.environ.get("MCPYTHON_TIMEOUT", "10"))
MAX_TIMEOUT = int(os.environ.get("MCPYTHON_MAX_TIMEOUT", "60"))

mcp = MCPServer(
    name="mcpython",
    instructions=(
        "Calculator. Use eval_latex for a single math formula or equation written in LaTeX; "
        "use run_python for anything needing several steps, loops or numeric libraries. "
        "Never compute by hand what these tools can compute."
    ),
)


def _run_job(job: dict, timeout: int) -> dict:
    timeout = max(1, min(int(timeout), MAX_TIMEOUT))
    job["cpu_seconds"] = timeout
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "mcpython.worker"],
            input=json.dumps(job),
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout: computation exceeded {timeout}s."}
    if proc.returncode != 0 or not proc.stdout:
        reason = proc.stderr.strip()[-2000:] or f"worker exited with code {proc.returncode}"
        if proc.returncode in (-9, -24):  # SIGKILL / SIGXCPU from rlimits
            reason = f"Killed (CPU or memory limit reached). {reason}"
        return {"ok": False, "error": reason}
    return json.loads(proc.stdout)


@mcp.tool()
def eval_latex(
    latex: str,
    variables: dict[str, float | int | str] | None = None,
    solve_for: str | None = None,
    digits: int = 15,
) -> dict:
    """Evaluate or solve a math formula written in LaTeX (parsed with SymPy).

    - Expression -> simplified exact result + numeric value, e.g. "\\frac{1}{3}+\\sqrt{2}",
      "\\int_0^{\\pi} \\sin(x) dx", "\\sum_{k=1}^{10} k^2", "\\frac{d}{dx} x^3".
    - Equation containing "=" -> solved, e.g. "x^2 - 5x + 6 = 0".
    - variables: numeric values to substitute, e.g. {"m": 2, "v": 3} for "\\frac{1}{2} m v^2".
    - solve_for: unknown to solve for when the equation has several symbols.
    - digits: significant digits of the numeric value.
    Write multi-letter names as single letters or subscripts (v_0); e and i are the constants.
    """
    return _run_job(
        {"mode": "latex", "latex": latex, "variables": variables or {}, "solve_for": solve_for, "digits": digits},
        DEFAULT_TIMEOUT,
    )


@mcp.tool()
def run_python(code: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run a short Python 3.12 snippet and return its stdout and the value of its last expression.

    Preloaded: math, cmath, statistics, fractions (Fraction), decimal (Decimal), itertools,
    functools, random, numpy as np, sympy as sp, scipy. No network, no persistent files,
    each call starts from a clean state. Example: "sum(1/k**2 for k in range(1, 10**6))".
    """
    return _run_job({"mode": "python", "code": code}, timeout)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run(transport, host=os.environ.get("MCP_HOST", "0.0.0.0"), port=int(os.environ.get("MCP_PORT", "8000")))


if __name__ == "__main__":
    main()
