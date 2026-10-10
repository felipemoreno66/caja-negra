"""Caracterización de los cambios de la versión 2 del original (desde ~15:51-15:56)."""
import sys
from client import send, reset, msg, set_seq, TOKEN
from checksum import control

def m(body, hip):
    r = msg(f"{body};{control(body)}", "v2: " + hip)
    print(f"  #{r['log_id']} {body:38} -> {r['status']} {r['text']}", flush=True)
    return r

def limite():
    print("== A. límite de transferencia (origen nuevo en cada prueba para no bloquear)")
    reset("v2-limite", hipotesis="v2: reset para buscar el nuevo límite de TRANSFER")
    m("ALTA;Destino", "cuenta destino AC-0001")
    n = [1]
    def probe(amount):
        n[0] += 1
        acc = f"AC-{n[0]:04d}"
        m(f"ALTA;Origen{n[0]}", "origen nuevo para no acumular rechazos")
        m(f"DEPOSITO;{acc};9999999999", "fondos de sobra")
        r = m(f"TRANSFER;{acc};AC-0001;{amount}", f"¿{amount} supera el nuevo límite?")
        return r["status"] == 200
    lo, hi = 40000, 100000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if probe(mid): lo = mid
        else: hi = mid
    print(f"  => máximo permitido {lo}, primer rechazado {hi}")
    return lo

def bloqueo(lim):
    over = lim + 1
    print("== B1. qué afecta el bloqueo y cómo cuenta intentos")
    reset("v2-bloqueo-1", hipotesis="v2: reset, alcance del bloqueo")
    for b in ["ALTA;A", "ALTA;B", "DEPOSITO;AC-0001;500000", "DEPOSITO;AC-0002;500000"]:
        m(b, "preparación")
    for i in range(3):
        m(f"TRANSFER;AC-0001;AC-0002;{over}", f"rechazo por límite {i+1} de 3")
    m("TRANSFER;AC-0001;AC-0002;100", "transferencia válida tras 3 rechazos: ¿bloqueada?")
    m("TRANSFER;AC-0001;AC-0002;100", "segundo intento: ¿intentos 2?")
    m("DEPOSITO;AC-0001;100", "¿se puede depositar en una cuenta bloqueada?")
    m("CONSULTA;AC-0001", "¿se puede consultar una cuenta bloqueada? ¿cambió el saldo?")
    m("TRANSFER;AC-0002;AC-0001;100", "¿se puede transferir HACIA una cuenta bloqueada?")
    m("ANULA;OP-0003", "¿se puede anular una operación de la cuenta bloqueada?")
    m("TRANSFER;AC-0001;AC-0002;100", "tras otras operaciones: ¿intentos sigue subiendo (3)?")
    print("== B2. orden de E510 frente a otros errores (cuenta A bloqueada)")
    m(f"TRANSFER;AC-0001;AC-0002;{over}", "bloqueada y sobre el límite: ¿E510 o E506?")
    m("TRANSFER;AC-0001;AC-0002;0", "bloqueada y monto inválido: ¿E510 o E303?")
    m("TRANSFER;AC-0001;AC-0001;100", "bloqueada y misma cuenta: ¿E510 o E304?")
    m("TRANSFER;AC-0001;AC-0099;100", "bloqueada y destino inexistente: ¿E510 o E401?")
    m("TRANSFER;AC-0001;AC-0002;99999999", "bloqueada y saldo insuficiente/sobre límite: ¿E510?")
    m("TRANSFER;AC-0001;AC-0002;100", "¿qué intentos lleva ahora? (cuáles de los anteriores contaron)")

    print("== B3. ¿cuentan los rechazos por saldo insuficiente?")
    reset("v2-bloqueo-saldo", hipotesis="v2: reset, ¿E507 cuenta para el bloqueo?")
    for b in ["ALTA;A", "ALTA;B", "DEPOSITO;AC-0001;100"]:
        m(b, "preparación")
    for i in range(3):
        m("TRANSFER;AC-0001;AC-0002;500", f"saldo insuficiente {i+1} de 3")
    m("TRANSFER;AC-0001;AC-0002;50", "válida tras 3 E507: ¿bloqueada?")

    print("== B4. ¿cuentan monto inválido / destino inexistente?")
    reset("v2-bloqueo-otros", hipotesis="v2: reset, ¿E303 y E401 cuentan para el bloqueo?")
    for b in ["ALTA;A", "ALTA;B", "DEPOSITO;AC-0001;1000"]:
        m(b, "preparación")
    for b in ["TRANSFER;AC-0001;AC-0002;0", "TRANSFER;AC-0001;AC-0099;5", "TRANSFER;AC-0001;AC-0002;abc"]:
        m(b, "fallo que no es por límite")
    m("TRANSFER;AC-0001;AC-0002;50", "válida tras 3 fallos de otro tipo: ¿bloqueada?")

    print("== B5. ¿consecutivos o acumulados? ¿una transferencia válida reinicia la cuenta?")
    reset("v2-bloqueo-consecutivos", hipotesis="v2: reset, ¿los rechazos deben ser consecutivos?")
    for b in ["ALTA;A", "ALTA;B", "DEPOSITO;AC-0001;500000"]:
        m(b, "preparación")
    m(f"TRANSFER;AC-0001;AC-0002;{over}", "rechazo 1")
    m(f"TRANSFER;AC-0001;AC-0002;{over}", "rechazo 2")
    m("TRANSFER;AC-0001;AC-0002;100", "válida entre rechazos")
    m(f"TRANSFER;AC-0001;AC-0002;{over}", "rechazo 3 (no consecutivo)")
    m("TRANSFER;AC-0001;AC-0002;100", "¿bloqueada tras 3 rechazos no consecutivos?")
    m(f"TRANSFER;AC-0001;AC-0002;{over}", "rechazo 4")
    m("TRANSFER;AC-0001;AC-0002;100", "¿y ahora?")

    print("== B6. ¿el bloqueo es por cuenta de origen? ¿el reset lo quita?")
    reset("v2-bloqueo-origen", hipotesis="v2: reset, alcance por cuenta")
    for b in ["ALTA;A", "ALTA;B", "ALTA;C", "DEPOSITO;AC-0001;500000", "DEPOSITO;AC-0003;500000"]:
        m(b, "preparación")
    for i in range(3):
        m(f"TRANSFER;AC-0001;AC-0002;{over}", f"rechazo {i+1} desde A")
    m("TRANSFER;AC-0003;AC-0002;100", "C (no bloqueada) transfiere: ¿afectada?")
    m(f"TRANSFER;AC-0003;AC-0001;{over}", "C sobre el límite hacia A")
    reset("v2-bloqueo-reset", hipotesis="v2: ¿el reset quita el bloqueo?")
    for b in ["ALTA;A", "ALTA;B", "DEPOSITO;AC-0001;500000"]:
        m(b, "preparación")
    m("TRANSFER;AC-0001;AC-0002;100", "tras reset, la AC-0001 nueva no está bloqueada")

