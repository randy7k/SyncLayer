"""Auxiliar de las pruebas de niveles (Fase 3). No es un test_*.py.

Lee la tabla de niveles de install.ps1 ($LevelRows) y la documentada en el README (entre los
marcadores), y trae el renderizador de referencia de frontmatter (3.3 del plan): una segunda
implementacion, independiente de PowerShell, contra la que se comparan los bytes del instalador.
Solo biblioteca estandar.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "install.ps1")
README = os.path.join(ROOT, "README.md")
AGENTS_DIR = os.path.join(ROOT, "agents")

BEGIN_MARK = "<!-- niveles:inicio -->"
END_MARK = "<!-- niveles:fin -->"
NO_EFFORT = "-"


def _read_text(path):
    with open(path, "rb") as f:
        # Con core.autocrlf git deja el archivo en CRLF: se normaliza antes de usar anclas de fin de linea.
        return f.read().decode("utf-8").replace("\r\n", "\n")


def script_text(path=SCRIPT):
    return _read_text(path)


def read_ps_list(name, text=None):
    """Lista `$name = @('a', 'b', ...)` de una sola linea de install.ps1."""
    text = script_text() if text is None else text.replace("\r\n", "\n")
    m = re.search(r"^\$" + re.escape(name) + r" = @\((.*)\)$", text, re.M)
    if m is None:
        raise ValueError("no se encontro $%s en install.ps1" % name)
    return re.findall(r"'([^']*)'", m.group(1))


def read_level_rows(text=None):
    """Filas de $LevelRows como tuplas (nivel:int, agente, modelo, esfuerzo), en el orden del script."""
    text = script_text() if text is None else text.replace("\r\n", "\n")
    m = re.search(r"^\$LevelRows = @\(\n(.*?)^\)$", text, re.M | re.S)
    if m is None:
        raise ValueError("no se encontro $LevelRows en install.ps1")
    rows = []
    for raw in re.findall(r"'([^']*)'", m.group(1)):
        parts = raw.split("|")
        if len(parts) != 4:
            raise ValueError("fila mal formada: %r" % raw)
        rows.append((int(parts[0]), parts[1], parts[2], parts[3]))
    return rows


def table_from_rows(rows):
    """{(nivel, agente): (modelo, esfuerzo)}; falla si hay una clave repetida."""
    table = {}
    for level, agent, model, effort in rows:
        if (level, agent) in table:
            raise ValueError("fila repetida: %r" % ((level, agent),))
        table[(level, agent)] = (model, effort)
    return table


def read_script_table(text=None):
    return table_from_rows(read_level_rows(text))


def _cell(cell):
    """Celda del README `modelo`, esfuerzo -> (modelo, esfuerzo); la raya larga es sin effort:."""
    parts = [p.strip().strip("`") for p in cell.split(", ")]
    if len(parts) != 2 or not parts[0]:
        raise ValueError("celda mal formada: %r" % cell)
    effort = NO_EFFORT if parts[1] in ("—", "-") else parts[1]
    return parts[0], effort


def read_readme_table(text=None):
    """Tabla del README entre los marcadores: {(nivel, agente): (modelo, esfuerzo)}, niveles 1 a 5."""
    text = _read_text(README) if text is None else text.replace("\r\n", "\n")
    if text.count(BEGIN_MARK) != 1 or text.count(END_MARK) != 1:
        raise ValueError("el README debe tener un marcador de inicio y uno de fin de la tabla de niveles")
    body = text.split(BEGIN_MARK, 1)[1].split(END_MARK, 1)[0]
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    if len(lines) < 3:
        raise ValueError("la tabla del README esta vacia")
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    levels = []
    for h in header[1:]:
        m = re.match(r"Nivel (\d)\b", h)
        if m is None:
            raise ValueError("cabecera inesperada: %r" % h)
        levels.append(int(m.group(1)))
    table = {}
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(levels) + 1:
            raise ValueError("fila con columnas de mas o de menos: %r" % line)
        agent = cells[0].strip("`")
        for level, cell in zip(levels, cells[1:]):
            if (level, agent) in table:
                raise ValueError("celda repetida: %r" % ((level, agent),))
            table[(level, agent)] = _cell(cell)
    return table


def repo_frontmatter(name):
    """Lineas del frontmatter de agents/<name>.md del repositorio (sin los separadores)."""
    lines = _read_text(os.path.join(AGENTS_DIR, name + ".md")).split("\n")
    if lines[0] != "---":
        raise ValueError("%s no empieza por ---" % name)
    end = lines.index("---", 1)
    return lines[1:end]


def state_for(manifest, out_hashes=None, level=5):
    """Estado esquema 2 esperado (3.4 del plan), en bytes: segunda implementacion, independiente de
    PowerShell. `manifest` es el texto, los bytes o el dict de install-manifest.json (schema 1);
    `out_hashes` {ruta: hash de lo escrito} (por defecto el sha256 del origen: nivel 5); `level` el
    nivel de la instalacion, igual en todas las entradas. Orden de `files`: el del manifiesto."""
    if isinstance(manifest, (bytes, bytearray)):
        manifest = manifest.decode("utf-8")
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    out_hashes = {} if out_hashes is None else out_hashes
    files = []
    for entry in manifest["files"]:
        path = entry["path"]
        files.append({
            "path": path,
            "sha256": entry["sha256"],
            "written": out_hashes.get(path, entry["sha256"]),
            "level": level,
        })
    state = {"schema": 2, "algorithm": "sha256", "eol": "lf", "files": files}
    return (json.dumps(state, indent=2, ensure_ascii=True) + "\n").encode("ascii")


_KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):")


def _front_keys(lines):
    return [m.group(1) for m in (_KEY.match(l) for l in lines) if m]


def render_expected(data, model, effort):
    """Referencia de 3.3: bytes canonicos de un agente + celda -> bytes a escribir.

    Lanza ValueError si el frontmatter no es renderizable. `effort` '-' no toca el esfuerzo.
    Reglas de falla cerrada (un origen manipulado no puede dejar YAML distinto), sobre las lineas entre los dos
    `---`: (1) solo bytes 0x20 a 0x7E (sin CR, tabulador, NEL, U+2028, NBSP, BOM...); (2) toda linea sin sangria
    tiene la forma `clave:` seguida de espacio o de fin de linea; (3) ningun valor de primer nivel empieza por un
    indicador YAML (comillas, corchete, llave, barra, mayor, ampersand, asterisco, exclamacion, porcentaje, arroba
    o acento grave); ademas model: tiene la forma `model: <valor simple>` y effort: la forma `effort: <letras>`;
    la linea siguiente a model: y a effort: es el cierre o empieza por una letra; y la salida tiene las claves de
    primer nivel de la entrada mas, como mucho, effort, sin repetidas."""
    text = data.replace(b"\r\n", b"\n").decode("iso-8859-1")
    lines = text.split("\n")
    if lines[0] != "---":
        raise ValueError("la primera linea no es ---")
    close = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
    if close is None:
        raise ValueError("frontmatter sin cierre")
    front = lines[1:close]
    if any(ord(c) < 0x20 or ord(c) > 0x7E for l in front for c in l):
        raise ValueError("caracter fuera de ASCII imprimible en el frontmatter")
    if any(not l.startswith(" ") and not re.match(r"[A-Za-z][A-Za-z0-9_-]*:(?: |\Z)", l) for l in front):
        raise ValueError("linea de primer nivel sin la forma clave:")
    if any(re.match(r"[A-Za-z][A-Za-z0-9_-]*: +[\"'\[{|>&*!%@`]", l) for l in front):
        raise ValueError("valor de primer nivel que empieza por un indicador YAML")
    model_idx = [i for i in range(1, close) if lines[i].startswith("model:")]
    effort_idx = [i for i in range(1, close) if lines[i].startswith("effort:")]
    if len(model_idx) != 1:
        raise ValueError("debe haber exactamente una linea model:")
    if len(effort_idx) > 1:
        raise ValueError("hay mas de una linea effort:")
    if not re.fullmatch(r"model: [A-Za-z0-9][A-Za-z0-9._-]*", lines[model_idx[0]]):
        raise ValueError("la linea model: del origen no tiene la forma esperada")
    if effort_idx and not re.fullmatch(r"effort: [a-z]+", lines[effort_idx[0]]):
        raise ValueError("la linea effort: del origen no tiene la forma esperada")
    for i in model_idx + effort_idx:
        if lines[i + 1] != "---" and not re.match(r"[A-Za-z]", lines[i + 1]):
            raise ValueError("continuacion de model: o effort: en la linea siguiente")
    out = list(lines)
    out[model_idx[0]] = "model: " + model
    if effort != NO_EFFORT:
        if effort_idx:
            out[effort_idx[0]] = "effort: " + effort
        else:
            out.insert(model_idx[0] + 1, "effort: " + effort)
    # Autocomprobacion estructural: claves de primer nivel de la salida = las de la entrada (mas effort).
    out_close = out.index("---", 1)
    out_keys = _front_keys(out[1:out_close])
    want = set(_front_keys(lines[1:close])) | ({"effort"} if effort != NO_EFFORT else set())
    if len(out_keys) != len(set(out_keys)) or set(out_keys) != want:
        raise ValueError("autocomprobacion: claves de primer nivel repetidas o distintas")
    return "\n".join(out).encode("iso-8859-1")
