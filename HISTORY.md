# Historial

## [Sin publicar]

### Planificado (Fase 5)

Plan `docs/plans/2026-11-24-fase5-configuraciones-dinamicas.md`, aprobado por el propietario el 2026-11-24
con los valores por defecto de P1 a P14; rama `feat/configuraciones-dinamicas`. 9 unidades (T1 a T8 y el
cierre), 7 cerradas (T1 a T7, ver más abajo); la carpeta de planes se lee, se valida y se aplica al instalar, y
el reporte de uso sale en español o en inglés con `--lang`.

- Candidatas que entran: carpeta de planes configurable (clave `plans_dir` de `synclayer-config.json`,
  aplicada al instalar; sin la clave, bytes y salida idénticos a los de hoy); idioma del reporte de uso
  (`es` por defecto, `en`, con el parámetro `--lang`); perfiles por proyecto, sólo documentación
  (`.claude/agents/` y `permissions.deny` con `Agent(<nombre>)`; lo no documentado por Claude Code se
  escribe como no verificado).
- Convención de commits: descartada de la carpeta de planes, porque nada del repositorio la lee ni la hace
  cumplir (sería una opción sin efecto); queda en el `CLAUDE.md` de cada proyecto.
- Candidatas descartadas: (a) activar o desactivar agentes por usuario: las pruebas fijan nueve agentes y
  doce archivos, y habría que redefinir manifiesto, catálogos y flujos; se ofrece `permissions.deny`. (b)
  `tools:` por agente: el mínimo seguro depende del rol y no hay transformación de esa línea; se ofrece
  editarla a mano o un agente de proyecto. (e) estrictez de la guarda: exige transformar el bloque `hooks:`,
  hoy prohibido, y un modo sin guarda contradice la falla cerrada; no se ofrece nada.
- Pendiente del propietario, fuera del conteo: G1 de la Fase 5 (no bloquea), V1 y V2.

### Añadido (Fase 5, T7)

- Documentación de perfiles por proyecto (sin código): sección «Perfiles por proyecto» del `README.md` con una
  tabla de lo documentado por Claude Code (reemplazo por `name:` solo en ese proyecto, prioridad gestionado,
  `--agents`, proyecto, usuario, plugin; `permissions.deny` con `Agent(<nombre>)` o `--disallowedTools`) y de lo
  marcado como no verificado (guarda sin el bloque `hooks:`, alias como nombre a igualar, efecto real de la
  negativa; G1 del propietario). No hay fusión de campos documentada y el nivel no llega a una copia de proyecto.
- «Desactivar un agente» y «Lo que no se configura y por qué» (activar o desactivar por usuario, `tools:` por
  agente, estrictez de la guarda, convención de commits), con su motivo y lo que se ofrece a cambio.
- `docs/agentes.md`: «Adaptar un agente a un proyecto» ampliado (texto con `<nombre>` y `<alias>`). Cambia un
  archivo gestionado: hay que regenerar el manifiesto (`python -B tools/build_manifest.py`). `rules/agentes.md` no
  cambia.
- Pruebas: `tests/test_phase5_docs.py` (13 pruebas, casos 44 a 46). Suite: 1803 pruebas, 367 saltadas (365
  contra pwsh y 2 de la rama POSIX); suite completa: 1803 pruebas, OK, 367 saltadas.

### Añadido (Fase 5, T6)

- Idioma del reporte de uso: `LANGS = ("es", "en")`, catálogo `en` de 137 claves por idioma (mismo juego de claves
  que `es`; traducción fiel, ASCII, sin promesas de ahorro, calidad ni costo). `render_project_report` y
  `render_global_report` aceptan `lang` (por defecto `es`); un valor que no sea la cadena `es` ni `en` lanza
  `ValueError` con mensaje fijo, sin eco.
- `--lang es|en` en `project` y `global` (no en `inspect`), por defecto `es`: `type=` propio, comparación exacta
  (`EN`, `en-US` y vacío dan exit 2 con `idioma invalido: use es o en`, sin repetir el valor), validado antes de leer
  nada; repetido gana el último; con `--stdout` imprime en el idioma pedido; un reporte `en` sustituye al `es` en el
  mismo destino (mismo marcador). Sin `--lang` los bytes son los de antes.
- Etiquetas cerradas del lector traducidas con tablas cerradas por idioma (`_labels`, `_cell`; los nombres de
  conjunto sin paréntesis solo en columnas de conjunto); `_code(text, t=None)` toma sus marcadores de vacío y de no
  cadena del catálogo. No cambian con el idioma: cifras, fechas, orden, marcador, `REPORT_SCHEMA`, claves del pie
  (`report_schema`, `herramienta`, `ultima_version_verificada`, `proyecto`), destinos, nombres del usuario, mensajes
  de la CLI e `inspect` (en español). Lector y agregado sin cambios.
- Pruebas: golden `tests/usage_golden_en.json` (mismos cinco escenarios y receta que el del español),
  `ReportGoldenEn`, `ReportCatalogCoverageEn`, `ReportCatalogEn`, `ReportLang`, `LangOption` (CLI) y
  `LangPrivacyEndToEnd` (bordes). `ReportTextsOutsideCatalog` baja a 7 excepciones (`integrado`, `(no cadena)` y
  `(vacio)` pasan al catálogo). Suite: 1790 pruebas, 367 saltadas (365 contra pwsh y 2 de la rama POSIX).
- Límites: el reporte `en` es traducción; las claves del pie siguen en español; `argparse` repite en stderr los
  argumentos desconocidos (también `inspect --lang X`, ya ocurría antes); `lbl_other_version` no existe porque
  `versions_seen` es numérico. El efecto con un `~/.claude` real no se verificó (V2 del propietario).

### Añadido (Fase 5, T5)

- Catálogo de textos del reporte de uso en `tools/usage_report.py`: `LANGS = ("es",)`, `DEFAULT_LANG = "es"` y
  `CATALOG` inmutable (`MappingProxyType` en dos capas; unas 150 claves por idioma, mismo juego de claves, tuplas
  y marcadores `%d`/`%s`/`%%` con la misma forma). Los 28 generadores internos, de `_legend` a
  `render_global_report`, reciben el catálogo ya resuelto `t` y leen `t["clave"]`. Las constantes de texto del
  módulo (`HOW_TO_READ`, `PRIVACY_NOTES`, `NOTE_*`, `LEGEND_SMALL`, `UNKNOWN_WARNING`, `GLOBAL_*`) quedan como
  alias de compatibilidad. Sin estado global mutable; firmas públicas sin cambio; sin `--lang` ni parámetro
  `lang` (es de T6). El reporte en español no cambia.
- Golden `tests/usage_golden_es.json` (5 escenarios, proyecto y global), generado con la herramienta anterior al
  refactor y comparado byte a byte; se construye con `VERIFIED_MAX` fijado en `2.1.326` mediante `mock.patch`,
  así subir `VERIFIED_MAX` no lo rompe. La receta de regeneración está en `tests/test_usage_report.py`.
- Pruebas nuevas: `ReportGoldenEs`, `ReportCatalog`, `ReportTextsOutsideCatalog` (caso 33, con `ast`: ningún texto
  fijo fuera del catálogo salvo 10 excepciones justificadas), `ReportCatalogCoverage` (paridad entre idiomas,
  toda clave se usa, cada texto cambia algún escenario del golden) y una más. Se modificó una prueba existente
  por necesidad: la lista blanca `ReportPurity.REACHABLE` (cinco nombres quitados; `CATALOG`, `DEFAULT_LANG`,
  `_ES` y `_ES_HOW_TO_READ_COMMON` agregados) y se podaron entradas muertas de `GlobalPurity`.
- Mutaciones: 16 de `forge` y 10 de `auditor` murieron. `auditor`: sin Critical; 2 Important (el golden dependía
  de `VERIFIED_MAX`; documentación de cierre) resueltos; Minor corregidos. `shield`: no aplica (sin entrada de
  usuario nueva; interviene en T6, que agrega `--lang`).
- Pendiente para T6: las etiquetas del lector que van por `_code` (`(otro agente)`, `integrado`, `sin-meta`,
  `WARN_*`, `RANGE_*`, `READ_QUALITY_LABELS`, `OTHER_*`, `(vacio)`/`(no cadena)`) no están en el catálogo y se
  traducirán con tabla cerrada; `REPEAT_LIMITATIONS` y `SKILL_LIMITATIONS` se referencian, no se copian; el
  catálogo `en` debe tener las mismas 17 entradas y el mismo orden en `q_problems`.
