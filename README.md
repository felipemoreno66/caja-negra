# Reemplazo de la caja negra (Reto 2)

Reemplazo del servicio `caja-negra`, construido solo a partir de experimentos contra el original.

- `server.py` — el reemplazo. Python estándar, sin dependencias, un solo proceso con estado en memoria.
- `lab/` — laboratorio: cliente que registra cada request al original (`experimentos.jsonl`),
  oráculo del dígito de control, scripts de exploración y la regresión `replay_log.py`.
- `design/` — doc de diseño y diagrama de arquitectura.

## Correr local

```bash
TEAM_TOKEN=<token> PORT=8000 python3 server.py
```

## Regresión contra el log de experimentos

```bash
TEAM_TOKEN=<token> REPLACEMENT_URL=http://localhost:8000 python3 lab/replay_log.py
```

## Despliegue

Railway: `python server.py`, variable `TEAM_TOKEN`, una sola réplica (el estado vive en memoria).
