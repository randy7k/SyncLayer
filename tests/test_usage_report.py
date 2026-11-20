import ast
import collections
import contextlib
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import usage_report as ur  # noqa: E402
import usage_synth as us  # noqa: E402

SCRIPT = os.path.join(ROOT, "tools", "usage_report.py")


class RealHomeTouched(BaseException):
    """BaseException a proposito: main() captura Exception y esto no debe quedar escondido."""


def _forbidden_default():
    raise RealHomeTouched("una prueba intento resolver el ~/.claude real")


def snapshot(path):
    """(ruta relativa, tamano, mtime_ns) de todo lo que cuelga de path."""
    result = []
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            result.append((os.path.relpath(full, path), st.st_size, st.st_mtime_ns))
    return sorted(result)


def section(out, header_start):
    """Lineas de la seccion cuyo titulo empieza por header_start, hasta la linea en blanco."""
    lines = out.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("== " + header_start):
            body = []
            for nxt in lines[i + 1:]:
                if not nxt:
                    break
                body.append(nxt)
            return body
    raise AssertionError("seccion no encontrada: " + header_start)


def field(out, label):
    m = re.search(r"^" + re.escape(label) + r": (\d+)$", out, re.M)
    if not m:
        raise AssertionError("etiqueta no encontrada: " + label)
    return int(m.group(1))


class Base(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="sync layer ")
        self.addCleanup(td.cleanup)
        self.base = td.name
        patcher = mock.patch.object(ur, "_default_claude_dir", _forbidden_default)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ur.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def inspect(self, tree, *extra):
        return self.run_main("inspect", "--claude-dir", tree.claude_dir, *extra)

    def make_link(self, target, link, is_dir=True):
        """Crea un enlace o junction. Devuelve False si el sistema no lo permite."""
        try:
            os.symlink(target, link, target_is_directory=is_dir)
        except (OSError, NotImplementedError):
            if os.name == "nt" and is_dir:
                proc = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", link, target],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                )
                if proc.returncode != 0:
                    return False
            elif os.name == "nt":
                # sin privilegio para el symlink de archivo: reanalisis de etiqueta propia
                if not us.make_tagged_reparse_file(link):
                    return False
            else:
                return False

        def remove():
            try:
                if is_dir:
                    os.rmdir(link)
                else:
                    os.unlink(link)
            except OSError:
                pass

        self.addCleanup(remove)
        return True


def rich_tree(base):
    """Dos proyectos, tres sesiones, cinco subagentes, con marcadores en todos los campos."""
    tree = us.Tree(base)
    fa = "c--Users-" + us.M_FOLDER + "-proj"
    fb = "c--Users-otro"
    s1, s2, s3 = us.M_SESSION + "-1", us.M_SESSION + "-2", us.M_SESSION + "-3"
    agent_call = us.assistant(
        "mm1", "2026-03-01T10:00:00Z",
        blocks=[
            us.text_block(),
            us.tool_use_block("toolu_a1", "Agent", {
                "subagent_type": "forge", "prompt": us.M_PROMPT, "description": us.M_DESCRIPTION,
                "run_in_background": True, us.M_UNKNOWN_INPUT_KEY: us.M_INPUT,
            }),
            us.tool_use_block("toolu_t1", "Task", {"subagent_type": "scout", "prompt": us.M_PROMPT}),
            us.tool_use_block("toolu_s1", "Skill", {"skill": "brainstorm", "args": us.M_ARGS}),
        ],
        sidechain=False,
    )
    tree.main_session(fa, s1, [
        us.user("2026-03-01T09:59:00Z", sidechain=False),
        agent_call,
        agent_call,  # misma linea repetida: se cuenta una vez
        us.tool_result_line("2026-03-01T10:05:00Z"),
        us.assistant("mm2", "2026-03-01T10:06:00Z", version=us.M_VERSION, sidechain=False,
                     **{us.M_UNKNOWN_KEY: us.M_CONTENT}),
        {"type": us.M_TYPE, "timestamp": "2026-03-01T10:07:00Z", "message": {"content": us.M_CONTENT}},
    ])
    ts = "2026-03-01T10:01:0"
    tree.subagent(fa, s1, "a1", [
        us.user(ts + "0Z"),
        us.assistant("m1", ts + "1Z"),
        us.assistant("m1", ts + "2Z"),  # mismo message.id: otra linea de la misma respuesta
        us.assistant("m2", ts + "3Z", model=us.M_MODEL),
        us.tool_result_line(ts + "4Z"),
    ], meta={"agentType": "forge", "toolUseId": "toolu_a1", "description": us.M_DESCRIPTION,
             us.M_UNKNOWN_KEY: us.M_CONTENT})
    tree.subagent(fa, s1, "a2", [
        us.user(ts + "0Z"),
        us.assistant("m3", ts + "1Z", usage_value=None),
    ], meta={"agentType": "scout", "toolUseId": "toolu_no_coincide"})
    tree.subagent(fa, s1, "a3", [
        us.assistant("m4", ts + "1Z"),
        '{"type": "assistant", "timestamp": "2026-03-01T10:0' + us.M_CONTENT,
    ], meta=None, final_newline=False)
    tree.subagent(fa, s2, "a4", [us.assistant("m5", ts + "1Z")])
    tree.main_session(fb, s3, [
        us.assistant("mm3", "2026-03-02T10:00:00Z", sidechain=False, blocks=[
            us.tool_use_block("toolu_a5", "Agent", {"subagent_type": "auditor", "prompt": us.M_PROMPT}),
            us.tool_use_block("toolu_s2", "Skill", {"skill": "x", "args": us.M_ARGS}),
        ]),
    ])
    tree.subagent(fb, s3, "a5", [us.assistant("m6", "2026-03-02T10:01:00Z", model="claude-opus-4-2",
                                              version="2.1.328")],
                  meta={"agentType": "auditor", "toolUseId": "toolu_a5"})
    return tree


class Derivation(unittest.TestCase):
    def test_known_path(self):
        self.assertEqual(ur.derive_folder_name("c:\\Proyectos\\Demo"), "c--Proyectos-Demo")

    def test_spaces_dots_and_non_ascii(self):
        self.assertEqual(ur.derive_folder_name("/home/a b/x.y/\u00e9"), "-home-a-b-x-y--")

    def test_matches_independent_implementation(self):
        for p in ("c:\\a b\\c", "D:\\x.y\\z", "/tmp/sync layer 1/p", "c:\\a\U0001F600b\\\u00e9"):
            self.assertEqual(ur.derive_folder_name(p), us.folder_name_for(p))

    def test_character_outside_bmp_is_two_dashes(self):
        # JS sustituye por unidad UTF-16: un caracter fuera del BMP son dos guiones.
        # A confirmar en G1 contra el nombre de carpeta que produce Claude Code de verdad.
        self.assertEqual(ur.derive_folder_name("c:\\a\U0001F600b"), "c--a--b")
        self.assertEqual(ur.derive_folder_name("\u00e9"), "-")


class SafeName(unittest.TestCase):
    def test_valid_names_pass(self):
        for n in ("forge", "plugin:agent", "claude-opus-4.5", "a/b", "2.1.330", "A" * 64):
            self.assertEqual(ur.safe_name(n), n)

    def test_invalid_names_replaced_by_alias_that_cannot_pass_as_valid(self):
        for n in ("a|b", "a\nb", "a\\b", "A" * 65, "", " x", "<x>", us.M_MODEL, "a\u00e9"):
            out = ur.safe_name(n)
            self.assertRegex(out, r"^<no-valido-[0-9a-f]{4}>$", repr(n))
            self.assertIsNone(ur.NAME_RE.match(out), "el alias no debe ser falsificable")
            self.assertEqual(out, ur.safe_name(n))

    def test_trailing_newline_not_accepted(self):
        self.assertRegex(ur.safe_name("forge\n"), r"^<no-valido-")

    def test_non_string(self):
        self.assertEqual(ur.safe_name(None), "(no-cadena:null)")
        self.assertEqual(ur.safe_name(True), "(no-cadena:bool)")
        self.assertEqual(ur.safe_name({"a": 1}), "(no-cadena:dict)")


