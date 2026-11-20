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
import dataclasses
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
# Tope del conjunto GLOBAL de message.id (digests de 8 bytes) del lector de subagentes, para
# detectar un mismo id en dos archivos. Pasado el tope se deja de recordar ids nuevos (no se
# omite nada): lo que ya no se puede comparar se cuenta aparte y avisa. ~2 M ids son ~150 MB.
MAX_IDS_GLOBAL = 2_000_000
# Versiones de Claude Code que el mensaje de exit 3 enumera por lista (las mas recientes).
MAX_SHOWN_VERSIONS = 8
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
# Version: x.y.z numerico acotado y sufijo opcional de lista cerrada (-alpha, -beta, -rc), hasta
# 3 digitos y hasta dos bloques .n (-beta.1, -rc1). Las versiones reales vistas no llevan sufijo:
# cualquier otra palabra (clave, hash, texto) no pasa.
VERSION_RE = re.compile(
    r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,6}(-(alpha|beta|rc)[0-9]{0,3}(\.[0-9]{1,3}){0,2})?\Z")
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
    """Archivo con mas de un enlace duro: podria apuntar fuera de projects/. Se cuenta aparte
    ("hardlinks (nlink > 1)" en inspect)."""


class _TooBig(Exception):
    """Archivo o conjunto de ids por encima de los topes: se omite el archivo."""


