"""Auxiliar de las pruebas de alias (Fase 4). No es un test_*.py.

Segunda implementacion, independiente de PowerShell, de la validacion de la tabla de alias (3.2 del
plan), de las formas del alias, de la transformacion de textos con limite de palabra (3.5) y del
estado esquema 3 (3.4): contra ella se compararan los bytes que escriba el instalador. Lee las listas
cerradas de install.ps1 ($AliasRoles, $ReservedAliases, $YamlWords) con levels_ref.read_ps_list.
Solo biblioteca estandar.
"""

import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

import build_manifest as bm  # noqa: E402
import levels_ref as lr  # noqa: E402
import names  # noqa: E402

ROOT = lr.ROOT

# Palabras que llevan el nombre de un rol como subcadena sin ser el agente: no se tocan (limite de palabra).
# Por rol: hoy solo el escritor (las palabras espanolas con su nombre dentro); cualquier otro rol no tiene ninguna.
SCRIBE_WORDS = {names.WRITER: {"escribe", "escriben", "describe", "reescribe", "sobrescribe"}}

# Limite de palabra (3.5, enmienda E1), sobre el texto decodificado en ISO-8859-1 (un byte, un caracter):
# letra = [A-Za-z0-9_] o la pareja \xC3 + [\x80-\xBF] (U+00C0 a U+00FF en UTF-8); todo lo demas es limite.
# Dos lookbehind de ancho fijo y dos lookahead, sin IGNORECASE.
_LB = r"(?<![A-Za-z0-9_])(?<!\xc3[\x80-\xbf])"
_LA = r"(?![A-Za-z0-9_])(?!\xc3[\x80-\xbf])"
_LETTER = re.compile(r"(?:[A-Za-z0-9_]|\xc3[\x80-\xbf])+")
_ALIAS_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_KEY_LINE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*:(?: |\Z)")
_YAML_INDICATORS = "\"'[{|>&*!%@`"


def roles():
    return lr.read_ps_list("AliasRoles")


def reserved():
    return lr.read_ps_list("ReservedAliases")


def yaml_words():
    return lr.read_ps_list("YamlWords")


# --- formas y transformacion de texto ---

def effective(table):
    """Pares rol -> alias con alias distinto del rol (la tabla efectiva)."""
    return {r: a for r, a in table.items() if a != r}


def form_variants(word):
    """Tres formas de un nombre en minuscula: minuscula, Capitalizada y MAYUSCULAS."""
    return [word, word[0].upper() + word[1:], word.upper()]


def forms(table):
    """Diccionario ordinal forma de rol -> forma de alias, sobre la tabla efectiva. Un dict de Python es
    ordinal; @agent-<rol> no tiene entrada propia: sale de la forma minuscula (el - es limite)."""
    out = {}
    for role, alias in effective(table).items():
        for src, dst in zip(form_variants(role), form_variants(alias)):
            out[src] = dst
    return out


def _pattern(words):
    keys = sorted(words, key=lambda k: (-len(k), k))
    return re.compile(_LB + "(?:" + "|".join(re.escape(k) for k in keys) + ")" + _LA)


def transform_text(text, table):
    """Reemplazo de formas con limite de palabra, en una sola pasada y sin IGNORECASE."""
    mapping = forms(table)
    if not mapping:
        return text
    return _pattern(mapping).sub(lambda m: mapping[m.group(0)], text)


def role_hits(text, table):
    """Formas con limite de palabra de un rol con alias que quedan en el texto (residuo)."""
    mapping = forms(table)
    if not mapping:
        return []
    return [m.group(0) for m in _pattern(mapping).finditer(text)]


# --- validacion de la tabla (3.2) ---

