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
              directorios de pruebas se evaluan sobre la ruta relativa a `cwd`.
              Una ruta ABSOLUTA fuera de `cwd` (o sin `cwd`) solo vale si es
              temporal (ademas de parecer de pruebas por nombre). Nunca se escribe
              bajo `.git`, `.github`, `.claude`, `.husky`, `.vscode`, `.idea`,
              `.venv`, `venv`, `site-packages` ni `node_modules`, ni en segmentos
              con `~` (nombres 8.3), ni en segmentos `.`+glob (`.?`, `.*`: con
              bash < 5.2 coinciden con `..`).
              Bash: aplica todas las reglas de `readonly` con --allow-temp, y
              ademas permite escribir (redirecciones, rm/rmdir/mkdir/touch/cp/mv/
              tee) en rutas de pruebas segun el mismo criterio. Esas rutas no
              pueden llevar `..`, `$`, `~`, `%`, `{}`, `[`, `]`, barra invertida ni
              sustituciones (usar `/`), ni `C:x`, y las absolutas deben estar
              bajo `cwd`. Con cd/pushd/popd/chdir, env -C, sudo -D o find
              -execdir en el comando, o sin `cwd` valido, solo cuenta el
              directorio temporal. cp -l/-s queda bloqueado. `trap` esta prohibido.
              Tambien estan prohibidos `hash`, `enable`, `flock`, `watch`, `strace`,
              `ltrace`, `ssh-agent` y `chroot`, y los prefijos de asignacion `GIT_*`,
              PAGER, LESSOPEN, LESSCLOSE, TAPE, PATH, BASH_ENV, ENV, LD_PRELOAD y
              `*EDITOR`/`*VISUAL` (hacen que un comando inocuo ejecute otro).

              MODO ESTRICTO (solo tests-only + Bash, antes de analizar el comando): el
              parser que imita a bash y bash divergen en `[[`, `((`, comentarios dentro de
              `$( )`, backticks anidados, `\\<newline>`, heredocs, etc.; cuatro rondas de
              parches siguieron dejando huecos. En lugar de emular esa sintaxis, se FALLA
              CERRADO ante ella (`_strict_syntax_reason`, exit 2). Con estado de comillas:
              dentro de comillas simples todo es literal. Fuera de comillas simples (incluidas
              las dobles) se rechaza `$` (cualquier forma), backtick y `\\` (salvo la palabra
              exacta `\\;` de `find -exec`). Fuera de todas las comillas se rechaza `(` `)`,
              `{` `}` (salvo la palabra `{}`), `[[`, `[` y `]` dentro de una palabra (globs;
              solo valen como palabra suelta, el comando `[`), `<<` y `<<<` (heredoc,
              here-string), `<(` y `>(`, saltos de linea, `#` al inicio de palabra
              (comentarios) y `&` salvo `&&`, `&>`, `&>>`, `>&`, `2>&1`, y bytes NUL o de control (``-``, salvo
              tabulador y saltos de linea, que ya se rechazan aparte). Se permiten palabras
              simples, comillas sin `$`/backtick/`\\`, `|`, `||`, `&&`, `;`, redirecciones
              `>` `>>` `2>` `&>` `<`, `*` y `?`. `readonly` NO usa el modo estricto.
  readonly    Bash sin comandos que modifiquen repo, archivos o entorno.
              --allow-temp permite rm/rmdir/mkdir/touch/cp/mv/tee y redirecciones
              cuando todas las rutas estan bajo un directorio temporal.
              En ambos modos `git -c` y `git --config-env` estan bloqueados (inyectan
              alias, core.fsmonitor, diff.external...), igual que `git difftool` y
              `git grep -O`; `sed` con `e`/`s///e`, `awk -i inplace`, `ruby -i`, `xxd -r`
              con salida, `certutil`, `split`/`csplit`, `cpio`, `ar x`, `ex`/`ed`,
              `vim -s` y `openssl enc -out` tambien. `mktemp` se permite sin plantilla o
              con destino temporal (solo con --allow-temp).

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
# Carpetas donde nunca se escribe aunque el nombre del archivo parezca de pruebas.
NON_TEST_DIRS = {".git", ".github", ".venv", "venv", "site-packages", "node_modules",
                 ".claude", ".husky", ".vscode", ".idea"}
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


def _dot_glob(path):
    """True si algun segmento de la ruta empieza por `.` y lleva `*` o `?`: con bash < 5.2 (o
    `shopt -u globskipdots`) `.?` y `.*` coinciden con `..` y la ruta se sale del arbol."""
    return any(seg.startswith(".") and ("*" in seg or "?" in seg)
               for seg in path.replace("\\", "/").split("/"))


def is_test_path(path, cwd=None):
    raw_parts = path.replace("\\", "/").split("/")
    if ".." in raw_parts:
        return False
    if ":" in re.sub(r"^[A-Za-z]:", "", path):
        return False  # flujos NTFS (`app.py:x_test.py`): el nombre real es otro
    p = _norm_path(path)
    all_segs = p.split("/")[:-1]
    if _is_abs(p):
        dir_segs = []
        if isinstance(cwd, str) and cwd.strip():
            c = _norm_path(cwd).rstrip("/")
            if _is_abs(c) and p.startswith(c + "/"):
                dir_segs = p[len(c) + 1:].split("/")[:-1]
                all_segs = dir_segs  # los ancestros del cwd no cuentan
    else:
        dir_segs = all_segs
    if any(seg in NON_TEST_DIRS for seg in all_segs):
        return False  # los patrones de nombre no valen dentro de CI, venv, node_modules ni .git
    if any("~" in seg for seg in all_segs) or "~" in p.rsplit("/", 1)[-1]:
        return False  # nombres 8.3 (`GITHUB~1` es `.github`): el nombre real es otro
    if p.rsplit("/", 1)[-1] == ".git":
        return False  # `tests/.git` (archivo o directorio): git trataria la carpeta como repo
    if any(seg in TEST_DIRS for seg in dir_segs):
        return True
    base = p.rsplit("/", 1)[-1]
    if any(fnmatch.fnmatchcase(base, pat) for pat in TEST_FILE_PATTERNS):
        return True
    return any(fnmatch.fnmatchcase(raw_parts[-1], pat) for pat in TEST_FILE_PATTERNS_CS)


