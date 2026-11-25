# Plan: Fase 5, otras configuraciones dinámicas (carpeta de planes, idioma del reporte de uso, perfiles por proyecto)

Fecha: 2026-11-24. Estado: **aprobado por el propietario el 2026-11-24, con los valores por defecto
de P1 a P14**. Rama: `feat/configuraciones-dinamicas`. Avance: T1 cerrada (2026-11-24): tres constantes sin uso en `install.ps1`, `tests/plans_ref.py` y `tests/test_plans.py`
(43 pruebas, casos 1 a 9 y 31). T2 cerrada (2026-11-24): clave `plans_dir` leída y validada (`Get-PlansDirProblem`,
L1 a L5) con guarda temporal que impide aplicarla; 22 pruebas nuevas (3 estáticas y 19 `test_f5t2_*`), suite de 1663 pruebas. T3 cerrada (2026-11-24): `plans_dir` se aplica al instalar (`Get-PlansMatchIndexes`,
`ConvertTo-PlansText`, `ConvertTo-PlansBytes`, bloque `# Planes:`), guarda temporal retirada; 37 pruebas `test_f5t3_*`,
suite de 1695 pruebas, 357 saltadas. T4 cerrada (2026-11-24): sólo pruebas (10 `test_f5t4_*` en `tests/test_install.py`;
`install.ps1` no cambió), suite de 1715 pruebas, 367 saltadas. T5 cerrada (2026-11-24): catálogo de textos del reporte
de uso (`LANGS`, `DEFAULT_LANG`, `CATALOG`; generadores con `t["clave"]`; español idéntico byte a byte contra
`tests/usage_golden_es.json`), sin `--lang` (es de T6); suite de 1735 pruebas, 367 saltadas. T6 cerrada (2026-11-25):
catálogo `en` (137 claves por idioma), parámetro `lang` de los dos generadores y `--lang es|en` en `project` y `global`;
golden `tests/usage_golden_en.json`; suite de 1790 pruebas, 367 saltadas. T7 cerrada (2026-11-25): sección «Perfiles
por proyecto» del `README.md` y ampliación de «Adaptar un agente a un proyecto» en `docs/agentes.md`; 13 pruebas
nuevas en `tests/test_phase5_docs.py` (casos 44 a 46), manifiesto regenerado, suite de 1803 pruebas, 367 saltadas
(suite completa: 1803 pruebas, OK, 367 saltadas).

Fuentes: [`2026-11-19-backlog-configuracion-y-reportes.md`](2026-11-19-backlog-configuracion-y-reportes.md)
(Fase 5 y «Restricción de diseño: simple»),
[`2026-11-22-fase4-nombres-configurables.md`](2026-11-22-fase4-nombres-configurables.md) (clave de
configuración, transformación de textos, referencia independiente, anclas),
[`2026-11-20-fase3-esfuerzo-configurable.md`](2026-11-20-fase3-esfuerzo-configurable.md) (lectura única
de `synclayer-config.json`), decisión del propietario del 2026-11-24, hechos verificados por `scout`
(documentación oficial, leída el 2026-11-24) y mapa de `oracle`. Rama propuesta:
`feat/configuraciones-dinamicas`.

## 1. Objetivo

Cerrar la Fase 5 con tres entregas pequeñas y descartar el resto con motivo escrito:

- **(d) Carpeta de planes configurable.** Clave nueva y opcional en `<Target>/synclayer-config.json`.
  Al instalar, `install.ps1` sustituye la carpeta `docs/plans/` por la configurada en los textos que
  instala. Cambiarla = editar el archivo y reinstalar. Sin la clave, bytes y salida idénticos a hoy.
- **(c) Idioma del reporte de uso.** `tools/usage_report.py` puede generar el Markdown del reporte en
  un idioma de una lista cerrada. Por defecto, español: los mismos bytes que hoy.
- **(f) Perfiles por proyecto.** Sólo documentación: `.claude/agents/` de un repositorio reemplaza al
  agente global del mismo `name:`, con lo que está documentado y lo que no; y `permissions.deny` con
  `Agent(<nombre>)` como vía oficial para desactivar un agente. Sin código.

### Decisiones ya tomadas (propietario, 2026-11-24; no se reabren)

1. Entran (c), (d) y (f). El resto de candidatas del backlog se descarta (1.2).
2. (f) es sólo documentación. La prioridad documentada por Claude Code es: gestionado > `--agents` >
   proyecto > usuario > plugin. **No está documentado** si el reemplazo por nombre incluye el bloque
   `hooks:` del frontmatter ni si hay fusión de campos: se escribe como **no verificado** y se
   comprueba en la compuerta G1 del propietario. Nunca se documenta como hecho.
3. `permissions.deny` con `Agent(<nombre>)` (o `--disallowedTools`) se documenta como alternativa
   oficial a desactivar un agente. No se implementa nada alrededor.
4. (d) cubre sólo la carpeta de planes. **La convención de commits queda descartada**: nada del
   repositorio la lee ni la hace cumplir.
5. (c) cubre sólo el reporte de uso. No se tocan los prompts de los agentes (inglés) ni el idioma de
   los reportes que producen los agentes (español).
6. Nada promete ahorro, calidad ni costo. Ningún mensaje imprime rutas sin `--show-paths`.
   Documentación al día en el mismo cambio.
7. Los valores por defecto reproducen el comportamiento actual (restricción de diseño del backlog).

### 1.1 Dentro de alcance

- `install.ps1`: clave `plans_dir`, validación cerrada, transformación de textos, línea `Planes:`,
  texto de verificación.
- `tools/usage_report.py`: catálogo de textos por idioma, parámetro `lang` de los dos generadores,
  parámetro `--lang` de `project` y `global`.
- Pruebas: `tests/plans_ref.py`, `tests/test_plans.py` y `tests/test_phase5_docs.py` (nuevos); casos
  nuevos en `tests/test_install.py`, `tests/test_usage_report.py`, `tests/test_usage_report_cli.py`
  y `tests/test_usage_report_edges.py`.
- Documentación: `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`, manifiesto regenerado,
  estado de la Fase 5 en el backlog.

### 1.2 Descartadas, con motivo

| Candidata | Motivo del descarte | Qué se ofrece a cambio |
|---|---|---|
| (a) Activar o desactivar agentes por usuario | Costo alto: las pruebas fijan nueve agentes y doce archivos (`tests/test_manifest.py`, `tests/test_install.py`, `tests/test_brand_agents.py` contra `agents_data.py`, `tests/test_aliases.py`); habría que definir qué hace el manifiesto, el catálogo de `rules/agentes.md` y de la guía, la tabla de precedencia y los flujos cuando falta un agente (por ejemplo, sin `auditor`) | La vía oficial: `permissions.deny` con `Agent(<nombre>)` o `--disallowedTools`. Se documenta en (f) |
| (b) `tools:` por agente | El mínimo seguro depende del rol (un `auditor` con `Edit` deja de ser una revisión independiente) y no existe una transformación de la línea `tools:`; la de alias la deja intacta a propósito | Editar la línea `tools:` a mano (sale `MODIFICADO`; ya documentado en la guía) o un agente de proyecto (f) |
| (e) Estrictez de la guarda | Exige transformar el bloque `hooks:`, que hoy está prohibido (la autocomprobación de alias exige que quede byte a byte); un modo «sin guarda» contradice la falla cerrada, y cualquier grado intermedio invita a documentarla como sandbox | Nada. La guarda sigue siendo la del repositorio |
| Convención de commits (parte de (d)) | Nada la lee ni la hace cumplir: sería una opción sin efecto | El `CLAUDE.md` de cada proyecto |

### 1.3 Fuera de alcance

- Cambiar `agents/*.md`, `rules/agentes.md` (salvo P12), `hooks/agent_guard.py`,
  `tools/build_manifest.py`, el formato de `install-manifest.json`, `assets/`,
  `tests/test_manifest.py` o `tests/test_brand_agents.py`. Siguen siendo nueve agentes y doce
  archivos gestionados.
- Un esquema nuevo del estado: `synclayer-manifest.json` no cambia (3.1.6).
- Que el instalador cree, compruebe o use como ruta la carpeta de planes. Que el instalador cree,
  edite, respalde o borre `synclayer-config.json`. Leer o escribir `settings.json`.
- Carpeta de planes por proyecto. La configuración sigue viviendo en cada `-Target`.
- Que `tools/usage_report.py` lea `synclayer-config.json` (ver 3.2.1 y P8).
- Traducir los mensajes de `stderr`, la ayuda de `argparse` o la salida de `inspect`.
- Cualquier uso del ajuste `language` de Claude Code: es el único mecanismo oficial de idioma y no
  está documentado si lo heredan los subagentes; aquí no se toca ni se promete nada sobre él.
- La tarea pendiente de `Get-Prop` (P11 de la Fase 4): sigue siendo una tarea aparte.

## 2. Supuestos

Los marcados **[G1]** los comprueba el propietario en la compuerta G1 y no se documentan como hechos.

1. Windows PowerShell 5.1; `install.ps1` en ASCII sin BOM y sin el carácter asterisco (las
   expresiones regulares usan `{0,}` y `{1,}`); mensajes en español sin acentos. Python 3.12 con
   `-B`, sólo biblioteca estándar, `unittest`. Sin pwsh.
2. Las fases 1 a 4 están cerradas y en `main`. La configuración admite hoy sólo `level` y `aliases`;
   cualquier otra clave da exit 1.