def validate_table(aliases, manifest_paths=None):
    """Primer problema de la tabla rol -> alias (texto) o None. Reglas V1 a V7 (V8 solo si se pasa la
    lista de rutas del manifiesto). Nunca nombra el valor del alias."""
    known = roles()
    if not isinstance(aliases, dict):
        return "aliases debe ser un objeto"
    for key in aliases:
        if key not in known:
            return "rol desconocido en aliases: " + key
    for role in known:
        if role not in aliases:
            continue
        value = aliases[role]
        if not isinstance(value, str):
            return "el alias de %s debe ser texto" % role
        if not _ALIAS_RE.match(value):
            return ("el alias de %s solo admite a-z, 0-9, _ y -, empieza por letra y tiene hasta 64 caracteres"
                    % role)
        if value in yaml_words():
            return "el alias de %s es una palabra reservada de YAML" % role
        if not bm.ALLOWED.match("agents/" + value + ".md"):
            return "el alias de %s es un nombre reservado de Windows" % role
        if value in reserved():
            return "el alias de %s es el nombre de un agente integrado de Claude Code" % role
    eff = effective(aliases)
    for role in known:
        if role not in eff:
            continue
        alias = eff[role]
        if alias in known:
            return "el alias de %s es el nombre de otro agente de SyncLayer" % role
        if any(re.search(_LB + re.escape(r) + _LA, alias) for r in known):
            return "el alias de %s contiene el nombre de un agente de SyncLayer" % role
    seen = {}
    for role in known:
        if role not in eff:
            continue
        if eff[role] in seen:
            return "%s y %s tienen el mismo alias" % (seen[eff[role]], role)
        seen[eff[role]] = role
    if manifest_paths is not None:
        # V8 completa (enmienda E2): el destino de TODA alias efectiva se compara con TODAS las rutas del
        # manifiesto, este o no el archivo del rol de origen en el manifiesto.
        taken = set(manifest_paths)
        for role in known:
            if role in eff and "agents/%s.md" % eff[role] in taken:
                return "el alias de %s coincide con otro archivo del manifiesto" % role
    return None


def dest_for(path, table):
    """Ruta de destino de una ruta del manifiesto: agents/<alias>.md si el rol tiene alias efectivo."""
    m = re.fullmatch(r"agents/([a-z0-9_-]+)\.md", path)
    if m and m.group(1) in effective(table):
        return "agents/%s.md" % effective(table)[m.group(1)]
    return path


# --- transformacion de agentes y textos (3.5) ---

def _canon_lines(data):
    return data.replace(b"\r\n", b"\n").decode("iso-8859-1").split("\n")


def _split(lines):
    if lines[0] != "---":
        raise ValueError("la primera linea no es ---")
    close = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
    if close is None:
        raise ValueError("frontmatter sin cierre")
    return close


def _description_ok(lines, idx, close):
    line = lines[idx]
    if not re.fullmatch(r"description: [\x20-\x7e]+", line):
        return False
    if line[len("description: "):][0] in _YAML_INDICATORS:
        return False
    nxt = lines[idx + 1]
    return nxt == "---" or bool(_KEY_LINE.match(nxt) and not nxt.startswith(" "))


def transform_agent(data, role, table):
    """Bytes canonicos de agents/<role>.md -> bytes con los alias de la tabla. ValueError si el frontmatter
    no es transformable o falla la autocomprobacion. Tabla efectiva vacia: los bytes canonicos."""
    canon = data.replace(b"\r\n", b"\n")
    if not effective(table):
        return canon
    lines = _canon_lines(data)
    close = _split(lines)
    front = range(1, close)
    for i in front:
        if re.search(r"[^\x20-\x7e]", lines[i]):
            raise ValueError("el frontmatter tiene un caracter fuera de ASCII imprimible")
    names = [i for i in front if lines[i].startswith("name:")]
    if len(names) != 1 or lines[names[0]] != "name: " + role:
        raise ValueError("debe haber exactamente una linea name: " + role)
    nxt = lines[names[0] + 1]
    if not (nxt == "---" or _KEY_LINE.match(nxt)):
        raise ValueError("la linea name: tiene continuacion en la linea siguiente")
    descs = [i for i in front if lines[i].startswith("description:")]
    if len(descs) != 1 or not _description_ok(lines, descs[0], close):
        raise ValueError("debe haber exactamente una linea description: de una sola linea")
    for i in front:
        if i not in (names[0], descs[0]) and role_hits(lines[i], table):
            raise ValueError("referencia a un rol en una linea del frontmatter que no se transforma")
    out = list(lines)
    if role in effective(table):
        out[names[0]] = "name: " + effective(table)[role]
    out[descs[0]] = transform_text(lines[descs[0]], table)
    if close + 1 < len(lines):
        body = transform_text("\n".join(lines[close + 1:]), table).split("\n")
        out = out[:close + 1] + body
    # Autocomprobacion.
    if len(out) != len(lines):
        raise ValueError("autocomprobacion: cambia el numero de lineas")
    if _split(out) != close:
        raise ValueError("autocomprobacion: cambia el cierre del frontmatter")
    for i in front:
        if i not in (names[0], descs[0]) and out[i] != lines[i]:
            raise ValueError("autocomprobacion: cambia una linea del frontmatter")
    if out[names[0]] != "name: " + effective(table).get(role, role):
        raise ValueError("autocomprobacion: name: incorrecto")
    if not _description_ok(out, descs[0], close):
        raise ValueError("autocomprobacion: description: ya no es de una linea")
    keys = [m.group(1) for m in (re.match(r"([A-Za-z][A-Za-z0-9_-]*):", out[i]) for i in front
                                 if not out[i].startswith(" ")) if m]
    if len(keys) != len(set(keys)):
        raise ValueError("autocomprobacion: claves repetidas")
    _check_pass(lines, out, table, skip=(names[0],))
    return "\n".join(out).encode("iso-8859-1")


