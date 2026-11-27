# Plan: Fase 6, renombrado de los agentes en el repositorio

Fecha: 2026-11-27. Estado: **propuesto, pendiente de aprobación del propietario** (P1 a P16 con valor por
defecto). Rama propuesta: `feat/renombrado-de-agentes`, creada desde `feat/configuraciones-dinamicas` una vez
cerrada la Fase 5 (o desde `main` si la Fase 5 ya se integró). Este plan no toca código: sólo existe este archivo.

Fuentes: decisión del propietario del 2026-11-23 (tabla de nombres, guardada en la memoria del proyecto) y del
2026-11-27 (los nombres nuevos pasan a ser los de fábrica);
[`2026-11-22-fase4-nombres-configurables.md`](2026-11-22-fase4-nombres-configurables.md) (alias, rol frente a
ruta, estado esquema 3, huérfanos, límite de palabra E1);
[`2026-11-24-fase5-configuraciones-dinamicas.md`](2026-11-24-fase5-configuraciones-dinamicas.md) (formato de
plan, carpeta de planes, catálogo del reporte de uso);
[`2026-11-20-fase3-esfuerzo-configurable.md`](2026-11-20-fase3-esfuerzo-configurable.md) (tabla de niveles);
`CLAUDE.md` del repositorio (contratos con las pruebas) y lectura directa de `install.ps1`, `tests/`,
`tools/usage_report.py` y `assets/brand/src/` el 2026-11-27.

## 1. Objetivo

Los nueve agentes de SyncLayer cambian de nombre **en el repositorio**. Los nombres nuevos son los que instala
cualquiera sin configurar nada: archivos de `agents/`, `name:`, textos, reglas, guía, manifiesto, tablas del
instalador, pruebas, datos de marca y documentación.

| Nombre actual | Nombre nuevo | Capitalizada | MAYÚSCULAS | Guarda (`hooks:`) | En `$LevelAgents` |
|---|---|---|---|---|---|
| `atlas` | `atlas` (sin cambio) | Atlas | ATLAS | no | sí |
| `oracle` | `heimdall` | Heimdall | HEIMDALL | no | sí |
| `scout` | `hermes` | Hermes | HERMES | no | sí |
| `forge` | `sindri` | Sindri | SINDRI | no | sí |
| `sentinel` | `anubis` | Anubis | ANUBIS | `tests-only` | sí |
| `auditor` | `salomon` | Salomon | SALOMON | `readonly --allow-temp` | no (fijo) |
| `shield` | `hector` | Hector | HECTOR | `readonly --allow-temp` | no (fijo) |
| `debugger` | `sherlock` | Sherlock | SHERLOCK | `readonly --allow-temp` | no (fijo) |
| `scribe` | `shakespeare` | Shakespeare | SHAKESPEARE | no | sí |

`salomon` y `hector` van **sin tilde en todas partes** (nombre, prosa, tablas): el alias y el nombre de archivo
sólo admiten `[a-z0-9_-]` y la transformación de alias trabaja con tres formas ASCII.

En este documento, «nombre viejo» es la primera columna y «nombre nuevo» la segunda. Las tareas las ejecutan
los agentes instalados hoy en `~/.claude` (con sus nombres viejos: `forge`, `auditor`, `shield`, `sentinel`,
`scribe`): el repositorio cambia, la copia viva no, hasta que el propietario reinstale (V2).

### Decisiones ya tomadas (propietario; no se reabren)

1. La tabla de arriba. Las opciones descartadas quedan en la memoria del proyecto.
2. Los nombres nuevos son los de fábrica en `agents/`, documentación, pruebas, manifiesto e instalador.
3. Nada del plan toca `~/.claude`. Lo que haya que cambiar allí lo hace el propietario con una lista que
   entrega el cierre (4, «V2»).
4. El efecto en un Claude Code real no se da por probado (G1/V1).

### 1.1 Dentro de alcance

- `agents/`: ocho archivos renombrados (`git mv`) y los nueve con el texto nuevo. `rules/agentes.md`,
  `docs/agentes.md`. `install-manifest.json` regenerado.
- `install.ps1`: `$AliasRoles`, `$LevelAgents`, `$LevelRows`, comentarios y ayuda; tabla nueva de nombres
  anteriores (`$LegacyRoles`) con dos usos acotados (3.3).
- `tools/usage_report.py`: `SYNCLAYER_AGENTS` y lista cerrada de nombres anteriores (3.5).
- `assets/brand/src/agents_data.py`, `assets/brand/src/build_round3.py` (espécimen) y los SVG regenerados.
- Pruebas: `tests/names.py`, `tests/rename_ref.py`, `tests/test_rename.py`, `tests/test_phase6_docs.py`
  (nuevos) y adaptación de las existentes.
- Documentación: `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`, `docs/brand/voice-and-tone.md`,
  `docs/brand/claude-design-handoff.md`, backlog, línea de tiempo.

### 1.2 Fuera de alcance

- `~/.claude` (agentes vivos, `rules/agentes.md` vivo, `CLAUDE.md` global, `settings.json`, memoria): sólo se
  avisa (3.6).
- `hooks/agent_guard.py`: no nombra ningún agente (comprobado: cero apariciones). No cambia, su hash tampoco.
- Los bloques `hooks:` y las líneas `tools:`, `model:` y `color:` de los agentes: byte a byte.
- Un esquema nuevo del estado. Borrar, mover o respaldar los archivos con el nombre viejo en el destino.
- Reescribir la historia: `HISTORY.md` (entradas pasadas), `docs/plans/` anteriores, hitos cerrados de la
  línea de tiempo y comentarios históricos de las pruebas (P7).
- Cambiar las celdas de la tabla de niveles (sólo cambia el nombre de la fila), `$ReservedAliases`,
  `$YamlWords`, `$AllowedPattern`, la carpeta de planes o el catálogo de textos del reporte de uso.
- La tarea pendiente de `Get-Prop` (P11 de la Fase 4).

## 2. Supuestos

Los marcados **[G1]** los comprueba el propietario y no se documentan como hechos. Los marcados **[T1]** los
confirma la primera tarea antes de seguir; si alguno falla, T1 se detiene y vuelve a la sesión principal.

1. Windows PowerShell 5.1; `install.ps1` en ASCII sin BOM y sin asterisco; mensajes en español sin acentos.
   Python 3.12 con `-B`, sólo biblioteca estándar. Sin pwsh. La suite tarda entre 43 y 70 minutos.
2. La Fase 5 está cerrada antes de empezar (cierre con `sentinel`, `shield` y `auditor`). Si no lo está, la
   aritmética de 4.7 cambia (ver allí).
3. Los ocho nombres nuevos pasan V1 a V4 como alias con las listas actuales (lo validó `validate_table` el
   2026-11-23 según la memoria del proyecto). **[T1]** se vuelve a comprobar con una prueba.
4. **[T1]** Ninguno de los ocho nombres nuevos aparece hoy, en ninguna capitalización ni como subcadena, en
   los doce archivos gestionados, en `install.ps1`, en `tools/` ni en `tests/` (búsqueda del 2026-11-27 fuera
   de `docs/plans/`: cero resultados). Así el cambio no es ambiguo.
5. **[T1]** `tools/build_manifest.py` ordena las rutas; el orden de filas de la salida del instalador sigue
   ese orden y cambiará (`agents/anubis.md` primero).
6. **[T1]** `levels_ref.read_ps_list` lee una lista vacía `@()`. Si no, T5 usa otra forma de dato (4, T5).
7. **[T1]** Ninguna prueba compara los SVG de `assets/brand/` con `agents_data.py` (sólo
   `tests/test_brand_agents.py`, que compara los datos con el frontmatter).