def _inside_cwd_or_relative(path, cwd):
    """True si la ruta es relativa o absoluta bajo `cwd`. Una absoluta fuera de `cwd` (o sin
    `cwd` valido) devuelve False: en Write/Edit solo puede valer si es temporal."""
    p = _norm_path(path)
    if not _is_abs(p):
        return True
    if isinstance(cwd, str) and cwd.strip():
        c = _norm_path(cwd).rstrip("/")
        return _is_abs(c) and p.startswith(c + "/")
    return False


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
    cwd = payload.get("cwd")
    if is_test_path(path, cwd):
        if _inside_cwd_or_relative(path, cwd) or _is_temp(path.replace("\\", "/")):
            return None
        return ("Bloqueado por agent_guard (tests-only): '%s' está fuera del directorio de "
                "trabajo (o no hay cwd) y no es temporal. Fuera de cwd solo se escribe bajo el "
                "directorio temporal; reportá el cambio necesario en lugar de aplicarlo." % path)
    return ("Bloqueado por agent_guard (tests-only): '%s' no es un archivo de pruebas. "
            "Este agente solo escribe en tests (carpetas tests/, fixtures/, e2e/, archivos "
            "test_*.py, *.spec.*, etc.); reportá el cambio necesario en el código en lugar de aplicarlo."
            % path)


# ------------------------------------------------------------------ readonly

class ParseError(Exception):
    pass


_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")
_SUB = "$(sub)"
_MAX_DEPTH = 20
_WORD_END = " \t\n;&|<>()"


_ANSI_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n",
                "r": "\r", "t": "\t", "v": "\v", "'": "'", "\\": "\\", '"': '"'}


def _ansi_text(inner):
    """Decodifica el contenido de $'...'. Solo los escapes simples (\\a \\b \\e \\E \\f \\n \\r
    \\t \\v y \\' \\" \\\\); \\xNN, octal, \\u, \\U, \\c y cualquier otro fallan cerrado."""
    out = []
    k = 0
    n = len(inner)
    while k < n:
        ch = inner[k]
        if ch != "\\":
            out.append(ch)
            k += 1
            continue
        esc = inner[k + 1:k + 2]
        if not esc or esc not in _ANSI_SIMPLE:
            raise ParseError("secuencia de escape en $'...' que no se puede analizar")
        out.append(_ANSI_SIMPLE[esc])
        k += 2
    return "".join(out)


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
            out.append(_ansi_text(s[k + 2:e - 1]))
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
    quoted = False  # la palabra en curso lleva comillas o escapes
    pending = None  # (op, es_salida)
    heredocs = []
    arith_failed = False
    i = 0
    n = len(cmd)

    def end_word():
        nonlocal buf, in_word, pending, quoted
        quoted = False
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
            elif nxt:
                buf.append(nxt)  # como bash: `\x` -> `x`
                in_word = True
                quoted = True
                i += 2
            else:
                buf.append("\\")
                in_word = True
                quoted = True
                i += 1
            continue
        if c == "'":
            j = cmd.find("'", i + 1)
            if j == -1:
                raise ParseError("comilla simple sin cerrar")
            buf.append(cmd[i + 1:j])
            in_word = True
            quoted = True
            i = j + 1
            continue
        if c == "$" and nxt == '"':
            i += 1  # $"..." (traduccion de locale): se descarta el `$`; la comilla se procesa
            continue
        if c == "$" and nxt == "'":
            k = _skip_ansi(cmd, i)
            if k == -1:
                raise ParseError("comilla $'...' sin cerrar")
            buf.append(_ansi_text(cmd[i + 2:k - 1]))
            in_word = True
            quoted = True
            i = k
            continue
        if c == '"':
            in_word = True
            quoted = True
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
            # sin cierre: bash tambien falla; no se re-escanea en cada `$[` (costo cuadratico)
            raise ParseError("aritmética $[ sin cerrar")
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
            if in_word and pending is None and not quoted and "".join(buf).isdigit():
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
# Opciones largas con valor por envoltorio (se aceptan abreviaturas GNU y `--opt=valor`).
_WRAP_LONG_VAL = {
    "nice": ("--adjustment",),
    "ionice": ("--class", "--classdata", "--pid", "--pgid", "--uid"),
    "stdbuf": ("--input", "--output", "--error"),
    "timeout": ("--signal", "--kill-after"),
    "sudo": ("--user", "--group", "--host", "--prompt", "--role", "--type", "--close-from",
             "--other-user", "--login-class", "--command-timeout", "--chroot"),
}
_WRAP_LONG_VAL["doas"] = _WRAP_LONG_VAL["sudo"]


def _long_takes_value(wrapper, opt):
    """True si la opcion larga `opt` (sin `=`) de `wrapper` consume el argumento siguiente."""
    return any(_is_long_prefix(opt, full) for full in _WRAP_LONG_VAL.get(wrapper, ()))


def _sudo_chdir(opt):
    """(es_chdir, consume_siguiente) para una opcion de sudo/doas."""
    if opt.startswith("--"):
        name, eq, _ = opt.partition("=")
        if _is_long_prefix(name, "--chdir", 5):
            return True, not eq
        return False, False
    for idx in range(1, len(opt)):
        ch = opt[idx]
        if ch == "D":
            return True, idx + 1 == len(opt)
        if ch in "ugphcdrtUCRT":
            break  # consume el resto del cumulo como valor
    return False, False


def _sudo_takes_value(opt):
    """True si la corta (o cumulo) `opt` de sudo/doas termina en una letra con valor y este es
    el argumento siguiente (`-u root`, `-iu root`); en `-uroot` el valor va pegado."""
    for idx in range(1, len(opt)):
        if opt[idx] in "ugphcdrtUCRT":
            return idx + 1 == len(opt)
    return False


def _env_opt(opt):
    """(tipo, consume_siguiente) para una opcion de env.

    tipo: "chdir" (-C/--chdir), "split" (-S/--split-string: ejecuta un texto que no se puede
    analizar), "value" (otra opcion con valor) o None.
    """
    if opt.startswith("--"):
        name, eq, _ = opt.partition("=")
        if _is_long_prefix(name, "--chdir"):
            return "chdir", not eq
        if _is_long_prefix(name, "--split-string"):
            return "split", not eq
        if _is_long_prefix(name, "--unset") or _is_long_prefix(name, "--argv0"):
            return "value", not eq
        return None, False
    for idx in range(1, len(opt)):
        ch = opt[idx]
        if ch == "C":
            return "chdir", idx + 1 == len(opt)
        if ch == "S":
            return "split", idx + 1 == len(opt)
        if ch in "ua":
            return "value", idx + 1 == len(opt)
    return None, False


def _skip_opts(words, i, wrapper, short_val=()):
    """Salta las opciones de un envoltorio desde words[i]; devuelve el indice siguiente.

    Un `--` termina las opciones. Las cortas de short_val y las largas de _WRAP_LONG_VAL
    consumen el argumento siguiente.
    """
    n = len(words)
    while i < n and words[i].startswith("-"):
        w = words[i]
        if w == "--":
            return i + 1
        if w.startswith("--"):
            i += 2 if "=" not in w and _long_takes_value(wrapper, w) else 1
        else:
            i += 2 if w in short_val else 1
    return i


def _assign_name(w):
    return re.match(r"[A-Za-z_][A-Za-z0-9_]*", w).group()