- Pruebas: 1735 pruebas, 367 saltadas (365 contra pwsh y 2 de la rama POSIX del reporte de uso); unos 48 minutos.

### Añadido (Fase 5, T4)

- Sólo pruebas: `install.ps1` no cambió. 10 `test_f5t4_*` en `tests/test_install.py` y los helpers `f5t4_repo`,
  `f5t4_state_by_path` y `f5t4_split`.
- Cubren la interacción alias, nivel y carpeta de planes con el repositorio real (nueve alias, niveles 5 y 3,
  ningún nombre de rol residual; las 6 permutaciones del orden alias/planes/nivel contra la salida instalada,
  con `segment_problems` vacío como condición previa), la celda del rol en `model:`/`effort:` y `Ajuste:` con la
  ruta de destino, y `-DryRun` sobre una instalación existente.
- Cambios de carpeta (K1 a K3: agregada, cambiada, quitada): `ACTUALIZAR`, nunca `MODIFICADO` sobre un destino
  intacto, con y sin alias; el repositorio real da 3 `ACTUALIZAR` y 9 `IGUAL`. K4: edición a mano, exit 3 con sus
  frases en orden y `-Force`. K5: estado ilegible, vacío, de esquema 99 o ausente, nunca `ACTUALIZAR`. K6:
  reinstalar lo mismo no cambia nada, ni línea nueva salvo `Planes:`.
- También: alias quitados con carpeta (huérfanos intactos, el estado vuelve al esquema 2) y la configuración
  nunca escrita ni respaldada con alias, nivel y carpeta.
- Mutaciones: 13 de `forge` murieron y `auditor` verificó 4 más. `auditor`: sin Critical ni Important; Minor
  corregidos (constante muerta, caso 17 listaba la carpeta equivocada, rama duplicada, K6 comparado con la salida
  sin `plans_dir`). Abiertos a propósito (Minor, aserciones opcionales): respaldo del estado y de los otros nueve
  archivos en K1 a K3 del repo real, aserto redundante del esquema 2, respaldo del estado ilegible con `-Force`
  final en K5. `shield`: no aplica (sin código de producción; la interacción ya la revisó en T3).
- Pruebas: 10 `test_f5t4_*`. Suite: 1715 pruebas, 367 saltadas (365 contra pwsh y 2 de la rama POSIX del reporte
  de uso).

### Añadido (Fase 5, T3)

- `plans_dir` se APLICA al instalar. Funciones puras con autocomprobación `Get-PlansMatchIndexes`,
  `ConvertTo-PlansText` y `ConvertTo-PlansBytes` reemplazan el literal `docs/plans/` por `<carpeta>/` en
  `agents/atlas.md`, `rules/agentes.md` y `docs/agentes.md`: límite izquierdo (no lo precede ninguno de
  `A-Za-z0-9_./-`) y una sola pasada. Un literal en el frontmatter de un agente da exit 1 (`... referencia a la
  carpeta de planes en el frontmatter. No se escribio nada.`); la función revalida la carpeta con el motivo fijo
  `la carpeta de planes no es valida`.
- Bloque `# Planes:` entre el bucle de `$aliasBytes` y `# Nivel:` (`# Nivel:` sin editar). Orden: alias, planes,
  nivel. Sin carpeta efectiva (sin la clave o `docs/plans`) no se llama a la transformación y bytes y salida son
  idénticos a los de antes. El hook no se transforma; frontmatter y `hooks:` intactos.
- Guarda temporal de T2 retirada. `$verifyWhat` con carpeta efectiva: `lo esperado para el nivel N y la carpeta de
  planes` (con alias, `... N, los alias y la carpeta de planes`). Hash, clasificación y `written` del estado van
  sobre el texto transformado.
- El eco `Planes:` pasa por `Format-Safe` (cierra el Low abierto en T2).
- Límites anotados en «Límites del instalador» del README: reemplazo textual sólo en los tres textos; no mueve ni
  crea carpetas ni toca planes ya escritos ni el `CLAUDE.md` del usuario; la carpeta es por `-Target`; con carpeta
  efectiva la copia inversa `~/.claude` a repo no vale; los bytes con carpeta no los cubre el hash del manifiesto;
  no hay «carpeta anterior» en la salida; un defecto del origen da exit 1 sólo con carpeta efectiva, también en
  `-DryRun`.
- Efecto en un Claude Code real (que `atlas` use la carpeta): NO verificado (G1 del propietario).
- `auditor` y `shield`: sin Critical ni Important de código; Lows y Minors corregidos (comentarios y 4 bordes del
  límite izquierdo en el fixture).
- Pruebas: 37 `test_f5t3_*`. Suite: 1695 pruebas, 357 saltadas (355 contra pwsh y 2 de la rama POSIX del reporte
  de uso).

### Añadido (Fase 5, T2)

- `install.ps1` lee la clave `plans_dir` de `<Target>/synclayer-config.json` en la lectura única de la
  configuración (la lista cerrada de claves de la raíz pasa a `level`, `aliases` y `plans_dir`) y la valida con
  `Get-PlansDirProblem` (L1 a L5: cadena; de una a cuatro carpetas en minúsculas separadas por `/`; hasta 64
  caracteres; sin nombres de dispositivo de Windows; sin nombres de rol). La validación va después de la tabla
  de alias y antes de leer el estado y de escribir: exit 1 también con `-DryRun`. Los mensajes llevan un motivo
  fijo, nunca el valor.
- Línea `Planes: <valor>` sólo si la carpeta efectiva (válida y distinta de `docs/plans`) existe.
- Guarda temporal: con carpeta efectiva, tras `Planes:` sale con exit 1 y `error: la carpeta de planes aun no se
  puede aplicar en esta version. No se escribio nada.` (también en `-DryRun`). La retira T3.
- Sin la clave, o con `docs/plans`, la salida es idéntica a la de antes byte a byte.
- Medido en Windows PowerShell 5.1: con `plans_dir` repetido gana la última, sin aviso; cualquier `__type`,
  también dentro de un valor, da `clave desconocida: __type` (por eso `docs/a__type` se rechaza). Anotado en
  «Límites del instalador» del README, que además gana la sección «Carpeta de planes (`plans_dir`)».
- `auditor` y `shield`: sin Critical ni Important. Abiertos a propósito (Low/Minor): el eco de `Planes:` sin
  `Format-Safe` (el valor ya pasó la regex), la clave repetida sin aviso y dos pruebas que podrían comparar más
  (caso 10, variante sin nivel; caso 17, sin comprobar el exit).
- Pruebas: 22 nuevas (3 estáticas y 19 `test_f5t2_*`). Suite: 1663 pruebas, 342 saltadas (320 de `install.ps1`
  contra pwsh, 19 de la clase contra pwsh de T2 y 3 de la rama POSIX del reporte de uso).

### Añadido (Fase 5, T1)

- `install.ps1` define tres constantes sin uso junto a `$AliasRoles`: `$PlansDirDefault` (`docs/plans`),
  `$PlansDirPattern` (de una a cuatro carpetas en minúsculas separadas por `/`, con `\z`) y
  `$PlansDirMaxLength` (64). El instalador se comporta igual que antes (10 escenarios comparados byte a byte
  con la base).
- `tests/plans_ref.py`: referencia independiente en Python (validación por segmentos, transformación con
  búsqueda manual y autocomprobación, composición con `aliases_ref` y `levels_ref` en cualquier orden, lectura
  de las tres constantes del script, inventario, zonas y comprobación de segmentos `<segmento>/plans/`).
- `tests/test_plans.py`: 43 pruebas (casos 1 a 9 y 31 del plan), sin PowerShell.
- Plan 3.1.4 y caso 8 corregidos: un alias puede crear o destruir el literal `docs/plans/` en general; hoy no
  ocurre en los once textos y el inventario falla si aparece otra forma `<segmento>/plans/`. La conmutación del
  caso 8 vale sólo mientras esa comprobación pase.
- `auditor`: sin Critical; 1 Important de prueba (la aserción de CRLF dependía de `autocrlf`) y 9 Minor,
  corregidos.
- Nada se aplica todavía: no existe la clave `plans_dir` ni la carpeta configurable.
- Pruebas: 1622 pruebas, 323 saltadas (320 de `install.ps1` contra pwsh y 3 de la rama POSIX del reporte de
  uso); las 43 nuevas no tienen duplicado contra pwsh.

