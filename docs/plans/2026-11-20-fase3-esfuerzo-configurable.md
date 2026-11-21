# Plan: Fase 3, esfuerzo configurable por niveles (`synclayer-config.json`)

Fecha: 2026-11-20. Estado: **aprobado por el propietario el 2026-11-20** (el plan, la tabla de 3.2 y los valores por defecto de P2 a P8, sin cambios).

Fuentes: [`2026-11-20-fase3-esfuerzo-exploracion.md`](2026-11-20-fase3-esfuerzo-exploracion.md)
(hechos verificados por `scout`, mapa de `oracle`, opciones y riesgos) y
[`2026-11-19-backlog-configuracion-y-reportes.md`](2026-11-19-backlog-configuracion-y-reportes.md)
(Fase 3 y «Restricción de diseño: simple»). Rama: `feat/esfuerzo-configurable`.

## 1. Objetivo

Que quien instala SyncLayer pueda elegir uno de cinco niveles en
`<Target>/synclayer-config.json` y que `install.ps1`, al instalar, escriba el `model:` y el
`effort:` de los seis agentes modificables (`atlas`, `forge`, `sentinel`, `scribe`, `scout`,
`oracle`) según ese nivel. Cambiar de nivel = editar el archivo y reinstalar. El nivel 5 es el
repositorio tal cual: quien no configura nada instala los mismos bytes que hoy.

### Decisiones ya tomadas (no se reabren)

1. Los niveles controlan modelo y esfuerzo de los seis agentes modificables. `auditor`, `shield`
   y `debugger` quedan fijos en todos los niveles (modelo actual, sin `effort:`, hook intacto).
2. Cinco niveles. El nivel 5 reproduce exactamente los bytes del repositorio.
3. Configuración en `<Target>/synclayer-config.json`, campo único `level` (entero de 1 a 5),
   lista cerrada, sin sobreescrituras por agente. `-DryRun` lo lee sin escribir. Inválido: exit 1
   antes de escribir. La Fase 4 podrá añadir su tabla de alias al mismo archivo.
4. Para los niveles 1 a 4 el instalador parte de los bytes canónicos del origen y sólo toca las
   líneas `model:` y `effort:` del frontmatter. El estado guarda, por archivo, hash del origen,
   hash de lo escrito y nivel. Estado versionado: el esquema viejo se lee y se migra.
5. La tabla nivel por agente vive en `install.ps1`, con valores de lista cerrada y una prueba
   que la compara con la documentada. No hay archivo gestionado número trece.
6. El instalador avisa (sólo lectura) de `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` y
   `CLAUDE_CODE_EFFORT_LEVEL`. El README documenta el resto de anulaciones.
7. Ningún texto promete ahorro de tokens ni de costo.

### Dentro de alcance

- `install.ps1`: tabla de niveles, lectura del archivo de configuración, renderizado del
  frontmatter, estado con esquema 2 y migración, avisos de entorno.
- Pruebas nuevas y adaptación de las existentes de `tests/test_install.py`.
- Documentación: `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`, `rules/agentes.md`,
  manifiesto regenerado, estado de la Fase 3 en el backlog.

### Fuera de alcance

- Sobreescrituras por agente, niveles definidos por el usuario o un parámetro `-Level`.
- Cambiar `agents/*.md`, `tools/build_manifest.py`, el formato de `install-manifest.json`,
  `assets/brand/src/agents_data.py`, `tests/test_brand_agents.py` o los SVG: siguen en nivel 5.
- Tocar `auditor`, `shield`, `debugger` o `hooks/agent_guard.py`.
- Que el instalador cree, edite, respalde o borre `synclayer-config.json`.
- Leer o escribir `settings.json`. Cambiar variables de entorno.
- Medir ahorro. Comparar tokens por nivel con el reporte de uso (extensión posible, otra fase).
- Fase 4 (nombres). Sólo se deja el archivo de configuración preparado (3.1).
- Cambiar el recordatorio «reinicia las sesiones» antes de la verificación V1.

## 2. Supuestos

Los marcados **[G1]** los confirma el propietario en la compuerta G1, antes de T4.

1. Windows PowerShell 5.1, `install.ps1` en ASCII sin BOM, mensajes en español sin acentos.
   Python 3.12 con `-B`, sólo biblioteca estándar, `unittest`.
2. **[G1]** La versión de Claude Code instalada reconoce `effort:` en el frontmatter de un
   subagente (`claude --debug` no lo lista como campo no reconocido). La exploración confirmó
   que el campo existe; no confirmó desde qué versión.
3. **[G1]** Los alias `opus`, `sonnet` y `haiku` en `model:` funcionan en un subagente con la
   versión instalada.
4. Los cinco valores de `effort` (`low`, `medium`, `high`, `xhigh`, `max`) existen en Fable,
   Opus 5.5, Sonnet 5.5 y Haiku 5.5 (hecho verificado). Un valor no soportado baja al más alto
   soportado igual o inferior.
5. Sin `effort:` en el frontmatter, el subagente usa el esfuerzo de la sesión (inferido de «el
   `effort:` del frontmatter sobrescribe el de la sesión»). No verificado de forma directa.
6. El frontmatter de los seis agentes modificables tiene hoy exactamente una línea `model:` en
   la columna 0 y ninguna `effort:` (comprobado en el repositorio; T1 lo fija con una prueba).
7. Los doce archivos gestionados siguen siendo doce. `synclayer-config.json` no es gestionado.
8. Ningún agente ejecuta el instalador sin `-Target` a una carpeta temporal. Los prompts de
   `forge`, `sentinel`, `auditor` y `shield` lo dicen de forma explícita.

## 3. Diseño

### 3.1 Archivo de configuración

Ruta: `<Target>/synclayer-config.json`, junto a `synclayer-manifest.json`. Lo escribe el
usuario a mano. El instalador sólo lo lee, una vez.

```json
{ "level": 3 }
```

| Regla | Detalle |
|---|---|
| Ausente | Nivel 5. No es un error |
| Codificación | UTF-8, con o sin BOM; CRLF o LF |
| Tamaño máximo | 65 536 bytes. Mayor: exit 1 sin interpretar |
| Raíz | Un objeto JSON. `null`, lista, número o cadena: exit 1 |
| Claves | Lista cerrada: sólo `level`. Cualquier otra (incluida `Level`): exit 1. Se comparan distinguiendo mayúsculas (`Get-PropRaw`) |
| `level` | Entero (`[int]` o `[long]`) de 1 a 5. `"3"`, `3.0`, `true`, 0, 6 y negativos: exit 1 |
| Objeto vacío `{}` | Válido, nivel 5 (ver P4) |
| Carpeta, punto de reanálisis, bloqueado o ilegible | exit 1. No se trata como ausente (al contrario que el estado): un nivel que no se puede leer no se sustituye en silencio por el 5 |

Opciones consideradas para dejar sitio a la Fase 4:

| Opción | A favor | En contra |
|---|---|---|
| A. Claves de lista cerrada; una clave desconocida da exit 1 | Falla cerrado: un instalador viejo ante un archivo de la Fase 4 se detiene en vez de instalar con nombres por defecto. La Fase 4 sólo añade su clave a la lista | Un archivo más nuevo que el instalador no instala |
| B. Ignorar claves desconocidas | Compatible hacia adelante | Un error de escritura (`"nivel": 2`) instala nivel 5 sin avisar |
| C. Campo `schema` obligatorio | Versión explícita | Segundo campo que el usuario escribe a mano; contradice «campo único» |

Se elige **A**, sin `schema`. El mensaje de la clave desconocida dice que el instalador puede
ser anterior al archivo.

### 3.2 Tabla nivel por agente — **aprobada por el propietario (2026-11-20)**

Afinada sobre la hipótesis 5.4 de la exploración. «—» significa «sin `effort:`» (no se toca; el
agente usa el esfuerzo de la sesión, supuesto 5).

Fijos en todos los niveles: `auditor` (`opus`), `shield` (`opus`), `debugger` (`opus`), sin `effort:`.

| Agente | Nivel 5 (repo) | Nivel 4 | Nivel 3 | Nivel 2 | Nivel 1 |
|---|---|---|---|---|---|
| `atlas` | `claude-fable-5-2`, — | `opus`, — | `opus`, `medium` | `sonnet`, `medium` | `sonnet`, `medium` |
| `forge` | `sonnet`, — | `sonnet`, — | `sonnet`, — | `sonnet`, `medium` | `sonnet`, `low` |
| `sentinel` | `sonnet`, — | `sonnet`, — | `sonnet`, — | `sonnet`, — | `sonnet`, `medium` |
| `scribe` | `sonnet`, — | `sonnet`, — | `sonnet`, `medium` | `sonnet`, `low` | `haiku`, `medium` |
| `scout` | `sonnet`, — | `sonnet`, — | `sonnet`, — | `sonnet`, `medium` | `sonnet`, `low` |
| `oracle` | `haiku`, — | `haiku`, — | `haiku`, — | `haiku`, — | `haiku`, — |

Reglas con las que se construyó (T1 las convierte en prueba):

- **R1.** El nivel 5 es el frontmatter del repositorio.
- **R2.** Por agente, al bajar un nivel el par (modelo, esfuerzo) no sube. Orden de modelo:
  `claude-fable-5-2` > `opus` > `sonnet` > `haiku`. Orden de esfuerzo: — > `max` > `xhigh` >
  `high` > `medium` > `low`. La comparación es lexicográfica: si baja el modelo, el esfuerzo
  puede reiniciarse.
- **R3.** Ninguna celda combina `haiku` con `low`.
- **R4.** Niveles contiguos difieren en al menos un agente.
- **R5.** Modelos escritos: sólo los alias `opus`, `sonnet`, `haiku`. Esfuerzos: sólo los cinco
  valores oficiales.

Justificación por agente, con los hechos verificados (precios por millón de tokens,
entrada/salida: Fable 5.2 8/40, Opus 5.5 4/20, Sonnet 5.5 2/10, Haiku 5.5 0,10/0,50):

| Agente | Qué cambia respecto de la hipótesis | Motivo |
|---|---|---|
| `atlas` | Niveles 2 y 1: `sonnet`, `medium` (antes `sonnet` sin esfuerzo y `sonnet`, `low`) | Es el agente más caro por token, por eso baja primero y sólo de modelo (nivel 4: mitad de precio por token). En el nivel 2 el esfuerzo queda en `medium` para que R2 se cumpla (un `sonnet` sin `effort:` hereda el de la sesión, que puede ser mayor que el `medium` del nivel 3). Nunca `low`: el plan gobierna todas las tasks y la documentación avisa de que bajar el esfuerzo reduce capacidad |
| `forge` | Igual que la hipótesis | Es el agente con más llamadas (una por task). Su salida la revisa `auditor`, que es fijo: es donde bajar el esfuerzo tiene red de seguridad |
| `sentinel` | Sin cambio hasta el nivel 1, y ahí `medium` (antes `medium` en el 2 y `low` en el 1) | Su evidencia pesa más que la opinión de `auditor` en la precedencia de `rules/agentes.md`. Es el último en bajar y nunca llega a `low` |
| `scribe` | Nivel 1: `haiku`, `medium` (antes `haiku`, `low`) | Documentación: el riesgo más bajo, baja primero de esfuerzo. En el nivel 1 pasa a Haiku (20 veces más barato por token que Sonnet), pero no con `low`: la documentación oficial avisa de que Haiku 5.5 en `low` tiende a saltarse búsquedas y comprobaciones (R3) |
| `scout` | Se queda en `sonnet` en todos los niveles; `medium` en el 2 y `low` en el 1 (antes `medium`, `low` y `haiku`, `low`) | Su trabajo es buscar y verificar: justo lo que Haiku en `low` tiende a saltarse. Un hecho mal verificado contamina el plan |
| `oracle` | Sin cambio en ningún nivel (antes `haiku`, `low` en los niveles 2 y 1) | Ya usa el modelo más barato (0,10/0,50): lo que se puede bajar es mínimo, y la única palanca que queda es la que la documentación desaconseja (R3). Se mantiene en la tabla, con el mismo valor, para que la lista de modificables no cambie (ver P2) |

Límites de la tabla, que el README dirá tal cual:

- Es un orden razonado, no una medición. La documentación no da cifras de ahorro ni de pérdida
  de calidad por nivel.
- El precio por token no es el costo por tarea: un modelo más barato puede gastar más tokens.
- Un `effort:` explícito fija el esfuerzo del agente aunque la sesión tenga otro. Si la sesión
  corre en `low`, una celda `medium` lo sube para ese agente. R2 ordena las celdas entre sí, no
  frente a la sesión.
- Los alias cambian de versión con el tiempo.

Formato en `install.ps1` (contrato con `tests/test_levels.py`; una fila por línea,
`nivel|agente|modelo|esfuerzo`, `-` = sin `effort:`):

```powershell
$LevelAgents = @('atlas', 'forge', 'sentinel', 'scribe', 'scout', 'oracle')
$AllowedModels = @('opus', 'sonnet', 'haiku')
$AllowedEfforts = @('-', 'low', 'medium', 'high', 'xhigh', 'max')
$LevelRows = @(
    '4|atlas|opus|-',
    ...
)
```

Son 24 filas (niveles 1 a 4 por seis agentes). El nivel 5 no tiene filas: no se renderiza. Al
arrancar, el script valida la tabla (24 filas únicas, agente en `$LevelAgents`, valores en las
listas) y sale con 1 si no cumple. La tabla documentada es la del README, entre los marcadores
`<!-- niveles:inicio -->` y `<!-- niveles:fin -->`.

### 3.3 Renderizado del frontmatter

Se aplica sólo si el nivel es 1 a 4, y sólo a `agents/<nombre>.md` con `<nombre>` en
`$LevelAgents` que esté en el manifiesto. Entrada: los bytes canónicos ya verificados contra el
manifiesto en el Paso 2 (`$canonSrc`), el modelo y el esfuerzo de la celda. Salida: bytes a
escribir. Función pura, sin E/S.