8. El texto nuevo de los once archivos de texto gestionados es, byte a byte, el que produce hoy la
   transformación de alias de la Fase 4 con la tabla del propietario (3.2). Esa transformación ya tiene
   referencia independiente (`tests/aliases_ref.py`) y está probada contra el instalador (casos 41 a 45).
9. En el repositorio no hay carpeta `.claude/` con agentes de proyecto (comprobado el 2026-11-27).
10. Ningún agente ejecuta el instalador sin `-Target` y `HOME` temporales, ni el reporte de uso sin
    `--claude-dir` temporal.
11. Los generadores de marca necesitan `fontTools`, `uharfbuzz` y las cinco fuentes IBM Plex, que no se
    versionan: T10 necesita que el propietario indique la carpeta de fuentes (P10).
12. **[G1]** Claude Code delega por `name:` y por la `description:`. Los nombres nuevos describen menos el
    oficio que los viejos (`forge`, `auditor`, `debugger`); las descripciones conservan el oficio («SINDRI,
    senior developer…»). Si la delegación automática empeora o no, no lo puede probar la suite.
13. **[G1]** Con los archivos viejos y nuevos a la vez en `~/.claude/agents/` hay hasta 17 agentes, ocho pares
    con descripciones casi iguales. Qué elige Claude Code no está documentado.

## 3. Diseño

### 3.1 Qué es el rol tras el renombrado

El rol es el id estable interno del instalador: clave de manifiesto, de `$LevelRows`, de `aliases` y del
`path` del estado (Fase 4).

| Opción | A favor | En contra |
|---|---|---|
| A. Los nombres nuevos pasan a ser los roles | Una sola verdad: archivo, `name:`, manifiesto, tablas y docs dicen lo mismo. El nivel 5 sigue siendo «el repositorio tal cual». Sin alias efectivo, el estado sigue en esquema 2 y la copia inversa `~/.claude` a repo sigue valiendo. El mecanismo de alias no cambia. Es lo que pidió el propietario (nombres nuevos en `agents/` y en el manifiesto) | Toca casi todas las pruebas (unas 900 apariciones). Quien ya instaló ve ocho huérfanos; quien configuró `aliases` con claves viejas recibe un error |
| B. Rol viejo como id interno y nombres nuevos como alias por defecto (`$DefaultAliases`) | Poco cambio en datos; el huérfano por cambio de nombre y las claves viejas de `aliases` funcionan sin código nuevo | Contradice la decisión 2: `agents/` y el manifiesto seguirían con los nombres viejos. Toda instalación tendría alias efectivo: estado en esquema 3 siempre, nivel 5 distinto del repositorio, copia inversa inválida por defecto, y dejan de valer las regresiones «sin alias la salida es idéntica» (`F4T6_GOLDEN`, 14 escenarios). El repositorio diría `forge` y la instalación `sindri`: dos vocabularios para siempre. El reporte de uso vería alias (`(otro agente)`) |
| **C. A más una tabla cerrada de nombres anteriores** | Todo lo de A. La compatibilidad se resuelve con datos (`$LegacyRoles`, ocho pares) y dos usos pequeños: mejor aviso de huérfano y mensaje claro para una clave vieja. Reutiliza `RenamedTo` de la Fase 4 | El costo de pruebas de A, más una tarea de instalador con revisión de seguridad |

Se elige **C** (P1). El costo de pruebas se paga una vez y se reduce parametrizando las pruebas antes del
cambio (3.7). B es más barata hoy y más cara cada día siguiente, y no cumple lo decidido.

Consecuencias de C:

- `$AliasRoles` = los nueve nombres nuevos, en orden alfabético (P9), porque el caso 1 de
  `tests/test_aliases.py` lo compara con el listado ordenado de `agents/`:
  `anubis`, `atlas`, `hector`, `heimdall`, `hermes`, `salomon`, `shakespeare`, `sherlock`, `sindri`.
  El orden de las líneas `Alias:` y del «primer problema» de la validación sigue ese orden.
- Las claves de `aliases` son los nombres nuevos. El mecanismo de alias, sus reglas V1 a V8, la carpeta de
  planes (L5 usa `$AliasRoles`) y el estado no cambian de lógica.
- `$LevelAgents = @('atlas', 'sindri', 'anubis', 'shakespeare', 'hermes', 'heimdall')` y las 24 filas de
  `$LevelRows` con el nombre nuevo y **las mismas celdas**. La tabla del README entre los marcadores de
  niveles cambia igual, en el mismo commit. `salomon`, `hector` y `sherlock` quedan fijos.

### 3.2 Cómo se produce el texto nuevo de los archivos gestionados

No se edita a mano. El texto nuevo de los nueve agentes, de `rules/agentes.md` y de `docs/agentes.md` es la
salida de la transformación de alias con la tabla del propietario sobre el texto actual:

- Agentes: `aliases_ref.transform_agent(bytes, rol, TABLA)`: cambia `name:`, la línea `description:` y el
  cuerpo, con límite de palabra E1 y tres formas. Frontmatter restante y `hooks:` intactos, por la
  autocomprobación.
- Reglas y guía: `aliases_ref.transform_doc(bytes, TABLA)`.
- Equivale a instalar el repositorio actual en una carpeta temporal con esos ocho alias en el nivel 5 y copiar
  el resultado (`agents/<nuevo>.md`).

Esto da un criterio objetivo para la tarea del cambio: T1 guarda los once hashes canónicos esperados en un
fixture (`tests/rename_expected.json`, **prueba puente**), y tras el cambio los archivos del repositorio deben
tener esos hashes. La prueba puente vive de T1 a T7 y se retira en T8, que es la primera tarea que edita la
guía. Entre T1 y T7 nadie edita los once textos.

Lo que la transformación no cubre y se hace a mano después (T8, T9): prosa que explica los nombres (por
ejemplo el párrafo del README sobre `scribe` como subcadena de «escribe»), ejemplos de configuración y todo
archivo no gestionado.

### 3.3 Compatibilidad en el instalador

Dato nuevo, junto a `$AliasRoles` (una definición por línea, contrato con las pruebas):

```powershell
$LegacyRoles = @('oracle|heimdall', 'scout|hermes', 'forge|sindri', 'sentinel|anubis', 'auditor|salomon', 'shield|hector', 'debugger|sherlock', 'scribe|shakespeare')
```

Antes del cambio (T5) la lista está vacía y el mecanismo no hace nada; el cambio (T7) la llena. Función pura
`Get-LegacyTableProblem`, evaluada al arrancar como `Get-LevelTableProblem`: formato `viejo|nuevo`, ambos
`[a-z][a-z0-9_-]{0,63}`, viejos únicos, ningún viejo en `$AliasRoles`, todo nuevo en `$AliasRoles`.

**Uso 1: quien ya instaló los nombres viejos.** Situación sin código nuevo: el estado previo (esquema 2 o 3)
trae `agents/forge.md`, que ya no está en el manifiesto; `Read-State` lo acepta (`$AllowedPattern` admite
cualquier `agents/<nombre>.md`) y sale como `HUERFANO` clásico, con la nota de stdout y **sin** el aviso de
que hay dos agentes activos. Cambio: en el bucle de huérfanos, si la ruta previa no es un rol actual y es
`agents/<viejo>.md` con `<viejo>` en `$LegacyRoles`, `RenamedTo` = `$destRel['agents/<nuevo>.md']`. Con eso
sale el aviso existente de la Fase 4 por stderr, uno por archivo y sólo si el archivo existe:
`aviso: agents/forge.md es el nombre anterior de agents/sindri.md y sigue en el destino: no se borra…`.

