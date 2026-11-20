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


def _digest(value: str, key: bytes = b"") -> bytes:
    """Resumen blake2b de 8 bytes. Con `key` (clave por ejecucion, ver read_calls) el resumen no se
    puede recalcular desde fuera de la ejecucion; sin ella solo sirve para conjuntos en memoria."""
    return hashlib.blake2b(value.encode("utf-8", "surrogatepass"), digest_size=8, key=key).digest()


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
#
# T4 (skills): de un bloque `tool_use` de nombre `Skill` se lee ademas `name` e `input.skill`; NUNCA
# `input.args` (puede llevar contenido). Se leen las lineas `assistant` de la sesion principal
# (`<sesion>.jsonl`) y las de cada subagente. El origen de una invocacion sale del ARCHIVO donde esta
# (sesion principal o subagente, y el agente de ese archivo), no de `isSidechain` ni de `agentId`: asi no
# se lee ninguna clave mas. La hora es la de la linea del tool_use. Los topes (tamano, ids, lineas), la
# firma estructural y la regla "un archivo omitido a mitad no deja nada" son los del lector de subagentes;
# los enlaces duros SI se aceptan en subagentes (decision G1) y NO en sesiones principales (G1 no los
# observo ahi: se rechazan y se cuentan). Los identificadores internos (`call_id`, `session`, `agent_key`)
# son resumenes con una clave aleatoria por ejecucion (read_calls): un CallRecord o un SkillUse no debe
# serializarse jamas (T5 a T7: nada de asdict, vars, pickle ni __dict__; una prueba lo vigila).
#
# LIMITACIONES DEL CONTEO DE SKILLS (SKILL_LIMITATIONS, que T5 vuelca en "Como leer estos numeros"):
#   (a) Un subagente con una linea intermedia corrupta conserva sus skills (su llamada queda danada para
#       los tokens, no para las skills), y una sesion principal con lineas corruptas tambien se lee: una
#       linea corrupta puede esconder una invocacion, y eso es un subconteo SILENCIOSO.
#   (b) Las skills que el usuario invoca con `/nombre` no generan un `tool_use` de Skill y no se cuentan.
#   Las sesiones principales omitidas (enlace duro, tope de tamano, ilegibles) si avisan: salen en
#   `ReadResult.warnings` (WARN_MAIN_*) y en `read_quality`.
# Los nombres de skill de USUARIO salen tal cual (si pasan SKILL_NAME_RE), a diferencia de los agentes de
# usuario, que salen como `(otro agente)`: riesgo de privacidad asimetrico (ver SKILL_NAME_RE; T6).

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
# Clave interna de las llamadas sin meta: una constante FUERA del espacio de los resumenes (los
# resumenes son 16 caracteres hexadecimales; esta cadena no lo es), para que ningun agentType fabricado
# la reproduzca y para que nunca se tomen por "el mismo agente".
NO_META_KEY = "<sin-meta>"
# Skills: igual que los agentes, el nombre visible sale de listas cerradas o de un patron estrecho. Un
# nombre con ":" es de un plugin y solo se muestra su PREFIJO validado (como en classify_agent). Un nombre
# que no pasa el patron se muestra como "(otra skill)". El nombre de una skill es configuracion, no
# contenido de conversacion, pero puede revelar nombres privados (de skills de usuario, que se muestran
# si pasan el patron, y de plugins, por el prefijo): riesgo aceptado y documentado (T8).
# ASIMETRIA DE PRIVACIDAD: un agente de usuario sale como `(otro agente)` (lista cerrada), pero una skill
# de usuario sale TAL CUAL su nombre si pasa el patron. T6 debe valorar, para el reporte global
# compartible, agrupar las skills de usuario como `(otra skill)` salvo una lista cerrada de integradas.
# El patron no admite ":" (los nombres con ":" son de plugin y se tratan antes, en classify_skill).
SKILL_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
OTHER_SKILL = "(otra skill)"
# SyncLayer no distribuye skills hoy: el conjunto existe para cuando las haya (una prueba lo fija vacio).
# Si algun dia hay un `skills/` en el repositorio, derivar el conjunto de sus nombres (como los agentes,
# que una prueba compara con agents/*.md) en lugar de mantener la lista a mano.
SYNCLAYER_SKILLS = frozenset()
# Skills integradas de Claude Code que se reconocen por nombre. VACIA a proposito: ninguna fuente del
# repositorio (G1 incluida) verifica nombres de skills integradas, y los comandos (`init`, `review`,
# `security-review`...) no son skills. Hasta tener evidencia, toda skill sale en el conjunto "otros"
# (visible si pasa el patron). Aunque se llene, un nombre de la lista NO distingue una skill integrada de
# una skill de usuario con el mismo nombre: sale como "integrado" igualmente, y el reporte debe decirlo.
BUILTIN_SKILLS = frozenset()
ORIGIN_MAIN = "sesion"          # la skill se invoco en la sesion principal
ORIGIN_SUBAGENT = "subagente"   # la skill se invoco dentro de un subagente
# Alias de modelo que el meta puede traer en lugar de un id completo (lista cerrada).
# "inherit" NO esta: no es un modelo (el subagente hereda el del padre), se trata como ausente.
MODEL_ALIASES = frozenset(("opus", "sonnet", "haiku", "fable"))
NOT_A_MODEL = frozenset(("inherit",))
_DATE_SUFFIX_RE = re.compile(r"[-@][0-9]{8}\Z")

# Avisos de texto fijo para el reporte (T5): salen de ReadResult.warnings. Sin datos. Llevan tildes y enes
# como escapes \u00xx: el reporte es en espanol correcto y el fuente sigue siendo ASCII.
WARN_NO_MESSAGE_ID = ("hay l\u00edneas con usage sin message.id: cada l\u00ednea se cuenta como una petici\u00f3n "
                      "y no se puede deduplicar")
WARN_ID_REPEATED = ("hay message.id repetidos entre archivos (p. ej. agentes reanudados): el "
                    "segundo archivo no suma esas peticiones")
WARN_ID_CAP = ("se alcanz\u00f3 el tope de ids para deduplicar entre archivos: puede haber peticiones "
               "repetidas sin detectar")
WARN_SKILL_ID_REPEATED = ("hay tool_use de Skill con el mismo id en varios archivos (p. ej. agentes "
                          "reanudados): la segunda aparici\u00f3n no se cuenta")
WARN_SKILL_ID_CAP = ("se alcanz\u00f3 el tope de ids de Skill para deduplicar entre archivos: puede haber "
                     "invocaciones repetidas sin detectar")
WARN_MAIN_HARDLINK = ("hay sesiones principales omitidas por ser enlaces duros: sus invocaciones de "
                      "Skill no se cuentan")
WARN_MAIN_CAP = ("hay sesiones principales omitidas por superar el tope de tama\u00f1o: sus invocaciones de "
                 "Skill no se cuentan")
WARN_MAIN_UNREADABLE = "hay sesiones principales ilegibles: sus invocaciones de Skill no se cuentan"
# T6: el alias de proyecto son 32 bits de un hash sin sal: dos carpetas distintas pueden coincidir (improbable).
WARN_ALIAS_COLLISION = ("hay carpetas de proyecto distintas con el mismo alias (colisi\u00f3n de 32 bits, improbable): "
                        "sus llamadas se agrupan como un solo proyecto")

# Limitaciones del conteo de skills: texto fijo para "Como leer estos numeros" (T5), como
# REPEAT_LIMITATIONS. Las dos son subconteos SILENCIOSOS (el lector no puede saber que se perdio algo).
SKILL_LIMITATIONS = (
    "Una l\u00ednea corrupta en medio de una sesi\u00f3n principal o de un subagente se descarta y puede esconder"
    " una invocaci\u00f3n de Skill: el conteo de skills puede ser menor que el real.",
    "Las skills que el usuario invoca con /nombre no generan un bloque tool_use de Skill y no se cuentan:"
    " solo se cuentan las que invoca el modelo.",
)

# Comprobaciones de esquema (exit 3). Los nombres salen en el mensaje: texto fijo.
CHK_USAGE_OBJ = "usage presente y no es objeto"
CHK_TOKENS = "campo de tokens que no es entero no negativo"
# Verificado con datos reales en G1+: 0 lineas user/assistant sin timestamp (el 100 % de las lineas `user`,
# `assistant`, `attachment` y `system` lo traen) y 0 lineas corruptas; solo `file-history-snapshot`,
# `last-prompt` y similares carecen de el, y la firma estructural no los exige. Vale tambien para las
# sesiones principales (CHK_TS y CHK_NO_TYPE se aplican a ellas con la misma firma).
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


def classify_skill(raw):
    """(nombre visible, conjunto) de un `input.skill`.

    Igual que classify_agent: SyncLayer e integrado salen de listas cerradas; un nombre con ":" es de un
    plugin y solo se muestra el PREFIJO validado con PLUGIN_PREFIX_RE, como `plugin:<prefijo>` (nombre
    y conjunto); lo que hay tras el primer ":" nunca se muestra. El resto pasa por SKILL_NAME_RE y se
    muestra tal cual (conjunto "otros"); lo que no la cumple, o no es una cadena, es "(otra skill)".

    PRIVACIDAD: los nombres de skill de USUARIO salen tal cual, a diferencia de los agentes de usuario
    (que salen como `(otro agente)`): riesgo asimetrico. T6 debe valorar agrupar las skills de usuario en
    el reporte global compartible (opcion: `(otra skill)` salvo una lista cerrada de integradas)."""
    if isinstance(raw, str):
        if raw in SYNCLAYER_SKILLS:
            return raw, "SyncLayer"
        if raw in BUILTIN_SKILLS:
            return raw, "integrado"
        if ":" in raw:
            prefix = raw.split(":", 1)[0]
            if PLUGIN_PREFIX_RE.match(prefix):
                label = "plugin:" + prefix
                return label, label
            return OTHER_SKILL, "plugin:(no-valido)"
        if SKILL_NAME_RE.match(raw):
            return raw, "otros"
    return OTHER_SKILL, "otros"


