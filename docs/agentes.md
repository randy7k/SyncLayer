# Ecosistema de agentes — guía de uso y mantenimiento

Instalado el 2026-11-19 con Claude Code 2.1.310.

## Qué hay instalado

| Archivo | Contenido |
|---|---|
| `~/.claude/agents/*.md` | Los nueve agentes: `oracle`, `scout`, `atlas`, `forge`, `sentinel`, `auditor`, `shield`, `debugger`, `scribe` |
| `~/.claude/rules/agentes.md` | Reglas de orquestación. Se cargan en todos los proyectos |
| `~/.claude/hooks/agent_guard.py` | Hook de seguridad `PreToolUse` que usan `sentinel`, `auditor`, `shield` y `debugger` (ver «Límites conocidos») |
| `~/.claude/CLAUDE.md` | Instrucciones globales del usuario: deben apuntar a `~/.claude/rules/agentes.md` |
| `~/.claude/docs/agentes.md` | Esta guía |
| Copias previas | Respaldo de `CLAUDE.md` y `settings.json` antes de instalar, en la carpeta que elijas |

Si el plugin `superpowers` está habilitado, puede solaparse con este ecosistema en la
ejecución de planes. Deshabilitarlo es opcional.

## Catálogo

| Agente | Rol | Modelo | Herramientas |
|---|---|---|---|
| ORACLE | Analista de proyecto, sólo lectura | `haiku` | Read, Grep, Glob |
| SCOUT | Investigación en fuentes oficiales | `sonnet` | WebSearch, WebFetch, Read, Grep, Glob |
| ATLAS | Planificador y arquitecto | `claude-fable-5-2` | Read, Grep, Glob, Write |
| FORGE | Desarrollador | `sonnet` | Read, Edit, Write, Grep, Glob, Bash |
| SENTINEL | QA | `sonnet` | Read, Grep, Glob, Bash, Edit, Write |
| AUDITOR | Code review independiente | `opus` | Read, Grep, Glob, Bash |
| SHIELD | Seguridad | `opus` | Read, Grep, Glob, Bash |
| DEBUGGER | Causa raíz | `opus` | Read, Grep, Glob, Bash |
| SCRIBE | Documentación | `sonnet` | Read, Grep, Glob, Edit, Write |

Ningún agente tiene acceso a los conectores MCP (correo, Teams, SharePoint, etc.):
la lista `tools` de cada uno es explícita.

## Cómo se usan

- **Automático.** Claude delega según el tamaño de la tarea, con las reglas de
  `~/.claude/rules/agentes.md`. Las tareas triviales no usan agentes.
- **Por nombre.** «Usá a forge para…», o `@agent-forge` en el prompt.
- **Listar.** `/agents` dentro de Claude Code muestra los agentes registrados y de
  dónde viene cada uno.

## Flujos

| Tamaño | Flujo |
|---|---|
| Trivial | Sesión principal, sin agentes |
| Mediana | ORACLE (si hace falta) → FORGE → AUDITOR |
| Grande | ORACLE ∥ SCOUT → ATLAS → tu aprobación → por task: FORGE → AUDITOR → SENTINEL → SHIELD (si aplica) → SCRIBE → AUDITOR final |
| Bug sin causa clara | DEBUGGER → FORGE → SENTINEL |

### Ejemplo: exportar órdenes a CSV

1. ORACLE devuelve modelos, vistas y tests de órdenes con `archivo:línea`.
2. ATLAS escribe `docs/plans/AAAA-MM-DD-export-csv.md` con tres tasks y sus criterios
   de aceptación. Claude te lo presenta y esperás aprobarlo.
3. FORGE implementa la task 1; AUDITOR revisa su diff; FORGE corrige lo que aparezca.
   Se repite para las tasks 2 y 3.
4. SENTINEL corre la suite y agrega casos: CSV vacío, acentos, 10 000 filas.
5. SHIELD revisa permisos de la vista e inyección de fórmulas en el CSV.
6. SCRIBE actualiza `README.md`, `CLAUDE.md` y `HISTORY.md`.
7. AUDITOR revisa el cambio completo. Claude cierra con la evidencia de pruebas.

## Mantenimiento

**Cambiar el modelo de un agente.** Editá la línea `model:` de su archivo. Valores:
`haiku`, `sonnet`, `opus`, `fable`, un ID completo de modelo, o `inherit` (usa el de
la sesión). Los alias apuntan siempre a la versión vigente de cada familia.

