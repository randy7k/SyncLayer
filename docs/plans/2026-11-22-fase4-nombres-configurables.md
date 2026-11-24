# Plan: Fase 4, nombres de agentes configurables (`aliases` en `synclayer-config.json`)

Fecha: 2026-11-22. Estado: **aprobado por el propietario el 2026-11-22** (el plan y los valores por
defecto de P1 a P9). **Enmienda E1 incorporada tras T1 (2026-11-22):** regla del límite de palabra
(3.5, casos 3, 5, 6, 34, 40, 42, 55 y 56, tarea T1-E). Ver «Enmiendas» al final. Los valores por
defecto y el resto del plan quedaron aprobados el 2026-11-22; la enmienda E1 fue aprobada por el propietario el 2026-11-22.
**Enmienda E2, aprobada tras T2 (2026-11-23):** la lista de nombres reservados pasa de siete a nueve
(decisión 4, V4) y V8 compara el destino de toda alias efectiva con todas las rutas del manifiesto
(3.2, casos 2, 8, 13, 57 y 58, tarea T2). **P10** (agente propio del usuario con el mismo `name:` que
un alias) quedó resuelta el 2026-11-23 con su valor por defecto: ver «Decisión sobre P10» al final.
**Enmienda E3, aprobada tras T3 (2026-11-23):** dos reglas nuevas del estado con esquema 3 (un `dest`
con alias no puede ser una ruta del manifiesto; tope de 74 caracteres), validación con conjuntos
ordinales, `$ManifestPaths` obligatorio en `Read-State` y ajuste del caso 20 (3.4, 3.7, casos 20, 21,
25 y 59 a 61, tareas T3 y T7). Queda abierta **P11** (`Get-Prop` desenrolla listas de un elemento:
defecto previo de las Fases 1 y 3).

Fuentes: [`2026-11-22-fase4-nombres-exploracion.md`](2026-11-22-fase4-nombres-exploracion.md)
(hechos verificados por `scout`, mapa de `oracle`, riesgos y opciones),
[`2026-11-20-fase3-esfuerzo-configurable.md`](2026-11-20-fase3-esfuerzo-configurable.md) (archivo de
configuración, estado con esquema 2, renderizado, clasificación) y
[`2026-11-19-backlog-configuracion-y-reportes.md`](2026-11-19-backlog-configuracion-y-reportes.md)
(Fase 4 y «Restricción de diseño: simple»). Rama: `feat/nombres-configurables`.

## 1. Objetivo

Que quien instala SyncLayer pueda dar a cualquiera de los nueve agentes un nombre propio (alias) en
`<Target>/synclayer-config.json` y que `install.ps1`, al instalar, escriba el agente en
`agents/<alias>.md` con `name: <alias>` y sustituya el nombre del rol por el alias en los textos que
instala. Cambiar un alias = editar el archivo y reinstalar. Sin alias configurados, el instalador
escribe los mismos bytes y muestra la misma salida que hoy.

### Decisiones ya tomadas (no se reabren)

1. Alcance: los nueve agentes (`atlas`, `auditor`, `debugger`, `forge`, `oracle`, `scout`, `scribe`,
   `sentinel`, `shield`), cada uno opcional. El que no figura conserva su nombre. El rol sigue siendo
   el id estable interno.
2. El instalador reemplaza el nombre del rol por el alias en lo que escribe en el destino: nombre del
   archivo, `name:`, `description:` y cuerpo de los agentes, y los textos gestionados
   `rules/agentes.md` y `docs/agentes.md`. El repositorio conserva los nombres originales. `README.md`,
   `HISTORY.md`, `docs/plans/` y `docs/brand/` no se transforman.
3. Si ya había un agente instalado con el nombre anterior, el instalador lo informa como `HUERFANO` y
   no lo toca, con una advertencia explícita de que dos agentes activos pueden solaparse.
4. Alias: sólo `[a-z0-9_-]`, sin `-` inicial, hasta 64 caracteres. Se rechazan los nombres integrados
   (`Explore`, `Plan`, `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide`,
   `web-fetch`), los alias duplicados, un alias igual al rol de otro agente y los ciclos. Se valida la
   tabla entera antes de escribir (exit 1, también con `-DryRun`).
   **Enmendada por E2 (2026-11-23):** la lista de nombres rechazados suma `fork` y
   `output-style-setup` (nueve en total). Es una ampliación conservadora, no un cambio de criterio;
   motivo en «Enmiendas».
5. Formas del alias derivadas de un único alias en minúsculas: minúscula, Capitalizada, MAYÚSCULAS y
   `@agent-<alias>`. Reemplazo con límite de palabra.
6. El reporte de uso (Fase 2) no cambia: un agente con alias sale como `(otro agente)`. Se documenta.
7. Clave nueva y opcional `aliases` (objeto rol a alias) en `synclayer-config.json`. `level` y
   `aliases` son opcionales; cualquier otra clave sigue dando exit 1; `{}` y la ausencia del archivo
   siguen siendo válidos. Sin alias, comportamiento y bytes idénticos a hoy (también la salida del
   nivel 5).
8. Nada promete ahorro, calidad ni costo. Documentación al día en el mismo cambio.

### Dentro de alcance

- `install.ps1`: listas cerradas de roles y nombres prohibidos, lectura y validación de `aliases`,
  separación de rol y ruta de destino, estado con esquema 3 y su lectura, transformación de textos,
  huérfanos por cambio de nombre, mensajes.
- Pruebas: `tests/aliases_ref.py` y `tests/test_aliases.py` (nuevos), casos nuevos en
  `tests/test_install.py`.
- Documentación: `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`, manifiesto regenerado,
  estado de la Fase 4 en el backlog.

### Fuera de alcance

- Cambiar `agents/*.md`, `tools/build_manifest.py`, el formato de `install-manifest.json`,
  `hooks/agent_guard.py`, `assets/brand/src/agents_data.py`, `tests/test_brand_agents.py`,
  `tests/test_manifest.py` o `tools/usage_report.py` (`SYNCLAYER_AGENTS`). El manifiesto sigue con
  doce archivos; los alias no entran en él.
- Alias con mayúsculas, espacios o unicode («el amigo QA» se escribe `amigo-qa`). Relajar
  `AllowedPattern`.
- Que el reporte de uso lea la tabla de alias.
- Borrar o renombrar el archivo anterior. Que el instalador cree, edite, respalde o borre
  `synclayer-config.json`. Leer o escribir `settings.json`.
- Detectar colisiones con agentes de proyecto, de plugin o gestionados (se documenta).
- Transformar texto fuera de los once archivos de texto gestionados (nueve agentes, reglas y guía).
  El hook no se transforma.
- Un parámetro `-Alias` o alias por proyecto.
- Corregir la laxitud de `Get-Prop` con listas de un elemento (P11): por defecto, tarea aparte tras
  la fase.

## 2. Supuestos

Los marcados **[G1]** los confirma el propietario en la compuerta G1.

1. Windows PowerShell 5.1; `install.ps1` en ASCII sin BOM y sin el carácter asterisco (ni en
   comentarios: las expresiones regulares usan `{0,}` y `{1,}`); mensajes en español sin acentos.
   Python 3.12 con `-B`, sólo biblioteca estándar, `unittest`. Sin pwsh.
2. **[G1]** Un agente de usuario cuyo archivo y `name:` son el alias carga y se invoca por el alias
   (`@agent-<alias>`, «usá a <alias>»). Hecho documentado: la identidad es `name:`, no el archivo.
3. **[G1]** Los caracteres `_`, `-` (no inicial) y los dígitos en `name:` son válidos. La
   documentación sólo prohíbe `-` inicial, `:` y más de 256 caracteres; el resto no está documentado.
4. Los nueve agentes del repositorio tienen exactamente una línea `name: <rol>` y una línea
   `description:` de una sola línea, en la columna 0 del frontmatter, y ninguna otra línea del
   frontmatter nombra un rol (comprobado en el repositorio; T1 lo fija con una prueba).
5. En `agents/*.md`, `rules/agentes.md` y `docs/agentes.md` los nueve nombres sólo aparecen como
   nombre de agente, en tres formas (`forge`, `Forge`, `FORGE`). «scribe» aparece además como
   subcadena de «escribe», «escriben», «describe», «reescribe» y «sobrescribe» (T1 fija el
   inventario). Algunos nombres van pegados a comillas angulares: `docs/agentes.md` trae
   `«SENTINEL sólo escribe tests»` y `«AUDITOR, SHIELD y…` (hallado por `forge` en T1; enmienda E1).
6. Ningún nombre de rol aparece hoy dentro de un bloque de código cercado, del destino de un enlace
   ni de una URL en esos archivos (comprobado: el único bloque cercado de `docs/agentes.md` no nombra
   roles; T1 lo fija).
7. `ConvertFrom-Json` de 5.1 entrega un objeto anidado como `PSCustomObject` y una lista anidada como
   `Object[]`. No verificado en este plan: T2 fija con pruebas el comportamiento real (incluida la
   clave repetida dentro de `aliases`).
8. Las fases 1 a 3 están cerradas: el estado actual es esquema 2 y `Read-State` lee 1 y 2.
9. Ningún agente ejecuta el instalador sin `-Target` y `HOME` temporales ni toca el `~/.claude` real.
   Los prompts de `forge`, `sentinel`, `auditor` y `shield` lo dicen de forma explícita.
10. Los once archivos de texto gestionados son UTF-8 válido (T1-E lo fija con una prueba): en UTF-8
    válido el byte `C3` siempre abre un carácter de dos bytes (U+00C0 a U+00FF). La regla de 3.5 se
    apoya en eso.
11. El repositorio trae los nueve roles en el manifiesto. Un manifiesto sin el archivo de un rol o
    con un agente que no es uno de los nueve sólo existe en las pruebas (E2 lo cubre igualmente).
12. **No documentado (ver P10):** qué agente gana cuando dos archivos de `~/.claude/agents/` declaran
    el mismo `name:`. La documentación sólo define la prioridad entre ámbitos distintos.
13. **Defecto previo, hallado en T3 (ver P11):** `Get-Prop` desenrolla una lista de un elemento, así
    que varios campos del estado y de `install-manifest.json` aceptan `[valor]` en lugar de `valor`.
    No es un hueco de seguridad conocido; contradice «tipos estrictos». `dest` no lo sufre.

## 3. Diseño

### 3.1 Formato de `aliases`

```json
{ "level": 3, "aliases": { "sentinel": "amigo-qa", "forge": "dev" } }
```

| Regla | Detalle |
|---|---|
| Claves de la raíz | Lista cerrada: `level` y `aliases`, las dos opcionales, comparación ordinal. Cualquier otra (incluida `agents` y `Aliases`): exit 1, con el mensaje actual |
| `aliases` ausente o `{}` | Sin alias. Comportamiento y bytes idénticos a hoy |
| `aliases` | Un objeto. `null`, lista, cadena, número o booleano: exit 1 |
| Claves de `aliases` | Lista cerrada: los nueve roles (`$AliasRoles`), comparación ordinal. Otra clave (incluida `Forge`): exit 1 |
| Valor | Una cadena. `null`, número, booleano, lista u objeto: exit 1 (no se trata como «sin alias») |
| Alias igual a su propio rol (`"forge": "forge"`) | Válido; equivale a no ponerlo (ver P3) |
| Lectura | La misma lectura única de la Fase 3 (tope de 65 536 bytes, UTF-8 estricto, rechazo de enlaces antes y después, rechazo de `__type`). El archivo no se abre dos veces |

La **tabla efectiva** es el conjunto de pares rol a alias con alias distinto del rol. Si está vacía, no
se llama a ninguna función de transformación y `destRel` es la identidad.

Consecuencia conocida: `__type` se rechaza en cualquier parte del texto (regla de la Fase 3), así que
un alias que contenga `__type` da el mensaje de clave desconocida. Se documenta; T2 lo fija.

### 3.2 Validación de la tabla (toda, antes de escribir)

Función pura `Get-AliasTableProblem`: devuelve el primer problema o `$null`. Se evalúa sobre la tabla
completa, antes de leer el estado y de cualquier escritura; exit 1 también con `-DryRun`.

| # | Regla | Motivo |
|---|---|---|
| V1 | El alias casa (ordinal, sin `IgnoreCase`) con `^[a-z][a-z0-9_-]{0,63}\z` | Decisión 4. La primera letra obligatoria es un endurecimiento (ver P1): un alias sólo de dígitos (`123`, `1e3`, `0x1f`) lo leería YAML como número en `name:`, y la forma Capitalizada necesita una letra |
| V2 | El alias no es un escalar que YAML convierte: `true`, `false`, `null`, `yes`, `no`, `on`, `off`, `y`, `n` | `name: yes` no sería una cadena |
| V3 | `agents/<alias>.md` casa con `$AllowedPattern` | Reutiliza la exclusión de nombres reservados de Windows (`con`, `nul`, `com1`...) |
| V4 | El alias no está en `$ReservedAliases`: **nueve** nombres en minúsculas (E2). Los siete integrados (`explore`, `plan`, `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide`, `web-fetch`) más `fork` y `output-style-setup` | Un agente de usuario con el nombre de un integrado lo sobrescribe; la sensibilidad a mayúsculas no está documentada, por eso se compara en minúsculas. `fork` y `output-style-setup` se reservan por prudencia (ver abajo) |
| V5 | El alias no es el nombre de otro rol de `$AliasRoles` | Dos agentes en la misma ruta. Hace imposibles los ciclos A a B y B a A; aun así la prueba los cubre de forma explícita |
| V6 | Ningún alias se repite | Dos roles en la misma ruta |
| V7 | Ningún alias contiene el nombre de un rol como palabra delimitada por `-` o por los extremos (`dev-sentinel`, `forge-2`) | Mantiene cerrada la transformación: la salida no contiene ninguna forma de un rol con alias, y eso es lo que comprueba la autocomprobación de 3.5 (ver P2) |
| V8 | **(E2)** Para **toda** alias efectiva, esté o no `agents/<rol>.md` en el manifiesto: `agents/<alias>.md` no coincide con **ninguna** ruta del manifiesto ni con el destino de otro rol | El alias nombraría un archivo que es otro agente. Ejemplo: `{"forge":"alfa"}` con un manifiesto que trae `agents/alfa.md` y no `agents/forge.md`. También cubre un manifiesto con un décimo agente (`AllowedPattern` lo admite) |

**V4, por qué nueve (E2).**

- `fork`: no figura como agente integrado, pero es un valor especial de `subagent_type`
  (`subagent_type: "fork"`; la documentación lo usa en `Agent(fork)` y aparece en el changelog
  2.1.302). Un agente de usuario con ese nombre podría chocar con ese valor.
