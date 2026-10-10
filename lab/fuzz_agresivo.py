"""Fuzzer diferencial agresivo: muta mensajes válidos carácter a carácter, ataca el cuerpo JSON
y la capa HTTP, y genera secuencias largas con valores límite. Todo request al original queda
en el log; cada diferencia con el reemplazo se imprime con su línea de log.

  REPLACEMENT_URL=http://localhost:8765 python3 lab/fuzz_agresivo.py <modo> <semilla> <n>
  modos: mutacion | cuerpo | http | secuencias
"""
import json, os, random, sys
from client import send, reset, msg, TOKEN
from checksum import control

REPL = os.environ.get("REPLACEMENT_URL", "http://localhost:8765")
TEAM = os.environ["TEAM_TOKEN"]
DIFFS = []

CHARS = (list("AZaz09;-. ,+_/\\'\"") + ["\t", "\n", "\r", "\x00", "\x7f", "é", "ñ", "ß", "ı", "İ", "０", "٣", "😀",
         "​", "﻿", " ", "ﬁ", "Ω"])
TEMPLATES = ["PING;64", "ALTA;Ana", "CONSULTA;AC-0001", "DEPOSITO;AC-0001;500", "TRANSFER;AC-0001;AC-0002;100",
             "ANULA;OP-0001", "HALT;X", "CONSULTA;AC-0002", "DEPOSITO;AC-0002;100000", "TRANSFER;AC-0002;AC-0001;1"]


def same(o, p):
    if o["status"] != p["status"]:
        return False
    if o["json"] is not None and p["json"] is not None:
        return o["json"] == p["json"]
    return o["text"] == p["text"]


def report(tag, o, p, detail):
    DIFFS.append(tag)
    print(f"DIFF [{tag}] log#{o.get('log_id')} {detail}\n   original:  {o['status']} {o['text'][:140]!r}\n"
          f"   reemplazo: {p['status']} {p['text'][:140]!r}", flush=True)


def pair_msg(m, hip, tag):
    o = msg(m, hip)
    p = send("POST", "/msg", base=REPL, token=TEAM, json_body={"m": m}, log=False)
    if not same(o, p):
        report(tag, o, p, repr(m)[:120])
    return o


def reset_both(name, hip):
    reset(name, hipotesis=hip)
    send("POST", "/__reset", base=REPL, token=TEAM, log=False)


# --- modo 1: mutación de mensajes --------------------------------------------------
def mutate(r, s):
    for _ in range(r.randint(1, 3)):
        op = r.choice(["ins", "del", "rep", "case", "dupseg", "swapseg", "edge"])
        i = r.randint(0, max(0, len(s) - 1))
        if op == "ins":
            s = s[:i] + r.choice(CHARS) + s[i:]
        elif op == "del" and s:
            s = s[:i] + s[i + 1:]
        elif op == "rep" and s:
            s = s[:i] + r.choice(CHARS) + s[i + 1:]
        elif op == "case" and s:
            s = s[:i] + s[i].swapcase() + s[i + 1:]
        elif op == "dupseg":
            seg = s.split(";"); k = r.randrange(len(seg)); seg.insert(k, seg[k]); s = ";".join(seg)
        elif op == "swapseg":
            seg = s.split(";")
            if len(seg) > 1:
                a, b = r.sample(range(len(seg)), 2); seg[a], seg[b] = seg[b], seg[a]
            s = ";".join(seg)
        else:
            s = r.choice([" ", "\t", "\n", ";", "\x00"]) + s if r.random() < .5 else s + r.choice([" ", "\t", "\n", ";", "\x00"])
    return s


def modo_mutacion(seed, n):
    r = random.Random(seed)
    for k in range(n):
        name = f"agresivo-mutacion-{seed}-{k}"
        hip = f"fuzz agresivo, mutación de mensajes (semilla {seed}, secuencia {k})"
        reset_both(name, hip + ": reset")
        for m in ["ALTA;Ana", "ALTA;Beto", "DEPOSITO;AC-0001;1000"]:
            pair_msg(f"{m};{control(m)}", hip + ": preparación", name)
        for j in range(8):
            body = mutate(r, r.choice(TEMPLATES))
            u = r.random()
            if u < 0.6:
                m = f"{body};{control(body)}"          # firmado sobre el texto mutado
            elif u < 0.8:
                base = r.choice(TEMPLATES); m = mutate(r, f"{base};{control(base)}")  # muta después de firmar
            else:
                m = body
            pair_msg(m, f"{hip}: mensaje mutado {j}", name)
        for m in ["CONSULTA;AC-0001", "CONSULTA;AC-0002", "CONSULTA;AC-0003"]:
            pair_msg(f"{m};{control(m)}", hip + ": verificación de estado", name)


