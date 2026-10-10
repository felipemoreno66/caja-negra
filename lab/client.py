"""Cliente HTTP crudo + log de experimentos en el formato del README.

Cada request al original queda en lab/experimentos.jsonl con:
  id, seq, x_req, hipotesis, request, status, response, conclusion
(+ metodo/ruta cuando no es POST /msg, y ts).

Config en lab/.env (no se sube al repo):
  ORIGINAL_URL, TOKEN (caja negra), TEAM_TOKEN (entrypoint del reemplazo)
"""
import http.client
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


_load_env()
ORIGINAL_URL = os.environ.get("ORIGINAL_URL", "")
TOKEN = os.environ.get("TOKEN", "")
LOG_PATH = os.environ.get("EXPERIMENTS_LOG", os.path.join(HERE, "experimentos.jsonl"))

_DEFAULT = object()
_MIN_INTERVAL = 0.12  # ~8 req/s, bajo el límite de 10/s por token
_last_call = 0.0
_seq = "s0"


def _next_id():
    if not os.path.exists(LOG_PATH):
        return 1
    n = 0
    with open(LOG_PATH) as f:
        for _ in f:
            n += 1
    return n + 1


def set_seq(name):
    global _seq
    _seq = name


def send(method, path, *, base=None, body=None, json_body=_DEFAULT, headers=None,
         token=_DEFAULT, hipotesis="", conclusion=None, log=True, timeout=15):
    """Envía un request y devuelve dict(status, headers, text, json, x_req, ms).

    token: por defecto TOKEN; None = sin Authorization; str = ese token.
    json_body: se serializa como JSON. body: texto/bytes crudos.
    """
    global _last_call
    base = base or ORIGINAL_URL
    u = urlsplit(base)
    conn_cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection

    hdrs = dict(headers or {})
    tok = TOKEN if token is _DEFAULT else token
    if tok is not None and not any(k.lower() == "authorization" for k in hdrs):
        hdrs["Authorization"] = f"Bearer {tok}"
    if json_body is not _DEFAULT:
        body = json.dumps(json_body, ensure_ascii=False)
        hdrs.setdefault("Content-Type", "application/json")
    raw_body = body.encode() if isinstance(body, str) else body

    wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0 and base == ORIGINAL_URL:
        time.sleep(wait)
    _last_call = time.monotonic()

    t0 = time.perf_counter()
    conn = conn_cls(u.netloc, timeout=timeout)
    conn.request(method, path, body=raw_body, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    ms = round((time.perf_counter() - t0) * 1000, 1)
    resp_headers = resp.getheaders()
    conn.close()

    text = raw.decode(errors="replace")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    hmap = {k.lower(): v for k, v in resp_headers}
    x_req = hmap.get("x-req")
    try:
        x_req = int(x_req)
    except (TypeError, ValueError):
        pass

    if hmap.get("x-frontier-infra") == "rate-limit":
        print("!! rate-limit de la infraestructura; esperando 2 s")
        time.sleep(2)

    result = {"status": resp.status, "headers": resp_headers, "text": text,
              "json": parsed, "x_req": x_req, "ms": ms}

    if log and base == ORIGINAL_URL:
        if json_body is not _DEFAULT:
            req_repr = json_body
        else:
            req_repr = raw_body.decode(errors="replace") if raw_body else None
        entry = {
            "id": _next_id(),
            "seq": _seq,
            "x_req": x_req,
            "hipotesis": hipotesis,
            "request": req_repr,
            "status": resp.status,
            "response": parsed if parsed is not None else text,
        }
        if conclusion:
            entry["conclusion"] = conclusion
        if (method, path) != ("POST", "/msg"):
            entry["metodo"] = method
            entry["ruta"] = path
        custom = next((v for k, v in (headers or {}).items() if k.lower() == "authorization"), None)
        if custom is not None:
            entry["auth_header"] = re.sub(re.escape(TOKEN), "<TOKEN>", custom, flags=re.I) if TOKEN else custom
        elif tok != TOKEN:
            entry["auth"] = "sin token" if tok is None else "token distinto"
        if json_body is _DEFAULT and raw_body:
            entry["raw"] = True
        if any(k.lower() == "content-type" for k in hdrs) and json_body is _DEFAULT:
            entry["content_type"] = next(v for k, v in hdrs.items() if k.lower() == "content-type")
        entry["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        result["log_id"] = entry["id"]
    return result


def msg(m, hipotesis="", **kw):
    """POST /msg con {"m": m}."""
    return send("POST", "/msg", json_body={"m": m}, hipotesis=hipotesis, **kw)


def reset(seq_name, hipotesis="reset antes de la secuencia", **kw):
    """POST /__reset y abre una nueva secuencia en el log."""
    set_seq(seq_name)
    return send("POST", "/__reset", hipotesis=hipotesis, **kw)


def short(r):
    return f"{r['status']} {r['text'][:200]}  (x_req={r['x_req']}, {r['ms']} ms)"
