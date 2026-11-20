"""Reporte de uso de subagentes a partir de las transcripciones locales de Claude Code.

Uso (se ejecuta desde el clon; no se instala en ~/.claude):

    python -B tools/usage_report.py inspect [--claude-dir DIR] [--project-dir DIR] [--show-paths]

Por ahora existe el subcomando `inspect`: imprime SOLO estructura (nombres de claves de una
lista cerrada, tipos y conteos agregados) para confirmar el formato de las transcripciones.
Nunca imprime valores de contenido (solo `version` y `model` filtrados salen como texto), prompts, rutas, nombres de carpeta ni identificadores de
sesion, asi que su salida es segura de pegar en una conversacion. Una clave que no esta en
la lista cerrada se cuenta como "(clave desconocida)" sin mostrar su nombre ni su valor.

Codigos de salida: 0 correcto; 1 entorno o datos (falta projects/, sin transcripciones,
error no previsto); 2 uso incorrecto (lo emite argparse); 3 demasiados archivos danados
(la salida de inspect se imprime igual: es la herramienta de diagnostico).

Lectura defensiva: no se siguen enlaces simbolicos ni junctions, las lineas tienen un tope de
tamano (MAX_LINE_BYTES) y se descartan sin cargarlas, y un error no previsto imprime solo el
nombre de la clase de la excepcion (un traceback podria arrastrar contenido). Los mensajes
van en ASCII.

Decision de diseno: `inspect` muestra SOLO nombres de clave de listas cerradas; las claves
desconocidas siguen fundidas en "(clave desconocida)" (no se muestra su nombre aunque ayudaria
a descubrir el formato: un nombre de clave tambien puede ser texto libre). Los histogramas de
`type`, `version` y `model` (unico canal de texto libre) pasan por un filtro propio por campo:
lo que no encaja sale como "(otro type)", "(otra version)" u "(otro modelo)".

Nombres de entrada: solo se abren carpetas y archivos cuyo nombre cumple una lista permitida
(lo que produce derive_folder_name para carpetas, `agent-<id>` para subagentes); el resto se
cuenta como "nombres no validos omitidos". Eso cierra los gemelos de Win32 (`x.` y `x ` se
resuelven como `x`) y los nombres de dispositivo.

Limite aceptado (carrera): entre el lstat de una carpeta y su listado, o entre el listado y la
apertura de un archivo, otro proceso con permiso de escritura en la carpeta de usuario podria
cambiar la entrada, y tambien los componentes intermedios (`subagents/`, `<sesion>/`) que se
cambien por una junction despues del listado. Se repite el lstat de la carpeta despues de listarla y se compara
(ino, dev); para los archivos, _open_regular compara lstat y fstat del descriptor abierto.
La ventana entre os.lstat y os.scandir/os.open no se puede cerrar con la biblioteca estandar
en Windows. Quien puede escribir en ~/.claude ya puede alterar las transcripciones; esta
herramienta solo lee y nunca ejecuta lo que lee.
"""

import argparse
import collections
import datetime
import hashlib
import json
import os
import re
import stat
import sys

EXIT_OK = 0
EXIT_ENV = 1
EXIT_SCHEMA = 3

# Una linea de transcripcion mayor que esto (imagen en base64, salida enorme) se descarta
# leyendola por trozos acotados: la memoria no depende del tamano de la linea.
MAX_LINE_BYTES = 4 * 1024 * 1024
MAX_META_BYTES = 64 * 1024
# Tope de tamano de un archivo JSONL (512 MiB). Se comprueba con fstat().st_size y con los
# bytes realmente leidos (un archivo puede crecer mientras se lee). Pasado el tope el archivo
# se omite y se cuenta en "archivos omitidos por tope de tamano".
MAX_FILE_BYTES = 512 * 1024 * 1024
# Tope de elementos de cada conjunto de ids por archivo (message.id, tool_use, Agent/Task).
# Pasado el tope el archivo se omite igual que arriba: la memoria queda acotada.
MAX_IDS_PER_FILE = 500_000
# Mas de este porcentaje de archivos de subagente danados o ilegibles da exit 3.
MAX_DAMAGED_PERCENT = 5
# Tope de valores distintos por histograma (memoria) y de valores mostrados.
HIST_STORE_LIMIT = 200
HIST_SHOW_LIMIT = 30

