# Plan y avance de SyncLayer

Detalle de la línea de tiempo y del avance por fase y por frente. El resumen está en la sección «Línea de tiempo y avance» del [README](README.md); los planes de cada fase, en [docs/plans/](docs/plans/).

> **Sección viva.** Se actualiza en el mismo commit que cierra una sub-fase y cada vez que el plan general suma fases. Última actualización: **2026-11-27** (T4 de la Fase 6 cerrada: 4 de 11 unidades; Fase 5 cerrada e integrada en `main`).

## Avance global

**El proyecto completo va en 89%.** Cuenta las seis fases con el mismo peso: (5 fases al 100 % + la fase 6 al 36,4 %) = (5 × 100 + 100 × 4 ÷ 11) ÷ 6 = 536,36 ÷ 6 = 89,39 % → 89 % (9 cuadros: 8,94 redondea a 9). La fase 5 ([plan](docs/plans/2026-11-24-fase5-configuraciones-dinamicas.md)) cuenta 9 de 9 unidades (T1 a T8 y el cierre) = 100 % (10 cuadros). La fase 6 ([plan](docs/plans/2026-11-27-fase6-renombrado-de-agentes.md)) cuenta 0 de 11; con k unidades cerradas el global es (500 + 100 × k ÷ 11) ÷ 6 = 83,33 + 1,515 × k y sólo llega a 100 % al cerrar las once. Siguen pendientes del propietario, fuera del conteo, G1/V1 de las fases 3 y 4 (efecto real de `effort:` y de los alias en Claude Code), G1 de la fase 5, V2 (aplicar los alias a su `~/.claude`), el push y la corrida real C4.

| Fase | Avance | % | Unidades | Estado |
|:--|:--|--:|:--|:--|
| **Proyecto completo** | 🟩🟩🟩🟩🟩🟩🟩🟩🟩⬜ | **89%** | 6 fases, mismo peso | |
| **1. Instalador** | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 7 de 7 | Cerrada en la rama `feat/instalador`; falta el `-DryRun` y la instalación real del propietario y el merge a `main` ([plan](docs/plans/2026-11-19-instalador.md)) |
| **2. Reporte de uso de agentes** | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 9 de 9 | Cerrada en la rama `feat/reporte-de-uso` (T9 retirado). Falta la corrida real C4 del propietario, que no resta, y el merge a `main` ([plan](docs/plans/2026-11-19-fase2-reporte-de-uso.md), [exploración](docs/plans/2026-11-19-fase2-reporte-de-uso-exploracion.md)) |
| **3. Esfuerzo configurable (5 niveles)** | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 8 de 8 | Plan aprobado, cerrada en la rama `feat/esfuerzo-configurable` (T1 a T7 y cierre); la compuerta G1 del propietario sigue pendiente (verificación en Claude Code real; no bloquea) ([plan](docs/plans/2026-11-20-fase3-esfuerzo-configurable.md), [exploración](docs/plans/2026-11-20-fase3-esfuerzo-exploracion.md)) |
| **4. Nombres de agentes configurables** | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 9 de 9 | Plan aprobado, cerrada en la rama `feat/nombres-configurables` (T1 a T8 y cierre); la compuerta G1/V1 del propietario no resta pero sí condiciona aplicar alias a su `~/.claude` real (V2): el efecto de los alias en Claude Code real no está verificado ([plan](docs/plans/2026-11-22-fase4-nombres-configurables.md), [exploración](docs/plans/2026-11-22-fase4-nombres-exploracion.md)) |
| **5. Otras configuraciones dinámicas** | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 9 de 9 | Plan aprobado (2026-11-24, con los valores por defecto de P1 a P14), T1 a T8 y cierre cerradas, en la rama `feat/configuraciones-dinamicas` (cierre: `sentinel` con 1810 pruebas OK y 367 saltadas, `shield` sin Critical, High ni Medium, `auditor` sin Critical ni Important); la compuerta G1 del propietario no bloquea ([plan](docs/plans/2026-11-24-fase5-configuraciones-dinamicas.md), [backlog](docs/plans/2026-11-19-backlog-configuracion-y-reportes.md)) |
| **6. Renombrado de agentes** | 🟩🟩🟩🟩⬜⬜⬜⬜⬜⬜ | **36%** | 4 de 11 | Plan aprobado (2026-11-27, con los valores por defecto de P1 a P16): nombres nuevos como roles, 4 fases (preparación, compatibilidad, cambio atómico, documentación y marca). Arranca al cerrar la Fase 5, en la rama `feat/renombrado-de-agentes`; el efecto en Claude Code real (G1) no bloquea T1 a T10 y sí la aplicación a `~/.claude` ([plan](docs/plans/2026-11-27-fase6-renombrado-de-agentes.md)) |

