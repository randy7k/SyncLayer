# Plan: Fase 2, reporte de uso de agentes (`tools/usage_report.py`)

Fecha: 2026-11-19. Estado: propuesto, pendiente de aprobación del propietario.

Fuentes: [`2026-11-19-fase2-reporte-de-uso-exploracion.md`](2026-11-19-fase2-reporte-de-uso-exploracion.md)
(decisiones y riesgos) y [`2026-11-19-backlog-configuracion-y-reportes.md`](2026-11-19-backlog-configuracion-y-reportes.md)
(«Restricción de diseño: simple»).

## 1. Objetivo

Una herramienta de línea de comandos, de biblioteca estándar, que lee las transcripciones
locales de Claude Code (`~/.claude/projects/`) y escribe dos reportes Markdown con conteos y
métricas de uso de subagentes:

- **Reporte de proyecto:** un `.md` local dentro del proyecto, fuera de git.
- **Reporte global:** un `.md` en `~/.claude/`, con todos los proyectos bajo alias, para
  comparar conjuntos de subagentes y skills con métricas comparables.

La herramienta lee sólo claves numéricas y nombres. Nunca copia contenido de conversaciones
ni rutas. Ante un formato que no reconoce, falla con un mensaje claro y no escribe nada.

### Decisiones ya tomadas (no se reabren)

1. Fuente de datos: script que lee las transcripciones. El hook registrador va después, como
   task final separada (T9).
2. Reporte de proyecto local y fuera de git; reporte global en `~/.claude/`.
3. Tablas y barras de texto en Markdown, sin dependencias.

### Fuera de alcance

- SVG o cualquier gráfico. OpenTelemetry. `/cost` y `stats-cache.json`.
- Medir calidad del resultado de un agente. Estimar costo en dinero.
- Atribuir tokens a una skill (corre en el contexto de la sesión principal).
- Caché, índice o base de datos de lecturas anteriores. Proceso residente.
- Modificar `settings.json`, `~/.claude/CLAUDE.md` o el `.gitignore` del proyecto del usuario.
- Instalar la herramienta en `~/.claude` (ver 3.9).
- Corregir numéricamente los tokens inflados de las versiones 2.1.310 a 2.1.327: sólo se anota.

### Siguientes (no se diseñan aquí)

- Que el reporte consuma el registro del hook de T9 (duración y herramientas de fuente estable).
- Archivo de alias legibles por proyecto para el reporte global.
- Registro manual de calidad (hallazgos de `auditor` aceptados).

## 2. Supuestos

Los marcados **[G1]** se confirman con datos reales en la compuerta G1, tras T1. Si alguno
resulta falso, la sesión principal corrige esta sección antes de lanzar T2.

1. Python 3.12, sólo biblioteca estándar, siempre `python -B`. Pruebas con `unittest`.
2. **[G1]** Cada llamada a un subagente deja un archivo
   `~/.claude/projects/<proyecto>/<sesión>/subagents/agent-<id>.jsonl` y un
   `agent-<id>.meta.json` con `agentType` (cadena) y `toolUseId`.
3. **[G1]** Cada línea del JSONL es un objeto con `type`, `timestamp` (ISO 8601), `version`
   (versión de Claude Code) e `isSidechain`. Las líneas `type: "assistant"` llevan
   `message.id`, `message.model` y `message.usage` con `input_tokens`, `output_tokens`,
   `cache_creation_input_tokens` y `cache_read_input_tokens` (enteros).
4. **[G1]** Una misma respuesta del modelo puede ocupar varias líneas (una por bloque de
   contenido) que repiten `message.id` y `usage`. Por eso se deduplica por `message.id`.
5. **[G1]** El nombre de la carpeta de proyecto se obtiene de la ruta absoluta sustituyendo
   por `-` cada carácter que no sea `[A-Za-z0-9]` (`c:\NotionGroup\SyncLayer` da
   `c--NotionGroup-SyncLayer`). En Windows la letra de unidad puede variar de caja.
6. **[G1]** La herramienta `Skill` aparece en la sesión principal como bloque `tool_use` de
   nombre `Skill` con `input.skill` (cadena). Si no se confirma, T4 se descarta (ver 4).
7. **[G1]** Los subagentes en segundo plano dejan el mismo par de archivos que los demás.
8. El trabajo se hace en la rama `feat/reporte-de-uso`, con commits sin etiquetas de
   coautoría. Nada personal en archivos, mensajes ni fixtures (usar `~`).
9. Las fechas se interpretan en UTC. El reporte no lleva hora de generación.

## 3. Diseño

### 3.1 Piezas

| Pieza | Ruta | Papel |
|---|---|---|
| Herramienta | `tools/usage_report.py` | Lector, agregación, generadores y CLI. Un solo archivo |
| Generador de transcripciones sintéticas | `tests/usage_synth.py` | Auxiliar de pruebas (no es un `test_*.py`) |
| Pruebas | `tests/test_usage_report.py` | `unittest`, sólo carpetas temporales |
| Hook registrador (T9, opcional) | `tools/usage_logger.py`, `tests/test_usage_logger.py` | Registro de eventos de fuente estable |

Se usa `tools/` porque ya existe para utilidades que no se instalan
(`tools/build_manifest.py`). Un solo módulo: el backlog pide simplicidad y el tamaño esperado
no justifica un paquete. Los mensajes del script van en ASCII, como `build_manifest.py`.

### 3.2 CLI: una herramienta con subcomandos

Opciones consideradas:

| Opción | A favor | En contra |
|---|---|---|
| A. Un script con subcomandos (`argparse`) | Un solo punto de entrada; cada subcomando tiene su destino fijo; ayuda integrada | Un archivo más largo |
| B. Dos scripts (proyecto y global) | Archivos cortos | Lector duplicado o tercer módulo compartido |
| C. Un script con banderas (`--global`) | Corto de escribir | Combinaciones ambiguas (`--global --project-dir`) |

Se elige **A**.

```
python -B tools/usage_report.py inspect  [--claude-dir DIR] [--project-dir DIR]
python -B tools/usage_report.py project  [--project-dir DIR] [--claude-dir DIR] [ventana] [--stdout]
python -B tools/usage_report.py global   [--claude-dir DIR] [ventana] [--stdout]
```