# Patron generico de nombres. `inspect` NO lo usa. Es demasiado amplio para una salida: deja
# pasar `user@example.com`, `home/x/secret`, etc. Si T2 reutiliza `safe_name` para mostrar
# algo, debe usar una lista mas estrecha y un identificador de al menos 8 bytes, o ninguno.
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/\-]{0,63}\Z")
SYNTHETIC_MODEL = "<synthetic>"

# Filtros de los histogramas, uno por campo (lista cerrada o patron estrecho).
# Version: x.y.z numerico acotado y sufijo opcional corto (-beta.1, -rc1): letras (hasta 8),
# hasta 3 digitos y hasta dos bloques .n. Un sufijo largo (clave, hash) no pasa.
VERSION_RE = re.compile(
    r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,6}(-[A-Za-z]{1,8}[0-9]{0,3}(\.[0-9]{1,3}){0,2})?\Z")
# Modelo: familia conocida (o version numerica, p. ej. claude-3-5-sonnet-...) y luego tramos
# separados por '-'. Un tramo es: palabra en minuscula de hasta 12 caracteres, numero de 1-2
# digitos (con '.' solo entre numeros cortos, p. ej. 4.5) o fecha de 8 digitos. Un '.' nunca
# une letras (no pasa un host) y no hay tramo alfanumerico largo ni numero de 3-7 o mas de 8
# digitos (no pasa una tarjeta ni un hash). Sin lista cerrada de modelos exactos.
_MODEL_NUM = r"[0-9]{1,2}(?:\.[0-9]{1,2}){0,2}"
MODEL_RE = re.compile(
    r"(?=.{8,64}\Z)claude-(?:opus|sonnet|haiku|fable|instant|" + _MODEL_NUM + r")"
    r"(?:-(?:[a-z][a-z0-9]{0,11}|" + _MODEL_NUM + r"|[0-9]{8})){0,8}(?:@[0-9]{8})?\Z")
KNOWN_TYPES = frozenset((
    "user", "assistant", "system", "summary", "attachment", "progress",
    "file-history-snapshot", "queue-operation", "last-prompt", "permission-mode",
))
OTHER_LABELS = {"type": "(otro type)", "version": "(otra version)", "model": "(otro modelo)"}

# Listas permitidas de nombres de entrada del sistema de archivos.
DIR_NAME_RE = re.compile(r"[A-Za-z0-9-]+\Z")
SESSION_FILE_RE = re.compile(r"[A-Za-z0-9-]+\.jsonl\Z")
AGENT_FILE_RE = re.compile(r"agent-[A-Za-z0-9_-]+\.(jsonl|meta\.json)\Z")
# Nombres de dispositivo de Windows: abrirlos con una ruta normal abre el dispositivo.
RESERVED_STEMS = frozenset(["con", "prn", "aux", "nul"]
                           + ["com%d" % i for i in range(10)] + ["lpt%d" % i for i in range(10)])

UNKNOWN_KEY = "(clave desconocida)"

# Listas cerradas de claves cuyo nombre puede mostrarse. Todo lo demas sale como UNKNOWN_KEY.
LINE_KEYS = frozenset((
    "type", "timestamp", "version", "isSidechain", "message", "uuid", "parentUuid",
    "sessionId", "cwd", "gitBranch", "userType", "entrypoint", "requestId", "agentId",
    "slug", "toolUseResult", "isMeta", "isApiErrorMessage", "isCompactSummary", "summary",
    "leafUuid", "sourceToolAssistantUUID", "toolUseID", "parentToolUseID", "level",
    "subtype", "content", "error", "permissionMode", "promptId", "data", "todos",
))
MESSAGE_KEYS = frozenset((
    "id", "type", "role", "model", "content", "usage", "stop_reason", "stop_sequence",
    "container", "context_management",
))
USAGE_KEYS = frozenset((
    "input_tokens", "output_tokens", "cache_creation_input_tokens",
    "cache_read_input_tokens", "cache_creation", "service_tier", "server_tool_use",
    "inference_geo", "speed", "iterations",
))
META_KEYS = frozenset(("agentType", "toolUseId", "description", "agentId", "prompt", "model"))
INPUT_KEYS = frozenset((
    "subagent_type", "description", "prompt", "run_in_background", "model", "skill",
    "args", "isolation", "resume", "name", "team_name", "mode", "max_turns",
))
RESULT_FIXED_KEYS = ("totalDurationMs", "totalTokens", "totalToolUseCount")
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens")
INPUT_TOOLS = ("Agent", "Task", "Skill")


