"""Helpers para correr secuencias de experimentos contra el original."""
from client import reset, msg, send, short
from checksum import sign


def run(seq, steps, do_reset=True):
    """steps: lista de (mensaje, hipotesis) o (mensaje, hipotesis, False) para no firmar."""
    if do_reset:
        reset(seq)
    out = []
    for st in steps:
        m, hip = st[0], st[1]
        signed = st[2] if len(st) > 2 else True
        mm = sign(m) if signed else m
        r = msg(mm, hip)
        print(f"{mm:45} -> {r['status']} {r['text'][:160]}", flush=True)
        out.append(r)
    return out


def http(method, path, hip, **kw):
    r = send(method, path, hipotesis=hip, **kw)
    ct = dict((k.lower(), v) for k, v in r["headers"]).get("content-type")
    print(f"{method:7} {path:22} {str(kw.get('token','(token)'))[:12]:12} -> {r['status']} [{ct}] {r['text'][:160]!r}", flush=True)
    return r
