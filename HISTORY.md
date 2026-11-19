# Historial

## [Sin publicar]

### Cambiado (guarda, auditoría 2026-11-19)

- `sentinel`: el matcher del hook pasa a `Write|Edit|NotebookEdit|Bash`. En `tests-only`,
  el Bash es estricto: sólo comandos simples y escrituras a rutas de pruebas o temporales.
  Tras 6 rondas de revisión (auditor y shield) y 186 pruebas; se documentan los huecos
  confirmados que quedan.
- `tests-only` Write/Edit: una ruta absoluta fuera de `cwd` (o sin `cwd`) sólo vale si es
  temporal; se excluyen `.git`, `.github`, `.claude`, `.vscode`, `.idea`, `.husky`,
  `.venv`, `venv`, `site-packages` y `node_modules`.
- `readonly`: sólo endurecimientos (`builtin`, `cp -l`/`-s`, `find -fprint`, `env`/`sudo`
  con `--chdir`, `git -c`, `hash -p`, `tar`/`unzip`/`7z`, `shred`/`rsync`/`scp`, llaves y
  barras invertidas en rutas). `mktemp` y `tar -O` se permiten con `--allow-temp`.
- El parser emula a bash para `\x` y `$"..."`.

### Cambiado (marca)

- Dirección visual: «Stepped S» se descarta y rige «Modular Grid System» (cuatro bloques en
  rejilla de 8 × 8 u, uno de ellos en acento). Marca aprobada el 2026-11-19.
- Wordmark: «SyncLayer», una palabra, IBM Plex Sans 600; recomendado, sin confirmar.
- Paleta light: `surface-2` `#EAEFF3` y texto blanco sobre el acento, supuestos sin medir.
- Sin cambios: lema, voz, tipografía y el resto de la paleta.
- Pendientes: SVG finales, wordmark convertido a trazados y cuestionar el acento.

### Añadido

- `docs/brand/`: estrategia de marca, voz y tono, e identidad visual (paleta dark/light con
  contrastes medidos, tipografía IBM Plex). Sin assets finales todavía.
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