class Environment(Base):
    def test_missing_projects_dir_exit_1_and_nothing_written(self):
        claude = os.path.join(self.base, us.M_FOLDER + " claude")
        os.makedirs(claude)
        before = snapshot(self.base)
        code, out, err = self.run_main("inspect", "--claude-dir", claude)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("projects", err)
        self.assertNotIn(us.M_FOLDER, err)
        self.assertEqual(snapshot(self.base), before)

    def test_show_paths_adds_path_to_stderr_only(self):
        claude = os.path.join(self.base, "sin projects")
        os.makedirs(claude)
        code, out, err = self.run_main("inspect", "--claude-dir", claude, "--show-paths")
        self.assertEqual(code, 1)
        self.assertIn("sin projects", err)
        self.assertEqual(out, "")

    def test_claude_dir_missing_entirely(self):
        code, out, err = self.run_main("inspect", "--claude-dir", os.path.join(self.base, "nada"))
        self.assertEqual(code, 1)
        self.assertNotIn("nada", err)

    def test_project_without_transcripts_exit_1(self):
        tree = rich_tree(self.base)
        proj = os.path.join(self.base, "otro proyecto")
        code, out, err = self.inspect(tree, "--project-dir", proj)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("transcripciones", err)
        self.assertNotIn("otro proyecto", err)

    def test_empty_projects_dir_exit_1(self):
        tree = us.Tree(self.base)
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_default_claude_dir_only_computed_when_missing(self):
        tree = rich_tree(self.base)
        with mock.patch.object(ur, "_default_claude_dir", return_value=tree.claude_dir) as m:
            code, _, _ = self.run_main("inspect")
            self.assertEqual(code, 0)
            self.assertEqual(m.call_count, 1)
            m.reset_mock()
            code, _, _ = self.run_main("inspect", "--claude-dir", tree.claude_dir)
            self.assertEqual(code, 0)
            self.assertEqual(m.call_count, 0)

    def test_usage_errors_exit_2(self):
        for argv in ([], ["nada"], ["inspect", "--no-existe"], ["inspect", "--claude-dir"]):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 2, argv)
            self.assertEqual(out, "")

    def test_unexpected_error_prints_only_class_name(self):
        tree = rich_tree(self.base)
        with mock.patch.object(ur, "_scan_project_folder", side_effect=RuntimeError(us.M_CONTENT)):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, "error: error no previsto (RuntimeError)\n")
        self.assertNotIn("Traceback", err)

    def test_only_standard_library_imports(self):
        with open(SCRIPT, "rb") as f:
            tree = ast.parse(f.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                names.add(node.module.split(".")[0])
        self.assertLessEqual(names, set(sys.stdlib_module_names), names)


class InspectStructure(Base):
    def test_structural_counts(self):
        tree = rich_tree(self.base)
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        expected = {
            "carpetas de proyecto leidas": 2,
            "sesiones": 3,
            "archivos de sesion principal": 2,
            "archivos de subagente": 5,
            "subagentes sin meta": 1,
            "subagentes sin ninguna linea assistant con usage": 1,
            "meta con agentType cadena": 4,
            "meta cuyo toolUseId coincide con un tool_use Agent/Task": 2,
            "meta cuyo toolUseId no coincide": 1,
            "meta con toolUseId sin sesion principal": 1,
            "archivos con ultima linea truncada": 1,
            "archivos de subagente danados o ilegibles": 0,
            "lineas corruptas": 0,
            "subagente lineas assistant con usage": 6,
            "message.id distintos con usage (subagentes)": 5,
            "tool_use Agent (sesion principal)": 2,
            "tool_use Task (sesion principal)": 1,
            "tool_use Skill (sesion principal)": 2,
            "Agent con run_in_background": 1,
            "toolUseResult.totalTokens presente": 2,
            "toolUseResult con otras claves": 2,
            "enlaces omitidos": 0,
        }
        for label, value in expected.items():
            self.assertEqual(field(out, label), value, label)

    def test_unknown_keys_reported_generically(self):
        tree = rich_tree(self.base)
        _, out, _ = self.inspect(tree)
        self.assertIn("(clave desconocida) str: 1", section(out, "Claves sesion.linea"))
        self.assertIn("(clave desconocida) str: 1", section(out, "Claves meta"))
        self.assertIn("(clave desconocida) str: 1", section(out, "Claves input.Agent"))
        self.assertIn("run_in_background bool: 1", section(out, "Claves input.Agent"))
        self.assertIn("agentType str: 4", section(out, "Claves meta"))

    def test_histograms_use_allowed_names_only(self):
        tree = rich_tree(self.base)
        _, out, _ = self.inspect(tree)
        models = section(out, "Histograma subagente.model")
        self.assertIn("claude-opus-4-1: 5", models)
        self.assertIn("claude-opus-4-2: 1", models)
        self.assertIn("(otro modelo): 1", models)
        self.assertNotIn(us.M_MODEL, "\n".join(models))
        self.assertTrue(any(l.startswith("2.1.328") for l in section(out, "Histograma subagente.version")))

    def test_histogram_overflow_is_aggregated(self):
        tree = us.Tree(self.base)
        items = [us.assistant("m%d" % i, "2026-03-01T10:00:00Z", model="claude-opus-%d-%d" % (i // 100, i % 100))
                 for i in range(ur.HIST_STORE_LIMIT + 50)]
        tree.subagent("c--p", "s1", "a1", items)
        code, out, _ = self.inspect(tree)
        self.assertEqual(code, 0)
        body = section(out, "Histograma subagente.model")
        self.assertEqual(len(body), ur.HIST_SHOW_LIMIT + 1)
        self.assertEqual(body[-1], "(otros valores): %d" % (ur.HIST_STORE_LIMIT + 50 - ur.HIST_SHOW_LIMIT))

    def test_empty_sections_say_no_data(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")], meta=None)
        _, out, _ = self.inspect(tree)
        self.assertEqual(section(out, "Claves input.Skill"), ["(sin datos)"])

    def test_deterministic_output(self):
        tree = rich_tree(self.base)
        first = self.inspect(tree)
        second = self.inspect(tree)
        self.assertEqual(first, second)
        self.assertTrue(first[1].endswith("\n"))
        first[1].encode("ascii")

    def test_inspect_writes_nothing(self):
        tree = rich_tree(self.base)
        proj = os.path.join(self.base, "proj dir")
        os.makedirs(proj)
        before = snapshot(self.base)
        self.inspect(tree)
        self.inspect(tree, "--project-dir", proj)
        self.assertEqual(snapshot(self.base), before)

    def test_project_dir_filters_and_matches_case_insensitively(self):
        tree = us.Tree(self.base)
        proj = os.path.join(self.base, "my proj")
        os.makedirs(proj)
        folder = us.folder_name_for(os.path.abspath(proj))
        tree.subagent(folder.swapcase(), "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        tree.subagent("c--otra-cosa", "s2", "a2", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        code, out, _ = self.inspect(tree, "--project-dir", proj)
        self.assertEqual(code, 0)
        self.assertEqual(field(out, "sesiones"), 1)
        self.assertEqual(field(out, "archivos de subagente"), 1)
        code, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "sesiones"), 2)

    def test_two_case_variants_both_read(self):
        # En NTFS no pueden coexistir dos carpetas que solo difieran en la caja: se parchea el
        # listado de projects/ para que devuelva las dos variantes y asi corra en todos lados.
        tree = us.Tree(self.base)
        proj = os.path.join(self.base, "my proj")
        os.makedirs(proj)
        folder = us.folder_name_for(os.path.abspath(proj))
        other = folder.swapcase()
        self.assertNotEqual(other, folder)
        tree.subagent(folder, "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        if not os.path.exists(os.path.join(tree.projects, other)):
            tree.subagent(other, "s2", "a2", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        real_list = ur._list_dir

        def fake_list(path):
            if path == tree.projects:
                return [(folder, "dir"), (other, "dir")]
            return real_list(path)

        with mock.patch.object(ur, "_list_dir", fake_list):
            code, out, err = self.inspect(tree, "--project-dir", proj)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "carpetas de proyecto leidas"), 2)
        self.assertEqual(field(out, "sesiones"), 2)


class HistogramFilters(Base):
    EVIL = (
        "user@example.com",
        "AKIAIOSFODNN7EXAMPLE",
        "IGNORE.PREVIOUS.INSTRUCTIONS:run/curl",
        "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-3",
        "home/x/secret",
    )

    def test_label_functions(self):
        for good in ("2.1.330", "10.20.300", "2.1.330-beta.1"):
            self.assertEqual(ur.hist_label("version", good), good)
        for bad in ("2.1", "2.1.330\n", "2.1.330-", "\uff12.1.1", "v2.1.330", 5, None) + self.EVIL:
            self.assertEqual(ur.hist_label("version", bad), "(otra version)", repr(bad))
        for good in ("user", "assistant", "system", "summary", "attachment", "progress",
                     "file-history-snapshot", "queue-operation", "last-prompt", "permission-mode"):
            self.assertEqual(ur.hist_label("type", good), good)
        for bad in ("User", "assistant\n", "tool_use", 5, None) + self.EVIL:
            self.assertEqual(ur.hist_label("type", bad), "(otro type)", repr(bad))
        for good in ("claude-opus-4-5", "claude-sonnet-4.5", "claude-opus-4-5@20251101",
                     "claude-sonnet-4-5-20250929", "claude-haiku-4-5@20251001",
                     "claude-3-5-sonnet-20241022", "claude-fable-5-2", "<synthetic>"):
            self.assertEqual(ur.hist_label("model", good), good)
        for bad in ("claude-", "claude-x@2025110", "claude-opus-4-5@2025110",
                    "claude-opus-4-5@20251101\n",
                    "claude-opus@\uff12\uff10\uff12\uff15\uff11\uff11\uff10\uff11", "Claude-opus",
                    "claude-opus/y", "claude-opus:y", "<synthetic>\n", 5, None,
                    "claude-" + "a" * 60, "claude-" + "a" * 61,
                    "claude-internal.corp.example.com", "claude-opus.corp.example.com",
                    "claude-opus-4-5.corp.example.com", "claude-opus-abcdef0123456789",
                    "claude-1234-5678-9012-3456", "claude-opus-4111111111111111",
                    "claude-opus-" + "0123456789abcdef" * 3, "claude-opusx") + self.EVIL:
            self.assertEqual(ur.hist_label("model", bad), "(otro modelo)", repr(bad))

    def test_version_sensitive_values(self):
        for bad in ("1.2.3-AKIAIOSFODNN7EXAMPLE", "4111111111111111.12.2030",
                    "1.2.3-" + "a" * 5000, "12345.1.1", "1.12345.1", "1.1.1234567",
                    "1.2.3-a/b", "1.2.3-a b", "1.2.3-a@b", "1.2.3-" + "a" * 25,
                    "1.2.3-a\n", "1.2.3-abcdefgh", "1.2.3-preview", "1.2.3-RC1", "1.2.3-rc1234",
                    "1.2.3-rc1.2.3.4", "1.2.3-beta.1234", "1.2.3-gamma", "1.2.3-rcx"):
            self.assertEqual(ur.hist_label("version", bad), "(otra version)", repr(bad))
        for good in ("1.2.3-rc1", "1234.1234.123456", "2.1.330-beta.1", "1.2.3-alpha", "1.2.3-rc",
                     "1.2.3-beta123.1.2", "1.2.3-rc999"):
            self.assertEqual(ur.hist_label("version", good), good)

    def test_free_text_values_never_reach_the_output(self):
        tree = us.Tree(self.base)
        items = [{"type": v, "version": v, "message": {"model": v, "usage": us.usage()}} for v in self.EVIL]
        items.append(us.assistant("m1", "2026-03-01T10:00:00Z", model="claude-opus-4-5@20251101",
                                  version="2.1.330-beta.1"))
        tree.subagent("c--p", "s1", "a1", items)
        tree.main_session("c--p", "s1", items)
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        n = len(self.EVIL)
        for scope in ("subagente", "sesion"):
            self.assertIn("(otro modelo): %d" % n, section(out, "Histograma %s.model" % scope))
            self.assertIn("(otra version): %d" % n, section(out, "Histograma %s.version" % scope))
            self.assertIn("(otro type): %d" % n, section(out, "Histograma %s.type" % scope))
            self.assertIn("claude-opus-4-5@20251101: 1", section(out, "Histograma %s.model" % scope))
        for evil in self.EVIL:
            self.assertNotIn(evil, out)
        for needle in ("user@", "AKIA", "IGNORE", "arn:", "secret", "no-valido"):
            self.assertNotIn(needle, out)


class DefensiveReading(Base):
    def test_truncated_last_line_is_not_damage(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z"),
                                           '{"type": "assistant", "times'], final_newline=False)
        code, out, _ = self.inspect(tree)
        self.assertEqual(code, 0)
        self.assertEqual(field(out, "archivos con ultima linea truncada"), 1)
        self.assertEqual(field(out, "archivos de subagente danados o ilegibles"), 0)
        self.assertEqual(field(out, "subagente lineas"), 1)

    def test_complete_last_line_without_newline_is_fine(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")], final_newline=False)
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "archivos con ultima linea truncada"), 0)
        self.assertEqual(field(out, "subagente lineas"), 1)

    def _tree_with_files(self, total, corrupt):
        tree = us.Tree(self.base)
        for i in range(total):
            items = [us.assistant("m%d" % i, "2026-03-01T10:00:00Z")]
            if i < corrupt:
                items = ["esto no es json", us.assistant("n%d" % i, "2026-03-01T10:00:01Z")]
            tree.subagent("c--p", "s1", "a%d" % i, items)
        return tree

    def test_damaged_exactly_at_threshold_is_ok(self):
        tree = self._tree_with_files(20, 1)  # 5 %
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "archivos de subagente danados o ilegibles"), 1)
        self.assertEqual(field(out, "lineas corruptas"), 1)

    def test_damaged_over_threshold_exit_3_with_output(self):
        tree = self._tree_with_files(19, 1)  # 5,26 %
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 3)
        self.assertIn("synclayer-usage-inspect v1", out)
        self.assertIn("demasiados archivos", err)
        self.assertIn("1 de 19", err)
        self.assertNotIn(self.base, err)

    def test_oversize_lines_skipped_and_following_lines_read(self):
        tree = us.Tree(self.base)
        huge = '{"type": "assistant", "pad": "' + "x" * 50000 + '"}'
        tree.subagent("c--p", "s1", "a1", [
            us.assistant("m1", "2026-03-01T10:00:00Z"), huge,
            us.assistant("m2", "2026-03-01T10:00:01Z"), huge,
        ], final_newline=False)
        with mock.patch.object(ur, "MAX_LINE_BYTES", 2000):
            code, out, _ = self.inspect(tree)
        self.assertEqual(code, 0)
        self.assertEqual(field(out, "lineas oversize descartadas"), 2)
        self.assertEqual(field(out, "subagente lineas"), 2)
        self.assertEqual(field(out, "message.id distintos con usage (subagentes)"), 2)

    def test_oversize_read_is_bounded(self):
        tree = us.Tree(self.base)
        huge = b'{"type": "assistant", "pad": "' + b"x" * 300000 + b'"}'
        tree.subagent("c--p", "s1", "a1", [huge, us.assistant("m1", "2026-03-01T10:00:00Z")], meta=None)
        sizes = []
        real_open = ur._open_regular

        def spy(path):
            f = real_open(path)
            real_readline = f.readline

            class Spy:
                def readline(self_inner, limit=-1):
                    data = real_readline(limit)
                    sizes.append(len(data))
                    return data

                def fileno(self_inner):
                    return f.fileno()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *a):
                    f.close()

            return Spy()

        with mock.patch.object(ur, "MAX_LINE_BYTES", 1000), mock.patch.object(ur, "_open_regular", spy):
            code, out, _ = self.inspect(tree)
        self.assertEqual(code, 0)
        self.assertLessEqual(max(sizes), 1001)
        self.assertEqual(field(out, "lineas oversize descartadas"), 1)

    def test_deeply_nested_json_is_a_corrupt_line_not_a_crash(self):
        tree = us.Tree(self.base)
        deep = "[" * 100000 + "]" * 100000
        items = [deep] * 3 + [us.assistant("m%d" % i, "2026-03-01T10:00:00Z") for i in range(40)]
        tree.subagent("c--p", "s1", "a1", items)
        tree.subagent("c--p", "s1", "a2", [us.assistant("z", "2026-03-01T10:00:00Z")])
        for i in range(30):
            tree.subagent("c--p", "s1", "b%d" % i, [us.assistant("z", "2026-03-01T10:00:00Z")])
        code, out, err = self.inspect(tree)
        self.assertIn(code, (0, 3))
        self.assertNotIn("error no previsto", err)
        self.assertGreaterEqual(field(out, "lineas corruptas"), 1)

    def test_non_object_lines_counted(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", ["[1, 2]", "7", '"texto"', us.assistant("m1", "2026-03-01T10:00:00Z")])
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "lineas que no son objeto"), 3)
        self.assertEqual(field(out, "subagente lineas"), 1)

    def test_unreadable_file_counted(self):
        tree = us.Tree(self.base)
        for i in range(30):
            tree.subagent("c--p", "s1", "a%d" % i, [us.assistant("m1", "2026-03-01T10:00:00Z")])
        real_open = os.open

        def fake_open(path, *a, **k):
            if os.path.basename(path) == "agent-a1.jsonl":
                raise PermissionError("denegado " + us.M_CONTENT)
            return real_open(path, *a, **k)

        with mock.patch.object(ur.os, "open", fake_open):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "archivos ilegibles"), 1)
        self.assertEqual(field(out, "archivos de subagente"), 30)
        self.assertEqual(field(out, "archivos de subagente danados o ilegibles"), 1)
        self.assertNotIn(us.M_CONTENT, out + err)

    def test_meta_variants(self):
        tree = us.Tree(self.base)
        line = [us.assistant("m1", "2026-03-01T10:00:00Z")]
        tree.subagent("c--p", "s1", "a1", line, meta=b"{no json")
        tree.subagent("c--p", "s1", "a2", line, meta=b"[1]")
        tree.subagent("c--p", "s1", "a3", line, meta={"agentType": 5})
        tree.subagent("c--p", "s1", "a4", line, meta=b'{"agentType": "' + b"x" * 100000 + b'"}')
        for i in range(50):
            tree.subagent("c--p", "s1", "b%d" % i, line)
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "meta corrupto"), 1)
        self.assertEqual(field(out, "meta que no es objeto"), 1)
        self.assertEqual(field(out, "meta sin agentType cadena"), 1)
        self.assertEqual(field(out, "meta sobredimensionado"), 1)

    def test_orphan_meta_counted(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        sub = os.path.join(tree.projects, "c--p", "s1", "subagents")
        with open(os.path.join(sub, "agent-zz.meta.json"), "wb") as f:
            f.write(b"{}")
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "metas sin transcripcion"), 1)

    def test_directory_named_like_a_transcript_is_not_opened(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        os.makedirs(os.path.join(tree.projects, "c--p", "s1", "subagents", "agent-dir.jsonl"))
        code, out, _ = self.inspect(tree)
        self.assertEqual(code, 0)
        self.assertEqual(field(out, "archivos de subagente"), 1)

    def test_file_without_any_type_counted(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [{"foo": 1}, {"bar": 2}])
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "archivos con lineas y ninguna con type"), 1)

    def test_usage_shapes(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [
            us.assistant("m1", "2026-03-01T10:00:00Z", usage_value=us.usage(inp=True)),
            us.assistant("m2", "2026-03-01T10:00:01Z", usage_value=us.usage(inp=-1)),
            us.assistant("m3", "2026-03-01T10:00:02Z", usage_value="texto"),
            us.assistant("m4", "2026-03-01T10:00:03Z"),
            us.assistant("m5", "bad-timestamp"),
        ])
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "usage con los 4 campos enteros no negativos"), 2)
        self.assertEqual(field(out, "usage sin los 4 campos enteros"), 2)
        self.assertEqual(field(out, "timestamp no interpretable"), 1)