def _default_claude_dir() -> str:
    """Carpeta de usuario por defecto. Solo se llama si falta --claude-dir."""
    return os.path.join(os.path.expanduser("~"), ".claude")


def derive_folder_name(abs_path: str) -> str:
    """Nombre de carpeta de projects/ para una ruta absoluta: todo lo que no es [A-Za-z0-9] pasa a '-'.

    Se sustituye por unidad UTF-16 (un caracter fuera del BMP da dos guiones), como hace JS con
    su regex sobre cadenas UTF-16. A confirmar en G1 con los nombres de carpeta reales."""
    out = []
    for ch in abs_path:
        if ch.isascii() and ch.isalnum():
            out.append(ch)
        else:
            out.append("-" * (len(ch.encode("utf-16-le", "surrogatepass")) // 2))
    return "".join(out)


def safe_name(value) -> str:
    """Pasa un valor por la lista permitida. Lo que no cumple se sustituye por <no-valido-xxxx>.

    El alias lleva < y >, que NAME_RE no admite: un valor real no puede falsificarlo. Los 4 hex
    son un hash corto (16 bits); `inspect` no usa esta funcion (agrupa todo lo no valido)."""
    if isinstance(value, str):
        if NAME_RE.match(value):
            return value
        digest = hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()
        return "<no-valido-" + digest[:4] + ">"
    return "(no-cadena:" + _type_name(value) + ")"


def hist_label(field: str, value) -> str:
    """Etiqueta mostrable de un valor de histograma (type, version o model), con filtro propio."""
    if isinstance(value, str):
        if field == "type" and value in KNOWN_TYPES:
            return value
        if field == "version" and VERSION_RE.match(value):
            return value
        if field == "model" and (value == SYNTHETIC_MODEL or MODEL_RE.match(value)):
            return value
    return OTHER_LABELS[field]


def _reserved(name: str) -> bool:
    return name.split(".", 1)[0].lower() in RESERVED_STEMS


def valid_dir_name(name: str) -> bool:
    """Carpeta de proyecto o de sesion: [A-Za-z0-9-]+ y no un nombre de dispositivo."""
    return bool(DIR_NAME_RE.match(name)) and not _reserved(name)


def valid_session_file(name: str) -> bool:
    return bool(SESSION_FILE_RE.match(name)) and not _reserved(name)


def valid_agent_file(name: str) -> bool:
    return bool(AGENT_FILE_RE.match(name))


def _type_name(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "otro"


def _is_link_stat(st) -> bool:
    """Enlace simbolico o cualquier punto de reanalisis (junction) de Windows."""
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0) or 0
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _kind(st) -> str:
    if _is_link_stat(st):
        return "link"
    if stat.S_ISDIR(st.st_mode):
        return "dir"
    if stat.S_ISREG(st.st_mode):
        return "file"
    return "other"


def _identity_changed(a, b) -> bool:
    """True si (ino, dev) difiere; solo se compara cuando el sistema los informa (distintos de 0)."""
    if a.st_ino and b.st_ino and (a.st_ino, a.st_dev) != (b.st_ino, b.st_dev):
        return True
    return False


def _list_dir(path: str):
    """(nombre, tipo) de las entradas, ordenadas, sin seguir enlaces. None si no se puede listar.

    Repite el lstat de la carpeta despues de listarla: si dejo de ser una carpeta normal o
    cambio su identidad (ino, dev), se descarta. Ver "Limite aceptado" en el docstring del modulo."""
    try:
        before = os.lstat(path)
        if _kind(before) != "dir":
            return None
        with os.scandir(path) as it:
            raw = list(it)
        after = os.lstat(path)
    except OSError:
        return None
    if _kind(after) != "dir" or _identity_changed(before, after):
        return None
    result = []
    for entry in raw:
        try:
            result.append((entry.name, _kind(entry.stat(follow_symlinks=False))))
        except OSError:
            result.append((entry.name, "other"))
    result.sort()
    return result


class LinkRefused(OSError):
    """Archivo con mas de un enlace duro: podria apuntar fuera de projects/. Se cuenta aparte."""


class _TooBig(Exception):
    """Archivo o conjunto de ids por encima de los topes: se omite el archivo."""


def _open_regular(path: str):
    """Abre en binario un archivo regular sin seguir enlaces. Lanza OSError si no lo es.

    Rechaza enlaces simbolicos, puntos de reanalisis, no regulares y archivos con mas de un
    enlace duro (LinkRefused). O_NONBLOCK (donde existe) evita que un FIFO cambiado en la
    carrera bloquee la apertura."""
    st = os.lstat(path)
    if _kind(st) != "file":
        raise OSError("no es un archivo regular")
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        st2 = os.fstat(fd)
        if not stat.S_ISREG(st2.st_mode):
            raise OSError("cambio de tipo")
        if _identity_changed(st, st2):
            raise OSError("cambio de archivo")
        if st2.st_nlink != 1:
            raise LinkRefused("mas de un enlace duro")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


class _LineInfo:
    """Hallazgos de la lectura de un archivo JSONL (solo contadores)."""

    def __init__(self):
        self.corrupt = 0
        self.truncated_tail = False
        self.oversize = 0
        self.not_object = 0
        self.bytes_read = 0


def _iter_objects(f, info: _LineInfo):
    """Objetos JSON (dict) de un JSONL, una linea a la vez y con tope de tamano por linea."""
    while True:
        line = f.readline(MAX_LINE_BYTES + 1)
        if not line:
            return
        info.bytes_read += len(line)
        if info.bytes_read > MAX_FILE_BYTES:
            raise _TooBig()
        has_newline = line.endswith(b"\n")
        if len(line) > MAX_LINE_BYTES and not has_newline:
            info.oversize += 1
            while True:
                chunk = f.readline(MAX_LINE_BYTES)
                info.bytes_read += len(chunk)
                if info.bytes_read > MAX_FILE_BYTES:
                    raise _TooBig()
                if not chunk or chunk.endswith(b"\n"):
                    break
            continue
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except (ValueError, RecursionError):
            if has_newline:
                info.corrupt += 1
            else:
                info.truncated_tail = True
            continue
        if isinstance(obj, dict):
            yield obj
        else:
            info.not_object += 1


def _digest(value: str) -> bytes:
    return hashlib.blake2b(value.encode("utf-8", "surrogatepass"), digest_size=8).digest()


class _Stats:
    def __init__(self):
        self.c = collections.Counter()
        self.keys = collections.defaultdict(collections.Counter)
        self.hist = collections.defaultdict(collections.Counter)
        self.hist_overflow = collections.Counter()

    def add_hist(self, scope: str, value) -> None:
        name = hist_label(scope.rsplit(".", 1)[1], value)
        counter = self.hist[scope]
        if name in counter or len(counter) < HIST_STORE_LIMIT:
            counter[name] += 1
        else:
            self.hist_overflow[scope] += 1

    def add_keys(self, scope: str, mapping: dict, allowed) -> None:
        counter = self.keys[scope]
        for key, value in mapping.items():
            label = key if (isinstance(key, str) and key in allowed) else UNKNOWN_KEY
            counter[(label, _type_name(value))] += 1


class _FileCtx:
    """Estado por archivo: deduplicacion de ids y, en sesiones principales, ids de Agent/Task."""

    def __init__(self, scope: str):
        self.scope = scope
        self.msg_ids = set()
        self.block_ids = set()
        self.agent_ids = set()
        self.has_usage = False
        self.lines = 0
        self.typed_lines = 0

    @staticmethod
    def remember(bag: set, key) -> None:
        """Agrega a un conjunto de ids con tope: pasado MAX_IDS_PER_FILE se omite el archivo."""
        if key not in bag:
            if len(bag) >= MAX_IDS_PER_FILE:
                raise _TooBig()
            bag.add(key)


def _timestamp_ok(value) -> bool:
    if not isinstance(value, str) or len(value) > 64:
        return False
    try:
        datetime.datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _scan_line(obj: dict, st: _Stats, ctx: _FileCtx) -> None:
    scope = ctx.scope
    ctx.lines += 1
    st.c[scope + " lineas"] += 1
    st.add_keys(scope + ".linea", obj, LINE_KEYS)
    if "type" in obj:
        ctx.typed_lines += 1
        st.add_hist(scope + ".type", obj["type"])
    if "version" in obj:
        st.add_hist(scope + ".version", obj["version"])
    if "timestamp" in obj:
        st.c["timestamp interpretable" if _timestamp_ok(obj["timestamp"]) else "timestamp no interpretable"] += 1
    if "toolUseResult" in obj:
        result = obj["toolUseResult"]
        st.c["toolUseResult " + _type_name(result)] += 1
        if isinstance(result, dict):
            for name in RESULT_FIXED_KEYS:
                if name in result:
                    st.c["toolUseResult." + name + " presente"] += 1
            if any(k not in RESULT_FIXED_KEYS for k in result):
                st.c["toolUseResult con otras claves"] += 1
    message = obj.get("message")
    if not isinstance(message, dict):
        return
    st.add_keys(scope + ".message", message, MESSAGE_KEYS)
    if "model" in message:
        st.add_hist(scope + ".model", message["model"])
    is_assistant = obj.get("type") == "assistant"
    if is_assistant:
        st.c[scope + " lineas assistant"] += 1
    usage = message.get("usage")
    if isinstance(usage, dict):
        st.add_keys(scope + ".usage", usage, USAGE_KEYS)
        if is_assistant:
            ctx.has_usage = True
            st.c[scope + " lineas assistant con usage"] += 1
            msg_id = message.get("id")
            if isinstance(msg_id, str):
                ctx.remember(ctx.msg_ids, _digest(msg_id))
            ok = True
            for field in TOKEN_FIELDS:
                value = usage.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    ok = False
            st.c["usage con los 4 campos enteros no negativos" if ok else "usage sin los 4 campos enteros"] += 1
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                _scan_tool_use(block, st, ctx)


def _scan_tool_use(block: dict, st: _Stats, ctx: _FileCtx) -> None:
    name = block.get("name")
    if not isinstance(name, str) or name not in INPUT_TOOLS:
        return
    block_id = block.get("id")
    if isinstance(block_id, str):
        key = (name, _digest(block_id))
        if key in ctx.block_ids:
            return
        ctx.remember(ctx.block_ids, key)
    if ctx.scope != "sesion":
        return
    st.c["tool_use " + name + " (sesion principal)"] += 1
    tool_input = block.get("input")
    if isinstance(tool_input, dict):
        st.add_keys("input." + name, tool_input, INPUT_KEYS)
    if name in ("Agent", "Task") and isinstance(block_id, str):
        ctx.remember(ctx.agent_ids, _digest(block_id))
    if name == "Agent" and isinstance(tool_input, dict) and tool_input.get("run_in_background") is True:
        st.c["Agent con run_in_background"] += 1


def _finish_file(info: _LineInfo, ctx: _FileCtx, st: _Stats) -> None:
    st.c["lineas oversize descartadas"] += info.oversize
    st.c["lineas corruptas"] += info.corrupt
    st.c["lineas que no son objeto"] += info.not_object
    if info.truncated_tail:
        st.c["archivos con ultima linea truncada"] += 1
    if ctx.lines and not ctx.typed_lines:
        st.c["archivos con lineas y ninguna con type"] += 1
    if ctx.scope == "subagente":
        st.c["message.id distintos con usage (subagentes)"] += len(ctx.msg_ids)


_SKIPPED = object()


def _scan_jsonl(path: str, scope: str, st: _Stats):
    """Lee un JSONL y acumula estructura.

    Devuelve (ctx, info); None si no se pudo leer u omitido por tope de tamano; _SKIPPED si es
    un archivo con varios enlaces duros (ya contado en "enlaces omitidos")."""
    try:
        f = _open_regular(path)
    except LinkRefused:
        st.c["enlaces omitidos"] += 1
        return _SKIPPED
    except OSError:
        return None
    ctx = _FileCtx(scope)
    info = _LineInfo()
    try:
        with f:
            if os.fstat(f.fileno()).st_size > MAX_FILE_BYTES:
                raise _TooBig()
            for obj in _iter_objects(f, info):
                _scan_line(obj, st, ctx)
    except _TooBig:
        st.c["archivos omitidos por tope de tamano"] += 1
        return None
    except OSError:
        return None
    _finish_file(info, ctx, st)
    return ctx, info


def _scan_meta(path: str, st: _Stats, agent_ids, main_present: bool) -> None:
    try:
        f = _open_regular(path)
        with f:
            data = f.read(MAX_META_BYTES + 1)
    except LinkRefused:
        st.c["enlaces omitidos"] += 1
        return
    except OSError:
        st.c["meta ilegible"] += 1
        return
    if len(data) > MAX_META_BYTES:
        st.c["meta sobredimensionado"] += 1
        return
    try:
        meta = json.loads(data)
    except (ValueError, RecursionError):
        st.c["meta corrupto"] += 1
        return
    if not isinstance(meta, dict):
        st.c["meta que no es objeto"] += 1
        return
    st.add_keys("meta", meta, META_KEYS)
    st.c["meta con agentType cadena" if isinstance(meta.get("agentType"), str) else "meta sin agentType cadena"] += 1
    tool_use_id = meta.get("toolUseId")
    if not isinstance(tool_use_id, str):
        st.c["meta sin toolUseId cadena"] += 1
    elif not main_present:
        st.c["meta con toolUseId sin sesion principal"] += 1
    elif _digest(tool_use_id) in agent_ids:
        st.c["meta cuyo toolUseId coincide con un tool_use Agent/Task"] += 1
    else:
        st.c["meta cuyo toolUseId no coincide"] += 1


def _scan_session(folder: str, sid: str, has_main: bool, has_dir: bool, st: _Stats) -> None:
    st.c["sesiones"] += 1
    agent_ids = set()
    if has_main:
        done = _scan_jsonl(os.path.join(folder, sid + ".jsonl"), "sesion", st)
        if done is not _SKIPPED:
            st.c["archivos de sesion principal"] += 1
            if done is None:
                st.c["archivos ilegibles"] += 1
            else:
                agent_ids = done[0].agent_ids
    if not has_dir:
        return
    sub_dir = os.path.join(folder, sid, "subagents")
    listing = _list_dir(sub_dir)
    if listing is None:
        st.c["carpetas ilegibles"] += 1
        return
    kinds = dict(listing)
    for name, kind in listing:
        if kind == "link":
            st.c["enlaces omitidos"] += 1
            continue
        if kind != "file" or not name.startswith("agent-"):
            continue
        if not name.endswith((".jsonl", ".meta.json")):
            continue
        if not valid_agent_file(name):
            st.c["nombres no validos omitidos"] += 1
            continue
        if name.endswith(".jsonl"):
            stem = name[:-len(".jsonl")]
            _scan_subagent(sub_dir, name, stem + ".meta.json", kinds, agent_ids, has_main, st)
        else:
            if kinds.get(name[:-len(".meta.json")] + ".jsonl") != "file":
                st.c["metas sin transcripcion"] += 1


def _scan_subagent(sub_dir, name, meta_name, kinds, agent_ids, main_present, st: _Stats) -> None:
    done = _scan_jsonl(os.path.join(sub_dir, name), "subagente", st)
    if done is _SKIPPED:
        return
    st.c["archivos de subagente"] += 1
    if done is None:
        st.c["archivos ilegibles"] += 1
        st.c["archivos de subagente danados o ilegibles"] += 1
    else:
        ctx, info = done
        if info.corrupt:
            st.c["archivos de subagente danados o ilegibles"] += 1
            st.c["archivos de subagente con linea intermedia corrupta"] += 1
        if not ctx.has_usage:
            st.c["subagentes sin ninguna linea assistant con usage"] += 1
    if kinds.get(meta_name) == "file":
        _scan_meta(os.path.join(sub_dir, meta_name), st, agent_ids, main_present)
    else:
        st.c["subagentes sin meta"] += 1


def _scan_project_folder(folder: str, st: _Stats) -> None:
    listing = _list_dir(folder)
    if listing is None:
        st.c["carpetas ilegibles"] += 1
        return
    st.c["carpetas de proyecto leidas"] += 1
    sessions = {}
    for name, kind in listing:
        if kind == "link":
            st.c["enlaces omitidos"] += 1
        elif kind == "file" and name.endswith(".jsonl"):
            if valid_session_file(name):
                sessions.setdefault(name[:-len(".jsonl")], [False, False])[0] = True
            else:
                st.c["nombres no validos omitidos"] += 1
        elif kind == "dir":
            if not valid_dir_name(name):
                st.c["nombres no validos omitidos"] += 1
                continue
            sub = _list_dir(os.path.join(folder, name))
            if sub is None:
                continue
            if ("subagents", "dir") in sub:
                sessions.setdefault(name, [False, False])[1] = True
            elif ("subagents", "link") in sub:
                st.c["enlaces omitidos"] += 1
    for sid in sorted(sessions):
        has_main, has_dir = sessions[sid]
        _scan_session(folder, sid, has_main, has_dir, st)


# Orden fijo de las lineas del resumen: la salida siempre lleva todas, con ceros.
SUMMARY_LABELS = (
    "carpetas de proyecto leidas",
    "sesiones",
    "archivos de sesion principal",
    "archivos de subagente",
    "subagentes sin meta",
    "metas sin transcripcion",
    "subagentes sin ninguna linea assistant con usage",
    "enlaces omitidos",
    "nombres no validos omitidos",
    "archivos omitidos por tope de tamano",
    "archivos ilegibles",
    "carpetas ilegibles",
    "meta ilegible",
    "meta corrupto",
    "meta sobredimensionado",
    "meta que no es objeto",
    "meta con agentType cadena",
    "meta sin agentType cadena",
    "meta sin toolUseId cadena",
    "meta con toolUseId sin sesion principal",
    "meta cuyo toolUseId coincide con un tool_use Agent/Task",
    "meta cuyo toolUseId no coincide",
    "subagente lineas",
    "sesion lineas",
    "subagente lineas assistant",
    "subagente lineas assistant con usage",
    "message.id distintos con usage (subagentes)",
    "sesion lineas assistant con usage",
    "usage con los 4 campos enteros no negativos",
    "usage sin los 4 campos enteros",
    "timestamp interpretable",
    "timestamp no interpretable",
    "archivos con ultima linea truncada",
    "archivos de subagente con linea intermedia corrupta",
    "archivos de subagente danados o ilegibles",
    "lineas corruptas",
    "lineas oversize descartadas",
    "lineas que no son objeto",
    "archivos con lineas y ninguna con type",
    "tool_use Agent (sesion principal)",
    "tool_use Task (sesion principal)",
    "tool_use Skill (sesion principal)",
    "Agent con run_in_background",
    "toolUseResult dict",
    "toolUseResult str",
    "toolUseResult list",
    "toolUseResult otro",
    "toolUseResult null",
    "toolUseResult int",
    "toolUseResult float",
    "toolUseResult bool",
    "toolUseResult.totalDurationMs presente",
    "toolUseResult.totalTokens presente",
    "toolUseResult.totalToolUseCount presente",
    "toolUseResult con otras claves",
)
KEY_SCOPES = (
    "subagente.linea", "subagente.message", "subagente.usage", "meta",
    "sesion.linea", "sesion.message", "sesion.usage",
    "input.Agent", "input.Task", "input.Skill",
)
HIST_SCOPES = (
    "subagente.type", "subagente.version", "subagente.model",
    "sesion.type", "sesion.version", "sesion.model",
)


def render_inspect(st: _Stats) -> str:
    out = [
        "synclayer-usage-inspect v1",
        "Solo estructura: nombres de claves de una lista cerrada, tipos y conteos. "
        "Nunca valores de contenido; solo `version` y `model` filtrados salen como texto.",
        "",
        "== Resumen ==",
    ]
    for label in SUMMARY_LABELS:
        out.append(label + ": " + str(st.c.get(label, 0)))
    for scope in KEY_SCOPES:
        out.append("")
        out.append("== Claves " + scope + " (clave, tipo: lineas) ==")
        counter = st.keys.get(scope)
        if not counter:
            out.append("(sin datos)")
            continue
        for (label, tname), count in sorted(counter.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            out.append(label + " " + tname + ": " + str(count))
    for scope in HIST_SCOPES:
        out.append("")
        out.append("== Histograma " + scope + " ==")
        counter = st.hist.get(scope)
        if not counter:
            out.append("(sin datos)")
            continue
        ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        for name, count in ordered[:HIST_SHOW_LIMIT]:
            out.append(name + ": " + str(count))
        rest = sum(count for _, count in ordered[HIST_SHOW_LIMIT:]) + st.hist_overflow.get(scope, 0)
        if rest:
            out.append("(otros valores): " + str(rest))
    return "\n".join(out) + "\n"


def _fail(message: str, code: int, path=None, show_paths=False) -> int:
    if show_paths and path is not None:
        message = message + ": " + path
    print("error: " + message, file=sys.stderr)
    return code


def _projects_dir_state(projects: str):
    """None si es un directorio normal; si no, el motivo."""
    try:
        st = os.lstat(projects)
    except OSError:
        return "falta la carpeta projects/ dentro de la carpeta de usuario"
    kind = _kind(st)
    if kind == "link":
        return "projects/ es un enlace simbolico o junction: no se sigue"
    if kind != "dir":
        return "projects/ no es una carpeta"
    return None


def _cmd_inspect(args) -> int:
    claude_dir = args.claude_dir if args.claude_dir is not None else _default_claude_dir()
    projects = os.path.join(claude_dir, "projects")
    reason = _projects_dir_state(projects)
    if reason is not None:
        return _fail(reason, EXIT_ENV, projects, args.show_paths)
    listing = _list_dir(projects)
    if listing is None:
        return _fail("no se puede leer projects/", EXIT_ENV, projects, args.show_paths)
    st = _Stats()
    wanted = None
    if args.project_dir is not None:
        wanted = derive_folder_name(os.path.abspath(args.project_dir)).lower()
    for name, kind in listing:
        if kind == "link":
            st.c["enlaces omitidos"] += 1
        elif kind == "dir":
            if not valid_dir_name(name):
                st.c["nombres no validos omitidos"] += 1
            elif wanted is None or name.lower() == wanted:
                _scan_project_folder(os.path.join(projects, name), st)
    if not st.c["sesiones"]:
        what = "el proyecto no tiene transcripciones" if wanted is not None else "no hay transcripciones"
        return _fail(what, EXIT_ENV)
    sys.stdout.write(render_inspect(st))
    sys.stdout.flush()
    total = st.c["archivos de subagente"]
    damaged = st.c["archivos de subagente danados o ilegibles"]
    if total and damaged * 100 > total * MAX_DAMAGED_PERCENT:
        return _fail(
            "demasiados archivos de subagente danados o ilegibles: %d de %d (limite %d %%)"
            % (damaged, total, MAX_DAMAGED_PERCENT),
            EXIT_SCHEMA,
        )
    return EXIT_OK


def _non_empty(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("no puede estar vacio")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="usage_report.py",
        description="Reporte de uso de subagentes de Claude Code (solo lectura de estructura por ahora).",
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    insp = sub.add_parser("inspect", help="imprime solo la estructura de las transcripciones",
                           allow_abbrev=False)
    insp.add_argument("--claude-dir", default=None, type=_non_empty, help="carpeta de usuario (por defecto ~/.claude)")
    insp.add_argument("--project-dir", default=None, type=_non_empty,
                      help="limita la lectura a las transcripciones de este proyecto")
    insp.add_argument("--show-paths", action="store_true",
                      help="permite rutas en los mensajes de error de stderr")
    insp.set_defaults(func=_cmd_inspect)
    return parser


def main(argv=None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        return args.func(args)
    except KeyboardInterrupt:
        print("interrumpido", file=sys.stderr)
        return 130
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 2
    except Exception as exc:  # noqa: BLE001 - nunca un traceback: podria arrastrar contenido
        print("error: error no previsto (" + type(exc).__name__ + ")", file=sys.stderr)
        return EXIT_ENV


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
