#!/usr/bin/env python3
"""agent_guard: hook PreToolUse de Claude Code para limitar lo que puede escribir un agente.

Uso: python agent_guard.py <tests-only|readonly> [--allow-temp]

Es una guarda HEURISTICA contra escrituras accidentales, NO un sandbox. Un
interprete en una linea (`python -c`, `node -e`, `perl -e`, `powershell -Command`,
`bash -c`, `xargs rm`, etc.) todavia puede escribir archivos. No sustituye
permisos del sistema operativo ni aislamiento real.

Contrato del hook: JSON por stdin (`tool_name`, `tool_input`, `cwd`). Exit 0 =
permitir (sin salida). Exit 2 = bloquear; el texto de stderr se le muestra al
agente como motivo. Cualquier otro codigo de salida lo trata Claude Code como un
error NO bloqueante y la llamada sigue, por eso el script nunca sale con un codigo
distinto de 0 o 2: ante entrada invalida, modo desconocido o cualquier excepcion
interna (incluidos RecursionError y MemoryError) falla cerrado (exit 2).

LIMITACION que no se puede arreglar desde este script: si `python` no esta en el
PATH del shell que lanza el hook, el shell sale con 127 y Claude Code deja pasar la
llamada (falla abierto). Hay que asegurar que `python` resuelva en ese shell.

Modos:
  tests-only  Write/Edit/NotebookEdit solo sobre archivos de pruebas. Los
              directorios de pruebas se evaluan sobre la ruta relativa a `cwd`;
              fuera de `cwd` (o sin `cwd`) solo cuenta el nombre del archivo.
  readonly    Bash sin comandos que modifiquen repo, archivos o entorno.
              --allow-temp permite rm/rmdir/mkdir/touch/cp/mv/tee y redirecciones
              cuando todas las rutas estan bajo un directorio temporal.

Solo biblioteca estandar. No usa red ni escribe archivos.
"""
import fnmatch
import json
import re
import os
import sys

MODES = ("tests-only", "readonly")

# ---------------------------------------------------------------- tests-only

TEST_DIRS = {
    "tests", "test", "__tests__", "spec", "specs", "fixtures", "testdata",
    "e2e", "cypress", "playwright",
}
# Se comparan contra el nombre en minusculas.
TEST_FILE_PATTERNS = [
    "test_*.py", "*_test.*", "*.test.*", "*.spec.*", "conftest.py",
]
# Se comparan sin normalizar mayusculas (la T mayuscula evita Latest.java, Contests.cs).
TEST_FILE_PATTERNS_CS = ["*Tests.cs", "*Test.java", "*Tests.java"]
TESTS_TOOLS = ("Write", "Edit", "NotebookEdit")


def _norm_path(p):
    """Minusculas, '/' como separador y formas /c/x, /mnt/c/x o C:\\x unificadas a c:/x."""
    p = p.replace("\\", "/")
    m = re.match(r"^/(?:mnt/)?([A-Za-z])(?:/|$)", p)
    if m:
        p = m.group(1) + ":/" + p[m.end():]
    p = re.sub(r"(?<!^)/{2,}", "/", p)
    return p.lower()


def _is_abs(p):
    return p.startswith("/") or re.match(r"^[a-z]:/", p) is not None


def is_test_path(path, cwd=None):
    raw_parts = path.replace("\\", "/").split("/")
    if ".." in raw_parts:
        return False
    p = _norm_path(path)
    if _is_abs(p):
        dir_segs = []
        if isinstance(cwd, str) and cwd.strip():
            c = _norm_path(cwd).rstrip("/")
            if _is_abs(c) and p.startswith(c + "/"):
                dir_segs = p[len(c) + 1:].split("/")[:-1]
    else:
        dir_segs = p.split("/")[:-1]
    if any(seg in TEST_DIRS for seg in dir_segs):
        return True
    base = p.rsplit("/", 1)[-1]
    if any(fnmatch.fnmatchcase(base, pat) for pat in TEST_FILE_PATTERNS):
        return True
    return any(fnmatch.fnmatchcase(raw_parts[-1], pat) for pat in TEST_FILE_PATTERNS_CS)


def _check_tests_only(payload):
    tool = payload.get("tool_name")
    if tool not in TESTS_TOOLS:
        return None
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        ti = {}
    path = ti.get("notebook_path") if tool == "NotebookEdit" else ti.get("file_path")
    if not isinstance(path, str) or not path.strip():
        return ("Bloqueado por agent_guard (tests-only): la llamada a %s no trae ruta de archivo. "
                "Este agente solo puede escribir archivos de pruebas." % tool)
    if is_test_path(path, payload.get("cwd")):
        return None
    return ("Bloqueado por agent_guard (tests-only): '%s' no es un archivo de pruebas. "
            "Este agente solo escribe en tests (carpetas tests/, fixtures/, e2e/, archivos "
            "test_*.py, *.spec.*, etc.); reportá el cambio necesario en el código en lugar de aplicarlo."
            % path)


# ------------------------------------------------------------------ readonly

class ParseError(Exception):
    pass


_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SUB = "$(sub)"
_ESC_NEXT = set(" \t\"'\\$`;&|<>()\n*?[]#~")
_MAX_DEPTH = 20
_WORD_END = " \t\n;&|<>()"


def _skip_ansi(s, j):
    """s[j] es '$' y s[j+1] es "'" ; devuelve el indice tras el cierre o -1."""
    n = len(s)
    k = j + 2
    while k < n and s[k] != "'":
        k += 2 if s[k] == "\\" else 1
    return k + 1 if k < n else -1


