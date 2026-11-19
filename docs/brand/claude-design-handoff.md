# HANDOFF: SyncLayer visual identity (for Claude Design)

> **Update (2026-11-19).** This brief was revised: the «Stepped S» direction was dropped and the approved direction is now **Modular Grid System**, described below. If anything here disagrees with `docs/brand/visual-identity.md`, that file wins and you tell the owner.

## Your role

Develop the visual identity of **SyncLayer** from an approved brand strategy and visual direction. Strategy, voice, colors and typography are already decided. Your job is the visual exploration: the final symbol artwork, the logo lockups and the first applications, presented so the project owner can steer them. What is pending is the final SVG files.

Work in rounds. After each round, show the lockups and applications as options side by side (the symbol is decided) and wait for direction. Do not finalize anything the owner has not approved.

## What SyncLayer is

A versioned, global layer of **nine specialist agents**, orchestration rules and a guard hook for **Claude Code**. One main session orchestrates; agents never delegate to each other. It is plain files under version control, copied into `~/.claude/`. It is an open engineering project, not a commercial SaaS.

Official tagline: **One layer. Many specialists.**

Do not claim anything the project does not do today:

- It is not multi-provider (Claude Code only for now).
- It does not sync automatically.
- It is not a sandbox. The guard is a heuristic and its limits are documented.
- It is not an Anthropic product, and the identity must not look like one.

## Brand personality

Precise, modular, orchestrated, candid, quiet, durable. Minimalist, technical, sophisticated. Dark, understated, engineering-oriented. It should feel like credible infrastructure, not a generic AI startup.

**Never use:** brains, robots, circuits, sparkles, glowing orbs, neural-network imagery, gradients as decoration, mascots, 3D renders.

## Approved visual direction: «Modular Grid System»

Minimalist and modern: blocks, gaps and one accent node. It comes from an exploration in Claude Design that is not versioned in this repository. Four blocks on a grid: the blocks are the *layer*; the accent block is the *sync*. The gaps hold the shape together.

The mark is approved (2026-11-19). Geometry on an 8 × 8 unit grid (u), gap between blocks 0.4 u, corner radius 0.25 u:

| SVG layer | x | y | Width | Height | Color token |
|---|---|---|---|---|---|
| `block-top-left` | 0 | 0 | 5.1 | 3 | `text` |
| `block-sync` | 5.5 | 0 | 2.5 | 3 | `accent` |
| `block-bottom-left` | 0 | 3.4 | 2.5 | 4.6 | `text-3` |
| `block-bottom-right` | 2.9 | 3.4 | 5.1 | 4.6 | `text` |

Constraints:

- Monochrome: all four blocks in one ink; the gaps hold the shape.
- Clear space 1 u. Minimum size 16 px.
- No gradients, shadows, or added strokes or outlines. Never used as a repeated pattern.
- Proposal, not validated in render: at 16 px the grid is 2 px per u (0.4 u = 0.8 px), so the gap rounds to at least 1 px and the corner radius is 0.

Wordmark: «SyncLayer», one word, IBM Plex Sans 600. This is a recommendation; the owner has not confirmed it. The two-weight version (Sync 400 / Layer 600) was evaluated and is not recommended.

Directions considered earlier were all dropped: *Stepped S* (an «S» monogram from two offset planes) did not land with the owner. *Strata* (stacked offset planes) and *Bus* (a line with nodes) were set aside before. The reason given for Strata, «generic», no longer holds without qualification: the current direction resembles it, since it is also built from rectangular planes. The difference is four coplanar blocks on a grid, separated by gaps, with a single accent block. *Bus* reflects the orchestration but disappears at small sizes. The orchestration **star** (main session at the center, agents around it) is reserved for diagrams, not for the logo.

## Design tokens

### Dark (default)

| Token | HEX | Role |
|---|---|---|
| bg | `#0B1118` | Background |
| surface | `#151F2A` | Cards and blocks |
| surface-2 | `#1C2936` | Elevated surface |
| text | `#E6EDF3` | Primary text |
| text-2 | `#A9B6C2` | Secondary text |
| text-3 | `#7D8B99` | Muted text and labels |
| accent | `#63D6C4` | The single accent |
| border | `#2A3A4A` | Decorative borders |
| ok / warn / error / info | `#4ADE80` / `#F5B84B` / `#FF7A7A` / `#7DB4FF` | Status |

### Light (required: GitHub shows light by default)

