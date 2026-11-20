"""Genera install-manifest.json: los archivos que instala install.ps1 y su hash canonico.

Uso (la raiz es la carpeta que contiene tools/, salvo que se pase --root):

    python -B tools/build_manifest.py            escribe install-manifest.json
    python -B tools/build_manifest.py --check    no escribe; sale con 0 si esta al dia, 1 si no

Hash canonico: SHA-256, en hexadecimal minusculas, de los bytes del archivo tras sustituir
cada par CRLF por LF. Un CR suelto no se toca. No se quita BOM ni se recodifica.

El manifiesto detecta deriva, corrupcion y ediciones sin regenerar. No autentica el origen:
vive en el mismo repositorio que los archivos que describe.
"""

import hashlib
import json
import os
import re
import subprocess
import sys

MANIFEST_NAME = "install-manifest.json"

# Lista permitida: tres rutas fijas (rules/agentes.md, hooks/agent_guard.py, docs/agentes.md)
# y cualquier agents/<nombre>.md con nombre [a-z0-9_-]+. NO es una lista cerrada de doce
# nombres: hoy se instalan doce archivos, pero el patron acepta cualquier agente nuevo.
# install.ps1 lleva la misma regex, pero con \z: en .NET \Z (y $) aceptan un \n final, \z no.
# El lookahead excluye los nombres reservados de Windows (con, prn, aux, nul, com1-9, lpt1-9).
ALLOWED = re.compile(
    r"^(agents/(?!(con|prn|aux|nul|com[1-9]|lpt[1-9])\.)[a-z0-9_-]+\.md|rules/agentes\.md|hooks/agent_guard\.py|docs/agentes\.md)\Z"
)

# Carpetas donde un archivo fuera de la lista permitida obliga a decidir si se instala.
_GUARDED_PREFIXES = ("agents/", "rules/", "hooks/")


class ManifestError(ValueError):
    """Entrada que no se puede convertir en manifiesto."""


def canonical_sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


_GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")
_REGULAR_MODES = ("100644", "100755")


def _git_env() -> dict:
    """Entorno sin variables que hagan que git ignore el repositorio de cwd."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_VARS}


def parse_ls_files(raw: bytes) -> list[str]:
    """Rutas de la salida de git ls-files -s -z. Rechaza todo modo que no sea archivo regular."""
    paths = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        meta, sep, path = entry.partition(b"\t")
        fields = meta.split(b" ")
        if not sep or len(fields) != 3:
            raise ManifestError("salida inesperada de git ls-files: " + repr(entry))
        mode = fields[0].decode("ascii", "replace")
        name = path.decode("utf-8", "replace")
        if mode not in _REGULAR_MODES:
            raise ManifestError(
                "modo git no permitido " + mode + " (enlace simbolico, submodulo u otro) en: " + name
            )
        paths.append(path.decode("utf-8"))
    return paths


def managed_files(root: str) -> list[str]:
    """Rutas gestionadas segun git ls-files, filtradas por ALLOWED y ordenadas."""
    if not os.path.isdir(root):
        raise ManifestError("la carpeta raiz no existe: " + root)
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-s", "-z", "--", "agents", "rules", "hooks", "docs/agentes.md"],
            cwd=root,
            env=_git_env(),
            check=True,
            timeout=60,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ManifestError("git no esta en el PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ManifestError("git ls-files excedio el tiempo limite (60 s)") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", "replace").strip()
        raise ManifestError("git ls-files fallo: " + detail) from exc
    try:
        paths = parse_ls_files(proc.stdout)
    except UnicodeDecodeError as exc:
        raise ManifestError("git ls-files devolvio una ruta que no es UTF-8") from exc
    unexpected = [
        p for p in paths if p.startswith(_GUARDED_PREFIXES) and not ALLOWED.match(p)
    ]
    if unexpected:
        raise ManifestError(
            "archivos fuera de la lista permitida bajo agents/, rules/ o hooks/: "
            + ", ".join(sorted(unexpected))
            + ". Alguien agrego un archivo: decide si se instala y ajusta ALLOWED "
            "(tools/build_manifest.py e install.ps1)."
        )
    result = sorted(p for p in paths if ALLOWED.match(p))
    if not result:
        raise ManifestError(
            "git ls-files no devolvio ningun archivo gestionado en " + root
            + ". Revisa --root: debe ser la raiz del repositorio."
        )
    return result


def build_manifest(root: str, paths: list[str]) -> dict:
    seen = set()
    entries = []
    for rel in sorted(paths):
        if not ALLOWED.match(rel):
            raise ManifestError("ruta fuera de la lista permitida: " + rel)
        if rel in seen:
            raise ManifestError("ruta duplicada: " + rel)
        seen.add(rel)
        with open(os.path.join(root, *rel.split("/")), "rb") as f:
            entries.append({"path": rel, "sha256": canonical_sha256(f.read())})
    return {"schema": 1, "algorithm": "sha256", "eol": "lf", "files": entries}


def render(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=True) + "\n"


def _default_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv: list[str]) -> int:
    check = False
    root = _default_root()
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--check":
            check = True
        elif arg == "--root" and args:
            root = args.pop(0)
        else:
            print("uso: build_manifest.py [--check] [--root CARPETA]", file=sys.stderr)
            return 1
    target = os.path.join(root, MANIFEST_NAME)
    try:
        text = render(build_manifest(root, managed_files(root)))
    except (ManifestError, OSError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 1
    if check:
        try:
            with open(target, "rb") as f:
                current = f.read().replace(b"\r\n", b"\n")
        except OSError:
            current = None
        if current == text.encode("ascii"):
            return 0
        print(
            MANIFEST_NAME + " no esta al dia. Regeneralo con: python -B tools/build_manifest.py",
            file=sys.stderr,
        )
        return 1
    with open(target, "wb") as f:
        f.write(text.encode("ascii"))
    print("escrito " + MANIFEST_NAME + " (" + str(text.count('"path"')) + " archivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