def _skip_dquote(s, j):
    """s[j] es '"' ; devuelve el indice tras el cierre o -1. Salta $( ) y backticks."""
    n = len(s)
    j += 1
    while j < n and s[j] != '"':
        c = s[j]
        if c == "\\":
            j += 2
        elif c == "$" and s[j + 1:j + 2] == "(":
            end, j2 = _match_paren(s, j + 2)
            if end >= n:
                return -1
            j = j2
        elif c == "`":
            end, j2 = _match_backtick(s, j + 1)
            if end >= n:
                return -1
            j = j2
        else:
            j += 1
    return j + 1 if j < n else -1


def _read_delim(s, k):
    """Lee la palabra delimitadora de un heredoc desde s[k]; devuelve (delim, indice, quoted).

    Quita comillas y `\\x` -> `x` como bash. delim es None si no hay palabra. quoted es True
    si la palabra lleva alguna comilla o escape (`'x'`, `"x"`, `\\x`, `$'x'`, `$"x"`): entonces
    el cuerpo no expande `$( )` ni backticks.
    """
    n = len(s)
    while k < n and s[k] in " \t":
        k += 1
    start = k
    out = []
    quoted = False
    while k < n and s[k] not in _WORD_END:
        ch = s[k]
        if ch == "$" and s[k + 1:k + 2] == "'":
            e = _skip_ansi(s, k)
            if e == -1:
                return None, n, False
            out.append(re.sub(r"\\(['\\\"])", r"\1", s[k + 2:e - 1]))
            quoted = True
            k = e
        elif ch == "$" and s[k + 1:k + 2] == '"':
            quoted = True
            k += 1  # la comilla doble se procesa en la vuelta siguiente
        elif ch == "\\":
            quoted = True
            if k + 1 < n:
                out.append(s[k + 1])
            k += 2
        elif ch == "'":
            quoted = True
            e = s.find("'", k + 1)
            if e == -1:
                return None, n, False
            out.append(s[k + 1:e])
            k = e + 1
        elif ch == '"':
            quoted = True
            k += 1
            while k < n and s[k] != '"':
                if s[k] == "\\" and k + 1 < n and s[k + 1] in '$`"\\':
                    out.append(s[k + 1])
                    k += 2
                else:
                    out.append(s[k])
                    k += 1
            if k >= n:
                return None, n, False
            k += 1
        else:
            out.append(ch)
            k += 1
    if k == start:
        return None, k, False
    return "".join(out), k, quoted


def _skip_bodies(s, i, heredocs):
    """Salta los cuerpos de heredoc desde s[i].

    Devuelve (indice, todos_terminados, cuerpos_expandibles): estos ultimos son los textos de
    los cuerpos cuyo delimitador no llevaba comillas (bash les expande $( ) y backticks).
    """
    n = len(s)
    expandable = []
    for delim, strip_tabs, quoted in heredocs:
        found = False
        start = i
        while i < n:
            line_start = i
            e = s.find("\n", i)
            if e == -1:
                e = n
            line = s[i:e]
            i = e + 1
            if (line.lstrip("\t") if strip_tabs else line).rstrip("\r") == delim:
                found = True
                if not quoted:
                    expandable.append(s[start:line_start])
                break
        if not found:
            return n, False, []
    return i, True, expandable


def _match_paren(s, i):
    """s[i] es el primer caracter tras '$(' ; devuelve (indice_de_cierre, fin).

    Si no cierra devuelve (n, n). Salta comillas y cuerpos de heredoc.
    """
    depth = 1
    j = i
    n = len(s)
    heredocs = []
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            if k == -1:
                return n, n
            j = k + 1
            continue
        if c == "$" and s[j + 1:j + 2] == "'":
            k = _skip_ansi(s, j)
            if k == -1:
                return n, n
            j = k
            continue
        if c == '"':
            k = _skip_dquote(s, j)
            if k == -1:
                return n, n
            j = k
            continue
        if c == "<" and s.startswith("<<", j) and not s.startswith("<<<", j):
            k = j + 2
            strip = False
            if s[k:k + 1] == "-":
                strip = True
                k += 1
            delim, k, quoted = _read_delim(s, k)
            if delim is not None:
                heredocs.append((delim, strip, quoted))
            j = max(k, j + 2)
            continue
        if c == "\n" and heredocs:
            j, ok, _ = _skip_bodies(s, j + 1, heredocs)
            heredocs = []
            if not ok:
                return n, n
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j, j + 1
        j += 1
    return n, n


def _match_backtick(s, i):
    j = i
    n = len(s)
    while j < n:
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "`":
            return j, j + 1
        j += 1
    return n, n


def _scan_subs(body, heredoc=False):
    """Devuelve los textos internos de $( ) y backticks de un fragmento no ejecutable
    (aritmetica, [[ ]] o cuerpo de heredoc) para analizarlos como comandos.

    heredoc=True: en un cuerpo de heredoc las comillas no son especiales; solo `\\`,
    $( ) y backticks.
    """
    out = []
    n = len(body)
    j = 0

    def grab_paren(j):
        end, j2 = _match_paren(body, j + 2)
        if end >= n:
            raise ParseError("sustitución $( sin cerrar")
        out.append(body[j + 2:end])
        return j2

    def grab_tick(j):
        end, j2 = _match_backtick(body, j + 1)
        if end >= n:
            raise ParseError("backtick sin cerrar")
        out.append(body[j + 1:end])
        return j2

    while j < n:
        c = body[j]
        if heredoc:
            if c == "\\":
                j += 2
            elif c == "$" and body[j + 1:j + 2] == "(":
                j = grab_paren(j)
            elif c == "`":
                j = grab_tick(j)
            else:
                j += 1
            continue
        if c == "\\":
            j += 2
        elif c == "'":
            k = body.find("'", j + 1)
            j = n if k == -1 else k + 1
        elif c == "$" and body[j + 1:j + 2] == "'":
            k = _skip_ansi(body, j)
            j = n if k == -1 else k
        elif c == "$" and body[j + 1:j + 2] == "(":
            j = grab_paren(j)
        elif c == "`":
            j = grab_tick(j)
        elif c == '"':
            j += 1
            while j < n and body[j] != '"':
                if body[j] == "\\":
                    j += 2
                elif body[j] == "$" and body[j + 1:j + 2] == "(":
                    j = grab_paren(j)
                elif body[j] == "`":
                    j = grab_tick(j)
                else:
                    j += 1
            j += 1
        else:
            j += 1
    return out


