# CLAUDE.md

Guía para trabajar dentro de este repositorio. Qué es y cómo se instala: `README.md`.

## Comandos

```
python -B -m unittest discover -s tests
```

Sólo biblioteca estándar, Python 3.12. Corre siempre Python con `-B` para no generar
`__pycache__`. La suite: 1238 pruebas, 184 saltadas (181 de `install.ps1` contra pwsh, que no está instalado, y 3 de
la rama POSIX del reporte de uso: permisos 0600, `fchmod`, FIFO; no corren en Windows), unos 4 minutos. No la
corras en paralelo con procesos pesados: da fallos por memoria («paging file too small»,
OutOfMemory).

Manifiesto del instalador (regenerar tras cambiar cualquiera de los doce archivos gestionados):

```
python -B tools/build_manifest.py
python -B tools/build_manifest.py --check
```

El segundo sólo comprueba: sale con 0 si está al día y con 1 si no. Probar el instalador sin
tocar `~/.claude`, siempre con `-Target` a una carpeta temporal:

```
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun -Target <carpeta-temporal>
```

Probar la guarda a mano con un payload JSON por stdin (el código de salida es 0 o 2;
el motivo del bloqueo sale por stderr). Construye el payload con Python, no con
comillas a mano:

```
python -B -c "import json; print(json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git add .'}, 'cwd': '.'}))" | python -B hooks/agent_guard.py readonly --allow-temp
```

En Windows con Git Bash, las barras invertidas dentro de un JSON escrito a mano se
rompen con facilidad al citar; por eso conviene generarlo con `json.dumps`.

Reporte de uso de subagentes (se ejecuta desde el clon, no se instala). Pasa siempre
`--claude-dir` a una carpeta temporal en las pruebas, nunca el `~/.claude` real:

```
python -B tools/usage_report.py inspect [--claude-dir DIR] [--project-dir DIR] [--show-paths]
python -B tools/usage_report.py project [--project-dir DIR] [--claude-dir DIR] [--transcripts-dir NOMBRE]... [--since AAAA-MM-DD] [--until AAAA-MM-DD | --all] [--stdout] [--show-paths]
python -B tools/usage_report.py global  [--claude-dir DIR] [--since AAAA-MM-DD] [--until AAAA-MM-DD | --all] [--stdout] [--show-paths]
```

Exit 0 correcto, 1 entorno o datos, 2 uso incorrecto, 3 esquema desconocido o demasiados
archivos dañados. Detalle de parámetros y destinos en `README.md` («Reporte de uso»).

Regenerar los assets de marca (necesita `fontTools` y `uharfbuzz`):

```
python -B assets/brand/src/build_brand.py --fonts <carpeta-de-fuentes>
python -B assets/brand/src/build_round2.py --fonts <carpeta-de-fuentes>
python -B assets/brand/src/build_round3.py --fonts <carpeta-de-fuentes>
```

`build_brand.py` produce también los lockups apilados y `favicon.svg`; `build_round3.py`, la
hoja de marca. Los PNG y el `.ico` se exportan aparte (sólo biblioteca estándar, necesitan
msedge; `--edge <ruta>` si no lo encuentra):

```
python -B assets/brand/src/export_social_png.py
python -B assets/brand/src/export_favicons.py
```

La carpeta debe tener `IBMPlexSans-SemiBold.ttf`, `IBMPlexSans-Medium.ttf`,
`IBMPlexSans-Regular.ttf`, `IBMPlexMono-Medium.ttf` e `IBMPlexMono-Regular.ttf` (OFL,
github.com/IBM/plex). Las fuentes no se versionan.

## Arquitectura

Cuatro piezas, de la más abstracta a la más concreta (la cuarta, el instalador, está más abajo):

1. `agents/*.md`: un archivo por agente (nueve). Frontmatter + prompt.
2. `rules/agentes.md`: reglas de orquestación. Forma de estrella: sólo la sesión
   principal delega y pregunta al usuario; los agentes no se delegan entre sí.