1. Decodificar en ISO-8859-1 (como `ConvertTo-CanonicalBytes`) y partir por `LF`.
2. La línea 0 debe ser exactamente `---`. Si no (incluido un BOM delante): error.
3. Cierre: la primera línea posterior que sea exactamente `---`. Si no hay: error.
4. Entre ambas, contar las líneas que empiezan por `model:` en la columna 0 (comparación
   ordinal). Debe haber exactamente una. Cero o más de una: error.
5. Contar las que empiezan por `effort:` en la columna 0. Más de una: error.
6. Sustituir la línea `model:` por `model: <modelo>`.
7. Esfuerzo: si la celda trae valor y hay línea `effort:`, sustituirla por `effort: <valor>`; si
   no hay, insertar `effort: <valor>` justo después de la línea `model:`. Si la celda es `-`, no
   se toca nada (una `effort:` del origen se conserva).
8. Unir con `LF` y codificar en ISO-8859-1.
9. Autocomprobación: el resultado tiene las mismas líneas que la entrada, salvo la de `model:`,
   la de `effort:` y, como mucho, una línea insertada. Si no: error.

Casos límite:

| Caso | Resultado |
|---|---|
| `model:` ausente en el frontmatter | Error |
| `model:` duplicado | Error |
| `effort:` ya presente, celda con valor | Se sustituye en su sitio |
| `effort:` ya presente, celda `-` | Se conserva |
| `effort:` duplicado | Error |
| Origen con CRLF | Ya llega en LF (bytes canónicos). El destino queda en LF |
| CR suelto en la línea `---` o en `model:` | `---\r` no es un cierre; `model: x\r` se sustituye entera. Sin caso especial |
| Frontmatter sin cierre | Error |
| Primera línea distinta de `---` (BOM, línea en blanco) | Error |
| `model:` indentado (dentro de `hooks:` u otro bloque) | No cuenta y no se toca |
| `model:` en el cuerpo, tras el cierre | No se toca |
| Celda igual al origen (`sonnet`, `-` sobre `model: sonnet`) | Bytes idénticos al origen |
| `model:` con espacios extra o comentario | Se normaliza a `model: <modelo>` |
| Agente modificable que no está en el manifiesto | No se renderiza; no es error |

Un error de renderizado es un defecto del origen que el manifiesto no detecta: exit 1 antes de
escribir, también en `-DryRun`, con
`error: no se puede aplicar el nivel N a agents/<nombre>.md: <motivo>. No se escribio nada.`

Por archivo quedan dos valores: `srcHash` (el del manifiesto) y `outBytes`/`outHash` (lo que se
va a escribir). Para los archivos no renderizados, `outBytes` son los bytes canónicos del origen.

### 3.4 Estado con esquema 2 y migración

`<Target>/synclayer-manifest.json` deja de ser una copia del manifiesto. Formato nuevo, siempre
(también en el nivel 5):

```json
{
  "schema": 2,
  "algorithm": "sha256",
  "eol": "lf",
  "files": [
    {
      "path": "agents/atlas.md",
      "sha256": "<hash canonico del origen>",
      "written": "<hash canonico de lo escrito>",
      "level": 3
    }
  ]
}
```

- Orden de `files`: el del manifiesto. `level` es el nivel de la instalación, igual en todas las
  entradas (va por archivo por decisión del propietario y deja sitio a ajustes por agente).
- Bytes exactos: ASCII, `LF`, sangría de dos espacios, salto final. Deben coincidir byte a byte
  con `json.dumps(obj, indent=2, ensure_ascii=True) + "\n"` de Python con ese orden de claves.
  `install.ps1` lo construye con `StringBuilder` (no con `ConvertTo-Json`, cuyo formato en 5.1
  es distinto). Es una función pura de manifiesto, nivel y origen: reinstalar sin cambios no
  reescribe el estado.
- `install-manifest.json` del repositorio no cambia: sigue en `schema` 1 y `Read-Manifest` sigue
  exigiendo 1. El estado se lee con una función nueva, `Read-State`.

Lectura del estado previo:

| Estado previo | Tratamiento |
|---|---|
| `schema` 1 (instalador de la Fase 1) | Válido. `written` = `sha256` y `level` = 5 por archivo: aquel instalador escribía los bytes canónicos del origen |
| `schema` 2 | Mismas validaciones de ruta que el manifiesto, más `written` de 64 hex minúsculas y `level` entero de 1 a 5 |
| Otro `schema`, ilegible o inválido | Ausente, con el aviso actual por stderr. No se respalda |

Migración: al reinstalar con un estado `schema` 1, el estado se reescribe en `schema` 2 y el
viejo va al respaldo (regla actual: estado válido que se reescribe, se respalda). Consecuencia
aceptada: la primera reinstalación tras actualizar crea una carpeta de respaldo aunque todos los
archivos salgan `IGUAL`. Un instalador anterior no sabe leer el `schema` 2: lo trata como ausente
(se documenta en «Límites del instalador»).

Opción descartada: escribir `schema` 1 en el nivel 5 y `schema` 2 sólo en los niveles 1 a 4.
Dejaría intactos los casos 3, 7 y 18, pero mantiene dos formatos de escritura para siempre.

### 3.5 Clasificación

La regla actual se conserva; cambian los dos hashes con los que se compara.

| ¿Existe el destino? | hash destino = `outHash` | estado previo con la ruta y `written` = hash destino | Estado | Acción |
|---|---|---|---|---|
| No | — | — | `NUEVO` | Escribe `outBytes` |
| Sí | Sí | — | `IGUAL` | Nada |
| Sí | No | Sí | `ACTUALIZAR` | Respalda y escribe |
| Sí | No | No | `MODIFICADO` | Sin `-Force`: exit 3. Con `-Force`: respalda y escribe |
| (ruta del estado previo que ya no está en el manifiesto) | | | `HUERFANO` | Sólo informa |

Cómo quedan las situaciones que importan:

| Situación | Resultado |
|---|---|
| Sin configuración, destino instalado por la Fase 1 | Todo `IGUAL`; el estado migra a `schema` 2 |
| Nivel 5 a 3 | Los agentes cuya celda cambia: `ACTUALIZAR`. El resto: `IGUAL` |
| Nivel 3 a 5 | Vuelven a los bytes del repositorio: `ACTUALIZAR` |
| Edición a mano de `model:` tras instalar | `MODIFICADO`, exit 3 |
| Edición a mano de un agente fijo | `MODIFICADO`, exit 3 (como hoy) |
| Cambio de nivel y cambio del origen a la vez | `ACTUALIZAR` |
| Estado `schema` 1, destino intacto, configuración en nivel 3 | `ACTUALIZAR` |
| Sin estado, destino en bytes del repositorio, configuración en nivel 3 | `MODIFICADO` (regla vigente: sin estado, todo lo distinto es `MODIFICADO`) |
| Estado ilegible, destino ya en el nivel pedido | `IGUAL`; el estado se reescribe sin respaldo |