def _match_old_arith(s, i):
    """s[i] es el primer caracter tras '$['; devuelve el indice del ']' de cierre o -1."""
    n = len(s)
    depth = 1
    j = i
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            if k == -1:
                return -1
            j = k + 1
            continue
        if c == '"':
            k = _skip_dquote(s, j)
            if k == -1:
                return -1
            j = k
            continue
        if c == "$" and s[j + 1:j + 2] == "(":
            end, j2 = _match_paren(s, j + 2)
            if end >= n:
                return -1
            j = j2
            continue
        if c == "`":
            end, j2 = _match_backtick(s, j + 1)
            if end >= n:
                return -1
            j = j2
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _match_dbl_bracket(s, i):
    """s[i] es el primer caracter tras '[['; devuelve el indice tras el ']]' de cierre."""
    n = len(s)
    j = i
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
        elif c == "'":
            k = s.find("'", j + 1)
            if k == -1:
                break
            j = k + 1
        elif c == "$" and s[j + 1:j + 2] == "'":
            k = _skip_ansi(s, j)
            if k == -1:
                break
            j = k
        elif c == '"':
            k = _skip_dquote(s, j)
            if k == -1:
                break
            j = k
        elif c == "$" and s[j + 1:j + 2] == "(":
            end, j2 = _match_paren(s, j + 2)
            if end >= n:
                break
            j = j2
        elif c == "`":
            end, j2 = _match_backtick(s, j + 1)
            if end >= n:
                break
            j = j2
        elif (c == "]" and s.startswith("]]", j) and j > 0 and s[j - 1] in " \t\n"
              and (j + 2 >= n or s[j + 2] in " \t\n;&|)")):
            return j + 2
        else:
            j += 1
    raise ParseError("[[ sin cerrar")