- `output-style-setup`: `shield` recuerda un agente integrado histórico con ese nombre. `scout` no lo
  encontró en la documentación ni en el changelog 2.1.300 a 2.1.330, y no puede afirmar que nunca
  existiera. **No verificado.** Reservarlo cuesta un nombre y es conservador.
- **La lista es cerrada y puede quedarse atrás.** Claude Code puede añadir integrados nuevos; el
  instalador no los conoce hasta que se actualice `$ReservedAliases`. Se documenta en el README como
  límite: antes de elegir un alias, comprobar con `/agents` que el nombre no existe ya.

**V8, alcance (E2).** La versión original sólo comparaba el destino cuando el archivo del rol de
origen estaba en el manifiesto. Ahora compara siempre. Con el repositorio real (los nueve roles en el
manifiesto, supuesto 11) el resultado es el mismo que antes: V5 ya rechaza un alias igual a otro rol.
La diferencia sólo se ve con manifiestos de prueba. V8 **sólo ve las rutas del manifiesto**: no ve
los archivos que el usuario tenga ya en `<Target>/agents/` (ver 3.9 y P10).

Un alias para un rol cuyo archivo no está en el manifiesto sigue sin ser un error por sí mismo (igual
que un agente modificable ausente en la Fase 3): la tabla se aplica a los textos y no hay archivo que
renombrar. Sí lo es si su destino coincide con una ruta del manifiesto (V8).

Datos nuevos en `install.ps1` (contrato con `tests/test_aliases.py`; una lista por línea, como
`$LevelAgents`):

```powershell
$AliasRoles = @('atlas', 'auditor', 'debugger', 'forge', 'oracle', 'scout', 'scribe', 'sentinel', 'shield')
$ReservedAliases = @('explore', 'plan', 'general-purpose', 'claude', 'statusline-setup', 'claude-code-guide', 'web-fetch', 'fork', 'output-style-setup')
$YamlWords = @('true', 'false', 'null', 'yes', 'no', 'on', 'off', 'y', 'n')
```

### 3.3 Separación de rol y ruta de destino

Tres conceptos:

- **Rol** (`$rel`, por ejemplo `agents/sentinel.md`): clave del manifiesto, de `$canonSrc`,
  `$LevelRows`, `$LevelAgents`, `$outBytes`, `$outHash`, de `path` en el estado y de los mensajes
  sobre el origen.
- **Ruta de destino** (`$destRel[$rel]`, por ejemplo `agents/amigo-qa.md`): sólo para leer, escribir,
  respaldar y verificar en el destino, y para los mensajes sobre el destino.
- `$destRel` es una tabla rol a ruta, calculada una vez en el bloque `# Alias:`. Para los tres
  archivos fijos y para los agentes sin alias es la identidad.

Las filas de clasificación pasan de `@{ State; Path; DestHash }` a
`@{ State; Path; Dest; DestHash }` (`Path` = rol, o `$null` en un huérfano; `Dest` = ruta de destino).

| Uso | Hoy | Con el plan |
|---|---|---|
| Paso 2 (origen) | `$rel` | Rol. Sin cambio |
| Bloque `# Nivel:` (celda y `ConvertTo-LevelBytes`) | Extrae el agente de `$rel` | Rol. Sin cambio de clave: es lo que evita el fallo silencioso del nivel |
| `$outBytes`, `$outHash` | `$rel` | Rol |
| Paso 3: lectura del estado | `Read-State $statePath` | `Read-State` recibe además `$ManifestPaths` (las rutas del manifiesto), obligatorio (E3) |
| Paso 4: reanálisis, carpeta intermedia, existencia, hash del destino | `$rel` | Ruta de destino |
| Paso 4: comparación con el estado previo | `$prev.Written[$rel]` | `prevByDest[ruta de destino]` (3.6) |
| Paso 4: huérfanos | Ruta del estado que no está en el manifiesto | Ruta de destino del estado que no es destino actual de ningún rol (3.7) |
| Orden «hook primero» | `$row.Path -ceq $hookPath` | Rol (el hook no admite alias) |
| Respaldo (`Rel`, `From`) | `$row.Path` | Ruta de destino: el respaldo refleja el destino (`<respaldo>/agents/amigo-qa.md`) |
| Paso 5: filas del plan, `Ajuste:` | `$row.Path`, `$rel` | Ruta de destino |
| Sólo lectura y bloqueo antes de escribir | `$row.Path` | Ruta de destino |
| Paso 6 | `$item.Rel` | Ruta de destino (ya viene en el item) |
| Paso 7: `Find-Reparse`, `Write-Atomic`, `Copiado:`, `$written` | `$rel` | Escribe en la ruta de destino los `$outBytes` del rol; verifica contra `$outHash` del rol; `$written` y `Copiado:` llevan la ruta de destino |
| Paso 8 | `$rel` de `$written` | Ruta de destino contra `$outHash` del rol (tabla destino a rol) |
| Paso 9 y estado | `path` | `path` = rol; `dest` = ruta de destino (3.4) |
| Mensaje de exit 3 | `$row.Path` | Ruta de destino |
| Errores de nivel o de transformación (defecto del origen) | `$rel` | Rol |

Regla de mensajes: lo que habla del origen o de la tabla nombra el rol; lo que habla de un archivo del
destino nombra la ruta de destino. La correspondencia la dan las líneas `Alias:` (3.8).

Anclas de `patch_script` que **no cambian de texto ni de sitio**: los diez `# Paso N:`,
`# Carpeta de respaldo ya comprobada`, `Write-Atomic $dest $outBytes[$rel] $existing`,
`Write-Atomic $statePath $stateBytes $stateExists`, `$level = [int](Read-LevelConfig $configPath)`,
`function ConvertTo-LevelBytes` y `$result = $latin1.GetBytes(`. En el Paso 7, `$rel` sigue siendo el
rol y `$dest` pasa a calcularse con `$destRel[$rel]`. Anclas nuevas (contrato): el comentario
`# Alias:` (no tiene la forma `# Paso N:`) y `function ConvertTo-AliasBytes`.

Orden de ejecución: validaciones de `-Target`; tabla de niveles; Paso 1; Paso 2; `# Configuracion:`
(lee `level` y `aliases`, valida la tabla, V8 incluida: el manifiesto ya está cargado); avisos de
entorno; `# Alias:` (calcula `$destRel` y los bytes con alias); `# Nivel:` (parte de los bytes con
alias); Paso 3 en adelante.

### 3.4 Estado: esquema 3 y migración

Opciones consideradas:

| Opción | A favor | En contra |
|---|---|---|
| A. Escribir siempre esquema 3 | Un solo formato de escritura | Sin alias el estado ya no es idéntico byte a byte al de hoy; la primera reinstalación de todo el mundo crea un respaldo sólo con el estado; hay que tocar las aserciones `assert_state` de toda la suite |
| **B. Esquema 2 si `destRel` es la identidad; esquema 3 si algún destino difiere del rol** | Cumple «sin alias, bytes idénticos a hoy» también en el estado y en la salida (ninguna línea `Respaldo:` nueva); la suite existente no se toca | Dos formatos de escritura (difieren en una clave por entrada) |
| C. Archivo de estado aparte para los alias | El estado actual no cambia | Dos archivos que pueden desincronizarse; segunda entrada no confiable |

Se elige **B** (ver P4). `ConvertTo-StateBytes` recibe `$destRel`: con la identidad produce
exactamente los bytes de hoy; si no, esquema 3:

```json
{
  "schema": 3,
  "algorithm": "sha256",
  "eol": "lf",
  "files": [
    {
      "path": "agents/sentinel.md",
      "sha256": "<hash canonico del origen>",
      "written": "<hash canonico de lo escrito>",
      "level": 3,
      "dest": "agents/amigo-qa.md"
    }
  ]
}
```

- En el esquema 3, `dest` va en **todas** las entradas (igual a `path` en las que no tienen alias).
  Orden de claves fijo; mismos bytes que `json.dumps(obj, indent=2, ensure_ascii=True) + "\n"`.
- `Read-State` devuelve además `Dest` (rol a ruta).
- **(E3)** `Read-State` recibe `$ManifestPaths` (las rutas del manifiesto ya cargado) como parámetro
  **obligatorio**: sin él no puede aplicar la regla D5. No hay valor por defecto ni llamada sin él.

| Estado previo | Tratamiento |
|---|---|
| `schema` 1 | Como hoy; `dest` = `path` |
| `schema` 2 | Como hoy (mismas validaciones); `dest` = `path`. Si la entrada trae la clave `dest`: clave desconocida, ausente |
| `schema` 3 | Validaciones del 2, más las reglas D1 a D7 de abajo. Falta `dest` en alguna entrada: inválido |
| Otro `schema`, ilegible o inválido | Ausente, con el aviso actual. No se respalda. Nunca produce `ACTUALIZAR` ni `HUERFANO` |

Reglas de `dest` en el esquema 3 (cualquiera que falle: estado **ausente**, con aviso):

| # | Regla | Origen |
|---|---|---|
| D1 | Claves por entrada de lista cerrada: `path`, `sha256`, `written`, `level`, `dest` | Plan |
| D2 | `dest` es una cadena (leída con `Get-PropRaw(...).Value`: tipo estricto, una lista de un elemento no vale), sin `..`, `\`, `:` ni `/` inicial, y casa con `$AllowedPattern` | Plan |
| D3 | Si `path` no es `agents/...`, `dest` = `path`. Si lo es, `dest` empieza por `agents/` | Plan |
| D4 | Ningún `dest` repetido | Plan |
| D5 | **(E3)** Un `dest` distinto de su `path` no es el `path` de otra entrada del estado **ni la ruta de ningún archivo del manifiesto actual** (`$ManifestPaths`) | La primera mitad, plan; la segunda, T3 |
| D6 | **(E3)** Un `dest` distinto de su `path` mide como mucho **74 caracteres**: `agents/` (7) + alias (64) + `.md` (3). El 64 sale de la regex del alias de V1: una letra inicial más `{0,63}` | T3 |
| D7 | **(E3)** La validación usa conjuntos ordinales (`HashSet[string]` con `StringComparer.Ordinal`), no búsquedas en listas | T3 |

**D5, motivo y consecuencia aceptada (E3).** Es la regla conservadora: un estado que afirma «el rol
A está escrito en la ruta que hoy es el archivo de origen de B» no se puede clasificar sin ambigüedad
(esa ruta tendría a la vez un `written` del estado y un origen propio). Consecuencia aceptada:

- El usuario tenía `sentinel -> tester` y una versión nueva del repositorio añade un agente `tester`.
  El estado previo trae `dest: agents/tester.md`, que ahora es una ruta del manifiesto: D5 falla y el
  estado se trata como **ausente**. Todo archivo cuyo contenido cambió sale `MODIFICADO` (no hay
  `ACTUALIZAR` sin estado) y hace falta `-Force`; no se informa ningún huérfano.
- En ese mismo escenario la configuración también deja de ser válida: V8 rechaza el alias `tester`
  con exit 1 antes de llegar al estado. El usuario cambia primero el alias y después reinstala con
  `-Force`.
- El aviso debe ser claro. Motivo exigido (ASCII, sin acentos; rutas por `Format-SafeShort`):

  `aviso: <estado> no se pudo leer o no es valido (el destino <dest> de <path> es ahora un archivo del manifiesto; si el repositorio anadio un agente con el nombre de tu alias, elige otro alias y repite con -Force). Se trata como ausente: no se respalda.`

- Se documenta como límite en el README («Límites del instalador») y en 3.9.

**D6, motivo (E3).** Sin tope, un `dest` de 200 KB que casa con `$AllowedPattern` (el patrón no
limita la longitud) pasaba la validación y salía **entero por stdout** como fila `HUERFANO`. El tope
vale sólo para un `dest` distinto de su `path`: uno igual a su `path` ya está acotado por las rutas
reales. Una prueba ata el 74 a la regex del alias de `install.ps1`: lee el cuantificador y comprueba
que 7 + (1 + máximo) + 3 = 74; si alguien cambia la longitud del alias y no el tope, falla.

**D7, motivo (E3).** La primera versión comparaba cada `dest` contra listas: cuadrática. Con 2000
entradas tardaba 304 s. Con conjuntos ordinales es lineal.

Otras reglas de implementación fijadas en T3 (E3):

- `$dests` (rol a ruta, resultado de `Read-State`) y `$prevByDest` (ruta a `written`) son
  diccionarios **ordinales** (`Dictionary[string,string]` con `StringComparer.Ordinal`), no `@{}`.
- **Todos** los mensajes de `Read-State` y de `Get-ManifestEntries` que incluyen texto del archivo
  (rutas, claves) pasan por `Format-SafeShort` (40 caracteres y escapado). Antes, algunos usaban
  `Format-Safe`, sin recorte.

Migración: no hay migración forzada. El estado se reescribe sólo si sus bytes cambian (regla actual):
al activar el primer alias pasa de 2 a 3, y al quitar el último vuelve a 2; el estado anterior va al
respaldo (regla actual). Un instalador de la Fase 3 no lee el esquema 3: lo trata como ausente
(`MODIFICADO`, exit 3; nunca sobrescribe sin `-Force`). Se documenta.

`Nivel anterior:` no cambia: se calcula igual a partir de `level` de las entradas, en los tres
esquemas.

Laxitud heredada y no corregida aquí (P11): `path`, `sha256`, `written`, `level`, `schema`,
`algorithm` y `eol` se leen con `Get-Prop`, que desenrolla una lista de un elemento.

### 3.5 Transformación de textos

Dos funciones puras, sin E/S, en `install.ps1`:

- `ConvertTo-AliasText([string]$Text, $Forms)`: reemplazo de formas con límite de palabra.
- `ConvertTo-AliasBytes([byte[]]$Canon, [string]$Kind, [string]$Role, $Forms)`: `Kind` es `agent` o
  `text`. Entrada: bytes canónicos ya verificados contra el manifiesto. Salida: bytes a escribir.

**Formas.** Por cada par de la tabla efectiva, tres entradas en un diccionario **ordinal**
(`Dictionary[string,string]` con `StringComparer.Ordinal`; un `@{}` de PowerShell no distingue
mayúsculas y mezclaría `forge`, `Forge` y `FORGE`):

| Forma | Rol | Alias `amigo-qa` |
|---|---|---|
| Minúscula | `sentinel` | `amigo-qa` |
| Capitalizada (primera letra en mayúscula, resto igual) | `Sentinel` | `Amigo-qa` |
| Mayúsculas (`ToUpperInvariant`) | `SENTINEL` | `AMIGO-QA` |
| `@agent-<rol>` | `@agent-sentinel` | `@agent-amigo-qa` (sale de la forma minúscula: `-` es límite por la izquierda; tiene prueba propia) |

**Límite de palabra — regla incorporada tras T1 (2026-11-22), enmienda E1.**

Motivo: la regla original contaba como letra todo byte de 0x80 a 0xFF del texto decodificado en
ISO-8859-1. Un rol pegado a `«` o `»` (UTF-8 `C2 AB` y `C2 BB`) no se reemplazaba:
`«SENTINEL sólo escribe tests»` y `«AUDITOR, SHIELD y…` de `docs/agentes.md` conservaban `SENTINEL` y
`AUDITOR` en la copia instalada, contra la aceptación de T6 y el caso 42.

Regla vigente, sobre el texto decodificado en ISO-8859-1 (un byte, un carácter):

- Una **letra** es un carácter de `[A-Za-z0-9_]`, o la **secuencia de dos caracteres** `\xC3`
  seguido de uno de `\x80` a `\xBF` (en UTF-8, los caracteres U+00C0 a U+00FF: las letras latinas
  acentuadas `á é í ó ú ñ ü` y sus mayúsculas).
- **Todo lo demás es límite**, incluidos los demás bytes altos: `C2 AB` y `C2 BB` (`«` `»`), `C2 BF`
  y `C2 A1` (`¿` `¡`), `C2 A0` (espacio duro), `E2 80 xx` (comillas tipográficas, raya y semirraya,
  puntos suspensivos), `E2 86 92` (`→`), `E2 88 A5` (`∥`), y también `-`, `/`, `.`, `` ` ``, `@`,
  espacio y puntuación ASCII.