def _command_word(words, info=None):
    """Salta asignaciones y envoltorios. Devuelve (nombre, args) o None.

    info: dict opcional; se le pone info["chdir"] = True si un envoltorio cambia de
    directorio (env -C/--chdir, sudo/doas -D/--chdir). Lanza ParseError con `env -S`.
    """
    i = 0
    n = len(words)
    assigns = info.setdefault("assign", []) if info is not None else []
    while i < n:
        w = words[i]
        if _ASSIGN.match(w):
            assigns.append(_assign_name(w))
            i += 1
            continue
        b = _base(w)
        if b == "function":
            i += 2  # `function NAME {`: el nombre no es el comando
        elif b in _KEYWORDS:
            i += 1
        elif b == "coproc":
            i += 1
            if (i + 1 < n and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", words[i])
                    and words[i + 1] == "{"):
                i += 1  # `coproc NAME { ...; }`
        elif b == "builtin":
            i += 1
            if i < n and words[i] == "--":
                i += 1
        elif b in ("sudo", "doas"):
            i += 1
            while i < n and words[i].startswith("-"):
                if words[i] == "--":
                    i += 1
                    break
                is_cd, takes = _sudo_chdir(words[i])
                if is_cd and info is not None:
                    info["chdir"] = True
                if is_cd:
                    i += 2 if takes else 1
                elif words[i].startswith("--"):
                    i += 2 if "=" not in words[i] and _long_takes_value(b, words[i]) else 1
                else:
                    i += 2 if _sudo_takes_value(words[i]) else 1
        elif b == "env":
            i += 1
            while i < n and (words[i].startswith("-") or _ASSIGN.match(words[i])):
                if words[i] == "--":
                    i += 1
                    continue
                if words[i].startswith("-"):
                    kind, takes = _env_opt(words[i])
                    if kind == "split":
                        raise ParseError("env -S/--split-string ejecuta un texto que no se "
                                         "puede analizar")
                    if kind == "chdir" and info is not None:
                        info["chdir"] = True
                    i += 2 if takes else 1
                else:
                    if _ASSIGN.match(words[i]):
                        assigns.append(_assign_name(words[i]))
                    i += 1
        elif b == "command":
            i += 1
            while i < n and words[i].startswith("-"):
                if words[i] in ("-v", "-V"):
                    return None
                if words[i] == "--":
                    i += 1
                    break
                i += 1
        elif b in _WRAP_VAL:
            i = _skip_opts(words, i + 1, b, _WRAP_VAL[b])
        elif b in ("time", "nohup", "winpty"):
            i += 1
            while i < n and words[i].startswith("-"):
                i += 1
        elif b == "timeout":
            i = _skip_opts(words, i + 1, b, ("-s", "-k"))
            i += 1  # duracion
        else:
            return b, words[i + 1:]
    return None


GIT_MUTATING = {
    "add", "commit", "push", "pull", "merge", "rebase", "reset", "checkout", "switch",
    "restore", "clean", "rm", "mv", "apply", "am", "cherry-pick", "revert", "init", "clone",
    "gc", "prune", "update-ref", "update-index", "filter-branch",
    "stage", "replace", "read-tree", "checkout-index", "write-tree", "commit-tree", "maintenance",
    "repack", "pack-refs", "mergetool", "prune-packed", "unpack-objects", "fast-import",
    "update-server-info", "difftool", "merge-file",
}
_LFS_READ_SUBS = {"ls-files", "status", "env", "version", "locks"}
_GIT_OPT_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix",
                  "--config-env", "--attr-source"}
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
    "copy-item", "rename-item", "clear-content", "unlink", "shred", "rsync", "scp",
    "link", "mkfifo", "mknod", "mktemp", "dos2unix", "unix2dos",
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
# Opciones globales de pip que consumen el valor siguiente.
_PIP_VALUE_OPTS = {"--proxy", "--cache-dir", "--log", "--retries", "--timeout",
                   "--exists-action", "--trusted-host", "--cert", "--client-cert", "--python",
                   "--use-feature", "--use-deprecated", "--keyring-provider",
                   "--resume-retries"}
_MAX_EXEC_DEPTH = 20  # niveles de find -exec/-ok anidados
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
    if "\\" in path:
        return False  # bash elimina `\` delante de casi todo: usar `/`
    path = re.sub(r"^\$\{(TMPDIR|TEMP|TMP)\}", r"$\1", path)
    if ".." in path or _SUB in path or "{" in path or "}" in path:
        return False  # las llaves se expanden en bash: `rm {a,/tmp/b}`
    if _dot_glob(path):
        return False  # `.?` / `.*` pueden coincidir con `..`
    # las variables distinguen mayusculas (`$tmp` esta vacia en bash); en Git Bash `$TEMP`/`$TMP`
    # tambien pueden estar vacias (limitacion conocida)
    for pre in ("$TMPDIR/", "$TEMP/", "$TMP/"):
        if path.startswith(pre) and len(path) > len(pre):
            return True
        if allow_dir and path.rstrip("/") == pre[:-1]:
            return True
    p = path.replace("\\", "/").lower()
    prefixes = ["/tmp/", "/var/tmp/"]
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
    # el temporal de Windows solo vale anclado: `<unidad>/users/<usuario>/appdata/local/temp`
    np = _norm_path(path)
    m = re.match(r"^[a-z]:/users/[^/]+/appdata/local/temp/", np)
    if m and len(np) > m.end():
        return True
    return allow_dir and re.fullmatch(
        r"[a-z]:/users/[^/]+/appdata/local/temp", np.rstrip("/")) is not None


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
        if a == "-c" or a == "--config-env" or a.startswith("--config-env="):
            return ("'git -c/--config-env' inyecta configuración (alias con `!`, "
                    "core.fsmonitor, diff.external, etc.) que ejecuta comandos.")
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
    if sub == "grep":
        for a in rest:
            if a == "--":
                break
            if (a.startswith("--") and _is_long_prefix(a.partition("=")[0],
                                                          "--open-files-in-pager", 4)) \
                    or (not a.startswith("--") and a.startswith("-")
                        and _short_cluster_has(a, "O", "efABCm")):
                return "'git grep -O/--open-files-in-pager' ejecuta un comando."
        return None
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
    elif name == "ruby":
        stops = "eIrCxFE"
    else:
        return False
    for a in args:
        if a == "--":
            break
        if name == "sed" and a.startswith("--") \
                and _is_long_prefix(a.partition("=")[0], "--in-place"):
            return True  # `--i` y cualquier abreviatura GNU de --in-place
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            k = 1
            while k < len(a):
                ch = a[k]
                if ch == "i":
                    return True
                if name in ("perl", "ruby") and ch in "l0":
                    k += 1  # -l y -0 consumen solo digitos octales
                    while k < len(a) and a[k] in "01234567":
                        k += 1
                    continue
                if ch in stops:
                    break
                k += 1
    return False