### Añadido (alias, Fase 4)

Resumen de la Fase 4 (plan `docs/plans/2026-11-22-fase4-nombres-configurables.md`); el detalle por task sigue
en las entradas T1 a T7 de abajo. Fase cerrada en la rama `feat/nombres-configurables` (T1 a T8 y cierre; ver
la entrada del cierre más abajo). Siguen pendientes del propietario G1/V1 (efecto de los alias en Claude Code
real, caso P10) y V2 (aplicar los alias a su `~/.claude`).

- Cada uno de los nueve agentes puede llevar un alias en la clave `aliases` de
  `<Target>/synclayer-config.json`. Al reinstalar, el instalador escribe el agente en `agents/<alias>.md` con
  `name: <alias>` y reemplaza el nombre del rol por el alias (minúscula, Capitalizada, MAYÚSCULAS y
  `@agent-<rol>`, con límite de palabra) en `description:` y cuerpo de los nueve agentes y en
  `rules/agentes.md` y `docs/agentes.md`. El hook no se transforma y los bloques `hooks:` quedan byte a byte.
  El repositorio conserva los nombres originales. Sin alias, los bytes y la salida son los de siempre.
- La tabla se valida entera antes de escribir (V1 a V8; exit 1, también con `-DryRun`): minúsculas, letra
  inicial, `[a-z0-9_-]` y hasta 64 caracteres; ni palabras de YAML, ni nombres de dispositivo de Windows, ni
  los nueve nombres reservados (los siete integrados, `fork` y `output-style-setup`: lista cerrada), ni el
  rol de otro agente, ni repetidos, ni un rol como palabra, ni una ruta del manifiesto.
- El instalador separa el rol de la ruta de destino; el estado pasa a esquema 3 (`dest` en todas las
  entradas, hasta 74 caracteres) sólo si algún destino difiere del rol, y vuelve a esquema 2 sin alias. El
  archivo con el nombre anterior no se borra: sale `HUERFANO` con un aviso por stderr, una vez.
- Documentación (T8): `README.md` gana la sección «Alias» (formato, reglas, qué se renombra, probar y
  cambiar, tabla de situaciones, qué no está verificado) y actualiza «Instalación» (línea `Alias:`, estado
  `HUERFANO`, esquema 3, exit 1 y frase del exit 3), «Límites del instalador» (reemplazo textual, límite de
  palabra, reservados cerrados, agente propio con el mismo `name:` en el caso P10, colisiones, `dest` de 74,
  laxitud de `Get-Prop` según P11), «Límites del reporte de uso» (un agente con alias sale como
  `(otro agente)`), «Dos copias», «Estructura» y «Pruebas». `CLAUDE.md` suma el contrato con las pruebas y los
  puntos no obvios. `docs/agentes.md` gana «Cambiar el nombre de un agente» sin nombres de rol como ejemplo (se
  transformaría al instalar). El backlog anota el estado de la Fase 4 y la tarea de `Get-Prop` (P11) para
  después de la fase.
- No verificado: con alias reales el efecto en Claude Code real (que se invoque por el alias, `_` y `-` en
  `name:`, el caso de dos archivos con el mismo `name:`, la recarga en caliente) lo comprueba el propietario
  en G1/V1. Ningún documento lo da por probado.
- Pruebas: 1579 pruebas, 323 saltadas (320 de `install.ps1` contra pwsh y 3 de la rama POSIX del reporte de
  uso).

### Corregido

- Prueba frágil `test_no_object_reprs_in_any_output` (reporte de uso): buscaba `0x` suelto y fallaba al azar
  cuando la carpeta temporal contenía `0x`. Ahora busca el patrón de un repr de objeto; se añaden 2 pruebas
  deterministas.
- `com0` y `lpt0` pasan a ser nombres de dispositivo reservados: `$AllowedPattern` de `install.ps1` y `ALLOWED`
  de `tools/build_manifest.py` usan `com[0-9]` y `lpt[0-9]`. Un alias `com0` o `lpt0` da exit 1, y un
  manifiesto con `agents/com0.md` también.

### Añadido (Fase 4, cierre)

- `sentinel`: suite de 1571 pruebas en verde y los 61 casos de la sección 3.11 del plan cubiertos; 4 pruebas
  `test_f4c1_*` nuevas, comprobadas con mutaciones.
- `shield` sobre el cambio completo: sin hallazgos Critical, High ni Medium; 3 Low.
- `auditor` sobre el cambio completo: sin Critical; el Important de los conteos de pruebas, corregido.
- Documentación: el límite del estado (integridad, no autenticidad) cubre también `dest`; las referencias por
  nombre que escribe el usuario incluyen las instrucciones en texto libre; la fila de la tabla de situaciones
  «volver a un nombre anterior» se generaliza.
- No verificado: G1/V1 (efecto de los alias en Claude Code real, caso P10) y V2 (aplicar los alias al
  `~/.claude` del propietario) siguen pendientes.
- Pruebas: 1579 pruebas, 323 saltadas (320 de `install.ps1` contra pwsh y 3 de la rama POSIX del reporte de
  uso).

### Añadido (Fase 4, T7: huérfanos por cambio de nombre y frase extra del exit 3)

- Cada fila `HUERFANO` lleva `RenamedTo`: el destino actual del rol si el rol de la entrada previa sigue en el
  manifiesto; si no, es un huérfano clásico.
- Un huérfano por cambio de nombre da un aviso por stderr, uno por archivo, sólo si el archivo existe
  (`File.Exists`; nunca se abre, respalda ni borra), en `-DryRun` y en ejecución real, sin cambiar el exit code.
- La nota por stdout «ya no están en el manifiesto» sale ahora sólo si hay algún huérfano clásico (texto sin
  cambio).
- Exit 3: se añade «Si el archivo es un agente tuyo con el mismo nombre que un alias, elige otro alias.» sólo si
  algún `MODIFICADO` está en una ruta con alias (destino distinto del `path`), antes de la frase final de
  `model:`/`effort:`, que sigue siempre al final.
- Sin alias la salida es idéntica a la base (comparada byte a byte en 14 escenarios). `synclayer-config.json`
  nunca se escribe ni se respalda.
- Pruebas: 19 `test_f4t7_*` (S1 a S12, casos 50 a 53) y aserciones nuevas en el caso 20 de T3.
- No verificado: con alias reales el efecto en Claude Code real lo comprueba el propietario en G1/V1.
- Pendiente (lo cerró T8): documentación final y límites de alias y frontmatter.
- Pruebas: la suite pasa a 1569 pruebas, 319 saltadas (316 de `install.ps1` contra pwsh y 3 de la rama POSIX del
  reporte de uso).

### Añadido (Fase 4, T6: alias con niveles, repositorio real y `-DryRun`)

- Pruebas de los alias con los niveles, del repositorio real con nueve alias y de `-DryRun` (casos 41 a 46,
  `test_f4t6_*`). Con alias, `model:` y `effort:` salen de la celda del rol, no del destino, y `Ajuste:` lleva la
  ruta de destino.
- Repositorio real con nueve alias en los niveles 5 y 3: 13 archivos (12 gestionados + estado) y ningún nombre de
  rol en los once textos salvo `escribe`, `escriben`, `describe`, `reescribe` y `sobrescribe`. `-DryRun` con alias
  no escribe nada. El hook sale con el hash del manifiesto y los `hooks:` de `sentinel`, `auditor`, `shield` y
  `debugger` quedan intactos. Una verificación posterior alterada da exit 4.
- Caso 46: regresión de la salida del nivel 5 sin alias, idéntica byte a byte a la de antes de la fase (golden
  embebido `F4T6_GOLDEN`, calculado con el instalador anterior a la fase; normaliza las rutas temporales también
  en su forma escapada no ASCII).
- Único cambio de código: `$verifyWhat` con tabla efectiva no vacía dice `lo esperado para el nivel N y los alias`
  (también en el nivel 5: `lo esperado para el nivel 5 y los alias`). Sin tabla efectiva (vacía o alias igual al
  rol) los textos no cambian. Cierra el pendiente de T5.
- Revisiones: `auditor` sin Critical ni Important (Minor y Low corregidos); `shield` sin hallazgos de ninguna
  severidad. Sin alias, la salida es idéntica a la base en 14 a 15 escenarios por revisor.