3. `hooks/agent_guard.py`: guarda `PreToolUse`, enlazada desde el frontmatter
   (`hooks:`) de `sentinel` (modo `tests-only`) y de `auditor`, `shield` y `debugger`
   (modo `readonly --allow-temp`).

4. El instalador: `install.ps1` (Windows PowerShell 5.1), `install-manifest.json` (los doce
   archivos gestionados con su hash canónico) y `tools/build_manifest.py` (lo genera y lo
   comprueba). Lee además `<Target>/synclayer-config.json` (opcional, a mano, sólo `level`; ver «Niveles
   de esfuerzo» en «Comportamientos no obvios»). En el destino deja el estado `<Target>/synclayer-manifest.json`, con esquema 2 (por
   archivo: hash del origen `sha256`, hash de lo escrito `written` y `level`; lee también el esquema 1 y lo
   migra). La clasificación compara el destino con `written`: igual al origen nuevo es `IGUAL`, igual a
   `written` es `ACTUALIZAR`, cualquier otro caso `MODIFICADO`; un estado no reconocido se trata como
   ausente y nunca produce `ACTUALIZAR`. Las comparaciones de claves y valores del estado son ordinales. Ni el instalador, ni `tools/`, ni el manifiesto del repo se instalan
   en `~/.claude`.

Fuera de las cuatro piezas, `tools/usage_report.py` es el reporte de uso (Fase 2): un solo
archivo, sólo biblioteca estándar, que se ejecuta desde el clon. Capas: lector defensivo de
transcripciones (`read_calls`), agregación pura (`aggregate_calls`, `make_window`),
generadores puros de Markdown (`render_project_report`, `render_global_report`) y la CLI con
escritura (`project`, `global`) más `inspect` de diagnóstico. Pruebas:
`tests/test_usage_report.py`, `tests/test_usage_report_cli.py` y `tests/test_usage_report_edges.py`
(bordes de punta a punta: ventana, exit 1/2/3/130, nombres raros, mensajes sin fuga).

`docs/agentes.md` es la guía humana. `docs/brand/` define la marca (estrategia, voz, identidad
visual); el copy oficial va en inglés y no declara capacidades que el repositorio no tenga.

`assets/brand/` contiene los SVG de marca y `social-preview.png`; `assets/brand/src/` los
generadores (`build_brand.py`: símbolo, wordmark, lockups horizontal y apilado, `favicon.svg`;
`build_round2.py`: banner, social preview, catálogo, estrella, slides; `build_round3.py`: hoja
de marca) y los exportadores (`export_social_png.py`, `export_favicons.py`, `ico.py`). No forma parte de la instalación en `~/.claude/`.

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
- Todo cambio en `install.ps1` empieza con una prueba que falla en `tests/test_install.py`.
- Todo cambio en `tools/usage_report.py` empieza con una prueba que falla en
  `tests/test_usage_report.py` (lector, métricas, generadores) `tests/test_usage_report_cli.py`
  (subcomandos y escritura) o `tests/test_usage_report_edges.py` (bordes de punta a punta). Ningún agente ejecuta la herramienta contra el `~/.claude` real.
- El código de `tools/usage_report.py` es ASCII (las tildes del reporte van como escapes
  `\u00xx`); el texto de los reportes va en español con tildes.
- `install.ps1` va en ASCII puro y sin BOM: Windows PowerShell 5.1 lee como ANSI un archivo
  sin BOM. Los mensajes van en español sin acentos. Hay una prueba. Con `core.autocrlf` git
  deja el archivo en CRLF al hacer checkout o merge: las pruebas que leen su texto deben
  normalizar CRLF a LF (`\r\n` a `\n`) antes de usar regex con anclas de fin de línea.
- Ejecuta Python con `-B`. No se versiona `__pycache__`.
- Los SVG de `assets/brand/` se regeneran con los scripts de `assets/brand/src/`; no se
  editan a mano.
