"""Sonda diferencial de la capa HTTP: mismo request al original y al reemplazo."""
import json, os, sys
from client import send, set_seq, TOKEN

REPL = os.environ.get("REPLACEMENT_URL", "http://localhost:8765")
TEAM = os.environ["TEAM_TOKEN"]
J = {"Content-Type": "application/json"}


def both(method, path, hip, auth="ok", body=None, json_body=None, headers=None):
    """auth: 'ok' | None | 'otro' | callable(token)->header value"""
    def hdrs(tok):
        h = dict(headers or {})
        if callable(auth):
            h["Authorization"] = auth(tok)
            return h, None
        return h, (tok if auth == "ok" else (None if auth is None else auth))
    kw = {}
    if json_body is not None:
        kw["json_body"] = json_body
    elif body is not None:
        kw["body"] = body
    h, t = hdrs(TOKEN)
    o = send(method, path, headers=h, token=t, hipotesis=hip, **kw)
    h, t = hdrs(TEAM)
    p = send(method, path, base=REPL, headers=h, token=t, log=False, **kw)
    same = (o["status"], o["text"]) == (p["status"], p["text"]) or (o["status"] == p["status"] and o["json"] is not None and o["json"] == p["json"])
    tag = "ok  " if same else "DIFF"
    print(f"{tag} {method:7} {path:16} {hip[:55]:55} orig={o['status']} {o['text'][:90]!r}" + ("" if same else f"\n      repl={p['status']} {p['text'][:90]!r}"), flush=True)
    return o


if __name__ == "__main__":
    set_seq(sys.argv[1] if len(sys.argv) > 1 else "http-edge")
    both("POST", "/__reset", "reset inicial")
    for m in ["OPTIONS", "HEAD", "PATCH"]:
        for path in ["/msg", "/health", "/__reset", "/nada"]:
            both(m, path, f"{m} {path}: ¿404, 405, 204?")
    both("OPTIONS", "/msg", "OPTIONS /msg sin token (preflight CORS)", auth=None, headers={"Origin": "https://x.com", "Access-Control-Request-Method": "POST"})
    for path in ["/health/", "/HEALTH", "//msg", "/msg/../msg", "/msg%20", "/__reset/", "/__RESET", "/msg.json"]:
        both("POST" if "msg" in path or "reset" in path.lower() else "GET", path, f"variante de ruta {path}", json_body={"m": "PING;64"} if "msg" in path else None)
    both("GET", "/health?x=1", "health con query")
    for name, fn in [("bearer minúscula", lambda t: f"bearer {t}"), ("BEARER mayúscula", lambda t: f"BEARER {t}"),
                     ("doble espacio", lambda t: f"Bearer  {t}"), ("espacio final", lambda t: f"Bearer {t} "),
                     ("sin Bearer", lambda t: t), ("Token esquema", lambda t: f"Token {t}"),
                     ("Bearer vacío", lambda t: "Bearer "), ("Bearer solo", lambda t: "Bearer"),
                     ("token + basura", lambda t: f"Bearer {t}x"), ("Basic", lambda t: "Basic dXNlcjpwYXNz")]:
        both("POST", "/msg", f"auth {name}", auth=fn, json_body={"m": "PING;64"})
        both("GET", "/health", f"auth {name} en health", auth=fn)
    both("POST", "/msg", "body con BOM", body="﻿{\"m\":\"PING;64\"}", headers=J)
    both("POST", "/msg", "body NaN", body="NaN", headers=J)
    both("POST", "/msg", "body null", body="null", headers=J)
    both("POST", "/msg", "body true", body="true", headers=J)
    both("POST", "/msg", "body número", body="5", headers=J)
    both("POST", "/msg", "body solo espacios", body="   ", headers=J)
    both("POST", "/msg", "claves duplicadas", body='{"m":"X;1","m":"PING;64"}', headers=J)
    both("POST", "/msg", "m anidado", json_body={"m": {"m": "PING;64"}})
    both("POST", "/msg", "m con escape unicode", body='{"m":"PI\\u004eG;64"}', headers=J)
    both("POST", "/msg", "JSON con coma final", body='{"m":"PING;64",}', headers=J)
    both("POST", "/msg", "JSON con comillas simples", body="{'m':'PING;64'}", headers=J)
    both("POST", "/msg", "form urlencoded", body="m=PING%3B64", headers={"Content-Type": "application/x-www-form-urlencoded"})
    both("POST", "/msg", "texto con salto en string", body='{"m":"PING;64\n"}', headers=J)
    both("POST", "/msg", "body enorme 200KB", json_body={"m": "ALTA;" + "A" * 200000 + ";1"})
    both("POST", "/msg", "content-type raro con json", body='{"m":"PING;64"}', headers={"Content-Type": "text/html"})
