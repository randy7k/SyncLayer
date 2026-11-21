# Backlog: reportes de uso y configuración de SyncLayer

> Estado: **backlog, sin desglosar**. Las cuatro fases de abajo son intención del propietario
> (2026-11-19), no un diseño. Cada una empieza con una exploración cuyo resultado se le propone
> al propietario antes de implementar nada. Las ideas marcadas «hipótesis» no están verificadas.
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
`feat/esfuerzo-configurable`. T1, T2, T3 y T6 cerradas. T4 (renderizado de `model:` y `effort:`)
implementada sin correr la compuerta G1 del propietario (decisión suya), en revisión. T5, T7 y el
cierre pendientes (T7 tiene una versión parcial escrita). Los niveles 1 a 4 se aplican; el efecto real
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

## Fase 5: otras configuraciones dinámicas

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
