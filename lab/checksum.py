"""Dígito de control del servicio (hipótesis confirmada con el oráculo).
Letras -> posición en el alfabeto (A=1..Z=26, sin distinguir mayúsculas), dígitos tal cual,
el resto se ignora. Se concatena como número N y control = 98 - (N*100 mod 97)."""


def control(body: str) -> int:
    digits = []
    for ch in body.upper():
        if "A" <= ch <= "Z":
            digits.append(str(ord(ch) - 64))
        elif ch.isdigit():
            digits.append(ch)
    n = int("".join(digits) or "0")
    return 98 - (n * 100) % 97


def sign(body: str) -> str:
    return f"{body};{control(body)}"
