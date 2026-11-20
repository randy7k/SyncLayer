# Fase 2: reporte de uso de agentes. Resultado de la exploración

> Estado: **exploración cerrada, fase todavía sin desglosar.** Siguiente paso: que `atlas`
> desglose en tasks a partir de este documento, y aprobación del propietario antes de
> implementar. Fecha de la consulta a la documentación: 2026-11-19 (Claude Code 2.1.310 en
> este equipo; la documentación oficial no lleva fecha propia). Plan de origen:
> [`2026-11-19-backlog-configuracion-y-reportes.md`](2026-11-19-backlog-configuracion-y-reportes.md).

## Decisiones del propietario (2026-11-19)

1. **Fuente de datos:** un script de biblioteca estándar que lee las transcripciones
   locales, ahora; un hook registrador opcional, después.
2. **Ubicación:** reporte por proyecto en un `.md` local dentro del proyecto y **fuera de git**;
   reporte global comparativo en `~/.claude/`.
3. **Formato:** tablas y barras de texto en Markdown, sin dependencias. Un SVG puede venir
   después.

## Qué datos existen (resumen verificado)

| Dato | Dónde | Estable | Notas |
|---|---|---|---|
| Llamadas por agente (`agent_type`) | Transcripciones (`tool_use` de nombre `Agent`, `input.subagent_type`) y hooks | Hooks sí; transcripción no | La herramienta se llamaba `Task` antes de la v2.1.63 |
| Modelo por llamada | Líneas del archivo del subagente (`model`) y `PostToolUse` | Igual | Declarado en el frontmatter ≠ modelo real |
| Tokens por petición | Campo `usage` de cada mensaje del subagente | Transcripción: no | **Sumando las peticiones se obtiene el total real**; los hooks sólo traen la última petición |
| Duración y conteo de herramientas | Hooks (`totalDurationMs`, `totalToolUseCount`) | Sí | En la transcripción no se encontraron con esos nombres |
| Uso de skills y plugins | OpenTelemetry; en hooks, `tool_name` `Skill` (forma de `tool_input` sin verificar) | Parcial | |
| Calidad del resultado, tasa de reintento | Ninguna métrica oficial | — | El reintento sólo se puede inferir contando llamadas repetidas |

Las transcripciones viven en `~/.claude/projects/<proyecto>/<sesión>.jsonl` y los subagentes
en `<sesión>/subagents/agent-<id>.jsonl` con un `.meta.json` (`agentType`, `toolUseId`, ...).
En este equipo: 34 sesiones principales y 2 855 transcripciones de subagentes; en SyncLayer,
4 sesiones y 57 subagentes. Los conteos preliminares de `oracle` eran de líneas, no de
ocurrencias: el script debe contar bien.

## Riesgos que el diseño debe respetar

- **Formato interno.** La documentación oficial dice que el JSONL «changes between versions,
  so scripts that parse these files directly can break on any release». El script debe
  detectar un esquema desconocido y **fallar con un mensaje claro**, nunca producir números
  silenciosamente erróneos. Por eso el hook registrador va después como fuente estable.
- **Privacidad.** Las transcripciones guardan prompts, código, salidas de herramientas y rutas
  de proyectos. El script lee sólo claves numéricas y nombres (agente, modelo, `usage`), ignora
  `message.content`, `prompt`, `description` y `toolUseResult` no numérico, y el reporte nunca
  copia contenido. Los nombres de carpeta de proyecto codifican rutas: el reporte global no
  debe publicar nombres de clientes (alias o resumen por proyecto).
- **Tokens inflados por reintentos.** La v2.1.328 corrige que los conteos de tokens de
  subagentes contaban una respuesta reintentada dos veces: entre 2.1.310 y 2.1.327 pueden
  estar inflados. Cualquier comparación debe anotar la versión de Claude Code.
- **Estimaciones de costo** son a precio de lista, no el cobro real.

## Qué mide el reporte (propuesta para el desglose)

Por agente (los nueve y cualquier otro `agent_type`, también de plugins o integrados):
llamadas, tokens por llamada (suma de las peticiones del subagente: entrada, salida, caché),
mediana y percentil 90, modelo real usado, duración y herramientas por llamada si están
disponibles, llamadas por sesión y llamadas repetidas seguidas al mismo agente (señal de
reintento, marcada como inferida). Reporte por proyecto con ventana de fechas; reporte global
con la misma tabla para comparar conjuntos de subagentes o skills **sólo con métricas
comparables** (llamadas, tokens por llamada, duración, herramientas). No compara calidad ni
costo real.

## Fuera de alcance de esta fase

- Medir la calidad del resultado de un agente (hallazgos de `auditor` aceptados, etc.): no hay
  campo fiable; podría ser un registro manual en una fase posterior.
- OpenTelemetry: no tiene exportador a archivo documentado y oculta los nombres de agentes
  propios como «custom» sin `OTEL_LOG_TOOL_DETAILS=1`, que además expone rutas y comandos.
- Modificar `settings.json`: hoy el instalador promete no tocarlo. El hook registrador exigiría
  cambiar esa promesa de forma explícita y documentada.

## No verificado (a resolver en el desglose o en la primera task)

- Forma de `tool_input` de la herramienta `Skill` y si `PostToolUse` dispara para ella.
- Si un subagente en segundo plano entrega `totalTokens` por hook.
- Si `SubagentStart` se puede declarar en el frontmatter (la documentación lo da sólo para
  `settings.json`).
- Existencia de `/cost` y esquema de `stats-cache.json`.
- Changelog de las versiones 2.1.311 a 2.1.325.
- Relación exacta entre el `toolUseId` del `.meta.json` y el `tool_use` de la sesión principal.

## Para `atlas`

Desglosar en tasks pequeñas: (1) lector defensivo de transcripciones con detección de
esquema y pruebas con transcripciones sintéticas (nunca reales en el repo); (2) agregación y
métricas; (3) generador del `.md` por proyecto y del global; (4) integración con el
instalador o comando de uso manual (decidir); (5) hook registrador opcional (con su propia
decisión sobre `settings.json`); (6) documentación y línea de tiempo. `shield` aplica porque
el script lee datos sensibles de la carpeta de usuario. Preguntas abiertas para el propietario
al desglosar: nombre y forma de invocación del comando, ventana de fechas por defecto y si el
reporte global usa alias de proyecto.

Fuentes oficiales consultadas (code.claude.com/docs/en): `hooks`, `monitoring-usage`,
`sub-agents`, `costs`, `statusline`, `sessions`, `claude-directory`, `data-usage`,
`agent-sdk/cost-tracking` y el `CHANGELOG.md` del repositorio de Claude Code.
