"""Auxiliar de las pruebas de la Fase 6 (renombrado de agentes). No es un test_*.py.

Fija la tabla RENAME (nombre actual -> nombre nuevo), produce en memoria los once textos gestionados con
la transformacion de alias de la Fase 4 (aliases_ref) y su fixture de hashes (tests/rename_expected.json,
prueba puente de T1 a T7), y guarda como datos fijos el frontmatter que el renombrado no debe tocar.
Solo biblioteca estandar. No escribe nada salvo con `python -B tests/rename_ref.py --write`.
"""

import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aliases_ref as ar  # noqa: E402

ROOT = ar.ROOT
bm = ar.bm
FIXTURE = os.path.join(HERE, "rename_expected.json")

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

# Archivos de esta fase: no cuentan en la busqueda de nombres nuevos (caso 3).
OWN_NAMES = ("rename_ref.py", "test_rename.py", "rename_expected.json")
OWN_FILES = tuple("tests/" + n for n in OWN_NAMES)

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


def new_path(path):
    """Ruta del manifiesto con el nombre nuevo: agents/<viejo>.md -> agents/<nuevo>.md; el resto igual."""
    m = re.fullmatch(r"agents/([a-z0-9_-]+)\.md", path)
    if m and m.group(1) in RENAME:
        return "agents/%s.md" % RENAME[m.group(1)]
    return path


def expected_texts(table=None, read=None):
    """Los once textos gestionados ya transformados, en bytes LF y con la ruta nueva como clave: nueve agentes
    con aliases_ref.transform_agent y rules/agentes.md y docs/agentes.md con transform_doc. `read(rel)` da los
    bytes de origen (por omision el repositorio); `table` (por omision RENAME) es la tabla rol -> nombre."""
    table = dict(RENAME) if table is None else table
    read = (lambda rel: ar.repo_text(rel).encode("iso-8859-1")) if read is None else read
    out = {}
    for role in ar.roles():
        path = "agents/%s.md" % role
        dest = "agents/%s.md" % table.get(role, role)
        out[dest] = ar.transform_agent(read(path), role, table)
    for rel in ("rules/agentes.md", "docs/agentes.md"):
        out[rel] = ar.transform_doc(read(rel), table)
    return out


def expected_hashes(table=None, read=None):
    """{ruta nueva: sha256 canonico}, ordenado por ruta."""
    texts = expected_texts(table, read)
    return {path: bm.canonical_sha256(texts[path]) for path in sorted(texts)}


def repo_texts():
    """Los once textos gestionados tal como estan en el repositorio (bytes LF), con su ruta como clave. Tras el
    cambio de T7 son los mismos que produce expected_texts() sobre el repositorio anterior."""
    paths = ["agents/%s.md" % r for r in ar.roles()] + ["rules/agentes.md", "docs/agentes.md"]
    return {path: ar.repo_text(path).encode("iso-8859-1") for path in sorted(paths)}


def repo_hashes():
    """{ruta: sha256 canonico} de los once textos del repositorio, ordenado por ruta."""
    texts = repo_texts()
    return {path: bm.canonical_sha256(texts[path]) for path in sorted(texts)}


def fixture_bytes(hashes=None):
    """Contenido de tests/rename_expected.json: ASCII, indent=2, LF y salto final. `hashes` (por omision
    expected_hashes(), solo valido con el repositorio sin renombrar) es el diccionario ruta -> hash."""
    hashes = expected_hashes() if hashes is None else hashes
    data = {"schema": 1, "algorithm": "sha256", "eol": "lf", "files": hashes}
    return (json.dumps(data, indent=2, ensure_ascii=True) + "\n").encode("ascii")


# --- busqueda de nombres nuevos (caso 3) ---

def scan_files():
    """{ruta relativa: bytes} de lo que no debe nombrar aun a los agentes nuevos: los doce archivos gestionados,
    install.ps1, tools/ y tests/ (sin __pycache__ ni los archivos de esta fase)."""
    paths = bm.managed_files(ROOT) + ["install.ps1"]
    for sub in ("tools", "tests"):
        for base, dirs, names in os.walk(os.path.join(ROOT, sub)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in names:
                if name.endswith(".pyc"):
                    continue
                paths.append(os.path.relpath(os.path.join(base, name), ROOT).replace(os.sep, "/"))
    out = {}
    for rel in sorted(set(paths)):
        if rel in OWN_FILES:
            continue
        with open(os.path.join(ROOT, *rel.split("/")), "rb") as f:
            out[rel] = f.read()
    return out


def new_name_hits(files, names=None):
    """[(ruta, nombre)] de los nombres nuevos hallados como subcadena, sin distinguir mayusculas. `files` es
    {ruta: bytes}: la prueba muta una copia en memoria."""
    names = sorted(RENAME.values()) if names is None else names
    hits = []
    for rel in sorted(files):
        low = files[rel].lower()
        hits += [(rel, n) for n in names if n.encode("ascii") in low]
    return hits


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


MSG_REFUSED = "se niega: los roles del repositorio ya no son los de antes del renombrado; no se regenera el fixture"


def main(argv):
    """`--write` regenera el fixture solo si los roles vivos son atlas mas las claves de RENAME (repositorio sin
    renombrar); si no, mensaje fijo y salida 1. Cualquier otro argumento: uso y salida 2."""
    if argv == ["--write"]:
        if set(ar.roles()) != {"atlas"} | set(RENAME):
            print(MSG_REFUSED, file=sys.stderr)
            return 1
        with open(FIXTURE, "wb") as f:
            f.write(fixture_bytes())
        print("escrito " + os.path.basename(FIXTURE))
        return 0
    print("uso: python -B tests/rename_ref.py --write")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
