# Historial

## [Sin publicar]

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