| Situación al reinstalar sobre una instalación con nombres viejos | Resultado esperado |
|---|---|
| Estado esquema 2, archivos intactos, sin `aliases` | 8 `NUEVO` (`agents/<nuevo>.md`); `agents/atlas.md`, `rules/agentes.md` y `docs/agentes.md` `ACTUALIZAR` (respaldo); hook `IGUAL`; 8 `HUERFANO` con aviso por stderr; sin la nota de huérfano clásico; estado reescrito en esquema 2 con las rutas nuevas y el anterior al respaldo |
| Estado esquema 3 (había alias `forge` a `dev`) y `aliases` ya corregido a `sindri` a `dev` | `agents/dev.md` `ACTUALIZAR`; sin huérfano para ese rol |
| Estado esquema 3 y sin `aliases` ahora | `agents/dev.md` `HUERFANO` con aviso («nombre anterior de `agents/sindri.md`») |
| `aliases` con los nombres viejos como alias (`"sindri": "forge"`, P3) | `agents/forge.md` es destino actual: `ACTUALIZAR` o `IGUAL`, sin huérfano |
| El usuario tiene un agente propio `agents/hermes.md` | `MODIFICADO`, exit 3, nada escrito (comportamiento actual). Se documenta |
| Estado ausente o ilegible | Nunca `ACTUALIZAR`; ningún huérfano (no hay de dónde saberlo): los ocho archivos viejos quedan sin aviso. Se documenta: quitarlos a mano |
| Segunda corrida | Todo `IGUAL`; los huérfanos ya no se informan (el estado nuevo no los trae). Comportamiento actual, documentado |

El instalador sigue sin abrir, respaldar ni borrar el archivo viejo (P4). No cambia el exit code.

**Uso 2: quien configuró `aliases` con claves viejas.** Hoy daría `rol desconocido en aliases: forge`. Cambio en
`Get-AliasTableProblem`, antes de ese mensaje: si la clave es un nombre viejo de `$LegacyRoles`, el motivo es
`el rol forge ahora se llama sindri: cambia la clave en aliases`. Los dos nombres salen de la lista cerrada,
nunca del archivo; exit 1 antes de escribir, también con `-DryRun` (P2). No se aceptan claves viejas como
sinónimo: dos claves para un mismo rol obligarían a definir cuál gana.

**Nombres viejos como alias (P3).** Se permiten: `$LegacyRoles` no entra en V5 ni en V7. Es la forma soportada
de conservar los nombres viejos, y el README trae la tabla lista para copiar:

```json
{ "aliases": { "heimdall": "oracle", "hermes": "scout", "sindri": "forge", "anubis": "sentinel", "salomon": "auditor", "hector": "shield", "sherlock": "debugger", "shakespeare": "scribe" } }
```

Con esa tabla el estado pasa a esquema 3 y los archivos existentes salen `ACTUALIZAR` si están intactos.

Sin cambios: esquema del estado, `Read-State`, `ConvertTo-StateBytes`, `ConvertTo-AliasBytes`,
`ConvertTo-PlansBytes`, `ConvertTo-LevelBytes`, los diez `# Paso N:`, `# Configuracion:`, la única línea
`# Alias:`, `# Planes:`, `# Nivel:` y el resto de anclas de `patch_script`.

### 3.4 Colisiones y límite de palabra

- **V1 a V4 sobre los nombres nuevos.** Los ocho casan `^[a-z][a-z0-9_-]{0,63}\z` (de 6 a 11 caracteres), no
  son palabras YAML, ni nombres de dispositivo de Windows, ni están en `$ReservedAliases` (`explore`, `plan`,
  `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide`, `web-fetch`, `fork`,
  `output-style-setup`). Son distintos entre sí, también sin distinguir mayúsculas (NTFS). T1 lo fija con una
  prueba. `hermes` y `sherlock` no coinciden con ningún integrado conocido; si Claude Code añade un integrado
  con uno de estos nombres, hay que cambiarlo (riesgo, G1).
- **V5 y V7 después del cambio.** Un alias ya no puede ser ni contener (partido por `-`) un nombre nuevo:
  `sherlock-2` se rechaza. Los nombres viejos dejan de estar prohibidos (P3). L5 de `plans_dir`: `docs/hermes`
  pasa a rechazarse y `docs/forge` a admitirse.
- **Subcadenas.** El problema de `scribe` dentro de «escribe», «describe», «reescribe» y «sobrescribe»
  desaparece: `scribe` deja de ser rol. Ningún nombre nuevo es subcadena de una palabra de los once textos
  (T1 lo comprueba sobre el texto ya transformado: `inventory(...)` sin palabras sin clasificar y recuento de
  subcadenas igual al de formas). `SCRIBE_WORDS` de `tests/aliases_ref.py` se generaliza a un diccionario por
  rol, vacío tras el cambio; el límite de palabra se sigue probando con palabras sintéticas (`<rol>2`,
  `x_<rol>`, `ñ<rol>`), no con palabras reales del español.
- **Nombres propios.** `Hermes`, `Hector`, `Sherlock` y `Shakespeare` son también nombres de personas, obras
  y productos. Si un texto gestionado los usa en otro sentido, la transformación de alias lo reemplazará
  cuando el usuario ponga un alias. Regla (ya existe para los roles): en `rules/agentes.md` y `docs/agentes.md`
  esos nombres sólo designan al agente; los ejemplos usan `<rol>` y `<alias>`.
- **Tildes.** `Salomón` y `Héctor` con tilde no son ninguna de las tres formas: quedarían sin reemplazar y el
  inventario los daría como «sin clasificar». Regla: siempre sin tilde (P12). T1 y T9 lo vigilan con prueba.
- **Inventario.** `INVENTORY` de `tests/test_aliases.py` cambia de claves (rutas y roles nuevos) y conserva
  los recuentos: la transformación es uno a uno. Los recuentos sólo cambian en T8, al editar la guía.

### 3.5 Reporte de uso

`SYNCLAYER_AGENTS` de `tools/usage_report.py` es una lista cerrada que una prueba compara con `agents/`. Las
transcripciones ya escritas traen `agentType` con los nombres viejos.

| Opción | Efecto |
|---|---|
| Sólo nombres nuevos | El historial anterior al cambio sale como `(otro agente)`: se pierde el desglose de todo lo ya registrado |
| **Nombres nuevos más una lista cerrada de nombres anteriores, cada uno con su fila** | El historial se sigue viendo con el nombre que tenía; lo nuevo, con el nombre nuevo. Sin texto nuevo en el catálogo. Los goldens (`usage_golden_es.json`, `usage_golden_en.json`, que usan `forge` y `scout`) no cambian |
| Fusionar viejo en nuevo | Una fila por agente, pero el reporte mostraría un nombre que la transcripción no trae, y un agente propio del usuario llamado `forge` se sumaría a `sindri` |

Se elige la segunda (P5): `SYNCLAYER_LEGACY_AGENTS` (frozenset, vacío hasta el cambio) y la clasificación mira
la unión; mismo conjunto «SyncLayer». Sin nota nueva en el reporte (P6): un texto nuevo exige las dos lenguas y
regenerar los dos goldens. El README lo explica. Un agente con alias sigue saliendo como `(otro agente)`.

### 3.6 Lo que vive fuera del repositorio

El plan no escribe en `~/.claude`. El cierre entrega al propietario una lista (V2), que el README también
documenta en «Nombres anteriores»:

1. Reinstalar: `-DryRun` primero; se esperan 8 `NUEVO`, 3 `ACTUALIZAR`, 1 `IGUAL` y 8 `HUERFANO` con aviso
   (si `~/.claude` está intacto y con estado válido).