- Excepción de dependencias: los generadores de `assets/brand/src/` requieren `fontTools` y
  `uharfbuzz` (no son biblioteca estándar). Son herramienta de build; el repositorio, la
  guarda y las pruebas siguen siendo sólo biblioteca estándar.
- Los datos de los agentes (rol, modelo, herramientas, guarda) están duplicados en
  `assets/brand/src/agents_data.py` (`AGENTS`, sin dependencias; lo importa
  `build_round2.py`). `tests/test_brand_agents.py` los compara con el frontmatter de
  `agents/*.md` (nombre, `model`, `tools`, `hooks:` y Edit/Write) y falla si se desincronizan:
  al cambiar `agents/*.md`, actualiza `agents_data.py` y regenera.
- `social-preview.png` se exporta de `social-preview.svg` con
  `python -B assets/brand/src/export_social_png.py` (sólo biblioteca estándar; usa msedge
  headless, `--edge <ruta>` si no lo encuentra). Genera esta HTML en un temporal, sin margen
  del navegador (si no, la imagen sale desplazada):
  `<body style="margin:0"><img src="<ruta al SVG>" style="width:1280px;height:640px;display:block">`
  y la captura con `msedge --headless --disable-gpu --force-device-scale-factor=1 --hide-scrollbars --window-size=1280,640 --screenshot=<salida>.png <html>`.
  Regenéralo cada vez que cambie el SVG.
- `export_favicons.py` genera `favicon-16/32/48.png`, `apple-touch-icon.png` y `favicon.ico`
  (el contenedor lo escribe `ico.py`, que cubre `tests/test_ico.py`). Usa el símbolo dark sobre
  un fondo `bg` opaco: un símbolo transparente se pierde en una de las dos pestañas (tinta oscura
  sobre pestaña oscura o al revés); el tile mantiene visibles los huecos en ambas. Los tres
  dibujan `symbol-16-dark.svg`: 16 px a 1x sin margen (el símbolo llena el lienzo), 32 px a 1x y
  48 px a 2x, ambos con 8 px de margen `bg` por lado (huecos de 1, 1 y 2 px exactos). Limitación:
  sobre una pestaña clara el icono de 16 px no tiene margen y los bloques claros pierden contraste
  contra el blanco. Edge headless se ha colgado alguna vez con ventanas pequeñas: cada captura
  usa su propio `--user-data-dir`, con timeout de 30 s y un reintento, y los archivos se copian a
  `assets/brand/` sólo si todas las capturas salen bien. Regenéralos cuando cambien `symbol-16-dark.svg` o `symbol-dark.svg`.
- El catálogo visual clasifica a los agentes por herramientas (sin `Edit`/`Write`; escribe), nunca
  como «read-only»: la guarda es heurística, no un sandbox.
