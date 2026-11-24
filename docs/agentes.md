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
| Copias previas | `install.ps1` respalda lo que sobrescribe en `<Target>-backup-<fecha-hora>` (o en el `-BackupDir` que pases; por defecto `~/.claude-backup-<fecha-hora>`); no toca `CLAUDE.md` ni `settings.json`, así que respaldalos vos si los vas a editar |
| `~/.claude/synclayer-manifest.json` | Estado que deja `install.ps1` tras la última instalación correcta: por archivo, el hash del origen, el de lo escrito y el nivel y, con alias, la ruta de destino (`dest`, esquema 3) |
| `~/.claude/synclayer-config.json` | Opcional. Lo escribís vos a mano (campos `level`, de 1 a 5, y `aliases`). No lo instala ni lo gestiona `install.ps1`: sólo lo lee. Al reinstalar, el instalador aplica el nivel y los alias (ver «Niveles» y «Alias» en el `README.md`) |
| `~/.claude/synclayer-usage.md` | Reporte global de uso de subagentes. No lo instala `install.ps1`: lo genera `tools/usage_report.py global` (ver «Reporte de uso») |

Cómo instalar y actualizar: `install.ps1`, con `-DryRun` primero. Uso y límites en la sección
«Instalación» del `README.md` del repositorio.

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

La columna de modelo es la del nivel 5 (el repositorio tal cual); con los niveles 1 a 4 el modelo real de seis agentes puede ser otro: ver `synclayer-config.json`.

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

## Reporte de uso

Para ver cuánto se usa cada agente hay un reporte generado a partir de las transcripciones
locales. La herramienta (`tools/usage_report.py`) no se instala en `~/.claude`: se corre desde el
clon del repositorio, a mano.

```
python -B tools/usage_report.py project --project-dir <carpeta-del-proyecto>
python -B tools/usage_report.py global
```

- `project` escribe `<carpeta-del-proyecto>/.synclayer/usage-report.md` (la carpeta se ignora sola
  en git). `global` escribe `~/.claude/synclayer-usage.md`, privado por defecto: revisalo antes de
  compartirlo. Con `--stdout` imprimen el reporte y no escriben nada.
- Por defecto cubre los últimos 30 días (UTC); `--since`, `--until` y `--all` cambian la ventana.
- Compara llamadas, tokens por llamada, duración y herramientas. No mide la calidad del resultado,
  ni el costo real, ni afirma ahorro de tokens.
- Parámetros, códigos de salida y límites: `README.md` del repositorio («Reporte de uso» y
  «Límites del reporte de uso»).
- Un agente con alias (ver «Cambiar el nombre de un agente») sale como `(otro agente)` y deja de
  atribuirse a SyncLayer: el reporte reconoce a los agentes por su nombre original.

## Mantenimiento

**Cambiar el modelo de un agente.** Para `atlas`, `forge`, `sentinel`, `scribe`, `scout` y `oracle`,
la vía preferida es el nivel de `synclayer-config.json`: el instalador escribe su `model:` y su
`effort:` al reinstalar (ver «Niveles» en el `README.md`; el efecto real de `effort:` en Claude Code
no está verificado en una máquina real). Para cualquier agente también podés editar a mano la línea
`model:` de su archivo. Valores: `haiku`, `sonnet`, `opus`, `fable`, un ID completo de modelo, o
`inherit` (usa el de la sesión). Los alias apuntan siempre a la versión vigente de cada familia. Una
edición a mano de `model:` o `effort:` sale `MODIFICADO` (exit 3) la próxima vez que reinstalés, y
hace falta `-Force` (con respaldo).

**Cambiar el nombre de un agente.** Cada uno de los nueve puede llevar un alias. Agregá en
`~/.claude/synclayer-config.json` la clave `aliases`, un objeto de `<rol>` a `<alias>` (el `<rol>` es el
nombre original del agente, el del repositorio; ver «Alias» del `README.md`, en minúsculas): `{ "aliases": { "<rol>": "<alias>" } }`. Al reinstalar, el
instalador escribe ese agente en `agents/<alias>.md` con `name: <alias>` y cambia el nombre por el alias
en las descripciones, en los cuerpos y en las dos copias de texto que instala (las reglas y esta guía). El
repositorio conserva los nombres originales.

