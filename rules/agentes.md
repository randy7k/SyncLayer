# Ecosistema de agentes

Hay nueve agentes globales en `~/.claude/agents/`. La sesión principal es la única
que orquesta: decide a quién llamar, le pasa el contexto y le pregunta al usuario.
Los agentes no se delegan trabajo entre sí y no pueden preguntarle al usuario.

Guía completa: `~/.claude/docs/agentes.md`.

## Catálogo

| Agente | Para qué | Modelo | Escribe |
|---|---|---|---|
| `oracle` | Mapear un repo o un área desconocida | haiku | no |
| `scout` | Verificar docs oficiales, comparar librerías | sonnet | no |
| `atlas` | Plan de implementación y arquitectura | claude-fable-5-2 | sólo el archivo del plan |
| `forge` | Implementar una unidad de trabajo | sonnet | código y sus tests |
| `sentinel` | Correr y ampliar pruebas, validar requisitos | sonnet | sólo tests |
| `auditor` | Review independiente del diff | opus | no |
| `shield` | Seguridad del diff | opus | no |
| `debugger` | Causa raíz de un fallo | opus | no |
| `scribe` | README, CLAUDE.md, HISTORY.md, docs de API | sonnet | sólo documentación |

## Cuándo delegar

Delegá sólo cuando el agente aporta algo que la sesión principal no haría igual de
bien y más barato. Ante la duda entre dos tamaños, elegí el menor.

| Tamaño | Señales | Flujo |
|---|---|---|
| Trivial | Un archivo, requisito claro, sin riesgo | La sesión principal lo hace. Sin agentes. |
| Mediana | 2 a 5 archivos, requisito claro | `oracle` si el área es desconocida → `forge` → `auditor` |
| Grande | Feature nueva, varias fases, cambio entre módulos, decisión de arquitectura | `oracle` y `scout` (si hace falta) → `atlas` → aprobación del usuario → por cada task: `forge` → `auditor` → al final: `sentinel` → `shield` si aplica → `scribe` → `auditor` sobre el cambio completo |
| Bug sin causa clara | Intermitente, cruza módulos, o falló un primer intento | `debugger` → `forge` → `sentinel` |

Preguntas, explicaciones y lecturas puntuales no usan agentes.

Si el usuario nombra un agente, usalo aunque la tabla diga otra cosa.

`shield` interviene cuando el cambio toca autenticación, autorización, sesiones,
secretos, entrada de usuario, construcción de SQL u otras consultas, subida o
descarga de archivos, deserialización, peticiones salientes o dependencias nuevas.
Para auditar un repositorio completo se usa el plugin `claude-security`, no `shield`.

## Cómo pasar contexto

Un agente arranca sin ver la conversación y devuelve sólo su reporte final.

- El prompt de cada delegación lleva: objetivo, criterios de aceptación, rutas a leer
  (el plan, archivos concretos), lo ya descartado y qué formato de respuesta se espera.
- Pasá rutas, no contenido pegado. El plan de `atlas` vive en un archivo del repo
  (`docs/plans/AAAA-MM-DD-<tema>.md` salvo que el proyecto use otro lugar) y es la
  fuente común para `forge`, `sentinel`, `auditor` y `scribe`.
- No hagas que dos agentes exploren lo mismo: el reporte de `oracle` se reutiliza
  en los prompts siguientes.
- A `auditor` y `shield` se les da el diff y el requisito, no la conclusión del
  implementador.

## Paralelo y secuencial

- En paralelo: sólo agentes que no escriben (`oracle`, `scout`, `auditor`, `shield`),
  lanzados en un mismo mensaje.
- Un solo agente que escribe a la vez por checkout: `forge`, `sentinel` y `scribe`
  nunca corren al mismo tiempo sobre el mismo árbol de trabajo.
- Dos `forge` en paralelo sólo si sus tasks tocan archivos disjuntos según el plan y
  cada uno corre en su propio worktree.
- `atlas` siempre antes de `forge`; `auditor` y `sentinel` siempre después.

## Conflictos entre recomendaciones

Orden de precedencia: `shield` (seguridad) > `sentinel` (evidencia de pruebas) >
`auditor` > plan de `atlas` > `forge`. Un hallazgo con evidencia ejecutada pesa más
que una opinión. Si el conflicto es una decisión de producto o de alcance, o la
precedencia no lo resuelve, preguntale al usuario.

## Cuándo una tarea está terminada

Todas a la vez:

1. Las pruebas relevantes se corrieron en esta sesión y pasaron, con el comando y la
   salida a la vista.
2. Cada criterio de aceptación está verificado contra evidencia.
3. No quedan hallazgos Critical ni Important de `auditor`, `sentinel` o `shield` sin
   resolver. Los corrige `forge` y el agente que los encontró vuelve a revisar.
4. La documentación del proyecto está actualizada.

Lo que no se pudo verificar se dice explícitamente en el cierre. El reporte de un
agente es su versión de los hechos: revisá el diff o la salida antes de darlo por bueno.

## Agentes por proyecto

Un archivo `.claude/agents/<nombre>.md` dentro de un repo reemplaza al agente global
del mismo nombre sólo en ese proyecto. Usalo para adaptar un agente a un stack, no
copies los nueve.
