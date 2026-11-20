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
├── assets/
│   └── brand/         SVG de marca (símbolo, wordmark, lockups, favicon, banner,
│       │              catálogo, estrella, slides, hoja de marca), PNG/ICO exportados
│       │              y generadores
│       └── src/       build_brand.py, build_round2.py, build_round3.py, brandlib.py,
│                          fonts_util.py, agents_data.py, ico.py, export_social_png.py,
│                          export_favicons.py
├── docs/
│   ├── agentes.md     Guía de uso y mantenimiento
│   └── brand/         Estrategia, voz e identidad visual del proyecto
└── tests/
    ├── test_agent_guard.py
    ├── test_brand_agents.py
    └── test_ico.py
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

## Pruebas

```
python -B -m unittest discover -s tests
```

197 pruebas (186 de la guarda, 2 de sincronía de los datos de marca y 9 del escritor ICO), sólo biblioteca estándar, Python 3.12. Además se verificó en sesiones
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

## Línea de tiempo y avance

> **Sección viva.** Se actualiza en el mismo commit que cierra una sub-fase y cada vez que el plan general suma fases. Última actualización: **2026-11-19** (T5 del instalador cerrada; T6 en curso).

### Avance global

**El proyecto completo va en 14%.** Cuenta las cinco fases con el mismo peso; las fases 2 a 5 son backlog sin desglosar ([plan](docs/plans/2026-11-19-backlog-configuracion-y-reportes.md)), así que el número sube cuando se desglosen en sub-fases.

| Fase | Avance | % | Unidades | Estado |
|:--|:--|--:|:--|:--|
| **Proyecto completo** | 🟩⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **14%** | 5 fases, mismo peso | |
| **1. Instalador** | 🟩🟩🟩🟩🟩🟩🟩⬜⬜⬜ | **71%** | 5 de 7 | En curso ([plan](docs/plans/2026-11-19-instalador.md)) |
| **2. Reporte de uso de agentes** | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | sin desglosar | Backlog: empieza con una exploración |
| **3. Esfuerzo configurable (5 niveles)** | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | sin desglosar | Backlog |
| **4. Nombres de agentes configurables** | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | sin desglosar | Backlog |
| **5. Otras configuraciones dinámicas** | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | sin desglosar | Backlog |

Cada sub-fase cuenta igual (una unidad). Porcentaje = unidades cerradas ÷ unidades planeadas. «Cerrada» = commiteada en la rama de la fase con su suite verde y la revisión de `auditor` sin hallazgos Critical ni Important; la integración a `main` se hace al cerrar la fase. Lo que falta probar en un entorno real (la instalación sobre el `~/.claude` verdadero) se lista aparte y no resta.

### La Fase 1 por frentes

| Frente | Avance | % | Unidades |
|:--|:--|--:|:--|
| Manifiesto y su prueba de sincronía | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T1, T2) |
| `install.ps1` | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 3 de 3 (T3, T4, T5) |
| Documentación y cierre | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | 0 de 2 (T6, cierre) |

- **Manifiesto y su prueba de sincronía**
  - ✅ Hecho: T1 generador con hash canónico (`tools/build_manifest.py`); T2 `install-manifest.json` y prueba de sincronía.
  - ⬜ Falta: Nada.
- **`install.ps1`**
  - ✅ Hecho: T3 validación, clasificación y `-DryRun`; T4 respaldo verificado, copia atómica con el hook primero, verificación posterior y archivo de estado; T5 cambios locales, `-Force`, estado ilegible, rechazo de puntos de reanálisis y bloqueos detectados antes de escribir.
  - ⬜ Falta: Nada. Los hallazgos Minor que quedaron de la revisión de T5 (mensajes de `-Force` con estado bloqueado, avisos también en `-DryRun`, normalización de `-BackupDir`) se recogen en T6 o en el cierre y no restan.
- **Documentación y cierre**
  - ✅ Hecho: Nada todavía.
  - ⬜ Falta: T6 (README, CLAUDE.md, HISTORY.md, `docs/agentes.md`, regenerar el manifiesto); cierre: `sentinel` en ambos shells, `shield`, `auditor` sobre el cambio completo. Fuera del conteo y del propietario: `-DryRun` e instalación real sobre `~/.claude`.

### Línea de tiempo

| Fecha | Hito | |
|:--|:--|:-:|
| 2026-11-19 | Nace SyncLayer: nueve agentes, reglas de orquestación y hook `agent_guard.py` | ✅ |
| 2026-11-19 | Límites de la guarda documentados; Bash guardado para `sentinel` (`tests-only` estricto) | ✅ |
| 2026-11-19 | Marca «Modular Grid System»: símbolo, wordmark, lockups, favicon, banner, social preview, catálogo, estrella, slides y hoja de marca | ✅ |
| 2026-11-19 | Plan del instalador aprobado; T1 y T2 (manifiesto) y T3 a T5 (`install.ps1`) cerradas | ✅ |
| **Ahora** | **T6 del instalador** (documentación y regenerar el manifiesto) | 🔄 |
| Luego | Cierre del instalador (`sentinel`, `shield`, `auditor`, `-DryRun` real) → desglosar y ejecutar las fases 2 a 5 | ⬜ |

Leyenda: ✅ cerrada · 🔄 en curso · ⬜ pendiente. Las fechas son las del historial de `git`; el detalle está en [HISTORY.md](HISTORY.md).

### Cómo se mantiene

1. **Se cierra una sub-fase:** sumar su unidad a «Hecho», recalcular los porcentajes del frente, de la fase y del proyecto completo, y actualizar la tabla «Avance global» y los cuadros 🟩 (un cuadro = 10 %, redondeando al más cercano). Pasar el hito a ✅ y mover el 🔄 al siguiente.
2. **Se agregan fases o sub-fases al plan general:** sumarlas a «Unidades» y a «Falta» (o crear el frente) y recalcular; el porcentaje baja, y es lo esperado.
3. **Se desglosa una fase del backlog:** pasar «sin desglosar» a sus unidades reales.
4. Actualizar la fecha de «Última actualización».
