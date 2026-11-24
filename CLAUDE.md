# CLAUDE.md

Guía para trabajar dentro de este repositorio. Qué es y cómo se instala: `README.md`.

## Comandos

```
python -B -m unittest discover -s tests
```

Sólo biblioteca estándar, Python 3.12. Corre siempre Python con `-B` para no generar
`__pycache__`. La suite: 1715 pruebas, 367 saltadas (365 contra pwsh, que no está instalado, y 2 de
la rama POSIX del reporte de uso: permisos 0600, `fchmod`, FIFO; no corren en Windows), más de una hora (unos 70 minutos). No la
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
   comprueba). Lee además `<Target>/synclayer-config.json` (opcional, a mano, sólo `level`, `aliases` y `plans_dir`; ver «Niveles
   de esfuerzo» y «Alias de agentes» en «Comportamientos no obvios»). En el destino deja el estado `<Target>/synclayer-manifest.json`, con esquema 2 (por
   archivo: hash del origen `sha256`, hash de lo escrito `written` y `level`; con algún alias efectivo, esquema 3, que
   añade `dest`, la ruta real de destino; lee también el esquema 1 y lo migra). Con alias, el agente se escribe en
   `agents/<alias>.md` y el nombre del rol se reemplaza por el alias en los nueve agentes y en `rules/agentes.md` y
   `docs/agentes.md` (el hook no se transforma). La clasificación compara el destino con `written`: igual a lo que se escribiría para el nivel (el origen en el nivel 5) es `IGUAL`, igual a
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
- Alias de agentes (Fase 4, plan `docs/plans/2026-11-22-fase4-nombres-configurables.md`; Fase 4 cerrada
  en la rama, T1 a T8 y cierre; G1/V1 y V2 del propietario pendientes): `install.ps1` lee y valida la clave `aliases` de `synclayer-config.json` (lectura única;
  `Get-AliasTableProblem`, V1 a V8, tabla entera antes de escribir; líneas `Alias:`) y, desde T5, la APLICA de
  punta a punta (la guardia temporal de T2 se retiró). Con alias reales el efecto en Claude Code real NO está
  verificado (G1/V1 del propietario: renombrar un agente, `effort:`, caso P10): no lo documentes como probado.
  `$ReservedAliases` son nueve
  nombres cerrados (los siete integrados, `fork` y `output-style-setup`) y puede quedarse atrás frente a
  integrados nuevos. La referencia independiente es `tests/aliases_ref.py` y la prueba `tests/test_aliases.py`. Límite de palabra
  del reemplazo (enmienda E1): letra = `[A-Za-z0-9_]` o la pareja UTF-8 `C3 80` a `C3 BF` sobre texto
  decodificado ISO-8859-1; el resto es límite (comillas angulares, `¿¡`, rayas, espacio duro, marcas
  combinantes). `scribe` es subcadena de `escribe`, `describe`, `reescribe`, `sobrescribe`: sin límite de
  palabra se rompen. Cuidado al editar con la herramienta Bash: colapsa `\\` a `\` y los escapes `\u00xx`
  pasan a ser el carácter; construye la barra con `chr(92)` y verifica que el archivo no gane bytes no ASCII.
  - Rol y ruta (T4): en los Pasos 4 a 9 el rol (`$rel`: clave de manifiesto, niveles, `$outBytes`/`$outHash`,
    mensajes de nivel) va separado de la ruta de destino (`$destRel[$rel]`: leer, escribir, respaldar, verificar
    y clasificar contra `prevByDest`). El bloque `# Alias:` calcula `$destRel` desde la tabla efectiva (sin
    alias efectivo es identidad). El ancla `# Alias:` sigue siendo la línea «# Alias: fin
    del bloque...», tras el cálculo de `$destRel` y antes de `Get-DestRelProblem` (D1 a D7, defensa en profundidad: exit 1
    antes de escribir, también en `-DryRun`; el mensaje nombra el rol, no la ruta). Las filas `HUERFANO`
    llevan `Path = $null`.
  - Estado con esquema 3 (T3, T4): `Read-State` lo lee (campo `dest` por entrada, la ruta real de destino).
    `ConvertTo-StateBytes` ESCRIBE el esquema 3 (`dest` en todas las entradas) sólo si algún destino difiere del
    rol; con identidad (sin alias efectivo) escribe el esquema 2. Reglas de `dest` cuando difiere de `path`: `agents/<alias>.md`
    de hasta 74 caracteres (`agents/` + 64 + `.md`, atado por una prueba a la regex del alias), sin colisión
    con el `path` de otra entrada ni con ninguna ruta del manifiesto (`$ManifestPaths`, obligatorio en
    `Read-State`); `dest` se lee con `Get-PropRaw` (estricto) y se valida con `HashSet` ordinales; los
    mensajes usan `Format-SafeShort`. Un esquema 3 inválido es estado AUSENTE: nunca `ACTUALIZAR` ni
    `HUERFANO`. `prevByDest` indexa lo escrito por ruta de destino y el huérfano es el destino previo que ya
    no es destino actual; ningún camino usa `dest` para escribir, respaldar ni borrar.
  - Transformación (T5): funciones puras con autocomprobación `New-AliasRegex`, `ConvertTo-AliasText`,
    `Test-AliasDescriptionLine` y `ConvertTo-AliasBytes`. El bloque `# Alias:` calcula `$destRel` y `$aliasBytes`
    (bytes con alias de los nueve agentes, `rules/agentes.md` y `docs/agentes.md`); `# Nivel:` parte de
    `$aliasBytes` y busca la celda de la tabla por ROL, no por alias. Sin alias efectivo no se llama a la
    transformación y la salida es idéntica a la base. El alias nunca entra en la regex: sólo las formas de los
    roles, escapadas. Límite de palabra E1. `hooks/agent_guard.py` no se transforma y los bloques `hooks:` quedan
    byte a byte. Un frontmatter defectuoso con alias da exit 1 en ambos modos (también `-DryRun`), sin escribir
    nada, y el mensaje nombra el rol; con alias se exige ASCII imprimible en todo el frontmatter y que la línea
    tras `name:` sea `---` o `clave:`. La transformación recorre los nueve agentes aunque sólo uno tenga alias:
    un defecto en uno sin alias también detiene. Un agente sin cuerpo y sin LF final se instala. Pruebas:
    casos 32 a 40 y 56 del plan (`test_f4t5_*` en `tests/test_install.py`). Frontmatter y límites de alias están
    documentados (T8, README: «Alias» y «Límites del instalador»). Límite aceptado: con clave repetida en la tabla gana la última, sin aviso (heredado de T2).
  - Niveles y verificación con alias (T6): con alias, `model:` y `effort:` salen de la celda del ROL (no del
    destino) y `Ajuste:` lleva la ruta de destino. `$verifyWhat` con tabla efectiva no vacía dice `lo esperado
    para el nivel N y los alias` (también en el nivel 5); sin tabla efectiva (vacía o alias igual al rol)
    conserva los textos de siempre. Caso 46: regresión de la salida del nivel 5 sin alias, idéntica byte a byte a
    la de antes de la fase (golden embebido `F4T6_GOLDEN`, calculado con el instalador anterior a la fase;
    normaliza las rutas temporales también en su forma escapada no ASCII). Casos 41 a 45: repositorio real con
    nueve alias en los niveles 5 y 3 (13 archivos: 12 gestionados + estado; ningún nombre de rol en los once
    textos salvo `escribe`, `escriben`, `describe`, `reescribe` y `sobrescribe`), `-DryRun` con alias sin
    escribir nada, el hook con el hash del manifiesto, `hooks:` de `sentinel`, `auditor`, `shield` y
    `debugger` intactos y verificación posterior alterada con exit 4 (`test_f4t6_*` en `tests/test_install.py`).
  - Huérfanos y exit 3 con alias (T7): cada fila `HUERFANO` lleva `RenamedTo`: el destino actual del rol si el
    rol de la entrada previa sigue en el manifiesto; si no, es un huérfano clásico. Un huérfano por cambio de
    nombre da un aviso por stderr, uno por archivo, sólo si el archivo existe (`File.Exists`; nunca se abre,
    respalda ni borra), en `-DryRun` y en ejecución real, sin cambiar el exit code. La nota por stdout «ya no
    están en el manifiesto» sale sólo si hay algún huérfano clásico (texto sin cambio). Exit 3: se añade «Si el
    archivo es un agente tuyo con el mismo nombre que un alias, elige otro alias.» sólo si algún `MODIFICADO`
    está en una ruta con alias (destino distinto del `path`), antes de la frase final de `model:`/`effort:`,
    que sigue siempre al final. Sin alias la salida es idéntica a la base (14 escenarios comparados byte a
    byte). `synclayer-config.json` nunca se escribe ni se respalda. Pruebas: 19 `test_f4t7_*` (S1 a S12, casos
    50 a 53) y aserciones nuevas en el caso 20 de T3. Con alias reales el efecto en Claude Code real sigue sin
    verificar (G1/V1).
  - Límite conocido: `Get-Prop` desenrolla listas de un elemento, así que `path`, `sha256`, `written`,
    `level`, `schema`, `algorithm` y `eol` del estado y del manifiesto aceptan `[valor]` (laxitud heredada de
    las Fases 1 y 3, no es un hueco). `Get-PropRaw(...).Value` no desenrolla: `dest` y los campos de la
    configuración se leen así y son estrictos. Decisión P11 (2026-11-23): se documenta y se corrige en una tarea
    aparte tras la Fase 4 (`Get-PropRaw(...).Value` en `Get-ManifestEntries`, `Read-Manifest` y `Read-State`,
    con prueba roja primero); no la corrijas dentro de la Fase 4. Backlog:
    `docs/plans/2026-11-19-backlog-configuracion-y-reportes.md`.
  - Contrato con las pruebas y convenciones del código de alias:
    - `$AliasRoles`, `$ReservedAliases` y `$YamlWords` son listas (una por línea, como `$LevelAgents`) que las
      pruebas leen con `read_ps_list`. Las anclas de `patch_script` (inyecta código tras ellas) son sólo el
      comentario `# Alias:` (la línea «# Alias: fin del bloque...», que no tiene la forma `# Paso N:`) y
      `function ConvertTo-AliasBytes`. No renombres ni muevas nada de esto sin ajustar `tests/test_install.py` y
      `tests/test_aliases.py`.
    - Diccionarios y conjuntos ordinales (`Dictionary[string,string]` y `HashSet[string]` con
      `StringComparer.Ordinal`) para formas, `$destRel`, `$dests`, `$prevByDest` y la validación de `dest`; un
      `@{}` de PowerShell compara sin distinguir mayúsculas. Las expresiones regulares van sin `IgnoreCase`.
    - `Read-State` exige `$ManifestPaths` (lanza si es `$null`): sin él no puede aplicar la regla de colisión
      de `dest` con el manifiesto. Los mensajes de `Read-State` y `Get-ManifestEntries` pasan por
      `Format-SafeShort` (40 caracteres y escapado), no por `Format-Safe`.
    - El `Alias:` de la salida no casa con la expresión `LINE` de las pruebas; sin alias no aparece ninguna
      línea nueva.
  - No obvio, alias: rol frente a ruta de destino (el rol es la clave de manifiesto, nivel, `$outBytes`,
    `$outHash` y `path` del estado; la ruta de destino, lo que se lee, escribe, respalda y verifica; no los
    mezcles, el nivel dejaría de encontrar la celda en silencio). Alias primero y nivel después:
    `ConvertTo-LevelBytes` no cambia y recibe los bytes con alias. El límite de palabra trabaja sobre
    ISO-8859-1 y sólo cuenta como letra `[A-Za-z0-9_]` y la pareja `C3` más un byte de `80` a `BF`.
    `$ReservedAliases` es una lista cerrada de nueve que hay que revisar cuando Claude Code añada integrados
    (`output-style-setup` se reserva por prudencia, sin verificar). V8 sólo ve las rutas del manifiesto: no ve
    archivos propios del usuario en `<Target>/agents/` (un agente suyo con el mismo `name:` que un alias no se
    detecta; caso P10, documentado, G1 pendiente). El tope de 74 de `dest` sale de la regex del alias
    (`agents/` + letra + `{0,63}` + `.md`) y una prueba los ata: si cambias uno, cambia el otro.
  - El texto de `docs/agentes.md` y de `rules/agentes.md` se TRANSFORMA al instalar: una palabra igual a un rol
    (en minúscula, Capitalizada o MAYÚSCULAS) en esos archivos se reemplaza por el alias, también en código en
    línea. Al editarlos usa `<rol>` y `<alias>` como ejemplo, nunca un nombre de rol. El inventario de
    `tests/test_aliases.py` (`INVENTORY`) falla si aparece una forma nueva o cambia un conteo: actualízalo en el
    mismo cambio. `README.md`, `HISTORY.md`, `docs/plans/` y `docs/brand/` no se instalan ni se transforman.
- Carpeta de planes (Fase 5, plan `docs/plans/2026-11-24-fase5-configuraciones-dinamicas.md`; en curso, T1
  a T4 hechas): `install.ps1` define `$PlansDirDefault`, `$PlansDirPattern` y `$PlansDirMaxLength` junto a
  `$AliasRoles`. La referencia es `tests/plans_ref.py` (contrato: `script_constants` lee esas tres
  constantes de `install.ps1`) y las pruebas `tests/test_plans.py` (casos 1 a 9 y 31, sin PowerShell). El
  inventario falla si aparece una forma `<segmento>/plans/` distinta de `docs/plans/` (un alias válido podría
  crear o destruir el literal; de eso depende el orden alias, planes, nivel).
  - T2 (hecha): `install.ps1` lee `plans_dir` en la lectura única de la configuración
    (`$script:ConfigPlansPair`, con `Get-PropRaw`: tipo estricto) y la valida con `Get-PlansDirProblem` (L1 a L5;
    función pura, motivo fijo, nunca el valor) después de la tabla de alias y antes del Paso 3: exit 1 también con
    `-DryRun`, antes de escribir. Carpeta efectiva = valor válido distinto de `docs/plans`; sólo entonces imprime
    `Planes: <valor>` (tras `Nivel:` y `Alias:`; no casa con `LINE`). Sin la clave o con
    `docs/plans`, la salida es idéntica a la base byte a byte. Medido en 5.1: con `plans_dir` repetido gana la
    última, sin aviso; cualquier `__type`, también dentro de un valor, da `clave desconocida: __type` (por eso
    `docs/a__type` se rechaza). Pruebas: 3 estáticas y 19 `test_f5t2_*` en `tests/test_install.py`. Abierto a
    propósito (Low): la clave repetida no avisa.
  - T3 (hecha): la carpeta se APLICA (la guarda temporal de T2 ya no existe). Funciones puras con autocomprobación
    `Get-PlansMatchIndexes` (recorrido manual con `IndexOf` ordinal), `ConvertTo-PlansText` y `ConvertTo-PlansBytes`
    (`$Bytes`, `$Kind` `agent` o `text`, `$PlansDir`): cambian el literal `docs/plans/` por `<carpeta>/` si no lo
    precede un carácter de `[A-Za-z0-9_./-]`, en una sola pasada. En un agente, un literal dentro del frontmatter
    lanza `referencia a la carpeta de planes en el frontmatter`; la función revalida la carpeta por su cuenta con el
    motivo fijo `la carpeta de planes no es valida`. Un error sale como exit 1 antes de escribir (también en
    `-DryRun`): `error: no se puede aplicar la carpeta de planes a <rol>: <motivo>. No se escribio nada.` El bloque
    `# Planes:` va entre el bucle que calcula `$aliasBytes` y `# Nivel:` (el ancla es una sola línea; `# Nivel:` no
    se edita), reescribe `$aliasBytes[$rel]` en su sitio y recorre los nueve agentes y `rules/agentes.md` y
    `docs/agentes.md`. Orden: alias, planes, nivel. Sin carpeta efectiva (sin clave o `docs/plans`) no se llama a la
    transformación y bytes y salida son idénticos a la base. El hook no se transforma; frontmatter y `hooks:`
    quedan intactos. Hash, clasificación y `written` del estado van sobre el texto transformado; los bytes con
    carpeta no los cubre el hash del manifiesto: se verifican contra `$outHash`. `$verifyWhat` con carpeta efectiva
    dice `lo esperado para el nivel N y la carpeta de planes` (con alias, `... N, los alias y la carpeta de planes`).
    El eco `Planes:` pasa por `Format-Safe`. El estado no guarda la carpeta: no hay «carpeta anterior» en la
    salida. Con carpeta efectiva la copia inversa `~/.claude` -> repo no vale. Pruebas: 37 `test_f5t3_*`. El efecto
    en Claude Code real (que `atlas` use la carpeta) NO está verificado (G1): no lo documentes como probado.
  - T4 (hecha): SOLO pruebas; `install.ps1` no cambió. 10 `test_f5t4_*` en `tests/test_install.py` con los
    helpers `f5t4_repo`, `f5t4_state_by_path` y `f5t4_split`. Cubren alias + nivel + carpeta con el repositorio
    real (nueve alias, niveles 5 y 3, ningún nombre de rol residual, las 6 permutaciones del orden alias/planes/
    nivel contra la salida instalada, con `segment_problems` vacío como condición previa), la celda del ROL en
    `model:`/`effort:` y `Ajuste:` con la ruta de destino, `-DryRun` sobre una instalación existente, K1 a K3
    (carpeta agregada, cambiada, quitada: `ACTUALIZAR`, nunca `MODIFICADO` sobre un destino intacto; con y sin
    alias; repo real = 3 `ACTUALIZAR` y 9 `IGUAL`), K4 (edición a mano: exit 3 con sus frases en orden, y
    `-Force`), K5 (estado ilegible, vacío, esquema 99 o ausente: nunca `ACTUALIZAR`), K6 (reinstalar lo mismo no
    cambia nada, ni línea nueva salvo `Planes:`), alias quitados con carpeta (huérfanos intactos, el estado vuelve
    al esquema 2) y la configuración nunca escrita ni respaldada. Abiertos a propósito (Minor, aserciones
    opcionales): respaldo del estado y de los otros nueve archivos en K1 a K3 del repo real, aserto redundante
    del esquema 2 y respaldo del estado ilegible con `-Force` final en K5.
- Niveles de esfuerzo (Fase 3, plan `docs/plans/2026-11-20-fase3-esfuerzo-configurable.md`). Estado: fase
  cerrada (T1 a T7 y cierre); G1 pendiente. Los niveles 1 a 4 se aplican (el instalador
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
  - `<Target>/synclayer-config.json` (opcional, campo `level` de 1 a 5, sin archivo o `{}` = 5; la clave `aliases` es de la Fase 4) es entrada
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
  - Contrato de T5: `Nivel anterior: M` sólo con estado previo válido cuyas entradas tienen todas el
    mismo nivel M distinto del actual (nunca sin estado, con el mismo nivel ni con niveles mezclados). El
    mensaje del exit 3 termina SIEMPRE con «Si cambiaste model: o effort: a mano, usa
    synclayer-config.json.», aunque el `MODIFICADO` no tenga `model:` (el hook) o se haya perdido el
    estado (entonces el arreglo es `-Force`). Una edición a mano es `MODIFICADO` en cualquier nivel y
    archivo, incluidos los fijos; con estado ilegible, ausente o de esquema desconocido nunca hay
    `ACTUALIZAR`. Tras un fallo parcial el estado queda desfasado: cambiar de nivel entonces da
    `MODIFICADO` en lo ya copiado; repite antes con el mismo nivel. Casos 31 a 37 del plan: pruebas
    `test_t5_case31`..`case37` en `tests/test_install.py`.
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
- pwsh no está instalado: las pruebas contra pwsh se saltan (365 en la última corrida; las otras 2 saltadas son de la rama POSIX del reporte de uso).
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
