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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_manifest as bm  # noqa: E402
import levels_ref as lr  # noqa: E402

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

    def write_state(self, files, schema=2, written=None, level=5):
        """Estado previo en el destino, el de una instalacion anterior con esos archivos. schema=1: copia
        del manifiesto (instalador de la Fase 1); schema=2: el estado nuevo, con `written` (por defecto el
        hash del origen) y `level`."""
        old = os.path.join(self.tmp, "viejo")
        for rel, data in files.items():
            write(old, rel, data)
        manifest = manifest_for(old, sorted(files))
        if schema == 1:
            data = manifest.encode("ascii")
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
        # el estado final depende del valor que gana, y un 1 a 4 sigue topando con la guarda.
        self.make_source()
        self.write_config(b'{"level": 3, "level": 5}')
        out, err = self.install_ok("-DryRun")
        self.assertIn("Nivel: 5 (synclayer-config.json)", out.splitlines())
        self.write_config(b'{"level": 5, "level": 3}')
        code, out, err = self.run_install("-DryRun")
        self.assertEqual(code, 1, out + err)
        self.assertIn("error: el nivel 3 aun no se puede aplicar en esta version.", err)

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

    def test_t3_valid_level_1_to_4_is_stopped_by_the_temporary_guard(self):
        # Guarda temporal de T3: T4 la retira junto con esta prueba. Ningun commit acepta un nivel que no aplica.
        for level in (1, 2, 3, 4):
            with self.subTest(level=level):
                self.make_source()
                self.write_config(('{"level": %d}' % level).encode("ascii"))
                before = snapshot(self.target)
                listing = sorted(os.listdir(self.tmp))
                for mode in (["-DryRun"], []):
                    code, out, err = self.run_install(*mode)
                    self.assertEqual(code, 1, out + err)
                    self.assertIn("error: el nivel %d aun no se puede aplicar en esta version." % level, err.splitlines())
                    self.assertNotIn("Copiado", out)
                    self.assertEqual(snapshot(self.target), before)
                    self.assertEqual(sorted(os.listdir(self.tmp)), listing)
                shutil.rmtree(self.target)

    def test_t3_level_read_reaches_the_state_when_the_temporary_guard_is_patched_out(self):
        # La guarda temporal impide un nivel 1 a 4 real; sin ella, el nivel leido va al estado (campo level
        # de cada entrada) y los archivos siguen siendo los del origen. T4 sustituye esta prueba.
        for level in (1, 3, 4):
            with self.subTest(level=level):
                self.make_source()
                path = os.path.join(self.src, "install.ps1")
                with open(path, "rb") as f:
                    text = f.read().decode("ascii")
                guard = "Stop-Install 1 ('error: el nivel ' + $level + ' aun no se puede aplicar en esta version.')"
                self.assertEqual(text.count(guard), 1)
                with open(path, "wb") as f:
                    f.write(text.replace(guard, "$null = 0").encode("ascii"))
                self.write_config(('{"level": %d}' % level).encode("ascii"))
                out, err = self.install_ok()
                self.assertIn("Nivel: %d (synclayer-config.json)" % level, out.splitlines())
                self.assert_state(level)
                for rel, data in SAMPLE.items():
                    self.assertEqual(read(self.target, rel), data)
                shutil.rmtree(self.target)
                shutil.copyfile(SCRIPT, path)

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
        self.patch_script("Write-Atomic $dest $canonSrc[$rel] $existing",
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