_SED_STD_OUT = ("/dev/stdout", "/dev/stderr")


def _sed_scripts(args):
    """Textos de script de sed: los de -e/--expression o, sin ellos ni -f, el primer posicional."""
    scripts = []
    pos = []
    has_opt = False
    k = 0
    n = len(args)
    while k < n:
        a = args[k]
        if a == "--":
            pos.extend(args[k + 1:])
            break
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            if _is_long_prefix(name, "--expression"):
                has_opt = True
                if eq:
                    scripts.append(val)
                elif k + 1 < n:
                    scripts.append(args[k + 1])
                    k += 1
            elif _is_long_prefix(name, "--file"):
                has_opt = True
                k += 0 if eq else 1
            elif _is_long_prefix(name, "--line-length") and not eq:
                k += 1
        elif a.startswith("-") and len(a) > 1:
            for idx in range(1, len(a)):
                ch = a[idx]
                if ch in "ef":
                    has_opt = True
                    if idx + 1 < len(a):
                        val = a[idx + 1:]
                    else:
                        val = args[k + 1] if k + 1 < n else None
                        k += 1
                    if ch == "e" and val is not None:
                        scripts.append(val)
                    break
                if ch == "l":
                    if idx + 1 == len(a):
                        k += 1
                    break
                if ch == "i":
                    break  # el resto es el sufijo
        else:
            pos.append(a)
        k += 1
    if not has_opt and pos:
        scripts.append(pos[0])
    return scripts


def _sed_script_writes(script):
    """True si el script de sed tiene un comando `w`/`W` o un flag `w` de `s` cuyo archivo
    no es /dev/stdout ni /dev/stderr, o ejecuta shell (comando `e`, flag `e` de `s`). Analisis
    heuristico de comandos, direcciones y s/y."""
    n = len(script)
    i = 0

    def line_end(j):
        e = script.find("\n", j)
        return n if e == -1 else e

    def skip_delim(j, d):
        while j < n:
            if script[j] == "\\":
                j += 2
            elif script[j] == d:
                return j + 1
            else:
                j += 1
        return n

    while i < n:
        c = script[i]
        if c in " \t\n;{}":
            i += 1
            continue
        while i < n:  # direcciones: 1, $, 1~2, +N, /re/, \cREc, `,` y `!`
            c = script[i]
            if c.isdigit() or c in "$~+,! \t":
                i += 1
            elif c == "/" or c == "\\":
                d = "/"
                if c == "\\":
                    i += 1
                    d = script[i] if i < n else "/"
                i = skip_delim(i + 1, d)
                while i < n and script[i] in "IM":
                    i += 1
            else:
                break
        if i >= n:
            break
        cmd = script[i]
        i += 1
        if cmd in "wW":
            e = line_end(i)
            if script[i:e].strip() not in _SED_STD_OUT:
                return True
            i = e
        elif cmd == "s" and i < n:
            d = script[i]
            i = skip_delim(skip_delim(i + 1, d), d)
            while i < n and script[i] not in ";\n}#":
                if script[i] == "w":
                    e = line_end(i + 1)
                    if script[i + 1:e].strip() not in _SED_STD_OUT:
                        return True
                    i = e
                    break
                if script[i] == "e":
                    return True  # el flag `e` de s ejecuta el resultado como comando
                i += 1
        elif cmd == "e":
            return True  # el comando `e` ejecuta un comando de shell
        elif cmd == "y" and i < n:
            d = script[i]
            i = skip_delim(skip_delim(i + 1, d), d)
        elif cmd in "aic":
            j = i
            while True:  # texto hasta fin de linea; una `\` final lo continua
                e = line_end(j)
                if e < n and script[e - 1:e] == "\\":
                    j = e + 1
                else:
                    break
            i = e
        elif cmd == "r" or cmd == "R":
            i = line_end(i)
        elif cmd in ":bBtTlLqQ":
            while i < n and script[i] not in ";\n":
                i += 1
    return False


def _sed_writes_file(args):
    return any(_sed_script_writes(sc) for sc in _sed_scripts(args))


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


def _cp_link_option(args):
    """True si cp lleva -l/--link o -s/--symbolic-link (crean enlaces hacia el original)."""
    for k, a in enumerate(args):
        if a == "--":
            break
        if a.startswith("--"):
            name = a.partition("=")[0]
            if _is_long_prefix(name, "--link") or _is_long_prefix(name, "--symbolic-link"):
                return True
        elif a.startswith("-") and len(a) > 1:
            for ch in a[1:]:
                if ch in "ls":
                    return True
                if ch in "tS":
                    break  # el resto del cumulo es un valor
    return False


_TAR_VALUE_LETTERS = "bCfFgHIKLNTVX"  # opciones cortas de tar que consumen un valor
_COMPRESSORS = {"gzip", "gunzip", "bzip2", "bunzip2", "xz", "unxz", "zstd", "unzstd", "lz4",
                "unlz4"}


def _short_cluster_has(a, wanted, stops=""):
    """True si el cumulo corto `a` (`-abc`) contiene alguna letra de `wanted`; deja de
    mirar en la primera letra de `stops` (el resto del cumulo es su valor)."""
    for ch in a[1:]:
        if ch in wanted:
            return True
        if ch in stops:
            break
    return False


def _tar_scan(args):
    """Analiza las opciones de tar. Devuelve un dict: extract (-x/--extract/--get), create
    (-c -r -u -A, --delete y formas largas: escriben el archivo de -f), stdout (-O/--to-stdout),
    exec (--to-command), dirs (valores de -C/--directory) y files (valores de -f/--file)."""
    st = {"extract": False, "create": False, "stdout": False, "exec": False,
          "dirs": [], "files": []}
    k = 0
    n = len(args)
    while k < n:
        a = args[k]
        if a == "--":
            break
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            if _is_long_prefix(name, "--extract", 4) or _is_long_prefix(name, "--get", 4):
                st["extract"] = True
            elif (_is_long_prefix(name, "--create", 4) or _is_long_prefix(name, "--append", 4)
                    or _is_long_prefix(name, "--update", 4)
                    or _is_long_prefix(name, "--catenate", 5)
                    or _is_long_prefix(name, "--concatenate", 5)
                    or _is_long_prefix(name, "--delete", 5)):
                st["create"] = True
            elif _is_long_prefix(name, "--to-stdout", 6):
                st["stdout"] = True
            elif _is_long_prefix(name, "--to-command", 6):
                st["exec"] = True
            elif _is_long_prefix(name, "--file", 4) or _is_long_prefix(name, "--directory", 4):
                key = "files" if _is_long_prefix(name, "--file", 4) else "dirs"
                if eq:
                    st[key].append(val)
                else:
                    st[key].append(args[k + 1] if k + 1 < n else "")
                    k += 1
        elif (a.startswith("-") and len(a) > 1) or k == 0:
            old = not a.startswith("-")  # `tar cf out.tar x`: los valores van en orden
            letters = a if old else a[1:]
            idx = 0
            used = 0
            while idx < len(letters):
                ch = letters[idx]
                idx += 1
                if ch in "cruA":
                    st["create"] = True
                elif ch == "x":
                    st["extract"] = True
                elif ch == "O":
                    st["stdout"] = True
                elif ch in _TAR_VALUE_LETTERS:
                    # estilo antiguo (`fx`): las letras con valor no consumen el resto del cumulo
                    if not old and idx < len(letters):
                        val = letters[idx:]
                        idx = len(letters)
                    else:
                        j = k + 1 + used
                        val = args[j] if j < n else ""
                        used += 1
                    if ch == "f":
                        st["files"].append(val)
                    elif ch == "C":
                        st["dirs"].append(val)
            k += used
        k += 1
    return st


