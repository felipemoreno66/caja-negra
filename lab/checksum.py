"""Dígito de control del servicio (hipótesis confirmada con el oráculo).
Letras -> posición en el alfabeto (A=1..Z=26, sin distinguir mayúsculas), dígitos tal cual,
el resto se ignora. Se concatena como número N y control = 98 - (N*100 mod 97)."""


def control(body: str) -> int:
    n = 0  # N mod 97, dígito a dígito (N puede tener miles de dígitos)
    for ch in body.upper():
        if "A" <= ch <= "Z":
            digits = str(ord(ch) - 64)
        elif "0" <= ch <= "9":
            digits = ch
        else:
            continue
        for d in digits:
            n = (n * 10 + int(d)) % 97
    return 98 - (n * 100) % 97


def sign(body: str) -> str:
    return f"{body};{control(body)}"