- Una forma casa sólo si **no** hay una letra justo antes ni justo después.
- Límite izquierdo, dicho como procedimiento: se mira el carácter anterior; si está en
  `[A-Za-z0-9_]`, es letra; si está entre `\x80` y `\xBF` **y** el anterior a ése es `\xC3`, es
  letra; en cualquier otro caso (incluido un `\xC3` suelto o un byte de continuación sin `\xC3`
  delante) es límite. Límite derecho: el carácter siguiente está en `[A-Za-z0-9_]`, o es `\xC3`
  seguido de uno de `\x80` a `\xBF`.

Expresión, la misma en los dos lenguajes. Dos lookbehind negativos de **ancho fijo** (uno y dos
caracteres) en vez de uno de ancho variable: el módulo `re` de Python no admite lookbehind de ancho
variable y .NET sí, así que esta forma vale en ambos.

PowerShell 5.1 (fuente en ASCII, sin asterisco; `$alt` es la alternación de las formas, cada una con
`[regex]::Escape`; opciones `RegexOptions.CultureInvariant`, sin `IgnoreCase`):

```powershell
$pattern = '(?<![A-Za-z0-9_])(?<!Ã[\u0080-¿])(?:' + $alt + ')(?![A-Za-z0-9_])(?!Ã[\u0080-¿])'
```

Python (`tests/aliases_ref.py`, sobre `data.decode("iso-8859-1")`, sin `re.I`):

```python
pattern = r"(?<![A-Za-z0-9_])(?<!\xc3[\x80-\xbf])(?:" + alt + r")(?![A-Za-z0-9_])(?!\xc3[\x80-\xbf])"
```

Límites reconocidos de la regla (se documentan):

- `C3 97` (`×`) y `C3 B7` (`÷`) cuentan como letra: un rol pegado a ellos no se reemplaza. Falla
  hacia el lado conservador.
- Las letras de fuera de U+00C0 a U+00FF (`ő`, griego, cirílico) son límite: un rol pegado a una de
  ellas sí se reemplaza. Hoy no hay ninguna en los once textos; el caso 5 lo vigila
  (`foreign_letter_hits`).
- Las marcas combinantes (categoría Unicode M, texto en NFD, p. ej. `forge` seguido de U+0301) son
  límite: un rol pegado a una se reemplazaría y el acento quedaría sobre el alias. Hoy los once textos
  son NFC y no tienen ninguna; el caso 5 también la vigila.
- Otras grafías (`sCribe`) no se tocan.

**Una sola pasada.** Se recorre el texto una vez, de izquierda a derecha, y lo ya reemplazado no se
vuelve a examinar. Nunca reemplazos sucesivos rol por rol.

**Agente (`Kind` = `agent`).**

1. Decodificar en ISO-8859-1 y partir por LF. Línea 0 = `---`; cierre = primera línea posterior
   exactamente `---`. Si no: error.
2. En el frontmatter: exactamente una línea igual a `name: <rol>` (ordinal; el rol sale de la ruta del
   manifiesto). Cero, más de una u otro valor: error.
3. Exactamente una línea que empieza por `description:` en la columna 0, con la forma
   `description: <texto>` de una sola línea: sólo ASCII imprimible, el valor no empieza por un
   indicador YAML y la línea siguiente es el cierre o una línea `clave:` (sin continuación). Si no:
   error.
4. Si alguna **otra** línea del frontmatter (`tools:`, `model:`, `color:`, `hooks:` y su bloque,
   `omitClaudeMd:`...) contiene una forma de un rol con alias: error (`referencia a un rol en una
   linea del frontmatter que no se transforma`). No se reescribe, por ejemplo, un `Agent(forge)`.
5. Si el propio rol tiene alias, la línea `name:` pasa a ser `name: <alias>`.
6. La línea `description:` y todo el cuerpo (tras el cierre) pasan por `ConvertTo-AliasText`. Las
   demás líneas del frontmatter no se tocan.
7. Unir con LF y codificar en ISO-8859-1.

**Texto (`Kind` = `text`, `rules/agentes.md` y `docs/agentes.md`).** Todo el contenido pasa por
`ConvertTo-AliasText`. No hay excepciones por bloques de código, código en línea ni enlaces: el
reemplazo es textual (decisión 2 y límite reconocido en la exploración). El código en línea **debe**
reemplazarse (`` `forge` `` es la forma más usada). Para que eso no toque nada imprevisto, T1 fija
con una prueba sobre el repositorio que ninguna forma de rol cae dentro de un bloque cercado, del
destino de un enlace `](...)` ni de una URL; si un cambio futuro de la guía mete una, la prueba falla
y obliga a decidir.

**Autocomprobación (falla cerrado).** Sobre el resultado, releído:

- Mismo número de líneas que la entrada (un alias no puede contener LF).
- Agente: cierre en el mismo índice; todas las líneas del frontmatter salvo `name:` y `description:`
  idénticas, índice por índice (el bloque `hooks:` de `sentinel`, `auditor`, `shield` y `debugger`
  queda byte a byte); la línea `name:` es exactamente `name: <alias o rol>`; la línea `description:`
  sigue cumpliendo la forma del paso 3; mismo conjunto de claves de primer nivel, sin repetidas.
- Recorrido en paralelo de entrada y salida: fuera de las coincidencias, carácter a carácter iguales;
  en cada coincidencia, la salida trae el texto esperado.
- Residuo: la salida no contiene ninguna forma con límite de palabra (misma regla) de un rol con
  alias (lo garantiza V7).

Un error de transformación es un defecto del origen que el manifiesto no detecta: exit 1 antes de
escribir, también con `-DryRun`.

**Orden con el nivel.** Opciones: alias primero y nivel después, o al revés. Tocan líneas disjuntas
(`name:`, `description:` y cuerpo frente a `model:` y `effort:`), así que el resultado es el mismo. Se
elige **alias primero, nivel después**: `ConvertTo-LevelBytes` no se modifica, valida la forma del
frontmatter ya con alias (regla 3: `name:` no empieza por indicador) y su autocomprobación compara
contra los bytes con alias. La celda del nivel se busca siempre por **rol**. Una prueba compara con la
referencia en los dos órdenes.

Casos límite:

| Caso | Resultado |
|---|---|
| Tabla efectiva vacía | No se llama a `ConvertTo-AliasBytes`; bytes del origen |
| Agente sin alias propio, con otro rol aliado | `name:` intacto; `description:` y cuerpo con el alias del otro (referencias cruzadas: «ATLAS plan», «SHIELD review», «implemented by FORGE», «ORACLE report») |
| «escribe», «escriben», «describe», «reescribe», «sobrescribe», «Describe» con `scribe` aliado | No se tocan (letra ASCII pegada) |
| Rol pegado a `«`, `»`, `¿`, `¡`, comilla tipográfica (`“` `”` `‘` `’`), raya (`—`), `…`, `→` o espacio duro | **Se reemplaza** (`«SENTINEL sólo…` pasa a `«AMIGO-QA sólo…`) |
| Rol pegado a una letra acentuada, antes o después (`Sentinelé`, `ñforge`, `SCRIBEÁ`) | **No se reemplaza** |
| Rol seguido de espacio y palabra acentuada (`SENTINEL sólo`) | Se reemplaza (el espacio es límite) |
| `agents/forge.md`, `~/.claude/agents/forge.md` dentro de un texto | La ruta pasa al alias (es la ruta real en el destino) |
| `Forge (Sonnet): ...` | `Dev (Sonnet): ...` |
| Alias que contiene otro alias como subcadena (`qa` y `qa2`) | Sin interferencia: una sola pasada, límites de palabra |
| `name:` duplicado, ausente o con otro valor; `description:` multilínea, ausente o duplicada | Error, exit 1 |
| `name:` o rol en el cuerpo (`name: forge` tras el cierre) | Es cuerpo: pasa por el reemplazo de palabras |
| Origen con CRLF | Llega en LF (bytes canónicos) |
| Bytes altos del texto | Se conservan byte a byte (ida y vuelta por ISO-8859-1) |
| Archivo que no nombra ningún rol con alias | Bytes idénticos al origen; sale `IGUAL` |
| Hook (`hooks/agent_guard.py`) | Nunca se transforma |
| Agente del manifiesto que no es uno de los nueve | No se transforma |

Por archivo quedan, como en la Fase 3, `srcHash` (manifiesto) y `outBytes`/`outHash` (lo que se
escribe: origen, con alias, con nivel o con ambos). Los bytes con alias no los cubre el hash del
manifiesto: se verifican contra `outHash` en los Pasos 7 y 8.

### 3.6 Clasificación

Con un estado válido se construye `prevByDest`: ruta de destino del estado a `written` (diccionario
ordinal, E3). La regla actual se conserva, mirando la **ruta de destino**:

| ¿Existe el destino? | hash = `outHash[rol]` | `prevByDest[destino]` = hash del destino | Estado | Acción |
|---|---|---|---|---|
| No | — | — | `NUEVO` | Escribe |
| Sí | Sí | — | `IGUAL` | Nada |
| Sí | No | Sí | `ACTUALIZAR` | Respalda y escribe |
| Sí | No | No | `MODIFICADO` | Sin `-Force`: exit 3. Con `-Force`: respalda y escribe |
| (destino del estado previo que ya no es destino de ningún rol) | | | `HUERFANO` | Sólo informa |

Sin alias y con estado de esquema 1 o 2, `prevByDest` es `Written` y la regla es la de hoy. La regla
dice «el estado afirma que en esta ruta escribimos estos bytes»: un archivo ajeno que ya ocupa la ruta
del alias nunca sale `ACTUALIZAR`.

Situaciones (cada fila tiene prueba en T7, salvo las marcadas):

| # | Situación | Resultado |
|---|---|---|
| S1 | Alias nuevo (`sentinel` a `amigo-qa`) sobre una instalación intacta sin alias | `agents/amigo-qa.md` `NUEVO`; `agents/sentinel.md` `HUERFANO` con aviso; los archivos que nombran a `sentinel` `ACTUALIZAR`; el resto `IGUAL`; estado a esquema 3; el anterior, al respaldo |
| S2 | Alias nuevo y ya existe un `agents/amigo-qa.md` ajeno | `MODIFICADO`, exit 3, nada escrito. Con `-Force`: respaldo y sobrescritura |
| S3 | Alias cambiado (`amigo-qa` a `tester`) | `agents/tester.md` `NUEVO`; `agents/amigo-qa.md` `HUERFANO` con aviso; textos `ACTUALIZAR`. El `agents/sentinel.md` de S1 ya no se informa |
| S4 | Alias quitado, sin el archivo viejo en disco | `agents/sentinel.md` `NUEVO`; `agents/amigo-qa.md` `HUERFANO` con aviso; estado vuelve a esquema 2 |
| S5 | Alias quitado, con el `agents/sentinel.md` viejo en disco | `IGUAL` si sus bytes son los que se escribirían; si no, `MODIFICADO` (no está en `prevByDest`), exit 3 |
| S6 | Cambio de nivel con el alias ya instalado | `agents/amigo-qa.md` `ACTUALIZAR` si su celda cambia, con el `model:` y el `effort:` del **rol**; `Nivel anterior:` |
| S7 | Alias nuevo y cambio de nivel a la vez | Como S1, y el agente nuevo sale con el nivel aplicado |
| S8 | Edición a mano de `agents/amigo-qa.md` | `MODIFICADO`, exit 3. Con `-Force`: respaldo en `<respaldo>/agents/amigo-qa.md` |
| S9 | Reasignación (`sentinel`: `amigo-qa` a `tester`; `forge`: a `amigo-qa`) | `agents/amigo-qa.md` `ACTUALIZAR` (intacto según `prevByDest`); `agents/tester.md` `NUEVO`; `agents/forge.md` `HUERFANO` con aviso |
| S10 | Estado ausente o ilegible con alias ya instalados | Destinos con los bytes esperados `IGUAL`; distintos, `MODIFICADO`; ningún huérfano (no hay de dónde saberlo) |
| S11 | Estado de esquema 1 o 2 y alias nuevo | Como S1 |
| S12 | Reinstalar igual, con alias | Todo `IGUAL`; ni estado, ni respaldo, ni aviso |
| S13 | Estado de esquema 3 leído por el instalador de la Fase 3 | Ausente: `IGUAL` o `MODIFICADO`. Sólo se documenta (no hay prueba: es otro binario) |
| S14 | **(E3)** El repositorio añade un agente con el nombre de un alias ya instalado (`sentinel -> tester` y aparece `agents/tester.md` en el manifiesto) | Con el alias aún en la configuración: exit 1 por V8. Tras cambiar el alias: el estado falla D5 y se trata como ausente, con el aviso de 3.4; lo que cambió sale `MODIFICADO` y hace falta `-Force`; ningún huérfano. Prueba en T3 (caso 59) |

### 3.7 Huérfanos

- Regla única: toda ruta de destino del estado previo que no es destino actual de ningún rol del
  manifiesto es `HUERFANO`. Sin alias coincide con la regla de hoy. Se informa aunque el archivo ya no
  exista (como hoy). Nunca se abre, respalda ni borra.
- **Huérfano por cambio de nombre**: su rol sigue en el manifiesto y su destino cambió. Si el archivo
  existe, además de la fila, un aviso por stderr (uno por archivo), en `-DryRun` y en ejecución real,
  sin cambiar el código de salida:

  `aviso: agents/sentinel.md es el nombre anterior de agents/amigo-qa.md y sigue en el destino: no se borra. Mientras exista hay dos agentes activos con descripciones casi iguales y la delegacion puede elegir cualquiera. Quitalo a mano si ya no lo usas.`

