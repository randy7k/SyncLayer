import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_manifest as bm  # noqa: E402

GIT = shutil.which("git")

GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")


def clean_env():
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}

TWELVE = [
    "agents/atlas.md",
    "agents/auditor.md",
    "agents/debugger.md",
    "agents/forge.md",
    "agents/oracle.md",
    "agents/scout.md",
    "agents/scribe.md",
    "agents/sentinel.md",
    "agents/shield.md",
    "docs/agentes.md",
    "hooks/agent_guard.py",
    "rules/agentes.md",
]


RESERVED = ["agents/" + n + ".md" for n in
            ("con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9")]


class CanonicalHash(unittest.TestCase):
    def test_crlf_equals_lf(self):
        self.assertEqual(bm.canonical_sha256(b"a\r\nb"), bm.canonical_sha256(b"a\nb"))

    def test_lone_cr_changes_hash(self):
        self.assertNotEqual(bm.canonical_sha256(b"a\rb"), bm.canonical_sha256(b"a\nb"))
        self.assertNotEqual(bm.canonical_sha256(b"a\rb"), bm.canonical_sha256(b"ab"))

    def test_substitution_is_single_pass(self):
        self.assertEqual(bm.canonical_sha256(b"a\r\r\nb"), hashlib.sha256(b"a\r\nb").hexdigest())

    def test_empty_known_value(self):
        self.assertEqual(
            bm.canonical_sha256(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_lowercase_hex_64(self):
        h = bm.canonical_sha256(b"x")
        self.assertEqual(len(h), 64)
        self.assertEqual(h, h.lower())

    def test_matches_sha256_of_lf_bytes(self):
        self.assertEqual(bm.canonical_sha256(b"a\r\nb\r\n"), hashlib.sha256(b"a\nb\n").hexdigest())

    def test_bom_not_stripped(self):
        self.assertNotEqual(bm.canonical_sha256(b"\xef\xbb\xbfa"), bm.canonical_sha256(b"a"))


class Allowed(unittest.TestCase):
    def test_accepts_twelve(self):
        for p in TWELVE:
            self.assertTrue(bm.ALLOWED.match(p), p)

    def test_rejects_others(self):
        for p in [
            "docs/brand/x.md",
            "agents/x.txt",
            "agents/sub/x.md",
            "../x",
            "hooks/otro.ps1",
            "settings.json",
            "C:/x",
            "agents/X.md",
            "agents/a.md\n",
            "rules/otro.md",
            "docs/agentes.md/x",
        ] + RESERVED:
            self.assertIsNone(bm.ALLOWED.match(p), repr(p))

    def test_reserved_lookalikes_accepted(self):
        for p in ["agents/console.md", "agents/com10.md", "agents/com0.md", "agents/lpt.md",
                  "agents/nul-x.md", "agents/auxiliar.md"]:
            self.assertTrue(bm.ALLOWED.match(p), p)


class Render(unittest.TestCase):
    def sample(self):
        return {
            "schema": 1,
            "algorithm": "sha256",
            "eol": "lf",
            "files": [{"path": "agents/atlas.md", "sha256": "0" * 64}],
        }

    def test_deterministic_ascii_lf_final_newline(self):
        a = bm.render(self.sample())
        self.assertEqual(a, bm.render(self.sample()))
        a.encode("ascii")
        self.assertNotIn("\r", a)
        self.assertTrue(a.endswith("}\n"))
        self.assertFalse(a.endswith("\n\n"))

    def test_indent_two_and_roundtrip(self):
        a = bm.render(self.sample())
        self.assertIn('\n  "schema": 1,', a)
        self.assertEqual(json.loads(a), self.sample())

    def test_non_ascii_escaped(self):
        m = self.sample()
        m["files"][0]["path"] = "agents/\u00e1.md"
        a = bm.render(m)
        a.encode("ascii")
        self.assertIn("\\u00e1", a)

    def test_key_order_preserved(self):
        a = bm.render(self.sample())
        self.assertLess(a.index('"schema"'), a.index('"algorithm"'))
        self.assertLess(a.index('"algorithm"'), a.index('"eol"'))
        self.assertLess(a.index('"eol"'), a.index('"files"'))
        self.assertLess(a.index('"path"'), a.index('"sha256":'))


class BuildManifest(unittest.TestCase):
    def test_build_from_temp_dir(self):
        with tempfile.TemporaryDirectory(prefix="sync layer ", ignore_cleanup_errors=True) as d:
            os.makedirs(os.path.join(d, "agents"))
            with open(os.path.join(d, "agents", "b.md"), "wb") as f:
                f.write(b"one\r\ntwo\r\n")
            with open(os.path.join(d, "agents", "a.md"), "wb") as f:
                f.write(b"x")
            m = bm.build_manifest(d, ["agents/b.md", "agents/a.md"])
        self.assertEqual(m["schema"], 1)
        self.assertEqual(m["algorithm"], "sha256")
        self.assertEqual(m["eol"], "lf")
        self.assertEqual([e["path"] for e in m["files"]], ["agents/a.md", "agents/b.md"])
        self.assertEqual(m["files"][1]["sha256"], hashlib.sha256(b"one\ntwo\n").hexdigest())
        self.assertEqual(m["files"][0]["sha256"], hashlib.sha256(b"x").hexdigest())

    def test_rejects_path_outside_allowed(self):
        with tempfile.TemporaryDirectory(prefix="sync layer ", ignore_cleanup_errors=True) as d:
            with self.assertRaises(bm.ManifestError):
                bm.build_manifest(d, ["settings.json"])

    def test_rejects_duplicates(self):
        with tempfile.TemporaryDirectory(prefix="sync layer ", ignore_cleanup_errors=True) as d:
            os.makedirs(os.path.join(d, "agents"))
            with open(os.path.join(d, "agents", "a.md"), "wb") as f:
                f.write(b"x")
            with self.assertRaises(bm.ManifestError):
                bm.build_manifest(d, ["agents/a.md", "agents/a.md"])


@unittest.skipIf(GIT is None, "git no esta en el PATH: pruebas de managed_files omitidas")
class GitRepo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="sync layer ", ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run([GIT, *args], cwd=self.root, env=clean_env(), check=True,
                              timeout=60, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def put(self, rel, data=b"x", add=True):
        p = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        if add:
            self.git("add", "--", rel)

    def test_lists_sorted_and_filtered(self):
        for rel in ["rules/agentes.md", "hooks/agent_guard.py", "docs/agentes.md",
                    "agents/zeta.md", "agents/alfa.md"]:
            self.put(rel)
        self.put("docs/otro.md")
        self.put("README.md")
        self.put("tests/t.py")
        self.assertEqual(
            bm.managed_files(self.root),
            ["agents/alfa.md", "agents/zeta.md", "docs/agentes.md",
             "hooks/agent_guard.py", "rules/agentes.md"],
        )

    def test_untracked_ignored(self):
        self.put("agents/a.md")
        self.put("agents/b.md", add=False)
        self.assertEqual(bm.managed_files(self.root), ["agents/a.md"])

    def test_disallowed_under_agents_fails(self):
        self.put("agents/a.md")
        self.put("agents/notas.txt")
        with self.assertRaises(bm.ManifestError) as cm:
            bm.managed_files(self.root)
        self.assertIn("agents/notas.txt", str(cm.exception))

    def test_disallowed_under_hooks_and_rules_fail(self):
        for rel in ["hooks/otro.ps1", "rules/otro.md", "agents/sub/x.md"]:
            with self.subTest(rel=rel):
                self.put(rel)
                with self.assertRaises(bm.ManifestError):
                    bm.managed_files(self.root)
                self.git("rm", "-q", "-f", "--", rel)

    def test_main_write_and_check(self):
        self.put("agents/a.md", b"hola\r\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bm.main(["--check", "--root", self.root]), 1)
            self.assertFalse(os.path.exists(os.path.join(self.root, "install-manifest.json")))
            self.assertEqual(bm.main(["--root", self.root]), 0)
            self.assertEqual(bm.main(["--check", "--root", self.root]), 0)
        path = os.path.join(self.root, "install-manifest.json")
        with open(path, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(json.loads(raw)["files"][0]["path"], "agents/a.md")
        self.put("agents/a.md", b"cambio\n", add=False)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bm.main(["--check", "--root", self.root]), 1)

    def test_check_failure_message_has_regen_command(self):
        self.put("agents/a.md")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(bm.main(["--check", "--root", self.root]), 1)
        self.assertIn("Regeneralo con: python -B tools/build_manifest.py", err.getvalue())

    def test_not_a_git_repo_becomes_manifest_error(self):
        with tempfile.TemporaryDirectory(prefix="sync layer ", ignore_cleanup_errors=True) as d:
            # El temporal podria estar dentro de un repo git: el techo corta la busqueda al padre.
            ceiling = {"GIT_CEILING_DIRECTORIES": os.path.dirname(os.path.realpath(d))}
            with mock.patch.dict(os.environ, ceiling):
                with self.assertRaises(bm.ManifestError) as cm:
                    bm.managed_files(d)
        self.assertIn("git ls-files fallo", str(cm.exception))

    def test_check_tolerates_crlf_manifest(self):
        self.put("agents/a.md")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bm.main(["--root", self.root]), 0)
        path = os.path.join(self.root, "install-manifest.json")
        with open(path, "rb") as f:
            raw = f.read()
        with open(path, "wb") as f:
            f.write(raw.replace(b"\n", b"\r\n"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bm.main(["--check", "--root", self.root]), 0)

    def test_main_fails_on_disallowed(self):
        self.put("agents/notas.txt")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bm.main(["--root", self.root]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "install-manifest.json")))

    def test_main_rejects_unknown_arg(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bm.main(["--nope"]), 1)

    def test_filter_drops_tracked_path_under_allowed_file(self):
        # docs/agentes.md/x entra por el pathspec de git, no esta bajo agents/, rules/ ni hooks/,
        # asi que solo el filtro final por ALLOWED lo deja fuera.
        self.put("agents/a.md")
        self.put("docs/agentes.md/x")
        self.assertEqual(bm.managed_files(self.root), ["agents/a.md"])

    def test_empty_result_fails(self):
        self.put("README.md")
        with self.assertRaises(bm.ManifestError) as cm:
            bm.managed_files(self.root)
        self.assertIn("ningun archivo gestionado", str(cm.exception))

    def test_main_fails_on_empty_result(self):
        self.put("README.md")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bm.main(["--root", self.root]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "install-manifest.json")))

    def test_main_fails_on_empty_subfolder_root(self):
        self.put("agents/a.md")
        sub = os.path.join(self.root, "sub")
        os.makedirs(sub)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bm.main(["--root", sub]), 1)
        self.assertFalse(os.path.exists(os.path.join(sub, "install-manifest.json")))

    def test_ignores_git_env_variables(self):
        self.put("agents/a.md")
        with mock.patch.dict(os.environ, {
            "GIT_DIR": os.path.join(ROOT, ".git"),
            "GIT_WORK_TREE": ROOT,
            "GIT_INDEX_FILE": os.path.join(ROOT, ".git", "index"),
        }):
            self.assertEqual(bm.managed_files(self.root), ["agents/a.md"])

    def test_missing_root_is_not_reported_as_missing_git(self):
        missing = os.path.join(self.root, "no existe")
        with self.assertRaises(bm.ManifestError) as cm:
            bm.managed_files(missing)
        self.assertNotIn("PATH", str(cm.exception))
        self.assertIn("raiz no existe", str(cm.exception))

    def test_timeout_becomes_manifest_error(self):
        with mock.patch.object(bm.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("git", 60)):
            with self.assertRaises(bm.ManifestError):
                bm.managed_files(self.root)

    def test_non_utf8_path_becomes_manifest_error(self):
        fake = subprocess.CompletedProcess([], 0, stdout=b"100644 " + b"a" * 40 + b" 0\tagents/\xff.md\0")
        with mock.patch.object(bm.subprocess, "run", return_value=fake):
            with self.assertRaises(bm.ManifestError):
                bm.managed_files(self.root)

    def test_symlink_entry_rejected(self):
        # Se inyecta la entrada con update-index: no hace falta poder crear un symlink en disco.
        self.put("README.md")
        sha = subprocess.run([GIT, "hash-object", "-w", "--stdin"], cwd=self.root, env=clean_env(),
                             input=b"target", check=True, timeout=60, stdout=subprocess.PIPE
                             ).stdout.decode().strip()
        self.git("update-index", "--add", "--cacheinfo", "120000," + sha + ",agents/a.md")
        with self.assertRaises(bm.ManifestError) as cm:
            bm.managed_files(self.root)
        self.assertIn("120000", str(cm.exception))
        self.assertIn("agents/a.md", str(cm.exception))