- No verificado: con alias reales el efecto en Claude Code real lo comprueba el propietario en G1/V1.
- Pendiente (la nota de huérfanos y la frase extra del exit 3 las cerró T7): documentación final y límites de
  alias y frontmatter (T8).
- Pruebas: la suite pasa a 1531 pruebas, 300 saltadas (297 de `install.ps1` contra pwsh y 3 de la rama POSIX del
  reporte de uso).

### Añadido (Fase 4, T5: transformación de textos y activación de los alias)

- `install.ps1` aplica los alias de punta a punta. Funciones puras nuevas con autocomprobación: `New-AliasRegex`,
  `ConvertTo-AliasText`, `Test-AliasDescriptionLine` y `ConvertTo-AliasBytes`. El bloque `# Alias:` calcula
  `$destRel` desde la tabla efectiva y `$aliasBytes` (bytes con alias de los nueve agentes, de
  `rules/agentes.md` y de `docs/agentes.md`); `# Nivel:` parte de `$aliasBytes` y busca la celda por rol. El
  alias nunca entra en la regex (sólo las formas de los roles, escapadas) y rige el límite de palabra E1.
  `hooks/agent_guard.py` no se transforma y los bloques `hooks:` quedan byte a byte.
- Se retiró la guardia temporal de T2 y sus dos pruebas; las pruebas de T2 afines se ajustaron sin debilitarlas.
- Un frontmatter defectuoso con alias da exit 1 en ambos modos (también `-DryRun`), sin escribir nada, y el
  mensaje nombra el rol. Con alias se exige ASCII imprimible en todo el frontmatter y que la línea tras `name:`
  sea `---` o `clave:`. La transformación recorre los nueve agentes aunque sólo uno tenga alias: un defecto en
  uno sin alias también detiene. Un agente sin cuerpo y sin LF final se instala.
- Sin alias efectivo no se llama a la transformación y la salida es idéntica a la base (13 + 11 + 17
  escenarios, 0 diferencias).
- Revisiones: `auditor` sin Critical ni Important (4 Minor corregidos); `shield` sin Critical, High ni Medium
  (Low de frontmatter corregido; Low de `$verifyWhat` queda para T6).
- No verificado: con alias reales activos el efecto en Claude Code real (renombrar un agente, `effort:`, caso
  P10) lo comprueba el propietario en G1/V1.
- Pendiente (`$verifyWhat` lo cerró T6): `$verifyWhat` dice «el manifiesto» con alias en nivel 5; frase extra del exit 3 y aviso de
  huérfano por cambio de nombre (T7); frontmatter y límites de alias documentados en T8. Límite aceptado: con
  clave repetida en la tabla gana la última, sin aviso (heredado de T2).
- Pruebas: casos 32 a 40 y 56 del plan (`test_f4t5_*`). La suite pasa a 1512 pruebas, 291 saltadas (288 de
  `install.ps1` contra pwsh y 3 de la rama POSIX del reporte de uso).

### Añadido (Fase 4, T4: rol separado de la ruta de destino y estado con esquema 3)

- `install.ps1` separa el rol (`$rel`: clave de manifiesto, niveles, `$outBytes` y `$outHash`, mensajes de nivel)
  de la ruta de destino (`$destRel[$rel]`: leer, escribir, respaldar, verificar y clasificar contra
  `prevByDest`) en los Pasos 4 a 9. El bloque `# Alias:` calcula `$destRel`; en producción es siempre
  identidad, porque la guardia temporal de T2 sigue y la retira T5. El ancla `# Alias:` es ahora la línea
  «# Alias: fin del bloque...», tras el cálculo y antes de `Get-DestRelProblem`.
- Función nueva `Get-DestRelProblem` (D1 a D7, defensa en profundidad): exit 1 antes de escribir, también en
  `-DryRun`, y el mensaje nombra el rol, no la ruta. Las filas `HUERFANO` llevan `Path = $null`.
- `ConvertTo-StateBytes` escribe el esquema 2 con identidad y el esquema 3 (`dest` en todas las entradas) si
  algún destino difiere del rol. Con identidad, los bytes de destino, el estado y la salida son idénticos a los
  de la base (comparados en 16 escenarios de `forge` y 17 de `auditor`, 0 diferencias).
- Revisiones: `auditor` sin Critical ni Important (2 Minor corregidos con pruebas); `shield` sin Critical, High
  ni Medium (2 Low aceptados: `$row.Dest` sin `Format-Safe`, hoy no explotable, y un TOCTOU preexistente).
- Pruebas: casos 26 a 31 del plan (`test_f4t4_*`) y 4 pruebas de límite 74/75 y de manifiesto. La suite pasa a
  1479 pruebas, 275 saltadas (272 de `install.ps1` contra pwsh y 3 de la rama POSIX del reporte de uso).

### Añadido (Fase 4, T3: lectura del estado con esquema 3 y huérfanos)

- `install.ps1` lee el estado con esquema 3: cada entrada puede llevar `dest`, la ruta real de destino de ese
  rol (en la Fase 4, `agents/<alias>.md`). Un `dest` distinto de `path` debe ser `agents/<alias>.md` de hasta
  74 caracteres, único y sin coincidir con el `path` de otra entrada ni con una ruta del manifiesto actual; un
  estado con esquema 3 inválido, o con la clave `dest` en esquema 2, se trata como ausente y nunca produce
  `ACTUALIZAR` ni `HUERFANO`. La validación usa `HashSet` ordinales (con listas tardaba 304 s con 2000
  entradas) y todos los mensajes del estado y del manifiesto se recortan con `Format-SafeShort`.
- La clasificación usa `prevByDest` (lo escrito, por ruta de destino) y el huérfano es el destino previo que
  ya no es destino actual. Con estados de esquema 1 y 2 el resultado es idéntico al de antes. El instalador
  todavía escribe el esquema 2 y no aplica alias; ningún camino usa `dest` para escribir, respaldar o borrar.
- Enmienda E3 del plan (aprobada tras T3): las reglas de `dest` (colisión con el manifiesto, tope de 74
  caracteres, validación ordinal) y la situación S14 (el repositorio añade un agente con el nombre de un alias
  ya instalado: el estado se trata como ausente y hace falta `-Force`). Punto abierto P11: `Get-Prop`
  desenrolla listas de un elemento (laxitud heredada de las Fases 1 y 3).
- Pruebas: casos 20 a 25 y 59 a 61 del plan; `tests/aliases_ref.py` gana la referencia independiente del estado
  con esquema 3.

### Añadido (Fase 4, T2: clave `aliases` del archivo de configuración)

- `install.ps1` acepta la clave opcional `aliases` (objeto rol a alias) en `<Target>/synclayer-config.json`,
  junto a `level`; cualquier otra clave sigue dando exit 1. La lectura sigue siendo única y la validación
  de la tabla entera ocurre antes de escribir nada, también en `-DryRun`: el alias va en minúsculas,
  empieza por letra, usa sólo `[a-z0-9_-]` y hasta 64 caracteres; no puede ser una palabra que YAML no lee
  como cadena, un nombre de dispositivo de Windows, un agente integrado de Claude Code (los siete de la
  documentación más `fork` y `output-style-setup`, la lista es cerrada), el rol de otro agente, un alias
  repetido, contener un rol como palabra, formar un ciclo ni coincidir con una ruta del manifiesto. Un alias
  igual al propio rol se descarta sin error. Los mensajes nunca contienen el valor de un alias inválido.
- La salida muestra una línea `Alias: <rol> -> <alias> (agents/<alias>.md)` por alias efectivo. **Guardia
  temporal:** una tabla efectiva válida y no vacía termina con exit 1 («los alias aun no se pueden aplicar
  en esta version») antes de escribir; la retira T5. Sin `aliases`, o con una tabla efectiva vacía, la salida
  y los bytes son idénticos a los de antes.
- Enmienda E2 del plan (aprobada tras T2): `$ReservedAliases` pasa de siete a nueve nombres y V8 compara el
  destino de toda alias efectiva con todas las rutas del manifiesto, esté o no el rol de origen. Punto
  abierto P10: un agente propio del usuario con el mismo `name:` que un alias.
- Pruebas: casos 9 a 19 y 57 y 58 del plan, comparados con la referencia independiente
  `tests/aliases_ref.py`; una prueba de comportamiento fija que la configuración se lee una sola vez.