@dataclasses.dataclass(frozen=True)
class CallRecord:
    """Una llamada a un subagente (un agent-<id>.jsonl). Sin contenido: solo numeros y
    etiquetas de listas cerradas. Los identificadores son resumenes (blake2b de 64 bits) para
    agrupar en memoria; no se escriben en ningun reporte.

    `agent_key`: resumen blake2b de 8 bytes (con la clave de la ejecucion) del NOMBRE CANONICO del
    agente: el `agentType` crudo del meta, con "" equivalente a DEFAULT_AGENT (NO_META_KEY sin meta).
    Es la identidad interna del agente: las etiquetas visibles (`agent`, `agent_group`) juntan
    agentes distintos ("(otro agente)", "plugin:<prefijo>"), la clave no. Solo T3 la usa (repeticiones
    y numero de agentes por conjunto); no entra en `repr`/`str` ni en ningun reporte.

    `call_id`, `session` y `agent_key` llevan la clave aleatoria de la ejecucion: no se pueden
    recalcular desde fuera ni comparar entre ejecuciones. Los tres (y `seq`) tienen `repr=False`: ni
    `repr` ni `str` de un CallRecord los muestran. Un CallRecord no se serializa nunca (T5 a T7).

    `seq`: ordinal de recorrido, 0, 1, 2... en el orden DETERMINISTA de enumeracion de `read_calls`
    (carpetas, sesiones y archivos ordenados por nombre). Es el unico desempate permitido cuando dos
    llamadas coinciden en una clave de orden visible: `call_id`, `session` y `agent_key` cambian en cada
    ejecucion (clave aleatoria) y ordenar o desempatar con ellos haria que los mismos datos dieran
    metricas distintas (3.6: mismos argumentos, mismos bytes). No se escribe en ningun reporte.

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
    call_id: str = dataclasses.field(repr=False)     # resumen con clave: no sale en repr (ver arriba)
    project: str            # alias p-<8 hex> (3.7)
    session: str = dataclasses.field(repr=False)     # resumen de la sesion, solo para agrupar
    agent: str              # nombre visible (lista cerrada) o "(otro agente)" / "(sin-meta)"
    agent_group: str        # SyncLayer | integrado | plugin:<prefijo> | plugin:(no-valido) | otros | sin-meta
    agent_key: str = dataclasses.field(repr=False)   # identidad interna del agente (ver arriba)
    seq: int = dataclasses.field(repr=False)         # ordinal de recorrido (ver arriba)
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
        """Entra en las estadisticas de tokens (sumas, medianas, p90): tiene usage, el archivo no
        esta danado y aporta al menos una peticion. Un archivo cuyos message.id ya conto otro
        archivo (agente reanudado) queda con requests = 0 y tokens 0: tiene `has_usage` pero no es
        `usable`, para que sus ceros no bajen las medianas. Sigue sin estar `excluded`."""
        return self.has_usage and self.damage is None and self.requests > 0

    @property
    def excluded(self) -> bool:
        """Llamada danada (damage no es None): fuera de las estadisticas de tokens. Distinto de
        `usable`: una llamada `sin_usage` no esta excluida."""
        return self.damage is not None

    @property
    def unverified(self) -> bool:
        return any(is_unverified(v) for v in self.versions)


@dataclasses.dataclass(frozen=True)
class SkillUse:
    """Una invocacion de la herramienta Skill (un bloque tool_use de nombre `Skill`). Sin contenido:
    `skill` y `group` salen de classify_skill (lista cerrada o patron estrecho), nunca `input.args`.

    `origin`: ORIGIN_MAIN (sesion principal) u ORIGIN_SUBAGENT; en este ultimo caso `agent` y
    `agent_group` son el agente (etiquetas visibles) del archivo de subagente donde se encontro, y en el
    primero None. `moment`: marca de tiempo de la linea del tool_use (UTC) o None. `session`: resumen con
    la clave de la ejecucion, el MISMO que el de las llamadas de esa sesion (CallRecord.session); sirve
    para contar sesiones distintas, no se escribe en ningun reporte y tiene `repr=False`. No se serializa
    (ver CallRecord)."""
    skill: str
    group: str
    origin: str
    project: str            # alias p-<8 hex> (3.7)
    session: str = dataclasses.field(repr=False)   # resumen con clave: no sale en repr
    moment: object           # datetime UTC o None
    agent: object           # etiqueta visible del agente o None
    agent_group: object


class ReadResult:
    def __init__(self):
        self.calls = []
        self.skill_uses = []                   # SkillUse, en el orden del recorrido
        self._key = b""                        # clave de los resumenes (la fija read_calls)
        self._seen_skill_ids = set()           # digests de id de tool_use Skill ya contados (entre archivos)
        self.quality = collections.Counter()
        self.schema = collections.Counter()    # comprobacion -> archivos
        self.versions = collections.Counter()  # version filtrada -> archivos
        self.schema_versions = collections.Counter()  # version -> archivos que fallan una comprobacion
        self._seen_ids = set()                 # digests de message.id ya sumados (entre archivos)
        self._seen_inodes = set()              # (st_dev, st_ino) de los hardlinks (nlink > 1) ya leidos
        self._alias_folders = set()            # (alias, nombre de carpeta en minusculas) leidos; solo en memoria

    def release_key(self) -> None:
        """Olvida la clave de los resumenes (`_key = None`). T7 la invoca cuando ya no se crean mas
        resumenes (tras leer y agregar): sin la clave, call_id/session/agent_key no se pueden recalcular
        ni siquiera desde este objeto. `read_calls` NO la libera: las pruebas la necesitan."""
        self._key = None

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
        if self.quality["skills: id repetido entre archivos"] > 0:
            out.append(WARN_SKILL_ID_REPEATED)
        if self.quality["skills: ids sin deduplicar (tope)"] > 0:
            out.append(WARN_SKILL_ID_CAP)
        if self.quality["sesiones principales omitidas por enlace duro"] > 0:
            out.append(WARN_MAIN_HARDLINK)
        if self.quality["sesiones principales omitidas por tope de tamano"] > 0:
            out.append(WARN_MAIN_CAP)
        if self.quality["sesiones principales ilegibles"] > 0:
            out.append(WARN_MAIN_UNREADABLE)
        if self.quality["alias de proyecto repetido entre carpetas"] > 0:
            out.append(WARN_ALIAS_COLLISION)
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
        self.skills = []       # (digest del id o None, nombre visible, conjunto, hora, nombre era cadena)
        self.skill_ids = set()


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


def _acc_head(obj: dict, acc: _CallAcc):
    """Parte comun a los dos lectores: tipo, version y hora de la linea. Devuelve (type, hora UTC)."""
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
    return kind, ts


def _acc_skill(block: dict, ts, acc: _CallAcc) -> None:
    """Una invocacion de la herramienta Skill: de un bloque tool_use solo `name`, `id` e `input.skill`
    (NUNCA `input.args`). Se deduplica por el id del bloque dentro del archivo; un bloque sin id (o con un
    id que no es cadena) cuenta cada vez que aparece. El nombre se clasifica aqui: no se conserva crudo."""
    if block.get("name") != "Skill":
        return
    block_id = block.get("id")
    key = None
    if isinstance(block_id, str):
        key = _digest(block_id)
        if key in acc.skill_ids:
            return
        if len(acc.skill_ids) >= MAX_IDS_PER_FILE:
            raise _TooBig()
        acc.skill_ids.add(key)
    if len(acc.skills) >= MAX_IDS_PER_FILE:
        raise _TooBig()
    tool_input = block.get("input")
    raw = tool_input.get("skill") if isinstance(tool_input, dict) else None
    label, group = classify_skill(raw)
    acc.skills.append((key, label, group, ts, isinstance(raw, str)))


def _acc_main_line(obj: dict, acc: _CallAcc) -> None:
    """Linea de la sesion principal: solo las invocaciones de Skill de las lineas `assistant` de
    peticiones reales (no `<synthetic>`)."""
    kind, ts = _acc_head(obj, acc)
    if kind != "assistant":
        return
    message = obj.get("message")
    if not isinstance(message, dict) or message.get("model") == SYNTHETIC_MODEL:
        return
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                _acc_skill(block, ts, acc)


def _acc_line(obj: dict, acc: _CallAcc) -> None:
    kind, ts = _acc_head(obj, acc)
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
                _acc_skill(block, ts, acc)


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
    "message.id repetido entre archivos" y avisa. La peticion se atribuye al archivo que se recorre
    PRIMERO (carpetas, sesiones y archivos por nombre, orden alfabetico), NO al de inicio mas
    temprano: atribuir al mas temprano exigiria conservar los ids de cada archivo hasta el final
    y rehacer las sumas, y no es barato. El total no cambia; si cambia el reparto entre agentes,
    proyectos y ventana cuando el id repetido cae en llamadas distintas (el aviso lo senala). Un archivo danado no registra sus ids (sus
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
            if hardlink and st.st_ino:
                # el mismo inodo con dos nombres dentro de projects/ es UNA transcripcion: el nombre
                # que se recorre primero crea la llamada; el otro se cuenta aparte y no suma nada
                ident = (st.st_dev, st.st_ino)
                if ident in res._seen_inodes:
                    res.quality["hardlinks duplicados dentro de projects"] += 1
                    return
                res._seen_inodes.add(ident)
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
    sums = [0, 0, 0, 0]
    for entry in entries:
        sums = [total + value for total, value in zip(sums, entry)]
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
        seq=len(res.calls),    # ordinal de recorrido (CallRecord.seq)
        call_id=_digest(folder_name + "\0" + sid + "\0" + stem, res._key).hex(),
        project=_project_alias(folder_name),
        session=_session_digest(folder_name, sid, res._key),
        agent=agent, agent_group=group, status=status, damage=damage,
        # nombre canonico: agentType "" y general-purpose son el mismo agente
        agent_key=_digest(agent_raw or DEFAULT_AGENT, res._key).hex() if (present and not meta_bad) else NO_META_KEY,
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
    if failure is None:   # un archivo omitido a mitad de lectura (acc reiniciado) no deja skills
        _merge_skills(acc, res, folder_name, sid, ORIGIN_SUBAGENT, agent, group)


def _project_alias(folder_name: str) -> str:
    """Alias del proyecto en el reporte global (3.7): p- y 8 hex del SHA-256 del nombre en minusculas.
    Estable entre ejecuciones a proposito (no lleva la clave de la ejecucion)."""
    return "p-" + hashlib.sha256(folder_name.lower().encode("utf-8", "surrogatepass")).hexdigest()[:8]


def _session_digest(folder_name: str, sid: str, key: bytes) -> str:
    return _digest(folder_name + "\0" + sid, key).hex()


def _merge_skills(acc: _CallAcc, res: ReadResult, folder_name, sid, origin, agent, agent_group) -> None:
    """Pasa las invocaciones de Skill de UN archivo (leido sin fallos) al resultado. Un id de tool_use ya
    contado en otro archivo no se vuelve a contar (se anota y avisa); pasado MAX_IDS_GLOBAL no se recuerdan
    ids nuevos (no se omite nada: se cuenta aparte y avisa). El primer archivo del recorrido gana: la sesion
    principal antes que los subagentes de su sesion."""
    q = res.quality
    seen = res._seen_skill_ids
    project = _project_alias(folder_name)
    session = _session_digest(folder_name, sid, res._key)
    for key, label, skill_group, ts, named in acc.skills:
        if key is None:
            q["skills: tool_use sin id"] += 1
        elif key in seen:
            q["skills: id repetido entre archivos"] += 1
            continue
        elif len(seen) < MAX_IDS_GLOBAL:
            seen.add(key)
        else:
            q["skills: ids sin deduplicar (tope)"] += 1
        if not named:
            q["skills: nombre no cadena"] += 1
        res.skill_uses.append(SkillUse(
            skill=label, group=skill_group, origin=origin, project=project, session=session, moment=ts,
            agent=agent, agent_group=agent_group))


def _read_main(folder_path, folder_name, sid, res: ReadResult) -> None:
    """Lee `<sesion>.jsonl` SOLO para las invocaciones de Skill (ver la cabecera de la seccion). Los
    enlaces duros se rechazan y se cuentan; un archivo omitido o ilegible no deja nada."""
    q = res.quality
    try:
        f = _open_regular(os.path.join(folder_path, sid + ".jsonl"))
    except LinkRefused:
        q["sesiones principales omitidas por enlace duro"] += 1
        return
    except OSError:
        q["sesiones principales ilegibles"] += 1
        return
    acc = _CallAcc()
    info = _LineInfo()
    try:
        with f:
            if os.fstat(f.fileno()).st_size > MAX_FILE_BYTES:
                raise _TooBig()
            for obj in _iter_objects(f, info):
                _acc_main_line(obj, acc)
    except _TooBig:
        q["sesiones principales omitidas por tope de tamano"] += 1
        return
    except OSError:
        q["sesiones principales ilegibles"] += 1
        return
    if acc.lines and not acc.typed:
        acc.schema.add(CHK_NO_TYPE)
    for check in acc.schema:
        res.schema[check] += 1
    for label in acc.versions:
        res.versions[label] += 1
        if acc.schema:
            res.schema_versions[label] += 1
    q["sesiones principales leidas"] += 1
    q["lineas corruptas (sesion principal)"] += info.corrupt
    q["lineas oversize (sesion principal)"] += info.oversize
    q["lineas que no son objeto (sesion principal)"] += info.not_object
    if info.truncated_tail:
        q["sesiones principales con ultima linea truncada"] += 1
    _merge_skills(acc, res, folder_name, sid, ORIGIN_MAIN, None, None)


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


def _count_alias_collisions(res: ReadResult) -> int:
    """Alias compartidos por carpetas DISTINTAS (nombres en minusculas distintos). `c--x` y `C--x` son el
    mismo proyecto y no cuentan. El alias son 32 bits de un hash sin sal: una colision es improbable, pero si
    ocurre el agregado cuenta esas carpetas como un solo proyecto y el reporte lo avisa."""
    count, prev, run = 0, None, 0
    for alias in sorted(alias for alias, _ in res._alias_folders):   # un par por (alias, nombre) distinto
        run = run + 1 if alias == prev else 1
        if run == 2:
            count += 1
        prev = alias
    return count


def _read_project_folder(folder_path, folder_name, res: ReadResult) -> None:
    res._alias_folders.add((_project_alias(folder_name), folder_name.lower()))
    for sid, has_main, has_dir in _enum_sessions(folder_path, res.quality) or ():
        if has_main:   # la sesion principal solo se lee para las invocaciones de Skill (T4)
            _read_main(folder_path, folder_name, sid, res)
        if has_dir:
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


def read_calls(claude_dir: str, project_dir=None, check_damage: bool = True,
               digest_key=None) -> ReadResult:
    """Lee todas las llamadas de subagentes bajo <claude_dir>/projects (o solo las del proyecto) y las
    invocaciones de Skill de las sesiones principales y de los subagentes (T4).

    Lanza EnvError (entorno) o SchemaError (esquema desconocido, o danados sobre el umbral si
    check_damage). No escribe nada. Las llamadas salen en el orden del recorrido (carpetas,
    sesiones y archivos por nombre): la salida es determinista. Una sesion sin transcripciones
    de subagentes no produce llamadas (si produce invocaciones de Skill); el reporte de sesiones
    sale de las llamadas y de las invocaciones.

    `call_id`, `session` y `agent_key` son resumenes blake2b con una clave aleatoria generada aqui,
    por ejecucion (os.urandom): no se pueden recalcular desde fuera ni comparar entre ejecuciones.
    `digest_key` (bytes, hasta 64) la fija a mano; solo para pruebas reproducibles.

    Con check_damage=False el 5 % de danadas no se comprueba aqui: T3 (aggregate_calls) lo mide
    sobre las llamadas de la ventana. Un message.id repetido entre archivos se atribuye al
    archivo que se recorre primero (ver _drop_repeated_ids). Dos nombres del mismo inodo dentro
    de projects/ (hardlinks) son una sola llamada. Al terminar se liberan los conjuntos de ids e
    inodos de ReadResult (None)."""
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
    res._key = digest_key if digest_key is not None else os.urandom(16)
    for name, kind in listing:
        if kind == "link":
            res.quality["enlaces omitidos"] += 1
        elif kind == "dir":
            if not valid_dir_name(name):
                res.quality["nombres no validos omitidos"] += 1
            elif wanted is None or name.lower() == wanted:
                _read_project_folder(os.path.join(projects, name), name, res)
    res.quality["alias de proyecto repetido entre carpetas"] = _count_alias_collisions(res)
    res._alias_folders = None   # nombres de carpeta: no deben sobrevivir a la lectura
    res._seen_ids = None      # memoria: ya no se necesitan al terminar la lectura
    res._seen_inodes = None
    res._seen_skill_ids = None
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


# --- Agregacion y metricas (T3) ---
#
# Funciones PURAS: reciben llamadas ya leidas (un ReadResult o una lista de CallRecord) y una
# ventana, y devuelven dataclasses inmutables con solo numeros y etiquetas de listas cerradas
# (nombres de agente, conjuntos, modelos y versiones ya filtrados por el lector). No hacen E/S
# (ni siquiera leen el reloj: `utc_today` lo lee el llamador y lo inyecta) y no devuelven
# contenido, rutas, identificadores de llamada ni de sesion. El alias de proyecto `p-<8 hex>` es
# un dato interno que solo T6 muestra.
#
# Definiciones (3.5 del plan, con las notas de T2 a T3):
#   - Ventana: fechas UTC con ambos extremos inclusivos. Una llamada pertenece a la ventana por su
#     primera marca de tiempo (`start`); sin `start` se usa `fallback_time` (mtime, APROXIMADA);
#     sin ninguna de las dos solo entra con la ventana "todo" (`--all`). Un instante cuenta por su
#     fecha UTC: 00:00:00 de `since` entra; 23:59:59.999999 de `until` entra; el instante siguiente
#     no. Una hora con zona se lleva a UTC antes; una hora sin zona se toma como UTC.
#   - El 5 % de danadas (check_damaged) se mide sobre las llamadas de la ventana MAS las danadas sin
#     ninguna hora (ni start ni fallback_time), que no pueden ubicarse y quedarian fuera del umbral
#     (criterio conservador: suman al numerador y al denominador; las no danadas sin hora, no).
#   - Tokens, sumas, medianas y p90: solo llamadas `usable` (usage, no danadas, requests > 0).
#     Duracion, herramientas y modelos: todas las no `excluded` (incluidas las sin usage).
#   - Mediana: con n par, media de los dos centrales redondeada al entero, medio hacia arriba.
#   - p90: rango mas cercano, el valor en la posicion ceil(0,9 n) (de 1 a n) de la lista ordenada;
#     determinista, sin interpolar. `small` marca n < 10 ("n pequeno").
#   - Duracion: ultima menos primera marca de tiempo, en segundos enteros (medio hacia arriba).
#   - Repeticiones consecutivas (INFERIDO, no es un reintento confirmado): dentro de una sesion se
#     ordenan TODAS las llamadas con inicio y fin por (inicio, fin, seq); una llamada cuenta si la
#     anterior en ese orden es del mismo agente (`agent_key`) y termino ESTRICTAMENTE antes de que
#     esta empezara. Las paralelas y las separadas por otro agente no cuentan. Cuenta la llamada
#     posterior, y se atribuye a su agente. Una llamada danada que conservo sus horas participa.
#     "Mismo agente" = misma `agent_key` (resumen del NOMBRE CANONICO: "" = general-purpose), no la misma etiqueta
#     visible: dos agentes de un mismo plugin, o dos agentes de usuario, no se repiten entre si.
#     Las llamadas SIN meta (clave constante) participan en la cadena (rompen la de otros) pero
#     nunca se marcan: sin meta no hay identidad de agente. Es una senal INFERIDA con limites
#     conocidos (REPEAT_LIMITATIONS, que T5 vuelca en "Como leer estos numeros").
#   - Rango de version de Claude Code de una llamada: sus lineas pueden traer varias versiones. Si
#     alguna cae en 2.1.310-2.1.327 (tokens posiblemente inflados) la llamada va al rango dudoso;
#     si no, va al rango de su version MAS ALTA. Sin ninguna version numerica: RANGE_NONE (una sola
#     fila para "sin version" y "version no reconocible"; los contadores de calidad `without_version`
#     y `unrecognized_version` las separan). El numero de llamadas con versiones en varios rangos
#     se informa en la calidad de datos.
#   - Agrupacion: las filas por agente son por (nombre visible, conjunto), nunca solo por nombre:
#     "(otro agente)" lo comparten los agentes de usuario y los de plugin con prefijo no valido, que son
#     conjuntos distintos. La IDENTIDAD de un agente es `agent_key` (nombre canonico, "" = general-purpose):
#     el numero de agentes de un conjunto cuenta `agent_key` distintas, y las repeticiones comparan `agent_key`.
#   - Skills (T4): una invocacion pertenece a la ventana por la hora de la linea de su tool_use (sin hora,
#     solo con la ventana "todo"). Se cuentan por skill (nombre visible, conjunto), por conjunto y por
#     origen (sesion principal / subagente); las de subagentes se enlazan con el agente del archivo donde
#     estan. Sesiones = resumenes de sesion distintos (los subagentes comparten el de su sesion). Solo
#     conteos: no se atribuye ningun token, duracion ni costo a una skill (corre en el contexto de la
#     sesion) y la comparacion con otros conjuntos es de conteos y distribucion, no de calidad ni ahorro.

WINDOW_DAYS = 30
SMALL_N = 10          # con menos llamadas, mediana y p90 dicen poco
RANGE_BEFORE = "<2.1.310"
RANGE_DOUBTFUL = "2.1.310-2.1.327"
RANGE_AFTER = ">=2.1.328"
RANGE_NONE = "sin version reconocible"   # sin version o con versiones que no son numericas
VERSION_RANGES = (RANGE_BEFORE, RANGE_DOUBTFUL, RANGE_AFTER, RANGE_NONE)
_DOUBTFUL_FROM = (2, 1, 310)
_DOUBTFUL_TO = (2, 1, 327)

# Limitaciones de la senal "repeticiones consecutivas": texto fijo para "Como leer estos numeros" (T5).
REPEAT_LIMITATIONS = (
    "Las repeticiones son una se\u00f1al inferida por horas de inicio y fin, no un reintento confirmado.",
    "Una llamada puede marcarse aunque corra en paralelo con otra anterior del mismo agente: solo se"
    " mira la anterior inmediata por hora de inicio (A1 0-100, A2 10-20, A3 30-40: se marca A3).",
    "Las llamadas sin hora de inicio no participan en la cadena ni la rompen.",
    "La primera llamada de la ventana no se marca, aunque su anterior quedara fuera de la ventana.",
    "Las llamadas sin meta nunca se marcan, pero rompen la cadena de los dem\u00e1s agentes.",
    "En flujos secuenciales leg\u00edtimos (el mismo agente en pasos distintos de un plan) sobreestima.",
)

MSG_TODAY_REQUIRED = "aggregate_calls necesita `today` (o `window`): no lee el reloj"
MSG_WINDOW_RANGE = "la ventana sale del rango de fechas admitido"
MSG_WINDOW_INVALID = "ventana invalida: since y until deben ser fechas (datetime.date), ambas o ninguna, y since <= until"
MSG_WINDOW_TYPES = ("ventana invalida: today, since y until deben ser fechas (datetime.date; no datetime, "
                    "None ni cadena) y days un entero positivo")

# Contadores de la LECTURA completa (no de la ventana) que se copian al resultado, en orden fijo.
READ_QUALITY_LABELS = (
    "message.id repetido entre archivos",
    "message.id sin deduplicar entre archivos (tope)",
    "usage sin message.id",
    "hardlinks duplicados dentro de projects",
    "metas rechazadas por enlace duro",
    "archivos con ultima linea truncada",
    "lineas corruptas",
    "lineas oversize descartadas",
    "lineas que no son objeto",
    "lineas synthetic excluidas",
    "archivos omitidos por tope de tamano",
    "archivos ilegibles",
    "meta ilegible",
    "meta sobredimensionado",
    "enlaces omitidos",
    "nombres no validos omitidos",
    "carpetas ilegibles",
    "alias de proyecto repetido entre carpetas",
    # skills (T4) y lectura de las sesiones principales
    "skills: tool_use sin id",
    "skills: nombre no cadena",
    "skills: id repetido entre archivos",
    "skills: ids sin deduplicar (tope)",
    "sesiones principales leidas",
    "sesiones principales ilegibles",
    "sesiones principales omitidas por enlace duro",
    "sesiones principales omitidas por tope de tamano",
    "sesiones principales con ultima linea truncada",
    "lineas corruptas (sesion principal)",
    "lineas oversize (sesion principal)",
    "lineas que no son objeto (sesion principal)",
)


def utc_today():
    """Fecha actual en UTC. Es lo unico que lee el reloj: el llamador la inyecta (`today`)."""
    return datetime.datetime.now(datetime.timezone.utc).date()


@dataclasses.dataclass(frozen=True)
class Window:
    """Ventana de fechas UTC, ambos extremos inclusivos. since = until = None: sin ventana."""
    since: object   # datetime.date o None
    until: object

    def __post_init__(self):
        """ValueError si no son dos fechas (datetime.date, no datetime) con since <= until, o ninguna."""
        if self.since is None and self.until is None:
            return
        for value in (self.since, self.until):
            if not isinstance(value, datetime.date) or isinstance(value, datetime.datetime):
                raise ValueError(MSG_WINDOW_INVALID)
        if self.since > self.until:
            raise ValueError(MSG_WINDOW_INVALID)

    @property
    def is_all(self) -> bool:
        return self.since is None and self.until is None

    def contains(self, moment) -> bool:
        """True si el instante (con zona; sin zona se toma como UTC) cae en la ventana."""
        if self.is_all:
            return True
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        try:
            day = moment.astimezone(datetime.timezone.utc).date()
        except OverflowError:
            return False   # fuera del calendario al llevarlo a UTC: cae fuera de cualquier ventana
        return self.since <= day <= self.until


def _is_date(value) -> bool:
    """datetime.date, no datetime.datetime (que es subclase de date pero lleva hora)."""
    return isinstance(value, datetime.date) and not isinstance(value, datetime.datetime)


def make_window(today, since=None, until=None, all_time=False, days: int = WINDOW_DAYS) -> Window:
    """Ventana por defecto: las `days` fechas UTC que terminan en `today` (since = until - days + 1).
    `since`/`until` son datetime.date. ValueError si all_time se combina con fechas, si la ventana
    queda invertida o si sale del rango de fechas de Python (cerca de date.min). Los tipos se validan
    ANTES de restar o comparar: un datetime, None o una cadena dan ValueError (MSG_WINDOW_TYPES), no un
    TypeError. `today` solo se valida si hace falta (until ausente)."""
    if all_time:
        if since is not None or until is not None:
            raise ValueError("all_time es incompatible con since/until")
        return Window(None, None)
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError(MSG_WINDOW_TYPES)
    for value in (since, until):
        if value is not None and not _is_date(value):
            raise ValueError(MSG_WINDOW_TYPES)
    if until is None:
        if not _is_date(today):
            raise ValueError(MSG_WINDOW_TYPES)
        until = today
    if since is None:
        try:
            since = until - datetime.timedelta(days=days - 1)
        except OverflowError:
            raise ValueError(MSG_WINDOW_RANGE) from None
    if since > until:
        raise ValueError("ventana invertida")
    return Window(since, until)


@dataclasses.dataclass(frozen=True)
class Dist:
    """Distribucion de una lista de enteros. n = 0: median y p90 son None."""
    n: int
    total: int
    median: object
    p90: object
    small: bool     # 0 < n < SMALL_N


def distribution(values) -> Dist:
    data = sorted(values)
    n = len(data)
    if n == 0:
        return Dist(0, 0, None, None, False)
    mid = n // 2
    median = data[mid] if n % 2 else (data[mid - 1] + data[mid] + 1) // 2
    rank = -(-9 * n // 10)   # ceil(0,9 n) con enteros
    return Dist(n, sum(data), median, data[rank - 1], n < SMALL_N)


@dataclasses.dataclass(frozen=True)
class TokenStats:
    """Tokens por llamada de las llamadas `usable` (n). Cada campo es una Dist por llamada; su
    `total` es la suma sobre las llamadas."""
    n: int
    input_tokens: Dist
    output_tokens: Dist
    cache_creation_tokens: Dist
    cache_read_tokens: Dist
    total: Dist
    requests: Dist


@dataclasses.dataclass(frozen=True)
class VersionRow:
    range: str
    calls: int
    tokens: TokenStats

    @property
    def inflated(self) -> bool:
        """Rango con tokens posiblemente inflados por reintentos (corregido en 2.1.328)."""
        return self.range == RANGE_DOUBTFUL


@dataclasses.dataclass(frozen=True)
class ScopeMetrics:
    """Metricas de un conjunto de llamadas (todo, un agente, un conjunto o un proyecto)."""
    calls: int
    excluded: int
    sessions: int
    calls_per_session_tenths: object   # llamadas / sesiones en decimas (redondeo al mas cercano); None sin sesiones
    tokens: TokenStats
    duration: Dist                      # segundos; llamadas no excluidas con inicio y fin
    tools: Dist                         # llamadas no excluidas
    models: tuple                       # ((modelo, llamadas), ...) de las no excluidas
    repeats: int                        # INFERIDO: repeticiones consecutivas
    versions: tuple                     # un VersionRow por rango, en el orden de VERSION_RANGES


@dataclasses.dataclass(frozen=True)
class AgentMetrics:
    agent: str
    group: str
    metrics: ScopeMetrics


@dataclasses.dataclass(frozen=True)
class GroupMetrics:
    group: str
    agents: int
    metrics: ScopeMetrics


@dataclasses.dataclass(frozen=True)
class ProjectMetrics:
    project: str      # alias p-<8 hex>: dato interno, solo T6 lo muestra
    metrics: ScopeMetrics


@dataclasses.dataclass(frozen=True)
class DataQuality:
    """Conteos de calidad de datos sobre las llamadas de la ventana (salvo calls_read,
    calls_outside_window y without_any_time, que miran todas las leidas)."""
    calls_read: int
    calls_in_window: int
    calls_outside_window: int
    without_start: int            # en la ventana, sin marca de tiempo de inicio
    placed_by_fallback: int       # de ellas, ubicadas por fallback_time (hora APROXIMADA)
    without_any_time: int         # sin start ni fallback_time (entre todas las leidas)
    without_any_time_excluded: int  # de ellas, danadas: cuentan en el umbral de danadas de la ventana
    excluded: int                 # danadas: fuera de tokens, duracion y herramientas
    excluded_corrupt_line: int
    excluded_unreadable: int
    excluded_cap: int
    without_usage: int            # no danadas y sin usage
    all_ids_repeated: int         # con usage pero 0 peticiones propias (ids ya contados en otro archivo)
    without_meta: int
    tokens_calls: int             # llamadas que entran en las estadisticas de tokens
    without_version: int          # sin ninguna version en sus lineas
    unrecognized_version: int     # con versiones, ninguna numerica
    multiple_ranges: int          # versiones en varios rangos
    unverified_calls: int         # alguna version mayor que VERIFIED_MAX
    hardlinks: int                # hardlinks aceptados (decision G1)
    oversize_lines: int
    model_mismatch: int


@dataclasses.dataclass(frozen=True)
class SkillRow:
    """Una skill (nombre visible y conjunto) en la ventana. Solo conteos."""
    skill: str
    group: str
    calls: int              # invocaciones
    main_calls: int         # de ellas, desde la sesion principal
    subagent_calls: int     # de ellas, desde un subagente
    sessions: int           # sesiones distintas


@dataclasses.dataclass(frozen=True)
class SkillGroupRow:
    group: str
    skills: int             # nombres visibles distintos del conjunto
    calls: int
    sessions: int


@dataclasses.dataclass(frozen=True)
class SkillAgentRow:
    """Invocaciones de una skill hechas dentro de subagentes, por agente (etiquetas visibles)."""
    agent: str
    agent_group: str
    skill: str
    skill_group: str
    calls: int


@dataclasses.dataclass(frozen=True)
class SkillQuality:
    uses_read: int          # invocaciones leidas (todas, con o sin hora)
    in_window: int
    outside_window: int
    without_time: int       # sin marca de tiempo (solo entran con la ventana "todo")
    other_name: int         # en la ventana, con nombre no valido o no cadena: "(otra skill)"


@dataclasses.dataclass(frozen=True)
class SkillMetrics:
    calls: int
    sessions: int
    main_calls: int
    subagent_calls: int
    rows: tuple             # SkillRow: llamadas desc., skill, conjunto
    groups: tuple           # SkillGroupRow: llamadas desc., conjunto
    by_agent: tuple         # SkillAgentRow: llamadas desc., agente, conjunto, skill, conjunto de la skill
    quality: SkillQuality


@dataclasses.dataclass(frozen=True)
class UsageMetrics:
    window: Window
    total: ScopeMetrics
    agents: tuple             # AgentMetrics por (agente, conjunto): llamadas desc., agente, conjunto
    groups: tuple             # GroupMetrics: llamadas desc., conjunto
    projects: tuple           # ProjectMetrics: llamadas desc., alias
    versions_seen: tuple      # ((version, llamadas), ...) por version numerica, ascendente
    unverified_versions: tuple    # versiones vistas mayores que VERIFIED_MAX
    verified_max: str
    quality: DataQuality
    read_quality: tuple       # ((etiqueta, n), ...) de la lectura completa (no de la ventana)
    warnings: tuple           # avisos de texto fijo del lector (T5 los muestra en la cabecera)
    skills: SkillMetrics      # uso de skills en la ventana (T4)


def _range_of(key) -> str:
    if key < _DOUBTFUL_FROM:
        return RANGE_BEFORE
    if key <= _DOUBTFUL_TO:
        return RANGE_DOUBTFUL
    return RANGE_AFTER


def _numeric_versions(call) -> list:
    return [v for v in call.versions if _VERSION_PARTS_RE.match(v)]


def version_range(call) -> str:
    """Rango de version de una llamada (ver la cabecera de la seccion)."""
    numeric = _numeric_versions(call)
    if not numeric:
        return RANGE_NONE
    ranges = {_range_of(version_key(v)) for v in numeric}
    if RANGE_DOUBTFUL in ranges:
        return RANGE_DOUBTFUL
    return _range_of(max(version_key(v) for v in numeric))


def _spans_ranges(call) -> bool:
    return len({_range_of(version_key(v)) for v in _numeric_versions(call)}) > 1


def _call_moment(call):
    """(instante, aproximado) con el que la llamada se ubica en la ventana; (None, False) sin hora."""
    if call.start is not None:
        return call.start, False
    if call.fallback_time is not None:
        return call.fallback_time, True
    return None, False


def _duration_seconds(call):
    if call.start is None or call.end is None:
        return None
    micros = (call.end - call.start) // datetime.timedelta(microseconds=1)
    return max(0, (micros + 500_000) // 1_000_000)


def token_stats(calls) -> TokenStats:
    used = [c for c in calls if c.usable]
    return TokenStats(
        n=len(used),
        input_tokens=distribution([c.input_tokens for c in used]),
        output_tokens=distribution([c.output_tokens for c in used]),
        cache_creation_tokens=distribution([c.cache_creation_tokens for c in used]),
        cache_read_tokens=distribution([c.cache_read_tokens for c in used]),
        total=distribution([c.total_tokens for c in used]),
        requests=distribution([c.requests for c in used]),
    )


def repeat_flags(calls) -> frozenset:
    """call_id de las llamadas que repiten a la anterior de su sesion (INFERIDO).

    "Mismo agente" es la misma `agent_key` (nombre canonico), no la misma etiqueta visible. Una
    llamada sin meta (NO_META_KEY) no se marca nunca, aunque la anterior tambien sea sin meta; si
    participa en la cadena (rompe la de otros agentes). Solo entran las llamadas con `start` y
    `end`: una sin `start` no participa ni rompe la cadena, y si la anterior cayo fuera de la
    ventana (el llamador solo pasa las de la ventana) la primera de la ventana no se marca. Mira
    solo la anterior inmediata por (start, end, seq): A1 [0,100], A2 [10,20], A3 [30,40] marca
    A3 aunque corre en paralelo con A1. Con empate de (start, end) manda el ordinal de recorrido `seq`
    (determinista), no call_id, que lleva la clave aleatoria de la ejecucion. Ver REPEAT_LIMITATIONS."""
    by_session = collections.defaultdict(list)
    for c in calls:
        if c.start is not None and c.end is not None:
            by_session[c.session].append(c)
    flagged = set()
    for items in by_session.values():
        items.sort(key=lambda c: (c.start, c.end, c.seq))   # seq: desempate determinista, nunca call_id
        for prev, cur in zip(items, items[1:]):
            if (cur.agent_key != NO_META_KEY and prev.agent_key == cur.agent_key
                    and prev.end < cur.start):
                flagged.add(cur.call_id)
    return frozenset(flagged)


def _scope(calls, flagged, ranges) -> ScopeMetrics:
    """`ranges`: rango de version de cada llamada, calculado UNA vez por aggregate_calls (clave: id(c))."""
    live = [c for c in calls if not c.excluded]
    sessions = len({c.session for c in calls})
    durations = [d for d in (_duration_seconds(c) for c in live) if d is not None]
    models = collections.Counter(c.model for c in live)
    by_range = _by_key(calls, lambda c: ranges[id(c)])
    rows = []
    for name in VERSION_RANGES:
        in_range = by_range.get(name, [])
        rows.append(VersionRow(name, len(in_range), token_stats(in_range)))
    return ScopeMetrics(
        calls=len(calls),
        excluded=len(calls) - len(live),
        sessions=sessions,
        calls_per_session_tenths=(20 * len(calls) + sessions) // (2 * sessions) if sessions else None,
        tokens=token_stats(calls),
        duration=distribution(durations),
        tools=distribution([c.tools for c in live]),
        models=tuple(sorted(models.items(), key=lambda kv: (-kv[1], kv[0]))),
        repeats=sum(1 for c in calls if c.call_id in flagged),
        versions=tuple(rows),
    )


def _data_quality(total_read, inside, outside, fallback_used, no_time, no_time_excluded) -> DataQuality:
    def count(pred):
        return sum(1 for c in inside if pred(c))

    return DataQuality(
        calls_read=total_read,
        calls_in_window=len(inside),
        calls_outside_window=outside,
        without_start=count(lambda c: c.start is None),
        placed_by_fallback=fallback_used,
        without_any_time=no_time,
        without_any_time_excluded=no_time_excluded,
        excluded=count(lambda c: c.excluded),
        excluded_corrupt_line=count(lambda c: c.damage == "linea intermedia corrupta"),
        excluded_unreadable=count(lambda c: c.damage == "ilegible"),
        excluded_cap=count(lambda c: c.damage == "tope"),
        without_usage=count(lambda c: not c.excluded and not c.has_usage),
        all_ids_repeated=count(lambda c: not c.excluded and c.has_usage and c.requests == 0),
        without_meta=count(lambda c: c.agent_group == "sin-meta"),
        tokens_calls=count(lambda c: c.usable),
        without_version=count(lambda c: not c.versions),
        unrecognized_version=count(lambda c: c.versions and not _numeric_versions(c)),
        multiple_ranges=count(_spans_ranges),
        unverified_calls=count(lambda c: c.unverified),
        hardlinks=count(lambda c: c.hardlink),
        oversize_lines=sum(c.oversize_lines for c in inside),
        model_mismatch=count(lambda c: c.model_mismatch),
    )


def _by_key(calls, key):
    groups = collections.defaultdict(list)
    for c in calls:
        groups[key(c)].append(c)
    return groups


def skill_metrics(uses, window) -> SkillMetrics:
    """Conteos de uso de skills en la ventana (ver la cabecera de la seccion). Pura: solo cuenta."""
    uses = list(uses)
    inside = []
    without_time = 0
    for u in uses:
        if u.moment is None:
            without_time += 1
            if window.is_all:
                inside.append(u)
        elif window.contains(u.moment):
            inside.append(u)
    rows = []
    for (skill, group), items in _by_key(inside, lambda u: (u.skill, u.group)).items():
        rows.append(SkillRow(
            skill, group, len(items),
            sum(1 for u in items if u.origin == ORIGIN_MAIN),
            sum(1 for u in items if u.origin == ORIGIN_SUBAGENT),
            len({u.session for u in items})))
    rows.sort(key=lambda r: (-r.calls, r.skill, r.group))
    groups = []
    for group, items in _by_key(inside, lambda u: u.group).items():
        groups.append(SkillGroupRow(group, len({u.skill for u in items}), len(items),
                                    len({u.session for u in items})))
    groups.sort(key=lambda g: (-g.calls, g.group))
    linked = [u for u in inside if u.origin == ORIGIN_SUBAGENT]
    by_agent = []
    for (agent, agent_group, skill, group), items in _by_key(
            linked, lambda u: (u.agent, u.agent_group, u.skill, u.group)).items():
        by_agent.append(SkillAgentRow(agent, agent_group, skill, group, len(items)))
    by_agent.sort(key=lambda r: (-r.calls, r.agent, r.agent_group, r.skill, r.skill_group))
    return SkillMetrics(
        calls=len(inside),
        sessions=len({u.session for u in inside}),
        main_calls=sum(1 for u in inside if u.origin == ORIGIN_MAIN),
        subagent_calls=len(linked),
        rows=tuple(rows),
        groups=tuple(groups),
        by_agent=tuple(by_agent),
        quality=SkillQuality(
            uses_read=len(uses), in_window=len(inside), outside_window=len(uses) - len(inside),
            without_time=without_time, other_name=sum(1 for u in inside if u.skill == OTHER_SKILL)),
    )


def aggregate_calls(source, window=None, today=None, check_damage: bool = True,
                    skill_uses=None) -> UsageMetrics:
    """Metricas de uso. `source`: un ReadResult (idealmente de read_calls(check_damage=False)) o
    cualquier iterable de CallRecord. `skill_uses`: invocaciones de Skill (SkillUse); por defecto las del
    ReadResult (una lista de CallRecord no trae ninguna) y, si se pasan, mandan. Sin `window`, la de
    WINDOW_DAYS dias UTC que terminan en `today`, que el llamador inyecta (T7 usa utc_today()): sin `window` ni `today` lanza ValueError
    (MSG_TODAY_REQUIRED); aqui no se lee el reloj. Con check_damage, lanza SchemaError si mas del
    5 % de las llamadas DE LA VENTANA, mas las danadas sin ninguna hora (fuera de la ventana pero
    contadas por prudencia), esta danado. Pura: no hace E/S y el resultado no depende del orden de
    entrada."""
    if isinstance(source, ReadResult):
        calls = list(source.calls)
        warnings = tuple(source.warnings)
        read_quality = tuple((label, int(source.quality[label])) for label in READ_QUALITY_LABELS)
        if skill_uses is None:
            skill_uses = source.skill_uses
    else:
        calls = list(source)
        warnings = ()
        read_quality = ()
    if skill_uses is None:
        skill_uses = ()
    if window is None:
        if today is None:
            raise ValueError(MSG_TODAY_REQUIRED)
        window = make_window(today)
    inside, fallback_used, no_time, lost = [], 0, 0, []
    for c in calls:
        moment, approximate = _call_moment(c)
        if moment is None:
            no_time += 1
            if c.excluded:
                lost.append(c)
        if (moment is None and window.is_all) or (moment is not None and window.contains(moment)):
            inside.append(c)
            if approximate and not window.is_all:
                fallback_used += 1
    if check_damage:
        # con --all las danadas sin hora ya estan en `inside`: no se cuentan dos veces
        check_damaged(inside if window.is_all else inside + lost)
    flagged = repeat_flags(inside)
    ranges = {id(c): version_range(c) for c in inside}   # una vez por llamada (no por ambito y rango)
    agents = [AgentMetrics(agent, group, _scope(items, flagged, ranges))
              for (agent, group), items in _by_key(inside, lambda c: (c.agent, c.agent_group)).items()]
    agents.sort(key=lambda a: (-a.metrics.calls, a.agent, a.group))
    groups = []
    for group, items in _by_key(inside, lambda c: c.agent_group).items():
        groups.append(GroupMetrics(group, len({c.agent_key for c in items}), _scope(items, flagged, ranges)))
    groups.sort(key=lambda g: (-g.metrics.calls, g.group))
    projects = [ProjectMetrics(project, _scope(items, flagged, ranges))
                for project, items in _by_key(inside, lambda c: c.project).items()]
    projects.sort(key=lambda p: (-p.metrics.calls, p.project))
    seen = collections.Counter(v for c in inside for v in set(_numeric_versions(c)))
    seen_sorted = tuple(sorted(seen.items(), key=lambda kv: (version_key(kv[0]), kv[0])))
    return UsageMetrics(
        window=window,
        total=_scope(inside, flagged, ranges),
        agents=tuple(agents),
        groups=tuple(groups),
        projects=tuple(projects),
        versions_seen=seen_sorted,
        unverified_versions=tuple(v for v, _ in seen_sorted if is_unverified(v)),
        verified_max=VERIFIED_MAX,
        quality=_data_quality(len(calls), inside, len(calls) - len(inside), fallback_used, no_time,
                                 len(lost)),
        read_quality=read_quality,
        warnings=warnings,
        skills=skill_metrics(skill_uses, window),
    )


# --- Reporte de proyecto (T5) ---
#
# `render_project_report` es PURA: recibe el resultado agregado (`UsageMetrics`) mas dos datos inyectados (el
# alias del proyecto y, opcionalmente, la fecha de generacion) y devuelve el Markdown como `str`. No hace E/S,
# no lee el reloj (la fecha la inyecta el llamador, T7), no importa nada y no recibe llamadas crudas: solo ve
# numeros y etiquetas que el lector ya filtro por listas cerradas. T7 la codifica en UTF-8 sin BOM.
#
# Decisiones de formato:
#   - El texto en espanol lleva tildes y enes correctas (decision del propietario: titulos, rotulos de columna,
#     avisos, HOW_TO_READ, REPEAT_LIMITATIONS, SKILL_LIMITATIONS y WARN_*), siempre como escapes \u00xx dentro
#     de las constantes: el FUENTE sigue siendo ASCII, el REPORTE no (UTF-8 sin BOM, LF; T7 lo escribe asi).
#     Las barras (\u2588 y \u2591) salen igual. Lo que pasa por `_code` (nombres, versiones, etiquetas de
#     READ_QUALITY_LABELS y de rango) sigue en ASCII: `_code` cambia lo no ASCII por `?`. Esas etiquetas son
#     cerradas y sin tildes, por eso no necesitan salir de `_code`.
#   - Enteros SIN separador de miles (3.6 del plan): sin ambiguedad de configuracion regional y cualquier valor,
#     por enorme que sea, se imprime completo. Un decimal usa punto ("1.5"). `None` es "-" y el cero real es "0".
#   - Porcentajes: entero, redondeo al mas cercano con medio hacia arriba; un valor distinto de cero que
#     redondea a 0 se escribe "<1 %"; sin base, "-".
#   - Marca "*" (pocas muestras) en n, mediana y p90 cuando n < SMALL_N.
#   - Todo texto variable (agente, conjunto, modelo, skill, version) pasa por `_code`: ASCII imprimible, entre
#     comillas invertidas, con `|` escapado, sin saltos de linea y acotado a MAX_CELL_CHARS. Una tabla no puede
#     romperse. Las filas de cada tabla se acotan a MAX_TABLE_ROWS (las versiones, a MAX_VERSION_ROWS).
#   - Privacidad: de la entrada solo se muestran las etiquetas de las listas cerradas del lector, los avisos de
#     texto fijo conocidos (uno desconocido sale como "aviso no reconocido") y los contadores de
#     READ_QUALITY_LABELS. Nunca el alias de OTROS proyectos (`metrics.projects` no se imprime), ni `call_id`,
#     `session` o `agent_key` (no existen en `UsageMetrics`).
#   - El orden de las filas es el de las metricas (llamadas descendente y nombre): mismo input, mismos bytes.
#   - REGLA (T6 la hereda): TODA tabla por agente lleva la columna `Conjunto` junto a `Agente`. T3 agrupa por
#     (agente, conjunto) y `(otro agente)` sale en `otros` y en `plugin:(no-valido)`: sin la columna, dos filas
#     serian indistinguibles. No se usan etiquetas compuestas. "Agentes distintos" cuenta pares (nombre, conjunto).
#   - Marca `*` (pocas muestras): cada tabla que la contenga lleva debajo su leyenda (`_table`/`_capped_table`
#     la anaden solas), tambien si la tabla de tokens no la tiene y la de duracion si.
#   - Cabecera: un dato por linea con `> - ` (varias lineas `> ...` seguidas son UN parrafo en GFM).
#   - Contadores de la lectura (READ_QUALITY_LABELS) en listas cerradas: INCIDENCIA (READ_INCIDENT_LABELS) o
#     INFORMATIVO (READ_INFO_LABELS). Solo las incidencias entran en el resumen de la cabecera y en el detalle
#     de incidencias; las que ya tienen aviso propio (READ_WARNED) no se cuentan dos veces en la cabecera.
#   - Varios alias en `metrics.projects`: no es un error. T7 puede leer varias carpetas (`--transcripts-dir`; un
#     worktree vive en otra carpeta y tiene otro alias; `c--` y `C--` dan el mismo alias) y el generador solo
#     imprime el alias que recibe. `UsageMetrics` no expone cuantas carpetas se leyeron: el campo
#     "Carpetas de transcripciones leidas: N" de la cabecera queda para T7 (necesita ese dato en el resultado
#     de la lectura) y se anade entonces.
#
# DESVIOS respecto de 3.6 del plan (a registrar en el plan al cerrar T5):
#   - "Tokens por llamada" lleva `Conjunto`, `Tokens (suma)` y `Barra` ademas de las columnas del plan.
#   - "Duracion y herramientas" y "Modelo real" llevan `Conjunto` (regla de arriba).
#   - El reporte de proyecto lleva tambien la tabla "Por conjunto" (en el plan es solo del global).
#   - La tabla de skills tiene 7 columnas (Skill, Conjunto, Invocaciones, Barra, Sesiones, Sesion principal,
#     Subagente) mas las de conjunto y agente, en vez de `Skill | Invocaciones | Sesiones`.
#   - Seccion "Resumen" (no esta en el plan) tras la cabecera.
#   - Dos tablas de versiones: por rango (con la nota de 2.1.310 a 2.1.327, G1 2) y versiones vistas.

REPORT_SCHEMA = 1
REPORT_MARKER = "<!-- synclayer-usage-report v%d -->" % REPORT_SCHEMA
TOOL_NAME = "tools/usage_report.py"
BAR_WIDTH = 10
BAR_FULL = "\u2588"
BAR_EMPTY = "\u2591"
MAX_CELL_CHARS = 64
MAX_TABLE_ROWS = 40
MAX_VERSION_ROWS = 40
ALIAS_RE = re.compile(r"p-[0-9a-f]{8}\Z")
SMALL_MARK = " *"
MSG_REPORT_METRICS = "render_project_report necesita un UsageMetrics"
MSG_REPORT_ALIAS = "alias de proyecto invalido: debe ser p- y 8 hexadecimales en minuscula"
MSG_REPORT_DATE = "fecha de generacion invalida: debe ser datetime.date o None"
UNKNOWN_WARNING = "aviso no reconocido"
LABEL_MAIN_READ = "sesiones principales leidas"
# Conjuntos de agentes que el reporte conoce (los de classify_agent y `sin-meta`); un conjunto `plugin:<prefijo>`
# con el prefijo validado tambien se muestra. Cualquier otra etiqueta sale como OTHER_GROUP en las tablas de los
# dos reportes (defensa uniforme: el lector nunca la produce).
OTHER_GROUP = "(otro conjunto)"
NO_META_GROUP = "sin-meta"
AGENT_GROUPS = frozenset(("SyncLayer", "integrado", "otros", "plugin:(no-valido)", NO_META_GROUP))
# Conjuntos cuyo numero de agentes (o de skills) distintos el global no muestra: reunen nombres de usuario.
HIDDEN_COUNT_GROUPS = frozenset(("otros", "plugin:(no-valido)", OTHER_GROUP))

# "Como leer estos numeros" (texto fijo). Las limitaciones de repeticiones y de skills salen de
# REPEAT_LIMITATIONS y SKILL_LIMITATIONS (T3, T4) y se vuelcan tal cual debajo.
HOW_TO_READ = (
    "No mide la calidad del resultado de un agente ni el costo en dinero: una llamada con menos tokens no"
    " dice nada sobre su resultado.",
    "No muestra costos. Los tokens no son una factura (la cach\u00e9 le\u00edda se cobra distinto) y cualquier costo"
    " ser\u00eda una estimaci\u00f3n a precio de lista; aqu\u00ed no se calcula.",
    "Una llamada es un archivo de subagente (`agent-<id>.jsonl`). Los tokens por llamada suman entrada,"
    " salida, cach\u00e9 escrita y cach\u00e9 le\u00edda; una respuesta repartida en varias l\u00edneas se cuenta una vez (se"
    " deduplica por `message.id`).",
    "La duraci\u00f3n es aproximada: \u00faltima marca de tiempo menos la primera. Incluye esperas de herramientas y"
    " de permisos.",
    "Con n < 10 llamadas (marca `*`, pocas muestras) la mediana y el p90 dicen poco.",
    "Mediana: con n par, media de los dos centrales redondeada al entero (medio hacia arriba). p90: el valor"
    " en la posici\u00f3n ceil(0,9 n) de la lista ordenada. Los porcentajes se redondean al entero m\u00e1s cercano"
    " (medio hacia arriba); `<1 %` es un valor distinto de cero que redondea a 0.",
    "Las repeticiones son una inferencia, no un reintento confirmado (ver abajo).",
    "Las versiones 2.1.310 a 2.1.327 de Claude Code pueden inflar los tokens por reintentos y no se corrige"
    " num\u00e9ricamente. Comparar entre rangos de versi\u00f3n es solo indicativo.",
    "Los n\u00fameros dependen de un formato interno de Claude Code que no est\u00e1 garantizado y puede cambiar sin"
    " aviso.",
    "Solo se leen las carpetas de transcripciones elegidas para este proyecto: las sesiones abiertas desde"
    " una subcarpeta o un worktree viven en otra carpeta y no se incluyen salvo que se indique.",
)
PRIVACY_NOTES = (
    "Este archivo no contiene contenido de conversaciones ni rutas, pero revela volumen de uso. Es local: no"
    " lo subas a git ni lo compartas sin revisarlo.",
    "El alias `p-<8 hex>` es un hash sin sal del nombre de la carpeta del proyecto: quien conozca o adivine el"
    " nombre de la carpeta puede recalcularlo. No es anonimato.",
    "Los nombres de skills de usuario salen tal cual: pueden revelar nombres privados. El prefijo de una skill de"
    " plugin (`plugin:<prefijo>`) sale de texto que escribe el modelo: puede ser cualquier cadena `[a-z0-9-]{1,32}`,"
    " no solo un nombre de plugin.",
    "Los nombres de modelo salen de las transcripciones con un patr\u00f3n amplio (`claude-` y tramos de palabra de"
    " hasta 12 caracteres): un id de modelo personalizado puede salir tal cual.",
    "Un agente de proyecto con el mismo nombre que uno de SyncLayer cuenta como SyncLayer.",
)
KNOWN_WARNINGS = frozenset((
    WARN_NO_MESSAGE_ID, WARN_ID_REPEATED, WARN_ID_CAP, WARN_SKILL_ID_REPEATED, WARN_SKILL_ID_CAP,
    WARN_MAIN_HARDLINK, WARN_MAIN_CAP, WARN_MAIN_UNREADABLE, WARN_ALIAS_COLLISION,
))
NOTE_DOUBTFUL_RANGE = "dudoso: tokens posiblemente inflados por reintentos (corregido en 2.1.328)"
NOTE_NO_RANGE = "sin versi\u00f3n en las l\u00edneas o versi\u00f3n no reconocible"
LEGEND_SMALL = "`*`: n < %d, pocas muestras. La mediana y el p90 dicen poco." % SMALL_N

# Contadores de la lectura completa, en dos listas CERRADAS (cada etiqueta de READ_QUALITY_LABELS esta en una
# sola). INFORMATIVOS: dicen que se leyo o se saco a proposito, no que algo fallo. El resto son INCIDENCIAS.
READ_INFO_LABELS = (
    "hardlinks duplicados dentro de projects",
    "lineas synthetic excluidas",
    "sesiones principales leidas",
)
READ_INCIDENT_LABELS = tuple(label for label in READ_QUALITY_LABELS if label not in READ_INFO_LABELS)
# Incidencias con aviso propio en la cabecera (ReadResult.warnings): no se cuentan otra vez en el resumen.
READ_WARNED = {
    "usage sin message.id": WARN_NO_MESSAGE_ID,
    "message.id repetido entre archivos": WARN_ID_REPEATED,
    "message.id sin deduplicar entre archivos (tope)": WARN_ID_CAP,
    "skills: id repetido entre archivos": WARN_SKILL_ID_REPEATED,
    "skills: ids sin deduplicar (tope)": WARN_SKILL_ID_CAP,
    "sesiones principales omitidas por enlace duro": WARN_MAIN_HARDLINK,
    "sesiones principales omitidas por tope de tamano": WARN_MAIN_CAP,
    "sesiones principales ilegibles": WARN_MAIN_UNREADABLE,
    "alias de proyecto repetido entre carpetas": WARN_ALIAS_COLLISION,
}

def _bar(value, maximum) -> str:
    """Barra de BAR_WIDTH caracteres proporcional al maximo de la columna. Redondeo al mas cercano (medio
    hacia arriba) con enteros; un valor distinto de cero lleva al menos un bloque; maximo <= 0: vacia."""
    if value is None or maximum is None or maximum <= 0 or value <= 0:
        return BAR_EMPTY * BAR_WIDTH
    filled = (2 * BAR_WIDTH * value + maximum) // (2 * maximum)
    filled = min(BAR_WIDTH, max(1, filled))
    return BAR_FULL * filled + BAR_EMPTY * (BAR_WIDTH - filled)


def _num(value) -> str:
    return "-" if value is None else "%d" % value


def _tenths(value) -> str:
    if value is None:
        return "-"
    whole, tenth = divmod(value, 10)
    return "%d.%d" % (whole, tenth)


def _percent(part, whole) -> str:
    if whole <= 0:
        return "-"
    if part <= 0:
        return "0 %"
    rounded = (200 * part + whole) // (2 * whole)
    return "<1 %" if rounded == 0 else "%d %%" % rounded


def _plural(count, one, many) -> str:
    return "%d %s" % (count, one if count == 1 else many)


def _code(text) -> str:
    """Texto variable seguro para una celda o una linea: ASCII imprimible entre comillas invertidas, `|`
    escapado, sin saltos de linea ni comillas invertidas propias, y acotado a MAX_CELL_CHARS."""
    if not isinstance(text, str):
        return "`(no cadena)`"
    if text == "":
        return "`(vacio)`"
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS - 3] + "..."
    clean = "".join(ch if " " <= ch <= "~" else "?" for ch in text)
    clean = clean.replace("\\", "/").replace("`", "'").replace("|", "\\|")
    return "`" + clean + "`"


def _small(value, small) -> str:
    """Un entero (o None) con la marca de pocas muestras cuando `small` y hay valor."""
    return _num(value) + (SMALL_MARK if small and value is not None else "")


def _raw_table(headers, aligns, rows) -> list:
    """Tabla Markdown sin leyenda. Todas las filas tienen las columnas de la cabecera (ValueError si no)."""
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---:" if a == "r" else "---" for a in aligns) + "|"]
    for row in rows:
        if len(row) != len(headers):
            raise ValueError("fila con columnas de mas o de menos")
        out.append("| " + " | ".join(row) + " |")
    return out


def _legend(table_lines) -> list:
    """La leyenda de `*` (con una linea en blanco antes) si alguna fila de la tabla lleva la marca; si no, nada.
    Una celda de texto variable termina en comilla invertida (`_code`), nunca en " * |"."""
    if any((SMALL_MARK + " |") in line for line in table_lines[2:]):
        return ["", LEGEND_SMALL]
    return []


def _table(headers, aligns, rows) -> list:
    """Tabla Markdown con su leyenda de `*` si lleva la marca."""
    out = _raw_table(headers, aligns, rows)
    return out + _legend(out)


def _capped_table(headers, aligns, rows) -> list:
    """Como _table, acotada a MAX_TABLE_ROWS filas, con una nota si se omiten (antes de la leyenda)."""
    out = _raw_table(headers, aligns, rows[:MAX_TABLE_ROWS])
    legend = _legend(out)
    if len(rows) > MAX_TABLE_ROWS:
        out += ["", "Se muestran las %d primeras filas de %d." % (MAX_TABLE_ROWS, len(rows))]
    return out + legend


def _bullets(lines) -> list:
    return ["- " + line for line in lines]


def _range_calls(metrics, name) -> int:
    for row in metrics.total.versions:
        if row.range == name:
            return row.calls
    return 0


def _window_text(window) -> str:
    if window.is_all:
        return "todo el historial (sin ventana)"
    return "%s a %s (UTC, ambos inclusive)" % (window.since.isoformat(), window.until.isoformat())


def _versions_header(seen) -> str:
    # las versiones de las metricas son texto de entrada para este generador: siempre por `_code`
    if not seen:
        return "sin versiones reconocibles"
    if len(seen) == 1:
        return "versi\u00f3n %s" % _code(seen[0][0])
    return "versiones %s a %s (%d versiones)" % (_code(seen[0][0]), _code(seen[-1][0]), len(seen))


def _recent_codes(labels) -> str:
    """Hasta MAX_SHOWN_VERSIONS versiones, las mas recientes primero y cada una por `_code`, y cuantas quedan
    fuera. Como `_recent_first` del lector, pero sin confiar en que las etiquetas ya vengan filtradas."""
    ordered = sorted(labels, key=lambda v: (version_key(v), v), reverse=True)
    text = ", ".join(_code(v) for v in ordered[:MAX_SHOWN_VERSIONS])
    if len(ordered) > MAX_SHOWN_VERSIONS:
        text += " (+%d m\u00e1s)" % (len(ordered) - MAX_SHOWN_VERSIONS)
    return text


def _read_incidents(metrics) -> list:
    """Incidencias de la lectura completa: contadores distintos de cero de READ_INCIDENT_LABELS (las
    informativas y las etiquetas fuera de la lista cerrada no cuentan)."""
    return [(label, n) for label, n in metrics.read_quality if label in READ_INCIDENT_LABELS and n > 0]


def _read_info(metrics) -> list:
    """Contadores informativos distintos de cero. `sesiones principales leidas` va en la tabla base."""
    return [(label, n) for label, n in metrics.read_quality
            if label in READ_INFO_LABELS and label != LABEL_MAIN_READ and n > 0]


def _unwarned_incidents(metrics) -> list:
    """Las incidencias que la cabecera no avisa ya por su cuenta: sin aviso propio, o con aviso que las
    metricas no traen. Evita decir dos veces lo mismo (el aviso y el resumen)."""
    return [(label, n) for label, n in _read_incidents(metrics)
            if label not in READ_WARNED or READ_WARNED[label] not in metrics.warnings]


def _read_count(metrics, label) -> int:
    return sum(n for name, n in metrics.read_quality if name == label)


def _notices(metrics) -> list:
    """Avisos de la cabecera: solo los que valen mas de cero."""
    q = metrics.quality
    out = []
    doubtful = _range_calls(metrics, RANGE_DOUBTFUL)
    if doubtful:
        out.append("%s con versiones de Claude Code de 2.1.310 a 2.1.327: tokens posiblemente inflados por"
                   " reintentos (corregido en 2.1.328)." % _plural(doubtful, "llamada", "llamadas"))
    if metrics.unverified_versions:
        out.append("hay versiones de Claude Code posteriores a la \u00faltima verificada (%s): %s. El formato"
                   " interno puede haber cambiado."
                   % (_code(metrics.verified_max), _recent_codes(metrics.unverified_versions)))
    for text in metrics.warnings:
        out.append(text if text in KNOWN_WARNINGS else UNKNOWN_WARNING)
    if q.excluded == 1:
        out.append("1 llamada da\u00f1ada queda fuera de los tokens, la duraci\u00f3n y las herramientas.")
    elif q.excluded:
        out.append("%d llamadas da\u00f1adas quedan fuera de los tokens, la duraci\u00f3n y las herramientas."
                   % q.excluded)
    if q.without_start:
        text = _plural(q.without_start, "llamada sin hora de inicio", "llamadas sin hora de inicio")
        if q.placed_by_fallback:
            text += "; %s por la fecha de modificaci\u00f3n del archivo (aproximada)" % _plural(
                q.placed_by_fallback, "ubicada", "ubicadas")
        out.append(text + ".")
    if q.hardlinks == 1:
        out.append("1 llamada le\u00edda de un enlace duro aceptado.")
    elif q.hardlinks:
        out.append("%d llamadas le\u00eddas de enlaces duros aceptados." % q.hardlinks)
    incidents = _unwarned_incidents(metrics)
    if incidents:
        out.append("la lectura tuvo incidencias en %s (detalle en Calidad de los datos)."
                   % _plural(len(incidents), "contador", "contadores"))
    return out


def _header_section(metrics, alias, generated) -> list:
    t = metrics.total
    # un dato por linea con `> - `: varias lineas `> ...` seguidas serian un solo parrafo en GFM
    lines = [
        REPORT_MARKER,
        "# Reporte de uso de subagentes: proyecto " + alias,
        "",
        "> - Ventana: " + _window_text(metrics.window),
        "> - Llamadas: %d en %s" % (t.calls, _plural(t.sessions, "sesi\u00f3n", "sesiones")),
        "> - Claude Code: " + _versions_header(metrics.versions_seen),
        "> - Esquema del reporte: %d" % REPORT_SCHEMA,
    ]
    if generated is not None:
        lines.append("> - Generado: " + generated.isoformat())
    lines.append("> - Reporte local: no lo subas a git.")
    for text in _notices(metrics):
        lines.append("> - AVISO: " + text)
    return lines + [""]


def _summary_section(metrics, extra=()) -> list:
    """`extra`: lineas fijas que el reporte global anade tras la primera (proyectos y conjuntos)."""
    t = metrics.total
    lines = ["## Resumen", ""]
    items = ["Llamadas: %d en %s (%s llamadas por sesi\u00f3n)" % (
        t.calls, _plural(t.sessions, "sesi\u00f3n", "sesiones"), _tenths(t.calls_per_session_tenths))]
    items.extend(extra)
    if not t.calls:
        lines += _bullets(items)
        return lines + ["", "Sin llamadas a subagentes en la ventana.", ""]
    # pares (nombre, conjunto), que es como T3 agrupa: el numero coincide con las filas de las tablas
    items.append("Agentes distintos (por nombre y conjunto): %d" % len(metrics.agents))
    items.append("Tokens (suma de las llamadas con estad\u00edsticas): %s en %s" % (
        _num(t.tokens.total.total), _plural(t.tokens.n, "llamada", "llamadas")))
    items.append("Repeticiones consecutivas (inferido): %d" % t.repeats)
    doubtful = _range_calls(metrics, RANGE_DOUBTFUL)
    items.append("Llamadas en el rango de versi\u00f3n dudoso (2.1.310 a 2.1.327): %d de %d (%s)" % (
        doubtful, t.calls, _percent(doubtful, t.calls)))
    if t.excluded:
        items.append("Llamadas da\u00f1adas, fuera de tokens, duraci\u00f3n y herramientas: %d de %d (%s)" % (
            t.excluded, t.calls, _percent(t.excluded, t.calls)))
    items.append("Skills: %s en %s" % (_plural(metrics.skills.calls, "invocaci\u00f3n", "invocaciones"),
                                       _plural(metrics.skills.sessions, "sesi\u00f3n", "sesiones")))
    return lines + _bullets(items) + [""]


def _group_label(group) -> str:
    """Conjunto de agente a mostrar: lista cerrada, `plugin:<prefijo>` con el prefijo validado u OTHER_GROUP."""
    if isinstance(group, str):
        if group in AGENT_GROUPS:
            return group
        if group.startswith("plugin:") and PLUGIN_PREFIX_RE.match(group[7:]) is not None:
            return group
    return OTHER_GROUP


def _model_rows(models, label_of) -> list:
    """Filas (modelo, llamadas) de una tabla. Con `label_of` (el global) los modelos que comparten etiqueta suman sus
    llamadas y el orden es el de las metricas (llamadas descendente y etiqueta); sin ella, las de las metricas."""
    if label_of is None:
        return list(models)
    merged = {}
    for model, count in models:
        label = label_of(model)
        merged[label] = merged.get(label, 0) + count
    return sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))


def _agent_sections(metrics, model_label=None) -> list:
    """`model_label`: None (el reporte de proyecto muestra el modelo que el lector ya filtro) o la funcion que el
    global usa para limitarlo a una lista cerrada (`_global_model_label`)."""
    agents = metrics.agents
    max_calls = max([a.metrics.calls for a in agents] or [0])
    max_tokens = max([a.metrics.tokens.total.total for a in agents] or [0])
    calls_rows, token_rows, time_rows, model_rows = [], [], [], []
    for a in agents:
        m = a.metrics
        # el par (Agente, Conjunto) va en TODAS las tablas por agente (ver la regla de la cabecera de la seccion)
        name, group = _code(a.agent), _code(_group_label(a.group))
        calls_rows.append([name, group, _num(m.calls), _bar(m.calls, max_calls), _num(m.sessions),
                           _tenths(m.calls_per_session_tenths), _num(m.repeats)])
        tk = m.tokens
        token_rows.append([
            name, group, _small(tk.n, tk.total.small), _num(tk.total.total), _bar(tk.total.total, max_tokens),
            _small(tk.total.median, tk.total.small), _small(tk.total.p90, tk.total.small),
            _num(tk.input_tokens.median), _num(tk.output_tokens.median),
            _num(tk.cache_creation_tokens.median), _num(tk.cache_read_tokens.median),
            _num(tk.requests.median)])
        time_rows.append([
            name, group, _small(m.duration.median, m.duration.small),
            _small(m.duration.p90, m.duration.small),
            _small(m.tools.median, m.tools.small), _small(m.tools.p90, m.tools.small)])
        for model, count in _model_rows(m.models, model_label):
            model_rows.append([name, group, _code(model), _num(count)])
    out = ["## Llamadas por agente", ""]
    out += _capped_table(["Agente", "Conjunto", "Llamadas", "Barra", "Sesiones", "Llamadas/sesi\u00f3n",
                          "Repeticiones (inferido)"], "llrlrrr", calls_rows)
    out += ["", "## Tokens por llamada", ""]
    out += _capped_table(
        ["Agente", "Conjunto", "n", "Tokens (suma)", "Barra", "Mediana", "p90", "Entrada (med.)",
         "Salida (med.)", "Cach\u00e9 escrita (med.)", "Cach\u00e9 le\u00edda (med.)", "Peticiones (med.)"],
        "llrrlrrrrrrr", token_rows)
    out += ["", "## Duraci\u00f3n y herramientas", ""]
    out += _capped_table(["Agente", "Conjunto", "Duraci\u00f3n aprox. s (med.)", "p90", "Herramientas (med.)",
                          "p90"], "llrrrr", time_rows)
    out += ["", "## Modelo real", ""]
    out += _capped_table(["Agente", "Conjunto", "Modelo", "Llamadas"], "lllr", model_rows)
    return out + [""]


def _group_table(metrics, hide_counts=False) -> list:
    """`hide_counts`: el global no muestra la columna `Agentes` de los conjuntos de HIDDEN_COUNT_GROUPS (el
    numero revelaria cuantos agentes de usuario distintos hay)."""
    groups = metrics.groups
    max_calls = max([g.metrics.calls for g in groups] or [0])
    rows = []
    for g in groups:
        m = g.metrics
        label = _group_label(g.group)
        agents = None if hide_counts and label in HIDDEN_COUNT_GROUPS else g.agents
        rows.append([_code(label), _num(agents), _num(m.calls), _bar(m.calls, max_calls),
                     _small(m.tokens.total.median, m.tokens.total.small),
                     _small(m.tokens.total.p90, m.tokens.total.small),
                     _small(m.duration.median, m.duration.small), _small(m.tools.median, m.tools.small)])
    return _capped_table(["Conjunto", "Agentes", "Llamadas", "Barra", "Tokens/llamada (med.)", "p90",
                          "Duraci\u00f3n aprox. s (med.)", "Herramientas (med.)"], "lrrlrrrr", rows)


def _group_section(metrics) -> list:
    return ["## Por conjunto", ""] + _group_table(metrics) + [""]


def _skills_section(metrics) -> list:
    sk = metrics.skills
    out = ["## Skills", ""]
    if sk.calls == 0:
        out.append("Sin invocaciones de skills en la ventana.")
    else:
        out.append("Invocaciones: %d en %s (%d en la sesi\u00f3n principal, %d en subagentes)." % (
            sk.calls, _plural(sk.sessions, "sesi\u00f3n", "sesiones"), sk.main_calls, sk.subagent_calls))
        rows = [r for r in sk.rows if r.calls > 0]
        max_calls = max([r.calls for r in rows] or [0])
        out += ["", "Por skill:", ""]
        out += _capped_table(
            ["Skill", "Conjunto", "Invocaciones", "Barra", "Sesiones", "Sesi\u00f3n principal", "Subagente"],
            "llrlrrr",
            [[_code(r.skill), _code(r.group), _num(r.calls), _bar(r.calls, max_calls), _num(r.sessions),
              _num(r.main_calls), _num(r.subagent_calls)] for r in rows])
        groups = [g for g in sk.groups if g.calls > 0]
        out += ["", "Por conjunto de skill:", ""]
        out += _capped_table(
            ["Conjunto", "Skills", "Invocaciones", "Sesiones"], "lrrr",
            [[_code(g.group), _num(g.skills), _num(g.calls), _num(g.sessions)] for g in groups])
        linked = [r for r in sk.by_agent if r.calls > 0]
        if linked:
            out += ["", "Por agente (skills invocadas dentro de subagentes):", ""]
            out += _capped_table(
                ["Agente", "Conjunto del agente", "Skill", "Invocaciones"], "lllr",
                [[_code(r.agent), _code(r.agent_group), _code(r.skill), _num(r.calls)] for r in linked])
    out += ["", "No se atribuyen tokens a una skill: corre en el contexto de la sesi\u00f3n que la invoca.", ""]
    return out


def _version_section(metrics) -> list:
    rows = []
    for row in metrics.total.versions:
        if row.range == RANGE_NONE and row.calls == 0:
            continue
        note = NOTE_DOUBTFUL_RANGE if row.inflated else (NOTE_NO_RANGE if row.range == RANGE_NONE else "")
        tk = row.tokens
        rows.append([_code(row.range), _num(row.calls), _small(tk.total.median, tk.total.small),
                     _small(tk.total.p90, tk.total.small), note])
    out = ["## Versiones de Claude Code", "", "Por rango de versi\u00f3n:", ""]
    out += _table(["Rango", "Llamadas", "Tokens/llamada (med.)", "p90", "Nota"], "lrrrl", rows)
    out += ["", "Comparar entre rangos es solo indicativo.", ""]
    seen = list(metrics.versions_seen)
    omitted = max(0, len(seen) - MAX_VERSION_ROWS)
    version_rows = []
    for version, count in seen[omitted:]:
        if _range_of(version_key(version)) == RANGE_DOUBTFUL:
            note = "dudosa: posible conteo doble (2.1.310 a 2.1.327)"
        elif is_unverified(version):
            note = "no verificada (mayor que %s)" % _code(metrics.verified_max)
        else:
            note = ""
        version_rows.append([_code(version), _num(count), note])
    if version_rows:
        out += ["Versiones vistas:", ""]
        out += _table(["Versi\u00f3n", "Llamadas", "Nota"], "lrl", version_rows)
        if omitted:
            out += ["", "Solo se muestran las %d versiones m\u00e1s recientes; %s." % (
                MAX_VERSION_ROWS, "se omite la versi\u00f3n m\u00e1s antigua" if omitted == 1
                else "se omiten las %d versiones m\u00e1s antiguas" % omitted)]
        out.append("")
    return out


def _quality_section(metrics) -> list:
    q = metrics.quality
    rows = [["Llamadas le\u00eddas (todas las ventanas)", _num(q.calls_read)],
            ["Llamadas en la ventana", _num(q.calls_in_window)],
            ["Llamadas fuera de la ventana", _num(q.calls_outside_window)],
            ["Llamadas con estad\u00edsticas de tokens", _num(q.tokens_calls)]]
    # solo si son distintos de cero (los cuatro de arriba van siempre)
    problems = (
        ("Llamadas da\u00f1adas (fuera de tokens, duraci\u00f3n y herramientas)", q.excluded),
        ("Llamadas da\u00f1adas por l\u00ednea intermedia corrupta", q.excluded_corrupt_line),
        ("Llamadas da\u00f1adas por archivo ilegible", q.excluded_unreadable),
        ("Llamadas da\u00f1adas por tope de tama\u00f1o", q.excluded_cap),
        ("Llamadas sin hora de inicio", q.without_start),
        ("Llamadas ubicadas por la fecha de modificaci\u00f3n del archivo (aproximada)", q.placed_by_fallback),
        ("Llamadas sin ninguna hora (le\u00eddas en total)", q.without_any_time),
        ("Llamadas sin usage", q.without_usage),
        ("Llamadas con todos sus `message.id` ya contados en otro archivo", q.all_ids_repeated),
        ("Llamadas sin meta (agente `(sin-meta)`)", q.without_meta),
        ("Llamadas sin versi\u00f3n", q.without_version),
        ("Llamadas con versi\u00f3n no reconocible", q.unrecognized_version),
        ("Llamadas con versiones en varios rangos", q.multiple_ranges),
        ("Llamadas con una versi\u00f3n posterior a la verificada", q.unverified_calls),
        ("Enlaces duros aceptados (hardlinks)", q.hardlinks),
        ("L\u00edneas sobredimensionadas descartadas", q.oversize_lines),
        ("Llamadas con modelo distinto del que declara el meta", q.model_mismatch),
    )
    for label, value in problems:
        if value:
            rows.append([label, _num(value)])
    main_read = _read_count(metrics, LABEL_MAIN_READ)
    if main_read:
        rows.append(["Sesiones principales le\u00eddas (solo para contar skills)", _num(main_read)])
    sq = metrics.skills.quality
    if sq.uses_read:
        rows.append(["Skills: invocaciones le\u00eddas", _num(sq.uses_read)])
        if sq.outside_window:
            rows.append(["Skills: invocaciones fuera de la ventana", _num(sq.outside_window)])
        if sq.without_time:
            rows.append(["Skills: invocaciones sin hora (solo cuentan con todo el historial)",
                         _num(sq.without_time)])
        if sq.other_name:
            rows.append(["Skills: invocaciones con nombre no v\u00e1lido (se muestran como `(otra skill)`)",
                         _num(sq.other_name)])
    out = ["## Calidad de los datos", ""] + _table(["Concepto", "Cantidad"], "lr", rows)
    incidents = _read_incidents(metrics)
    if incidents:
        out += ["", "Lectura completa (no solo la ventana), contadores de incidencias distintos de cero:", ""]
        out += _table(["Contador", "Cantidad"], "lr", [[_code(label), _num(n)] for label, n in incidents])
    info = _read_info(metrics)
    if info:
        out += ["", "Lectura completa, contadores informativos (no son incidencias) distintos de cero:", ""]
        out += _table(["Contador", "Cantidad"], "lr", [[_code(label), _num(n)] for label, n in info])
    return out + [""]


def _guide_section(how_to_read) -> list:
    """`how_to_read`: HOW_TO_READ (proyecto) o HOW_TO_READ_GLOBAL; las limitaciones de repeticiones y de
    skills son las mismas."""
    out = ["## C\u00f3mo leer estos n\u00fameros", ""] + _bullets(how_to_read)
    out += ["", "### Repeticiones (inferido)", ""] + _bullets(REPEAT_LIMITATIONS)
    out += ["", "### Skills", ""] + _bullets(SKILL_LIMITATIONS)
    return out + [""]


def _footer_section(metrics, alias) -> list:
    out = ["## Pie", ""] + _bullets([
        "report_schema: %d" % REPORT_SCHEMA,
        "herramienta: " + TOOL_NAME,
        "ultima_version_verificada: " + _code(metrics.verified_max),
        "proyecto: " + alias,
    ])
    return out + [""] + _bullets(PRIVACY_NOTES)


def render_project_report(metrics, project_alias, generated=None) -> str:
    """Markdown del reporte local de UN proyecto (ver la cabecera de la seccion). Pura.

    `metrics`: UsageMetrics de las llamadas de ESE proyecto (el llamador filtra; este generador imprime
    solo `project_alias`, nunca `metrics.projects`). `project_alias`: `p-<8 hex>` (ValueError si no
    encaja: una ruta o un nombre real no puede colarse). `generated`: datetime.date inyectada o None; el
    generador no lee el reloj. ValueError con mensaje fijo (sin eco del valor) ante argumentos invalidos.
    Devuelve texto con LF y salto final; T7 lo escribe en UTF-8 sin BOM."""
    if not isinstance(metrics, UsageMetrics):
        raise ValueError(MSG_REPORT_METRICS)
    if not isinstance(project_alias, str) or not ALIAS_RE.match(project_alias):
        raise ValueError(MSG_REPORT_ALIAS)
    if generated is not None and not _is_date(generated):
        raise ValueError(MSG_REPORT_DATE)
    lines = _header_section(metrics, project_alias, generated)
    lines += _summary_section(metrics)
    if metrics.total.calls:
        lines += _agent_sections(metrics)
        lines += _group_section(metrics)
    lines += _skills_section(metrics)
    if metrics.total.calls:
        lines += _version_section(metrics)
    lines += _quality_section(metrics)
    lines += _guide_section(HOW_TO_READ)
    lines += _footer_section(metrics, project_alias)
    return "\n".join(lines) + "\n"


# --- Reporte global (T6) ---
#
# `render_global_report` es PURA, como la de proyecto: recibe el `UsageMetrics` de TODOS los proyectos leidos (el
# llamador agrega sin filtrar por proyecto) y, opcionalmente, la fecha de generacion; devuelve el Markdown. No
# recibe llamadas crudas, no lee el reloj, no hace E/S y no calcula alias. T7 lo escribe en
# `<claude-dir>/synclayer-usage.md`.
#
# Decisiones:
#   - Firma: `render_global_report(metrics, generated=None)`. No lleva alias ni lista de proyectos aparte: el
#     agregado ya trae un `ProjectMetrics` por proyecto. Menos argumentos, menos formas de colar un nombre real.
#   - Reutiliza los generadores de T5 (cabecera de avisos, resumen, tablas por agente con la columna `Conjunto`,
#     versiones, calidad, guia, barras, `_code`, leyenda de `*`). Lo propio del global: cabecera sin alias de
#     proyecto, "Por conjunto" ampliado (mismas columnas comparables para todos los conjuntos, tasa de repeticiones
#     por cada 100 llamadas y desglose por rango de version), "Por proyecto", skills con nombres protegidos, "Que
#     compara y que no", guia y pie propios.
#   - Privacidad del global: es PRIVADO por defecto y se puede compartir solo tras revisarlo (la cabecera y el pie
#     lo dicen). Solo numeros y etiquetas de listas cerradas. Nunca contenido, rutas, nombres de carpeta,
#     `call_id`, `session` ni `agent_key`.
#   - Proyectos (D1 del propietario): el global NO imprime el alias `p-<8 hex>` en ninguna parte. Numera los
#     proyectos `proyecto 1..N` por volumen de llamadas descendente; el desempate usa los valores visibles de la fila
#     (sesiones y luego tokens), nunca el alias ni un identificador con clave. Si dos proyectos empatan en todo lo
#     visible, sus filas son identicas: el orden entre ellos no se nota y los bytes no dependen del alias. Un alias
#     es un hash de 32 bits sin sal del nombre de la carpeta: imprimirlo permitiria recalcularlo a quien adivine el
#     nombre; con ordinales no hay nada que recalcular. `ProjectMetrics.project` sigue existiendo para el reporte
#     de proyecto, que muestra su propio alias. La numeracion puede cambiar entre ejecuciones y no se puede cruzar
#     con el alias del reporte de proyecto (el pie lo dice).
#   - Alias repetido (colision de 32 bits): el lector cuenta las carpetas distintas con el mismo alias (`alias de
#     proyecto repetido entre carpetas`, con aviso WARN_ALIAS_COLLISION) y el agregado las agrupa en UN
#     `ProjectMetrics`: con ordinales siguen siendo un solo proyecto. Se descarto quitar la agrupacion en el global:
#     `CallRecord.project` ya es el alias (el nombre de la carpeta no llega al agregado) y separarlas exigiria
#     conservar ese nombre. El limite se documenta en la calidad del global (GLOBAL_ALIAS_LIMIT) y en el pie.
#   - Skills en el global: los nombres de skills de USUARIO no salen (a diferencia del reporte de proyecto): una
#     skill de usuario puede llamarse como un proyecto privado. Solo se muestran los nombres de las listas cerradas
#     (SYNCLAYER_SKILLS, BUILTIN_SKILLS, hoy vacias) y el prefijo de plugin que TAMBIEN aparecio como prefijo de
#     un agente en la misma lectura (D2: el prefijo de un agente lo escribe Claude Code; el de una skill sale de texto
#     que escribe el modelo y puede ser cualquier cadena `[a-z0-9-]{1,32}`). Los demas prefijos de plugin se agrupan
#     como `plugin:(otro)`, y lo demas como `(otra skill)`, UNA fila por conjunto mostrado, con las sesiones del
#     conjunto (exactas) o "-" si no se pueden contar. Limite: "visto como agente" mira solo los agentes con llamadas
#     (o con skills invocadas) en la VENTANA, que es lo que expone `UsageMetrics`.
#   - Cuentas que revelan nombres de usuario: la columna `Agentes` de "Por conjunto" y la columna `Skills` de "Por
#     conjunto de skill" salen como "-" en los conjuntos que reunen nombres de usuario (HIDDEN_COUNT_GROUPS, y los
#     conjuntos de skills con algun nombre agrupado).
#   - Modelos: el patron del lector (MODEL_RE) admite tramos de palabra de hasta 12 caracteres. El global solo muestra
#     ids hechos de tramos de lista cerrada (familias, numeros, fecha, `latest`; GLOBAL_MODEL_RE) o un alias; el resto
#     sale como `(otro modelo)` y las filas que comparten etiqueta suman. El reporte de proyecto mantiene el patron
#     amplio y lo advierte en su pie.
#   - Conjuntos: `sin-meta` (llamadas sin archivo meta) NO es un conjunto de agentes: tiene su fila (las llamadas son
#     reales) pero no cuenta en "Conjuntos con llamadas", ni en la comparacion ni en la razon de volumenes.
#   - Comparacion: con un solo conjunto de agentes con llamadas dice que no hay con que comparar; con volumenes que
#     difieren VOLUME_RATIO veces o mas lo avisa. La seccion fija "Que compara y que no" va siempre.
#   - Filas: cada tabla se acota a MAX_TABLE_ROWS (nota con el total); "Por proyecto" anade cuantas llamadas suman
#     las filas omitidas. `aggregate_calls` solo crea un `ProjectMetrics` para un proyecto con llamadas en la ventana:
#     uno leido con todas sus llamadas fuera de ella, o solo con skills, no aparece (lo dice una linea fija). Si
#     alguien pasa a mano uno con 0 llamadas, el generador lo imprime como fila de ceros con la barra vacia.
#
# DESVIOS respecto de 3.6 del plan (a registrar al cerrar T6): "Por conjunto" lleva dos tablas mas (detalle con
# sesiones, llamadas por sesion, repeticiones y p90 de duracion y herramientas; y tokens por conjunto y rango de
# version) ademas de la de las ocho columnas del plan; el global numera los proyectos en lugar de usar el alias de
# 3.7 (decision D1 del propietario).

VOLUME_RATIO = 10
OTHER_PLUGIN_GROUP = "plugin:(otro)"
OTHER_MODEL = OTHER_LABELS["model"]
MSG_GLOBAL_METRICS = "render_global_report necesita un UsageMetrics"
# Conjuntos de skills que el reporte conoce (listas cerradas del lector); cualquier otro se agrupa como OTHER_GROUP
# (o como OTHER_PLUGIN_GROUP si es un prefijo de plugin que no se vio como agente).
SKILL_GROUPS = frozenset(("SyncLayer", "integrado", "otros", "plugin:(no-valido)"))
# Modelo del global: solo tramos de lista cerrada. Como MODEL_RE, pero el tramo de palabra es una familia conocida
# o `latest` (no `[a-z][a-z0-9]{0,11}`), para que un id con palabras propias no salga.
_GLOBAL_MODEL_WORD = r"(?:opus|sonnet|haiku|fable|instant)"
GLOBAL_MODEL_RE = re.compile(
    r"(?=.{8,64}\Z)claude-(?:" + _GLOBAL_MODEL_WORD + r"|" + _MODEL_NUM + r")"
    r"(?:-(?:" + _GLOBAL_MODEL_WORD + r"|latest|" + _MODEL_NUM + r"|[0-9]{8})){0,8}(?:@[0-9]{8})?\Z")

HOW_TO_READ_GLOBAL = HOW_TO_READ[:-1] + (
    "Se leen todas las carpetas de transcripciones de `projects/`: las sesiones abiertas desde una subcarpeta o un"
    " worktree viven en otra carpeta y salen como otro proyecto.",
)
GLOBAL_COMPARES = (
    "Compara entre conjuntos de agentes solo estas cifras: llamadas y llamadas por sesi\u00f3n, tokens por llamada"
    " (mediana y p90), duraci\u00f3n aproximada, herramientas por llamada, uso de skills (invocaciones y sesiones) y"
    " repeticiones inferidas.",
    "No compara la calidad del resultado de un agente, ni el costo real, ni el ahorro de nadie: esas cifras no salen"
    " de las transcripciones.",
    "Dos conjuntos hacen trabajos distintos: una cifra menor de tokens por llamada no dice nada sobre el resultado.",
    "Comparar conjuntos con vol\u00famenes muy distintos (pocas llamadas frente a muchas) o con versiones de Claude"
    " Code distintas es solo indicativo: con n < 10 la mediana y el p90 dicen poco (marca `*`), y los tokens de las"
    " versiones 2.1.310 a 2.1.327 pueden estar inflados por reintentos.",
    "Las skills solo se comparan por n\u00famero de invocaciones y de sesiones: corren en el contexto de la sesi\u00f3n"
    " que las invoca y no se les atribuyen tokens.",
    "Las repeticiones son inferidas, no un reintento confirmado: salen de las horas de inicio y fin de dos llamadas"
    " seguidas del mismo agente en una sesi\u00f3n. Pueden ser un reintento, un paso de un plan o un encargo nuevo, y la"
    " herramienta no puede distinguirlos; por eso se muestran como `Repeticiones (inferido)` y como porcentaje de las"
    " llamadas.",
    "Contenido de cada conjunto: `integrado`, los agentes integrados de Claude Code; `SyncLayer`, los agentes de este"
    " repositorio (un agente de proyecto con el mismo nombre cuenta como SyncLayer); `plugin:<prefijo>`, todos los"
    " agentes de ese plugin en una sola fila; `otros`, los agentes de usuario; `sin-meta`, las llamadas sin archivo"
    " meta, que no es un conjunto de agentes y no entra en la comparaci\u00f3n. `Agentes` cuenta tipos de agente"
    " distintos, no filas, y no se muestra (`-`) en `otros` ni en `plugin:(no-valido)`.",
)
GLOBAL_PROJECT_NOTES = (
    "Los proyectos van numerados por volumen de llamadas, de m\u00e1s a menos (desempate por sesiones y luego por"
    " tokens). La numeraci\u00f3n puede cambiar entre ejecuciones y no coincide con el alias del reporte de proyecto.",
    "Un proyecto le\u00eddo con todas sus llamadas fuera de la ventana, o solo con skills, no aparece.",
)
GLOBAL_SIN_META_NOTE = (
    "`sin-meta` re\u00fane las llamadas sin archivo meta: no es un conjunto de agentes y no entra en el recuento de"
    " conjuntos ni en la comparaci\u00f3n.")
GLOBAL_ALIAS_LIMIT = (
    "Proyectos: dos carpetas distintas con el mismo alias interno (colisi\u00f3n de 32 bits, improbable) se cuentan como"
    " un solo proyecto; la cabecera lo avisa cuando ocurre.")
GLOBAL_SKILLS_NOTE = (
    "Las skills de usuario se agrupan como `(otra skill)`: el nombre de una skill puede revelar contenido privado."
    " Solo se muestran los nombres de las listas cerradas; el prefijo de plugin (`plugin:<prefijo>`) solo se muestra"
    " si tambi\u00e9n apareci\u00f3 como agente, y el resto se agrupa como `plugin:(otro)`. En los conjuntos con nombres"
    " agrupados la columna `Skills` no se muestra (`-`).")
GLOBAL_PRIVACY_NOTES = (
    "Este archivo es privado por defecto: no contiene contenido de conversaciones, rutas, nombres de carpeta ni alias"
    " de proyecto, pero revela el volumen de uso de cada proyecto. Comp\u00e1rtelo solo despu\u00e9s de revisarlo.",
    "Los proyectos se numeran por volumen en cada ejecuci\u00f3n: la numeraci\u00f3n puede cambiar entre ejecuciones y no se"
    " puede cruzar con el alias del reporte de proyecto. Con un alias de 32 bits, dos carpetas distintas pueden dar el"
    " mismo alias interno (improbable): se cuentan como un solo proyecto y la cabecera lo avisa.",
    "El prefijo de un agente de plugin (`plugin:<prefijo>`) lo escribe Claude Code. El prefijo de una skill de plugin"
    " sale de texto que escribe el modelo: solo se muestra si ese prefijo tambi\u00e9n apareci\u00f3 como agente en esta"
    " lectura; el resto se agrupa como `plugin:(otro)`. Los nombres de skills de usuario no salen: se agrupan como"
    " `(otra skill)`.",
    "Los nombres de modelo que no son de una lista cerrada (familias conocidas, n\u00fameros y fechas) salen como"
    " `(otro modelo)`. En los conjuntos `otros` y `plugin:(no-valido)` y en los conjuntos de skills con nombres"
    " agrupados no se muestra cu\u00e1ntos agentes ni cu\u00e1ntas skills distintos hay (`-`).",
    "Un agente de proyecto con el mismo nombre que uno de SyncLayer cuenta como SyncLayer.",
)


def _global_model_label(model) -> str:
    """Modelo a mostrar en el global: un alias, la etiqueta cerrada `(otro modelo)` o un id hecho solo de tramos
    de lista cerrada (GLOBAL_MODEL_RE); cualquier otra cosa, incluida `<synthetic>`, sale como OTHER_MODEL."""
    if isinstance(model, str) and (model in MODEL_ALIASES or model == OTHER_MODEL
                                   or GLOBAL_MODEL_RE.match(model) is not None):
        return model
    return OTHER_MODEL


def _plugin_groups_seen(metrics) -> frozenset:
    """Conjuntos `plugin:<prefijo>` (prefijo validado) de agentes vistos en la lectura: los de las llamadas de la
    ventana y los de los agentes que invocaron skills. Su prefijo lo escribe Claude Code en el meta."""
    labels = {g.group for g in metrics.groups}
    labels.update(r.agent_group for r in metrics.skills.by_agent)
    return frozenset(label for label in labels if isinstance(label, str) and label.startswith("plugin:")
                     and PLUGIN_PREFIX_RE.match(label[7:]) is not None)


def _skill_shown(skill, group, plugins) -> bool:
    """True si el nombre de la skill puede salir en el global: lista cerrada de su conjunto, o el conjunto
    `plugin:<prefijo>` de un prefijo visto como agente (el nombre de una skill de plugin ES su conjunto)."""
    if not isinstance(skill, str) or not isinstance(group, str):
        return False
    if group == "SyncLayer":
        return skill in SYNCLAYER_SKILLS
    if group == "integrado":
        return skill in BUILTIN_SKILLS
    return group in plugins and skill == group


def _skill_group_label(group, plugins) -> str:
    """Conjunto de skill a mostrar: los conocidos, un `plugin:<prefijo>` visto como agente, OTHER_PLUGIN_GROUP para
    un prefijo de plugin valido que no se vio como agente, u OTHER_GROUP."""
    if isinstance(group, str):
        if group in SKILL_GROUPS or group in plugins:
            return group
        if group.startswith("plugin:") and PLUGIN_PREFIX_RE.match(group[7:]) is not None:
            return OTHER_PLUGIN_GROUP
    return OTHER_GROUP


def _global_skill_rows(sk, plugins) -> list:
    """Filas (skill, conjunto, invocaciones, sesion principal, subagente, sesiones) del global: las skills de
    lista cerrada y de plugin visto por nombre; el resto, agrupadas UNA vez por conjunto mostrado como OTHER_SKILL.
    Las sesiones de una fila agrupada son las del conjunto si un solo conjunto del lector se agrupo en ella y no
    se mostro ninguna skill de esa etiqueta; si no, None (no se pueden sumar)."""
    group_sessions = {g.group: g.sessions for g in sk.groups}
    shown, merged, shown_labels = [], {}, set()
    for r in sk.rows:
        if r.calls <= 0:
            continue
        label = _skill_group_label(r.group, plugins)
        if _skill_shown(r.skill, r.group, plugins):
            shown.append((r.skill, label, r.calls, r.main_calls, r.subagent_calls, r.sessions))
            shown_labels.add(label)
        else:
            acc = merged.setdefault(label, [0, 0, 0, set()])
            acc[0] += r.calls
            acc[1] += r.main_calls
            acc[2] += r.subagent_calls
            acc[3].add(r.group)
    rows = list(shown)
    for label, acc in merged.items():
        sessions = group_sessions.get(list(acc[3])[0]) if label not in shown_labels and len(acc[3]) == 1 else None
        rows.append((OTHER_SKILL, label, acc[0], acc[1], acc[2], sessions))
    rows.sort(key=lambda r: (-r[2], r[0], r[1]))
    return rows


def _global_skill_groups(sk, plugins) -> list:
    """Filas (conjunto, skills, invocaciones, sesiones) de "Por conjunto de skill" con las etiquetas del global.
    Los conjuntos que el lector separa y el global junta (OTHER_GROUP, OTHER_PLUGIN_GROUP) suman invocaciones y
    sacan "-" en las sesiones. `Skills` solo sale si todos los nombres del conjunto se muestran: si hay alguno
    agrupado, el numero diria cuantas skills de usuario distintas hay."""
    shown_labels, hidden_labels = set(), set()
    for r in sk.rows:
        if r.calls > 0:
            label = _skill_group_label(r.group, plugins)
            (shown_labels if _skill_shown(r.skill, r.group, plugins) else hidden_labels).add(label)
    acc_by_label = {}
    for g in sk.groups:
        if g.calls > 0:
            acc = acc_by_label.setdefault(_skill_group_label(g.group, plugins), [0, 0, 0, 0])
            acc[0] += g.skills
            acc[1] += g.calls
            acc[2] += g.sessions
            acc[3] += 1
    rows = []
    for label, acc in acc_by_label.items():
        names = acc[0] if label in shown_labels and label not in hidden_labels else None
        rows.append((label, names, acc[1], acc[2] if acc[3] == 1 else None))
    rows.sort(key=lambda r: (-r[2], r[0]))
    return rows


def _global_agent_skill_rows(sk, plugins) -> list:
    """Filas (agente, conjunto del agente, skill, invocaciones) de las skills invocadas dentro de subagentes, con
    el nombre de skill y el conjunto protegidos como en `_global_skill_rows` y las filas iguales sumadas."""
    merged = {}
    for r in sk.by_agent:
        if r.calls <= 0:
            continue
        skill = r.skill if _skill_shown(r.skill, r.skill_group, plugins) else OTHER_SKILL
        key = (r.agent, _group_label(r.agent_group), skill)
        merged[key] = merged.get(key, 0) + r.calls
    rows = [(key[0], key[1], key[2], calls) for key, calls in merged.items()]
    rows.sort(key=lambda r: (-r[3], r[0], r[1], r[2]))
    return rows


def _group_detail_table(metrics) -> list:
    rows = []
    for g in metrics.groups:
        m = g.metrics
        tk = m.tokens
        rows.append([_code(_group_label(g.group)), _num(m.sessions), _tenths(m.calls_per_session_tenths),
                     _small(tk.n, tk.total.small), _num(tk.total.total),
                     _small(m.duration.p90, m.duration.small), _small(m.tools.p90, m.tools.small),
                     _num(m.repeats), _percent(m.repeats, m.calls)])
    return _capped_table(["Conjunto", "Sesiones", "Llamadas/sesi\u00f3n", "n", "Tokens (suma)",
                          "Duraci\u00f3n aprox. s (p90)", "Herramientas (p90)", "Repeticiones (inferido)",
                          "Repeticiones (% de llamadas)"], "lrrrrrrrr", rows)


def _group_range_table(metrics) -> list:
    rows = []
    for g in metrics.groups:
        for row in g.metrics.versions:
            if row.calls <= 0:
                continue
            tk = row.tokens
            note = NOTE_DOUBTFUL_RANGE if row.inflated else (NOTE_NO_RANGE if row.range == RANGE_NONE else "")
            rows.append([_code(_group_label(g.group)), _code(row.range), _num(row.calls), _small(tk.n, tk.total.small),
                         _small(tk.total.median, tk.total.small), _small(tk.total.p90, tk.total.small), note])
    return _capped_table(["Conjunto", "Rango", "Llamadas", "n", "Mediana", "p90", "Nota"], "llrrrrl", rows)


def _live_group_calls(metrics) -> list:
    """Llamadas de cada conjunto DE AGENTES con llamadas: `sin-meta` no es un conjunto de agentes."""
    return [g.metrics.calls for g in metrics.groups if g.metrics.calls > 0 and g.group != NO_META_GROUP]


def _global_group_section(metrics) -> list:
    live = _live_group_calls(metrics)
    out = ["## Por conjunto", ""]
    if len(live) == 1:
        out += ["Solo hay un conjunto con llamadas en la ventana: no hay con qu\u00e9 comparar.", ""]
    elif len(live) > 1 and max(live) >= VOLUME_RATIO * min(live):
        out += ["Los conjuntos tienen vol\u00famenes muy distintos (de %d a %d llamadas): compararlos es solo"
                " indicativo." % (min(live), max(live)), ""]
    if any(g.group == NO_META_GROUP and g.metrics.calls > 0 for g in metrics.groups):
        out += [GLOBAL_SIN_META_NOTE, ""]
    out += _group_table(metrics, True)
    out += ["", "Detalle por conjunto:", ""] + _group_detail_table(metrics)
    out += ["", "Tokens por llamada, por conjunto y rango de versi\u00f3n:", ""] + _group_range_table(metrics)
    return out + [""]


def _global_project_section(metrics) -> list:
    # numeracion por valores visibles (llamadas, sesiones, tokens): nunca por alias. El orden es estable y, si dos
    # proyectos empatan en todo, sus filas son identicas
    projects = sorted(metrics.projects, key=lambda p: (-p.metrics.calls, -p.metrics.sessions,
                                                       -p.metrics.tokens.total.total))
    max_calls = max([p.metrics.calls for p in projects] or [0])
    rows = [[_code("proyecto %d" % n), _num(p.metrics.sessions), _num(p.metrics.calls),
             _bar(p.metrics.calls, max_calls), _num(p.metrics.tokens.total.total)]
            for n, p in enumerate(projects, 1)]
    out = ["## Por proyecto", ""]
    for note in GLOBAL_PROJECT_NOTES:
        out += [note, ""]
    out += _capped_table(["Proyecto", "Sesiones", "Llamadas", "Barra", "Tokens (suma)"], "lrrlr", rows)
    omitted = projects[MAX_TABLE_ROWS:]
    if omitted:
        calls = sum(p.metrics.calls for p in omitted)
        out += ["", "%s %s %s." % (
            "La fila omitida suma" if len(omitted) == 1 else "Las %d filas omitidas suman" % len(omitted),
            _num(calls), "llamada" if calls == 1 else "llamadas")]
    return out + [""]


def _global_skills_section(metrics) -> list:
    sk = metrics.skills
    plugins = _plugin_groups_seen(metrics)
    out = ["## Skills", ""]
    if sk.calls == 0:
        out.append("Sin invocaciones de skills en la ventana.")
    else:
        out.append("Invocaciones: %d en %s (%d en la sesi\u00f3n principal, %d en subagentes)." % (
            sk.calls, _plural(sk.sessions, "sesi\u00f3n", "sesiones"), sk.main_calls, sk.subagent_calls))
        rows = _global_skill_rows(sk, plugins)
        max_calls = max([r[2] for r in rows] or [0])
        out += ["", "Por skill:", ""]
        out += _capped_table(
            ["Skill", "Conjunto", "Invocaciones", "Barra", "Sesiones", "Sesi\u00f3n principal", "Subagente"],
            "llrlrrr",
            [[_code(r[0]), _code(r[1]), _num(r[2]), _bar(r[2], max_calls), _num(r[5]), _num(r[3]), _num(r[4])]
             for r in rows])
        out += ["", "Por conjunto de skill:", ""]
        out += _capped_table(
            ["Conjunto", "Skills", "Invocaciones", "Sesiones"], "lrrr",
            [[_code(r[0]), _num(r[1]), _num(r[2]), _num(r[3])] for r in _global_skill_groups(sk, plugins)])
        linked = _global_agent_skill_rows(sk, plugins)
        if linked:
            out += ["", "Por agente (skills invocadas dentro de subagentes):", ""]
            out += _capped_table(
                ["Agente", "Conjunto del agente", "Skill", "Invocaciones"], "lllr",
                [[_code(r[0]), _code(r[1]), _code(r[2]), _num(r[3])] for r in linked])
        out += ["", GLOBAL_SKILLS_NOTE]
    out += ["", "No se atribuyen tokens a una skill: corre en el contexto de la sesi\u00f3n que la invoca.", ""]
    return out


def _global_compare_section() -> list:
    return ["## Qu\u00e9 compara y qu\u00e9 no", ""] + _bullets(GLOBAL_COMPARES) + [""]


def _global_quality_section(metrics) -> list:
    """La calidad de T5 y, tras sus tablas, el limite de la agrupacion de proyectos por alias."""
    return _quality_section(metrics)[:-1] + ["", GLOBAL_ALIAS_LIMIT, ""]


def _global_header_section(metrics, generated) -> list:
    t = metrics.total
    lines = [
        REPORT_MARKER,
        "# Reporte global de uso de subagentes",
        "",
        "> - Ventana: " + _window_text(metrics.window),
        "> - Llamadas: %d en %s en %s" % (t.calls, _plural(t.sessions, "sesi\u00f3n", "sesiones"),
                                         _plural(len(metrics.projects), "proyecto", "proyectos")),
        "> - Claude Code: " + _versions_header(metrics.versions_seen),
        "> - Esquema del reporte: %d" % REPORT_SCHEMA,
    ]
    if generated is not None:
        lines.append("> - Generado: " + generated.isoformat())
    lines.append("> - Alcance: todos los proyectos le\u00eddos; proyectos numerados por volumen, sin nombres ni rutas"
                 " ni alias.")
    lines.append("> - Reporte privado por defecto: lleva el volumen de uso de cada proyecto; no lo subas a git y"
                 " comp\u00e1rtelo solo despu\u00e9s de revisarlo.")
    for text in _notices(metrics):
        lines.append("> - AVISO: " + text)
    return lines + [""]


def _global_footer_section(metrics) -> list:
    out = ["## Pie", ""] + _bullets([
        "report_schema: %d" % REPORT_SCHEMA,
        "herramienta: " + TOOL_NAME,
        "ultima_version_verificada: " + _code(metrics.verified_max),
        "alcance: global (todos los proyectos le\u00eddos)",
    ])
    return out + [""] + _bullets(GLOBAL_PRIVACY_NOTES)


def render_global_report(metrics, generated=None) -> str:
    """Markdown del reporte GLOBAL (todos los proyectos leidos; ver la cabecera de la seccion). Pura.

    `metrics`: UsageMetrics de las llamadas de TODOS los proyectos (un `ProjectMetrics` por proyecto; el global los
    numera y no imprime su alias). `generated`: datetime.date inyectada o None; el generador no lee el reloj.
    ValueError con mensaje fijo (sin eco del valor) ante argumentos invalidos. Devuelve texto con LF y salto
    final; T7 lo escribe en UTF-8 sin BOM."""
    if not isinstance(metrics, UsageMetrics):
        raise ValueError(MSG_GLOBAL_METRICS)
    if generated is not None and not _is_date(generated):
        raise ValueError(MSG_REPORT_DATE)
    extra = ["Proyectos con llamadas en la ventana: %d" % len(metrics.projects),
             "Conjuntos con llamadas: %d" % len(_live_group_calls(metrics))]
    lines = _global_header_section(metrics, generated)
    lines += _summary_section(metrics, extra)
    if metrics.total.calls:
        lines += _global_group_section(metrics)
        lines += _agent_sections(metrics, _global_model_label)
        lines += _global_project_section(metrics)
    lines += _global_skills_section(metrics)
    if metrics.total.calls:
        lines += _version_section(metrics)
    lines += _global_compare_section()
    lines += _global_quality_section(metrics)
    lines += _guide_section(HOW_TO_READ_GLOBAL)
    lines += _global_footer_section(metrics)
    return "\n".join(lines) + "\n"


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