2. Quitar a mano los ocho archivos viejos de `~/.claude/agents/` (o decidir conservar los nombres viejos con
   la tabla de 3.3).
3. `~/.claude/rules/agentes.md` y `~/.claude/docs/agentes.md` se actualizan solos al reinstalar (son
   gestionados).
4. `~/.claude/CLAUDE.md` (global, del propietario): nombra `forge` y `auditor` en «Ejecución de planes» y
   remite a `superpowers`; hay que editarlo a mano. El cierre lista las líneas exactas.
5. Memoria del proyecto (`feedback-agent-labels`: «Forge (Sonnet): …») y cualquier otra memoria que nombre
   agentes.
6. `settings.json` (usuario y proyectos): reglas `Agent(<nombre>)` en `permissions`, `--disallowedTools`,
   matchers de hooks y `--agent <nombre>`.
7. Agentes de proyecto (`.claude/agents/<nombre>.md`) en otros repositorios: el `name:` a igualar pasa a ser
   el nuevo.
8. Reiniciar las sesiones abiertas.

### 3.7 Estrategia de pruebas

El cambio de nombres es atómico por fuerza: las pruebas atan `$AliasRoles` al listado de `agents/`, el
manifiesto a los archivos, `$LevelRows` al README, `agents_data.py` al frontmatter y `SYNCLAYER_AGENTS` al
listado. No se puede renombrar por partes con la suite en verde.

| Opción | A favor | En contra |
|---|---|---|
| **Parametrizar antes (`tests/names.py`) y cambiar después** | Las tareas previas no cambian comportamiento y se revisan con la suite en verde. El commit del cambio toca en pruebas casi sólo datos. Un renombrado futuro cuesta poco | Dos tareas grandes sobre `tests/test_install.py` (476 apariciones) |
| Reemplazo mecánico con script dentro del commit del cambio | Dos unidades menos | Un commit enorme; las expectativas que dependen del orden alfabético y las pruebas de subcadenas hay que rehacerlas a mano dentro del mismo commit |
| Renombrar un agente por tarea | Tareas muy pequeñas | Ocho pasadas por los mismos archivos y ocho corridas de 70 minutos |

Se elige la primera (P8).

`tests/names.py` (nuevo, sin dependencias, **independiente de `install.ps1`**: es la referencia escrita a
mano contra la que se comparan las listas del script):

```python
PLANNER, ANALYST, RESEARCHER, DEVELOPER, QA = "atlas", "oracle", "scout", "forge", "sentinel"
REVIEWER, SECURITY, DEBUGGER, WRITER = "auditor", "shield", "debugger", "scribe"
ROLES = sorted([PLANNER, ANALYST, RESEARCHER, DEVELOPER, QA, REVIEWER, SECURITY, DEBUGGER, WRITER])
LEVEL_ROLES = [PLANNER, DEVELOPER, QA, WRITER, RESEARCHER, ANALYST]
FIXED = [REVIEWER, SECURITY, DEBUGGER]
GUARDED = {QA: "tests-only", REVIEWER: "readonly --allow-temp", SECURITY: "readonly --allow-temp", DEBUGGER: "readonly --allow-temp"}
LEGACY = {}   # nombre anterior -> nombre actual; lo llena el cambio (T7)
```

Reglas de la parametrización (T2 a T4): las pruebas usan las constantes; las expectativas que dependen del
orden se calculan (`sorted`, orden de `names.ROLES`); los textos de muestra se construyen con las constantes
(`"Eres %s." % DEVELOPER.upper()`); los goldens embebidos (`F4T6_GOLDEN`) pasan a plantilla con las rutas
calculadas, conservando byte a byte todo lo demás. Quedan literales, con lista cerrada y comentario: los
goldens del reporte de uso y sus pruebas (nombres anteriores a propósito), comentarios históricos y los
ejemplos de alias de fantasía (`dev`, `amigo-qa`, `redactor`).

Casos (P = PowerShell 5.1; el resto sólo Python):

| # | Caso | Tarea |
|---|---|---|
| 1 | La tabla del renombrado: ocho pares, `atlas` fuera, viejos y nuevos únicos, sin tilde | T1 |
| 2 | Los nombres nuevos pasan V1 a V4 con las listas actuales de `install.ps1` y no chocan sin distinguir mayúsculas | T1 |
| 3 | Ningún nombre nuevo aparece hoy (subcadena, cualquier capitalización) en gestionados, `install.ps1`, `tools/`, `tests/` (salvo los archivos de esta fase) | T1 |
| 4 | Ensayo en memoria: transformar los once textos con la tabla; sin palabras sin clasificar, sin nombre viejo residual, sin nombre nuevo en zonas sensibles nuevas, `hooks:` y frontmatter restante idénticos, recuentos de `INVENTORY` conservados uno a uno | T1 |
| 5 | Prueba puente: hashes esperados en `tests/rename_expected.json` (antes del cambio, calculados; tras el cambio, los del repositorio) | T1, T7 |
| 6 | Supuestos 5, 6 y 7 | T1 |
| 7 | Parametrización sin cambio: `git diff` de T2 a T4 sólo en `tests/`; suite en verde; ningún nombre viejo literal en las pruebas fuera de la lista cerrada | T2 a T4 |
| 8 | Mutación de control: con `names.py` cambiado en memoria a otros nueve nombres, las pruebas puras de Python que no leen el repositorio siguen pasando | T2 |
| 9 P | `$LegacyRoles` vacía: salida y bytes idénticos a la base (escenarios existentes sin modificar) | T5 |
| 10 P | Tabla heredada inválida (inyectada): exit 1 al arrancar, sin escribir | T5 |
| 11 P | Huérfano heredado (pares inyectados): `RenamedTo`, aviso por stderr sólo si el archivo existe, sin nota clásica, exit code sin cambio, también con `-DryRun`; el archivo viejo no se abre, respalda ni borra | T5 |
| 12 P | Huérfano heredado con estado esquema 3 (alias previo) | T5 |
| 13 P | Clave vieja en `aliases`: exit 1, motivo fijo con los dos nombres, sin el valor, sin escribir, también con `-DryRun` | T5 |
| 14 P | Nombre viejo como alias: válido; el destino viejo no es huérfano | T5 |
| 15 | Reporte: lista de anteriores vacía, bytes idénticos (goldens sin regenerar) | T6 |
| 16 | Reporte: con anteriores inyectados (`mock.patch`), el nombre anterior sale en el conjunto SyncLayer con su fila; uno desconocido sigue como `(otro agente)` | T6 |
| 17 | Tras el cambio: `agents/` tiene los nueve nombres nuevos y ninguno viejo; `name:` igual al nombre de archivo; `$AliasRoles`, `$LevelAgents`, `$LevelRows`, README (niveles), manifiesto, `agents_data.py` y `SYNCLAYER_AGENTS` coherentes | T7 |
| 18 | Tras el cambio: los cuatro bloques `hooks:` y las líneas `tools:`, `model:` y `color:` de los nueve agentes son byte a byte los de antes (comparados con valores fijados en T1) | T1, T7 |
| 19 P | Tras el cambio, repositorio real: instalación limpia (12 `NUEVO`), actualización desde una instalación vieja simulada (tabla de 3.3, fila 1), tabla de nombres viejos como alias, nueve alias con niveles 5 y 3 | T7 |
| 20 P | Tras el cambio: `$LegacyRoles` real igual a `names.LEGACY`; clave vieja real | T7 |
| 21 | Tras el cambio: goldens del reporte sin regenerar; los nueve nuevos y los ocho anteriores se clasifican como SyncLayer | T7 |
| 22 | Documentación: ningún nombre viejo como palabra en `README.md`, `CLAUDE.md`, `docs/agentes.md`, `docs/brand/*.md` fuera de las zonas marcadas (3.8); sin `Salomón` ni `Héctor`; sin promesas (`promise_hits`); nada marcado [G1] dicho como probado | T8, T9 |
| 23 | `INVENTORY` y manifiesto al día tras editar la guía; prueba puente retirada | T8 |
| 24 | Marca: `agents_data.py` igual al frontmatter; los SVG regenerados contienen los nueve nombres nuevos y ninguno viejo | T10 |

