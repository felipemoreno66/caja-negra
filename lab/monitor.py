"""Monitor de cambios del original: re-ejecuta secuencias ya registradas y compara
con lo que respondió antes. Cada request queda en el log como un experimento más.

  python3 lab/monitor.py              # una pasada
  python3 lab/monitor.py --all        # todas las secuencias del log
  python3 lab/monitor.py --seqs ejemplos-oficiales --loop 300  # detector rápido cada 5 minutos
  python3 lab/monitor.py --loop 3600  # una pasada cada hora hasta las 19:50
"""
import json, sys, time
from collections import OrderedDict
from datetime import datetime
from client import send, set_seq
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # rutas relativas a lab/, se ejecute desde donde se ejecute

SEQS = ["ejemplos-oficiales", "transfer", "anula", "integridad-2", "sugerencias-empates", "halt-detenido"]


def load():
    seqs = OrderedDict()
    for line in open("experimentos.jsonl"):
        e = json.loads(line)
        seqs.setdefault(e["seq"], []).append(e)
    ej = [json.loads(l) for l in open("ejemplos.jsonl")]
    seqs["ejemplos-oficiales"] = [{"ruta": "/__reset", "metodo": "POST", "request": None, "status": 200,
                                   "response": {"ok": True}, "id": "-"}] + ej
    return seqs


def run_once():
    seqs = load()
    stamp = datetime.now().strftime("%H%M")
    changes = []
    total = 0
    for name in SEQS:
        set_seq(f"monitor-{stamp}-{name}")
        for e in seqs[name]:
            auth = e.get("auth")
            kw = {"token": None} if auth == "sin token" else ({"token": "otro"} if auth == "token distinto" else {})
            if e.get("raw") or "content_type" in e:
                kw["body"] = e["request"] or ""
                if "content_type" in e:
                    kw["headers"] = {"Content-Type": e["content_type"]}
            elif e["request"] is not None:
                kw["json_body"] = e["request"]
            r = send(e.get("metodo", "POST"), e.get("ruta", "/msg"),
                     hipotesis=f"monitor de cambios: ¿el original sigue respondiendo igual que en el log #{e['id']}?", **kw)
            total += 1
            got = r["json"] if r["json"] is not None else r["text"]
            if r["status"] != e["status"] or got != e["response"]:
                changes.append((name, e, r))
    line = f"{datetime.now().isoformat(timespec='seconds')} pasos={total} cambios={len(changes)}"
    with open("cambios.log", "a") as f:
        f.write(line + "\n")
        for name, e, r in changes:
            f.write(f"  [{name}] log#{e['id']} {json.dumps(e['request'], ensure_ascii=False)} "
                    f"antes={e['status']} {json.dumps(e['response'], ensure_ascii=False)} "
                    f"ahora={r['status']} {r['text']} (log#{r['log_id']})\n")
    print(line, flush=True)
    for name, e, r in changes:
        print(f"  CAMBIO [{name}] {e['request']} antes={e['status']} {e['response']} ahora={r['status']} {r['text']}", flush=True)
    return changes


if __name__ == "__main__":
    if "--all" in sys.argv:
        SEQS[:] = [k for k, v in load().items()
                   if not k.startswith(("monitor-", "oraculo")) and (v[0].get("ruta") == "/__reset" or k.startswith("entrada-") or k == "ejemplos-oficiales")]
    if "--seqs" in sys.argv:
        SEQS[:] = sys.argv[sys.argv.index("--seqs") + 1].split(",")
    if "--loop" in sys.argv:
        every = int(sys.argv[sys.argv.index("--loop") + 1])
        while True:
            if run_once():
                sys.exit(3)  # sale para avisar del cambio
            if datetime.now().strftime("%H%M") >= "1950":
                break
            time.sleep(every)
    else:
        run_once()
