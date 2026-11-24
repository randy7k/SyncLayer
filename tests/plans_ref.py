"""Auxiliar de las pruebas de la carpeta de planes (Fase 5). No es un test_*.py.

Segunda implementacion, independiente de PowerShell, de la validacion de plans_dir (3.1.2 del plan) y de
la transformacion de textos (3.1.3): contra ella se compararan los bytes que escriba el instalador. La
busqueda es un recorrido manual con str.find (no usa la expresion del script) y la autocomprobacion usa la
expresion con lookbehind de ancho fijo: dos caminos distintos para el mismo resultado. Sin re.I ni lookbehind
de ancho variable. Compone aliases_ref y levels_ref en expected_bytes. Solo biblioteca estandar.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aliases_ref as ar  # noqa: E402
import levels_ref as lr  # noqa: E402

ROOT = lr.ROOT

# Datos de 3.1.2. install.ps1 debe traer los mismos (caso 1); script_constants() los lee de alli.
DEFAULT = "docs/plans"
PATTERN_PS = r"^[a-z0-9][a-z0-9_-]{0,31}(/[a-z0-9][a-z0-9_-]{0,31}){0,3}\z"
MAX_LENGTH = 64

# Nombres de dispositivo de Windows (L4); el caso 9 los compara con $AllowedPattern de install.ps1.
DEVICE_NAMES = ["con", "prn", "aux", "nul"] + ["com%d" % i for i in range(10)] + ["lpt%d" % i for i in range(10)]

_SEGMENT = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
LITERAL = "docs/plans/"
# Caracteres que, justo antes del literal, impiden la coincidencia.
_LEFT_BLOCK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./-")
# Misma regla para la autocomprobacion, en forma de expresion (lookbehind de ancho fijo, sin bandera de mayusculas).
_MATCH_RE = re.compile(r"(?<![A-Za-z0-9_./-])docs/plans/")

MSG_TYPE = "plans_dir debe ser texto"
MSG_SHAPE = ("plans_dir solo admite de 1 a 4 carpetas separadas por /, en minusculas (a-z, 0-9, _ y -; cada una "
             "empieza por letra o digito y tiene hasta 32 caracteres) y hasta 64 caracteres en total")
MSG_DEVICE = "plans_dir contiene un nombre reservado de Windows"
MSG_ROLE = "plans_dir contiene el nombre de un agente de SyncLayer"


def script_constants(text=None):
    """(default, patron, longitud maxima) leidos de install.ps1: $PlansDirDefault, $PlansDirPattern y
    $PlansDirMaxLength, cada uno en una sola linea. ValueError si falta alguno o esta repetido."""
    text = lr.script_text() if text is None else text.replace("\r\n", "\n")

    def one(name, rx):
        found = re.findall(r"^\$" + name + r" = " + rx + r"$", text, re.M)
        if len(found) != 1:
            raise ValueError("debe haber exactamente una linea $%s en install.ps1" % name)
        return found[0]

    return (one("PlansDirDefault", r"'([^']*)'"), one("PlansDirPattern", r"'([^']*)'"),
            int(one("PlansDirMaxLength", r"([0-9]+)")))


def validate_plans_dir(value):
    """Primer problema de plans_dir (texto) o None. Reglas L1 a L5 de 3.1.2. Nunca nombra el valor."""
    if not isinstance(value, str):
        return MSG_TYPE
    segments = value.split("/")
    if (len(value) > MAX_LENGTH or not 1 <= len(segments) <= 4
            or not all(_SEGMENT.fullmatch(s) for s in segments)):
        return MSG_SHAPE
    if any(s in DEVICE_NAMES for s in segments):
        return MSG_DEVICE
    roles = ar.roles()
    if any(piece in roles for s in segments for piece in s.split("-")):
        return MSG_ROLE
    return None


def effective(plans_dir):
    """Hay carpeta efectiva si hay valor y es distinto de la carpeta por defecto."""
    return plans_dir is not None and plans_dir != DEFAULT


def _find_matches(text):
    """Posiciones de cada coincidencia del literal con limite izquierdo, de izquierda a derecha."""
    hits = []
    pos = 0
    while True:
        idx = text.find(LITERAL, pos)
        if idx < 0:
            return hits
        if idx == 0 or text[idx - 1] not in _LEFT_BLOCK:
            hits.append(idx)
        pos = idx + 1


def _replace(text, plans_dir):
    out = []
    pos = 0
    for idx in _find_matches(text):
        out.append(text[pos:idx])
        out.append(plans_dir + "/")
        pos = idx + len(LITERAL)
    out.append(text[pos:])
    return "".join(out)


def _check(src, out, plans_dir):
    """Autocomprobacion: recorrido en paralelo de entrada y salida (fuera de las coincidencias iguales; en
    cada una, el texto esperado), mismo numero de lineas y numero de reemplazos = coincidencias."""
    if src.count("\n") != out.count("\n"):
        raise ValueError("autocomprobacion: cambia el numero de lineas")
    matches = list(_MATCH_RE.finditer(src))
    if len(matches) != len(_find_matches(src)):
        raise ValueError("autocomprobacion: las dos busquedas difieren")
    pos = 0
    cur = 0
    for m in matches:
        gap = src[pos:m.start()]
        if out[cur:cur + len(gap)] != gap:
            raise ValueError("autocomprobacion: cambia texto fuera de una coincidencia")
        cur += len(gap)
        want = plans_dir + "/"
        if out[cur:cur + len(want)] != want:
            raise ValueError("autocomprobacion: una coincidencia no tiene el texto esperado")
        cur += len(want)
        pos = m.end()
    if out[cur:] != src[pos:]:
        raise ValueError("autocomprobacion: cambia texto despues de la ultima coincidencia")


def _guard(plans_dir):
    problem = validate_plans_dir(plans_dir)
    if problem is not None:
        raise ValueError(problem)


def transform_text(data, plans_dir):
    """Bytes (CRLF o LF) de un texto -> bytes canonicos (LF) con la carpeta de planes. Sin carpeta efectiva
    (None o la de por defecto): los bytes canonicos. ValueError si la carpeta no es valida o falla la
    autocomprobacion."""
    canon = data.replace(b"\r\n", b"\n")
    if not effective(plans_dir):
        return canon
    _guard(plans_dir)
    src = canon.decode("iso-8859-1")
    out = _replace(src, plans_dir)
    _check(src, out, plans_dir)
    return out.encode("iso-8859-1")


def transform_agent(data, plans_dir):
    """Como transform_text para un agente: solo el cuerpo; una coincidencia en el frontmatter es un error."""
    canon = data.replace(b"\r\n", b"\n")
    if not effective(plans_dir):
        return canon
    _guard(plans_dir)
    lines = canon.decode("iso-8859-1").split("\n")
    if lines[0] != "---":
        raise ValueError("la primera linea no es ---")
    close = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
    if close is None:
        raise ValueError("frontmatter sin cierre")
    if _find_matches("\n".join(lines[:close + 1])):
        raise ValueError("referencia a la carpeta de planes en el frontmatter")
    head = lines[:close + 1]
    body_lines = lines[close + 1:]
    out = list(head)
    if body_lines:
        body = "\n".join(body_lines)
        new_body = _replace(body, plans_dir)
        _check(body, new_body, plans_dir)
        out += new_body.split("\n")
    if len(out) != len(lines):
        raise ValueError("autocomprobacion: cambia el numero de lineas")
    return "\n".join(out).encode("iso-8859-1")


def _agent_role(path):
    m = re.fullmatch(r"agents/([a-z0-9_-]+)\.md", path)
    return m.group(1) if m and m.group(1) in ar.roles() else None


def _step_alias(path, data, table):
    role = _agent_role(path)
    if role is not None:
        return ar.transform_agent(data, role, table)
    if path in ("rules/agentes.md", "docs/agentes.md"):
        return ar.transform_doc(data, table)
    return data.replace(b"\r\n", b"\n")


def _step_plans(path, data, plans_dir):
    if _agent_role(path) is not None:
        return transform_agent(data, plans_dir)
    if path in ("rules/agentes.md", "docs/agentes.md"):
        return transform_text(data, plans_dir)
    return data.replace(b"\r\n", b"\n")


def _step_level(path, data, level):
    role = _agent_role(path)
    if level != 5 and role is not None and role in lr.read_ps_list("LevelAgents"):
        model, effort = lr.read_script_table()[(level, role)]
        return lr.render_expected(data, model, effort)
    return data.replace(b"\r\n", b"\n")


def expected_bytes(path, canon, level=5, aliases=None, plans_dir=None, order=("alias", "plans", "level")):
    """Bytes esperados en el destino para un archivo del manifiesto (ruta de rol y bytes del origen): alias,
    carpeta de planes y nivel, compuestos con aliases_ref, esta referencia y levels_ref. `order` permite
    probar que el resultado no depende del orden (caso 8). El hook nunca se transforma."""
    table = {} if aliases is None else aliases
    steps = {
        "alias": lambda d: _step_alias(path, d, table),
        "plans": lambda d: _step_plans(path, d, plans_dir),
        "level": lambda d: _step_level(path, d, level),
    }
    if sorted(order) != ["alias", "level", "plans"]:
        raise ValueError("order debe ser una permutacion de alias, plans y level")
    data = canon
    for step in order:
        data = steps[step](data)
    return data


def managed_paths():
    """Rutas de los archivos gestionados (install-manifest.json), en su orden."""
    import json
    with open(os.path.join(ROOT, "install-manifest.json"), "rb") as f:
        return [e["path"] for e in json.loads(f.read().decode("utf-8"))["files"]]


def repo_bytes(rel):
    """Bytes canonicos (LF) de un archivo gestionado del repositorio."""
    with open(os.path.join(ROOT, *rel.split("/")), "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def inventory_problems(files):
    """Problemas del inventario de `docs/plans` (caso 2) sobre {ruta: bytes}: debe aparecer exactamente 3 veces,
    una en cada uno de agents/atlas.md, rules/agentes.md y docs/agentes.md, las tres reemplazables (limite
    izquierdo), ninguna en el hook ni en un frontmatter."""
    expected = {"agents/atlas.md": 1, "rules/agentes.md": 1, "docs/agentes.md": 1}
    problems = []
    total = 0
    for rel, data in sorted(files.items()):
        text = data.replace(b"\r\n", b"\n").decode("iso-8859-1")
        n = text.count("docs/plans")
        total += n
        if n != expected.get(rel, 0):
            problems.append("%s: %d apariciones, se esperaban %d" % (rel, n, expected.get(rel, 0)))
        if len(_find_matches(text)) != n:
            problems.append("%s: una aparicion no es reemplazable" % rel)
        if rel == "hooks/agent_guard.py" and n:
            problems.append("el hook nombra la carpeta de planes")
        if _agent_role(rel) is not None and n:
            lines = text.split("\n")
            close = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
            if close is None:
                problems.append("%s: frontmatter sin cierre" % rel)
            elif "docs/plans" in "\n".join(lines[:close + 1]):
                problems.append("%s: aparicion en el frontmatter" % rel)
    if total != 3:
        problems.append("en total %d apariciones, se esperaban 3" % total)
    return problems


_SEGMENT_PLANS = re.compile(r"[A-Za-z0-9_-]+/plans/")


def segment_problems(files):
    """Un alias podria crear o destruir el literal (p. ej. `docs` sobre `forge/plans/` da `docs/plans/`): en los
    textos de {ruta: bytes} no debe haber `<segmento>/plans/` salvo `docs/plans/` (regex independiente)."""
    out = []
    for rel, data in sorted(files.items()):
        text = data.replace(b"\r\n", b"\n").decode("iso-8859-1")
        for m in _SEGMENT_PLANS.finditer(text):
            if m.group(0) != LITERAL:
                out.append("%s: aparece %s" % (rel, m.group(0)))
    return out


def zone_problems(files):
    """Apariciones de `docs/plans` en zonas sensibles (bloque cercado, destino de enlace, URL) de {ruta: bytes}."""
    out = []
    for rel, data in sorted(files.items()):
        text = data.replace(b"\r\n", b"\n").decode("iso-8859-1")
        for zone in ar.sensitive_zones(text):
            if "docs/plans" in zone:
                out.append((rel, zone))
    return out