def parse_commands(cmd, depth=0):
    """Devuelve lista de (palabras, redirecciones) por comando simple.

    redirecciones: lista de (operador, destino) solo de salida a archivo.
    Incluye los comandos dentro de $( ), backticks y <( ) / >( ). Lanza ParseError
    si el texto no se puede analizar con seguridad (comilla, $(, backtick o heredoc
    sin cerrar).
    """
    if depth > _MAX_DEPTH:
        raise ParseError("anidamiento excesivo")
    cmds = []
    words = []
    redirs = []
    buf = []
    in_word = False
    pending = None  # (op, es_salida)
    heredocs = []
    arith_failed = False
    i = 0
    n = len(cmd)

    def end_word():
        nonlocal buf, in_word, pending
        if in_word:
            w = "".join(buf)
            if pending is not None:
                op, is_out = pending
                if is_out:
                    if op == ">&" and re.fullmatch(r"\d+|-", w):
                        pass  # duplicacion de descriptor
                    else:
                        redirs.append((op, w))
                pending = None
            else:
                words.append(w)
        buf = []
        in_word = False

    def end_cmd():
        nonlocal words, redirs, pending
        end_word()
        if words or redirs:
            cmds.append((words, redirs))
        words = []
        redirs = []
        pending = None

    def sub(inner):
        cmds.extend(parse_commands(inner, depth + 1))

    def dollar_paren(i):
        """cmd[i:i+2] == '$(' ; analiza el contenido y devuelve el indice siguiente."""
        if cmd[i + 2:i + 3] == "(":
            # $(( aritmetica )): no es un comando, solo se miran sus sustituciones
            end, _ = _match_paren(cmd, i + 3)
            if end < n and cmd[end + 1:end + 2] == ")":
                for inner in _scan_subs(cmd[i + 3:end]):
                    sub(inner)
                return end + 2
        end, i2 = _match_paren(cmd, i + 2)
        if end >= n:
            raise ParseError("sustitución $( sin cerrar")
        sub(cmd[i + 2:end])
        return i2

    def backtick(i):
        end, i2 = _match_backtick(cmd, i + 1)
        if end >= n:
            raise ParseError("backtick sin cerrar")
        sub(cmd[i + 1:end])
        return i2

    while i < n:
        c = cmd[i]
        nxt = cmd[i + 1] if i + 1 < n else ""
        if (not in_word and pending is None and c in "[(" and nxt == c
                and all(_base(w) in _KEYWORDS or _ASSIGN.match(w) for w in words)):
            # [[ ... ]] y (( ... )): < y > son comparaciones, no redirecciones
            if c == "[":
                if cmd[i + 2:i + 3] in (" ", "\t", "\n"):
                    end = _match_dbl_bracket(cmd, i + 2)
                    for inner in _scan_subs(cmd[i + 2:end - 2]):
                        sub(inner)
                    buf = ["[[ ]]"]
                    in_word = True
                    i = end
                    continue
            elif not arith_failed:
                j, _ = _match_paren(cmd, i + 2)
                if j < n and cmd[j + 1:j + 2] == ")":
                    for inner in _scan_subs(cmd[i + 2:j]):
                        sub(inner)
                    buf = ["(( ))"]
                    in_word = True
                    i = j + 2
                    continue
                if j >= n:
                    # sin cierre: no reintentar en cada '(' posterior (costo cuadratico)
                    arith_failed = True
        if c == "\\":
            if nxt == "\n":
                i += 2
            elif nxt in _ESC_NEXT and nxt:
                buf.append(nxt)
                in_word = True
                i += 2
            else:
                buf.append("\\")  # ruta de Windows: se conserva
                in_word = True
                i += 1
            continue
        if c == "'":
            j = cmd.find("'", i + 1)
            if j == -1:
                raise ParseError("comilla simple sin cerrar")
            buf.append(cmd[i + 1:j])
            in_word = True
            i = j + 1
            continue
        if c == "$" and nxt == "'":
            k = _skip_ansi(cmd, i)
            if k == -1:
                raise ParseError("comilla $'...' sin cerrar")
            buf.append(re.sub(r"\\(['\\\"])", r"\1", cmd[i + 2:k - 1]))
            in_word = True
            i = k
            continue
        if c == '"':
            in_word = True
            i += 1
            while i < n and cmd[i] != '"':
                d = cmd[i]
                if d == "\\" and i + 1 < n:
                    if cmd[i + 1] in '$`"\\':
                        buf.append(cmd[i + 1])
                    elif cmd[i + 1] == "\n":
                        pass
                    else:
                        buf.append("\\" + cmd[i + 1])
                    i += 2
                elif d == "$" and cmd[i + 1:i + 2] == "(":
                    i = dollar_paren(i)
                    buf.append(_SUB)
                elif d == "`":
                    i = backtick(i)
                    buf.append(_SUB)
                else:
                    buf.append(d)
                    i += 1
            if i >= n:
                raise ParseError("comilla doble sin cerrar")
            i += 1
            continue
        if c == "$" and nxt == "(":
            i = dollar_paren(i)
            buf.append(_SUB)
            in_word = True
            continue
        if c == "$" and nxt == "[":
            # $[ ... ] aritmetica antigua: no es un comando, solo se miran sus sustituciones
            end = _match_old_arith(cmd, i + 2)
            if end != -1:
                for inner in _scan_subs(cmd[i + 2:end]):
                    sub(inner)
                buf.append(_SUB)
                in_word = True
                i = end + 1
                continue
        if c == "`":
            i = backtick(i)
            buf.append(_SUB)
            in_word = True
            continue
        if c in "<>" and nxt == "(":
            end, i2 = _match_paren(cmd, i + 2)
            if end >= n:
                raise ParseError("sustitución de proceso sin cerrar")
            sub(cmd[i + 2:end])
            i = i2
            continue
        if c in " \t\r":
            end_word()
            i += 1
            continue
        if c == "\n":
            end_cmd()
            i += 1
            if heredocs:
                i, ok, bodies = _skip_bodies(cmd, i, heredocs)
                if not ok:
                    raise ParseError("heredoc sin terminar")
                heredocs = []
                for body in bodies:
                    for inner in _scan_subs(body, heredoc=True):
                        sub(inner)
            continue
        if c == ";":
            end_cmd()
            i += 1
            continue
        if c == "&":
            if nxt == "&":
                end_cmd()
                i += 2
            elif nxt == ">":
                end_word()
                op = "&>>" if cmd[i + 2:i + 3] == ">" else "&>"
                pending = (op, True)
                i += len(op)
            else:
                end_cmd()
                i += 1
            continue
        if c == "|":
            end_cmd()
            i += 2 if nxt in ("|", "&") and nxt else 1
            continue
        if c in "()":
            end_cmd()
            i += 1
            continue
        if c in "<>":
            if in_word and "".join(buf).isdigit():
                buf = []
                in_word = False
            else:
                end_word()
            if c == ">":
                if nxt == ">":
                    op = ">>"
                elif nxt == "|":
                    op = ">|"
                elif nxt == "&":
                    op = ">&"
                else:
                    op = ">"
                pending = (op, True)
            else:
                if cmd[i:i + 3] == "<<<":
                    op = "<<<"
                elif cmd[i:i + 3] == "<<-":
                    op = "<<-"
                elif nxt == "<":
                    op = "<<"
                elif nxt == "&":
                    op = "<&"
                else:
                    op = "<"
                if op in ("<<", "<<-"):
                    delim, k, quoted = _read_delim(cmd, i + len(op))
                    if delim is None:
                        raise ParseError("heredoc sin delimitador")
                    heredocs.append((delim, op == "<<-", quoted))
                    i = k
                    continue
                pending = (op, False)
            i += len(op)
            continue
        if c == "#" and not in_word:
            j = cmd.find("\n", i)
            i = n if j == -1 else j
            continue
        buf.append(c)
        in_word = True
        i += 1
    end_cmd()
    if heredocs:
        raise ParseError("heredoc sin terminar")
    return cmds


def _base(word):
    b = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if b.endswith(".exe"):
        b = b[:-4]
    return b


_KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until",
             "!", "{", "}", "case", "esac", "for", "in", "select", "function"}
# Envoltorios que ejecutan el comando siguiente: opciones que consumen un valor separado.
_WRAP_VAL = {"exec": {"-a"}, "nice": {"-n"}, "ionice": {"-c", "-n", "-p", "-P", "-u"},
             "stdbuf": {"-i", "-o", "-e"}, "setsid": set()}
_SUDO_VAL = {"-u", "-g", "-h", "-p", "-c", "-d", "-r", "-t", "-U", "-C", "-D", "-R", "-T"}


def _command_word(words):
    """Salta asignaciones y envoltorios. Devuelve (nombre, args) o None."""
    i = 0
    n = len(words)
    while i < n:
        w = words[i]
        if _ASSIGN.match(w):
            i += 1
            continue
        b = _base(w)
        if b in _KEYWORDS:
            i += 1
        elif b in ("sudo", "doas"):
            i += 1
            while i < n and words[i].startswith("-"):
                i += 2 if words[i] in _SUDO_VAL else 1
        elif b == "env":
            i += 1
            while i < n and (words[i].startswith("-") or _ASSIGN.match(words[i])):
                i += 2 if words[i] in ("-u", "-C", "-S") else 1
        elif b == "command":
            i += 1
            while i < n and words[i].startswith("-"):
                if words[i] in ("-v", "-V"):
                    return None
                i += 1
        elif b in _WRAP_VAL:
            i += 1
            while i < n and words[i].startswith("-"):
                i += 2 if words[i] in _WRAP_VAL[b] else 1
        elif b in ("time", "nohup"):
            i += 1
            while i < n and words[i].startswith("-"):
                i += 1
        elif b == "timeout":
            i += 1
            while i < n and words[i].startswith("-"):
                i += 2 if words[i] in ("-s", "-k") else 1
            i += 1  # duracion
        else:
            return b, words[i + 1:]
    return None