- La nota actual por stdout (`nota: los HUERFANO los instalo una version anterior y ya no estan en el
  manifiesto. No se borran.`) es **falsa** para un huérfano por cambio de nombre: su rol sí está en el
  manifiesto. Queda así:
  - **Entre T3 y T7 (estado intermedio, E3):** el instalador imprime la nota actual para cualquier
    huérfano, también el de cambio de nombre, y no hay aviso por stderr. Por eso el caso 20 no afirma
    ni la nota ni que stderr esté vacío: afirma la fila `HUERFANO`, que el archivo no se toca y el
    estado resultante.
  - **T7:** implementa el aviso de arriba y **cambia la nota**: se imprime sólo si hay algún huérfano
    que no es por cambio de nombre (su texto no cambia). Sin alias, la salida es idéntica a hoy y la
    prueba `test_orphan_note_is_stdout_and_not_a_warning` no se toca. T7 fija en sus casos 50 y 51 lo
    que el caso 20 dejó sin afirmar.
- El huérfano se informa en la corrida que lo deja huérfano y en sus `-DryRun` previos. Una vez
  reescrito el estado deja de informarse (igual que hoy; ver P5).
- La ruta de un huérfano viene del estado (entrada no confiable): está acotada por D2 y D6 (como mucho
  74 caracteres cuando es un alias) antes de imprimirse.

### 3.8 Salida de `-DryRun`, mensajes y códigos de salida

Sin alias no aparece ninguna línea nueva. Con tabla efectiva no vacía, tras `Nivel:` y
`Nivel anterior:` y antes de `Respaldo:`, una línea por alias en el orden de `$AliasRoles`:

`Alias: sentinel -> amigo-qa (agents/amigo-qa.md)`

Las filas del plan, `Ajuste:`, `Respaldado:` y `Copiado:` muestran la ruta de destino. `Alias:` no
casa con la expresión `LINE` de las pruebas.

| Código | Casos nuevos |
|---|---|
| 1 | `aliases` inválido; tabla de alias inválida (V1 a V8); error de transformación |
| 3 | Sin cambio de regla. Si algún `MODIFICADO` está en una ruta con alias, el mensaje añade: `Si el archivo es un agente tuyo con el mismo nombre que un alias, elige otro alias.` Sin alias, el mensaje es el de hoy |
| 4 | El archivo escrito no coincide con lo esperado |

`$verifyWhat`: sin alias, los textos de hoy (`el manifiesto`; `lo esperado para el nivel N`). Con
alias: `lo esperado para el nivel N y los alias`.

Mensajes de configuración (ASCII, sin acentos). Nombran el **rol** (clave ya validada contra la lista
cerrada) y un motivo fijo; **nunca el valor del alias** ni el contenido del archivo. Una clave
desconocida pasa por `Format-SafeShort`:

- `error: synclayer-config.json no es valido: <motivo>. No se escribio nada.`
- Motivos: `aliases debe ser un objeto`; `rol desconocido en aliases: <clave>`; `el alias de <rol>
  debe ser texto`; `el alias de <rol> solo admite a-z, 0-9, _ y -, empieza por letra y tiene hasta 64
  caracteres`; `el alias de <rol> es una palabra reservada de YAML`; `el alias de <rol> es un nombre
  reservado de Windows`; `el alias de <rol> es el nombre de un agente integrado de Claude Code`; `el
  alias de <rol> es el nombre de otro agente de SyncLayer`; `el alias de <rol> contiene el nombre de
  un agente de SyncLayer`; `<rol> y <rol> tienen el mismo alias`; `el alias de <rol> coincide con otro
  archivo del manifiesto`.
- Los motivos no cambian con E2: `fork` y `output-style-setup` usan el de V4, y V8 usa el suyo
  también cuando el rol de origen no está en el manifiesto.
- Transformación: `error: no se pueden aplicar los alias a agents/<rol>.md: <motivo>. No se escribio
  nada.`
- Estado y manifiesto (E3): todo texto del archivo que aparezca en un mensaje de `Read-State` o de
  `Get-ManifestEntries` pasa por `Format-SafeShort`. El aviso de D5 es el de 3.4.

### 3.9 Colisiones que el instalador no ve, copia inversa y reporte

Se documentan (README y guía), no se comprueban:

- Un agente de proyecto, de `--agents` o gestionado con el mismo nombre que el alias gana por
  prioridad. Un `.claude/agents/<rol>.md` de proyecto deja de reemplazar al global renombrado.
- Las plantillas de plugin y las referencias por nombre del usuario (`Agent(nombre)` en `tools:`,
  `permissions.deny`, matchers de `SubagentStart`/`SubagentStop`, `--agent`, `agent` de
  `settings.json`) siguen apuntando al nombre viejo.
- En un sistema de archivos que no distingue mayúsculas, un `agents/Amigo-QA.md` ajeno ocupa la ruta
  del alias: sale `MODIFICADO` (S2).
- Un integrado de Claude Code que no esté en `$ReservedAliases` (lista cerrada, E2): el instalador no
  lo rechaza y el agente con alias lo sobrescribiría.
- **Un agente nuevo del repositorio con el nombre de un alias ya instalado (E3, S14).** El instalador
  lo detecta, pero la salida es costosa: V8 rechaza la configuración (exit 1) y, tras cambiar el
  alias, el estado previo se trata como ausente (D5), así que los archivos con cambios salen
  `MODIFICADO` y hace falta `-Force`. No se pierde nada (siempre hay respaldo), pero no hay camino
  automático. Límite aceptado.
- **Agente propio del usuario en `<Target>/agents/` (P10, resuelta: se documenta; revisión de
  `shield` de T2).** V8 sólo ve las rutas del manifiesto. Dos casos:
  1. El usuario ya tiene un `agents/<alias>.md` propio: resuelto, sale `MODIFICADO` (S2).
  2. El usuario tiene **otro** archivo (`agents/mio.md`) que declara `name: <alias>`. El instalador
     no lo ve. Qué agente gana entre dos archivos del mismo ámbito con el mismo `name:` no está
     documentado (supuesto 12). Si ganara el del usuario, las llamadas al alias irían a un agente
     **sin el bloque `hooks:`** del rol renombrado (`sentinel`, `auditor`, `shield`, `debugger`): la
     guarda dejaría de aplicarse sin ningún aviso. Se documenta y se comprueba en G1 (ver «Decisión
     sobre P10»).
- **Copia inversa:** con alias (o con nivel distinto de 5) los archivos de `~/.claude` no son los del
  repositorio. La copia `~/.claude` a repo de un agente, de las reglas o de la guía no vale: el cambio
  se hace en el repositorio y se reinstala. `git ls-files` no lista `agents/<alias>.md`.
- **Reporte de uso:** un agente con alias sale como `(otro agente)` y deja de atribuirse a SyncLayer
  (decisión 6).
- Las pruebas que fijan nueve agentes y doce archivos (`TWELVE`, `SYNCLAYER_AGENTS`,
  `agents_data.py`, las listas de `test_install.py` y `test_levels.py`) siguen valiendo: el
  repositorio no cambia.

### 3.10 Seguridad

`aliases` es entrada no confiable y termina en una ruta y en un `name:` de frontmatter.

