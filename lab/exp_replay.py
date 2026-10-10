"""Reproduce pruebas/ejemplos.jsonl contra el original y reporta diferencias."""
import json, sys
from client import reset, msg, short
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # rutas relativas a lab/, se ejecute desde donde se ejecute

seq = sys.argv[1] if len(sys.argv) > 1 else "replay-ejemplos"
rows = [json.loads(l) for l in open("ejemplos.jsonl")]
r = reset(seq)
print("reset:", short(r))
diffs = 0
for row in rows:
    r = msg(row["request"]["m"], hipotesis=f"replay ejemplo n={row['n']}: ¿misma respuesta que en la mañana?")
    same = r["status"] == row["status"] and r["json"] == row["response"]
    diffs += not same
    print(("OK  " if same else "DIFF"), row["request"]["m"], "->", short(r))
    if not same:
        print("     esperado:", row["status"], json.dumps(row["response"], ensure_ascii=False))
print(f"\n{len(rows)-diffs}/{len(rows)} iguales")
