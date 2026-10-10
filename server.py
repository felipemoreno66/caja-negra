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
TRANSFER_LIMIT = 100_000
MAX_BODY_BYTES = 8192
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
        self.accounts = {}  # "AC-0001" -> saldo
        self.ops = {}  # "OP-0001" -> dict
        self.next_account = 1
        self.next_op = 1

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
    return 200, {"cuenta_id": acc, "saldo": st.accounts[acc]}


def cmd_deposito(st, args):
    acc, monto = args
    if not AMOUNT_RE.fullmatch(monto):
        return err(400, "E303", "monto inválido")
    if acc not in st.accounts:
        return err(404, "E401", "cuenta inexistente")
    monto = int(monto)
    st.accounts[acc] += monto
    return 200, {"status": "recieved", "operacionId": st.new_op(tipo="deposito", cuenta=acc, monto=monto)}


def cmd_transfer(st, args):
    origen, destino, monto = args
    if not AMOUNT_RE.fullmatch(monto):
        return err(400, "E303", "monto inválido")
    if origen == destino:
        return err(400, "E304", "origen y destino iguales")
    if origen not in st.accounts or destino not in st.accounts:
        return err(404, "E401", "cuenta inexistente")
    monto = int(monto)
    if monto > TRANSFER_LIMIT:
        return err(422, "E506", "límite excedido")
    if st.accounts[origen] < monto:
        return err(422, "E507", "saldo insuficiente")
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


def handle_message(st, raw_body):
    """Procesa el cuerpo de POST /msg en el mismo orden de validación que el original."""
    try:
        # Los bytes UTF-8 inválidos se reemplazan por U+FFFD, como hace el original.
        payload = json.loads(raw_body.decode("utf-8", errors="replace"), parse_constant=_reject_constant)
    except ValueError:
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
    if int(ctl) != control(";".join(segments[:-1])):
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
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

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

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _dispatch


if __name__ == "__main__":
    if not TEAM_TOKEN:
        print("ADVERTENCIA: TEAM_TOKEN vacío; todas las llamadas responderán 401")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