def _tar_reason(args, dest_ok, dir_ok):
    """tar: extraer (salvo a stdout con -O), -C/--directory (salvo a un directorio temporal) y
    escribir el archivo de -f (crear, añadir, --delete) solo si el destino lo permite."""
    st = _tar_scan(args)
    msg = "'tar' con -x/--extract o -C/--directory escribe archivos."
    if st["exec"] or (st["extract"] and not st["stdout"]):
        return msg
    for d in st["dirs"]:
        if not (dir_ok is not None and dir_ok(d)):
            return msg
    if st["create"]:
        for f in st["files"]:
            if not (dest_ok is not None and dest_ok(f)):
                return ("'tar' al crear, añadir o borrar escribe el archivo '%s': solo se "
                        "permite `-f -` o un destino temporal o de pruebas." % f)
    return None


_SPLIT_VALUE_OPTS = {"-a", "-b", "-l", "-n", "-C", "-t", "--bytes", "--lines", "--line-bytes",
                     "--number", "--suffix-length", "--separator", "--additional-suffix"}
_XXD_VALUE_OPTS = {"-c", "-g", "-l", "-o", "-s", "-n", "-R", "-cols", "-groupsize", "-len",
                   "-offset", "-seek"}


def _mktemp_reason(args, allow_temp, ok):
    """mktemp crea un archivo: sin plantilla (usa el directorio temporal) o con destino
    temporal se permite (solo con --allow-temp); la plantilla relativa sin -p/-t/--tmpdir cae
    en el directorio actual."""
    if not allow_temp:
        return "'mktemp' crea archivos (solo se permite con --allow-temp y destino temporal)."
    msg = ("'mktemp' crea un archivo fuera de un directorio temporal (solo se permite sin "
           "plantilla o con plantilla/-p temporal).")
    dirs = []
    tmpdir = False
    pos = []
    dd = False
    k = 0
    n = len(args)
    while k < n:
        a = args[k]
        if dd:
            pos.append(a)
        elif a == "--":
            dd = True
        elif a.startswith("--"):
            name, eq, val = a.partition("=")
            if _is_long_prefix(name, "--tmpdir", 4):
                if eq:
                    dirs.append(val)
                else:
                    tmpdir = True
            elif _is_long_prefix(name, "--suffix", 4) and not eq:
                k += 1
        elif a.startswith("-") and len(a) > 1:
            found, val, used = _short_option_value(args, k, "p")
            if found:
                dirs.append(val if val is not None else "")
                k += used
            if _short_cluster_has(a, "t", "p"):
                tmpdir = True
        else:
            pos.append(a)
        k += 1
    if any(not ok(d, True) for d in dirs) or len(pos) > 1:
        return msg
    if pos:
        t = pos[0]
        if ok(t):
            return None
        if (dirs or tmpdir) and not t.startswith("/") and ".." not in t and "\\" not in t \
                and not _dot_glob(t) and _SUB not in t:
            return None
        return msg
    return None


def _writer_reason(name, args, dest_ok):
    """Escritores y ejecutores de la ronda 6 (awk -i inplace, xxd -r, certutil, split, cpio,
    ar x, ex/ed, vim -s, openssl enc -out)."""
    if name in ("awk", "gawk", "mawk", "nawk"):
        for k, a in enumerate(args):
            if a == "--":
                break
            if a.startswith("--"):
                nm, eq, val = a.partition("=")
                if _is_long_prefix(nm, "--include", 5):
                    v = val if eq else (args[k + 1] if k + 1 < len(args) else "")
                    if v.startswith("inplace"):
                        return "'%s -i inplace' modifica archivos." % name
            elif a.startswith("-i"):
                v = a[2:] or (args[k + 1] if k + 1 < len(args) else "")
                if v.startswith("inplace"):
                    return "'%s -i inplace' modifica archivos." % name
    elif name == "xxd":
        opts, pos = _split_opts(args, _XXD_VALUE_OPTS)
        if any(o.startswith("-r") for o in opts) and len(pos) >= 2 \
                and not _is_null_target(pos[1]):
            return "'xxd -r' con archivo de salida escribe archivos."
    elif name == "certutil":
        for a in args:
            if a[:1] in ("-", "/") and a.lower().lstrip("-/") in (
                    "decode", "encode", "f", "decodehex", "encodehex"):
                return "'certutil' con -decode/-encode/-f escribe archivos."
    elif name == "split":
        if any(a.startswith("--") and _is_long_prefix(a.partition("=")[0], "--filter", 4)
               for a in args):
            return "'split --filter' ejecuta comandos."
        _, pos = _split_opts(args, _SPLIT_VALUE_OPTS)
        if not (len(pos) >= 2 and dest_ok is not None and dest_ok(pos[1])):
            return ("'split' escribe archivos de salida: solo se permite con un prefijo "
                    "temporal o de pruebas.")
    elif name == "csplit":
        vals, _ = _output_values(args, "f", "--prefix", "bn")
        if not (vals and all(dest_ok is not None and dest_ok(v) for v in vals)):
            return ("'csplit' escribe archivos de salida: solo se permite con -f/--prefix "
                    "temporal o de pruebas.")
    elif name == "cpio":
        return "'cpio' extrae o escribe archivos."
    elif name == "ar":
        if args and not args[0].startswith("--") and "x" in args[0].lstrip("-"):
            return "'ar x' extrae archivos."
    elif name in ("ex", "ed"):
        return "'%s' edita archivos." % name
    elif name in ("vim", "vi", "nvim"):
        if any(a.startswith("-") and not a.startswith("--") and "s" in a[1:] for a in args):
            return "'%s -s/-es' edita archivos en modo silencioso." % name
    elif name == "openssl" and args and args[0] == "enc":
        for k, a in enumerate(args):
            if a == "-out":
                v = args[k + 1] if k + 1 < len(args) else ""
                if not (dest_ok is not None and dest_ok(v)):
                    return "'openssl enc -out' escribe el archivo '%s'." % v
    return None