3. En los doce archivos gestionados, la cadena `docs/plans` aparece **exactamente tres veces**, las
   tres con la forma `docs/plans/` precedida de una comilla invertida y fuera del frontmatter
   (comprobado el 2026-11-24; T1 lo fija con una prueba):
   - `agents/atlas.md`, línea 37: `` `docs/plans/YYYY-MM-DD-<topic>.md` ``
   - `rules/agentes.md`, línea 53: `` `docs/plans/AAAA-MM-DD-<tema>.md` ``
   - `docs/agentes.md`, línea 64: `` `docs/plans/AAAA-MM-DD-export-csv.md` ``
4. `hooks/agent_guard.py` no nombra la carpeta de planes: ningún modo de la guarda depende de ella.
5. `atlas` no tiene guarda: que escriba el plan en la carpeta configurada depende del texto de su
   prompt y de las reglas, no de un control. **[G1]** El efecto real (que `atlas` y la sesión
   principal usen la carpeta nueva) es comportamiento del modelo y no lo puede probar la suite.
6. **[G1]** Un agente de proyecto reemplaza al global del mismo `name:`. Lo documentado es la
   prioridad entre ámbitos. **No documentado:** si el reemplazo incluye `hooks:`, si hay fusión de
   campos, y qué pasa con un agente global instalado con alias (el nombre a igualar sería el alias).
7. **[G1]** `permissions.deny` con `Agent(<nombre>)` impide delegar en ese agente. Documentado; no
   probado en este equipo.
8. Los generadores del reporte (`render_project_report`, `render_global_report`) son puros y sus
   textos están repartidos entre constantes de módulo y literales dentro de las funciones `_…_section`.
   Las etiquetas en español del lector y del agregado (`WARN_…`, `READ_QUALITY_LABELS`,
   `(otro agente)`, `integrado`, `otros`, `sin-meta`) funcionan además como identificadores internos.
9. Ningún agente ejecuta el instalador sin `-Target` y `HOME` temporales, ni la herramienta de
   reporte contra el `~/.claude` real (`--claude-dir` siempre temporal). Los prompts de `forge`,
   `sentinel`, `auditor` y `shield` lo dicen de forma explícita.
10. La regresión `F4T6_GOLDEN` (salida del nivel 5 sin alias) no depende del contenido de
    `docs/agentes.md` (la Fase 4 lo editó después sin romperla). T7 lo confirma al tocar la guía.
11. Una prueba existente (`test_f4t5_static_functions_pattern_and_the_removed_guard`, en
    `tests/test_install.py`) exige que el bloque `# Nivel:` contenga el texto
    `ConvertTo-LevelBytes $aliasBytes[$rel]`, que haya una sola línea que empiece por `# Alias:` y
    diez `# Paso N:`. El diseño de 3.1.4 lo respeta.

## 3. Diseño

### 3.1 (d) Carpeta de planes

#### 3.1.1 Formato

```json
{ "level": 3, "aliases": { "sentinel": "amigo-qa" }, "plans_dir": "docs/planes" }
```

| Regla | Detalle |
|---|---|
| Claves de la raíz | Lista cerrada: `level`, `aliases` y `plans_dir`, las tres opcionales, comparación ordinal. Cualquier otra (incluidas `plansDir`, `Plans_dir`, `plans`): exit 1, con el mensaje actual |
| `plans_dir` ausente | Carpeta `docs/plans`. Comportamiento y bytes idénticos a hoy |
| `plans_dir` igual a `docs/plans` | Válido; equivale a no ponerlo (como un alias igual a su rol) |
| Valor | Una cadena, leída con `Get-PropRaw(...).Value` (tipo estricto: una lista de un elemento no vale). `null`, número, booleano, lista u objeto: exit 1 |
| Lectura | La misma lectura única (tope de 65 536 bytes, UTF-8 estricto, rechazo de enlaces antes y después, rechazo de `__type`). El archivo no se abre otra vez |

La **carpeta efectiva** es el valor si es distinto de `docs/plans`; si no hay carpeta efectiva, no se
llama a ninguna función de transformación.

#### 3.1.2 Validación (cerrada, antes de escribir)

Función pura `Get-PlansDirProblem`: devuelve el motivo del primer problema o `$null`. Se evalúa junto
a la tabla de alias, antes de leer el estado; exit 1 también con `-DryRun`.

| # | Regla | Motivo |
|---|---|---|
| L1 | Es una cadena | Tipo estricto |
| L2 | Casa (ordinal, `CultureInvariant`, sin `IgnoreCase`) con `^[a-z0-9][a-z0-9_-]{0,31}(/[a-z0-9][a-z0-9_-]{0,31}){0,3}\z` | De una a cuatro carpetas separadas por `/`. Excluye por construcción `..`, `.`, `\`, `:`, espacios, comillas, comilla invertida, saltos de línea, barra inicial o final, segmentos vacíos, mayúsculas y no ASCII: el valor no puede inyectar Markdown ni instrucciones en un prompt |
| L3 | Mide como mucho 64 caracteres | Acota lo que sale por `Planes:` y lo que entra en los textos |
| L4 | Ningún segmento es un nombre de dispositivo de Windows (`con`, `prn`, `aux`, `nul`, `com0` a `com9`, `lpt0` a `lpt9`) | La carpeta la crearán los agentes en proyectos del usuario. Misma lista que `$AllowedPattern`; una prueba las ata |
| L5 | Ningún trozo de un segmento, partido por `-`, es un nombre de `$AliasRoles` (`docs/forge`, `atlas-planes`) | La transformación de alias reemplazaría ese trozo; mantiene la garantía de la Fase 4 («ningún nombre de rol con alias en los textos instalados») y hace que el orden entre las dos transformaciones no importe |

Datos nuevos en `install.ps1` (contrato con `tests/test_plans.py`, una definición por línea, como
`$AliasRoles`):

```powershell
$PlansDirDefault = 'docs/plans'
$PlansDirPattern = '^[a-z0-9][a-z0-9_-]{0,31}(/[a-z0-9][a-z0-9_-]{0,31}){0,3}\z'
$PlansDirMaxLength = 64
```

Mensajes (ASCII, sin acentos; **nunca el valor** ni contenido del archivo):

- `error: synclayer-config.json no es valido: <motivo>. No se escribio nada.`
- Motivos: `plans_dir debe ser texto`; `plans_dir solo admite de 1 a 4 carpetas separadas por /, en
  minusculas (a-z, 0-9, _ y -; cada una empieza por letra o digito y tiene hasta 32 caracteres) y
  hasta 64 caracteres en total`; `plans_dir contiene un nombre reservado de Windows`; `plans_dir
  contiene el nombre de un agente de SyncLayer`.
- Transformación: `error: no se puede aplicar la carpeta de planes a <rol>: <motivo>. No se escribio
  nada.` (`<rol>` es la ruta del manifiesto).

#### 3.1.3 Transformación de textos

Función pura, sin E/S: `ConvertTo-PlansBytes([byte[]]$Bytes, [string]$Kind, [string]$PlansDir)`, con
`Kind` = `agent` o `text`. Mismo estilo que `ConvertTo-AliasBytes`: decodifica en ISO-8859-1 (un
byte, un carácter; los bytes altos se conservan), trabaja por líneas LF y falla cerrado.

- **Qué se busca.** El literal `docs/plans/` cuando el carácter anterior **no** es de
  `[A-Za-z0-9_./-]` (ni existe). Así `mydocs/plans/` y `x/docs/plans/` no casan. Expresión, la misma
  en PowerShell y en la referencia Python (lookbehind de ancho fijo, sin `IgnoreCase` ni `re.I`):
  `(?<![A-Za-z0-9_./-])docs/plans/`.
- **Por qué se sustituye.** `<carpeta efectiva>/`. Resultado: `` `docs/planes/AAAA-MM-DD-<tema>.md` ``.
- **Dónde.** Sólo los tres archivos de texto que hoy la nombran entran en juego, pero la función se
  aplica a los once textos gestionados (nueve agentes, `rules/agentes.md`, `docs/agentes.md`): un
  archivo sin coincidencias sale con los bytes de entrada. El hook nunca se transforma.
- **Agente (`Kind` = `agent`).** Línea 0 = `---` y cierre = primera línea posterior exactamente
  `---`; si no, error. Una coincidencia **dentro del frontmatter** es un error (`referencia a la
  carpeta de planes en el frontmatter`): no se reescribe una `description:` ni un bloque `hooks:`.
  Sólo se sustituye en el cuerpo.
- **Texto (`Kind` = `text`).** Todo el contenido. Sin excepciones por bloques de código o enlaces:
  el reemplazo es textual. T1 fija con una prueba que hoy ninguna coincidencia cae dentro de un
  bloque cercado, del destino de un enlace `](...)` ni de una URL.
- **Una sola pasada**, de izquierda a derecha; lo ya reemplazado no se vuelve a examinar (una
  carpeta como `docs/plans-v2` o `x/docs/plans` no provoca un segundo reemplazo).
- **Autocomprobación (falla cerrado).** Sobre el resultado: mismo número de líneas; en un agente, el
  frontmatter idéntico línea a línea y el cierre en el mismo índice; recorrido en paralelo de entrada
  y salida (fuera de las coincidencias, carácter a carácter iguales; en cada coincidencia, el texto
  esperado); número de reemplazos = número de coincidencias de la entrada.

Un error de transformación es un defecto del origen que el manifiesto no detecta: exit 1 antes de
escribir, también con `-DryRun`.

#### 3.1.4 Orden con alias y niveles

Opciones:

| Opción | A favor | En contra |
|---|---|---|
| A. Planes, después alias, después nivel | La carpeta se aplica a los bytes verificados contra el manifiesto | Cambia la entrada de `ConvertTo-AliasBytes` (código de la Fase 4 recién cerrado); la autocomprobación de alias vería texto ya modificado |
| **B. Alias, después planes, después nivel** | El cálculo de alias no se toca; la nueva capa se apoya en bytes ya autocomprobados; el nivel sigue siendo el último y valida el frontmatter final | Hay que respetar el texto que una prueba exige en `# Nivel:` (supuesto 11) |
| C. Una sola función que haga alias y carpeta a la vez | Una pasada | Reabre `ConvertTo-AliasBytes` y sus 61 casos |

