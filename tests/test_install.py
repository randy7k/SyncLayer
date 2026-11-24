"""Pruebas de install.ps1 (T3: validacion, plan y -DryRun; T4: respaldo, copia, verificacion y estado;
T5: cambios locales, -Force, estado ilegible y puntos de reanalisis).

Lanzan el script con subprocess (sin shell, con timeout) sobre powershell.exe y/o pwsh.
Nunca usan el destino por defecto: todas pasan -Target a una carpeta temporal.

Cobertura de interpretes (decision tomada para el plan, 3.6): pwsh 7 no esta instalado en el
equipo de desarrollo ni se va a instalar. El requisito "una ejecucion sin saltos" se cumple con
Windows PowerShell 5.1. La clase de pwsh queda opcional: se salta con motivo claro cuando no
esta, y la compatibilidad con pwsh 7 es NO VERIFICADA hasta que alguien la corra. En Windows la
falta de powershell.exe es un FALLO (ShellAvailability), no un salto silencioso.
"""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aliases_ref as ar  # noqa: E402
import build_manifest as bm  # noqa: E402
import levels_ref as lr  # noqa: E402
import plans_ref as pr  # noqa: E402

SCRIPT = os.path.join(ROOT, "install.ps1")
POWERSHELL = shutil.which("powershell")
PWSH = shutil.which("pwsh")
NO_SHELL = "no hay powershell.exe ni pwsh en el PATH: pruebas de install.ps1 omitidas"
PWSH_SKIP = "pwsh no esta en el PATH: compatibilidad con pwsh 7 NO verificada en este equipo"
TIMEOUT = 120
ENV_FORCE = "CLAUDE_CODE_SUBAGENT_MODEL_FORCE"
ENV_EFFORT = "CLAUDE_CODE_EFFORT_LEVEL"
ENV_OVERRIDE_VARS = (ENV_FORCE, ENV_EFFORT)


def shell_version(exe):
    """Version del interprete, para dejar claro en la salida de la suite que shell corrio."""
    try:
        proc = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"],
            timeout=TIMEOUT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return proc.stdout.decode("utf-8", "replace").strip() or "version desconocida"
    except (OSError, subprocess.SubprocessError):
        return "version desconocida"


def personal_tokens():
    """Datos personales a vigilar: usuario del equipo calculado en ejecucion (nunca literal)."""
    names = {os.path.basename(os.path.expanduser("~")),
             os.environ.get("USERNAME"), os.environ.get("USER")}
    return [n.lower() for n in names if n and len(n) > 2] + ["c:\\users", "/users/", "/home/"]

SAMPLE = {
    "agents/alfa.md": b"agente alfa\nlinea 2\n",
    "agents/beta.md": b"agente beta\n",
    "rules/agentes.md": b"reglas\n",
    "hooks/agent_guard.py": b"print('guard')\n",
    "docs/agentes.md": b"guia\n",
}

LINE = re.compile(r"^(NUEVO|IGUAL|ACTUALIZAR|MODIFICADO|HUERFANO) +(\S.*)$")


def agent_md(name, model, before=(), after=()):
    """Agente de prueba con frontmatter minimo. `before` y `after` son lineas extra del frontmatter antes y
    despues de `model:` (model=None: sin esa linea). El cuerpo trae una linea `model:` en la columna 0."""
    lines = ["---", "name: " + name, "description: agente de prueba " + name, "tools: Read, Grep"] + list(before)
    if model is not None:
        lines.append("model: " + model)
    lines += list(after) + ["color: blue", "---", "Cuerpo de " + name + ".", "model: linea del cuerpo, no se toca", ""]
    return "\n".join(lines).encode("latin-1")


# Bloque hooks: de sentinel, con un model: indentado dentro (no cuenta como la linea model: del frontmatter).
SENTINEL_HOOKS = ["hooks:", "  PreToolUse:", '    - matcher: "Write|Edit"', "      hooks:", "        - type: command",
                  '          command: "python guard.py"', "          model: dentro-de-hooks"]

# Fixture de los niveles (Fase 3, T4): los seis agentes modificables, los tres agentes fijos y las tres
# rutas fijas, con el model: del repositorio (nivel 5).
LEVEL_SAMPLE = {
    "agents/atlas.md": agent_md("atlas", "claude-fable-5-2"),
    "agents/forge.md": agent_md("forge", "sonnet"),
    "agents/sentinel.md": agent_md("sentinel", "sonnet", after=SENTINEL_HOOKS),
    "agents/scribe.md": agent_md("scribe", "sonnet"),
    "agents/scout.md": agent_md("scout", "sonnet"),
    "agents/oracle.md": agent_md("oracle", "haiku"),
    "agents/auditor.md": agent_md("auditor", "opus"),
    "agents/shield.md": agent_md("shield", "opus"),
    "agents/debugger.md": agent_md("debugger", "opus"),
    "rules/agentes.md": b"reglas\n",
    "hooks/agent_guard.py": b"print('guard')\n",
    "docs/agentes.md": b"guia\n",
}
LEVEL_FIXED = [rel for rel in LEVEL_SAMPLE
               if not (rel.startswith("agents/") and rel.split("/")[1][:-3] in lr.read_ps_list("LevelAgents"))]


def alias_agent(role, description, body, after=()):
    """Agente de ALIAS_SAMPLE: frontmatter de una linea por clave (con `after` tras model:), cuerpo en UTF-8."""
    lines = (["---", "name: " + role, "description: " + description, "tools: Read, Grep", "model: sonnet"]
             + list(after) + ["color: blue", "---", body])
    return "\n".join(lines).encode("utf-8")


# Fixture de los alias (Fase 4, T5): cuatro de los nueve agentes (sentinel con hooks:), las reglas y la guia (UTF-8, con
# "escribe", "describe", @agent-forge, `Forge (Sonnet):`, una tabla en mayusculas, roles entre las comillas angulares,
# tras la apertura de interrogacion y pegados a una letra acentuada, y un bloque cercado sin roles), el hook (que nombra
# roles y no se transforma) y un agente que no es de los nueve (tampoco se transforma). Los bytes altos son UTF-8 valido.
ALIAS_SAMPLE = {
    "agents/atlas.md": alias_agent("atlas", "Plans the work and hands it to FORGE.",
                                   "Eres ATLAS. Pide a forge que implemente y a SENTINEL que pruebe.\n"),
    "agents/forge.md": alias_agent(
        "forge", "Implements one unit of the ATLAS plan.",
        "Eres FORGE. Usa `forge`, Forge (Sonnet): tarea, @agent-forge, agents/forge.md y ~/.claude/agents/forge.md.\n"
        "«FORGE» y ¿forge? y Forgeé.\n"),
    "agents/scribe.md": alias_agent(
        "scribe", "Writes the docs.",
        "Eres SCRIBE. Quien escribe, describe, reescribe o sobrescribe; escriben. Describe. scribe.\n"),
    "agents/sentinel.md": alias_agent(
        "sentinel", "Runs the tests.",
        "Eres SENTINEL. «SENTINEL sólo escribe tests». Sentinelé y ñforge no cambian.\n",
        after=SENTINEL_HOOKS),
    "agents/alfa.md": "agente alfa que nombra a forge y a SENTINEL\n".encode("utf-8"),
    "rules/agentes.md": (
        "# Reglas\n\n| Agente | Uso |\n|---|---|\n| FORGE | implementar |\n| SENTINEL | pruebas |\n"
        "| ATLAS | planes |\n| SCRIBE | docs |\n\n"
        "`forge`, `sentinel`, `atlas` y `scribe`. Forge (Sonnet): corregir. @agent-forge y @agent-scribe. "
        "agents/forge.md.\n"
        "«SENTINEL sólo escribe tests». ¿scribe escribe o describe? Sentinelé, ñforge, "
        "éSCRIBE y SCRIBEÁ no cambian. Sobrescribe y reescribe: igual.\n\n"
        "```text\nbloque cercado sin roles\n```\n").encode("utf-8"),
    "docs/agentes.md": (
        "# Guia\n\nCada agente tiene un rol: FORGE implementa, SENTINEL prueba y ATLAS planifica.\n"
        "«SENTINEL sólo escribe tests» y «FORGE, SCRIBE y ATLAS… forge — sentinel.\n"
        "Describe lo que escribe `scribe` (Forge (Sonnet)).\n").encode("utf-8"),
    "hooks/agent_guard.py": b"# forge sentinel SCRIBE ATLAS no se transforman\nprint('guard')\n",
}
ALIAS_ONE = {"sentinel": "amigo-qa"}
ALIAS_FOUR = {"atlas": "mapa", "forge": "dev", "scribe": "redactor", "sentinel": "amigo-qa"}


def alias_expected(files, table, level=5):
    """{ruta del rol: (ruta de destino, bytes esperados)} segun la referencia independiente (aliases_ref) y, con el
    nivel 1 a 4, la celda del ROL de la tabla de install.ps1."""
    out = {}
    for rel, data in files.items():
        m = re.match(r"^agents/([a-z0-9_-]+)\.md$", rel)
        canon = data.replace(b"\r\n", b"\n")
        if m and m.group(1) in ar.roles():
            canon = ar.transform_agent(data, m.group(1), table)
        elif rel in ("rules/agentes.md", "docs/agentes.md"):
            canon = ar.transform_doc(data, table)
        if level != 5 and m and m.group(1) in lr.read_ps_list("LevelAgents"):
            model, effort = lr.read_script_table()[(level, m.group(1))]
            canon = lr.render_expected(canon, model, effort)
        out[rel] = (ar.dest_for(rel, table), canon)
    return out


def level_expected(files, level):
    """{ruta: bytes esperados en el destino} segun la referencia de Python (render_expected) y la tabla de
    install.ps1: los seis agentes modificables se renderizan en los niveles 1 a 4; el resto, y todo en el
    nivel 5, son los bytes canonicos (CRLF a LF) del origen."""
    table = lr.read_script_table()
    agents = lr.read_ps_list("LevelAgents")
    out = {}
    for rel, data in files.items():
        canon = data.replace(b"\r\n", b"\n")
        m = re.match(r"^agents/([a-z0-9_-]+)\.md$", rel)
        if level != 5 and m and m.group(1) in agents:
            model, effort = table[(level, m.group(1))]
            canon = lr.render_expected(canon, model, effort)
        out[rel] = canon
    return out


def level_hashes(files, level):
    return {rel: bm.canonical_sha256(data) for rel, data in level_expected(files, level).items()}


def split_front(data):
    """(lineas del frontmatter sin los separadores, lineas desde el cierre) de un agente en LF."""
    lines = data.decode("ascii").split("\n")
    close = lines.index("---", 1)
    return lines[1:close], lines[close:]


def write(base, rel, data):
    path = os.path.join(base, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def read(base, rel):
    with open(os.path.join(base, *rel.split("/")), "rb") as f:
        return f.read()


def manifest_for(src, paths=None):
    """Manifiesto generado por Python (build_manifest + render) para los archivos de src."""
    paths = sorted(SAMPLE) if paths is None else paths
    return bm.render(bm.build_manifest(src, paths))


def rename(d, old, new):
    return {(new if k == old else k): v for k, v in d.items()}


def snapshot(base):
    """Todos los archivos y carpetas bajo base con bytes y mtime (ns)."""
    snap = {}
    for dirpath, dirnames, filenames in os.walk(base):
        for name in dirnames:
            snap[os.path.relpath(os.path.join(dirpath, name), base)] = "dir"
        for name in filenames:
            p = os.path.join(dirpath, name)
            with open(p, "rb") as f:
                snap[os.path.relpath(p, base)] = (f.read(), os.stat(p).st_mtime_ns)
    return snap


class StaticChecks(unittest.TestCase):
    """Comprobaciones sobre el texto de install.ps1; no necesitan PowerShell."""

    def setUp(self):
        with open(SCRIPT, "rb") as f:
            self.raw = f.read()

    def test_script_is_pure_ascii(self):
        # Windows PowerShell 5.1 lee como ANSI un script sin BOM: nada fuera de ASCII (BOM incluido).
        bad = [i for i, b in enumerate(self.raw) if b > 0x7F]
        self.assertEqual(bad, [], "install.ps1 tiene bytes no ASCII en las posiciones " + str(bad[:5]))

    def test_no_forbidden_constructs(self):
        text = self.raw.decode("ascii")
        self.assertNotIn("&&", text)
        self.assertNotIn("??", text)
        self.assertNotRegex(text, r"(?i)invoke-expression|\biex\b")
        self.assertNotIn("*", text, "ninguna ruta se construye con comodines")
        for personal in personal_tokens():
            self.assertNotIn(personal, text.lower())

    def test_script_never_sets_or_removes_environment_variables(self):
        # T6: el instalador solo lee el entorno (GetEnvironmentVariable); nunca define, cambia ni borra.
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        self.assertNotRegex(text, r"(?i)SetEnvironmentVariable|\bsetx\b|\benv:|\[Environment\]::Set")
        # el detector mismo: una linea de escritura de entorno se detecta
        self.assertRegex("[System.Environment]::SetEnvironmentVariable('X', 'y')", r"(?i)SetEnvironmentVariable")
        self.assertRegex("$env:X = 'y'", r"(?i)\benv:")

    def test_real_agents_pass_the_structural_rules_of_the_renderer(self):
        # Los nueve agents/*.md del repositorio no quedan rechazados por la referencia (misma forma que el instalador)
        # en ninguna celda de la tabla: las reglas de falla cerrada no rompen a los agentes reales.
        names = ["atlas", "auditor", "debugger", "forge", "oracle", "scout", "scribe", "sentinel", "shield"]
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "agents"))), [n + ".md" for n in names])
        for name in names:
            data = read(ROOT, "agents/%s.md" % name)
            for model in ("opus", "sonnet", "haiku"):
                for effort in ("-", "low", "medium"):
                    with self.subTest(agent=name, model=model, effort=effort):
                        lr.render_expected(data, model, effort)

    def test_alias_lists_are_closed_data_in_the_script(self):
        # Fase 4, T1 (caso 1 y 2): $AliasRoles son los nombres de agents/*.md; las otras dos listas son datos
        # cerrados en minuscula. Aun sin uso: la instalacion no cambia. Con CRLF se normaliza dentro de read_ps_list.
        names = sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md"))
        self.assertEqual(len(names), 9)
        self.assertEqual(lr.read_ps_list("AliasRoles"), names)
        reserved = lr.read_ps_list("ReservedAliases")
        self.assertEqual(reserved, ["explore", "plan", "general-purpose", "claude", "statusline-setup",
                                    "claude-code-guide", "web-fetch", "fork", "output-style-setup"])
        words = lr.read_ps_list("YamlWords")
        self.assertEqual(words, ["true", "false", "null", "yes", "no", "on", "off", "y", "n"])
        for values in (names, reserved, words):
            self.assertEqual(values, [v.lower() for v in values])
            self.assertEqual(len(values), len(set(values)))

    def test_t2_alias_anchor_and_validator_are_defined_once(self):
        # Fase 4, T2: `# Alias:` es ancla de patch_script (T4 inyecta tras ella) y no tiene la forma `# Paso N:`;
        # la validacion de la tabla es una funcion unica. T5 retiro la guarda temporal de T2.
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        lines = [l.strip() for l in text.split("\n")]
        self.assertEqual(len([l for l in lines if l.startswith("# Alias:")]), 1)
        self.assertEqual(len(re.findall(r"^function Get-AliasTableProblem\b", text, re.M)), 1)
        self.assertEqual(text.count("los alias aun no se pueden aplicar en esta version"), 0)
        self.assertEqual(len([l for l in lines if re.match(r"# Paso \d+:", l)]), 10)

    def test_t2_the_config_is_read_once_through_the_known_anchor(self):
        # Lectura unica: el ancla de patch_script (`$level = [int](Read-LevelConfig $configPath)`) sigue siendo la
        # unica llamada de lectura; los alias salen de esa misma lectura y el archivo no se abre otra vez.
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        self.assertEqual(text.count("Read-LevelConfig $configPath"), 1)
        self.assertEqual(text.count("$level = [int](Read-LevelConfig $configPath)"), 1)
        body = text[text.index("function Read-LevelConfig"):text.index("function Find-AliasPair")]
        self.assertEqual(len(re.findall(r"\[System\.IO\.File\]::(Open|Read|OpenRead)\w*\(", body)), 1)
        # Todo uso de $configPath en el script: asignacion, comprobacion de carpeta, de existencia y la unica lectura.
        uses = [l.strip() for l in text.split("\n") if "$configPath" in l]
        self.assertEqual(uses, ["$configPath = Join-Path $TargetFull $ConfigName",
                                "if ([System.IO.Directory]::Exists($configPath)) {",
                                "if ([System.IO.File]::Exists($configPath)) {",
                                "$level = [int](Read-LevelConfig $configPath)"])
        # Get-AliasTableProblem y Get-AliasEffective no tocan el disco
        pure = text[text.index("function Find-AliasPair"):text.index("# Bytes del estado con esquema 2")]
        self.assertNotRegex(pure, r"\[System\.IO\.|Get-Content|Set-Content|Out-File")

    def test_allowed_pattern_matches_generator(self):
        # Con core.autocrlf git deja install.ps1 en CRLF al hacer checkout o merge: el ancla `$`
        # de la regex no tolera el retorno de carro (CR), asi que se normaliza antes de buscar.
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        m = re.search(r"^\$AllowedPattern = '(.*)'$", text, re.M)
        self.assertIsNotNone(m, "no se encontro $AllowedPattern en install.ps1")
        ps_pattern = m.group(1)
        self.assertTrue(ps_pattern.endswith(r"\z"))
        self.assertNotIn(r"\Z", ps_pattern)
        # Python usa \Z para lo que .NET llama \z; el resto debe ser identico.
        self.assertEqual(ps_pattern[:-2] + r"\Z", bm.ALLOWED.pattern)

    def test_f4t3_dest_max_length_is_derived_from_the_alias_rule(self):
        # El tope de dest (74) = "agents/" + alias de hasta 64 (letra inicial + {0,63}) + ".md". Se deriva de la regex
        # del alias de install.ps1 y se compara con el literal del instalador y con la referencia: si cambian por
        # separado, falla.
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        m = re.search(r"IsMatch\(\$value, '\^\[a-z\]\[a-z0-9_-\]\{0,(\d+)\}" + re.escape(chr(92)) + "z'", text)
        self.assertIsNotNone(m, "no se encontro la regex del alias en install.ps1")
        longest = 1 + int(m.group(1))
        self.assertEqual(longest, 64)
        expected = len("agents/") + longest + len(".md")
        self.assertEqual(expected, 74)
        lits = re.findall(r"\$d\.Length -gt (\d+) -and", text)
        self.assertEqual(lits, [str(expected)])
        self.assertEqual(ar.DEST_MAX, expected)
        ref = re.search(r"\{0,(\d+)\}", ar._ALIAS_RE.pattern)
        self.assertEqual(1 + int(ref.group(1)), longest)

    def test_f4t3_dest_max_length_literal_in_both_checks_matches_the_alias_rule(self):
        # Read-State y Get-DestRelProblem llevan cada uno su literal del tope: los dos deben existir, ser iguales entre
        # si y al tope derivado de la regla del alias (la prueba anterior sólo ve el de Read-State, por el `-and`).
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        m = re.search(r"IsMatch\(\$value, '\^\[a-z\]\[a-z0-9_-\]\{0,(\d+)\}" + re.escape(chr(92)) + "z'", text)
        self.assertIsNotNone(m, "no se encontro la regla del alias en install.ps1")
        expected = len("agents/") + 1 + int(m.group(1)) + len(".md")
        read_state = re.search(r"^function Read-State\(.*?^\}$", text, re.M | re.S)
        dest_rel = re.search(r"^function Get-DestRelProblem\(.*?^\}$", text, re.M | re.S)
        self.assertIsNotNone(read_state)
        self.assertIsNotNone(dest_rel)
        in_state = re.findall(r"\$d\.Length -gt (\d+)\b", read_state.group(0))
        in_dest = re.findall(r"\$d\.Length -gt (\d+)\b", dest_rel.group(0))
        self.assertEqual(in_state, [str(expected)])
        self.assertEqual(in_dest, [str(expected)])
        self.assertEqual(in_state, in_dest)

    def test_f4t3_read_state_requires_the_manifest_paths_and_dicts_are_ordinal(self):
        # Sin valor por defecto: un llamador que olvide $ManifestPaths no desactiva la regla en silencio.
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        self.assertEqual(re.findall(r"^function Read-State\((.*)\) \{$", text, re.M), [r"[string]$FilePath, $ManifestPaths"])
        self.assertEqual(text.count("Read-State $statePath $manifest.Order"), 1)
        self.assertEqual(len(re.findall(r"Read-State \$", text)), 1)
        ordinal = "New-Object 'System.Collections.Generic.Dictionary[string,string]' ([System.StringComparer]::Ordinal)"
        self.assertIn("$dests = " + ordinal, text)
        self.assertIn("$prevByDest = " + ordinal, text)
        self.assertNotRegex(text, r"\$(dests|prevByDest) = @\{\}")

    def test_f4t4_dest_rel_starts_as_identity_then_alias_reassigns_and_anchors_hold(self):
        # T4/T5: $destRel arranca como identidad (una asignacion) y el alias la reasigna (otra) en el bloque `# Alias:`,
        # a partir de la tabla efectiva (nunca del estado ni del entorno). Las anclas de patch_script de 3.3 siguen una
        # sola vez y en su sitio.
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        self.assertEqual(text.count("foreach ($rel in $manifest.Order) { $destRel[$rel] = $rel }"), 1)
        # T5: dos asignaciones, la identidad (arriba) y la del alias (solo si el archivo del rol esta en el manifiesto).
        self.assertEqual(len(re.findall(r"\$destRel\[[^\]]*\]\s*=", text)), 2)
        self.assertEqual(len(re.findall(r"^\s*\$destRel = ", text, re.M)), 1)
        self.assertEqual(text.count("Write-Atomic $dest $outBytes[$rel] $existing"), 1)
        self.assertEqual(text.count("Write-Atomic $statePath $stateBytes $stateExists"), 1)
        self.assertEqual(len(re.findall(r"^function Get-DestRelProblem\b", text, re.M)), 1)
        self.assertEqual(text.count("ConvertTo-StateBytes $manifest $outHash $level $destRel"), 1)
        self.assertEqual(text.count("$destProblem = Get-DestRelProblem $destRel $manifest.Order"), 1)
        lines = [l.strip() for l in text.split("\n")]
        anchor = next(i for i, l in enumerate(lines) if l.startswith("# Alias:"))
        check = lines.index("$destProblem = Get-DestRelProblem $destRel $manifest.Order")
        build = lines.index("foreach ($rel in $manifest.Order) { $destRel[$rel] = $rel }")
        self.assertLess(build, anchor)
        self.assertLess(anchor, check)

    def test_f4t4_steps_4_to_9_never_use_the_role_path_on_disk(self):
        # En los pasos 4 a 9 el rol ($rel) no se usa como ruta del disco: se lee, escribe, respalda y verifica la ruta
        # de destino. (El rol sirve para outBytes y outHash.)
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        body = text[text.index("# Paso 4: clasificar."):text.index("# Paso 10: mensaje final.")]
        self.assertEqual(re.findall(r"ConvertTo-LocalPath \$(?:TargetFull|BackupFull) \$rel\b", body), [])
        self.assertEqual(re.findall(r"Find-Reparse \$(?:TargetFull|BackupFull) \$rel\b", body), [])
        self.assertEqual(re.findall(r"\$written\.Add\(\$rel\)", body), [])
        self.assertEqual(re.findall(r"Path = \$prevDest", body), [])
        self.assertIn("$prevByDest.ContainsKey($destPath)", body)
        self.assertIn("$outHash[$roleByDest[$destPath]]", body)
        self.assertIn("Write-Atomic $dest $outBytes[$rel] $existing", body)

    def test_f4t5_static_functions_pattern_and_the_removed_guard(self):
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        for name in ("ConvertTo-AliasText", "ConvertTo-AliasBytes"):
            self.assertEqual(len(re.findall(r"^function " + name + r"\b", text, re.M)), 1, name)
        # la expresion de 3.5, tal cual (E1): dos lookbehind de ancho fijo y dos lookahead, sin IgnoreCase
        bs = chr(92)
        self.assertIn("'(?<![A-Za-z0-9_])(?<!" + bs + "u00c3[" + bs + "u0080-" + bs + "u00bf])(?:'", text)
        self.assertIn("')(?![A-Za-z0-9_])(?!" + bs + "u00c3[" + bs + "u0080-" + bs + "u00bf])'", text)
        body = text[text.index("function ConvertTo-AliasText"):text.index("try {\n    $Source = $PSScriptRoot")]
        self.assertNotIn("IgnoreCase", body)
        self.assertNotIn("[regex]::Replace", body)
        self.assertEqual(text.count("$aliasResult = $latin1.GetBytes("), 1)
        self.assertEqual(len(re.findall(r"^\s*\$result = \$latin1\.GetBytes\(", text, re.M)), 1)
        self.assertNotIn("aun no se pueden aplicar", text)
        lines = [l.strip() for l in text.split("\n")]
        alias_at = next(i for i, l in enumerate(lines) if l.startswith("# Alias:"))
        nivel_at = next(i for i, l in enumerate(lines) if l.startswith("# Nivel:"))
        self.assertLess(alias_at, nivel_at)
        self.assertEqual(len([l for l in lines if l.startswith("# Alias:")]), 1)
        self.assertEqual(len([l for l in lines if re.match(r"# Paso \d+:", l)]), 10)
        # el bloque Nivel parte de los bytes con alias y busca la celda por rol
        nivel = text[text.index("    # Nivel:"):text.index("    # Paso 3:")]
        self.assertIn("ConvertTo-LevelBytes $aliasBytes[$rel]", nivel)
        self.assertIn("Get-LevelCell $level $agentMatch.Groups[1].Value", nivel)

    def test_f5t2_plans_dir_is_read_once_validated_after_the_alias_table_and_never_used_as_a_path(self):
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        # una sola funcion de validacion y una sola lectura de la clave (dentro de la lectura unica de la configuracion)
        self.assertEqual(len(re.findall(r"^function Get-PlansDirProblem\b", text, re.M)), 1)
        self.assertEqual(text.count("Get-PropRaw $m 'plans_dir'"), 1)
        read_body = text[text.index("function Read-LevelConfig"):text.index("function Find-AliasPair")]
        self.assertIn("Get-PropRaw $m 'plans_dir'", read_body)
        self.assertEqual(len(re.findall(r"\[System\.IO\.File\]::(Open|Read|OpenRead)\w*\(", read_body)), 1)
        # la validacion de la carpeta va despues de la de la tabla de alias, y las dos antes del estado y de escribir
        self.assertLess(text.index("$aliasProblem = Get-AliasTableProblem"), text.index("$plansProblem = Get-PlansDirProblem"))
        self.assertLess(text.index("$plansProblem = Get-PlansDirProblem"), text.index("# Paso 3:"))
        # pura: sin E/S ni rutas
        body = text[text.index("function Get-PlansDirProblem"):text.index("# Bytes del estado con esquema 2")]
        self.assertNotRegex(body, r"\[System\.IO\.|Get-Content|Set-Content|Out-File|Join-Path|Test-Path|Write-Out|Write-Err")
        self.assertIn("$PlansDirMaxLength", body)
        self.assertIn("$PlansDirPattern", body)
        self.assertIn("$AllowedPattern", body)
        self.assertIn("$AliasRoles", body)
        self.assertNotIn("IgnoreCase", body)
        # los motivos del script son los de la referencia
        for message in (pr.MSG_TYPE, pr.MSG_SHAPE, pr.MSG_DEVICE, pr.MSG_ROLE):
            self.assertIn("'" + message + "'", text)
        # el valor es texto: ninguna linea que lo toque lo usa para construir o abrir una ruta ni lo mete en un error
        touching = [l.strip() for l in text.split("\n") if "ConfigPlansPair" in l or "plansEffective" in l]
        self.assertTrue(touching)
        for line in touching:
            self.assertNotRegex(line, r"Join-Path|ConvertTo-LocalPath|Find-Reparse|\[System\.IO\.|Get-Content|Set-Content",
                                line)
        stops = [l.strip() for l in text.split("\n") if "Stop-Install" in l and "plans" in l.lower()]
        for line in stops:
            self.assertNotIn("ConfigPlansPair", line)
            self.assertNotIn("plansEffective", line)
        self.assertEqual([l for l in text.split("\n") if l.strip().startswith("Write-Out ('Planes: '")],
                         ["        Write-Out ('Planes: ' + $plansEffective)"])
        # anclas intactas: una sola `# Alias:`, diez `# Paso N:`, la lectura de siempre y ningun marcador nuevo `# Paso`
        lines = [l.strip() for l in text.split("\n")]
        self.assertEqual(len([l for l in lines if l.startswith("# Alias:")]), 1)
        self.assertEqual(len([l for l in lines if l.startswith("# Configuracion:")]), 1)
        self.assertEqual(len([l for l in lines if l.startswith("# Nivel:")]), 1)
        self.assertEqual(len([l for l in lines if re.match(r"# Paso \d+:", l)]), 10)
        self.assertEqual(len([l for l in lines if l.startswith("# Paso")]), 10)
        self.assertEqual(text.count("$level = [int](Read-LevelConfig $configPath)"), 1)

    def test_f5t2_temporary_guard_is_one_stop_and_has_no_other_effect(self):
        # Guarda temporal de T2: un solo Stop-Install con su texto, dentro del bloque que imprime `Planes:`. T3 la retira
        # junto con esta prueba.
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        guard = "error: la carpeta de planes aun no se puede aplicar en esta version. No se escribio nada."
        self.assertEqual(text.count(guard), 1)
        self.assertEqual(text.count("Stop-Install 1 '" + guard + "'"), 1)
        block = ("    if ($null -ne $plansEffective) {\n        Write-Out ('Planes: ' + $plansEffective)\n"
                 "        Stop-Install 1 '" + guard + "'\n    }\n")
        self.assertEqual(text.count(block), 1)
        self.assertLess(text.index(block), text.index("# Paso 6:"))
        self.assertGreater(text.index(block), text.index("# Paso 5:"))

    def test_f5t2_the_config_documentation_in_the_script_lists_the_three_keys(self):
        text = self.raw.decode("ascii").replace(chr(13) + chr(10), chr(10))
        head = text[:text.index(".PARAMETER Target")]
        for key in ("level", "aliases", "plans_dir"):
            self.assertIn(key, head)
        self.assertIn("tres campos", head)
        self.assertNotIn("dos campos", head)
        reader = text[text.index("# Lee y valida <Target>/synclayer-config.json"):text.index("function Read-LevelConfig")]
        self.assertIn("plans_dir", reader)
        self.assertIn("ConfigPlansPair", reader)
        self.assertIn("level, aliases y plans_dir", text)


class InstallCases:
    """Casos de install.ps1. Cada subclase fija self.exe (un interprete)."""

    exe = None
    label = ""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sys.stderr.write("\n[install.ps1] %s: %s (version %s)\n"
                         % (cls.label, cls.exe, shell_version(cls.exe)))

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="sync layer ", ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.src = os.path.join(self.tmp, "origen")
        self.home = os.path.join(self.tmp, "home")
        self.target = os.path.join(self.tmp, "destino")
        self.outside = os.path.join(self.tmp, "fuera")
        os.makedirs(self.src)
        os.makedirs(self.home)
        shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))

    # --- auxiliares ---

    def make_source(self, files=None, crlf=False):
        files = SAMPLE if files is None else files
        for rel, data in files.items():
            if crlf:
                data = data.replace(b"\n", b"\r\n")
            write(self.src, rel, data)
        with open(os.path.join(self.src, "install-manifest.json"), "wb") as f:
            f.write(manifest_for(self.src, sorted(files)).encode("ascii"))

    def run_install(self, *args, target=True, env_extra=None):
        cmd = [self.exe, "-NoProfile", "-NonInteractive"]
        if os.name == "nt":
            cmd += ["-ExecutionPolicy", "Bypass"]
        cmd += ["-File", os.path.join(self.src, "install.ps1")]
        if target:
            cmd += ["-Target", self.target]
        cmd += list(args)
        env = dict(os.environ)
        # Las dos variables que anulan model: y effort: (avisos de T6) no se heredan: la suite puede correr
        # dentro de una sesion que las defina. Una prueba que las necesite las pasa en env_extra.
        for name in ENV_OVERRIDE_VARS:
            env.pop(name, None)
        drive, tail = os.path.splitdrive(self.home)
        env.update({"USERPROFILE": self.home, "HOME": self.home,
                    "HOMEDRIVE": drive, "HOMEPATH": tail or self.home})
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(cmd, cwd=self.tmp, env=env, timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return (proc.returncode, proc.stdout.decode("utf-8", "replace"),
                proc.stderr.decode("utf-8", "replace"))

    def states(self, out):
        result = {}
        for line in out.splitlines():
            m = LINE.match(line.rstrip())
            if m:
                result[m.group(2)] = m.group(1)
        return result

    def write_state(self, files, schema=2, written=None, level=5, dests=None):
        """Estado previo en el destino, el de una instalacion anterior con esos archivos. schema=1: copia
        del manifiesto (instalador de la Fase 1); schema=2: el estado nuevo, con `written` (por defecto el
        hash del origen) y `level`; schema=3 (Fase 4): ademas `dest` por entrada, de `dests` {ruta: destino}
        (por defecto la propia ruta), con la referencia aliases_ref.state_for3."""
        old = os.path.join(self.tmp, "viejo")
        for rel, data in files.items():
            write(old, rel, data)
        manifest = manifest_for(old, sorted(files))
        if schema == 1:
            data = manifest.encode("ascii")
        elif schema == 3:
            data = ar.state_for3(manifest, written, level, dests)
        else:
            data = lr.state_for(manifest, written, level)
        write(self.target, "synclayer-manifest.json", data)

    def assert_state(self, level=5, out_hashes=None):
        """El estado del destino es, byte a byte, el que genera la referencia de Python para el origen."""
        self.assertEqual(read(self.target, "synclayer-manifest.json"),
                         lr.state_for(read(self.src, "install-manifest.json"), out_hashes, level))

    def assert_nothing_written_outside_target_and_backup(self):
        self.assertEqual(sorted(os.listdir(self.tmp)),
                         sorted(n for n in ("origen", "home", "destino") if os.path.exists(os.path.join(self.tmp, n))))

    # --- casos ---

    def test_case1_dryrun_on_populated_target_writes_nothing(self):
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        write(self.target, "settings.json", b"{}")
        write(self.target, "agents/ajeno.md", b"ajeno")
        before = snapshot(self.target)
        parent_before = sorted(os.listdir(self.tmp))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(snapshot(self.target), before)
        self.assertEqual(sorted(os.listdir(self.tmp)), parent_before)
        st = self.states(out)
        self.assertEqual(set(st.values()), {"IGUAL"})
        self.assertEqual(set(st), set(SAMPLE))
        self.assertIn("Resumen:", out)
        self.assert_quiet_when_nothing_written(out)

    def test_case2_dryrun_missing_target_all_new(self):
        self.make_source()
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out), {rel: "NUEVO" for rel in SAMPLE})
        self.assertFalse(os.path.exists(self.target))
        self.assert_nothing_written_outside_target_and_backup()

    def test_case6_altered_source_hash_exit2(self):
        self.make_source()
        write(self.src, "agents/beta.md", b"alterado despues del manifiesto\n")
        write(self.target, "agents/alfa.md", b"previo")
        before = snapshot(self.target)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 2, out + err)
        self.assertIn("agents/beta.md", err)
        self.assertEqual(snapshot(self.target), before)
        # primero revisar y restaurar; regenerar solo para un mantenedor con un cambio intencional
        self.assertIn("git diff", err)
        self.assertIn("vuelve a clonar", err)
        self.assertIn("mantenedor", err)
        self.assertLess(err.index("git diff"), err.index("build_manifest"))
        self.assertLess(err.index("mantenedor"), err.index("build_manifest"))

    def test_case6_missing_source_file_exit2(self):
        self.make_source()
        os.remove(os.path.join(self.src, "agents", "beta.md"))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 2, out + err)
        self.assertIn("agents/beta.md", err)
        self.assertFalse(os.path.exists(self.target))

    def test_case8_paths_with_spaces_dryrun(self):
        self.make_source()
        self.assertIn(" ", self.target)
        backup = os.path.join(self.tmp, "mi respaldo")
        code, out, err = self.run_install("-DryRun", "-BackupDir", backup)
        self.assertEqual(code, 0, out + err)
        self.assertIn(self.target, out)
        self.assertFalse(os.path.exists(backup))
        self.assertFalse(os.path.exists(self.target))

    def test_case9_local_change_without_force_exit3_dryrun(self):
        self.make_source()
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"version anterior\n"
        self.write_state(old)
        write(self.target, "agents/alfa.md", b"version anterior\n")      # ACTUALIZAR
        write(self.target, "agents/beta.md", b"editado a mano\n")        # MODIFICADO
        before = snapshot(self.target)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        st = self.states(out)
        self.assertEqual(st["agents/alfa.md"], "ACTUALIZAR")
        self.assertEqual(st["agents/beta.md"], "MODIFICADO")
        self.assertIn("agents/beta.md", err)
        self.assertIn("-Force", err)
        self.assertEqual(snapshot(self.target), before)

    def test_case9_force_dryrun_exit0(self):
        self.make_source()
        write(self.target, "agents/beta.md", b"editado a mano\n")
        code, out, err = self.run_install("-DryRun", "-Force")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/beta.md"], "MODIFICADO")

    def test_case11_existing_without_state_is_modified(self):
        self.make_source()
        write(self.target, "agents/alfa.md", b"distinto\n")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
        self.assertEqual(self.states(out)["agents/beta.md"], "NUEVO")

    def test_case12_existing_without_state_identical_is_igual(self):
        self.make_source()
        write(self.target, "agents/alfa.md", SAMPLE["agents/alfa.md"])
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "IGUAL")

    def test_unreadable_state_treated_as_absent_with_warning(self):
        self.make_source()
        write(self.target, "synclayer-manifest.json", b"{no es json")
        write(self.target, "agents/alfa.md", b"distinto\n")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
        self.assertIn("aviso", err)

    def test_case13_crlf_source_against_python_manifest(self):
        # Cruza las dos implementaciones del hash: origen en CRLF, manifiesto generado por Python.
        self.make_source(crlf=True)
        self.assertIn(b"\r\n", read(self.src, "agents/alfa.md"))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(set(self.states(out).values()), {"NUEVO"})

    def test_case13_crlf_destination_same_content_is_igual(self):
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data.replace(b"\n", b"\r\n"))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})

    def test_case13_lone_cr_in_destination_is_not_igual(self):
        self.make_source()
        write(self.target, "agents/beta.md", b"agente beta\r")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/beta.md"], "MODIFICADO")

    def test_case14_manifest_paths_outside_allowed_list(self):
        self.make_source()
        base = json.loads(read(self.src, "install-manifest.json"))
        good = base["files"][0]["sha256"]
        bad_paths = [
            "../x", "docs/brand/a.md", "C:/x", "settings.json", "/agents/a.md",
            "agents\\a.md", "agents/a.md\n", "agents/A.md", "agents/sub/x.md",
            "agents/a.txt", "hooks/otro.ps1", "agents/..md", "agents/a.md:x",
            "//srv/share/a.md", "\\\\srv\\share\\a.md",
            "agents/a‐b.md", "agents/K.md", "agents/ａ.md",
        ] + ["agents/" + n + ".md" for n in
             ("con", "prn", "aux", "nul", "com0", "com1", "com9", "lpt0", "lpt1", "lpt9")]
        for bad in bad_paths:
            with self.subTest(path=bad):
                m = dict(base)
                m["files"] = base["files"] + [{"path": bad, "sha256": good}]
                write(self.src, "install-manifest.json", json.dumps(m).encode("ascii"))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertFalse(os.path.exists(self.target))
                self.assertEqual(self.states(out), {})

    def test_case14_trailing_newline_path_rejected_even_if_file_exists(self):
        # \z y no $: en .NET $ y \Z aceptan un salto de linea final.
        self.make_source({"agents/a.md": b"x\n"})
        m = json.loads(read(self.src, "install-manifest.json"))
        m["files"][0]["path"] = "agents/a.md\n"
        write(self.src, "install-manifest.json", json.dumps(m).encode("ascii"))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertIn("agents/a.md", err)

    def test_case14_duplicate_path_rejected(self):
        self.make_source()
        m = json.loads(read(self.src, "install-manifest.json"))
        m["files"].append(dict(m["files"][0]))
        write(self.src, "install-manifest.json", json.dumps(m).encode("ascii"))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertIn("duplicada", err)

    def test_case15_manifest_missing_or_invalid(self):
        self.make_source()
        good = json.loads(read(self.src, "install-manifest.json"))
        sha = good["files"][0]["sha256"]
        variants = {
            "json invalido": b"{no es json",
            "vacio": b"",
            "schema 2": json.dumps(dict(good, schema=2)).encode(),
            "schema texto": json.dumps(dict(good, schema="1")).encode(),
            "schema true": json.dumps(dict(good, schema=True)).encode(),
            "algorithm md5": json.dumps(dict(good, algorithm="md5")).encode(),
            "sin files": json.dumps({"schema": 1, "algorithm": "sha256"}).encode(),
            "files vacio": json.dumps(dict(good, files=[])).encode(),
            "sha corto": json.dumps(dict(good, files=[{"path": "agents/alfa.md", "sha256": "abc"}])).encode(),
            "sha mayusculas": json.dumps(dict(good, files=[{"path": "agents/alfa.md", "sha256": sha.upper()}])).encode(),
            "sin path": json.dumps(dict(good, files=[{"sha256": sha}])).encode(),
            "files objeto": json.dumps(dict(good, files=good["files"][0])).encode(),
            "files texto": json.dumps(dict(good, files="agents/alfa.md")).encode(),
            "files null": json.dumps(dict(good, files=None)).encode(),
            "files [null]": json.dumps(dict(good, files=[None])).encode(),
            "files [texto]": json.dumps(dict(good, files=["agents/alfa.md"])).encode(),
            "clave Schema": json.dumps(rename(good, "schema", "Schema")).encode(),
            "clave Files": json.dumps(rename(good, "files", "Files")).encode(),
            "clave Algorithm": json.dumps(rename(good, "algorithm", "Algorithm")).encode(),
            "clave PATH": json.dumps(dict(good, files=[{"PATH": "agents/alfa.md", "sha256": sha}])).encode(),
            "clave SHA256": json.dumps(dict(good, files=[{"path": "agents/alfa.md", "SHA256": sha}])).encode(),
            "algorithm SHA256": json.dumps(dict(good, algorithm="SHA256")).encode(),
        }
        for name, content in variants.items():
            with self.subTest(case=name):
                write(self.src, "install-manifest.json", content)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertFalse(os.path.exists(self.target))
        os.remove(os.path.join(self.src, "install-manifest.json"))
        with self.subTest(case="ausente"):
            code, out, err = self.run_install("-DryRun")
            self.assertEqual(code, 1, out + err)
            self.assertIn("install-manifest.json", err)

    def test_case16_orphan_reported_and_kept(self):
        self.make_source()
        old = dict(SAMPLE)
        old["agents/viejo.md"] = b"de una version anterior\n"
        self.write_state(old)
        for rel, data in old.items():
            write(self.target, rel, data)
        before = snapshot(self.target)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/viejo.md"], "HUERFANO")
        self.assertEqual(snapshot(self.target), before)
        self.assertTrue(os.path.exists(os.path.join(self.target, "agents", "viejo.md")))

    def test_empty_target_rejected(self):
        self.make_source()
        code, out, err = self.run_install("-DryRun", "-Target", "", target=False)
        self.assertEqual(code, 1, out + err)
        self.assertIn("-Target no puede estar vacio", err)

    # --- validacion del destino: -DryRun y la real dan el mismo codigo ---

    def assert_same_exit(self, expected, *args, expect_err=None, with_backup=False, **kw):
        """-DryRun y la real dan el mismo codigo. La variante con -BackupDir (2 lanzamientos mas) es
        opcional: las validaciones del destino no dependen del respaldo."""
        respaldo = os.path.join(self.tmp, "respaldo")
        variants = [[], ["-BackupDir", respaldo]] if with_backup else [[]]
        for extra in variants:
            for mode in (["-DryRun"], []):
                with self.subTest(mode=mode, extra=extra):
                    code, out, err = self.run_install(*(mode + extra + list(args)), **kw)
                    self.assertEqual(code, expected, out + err)
                    if expect_err:
                        self.assertIn(expect_err, err)
        self.assertFalse(os.path.exists(respaldo))

    def test_target_that_is_a_file_exit1(self):
        self.make_source()
        write(self.tmp, "destino", b"soy un archivo")
        self.assert_same_exit(1)
        self.assertEqual(read(self.tmp, "destino"), b"soy un archivo")

    def test_intermediate_folder_that_is_a_file_exit1(self):
        self.make_source()
        write(self.target, "agents", b"soy un archivo")
        self.assert_same_exit(1, expect_err="agents")

    def test_target_below_a_file_exit1(self):
        self.make_source()
        write(self.tmp, "destino", b"soy un archivo")
        self.target = os.path.join(self.target, "sub")
        self.assert_same_exit(1)

    def test_destination_that_is_a_folder_exit1(self):
        self.make_source()
        os.makedirs(os.path.join(self.target, "agents", "alfa.md"))
        self.assert_same_exit(1, expect_err="es una carpeta")

    @unittest.skipUnless(os.name == "nt", "los proveedores del registro solo existen en Windows")
    def test_non_filesystem_provider_exit1(self):
        self.make_source()
        self.target = "HKCU:\\Software\\SyncLayerPruebaInexistente"
        self.assert_same_exit(1)

    def test_default_backup_is_absolute_sibling_of_target(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        m = re.search(r"^Respaldo: (.*)$", out, re.M)
        self.assertIsNotNone(m, out)
        backup = m.group(1).strip()
        self.assertTrue(os.path.isabs(backup), backup)
        self.assertRegex(backup, re.escape(self.target) + r"-backup-\d{8}-\d{6}$")

    def test_relative_backup_dir_is_resolved_to_absolute(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        code, out, err = self.run_install("-DryRun", "-BackupDir", "rel respaldo")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Respaldo: " + os.path.join(self.tmp, "rel respaldo"), out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "rel respaldo")))

    @unittest.skipUnless(os.name == "nt", "raiz de unidad de Windows")
    def test_drive_root_target_needs_explicit_backup_dir(self):
        self.make_source()
        root = os.path.splitdrive(self.tmp)[0] + "\\"
        code, out, err = self.run_install("-DryRun", "-Target", root, target=False)
        self.assertEqual(code, 1, out + err)
        self.assertIn("-BackupDir", err)
        self.assertNotIn("Respaldo:", out)

    # --- canal de salida: plan y nota de HUERFANO por stdout; avisos y errores por stderr ---

    def test_orphan_note_is_stdout_and_not_a_warning(self):
        self.make_source()
        old = dict(SAMPLE)
        old["agents/viejo.md"] = b"de una version anterior\n"
        self.write_state(old)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertIn("nota:", out)
        self.assertNotIn("aviso", out)
        self.assertEqual(err, "")

    # --- mensajes: solo ASCII imprimible y sin texto interno de PowerShell ---

    def test_non_ascii_manifest_paths_are_escaped_in_errors(self):
        self.make_source()
        base = json.loads(read(self.src, "install-manifest.json"))
        good = base["files"][0]["sha256"]
        for bad, esc in (("agents/a‐b.md", "\\u2010"), ("agents/K.md", "\\u212a")):
            with self.subTest(path=bad):
                m = dict(base, files=base["files"] + [{"path": bad, "sha256": good}])
                write(self.src, "install-manifest.json", json.dumps(m).encode("ascii"))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertIn(esc, err.lower())
                self.assertTrue(err.isascii(), repr(err))
                self.assertNotIn(bad, err)

    def test_non_ascii_target_is_escaped_in_error(self):
        self.make_source()
        self.target = os.path.join(self.tmp, "dest‐inoK")
        write(self.target, "agents", b"soy un archivo")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertIn("\\u2010", err)
        self.assertIn("\\u212a", err.lower())
        self.assertTrue(err.isascii(), repr(err))

    def test_broken_json_message_has_no_powershell_internals_or_manifest_text(self):
        self.make_source()
        raw = read(self.src, "install-manifest.json")
        write(self.src, "install-manifest.json", raw[: len(raw) // 2])
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertIn("install-manifest.json", err)
        for leak in ("ConvertFrom-Json", "Exception", "agents/", "sha256", "At line", "Cannot"):
            self.assertNotIn(leak, err)

    def test_files_null_entry_message(self):
        self.make_source()
        m = json.loads(read(self.src, "install-manifest.json"))
        m["files"] = [None]
        write(self.src, "install-manifest.json", json.dumps(m).encode("ascii"))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertIn("una entrada de files no tiene path de texto", err)

    # --- mutaciones que antes no rompian ninguna prueba ---

    def test_bom_in_source_file_is_hashed_as_is(self):
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"\xef\xbb\xbfagente alfa\n"
        self.make_source(files)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "NUEVO")

    def test_lone_cr_in_source_is_kept_and_crlf_is_folded(self):
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"a\rb\r\nc\r"
        self.make_source(files)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "NUEVO")

    def test_state_without_the_path_and_different_destination_is_modified(self):
        self.make_source()
        self.write_state({"agents/beta.md": SAMPLE["agents/beta.md"]})
        write(self.target, "agents/alfa.md", b"otra cosa\n")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")

    def test_state_hash_differs_from_destination_is_modified(self):
        self.make_source()
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"version anterior\n"
        self.write_state(old)
        write(self.target, "agents/alfa.md", b"editado sobre otra version\n")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")

    def test_real_repo_files_as_source_dryrun(self):
        # Copia el instalador, el manifiesto y los doce archivos reales a un origen temporal.
        raw = read(ROOT, "install-manifest.json")
        write(self.src, "install-manifest.json", raw)
        for entry in json.loads(raw)["files"]:
            write(self.src, entry["path"], read(ROOT, entry["path"]))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        st = self.states(out)
        self.assertEqual(len(st), 12)
        self.assertEqual(set(st.values()), {"NUEVO"})
        self.assertFalse(any(p.startswith(("docs/brand", "tests", "tools")) for p in st))
        self.assertFalse(os.path.exists(self.target))

    # --- T4: copia real ---

    def preinstall(self):
        """Deja el destino como lo deja una instalacion limpia (los archivos canonicos y el estado), sin
        lanzar PowerShell: solo para pruebas que necesitan ese punto de partida y no prueban la instalacion.
        El estado es el de esquema 2 que deja el instalador: asi estas pruebas no ganan un respaldo por migracion."""
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        write(self.target, "synclayer-manifest.json", lr.state_for(read(self.src, "install-manifest.json")))

    def install_ok(self, *args):
        code, out, err = self.run_install(*args)
        self.assertEqual(code, 0, out + err)
        return out, err

    def leftover_temps(self):
        found = []
        for dirpath, _dirs, files in os.walk(self.target):
            found += [os.path.join(dirpath, f) for f in files if f.endswith(".tmp")]
        return found

    def patch_script(self, after_line, code, before=False):
        """Inserta codigo PowerShell en la COPIA del script de prueba, tras la linea que empieza igual
        (o justo antes de ella con before=True)."""
        path = os.path.join(self.src, "install.ps1")
        with open(path, "rb") as f:
            lines = f.read().decode("ascii").split("\n")
        idx = [i for i, l in enumerate(lines) if l.strip().startswith(after_line)]
        self.assertEqual(len(idx), 1, after_line)
        lines.insert(idx[0] if before else idx[0] + 1, code)
        with open(path, "wb") as f:
            f.write("\n".join(lines).encode("ascii"))

    def update_source(self, rel, data):
        files = dict(SAMPLE)
        files[rel] = data
        self.make_source(files)
        return files

    def test_case3_clean_install_in_empty_target(self):
        self.make_source()
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        for rel, data in SAMPLE.items():
            self.assertEqual(read(self.target, rel), data)
        self.assert_state(5)
        self.assertFalse(os.path.exists(backup))
        self.assertEqual(self.leftover_temps(), [])
        self.assertEqual(sorted(os.listdir(self.tmp)), ["destino", "home", "origen"])

    def test_case3_missing_intermediate_folders_are_created(self):
        self.make_source()
        write(self.target, "settings.json", b"{}")
        self.install_ok()
        self.assertEqual(read(self.target, "docs/agentes.md"), SAMPLE["docs/agentes.md"])
        self.assertEqual(read(self.target, "settings.json"), b"{}")

    def test_hook_is_copied_first_and_final_message(self):
        self.make_source()
        out, err = self.install_ok()
        copied = [l.split(": ", 1)[1].strip() for l in out.splitlines() if l.startswith("Copiado: ")]
        self.assertEqual(copied[0], "hooks/agent_guard.py")
        self.assertEqual(sorted(copied), sorted(SAMPLE))
        self.assertIn("reinicia las sesiones de Claude Code", out)
        self.assertIn("no hay sincronizacion automatica", out)
        self.assertIn("settings.json", out)
        self.assertNotIn("sincronizado", out.lower())

    def test_hook_first_also_on_update(self):
        self.make_source()
        self.preinstall()
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"alfa 2\n"
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_source(files)
        out, err = self.install_ok("-BackupDir", os.path.join(self.tmp, "respaldo"))
        copied = [l.split(": ", 1)[1].strip() for l in out.splitlines() if l.startswith("Copiado: ")]
        self.assertEqual(copied, ["hooks/agent_guard.py", "agents/alfa.md"])

    def test_case4_update_creates_verifiable_backup(self):
        self.make_source()
        self.preinstall()
        old_state = read(self.target, "synclayer-manifest.json")
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        backup = os.path.join(self.tmp, "mi respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(read(self.target, "agents/alfa.md"), b"alfa nueva\n")
        self.assertEqual(read(backup, "agents/alfa.md"), SAMPLE["agents/alfa.md"])
        self.assertEqual(read(backup, "synclayer-manifest.json"), old_state)
        # solo lo que cambia: beta, reglas, hook y docs no se respaldan
        saved = sorted(os.path.relpath(os.path.join(d, f), backup).replace("\\", "/")
                       for d, _s, fs in os.walk(backup) for f in fs)
        self.assertEqual(saved, ["agents/alfa.md", "synclayer-manifest.json"])
        self.assertEqual(self.states(out)["agents/alfa.md"], "ACTUALIZAR")
        self.assert_state(5)
        self.assertIn(backup, out)
        self.assertEqual(self.leftover_temps(), [])

    def test_case4_default_backup_dir_is_created_next_to_target(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        self.install_ok()
        backups = [n for n in os.listdir(self.tmp) if n.startswith("destino-backup-")]
        self.assertEqual(len(backups), 1, os.listdir(self.tmp))
        self.assertEqual(read(os.path.join(self.tmp, backups[0]), "agents/alfa.md"),
                         SAMPLE["agents/alfa.md"])

    def test_case5_foreign_files_untouched(self):
        self.make_source()
        foreign = {"hooks/otro-statusline.ps1": b"ajeno", "agents/ajeno.md": b"ajeno md",
                   "settings.json": b"{}", "CLAUDE.md": b"mio"}
        for rel, data in foreign.items():
            write(self.target, rel, data)
        before = {rel: os.stat(os.path.join(self.target, *rel.split("/"))).st_mtime_ns for rel in foreign}
        self.install_ok()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        backup = os.path.join(self.tmp, "respaldo")
        self.install_ok("-BackupDir", backup)
        for rel, data in foreign.items():
            p = os.path.join(self.target, *rel.split("/"))
            self.assertEqual(read(self.target, rel), data)
            self.assertEqual(os.stat(p).st_mtime_ns, before[rel])
            self.assertFalse(os.path.exists(os.path.join(backup, *rel.split("/"))))

    def assert_quiet_when_nothing_written(self, out):
        for text in ("Respaldo", "Verificado", "Recordatorio", "reinicia"):
            self.assertNotIn(text, out)

    def test_case7_rerun_is_idempotent(self):
        self.make_source()
        self.install_ok()
        snap = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        out, err = self.install_ok()
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertEqual(snapshot(self.target), snap)
        self.assertEqual(sorted(os.listdir(self.tmp)), listing)
        self.assertIn("escritos=0", out)
        self.assert_quiet_when_nothing_written(out)

    def test_case8_paths_with_spaces_real_run(self):
        self.make_source()
        self.assertIn(" ", self.target)
        self.install_ok("-BackupDir", os.path.join(self.tmp, "mi respaldo"))
        self.assertEqual(read(self.target, "agents/alfa.md"), SAMPLE["agents/alfa.md"])

    def test_case12_identical_without_state_writes_only_state(self):
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        before = {rel: os.stat(os.path.join(self.target, *rel.split("/"))).st_mtime_ns for rel in SAMPLE}
        out, err = self.install_ok()
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assert_state(5)
        for rel in SAMPLE:
            self.assertEqual(os.stat(os.path.join(self.target, *rel.split("/"))).st_mtime_ns, before[rel])
        self.assertEqual(sorted(os.listdir(self.tmp)), ["destino", "home", "origen"])
        self.assert_quiet_when_nothing_written(out)

    def test_case13_crlf_source_writes_lf_bytes(self):
        self.make_source(crlf=True)
        self.assertIn(b"\r\n", read(self.src, "agents/alfa.md"))
        self.install_ok()
        for rel, data in SAMPLE.items():
            self.assertEqual(read(self.target, rel), data)
            self.assertNotIn(b"\r", read(self.target, rel))

    def test_case13_crlf_destination_is_igual_and_not_rewritten(self):
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data.replace(b"\n", b"\r\n"))
        self.install_ok()
        self.assertIn(b"\r\n", read(self.target, "agents/alfa.md"))

    def test_case17_existing_backup_is_not_overwritten_exit1(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        backup = os.path.join(self.tmp, "respaldo")
        write(backup, "agents/alfa.md", b"respaldo anterior")
        before_t, before_b = snapshot(self.target), snapshot(backup)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*(mode + ["-BackupDir", backup]))
                self.assertEqual(code, 1, out + err)
                self.assertIn("ya existe el respaldo", err)
                self.assertIn("-BackupDir", err)
                self.assertEqual(snapshot(backup), before_b)
                self.assertEqual(snapshot(self.target), before_t)

    def test_backup_dir_that_is_a_file_exit1_in_both_modes(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        backup = os.path.join(self.tmp, "respaldo")
        write(self.tmp, "respaldo", b"soy un archivo")
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*(mode + ["-BackupDir", backup]))
                self.assertEqual(code, 1, out + err)
                self.assertEqual(snapshot(self.target), before)

    def test_case18_real_repo_as_source_real_run(self):
        raw = read(ROOT, "install-manifest.json")
        write(self.src, "install-manifest.json", raw)
        for entry in json.loads(raw)["files"]:
            write(self.src, entry["path"], read(ROOT, entry["path"]))
        self.install_ok()
        got = sorted(os.path.relpath(os.path.join(d, f), self.target).replace("\\", "/")
                     for d, _s, fs in os.walk(self.target) for f in fs)
        want = sorted([e["path"] for e in json.loads(raw)["files"]] + ["synclayer-manifest.json"])
        self.assertEqual(got, want)
        self.assertEqual(len(want), 13)
        self.assertFalse(os.path.exists(os.path.join(self.target, "docs", "brand")))
        self.assertFalse(os.path.exists(os.path.join(self.target, "tests")))
        for entry in json.loads(raw)["files"]:
            self.assertEqual(bm.canonical_sha256(read(self.target, entry["path"])), entry["sha256"])
        self.assert_state(5)
        state = json.loads(read(self.target, "synclayer-manifest.json"))
        self.assertEqual(state["schema"], 2)
        self.assertEqual({f["level"] for f in state["files"]}, {5})
        self.assertTrue(all(f["written"] == f["sha256"] for f in state["files"]))

    def test_real_run_altered_source_exit2_writes_nothing(self):
        self.make_source()
        write(self.src, "agents/beta.md", b"alterado\n")
        code, out, err = self.run_install("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 2, out + err)
        self.assertIn("agents/beta.md", err)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["home", "origen"])

    def test_real_run_modified_without_force_exit3_writes_nothing(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        write(self.target, "agents/beta.md", b"editado a mano\n")
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 3, out + err)
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(os.path.exists(backup))

    def test_written_bytes_are_the_verified_ones_not_a_reread(self):
        # Tras verificar el origen se cambia el archivo en disco; el destino debe tener lo verificado.
        self.make_source()
        evil = os.path.join(self.src, "agents", "alfa.md").replace("'", "''")
        self.patch_script("# Paso 3:", "[System.IO.File]::WriteAllBytes('%s', [byte[]]@(88,88))" % evil)
        self.install_ok()
        self.assertEqual(read(self.src, "agents/alfa.md"), b"XX")
        self.assertEqual(read(self.target, "agents/alfa.md"), SAMPLE["agents/alfa.md"])

    def test_verification_detects_corrupted_file_exit4(self):
        self.make_source()
        victim = os.path.join(self.target, "rules", "agentes.md").replace("'", "''")
        self.patch_script("# Paso 8:", "[System.IO.File]::WriteAllBytes('%s', [byte[]]@(65))" % victim)
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("la verificacion posterior fallo", err)
        self.assertIn("rules/agentes.md", err)
        self.assertIn("Escrito hasta ahora", err)
        self.assertFalse(os.path.exists(os.path.join(self.target, "synclayer-manifest.json")))
        self.assertEqual(self.leftover_temps(), [])

    def make_readonly(self, rel):
        path = os.path.join(self.target, *rel.split("/"))
        os.chmod(path, stat.S_IREAD)
        self.addCleanup(os.chmod, path, stat.S_IWRITE | stat.S_IREAD)

    def inject_readonly_at_step7(self, rel):
        """Simula un destino que se vuelve de solo lectura DESPUES de clasificar (fallo solo al escribir)."""
        path = os.path.join(self.target, *rel.split("/"))
        self.addCleanup(lambda: os.path.exists(path) and os.chmod(path, stat.S_IWRITE | stat.S_IREAD))
        self.patch_script("# Paso 7:", "[System.IO.File]::SetAttributes('%s', [System.IO.FileAttributes]::ReadOnly)"
                          % path.replace("'", "''"))

    @unittest.skipUnless(os.name == "nt", "el atributo de solo lectura bloquea el reemplazo solo en Windows")
    def test_copy_failure_mid_run_exit4_keeps_backup_and_hook_intact(self):
        self.make_source()
        self.preinstall()
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"alfa 2\n"
        files["agents/beta.md"] = b"beta 2\n"
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_source(files)
        self.inject_readonly_at_step7("agents/beta.md")   # bloquea el reemplazo de beta
        backup = os.path.join(self.tmp, "respaldo")
        old_state = read(self.target, "synclayer-manifest.json")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 4, out + err)
        self.assertNotIn("\\u000d", err)
        self.assertIn("agents/beta.md", err)
        self.assertIn(backup, err)
        # el hook va primero y quedo completo y verificado
        self.assertEqual(read(self.target, "hooks/agent_guard.py"), files["hooks/agent_guard.py"])
        self.assertIn("hooks/agent_guard.py", err.split("Escrito hasta ahora")[1])
        # lo que no se pudo escribir conserva su version anterior; el respaldo la tiene
        self.assertEqual(read(self.target, "agents/beta.md"), SAMPLE["agents/beta.md"])
        self.assertEqual(read(backup, "agents/beta.md"), SAMPLE["agents/beta.md"])
        self.assertEqual(read(backup, "hooks/agent_guard.py"), SAMPLE["hooks/agent_guard.py"])
        # el estado viejo sigue y no queda ningun temporal
        self.assertEqual(read(self.target, "synclayer-manifest.json"), old_state)
        self.assertEqual(self.leftover_temps(), [])
        # cada archivo del destino es la version vieja o la nueva, nunca una intermedia
        for rel, data in files.items():
            self.assertIn(read(self.target, rel), (data, SAMPLE.get(rel)))

    @unittest.skipUnless(os.name == "nt", "el atributo de solo lectura bloquea el reemplazo solo en Windows")
    def test_hook_copy_failure_writes_no_agent(self):
        self.make_source()
        self.preinstall()
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"alfa 2\n"
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_source(files)
        self.inject_readonly_at_step7("hooks/agent_guard.py")
        code, out, err = self.run_install("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 4, out + err)
        self.assertIn("No se escribio ningun archivo del destino", err)
        self.assertEqual(read(self.target, "hooks/agent_guard.py"), SAMPLE["hooks/agent_guard.py"])
        self.assertEqual(read(self.target, "agents/alfa.md"), SAMPLE["agents/alfa.md"])
        self.assertEqual(self.leftover_temps(), [])

    def test_force_overwrites_modified_with_backup(self):
        self.make_source()
        write(self.target, "agents/beta.md", b"editado a mano\n")
        backup = os.path.join(self.tmp, "respaldo")
        self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(read(backup, "agents/beta.md"), b"editado a mano\n")
        self.assertEqual(read(self.target, "agents/beta.md"), SAMPLE["agents/beta.md"])

    def test_orphan_is_kept_after_real_install(self):
        self.make_source()
        old = dict(SAMPLE)
        old["agents/viejo.md"] = b"de una version anterior\n"
        self.write_state(old)
        for rel, data in old.items():
            write(self.target, rel, data)
        out, err = self.install_ok("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(self.states(out)["agents/viejo.md"], "HUERFANO")
        self.assertEqual(read(self.target, "agents/viejo.md"), b"de una version anterior\n")

    # --- Fase 3, T2: estado con esquema 2 (hash del origen, written y level) y migracion del esquema 1 ---

    STATE = "synclayer-manifest.json"

    def sha(self, data):
        return bm.canonical_sha256(data)

    def test_t2_case6_state_bytes_are_the_python_serialization(self):
        # Caso 6: los bytes del estado de PowerShell son los de json.dumps(indent=2) de Python.
        self.make_source()
        self.install_ok()
        raw = read(self.target, self.STATE)
        self.assertEqual(raw, lr.state_for(read(self.src, "install-manifest.json"), None, 5))
        self.assertTrue(raw.isascii())
        self.assertNotIn(b"\r", raw)
        self.assertTrue(raw.endswith(b"}\n"))
        self.assertFalse(raw.endswith(b"\n\n"))
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        # independiente de state_for: releer el JSON y volver a serializarlo da los mismos bytes
        data = json.loads(raw)
        self.assertEqual((json.dumps(data, indent=2, ensure_ascii=True) + "\n").encode("ascii"), raw)
        self.assertEqual(list(data), ["schema", "algorithm", "eol", "files"])
        self.assertEqual(data["schema"], 2)
        self.assertEqual([list(f) for f in data["files"]], [["path", "sha256", "written", "level"]] * len(SAMPLE))
        self.assertEqual([f["path"] for f in data["files"]], sorted(SAMPLE))
        for f in data["files"]:
            self.assertEqual(f["written"], f["sha256"])
            self.assertEqual(f["level"], 5)
            self.assertIs(type(f["level"]), int)

    def test_t2_case6_state_with_crlf_source_is_still_lf(self):
        self.make_source(crlf=True)
        self.install_ok()
        self.assert_state(5)
        self.assertNotIn(b"\r", read(self.target, self.STATE))

    def test_t2_case7_schema1_state_intact_destination_is_igual_and_migrates(self):
        # Caso 7: estado de la Fase 1 con el destino intacto: todo IGUAL; el estado migra y el viejo va al respaldo.
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        self.write_state(SAMPLE, schema=1)
        old_state = read(self.target, self.STATE)
        self.assertEqual(json.loads(old_state)["schema"], 1)
        before_dry = snapshot(self.target)
        listing_dry = sorted(os.listdir(self.tmp))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertIn("Respaldo:", out)
        self.assertEqual(snapshot(self.target), before_dry)
        self.assertEqual(sorted(os.listdir(self.tmp)), listing_dry)
        self.assertEqual(read(self.target, self.STATE), old_state)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertIn("escritos=0", out)
        self.assertNotIn("Se trata como ausente", err)
        self.assert_state(5)
        self.assertEqual(read(backup, self.STATE), old_state)
        saved = sorted(os.path.relpath(os.path.join(d, f), backup).replace("\\", "/")
                       for d, _s, fs in os.walk(backup) for f in fs)
        self.assertEqual(saved, [self.STATE])
        for rel, data in SAMPLE.items():
            self.assertEqual(read(self.target, rel), data)
        # segunda corrida: ya es esquema 2, sin escrituras ni respaldo, solo IGUAL
        after = snapshot(self.target)
        backup2 = os.path.join(self.tmp, "respaldo2")
        out, err = self.install_ok("-BackupDir", backup2)
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertEqual(snapshot(self.target), after)
        self.assertFalse(os.path.exists(backup2))
        self.assertNotIn("Estado:", out)
        self.assert_quiet_when_nothing_written(out)

    def test_t2_case8_schema1_state_with_changed_source_is_actualizar(self):
        # Caso 8: el destino coincide con el estado viejo y el origen cambio: ACTUALIZAR, como antes.
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        self.write_state(SAMPLE, schema=1)
        old_state = read(self.target, self.STATE)
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        st = self.states(out)
        self.assertEqual(st["agents/alfa.md"], "ACTUALIZAR")
        self.assertEqual({v for k, v in st.items() if k != "agents/alfa.md"}, {"IGUAL"})
        self.assertEqual(read(self.target, "agents/alfa.md"), b"alfa nueva\n")
        self.assertEqual(read(backup, "agents/alfa.md"), SAMPLE["agents/alfa.md"])
        self.assertEqual(read(backup, self.STATE), old_state)
        self.assert_state(5)

    def valid_old_state(self):
        """Escribe en el destino el estado esquema 2 de una instalacion anterior con alfa vieja y lo devuelve como dict."""
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"alfa vieja\n"
        self.write_state(old)
        return json.loads(read(self.target, self.STATE))

    def dump_state(self, data):
        if isinstance(data, (bytes, bytearray)):
            raw = bytes(data)
        else:
            raw = (json.dumps(data, indent=2, ensure_ascii=True) + "\n").encode("ascii")
        write(self.target, self.STATE, raw)
        return raw

    def test_t2_case9_invalid_schema2_state_is_absent_and_never_actualizar(self):
        # Caso 9: un estado esquema 2 invalido se trata como ausente: con la edicion o la version vieja en el
        # destino sale MODIFICADO (nunca ACTUALIZAR), con aviso por stderr, y el estado no se respalda ni toca.
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"alfa vieja\n"

        def entry(d, rel="agents/alfa.md"):
            return next(f for f in d["files"] if f["path"] == rel)

        def top(key, value):
            def mut(d):
                d[key] = value
            return mut

        def field(key, value):
            def mut(d):
                entry(d)[key] = value
            return mut

        def drop(key):
            def mut(d):
                del entry(d)[key]
            return mut

        def extra_top(d):
            d["extra"] = 1

        def extra_entry(d):
            entry(d)["extra"] = 1

        def unicode_key(d):
            d["claveé"] = 1

        def bad_path(d):
            entry(d)["path"] = "settings.json"

        def dup_path(d):
            d["files"].append(dict(entry(d)))

        def empty_files(d):
            d["files"] = []

        def upper_written(d):
            entry(d)["written"] = entry(d)["written"].upper()

        def rename_key(owner, old_key, new_key):
            def mut(d):
                target = d if owner == "top" else entry(d)
                items = list(target.items())
                target.clear()
                for k, v in items:
                    target[new_key if k == old_key else k] = v
            return mut

        variants = {
            "clave eol con NUL": rename_key("top", "eol", "eol\u0000"),
            "clave written con NUL": rename_key("entry", "written", "written\u0000"),
            "clave level con NUL": rename_key("entry", "level", "level\u0000"),
            "clave schema con NUL": rename_key("top", "schema", "schema\u0000"),
            "algorithm con guion blando": top("algorithm", "sha\u00ad256"),
            "algorithm con NUL": top("algorithm", "sha256\u0000"),
            "eol con NUL": top("eol", "lf\u0000"),
            "eol con guion blando": top("eol", "l\u00adf"),
            "level 6": field("level", 6),
            "written de 65 caracteres": field("written", "a" * 65),
            "written no hexadecimal": field("written", "z" * 64),
            "written en mayusculas": upper_written,
            "written corto": field("written", "abc"),
            "written numero": field("written", 5),
            "written null": field("written", None),
            "sin written": drop("written"),
            "level 9": field("level", 9),
            "level 0": field("level", 0),
            "level texto": field("level", "5"),
            "level decimal": field("level", 5.0),
            "level booleano": field("level", True),
            "level null": field("level", None),
            "sin level": drop("level"),
            "schema 3": top("schema", 3),
            "schema 0": top("schema", 0),
            "schema texto": top("schema", "2"),
            "schema decimal": top("schema", 2.0),
            "algorithm md5": top("algorithm", "md5"),
            "eol crlf": top("eol", "crlf"),
            "clave de mas en la raiz": extra_top,
            "clave de mas en una entrada": extra_entry,
            "clave no ASCII": unicode_key,
            "ruta fuera de la lista": bad_path,
            "ruta duplicada": dup_path,
            "files vacio": empty_files,
        }
        for name, mutate in variants.items():
            with self.subTest(case=name):
                shutil.rmtree(self.target, ignore_errors=True)
                for rel, data in old.items():
                    write(self.target, rel, data)
                data = self.valid_old_state()
                mutate(data)
                raw = self.dump_state(data)
                before = snapshot(self.target)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 3, out + err)
                self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
                self.assertNotIn("ACTUALIZAR", set(self.states(out).values()))
                self.assert_clean_unreadable_warning(err)
                self.assertEqual(snapshot(self.target), before)
                self.assertEqual(read(self.target, self.STATE), raw)
                if name == "clave no ASCII":
                    self.assertIn("\\u00e9", err)

    def test_t2_case9_control_valid_schema2_state_gives_actualizar(self):
        # Control de la prueba anterior: sin el campo invalido, el mismo estado da ACTUALIZAR.
        self.make_source()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"alfa vieja\n"
        for rel, data in old.items():
            write(self.target, rel, data)
        self.write_state(old)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "ACTUALIZAR")
        self.assertEqual(err, "")

    def test_t2_case9_oversized_state_is_absent(self):
        self.make_source()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"alfa vieja\n"
        for rel, data in old.items():
            write(self.target, rel, data)
        self.write_state(old)
        raw = read(self.target, self.STATE) + b" " * 1100000
        write(self.target, self.STATE, raw)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
        self.assert_clean_unreadable_warning(err)

    def test_t2_case9_state_size_limit_is_exact(self):
        # 1048576 bytes validos se leen (ACTUALIZAR); un byte mas, estado ausente (MODIFICADO).
        self.update_source("agents/alfa.md", b"alfa nueva" + bytes([10]))
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"alfa vieja" + bytes([10])
        for extra, expected, code_expected in ((0, "ACTUALIZAR", 0), (1, "MODIFICADO", 3)):
            with self.subTest(extra=extra):
                shutil.rmtree(self.target, ignore_errors=True)
                for rel, data in old.items():
                    write(self.target, rel, data)
                self.write_state(old)
                raw = read(self.target, self.STATE)
                raw += b" " * (1048576 + extra - len(raw))
                self.assertEqual(len(raw), 1048576 + extra)
                write(self.target, self.STATE, raw)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, code_expected, out + err)
                self.assertEqual(self.states(out)["agents/alfa.md"], expected)

    def test_t2_install_manifest_algorithm_is_compared_ordinally(self):
        # Read-Manifest: algorithm con guion blando o NUL no es sha256.
        self.make_source()
        good = json.loads(read(self.src, "install-manifest.json"))
        for name, value in (("guion blando", "sha\u00ad256"), ("NUL", "sha256\u0000")):
            with self.subTest(case=name):
                write(self.src, "install-manifest.json", json.dumps(dict(good, algorithm=value)).encode("ascii"))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertIn("algorithm debe ser sha256", err)
                self.assertFalse(os.path.exists(self.target))

    def test_t2_case9_invalid_state_real_run_is_replaced_without_backup(self):
        # No se respalda un estado no reconocido; con -Force el estado se reescribe en esquema 2.
        for name, mutate in (("schema 3", lambda d: d.update(schema=3)),
                             ("written invalido", lambda d: d["files"][0].update(written="XYZ"))):
            with self.subTest(case=name):
                shutil.rmtree(self.target, ignore_errors=True)
                self.make_source()
                for rel, data in SAMPLE.items():
                    write(self.target, rel, data)
                data = self.valid_old_state()
                write(self.target, "agents/alfa.md", SAMPLE["agents/alfa.md"])
                mutate(data)
                self.dump_state(data)
                backup = os.path.join(self.tmp, "respaldo")
                code, out, err = self.run_install("-Force", "-BackupDir", backup)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(set(self.states(out).values()), {"IGUAL"})
                self.assert_clean_unreadable_warning(err)
                self.assert_state(5)
                self.assertFalse(os.path.exists(backup))

    def test_t2_case10_orphan_with_schema2_state_is_reported_and_kept(self):
        # Caso 10: una ruta del estado esquema 2 que ya no esta en el manifiesto es HUERFANO: se informa y no se borra.
        self.make_source()
        old = dict(SAMPLE)
        old["agents/viejo.md"] = b"de una version anterior\n"
        self.write_state(old)
        for rel, data in old.items():
            write(self.target, rel, data)
        before = snapshot(self.target)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/viejo.md"], "HUERFANO")
        self.assertEqual(snapshot(self.target), before)
        out, err = self.install_ok("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(self.states(out)["agents/viejo.md"], "HUERFANO")
        self.assertIn("nota:", out)
        self.assertEqual(read(self.target, "agents/viejo.md"), b"de una version anterior\n")
        self.assert_state(5)
        self.assertNotIn("viejo", read(self.target, self.STATE).decode("ascii"))

    def test_t2_case11_rerun_leaves_state_untouched_and_makes_no_backup(self):
        # Caso 11: reejecucion idempotente: el estado no se reescribe (bytes y mtime) y no hay respaldo.
        self.make_source()
        self.install_ok()
        state_path = os.path.join(self.target, self.STATE)
        raw, mtime = read(self.target, self.STATE), os.stat(state_path).st_mtime_ns
        listing = sorted(os.listdir(self.tmp))
        for _ in range(2):
            out, err = self.install_ok()
            self.assertEqual(set(self.states(out).values()), {"IGUAL"})
            self.assertNotIn("Estado:", out)
            self.assertEqual(read(self.target, self.STATE), raw)
            self.assertEqual(os.stat(state_path).st_mtime_ns, mtime)
            self.assertEqual(sorted(os.listdir(self.tmp)), listing)
            self.assertNotIn("Se trata como ausente", err)

    def test_t2_written_is_what_classifies_not_the_source_hash(self):
        # El destino se compara con `written` de la instalacion previa. Con written distinto de sha256:
        # destino = written -> ACTUALIZAR; destino = sha256 viejo (no written) -> MODIFICADO.
        self.make_source()
        written_bytes = b"alfa como la dejo la instalacion\n"
        other = b"alfa de otro origen\n"
        for label, dest_bytes, state_src, expected in (
                ("destino = written", written_bytes, SAMPLE["agents/alfa.md"], "ACTUALIZAR"),
                ("destino = hash del origen previo", other, other, "MODIFICADO")):
            with self.subTest(case=label):
                shutil.rmtree(self.target, ignore_errors=True)
                for rel, data in SAMPLE.items():
                    write(self.target, rel, data)
                write(self.target, "agents/alfa.md", dest_bytes)
                # el origen cambio: el destino ya no coincide con el origen de hoy
                old = dict(SAMPLE)
                old["agents/alfa.md"] = state_src
                self.write_state(old, written={"agents/alfa.md": self.sha(written_bytes)})
                code, out, err = self.run_install("-DryRun", "-Force")
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.states(out)["agents/alfa.md"], expected)

    def test_t2_actualizar_with_written_overwrites_with_backup_and_records_state(self):
        self.make_source()
        written_bytes = b"alfa como la dejo la instalacion\n"
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        write(self.target, "agents/alfa.md", written_bytes)
        self.write_state(SAMPLE, written={"agents/alfa.md": self.sha(written_bytes)})
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(self.states(out)["agents/alfa.md"], "ACTUALIZAR")
        self.assertEqual(read(backup, "agents/alfa.md"), written_bytes)
        self.assertEqual(read(self.target, "agents/alfa.md"), SAMPLE["agents/alfa.md"])
        self.assert_state(5)

    def test_t2_manual_edit_is_modified_exit3_never_actualizar(self):
        # Edicion a mano del destino con un estado esquema 2 valido: MODIFICADO y exit 3 sin -Force,
        # con o sin cambio de origen; nada se escribe.
        for changed_source in (False, True):
            with self.subTest(changed_source=changed_source):
                shutil.rmtree(self.target, ignore_errors=True)
                self.make_source()
                self.preinstall()
                if changed_source:
                    self.update_source("agents/alfa.md", b"alfa nueva\n")
                write(self.target, "agents/alfa.md", b"editado a mano\n")
                before = snapshot(self.target)
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*(mode + ["-BackupDir", os.path.join(self.tmp, "respaldo")]))
                    self.assertEqual(code, 3, out + err)
                    self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
                    self.assertNotIn("ACTUALIZAR", set(self.states(out).values()))
                    self.assertEqual(snapshot(self.target), before)
                    self.assertFalse(os.path.exists(os.path.join(self.tmp, "respaldo")))

    def test_t2_schema1_state_with_manual_edit_is_modified(self):
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        self.write_state(SAMPLE, schema=1)
        write(self.target, "agents/beta.md", b"editado a mano\n")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/beta.md"], "MODIFICADO")

    def test_t2_state_never_prints_unsafe_text_from_a_hostile_state(self):
        # El estado es entrada no confiable: una ruta o clave hostil no llega cruda a stdout ni a stderr.
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        data = self.valid_old_state()
        write(self.target, "agents/alfa.md", SAMPLE["agents/alfa.md"])
        data["files"][0]["path"] = "agents/a‐b.md"
        self.dump_state(data)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(err.isascii() and out.isascii(), repr(out + err))
        self.assertIn("\\u2010", err)
        self.assertNotIn("a‐b", out + err)

    # --- T5: cambios locales y -Force ---

    def test_t5_mixed_modified_and_update_without_force_writes_neither(self):
        self.make_source()
        self.preinstall()
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"alfa 2\n"          # ACTUALIZAR
        files["agents/beta.md"] = b"beta 2\n"          # el destino se edita a mano: MODIFICADO
        self.make_source(files)
        write(self.target, "agents/beta.md", b"editado a mano\n")
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "ACTUALIZAR")
        self.assertEqual(self.states(out)["agents/beta.md"], "MODIFICADO")
        self.assertIn("agents/beta.md", err)
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(os.path.exists(backup))
        self.assertEqual(self.leftover_temps(), [])

    def test_t5_force_backs_up_local_version_and_overwrites(self):
        self.make_source()
        self.preinstall()
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"alfa 2\n"
        self.make_source(files)
        write(self.target, "agents/beta.md", b"editado a mano\r\ncon CR\r\n")
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(self.states(out)["agents/beta.md"], "MODIFICADO")
        # la version local queda tal cual en el respaldo (bytes originales)
        self.assertEqual(read(backup, "agents/beta.md"), b"editado a mano\r\ncon CR\r\n")
        for rel, data in files.items():
            self.assertEqual(read(self.target, rel), data)
        self.assert_state(5)
        self.assertIn("Recordatorio", out)
        self.assertEqual(self.leftover_temps(), [])

    def test_t5_case11_real_run_existing_without_state_modified_exit3(self):
        self.make_source()
        write(self.target, "agents/alfa.md", b"distinto\n")
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 3, out + err)
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(os.path.exists(backup))

    def test_t5_case16_orphan_real_run_kept_and_reported(self):
        self.make_source()
        old = dict(SAMPLE)
        old["agents/viejo.md"] = b"de una version anterior\n"
        self.write_state(old)
        for rel, data in old.items():
            write(self.target, rel, data)
        out, err = self.install_ok("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(self.states(out)["agents/viejo.md"], "HUERFANO")
        self.assertEqual(read(self.target, "agents/viejo.md"), b"de una version anterior\n")
        self.assert_state(5)

    # --- T5: estado previo ilegible: tratado como ausente, sin hash ni respaldo, con aviso por stderr ---

    def assert_clean_unreadable_warning(self, err):
        self.assertIn("aviso", err)
        self.assertIn("Se trata como ausente", err)
        self.assertNotIn("Exception", err)
        self.assertNotIn("At line", err)
        self.assertTrue(err.isascii(), repr(err))
        self.assertNotIn("\\u000d", err)

    def test_t5_corrupt_state_all_equal_real_run_replaces_state_no_backup(self):
        for extra in ([], ["-Force"]):
            with self.subTest(extra=extra):
                shutil.rmtree(self.target, ignore_errors=True)
                self.make_source()
                for rel, data in SAMPLE.items():
                    write(self.target, rel, data)
                write(self.target, "synclayer-manifest.json", b"{no es json")
                backup = os.path.join(self.tmp, "respaldo")
                code, out, err = self.run_install(*(extra + ["-BackupDir", backup]))
                self.assertEqual(code, 0, out + err)
                self.assert_clean_unreadable_warning(err)
                self.assert_state(5)
                self.assertFalse(os.path.exists(backup))      # un estado invalido no se respalda
                self.assertNotIn("Respaldo", out)

    def test_t5_corrupt_state_with_modified_needs_force_and_state_not_in_backup(self):
        self.make_source()
        write(self.target, "synclayer-manifest.json", b"{no es json")
        write(self.target, "agents/alfa.md", b"editado\n")
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 3, out + err)
        self.assert_clean_unreadable_warning(err)
        self.assertEqual(read(self.target, "synclayer-manifest.json"), b"{no es json")
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(read(backup, "agents/alfa.md"), b"editado\n")
        self.assertFalse(os.path.exists(os.path.join(backup, "synclayer-manifest.json")))

    def lock_file(self, path, access, share):
        """Abre el archivo con acceso/uso compartido dados (Win32) y lo mantiene abierto hasta el final de la prueba."""
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = k32.CreateFileW(path, access, share, None, 3, 0x80, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            self.skipTest("no se pudo abrir %s con el bloqueo pedido" % path)
        self.addCleanup(k32.CloseHandle, handle)

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000

    @unittest.skipUnless(os.name == "nt", "el bloqueo con FileShare 0 es de Windows")
    def test_t5_locked_state_exit1_before_writing_in_both_modes(self):
        # Un estado bloqueado se ve antes de escribir: se trata como ilegible (aviso) y, como hay que
        # reescribirlo, exit 1 en -DryRun y en la real, sin tocar nada. El exit 4 queda para fallos al escribir.
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)
        state = write(self.target, "synclayer-manifest.json", read(self.src, "install-manifest.json"))
        self.lock_file(state, self.GENERIC_READ | self.GENERIC_WRITE, 0)
        backup = os.path.join(self.tmp, "respaldo")
        for extra in ([], ["-DryRun"], ["-Force"]):
            with self.subTest(extra=extra):
                code, out, err = self.run_install(*(extra + ["-BackupDir", backup]))
                self.assertEqual(code, 1, out + err)
                self.assert_clean_unreadable_warning(err)
                self.assertIn("bloqueado", err)
                self.assertIn("synclayer-manifest.json", err)
                self.assertIn("No se escribio nada", err)
                self.assertNotIn("Copiado", out)
                self.assertEqual(self.leftover_temps(), [])
                self.assertFalse(os.path.exists(backup))

    @unittest.skipUnless(os.name == "nt", "el bloqueo con FileShare 0 es de Windows")
    def test_t5_destination_file_open_without_sharing_exit1_with_context(self):
        # No se puede ni leer para clasificar: mensaje con contexto, no texto crudo de .NET.
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        self.lock_file(os.path.join(self.target, "agents", "alfa.md"), self.GENERIC_READ, 0)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("no se pudo leer el destino", err)
                self.assertIn("No se escribio nada en el destino", err)
                self.assertTrue(err.isascii(), repr(err))
                self.assertNotIn("Exception", err)
        self.assertEqual(self.leftover_temps(), [])

    @unittest.skipUnless(os.name == "nt", "el bloqueo de uso compartido es de Windows")
    def test_t5_destination_file_readable_but_not_writable_by_sharing_exit1_in_both_modes(self):
        # Se puede leer (clasifica) pero otro proceso lo tiene abierto sin permitir escritura: se detecta
        # antes de escribir, exit 1 en ambos modos (no exit 4 a mitad de la copia).
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        self.lock_file(os.path.join(self.target, "agents", "alfa.md"), self.GENERIC_READ, 1)
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("bloqueado", err)
                self.assertIn("alfa.md", err)
                self.assertEqual(snapshot(self.target), before)
                self.assertNotIn("Copiado", out)

    @unittest.skipUnless(os.name == "nt", "icacls es de Windows")
    def test_t5_destination_file_with_deny_write_acl_exit1_in_both_modes(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        path = os.path.join(self.target, "agents", "alfa.md")
        deny = subprocess.run(["icacls", path, "/deny", "*S-1-1-0:(WD,AD)"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if deny.returncode != 0:
            self.skipTest("icacls no pudo negar la escritura")
        self.addCleanup(subprocess.run, ["icacls", path, "/remove:d", "*S-1-1-0"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("no se puede escribir", err)
                self.assertNotIn("Copiado", out)
        self.assertEqual(read(self.target, "agents/alfa.md"), SAMPLE["agents/alfa.md"])

    def test_t5_backup_read_failure_has_context(self):
        # ReadAllBytes del original al respaldar falla (otro proceso lo abre sin compartir tras clasificar).
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        victim = os.path.join(self.target, "agents", "alfa.md").replace("'", "''")
        self.patch_script("# Paso 6:", "$lockfs = [System.IO.File]::Open('%s', 'Open', 'Read', 'None')" % victim)
        code, out, err = self.run_install("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 1, out + err)
        self.assertIn("para respaldarlo", err)
        self.assertIn("No se escribio nada en el destino", err)
        self.assertTrue(err.isascii(), repr(err))
        self.assertNotIn("Exception", err)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "respaldo")))

    # --- T5: minor de T4 ---

    def test_t5_state_that_is_a_folder_exit1_in_both_modes(self):
        self.make_source()
        os.makedirs(os.path.join(self.target, "synclayer-manifest.json"))
        self.assert_same_exit(1, expect_err="synclayer-manifest.json")

    def test_t5_readonly_destination_exit1_in_both_modes(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        self.make_readonly("agents/alfa.md")
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*(mode + ["-BackupDir", backup]))
                self.assertEqual(code, 1, out + err)
                self.assertIn("solo lectura", err)
                self.assertIn("alfa.md", err)
                self.assertEqual(snapshot(self.target), before)
                self.assertFalse(os.path.exists(backup))

    def test_t5_readonly_destination_with_force_exit1(self):
        self.make_source()
        write(self.target, "agents/alfa.md", b"editado\n")
        self.make_readonly("agents/alfa.md")
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*(mode + ["-Force"]))
                self.assertEqual(code, 1, out + err)
                self.assertIn("solo lectura", err)
        self.assertEqual(read(self.target, "agents/alfa.md"), b"editado\n")

    def test_t5_readonly_state_exit1_in_both_modes(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        self.make_readonly("synclayer-manifest.json")
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("solo lectura", err)
                self.assertEqual(snapshot(self.target), before)

    def test_t5_readonly_file_that_is_igual_is_not_a_problem(self):
        self.make_source()
        self.preinstall()
        self.make_readonly("agents/alfa.md")
        code, out, err = self.run_install()
        self.assertEqual(code, 0, out + err)

    def test_t5_temp_with_colliding_name_is_not_deleted(self):
        # Si CreateNew falla porque el nombre ya existia, ese archivo no es nuestro: no se borra.
        self.make_source()
        path = os.path.join(self.src, "install.ps1")
        with open(path, "rb") as f:
            text = f.read().decode("ascii")
        self.assertEqual(text.count("[guid]::NewGuid().ToString('N')"), 1)
        with open(path, "wb") as f:
            f.write(text.replace("[guid]::NewGuid().ToString('N')", "'fijo'").encode("ascii"))
        foreign = write(self.target, "hooks/.synclayer-fijo.tmp", b"ajeno")
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertTrue(os.path.exists(foreign))
        self.assertEqual(read(self.target, "hooks/.synclayer-fijo.tmp"), b"ajeno")
        self.assertNotIn("\\u000d", err)

    def test_t5_error_message_with_trailing_crlf_is_trimmed_before_escaping(self):
        # Los mensajes de .NET pueden terminar en CRLF; no deben salir como \u000d\u000a.
        self.make_source()
        self.patch_script("# Paso 7:", "throw ('causa de prueba' + [char]13 + [char]10)")
        code, out, err = self.run_install()
        self.assertEqual(code, 1, out + err)
        self.assertEqual(err.strip(), "error: causa de prueba")
        self.assertNotIn("\\u000d", err)
        self.assertNotIn("\\u000a", err)

    def test_t5_update_replaces_the_file_instead_of_rewriting_in_place(self):
        # Atomicidad: un enlace duro al hook conserva el contenido viejo (Replace crea un archivo nuevo;
        # WriteAllBytes sobre el destino cambiaria tambien el enlace).
        self.make_source()
        self.preinstall()
        hook = os.path.join(self.target, "hooks", "agent_guard.py")
        link = os.path.join(self.tmp, "enlace duro")
        try:
            os.link(hook, link)
        except (OSError, NotImplementedError, AttributeError) as e:
            self.skipTest("no se pudo crear un enlace duro: %s" % e)
        files = dict(SAMPLE)
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_source(files)
        self.install_ok("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(read(self.target, "hooks/agent_guard.py"), b"print('guard 2')\n")
        with open(link, "rb") as f:
            self.assertEqual(f.read(), SAMPLE["hooks/agent_guard.py"])

    def test_t5_target_notice_goes_to_stderr_in_a_real_run(self):
        self.make_source()
        out, err = self.install_ok()
        self.assertIn("aviso: -Target no es", err)
        self.assertNotIn("aviso", out)

    def test_t5_hash_check_before_backup_covers_all_items_before_the_first_backup(self):
        self.make_source()
        self.preinstall()
        files = dict(SAMPLE)
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"     # primer respaldo: el hook
        files["agents/beta.md"] = b"beta 2\n"                      # segundo respaldo: beta
        self.make_source(files)
        victim = os.path.join(self.target, "agents", "beta.md").replace("'", "''")
        self.patch_script("# Paso 6:", "[System.IO.File]::WriteAllBytes('%s', [byte[]]@(66,66))" % victim)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 1, out + err)
        self.assertIn("cambio en el destino durante la ejecucion", err)
        self.assertFalse(os.path.exists(backup), "no debe quedar ningun respaldo parcial")
        self.assertEqual(read(self.target, "hooks/agent_guard.py"), SAMPLE["hooks/agent_guard.py"])

    def test_t5_hash_check_before_replace_detects_change_after_classification(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        victim = os.path.join(self.target, "agents", "alfa.md").replace("'", "''")
        self.patch_script("# Paso 7:", "[System.IO.File]::WriteAllBytes('%s', [byte[]]@(90,90))" % victim)
        code, out, err = self.run_install("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 4, out + err)
        self.assertIn("el archivo cambio en el destino despues de clasificarlo", err)
        self.assertEqual(read(self.target, "agents/alfa.md"), b"ZZ")

    def test_t5_backup_name_collision_mentions_backupdir_without_raw_dotnet_text(self):
        self.make_source()
        self.preinstall()
        files = dict(SAMPLE)
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_source(files)
        backup = os.path.join(self.tmp, "respaldo")
        mine = os.path.join(backup, "hooks", "agent_guard.py").replace("'", "''")
        self.patch_script("# Carpeta de respaldo ya comprobada",
                          "[void][System.IO.Directory]::CreateDirectory('%s'); [System.IO.File]::WriteAllBytes('%s', [byte[]]@(80))"
                          % (os.path.dirname(mine), mine))
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 1, out + err)
        self.assertIn("-BackupDir", err)
        self.assertTrue(err.isascii(), repr(err))
        self.assertNotIn("\\u000d", err)
        self.assertEqual(read(backup, "hooks/agent_guard.py"), b"P")
        self.assertEqual(read(self.target, "hooks/agent_guard.py"), SAMPLE["hooks/agent_guard.py"])

    # --- T5: puntos de reanalisis ---

    def make_link_dir(self, link, target):
        """Junction real (Windows) o enlace simbolico de carpeta; salta con motivo si no se puede."""
        os.makedirs(target, exist_ok=True)
        if os.name == "nt":
            try:
                import _winapi
                _winapi.CreateJunction(target, link)
                return
            except (ImportError, AttributeError, OSError) as e:
                self.skipTest("no se pudo crear una junction en el temporal: %s" % e)
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError) as e:
            self.skipTest("no se pudo crear un enlace simbolico: %s" % e)

    def make_tagged_reparse_file(self, path):
        """Archivo con punto de reanalisis de etiqueta propia (FSCTL_SET_REPARSE_POINT, tag 0x80001234 + GUID).
        No requiere privilegio, a diferencia del enlace simbolico de archivo. Windows solamente.
        Se usa un tag con el bit 31 (Microsoft) y sin asignar: en este equipo 0x1234 da ERROR_INVALID_REPARSE_DATA (4392)."""
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
            self.skipTest("no se pudo abrir el archivo para fijar el punto de reanalisis")
        guid = bytes(range(1, 17))
        buf = struct.pack("<IHH", 0x80001234, len(guid), 0) + guid
        returned = wintypes.DWORD(0)
        ok = k32.DeviceIoControl(handle, 0x000900A4, buf, len(buf), None, 0, ctypes.byref(returned), None)
        k32.CloseHandle(handle)
        if not ok:
            os.remove(path)
            self.skipTest("FSCTL_SET_REPARSE_POINT fallo (error %d)" % ctypes.get_last_error())

        def cleanup():
            try:
                os.remove(path)
            except OSError:
                pass
        self.addCleanup(cleanup)

    def make_link_file(self, link, target):
        """Enlace simbolico de archivo; sin privilegio (WinError 1314), reanalisis de etiqueta propia en Windows."""
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as e:
            if os.name == "nt":
                self.make_tagged_reparse_file(link)
                return
            self.skipTest("no se pudo crear un enlace simbolico de archivo (sin privilegio?): %s" % e)

    def assert_reparse_rejected(self, *extra, expect_in_err=None, outside_before=None, modes=None):
        for mode in (modes or (["-DryRun"], [])):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*(mode + list(extra)))
                self.assertEqual(code, 1, out + err)
                self.assertIn("punto de reanalisis", err)
                self.assertTrue(err.isascii(), repr(err))
                if expect_in_err:
                    self.assertIn(expect_in_err, err)
                self.assertNotIn("Copiado", out)
                self.assertNotIn("Respaldado", out)
        if outside_before is not None:
            self.assertEqual(snapshot(self.outside), outside_before)

    def test_t5_reparse_point_in_intermediate_folder_exit1_in_both_modes(self):
        self.make_source()
        for folder in ("agents", "rules", "hooks", "docs"):
            with self.subTest(folder=folder):
                os.makedirs(self.target, exist_ok=True)
                link = os.path.join(self.target, folder)
                self.make_link_dir(link, self.outside)
                try:
                    before = snapshot(self.outside)
                    # la real solo con hooks (el caso medido): la clasificacion es el mismo codigo en ambos modos
                    modes = (["-DryRun"], []) if folder == "hooks" else (["-DryRun"],)
                    self.assert_reparse_rejected(expect_in_err=folder, outside_before=before, modes=modes)
                    self.assertEqual(os.listdir(self.outside), [])
                finally:
                    os.rmdir(link)

    def test_t5_reparse_point_in_populated_folder_does_not_write_outside(self):
        # El escenario medido: hooks es una junction a una carpeta externa que ya existe.
        self.make_source()
        write(self.outside, "ajeno.txt", b"ajeno")
        link = os.path.join(self.target, "hooks")
        os.makedirs(self.target)
        self.make_link_dir(link, self.outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        before = snapshot(self.outside)
        self.assert_reparse_rejected(outside_before=before)
        self.assertFalse(os.path.exists(os.path.join(self.outside, "agent_guard.py")))

    def test_t5_target_that_is_a_reparse_point_exit1(self):
        self.make_source()
        real = os.path.join(self.tmp, "real")
        self.make_link_dir(self.target, real)
        self.addCleanup(lambda: os.path.isdir(self.target) and os.rmdir(self.target))
        self.assert_reparse_rejected()
        self.assertEqual(os.listdir(real), [])

    def test_t5_destination_file_that_is_a_symlink_exit1(self):
        self.make_source()
        victim = write(self.outside, "victima.md", b"no tocar")
        os.makedirs(os.path.join(self.target, "agents"))
        self.make_link_file(os.path.join(self.target, "agents", "alfa.md"), victim)
        before = snapshot(self.outside)
        self.assert_reparse_rejected(expect_in_err="alfa.md", outside_before=before)
        self.assert_reparse_rejected("-Force", expect_in_err="alfa.md", outside_before=before, modes=(["-DryRun"],))
        self.assertEqual(read(self.outside, "victima.md"), b"no tocar")

    def test_t5_destination_file_path_that_is_a_reparse_point_exit1(self):
        # Ultimo componente de la ruta (el archivo de destino): con una junction en su lugar tambien se rechaza
        # (los symlink de archivo no se pueden crear sin privilegio en todos los equipos).
        self.make_source()
        os.makedirs(os.path.join(self.target, "agents"))
        link = os.path.join(self.target, "agents", "alfa.md")
        self.make_link_dir(link, self.outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        self.assert_reparse_rejected(expect_in_err="alfa.md", outside_before=snapshot(self.outside))
        self.assertEqual(os.listdir(self.outside), [])

    def test_t5_dangling_symlink_destination_exit1(self):
        self.make_source()
        os.makedirs(os.path.join(self.target, "agents"))
        self.make_link_file(os.path.join(self.target, "agents", "alfa.md"), os.path.join(self.outside, "no existe.md"))
        self.assert_reparse_rejected(expect_in_err="alfa.md")
        self.assertFalse(os.path.exists(self.outside))

    def test_t5_state_file_that_is_a_symlink_exit1(self):
        self.make_source()
        victim = write(self.outside, "estado.json", b"no tocar")
        os.makedirs(self.target)
        self.make_link_file(os.path.join(self.target, "synclayer-manifest.json"), victim)
        self.assert_reparse_rejected(expect_in_err="synclayer-manifest.json")
        self.assertEqual(read(self.outside, "estado.json"), b"no tocar")

    def test_t5_backup_dir_that_is_a_reparse_point_exit1(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        backup = os.path.join(self.tmp, "respaldo")
        self.make_link_dir(backup, self.outside)
        self.addCleanup(lambda: os.path.isdir(backup) and os.rmdir(backup))
        before_t = snapshot(self.target)
        self.assert_reparse_rejected("-BackupDir", backup, outside_before=snapshot(self.outside))
        self.assertEqual(os.listdir(self.outside), [])
        self.assertEqual(snapshot(self.target), before_t)

    def test_t5_backup_subfolder_that_is_a_reparse_point_exit1(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        backup = os.path.join(self.tmp, "respaldo")
        os.makedirs(backup)
        link = os.path.join(backup, "agents")
        self.make_link_dir(link, self.outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        before_t = snapshot(self.target)
        self.assert_reparse_rejected("-BackupDir", backup, outside_before=snapshot(self.outside))
        self.assertEqual(snapshot(self.target), before_t)

    @unittest.skipUnless(os.name == "nt", "New-Item -ItemType Junction solo en Windows")
    def test_t5_backup_reparse_check_is_repeated_right_before_writing(self):
        # TOCTOU: tras clasificar, la carpeta de respaldo pasa a ser un enlace.
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        os.makedirs(self.outside)
        backup = os.path.join(self.tmp, "respaldo")
        link = os.path.join(backup, "agents")
        self.patch_script("# Paso 6:",
                          "[void][System.IO.Directory]::CreateDirectory('%s'); New-Item -ItemType Junction -Path '%s' -Value '%s' | Out-Null"
                          % (backup.replace("'", "''"), link.replace("'", "''"), self.outside.replace("'", "''")))
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 1, out + err)
        self.assertIn("punto de reanalisis", err)
        self.assertEqual(os.listdir(self.outside), [])
        self.assertEqual(read(self.target, "agents/alfa.md"), SAMPLE["agents/alfa.md"])

    @unittest.skipUnless(os.name == "nt", "New-Item -ItemType Junction solo en Windows")
    def test_t5_destination_reparse_check_is_repeated_right_before_writing(self):
        # TOCTOU: tras clasificar (todo NUEVO) y respaldar, hooks pasa a ser una junction a una carpeta externa.
        self.make_source()
        os.makedirs(self.outside)
        link = os.path.join(self.target, "hooks")
        self.patch_script("# Paso 7:",
                          "[void][System.IO.Directory]::CreateDirectory('%s'); New-Item -ItemType Junction -Path '%s' -Value '%s' | Out-Null"
                          % (self.target.replace("'", "''"), link.replace("'", "''"), self.outside.replace("'", "''")))
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("punto de reanalisis", err)
        self.assertEqual(os.listdir(self.outside), [])
        self.assertFalse(os.path.exists(os.path.join(self.target, "synclayer-manifest.json")))
        self.assertNotIn("Copiado: hooks/agent_guard.py", out)

    # --- T5, ronda de correcciones ---

    def test_t5_force_with_reparse_folder_exit1_in_both_modes(self):
        self.make_source()
        link = os.path.join(self.target, "agents")
        os.makedirs(self.target)
        self.make_link_dir(link, self.outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        self.assert_reparse_rejected("-Force", expect_in_err="agents", outside_before=snapshot(self.outside))
        self.assertEqual(os.listdir(self.outside), [])

    def test_t5_state_that_is_a_reparse_point_exit1_with_reparse_message(self):
        # Un estado que es junction se rechaza como reanalisis, no como "es una carpeta".
        self.make_source()
        link = os.path.join(self.target, "synclayer-manifest.json")
        os.makedirs(self.target)
        self.make_link_dir(link, self.outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        self.assert_reparse_rejected(expect_in_err="synclayer-manifest.json", outside_before=snapshot(self.outside))
        self.assertEqual(os.listdir(self.outside), [])

    # --- Fase 3, T3: synclayer-config.json (lectura y validacion del nivel; entrada no confiable) ---

    CONFIG = "synclayer-config.json"

    def write_config(self, data):
        return write(self.target, self.CONFIG, data)

    def tree(self, base):
        """Contenido (solo bytes) de todos los archivos bajo base, por ruta relativa."""
        result = {}
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                p = os.path.join(dirpath, name)
                with open(p, "rb") as f:
                    result[os.path.relpath(p, base)] = f.read()
        return result

    def assert_config_rejected(self, data, motivo, modes=None, expect_out_nivel=False):
        """Configuracion invalida: exit 1 en -DryRun y real, mensaje con el motivo, nada escrito ni respaldado."""
        self.make_source()
        self.write_config(data)
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        for mode in (modes or (["-DryRun"], [])):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("error: synclayer-config.json no es valido: ", err)
                self.assertIn(motivo, err)
                self.assertIn("No se escribio nada", err)
                self.assertTrue(err.isascii(), repr(err))
                self.assertFalse(any(ord(c) < 0x20 and c not in "\r\n" for c in err), repr(err))
                self.assertNotIn("Exception", err)
                self.assertNotIn("ConvertFrom-Json", err)
                self.assertNotIn("Copiado", out)
                self.assertNotIn("Nivel:", out)
                self.assertEqual(snapshot(self.target), before)
                self.assertEqual(sorted(os.listdir(self.tmp)), listing)

    def test_t3_case12_no_config_installs_level5_and_says_default(self):
        self.make_source()
        out, err = self.install_ok()
        self.assertIn("Nivel: 5 (por defecto; no hay synclayer-config.json)", out.splitlines())
        for rel, data in SAMPLE.items():
            self.assertEqual(read(self.target, rel), data)
        self.assert_state(5)
        self.assertFalse(os.path.exists(os.path.join(self.target, self.CONFIG)))

    def test_t3_case12_level_line_comes_after_destino_and_before_the_plan(self):
        self.make_source()
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("Destino: "), lines)
        self.assertEqual(lines[1], "Nivel: 5 (por defecto; no hay synclayer-config.json)")
        self.assertFalse(os.path.exists(self.target))

    def test_t3_case13_level5_config_gives_same_destination_and_state_as_no_config(self):
        self.make_source()
        self.install_ok()
        reference = self.tree(self.target)
        shutil.rmtree(self.target)
        self.write_config(b'{"level": 5}')
        out, err = self.install_ok()
        self.assertIn("Nivel: 5 (synclayer-config.json)", out.splitlines())
        got = self.tree(self.target)
        self.assertEqual(got.pop(self.CONFIG), b'{"level": 5}')
        self.assertEqual(got, reference)
        self.assert_state(5)

    def test_t3_case14_invalid_configurations_exit1_in_both_modes_and_write_nothing(self):
        invalid_level = "level debe ser un entero de 1 a 5"
        variants = [
            ("json roto", b'{no es json', "JSON invalido"),
            ("vacio", b"", "JSON invalido"),
            ("solo blancos", b" \r\n\t ", "JSON invalido"),
            ("basura al final", b'{"level": 5} x', "JSON invalido"),
            ("dos objetos", b'{"level": 5}{"level": 5}', "JSON invalido"),
            ("lista vacia", b"[]", "debe ser un objeto"),
            ("lista de numeros", b"[1, 2]", "debe ser un objeto"),
            ("lista de un objeto valido", b'[{"level": 5}]', "debe ser un objeto"),
            ("numero", b"5", "debe ser un objeto"),
            ("cadena", b'"5"', "debe ser un objeto"),
            ("null", b"null", "debe ser un objeto"),
            ("true", b"true", "debe ser un objeto"),
            ("level texto", b'{"level": "3"}', invalid_level),
            ("level texto 5", b'{"level": "5"}', invalid_level),
            ("level decimal", b'{"level": 3.0}', invalid_level),
            ("level decimal 5.0", b'{"level": 5.0}', invalid_level),
            ("level decimal 2.5", b'{"level": 2.5}', invalid_level),
            ("level true", b'{"level": true}', invalid_level),
            ("level false", b'{"level": false}', invalid_level),
            ("level null", b'{"level": null}', invalid_level),
            ("level cero", b'{"level": 0}', invalid_level),
            ("level seis", b'{"level": 6}', invalid_level),
            ("level negativo", b'{"level": -1}', invalid_level),
            ("level enorme", b'{"level": 99999999999}', invalid_level),
            ("level enorme de 30 cifras", b'{"level": 999999999999999999999999999999}', invalid_level),
            ("level exponente", b'{"level": 5e0}', invalid_level),
            ("level lista", b'{"level": [5]}', invalid_level),
            ("level objeto", b'{"level": {"level": 5}}', invalid_level),
            ("level cadena vacia", b'{"level": ""}', invalid_level),
            ("clave Level", b'{"Level": 3}', "clave desconocida: Level"),
            ("clave Level con level", b'{"level": 5, "Level": 5}', "JSON invalido"),
            ("clave agents", b'{"level": 5, "agents": {}}', "clave desconocida: agents"),
            ("clave nivel", b'{"nivel": 2}', "clave desconocida: nivel"),
            ("clave vacia (5.1 la rechaza como JSON)", b'{"": 1}', "JSON invalido"),
            ("clave con espacio", b'{"level ": 5}', "clave desconocida: level "),
            ("clave con guion blando", '{"level\u00ad": 5}'.encode("utf-8"), "clave desconocida: level\\u00ad"),
            ("level 5 con clave extra", b'{"level": 5, "extra": 1}', "clave desconocida: extra"),
            # ConvertFrom-Json de 5.1 descarta __type en silencio: el instalador debe rechazarlo antes.
            ("__type solo", b'{"__type":"x"}', "clave desconocida: __type"),
            ("level con __type", b'{"level":5,"__type":"System.String"}', "clave desconocida: __type"),
            ("__type antes de level 3", b'{"__type":"x","level":3}', "clave desconocida: __type"),
            ("__type escapado entero", b'{"\\u005f\\u005ftype":"x"}', "clave desconocida: __type"),
            ("__type con un guion escapado", b'{"level":5,"_\\u005Ftype":"x"}', "clave desconocida: __type"),
            ("__type con letra escapada", b'{"level":5,"__t\\u0079pe":"x"}', "clave desconocida: __type"),
            ("__type como valor", b'{"level":5,"x":"__type"}', "clave desconocida: __type"),
            ("__TYPE (5.1 lo conserva)", b'{"level":5,"__TYPE":"x"}', "clave desconocida: __TYPE"),
            ("a__type (se rechaza por contener __type)", b'{"level":5,"a__type":"x"}', "clave desconocida: __type"),
        ]
        for name, data, motivo in variants:
            with self.subTest(case=name):
                self.assert_config_rejected(data, motivo)
                shutil.rmtree(self.target)

    def test_t3_case14_type_key_does_not_affect_legitimate_configurations(self):
        # Control: level y los guiones bajos de otras formas no se ven afectados por el rechazo de __type.
        for data in (b'{"level": 5}', b'{"level": 5 }', b'{"l\\u0065vel": 5}', b'{}'):
            with self.subTest(data=data):
                self.make_source()
                self.write_config(data)
                out, err = self.install_ok("-DryRun")
                self.assertIn("Nivel: 5 (synclayer-config.json)", out.splitlines())
                shutil.rmtree(self.target)

    def test_t3_case14_encodings_other_than_utf8_are_rejected(self):
        text = '{"level": 5}'
        variants = [
            ("utf-16 con BOM", text.encode("utf-16")),
            ("utf-16 sin BOM", text.encode("utf-16-le")),
            ("utf-16 big endian", text.encode("utf-16-be")),
            ("utf-32", text.encode("utf-32")),
            ("latin-1 en una clave", b'{"level": 5, "\xe9": 1}'),
            ("byte suelto invalido", b'{"level": 5}\xff'),
            ("doble BOM utf-8", b'\xef\xbb\xbf\xef\xbb\xbf{"level": 5}'),
            ("NUL final", b'{"level": 5}\x00'),
        ]
        for name, data in variants:
            with self.subTest(case=name):
                self.assert_config_rejected(data, "JSON invalido")
                shutil.rmtree(self.target)

    def test_t3_case14_size_limit_is_checked_on_what_is_read(self):
        head = b'{"level": 5}'
        limit = 65536
        # exactamente el tope es valido; un byte mas, no; uno enorme, tampoco (sin interpretarlo).
        self.make_source()
        self.write_config(head + b" " * (limit - len(head)))
        self.assertEqual(os.path.getsize(os.path.join(self.target, self.CONFIG)), limit)
        out, err = self.install_ok("-DryRun")
        self.assertIn("Nivel: 5 (synclayer-config.json)", out)
        shutil.rmtree(self.target)
        for name, size in (("tope mas uno", limit + 1), ("tres megas", 3 * 1024 * 1024)):
            with self.subTest(case=name):
                self.assert_config_rejected(head + b" " * (size - len(head)), "supera 65536 bytes")
                shutil.rmtree(self.target)

    def test_t3_case14_deeply_nested_json_is_a_clean_error(self):
        data = b'{"a": ' + b"[" * 20000 + b"]" * 20000 + b"}"
        self.assert_config_rejected(data, "JSON invalido")

    def test_t3_case15_bom_crlf_and_empty_object_are_valid(self):
        variants = [
            ("BOM y CRLF", b'\xef\xbb\xbf{\r\n  "level": 5\r\n}\r\n', 5),
            ("solo LF", b'{\n  "level": 5\n}\n', 5),
            ("BOM sin saltos", b'\xef\xbb\xbf{"level":5}', 5),
            ("objeto vacio", b"{}", 5),
            ("objeto vacio con blancos y BOM", b"\xef\xbb\xbf \r\n{ }\r\n", 5),
            ("level 5 con tabuladores", b'\t{\t"level"\t:\t5\t}\t', 5),
        ]
        for name, data, level in variants:
            with self.subTest(case=name):
                self.make_source()
                self.write_config(data)
                out, err = self.install_ok()
                self.assertIn("Nivel: %d (synclayer-config.json)" % level, out.splitlines())
                self.assert_state(level)
                for rel, content in SAMPLE.items():
                    self.assertEqual(read(self.target, rel), content)
                self.assertEqual(read(self.target, self.CONFIG), data)
                shutil.rmtree(self.target)

    def test_t3_case15_dryrun_with_valid_config_writes_nothing(self):
        self.make_source()
        self.write_config(b'{"level": 5}')
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Nivel: 5 (synclayer-config.json)", out.splitlines())
        self.assertEqual(self.states(out), {rel: "NUEVO" for rel in SAMPLE})
        self.assertEqual(snapshot(self.target), before)
        self.assertEqual(sorted(os.listdir(self.tmp)), listing)

    def test_t3_case16_config_that_is_a_folder_exit1_not_absent(self):
        self.make_source()
        os.makedirs(os.path.join(self.target, self.CONFIG, "dentro"))
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("synclayer-config.json no es valido: es una carpeta", err)
                self.assertIn("No se escribio nada", err)
                self.assertNotIn("Nivel:", out)
                self.assertEqual(snapshot(self.target), before)

    def test_t3_case16_config_that_is_a_junction_exit1_and_target_unchanged(self):
        self.make_source()
        write(self.outside, "level.json", b'{"level": 5}')
        os.makedirs(self.target)
        link = os.path.join(self.target, self.CONFIG)
        self.make_link_dir(link, self.outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        before = snapshot(self.outside)
        self.assert_reparse_rejected(expect_in_err=self.CONFIG, outside_before=before)
        self.assertEqual([n for n in os.listdir(self.target)], [self.CONFIG])

    def test_t3_case16_config_that_is_a_file_link_exit1_and_victim_untouched(self):
        self.make_source()
        victim = write(self.outside, "victima.json", b'{"level": 5}')
        os.makedirs(self.target)
        self.make_link_file(os.path.join(self.target, self.CONFIG), victim)
        before = snapshot(self.outside)
        self.assert_reparse_rejected(expect_in_err=self.CONFIG, outside_before=before)
        self.assertEqual(read(self.outside, "victima.json"), b'{"level": 5}')
        self.assertEqual(os.listdir(self.target), [self.CONFIG])

    def test_t3_case16_dangling_config_link_is_rejected_not_absent(self):
        self.make_source()
        os.makedirs(self.target)
        missing = os.path.join(self.tmp, "no existe")
        link = os.path.join(self.target, self.CONFIG)
        os.makedirs(missing)
        self.make_link_dir(link, missing)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        os.rmdir(missing)
        self.assert_reparse_rejected(expect_in_err=self.CONFIG)

    def test_t3_case16_target_that_is_a_reparse_point_with_config_inside_exit1(self):
        self.make_source()
        real = os.path.join(self.tmp, "real")
        write(real, self.CONFIG, b'{"level": 5}')
        self.make_link_dir(self.target, real)
        self.addCleanup(lambda: os.path.isdir(self.target) and os.rmdir(self.target))
        self.assert_reparse_rejected()
        self.assertEqual(os.listdir(real), [self.CONFIG])

    @unittest.skipUnless(os.name == "nt", "el bloqueo con FileShare 0 es de Windows")
    def test_t3_case16_locked_config_exit1_not_absent(self):
        self.make_source()
        path = self.write_config(b'{"level": 5}')
        self.lock_file(path, self.GENERIC_READ, 0)
        listing = sorted(os.listdir(self.tmp))
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("synclayer-config.json no es valido: no se pudo abrir el archivo", err)
                self.assertIn("No se escribio nada", err)
                self.assertTrue(err.isascii(), repr(err))
                self.assertNotIn("Nivel:", out)
                self.assertEqual(os.listdir(self.target), [self.CONFIG])
                self.assertEqual(sorted(os.listdir(self.tmp)), listing)

    @unittest.skipUnless(os.name == "nt", "New-Item -ItemType Junction solo en Windows")
    def test_t3_config_turned_into_a_junction_after_reading_is_rejected(self):
        # La segunda comprobacion de reanalisis (tras leer): el archivo valido se sustituye, justo despues
        # de leerlo, por una junction. Sin esa comprobacion la instalacion terminaria en exit 0.
        self.make_source()
        os.makedirs(self.outside)
        path = self.write_config(b'{"level": 5}')
        self.patch_script("$level = [int](Read-LevelConfig $configPath)",
                          "[System.IO.File]::Delete('%s'); New-Item -ItemType Junction -Path '%s' -Value '%s' | Out-Null"
                          % (path.replace("'", "''"), path.replace("'", "''"), self.outside.replace("'", "''")))
        self.addCleanup(lambda: os.path.isdir(path) and os.rmdir(path))
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                if not os.path.isdir(path):
                    self.write_config(b'{"level": 5}')
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("punto de reanalisis", err)
                self.assertIn("No se escribio nada", err)
                self.assertNotIn("Copiado", out)
                self.assertNotIn("Nivel:", out)
                self.assertEqual(os.listdir(self.outside), [])
                self.assertEqual(os.listdir(self.target), [self.CONFIG])
                os.rmdir(path)

    def test_t3_case17_duplicate_level_key_last_one_wins_in_windows_powershell_5_1(self):
        # Comportamiento medido de ConvertFrom-Json de 5.1: sin error, gana la ultima clave. Se fija aqui;
        # el estado final depende del valor que gana.
        self.make_source()
        self.write_config(b'{"level": 3, "level": 5}')
        out, err = self.install_ok("-DryRun")
        self.assertIn("Nivel: 5 (synclayer-config.json)", out.splitlines())
        self.write_config(b'{"level": 5, "level": 3}')
        out, err = self.install_ok("-DryRun")
        self.assertIn("Nivel: 3 (synclayer-config.json)", out.splitlines())

    def test_t3_case18_config_is_never_touched_backed_up_or_listed(self):
        self.make_source()
        data = b'\xef\xbb\xbf{"level": 5}\r\n'
        path = self.write_config(data)
        old = os.stat(path).st_mtime_ns - 5_000_000_000
        os.utime(path, ns=(old, old))
        before = snapshot(self.target)[self.CONFIG]
        self.install_ok()
        self.assertEqual(snapshot(self.target)[self.CONFIG], before)
        # una instalacion con respaldo y -Force: el config ni se respalda ni se sobrescribe
        write(self.target, "agents/alfa.md", b"editado a mano\n")
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertIn("Respaldado: agents/alfa.md", out)
        self.assertEqual(snapshot(self.target)[self.CONFIG], before)
        self.assertEqual(sorted(self.tree(backup)), [os.path.join("agents", "alfa.md")])
        self.assertNotIn("HUERFANO", self.states(out).values())
        self.assertNotIn(self.CONFIG, self.states(out))
        # y una tercera, idempotente, tampoco lo toca
        out, err = self.install_ok()
        self.assertEqual(snapshot(self.target)[self.CONFIG], before)

    def test_t3_case19_messages_escape_keys_and_never_echo_values_or_internal_text(self):
        secret = "SECRETO-DEL-ARCHIVO"
        variants = [
            ("clave con NUL, ESC y no ASCII",
             b'{"a\\u0000b\\u001b[31m\\u00e9\\u202e": 1}',
             "clave desconocida: a\\u0000b\\u001b[31m\\u00e9\\u202e"),
            ("clave con CR, LF y tabulador", b'{"a\\r\\n\\tb": 1}', "clave desconocida: a\\u000d\\u000a\\u0009b"),
            ("clave con barra invertida", b'{"a\\\\u0041": 1}', "clave desconocida: a\\u0041"),
            ("clave de 60000 caracteres", b'{"' + b"k" * 60000 + b'": 1}', "clave desconocida: " + "k" * 40 + "..."),
            ("valor de level con control y secreto",
             ('{"level": "%s\\u001b[31m\\u0000"}' % secret).encode("ascii"), "level debe ser un entero de 1 a 5"),
            ("valor de otra clave con secreto", ('{"clave": "%s"}' % secret).encode("ascii"), "clave desconocida: clave"),
            ("json roto con secreto", ('{"%s": ' % secret).encode("ascii"), "JSON invalido"),
        ]
        for name, data, motivo in variants:
            with self.subTest(case=name):
                self.make_source()
                self.write_config(data)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertIn(motivo, err)
                self.assertTrue(err.isascii(), repr(err))
                self.assertFalse(any(ord(c) < 0x20 and c not in "\r\n" for c in err + out), repr(err))
                self.assertNotIn("ConvertFrom-Json", err)
                self.assertNotIn("Exception", err)
                self.assertNotIn("System.", err)
                self.assertLess(len(err), 600)
                if "SECRETO" in data.decode("ascii", "replace"):
                    self.assertNotIn(secret, err + out)
                shutil.rmtree(self.target)

    # --- Fase 3, T4: renderizado y aplicacion de los niveles 1 a 4 (casos 20 a 30 del plan) ---

    def make_level_source(self, files=None, crlf=False):
        files = dict(LEVEL_SAMPLE) if files is None else files
        self.make_source(files, crlf=crlf)
        return files

    def set_level(self, level):
        self.write_config(('{"level": %d}' % level).encode("ascii"))

    def assert_level_installed(self, files, level):
        """Cada archivo del destino es lo que da la referencia de Python (render_expected) y el estado
        guarda written = hash de lo escrito y level = nivel."""
        for rel, data in level_expected(files, level).items():
            self.assertEqual(read(self.target, rel), data, rel)
        self.assert_state(level, level_hashes(files, level))

    def real_repo_source(self):
        raw = read(ROOT, "install-manifest.json")
        write(self.src, "install-manifest.json", raw)
        files = {}
        for entry in json.loads(raw)["files"]:
            files[entry["path"]] = read(ROOT, entry["path"])
            write(self.src, entry["path"], files[entry["path"]])
        return files

    def test_t4_case20_clean_install_levels_1_to_4(self):
        spots = {1: ("atlas", b"model: sonnet\neffort: medium\n"), 3: ("atlas", b"model: opus\neffort: medium\n"),
                 4: ("atlas", b"model: opus\n")}
        for level in (1, 2, 3, 4):
            with self.subTest(level=level):
                files = self.make_level_source()
                self.set_level(level)
                self.install_ok()
                self.assert_level_installed(files, level)
                for rel in LEVEL_FIXED:
                    self.assertEqual(read(self.target, rel), files[rel], rel)
                if level in spots:
                    agent, lines = spots[level]
                    self.assertIn(lines, read(self.target, "agents/%s.md" % agent))
                state = json.loads(read(self.target, "synclayer-manifest.json"))
                self.assertEqual({f["level"] for f in state["files"]}, {level})
                for f in state["files"]:
                    self.assertEqual(f["written"], bm.canonical_sha256(read(self.target, f["path"])))
                    self.assertEqual(f["sha256"], bm.canonical_sha256(files[f["path"]]))
                self.assertEqual(self.leftover_temps(), [])
                shutil.rmtree(self.target)

    def test_t4_case21_only_model_and_effort_lines_change(self):
        hooks_block = "\n".join(SENTINEL_HOOKS).encode("ascii") + b"\n"
        for level in (1, 2, 3, 4):
            with self.subTest(level=level):
                files = self.make_level_source()
                self.set_level(level)
                self.install_ok()
                for rel, data in files.items():
                    got = read(self.target, rel)
                    self.assertNotIn(b"\r", got, rel)
                    self.assertTrue(got.endswith(b"\n"), rel)
                    if not rel.startswith("agents/"):
                        continue
                    front_in, rest_in = split_front(data)
                    front_out, rest_out = split_front(got)
                    keep = lambda lines: [l for l in lines if not l.startswith(("model:", "effort:"))]
                    self.assertEqual(keep(front_out), keep(front_in), rel)
                    self.assertEqual(rest_out, rest_in, rel)
                    self.assertIn(len(front_out) - len(front_in), (0, 1), rel)
                    self.assertEqual(got.count(b"\nmodel: linea del cuerpo, no se toca\n"), 1, rel)
                self.assertIn(hooks_block, read(self.target, "agents/sentinel.md"))
                shutil.rmtree(self.target)

    def test_t4_case22_crlf_source_gives_the_same_result_as_lf(self):
        for level in (2, 3):
            with self.subTest(level=level):
                files = self.make_level_source(crlf=True)
                self.assertIn(b"\r\n", read(self.src, "agents/atlas.md"))
                self.set_level(level)
                self.install_ok()
                self.assert_level_installed(files, level)
                for rel in files:
                    self.assertNotIn(b"\r", read(self.target, rel), rel)
                shutil.rmtree(self.target)

    def test_t4_case23_existing_effort_is_replaced_or_kept(self):
        files = dict(LEVEL_SAMPLE)
        files["agents/atlas.md"] = agent_md("atlas", "claude-fable-5-2", before=["effort: max"])
        files["agents/forge.md"] = agent_md("forge", "sonnet", after=["effort: xhigh"])
        files["agents/scout.md"] = agent_md("scout", "sonnet", before=["effort: low"])
        for level in (2, 3):
            with self.subTest(level=level):
                self.make_level_source(files)
                self.set_level(level)
                self.install_ok()
                self.assert_level_installed(files, level)
                table = lr.read_script_table()
                for agent in ("atlas", "forge", "scout"):
                    front, _rest = split_front(read(self.target, "agents/%s.md" % agent))
                    efforts = [l for l in front if l.startswith("effort:")]
                    self.assertEqual(len(efforts), 1, agent)
                    effort = table[(level, agent)][1]
                    if effort != "-":
                        self.assertEqual(efforts, ["effort: " + effort], agent)
                    else:
                        self.assertEqual(efforts, [{"forge": "effort: xhigh", "scout": "effort: low"}[agent]], agent)
                # en su sitio: la linea de atlas sigue antes de model:
                front, _rest = split_front(read(self.target, "agents/atlas.md"))
                self.assertLess([l.split(":")[0] for l in front].index("effort"), [l.split(":")[0] for l in front].index("model"))
                shutil.rmtree(self.target)

    DEFECTS = [
        ("sin model:", agent_md("atlas", None), "debe haber exactamente una linea model:"),
        ("model: duplicado", agent_md("atlas", "claude-fable-5-2", after=["model: opus"]),
         "debe haber exactamente una linea model:"),
        ("effort: duplicado", agent_md("atlas", "claude-fable-5-2", before=["effort: low", "effort: high"]),
         "hay mas de una linea effort:"),
        ("sin cierre", agent_md("atlas", "claude-fable-5-2").replace(b"\n---\n", b"\n", 1), "frontmatter sin cierre"),
        ("primera linea en blanco", b"\n" + agent_md("atlas", "claude-fable-5-2"), "la primera linea no es ---"),
        ("BOM", b"\xef\xbb\xbf" + agent_md("atlas", "claude-fable-5-2"), "la primera linea no es ---"),
        # Renderizado estructural (auditor y shield): un origen manipulado que pasa el Paso 2 no puede dejar YAML distinto.
        ("CR suelto tras model:", agent_md("atlas", "sonnet\rhooks:", after=["  PreToolUse: x"]), "retorno de carro"),
        ("CR suelto antes de model:", agent_md("atlas", "claude-fable-5-2", before=["color: green\rmodel: opus"]),
         "retorno de carro"),
        ("CR suelto antes de effort:", agent_md("atlas", "claude-fable-5-2", before=["color: green\reffort: max"]),
         "retorno de carro"),
        ("tabulador", agent_md("atlas", "claude-fable-5-2", before=["extra:\tvalor"]), "tabulador"),
        ("model: bloque literal", agent_md("atlas", "|", after=["  claude-fable-5-2"]), "indicador YAML"),
        ("model: bloque plegado", agent_md("atlas", ">", after=["  claude-fable-5-2"]), "indicador YAML"),
        ("model: lista", agent_md("atlas", None, after=["model:", "  - x"]), "linea model: del origen"),
        ("model: ancla", agent_md("atlas", "&m sonnet"), "indicador YAML"),
        ("model: comentario", agent_md("atlas", "sonnet # nota"), "linea model: del origen"),
        ("model: comilla sin cerrar", agent_md("atlas", "'sonnet"), "indicador YAML"),
        ("effort: comentario", agent_md("atlas", "claude-fable-5-2", before=["effort: max # c"]), "linea effort: del origen"),
        ("model: continuacion", agent_md("atlas", "sonnet", after=["  mas"]), "continuacion"),
        ("effort: continuacion", agent_md("atlas", "claude-fable-5-2", before=["effort: max", "  mas"]), "continuacion"),
        ("segundo hooks:", agent_md("atlas", "claude-fable-5-2", after=["hooks:", "  a: b", "hooks:", "  c: d"]),
         "autocomprobacion"),
        ("--- con espacio final", agent_md("atlas", "claude-fable-5-2", before=["--- "]), "forma clave"),
        ("linea ...", agent_md("atlas", "claude-fable-5-2", before=["..."]), "forma clave"),
        # Regla comun (shield y auditor): ASCII imprimible, lineas de primer nivel con forma `clave:` y valores sin indicador.
        ("NEL (U+0085) entre dos claves", agent_md("atlas", "claude-fable-5-2", before=["color: green\x85model: opus"]),
         "retorno de carro"),
        ("U+2028 en una linea", agent_md("atlas", "claude-fable-5-2", before=["color: green\xe2\x80\xa8x: y"]),
         "retorno de carro"),
        ("--- seguido de NBSP", agent_md("atlas", "claude-fable-5-2", before=["---\xc2\xa0"]), "retorno de carro"),
        ("--- seguido de U+2028", agent_md("atlas", "claude-fable-5-2", before=["---\xe2\x80\xa8"]), "retorno de carro"),
        ("... seguido de NBSP", agent_md("atlas", "claude-fable-5-2", before=["...\xc2\xa0"]), "retorno de carro"),
        ("BOM interior delante de hooks: x", agent_md("atlas", "claude-fable-5-2", before=["\xef\xbb\xbfhooks: x"]),
         "retorno de carro"),
        ("hooks : x", agent_md("atlas", "claude-fable-5-2", before=["hooks : x"]), "forma clave"),
        ('"hooks": x', agent_md("atlas", "claude-fable-5-2", before=['"hooks": x']), "forma clave"),
        ("? hooks / : x", agent_md("atlas", "claude-fable-5-2", before=["? hooks", ": x"]), "forma clave"),
        ("{hooks: none}", agent_md("atlas", "claude-fable-5-2", before=["{hooks: none}"]), "forma clave"),
        ("model : opus", agent_md("atlas", "claude-fable-5-2", before=["model : opus"]), "forma clave"),
        ("lista de flujo abierta con model: dentro", agent_md("atlas", "sonnet", before=["flow: [Read, Write,"],
                                                              after=["Grep]"]), "forma clave"),
        ("lista de flujo abierta con la continuacion sangrada", agent_md("atlas", "sonnet", before=["flow: [Read, Write,"],
                                                                         after=["  Grep]"]), "indicador YAML"),
        ("comillas abiertas de otra clave", agent_md("atlas", "sonnet", before=['zz: "a'], after=['b: c"']),
         "indicador YAML"),
        ("valor con corchete", agent_md("atlas", "claude-fable-5-2", before=["k: [a]"]), "indicador YAML"),
        ("valor con llave", agent_md("atlas", "claude-fable-5-2", before=["k: {a: b}"]), "indicador YAML"),
        ("valor con ancla de alias", agent_md("atlas", "claude-fable-5-2", before=["k: *a"]), "indicador YAML"),
        ("valor con etiqueta", agent_md("atlas", "claude-fable-5-2", before=["k: !tag x"]), "indicador YAML"),
        ("valor con porcentaje", agent_md("atlas", "claude-fable-5-2", before=["k: %x"]), "indicador YAML"),
        ("valor con arroba", agent_md("atlas", "claude-fable-5-2", before=["k: @x"]), "indicador YAML"),
        ("valor con acento grave", agent_md("atlas", "claude-fable-5-2", before=["k: `x"]), "indicador YAML"),
        ("valor con comilla doble", agent_md("atlas", "claude-fable-5-2", before=['k: "x']), "indicador YAML"),
        # Hueco envolvente (shield y auditor): una linea con sangria antes de model: o de effort: podria ser la
        # continuacion de un valor abierto que model: cierra. Se rechaza cualquier sangria hasta la mayor de las dos.
        ("comilla abierta que model: envuelve", agent_md("atlas", "sonnet", before=["xq:", '  "abc'], after=['q: r"']),
         "con sangria antes de"),
        ("corchete abierto que model: envuelve", agent_md("atlas", "sonnet", before=["xf:", "  [a,"], after=["b: ]"]),
         "con sangria antes de"),
        ("llave abierta que model: envuelve", agent_md("atlas", "sonnet", before=["xf:", "  {a: 1,"], after=["b: c}"]),
         "con sangria antes de"),
        ("lista de flujo en hooks: antes de model:", agent_md("atlas", "sonnet", before=["hooks:", "  PreToolUse: [ {a: 1},"],
                                                             after=["b: 2 ]"]), "con sangria antes de"),
        ("hooks: con hijos antes de model:", agent_md("atlas", "sonnet", before=["hooks:", "  PreToolUse:", "    - x"]),
         "con sangria antes de"),
        ("sangria entre model: y effort:", agent_md("atlas", "sonnet", after=["hooks:", "  a: b", "effort: max"]),
         "con sangria antes de"),
    ]

    def test_t4_the_reference_renderer_rejects_the_same_defects(self):
        # render_expected (referencia independiente, Python) tiene las mismas reglas: no comparte el punto ciego.
        for name, data, _motivo in self.DEFECTS:
            for effort in ("-", "medium"):
                with self.subTest(case=name, effort=effort):
                    with self.assertRaises(ValueError):
                        lr.render_expected(data, "sonnet", effort)

    def test_t4_case24_defective_frontmatter_exit1_in_both_modes_and_writes_nothing(self):
        for name, data, motivo in self.DEFECTS:
            for level in (3, 1):
                with self.subTest(case=name, level=level):
                    files = dict(LEVEL_SAMPLE)
                    files["agents/atlas.md"] = data
                    self.make_level_source(files)
                    self.set_level(level)
                    before = snapshot(self.target)
                    listing = sorted(os.listdir(self.tmp))
                    for mode in (["-DryRun"], []):
                        code, out, err = self.run_install(*mode)
                        self.assertEqual(code, 1, out + err)
                        self.assertIn("error: no se puede aplicar el nivel %d a agents/atlas.md: " % level, err)
                        self.assertIn(motivo, err)
                        self.assertIn(". No se escribio nada.", err)
                        self.assertTrue(err.isascii(), repr(err))
                        self.assertNotIn("Copiado", out)
                        self.assertEqual(snapshot(self.target), before)
                        self.assertEqual(sorted(os.listdir(self.tmp)), listing)
                    shutil.rmtree(self.target)

    def test_t4_case24_a_defect_only_matters_where_the_agent_is_rendered(self):
        # Nivel 5 no renderiza; auditor no es modificable: el mismo defecto no detiene la instalacion.
        for name, data, _motivo in self.DEFECTS:
            with self.subTest(case=name, level=5):
                files = dict(LEVEL_SAMPLE)
                files["agents/atlas.md"] = data
                self.make_level_source(files)
                self.install_ok()
                self.assertEqual(read(self.target, "agents/atlas.md"), data.replace(b"\r\n", b"\n"))
                shutil.rmtree(self.target)
            with self.subTest(case=name, fixed_agent_at_level=3):
                files = dict(LEVEL_SAMPLE)
                files["agents/auditor.md"] = data
                self.make_level_source(files)
                self.set_level(3)
                self.install_ok()
                self.assertEqual(read(self.target, "agents/auditor.md"), data)
                shutil.rmtree(self.target)

    def test_t4_case25_indented_model_and_body_model_are_not_touched(self):
        files = dict(LEVEL_SAMPLE)
        # Las lineas con sangria van DESPUES de model: (antes se rechazan: hueco envolvente).
        files["agents/atlas.md"] = agent_md("atlas", "claude-fable-5-2",
                                            after=["meta:", "  model: indentado-despues", "  effort: indentado-despues"])
        self.make_level_source(files)
        self.set_level(3)
        self.install_ok()
        self.assert_level_installed(files, 3)
        got = read(self.target, "agents/atlas.md")
        self.assertIn(b"\nmodel: opus\neffort: medium\nmeta:\n  model: indentado-despues\n  effort: indentado-despues\ncolor: blue\n", got)
        self.assertIn(b"\nmodel: linea del cuerpo, no se toca\n", got)
        self.assertEqual(got.count(b"effort: medium"), 1)

    def test_t4_case26_cell_equal_to_the_source_keeps_the_bytes_and_is_igual(self):
        files = self.make_level_source()
        self.install_ok()
        self.set_level(4)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        states = self.states(out)
        expected = level_expected(files, 4)
        for rel, data in files.items():
            self.assertEqual(states[rel], "IGUAL" if expected[rel] == data else "ACTUALIZAR", rel)
        self.assertEqual(states["agents/forge.md"], "IGUAL")
        self.assertEqual(states["agents/atlas.md"], "ACTUALIZAR")
        self.assertEqual(read(self.target, "agents/forge.md"), files["agents/forge.md"])
        self.assert_level_installed(files, 4)
        self.assertEqual(sorted(self.tree(backup)),
                         sorted([os.path.join(*r.split("/")) for r in files if expected[r] != files[r]] + ["synclayer-manifest.json"]))

    def test_t4_levels_down_and_up_with_intact_files_are_actualizar_with_backup(self):
        files = self.make_level_source()
        self.install_ok()
        previous = 5
        for step, level in enumerate((3, 1, 5, 2)):
            with self.subTest(step=step, level=level):
                self.set_level(level)
                backup = os.path.join(self.tmp, "respaldo%d" % step)
                old = level_expected(files, previous)
                new = level_expected(files, level)
                out, err = self.install_ok("-BackupDir", backup)
                states = self.states(out)
                changed = [rel for rel in files if old[rel] != new[rel]]
                self.assertTrue(changed)
                for rel in files:
                    self.assertEqual(states[rel], "ACTUALIZAR" if rel in changed else "IGUAL", rel)
                self.assert_level_installed(files, level)
                saved = self.tree(backup)
                self.assertEqual(sorted(saved), sorted([os.path.join(*r.split("/")) for r in changed] + ["synclayer-manifest.json"]))
                for rel in changed:
                    self.assertEqual(saved[os.path.join(*rel.split("/"))], old[rel], rel)
                previous = level

    def test_t4_back_to_level_5_restores_the_repository_bytes(self):
        files = self.make_level_source()
        self.set_level(1)
        self.install_ok()
        self.assertNotEqual(read(self.target, "agents/atlas.md"), files["agents/atlas.md"])
        self.set_level(5)
        out, err = self.install_ok()
        for rel, data in files.items():
            self.assertEqual(read(self.target, rel), data, rel)
        self.assert_state(5)

    def test_t4_reinstalling_the_same_level_is_igual_and_writes_nothing(self):
        for level in (1, 3, 4):
            with self.subTest(level=level):
                self.make_level_source()
                self.set_level(level)
                self.install_ok()
                snap = snapshot(self.target)
                listing = sorted(os.listdir(self.tmp))
                out, err = self.install_ok()
                self.assertEqual(set(self.states(out).values()), {"IGUAL"})
                self.assertEqual(snapshot(self.target), snap)
                self.assertEqual(sorted(os.listdir(self.tmp)), listing)
                self.assertIn("escritos=0", out)
                self.assertNotIn("Respaldo", out)
                shutil.rmtree(self.target)

    def test_t4_case27_modifiable_agent_missing_from_the_manifest_is_not_an_error(self):
        files = {rel: data for rel, data in LEVEL_SAMPLE.items() if rel not in ("agents/oracle.md", "agents/scout.md")}
        self.make_level_source(files)
        self.set_level(2)
        out, err = self.install_ok()
        self.assertNotIn("oracle", out)
        self.assertNotIn("scout", out)
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("Ajuste:")]), 4)
        self.assert_level_installed(files, 2)
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "oracle.md")))

    def test_t4_case28_dryrun_level_3_prints_nivel_and_ajuste_lines_and_writes_nothing(self):
        self.make_level_source()
        self.set_level(3)
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        lines = out.splitlines()
        self.assertIn("Nivel: 3 (synclayer-config.json)", lines)
        table = lr.read_script_table()
        want = ["Ajuste: agents/%s.md  model: %s  effort: %s" % ((a,) + table[(3, a)])
                for a in sorted(lr.read_ps_list("LevelAgents"))]
        got = [l for l in lines if l.startswith("Ajuste:")]
        self.assertEqual(got, want)
        self.assertIn("Ajuste: agents/atlas.md  model: opus  effort: medium", got)
        self.assertIn("Ajuste: agents/sentinel.md  model: sonnet  effort: -", got)
        self.assertGreater(lines.index(got[0]), [i for i, l in enumerate(lines) if l.startswith("Resumen:")][0])
        self.assertEqual(self.states(out), {rel: "NUEVO" for rel in LEVEL_SAMPLE})
        self.assertEqual(snapshot(self.target), before)
        self.assertEqual(sorted(os.listdir(self.tmp)), listing)

    def test_t4_case29_real_repo_as_source_levels_1_to_4(self):
        agents = lr.read_ps_list("LevelAgents")
        for level in (1, 2, 3, 4):
            with self.subTest(level=level):
                files = self.real_repo_source()
                self.set_level(level)
                self.install_ok()
                got = sorted(os.path.relpath(os.path.join(d, f), self.target).replace("\\", "/")
                             for d, _s, fs in os.walk(self.target) for f in fs)
                self.assertEqual(got, sorted(list(files) + ["synclayer-manifest.json", self.CONFIG]))
                self.assertEqual(len(files), 12)
                manifest = {e["path"]: e["sha256"] for e in json.loads(read(ROOT, "install-manifest.json"))["files"]}
                modifiable = ["agents/%s.md" % a for a in agents]
                self.assertEqual(len([r for r in files if r in modifiable]), 6)
                for rel in files:
                    if rel in modifiable:
                        name = rel.split("/")[1][:-3]
                        model, effort = lr.read_script_table()[(level, name)]
                        self.assertEqual(read(self.target, rel), lr.render_expected(files[rel].replace(b"\r\n", b"\n"), model, effort), rel)
                    else:
                        self.assertEqual(bm.canonical_sha256(read(self.target, rel)), manifest[rel], rel)
                self.assert_level_installed(files, level)
                self.assertIn(b"hooks:", read(self.target, "agents/sentinel.md"))
                self.assertFalse(os.path.exists(os.path.join(self.target, "docs", "brand")))
                shutil.rmtree(self.target)

    def test_t4_case30_post_verification_catches_an_altered_file_at_level_3(self):
        self.make_level_source()
        self.set_level(3)
        atlas = os.path.join(self.target, "agents", "atlas.md").replace("'", "''")
        self.patch_script("# Paso 8:", "[System.IO.File]::AppendAllText('%s', 'x')" % atlas)
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("la verificacion posterior fallo", err)
        self.assertIn("agents/atlas.md", err)
        self.assertFalse(os.path.exists(os.path.join(self.target, "synclayer-manifest.json")))

    def test_t4_the_renderer_runs_only_for_the_six_agents_and_never_at_level_5(self):
        marker = "[Console]::Out.WriteLine('RENDER-LLAMADO ' + $Model + ' ' + $Effort)"
        for config, calls in ((None, 0), (b'{"level": 5}', 0), (b"{}", 0), (b'{"level": 3}', 6)):
            with self.subTest(config=config):
                self.make_level_source()
                self.patch_script("function ConvertTo-LevelBytes", marker)
                if config is not None:
                    self.write_config(config)
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 0, out + err)
                    self.assertEqual(len([l for l in out.splitlines() if l.startswith("RENDER-LLAMADO")]), calls)
                    self.assertEqual(len([l for l in out.splitlines() if l.startswith("Ajuste:")]), calls)
                shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))
                shutil.rmtree(self.target, ignore_errors=True)

    def test_t4_level_5_writes_the_source_bytes_and_prints_no_ajuste(self):
        files = self.make_level_source()
        out, err = self.install_ok()
        for rel, data in files.items():
            self.assertEqual(read(self.target, rel), data, rel)
        self.assertNotIn("Ajuste:", out)
        self.assert_state(5)

    def test_t4_a_value_outside_the_closed_lists_is_never_rendered(self):
        # La funcion se invoca directamente con celdas fuera de las listas cerradas: exit 1 antes de escribir.
        self.make_level_source()
        path = os.path.join(self.src, "install.ps1")
        with open(path, "rb") as f:
            text = f.read().decode("ascii")
        call = "$cell = Get-LevelCell $level $agentMatch.Groups[1].Value"
        self.assertEqual(text.count(call), 1)
        for bad in ("@{ Model = 'opus-9'; Effort = '-' }", "@{ Model = 'opus'; Effort = 'extreme' }",
                    "@{ Model = 'Opus'; Effort = '-' }", "@{ Model = 'opus'; Effort = '' }"):
            with self.subTest(cell=bad):
                with open(path, "wb") as f:
                    f.write(text.replace(call, "$cell = " + bad).encode("ascii"))
                self.set_level(3)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertIn("fuera de la lista cerrada", err)
                self.assertIn(". No se escribio nada.", err)
                shutil.rmtree(self.target)

    def test_t4_self_check_catches_a_corrupted_result_with_coverage(self):
        # Se estropea $result justo despues de construirlo (hooks: pasa a hookz:): la autocomprobacion debe
        # detenerlo con exit 1 en ambos modos y sin escribir nada.
        self.make_level_source()
        self.set_level(3)
        self.patch_script("$result = $latin1.GetBytes(",
                          "$result = $latin1.GetBytes($latin1.GetString($result).Replace('hooks:', 'hookz:'))")
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("autocomprobacion", err)
                self.assertIn(". No se escribio nada.", err)
                self.assertNotIn("Copiado", out)
                self.assertEqual(snapshot(self.target), before)

    def test_t4_case25_variants(self):
        base = "claude-fable-5-2"
        ok = [
            ("sin salto final", agent_md("atlas", base).rstrip(b"\n")),
            ("--- y model: en el cuerpo", agent_md("atlas", base) + b"---\nmodel: otro\neffort: low\nmas texto\n"),
            ("Model: en mayusculas", agent_md("atlas", base, before=["Model: no-tocar"])),
            ("effort: max antes de model:", agent_md("atlas", base, before=["effort: max"])),
        ]
        rejected = [
            ("model: con comentario", agent_md("atlas", "x # nota")),
            ("effort: con comentario antes de model:", agent_md("atlas", base, before=["effort: max # c"])),
            ("CR suelto", agent_md("atlas", base, before=["color: green\rx: y"])),
        ]
        for name, data in ok:
            with self.subTest(case=name):
                files = dict(LEVEL_SAMPLE)
                files["agents/atlas.md"] = data
                self.make_level_source(files)
                self.set_level(3)
                self.install_ok()
                self.assert_level_installed(files, 3)
                got = read(self.target, "agents/atlas.md")
                if name.startswith("Model:"):
                    self.assertIn(b"\nModel: no-tocar\n", got)
                if name.startswith("---"):
                    self.assertIn(b"\n---\nmodel: otro\neffort: low\nmas texto\n", got)
                if name == "sin salto final":
                    self.assertFalse(got.endswith(b"\n"))
                shutil.rmtree(self.target)
        for name, data in rejected:
            with self.subTest(case=name):
                files = dict(LEVEL_SAMPLE)
                files["agents/atlas.md"] = data
                self.make_level_source(files)
                self.set_level(3)
                before = snapshot(self.target)
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 1, out + err)
                    self.assertIn("agents/atlas.md", err)
                    self.assertEqual(snapshot(self.target), before)
                shutil.rmtree(self.target)

    def test_t4_level_5_output_is_the_same_as_before_the_levels(self):
        # Quien no configura nada ve la misma salida que antes de T4 (literal fijado a partir del commit 2f25a64).
        self.make_source()
        out, err = self.install_ok()
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("Destino: "), lines[0])
        self.assertEqual(lines[1:], [
            "Nivel: 5 (por defecto; no hay synclayer-config.json)",
            "NUEVO       agents/alfa.md",
            "NUEVO       agents/beta.md",
            "NUEVO       docs/agentes.md",
            "NUEVO       hooks/agent_guard.py",
            "NUEVO       rules/agentes.md",
            "Resumen: NUEVO=5 IGUAL=0 ACTUALIZAR=0 MODIFICADO=0 HUERFANO=0",
            "Copiado: hooks/agent_guard.py",
            "Copiado: agents/alfa.md",
            "Copiado: agents/beta.md",
            "Copiado: docs/agentes.md",
            "Copiado: rules/agentes.md",
            "Verificado: 5 archivo(s) escritos coinciden con el manifiesto.",
            "Estado: synclayer-manifest.json actualizado.",
            "Instalacion terminada: escritos=5 IGUAL=0.",
            "Recordatorio: reinicia las sesiones de Claude Code abiertas; no ven agentes nuevos o modificados.",
            "Recordatorio: este instalador no toca settings.json ni CLAUDE.md; ~/.claude/CLAUDE.md debe apuntar a ~/.claude/rules/agentes.md.",
            "Recordatorio: no hay sincronizacion automatica; repite la instalacion cuando cambien los archivos del repositorio.",
        ])

    def test_t4_verification_messages_name_what_they_compare_with(self):
        for level, what in ((5, "el manifiesto"), (3, "lo esperado para el nivel 3"), (1, "lo esperado para el nivel 1")):
            with self.subTest(level=level):
                self.make_level_source()
                if level != 5:
                    self.set_level(level)
                out, err = self.install_ok()
                self.assertIn("Verificado: 12 archivo(s) escritos coinciden con %s." % what, out.splitlines())
                shutil.rmtree(self.target)
                # Paso 7: los bytes escritos no son los esperados (inyectado antes de la escritura): exit 4.
                self.make_level_source()
                if level != 5:
                    self.set_level(level)
                self.patch_script("Write-Atomic $dest $outBytes[$rel] $existing", "$outBytes[$rel] = [byte[]]@(88)",
                                  before=True)
                code, out, err = self.run_install()
                self.assertEqual(code, 4, out + err)
                self.assertIn("el hash del archivo escrito no coincide con %s" % what, err)
                shutil.rmtree(self.target)
                shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))

    # --- Fase 3, T2 (pendientes): Read-State con lectura unica y claves cerradas en el esquema 1 ---

    def test_t2_read_state_reads_once_with_a_cap_on_what_was_read(self):
        # Prueba estatica: la funcion no mide con FileInfo ni lee con ReadAllBytes; abre una vez (FileShare.Read) y
        # lee como maximo el tope mas uno, como Read-LevelConfig. El limite exacto lo fija la prueba de 1048576 bytes.
        with open(SCRIPT, "rb") as f:
            text = f.read().decode("ascii").replace(chr(13) + chr(10), chr(10))
        body = text.split("function Read-State(", 1)[1].split(chr(10) + "}" + chr(10), 1)[0]
        self.assertNotIn("FileInfo", body)
        self.assertNotIn("ReadAllBytes", body)
        self.assertIn("[System.IO.FileShare]::Read", body)
        self.assertIn("$StateMaxBytes + 1", body)

    def test_t2_schema1_state_with_unknown_keys_is_absent_and_never_actualizar(self):
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"version anterior\n"
        cases = [("control sin clave extra", None, 0), ("clave extra en la raiz", "root", 3),
                 ("clave extra en una entrada", "entry", 3)]
        for name, where, expected_code in cases:
            with self.subTest(case=name):
                self.make_source()
                oldsrc = os.path.join(self.tmp, "viejo")
                for rel, data in old.items():
                    write(oldsrc, rel, data)
                state = json.loads(manifest_for(oldsrc, sorted(old)))
                if where == "root":
                    state["extra"] = 1
                elif where == "entry":
                    state["files"][0]["extra"] = 1
                write(self.target, "synclayer-manifest.json", (json.dumps(state, indent=2) + "\n").encode("ascii"))
                for rel, data in old.items():
                    write(self.target, rel, data)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, expected_code, out + err)
                if where is None:
                    self.assertEqual(self.states(out)["agents/alfa.md"], "ACTUALIZAR")
                else:
                    self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
                    self.assertNotIn("ACTUALIZAR", self.states(out).values())
                    self.assertIn("clave desconocida", err)
                    self.assertIn("Se trata como ausente", err)
                shutil.rmtree(self.target)
                shutil.rmtree(oldsrc)

    # --- T6: avisos de variables de entorno (casos 38 y 39 del plan) ---

    WARN_FORCE = ("aviso: CLAUDE_CODE_SUBAGENT_MODEL_FORCE esta definida: Claude Code ignora el model: de los "
                  "agentes y el nivel %d no cambia el modelo.")
    WARN_EFFORT = "aviso: CLAUDE_CODE_EFFORT_LEVEL esta definida: tiene prioridad sobre el effort: de los agentes."

    def env_warnings(self, err):
        return [l for l in err.splitlines() if "CLAUDE_CODE_" in l]

    def test_t6_case38_warnings_for_each_variable_with_level_1_to_4(self):
        # Nivel 3: las cuatro combinaciones en los dos modos. Niveles 1, 2 y 4: solo «ambas» en -DryRun
        # (la condicion es la misma para todo nivel 1 a 4; el nivel va en el texto del aviso de FORCE).
        secret = "SECRETO-12345"
        both = {ENV_FORCE: secret, ENV_EFFORT: secret}
        combos = [
            ("solo FORCE", {ENV_FORCE: secret}, [self.WARN_FORCE]),
            ("solo EFFORT", {ENV_EFFORT: secret}, [self.WARN_EFFORT]),
            ("ambas", both, [self.WARN_FORCE, self.WARN_EFFORT]),
            ("ninguna", {}, []),
        ]
        cases = [(3, name, env, expected, mode) for name, env, expected in combos for mode in (["-DryRun"], [])]
        cases += [(level, "ambas", both, [self.WARN_FORCE, self.WARN_EFFORT], ["-DryRun"]) for level in (1, 2, 4)]
        for level, name, env, expected, mode in cases:
            with self.subTest(level=level, combo=name, mode=mode):
                self.make_source()
                self.write_config(('{"level": %d}' % level).encode("ascii"))
                code, out, err = self.run_install(*mode, env_extra=env)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.env_warnings(err), [w % level if "%d" in w else w for w in expected])
                self.assertNotIn(secret, out + err)
                self.assertEqual(self.states(out), {rel: "NUEVO" for rel in SAMPLE})
                if mode:
                    self.assertFalse(os.path.exists(os.path.join(self.target, "agents")))
                shutil.rmtree(self.target)

    def test_t6_case38_warning_does_not_change_exit_code_or_output(self):
        # Con y sin las variables: mismo codigo, mismo stdout, mismo resultado en disco.
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                results = []
                for env in ({}, {ENV_FORCE: "1", ENV_EFFORT: "high"}):
                    self.make_source()
                    self.write_config(b'{"level": 3}')
                    code, out, err = self.run_install(*mode, env_extra=env)
                    results.append((code, out, self.tree(self.target)))
                    shutil.rmtree(self.target)
                self.assertEqual(results[0], results[1])

    def test_t6_case38_warnings_come_before_the_dryrun_exit(self):
        # Los avisos salen por stderr en -DryRun (que termina con exit 0) y no cambian el codigo.
        self.make_source()
        self.write_config(b'{"level": 2}')
        code, out, err = self.run_install("-DryRun", env_extra={ENV_FORCE: "x", ENV_EFFORT: "y"})
        self.assertEqual(code, 0, out + err)
        lines = err.splitlines()
        self.assertIn(self.WARN_FORCE % 2, lines)
        self.assertIn(self.WARN_EFFORT, lines)
        self.assertIn("Modo: -DryRun (no se escribe nada)", out.splitlines())

    def test_t6_case38_value_is_never_printed_and_control_characters_do_not_break(self):
        secret = "SECRETO-12345"
        values = [
            secret,
            "\x1b[31m" + secret + "\x07\x08",
            secret + "\r\n" + secret + "\tfin",
            "é‮" + secret,
            secret * 2000,
        ]
        for i, value in enumerate(values):
            for mode in (["-DryRun"], []):
                with self.subTest(case=i, mode=mode):
                    self.make_source()
                    self.write_config(b'{"level": 4}')
                    code, out, err = self.run_install(*mode, env_extra={ENV_FORCE: value, ENV_EFFORT: value})
                    self.assertEqual(code, 0, out + err)
                    self.assertEqual(self.env_warnings(err), [self.WARN_FORCE % 4, self.WARN_EFFORT])
                    self.assertNotIn("SECRETO", out + err)
                    self.assertNotIn("\x1b", out + err)
                    self.assertTrue(err.isascii(), repr(err))
                    shutil.rmtree(self.target)

    def test_t6_case38_the_installer_reads_the_override_variables_unchanged(self):
        # Dentro del proceso del instalador, justo antes de salir, las variables siguen como llegaron.
        # (Que el instalador no las defina ni las borre lo exige la prueba estatica de StaticChecks.)
        self.make_source()
        self.patch_script("# Paso 10:", (
            "[Console]::Out.WriteLine('ENVCHK F=' + [System.Environment]::GetEnvironmentVariable('%s') + "
            "' E=' + [System.Environment]::GetEnvironmentVariable('%s'))" % ENV_OVERRIDE_VARS))
        self.write_config(b'{"level": 3}')
        code, out, err = self.run_install(env_extra={ENV_FORCE: "valorF", ENV_EFFORT: "valorE"})
        self.assertEqual(code, 0, out + err)
        self.assertIn("ENVCHK F=valorF E=valorE", out.splitlines())

    def test_t6_run_install_strips_inherited_override_variables(self):
        # run_install no hereda las variables aunque la sesion que corre la suite las defina.
        self.make_source()
        self.write_config(b'{"level": 3}')
        saved = {n: os.environ.get(n) for n in ENV_OVERRIDE_VARS}
        try:
            for n in ENV_OVERRIDE_VARS:
                os.environ[n] = "HEREDADO-SECRETO"
            code, out, err = self.run_install("-DryRun")
        finally:
            for n, v in saved.items():
                if v is None:
                    os.environ.pop(n, None)
                else:
                    os.environ[n] = v
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.env_warnings(err), [])
        self.assertNotIn("HEREDADO", out + err)

    def test_t6_case39_no_warning_with_level_5(self):
        env = {ENV_FORCE: "SECRETO-12345", ENV_EFFORT: "SECRETO-12345"}
        for mode in (["-DryRun"], []):
            for config in (None, b'{"level": 5}', b"{}"):
                with self.subTest(mode=mode, config=config):
                    self.make_source()
                    if config is not None:
                        self.write_config(config)
                    clean = self.run_install(*mode)
                    code0, out0, err0 = clean
                    snap0 = self.tree(self.target)
                    shutil.rmtree(self.target, ignore_errors=True)
                    if config is not None:
                        self.write_config(config)
                    code, out, err = self.run_install(*mode, env_extra=env)
                    self.assertEqual((code, out, err), clean)
                    self.assertEqual(code, 0, out + err)
                    self.assertEqual(self.env_warnings(err), [])
                    self.assertEqual(self.tree(self.target), snap0)
                    shutil.rmtree(self.target, ignore_errors=True)

    def test_t6_case39_absent_or_empty_string_variable_with_level_3_gives_no_warning(self):
        # Una variable "" pasada desde Python llega al instalador como ausente ($null en PS 5.1): esta
        # prueba fija «ausente / cadena vacia: sin aviso». La otra variable, con valor, si avisa.
        self.make_source()
        self.write_config(b'{"level": 3}')
        code, out, err = self.run_install("-DryRun", env_extra={ENV_FORCE: "", ENV_EFFORT: ""})
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.env_warnings(err), [])
        code, out, err = self.run_install("-DryRun", env_extra={ENV_FORCE: "", ENV_EFFORT: "high"})
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.env_warnings(err), [self.WARN_EFFORT])

    def test_t6_whitespace_only_variable_with_level_3_does_warn(self):
        # Decision fijada: «existe y no esta vacia» (3.8). Solo espacios no es vacia: avisa (T7 lo documenta).
        self.make_source()
        self.write_config(b'{"level": 3}')
        code, out, err = self.run_install("-DryRun", env_extra={ENV_FORCE: "   ", ENV_EFFORT: "   "})
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.env_warnings(err), [self.WARN_FORCE % 3, self.WARN_EFFORT])

    def test_t3_config_validation_runs_before_any_write_even_with_a_valid_state(self):
        # Instalacion previa y configuracion invalida despues: nada cambia (ni el estado ni los archivos).
        self.make_source()
        self.install_ok()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        self.write_config(b'{"level": "x"}')
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        for mode in (["-DryRun"], []):
            code, out, err = self.run_install(*mode)
            self.assertEqual(code, 1, out + err)
            self.assertEqual(snapshot(self.target), before)
            self.assertEqual(sorted(os.listdir(self.tmp)), listing)

    def test_backup_dir_inside_target_exit1_in_both_modes(self):
        self.make_source()
        for name, backup in (("subcarpeta", os.path.join(self.target, "agents", "old")),
                             ("el propio destino", self.target)):
            for mode in (["-DryRun"], []):
                with self.subTest(case=name, mode=mode):
                    code, out, err = self.run_install(*(mode + ["-BackupDir", backup]))
                    self.assertEqual(code, 1, out + err)
                    self.assertIn("dentro de -Target", err)
        self.assertFalse(os.path.exists(self.target))

    def test_backup_dir_sibling_with_same_prefix_is_not_inside_target(self):
        self.make_source()
        code, out, err = self.run_install("-DryRun", "-BackupDir", self.target + "-x")
        self.assertEqual(code, 0, out + err)

    def test_existing_empty_backup_dir_exit1_in_both_modes(self):
        # Un respaldo va en una carpeta nueva: una existente (aunque vacia) se rechaza.
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa 2\n")
        backup = os.path.join(self.tmp, "respaldo")
        os.makedirs(backup)
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*(mode + ["-BackupDir", backup]))
                self.assertEqual(code, 1, out + err)
                self.assertIn("ya existe el respaldo", err)
                self.assertEqual(os.listdir(backup), [])
                self.assertEqual(snapshot(self.target), before)

    def test_home_env_differs_from_powershell_home_warns_which_copy_runs(self):
        self.make_source()
        other = os.path.join(self.tmp, "otro home")
        code, out, err = self.run_install(env_extra={"HOME": other})
        self.assertEqual(code, 0, out + err)
        self.assertIn("aviso: la variable de entorno HOME", err)
        self.assertIn(other, err)
        self.assertIn(self.home, err)
        self.assertIn(other + "/.claude/hooks/agent_guard.py", err)
        self.assertIn(self.home + "/.claude/hooks/agent_guard.py", err)
        self.assertNotIn("aviso", out)

    def test_home_env_equal_to_powershell_home_does_not_warn(self):
        self.make_source()
        out, err = self.install_ok()
        self.assertNotIn("difiere", err)

    @unittest.skipUnless(os.name == "nt", "icacls es de Windows")
    def test_hook_with_explicit_write_ace_for_other_account_warns(self):
        self.make_source()
        self.preinstall()
        hook = os.path.join(self.target, "hooks", "agent_guard.py")
        grant = subprocess.run(["icacls", hook, "/grant", "*S-1-1-0:(W)"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if grant.returncode != 0:
            self.skipTest("icacls no pudo conceder la escritura")
        self.addCleanup(subprocess.run, ["icacls", hook, "/remove:g", "*S-1-1-0"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = self.install_ok()
        self.assertIn("permisos de escritura explicitos", err)
        self.assertIn("S-1-1-0", err)
        self.assertNotIn("S-1-5-18", err)

    def test_hook_without_foreign_write_ace_does_not_warn(self):
        self.make_source()
        out, err = self.install_ok()
        self.assertNotIn("permisos de escritura", err)

    def test_replace_failure_1177_keeps_the_only_new_copy_and_reports_its_path(self):
        # ERROR_UNABLE_TO_MOVE_REPLACEMENT_2 inyectado en lugar de File.Replace: el temporal no se borra.
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        path = os.path.join(self.src, "install.ps1")
        with open(path, "rb") as f:
            text = f.read().decode("ascii")
        call = "[System.IO.File]::Replace($tmp, $Dest, [NullString]::Value)"
        self.assertEqual(text.count(call), 1)
        with open(path, "wb") as f:
            f.write(text.replace(call, "throw (New-Object System.IO.IOException('prueba', -2147023719))").encode("ascii"))
        code, out, err = self.run_install("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 4, out + err)
        temps = self.leftover_temps()
        self.assertEqual(len(temps), 1, err)
        self.assertIn(os.path.basename(temps[0]), err)
        self.assertIn("no se borra", err)
        with open(temps[0], "rb") as f:
            self.assertEqual(f.read(), b"alfa nueva\n")

    def test_replace_failure_other_code_still_deletes_own_temp(self):
        self.make_source()
        self.preinstall()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        path = os.path.join(self.src, "install.ps1")
        with open(path, "rb") as f:
            text = f.read().decode("ascii")
        call = "[System.IO.File]::Replace($tmp, $Dest, [NullString]::Value)"
        with open(path, "wb") as f:
            f.write(text.replace(call, "throw (New-Object System.IO.IOException('prueba', -2147024864))").encode("ascii"))
        code, out, err = self.run_install("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 4, out + err)
        self.assertEqual(self.leftover_temps(), [])
        self.assertNotIn("no se borra", err)

    @unittest.skipUnless(os.name == "nt", "New-Item -ItemType Junction solo en Windows")
    def test_junction_injected_just_before_writing_is_detected_after_exit4(self):
        # La carrera no se cierra (el archivo llega a la carpeta externa), pero ya no termina en exit 0.
        self.make_source()
        os.makedirs(self.outside)
        link = os.path.join(self.target, "hooks")
        self.patch_script("Write-Atomic $dest $outBytes[$rel] $existing",
                          "[void][System.IO.Directory]::CreateDirectory('%s'); New-Item -ItemType Junction -Path '%s' -Value '%s' | Out-Null"
                          % (self.target.replace("'", "''"), link.replace("'", "''"), self.outside.replace("'", "''")),
                          before=True)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("punto de reanalisis", err)
        self.assertIn("Aparecio mientras se escribia", err)
        self.assertIn("fallo la copia de hooks/agent_guard.py", err)
        self.assertEqual(os.listdir(self.outside), ["agent_guard.py"])
        self.assertNotIn("Copiado: hooks/agent_guard.py", out)
        self.assertFalse(os.path.exists(os.path.join(self.target, "synclayer-manifest.json")))

    @unittest.skipUnless(os.name == "nt", "New-Item -ItemType Junction solo en Windows")
    def test_junction_injected_at_verification_is_exit4_with_reparse_message(self):
        self.make_source()
        os.makedirs(self.outside)
        hooks = os.path.join(self.target, "hooks")
        self.patch_script("# Paso 8:",
                          "[System.IO.Directory]::Move('%s', '%s'); New-Item -ItemType Junction -Path '%s' -Value '%s' | Out-Null"
                          % (hooks.replace("'", "''"), (hooks + ".real").replace("'", "''"),
                             hooks.replace("'", "''"), self.outside.replace("'", "''")))
        self.addCleanup(lambda: os.path.isdir(hooks) and os.rmdir(hooks))
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("la verificacion posterior fallo", err)
        self.assertIn("punto de reanalisis", err)
        self.assertEqual(os.listdir(self.outside), [])
        self.assertFalse(os.path.exists(os.path.join(self.target, "synclayer-manifest.json")))

    @unittest.skipUnless(os.name == "nt", "New-Item -ItemType Junction solo en Windows")
    def test_junction_at_state_path_injected_at_step9_exit4_nothing_outside(self):
        self.make_source()
        os.makedirs(self.outside)
        link = os.path.join(self.target, "synclayer-manifest.json")
        self.patch_script("# Paso 9:", "New-Item -ItemType Junction -Path '%s' -Value '%s' | Out-Null"
                          % (link.replace("'", "''"), self.outside.replace("'", "''")))
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("no se pudo escribir synclayer-manifest.json", err)
        self.assertIn("punto de reanalisis", err)
        self.assertEqual(os.listdir(self.outside), [])

    @unittest.skipUnless(os.name == "nt", "New-Item -ItemType Junction solo en Windows")
    def test_target_turned_into_junction_during_state_write_is_exit4(self):
        # Repeticion tras escribir el estado: -Target pasa a ser un enlace justo antes de Write-Atomic.
        self.make_source()
        real = self.target + ".real"
        self.patch_script("Write-Atomic $statePath $stateBytes $stateExists",
                          "[System.IO.Directory]::Move('%s', '%s'); New-Item -ItemType Junction -Path '%s' -Value '%s' | Out-Null"
                          % (self.target.replace("'", "''"), real.replace("'", "''"),
                             self.target.replace("'", "''"), real.replace("'", "''")),
                          before=True)
        self.addCleanup(lambda: os.path.isdir(self.target) and os.rmdir(self.target))
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("Aparecio mientras se escribia", err)
        self.assertTrue(os.path.exists(os.path.join(real, "synclayer-manifest.json")))

    # --- Fase 3, T5: cambios de nivel, ediciones a mano y -Force (casos 31 a 37 y la tabla de situaciones de 3.5) ---
    #
    # Mapa de la tabla «Cómo quedan las situaciones que importan» (3.5) a sus pruebas:
    #   Sin configuracion, destino de la Fase 1 ........ test_t5_situation_phase1_target_without_config_is_igual_and_migrates
    #   Nivel 5 a 3 / 3 a 5 ............................ test_t5_case31_level_changes_are_actualizar_with_backup_and_the_previous_level
    #   Edicion a mano de model: tras instalar ......... test_t5_case32_manual_edit_is_modified_exit3_writes_nothing_and_force_backs_up
    #   Edicion a mano de un agente fijo ............... (la misma, con auditor, shield y debugger)
    #   Edicion a mano y luego cambio de nivel ......... test_t5_case32_manual_edit_then_level_change_is_modified_for_that_file_only
    #   Cambio de nivel y del origen a la vez .......... test_t5_case34_level_change_and_source_change_together_are_actualizar
    #   Estado schema 1, destino intacto, nivel 3 ...... test_t5_case33_schema1_state_with_intact_destination_at_level_3_is_actualizar
    #   Sin estado, destino del repositorio, nivel 3 ... test_t5_case35_unreadable_absent_or_unknown_state_is_treated_as_absent
    #   Estado ilegible, destino ya en el nivel ........ (la misma)
    #   Estado de otro nivel, archivos ya en el nuevo .. test_t5_state_of_another_level_with_files_already_at_the_new_level_is_igual
    #   HUERFANO con cambio de nivel ................... test_t5_orphan_is_reported_and_kept_on_a_level_change

    PHRASE = "Si cambiaste model: o effort: a mano, usa synclayer-config.json."

    def t5_first_install(self, level):
        files = self.make_level_source()
        if level != 5:
            self.set_level(level)
        self.install_ok()
        return files

    def t5_world(self):
        return snapshot(self.target), sorted(os.listdir(self.tmp))

    def t5_changed(self, files, old_level, new_level):
        old = level_expected(files, old_level)
        new = level_expected(files, new_level)
        return [rel for rel in files if old[rel] != new[rel]]

    def t5_prev_lines(self, out):
        return [l for l in out.splitlines() if l.startswith("Nivel anterior:")]

    def t5_assert_previous_level(self, out, previous):
        """Una sola linea `Nivel anterior: M`, justo despues de la linea `Nivel:`."""
        lines = out.splitlines()
        idx = [n for n, l in enumerate(lines) if l.startswith("Nivel: ")]
        self.assertEqual(len(idx), 1, out)
        self.assertEqual(lines[idx[0] + 1], "Nivel anterior: %d" % previous, out)
        self.assertEqual(self.t5_prev_lines(out), ["Nivel anterior: %d" % previous])

    def t5_path(self, rel):
        return os.path.join(*rel.split("/"))

    def test_t5_case31_level_changes_are_actualizar_with_backup_and_the_previous_level(self):
        files = self.t5_first_install(5)
        previous = 5
        for step, level in enumerate((3, 1, 3, 5)):
            # `previous` avanza antes de las aserciones; si el paso falla, se resincroniza el destino con -Force
            # para que los pasos siguientes no fallen en cascada por un punto de partida equivocado.
            prior, previous = previous, level
            ok = False
            with self.subTest(step=step, previous=prior, level=level):
                self.set_level(level)
                backup = os.path.join(self.tmp, "respaldo%d" % step)
                old = level_expected(files, prior)
                changed = self.t5_changed(files, prior, level)
                self.assertTrue(changed)
                old_state = read(self.target, self.STATE)
                wanted = {rel: ("ACTUALIZAR" if rel in changed else "IGUAL") for rel in files}
                before = self.t5_world()
                code, out, err = self.run_install("-DryRun", "-BackupDir", backup)
                self.assertEqual(code, 0, out + err)
                self.t5_assert_previous_level(out, prior)
                self.assertEqual(self.states(out), wanted)
                self.assertIn("Respaldo: ", out)
                self.assertEqual(self.t5_world(), before)
                self.assertFalse(os.path.exists(backup))
                out, err = self.install_ok("-BackupDir", backup)
                self.t5_assert_previous_level(out, prior)
                self.assertEqual(self.states(out), wanted)
                self.assert_level_installed(files, level)
                saved = self.tree(backup)
                self.assertEqual(sorted(saved), sorted([self.t5_path(r) for r in changed] + [self.STATE]))
                for rel in changed:
                    self.assertEqual(saved[self.t5_path(rel)], old[rel], rel)
                self.assertEqual(saved[self.STATE], old_state)
                ok = True
            if not ok:
                self.run_install("-Force", "-BackupDir", os.path.join(self.tmp, "resync%d" % step))
        for rel, data in files.items():
            self.assertEqual(read(self.target, rel), data, rel)

    def test_t5_the_previous_level_line_appears_only_when_a_valid_state_has_another_level(self):
        self.make_level_source()
        self.set_level(3)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.t5_prev_lines(out), [], "sin estado")
        self.install_ok()
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(self.t5_prev_lines(out), [], "mismo nivel")
        out, err = self.install_ok()
        self.assertEqual(self.t5_prev_lines(out), [], "mismo nivel, ejecucion real")
        self.set_level(4)
        code, out, err = self.run_install("-DryRun")
        self.t5_assert_previous_level(out, 3)
        # un estado con niveles mezclados (no lo escribe este instalador) no dice un nivel anterior
        state = json.loads(read(self.target, self.STATE))
        state["files"][0]["level"] = 2
        write(self.target, self.STATE, (json.dumps(state, indent=2) + "\n").encode("ascii"))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.t5_prev_lines(out), [], "niveles mezclados")

    def test_t5_situation_phase1_target_without_config_is_igual_and_migrates(self):
        files = self.make_level_source()
        for rel, data in files.items():
            write(self.target, rel, data)
        self.write_state(files, schema=1)
        old_state = read(self.target, self.STATE)
        backup = os.path.join(self.tmp, "respaldo")
        for mode in (["-DryRun"], []):
            code, out, err = self.run_install(*mode, "-BackupDir", backup)
            self.assertEqual(code, 0, out + err)
            self.assertEqual(set(self.states(out).values()), {"IGUAL"})
            self.assertEqual(self.t5_prev_lines(out), [], "el esquema 1 es el nivel 5: no hay nivel anterior")
            self.assertIn("Nivel: 5 (por defecto", out)
        self.assert_level_installed(files, 5)
        self.assertEqual(self.tree(backup), {self.STATE: old_state})

    def test_t5_case32_manual_edit_is_modified_exit3_writes_nothing_and_force_backs_up(self):
        combos = [(5, "agents/atlas.md"), (5, "agents/auditor.md"), (3, "agents/atlas.md"), (3, "agents/auditor.md"),
                  (3, "agents/shield.md"), (3, "agents/debugger.md"), (3, "agents/forge.md"),
                  (1, "agents/atlas.md"), (1, "agents/auditor.md")]
        for n, (level, rel) in enumerate(combos):
            with self.subTest(level=level, rel=rel):
                shutil.rmtree(self.target, ignore_errors=True)
                files = self.t5_first_install(5)
                if level != 5:
                    # la edicion llega despues de un cambio de nivel, no de una instalacion limpia
                    self.set_level(level)
                    self.install_ok()
                expected = level_expected(files, level)
                edited = read(self.target, rel).replace(b"\nmodel: ", b"\nmodel: manual-", 1)
                self.assertNotEqual(edited, expected[rel])
                write(self.target, rel, edited)
                before = self.t5_world()
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 3, out + err)
                    self.assertEqual(self.states(out), {r: ("MODIFICADO" if r == rel else "IGUAL") for r in files})
                    self.assertIn(self.PHRASE, err)
                    self.assertEqual(self.t5_world(), before)
                backup = os.path.join(self.tmp, "respaldo%d" % n)
                self.install_ok("-Force", "-BackupDir", backup)
                self.assertEqual(self.tree(backup), {self.t5_path(rel): edited})
                self.assertEqual(read(self.target, rel), expected[rel])
                self.assert_level_installed(files, level)
                shutil.rmtree(self.target)

    def test_t5_case32_manual_edit_then_level_change_is_modified_for_that_file_only(self):
        files = self.t5_first_install(3)
        rel = "agents/atlas.md"
        old = level_expected(files, 3)
        edited = read(self.target, rel).replace(b"\nmodel: ", b"\nmodel: manual-", 1)
        write(self.target, rel, edited)
        old_state = read(self.target, self.STATE)
        self.set_level(1)
        changed = self.t5_changed(files, 3, 1)
        self.assertIn(rel, changed)
        self.assertGreater(len(changed), 1)
        wanted = {r: ("MODIFICADO" if r == rel else ("ACTUALIZAR" if r in changed else "IGUAL")) for r in files}
        before = self.t5_world()
        for mode in (["-DryRun"], []):
            code, out, err = self.run_install(*mode)
            self.assertEqual(code, 3, out + err)
            self.assertEqual(self.states(out), wanted)
            self.assertIn(self.PHRASE, err)
            self.assertEqual(self.t5_world(), before, "ni los ACTUALIZAR se escriben si hay un MODIFICADO")
        backup = os.path.join(self.tmp, "respaldo")
        self.install_ok("-Force", "-BackupDir", backup)
        saved = self.tree(backup)
        self.assertEqual(sorted(saved), sorted([self.t5_path(r) for r in changed] + [self.STATE]))
        self.assertEqual(saved[self.t5_path(rel)], edited)
        for r in changed:
            if r != rel:
                self.assertEqual(saved[self.t5_path(r)], old[r], r)
        self.assertEqual(saved[self.STATE], old_state)
        self.assert_level_installed(files, 1)

    def test_t5_case33_schema1_state_with_intact_destination_at_level_3_is_actualizar(self):
        files = self.make_level_source()
        for rel, data in files.items():
            write(self.target, rel, data)
        self.write_state(files, schema=1)
        self.set_level(3)
        old_state = read(self.target, self.STATE)
        self.assertEqual(json.loads(old_state)["schema"], 1)
        changed = self.t5_changed(files, 5, 3)
        self.assertTrue(changed)
        wanted = {rel: ("ACTUALIZAR" if rel in changed else "IGUAL") for rel in files}
        backup = os.path.join(self.tmp, "respaldo")
        before = self.t5_world()
        code, out, err = self.run_install("-DryRun", "-BackupDir", backup)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out), wanted)
        self.t5_assert_previous_level(out, 5)
        self.assertEqual(self.t5_world(), before)
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(self.states(out), wanted)
        self.assertEqual(json.loads(read(self.target, self.STATE))["schema"], 2)
        self.assert_level_installed(files, 3)
        saved = self.tree(backup)
        self.assertEqual(sorted(saved), sorted([self.t5_path(r) for r in changed] + [self.STATE]))
        for rel in changed:
            self.assertEqual(saved[self.t5_path(rel)], files[rel], rel)
        self.assertEqual(saved[self.STATE], old_state)

    def test_t5_case34_level_change_and_source_change_together_are_actualizar(self):
        files = self.t5_first_install(5)
        new = dict(files)
        new["agents/atlas.md"] = agent_md("atlas", "claude-fable-5-2", before=["version: 2"])
        new["agents/forge.md"] = agent_md("forge", "sonnet", before=["version: 2"])
        new["agents/auditor.md"] = agent_md("auditor", "opus", before=["version: 2"])
        new["rules/agentes.md"] = b"reglas 2\n"
        self.make_level_source(new)
        self.set_level(3)
        old = level_expected(files, 5)
        want = level_expected(new, 3)
        changed = [rel for rel in new if old[rel] != want[rel]]
        for rel in ("agents/atlas.md", "agents/forge.md", "agents/auditor.md", "rules/agentes.md", "agents/scribe.md"):
            self.assertIn(rel, changed)
        backup = os.path.join(self.tmp, "respaldo")
        wanted = {rel: ("ACTUALIZAR" if rel in changed else "IGUAL") for rel in new}
        before = self.t5_world()
        code, out, err = self.run_install("-DryRun", "-BackupDir", backup)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out), wanted)
        self.t5_assert_previous_level(out, 5)
        self.assertEqual(self.t5_world(), before)
        self.assertFalse(os.path.exists(backup))
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(self.states(out), wanted)
        self.t5_assert_previous_level(out, 5)
        self.assert_level_installed(new, 3)
        self.assertIn(b"version: 2", read(self.target, "agents/forge.md"))
        saved = self.tree(backup)
        self.assertEqual(sorted(saved), sorted([self.t5_path(r) for r in changed] + [self.STATE]))
        for rel in changed:
            self.assertEqual(saved[self.t5_path(rel)], old[rel], rel)

    def t5_bad_state(self, kind):
        """Escribe en el destino un estado que el instalador no puede usar (o ninguno)."""
        if kind == "absent":
            return
        if kind == "ilegible":
            data = b"{ esto no es json"
        elif kind == "schema3":
            data = b'{"schema": 3, "algorithm": "sha256", "eol": "lf", "files": []}'
        else:
            state = json.loads(lr.state_for(read(self.src, "install-manifest.json")))
            state["files"][0]["written"] = "no-es-hexadecimal"
            data = (json.dumps(state, indent=2) + "\n").encode("ascii")
        write(self.target, self.STATE, data)

    def test_t5_case35_unreadable_absent_or_unknown_state_is_treated_as_absent(self):
        variants = [("absent", 3), ("absent", 1), ("ilegible", 3), ("ilegible", 1), ("schema3", 3), ("written", 3)]
        for n, (kind, level) in enumerate(variants):
            with self.subTest(state=kind, level=level):
                shutil.rmtree(self.target, ignore_errors=True)
                files = self.make_level_source()
                self.set_level(level)
                # (a) el destino ya esta en el nivel pedido: IGUAL, el estado se reescribe y no se respalda
                for rel, data in level_expected(files, level).items():
                    write(self.target, rel, data)
                self.t5_bad_state(kind)
                backup = os.path.join(self.tmp, "respaldo-a%d" % n)
                out, err = self.install_ok("-BackupDir", backup)
                self.assertEqual(set(self.states(out).values()), {"IGUAL"})
                self.assertIn("escritos=0", out)
                self.assertEqual(self.t5_prev_lines(out), [])
                self.assertEqual("Se trata como ausente" in err, kind != "absent", err)
                self.assertFalse(os.path.exists(backup))
                self.assert_level_installed(files, level)
                shutil.rmtree(self.target)
                # (b) el destino tiene los bytes del repositorio: lo que difiere del esperado es MODIFICADO,
                # nunca ACTUALIZAR (sin estado valido no se reconoce ningun archivo como propio)
                self.set_level(level)
                for rel, data in level_expected(files, 5).items():
                    write(self.target, rel, data)
                self.t5_bad_state(kind)
                changed = self.t5_changed(files, 5, level)
                self.assertTrue(changed)
                wanted = {rel: ("MODIFICADO" if rel in changed else "IGUAL") for rel in files}
                before = self.t5_world()
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 3, out + err)
                    self.assertEqual(self.states(out), wanted)
                    self.assertNotIn("ACTUALIZAR ", out)
                    self.assertIn(self.PHRASE, err)
                    self.assertEqual(self.t5_prev_lines(out), [])
                    self.assertEqual(self.t5_world(), before)
                backup = os.path.join(self.tmp, "respaldo-b%d" % n)
                self.install_ok("-Force", "-BackupDir", backup)
                saved = self.tree(backup)
                self.assertEqual(sorted(saved), sorted(self.t5_path(r) for r in changed), "un estado invalido no se respalda")
                for rel in changed:
                    self.assertEqual(saved[self.t5_path(rel)], files[rel], rel)
                self.assert_level_installed(files, level)
                shutil.rmtree(self.target)

    def test_t5_state_of_another_level_with_files_already_at_the_new_level_is_igual(self):
        files = self.make_level_source()
        for rel, data in level_expected(files, 3).items():
            write(self.target, rel, data)
        old_state = lr.state_for(read(self.src, "install-manifest.json"), None, 5)
        write(self.target, self.STATE, old_state)
        self.set_level(3)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertIn("escritos=0", out)
        self.t5_assert_previous_level(out, 5)
        self.assert_level_installed(files, 3)
        self.assertEqual(self.tree(backup), {self.STATE: old_state})

    def test_t5_orphan_is_reported_and_kept_on_a_level_change(self):
        files = self.make_level_source()
        old = dict(files)
        old["agents/viejo.md"] = b"de una version anterior\n"
        for rel, data in old.items():
            write(self.target, rel, data)
        self.write_state(old)
        self.set_level(3)
        changed = self.t5_changed(files, 5, 3)
        code, out, err = self.run_install("-DryRun", "-BackupDir", os.path.join(self.tmp, "respaldo-dry"))
        self.assertEqual(code, 0, out + err)
        out, err = self.install_ok("-BackupDir", os.path.join(self.tmp, "respaldo"))
        wanted = {rel: ("ACTUALIZAR" if rel in changed else "IGUAL") for rel in files}
        wanted["agents/viejo.md"] = "HUERFANO"
        self.assertEqual(self.states(out), wanted)
        self.t5_assert_previous_level(out, 5)
        self.assertEqual(read(self.target, "agents/viejo.md"), b"de una version anterior\n")

    def test_t5_case36_hook_goes_first_in_a_level_change_that_also_updates_the_hook(self):
        files = self.t5_first_install(5)
        new = dict(files)
        new["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_level_source(new)
        self.set_level(3)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        copied = [l[len("Copiado: "):] for l in out.splitlines() if l.startswith("Copiado: ")]
        saved = [l[len("Respaldado: "):] for l in out.splitlines() if l.startswith("Respaldado: ")]
        self.assertEqual(copied[0], "hooks/agent_guard.py", out)
        self.assertEqual(saved[0], "hooks/agent_guard.py", out)
        self.assertIn("agents/atlas.md", copied[1:])
        self.assertEqual(sorted(copied), sorted(r for r in new if level_expected(files, 5)[r] != level_expected(new, 3)[r]))
        self.assert_level_installed(new, 3)

    def test_t5_case37_destination_in_crlf_with_the_content_of_the_level_is_igual_and_not_rewritten(self):
        files = self.t5_first_install(3)
        for rel, data in level_expected(files, 3).items():
            write(self.target, rel, data.replace(b"\n", b"\r\n"))
        snap = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        out, err = self.install_ok()
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertIn("escritos=0", out)
        self.assertEqual(snapshot(self.target), snap)
        self.assertEqual(sorted(os.listdir(self.tmp)), listing)
        # con un estado que dice otro nivel: los archivos que ya coinciden en CRLF siguen siendo IGUAL
        write(self.target, self.STATE, lr.state_for(read(self.src, "install-manifest.json"), None, 5))
        for rel in ("agents/atlas.md", "agents/scribe.md"):
            write(self.target, rel, level_expected(files, 3)[rel].replace(b"\n", b"\r\n"))
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertEqual(read(self.target, "agents/atlas.md"), level_expected(files, 3)["agents/atlas.md"].replace(b"\n", b"\r\n"))
        self.assert_state(3, level_hashes(files, 3))
        self.assertEqual(sorted(self.tree(backup)), [self.STATE])


    # --- Cierre de la Fase 3 (sentinel): huecos de borde no cubiertos por los casos 1 a 40 ---

    def test_g1_removing_the_config_after_level_3_returns_to_the_repository_bytes(self):
        # Nivel por defecto (sin archivo) sobre un estado de nivel 3: es el nivel 5, no «el mismo nivel».
        files = self.t5_first_install(3)
        os.remove(os.path.join(self.target, self.CONFIG))
        changed = self.t5_changed(files, 3, 5)
        self.assertTrue(changed)
        wanted = {rel: ("ACTUALIZAR" if rel in changed else "IGUAL") for rel in files}
        code, out, err = self.run_install("-DryRun", "-BackupDir", os.path.join(self.tmp, "respaldo-dry"))
        self.assertEqual(code, 0, out + err)
        self.assertIn("Nivel: 5 (por defecto", out)
        self.t5_assert_previous_level(out, 3)
        self.assertEqual(self.states(out), wanted)
        out, err = self.install_ok("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(self.states(out), wanted)
        self.assert_level_installed(files, 5)
        for rel, data in files.items():
            self.assertEqual(read(self.target, rel), data, rel)

    def test_g2_level_3_with_a_readonly_destination_exit1_in_both_modes_writes_nothing(self):
        files = self.t5_first_install(5)
        self.set_level(3)
        self.make_readonly("agents/atlas.md")
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*(mode + ["-BackupDir", backup]))
                self.assertEqual(code, 1, out + err)
                self.assertIn("solo lectura", err)
                self.assertIn("atlas.md", err)
                self.assertEqual(snapshot(self.target), before)
                self.assertFalse(os.path.exists(backup))
        self.assertEqual(read(self.target, "agents/atlas.md"), files["agents/atlas.md"])

    def test_g3_a_manifest_without_the_fixed_agents_installs_at_level_3(self):
        files = {rel: data for rel, data in LEVEL_SAMPLE.items()
                 if rel not in ("agents/auditor.md", "agents/shield.md", "agents/debugger.md")}
        self.make_level_source(files)
        self.set_level(3)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("Ajuste:")]), 6)
        self.install_ok()
        self.assert_level_installed(files, 3)
        for name in ("auditor", "shield", "debugger"):
            self.assertFalse(os.path.exists(os.path.join(self.target, "agents", name + ".md")))

    def test_g4_reinstall_after_exit4_at_level_3_needs_force_for_the_corrupted_file_only(self):
        files = self.make_level_source()
        self.set_level(3)
        atlas = os.path.join(self.target, "agents", "atlas.md").replace("'", "''")
        self.patch_script("# Paso 8:", "[System.IO.File]::AppendAllText('%s', 'x')" % atlas)
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertFalse(os.path.exists(os.path.join(self.target, self.STATE)))
        shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))
        # sin estado, lo que difiere de lo esperado es MODIFICADO (regla vigente): solo atlas
        code, out, err = self.run_install()
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out), {r: ("MODIFICADO" if r == "agents/atlas.md" else "IGUAL") for r in files})
        backup = os.path.join(self.tmp, "respaldo")
        self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(sorted(self.tree(backup)), [os.path.join("agents", "atlas.md")])
        self.assert_level_installed(files, 3)

    def test_g5_environment_warnings_and_exit_3_come_together_without_the_value(self):
        files = self.t5_first_install(3)
        edited = read(self.target, "agents/atlas.md").replace(b"\nmodel: ", b"\nmodel: manual-", 1)
        write(self.target, "agents/atlas.md", edited)
        secret = "SECRETO-98765"
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode, env_extra={ENV_FORCE: secret, ENV_EFFORT: secret})
                self.assertEqual(code, 3, out + err)
                self.assertEqual(len(self.env_warnings(err)), 2, err)
                self.assertIn(self.PHRASE, err)
                self.assertNotIn(secret, out + err)
                self.assertEqual(read(self.target, "agents/atlas.md"), edited)

    def test_g6_dryrun_with_every_state_at_once_at_level_3(self):
        files = self.make_level_source()
        old = dict(files)
        old["agents/viejo.md"] = b"de una version anterior\n"
        for rel, data in old.items():
            write(self.target, rel, data)
        self.write_state(old)
        os.remove(os.path.join(self.target, "agents", "scribe.md"))
        write(self.target, "agents/forge.md", b"editado a mano\n")
        self.set_level(3)
        changed = self.t5_changed(files, 5, 3)
        self.assertIn("agents/atlas.md", changed)
        self.assertIn("agents/scribe.md", changed)
        self.assertNotIn("agents/forge.md", changed)
        wanted = {rel: ("ACTUALIZAR" if rel in changed else "IGUAL") for rel in files}
        wanted["agents/scribe.md"] = "NUEVO"
        wanted["agents/forge.md"] = "MODIFICADO"
        wanted["agents/viejo.md"] = "HUERFANO"
        counts = {k: list(wanted.values()).count(k) for k in ("NUEVO", "IGUAL", "ACTUALIZAR", "MODIFICADO", "HUERFANO")}
        before = self.t5_world()
        code, out, err = self.run_install("-DryRun", "-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out), wanted)
        self.assertIn("Resumen: NUEVO=%(NUEVO)d IGUAL=%(IGUAL)d ACTUALIZAR=%(ACTUALIZAR)d MODIFICADO=%(MODIFICADO)d "
                      "HUERFANO=%(HUERFANO)d" % counts, out)
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("Ajuste:")]), 6)
        self.t5_assert_previous_level(out, 5)
        self.assertEqual(self.t5_world(), before)

    # --- Cierre de la Fase 3: salida acotada, hueco envolvente y __type en el estado ---

    def test_t6c_hostile_state_with_huge_key_or_path_gives_bounded_stderr(self):
        # Entrada no confiable: una clave o una ruta de cientos de miles de caracteres no debe volcarse entera a stderr.
        self.make_source()
        for rel, data in SAMPLE.items():
            write(self.target, rel, data)

        def base():
            return json.loads(lr.state_for(read(self.src, "install-manifest.json")))

        def key():
            s = base()
            s["files"][0]["k" * 450000] = 1
            return s

        def path_not_allowed():
            s = base()
            s["files"][0]["path"] = "agents/" + "A" * 450000 + ".md"
            return s

        def path_with_dots():
            s = base()
            s["files"][0]["path"] = "x" * 450000 + ".."
            return s

        for name, build in (("clave desconocida en una entrada", key), ("ruta fuera de la lista", path_not_allowed),
                            ("ruta con ..", path_with_dots)):
            with self.subTest(case=name):
                raw = self.dump_state(build())
                self.assertGreater(len(raw), 400000)
                self.assertLess(len(raw), 1048576)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 0, out + err)
                self.assertIn("Se trata como ausente", err)
                self.assertLess(len(err.encode("utf-8")), 1000, len(err))
        # el mismo tope en el manifiesto del origen
        for name, bad in (("ruta fuera de la lista", "agents/" + "A" * 450000 + ".md"), ("ruta con ..", "x" * 450000 + "..")):
            with self.subTest(case="manifiesto: " + name):
                m = json.loads(read(self.src, "install-manifest.json"))
                m["files"][0]["path"] = bad
                write(self.src, "install-manifest.json", json.dumps(m).encode("ascii"))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertLess(len(err.encode("utf-8")), 1000, len(err))

    def test_t6c_valid_hooks_block_after_model_is_still_rendered(self):
        hooks = ["hooks:", "  PreToolUse:", '    - matcher: "Write"', "      hooks: [a, b]"]
        for level in (3, 1):
            with self.subTest(level=level):
                files = dict(LEVEL_SAMPLE)
                files["agents/atlas.md"] = agent_md("atlas", "claude-fable-5-2", after=hooks)
                self.make_level_source(files)
                self.set_level(level)
                self.install_ok()
                self.assert_level_installed(files, level)
                got = read(self.target, "agents/atlas.md")
                self.assertIn(("\n".join(hooks) + "\n").encode("ascii"), got)
                shutil.rmtree(self.target)

    def test_t6c_type_key_in_a_state_makes_it_absent_never_actualizar(self):
        # ConvertFrom-Json de 5.1 descarta __type antes de la lista cerrada de claves: se rechaza en el texto (como en la
        # configuracion). Control: el mismo estado sin __type da ACTUALIZAR; con __type, MODIFICADO (estado ausente).
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        old = dict(SAMPLE)
        old["agents/alfa.md"] = b"alfa vieja\n"
        for rel, data in old.items():
            write(self.target, rel, data)
        self.write_state(old)
        clean = read(self.target, self.STATE).decode("ascii")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(self.states(out)["agents/alfa.md"], "ACTUALIZAR", out + err)
        variants = [
            ("raiz", clean.replace("{\n", '{\n  "__type": "x",\n', 1)),
            ("raiz escrito con escapes", clean.replace("{\n", '{\n  "\\u005f\\u005ftype": "x",\n', 1)),
            ("raiz con una letra escapada", clean.replace("{\n", '{\n  "__t\\u0079pe": "x",\n', 1)),
            ("en una entrada", clean.replace('"path": "agents/alfa.md",', '"__type": "x", "path": "agents/alfa.md",', 1)),
        ]
        schema1 = json.loads(read(self.src, "install-manifest.json"))
        variants.append(("esquema 1", json.dumps(dict(schema1, __type="x"), indent=2)))
        for name, text in variants:
            with self.subTest(case=name):
                self.assertNotEqual(text, clean)
                write(self.target, self.STATE, text.encode("ascii"))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 3, out + err)
                self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
                self.assertNotIn("ACTUALIZAR ", out)
                self.assertIn("Se trata como ausente", err)
                self.assertIn("__type", err)

    # --- Fase 4, T2: clave aliases de synclayer-config.json (lectura, validacion V1 a V8 y lineas Alias:; casos 9 a
    # 19 del plan). T5 retiro la guarda temporal de T2: una tabla efectiva valida ya se aplica de punta a punta. ---

    CONFIG_ERR = "error: synclayer-config.json no es valido: "
    ALIAS_NINE = {"atlas": "mapa", "auditor": "revisor", "debugger": "cazador", "forge": "dev", "oracle": "guia",
                  "scout": "explorador", "scribe": "redactor", "sentinel": "amigo-qa", "shield": "guardia"}

    def alias_config(self, aliases, level=None):
        obj = {}
        if level is not None:
            obj["level"] = level
        obj["aliases"] = aliases
        return json.dumps(obj).encode("ascii")

    def assert_quiet_failure(self, code, out, err, before, listing):
        """Nada escrito ni respaldado: ni el destino ni la carpeta temporal cambian."""
        self.assertEqual(code, 1, out + err)
        self.assertNotIn("Copiado", out)
        self.assertEqual(snapshot(self.target), before)
        self.assertEqual(sorted(os.listdir(self.tmp)), listing)
        self.assertTrue(err.isascii(), repr(err))
        self.assertFalse(any(ord(c) < 0x20 and c not in "\r\n" for c in err + out), repr(err + out))

    def alias_transform_error(self, files, aliases):
        """La referencia independiente (aliases_ref) aplicada a los archivos del manifiesto: el primer archivo cuya
        transformacion falla (ValueError) o None."""
        for rel in sorted(files):
            m = re.match(r"^agents/([a-z0-9_-]+)\.md$", rel)
            try:
                if m and m.group(1) in ar.roles():
                    ar.transform_agent(files[rel], m.group(1), aliases)
                elif rel in ("rules/agentes.md", "docs/agentes.md"):
                    ar.transform_doc(files[rel], aliases)
            except ValueError:
                return rel
        return None

    def assert_alias_verdict(self, aliases, files=None, modes=(["-DryRun"],), raw=None):
        """El veredicto del instalador es el de la referencia independiente (aliases_ref): el mismo motivo si la tabla
        es invalida; si es valida y la tabla efectiva no esta vacia, exit 0 (o exit 1 con el error de transformacion
        si la referencia tambien falla); si esta vacia, exit 0 sin linea Alias:. Nunca se escribe nada en los casos
        de error."""
        files = SAMPLE if files is None else files
        self.make_source(files)
        self.write_config(self.alias_config(aliases) if raw is None else raw)
        expected = ar.validate_table(aliases, manifest_paths=sorted(files))
        effective = isinstance(aliases, dict) and bool(ar.effective(aliases))
        failing = self.alias_transform_error(files, aliases) if expected is None and effective else None
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        for mode in modes:
            with self.subTest(aliases=repr(aliases)[:80], mode=mode):
                code, out, err = self.run_install(*mode)
                if expected is None and failing is None:
                    self.assertEqual(code, 0, out + err)
                    self.assertEqual("Alias:" in out, effective)
                    if "-DryRun" in mode:
                        self.assertEqual(snapshot(self.target), before)
                    else:
                        shutil.rmtree(self.target)
                        self.write_config(self.alias_config(aliases) if raw is None else raw)
                        before = snapshot(self.target)
                    continue
                self.assert_quiet_failure(code, out, err, before, listing)
                if expected is None:
                    self.assertTrue(err.startswith("error: no se pueden aplicar los alias a " + failing + ": "), err)
                    self.assertTrue(err.strip().endswith(". No se escribio nada."), err)
                else:
                    self.assertEqual(err.strip(), self.CONFIG_ERR + expected + ". No se escribio nada.")

    def test_t2_case9_no_aliases_or_empty_or_own_role_is_identical_to_today(self):
        # Casos 9 y 15: sin `aliases`, con `{}` y con cada alias igual a su propio rol (tabla efectiva vacia)
        # dan stdout, stderr, destino y estado identicos byte a byte; ninguna linea Alias:.
        own = json.dumps({"level": 5, "aliases": {r: r for r in ar.roles()}}).encode("ascii")
        for mode in (["-DryRun"], []):
            results = {}
            for name, cfg in (("base", b'{"level": 5}'), ("vacio", b'{"level": 5, "aliases": {}}'),
                              ("propio", b'{"level": 5, "aliases": {"forge": "forge"}}'), ("nueve propios", own)):
                with self.subTest(case=name, mode=mode):
                    self.make_source()
                    self.write_config(cfg)
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 0, out + err)
                    self.assertNotIn("Alias:", out)
                    tree = self.tree(self.target)
                    tree.pop(self.CONFIG)
                    results[name] = (code, out, err, tree)
                    shutil.rmtree(self.target)
            for name, got in results.items():
                with self.subTest(compare=name, mode=mode):
                    self.assertEqual(got, results["base"])

    def test_t2_case9_without_config_equals_empty_aliases_except_the_level_origin(self):
        self.make_source()
        code, out0, err0 = self.run_install("-DryRun")
        self.assertEqual(code, 0, out0 + err0)
        self.write_config(b'{"aliases": {}}')
        code, out1, err1 = self.run_install("-DryRun")
        self.assertEqual(code, 0, out1 + err1)
        self.assertEqual(err0, err1)
        self.assertEqual(out0.replace("(por defecto; no hay synclayer-config.json)", "(synclayer-config.json)"), out1)
        self.assertNotIn("Alias:", out1)

    def test_t2_case10_aliases_of_an_invalid_type_exit1_in_both_modes(self):
        variants = [("null", b"null"), ("lista vacia", b"[]"), ("lista de un objeto", b'[{"forge": "dev"}]'),
                    ("cadena", b'"dev"'), ("numero", b"3"), ("true", b"true"), ("false", b"false"),
                    ("lista de listas", b"[[]]")]
        for name, value in variants:
            with self.subTest(case=name):
                self.assert_config_rejected(b'{"aliases": ' + value + b"}", "aliases debe ser un objeto")
                shutil.rmtree(self.target)

    def test_t2_case11_unknown_alias_key_exit1_and_the_key_is_escaped(self):
        for key in ("qa", "Forge", "FORGE", "forge ", "agents", "forg"):
            with self.subTest(key=key):
                self.assert_config_rejected(json.dumps({"aliases": {key: "dev"}}).encode("ascii"),
                                            "rol desconocido en aliases: " + key)
                shutil.rmtree(self.target)
        # una clave vacia la rechaza ConvertFrom-Json de 5.1 antes que el instalador
        self.assert_config_rejected(b'{"aliases": {"": "dev"}}', "JSON invalido")
        shutil.rmtree(self.target)
        self.assert_config_rejected(json.dumps({"aliases": {"a\u0000b\u001b[31mé": "dev"}}).encode("ascii"),
                                    "rol desconocido en aliases: a\\u0000b\\u001b[31m\\u00e9")
        shutil.rmtree(self.target)
        self.assert_config_rejected(json.dumps({"aliases": {"k" * 60000: "dev"}}).encode("ascii"),
                                    "rol desconocido en aliases: " + "k" * 40 + "...")

    def test_t2_case12_invalid_values_name_the_role_and_match_the_reference(self):
        bad = ["", "Dev", "DEV", "a b", "a:b", "a.b", "a/b", "a\\b", "-dev", "1dev", "123", "1e3", "0x1f", "_dev",
               "a" * 65, "dév", "dev\n", "dev\nhooks: x", "dev#x", "'dev'", "dev\u0000", "\u00ad", "dev ",
               "de\u0301v"]
        for value in bad:
            self.assertIsNotNone(ar.validate_table({"forge": value}), repr(value))
            self.assert_alias_verdict({"forge": value})
        for value in (None, 3, 3.5, True, False, ["dev"], {"a": "b"}, [], {}):
            self.assertIn("debe ser texto", ar.validate_table({"forge": value}))
            self.assert_alias_verdict({"forge": value})

    def test_t2_case12_both_modes_for_a_representative_set(self):
        for value in ("Dev", None, "a" * 65, ["dev"]):
            self.assert_alias_verdict({"scribe": value}, modes=(["-DryRun"], []))

    def test_t2_case13_reserved_names_yaml_words_and_windows_names(self):
        words = (ar.reserved() + ["Explore", "PLAN", "General-Purpose"] + ar.yaml_words() +
                 ["con", "prn", "aux", "nul", "com0", "com1", "com9", "lpt0", "lpt1", "lpt9"])
        self.assertIn("fork", ar.reserved())
        self.assertIn("output-style-setup", ar.reserved())
        for value in words:
            self.assertIsNotNone(ar.validate_table({"forge": value}), value)
            self.assert_alias_verdict({"forge": value})
        # El motivo exacto de cada familia (V1, V2, V3, V4).
        for value, motivo in (("true", "es una palabra reservada de YAML"), ("null", "es una palabra reservada de YAML"),
                              ("con", "es un nombre reservado de Windows"), ("nul", "es un nombre reservado de Windows"),
                              ("com1", "es un nombre reservado de Windows"),
                              ("fork", "es el nombre de un agente integrado de Claude Code"),
                              ("output-style-setup", "es el nombre de un agente integrado de Claude Code"),
                              ("explore", "es el nombre de un agente integrado de Claude Code"),
                              ("Explore", "solo admite a-z, 0-9, _ y -"), ("PLAN", "solo admite a-z, 0-9, _ y -")):
            with self.subTest(value=value):
                self.assert_config_rejected(self.alias_config({"forge": value}),
                                            "el alias de forge " + motivo, modes=(["-DryRun"],))
                shutil.rmtree(self.target)

    def test_t2_case14_table_rules_v5_v6_v7_v8_and_cycles(self):
        two_cycle = {"forge": "scribe", "scribe": "forge"}
        three_cycle = {"forge": "scribe", "scribe": "sentinel", "sentinel": "forge"}
        tables = [
            {"forge": "scribe"}, two_cycle, three_cycle, {"atlas": "shield"},
            {"forge": "dev", "scribe": "dev"}, {"forge": "dev", "oracle": "x", "scribe": "dev"},
            {"oracle": "dev-sentinel"}, {"oracle": "forge-2"}, {"oracle": "sentinel-dev"}, {"oracle": "a-forge-b"},
            {"forge": "forge-2"}, {"forge": "x-scribe"},
            {"forge": "forge", "scribe": "forge"},
        ]
        for table in tables:
            self.assertIsNotNone(ar.validate_table(table), table)
            self.assert_alias_verdict(table)
        for table, motivo in ((two_cycle, "el alias de forge es el nombre de otro agente de SyncLayer"),
                              (three_cycle, "el alias de forge es el nombre de otro agente de SyncLayer"),
                              ({"forge": "dev", "scribe": "dev"}, "forge y scribe tienen el mismo alias"),
                              ({"oracle": "forge-2"}, "el alias de oracle contiene el nombre de un agente de SyncLayer")):
            with self.subTest(table=table):
                self.assert_config_rejected(self.alias_config(table), motivo, modes=(["-DryRun"], []))
                shutil.rmtree(self.target)
        # V8: un manifiesto con un agente que ya ocupa la ruta del alias.
        files = dict(SAMPLE)
        files["agents/forge.md"] = b"agente forge\n"
        files["agents/dev.md"] = b"agente dev\n"
        self.assertIn("coincide con otro archivo del manifiesto", ar.validate_table({"forge": "dev"}, sorted(files)))
        self.assert_alias_verdict({"forge": "dev"}, files=files)
        self.assert_alias_verdict({"forge": "dev2"}, files=files)
        self.assert_alias_verdict({"forge": "forge"}, files=files)

    def test_t2_v8_covers_roles_whose_file_is_not_in_the_manifest(self):
        # E2: SAMPLE trae agents/alfa.md y no trae agents/forge.md: el alias alfa nombra el archivo de otro agente.
        self.assertIn("coincide con otro archivo del manifiesto", ar.validate_table({"forge": "alfa"}, sorted(SAMPLE)))
        self.assert_alias_verdict({"forge": "alfa"}, modes=(["-DryRun"], []))
        self.assert_alias_verdict({"forge": "alfa", "scribe": "redactor"})
        self.assert_alias_verdict({"forge": "gamma"})  # no coincide con ninguna ruta: pasa la validacion y se instala
        files = dict(SAMPLE)
        files["agents/forge.md"] = b"agente forge\n"
        self.assert_alias_verdict({"forge": "alfa"}, files=files)
        self.assert_alias_verdict({"forge": "gamma"}, files=files)

    def test_t2_reserved_output_style_setup_is_v4_in_both_modes(self):
        self.assertIn("agente integrado", ar.validate_table({"forge": "output-style-setup"}))
        self.assert_alias_verdict({"forge": "output-style-setup"}, modes=(["-DryRun"], []))

    def test_t2_second_read_of_the_config_is_detected_by_behaviour(self):
        # Lectura unica: tras la lectura se reescribe la configuracion; el resultado (exit y lineas Alias:) debe
        # reflejar la PRIMERA lectura. Una segunda lectura en cualquier punto posterior lo cambiaria.
        self.make_source()
        path = self.write_config(self.alias_config({"forge": "dev"}))
        for later, why in (('{"aliases": {"forge": "Dev"}}', "tabla invalida"), ('{"aliases": {}}', "tabla vacia"),
                           ('{"aliases": {"scribe": "redactor"}}', "otra tabla")):
            with self.subTest(later=why):
                self.make_source()
                shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))
                self.patch_script("$level = [int](Read-LevelConfig $configPath)",
                                  "[System.IO.File]::WriteAllText('%s', '%s')" % (path.replace("'", "''"), later))
                self.write_config(self.alias_config({"forge": "dev"}))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 0, out + err)
                self.assertEqual([l for l in out.splitlines() if l.startswith("Alias:")],
                                 ["Alias: forge -> dev (agents/dev.md)"])
                self.assertEqual(err.strip(), "")

    def test_t2_valid_tables_pass_v1_to_v8_and_install(self):
        # Pasan V1 a V8 (y de ahi se aplican): las dos mitades del veredicto de cada regla.
        valid = [{"forge": "dev"}, {"sentinel": "amigo-qa", "forge": "dev"}, dict(self.ALIAS_NINE),
                 {"forge": "a" * 64}, {"forge": "forge_2"}, {"forge": "forgery"}, {"forge": "sentinels"},
                 {"forge": "com10"}, {"forge": "lpt10"}, {"forge": "yes-no"}, {"forge": "x1"}, {"forge": "y2"},
                 {"forge": "explorer"}, {"forge": "forge", "scribe": "dev"}, {"forge": "conx"}, {"forge": "nulo"}]
        for table in valid:
            self.assertIsNone(ar.validate_table(table, manifest_paths=sorted(SAMPLE)), table)
            self.assert_alias_verdict(table)
        # Tabla efectiva vacia: exit 0.
        for table in ({}, {"forge": "forge"}, {r: r for r in ar.roles()}):
            self.assert_alias_verdict(table)

    def test_t2_case17_unknown_root_keys_still_exit1_with_aliases_present(self):
        for data, motivo in ((b'{"aliases": {}, "agents": {}}', "clave desconocida: agents"),
                             (b'{"Aliases": {}}', "clave desconocida: Aliases"),
                             (b'{"level": 3, "aliases": {}, "names": {}}', "clave desconocida: names"),
                             (b'{"alias": {}}', "clave desconocida: alias")):
            with self.subTest(data=data):
                self.assert_config_rejected(data, motivo)
                shutil.rmtree(self.target)

    def test_t2_level_and_empty_aliases_together_keep_working(self):
        self.make_source()
        self.write_config(b'{"level": 3, "aliases": {}}')
        out, err = self.install_ok("-DryRun")
        self.assertIn("Nivel: 3 (synclayer-config.json)", out.splitlines())
        self.assertNotIn("Alias:", out)

    def test_t2_case18_level_and_alias_lines_come_in_order_before_the_plan(self):
        files = dict(SAMPLE)
        files["agents/sentinel.md"] = agent_md("sentinel", "sonnet")
        self.make_source(files)
        self.write_config(self.alias_config({"sentinel": "amigo-qa", "forge": "dev"}, level=3))
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 0, out + err)
                lines = out.splitlines()
                self.assertTrue(lines[0].startswith("Destino: "), lines)
                self.assertEqual(lines[1:4], ["Nivel: 3 (synclayer-config.json)",
                                              "Alias: forge -> dev (agents/dev.md)",
                                              "Alias: sentinel -> amigo-qa (agents/amigo-qa.md)"])
                self.assertTrue(lines[4].startswith(("Respaldo: ", "Modo: ")) or LINE.match(lines[4]), lines)
                self.assertNotIn("error", err)
                if "-DryRun" in mode:
                    self.assertEqual(os.listdir(self.target), [self.CONFIG])
        # `Alias:` no se confunde con una fila del plan (la expresion LINE de las pruebas)
        self.assertIsNone(LINE.match("Alias: forge -> dev (agents/dev.md)"))

    def test_t2_alias_lines_follow_the_previous_level_line(self):
        self.make_source()
        self.install_ok()
        self.write_config(self.alias_config({"scribe": "redactor"}, level=2))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        lines = out.splitlines()
        self.assertEqual(lines[1:4], ["Nivel: 2 (synclayer-config.json)", "Nivel anterior: 5",
                                      "Alias: scribe -> redactor (agents/redactor.md)"])

    def test_t2_case19_invalid_table_writes_and_backs_up_nothing_with_a_valid_state(self):
        self.make_source()
        self.install_ok()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        self.write_config(self.alias_config({"forge": "scribe"}))
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assert_quiet_failure(code, out, err, before, listing)
                self.assertIn(self.CONFIG_ERR + "el alias de forge es el nombre de otro agente de SyncLayer", err)
                self.assertNotIn("Respaldo", out)
                self.assertFalse([n for n in os.listdir(self.tmp) if "backup" in n])

    def test_t2_invalid_alias_values_never_leak_into_stdout_or_stderr(self):
        secret = "SECRETO-ALIAS-123"
        values = [secret, secret.lower() + "\u001b[31m", "dev\u0000" + secret, secret + "\n" + secret,
                  secret + "!", "x" * 60000 + secret, "\u202e" + secret, "'" + secret + "'", secret + "-" * 70]
        for value in values:
            with self.subTest(value=value[:25]):
                self.make_source()
                self.write_config(self.alias_config({"sentinel": value}))
                for mode in (["-DryRun"], []) if value == secret else (["-DryRun"],):
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 1, out + err)
                    self.assertIn(self.CONFIG_ERR + "el alias de sentinel ", err)
                    for needle in (secret, secret.lower(), "SECRETO", "secreto", "x" * 40):
                        self.assertNotIn(needle, out + err)
                    self.assertTrue(err.isascii(), repr(err))
                    self.assertFalse(any(ord(c) < 0x20 and c not in "\r\n" for c in err + out), repr(err))
                    self.assertLess(len(err), 400)
                shutil.rmtree(self.target)
        # un valor inocente tampoco aparece en la salida de error de una tabla invalida por otra causa
        self.make_source()
        self.write_config(self.alias_config({"forge": "inocente", "scribe": "Mal"}))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertNotIn("inocente", out + err)
        self.assertNotIn("Mal", err.replace("el alias de scribe", ""))

    def test_t2_case16_type_key_inside_aliases_is_rejected(self):
        for data in (b'{"aliases": {"forge": "x__type"}}', b'{"aliases": {"__type": "x"}}',
                     b'{"aliases": {"forge": "dev", "__type": "System.String"}}',
                     b'{"aliases": {"forge": "x\\u005f\\u005ftype"}}', b'{"aliases": {"__t\\u0079pe": "x"}}'):
            with self.subTest(data=data):
                self.assert_config_rejected(data, "clave desconocida: __type")
                shutil.rmtree(self.target)

    def test_t2_case16_repeated_keys_in_windows_powershell_5_1_last_one_wins(self):
        # Comportamiento medido de ConvertFrom-Json de 5.1 (como con level, caso 17 de la Fase 3): sin error;
        # la ultima aparicion gana, tambien dentro de aliases y para la propia clave aliases.
        self.make_source()
        for data, expect in ((b'{"aliases": {"forge": "dev", "forge": "otro"}}', "Alias: forge -> otro (agents/otro.md)"),
                             (b'{"aliases": {"forge": "otro", "forge": "dev"}}', "Alias: forge -> dev (agents/dev.md)"),
                             (b'{"aliases": {"forge": "dev"}, "aliases": {"scribe": "redactor"}}',
                              "Alias: scribe -> redactor (agents/redactor.md)")):
            with self.subTest(data=data):
                self.write_config(data)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 0, out + err)
                self.assertEqual([l for l in out.splitlines() if l.startswith("Alias:")], [expect])
                self.assertEqual(err.strip(), "")
        self.write_config(b'{"aliases": {"forge": "dev"}, "aliases": {}}')
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("Alias:", out)
        # una clave repetida con el ultimo valor valido (y el primero invalido) gana el ultimo
        self.write_config(b'{"aliases": {"forge": "Dev", "forge": "dev"}}')
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([l for l in out.splitlines() if l.startswith("Alias:")], ["Alias: forge -> dev (agents/dev.md)"])

    def test_t2_config_size_limit_with_aliases(self):
        head = b'{"aliases": {}}'
        limit = 65536
        self.make_source()
        self.write_config(head + b" " * (limit - len(head)))
        self.assertEqual(os.path.getsize(os.path.join(self.target, self.CONFIG)), limit)
        out, err = self.install_ok("-DryRun")
        self.assertIn("Nivel: 5 (synclayer-config.json)", out)
        shutil.rmtree(self.target)
        self.assert_config_rejected(head + b" " * (limit + 1 - len(head)), "supera 65536 bytes")
        shutil.rmtree(self.target)
        # una tabla valida de tope exacto se lee y se aplica, no choca con el limite de tamano
        full = self.alias_config({"forge": "dev"})
        self.write_config(full + b" " * (limit - len(full)))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Alias: forge -> dev (agents/dev.md)", out.splitlines())

    def test_t2_config_is_never_opened_for_writing_with_aliases(self):
        # La configuracion no se escribe, respalda ni lista ni con una tabla valida (se instala sin tocarla) ni invalida.
        self.make_source()
        for table in ({"forge": "dev"}, {"forge": "Dev"}, {}):
            with self.subTest(table=table):
                path = self.write_config(self.alias_config(table))
                old = os.stat(path).st_mtime_ns - 5_000_000_000
                os.utime(path, ns=(old, old))
                before = snapshot(self.target)[self.CONFIG]
                for mode in (["-DryRun"], []):
                    self.run_install(*mode)
                    self.assertEqual(snapshot(self.target)[self.CONFIG], before)
                shutil.rmtree(self.target)

    # --- Fase 4, T3: estado con esquema 3 (lectura, prevByDest y huerfanos generalizados) ---
    # Estas pruebas (escritas antes de T5) usan estados de esquema 3 escritos a mano (write_state con dests) y sin alias
    # en la configuracion: el destino actual de cada rol es su ruta. Con alias, el instalador escribe el esquema 3 (T5).

    F4_OLD_ALFA = b"alfa vieja\n"
    F4_NEW_ALFA = b"alfa nueva\n"

    def f4_old(self):
        old = dict(SAMPLE)
        old["agents/alfa.md"] = self.F4_OLD_ALFA
        return old

    def f4_target(self, files):
        """Destino limpio con esos archivos en disco."""
        shutil.rmtree(self.target, ignore_errors=True)
        for rel, data in files.items():
            write(self.target, rel, data)

    def f4_state3(self, files=None, dests=None, written=None, level=5):
        """Escribe un estado esquema 3 valido (alfa vieja por defecto) y lo devuelve como dict."""
        self.write_state(files or self.f4_old(), schema=3, written=written, level=level, dests=dests)
        return json.loads(read(self.target, self.STATE))

    def f4_entry(self, data, rel="agents/alfa.md"):
        return next(f for f in data["files"] if f["path"] == rel)

    def f4_tree(self, base):
        """{ruta relativa: bytes} de los archivos bajo base."""
        found = {}
        for dirpath, _dirs, names in os.walk(base):
            for name in names:
                full = os.path.join(dirpath, name)
                with open(full, "rb") as f:
                    found[os.path.relpath(full, base).replace(os.sep, "/")] = f.read()
        return found

    def test_f4t3_case20_schema3_state_without_aliases_old_dest_is_orphan_and_state_goes_back_to_schema2(self):
        # Caso 20: estado esquema 3 (alfa estuvo en agents/viejo-alfa.md), sin alias en la configuracion: el rol sale
        # IGUAL o NUEVO, la ruta dest vieja HUERFANO (informada, intacta), y el estado se reescribe en esquema 2.
        self.make_source()
        for present, expected in ((True, "IGUAL"), (False, "NUEVO")):
            with self.subTest(alfa_on_disk=present):
                files = dict(SAMPLE)
                disk = dict(files)
                disk["agents/viejo-alfa.md"] = b"nombre anterior\n"
                if not present:
                    del disk["agents/alfa.md"]
                self.f4_target(disk)
                self.write_state(files, schema=3, dests={"agents/alfa.md": "agents/viejo-alfa.md"})
                prev_state = read(self.target, self.STATE)
                self.assertIn(b'"schema": 3', prev_state)
                before = snapshot(self.target)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 0, out + err)
                st = self.states(out)
                self.assertEqual(st["agents/alfa.md"], expected)
                self.assertEqual(st["agents/viejo-alfa.md"], "HUERFANO")
                self.assertEqual(sorted(k for k, v in st.items() if v == "HUERFANO"), ["agents/viejo-alfa.md"])
                # igual que la referencia independiente (huerfanos y prevByDest)
                prev = json.loads(prev_state)
                self.assertEqual(ar.state3_orphans(prev, sorted(SAMPLE)), ["agents/viejo-alfa.md"])
                self.assertNotIn("agents/alfa.md", ar.prev_by_dest(prev))
                self.assertIn("HUERFANO=1", out)
                # T7: ahora si se afirma lo que T3 dejo abierto. El huerfano es por cambio de nombre (el rol alfa sigue en
                # el manifiesto): sin la nota de stdout y con el aviso de stderr (el archivo existe).
                self.assertNotIn("ya no estan en el manifiesto", out)
                self.assertNotIn("nota:", out)
                self.assertEqual([l for l in err.splitlines() if "es el nombre anterior de" in l],
                                 [self.f4t7_aviso("agents/viejo-alfa.md", "agents/alfa.md")])
                # Contrato de T3: clasificacion, HUERFANO informado y archivo intacto.
                self.assertEqual(snapshot(self.target), before)
                backup = os.path.join(self.tmp, "respaldo")
                shutil.rmtree(backup, ignore_errors=True)
                orphan_before = os.stat(os.path.join(self.target, "agents", "viejo-alfa.md")).st_mtime_ns
                out, err = self.install_ok("-BackupDir", backup)
                self.assertEqual(self.states(out)["agents/viejo-alfa.md"], "HUERFANO")
                self.assertEqual(read(self.target, "agents/viejo-alfa.md"), b"nombre anterior\n")
                self.assertEqual(os.stat(os.path.join(self.target, "agents", "viejo-alfa.md")).st_mtime_ns, orphan_before)
                self.assertEqual(read(self.target, "agents/alfa.md"), SAMPLE["agents/alfa.md"])
                # esquema 2 (no se escribe el 3), sin el huerfano, y el estado previo va al respaldo
                self.assert_state(5)
                self.assertNotIn(b'"dest"', read(self.target, self.STATE))
                self.assertNotIn(b"viejo-alfa", read(self.target, self.STATE))
                self.assertEqual(self.f4_tree(backup), {self.STATE: prev_state})

    def test_f4t3_case20_schema3_with_dest_equal_to_path_behaves_like_schema2(self):
        # Esquema 3 valido con dest = ruta del rol: misma clasificacion, salida y destino que el esquema 2.
        old = self.f4_old()
        scenarios = {
            "ACTUALIZAR y huerfano": (dict(old, **{"agents/viejo.md": b"anterior\n"}), True, 0),
            "intacto": (old, False, 0),
            "MODIFICADO": (dict(old, **{"agents/beta.md": b"editado a mano\n"}), False, 3),
        }
        for name, (disk, alfa_new, expected_code) in scenarios.items():
            with self.subTest(case=name):
                results = {}
                for schema in (2, 3):
                    self.update_source("agents/alfa.md", self.F4_NEW_ALFA if alfa_new else self.F4_OLD_ALFA)
                    self.f4_target(disk)
                    state_files = dict(old)
                    if "agents/viejo.md" in disk:
                        state_files["agents/viejo.md"] = disk["agents/viejo.md"]
                    self.write_state(state_files, schema=schema)
                    backup = os.path.join(self.tmp, "respaldo")
                    shutil.rmtree(backup, ignore_errors=True)
                    code, out, err = self.run_install("-BackupDir", backup, "-Force" if expected_code == 3 else "-DryRun")
                    # Se compara la clasificacion (no el manejo del estado: un esquema 3 distinto del que se escribiria
                    # se reescribe y se respalda; un esquema 2 igual, no).
                    summary = [l for l in out.splitlines() if l.startswith("Resumen:")]
                    results[schema] = (code, self.states(out), summary, err,
                                       {k: v for k, v in self.f4_tree(self.target).items() if k != self.STATE},
                                       sorted(k for k in self.f4_tree(backup) if k != self.STATE)
                                       if os.path.isdir(backup) else None)
                self.assertEqual(results[2], results[3])
                self.assertEqual(results[2][0], 0, str(results[2]))

    def test_f4t3_case21_invalid_schema3_state_is_absent_never_actualizar_never_huerfano(self):
        # Caso 21: un estado esquema 3 invalido se trata como ausente: con la version vieja en el destino sale
        # MODIFICADO (exit 3), nunca ACTUALIZAR ni HUERFANO; aviso limpio por stderr; ni se respalda ni se toca.
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        alfa = "agents/alfa.md"

        def dest(value):
            def mut(d):
                self.f4_entry(d)["dest"] = value
            return mut

        def drop_dest(d):
            del self.f4_entry(d)["dest"]

        def dest_of(rel, value):
            def mut(d):
                self.f4_entry(d, rel)["dest"] = value
            return mut

        def dup_dest(d):
            self.f4_entry(d)["dest"] = "agents/x.md"
            self.f4_entry(d, "agents/beta.md")["dest"] = "agents/x.md"

        def other_entry_path(d):
            self.f4_entry(d)["dest"] = "agents/beta.md"
            self.f4_entry(d, "agents/beta.md")["dest"] = "agents/beta2.md"

        def other_entry_path_not_in_manifest(d):
            # El "otro path" (agents/viejo.md) no esta en el manifiesto: solo la regla "dest igual al path de otra
            # entrada" lo atrapa, no la de las rutas del manifiesto.
            d["files"].append({"path": "agents/viejo.md", "sha256": self.f4_entry(d)["sha256"],
                               "written": self.f4_entry(d)["written"], "level": 5, "dest": "agents/viejo2.md"})
            self.f4_entry(d)["dest"] = "agents/viejo.md"

        def other_role_without_entry(d):
            d["files"] = [f for f in d["files"] if f["path"] != "agents/beta.md"]
            self.f4_entry(d)["dest"] = "agents/beta.md"

        def top(key, value):
            def mut(d):
                d[key] = value
            return mut

        def field(key, value):
            def mut(d):
                self.f4_entry(d)[key] = value
            return mut

        def rename_key(owner, old_key, new_key):
            def mut(d):
                target = d if owner == "top" else self.f4_entry(d)
                items = list(target.items())
                target.clear()
                for k, v in items:
                    target[new_key if k == old_key else k] = v
            return mut

        def schema1_with_dest(d):
            d.clear()
            d.update({"schema": 1, "algorithm": "sha256", "files": [
                {"path": f["path"], "sha256": f["sha256"], "dest": f["dest"]} for f in
                json.loads(read(self.target, self.STATE))["files"]]})

        variants = {
            "sin dest": drop_dest,
            "dest null": dest(None),
            "dest numero": dest(5),
            "dest booleano": dest(True),
            "dest lista": dest(["agents/x.md"]),
            "dest objeto": dest({"a": 1}),
            "dest vacio": dest(""),
            "dest settings.json": dest("settings.json"),
            "dest con ..": dest("agents/../x.md"),
            "dest con barra invertida": dest("agents\\x.md"),
            "dest con dos puntos": dest("agents/x:y.md"),
            "dest absoluto": dest("/agents/x.md"),
            "dest con mayusculas": dest("agents/Amigo.md"),
            "dest con salto final": dest("agents/amigo.md\n"),
            "dest reservado de Windows": dest("agents/con.md"),
            "dest con otra extension": dest("agents/amigo.txt"),
            "dest en subcarpeta": dest("agents/sub/x.md"),
            "dest de 75 caracteres": dest("agents/" + "a" * 65 + ".md"),
            "dest no ASCII": dest("agents/\u00e9.md"),
            "dest con NUL": dest("agents/a\u0000b.md"),
            "dest con guion blando": dest("agents/a\u00adb.md"),
            "dest de otra carpeta fija": dest("rules/agentes.md"),
            "dest repetido entre entradas": dup_dest,
            "dest igual al path de otra entrada": other_entry_path,
            "dest igual al path de otra entrada que no esta en el manifiesto": other_entry_path_not_in_manifest,
            "dest igual a la ruta de otro rol del manifiesto sin entrada": other_role_without_entry,
            "dest distinto en la regla fija": dest_of("rules/agentes.md", "agents/otro.md"),
            "dest distinto en el hook": dest_of("hooks/agent_guard.py", "agents/otro.md"),
            "dest distinto en la guia": dest_of("docs/agentes.md", "docs/otra.md"),
            "clave de mas en una entrada": field("extra", 1),
            "clave de mas en la raiz": top("extra", 1),
            "clave Dest con otra capitalizacion": rename_key("entry", "dest", "Dest"),
            "clave dest con NUL": rename_key("entry", "dest", "dest\u0000"),
            "clave __type": top("__type", "x"),
            "level 6": field("level", 6),
            "sin level": lambda d: self.f4_entry(d).pop("level"),
            "written invalido": field("written", "XYZ"),
            "eol crlf": top("eol", "crlf"),
            "algorithm md5": top("algorithm", "md5"),
            "schema 4": top("schema", 4),
            "schema 0": top("schema", 0),
            "schema texto": top("schema", "3"),
            "schema decimal": top("schema", 3.0),
            "schema 2 con la clave dest": top("schema", 2),
            "schema 1 con la clave dest": schema1_with_dest,
            "files vacio": top("files", []),
        }
        # Control: sin mutar, el mismo estado clasifica ACTUALIZAR (las variantes fallan por su campo).
        self.f4_target(self.f4_old())
        control = self.f4_state3()
        self.assertIsNone(ar.state3_problem(control, sorted(SAMPLE)))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)[alfa], "ACTUALIZAR")
        for name, mutate in variants.items():
            with self.subTest(case=name):
                self.f4_target(self.f4_old())
                data = self.f4_state3()
                mutate(data)
                # La referencia independiente tambien lo rechaza (o no es un esquema 3).
                self.assertIsNotNone(ar.state3_problem(data, sorted(SAMPLE)))
                raw = self.dump_state(data)
                before = snapshot(self.target)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 3, out + err)
                st = self.states(out)
                self.assertEqual(st[alfa], "MODIFICADO")
                self.assertNotIn("ACTUALIZAR", set(st.values()))
                self.assertNotIn("HUERFANO", set(st.values()))
                self.assertIn("HUERFANO=0", out)
                self.assertNotIn("nota:", out)
                self.assert_clean_unreadable_warning(err)
                self.assertEqual(snapshot(self.target), before)
                self.assertEqual(read(self.target, self.STATE), raw)

    def test_f4t3_case21_invalid_schema3_state_real_run_replaces_it_without_backup(self):
        # Un esquema 3 invalido no se respalda: con -Force se reescribe en esquema 2 y solo se respalda lo sobrescrito.
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        self.f4_target(self.f4_old())
        data = self.f4_state3(dests={"agents/alfa.md": "agents/viejo-alfa.md"})
        del self.f4_entry(data)["dest"]
        self.dump_state(data)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-Force", "-BackupDir", backup)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
        self.assertNotIn("HUERFANO", set(self.states(out).values()))
        self.assert_clean_unreadable_warning(err)
        self.assert_state(5)
        self.assertEqual(self.f4_tree(backup), {"agents/alfa.md": self.F4_OLD_ALFA})

    def test_f4t3_case21_state_size_limit_is_exact_for_schema3(self):
        # 1048576 bytes validos se leen (ACTUALIZAR); un byte mas, estado ausente (MODIFICADO).
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        for extra, expected, expected_code in ((0, "ACTUALIZAR", 0), (1, "MODIFICADO", 3)):
            with self.subTest(extra=extra):
                self.f4_target(self.f4_old())
                self.f4_state3()
                raw = read(self.target, self.STATE)
                raw += b" " * (1048576 + extra - len(raw))
                write(self.target, self.STATE, raw)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, expected_code, out + err)
                self.assertEqual(self.states(out)["agents/alfa.md"], expected)

    def test_f4t3_case22_schema2_with_dest_key_and_schema4_are_absent(self):
        # Caso 22: esquema 2 con la clave dest (desconocida en ese esquema) y schema 4: ausentes, con aviso.
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        for name, mutate in (("esquema 2 con dest", lambda d: d.update(schema=2)),
                             ("esquema 4", lambda d: d.update(schema=4))):
            with self.subTest(case=name):
                self.f4_target(self.f4_old())
                data = self.f4_state3(dests={"agents/alfa.md": "agents/viejo-alfa.md"})
                mutate(data)
                self.dump_state(data)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 3, out + err)
                self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
                self.assertNotIn("HUERFANO", set(self.states(out).values()))
                self.assert_clean_unreadable_warning(err)

    def test_f4t3_case23_prev_by_dest_actualizar_when_state_says_we_wrote_these_bytes_in_this_path(self):
        # Caso 23: estado 3 con dest = ruta actual y written = hash del destino: ACTUALIZAR, con respaldo del destino.
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        self.f4_target(self.f4_old())
        self.f4_state3()
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "ACTUALIZAR")
        self.assertEqual(err, "")
        backup = os.path.join(self.tmp, "respaldo")
        self.install_ok("-BackupDir", backup)
        self.assertEqual(read(self.target, "agents/alfa.md"), self.F4_NEW_ALFA)
        self.assertEqual(self.f4_tree(backup)["agents/alfa.md"], self.F4_OLD_ALFA)
        self.assert_state(5)

    def test_f4t3_case23_prev_by_dest_written_of_another_path_is_modified(self):
        # written de otra ruta (el hash de beta): el estado no afirma esos bytes para esta ruta: MODIFICADO.
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        self.f4_target(self.f4_old())
        self.f4_state3(written={"agents/alfa.md": self.sha(SAMPLE["agents/beta.md"])})
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)["agents/alfa.md"], "MODIFICADO")
        self.assertNotIn("ACTUALIZAR", set(self.states(out).values()))

    def test_f4t3_case23_prev_by_dest_role_with_a_previous_alias_is_not_actualizar_in_its_own_path(self):
        # El estado dice que el rol estuvo en agents/amigo.md: en agents/alfa.md (hoy su destino) no hay nada
        # escrito por nosotros. Con la version vieja da MODIFICADO aunque written coincida con ese hash (clasificar
        # contra el hash del rol daria ACTUALIZAR). El archivo viejo es HUERFANO, informado y sin tocar.
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        disk = dict(self.f4_old())
        disk["agents/amigo.md"] = b"nombre anterior\n"
        self.f4_target(disk)
        self.f4_state3(dests={"agents/alfa.md": "agents/amigo.md"})
        before = snapshot(self.target)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        st = self.states(out)
        self.assertEqual(st["agents/alfa.md"], "MODIFICADO")
        self.assertEqual(st["agents/amigo.md"], "HUERFANO")
        self.assertNotIn("ACTUALIZAR", set(st.values()))
        self.assertEqual(snapshot(self.target), before)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(self.states(out)["agents/amigo.md"], "HUERFANO")
        self.assertEqual(read(self.target, "agents/amigo.md"), b"nombre anterior\n")
        self.assertEqual(read(self.target, "agents/alfa.md"), self.F4_NEW_ALFA)
        self.assertEqual(sorted(self.f4_tree(backup)), ["agents/alfa.md", self.STATE])
        self.assertEqual(self.f4_tree(backup)["agents/alfa.md"], self.F4_OLD_ALFA)
        self.assert_state(5)

    def test_f4t3_case23_orphan_by_dest_is_reported_even_if_the_file_is_gone(self):
        # El huerfano se informa aunque el archivo ya no exista (como hoy) y nunca se crea ni se borra nada.
        self.make_source()
        disk = dict(SAMPLE)
        self.f4_target(disk)
        self.write_state(dict(SAMPLE), schema=3, dests={"agents/alfa.md": "agents/amigo.md"})
        out, err = self.install_ok("-DryRun")
        self.assertEqual(self.states(out)["agents/amigo.md"], "HUERFANO")
        self.assertEqual(self.states(out)["agents/alfa.md"], "IGUAL")
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "amigo.md")))

    def test_f4t3_case23_reassignment_in_the_state_gives_one_orphan_per_old_dest(self):
        # Dos roles con alias previos: cada destino previo que ya no es destino actual es un HUERFANO.
        self.make_source()
        self.f4_target(dict(SAMPLE))
        self.write_state(dict(SAMPLE), schema=3, dests={"agents/alfa.md": "agents/uno.md", "agents/beta.md": "agents/dos.md"})
        out, err = self.install_ok("-DryRun")
        st = self.states(out)
        self.assertEqual(sorted(k for k, v in st.items() if v == "HUERFANO"), ["agents/dos.md", "agents/uno.md"])
        self.assertIn("HUERFANO=2", out)

    def test_f4t3_case24_schema1_and_2_states_classify_as_before_and_keep_the_previous_level(self):
        # Caso 24: con estados de esquema 1 y 2 (y el 3 con dest = ruta) la clasificacion es la de hoy y
        # `Nivel anterior:` se calcula igual.
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        old = dict(self.f4_old())
        old["agents/viejo.md"] = b"anterior\n"
        for schema, level in ((1, 5), (2, 5), (3, 5), (2, 3), (3, 3)):
            with self.subTest(schema=schema, level=level):
                self.f4_target(old)
                self.write_state(old, schema=schema, level=level)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.states(out), {
                    "agents/alfa.md": "ACTUALIZAR", "agents/beta.md": "IGUAL", "rules/agentes.md": "IGUAL",
                    "hooks/agent_guard.py": "IGUAL", "docs/agentes.md": "IGUAL", "agents/viejo.md": "HUERFANO"})
                self.assertIn("Resumen: NUEVO=0 IGUAL=4 ACTUALIZAR=1 MODIFICADO=0 HUERFANO=1", out)
                self.assertIn("nota: los HUERFANO", out)
                self.assertEqual(err, "")
                if level == 3:
                    self.assertIn("Nivel anterior: 3", out.splitlines())
                else:
                    self.assertNotIn("Nivel anterior", out)

    def test_f4t3_case25_hostile_dest_gives_bounded_escaped_stderr(self):
        # Caso 25: un dest enorme o no ASCII no llega crudo ni entero a stdout ni a stderr.
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        variants = {
            "enorme": ("agents/" + "a" * 200000 + ".md", None),
            "no ASCII": ("agents/\u00e9\u202e\u0301\u00ad.md", ("\\u00e9", "\\u202e", "\\u0301", "\\u00ad")),
            "enorme no ASCII": ("agents/" + "\u00e9" * 50000 + ".md", ("\\u00e9",)),
        }
        for name, (value, escapes) in variants.items():
            with self.subTest(case=name):
                self.f4_target(self.f4_old())
                data = self.f4_state3()
                self.f4_entry(data)["dest"] = value
                self.dump_state(data)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 3, out + err)
                self.assertTrue(out.isascii() and err.isascii(), repr(out + err)[:300])
                self.assertLess(len(out) + len(err), 4000)
                self.assertNotIn("a" * 60, out + err)
                self.assertNotIn("HUERFANO", set(self.states(out).values()))
                self.assert_clean_unreadable_warning(err)
                for esc in escapes or ():
                    self.assertIn(esc, err)

    def test_f4t3_dest_of_74_characters_is_valid(self):
        # Limite exacto: agents/ + alias de 64 + .md = 74 caracteres es un dest valido (el de 75 se rechaza en el caso 21).
        self.update_source("agents/alfa.md", self.F4_NEW_ALFA)
        long_dest = "agents/" + "a" * 64 + ".md"
        self.f4_target(self.f4_old())
        self.f4_state3(dests={"agents/alfa.md": long_dest})
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)[long_dest], "HUERFANO")
        self.assertNotIn("aviso", err)

    def test_f4t3_dest_outside_agents_is_checked_on_its_own(self):
        # El chequeo "dest fuera de agents/" aislado: sin docs/agentes.md en el manifiesto ni en el estado, un agente
        # con dest docs/agentes.md no choca con ninguna otra regla (ni path de otra entrada, ni ruta del manifiesto).
        files = {k: v for k, v in SAMPLE.items() if k != "docs/agentes.md"}
        self.make_source(dict(files, **{"agents/alfa.md": self.F4_NEW_ALFA}))
        old = dict(files, **{"agents/alfa.md": self.F4_OLD_ALFA})
        for dest, valid in (("docs/agentes.md", False), ("agents/otro.md", True)):
            with self.subTest(dest=dest):
                self.f4_target(old)
                data = self.f4_state3(files=old)
                self.f4_entry(data)["dest"] = dest
                self.assertEqual(ar.state3_problem(data, sorted(files)) is None, valid)
                self.dump_state(data)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 3, out + err)
                st = self.states(out)
                self.assertEqual(st["agents/alfa.md"], "MODIFICADO")
                if valid:
                    self.assertEqual(st["agents/otro.md"], "HUERFANO")  # control: el estado es valido
                    self.assertNotIn("aviso", err)
                else:
                    self.assertNotIn("HUERFANO", set(st.values()))
                    self.assert_clean_unreadable_warning(err)
                    self.assertNotIn("HUERFANO=1", out)

    def f4_big_state(self, schema, n=2000, clash=False):
        files = []
        for i in range(n):
            h = "%064x" % (i + 1)
            entry = {"path": "agents/p%d.md" % i, "sha256": h, "written": h, "level": 5}
            if schema == 3:
                entry["dest"] = "agents/q%d.md" % i
            files.append(entry)
        if clash:
            files[0]["dest"] = "agents/p%d.md" % (n - 1)
        return {"schema": schema, "algorithm": "sha256", "eol": "lf", "files": files}

    def test_f4t3_schema3_validation_is_not_quadratic(self):
        # 2000 entradas con dest distinto: tiempo del instalador relativo al esquema 2 equivalente (no depende de la
        # maquina) y misma decision. Una busqueda por lista en la regla "dest igual al path de otra entrada" tardaba minutos.
        self.make_source()
        self.f4_target(dict(SAMPLE))
        timings = {}
        for name, state in (("2", self.f4_big_state(2)), ("3", self.f4_big_state(3)),
                            ("3 con choque", self.f4_big_state(3, clash=True))):
            with self.subTest(state=name):
                self.dump_state(state)
                start = time.perf_counter()
                code, out, err = self.run_install("-DryRun")
                timings[name] = time.perf_counter() - start
                self.assertEqual(code, 0, (out + err)[:500])
                if name == "3 con choque":
                    self.assertIn("HUERFANO=0", out)
                    self.assertIn("dest igual al path de otra entrada", err)
                else:
                    self.assertIn("HUERFANO=2000", out)
                    self.assertEqual(err, "")
        self.assertLessEqual(timings["3"], 3 * timings["2"] + 2, timings)
        self.assertLessEqual(timings["3 con choque"], 3 * timings["2"] + 2, timings)

    def test_f4t3_huge_values_give_short_stderr_in_state_and_manifest(self):
        # Toda ruta del estado o del manifiesto puede medir cientos de miles de caracteres y casar con la lista
        # permitida: los mensajes la recortan. Estado ausente: todo IGUAL, exit 0, solo el aviso en stderr.
        self.make_source()
        huge = "agents/" + "a" * 450000 + ".md"
        h = "%064x" % 7

        def entry(**kw):
            base = {"path": huge, "sha256": h, "written": h, "level": 5}
            base.update(kw)
            return base

        cases = {
            "esquema 2, written invalido": (2, [entry(written="zz")]),
            "esquema 2, level invalido": (2, [entry(level=9)]),
            "esquema 2, sha256 invalido": (2, [entry(sha256="zz")]),
            "esquema 2, ruta duplicada": (2, [entry(), entry()]),
            "esquema 3, written invalido": (3, [entry(written="zz", dest="agents/x.md")]),
            "esquema 3, level invalido": (3, [entry(level=9, dest="agents/x.md")]),
            "esquema 3, sin dest": (3, [entry()]),
            "esquema 3, dest no texto": (3, [entry(dest=5)]),
            "esquema 3, dest fuera de agents": (3, [entry(dest="rules/agentes.md")]),
            "esquema 3, dest demasiado largo": (3, [entry(dest="agents/" + "b" * 400000 + ".md")]),
        }
        for name, (schema, files) in cases.items():
            with self.subTest(case=name):
                self.f4_target(dict(SAMPLE))
                self.dump_state({"schema": schema, "algorithm": "sha256", "eol": "lf", "files": files})
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 0, (out + err)[:500])
                self.assertLess(len(err.encode("utf-8")), 1000, len(err))
                self.assert_clean_unreadable_warning(err)
        good = json.loads(read(self.src, "install-manifest.json"))
        for name, files in (("sha256 invalido", [{"path": huge, "sha256": "zz"}]),
                            ("ruta duplicada", [{"path": huge, "sha256": h}, {"path": huge, "sha256": h}])):
            with self.subTest(case="manifiesto, " + name):
                write(self.src, "install-manifest.json", json.dumps(dict(good, files=files)).encode("ascii"))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, (out + err)[:500])
                self.assertLess(len(err.encode("utf-8")), 1000, len(err))

    @staticmethod
    def d5_reason(dest):
        short = dest[:40] + "..." if len(dest) > 40 else dest
        return ("el destino " + short + " de agents/sentinel.md es ahora un archivo del manifiesto; si el "
                "repositorio anadio un agente con el nombre de tu alias, elige otro alias y repite con -Force")

    def test_f4t3_case59_dest_equal_to_a_manifest_path_is_absent_with_the_d5_warning(self):
        for alias in ('tester', 'a' * 50):
            with self.subTest(alias=alias):
                self.f4_case59(alias)

    def f4_case59(self, alias):
        dest = 'agents/' + alias + '.md'
        # Caso 59 (E3, S14): el estado dice sentinel -> tester y el repositorio ahora trae agents/tester.md: el estado se
        # trata como ausente con el aviso de D5; lo que cambio sale MODIFICADO (exit 3, nada escrito); con -Force
        # respaldo (sin el estado invalido) y sobrescritura; ni ACTUALIZAR ni HUERFANO. Control: sin tester en el
        # manifiesto el mismo estado es valido y agents/tester.md sale HUERFANO, sin aviso.
        old = dict(SAMPLE, **{"agents/sentinel.md": b"sentinel viejo\n"})
        new_source = dict(old, **{"agents/sentinel.md": b"sentinel nuevo\n", dest: b"agente del repositorio\n"})
        edited = b"sentinel editado a mano\n"

        def prepare(source):
            self.make_source(source)
            self.f4_target(dict(old, **{"agents/sentinel.md": edited}))
            data = self.f4_state3(files=old, dests={"agents/sentinel.md": dest})
            self.dump_state(data)
            return data

        state = prepare(new_source)
        self.assertIsNotNone(ar.state3_problem(state, sorted(new_source)))
        raw = read(self.target, self.STATE)
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 3, out + err)
                st = self.states(out)
                self.assertEqual(st["agents/sentinel.md"], "MODIFICADO")
                self.assertEqual(st[dest], "NUEVO")
                self.assertNotIn("ACTUALIZAR", set(st.values()))
                self.assertNotIn("HUERFANO", set(st.values()))
                self.assertIn("aviso:", err)
                self.assertIn("no se pudo leer o no es valido (" + self.d5_reason(dest) + "). Se trata como ausente: no se respalda.", err)
                self.assertTrue(err.isascii())
                self.assertEqual(snapshot(self.target), before)
                self.assertEqual(read(self.target, self.STATE), raw)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-Force", "-BackupDir", backup)
        self.assertEqual(code, 0, out + err)
        self.assertIn(self.d5_reason(dest), err)
        self.assertEqual(self.f4_tree(backup), {"agents/sentinel.md": edited})
        self.assertEqual(read(self.target, "agents/sentinel.md"), b"sentinel nuevo\n")
        self.assertEqual(read(self.target, dest), b"agente del repositorio\n")
        self.assert_state(5)
        # Control: el manifiesto no trae agents/tester.md.
        shutil.rmtree(backup, ignore_errors=True)
        control_source = dict(new_source)
        del control_source[dest]
        state = prepare(control_source)
        self.assertIsNone(ar.state3_problem(state, sorted(control_source)))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 3, out + err)
        st = self.states(out)
        self.assertEqual(st["agents/sentinel.md"], "MODIFICADO")
        self.assertEqual(st[dest], "HUERFANO")
        self.assertNotIn("aviso", err)

    def test_f4t3_read_state_without_manifest_paths_fails_clearly(self):
        # Llamar a Read-State sin la lista del manifiesto (o con $null) lanza un error claro, no desactiva la regla.
        self.make_source()
        self.f4_target(dict(SAMPLE))
        self.write_state(dict(SAMPLE), schema=3)
        self.patch_script("$prevLevel = $null",
                          "try { [void](Read-State $statePath $null) } catch { Write-Err ('PROBE ' + $_.Exception.Message) }")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertIn("PROBE falta la lista de rutas del manifiesto (ManifestPaths)", err)

    def test_f4t3_read_manifest_still_requires_schema_1(self):
        # install-manifest.json sigue siendo esquema 1: un manifiesto con schema 3 (y dest) no es valido.
        self.make_source()
        good = json.loads(read(self.src, "install-manifest.json"))
        for schema in (2, 3):
            with self.subTest(schema=schema):
                bad = dict(good, schema=schema)
                bad["files"] = [dict(f, dest=f["path"]) for f in good["files"]]
                write(self.src, "install-manifest.json", json.dumps(bad).encode("ascii"))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertIn("schema debe ser 1", err)
                self.assertFalse(os.path.exists(self.target))

    def test_f4t3_dest_never_leads_to_a_write_or_delete(self):
        # Un estado forjado con un dest valido solo puede dar un HUERFANO informado: ni se borra, ni se respalda, ni
        # se escribe en esa ruta (bytes y mtime intactos tras una instalacion real con -Force).
        self.make_source()
        disk = dict(SAMPLE)
        disk["agents/ajeno.md"] = b"archivo del usuario\n"
        self.f4_target(disk)
        self.write_state(dict(SAMPLE), schema=3, dests={"agents/alfa.md": "agents/ajeno.md"})
        before = snapshot(self.target)["agents\\ajeno.md" if os.name == "nt" else "agents/ajeno.md"]
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(self.states(out)["agents/ajeno.md"], "HUERFANO")
        after = snapshot(self.target)["agents\\ajeno.md" if os.name == "nt" else "agents/ajeno.md"]
        self.assertEqual(after, before)
        self.assertNotIn("agents/ajeno.md", self.f4_tree(backup))
        self.assertEqual(self.leftover_temps(), [])

    # --- Fase 4, T4: destRel (ruta de destino) separada del rol en los pasos 4 a 9 ---
    # Estas pruebas inyectan, tras el ancla `# Alias:`, un destRel que no es la identidad (sin alias configurados en
    # produccion destRel es la identidad; con alias lo calcula T5 antes del ancla). El mapa viaja en la variable de
    # entorno F4_DESTS ("rol=destino;rol=destino"): el mismo script (parcheado una vez) sirve para varias corridas con
    # destinos distintos, y las ayudas existentes (assert_reparse_rejected, ...) lo heredan sin cambios.

    F4T4_INJECT = ("foreach ($f4pair in ([string]$env:F4_DESTS).Split([char]59)) { if ($f4pair.Length -gt 0) "
                   "{ $f4kv = $f4pair.Split([char]61); $destRel[$f4kv[0]] = $f4kv[1] } }")
    F4T4_ALFA = "agents/alfa.md"
    F4T4_BETA = "agents/beta.md"
    F4T4_TESTER = "agents/tester.md"
    F4T4_DEV = "agents/dev.md"

    def f4t4_prepare(self, files=None):
        self.make_source(files)
        self.patch_script("# Alias:", self.F4T4_INJECT)

    def f4t4_set(self, mapping):
        """Fija el destRel inyectado para las corridas siguientes ({} = identidad)."""
        self.addCleanup(os.environ.pop, "F4_DESTS", None)
        os.environ["F4_DESTS"] = ";".join("%s=%s" % kv for kv in mapping.items())

    def f4t4_manifest(self):
        return read(self.src, "install-manifest.json")

    def f4t4_copied(self, out):
        return [l.split(": ", 1)[1].strip() for l in out.splitlines() if l.startswith("Copiado: ")]

    def f4t4_role_path_absent(self):
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "alfa.md")))

    def test_f4t4_case26_clean_install_writes_only_in_the_dest_path(self):
        # Caso 26: el archivo del rol alfa se escribe SOLO en agents/tester.md; Copiado: y la fila llevan esa ruta; el
        # estado es el de la referencia (esquema 3 con dest en todas las entradas).
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(read(self.target, self.F4T4_TESTER), SAMPLE[self.F4T4_ALFA])
        self.f4t4_role_path_absent()
        copied = self.f4t4_copied(out)
        self.assertIn(self.F4T4_TESTER, copied)
        self.assertNotIn(self.F4T4_ALFA, copied)
        self.assertEqual(len(copied), 5)
        st = self.states(out)
        self.assertEqual(st[self.F4T4_TESTER], "NUEVO")
        self.assertNotIn(self.F4T4_ALFA, st)
        self.assertEqual(len(st), 5)
        self.assertEqual(set(st.values()), {"NUEVO"})
        self.assertIn("Verificado: 5 archivo(s)", out)
        self.assertEqual(read(self.target, self.STATE),
                         ar.state_for3(self.f4t4_manifest(), None, 5, {self.F4T4_ALFA: self.F4T4_TESTER}))
        self.assertIn(b'"schema": 3', read(self.target, self.STATE))
        self.assertFalse(os.path.exists(backup))
        self.assertEqual(self.leftover_temps(), [])
        self.assertNotIn("no se pudo leer o no es valido", err)
        self.assert_nothing_written_outside_target_and_backup()

    def test_f4t4_case26_dryrun_shows_the_dest_path_and_writes_nothing(self):
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        st = self.states(out)
        self.assertEqual(st[self.F4T4_TESTER], "NUEVO")
        self.assertNotIn(self.F4T4_ALFA, st)
        self.assertIn("NUEVO=5", out)
        self.assertFalse(os.path.exists(self.target))
        self.assert_nothing_written_outside_target_and_backup()

    def test_f4t4_case27_actualizar_backs_up_the_dest_path(self):
        # Caso 27 (a): destino con alias intacto segun el estado: ACTUALIZAR, respaldo en <respaldo>/<ruta de destino>.
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        self.install_ok()
        prev_state = read(self.target, self.STATE)
        new = dict(SAMPLE)
        new[self.F4T4_ALFA] = b"alfa 2\n"
        self.make_source(new)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-DryRun", "-BackupDir", backup)
        self.assertEqual(code, 0, out + err)
        st = self.states(out)
        self.assertEqual(st[self.F4T4_TESTER], "ACTUALIZAR")
        self.assertEqual(sorted(k for k, v in st.items() if v == "ACTUALIZAR"), [self.F4T4_TESTER])
        self.assertIn("Respaldo: ", out)
        self.assertFalse(os.path.exists(backup))
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(read(backup, self.F4T4_TESTER), SAMPLE[self.F4T4_ALFA])
        self.assertFalse(os.path.exists(os.path.join(backup, "agents", "alfa.md")))
        self.assertIn("Respaldado: " + self.F4T4_TESTER, out)
        self.assertEqual(read(self.target, self.F4T4_TESTER), b"alfa 2\n")
        self.f4t4_role_path_absent()
        # el estado cambio (alfa tiene otro written): el anterior va al respaldo
        self.assertEqual(read(backup, self.STATE), prev_state)
        self.assertEqual(read(self.target, self.STATE),
                         ar.state_for3(self.f4t4_manifest(), None, 5, {self.F4T4_ALFA: self.F4T4_TESTER}))
        self.assertEqual(self.f4_tree(backup).keys(), {self.F4T4_TESTER, self.STATE})

    def test_f4t4_case27_hand_edited_dest_is_modificado_and_force_backs_it_up(self):
        # Caso 27 (b): edicion a mano del archivo con alias: MODIFICADO (exit 3, nada escrito); con -Force, respaldo
        # de la ruta de destino y sobrescritura.
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        self.install_ok()
        write(self.target, self.F4T4_TESTER, b"editado a mano\n")
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.states(out)[self.F4T4_TESTER], "MODIFICADO")
        self.assertIn(self.F4T4_TESTER, err)
        self.assertNotIn(self.F4T4_ALFA, err)
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(os.path.exists(backup))
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(read(backup, self.F4T4_TESTER), b"editado a mano\n")
        self.assertFalse(os.path.exists(os.path.join(backup, "agents", "alfa.md")))
        self.assertEqual(read(self.target, self.F4T4_TESTER), SAMPLE[self.F4T4_ALFA])
        self.f4t4_role_path_absent()
        # el segundo estado no cambia (written igual): solo el archivo editado va al respaldo
        self.assertEqual(self.f4_tree(backup), {self.F4T4_TESTER: b"editado a mano\n"})

    def test_f4t4_case27_file_in_the_role_path_is_an_orphan_and_is_never_touched(self):
        # El archivo previo en la ruta del rol queda HUERFANO informado: sin tocar (bytes y mtime), sin respaldar,
        # tambien con -Force. Una vez reescrito el estado deja de informarse.
        self.f4t4_prepare()
        self.f4t4_set({})
        self.install_ok()
        role_file = os.path.join(self.target, "agents", "alfa.md")
        old = os.stat(role_file).st_mtime_ns - 5_000_000_000
        os.utime(role_file, ns=(old, old))
        prev_state = read(self.target, self.STATE)
        before = snapshot(self.target)["agents\\alfa.md" if os.name == "nt" else "agents/alfa.md"]
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        st = self.states(out)
        self.assertEqual(st[self.F4T4_TESTER], "NUEVO")
        self.assertEqual(st[self.F4T4_ALFA], "HUERFANO")
        self.assertEqual(sorted(k for k, v in st.items() if v == "HUERFANO"), [self.F4T4_ALFA])
        self.assertIn("HUERFANO=1", out)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(self.states(out)[self.F4T4_ALFA], "HUERFANO")
        after = snapshot(self.target)["agents\\alfa.md" if os.name == "nt" else "agents/alfa.md"]
        self.assertEqual(after, before)
        self.assertEqual(read(self.target, self.F4T4_TESTER), SAMPLE[self.F4T4_ALFA])
        self.assertEqual(self.f4_tree(backup), {self.STATE: prev_state})
        self.assertEqual(read(self.target, self.STATE),
                         ar.state_for3(self.f4t4_manifest(), None, 5, {self.F4T4_ALFA: self.F4T4_TESTER}))
        out, err = self.install_ok()
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertNotIn(self.F4T4_ALFA, self.states(out))

    def test_f4t4_role_path_is_never_inspected_when_it_has_another_destination(self):
        # Ni el reanalisis, ni la carpeta, ni el bloqueo de la ruta del rol importan: no se mira. Una junction en
        # agents/alfa.md no impide instalar alfa en agents/tester.md.
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        os.makedirs(os.path.join(self.target, "agents"))
        link = os.path.join(self.target, "agents", "alfa.md")
        self.make_link_dir(link, self.outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        out, err = self.install_ok()
        self.assertEqual(read(self.target, self.F4T4_TESTER), SAMPLE[self.F4T4_ALFA])
        self.assertEqual(os.listdir(self.outside), [])

    def test_f4t4_case28_verification_names_the_dest_path_exit4(self):
        # Caso 28: archivo alterado en el Paso 8: exit 4 y el mensaje nombra la ruta de destino (no la del rol).
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        victim = os.path.join(self.target, "agents", "tester.md").replace("'", "''")
        self.patch_script("# Paso 8:", "[System.IO.File]::WriteAllBytes('%s', [byte[]]@(65))" % victim)
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("la verificacion posterior fallo", err)
        failed = err.split("la verificacion posterior fallo", 1)[1]
        self.assertIn(self.F4T4_TESTER, failed.splitlines()[1])
        self.assertNotIn(self.F4T4_ALFA, err)
        self.assertFalse(os.path.exists(os.path.join(self.target, self.STATE)))
        self.f4t4_role_path_absent()

    @unittest.skipUnless(os.name == "nt", "el atributo de solo lectura bloquea el reemplazo solo en Windows")
    def test_f4t4_copy_failure_names_the_dest_path_exit4(self):
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        self.install_ok()
        new = dict(SAMPLE)
        new[self.F4T4_ALFA] = b"alfa 2\n"
        self.make_source(new)
        self.inject_readonly_at_step7(self.F4T4_TESTER)
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("fallo la copia de " + self.F4T4_TESTER, err)
        self.assertNotIn(self.F4T4_ALFA, err)

    def test_f4t4_case29_reparse_point_in_the_dest_path_exit1_in_both_modes(self):
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        os.makedirs(os.path.join(self.target, "agents"))
        link = os.path.join(self.target, "agents", "tester.md")
        self.make_link_dir(link, self.outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        self.assert_reparse_rejected(expect_in_err="tester.md", outside_before=snapshot(self.outside))
        self.assert_reparse_rejected("-Force", expect_in_err="tester.md", outside_before=snapshot(self.outside))
        self.assertEqual(os.listdir(self.outside), [])

    def test_f4t4_case29_folder_in_the_dest_path_exit1_in_both_modes(self):
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        os.makedirs(os.path.join(self.target, "agents", "tester.md"))
        before = snapshot(self.target)
        for mode in (["-DryRun"], [], ["-Force"]):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("es una carpeta, no un archivo", err)
                self.assertIn("tester.md", err)
                self.assertNotIn("Copiado", out)
                self.assertEqual(snapshot(self.target), before)

    def test_f4t4_case29_file_where_a_folder_is_needed_exit1_in_both_modes(self):
        # Una de las carpetas intermedias de la ruta de destino es un archivo (agents/ en este caso).
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        write(self.target, "agents", b"soy un archivo")
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("es un archivo y deberia ser una carpeta", err)
                self.assertNotIn("Copiado", out)

    def test_f4t4_case29_read_only_dest_exit1_in_both_modes(self):
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        self.install_ok()
        new = dict(SAMPLE)
        new[self.F4T4_ALFA] = b"alfa 2\n"
        self.make_source(new)
        self.make_readonly(self.F4T4_TESTER)
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("solo lectura", err)
                self.assertIn("tester.md", err)
                self.assertNotIn("Copiado", out)
                self.assertEqual(snapshot(self.target), before)

    @unittest.skipUnless(os.name == "nt", "el bloqueo de uso compartido es de Windows")
    def test_f4t4_case29_locked_dest_exit1_in_both_modes(self):
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        self.install_ok()
        new = dict(SAMPLE)
        new[self.F4T4_ALFA] = b"alfa 2\n"
        self.make_source(new)
        self.lock_file(os.path.join(self.target, "agents", "tester.md"), self.GENERIC_READ, 1)
        before = snapshot(self.target)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)
                self.assertIn("bloqueado", err)
                self.assertIn("tester.md", err)
                self.assertNotIn("Copiado", out)
                self.assertEqual(snapshot(self.target), before)

    def test_f4t4_case30_hook_goes_first_with_a_non_identity_dest(self):
        # Caso 30: el hook (rol fijo, Path) va primero aunque el agente con otro destino sea el primero del manifiesto.
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        out, err = self.install_ok()
        copied = self.f4t4_copied(out)
        self.assertEqual(copied[0], "hooks/agent_guard.py")
        self.assertIn(self.F4T4_TESTER, copied)
        # tambien cuando el hook ya existe y se actualiza
        new = dict(SAMPLE)
        new["hooks/agent_guard.py"] = b"print('guard 2')\n"
        new[self.F4T4_ALFA] = b"alfa 2\n"
        self.make_source(new)
        out, err = self.install_ok()
        copied = self.f4t4_copied(out)
        self.assertEqual(copied[0], "hooks/agent_guard.py")
        self.assertEqual(sorted(copied), sorted(["hooks/agent_guard.py", self.F4T4_TESTER]))

    def test_f4t4_case31_second_run_is_all_igual_and_does_not_rewrite_the_state(self):
        # Caso 31: el estado esquema 3 que escribio T4 se relee como valido: segunda corrida todo IGUAL, ni estado, ni
        # respaldo, ni aviso.
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER, self.F4T4_BETA: self.F4T4_DEV})
        self.install_ok()
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-DryRun", "-BackupDir", backup)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertNotIn("Respaldo:", out)
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertEqual(len(self.states(out)), 5)
        self.assertIn("escritos=0 IGUAL=5", out)
        self.assertNotIn("Estado:", out)
        self.assertNotIn("Copiado", out)
        self.assertNotIn("Respaldado", out)
        self.assertNotIn("no se pudo leer o no es valido", err)
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(os.path.exists(backup))

    def test_f4t4_changing_the_alias_leaves_one_orphan_per_old_dest(self):
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        self.install_ok()
        prev_state = read(self.target, self.STATE)
        tester_before = snapshot(self.target)["agents\\tester.md" if os.name == "nt" else "agents/tester.md"]
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_DEV})
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        st = self.states(out)
        self.assertEqual(st[self.F4T4_DEV], "NUEVO")
        self.assertEqual(st[self.F4T4_TESTER], "HUERFANO")
        self.assertEqual(sorted(k for k, v in st.items() if v == "HUERFANO"), [self.F4T4_TESTER])
        self.assertEqual(read(self.target, self.F4T4_DEV), SAMPLE[self.F4T4_ALFA])
        self.f4t4_role_path_absent()
        after = snapshot(self.target)["agents\\tester.md" if os.name == "nt" else "agents/tester.md"]
        self.assertEqual(after, tester_before)
        self.assertEqual(read(self.target, self.STATE),
                         ar.state_for3(self.f4t4_manifest(), None, 5, {self.F4T4_ALFA: self.F4T4_DEV}))
        self.assertEqual(self.f4_tree(backup), {self.STATE: prev_state})

    def test_f4t4_swapping_two_dests_classifies_each_path_against_its_own_state_entry(self):
        # alfa: tester a dev; beta: dev a tester. Cada ruta de destino lleva los bytes del OTRO rol: intactas segun
        # prevByDest (ruta a written), asi que son ACTUALIZAR (no MODIFICADO) y los dos viejos van al respaldo.
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER, self.F4T4_BETA: self.F4T4_DEV})
        self.install_ok()
        self.assertNotEqual(SAMPLE[self.F4T4_ALFA], SAMPLE[self.F4T4_BETA])
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_DEV, self.F4T4_BETA: self.F4T4_TESTER})
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        st = self.states(out)
        self.assertEqual(st[self.F4T4_DEV], "ACTUALIZAR")
        self.assertEqual(st[self.F4T4_TESTER], "ACTUALIZAR")
        self.assertEqual(sorted(k for k, v in st.items() if v == "HUERFANO"), [])
        self.assertEqual(read(self.target, self.F4T4_DEV), SAMPLE[self.F4T4_ALFA])
        self.assertEqual(read(self.target, self.F4T4_TESTER), SAMPLE[self.F4T4_BETA])
        self.assertEqual(read(backup, self.F4T4_DEV), SAMPLE[self.F4T4_BETA])
        self.assertEqual(read(backup, self.F4T4_TESTER), SAMPLE[self.F4T4_ALFA])

    def test_f4t4_removing_the_alias_orphans_the_alias_file_and_goes_back_to_schema2(self):
        # Primero sin alias, luego con alias (el archivo del rol queda), luego sin alias otra vez: el del rol sale IGUAL
        # (sus bytes son los que se escribirian), el del alias HUERFANO, y el estado vuelve a esquema 2.
        self.f4t4_prepare()
        self.f4t4_set({})
        self.install_ok()
        self.assert_state(5)
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_TESTER})
        self.install_ok()
        self.assertIn(b'"schema": 3', read(self.target, self.STATE))
        self.f4t4_set({})
        out, err = self.install_ok()
        st = self.states(out)
        self.assertEqual(st[self.F4T4_ALFA], "IGUAL")
        self.assertEqual(st[self.F4T4_TESTER], "HUERFANO")
        self.assertEqual(read(self.target, self.F4T4_TESTER), SAMPLE[self.F4T4_ALFA])
        self.assert_state(5)
        self.assertNotIn(b'"dest"', read(self.target, self.STATE))
        # sin el archivo viejo del rol en disco: NUEVO
        os.remove(os.path.join(self.target, "agents", "alfa.md"))
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_DEV})
        self.install_ok()
        os.remove(os.path.join(self.target, "agents", "tester.md"))
        self.f4t4_set({})
        out, err = self.install_ok()
        st = self.states(out)
        self.assertEqual(st[self.F4T4_ALFA], "NUEVO")
        self.assertEqual(st[self.F4T4_DEV], "HUERFANO")
        self.assert_state(5)

    def test_f4t4_identity_keeps_schema2_without_dest(self):
        # Con la identidad (tambien dicha de forma explicita) el estado es el esquema 2 de siempre.
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_ALFA, "hooks/agent_guard.py": "hooks/agent_guard.py"})
        self.install_ok()
        self.assert_state(5)
        self.assertNotIn(b'"dest"', read(self.target, self.STATE))
        self.assertIn(b'"schema": 2', read(self.target, self.STATE))

    def test_f4t4_level_cell_is_looked_up_by_role_not_by_dest_path(self):
        # Con un destRel no identidad, la celda de la tabla de niveles sigue buscandose por ROL: el archivo trae el
        # model: y el effort: del rol y la linea Ajuste: lleva la ruta de destino.
        mapping = {"agents/atlas.md": "agents/dev.md", "agents/scribe.md": "agents/qa.md"}
        self.f4t4_prepare(LEVEL_SAMPLE)
        self.f4t4_set(mapping)
        write(self.target, self.CONFIG, b'{"level": 3}')
        out, err = self.install_ok()
        expected = level_expected(LEVEL_SAMPLE, 3)
        self.assertNotEqual(expected["agents/atlas.md"], LEVEL_SAMPLE["agents/atlas.md"])
        self.assertEqual(read(self.target, "agents/dev.md"), expected["agents/atlas.md"])
        self.assertEqual(read(self.target, "agents/qa.md"), expected["agents/scribe.md"])
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "atlas.md")))
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "scribe.md")))
        table = lr.read_script_table()
        for role, dest in (("atlas", "dev"), ("scribe", "qa")):
            model, effort = table[(3, role)]
            self.assertIn("Ajuste: agents/%s.md  model: %s  effort: %s" % (dest, model, effort), out.splitlines())
            self.assertNotIn("Ajuste: agents/%s.md" % role, out)
        self.assertEqual(read(self.target, self.STATE),
                         ar.state_for3(self.f4t4_manifest(), level_hashes(LEVEL_SAMPLE, 3), 3, mapping))
        # reinstalar igual: todo IGUAL
        out, err = self.install_ok()
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})

    def test_f4t4_level_change_with_an_alias_updates_the_dest_file(self):
        mapping = {"agents/atlas.md": "agents/dev.md"}
        self.f4t4_prepare(LEVEL_SAMPLE)
        self.f4t4_set(mapping)
        write(self.target, self.CONFIG, b'{"level": 3}')
        self.install_ok()
        e3 = level_expected(LEVEL_SAMPLE, 3)["agents/atlas.md"]
        e4 = level_expected(LEVEL_SAMPLE, 4)["agents/atlas.md"]
        self.assertNotEqual(e3, e4)
        write(self.target, self.CONFIG, b'{"level": 4}')
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        self.assertEqual(self.states(out)["agents/dev.md"], "ACTUALIZAR")
        self.assertIn("Nivel anterior: 3", out)
        self.assertEqual(read(self.target, "agents/dev.md"), e4)
        self.assertEqual(read(backup, "agents/dev.md"), e3)
        self.assertEqual(read(self.target, self.STATE),
                         ar.state_for3(self.f4t4_manifest(), level_hashes(LEVEL_SAMPLE, 4), 4, mapping))

    def test_f4t4_dest_of_75_chars_is_rejected_before_writing_in_both_modes(self):
        # Tope en el limite: agents/ + 64 + .md = 74 vale; 75 es demasiado larga.
        long75 = "agents/" + "a" * 65 + ".md"
        self.assertEqual(len(long75), 75)
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: long75})
        for mode in (["-DryRun"], []):
            code, out, err = self.run_install(*mode)
            self.assertEqual(code, 1, out + err)
            self.assertIn("error: la ruta de destino de ", err)
            self.assertIn("es demasiado larga", err)
            self.assertIn("No se escribio nada", err)
            self.assertNotIn(long75, out + err)
            self.assertFalse(os.path.exists(self.target))
            self.assertNotIn("Copiado", out)
        self.assert_nothing_written_outside_target_and_backup()

    def test_f4t4_dest_of_exactly_74_chars_is_accepted(self):
        ok74 = "agents/" + "a" * 64 + ".md"
        self.assertEqual(len(ok74), 74)
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: ok74})
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(os.path.exists(self.target))
        out, err = self.install_ok()
        self.assertEqual(read(self.target, ok74), SAMPLE[self.F4T4_ALFA])
        self.f4t4_role_path_absent()

    def test_f4t4_dest_equal_to_a_manifest_path_without_repeats_is_rejected_by_manifest_check(self):
        # Sin repetidos (alfa -> beta.md, beta -> dev.md): sólo la comprobacion contra el manifiesto puede rechazarlo.
        self.f4t4_prepare()
        self.f4t4_set({self.F4T4_ALFA: self.F4T4_BETA, self.F4T4_BETA: self.F4T4_DEV})
        for mode in (["-DryRun"], []):
            code, out, err = self.run_install(*mode)
            self.assertEqual(code, 1, out + err)
            self.assertIn("error: la ruta de destino de ", err)
            self.assertIn("coincide con un archivo del manifiesto", err)
            self.assertNotIn("repite", err)
            self.assertIn("No se escribio nada", err)
            self.assertFalse(os.path.exists(self.target))
            self.assertNotIn("Copiado", out)
        self.assert_nothing_written_outside_target_and_backup()

    def test_f4t4_invalid_dest_table_is_exit1_before_writing_in_both_modes(self):
        # Defensa en profundidad: ninguna ruta de destino que no cumpla las reglas del estado (D1 a D7) llega a un
        # destino de escritura, venga de donde venga. El mensaje nombra el rol y nunca la ruta.
        alfa, beta = self.F4T4_ALFA, self.F4T4_BETA
        cases = {
            "con ..": {alfa: "agents/../x.md"},
            "mayusculas": {alfa: "agents/Tester.md"},
            "reservado de Windows": {alfa: "agents/con.md"},
            "barra inicial": {alfa: "/agents/x.md"},
            "dos puntos": {alfa: "agents/x:y.md"},
            "sale de agents/": {alfa: "rules/agentes.md"},
            "ruta de otro archivo del manifiesto": {alfa: "agents/beta.md"},
            "archivo fijo cambiado": {"hooks/agent_guard.py": "agents/x.md"},
            "demasiado larga": {alfa: "agents/" + "a" * 72 + ".md"},
            "repetida": {alfa: "agents/x.md", beta: "agents/x.md"},
        }
        for name, mapping in cases.items():
            with self.subTest(case=name):
                shutil.rmtree(self.src, ignore_errors=True)
                os.makedirs(self.src)
                shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))
                self.f4t4_prepare()
                self.f4t4_set(mapping)
                shutil.rmtree(self.target, ignore_errors=True)
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 1, out + err)
                    self.assertIn("error: la ruta de destino de ", err)
                    self.assertIn("No se escribio nada", err)
                    for bad in mapping.values():
                        self.assertNotIn(bad, out + err)
                    self.assertFalse(os.path.exists(self.target))
                    self.assertNotIn("Copiado", out)
                self.assert_nothing_written_outside_target_and_backup()

    # --- Fase 4, T5: transformacion de textos y activacion de los alias (casos 32 a 40 y 56 del plan) ---

    F4T5_MSG = "error: no se pueden aplicar los alias a "

    def f4t5_source(self, files=None, crlf=False):
        files = ALIAS_SAMPLE if files is None else files
        self.make_source(files, crlf=crlf)
        return files

    def f4t5_config(self, aliases, level=None):
        return self.write_config(self.alias_config(aliases, level=level))

    def assert_alias_installed(self, files, level, aliases):
        """Cada archivo del destino es, byte a byte, el de la referencia; ningun agents/<rol>.md con alias queda; el
        estado es el de la referencia (esquema 3 si algun destino difiere del rol, si no el esquema 2)."""
        expected = alias_expected(files, aliases, level)
        hashes, dests = {}, {}
        for rel, (dest, data) in expected.items():
            self.assertEqual(read(self.target, dest), data, rel)
            hashes[rel] = bm.canonical_sha256(data)
            dests[rel] = dest
            if dest != rel:
                self.assertFalse(os.path.exists(os.path.join(self.target, *rel.split("/"))), rel)
        manifest = read(self.src, "install-manifest.json")
        if any(d != r for r, d in dests.items()):
            want = ar.state_for3(manifest, hashes, level, dests)
        else:
            want = lr.state_for(manifest, hashes, level)
        self.assertEqual(read(self.target, self.STATE), want)

    def test_f4t5_case32_clean_install_with_one_alias_matches_the_reference(self):
        files = self.f4t5_source()
        self.f4t5_config(ALIAS_ONE)
        out, err = self.install_ok()
        # el unico aviso es el de siempre de un -Target distinto de ~/.claude
        self.assertEqual(err.strip().count("aviso:"), 1, err)
        self.assertNotIn("error", err)
        self.assert_alias_installed(files, 5, ALIAS_ONE)
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "sentinel.md")))
        self.assertIn(b"\nname: amigo-qa\n", read(self.target, "agents/amigo-qa.md"))
        self.assertIn(b'"schema": 3', read(self.target, self.STATE))
        self.assertIn(b'"dest": "agents/amigo-qa.md"', read(self.target, self.STATE))
        self.assertIn("Alias: sentinel -> amigo-qa (agents/amigo-qa.md)", out.splitlines())
        copied = self.f4t4_copied(out)
        self.assertEqual(copied[0], "hooks/agent_guard.py")
        self.assertIn("agents/amigo-qa.md", copied)
        self.assertNotIn("agents/sentinel.md", copied)
        self.assertEqual(self.states(out)["agents/amigo-qa.md"], "NUEVO")
        self.assertNotIn("agents/sentinel.md", self.states(out))
        self.assertEqual(self.leftover_temps(), [])

    def test_f4t5_case32_four_aliases_dryrun_and_idempotence(self):
        files = self.f4t5_source()
        self.f4t5_config(ALIAS_FOUR)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([l for l in out.splitlines() if l.startswith("Alias:")],
                         ["Alias: atlas -> mapa (agents/mapa.md)", "Alias: forge -> dev (agents/dev.md)",
                          "Alias: scribe -> redactor (agents/redactor.md)",
                          "Alias: sentinel -> amigo-qa (agents/amigo-qa.md)"])
        st = self.states(out)
        for dest in ("agents/mapa.md", "agents/dev.md", "agents/redactor.md", "agents/amigo-qa.md"):
            self.assertEqual(st[dest], "NUEVO")
        for role in ("atlas", "forge", "scribe", "sentinel"):
            self.assertNotIn("agents/%s.md" % role, st)
        self.assertEqual(os.listdir(self.target), [self.CONFIG])
        self.install_ok()
        self.assert_alias_installed(files, 5, ALIAS_FOUR)
        # segunda corrida: todo IGUAL, estado intacto
        state_before = snapshot(self.target)[self.STATE]
        out, err = self.install_ok()
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
        self.assertEqual(snapshot(self.target)[self.STATE], state_before)

    def test_f4t5_case32_an_alias_for_a_role_outside_the_manifest_only_changes_the_texts(self):
        # Alias para un rol sin archivo en el manifiesto: se aplica a los textos y no hay archivo que renombrar.
        files = {k: v for k, v in ALIAS_SAMPLE.items() if k != "agents/sentinel.md"}
        self.f4t5_source(files)
        self.f4t5_config(ALIAS_ONE)
        self.install_ok()
        self.assert_alias_installed(files, 5, ALIAS_ONE)
        self.assertNotIn("agents/amigo-qa.md", self.f4_tree(self.target))
        self.assertIn(b"AMIGO-QA", read(self.target, "docs/agentes.md"))

    def test_f4t5_case33_only_name_description_and_body_change_and_hooks_is_untouched(self):
        files = self.f4t5_source()
        self.f4t5_config(ALIAS_FOUR)
        self.install_ok()
        for role in ("atlas", "forge", "scribe", "sentinel"):
            src = files["agents/%s.md" % role].decode("utf-8").split("\n")
            dst = read(self.target, "agents/%s.md" % ALIAS_FOUR[role])
            self.assertNotIn(b"\r", dst)
            self.assertTrue(dst.endswith(b"\n"))
            out = dst.decode("utf-8").split("\n")
            self.assertEqual(len(out), len(src))
            close = src.index("---", 1)
            self.assertEqual(out.index("---", 1), close)
            for i, (a, b) in enumerate(zip(src, out)):
                if a != b:
                    self.assertTrue(i > close or a.startswith(("name:", "description:")), (role, i, a, b))
            self.assertEqual(out[1:close].count("name: " + ALIAS_FOUR[role]), 1)
        # el bloque hooks: de sentinel, byte a byte (con el model: de dentro incluido)
        src = files["agents/sentinel.md"]
        dst = read(self.target, "agents/amigo-qa.md")
        block = ("\n".join(SENTINEL_HOOKS) + "\n").encode("ascii")
        self.assertIn(block, src)
        self.assertIn(block, dst)
        # las lineas de tools:, model: y color: del frontmatter, intactas
        for role in ("atlas", "forge", "scribe", "sentinel"):
            dst = read(self.target, "agents/%s.md" % ALIAS_FOUR[role])
            for line in (b"tools: Read, Grep\n", b"model: sonnet\n", b"color: blue\n"):
                self.assertIn(line, dst)

    def test_f4t5_case34_four_forms_and_word_boundary_in_literal_text(self):
        # Los bytes se comparan con la referencia y ademas con cadenas literales (no solo con la referencia).
        files = self.f4t5_source()
        table = {"forge": "dev", "scribe": "redactor"}
        self.f4t5_config(table)
        self.install_ok()
        self.assert_alias_installed(files, 5, table)
        rules = read(self.target, "rules/agentes.md").decode("utf-8")
        for needle in ("`dev`", "Dev (Sonnet): corregir", "| DEV | implementar |", "@agent-dev", "@agent-redactor",
                       "agents/dev.md", "`redactor`", "| REDACTOR | docs |"):
            self.assertIn(needle, rules)
        left = rules.replace("Sentinelé, ñforge, éSCRIBE y SCRIBEÁ", "")
        for needle in ("forge", "Forge", "FORGE", "agents/forge.md", "`scribe`", "SCRIBE |", "@agent-scribe"):
            self.assertNotIn(needle, left)
        # con scribe aliado, las palabras que lo contienen no se tocan
        redactor = read(self.target, "agents/redactor.md").decode("utf-8")
        self.assertIn("Quien escribe, describe, reescribe o sobrescribe; escriben. Describe. redactor.", redactor)
        self.assertIn("Sobrescribe y reescribe: igual.", rules)
        for broken in ("esredactor", "deredactor", "redactorn", "reredactor", "sobreredactor"):
            self.assertNotIn(broken, rules + redactor)
        # el agente forge: ruta de destino, forma Capitalizada y MAYUSCULAS
        body = read(self.target, "agents/dev.md").decode("utf-8")
        self.assertIn("Usa `dev`, Dev (Sonnet): tarea, @agent-dev, agents/dev.md y ~/.claude/agents/dev.md.", body)
        self.assertIn("Eres DEV.", body)

    def test_f4t5_case35_cross_references_and_files_that_name_no_aliased_role(self):
        files = self.f4t5_source()
        self.f4t5_config({"scribe": "redactor"})
        self.install_ok()
        self.assert_alias_installed(files, 5, {"scribe": "redactor"})
        # atlas, forge y sentinel no nombran a scribe: bytes del origen; name: intacto
        for role in ("atlas", "forge", "sentinel"):
            self.assertEqual(read(self.target, "agents/%s.md" % role), files["agents/%s.md" % role], role)
        self.assertIn(b"\nname: redactor\n", read(self.target, "agents/redactor.md"))
        # referencia cruzada: forge sin alias propio, atlas con alias
        shutil.rmtree(self.target)
        self.f4t5_config({"atlas": "mapa"})
        self.install_ok()
        self.assert_alias_installed(files, 5, {"atlas": "mapa"})
        forge = read(self.target, "agents/forge.md").decode("utf-8")
        self.assertIn("\nname: forge\n", forge)
        self.assertIn("description: Implements one unit of the MAPA plan.\n", forge)
        self.assertIn("Eres FORGE.", forge)
        self.assertEqual(read(self.target, "agents/scribe.md"), files["agents/scribe.md"])
        # un archivo que no nombra ningun rol con alias sale IGUAL en la segunda corrida
        out, err = self.install_ok()
        self.assertEqual(set(self.states(out).values()), {"IGUAL"})

    def f4t5_defects(self):
        """Variantes defectuosas de agents/forge.md (con alias en forge y sentinel)."""
        text = ALIAS_SAMPLE["agents/forge.md"].decode("utf-8")
        return {
            "sin name": text.replace("name: forge\n", ""),
            "name duplicado": text.replace("name: forge\n", "name: forge\nname: forge\n"),
            "name con otro valor": text.replace("name: forge\n", "name: otro\n"),
            "description multilinea": text.replace("description: Implements one unit of the ATLAS plan.\n",
                                                   "description: Implements one unit\n  of the ATLAS plan.\n"),
            "sin description": text.replace("description: Implements one unit of the ATLAS plan.\n", ""),
            "description duplicada": text.replace("tools:", "description: otra\ntools:"),
            "rol en tools": text.replace("tools: Read, Grep", "tools: Agent(sentinel), Read"),
            "rol en hooks": text.replace("tools: Read, Grep", "tools: Read\nhooks:\n  x: sentinel"),
            "sin cierre": text.replace("color: blue\n---\n", "color: blue\n"),
            "continuacion tras name": text.replace("name: forge\n", "name: forge\n  extra\n"),
            "color con CR oculto": text.replace("color: blue\n", "color: orange\rhooks: x\n"),
            "tools fuera de ASCII": text.replace("tools: Read, Grep", "tools: Read, Grép"),
        }

    def test_f4t5_case36_defective_frontmatter_exit1_in_both_modes_and_nothing_is_written(self):
        table = {"forge": "dev", "sentinel": "amigo-qa"}
        for label, text in self.f4t5_defects().items():
            with self.subTest(defect=label):
                files = dict(ALIAS_SAMPLE)
                files["agents/forge.md"] = text.encode("utf-8")
                self.assertIsNotNone(self.alias_transform_error(files, table), label)
                self.f4t5_source(files)
                self.f4t5_config(table)
                before = snapshot(self.target)
                listing = sorted(os.listdir(self.tmp))
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assert_quiet_failure(code, out, err, before, listing)
                    self.assertTrue(err.startswith(self.F4T5_MSG + "agents/forge.md: "), err)
                    self.assertTrue(err.strip().endswith(". No se escribio nada."), err)
                    self.assertNotIn("amigo-qa", err)
                    if label in ("rol en tools", "rol en hooks"):
                        self.assertIn("referencia a un rol en una linea del frontmatter", err)
                shutil.rmtree(self.target)

    def test_f4t5_case36_a_defect_in_a_file_without_its_own_alias_also_stops(self):
        # Con tabla efectiva no vacia los nueve agentes pasan por la transformacion: un defecto en uno sin alias propio
        # tambien detiene la instalacion (el mensaje nombra su ruta).
        files = dict(ALIAS_SAMPLE)
        files["agents/atlas.md"] = files["agents/atlas.md"].replace(b"name: atlas\n", b"")
        self.f4t5_source(files)
        self.f4t5_config(ALIAS_ONE)
        for mode in (["-DryRun"], []):
            code, out, err = self.run_install(*mode)
            self.assertEqual(code, 1, out + err)
            self.assertTrue(err.startswith(self.F4T5_MSG + "agents/atlas.md: "), err)
            self.assertEqual(os.listdir(self.target), [self.CONFIG])

    def test_f4t5_case36_agent_without_body_and_without_final_lf_installs_with_aliases(self):
        # Archivo que termina en el cierre --- sin LF final: no hay lineas tras el cierre, el cuerpo no se transforma.
        files = dict(ALIAS_SAMPLE)
        files["agents/atlas.md"] = b"---\nname: atlas\ndescription: Plans.\nmodel: opus\n---"
        self.assertIsNone(self.alias_transform_error(files, ALIAS_ONE))
        self.f4t5_source(files)
        self.f4t5_config(ALIAS_ONE)
        for mode in (["-DryRun"], []):
            code, out, err = self.run_install(*mode)
            self.assertEqual(code, 0, out + err)
        self.assert_alias_installed(files, 5, ALIAS_ONE)
        self.assertEqual(read(self.target, "agents/atlas.md"), files["agents/atlas.md"])

    def test_f4t5_case36_the_two_texts_have_no_frontmatter_rules(self):
        # rules/agentes.md y docs/agentes.md no tienen frontmatter: cualquier texto vale.
        files = dict(ALIAS_SAMPLE)
        files["rules/agentes.md"] = b"sin encabezado, forge y SENTINEL\n"
        self.f4t5_source(files)
        self.f4t5_config(ALIAS_ONE)
        self.install_ok()
        self.assert_alias_installed(files, 5, ALIAS_ONE)

    def test_f4t5_case37_a_defect_only_matters_with_aliases(self):
        for label, text in self.f4t5_defects().items():
            with self.subTest(defect=label):
                files = dict(ALIAS_SAMPLE)
                files["agents/forge.md"] = text.encode("utf-8")
                for cfg in (None, b"{}", b'{"aliases": {}}', b'{"aliases": {"forge": "forge", "sentinel": "sentinel"}}'):
                    self.f4t5_source(files)
                    if cfg is not None:
                        self.write_config(cfg)
                    out, err = self.install_ok()
                    self.assertNotIn("error", err)
                    self.assertNotIn("autocomprobacion", err)
                    for rel, data in files.items():
                        self.assertEqual(read(self.target, rel), data, rel)
                    self.assertNotIn("Alias:", out)
                    shutil.rmtree(self.target)

    def test_f4t5_case38_the_transformation_only_runs_with_a_non_empty_effective_table(self):
        marker = "[Console]::Out.WriteLine('ALIAS-LLAMADO ' + $Kind + ' ' + $Role)"
        self.f4t5_source()
        self.patch_script("function ConvertTo-AliasBytes", marker)
        for config, calls in ((None, 0), (b'{"level": 5}', 0), (b"{}", 0), (b'{"aliases": {}}', 0),
                              (b'{"aliases": {"forge": "forge"}}', 0), (b'{"level": 3, "aliases": {}}', 0),
                              (self.alias_config(ALIAS_ONE), 6), (self.alias_config(ALIAS_FOUR, level=3), 6)):
            with self.subTest(config=config):
                shutil.rmtree(self.target, ignore_errors=True)
                if config is not None:
                    self.write_config(config)
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 0, out + err)
                    called = [l for l in out.splitlines() if l.startswith("ALIAS-LLAMADO")]
                    self.assertEqual(len(called), calls)
                    if calls:
                        self.assertEqual(sorted(l.split()[1] for l in called), ["agent"] * 4 + ["text"] * 2)

    def test_f4t5_case39_self_check_catches_a_corrupted_result_in_both_modes(self):
        # $aliasResult se estropea justo despues de construirlo: la autocomprobacion detiene la instalacion con exit 1
        # y sin escribir nada. Cada variante toca algo distinto (cuerpo, name:, hooks:, numero de lineas, residuo...).
        variants = {
            "ultimo caracter": "$aliasResult[$aliasResult.Length - 2] = 88",
            "name": "$aliasResult = $latin1.GetBytes($latin1.GetString($aliasResult).Replace('name: amigo-qa', 'name: amigo-qb'))",
            "hooks": "$aliasResult = $latin1.GetBytes($latin1.GetString($aliasResult).Replace('hooks:', 'hookz:'))",
            "lineas": "$aliasResult = $latin1.GetBytes($latin1.GetString($aliasResult).Replace('Eres', 'x' + [char]10 + 'Eres'))",
            "residuo": "$aliasResult = $latin1.GetBytes($latin1.GetString($aliasResult).Replace('AMIGO-QA', 'SENTINEL'))",
            "description": "$aliasResult = $latin1.GetBytes($latin1.GetString($aliasResult).Replace('description: Runs', 'description:' + [char]10 + '  Runs'))",
        }
        for label, code_line in variants.items():
            with self.subTest(variant=label):
                self.f4t5_source()
                self.patch_script("$aliasResult = $latin1.GetBytes(", code_line)
                self.f4t5_config(ALIAS_ONE)
                before = snapshot(self.target)
                listing = sorted(os.listdir(self.tmp))
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assert_quiet_failure(code, out, err, before, listing)
                    self.assertIn("autocomprobacion", err)
                    self.assertTrue(err.startswith(self.F4T5_MSG), err)
                    self.assertTrue(err.strip().endswith(". No se escribio nada."), err)
                shutil.rmtree(self.target)
                shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))

    def test_f4t5_case39_self_check_also_covers_the_two_texts(self):
        # Solo archivos de texto (sin frontmatter): el recorrido en paralelo los pilla igual.
        files = {k: v for k, v in ALIAS_SAMPLE.items() if k.startswith(("rules", "docs", "hooks"))}
        self.f4t5_source(files)
        self.patch_script("$aliasResult = $latin1.GetBytes(", "$aliasResult[$aliasResult.Length - 2] = 88")
        self.f4t5_config(ALIAS_ONE)
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        code, out, err = self.run_install("-DryRun")
        self.assert_quiet_failure(code, out, err, before, listing)
        self.assertIn("autocomprobacion", err)
        self.assertTrue(err.startswith(self.F4T5_MSG), err)

    def test_f4t5_case40_crlf_and_high_bytes_give_the_same_result_as_lf(self):
        results = {}
        for crlf in (False, True):
            shutil.rmtree(self.target, ignore_errors=True)
            files = self.f4t5_source(crlf=crlf)
            self.f4t5_config(ALIAS_FOUR)
            self.install_ok()
            results[crlf] = self.f4_tree(self.target)
            self.assert_alias_installed(files, 5, ALIAS_FOUR)
        self.assertEqual(results[False], results[True])
        for rel, data in results[True].items():
            self.assertNotIn(b"\r", data, rel)
            data.decode("utf-8")
        # los bytes altos se conservan: la comilla angular y la letra acentuada siguen en su sitio
        rules = results[True]["rules/agentes.md"]
        self.assertIn("«AMIGO-QA sólo escribe tests»".encode("utf-8"), rules)
        self.assertEqual(rules.count("é".encode("utf-8")), ALIAS_SAMPLE["rules/agentes.md"].count("é".encode("utf-8")))

    def test_f4t5_case56_boundary_with_high_bytes_in_the_installer(self):
        files = self.f4t5_source()
        self.f4t5_config(ALIAS_ONE)
        self.install_ok()
        self.assert_alias_installed(files, 5, ALIAS_ONE)
        for rel in ("rules/agentes.md", "docs/agentes.md", "agents/amigo-qa.md"):
            text = read(self.target, rel).decode("utf-8")
            self.assertIn("«AMIGO-QA sólo escribe tests»", text, rel)
            self.assertNotIn("«SENTINEL", text, rel)
        for rel in ("rules/agentes.md", "agents/amigo-qa.md"):
            text = read(self.target, rel).decode("utf-8")
            # pegado a una letra acentuada no se reemplaza (antes y despues)
            self.assertIn("Sentinelé", text, rel)
            self.assertIn("ñforge", text, rel)
        self.assertIn("éSCRIBE y SCRIBEÁ", read(self.target, "rules/agentes.md").decode("utf-8"))
        # tras la apertura de interrogacion y entre raya y espacio, si se reemplaza
        shutil.rmtree(self.target)
        self.f4t5_config({"scribe": "redactor", "forge": "dev"})
        self.install_ok()
        rules = read(self.target, "rules/agentes.md").decode("utf-8")
        self.assertIn("¿redactor escribe o describe?", rules)
        docs = read(self.target, "docs/agentes.md").decode("utf-8")
        self.assertIn("«DEV, REDACTOR y ATLAS… dev — sentinel.", docs)
        # con forge y scribe aliados, pegados a una letra acentuada (antes y despues) siguen intactos
        self.assertIn("Sentinelé, ñforge, éSCRIBE y SCRIBEÁ no cambian.", rules)
        for broken in ("ñdev", "éREDACTOR", "REDACTORÁ"):
            self.assertNotIn(broken, rules)

    def test_f4t5_the_hook_and_other_files_are_never_transformed(self):
        files = self.f4t5_source()
        self.f4t5_config(ALIAS_FOUR)
        self.install_ok()
        self.assertEqual(read(self.target, "hooks/agent_guard.py"), files["hooks/agent_guard.py"])
        self.assertEqual(read(self.target, "agents/alfa.md"), files["agents/alfa.md"])
        state = json.loads(read(self.target, self.STATE))
        by_path = {f["path"]: f for f in state["files"]}
        self.assertEqual(by_path["hooks/agent_guard.py"]["written"], by_path["hooks/agent_guard.py"]["sha256"])
        self.assertEqual(by_path["agents/alfa.md"]["written"], by_path["agents/alfa.md"]["sha256"])
        self.assertEqual(by_path["hooks/agent_guard.py"]["dest"], "hooks/agent_guard.py")
        self.assertNotEqual(by_path["docs/agentes.md"]["written"], by_path["docs/agentes.md"]["sha256"])
        # ningun archivo nuevo fuera de los diez esperados
        self.assertEqual(sorted(self.f4_tree(self.target)), sorted(
            ["agents/mapa.md", "agents/dev.md", "agents/redactor.md", "agents/amigo-qa.md", "agents/alfa.md",
             "rules/agentes.md", "docs/agentes.md", "hooks/agent_guard.py", self.STATE, self.CONFIG]))

    def test_f4t5_alias_and_level_use_the_cell_of_the_role_not_the_destination(self):
        files = self.f4t5_source()
        table = {"atlas": "mapa", "sentinel": "amigo-qa"}
        self.f4t5_config(table, level=3)
        out, err = self.install_ok()
        self.assert_alias_installed(files, 3, table)
        mapa = read(self.target, "agents/mapa.md").decode("utf-8")
        self.assertIn("\nmodel: opus\n", mapa)
        self.assertIn("\neffort: medium\n", mapa)
        self.assertIn("\nname: mapa\n", mapa)
        lines = out.splitlines()
        self.assertIn("Ajuste: agents/mapa.md  model: opus  effort: medium", lines)
        self.assertIn("Ajuste: agents/amigo-qa.md  model: sonnet  effort: -", lines)
        self.assertEqual(len([l for l in lines if l.startswith("Ajuste:")]), 4)
        # el hooks: de sentinel sigue intacto con nivel y alias
        self.assertIn(("\n".join(SENTINEL_HOOKS) + "\n").encode("ascii"), read(self.target, "agents/amigo-qa.md"))

    # --- Fase 4, T6: alias con niveles, repositorio real y -DryRun (casos 41 a 46 del plan) ---

    F4T6_MODELS = {"atlas": "claude-fable-5-2", "forge": "sonnet", "sentinel": "sonnet", "scribe": "sonnet",
                   "scout": "sonnet", "oracle": "haiku", "auditor": "opus", "shield": "opus", "debugger": "opus"}
    F4T6_HOOKED = ("sentinel", "auditor", "shield", "debugger")
    F4T6_SCRIBE_WORDS = re.compile("escribe|escriben|describe|reescribe|sobrescribe", re.I)

    def f4t6_nine_sample(self):
        """Los nueve agentes (frontmatter de una linea por clave, los cuatro con guarda con su bloque hooks:, cuerpo con
        referencias cruzadas a otros roles), las reglas, la guia y el hook, como los de ALIAS_SAMPLE."""
        files = {}
        for role, model in self.F4T6_MODELS.items():
            lines = ["---", "name: " + role, "description: Rol " + role.upper() + " que avisa a FORGE y a SHIELD.",
                     "tools: Read, Grep", "model: " + model]
            if role in self.F4T6_HOOKED:
                lines += SENTINEL_HOOKS
            lines += ["color: blue", "---",
                      "Eres " + role.upper() + ". Habla con `forge`, Sentinel y @agent-atlas; «" + role.upper() +
                      " sólo escribe tests». scribe describe y escribe.\n"]
            files["agents/%s.md" % role] = "\n".join(lines).encode("utf-8")
        for rel in ("rules/agentes.md", "docs/agentes.md", "hooks/agent_guard.py"):
            files[rel] = ALIAS_SAMPLE[rel]
        return files

    def f4t6_cell(self, level, role):
        return lr.read_script_table()[(level, role)]

    def f4t6_prepare(self, files, table, level):
        """Origen nuevo con `files`, destino vacio y la configuracion de `table` y `level`."""
        self.f4t5_source(files)
        shutil.rmtree(self.target, ignore_errors=True)
        self.f4t5_config(table, level=level)

    def test_f4t6_case41_alias_and_level_together_levels_1_to_4(self):
        files = self.f4t6_nine_sample()
        table = dict(self.ALIAS_NINE)
        level_agents = lr.read_ps_list("LevelAgents")
        for level in (1, 2, 3, 4):
            with self.subTest(level=level):
                self.f4t6_prepare(files, table, level)
                out, err = self.install_ok()
                self.assert_alias_installed(files, level, table)
                lines = out.splitlines()
                for role in ar.roles():
                    dest = "agents/%s.md" % table[role]
                    data = read(self.target, dest)
                    self.assertFalse(os.path.exists(os.path.join(self.target, "agents", role + ".md")), role)
                    text = data.decode("utf-8")
                    front = text.split("\n---\n")[0]
                    if role in level_agents:
                        # la celda es la del ROL, no la del alias: model: y effort: del frontmatter, una vez cada uno
                        model, effort = self.f4t6_cell(level, role)
                        self.assertEqual(front.count("\nmodel: %s\n" % model), 1, (level, role))
                        if effort != "-":
                            self.assertEqual(front.count("\neffort: %s\n" % effort), 1, (level, role))
                        else:
                            self.assertNotIn("\neffort:", front)
                        self.assertIn("Ajuste: %s  model: %s  effort: %s" % (dest, model, effort), lines)
                    else:
                        # auditor, shield y debugger: modelo y hooks: del origen con cualquier alias
                        self.assertNotIn("Ajuste: " + dest, "\n".join(lines))
                        self.assertIn("\nmodel: %s\n" % self.F4T6_MODELS[role], text)
                        self.assertNotIn("\neffort:", front)
                    if role in self.F4T6_HOOKED:
                        self.assertIn(("\n".join(SENTINEL_HOOKS) + "\n").encode("ascii"), data, role)
                    self.assertIn("\nname: %s\n" % table[role], text)
                ajustes = [l for l in lines if l.startswith("Ajuste:")]
                self.assertEqual(len(ajustes), len(level_agents))
                for role in ar.roles():
                    self.assertFalse([l for l in ajustes if l.startswith("Ajuste: agents/%s.md " % role)], role)
                self.assertIn("Verificado: 12 archivo(s) escritos coinciden con lo esperado para el nivel %d y los alias."
                              % level, lines)
                self.assertEqual(read(self.target, "hooks/agent_guard.py"), files["hooks/agent_guard.py"])

    def test_f4t6_case41_alias_then_level_equals_level_then_alias(self):
        # Los dos ordenes de la referencia dan los mismos bytes, y son los que escribe el instalador.
        files = self.f4t6_nine_sample()
        table = dict(self.ALIAS_NINE)
        for level in (1, 4):
            with self.subTest(level=level):
                self.f4t6_prepare(files, table, level)
                self.install_ok()
                for role in lr.read_ps_list("LevelAgents"):
                    model, effort = self.f4t6_cell(level, role)
                    other = ar.transform_agent(lr.render_expected(files["agents/%s.md" % role], model, effort), role, table)
                    self.assertEqual(read(self.target, "agents/%s.md" % table[role]), other, (level, role))
                    self.assertEqual(alias_expected(files, table, level)["agents/%s.md" % role][1], other, (level, role))

    def test_f4t6_case41_a_level_change_with_aliases_keeps_the_role_cell(self):
        files = self.f4t6_nine_sample()
        table = dict(self.ALIAS_NINE)
        self.f4t6_prepare(files, table, 2)
        self.install_ok()
        self.f4t5_config(table, level=4)
        out, err = self.install_ok()
        self.assertIn("Nivel anterior: 2", out.splitlines())
        self.assert_alias_installed(files, 4, table)
        model, effort = self.f4t6_cell(4, "forge")
        self.assertIn("\nmodel: %s\n" % model, read(self.target, "agents/dev.md").decode("utf-8"))

    def f4t6_repo_files(self):
        manifest = json.loads(read(ROOT, "install-manifest.json"))
        return {f["path"]: read(ROOT, f["path"]) for f in manifest["files"]}

    def test_f4t6_case42_real_repository_nine_aliases_levels_5_and_3(self):
        files = self.f4t6_repo_files()
        self.assertEqual(len(files), 12)
        table = dict(self.ALIAS_NINE)
        texts = ["agents/%s.md" % r for r in ar.roles()] + ["rules/agentes.md", "docs/agentes.md"]
        for level in (5, 3):
            with self.subTest(level=level):
                self.f4t6_prepare(files, table, level)
                # el manifiesto del repositorio, no uno regenerado: el hook se verifica contra su hash
                shutil.copyfile(os.path.join(ROOT, "install-manifest.json"), os.path.join(self.src, "install-manifest.json"))
                manifest = json.loads(read(self.src, "install-manifest.json"))
                hook_sha = {f["path"]: f["sha256"] for f in manifest["files"]}["hooks/agent_guard.py"]
                out, err = self.install_ok()
                self.assertNotIn("error", err)
                self.assert_alias_installed(files, level, table)
                tree = self.f4_tree(self.target)
                tree.pop(self.CONFIG)
                self.assertEqual(len(tree), 13, sorted(tree))
                self.assertEqual(sorted(p for p in tree if p.startswith("agents/")),
                                 sorted("agents/%s.md" % a for a in table.values()))
                for role in ar.roles():
                    self.assertNotIn("agents/%s.md" % role, tree)
                # el hook: bytes y hash del manifiesto, sin transformar
                self.assertEqual(bm.canonical_sha256(tree["hooks/agent_guard.py"]), hook_sha)
                self.assertEqual(tree["hooks/agent_guard.py"], files["hooks/agent_guard.py"].replace(b"\r\n", b"\n"))
                # sin residuo: ningun nombre de rol en los once textos instalados salvo las subcadenas conocidas. Busqueda
                # simple, sin la regla de limite de palabra de la implementacion; tambien entre « y » (la guia)
                for rel in texts:
                    text = tree[ar.dest_for(rel, table)].decode("utf-8")
                    for role in ar.roles():
                        # assertFalse y no assertNotIn: si falla, no imprime el texto entero dos veces
                        self.assertFalse(role in self.F4T6_SCRIBE_WORDS.sub("", text).lower(), (rel, role))
                    # los roles entre comillas angulares son subcadenas del texto completo: el bucle de arriba ya los cubre
                # auditor, shield y debugger: frontmatter igual salvo name: y description:
                for role in ("auditor", "shield", "debugger"):
                    src = files["agents/%s.md" % role].decode("utf-8").replace("\r\n", "\n").split("\n")
                    dst = tree["agents/%s.md" % table[role]].decode("utf-8").split("\n")
                    close = src.index("---", 1)
                    self.assertEqual(dst.index("---", 1), close)
                    for i in range(1, close):
                        if not src[i].startswith(("name:", "description:")):
                            self.assertEqual(dst[i], src[i], (role, i))
                self.assertIn("Verificado: 12 archivo(s) escritos coinciden con lo esperado para el nivel %d y los alias."
                              % level, out.splitlines())

    def test_f4t6_case43_dryrun_with_aliases_lists_aliases_and_dest_rows_and_writes_nothing(self):
        files = self.f4t6_nine_sample()
        table = dict(self.ALIAS_NINE)
        self.f4t6_prepare(files, table, 3)
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(snapshot(self.target), before)
        self.assertEqual(sorted(os.listdir(self.tmp)), listing)
        self.assertEqual(os.listdir(self.target), [self.CONFIG])
        lines = out.splitlines()
        self.assertEqual([l for l in lines if l.startswith("Alias:")],
                         ["Alias: %s -> %s (agents/%s.md)" % (r, table[r], table[r]) for r in ar.roles()])
        st = self.states(out)
        for role in ar.roles():
            self.assertEqual(st["agents/%s.md" % table[role]], "NUEVO")
            self.assertNotIn("agents/%s.md" % role, st)
        self.assertEqual(len(st), 12)
        self.assertIn("Resumen: NUEVO=12 IGUAL=0 ACTUALIZAR=0 MODIFICADO=0 HUERFANO=0", lines)
        ajustes = [l for l in lines if l.startswith("Ajuste:")]
        self.assertEqual(len(ajustes), 6)
        for role in lr.read_ps_list("LevelAgents"):
            model, effort = self.f4t6_cell(3, role)
            self.assertIn("Ajuste: agents/%s.md  model: %s  effort: %s" % (table[role], model, effort), ajustes)
        self.assertNotIn("Copiado", out)
        self.assertNotIn("Verificado", out)
        # lo que muestra el simulacro es lo que despues hace la real: mismas lineas hasta el primer Copiado
        code2, out2, err2 = self.run_install()
        self.assertEqual(code2, 0, out2 + err2)
        plan = lambda text: [l for l in text.split("\nCopiado:", 1)[0].splitlines() if not l.startswith("Modo:")]
        self.assertEqual(plan(out), plan(out2))
        self.assert_alias_installed(files, 3, table)

    def test_f4t6_case44_verification_messages(self):
        files = self.f4t6_nine_sample()
        table = dict(self.ALIAS_NINE)
        cases = ((5, table, "lo esperado para el nivel 5 y los alias"),
                 (3, table, "lo esperado para el nivel 3 y los alias"),
                 (1, table, "lo esperado para el nivel 1 y los alias"),
                 # tabla efectiva vacia (alias igual al rol, o sin alias): los textos de hoy
                 (5, {"forge": "forge"}, "el manifiesto"), (3, {"forge": "forge"}, "lo esperado para el nivel 3"),
                 (5, {}, "el manifiesto"))
        for level, aliases, what in cases:
            with self.subTest(level=level, aliases=len(aliases), what=what):
                self.f4t6_prepare(files, aliases, level)
                out, err = self.install_ok()
                self.assertIn("Verificado: 12 archivo(s) escritos coinciden con %s." % what, out.splitlines())
                # Paso 7: bytes distintos de los esperados: exit 4 y el mismo texto
                self.f4t6_prepare(files, aliases, level)
                try:
                    self.patch_script("Write-Atomic $dest $outBytes[$rel] $existing", "$outBytes[$rel] = [byte[]]@(88)",
                                      before=True)
                    code, out, err = self.run_install()
                    self.assertEqual(code, 4, out + err)
                    self.assertIn("el hash del archivo escrito no coincide con %s\n" % what, err.replace("\r\n", "\n") + "\n")
                finally:
                    # restaura la copia aunque falle una asercion: sin esto las demas iteraciones fallan en cascada
                    shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))

    def test_f4t6_case45_post_verification_with_aliases_exit4(self):
        files = self.f4t6_nine_sample()
        table = dict(self.ALIAS_NINE)
        self.f4t6_prepare(files, table, 3)
        victim = os.path.join(self.target, "agents", "amigo-qa.md").replace("'", "''")
        self.patch_script("# Paso 8:", "[System.IO.File]::AppendAllText('%s', 'x')" % victim)
        code, out, err = self.run_install()
        self.assertEqual(code, 4, out + err)
        self.assertIn("la verificacion posterior fallo", err)
        failed = [l.strip() for l in err.split("la verificacion posterior fallo:", 1)[1].splitlines() if l.strip()]
        self.assertEqual(failed[:1], ["agents/amigo-qa.md"])
        self.assertNotIn("agents/sentinel.md", err)
        self.assertFalse(os.path.exists(os.path.join(self.target, self.STATE)))
        self.assertNotIn("Verificado", out)

    def test_f4t6_ajuste_names_the_dest_path_and_never_the_role_path(self):
        self.f4t6_prepare(self.f4t6_nine_sample(), {"forge": "dev", "scout": "explorador"}, 1)
        out, err = self.install_ok()
        lines = out.splitlines()
        model, effort = self.f4t6_cell(1, "forge")
        self.assertIn("Ajuste: agents/dev.md  model: %s  effort: %s" % (model, effort), lines)
        model, effort = self.f4t6_cell(1, "scout")
        self.assertIn("Ajuste: agents/explorador.md  model: %s  effort: %s" % (model, effort), lines)
        self.assertFalse([l for l in lines if l.startswith(("Ajuste: agents/forge.md", "Ajuste: agents/scout.md"))])
        self.assertEqual(len([l for l in lines if l.startswith("Ajuste:")]), 6)

    # Caso 46: salida sin alias, nivel 5, identica a la de antes de la fase. El golden se calculo con el install.ps1 de
    # antes de la Fase 4 (commit 9c33300) y estas mismas ayudas: por paso, codigo de salida, hash de stdout, hash de
    # stderr (con las rutas reemplazadas por <T>, <B>, <H> y <TMP>) y hash del arbol del destino y del respaldo.
    F4T6_GOLDEN = [
        ["simulacro", 0, "ce93ef3e3bb35424", "e3b0c44298fc1c14", "-", "-"],
        ["limpia", 0, "67a9f7511ccbfd75", "82b819d5c8b38503", "96eefc2b8f061bbe", "-"],
        ["repetida", 0, "953cf9224ec3bfac", "82b819d5c8b38503", "96eefc2b8f061bbe", "-"],
        ["modificado", 3, "55405763bec5d625", "b1556d3d3801c3ea", "a2cc21adae4f6a35", "-"],
        ["force", 0, "e45f06b6d68001b3", "82b819d5c8b38503", "96eefc2b8f061bbe", "60032c9b6c675ac3"],
        ["actualizar", 0, "3a3cce7654540f01", "82b819d5c8b38503", "00c9444b1dc4cb89", "7753155e2dae7724"],
        ["huerfano", 0, "148f83662d074178", "82b819d5c8b38503", "9511547705801bfe", "111a091266d0050c"],
        ["estado ilegible", 0, "30b266aec73c859e", "2b5b1a2f96879e6c", "9511547705801bfe", "-"],
        ["nivel 5 explicito", 0, "bc2370e30947d44a", "82b819d5c8b38503", "b113db7993f07848", "-"],
        ["origen con CRLF", 0, "bc2370e30947d44a", "82b819d5c8b38503", "b113db7993f07848", "-"],
    ]

    def f4t6_regression_steps(self):
        backups = []

        def norm(text):
            return f4t6_normalize_paths(
                text, [(b, "<B>") for b in backups] + [(self.target, "<T>"), (self.home, "<H>"), (self.tmp, "<TMP>")])

        def digest(text):
            return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

        def tree_digest(base):
            if not os.path.isdir(base):
                return "-"
            tree = {rel: hashlib.sha256(data).hexdigest()[:16] for rel, data in self.f4_tree(base).items()}
            return digest(json.dumps(tree, sort_keys=True))

        steps, raw = [], []

        def run(label, *args):
            backup = os.path.join(self.tmp, "respaldo%d" % len(backups))
            backups.append(backup)
            code, out, err = self.run_install("-BackupDir", backup, *args)
            raw.append((label, norm(out), norm(err)))
            steps.append([label, code, digest(norm(out)), digest(norm(err)), tree_digest(self.target), tree_digest(backup)])

        files = dict(SAMPLE)
        self.make_source(files)
        run("simulacro", "-DryRun")
        run("limpia")
        run("repetida")
        write(self.target, "agents/alfa.md", b"editado a mano\n")
        run("modificado")
        run("force", "-Force")
        files["agents/beta.md"] = b"agente beta 2\n"
        self.make_source(files)
        run("actualizar")
        files.pop("agents/beta.md")
        self.make_source(files)
        run("huerfano")
        write(self.target, "synclayer-manifest.json", b"no es json")
        run("estado ilegible")
        self.write_config(b'{"level": 5}')
        run("nivel 5 explicito")
        self.make_source(files, crlf=True)
        run("origen con CRLF")
        return steps, raw

    def test_f4t6_case46_level5_without_aliases_is_identical_to_before_the_phase(self):
        steps, raw = self.f4t6_regression_steps()
        message = "\n".join("--- %s\n%s%s" % item for item in raw)
        self.assertEqual(steps, self.F4T6_GOLDEN, message)
        # el golden no es trivial: cubre el simulacro, un exit 3, un respaldo, una actualizacion y un huerfano
        self.assertEqual([s[1] for s in steps], [0, 0, 0, 3, 0, 0, 0, 0, 0, 0])
        text = "\n".join(out for _label, out, _err in raw)
        for needle in ("HUERFANO", "MODIFICADO", "ACTUALIZAR", "Respaldo", "Nivel: 5"):
            self.assertIn(needle, text)
        self.assertNotIn("Alias:", text)
        self.assertNotIn("y los alias", text)

    # --- Fase 4, T7: cambios de alias, ediciones a mano, -Force y huerfanos (casos 47 a 53 del plan) ---

    F4T7_NOTE = "ya no estan en el manifiesto"
    F4T7_MODEL_HINT = "Si cambiaste model: o effort: a mano, usa synclayer-config.json."
    F4T7_ALIAS_HINT = "Si el archivo es un agente tuyo con el mismo nombre que un alias, elige otro alias."

    def f4t7_aviso(self, old, new):
        return ("aviso: %s es el nombre anterior de %s y sigue en el destino: no se borra. Mientras exista hay dos "
                "agentes activos con descripciones casi iguales y la delegacion puede elegir cualquiera. Quitalo a "
                "mano si ya no lo usas." % (old, new))

    def f4t7_avisos(self, err):
        return [l for l in err.splitlines() if "es el nombre anterior de" in l]

    def f4t7_config(self, aliases=None, level=None):
        obj = {}
        if level is not None:
            obj["level"] = level
        if aliases is not None:
            obj["aliases"] = aliases
        self.write_config(json.dumps(obj).encode("ascii"))

    def f4t7_start(self, aliases=None, level=None, files=None):
        """Origen de ALIAS_SAMPLE e instalacion real con esa configuracion."""
        files = self.f4t5_source(files)
        self.f4t7_config(aliases, level)
        self.install_ok()
        return files

    def f4t7_file(self, rel):
        """(bytes, mtime en ns) de un archivo del destino."""
        p = os.path.join(self.target, *rel.split("/"))
        with open(p, "rb") as f:
            data = f.read()
        return data, os.stat(p).st_mtime_ns

    def f4t7_changed(self, files, old_table, new_table, level=5, old_level=None):
        """Destinos que no cambian de ruta y cuyos bytes cambian de una tabla a otra, segun la referencia."""
        old = alias_expected(files, old_table, level if old_level is None else old_level)
        new = alias_expected(files, new_table, level)
        return {new[r][0] for r in files if old[r][0] == new[r][0] and old[r][1] != new[r][1]}

    def f4t7_by_state(self, out, state):
        return sorted(k for k, v in self.states(out).items() if v == state)

    def f4t7_assert_installed(self, files, level, aliases):
        """Como assert_alias_installed, sin exigir que falte agents/<rol>.md: en T7 el archivo anterior queda en disco
        (huerfano) y se comprueba aparte. Cada destino = referencia; estado = referencia (esquema 3 o 2)."""
        expected = alias_expected(files, aliases, level)
        hashes, dests = {}, {}
        for rel, (dest, data) in expected.items():
            self.assertEqual(read(self.target, dest), data, rel)
            hashes[rel] = bm.canonical_sha256(data)
            dests[rel] = dest
        manifest = read(self.src, "install-manifest.json")
        if any(d != r for r, d in dests.items()):
            want = ar.state_for3(manifest, hashes, level, dests)
        else:
            want = lr.state_for(manifest, hashes, level)
        self.assertEqual(read(self.target, self.STATE), want)

    def f4t7_assert_one_rename_orphan(self, out, err, old, new, exists=True):
        """Un solo huerfano, por cambio de nombre: sin la nota de stdout y con el aviso de stderr si el archivo existe."""
        self.assertEqual(self.f4t7_by_state(out, "HUERFANO"), [old], out)
        self.assertIn("HUERFANO=1", out)
        self.assertNotIn(self.F4T7_NOTE, out)
        self.assertNotIn("nota:", out)
        self.assertEqual(self.f4t7_avisos(err), [self.f4t7_aviso(old, new)] if exists else [], err)

    def test_f4t7_case47_s1_new_alias_over_an_intact_install_without_aliases(self):
        files = self.f4t7_start()
        old_tree = self.f4_tree(self.target)
        old_sentinel = self.f4t7_file("agents/sentinel.md")
        prev_state = read(self.target, self.STATE)
        self.assertIn(b'"schema": 2', prev_state)
        self.f4t7_config(ALIAS_ONE)
        changed = self.f4t7_changed(files, {}, ALIAS_ONE)
        self.assertTrue({"agents/atlas.md", "rules/agentes.md", "docs/agentes.md"} <= changed, changed)
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        for dry in (True, False):
            with self.subTest(dry_run=dry):
                if dry:
                    code, out, err = self.run_install("-DryRun")
                    self.assertEqual(code, 0, out + err)
                    self.assertEqual(snapshot(self.target), before)
                    self.assertFalse(os.path.exists(backup))
                else:
                    out, err = self.install_ok("-BackupDir", backup)
                st = self.states(out)
                self.assertEqual(st["agents/amigo-qa.md"], "NUEVO")
                self.assertEqual(st["agents/sentinel.md"], "HUERFANO")
                self.assertEqual(self.f4t7_by_state(out, "ACTUALIZAR"), sorted(changed))
                self.assertEqual(self.f4t7_by_state(out, "NUEVO"), ["agents/amigo-qa.md"])
                self.assertFalse(self.f4t7_by_state(out, "MODIFICADO"))
                self.f4t7_assert_one_rename_orphan(out, err, "agents/sentinel.md", "agents/amigo-qa.md")
        # corrida real: el archivo anterior intacto (bytes y mtime), estado a esquema 3, el anterior al respaldo
        self.assertEqual(self.f4t7_file("agents/sentinel.md"), old_sentinel)
        self.f4t7_assert_installed(files, 5, ALIAS_ONE)
        self.assertIn(b'"schema": 3', read(self.target, self.STATE))
        tree = self.f4_tree(backup)
        self.assertEqual(set(tree), set(changed) | {self.STATE})
        for rel in changed:
            self.assertEqual(tree[rel], old_tree[rel], rel)
        self.assertEqual(tree[self.STATE], prev_state)

    def test_f4t7_case47_s2_new_alias_over_a_foreign_file_is_modificado_and_force_backs_it_up(self):
        files = self.f4t7_start()
        self.f4t7_config(ALIAS_ONE)
        write(self.target, "agents/amigo-qa.md", b"agente ajeno del usuario\n")
        old_sentinel = self.f4t7_file("agents/sentinel.md")
        before = snapshot(self.target)
        for flags in ([], ["-DryRun"]):
            with self.subTest(flags=flags):
                code, out, err = self.run_install(*flags)
                self.assertEqual(code, 3, out + err)
                self.assertEqual(snapshot(self.target), before)
                self.assertEqual(self.f4t7_by_state(out, "MODIFICADO"), ["agents/amigo-qa.md"])
                self.assertNotIn("Copiado", out)
                self.assertIn(self.F4T7_ALIAS_HINT, err)
                self.assertTrue(err.rstrip().endswith(self.F4T7_MODEL_HINT), err)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(self.f4t7_by_state(out, "MODIFICADO"), ["agents/amigo-qa.md"])
        self.assertEqual(read(backup, "agents/amigo-qa.md"), b"agente ajeno del usuario\n")
        self.f4t7_assert_installed(files, 5, ALIAS_ONE)
        self.assertEqual(self.f4t7_file("agents/sentinel.md"), old_sentinel)
        self.assertNotIn("agents/sentinel.md", self.f4_tree(backup))

    def test_f4t7_case47_s3_changed_alias_orphans_the_previous_alias_file_only(self):
        # Se parte de S1: instalacion sin alias y luego ALIAS_ONE; agents/sentinel.md queda en disco.
        files = self.f4t7_start()
        self.f4t7_config(ALIAS_ONE)
        self.install_ok()
        old_sentinel = self.f4t7_file("agents/sentinel.md")
        old_amigo = self.f4t7_file("agents/amigo-qa.md")
        prev_state = read(self.target, self.STATE)
        table = {"sentinel": "tester"}
        self.f4t7_config(table)
        changed = self.f4t7_changed(files, ALIAS_ONE, table)
        self.assertTrue({"agents/atlas.md", "rules/agentes.md", "docs/agentes.md"} <= changed, changed)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        st = self.states(out)
        self.assertEqual(st["agents/tester.md"], "NUEVO")
        self.assertEqual(self.f4t7_by_state(out, "ACTUALIZAR"), sorted(changed))
        self.assertNotIn("agents/sentinel.md", st)
        self.f4t7_assert_one_rename_orphan(out, err, "agents/amigo-qa.md", "agents/tester.md")
        # el archivo del rol (de la instalacion sin alias) sigue en disco, no es destino ni destino previo: ni fila
        # HUERFANO ni aviso
        self.assertEqual(self.f4t7_file("agents/sentinel.md"), old_sentinel)
        self.assertNotIn("agents/sentinel.md", self.f4t7_by_state(out, "HUERFANO"))
        self.assertFalse([l for l in err.splitlines() if "agents/sentinel.md" in l], err)
        self.assertEqual(self.f4t7_file("agents/amigo-qa.md"), old_amigo)
        self.f4t7_assert_installed(files, 5, table)
        tree = self.f4_tree(backup)
        self.assertEqual(set(tree), set(changed) | {self.STATE})
        self.assertEqual(tree[self.STATE], prev_state)

    def test_f4t7_case47_s4_removed_alias_without_the_old_role_file_is_nuevo_and_state_goes_back_to_schema2(self):
        files = self.f4t7_start(ALIAS_ONE)
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "sentinel.md")))
        old_amigo = self.f4t7_file("agents/amigo-qa.md")
        prev_state = read(self.target, self.STATE)
        self.assertIn(b'"schema": 3', prev_state)
        self.f4t7_config(None)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        st = self.states(out)
        self.assertEqual(st["agents/sentinel.md"], "NUEVO")
        self.f4t7_assert_one_rename_orphan(out, err, "agents/amigo-qa.md", "agents/sentinel.md")
        self.assertEqual(self.f4t7_file("agents/amigo-qa.md"), old_amigo)
        self.f4t7_assert_installed(files, 5, {})
        self.assertNotIn(b'"dest"', read(self.target, self.STATE))
        self.assertEqual(self.f4_tree(backup)[self.STATE], prev_state)
        self.assertNotIn("agents/amigo-qa.md", self.f4_tree(backup))

    def test_f4t7_case47_s5_removed_alias_with_the_old_role_file_on_disk(self):
        # (a) los bytes son los que se escribirian: IGUAL. (b) distintos: no esta en prevByDest, MODIFICADO y exit 3.
        for edited in (False, True):
            with self.subTest(edited=edited):
                shutil.rmtree(self.target, ignore_errors=True)
                files = self.f4t7_start()
                self.f4t7_config(ALIAS_ONE)
                self.install_ok()
                if edited:
                    with open(os.path.join(self.target, "agents", "sentinel.md"), "ab") as f:
                        f.write(b"editado a mano\n")
                self.f4t7_config(None)
                old_amigo = self.f4t7_file("agents/amigo-qa.md")
                before = snapshot(self.target)
                code, out, err = self.run_install()
                if not edited:
                    self.assertEqual(code, 0, out + err)
                    self.assertEqual(self.states(out)["agents/sentinel.md"], "IGUAL")
                    self.f4t7_assert_one_rename_orphan(out, err, "agents/amigo-qa.md", "agents/sentinel.md")
                    self.f4t7_assert_installed(files, 5, {})
                else:
                    self.assertEqual(code, 3, out + err)
                    self.assertEqual(self.states(out)["agents/sentinel.md"], "MODIFICADO")
                    self.assertEqual(snapshot(self.target), before)
                    self.assertNotIn(self.F4T7_ALIAS_HINT, err)
                    self.assertTrue(err.rstrip().endswith(self.F4T7_MODEL_HINT), err)
                self.assertEqual(self.f4t7_file("agents/amigo-qa.md"), old_amigo)

    def test_f4t7_case48_s6_level_change_with_the_alias_already_installed(self):
        files = self.f4t7_start(ALIAS_ONE)
        e5 = alias_expected(files, ALIAS_ONE, 5)["agents/sentinel.md"][1]
        e1 = alias_expected(files, ALIAS_ONE, 1)["agents/sentinel.md"][1]
        self.assertNotEqual(e5, e1)
        self.f4t7_config(ALIAS_ONE, level=1)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        st = self.states(out)
        self.assertEqual(st["agents/amigo-qa.md"], "ACTUALIZAR")
        self.assertFalse(self.f4t7_by_state(out, "MODIFICADO"))
        self.assertFalse(self.f4t7_by_state(out, "HUERFANO"))
        self.assertIn("HUERFANO=0", out)
        self.assertEqual(self.f4t7_avisos(err), [])
        self.assertIn("Nivel anterior: 5", out)
        model, effort = lr.read_script_table()[(1, "sentinel")]
        self.assertIn("Ajuste: agents/amigo-qa.md  model: %s  effort: %s" % (model, effort), out.splitlines())
        self.assertEqual(read(self.target, "agents/amigo-qa.md"), e1)
        self.assertEqual(read(backup, "agents/amigo-qa.md"), e5)
        self.f4t7_assert_installed(files, 1, ALIAS_ONE)

    def test_f4t7_case48_s7_new_alias_and_level_change_at_once(self):
        files = self.f4t7_start()
        old_tree = self.f4_tree(self.target)
        old_sentinel = self.f4t7_file("agents/sentinel.md")
        prev_state = read(self.target, self.STATE)
        self.assertIn(b'"schema": 2', prev_state)
        self.f4t7_config(ALIAS_ONE, level=1)
        changed = self.f4t7_changed(files, {}, ALIAS_ONE, level=1, old_level=5)
        self.assertTrue({"agents/atlas.md", "rules/agentes.md", "docs/agentes.md"} <= changed, changed)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        st = self.states(out)
        self.assertEqual(st["agents/amigo-qa.md"], "NUEVO")
        self.assertEqual(self.f4t7_by_state(out, "ACTUALIZAR"), sorted(changed))
        self.assertFalse(self.f4t7_by_state(out, "MODIFICADO"))
        self.f4t7_assert_one_rename_orphan(out, err, "agents/sentinel.md", "agents/amigo-qa.md")
        self.assertIn("Nivel anterior: 5", out)
        model, effort = lr.read_script_table()[(1, "sentinel")]
        self.assertIn("Ajuste: agents/amigo-qa.md  model: %s  effort: %s" % (model, effort), out.splitlines())
        self.assertEqual(read(self.target, "agents/amigo-qa.md"), alias_expected(files, ALIAS_ONE, 1)["agents/sentinel.md"][1])
        self.assertEqual(self.f4t7_file("agents/sentinel.md"), old_sentinel)
        self.f4t7_assert_installed(files, 1, ALIAS_ONE)
        self.assertIn(b'"schema": 3', read(self.target, self.STATE))
        tree = self.f4_tree(backup)
        self.assertEqual(set(tree), set(changed) | {self.STATE})
        for rel in changed:
            self.assertEqual(tree[rel], old_tree[rel], rel)
        self.assertEqual(tree[self.STATE], prev_state)

    def test_f4t7_case49_s8_hand_edit_of_the_alias_file_is_modificado_and_force_backs_it_up(self):
        files = self.f4t7_start(ALIAS_ONE)
        path = os.path.join(self.target, "agents", "amigo-qa.md")
        with open(path, "ab") as f:
            f.write(b"editado a mano\n")
        edited = read(self.target, "agents/amigo-qa.md")
        before = snapshot(self.target)
        for flags in ([], ["-DryRun"]):
            with self.subTest(flags=flags):
                code, out, err = self.run_install(*flags)
                self.assertEqual(code, 3, out + err)
                self.assertEqual(snapshot(self.target), before)
                self.assertEqual(self.f4t7_by_state(out, "MODIFICADO"), ["agents/amigo-qa.md"])
                self.assertIn(self.F4T7_ALIAS_HINT, err)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-Force", "-BackupDir", backup)
        self.assertEqual(read(backup, "agents/amigo-qa.md"), edited)
        self.f4t7_assert_installed(files, 5, ALIAS_ONE)
        self.assertEqual(set(self.f4_tree(backup)), {"agents/amigo-qa.md"})

    def test_f4t7_case49_s9_reassignment_between_two_roles(self):
        files = self.f4t7_start(ALIAS_ONE)
        old_amigo = self.f4t7_file("agents/amigo-qa.md")
        old_forge = self.f4t7_file("agents/forge.md")
        table = {"sentinel": "tester", "forge": "amigo-qa"}
        self.f4t7_config(table)
        backup = os.path.join(self.tmp, "respaldo")
        out, err = self.install_ok("-BackupDir", backup)
        st = self.states(out)
        self.assertEqual(st["agents/amigo-qa.md"], "ACTUALIZAR")
        self.assertEqual(st["agents/tester.md"], "NUEVO")
        self.assertFalse(self.f4t7_by_state(out, "MODIFICADO"))
        self.f4t7_assert_one_rename_orphan(out, err, "agents/forge.md", "agents/amigo-qa.md")
        self.assertEqual(self.f4t7_file("agents/forge.md"), old_forge)
        self.assertEqual(read(backup, "agents/amigo-qa.md"), old_amigo[0])
        self.assertNotIn("agents/forge.md", self.f4_tree(backup))
        self.f4t7_assert_installed(files, 5, table)

    def test_f4t7_case49_s10_missing_or_unreadable_state_with_aliases_already_installed(self):
        for variant in ("ausente", "ilegible"):
            for edited in (False, True):
                with self.subTest(state=variant, edited=edited):
                    shutil.rmtree(self.target, ignore_errors=True)
                    files = self.f4t7_start()
                    self.f4t7_config(ALIAS_ONE)
                    self.install_ok()
                    if edited:
                        with open(os.path.join(self.target, "agents", "amigo-qa.md"), "ab") as f:
                            f.write(b"editado a mano\n")
                    state = os.path.join(self.target, self.STATE)
                    if variant == "ausente":
                        os.remove(state)
                    else:
                        with open(state, "wb") as f:
                            f.write(b"{no es json")
                    old_sentinel = self.f4t7_file("agents/sentinel.md")
                    code, out, err = self.run_install()
                    if edited:
                        self.assertEqual(code, 3, out + err)
                        self.assertEqual(self.f4t7_by_state(out, "MODIFICADO"), ["agents/amigo-qa.md"])
                    else:
                        self.assertEqual(code, 0, out + err)
                        self.assertEqual(set(self.states(out).values()), {"IGUAL"})
                    self.assertFalse(self.f4t7_by_state(out, "HUERFANO"))
                    self.assertNotIn(self.F4T7_NOTE, out)
                    self.assertEqual(self.f4t7_avisos(err), [])
                    self.assertEqual(self.f4t7_file("agents/sentinel.md"), old_sentinel)

    def test_f4t7_case49_s11_state_of_schema_1_or_2_and_a_new_alias_behaves_like_s1(self):
        for schema in (1, 2):
            with self.subTest(schema=schema):
                shutil.rmtree(self.target, ignore_errors=True)
                files = self.f4t5_source()
                for rel, data in files.items():
                    write(self.target, rel, data)
                self.write_state(files, schema=schema)
                self.f4t7_config(ALIAS_ONE)
                changed = self.f4t7_changed(files, {}, ALIAS_ONE)
                out, err = self.install_ok()
                st = self.states(out)
                self.assertEqual(st["agents/amigo-qa.md"], "NUEVO")
                self.assertEqual(self.f4t7_by_state(out, "ACTUALIZAR"), sorted(changed))
                self.assertFalse(self.f4t7_by_state(out, "MODIFICADO"))
                self.f4t7_assert_one_rename_orphan(out, err, "agents/sentinel.md", "agents/amigo-qa.md")
                self.f4t7_assert_installed(files, 5, ALIAS_ONE)
                self.assertEqual(read(self.target, "agents/sentinel.md"), files["agents/sentinel.md"])

    def test_f4t7_case49_s12_reinstalling_the_same_aliases_changes_nothing(self):
        files = self.f4t7_start()
        self.f4t7_config(ALIAS_FOUR)
        self.install_ok()
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        for flags in (["-DryRun"], []):
            with self.subTest(flags=flags):
                code, out, err = self.run_install(*flags)
                self.assertEqual(code, 0, out + err)
                self.assertFalse(self.f4t7_by_state(out, "HUERFANO"))
                self.assertEqual(set(self.states(out).values()), {"IGUAL"})
                self.assertNotIn("Respaldo:", out)
                self.assertNotIn("Copiado", out)
                self.assertEqual(self.f4t7_avisos(err), [])
                self.assertNotIn("nota:", out)
                self.assertEqual(snapshot(self.target), before)
                self.assertEqual(sorted(os.listdir(self.tmp)), listing)
        self.f4t7_assert_installed(files, 5, ALIAS_FOUR)

    def test_f4t7_case50_rename_orphan_warns_only_if_the_file_exists_and_is_never_touched(self):
        for exists in (True, False):
            for dry in (True, False):
                with self.subTest(file_exists=exists, dry_run=dry):
                    shutil.rmtree(self.target, ignore_errors=True)
                    shutil.rmtree(os.path.join(self.tmp, "respaldo"), ignore_errors=True)
                    self.f4t7_start()
                    if not exists:
                        os.remove(os.path.join(self.target, "agents", "sentinel.md"))
                    old = self.f4t7_file("agents/sentinel.md") if exists else None
                    self.f4t7_config(ALIAS_ONE)
                    backup = os.path.join(self.tmp, "respaldo")
                    flags = ["-DryRun"] if dry else []
                    code, out, err = self.run_install(*flags, "-BackupDir", backup)
                    self.assertEqual(code, 0, out + err)
                    self.f4t7_assert_one_rename_orphan(out, err, "agents/sentinel.md", "agents/amigo-qa.md", exists=exists)
                    if exists:
                        self.assertEqual(self.f4t7_file("agents/sentinel.md"), old)
                    else:
                        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "sentinel.md")))
                    if not dry:
                        self.assertNotIn("agents/sentinel.md", self.f4_tree(backup))
                    else:
                        self.assertFalse(os.path.exists(backup))

    def test_f4t7_case50_one_warning_per_file(self):
        # Dos huerfanos por cambio de nombre a la vez (sentinel y forge pasan a alias): un aviso por archivo.
        self.f4t7_start()
        self.f4t7_config({"sentinel": "amigo-qa", "forge": "dev"})
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(sorted(self.f4t7_avisos(err)),
                         sorted([self.f4t7_aviso("agents/sentinel.md", "agents/amigo-qa.md"),
                                 self.f4t7_aviso("agents/forge.md", "agents/dev.md")]))
        self.assertIn("HUERFANO=2", out)
        self.assertNotIn(self.F4T7_NOTE, out)

    def test_f4t7_case51_classic_orphan_keeps_the_note_and_has_no_warning(self):
        # Sin alias: nota por stdout, ningun aviso de cambio de nombre (la prueba existente fija el resto).
        self.make_source()
        old = dict(SAMPLE)
        old["agents/viejo.md"] = b"de una version anterior\n"
        self.write_state(old)
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertIn("nota: los HUERFANO los instalo una version anterior y ya no estan en el manifiesto. No se borran.",
                      out.splitlines())
        self.assertEqual(self.f4t7_avisos(err), [])
        self.assertEqual(err, "")

    def test_f4t7_case51_mixed_classic_and_rename_orphans_print_the_note_and_the_warning(self):
        files = self.f4t7_start()
        extra = dict(files)
        extra["agents/viejo.md"] = b"de una version anterior\n"
        self.write_state(extra)
        write(self.target, "agents/viejo.md", b"de una version anterior\n")
        self.f4t7_config(ALIAS_ONE)
        for flags in (["-DryRun"], []):
            with self.subTest(flags=flags):
                code, out, err = self.run_install(*flags)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.f4t7_by_state(out, "HUERFANO"), ["agents/sentinel.md", "agents/viejo.md"])
                self.assertIn("HUERFANO=2", out)
                self.assertEqual(out.count("nota: los HUERFANO los instalo una version anterior"), 1)
                self.assertEqual(self.f4t7_avisos(err), [self.f4t7_aviso("agents/sentinel.md", "agents/amigo-qa.md")])
                self.assertEqual(read(self.target, "agents/viejo.md"), b"de una version anterior\n")
                if not flags:
                    # el huerfano clasico tampoco se toco; el estado ya no los lista
                    self.assertNotIn(b"viejo", read(self.target, self.STATE))

    def test_f4t7_case51_classic_orphan_with_aliases_configured_and_unchanged(self):
        # Alias ya instalados y sin cambios, mas un huerfano clasico en el estado: nota, sin aviso de cambio de nombre.
        files = self.f4t7_start(ALIAS_ONE)
        extra = dict(files)
        extra["agents/viejo.md"] = b"de una version anterior\n"
        write(self.target, "agents/viejo.md", b"de una version anterior\n")
        self.write_state(extra, schema=3, dests={"agents/sentinel.md": "agents/amigo-qa.md"})
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.f4t7_by_state(out, "HUERFANO"), ["agents/viejo.md"])
        self.assertIn("nota: los HUERFANO los instalo una version anterior", out)
        self.assertEqual(self.f4t7_avisos(err), [])

    def test_f4t7_case52_exit3_adds_the_alias_phrase_only_when_a_modificado_is_in_an_alias_path(self):
        end = self.F4T7_MODEL_HINT
        files = self.f4t7_start(ALIAS_ONE)
        # (a) MODIFICADO en la ruta de un alias: frase de alias y, al final de todo, la del model:
        with open(os.path.join(self.target, "agents", "amigo-qa.md"), "ab") as f:
            f.write(b"editado a mano\n")
        code, out, err = self.run_install()
        self.assertEqual(code, 3, out + err)
        self.assertEqual(err.count(self.F4T7_ALIAS_HINT), 1, err)
        self.assertEqual(err.count(end), 1, err)
        self.assertTrue(err.rstrip().endswith(end), err)
        self.assertLess(err.index(self.F4T7_ALIAS_HINT), err.index(end))
        # (b) MODIFICADO solo en un archivo sin alias (forge no tiene alias), con alias configurados: sin la frase
        shutil.rmtree(self.target, ignore_errors=True)
        self.f4t7_start(ALIAS_ONE)
        with open(os.path.join(self.target, "agents", "forge.md"), "ab") as f:
            f.write(b"editado a mano\n")
        code, out, err = self.run_install()
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.f4t7_by_state(out, "MODIFICADO"), ["agents/forge.md"])
        self.assertNotIn(self.F4T7_ALIAS_HINT, err)
        self.assertTrue(err.rstrip().endswith(end), err)
        # (c) los dos a la vez: una sola vez cada frase
        with open(os.path.join(self.target, "agents", "amigo-qa.md"), "ab") as f:
            f.write(b"editado a mano\n")
        code, out, err = self.run_install()
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.f4t7_by_state(out, "MODIFICADO"), ["agents/amigo-qa.md", "agents/forge.md"])
        self.assertEqual(err.count(self.F4T7_ALIAS_HINT), 1, err)
        self.assertTrue(err.rstrip().endswith(end), err)
        # (d) sin alias: el mensaje es el de hoy
        shutil.rmtree(self.target, ignore_errors=True)
        self.f4t7_start()
        with open(os.path.join(self.target, "agents", "forge.md"), "ab") as f:
            f.write(b"editado a mano\n")
        code, out, err = self.run_install()
        self.assertEqual(code, 3, out + err)
        self.assertNotIn(self.F4T7_ALIAS_HINT, err)
        self.assertTrue(err.rstrip().endswith(end), err)

    def test_f4t7_case53_the_configuration_is_never_touched_nor_backed_up(self):
        files = self.f4t7_start()
        self.f4t7_config(ALIAS_ONE)
        config = os.path.join(self.target, self.CONFIG)
        raw = read(self.target, self.CONFIG)
        mtime = os.stat(config).st_mtime_ns
        backup = os.path.join(self.tmp, "respaldo")
        steps = (["-DryRun"], ["-BackupDir", backup], ["-Force", "-BackupDir", backup])
        for flags in steps:
            with self.subTest(flags=flags):
                code, out, err = self.run_install(*flags)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(read(self.target, self.CONFIG), raw)
                self.assertEqual(os.stat(config).st_mtime_ns, mtime)
        self.assertTrue(os.path.isdir(backup))
        self.assertNotIn(self.CONFIG, self.f4_tree(backup))
        # con un cambio de alias y -Force, otro respaldo: la configuracion tampoco entra
        self.f4t7_config({"sentinel": "tester"})
        raw = read(self.target, self.CONFIG)
        mtime = os.stat(config).st_mtime_ns
        backup2 = os.path.join(self.tmp, "respaldo2")
        self.install_ok("-Force", "-BackupDir", backup2)
        self.assertEqual(read(self.target, self.CONFIG), raw)
        self.assertEqual(os.stat(config).st_mtime_ns, mtime)
        self.assertNotIn(self.CONFIG, self.f4_tree(backup2))
        self.assertTrue(self.f4_tree(backup2))

    # --- Fase 4, cierre C1: bordes entre alias, nivel, estado esquema 3, -Force y configuracion invalida ---

    def test_f4c1_invalid_level_with_valid_aliases_exit1_in_both_modes_and_no_alias_line(self):
        for level in (0, 6, "3", None):
            with self.subTest(level=level):
                data = json.dumps({"level": level, "aliases": ALIAS_ONE}).encode("ascii")
                self.assert_config_rejected(data, "level debe ser un entero de 1 a 5")
                shutil.rmtree(self.target)

    def test_f4c1_invalid_alias_table_with_force_writes_and_backs_up_nothing(self):
        self.f4t7_start(ALIAS_ONE)
        path = os.path.join(self.target, "agents", "amigo-qa.md")
        with open(path, "ab") as f:
            f.write(b"editado a mano\n")
        self.f4t7_config({"sentinel": "Mal"}, level=2)
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        backup = os.path.join(self.tmp, "respaldo")
        for flags in (["-Force", "-BackupDir", backup], ["-Force", "-DryRun", "-BackupDir", backup]):
            with self.subTest(flags=flags):
                code, out, err = self.run_install(*flags)
                self.assert_quiet_failure(code, out, err, before, listing)
                self.assertIn(self.CONFIG_ERR + "el alias de sentinel ", err)
                self.assertNotIn("Alias:", out)
                self.assertFalse(os.path.exists(backup))

    def test_f4c1_schema3_state_with_mixed_levels_prints_no_previous_level(self):
        # Contrato de T5: `Nivel anterior:` solo si TODAS las entradas del estado previo tienen el mismo nivel.
        self.f4t7_start(ALIAS_ONE, level=3)
        state_path = os.path.join(self.target, self.STATE)
        data = json.loads(read(self.target, self.STATE))
        self.assertEqual(data["schema"], 3)
        self.assertEqual({e["level"] for e in data["files"]}, {3})
        self.f4t7_config(ALIAS_ONE, level=1)
        out, err = self.install_ok("-DryRun")
        self.assertIn("Nivel anterior: 3", out.splitlines())  # control: nivel uniforme
        data["files"][0]["level"] = 2
        with open(state_path, "wb") as f:
            f.write((json.dumps(data, indent=2) + "\n").encode("ascii"))
        for flags in (["-DryRun"], []):
            with self.subTest(flags=flags):
                code, out, err = self.run_install(*flags)
                self.assertNotEqual(code, 1, out + err)
                self.assertIn("Nivel: 1 (synclayer-config.json)", out.splitlines())
                self.assertNotIn("Nivel anterior", out)

    def test_f4c1_schema3_state_with_a_foreign_valid_dest_keeps_the_real_alias_file_igual(self):
        # Estado esquema 3 valido pero manipulado: dest apunta a otra ruta. El archivo de alias real, intacto y con los
        # bytes que se escribirian, es IGUAL; la ruta falsa es HUERFANO y nunca se toca (no existe, no hay aviso).
        files = self.f4t7_start(ALIAS_ONE)
        state_path = os.path.join(self.target, self.STATE)
        data = json.loads(read(self.target, self.STATE))
        moved = [e for e in data["files"] if e["path"] == "agents/sentinel.md"]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["dest"], "agents/amigo-qa.md")
        moved[0]["dest"] = "agents/otro.md"
        with open(state_path, "wb") as f:
            f.write((json.dumps(data, indent=2) + "\n").encode("ascii"))
        before = snapshot(self.target)
        out, err = self.install_ok("-DryRun")
        st = self.states(out)
        self.assertEqual(st["agents/amigo-qa.md"], "IGUAL")
        self.assertEqual(self.f4t7_by_state(out, "HUERFANO"), ["agents/otro.md"])
        self.assertEqual(self.f4t7_avisos(err), [])
        self.assertFalse(self.f4t7_by_state(out, "MODIFICADO"))
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(os.path.exists(os.path.join(self.target, "agents", "otro.md")))

    # --- Fase 5, T2: clave plans_dir de synclayer-config.json (lectura unica, validacion L1 a L5 y linea Planes:; casos
    # 10 a 17 del plan). Aun NO se aplica: una carpeta efectiva valida termina con la guarda temporal (T3 la retira junto
    # con test_f5t2_temporary_guard_*). El valor de plans_dir es entrada no confiable: nunca sale en un mensaje. ---

    F5_GUARD = "error: la carpeta de planes aun no se puede aplicar en esta version. No se escribio nada."
    F5_BAD_SET = ["a/b/c/d/e", "..", ".", "docs/../x", "/docs", "docs/", "docs//x", "Docs", "docs/Plans", "docs/plans.v2",
                  "docs plans", "a" * 32 + "/" + "b" * 32, "a" * 33, "nul", "docs/com1", "docs/lpt0", "docs/forge",
                  "atlas-planes", "docs/x-shield-y", "", "a\nb", "docs/`x`", "d\u00f3cs", "docs\\x", "docs:x",
                  "docs/plans\n", "docs/'x'", "-docs", "_docs", "docs/-x", "docs/a b", "docs/<x>", "docs/a|b", "docs/#x",
                  "\u202edocs", "x" * 65, "docs/plans/../..", "~/docs", "c:/docs"]
    F5_GOOD_SET = ["planes", "docs/planes", "a/b/c/d", "forge_x", "forges", "docs/plans-v2", "x" * 32, "a1/b2_c/d-e",
                   "docs/x/y", "com10", "docs/lpt10", "nulo", "docs/plans2"]

    def f5_config(self, plans_dir, level=None, aliases=None):
        obj = {}
        if level is not None:
            obj["level"] = level
        if aliases is not None:
            obj["aliases"] = aliases
        obj["plans_dir"] = plans_dir
        return json.dumps(obj).encode("ascii")

    def f5_prepare(self, config):
        self.make_source()
        self.write_config(config)
        return snapshot(self.target), sorted(os.listdir(self.tmp))

    def f5_expect_valid_guard(self, value, modes=(["-DryRun"], []), level=None):
        """Valor valido y efectivo: la linea Planes: y despues la guarda temporal, sin escribir nada."""
        before, listing = self.f5_prepare(self.f5_config(value, level=level))
        for mode in modes:
            with self.subTest(plans_dir=value[:40], mode=mode):
                code, out, err = self.run_install(*mode)
                self.assert_quiet_failure(code, out, err, before, listing)
                self.assertEqual(err.strip(), self.F5_GUARD)
                self.assertIn("Planes: " + value, out.splitlines())
                self.assertEqual(len([l for l in out.splitlines() if l.startswith("Planes:")]), 1)

    def f5_expect_invalid(self, value, modes=(["-DryRun"],)):
        expected = pr.validate_plans_dir(value)
        self.assertIsNotNone(expected, repr(value))
        before, listing = self.f5_prepare(self.f5_config(value))
        for mode in modes:
            with self.subTest(plans_dir=repr(value)[:40], mode=mode):
                code, out, err = self.run_install(*mode)
                self.assert_quiet_failure(code, out, err, before, listing)
                self.assertEqual(err.strip(), self.CONFIG_ERR + expected + ". No se escribio nada.")
                self.assertNotIn("Planes:", out)
                self.assertNotIn("Nivel:", out)

    def test_f5t2_case10_without_plans_dir_or_with_the_default_is_identical(self):
        # Caso 10: sin la clave y con "plans_dir": "docs/plans" dan stdout, stderr, destino y estado identicos byte a
        # byte; ninguna linea Planes: (la carpeta por defecto no es una carpeta efectiva).
        configs = (("base", b'{"level": 3}'), ("explicita", b'{"level": 3, "plans_dir": "docs/plans"}'),
                   ("sin nivel", b'{"plans_dir": "docs/plans"}'))
        for mode in (["-DryRun"], []):
            results = {}
            for name, cfg in configs:
                with self.subTest(case=name, mode=mode):
                    self.make_source()
                    self.write_config(cfg)
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 0, out + err)
                    self.assertNotIn("Planes:", out)
                    tree = self.tree(self.target)
                    tree.pop(self.CONFIG)
                    results[name] = (code, out, err, tree)
                    shutil.rmtree(self.target)
            self.assertEqual(results["explicita"], results["base"])
            self.assertEqual(results["sin nivel"][0], 0)
        # con alias y nivel a la vez
        for mode in (["-DryRun"], []):
            results = []
            for cfg in (b'{"level": 2, "aliases": {"forge": "dev"}}',
                        b'{"level": 2, "aliases": {"forge": "dev"}, "plans_dir": "docs/plans"}'):
                self.make_source()
                self.write_config(cfg)
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 0, out + err)
                tree = self.tree(self.target)
                tree.pop(self.CONFIG)
                results.append((code, out, err, tree))
                shutil.rmtree(self.target)
            self.assertEqual(results[0], results[1])
            self.assertNotIn("Planes:", results[1][1])

    def test_f5t2_case11_plans_dir_of_an_invalid_type_exit1_in_both_modes(self):
        variants = [("null", b"null"), ("entero", b"3"), ("cero", b"0"), ("decimal", b"1.5"), ("true", b"true"),
                    ("false", b"false"), ("lista vacia", b"[]"), ("lista", b'["docs", "planes"]'),
                    ("lista de una cadena", b'["docs/planes"]'), ("lista de listas", b"[[]]"), ("objeto", b'{"a": "b"}'),
                    ("objeto vacio", b"{}")]
        for name, value in variants:
            with self.subTest(case=name):
                self.assert_config_rejected(b'{"plans_dir": ' + value + b"}", "plans_dir debe ser texto")
                shutil.rmtree(self.target)
        before, listing = self.f5_prepare(b'{"plans_dir": ["docs/planes"]}')
        code, out, err = self.run_install()
        self.assert_quiet_failure(code, out, err, before, listing)
        self.assertEqual(err.strip(), self.CONFIG_ERR + pr.MSG_TYPE + ". No se escribio nada.")

    def test_f5t2_case12_invalid_values_match_the_reference_and_never_write(self):
        for value in self.F5_BAD_SET:
            self.f5_expect_invalid(value)
            shutil.rmtree(self.target)

    def test_f5t2_case12_invalid_values_exit1_in_the_real_mode_too(self):
        for value in ("Docs", "docs/forge", "nul", "", "a\nb", "docs/`x`", "d\u00f3cs", "a/b/c/d/e"):
            self.f5_expect_invalid(value, modes=([],))
            shutil.rmtree(self.target)

    def test_f5t2_case12_each_reason_is_reported_with_its_fixed_text(self):
        for value, motivo in (("Docs", pr.MSG_SHAPE), ("a/b/c/d/e", pr.MSG_SHAPE), ("x" * 65, pr.MSG_SHAPE),
                              ("a" * 32 + "/" + "b" * 32, pr.MSG_SHAPE), ("nul", pr.MSG_DEVICE),
                              ("docs/com1", pr.MSG_DEVICE), ("docs/forge", pr.MSG_ROLE), ("atlas-planes", pr.MSG_ROLE)):
            with self.subTest(value=value[:20]):
                self.assert_config_rejected(self.f5_config(value), motivo, modes=(["-DryRun"],))
                shutil.rmtree(self.target)
        self.assertEqual(pr.MSG_TYPE, "plans_dir debe ser texto")

    def test_f5t2_case12_valid_values_match_the_reference(self):
        for value in self.F5_GOOD_SET:
            self.assertIsNone(pr.validate_plans_dir(value), value)
            self.f5_expect_valid_guard(value, modes=(["-DryRun"],))
            shutil.rmtree(self.target)

    def test_f5t2_case12_a_hostile_value_never_reaches_stdout_or_stderr(self):
        values = ["SECRETO-PLANES-123", "secreto-planes!", "secreto/forge", "secreto/nul", "secreto/a/b/c/d",
                  "secreto\nsecreto", "secreto`x`", "SECRETO" + "x" * 60000, "secreto\u001b[31m", "\u202esecreto",
                  "secreto/" + "y" * 40, "secreto:x", "secreto\\x"]
        for value in values:
            with self.subTest(value=value[:25]):
                before, listing = self.f5_prepare(self.f5_config(value))
                code, out, err = self.run_install("-DryRun")
                self.assert_quiet_failure(code, out, err, before, listing)
                self.assertIn(self.CONFIG_ERR + "plans_dir ", err)
                for needle in ("secreto", "SECRETO", "y" * 20, "x" * 40):
                    self.assertNotIn(needle, out + err)
                self.assertLess(len(err), 500)
                shutil.rmtree(self.target)

    def test_f5t2_case13_similar_keys_are_still_unknown_keys(self):
        for key in ("plansDir", "Plans_dir", "plans", "PLANS_DIR", "plans_dir ", "plans-dir", "planes_dir"):
            with self.subTest(key=key):
                self.assert_config_rejected(json.dumps({key: "docs/planes"}).encode("ascii"),
                                            "clave desconocida: " + key + " (el instalador puede ser anterior al archivo)")
                shutil.rmtree(self.target)
        # la clave correcta junto a una parecida: sigue siendo desconocida la parecida
        self.assert_config_rejected(b'{"plans_dir": "docs/planes", "plansDir": "x"}', "clave desconocida: plansDir")

    def test_f5t2_case14_plans_dir_level_and_aliases_lines_come_in_order(self):
        files = dict(SAMPLE)
        files["agents/sentinel.md"] = agent_md("sentinel", "sonnet")
        self.make_source(files)
        self.write_config(self.f5_config("docs/planes", level=3, aliases={"sentinel": "amigo-qa", "forge": "dev"}))
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assert_quiet_failure(code, out, err, before, listing)
                lines = out.splitlines()
                self.assertTrue(lines[0].startswith("Destino: "), lines)
                self.assertEqual(lines[1:5], ["Nivel: 3 (synclayer-config.json)",
                                              "Alias: forge -> dev (agents/dev.md)",
                                              "Alias: sentinel -> amigo-qa (agents/amigo-qa.md)",
                                              "Planes: docs/planes"])
                self.assertEqual(len(lines), 5, lines)
                self.assertEqual(err.strip(), self.F5_GUARD)
        # `Planes:` no se confunde con una fila del plan (la expresion LINE de las pruebas)
        self.assertIsNone(LINE.match("Planes: docs/planes"))
        self.assertIsNone(LINE.match("Planes: docs/plans"))

    def test_f5t2_case14_the_planes_line_follows_the_previous_level_line(self):
        self.make_source()
        self.install_ok()
        self.write_config(self.f5_config("docs/planes", level=2))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(out.splitlines()[1:4], ["Nivel: 2 (synclayer-config.json)", "Nivel anterior: 5",
                                                 "Planes: docs/planes"])

    def test_f5t2_temporary_guard_valid_effective_values_end_with_exit1_and_write_nothing(self):
        # Guarda temporal de la Fase 5 (T2): se retira en T3 junto con esta prueba.
        for value in ("docs/planes", "planes", "a/b/c/d", "docs/plans-v2", "x" * 32):
            self.f5_expect_valid_guard(value)
            shutil.rmtree(self.target)
        self.f5_expect_valid_guard("docs/planes", level=3)
        shutil.rmtree(self.target)
        # con -Force y un destino editado a mano tampoco se escribe ni se respalda
        self.make_source()
        self.install_ok()
        write(self.target, "agents/alfa.md", b"editado a mano\n")
        self.write_config(self.f5_config("docs/planes"))
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        for mode in (["-Force"], ["-Force", "-DryRun"]):
            code, out, err = self.run_install(*mode)
            self.assert_quiet_failure(code, out, err, before, listing)
            self.assertEqual(err.strip(), self.F5_GUARD)
            self.assertFalse([n for n in os.listdir(self.tmp) if "backup" in n or "respaldo" in n])

    def test_f5t2_temporary_guard_does_not_apply_to_the_default_folder(self):
        for mode in (["-DryRun"], []):
            self.make_source()
            self.write_config(b'{"plans_dir": "docs/plans"}')
            code, out, err = self.run_install(*mode)
            self.assertEqual(code, 0, out + err)
            self.assertNotIn("error", err)
            self.assertNotIn("Planes:", out)
            shutil.rmtree(self.target)

    def test_f5t2_case15_an_invalid_plans_dir_writes_and_backs_up_nothing_with_a_valid_state(self):
        self.make_source()
        self.install_ok()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        write(self.target, "agents/beta.md", b"editado a mano\n")
        self.write_config(self.f5_config("Docs/Forge"))
        before = snapshot(self.target)
        listing = sorted(os.listdir(self.tmp))
        for mode in (["-DryRun"], [], ["-Force"]):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assert_quiet_failure(code, out, err, before, listing)
                self.assertEqual(err.strip(), self.CONFIG_ERR + pr.MSG_SHAPE + ". No se escribio nada.")
                self.assertNotIn("Respaldo", out)
                self.assertFalse([n for n in os.listdir(self.tmp) if "backup" in n or "respaldo" in n])

    def test_f5t2_case15_alias_and_plans_errors_at_once_give_a_single_error_the_alias_one(self):
        cfg = json.dumps({"aliases": {"forge": "Dev"}, "plans_dir": "Docs/Forge"}).encode("ascii")
        before, listing = self.f5_prepare(cfg)
        for mode in (["-DryRun"], []):
            code, out, err = self.run_install(*mode)
            self.assert_quiet_failure(code, out, err, before, listing)
            self.assertEqual(err.strip(), self.CONFIG_ERR + "el alias de forge solo admite a-z, 0-9, _ y -, empieza por "
                                          "letra y tiene hasta 64 caracteres. No se escribio nada.")
            self.assertEqual(len([l for l in err.splitlines() if l.strip()]), 1, err)
            self.assertNotIn("plans_dir", err)
        # alias valido y carpeta invalida: el error es el de la carpeta y no sale ninguna linea Alias:
        cfg = json.dumps({"aliases": {"forge": "dev"}, "plans_dir": "Docs"}).encode("ascii")
        self.write_config(cfg)
        before = snapshot(self.target)
        code, out, err = self.run_install("-DryRun")
        self.assert_quiet_failure(code, out, err, before, listing)
        self.assertEqual(err.strip(), self.CONFIG_ERR + pr.MSG_SHAPE + ". No se escribio nada.")
        self.assertNotIn("Alias:", out)
        # alias invalido y carpeta valida y efectiva: el error es el del alias, no la guarda
        cfg = json.dumps({"aliases": {"forge": "Dev"}, "plans_dir": "docs/planes"}).encode("ascii")
        self.write_config(cfg)
        before = snapshot(self.target)
        code, out, err = self.run_install("-DryRun")
        self.assert_quiet_failure(code, out, err, before, listing)
        self.assertIn("el alias de forge", err)
        self.assertNotIn("carpeta de planes", err)

    def test_f5t2_case16_a_repeated_plans_dir_key_in_windows_powershell_5_1_last_one_wins(self):
        # Comportamiento medido de ConvertFrom-Json de 5.1 (como con level y aliases): sin error; gana la ultima
        # aparicion. Un valor invalido anterior queda descartado; uno invalido posterior manda.
        for data, expect in ((b'{"plans_dir": "docs/uno", "plans_dir": "docs/dos"}', "Planes: docs/dos"),
                             (b'{"plans_dir": "docs/dos", "plans_dir": "docs/uno"}', "Planes: docs/uno"),
                             (b'{"plans_dir": "Docs", "plans_dir": "docs/uno"}', "Planes: docs/uno"),
                             (b'{"plans_dir": 3, "plans_dir": "docs/uno"}', "Planes: docs/uno")):
            with self.subTest(data=data):
                self.make_source()
                self.write_config(data)
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertEqual(err.strip(), self.F5_GUARD)
                self.assertEqual([l for l in out.splitlines() if l.startswith("Planes:")], [expect])
                shutil.rmtree(self.target)
        # ultimo valido igual a docs/plans: sin carpeta efectiva
        self.make_source()
        self.write_config(b'{"plans_dir": "docs/uno", "plans_dir": "docs/plans"}')
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("Planes:", out)
        # ultimo invalido: manda
        self.write_config(b'{"plans_dir": "docs/uno", "plans_dir": "Docs"}')
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(err.strip(), self.CONFIG_ERR + pr.MSG_SHAPE + ". No se escribio nada.")

    def test_f5t2_case16_the_type_key_is_rejected_anywhere_even_in_a_value_that_would_be_valid(self):
        # 5.1 descarta __type en silencio: el instalador lo rechaza antes. "a__type" pasaria L2, pero contiene __type:
        # limite documentado (la clave desconocida nombra __type, nunca el valor).
        for data in (b'{"plans_dir": {"__type": "x"}}', b'{"__type": "x", "plans_dir": "docs/planes"}',
                     b'{"plans_dir": "docs/a__type"}', b'{"plans_dir": "docs/a\\u005f\\u005ftype"}',
                     b'{"plans_dir": "docs/planes", "__t\\u0079pe": "x"}'):
            with self.subTest(data=data):
                self.assert_config_rejected(data, "clave desconocida: __type")
                shutil.rmtree(self.target)
        self.assertIsNone(pr.validate_plans_dir("docs/a__type"))

    def test_f5t2_second_read_of_the_config_is_detected_by_behaviour(self):
        # Lectura unica: tras la lectura se reescribe la configuracion; el resultado debe reflejar la PRIMERA lectura.
        path = None
        for later, why in (('{"plans_dir": "Docs"}', "invalida"), ('{}', "sin clave"), ('{"plans_dir": "docs/otra"}', "otra"),
                           ('{"plans_dir": "docs/plans"}', "la de por defecto")):
            with self.subTest(later=why):
                self.make_source()
                shutil.copyfile(SCRIPT, os.path.join(self.src, "install.ps1"))
                path = self.write_config(self.f5_config("docs/planes"))
                self.patch_script("$level = [int](Read-LevelConfig $configPath)",
                                  "[System.IO.File]::WriteAllText('%s', '%s')" % (path.replace("'", "''"), later))
                self.write_config(self.f5_config("docs/planes"))
                code, out, err = self.run_install("-DryRun")
                self.assertEqual(code, 1, out + err)
                self.assertEqual([l for l in out.splitlines() if l.startswith("Planes:")], ["Planes: docs/planes"])
                self.assertEqual(err.strip(), self.F5_GUARD)
                shutil.rmtree(self.target)

    def test_f5t2_case17_the_config_is_never_written_backed_up_or_listed(self):
        # Bytes y mtime de synclayer-config.json iguales tras -DryRun, instalacion y -Force, con carpeta por defecto,
        # efectiva (guarda) e invalida; no aparece en el respaldo. T4 repetira el caso con la carpeta aplicada.
        for value in ("docs/plans", "docs/planes", "Docs"):
            with self.subTest(plans_dir=value):
                self.make_source()
                self.install_ok()
                write(self.target, "agents/alfa.md", b"editado a mano\n")
                path = self.write_config(self.f5_config(value))
                old = os.stat(path).st_mtime_ns - 5_000_000_000
                os.utime(path, ns=(old, old))
                before = snapshot(self.target)[self.CONFIG]
                backup = os.path.join(self.tmp, "respaldo-f5")
                for mode in (["-DryRun"], ["-BackupDir", backup], ["-Force", "-BackupDir", backup]):
                    self.run_install(*mode)
                    self.assertEqual(snapshot(self.target)[self.CONFIG], before)
                found = []
                for dirpath, _dirs, files in os.walk(backup):
                    found += [f for f in files if f == self.CONFIG]
                self.assertEqual(found, [])
                shutil.rmtree(self.target)
                shutil.rmtree(backup, ignore_errors=True)

    def test_f5t2_config_size_limit_with_plans_dir(self):
        head = b'{"plans_dir": "docs/plans"}'
        limit = 65536
        self.make_source()
        self.write_config(head + b" " * (limit - len(head)))
        out, err = self.install_ok("-DryRun")
        self.assertNotIn("Planes:", out)
        shutil.rmtree(self.target)
        self.assert_config_rejected(head + b" " * (limit + 1 - len(head)), "supera 65536 bytes")


def f4t6_normalize_paths(text, pairs):
    """Reemplaza cada ruta por su etiqueta, tal cual y en la forma escapada por Format-Safe de install.ps1 (todo lo
    que no es ASCII imprimible sale como \\uXXXX en minusculas, por unidad UTF-16). Con rutas ASCII las dos formas
    coinciden."""
    for path, label in pairs:
        units = path.encode("utf-16-le")
        escaped = "".join(
            chr(c) if 0x20 <= c <= 0x7E else "\\u%04x" % c
            for c in (int.from_bytes(units[i:i + 2], "little") for i in range(0, len(units), 2)))
        text = text.replace(path, label)
        if escaped != path:
            text = text.replace(escaped, label)
    return text


class F4T6NormalizeCases(unittest.TestCase):
    def test_f4t6_normalize_paths_ascii_unchanged_and_escaped_non_ascii_replaced(self):
        ascii_path = "C:\\Temp\\abc"
        self.assertEqual(f4t6_normalize_paths("Destino: %s fin" % ascii_path, [(ascii_path, "<T>")]), "Destino: <T> fin")
        path = "C:\\Users\\Jos\u00e9 \U0001F600\\tmp"
        escaped = "C:\\Users\\Jos\\u00e9 \\ud83d\\ude00\\tmp"
        self.assertNotEqual(path, escaped)
        text = "Destino: %s\nraw: %s\notro: %s-x" % (escaped, path, escaped)
        self.assertEqual(f4t6_normalize_paths(text, [(path, "<TMP>")]), "Destino: <TMP>\nraw: <TMP>\notro: <TMP>-x")


def _make_class(label, exe, reason):
    cls = type("Install" + label, (InstallCases, unittest.TestCase), {"exe": exe, "label": label})
    return unittest.skipIf(exe is None, reason)(cls)


class ShellAvailability(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "en Windows powershell.exe es obligatorio")
    def test_windows_powershell_exists_on_windows(self):
        # Sin esto, un equipo Windows sin powershell.exe saltaria todas las pruebas en silencio.
        self.assertIsNotNone(POWERSHELL, "powershell.exe no esta en el PATH: no se probo install.ps1")


_none = not (POWERSHELL or PWSH)
InstallWindowsPowerShell = _make_class(
    "WindowsPowerShell", POWERSHELL, NO_SHELL if _none else "powershell no esta en el PATH")
InstallPwsh = _make_class(
    "Pwsh", PWSH, NO_SHELL if _none else PWSH_SKIP)

if __name__ == "__main__":
    unittest.main()