**Cambiar herramientas.** Editá la línea `tools:`. Si se borra la línea, el agente
hereda todas las herramientas de la sesión, incluidos los conectores MCP.

**Cambiar cuándo interviene.** El campo `description` es lo que Claude lee para
decidir si delega. Las reglas generales están en `~/.claude/rules/agentes.md`.

**Adaptar un agente a un proyecto.** Creá `.claude/agents/<nombre>.md` dentro del
repo con el mismo `name`. Reemplaza al global sólo ahí. No copies los nueve.

**Agregar un agente.** Archivo nuevo en `~/.claude/agents/` con `name` y
`description` en el frontmatter, más una fila en el catálogo de las reglas y de esta
guía. Antes de agregarlo, comprobá que no se pueda resolver ampliando uno existente.

**Recarga.** Los cambios en archivos de agentes se toman en segundos. Los cambios en
`CLAUDE.md`, `rules/` y `settings.json` aplican a sesiones nuevas.

**Diagnóstico.** `/agents` para ver si está registrado; `/doctor` avisa de nombres
duplicados; `claude --debug` muestra campos de frontmatter no reconocidos.

## Variables de entorno que alteran los modelos

- `CLAUDE_CODE_SUBAGENT_MODEL`: modelo por defecto para agentes sin `model`.
- `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`: ignora el `model` de cada agente.
- `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS,FABLE}_MODEL`: cambian a qué apunta cada alias.

Si un agente no usa el modelo esperado, revisá estas variables primero.

## Límites conocidos

- **SENTINEL** tiene guarda en `Write`/`Edit`/`NotebookEdit` y en `Bash`. En `Bash` el modo
  `tests-only` es estricto: acepta sólo comandos simples (sin `$`, backticks, `\`,
  subshells, `[[`, heredocs ni varias líneas) y escribe sólo en rutas de pruebas o
  temporales. Escribe un comando simple por llamada, con rutas literales y `/`. Sigue
  siendo una lista negra: los huecos confirmados están en el `README.md`.
- AUDITOR, SHIELD y DEBUGGER no son de solo lectura real: corren tests y builds, que
  ejecutan código arbitrario, y el hook no limita lecturas (`.env`) ni red.
- «SENTINEL sólo escribe tests» (en sus herramientas de escritura) y «AUDITOR, SHIELD y
  DEBUGGER no modifican nada» (en comandos conocidos) los hace cumplir `~/.claude/hooks/agent_guard.py`, enlazado desde el frontmatter
  (`hooks:`) de esos cuatro agentes. Es una heurística contra escrituras accidentales,
  no un sandbox: un intérprete en una línea (`python -c`, `node -e`, `bash -c`, `eval`,
  `xargs rm`, `cmd /c`, `python -m venv`) todavía puede escribir archivos. Tampoco cubre
  `wget -o`/`-a` ni `curl -D`/`-c`/`--trace`.
- Si `python` no está en el PATH del shell que lanza el hook, el shell sale con 127 y
  Claude Code deja pasar la llamada (falla abierto). Lo mismo si `python` resuelve al
  alias de la Microsoft Store. Comprobá con `Get-Command python -All` que el primero sea
  un Python real y con `python -B -c "import sys; print(sys.version)"` que funcione.
- Los hooks del frontmatter de agentes de usuario corren sin el diálogo de confianza
  del espacio de trabajo.
- Si la sesión principal está en un modo de permisos amplio (aceptar ediciones, auto),
  ese modo también rige para los agentes.
- Cada agente arranca sin contexto y relee lo que necesita. El flujo «grande» consume
  varias veces más tokens que una sesión sola; por eso las tareas triviales no delegan.

## Cómo revertir

1. Borrar `~/.claude/agents/`, `~/.claude/rules/agentes.md` y
   `~/.claude/hooks/agent_guard.py`. Si se conservan los agentes, quitar antes el
   bloque `hooks:` del frontmatter de `sentinel`, `auditor`, `shield` y `debugger`.
2. Restaurar la copia previa de `CLAUDE.md` sobre `~/.claude/CLAUDE.md`, o quitar de
   él la referencia a `~/.claude/rules/agentes.md`.
3. Restaurar la copia previa de `settings.json` sobre `~/.claude/settings.json`, si
   se había modificado.