Se elige **B**. Las tres transformaciones tocan zonas que no se pisan: alias (`name:`,
`description:`, palabras del cuerpo), planes (el literal `docs/plans/` del cuerpo), nivel (`model:` y
`effort:`). El resultado es el mismo en cualquier orden sólo mientras un alias no pueda crear ni
destruir el literal, y esto no es cierto en general: un alias válido `docs` sobre una forma
`forge/plans/` produciría `docs/plans/`. Hoy no ocurre en los once textos, y T1 añadió una
comprobación de inventario (`segment_problems` en `tests/plans_ref.py`) que falla si aparece una forma
`<segmento>/plans/` distinta de `docs/plans/`. Por eso el orden alias, planes, nivel queda fijado
(opción B), y la conmutación del caso 8 (los tres órdenes, en la referencia Python) vale sólo mientras
esa comprobación pase. La carpeta no puede traer un nombre de rol (alfabeto cerrado L2 y validación).

**Cómo se inserta sin tocar `# Nivel:`.** Bloque nuevo en `install.ps1`, después del bucle que llena
`$aliasBytes` y **antes** del comentario `# Nivel:`, con el marcador `# Planes:` (no empieza por
`# Paso` ni por `# Alias:`). Con carpeta efectiva, el bloque **reescribe en su sitio**
`$aliasBytes[$rel]` con el resultado de `ConvertTo-PlansBytes` para los once textos; sin carpeta
efectiva no hace nada. El bloque `# Nivel:` no se edita: sigue leyendo `$aliasBytes[$rel]` y la
aserción `ConvertTo-LevelBytes $aliasBytes[$rel]` de la prueba existente sigue valiendo. Los
comentarios dicen que, desde este punto, `$aliasBytes` son «los bytes con alias y con carpeta de
planes». (Renombrar la variable sería más limpio, pero obliga a modificar una prueba de la Fase 4;
se descarta.)

Anclas que **no cambian de texto ni de sitio**: los diez `# Paso N:`, `# Configuracion:`, la única
línea `# Alias:`, `# Nivel:`, `$level = [int](Read-LevelConfig $configPath)`,
`function ConvertTo-LevelBytes`, `function ConvertTo-AliasBytes`,
`ConvertTo-LevelBytes $aliasBytes[$rel]`, `Write-Atomic $dest $outBytes[$rel] $existing` y el resto
de las de la Fase 4. Anclas nuevas (contrato): `# Planes:` (una sola línea que empiece así) y
`function ConvertTo-PlansBytes`.

Orden de ejecución: Paso 1; Paso 2; `# Configuracion:` (lee `level`, `aliases` y `plans_dir`; valida
alias y carpeta); avisos de entorno; `# Alias:`; `# Planes:`; `# Nivel:`; Paso 3 en adelante.

#### 3.1.5 Salida, mensajes y códigos

Sin carpeta efectiva no aparece ninguna línea nueva (el golden `F4T6_GOLDEN` sigue valiendo). Con
carpeta efectiva, tras las líneas `Alias:` y antes de `Respaldo:`:

`Planes: docs/planes`

El valor impreso ya pasó L2 (alfabeto cerrado, 64 caracteres). `Planes:` no casa con la expresión
`LINE` de las pruebas (T2 lo comprueba).

`$verifyWhat`:

| Nivel | Alias efectivos | Carpeta efectiva | Texto |
|---|---|---|---|
| 5 | no | no | `el manifiesto` (hoy) |
| 1 a 4 | no | no | `lo esperado para el nivel N` (hoy) |
| cualquiera | sí | no | `lo esperado para el nivel N y los alias` (hoy) |
| cualquiera | no | sí | `lo esperado para el nivel N y la carpeta de planes` |
| cualquiera | sí | sí | `lo esperado para el nivel N, los alias y la carpeta de planes` |

Códigos de salida: 1 (valor inválido, error de transformación), 3 y 4 sin cambio de regla ni de
texto.

#### 3.1.6 Clasificación y estado

No hay esquema nuevo. La clasificación de las Fases 3 y 4 ya compara el destino con `$outHash` (lo
que se escribiría) y con `written` del estado:

| Situación | Resultado |
|---|---|
| K1. Carpeta nueva sobre una instalación intacta | Los tres archivos que la nombran salen `ACTUALIZAR` (con respaldo); el resto `IGUAL`; el estado se reescribe porque cambian sus `written` |
| K2. Cambio de carpeta | Los mismos tres, `ACTUALIZAR` |
| K3. Carpeta quitada (o puesta a `docs/plans`) | Los mismos tres, `ACTUALIZAR`; vuelven a los bytes del origen (con alias o nivel si los hay) |
| K4. Edición a mano de uno de los tres | `MODIFICADO`, exit 3; con `-Force`, respaldo y sobrescritura |
| K5. Estado ausente o ilegible con carpeta ya instalada | Con los bytes esperados, `IGUAL`; distintos, `MODIFICADO`. Nunca `ACTUALIZAR` |
| K6. Reinstalar igual | Todo `IGUAL`; ni estado, ni respaldo, ni línea nueva salvo `Planes:` |
| K7. Carpeta, alias y nivel a la vez | Cada archivo = referencia Python; `atlas` con alias lleva la carpeta en su cuerpo, `name:` con el alias y la celda de nivel del rol |

No hay huérfanos nuevos: la carpeta no cambia ninguna ruta de destino. El instalador no guarda la
carpeta en el estado y no imprime «carpeta anterior» (ver P6).

#### 3.1.7 Seguridad

`plans_dir` es entrada no confiable y termina dentro del texto de un prompt (`agents/atlas.md`) y de
las reglas que lee la sesión principal.

- Alfabeto cerrado (L2): sin espacios, saltos de línea, comillas, comilla invertida, `<`, `>`, `|`,
  `#` ni `:`. No puede cerrar el código en línea, abrir un enlace ni añadir una frase.
- El instalador **nunca** usa el valor como ruta: no lo une a `-Target`, no lo crea, no lo lee. Sólo
  es texto que se inserta. No hay recorrido de carpetas posible desde el instalador.
- El frontmatter de los agentes no cambia con ninguna carpeta (autocomprobación); el bloque `hooks:`
  queda byte a byte.
- Ningún mensaje de error imprime el valor. La línea `Planes:` imprime sólo un valor ya validado.
- Comparaciones ordinales; expresiones sin `IgnoreCase`; lectura única heredada.
- Límite documentado: el efecto sobre el comportamiento del agente no es un control. Un proyecto
  cuyo `CLAUDE.md` nombre otra carpeta sigue mandando en ese proyecto.

#### 3.1.8 Límites que se documentan

- El reemplazo es textual. Sólo cambia los tres textos instalados; no cambia el `CLAUDE.md` del
  usuario, la memoria, los planes ya escritos ni los enlaces de documentos existentes.
- No mueve ni crea carpetas. Los planes anteriores quedan donde estaban.
- La configuración es por `-Target`: una sola carpeta para todos los proyectos del usuario. Para un
  proyecto concreto, el `CLAUDE.md` del proyecto o un agente de proyecto (f).
- Con carpeta efectiva los archivos de `~/.claude` no son los del repositorio: la copia inversa no
  vale (igual que con alias o nivel).
- Los bytes con carpeta no los cubre el hash del manifiesto: se verifican contra `$outHash`.
- Sin mayúsculas, puntos ni espacios en el nombre (P4). Un instalador anterior rechaza la clave
  (`clave desconocida ... el instalador puede ser anterior al archivo`).

### 3.2 (c) Idioma del reporte de uso

#### 3.2.1 Dónde vive la opción

| Opción | A favor | En contra |
|---|---|---|
| **A. Parámetro `--lang` de `project` y `global`** | La herramienta se ejecuta a mano desde el clon y ya se gobierna sólo por parámetros (`--claude-dir`, `--since`, `--stdout`); sin estado nuevo; determinista | Hay que escribirlo en cada corrida |
| B. Clave en `synclayer-config.json` | Se configura una vez | Obliga a que `install.ps1` acepte una clave que no usa (hoy rechaza toda clave desconocida) y a un **segundo lector** de una entrada no confiable, en Python, con las mismas defensas (tope, UTF-8 estricto, enlaces, `__type`); la herramienta no lee hoy nada de `<claude-dir>` salvo `projects/` |
| C. Ambas, el parámetro gana | Cómodo | Suma el costo de B y una regla de precedencia |