class Links(Base):
    def _tree_and_outside(self):
        tree = us.Tree(self.base)
        tree.subagent("c--real", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        outside = os.path.join(self.base, "afuera")
        tree2 = us.Tree(outside)
        tree2.subagent("c--ajena", "s9", "a9", [us.assistant("m9", "2026-03-01T10:00:00Z")])
        return tree, tree2

    def test_linked_project_folder_not_followed(self):
        tree, outer = self._tree_and_outside()
        link = os.path.join(tree.projects, "c--enlace")
        if not self.make_link(os.path.join(outer.projects, "c--ajena"), link):
            self.skipTest("el sistema no permite crear enlaces ni junctions")
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "carpetas de proyecto leidas"), 1)
        self.assertEqual(field(out, "archivos de subagente"), 1)
        self.assertGreaterEqual(field(out, "enlaces omitidos"), 1)

    def test_linked_session_and_subagents_dirs_not_followed(self):
        tree, outer = self._tree_and_outside()
        folder = os.path.join(tree.projects, "c--real")
        if not self.make_link(os.path.join(outer.projects, "c--ajena", "s9"), os.path.join(folder, "s-link")):
            self.skipTest("el sistema no permite crear enlaces ni junctions")
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "archivos de subagente"), 1)
        self.assertEqual(field(out, "sesiones"), 1)

    def test_linked_projects_dir_refused(self):
        _, outer = self._tree_and_outside()
        claude = os.path.join(self.base, "claude con enlace")
        os.makedirs(claude)
        if not self.make_link(outer.projects, os.path.join(claude, "projects")):
            self.skipTest("el sistema no permite crear enlaces ni junctions")
        code, out, err = self.run_main("inspect", "--claude-dir", claude)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("enlace", err)

    def test_linked_transcript_file_not_followed(self):
        tree, outer = self._tree_and_outside()
        target = os.path.join(outer.projects, "c--ajena", "s9", "subagents", "agent-a9.jsonl")
        link = os.path.join(tree.projects, "c--real", "s1", "subagents", "agent-l.jsonl")
        if not self.make_link(target, link, is_dir=False):
            self.skipTest("el sistema no permite crear enlaces de archivo")
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "archivos de subagente"), 1)
        self.assertGreaterEqual(field(out, "enlaces omitidos"), 1)


def raw_path(path):
    """En Windows, ruta con prefijo \\\\?\\ para crear nombres que Win32 normalizaria (punto o espacio final)."""
    # sin abspath: normalizaria justo lo que se quiere conservar (punto o espacio final)
    assert os.path.isabs(path)
    return "\\\\?\\" + path if os.name == "nt" else path


class HardlinksAndLinkCount(Base):
    def _hardlink(self, outside_file, link):
        try:
            os.link(outside_file, link)
        except (OSError, NotImplementedError, AttributeError) as e:
            self.skipTest("el sistema no permite hardlinks: %s" % e)

    def test_hardlinked_transcript_not_read_and_counted(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        outer = us.Tree(os.path.join(self.base, "afuera"))
        target = outer.subagent("c--ajena", "s9", "a9", [us.assistant("m9", "2026-03-01T10:00:00Z")],
                                meta=None)
        sub = os.path.join(tree.projects, "c--p", "s1", "subagents")
        self._hardlink(target, os.path.join(sub, "agent-h.jsonl"))
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        # G1: los hardlinks de subagentes son legitimos; inspect no los lee pero los cuenta aparte
        self.assertEqual(field(out, "hardlinks (nlink > 1)"), 1)
        self.assertEqual(field(out, "enlaces omitidos"), 0)
        self.assertEqual(field(out, "archivos de subagente"), 1)
        self.assertEqual(field(out, "subagente lineas"), 1)
        self.assertEqual(field(out, "archivos ilegibles"), 0)

    def test_hardlinked_main_session_and_meta_counted(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")], meta=None)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        main = outer.main_session("c--ajena", "s9", [us.assistant("m9", "2026-03-01T10:00:00Z")])
        meta = os.path.join(outer.folder("c--ajena"), "meta.json")
        with open(meta, "wb") as f:
            f.write(b'{"agentType": "forge"}')
        self._hardlink(main, os.path.join(tree.projects, "c--p", "s1.jsonl"))
        self._hardlink(meta, os.path.join(tree.projects, "c--p", "s1", "subagents", "agent-a1.meta.json"))
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "hardlinks (nlink > 1)"), 2)
        self.assertEqual(field(out, "enlaces omitidos"), 0)
        self.assertEqual(field(out, "sesion lineas"), 0)
        self.assertEqual(field(out, "archivos de sesion principal"), 0)
        self.assertEqual(field(out, "meta con agentType cadena"), 0)

    def test_five_known_links_counted_exactly_five(self):
        tree = us.Tree(self.base)
        tree.subagent("c--real", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")], meta=None)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        tgt = outer.subagent("c--ajena", "s9", "a9", [us.assistant("m9", "2026-03-01T10:00:00Z")])
        ajena = os.path.join(outer.projects, "c--ajena")
        folder = os.path.join(tree.projects, "c--real")
        sub = os.path.join(folder, "s1", "subagents")
        # 1 carpeta de proyecto enlazada, 2 carpeta subagents enlazada, 3 transcripcion enlazada,
        # 4 meta enlazado, 5 hardlink a un archivo fuera de projects/
        os.makedirs(os.path.join(folder, "s2"))
        made = [
            self.make_link(ajena, os.path.join(tree.projects, "c--enlace")),
            self.make_link(os.path.join(ajena, "s9", "subagents"), os.path.join(folder, "s2", "subagents")),
            self.make_link(tgt, os.path.join(sub, "agent-l.jsonl"), is_dir=False),
            self.make_link(tgt, os.path.join(sub, "agent-a1.meta.json"), is_dir=False),
        ]
        if not all(made):
            self.skipTest("el sistema no permite crear enlaces, junctions o reanalisis de archivo")
        self._hardlink(tgt, os.path.join(sub, "agent-h.jsonl"))
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "enlaces omitidos"), 4)
        self.assertEqual(field(out, "hardlinks (nlink > 1)"), 1)
        self.assertEqual(field(out, "archivos de subagente"), 1)
        self.assertEqual(field(out, "sesiones"), 1)


class OpenRegular(Base):
    """_open_regular se ejercita directamente, sin pasar por el listado que ya filtra enlaces."""

    def _file(self, name="f.jsonl", data=b"{}\n"):
        path = os.path.join(self.base, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_regular_file_opens(self):
        with ur._open_regular(self._file()) as f:
            self.assertEqual(f.read(), b"{}\n")

    def test_directory_rejected(self):
        d = os.path.join(self.base, "una carpeta")
        os.makedirs(d)
        with self.assertRaises(OSError):
            ur._open_regular(d)

    def test_junction_or_dir_link_rejected(self):
        target = os.path.join(self.base, "destino")
        os.makedirs(target)
        link = os.path.join(self.base, "junction")
        if not self.make_link(target, link):
            self.skipTest("el sistema no permite crear enlaces ni junctions")
        with self.assertRaises(OSError):
            ur._open_regular(link)

    def test_file_with_own_tag_reparse_point_rejected(self):
        if os.name != "nt":
            self.skipTest("solo Windows")
        path = os.path.join(self.base, "reparse.jsonl")
        if not us.make_tagged_reparse_file(path):
            self.skipTest("no se pudo crear el punto de reanalisis de etiqueta propia")
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.assertTrue(ur._is_link_stat(os.lstat(path)))
        with self.assertRaises(OSError):
            ur._open_regular(path)

    def test_symlink_to_file_rejected(self):
        target = self._file()
        link = os.path.join(self.base, "enlace.jsonl")
        if not self.make_link(target, link, is_dir=False):
            self.skipTest("el sistema no permite crear enlaces de archivo")
        with self.assertRaises(OSError):
            ur._open_regular(link)

    def test_hardlink_rejected_with_link_refused(self):
        target = self._file()
        link = os.path.join(self.base, "hard.jsonl")
        try:
            os.link(target, link)
        except (OSError, NotImplementedError) as e:
            self.skipTest("el sistema no permite hardlinks: %s" % e)
        with self.assertRaises(ur.LinkRefused):
            ur._open_regular(link)
        with self.assertRaises(ur.LinkRefused):
            ur._open_regular(target)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "sin FIFO en este sistema")
    def test_fifo_does_not_block(self):
        path = os.path.join(self.base, "fifo.jsonl")
        os.mkfifo(path)
        with self.assertRaises(OSError):
            ur._open_regular(path)

    def test_nonblock_flag_is_requested_where_it_exists(self):
        path = self._file()
        seen = []
        real_open = os.open

        def spy(p, flags, *a, **k):
            seen.append(flags)
            return real_open(p, flags & ~0x800, *a, **k)

        with mock.patch.object(os, "O_NONBLOCK", 0x800, create=True), mock.patch.object(ur.os, "open", spy):
            ur._open_regular(path).close()
        self.assertTrue(seen and seen[0] & 0x800)