Descartado: reconocer sin estado «el destino coincide con el origen o con el renderizado de otro
nivel» como `ACTUALIZAR`. Es más cómodo cuando se pierde el estado, pero añade una segunda regla
de clasificación. `-Force` (con respaldo) cubre ese caso.

Las verificaciones de los Pasos 7 y 8 comparan con `outHash`, no con el hash del manifiesto.

### 3.6 Orden de ejecución y marcadores

Los diez comentarios `# Paso N:` no se renombran ni se mueven. El bloque nuevo va entre el
Paso 2 y el Paso 3, con marcadores que no empiezan por `# Paso`:

1. Validaciones de `-Target` y `-BackupDir` (como hoy).
2. Validación de la tabla de niveles (exit 1).
3. Paso 1 y Paso 2 (como hoy; exit 2 si el origen no coincide).
4. `# Configuracion:` leer y validar `synclayer-config.json` (exit 1).
5. `# Nivel:` renderizar y calcular `outBytes` y `outHash` (exit 1).
6. Paso 3 en adelante.

Anclas de `patch_script` que cambian de texto y hay que actualizar en la misma task:
`Write-Atomic $dest $canonSrc[$rel] $existing` (pasa a escribir `outBytes`). El ancla
`Write-Atomic $statePath $stateBytes $stateExists` se conserva.

### 3.7 Salida de `-DryRun`, mensajes y códigos de salida

Líneas nuevas en stdout, tras `Destino:`:

| Situación | Línea |
|---|---|
| Sin archivo de configuración | `Nivel: 5 (por defecto; no hay synclayer-config.json)` |
| Con archivo | `Nivel: N (synclayer-config.json)` |
| El estado previo tiene otro nivel | `Nivel anterior: M` |
| Nivel 1 a 4, una por agente renderizado, tras el `Resumen:` | `Ajuste: agents/atlas.md  model: opus  effort: medium` (`effort: -` si la celda no lo fija) |

`Ajuste:` no casa con la expresión `LINE` de las pruebas. Los códigos de salida no cambian de
significado:

| Código | Casos nuevos |
|---|---|
| 1 | Tabla de niveles incoherente; configuración inválida, ilegible, carpeta o punto de reanálisis; error de renderizado |
| 3 | Sin cambios de regla. El mensaje añade: `Si cambiaste model: o effort: a mano, usa synclayer-config.json.` |
| 4 | El archivo escrito no coincide con lo esperado para el nivel |

Mensajes de configuración (ASCII, sin acentos; nombres de clave por `Format-Safe`; nunca el
contenido del archivo):

- `error: synclayer-config.json no es valido: <motivo>. No se escribio nada.`
- Motivos: `JSON invalido`; `debe ser un objeto`; `clave desconocida: <clave> (el instalador
  puede ser anterior al archivo)`; `level debe ser un entero de 1 a 5`; `supera 65536 bytes`.

### 3.8 Avisos de entorno

Con nivel 1 a 4, si `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` o `CLAUDE_CODE_EFFORT_LEVEL` existe y no
está vacía en el entorno del instalador, un aviso por stderr por variable, en `-DryRun` y en
ejecución real, sin cambiar el código de salida:

- `aviso: CLAUDE_CODE_SUBAGENT_MODEL_FORCE esta definida: Claude Code ignora el model: de los agentes y el nivel N no cambia el modelo.`
- `aviso: CLAUDE_CODE_EFFORT_LEVEL esta definida: tiene prioridad sobre el effort: de los agentes.`

Sólo se lee el nombre y si tiene valor. El valor no se imprime. En el nivel 5 no hay aviso: así
se cumple a la vez la decisión 2 (quien no configura nada no ve nada nuevo) y la 6 (ver P5).

Lo que el instalador no puede ver, y documenta el README: variables definidas en el bloque `env`
de `settings.json` o en otro shell; un `.claude/agents/<nombre>.md` de proyecto con el mismo
nombre; `maxEffortLevel` o `availableModels` gestionados; el parámetro `model` de la llamada a
Agent.

### 3.9 Estrategia de pruebas

- `tests/levels_ref.py` (auxiliar, no es un `test_*.py`): lectura de `$LevelRows` desde el texto
  de `install.ps1`, renderizador de referencia en Python (`render_expected(data, model, effort)`)
  y generador del estado esperado (`state_for(manifest, out_hashes, level)`). Es una segunda
  implementación independiente: las pruebas comparan bytes del instalador contra ella.
- `tests/test_levels.py`: pruebas que no necesitan PowerShell (tabla, README, frontmatter real).
- `tests/test_install.py`: casos con `powershell.exe`, siempre con `-Target` temporal. Fixture
  nuevo `LEVEL_SAMPLE` con `agents/atlas.md`, `agents/sentinel.md` (con bloque `hooks:`),
  `agents/auditor.md` y los tres archivos fijos, todos con frontmatter mínimo.
- `run_install` quita por defecto del entorno heredado `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` y
  `CLAUDE_CODE_EFFORT_LEVEL` (la suite puede correr dentro de una sesión que las defina).
- Adaptación de lo que se rompe:
  - Las seis aserciones «estado igual byte a byte al manifiesto» (casos 3, 4 y 12 y tres pruebas
    `t5`) pasan a `assert_state(level)`, que compara con `state_for`.
  - `preinstall()` escribe el estado `schema` 2 (lo que deja el instalador nuevo); así las
    pruebas que parten de él no ganan un respaldo por migración. `write_state()` recibe
    `schema=1|2`. Las pruebas de migración usan el `schema` 1 de forma explícita.
  - Caso 7 (idempotencia): sin cambios en la prueba; exige que el estado sea determinista.
  - Caso 18 (repositorio real): se conserva en nivel 5 y gana variantes en los niveles 1 a 4.
- La suite tarda unos 4 minutos y cada caso lanza PowerShell: agrupar variantes con `subTest`
  sólo donde compartan preparación. El conteo de pruebas y de saltadas de la documentación se
  toma de la salida real.

Casos mínimos:

| # | Caso | Se comprueba | Task |
|---|---|---|---|
| 1 | Tabla de `install.ps1` frente a la del README | Mismas 24 celdas | T1 |
| 2 | Lista cerrada | 24 filas únicas; agentes = los seis; modelos y esfuerzos en las listas; `auditor`, `shield` y `debugger` no aparecen | T1 |
| 3 | Reglas R2, R3 y R4 | Ninguna celda sube al bajar de nivel; ninguna `haiku` con `low`; niveles contiguos distintos | T1 |
| 4 | Nivel 5 del README frente a `agents/*.md` | Coincide con el `model:` real; ningún agente tiene `effort:` | T1 |
| 5 | Los seis agentes reales son renderizables | El renderizador de referencia no falla en ningún nivel; sólo cambian las líneas `model:` y `effort:`; el bloque `hooks:` de `sentinel` queda idéntico | T1 |
| 6 | Formato del estado | Instalación limpia: bytes del estado = `state_for(...)`; ASCII, LF, salto final | T2 |
| 7 | Estado `schema` 1 y destino intacto | Todo `IGUAL`; el estado migra a `schema` 2; el viejo queda en el respaldo; segunda corrida sin escrituras | T2 |
| 8 | Estado `schema` 1 con origen cambiado | `ACTUALIZAR` (como hoy) | T2 |
| 9 | Estado `schema` 2 inválido (`written` no hexadecimal, `level` 9, `schema` 3) | Ausente con aviso; no se respalda | T2 |
| 10 | `HUERFANO` con estado `schema` 2 | Se informa y no se borra | T2 |
| 11 | Reejecución idempotente | Estado sin reescribir (bytes y mtime), sin respaldo | T2 |
| 12 | Sin configuración | Mismos bytes de destino que antes; `Nivel: 5 (por defecto...` | T3 |
| 13 | `{"level": 5}` | Destino y estado idénticos byte a byte al caso 12 | T3 |
| 14 | Configuración inválida: JSON roto, vacío, `[]`, `null`, `"3"`, `3.0`, `true`, 0, 6, -1, clave `Level`, clave `agents`, más de 65 536 bytes | Exit 1 en `-DryRun` y real; nada escrito; el mensaje nombra el motivo | T3 |
| 15 | Configuración con BOM y CRLF; `{}` | Válida; `{}` es nivel 5 | T3 |
| 16 | Configuración que es carpeta, punto de reanálisis (se salta si no se puede crear) o está bloqueada | Exit 1; no se trata como ausente | T3 |
| 17 | Clave `level` repetida | Se fija el comportamiento real de 5.1 (exit 1 o gana la última) y se documenta | T3 |
| 18 | El archivo de configuración no se toca | Bytes y mtime iguales tras una instalación real y con `-Force`; no aparece en el respaldo | T3 |
| 19 | Mensajes de error de configuración | Sin contenido del archivo ni texto interno de PowerShell; claves no ASCII escapadas | T3 |
| 20 | Instalación limpia en los niveles 1 a 4 | Cada archivo = `render_expected`; los fijos = origen; estado con `written` y `level` | T4 |
| 21 | Sólo cambian `model:` y `effort:` | Diferencia línea a línea; `hooks:` de `sentinel` y cuerpo intactos; LF y salto final | T4 |
| 22 | Origen con CRLF | Mismo resultado que con LF | T4 |
| 23 | `effort:` ya presente | Sustituido si la celda trae valor; conservado si es `-` | T4 |
| 24 | Frontmatter defectuoso: sin `model:`, `model:` duplicado, `effort:` duplicado, sin cierre, primera línea distinta de `---`, BOM | Exit 1 en ambos modos; nada escrito; el mensaje nombra el archivo | T4 |
| 25 | `model:` indentado y `model:` en el cuerpo | No se tocan | T4 |
| 26 | Celda igual al origen | Bytes idénticos; `IGUAL` sobre una instalación en nivel 5 | T4 |
| 27 | Agente modificable ausente del manifiesto | Sin error | T4 |
| 28 | `-DryRun` en nivel 3 | Líneas `Nivel:` y `Ajuste:`; nada escrito | T4 |
| 29 | Repositorio real como origen, niveles 1 a 4 | 13 archivos; los seis = `render_expected`; los otros seis con el hash del manifiesto | T4 |
| 30 | Verificación posterior en nivel 3 con un archivo alterado (inyectado en el Paso 8) | Exit 4 | T4 |
| 31 | Nivel 5 a 3, 3 a 1 y 3 a 5 | `ACTUALIZAR` sólo donde cambia la celda; el respaldo trae la versión anterior y el estado; al volver a 5, bytes del repositorio | T5 |
| 32 | Edición a mano tras nivel 3, de un modificable y de un fijo | `MODIFICADO`, exit 3, nada escrito; con `-Force`, respaldo y sobrescritura | T5 |
| 33 | Estado `schema` 1, destino intacto, nivel 3 | `ACTUALIZAR`; estado en `schema` 2 | T5 |
| 34 | Cambio de nivel y de origen a la vez | `ACTUALIZAR` | T5 |
| 35 | Estado ilegible: destino ya en nivel 3; destino en nivel 5 | `IGUAL`; `MODIFICADO` | T5 |
| 36 | Hook primero en un cambio de nivel que también actualiza el hook | `Copiado:` empieza por `hooks/agent_guard.py` | T5 |
| 37 | Destino en CRLF con el contenido del nivel | `IGUAL`, no se reescribe | T5 |
| 38 | Cada variable de entorno con nivel 3 | Aviso en stderr con el nombre y sin el valor; en `-DryRun` y real; mismo código de salida | T6 |
| 39 | Variables con nivel 5, y variable vacía con nivel 3 | Sin aviso | T6 |
| 40 | `install.ps1` sigue en ASCII, sin `*`, `&&`, `??` ni datos personales | Pruebas estáticas existentes | T1 a T6 |

## 4. Tareas

Todas secuenciales: T1 a T6 tocan `install.ps1` y T2 a T6 `tests/test_install.py`. No hay tasks
paralelizables. Reglas para todas:

- Primero la prueba que falla, después la implementación. Python con `-B`.
- Ningún agente lanza `install.ps1` sin `-Target` a una carpeta temporal ni toca `~/.claude`.
- `install.ps1` en ASCII sin BOM; mensajes sin acentos; los `# Paso N:` no se mueven.
- Ciclo por task: `forge` y después `auditor`. Donde se indica, también `shield`.
- Al cerrar cada task, el mismo commit actualiza «Línea de tiempo y avance» del README con la
  aritmética de 4.5. Commits sin etiquetas de coautoría.

Tamaños: S (hasta medio día de `forge`), M (uno o dos archivos con lógica nueva), L (lógica
nueva más adaptación amplia de pruebas).

### Paso previo (sesión principal; no cuenta como unidad)

Al aprobar el plan y la tabla: en el README, la Fase 3 pasa de «sin desglosar» a «0 de 8» y se
crea «La Fase 3 por frentes». El avance global sigue en 40 %. Este plan pasa a «aprobado» y la
tabla de 3.2 pierde la marca de pendiente.

### G1. Compuerta: verificación en Claude Code real (propietario; no cuenta como unidad)

- En un proyecto de pruebas, crear `.claude/agents/zz-nivel-prueba.md` (agente de proyecto: no
  toca `~/.claude`) con `model: opus` y `effort: medium`. Comprobar con `claude --debug` que
  `effort` no sale como campo no reconocido y delegarle una tarea trivial. Repetir con `sonnet`
  y `haiku`. Anotar la versión de Claude Code.
- Opcional: consulta a `scout` sobre la versión mínima que admite `effort:` en subagentes, para
  escribirla en «Requisitos» del README.