### Añadido (Fase 4, T1: listas cerradas del alias y referencia independiente)

- `install.ps1` lleva tres listas cerradas para los alias de agentes, todavía sin uso (el instalador se
  comporta igual que antes): `$AliasRoles` (los nueve roles), `$ReservedAliases` (nombres de agentes
  integrados de Claude Code que un alias no puede pisar) y `$YamlWords` (palabras que YAML no lee como
  cadena).
- `tests/aliases_ref.py` es la referencia independiente en Python de lo que el instalador hará con los alias:
  validación de la tabla, las tres formas del nombre (minúscula, Capitalizada, MAYÚSCULAS) y reemplazo en
  una sola pasada con límite de palabra. `tests/test_aliases.py` la prueba y fija el inventario de cada
  rol en los once textos que se instalan.
- Enmienda E1 del plan: al implementar T1 se vio que contar todo byte alto como letra dejaba sin reemplazar
  `SENTINEL` y `AUDITOR` pegados a comillas angulares en `docs/agentes.md`. Ahora una letra es
  `[A-Za-z0-9_]` o una letra latina acentuada real (secuencia UTF-8 `C3 80` a `C3 BF`) y el resto, comillas
  angulares, signos de interrogación, rayas, espacio duro y marcas combinantes, es límite. Límites
  reconocidos: `×` y `÷` cuentan como letra y las letras fuera de U+00C0 a U+00FF son límite.
- Plan y exploración: `docs/plans/2026-11-22-fase4-nombres-configurables.md` y
  `2026-11-22-fase4-nombres-exploracion.md`: la identidad de un subagente es su `name:`; las referencias por
  nombre del usuario (`Agent(nombre)`, `permissions.deny`, matchers de hooks, `--agent`) se romperían al
  renombrar.

### Añadido (Fase 3, cierre: T7)

Estado final de la fase de esfuerzo configurable (plan `docs/plans/2026-11-20-fase3-esfuerzo-configurable.md`).
La documentación (T7) está completa; el cierre (`sentinel`, `shield`, `auditor`) se hizo.

- Niveles 1 a 5 en `<Target>/synclayer-config.json` (campo `level`, sin archivo = 5). El nivel 5 es el
  repositorio; del 1 al 4 el instalador escribe el `model:` y el `effort:` de `atlas`, `forge`, `sentinel`,
  `scribe`, `scout` y `oracle` según la tabla del README. `auditor`, `shield`, `debugger` y el resto quedan
  con los bytes del origen.
- Estado de esquema 2 (hash del origen, hash de lo escrito y nivel por archivo) con migración desde el
  esquema 1; la clasificación compara con lo que se escribiría y con lo ya escrito.
- Renderizado por líneas que falla cerrado ante un frontmatter que no entiende; avisos por `stderr` de las
  dos variables de entorno que anulan el nivel; `Nivel anterior:` y la frase del exit 3; transiciones de
  nivel, ediciones a mano y `-Force` con pruebas.
- Límites documentados en el README («Niveles» y «Límites del instalador»): el hash del manifiesto no cubre
  los bytes renderizados, la sintaxis laxa de PowerShell 5.1, el estado desfasado tras un fallo parcial y
  el efecto real de `effort:` sin verificar. No hay medición de ahorro ni de calidad por nivel.
- Del propietario, pendientes y fuera del conteo: la compuerta G1 (comprobar `effort:` en Claude Code real)
  y V1 (recarga en caliente de los agentes).

### Añadido (Fase 3, T5: cambios de nivel, ediciones a mano y `-Force`)

- Tras `Nivel:`, el instalador imprime `Nivel anterior: M` sólo cuando el estado previo es válido, todas
  sus entradas tienen el mismo nivel M y M es distinto del nivel actual.
- El mensaje del exit 3 (`MODIFICADO` sin `-Force`) termina con la línea `Si cambiaste model: o effort: a
  mano, usa synclayer-config.json.` Se añade siempre que hay exit 3, también cuando el único `MODIFICADO`
  no tiene `model:` (el hook) o cuando se perdió el estado (entonces el arreglo es `-Force`).
- Comportamiento verificado con pruebas (casos 31 a 37 del plan): cambiar de nivel con archivos intactos y
  estado válido es `ACTUALIZAR` (con respaldo de la versión y del estado anteriores), nunca `MODIFICADO`;
  una edición a mano es `MODIFICADO` en cualquier nivel y archivo, también en los fijos, con exit 3 y sin
  escribir nada sin `-Force` (con `-Force` se respalda la versión local); con estado ilegible, ausente o de
  esquema desconocido, lo que coincide con lo esperado es `IGUAL` y lo que difiere `MODIFICADO`, nunca
  `ACTUALIZAR`; un estado de esquema 1 intacto con nivel 3 es `ACTUALIZAR` y migra a esquema 2.
- Límite nuevo: tras un fallo parcial (exit 1 o 4 a mitad de la copia) el estado no se reescribe y queda
  desfasado; si luego se cambia de nivel, los archivos ya copiados salen `MODIFICADO`. Hay que repetir la
  instalación con el mismo nivel antes de cambiarlo; restaurar a mano un estado viejo tiene el mismo
  efecto. Quien puede escribir el estado puede forjar `written` (aceptado por el modelo de amenazas).
- T7 sigue abierta hasta el cierre de la fase.

### Añadido (Fase 3, T4: renderizado y aplicación de los niveles 1 a 4)

- Un nivel de 1 a 4 válido **se aplica**: para `atlas`, `forge`, `sentinel`, `scribe`, `scout` y `oracle`
  el instalador escribe en el destino el `model:` y, según la tabla (`$LevelRows`), el `effort:`.
  `auditor`, `shield`, `debugger`, el hook, `rules/agentes.md`, `docs/agentes.md` y el resto quedan con los
  bytes del origen. El nivel 5 es el repositorio y no se renderiza. La guardia temporal de T3 se retiró.
- La salida muestra `Nivel: N (...)` en todos los niveles y, con 1 a 4, líneas
  `Ajuste: agents/<nombre>.md  model: <modelo>  effort: <esfuerzo>` tras `Resumen:`. Con `-DryRun` muestra
  el plan y no escribe.
- El renderizado falla cerrado: exit 1 antes de escribir (también en `-DryRun`) con
  `error: no se puede aplicar el nivel N a agents/<nombre>.md: <motivo>. No se escribio nada.` si el
  frontmatter del origen de un agente que se renderiza no tiene cierre, no tiene `model:` o lo repite,
  repite `effort:`, trae BOM, empieza por una línea en blanco, tiene un retorno de carro suelto o un
  tabulador, tiene un `model:` que no es un escalar simple o un `effort:` con comentario o continuación,
  tiene `---` con espacios finales o una línea `...`, o falla la autocomprobación estructural. El mismo
  defecto no detiene el nivel 5 ni a un agente fijo.
- La clasificación compara con `outHash` (lo que se escribiría para el nivel) y con `written` (lo que
  escribió la instalación anterior): cambiar de nivel con archivos intactos es `ACTUALIZAR` (con respaldo),
  reinstalar el mismo nivel es `IGUAL` y una edición a mano es `MODIFICADO` (exit 3 sin `-Force`). El estado
  guarda `written` y `level` por archivo. Con el nivel 5 la salida es la de siempre («coinciden con el
  manifiesto»); con 1 a 4, los Pasos 7 y 8 dicen «lo esperado para el nivel N».
- El estado de esquema 1 tiene lista cerrada de claves y `Read-State` lee una sola vez con tope.
- La compuerta G1 (comprobar en Claude Code real que `effort:` se reconoce) no se corrió: T4 se hizo sin
  ella por decisión del propietario. El efecto real de `effort:` y de un valor no soportado sólo está
  verificado por la documentación. No hay medición de ahorro ni de calidad por nivel.
- Lo que T4 dejó pendiente (la línea `Nivel anterior:`, la frase del exit 3 y los casos 31 a 37) lo
  cerró T5, arriba.

### Añadido (niveles, Fase 3)

Resumen parcial de la Fase 3 (esfuerzo configurable por niveles, plan
`docs/plans/2026-11-20-fase3-esfuerzo-configurable.md`). Los niveles 1 a 4 se aplican (T4), sin la
compuerta G1. El detalle está en las entradas por task:

- T1, tabla de niveles de esfuerzo (24 filas, listas cerradas, validada al arrancar; misma tabla en el README).
- T2, estado del instalador con esquema 2 y migración desde el esquema 1.
- T3, lectura y validación de `<Target>/synclayer-config.json` y guardia temporal (retirada en T4).
- T4, renderizado y aplicación de los niveles 1 a 4.
- T5, cambios de nivel, ediciones a mano y `-Force` (`Nivel anterior:`, frase del exit 3, casos 31 a 37).
- T6, avisos de variables de entorno que anulan el nivel (adelantada a T4 y T5).
- T7 (abierta hasta el cierre de la fase), documentación: README (sección «Niveles», estado del
  instalador, límites), CLAUDE.md, `docs/agentes.md`, `rules/agentes.md` y el estado de la fase en el
  backlog.
- Pendiente: el cierre de la fase. No hay medición de ahorro ni de calidad por nivel.

### Añadido (Fase 3, T6: avisos de variables de entorno)

- `install.ps1` avisa por `stderr` cuando el nivel leído es 1 a 4 y el entorno del instalador trae, con
  valor no vacío, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` o `CLAUDE_CODE_EFFORT_LEVEL`, que anulan el `model:` y
  el `effort:` del frontmatter. Sólo imprime el nombre y un texto fijo, nunca el valor; no cambia el código
  de salida, no escribe nada y no define, cambia ni borra variables. Con nivel 5 no añade ninguna línea.
  El aviso va después de leer el nivel y antes de la guardia temporal de T3 (retirada en T4); el aviso sigue
  saliendo.
- T6 se adelantó a T4 y T5 por decisión del propietario (sólo depende de T3 en la práctica); las
  unidades de la fase siguen siendo 8.
- Pruebas: casos 38 y 39 de la Fase 3 y una prueba estática de que el script nunca define ni borra
  variables de entorno. `run_install` quita ambas variables del entorno heredado.
- Para T4: reescribir el comentario de la guardia y retirar `patch_out_guard` de las pruebas. Para T7,
  documentar que el aviso sólo mira el ámbito `Process` (una variable definida con `setx` y sin reiniciar
  la consola no avisa), que una variable de sólo espacios avisa y que `FORCE=0` también avisa aunque
  Claude Code quizá lo trate como inactivo (no verificado).

### Añadido (Fase 3, T3: archivo de configuración del nivel)

- `install.ps1` lee `<Target>/synclayer-config.json` (opcional): un único campo `level`, entero de 1 a 5.
  Sin archivo o con `{}` el nivel es 5. Lectura única con tope de 64 KiB sobre lo leído, UTF-8 estricto,
  rechazo de enlaces, junctions, carpetas y archivos bloqueados, claves de lista cerrada con
  comparaciones ordinales (también se rechaza `__type`, que `ConvertFrom-Json` de 5.1 descartaría en
  silencio). Cualquier problema sale con exit 1 antes de escribir nada, también en `-DryRun`. Ningún valor
  del archivo llega al estado ni al destino salvo el entero validado. El instalador no lo escribe, no lo
  respalda, no lo clasifica ni lo borra.
- La salida muestra `Nivel: N (...)` y el estado guarda el nivel leído. **Guardia temporal (retirada en T4):** un nivel 1 a 4
  válido terminaba con exit 1 («el nivel N aun no se puede aplicar en esta version») hasta que T4 aplique
  la tabla; así ningún commit acepta un nivel que no se escribe.
- Límites conocidos, para documentar en T7: PowerShell 5.1 acepta más que JSON estricto (comillas
  simples, claves sin comillas, `+3`, `03`); con una clave `level` repetida gana la última; entre la
  comprobación de enlaces y la apertura del archivo queda una carrera residual que exige escribir en
  `-Target`; `Format-Safe` no escapa la barra invertida; pwsh 7 no se verificó.
- Pruebas: casos 12 a 19 de la Fase 3 en `tests/test_install.py` y una prueba de la guardia.

### Cambiado (Fase 3, T2: estado del instalador con esquema 2)

- `install.ps1` escribe el estado `<Target>/synclayer-manifest.json` con esquema 2: por archivo, el hash
  del origen (`sha256`), el hash de lo escrito (`written`) y el `level` (hoy siempre 5, así que
  `written` es igual al origen). Lee los esquemas 1 y 2; el 1 se migra al reinstalar y se respalda.
- La clasificación compara el destino con lo que escribió la instalación anterior: igual al origen nuevo
  es `IGUAL`, igual a `written` es `ACTUALIZAR`, cualquier otro caso `MODIFICADO` (exit 3 sin `-Force`).
  Un estado no reconocido (esquema desconocido, hashes mal formados, claves de más, rutas fuera de lista o
  de más de 1 MiB) se trata como ausente y nunca produce `ACTUALIZAR`. Las comparaciones de claves y
  valores del estado son ordinales: un NUL o un guion blando no se confunden con la clave canónica.
- Los bytes de los doce archivos destino no cambian. `Read-Manifest` sigue exigiendo el esquema 1 en
  `install-manifest.json`. `docs/agentes.md` describe el estado nuevo y el manifiesto se regeneró.
- Pruebas: casos 6 a 11 de la Fase 3 en `tests/test_install.py`, las aserciones «estado igual al manifiesto»
  pasan a `assert_state`, y `tests/levels_ref.py` serializa el estado esperado.

### Añadido (Fase 3, T1: tabla de niveles de esfuerzo)

- `install.ps1` lleva la tabla nivel por agente (niveles 1 a 4, 24 filas de `$LevelRows`; el nivel 5
  es el repositorio) con listas cerradas de agentes, modelos y esfuerzos, y la valida al arrancar: una
  tabla rota sale con exit 1 sin escribir nada. Todavía no se usa para escribir: la instalación se
  comporta igual que antes. `auditor`, `shield` y `debugger` no están en la tabla.
- `README.md`: sección «Niveles» con la misma tabla entre marcadores; dice que es un orden razonado, no
  una medición, y no promete ahorro.
- `tests/levels_ref.py` y `tests/test_levels.py` (28 pruebas): igualdad celda por celda entre
  `install.ps1` y el README, reglas R1 a R5, asignación única de las variables de la tabla, validación al
  arrancar con PowerShell y una guarda contra promesas de ahorro reutilizable en la documentación.
- Plan y exploración: `docs/plans/2026-11-20-fase3-esfuerzo-configurable.md` y
  `2026-11-20-fase3-esfuerzo-exploracion.md`. Claude Code ya ofrece `effort:` por subagente con cinco
  niveles; modelo y esfuerzo son palancas distintas.

### Cambiado (reporte de uso, rendimiento C4)

- Lector de transcripciones más rápido sin cambiar la salida (bytes idénticos): buffer de lectura
  de 256 KiB, etiquetas de versión y modelo con caché LRU acotada en entradas (256) y con claves de hasta 64 caracteres, `_parse_ts` y `_token_tuple` sin
  trabajo redundante. En un árbol sintético de 558 MB, `global --all` baja de 18,8 s a 15,1 s (promedio de tres corridas alternadas, 19,7 % menos).
  Pruebas de equivalencia contra la implementación anterior y de tope de trabajo en
  `tests/test_usage_report_perf.py`. El resto del tiempo es lectura y `json.loads`, por byte.

### Añadido (reporte de uso, Fase 2)

- `tools/usage_report.py`: reporte de uso de subagentes a partir de las transcripciones locales
  (`python -B tools/usage_report.py <inspect|project|global>`). Se ejecuta desde el clon; no se
  instala ni lo toca el instalador. Compara llamadas, sesiones, tokens por llamada (mediana y p90),
  duración aproximada, herramientas, modelo real, versión de Claude Code y skills; no mide calidad
  ni costo ni afirma ahorro.
- Subcomandos `project` y `global`: escriben sólo en destinos fijos
  (`<project-dir>/.synclayer/usage-report.md` con `.synclayer/.gitignore` exactamente `*`, y
  `<claude-dir>/synclayer-usage.md`); no existe `--out`. Escritura por temporal aleatorio
  `O_EXCL` en la misma carpeta y `os.replace`, con `lstat` repetido antes del reemplazo, marcador
  leído de forma acotada, modo `0600`, UTF-8 sin BOM con LF y limpieza si algo falla; enlaces,
  junctions y destinos ajenos se rechazan. `--stdout` imprime bytes UTF-8. `--transcripts-dir`
  (repetible) sólo admite nombres de carpeta de `projects/`. Ventana de 30 días UTC, o
  `--since`/`--until`/`--all`. Códigos de salida 0, 1, 2 y 3 (130 con Ctrl+C); el 3 por esquema
  desconocido sale del lector sobre todos los archivos leídos, el 3 por más del 5 % de archivos
  dañados, de la agregación sobre la ventana.
- Privacidad: no copia mensajes, prompts, argumentos, rutas, nombres de carpeta ni
  identificadores de sesión; sí copia nombres de skill escritos por el modelo e ids de modelo que
  pasan listas cerradas o patrones (hasta 64 caracteres por celda). El global numera `proyecto 1..N` (sin hash) y es privado por defecto;
  el de proyecto muestra su alias, recalculable por quien conozca la ruta.
- Avisos de git por stderr (sin llamar a git): el global, si existe `.git` en `<claude-dir>` o una
  carpeta padre; el de proyecto, si el reporte ya está versionado (lee `.git/index`; no detecta el
  índice v4, sparse ni split). El mensaje final no imprime rutas salvo con `--show-paths`.
- Reporte de proyecto con «Carpetas de transcripciones leídas: N».
- `README.md`: secciones «Reporte de uso» y «Límites del reporte de uso» (Windows ACL y OneDrive,
  rama POSIX sin verificar, TOCTOU residual). `docs/agentes.md`: cómo usar el reporte.
- Siguientes: comprobaciones restantes de C4 del propietario y merge a `main`. El hook registrador
  `usage_logger.py` (T9) se retiró de la fase: `SubagentStop` no documenta tokens ni duración
  (consulta de `scout`, decisión en el plan).

### Añadido (Fase 2, T6)

- `tools/usage_report.py`: `render_global_report`, generador puro del reporte global comparativo:
  comparación por conjunto de agentes (SyncLayer, integrado, `plugin:<prefijo>`, otros) con las
  mismas columnas, skills, rangos de versión de Claude Code y sección fija «Qué compara y qué no».
  Los proyectos se numeran `proyecto 1..N` por volumen, sin hash ni alias (un alias sin sal se
  recalcula por diccionario); el prefijo de plugin de una skill sólo sale si coincide con un agente
  visto; los modelos se limitan a tramos de lista cerrada.
- El lector avisa si dos carpetas de proyecto dan el mismo alias.
- `docs/plans/2026-11-19-fase2-reporte-de-uso.md`: decisiones de T6 y los riesgos que T7 debe cubrir.

### Añadido (Fase 2, T5)

- `tools/usage_report.py`: `render_project_report`, generador puro (sin E/S ni reloj) del reporte de
  uso de un proyecto en Markdown: resumen, tablas por agente con columna `Conjunto`, tokens (suma,
  mediana y p90), duración y herramientas, modelo real, conjuntos, skills y versiones de Claude Code
  con el rango 2.1.310 a 2.1.327 marcado como dudoso, calidad de los datos, «Cómo leer estos
  números» y pie de privacidad. Barras de texto, texto en español con tildes, UTF-8 sin BOM.
- `docs/plans/2026-11-19-fase2-reporte-de-uso.md`: notas de la revisión de T5 para T6 y T7.

### Añadido (Fase 2, T4)

- `tools/usage_report.py`: conteo de uso de skills desde la sesión principal y los subagentes (sólo
  `name`, `id` e `input.skill`; nunca `input.args`), con nombres filtrados, conjuntos y agregación pura.
- Identificadores de llamada, sesión y agente con blake2b y clave aleatoria por ejecución; el orden y
  los desempates usan un ordinal de recorrido determinista (`seq`) para que el reporte sea idéntico
  entre ejecuciones.
- `docs/plans/2026-11-19-fase2-reporte-de-uso.md`: `CHK_TS` verificado con datos reales y notas para T5 a T7.

### Añadido (Fase 2, T3)

- `tools/usage_report.py`: agregación pura sin E/S (`aggregate_calls`, `make_window`, `distribution`):
  ventana UTC inclusiva de 30 fechas, mediana y p90 por rango más cercano, desglose de tokens por rango
  de versión de Claude Code (anterior a 2.1.310, 2.1.310 a 2.1.327, desde 2.1.328), repeticiones
  consecutivas inferidas con clave interna por agente, calidad de datos y avisos.
- El lector ya no cuenta como `usable` una llamada con todos sus ids repetidos, deduplica hardlinks
  por inodo dentro de `projects/` y libera los conjuntos de ids al terminar.

### Añadido (Fase 2, T2)

- `tools/usage_report.py`: lector defensivo de subagentes (`read_calls`, `CallRecord`): deduplicación
  por `message.id` dentro y entre archivos, hardlinks de Claude Code aceptados con contador aparte,
  conteos por archivo (un archivo omitido a mitad de lectura no deja líneas contadas), tipo de agente
  por lista cerrada y conjuntos `SyncLayer`, `integrado`, `plugin:<prefijo>`, `otros` y `sin-meta`,
  exit 3 ante esquema desconocido o más del 5 % de archivos dañados.
- `docs/plans/2026-11-19-fase2-reporte-de-uso.md`: notas obligatorias para T3 en adelante.

### Añadido (compuerta G1 de la Fase 2)

- `docs/plans/2026-11-20-fase2-g1-resultado.md`: resultado de correr `inspect` sobre las
  transcripciones reales (sólo conteos): `message.id` repetido (la deduplicación es obligatoria),
  `input.skill` confirmado, enlace `toolUseId` confirmado, totales del resultado presentes en
  sólo 399 de 2 866 llamadas, 122 transcripciones de subagentes con hardlink creados por Claude
  Code y 60 % de las líneas en la ventana de versiones con posible conteo inflado.

### Añadido (exploración de la Fase 2)

- `docs/plans/2026-11-19-fase2-reporte-de-uso-exploracion.md`: qué datos de uso de subagentes
  existen (transcripciones locales, hooks, OpenTelemetry), riesgos (formato interno, privacidad,
  tokens inflados por reintentos), decisiones del propietario (script sobre transcripciones ahora,
  hook después; reportes locales fuera de git; tablas y barras de texto) y lo no verificado.

### Corregido (instalador)

- `test_allowed_pattern_matches_generator` fallaba tras el merge a `main`: git (con
  `core.autocrlf`) deja `install.ps1` en CRLF y la regex anclada a fin de línea no lo toleraba.
  La prueba normaliza CRLF a LF. El instalador no cambió (su hash canónico ya es inmune a CRLF).

### Añadido (instalador)

- `install.ps1` (Windows PowerShell 5.1) con `-Target`, `-BackupDir`, `-DryRun` y `-Force`.
  Copia a `~/.claude/` doce archivos (nueve agentes, `rules/agentes.md`,
  `hooks/agent_guard.py`, `docs/agentes.md`); no instala `docs/brand/`, `assets/`, `tests/` ni
  `tools/`, y nunca borra ni toca archivos ajenos. Códigos de salida: 0 correcto, 1 uso o
  entorno, 2 origen distinto del manifiesto, 3 cambios locales sin `-Force`, 4 fallo al copiar,
  verificar o escribir el estado.
- `install-manifest.json` y `tools/build_manifest.py` (escribe y `--check`): manifiesto con el
  SHA-256 canónico (CRLF convertido a LF) de cada archivo. `tests/test_manifest.py` falla si el
  manifiesto queda desactualizado. El instalador escribe los archivos con LF.
- Clasificación `NUEVO`, `IGUAL`, `ACTUALIZAR`, `MODIFICADO` y `HUERFANO` con el estado
  `<Target>/synclayer-manifest.json`. `MODIFICADO` aborta con exit 3 sin escribir; con
  `-Force` respalda y sobrescribe. Los `HUERFANO` sólo se informan.
- Respaldo verificado en una carpeta nueva (por defecto `<Target>-backup-<yyyyMMdd-HHmmss>`),
  copia atómica con el hook primero (temporal en la misma carpeta y movimiento) y verificación
  posterior.
- Decisiones: un `-Target` que es punto de reanálisis se rechaza; un estado bloqueado o
  ilegible se trata como ausente; `-BackupDir` debe ser nuevo y no estar dentro de `-Target`;
  el mensaje de exit 2 manda a revisar `git status`/`git diff` y sólo a los mantenedores a
  regenerar el manifiesto; un bloqueo o enlace detectado antes de escribir da exit 1 y
  después de escribir, exit 4; la carrera con enlaces no se cierra y se informa con exit 4.
- `tests/test_install.py` y `tests/test_manifest.py`: la suite pasa a 464 pruebas, 109
  saltadas porque pwsh no está instalado.
- `README.md`: «Instalación» con el uso de `install.ps1` y «Límites del instalador» con los
  riesgos residuales (el manifiesto da integridad, no autenticidad; no verificado: pwsh 7,
  volúmenes de red y OneDrive, enlace simbólico de archivo real, corte de energía, Windows 10).
  `CLAUDE.md` con comandos, arquitectura y comportamientos no obvios.
- La copia `~/.claude` -> repo sigue siendo manual y por archivo, ahora limitada a los doce
  archivos gestionados.
- Siguientes (fuera de alcance de esta fase, sin diseñar): comando `status` que compare por
  hash el destino con el manifiesto, y copia inversa `~/.claude` -> repositorio automatizada.

### Añadido (plan y línea de tiempo)

- `README.md`: sección «Línea de tiempo y avance» (avance global, la Fase 1 por frentes, línea
  de tiempo y reglas de mantenimiento) y regla de cierre en `CLAUDE.md`.
- `docs/plans/2026-11-19-backlog-configuracion-y-reportes.md`: backlog sin desglosar de cuatro
  fases (reporte de uso de agentes, esfuerzo configurable de 5 niveles, nombres de agentes
  configurables, otras configuraciones dinámicas), cada una con una exploración previa.

### Añadido (assets de marca)

- `assets/brand/`: símbolo (`symbol-*`, capas `block-top-left`, `block-sync`,
  `block-bottom-left`, `block-bottom-right`), wordmark y lockup horizontal en dark, light,
  mono y mono-reverse; texto a trazados, IBM Plex Sans 600. Variante `symbol-16-*` (rejilla de
  16 px, hueco de 1 px, radio 0).
- Ronda 2: `banner-{dark,light}.svg`, `social-preview.svg` y `.png` (1280×640),
  `agent-catalog-{dark,light}.svg`, `architecture-star-{dark,light}.svg` y tres slides
  (1920×1080, oscuro).
- Generadores en `assets/brand/src/` (`build_brand.py`, `build_round2.py`, `brandlib.py`,
  `fonts_util.py`, `agents_data.py`). Requieren `fontTools` y `uharfbuzz`; las fuentes no se versionan.
  `export_social_png.py` (biblioteca estándar, msedge headless) exporta `social-preview.png`.
- Catálogo, estrella y slide 3 clasifican por herramientas («no Edit/Write», «no Edit/Write ·
  guarded Bash», «writes tests · guarded Bash», «writes: …»), con círculo para quien no tiene
  `Edit`/`Write` y cuadrado para quien escribe (la forma además del color), y la línea «The guard
  is a heuristic, not a sandbox.». Los SVG llevan `<desc>`; slide 3 queda centrada.
- `tests/test_brand_agents.py`: compara los datos de `agents_data.py` con el frontmatter de
  `agents/*.md`.
- `README.md`: banner con `<picture>`, `assets/` en la estructura y nota para subir la social
  preview a mano.

- Ronda 3: lockups apilados `lockup-stacked-{dark,light,mono,mono-reverse}.svg`; `favicon.svg`
  (geometría de 16 px, colores dark/light con `prefers-color-scheme`, sin degradados);
  `favicon-16/32/48.png`, `apple-touch-icon.png` (180×180) y `favicon.ico` (PNG embebidos de 16,
  32 y 48 px) exportados con `export_favicons.py` (msedge headless); hoja de marca
  `brand-sheet-{dark,light}.svg` (1600×1131) con `build_round3.py`.
- `ico.py` (escritor ICO, biblioteca estándar; los bits por píxel salen del tipo de color del IHDR y un PNG truncado da `ValueError`) y `tests/test_ico.py`.
- Favicon: 16 px sin margen; 32 y 48 px con 8 px de margen `bg` por lado (símbolo de 16 px a 1x y 2x). La hoja de marca usa ids únicos (`sym-`, `lk-`, `s16-`, `s24-`, `s32-`).

### Cambiado (assets de marca)

- Comentario de `build_brand.py` corregido (dark, light, mono y mono-reverse) y docs de marca al día
  (SVG finales existentes, wordmark confirmado, 16 px medido). Se documenta cómo exportar
  `social-preview.png`.
- Wordmark confirmado por el propietario (2026-11-19): una palabra, IBM Plex Sans 600.
- Regla de 16 px con medición real: `symbol-16-*` entre 16 y 24 px y para favicon; desde 32 px
  el símbolo original.
- Pendiente: cuestionar el acento `#63D6C4`.

### Cambiado (guarda, auditoría 2026-11-19)

- `sentinel`: el matcher del hook pasa a `Write|Edit|NotebookEdit|Bash`. En `tests-only`,
  el Bash es estricto: sólo comandos simples y escrituras a rutas de pruebas o temporales.
  Tras 6 rondas de revisión (auditor y shield) y 186 pruebas; se documentan los huecos
  confirmados que quedan.
- `tests-only` Write/Edit: una ruta absoluta fuera de `cwd` (o sin `cwd`) sólo vale si es
  temporal; se excluyen `.git`, `.github`, `.claude`, `.vscode`, `.idea`, `.husky`,
  `.venv`, `venv`, `site-packages` y `node_modules`.
- `readonly`: sólo endurecimientos (`builtin`, `cp -l`/`-s`, `find -fprint`, `env`/`sudo`
  con `--chdir`, `git -c`, `hash -p`, `tar`/`unzip`/`7z`, `shred`/`rsync`/`scp`, llaves y
  barras invertidas en rutas). `mktemp` y `tar -O` se permiten con `--allow-temp`.
- El parser emula a bash para `\x` y `$"..."`.

### Cambiado (marca)

- Dirección visual: «Stepped S» se descarta y rige «Modular Grid System» (cuatro bloques en
  rejilla de 8 × 8 u, uno de ellos en acento). Marca aprobada el 2026-11-19.
- Wordmark: «SyncLayer», una palabra, IBM Plex Sans 600; recomendado (confirmado después, ver «assets de marca»).
- Paleta light: `surface-2` `#EAEFF3` y texto blanco sobre el acento, supuestos sin medir.
- Sin cambios: lema, voz, tipografía y el resto de la paleta.
- Pendientes en ese momento: SVG finales, wordmark convertido a trazados y cuestionar el acento.

### Añadido

- `docs/brand/`: estrategia de marca, voz y tono, e identidad visual (paleta dark/light con
  contrastes medidos, tipografía IBM Plex). Sin assets finales todavía.
- Tagline: «One layer. Many specialists.» (reemplaza «One Layer. Multiple Intelligence.»).
- `README.md`: introducción de marca en inglés y enlace a `docs/brand/`.

### Corregido (documentación, auditoría 2026-11-19)

- Se documenta que `sentinel` no tiene guarda sobre `Bash` y que `auditor`, `shield` y
  `debugger` no son de solo lectura real.
- Se documentan los bypasses medidos de `readonly`.
- Se avisa del fallo abierto cuando `python` resuelve al alias de la Microsoft Store y se
  añade cómo comprobarlo.
- La copia `~/.claude` -> repo pasa a ser por archivo (`git ls-files`) para no traer
  archivos ajenos a un repo público.

## 2026-11-19 — Versión inicial

- Nueve agentes en `agents/`: `oracle`, `scout`, `atlas`, `forge`, `sentinel`,
  `auditor`, `shield`, `debugger`, `scribe`.
- Reglas de orquestación en `rules/agentes.md`.
- Guía de uso y mantenimiento en `docs/agentes.md`.
- Hook de seguridad `hooks/agent_guard.py` con 93 pruebas en
  `tests/test_agent_guard.py`. Modos `tests-only` (para `sentinel`) y `readonly
  --allow-temp` (para `auditor`, `shield` y `debugger`).
- `atlas` fijado a `claude-fable-5-2`.
- Tres rondas de revisión del hook por un agente revisor independiente: la primera
  encontró 12 hallazgos y la segunda 8; todos se corrigieron.
- Brechas conocidas del hook: `python -c`, `node -e`, `bash -c`, `eval`, `xargs rm`,
  `cmd /c`, `python -m venv`; sin cubrir `wget -o`/`-a` y `curl -D`/`-c`/`--trace`.
  Si `python` no está en el PATH, el hook falla abierto (exit 127).