- Los SVG de marca llevan ids fijos (`wordmark`, `background`, etc.) y sólo se usan como
  `<img>`. Insertar varios inline en una misma página exige prefijar los ids.
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
- `sentinel` tiene guarda en `Write|Edit|NotebookEdit|Bash`. En `tests-only` el Bash es
  estricto (sólo comandos simples; rechaza `$`, backtick, `\`, subshells, `[[`, heredocs y
  multilínea) porque 4 rondas de parches a un parser que imita a bash dejaron huecos
  nuevos cada vez. Sigue siendo una lista negra: no documentes «sólo escribe tests» como
  garantía. Los huecos confirmados y no corregidos están en `README.md` (Límites).
- Es una heurística, no un sandbox: `python -c`, `node -e`, `bash -c`, `eval`,
  `xargs rm`, `cmd /c` y `python -m venv` son brechas aceptadas.
- `atlas` está fijado a `model: claude-fable-5-2` porque el alias `fable` resolvía a
  Fable 5.1 con Claude Code 2.1.310. El CLI avisa `unrecognized_model`, pero la API
  lo acepta.
- Los frontmatter apuntan a `$HOME/.claude/hooks/agent_guard.py`, no a este repo: tras
  editar `hooks/agent_guard.py` hay que reinstalar la copia en `~/.claude/hooks/`.
- En `tests-only`, los directorios de pruebas se evalúan sobre la ruta relativa al
  `cwd` del payload. Fuera de `cwd`, o sin `cwd`, una ruta absoluta sólo vale si es temporal.
- Las sesiones ya abiertas no ven agentes nuevos o modificados: reiniciarlas.

- El manifiesto hay que REGENERAR cada vez que cambie cualquiera de los doce archivos
  gestionados (`agents/*.md`, `rules/agentes.md`, `hooks/agent_guard.py`,
  `docs/agentes.md`). La prueba de sincronía de `tests/test_manifest.py` falla y su mensaje
  trae el comando de regeneración.
- Hash canónico: SHA-256 de los bytes con CRLF convertido a LF, para que `autocrlf` no cambie
  el hash. El instalador escribe en el destino los bytes canónicos (LF).
- `AllowedPattern` de `install.ps1` y `ALLOWED` de `tools/build_manifest.py` son la misma regex,
  pero el script usa `\z` (en .NET `\Z` y `$` aceptan un salto de línea final). Una prueba las
  compara. Acepta cualquier `agents/<nombre>.md`, no una lista cerrada de nombres.
- Niveles de esfuerzo (Fase 3, plan `docs/plans/2026-11-20-fase3-esfuerzo-configurable.md`). Estado: T1,
  T2, T3, T4 y T6 hechas; T5 (pruebas de transiciones, línea `Nivel anterior:` y frase del exit 3) y
  el cierre pendientes; T7 abierta hasta después de T5. Los niveles 1 a 4 se aplican (el instalador
  escribe `model:` y `effort:`), pero la compuerta G1 no se corrió: el efecto real de `effort:` en
  Claude Code sólo está verificado por documentación. No lo documentes como probado en una máquina real.
  - Contrato con las pruebas: la tabla nivel por agente vive en `install.ps1` (`$LevelRows`, niveles 1 a 4;
    el 5 es el repositorio, sin filas) y debe ser igual a la del README entre `<!-- niveles:inicio -->` y
    `<!-- niveles:fin -->` (`tests/levels_ref.py` los lee, `tests/test_levels.py` lo comprueba junto con
    las reglas R1 a R5). Cambiar una celda exige cambiarla en los dos sitios. `auditor`, `shield` y
    `debugger` no entran en la tabla. No muevas ni renombres los marcadores.
  - Los textos de niveles no pueden prometer ahorro: `promise_hits` de `tests/test_levels.py` revisa la
    sección «Niveles» del README (la lista completa de patrones está en `PROMISE_PATTERNS`). Haz lo mismo en el resto de la documentación.
  - Nivel 5 = repositorio tal cual: la instalación escribe los bytes canónicos del origen.
    `assets/brand/src/agents_data.py` y `tests/test_brand_agents.py` siguen en el nivel 5.
  - `<Target>/synclayer-config.json` (opcional, campo `level` de 1 a 5, sin archivo o `{}` = 5) es entrada
    no confiable: lectura única con tope de 64 KiB, UTF-8 estricto, sin enlaces, claves de lista cerrada
    (incluida `__type`, que `ConvertFrom-Json` de 5.1 descarta en silencio). Una configuración ilegible o
    inválida falla con exit 1 antes de escribir (también en `-DryRun`); un estado ilegible, en cambio, se
    trata como ausente. El instalador nunca escribe, respalda ni borra la configuración.
  - Renderizado (T4): con nivel 1 a 4, los seis agentes de `$LevelAgents` pasan por `ConvertTo-LevelBytes`
    (función pura; sólo toca las líneas `model:` y `effort:` del frontmatter) y falla cerrado con exit 1
    antes de escribir, también en `-DryRun`, ante un frontmatter que no entiende. Los demás archivos y
    los agentes fijos salen con los bytes del origen. Con nivel 5 no se llama al renderizado. Los avisos
    de entorno (T6) van antes. La guardia temporal de T3 ya no existe.
  - Marcadores de `install.ps1` entre el Paso 2 y el Paso 3: `# Configuracion:` (lee y valida el archivo)
    y `# Nivel:` (calcula `$outBytes` y `$outHash` por archivo; llama al renderizado sólo con nivel 1 a 4).
    No empiezan por `# Paso`, que es el contrato de `patch_script`. El Paso 7 escribe `$outBytes` y los
    Pasos 7 y 8 verifican contra `$outHash` (el manifiesto en el nivel 5; «lo esperado para el nivel N»
    en el 1 a 4).
  - La clasificación compara con `$outHash` (lo que se escribiría) y con `written` del estado previo:
    cambio de nivel con archivos intactos = `ACTUALIZAR`; mismo nivel = `IGUAL`; edición a mano =
    `MODIFICADO`. `Read-State` lee una sola vez con tope y el esquema 1 tiene lista cerrada de claves.
  - Pendiente de T5: línea `Nivel anterior:`, la frase del exit 3 que remite a la configuración y los
    casos 31 a 37 del plan como pruebas formales.
  - Límites conocidos de la configuración (README, «Límites del instalador»): 5.1 acepta sintaxis laxa
    (comillas simples, `+3`, `03`); con `level` repetido gana el último; carrera residual de lectura de
    enlace; `Format-Safe` no escapa `\`; pwsh 7 sin verificar.
  - Avisos de entorno: sólo con nivel 1 a 4, sólo el ámbito `Process`, nunca imprimen el valor; una
    variable de sólo espacios avisa y `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=0` también (sin verificar).
- Las pruebas del instalador pasan SIEMPRE `-Target` a una carpeta temporal, nunca
  `~/.claude`, y no escriben el nombre de usuario como literal.
- Los comentarios `# Paso N:` de `install.ps1` son un contrato con las pruebas: `patch_script`
  inyecta código justo después de esa línea. No los renombres ni los muevas sin ajustar las
  pruebas.
- pwsh no está instalado: las pruebas contra pwsh se saltan (181 en la última corrida; las otras 3 saltadas son de la rama POSIX del reporte de uso).
- El instalador: `MODIFICADO` aborta con exit 3 sin `-Force`; copia primero el hook; nunca
  borra; los `HUERFANO` sólo se informan. Un `-Target` o un destino que es punto de reanálisis
  se rechaza. Un `-Target` distinto de `~/.claude` no sirve para uso real: los `hooks:` de los
  agentes apuntan a `$HOME/.claude/hooks/agent_guard.py`. El manifiesto da integridad, no
  autenticidad; los riesgos residuales están en `README.md` («Límites del instalador»).
- Copia `~/.claude` -> repo sólo por archivo (`git ls-files`), nunca con comodines:
  `~/.claude/hooks/` y otras carpetas tienen archivos ajenos y el repo es público.
- Reporte de uso (`tools/usage_report.py`):
  - Destinos fijos, sin `--out`: `<project-dir>/.synclayer/usage-report.md` (con
    `.synclayer/.gitignore` exactamente `*\n`; otro contenido da exit 1 y no se edita) y
    `<claude-dir>/synclayer-usage.md`. Primera línea: marcador `<!-- synclayer-usage-report v1 -->`;
    un destino sin marcador, enlace, junction o con más de un enlace duro da exit 1 (no se pisa).
  - Escritura: temporal aleatorio `O_EXCL` en la misma carpeta, `0600`, bytes UTF-8 sin BOM con LF,
    `lstat` repetido antes de `os.replace`. Lectura y agregación van ANTES de tocar el disco: exit 1
    o 3 no dejan `.synclayer/` ni temporales. No se crean `<claude-dir>` ni `<project-dir>`.
  - `--claude-dir` por defecto `~/.claude`; no se honra `CLAUDE_CONFIG_DIR`. `--stdout` escribe bytes
    UTF-8 en `sys.stdout.buffer` (la consola de Windows, cp1252, rompería con `print`) y no escribe
    archivos. Sin `--show-paths` ningún mensaje imprime rutas; un error no previsto imprime sólo el
    nombre de la clase de la excepción (exit 1). Ctrl+C sale con 130.
  - Ventana: 30 fechas UTC que terminan hoy (inclusive); `--all` la quita. Fechas inválidas o
    `--all` con `--since/--until` dan exit 2. Hay dos exit 3: el de esquema desconocido sale del
    lector (`read_calls` -> `check_schema`, sobre TODOS los archivos leídos, aunque estén fuera de
    la ventana); el de más del 5 % de archivos dañados sale de `aggregate_calls`, sobre la ventana.
  - Deduplicación por `message.id` (dentro y entre archivos): una respuesta repartida en varias
    líneas no se cuenta dos veces. No se usa `totalTokens` de ningún resultado. Tokens desglosados
    por rango de versión (anterior a 2.1.310, 2.1.310 a 2.1.327 dudoso, desde 2.1.328).
  - Los ids con clave (`call_id`, `session`, `agent_key`) llevan blake2b con clave aleatoria por
    ejecución: ningún orden ni desempate puede depender de ellos (se usa `seq`), y
    `ReadResult.release_key()` se invoca al agregar. Nunca se serializa `ReadResult`, `CallRecord`,
    `SkillUse` ni `UsageMetrics`.
  - Privacidad: el global numera `proyecto 1..N` (sin hash); el de proyecto muestra su alias
    `p-<8 hex>` (recalculable, no es anonimización). El global es privado por defecto.
  - Avisos de git por stderr, sin llamar a git, y se escribe igual. Global: `.git` en `<claude-dir>`
    o una carpeta padre. Proyecto: reporte ya versionado, leyendo `.git/index` (v2 y v3; el v4,
    sparse y split no se detectan; falso positivo posible; en Windows depende de las mayúsculas de
    `--project-dir`). Es una ayuda, no una garantía; `git add -f` lo versiona igual.
  - Límites aceptados (README, «Límites del reporte de uso»): TOCTOU residual entre la última
    comprobación y `os.replace` en Windows; todo reparse point cuenta como enlace (los marcadores de
    OneDrive podrían dar exit 1); ACL heredada en Windows; rama POSIX sin verificar en este equipo.
  - Las pruebas «sin aviso de git» suben carpetas padre reales: fallarían en una máquina con `.git`
    en el home o en `%TEMP%`. Las pruebas pasan siempre `--claude-dir` a una carpeta temporal.
  - El instalador no instala la herramienta ni toca `synclayer-usage.md` ni `settings.json`.

## Cierre de un cambio

En el mismo cambio se actualizan `README.md`, `CLAUDE.md` y `HISTORY.md`. Si cambia un archivo
gestionado, se regenera el manifiesto (`python -B tools/build_manifest.py`). Si cambia el
catálogo, la guía `docs/agentes.md` y el catálogo de `rules/agentes.md` también.

Al cerrar una sub-fase del plan en curso (instalador y backlog), actualiza en el mismo
commit la sección «Línea de tiempo y avance» al final de `README.md`: suma la unidad a
«Hecho», recalcula frente, fase y global (un cuadro = 10 %, redondeando al más cercano),
mueve el 🔄 y cambia la fecha. Muestra la aritmética en el resumen del cierre. «Cerrada»
aquí = commiteada en la rama de la fase con la suite verde y `auditor` sin Critical ni
Important. Al desglosar una fase del backlog, «sin desglosar» pasa a sus unidades.