- Resultado: se anota en una sección «Resultado de G1» de este plan.
- **Bloquea T4.** T1 a T3 pueden avanzar antes. Si el supuesto 2 es falso, el plan vuelve a
  `atlas`: las alternativas son exigir una versión mínima o reducir los niveles a sólo modelo.

### Fase A: tabla y estado

#### T1. Tabla de niveles y pruebas estáticas — tamaño S

- **Objetivo:** la tabla de 3.2 como datos en `install.ps1` y documentada en el README, con las
  pruebas que las mantienen iguales.
- **Archivos:** modificar `install.ps1`, `README.md`; crear `tests/levels_ref.py`,
  `tests/test_levels.py`.
- **Pasos:** `tests/levels_ref.py` con el lector de `$LevelRows` (normaliza CRLF antes de usar
  anclas de fin de línea), el lector de la tabla del README entre marcadores y
  `render_expected`. En `install.ps1`: `$LevelAgents`, `$AllowedModels`, `$AllowedEfforts`,
  `$LevelRows` y la validación de la tabla al arrancar. En el README: sección «Niveles» mínima
  con la tabla entre marcadores (el resto del texto lo escribe T7). La tabla aún no se usa.
- **Pruebas:** casos 1 a 5 y 40.
- **Aceptación:** la suite pasa; la instalación se comporta igual que antes (ninguna prueba
  existente cambia); cambiar una celda en uno solo de los dos sitios hace fallar el caso 1.
- **Dependencias:** aprobación del plan y de la tabla (P1).
- **Revisa:** `auditor`.

#### T2. Estado con esquema 2 y migración — tamaño L — revisión de seguridad

- **Objetivo:** el instalador escribe el estado de 3.4 y lee los dos esquemas. El nivel es
  siempre 5 en esta task.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`, `tests/levels_ref.py`.
- **Pasos:** `state_for` en el auxiliar; `Read-State` (esquemas 1 y 2); generador de los bytes
  del estado con `StringBuilder`; clasificación con `written` del estado previo (3.5);
  `preinstall()` y `write_state()` según 3.9; sustituir las seis aserciones de igualdad con el
  manifiesto por `assert_state`; actualizar la ayuda `.DESCRIPTION` del script.
- **Pruebas:** casos 6 a 11; toda la suite existente.
- **Aceptación:** la suite pasa; los bytes de los doce destinos no cambian respecto de antes;
  `Read-Manifest` sigue exigiendo `schema` 1 para `install-manifest.json`; `tools/build_manifest.py`
  y `tests/test_manifest.py` sin tocar; un estado no reconocido nunca produce `ACTUALIZAR`.
- **Dependencias:** T1.
- **Revisa:** `auditor`. `shield` en el cierre.

### Fase B: configuración y renderizado

#### T3. Lectura y validación de `synclayer-config.json` — tamaño M — revisión de seguridad

- **Objetivo:** leer el nivel según 3.1 y mostrarlo (3.7), sin aplicarlo todavía.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** bloque `# Configuracion:` entre el Paso 2 y el Paso 3; comprobación de punto de
  reanálisis, carpeta, tamaño y lectura única; validación de raíz, claves y `level`; línea
  `Nivel:`; el nivel leído se guarda en el estado. **Guarda temporal:** un nivel 1 a 4 válido
  termina con exit 1 y `error: el nivel N aun no se puede aplicar en esta version.`; T4 la
  retira junto con su prueba. Así ningún commit acepta un nivel que no aplica.
- **Pruebas:** casos 12 a 19; una prueba de la guarda temporal.
- **Aceptación:** la suite pasa; ningún valor de la configuración llega a un archivo del destino
  salvo el entero validado; ningún camino de error escribe; el archivo de configuración no se
  abre para escritura en ningún punto del script.
- **Dependencias:** T2.
- **Revisa:** `auditor` y `shield`.

#### T4. Renderizado y aplicación de los niveles 1 a 4 — tamaño L — revisión de seguridad

- **Objetivo:** el algoritmo de 3.3 y su uso en clasificación, copia y verificación.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** función de renderizado pura; bloque `# Nivel:` que calcula `outBytes` y `outHash`;
  clasificación, Paso 7 y Paso 8 contra `outHash`; el Paso 7 escribe `outBytes` (actualizar el
  ancla de `patch_script`, 3.6); líneas `Ajuste:`; retirar la guarda temporal de T3; fixture
  `LEVEL_SAMPLE`; variantes del caso 18.
- **Pruebas:** casos 20 a 30.
- **Aceptación:** la suite pasa; en los niveles 1 a 4 los bytes de `auditor`, `shield`,
  `debugger`, el hook, las reglas y la guía son los del origen; todo valor escrito en `model:` o
  `effort:` sale de `$LevelRows`; en el nivel 5 no se llama al renderizado.
- **Dependencias:** T3 y G1.
- **Revisa:** `auditor` y `shield`.

#### T5. Cambios de nivel, ediciones a mano y `-Force` — tamaño M — revisión de seguridad

- **Objetivo:** demostrar con pruebas la tabla de situaciones de 3.5 y cerrar lo que falle.
- **Archivos:** modificar `tests/test_install.py`, `install.ps1`.
- **Pasos:** pruebas de transición; frase añadida al mensaje de exit 3 (3.7); línea
  `Nivel anterior:`; corregir lo que las pruebas destapen.
- **Pruebas:** casos 31 a 37.
- **Aceptación:** la suite pasa; cada fila de «situaciones» de 3.5 tiene una prueba; ningún
  cambio de nivel produce `MODIFICADO` sobre un destino intacto con estado válido; ninguna
  edición a mano se sobrescribe sin `-Force`.
- **Dependencias:** T4.
- **Revisa:** `auditor`. `shield` en el cierre.

### Fase C: avisos

#### T6. Avisos de variables de entorno — tamaño S — revisión de seguridad

- **Objetivo:** los avisos de 3.8.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** `run_install` quita las dos variables del entorno heredado; lectura con
  `[System.Environment]::GetEnvironmentVariable`; avisos antes de la salida de `-DryRun`.
- **Pruebas:** casos 38 y 39.
- **Aceptación:** la suite pasa; el valor de las variables no aparece en stdout ni en stderr;
  el instalador no define, cambia ni borra variables.
- **Dependencias:** T5.
- **Revisa:** `auditor` y `shield`.

### Fase D: documentación y cierre

#### T7. Documentación — tamaño M

- **Objetivo:** documentación al día en el mismo cambio. La escribe `scribe`; la sesión
  principal regenera el manifiesto y corre la suite.
- **Archivos:** modificar `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`,
  `rules/agentes.md`, `install-manifest.json`,
  `docs/plans/2026-11-19-backlog-configuracion-y-reportes.md`.