class ParseLsFiles(unittest.TestCase):
    SHA = "a" * 40

    def entry(self, mode, path):
        return (mode + " " + self.SHA + " 0\t" + path + "\0").encode()

    def test_regular_modes_accepted(self):
        raw = self.entry("100644", "agents/a.md") + self.entry("100755", "agents/b.md")
        self.assertEqual(bm.parse_ls_files(raw), ["agents/a.md", "agents/b.md"])

    def test_other_modes_rejected(self):
        for mode in ["120000", "160000", "100664", "040000"]:
            with self.subTest(mode=mode):
                with self.assertRaises(bm.ManifestError):
                    bm.parse_ls_files(self.entry(mode, "agents/a.md"))

    def test_malformed_rejected(self):
        with self.assertRaises(bm.ManifestError):
            bm.parse_ls_files(b"agents/a.md\0")


@unittest.skipIf(GIT is None, "git no esta en el PATH: prueba del repositorio real omitida")
@unittest.skipUnless(
    os.path.exists(os.path.join(ROOT, ".git")),
    "no hay .git en la raiz (copia sin historial, p. ej. zip de GitHub): pruebas del repositorio real omitidas",
)
class RealRepo(unittest.TestCase):
    # CIERRE: cualquier cambio posterior en los doce archivos gestionados (los nueve
    # agents/*.md, rules/agentes.md, hooks/agent_guard.py y docs/agentes.md) exige regenerar
    # install-manifest.json con `python -B tools/build_manifest.py` en el mismo cambio; si no,
    # estas pruebas fallan. Anadir o quitar un archivo gestionado exige ademas actualizar TWELVE.
    REGEN = "Regeneralo con: python -B tools/build_manifest.py"

    def load_manifest(self):
        path = os.path.join(ROOT, "install-manifest.json")
        self.assertTrue(os.path.exists(path), "falta install-manifest.json. " + self.REGEN)
        with open(path, "rb") as f:
            raw = f.read()
        return raw, json.loads(raw)

    def test_real_repo_has_twelve_files(self):
        files = bm.managed_files(ROOT)
        self.assertEqual(files, TWELVE)

    def test_manifest_paths_match_git_ls_files(self):
        _, manifest = self.load_manifest()
        paths = [e["path"] for e in manifest["files"]]
        self.assertEqual(paths, bm.managed_files(ROOT),
                         "install-manifest.json no lista los mismos archivos que git ls-files. "
                         + self.REGEN)
        self.assertEqual(len(paths), 12)
        self.assertEqual(sum(p.startswith("agents/") for p in paths), 9)

    def test_manifest_hashes_match_working_tree(self):
        _, manifest = self.load_manifest()
        stale = []
        for entry in manifest["files"]:
            full = os.path.join(ROOT, *entry["path"].split("/"))
            if not os.path.exists(full):
                stale.append(entry["path"])
                continue
            with open(full, "rb") as f:
                if bm.canonical_sha256(f.read()) != entry["sha256"]:
                    stale.append(entry["path"])
        self.assertEqual(stale, [],
                         "hash desactualizado en install-manifest.json para: "
                         + ", ".join(stale) + ". " + self.REGEN)

    def test_manifest_file_equals_render(self):
        raw, _ = self.load_manifest()
        expected = bm.render(bm.build_manifest(ROOT, bm.managed_files(ROOT)))
        self.assertEqual(raw.replace(b"\r\n", b"\n"), expected.encode("ascii"),
                         "install-manifest.json difiere de lo que genera build_manifest. "
                         + self.REGEN)

    def test_main_check_default_root_is_up_to_date(self):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = bm.main(["--check"])
        self.assertEqual(code, 0, err.getvalue() or "main(['--check']) no dio 0")

    def test_manifest_has_no_absolute_paths_or_backslashes(self):
        raw, manifest = self.load_manifest()
        for entry in manifest["files"]:
            self.assertFalse(entry["path"].startswith("/") or ":" in entry["path"], entry["path"])
        self.assertNotIn(b"\\", raw)


if __name__ == "__main__":
    unittest.main()
