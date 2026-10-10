"""Oráculo del dígito de control: para un cuerpo dado, prueba controles 0..96
hasta que el original deja de responder E202. Guarda resultados en controles.json."""
import json, os, sys
from client import msg, set_seq

DB = "controles.json"
known = json.load(open(DB)) if os.path.exists(DB) else {}


def find(body):
    if body in known:
        return known[body]
    for c in range(97):
        r = msg(f"{body};{c}", hipotesis=f"oráculo: buscar el control válido de '{body}' (probando {c})")
        err = (r["json"] or {}).get("error") if isinstance(r["json"], dict) else None
        if err != "E202":
            known[body] = {"control": c, "status": r["status"], "response": r["json"], "log_id": r["log_id"]}
            json.dump(known, open(DB, "w"), ensure_ascii=False, indent=1)
            return known[body]
    known[body] = {"control": None}
    json.dump(known, open(DB, "w"), ensure_ascii=False, indent=1)
    return known[body]


if __name__ == "__main__":
    set_seq(sys.argv[1])
    for b in sys.argv[2:]:
        res = find(b)
        print(f"{b!r:24} -> control {res['control']}  {json.dumps(res.get('response'), ensure_ascii=False)}", flush=True)