- **Pasos:**
  - `README.md`: sección «Niveles» completa (cómo crear el archivo, `-DryRun`, reinstalar; la
    tabla entre marcadores; los tres agentes fijos; aviso: bajar el nivel cambia la calidad
    esperada y el ahorro no está medido; los límites de la tabla de 3.2; qué anula el nivel:
    las dos variables, el bloque `env` de `settings.json`, un agente de proyecto homónimo,
    `maxEffortLevel`, `availableModels`); «Instalación» (pasos 3, 4, 8 y 9, tabla de estados,
    códigos de salida, «qué no hace»: no crea ni edita la configuración); «Catálogo» (los
    modelos son los del nivel 5); «Límites del instalador» (los bytes renderizados no los cubre
    el hash del manifiesto y `install.ps1` no está en él; estado `schema` 2 ilegible para un
    instalador anterior; respaldo en la primera reinstalación; clave repetida; el entorno del
    instalador no es el de Claude Code; la configuración vive en cada `-Target`); «Estructura»
    y «Pruebas» (conteos de la salida real).
  - `CLAUDE.md`: arquitectura (configuración, estado `schema` 2), convenciones (`$LevelRows` y
    los marcadores del README son contrato con `tests/test_levels.py`; los marcadores
    `# Configuracion:` y `# Nivel:`), no obvios (nivel 5 = repositorio; `agents_data.py` sigue
    en nivel 5; la configuración ilegible falla y el estado ilegible se trata como ausente). La
    nota sobre reiniciar sesiones no se toca (V1).
  - `HISTORY.md`, `[Sin publicar]`: «Añadido (niveles, Fase 3)».
  - `docs/agentes.md`: «Cambiar el modelo de un agente» (preferir el nivel; una edición a mano
    sale `MODIFICADO`), fila de `synclayer-config.json` en la tabla de archivos,
    `CLAUDE_CODE_EFFORT_LEVEL` en las variables de entorno.
  - `rules/agentes.md`: una línea bajo el catálogo: la columna de modelo es la del nivel 5 (ver P6).
  - Regenerar el manifiesto: `python -B tools/build_manifest.py`.
  - Backlog: estado de la Fase 3.
- **Pruebas:** suite completa.
- **Aceptación:** la suite pasa, incluidas la sincronía del manifiesto y el caso 1; ningún
  documento promete ahorro; siguen siendo doce archivos gestionados; nada personal.
- **Dependencias:** T6.
- **Revisa:** `auditor`.

#### Cierre (lo coordina la sesión principal; cuenta como una unidad)

- **C1. `sentinel`:** suite completa con la salida a la vista; los 40 casos de 3.9 cubiertos.
- **C2. `shield`:** T2 a T6. Aplica: archivo de configuración como entrada, lectura de entorno,
  escritura de agentes transformados en `~/.claude`. Focos: que sólo el entero validado influya
  en lo escrito; que ningún nivel alcance a `auditor`, `shield`, `debugger` ni al bloque
  `hooks:` de `sentinel`; que un origen manipulado no haga al renderizado quitar `hooks:`;
  estado manipulado que convierta una edición en `ACTUALIZAR`; enlaces y carrera sobre la
  configuración; tamaño; fuga de contenido o de valores de entorno en mensajes.
- **C3. `auditor`** sobre el cambio completo.
- **C4.** Memoria del proyecto actualizada por la sesión principal.
- **V1. Recarga en caliente (propietario; fuera del conteo):** con una sesión abierta, instalar
  un cambio de nivel y delegar sin reiniciar; mirar el modelo real con
  `python -B tools/usage_report.py project --stdout` (sección «Modelo real»). Sólo si se
  confirma, una task aparte cambia la nota de `CLAUDE.md`, el README y el recordatorio de
  `install.ps1` (con su prueba). Hasta entonces el texto no cambia.
- **V2. Instalación real (propietario; fuera del conteo):** `-DryRun` y ejecución real sobre
  `~/.claude` en nivel 5, y un cambio de ida y vuelta a otro nivel.

### 4.5 Unidades y aritmética de la línea de tiempo

La Fase 3 tiene **8 unidades**: T1 a T7 y el cierre. El paso previo, G1, V1 y V2 no cuentan.

| Frente | Unidades |
|---|---|
| Tabla y estado | 2 (T1, T2) |
| Configuración y renderizado | 3 (T3, T4, T5) |
| Avisos | 1 (T6) |
| Documentación y cierre | 2 (T7, cierre) |

Con k unidades cerradas: Fase 3 = k ÷ 8. Proyecto completo = (200 + 100 × k ÷ 8) ÷ 5 =
40 + 2,5 × k. Fases 1 y 2 al 100 %; fases 3 a 5 con el mismo peso. Un cuadro = 10 %; la mitad
exacta redondea hacia arriba, y el porcentaje mostrado también.

| k | Fase 3 | Mostrado | Cuadros | Global | Mostrado | Cuadros |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 0 % | 0 % | 0 | 40 % | 40 % | 4 |
| 1 | 12,5 % | 13 % | 1 | 42,5 % | 43 % | 4 |
| 2 | 25 % | 25 % | 3 | 45 % | 45 % | 5 |
| 3 | 37,5 % | 38 % | 4 | 47,5 % | 48 % | 5 |
| 4 | 50 % | 50 % | 5 | 50 % | 50 % | 5 |
| 5 | 62,5 % | 63 % | 6 | 52,5 % | 53 % | 5 |
| 6 | 75 % | 75 % | 8 | 55 % | 55 % | 6 |
| 7 | 87,5 % | 88 % | 9 | 57,5 % | 58 % | 6 |
| 8 | 100 % | 100 % | 10 | 60 % | 60 % | 6 |

Si G1 obliga a rehacer el plan o se añade la task de V1, las unidades cambian y se recalcula
con la misma fórmula.

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| La versión instalada de Claude Code no reconoce `effort:` | Compuerta G1 antes de T4; el README pide comprobarlo con `claude --debug` |
| Un nivel bajo debilita las revisiones | `auditor`, `shield` y `debugger` fuera de `$LevelAgents`; casos 2, 20 y 29; foco de `shield` |
| El renderizado altera algo más que `model:` y `effort:` (por ejemplo `hooks:` de `sentinel`) | Autocomprobación del paso 9 de 3.3; renderizador de referencia independiente; casos 5, 21 y 29 |
| Los bytes renderizados no están cubiertos por el hash del manifiesto | Parten de bytes verificados; valores de lista cerrada; se verifica contra `outHash`; documentado en «Límites del instalador» |
| Las tablas de `install.ps1` y del README se separan | Caso 1 |
| El estado nuevo rompe pruebas existentes | T2 aislada en nivel 5; `preinstall()` en `schema` 2; `assert_state` |
| El estado de PowerShell no coincide byte a byte con el de Python | Caso 6; formato fijado en 3.4 |
| Un instalador anterior no lee el estado `schema` 2 | Lo trata como ausente (`MODIFICADO`, exit 3, nunca sobrescribe sin `-Force`); documentado |
| Primera reinstalación crea un respaldo sólo con el estado | Aceptado y documentado |
| El usuario edita `model:` a mano (lo decía `docs/agentes.md`) | Sale `MODIFICADO`; el mensaje de exit 3 remite a la configuración; T7 corrige la guía |
| Variables de entorno, agente de proyecto o políticas gestionadas anulan el nivel | Avisos de 3.8 para lo visible; README para el resto |
| Un `effort:` explícito sube el esfuerzo respecto de una sesión en `low` | Documentado como límite de la tabla |
| Alguien lee los niveles como ahorro garantizado | Aviso en el README; ningún mensaje del instalador habla de ahorro |
| Los alias cambian de versión | Documentado; `atlas` en nivel 5 sigue con el id fijo |
| Clave `level` repetida con comportamiento no documentado en 5.1 | Caso 17 fija el comportamiento; documentado |
| La suite se alarga (hoy unos 4 minutos) | `subTest` donde se comparte preparación; pruebas sin PowerShell en `test_levels.py` |
| Las pruebas heredan las variables de entorno de la sesión que las corre | `run_install` las quita por defecto |
| Etiquetas de delegación («Atlas (Fable)») desfasadas con otro nivel | Nota en `rules/agentes.md` y `docs/agentes.md` (P6) |
| Un agente instala contra el `~/.claude` real | Regla en todos los prompts; `-Target` siempre explícito en las pruebas |
| pwsh 7 sin verificar | Sigue como «no verificado»; las clases de pwsh se saltan |

