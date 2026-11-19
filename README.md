# SyncLayer

Infraestructura global de agentes especializados para Claude Code.

Este repositorio es la copia versionada de un ecosistema de nueve subagentes de
Claude Code, sus reglas de orquestación y un hook de seguridad. Claude Code lee los
archivos vivos desde la carpeta personal (`~/.claude/`); este repositorio es la copia
que se versiona. Instalar es copiar estas carpetas dentro de `~/.claude/`.

La orquestación tiene forma de estrella: sólo la sesión principal decide a qué agente
llamar y le pregunta al usuario. Los agentes no se delegan trabajo entre sí y no
pueden hacer preguntas al usuario.

## Requisitos

- Claude Code (las verificaciones se hicieron con 2.1.310).
- Python 3.12 en el PATH del shell que lanza los hooks (lo necesita
  `hooks/agent_guard.py`; usa sólo la biblioteca estándar).

## Estructura

```
SyncLayer/
├── agents/            Un archivo por agente (frontmatter + prompt)
│   ├── oracle.md  scout.md  atlas.md  forge.md  sentinel.md
│   └── auditor.md  shield.md  debugger.md  scribe.md
├── rules/
│   └── agentes.md     Reglas de orquestación (se cargan en todos los proyectos)
├── hooks/
│   └── agent_guard.py Hook PreToolUse que limita lo que escriben los agentes
├── docs/
│   └── agentes.md     Guía de uso y mantenimiento
└── tests/
    └── test_agent_guard.py
```

## Instalación

Destino: `~/.claude/agents/`, `~/.claude/rules/`, `~/.claude/hooks/` y
`~/.claude/docs/`. Antes de copiar, respalda lo que ya exista en esas carpetas: la
copia sobrescribe archivos con el mismo nombre.

PowerShell, desde la raíz del repositorio:

```powershell
# Respaldo previo (ajusta la carpeta de destino si quieres otra)
$backup = "$HOME\.claude-backup-$(Get-Date -Format yyyyMMdd)"
New-Item -ItemType Directory -Force $backup | Out-Null
foreach ($d in 'agents','rules','hooks','docs') {
    if (Test-Path "$HOME\.claude\$d") { Copy-Item "$HOME\.claude\$d" $backup -Recurse -Force }
}

# Repositorio -> ~/.claude
foreach ($d in 'agents','rules','hooks','docs') {
    New-Item -ItemType Directory -Force "$HOME\.claude\$d" | Out-Null
    Copy-Item ".\$d\*" "$HOME\.claude\$d" -Recurse -Force
}
```

Después, las instrucciones globales del usuario (`~/.claude/CLAUDE.md`) deben apuntar
a las reglas. Las reglas de `~/.claude/rules/` se cargan en todos los proyectos. Ejemplo
de fragmento:

```markdown
## Ejecución de planes

Delega según el tamaño de la tarea con los agentes globales descritos en
`~/.claude/rules/agentes.md`.
```

Las sesiones que ya estaban abiertas al copiar no ven los agentes nuevos: reinícialas.

### Dos copias, sin sincronización automática

Editar los archivos vivos de `~/.claude/` no actualiza este repositorio, y editar el
repositorio no actualiza `~/.claude/`. Hay que copiar a mano en el sentido que
corresponda. Haz respaldo del destino antes de sobrescribir.

`~/.claude` -> repositorio: copia sólo los archivos de SyncLayer, nunca con comodines.
`~/.claude/agents/`, `hooks/` y `docs/` contienen archivos que no son de SyncLayer
(por ejemplo `hooks/caveman-statusline.ps1`); este repositorio es público y no deben
entrar. Desde la raíz del repositorio:

```powershell
foreach ($f in (git ls-files agents rules hooks docs)) {
    Copy-Item "$HOME\.claude\$f" ".\$f" -Force
}
git status   # revisa el diff antes de commitear
```

Repositorio -> `~/.claude`: el segundo bloque de la sección anterior. Ojo con
`tests/`: sólo existe en el repositorio.