GIT_MUTATING = {
    "add", "commit", "push", "pull", "merge", "rebase", "reset", "checkout", "switch",
    "restore", "clean", "rm", "mv", "apply", "am", "cherry-pick", "revert", "init", "clone",
    "gc", "prune", "update-ref", "update-index", "filter-branch",
    "replace", "read-tree", "checkout-index", "write-tree", "commit-tree", "maintenance",
    "repack", "pack-refs", "mergetool", "prune-packed", "unpack-objects", "fast-import",
    "update-server-info",
}
_LFS_READ_SUBS = {"ls-files", "status", "env", "version", "locks"}
_GIT_OPT_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix",
                  "--config-env"}
_BRANCH_MUT_LONG = {"--delete", "--move", "--copy", "--set-upstream-to", "--unset-upstream",
                    "--edit-description"}
_BRANCH_VALUE_OPTS = {"--contains", "--no-contains", "--merged", "--no-merged", "--points-at",
                      "--sort", "--format", "--abbrev"}
_CONFIG_MUT_OPTS = {"--unset", "--unset-all", "--add", "--replace-all", "--edit", "-e",
                    "--rename-section", "--remove-section"}
_CONFIG_GET_OPTS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--get-color",
                    "--get-colorbool", "-l", "--list"}
_CONFIG_VALUE_OPTS = {"-f", "--file", "--blob", "--default", "--type", "--comment"}
_CONFIG_MUT_SUBS = {"set", "unset", "edit", "rename-section", "remove-section"}
_TAG_MUT_LONG = {"--delete", "--force", "--annotate", "--sign", "--local-user", "--message",
                 "--file"}
_TAG_VALUE_LONG = {"--contains", "--no-contains", "--points-at", "--merged", "--no-merged",
                   "--sort", "--format"}
_TAG_LIST_LONG = {"--contains", "--no-contains", "--points-at", "--merged", "--no-merged",
                  "--list"}

FILE_MUTATORS = {
    "rm", "rmdir", "mv", "cp", "touch", "mkdir", "chmod", "chown", "ln", "tee", "truncate",
    "dd", "install", "patch", "del", "erase", "rd", "ren", "move", "copy", "xcopy", "robocopy",
    "remove-item", "set-content", "add-content", "out-file", "new-item", "move-item",
    "copy-item", "rename-item", "clear-content", "unlink",
}
TEMP_OK = {"rm", "rmdir", "mkdir", "touch", "cp", "mv", "tee"}

_PKG_SUBS = {
    "npm": {"install", "i", "ci", "uninstall", "update", "link", "publish", "add", "rm", "un",
            "r", "up", "it", "remove", "unlink", "upgrade", "udpate", "in", "ins", "inst",
            "insta", "instal", "isnt", "isnta", "isntal", "isntall", "clean-install", "ic",
            "install-clean", "isntall-clean", "install-test", "install-ci-test", "cit"},
    "yarn": {"add", "remove", "install", "upgrade", "up"},
    "pnpm": {"add", "remove", "install", "update", "i", "rm", "up", "uninstall", "un",
             "upgrade"},
    "apt": {"install", "remove", "upgrade", "uninstall", "purge", "dist-upgrade", "autoremove"},
    "apt-get": {"install", "remove", "upgrade", "uninstall", "purge", "dist-upgrade",
                "autoremove"},
    "brew": {"install", "remove", "upgrade", "uninstall"},
    "choco": {"install", "remove", "upgrade", "uninstall"},
    "winget": {"install", "remove", "upgrade", "uninstall"},
    "scoop": {"install", "remove", "upgrade", "uninstall"},
}
# Opciones de los gestores de paquetes que consumen el valor siguiente.
_PKG_VALUE_OPTS = {
    "npm": {"--prefix", "--workspace", "-w", "--registry", "--userconfig", "--cache",
            "--loglevel"},
    "pnpm": {"-C", "--dir", "--filter", "-F", "--workspace-dir", "--registry", "--loglevel"},
    "yarn": {"--cwd", "--registry", "--proxy", "--https-proxy", "--modules-folder",
             "--cache-folder", "--link-folder", "--global-folder", "--mutex",
             "--network-concurrency", "--network-timeout", "--otp", "--use-yarnrc"},
}
_PIP = r"pip[0-9.]*"
_NULL_TARGETS = {"/dev/null", "nul", "/dev/stderr", "/dev/stdout", "/dev/tty"}
MAX_COMMAND_LEN = 100000


def _positional(args):
    out = []
    dashdash = False
    for a in args:
        if dashdash:
            out.append(a)
        elif a == "--":
            dashdash = True
        elif a.startswith("-") and a != "-":
            continue
        else:
            out.append(a)
    return out


def _split_opts(args, value_opts=()):
    """Separa (opciones, posicionales); las opciones de value_opts consumen el valor."""
    opts = []
    pos = []
    dd = False
    k = 0
    while k < len(args):
        a = args[k]
        if dd:
            pos.append(a)
        elif a == "--":
            dd = True
        elif a.startswith("-") and a != "-":
            opts.append(a)
            if a in value_opts:
                k += 1
        else:
            pos.append(a)
        k += 1
    return opts, pos


