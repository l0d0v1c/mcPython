"""Isolated worker: reads a JSON job on stdin, writes a JSON result on stdout.

Spawned as a fresh subprocess for every call so that a crash, an infinite loop
or a memory blow-up never takes the MCP server down.
"""

import ast
import contextlib
import io
import json
import os
import resource
import sys
import traceback

MAX_OUTPUT = int(os.environ.get("MCPYTHON_MAX_OUTPUT", "20000"))


def _set_limits(cpu_seconds: int) -> None:
    mem = int(os.environ.get("MCPYTHON_MEM_MB", "1024")) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024,) * 2)


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n... [truncated, {len(text) - MAX_OUTPUT} more chars]"


def _prelude() -> dict:
    ns: dict = {"__name__": "__main__"}
    exec(
        "import math, cmath, statistics, fractions, decimal, itertools, functools, random\n"
        "import numpy as np\n"
        "import sympy as sp\n"
        "import scipy\n"
        "from fractions import Fraction\n"
        "from decimal import Decimal\n",
        ns,
    )
    return ns


def run_python(code: str) -> dict:
    """Execute code REPL-style: the value of a trailing expression is returned."""
    ns = _prelude()
    out = io.StringIO()
    result = None
    try:
        tree = ast.parse(code, mode="exec")
        last = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(compile(tree, "<code>", "exec"), ns)
            if last is not None:
                value = eval(compile(last, "<code>", "eval"), ns)
                if value is not None:
                    if hasattr(value, "item") and getattr(value, "shape", None) == ():
                        value = value.item()  # numpy scalar -> plain Python number
                    result = repr(value)
    except BaseException:  # noqa: BLE001 - report everything, including SystemExit
        return {"ok": False, "stdout": _truncate(out.getvalue()), "error": _truncate(traceback.format_exc(limit=5))}
    return {"ok": True, "stdout": _truncate(out.getvalue()), "result": _truncate(result) if result else None}


def eval_latex(latex: str, variables: dict, solve_for: str | None, digits: int) -> dict:
    import sympy as sp
    from sympy.parsing.latex import parse_latex

    try:
        expr = parse_latex(latex)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"LaTeX parse error: {exc}"}

    try:
        # The LaTeX parser yields plain symbols for pi, e and i; map them to constants
        # unless the caller explicitly gave them a value.
        consts = {sp.Symbol("pi"): sp.pi}
        if "e" not in variables:
            consts[sp.Symbol("e")] = sp.E
        if "i" not in variables and solve_for != "i":
            consts[sp.Symbol("i")] = sp.I
        expr = expr.subs(consts)

        subs = {sp.Symbol(k): sp.sympify(v) for k, v in variables.items()}
        expr = expr.subs(subs)

        res: dict = {"ok": True, "parsed": str(expr)}

        if isinstance(expr, sp.Equality):
            free = sorted(expr.free_symbols, key=lambda s: s.name)
            if solve_for:
                target = sp.Symbol(solve_for)
            elif len(free) == 1:
                target = free[0]
            else:
                return {"ok": False, "parsed": str(expr),
                        "error": f"Equation has unknowns {[s.name for s in free]}: give solve_for or variables."}
            sols = sp.solve(sp.Eq(expr.lhs.doit(), expr.rhs.doit()), target)
            res["solve_for"] = target.name
            res["solutions"] = [str(s) for s in sols]
            res["solutions_latex"] = [sp.latex(s) for s in sols]
            res["solutions_numeric"] = [str(sp.N(s, digits)) for s in sols]
            return res

        value = sp.simplify(expr.doit())
        res["result"] = str(value)
        res["result_latex"] = sp.latex(value)
        res["free_symbols"] = sorted(s.name for s in value.free_symbols)
        if not value.free_symbols:
            res["numeric"] = str(sp.N(value, digits))
        return res
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": traceback.format_exc(limit=3)}


def main() -> None:
    job = json.load(sys.stdin)
    _set_limits(int(job.get("cpu_seconds", 10)))
    if job["mode"] == "python":
        out = run_python(job["code"])
    else:
        out = eval_latex(job["latex"], job.get("variables") or {}, job.get("solve_for"), int(job.get("digits", 15)))
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
