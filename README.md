<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/banner-dark.svg">
  <img src="assets/brand/banner-light.svg" alt="SyncLayer">
</picture>

# SyncLayer

**One layer. Many specialists.**

SyncLayer is a versioned layer of nine specialist agents, orchestration rules and a guard hook for Claude Code. One session orchestrates; agents never delegate to each other. The guard is a heuristic, not a sandbox, and this repository documents exactly where it stops.

Infraestructura global de agentes especializados para Claude Code. Identidad y voz del proyecto: [`docs/brand/`](docs/brand/brand-strategy.md).

Este repositorio es la copia versionada de un ecosistema de nueve subagentes de
Claude Code, sus reglas de orquestación y un hook de seguridad. Claude Code lee los
archivos vivos desde la carpeta personal (`~/.claude/`); este repositorio es la copia
que se versiona. Se instala con `install.ps1`, que copia doce archivos dentro de
`~/.claude/` (ver «Instalación»).

La orquestación tiene forma de estrella: sólo la sesión principal decide a qué agente
llamar y le pregunta al usuario. Los agentes no se delegan trabajo entre sí y no
pueden hacer preguntas al usuario.

## Requisitos

- Claude Code (las verificaciones se hicieron con 2.1.310).
- Python 3.12 en el PATH del shell que lanza los hooks (lo necesita
  `hooks/agent_guard.py`; usa sólo la biblioteca estándar).
- Para instalar: Windows PowerShell 5.1. Es el único entorno verificado (ver «Límites del
  instalador»).

## Estructura

```
SyncLayer/
├── install.ps1        Instalador (Windows PowerShell 5.1)
├── install-manifest.json  Manifiesto: los doce archivos que se instalan y su hash
├── tools/
│   └── build_manifest.py  Genera y comprueba el manifiesto
├── agents/            Un archivo por agente (frontmatter + prompt)
│   ├── oracle.md  scout.md  atlas.md  forge.md  sentinel.md
│   └── auditor.md  shield.md  debugger.md  scribe.md
├── rules/
│   └── agentes.md     Reglas de orquestación (se cargan en todos los proyectos)
├── hooks/
│   └── agent_guard.py Hook PreToolUse que limita lo que escriben los agentes
├── assets/
│   └── brand/         SVG de marca (símbolo, wordmark, lockups, favicon, banner,
│       │              catálogo, estrella, slides, hoja de marca), PNG/ICO exportados
│       │              y generadores
│       └── src/       build_brand.py, build_round2.py, build_round3.py, brandlib.py,
│                          fonts_util.py, agents_data.py, ico.py, export_social_png.py,
│                          export_favicons.py
├── docs/
│   ├── agentes.md     Guía de uso y mantenimiento
│   ├── brand/         Estrategia, voz e identidad visual del proyecto
│   └── plans/         Planes de implementación y backlog
└── tests/
    ├── test_agent_guard.py
    ├── test_brand_agents.py
    ├── test_ico.py
    ├── test_install.py
    └── test_manifest.py
```

## Assets de marca

`assets/brand/` guarda los SVG finales (con variantes dark, light y monocromas) y los
scripts que los generan. Los SVG se regeneran, no se editan a mano; cómo, en
[`CLAUDE.md`](CLAUDE.md). Reglas de uso y de tamaño mínimo:
[`docs/brand/visual-identity.md`](docs/brand/visual-identity.md).

Contenido de `assets/brand/`:

- Símbolo `symbol-*` y variante de 16 px `symbol-16-*`; wordmark `wordmark-*`; lockups
  `lockup-horizontal-*` y `lockup-stacked-*` (cada uno en dark, light, mono y mono-reverse).
- Favicon: `favicon.svg` (un solo archivo; cambia de colores con `prefers-color-scheme`),
  `favicon-16.png`, `favicon-32.png`, `favicon-48.png`, `favicon.ico` (PNG de 16, 32 y 48 px
  embebidos) y `apple-touch-icon.png` (180×180). Los PNG llevan el símbolo dark sobre un
  fondo `bg` opaco (con 8 px de margen a 32 y 48 px; el de 16 px no tiene margen). El repositorio no tiene sitio web: estos archivos están listos para usarse
  si algún día lo hay, pero hoy no se enlazan desde ningún sitio.