def transform_doc(data, table):
    """rules/agentes.md y docs/agentes.md: todo el contenido pasa por transform_text."""
    canon = data.replace(b"\r\n", b"\n")
    if not effective(table):
        return canon
    text = canon.decode("iso-8859-1")
    out = transform_text(text, table)
    if out.count("\n") != text.count("\n"):
        raise ValueError("autocomprobacion: cambia el numero de lineas")
    _check_pass(text.split("\n"), out.split("\n"), table)
    return out.encode("iso-8859-1")


def _check_pass(src_lines, out_lines, table, skip=()):
    """Recorrido en paralelo: fuera de las coincidencias, igual; en ellas, el texto esperado; sin residuo."""
    mapping = forms(table)
    pat = _pattern(mapping)
    for i, (a, b) in enumerate(zip(src_lines, out_lines)):
        if i in skip:
            continue  # la linea name: se reescribe entera (ya comprobada)
        pos = 0
        expect = []
        for m in pat.finditer(a):
            expect.append(a[pos:m.start()])
            expect.append(mapping[m.group(0)])
            pos = m.end()
        expect.append(a[pos:])
        want = "".join(expect)
        if want != b:
            raise ValueError("autocomprobacion: una linea difiere de lo esperado")
    if any(role_hits(l, table) for l in out_lines):
        raise ValueError("autocomprobacion: queda una forma de un rol con alias")


# --- estado esquema 3 (3.4) ---

def state_for3(manifest, out_hashes=None, level=5, dests=None):
    """Estado esquema 3 esperado, en bytes. `dests` {ruta: ruta de destino}; `dest` va en todas las
    entradas (igual a path en las que no tienen alias). Orden de claves fijo."""
    if isinstance(manifest, (bytes, bytearray)):
        manifest = manifest.decode("utf-8")
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    out_hashes = {} if out_hashes is None else out_hashes
    dests = {} if dests is None else dests
    files = []
    for entry in manifest["files"]:
        path = entry["path"]
        files.append({
            "path": path,
            "sha256": entry["sha256"],
            "written": out_hashes.get(path, entry["sha256"]),
            "level": level,
            "dest": dests.get(path, path),
        })
    state = {"schema": 3, "algorithm": "sha256", "eol": "lf", "files": files}
    return (json.dumps(state, indent=2, ensure_ascii=True) + "\n").encode("ascii")


STATE_ROOT_KEYS = {"schema", "algorithm", "eol", "files"}
STATE3_ENTRY_KEYS = {"path", "sha256", "written", "level", "dest"}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
DEST_MAX = 74  # agents/ + alias de hasta 64 + .md


def _bad_path(value):
    return (not isinstance(value, str) or ".." in value or "\\" in value or ":" in value
            or value.startswith("/") or not bm.ALLOWED.match(value))


def state3_problem(state, manifest_paths=()):
    """Primer problema de un estado esquema 3 (dict) segun 3.4 del plan, o None si es valido. Segunda
    implementacion, independiente de Read-State: `manifest_paths` son las rutas del manifiesto (un dest distinto
    de su path no puede ser la ruta de otro rol). Todo estado con problema es AUSENTE para el instalador."""
    if not isinstance(state, dict):
        return "raiz"
    if set(state) - STATE_ROOT_KEYS:
        return "clave desconocida en la raiz"
    if type(state.get("schema")) is not int or state["schema"] != 3:
        return "schema"
    if state.get("algorithm") != "sha256" or state.get("eol") != "lf":
        return "algorithm o eol"
    files = state.get("files")
    if not isinstance(files, list) or not files:
        return "files"
    paths, dests = [], []
    for entry in files:
        if not isinstance(entry, dict) or set(entry) - STATE3_ENTRY_KEYS:
            return "clave desconocida en una entrada"
        path = entry.get("path")
        if _bad_path(path) or path in paths:
            return "path"
        if not isinstance(entry.get("sha256"), str) or not _HEX64.match(entry["sha256"]):
            return "sha256"
        if not isinstance(entry.get("written"), str) or not _HEX64.match(entry["written"]):
            return "written"
        level = entry.get("level")
        if type(level) is not int or not 1 <= level <= 5:
            return "level"
        if "dest" not in entry:
            return "falta dest"
        dest = entry["dest"]
        if _bad_path(dest):
            return "dest"
        if path.startswith("agents/") != dest.startswith("agents/") and dest != path:
            return "dest fuera de agents/ o distinto en un archivo fijo"
        if not path.startswith("agents/") and dest != path:
            return "dest distinto en un archivo fijo"
        if dest != path and len(dest) > DEST_MAX:
            return "dest demasiado largo"
        if dest in dests:
            return "dest repetido"
        paths.append(path)
        dests.append(dest)
    for path, dest in zip(paths, dests):
        if dest != path and (dest in paths or dest in manifest_paths):
            return "dest es la ruta de otro rol"
    return None