- **Formato del alias.** Minúsculas, empieza por letra, sólo `a-z`, `0-9`, `_` y `-`, hasta 64
  caracteres. No puede ser el nombre de un agente integrado de Claude Code, el de otro agente de
  SyncLayer, repetirse, contener el nombre de un agente de SyncLayer como palabra ni ser una palabra
  que YAML no lee como texto. El instalador valida la tabla entera antes de escribir (exit 1, también
  con `-DryRun`). Las reglas completas están en la sección «Alias» del `README.md`.
- **Ensayá primero.** `-DryRun` muestra una línea `Alias:` por alias y qué archivo cambia. Para
  cambiar o quitar un alias, editá el archivo y reinstalá.
- **El archivo anterior queda.** El instalador nunca borra: si ya existía `agents/<nombre-anterior>.md`,
  sale como `HUERFANO` y, mientras exista, hay dos agentes activos con descripciones casi iguales.
  Quitalo a mano.
- **Reiniciá las sesiones abiertas.** Renombrar con sesiones abiertas no está documentado.
- **Qué no cambia.** El hook `agent_guard.py` no se transforma, y el bloque `hooks:` de los agentes
  que lo usan queda igual. Tus referencias propias por nombre (`Agent(<nombre>)` en `tools:`,
  `permissions.deny`, matchers de hooks, `--agent`, un `.claude/agents/<nombre>.md` de proyecto, y las
  instrucciones en texto libre que nombren un agente: un `CLAUDE.md` propio, la memoria, reglas)
  siguen apuntando al nombre anterior y no se actualizan solas; el instalador no las toca.
- **Un agente tuyo con el mismo `name:`.** Si otro archivo de `~/.claude/agents/` declara el mismo
  `name:` que un alias, no está documentado cuál de los dos gana, y el agente renombrado podría
  quedar sin su guarda. El instalador no lo detecta; elegí un alias que no uses.
- **Copia inversa.** Con alias los archivos de `~/.claude` no son los del repositorio: el cambio se
  hace en el repositorio y se reinstala.
- **No verificado.** El efecto de los alias en un Claude Code real (invocar al agente por su alias,
  nombres con `_` o `-`, el caso de dos archivos con el mismo `name:`) lo tiene que comprobar el
  propietario; no está probado.

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
- `CLAUDE_CODE_EFFORT_LEVEL`: tiene prioridad sobre el `effort:` de los agentes.
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

1. Tocá sólo los doce archivos que lista `~/.claude/synclayer-manifest.json`:
   `agents/<los nueve>.md`, `rules/agentes.md`, `hooks/agent_guard.py` y
   `docs/agentes.md`. No borres `~/.claude/agents/` entero: es la carpeta estándar de
   todos los agentes de usuario y puede tener archivos que no son de SyncLayer y que no
   están en ningún respaldo (`install.ps1` sólo respalda lo que sobrescribe).
   - Los que el instalador creó como `NUEVO` (salen en su salida como `NUEVO  ruta`): borralos. Lo que está en la lista y no está en el respaldo fue `NUEVO` o `IGUAL`: si no guardaste la salida, comparalo con tu copia antes de borrar.
   - Los que sobrescribió: restauralos desde la carpeta de respaldo (`-BackupDir`). Si hubo un exit 4 y repetiste la instalación, hay dos carpetas de respaldo: para cada archivo usá el respaldo más antiguo, que tiene el original.
   - `~/.claude/synclayer-manifest.json`: si el instalador reescribió un estado previo,
     restaurá ese estado desde el respaldo. Borralo sólo si no existía antes (primera
     instalación): si no, lo restaurado saldría `MODIFICADO` y exigiría `-Force`. Si había un estado ilegible o inválido (no se respalda) o no hay estado porque la primera instalación terminó en exit 4, borralo también: los archivos restaurados saldrán `MODIFICADO` de todos modos y se reinstalan con `-Force`.
   - Con alias, cada agente vive en `agents/<alias>.md` y el estado lo lista en `dest` (esquema 3), no en
     `path`: usá `dest` para saber qué borrar o restaurar. Los `agents/<alias-anterior>.md` de un nombre
     anterior (`HUERFANO`) ya no figuran en el estado tras reescribirlo: quitalos a mano.
   - Si conservás los agentes, quitá antes el bloque `hooks:` del frontmatter de
     `sentinel`, `auditor`, `shield` y `debugger`.
2. Restaurar la copia previa de `CLAUDE.md` sobre `~/.claude/CLAUDE.md`, o quitar de
   él la referencia a `~/.claude/rules/agentes.md`.
3. Restaurar la copia previa de `settings.json` sobre `~/.claude/settings.json`, si
   se había modificado.
