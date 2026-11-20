"""Generador de transcripciones SINTETICAS para las pruebas del reporte de uso.

No es una prueba (no empieza con test_): lo importan las pruebas. Todo lo que genera es
inventado; nunca hay datos reales. Las lineas llevan MARCADORES unicos en los campos de
contenido para comprobar que ninguna salida de la herramienta los copia.

Estructura que construye, dentro de una carpeta temporal:

    <claude_dir>/projects/<carpeta-proyecto>/<sesion>.jsonl
    <claude_dir>/projects/<carpeta-proyecto>/<sesion>/subagents/agent-<id>.jsonl
    <claude_dir>/projects/<carpeta-proyecto>/<sesion>/subagents/agent-<id>.meta.json
"""

import json
import os
import re

# Marcadores de contenido. Ninguno debe aparecer jamas en una salida. Ninguno cumple la lista
# permitida de nombres (llevan espacios) salvo los de nombre de carpeta y de sesion, que no
# se muestran nunca.
M_CONTENT = "ZZMARK contenido del mensaje secreto"
M_PROMPT = "ZZMARK prompt privado del usuario"
M_DESCRIPTION = "ZZMARK descripcion interna"
M_RESULT = "ZZMARK resultado de herramienta"
M_CWD = "C:\\ZZMARK\\ruta\\privada con espacios"
M_BRANCH = "ZZMARK/rama-secreta"
M_INPUT = "ZZMARK entrada de herramienta"
M_ARGS = "ZZMARK argumentos de skill"
M_UNKNOWN_KEY = "ZZMARKclaveDesconocida"
M_UNKNOWN_INPUT_KEY = "ZZMARKclaveEntrada"
M_FOLDER = "ZZMARKcarpeta"
M_SESSION = "ZZMARKsesion"
M_MODEL = "ZZMARK modelo invalido"
M_VERSION = "ZZMARK version invalida"
M_TYPE = "ZZMARK tipo invalido"
ALL_MARKERS = (
    M_CONTENT, M_PROMPT, M_DESCRIPTION, M_RESULT, M_CWD, M_BRANCH, M_INPUT, M_ARGS,
    M_UNKNOWN_KEY, M_UNKNOWN_INPUT_KEY, M_FOLDER, M_SESSION, M_MODEL, M_VERSION, M_TYPE,
)

DEFAULT_VERSION = "2.1.330"
DEFAULT_MODEL = "claude-opus-4-1"


def folder_name_for(abs_path: str) -> str:
    """Calculo independiente del que hace la herramienta: por unidad UTF-16, lo que no es
    [A-Za-z0-9] pasa a '-' (un caracter fuera del BMP son dos unidades, como en JS)."""
    raw = abs_path.encode("utf-16-le", "surrogatepass")
    out = []
    for i in range(0, len(raw), 2):
        unit = raw[i] | (raw[i + 1] << 8)
        ch = chr(unit)
        out.append(ch if unit < 128 and re.fullmatch("[A-Za-z0-9]", ch) else "-")
    return "".join(out)


def make_tagged_reparse_file(path: str) -> bool:
    """Archivo con punto de reanalisis de etiqueta propia (tag 0x80001234 + GUID), sin privilegio.

    Replica el helper de tests/test_install.py (alla es un metodo que salta la prueba; aqui
    devuelve False si no se pudo). Solo Windows. El tag 0x1234 falla en este equipo con
    ERROR_INVALID_REPARSE_DATA; por eso 0x80001234."""
    if os.name != "nt":
        return False
    import ctypes
    import struct
    from ctypes import wintypes
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPCVOID, wintypes.DWORD,
                                    wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                    wintypes.LPVOID]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.CreateFileW(path, 0x40000000, 0, None, 3, 0x00200000, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        os.remove(path)
        return False
    guid = bytes(range(1, 17))
    buf = struct.pack("<IHH", 0x80001234, len(guid), 0) + guid
    returned = wintypes.DWORD(0)
    ok = k32.DeviceIoControl(handle, 0x000900A4, buf, len(buf), None, 0, ctypes.byref(returned), None)
    k32.CloseHandle(handle)
    if not ok:
        os.remove(path)
        return False
    return True


def usage(inp=10, out=5, cache_w=2, cache_r=3, **extra):
    data = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_creation_input_tokens": cache_w,
        "cache_read_input_tokens": cache_r,
    }
    data.update(extra)
    return data