### 3.8 Documentación

- **Vigente (se actualiza):** `README.md` (estructura, uso y flujos, catálogo, hook, niveles, alias, carpeta
  de planes, perfiles, reporte de uso, límites, pruebas, mantenimiento), `CLAUDE.md`, `docs/agentes.md`,
  `docs/brand/voice-and-tone.md`, `docs/brand/claude-design-handoff.md`.
- **Histórica (no se reescribe, P7):** entradas pasadas de `HISTORY.md`, planes anteriores, hitos ✅ y
  párrafos «Hecho» de la línea de tiempo. Se añade una tabla de equivalencia en `HISTORY.md` y una frase al
  inicio de «Línea de tiempo y avance».
- **Sección nueva del README, «Nombres anteriores»**, entre los marcadores `<!-- nombres-anteriores:inicio -->`
  y `<!-- nombres-anteriores:fin -->`: tabla viejo a nuevo, qué ve quien reinstala (3.3), la lista de 3.6, la
  tabla de alias para conservar los nombres viejos, el reporte de uso (3.5) y el aviso de que el efecto en
  Claude Code real no está verificado.
- La prueba del caso 22 excluye sólo: esa sección, la sección «Línea de tiempo y avance», y en `CLAUDE.md` un
  bloque marcado igual. Todo lo demás debe estar con los nombres nuevos.
- Sin porcentajes ni promesas de ahorro, calidad o costo.

### 3.9 Seguridad

- El cambio no puede aflojar la guarda: `anubis` conserva `tests-only`; `salomon`, `hector` y `sherlock`,
  `readonly --allow-temp`. Caso 18 y revisión de `shield` en T7.
- `$LegacyRoles` es dato del script, no entrada. El estado previo y la configuración siguen siendo entrada no
  confiable: el uso 1 sólo calcula un texto de aviso y llama a `File.Exists` como hoy; el uso 2 sólo elige un
  mensaje fijo. Ningún camino nuevo abre, escribe, respalda ni borra. Mensajes por `Format-Safe`.
- El reporte de uso sigue mostrando sólo nombres de listas cerradas.

## 4. Tareas

Reglas para todas:

- Primero la prueba que falla, después la implementación. Python con `-B`.
- Nadie toca `~/.claude`: `-Target`, `HOME` y `--claude-dir` siempre temporales.
- `install.ps1` en ASCII sin BOM y sin asterisco; mensajes sin acentos; anclas sin mover ni renombrar.
  `tools/usage_report.py` en ASCII.
- De T1 a T7 nadie edita los once textos gestionados salvo T7, y T7 sólo con la transformación de 3.2.
- Ciclo por tarea: un `forge` fresco y después `auditor`; donde se indica, también `shield`. Los agentes se
  invocan con sus nombres vivos (los viejos) hasta V2.
- Cada cierre actualiza en el mismo commit «Línea de tiempo y avance» con la aritmética de 4.7. Commits sin
  etiquetas de coautoría.
- La suite no se corre en paralelo con procesos pesados.
- Decisión de T1 (hallazgo 3 de `auditor`): el caso 3 escanea `tests/` y sólo excluye los tres archivos de la
  fase. Los pares y nombres «inyectados» de T5 (casos 11 a 14) y T6 (caso 16) usan nombres de fantasía
  (por ejemplo `zeta-uno`), no los ocho nombres nuevos ni los viejos; así el caso 3 no se amplía ni se retira antes
  de T7. Si una prueba necesita de verdad un nombre real, se añade su archivo a la lista cerrada `OWN_FILES` con
  un comentario que lo justifique, y se anota en el cierre de la tarea.
- Pendientes de T2 para T7 (5 Minor de `auditor`, sin Critical ni Important), en `tests/test_rename.py`: (1) el
  caso 7 quita `DEBUGGER` y `SCRIBE_WORDS` de todo el texto y no vería un `DEBUGGER` literal en una cadena: usar
  `tokenize` y quitar sólo los identificadores; (2) tras T7 `OLD_ROLES`, `test_case1_eight_pairs`, `ALLOWED_TOKENS`
  y `_CONSTANT_TOKEN` salen de los valores de `names` y se rompen: tomar los nombres viejos de las claves de
  `rr.RENAME` y los identificadores fijos como literales; (3) en el caso 8 las entradas `PURE` de `test_plans` y
  `test_levels` no usan `names` (vacuas): quitarlas o anotarlo; (4) `run_with_mutated_names` debe restaurar
  `sys.path`; (5) renombrar `test_case7_names_py_and_rename_ref_are_the_only_homes_of_the_names` y comparar el
  conjunto de modos de `hooks:` en vez de `found[0]`. T7 no cierra sin resolverlos.
- Aviso para T10 (hallazgo C de `auditor`): `test_case6_assumption7...` de `tests/test_rename.py` falla si otra
  prueba de `tests/` menciona `.svg`; el caso 24 de T10 necesita leer los SVG, así que T10 ajusta o retira esa
  comprobación en el mismo cambio y lo anota en su cierre.

**Orden y paralelismo.** Estrictamente secuencial de T1 a T9: T2 a T5 y T7 comparten `tests/test_install.py`
o `install.ps1`, y cada cierre edita el `README.md`. T6 (reporte de uso) toca archivos disjuntos de T3 a T5
(`tools/usage_report.py`, `tests/test_usage_report*.py`) y podría ir en paralelo en su propio worktree; se
recomienda secuencial por la línea de tiempo y la memoria. T10 (`assets/`) es disjunta de T8 y T9 salvo el
README; misma recomendación.

Tamaños: S (hasta medio día), M (uno o dos archivos con lógica nueva), L (adaptación amplia de pruebas).

### Paso previo (sesión principal; no cuenta como unidad)

Al aprobar el plan: crear la rama; en el README añadir la fila «6. Renombrado de agentes» con «0 de 11», la
sección «La Fase 6 por frentes» y recalcular el global (4.7); este plan pasa a «aprobado» con las respuestas a
P1 a P16; el backlog enlaza a él.

### G1. Compuerta: Claude Code real (propietario; no cuenta como unidad)

En un proyecto de pruebas o con un `CLAUDE_CONFIG_DIR` aparte, sin tocar los agentes reales. Anotar la versión.

- Con los nueve agentes nuevos instalados: `/agents` los lista; se delega por nombre y por descripción; la
  guarda de `anubis`, `salomon`, `hector` y `sherlock` bloquea lo que debe.
- Con los ocho viejos todavía presentes: a cuál delega.
- Etiqueta de la delegación («Sindri (Sonnet): …») visible en el mapa de agentes.
- Resultado: sección «Resultado de G1» de este plan. **No bloquea T1 a T10; sí bloquea V2** (P13). Mientras no
  se corra, la documentación dice «no verificado».

### Fase A: preparación (sin cambio de comportamiento)

#### T1. Referencia del renombrado, colisiones y ensayo en memoria — tamaño M

