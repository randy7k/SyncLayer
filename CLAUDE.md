# CLAUDE.md

Guía para trabajar dentro de este repositorio. Qué es y cómo se instala: `README.md`.

## Comandos

```
python -B -m unittest discover -s tests
```

Sólo biblioteca estándar, Python 3.12. Corre siempre Python con `-B` para no generar
`__pycache__`.

Probar la guarda a mano con un payload JSON por stdin (el código de salida es 0 o 2;
el motivo del bloqueo sale por stderr). Construye el payload con Python, no con
comillas a mano:

```
python -B -c "import json; print(json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git add .'}, 'cwd': '.'}))" | python -B hooks/agent_guard.py readonly --allow-temp
```

En Windows con Git Bash, las barras invertidas dentro de un JSON escrito a mano se
rompen con facilidad al citar; por eso conviene generarlo con `json.dumps`.

## Arquitectura

Tres piezas, de la más abstracta a la más concreta:

1. `agents/*.md`: un archivo por agente (nueve). Frontmatter + prompt.
2. `rules/agentes.md`: reglas de orquestación. Forma de estrella: sólo la sesión
   principal delega y pregunta al usuario; los agentes no se delegan entre sí.
3. `hooks/agent_guard.py`: guarda `PreToolUse`, enlazada desde el frontmatter
   (`hooks:`) de `sentinel` (modo `tests-only`) y de `auditor`, `shield` y `debugger`
   (modo `readonly --allow-temp`).

`docs/agentes.md` es la guía humana. `docs/brand/` define la marca (estrategia, voz, identidad
visual); el copy oficial va en inglés y no declara capacidades que el repositorio no tenga.

Claude Code lee los archivos vivos de `~/.claude/` (`agents/`, `rules/agentes.md`,
`hooks/agent_guard.py`, `docs/agentes.md`). Este repositorio es la copia versionada:
editar uno no actualiza el otro. `tests/` sólo existe aquí.

## Convenciones

- Los prompts de los agentes van en inglés; los reportes que producen, en español.
- Campos de frontmatter usados: `name`, `description`, `tools`, `model`, `color`,
  `hooks` (sólo los cuatro agentes con guarda) y `omitClaudeMd` (en `oracle` y `scout`).
- Un agente por archivo.
- Todo cambio en `hooks/agent_guard.py` empieza con una prueba que falla en
  `tests/test_agent_guard.py`.
- Ejecuta Python con `-B`. No se versiona `__pycache__`.
- Nada personal en el repositorio (nombres, correos, rutas internas): es público. Usa
  `~` para la carpeta personal.

## Comportamientos no obvios

- Contrato de salida del hook: sólo 0 (permitir) o 2 (bloquear). Claude Code trata
  cualquier otro código como error no bloqueante y deja pasar la llamada, por eso el
  script nunca sale con otro valor.
- Falla cerrado: entrada inválida, modo desconocido, error interno (incluidos
  `RecursionError` y `MemoryError`) y comandos de más de 100 000 caracteres dan exit 2.
- Si `python` no está en el PATH del shell que lanza el hook, el shell sale con 127 y
  la llamada pasa (falla abierto); igual si resuelve al alias de la Microsoft Store.
  No se puede arreglar desde el script.
- `sentinel` sólo tiene guarda en `Write|Edit|NotebookEdit`: su `Bash` queda libre. No
  documentes «sólo escribe tests» como garantía.
- Es una heurística, no un sandbox: `python -c`, `node -e`, `bash -c`, `eval`,
  `xargs rm`, `cmd /c` y `python -m venv` son brechas aceptadas.
- `atlas` está fijado a `model: claude-fable-5-2` porque el alias `fable` resolvía a
  Fable 5.1 con Claude Code 2.1.310. El CLI avisa `unrecognized_model`, pero la API
  lo acepta.
- Los frontmatter apuntan a `$HOME/.claude/hooks/agent_guard.py`, no a este repo: tras
  editar `hooks/agent_guard.py` hay que reinstalar la copia en `~/.claude/hooks/`.
- En `tests-only`, los directorios de pruebas se evalúan sobre la ruta relativa al
  `cwd` del payload. Fuera de `cwd`, o sin `cwd`, sólo cuenta el nombre del archivo.
- Las sesiones ya abiertas no ven agentes nuevos o modificados: reiniciarlas.

- Copia `~/.claude` -> repo sólo por archivo (`git ls-files`), nunca con comodines:
  `~/.claude/hooks/` y otras carpetas tienen archivos ajenos y el repo es público.

## Cierre de un cambio

En el mismo cambio se actualizan `README.md`, `CLAUDE.md` y `HISTORY.md`. Si cambia el
catálogo, la guía `docs/agentes.md` y el catálogo de `rules/agentes.md` también.