def _is_temp(path, allow_dir=False):
    """allow_dir=True acepta tambien el directorio temporal exacto (destino de cp/mv)."""
    if ".." in path or _SUB in path:
        return False
    p = path.replace("\\", "/").lower()
    prefixes = ["/tmp/", "/var/tmp/", "$tmpdir/", "$temp/", "$tmp/", "${tmpdir}/",
                "${temp}/", "${tmp}/", "%temp%/", "%tmp%/"]
    for var in ("TMPDIR", "TEMP", "TMP"):
        val = os.environ.get(var)
        if val:
            v = val.replace("\\", "/").lower().rstrip("/") + "/"
            if len(v) > 1:
                prefixes.append(v)
    for pre in prefixes:
        if p.startswith(pre) and len(p) > len(pre):
            return True
        if allow_dir and p.rstrip("/") == pre[:-1]:
            return True
    marker = "/appdata/local/temp/"
    k = p.find(marker)
    if k != -1 and len(p) > k + len(marker):
        return True
    return allow_dir and p.rstrip("/").endswith(marker[:-1])


def _extract_target(args):
    """Devuelve (destino de -t/--target-directory o None, args restantes)."""
    target = None
    rest = []
    k = 0
    n = len(args)
    while k < n:
        a = args[k]
        if a == "--":
            rest.extend(args[k:])
            break
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            if _is_long_prefix(name, "--target-directory"):
                if eq:
                    target = val
                elif k + 1 < n:
                    target = args[k + 1]
                    k += 1
                else:
                    rest.append(a)
            else:
                rest.append(a)
            k += 1
            continue
        found, val, consumed = _short_option_value(args, k, "t", "S")
        if found and (val is not None):
            target = val
            k += 1 + consumed
            continue
        rest.append(a)
        k += 1
    return target, rest


def _is_long_prefix(name, full, minlen=3):
    """True si name es el nombre largo `full` o un prefijo suyo (abreviatura GNU)."""
    return len(name) >= minlen and full.startswith(name)


def _short_option_value(args, k, letter, stops=""):
    """Busca la opcion corta `letter` en un cumulo `-abc` (args[k]).

    `stops` son letras que consumen el resto del cumulo como valor propio (se deja de
    mirar). Devuelve (encontrada, valor, args_extra_consumidos); el valor es el resto del
    cumulo o, si no hay, el argumento siguiente (None si falta).
    """
    a = args[k]
    if not a.startswith("-") or a.startswith("--") or len(a) < 2:
        return False, None, 0
    for idx in range(1, len(a)):
        ch = a[idx]
        if ch == letter:
            if idx + 1 < len(a):
                return True, a[idx + 1:], 0
            if k + 1 < len(args):
                return True, args[k + 1], 1
            return True, None, 0
        if ch in stops:
            break
    return False, None, 0


def _is_null_target(t):
    """Destinos de salida inocuos: `-`, nul, /dev/null, /dev/stdout, /dev/stderr, /dev/tty, /dev/fd/N."""
    return t == "-" or t.lower() in _NULL_TARGETS or re.fullmatch(r"/dev/fd/\d+", t) is not None


def _git_reason(args):
    i = 0
    while i < len(args):
        a = args[i]
        if a in _GIT_OPT_VALUE:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            break
    if i >= len(args):
        return None
    sub = args[i]
    rest = args[i + 1:]
    msg = "'git %s' modifica el repositorio." % sub
    if sub in GIT_MUTATING:
        return msg
    if any(a == "--output" or a.startswith("--output=") for a in rest):
        return "'git %s --output' escribe un archivo." % sub
    if sub == "stash":
        return None if rest and rest[0] in ("list", "show") else msg
    if sub == "tag":
        pos = False
        implied = False
        k = 0
        while k < len(rest):
            a = rest[k]
            if a == "--":
                pos = pos or k + 1 < len(rest)
                break
            if a.startswith("--"):
                name = a.split("=", 1)[0]
                if name in _TAG_MUT_LONG:
                    return msg
                if name in _TAG_LIST_LONG or name == "--verify":
                    implied = True
                if name in _TAG_VALUE_LONG and "=" not in a:
                    k += 1
            elif a.startswith("-") and len(a) > 1:
                if a.startswith("-n"):
                    implied = True
                else:
                    if any(ch in "dasufmF" for ch in a[1:]):
                        return msg
                    if "l" in a[1:] or "v" in a[1:]:
                        implied = True
            else:
                pos = True
            k += 1
        return msg if pos and not implied else None
    if sub == "hash-object":
        for a in rest:
            if a == "--":
                break
            if a.startswith("-") and not a.startswith("--") and "w" in a[1:]:
                return msg
        return None
    if sub == "rerere":
        _, pos = _split_opts(rest)
        return None if pos and pos[0] in ("status", "diff", "remaining") else msg
    if sub == "lfs":
        _, pos = _split_opts(rest)
        return msg if pos and pos[0] not in _LFS_READ_SUBS else None
    if sub == "worktree":
        return None if rest and rest[0] == "list" else msg
    if sub == "config":
        opts, pos = _split_opts(rest, _CONFIG_VALUE_OPTS)
        names = [o.split("=", 1)[0] for o in opts]
        if any(nm in _CONFIG_MUT_OPTS for nm in names):
            return msg
        if any(nm in _CONFIG_GET_OPTS for nm in names):
            return None
        if pos and pos[0] in _CONFIG_MUT_SUBS:
            return msg
        if pos and pos[0] in ("get", "list"):
            return None
        return msg if len(pos) >= 2 else None
    if sub == "remote":
        if not rest or rest[0] in ("-v", "--verbose", "show", "get-url"):
            return None
        return msg
    if sub == "submodule":
        _, pos = _split_opts(rest)
        return None if not pos or pos[0] in ("status", "summary") else msg
    if sub == "bisect":
        _, pos = _split_opts(rest)
        return None if pos and pos[0] in ("log", "visualize", "view") else msg
    if sub == "format-patch":
        return None if "--stdout" in rest else msg
    if sub == "archive":
        if any(a == "-o" or (a.startswith("-o") and not a.startswith("--")) for a in rest):
            return "'git archive -o' escribe un archivo."
        return None
    if sub == "notes":
        _, pos = _split_opts(rest, {"--ref"})
        return None if not pos or pos[0] in ("list", "show", "get-ref") else msg
    if sub == "sparse-checkout":
        _, pos = _split_opts(rest)
        return None if pos and pos[0] == "list" else msg
    if sub == "reflog":
        _, pos = _split_opts(rest)
        return msg if pos and pos[0] in ("expire", "delete") else None
    if sub == "symbolic-ref":
        opts, pos = _split_opts(rest, {"-m"})
        if any(o in ("-d", "--delete", "-m") for o in opts) or len(pos) >= 2:
            return msg
        return None
    if sub == "bundle":
        _, pos = _split_opts(rest)
        return None if pos and pos[0] in ("verify", "list-heads") else msg
    if sub == "branch":
        listing = False
        k = 0
        positional = False
        while k < len(rest):
            a = rest[k]
            if a in _BRANCH_VALUE_OPTS:
                k += 2
                continue
            if a.startswith("--"):
                name = a.split("=", 1)[0]
                if name in _BRANCH_MUT_LONG:
                    return msg
                if name == "--list":
                    listing = True
            elif a.startswith("-") and len(a) > 1:
                if any(ch in "dDmMcCu" for ch in a[1:]):
                    return msg
                if "l" in a[1:]:
                    listing = True
            else:
                positional = True
            k += 1
        if positional and not listing:
            return msg
        return None
    return None