class NameAllowlist(Base):
    def _put(self, rel, data=None):
        path = raw_path(os.path.join(self.projects, *rel))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data if data is not None else
                    (json_line("m1") + b"\n"))

    def _cleanup_raw(self, rel):
        top = raw_path(os.path.join(self.projects, rel))

        def clean():
            shutil.rmtree(top, ignore_errors=True)

        self.addCleanup(clean)

    def test_invalid_names_skipped_and_counted(self):
        tree = us.Tree(self.base)
        self.projects = tree.projects
        tree.subagent("c--ok", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        # gemelos Win32: `c--dot.` y `c--dot ` se leerian como `c--dot` (que existe de verdad)
        tree.subagent("c--dot", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        for weird in ("c--dot.", "c--dot ", "con", "c--é"):
            self._cleanup_raw(weird)
            self._put([weird, "s1", "subagents", "agent-x.jsonl"])
        # dentro de una carpeta valida: transcripciones y carpetas de sesion con nombre no valido
        for rel in (["c--ok", "s.1.jsonl"], ["c--ok", "a b.jsonl"], ["c--ok", "con.jsonl"],
                    ["c--ok", "NUL.jsonl"]):
            self._cleanup_raw(rel[0] + os.sep + rel[1])
            self._put(rel)
        self._cleanup_raw(os.path.join("c--ok", "s 2"))
        self._put(["c--ok", "s 2", "subagents", "agent-y.jsonl"])
        sub = ["c--ok", "s1", "subagents"]
        for name in ("agent-x y.jsonl", "agent-.jsonl", "agent-a.b.jsonl", "agent-r s.meta.json",
                     "agent-q.v.meta.json"):
            self._cleanup_raw(os.path.join(*sub, name))
            self._put(sub + [name])
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        # c--ok (s1) y c--dot (s1) son las unicas sesiones; 4 carpetas raras en projects/ (+ la de c--ok/s 2)
        self.assertEqual(field(out, "carpetas de proyecto leidas"), 2)
        self.assertEqual(field(out, "sesiones"), 2)
        self.assertEqual(field(out, "archivos de subagente"), 2)
        self.assertEqual(field(out, "nombres no validos omitidos"), 4 + 4 + 1 + 5)

    def test_valid_names_are_not_counted(self):
        tree = rich_tree(self.base)
        _, out, _ = self.inspect(tree)
        self.assertEqual(field(out, "nombres no validos omitidos"), 0)

    def test_name_predicates(self):
        for good in ("c--Users-x", "-home-x", "0a1b2c3d-1111-2222-3333-444455556666"):
            self.assertTrue(ur.valid_dir_name(good), good)
        for bad in ("", "c--dot.", "c--dot ", "a b", "con", "NUL", "Com1", "lpt9", "é", "a\n", "a:b"):
            self.assertFalse(ur.valid_dir_name(bad), repr(bad))
        self.assertTrue(ur.valid_session_file("abc-123.jsonl"))
        for bad in ("con.jsonl", "a.b.jsonl", "abc.jsonl ", "abc.jsonl.", ".jsonl", "a\n.jsonl"):
            self.assertFalse(ur.valid_session_file(bad), repr(bad))
        for good in ("agent-a1.jsonl", "agent-a_1-b.meta.json"):
            self.assertTrue(ur.valid_agent_file(good), good)
        for bad in ("agent-.jsonl", "agent-a.b.jsonl", "agent-a b.jsonl", "agent-a.jsonl\n", "x-a.jsonl",
                    "agent-a.meta.json.", "agent-é.jsonl"):
            self.assertFalse(ur.valid_agent_file(bad), repr(bad))


def json_line(msg_id):
    return json.dumps(us.assistant(msg_id, "2026-03-01T10:00:00Z")).encode("utf-8")


class ResourceLimits(Base):
    def _many_small(self, tree, n=30):
        for i in range(n):
            tree.subagent("c--p", "s1", "z%d" % i, [us.assistant("m1", "2026-03-01T10:00:00Z")])

    def test_file_over_max_bytes_by_fstat_is_omitted(self):
        tree = us.Tree(self.base)
        self._many_small(tree)
        tree.subagent("c--p", "s1", "big", [us.assistant("b%d" % i, "2026-03-01T10:00:00Z")
                                            for i in range(60)])
        with mock.patch.object(ur, "MAX_FILE_BYTES", 5000):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "archivos omitidos por tope de tamano"), 1)
        self.assertEqual(field(out, "subagente lineas"), 30)
        self.assertEqual(field(out, "archivos ilegibles"), 1)

    def test_growing_file_is_caught_by_bytes_read(self):
        tree = us.Tree(self.base)
        self._many_small(tree)
        tree.subagent("c--p", "s1", "big", [us.assistant("b%d" % i, "2026-03-01T10:00:00Z")
                                            for i in range(60)])
        real_fstat = os.fstat

        def lying_fstat(fd):
            st = real_fstat(fd)
            values = list(st)
            values[6] = 0
            return os.stat_result(values)

        with mock.patch.object(ur, "MAX_FILE_BYTES", 5000), mock.patch.object(ur.os, "fstat", lying_fstat):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "archivos omitidos por tope de tamano"), 1)

    def test_id_sets_are_capped(self):
        tree = us.Tree(self.base)
        self._many_small(tree)
        tree.subagent("c--p", "s1", "ids", [us.assistant("i%d" % i, "2026-03-01T10:00:00Z")
                                            for i in range(10)])
        with mock.patch.object(ur, "MAX_IDS_PER_FILE", 3):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "archivos omitidos por tope de tamano"), 1)
        self.assertNotIn("error no previsto", err)

    def test_tool_use_id_sets_are_capped(self):
        tree = us.Tree(self.base)
        self._many_small(tree)
        blocks = [us.tool_use_block("toolu_%d" % i, "Agent", {"subagent_type": "forge"}) for i in range(10)]
        tree.main_session("c--p", "s1", [us.assistant("m1", "2026-03-01T10:00:00Z", blocks=blocks,
                                                      sidechain=False)])
        with mock.patch.object(ur, "MAX_IDS_PER_FILE", 3):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "archivos omitidos por tope de tamano"), 1)

    def test_max_file_bytes_default_is_documented_constant(self):
        self.assertEqual(ur.MAX_FILE_BYTES, 512 * 1024 * 1024)


class DirectoryRace(Base):
    def test_dir_replaced_between_checks_is_unreadable(self):
        d = os.path.join(self.base, "carpeta")
        os.makedirs(d)
        self.assertIsNotNone(ur._list_dir(d))
        real_lstat = os.lstat
        calls = []

        def swapping(path, *a, **k):
            st = real_lstat(path, *a, **k)
            if path == d:
                calls.append(1)
                if len(calls) >= 2:
                    values = list(st)
                    values[1] += 1
                    return os.stat_result(values)
            return st

        with mock.patch.object(ur.os, "lstat", swapping):
            self.assertIsNone(ur._list_dir(d))
        self.assertGreaterEqual(len(calls), 2)

    def test_dir_that_is_a_link_is_not_listed(self):
        target = os.path.join(self.base, "destino")
        os.makedirs(target)
        link = os.path.join(self.base, "enlace")
        if not self.make_link(target, link):
            self.skipTest("el sistema no permite crear enlaces ni junctions")
        self.assertIsNone(ur._list_dir(link))


class CommandLine(Base):
    def test_abbreviations_rejected(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z")])
        code, out, err = self.run_main("inspect", "--claude", tree.claude_dir)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        code, _, _ = self.run_main("inspect", "--show", "--claude-dir", tree.claude_dir)
        self.assertEqual(code, 2)

    def test_empty_dirs_rejected_with_clear_message(self):
        for flag in ("--claude-dir", "--project-dir"):
            code, out, err = self.run_main("inspect", flag, "")
            self.assertEqual(code, 2, flag)
            self.assertEqual(out, "")
            self.assertIn("vacio", err)
            self.assertNotIn("Traceback", err)

    def test_keyboard_interrupt_exit_130_without_traceback(self):
        tree = rich_tree(self.base)
        with mock.patch.object(ur, "_scan_project_folder", side_effect=KeyboardInterrupt):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 130)
        self.assertEqual(out, "")
        self.assertNotIn("Traceback", err)
        self.assertEqual(err, "interrumpido\n")


class NoLeak(Base):
    def _assert_clean(self, *texts):
        joined = "\n".join(texts)
        for marker in us.ALL_MARKERS:
            self.assertNotIn(marker, joined, marker)
        self.assertNotIn("Traceback", joined)

    def test_inspect_output_has_no_markers(self):
        tree = rich_tree(self.base)
        proj = os.path.join(self.base, "p")
        for argv in ((), ("--project-dir", proj), ("--show-paths",)):
            code, out, err = self.inspect(tree, *argv)
            self._assert_clean(out, err)
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0)
        # el nombre de la carpeta del proyecto y el id de sesion tampoco salen
        self.assertNotIn("c--Users", out)

    def test_error_paths_have_no_markers(self):
        tree = rich_tree(self.base)
        with mock.patch.object(ur, "_scan_session", side_effect=ValueError(us.M_CONTENT + us.M_CWD)):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 1)
        self._assert_clean(out, err)
        code, out, err = self.run_main("inspect", "--claude-dir", os.path.join(self.base, us.M_FOLDER))
        self._assert_clean(out, err)

    def test_exit_3_has_no_markers(self):
        tree = us.Tree(self.base)
        for i in range(10):
            tree.subagent("c--" + us.M_FOLDER, us.M_SESSION, "a%d" % i,
                          [us.user("2026-03-01T10:00:00Z"), "basura " + us.M_CONTENT])
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 3)
        self._assert_clean(out, err)

    def test_username_not_in_output(self):
        tree = rich_tree(self.base)
        user = os.path.basename(os.path.expanduser("~"))
        _, out, err = self.inspect(tree)
        if len(user) > 3:
            self.assertNotIn(user.lower(), (out + err).lower())


