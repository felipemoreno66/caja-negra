"""Regresión: reproduce contra el reemplazo cada secuencia del log que empieza con
POST /__reset (y los 20 ejemplos oficiales) y compara status + body como el evaluador:
JSON sin importar orden de claves; si no es JSON, texto exacto.

  REPLACEMENT_URL=http://localhost:8000 python3 lab/replay_log.py [--verbose]
"""
import json, os, sys
from collections import OrderedDict
from client import send

BASE = os.environ.get("REPLACEMENT_URL", "http://localhost:8000")
TEAM = os.environ["TEAM_TOKEN"]


def load_seqs():
    seqs = OrderedDict()
    for line in open("experimentos.jsonl"):
        e = json.loads(line)
        seqs.setdefault(e["seq"], []).append(e)
    # Secuencias con reset inicial, más las de la capa HTTP (no dependen del estado).
    seqs = {k: v for k, v in seqs.items() if v[0].get("ruta") == "/__reset" or k.startswith("entrada-")}
    ej = [json.loads(l) for l in open("ejemplos.jsonl")]
    seqs["ejemplos-oficiales"] = [{"ruta": "/__reset", "metodo": "POST", "request": None, "status": 200,
                                   "response": {"ok": True}, "id": "-"}] + ej
    return seqs


def replay(e):
    method, path = e.get("metodo", "POST"), e.get("ruta", "/msg")
    auth = e.get("auth")
    token = None if auth == "sin token" else ("otro-token" if auth == "token distinto" else TEAM)
    kw = {}
    if e.get("raw") or "content_type" in e:
        kw["body"] = e["request"] or ""
        if "content_type" in e:
            kw["headers"] = {"Content-Type": e["content_type"]}
    elif e["request"] is not None:
        kw["json_body"] = e["request"]
    return send(method, path, base=BASE, token=token, log=False, **kw)


def same(e, r):
    if e["status"] != r["status"]:
        return False
    if r["json"] is not None:
        return r["json"] == e["response"]
    return r["text"] == e["response"]


def main(verbose):
    total = ok = 0
    seq_ok = seq_total = 0
    for name, steps in load_seqs().items():
        seq_total += 1
        good = True
        for e in steps:
            r = replay(e)
            total += 1
            if same(e, r):
                ok += 1
            else:
                good = False
                print(f"FAIL [{name}] log#{e['id']} {e.get('metodo','POST')} {e.get('ruta','/msg')} {json.dumps(e['request'], ensure_ascii=False)[:90]}")
                print(f"     original:  {e['status']} {json.dumps(e['response'], ensure_ascii=False)[:150]}")
                print(f"     reemplazo: {r['status']} {r['text'][:150]}")
        seq_ok += good
        if verbose and good:
            print(f"ok   [{name}] {len(steps)} pasos")
    print(f"\nPasos: {ok}/{total} ({100*ok/total:.1f}%)   Secuencias completas: {seq_ok}/{seq_total}")


if __name__ == "__main__":
    main("--verbose" in sys.argv)