Cada sub-fase cuenta igual (una unidad). Porcentaje = unidades cerradas ÷ unidades planeadas. «Cerrada» = commiteada en la rama de la fase con su suite verde y la revisión de `auditor` sin hallazgos Critical ni Important; la integración a `main` se hace al cerrar la fase. Lo que falta probar en un entorno real (la instalación sobre el `~/.claude` verdadero) se lista aparte y no resta.

## La Fase 1 por frentes

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

## La Fase 3 por frentes

| Frente | Avance | % | Unidades |
|:--|:--|--:|:--|
| Tabla y estado | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T1, T2) |
| Configuración y renderizado | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 3 de 3 (T3, T4, T5) |
| Avisos | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 1 de 1 (T6) |
| Documentación y cierre | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T7, cierre) |

- **Tabla y estado**
  - ✅ Hecho: T1 tabla nivel por agente como datos en `install.ps1` (validada al arrancar) y en el README, con las pruebas que las mantienen iguales y las reglas R1 a R5.
  - ✅ Hecho también: T2 estado con esquema 2 (hash del origen, hash de lo escrito y nivel por archivo), lectura de los esquemas 1 y 2 con migración, clasificación contra lo escrito y comparaciones ordinales.
  - ⬜ Falta: nada.
- **Configuración y renderizado**
  - ✅ Hecho: T3 lectura y validación de `<Target>/synclayer-config.json` (campo `level` de 1 a 5, ausente o `{}` = nivel 5; lectura única con tope de 64 KiB, rechazo de enlaces, claves de lista cerrada incluido `__type`), línea `Nivel:` y guardia temporal que impide aplicar un nivel 1 a 4.
  - ✅ Hecho también: T4 renderizado y aplicación de los niveles 1 a 4 (sólo `model:` y `effort:` de seis agentes, con valores de lista cerrada; falla cerrado ante un frontmatter que no entiende), clasificación contra lo que se escribiría y lo ya escrito, líneas `Ajuste:` y retirada de la guardia temporal. Se hizo sin la compuerta G1: el efecto real de `effort:` en Claude Code sólo está verificado por documentación.
  - ✅ Hecho también: T5 cambios de nivel, ediciones a mano y `-Force`: la tabla de situaciones tiene prueba (cambio de nivel con archivos intactos es `ACTUALIZAR`, una edición a mano es `MODIFICADO`, estado perdido se trata como ausente), línea `Nivel anterior:` y frase del exit 3.
  - ⬜ Falta: nada.
- **Avisos**
  - ✅ Hecho: T6 (adelantada a T4 y T5 por decisión del propietario) aviso por `stderr` si el nivel es 1 a 4 y el entorno trae `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` o `CLAUDE_CODE_EFFORT_LEVEL`; nunca imprime el valor y con nivel 5 no añade ninguna línea.
  - ⬜ Falta: nada.