Se elige **A** (ver P8). No se lee ninguna variable de entorno ni el ajuste `language` de Claude Code.

#### 3.2.2 Idiomas

Lista cerrada: `es` (por defecto) y `en` (ver P9). Comparación exacta: `EN`, `en-US`, `english` y la
cadena vacía dan exit 2.

#### 3.2.3 Alcance de la traducción

| Se traduce con `--lang en` | No cambia nunca |
|---|---|
| Todo el Markdown del reporte de proyecto y del global: títulos, cabecera, etiquetas de resumen, cabeceras de tabla, avisos, «Cómo leer estos números», limitaciones, «Qué compara y qué no», notas de privacidad, leyendas | El marcador de la primera línea (`<!-- synclayer-usage-report v1 -->`), `REPORT_SCHEMA` (1) y los destinos fijos |
| Las etiquetas de listas cerradas que el lector produce en español (`(otro agente)`, `(otro modelo)`, `(otra skill)`, `(otro conjunto)`, `integrado`, `otros`, `sin-meta`, `plugin:(otro)`, `plugin:(no-valido)`, orígenes `sesion` y `subagente`, contadores de calidad), mediante una tabla cerrada **en el generador** | El lector, el agregado y sus etiquetas internas (siguen siendo identificadores en español); `SyncLayer`; nombres de agente, modelo, skill y versión |
| `proyecto 1..N` del global | Las claves del pie (`report_schema`, `herramienta`, `ultima_version_verificada`, `proyecto`): son identificadores estables (ver P10) |
| | Mensajes de `stderr` y de `stdout` de la CLI, ayuda de `argparse`, salida de `inspect` (ver P10) |
| | Formato de números, porcentajes y fechas: el mismo en los dos idiomas (ISO, punto decimal, `%d %%`) |

Un `es` y un `en` generados con la misma entrada tienen las mismas tablas, filas, números y orden:
sólo cambia el texto fijo. Una prueba lo comprueba (caso 37).

#### 3.2.4 Catálogo de textos

- En `tools/usage_report.py` (sigue siendo un solo archivo, sólo biblioteca estándar, código ASCII):
  `LANGS = ("es", "en")`, `DEFAULT_LANG = "es"` y un catálogo cerrado por idioma con las mismas
  claves. Los textos en español conservan sus escapes `\u00xx`; los de inglés son ASCII.
- Los generadores reciben el idioma como argumento: `render_project_report(metrics, project_alias,
  generated=None, lang="es")` y `render_global_report(metrics, generated=None, lang="es")`. Un
  `lang` fuera de `LANGS` lanza `ValueError` con mensaje fijo, sin eco del valor. Siguen siendo
  puros: **ningún estado global mutable** decide el idioma.
- Las constantes actuales que otras capas usan como identificadores (`WARN_…`, `KNOWN_WARNINGS`,
  `READ_QUALITY_LABELS`, `OTHER_AGENT`, `OTHER_LABELS`, grupos) **no cambian de valor**. El catálogo
  `en` las traduce por clave; una etiqueta fuera de las listas cerradas sale como hoy
  (`aviso no reconocido`, `(otro conjunto)`), traducida.
- Paridad obligatoria entre idiomas: mismas claves; por clave, la misma secuencia de marcadores
  (`%d`, `%s`, `%%`) y, si el valor es una tupla, la misma longitud.

#### 3.2.5 CLI

- `--lang IDIOMA` en `_add_report_arguments` (lo reciben `project` y `global`; **no** `inspect`).
  Por defecto `es`.
- Validación con un `type=` propio y mensaje fijo (`idioma invalido: use es o en`), como
  `_date_arg`. No se usa `choices=`: `argparse` repetiría el valor recibido en `stderr`.
- Valor inválido: exit 2, antes de leer ninguna transcripción y sin tocar el disco.
- Con `--stdout`, bytes UTF-8 por `sys.stdout.buffer`, como hoy.
- El destino es el mismo en los dos idiomas: un reporte en `en` sustituye al de `es` (los dos llevan
  el marcador). Misma entrada, mismos argumentos y mismo día dan los mismos bytes.

#### 3.2.6 Seguridad y privacidad

- `--lang` es entrada de usuario de lista cerrada: no forma ninguna ruta ni nombre de archivo y no
  se imprime.
- El catálogo `en` no puede abrir una fuga: los textos son fijos y los valores variables siguen
  pasando por `_code` y por las listas permitidas. Las pruebas de «sin fuga» y «sin rutas sin
  `--show-paths`» se repiten con `--lang en`.
- El catálogo `en` no promete ahorro, calidad ni costo: es traducción fiel del `es`; una prueba
  busca patrones de promesa en inglés fuera de una lista cerrada de frases negadas (caso 35).

### 3.3 (f) Perfiles por proyecto (sólo documentación)

Qué se escribe, y con qué grado de certeza:

| Afirmación | Cómo se escribe |
|---|---|
| Un `.claude/agents/<nombre>.md` de un repositorio con el mismo `name:` reemplaza al agente global en ese proyecto | Documentado por Claude Code |
| Prioridad: gestionado > `--agents` > proyecto > usuario > plugin | Documentado por Claude Code |
| El reemplazo es por nombre, del archivo entero | La documentación no describe fusión de campos: se escribe «no hay fusión documentada» |
| Si la copia de proyecto no trae el bloque `hooks:`, el agente corre sin la guarda | **No verificado.** Se escribe como riesgo: «copiá también el bloque `hooks:`; no está documentado qué pasa si falta» |
| Con alias, el nombre a igualar es el alias instalado, no el rol | Consecuencia del reemplazo por `name:`; **no verificado** en Claude Code real |
| El nivel de `synclayer-config.json` no llega a una copia de proyecto | Hecho del instalador: sólo escribe en `-Target` |
| `permissions.deny` con `Agent(<nombre>)` (o `--disallowedTools`) impide usar un agente | Documentado por Claude Code; SyncLayer no lo configura ni lo comprueba. Las reglas siguen nombrando al agente: la sesión principal puede intentar delegar y recibir la negativa |

Dónde: sección nueva «Perfiles por proyecto» en el `README.md` (con el apartado «Desactivar un
agente» y la tabla de descartadas de 1.2 en lenguaje llano) y el párrafo «Adaptar un agente a un
proyecto» de `docs/agentes.md` ampliado. `rules/agentes.md` no cambia (P12). En los archivos
gestionados el texto nuevo usa `<nombre>` y `<alias>`, nunca un nombre de rol ni el literal
`docs/plans` (se transformarían al instalar; los inventarios de `tests/test_aliases.py` y
`tests/test_plans.py` fallarían).

### 3.4 Estrategia de pruebas

- `tests/plans_ref.py` (auxiliar, no es `test_*.py`): segunda implementación independiente en
  Python: `validate_plans_dir(value)`, `transform_text(data, plans_dir)`,
  `transform_agent(data, plans_dir)`, `expected_bytes(path, canon, level, aliases, plans_dir)` (que
  compone `aliases_ref` y `levels_ref`). Lee `$PlansDirDefault`, `$PlansDirPattern` y
  `$PlansDirMaxLength` de `install.ps1`.
- `tests/test_plans.py`: pruebas sin PowerShell (constantes, inventario, referencia).
- `tests/test_install.py`: casos con `powershell.exe`, siempre con `-Target` y `HOME` temporales.
  La configuración se escribe con la ayuda existente `write_config(data)` (un diccionario con
  `plans_dir`). Fixture nuevo `PLANS_SAMPLE` (no se cambian los bytes de `ALIAS_SAMPLE`): un agente
  con el literal en el cuerpo, reglas y guía mínimas con el literal, una coincidencia que no debe
  casar (`mydocs/plans/`) y el hook.
- `tests/test_usage_report.py` (catálogo y generadores), `tests/test_usage_report_cli.py`
  (`--lang`), `tests/test_usage_report_edges.py` (bordes de punta a punta). Siempre `--claude-dir`
  temporal; datos de `tests/usage_synth.py`.
- `tests/test_phase5_docs.py`: comprobaciones estáticas de la documentación.
- Las pruebas existentes no se modifican. La suite tarda unos 4 minutos y no se corre en paralelo con
  procesos pesados: variantes con `subTest`; la validación de `plans_dir` se cubre sobre todo en
  Python y, en PowerShell, con un `subTest` por motivo.

Casos:

| # | Caso | Se comprueba | Task |
|---|---|---|---|
| 1 | Constantes de `install.ps1` | `$PlansDirDefault` = `docs/plans`; `$PlansDirPattern` y `$PlansDirMaxLength` = los de la referencia; el valor por defecto pasa su propia validación | T1 |
| 2 | Inventario del repositorio | En los doce archivos gestionados, `docs/plans` aparece exactamente 3 veces (`agents/atlas.md`, `rules/agentes.md`, `docs/agentes.md`), las 3 reemplazables; ninguna en el hook ni en un frontmatter | T1 |
| 3 | Zonas sensibles | Ninguna coincidencia dentro de un bloque cercado, del destino de un enlace ni de una URL; sobre una copia en memoria, añadir una en un bloque cercado hace fallar la prueba | T1 |
| 4 | Referencia: validación | Cada regla L1 a L5 con un caso que pasa y uno que falla: `planes`, `docs/planes`, `a/b/c/d` válidos; `a/b/c/d/e`, `..`, `docs/../x`, `/docs`, `docs/`, `docs//x`, `Docs`, `docs/plans.v2`, `docs plans`, 65 caracteres, segmento de 33, `nul`, `docs/com1`, `docs/forge`, `atlas-planes` inválidos; `forge_x` y `forges` válidos | T1 |
| 5 | Referencia: límite izquierdo | `` `docs/plans/x` `` y `(docs/plans/x` se reemplazan; `mydocs/plans/`, `x/docs/plans/`, `.docs/plans/`, `-docs/plans/` y `docs/plans` sin barra final no | T1 |
| 6 | Referencia: una sola pasada | Con `docs/plans-v2` y con `x/docs/plans` como carpeta, el resultado no se vuelve a reemplazar y la autocomprobación pasa | T1 |
| 7 | Referencia sobre el repositorio real | Con `docs/planes`: cambian exactamente tres líneas en tres archivos; los otros nueve, bytes idénticos; frontmatter de `atlas` idéntico; LF y salto final | T1 |
| 8 | Referencia: orden | Para nueve alias, niveles 1 a 5 y una carpeta: alias→planes→nivel = planes→alias→nivel = nivel→alias→planes, byte a byte, en los once textos. Vale sólo mientras `segment_problems` (inventario) no halle una forma `<segmento>/plans/` distinta de `docs/plans/` (3.1.4) | T1 |
| 9 | Nombres de dispositivo | La lista de L4 de la referencia es la de `$AllowedPattern` de `install.ps1` (leída del script) | T1 |
| 10 | Sin `plans_dir`, y `"plans_dir": "docs/plans"` | Destino, estado, stdout y stderr idénticos byte a byte a la corrida sin esa clave; sin línea `Planes:` | T2 |
| 11 | Tipo inválido: `null`, número, `true`, lista, lista de una cadena, objeto | Exit 1 en `-DryRun` y real; nada escrito; motivo `plans_dir debe ser texto` | T2 |
| 12 | Valor inválido (los de 4) más cadena vacía, salto de línea, comilla invertida, no ASCII | Exit 1 en ambos modos; el mensaje **no contiene el valor**; nada escrito | T2 |
| 13 | Claves parecidas: `plansDir`, `Plans_dir`, `plans` | Siguen siendo clave desconocida, con el mensaje actual | T2 |
| 14 | `plans_dir` válido con `level` y `aliases` válidos | Líneas `Nivel:`, `Alias:` y `Planes:` en ese orden; `Planes:` no casa con `LINE`; (mientras dure la guarda temporal: exit 1 con su mensaje) | T2 |
| 15 | Validación antes de cualquier escritura | Con estado válido y cambios pendientes, un `plans_dir` inválido no escribe ni respalda; con alias inválido y carpeta inválida a la vez, sale un único error | T2 |
| 16 | Clave `plans_dir` repetida; valor con `__type` | Se fija el comportamiento real de 5.1 y se documenta | T2 |
| 17 | Configuración intacta | Bytes y mtime de `synclayer-config.json` iguales tras `-DryRun`, instalación y `-Force`; no aparece en el respaldo | T2, T4 |
| 18 | Instalación limpia con carpeta (`PLANS_SAMPLE`) | Cada archivo = `plans_ref`; el literal viejo no queda en los tres textos; `mydocs/plans/` intacto; el estado sigue en esquema 2 | T3 |
| 19 | Diferencia línea a línea | Sólo cambian las líneas con el literal; frontmatter y `hooks:` byte a byte; el hook con el hash del manifiesto | T3 |
| 20 | La transformación sólo corre con carpeta efectiva | Marcador inyectado en `function ConvertTo-PlansBytes` no se alcanza sin `plans_dir` ni con `docs/plans` | T3 |
| 21 | Origen defectuoso con carpeta efectiva: literal en `description:`, agente sin cierre | Exit 1 en ambos modos; nada escrito; el mensaje nombra el rol. Control: el mismo origen instala sin `plans_dir` | T3 |
| 22 | Autocomprobación | Resultado corrompido por inyección: exit 1, nada escrito | T3 |
| 23 | Origen con CRLF y con bytes altos | Mismo resultado que con LF; bytes altos conservados; UTF-8 válido | T3 |
| 24 | Texto de verificación | Las cinco filas de 3.1.5; verificación posterior alterada (Paso 8): exit 4 con el texto correspondiente | T3, T4 |
| 25 | Carpeta, alias y nivel juntos (`PLANS_SAMPLE`, niveles 1 a 5) | Bytes = `expected_bytes`; `model:` y `effort:` de la celda del rol; `name:` con el alias; `Ajuste:` con la ruta de destino | T4 |
| 26 | Repositorio real como origen, nueve alias, nivel 3 y carpeta | 13 archivos; los once textos = referencia; ningún nombre de rol salvo las subcadenas permitidas de la Fase 4; ningún `docs/plans/` en los tres textos; `hooks:` de los cuatro agentes con guarda intactos | T4 |
| 27 | `-DryRun` con carpeta | Línea `Planes:`, filas `ACTUALIZAR` en los tres archivos, nada escrito | T4 |
| 28 | K1 a K3 | Carpeta nueva, cambiada y quitada sobre instalación intacta: `ACTUALIZAR` con respaldo en los tres, `IGUAL` en el resto, sin huérfanos | T4 |
| 29 | K4 a K6 | Edición a mano: `MODIFICADO`, exit 3, y con `-Force` respaldo; estado ausente: nunca `ACTUALIZAR`; reinstalar igual: todo `IGUAL`, sin estado ni respaldo nuevos | T4 |
| 30 | Regresión sin carpeta | `F4T6_GOLDEN` y las pruebas de las Fases 1 a 4 pasan sin modificarse (incluida la aserción `ConvertTo-LevelBytes $aliasBytes[$rel]` y la de una sola línea `# Alias:`) | T2 a T4 |
| 31 | `install.ps1` sigue en ASCII, sin BOM, sin asterisco, `&&`, `??` ni datos personales | Pruebas estáticas existentes | T1 a T4 |
| 32 | Español sin cambios tras extraer el catálogo | Los reportes de proyecto y global de un conjunto sintético amplio (todas las secciones, avisos, tablas acotadas, sin llamadas) son idénticos byte a byte a un golden generado **antes** del cambio; las pruebas existentes pasan sin modificarse | T5 |
| 33 | Ningún texto fijo fuera del catálogo | Prueba estática con `ast`: en las funciones generadoras (de `_bar` a `render_global_report`) ningún literal de cadena con dos o más palabras alfabéticas, ni con caracteres no ASCII salvo los bloques de barra, fuera de una lista cerrada y justificada (claves del pie, formatos) | T5 |
| 34 | Paridad del catálogo | `es` y `en`: mismas claves; por clave, misma secuencia de marcadores y misma longitud de tupla; todo valor `en` es ASCII; ningún valor `en` igual al `es` salvo una lista cerrada de términos neutros | T6 |
| 35 | Sin promesas en inglés | Ningún valor `en` casa con los patrones de promesa en inglés (ahorro, más barato, mejor calidad) fuera de la lista cerrada de frases negadas | T6 |
| 36 | `lang` en los generadores | `lang="es"` = sin argumento, byte a byte; `lang="en"` produce un reporte todo ASCII salvo los dos caracteres de barra; `lang` inválido (`"fr"`, `"EN"`, `""`, `None`, `1`): `ValueError` con mensaje fijo, sin eco | T6 |
| 37 | Misma estructura en los dos idiomas | Mismo número de líneas, de tablas y de filas, y las mismas celdas numéricas y de `_code`, en el reporte de proyecto y en el global | T6 |
| 38 | Etiquetas de listas cerradas en `en` | `(otro agente)`, `integrado`, `sin-meta`, avisos `WARN_…` y contadores de calidad salen traducidos; un aviso o un conjunto fuera de la lista sale como la etiqueta genérica traducida; el marcador, `REPORT_SCHEMA` y las claves del pie no cambian | T6 |
| 39 | `--lang` en la CLI | `project` y `global` con `--lang en` y con `--lang es`, escribiendo y con `--stdout`: exit 0 y bytes = generador; sin `--lang` = `--lang es` | T6 |
| 40 | `--lang` inválido | `fr`, `EN`, `en-US`, vacío, valor con una ruta: exit 2; `stderr` no contiene el valor; no se lee `projects/` ni se crea `.synclayer/`; `inspect --lang en` da exit 2 | T6 |
| 41 | Sustitución entre idiomas | Un destino en `es` se sustituye por `en` y al revés (mismo marcador); un destino ajeno sin marcador sigue dando exit 1 con `--lang en` | T6 |
| 42 | Privacidad en `en` | Las pruebas de «sin fuga» y «sin rutas sin `--show-paths`» de `tests/test_usage_report_edges.py`, repetidas con `--lang en`; los mensajes de `stderr` siguen en español | T6 |
| 43 | El código sigue siendo ASCII | `tools/usage_report.py` sin bytes no ASCII; determinismo: dos corridas con la misma entrada y el mismo día dan los mismos bytes en cada idioma | T5, T6 |
| 44 | Documentación de perfiles | El `README.md` tiene la sección «Perfiles por proyecto» con la prioridad, `permissions.deny`, `Agent(` y la marca de «no verificado» junto a `hooks:`; ninguna frase afirma que la guarda se hereda o se pierde como hecho | T7 |
| 45 | Documentación sin promesas | Las secciones nuevas del README («Perfiles por proyecto», «Carpeta de planes») pasan `promise_hits` (`PROMISE_PATTERNS` de `tests/test_levels.py`; ojo: incluye `\d+\s*%`, así que esas secciones no llevan porcentajes) | T7, T8 |
| 46 | Archivos gestionados tras documentar | Inventario de roles (`tests/test_aliases.py`) e inventario de `docs/plans` (caso 2) sin cambio de conteo; sincronía del manifiesto; siguen siendo doce archivos | T7, T8 |
| 47 | Documentación de carpeta e idioma | El README documenta `plans_dir` (formato, reglas, límites), `--lang` en la sinopsis y en la tabla de parámetros; `CLAUDE.md` e `HISTORY.md` al día; el backlog marca la Fase 5 como desglosada | T8 |

