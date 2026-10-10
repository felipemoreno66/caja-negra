"""Reemplazo de la caja negra.

Un solo proceso, sin dependencias. Estado en memoria que POST /__reset devuelve al inicio.
Cada comportamiento está descrito en SPEC.md con su evidencia en lab/experimentos.jsonl.

Variables de entorno:
  TEAM_TOKEN  token del equipo (Authorization: Bearer <TEAM_TOKEN>)
  PORT        puerto HTTP (Railway lo define)
"""
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEAM_TOKEN = os.environ.get("TEAM_TOKEN", "")
PORT = int(os.environ.get("PORT", "8000"))

COMMANDS = {  # comando -> cantidad de argumentos (sin contar el control)
    "ALTA": 1,
    "ANULA": 1,
    "CONSULTA": 1,
    "DEPOSITO": 2,
    "HALT": 1,
    "PING": 1,  # PING no lleva control: su único argumento ocupa ese lugar
    "TRANSFER": 3,
}
TRANSFER_LIMIT = 50_000  # v2 (desde ~15:51); en v1 era 100_000
REJECTIONS_TO_BLOCK = 3  # v2: rechazos seguidos (E506/E507) que bloquean la cuenta de origen
MAX_BODY_BYTES = 8192
MAX_JSON_DEPTH = 20  # contando la raíz; arrays y objetos por igual
CONTROL_RE = re.compile(r"[0-9]{1,2}", re.ASCII)
AMOUNT_RE = re.compile(r"[1-9][0-9]{0,9}", re.ASCII)


_ASCII_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def ascii_upper(text):
    """Mayúsculas solo para a-z: el original no convierte "ß" en "SS" ni "ı" en "I"."""
    return text.translate(_ASCII_UPPER)


def err(status, code, mensaje, **extra):
    return status, {"error": code, "mensaje": mensaje, **extra}


# --- Integridad ---------------------------------------------------------------

def control(body):
    """Letras ASCII -> A=1..Z=26 (sin distinguir mayúsculas), dígitos ASCII tal cual, el resto se ignora.
    Se concatena como número N y el control es 98 - (N*100 mod 97)."""
    n = 0  # N mod 97, dígito a dígito: N puede tener miles de dígitos
    for ch in ascii_upper(body):
        if "A" <= ch <= "Z":
            digits = str(ord(ch) - 64)
        elif "0" <= ch <= "9":
            digits = ch
        else:
            continue
        for d in digits:
            n = (n * 10 + int(d)) % 97
    return 98 - (n * 100) % 97


def levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def suggestion(cmd):
    """Comando más cercano a distancia <= 2; en empate gana el primero alfabéticamente."""
    best = None
    for name in sorted(COMMANDS):
        d = levenshtein(cmd, name)
        if d <= 2 and (best is None or d < best[0]):
            best = (d, name)
    return best[1] if best else None


# --- Estado -------------------------------------------------------------------

class State:
    def __init__(self):
        self.reset()

    def reset(self):
        self.halted = False
        self.accounts = {}  # "AC-0001" -> saldo en céntimos
        self.ops = {}  # "OP-0001" -> dict
        self.rejections = {}  # v2: cuenta -> rechazos seguidos como origen (E506/E507)
        self.blocked = {}  # v2: cuenta bloqueada -> intentos de transferir desde ella
        self.next_account = 1
        self.next_op = 1

    def unblock(self, acc):
        self.rejections.pop(acc, None)
        self.blocked.pop(acc, None)

    def reject(self, acc, status, code, mensaje):
        self.rejections[acc] = self.rejections.get(acc, 0) + 1
        if self.rejections[acc] >= REJECTIONS_TO_BLOCK:
            self.blocked[acc] = 0
        return err(status, code, mensaje)

    def new_op(self, **op):
        op_id = f"OP-{self.next_op:04d}"
        self.next_op += 1
        self.ops[op_id] = {**op, "anulada": False}
        return op_id


STATE = State()
LOCK = threading.Lock()


# --- Comandos -----------------------------------------------------------------

def cmd_ping(st, args):
    return 200, {"pong": True}


def cmd_alta(st, args):
    acc_id = f"AC-{st.next_account:04d}"
    st.next_account += 1
    st.accounts[acc_id] = 0
    return 201, {"cuentaId": acc_id}


