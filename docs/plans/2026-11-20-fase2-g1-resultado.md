# Fase 2: resultado de la compuerta G1

> Fecha: 2026-11-20. Se corrió `python -B tools/usage_report.py inspect` (T1) sobre las
> transcripciones reales del equipo del propietario, en una sola máquina y con Claude Code
> 2.1.287 a 2.1.326 mezclado. **Sólo conteos y estructura; ningún contenido, ruta ni nombre de
> proyecto.** `projects/` quedó sin cambios (instantánea antes y después) y la salida no tuvo
> bytes fuera de ASCII ni el nombre de usuario. Plan: [`2026-11-19-fase2-reporte-de-uso.md`](2026-11-19-fase2-reporte-de-uso.md).
> G1 es una compuerta, no una unidad: no cambia el avance.

## Qué se confirmó

| Supuesto del plan | Resultado | Consecuencia |
|---|---|---|
| Las llamadas a subagentes tienen `tool_use` `Agent` con `input.subagent_type` | Sí: 2 866 `Agent`, 0 `Task`; `subagent_type` en 2 646 (el resto, 220, usan el agente por defecto o no lo declaran) | T2 debe tratar la ausencia de `subagent_type` como agente por defecto, no como error |
| Un `agent-<id>.jsonl` por llamada con su `.meta.json` | Sí: 2 746 subagentes, 2 746 con meta, 0 sin meta, 0 metas sin transcripción | Unidad de medida confirmada |
| `meta.agentType` cadena | 2 746 de 2 746 | Es la fuente fiable del tipo de agente |
| `meta.toolUseId` enlaza con el `tool_use` de la sesión principal | 2 743 coinciden, 0 no coinciden, 3 sin `toolUseId` | El enlace funciona; los 3 sin id quedan como «sin enlazar» |
| Hay `message.id` repetido entre líneas | **Sí, mucho:** 113 541 líneas `assistant` con `usage` en subagentes frente a 59 796 `message.id` distintos (≈ 1,9 líneas por id) | La deduplicación por `message.id` es **obligatoria**: sin ella los tokens se duplicarían casi al doble |
| `usage` con los cuatro campos enteros | 149 986 de 149 986, 0 sin ellos | La lectura de tokens es posible y uniforme (entrada, salida, creación y lectura de caché) |
| Marcas de tiempo interpretables | 474 572 de 474 572 | Ventana por fechas viable |
| `input.skill` en la herramienta `Skill` | **Sí:** 232 llamadas `Skill`, `skill` cadena en 232, `args` en 137 | **T4 (conteo de skills) se mantiene** |
| Subagentes en segundo plano | `run_in_background` aparece en 826 de las llamadas (verdadero o texto); `toolUseResult.totalTokens`, `totalDurationMs` y `totalToolUseCount` sólo en 399 de 2 866 llamadas | Los totales del resultado no sirven como fuente: **sumar las peticiones del subagente** (decisión ya tomada) |
| `meta.model` | Presente en 2 543 de 2 746 | Hay un modelo por llamada también en el meta; T2 puede usarlo y contrastar con el de las líneas |
| Líneas corruptas, truncadas o ilegibles | 0, 0, 0 | Datos sanos; una sola línea sobredimensionada descartada |
| Nombres de carpeta con emoji (unidad UTF-16) | **No verificable:** las 20 carpetas leídas tienen nombres válidos y ninguna con carácter fuera del BMP | Sigue «a confirmar»; el riesgo es sólo para `--project-dir` |

## Qué cambia en el plan (a aprobar por el propietario)

### 1. Los hardlinks de subagentes son legítimos de Claude Code

`inspect` omitió **122 «enlaces»**. Son todas transcripciones de subagentes (`.jsonl`) con
`nlink = 2`, cuyo otro enlace **no está dentro de `projects/`** (probablemente el archivo de
salida de las tareas en segundo plano). Los crea Claude Code, no un tercero.

- **Efecto con la política actual de T1** (rechazar `nlink != 1`): las transcripciones de
  esos 122 subagentes (4,3 % de 2 868) quedan fuera, y son justo los de tareas en segundo
  plano: un **sesgo sistemático** en cualquier reporte de uso.
- **Propuesta para T2:** aceptar `nlink > 1` en el lector de subagentes cuando el nombre pase la
  lista permitida (`agent-<id>.jsonl` bajo `subagents/` de una sesión válida), contarlos aparte
  («hardlinks aceptados: N») y seguir rechazando enlaces simbólicos y puntos de reanálisis.
- **Riesgo residual (Low, documentado por `shield` como hallazgo 1 de T1):** un proceso del mismo
  usuario podría plantar un hardlink a otro archivo. Mitigación: T2 sólo lee claves numéricas y
  nombres de una lista cerrada y valida la firma estructural; un archivo ajeno no pasa la firma.
  `inspect` puede mantener el rechazo o también aceptarlos con un contador; decidir en T2.

### 2. Versiones de Claude Code y tokens posiblemente inflados

La exploración indicó que entre 2.1.310 y 2.1.327 los conteos de tokens de subagentes pueden
contar dos veces una respuesta reintentada. En estos datos, el **60 % de las líneas de subagentes
(205 448 de 340 468 con versión)** pertenece a versiones de esa ventana, por lo que el efecto no
es marginal.

- La deduplicación por `message.id` probablemente neutraliza el doble conteo si el reintento
  repite el id; **no está verificado**.
- **T3 debe desglosar por versión de Claude Code** (antes de 2.1.310, de 2.1.310 a 2.1.327, desde
  2.1.328) en lugar de una sola cifra, y el reporte debe decir que la comparación entre rangos
  es indicativa.

### 3. Otros ajustes menores

- Agente sin `subagent_type` (220 de 2 866): se clasifica como agente por defecto.
- La línea sobredimensionada descartada: T2 no debe sumar tokens de líneas descartadas y debe
  contarlas aparte.
- Dos pendientes de `shield` pasan a T2 (conteos parciales de un archivo omitido a mitad de
  lectura; sesión cuyo único archivo es un hardlink).

## Escala de los datos (para el rendimiento)

20 carpetas de proyecto, 34 sesiones, 2 746 subagentes, ~637 000 líneas en total. `inspect`
tardó más de dos minutos en esta máquina: T2 debe medir el tiempo y valorar un caché por
archivo (decisión del plan, objetivo de 60 s en C4).