## 4. Tareas

Reglas para todas:

- Primero la prueba que falla, después la implementación. Python con `-B`.
- Ningún agente lanza `install.ps1` sin `-Target` y `HOME` temporales, ni `tools/usage_report.py`
  sin `--claude-dir` temporal; nadie toca `~/.claude`.
- `install.ps1` en ASCII sin BOM y sin asterisco; mensajes sin acentos; los `# Paso N:` y las anclas
  de 3.1.4 no se renombran ni se mueven. `tools/usage_report.py` en ASCII (tildes como `\u00xx`).
- Ciclo por task: un `forge` fresco y después `auditor`. Donde se indica, también `shield`.
- Al cerrar cada task, el mismo commit actualiza «Línea de tiempo y avance» del README con la
  aritmética de 4.6. Commits sin etiquetas de coautoría.
- La suite no se corre en paralelo con procesos pesados.

**Orden y paralelismo.** El frente de la carpeta (T1 a T4: `install.ps1`, `tests/test_install.py`,
`tests/plans_ref.py`, `tests/test_plans.py`) y el del idioma (T5, T6: `tools/usage_report.py`,
`tests/test_usage_report*.py`) tocan archivos disjuntos y podrían ir en paralelo, cada `forge` en su
worktree. Aun así se recomienda **secuencial** (P13): cada cierre edita el mismo `README.md` (línea
de tiempo) y dos suites a la vez agotan la memoria. Dentro de cada frente, estrictamente secuencial.
T7 y T8 tocan los mismos documentos: secuenciales, después de T1 a T6.

Tamaños: S (hasta medio día de `forge`), M (uno o dos archivos con lógica nueva), L (lógica nueva más
adaptación amplia de pruebas).

### Paso previo (sesión principal; no cuenta como unidad)

Al aprobar el plan: en el README, la Fase 5 pasa de «sin desglosar» a «0 de 9» y se crea «La Fase 5
por frentes»; la frase de «Avance global» deja de decir que la fase 5 está sin desglosar. El avance
global sigue en 80 %. Este plan pasa a «aprobado» y el backlog enlaza a él.

### G1. Compuerta: verificación en Claude Code real (propietario; no cuenta como unidad)

En un proyecto de pruebas, sin tocar los agentes reales. Anotar la versión de Claude Code.

- **Perfiles.** Crear `.claude/agents/<nombre>.md` con el `name:` de un agente global con guarda,
  una vez **con** el bloque `hooks:` y otra **sin** él, y un cuerpo distinguible. Comprobar con
  `/agents` y `claude --debug` cuál carga, y con una acción que la guarda bloquearía si el hook
  sigue aplicándose en cada variante.
- **Desactivar.** Añadir `Agent(<nombre>)` a `permissions.deny` del proyecto y comprobar que la
  delegación se niega y qué ve la sesión principal.
- **Carpeta de planes.** Tras instalar con `plans_dir` en un `-Target` de pruebas, o leyendo los
  textos generados: pedir un plan y ver dónde lo escribe `atlas`.
- Resultado: sección «Resultado de G1» de este plan.
- **No bloquea T1 a T8** (P14). Mientras no se corra, la documentación dice «no verificado». Si el
  resultado contradice lo escrito, T7 se corrige en una tarea aparte.

### Fase A: carpeta de planes

#### T1. Constantes, referencia en Python e inventario — tamaño S

- **Objetivo:** los datos de 3.1.2 en `install.ps1` y la referencia independiente con la que se
  compararán los bytes del instalador.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py` (sólo si hace falta una
  comprobación estática); crear `tests/plans_ref.py`, `tests/test_plans.py`.
- **Pasos:** prueba roja del caso 1. En `install.ps1`: `$PlansDirDefault`, `$PlansDirPattern`,
  `$PlansDirMaxLength` (aún sin uso), junto a `$AliasRoles`. `plans_ref.py` completo (3.4).
  `test_plans.py` con los casos 1 a 9.
- **Pruebas:** casos 1 a 9 y 31.
- **Aceptación:** la suite pasa; el instalador se comporta igual que antes (ninguna prueba existente
  cambia); cambiar `$PlansDirPattern` sin la referencia hace fallar el caso 1; añadir un cuarto
  `docs/plans` a un archivo gestionado hace fallar el caso 2 (comprobado sobre una copia en
  memoria); la referencia no usa `re.I` ni lookbehind de ancho variable.
- **Dependencias:** aprobación del plan.
- **Revisa:** `auditor`.

#### T2. Clave `plans_dir`: lectura y validación — tamaño M — revisión de seguridad

- **Objetivo:** leer y validar `plans_dir` según 3.1.1 y 3.1.2 y mostrar la línea `Planes:`, sin
  aplicarla todavía.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** pruebas rojas (casos 10 a 17). La lista cerrada de la raíz admite `plans_dir`; la
  lectura única entrega también el valor crudo (sin validar) al llamador, igual que
  `$script:ConfigAliasPairs`; la línea ancla `$level = [int](Read-LevelConfig $configPath)` se
  conserva. `Get-PlansDirProblem` (L1 a L5) evaluada tras la tabla de alias. Mensajes de 3.1.2.
  Línea `Planes:`. Actualizar `.DESCRIPTION` y los comentarios que listan las claves. **Guarda
  temporal:** una carpeta efectiva válida termina con exit 1 y
  `error: la carpeta de planes aun no se puede aplicar en esta version. No se escribio nada.`; T3 la
  retira junto con su prueba.
- **Pruebas:** casos 10 a 17, 30 y 31; una prueba de la guarda temporal.
- **Aceptación:** la suite pasa; ningún valor de `plans_dir` llega a un archivo del destino; ningún
  mensaje de error contiene el valor; ningún camino de error escribe; la configuración no se abre
  para escritura ni una segunda vez; las pruebas de las Fases 3 y 4 sobre la configuración pasan sin
  cambios; sin la clave, la salida es idéntica byte a byte.
- **Dependencias:** T1.
- **Revisa:** `auditor` y `shield`.

#### T3. Transformación y activación — tamaño M — revisión de seguridad

- **Objetivo:** el algoritmo de 3.1.3 y su uso: la carpeta se aplica de punta a punta.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** pruebas rojas (casos 18 a 24). `ConvertTo-PlansBytes` (pura, con autocomprobación);
  bloque `# Planes:` después del bucle de `$aliasBytes` y antes de `# Nivel:`, que reescribe
  `$aliasBytes[$rel]` en su sitio (3.1.4); el bloque `# Nivel:` **no se edita**; `$verifyWhat` según
  3.1.5 (única línea que se toca cerca de `# Nivel:`; antes de editarla, comprobar que ninguna
  prueba fija su texto); mensaje de error de transformación; retirar la guarda temporal de T2 y su
  prueba; fixture `PLANS_SAMPLE`.
- **Pruebas:** casos 18 a 24, 30 y 31.
- **Aceptación:** la suite pasa sin modificar ninguna prueba existente; sin carpeta efectiva no se
  llama a la transformación (caso 20) y los bytes son los de antes; con carpeta, todo byte escrito
  coincide con `plans_ref`; el frontmatter y el bloque `hooks:` de todos los agentes quedan
  idénticos; el hook no se transforma; hay una sola línea `# Planes:` y una sola `# Alias:`; el
  valor nunca se usa para construir una ruta del sistema de archivos (revisión de `shield`).
- **Dependencias:** T2.
- **Revisa:** `auditor` y `shield`.

#### T4. Carpeta con alias y niveles, repositorio real y cambios — tamaño M — revisión de seguridad

- **Objetivo:** demostrar con pruebas la tabla de situaciones de 3.1.6 y que las tres
  configuraciones conviven; corregir lo que las pruebas destapen.
- **Archivos:** modificar `tests/test_install.py`, `install.ps1` (sólo correcciones).
- **Pasos:** pruebas de los casos 25 a 29; regresión de la salida sin configuración.
- **Pruebas:** casos 17 y 24 a 31.
- **Aceptación:** la suite pasa; cada fila K1 a K7 tiene una prueba; con el repositorio real, nueve
  alias, nivel 3 y carpeta, los once textos coinciden con la referencia y no queda ningún
  `docs/plans/` reemplazable ni ningún nombre de rol fuera de las subcadenas permitidas; ningún
  cambio de carpeta produce `MODIFICADO` sobre un destino intacto con estado válido; `F4T6_GOLDEN`
  sin modificar.
- **Dependencias:** T3.
- **Revisa:** `auditor` y `shield`.

### Fase B: idioma del reporte de uso