class RealInvocation(unittest.TestCase):
    def test_subprocess_inspect_and_usage_error(self):
        with tempfile.TemporaryDirectory(prefix="sync layer ") as base:
            tree = rich_tree(base)
            proc = subprocess.run(
                [sys.executable, "-B", SCRIPT, "inspect", "--claude-dir", tree.claude_dir],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = proc.stdout.decode("ascii")
            self.assertIn("synclayer-usage-inspect v1", text)
            self.assertEqual(proc.stderr, b"")
            for marker in us.ALL_MARKERS:
                self.assertNotIn(marker, text)
            bad = subprocess.run([sys.executable, "-B", SCRIPT], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, timeout=120)
            self.assertEqual(bad.returncode, 2)


T0 = "2026-03-01T10:00:0"


class ReaderBase(Base):
    def read(self, tree, **kw):
        kw.setdefault("check_damage", True)
        return ur.read_calls(tree.claude_dir, **kw)

    def one(self, tree, **kw):
        res = self.read(tree, **kw)
        self.assertEqual(len(res.calls), 1)
        return res.calls[0]

    def hardlink(self, target, link):
        try:
            os.link(target, link)
        except (OSError, NotImplementedError, AttributeError) as e:
            self.skipTest("el sistema no permite hardlinks: %s" % e)

    def assert_no_markers(self, *objs):
        joined = "\n".join(repr(o) for o in objs)
        for marker in us.ALL_MARKERS:
            self.assertNotIn(marker, joined, marker)


class ReaderTokens(ReaderBase):
    def test_streaming_lines_with_same_id_count_once_last_line_wins(self):
        tree = us.Tree(self.base)
        items = [us.user(T0 + "0Z")]
        items += us.stream("m1", T0 + "1Z", [us.usage(1, 2, 3, 4), us.usage(10, 20, 30, 40), us.usage(100, 200, 300, 400)])
        items += us.stream("m2", T0 + "2Z", [us.usage(1, 1, 1, 1), us.usage(1, 1, 1, 1)])
        tree.subagent("c--p", "s1", "a1", items)
        c = self.one(tree)
        # m1 -> ultima linea (100,200,300,400); m2 -> (1,1,1,1) una sola vez
        self.assertEqual((c.input_tokens, c.output_tokens, c.cache_creation_tokens, c.cache_read_tokens),
                         (101, 201, 301, 401))
        self.assertEqual(c.requests, 2)
        self.assertEqual(c.total_tokens, 101 + 201 + 301 + 401)
        self.assertEqual(c.status, "correcta")

    def test_retry_with_new_id_is_counted_as_another_request(self):
        # limite conocido del diseno (3.5): un reintento con message.id nuevo no se corrige
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z"), us.assistant("m1b", T0 + "2Z")])
        c = self.one(tree)
        self.assertEqual(c.requests, 2)
        self.assertEqual(c.input_tokens, 20)

    def test_usage_without_message_id_counts_each_line_and_is_reported(self):
        tree = us.Tree(self.base)
        line = us.assistant("x", T0 + "1Z")
        del line["message"]["id"]
        tree.subagent("c--p", "s1", "a1", [line, line])
        res = self.read(tree)
        self.assertEqual(res.calls[0].requests, 2)
        self.assertEqual(res.quality["usage sin message.id"], 2)

    def test_call_without_usage_is_a_call_but_not_usable(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.user(T0 + "0Z"), us.assistant("m1", T0 + "1Z", usage_value=None)])
        c = self.one(tree)
        self.assertFalse(c.has_usage)
        self.assertFalse(c.usable)
        self.assertEqual(c.status, "sin_usage")
        self.assertEqual((c.requests, c.total_tokens), (0, 0))
        self.assertEqual(self.read(tree).quality["llamadas sin usage"], 1)

    def test_synthetic_model_excluded_from_models_and_tokens(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [
            us.assistant("m1", T0 + "1Z"),
            us.assistant("s1", T0 + "2Z", model="<synthetic>", usage_value=us.usage(999, 999, 999, 999)),
        ])
        res = self.read(tree)
        c = res.calls[0]
        self.assertEqual(c.input_tokens, 10)
        self.assertEqual(c.models, ("claude-opus-4-1",))
        self.assertEqual(res.quality["lineas synthetic excluidas"], 1)

    def test_tool_use_blocks_counted_by_distinct_id(self):
        tree = us.Tree(self.base)
        blocks = [us.tool_use_block("t1", "Read"), us.tool_use_block("t2", "Bash")]
        tree.subagent("c--p", "s1", "a1", [
            us.assistant("m1", T0 + "1Z", blocks=blocks),
            us.assistant("m1", T0 + "2Z", blocks=blocks),  # misma respuesta repetida
            us.assistant("m2", T0 + "3Z", blocks=[us.tool_use_block("t2", "Bash"), us.text_block()]),
        ])
        self.assertEqual(self.one(tree).tools, 2)

    def test_timestamps_start_end_in_utc(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [
            us.user("2026-03-01T12:00:05+02:00"),   # 10:00:05Z
            us.assistant("m1", "2026-03-01T10:00:09Z"),
            us.assistant("m2", "2026-03-01T10:00:07"),  # sin zona: UTC
        ])
        c = self.one(tree)
        self.assertEqual(c.start.isoformat(), "2026-03-01T10:00:05+00:00")
        self.assertEqual(c.end.isoformat(), "2026-03-01T10:00:09+00:00")

    def test_background_is_unknown_in_subagent_files(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        self.assertIsNone(self.one(tree).background)


class ReaderAgentAndModel(ReaderBase):
    def test_nine_synclayer_agents_and_builtins_pass(self):
        for name in ("oracle", "scout", "atlas", "forge", "sentinel", "auditor", "shield", "debugger", "scribe"):
            self.assertEqual(ur.classify_agent(name), (name, "SyncLayer"))
        for name in ("general-purpose", "Explore", "Plan", "statusline-setup", "output-style-setup",
                     "claude-code-guide"):
            self.assertEqual(ur.classify_agent(name), (name, "integrado"))

    def test_unknown_agent_names_are_never_shown(self):
        for raw in ("user@example.com", "home/x/secret", "AKIAIOSFODNN7EXAMPLE", us.M_TYPE, "forge\n",
                    "Forge", "a|b", "x" * 200, 5, None, {"a": 1}):
            name, group = ur.classify_agent(raw)
            self.assertEqual((name, group), ("(otro agente)", "otros"), repr(raw))
        self.assertEqual(ur.classify_agent("plug:agent"), ("plugin:plug", "plugin:plug"))
        self.assertEqual(ur.classify_agent(""), ("general-purpose", "integrado"))

    def test_synclayer_agents_match_agent_files(self):
        names = sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md"))
        self.assertEqual(sorted(ur.SYNCLAYER_AGENTS), names)

    def test_agent_from_meta_and_default_agent_without_subagent_type(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")],
                      meta={"agentType": "general-purpose"})   # meta sin toolUseId
        tree.subagent("c--p", "s1", "a2", [us.assistant("m2", T0 + "1Z")], meta={"agentType": "scout", "toolUseId": 7})
        res = self.read(tree)
        self.assertEqual([(c.agent, c.agent_group, c.has_meta) for c in res.calls],
                         [("general-purpose", "integrado", True), ("scout", "SyncLayer", True)])

    def test_missing_meta_is_sin_meta_call(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")], meta=None)
        c = self.one(tree)
        self.assertEqual((c.agent, c.agent_group, c.status, c.has_meta), ("(sin-meta)", "sin-meta", "sin_meta", False))
        self.assertEqual(c.input_tokens, 10)  # sus tokens cuentan
        self.assertTrue(c.usable)

    def test_agent_type_with_markers_is_not_in_records(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")], meta={"agentType": us.M_TYPE + "@x/y:z"})
        c = self.one(tree)
        self.assertEqual(c.agent, "(otro agente)")
        self.assert_no_markers(c)

    def test_model_from_lines_single_mixed_and_meta_fallback(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z", model="claude-opus-4-1"),
                                           us.assistant("m2", T0 + "2Z", model="claude-opus-4-1")])
        tree.subagent("c--p", "s1", "a2", [us.assistant("m3", T0 + "1Z", model="claude-opus-4-1"),
                                           us.assistant("m4", T0 + "2Z", model="claude-haiku-4-5")])
        tree.subagent("c--p", "s1", "a3", [us.assistant("m5", T0 + "1Z", usage_value=None, model=us.M_MODEL)],
                      meta={"agentType": "forge", "model": "claude-sonnet-4-5"})
        tree.subagent("c--p", "s1", "a4", [us.user(T0 + "1Z")], meta={"agentType": "forge", "model": "sonnet"})
        tree.subagent("c--p", "s1", "a5", [us.user(T0 + "1Z")], meta={"agentType": "forge", "model": us.M_MODEL})
        by = {c.call_id: c for c in self.read(tree, check_damage=False).calls}
        got = sorted((c.model, c.models, c.model_source) for c in by.values())
        self.assertEqual(got, sorted([
            ("claude-opus-4-1", ("claude-opus-4-1",), "lineas"),
            ("mixto", ("claude-haiku-4-5", "claude-opus-4-1"), "lineas"),
            ("(otro modelo)", ("(otro modelo)",), "lineas"),
            ("sonnet", ("sonnet",), "meta"),
            ("(otro modelo)", ("(otro modelo)",), "meta"),
        ]))

    def test_model_meta_fallback_when_lines_have_no_model(self):
        tree = us.Tree(self.base)
        line = us.assistant("m1", T0 + "1Z")
        del line["message"]["model"]
        tree.subagent("c--p", "s1", "a1", [line], meta={"agentType": "forge", "model": "claude-sonnet-4-5"})
        c = self.one(tree)
        self.assertEqual((c.model, c.model_source), ("claude-sonnet-4-5", "meta"))

    def test_model_discrepancy_between_lines_and_meta_is_recorded(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z", model="claude-opus-4-1")],
                      meta={"agentType": "forge", "model": "claude-sonnet-4-5"})
        tree.subagent("c--p", "s1", "a2", [us.assistant("m2", T0 + "1Z", model="claude-opus-4-1")],
                      meta={"agentType": "forge", "model": "claude-opus-4-1"})
        res = self.read(tree)
        self.assertEqual([c.model_mismatch for c in res.calls], [True, False])
        self.assertEqual([c.model for c in res.calls], ["claude-opus-4-1"] * 2)  # las lineas mandan
        self.assertEqual(res.quality["llamadas con modelo distinto del meta"], 1)

    def test_versions_per_call_and_unverified(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z", version="2.1.310"),
                                           us.assistant("m2", T0 + "2Z", version="2.1.328")])
        tree.subagent("c--p", "s1", "a2", [us.assistant("m3", T0 + "1Z", version="2.1.326")])
        tree.subagent("c--p", "s1", "a3", [us.assistant("m4", T0 + "1Z", version="2.1.327")])
        tree.subagent("c--p", "s1", "a4", [us.assistant("m5", T0 + "1Z", version=us.M_VERSION)])
        res = self.read(tree)
        self.assertEqual(ur.VERIFIED_MAX, "2.1.326")
        got = {c.versions: c.unverified for c in res.calls}
        self.assertEqual(got, {("2.1.310", "2.1.328"): True, ("2.1.326",): False, ("2.1.327",): True,
                               ("(otra version)",): False})
        self.assertEqual(res.versions["2.1.310"], 1)
        self.assertNotIn(us.M_VERSION, repr(res.versions))


class ReaderHardlinksAndLimits(ReaderBase):
    def test_hardlinked_subagent_is_read_and_counted_apart(self):
        tree = us.Tree(self.base)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        target = outer.subagent("c--x", "s9", "a9", [us.assistant("h1", T0 + "1Z", usage_value=us.usage(7, 1, 1, 1))],
                                meta=None)
        sub = os.path.join(tree.folder("c--p"), "s1", "subagents")
        os.makedirs(sub)
        self.hardlink(target, os.path.join(sub, "agent-h.jsonl"))
        res = self.read(tree)
        self.assertEqual(len(res.calls), 1)
        self.assertTrue(res.calls[0].hardlink)
        self.assertEqual(res.calls[0].input_tokens, 7)
        self.assertEqual(res.quality["hardlinks aceptados"], 1)

    def test_hardlinked_file_with_foreign_content_fails_the_signature(self):
        tree = us.Tree(self.base)
        outer = os.path.join(self.base, "afuera.txt")
        with open(outer, "wb") as f:
            f.write(b'{"clave": "' + us.M_CONTENT.encode() + b'"}\n{"otra": 1}\n')
        sub = os.path.join(tree.folder("c--p"), "s1", "subagents")
        os.makedirs(sub)
        self.hardlink(outer, os.path.join(sub, "agent-h.jsonl"))
        with self.assertRaises(ur.SchemaError) as cm:
            self.read(tree)
        self.assertIn(ur.CHK_NO_TYPE, cm.exception.message)
        self.assert_no_markers(cm.exception.message)

    def test_hardlinked_meta_is_still_rejected(self):
        tree = us.Tree(self.base)
        path = tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")], meta=None)
        outer = os.path.join(self.base, "meta-afuera.json")
        with open(outer, "wb") as f:
            f.write(b'{"agentType": "forge"}')
        self.hardlink(outer, path[:-len(".jsonl")] + ".meta.json")
        res = self.read(tree)
        self.assertEqual(res.calls[0].agent, "(sin-meta)")
        self.assertEqual(res.quality["metas rechazadas por enlace duro"], 1)

    def test_symlinked_transcript_is_not_read(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        target = os.path.join(self.base, "objetivo.jsonl")
        us.Tree.write_lines(target, [us.assistant("z", T0 + "1Z")])
        link = os.path.join(tree.projects, "c--p", "s1", "subagents", "agent-l.jsonl")
        if not self.make_link(target, link, is_dir=False):
            self.skipTest("el sistema no permite enlaces de archivo")
        res = self.read(tree)
        self.assertEqual(len(res.calls), 1)
        self.assertGreaterEqual(res.quality["enlaces omitidos"], 1)

    def _big_tree(self):
        tree = us.Tree(self.base)
        items = ["esto no es json", us.assistant("b0", T0 + "1Z", version="2.1.299"),
                 '{"type": "assistant", "x": "' + "y" * 5000 + '"}'] + \
                [us.assistant("b%d" % i, T0 + "2Z", version="2.1.299",
                              blocks=[us.tool_use_block("tb%d" % i, "Read")]) for i in range(1, 60)]
        tree.subagent("c--p", "s1", "big", items)
        return tree

    @staticmethod
    def _lying_fstat():
        real = os.fstat

        def lying(fd):
            values = list(real(fd))
            values[6] = 0
            return os.stat_result(values)

        return lying

    def test_file_over_cap_mid_read_leaves_no_partial_counts(self):
        tree = self._big_tree()
        with mock.patch.object(ur, "MAX_FILE_BYTES", 5000), mock.patch.object(ur.os, "fstat", self._lying_fstat()), \
                mock.patch.object(ur, "MAX_LINE_BYTES", 3000):
            res = self.read(tree, check_damage=False)
        c = res.calls[0]
        self.assertEqual((c.status, c.damage), ("danada", "tope"))
        self.assertEqual((c.requests, c.total_tokens, c.tools), (0, 0, 0))
        self.assertEqual((c.start, c.end, c.versions, c.models), (None, None, (), ()))
        self.assertEqual(res.quality["archivos omitidos por tope de tamano"], 1)
        for label in ("lineas corruptas", "lineas oversize descartadas", "lineas que no son objeto",
                      "usage sin message.id", "hardlinks aceptados"):
            self.assertEqual(res.quality[label], 0, label)
        self.assertNotIn("2.1.299", res.versions)

    def test_file_over_cap_by_fstat_is_omitted_as_damaged(self):
        tree = self._big_tree()
        with mock.patch.object(ur, "MAX_FILE_BYTES", 5000):
            res = self.read(tree, check_damage=False)
        self.assertEqual(res.calls[0].damage, "tope")

    def test_io_error_mid_read_leaves_no_partial_counts(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z"), us.assistant("m2", T0 + "2Z")])
        real = ur._iter_objects

        def failing(f, info):
            it = real(f, info)
            yield next(it)
            raise OSError("fallo " + us.M_CONTENT)

        with mock.patch.object(ur, "_iter_objects", failing):
            res = self.read(tree, check_damage=False)
        c = res.calls[0]
        self.assertEqual((c.damage, c.requests, c.total_tokens), ("ilegible", 0, 0))
        self.assertEqual(res.quality["archivos ilegibles"], 1)
        self.assertEqual(res.versions, {})
        self.assert_no_markers(res.quality, c)

    def test_unopenable_file_is_damaged_call(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        with mock.patch.object(ur, "_open_regular", side_effect=PermissionError(us.M_CONTENT)):
            res = self.read(tree, check_damage=False)
        self.assertEqual(res.calls[0].damage, "ilegible")

    def test_id_cap_marks_call_damaged(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("i%d" % i, T0 + "1Z") for i in range(10)])
        with mock.patch.object(ur, "MAX_IDS_PER_FILE", 3):
            res = self.read(tree, check_damage=False)
        self.assertEqual(res.calls[0].damage, "tope")
        self.assertEqual(res.calls[0].requests, 0)

    def test_oversize_line_contributes_no_tokens_and_is_counted(self):
        tree = us.Tree(self.base)
        huge = json.dumps(us.assistant("big", T0 + "3Z", usage_value=us.usage(5000, 5000, 5000, 5000),
                                       blocks=[us.text_block("x" * 50000)]))
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z"), huge, us.assistant("m2", T0 + "2Z")])
        with mock.patch.object(ur, "MAX_LINE_BYTES", 2000):
            res = self.read(tree)
        c = res.calls[0]
        self.assertEqual((c.input_tokens, c.requests, c.oversize_lines), (20, 2, 1))
        self.assertEqual(res.quality["lineas oversize descartadas"], 1)
        self.assertEqual(c.status, "correcta")


class ReaderDefensive(ReaderBase):
    def _expect_schema(self, tree, check, files=1):
        before = snapshot(self.base)
        with self.assertRaises(ur.SchemaError) as cm:
            self.read(tree)
        msg = cm.exception.message
        self.assertIn(check, msg)
        self.assertIn("%d archivos" % files, msg)
        self.assertIn(ur.VERIFIED_MAX, msg)
        self.assertIn("inspect", msg)
        self.assertNotIn(self.base, msg)
        self.assertNotIn("Traceback", msg)
        msg.encode("ascii")
        self.assert_no_markers(msg)
        self.assertEqual(snapshot(self.base), before)  # nada escrito
        return msg

    def test_usage_not_object(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z", usage_value="texto " + us.M_CONTENT)])
        msg = self._expect_schema(tree, ur.CHK_USAGE_OBJ)
        self.assertIn("2.1.330", msg)  # version vista, filtrada

    def test_token_field_invalid(self):
        for bad in (us.usage(inp=-1), us.usage(inp=True), us.usage(inp="3"), us.usage(inp=1.5),
                    {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 1}):
            with self.subTest(bad=bad):
                tree = us.Tree(os.path.join(self.base, str(abs(hash(repr(bad))))))
                tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z", usage_value=bad)])
                with self.assertRaises(ur.SchemaError) as cm:
                    ur.read_calls(tree.claude_dir)
                self.assertIn(ur.CHK_TOKENS, cm.exception.message)

    def test_timestamp_missing_or_unparseable_in_recognized_line(self):
        for ts in (None, "ayer", 5, "2026-13-45T00:00:00Z"):
            with self.subTest(ts=ts):
                tree = us.Tree(os.path.join(self.base, "t%s" % abs(hash(repr(ts)))))
                line = us.assistant("m1", ts)
                if ts is None:
                    del line["timestamp"]
                tree.subagent("c--p", "s1", "a1", [line])
                with self.assertRaises(ur.SchemaError) as cm:
                    ur.read_calls(tree.claude_dir)
                self.assertIn(ur.CHK_TS, cm.exception.message)

    def test_other_line_types_may_lack_timestamp(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z"), {"type": "summary", "summary": "x"}])
        self.assertEqual(len(self.read(tree).calls), 1)

    def test_meta_without_agent_type_or_not_object(self):
        for meta in ({"toolUseId": "t"}, {"agentType": 5}, {"agentType": None}, b"[1]", b"{no json", b'"texto"'):
            with self.subTest(meta=meta):
                tree = us.Tree(os.path.join(self.base, "m%s" % abs(hash(repr(meta)))))
                tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")], meta=meta)
                with self.assertRaises(ur.SchemaError) as cm:
                    ur.read_calls(tree.claude_dir)
                self.assertIn(ur.CHK_META, cm.exception.message)

    def test_oversize_or_unreadable_meta_is_not_schema_failure(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")],
                      meta=b'{"agentType": "' + b"x" * 100000 + b'"}')
        c = self.one(tree)
        self.assertEqual(c.agent, "(sin-meta)")

    def test_file_with_valid_lines_and_no_type(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [{"foo": 1}, {"bar": 2}])
        self._expect_schema(tree, ur.CHK_NO_TYPE)

    def test_message_counts_files_and_checks(self):
        tree = us.Tree(self.base)
        for i in range(3):
            tree.subagent("c--p", "s1", "a%d" % i, [us.assistant("m1", T0 + "1Z", usage_value="x")])
        tree.subagent("c--p", "s1", "z", [{"foo": 1}])
        with self.assertRaises(ur.SchemaError) as cm:
            self.read(tree)
        self.assertIn(ur.CHK_USAGE_OBJ + ": 3 archivos", cm.exception.message)
        self.assertIn(ur.CHK_NO_TYPE + ": 1 archivos", cm.exception.message)

    def test_truncated_last_line_is_tolerated_and_counted(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z"), '{"type": "assistant", "times'],
                      final_newline=False)
        res = self.read(tree)
        self.assertEqual(res.calls[0].status, "correcta")
        self.assertEqual(res.quality["archivos con ultima linea truncada"], 1)

    def test_middle_corrupt_line_damages_file_and_excludes_tokens(self):
        tree = us.Tree(self.base)
        for i in range(20):
            items = [us.assistant("m%d" % i, T0 + "1Z")]
            if i == 0:
                items = ["basura " + us.M_CONTENT, us.assistant("n", T0 + "2Z")]
            tree.subagent("c--p", "s1", "a%02d" % i, items)
        res = self.read(tree)  # 1 de 20 = 5 %: exacto en el umbral, pasa
        bad = [c for c in res.calls if c.status == "danada"]
        self.assertEqual(len(bad), 1)
        self.assertEqual((bad[0].damage, bad[0].requests, bad[0].total_tokens), ("linea intermedia corrupta", 0, 0))
        self.assertFalse(bad[0].usable)
        self.assertEqual(res.quality["llamadas danadas"], 1)
        self.assertEqual(res.quality["lineas corruptas"], 1)
        self.assert_no_markers(res.calls, res.quality)

    def test_damaged_over_threshold_raises_schema_error(self):
        tree = us.Tree(self.base)
        for i in range(19):
            items = [us.assistant("m%d" % i, T0 + "1Z")]
            if i == 0:
                items = ["basura " + us.M_CONTENT, us.assistant("n", T0 + "2Z")]
            tree.subagent("c--p", "s1", "a%02d" % i, items)
        with self.assertRaises(ur.SchemaError) as cm:
            self.read(tree)
        self.assertIn("1 de 19", cm.exception.message)
        self.assertIn(ur.VERIFIED_MAX, cm.exception.message)
        self.assert_no_markers(cm.exception.message)
        res = self.read(tree, check_damage=False)
        self.assertEqual(len(res.calls), 19)
        with self.assertRaises(ur.SchemaError):
            ur.check_damaged(res.calls)

    def test_schema_error_maps_to_exit_3_without_output(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z", usage_value="x")])

        def cmd(args):
            ur.read_calls(args.claude_dir)
            return 0

        with mock.patch.object(ur, "_cmd_inspect", cmd):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("error: esquema desconocido"))
        self.assertEqual(err.count("\n"), 1)

    def test_environment_errors(self):
        claude = os.path.join(self.base, "sin")
        os.makedirs(claude)
        with self.assertRaises(ur.EnvError) as cm:
            ur.read_calls(claude)
        self.assertIn("projects", cm.exception.message)
        self.assertNotIn(self.base, cm.exception.message)

    def test_no_markers_in_any_result(self):
        tree = rich_tree(self.base)
        res = ur.read_calls(tree.claude_dir, check_damage=False)
        self.assertGreaterEqual(len(res.calls), 5)
        self.assert_no_markers(res.calls, res.quality, res.versions, res.schema)

    def test_ids_are_safe_and_stable(self):
        tree = rich_tree(self.base)
        a = ur.read_calls(tree.claude_dir, check_damage=False)
        b = ur.read_calls(tree.claude_dir, check_damage=False)
        self.assertEqual(a.calls, b.calls)  # determinista
        ids = [c.call_id for c in a.calls]
        self.assertEqual(len(set(ids)), len(ids))
        for c in a.calls:
            self.assertRegex(c.call_id, r"^[0-9a-f]{16}$")
            self.assertRegex(c.session, r"^[0-9a-f]{16}$")
            self.assertRegex(c.project, r"^p-[0-9a-f]{8}$")

    def test_project_filter_and_case_insensitive_folder(self):
        tree = us.Tree(self.base)
        proj = os.path.join(self.base, "my proj")
        os.makedirs(proj)
        folder = us.folder_name_for(os.path.abspath(proj))
        tree.subagent(folder.swapcase(), "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        tree.subagent("c--otra", "s2", "a2", [us.assistant("m2", T0 + "1Z")])
        self.assertEqual(len(ur.read_calls(tree.claude_dir, project_dir=proj).calls), 1)
        self.assertEqual(len(ur.read_calls(tree.claude_dir).calls), 2)

    def test_session_with_only_main_file_is_not_a_call(self):
        tree = us.Tree(self.base)
        tree.main_session("c--p", "s1", [us.assistant("m1", T0 + "1Z")])
        self.assertEqual(ur.read_calls(tree.claude_dir).calls, [])

    def test_reader_only_touches_documented_keys(self):
        # lista cerrada de claves que el lector accede, por recorrido AST del bloque del lector
        with open(SCRIPT, "rb") as f:
            src = f.read().decode("utf-8")
        start = src.index("# --- Lector de subagentes (T2) ---")
        end = src.index("# Orden fijo de las lineas del resumen")
        used = keys_used_by(src[start:end])
        self.assertGreater(len(used), 5)   # el recorrido no esta vacio
        keys = {"type", "timestamp", "version", "message", "model", "id", "usage", "content", "agentType"}
        # valores de comparaciones `in` (no son claves) y etiquetas de los contadores de calidad que
        # el lector LEE en las propiedades de ReadResult
        values = {"user", "assistant", ":", "(otro modelo)"}
        labels = {"usage sin message.id", "message.id repetido entre archivos",
                  "message.id sin deduplicar entre archivos (tope)"}
        self.assertLessEqual(used, keys | values | labels | set(ur.TOKEN_FIELDS))
        self.assertEqual(ur.TOKEN_FIELDS, ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                           "cache_read_input_tokens"))

    def test_key_extractor_detects_evasions(self):
        for snippet, expected in (
            ('x = meta["agentType"]', {"agentType"}),
            ('x = obj["cwd"]', {"cwd"}),
            ('if "cwd" in obj: pass', {"cwd"}),
            ('if "cwd" not in obj: pass', {"cwd"}),
            ('if k in ("gitBranch", "cwd"): pass', {"gitBranch", "cwd"}),
            ('x = obj.get("prompt")', {"prompt"}),
            ('x = obj.get("prompt", {}).get("description")', {"prompt", "description"}),
            ('x = obj.pop("slug")', {"slug"}),
            ('x = obj.setdefault("slug", 1)', {"slug"}),
            ('x = a.b.c["toolUseResult"]["content"]', {"toolUseResult", "content"}),
        ):
            with self.subTest(snippet=snippet):
                self.assertEqual(keys_used_by(snippet), expected)
        # un contador que se escribe (q["x"] += 1) no es una clave de transcripcion
        self.assertEqual(keys_used_by('q["llamadas leidas"] += 1\nr = 3'), set())


def keys_used_by(source: str) -> set:
    """Constantes de cadena usadas como clave: subindices (solo lectura), `in`/`not in` y
    llamadas .get/.pop/.setdefault."""
    found = set()

    def consts(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
        elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for elt in node.elts:
                consts(elt)

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            consts(node.slice)
        elif isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
            consts(node.left)
            for comparator in node.comparators:
                consts(comparator)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in ("get", "pop", "setdefault") and node.args):
            consts(node.args[0])
    return found


class ReaderAuditFixes(ReaderBase):
    # --- 1. plugins ---
    def test_plugin_agents_are_grouped_by_validated_prefix(self):
        self.assertEqual(ur.classify_agent("miplugin:agente"), ("plugin:miplugin", "plugin:miplugin"))
        self.assertEqual(ur.classify_agent("otro-2:agente:mas"), ("plugin:otro-2", "plugin:otro-2"))
        self.assertEqual(ur.classify_agent("0a:x"), ("plugin:0a", "plugin:0a"))
        self.assertEqual(ur.classify_agent("a" * 32 + ":x")[1], "plugin:" + "a" * 32)
        self.assertNotEqual(ur.classify_agent("p1:x")[1], ur.classify_agent("p2:x")[1])
        self.assertEqual(ur.classify_agent("forge:x")[1], "plugin:forge")   # no se confunde con SyncLayer
        for raw in ("Foo:x", "fo o:x", "a@b:x", "a/b:x", ":x", "a" * 33 + ":x", "-a:x", "foo\n:x",
                    "a.b:x", us.M_TYPE + ":x", "２a:x", "a_b:x"):
            self.assertEqual(ur.classify_agent(raw), ("(otro agente)", "plugin:(no-valido)"), repr(raw))

    def test_user_agent_is_not_mixed_with_plugin_agent(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")], meta={"agentType": "mi-agente"})
        tree.subagent("c--p", "s1", "a2", [us.assistant("m2", T0 + "1Z")], meta={"agentType": "pl1:mi-agente"})
        tree.subagent("c--p", "s1", "a3", [us.assistant("m3", T0 + "1Z")], meta={"agentType": "pl2:mi-agente"})
        tree.subagent("c--p", "s1", "a4", [us.assistant("m4", T0 + "1Z")], meta={"agentType": "pl1:otro"})
        res = self.read(tree)
        self.assertEqual(sorted(c.agent_group for c in res.calls), ["otros", "plugin:pl1", "plugin:pl1", "plugin:pl2"])

    def test_text_after_colon_never_appears(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")],
                      meta={"agentType": "pl:" + us.M_TYPE + us.M_PROMPT})
        tree.subagent("c--p", "s1", "a2", [us.assistant("m2", T0 + "1Z")],
                      meta={"agentType": us.M_TYPE + ":" + us.M_PROMPT})
        res = self.read(tree)
        self.assertEqual([(c.agent, c.agent_group) for c in res.calls],
                         [("plugin:pl", "plugin:pl"), ("(otro agente)", "plugin:(no-valido)")])
        self.assert_no_markers(res.calls, res.quality)

    # --- 2. versiones en el mensaje de esquema ---
    def _many_versions(self, extra_items, count=40):
        tree = us.Tree(self.base)
        for i in range(count):
            tree.subagent("c--p", "s1", "a%02d" % i,
                          [us.assistant("m%d" % i, T0 + "1Z", version="2.1.%d" % (300 + i))])
        tree.subagent("c--p", "s1", "z-new", extra_items)
        return tree

    def test_schema_message_shows_range_and_the_new_failing_version(self):
        tree = self._many_versions([us.assistant("mx", T0 + "1Z", usage_value="x", version="2.1.340")])
        with self.assertRaises(ur.SchemaError) as cm:
            self.read(tree)
        msg = cm.exception.message
        self.assertIn("2.1.300 a 2.1.340 (41 versiones)", msg)
        self.assertIn("En archivos que fallan: 2.1.340", msg)
        self.assertIn("Posteriores a la ultima verificada", msg)
        self.assertIn(ur.VERIFIED_MAX, msg)
        msg.encode("ascii")
        self.assertLess(msg.index("2.1.340"), msg.index("2.1.339"))   # mas recientes primero
        self.assertNotIn("2.1.305", msg)   # no vuelca la lista entera

    def test_shown_versions_are_limited_and_recent_first(self):
        text = ur._versions_text(
            collections.Counter("2.1.%d" % n for n in range(300, 340)),
            collections.Counter("2.1.%d" % n for n in range(320, 340)))
        self.assertIn("2.1.300 a 2.1.339 (40 versiones)", text)
        later = text.split("Posteriores", 1)[1]
        self.assertLessEqual(len(set(re.findall(r"2\.1\.\d+", later))), 2 * ur.MAX_SHOWN_VERSIONS)
        self.assertIn("mas)", text)
        self.assertEqual(ur._versions_text(collections.Counter()), "(ninguna)")
        self.assertEqual(ur._versions_text(collections.Counter(["2.1.300"])), "2.1.300 (1 version)")

    def test_damaged_message_shows_versions_of_damaged_files(self):
        tree = us.Tree(self.base)
        for i in range(18):
            tree.subagent("c--p", "s1", "a%02d" % i,
                          [us.assistant("m%d" % i, T0 + "1Z", version="2.1.%d" % (300 + i))])
        tree.subagent("c--p", "s1", "z", ["basura", us.assistant("n", T0 + "2Z", version="2.1.350")])
        with self.assertRaises(ur.SchemaError) as cm:
            self.read(tree)
        msg = cm.exception.message
        self.assertIn("1 de 19", msg)
        self.assertIn("2.1.300 a 2.1.350 (19 versiones)", msg)
        self.assertIn("En archivos que fallan: 2.1.350", msg)

    # --- 3. deduplicacion entre archivos ---
    def test_message_id_repeated_across_files_counts_once_and_is_reported(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("dup", T0 + "1Z", usage_value=us.usage(10, 1, 1, 1))])
        tree.subagent("c--p", "s2", "a2", [us.assistant("dup", T0 + "2Z", usage_value=us.usage(10, 1, 1, 1)),
                                           us.assistant("nuevo", T0 + "3Z", usage_value=us.usage(5, 1, 1, 1))])
        res = self.read(tree)
        first, second = res.calls
        self.assertEqual((first.requests, first.input_tokens), (1, 10))
        self.assertEqual((second.requests, second.input_tokens), (1, 5))   # el segundo archivo no suma `dup`
        self.assertEqual(res.quality["message.id repetido entre archivos"], 1)
        self.assertEqual(sum(c.input_tokens for c in res.calls), 15)
        self.assertTrue(any("repetidos entre archivos" in w for w in res.warnings))

    def test_file_fully_duplicated_keeps_has_usage_with_zero_requests(self):
        tree = us.Tree(self.base)
        for n in ("a1", "a2"):
            tree.subagent("c--p", "s1", n, [us.assistant("dup", T0 + "1Z")])
        first, second = self.read(tree).calls
        self.assertEqual((second.requests, second.total_tokens, second.has_usage), (0, 0, True))
        self.assertEqual(first.requests, 1)

    def test_damaged_file_does_not_register_its_ids(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", ["basura", us.assistant("dup", T0 + "1Z")])
        tree.subagent("c--p", "s1", "a2", [us.assistant("dup", T0 + "1Z")])
        res = self.read(tree, check_damage=False)
        self.assertEqual([c.requests for c in res.calls], [0, 1])
        self.assertEqual(res.quality["message.id repetido entre archivos"], 0)

    def test_same_id_twice_in_one_file_is_not_cross_file(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("dup", T0 + "1Z"), us.assistant("dup", T0 + "2Z")])
        res = self.read(tree)
        self.assertEqual(res.calls[0].requests, 1)
        self.assertEqual(res.quality["message.id repetido entre archivos"], 0)
        self.assertEqual(res.warnings, [])

    def test_global_id_set_is_capped_and_reported(self):
        tree = us.Tree(self.base)
        for i in range(4):
            tree.subagent("c--p", "s1", "a%d" % i, [us.assistant("i%d" % i, T0 + "1Z")])
        tree.subagent("c--p", "s1", "b", [us.assistant("i0", T0 + "1Z")])   # repetido, dentro del tope
        with mock.patch.object(ur, "MAX_IDS_GLOBAL", 2):
            res = self.read(tree)
        self.assertEqual(len(res.calls), 5)
        self.assertEqual(res.quality["message.id repetido entre archivos"], 1)
        self.assertEqual(res.quality["message.id sin deduplicar entre archivos (tope)"], 2)
        self.assertTrue(any("tope" in w for w in res.warnings))

    # --- 4. usage sin message.id ---
    def test_usage_without_message_id_gives_a_fixed_warning(self):
        tree = us.Tree(self.base)
        line = us.assistant("x", T0 + "1Z")
        del line["message"]["id"]
        tree.subagent("c--p", "s1", "a1", [line])
        res = self.read(tree)
        self.assertEqual(res.quality["usage sin message.id"], 1)
        self.assertTrue(res.usage_without_message_id)
        self.assertEqual(res.warnings, [ur.WARN_NO_MESSAGE_ID])
        ur.WARN_NO_MESSAGE_ID.encode("ascii")
        clean = us.Tree(os.path.join(self.base, "limpio"))
        clean.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        res = self.read(clean)
        self.assertFalse(res.usage_without_message_id)
        self.assertEqual(res.warnings, [])

    def test_usage_without_id_in_damaged_file_is_not_counted(self):
        tree = us.Tree(self.base)
        line = us.assistant("x", T0 + "1Z")
        del line["message"]["id"]
        tree.subagent("c--p", "s1", "a1", ["basura", line])
        res = self.read(tree, check_damage=False)
        self.assertEqual(res.quality["usage sin message.id"], 0)
        self.assertEqual(res.warnings, [])

    # --- 5. modelo del meta ---
    def test_meta_inherit_is_not_a_model(self):
        tree = us.Tree(self.base)
        line = us.assistant("m1", T0 + "1Z")
        del line["message"]["model"]
        tree.subagent("c--p", "s1", "a1", [line], meta={"agentType": "forge", "model": "inherit"})
        tree.subagent("c--p", "s1", "a2", [us.assistant("m2", T0 + "1Z")],
                      meta={"agentType": "forge", "model": "inherit"})
        first, second = self.read(tree).calls
        self.assertEqual((first.model, first.models, first.model_source, first.model_mismatch),
                         ("(desconocido)", (), None, False))
        self.assertEqual((second.model, second.model_source, second.model_mismatch),
                         ("claude-opus-4-1", "lineas", False))

    def test_model_mismatch_ignores_date_suffix_and_aliases(self):
        cases = (
            ("claude-sonnet-4-5", "claude-sonnet-4-5-20250929", False),
            ("claude-sonnet-4-5-20250929", "claude-sonnet-4-5", False),
            ("claude-sonnet-4-5@20250929", "claude-sonnet-4-5-20250929", False),
            ("claude-sonnet-4-5-20250929", "claude-sonnet-4-5-20251001", False),
            ("claude-sonnet-4-5", "claude-sonnet-4-5", False),
            ("sonnet", "claude-opus-4-1", False),
            ("opus", "claude-opus-4-1-20250805", False),
            ("inherit", "claude-opus-4-1", False),
            (us.M_MODEL, "claude-opus-4-1", False),
            ("claude-sonnet-4-5", "claude-opus-4-1-20250805", True),
            ("claude-sonnet-4-5-20250929", "claude-sonnet-4-4-20250929", True),
            ("claude-sonnet-4", "claude-sonnet-4-5", True),
        )
        for i, (meta_model, line_model, expected) in enumerate(cases):
            with self.subTest(meta=meta_model, line=line_model):
                tree = us.Tree(os.path.join(self.base, "c%d" % i))
                tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z", model=line_model)],
                              meta={"agentType": "forge", "model": meta_model})
                res = self.read(tree)
                self.assertEqual(res.calls[0].model_mismatch, expected)
                self.assertEqual(res.quality["llamadas con modelo distinto del meta"], int(expected))

    def test_model_mismatch_with_mixed_lines_and_dated_meta(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z", model="claude-opus-4-1-20250805"),
                                           us.assistant("m2", T0 + "2Z", model="claude-haiku-4-5-20251001")],
                      meta={"agentType": "forge", "model": "claude-haiku-4-5"})
        c = self.one(tree)
        self.assertEqual((c.model, c.model_mismatch), ("mixto", False))

    # --- 6. hora de respaldo ---
    def test_fallback_time_is_file_mtime_in_utc(self):
        tree = us.Tree(self.base)
        path = tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        empty = tree.subagent("c--p", "s1", "a2", [])
        trunc = tree.subagent("c--p", "s1", "a3", ['{"type": "assistant", "times'], final_newline=False)
        epoch = 1_800_000_000
        for p in (path, empty, trunc):
            os.utime(p, (epoch, epoch))
        res = self.read(tree)
        expected = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
        for c in res.calls:
            self.assertEqual(c.fallback_time, expected)
            self.assertEqual(c.fallback_time.utcoffset(), datetime.timedelta(0))
        self.assertIsNotNone(res.calls[0].start)
        self.assertEqual([c.start for c in res.calls[1:]], [None, None])

    def test_fallback_time_for_cap_damage_and_none_when_unopenable(self):
        tree = us.Tree(self.base)
        path = tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        os.utime(path, (1_800_000_000, 1_800_000_000))
        with mock.patch.object(ur, "MAX_FILE_BYTES", 10):
            c = self.read(tree, check_damage=False).calls[0]
        self.assertEqual((c.damage, c.start), ("tope", None))
        self.assertEqual(c.fallback_time.timestamp(), 1_800_000_000)
        with mock.patch.object(ur, "_open_regular", side_effect=PermissionError(us.M_CONTENT)):
            c = self.read(tree, check_damage=False).calls[0]
        self.assertEqual((c.damage, c.fallback_time), ("ilegible", None))

    # --- 7. damage / excluded / usable ---
    def test_damaged_call_keeps_everything_but_tokens(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [
            us.assistant("m1", T0 + "1Z", version="2.1.310", blocks=[us.tool_use_block("t1", "Read")]),
            "basura " + us.M_CONTENT,
            us.assistant("m2", T0 + "5Z", version="2.1.311", model="claude-haiku-4-5"),
        ])
        c = self.read(tree, check_damage=False).calls[0]
        self.assertEqual((c.damage, c.status), ("linea intermedia corrupta", "danada"))
        self.assertTrue(c.excluded)
        self.assertFalse(c.usable)
        self.assertTrue(c.has_usage)
        self.assertEqual((c.requests, c.total_tokens), (0, 0))
        self.assertEqual(c.tools, 1)
        self.assertEqual(c.versions, ("2.1.310", "2.1.311"))
        self.assertEqual(c.models, ("claude-haiku-4-5", "claude-opus-4-1"))
        self.assertEqual((c.start.second, c.end.second), (1, 5))

    def test_sin_usage_is_not_excluded_but_not_usable(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.user(T0 + "0Z"),
                                           us.assistant("m1", T0 + "9Z", usage_value=None,
                                                        blocks=[us.tool_use_block("t1", "Read")])])
        tree.subagent("c--p", "s1", "a2", [us.assistant("m2", T0 + "1Z")])
        sin_usage, ok = self.read(tree).calls
        self.assertEqual(sin_usage.status, "sin_usage")
        self.assertFalse(sin_usage.excluded)
        self.assertFalse(sin_usage.usable)
        self.assertEqual((sin_usage.tools, sin_usage.start.second, sin_usage.end.second), (1, 0, 9))
        self.assertFalse(ok.excluded)
        self.assertTrue(ok.usable)

    def test_failed_file_is_excluded_and_empty(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        with mock.patch.object(ur, "MAX_FILE_BYTES", 10):
            c = self.read(tree, check_damage=False).calls[0]
        self.assertTrue(c.excluded)
        self.assertFalse(c.usable)
        self.assertEqual((c.tools, c.start, c.end, c.versions, c.models), (0, None, None, (), ()))

    # --- 8. hardlinks aceptados aunque falle ---
    def _hardlinked_big(self, tree):
        outer = us.Tree(os.path.join(self.base, "afuera"))
        target = outer.subagent("c--x", "s9", "a9", [us.assistant("h%d" % i, T0 + "1Z") for i in range(40)],
                                meta=None)
        sub = os.path.join(tree.folder("c--p"), "s1", "subagents")
        os.makedirs(sub)
        self.hardlink(target, os.path.join(sub, "agent-h.jsonl"))

    def test_hardlink_counted_when_file_exceeds_cap(self):
        tree = us.Tree(self.base)
        self._hardlinked_big(tree)
        with mock.patch.object(ur, "MAX_FILE_BYTES", 500):
            res = self.read(tree, check_damage=False)
        self.assertEqual(res.calls[0].damage, "tope")
        self.assertTrue(res.calls[0].hardlink)
        self.assertEqual(res.quality["hardlinks aceptados"], 1)

    def test_hardlink_counted_when_file_is_unreadable_mid_read(self):
        tree = us.Tree(self.base)
        self._hardlinked_big(tree)
        real = ur._iter_objects

        def failing(f, info):
            it = real(f, info)
            yield next(it)
            raise OSError("fallo")

        with mock.patch.object(ur, "_iter_objects", failing):
            res = self.read(tree, check_damage=False)
        self.assertEqual(res.calls[0].damage, "ilegible")
        self.assertTrue(res.calls[0].hardlink)
        self.assertEqual(res.quality["hardlinks aceptados"], 1)

    def test_hardlink_not_counted_for_regular_failed_file(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        with mock.patch.object(ur, "MAX_FILE_BYTES", 10):
            res = self.read(tree, check_damage=False)
        self.assertFalse(res.calls[0].hardlink)
        self.assertEqual(res.quality["hardlinks aceptados"], 0)

    # --- 12. un solo enumerador ---
    def test_reader_and_inspect_enumerate_the_same_way(self):
        tree = us.Tree(self.base)
        tree.subagent("c--ok", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        folder = tree.folder("c--ok")
        for name in ("a b.jsonl", "con.jsonl", "s.1.jsonl"):
            with open(os.path.join(folder, name), "wb") as f:
                f.write(b"{}\n")
        os.makedirs(os.path.join(folder, "s 2", "subagents"))
        res = self.read(tree)
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(res.quality["nombres no validos omitidos"], field(out, "nombres no validos omitidos"))
        self.assertEqual(res.quality["nombres no validos omitidos"], 4)
        self.assertEqual(res.quality["carpetas de proyecto leidas"], field(out, "carpetas de proyecto leidas"))


class InspectHardlinkSessions(Base):
    def test_session_whose_only_file_is_a_hardlinked_main_is_not_read(self):
        tree = us.Tree(self.base)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        main = outer.main_session("c--x", "s9", [us.assistant("m9", T0 + "1Z")])
        folder = tree.folder("c--p")
        try:
            os.link(main, os.path.join(folder, "s1.jsonl"))
        except (OSError, NotImplementedError) as e:
            self.skipTest("el sistema no permite hardlinks: %s" % e)
        code, out, err = self.inspect(tree)
        self.assertEqual(code, 1)  # ninguna sesion leida: no hay transcripciones
        self.assertEqual(out, "")

    def test_partial_file_leaves_no_lines_counted_in_inspect(self):
        tree = us.Tree(self.base)
        for i in range(30):
            tree.subagent("c--p", "s1", "a%d" % i, [us.assistant("m1", T0 + "1Z")])
        items = ["no es json"] + [us.assistant("b%d" % i, T0 + "1Z") for i in range(60)]
        tree.subagent("c--p", "s1", "big", items)
        with mock.patch.object(ur, "MAX_FILE_BYTES", 5000), \
                mock.patch.object(ur.os, "fstat", ReaderHardlinksAndLimits._lying_fstat()):
            code, out, err = self.inspect(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(field(out, "archivos omitidos por tope de tamano"), 1)
        self.assertEqual(field(out, "subagente lineas"), 30)
        self.assertEqual(field(out, "lineas corruptas"), 0)
        self.assertEqual(field(out, "subagente lineas assistant con usage"), 30)


if __name__ == "__main__":
    unittest.main()
