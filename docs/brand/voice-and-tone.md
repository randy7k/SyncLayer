# SyncLayer: voice and tone

> El copy citable va en inglés. Las notas para el mantenedor, en español.

## Voice

Plain, technical, present tense, concrete verbs. Say what the project does and where it stops.

| Do | Don't |
|---|---|
| «Nine specialist agents, one orchestrating session.» | «Supercharge your workflow with AI.» |
| «The guard is a heuristic, not a sandbox.» | «Secure by design.» |
| «A task is done when the tests ran and passed.» | «Seamless, autonomous development.» |
| Exact commands, paths and numbers. | Superlatives and adjectives without evidence. |

## Terminology

**Preferred:** layer, specialist, role, orchestration, guardrail, boundary, evidence, main session.
**Avoid:** revolutionary, supercharge, next-gen, magic, seamless, autonomous, game-changing, «AI-powered», «secure» sin matiz, «sandbox» (salvo para negarlo), emojis decorativos.

Reglas de escritura:

- Frases de 20 palabras o menos; voz activa; un término por cosa.
- Nombres de agentes en minúsculas y monoespaciado en prosa (`sindri`, `salomon`); en tablas de catálogo igual.
- Los nombres de agentes se escriben siempre sin tilde (`salomon`, `hector`), también en prosa: son identificadores de archivo. Los nombres anteriores sólo aparecen en la sección «Nombres anteriores» del README, en el bloque marcado de `CLAUDE.md`, en el historial y en los planes de fases cerradas.
- No prometer lo que el repositorio no hace. Lo futuro se rotula «planned» o «not yet».
- Los límites van junto a la afirmación, no en una nota al pie.

## Copy bank (official, English)

**Tagline**
One layer. Many specialists.

**Short description**
A global layer of specialist agents, orchestration rules and guardrails for AI coding assistants.

**GitHub repository description** (menos de 350 caracteres)
Specialist agents, orchestration rules and guardrails for Claude Code, kept in one versioned layer.

**Elevator pitch**
SyncLayer gives every project the same disciplined team of specialist agents, with clear roles and honest limits.

**README introduction**
SyncLayer is a versioned layer of nine specialist agents, orchestration rules and a guard hook for Claude Code. One session orchestrates; agents never delegate to each other. The guard is a heuristic, not a sandbox, and this repository documents exactly where it stops.

**Extended description**
SyncLayer keeps the working practice around AI coding assistants in one place instead of rebuilding it per project. It defines nine specialist roles (mapping, research, planning, implementation, testing, review, security, debugging and documentation), the rules for when each one is called, and a hook that limits what the review and testing roles can write. Everything is plain files under version control, copied into `~/.claude/`. It currently targets Claude Code only.

**Short presentation (3 slides)**
1. *The problem:* every project rebuilds its agents, rules and limits.
2. *The layer:* nine specialists, one orchestrating session, evidence before «done».
3. *The honest part:* what the guard enforces, what it only discourages, and what it cannot stop.

**Long presentation (outline)**
Problem → the star orchestration model → the nine roles → a worked example (task → sindri → salomon → anubis → shakespeare) → guardrails and their limits → how it is installed → what is planned and what is not.

## Tone by context

| Context | Tone |
|---|---|
| README, docs | Neutral, instructive, exact. |
| Security notes | Direct; the limitation first, then the mitigation. |
| Changelog (`HISTORY.md`) | Factual, one change per line. |
| Release or social text | Same voice, shorter; never louder. |

## Language policy

- Official brand copy: **English**.
- Existing technical documentation (README, guides, CLAUDE.md, HISTORY.md): remains in **Spanish**.
- A brand block may open the README in English with a link to the Spanish technical sections.