- **Objetivo:** fijar la tabla, demostrar que el cambio es viable y dejar el fixture de la prueba puente.
- **Archivos:** crear `tests/rename_ref.py`, `tests/test_rename.py`, `tests/rename_expected.json`.
- **Pasos:** `rename_ref.py`: `RENAME` (ocho pares), `expected_texts()` (los once textos transformados con
  `aliases_ref`, con la ruta nueva como clave), `frozen_frontmatter()` (por agente: bloque `hooks:` y líneas
  `tools:`, `model:`, `color:` actuales, como datos fijos). `test_rename.py`: casos 1 a 6 y 18 (parte previa).
  Generar el fixture con los once hashes canónicos. Confirmar los supuestos 4 a 7; si uno falla, parar y
  reportar.
- **Pruebas:** casos 1 a 6.
- **Aceptación:** suite en verde; `git diff` sólo añade los tres archivos; cambiar un par de `RENAME` hace
  fallar el caso 5; añadir `Hermes` a una copia en memoria de un texto gestionado hace fallar el caso 3;
  ningún texto transformado contiene un nombre viejo como palabra.
- **Dependencias:** aprobación del plan, Fase 5 cerrada.
- **Revisa:** `auditor`.

#### T2. `tests/names.py` y parametrización de las pruebas pequeñas — tamaño M

- **Objetivo:** que las pruebas que no son `tests/test_install.py` tomen los nombres de un solo sitio.
- **Archivos:** crear `tests/names.py`; modificar `tests/test_aliases.py`, `tests/aliases_ref.py`
  (`SCRIBE_WORDS` pasa a diccionario por rol), `tests/test_levels.py`, `tests/levels_ref.py` (si nombra
  agentes), `tests/test_plans.py`, `tests/plans_ref.py`, `tests/test_manifest.py`,
  `tests/test_phase5_docs.py`, `tests/test_rename.py` y, en las pruebas del reporte de uso, sólo las que
  comparan `SYNCLAYER_AGENTS` con `agents/`.
- **Pasos:** según 3.7. `INVENTORY` y `NINE` pasan a construirse con las constantes. Las rutas esperadas del
  manifiesto se calculan de `names.ROLES`.
- **Pruebas:** casos 7 y 8.
- **Aceptación:** suite en verde con el mismo número de pruebas más las nuevas; `git diff` sólo en `tests/`;
  ningún archivo de la lista contiene un nombre viejo literal fuera de `tests/names.py`, `tests/rename_ref.py`
  y la lista cerrada de excepciones comentadas; ninguna aserción se elimina ni se debilita (revisión de
  `auditor` prueba a prueba).
- **Dependencias:** T1.
- **Revisa:** `auditor`.

#### T3. Parametrización de `tests/test_install.py`, primera parte — tamaño L

- **Objetivo:** helpers, muestras (`SAMPLE`, `ALIAS_SAMPLE`, `PLANS_SAMPLE`, `agent_md`) y pruebas de las
  Fases 1 a 3.
- **Archivos:** modificar `tests/test_install.py`.
- **Pasos:** clasificar antes las apariciones (nombre como rol, ruta, texto de muestra, golden, comentario
  histórico) y anotar el recuento por clase en el mensaje del commit. Sustituir según 3.7.
- **Pruebas:** caso 7.
- **Aceptación:** suite en verde; `install.ps1` sin tocar; mismo número de pruebas; las expectativas de orden
  se calculan, no se copian.
- **Dependencias:** T2.
- **Revisa:** `auditor`.

#### T4. Parametrización de `tests/test_install.py`, segunda parte — tamaño L

- **Objetivo:** pruebas de las Fases 4 y 5 y goldens embebidos.
- **Archivos:** modificar `tests/test_install.py`.
- **Pasos:** como T3. `F4T6_GOLDEN` pasa a plantilla: sólo las rutas de agente salen de `names`; el resto del
  texto queda byte a byte. `F4T6_SCRIBE_WORDS` usa el diccionario de T2.
- **Pruebas:** caso 7.
- **Aceptación:** suite completa en verde; en `tests/test_install.py` no queda ningún nombre viejo literal
  fuera de la lista cerrada; el golden renderizado con los nombres actuales es idéntico byte a byte al literal
  anterior (aserción temporal dentro de la tarea, retirada antes del commit).
- **Dependencias:** T3.
- **Revisa:** `auditor`.

### Fase B: compatibilidad (mecanismo inactivo)

#### T5. Nombres anteriores en el instalador — tamaño M — revisión de seguridad