- **Documentación y cierre**
  - ✅ Hecho: T7 documentación completa de los niveles (README, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`, `rules/agentes.md`, manifiesto regenerado); cierre: `sentinel` (los 40 casos del plan con prueba y 6 pruebas de borde), `shield` sobre T2 a T6 sin Critical, High ni Medium, `auditor` sobre el cambio completo sin Critical.
  - ⬜ Falta: nada del plan. Fuera del conteo y del propietario: la compuerta G1 (comprobar en Claude Code real que `effort:` se reconoce, con `/tasks`), V1 (recarga en caliente de agentes) y aplicar el instalador nuevo al `~/.claude` real.

## La Fase 4 por frentes

| Frente | Avance | % | Unidades |
|:--|:--|--:|:--|
| Datos y configuración | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T1, T2) |
| Rol y ruta | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T3, T4) |
| Transformación | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 3 de 3 (T5, T6, T7) |
| Documentación y cierre | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T8, cierre) |

- **Datos y configuración**
  - ✅ Hecho: T1 listas cerradas del alias (`$AliasRoles`, `$ReservedAliases`, `$YamlWords`) en `install.ps1`, sin uso todavía, y la referencia independiente en Python (`tests/aliases_ref.py`, `tests/test_aliases.py`) con la regla de límite de palabra enmendada (E1).
  - ✅ Hecho también: T2 clave `aliases` de `synclayer-config.json`: lectura única y validación de la tabla entera antes de escribir (V1 a V8: caracteres, palabras YAML, nombres de dispositivo, agentes integrados y `fork` y `output-style-setup`, duplicados, ciclos, colisión con rutas del manifiesto), y líneas `Alias:` (la guardia temporal que impedía aplicarlos la retiró T5).
  - ⬜ Falta: nada.
- **Rol y ruta**
  - ✅ Hecho: T3 el instalador lee el estado con esquema 3 (campo `dest` validado: ruta `agents/<alias>.md` de hasta 74 caracteres, sin colisión con otra entrada ni con una ruta del manifiesto), clasifica con `prevByDest` e informa como huérfano el destino previo que ya no es destino actual. En T3 todavía escribía el esquema 2 y no aplicaba alias.
  - ✅ Hecho también: T4 el instalador separa el rol (clave de manifiesto, nivel, bytes y hash de salida) de la ruta de destino (leer, escribir, respaldar, verificar y clasificar) en los pasos 4 a 9; valida las rutas de destino antes de escribir (`Get-DestRelProblem`, también en `-DryRun`) y escribe el estado con esquema 3 (`dest` en todas las entradas) sólo si algún destino difiere del rol. Sin alias efectivo el destino es el rol, así que bytes, estado y salida son idénticos a los de antes y el esquema escrito es el 2.
  - ⬜ Falta: nada.
- **Transformación**
  - ✅ Hecho: T5 los alias se aplican de punta a punta: el reemplazo del nombre (con límite de palabra) recorre los nueve agentes, `rules/agentes.md` y `docs/agentes.md`; el hook `agent_guard.py` no se transforma y los bloques `hooks:` quedan byte a byte; el destino sale de la tabla efectiva y el nivel busca su celda por rol; un frontmatter defectuoso con alias da exit 1 antes de escribir, también en `-DryRun`, y se retiró la guardia temporal. Sin alias efectivo la salida es idéntica a la de antes. Con alias reales el efecto en Claude Code real no está verificado (compuerta G1 del propietario).
  - ✅ Hecho también: T6 alias con niveles, repositorio real y `-DryRun` (casos 41 a 46): con alias, `model:` y `effort:` salen de la celda del rol y `Ajuste:` lleva la ruta de destino; el repositorio real con nueve alias en los niveles 5 y 3 escribe 13 archivos (12 gestionados + estado) sin ningún nombre de rol en los once textos salvo `escribe`, `escriben`, `describe`, `reescribe` y `sobrescribe`; `-DryRun` con alias no escribe nada; el hook sale con el hash del manifiesto y los `hooks:` de `sentinel`, `auditor`, `shield` y `debugger` quedan intactos; una verificación posterior alterada da exit 4; la salida del nivel 5 sin alias es idéntica byte a byte a la de antes de la fase (golden embebido). Único cambio de código: con tabla efectiva no vacía, el texto de verificación dice `lo esperado para el nivel N y los alias` (también en el nivel 5). Revisada por `auditor` (sin Critical ni Important) y `shield` (sin hallazgos). Con alias reales el efecto en Claude Code real no está verificado (compuerta G1 del propietario).
  - ✅ Hecho también: T7 huérfanos por cambio de nombre y frase extra del exit 3 (casos 50 a 53): cada fila `HUERFANO` lleva `RenamedTo` (el destino actual del rol si el rol de la entrada previa sigue en el manifiesto; si no, es un huérfano clásico); un huérfano por cambio de nombre da un aviso por `stderr`, uno por archivo, sólo si el archivo existe (nunca se abre, respalda ni borra), también en `-DryRun` y sin cambiar el exit code; la nota por `stdout` «ya no están en el manifiesto» sale sólo si hay un huérfano clásico; el exit 3 añade «Si el archivo es un agente tuyo con el mismo nombre que un alias, elige otro alias.» sólo si algún `MODIFICADO` está en una ruta con alias, antes de la frase final de `model:`/`effort:`. Sin alias la salida es idéntica a la de antes (14 escenarios comparados byte a byte); `synclayer-config.json` nunca se escribe ni se respalda. Con alias reales el efecto en Claude Code real no está verificado (compuerta G1 del propietario).
  - ⬜ Falta: nada.
- **Documentación y cierre**
  - ✅ Hecho: T8 documentación completa de los alias (README: sección «Alias», instalación, límites del instalador y del reporte de uso, estructura y pruebas; `CLAUDE.md`; `HISTORY.md`; `docs/agentes.md`: «Cambiar el nombre de un agente» sin nombres de rol como ejemplo; estado de la Fase 4 y tarea pendiente de `Get-Prop` en el backlog). Sin promesas de ahorro, calidad ni costo; con alias reales el efecto en Claude Code real no está verificado (compuerta G1 del propietario).
  - ✅ Hecho también: cierre. `sentinel`: suite de 1571 pruebas en verde y los 61 casos de 3.11 cubiertos, con 4 pruebas `test_f4c1_*` nuevas comprobadas con mutaciones; `shield` sin Critical, High ni Medium (3 Low); `auditor` sin Critical, con el Important de los conteos corregido. Además `com0` y `lpt0` pasan a nombres de dispositivo reservados y se arregla la prueba frágil `test_no_object_reprs_in_any_output`.
  - ⬜ Falta: nada del plan. Fuera del conteo y del propietario: G1/V1 (efecto de los alias en Claude Code real, caso P10), V2 (aplicar los alias a su `~/.claude`).

## La Fase 5 por frentes

| Frente | Avance | % | Unidades |
|:--|:--|--:|:--|
| Carpeta de planes | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 4 de 4 (T1, T2, T3, T4) |
| Idioma del reporte de uso | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 2 de 2 (T5, T6) |
| Documentación y cierre | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 3 de 3 (T7, T8, cierre) |

- **Carpeta de planes**
  - ✅ Hecho: T1 tres constantes sin uso en `install.ps1` (`$PlansDirDefault`, `$PlansDirPattern`, `$PlansDirMaxLength`), referencia independiente en Python (`tests/plans_ref.py`, que lee esas constantes del script) y 43 pruebas (`tests/test_plans.py`: casos 1 a 9 y 31, sin PowerShell), con una comprobación de inventario que falla si aparece una forma `<segmento>/plans/` distinta de `docs/plans/`. Nada se aplica todavía: el instalador se comporta igual que antes (10 escenarios comparados byte a byte con la base). Revisada por `auditor` sin Critical.
  - ✅ Hecho también: T2 clave `plans_dir` de `synclayer-config.json` (lectura en la lectura única, validación `Get-PlansDirProblem` L1 a L5 después de la tabla de alias y antes del Paso 3, exit 1 también con `-DryRun`, mensajes sin el valor, línea `Planes:` sólo con una carpeta válida distinta de `docs/plans`) y guarda temporal: una carpeta efectiva da exit 1 («la carpeta de planes aun no se puede aplicar en esta version») hasta que T3 la retire. Sin la clave o con `docs/plans` la salida es idéntica a la de antes byte a byte. 22 pruebas nuevas (3 estáticas y 19 `test_f5t2_*`; la suite pasó a 1663 pruebas, 342 saltadas). Revisada por `auditor` y `shield` sin Critical ni Important. Medido en 5.1: con `plans_dir` repetido gana la última y cualquier `__type` da `clave desconocida` (ver «Límites del instalador»).
  - ✅ Hecho también: T3 transformación y activación de la carpeta de planes (`Get-PlansMatchIndexes`, `ConvertTo-PlansText`, `ConvertTo-PlansBytes`: reemplazan `docs/plans/` por `<carpeta>/` en `agents/atlas.md`, `rules/agentes.md` y `docs/agentes.md`, con límite izquierdo y una sola pasada; un literal en el frontmatter da exit 1), bloque `# Planes:` entre los alias y el nivel (orden alias, planes, nivel), guarda temporal retirada, textos de verificación con la carpeta, eco `Planes:` por `Format-Safe`. Sin carpeta efectiva la salida y los bytes son idénticos a los de antes. 37 pruebas `test_f5t3_*`; la suite pasa a 1695 pruebas, 357 saltadas. Revisada por `auditor` y `shield` sin Critical ni Important de código. El efecto en Claude Code real (que `atlas` use la carpeta) no está verificado (G1).
  - ✅ Hecho también: T4 carpeta con alias y niveles, repositorio real y cambios. Sólo pruebas (10 `test_f5t4_*` en `tests/test_install.py`); `install.ps1` no cambió. Cubren la interacción alias, nivel y carpeta con el repositorio real (nueve alias, niveles 5 y 3, sin ningún nombre de rol residual, las 6 permutaciones del orden contra la salida instalada), la celda del rol en `model:`/`effort:` y `Ajuste:` con la ruta de destino, `-DryRun` sobre una instalación existente, carpeta agregada, cambiada y quitada (`ACTUALIZAR`, nunca `MODIFICADO` sobre un destino intacto), edición a mano (exit 3 y `-Force`), estado ilegible, vacío, de esquema 99 o ausente (nunca `ACTUALIZAR`), reinstalar lo mismo, alias quitados con carpeta (huérfanos intactos, estado de vuelta al esquema 2) y la configuración nunca escrita ni respaldada. Revisada por `auditor` sin Critical ni Important; `shield` no aplica (sin código de producción). La suite pasa a 1715 pruebas, 367 saltadas.
  - ⬜ Falta: nada.
- **Idioma del reporte de uso**
  - ✅ Hecho: T5 catálogo de textos con el español sin cambios: `LANGS`, `DEFAULT_LANG` y `CATALOG` inmutable (120 claves por idioma) en `tools/usage_report.py`; los 28 generadores internos reciben el catálogo resuelto y leen `t["clave"]`; las constantes de texto del módulo quedan como alias. Sin `--lang` ni parámetro `lang` todavía. El español es idéntico byte a byte a un golden generado con la herramienta anterior (`tests/usage_golden_es.json`, 5 escenarios, proyecto y global, con `VERIFIED_MAX` fijado en la prueba), con pruebas de catálogo, de paridad de claves y de que ningún texto fijo quede fuera del catálogo; 20 pruebas nuevas, suite de 1735 pruebas, 367 saltadas. Revisada por `auditor` sin Critical (dos Important resueltos); `shield` no aplica (sin entrada de usuario nueva).
  - ✅ Hecho también: T6 idioma `en` y parámetro `--lang`: `LANGS = ("es", "en")`, catálogo `en` de 136 claves (traducción fiel, ASCII, sin promesas de ahorro, calidad ni costo), tablas cerradas por idioma para las etiquetas del lector (`_labels`, `_cell`; `_code` toma los marcadores de vacío y no cadena del catálogo), parámetro `lang` de `render_project_report` y `render_global_report` (`ValueError` fijo sin eco ante un valor que no sea `es` ni `en`), `--lang es|en` en `project` y `global` (no en `inspect`; `type=` propio, exit 2 con `idioma invalido: use es o en`, sin leer nada). Sin `--lang`, los bytes son los de antes (golden `tests/usage_golden_es.json`); golden del inglés en `tests/usage_golden_en.json`. Cifras, fechas, orden, marcador, `REPORT_SCHEMA`, claves del pie, destinos, mensajes de la CLI e `inspect` no cambian. Suite de 1790 pruebas, 367 saltadas. El efecto con un `~/.claude` real no está verificado (V2 del propietario).
  - ⬜ Falta: nada.
- **Documentación y cierre**
  - ✅ Hecho: T7 perfiles por proyecto y descartes (solo documentación): sección «Perfiles por proyecto» del README (tabla con la certeza de cada afirmación, «Desactivar un agente» con `permissions.deny` y `Agent(<nombre>)`, «Lo que no se configura y por qué») y ampliación de «Adaptar un agente a un proyecto» en `docs/agentes.md`. Lo no documentado por Claude Code (guarda sin `hooks:`, alias como nombre a igualar, efecto de `permissions.deny`) va marcado como no verificado (G1).
  - ✅ Hecho también: T8 documentación de la carpeta de planes y del idioma del reporte: `docs/agentes.md` (apartado «Cambiar la carpeta de planes» y viñeta de `--lang`; archivo gestionado, manifiesto regenerado), README (límites del instalador y del reporte, estructura y pruebas), `CLAUDE.md`, `HISTORY.md` y el caso 47 en `tests/test_phase5_docs.py` (20 pruebas en el archivo; suite de 1810 pruebas, 367 saltadas; suite completa en la corrida de cierre de T8). La sección «Carpeta de planes» y `--lang` en la sinopsis y en la tabla ya venían de T3, T5, T6 y T7.
  - ✅ Hecho también: cierre. `sentinel`: suite completa de 1810 pruebas, 367 saltadas, 0 fallos (4536 s) y los 47 casos del plan con prueba; `shield` sin Critical, High ni Medium (2 Low informativos); `auditor` sin Critical ni Important (3 Minor corregidos: 136 claves por idioma, 364 + 3 saltadas, comentarios de `install.ps1`).
  - ⬜ Falta: nada del plan. Fuera del conteo y del propietario: G1 (perfiles, desactivar con `permissions.deny` y carpeta de planes en Claude Code real) y V2 (instalación real con `plans_dir` y una corrida real de `global --lang en --stdout`).

## La Fase 6 por frentes

| Frente | Avance | % | Unidades |
|:--|:--|--:|:--|
| A. Preparación | 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 | **100%** | 4 de 4 (T1, T2, T3, T4) |
| B. Compatibilidad | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | 0 de 2 (T5, T6) |
| C. Cambio atómico | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | 0 de 1 (T7) |
| D. Documentación, marca y cierre | ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ | **0%** | 0 de 4 (T8, T9, T10, cierre) |

- **A. Preparación**
  - ✅ Hecho: T1 referencia del renombrado (`tests/rename_ref.py`, `tests/test_rename.py`, `tests/rename_expected.json`: tabla `RENAME` de ocho pares, once textos gestionados esperados con la transformación de alias y sus hashes canónicos, 34 pruebas de los casos 1 a 6 y 18 parte previa). Sólo pruebas: ningún código de producción ni texto gestionado cambió. Revisada por `auditor` en dos rondas (un Important de CRLF del fixture corregido) sin Critical ni Important abiertos.
  - ✅ Hecho también: T2 `tests/names.py` (única fuente de los nombres de rol, hoy los actuales) y parametrización de las pruebas pequeñas (`test_aliases`, `test_levels`, `test_plans`, `test_manifest`, `test_phase5_docs`, `test_rename`, `test_usage_report`) con los casos 7 y 8 (12 pruebas nuevas; 226 a 238 en los módulos afectados). Sólo `tests/`: sin cambio de comportamiento ni de texto gestionado. Revisada por `auditor` sin Critical ni Important; 5 Minor pasan a T7 (anotados en el plan).
  - ⬜ Falta: T3 y T4 parametrización de `tests/test_install.py`.
- **B. Compatibilidad**
  - ⬜ Falta: T5 nombres anteriores en `install.ps1` (con `shield`); T6 reporte de uso.
- **C. Cambio atómico**
  - ⬜ Falta: T7 renombrado de los archivos y regeneración del manifiesto (con `shield`).
- **D. Documentación, marca y cierre**
  - ⬜ Falta: T8, T9, T10 (assets de marca; necesita la carpeta de fuentes IBM Plex) y cierre. Fuera del conteo y del propietario: G1 (Claude Code real) y V2 (aplicar a `~/.claude`).

## Línea de tiempo

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
| 2026-11-20 | T4 de la Fase 2: conteo de skills (sólo `name`, `id` e `input.skill`; nunca `args`), orden determinista con ordinal de recorrido y claves de identificación aleatorias por ejecución; revisada por `auditor` | ✅ |
| 2026-11-20 | T5 de la Fase 2: generador del reporte de proyecto en Markdown (tablas con barras de texto, aviso del rango de versión dudoso, texto con tildes); revisado por `auditor` | ✅ |
| 2026-11-20 | T6 de la Fase 2: reporte global comparativo (conjuntos de agentes y skills, proyectos numerados sin alias, prefijos de skill limitados); revisado por `auditor` y `shield` | ✅ |
| 2026-11-20 | T7 de la Fase 2: subcomandos `project` y `global` (escritura atómica con temporal aleatorio, rechazo de enlaces, `.gitignore` exacto, avisos de git sin subprocesos, `--stdout` en bytes UTF-8); revisada por `auditor` y `shield` | ✅ |
| 2026-11-20 | T8 de la Fase 2: documentación completa del reporte de uso (README, CLAUDE.md, HISTORY.md, `docs/agentes.md`, manifiesto regenerado); revisada por `auditor` | ✅ |
| 2026-11-20 | Cierre del núcleo de la Fase 2: `sentinel` (22 casos del plan con prueba, 19 pruebas de borde), `shield` sin Critical, High ni Medium, `auditor` sin Critical ni Important; textos de privacidad corregidos | ✅ |
| 2026-11-20 | Corrida C4 parcial del propietario: `project --all` 7 s y `global --all` 2 min 55 s, ambos exit 0 y legibles; lector optimizado (buffer de 256 KiB y etiquetas memoizadas, 19,7 % menos en un árbol sintético) y tiempo aceptado y documentado | ✅ |
| 2026-11-20 | `scout` verifica los hooks de subagentes: `SubagentStop` no documenta tokens ni duración; T9 (hook registrador) se retira de la fase | ✅ |
| 2026-11-20 | Fase 2 integrada en `main` (merge `--no-ff`, 1064 pruebas OK) | ✅ |
| 2026-11-20 | Exploración de la Fase 3: `effort:` existe en el frontmatter con cinco niveles oficiales; plan de 8 unidades y tabla nivel por agente aprobados | ✅ |
| 2026-11-20 | T1 de la Fase 3: tabla nivel por agente como datos en `install.ps1` y en el README, con pruebas de igualdad y de las reglas R1 a R5; revisada por `auditor` | ✅ |
| 2026-11-20 | T2 de la Fase 3: estado con esquema 2 y migración; la clasificación distingue un cambio de origen de una edición manual y un estado no reconocido nunca produce `ACTUALIZAR`; revisada por `auditor` | ✅ |
| 2026-11-20 | T3 de la Fase 3: lectura y validación de `synclayer-config.json` (entrada no confiable, falla cerrado, guardia temporal para niveles 1 a 4); revisada por `auditor` y `shield` | ✅ |
| 2026-11-20 | T6 de la Fase 3 (adelantada): avisos de variables de entorno que anulan el nivel, sin imprimir su valor; revisada por `auditor` y `shield` | ✅ |
| 2026-11-21 | T4 de la Fase 3: renderizado y aplicación de los niveles 1 a 4 (frontmatter de seis agentes, valores de lista cerrada, falla cerrado), guardia temporal retirada; revisada por `auditor` y `shield` en tres rondas; sin la compuerta G1 | ✅ |
| 2026-11-21 | T5 de la Fase 3: cambios de nivel, ediciones a mano y `-Force` (casos 31 a 37 y cada fila de la tabla de situaciones, línea `Nivel anterior:` y frase del exit 3); revisada por `auditor` | ✅ |
| 2026-11-21 | T7 y cierre de la Fase 3: documentación completa de los niveles; `sentinel` (40 casos y 6 pruebas de borde), `shield` sobre T2 a T6 y `auditor` sobre el cambio completo; se cerró además el hueco de las líneas con sangría antes de `model:` | ✅ |
| 2026-11-21 | Fase 3 integrada en `main` (merge `--no-ff`, 1280 pruebas OK) | ✅ |
| 2026-11-22 | Exploración de la Fase 4: la identidad de un agente es su `name:` y las referencias por nombre del usuario se romperían al renombrar; plan de 9 unidades aprobado | ✅ |
| 2026-11-22 | T1 de la Fase 4: listas cerradas del alias en `install.ps1` y referencia independiente en Python con la regla de límite de palabra enmendada (E1: el nombre pegado a comillas angulares se reemplaza); revisada por `auditor` | ✅ |
| 2026-11-23 | T2 de la Fase 4: clave `aliases` de `synclayer-config.json` (lectura única, validación de la tabla entera, líneas `Alias:`, guardia temporal); revisada por `auditor` y `shield`; enmienda E2 (reservados y V8 completa) | ✅ |
| 2026-11-23 | T3 de la Fase 4: lectura del estado con esquema 3, `prevByDest` y huérfanos generalizados (el instalador aún escribe el esquema 2); revisada por `auditor` y `shield`; enmienda E3 | ✅ |
| 2026-11-23 | T4 de la Fase 4: rol separado de la ruta de destino en los pasos 4 a 9, `Get-DestRelProblem` y estado con esquema 3 cuando algún destino difiere (hoy siempre es identidad); revisada por `auditor` y `shield` | ✅ |
| 2026-11-23 | T5 de la Fase 4: transformación de textos y activación de los alias de punta a punta (nueve agentes, `rules/agentes.md` y `docs/agentes.md`; guardia temporal retirada); revisada por `auditor` y `shield`; efecto en Claude Code real sin verificar | ✅ |
| 2026-11-23 | T6 de la Fase 4: alias con niveles, repositorio real con nueve alias en los niveles 5 y 3 y `-DryRun` (casos 41 a 46; regresión byte a byte del nivel 5 sin alias); revisada por `auditor` y `shield`; efecto en Claude Code real sin verificar | ✅ |
| 2026-11-24 | T7 de la Fase 4: huérfanos por cambio de nombre (`RenamedTo`, aviso por `stderr`) y frase extra del exit 3 con alias (casos 50 a 53; sin alias la salida es idéntica a la de antes); efecto en Claude Code real sin verificar | ✅ |
| 2026-11-24 | T8 de la Fase 4: documentación de los alias (sección «Alias» del README, límites del instalador y del reporte de uso, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`, backlog); efecto en Claude Code real sin verificar | ✅ |
| 2026-11-24 | Cierre de la Fase 4: `sentinel` (1571 pruebas, 61 casos de 3.11), `shield` (sin Critical, High ni Medium) y `auditor` (sin Critical) sobre el cambio completo; `com0` y `lpt0` reservados; efecto en Claude Code real sin verificar | ✅ |
| 2026-11-24 | Fase 4 cerrada e integrada en `main` (merge `2565cff`) | ✅ |
| 2026-11-24 | Fase 5 desglosada y aprobada (9 unidades): carpeta de planes, idioma del reporte de uso y perfiles por proyecto (sólo documentación); rama `feat/configuraciones-dinamicas` | ✅ |
| 2026-11-24 | T1 de la Fase 5: constantes de la carpeta de planes sin uso en `install.ps1`, referencia independiente en Python e inventario (casos 1 a 9 y 31; 43 pruebas); el instalador se comporta igual que antes; revisada por `auditor` | ✅ |
| 2026-11-24 | T2 de la Fase 5: clave `plans_dir` (lectura, validación L1 a L5, línea `Planes:`) con guarda temporal que impide aplicarla; sin la clave la salida es idéntica a la de antes; revisada por `auditor` y `shield` | ✅ |
| 2026-11-24 | T3 de la Fase 5: transformación de textos y activación de la carpeta de planes (`plans_dir` se aplica al instalar; guarda temporal retirada; sin la clave la salida es idéntica a la de antes); revisada por `auditor` y `shield`; efecto en Claude Code real sin verificar | ✅ |
| 2026-11-24 | T4 de la Fase 5: carpeta de planes con alias y niveles, repositorio real y cambios (sólo pruebas, 10 `test_f5t4_*`; `install.ps1` no cambió); revisada por `auditor` | ✅ |
| 2026-11-24 | T5 de la Fase 5: catálogo de textos del reporte de uso con el español idéntico byte a byte (golden, 20 pruebas nuevas; sin `--lang` todavía); revisada por `auditor` | ✅ |
| 2026-11-25 | T6 de la Fase 5: idioma `en` del reporte de uso y parámetro `--lang es\|en` en `project` y `global` (sin `--lang`, los bytes no cambian; efecto con un `~/.claude` real sin verificar) | ✅ |
| 2026-11-25 | T7 de la Fase 5: perfiles por proyecto y candidatas descartadas (solo documentación: README y `docs/agentes.md`; lo no documentado por Claude Code va como no verificado) | ✅ |
| 2026-11-25 | T8 de la Fase 5: documentación de la carpeta de planes y del idioma del reporte de uso (README, `CLAUDE.md`, `HISTORY.md`; solo documentación; efecto en Claude Code real sin verificar) | ✅ |
| 2026-11-27 | Cierre de la Fase 5: `sentinel` (1810 pruebas, 47 casos), `shield` (sin Critical, High ni Medium) y `auditor` (sin Critical ni Important) sobre el cambio completo | ✅ |
| 2026-11-27 | Plan de la Fase 6 (renombrado de agentes) aprobado: 11 unidades, nombres nuevos como roles | ✅ |
| 2026-11-27 | Fase 5 integrada en `main` (merge `4da51e1`, sin push) | ✅ |
| 2026-11-27 | T1 de la Fase 6: referencia del renombrado, 34 pruebas y fixture de hashes (sólo pruebas); revisada por `auditor` en dos rondas | ✅ |
| 2026-11-27 | T2 de la Fase 6: `tests/names.py` y parametrización de las pruebas pequeñas (casos 7 y 8; sólo pruebas); revisada por `auditor` | ✅ |
| 2026-11-27 | T3 de la Fase 6: parametrización de `tests/test_install.py`, primera parte (Fases 1 a 3; caso 7 ampliado; sólo pruebas); revisada por `auditor` | ✅ |
| 2026-11-27 | T4 de la Fase 6: parametrización de `tests/test_install.py`, segunda parte (Fases 4 y 5; caso 7 con escaneo completo; sólo pruebas); revisada por `auditor` | ✅ |
| **Ahora** | **T5 de la Fase 6** (nombres viejos en `install.ps1`, con `shield`). **Del propietario:** G1/V1 de las fases 3 y 4 (`effort:` y renombrar con `/tasks`, caso P10), V2 (aplicar los alias a su `~/.claude`), G1 de la fase 5 y las comprobaciones restantes de C4 (`\| head`, BOM, `usage: null`, rutas largas) | 🔄 |
| Luego | Tarea aparte de `Get-Prop` (P11) | ⬜ |

Leyenda: ✅ cerrada · 🔄 en curso · ⬜ pendiente. Las fechas son las del historial de `git`; el detalle está en [HISTORY.md](HISTORY.md).

## Cómo se mantiene

1. **Se cierra una sub-fase:** sumar su unidad a «Hecho», recalcular los porcentajes del frente, de la fase y del proyecto completo, y actualizar la tabla «Avance global» y los cuadros 🟩 (un cuadro = 10 %, redondeando al más cercano). Pasar el hito a ✅ y mover el 🔄 al siguiente.
2. **Se agregan fases o sub-fases al plan general:** sumarlas a «Unidades» y a «Falta» (o crear el frente) y recalcular; el porcentaje baja, y es lo esperado.
3. **Se desglosa una fase del backlog:** pasar «sin desglosar» a sus unidades reales.
4. Actualizar la fecha de «Última actualización».