## 6. Preguntas abiertas

Cada una tiene un valor por defecto, que es lo que el plan implementa si no hay respuesta.

- **P1. Tabla de 3.2.** Por defecto: la propuesta. Alternativa: la hipótesis 5.4 de la
  exploración, que incumple R3 (`haiku` con `low` en `oracle`, `scout` y `scribe`).
- **P2. `oracle`.** Por defecto: igual en los cinco niveles. Alternativa: `haiku`, `medium` en
  el nivel 1 (puede subir o bajar el esfuerzo según el de la sesión).
- **P3. `scribe` en el nivel 1.** Por defecto: `haiku`, `medium`. Alternativa: `sonnet`, `low`
  (ningún agente cambia a Haiku).
- **P4. Configuración sin `level` (`{}`).** Por defecto: válida, nivel 5 (la Fase 4 podrá traer
  sólo alias). Alternativa: exit 1.
- **P5. Avisos de entorno.** Por defecto: sólo con nivel 1 a 4, en `-DryRun` y en ejecución
  real. Alternativa: siempre, también en nivel 5 (añade una línea a quien no configuró nada).
- **P6. `rules/agentes.md`.** Por defecto: una línea que dice que la columna de modelo es la
  del nivel 5. Alternativa: no tocar las reglas.
- **P7. Línea `Nivel:` sin configuración.** Por defecto: se imprime siempre
  (`Nivel: 5 (por defecto...)`), para que la opción se descubra. Alternativa: sólo si existe el
  archivo.
- **P8. Versión mínima de Claude Code.** Por defecto: el README pide comprobar `effort:` con
  `claude --debug`, sin número. Alternativa: `scout` busca la versión en G1 y se escribe.

## Consulta de `scout` para G1 (2026-11-20, por documentación; no sustituye a G1)

Fuentes: `code.claude.com/docs` (sub-agents, model-config, env-vars, errors) y el changelog; páginas leídas por tramos, algunas sin leer del todo.

- **`effort:` en subagentes está documentado** con los cinco niveles (`low`, `medium`, `high`, `xhigh`, `max`; los disponibles dependen del modelo). El changelog lo da por funcionando: 2.1.267 arregló que se ignorara en subagentes, y 2.1.78 lo añadió para agentes de plugin. No hay entrada «Added» para agentes de usuario. Con 2.1.328 está cubierto en cualquier caso. Parámetro `effort` de la herramienta Agent: 2.1.292. `CLAUDE_CODE_SUBAGENT_EFFORT`: 2.1.316 en el changelog y 2.1.315 en la página de variables (discrepancia menor).
- **Niveles:** Opus 5.5, Sonnet 5.5, Haiku 5.5 y Fable admiten los cinco; Opus 4.6 y Sonnet 4.6 no tienen `xhigh`. Un nivel no soportado baja al más alto soportado igual o inferior (regla documentada para la sesión; aplicarla al agente es inferencia). Sin aviso documentado.
- **NO documentado:** el efecto de un `effort:` inválido (`extreme`, vacío, `Medium`, número) y de un `model:` desconocido en el frontmatter de un agente (sólo hay reglas generales de modelo y de la sesión). Un campo desconocido se ignora y `claude --debug` lo nombra (`does not recognize or apply`, v2.1.296 o posterior). «Invalid `--agents` configuration» sólo aplica a `--agents`, no a los `.md`. Por eso el instalador escribe sólo valores de lista cerrada.
- **Variables:** `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` documenta sólo el valor `1`; que `0` o `false` la dejen inactiva es inferencia por la regla general de booleanas. `CLAUDE_CODE_EFFORT_LEVEL` acepta los cinco niveles, `auto` y `unset`; vacío o sólo espacios no está documentado.
- **Verificar modelo y esfuerzo:** `/tasks` (v2.1.242 o posterior) nombra el modelo y el esfuerzo de cada subagente. `claude --debug` sólo documenta campos no reconocidos y archivos omitidos. `/effort status` es de la sesión, no del subagente.
- **Recarga en caliente (V1):** la página de sub-agents dice que Claude Code vigila `~/.claude/agents/` y `.claude/agents/` y que la siguiente delegación usa la definición nueva «sin reiniciar»; hace falta reiniciar para `.claude/agents/` de directorios añadidos con `--add-dir`. Sin verificar en la práctica.
- **Pista no oficial, no tomarla como hecho:** issues de GitHub (anthropics/claude-code #81677 y #82259) dicen que `claude --agent` ignora el `effort:` del frontmatter, mientras que los subagentes lanzados con la herramienta Agent sí lo respetan. SyncLayer usa subagentes, pero conviene confirmarlo en G1.

### Procedimiento G1 mínimo (propietario)

1. Crear `.claude/agents/zz-nivel-prueba.md` en un proyecto de prueba (no toca `~/.claude`) con `name: zz-nivel-prueba`, una `description`, `model: sonnet` y `effort: low`; en el cuerpo, que responda «ok».
2. Antes de abrir Claude Code, comprobar que `CLAUDE_CODE_EFFORT_LEVEL` y `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` no están definidas: anulan lo que se prueba.
3. Abrir `claude --debug` en ese proyecto.
4. Pedir «Usa el subagente zz-nivel-prueba» y, mientras corre, ejecutar `/tasks`: la fila debe nombrar el modelo (`sonnet`) y el esfuerzo (`low`).
5. En `~/.claude/debug/<session-id>.txt` buscar `does not recognize or apply` y `zz-nivel-prueba`: si no hay línea de campo no reconocido, los campos se leyeron como válidos (conclusión por ausencia).
6. Repetir con `opus` y `haiku`. Repetir con `effort: xhigh` y un modelo 4.6 (debería mostrar `high`), con un `effort:` inválido y con un `model:` inexistente, para cubrir los casos no documentados. Anotar la versión de Claude Code y el resultado en una sección «Resultado de G1» de este plan.
