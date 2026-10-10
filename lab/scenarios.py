"""Escenarios diferenciales explícitos: cada uno se manda al original (log) y al reemplazo."""
import os, sys
from client import send, reset, msg
from checksum import sign

REPL = os.environ.get("REPLACEMENT_URL", "http://localhost:8765")
TEAM = os.environ["TEAM_TOKEN"]


def run(name, steps, hip):
    reset(name, hipotesis=f"{hip}: reset")
    send("POST", "/__reset", base=REPL, token=TEAM, log=False)
    bad = 0
    for i, st in enumerate(steps):
        m = st if isinstance(st, tuple) else sign(st)
        m = m[0] if isinstance(m, tuple) else m
        o = msg(m, f"{hip} (paso {i})")
        p = send("POST", "/msg", base=REPL, token=TEAM, json_body={"m": m}, log=False)
        same = o["status"] == p["status"] and (o["json"] == p["json"] if o["json"] is not None else o["text"] == p["text"])
        if not same:
            bad += 1
            print(f"  DIFF [{name}] paso {i} log#{o['log_id']} {m[:70]!r}\n     orig={o['status']} {o['text'][:120]}\n     repl={p['status']} {p['text'][:120]}", flush=True)
    print(f"{'ok  ' if not bad else 'FAIL'} {name} ({len(steps)} pasos)", flush=True)