_WRAPPER_BLOCKED = {"flock", "watch", "strace", "ltrace", "ssh-agent"}


_ZIP_VALUE_OPTS = {"-b", "--temp-path", "-t", "-tt", "-n", "--suffixes", "-P", "--password"}


def _zip_reason(args, dest_ok):
    """zip escribe el archivo destino (el primer posicional, o el valor de -O)."""
    dests = []
    pos = []
    has_out = False
    k = 0
    n = len(args)
    dd = False
    while k < n:
        a = args[k]
        if dd:
            pos.append(a)
        elif a == "--":
            dd = True
        elif a in ("-O", "--output-file"):
            has_out = True
            dests.append(args[k + 1] if k + 1 < n else "")
            k += 1
        elif a.startswith("--output-file="):
            has_out = True
            dests.append(a.partition("=")[2])
        elif a in _ZIP_VALUE_OPTS:
            k += 1
        elif a.startswith("-") and a != "-":
            pass
        else:
            pos.append(a)
        k += 1
    if not has_out and pos:
        dests.append(pos[0])
    for d in dests:
        if not (dest_ok is not None and dest_ok(d)):
            return ("'zip' escribe el archivo '%s': solo se permite `-` o un destino temporal "
                    "o de pruebas." % d)
    return None


def _pip_subcommand(args):
    _, pos = _split_opts(args, _PIP_VALUE_OPTS)
    return pos[0] if pos else None


def _archive_reason(name, args, dest_ok=None, dir_ok=None):
    """tar (extraer o -C), compresores sin salida estandar, unzip y 7z extraen o escriben."""
    if name == "tar":
        return _tar_reason(args, dest_ok, dir_ok)
    elif name in _COMPRESSORS:
        if name in ("zstd", "unzstd", "lz4", "unlz4") and any(
                a == "-o" or a.startswith("--output") for a in args):
            return "'%s' con -o escribe un archivo." % name
        for a in args:
            if a == "--":
                break
            if a.startswith("--"):
                opt = a.partition("=")[0]
                if any(_is_long_prefix(opt, full, 4)
                       for full in ("--stdout", "--to-stdout", "--test", "--list")):
                    return None
            elif a.startswith("-") and len(a) > 1 and _short_cluster_has(a, "ctl", "SCFMT"):
                return None
        return "'%s' sin -c/--stdout (ni -t/-l) escribe o reemplaza archivos." % name
    elif name == "unzip":
        for a in args:
            if a == "--":
                break
            if a.startswith("-") and not a.startswith("--") and len(a) > 1 \
                    and _short_cluster_has(a, "ltpZ", "dx"):
                return None
        return "'unzip' extrae archivos."
    elif re.fullmatch(r"7z[a-z]?", name):
        _, pos = _split_opts(args)
        if pos and pos[0] in ("x", "e", "a", "u", "d", "rn"):
            return "'%s %s' escribe archivos." % (name, pos[0])
    return None


def _find_exec_inner(args, k):
    """args[k] es -exec/-execdir/-ok/-okdir; devuelve (comando interno, indice tras su
    terminador `;` o `{} +`: un `+` en otro sitio es un argumento). Quien llama sigue desde
    ese indice, asi un -exec anidado no se vuelve a analizar en cada nivel (costo lineal, no
    exponencial); la profundidad se limita con _MAX_EXEC_DEPTH."""
    n = len(args)
    j = k + 1
    while j < n and not (args[j] == ";" or (args[j] == "+" and j > k + 1 and args[j - 1] == "{}")):
        j += 1
    return args[k + 1:j], j + 1


_BS_HINT = ("La ruta lleva '\\': usa '/' como separador (bash elimina la barra invertida, así "
            "que no se puede evaluar).")


def _bs_like(p):
    """Ruta con barra invertida o de unidad relativa (`C:x`: lo que queda de `C:` + barra + `x`)."""
    return "\\" in p or re.match(r"^[A-Za-z]:[^/]", p) is not None