## Uso

- **Automático.** Claude delega según el tamaño de la tarea, con las reglas de
  `rules/agentes.md`. Las tareas triviales no usan agentes.
- **Por nombre.** «Usa a forge para…», o `@agent-forge` en el prompt.
- **Listar.** `/agents` dentro de Claude Code muestra los agentes registrados.
- **Diagnóstico.** `claude --debug` muestra campos de frontmatter no reconocidos.

### Flujos por tamaño

| Tamaño | Flujo |
|---|---|
| Trivial | Sesión principal, sin agentes |
| Mediana | `oracle` (si el área es desconocida) -> `forge` -> `auditor` |
| Grande | `oracle` y `scout` (si hace falta) -> `atlas` -> aprobación del usuario -> por task: `forge` -> `auditor` -> al final: `sentinel` -> `shield` (si aplica) -> `scribe` -> `auditor` sobre el cambio completo |
| Bug sin causa clara | `debugger` -> `forge` -> `sentinel` |

Resumen de las reglas (detalle en [`rules/agentes.md`](rules/agentes.md)):

- En paralelo sólo corren agentes que no escriben (`oracle`, `scout`, `auditor`, `shield`).
- Un solo agente que escribe (`forge`, `sentinel`, `scribe`) a la vez por checkout.
- Precedencia ante conflictos: `shield` > `sentinel` > `auditor` > plan de `atlas` > `forge`.
- Una tarea está terminada cuando las pruebas relevantes se corrieron y pasaron, los
  criterios de aceptación están verificados, no quedan hallazgos Critical ni Important
  sin resolver y la documentación está al día.

## Catálogo

| Agente | Rol | Modelo | Herramientas |
|---|---|---|---|
| `oracle` | Analista de proyecto, sólo lectura | `haiku` | Read, Grep, Glob |
| `scout` | Investigación en fuentes oficiales | `sonnet` | WebSearch, WebFetch, Read, Grep, Glob |
| `atlas` | Planificador y arquitecto | `claude-fable-5-2` | Read, Grep, Glob, Write |
| `forge` | Desarrollador | `sonnet` | Read, Edit, Write, Grep, Glob, Bash |
| `sentinel` | QA | `sonnet` | Read, Grep, Glob, Bash, Edit, Write |
| `auditor` | Code review independiente | `opus` | Read, Grep, Glob, Bash |
| `shield` | Seguridad | `opus` | Read, Grep, Glob, Bash |
| `debugger` | Causa raíz | `opus` | Read, Grep, Glob, Bash |
| `scribe` | Documentación | `sonnet` | Read, Grep, Glob, Edit, Write |

Los alias (`haiku`, `sonnet`, `opus`) los resuelve Claude Code a la versión vigente de
cada familia. `atlas` va fijado al ID `claude-fable-5-2` porque, con Claude Code
2.1.310, el alias `fable` resolvía a Fable 5.1. Esa versión del CLI muestra un aviso
`unrecognized_model` para el ID fijado, pero la API lo acepta y la sesión corrió con
ese modelo.

Ningún agente tiene acceso a conectores MCP: la lista `tools` de cada uno es explícita.

## Hook de seguridad: `hooks/agent_guard.py`

Guarda `PreToolUse` enlazada desde el frontmatter (`hooks:`) de cuatro agentes:

| Agente | Matcher | Comando |
|---|---|---|
| `sentinel` | `Write\|Edit\|NotebookEdit` | `python "$HOME/.claude/hooks/agent_guard.py" tests-only` |
| `auditor`, `shield`, `debugger` | `Bash` | `python "$HOME/.claude/hooks/agent_guard.py" readonly --allow-temp` |

Contrato: lee un JSON por stdin (`tool_name`, `tool_input`, `cwd`). Sale con 0 para
permitir y con 2 para bloquear; en ese caso escribe el motivo, en español, por stderr.
Falla cerrado: entrada inválida, modo desconocido, cualquier error interno y comandos
de más de 100 000 caracteres terminan en bloqueo.