| Parámetro | Por defecto | Efecto |
|---|---|---|
| `--claude-dir` | `~/.claude` | Carpeta de usuario. No se honra `CLAUDE_CONFIG_DIR`, igual que el instalador. Las pruebas la pasan siempre |
| `--project-dir` | Carpeta actual | Proyecto a reportar y donde se escribe el reporte local |
| `--transcripts-dir` | (derivada, ver 3.3) | Repetible. Carpetas de `projects/` a leer cuando la derivación no acierta |
| `--since`, `--until` | Últimos 30 días hasta hoy (UTC), ambos inclusive | Ventana `AAAA-MM-DD` |
| `--all` | apagado | Sin ventana. Incompatible con `--since`/`--until` |
| `--stdout` | apagado | Imprime el reporte (bytes UTF-8 por `sys.stdout.buffer`) y no escribe archivos |
| `--show-paths` | apagado | Permite rutas en los mensajes de error de stderr. Nunca afecta al reporte |

No existe `--out`: los destinos son fijos (3.7), así la herramienta no escribe en rutas
arbitrarias.

Códigos de salida:

| Código | Significado | ¿Escribió algo? |
|---|---|---|
| 0 | Correcto, incluido «sin llamadas en la ventana» | Sí (salvo `--stdout` e `inspect`) |
| 1 | Entorno o datos: falta `projects/`, el proyecto no tiene transcripciones, destino no escribible, enlace o junction en el destino, archivo ajeno en el destino, error no previsto | No |
| 2 | Uso incorrecto (lo emite `argparse`) | No |
| 3 | Esquema desconocido o demasiados archivos dañados | No |

Un error no previsto se convierte en exit 1 e imprime sólo el nombre de la clase de la
excepción: un traceback podría arrastrar contenido.

### 3.3 Qué lee y qué ignora

Recorrido: `os.scandir` sin seguir enlaces. Sólo abre `<sesión>/subagents/agent-*.jsonl`, su
`agent-*.meta.json` y, para T4, `<sesión>.jsonl`. Lectura línea a línea, sin cargar el
archivo entero.

| Origen | Claves que lee | Uso |
|---|---|---|
| `agent-*.meta.json` | `agentType` | Nombre del agente |
| Línea del subagente | `type`, `timestamp`, `version`, `isSidechain` | Clasificar, ventana, versión |
| Línea `assistant` | `message.id`, `message.model`, `message.usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}` | Tokens y modelo |
| Bloques de `message.content` | Sólo `type` e `id` de cada bloque | Contar `tool_use` |
| Sesión principal (sólo T4) | En bloques `tool_use`: `name` e `input.skill` | Contar skills |

Ignora siempre: el texto de `message.content`, `prompt`, `description`, `toolUseResult`,
`cwd`, `gitBranch`, `input` de cualquier herramienta (salvo `input.skill`), y el resto de
claves. El identificador de sesión se usa en memoria para agrupar y nunca se escribe.

