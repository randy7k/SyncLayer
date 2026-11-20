# CLAUDE.md

Guía para trabajar dentro de este repositorio. Qué es y cómo se instala: `README.md`.

## Comandos

```
python -B -m unittest discover -s tests
```

Sólo biblioteca estándar, Python 3.12. Corre siempre Python con `-B` para no generar
`__pycache__`.

Probar la guarda a mano con un payload JSON por stdin (el código de salida es 0 o 2;
el motivo del bloqueo sale por stderr). Construye el payload con Python, no con
comillas a mano:

```
python -B -c "import json; print(json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git add .'}, 'cwd': '.'}))" | python -B hooks/agent_guard.py readonly --allow-temp
```

En Windows con Git Bash, las barras invertidas dentro de un JSON escrito a mano se
rompen con facilidad al citar; por eso conviene generarlo con `json.dumps`.

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

Tres piezas, de la más abstracta a la más concreta:

1. `agents/*.md`: un archivo por agente (nueve). Frontmatter + prompt.
2. `rules/agentes.md`: reglas de orquestación. Forma de estrella: sólo la sesión
   principal delega y pregunta al usuario; los agentes no se delegan entre sí.
3. `hooks/agent_guard.py`: guarda `PreToolUse`, enlazada desde el frontmatter
   (`hooks:`) de `sentinel` (modo `tests-only`) y de `auditor`, `shield` y `debugger`
   (modo `readonly --allow-temp`).

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

- Copia `~/.claude` -> repo sólo por archivo (`git ls-files`), nunca con comodines:
  `~/.claude/hooks/` y otras carpetas tienen archivos ajenos y el repo es público.

## Cierre de un cambio

En el mismo cambio se actualizan `README.md`, `CLAUDE.md` y `HISTORY.md`. Si cambia el
catálogo, la guía `docs/agentes.md` y el catálogo de `rules/agentes.md` también.

Al cerrar una sub-fase del plan en curso (instalador y backlog), actualiza en el mismo
commit la sección «Línea de tiempo y avance» al final de `README.md`: suma la unidad a
«Hecho», recalcula frente, fase y global (un cuadro = 10 %, redondeando al más cercano),
mueve el 🔄 y cambia la fecha. Muestra la aritmética en el resumen del cierre. «Cerrada»
aquí = commiteada en la rama de la fase con la suite verde y `auditor` sin Critical ni
Important. Al desglosar una fase del backlog, «sin desglosar» pasa a sus unidades.
