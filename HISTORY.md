# Historial

## [Sin publicar]

Sin cambios pendientes.

## 2026-11-19 — Versión inicial

- Nueve agentes en `agents/`: `oracle`, `scout`, `atlas`, `forge`, `sentinel`,
  `auditor`, `shield`, `debugger`, `scribe`.
- Reglas de orquestación en `rules/agentes.md`.
- Guía de uso y mantenimiento en `docs/agentes.md`.
- Hook de seguridad `hooks/agent_guard.py` con 93 pruebas en
  `tests/test_agent_guard.py`. Modos `tests-only` (para `sentinel`) y `readonly
  --allow-temp` (para `auditor`, `shield` y `debugger`).
- `atlas` fijado a `claude-fable-5-2`.
- Tres rondas de revisión del hook por un agente revisor independiente: la primera
  encontró 12 hallazgos y la segunda 8; todos se corrigieron.
- Brechas conocidas del hook: `python -c`, `node -e`, `bash -c`, `eval`, `xargs rm`,
  `cmd /c`, `python -m venv`; sin cubrir `wget -o`/`-a` y `curl -D`/`-c`/`--trace`.
  Si `python` no está en el PATH, el hook falla abierto (exit 127).
