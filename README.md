# mcPython

Calculateur Python/LaTeX pour LLM local, exposé en serveur **MCP** dans un conteneur Docker.
Conçu pour LM Studio (≥ 0.3.17, support MCP natif), utilisable par tout client MCP.

## Outils exposés

| Outil | Entrée | Sortie |
|---|---|---|
| `eval_latex` | `latex`, `variables` (opt.), `solve_for` (opt.), `digits` (déf. 15) | résultat exact simplifié, LaTeX, valeur numérique ; solutions si la formule contient `=` |
| `run_python` | `code`, `timeout` (déf. 10 s, max 60 s) | `stdout` + valeur de la dernière expression (comme un REPL) |

Préchargés dans `run_python` : `math`, `cmath`, `statistics`, `Fraction`, `Decimal`, `itertools`,
`functools`, `random`, `numpy as np`, `sympy as sp`, `scipy`.

Exemples (sortie réelle du test) :

```
eval_latex  "\int_0^{\pi} \sin(x) dx"                     -> result "2"
eval_latex  "x^2 - 5x + 6 = 0"                            -> solutions ["2", "3"]
eval_latex  "\frac{1}{2} m v^2", variables {"m":2,"v":3}  -> result "9"
run_python  "Fraction(1,3)+Fraction(1,6)"                 -> result "Fraction(1, 2)"
```

## Isolation

- Chaque appel s'exécute dans un sous-processus neuf : limite CPU (= timeout), mémoire 1 Gio
  (`MCPYTHON_MEM_MB`), sortie tronquée à 20 000 caractères.
- Conteneur lancé sans réseau, en lecture seule, utilisateur non-root, capacités retirées.

## Construction

```bash
docker build -t mcpython:latest .
```

## Configuration LM Studio

Onglet *Program* → *Install* → *Edit mcp.json* (`~/.lmstudio/mcp.json`) :

```json
{
  "mcpServers": {
    "mcpython": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--network", "none", "--read-only", "--tmpfs", "/tmp",
        "--memory", "1g", "--cpus", "2", "--pids-limit", "64",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "mcpython:latest"
      ]
    }
  }
}
```

LM Studio démarre le conteneur à la demande et lui parle en stdio. Utiliser un modèle qui
gère le *tool calling* (Qwen3, Mistral Small, gpt-oss, etc.).

### Variante HTTP (conteneur permanent)

```bash
docker run -d --name mcpython -p 127.0.0.1:8000:8000 -e MCP_TRANSPORT=streamable-http mcpython:latest
```

```json
{ "mcpServers": { "mcpython": { "url": "http://127.0.0.1:8000/mcp" } } }
```

## Test de bout en bout

```bash
python3 -m venv .venv && .venv/bin/pip install mcp==2.3.0
.venv/bin/python tests/test_e2e.py
```

Lance le conteneur comme LM Studio (stdio) et vérifie 13 cas, dont timeout, dépassement
mémoire et absence de réseau.