def _inplace_editor(name, args):
    if name == "sed":
        stops = "efl"
    elif name == "perl":
        stops = "MmIeExF"
    else:
        return False
    for a in args:
        if a == "--":
            break
        if name == "sed" and (a == "--in-place" or a.startswith("--in-place=")):
            return True
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            k = 1
            while k < len(a):
                ch = a[k]
                if ch == "i":
                    return True
                if name == "perl" and ch in "l0":
                    k += 1  # -l y -0 consumen solo digitos octales
                    while k < len(a) and a[k] in "01234567":
                        k += 1
                    continue
                if ch in stops:
                    break
                k += 1
    return False


def _output_option_reason(name, args):
    """sort -o, curl -o/-O y wget escriben archivos aunque no sean 'mutadores' clasicos."""
    if name == "sort":
        vals, _ = _output_values(args, "o", "--output", "kStT")
        if any(not _is_null_target(v) for v in vals):
            return "'sort -o' escribe un archivo."
    elif name == "curl":
        vals, flags = _output_values(args, "o", "--output", "AbcCdDeEFHKmPQrTuUwxXyYz", "O")
        if flags or "--remote-name" in args or "--remote-name-all" in args \
                or any(not _is_null_target(v) for v in vals):
            return "'curl' con -o/-O escribe un archivo."
    elif name == "wget":
        if "--spider" in args:
            return None
        vals, _ = _output_values(args, "O", "--output-document", "etTwUPiBlQoaDIXAR")
        if vals and all(_is_null_target(v) for v in vals):
            return None
        return ("'wget' escribe un archivo (solo se permite con -O -, -O /dev/null o "
                "--spider).")
    return None


def _output_values(args, letter, long_name, value_letters="", flag_letters=""):
    """Valores de la opcion de salida `letter` / `long_name` (con abreviaturas GNU).

    Devuelve (valores, hay_flag): hay_flag es True si aparece alguna opcion corta de
    `flag_letters` (p. ej. curl -O, que escribe sin valor). value_letters son opciones
    cortas que consumen el resto del cumulo o el argumento siguiente.
    """
    vals = []
    flag = False
    k = 0
    n = len(args)
    while k < n:
        a = args[k]
        if a == "--":
            break
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            if _is_long_prefix(name, long_name):
                if eq:
                    vals.append(val)
                elif k + 1 < n:
                    vals.append(args[k + 1])
                    k += 1
                else:
                    vals.append("")
        elif a.startswith("-") and len(a) > 1:
            for idx in range(1, len(a)):
                ch = a[idx]
                if ch == letter:
                    if idx + 1 < len(a):
                        vals.append(a[idx + 1:])
                    elif k + 1 < n:
                        vals.append(args[k + 1])
                        k += 1
                    else:
                        vals.append("")
                    break
                if ch in flag_letters:
                    flag = True
                elif ch in value_letters:
                    if idx + 1 == len(a):
                        k += 1  # el valor es el argumento siguiente
                    break
        k += 1
    return vals, flag


