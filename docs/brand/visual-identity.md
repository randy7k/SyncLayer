# SyncLayer: visual identity

> Estado: marca de cuatro bloques («Modular Grid System») aprobada el 2026-11-19; «Stepped S» se descartó. Wordmark confirmado por el propietario el 2026-11-19. Este documento especifica; los assets de las Rondas 1, 2 y 3 existen en `assets/brand/` (ver «Assets»).

## Direction: «Modular Grid System»

Minimalista y moderna: bloques, huecos y un nodo de acento. Surge de una exploración en Claude Design, no versionada en este repositorio.

**Direcciones consideradas.** Las tres consideradas antes quedaron descartadas. *Stepped S* (monograma «S» con dos planos desplazados) no gustó. *Strata* (planos apilados) y *Bus* (línea con nodos) se habían apartado antes; el motivo de Strata, «genérica», ya no se sostiene sin matiz: la dirección vigente se le parece en que también se compone de planos rectangulares. La diferencia es que aquí son cuatro bloques coplanares en una rejilla, separados por huecos, con un único bloque de acento. *Bus* se mantiene apartada: refleja la orquestación, pero se pierde a tamaño pequeño, y la estrella de orquestación ya cubre ese papel en diagramas.

**Concept.** Cuatro bloques en una rejilla. Los bloques son la *layer*; el bloque en acento es el *sync*. Los huecos sostienen la forma. No recurre a imaginería de IA.

**Geometry (especificación; los SVG finales ya existen en `assets/brand/`).** Rejilla de 8 × 8 unidades (u); hueco entre bloques 0,4 u; radio de esquina 0,25 u.

| Capa SVG | x | y | Ancho | Alto | Color (token) |
|---|---|---|---|---|---|
| `block-top-left` | 0 | 0 | 5,1 | 3 | `text` |
| `block-sync` | 5,5 | 0 | 2,5 | 3 | `accent` |
| `block-bottom-left` | 0 | 3,4 | 2,5 | 4,6 | `text-3` |
| `block-bottom-right` | 2,9 | 3,4 | 5,1 | 4,6 | `text` |

**Monocromo.** Los cuatro bloques en una sola tinta; los huecos sostienen la forma.

**Wordmark.** «SyncLayer», una palabra, IBM Plex Sans 600 (confirmado el 2026-11-19). La variante de dos pesos (Sync 400 / Layer 600) se evaluó y no se recomienda.

**Small sizes.** Tamaño mínimo 16 px. A 16 px la rejilla da 2 px por u. Medido en Edge headless a escala 1, con píxeles leídos: con la geometría original (hueco 0,4 u = 0,8 px) el hueco ocupa 1 px, pero con cerca del 80 % de fondo (luminancia 61 frente a 17 de fondo y 237 de bloque, en dark): se ve, pero no es nítido. La variante `symbol-16-*` (rejilla de 16 px, hueco de 1 px, radio 0) deja el hueco al 100 % de fondo.

Regla: `symbol-16-*` entre 16 y 24 px y para favicon; desde 32 px basta el símbolo original (hueco de 1,6 px a 32 px y 3,2 px a 64 px). A 32 y 64 px sólo se verificó la geometría, no los píxeles.

**Usage rules.** Espacio libre de 1 u alrededor. Sin degradados, sombras ni contornos. Nunca como patrón repetido. Versión monocroma obligatoria. No combinar con cerebros, robots, circuitos ni destellos.

La estrella de orquestación (sesión al centro, agentes alrededor) se reserva para **diagramas**, no para el logo.

## Color

Los cuatro colores iniciales se conservan; se añaden los necesarios para texto, estados y superficies. Cifras de contraste WCAG 2.x medidas con la fórmula de luminancia relativa.

### Dark (default)

| Token | HEX | Role | Contraste |
|---|---|---|---|
| `--sl-bg` | `#0B1118` | Fondo principal | — |
| `--sl-surface` | `#151F2A` | Tarjetas, bloques | — |
| `--sl-surface-2` | `#1C2936` | Superficie elevada | — |
| `--sl-text` | `#E6EDF3` | Texto primario | 16,05 sobre bg · 14,09 sobre surface |
| `--sl-text-2` | `#A9B6C2` | Texto secundario | 9,17 · 8,05 |
| `--sl-text-3` | `#7D8B99` | Texto atenuado, etiquetas | 5,44 · 4,78 |
| `--sl-accent` | `#63D6C4` | Acento único | 10,79 · 9,47 |
| `--sl-border` | `#2A3A4A` | Bordes decorativos | 1,63 · 1,43 |
| `--sl-ok` | `#4ADE80` | Éxito | 10,88 sobre bg |
| `--sl-warn` | `#F5B84B` | Advertencia | 10,69 |
| `--sl-error` | `#FF7A7A` | Error | 7,51 |
| `--sl-info` | `#7DB4FF` | Información | 8,89 |