- **Objetivo:** el mecanismo de 3.3 con la tabla vacía.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`, `tests/test_aliases.py` (lista nueva),
  `tests/aliases_ref.py` (motivo de la clave vieja en `validate_table`).
- **Pasos:** pruebas rojas (casos 9 a 14, con pares inyectados por `patch_script` tras la línea de
  `$LegacyRoles` o por el ancla que T5 documente). `$LegacyRoles = @()` junto a `$AliasRoles`;
  `Get-LegacyTableProblem`; `RenamedTo` heredado en el bucle de huérfanos; motivo de la clave vieja en
  `Get-AliasTableProblem`. Si el supuesto 6 falló, la lista lleva un único elemento centinela documentado en
  vez de estar vacía.
- **Pruebas:** casos 9 a 14.
- **Aceptación:** suite en verde sin modificar pruebas existentes; con la tabla vacía, salida y bytes
  idénticos a la base; ningún camino nuevo abre, escribe, respalda ni borra; ningún mensaje contiene un valor
  de la configuración ni del estado sin `Format-Safe`; comparaciones ordinales, sin `IgnoreCase`.
- **Dependencias:** T4.
- **Revisa:** `auditor` y `shield`.

#### T6. Nombres anteriores en el reporte de uso — tamaño S

- **Objetivo:** el mecanismo de 3.5 con la lista vacía.
- **Archivos:** modificar `tools/usage_report.py`, `tests/test_usage_report.py`.
- **Pasos:** pruebas rojas (casos 15 y 16). `SYNCLAYER_LEGACY_AGENTS = frozenset()`; la clasificación usa la
  unión; actualizar `ReportPurity.REACHABLE` sólo si el nombre nuevo es alcanzable desde un generador.
- **Pruebas:** casos 15 y 16.
- **Aceptación:** suite del reporte en verde; goldens sin regenerar; sin texto nuevo en `CATALOG`; lector y
  agregado sin otro cambio.
- **Dependencias:** T2 (secuencial tras T5 por recomendación).
- **Revisa:** `auditor`.

### Fase C: el cambio

#### T7. Cambio atómico de nombres — tamaño L — revisión de seguridad

- **Objetivo:** el repositorio pasa a los nombres nuevos en un solo commit con la suite en verde.
- **Archivos:** renombrar con `git mv` los ocho `agents/*.md`; modificar los nueve agentes,
  `rules/agentes.md`, `docs/agentes.md` (sólo con 3.2), `install.ps1` (`$AliasRoles`, `$LevelAgents`,
  `$LevelRows`, `$LegacyRoles`, comentarios y `.DESCRIPTION`), `install-manifest.json` (regenerado),
  `README.md` (sólo la tabla entre los marcadores de niveles y la línea de tiempo),
  `assets/brand/src/agents_data.py`, `tools/usage_report.py` (`SYNCLAYER_AGENTS` y
  `SYNCLAYER_LEGACY_AGENTS`), `tests/names.py` (constantes y `LEGACY`), `tests/test_rename.py` (la prueba
  puente pasa a comparar el repositorio), y las pruebas que aún necesiten ajuste.
- **Pasos:** generar los once textos con `rename_ref.expected_texts()`; `git mv` y escribir; datos del
  instalador; `python -B tools/build_manifest.py`; pruebas nuevas (casos 17 a 21); suite completa.
- **Pruebas:** casos 5, 17 a 21 y toda la suite.
- **Aceptación:** suite completa en verde; los once hashes coinciden con `tests/rename_expected.json`;
  `hooks/agent_guard.py` sin cambio y con el mismo hash en el manifiesto; `git diff` de los agentes sin
  cambios en `hooks:`, `tools:`, `model:` ni `color:`; `python -B tools/build_manifest.py --check` sale con 0;
  las 24 celdas de niveles iguales a las de antes; ningún nombre viejo en `install.ps1` fuera de
  `$LegacyRoles` y comentarios que lo expliquen. Lo que queda desfasado a propósito hasta T8 a T10 (prosa del
  README, `CLAUDE.md`, SVG) se lista en el mensaje del commit.
- **Dependencias:** T1 a T6.
- **Revisa:** `auditor` y `shield` (frontmatter de los cuatro agentes con guarda; instalación sobre una
  instalación vieja simulada).

### Fase D: documentación, marca y cierre

#### T8. README y guía — tamaño M

- **Objetivo:** documentación de usuario con los nombres nuevos y la sección «Nombres anteriores».
- **Archivos:** modificar `README.md`, `docs/agentes.md`, `install-manifest.json` (regenerado),
  `tests/test_aliases.py` (`INVENTORY` si cambian recuentos), `tests/test_rename.py` y
  `tests/rename_expected.json` (retirar la prueba puente y el fixture); crear `tests/test_phase6_docs.py`.
- **Pasos:** según 3.8. En la guía, texto nuevo sólo con `<rol>`, `<nombre>` y `<alias>`. Reescribir el
  párrafo del límite de palabra (ya no hay subcadenas reales). Límites nuevos: estado ausente (ocho archivos
  viejos sin aviso), agente propio con un nombre nuevo, V7 con los nombres nuevos.
- **Pruebas:** casos 22 (README y guía) y 23.
- **Aceptación:** suite en verde; manifiesto al día; sin nombres viejos fuera de las zonas marcadas; nada
  [G1] dicho como probado; sin promesas.
- **Dependencias:** T7.
- **Revisa:** `auditor`.

#### T9. `CLAUDE.md`, historial, documentos de marca y backlog — tamaño S

- **Objetivo:** el resto de la documentación vigente.
- **Archivos:** modificar `CLAUDE.md`, `HISTORY.md` (`[Sin publicar]` con la tabla de equivalencia),
  `docs/brand/voice-and-tone.md`, `docs/brand/claude-design-handoff.md`,
  `docs/plans/2026-11-19-backlog-configuracion-y-reportes.md`, `tests/test_phase6_docs.py`.
- **Pasos:** `CLAUDE.md`: arquitectura, convenciones, «Comportamientos no obvios» (contrato de
  `tests/names.py`, `$LegacyRoles`, lista de anteriores del reporte, regla sin tilde, nombres propios) y
  «Cierre de un cambio». Las notas de fases pasadas que nombran agentes como hecho histórico van dentro del
  bloque marcado.
- **Pruebas:** caso 22 completo.
- **Aceptación:** suite en verde; caso 22 cubre los cinco documentos.
- **Dependencias:** T8.
- **Revisa:** `auditor`.

#### T10. Assets de marca — tamaño S

- **Objetivo:** los SVG muestran los nombres nuevos.
- **Archivos:** modificar `assets/brand/src/build_round3.py` (espécimen `auditor` a `salomon`, P11); regenerar
  `assets/brand/agent-catalog-dark.svg`, `agent-catalog-light.svg`, `architecture-star-dark.svg`,
  `architecture-star-light.svg`, `slide-3-roster.svg` y la hoja de marca; `tests/test_phase6_docs.py` o
  `tests/test_brand_agents.py` (caso 24).
- **Pasos:** correr `build_brand.py`, `build_round2.py` y `build_round3.py` con `--fonts <carpeta>`. Revisar
  `git status`: sólo deben cambiar los SVG que nombran agentes. Si cambia `social-preview.svg`, reexportar el
  PNG; si cambian `symbol-16-dark.svg` o `symbol-dark.svg`, los favicons (no se espera). Comprobar con las
  medidas del generador que `shakespeare` (11 caracteres; el más largo era de 8) cabe en la tarjeta del
  catálogo, en la estrella y en la slide; si no cabe, parar y reportar (cambio de diseño: decide el
  propietario).
- **Pruebas:** caso 24.
- **Aceptación:** suite en verde; ningún SVG contiene un nombre viejo; ningún SVG editado a mano; revisión
  visual del propietario anotada como pendiente (V3).
- **Dependencias:** T7; carpeta de fuentes del propietario (P10).
- **Revisa:** `auditor`.

#### Cierre (lo coordina la sesión principal; cuenta como una unidad)

- **C1. `sentinel`:** suite completa con la salida a la vista; los 24 casos de 3.7 cubiertos.
- **C2. `shield`:** T5 y T7. Focos: guarda intacta en los cuatro agentes; ningún camino nuevo de E/S con
  datos del estado o de la configuración; mensajes sin fuga; comparaciones ordinales; instalación sobre una
  instalación vieja (nunca borra, respaldo correcto); lista cerrada del reporte.
- **C3. `auditor`** sobre el cambio completo.
- **C4. `scribe`** si queda documentación desfasada; memoria del proyecto actualizada por la sesión principal.
- **C5.** La sesión principal entrega al propietario la lista de 3.6 con las líneas exactas de
  `~/.claude/CLAUDE.md` (sólo lectura).
- **V1 (propietario; fuera del conteo):** G1.
- **V2 (propietario; fuera del conteo):** lista de 3.6 sobre `~/.claude`, con copia y `-DryRun` antes.
- **V3 (propietario; fuera del conteo):** revisión visual de los SVG.

### 4.7 Unidades y aritmética de la línea de tiempo

La Fase 6 tiene **11 unidades**: T1 a T10 y el cierre. El paso previo, G1, V1, V2 y V3 no cuentan.

| Frente | Unidades |
|---|---|
| Preparación | 4 (T1, T2, T3, T4) |
| Compatibilidad | 2 (T5, T6) |
| El cambio | 1 (T7) |
| Documentación, marca y cierre | 4 (T8, T9, T10, cierre) |

Seis fases con el mismo peso. Con las Fases 1 a 5 al 100 % y k unidades cerradas: Fase 6 = k ÷ 11;
proyecto completo = (500 + 100 × k ÷ 11) ÷ 6 = 83,33 + 1,515 × k. **Al aprobar el plan el global baja de
100 % a 83 %: es lo esperado.** Un cuadro = 10 %; la mitad exacta redondea hacia arriba.

| k | Fase 6 | Mostrado | Cuadros | Global | Mostrado | Cuadros |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 0 % | 0 % | 0 | 83,33 % | 83 % | 8 |
| 1 | 9,09 % | 9 % | 1 | 84,85 % | 85 % | 8 |
| 2 | 18,18 % | 18 % | 2 | 86,36 % | 86 % | 9 |
| 3 | 27,27 % | 27 % | 3 | 87,88 % | 88 % | 9 |
| 4 | 36,36 % | 36 % | 4 | 89,39 % | 89 % | 9 |
| 5 | 45,45 % | 45 % | 5 | 90,91 % | 91 % | 9 |
| 6 | 54,55 % | 55 % | 5 | 92,42 % | 92 % | 9 |
| 7 | 63,64 % | 64 % | 6 | 93,94 % | 94 % | 9 |
| 8 | 72,73 % | 73 % | 7 | 95,45 % | 95 % | 10 |
| 9 | 81,82 % | 82 % | 8 | 96,97 % | 97 % | 10 |
| 10 | 90,91 % | 91 % | 9 | 98,48 % | 98 % | 10 |
| 11 | 100 % | 100 % | 10 | 100 % | 100 % | 10 |

Por frente: 4 unidades (0, 25, 50, 75, 100 %: 0, 3, 5, 8, 10 cuadros); 2 unidades (0, 50, 100 %: 0, 5, 10);
1 unidad (0 o 10). Si la Fase 5 siguiera en 8 de 9 al aprobar: global = (488,9 + 100 × k ÷ 11) ÷ 6 (con k = 0:
488,9 ÷ 6 = 81,48 %, mostrado 81 %, 8 cuadros). Si una respuesta
cambia las unidades (P8 con la alternativa: 9 unidades; P10 con la alternativa: 10), se recalcula con la
misma fórmula.

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| El cambio afloja o pierde la guarda de un agente | El texto sale de la transformación de alias, que deja `hooks:` byte a byte; caso 18 con valores fijados antes; `shield` en T7 |
| Quien reinstala queda con 17 agentes y la delegación elige el viejo | Aviso por stderr por archivo (3.3); README «Nombres anteriores»; lista V2; G1. No se borra nada (decisión) |
| Estado ausente o ilegible: los ocho archivos viejos quedan sin aviso | Documentado como límite; lista V2 |
| Una configuración con claves viejas deja de instalar | Mensaje fijo que dice el nombre nuevo (caso 13); falla antes de escribir |
| La parametrización debilita pruebas sin que se note | `auditor` prueba a prueba; mismo número de pruebas; mutación de control (caso 8); golden renderizado idéntico al literal (T4) |
| El commit del cambio es grande y difícil de revisar | Mecanismos y parametrización antes; el cambio es casi sólo datos; prueba puente con hashes fijados en T1 |
| Cambia el orden alfabético y rompe expectativas de orden | Expectativas calculadas en T2 a T4; supuesto 5 comprobado en T1 |
| Un nombre nuevo coincide con un integrado futuro de Claude Code o con un agente del usuario | Lista de reservados revisable; el agente propio da `MODIFICADO` (exit 3), nunca se pisa sin `-Force`; G1 |
| `Shakespeare`, `Hermes` u otro nombre propio aparece en la guía con otro sentido y un alias lo reemplaza | Regla de escritura; inventario (`INVENTORY`) falla ante una mención nueva |
| Alguien escribe `Salomón` o `Héctor` y queda sin transformar | Regla sin tilde; pruebas (casos 4 y 22) |
| Los nombres nuevos no dicen el oficio y la delegación automática empeora | Las descripciones conservan el oficio; G1; documentado como no verificado. Vuelta atrás soportada: la tabla de alias con los nombres viejos |
| El reporte de uso pierde el historial | Lista cerrada de anteriores (3.5); goldens sin regenerar |
| `shakespeare` no cabe en los SVG | T10 mide y se detiene; decisión de diseño del propietario |
| Faltan las fuentes o las dependencias de marca | P10; T10 puede quedar como tarea del propietario sin bloquear el cierre técnico (se recalculan unidades) |
| La documentación histórica y la vigente mezclan vocabularios | Zonas marcadas, tabla de equivalencia, caso 22 |
| Las reglas vivas (`~/.claude`) y el `CLAUDE.md` global siguen con nombres viejos tras reinstalar a medias | Lista V2 con las líneas exactas; G1 antes de V2 |
| Durante la fase, un agente confunde nombres vivos (viejos) con los del repositorio (nuevos) | Regla en todas las tareas: se invoca con el nombre vivo hasta V2; los prompts lo dicen |
| La suite se alarga o se corre dos veces a la vez | Secuencial; validación sobre todo en Python; `subTest` |
| Un agente instala contra el `~/.claude` real | `-Target`, `HOME` y `--claude-dir` temporales en todos los prompts |

## 6. Preguntas abiertas

Cada una tiene un valor por defecto, que es lo que el plan implementa si no hay respuesta.

- **P1. Qué es el rol.** Por defecto: los nombres nuevos son los roles, más la tabla cerrada `$LegacyRoles`
  (opción C de 3.1). Alternativa: roles viejos como id interno y nombres nuevos como alias por defecto
  (opción B; contradice «nombres nuevos en `agents/` y manifiesto»).
- **P2. Clave vieja en `aliases`.** Por defecto: exit 1 con el mensaje «el rol X ahora se llama Y». Alternativas:
  aceptarla como sinónimo; dejar el mensaje genérico «rol desconocido».
- **P3. Nombres viejos como alias.** Por defecto: permitidos (es la vía para conservarlos, con la tabla lista
  en el README). Alternativa: reservarlos (nadie podría volver a `forge`).
- **P4. Archivos viejos en el destino.** Por defecto: aviso por stderr y nada más; el instalador nunca borra.
  Alternativa: un parámetro que los respalde y los quite (tarea nueva con revisión de seguridad).
- **P5. Historial en el reporte de uso.** Por defecto: los nombres anteriores se siguen reconociendo, cada uno
  en su fila. Alternativas: fusionarlos en el nombre nuevo; reconocer sólo los nuevos (el historial pasa a
  `(otro agente)`).
- **P6. Nota en el reporte sobre nombres anteriores.** Por defecto: ninguna (sólo README). Alternativa: una
  línea en «Cómo leer estos números» (dos idiomas y goldens regenerados).
- **P7. Historia.** Por defecto: no se reescriben `HISTORY.md`, los planes anteriores ni los hitos cerrados;
  se añade una tabla de equivalencia. Alternativa: reescribir todo con los nombres nuevos.
- **P8. Estrategia de pruebas.** Por defecto: parametrizar con `tests/names.py` antes del cambio (11 unidades).
  Alternativa: reemplazo mecánico con script dentro del commit del cambio (9 unidades, commit mucho mayor).
- **P9. Orden de `$AliasRoles`.** Por defecto: alfabético de los nombres nuevos (cambia el orden de las líneas
  `Alias:` y de las filas). Alternativa: conservar el orden de los roles viejos (hay que relajar el caso 1).
- **P10. Assets de marca.** Por defecto: se regeneran dentro de la fase (T10); el propietario indica la carpeta
  de fuentes. Alternativa: tarea del propietario fuera del conteo (10 unidades; los SVG quedan con nombres
  viejos hasta entonces).
- **P11. Espécimen tipográfico de la hoja de marca.** Por defecto: `auditor` pasa a `salomon`. Alternativa:
  dejarlo (es una muestra de letra, no el catálogo).
- **P12. Tildes.** Por defecto: `salomon` y `hector` sin tilde en todo el repositorio, también en prosa.
  Alternativa: tilde en prosa no gestionada (dos grafías; la prueba tendría que distinguir zonas).
- **P13. G1.** Por defecto: no bloquea T1 a T10; sí bloquea aplicar el cambio al `~/.claude` real (V2).
  Alternativa: G1 antes de T7.
- **P14. Rama.** Por defecto: `feat/renombrado-de-agentes` desde `feat/configuraciones-dinamicas` tras el
  cierre de la Fase 5. Alternativa: integrar antes la Fase 5 en `main` y salir de `main`.
- **P15. Peso en la línea de tiempo.** Por defecto: Fase 6 nueva con el mismo peso (el global baja a 83 %).
  Alternativa: contarla como unidades añadidas a la Fase 4 (el global baja menos: (400 + 100 × 9 ÷ 20) ÷ 5 = 89 %).
- **P16. Paralelismo.** Por defecto: todo secuencial. Alternativa: T6 y T10 en worktrees propios, con la
  sesión principal serializando los commits de la línea de tiempo y las corridas de la suite.
