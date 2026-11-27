"""Auxiliar de las pruebas de la Fase 6 (renombrado de agentes). No es un test_*.py.

Fija la tabla RENAME (nombre anterior -> nombre vigente), da los once textos gestionados del repositorio y sus
hashes, y guarda como datos fijos el frontmatter que el renombrado no debe tocar. La prueba puente de T1 a T7 (el
fixture de hashes y la transformacion en memoria) se retiro en T8. Solo biblioteca estandar; no escribe nada.
"""

import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aliases_ref as ar  # noqa: E402

ROOT = ar.ROOT
bm = ar.bm

# Nombre actual -> nombre nuevo. atlas no cambia. Sin tilde (P12).
RENAME = {
    "oracle": "heimdall",
    "scout": "hermes",
    "forge": "sindri",
    "sentinel": "anubis",
    "auditor": "salomon",
    "shield": "hector",
    "debugger": "sherlock",
    "scribe": "shakespeare",
}

# Archivos de esta fase que guardan los nombres a proposito (caso 6, supuesto 7).
OWN_NAMES = ("rename_ref.py", "test_rename.py")

# Frontmatter que el renombrado no debe tocar (caso 18), fijado el 2026-11-27 sobre agents/*.md, por nombre
# actual: lineas tools:, model: y color: y el bloque hooks: completo (vacio si el agente no tiene guarda).
_HOOK_READONLY = [
    "hooks:",
    "  PreToolUse:",
    "    - matcher: \"Bash\"",
    "      hooks:",
    "        - type: command",
    "          command: 'python \"$HOME/.claude/hooks/agent_guard.py\" readonly --allow-temp'",
]
_HOOK_TESTS_ONLY = [
    "hooks:",
    "  PreToolUse:",
    "    - matcher: \"Write|Edit|NotebookEdit|Bash\"",
    "      hooks:",
    "        - type: command",
    "          command: 'python \"$HOME/.claude/hooks/agent_guard.py\" tests-only'",
]
_FROZEN = {
    "atlas": ("tools: Read, Grep, Glob, Write", "model: claude-fable-5-2", "color: purple", []),
    "auditor": ("tools: Read, Grep, Glob, Bash", "model: opus", "color: yellow", _HOOK_READONLY),
    "debugger": ("tools: Read, Grep, Glob, Bash", "model: opus", "color: pink", _HOOK_READONLY),
    "forge": ("tools: Read, Edit, Write, Grep, Glob, Bash", "model: sonnet", "color: orange", []),
    "oracle": ("tools: Read, Grep, Glob", "model: haiku", "color: cyan", []),
    "scout": ("tools: WebSearch, WebFetch, Read, Grep, Glob", "model: sonnet", "color: blue", []),
    "scribe": ("tools: Read, Grep, Glob, Edit, Write", "model: sonnet", "color: green", []),
    "sentinel": ("tools: Read, Grep, Glob, Bash, Edit, Write", "model: sonnet", "color: green", _HOOK_TESTS_ONLY),
    "shield": ("tools: Read, Grep, Glob, Bash", "model: opus", "color: red", _HOOK_READONLY),
}


def frozen_frontmatter():
    """{nombre actual: {tools, model, color, hooks}} como datos fijos (copia)."""
    return {role: {"tools": t, "model": m, "color": c, "hooks": list(h)} for role, (t, m, c, h) in _FROZEN.items()}


def frontmatter_parts(text):
    """Mismas partes que frozen_frontmatter, leidas del texto (LF) de un agente. El bloque hooks: va de la linea
    `hooks:` al cierre del frontmatter; ValueError si falta una linea o el frontmatter no cierra."""
    lines = text.split("\n")
    if lines[0] != "---":
        raise ValueError("la primera linea no es ---")
    close = lines.index("---", 1)
    front = lines[1:close]
    parts = {}
    for key in ("tools", "model", "color"):
        found = [l for l in front if l.startswith(key + ":")]
        if len(found) != 1:
            raise ValueError("debe haber una linea %s:" % key)
        parts[key] = found[0]
    parts["hooks"] = front[front.index("hooks:"):] if "hooks:" in front else []
    return parts


def repo_texts():
    """Los once textos gestionados tal como estan en el repositorio (bytes LF), con su ruta como clave."""
    paths = ["agents/%s.md" % r for r in ar.roles()] + ["rules/agentes.md", "docs/agentes.md"]
    return {path: ar.repo_text(path).encode("iso-8859-1") for path in sorted(paths)}


def repo_hashes():
    """{ruta: sha256 canonico} de los once textos del repositorio, ordenado por ruta."""
    texts = repo_texts()
    return {path: bm.canonical_sha256(texts[path]) for path in sorted(texts)}


# --- nombres vigentes en los textos (casos 3 y 4) ---

def word_counts(text, names):
    """Como aliases_ref.inventory pero para una lista de nombres cualquiera (sin excepciones de palabra):
    (counts {nombre: [minuscula, Capitalizada, MAYUSCULAS]}, other [(nombre, palabra)])."""
    counts = {n: [0, 0, 0] for n in names}
    other = []
    for m in ar._LETTER.finditer(text):
        word = m.group(0)
        low = word.lower()
        for name in [n for n in names if n in low]:
            variants = ar.form_variants(name)
            if word in variants:
                counts[name][variants.index(word)] += 1
            else:
                other.append((name, word))
    return counts, other


def foreign_letter_hits(text, names=None):
    """Como aliases_ref.foreign_letter_hits (misma condicion) pero para los nombres nuevos: [(nombre, caracter)]
    de los nombres (sin distinguir mayusculas) pegados a una letra o marca combinante que no es ASCII ni U+00C0 a
    U+00FF. `text` es Unicode (UTF-8 decodificado)."""
    names = sorted(RENAME.values()) if names is None else names
    hits = []
    for name in names:
        for m in re.finditer(re.escape(name), text, re.I):
            for ch in (text[m.start() - 1] if m.start() else "", text[m.end()] if m.end() < len(text) else ""):
                if (ch and ord(ch) > 0x7F and (ch.isalpha() or unicodedata.category(ch).startswith("M"))
                        and not 0xC0 <= ord(ch) <= 0xFF):
                    hits.append((name, ch))
    return hits