#### T5. Catálogo de textos, español sin cambios — tamaño L

- **Objetivo:** reunir todos los textos fijos de los dos generadores en un catálogo por idioma con
  una sola entrada (`es`), sin cambiar un byte de los reportes.
- **Archivos:** modificar `tools/usage_report.py`, `tests/test_usage_report.py`.
- **Pasos:** **antes de tocar el código**, generar y fijar en la prueba el golden del caso 32 con la
  versión actual (proyecto y global, conjunto sintético amplio de `tests/usage_synth.py`). Pruebas
  rojas: caso 33. Después: `LANGS`, `DEFAULT_LANG`, catálogo `es`; las funciones `_…_section` y sus
  ayudantes toman el texto del catálogo que reciben por argumento; las constantes usadas como
  identificadores por el lector y el agregado no cambian de valor. Las firmas públicas no cambian
  todavía.
- **Pruebas:** casos 32, 33 y 43; todas las de `tests/test_usage_report*.py` sin modificar.
- **Aceptación:** la suite pasa sin modificar ninguna prueba existente; los reportes son idénticos
  byte a byte al golden; ningún estado global mutable decide el texto; el código sigue en ASCII;
  la lista de excepciones del caso 33 es cerrada y cada entrada tiene su motivo en un comentario.
- **Dependencias:** aprobación del plan (independiente de T1 a T4).
- **Revisa:** `auditor`.

#### T6. Idioma `en` y parámetro `--lang` — tamaño M — revisión de seguridad

- **Objetivo:** el reporte en inglés y la opción de la CLI (3.2.2 a 3.2.6).
- **Archivos:** modificar `tools/usage_report.py`, `tests/test_usage_report.py`,
  `tests/test_usage_report_cli.py`, `tests/test_usage_report_edges.py`.
- **Pasos:** pruebas rojas (casos 34 a 42). Catálogo `en` (traducción fiel; tabla de etiquetas de
  listas cerradas); parámetro `lang` de `render_project_report` y `render_global_report`; `--lang`
  en `_add_report_arguments` con `type=` propio; la cabecera de uso del archivo (docstring) al día.
- **Pruebas:** casos 34 a 43.
- **Aceptación:** la suite pasa; sin `--lang`, los bytes son los de antes; con `--lang en` el
  reporte no contiene ningún texto del catálogo `es` que difiera del `en` y es ASCII salvo las
  barras; un valor inválido da exit 2 sin eco y sin tocar el disco; `inspect` no acepta `--lang`;
  ningún mensaje imprime rutas sin `--show-paths` en ninguno de los dos idiomas; el catálogo `en` no
  promete ahorro, calidad ni costo; lector y agregado sin cambios (`git diff` no toca sus funciones).
- **Dependencias:** T5.
- **Revisa:** `auditor` y `shield`.

### Fase C: documentación y cierre

#### T7. Perfiles por proyecto y descartes (documentación) — tamaño S

- **Objetivo:** documentar (f) según 3.3 y dejar escritas las candidatas descartadas. La prueba la
  escribe `forge`; los textos, `scribe`.
- **Archivos:** crear `tests/test_phase5_docs.py`; modificar `README.md`, `docs/agentes.md`,
  `install-manifest.json`.
- **Pasos:** prueba roja (caso 44). README: sección «Perfiles por proyecto» (tabla de 3.3 en
  lenguaje llano; «Desactivar un agente» con `permissions.deny` y `Agent(<nombre>)`; «Lo que no se
  configura y por qué», de 1.2). `docs/agentes.md`: ampliar «Adaptar un agente a un proyecto»
  (copiar el bloque `hooks:`, el alias como nombre a igualar, el nivel no llega, no verificado) y
  una línea sobre desactivar; sin nombres de rol ni el literal `docs/plans` en el texto nuevo.
  Regenerar el manifiesto: `python -B tools/build_manifest.py`.
- **Pruebas:** casos 44 a 46; suite completa.
- **Aceptación:** la suite pasa, incluida la sincronía del manifiesto y los inventarios de roles y
  de `docs/plans`; ninguna frase presenta como hecho lo marcado «no verificado» en 3.3; ningún
  documento promete ahorro, calidad ni costo; nada personal.
- **Dependencias:** T4 y T6 (para no cruzarse en `README.md`); no depende de su contenido.
- **Revisa:** `auditor`.

#### T8. Documentación de la carpeta y del idioma — tamaño M

- **Objetivo:** documentación al día en el mismo cambio. La escribe `scribe`; la sesión principal
  regenera el manifiesto y corre la suite.
- **Archivos:** modificar `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`,
  `install-manifest.json`, `tests/test_phase5_docs.py`,
  `docs/plans/2026-11-19-backlog-configuracion-y-reportes.md`.
- **Pasos:**
  - Prueba roja: caso 47.
  - `README.md`: sección «Carpeta de planes» (formato, reglas L1 a L5 en lenguaje llano, `-DryRun`,
    línea `Planes:`, qué textos cambian, cambiar y quitar); «Instalación» (línea nueva, textos de
    verificación); «Límites del instalador» (3.1.8; clave repetida y `__type`; G1 pendiente);
    «Reporte de uso» (`--lang` en la sinopsis y en la tabla; qué se traduce y qué no) y «Límites del
    reporte de uso» (mensajes y `inspect` sólo en español; el idioma no se guarda; un reporte
    sustituye al del otro idioma); «Estructura» y «Pruebas» (conteos de la salida real); «Línea de
    tiempo y avance».
  - `CLAUDE.md`: comandos (sinopsis con `--lang`), arquitectura (clave `plans_dir`), convenciones
    (`$PlansDirDefault`, `$PlansDirPattern`, `$PlansDirMaxLength`, `# Planes:` y
    `function ConvertTo-PlansBytes` son contrato con las pruebas; todo texto del reporte va en el
    catálogo, en los dos idiomas, con paridad), no obvios (orden alias, planes, nivel; desde
    `# Planes:` la variable `$aliasBytes` lleva también la carpeta; el inventario de
    `tests/test_plans.py` falla si aparece un `docs/plans` nuevo en un archivo gestionado: el
    literal se transforma al instalar; el valor nunca es una ruta para el instalador; las etiquetas
    en español del lector son identificadores y no se traducen en origen; `--lang` usa `type=` y no
    `choices=`).
  - `HISTORY.md`, `[Sin publicar]`: «Añadido (Fase 5)».
  - `docs/agentes.md`: apartado «Cambiar la carpeta de planes» y una línea de `--lang` en «Reporte
    de uso». Sin el literal `docs/plans` ni nombres de rol en el texto nuevo.
  - Regenerar el manifiesto. Backlog: estado de la Fase 5.
- **Pruebas:** casos 45 a 47; suite completa.
- **Aceptación:** la suite pasa; siguen siendo doce archivos gestionados; `git diff main --stat` no
  muestra cambios en `agents/`, `rules/agentes.md` (salvo P12), `hooks/`, `assets/`,
  `tools/build_manifest.py`, `tests/test_manifest.py` ni `tests/test_brand_agents.py`; nada marcado
  [G1] se documenta como probado.
- **Dependencias:** T7.
- **Revisa:** `auditor`.

#### Cierre (lo coordina la sesión principal; cuenta como una unidad)

- **C1. `sentinel`:** suite completa con la salida a la vista; los 47 casos de 3.4 cubiertos.
- **C2. `shield`:** T2 a T4 y T6. Aplica: entrada de usuario (`plans_dir`, `--lang`) y escritura de
  texto derivado de esa entrada. Focos: que ningún valor de `plans_dir` inyecte Markdown, una línea
  o una instrucción en un prompt; que el frontmatter y `hooks:` no cambien con ninguna carpeta; que
  el valor nunca forme una ruta ni llegue a una llamada de E/S; fuga del valor en mensajes de error;
  comparaciones no ordinales o con `IgnoreCase`; que la combinación con alias no reintroduzca un
  nombre de rol; lectura única de la configuración; que `--lang` no se imprima, no forme rutas y no
  abra una fuga en los textos `en`; que ningún camino de `--lang` inválido toque el disco.
- **C3. `auditor`** sobre el cambio completo.
- **C4.** Memoria del proyecto actualizada por la sesión principal.
- **V1 (propietario; fuera del conteo):** G1.
- **V2 (propietario; fuera del conteo):** `-DryRun` e instalación real con `plans_dir` sobre
  `~/.claude`; una corrida real `global --lang en --stdout`.

### 4.6 Unidades y aritmética de la línea de tiempo

La Fase 5 tiene **9 unidades**: T1 a T8 y el cierre. El paso previo, G1, V1 y V2 no cuentan.

| Frente | Unidades |
|---|---|
| Carpeta de planes | 4 (T1, T2, T3, T4) |
| Idioma del reporte de uso | 2 (T5, T6) |
| Documentación y cierre | 3 (T7, T8, cierre) |

Con k unidades cerradas: Fase 5 = k ÷ 9. Proyecto completo = (400 + 100 × k ÷ 9) ÷ 5 =
80 + 20 × k ÷ 9. Fases 1 a 4 al 100 %. Un cuadro = 10 %; la mitad exacta redondea hacia arriba, y el
porcentaje mostrado también.