Todo nombre que llega al reporte (`agentType`, `model`, skill) pasa por la lista permitida
`^[A-Za-z0-9][A-Za-z0-9._:@/\-]{0,63}\Z`. Lo que no la cumple se sustituye por
`no-valido-<4 hex>`. Así un nombre no puede llevar contenido, rutas con `\` ni romper una
tabla Markdown. El modelo `<synthetic>` (mensajes sin petición real) se excluye de modelos y
de tokens.

Carpeta del proyecto: se deriva con la regla del supuesto 5 y se compara sin distinguir
mayúsculas. Si hay varias coincidencias (`c--` y `C--`), se leen todas. Las sesiones
abiertas desde una subcarpeta o un worktree viven en otra carpeta y no se incluyen salvo con
`--transcripts-dir`. Sin coincidencias: exit 1 con la pista de `--transcripts-dir`.

### 3.4 Lectura defensiva

No hay número de esquema en el JSONL. Se usa una **firma estructural** más la versión.

Tolerado, y contado en la sección «Calidad de los datos» del reporte:

| Situación | Tratamiento |
|---|---|
| Última línea sin terminar (sesión en curso) | Se descarta la línea |
| Subagente sin ninguna línea con `usage` | Cuenta como llamada; queda fuera de las estadísticas de tokens |
| Falta el `.meta.json` | Cuenta como llamada del agente `(sin-meta)` |
| Línea intermedia que no es JSON | El archivo se marca «dañado»: cuenta como llamada y queda fuera de las estadísticas |
| Versión de Claude Code mayor que la última verificada (`VERIFIED_MAX`) | Aviso «versión no verificada» en el reporte |

Esquema desconocido (exit 3, no se escribe nada):

- `usage` presente y no es objeto, o un campo de tokens no es entero no negativo (`bool` no vale).
- `timestamp` ausente o no interpretable en una línea reconocida.
- `.meta.json` presente sin `agentType` de tipo cadena, o que no es un objeto JSON.
- Archivo con líneas JSON válidas y ninguna con `type`.
- Más del 5 % de los archivos de la ventana dañados (`MAX_DAMAGED_RATIO`).

El mensaje de exit 3 dice qué comprobación falló, en cuántos archivos, qué versiones de
Claude Code se vieron y cuál es `VERIFIED_MAX`, y remite a `inspect`. No incluye valores
leídos ni rutas (salvo `--show-paths`).

`inspect` imprime sólo estructura, para confirmar los supuestos [G1]: conteo de sesiones y
de archivos de subagente; nombres de las claves de primer nivel de las líneas, de `message`,
de `usage` y del meta, con su tipo y frecuencia; histograma de `version`, `type` y `model`
(pasados por la lista permitida); líneas `assistant` con `usage` frente a `message.id`
distintos; metas cuyo `toolUseId` coincide con el `id` de un `tool_use` `Agent` o `Task` de
su sesión principal (coinciden / no coinciden); nombres de las claves de `input` en
`tool_use` de nombre `Agent`, `Task` y `Skill`; cuántos `Agent` llevan `run_in_background`;
subagentes sin meta y sin `usage`. De `toolUseResult` sólo comprueba la presencia de una
lista fija (`totalDurationMs`, `totalTokens`, `totalToolUseCount`). Nunca imprime valores de
cadena fuera de los histogramas citados, ni nombres de carpeta.

### 3.5 Métricas

Unidad: **llamada** = un archivo `agent-<id>.jsonl`. Pertenece a la ventana por su primera
marca de tiempo.

| Métrica | Definición |
|---|---|
| Llamadas | Número de archivos de subagente del agente en la ventana |
| Sesiones | Sesiones distintas con al menos una llamada del agente |
| Llamadas por sesión | Llamadas ÷ sesiones, un decimal |
| Peticiones por llamada | `message.id` distintos con `usage` |
| Entrada, salida, caché escrita, caché leída (por llamada) | Suma, sobre los `message.id` distintos, de `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`. De cada `message.id` se toma la última línea |
| Tokens por llamada | Suma de los cuatro anteriores |
| Mediana | Sobre las llamadas con `usage`. Con n par, media de los dos centrales, redondeada a entero (medio hacia arriba) |
| p90 | Rango más cercano: el valor en la posición `ceil(0,9 × n)` de la lista ordenada. Con n < 10 se marca «n pequeño» |
| Modelo real | Conjunto de `message.model` de la llamada. Una llamada con más de uno cuenta como `mixto` |
| Duración aprox. | Última marca de tiempo menos la primera, en segundos. Incluye esperas de herramientas y de permisos |
| Herramientas por llamada | Bloques `tool_use` con `id` distinto |
| Repeticiones consecutivas (inferido) | Dentro de una sesión, llamadas ordenadas por inicio: una llamada cuenta si la anterior es del mismo agente y terminó antes de que ésta empezara. Las paralelas no cuentan |

Doble conteo: la deduplicación por `message.id` evita contar varias veces una respuesta
repartida en varias líneas. No se usa `totalTokens` de ningún `toolUseResult`. Lo que no se
puede distinguir es una respuesta reintentada con `message.id` nuevo: el reporte no la corrige.

Versión de Claude Code: el reporte lista las versiones vistas con sus llamadas. Si alguna
cae entre 2.1.310 y 2.1.327, añade el aviso «tokens posiblemente inflados por reintentos
(corregido en 2.1.328)» en la cabecera y en la fila de esa versión.

Conjunto de cada agente:

| Regla | Conjunto |
|---|---|
| Nombre en `SYNCLAYER_AGENTS` (los nueve: `oracle`, `scout`, `atlas`, `forge`, `sentinel`, `auditor`, `shield`, `debugger`, `scribe`) | `SyncLayer` |
| Nombre con `:` | `plugin:<prefijo>` |
| Resto | `otros` (integrados o del usuario) |

Una prueba compara `SYNCLAYER_AGENTS` con los archivos de `agents/*.md`. Un agente de
proyecto con el mismo nombre que uno de SyncLayer cuenta como SyncLayer: se dice en el pie.

### 3.6 Formato de los reportes

Comunes: UTF-8 sin BOM, `LF`, salto final. Primera línea
`<!-- synclayer-usage-report v1 -->`. Filas ordenadas por llamadas descendente y nombre.
Enteros sin separador de miles. Barra de 10 caracteres (`█` y `░`), proporcional al máximo de
la columna, redondeo al más cercano, mínimo un bloque si el valor no es cero. Misma entrada y
mismos argumentos dan los mismos bytes.

**Reporte de proyecto**

1. Título y cita de cabecera: ventana (UTC), sesiones, llamadas, versiones vistas, avisos
   (inflados, versión no verificada) y «reporte local: no lo subas a git».
2. `## Llamadas por agente`: `Agente | Conjunto | Llamadas | Barra | Sesiones | Llamadas/sesión | Repeticiones (inferido)`.
3. `## Tokens por llamada`: `Agente | n | Mediana | p90 | Entrada (med.) | Salida (med.) | Caché escrita (med.) | Caché leída (med.) | Peticiones (med.)`.
4. `## Duración y herramientas`: `Agente | Duración aprox. s (med.) | p90 | Herramientas (med.) | p90`.
5. `## Modelo real`: `Agente | Modelo | Llamadas`.
6. `## Skills` (si T4 entra): `Skill | Invocaciones | Sesiones`, con la nota «no se atribuyen
   tokens a una skill». Si T4 se descarta: una línea «uso de skills: no disponible».
7. `## Versiones de Claude Code`: `Versión | Llamadas | Nota`.
8. `## Calidad de los datos`: conteos de 3.4.
9. `## Cómo leer estos números` (texto fijo): no mide calidad; no mide costo (tokens no es
   factura; la caché leída se cobra distinto); «repeticiones» es una inferencia, no un
   reintento confirmado; la duración incluye esperas; con n pequeño la mediana y el p90 dicen
   poco; los números dependen de un formato interno de Claude Code.
10. Pie: `report_schema: 1`, nombre de la herramienta, `VERIFIED_MAX`, identificador del
    proyecto en el reporte global.

**Reporte global**: las secciones 1 a 10 sobre todos los proyectos, más:

- `## Por conjunto`: `Conjunto | Agentes | Llamadas | Barra | Tokens/llamada (med.) | p90 | Duración aprox. s (med.) | Herramientas (med.)`.
- `## Por proyecto`: `Proyecto | Sesiones | Llamadas | Barra | Tokens (suma)`, con alias (3.7).
- `## Qué compara y qué no`: compara sólo llamadas, tokens por llamada, duración y
  herramientas. No compara calidad del resultado, costo real ni ahorro. Dos conjuntos hacen
  trabajos distintos: menos tokens por llamada no significa mejor. Las skills sólo se
  comparan por número de invocaciones.

Ningún texto del reporte afirma ahorro de tokens (restricción del backlog).

### 3.7 Privacidad y escritura

- El reporte nunca contiene contenido de conversaciones, rutas, nombres de carpeta de
  `projects/`, identificadores de sesión ni ramas de git.
- Alias de proyecto en el global: `p-` más los 8 primeros hexadecimales del SHA-256 del
  nombre de la carpeta en minúsculas. Es estable entre ejecuciones y no necesita estado. No
  es anonimización fuerte: quien conozca la ruta puede recalcularlo. Se documenta así.
- El reporte de proyecto muestra su propio alias en el pie, para ubicarlo en el global.

Destinos fijos:

| Reporte | Ruta | Garantía «fuera de git» |
|---|---|---|
| Proyecto | `<project-dir>/.synclayer/usage-report.md` | La herramienta crea `.synclayer/.gitignore` con una línea `*`. La carpeta se ignora a sí misma |
| Global | `<claude-dir>/synclayer-usage.md` | `~/.claude` no es un repositorio del proyecto |

Opciones consideradas para el reporte de proyecto:

| Opción | A favor | En contra |
|---|---|---|
| A. Carpeta propia que se ignora sola (`.synclayer/.gitignore` con `*`) | No toca ningún archivo versionado ni `.git/`; funciona sin git | Una carpeta nueva en la raíz del proyecto |
| B. Añadir una línea al `.gitignore` del proyecto | Convencional | Modifica un archivo versionado del usuario: sorpresa y diff |
| C. Añadir una línea a `.git/info/exclude` | No aparece en diffs | Escribe dentro de `.git/`; no vale sin git; menos visible |
| D. Escribir en `docs/` y confiar en el usuario | Nada que crear | No garantiza nada |

Se elige **A** (decisión del propietario, P4).

Reglas de escritura:

- Si `.synclayer/.gitignore` existe y no tiene una línea `*`: exit 1. No se edita.
- Si el destino existe y su primera línea no es el marcador de 3.6: exit 1. No se pisa un
  archivo ajeno. Si lo es, se sobrescribe sin respaldo (es un derivado).
- Si `.synclayer`, el destino o `<claude-dir>` es un enlace simbólico o una junction: exit 1.
- Escritura mediante temporal en la misma carpeta y `os.replace`.
- No se crea `<claude-dir>` ni `<project-dir>`. Si falta `<claude-dir>/projects`: exit 1 con
  mensaje claro.
- Permisos: en POSIX el archivo se crea con modo `0600`. En Windows hereda la ACL de la
  carpeta; no se modifica. Se documenta.
- Riesgo residual documentado: `git add -f` puede versionar el reporte igualmente.

### 3.8 Estrategia de pruebas

- `python -B -m unittest discover -s tests`. Las pruebas llaman a `main(argv)` en el mismo
  proceso, con stdout y stderr capturados. Sólo dos o tres casos usan `subprocess` (sin
  shell, con `timeout`) para comprobar la invocación real y `--stdout` en bytes.
- `tests/usage_synth.py` construye en una carpeta temporal un árbol `projects/` sintético con
  `json.dumps`. Nunca hay transcripciones reales en el repositorio.
- Ninguna prueba lee el `~/.claude` real: todas pasan `--claude-dir` y `--project-dir`. Segunda
  barrera: la clase base sustituye la función que calcula el valor por defecto por una que
  falla.
- Carpetas temporales con espacio (`tempfile.TemporaryDirectory(prefix='sync layer ')`).

Casos mínimos:

| # | Caso | Se comprueba |
|---|---|---|
| 1 | Formato desconocido (`usage` como cadena; tokens negativos o `bool`; meta sin `agentType`; sin `type`) | Exit 3; ningún archivo escrito; el mensaje nombra la comprobación |
| 2 | Última línea truncada | Exit 0; contada en «Calidad de los datos» |
| 3 | Línea intermedia corrupta, por debajo y por encima del 5 % | Exit 0 con el archivo «dañado»; exit 3 al superar el umbral |
| 4 | Subagente sin `usage` | Cuenta como llamada; n de tokens no lo incluye |
| 5 | Sin `.meta.json` | Fila `(sin-meta)` |
| 6 | Varias sesiones y varios proyectos | Llamadas, sesiones y llamadas/sesión exactas |
| 7 | Respuesta en varias líneas con el mismo `message.id` | Tokens contados una vez |
| 8 | Repetición consecutiva, y dos llamadas paralelas del mismo agente | La primera cuenta; las paralelas no |
| 9 | Mediana y p90 con n = 1, 2, 9, 10, 11 | Valores calculados a mano |
| 10 | Ventana: llamada en el borde de `--since` y de `--until`; `--all`; ventana vacía | Inclusión correcta; reporte «sin llamadas», exit 0 |
| 11 | **No filtra contenido:** marcadores únicos en `message.content`, `prompt`, `description`, `toolUseResult`, `cwd`, `gitBranch`, `input` de herramientas, nombre de carpeta del proyecto e identificador de sesión | Ningún marcador aparece en el reporte de proyecto, en el global, en stdout ni en stderr, tampoco en los casos de exit 1 y exit 3 |
| 12 | `agentType` o `model` con `\|`, salto de línea, `\` o más de 64 caracteres | Sale `no-valido-<hex>`; la tabla no se rompe |
| 13 | Rutas con espacios; `cwd` sintético con barras invertidas; carpeta `C--` y `c--` a la vez | Derivación correcta; se leen ambas |
| 14 | Determinismo | Dos ejecuciones dan bytes idénticos; `LF`; sin BOM; salto final |
| 15 | Versiones 2.1.309, 2.1.310, 2.1.327, 2.1.328 y una mayor que `VERIFIED_MAX` | Aviso de inflados sólo en el rango; aviso de no verificada |
| 16 | Falta `projects/`; proyecto sin transcripciones | Exit 1; nada escrito |
| 17 | `.synclayer/.gitignore` creado; ya existente sin `*`; destino ajeno sin marcador; destino con marcador | Creación; exit 1; exit 1; sobrescritura |
| 18 | Enlace simbólico en el destino o dentro de `projects/` | Exit 1; el enlace no se sigue. Se salta con motivo claro si el sistema no deja crear el enlace |
| 19 | `--stdout` | No crea archivos; bytes UTF-8 válidos con `█` |
| 20 | `SYNCLAYER_AGENTS` frente a `agents/*.md` | Coinciden |
| 21 | Alias | `p-` + 8 hex; estable; el nombre de la carpeta no aparece |
| 22 | `inspect` sobre el árbol sintético con marcadores | Ningún marcador en la salida; conteos estructurales correctos |

Comprobación con datos reales (sólo el propietario, nunca un agente): compuerta G1 y cierre
C4. La salida no se versiona ni se pega en el repositorio. De G1 sólo pasan al plan hechos
de estructura (nombres de claves, versiones, conteos).

### 3.9 Manifiesto e instalador

La herramienta **no se instala** en `~/.claude` y no entra en el manifiesto: siguen siendo
doce archivos. Motivos: Claude Code no la lee; `tools/` ya es la carpeta de lo que no se
instala; añadir un archivo gestionado obliga a cambiar `ALLOWED` en dos sitios
(`tools/build_manifest.py` e `install.ps1`) y a repetir la revisión de seguridad del
instalador. Se ejecuta desde el clon. `install.ps1`, `install-manifest.json` y
`tools/build_manifest.py` no se tocan en esta fase.

`<claude-dir>/synclayer-usage.md` es un archivo nuevo en `~/.claude`: el instalador no lo
enumera ni lo toca. Se añade a la tabla de archivos de `docs/agentes.md` (archivo gestionado:
al cambiarlo se regenera el manifiesto, en T8).

### 3.10 Hook registrador (T9, opcional)

Va después del cierre del núcleo y sólo si el propietario lo activa (P6). Registra, por
evento de fin de subagente, una línea JSON en `<claude-dir>/synclayer-usage-log.jsonl` con
marca de tiempo, `agent_type`, duración, número de herramientas y versión. Ningún contenido.

Reglas: siempre sale con 0 (no es una guarda; un hook que falla no debe frenar una sesión),
captura cualquier error y no escribe nada en stdout.

`settings.json`: opciones.

| Opción | A favor | En contra |
|---|---|---|
| A. El README instruye al usuario a añadir el bloque `hooks` a mano; el script vive en `tools/usage_logger.py` y el bloque apunta al clon | No cambia la promesa del instalador; manifiesto intacto | Ruta al clon dentro de `settings.json`; si el clon se mueve, el hook deja de registrar en silencio |
| B. El script pasa a ser el archivo gestionado número trece (`hooks/usage_logger.py`); el usuario añade el bloque a mano | Ruta estable `$HOME/.claude/hooks/` | Cambia `ALLOWED`, `install.ps1`, sus pruebas y toda la documentación de «doce» |
| C. El instalador edita `settings.json` | Sin pasos manuales | Rompe la promesa vigente; fusionar JSON ajeno es arriesgado |

Por defecto **A**. C queda descartada salvo decisión expresa del propietario.

## 4. Tareas

Todas secuenciales: T1 a T7 tocan los mismos dos archivos. Cada una sigue el ciclo `forge` +
`auditor`. Reglas para todas:

- Primero la prueba que falla, después la implementación. Python siempre con `-B`.
- **Ningún agente ejecuta la herramienta sin `--claude-dir` apuntando a una carpeta
  temporal.** Los prompts de `forge`, `auditor` y `sentinel` lo dicen de forma explícita.
- Al cerrar cada task, el mismo commit actualiza «Línea de tiempo y avance» del README con la
  aritmética de la sección 4.5.

### Paso previo (sesión principal, no cuenta como unidad)

Al aprobar el plan: en el README, la Fase 2 pasa de «sin desglosar» a «0 de 10» y se crea
«La Fase 2 por frentes». El avance global sigue en 20 %.

### Fase A: lectura

#### T1. `inspect` y generador de transcripciones sintéticas — revisión de seguridad

- **Objetivo:** subcomando `inspect` (3.4) y `tests/usage_synth.py`.
- **Archivos:** crear `tools/usage_report.py`, `tests/usage_synth.py`,
  `tests/test_usage_report.py`.
- **Pasos:** esqueleto del CLI (`argparse`, códigos de salida, captura global de errores);
  recorrido sin seguir enlaces; derivación del nombre de carpeta; lista permitida de nombres;
  `inspect`. El generador sintético admite: varias sesiones y proyectos, líneas repetidas por
  `message.id`, marcadores de contenido, meta ausente, líneas truncadas y corruptas.
- **Pruebas:** casos 13 (derivación), 16 (falta `projects/`), 18 (enlaces), 22.
- **Aceptación:** la suite pasa; `inspect` no escribe archivos; ningún marcador en su salida;
  el script no importa nada fuera de la biblioteca estándar; el valor por defecto de
  `--claude-dir` sólo se calcula si falta el parámetro.
- **Dependencias:** ninguna.

#### G1. Compuerta: verificación con datos reales (propietario; no cuenta como unidad)

- El propietario ejecuta `python -B tools/usage_report.py inspect` y, en SyncLayer, con
  `--project-dir .`. Revisa la salida antes de compartirla con la sesión.
- La sesión principal contrasta la salida con los supuestos [G1] y anota el resultado en una
  sección «Resultado de G1» de este plan (sólo hechos de estructura).
- Resuelve: forma de `tool_input` de `Skill` (supuesto 6: decide si T4 entra), subagentes en
  segundo plano (supuesto 7), relación `toolUseId` con `tool_use` (informativa: el diseño no
  depende de ella), cuántos subagentes no tienen meta.
- Changelog 2.1.311 a 2.1.325: consulta opcional a `scout`. Si no se hace, queda como riesgo
  (sección 5) cubierto por la firma estructural y el aviso de versión.
- Si un supuesto [G1] distinto del 6 resulta falso: se corrige el plan antes de T2. Si el
  cambio altera el diseño (por ejemplo, no existe `message.id`), vuelve a `atlas`.

#### T2. Lector defensivo de subagentes — revisión de seguridad

- **Objetivo:** convertir cada archivo de subagente en un registro de llamada, con la
  política de 3.3 y 3.4.
- **Archivos:** modificar `tools/usage_report.py`, `tests/test_usage_report.py`,
  `tests/usage_synth.py`.
- **Pasos:** registro de llamada (agente, modelos, inicio, fin, cuatro sumas de tokens,
  peticiones, herramientas, versiones, estado: correcta, sin `usage`, sin meta, dañada);
  deduplicación por `message.id`; exclusión de `<synthetic>`; excepción de esquema con exit 3;
  umbral de dañados; fijar `VERIFIED_MAX` con el resultado de G1.
- **Pruebas:** casos 1, 2, 3, 4, 5, 7, 12 (a nivel de registro).
- **Aceptación:** la suite pasa; con exit 3 no se crea ningún archivo; los mensajes de error
  no contienen marcadores ni rutas sin `--show-paths`; el lector no accede a ninguna clave
  fuera de la tabla de 3.3 (lo comprueba `auditor` leyendo el código).
- **Dependencias:** T1, G1.

### Fase B: métricas

#### T3. Agregación y métricas

- **Objetivo:** las métricas de 3.5 sobre una lista de llamadas y una ventana.
- **Archivos:** los mismos tres.
- **Pasos:** ventana en UTC; agregación por agente, por conjunto, por proyecto y por versión;
  mediana y p90 con las reglas exactas de 3.5; repeticiones consecutivas; `SYNCLAYER_AGENTS`.
- **Pruebas:** casos 6, 8, 9, 10, 15 (clasificación de versiones), 20.
- **Aceptación:** la suite pasa; cada valor esperado de las pruebas está calculado a mano en
  un comentario; las funciones de agregación no hacen E/S.
- **Dependencias:** T2.

#### T4. Conteo de skills (condicionada a G1)

- **Objetivo:** invocaciones y sesiones por skill, leyendo de la sesión principal sólo
  `name` e `input.skill` de los bloques `tool_use`.
- **Archivos:** los mismos tres.
- **Pasos:** lectura línea a línea de `<sesión>.jsonl`; deduplicación por `id` del bloque;
  nombre por la lista permitida; misma ventana.
- **Pruebas:** skill invocada dos veces en una sesión y una en otra; marcadores en
  `input.args` y en el resto de la sesión principal que no aparecen en ninguna salida; sesión
  principal con última línea truncada.
- **Aceptación:** la suite pasa; de la sesión principal no se lee ninguna otra clave.
- **Dependencias:** T3. **Si G1 no confirma el supuesto 6, la task se descarta:** la fase
  pasa a 9 unidades y el reporte dice «uso de skills: no disponible».

### Fase C: reportes y CLI

#### T5. Generador del reporte de proyecto

- **Objetivo:** texto Markdown del reporte de proyecto (3.6), sin escribir en disco.
- **Archivos:** los mismos tres.
- **Pasos:** función pura de resumen a texto; barras; secciones 1 a 10; textos fijos de
  «Cómo leer estos números»; marcador y pie.
- **Pruebas:** casos 12 (tabla intacta), 14, 15 (avisos en el texto); barra con máximo, cero
  y valor mínimo distinto de cero; reporte sin llamadas.
- **Aceptación:** la suite pasa; el texto no contiene «ahorro», costos ni afirmaciones de
  calidad; las columnas coinciden con 3.6.
- **Dependencias:** T3 (y T4 si entra).

#### T6. Generador del reporte global — revisión de seguridad

- **Objetivo:** texto del reporte global: secciones comunes más «Por conjunto», «Por
  proyecto» con alias y «Qué compara y qué no».
- **Archivos:** los mismos tres.
- **Pasos:** alias `p-<8 hex>`; reutilizar los generadores de T5; lectura de todas las
  carpetas de `projects/`.
- **Pruebas:** casos 11 (sobre el texto global), 14, 21; dos proyectos sintéticos con
  conjuntos distintos (`SyncLayer`, `plugin:x`, `otros`).
- **Aceptación:** la suite pasa; ningún nombre de carpeta de `projects/` aparece en el texto.
- **Dependencias:** T5.

#### T7. Subcomandos `project` y `global`: escritura — revisión de seguridad

- **Objetivo:** unir lectura, métricas y generadores, y escribir en los destinos de 3.7.
- **Archivos:** los mismos tres.
- **Pasos:** resolución de carpetas (`--project-dir`, `--transcripts-dir`); ventana por
  defecto; `.synclayer/.gitignore`; comprobación del marcador; rechazo de enlaces; temporal y
  `os.replace`; modo `0600` en POSIX; `--stdout`; mensajes finales (ruta escrita, conteos).
- **Pruebas:** casos 11 (de extremo a extremo, incluidos stdout y stderr), 13, 16, 17, 18, 19;
  tras una ejecución correcta no queda ningún temporal; una ejecución con exit 1 o 3 no deja
  `.synclayer/`.
- **Aceptación:** la suite pasa; la herramienta sólo abre para escritura los dos destinos,
  `.synclayer/.gitignore` y sus temporales; no existe forma de escribir en otra ruta.
- **Dependencias:** T6.

### Fase D: documentación y cierre

#### T8. Documentación

- **Objetivo:** documentación al día en el mismo cambio.
- **Archivos:** modificar `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`,
  `install-manifest.json`, `docs/plans/2026-11-19-backlog-configuracion-y-reportes.md`.
- **Pasos:**
  - `README.md`: «Estructura» (`tools/usage_report.py`, pruebas nuevas); sección nueva
    «Reporte de uso» (subcomandos, parámetros, códigos de salida, destinos, qué lee y qué no,
    cómo leer los números); sección «Límites del reporte de uso» (formato interno sin
    garantía, tokens inflados entre 2.1.310 y 2.1.327, alias que no es anonimización fuerte,
    `git add -f`, sesiones de subcarpetas, repetición inferida, sin calidad ni costo);
    «Instalación» (la herramienta no se instala); «Pruebas» (conteo tomado de la salida real).
  - `CLAUDE.md`: comandos; arquitectura (pieza nueva); convención (todo cambio en
    `tools/usage_report.py` empieza con una prueba que falla; ningún agente la ejecuta contra
    el `~/.claude` real); no obvios (deduplicación por `message.id`, exit 3, destinos fijos,
    carpeta que se ignora sola, UTC).
  - `HISTORY.md`, `[Sin publicar]`: «Añadido (reporte de uso)» y la lista «Siguientes».
  - `docs/agentes.md`: fila para `~/.claude/synclayer-usage.md` y uso del reporte. Después,
    regenerar el manifiesto con `python -B tools/build_manifest.py`.
  - Backlog: estado de la Fase 2.
- **Pruebas:** suite completa.
- **Aceptación:** la suite pasa (incluida la prueba de sincronía del manifiesto); ningún
  documento promete ahorro, medición de calidad, costo real ni anonimato; los doce archivos
  gestionados siguen siendo doce; nada personal en los textos.
- **Dependencias:** T7.

#### Cierre del núcleo (lo coordina la sesión principal; cuenta como una unidad)

- **C1. `sentinel`:** suite completa con la salida a la vista; los 22 casos de 3.8 cubiertos.
- **C2. `shield`:** revisión de T1, T2, T6 y T7. Aplica: lee datos sensibles de la carpeta de
  usuario, procesa entrada no confiable y escribe archivos. Focos: fuga de contenido o rutas
  por reporte, stdout, stderr o excepciones; nombres que escapan de la lista permitida;
  enlaces y junctions en lectura y escritura; carrera entre comprobar y escribir; archivos
  enormes o líneas gigantes (memoria); que la documentación no prometa anonimato.
- **C3. `auditor`** sobre el cambio completo.
- **C4. Verificación real (propietario, fuera del conteo):** `project --stdout --all` en
  SyncLayer y `global --stdout`. Comprobar: el número de llamadas coincide con el número de
  archivos `agent-*.jsonl`; una llamada elegida a mano suma los mismos tokens; el reporte no
  contiene nada reconocible de una conversación; tiempo de ejecución sobre el total (objetivo:
  menos de 60 s con unos 3 000 archivos). Después, ejecución real sin `--stdout`.

### Fase E: hook registrador (opcional)

#### T9. Hook registrador `usage_logger.py` — revisión de seguridad

- **Objetivo:** registro de fuente estable según 3.10, con la opción A de `settings.json`.
- **Requisito previo (sesión principal):** decisión P6 del propietario y una consulta a
  `scout` sobre el payload de `SubagentStop` y de `PostToolUse` para `Agent` (campos
  disponibles; subagentes en segundo plano; si `SubagentStart` vale en frontmatter).
- **Archivos:** crear `tools/usage_logger.py`, `tests/test_usage_logger.py`; modificar
  `README.md`, `CLAUDE.md`, `HISTORY.md`.
- **Pasos:** leer el JSON del hook por stdin; extraer sólo los campos de 3.10 con la lista
  permitida de nombres; añadir una línea al registro; salir siempre con 0. El README da el
  bloque `hooks` que el usuario pega en `settings.json`, cómo quitarlo y el aviso de que la
  ruta apunta al clon. Se mantiene escrito que el instalador no toca `settings.json`.
- **Pruebas:** payload con marcadores de contenido que no llegan al registro; entrada
  inválida, vacía o gigante da exit 0 y no escribe; carpeta de destino ausente da exit 0;
  nombre no válido sustituido; líneas del registro en JSON válido y `LF`; todo contra una
  carpeta temporal (`--claude-dir`).
- **Aceptación:** la suite pasa; el script nunca sale con un código distinto de 0; no escribe
  en stdout; el manifiesto no cambia.
- **Cierre propio:** `shield` y `auditor` sobre T9.
- **Dependencias:** cierre del núcleo. Sus archivos de código son disjuntos de los de T1 a T8,
  pero comparte README y CLAUDE.md: se ejecuta en secuencia.

### 4.5 Unidades y aritmética de la línea de tiempo

La Fase 2 tiene **10 unidades**: T1 a T9 más el cierre del núcleo. G1, C4 y el paso previo no
cuentan.

| Frente | Unidades |
|---|---|
| Lectura | 2 (T1, T2) |
| Métricas | 2 (T3, T4) |
| Reportes y CLI | 3 (T5, T6, T7) |
| Documentación y cierre | 2 (T8, cierre) |
| Hook registrador | 1 (T9) |

Con k unidades cerradas: Fase 2 = k × 10 %. Proyecto completo = (100 + k × 10) ÷ 5 = 20 + 2k %.

| k | Fase 2 | Cuadros | Global | Cuadros |
|--:|--:|--:|--:|--:|
| 0 | 0 % | 0 | 20 % | 2 |
| 1 | 10 % | 1 | 22 % | 2 |
| 2 | 20 % | 2 | 24 % | 2 |
| 3 | 30 % | 3 | 26 % | 3 |
| 4 | 40 % | 4 | 28 % | 3 |
| 5 | 50 % | 5 | 30 % | 3 |
| 6 | 60 % | 6 | 32 % | 3 |
| 7 | 70 % | 7 | 34 % | 3 |
| 8 | 80 % | 8 | 36 % | 4 |
| 9 | 90 % | 9 | 38 % | 4 |
| 10 | 100 % | 10 | 40 % | 4 |

Si T4 se descarta en G1, o el propietario retira T9, la fase pasa a 9 unidades (u 8) y se
recalcula: Fase 2 = k ÷ 9, global = (100 + 100 × k ÷ 9) ÷ 5.

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| El formato interno del JSONL cambia sin aviso | Firma estructural y exit 3 (3.4); `VERIFIED_MAX` y aviso de versión no verificada; `inspect` para diagnosticar; T9 como fuente estable futura |
| Las transcripciones sintéticas no reflejan el formato real | Compuerta G1 antes de T2; C4 al cierre |
| Fuga de contenido o rutas | Lista cerrada de claves (3.3); lista permitida de nombres; caso 11 sobre reportes, stdout y stderr; errores sin traceback; `shield` (C2) |
| Un agente ejecuta la herramienta contra el `~/.claude` real | Regla en todos los prompts; pruebas con `--claude-dir` obligatorio y segunda barrera; la salida real no se versiona |
| Tokens inflados entre 2.1.310 y 2.1.327 | Deduplicación por `message.id`; aviso por versión; sin corrección numérica, dicho en el reporte |
| Versiones 2.1.311 a 2.1.325 sin revisar | Consulta opcional a `scout` en G1; la firma estructural no depende de la versión |
| Doble conteo por líneas repetidas | Deduplicación por `message.id`; caso 7; G1 mide líneas frente a identificadores |
| Rendimiento con miles de archivos | Lectura línea a línea, sin caché; medición en C4 (objetivo 60 s). Si se supera: prefiltro por fecha de modificación como mejora posterior, no en esta fase |
| Línea gigante (imagen en base64) agota la memoria | Foco de `shield`; si se confirma, límite de tamaño por línea con conteo en «Calidad de los datos» |
| El usuario lee los números como calidad, costo o ahorro | Sección fija «Cómo leer estos números» y «Qué compara y qué no»; «inferido» y «aprox.» en los encabezados; marca «n pequeño» |
| La repetición consecutiva se toma por reintento real | Etiqueta «inferido»; las paralelas no cuentan; explicación en el reporte |
| La duración incluye esperas de permisos | Etiqueta «aprox.»; T9 daría la duración de fuente estable |
| El alias se toma por anonimato | Documentado: hash sin sal, recalculable; el reporte es local |
| El reporte local acaba en git | Carpeta que se ignora sola; aviso en la cabecera; `git add -f` documentado como residual |
| Se pisa un archivo ajeno | Marcador de primera línea; destinos fijos; sin `--out` |
| Sesiones de subcarpetas o worktrees quedan fuera | Documentado; `--transcripts-dir` |
| Subagentes antiguos sin meta | Fila `(sin-meta)`; G1 los cuantifica |
| Consola de Windows no codifica `█` | `--stdout` escribe bytes UTF-8 |
| Un agente de proyecto homónimo cuenta como SyncLayer | Nota en el pie |
| El hook de T9 frena o rompe sesiones | Siempre exit 0; captura total de errores; opcional y posterior al cierre |
| Ruta al clon en `settings.json` deja de valer en silencio | Documentado en T9; alternativa B de 3.10 |

## 6. Preguntas abiertas

Cada una tiene un valor por defecto, que es lo que el plan implementa si no hay respuesta.

- **P1. Nombre e invocación.** Por defecto: `python -B tools/usage_report.py <inspect|project|global>`
  desde el clon. Alternativa: instalarla en `~/.claude` (archivo gestionado número trece;
  reabre el instalador).
- **P2. Ventana por defecto.** Por defecto: últimos 30 días (UTC). Alternativas: 7 días, o
  todo el historial.
- **P3. Alias en el global.** Por defecto: `p-<8 hex>` y el reporte de proyecto muestra el
  suyo. Alternativas: archivo de alias legibles (más estado que mantener) o un parámetro que
  muestre los nombres reales de carpeta.
- **P4. Ubicación del reporte local.** Por defecto: `<proyecto>/.synclayer/usage-report.md`
  con `.synclayer/.gitignore` propio. Alternativas: `docs/` más una línea en el `.gitignore`
  del proyecto, o `.git/info/exclude`.
- **P5. Cuándo corre.** Por defecto: sólo a mano. Alternativa: engancharlo a un hook
  `SessionEnd` o al instalador (más superficie; no recomendado).
- **P6. Hook registrador (T9).** Por defecto: se hace tras el cierre, con el script en
  `tools/` y el bloque de `settings.json` añadido a mano por el usuario (opción A de 3.10).
  Alternativas: archivo gestionado número trece (opción B) o retirar T9 de la fase.

## Decisiones tras la compuerta G1 (2026-11-20, aprobadas por el propietario)

Detalle y cifras en [`2026-11-20-fase2-g1-resultado.md`](2026-11-20-fase2-g1-resultado.md). Estas decisiones **prevalecen** sobre el texto anterior de este plan donde se contradigan.

1. **Hardlinks (T2).** El lector de subagentes **acepta** archivos con `nlink > 1` cuando el nombre pasa la lista permitida (`agent-<id>.jsonl` bajo `subagents/` de una sesión válida) y la firma estructural; los cuenta aparte como «hardlinks aceptados: N» (Claude Code los crea: 122 de 2 868 transcripciones de subagentes en el equipo del propietario, con el otro enlace fuera de `projects/`). Se siguen rechazando enlaces simbólicos y puntos de reanálisis. `inspect` sigue sin leerlos pero los cuenta como «hardlinks (nlink > 1)» separados de «enlaces omitidos», para que el diagnóstico los distinga. El riesgo residual (un proceso del mismo usuario que planta un hardlink a otro archivo) queda como Low documentado: el lector sólo toma claves numéricas y nombres de lista cerrada y exige la firma estructural.
2. **Versiones (T3).** Las métricas de tokens se **desglosan por rango de versión** de Claude Code: anterior a 2.1.310, de 2.1.310 a 2.1.327 y desde 2.1.328, con la advertencia de que comparar entre rangos es indicativo (el 60 % de las líneas de subagentes cae en el rango dudoso). La versión de cada llamada sale del campo `version` de sus líneas.
3. **Agente sin `subagent_type`** (220 de 2 866 llamadas): se clasifica como agente por defecto, no es un error. La fuente del tipo de agente es `meta.agentType` (2 746 de 2 746).
4. **Líneas sobredimensionadas descartadas:** no aportan tokens y se cuentan aparte.
5. **Pendientes de `shield` que entran en T2:** un archivo omitido a mitad de lectura no deja líneas contadas (acumular por archivo y fusionar sólo si termina bien); una sesión cuyo único archivo es un hardlink de la sesión principal no cuenta como sesión leída si no se leyó ningún archivo, o se documenta.
6. **`safe_name`** no se reutiliza para texto visible: si T2 necesita mostrar `agentType` usa una lista permitida estrecha (sin `@`, `/`, `:`) o una lista cerrada de agentes conocidos, y nunca un hash de 16 bits.

## Notas obligatorias para T3 en adelante (revisión de T2, 2026-11-20)

Salen de la revisión de `auditor` sobre T2 y prevalecen donde contradigan el texto anterior.

1. **Agrupar por `(agent, agent_group)`**, nunca sólo por nombre: `(otro agente)` lo comparten los agentes de usuario (`otros`) y los de plugin con prefijo no válido; los plugins válidos salen como `plugin:<prefijo>`.
2. **Ventana y daño.** T3 llama a `read_calls(check_damage=False)` y aplica `check_damaged` sobre las llamadas de la ventana (el 5 % se mide sobre los archivos de la ventana, no sobre todo el historial). Las llamadas sin `start` usan `fallback_time` (mtime aproximado) para ubicarse en la ventana.
3. **Qué entra en cada métrica.** Tokens y medianas: sólo llamadas con `usable` y `requests > 0`. Duración y herramientas: todas las que no estén `excluded` (`damage is None`), incluidas las `sin_usage`. Una llamada dañada conserva `tools`, `start`, `end`, `models` y `versions` pero queda fuera de las estadísticas.
4. **Archivos con todos los ids repetidos** (`requests = 0`, tokens 0, `usable=True`) no entran en medianas ni p90; el arreglo previo a T3 es `usable = has_usage and damage is None and requests > 0` (o un campo `repeated_requests` para que T3 decida). La deduplicación entre archivos atribuye el id al archivo que se recorre primero (orden alfabético), no al de inicio más temprano: documentarlo y, si es barato, atribuir al más temprano.
4b. **Hardlinks dentro de `projects/`.** Si dos nombres del mismo inodo aparecen dentro de `projects/` cuentan hoy como dos llamadas: recordar `(st_dev, st_ino)` de los archivos con `nlink > 1` y contar el duplicado aparte, sin crear llamada.
5. **Avisos del reporte** (T5): si `usage sin message.id` > 0 o `message.id repetido entre archivos` > 0 o se superó `MAX_IDS_GLOBAL`, el reporte lo muestra como aviso en la cabecera. Si en la corrida real (C4) `message.id repetido entre archivos` sale mayor que 0, esto sube a Important.
6. **Privacidad del prefijo de plugin.** `plugin:<prefijo>` sólo valida el alfabeto, no el contenido: revela nombres de plugins privados en un global compartible. Riesgo aceptado y documentado en 3.7, el README y el pie del reporte global; T6 valora una opción que agrupe plugins como `plugin:<4 bytes de hash>`.
7. **Desglose por versión** de Claude Code (decisión G1 2): tres rangos (anterior a 2.1.310, 2.1.310–2.1.327, desde 2.1.328).
8. **Liberar `ReadResult._seen_ids`** al terminar `read_calls` (`res._seen_ids = None`).
9. **Prueba de claves (`keys_used_by`):** que también falle ante `.items()`, `.values()`, `.keys()` y subíndices o `.get` con un argumento `Name` fuera de una lista de nombres permitidos.
10. **`read_calls(project_dir=...)` sin carpeta coincidente** devuelve vacío: T7 debe convertirlo en exit 1 con la pista de `--transcripts-dir` (§3.3).
11. **`CHK_TS`** (exit 3 si una línea `user`/`assistant` no trae `timestamp`) no está confirmado con datos reales: verificarlo en C4; si falla con datos sanos, relajarlo.