- `tests-only`: `Write`, `Edit` y `NotebookEdit` sólo pasan sobre artefactos de pruebas
  (carpetas de pruebas, `test_*.py`, `*.test.*`, `*.spec.*`, `conftest.py`, etc.). Las
  carpetas se evalúan sobre la ruta relativa al `cwd` del payload.
- `readonly`: bloquea git que modifica, comandos que modifican archivos, editores
  in situ, instalación de paquetes y redirección de salida a archivos.
  `--allow-temp` permite escribir sólo bajo directorios temporales.

### Límites

Es una heurística contra escrituras accidentales, **no un sandbox**.

- **`sentinel` solo está guardado en `Write`/`Edit`/`NotebookEdit`.** Su `Bash` no tiene
  guarda: con `sed -i`, `echo > archivo` o `python -c` puede modificar código de
  producción. «Solo escribe tests» ahí es una instrucción de su prompt, no algo que el
  hook imponga.
- `auditor`, `shield` y `debugger` no son de solo lectura real: deben correr tests y
  builds, y eso ejecuta código arbitrario. Tampoco hay restricción de lectura (`.env`)
  ni de red (`curl -d @archivo URL`).
- El modo `readonly` es una lista negra. Pasan, entre otros: `python script.py`,
  `$(echo rm) x`, `c=rm; $c x`, `builtin rm`, `busybox rm`, `find -fprint`/`-fls`,
  `sed 'w f'`, `awk` con redirección interna, `git -c core.pager=...`,
  `git log --ext-diff`, `tar -x`, `unzip`, `7z x`, `shred`, `rsync`, `scp`, `mklink`,
  `docker run`, `ssh`, `iex`, y `sqlite3`/`psql`/`mysql` con `DROP`.
- Brechas conocidas y aceptadas: `python -c`, `node -e`, `bash -c`, `eval`, `xargs rm`,
  `cmd /c`, `python -m venv`. Tampoco cubre `wget -o`/`-a` ni `curl -D`/`-c`/`--trace`.
- Si `python` no está en el PATH del shell que lanza el hook, el shell sale con 127 y
  Claude Code deja pasar la llamada (falla abierto). Lo mismo si `python` resuelve al
  alias de la Microsoft Store (`...\WindowsApps\python.exe`). Comprueba antes de
  confiar en la guarda:

  ```powershell
  Get-Command python -All | Select-Object Source   # el primero debe ser un Python real
  python -B -c "import sys; print(sys.version)"     # debe imprimir la versión, no un aviso
  ```
- Los hooks del frontmatter de agentes de usuario corren sin el diálogo de confianza
  del espacio de trabajo.

## Pruebas

```
python -B -m unittest discover -s tests
```

93 pruebas, sólo biblioteca estándar, Python 3.12. Además se verificó en sesiones
reales: `git add` bloqueado para `auditor`; `Write` sobre `src/` bloqueado y sobre
`tests/` permitido para `sentinel`.

## Mantenimiento

Resumen; la guía completa está en [`docs/agentes.md`](docs/agentes.md).

- **Cambiar el modelo:** línea `model:` del archivo del agente.
- **Cambiar herramientas:** línea `tools:`. Sin ella, el agente hereda todas, incluidos
  los conectores MCP.
- **Adaptar a un proyecto:** `.claude/agents/<nombre>.md` dentro del repo del proyecto
  reemplaza al agente global del mismo nombre sólo allí.
- **Agregar un agente:** archivo nuevo en `agents/` con `name` y `description`, y una
  fila en el catálogo de `rules/agentes.md` y de `docs/agentes.md`.
- **Variables de entorno que alteran los modelos:** `CLAUDE_CODE_SUBAGENT_MODEL`,
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, `ANTHROPIC_DEFAULT_*_MODEL`.
- Tras cambiar `hooks/agent_guard.py`, vuelve a instalarlo en `~/.claude/hooks/`.

## Licencia

Sin licencia definida todavía.
