# Backlog: reportes de uso y configuración de SyncLayer

> Estado (2026-11-24): **las fases 2 a 5 están desglosadas**; la Fase 5 está desglosada y aprobada, en curso
> (ver su sección). Las fases de abajo nacieron como intención del propietario (2026-11-19), no como un
> diseño; cada una empezó con una exploración cuyo resultado se le propuso al propietario antes de
> implementar nada. Las ideas marcadas «hipótesis» no están verificadas.
> Al desglosar una fase en tasks, se actualiza la sección «Línea de tiempo y avance» del README.

Punto de partida: el instalador (`docs/plans/2026-11-19-instalador.md`) está en curso y es la
base de las fases 3 a 5, porque la configuración se aplica al instalar (ver «Restricción de
diseño»).

## Restricción de diseño: simple

- Un solo archivo de configuración para el usuario, legible a mano (hipótesis: JSON o
  `.md` con frontmatter; se decide en la exploración de la Fase 3).
- La configuración se aplica **al instalar** (`install.ps1` genera los archivos de
  `~/.claude/agents/` a partir de las plantillas del repo), no en tiempo de ejecución. Así
  Claude Code sigue leyendo archivos planos y no hay un servicio que mantener.
- Los valores por defecto reproducen exactamente el comportamiento actual: quien no configura
  nada no nota ningún cambio.
- Nada de lo que se declare debe prometer ahorro de tokens medido sin evidencia.

## Fase 2: reporte de uso de agentes

**Estado (2026-11-20).** Desglosada y en curso: el plan está en
[`2026-11-19-fase2-reporte-de-uso.md`](2026-11-19-fase2-reporte-de-uso.md). T1 a T8 cerradas;
siguen el cierre del núcleo y T9 (hook registrador, opcional). El texto
que sigue es el pedido original de la etapa 1.

**Pedido.** Ver cuánto se usa cada agente. Un `.md` por proyecto, dentro de cada uno, y un `.md`
global para comparar eficiencia contra otros conjuntos de subagentes o skills.

**Etapa 1 (exploración, `scout` y `oracle`).** Responder y proponer al propietario:

- Qué datos existen hoy y dónde (hipótesis: las transcripciones de sesión en
  `~/.claude/projects/` registran las llamadas a subagentes; los hooks `SubagentStop` o
  `PostToolUse` podrían registrar eventos). Verificar con la documentación oficial qué trae cada
  uno: modelo, tokens, duración, resultado.
- Qué es «eficiencia» medible sin inventar: llamadas por agente, tokens por llamada, hallazgos
  Critical/Important encontrados por llamada del `auditor`, rondas de corrección por task,
  tiempo. Cuáles se pueden obtener y cuáles no.
- Forma de presentarlo, con opciones y una recomendación: Markdown con tablas y barras de texto
  (sin dependencias) frente a un SVG generado (como los de `assets/brand/`). Dónde vive cada
  reporte (el del proyecto en `docs/` del proyecto; el global en una carpeta de usuario) y quién
  lo genera (un script de biblioteca estándar invocado a mano, no un proceso residente).
- Cómo comparar contra «otros subagentes o skills» con datos comparables: qué hay que registrar
  de ambos lados y qué no se puede comparar honestamente.
- Privacidad: el reporte nunca copia contenido de las conversaciones, sólo conteos y métricas.

**Salida de la etapa 1:** un documento corto con las opciones, la recomendación y las
preguntas abiertas. Sin código.

## Fase 3: esfuerzo configurable (5 niveles)

**Estado (2026-11-20).** Plan aprobado:
[`2026-11-20-fase3-esfuerzo-configurable.md`](2026-11-20-fase3-esfuerzo-configurable.md), rama
`feat/esfuerzo-configurable`. T1 a T6 cerradas (T4 sin correr la compuerta G1, por decisión del
propietario). T7 y el cierre en curso. La compuerta G1 sigue pendiente del propietario y no bloquea. Los niveles 1 a 4 se aplican; el efecto real
de `effort:` en Claude Code no está verificado en una máquina real.

**Pedido.** Subir o bajar el consumo según los tokens que queden: por ejemplo, que `atlas`
pase de `claude-fable-5-2` a `opus` al bajar el esfuerzo.

**Etapa 1 (exploración).**

- Definir los 5 niveles como perfiles que asignan un modelo a cada agente (hipótesis: nivel 5 =
  la asignación actual; niveles menores bajan primero los agentes más caros: `atlas`, luego los
  de `opus`). Proponer la tabla nivel × agente y justificarla con la documentación de modelos.