def _simple_reason(words, redirs, allow_temp, path_ok=None, hint=None, _depth=0):
    """path_ok: callable opcional (Bash en tests-only); acepta destinos de escritura extra.

    hint: texto que sustituye la explicacion de --allow-temp cuando path_ok es None.
    """
    def ok(p, allow_dir=False):
        return _is_temp(p, allow_dir) or (path_ok is not None and path_ok(p))

    def dest_ok(p):
        return _is_null_target(p) or (allow_temp and ok(p))

    def dir_ok(p):
        return allow_temp and ok(p, True)

    for op, target in redirs:
        if target.lower() in _NULL_TARGETS or re.fullmatch(r"/dev/fd/\d+", target):
            continue
        if allow_temp and ok(target):
            continue
        if allow_temp and _bs_like(target):
            extra = " " + _BS_HINT
        elif hint is not None and path_ok is None:
            extra = " " + hint
        elif allow_temp and path_ok is None:
            extra = " Con --allow-temp solo se permite escribir bajo un directorio temporal."
        else:
            extra = ""
        return "la redirección '%s %s' escribe un archivo.%s" % (op, target, extra)
    cw = _command_word(words)
    if cw is None:
        return None
    name, args = cw
    if name == "git":
        return _git_reason(args)
    if name in _WRAPPER_BLOCKED:
        return "'%s' ejecuta otro comando que esta guarda no analiza." % name
    if name == "hash" and any(
            a.startswith("-") and not a.startswith("--") and "p" in a[1:] for a in args):
        return "'hash -p' redefine qué binario ejecuta un nombre de comando."
    if name == "mktemp":
        return _mktemp_reason(args, allow_temp, ok)
    if name in FILE_MUTATORS:
        if name == "tee" and all(_is_null_target(p) for p in _positional(args)):
            return None  # sin archivos, o solo /dev/null, `-`, /dev/stdout...
        if allow_temp and name in TEMP_OK:
            if name == "cp" and _cp_link_option(args):
                return ("'cp' con -l/--link o -s/--symbolic-link crea un enlace duro o "
                        "simbólico al original: escribir en él modificaría el original.")
            target = None
            if name in ("cp", "mv"):
                target, args = _extract_target(args)
            pos = _positional(args)
            if name == "tee":
                good = all(ok(p) or _is_null_target(p) for p in pos)
            elif name == "cp":
                if target is not None:
                    good = bool(pos) and ok(target, True)
                else:
                    good = len(pos) >= 2 and ok(pos[-1], True)
            elif name == "mv":
                if target is not None:
                    good = bool(pos) and all(ok(p) for p in pos) and ok(target, True)
                else:
                    good = (len(pos) >= 2 and all(ok(p) for p in pos[:-1])
                            and ok(pos[-1], True))
            else:
                good = bool(pos) and all(ok(p) for p in pos)
            if good:
                return None
            if any(_bs_like(p) for p in pos + ([target] if target else [])):
                return "'%s' escribe fuera de un directorio temporal o de pruebas. %s" % (
                    name, _BS_HINT)
            if path_ok is not None:
                return "'%s' escribe fuera de un directorio temporal o de pruebas." % name
            if hint is not None:
                return "'%s' escribe fuera de un directorio temporal. %s" % (name, hint)
            return ("'%s' escribe fuera de un directorio temporal (con --allow-temp solo se "
                    "permite bajo /tmp, $TMPDIR, etc.)." % name)
        return "'%s' modifica archivos." % name
    if name == "uniq":
        _, pos = _split_opts(args, {"-f", "-s", "-w", "--skip-fields", "--skip-chars",
                                    "--check-chars"})
        if len(pos) >= 2 and not _is_null_target(pos[1]):
            return "'uniq' con archivo de salida escribe archivos."
    if name == "history" and any(
            a.startswith("-") and not a.startswith("--") and any(ch in "wa" for ch in a[1:])
            for a in args):
        return "'history -w/-a' escribe el archivo de historial."
    if name == "zip":
        r = _zip_reason(args, dest_ok)
        if r:
            return r
    r = _archive_reason(name, args, dest_ok, dir_ok)
    if r:
        return r
    r = _writer_reason(name, args, dest_ok)
    if r:
        return r
    if _inplace_editor(name, args):
        return "'%s' con edición en el lugar (-i) modifica archivos." % name
    if name == "sed" and _sed_writes_file(args):
        return ("'sed' con el comando w/W/e (o los flags w/e de s) escribe archivos o "
                "ejecuta comandos.")
    r = _output_option_reason(name, args)
    if r:
        return r
    if name == "find":
        if "-delete" in args:
            return "'find -delete' borra archivos."
        k = 0
        while k < len(args):
            a = args[k]
            if a in ("-fprint", "-fprint0", "-fprintf", "-fls"):
                dest = args[k + 1] if k + 1 < len(args) else None
                if dest is None or not (allow_temp and ok(dest)) and not _is_null_target(dest):
                    return "'find %s' escribe un archivo." % a
            if a in ("-exec", "-execdir", "-ok", "-okdir"):
                if _depth >= _MAX_EXEC_DEPTH:
                    raise ParseError("find -exec anidado a más de %d niveles" % _MAX_EXEC_DEPTH)
                inner, k = _find_exec_inner(args, k)
                r = _simple_reason(inner, [], allow_temp, path_ok, hint, _depth + 1)
                if r:
                    return "'find %s' ejecuta un comando que modifica: %s" % (a, r)
                continue
            k += 1
        return None
    if re.fullmatch(_PIP, name):
        sub = _pip_subcommand(args)
        if sub in ("install", "uninstall"):
            return "'%s %s' cambia el entorno." % (name, sub)
        return None
    if re.fullmatch(r"python[0-9.]*|py", name):
        for k in range(len(args)):
            found, mod, used = _short_option_value(args, k, "m", "cWX")  # `-m pip` y `-mpip`
            if found and mod is not None and re.fullmatch(_PIP, mod):
                sub = _pip_subcommand(args[k + 1 + used:])
                if sub in ("install", "uninstall"):
                    return "'%s -m pip %s' cambia el entorno." % (name, sub)
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


_CD_COMMANDS = {"cd", "pushd", "popd", "chdir", "set-location", "sl"}


def _changes_dir(words, _depth=0):
    """True si el comando cambia el directorio de trabajo (propio o de un hijo)."""
    info = {}
    cw = _command_word(words, info)
    if info.get("chdir"):
        return True
    if cw is None:
        return False
    name, args = cw
    if name in _CD_COMMANDS:
        return True
    if name != "find":
        return False
    k = 0
    while k < len(args):
        a = args[k]
        if a in ("-execdir", "-okdir"):
            return True
        if a in ("-exec", "-ok"):
            if _depth >= _MAX_EXEC_DEPTH:
                raise ParseError("find -exec anidado a más de %d niveles" % _MAX_EXEC_DEPTH)
            inner, k = _find_exec_inner(args, k)
            if _changes_dir(inner, _depth + 1):  # `-exec env -C .. rm ...`
                return True
            continue
        k += 1
    return False


def _make_path_ok(cwd):
    """Criterio de ruta de pruebas para Bash en tests-only (mas estricto que is_test_path)."""
    if not (isinstance(cwd, str) and cwd.strip()):
        return None
    c = _norm_path(cwd).rstrip("/")
    if not _is_abs(c):
        return None

    def path_ok(path):
        if ".." in path or _SUB in path or any(ch in path for ch in "$~%{}[]\\"):
            return False
        if _dot_glob(path):
            return False  # `.?` / `.*` pueden coincidir con `..`
        if re.match(r"^[A-Za-z]:(?![/\\])", path):
            return False  # ruta de unidad relativa (C:src), depende del directorio de esa unidad
        norm = _norm_path(path)
        if _is_abs(norm) and not norm.startswith(c + "/"):
            return False
        return is_test_path(path, cwd)

    return path_ok


_STRICT_HINT = (" Simplifica el comando: una orden simple por llamada, con rutas literales "
                "(sin variables, sustituciones, subshells, funciones, heredocs ni varias líneas).")