### Light (necesario: GitHub muestra el modo claro por defecto)

| Token | HEX | Role | Contraste |
|---|---|---|---|
| `--sl-bg` | `#F6F8FA` | Fondo | — |
| `--sl-surface` | `#FFFFFF` | Tarjetas | — |
| `--sl-surface-2` | `#EAEFF3` | Superficie elevada | supuesto, sin medir |
| `--sl-text` | `#0B1118` | Texto primario | 17,81 sobre bg · 18,96 sobre surface |
| `--sl-text-2` | `#44525F` | Texto secundario | 7,53 · 8,02 |
| `--sl-text-3` | `#5B6874` | Texto atenuado | 5,36 · 5,71 |
| `--sl-accent` | `#0B7A6B` | Acento | 4,92 · 5,24 |
| `--sl-border` | `#D0D9E1` | Bordes decorativos | 1,34 |
| `--sl-ok` / `--sl-warn` / `--sl-error` / `--sl-info` | `#1A7F37` / `#8A5A00` / `#C0362C` / `#1F5FBF` | Estados | 4,77 / 5,57 / 5,18 / 5,72 sobre bg |

### Reglas de color

- El acento ocupa menos del 5 % de una composición o superficie. El símbolo es la excepción: el bloque `block-sync` mide cerca del 13 % del área de los cuatro bloques (7,5 de 57,76 u²). El `#63D6C4` es un teal muy usado en herramientas de desarrollo: la distinción la da el símbolo, no el color. El acento no se cuestionó todavía (2026-11-19).
- Texto sobre el acento (botones): `#0B1118`, contraste 10,79 en dark. En light, texto blanco sobre `#0B7A6B`: supuesto, sin medir.
- **Los bordes no llegan a 3:1.** Sirven de decoración. Si un borde delimita un control interactivo, usar un tono con al menos 3:1 (WCAG 1.4.11).
- Fondo y surface son casi indistintos: separar con borde, no sólo con tono.
- El estado nunca depende sólo del color: acompañarlo de icono o texto.

## Typography

| Uso | Familia | Pesos |
|---|---|---|
| Títulos y texto | **IBM Plex Sans** | 600 títulos, 400 cuerpo, 500 etiquetas |
| Código, rutas, nombres de agentes, etiquetas | **IBM Plex Mono** | 400, 500 |

Escala: 32 / 24 / 20 / 16 / 14 px; cuerpo 16 px con interlineado 1,6; código 14 px.
Títulos en mayúscula inicial, no en versales. Licencia OFL. Fallback: `system-ui` y `ui-monospace`.
Las fuentes sólo aplican a assets, slides y web: el README de GitHub no las carga.
Alternativa si se prefiere algo más neutro: Inter + JetBrains Mono.

## Graphic language

- **Rejilla** de 8 px; espaciados múltiplos de 8 (4 para ajustes finos).
- **Formas:** rectángulos con radio pequeño (4 a 6 px) y ángulos rectos. Sin curvas decorativas.
- **Líneas:** 1 a 1,5 px, color de borde; el acento sólo para un elemento por composición.
- **Capas:** bloques de rejilla separados por huecos.
- **Nodos y conexiones:** estrella con la sesión principal al centro y los agentes alrededor; conexiones rectas, sin flechas decorativas. Es un patrón de diagrama.
- **Iconografía:** trazo uniforme, geometría simple. Sin cerebros, robots ni destellos.
- **Ilustración:** diagramas, no mascotas ni escenas.
- **Superficies:** planas, con borde de 1 px; sin sombras difusas ni degradados.

## Applications

| Pieza | Directriz |
|---|---|
| **README (GitHub)** | Logo con `<picture>` y variantes dark/light; bloque de introducción en inglés; las secciones técnicas no cambian. |
| **Social preview** (1280×640) | Fondo `--sl-bg`, símbolo, nombre y tagline. Zona segura de 40 px. |
| **Documentación** | Mismas fuentes y paleta; bloques de código sobre `--sl-surface`. |
| **Diagramas de arquitectura** | Estrella de orquestación; un color de estado por rol, no uno por agente; etiquetas en Plex Mono. |
| **Catálogo de agentes** | Nueve tarjetas: nombre en IBM Plex Mono, rol en IBM Plex Sans, y modelo, herramientas y etiqueta de clase en Plex Mono. |
| **Sitio web (futuro)** | Sólo si se decide; sin framework. Reutiliza los tokens de este documento. |
| **Slides** | Fondo oscuro, un acento, un mensaje por diapositiva. |

Los colores `color:` del frontmatter de los agentes los define Claude Code y no forman parte de esta paleta.

## Assets

