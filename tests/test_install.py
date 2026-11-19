"""Pruebas de install.ps1 (T3: validacion, plan y -DryRun; T4: respaldo, copia, verificacion y estado).

Lanzan el script con subprocess (sin shell, con timeout) sobre powershell.exe y/o pwsh.
Nunca usan el destino por defecto: todas pasan -Target a una carpeta temporal.

Cobertura de interpretes (decision tomada para el plan, 3.6): pwsh 7 no esta instalado en el
equipo de desarrollo ni se va a instalar. El requisito "una ejecucion sin saltos" se cumple con
Windows PowerShell 5.1. La clase de pwsh queda opcional: se salta con motivo claro cuando no
esta, y la compatibilidad con pwsh 7 es NO VERIFICADA hasta que alguien la corra. En Windows la
falta de powershell.exe es un FALLO (ShellAvailability), no un salto silencioso.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_manifest as bm  # noqa: E402

SCRIPT = os.path.join(ROOT, "install.ps1")
POWERSHELL = shutil.which("powershell")
PWSH = shutil.which("pwsh")
NO_SHELL = "no hay powershell.exe ni pwsh en el PATH: pruebas de install.ps1 omitidas"
PWSH_SKIP = "pwsh no esta en el PATH: compatibilidad con pwsh 7 NO verificada en este equipo"
TIMEOUT = 120


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

    def test_allowed_pattern_matches_generator(self):
        text = self.raw.decode("ascii")
        m = re.search(r"^\$AllowedPattern = '(.*)'$", text, re.M)
        self.assertIsNotNone(m, "no se encontro $AllowedPattern en install.ps1")
        ps_pattern = m.group(1)
        self.assertTrue(ps_pattern.endswith(r"\z"))
        self.assertNotIn(r"\Z", ps_pattern)
        # Python usa \Z para lo que .NET llama \z; el resto debe ser identico.
        self.assertEqual(ps_pattern[:-2] + r"\Z", bm.ALLOWED.pattern)


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

    def run_install(self, *args, target=True):
        cmd = [self.exe, "-NoProfile", "-NonInteractive"]
        if os.name == "nt":
            cmd += ["-ExecutionPolicy", "Bypass"]
        cmd += ["-File", os.path.join(self.src, "install.ps1")]
        if target:
            cmd += ["-Target", self.target]
        cmd += list(args)
        env = dict(os.environ)
        drive, tail = os.path.splitdrive(self.home)
        env.update({"USERPROFILE": self.home, "HOME": self.home,
                    "HOMEDRIVE": drive, "HOMEPATH": tail or self.home})
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

    def write_state(self, files):
        """Estado previo en el destino: manifiesto de una instalacion anterior con esos archivos."""
        old = os.path.join(self.tmp, "viejo")
        for rel, data in files.items():
            write(old, rel, data)
        write(self.target, "synclayer-manifest.json", manifest_for(old, sorted(files)).encode("ascii"))

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
             ("con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9")]
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

    def assert_same_exit(self, expected, *args, **kw):
        respaldo = os.path.join(self.tmp, "respaldo")
        for extra in ([], ["-BackupDir", respaldo]):
            for mode in (["-DryRun"], []):
                with self.subTest(mode=mode, extra=extra):
                    code, out, err = self.run_install(*(mode + extra + list(args)), **kw)
                    self.assertEqual(code, expected, out + err)
        self.assertFalse(os.path.exists(respaldo))

    def test_target_that_is_a_file_exit1(self):
        self.make_source()
        write(self.tmp, "destino", b"soy un archivo")
        self.assert_same_exit(1)
        self.assertEqual(read(self.tmp, "destino"), b"soy un archivo")

    def test_intermediate_folder_that_is_a_file_exit1(self):
        self.make_source()
        write(self.target, "agents", b"soy un archivo")
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertIn("agents", err)
        self.assert_same_exit(1)

    def test_target_below_a_file_exit1(self):
        self.make_source()
        write(self.tmp, "destino", b"soy un archivo")
        self.target = os.path.join(self.target, "sub")
        self.assert_same_exit(1)

    def test_destination_that_is_a_folder_exit1(self):
        self.make_source()
        os.makedirs(os.path.join(self.target, "agents", "alfa.md"))
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertIn("es una carpeta", err)
        self.assert_same_exit(1)

    @unittest.skipUnless(os.name == "nt", "los proveedores del registro solo existen en Windows")
    def test_non_filesystem_provider_exit1(self):
        self.make_source()
        self.target = "HKCU:\\Software\\SyncLayerPruebaInexistente"
        self.assert_same_exit(1)

    def test_default_backup_is_absolute_sibling_of_target(self):
        self.make_source()
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 0, out + err)
        m = re.search(r"^Respaldo: (.*)$", out, re.M)
        self.assertIsNotNone(m, out)
        backup = m.group(1).strip()
        self.assertTrue(os.path.isabs(backup), backup)
        self.assertRegex(backup, re.escape(self.target) + r"-backup-\d{8}-\d{6}$")

    def test_relative_backup_dir_is_resolved_to_absolute(self):
        self.make_source()
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

    def install_ok(self, *args):
        code, out, err = self.run_install(*args)
        self.assertEqual(code, 0, out + err)
        return out, err

    def leftover_temps(self):
        found = []
        for dirpath, _dirs, files in os.walk(self.target):
            found += [os.path.join(dirpath, f) for f in files if f.endswith(".tmp")]
        return found

    def patch_script(self, after_line, code):
        """Inserta codigo PowerShell en la COPIA del script de prueba, tras la linea que empieza igual."""
        path = os.path.join(self.src, "install.ps1")
        with open(path, "rb") as f:
            lines = f.read().decode("ascii").split("\n")
        idx = [i for i, l in enumerate(lines) if l.strip().startswith(after_line)]
        self.assertEqual(len(idx), 1, after_line)
        lines.insert(idx[0] + 1, code)
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
        self.assertEqual(read(self.target, "synclayer-manifest.json"),
                         read(self.src, "install-manifest.json"))
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
        self.install_ok()
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"alfa 2\n"
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_source(files)
        out, err = self.install_ok("-BackupDir", os.path.join(self.tmp, "respaldo"))
        copied = [l.split(": ", 1)[1].strip() for l in out.splitlines() if l.startswith("Copiado: ")]
        self.assertEqual(copied, ["hooks/agent_guard.py", "agents/alfa.md"])

    def test_case4_update_creates_verifiable_backup(self):
        self.make_source()
        self.install_ok()
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
        self.assertEqual(read(self.target, "synclayer-manifest.json"),
                         read(self.src, "install-manifest.json"))
        self.assertIn(backup, out)
        self.assertEqual(self.leftover_temps(), [])

    def test_case4_default_backup_dir_is_created_next_to_target(self):
        self.make_source()
        self.install_ok()
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
        self.install_ok()
        before = {rel: os.stat(os.path.join(self.target, *rel.split("/"))).st_mtime_ns for rel in foreign}
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        backup = os.path.join(self.tmp, "respaldo")
        self.install_ok("-BackupDir", backup)
        for rel, data in foreign.items():
            p = os.path.join(self.target, *rel.split("/"))
            self.assertEqual(read(self.target, rel), data)
            self.assertEqual(os.stat(p).st_mtime_ns, before[rel])
            self.assertFalse(os.path.exists(os.path.join(backup, *rel.split("/"))))

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
        self.assertEqual(read(self.target, "synclayer-manifest.json"),
                         read(self.src, "install-manifest.json"))
        for rel in SAMPLE:
            self.assertEqual(os.stat(os.path.join(self.target, *rel.split("/"))).st_mtime_ns, before[rel])
        self.assertEqual(sorted(os.listdir(self.tmp)), ["destino", "home", "origen"])

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
        self.install_ok()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        backup = os.path.join(self.tmp, "respaldo")
        write(backup, "agents/alfa.md", b"respaldo anterior")
        before_t, before_b = snapshot(self.target), snapshot(backup)
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*(mode + ["-BackupDir", backup]))
                self.assertEqual(code, 1, out + err)
                self.assertIn("ya existe el respaldo", err)
                self.assertEqual(snapshot(backup), before_b)
                self.assertEqual(snapshot(self.target), before_t)

    def test_backup_dir_that_is_a_file_exit1_in_both_modes(self):
        self.make_source()
        self.install_ok()
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

    def test_real_run_altered_source_exit2_writes_nothing(self):
        self.make_source()
        write(self.src, "agents/beta.md", b"alterado\n")
        code, out, err = self.run_install("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 2, out + err)
        self.assertIn("agents/beta.md", err)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["home", "origen"])

    def test_real_run_modified_without_force_exit3_writes_nothing(self):
        self.make_source()
        self.install_ok()
        self.update_source("agents/alfa.md", b"alfa nueva\n")
        write(self.target, "agents/beta.md", b"editado a mano\n")
        before = snapshot(self.target)
        backup = os.path.join(self.tmp, "respaldo")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 3, out + err)
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(os.path.exists(backup))

    def test_real_run_target_validation_same_exit_as_dryrun(self):
        self.make_source()
        write(self.tmp, "destino", b"soy un archivo")
        for mode in (["-DryRun"], []):
            with self.subTest(mode=mode):
                code, out, err = self.run_install(*mode)
                self.assertEqual(code, 1, out + err)

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

    @unittest.skipUnless(os.name == "nt", "el atributo de solo lectura bloquea el reemplazo solo en Windows")
    def test_copy_failure_mid_run_exit4_keeps_backup_and_hook_intact(self):
        self.make_source()
        self.install_ok()
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"alfa 2\n"
        files["agents/beta.md"] = b"beta 2\n"
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_source(files)
        self.make_readonly("agents/beta.md")           # bloquea el reemplazo de beta
        backup = os.path.join(self.tmp, "respaldo")
        old_state = read(self.target, "synclayer-manifest.json")
        code, out, err = self.run_install("-BackupDir", backup)
        self.assertEqual(code, 4, out + err)
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
        self.install_ok()
        files = dict(SAMPLE)
        files["agents/alfa.md"] = b"alfa 2\n"
        files["hooks/agent_guard.py"] = b"print('guard 2')\n"
        self.make_source(files)
        self.make_readonly("hooks/agent_guard.py")
        code, out, err = self.run_install("-BackupDir", os.path.join(self.tmp, "respaldo"))
        self.assertEqual(code, 4, out + err)
        self.assertIn("No se escribio ningun archivo del destino", err)
        self.assertEqual(read(self.target, "hooks/agent_guard.py"), SAMPLE["hooks/agent_guard.py"])
        self.assertEqual(read(self.target, "agents/alfa.md"), SAMPLE["agents/alfa.md"])
        self.assertEqual(self.leftover_temps(), [])

    def test_force_overwrites_modified_with_backup(self):
        # Minimo de -Force en T4: la copia real respalda y sobrescribe (el resto de la semantica es T5).
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