def _open_regular(path: str, allow_hardlink: bool = False):
    """Abre en binario un archivo regular sin seguir enlaces. Lanza OSError si no lo es.

    Rechaza enlaces simbolicos, puntos de reanalisis, no regulares y, salvo allow_hardlink,
    archivos con mas de un enlace duro (LinkRefused). Solo el lector de transcripciones de
    subagentes acepta enlaces duros (decision G1: Claude Code los crea). O_NONBLOCK (donde
    existe) evita que un FIFO cambiado en la carrera bloquee la apertura."""
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
        if st2.st_nlink != 1 and not allow_hardlink:
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

    def merge(self, other: "_Stats") -> None:
        """Suma los conteos de otro _Stats. Se usa para fusionar un archivo SOLO si termino bien."""
        self.c.update(other.c)
        for scope, counter in other.keys.items():
            self.keys[scope].update(counter)
        for scope, counter in other.hist.items():
            mine = self.hist[scope]
            for name, count in counter.items():
                if name in mine or len(mine) < HIST_STORE_LIMIT:
                    mine[name] += count
                else:
                    self.hist_overflow[scope] += count
        self.hist_overflow.update(other.hist_overflow)

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
    un archivo con varios enlaces duros (ya contado en "hardlinks (nlink > 1)").

    Se acumula en un _Stats propio del archivo y se fusiona en `st` solo si la lectura termina
    bien: un archivo omitido a mitad (tope, error de E/S) no deja lineas contadas."""
    try:
        f = _open_regular(path)
    except LinkRefused:
        st.c["hardlinks (nlink > 1)"] += 1
        return _SKIPPED
    except OSError:
        return None
    ctx = _FileCtx(scope)
    info = _LineInfo()
    local = _Stats()
    try:
        with f:
            if os.fstat(f.fileno()).st_size > MAX_FILE_BYTES:
                raise _TooBig()
            for obj in _iter_objects(f, info):
                _scan_line(obj, local, ctx)
    except _TooBig:
        st.c["archivos omitidos por tope de tamano"] += 1
        return None
    except OSError:
        return None
    _finish_file(info, ctx, local)
    st.merge(local)
    return ctx, info


def _scan_meta(path: str, st: _Stats, agent_ids, main_present: bool) -> None:
    try:
        f = _open_regular(path)
        with f:
            data = f.read(MAX_META_BYTES + 1)
    except LinkRefused:
        st.c["hardlinks (nlink > 1)"] += 1
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
    # Una sesion cuenta como leida solo si se leyo algun archivo suyo: una sesion cuyo unico
    # archivo es un hardlink (no se lee) o es ilegible no cuenta.
    if _scan_session_files(folder, sid, has_main, has_dir, st):
        st.c["sesiones"] += 1


def _scan_session_files(folder: str, sid: str, has_main: bool, has_dir: bool, st: _Stats) -> bool:
    """Lee los archivos de una sesion. Devuelve True si leyo al menos uno."""
    read_any = False
    agent_ids = set()
    if has_main:
        done = _scan_jsonl(os.path.join(folder, sid + ".jsonl"), "sesion", st)
        if done is not _SKIPPED:
            st.c["archivos de sesion principal"] += 1
            if done is None:
                st.c["archivos ilegibles"] += 1
            else:
                read_any = True
                agent_ids = done[0].agent_ids
    if not has_dir:
        return read_any
    sub_dir = os.path.join(folder, sid, "subagents")
    listing = _list_dir(sub_dir)
    if listing is None:
        st.c["carpetas ilegibles"] += 1
        return read_any
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
            if _scan_subagent(sub_dir, name, stem + ".meta.json", kinds, agent_ids, has_main, st):
                read_any = True
        else:
            if kinds.get(name[:-len(".meta.json")] + ".jsonl") != "file":
                st.c["metas sin transcripcion"] += 1
    return read_any


def _scan_subagent(sub_dir, name, meta_name, kinds, agent_ids, main_present, st: _Stats) -> bool:
    """True si la transcripcion se leyo."""
    done = _scan_jsonl(os.path.join(sub_dir, name), "subagente", st)
    if done is _SKIPPED:
        return False
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
    return done is not None


def _enum_sessions(folder: str, counts):
    """Sesiones de una carpeta de proyecto: lista ordenada de (sid, tiene .jsonl, tiene
    subagents/), o None si la carpeta no se puede listar. UNICO enumerador: lo usan `inspect` y el
    lector de subagentes, asi cuentan igual las carpetas, los enlaces y los nombres no validos
    (`counts` es el Counter donde se anotan)."""
    listing = _list_dir(folder)
    if listing is None:
        counts["carpetas ilegibles"] += 1
        return None
    counts["carpetas de proyecto leidas"] += 1
    sessions = {}
    for name, kind in listing:
        if kind == "link":
            counts["enlaces omitidos"] += 1
        elif kind == "file" and name.endswith(".jsonl"):
            if valid_session_file(name):
                sessions.setdefault(name[:-len(".jsonl")], [False, False])[0] = True
            else:
                counts["nombres no validos omitidos"] += 1
        elif kind == "dir":
            if not valid_dir_name(name):
                counts["nombres no validos omitidos"] += 1
                continue
            sub = _list_dir(os.path.join(folder, name))
            if sub is None:
                continue
            if ("subagents", "dir") in sub:
                sessions.setdefault(name, [False, False])[1] = True
            elif ("subagents", "link") in sub:
                counts["enlaces omitidos"] += 1
    return [(sid, flags[0], flags[1]) for sid, flags in sorted(sessions.items())]


def _scan_project_folder(folder: str, st: _Stats) -> None:
    for sid, has_main, has_dir in _enum_sessions(folder, st.c) or ():
        _scan_session(folder, sid, has_main, has_dir, st)


# --- Lector de subagentes (T2) ---
#
# Convierte cada `agent-<id>.jsonl` en un CallRecord (una llamada). Solo lee las claves de la
# tabla 3.3 del plan: en las lineas `type`, `timestamp`, `version`, `message`; en `message`
# `id`, `model`, `usage` (cuatro campos numericos) y `content`; en cada bloque `type` e `id`;
# en el meta `agentType` y `model`. Nada mas.

# Ultima version de Claude Code contra la que se verifico el formato (G1: 2.1.287 a 2.1.326).
VERIFIED_MAX = "2.1.326"

# Los nueve agentes de SyncLayer (los comprueba una prueba contra agents/*.md) y los
# integrados mas comunes. El tipo de agente visible sale SOLO de estas listas cerradas:
# cualquier otro nombre (usuario, plugin) se muestra como "(otro agente)". No se muestra
# ningun texto libre del meta.
SYNCLAYER_AGENTS = frozenset((
    "oracle", "scout", "atlas", "forge", "sentinel", "auditor", "shield", "debugger", "scribe",
))
BUILTIN_AGENTS = frozenset((
    "general-purpose", "Explore", "Plan", "statusline-setup", "output-style-setup",
    "claude-code-guide",
))
DEFAULT_AGENT = "general-purpose"
OTHER_AGENT = "(otro agente)"
NO_META_AGENT = "(sin-meta)"
# Alias de modelo que el meta puede traer en lugar de un id completo (lista cerrada).
# "inherit" NO esta: no es un modelo (el subagente hereda el del padre), se trata como ausente.
MODEL_ALIASES = frozenset(("opus", "sonnet", "haiku", "fable"))
NOT_A_MODEL = frozenset(("inherit",))
_DATE_SUFFIX_RE = re.compile(r"[-@][0-9]{8}\Z")

# Avisos de texto fijo para el reporte (T5): salen de ReadResult.warnings. ASCII, sin datos.
WARN_NO_MESSAGE_ID = ("hay lineas con usage sin message.id: cada linea se cuenta como una peticion "
                      "y no se puede deduplicar")
WARN_ID_REPEATED = ("hay message.id repetidos entre archivos (p. ej. agentes reanudados): el "
                    "segundo archivo no suma esas peticiones")
WARN_ID_CAP = ("se alcanzo el tope de ids para deduplicar entre archivos: puede haber peticiones "
               "repetidas sin detectar")

# Comprobaciones de esquema (exit 3). Los nombres salen en el mensaje: texto fijo.
CHK_USAGE_OBJ = "usage presente y no es objeto"
CHK_TOKENS = "campo de tokens que no es entero no negativo"
CHK_TS = "timestamp ausente o no interpretable"
CHK_META = "meta que no es objeto JSON o sin agentType cadena"
CHK_NO_TYPE = "archivo con lineas validas y ninguna con type"

_VERSION_PARTS_RE = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")
# Prefijo de un agente de plugin (lo que va antes del primer ":"): minusculas, digitos y '-'.
PLUGIN_PREFIX_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}\Z")


class SchemaError(Exception):
    """Esquema desconocido o demasiados archivos danados (exit 3). El mensaje es texto fijo,
    numeros y versiones filtradas: nunca contenido ni rutas."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class EnvError(Exception):
    """Entorno o datos (exit 1). Mensaje de texto fijo, sin rutas."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def version_key(label: str):
    """(x, y, z) de una version ya filtrada; (0, 0, 0) si no es numerica."""
    m = _VERSION_PARTS_RE.match(label)
    return tuple(int(g) for g in m.groups()) if m else (0, 0, 0)


def is_unverified(label: str) -> bool:
    """True si la version es mayor que VERIFIED_MAX (una etiqueta no valida no cuenta)."""
    return version_key(label) > version_key(VERIFIED_MAX)


def classify_agent(raw):
    """(nombre visible, conjunto) de un agentType.

    SyncLayer, integrado y otros salen de listas cerradas. Un nombre con ":" es de un plugin: el
    unico texto libre que se muestra es el PREFIJO, validado con PLUGIN_PREFIX_RE, como
    `plugin:<prefijo>` (nombre visible y conjunto, para comparar plugins entre si, 3.5). Lo que hay
    tras el primer ":" nunca se muestra. Un prefijo no valido da ("(otro agente)",
    "plugin:(no-valido)")."""
    if isinstance(raw, str):
        if raw == "":
            return DEFAULT_AGENT, "integrado"
        if raw in SYNCLAYER_AGENTS:
            return raw, "SyncLayer"
        if raw in BUILTIN_AGENTS:
            return raw, "integrado"
        if ":" in raw:
            prefix = raw.split(":", 1)[0]
            if PLUGIN_PREFIX_RE.match(prefix):
                label = "plugin:" + prefix
                return label, label
            return OTHER_AGENT, "plugin:(no-valido)"
    return OTHER_AGENT, "otros"


@dataclasses.dataclass(frozen=True)
class CallRecord:
    """Una llamada a un subagente (un agent-<id>.jsonl). Sin contenido: solo numeros y
    etiquetas de listas cerradas. Los identificadores son resumenes (blake2b de 64 bits) para
    agrupar en memoria; no se escriben en ningun reporte.

    `damage` (None | "linea intermedia corrupta" | "ilegible" | "tope") marca una llamada EXCLUIDA
    de las estadisticas de tokens (propiedad `excluded`). Con "linea intermedia corrupta" la
    llamada conserva `tools`, `start`, `end`, `models`, `versions` y `has_usage`: solo se vacian
    los tokens y `requests`. Con "ilegible" o "tope" el archivo se descarta entero y no queda nada
    (tampoco start/end/versions): para ubicarla en una ventana esta `fallback_time`.

    `excluded` y `usable` no son opuestos: una llamada `sin_usage` no esta excluida (cuenta para
    duracion y herramientas) pero tampoco es `usable` (no tiene tokens que sumar).

    `fallback_time`: mtime del archivo (del fstat del descriptor ya abierto), en UTC. Es una
    hora APROXIMADA (la ultima escritura, no el inicio de la llamada) y solo sirve para ubicar en
    una ventana las llamadas con `start=None`. None si no se pudo abrir el archivo."""
    call_id: str
    project: str            # alias p-<8 hex> (3.7)
    session: str            # resumen de la sesion, solo para agrupar
    agent: str              # nombre visible (lista cerrada) o "(otro agente)" / "(sin-meta)"
    agent_group: str        # SyncLayer | integrado | plugin:<prefijo> | plugin:(no-valido) | otros | sin-meta
    status: str             # correcta | sin_usage | sin_meta | danada
    damage: object          # None | "linea intermedia corrupta" | "ilegible" | "tope"
    has_meta: bool
    has_usage: bool
    models: tuple
    model: str              # el modelo, "mixto" o "(desconocido)"
    model_source: object    # "lineas" | "meta" | None
    model_mismatch: bool    # el meta trae un id completo distinto de los de las lineas
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    requests: int           # message.id distintos con usage
    tools: int              # bloques tool_use con id distinto
    start: object           # datetime UTC o None
    end: object
    fallback_time: object   # datetime UTC (mtime del archivo, aproximado) o None
    versions: tuple         # versiones de Claude Code de sus lineas (ya filtradas)
    hardlink: bool
    oversize_lines: int
    background: object      # None: el dato vive en la sesion principal (T4), no aqui

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens + self.output_tokens + self.cache_creation_tokens
                + self.cache_read_tokens)

    @property
    def usable(self) -> bool:
        """Entra en las estadisticas de tokens: tiene usage y el archivo no esta danado."""
        return self.has_usage and self.damage is None

    @property
    def excluded(self) -> bool:
        """Llamada danada (damage no es None): fuera de las estadisticas de tokens. Distinto de
        `usable`: una llamada `sin_usage` no esta excluida."""
        return self.damage is not None

    @property
    def unverified(self) -> bool:
        return any(is_unverified(v) for v in self.versions)


class ReadResult:
    def __init__(self):
        self.calls = []
        self.quality = collections.Counter()
        self.schema = collections.Counter()    # comprobacion -> archivos
        self.versions = collections.Counter()  # version filtrada -> archivos
        self.schema_versions = collections.Counter()  # version -> archivos que fallan una comprobacion
        self._seen_ids = set()                 # digests de message.id ya sumados (entre archivos)

    @property
    def usage_without_message_id(self) -> bool:
        """True si alguna linea con usage no traia message.id (cada una cuenta como peticion)."""
        return self.quality["usage sin message.id"] > 0

    @property
    def warnings(self) -> list:
        """Avisos de texto fijo para el reporte (sin datos leidos)."""
        out = []
        if self.usage_without_message_id:
            out.append(WARN_NO_MESSAGE_ID)
        if self.quality["message.id repetido entre archivos"] > 0:
            out.append(WARN_ID_REPEATED)
        if self.quality["message.id sin deduplicar entre archivos (tope)"] > 0:
            out.append(WARN_ID_CAP)
        return out


class _CallAcc:
    """Acumulador de UN archivo: solo se fusiona en el resultado si termina bien."""

    def __init__(self):
        self.lines = 0
        self.typed = 0
        self.schema = set()
        self.versions = set()
        self.first = None
        self.last = None
        self.models = set()
        self.usage_by_id = {}
        self.usage_no_id = []
        self.tools = set()
        self.synthetic = 0


def _parse_ts(value):
    """datetime UTC de un ISO 8601 (sin zona se toma como UTC); None si no se interpreta."""
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except (ValueError, OverflowError):
        return None


def _token_tuple(usage: dict):
    """Los cuatro campos en orden, o None si alguno no es entero no negativo (bool no vale)."""
    out = []
    for name in TOKEN_FIELDS:
        value = usage.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        out.append(value)
    return tuple(out)


def _acc_line(obj: dict, acc: _CallAcc) -> None:
    acc.lines += 1
    kind = obj.get("type")
    if isinstance(kind, str):
        acc.typed += 1
    version = obj.get("version")
    if isinstance(version, str):
        acc.versions.add(hist_label("version", version))
    ts = _parse_ts(obj.get("timestamp"))
    if ts is None:
        if kind in ("user", "assistant"):
            acc.schema.add(CHK_TS)
    else:
        if acc.first is None or ts < acc.first:
            acc.first = ts
        if acc.last is None or ts > acc.last:
            acc.last = ts
    if kind != "assistant":
        return
    message = obj.get("message")
    if not isinstance(message, dict):
        return
    model = message.get("model")
    if model == SYNTHETIC_MODEL:
        acc.synthetic += 1   # sin peticion real: fuera de modelos, tokens y herramientas
        return
    if isinstance(model, str):
        acc.models.add(hist_label("model", model))
    if "usage" in message:
        usage = message.get("usage")
        if not isinstance(usage, dict):
            acc.schema.add(CHK_USAGE_OBJ)
        else:
            tokens = _token_tuple(usage)
            if tokens is None:
                acc.schema.add(CHK_TOKENS)
            else:
                msg_id = message.get("id")
                if isinstance(msg_id, str):
                    key = _digest(msg_id)
                    if key not in acc.usage_by_id and len(acc.usage_by_id) >= MAX_IDS_PER_FILE:
                        raise _TooBig()
                    acc.usage_by_id[key] = tokens   # la ultima linea de cada id manda
                else:
                    if len(acc.usage_no_id) >= MAX_IDS_PER_FILE:
                        raise _TooBig()
                    acc.usage_no_id.append(tokens)  # sin id no se puede deduplicar
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                block_id = block.get("id")
                if isinstance(block_id, str):
                    key = _digest(block_id)
                    if key not in acc.tools and len(acc.tools) >= MAX_IDS_PER_FILE:
                        raise _TooBig()
                    acc.tools.add(key)


def _model_label(raw, allow_alias: bool):
    if allow_alias and isinstance(raw, str) and raw in MODEL_ALIASES:
        return raw
    return hist_label("model", raw)


def _model_base(label: str) -> str:
    """Familia y version sin el sufijo de fecha (-YYYYMMDD o @YYYYMMDD)."""
    return _DATE_SUFFIX_RE.sub("", label)


def _read_meta(sub_dir: str, meta_name: str, kinds: dict, quality):
    """(presente, agentType, model, malo). `presente` False: se trata como llamada sin meta."""
    if kinds.get(meta_name) != "file":
        return False, None, None, False
    try:
        with _open_regular(os.path.join(sub_dir, meta_name)) as f:
            data = f.read(MAX_META_BYTES + 1)
    except LinkRefused:
        quality["metas rechazadas por enlace duro"] += 1   # decision G1: el meta sigue rechazado
        return False, None, None, False
    except OSError:
        quality["meta ilegible"] += 1
        return False, None, None, False
    if len(data) > MAX_META_BYTES:
        quality["meta sobredimensionado"] += 1
        return False, None, None, False
    try:
        meta = json.loads(data)
    except (ValueError, RecursionError):
        return True, None, None, True
    if not isinstance(meta, dict) or not isinstance(meta.get("agentType"), str):
        return True, None, None, True
    model = meta.get("model")
    return True, meta["agentType"], (model if isinstance(model, str) else None), False


def _drop_repeated_ids(acc: _CallAcc, res: ReadResult) -> list:
    """Entradas de tokens de un archivo NO danado, sin los message.id que otro archivo ya sumo.

    Decision: el segundo archivo (orden del recorrido) NO suma una peticion cuyo message.id ya
    conto otro archivo (agentes reanudados repiten el historial), pero se cuenta en
    "message.id repetido entre archivos" y avisa. Un archivo danado no registra sus ids (sus
    tokens no cuentan). Pasado MAX_IDS_GLOBAL no se recuerdan ids nuevos."""
    entries = list(acc.usage_no_id)
    seen = res._seen_ids
    for key, tokens in acc.usage_by_id.items():
        if key in seen:
            res.quality["message.id repetido entre archivos"] += 1
            continue
        if len(seen) < MAX_IDS_GLOBAL:
            seen.add(key)
        else:
            res.quality["message.id sin deduplicar entre archivos (tope)"] += 1
        entries.append(tokens)
    return entries


def _read_call(sub_dir, name, kinds, folder_name, sid, res: ReadResult) -> None:
    stem = name[:-len(".jsonl")]
    meta_name = stem + ".meta.json"
    acc = _CallAcc()
    info = _LineInfo()
    hardlink = False
    fallback_time = None
    failure = None
    try:
        with _open_regular(os.path.join(sub_dir, name), allow_hardlink=True) as f:
            st = os.fstat(f.fileno())
            # se anotan antes de leer: valen aunque la lectura falle despues
            hardlink = st.st_nlink > 1
            try:
                fallback_time = datetime.datetime.fromtimestamp(st.st_mtime, tz=datetime.timezone.utc)
            except (OSError, OverflowError, ValueError):
                fallback_time = None
            if st.st_size > MAX_FILE_BYTES:
                raise _TooBig()
            for obj in _iter_objects(f, info):
                _acc_line(obj, acc)
    except _TooBig:
        failure = "tope"
    except OSError:
        failure = "ilegible"
    q = res.quality
    present, agent_raw, meta_model, meta_bad = _read_meta(sub_dir, meta_name, kinds, q)
    if meta_bad:
        res.schema[CHK_META] += 1
    q["llamadas leidas"] += 1
    if hardlink:
        q["hardlinks aceptados"] += 1   # tambien si la lectura falla
    if meta_model in NOT_A_MODEL:
        meta_model = None   # "inherit" no es un modelo
    if failure is not None:
        # archivo omitido a mitad de lectura: no deja ninguna linea contada
        q["archivos omitidos por tope de tamano" if failure == "tope" else "archivos ilegibles"] += 1
        acc = _CallAcc()
        info = _LineInfo()
        damage = failure
    else:
        if acc.lines and not acc.typed:
            acc.schema.add(CHK_NO_TYPE)
        for check in acc.schema:
            res.schema[check] += 1
        for label in acc.versions:
            res.versions[label] += 1
            if acc.schema or meta_bad:
                res.schema_versions[label] += 1   # versiones de los archivos que fallan
        q["lineas corruptas"] += info.corrupt
        q["lineas oversize descartadas"] += info.oversize
        q["lineas que no son objeto"] += info.not_object
        q["lineas synthetic excluidas"] += acc.synthetic
        if info.truncated_tail:
            q["archivos con ultima linea truncada"] += 1
        damage = "linea intermedia corrupta" if info.corrupt else None
    entries = list(acc.usage_by_id.values()) + acc.usage_no_id
    has_usage = bool(entries)
    if damage is not None:
        entries = []   # un archivo danado queda fuera de las estadisticas de tokens
        q["llamadas danadas"] += 1
    else:
        q["usage sin message.id"] += len(acc.usage_no_id)
        entries = _drop_repeated_ids(acc, res)
    sums = [sum(e[i] for e in entries) for i in range(4)]
    line_models = acc.models
    meta_label = _model_label(meta_model, True) if meta_model is not None else None
    if line_models:
        models, source = tuple(sorted(line_models)), "lineas"
    elif meta_label is not None:
        models, source = (meta_label,), "meta"
    else:
        models, source = (), None
    # el sufijo de fecha no cuenta: el meta suele traer el id sin fecha y las lineas con fecha
    mismatch = bool(meta_label is not None and MODEL_RE.match(meta_model) and line_models
                    and "(otro modelo)" not in line_models
                    and _model_base(meta_label) not in {_model_base(m) for m in line_models})
    if mismatch:
        q["llamadas con modelo distinto del meta"] += 1
    if present and not meta_bad:
        agent, group = classify_agent(agent_raw)
    else:
        agent, group = NO_META_AGENT, "sin-meta"
    if damage is not None:
        status = "danada"
    elif not has_usage:
        status = "sin_usage"
    elif not present or meta_bad:
        status = "sin_meta"
    else:
        status = "correcta"
    if not has_usage and damage is None:
        q["llamadas sin usage"] += 1
    if group == "sin-meta":
        q["llamadas sin meta"] += 1
    res.calls.append(CallRecord(
        call_id=_digest(folder_name + "\0" + sid + "\0" + stem).hex(),
        project="p-" + hashlib.sha256(folder_name.lower().encode("utf-8", "surrogatepass")).hexdigest()[:8],
        session=_digest(folder_name + "\0" + sid).hex(),
        agent=agent, agent_group=group, status=status, damage=damage,
        has_meta=present and not meta_bad, has_usage=has_usage,
        models=models,
        model=("mixto" if len(models) > 1 else models[0]) if models else "(desconocido)",
        model_source=source, model_mismatch=mismatch,
        input_tokens=sums[0], output_tokens=sums[1], cache_creation_tokens=sums[2],
        cache_read_tokens=sums[3],
        requests=len(entries), tools=len(acc.tools), start=acc.first, end=acc.last,
        fallback_time=fallback_time,
        versions=tuple(sorted(acc.versions, key=lambda v: (version_key(v), v))),
        hardlink=hardlink, oversize_lines=info.oversize, background=None,
    ))


def _read_session(folder_path, folder_name, sid, res: ReadResult) -> None:
    sub_dir = os.path.join(folder_path, sid, "subagents")
    listing = _list_dir(sub_dir)
    if listing is None:
        res.quality["carpetas ilegibles"] += 1
        return
    kinds = dict(listing)
    for name, kind in listing:
        if kind == "link":
            res.quality["enlaces omitidos"] += 1
            continue
        if kind != "file" or not name.startswith("agent-") or not name.endswith(".jsonl"):
            continue
        if not valid_agent_file(name):
            res.quality["nombres no validos omitidos"] += 1
            continue
        _read_call(sub_dir, name, kinds, folder_name, sid, res)


def _read_project_folder(folder_path, folder_name, res: ReadResult) -> None:
    for sid, _has_main, has_dir in _enum_sessions(folder_path, res.quality) or ():
        if has_dir:   # el lector solo abre transcripciones de subagentes
            _read_session(folder_path, folder_name, sid, res)


def _recent_first(labels) -> str:
    """Hasta MAX_SHOWN_VERSIONS versiones, las mas recientes primero, y cuantas quedan fuera."""
    ordered = sorted(labels, key=lambda v: (version_key(v), v), reverse=True)
    text = ", ".join(ordered[:MAX_SHOWN_VERSIONS])
    if len(ordered) > MAX_SHOWN_VERSIONS:
        text += " (+%d mas)" % (len(ordered) - MAX_SHOWN_VERSIONS)
    return text


def _versions_text(seen, failing=None) -> str:
    """Resumen acotado de versiones: rango y cantidad de las vistas (el rango no oculta la
    version nueva), las posteriores a VERIFIED_MAX y las de los archivos que fallan."""
    numeric = sorted((v for v in seen if _VERSION_PARTS_RE.match(v)), key=lambda v: (version_key(v), v))
    if not seen:
        return "(ninguna)"
    if not numeric:
        text = "(ninguna reconocida)"
    elif len(numeric) == 1:
        text = "%s (1 version)" % numeric[0]
    else:
        text = "%s a %s (%d versiones)" % (numeric[0], numeric[-1], len(numeric))
    later = [v for v in numeric if is_unverified(v)]
    if later:
        text += ". Posteriores a la ultima verificada: " + _recent_first(later)
    bad = [v for v in (failing or ()) if _VERSION_PARTS_RE.match(v)]
    if bad:
        text += ". En archivos que fallan: " + _recent_first(bad)
    return text


def _schema_message(headline: str, versions, failing=None) -> str:
    return ("esquema desconocido: " + headline + ". Versiones de Claude Code vistas: "
            + _versions_text(versions, failing) + ". Ultima version verificada: " + VERIFIED_MAX
            + ". Ejecute el subcomando inspect para diagnosticar.")


def check_schema(res: ReadResult) -> None:
    """Lanza SchemaError si alguna comprobacion de esquema fallo en algun archivo."""
    if res.schema:
        parts = ["%s: %d archivos" % (name, res.schema[name]) for name in sorted(res.schema)]
        raise SchemaError(_schema_message("; ".join(parts), res.versions, res.schema_versions))


def check_damaged(calls) -> None:
    """Lanza SchemaError si mas del MAX_DAMAGED_PERCENT % de las llamadas esta danado."""
    total = len(calls)
    damaged = sum(1 for c in calls if c.damage is not None)
    if total and damaged * 100 > total * MAX_DAMAGED_PERCENT:
        versions = collections.Counter(v for c in calls for v in c.versions)
        failing = collections.Counter(v for c in calls if c.damage is not None for v in c.versions)
        raise SchemaError(_schema_message(
            "demasiados archivos de subagente danados o ilegibles: %d de %d (limite %d %%)"
            % (damaged, total, MAX_DAMAGED_PERCENT), versions, failing))


def read_calls(claude_dir: str, project_dir=None, check_damage: bool = True) -> ReadResult:
    """Lee todas las llamadas de subagentes bajo <claude_dir>/projects (o solo las del proyecto).

    Lanza EnvError (entorno) o SchemaError (esquema desconocido, o danados sobre el umbral si
    check_damage). No escribe nada. Las llamadas salen en el orden del recorrido (carpetas,
    sesiones y archivos por nombre): la salida es determinista. Una sesion sin transcripciones
    de subagentes no produce llamadas; el reporte de sesiones sale de las llamadas."""
    projects = os.path.join(claude_dir, "projects")
    reason = _projects_dir_state(projects)
    if reason is not None:
        raise EnvError(reason)
    listing = _list_dir(projects)
    if listing is None:
        raise EnvError("no se puede leer projects/")
    wanted = None
    if project_dir is not None:
        wanted = derive_folder_name(os.path.abspath(project_dir)).lower()
    res = ReadResult()
    for name, kind in listing:
        if kind == "link":
            res.quality["enlaces omitidos"] += 1
        elif kind == "dir":
            if not valid_dir_name(name):
                res.quality["nombres no validos omitidos"] += 1
            elif wanted is None or name.lower() == wanted:
                _read_project_folder(os.path.join(projects, name), name, res)
    check_schema(res)
    if check_damage:
        check_damaged(res.calls)
    return res


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
    "hardlinks (nlink > 1)",
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
    except (SchemaError, EnvError) as exc:  # mensajes de texto fijo, sin contenido ni rutas
        print("error: " + exc.message, file=sys.stderr)
        return EXIT_SCHEMA if isinstance(exc, SchemaError) else EXIT_ENV
    except Exception as exc:  # noqa: BLE001 - nunca un traceback: podria arrastrar contenido
        print("error: error no previsto (" + type(exc).__name__ + ")", file=sys.stderr)
        return EXIT_ENV


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