| k | Fase 5 | Mostrado | Cuadros | Global | Mostrado | Cuadros |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 0 % | 0 % | 0 | 80 % | 80 % | 8 |
| 1 | 11,11 % | 11 % | 1 | 82,22 % | 82 % | 8 |
| 2 | 22,22 % | 22 % | 2 | 84,44 % | 84 % | 8 |
| 3 | 33,33 % | 33 % | 3 | 86,67 % | 87 % | 9 |
| 4 | 44,44 % | 44 % | 4 | 88,89 % | 89 % | 9 |
| 5 | 55,56 % | 56 % | 6 | 91,11 % | 91 % | 9 |
| 6 | 66,67 % | 67 % | 7 | 93,33 % | 93 % | 9 |
| 7 | 77,78 % | 78 % | 8 | 95,56 % | 96 % | 10 |
| 8 | 88,89 % | 89 % | 9 | 97,78 % | 98 % | 10 |
| 9 | 100 % | 100 % | 10 | 100 % | 100 % | 10 |

Con k = 7 y k = 8 el global muestra diez cuadros sin estar al 100 %: es el redondeo de la regla; el
porcentaje escrito manda. Por frente: 4 unidades (0, 25, 50, 75, 100 %: 0, 3, 5, 8, 10 cuadros);
2 unidades (0, 50, 100 %: 0, 5, 10); 3 unidades (0, 33, 67, 100 %: 0, 3, 7, 10). Si una respuesta a
los puntos abiertos añade tareas (P8 con la opción B, P12 con la alternativa), las unidades cambian
y se recalcula con la misma fórmula.

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| El valor de `plans_dir` inyecta texto en el prompt de `atlas` o en las reglas | Alfabeto cerrado L2, tope L3; el mensaje nunca imprime un valor inválido; casos 4, 12; foco de `shield` |
| La carpeta trae un nombre de rol y la transformación de alias lo cambia o falla | L5; casos 4, 8 y 26 |
| El orden alias, planes, nivel altera el resultado | Zonas que no se pisan; la referencia compara los tres órdenes (caso 8) y el inventario falla ante una forma `<segmento>/plans/` nueva (`segment_problems`, 3.1.4); el instalador se compara con la referencia (casos 25, 26) |
| El bloque `# Planes:` rompe un ancla o una aserción estática de las Fases 3 o 4 (la prueba exige `ConvertTo-LevelBytes $aliasBytes[$rel]` en `# Nivel:`) | El bloque reescribe `$aliasBytes` en su sitio y no edita `# Nivel:` (3.1.4); anclas enumeradas; la suite existente no se modifica (caso 30) |
| `$aliasBytes` pasa a significar «alias y carpeta» y confunde a quien lea el script | Comentarios en el bloque y nota en `CLAUDE.md` (T8) |
| Alguien añade un `docs/plans` nuevo a un archivo gestionado y se transforma sin querer (o queda sin transformar por su forma) | Inventario fijado (casos 2, 3); regla para `scribe` en T7 y T8; aviso en `CLAUDE.md` |
| Sin la clave, la salida o los bytes cambian | Sin carpeta efectiva no se llama a nada ni se imprime nada; casos 10, 20, 30; `F4T6_GOLDEN` |
| El usuario espera que el instalador mueva los planes o que `atlas` obedezca siempre | Límites en el README (3.1.8); G1 |
| La expresión del límite izquierdo difiere entre PowerShell y Python | La misma expresión, con lookbehind de ancho fijo; casos 5 y 18 |
| Comportamiento de `ConvertFrom-Json` de 5.1 con la clave repetida o con `[valor]` | `Get-PropRaw(...).Value` estricto; caso 11 (lista de una cadena) y caso 16 |
| Extraer el catálogo cambia un byte del reporte en español | Golden generado antes del cambio (caso 32); pruebas existentes sin modificar |
| Queda un texto en español fuera del catálogo y el reporte `en` sale mezclado | Prueba estática con `ast` (caso 33); reporte `en` todo ASCII salvo las barras (caso 36) |
| La traducción cambia el sentido o promete ahorro | Paridad de marcadores (caso 34); patrones de promesa en inglés (caso 35); revisión de `auditor` frase a frase |
| Traducir una etiqueta del lector rompe una comparación interna (`KNOWN_WARNINGS`, `READ_WARNED`) | Las constantes no cambian de valor; se traduce sólo al imprimir; caso 38; `git diff` sin cambios en lector y agregado |
| `argparse` repite el valor inválido de `--lang` | `type=` propio con mensaje fijo; caso 40 |
| El idioma se decide con una variable global y un reporte sale en el idioma de la corrida anterior (pruebas en el mismo proceso) | Idioma por argumento; funciones puras; caso 36 |
| Los mensajes de la CLI siguen en español con `--lang en` y sorprende | Documentado como alcance (P10) |
| La documentación de perfiles afirma algo no verificado sobre `hooks:` | Tabla de 3.3 con el grado de certeza; caso 44; G1; revisión de `auditor` |
| El texto nuevo de la guía nombra un rol o `docs/plans` y se transforma al instalar | Regla de T7 y T8 (`<nombre>`, `<alias>`); caso 46 |
| La línea de tiempo se desincroniza si los dos frentes van en paralelo | Secuencial por defecto (P13) |
| La suite se alarga | `subTest`; validación sobre todo en Python; un solo conjunto sintético para los goldens |
| Un agente instala o reporta contra el `~/.claude` real | Regla en todos los prompts; `-Target`, `HOME` y `--claude-dir` temporales |

## 6. Preguntas abiertas

Cada una tiene un valor por defecto, que es lo que el plan implementa si no hay respuesta.
El propietario aprobó el 2026-11-24 los valores por defecto de las catorce: cada una queda marcada
«decidido: por defecto».

- **P1. Nombre de la clave.** [Decidido: por defecto.] Por defecto: `plans_dir`. Alternativas: `plansDir`, `plans`.
- **P2. Valor por defecto y valor igual al de fábrica.** [Decidido: por defecto.] Por defecto: ausente = `docs/plans`;
  escribir `docs/plans` es válido y no tiene efecto. Alternativa: exit 1 si es igual al de fábrica.
- **P3. Subcarpetas.** [Decidido: por defecto.] Por defecto: de 1 a 4 carpetas, 32 caracteres cada una, 64 en total.
  Alternativas: sólo una o dos carpetas; sin tope de profundidad.
- **P4. Alfabeto.** [Decidido: por defecto.] Por defecto: minúsculas, dígitos, `_` y `-`; sin mayúsculas, puntos ni espacios
  (`Docs/Plans` y `.planning` se rechazan). Alternativa: admitir mayúsculas y un punto inicial por
  segmento (más casos en L5 y en la comparación con los nombres de rol).
- **P5. Alcance del reemplazo.** [Decidido: por defecto.] Por defecto: los tres textos que hoy nombran la carpeta, incluido el
  prompt en inglés de `atlas`. Alternativa: sólo `rules/agentes.md` y `docs/agentes.md` (el prompt
  de `atlas` seguiría diciendo `docs/plans/`, incoherente con las reglas).
- **P6. «Carpeta anterior» en la salida.** [Decidido: por defecto.] Por defecto: no se guarda ni se muestra (el estado no
  cambia de esquema). Alternativa: guardarla en el estado (esquema nuevo y su validación).
- **P7. Carpeta que contiene el nombre de un agente (L5).** [Decidido: por defecto.] Por defecto: se rechaza.
  Alternativa: admitirla sólo si no hay alias (regla que depende de otra clave).
- **P8. Dónde vive el idioma.** [Decidido: por defecto.] Por defecto: sólo el parámetro `--lang`. Alternativa: además una
  clave en `synclayer-config.json` (el instalador tendría que aceptarla sin usarla y la herramienta
  necesitaría un lector defensivo propio: una tarea más con revisión de seguridad, 10 unidades).
- **P9. Idiomas iniciales.** [Decidido: por defecto.] Por defecto: `es` (por defecto) y `en`. Alternativa: sumar otro idioma
  (cada idioma es un catálogo completo que mantener en cada cambio de texto).
- **P10. Alcance de la traducción.** [Decidido: por defecto.] Por defecto: sólo el Markdown del reporte, con las etiquetas de
  listas cerradas traducidas al imprimir; las claves del pie, los mensajes de la CLI, la ayuda y
  `inspect` quedan en español. Alternativa: traducir también los mensajes de la CLI (catálogo mayor
  y pruebas de mensajes duplicadas).
- **P11. Marca del idioma en el reporte.** [Decidido: por defecto.] Por defecto: ninguna; el marcador y `REPORT_SCHEMA` no
  cambian. Alternativa: una línea `Idioma:` sólo en el reporte `en`.
- **P12. `rules/agentes.md`.** [Decidido: por defecto.] Por defecto: no se toca (ya dice que un agente de proyecto reemplaza
  al global). Alternativa: una línea sobre copiar el bloque `hooks:` y sobre `permissions.deny`
  (texto que la sesión principal lee en cada conversación, con una afirmación aún sin verificar).
- **P13. Paralelismo.** [Decidido: por defecto.] Por defecto: los dos frentes en secuencia (T1 a T4 y después T5, T6).
  Alternativa: en paralelo, cada `forge` en su worktree, con la sesión principal serializando los
  commits de la línea de tiempo y las corridas de la suite.
- **P14. G1.** [Decidido: por defecto.] Por defecto: no bloquea T1 a T8; la documentación dice «no verificado» hasta que se
  corra. Alternativa: G1 antes de T7, para documentar perfiles con el resultado.