def text_block(text=M_CONTENT):
    return {"type": "text", "text": text}


def tool_use_block(block_id, name, tool_input=None):
    return {"type": "tool_use", "id": block_id, "name": name,
            "input": tool_input if tool_input is not None else {"note": M_INPUT}}


def assistant(msg_id, ts, usage_value="default", model=DEFAULT_MODEL, version=DEFAULT_VERSION,
              blocks=None, sidechain=True, **extra):
    """Linea assistant. usage_value='default' usa usage(); None omite la clave."""
    message = {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": blocks if blocks is not None else [text_block()],
    }
    if usage_value == "default":
        message["usage"] = usage()
    elif usage_value is not None:
        message["usage"] = usage_value
    line = {
        "type": "assistant",
        "timestamp": ts,
        "version": version,
        "isSidechain": sidechain,
        "uuid": "u-" + msg_id,
        "cwd": M_CWD,
        "gitBranch": M_BRANCH,
        "message": message,
    }
    line.update(extra)
    return line


def stream(msg_id, ts, usages, **kw):
    """Una respuesta repartida en varias lineas (streaming): mismo message.id, un usage por linea.

    Replica la forma real confirmada en G1 (~1,9 lineas por id): cada linea repite el id y el
    usage crece hasta el valor final. `usages` es una lista de dict (ver usage())."""
    return [assistant(msg_id, ts, usage_value=u, **kw) for u in usages]


def user(ts, text=M_PROMPT, version=DEFAULT_VERSION, sidechain=True, **extra):
    line = {
        "type": "user",
        "timestamp": ts,
        "version": version,
        "isSidechain": sidechain,
        "cwd": M_CWD,
        "gitBranch": M_BRANCH,
        "message": {"role": "user", "content": text},
    }
    line.update(extra)
    return line


def tool_result_line(ts, result=None, version=DEFAULT_VERSION):
    return {
        "type": "user",
        "timestamp": ts,
        "version": version,
        "isSidechain": False,
        "message": {"role": "user", "content": [{"type": "tool_result", "content": M_RESULT}]},
        "toolUseResult": result if result is not None else {
            "totalDurationMs": 1200, "totalTokens": 50, "totalToolUseCount": 2,
            "prompt": M_PROMPT, "content": M_RESULT,
        },
    }


class Tree:
    """Arbol projects/ sintetico dentro de `base` (una carpeta temporal)."""

    def __init__(self, base, claude_name="claude home"):
        self.claude_dir = os.path.join(base, claude_name)
        self.projects = os.path.join(self.claude_dir, "projects")
        os.makedirs(self.projects, exist_ok=True)

    def folder(self, name):
        path = os.path.join(self.projects, name)
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def write_lines(path, items, final_newline=True):
        """items: dict (se serializa), bytes o str (literales, para corruptas y truncadas)."""
        parts = []
        for item in items:
            if isinstance(item, dict):
                parts.append(json.dumps(item).encode("utf-8"))
            elif isinstance(item, str):
                parts.append(item.encode("utf-8"))
            else:
                parts.append(item)
        data = b"\n".join(parts)
        if final_newline and parts:
            data += b"\n"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def main_session(self, folder, session, items, final_newline=True):
        path = os.path.join(self.folder(folder), session + ".jsonl")
        self.write_lines(path, items, final_newline)
        return path

    def subagent(self, folder, session, agent_id, items, meta="default", final_newline=True):
        """meta: 'default' crea un meta con agentType; None no lo crea; dict o bytes lo escribe tal cual."""
        sub = os.path.join(self.folder(folder), session, "subagents")
        os.makedirs(sub, exist_ok=True)
        path = os.path.join(sub, "agent-" + agent_id + ".jsonl")
        self.write_lines(path, items, final_newline)
        if meta == "default":
            meta = {"agentType": "forge", "toolUseId": "toolu_" + agent_id, "description": M_DESCRIPTION}
        if meta is not None:
            with open(os.path.join(sub, "agent-" + agent_id + ".meta.json"), "wb") as f:
                f.write(json.dumps(meta).encode("utf-8") if isinstance(meta, dict) else meta)
        return path