def cmd_consulta(st, args):
    acc = args[0]
    if acc not in st.accounts:
        return err(404, "E401", "cuenta inexistente")
    return 200, {"cuenta_id": acc, "saldo": format_saldo(st.accounts[acc])}


def format_saldo(cents):
    """v2: el saldo se muestra como texto en unidades con 2 decimales (40000 -> "400.00")."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def cmd_deposito(st, args):
    acc, monto = args
    if not AMOUNT_RE.fullmatch(monto):
        return err(400, "E303", "monto inválido")
    if acc not in st.accounts:
        return err(404, "E401", "cuenta inexistente")
    monto = int(monto)
    st.accounts[acc] += monto
    st.unblock(acc)  # v2: un depósito desbloquea la cuenta y reinicia sus rechazos
    return 200, {"status": "recieved", "operacionId": st.new_op(tipo="deposito", cuenta=acc, monto=monto)}


def cmd_transfer(st, args):
    origen, destino, monto = args
    if not AMOUNT_RE.fullmatch(monto):
        return err(400, "E303", "monto inválido")
    if origen == destino:
        return err(400, "E304", "origen y destino iguales")
    if origen not in st.accounts or destino not in st.accounts:
        return err(404, "E401", "cuenta inexistente")
    if origen in st.blocked:  # v2
        st.blocked[origen] += 1
        return err(423, "E510", "cuenta bloqueada", intentos=st.blocked[origen])
    monto = int(monto)
    if monto > TRANSFER_LIMIT:
        return st.reject(origen, 422, "E506", "límite excedido")
    if st.accounts[origen] < monto:
        return st.reject(origen, 422, "E507", "saldo insuficiente")
    st.rejections.pop(origen, None)  # v2: una transferencia exitosa reinicia el contador
    st.accounts[origen] -= monto
    st.accounts[destino] += monto
    op_id = st.new_op(tipo="transfer", origen=origen, destino=destino, monto=monto)
    return 200, {"status": "recieved", "operacionId": op_id}


def cmd_anula(st, args):
    op_id = args[0]
    op = st.ops.get(op_id)
    if op is None:
        return err(404, "E402", "operación inexistente")
    if op["anulada"]:
        return 200, {"ok": False, "motivo": "ya anulada"}
    # Revierte sin validar saldos: una cuenta puede quedar negativa (ver Riesgos en SPEC.md).
    if op["tipo"] == "deposito":
        st.accounts[op["cuenta"]] -= op["monto"]
    else:
        st.accounts[op["origen"]] += op["monto"]
        st.accounts[op["destino"]] -= op["monto"]
    op["anulada"] = True
    return 200, {"ok": True, "anulada": op_id}


def cmd_halt(st, args):
    if args[0] != "1":
        return err(409, "E520", "operación destructiva: detiene el servicio; reenvía con confirmación")
    st.halted = True
    return err(503, "E599", "service halted")


HANDLERS = {
    "ALTA": cmd_alta,
    "ANULA": cmd_anula,
    "CONSULTA": cmd_consulta,
    "DEPOSITO": cmd_deposito,
    "HALT": cmd_halt,
    "PING": cmd_ping,
    "TRANSFER": cmd_transfer,
}


def json_depth(text):
    """Profundidad máxima de arrays/objetos, sin recursión y sin contar lo que está dentro de strings."""
    depth = deepest = 0
    in_string = escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
            deepest = max(deepest, depth)
        elif ch in "]}":
            depth -= 1
    return deepest


def handle_message(st, raw_body):
    """Procesa el cuerpo de POST /msg en el mismo orden de validación que el original."""
    try:
        # Los bytes UTF-8 inválidos se reemplazan por U+FFFD, como hace el original.
        text = raw_body.decode("utf-8", errors="replace")
        if json_depth(text) > MAX_JSON_DEPTH:
            raise ValueError("demasiado profundo")
        payload = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return err(400, "E100", "json inválido")
    m = payload.get("m") if isinstance(payload, dict) else None
    if not isinstance(m, str):
        return err(400, "E102", "falta m")
    if ";" not in m:
        return err(400, "E103", "falta control")
    segments = m.split(";")
    if any(s == "" for s in segments):
        return err(400, "E104", "segmento vacío")

    cmd = ascii_upper(segments[0])
    if cmd == "PING":  # PING no valida el control, solo la aridad
        if len(segments) != 2:
            return err(400, "E302", "aridad inválida")
        return cmd_ping(st, [])

    ctl = segments[-1]
    if not CONTROL_RE.fullmatch(ctl):
        return err(400, "E201", "control mal formado")
    if ctl != str(control(";".join(segments[:-1]))):  # se compara como texto: "08" no es "8"
        return err(400, "E202", "control inválido")
    if cmd not in COMMANDS:
        sug = suggestion(cmd)
        return err(400, "E301", "comando desconocido ", **({"sugerencia": sug} if sug else {}))
    args = segments[1:-1]
    if len(args) != COMMANDS[cmd]:
        return err(400, "E302", "aridad inválida")
    return HANDLERS[cmd](st, args)


def _reject_constant(name):
    raise ValueError(name)  # JSON.parse no acepta NaN ni Infinity


# --- HTTP ---------------------------------------------------------------------

ROUTES = {("GET", "/health"), ("POST", "/msg"), ("POST", "/__reset")}
# Métodos que acepta el parser HTTP del original (Node): el resto, incluidos los que vienen en
# minúsculas, se rechaza con 400 sin cuerpo antes de llegar a las rutas.
NODE_METHODS = {
    "ACL", "BIND", "CHECKOUT", "COPY", "DELETE", "GET", "HEAD", "LINK", "LOCK", "M-SEARCH", "MERGE",
    "MKACTIVITY", "MKCALENDAR", "MKCOL", "MOVE", "NOTIFY", "OPTIONS", "PATCH", "POST", "PROPFIND", "PROPPATCH",
    "PURGE", "PUT", "QUERY", "REBIND", "REPORT", "SEARCH", "SOURCE", "SUBSCRIBE", "TRACE", "UNBIND", "UNLINK",
    "UNLOCK", "UNSUBSCRIBE",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "caja-negra"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body):
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _read_body(self):
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            return self._read_chunked()
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _read_chunked(self):
        data = bytearray()
        while True:
            size = int(self.rfile.readline().split(b";", 1)[0].strip() or b"0", 16)
            if size == 0:
                while self.rfile.readline().strip():  # trailers hasta la línea vacía
                    pass
                return bytes(data)
            data += self.rfile.read(size)
            self.rfile.readline()  # CRLF al final de cada trozo

    def _dispatch(self):
        # Ruta tal como llegó: http.server colapsa "//msg" a "/msg" en self.path, el original no.
        raw_target = self.requestline.split(" ")[1] if self.requestline.count(" ") >= 2 else self.path
        path = raw_target.split("?", 1)[0]
        body = self._read_body()
        if (self.command, path) not in ROUTES:
            return self._send(*err(404, "E404", "ruta desconocida"))
        if (self.headers.get("Authorization") or "").strip() != f"Bearer {TEAM_TOKEN}" or not TEAM_TOKEN:
            return self._send(*err(401, "E001", "no autorizado"))
        with LOCK:
            if path == "/health":
                return self._send(200, {"ok": True})
            if path == "/__reset":
                STATE.reset()
                return self._send(200, {"ok": True})
            if STATE.halted:
                return self._send(*err(503, "E599", "service halted"))
            if len(body) > MAX_BODY_BYTES:
                return self._send(*err(413, "E101", "cuerpo demasiado grande"))
            return self._send(*handle_message(STATE, body))

    def _bad_method(self, status=400):
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _dispatch

    def __getattr__(self, name):
        # http.server busca do_<MÉTODO>; sin esto respondería 501 con una página HTML.
        if name == "do_CONNECT":  # el proxy delante del original responde 405 vacío
            return lambda: self._bad_method(405)
        if name.startswith("do_"):
            return self._dispatch if name[3:] in NODE_METHODS else self._bad_method
        raise AttributeError(name)


if __name__ == "__main__":
    if not TEAM_TOKEN:
        print("ADVERTENCIA: TEAM_TOKEN vacío; todas las llamadas responderán 401")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
