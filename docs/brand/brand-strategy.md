# SyncLayer: brand strategy

> Estado: aprobado el 2026-11-19 (tagline, paleta y tipografía). Marca de cuatro bloques («Modular Grid System») aprobada el 2026-11-19; «Stepped S» se descartó. Wordmark recomendado, sin confirmar por el propietario (ver `visual-identity.md`).
> El copy oficial va en inglés; las explicaciones, en español, para quien mantiene el repositorio.

## Positioning

**What it is (official).** A global, versioned layer of specialist agents, orchestration rules and guardrails for AI coding assistants. It starts with Claude Code.

**Qué es hoy.** Nueve agentes, reglas de orquestación, un hook de guarda y una guía de uso, copiados entre este repositorio y `~/.claude/`.

**Qué no es hoy** (la marca no puede prometerlo):

- No es multi-proveedor: sólo funciona con Claude Code.
- No sincroniza automáticamente: la copia entre repo y `~/.claude/` es manual hasta que exista un instalador.
- No es un sandbox: la guarda es heurística y sus brechas están documentadas.
- No es un servicio ni un producto comercial.

**Problema.** Cada proyecto reinventa sus agentes, sus reglas y sus límites. SyncLayer los define una vez, con roles claros, y los aplica a todos los proyectos.

**Diferenciadores verificables en el repositorio:**

1. Una sola sesión orquesta; los agentes no se delegan trabajo entre sí.
2. Cada rol tiene una lista de herramientas distinta; los agentes de revisión no tienen `Edit` ni `Write`, y su `Bash` está limitado por una guarda heurística (no es de solo lectura real).
3. «Terminado» exige pruebas ejecutadas y evidencia, no una afirmación.
4. Documenta sus límites en lugar de ocultarlos.

**Audiencia hoy:** desarrolladores que usan Claude Code y quieren un flujo de agentes disciplinado.
**Audiencia futura (no prometida):** equipos con varios asistentes de código.

**No confundir con:**

| Con | Por qué no |
|---|---|
| Herramientas de sincronización de archivos | No sincroniza datos de usuario: distribuye configuración de agentes. |
| Frameworks de agentes (LangChain, CrewAI) | No es un runtime ni un SDK: son archivos que lee Claude Code. |
| Un producto de Anthropic | Es un proyecto independiente que corre sobre Claude Code. |
| Un sandbox o producto de seguridad | La guarda reduce accidentes; no aísla. |

## Personality

| Attribute | Cómo se nota |
|---|---|
| **Precise** | Cifras, comandos y rutas exactas. Sin adjetivos vacíos. |
| **Modular** | Piezas pequeñas y nombrables; diagramas por componentes. |
| **Orchestrated** | Habla de roles y coordinación, no de «inteligencia». |
| **Candid** | Documenta sus límites. Es el rasgo que más lo separa de una marca de IA genérica. |
| **Quiet** | Oscuro, sobrio, un solo acento. Sin brillos ni degradados. |
| **Durable** | Convenciones estables; evita modas. |

## Mission, vision, promise

- **Mission.** Give every project the same disciplined team of specialist agents.
- **Vision.** One layer of agent practice that outlives any single tool or model.
- **Promise.** Clear roles, enforced boundaries where possible, and honest limits where not.

La visión es una aspiración, no una funcionalidad actual.

## Principles

1. **Specialists over generalists.** Each agent does one job well.
2. **One orchestrator, no delegation chains.** Only the main session delegates and asks the user.
3. **Evidence before «done».** A task is finished when tests ran and criteria are checked.
4. **State the limits.** A guardrail that is a heuristic is called a heuristic.
5. **Plain files, under version control.** No service, no hidden state.

## Tagline

**One layer. Many specialists.**

Decisión (2026-11-19): se reemplaza «One Layer. Multiple Intelligence.» porque:

- *Multiple Intelligence* es gramaticalmente forzado y remite a la teoría de las inteligencias múltiples de Gardner.
- «Intelligence» acerca la marca al discurso genérico de IA y sugiere varios modelos o proveedores, que hoy no existen.
- «Many specialists» es exacto (nueve roles), no menciona IA y no ata la marca a un proveedor.

Alternativa descartada: *One layer. Multiple intelligences.* (corrige la gramática, mantiene los otros dos problemas).
