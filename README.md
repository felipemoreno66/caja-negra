# Reemplazo de la caja negra (Reto 2)

Reemplazo del servicio `caja-negra`, construido solo a partir de experimentos contra el original:
responde con el mismo status y el mismo cuerpo, errores incluidos, y nunca llama al original.
Implementa la **versión 2** del servicio, desplegada por el proveedor a las 15:51 (ver la sección 6 de la especificación).

- **Desplegado:** `https://web-production-05984.up.railway.app`
- **Resultado en el set oculto:** 82 → 95 → **97 / 100**
- **Especificación:** [`SPEC.pdf`](SPEC.pdf) (la misma en Markdown: [`SPEC.md`](SPEC.md)). Cada comportamiento cita la línea del log que lo prueba.
- **Log de experimentos:** [`lab/experimentos.jsonl`](lab/experimentos.jsonl), una línea por cada request al original con su hipótesis.

## Requisitos

Solo Python 3.10 o superior. No hay dependencias que instalar.

## 1. Correr el reemplazo

```bash
TEAM_TOKEN=mi-token PORT=8000 python3 server.py
```

```bash
curl -H "Authorization: Bearer mi-token" http://localhost:8000/health
curl -H "Authorization: Bearer mi-token" -H "Content-Type: application/json" -d '{"m":"PING;64"}' http://localhost:8000/msg
```

## 2. Comprobar que se comporta como el original

La regresión reproduce contra el reemplazo cada secuencia grabada en el log y compara status y cuerpo
igual que el evaluador (JSON sin importar el orden de las claves). No necesita acceso al original.

```bash
# Solo lo grabado contra la versión 2 (la vigente):
TEAM_TOKEN=mi-token REPLACEMENT_URL=http://localhost:8000 python3 lab/replay_log.py --desde 2026-10-10T20:51
# Todo el log, incluida la versión 1 (las diferencias esperadas son los cambios de la v2):
TEAM_TOKEN=mi-token REPLACEMENT_URL=http://localhost:8000 python3 lab/replay_log.py
```

## 3. El laboratorio (habla con el original)

Copia `lab/.env.example` como `lab/.env` y rellena la URL del original y los tokens. Todos los scripts
registran cada request en `lab/experimentos.jsonl`, con el token enmascarado.

| Script | Para qué sirve |
|---|---|
| `lab/client.py` | Cliente HTTP crudo y registro del log (`send`, `msg`, `reset`) |
| `lab/checksum.py` | Cálculo del dígito de control (mod 97, A=1…Z=26) |
| `lab/oracle.py` | Oráculo: encuentra el control válido de un mensaje probando valores |
| `lab/explore.py`, `lab/v2_caracterizar.py` | Experimentos dirigidos (v1 y versión 2) |
| `lab/scenarios.py` | Escenarios diferenciales: misma secuencia al original y al reemplazo |
| `lab/fuzz.py`, `lab/fuzz_agresivo.py` | Fuzzing diferencial: mutación de mensajes, cuerpo JSON, capa HTTP y secuencias |
| `lab/monitor.py` | Detector de cambios del original (`--seqs ejemplos-oficiales --loop 300`) |
| `lab/replay_log.py` | Regresión del reemplazo contra el log |

## Cómo está hecho el reemplazo

`server.py` es un único archivo con Python estándar (`http.server`), un solo proceso y el estado en memoria:

1. **HTTP:** ruta exacta → token → servicio detenido → tamaño del cuerpo (8 KB) → JSON (profundidad máxima 20).
2. **Integridad del mensaje** `COMANDO;args;control`: segmentos, formato y valor del dígito de control.
3. **Comandos:** cada uno en su función (`cmd_alta`, `cmd_transfer`…), con los errores en el mismo orden que el original.
4. **Estado:** cuentas, operaciones, bloqueos de la versión 2; `POST /__reset` lo devuelve al inicio.

## Despliegue

Railway con `python server.py`, la variable `TEAM_TOKEN` y **una sola réplica sin modo serverless**
(el estado vive en memoria). La configuración está en `railway.json`.