- Lista cerrada de caracteres (V1): un alias no puede traer salto de línea, `:`, espacio, comillas,
  `#`, `/`, `\`, `.` ni indicadores YAML. No puede inyectar una línea, una clave `hooks:` ni cambiar
  el tipo del escalar (V1, V2).
- La ruta `agents/<alias>.md` pasa por `$AllowedPattern` (V3) y por las comprobaciones de punto de
  reanálisis existentes, ahora sobre la ruta de destino, antes y después de escribir.
- Comparaciones ordinales (`Test-OrdinalEqual`, `Test-OrdinalIn`); expresiones regulares sin
  `IgnoreCase`; diccionarios y conjuntos ordinales (formas, `$dests`, `$prevByDest`, validación de
  `dest`).
- El bloque `hooks:` no se toca y la autocomprobación lo exige línea a línea; una referencia a un rol
  en una línea del frontmatter que no se transforma detiene la instalación.
- `dest` del estado es entrada no confiable: reglas D1 a D7 de 3.4. Un `dest` manipulado sólo puede
  producir una fila `HUERFANO` (informativa, de 74 caracteres como mucho si es un alias) o un
  `ACTUALIZAR` sobre una ruta permitida cuyo hash coincide (mismo modelo de amenaza que `written` hoy,
  siempre con respaldo). No puede apuntar a la ruta de un archivo del manifiesto (D5).
- Agotamiento de recursos (E3): la validación del estado es lineal (D7); un estado de 2000 entradas
  ya no bloquea el instalador durante minutos. El tope de 1 MiB del estado sigue vigente.
- Salida acotada (E3): ningún texto del estado o del manifiesto sale sin recorte por stdout ni por
  stderr (`Format-SafeShort` en los mensajes; D6 en las filas de huérfanos).
- Mensajes: nunca el valor de un alias inválido; rutas y claves por `Format-Safe` o
  `Format-SafeShort`.
- Tope de tamaño y lectura única heredados de la Fase 3.
- Nombres reservados (V4): lista cerrada de nueve, que puede quedarse atrás (E2).
- Límite documentado: un agente propio del usuario con el mismo `name:` que un alias podría dejar sin
  guarda al rol renombrado (3.9, P10).
- Laxitud heredada (P11, abierta): `Get-Prop` acepta `[valor]` por `valor` en varios campos del
  estado y del manifiesto. El valor interno se valida igual y siempre se lee con la misma función, así
  que no hay una doble interpretación conocida; contradice «tipos estrictos». `dest` es estricto.

### 3.11 Estrategia de pruebas

- `tests/aliases_ref.py` (auxiliar, no es `test_*.py`): segunda implementación independiente en
  Python: `validate_table(aliases)`, `forms(table)`, `transform_text(text, table)`,
  `transform_agent(data, role, table)`, `transform_doc(data, table)`, `dest_for(path, table)` y
  `state_for3(manifest, out_hashes, level, dests)`. Lee `$AliasRoles`, `$ReservedAliases` y
  `$YamlWords` con `levels_ref.read_ps_list`. El límite de palabra es la expresión de 3.5.
- `tests/test_aliases.py`: pruebas sin PowerShell (listas, inventario del repositorio, referencia).
- `tests/test_install.py`: casos con `powershell.exe`, siempre con `-Target` y `HOME` temporales.
  Fixture nuevo `ALIAS_SAMPLE`: `agents/sentinel.md` (con `hooks:`), `agents/forge.md` (cuya
  `description:` nombra a `ATLAS`), `agents/atlas.md`, `agents/scribe.md`, `rules/agentes.md` y
  `docs/agentes.md` mínimos (en UTF-8, con «escribe», «describe», `@agent-forge`, `Forge (Sonnet):`,
  una tabla en mayúsculas, un rol entre `«` y `»`, un rol tras `¿`, un rol pegado a una letra
  acentuada y un bloque cercado sin roles) y el hook. Ayudas: `set_config(level=None,
  aliases=None)`, `assert_alias_installed(files, level, aliases)`, `write_state(..., schema=3,
  dests=...)`.
- Las pruebas existentes no se modifican, salvo las anclas si alguna cambiara (no debería: 3.3).
- La suite ya tarda unos 4 minutos: variantes con `subTest` donde compartan preparación; la validación
  de la tabla se cubre sobre todo en Python y, en PowerShell, con un `subTest` por motivo.

Casos:

| # | Caso | Se comprueba | Task |
|---|---|---|---|
| 1 | `$AliasRoles` frente a `agents/*.md` | Los mismos nueve nombres | T1 |
| 2 | `$ReservedAliases` y `$YamlWords` | Listas esperadas, en minúsculas, sin repetidos. `$ReservedAliases` tiene **nueve** nombres, con `fork` y `output-style-setup` (E2) | T1, T2 (E2) |
| 3 | Inventario del repositorio | En los once archivos de texto, cada rol sólo aparece en las tres formas; conteo de coincidencias reemplazables por archivo fijado **con la regla de E1** (los `SENTINEL` y `AUDITOR` de `docs/agentes.md` pegados a `«` cuentan como reemplazables); «escribe», «escriben», «describe», «reescribe» y «sobrescribe» no cuentan; ninguna aparición de un nombre de rol queda sin clasificar: o es reemplazable o es una de esas subcadenas | T1, T1-E |
| 4 | Frontmatter real de los nueve | Una `name: <rol>`, una `description:` de una línea; ninguna otra línea del frontmatter nombra un rol | T1 |
| 5 | Zonas sensibles | Ningún rol dentro de un bloque cercado, del destino de un enlace ni de una URL en `rules/agentes.md` y `docs/agentes.md`; los once textos son UTF-8 válido; ningún rol queda pegado a una letra de fuera de ASCII y de U+00C0 a U+00FF | T1, T1-E |
| 6 | Referencia: nueve alias a la vez sobre el repositorio real | Sólo cambian `name:`, `description:` y líneas del cuerpo con roles; `hooks:` de los cuatro agentes con guarda idéntico; **sin residuo: ninguna aparición de un rol salvo las subcadenas del caso 3** | T1, T1-E |
| 7 | Referencia: orden con el nivel | `render_expected(transform_agent(x))` = `transform_agent(render_expected(x))` para los seis modificables y los niveles 1 a 4 | T1 |
| 8 | Referencia: validación | Cada regla V1 a V7 con un caso que falla y uno que pasa; ciclo A a B y B a A. Con E2: `fork` y `output-style-setup` fallan por V4 en la referencia | T1, T2 (E2) |
| 9 | Sin `aliases`, y `"aliases": {}` | Destino, estado y stdout idénticos byte a byte a la corrida sin configuración; sin línea `Alias:` | T2 |
| 10 | `aliases` de tipo inválido: `null`, lista, lista de un objeto, cadena, número, `true` | Exit 1 en ambos modos; nada escrito | T2 |
| 11 | Clave de `aliases` desconocida (`qa`, `Forge`, vacía) | Exit 1; mensaje con la clave escapada | T2 |
| 12 | Valor inválido: `null`, número, `true`, lista, objeto, vacío, 65 caracteres, mayúsculas, espacio, `:`, `.`, `/`, `-` inicial, dígito inicial, sólo dígitos, unicode, salto de línea | Exit 1 en ambos modos; el mensaje nombra el rol y no el valor | T2 |
| 13 | Reservados: los nueve de `$ReservedAliases` (también `Explore` y `PLAN`, que caen por V1), `true`, `null`, `con`, `nul`, `com1` | Exit 1 con su motivo | T2 |
| 14 | Tabla: alias repetido, alias igual a otro rol, intercambio `forge`/`scribe`, alias que contiene un rol (`dev-sentinel`, `forge-2`) | Exit 1; nada escrito | T2 |
| 15 | Alias igual al propio rol | Válido; idéntico al caso 9 | T2 |
| 16 | Clave repetida dentro de `aliases`; `aliases` repetida; alias con `__type` | Se fija el comportamiento real de 5.1 y se documenta | T2 |
| 17 | Clave `agents` en la raíz | Sigue siendo clave desconocida (prueba existente intacta) | T2 |
| 18 | `aliases` válido con `level` válido | Líneas `Nivel:` y `Alias:` en orden; (mientras dure la guarda temporal: exit 1 con su mensaje) | T2 |
| 19 | Validación antes de cualquier escritura | Con estado válido y cambios pendientes, una tabla inválida no escribe ni respalda | T2 |
| 20 | Estado esquema 3 válido, sin alias en la configuración | Rol `NUEVO` o `IGUAL`; la ruta `dest` vieja sale como fila `HUERFANO` y el archivo no se toca; estado reescrito en esquema 2. **(E3)** No afirma la nota de huérfanos ni que stderr esté vacío: eso lo define el aviso de 3.7 y lo fija T7 (casos 50 y 51) | T3 |
| 21 | Estado esquema 3 inválido: sin `dest`, `dest` fuera de `AllowedPattern`, con `..`, repetido, igual al `path` de otra entrada, `dest` distinto en un archivo fijo, clave extra, `dest` no texto, `dest` como lista de un elemento (`["agents/x.md"]`: estricto, D2) | Ausente con aviso; nunca `ACTUALIZAR` ni `HUERFANO`; no se respalda | T3 |
| 22 | Estado esquema 2 con clave `dest`; `schema` 4 | Ausente | T3 |
| 23 | `prevByDest` | Estado 3 con `dest` = ruta actual y `written` = hash del destino: `ACTUALIZAR`; con `written` de otra ruta: `MODIFICADO` | T3 |
| 24 | Estado esquema 1 y 2 sin alias | Toda la suite existente pasa sin cambios; `Nivel anterior:` igual | T3 |
| 25 | Estado hostil con `dest` enorme o no ASCII | stderr acotado y escapado; **(E3)** stdout también acotado: el `dest` no aparece entero en ninguna fila | T3 |
| 26 | `destRel` inyectado (después de `# Alias:`): instalación limpia | El archivo se escribe sólo en la ruta de destino; `Copiado:` y fila con esa ruta; estado = `state_for3` | T4 |
| 27 | `destRel` inyectado sobre un destino existente intacto y editado | `ACTUALIZAR` con respaldo en `<respaldo>/<ruta de destino>`; `MODIFICADO`, exit 3 | T4 |
| 28 | Verificación con ruta distinta del rol (alteración inyectada en el Paso 8) | Exit 4; el mensaje nombra la ruta de destino | T4 |
| 29 | Punto de reanálisis, carpeta, sólo lectura y bloqueo en la ruta de destino | Exit 1 en ambos modos, como hoy con la ruta del rol | T4 |
| 30 | Hook primero con `destRel` no identidad | `Copiado:` empieza por `hooks/agent_guard.py` | T4 |
| 31 | Idempotencia con `destRel` no identidad | Segunda corrida: todo `IGUAL`, estado sin reescribir | T4 |
| 32 | Instalación limpia con un alias (`ALIAS_SAMPLE`) | Cada archivo = referencia; `agents/<rol>.md` no existe; `name: <alias>`; estado esquema 3 | T5 |
| 33 | Diferencia línea a línea | Sólo `name:`, `description:` y cuerpo; `hooks:` de `sentinel` byte a byte; LF y salto final | T5 |
| 34 | Las cuatro formas y el límite de palabra | `forge`, `Forge (Sonnet):`, `FORGE`, `@agent-forge`, `agents/forge.md`; «escribe», «escriben», «describe», «reescribe», «sobrescribe» intactos con `scribe` aliado | T5 |
| 35 | Referencias cruzadas | Agente sin alias propio cambia sólo donde nombra a otro; un archivo que no nombra roles con alias queda en los bytes del origen | T5 |
| 36 | Frontmatter defectuoso: sin `name:`, `name:` duplicado o con otro valor, `description:` multilínea o duplicada, rol en `tools:` o en `hooks:`, sin cierre | Exit 1 en ambos modos; nada escrito; el mensaje nombra el rol | T5 |
| 37 | Un defecto sólo importa si hay alias | El mismo origen instala sin alias | T5 |
| 38 | La transformación sólo corre con tabla efectiva no vacía | Marcador inyectado en `function ConvertTo-AliasBytes` no se alcanza sin alias | T5 |
| 39 | Autocomprobación | Resultado corrompido por inyección: exit 1, nada escrito | T5 |
| 40 | Origen con CRLF y con bytes altos | Mismo resultado que con LF; los bytes altos se conservan byte a byte y el archivo sigue siendo UTF-8 válido | T5 |
| 41 | Alias y nivel juntos, niveles 1 a 4 | El archivo con alias trae el `model:` y el `effort:` de la celda del **rol** y línea `Ajuste:` con la ruta de destino; bytes = referencia en los dos órdenes | T6 |
| 42 | Repositorio real como origen, nueve alias, niveles 5 y 3 | 13 archivos; ninguno con nombre de rol; los once textos = referencia; el hook con el hash del manifiesto; sin residuo de roles: ningún nombre de rol en los once textos instalados salvo las subcadenas del caso 3 (incluye los roles entre `«` y `»` de la guía) | T6 |
| 43 | `-DryRun` con alias | Líneas `Alias:`, filas con rutas de destino, nada escrito | T6 |
| 44 | Mensajes de verificación | `lo esperado para el nivel N y los alias`; sin alias, los textos de hoy | T6 |
| 45 | Verificación posterior con alias (archivo alterado en el Paso 8) | Exit 4 | T6 |
| 46 | Nivel 5 sin alias | stdout, stderr, destino y estado idénticos byte a byte a los de antes de la fase (prueba de regresión de salida) | T6 |
| 47 | S1 a S5 | Tabla de situaciones | T7 |
| 48 | S6, S7 | Alias con cambios de nivel | T7 |
| 49 | S8 a S12 | Edición a mano, `-Force`, reasignación, estado ausente, estados 1 y 2, idempotencia | T7 |
| 50 | Huérfano por cambio de nombre | Aviso por stderr sólo si el archivo existe; **la nota actual por stdout no se imprime si todos los huérfanos son por cambio de nombre**; el archivo queda intacto (bytes y mtime); no entra en el respaldo; en `-DryRun` y real; mismo código de salida | T7 |
| 51 | Huérfano clásico sin alias | Nota por stdout y ningún aviso (prueba existente intacta). Mezcla de un huérfano clásico y uno por cambio de nombre: nota y aviso | T7 |
| 52 | Exit 3 con alias | Frase añadida sólo si un `MODIFICADO` está en una ruta con alias | T7 |
| 53 | Configuración intacta | Bytes y mtime de `synclayer-config.json` iguales tras instalar con alias y con `-Force`; no aparece en el respaldo | T7 |
| 54 | `install.ps1` sigue en ASCII, sin asterisco, `&&`, `??` ni datos personales | Pruebas estáticas existentes | T1 a T7 |
| 55 | Referencia: límite pegado a bytes altos (E1) | **Reemplaza** un rol pegado, antes y después, a `«`, `»`, `¿`, `¡`, `“`, `”`, `‘`, `’`, `—`, `–`, `…`, `→` y espacio duro. **No reemplaza** pegado a letra acentuada, antes o después: `Sentinelé`, `ñforge`, `éSCRIBE`, `SCRIBEÁ`. `\xC3` suelto y byte de continuación sin `\xC3` delante: límite (reemplaza). Las subcadenas del caso 3 siguen sin reemplazarse | T1-E |
| 56 | Lo mismo en el instalador (E1) | Con `ALIAS_SAMPLE` en UTF-8: `«SENTINEL sólo escribe tests»` sale con el alias en mayúsculas y «escribe» intacto; `Sentinelé` y `ñforge` no cambian; bytes = `aliases_ref` | T5 |
| 57 | Reservados añadidos por E2 | Alias `fork` y alias `output-style-setup`: exit 1 en `-DryRun` y real, nada escrito, motivo de V4, el mensaje nombra el rol y no el valor. Control: `forks` y `output-style` son válidos (la comparación es por nombre entero) | T2 (E2) |
| 58 | V8 con el rol de origen fuera del manifiesto (E2) | Manifiesto con `agents/alfa.md` y sin `agents/forge.md`, configuración `{"aliases": {"forge": "alfa"}}`: exit 1 en ambos modos, nada escrito, motivo `coincide con otro archivo del manifiesto`. Controles: el mismo manifiesto con `{"forge": "beta"}` (destino libre) es válido; con el rol de origen presente, V8 sigue rechazando la coincidencia | T2 (E2) |
| 59 | D5: `dest` con alias igual a una ruta del manifiesto (E3, S14) | Estado 3 con `agents/sentinel.md` a `agents/tester.md` y un manifiesto que trae `agents/tester.md`: estado ausente; el aviso nombra el motivo de 3.4 (dice que el destino es ahora un archivo del manifiesto y qué hacer); un archivo con cambios sale `MODIFICADO`, exit 3, nada escrito; con `-Force`, respaldo y sobrescritura; ningún `ACTUALIZAR` ni `HUERFANO`; el estado no se respalda. Control: el mismo estado con un manifiesto sin `agents/tester.md` es válido | T3 (E3) |
| 60 | D6: tope de 74 caracteres (E3) | `dest` con alias de 64 caracteres (74 en total): válido. De 65 (75 en total): ausente. `dest` de 200 KB que casa con `AllowedPattern`: ausente, y no aparece entero ni en stdout ni en stderr (salida acotada). Prueba estática: el 74 de `install.ps1` es 7 + (1 + el máximo del cuantificador de la regex del alias) + 3; cambiar uno sin el otro la hace fallar | T3 (E3) |
| 61 | D7 y mensajes (E3) | Estado de esquema 3 con 2000 entradas válidas: `-DryRun` termina dentro de un límite holgado (por ejemplo 60 s; antes, 304 s). Mensajes de `Read-State` y `Get-ManifestEntries` con una ruta o una clave larga: recortados a 40 caracteres y escapados. `Read-State` sin `$ManifestPaths` no es invocable (parámetro obligatorio; prueba estática de las llamadas) | T3 (E3) |

## 4. Tareas

Todas secuenciales: T1 a T7 tocan `install.ps1` y `tests/test_install.py`. No hay tasks
paralelizables. Reglas para todas:

- Primero la prueba que falla en `tests/test_install.py`, después la implementación. Python con `-B`.
- Ningún agente lanza `install.ps1` sin `-Target` y `HOME` temporales ni toca `~/.claude`.
- `install.ps1` en ASCII sin BOM y sin asterisco; mensajes sin acentos; los `# Paso N:` y las anclas
  de 3.3 no se renombran ni se mueven.
- Ciclo por task: `forge` y después `auditor`. Donde se indica, también `shield`.
- Al cerrar cada task, el mismo commit actualiza «Línea de tiempo y avance» del README con la
  aritmética de 4.5. Commits sin etiquetas de coautoría.
- La suite no se corre en paralelo con procesos pesados.

Tamaños: S (hasta medio día de `forge`), M (uno o dos archivos con lógica nueva), L (lógica nueva más
adaptación amplia de pruebas).

### Paso previo (sesión principal; no cuenta como unidad)

Al aprobar el plan: en el README, la Fase 4 pasa de «sin desglosar» a «0 de 9» y se crea «La Fase 4
por frentes»; la frase de «Avance global» deja de decir que la fase 4 está sin desglosar. El avance
global sigue en 60 %. Este plan pasa a «aprobado».

### G1. Compuerta: verificación en Claude Code real (propietario; no cuenta como unidad)

- En un proyecto de pruebas (agente de proyecto: no toca `~/.claude`), crear
  `.claude/agents/zz-alias_prueba-2.md` con `name: zz-alias_prueba-2`. Comprobar con `claude --debug`
  que no se omite, que aparece en `/agents` y que se invoca con `@agent-zz-alias_prueba-2` y por
  nombre en lenguaje natural. Anotar la versión de Claude Code.
- Copiar el archivo con otro nombre y otro `name:` y la misma `description:`: ver cómo se listan los
  dos y cuál elige la delegación automática (el solapamiento que avisa 3.7).
- **Para P10:** dos archivos del mismo ámbito con el **mismo** `name:` y cuerpos distintos (uno con
  bloque `hooks:` y otro sin él): anotar cuál carga, si `claude --debug` avisa del duplicado y cuál
  responde a `@agent-<nombre>`.
- Renombrar el archivo con la sesión abierta (no documentado): anotar si hace falta reiniciar.
- Resultado: sección «Resultado de G1» de este plan.
- **No bloquea T1 a T8** (ver P6). **Bloquea V2** (aplicar alias al `~/.claude` real). Si el supuesto
  2 o el 3 es falso, el plan vuelve a `atlas` antes de T5.

### Fase A: datos y configuración

#### T1. Listas cerradas, referencia en Python y pruebas estáticas — tamaño S

- **Objetivo:** los datos de 3.2 en `install.ps1` y la referencia independiente con la que se
  compararán los bytes del instalador.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`; crear `tests/aliases_ref.py`,
  `tests/test_aliases.py`.
- **Pasos:** prueba roja en `StaticChecks` (`$AliasRoles` = nombres de `agents/*.md`). En
  `install.ps1`: `$AliasRoles`, `$ReservedAliases`, `$YamlWords` (aún sin uso). `aliases_ref.py`
  completo (3.11). `test_aliases.py` con los casos 1 a 8.
- **Pruebas:** casos 1 a 8 y 54.
- **Aceptación:** la suite pasa; la instalación se comporta igual que antes (ninguna prueba existente
  cambia); quitar un nombre de `$AliasRoles` hace fallar el caso 1; añadir «forge» dentro de un bloque
  cercado de `docs/agentes.md` haría fallar el caso 5 (se comprueba sobre una copia en memoria).
- **Dependencias:** aprobación del plan.
- **Revisa:** `auditor`.

#### T1-E. Enmienda de T1: límite de palabra de E1 — tamaño S — no cuenta como unidad

Forma parte de T1 (mismo `forge`, misma unidad de la línea de tiempo). T1 no se da por cerrada sin
ella.

- **Objetivo:** que la referencia y sus pruebas usen la regla de 3.5 vigente (letra = `[A-Za-z0-9_]`
  o la pareja `\xC3[\x80-\xBF]`; todo otro byte alto es límite).
- **Archivos:** modificar `tests/aliases_ref.py`, `tests/test_aliases.py`. `install.ps1` no cambia
  (aún no tiene la transformación).
- **Pasos:** primero las pruebas rojas: caso 55, y los casos 3, 5 y 6 con la aserción de residuo
  («ningún nombre de rol salvo las subcadenas permitidas») y los conteos nuevos. Después, sustituir en
  `transform_text` el límite por la expresión Python de 3.5 (dos lookbehind de ancho fijo y dos
  lookahead). Recalcular los conteos por archivo del caso 3 con la regla nueva y fijarlos: en
  `docs/agentes.md` suben por los roles pegados a `«`. Añadir la comprobación de UTF-8 válido de los
  once textos.
- **Pruebas:** casos 3, 5, 6 y 55; el resto de `test_aliases.py` sin cambios.
- **Aceptación:** la suite pasa; con los nueve alias, la referencia no deja ningún nombre de rol en
  `docs/agentes.md`, `rules/agentes.md` ni en los nueve agentes, salvo «escribe», «escriben»,
  «describe», «reescribe» y «sobrescribe»; `Sentinelé` y `ñforge` no se reemplazan; el patrón no usa
  lookbehind de ancho variable ni `re.I`.
- **Dependencias:** T1.
- **Revisa:** `auditor` (junto con T1).

#### T2. Clave `aliases`: lectura y validación de la tabla — tamaño M — revisión de seguridad

- **Objetivo:** leer y validar `aliases` según 3.1 y 3.2 y mostrar las líneas `Alias:` (3.8), sin
  aplicarlas todavía.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`. Con E2, también
  `tests/aliases_ref.py` y `tests/test_aliases.py` (lista de nueve y V8 en la referencia).
- **Pasos:** la lista cerrada de la raíz admite `aliases`; lectura única (el archivo no se abre otra
  vez: la lectura actual entrega también el objeto `aliases`; la línea ancla
  `$level = [int](Read-LevelConfig $configPath)` se conserva); `Get-AliasTableProblem` (V1 a V8) y
  tabla efectiva; mensajes de 3.8; líneas `Alias:`; actualizar `.DESCRIPTION`. **Guarda temporal:**
  una tabla efectiva no vacía y válida termina con exit 1 y
  `error: los alias aun no se pueden aplicar en esta version. No se escribio nada.`; T5 la retira
  junto con su prueba.
- **Pasos de la enmienda E2 (misma unidad, mismo `forge`; T2 no se cierra sin ellos):** primero las
  pruebas rojas (casos 2, 8, 13, 57 y 58). Después: `$ReservedAliases` con los nueve nombres de 3.2;
  V8 evaluada para toda alias efectiva contra todas las rutas del manifiesto, esté o no el archivo
  del rol de origen; la referencia Python igual. Los textos de los mensajes no cambian.
- **Pruebas:** casos 9 a 19, 57 y 58; casos 2 y 8 actualizados; una prueba de la guarda temporal.
- **Aceptación:** la suite pasa; ningún valor de `aliases` llega a un archivo del destino; ningún
  mensaje contiene el valor de un alias inválido; ningún camino de error escribe; la configuración no
  se abre para escritura; las pruebas de la Fase 3 sobre la configuración pasan sin cambios. **Con
  E2:** `fork` y `output-style-setup` se rechazan por V4 en `-DryRun` y en ejecución real;
  `$ReservedAliases` tiene exactamente nueve nombres y coincide con la referencia; ninguna alias
  efectiva cuyo destino `agents/<alias>.md` sea una ruta del manifiesto pasa la validación, esté o no
  `agents/<rol>.md` en el manifiesto; con el repositorio real, ninguna configuración que antes era
  válida deja de serlo salvo las que usan los dos nombres nuevos.
- **Dependencias:** T1 y T1-E.
- **Revisa:** `auditor` y `shield` (los dos vuelven a revisar tras E2).

### Fase B: rol y ruta

#### T3. Estado con esquema 3: lectura, `prevByDest` y huérfanos — tamaño M — revisión de seguridad

- **Objetivo:** `Read-State` lee los esquemas 1, 2 y 3 (3.4); la clasificación usa `prevByDest` (3.6)
  y la regla de huérfanos generalizada (3.7, sin el aviso). No se escribe todavía el esquema 3.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`, `tests/aliases_ref.py`.
- **Pasos:** `write_state(..., schema=3, dests=...)` y `state_for3`; validaciones de `dest`; `Dest` en
  el resultado de `Read-State`; `prevByDest`; huérfano = destino previo que no es destino actual.
- **Lo que quedó fijado al implementarla (E3; parte de la misma unidad):**
  - `Read-State` recibe `$ManifestPaths`, obligatorio; el Paso 3 se lo pasa.
  - Reglas D5 (segunda mitad: `dest` con alias no puede ser una ruta del manifiesto), D6 (74
    caracteres, con la prueba que lo ata a la regex del alias) y D7 (conjuntos ordinales).
  - `$dests` y `$prevByDest` como diccionarios ordinales.
  - `Format-SafeShort` en todos los mensajes de `Read-State` y `Get-ManifestEntries`.
  - Aviso de D5 con el motivo de 3.4. Si el texto implementado no dice que el destino es ahora un
    archivo del manifiesto y qué hacer, se ajusta en esta misma unidad.
  - El caso 20 no afirma la nota de huérfanos ni stderr vacío (lo define T7).
  - `dest` se lee con `Get-PropRaw(...).Value` (estricto). El resto de campos sigue con `Get-Prop`:
    defecto previo, P11; **no se corrige en T3**.
- **Pruebas:** casos 20 a 25 y 59 a 61; toda la suite existente.
- **Aceptación:** la suite pasa sin modificar ninguna prueba existente; con estados de esquema 1 y 2
  la clasificación es la de hoy; un estado de esquema 3 inválido nunca produce `ACTUALIZAR` ni
  `HUERFANO`; `Read-Manifest` sigue exigiendo `schema` 1. **Con E3:** ningún `dest` con alias que
  coincida con una ruta del manifiesto o con el `path` de otra entrada deja un estado válido; ningún
  `dest` con alias de más de 74 caracteres deja un estado válido; ningún texto del estado sale sin
  recorte por stdout ni por stderr; un estado de 2000 entradas se valida en tiempo lineal; no queda
  ninguna llamada a `Read-State` sin `$ManifestPaths`; con el repositorio real y sin alias, la salida
  es la de antes.
- **Dependencias:** T2.
- **Revisa:** `auditor` y `shield`.

#### T4. `destRel` en los pasos 4 a 9 y escritura del esquema 3 — tamaño L — revisión de seguridad

- **Objetivo:** la tabla de usos de 3.3 completa, con `destRel` como identidad en producción.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** bloque `# Alias:` que calcula `$destRel` (identidad); V8 ya se evalúa en la validación
  de la tabla desde T2 (E2) y el bloque no la repite; filas con `Dest`; pasos 4 a 9 según la tabla de
  3.3; `ConvertTo-StateBytes` con `$destRel` (esquema 2 con la identidad, 3 si no); las pruebas
  inyectan con `patch_script("# Alias:", ...)` un `destRel` no identidad.
- **Coherencia con E3:** el estado que T4 escribe debe pasar las reglas D1 a D7 al releerlo. Un
  `destRel` inyectado en las pruebas usa rutas que no están en el manifiesto y de 74 caracteres como
  mucho; si no, la segunda corrida trataría el estado como ausente (el caso 31 lo detectaría).
- **P10 (resuelta: sin código):** T4 no añade ninguna comprobación sobre los archivos no gestionados
  de `<Target>/agents/`.
- **Pruebas:** casos 26 a 31; toda la suite existente.
- **Aceptación:** la suite pasa sin modificar ninguna prueba existente (las anclas de 3.3 intactas);
  con la identidad, los bytes del destino, del estado y de la salida son los de antes; con un
  `destRel` inyectado nunca se crea ni se toca `agents/<rol>.md`; el hook sigue yendo primero; el
  estado escrito con un `destRel` no identidad se relee como válido.
- **Dependencias:** T3.
- **Revisa:** `auditor` y `shield`.

### Fase C: transformación

#### T5. Transformación de textos y activación de los alias — tamaño L — revisión de seguridad

- **Objetivo:** el algoritmo de 3.5 y su uso: los alias se aplican de punta a punta.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** `ConvertTo-AliasText` (con la expresión PowerShell de 3.5, tal cual) y
  `ConvertTo-AliasBytes` (puras, con autocomprobación); el bloque `# Alias:` calcula `$destRel` desde
  la tabla efectiva y los bytes con alias de los nueve agentes y los dos textos; el bloque `# Nivel:`
  parte de esos bytes (la celda se sigue buscando por rol); mensajes de error de transformación;
  retirar la guarda temporal de T2 y su prueba; fixture `ALIAS_SAMPLE` y ayudas.
- **P10 (resuelta el 2026-11-23 con el valor por defecto):** T5 no añade comprobación sobre agentes
  propios del usuario; sólo se documenta en T8 y se comprueba en G1.
- **Pruebas:** casos 32 a 40 y 56.
- **Aceptación:** la suite pasa; sin alias no se llama a la transformación (caso 38) y los bytes son
  los de antes; con alias, todo byte escrito coincide con `aliases_ref`; un rol pegado a `«`, `»`,
  `¿` o `¡` se reemplaza y uno pegado a una letra acentuada no; el bloque `hooks:` de los agentes con
  guarda queda idéntico; el hook no se transforma; ningún archivo fuera de los once textos cambia.
- **Dependencias:** T4. G1 recomendada antes (no bloquea, P6).
- **Revisa:** `auditor` y `shield`.

#### T6. Alias con niveles, repositorio real y `-DryRun` — tamaño M — revisión de seguridad

- **Objetivo:** demostrar que el nivel no falla en silencio con alias y que la salida sin alias no
  cambió; cerrar lo que las pruebas destapen.
- **Archivos:** modificar `tests/test_install.py`, `install.ps1`.
- **Pasos:** pruebas de alias y nivel juntos; repositorio real con nueve alias; `-DryRun`;
  `$verifyWhat`; `Ajuste:` con la ruta de destino; prueba de regresión de la salida del nivel 5.
- **Pruebas:** casos 41 a 46.
- **Aceptación:** la suite pasa; para cada agente modificable con alias y cada nivel de 1 a 4, el
  `model:` y el `effort:` escritos son los de la celda de su rol; con los nueve alias no queda ningún
  `agents/<rol>.md` ni ningún nombre de rol en los once textos instalados, salvo las subcadenas
  «escribe», «escriben», «describe», «reescribe» y «sobrescribe»; `auditor`, `shield` y `debugger`
  conservan modelo y `hooks:` con cualquier alias.
- **Dependencias:** T5.
- **Revisa:** `auditor` y `shield`.

#### T7. Cambios de alias, ediciones a mano, `-Force` y huérfanos — tamaño M — revisión de seguridad

- **Objetivo:** demostrar con pruebas la tabla de situaciones de 3.6 y el aviso de 3.7.
- **Archivos:** modificar `tests/test_install.py`, `install.ps1`.
- **Pasos:** pruebas S1 a S12; aviso del huérfano por cambio de nombre; frase añadida al exit 3;
  corregir lo que las pruebas destapen.
- **Nota de huérfanos (E3):** hasta T7 el instalador imprime la nota actual («los instalo una version
  anterior y ya no estan en el manifiesto») también para el huérfano por cambio de nombre, y para ese
  caso es falsa. T7 la **cambia**: se imprime sólo si hay algún huérfano que no es por cambio de
  nombre; el de cambio de nombre lleva el aviso por stderr de 3.7. T7 afirma en los casos 50 y 51 lo
  que el caso 20 dejó sin afirmar (nota y stderr), y revisa el caso 20: si tras el cambio puede
  afirmar la ausencia de la nota, lo hace.
- **Pruebas:** casos 47 a 53.
- **Aceptación:** la suite pasa; cada fila S1 a S12 tiene una prueba; el archivo con el nombre
  anterior nunca se abre para escritura, se respalda ni se borra; ningún archivo ajeno en la ruta de
  un alias se sobrescribe sin `-Force`; ningún cambio de alias o de nivel produce `MODIFICADO` sobre
  un destino intacto con estado válido, salvo S5; ninguna corrida imprime «ya no estan en el
  manifiesto» cuando todos los huérfanos son por cambio de nombre; sin alias, la salida de un
  huérfano clásico es la de hoy.
- **Dependencias:** T6.
- **Revisa:** `auditor` y `shield`.

### Fase D: documentación y cierre

#### T8. Documentación — tamaño M

- **Objetivo:** documentación al día en el mismo cambio. La escribe `scribe`; la sesión principal
  regenera el manifiesto y corre la suite.
- **Archivos:** modificar `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`,
  `install-manifest.json`, `docs/plans/2026-11-19-backlog-configuracion-y-reportes.md`.
  `rules/agentes.md` no cambia (el catálogo no cambia; ver P7).
- **Pasos:**
  - `README.md`: sección «Alias» (formato, reglas V1 a V8 en lenguaje llano, con los nueve nombres
    reservados; `-DryRun`, reinstalar; qué se renombra y qué no; el archivo anterior queda y hay que
    quitarlo a mano; el huérfano se informa una vez; reiniciar sesiones); «Instalación» (línea
    `Alias:`, estado `HUERFANO`, códigos de salida, exit 3); «Límites del instalador» (reemplazo
    textual, no semántico; qué cuenta como letra en el límite de palabra y sus límites reconocidos de
    3.5; **la lista de nombres reservados es cerrada y puede quedarse atrás frente a integrados
    nuevos de Claude Code: comprobar con `/agents` antes de elegir un alias; `output-style-setup` se
    reserva por prudencia, sin verificar**; **un agente propio con el mismo `name:` que un alias: no
    está documentado cuál gana y el rol renombrado podría quedar sin su guarda (P10)**; **(E3) si una
    versión nueva del repositorio añade un agente con el nombre de un alias ya instalado, la
    configuración se rechaza (exit 1) y, tras cambiar el alias, el estado se trata como ausente: lo
    que cambió sale `MODIFICADO` y hace falta `-Force`; el aviso lo dice**; **(E3) el estado admite
    `dest` de 74 caracteres como mucho**; **(P11) laxitud heredada: varios campos del estado y del
    manifiesto aceptan una lista de un elemento en lugar del valor**; bytes con alias fuera del hash
    del manifiesto; esquema 3 ilegible para el instalador anterior; colisiones de 3.9; referencias
    por nombre del usuario; renombrar en caliente no documentado; claves repetidas y `__type`; G1
    pendiente si no se corrió); «Límites del reporte de uso» (un agente con alias sale como
    `(otro agente)`); copia inversa («Dos copias»); «Estructura» y «Pruebas» (conteos de la salida
    real); «Línea de tiempo y avance».
  - `CLAUDE.md`: arquitectura (alias, estado esquema 2 o 3), convenciones (`$AliasRoles`,
    `$ReservedAliases`, `$YamlWords`, el marcador `# Alias:` y `function ConvertTo-AliasBytes` son
    contrato con las pruebas; diccionarios y conjuntos ordinales; `Read-State` exige
    `$ManifestPaths`; `Format-SafeShort` en los mensajes del estado y del manifiesto), no obvios (rol
    frente a ruta de destino; alias primero y nivel después; el límite de palabra trabaja sobre
    ISO-8859-1 y sólo cuenta como letra `[A-Za-z0-9_]` y la pareja `C3` más byte de continuación;
    `$ReservedAliases` es una lista cerrada de nueve que hay que revisar cuando Claude Code añada
    integrados; V8 sólo ve el manifiesto; el tope de 74 de `dest` sale de la regex del alias y una
    prueba los ata; `Get-Prop` desenrolla listas de un elemento y `Get-PropRaw(...).Value` no (P11);
    el texto de `docs/agentes.md` y `rules/agentes.md` se transforma al instalar: una palabra igual a
    un rol en esos archivos se reemplaza; el inventario de `tests/test_aliases.py` falla si aparece
    una forma nueva).
  - `HISTORY.md`, `[Sin publicar]`: «Añadido (alias, Fase 4)».
  - `docs/agentes.md`: apartado «Cambiar el nombre de un agente» y el límite del reporte de uso. **Sin
    usar nombres de rol como ejemplo de alias** en el texto nuevo (se transformarían al instalar):
    usar `<rol>` y `<alias>`. Si cambia el conteo del caso 3, se actualiza en la misma task.
  - Regenerar el manifiesto: `python -B tools/build_manifest.py`.
  - Backlog: estado de la Fase 4 y, si P11 queda con su valor por defecto, la tarea pendiente de
    `Get-Prop` anotada para después de la fase.
- **Pruebas:** suite completa.
- **Aceptación:** la suite pasa, incluidas la sincronía del manifiesto y los casos 3 a 5; ningún
  documento promete ahorro, calidad ni costo; siguen siendo doce archivos gestionados; nada personal;
  `git diff main --stat` no muestra cambios en `agents/`, `rules/agentes.md`, `hooks/`,
  `tools/`, `assets/`, `tests/test_manifest.py` ni `tests/test_brand_agents.py`.
- **Dependencias:** T7.
- **Revisa:** `auditor`.

#### Cierre (lo coordina la sesión principal; cuenta como una unidad)

- **C1. `sentinel`:** suite completa con la salida a la vista; los 61 casos de 3.11 cubiertos.
- **C2. `shield`:** T2 a T7. Aplica: entrada de usuario (`aliases`), escritura de rutas derivadas de
  esa entrada, estado como entrada no confiable. Focos: que ningún alias inyecte una línea, una clave
  o un indicador YAML en el frontmatter; que el bloque `hooks:` no cambie con ningún alias; que una
  ruta con alias no salga de `agents/` ni atraviese un enlace; que un `dest` manipulado no convierta
  un archivo ajeno en `ACTUALIZAR` ni lleve una escritura fuera de la lista permitida; que el archivo
  huérfano nunca se toque; fuga del valor de un alias o del contenido del archivo en mensajes;
  comparaciones no ordinales o con `IgnoreCase`; que el reemplazo no parta una secuencia UTF-8 ni deje
  un archivo que no sea UTF-8 válido; tamaño y carrera sobre la configuración; que lo decidido en P10
  esté documentado tal como se decidió; salida acotada y validación lineal del estado (E3); que la
  laxitud de P11 no abra una doble interpretación de ningún campo.
- **C3. `auditor`** sobre el cambio completo.
- **C4.** Memoria del proyecto actualizada por la sesión principal.
- **V1. Renombrado en caliente (propietario; fuera del conteo):** parte de G1. Sólo si se confirma que
  no hace falta reiniciar, una task aparte cambia el recordatorio.
- **V2. Instalación real (propietario; fuera del conteo; exige G1):** `-DryRun` y ejecución real sobre
  `~/.claude` con un alias, comprobación de la invocación por el alias, quitar a mano el archivo
  huérfano y vuelta atrás.

### 4.5 Unidades y aritmética de la línea de tiempo

La Fase 4 tiene **9 unidades**: T1 a T8 y el cierre. El paso previo, G1, V1 y V2 no cuentan. La
enmienda T1-E es parte de la unidad T1, los pasos de E2 son parte de la unidad T2 y lo fijado por E3
es parte de la unidad T3: no añaden unidades y la tabla no cambia. Con el valor por defecto de P11
tampoco cambia (la corrección de `Get-Prop` queda fuera de la fase).

| Frente | Unidades |
|---|---|
| Datos y configuración | 2 (T1 con T1-E, T2 con E2) |
| Rol y ruta | 2 (T3 con E3, T4) |
| Transformación | 3 (T5, T6, T7) |
| Documentación y cierre | 2 (T8, cierre) |

Con k unidades cerradas: Fase 4 = k ÷ 9. Proyecto completo = (300 + 100 × k ÷ 9) ÷ 5 =
60 + 20 × k ÷ 9. Fases 1 a 3 al 100 %; fase 5 en 0 %. Un cuadro = 10 %; la mitad exacta redondea
hacia arriba, y el porcentaje mostrado también.

| k | Fase 4 | Mostrado | Cuadros | Global | Mostrado | Cuadros |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 0 % | 0 % | 0 | 60 % | 60 % | 6 |
| 1 | 11,11 % | 11 % | 1 | 62,22 % | 62 % | 6 |
| 2 | 22,22 % | 22 % | 2 | 64,44 % | 64 % | 6 |
| 3 | 33,33 % | 33 % | 3 | 66,67 % | 67 % | 7 |
| 4 | 44,44 % | 44 % | 4 | 68,89 % | 69 % | 7 |
| 5 | 55,56 % | 56 % | 6 | 71,11 % | 71 % | 7 |
| 6 | 66,67 % | 67 % | 7 | 73,33 % | 73 % | 7 |
| 7 | 77,78 % | 78 % | 8 | 75,56 % | 76 % | 8 |
| 8 | 88,89 % | 89 % | 9 | 77,78 % | 78 % | 8 |
| 9 | 100 % | 100 % | 10 | 80 % | 80 % | 8 |

Por frente: 2 unidades (0, 50, 100 %: 0, 5, 10 cuadros); 3 unidades (0, 33, 67, 100 %: 0, 3, 7, 10
cuadros). Si G1 obliga a rehacer el plan, se añade la task de V1 o el propietario elige la
alternativa de P11 (T3b dentro de la fase: 10 unidades, Fase 4 = k ÷ 10 y global = 60 + 2 × k), las
unidades cambian y se recalcula con la misma fórmula.

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| El nivel no reconoce a un agente con alias y lo deja sin `model:` ni `effort:`, sin error | El rol sigue siendo la clave de `$outBytes` y de la celda (3.3); casos 41 y 48; aceptación de T6 |
| La transformación altera el bloque `hooks:` o el tipo de `name:` | Sólo se tocan `name:`, `description:` y el cuerpo; autocomprobación línea a línea; V1 y V2; referencia independiente; casos 6, 33, 36 y 39; foco de `shield` |
| «scribe» dentro de «escribe», «describe» | Límite de palabra (letra ASCII pegada); casos 3 y 34 |
| Un rol pegado a `«`, `¿` u otra puntuación no ASCII queda sin reemplazar (defecto hallado en T1) | Enmienda E1: sólo `[A-Za-z0-9_]` y la pareja `C3` más continuación cuentan como letra; aserción de residuo en los casos 6 y 42; casos 55 y 56 |
| La expresión del límite difiere entre PowerShell y Python (lookbehind de ancho variable, clases de caracteres) | La misma expresión en los dos, con lookbehind de ancho fijo (3.5); caso 56 compara bytes del instalador con la referencia |
| Un rol pegado a una letra de fuera de U+00C0 a U+00FF se reemplaza; pegado a `×` o `÷` no | Límites reconocidos y documentados; el caso 5 vigila que no haya ninguno en el repositorio |
| Reemplazos en cadena (un alias contiene otro nombre) | Una sola pasada; V5 y V7; diccionario ordinal |
| Un `@{}` de PowerShell o un `-replace` sin `c` mezcla las tres formas | Diccionario ordinal y expresiones sin `IgnoreCase` exigidos en 3.5; caso 34 |
| El reemplazo textual cambia una palabra que no era un agente | Inventario fijado (casos 3 a 5); documentado como límite; aviso en `CLAUDE.md` para quien edite la guía |
| La documentación nueva de la guía nombra roles como ejemplo y se transforma al instalar | Regla en T8 (`<rol>`, `<alias>`); el caso 3 obliga a revisar el conteo |
| Refactor profundo de `install.ps1` rompe la instalación sin alias | T3 y T4 sin cambio de comportamiento, con toda la suite existente intacta; caso 46 |
| Dos formatos de estado (2 y 3) | Difieren en una clave; una sola función los genera; casos 20 a 26 |
| Un instalador anterior no lee el esquema 3 | Lo trata como ausente (nunca sobrescribe sin `-Force`); documentado |
| Un `dest` del estado apunta a la ruta de un archivo del manifiesto (estado manipulado, o un agente nuevo del repositorio con el nombre de un alias) | D5 (E3): estado ausente, nunca `ACTUALIZAR`; caso 59 |
| El repositorio añade un agente con el nombre de un alias ya instalado: el usuario se encuentra exit 1 y después todo `MODIFICADO` | Consecuencia aceptada de D5 (S14); aviso con el motivo y el remedio (3.4); documentado como límite en el README; siempre hay respaldo con `-Force` |
| Un `dest` enorme del estado sale entero por stdout como huérfano | D6 (E3): 74 caracteres, atado por una prueba a la regex del alias; caso 60 |
| La validación del estado es cuadrática y un estado grande bloquea el instalador (304 s con 2000 entradas) | D7 (E3): conjuntos ordinales; caso 61 |
| Un mensaje de `Read-State` o `Get-ManifestEntries` imprime sin recorte texto del archivo | `Format-SafeShort` en todos (E3); casos 25 y 61 |
| El tope de 74 y la longitud del alias se desincronizan | Prueba estática del caso 60 |
| La nota de huérfanos dice «ya no estan en el manifiesto» para un huérfano por cambio de nombre (falso) entre T3 y T7 | Estado intermedio reconocido; el caso 20 no la afirma; T7 la corrige y lo fija (casos 50 y 51); los alias no se pueden activar antes de T5 |
| `Get-Prop` desenrolla listas de un elemento: campos del estado y del manifiesto aceptan `[valor]` (defecto previo de las Fases 1 y 3) | **Abierto (P11).** Por defecto: documentado como laxitud heredada y corregido en una tarea aparte tras la fase; `dest` ya es estricto; foco de `shield` en C2 |
| Archivo viejo activo junto al nuevo | Fila `HUERFANO` y aviso explícito por stderr; README; nunca se borra (decisión 3) |
| El huérfano sólo se informa una vez | Documentado; P5 |
| Archivo ajeno en la ruta del alias | Sale `MODIFICADO` (S2); frase del exit 3 |
| Un alias sobrescribe a un agente integrado de Claude Code o choca con un valor especial de `subagent_type` | V4 con nueve nombres (E2): los siete integrados conocidos, `fork` y `output-style-setup`; casos 13 y 57 |
| La lista de reservados es cerrada: Claude Code añade un integrado y el instalador no lo conoce; `output-style-setup` está reservado sin verificar | Documentado como límite (README, `CLAUDE.md`); consejo de comprobar con `/agents`; añadir un nombre es una línea y una prueba |
| Un alias nombra un archivo del manifiesto que es otro agente, con el rol de origen fuera del manifiesto | V8 compara toda alias efectiva con todas las rutas del manifiesto (E2); caso 58 |
| Otro archivo del usuario en `<Target>/agents/` declara el mismo `name:` que un alias: no está documentado cuál gana; si gana el del usuario, el rol renombrado pierde su `hooks:` sin aviso | P10, resuelta: documentado; G1 lo comprueba en Claude Code real; V8 no lo cubre (sólo ve el manifiesto) |
| Colisión con agente de proyecto, plugin o gestionado; referencias por nombre del usuario | No detectable desde el instalador; documentado (3.9) |
| El reporte de uso deja de atribuir el agente con alias | Decisión 6; documentado en README y guía |
| `name:` con `_`, `-` o dígitos, o el renombrado en caliente, se comportan distinto de lo supuesto | G1; V2 bloqueada hasta G1; recordatorio de reiniciar sesiones |
| Comportamiento de `ConvertFrom-Json` de 5.1 con objetos anidados, claves repetidas y `__type` | Casos 10 y 16 fijan el comportamiento real; lo que no se pueda distinguir falla cerrado |
| Un alias inválido se filtra en un mensaje (inyección en la terminal o en logs) | Los mensajes nombran el rol, nunca el valor; caso 12 |
| La suite se alarga | `subTest`; validación de la tabla sobre todo en Python; el caso 61 usa un solo estado grande |
| Un agente instala contra el `~/.claude` real | Regla en todos los prompts; `-Target` y `HOME` temporales |
| Copia inversa de un archivo con alias al repositorio | Documentado; `git ls-files` no lista `agents/<alias>.md` |

## 6. Preguntas abiertas

Cada una tiene un valor por defecto, que es lo que el plan implementa si no hay respuesta. P1 a P9
quedaron aprobadas con su valor por defecto el 2026-11-22. P10 quedó resuelta el 2026-11-23 con su
valor por defecto (ver «Decisión sobre P10»). **P11 está abierta.**

- **P1. Primera letra obligatoria y palabras de YAML (V1, V2).** Endurece la decisión 4 («sin `-`
  inicial»): el alias debe empezar por letra y no puede ser `true`, `null`, `yes`... Por defecto: sí.
  Alternativa: admitir dígito o `_` inicial y escribir `name:` entre comillas (cambia la forma del
  frontmatter y la regla 3 del renderizado de niveles).
- **P2. Alias que contiene el nombre de un rol (V7).** Por defecto: se rechaza (`dev-sentinel`,
  `forge-2`); a cambio la autocomprobación puede exigir que no quede ninguna forma de un rol con
  alias. Alternativa: admitirlo y quitar esa comprobación.
- **P3. Alias igual al propio rol.** Por defecto: válido y sin efecto. Alternativa: exit 1.
- **P4. Formato del estado.** Por defecto: esquema 2 sin alias y esquema 3 con alias (estado y salida
  idénticos a hoy para quien no configura alias). Alternativa: siempre esquema 3 (un solo formato;
  toda instalación existente crea un respaldo con el estado en la primera reinstalación y cambian las
  aserciones de estado de la suite).
- **P5. Persistencia del aviso de huérfano.** Por defecto: se informa en la corrida que lo deja
  huérfano (y en sus `-DryRun`), como los huérfanos de hoy. Alternativa: guardar en el estado la lista
  de nombres anteriores y avisar en cada instalación mientras el archivo exista (más estado que
  validar).
- **P6. G1.** Por defecto: no bloquea T1 a T8 y sí bloquea aplicar alias al `~/.claude` real.
  Alternativa: bloquea T5.
- **P7. `rules/agentes.md`.** Por defecto: no se toca (el catálogo no cambia). Alternativa: una línea
  que diga que los nombres de la copia instalada pueden ser alias.
- **P8. Rutas en las filas del plan.** Por defecto: la ruta de destino, y la correspondencia en las
  líneas `Alias:`. Alternativa: añadir `(rol <rol>)` a cada fila con alias (cambia el formato que leen
  las pruebas).
- **P9. Nombre de la clave.** Por defecto: `aliases`. Alternativa: `names`.
- **P10. Agente propio del usuario con el mismo `name:` que un alias (resuelta el 2026-11-23:
  opción (a); revisión de `shield` de T2).** V8 sólo ve las rutas del manifiesto. Si el usuario
  tiene en `<Target>/agents/` otro archivo, con otro nombre de archivo, que declara `name: <alias>`,
  el instalador no lo ve. No está documentado cuál de los dos gana; si gana el del usuario, las
  llamadas al alias no pasan por el bloque `hooks:` del rol renombrado. (El caso del archivo
  `agents/<alias>.md` propio ya está resuelto: `MODIFICADO`, S2.)
  - **Por defecto (a), elegida:** documentarlo en el README («Límites del instalador») y en la guía,
    y comprobarlo en G1. Sin código nuevo.
  - **Opcional (b), además de (a):** un aviso por stderr, sin cambiar el código de salida, si algún
    `agents/*.md` no gestionado del destino declara un `name:` igual a un alias efectivo. Coste: el
    instalador pasa a leer archivos que no gestiona (entrada no confiable: tope de tamaño, sólo la
    línea `name:` del frontmatter, sin seguir enlaces, sólo el primer nivel de `agents/`, nunca
    imprime contenido); es heurístico (un `name:` entre comillas o con otra forma no se detecta); sin
    alias no debe leer nada, para que el comportamiento siga idéntico a hoy. Si se elige, el diseño
    vuelve a `atlas` y se implementa en T5.
  - **Alternativa (c):** lo mismo que (b) pero con exit 1 en vez de aviso (falla cerrado; un falso
    positivo bloquea la instalación hasta cambiar el alias).
- **P11. `Get-Prop` desenrolla listas de un elemento (abierta; defecto previo de las Fases 1 y 3,
  descubierto en T3; sin decidir).** `Get-Prop` devuelve el valor de la propiedad por la canalización
  de PowerShell, que desenrolla una lista de un solo elemento. Efecto: aceptan `[valor]` en lugar de
  `valor` los campos `path`, `sha256`, `written`, `level`, `schema`, `algorithm` y `eol` del estado,
  y `schema`, `path`, `sha256` y `algorithm` de `install-manifest.json`.
  - **Qué es y qué no.** No es un hueco conocido: el valor interno pasa las mismas validaciones y se
    lee siempre con la misma función, así que no hay dos lecturas distintas del mismo campo. Sí
    contradice lo que la documentación dice de esos archivos («tipos estrictos»). `dest` (Fase 4) se
    lee con `Get-PropRaw(...).Value` y es estricto (caso 21).
  - **Por defecto:** documentarlo como laxitud heredada (README, «Límites del instalador»;
    `CLAUDE.md`) y corregirlo en una **tarea aparte después de la Fase 4**: usar
    `Get-PropRaw(...).Value` en `Get-ManifestEntries`, `Read-Manifest` y `Read-State`, con la prueba
    roja primero (un estado y un manifiesto con cada campo como lista de un elemento deben
    rechazarse). Las 9 unidades y la tabla de 4.5 no cambian.
  - **Alternativa:** añadirlo como **T3b** dentro de esta fase (tamaño S, revisión de seguridad,
    después de T3 y antes de T4). Las unidades pasan de 9 a 10 y la aritmética cambia: Fase 4 =
    k ÷ 10 y global = 60 + 2 × k; la tabla de 4.5 se rehace y el README se recalcula (el porcentaje
    baja: es lo esperado). Riesgo: toca la lectura del manifiesto de la Fase 1, con su suite.

## Enmiendas

### E1. Límite de palabra — incorporada tras T1 (2026-11-22)

- **Defecto.** La regla original de 3.5 contaba como letra todo byte de 0x80 a 0xFF del texto
  decodificado en ISO-8859-1. Lo halló `forge` al implementar T1: en `docs/agentes.md`,
  `«SENTINEL sólo escribe tests»` y `«AUDITOR, SHIELD y…` llevan el rol pegado a `«` (UTF-8 `C2 AB`),
  así que `SENTINEL` y `AUDITOR` no se reemplazaban. La copia instalada habría conservado dos nombres
  de rol, contra la aceptación de T6 («ningún nombre de rol en los once textos instalados») y el caso
  42.
- **Decisión.** Letra = `[A-Za-z0-9_]` o la pareja `\xC3[\x80-\xBF]` (U+00C0 a U+00FF en UTF-8). Todo
  lo demás es límite, incluidos `«` `»` `¿` `¡`, las comillas tipográficas, las rayas y el espacio
  duro.
- **Qué cambió en este plan.** Supuestos 5 y 10; 3.5 (regla, expresión para PowerShell 5.1 y para
  Python con lookbehind de ancho fijo, límites reconocidos, filas nuevas de casos límite, residuo de
  la autocomprobación); 3.11 (fixture `ALIAS_SAMPLE`; casos 3, 5, 6, 34, 40 y 42; casos nuevos 55 y
  56); tarea T1-E; pasos, pruebas y aceptación de T5; aceptación de T6; pasos de T8; foco nuevo de
  `shield` en C2; C1 pasa de 54 a 56 casos; tres filas de riesgos.
- **Qué no cambió.** Las decisiones del propietario, la validación de la tabla (3.2), la separación
  de rol y ruta, el estado, la clasificación, los huérfanos, el número de unidades (9) y la tabla de
  la línea de tiempo. «escribe», «escriben», «describe», «reescribe» y «sobrescribe» siguen sin
  reemplazarse.

### E2. Nombres reservados y alcance de V8 — aprobada tras T2 (2026-11-23)

Salió de la revisión de T2 por `auditor` y `shield`. Toca dos puntos que estaban marcados «no se
reabren»; por eso queda registrada con su motivo.

- **Cambio 1: `$ReservedAliases` pasa de siete a nueve nombres** (decisión 4, V4 y bloque de datos de
  3.2). Se añaden:
  - `fork`. Motivo: es un valor especial de `subagent_type` (`subagent_type: "fork"`); la
    documentación lo usa en `Agent(fork)` y aparece en el changelog 2.1.302. No figura como agente
    integrado, pero reservarlo es conservador.
  - `output-style-setup`. Motivo: `shield` recuerda un integrado histórico con ese nombre. `scout` no
    lo encontró en la documentación ni en el changelog 2.1.300 a 2.1.330 y no puede afirmar que nunca
    existiera. **No verificado**; reservarlo es barato y conservador.
  - Se deja escrito que la lista es **cerrada** y puede quedarse atrás frente a integrados nuevos de
    Claude Code.
- **Cambio 2: V8 compara siempre.** Antes comparaba el destino `agents/<alias>.md` sólo cuando el
  archivo del rol de origen estaba en el manifiesto. Ahora compara el destino de **toda** alias
  efectiva contra **todas** las rutas del manifiesto. Caso que lo motiva: `{"forge":"alfa"}` con un
  manifiesto que trae `agents/alfa.md` y no `agents/forge.md` nombraría un archivo que es otro
  agente. Sólo ocurre con manifiestos hipotéticos (el repositorio trae los nueve roles); con el
  repositorio real la validación es igual de estricta que antes.
- **Qué cambió en este plan.** Cabecera; nota en la decisión 4; supuestos 11 y 12; 3.2 (V4, V8, los
  dos párrafos explicativos, el párrafo del rol ausente del manifiesto y el bloque de datos); orden
  de ejecución de 3.3; nota en los mensajes de 3.8; 3.9 (integrado fuera de la lista; agente propio
  del usuario); 3.10; casos 2, 8 y 13 y casos nuevos 57 y 58; T2 (archivos, pasos de la enmienda,
  pruebas, aceptación, segunda revisión); pasos de T4 (V8 ya no se calcula ahí) y notas de P10 en T4
  y T5; dependencia de T5; punto nuevo de G1; pasos de T8; foco nuevo en C2; C1 pasa de 56 a 58
  casos; cuatro filas de riesgos; pregunta P10.
- **Qué no cambió.** El número de unidades (9), los frentes y la tabla de la línea de tiempo: los
  pasos de E2 son parte de la unidad T2. Los textos de los mensajes de error. Las reglas V1 a V3 y V5
  a V7, la separación de rol y ruta, el estado, la transformación (E1 incluida), la clasificación y
  los huérfanos.
- **Punto anotado entonces y decidido después.** P10: agente propio del usuario con el mismo `name:`
  que un alias. V8 no lo cubre. Resuelta el 2026-11-23 (ver «Decisión sobre P10»).

### E3. Reglas del estado con esquema 3 — aprobada tras T3 (2026-11-23)

Salió de implementar T3 con `auditor` y `shield`. La sección 3.4 no tenía estas reglas.

- **Regla 1 (D5): un `dest` distinto de su `path` no puede ser la ruta de ningún archivo del
  manifiesto (`$ManifestPaths`) ni el `path` de otra entrada del estado.** Motivo: es lo conservador;
  un estado que sitúa un rol en la ruta que hoy es el origen de otro archivo no se puede clasificar
  sin ambigüedad. **Consecuencia aceptada:** si el usuario tenía `sentinel -> tester` y una versión
  nueva del repositorio añade un agente `tester`, el estado se trata como ausente: todo archivo con
  cambios sale `MODIFICADO` y hace falta `-Force`. El aviso debe decirlo con claridad (texto en
  3.4). Se documenta como límite en T8 y en 3.9 (S14).
- **Regla 2 (D6): tope de 74 caracteres para un `dest` distinto de su `path`.** `agents/` (7) + alias
  de 64 + `.md` (3); el 64 sale de la regex del alias (`{0,63}` más la letra inicial). Una prueba ata
  el número a esa regex. Motivo: sin el tope, un `dest` de 200 KB que casa con `$AllowedPattern`
  salía entero por stdout como huérfano.
- **Regla 3 (D7) y mensajes.** La validación de `dest` usa `HashSet` ordinal: la versión cuadrática
  con listas tardaba 304 s con 2000 entradas. Todos los mensajes de `Read-State` y
  `Get-ManifestEntries` usan `Format-SafeShort`. `$dests` y `$prevByDest` son diccionarios ordinales.
- **Regla 4.** `Read-State` recibe `$ManifestPaths` de forma obligatoria (lo necesita D5).
- **Regla 5 (caso 20 y nota de huérfanos).** El caso 20 ya no afirma la nota de huérfanos ni que
  stderr esté vacío para el huérfano por cambio de nombre. El aviso de 3.7 lo define y lo implementa
  T7, que además cambia la nota actual: para ese caso es falsa («ya no estan en el manifiesto»).
- **Defecto previo registrado, sin decidir (P11).** `Get-Prop` desenrolla listas de un elemento:
  `path`, `sha256`, `written`, `level`, `schema`, `algorithm` y `eol` del estado, y `schema`, `path`,
  `sha256` y `algorithm` de `install-manifest.json`, aceptan `[valor]` en lugar de `valor`. No es un
  hueco (el valor interno se valida igual y se lee siempre con la misma función), pero contradice
  «tipos estrictos». `dest` se lee con `Get-PropRaw(...).Value` y es estricto. Valor por defecto:
  documentarlo y corregirlo en una tarea aparte tras la Fase 4. Alternativa: T3b dentro de la fase
  (10 unidades).
- **Qué cambió en este plan.** Cabecera; fuera de alcance; supuesto 13; fila del Paso 3 en la tabla
  de 3.3; 3.4 (parámetro obligatorio, tabla de reglas D1 a D7, motivos, consecuencia aceptada y texto
  del aviso, reglas de implementación, laxitud heredada); 3.6 (diccionario ordinal, situación S14);
  3.7 (estado intermedio de la nota, cambio en T7, ruta acotada); 3.8 (mensajes del estado); 3.9
  (límite nuevo; P10 como resuelta); 3.10; casos 20, 21, 25, 50 y 51 y casos nuevos 59, 60 y 61; T3
  (lo fijado, pruebas, aceptación); T4 (coherencia con D1 a D7, aceptación); T5 (sin dependencia de
  P10); T7 (nota de huérfanos, aceptación); T8 (límites nuevos, `CLAUDE.md`, backlog); C2; C1 pasa de
  58 a 61 casos; ocho filas de riesgos; pregunta P11.
- **Qué no cambió.** El número de unidades (9), los frentes y la tabla de la línea de tiempo: lo
  fijado por E3 es parte de la unidad T3. Las decisiones del propietario, la validación de la tabla
  (3.2, E2 incluida), la transformación (E1 incluida), la elección del esquema 2 o 3 al escribir, la
  regla de clasificación y la regla única de huérfanos.

## Decisión sobre P10 (2026-11-23, propietario)

P10 se resuelve con el valor por defecto: **documentarlo y comprobarlo en G1, sin código nuevo.** Un agente propio del usuario en `<Target>/agents/` que declare el mismo `name:` que un alias no se detecta ni se avisa; se documenta como límite en T8 (README, «Límites del instalador» y la guía) y se añade como caso a la compuerta G1 del propietario (dos archivos del mismo ámbito con el mismo `name:` y cuerpos distintos, uno con `hooks:`: ver cuál carga y si el rol renombrado conserva su bloque `hooks:`). T5 no añade comprobación. Las 9 unidades no cambian y T5 ya no depende de una decisión pendiente. Si G1 mostrara que el agente del usuario puede ganar, el diseño vuelve a `atlas` antes de aplicar alias a un `~/.claude` real.

## Decisión sobre P11 (2026-11-23, propietario)

P11 se resuelve con el valor por defecto: **tarea aparte después de la Fase 4.** El desenrollado de listas de un elemento de `Get-Prop` (`path`, `sha256`, `written`, `level`, `schema`, `algorithm` y `eol` del estado; `schema`, `path`, `sha256` y `algorithm` de `install-manifest.json`) se documenta como laxitud heredada de las Fases 1 y 3 (no es un hueco: el valor interno se valida igual y se lee siempre con la misma función) y se corregirá luego con `Get-PropRaw(...).Value` en `Get-ManifestEntries`, `Read-Manifest` y `Read-State`, con prueba roja primero. La Fase 4 sigue con 9 unidades. T8 lo documenta en el README («Límites del instalador»).