# --- modo 2: cuerpo JSON -----------------------------------------------------------------
def rand_json(r, depth=0):
    t = r.choice(["str", "num", "bool", "null", "arr", "obj"] if depth < 4 else ["str", "num", "bool", "null"])
    if t == "str":
        return r.choice(["", "PING;64", "x" * r.randint(1, 30), "\x00", "😀", "ñ"])
    if t == "num":
        return r.choice([0, -1, 1.5, 10 ** 30, -0.0, 1e300])
    if t == "bool":
        return r.random() < .5
    if t == "null":
        return None
    if t == "arr":
        return [rand_json(r, depth + 1) for _ in range(r.randint(0, 3))]
    return {r.choice(["m", "M", "x", "", "m ", " m", "__proto__", "constructor"]): rand_json(r, depth + 1) for _ in range(r.randint(0, 3))}


RAW_BODIES = [
    '{"m":"PING;64"}  ', '\n{"m":"PING;64"}\n', '\t{"m":"PING;64"}', '{ "m" : "PING;64" }', '{"m":"PING;64"}{}',
    '{"m":"PING;64"} x', '{"m":"PI\\u004eG;64"}', '{"\\u006d":"PING;64"}', '{"m":"PING;\\u0036\\u0034"}',
    '{"m":"ALTA;\\ud800;50"}', '{"m":"ALTA;\\udfff;50"}', '{"m":"ALTA;\\u0000;50"}', '{"m":"PING;64\\u0000"}',
    '{"m":"PING;64","m":5}', '{"m":5,"m":"PING;64"}', '{"m":"PING;64",}', '{"m":"PING;64"', '{"m":"PING;64"]',
    '{"m":\'PING;64\'}', '{m:"PING;64"}', '{"m":"PING;64" /*c*/}', '{"m":"PING;64"}\x00', '{"m":"\\x41LTA;1"}',
    '{"m":"PING;64","x":1e999}', '{"m":"PING;64","x":-0}', '{"m":"PING;64","x":01}', '{"m":"PING;64","x":.5}',
    '{"m":"PING;64","x":1.}', '{"m":"PING;64","x":+1}', '{"m":"PING;64","x":0x1F}', '{"m":"PING;64","x":Infinity}',
    '{"m":"PING;64","x":-Infinity}', '{"m":"PING;64","x":undefined}', '{"m":"PING;64","x":true}', '{"m":"PING;64","x":True}',
    '{"m":"PING;64","x":"\\q"}', '{"m":"PING;64","x":"\\u12"}', '{"m":"PING;64","x":"tab\tliteral"}', '[]', '{}', '""',
    '"PING;64"', '0', '-1', 'true', 'false', 'null', ' ', '﻿{"m":"PING;64"}', '{"m":"PING;64"}﻿',
]


def modo_cuerpo(seed, n):
    r = random.Random(seed)
    name = f"agresivo-cuerpo-{seed}"
    reset_both(name, "fuzz agresivo, cuerpo JSON: reset")
    J = {"Content-Type": "application/json"}
    bodies = list(RAW_BODIES)
    for _ in range(n):
        obj = rand_json(r)
        if isinstance(obj, dict) and r.random() < .6:
            obj["m"] = r.choice(["PING;64", "ALTA;Ana;50", "CONSULTA;AC-0001;14", "", ";", "PING", 64, None, ["PING;64"]])
        bodies.append(json.dumps(obj, ensure_ascii=r.random() < .5))
    for b in bodies:
        o = send("POST", "/msg", body=b, headers=J, hipotesis=f"fuzz agresivo, cuerpo JSON: {b[:80]!r}")
        p = send("POST", "/msg", base=REPL, token=TEAM, body=b, headers=J, log=False)
        if not same(o, p):
            report(name, o, p, repr(b)[:120])


# --- modo 3: capa HTTP -------------------------------------------------------------------
PATHS = ["/msg", "/health", "/__reset", "/%6Dsg", "/m%73g", "/MSG", "/msg/", "/msg;x", "/msg?", "/msg?a=1&b",
         "/health?", "/./msg", "/msg/.", "/%2Fmsg", "/msg%2F", "/__reset?x=1", "/__Reset", "/healthz", "/msg%00", "/msg%23x",
         "/%5F%5Freset", "/__reset%20", "/health%3F", "/", "/msg ", "/ms g"]
METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "post", "Post", "get", "TRACE", "CONNECT", "FOO"]
AUTHS = ["Bearer <T>", " Bearer <T>", "Bearer <T>\t", "Bearer\t<T>", "Bearer <T>,", "Bearer <t>", "Bearer <T>;",
         "Bearer  <T> ", "bearer <T>", "Bearer", "", "Bearer <T> <T>", "Bearer \"<T>\"", "<T> Bearer"]


def modo_http(seed, n):
    r = random.Random(seed)
    name = f"agresivo-http-{seed}"
    reset_both(name, "fuzz agresivo, capa HTTP: reset")
    cases = [("POST", p, "Bearer <T>", '{"m":"PING;64"}') for p in PATHS]
    cases += [("GET", "/health", a, None) for a in AUTHS] + [("POST", "/msg", a, '{"m":"PING;64"}') for a in AUTHS]
    cases += [(m, "/msg", "Bearer <T>", '{"m":"PING;64"}') for m in METHODS]
    cases += [(m, "/health", "Bearer <T>", None) for m in METHODS]
    for _ in range(n):
        cases.append((r.choice(METHODS), r.choice(PATHS), r.choice(AUTHS), r.choice([None, '{"m":"PING;64"}', "{"])))
    for method, path, auth, body in cases:
        def call(base, tok, log):
            h = {"Content-Type": "application/json"}
            kw = {"body": body} if body is not None else {}
            if auth:
                h["Authorization"] = auth.replace("<T>", tok).replace("<t>", tok.lower())
            try:
                return send(method, path, base=base, headers=h, token=None, log=log,
                            hipotesis=f"fuzz agresivo, HTTP: {method} {path} auth={auth!r}", **kw)
            except Exception as e:  # noqa: BLE001
                return {"status": "EXC", "text": repr(e)[:100], "json": None, "log_id": None}
        o = call(None, TOKEN, True)
        p = call(REPL, TEAM, False)
        if not same(o, p):
            report(name, o, p, f"{method} {path} auth={auth!r} body={body!r}")


# --- modo 4: secuencias largas con valores límite ------------------------------------------
AMOUNTS = ["1", "49999", "50000", "50001", "500", "99999", "100000", "100001", "9999999999", "10000000000", "0", "00", "01", "1 ", " 1", "1.0", "１", "+1",
           "-1", "1e5", "", "1_000", "0x10", "١"]


def modo_secuencias(seed, n):
    r = random.Random(seed)
    for k in range(n):
        name = f"agresivo-secuencia-{seed}-{k}"
        hip = f"fuzz agresivo, secuencia con límites (semilla {seed}, secuencia {k})"
        reset_both(name, hip + ": reset")
        accounts = ops = 0
        for j in range(r.randint(6, 12)):
            acc = lambda: f"AC-{r.randint(1, max(1, accounts + 1)):04d}"  # noqa: E731
            kind = r.choices(["ALTA", "DEP", "TRF", "CON", "ANU", "HALT", "PING", "RAW"], [15, 20, 25, 12, 15, 3, 3, 7])[0]
            if kind == "ALTA":
                body = f"ALTA;{r.choice(['Ana', 'x', 'Ñu', 'a b', '1'])}"; accounts += 1
            elif kind == "DEP":
                body = f"DEPOSITO;{acc()};{r.choice(AMOUNTS)}"; ops += 1
            elif kind == "TRF":
                a, b = acc(), acc()
                body = f"TRANSFER;{a};{b if r.random() < .9 else a};{r.choice(AMOUNTS)}"; ops += 1
            elif kind == "CON":
                body = f"CONSULTA;{acc()}"
            elif kind == "ANU":
                body = f"ANULA;OP-{r.randint(1, max(1, ops + 1)):04d}"
            elif kind == "HALT":
                body = f"HALT;{r.choice(['1', '0', ' 1', '1 ', 'x'])}"
            elif kind == "PING":
                body = r.choice(["PING", "ping", "PING;1;2"])
            else:
                body = mutate(r, r.choice(TEMPLATES))
            m = f"{body};{control(body)}" if not body.upper().startswith("PING") else (body if ";" in body else body + ";64")
            pair_msg(m, f"{hip}: paso {j}", name)


if __name__ == "__main__":
    modo, seed, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    {"mutacion": modo_mutacion, "cuerpo": modo_cuerpo, "http": modo_http, "secuencias": modo_secuencias}[modo](seed, n)
    print(f"\n[{modo} semilla {seed}] diferencias: {len(DIFFS)}")