- `banner-*`, `social-preview` (SVG y PNG), `agent-catalog-*`, `architecture-star-*` y tres
  slides.
- `brand-sheet-{dark,light}.svg` (1600×1131): hoja de marca de una página con símbolo, lockup,
  paleta, tipografía y reglas de uso.

**Social preview.** GitHub no permite subirla desde un commit: carga
`assets/brand/social-preview.png` (1280×640) a mano en el repositorio, en
Settings > Social preview.

## Instalación

`install.ps1` copia a `~/.claude/` doce archivos, los que lista `install-manifest.json`:
los nueve `agents/*.md`, `rules/agentes.md`, `hooks/agent_guard.py` y `docs/agentes.md`.
No instala `docs/brand/`, `assets/`, `tests/` ni `tools/`. Sólo escribe esos doce
destinos, sus temporales, el archivo de estado y el respaldo; no borra nada y no toca
archivos ajenos (`hooks/caveman-statusline.ps1`, `settings.json`, `CLAUDE.md`...).
Escribe los archivos con finales de línea LF, vengan del árbol de trabajo con CRLF o con LF.

Instálalo sólo desde un clon cuyo commit hayas revisado (ver «Límites del instalador»). Desde la raíz del repositorio, en Windows PowerShell 5.1:

```powershell
# 1. Ensayo: muestra el plan y no escribe nada
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun

# 2. Instalación real
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

`-ExecutionPolicy Bypass` vale sólo para ese proceso; no ejecutes `Set-ExecutionPolicy`.
Una directiva de grupo (`MachinePolicy` o `UserPolicy`) tiene precedencia sobre
`-ExecutionPolicy`: si tu equipo la define, el parámetro no la anula.
Con `Bypass`, PowerShell no comprueba la marca de origen web (Mark-of-the-Web): si el
repositorio vino en un ZIP descargado, esa comprobación se salta. Lee `install.ps1`
antes de ejecutarlo.

Parámetros:

| Parámetro | Por defecto | Efecto |
|---|---|---|
| `-Target` | `~/.claude` (`Join-Path $HOME '.claude'`) | Carpeta de destino. Útil para probar contra una carpeta temporal |
| `-BackupDir` | `<Target>-backup-<yyyyMMdd-HHmmss>` (hermano del destino, p. ej. `~/.claude-backup-20261119-153000`) | Carpeta de respaldo. Debe ser una carpeta nueva y no estar dentro de `-Target`; si hay algo que respaldar y ya existe, el instalador sale con 1 |
| `-DryRun` | apagado | Muestra el plan y sale sin crear `-Target`, `-BackupDir` ni ningún archivo |
| `-Force` | apagado | Permite sobrescribir archivos con cambios locales, siempre con respaldo |

Qué hace, en orden (los pasos 1 a 5 no escriben nada):

1. Valida `install-manifest.json`: `schema` 1, `algorithm` `sha256` y que cada ruta cumpla la
   lista permitida (cualquier `agents/[a-z0-9_-]+.md`, hoy nueve, más `rules/agentes.md`,
   `hooks/agent_guard.py` y `docs/agentes.md`); rechaza rutas duplicadas, absolutas, con `..`,
   `\` o `:`.
2. Verifica el origen: el hash canónico (SHA-256 con CRLF convertido a LF) de cada archivo
   debe coincidir con el manifiesto.
3. Lee el estado previo `<Target>/synclayer-manifest.json`. Si no se puede leer o no es
   válido, lo trata como ausente, avisa por stderr y no lo respalda (se reescribe sin respaldo).
4. Clasifica cada archivo por el hash del destino. El plan muestra una línea `ESTADO  ruta`
   por archivo y un resumen:

   | Estado | Condición | Acción |
   |---|---|---|
   | `NUEVO` | El destino no existe | Copia |
   | `IGUAL` | El hash del destino coincide con el manifiesto | Nada |
   | `ACTUALIZAR` | Distinto, y coincide con lo que instaló la ejecución anterior | Respalda y copia |
   | `MODIFICADO` | Distinto, y sin estado previo o con un hash que no es el de la ejecución anterior | Sin `-Force`: aborta con exit 3 y no escribe nada. Con `-Force`: respalda y copia |
   | `HUERFANO` | Estaba en el estado previo y ya no está en el manifiesto | Sólo informa; no lo borra |

5. Con `-DryRun` termina aquí: sale con 0, o con el 1, 2 o 3 que habría dado la ejecución real.
6. Respalda en `-BackupDir`, con la misma ruta relativa, lo que va a sobrescribir (y el
   estado previo si lo va a reescribir y era válido), y verifica cada copia del respaldo. Un
   estado ilegible o inválido se reescribe sin respaldo. La carpeta de respaldo sólo se crea
   si hay algo que respaldar y nunca se pisa un respaldo.
7. Copia primero `hooks/agent_guard.py` y después el resto, cada archivo mediante un
   temporal en la misma carpeta y un movimiento sobre el destino.
8. Verifica el hash de lo escrito.
9. Escribe `<Target>/synclayer-manifest.json`, una copia del manifiesto instalado, sólo si
   todo lo anterior salió bien. Sin él, el instalador no distingue una versión anterior de
   SyncLayer de una edición a mano, y todo archivo distinto sale `MODIFICADO`.
10. Imprime los conteos, la ruta del respaldo y los recordatorios (reiniciar sesiones,
    `settings.json` y `CLAUDE.md` sin tocar, sin sincronización automática).

Primera instalación sobre una copia manual: sin estado previo, todo archivo distinto sale
`MODIFICADO`. Haz el `-DryRun`, mira qué difiere y decide: llevar el cambio al repositorio
(ver «Dos copias, sin sincronización automática») o repetir con `-Force`, que respalda y
sobrescribe.

Códigos de salida:

| Código | Significado | ¿Se escribió algo? |
|---|---|---|
| 0 | Correcto, incluido «nada que hacer» y `-DryRun` sin problemas | Sólo en ejecución real |
| 1 | Uso o entorno: manifiesto ausente o inválido, ruta no permitida, punto de reanálisis o archivo bloqueado detectados antes de escribir, respaldo que ya existe, `-Target` que es un archivo o una raíz de unidad sin `-BackupDir`, error no previsto | No (salvo fallo de E/S al crear el respaldo) |
| 2 | El origen no coincide con el manifiesto | No |
| 3 | Hay `MODIFICADO` y falta `-Force` | No |
| 4 | Falló la copia, la verificación posterior o la escritura del estado | Sí, parcial; el respaldo queda y no hay rollback |

Tras un exit 4, corrige la causa y repite: reinstalar es seguro. Si el exit 4 ocurrió después
de crear el respaldo y la repetición vuelve a tener algo que respaldar, repetir con el mismo
`-BackupDir` explícito sale 1 porque la carpeta ya existe: usa otro `-BackupDir` o ninguno.

Qué no hace: no sincroniza automáticamente, no borra nada, no toca `settings.json` ni
`~/.claude/CLAUDE.md`, no hace rollback y no autentica el origen. El único entorno
verificado es Windows PowerShell 5.1.

Después, las instrucciones globales del usuario (`~/.claude/CLAUDE.md`) deben apuntar
a las reglas. Las reglas de `~/.claude/rules/` se cargan en todos los proyectos. Ejemplo
de fragmento:

```markdown
## Ejecución de planes

