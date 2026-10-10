"""Fuzzer diferencial: genera secuencias aleatorias parecidas a las del set oculto,
las manda al original (queda en el log) y al reemplazo, y muestra cada diferencia.

  REPLACEMENT_URL=http://localhost:8765 python3 lab/fuzz.py <semilla> <n_secuencias>
"""
import json, os, random, sys
from client import send, reset, msg
from checksum import control

REPL = os.environ.get("REPLACEMENT_URL", "http://localhost:8765")
TEAM = os.environ["TEAM_TOKEN"]
NAMES = ["Lucia", "Mateo", "Ana", "Beto", "José", "Ñandú", "x", "Ana Maria", "123", "O'Brien"]
AMOUNTS = ["1", "50", "700", "999", "40000", "99999", "100000", "100001", "120000", "250000", "1000000",
           "0", "-5", "10.5", "007", "abc", "9999999999", "10000000000"]


class Gen:
    def __init__(self, rnd):
        self.r = rnd
        self.accounts = 0
        self.ops = 0

    def acc(self):
        r = self.r.random()
        if self.accounts and r < 0.8:
            return f"AC-{self.r.randint(1, self.accounts):04d}"
        return self.r.choice([f"AC-{self.accounts + 1:04d}", "AC-0009", "ac-0001", "AC-1", "XX-0001"])

    def op(self):
        if self.ops and self.r.random() < 0.8:
            return f"OP-{self.r.randint(1, self.ops):04d}"
        return self.r.choice([f"OP-{self.ops + 1:04d}", "OP-0099", "op-0001"])

    def body(self):
        r = self.r
        k = r.choices(["ALTA", "DEPOSITO", "TRANSFER", "CONSULTA", "ANULA", "PING", "HALT", "UNK"],
                      [18, 22, 24, 14, 10, 4, 3, 5])[0]
        if k == "ALTA":
            self.accounts += 1  # aproximado: solo guía la elección de ids
            return f"ALTA;{r.choice(NAMES)}"
        if k == "DEPOSITO":
            self.ops += 1
            return f"DEPOSITO;{self.acc()};{r.choice(AMOUNTS[:8] if r.random() < .8 else AMOUNTS)}"
        if k == "TRANSFER":
            self.ops += 1
            a = self.acc(); b = self.acc() if r.random() < .9 else a
            return f"TRANSFER;{a};{b};{r.choice(AMOUNTS[:10] if r.random() < .8 else AMOUNTS)}"
        if k == "CONSULTA":
            return f"CONSULTA;{self.acc()}"
        if k == "ANULA":
            return f"ANULA;{self.op()}"
        if k == "PING":
            return "PING"
        if k == "HALT":
            return f"HALT;{r.choice(['1', 'SI', 'X'])}"
        return r.choice(["SALDOS;AC-0001", "ALTAS;Ana", "consulta;AC-0001", "Deposito;AC-0001;5", "RETIRO;AC-0001;5", "TRANSFERIR;AC-0001;AC-0002;5"])

    def message(self):
        b = self.body()
        r = self.r.random()
        if b == "PING":
            return "PING;" + self.r.choice(["64", "1", "X"])
        if r < 0.82:
            return f"{b};{control(b)}"
        if r < 0.90:
            return f"{b};{(control(b) + self.r.randint(1, 96)) % 99}"  # control incorrecto
        if r < 0.94:
            return f"{b};{self.r.choice(['5X', '014', ''])}"
        if r < 0.97:
            return b.replace(";", ";;", 1)
        return b.lower() + f";{control(b)}"


def norm(r):
    return r["status"], (r["json"] if r["json"] is not None else r["text"])


def main(seed, n):
    rnd = random.Random(seed)
    diffs = 0
    for i in range(n):
        g = Gen(rnd)
        length = rnd.choices([1, rnd.randint(2, 5), rnd.randint(6, 12)], [40, 45, 15])[0]
        steps = [g.message() for _ in range(length)]
        name = f"fuzz-{seed}-{i}"
        reset(name, hipotesis="fuzzer diferencial: reset")
        send("POST", "/__reset", base=REPL, token=TEAM, log=False)
        for j, m in enumerate(steps):
            o = msg(m, f"fuzzer diferencial (semilla {seed}, secuencia {i}, paso {j}): ¿el reemplazo responde igual?")
            p = send("POST", "/msg", base=REPL, token=TEAM, json_body={"m": m}, log=False)
            if norm(o) != norm(p):
                diffs += 1
                print(f"DIFF {name} paso {j} log#{o['log_id']}: {m!r}")
                print(f"   original:  {o['status']} {o['text']}")
                print(f"   reemplazo: {p['status']} {p['text']}")
                print(f"   secuencia: {steps[:j+1]}", flush=True)
                break
    print(f"\nSecuencias: {n}, con diferencias: {diffs}")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