def state3_orphans(state, manifest_paths):
    """Huerfanos (3.7): destinos del estado previo que no son destino actual de ningun rol del manifiesto (hoy el
    destino de un rol es su ruta). Estado invalido: ninguno. Orden del estado."""
    if state3_problem(state, manifest_paths) is not None:
        return []
    return [f["dest"] for f in state["files"] if f["dest"] not in manifest_paths]


def prev_by_dest(state):
    """prevByDest (3.6): ruta de destino del estado -> hash escrito."""
    return {f["dest"]: f["written"] for f in state["files"]}


# --- comprobaciones sobre los textos del repositorio (inventario y zonas sensibles) ---

def repo_text(rel):
    """Texto (ISO-8859-1, LF) de un archivo del repositorio."""
    with open(os.path.join(ROOT, *rel.split("/")), "rb") as f:
        return f.read().replace(b"\r\n", b"\n").decode("iso-8859-1")


def text_files():
    """Los once archivos de texto gestionados que se transforman: nueve agentes, reglas y guia."""
    return ["agents/%s.md" % r for r in roles()] + ["rules/agentes.md", "docs/agentes.md"]


def inventory(text):
    """Clasifica cada palabra (con la definicion de letra de E1) que contiene un rol, sin distinguir mayusculas.

    Devuelve (counts, other): counts {rol: [minuscula, Capitalizada, MAYUSCULAS]} de formas que casan
    (reemplazables); other: palabras que no son ninguna forma ni una de SCRIBE_WORDS del rol (sin clasificar, por
    ejemplo el nombre de un rol capitalizado + e acentuada o el nombre + `2`). Una forma pegada a puntuacion, comillas angulares, rayas o espacio duro
    es una palabra por si sola: cuenta como reemplazable."""
    counts = {r: [0, 0, 0] for r in roles()}
    other = []
    for m in _LETTER.finditer(text):
        word = m.group(0)
        low = word.lower()
        for role in [r for r in roles() if r in low]:
            variants = form_variants(role)
            if word in variants:
                counts[role][variants.index(word)] += 1
            elif low in SCRIBE_WORDS.get(role, ()):
                continue
            else:
                other.append((role, word))
    return counts, other


def foreign_letter_hits(text):
    """Roles (sin distinguir mayusculas) pegados a una letra o marca combinante que no es ASCII ni U+00C0 a U+00FF. `text` es
    Unicode (UTF-8 decodificado): esas letras serian limite para el instalador y el reemplazo las cruzaria."""
    hits = []
    for role in roles():
        for m in re.finditer(re.escape(role), text, re.I):
            for ch in (text[m.start() - 1] if m.start() else "", text[m.end()] if m.end() < len(text) else ""):
                # Tambien las marcas combinantes (NFD): el acento quedaria sobre la primera letra del alias.
                if (ch and ord(ch) > 0x7F and (ch.isalpha() or unicodedata.category(ch).startswith("M"))
                        and not 0xC0 <= ord(ch) <= 0xFF):
                    hits.append((role, ch))
    return hits


def utf8_text(rel):
    """Texto Unicode de un archivo del repositorio; UnicodeDecodeError si no es UTF-8 valido."""
    with open(os.path.join(ROOT, *rel.split("/")), "rb") as f:
        return f.read().replace(b"\r\n", b"\n").decode("utf-8")


_FENCE = re.compile(r"^(`{3,}|~{3,})")


def sensitive_zones(text):
    """Trozos de texto donde un nombre de rol no debe aparecer: lineas dentro de un bloque cercado,
    destinos de enlaces `](...)` y `[x]: destino`, y URLs."""
    zones = []
    inside = False
    for line in text.split("\n"):
        if _FENCE.match(line):
            inside = not inside
            continue
        if inside:
            zones.append(line)
    zones += re.findall(r"\]\(([^)]*)\)", text)
    zones += re.findall(r"^\[[^\]]+\]:\s*(\S+)", text, re.M)
    zones += re.findall(r"https?://\S+", text)
    return zones


def role_hits_in_zones(text):
    """Apariciones (sin distinguir mayusculas, sin limite de palabra) de un rol en las zonas sensibles."""
    return [(z, r) for z in sensitive_zones(text) for r in roles() if r in z.lower()]