- Verificar si Claude Code ofrece un control propio de esfuerzo o de modelo por subagente
  (campo `model:` del frontmatter; variables `CLAUDE_CODE_SUBAGENT_MODEL` y
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`) y cómo se combina con la configuración de SyncLayer.
- Mecanismo: el instalador escribe el `model:` según el nivel elegido (cambiar de nivel =
  reinstalar) frente a depender de variables de entorno (cambio inmediato, pero global y menos
  explícito). Proponer una recomendación.
- Qué cambia además del modelo y qué no se debe tocar: el esfuerzo no puede quitar `auditor` ni
  `shield` de los cambios sensibles sin que el propietario lo decida expresamente.
- Aviso honesto en el README: bajar el nivel cambia la calidad esperada de las revisiones.

## Fase 4: nombres de agentes configurables

**Pedido.** Que el nombre de un agente no sea fijo (por ejemplo, «el amigo QA»).

**Etapa 1 (exploración).**

- Inventariar dónde aparece cada nombre: `name:` del frontmatter, el archivo, las reglas de
  orquestación (`rules/agentes.md`), la guía (`docs/agentes.md`), las descripciones de las
  delegaciones («Forge (Sonnet): …»), el hook (`$HOME/.claude/hooks/agent_guard.py` y su
  modo, que se enlaza desde el frontmatter, no por nombre: verificar), las pruebas y el manifiesto.
- Mecanismo propuesto (hipótesis): tabla de alias en el archivo de configuración; el instalador
  renombra el archivo y reemplaza el nombre en las reglas y descripciones. El rol sigue siendo
  el id estable interno.
- Riesgos a evaluar: nombres que choquen con agentes de otros plugins, caracteres válidos,
  que `rules/agentes.md` siga coherente tras el cambio y que la copia inversa y el manifiesto
  sigan funcionando (el manifiesto hoy fija las rutas).
- Qué pasa con un proyecto que tenga `.claude/agents/<nombre>.md` del nombre viejo.

**Estado (2026-11-24).** Desglosada y en curso: plan
`docs/plans/2026-11-22-fase4-nombres-configurables.md` (9 unidades). T1 a T8 hechas (la T8 es la
documentación: README, `CLAUDE.md`, `HISTORY.md` y `docs/agentes.md`); falta el cierre (`sentinel`,
`shield` y `auditor` sobre el cambio completo). Los alias se aplican, pero su efecto en un Claude Code
real no está verificado: es la compuerta G1 del propietario (incluido el caso P10, dos archivos del mismo
ámbito con el mismo `name:`).

**Tarea pendiente para después de la Fase 4 (decisión P11, 2026-11-23).** `Get-Prop` desenrolla las
listas de un elemento, así que `path`, `sha256`, `written`, `level`, `schema`, `algorithm` y `eol` del
estado, y `schema`, `path`, `sha256` y `algorithm` de `install-manifest.json`, aceptan `[valor]` en lugar
de `valor` (defecto heredado de las Fases 1 y 3; no es un hueco conocido, pero contradice «tipos
estrictos»). Corregirlo en una tarea aparte: usar `Get-PropRaw(...).Value` en `Get-ManifestEntries`,
`Read-Manifest` y `Read-State`, con la prueba roja primero (un estado y un manifiesto con cada campo como
lista de un elemento deben rechazarse). Mientras tanto está documentado como límite en el `README.md`
(«Límites del instalador») y en `CLAUDE.md`. No cambia las 9 unidades de la Fase 4.

## Fase 5: otras configuraciones dinámicas

**Estado (2026-11-24).** Desglosada y aprobada; en curso: plan
[`2026-11-24-fase5-configuraciones-dinamicas.md`](2026-11-24-fase5-configuraciones-dinamicas.md) (9
unidades), rama `feat/configuraciones-dinamicas`, aprobado por el propietario con los valores por
defecto de P1 a P14. Entran carpeta de planes, idioma del reporte de uso y perfiles por proyecto (sólo
documentación); el resto de las candidatas de abajo se descarta con motivo en el plan (sección 1.2). El
texto que sigue es el pedido original.

**Pedido.** Buscar qué más se puede configurar sin complicar el proyecto.

**Etapa 1 (exploración y propuesta).** Candidatas a evaluar, cada una con su costo de
mantenimiento; se proponen sólo las que valgan la pena:

- Activar o desactivar agentes por usuario (por ejemplo, sin `shield`).
- Herramientas (`tools:`) por agente, dentro de un mínimo seguro.
- Idioma de los reportes (hoy en español; los prompts son en inglés).
- Carpeta de planes (`docs/plans/` por defecto) y convención de commits.
- Estrictez de la guarda (qué modos de `agent_guard.py` se enlazan), sin ofrecer nada que la
  documente como sandbox.
- Perfiles por proyecto (`.claude/agents/` ya reemplaza al global; ver si basta con documentarlo).
- Descartar explícitamente lo que añada complejidad sin valor, y decir por qué.

## Orden sugerido

1. Terminar el instalador (la configuración se apoya en él).
2. Fase 3 (esfuerzo) y Fase 4 (nombres) comparten el mecanismo de plantillas y archivo de
   configuración: explorarlas juntas para diseñar un único archivo.
3. Fase 2 (reporte) es independiente y puede ir en paralelo si hay capacidad.
4. Fase 5 al final, con lo que quede de la exploración.

## Cómo se ejecuta cada fase

Según `rules/agentes.md`: `oracle` y `scout` exploran → `atlas` desglosa en tasks (aquí es
cuando la fase deja de estar «sin desglosar») → aprobación del propietario → `forge` por task
con `auditor` → `sentinel`, `shield` si toca rutas, entradas o escritura en `~/.claude` →
`scribe` → `auditor` sobre el cambio completo.