def _strict_syntax_reason(cmd):
    """Modo estricto de tests-only + Bash: motivo (str) si el comando usa sintaxis que el parser
    no puede emular con certeza respecto a bash, o None. Ver el docstring del modulo."""
    n = len(cmd)

    def no(what):
        return "sintaxis no admitida en tests-only (%s)." % what + _STRICT_HINT

    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", cmd):
        return no("byte NUL o carácter de control")

    def word_alone(i, length):
        before = cmd[i - 1] if i > 0 else " "
        after = cmd[i + length] if i + length < n else " "
        return before in " \t" and after in " \t"

    bs = ("barra invertida '\\' (escapes y continuaciones de línea; usa '/' como separador de "
          "rutas)")
    quote = None
    i = 0
    while i < n:
        c = cmd[i]
        if quote == "'":
            j = cmd.find("'", i)
            if j == -1:
                break
            quote = None
            i = j + 1
            continue
        if quote == '"':
            if c == '"':
                quote = None
            elif c == "$":
                return no("'$': variable, sustitución o expansión")
            elif c == "`":
                return no("backtick: sustitución de comandos")
            elif c == "\\":
                return no(bs)
            i += 1
            continue
        if c == "'":
            quote = "'"
        elif c == '"':
            quote = '"'
        elif c == "$":
            return no("'$': variable, sustitución o expansión")
        elif c == "`":
            return no("backtick: sustitución de comandos")
        elif c == "\\":
            if cmd[i + 1:i + 2] == ";" and word_alone(i, 2):
                i += 2  # `find ... -exec ... \;`
                continue
            return no(bs)
        elif c in "()":
            return no("paréntesis '%s': subshell, función, aritmética o array" % c)
        elif c in "{}":
            if c == "{" and cmd[i + 1:i + 2] == "}" and word_alone(i, 2):
                i += 2  # `{}` de find -exec
                continue
            return no("llave '%s': grupo, función o expansión de llaves" % c)
        elif c == "[":
            if cmd[i + 1:i + 2] == "[":
                return no("'[[ ]]'")
            if not word_alone(i, 1):
                return no("corchete '[': patrón glob")
        elif c == "]":
            if not word_alone(i, 1):
                return no("corchete ']': patrón glob o '[[ ]]'")
        elif c == "<":
            nxt = cmd[i + 1:i + 2]
            if nxt == "<":
                return no("'<<' o '<<<': heredoc o here-string")
            if nxt == "(":
                return no("'<(': sustitución de procesos")
        elif c == ">":
            if cmd[i + 1:i + 2] == "(":
                return no("'>(': sustitución de procesos")
        elif c in "\n\r":
            return no("varias líneas")
        elif c == "#":
            if i == 0 or cmd[i - 1] in " \t;|&<>":
                return no("'#': comentario")
        elif c == "&":
            nxt = cmd[i + 1:i + 2]
            if nxt == "&":
                i += 2
                continue
            if nxt == ">":
                i += 3 if cmd[i + 2:i + 3] == ">" else 2
                continue
            if i > 0 and cmd[i - 1] == ">" and (i < 2 or cmd[i - 2] != ">"):
                i += 1  # `>&`, `2>&1`
                continue
            return no("'&': segundo plano o redirección no admitida")
        i += 1
    if quote is not None:
        return "comilla sin cerrar en el comando (tests-only)."
    return None


_TESTS_ONLY_FORBIDDEN = {"trap", "hash", "enable", "flock", "watch", "strace", "ltrace",
                         "ssh-agent", "chroot"}
# Variables que hacen que un comando "inocuo" ejecute otro (GIT_EXTERNAL_DIFF=rm git diff).
_DANGEROUS_VAR = re.compile(
    r"GIT_.*|PAGER|LESSOPEN|LESSCLOSE|TAPE|PATH|BASH_ENV|ENV|LD_PRELOAD|.*EDITOR|.*VISUAL")
_VAR_SETTERS = {"export", "declare", "typeset", "local", "readonly"}


def _tests_only_forbidden(words, _depth=0):
    """Motivo (str) si el comando usa un ejecutor o una variable de entorno peligrosa que
    tests-only no admite (incluido dentro de find -exec), o None."""
    info = {}
    cw = _command_word(words, info)
    for nm in info.get("assign", ()):
        if _DANGEROUS_VAR.fullmatch(nm):
            return ("la variable '%s' no se admite como prefijo en tests-only: hace que "
                    "un comando ejecute otro programa." % nm)
    if cw is None:
        return None
    name, args = cw
    if name in _TESTS_ONLY_FORBIDDEN:
        return ("'%s' no se admite en tests-only: programa o ejecuta comandos fuera de lo que "
                "esta guarda analiza." % name)
    if name in _VAR_SETTERS:
        for a in args:
            if _ASSIGN.match(a) and _DANGEROUS_VAR.fullmatch(_assign_name(a)):
                return ("la variable '%s' no se admite en tests-only: hace que un comando "
                        "ejecute otro programa." % _assign_name(a))
    if name == "find":
        k = 0
        while k < len(args):
            if args[k] in ("-exec", "-execdir", "-ok", "-okdir"):
                if _depth >= _MAX_EXEC_DEPTH:
                    raise ParseError("find -exec anidado a más de %d niveles" % _MAX_EXEC_DEPTH)
                inner, k = _find_exec_inner(args, k)
                r = _tests_only_forbidden(inner, _depth + 1)
                if r:
                    return r
                continue
            k += 1
    return None


def _check_readonly(allow_temp, payload, tests_only=False):
    if payload.get("tool_name") != "Bash":
        return None
    ti = payload.get("tool_input")
    command = ti.get("command") if isinstance(ti, dict) else None
    prefix = "Bloqueado por agent_guard (%s): " % ("tests-only" if tests_only else "readonly")
    if not isinstance(command, str):
        return prefix + "la llamada a Bash no trae un comando analizable."
    if len(command) > MAX_COMMAND_LEN:
        return (prefix + "el comando es demasiado largo para analizarlo de forma segura "
                "(%d caracteres; el máximo es %d)." % (len(command), MAX_COMMAND_LEN))
    if tests_only:
        strict = _strict_syntax_reason(command)
        if strict:
            return prefix + strict
    try:
        cmds = parse_commands(command)
    except ParseError as e:
        return prefix + "no se pudo analizar el comando de forma segura (%s)." % e
    path_ok = None
    hint = None
    if tests_only:
        for words, _ in cmds:
            try:
                forbidden = _tests_only_forbidden(words)
            except ParseError as e:
                return prefix + "no se pudo analizar el comando de forma segura (%s)." % e
            if forbidden:
                return prefix + forbidden
        path_ok = _make_path_ok(payload.get("cwd"))
        if path_ok is None:
            hint = ("En tests-only, sin un cwd válido, solo se permite escribir bajo el "
                    "directorio temporal.")
        for words, _ in cmds:
            try:
                chdir = _changes_dir(words)
            except ParseError as e:
                return prefix + "no se pudo analizar el comando de forma segura (%s)." % e
            if chdir:
                # el directorio cambia: las rutas relativas ya no son fiables
                path_ok = None
                hint = ("En tests-only solo se escribe en pruebas (o en el directorio "
                        "temporal). El comando cambia de directorio (cd, pushd, env -C, "
                        "sudo -D, find -execdir, etc.), así que no se pueden evaluar rutas "
                        "relativas: usa rutas absolutas bajo el cwd sin cambiar de directorio.")
                break
    for words, redirs in cmds:
        try:
            r = _simple_reason(words, redirs, allow_temp, path_ok, hint)
        except ParseError as e:
            return prefix + "no se pudo analizar el comando de forma segura (%s)." % e
        if r and tests_only:
            return (prefix + r + " Este agente solo escribe en pruebas (tests/, fixtures/, "
                    "archivos de prueba o temporal); reportá el cambio necesario en lugar "
                    "de aplicarlo.")
        if r:
            return (prefix + r + " Este agente es de solo lectura; reportá el hallazgo en lugar "
                    "de aplicarlo.")
    return None


def check(mode, allow_temp, payload):
    """Devuelve el motivo del bloqueo (str) o None si se permite."""
    if mode == "tests-only":
        if payload.get("tool_name") == "Bash":
            return _check_readonly(True, payload, tests_only=True)
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