def _simple_reason(words, redirs, allow_temp):
    for op, target in redirs:
        if target.lower() in _NULL_TARGETS or re.fullmatch(r"/dev/fd/\d+", target):
            continue
        if allow_temp and _is_temp(target):
            continue
        extra = " Con --allow-temp solo se permite escribir bajo un directorio temporal." \
            if allow_temp else ""
        return "la redirección '%s %s' escribe un archivo.%s" % (op, target, extra)
    cw = _command_word(words)
    if cw is None:
        return None
    name, args = cw
    if name == "git":
        return _git_reason(args)
    if name in FILE_MUTATORS:
        if name == "tee" and all(_is_null_target(p) for p in _positional(args)):
            return None  # sin archivos, o solo /dev/null, `-`, /dev/stdout...
        if allow_temp and name in TEMP_OK:
            target = None
            if name in ("cp", "mv"):
                target, args = _extract_target(args)
            pos = _positional(args)
            if name == "tee":
                good = all(_is_temp(p) or _is_null_target(p) for p in pos)
            elif name == "cp":
                if target is not None:
                    good = bool(pos) and _is_temp(target, True)
                else:
                    good = len(pos) >= 2 and _is_temp(pos[-1], True)
            elif name == "mv":
                if target is not None:
                    good = bool(pos) and all(_is_temp(p) for p in pos) and _is_temp(target, True)
                else:
                    good = (len(pos) >= 2 and all(_is_temp(p) for p in pos[:-1])
                            and _is_temp(pos[-1], True))
            else:
                good = bool(pos) and all(_is_temp(p) for p in pos)
            if good:
                return None
            return ("'%s' escribe fuera de un directorio temporal (con --allow-temp solo se "
                    "permite bajo /tmp, $TMPDIR, %%TEMP%%, etc.)." % name)
        return "'%s' modifica archivos." % name
    if _inplace_editor(name, args):
        return "'%s' con edición en el lugar (-i) modifica archivos." % name
    r = _output_option_reason(name, args)
    if r:
        return r
    if name == "find":
        if "-delete" in args:
            return "'find -delete' borra archivos."
        for k, a in enumerate(args):
            if a in ("-exec", "-execdir", "-ok", "-okdir"):
                inner = []
                for b in args[k + 1:]:
                    if b in (";", "+"):
                        break
                    inner.append(b)
                r = _simple_reason(inner, [], allow_temp)
                if r:
                    return "'find %s' ejecuta un comando que modifica: %s" % (a, r)
        return None
    if re.fullmatch(_PIP, name):
        pos = _positional(args)
        if pos and pos[0] in ("install", "uninstall"):
            return "'%s %s' cambia el entorno." % (name, pos[0])
        return None
    if re.fullmatch(r"python[0-9.]*|py", name):
        for k, a in enumerate(args[:-1]):
            if a == "-m" and re.fullmatch(_PIP, args[k + 1]):
                pos = _positional(args[k + 2:])
                if pos and pos[0] in ("install", "uninstall"):
                    return "'%s -m pip %s' cambia el entorno." % (name, pos[0])
                return None
        return None
    if name in _PKG_SUBS:
        _, pos = _split_opts(args, _PKG_VALUE_OPTS.get(name, ()))
        if pos and pos[0] in _PKG_SUBS[name]:
            return "'%s %s' cambia el entorno." % (name, pos[0])
        if name == "npm" and pos:
            if pos[0] == "version" and len(pos) > 1:
                return "'npm version' cambia package.json y crea commits/tags."
            if pos[0] == "audit" and "fix" in pos[1:]:
                return "'npm audit fix' cambia el entorno."
        if name == "yarn" and not pos and not any(
                a in ("--version", "-v", "--help", "-h") for a in args):
            return "'yarn' sin subcomando instala dependencias (cambia el entorno)."
    return None


def _check_readonly(allow_temp, payload):
    if payload.get("tool_name") != "Bash":
        return None
    ti = payload.get("tool_input")
    command = ti.get("command") if isinstance(ti, dict) else None
    prefix = "Bloqueado por agent_guard (readonly): "
    if not isinstance(command, str):
        return prefix + "la llamada a Bash no trae un comando analizable."
    if len(command) > MAX_COMMAND_LEN:
        return (prefix + "el comando es demasiado largo para analizarlo de forma segura "
                "(%d caracteres; el máximo es %d)." % (len(command), MAX_COMMAND_LEN))
    try:
        cmds = parse_commands(command)
    except ParseError as e:
        return prefix + "no se pudo analizar el comando de forma segura (%s)." % e
    for words, redirs in cmds:
        r = _simple_reason(words, redirs, allow_temp)
        if r:
            return (prefix + r + " Este agente es de solo lectura; reportá el hallazgo en lugar "
                    "de aplicarlo.")
    return None


def check(mode, allow_temp, payload):
    """Devuelve el motivo del bloqueo (str) o None si se permite."""
    if mode == "tests-only":
        return _check_tests_only(payload)
    if mode == "readonly":
        return _check_readonly(allow_temp, payload)
    return "Bloqueado por agent_guard: modo desconocido '%s'." % mode


# ---------------------------------------------------------------------- main

def _fail(msg):
    try:
        sys.stderr.buffer.write((msg + "\n").encode("utf-8"))
        sys.stderr.buffer.flush()
    except Exception:
        pass
    return 2


def _main(argv):
    argv = sys.argv[1:] if argv is None else argv
    mode = None
    allow_temp = False
    for a in argv:
        if a == "--allow-temp":
            allow_temp = True
        elif mode is None:
            mode = a
        else:
            return _fail("Bloqueado por agent_guard: argumento inesperado '%s'. "
                         "Uso: agent_guard.py <tests-only|readonly> [--allow-temp]" % a)
    if mode not in MODES:
        return _fail("Bloqueado por agent_guard: modo desconocido o ausente (%r). "
                     "Uso: agent_guard.py <tests-only|readonly> [--allow-temp]" % mode)
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))  # quita el BOM
    except (ValueError, UnicodeDecodeError):
        return _fail("Bloqueado por agent_guard: la entrada no es JSON válido (falla cerrada).")
    if not isinstance(payload, dict):
        return _fail("Bloqueado por agent_guard: la entrada no es un objeto JSON (falla cerrada).")
    reason = check(mode, allow_temp, payload)
    if reason:
        return _fail(reason)
    return 0


def main(argv=None):
    """Punto de entrada: solo devuelve 0 o 2; cualquier excepcion falla cerrada."""
    try:
        return _main(argv)
    except SystemExit as e:
        if e.code in (0, 2):
            raise
        return _fail("Bloqueado por agent_guard: salida inesperada (código %r, falla cerrada)."
                     % (e.code,))
    except BaseException as e:  # incluye RecursionError y MemoryError
        return _fail("Bloqueado por agent_guard: error interno al evaluar (%s); falla cerrada."
                     % type(e).__name__)


if __name__ == "__main__":
    sys.exit(main())
