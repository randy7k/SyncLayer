# Historial

## [Sin publicar]

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