| Token | HEX |
|---|---|
| bg / surface | `#F6F8FA` / `#FFFFFF` |
| surface-2 | `#EAEFF3` (assumption, not measured) |
| text / text-2 / text-3 | `#0B1118` / `#44525F` / `#5B6874` |
| accent | `#0B7A6B` |
| border | `#D0D9E1` |
| ok / warn / error / info | `#1A7F37` / `#8A5A00` / `#C0362C` / `#1F5FBF` |

Rules: the accent covers less than 5 % of any composition. The symbol is the exception: `block-sync` is about 13 % of the block area. Text on the accent in dark mode is `#0B1118`. Borders do not reach 3:1 contrast, so they are decorative only. Status is never conveyed by color alone.

You may challenge the accent: `#63D6C4` is a teal common in developer tools. If you propose a more distinctive alternative, show it next to the original, keep contrast at 4.5:1 or better for text use, and explain the trade-off. Do not replace it silently.

## Typography

**IBM Plex Sans** for titles and text (600 titles, 400 body, 500 labels). **IBM Plex Mono** for code, paths, agent names and labels. Scale 32 / 24 / 20 / 16 / 14 px, body line-height 1.6. Titles in sentence case. Alternative to evaluate only if asked: Inter + JetBrains Mono.

## Graphic language

8 px grid. Rectangles with small radii (4 to 6 px) and right angles. 1 to 1.5 px lines in the border color; the accent on one element per composition. Flat surfaces with a 1 px border, no diffuse shadows. Uniform-stroke icons built from simple geometry. Diagrams, not illustrations.

## Round 1: what to produce

1. **Final symbol SVG.** The symbol is decided; do not explore new forms. Draw the four-block mark exactly as specified above, with the named layers. Show it at 16, 32, 64 and 256 px, in dark, light and monochrome.
2. **Lockups.** The mark with the wordmark «SyncLayer» (one word, IBM Plex Sans 600): horizontal and stacked, on dark and light. The two-weight version is not recommended and is not part of this round.
3. **A short check** of the result against the constraints above.

Stop here and wait for direction.

## Round 2 (after Round 1 is approved)

- **README header banner**, dark and light, to be used with an HTML `<picture>` element.
- **Social preview**, 1280 × 640 px, with a 40 px safe zone: background, symbol, name, tagline.
- **Agent catalog card:** name in Plex Mono, role, model and tools, for the nine agents `oracle`, `scout`, `atlas`, `forge`, `sentinel`, `auditor`, `shield`, `debugger`, `scribe`.
- **Architecture diagram:** the orchestration star. Main session at the center; the nine agents around it; no arrows between agents, since they never delegate to each other. One status color per role, not one per agent.
- **Slide template** for a short presentation: one message per slide, dark background, one accent.

## Round 3 (optional)

A one-page brand sheet with the symbol, palette, type specimen and usage rules (clear space, minimum size, don'ts).

## Copy you may use

- **Tagline:** One layer. Many specialists.
- **Short description:** A global layer of specialist agents, orchestration rules and guardrails for AI coding assistants.
- **Elevator pitch:** SyncLayer gives every project the same disciplined team of specialist agents, with clear roles and honest limits.
- **README introduction:** SyncLayer is a versioned layer of nine specialist agents, orchestration rules and a guard hook for Claude Code. One session orchestrates; agents never delegate to each other. The guard is a heuristic, not a sandbox, and this repository documents exactly where it stops.

Voice: plain, technical, present tense, concrete verbs. Avoid *revolutionary, supercharge, next-gen, magic, seamless, autonomous, AI-powered*.

## Deliverable format

- Symbol and lockups as **clean SVG** with no embedded raster, wordmark text always delivered converted to paths in the final SVGs, and named layers `block-top-left`, `block-sync`, `block-bottom-left` and `block-bottom-right`.
- Color and type tokens as a short list I can copy into CSS custom properties.
- For every round, a note listing what changed, what you chose not to do, and any open question.

## How to evaluate your own work

- Is it recognizable without any AI imagery?
- Does the four-block mark survive at 16 px in one color, with the gaps still visible?
- Does it look like an infrastructure project, not a startup landing page?
- Does anything imply a capability the project does not have?
- Would it still make sense if the project later supported other assistants besides Claude Code?

## Source of truth

The approved documents are in the repository under `docs/brand/`: `brand-strategy.md`, `voice-and-tone.md` and `visual-identity.md`. If this handoff and those files disagree, `visual-identity.md` wins and you tell the owner.