def saldo():
    print("== C. formato del saldo")
    reset("v2-saldo", hipotesis="v2: reset, formato del saldo")
    for b, h in [("ALTA;A", "cuenta"), ("CONSULTA;AC-0001", "saldo 0"), ("DEPOSITO;AC-0001;1", "1"),
                 ("CONSULTA;AC-0001", "¿0.01?"), ("DEPOSITO;AC-0001;9", "+9"), ("CONSULTA;AC-0001", "¿0.10?"),
                 ("DEPOSITO;AC-0001;9999999999", "máximo"), ("CONSULTA;AC-0001", "¿100000000.09?"),
                 ("ALTA;B", "cuenta B"), ("DEPOSITO;AC-0002;5", "5"), ("ANULA;OP-0004", "anular depósito de 5"),
                 ("ANULA;OP-0001", "anular el 1 de A"), ("CONSULTA;AC-0002", "¿0.00 o -0.00?"),
                 ("TRANSFER;AC-0001;AC-0002;7", "7 a B"), ("ANULA;OP-0005", "anular: B queda en -0.07?"),
                 ("DEPOSITO;AC-0002;2", "B en 2"), ("TRANSFER;AC-0002;AC-0001;2", "B a 0"), ("ANULA;OP-0006", "anula depósito: B -0.02?"),
                 ("CONSULTA;AC-0002", "¿-0.02?")]:
        m(b, h)

def auth():
    print("== D. autenticación (con el header correcto)")
    set_seq("v2-auth")
    for name, h in [("espacio final", f"Bearer {TOKEN} "), ("bearer minúscula", f"bearer {TOKEN}"), ("sin Bearer", TOKEN),
                    ("doble espacio", f"Bearer  {TOKEN}")]:
        r = send("GET", "/health", headers={"Authorization": h}, token=None, hipotesis=f"v2: auth {name} en health")
        print(f"  #{r['log_id']} auth {name:18} -> {r['status']} {r['text']}")

if __name__ == "__main__":
    lim = limite()
    bloqueo(lim)
    saldo()
    auth()