Viven en `assets/brand/`. Los SVG los producen los generadores de `assets/brand/src/` (`build_brand.py`, `build_round2.py`, `build_round3.py`); no se editan a mano. Los PNG y el `.ico` los exporta `export_social_png.py` y `export_favicons.py` (biblioteca estándar, msedge headless). Los generadores requieren `fontTools` y `uharfbuzz` y una carpeta de fuentes IBM Plex (no versionadas); el comando está en `CLAUDE.md`.

**Existen**

- Símbolo `symbol-{dark,light,mono,mono-reverse}.svg`, con las capas `block-top-left`, `block-sync`, `block-bottom-left` y `block-bottom-right`. Variante de 16 px `symbol-16-*`.
- Wordmark `wordmark-*.svg`, lockup horizontal `lockup-horizontal-*.svg` y lockup apilado `lockup-stacked-*.svg` (símbolo arriba, wordmark centrado debajo, 2,4 u de separación hasta las mayúsculas, altura de mayúsculas del wordmark de 3 u): IBM Plex Sans 600, texto a trazados, un solo peso. El viewBox ajusta a la tinta: arriba y abajo es exacto; a los lados quedan los márgenes laterales de la fuente (~0,17 u a la izquierda y ~0,09 u a la derecha) y el wordmark se centra por avance. El espacio libre de 1 u queda fuera.
- Ronda 2:
  - `banner-{dark,light}.svg` (1280×320).
  - `social-preview.svg` y `social-preview.png` (1280×640, margen de 40 px).
  - `agent-catalog-{dark,light}.svg` (nueve tarjetas).
  - `architecture-star-{dark,light}.svg`: sin conexiones entre agentes; acento sólo en la sesión principal.
  - Clasificación por herramientas, no por garantía: sin `Edit`/`Write` en `info` y círculo, escribe en `warn` y cuadrado, de modo que el estado no dependa sólo del color. Aplica al catálogo, la estrella y la slide 3.
  - Línea «The guard is a heuristic, not a sandbox.» en catálogo, estrella y slide 3 (la guarda es heurística, no un sandbox).
  - `slide-1-title.svg`, `slide-2-message.svg`, `slide-3-roster.svg` (1920×1080, oscuro).

- Ronda 3 (producida en local, sin Claude Design):
  - `favicon.svg`: geometría de `symbol-16-*`, un solo archivo con `@media (prefers-color-scheme: dark)`; colores light por defecto, dark bajo la media query; sin degradados. Verificado en Edge: `--blink-settings=preferredColorScheme=0` fuerza dark y `=1` light; sin la bandera sigue al sistema.
  - `favicon-16.png`, `favicon-32.png`, `favicon-48.png` y `favicon.ico` (PNG de 16, 32 y 48 px embebidos): símbolo dark sobre fondo `bg` opaco. Sin fondo, el símbolo dark (tinta clara) se pierde en pestañas claras y el light (tinta oscura) en pestañas oscuras; el tile mantiene visibles los huecos en ambas. Los tres dibujan `symbol-16-dark.svg`: 16 px a 1x, sin margen (el símbolo llena el lienzo); 32 px a 1x y 48 px a 2x, ambos centrados con 8 px de margen `bg` por lado. Medido en los PNG con zlib: huecos de 1, 1 y 2 px, 100 % del color de fondo, sin píxeles intermedios (sólo cuatro colores: `#0B1118`, `#E6EDF3`, `#7D8B99`, `#63D6C4`); el margen de 32 y 48 px es 100 % `bg`. El `bg` `#0B1118` contra blanco `#FFFFFF` da un contraste de 18,96:1, así que el tile se distingue sobre una pestaña clara. Limitación: el icono de 16 px no tiene margen (no cabe) y el símbolo dark llena el lienzo; sobre una pestaña blanca los bloques claros pierden contraste (`#E6EDF3` contra blanco, 1,18:1; `#63D6C4`, 1,76:1; `#7D8B99`, 3,49:1) y sólo los separa el hueco de 1 px.
  - `apple-touch-icon.png` (180×180): símbolo original dark de 128 px (u = 16 px) centrado sobre `bg`; 26 px de espacio libre por lado (1,6 u).
  - `brand-sheet-{dark,light}.svg` (1600×1131): símbolo con espacio libre, lockup horizontal, 16/24/32 px en una tinta, paleta con tokens y HEX, especimen tipográfico y reglas de uso, con `<title>` y `<desc>`.

**Faltan**

- Cuestionar el acento `#63D6C4`.
- Un sitio web que use el favicon: no existe, así que `favicon.svg`, los PNG y el `.ico` no se enlazan desde ningún sitio.

Los datos de los agentes del catálogo y de las slides están duplicados en `AGENTS` de `assets/brand/src/agents_data.py`: se actualizan junto con `agents/*.md` (`tests/test_brand_agents.py` los compara).
