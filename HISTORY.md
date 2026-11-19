# Historial

## [Sin publicar]

### Añadido

- `docs/brand/`: estrategia de marca, voz y tono, e identidad visual (dirección «Stepped S»,
  paleta dark/light con contrastes medidos, tipografía IBM Plex). Sin assets finales todavía.
- Tagline: «One layer. Many specialists.» (reemplaza «One Layer. Multiple Intelligence.»).
- `README.md`: introducción de marca en inglés y enlace a `docs/brand/`.

### Corregido (documentación, auditoría 2026-11-19)

- Se documenta que `sentinel` no tiene guarda sobre `Bash` y que `auditor`, `shield` y
  `debugger` no son de solo lectura real.
- Se documentan los bypasses medidos de `readonly`.
- Se avisa del fallo abierto cuando `python` resuelve al alias de la Microsoft Store y se
  añade cómo comprobarlo.
- La copia `~/.claude` -> repo pasa a ser por archivo (`git ls-files`) para no traer
  archivos ajenos a un repo público.

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