Delega según el tamaño de la tarea con los agentes globales descritos en
`~/.claude/rules/agentes.md`.
```

Las sesiones que ya estaban abiertas al instalar no ven los agentes nuevos: reinícialas.

### Dos copias, sin sincronización automática

Editar los archivos vivos de `~/.claude/` no actualiza este repositorio, y editar el
repositorio no actualiza `~/.claude/`. Repositorio -> `~/.claude` lo hace `install.ps1`
cuando lo ejecutas; `~/.claude` -> repositorio es manual, como sigue. El manifiesto detecta
deriva, corrupción y ediciones sin regenerar; no autentica el origen. Haz respaldo del
destino antes de sobrescribir.

`~/.claude` -> repositorio: copia sólo los archivos de SyncLayer, nunca con comodines.
`~/.claude/agents/`, `hooks/` y `docs/` contienen archivos que no son de SyncLayer
(por ejemplo `hooks/caveman-statusline.ps1`); este repositorio es público y no deben
entrar. Desde la raíz del repositorio:

```powershell
foreach ($f in (git ls-files agents rules hooks docs/agentes.md)) {
    Copy-Item "$HOME\.claude\$f" ".\$f" -Force
}
git status   # revisa el diff antes de commitear
```

Tras copiar un archivo gestionado al repositorio, regenera el manifiesto (ver
«Mantenimiento»). Ojo con `tests/`, `tools/` y `install.ps1`: sólo existen en el repositorio.

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
| `sentinel` | `Write\|Edit\|NotebookEdit\|Bash` | `python "$HOME/.claude/hooks/agent_guard.py" tests-only` |
| `auditor`, `shield`, `debugger` | `Bash` | `python "$HOME/.claude/hooks/agent_guard.py" readonly --allow-temp` |

Contrato: lee un JSON por stdin (`tool_name`, `tool_input`, `cwd`). Sale con 0 para
permitir y con 2 para bloquear; en ese caso escribe el motivo, en español, por stderr.
Falla cerrado: entrada inválida, modo desconocido, cualquier error interno y comandos
de más de 100 000 caracteres terminan en bloqueo.

- `tests-only`: `Write`, `Edit` y `NotebookEdit` sólo pasan sobre artefactos de pruebas
  (carpetas de pruebas, `test_*.py`, `*.test.*`, `*.spec.*`, `conftest.py`, etc.). Las
  carpetas se evalúan sobre la ruta relativa al `cwd` del payload; una ruta absoluta
  fuera de `cwd` (o sin `cwd`) sólo vale si es temporal. Quedan excluidas `.git`,
  `.github`, `.claude`, `.vscode`, `.idea`, `.husky`, `.venv`, `venv`, `site-packages`
  y `node_modules`.
  Para `Bash`, `tests-only` es **estricto**: sólo acepta comandos simples. Rechaza
  `$`, backticks, `\` (salvo `\;`), paréntesis, llaves (salvo `{}`), `[[`, heredocs,
  comandos de varias líneas, globs con corchetes, comentarios y caracteres de control,
  porque el parser no puede emularlos con certeza. Escribir sólo se permite hacia rutas
  de pruebas bajo `cwd` o temporales. Un `cd` anula las rutas relativas. Escribe un
  comando simple por llamada, con rutas literales y `/` como separador.
- `readonly`: bloquea git que modifica, comandos que modifican archivos, editores
  in situ, instalación de paquetes y redirección de salida a archivos.
  `--allow-temp` permite escribir sólo bajo directorios temporales.

### Límites

Es una heurística contra escrituras accidentales, **no un sandbox**.

- **`sentinel` tiene guarda en `Bash` desde el modo estricto de `tests-only`, pero sigue
  siendo una lista negra.** Escribe en rutas de pruebas y bloquea los escritores
  habituales, no todos. Sin sandbox, un runner de pruebas ejecuta código del repositorio
  y puede escribir donde quiera. «Sólo escribe tests» es heurístico.
- `auditor`, `shield` y `debugger` no son de solo lectura real: deben correr tests y
  builds, y eso ejecuta código arbitrario. Tampoco hay restricción de lectura (`.env`)
  ni de red (`curl -d @archivo URL`).
- El modo `readonly` es una lista negra con parser parcial de shell, no estricto. Pasan,
  entre otros, comandos que ejecutan o escriben por vías no listadas: `python script.py`,
  `$(echo rm) x`, `c=rm; $c x`, `busybox rm`, `awk '{print > "f"}'`,
  `GIT_EXTERNAL_DIFF=... git diff`, `docker run`, `ssh`, `iex`, `sqlite3`/`psql`/`mysql`
  con `DROP`.
- Huecos confirmados en la revisión final y no corregidos (`tests-only` y `readonly`):
  `tar` con `--checkpoint-action`/`--remove-files`/`--index-file`, `openssl rand -out` y
  `openssl base64 -d -out`, `xxd --revert`, `vim -c`/`+cmd`, `sed -f script` (el comando
  `e`), `cp` con `nullglob` y varios orígenes, variables que cambian la configuración de
  git (`HOME`, `XDG_CONFIG_HOME`), `export` sin `=`, `PS4` y `let`/`printf -v` con
  sustituciones en comillas simples, y los puntos y espacios finales de nombres de
  carpeta en Windows (`.claude./`).
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

## Límites del instalador

Riesgos residuales conocidos, verificados en revisión de seguridad y de código.

**Integridad, no autenticidad**

- El manifiesto vive en el mismo repositorio que los archivos: da integridad, no
  autenticidad. Un clon o un PR malicioso con el manifiesto regenerado instala, sin aviso,
  una `agent_guard.py` debilitada o agentes sin `hooks:`. Instala sólo desde un clon cuyo
  commit hayas revisado (`git log -p -- hooks/ agents/`).
- Un exit 2 se resuelve revisando `git status` y `git diff` y restaurando el archivo.
  Regenerar el manifiesto es cosa de los mantenedores, no de quien instala.
- La lista permitida acepta cualquier `agents/<nombre>.md`; qué archivos se instalan lo fija
  el manifiesto del repositorio.

**Códigos de salida por fase**

- Un punto de reanálisis o un bloqueo detectados antes de escribir en el destino dan exit 1.
  Los detectados durante o después de escribir (copia, verificación, estado) dan exit 4.

**Enlaces y rutas**

- La carrera con enlaces no se cierra: si un enlace aparece mientras se escribe, un archivo
  puede quedar escrito fuera de `-Target`. Se informa con exit 4 y nunca se borra.
- Un `-Target` que es enlace simbólico o junction se rechaza (exit 1). Un `~/.claude` que es
  un enlace a un repositorio de dotfiles se rechaza igual: pasa `-Target` con la ruta real.
  Con ese `-Target` el instalador avisa de que no es `~/.claude`, aunque resuelva al mismo sitio.
- No se comprueban los ancestros de `-Target` ni de `-BackupDir`. Un `-BackupDir` con punto
  final, con nombre 8.3 o con un enlace en un ancestro puede caer dentro de `-Target`.

**Permisos**

- El aviso de ACE sólo cubre entradas explícitas, no heredadas, sobre `agent_guard.py`. No
  cubre ACE heredadas, la ACL de la carpeta ni el propietario.
- `File.Replace` conserva el ACL del destino: reinstalar no repara permisos alterados.

**Respaldo**

- Queda una ventana mínima al crear la carpeta de respaldo (no existe un `mkdir` exclusivo
  sin P/Invoke), y el nombre por defecto es predecible (resolución de un segundo).
  `-BackupDir` debe ser una carpeta nueva y no estar dentro de `-Target`; si hay algo que
  respaldar y ya existe, el instalador sale con 1.
- Tras un exit 4 con respaldo creado, repetir con el mismo `-BackupDir` explícito da exit 1
  si vuelve a haber algo que respaldar: usa otro `-BackupDir` o ninguno.

**Fallos al escribir**

- Si `ReplaceFile` falla con HResult 1177, el temporal `.synclayer-*.tmp` se conserva (es la
  única copia nueva) y hay que moverlo a mano; el mensaje da su ruta.
- Los `HUERFANO` nunca se borran: un agente retirado del repositorio sigue activo hasta que
  lo borres a mano.

**Estado y avisos**

- Un estado bloqueado o ilegible se trata como ausente. Con el estado bloqueado y archivos a
  actualizar, sale primero exit 3 pidiendo `-Force`, y con `-Force` sale exit 1 «bloqueado».
  Es un comportamiento conocido, pendiente de pulir.
- Los avisos de `HOME`, de ACE y de `-Target` sólo salen en ejecución real, no en `-DryRun`.
- El instalador avisa si la variable de entorno `HOME` difiere de `$HOME` de PowerShell: los
  `hooks:` de los agentes usan `$HOME` del shell que los lanza.

**No verificado**

- pwsh 7 (no está instalado en el equipo de pruebas), volúmenes de red y OneDrive, un enlace
  simbólico de archivo real creado con privilegio, la durabilidad ante un corte de energía y
  Windows 10 (nombres reservados).

## Pruebas

```
python -B -m unittest discover -s tests
```

464 pruebas, 109 saltadas (las de `install.ps1` contra pwsh, que no está instalado; sin ningún PowerShell en el PATH se omiten también las de `powershell.exe`), sólo biblioteca estándar, Python 3.12. La suite tarda unos 4 minutos: no la corras en paralelo con procesos pesados (hay fallos por memoria, «paging file too small» u OutOfMemory). Las pruebas del instalador usan siempre `-Target` a una carpeta temporal, nunca `~/.claude`. Además se verificó en sesiones
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
- Tras cambiar cualquiera de los doce archivos gestionados (los nueve agentes,
  `rules/agentes.md`, `hooks/agent_guard.py`, `docs/agentes.md`), regenera el manifiesto con
  `python -B tools/build_manifest.py` (`--check` sólo comprueba y sale con 1 si no está al
  día) y vuelve a instalar con `install.ps1`. La prueba de sincronía falla si el manifiesto
  quedó viejo.

## Licencia

Sin licencia definida todavía.

## Línea de tiempo y avance

> **Sección viva.** Se actualiza en el mismo commit que cierra una sub-fase y cada vez que el plan general suma fases. Última actualización: **2026-11-19** (T3 de la Fase 2 cerrada: agregación y métricas).

### Avance global

**El proyecto completo va en 26%.** Cuenta las cinco fases con el mismo peso; las fases 2 a 5 son backlog sin desglosar ([plan](docs/plans/2026-11-19-backlog-configuracion-y-reportes.md)), así que el número sube cuando se desglosen en sub-fases.

| Fase | Avance | % | Unidades | Estado |
|:--|:--|--:|:--|:--|
| **Proyecto completo** | 🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜ | **26%** | 5 fases, mismo peso | |
| **1. Instalador** | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 7 de 7 | Cerrada en la rama `feat/instalador`; falta el `-DryRun` y la instalación real del propietario y el merge a `main` ([plan](docs/plans/2026-11-19-instalador.md)) |
| **2. Reporte de uso de agentes** | 🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜ | **30%** | 3 de 10 | Plan aprobado, en curso ([plan](docs/plans/2026-11-19-fase2-reporte-de-uso.md), [exploración](docs/plans/2026-11-19-fase2-reporte-de-uso-exploracion.md)) |
| **3. Esfuerzo configurable (5 niveles)** | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | sin desglosar | Backlog |
| **4. Nombres de agentes configurables** | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | sin desglosar | Backlog |
| **5. Otras configuraciones dinámicas** | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | sin desglosar | Backlog |

Cada sub-fase cuenta igual (una unidad). Porcentaje = unidades cerradas ÷ unidades planeadas. «Cerrada» = commiteada en la rama de la fase con su suite verde y la revisión de `auditor` sin hallazgos Critical ni Important; la integración a `main` se hace al cerrar la fase. Lo que falta probar en un entorno real (la instalación sobre el `~/.claude` verdadero) se lista aparte y no resta.

### La Fase 1 por frentes

| Frente | Avance | % | Unidades |
|:--|:--|--:|:--|
| Manifiesto y su prueba de sincronía | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T1, T2) |
| `install.ps1` | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 3 de 3 (T3, T4, T5) |
| Documentación y cierre | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T6, cierre) |

- **Manifiesto y su prueba de sincronía**
  - ✅ Hecho: T1 generador con hash canónico (`tools/build_manifest.py`); T2 `install-manifest.json` y prueba de sincronía.
  - ⬜ Falta: Nada.
- **`install.ps1`**
  - ✅ Hecho: T3 validación, clasificación y `-DryRun`; T4 respaldo verificado, copia atómica con el hook primero, verificación posterior y archivo de estado; T5 cambios locales, `-Force`, estado ilegible, rechazo de puntos de reanálisis y bloqueos detectados antes de escribir.
  - ⬜ Falta: Nada. Los hallazgos Minor que quedaron de la revisión de T5 (mensajes de `-Force` con estado bloqueado, avisos también en `-DryRun`, normalización de `-BackupDir`) se recogen en T6 o en el cierre y no restan.
- **Documentación y cierre**
  - ✅ Hecho: T6 (README, CLAUDE.md, HISTORY.md, `docs/agentes.md`, manifiesto regenerado); cierre: `sentinel` (464 pruebas en dos corridas, los 20 casos del plan cubiertos), `shield` sobre T3 a T5 sin Critical ni High, `auditor` sobre el cambio completo sin Critical ni Important.
  - ⬜ Falta: Nada del plan. Fuera del conteo y del propietario: `-DryRun` e instalación real sobre `~/.claude` (hoy `docs/agentes.md` de la copia viva difiere: saldrá `MODIFICADO`, exit 3, y hará falta `-Force`), compatibilidad con pwsh 7 (no verificada) y los Minor de UX que quedaron anotados en «Límites del instalador».

### Línea de tiempo

| Fecha | Hito | |
|:--|:--|:-:|
| 2026-11-19 | Nace SyncLayer: nueve agentes, reglas de orquestación y hook `agent_guard.py` | ✅ |
| 2026-11-19 | Límites de la guarda documentados; Bash guardado para `sentinel` (`tests-only` estricto) | ✅ |
| 2026-11-19 | Marca «Modular Grid System»: símbolo, wordmark, lockups, favicon, banner, social preview, catálogo, estrella, slides y hoja de marca | ✅ |
| 2026-11-19 | Plan del instalador aprobado; T1 y T2 (manifiesto), T3 a T5 (`install.ps1`), T6 (documentación) y cierre (`sentinel`, `shield`, `auditor`): Fase 1 cerrada | ✅ |
| 2026-11-19 | Instalador probado con `-DryRun` e instalado en el `~/.claude` real; integrado en `main` | ✅ |
| 2026-11-19 | Plan de la Fase 2 (reporte de uso) aprobado: 10 unidades (T1 a T9 y el cierre del núcleo) | ✅ |
| 2026-11-20 | T1 de la Fase 2: `inspect` (sólo estructura, filtros cerrados) y transcripciones sintéticas; revisada por `auditor` y `shield` | ✅ |
| 2026-11-20 | Compuerta G1: `inspect` corrido sobre los datos reales ([resultado](docs/plans/2026-11-20-fase2-g1-resultado.md)); supuestos confirmados, dos ajustes propuestos | ✅ |
| 2026-11-20 | T2 de la Fase 2: lector defensivo de subagentes (deduplicación por `message.id`, hardlinks de Claude Code aceptados, conjuntos `plugin:<prefijo>`); revisada por `auditor` | ✅ |
| 2026-11-20 | T3 de la Fase 2: agregación y métricas puras (ventana UTC, mediana, p90, desglose por rango de versión, repeticiones inferidas con clave interna por agente); revisada por `auditor` | ✅ |
| **Ahora** | **T4 de la Fase 2**: conteo de skills (`input.skill` confirmado en G1) y los Minor pendientes de T3 | 🔄 |
| Luego | T2 a T8, cierre del núcleo, T9 (hook opcional) y desglosar las fases 3 a 5 (backlog) | ⬜ |

Leyenda: ✅ cerrada · 🔄 en curso · ⬜ pendiente. Las fechas son las del historial de `git`; el detalle está en [HISTORY.md](HISTORY.md).

### Cómo se mantiene

1. **Se cierra una sub-fase:** sumar su unidad a «Hecho», recalcular los porcentajes del frente, de la fase y del proyecto completo, y actualizar la tabla «Avance global» y los cuadros 🟩 (un cuadro = 10 %, redondeando al más cercano). Pasar el hito a ✅ y mover el 🔄 al siguiente.
2. **Se agregan fases o sub-fases al plan general:** sumarlas a «Unidades» y a «Falta» (o crear el frente) y recalcular; el porcentaje baja, y es lo esperado.
3. **Se desglosa una fase del backlog:** pasar «sin desglosar» a sus unidades reales.
4. Actualizar la fecha de «Última actualización».
