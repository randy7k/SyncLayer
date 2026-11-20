import ast
import collections
import contextlib
import dataclasses
import datetime
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
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

    def _two_names_of_one_inode(self):
        tree = us.Tree(self.base)
        first = tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")], meta=None)
        self.hardlink(first, os.path.join(os.path.dirname(first), "agent-a2.jsonl"))
        return tree

    @staticmethod
    def _fstat_of_read_call(ino=None, dev=None):
        """os.fstat que solo miente cuando lo llama `_read_call` (el de `_open_regular` compara la
        identidad con el lstat previo y no debe verse afectado). `dev` es una funcion del numero de
        llamada (0, 1, ...)."""
        real = os.fstat
        counter = [0]

        def lying(fd):
            result = real(fd)
            if sys._getframe(1).f_code.co_name != "_read_call":
                return result
            values = list(result)
            if ino is not None:
                values[1] = ino
            if dev is not None:
                values[2] = dev(counter[0])
            counter[0] += 1
            return os.stat_result(values)

        return lying

    def test_two_names_of_one_inode_are_one_call_and_the_other_is_counted_apart(self):
        res = self.read(self._two_names_of_one_inode())
        self.assertEqual(len(res.calls), 1)
        self.assertEqual(res.quality["hardlinks duplicados dentro de projects"], 1)
        self.assertEqual(res.quality["hardlinks aceptados"], 1)

    def test_inode_zero_is_never_used_to_deduplicate(self):
        # un sistema que no informa st_ino (0): dos hardlinks no se pueden identificar -> dos llamadas
        tree = self._two_names_of_one_inode()
        with mock.patch.object(ur.os, "fstat", self._fstat_of_read_call(ino=0)):
            res = self.read(tree)
        self.assertEqual(len(res.calls), 2)
        self.assertEqual(res.quality["hardlinks duplicados dentro de projects"], 0)
        self.assertEqual(res.quality["hardlinks aceptados"], 2)

    def test_deduplication_key_includes_the_device(self):
        tree = self._two_names_of_one_inode()
        # mismo inodo en dos dispositivos distintos: son archivos distintos -> dos llamadas
        with mock.patch.object(ur.os, "fstat", self._fstat_of_read_call(dev=lambda n: 100 + n)):
            res = self.read(tree)
        self.assertEqual(len(res.calls), 2)
        self.assertEqual(res.quality["hardlinks duplicados dentro de projects"], 0)
        # mismo inodo y mismo dispositivo simulado: una llamada
        with mock.patch.object(ur.os, "fstat", self._fstat_of_read_call(dev=lambda n: 100)):
            res = self.read(tree)
        self.assertEqual(len(res.calls), 1)
        self.assertEqual(res.quality["hardlinks duplicados dentro de projects"], 1)

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
        # los resumenes llevan una clave aleatoria por ejecucion: con la misma clave inyectada la
        # lectura es determinista; sin ella, dos lecturas dan identificadores distintos (ver
        # ReaderRandomKey)
        key = b"k" * 16
        a = ur.read_calls(tree.claude_dir, check_damage=False, digest_key=key)
        b = ur.read_calls(tree.claude_dir, check_damage=False, digest_key=key)
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
        # T4 (skills): de un bloque tool_use solo `name` e `input`; de `input` solo `skill`
        keys = {"type", "timestamp", "version", "message", "model", "id", "usage", "content", "agentType",
                "name", "input", "skill"}
        # valores de comparaciones `in` (no son claves) y etiquetas de los contadores de calidad que
        # el lector LEE en las propiedades de ReadResult
        values = {"user", "assistant", ":", "(otro modelo)"}
        labels = {"usage sin message.id", "message.id repetido entre archivos",
                  "message.id sin deduplicar entre archivos (tope)",
                  "skills: id repetido entre archivos", "skills: ids sin deduplicar (tope)",
                  "sesiones principales omitidas por enlace duro",
                  "sesiones principales omitidas por tope de tamano", "sesiones principales ilegibles",
                  "alias de proyecto repetido entre carpetas",
                  "carpetas de proyecto leidas"}   # T7: ReadResult.folders_read
        self.assertLessEqual(used, keys | values | labels | set(ur.TOKEN_FIELDS))
        self.assertEqual(ur.TOKEN_FIELDS, ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                           "cache_read_input_tokens"))
        # nada de iterar un diccionario de la transcripcion ni de accederlo con una clave en una
        # variable, salvo los diccionarios propios del lector y `usage.get(name)` (name de TOKEN_FIELDS)
        self.assertEqual(unsafe_key_access(src[start:end]), [])
        self.assertIn("for name in TOKEN_FIELDS", src[start:end])
        # `args` puede llevar contenido; `isSidechain` y `agentId` no se leen (el origen de una skill
        # sale del archivo en que se encuentra); `description`, `prompt`, `cwd`... tampoco
        for never in ("args", "isSidechain", "agentId", "description", "prompt", "cwd", "gitBranch",
                      "toolUseResult", "toolUseId", "sessionId"):
            self.assertNotIn(never, used)

    def test_unsafe_access_detector_catches_evasions(self):
        for snippet in (
            "for k, v in obj.items(): pass",
            "x = list(obj.values())",
            "x = obj.keys()",
            "x = obj[k]",
            "x = obj.get(k)",
            "x = obj.get(k, 1)",
            "x = a.b.pop(k)",
            "x = obj.setdefault(k, 1)",
            # evasiones del subindice: no basta con que la clave no sea un Name/Call/BinOp
            "x = obj[x.y]",
            "x = obj[a[0]]",
            "x = obj[k if c else j]",
            'x = obj[f"{k}"]',
            "x = obj[k, 1]",
            "x = obj[:k]",
            "x = obj[1:k]",
            "x = obj[int(k)]",
            # el nombre suelto de un receptor propio ya no vale: solo la ruta completa
            "for e in content:\n    e.items()",
            "x = e[k]",
            "x = schema[k]",
            "x = usage_by_id[k]",
            "x = other.usage_by_id[k]",
            "x = e.get(k)",
            # recorridos y copias de un diccionario de la transcripcion
            "for k in obj: pass",
            "x = [k for k in obj]",
            "x = {k: 1 for k in obj}",
            "x = dict(obj)",
            "x = dict(**obj)",
            "x = list(obj)",
            "x = sorted(obj)",
            "x = tuple(obj)",
            "x = {**obj}",
            "x = json.dumps(obj)",
            "json.dump(obj, f)",
            "for k in (obj or ()): pass",
            # `name` solo vale dentro de `for name in TOKEN_FIELDS`
            "x = usage.get(name)",
            "for name in OTHER:\n    x = usage.get(name)",
            "for name in TOKEN_FIELDS:\n    pass\nx = usage.get(name)",
            "for key in TOKEN_FIELDS:\n    x = usage.get(key)",
            "for name in TOKEN_FIELDS:\n    x = usage.get(name2)",
        ):
            with self.subTest(snippet=snippet):
                self.assertTrue(unsafe_key_access(snippet), snippet)
        for snippet in (
            # los unicos usos permitidos de `name`: dentro de `for name in TOKEN_FIELDS`
            "for name in TOKEN_FIELDS:\n    x = usage.get(name)",
            "for name in TOKEN_FIELDS:\n    y = usage[name]",
            "x = kinds.get(meta_name)",            # ruta propia completa
            "x = acc.usage_by_id.items()",
            "x = list(acc.usage_by_id.values())",
            "x = res.schema[check]",
            "x = acc.usage_by_id[key]",
            "x = dict(listing)",
            "x = sorted(res.schema)",
            "for c in calls: pass",
            "x = items[1:]",                       # un corte con limites constantes
            "x = ordered[:MAX_SHOWN_VERSIONS]",
            "x = name[:-len('.jsonl')]",
            "x = numeric[-1]",
            'x = obj["type"]',                     # constante: lo revisa keys_used_by
            'q["a" if c else "b"] += 1',           # un IfExp de constantes sigue siendo constante
            "x = obj.get('type')",
            "x = json.dumps(acc.usage_by_id)",
        ):
            with self.subTest(snippet=snippet):
                self.assertEqual(unsafe_key_access(snippet), [], snippet)

    def test_unsafe_access_detector_catches_formatting_and_content_evasions(self):
        # T4 (Minor 5): `content` ya no es una ruta propia (solo `for block in content`), y pasar un
        # diccionario o texto de la transcripcion a str/repr/format/f-string/% o desempaquetarlo
        # (Starred) tambien se rechaza
        for snippet in (
            # `content` solo vale como iterable de `for block in content`
            "x = content[k]",
            "x = content.items()",
            "x = content.get(k)",
            "for k in content: pass",
            "for blk in content: pass",
            "for block in other: pass",
            "x = [b for b in content]",
            "x = [block for block in content]",
            "x = list(content)",
            "x = sorted(content)",
            "x = dict(content)",
            # convertir a texto una ruta ajena
            "x = str(obj)",
            "x = repr(obj)",
            "x = ascii(obj)",
            "x = format(obj)",
            "x = str(obj.get('type'))",
            "x = str(content)",
            'x = "{}".format(obj)',
            'x = "{a}".format(a=obj)',
            'x = "{}".format(a.b)',
            'x = f"{obj}"',
            'x = f"{obj!r}"',
            'x = f"{a.b}"',
            'x = f"{content}"',
            'x = f"{obj[0]}"',
            'x = "%s" % obj',
            'x = "%s %s" % (a, obj)',
            'x = "%s" % (obj,)',
            'x = "%s" % obj[0]',
            'x = "%s" % f(obj)',
            'x = "%s" % content',
            'x = fmt % obj',
            # desempaquetar (Starred)
            "f(*obj)",
            "print(*obj)",
            "x = [*obj]",
            "x = (*obj,)",
            "x = {*obj}",
            "f(**obj)",
            # T4 (Minor 3): concatenar, unir, formatear o acumular un valor ajeno
            'x = a + obj.get("name")',
            'x = "k:" + obj["name"]',
            'x = prefix + block.get("name")',
            'x = obj.get("a") + "k"',
            'x += obj.get("name")',
            'name = block.get("name")\nx = "k:" + name',
            'name = block.get("name")\nx = name + "k"',
            'raw = a.get("x")\ny = raw\nx = "k:" + y',
            'x = "".join([obj.get("a"), "b"])',
            'x = ",".join(obj.get("a"))',
            'x = ", ".join(str(v) for v in [obj["a"]])',
            'name = block.get("name")\nx = "".join([name, "b"])',
            'name = block.get("name")\nx = ",".join((name,))',
            'x = "{a}".format_map(obj)',
            'x = "{a}".format_map(a.b)',
            "x = obj.__str__()",
            "x = obj.__repr__()",
            'x = obj.__format__("")',
            "x = type(obj).__repr__(obj)",
            "x = a.b.__str__",
            'x = bytes(raw, "utf-8")',
            'x = bytes(obj.get("a"), "utf-8")',
            "x = bytearray(raw)",
            'lst.append(obj.get("name"))',
            'name = block.get("name")\nlst.append(name)',
            'name = block.get("name")\nother.items.append(name)',
            'out.append(block.get("name"))',
            'out.append((1, block.get("name")))',
            'name = block.get("name")\nx = "%s" % name',
            'name = block.get("name")\nx = "%s: %d" % (name, 1)',
            'name = block.get("name")\nx = f"{name}"',
            'name = block.get("name")\nx = "{}".format(name)',
            'name = block.get("name")\nx = str(name)',
            'name = block.get("name")\nx = repr(name)',
            # `name` suelto ya no es un escalar del lector: solo dentro de un bucle cerrado
            'x = "%s" % name',
            'x = "%s: %d" % (name, 1)',
            'x = f"{name}"',
            'x = "{}".format(name)',
            "x = str(name)",
            'for name in OTHER:\n    x = "%s" % name',
            'for name in TOKEN_FIELDS:\n    pass\nx = "%s" % name',
            'for key in TOKEN_FIELDS:\n    x = "%s" % name',
            'x = ["%s" % name for name in obj]',
            'x = ["%s" % name for name in sorted(obj)]',
            'for name in TOKEN_FIELDS:\n    name = block.get("x")\n    y = "%s" % name',
        ):
            with self.subTest(snippet=snippet):
                self.assertTrue(unsafe_key_access(snippet), snippet)
        # lo que sigue es seguro: rutas propias, escalares del lector, constantes y len(...)
        for snippet in (
            "for block in content:\n    pass",
            "for block in content:\n    x = block",
            "x = 'a %s' % acc.versions",
            "x = str(acc.versions)",
            "x = repr(res.quality)",
            "x = f'{res.quality}'",
            'x = "%d of %d" % (damaged, total)',
            'for name in TOKEN_FIELDS:\n    x = "%s" % name',
            'x = ["%s: %d archivos" % (name, res.schema[name]) for name in sorted(res.schema)]',
            'x = ["%s: %d" % (name, res.schema[name]) for name in res.schema]',
            'x = " (+%d mas)" % (len(ordered) - MAX_SHOWN_VERSIONS)',
            'x = "%s" % numeric[0]',
            'x = "{}".format(acc.versions)',
            # T4 (Minor 3): los usos reales del lector son seguros
            'x = "plugin:" + prefix',
            'x = folder_name + "\\0" + sid + "\\0" + stem',
            'x = stem + ".meta.json"',
            'x = name[:-len(".jsonl")] + ".meta.json"',
            'text = "a" + _recent_first(later)',
            'text += ". Posteriores: " + _recent_first(later)',
            'x = ", ".join(ordered[:MAX_SHOWN_VERSIONS])',
            'x = "".join(out)',
            'x = b"".join(out)',
            'x = "; ".join(parts)',
            "out.append(value)",
            "acc.skills.append((key, label, group, ts, isinstance(raw, str)))",
            "acc.usage_no_id.append(tokens)",
            "lst.append(n)",
            "x = bytes(3)",
            'x = "{a}".format_map(acc.versions)',
            'kind = obj.get("type")\nif kind == "assistant":\n    n = 1',
            'raw = tool_input.get("skill")\nlabel, group = classify_skill(raw)\nx = "a" + label',
            'message = obj.get("message")\nok = isinstance(message, dict)',
            'x = f"{len(ordered)} {MAX_SHOWN_VERSIONS}"',
            "x = 7 % 3",
            "x = [*acc.versions]",
            "f(*calls)",
        ):
            with self.subTest(snippet=snippet):
                self.assertEqual(unsafe_key_access(snippet), [], snippet)

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


# Contenedores PROPIOS del lector (no son lineas de la transcripcion): el acumulador por archivo, el
# listado de directorio, los contadores de ReadResult, listas locales y las constantes del modulo.
# Se aceptan SOLO por ruta completa: un nombre suelto como `e` o `schema` no vale, porque cualquier
# variable que apunte a una linea de la transcripcion podria llamarse asi.
OWN_PATHS = frozenset((
    "acc.usage_by_id", "acc.usage_no_id", "acc.schema", "acc.versions", "acc.tools",
    "res.schema", "res.versions", "res.schema_versions", "res.quality", "self.quality", "self.versions",
    "kinds", "listing", "TOKEN_FIELDS", "numeric", "seen", "failing", "calls", "c.versions",
    "line_models", "entries", "labels", "out", "ordered",
    # los lectores de skills acumulan en estos contenedores propios (nunca en una linea leida)
    "acc.skills", "acc.skill_ids", "res.skill_uses", "res._seen_skill_ids", "self.skill_uses",
    "res.calls",    # T4: la lista de llamadas del resultado (solo recibe CallRecord(...))
    "res._alias_folders",   # T6: pares (alias, nombre de carpeta) del lector; nunca una linea de la transcripcion
))
# Una variable solo vale como clave dentro de estos bucles (variable, iterable): `name` recorre
# TOKEN_FIELDS en `_token_tuple`. Fuera del bucle (o con otro iterable) se rechaza.
ALLOWED_KEY_LOOPS = frozenset((("name", "TOKEN_FIELDS"),))
# `content` (lista de bloques de `message.content`) NO es una ruta propia: solo se puede recorrer, y
# solo como `for block in content` (el lector comprueba antes que sea una `list`). Cualquier otro uso
# (subindice, .items(), copia, otro nombre de variable, comprension) se rechaza.
ALLOWED_ITER_LOOPS = frozenset((("block", "content"),))
# Escalares del lector que se pueden dar a str/%/format/f-string: `damaged` y `total` son enteros
# calculados con len/sum. El nombre generico `name` NO esta aqui: solo vale dentro de un bucle o una
# comprension de FORMAT_LOOPS (variable, iterable), donde recorre TOKEN_FIELDS o las etiquetas fijas de
# comprobaciones de `res.schema` (`sorted(res.schema)` o `res.schema`).
FORMAT_SCALARS = frozenset(("damaged", "total"))
FORMAT_LOOPS = frozenset((("name", "TOKEN_FIELDS"), ("name", "res.schema")))
# Constantes del modulo que valen como limite de un corte (`ordered[:MAX_SHOWN_VERSIONS]`).
SLICE_CONSTANTS = frozenset(("MAX_SHOWN_VERSIONS",))
_COPYING_CALLS = frozenset(("dict", "list", "tuple", "set", "frozenset", "sorted", "iter", "enumerate"))


def _path(node):
    """Ruta con puntos de un Name o de una cadena de Attribute sobre un Name; None si no es una."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _const_like(node) -> bool:
    """Constante, o una expresion cuyo valor solo puede ser una constante escrita en el codigo."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _const_like(node.operand)
    if isinstance(node, ast.IfExp):
        return _const_like(node.body) and _const_like(node.orelse)
    if isinstance(node, ast.Tuple):
        return all(_const_like(e) for e in node.elts)
    return False


def _bound_ok(node) -> bool:
    """Limite de un corte: ausente, constante, constante del modulo o len(<constante>)."""
    if node is None or _const_like(node):
        return True
    if isinstance(node, ast.Name):
        return node.id in SLICE_CONSTANTS
    if isinstance(node, ast.UnaryOp):
        return _bound_ok(node.operand)
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len"
            and len(node.args) == 1 and isinstance(node.args[0], ast.Constant))


def _iterated_paths(node):
    """Rutas que un `for`, una comprension o una copia recorren; None marca algo que no es una ruta."""
    path = _path(node)
    if path is not None:
        return [path]
    if isinstance(node, ast.BoolOp):
        return [p for v in node.values for p in _iterated_paths(v)]
    if isinstance(node, ast.IfExp):
        return _iterated_paths(node.body) + _iterated_paths(node.orelse)
    return []


def _format_ok(node, own_paths, scalars, scalar_ids=frozenset()) -> bool:
    """Operando que puede darse a str/repr/format/f-string/%: constante, ruta propia, escalar del
    lector (FORMAT_SCALARS), constante del modulo (MAYUSCULAS), subindice de una ruta propia o
    expresiones aritmeticas y len(...) de eso. Cualquier otra cosa (una ruta ajena, una llamada) no."""
    if isinstance(node, ast.Constant):
        return True
    path = _path(node)
    if path is not None:
        return (path in own_paths or path in scalars or id(node) in scalar_ids
                or (isinstance(node, ast.Name) and node.id.isupper()))
    if isinstance(node, ast.Subscript):
        return _path(node.value) in own_paths
    if isinstance(node, ast.Call):
        return isinstance(node.func, ast.Name) and node.func.id == "len" and len(node.args) == 1
    if isinstance(node, ast.BinOp):
        return (_format_ok(node.left, own_paths, scalars, scalar_ids)
                and _format_ok(node.right, own_paths, scalars, scalar_ids))
    if isinstance(node, ast.UnaryOp):
        return _format_ok(node.operand, own_paths, scalars, scalar_ids)
    if isinstance(node, ast.Tuple):
        return all(_format_ok(e, own_paths, scalars, scalar_ids) for e in node.elts)
    return False


def _iter_source(node):
    """Ruta del iterable de un bucle; `sorted(x)`, `list(x)` y `tuple(x)` dejan pasar la de `x`."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("sorted", "list", "tuple") and len(node.args) == 1 and not node.keywords):
        return _path(node.args[0])
    return _path(node)


def _scope_nodes(scope):
    """Nodos de un ambito (modulo o funcion) sin entrar en las funciones o clases anidadas."""
    todo, out = list(ast.iter_child_nodes(scope)), []
    while todo:
        node = todo.pop()
        out.append(node)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            todo.extend(ast.iter_child_nodes(node))
    return out


def _foreign(node, own_paths, tainted) -> bool:
    """Valor que sale SIN filtrar de una linea de la transcripcion: un subindice (no un corte) o un
    `.get/.pop/.setdefault` sobre algo que no es una ruta propia, o una variable `tainted` (asignada de uno
    de ellos o iteradora de algo ajeno), o una expresion que lo combina."""
    if isinstance(node, ast.Name):
        return node.id in tainted
    if isinstance(node, ast.Subscript):
        # un corte, o un elemento de `texto.split(...)`, es texto y no un diccionario de la transcripcion
        if isinstance(node.slice, ast.Slice) or (
                isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr in ("split", "rsplit", "partition", "rpartition", "splitlines")):
            return False
        return _path(node.value) not in own_paths
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("get", "pop", "setdefault")):
        return _path(node.func.value) not in own_paths
    if isinstance(node, ast.IfExp):
        return _foreign(node.body, own_paths, tainted) or _foreign(node.orelse, own_paths, tainted)
    if isinstance(node, ast.BoolOp):
        return any(_foreign(v, own_paths, tainted) for v in node.values)
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_foreign(e, own_paths, tainted) for e in node.elts)
    if isinstance(node, ast.BinOp):
        return _foreign(node.left, own_paths, tainted) or _foreign(node.right, own_paths, tainted)
    return False


def _any_foreign(node, own_paths, tainted) -> bool:
    """True si ALGUNA parte de la expresion es un valor ajeno (para los destinos de texto)."""
    return any(_foreign(sub, own_paths, tainted) for sub in ast.walk(node))


def _tainted_names(nodes, own_paths, iter_loops) -> set:
    """Variables de un ambito que reciben un valor ajeno (asignaciones, `:=`, desempaquetados, y el
    objetivo de un `for block in content`). Se propaga por asignaciones sucesivas hasta no cambiar."""
    tainted = set()
    for node in nodes:
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            if _iter_source(node.iter) is not None and _iter_source(node.iter) not in own_paths:
                tainted.add(node.target.id)
    for _ in range(4):
        before = len(tainted)
        for node in nodes:
            value, targets = None, []
            if isinstance(node, ast.Assign):
                value, targets = node.value, node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value, targets = node.value, [node.target]
            elif isinstance(node, ast.NamedExpr):
                value, targets = node.value, [node.target]
            if value is not None and _foreign(value, own_paths, tainted):
                for target in targets:
                    for sub in ast.walk(target):
                        if isinstance(sub, ast.Name):
                            tainted.add(sub.id)
        if len(tainted) == before:
            break
    return tainted


def _text_sink_offenders(scope, own_paths, iter_loops) -> list:
    """Destinos de texto o acumulacion que reciben un valor ajeno en un ambito: `+`/`+=`, `join`,
    `.format`/`format_map`, `%`, f-strings, str/repr/format, `__str__`/`__repr__`/`__format__`, `bytes(...)` y
    `.append(...)` (a una ruta propia solo si el valor ajeno es un acceso directo, no una variable
    ya filtrada por el lector)."""
    nodes = _scope_nodes(scope)
    tainted = _tainted_names(nodes, own_paths, iter_loops)
    direct = set()
    found = []
    for sub in nodes:
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Add):
            if _foreign(sub.left, own_paths, tainted) or _foreign(sub.right, own_paths, tainted):
                found.append("+ con un valor ajeno" + " (l.%d)" % sub.lineno)
        elif isinstance(sub, ast.AugAssign) and isinstance(sub.op, ast.Add):
            if _foreign(sub.value, own_paths, tainted):
                found.append("+= con un valor ajeno" + " (l.%d)" % sub.lineno)
        elif isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Mod):
            if _any_foreign(sub.right, own_paths, tainted):
                found.append("% con un valor ajeno" + " (l.%d)" % sub.lineno)
        elif isinstance(sub, ast.FormattedValue):
            if _any_foreign(sub.value, own_paths, tainted):
                found.append("f-string con un valor ajeno" + " (l.%d)" % sub.lineno)
        elif isinstance(sub, ast.Attribute) and sub.attr in ("__str__", "__repr__", "__format__"):
            found.append(sub.attr)
        elif isinstance(sub, ast.Call):
            args = list(sub.args) + [k.value for k in sub.keywords]
            if isinstance(sub.func, ast.Attribute):
                attr, recv = sub.func.attr, _path(sub.func.value)
                if attr in ("join", "format") and any(_any_foreign(a, own_paths, tainted) for a in args):
                    found.append("%s con un valor ajeno" % attr + " (l.%d)" % sub.lineno)
                elif attr == "format_map" and any(_path(a) not in own_paths for a in args):
                    found.append("format_map sobre algo que no es propio" + " (l.%d)" % sub.lineno)
                elif attr == "append" and args:
                    if recv in own_paths:
                        if any(_foreign(a, own_paths, direct) for a in args):
                            found.append("append de un acceso ajeno" + " (l.%d)" % sub.lineno)
                    elif any(_any_foreign(a, own_paths, tainted) for a in args):
                        found.append("append de un valor ajeno" + " (l.%d)" % sub.lineno)
            elif isinstance(sub.func, ast.Name):
                if sub.func.id in ("str", "repr", "ascii", "format") and any(
                        _any_foreign(a, own_paths, tainted) for a in args):
                    found.append("%s de un valor ajeno" % sub.func.id + " (l.%d)" % sub.lineno)
                elif sub.func.id in ("bytes", "bytearray") and args and not (
                        isinstance(args[0], ast.Constant) and not isinstance(args[0].value, str)
                        or _path(args[0]) in own_paths):
                    found.append("%s(<ajeno>)" % sub.func.id + " (l.%d)" % sub.lineno)
    return found


def unsafe_key_access(source: str, own_paths=OWN_PATHS, allowed_loops=ALLOWED_KEY_LOOPS,
                      iter_loops=ALLOWED_ITER_LOOPS, scalars=FORMAT_SCALARS, format_loops=FORMAT_LOOPS) -> list:
    """Accesos a diccionarios que keys_used_by no puede revisar. Se rechaza, salvo que el receptor
    sea una ruta propia COMPLETA (own_paths):
      - `.items()`, `.values()`, `.keys()`;
      - TODO subindice cuya clave no sea una constante (o un IfExp/tupla de constantes) o un corte con
        limites constantes; y `.get`/`.pop`/`.setdefault` con un primer argumento que no sea constante;
      - recorrer un diccionario: `for k in obj`, comprensiones, `dict(obj)`, `list(obj)`, `sorted(obj)`,
        `{**obj}`, `dict(**obj)` y `json.dumps(obj)`;
      - convertir a texto algo que no es propio o un escalar del lector: `str`, `repr`, `ascii`,
        `format`, `.format`, f-strings y `%` (_format_ok), y desempaquetarlo (`*obj`, `**obj`);
      - (T4) concatenar con `+`, `join`, `format_map`, `__str__`/`__repr__`/`__format__`, `bytes(...)` o
        `.append(...)` un valor ajeno, directo o guardado antes en una variable (`name = block.get("name")`
        seguido de `"%s" % name`): ver _text_sink_offenders.
    Una variable solo vale como clave dentro de un bucle de allowed_loops, `content` solo se recorre
    con un `for` de iter_loops (`for block in content`), y un nombre solo es un escalar de formato dentro
    de un bucle o comprension de format_loops (`name` recorriendo TOKEN_FIELDS o `res.schema`)."""
    tree = ast.parse(source)
    shielded = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and (node.target.id, _path(node.iter)) in allowed_loops):
            shielded |= {id(n) for stmt in node.body for n in ast.walk(stmt)
                         if isinstance(n, ast.Name) and n.id == node.target.id}
    # nombres que valen como escalar de formato: solo los usos dentro de un bucle de format_loops
    scalar_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            if (node.target.id, _iter_source(node.iter)) in format_loops:
                scalar_ids |= {id(n) for stmt in node.body for n in ast.walk(stmt)
                               if isinstance(n, ast.Name) and n.id == node.target.id}
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            for gen in node.generators:
                if isinstance(gen.target, ast.Name) and (gen.target.id, _iter_source(gen.iter)) in format_loops:
                    parts = [node.elt] if not isinstance(node, ast.DictComp) else [node.key, node.value]
                    parts += list(gen.ifs)
                    scalar_ids |= {id(n) for part in parts for n in ast.walk(part)
                                   if isinstance(n, ast.Name) and n.id == gen.target.id}

    def key_ok(key) -> bool:
        return _const_like(key) or (isinstance(key, ast.Name) and id(key) in shielded)

    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            recv = _path(node.func.value)
            attr = node.func.attr
            if attr in ("items", "values", "keys") and recv not in own_paths:
                offenders.append("%s() sobre %s" % (attr, recv))
            elif (attr in ("get", "pop", "setdefault") and node.args and recv not in own_paths
                  and not key_ok(node.args[0])):
                offenders.append("%s(<no constante>) sobre %s" % (attr, recv))
            elif _path(node.func) in ("json.dumps", "json.dump"):
                args = list(node.args) + [k.value for k in node.keywords]
                if any(_path(a) not in own_paths for a in args):
                    offenders.append("%s sobre algo que no es propio" % _path(node.func))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _COPYING_CALLS:
            for arg in list(node.args) + [k.value for k in node.keywords]:
                for path in _iterated_paths(arg):
                    if path not in own_paths:
                        offenders.append("%s(%s)" % (node.func.id, path))
        elif isinstance(node, ast.Subscript):
            recv = _path(node.value)
            if isinstance(node.slice, ast.Slice):
                ok = all(_bound_ok(b) for b in (node.slice.lower, node.slice.upper, node.slice.step))
            else:
                ok = key_ok(node.slice)
            if not ok and recv not in own_paths:
                offenders.append("subindice no constante sobre %s" % recv)
        elif isinstance(node, (ast.For, ast.comprehension)):
            allowed = (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                       and (node.target.id, _path(node.iter)) in iter_loops)
            for path in _iterated_paths(node.iter):
                if path not in own_paths and not allowed:
                    offenders.append("recorrido de %s" % path)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if key is None and _path(value) not in own_paths:
                    offenders.append("{**%s}" % _path(value))
        # convertir a texto o desempaquetar algo ajeno
        if isinstance(node, ast.Call):
            callee = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else None)
            if callee in ("str", "repr", "ascii", "format"):
                for arg in list(node.args) + [k.value for k in node.keywords]:
                    if not _format_ok(arg, own_paths, scalars, scalar_ids):
                        offenders.append("%s(<ajeno>)" % callee)
            for kw in node.keywords:
                if kw.arg is None and _path(kw.value) not in own_paths:
                    offenders.append("**%s" % _path(kw.value))
        elif isinstance(node, ast.FormattedValue):
            if not _format_ok(node.value, own_paths, scalars, scalar_ids):
                offenders.append("f-string con un valor ajeno")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            if not (isinstance(node.left, ast.Constant) and isinstance(node.left.value, (int, float))):
                if not _format_ok(node.right, own_paths, scalars, scalar_ids):
                    offenders.append("% con un operando ajeno")
        elif isinstance(node, ast.Starred):
            if _path(node.value) not in own_paths:
                offenders.append("*%s" % _path(node.value))
    # destinos de texto y acumulacion con valores ajenos, por ambito (modulo y cada funcion)
    for scope in [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        offenders += _text_sink_offenders(scope, own_paths, iter_loops)
    return offenders


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

    def test_file_fully_duplicated_keeps_has_usage_with_zero_requests_but_is_not_usable(self):
        # T3: `usable` exige requests > 0, asi un archivo con todos sus ids repetidos (0 peticiones,
        # 0 tokens) no entra en medianas ni p90. has_usage sigue siendo True (tenia usage).
        tree = us.Tree(self.base)
        for n in ("a1", "a2"):
            tree.subagent("c--p", "s1", n, [us.assistant("dup", T0 + "1Z")])
        first, second = self.read(tree).calls
        self.assertEqual((second.requests, second.total_tokens, second.has_usage), (0, 0, True))
        self.assertFalse(second.usable)
        self.assertFalse(second.excluded)   # sigue contando para duracion y herramientas
        self.assertEqual(first.requests, 1)
        self.assertTrue(first.usable)

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
        self.assertIn("líneas", ur.WARN_NO_MESSAGE_ID)      # el texto del reporte lleva tildes (decision del propietario)
        clean =us.Tree(os.path.join(self.base, "limpio"))
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


class ReaderDedupAndRelease(ReaderBase):
    """T3 previo: hardlinks repetidos dentro de projects/ y liberacion de memoria."""

    def _linked_pair(self, tree, ids=("m1",)):
        first = tree.subagent("c--p", "s1", "a1", [us.assistant(i, T0 + "1Z", usage_value=us.usage(7, 1, 1, 1))
                                                   for i in ids])
        sub2 = os.path.join(tree.folder("c--p"), "s2", "subagents")
        os.makedirs(sub2)
        self.hardlink(first, os.path.join(sub2, "agent-a2.jsonl"))
        return first

    def test_two_names_of_same_inode_inside_projects_are_one_call(self):
        tree = us.Tree(self.base)
        self._linked_pair(tree)
        res = self.read(tree)
        self.assertEqual(len(res.calls), 1)
        self.assertEqual(res.quality["hardlinks duplicados dentro de projects"], 1)
        self.assertEqual(res.quality["llamadas leidas"], 1)
        self.assertEqual(res.quality["hardlinks aceptados"], 1)
        self.assertEqual(res.calls[0].input_tokens, 7)   # no se cuenta dos veces
        # el nombre que se recorre primero (orden alfabetico: s1 antes que s2) crea la llamada
        self.assertEqual(res.calls[0].session, ur._digest("c--p\0s1", res._key).hex())

    def test_hardlinked_pair_with_outside_link_is_also_deduplicated(self):
        tree = us.Tree(self.base)
        first = self._linked_pair(tree)
        os.link(first, os.path.join(self.base, "afuera.jsonl"))   # nlink = 3
        res = self.read(tree)
        self.assertEqual(len(res.calls), 1)
        self.assertEqual(res.quality["hardlinks duplicados dentro de projects"], 1)

    def test_distinct_hardlinked_inodes_are_all_kept(self):
        tree = us.Tree(self.base)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        for i in (1, 2):
            target = outer.subagent("c--x", "s9", "a%d" % i, [us.assistant("h%d" % i, T0 + "1Z")], meta=None)
            sub = os.path.join(tree.folder("c--p"), "s%d" % i, "subagents")
            os.makedirs(sub)
            self.hardlink(target, os.path.join(sub, "agent-h%d.jsonl" % i))
        res = self.read(tree)
        self.assertEqual(len(res.calls), 2)
        self.assertEqual(res.quality["hardlinks duplicados dentro de projects"], 0)
        self.assertEqual(res.quality["hardlinks aceptados"], 2)

    def test_duplicate_does_not_register_ids_or_meta(self):
        tree = us.Tree(self.base)
        self._linked_pair(tree)
        res = self.read(tree)
        self.assertEqual(res.quality["message.id repetido entre archivos"], 0)
        self.assertEqual(res.warnings, [])

    def test_release_key_forgets_the_digest_key_and_read_calls_does_not_call_it(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        res = self.read(tree)
        self.assertEqual(len(res._key), 16)            # read_calls la conserva (las pruebas la usan)
        res.release_key()
        self.assertIsNone(res._key)
        res.release_key()                               # idempotente
        self.assertIsNone(res._key)
        self.assertEqual(len(res.calls), 1)             # lo ya leido sigue ahi
        self.assertEqual(ur.aggregate_calls(res, today=TODAY).total.calls, 0)   # (fuera de ventana)
        self.assertEqual(ur.aggregate_calls(res, window=ur.make_window(TODAY, all_time=True)).total.calls, 1)

    def test_read_result_releases_id_and_inode_sets(self):
        tree = us.Tree(self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", T0 + "1Z")])
        res = self.read(tree)
        self.assertIsNone(res._seen_ids)
        self.assertIsNone(res._seen_inodes)
        self.assertEqual(len(res.calls), 1)


# --- T3: agregacion y metricas ---
UTC = datetime.timezone.utc
TODAY = datetime.date(2026, 3, 31)   # ventana por defecto: 2026-03-02 .. 2026-03-31 (30 fechas)


def dt(day, hour=0, minute=0, second=0, micro=0, month=3):
    return datetime.datetime(2026, month, day, hour, minute, second, micro, tzinfo=UTC)


def span(seconds, day=10, hour=10):
    """(start, end) de una llamada que dura `seconds` segundos."""
    start = dt(day, hour)
    return {"start": start, "end": start + datetime.timedelta(seconds=seconds)}


def mk(n, **kw):
    """CallRecord a mano. Por defecto: usable, 1 peticion, 20 tokens (10+5+2+3), 10 s, 2.1.330."""
    fields = dict(
        call_id="c%03d" % n, project="p-00000001", session="s1", agent="forge", agent_group="SyncLayer",
        status="correcta", damage=None, has_meta=True, has_usage=True, models=("claude-opus-4-1",),
        model="claude-opus-4-1", model_source="lineas", model_mismatch=False, input_tokens=10,
        output_tokens=5, cache_creation_tokens=2, cache_read_tokens=3, requests=1, tools=0,
        fallback_time=None, versions=("2.1.330",), hardlink=False, oversize_lines=0, background=None, seq=n)
    fields.update(span(10))
    fields.update(kw)
    if "agent_key" not in fields:
        # clave interna del agente: sin meta, la constante; con meta, una por (agente, conjunto)
        fields["agent_key"] = (ur.NO_META_KEY if fields["agent_group"] == "sin-meta"
                               else "k:%s:%s" % (fields["agent"], fields["agent_group"]))
    return ur.CallRecord(**fields)


def no_usage(n, **kw):
    fields = dict(status="sin_usage", has_usage=False, input_tokens=0, output_tokens=0,
                  cache_creation_tokens=0, cache_read_tokens=0, requests=0)
    fields.update(kw)
    return mk(n, **fields)


def damaged(n, **kw):
    fields = dict(status="danada", damage="linea intermedia corrupta", input_tokens=0, output_tokens=0,
                  cache_creation_tokens=0, cache_read_tokens=0, requests=0)
    fields.update(kw)
    return mk(n, **fields)


def agg(source, **kw):
    kw.setdefault("today", TODAY)
    return ur.aggregate_calls(source, **kw)


class Percentiles(unittest.TestCase):
    def test_known_values_for_small_and_boundary_n(self):
        # mediana con n par: media de los dos centrales, medio hacia arriba. p90: rango mas cercano,
        # posicion ceil(0,9 n) de la lista ordenada (1 a n). "small" = n < 10.
        cases = (
            # n=1: mediana 7, posicion ceil(0,9)=1 -> 7
            ([7], 7, 7, True),
            # n=2: (1+4)/2=2,5 -> 3; posicion ceil(1,8)=2 -> 4
            ([4, 1], 3, 4, True),
            # n=9: mediana la 5.a = 5; posicion ceil(8,1)=9 -> 9
            (list(range(9, 0, -1)), 5, 9, True),
            # n=10: (5+6)/2=5,5 -> 6; posicion ceil(9,0)=9 -> 9 (no 10: es el limite)
            (list(range(1, 11)), 6, 9, False),
            # n=11: mediana la 6.a = 6; posicion ceil(9,9)=10 -> 10
            (list(range(11, 0, -1)), 6, 10, False),
            # n=2 con valores iguales: (2+2)/2 = 2
            ([2, 2], 2, 2, True),
            # n=2: (1+2)/2=1,5 -> 2
            ([1, 2], 2, 2, True),
            # n=10: nueve 5 y un 100: mediana (5+5)/2=5; posicion 9 -> 5 (el 100 queda fuera del p90)
            ([5] * 9 + [100], 5, 5, False),
        )
        for values, median, p90, small in cases:
            with self.subTest(values=values):
                d = ur.distribution(values)
                self.assertEqual((d.n, d.total, d.median, d.p90, d.small),
                                 (len(values), sum(values), median, p90, small))

    def test_empty_and_huge_values(self):
        d = ur.distribution([])
        self.assertEqual((d.n, d.total, d.median, d.p90, d.small), (0, 0, None, None, False))
        big = 10 ** 15
        d = ur.distribution([3 * big, big, big + 1])   # ordenado: big, big+1, 3 big
        # mediana la 2.a = big+1; posicion ceil(2,7)=3 -> 3 big; total 5 big + 1
        self.assertEqual((d.median, d.p90, d.total), (big + 1, 3 * big, 5 * big + 1))
        d = ur.distribution([0, 0, 0])
        self.assertEqual((d.median, d.p90, d.total), (0, 0, 0))

    def test_input_order_and_input_list_untouched(self):
        values = [5, 1, 9, 3]
        before = list(values)
        a = ur.distribution(values)
        b = ur.distribution(sorted(values))
        self.assertEqual(a, b)
        self.assertEqual(values, before)


class WindowRules(unittest.TestCase):
    def test_default_window_is_30_utc_dates_ending_today(self):
        w = ur.make_window(TODAY)
        self.assertEqual((w.since, w.until), (datetime.date(2026, 3, 2), TODAY))
        self.assertEqual((w.until - w.since).days + 1, 30)
        # 1 de marzo menos 29 dias = 31 de enero (febrero de 2026 tiene 28)
        w = ur.make_window(datetime.date(2026, 3, 1))
        self.assertEqual(w.since, datetime.date(2026, 1, 31))

    def test_boundaries_are_inclusive_by_date_in_utc(self):
        w = ur.make_window(TODAY)
        self.assertTrue(w.contains(dt(2, 0, 0, 0)))                       # primer instante de since
        self.assertFalse(w.contains(dt(1, 23, 59, 59, 999999)))           # ultimo instante antes de since
        self.assertTrue(w.contains(dt(31, 23, 59, 59, 999999)))           # ultimo instante de until
        self.assertFalse(w.contains(dt(1, month=4)))                      # primer instante despues de until
        # una hora con zona se lleva a UTC: 01:00+02:00 del 2 de marzo es 23:00Z del 1 -> fuera
        east = datetime.timezone(datetime.timedelta(hours=2))
        self.assertFalse(w.contains(datetime.datetime(2026, 3, 2, 1, 0, tzinfo=east)))
        # 23:30-05:00 del 31 de marzo es 04:30Z del 1 de abril -> fuera
        west = datetime.timezone(datetime.timedelta(hours=-5))
        self.assertFalse(w.contains(datetime.datetime(2026, 3, 31, 23, 30, tzinfo=west)))
        # sin zona se toma como UTC
        self.assertTrue(w.contains(datetime.datetime(2026, 3, 2, 0, 0)))

    def test_explicit_dates_all_and_errors(self):
        d = datetime.date
        self.assertEqual(ur.make_window(TODAY, since=d(2026, 3, 10)).until, TODAY)
        self.assertEqual(ur.make_window(TODAY, until=d(2026, 3, 30)).since, d(2026, 3, 1))
        one = ur.make_window(TODAY, since=d(2026, 3, 5), until=d(2026, 3, 5))
        self.assertTrue(one.contains(dt(5, 12)))
        self.assertFalse(one.contains(dt(6)))
        w = ur.make_window(TODAY, all_time=True)
        self.assertTrue(w.is_all)
        self.assertTrue(w.contains(dt(1, month=1)))
        with self.assertRaises(ValueError):
            ur.make_window(TODAY, all_time=True, since=d(2026, 3, 1))
        with self.assertRaises(ValueError):
            ur.make_window(TODAY, since=d(2026, 3, 10), until=d(2026, 3, 9))

    def test_utc_today_is_a_utc_date(self):
        self.assertIsInstance(ur.utc_today(), datetime.date)

    def test_dates_near_the_calendar_limits_are_a_clear_value_error(self):
        d = datetime.date
        # since = date.min + 5 dias - 29 dias desborda: OverflowError del calendario -> ValueError
        with self.assertRaises(ValueError) as cm:
            ur.make_window(d.min + datetime.timedelta(days=5))
        self.assertEqual(str(cm.exception), ur.MSG_WINDOW_RANGE)
        with self.assertRaises(ValueError):
            ur.make_window(TODAY, until=d.min)
        # el extremo superior no desborda: date.max como today da una ventana valida
        w = ur.make_window(d.max)
        self.assertEqual((w.until, (w.until - w.since).days), (d.max, 29))
        self.assertTrue(w.contains(datetime.datetime(9999, 12, 31, 23, 59, tzinfo=UTC)))
        # un instante que al llevarlo a UTC se sale del calendario cae fuera de toda ventana
        # (no es un OverflowError): 23:59-05:00 del 31-12-9999 seria el 1-1-10000
        far = datetime.timezone(datetime.timedelta(hours=-5))
        self.assertFalse(w.contains(datetime.datetime(9999, 12, 31, 23, 59, tzinfo=far)))
        east = datetime.timezone(datetime.timedelta(hours=5))
        self.assertFalse(ur.make_window(TODAY).contains(datetime.datetime(1, 1, 1, 1, 0, tzinfo=east)))

    def test_window_built_by_hand_is_validated_in_the_constructor(self):
        d = datetime.date
        for since, until in ((d(2026, 3, 1), None), (None, d(2026, 3, 1)), (d(2026, 3, 2), d(2026, 3, 1)),
                             ("2026-03-01", d(2026, 3, 1)), (d(2026, 3, 1), 5),
                             (datetime.datetime(2026, 3, 1), d(2026, 3, 2))):
            with self.subTest(since=since, until=until):
                with self.assertRaises(ValueError):
                    ur.Window(since, until)
        self.assertTrue(ur.Window(None, None).is_all)
        self.assertTrue(ur.Window(d(2026, 3, 1), d(2026, 3, 1)).contains(dt(1, 12)))


class AggregationWindow(unittest.TestCase):
    def test_today_is_required_when_there_is_no_window_and_the_clock_is_never_read(self):
        with self.assertRaises(ValueError) as cm:
            ur.aggregate_calls([mk(0)])
        self.assertEqual(str(cm.exception), ur.MSG_TODAY_REQUIRED)
        with mock.patch.object(ur, "utc_today", side_effect=AssertionError("reloj")):
            ur.aggregate_calls([mk(0)], today=TODAY)
            ur.aggregate_calls([mk(0)], window=ur.make_window(TODAY))

    def test_unreadable_calls_without_any_time_count_in_the_damage_threshold_of_a_window(self):
        # caso reproducido: 10 ilegibles sin hora y ninguna correcta. Sin hora quedan fuera de la
        # ventana, pero el umbral las cuenta (criterio conservador: en numerador y denominador)
        lost = [damaged(i, damage="ilegible", start=None, end=None, fallback_time=None) for i in range(10)]
        with self.assertRaises(ur.SchemaError) as cm:
            agg(lost)
        self.assertIn("10 de 10", cm.exception.message)
        # las no danadas sin hora NO entran en el denominador: 1 danada sin hora + 19 correctas = 1 de 20 = 5 %
        ok = [mk(100 + i) for i in range(19)]
        one = [damaged(1, damage="ilegible", start=None, end=None, fallback_time=None)]
        m = agg(ok + one)
        self.assertEqual((m.total.calls, m.quality.without_any_time, m.quality.without_any_time_excluded), (19, 1, 1))
        # 19 correctas + 2 danadas sin hora = 2 de 21 > 5 %
        two = one + [damaged(2, damage="tope", start=None, end=None, fallback_time=None)]
        with self.assertRaises(ur.SchemaError) as cm:
            agg(ok + two)
        self.assertIn("2 de 21", cm.exception.message)
        # una correcta sin hora no suma al denominador. Con 18 correctas + 1 danada sin hora son 1 de 19
        # = 5,26 % y SI supera el umbral; con la correcta sin hora la cuenta seria 1 de 20 = 5 % y no
        # fallaria: asi la prueba distingue «no sumar las no danadas sin hora» de sumarlas
        quiet = mk(200, start=None, end=None, fallback_time=None)
        ok18 = ok[:18]
        with self.assertRaises(ur.SchemaError) as cm:
            agg(ok18 + one + [quiet])
        self.assertIn("1 de 19", cm.exception.message)
        # el dato de calidad sigue exponiendo las dos llamadas sin hora (con la comprobacion apagada)
        m = agg(ok18 + one + [quiet], check_damage=False)
        self.assertEqual((m.quality.without_any_time, m.quality.without_any_time_excluded), (2, 1))
        # con fallback_time la danada se ubica en la ventana y cuenta una sola vez
        located = [damaged(3, damage="ilegible", start=None, end=None, fallback_time=dt(15, 12))]
        with self.assertRaises(ur.SchemaError) as cm:
            agg(located + [damaged(4, damage="tope", start=None, end=None, fallback_time=dt(15, 12))] + ok[:5])
        self.assertIn("2 de 7", cm.exception.message)
        # --all: entran en la ventana, no se cuentan dos veces
        with self.assertRaises(ur.SchemaError) as cm:
            agg(lost, window=ur.make_window(TODAY, all_time=True))
        self.assertIn("10 de 10", cm.exception.message)
        # sin comprobacion no lanza y el dato queda expuesto
        m = agg(lost, check_damage=False)
        self.assertEqual((m.total.calls, m.quality.without_any_time, m.quality.without_any_time_excluded), (0, 10, 10))

    def test_window_membership_and_quality_of_placement(self):
        old = datetime.datetime(2026, 2, 1, tzinfo=UTC)
        calls = [
            mk(0, **span(10, day=10)),                                                  # dentro
            mk(1, start=old, end=old),                                                  # fuera
            mk(2, start=None, end=None, fallback_time=dt(15, 12)),                      # respaldo, dentro
            mk(3, start=None, end=None, fallback_time=datetime.datetime(2026, 1, 5, tzinfo=UTC)),  # respaldo, fuera
            mk(4, start=None, end=None, fallback_time=None),                           # sin ninguna hora
        ]
        m = agg(calls)
        self.assertEqual(m.window.since, datetime.date(2026, 3, 2))
        self.assertEqual(m.total.calls, 2)
        q = m.quality
        self.assertEqual((q.calls_read, q.calls_in_window, q.calls_outside_window), (5, 2, 3))
        self.assertEqual((q.without_start, q.placed_by_fallback, q.without_any_time), (1, 1, 1))
        # con --all entran todas, tambien la que no tiene hora; el respaldo ya no hace falta
        m = agg(calls, window=ur.make_window(TODAY, all_time=True))
        self.assertEqual(m.total.calls, 5)
        self.assertEqual((m.quality.without_start, m.quality.placed_by_fallback, m.quality.without_any_time),
                         (3, 0, 1))

    def test_zero_calls_empty_window_and_single_call(self):
        m = agg([])
        self.assertEqual((m.total.calls, m.agents, m.groups, m.projects, m.warnings), (0, (), (), (), ()))
        self.assertEqual((m.total.sessions, m.total.calls_per_session_tenths), (0, None))
        self.assertEqual((m.total.tokens.n, m.total.tokens.total.median, m.total.duration.median), (0, None, None))
        m = agg([mk(0, start=dt(1, month=1), end=dt(1, month=1))])
        self.assertEqual((m.total.calls, m.quality.calls_read, m.quality.calls_outside_window), (0, 1, 1))
        m = agg([mk(0)])
        self.assertEqual((m.total.calls, m.total.tokens.n, m.total.tokens.total.median, m.total.tokens.total.p90,
                          m.total.tokens.total.small), (1, 1, 20, 20, True))

    def test_damage_ratio_is_measured_on_the_window_calls(self):
        ok = [mk(i) for i in range(19)]
        agg(ok + [damaged(100)])          # 1 de 20 = 5 %: no supera el umbral
        with self.assertRaises(ur.SchemaError) as cm:
            agg(ok + [damaged(100), damaged(101)])   # 2 de 21 > 5 %
        cm.exception.message.encode("ascii")
        # los danados FUERA de la ventana no cuentan
        old = [damaged(200 + i, start=dt(1, month=1), end=dt(1, month=1)) for i in range(50)]
        m = agg(ok + old)
        self.assertEqual(m.total.calls, 19)
        # con --all si cuentan: 50 de 69
        with self.assertRaises(ur.SchemaError):
            agg(ok + old, window=ur.make_window(TODAY, all_time=True))
        # y se puede desactivar la comprobacion
        m = agg(ok + [damaged(100), damaged(101)], check_damage=False)
        self.assertEqual(m.quality.excluded, 2)


class AggregationMetrics(unittest.TestCase):
    def test_calls_sessions_and_calls_per_session(self):
        calls = [mk(0, session="s1"), mk(1, session="s1"), mk(2, session="s2"),
                 mk(3, agent="scout", session="s1")]
        m = agg(calls)
        forge = m.agents[0]
        self.assertEqual((forge.agent, forge.group), ("forge", "SyncLayer"))
        # forge: 3 llamadas en 2 sesiones = 1,5 -> 15 decimas
        self.assertEqual((forge.metrics.calls, forge.metrics.sessions, forge.metrics.calls_per_session_tenths),
                         (3, 2, 15))
        # total: 4 llamadas en 2 sesiones distintas (s1, s2) = 2,0
        self.assertEqual((m.total.calls, m.total.sessions, m.total.calls_per_session_tenths), (4, 2, 20))
        # 7 llamadas / 3 sesiones = 2,33 -> 23 (redondeo al mas cercano)
        seven = [mk(i, session="s%d" % (i % 3)) for i in range(7)]
        self.assertEqual(agg(seven).total.calls_per_session_tenths, 23)

    def test_calls_per_session_rounds_to_nearest_tenth_not_down(self):
        # 7 / 4 = 1,75 -> 17,5 decimas -> 18 (medio hacia arriba; el suelo daria 17)
        # 5 / 4 = 1,25 -> 12,5 decimas -> 13 (el suelo daria 12)
        # 8 / 3 = 2,666 -> 26,7 -> 27 (el suelo daria 26); 4 / 3 = 1,333 -> 13,3 -> 13
        for calls, sessions, expected in ((7, 4, 18), (5, 4, 13), (8, 3, 27), (4, 3, 13), (1, 1, 10), (3, 2, 15)):
            with self.subTest(calls=calls, sessions=sessions):
                items = [mk(i, session="s%d" % (i % sessions)) for i in range(calls)]
                self.assertEqual(agg(items).total.calls_per_session_tenths, expected)

    def test_excluded_unreadable_and_excluded_cap_are_told_apart(self):
        calls = [mk(0), mk(1),
                 damaged(2, damage="linea intermedia corrupta"),
                 damaged(3, damage="ilegible"),
                 damaged(4, damage="tope"), damaged(5, damage="tope"), damaged(6, damage="tope")]
        q = agg(calls, check_damage=False).quality
        # 1 corrupta, 1 ilegible, 3 tope: ninguna cadena se cuenta en la de otra
        self.assertEqual((q.excluded, q.excluded_corrupt_line, q.excluded_unreadable, q.excluded_cap),
                         (5, 1, 1, 3))
        only = agg([mk(0), damaged(1, damage="ilegible")], check_damage=False).quality
        self.assertEqual((only.excluded_unreadable, only.excluded_cap, only.excluded_corrupt_line), (1, 0, 0))
        only = agg([mk(0), damaged(1, damage="tope")], check_damage=False).quality
        self.assertEqual((only.excluded_unreadable, only.excluded_cap, only.excluded_corrupt_line), (0, 1, 0))

    def test_groups_by_agent_and_group_never_by_name_alone(self):
        calls = [
            mk(0), mk(1),
            mk(2, agent="(otro agente)", agent_group="otros"),
            mk(3, agent="(otro agente)", agent_group="plugin:(no-valido)"),
            mk(4, agent="general-purpose", agent_group="integrado"),
        ]
        m = agg(calls)
        # orden: llamadas descendente, luego nombre y conjunto
        self.assertEqual([(a.agent, a.group, a.metrics.calls) for a in m.agents], [
            ("forge", "SyncLayer", 2),
            ("(otro agente)", "otros", 1),
            ("(otro agente)", "plugin:(no-valido)", 1),
            ("general-purpose", "integrado", 1),
        ])
        self.assertEqual([(g.group, g.agents, g.metrics.calls) for g in m.groups], [
            ("SyncLayer", 1, 2), ("integrado", 1, 1), ("otros", 1, 1), ("plugin:(no-valido)", 1, 1)])

    def test_group_agent_count_uses_the_internal_agent_key(self):
        calls = [
            mk(0, agent="(otro agente)", agent_group="otros", agent_key="ua1"),
            mk(1, agent="(otro agente)", agent_group="otros", agent_key="ua2"),
            mk(2, agent="(otro agente)", agent_group="otros", agent_key="ua2"),
            mk(3, agent="plugin:pl", agent_group="plugin:pl", agent_key="pa1"),
            mk(4, agent="plugin:pl", agent_group="plugin:pl", agent_key="pa2"),
            mk(5, agent="plugin:pl", agent_group="plugin:pl", agent_key="pa3"),
            mk(6, agent="(sin-meta)", agent_group="sin-meta", has_meta=False),
            mk(7, agent="(sin-meta)", agent_group="sin-meta", has_meta=False),
            mk(8), mk(9, agent="scout"),
        ]
        m = agg(calls)
        self.assertEqual({g.group: g.agents for g in m.groups},
                         {"otros": 2, "plugin:pl": 3, "sin-meta": 1, "SyncLayer": 2})
        # la fila por (agente, conjunto) sigue siendo una sola por etiqueta visible
        self.assertEqual(len([a for a in m.agents if a.group == "otros"]), 1)

    def test_tokens_use_only_usable_calls_but_duration_and_tools_use_non_excluded(self):
        calls = [
            mk(0, **span(10), tools=0),                                                    # usable: 20 tokens
            no_usage(1, **span(30), tools=4),                                              # sin usage
            damaged(2, **span(999), tools=9),                                              # excluida
            mk(3, has_usage=True, requests=0, input_tokens=0, output_tokens=0,
               cache_creation_tokens=0, cache_read_tokens=0, **span(0), tools=2),          # ids repetidos
            mk(4, input_tokens=100, output_tokens=50, cache_creation_tokens=20, cache_read_tokens=30,
               requests=3, **span(20), tools=0),                                           # usable: 200
        ]
        m = agg(calls, check_damage=False).total
        self.assertEqual((m.calls, m.excluded), (5, 1))
        t = m.tokens
        self.assertEqual(t.n, 2)
        # totales por llamada [20, 200]: mediana (20+200)/2=110, p90 posicion ceil(1,8)=2 -> 200, suma 220
        self.assertEqual((t.total.median, t.total.p90, t.total.total), (110, 200, 220))
        # entrada [10, 100]: (10+100)/2=55
        self.assertEqual((t.input_tokens.median, t.input_tokens.total), (55, 110))
        # salida [5, 50]: 27,5 -> 28; caches escrita [2, 20]: 11; leida [3, 30]: 16,5 -> 17
        self.assertEqual((t.output_tokens.median, t.cache_creation_tokens.median, t.cache_read_tokens.median), (28, 11, 17))
        # peticiones [1, 3]: mediana 2
        self.assertEqual((t.requests.median, t.requests.total), (2, 4))
        # duracion (no excluidas: 10, 30, 0, 20 -> ordenado 0,10,20,30): mediana (10+20)/2=15, p90 pos 4 -> 30
        self.assertEqual((m.duration.n, m.duration.median, m.duration.p90), (4, 15, 30))
        # herramientas (0, 4, 2, 0 -> ordenado 0,0,2,4): mediana (0+2)/2=1, p90 pos 4 -> 4
        self.assertEqual((m.tools.n, m.tools.median, m.tools.p90), (4, 1, 4))
        q = agg(calls, check_damage=False).quality
        self.assertEqual((q.excluded, q.excluded_corrupt_line, q.without_usage, q.all_ids_repeated, q.tokens_calls),
                         (1, 1, 1, 1, 2))

    def test_duration_rounds_to_nearest_second_and_skips_calls_without_times(self):
        calls = [
            mk(0, start=dt(10, 10), end=dt(10, 10, 0, 1, 499999)),   # 1,499999 s -> 1
            mk(1, start=dt(10, 10), end=dt(10, 10, 0, 1, 500000)),   # 1,5 s -> 2
            mk(2, start=None, end=None, fallback_time=dt(10), tools=3),   # sin horas: no tiene duracion
        ]
        m = agg(calls).total
        self.assertEqual((m.duration.n, m.duration.total), (2, 3))
        self.assertEqual((m.tools.n, m.tools.total), (3, 3))

    def test_models_distribution_of_non_excluded_calls(self):
        calls = [
            mk(0), mk(1),
            mk(2, models=("claude-haiku-4-5", "claude-opus-4-1"), model="mixto"),
            mk(3, models=(), model="(desconocido)", model_source=None),
            damaged(4, model="claude-sonnet-4-5", models=("claude-sonnet-4-5",)),
        ]
        m = agg(calls, check_damage=False).total
        self.assertEqual(m.models, (("claude-opus-4-1", 2), ("(desconocido)", 1), ("mixto", 1)))

    def test_projects_are_grouped_and_ordered(self):
        calls = [mk(0, project="p-aaaaaaaa", session="a1"), mk(1, project="p-aaaaaaaa", session="a1"),
                 mk(2, project="p-aaaaaaaa", session="a2"), mk(3, project="p-bbbbbbbb", session="b1")]
        m = agg(calls)
        self.assertEqual([(p.project, p.metrics.calls, p.metrics.sessions) for p in m.projects],
                         [("p-aaaaaaaa", 3, 2), ("p-bbbbbbbb", 1, 1)])
        self.assertEqual(m.projects[0].metrics.tokens.total.total, 60)

    def test_iterators_and_tuples_are_accepted(self):
        calls = [mk(0), mk(1, agent="scout")]
        self.assertEqual(agg(iter(calls)).total, agg(calls).total)
        self.assertEqual(agg(tuple(calls)).agents, agg(calls).agents)


class VersionBreakdown(unittest.TestCase):
    def _calls(self):
        # tokens por llamada = input (los otros tres campos en 0) para leer las sumas
        def v(n, versions, tokens):
            return mk(n, versions=versions, input_tokens=tokens, output_tokens=0, cache_creation_tokens=0,
                      cache_read_tokens=0)
        return [
            v(0, ("2.1.309",), 100),
            v(1, ("2.1.310",), 200),
            v(2, ("2.1.327",), 300),
            v(3, ("2.1.328",), 400),
            v(4, ("2.1.340",), 500),
            v(5, (), 600),
            v(6, ("(otra version)",), 700),
            v(7, ("2.1.309", "2.1.311"), 800),     # toca el rango dudoso -> dudoso
            v(8, ("2.1.309", "2.1.330"), 900),     # sin rango dudoso: la mas alta -> desde 2.1.328
            v(9, ("2.1.328-beta",), 1000),
            v(10, ("2.1.327-rc1",), 1100),
            v(11, ("2.1.315", "2.1.330"), 1200),   # dudoso aunque su version mas alta es posterior
        ]

    def test_ranges_tokens_and_quality(self):
        with mock.patch.object(ur, "VERIFIED_MAX", "2.1.326"):
            m = agg(self._calls())
        rows = {r.range: r for r in m.total.versions}
        self.assertEqual([r.range for r in m.total.versions],
                         [ur.RANGE_BEFORE, ur.RANGE_DOUBTFUL, ur.RANGE_AFTER, ur.RANGE_NONE])
        # antes de 2.1.310: v0 -> 1 llamada, 100 tokens
        self.assertEqual((rows[ur.RANGE_BEFORE].calls, rows[ur.RANGE_BEFORE].tokens.total.total), (1, 100))
        # 2.1.310-2.1.327: v1 + v2 + v7 + v10 + v11 = 200+300+800+1100+1200 = 3600 en 5 llamadas
        self.assertEqual((rows[ur.RANGE_DOUBTFUL].calls, rows[ur.RANGE_DOUBTFUL].tokens.total.total), (5, 3600))
        # desde 2.1.328: v3 + v4 + v8 + v9 = 400+500+900+1000 = 2800 en 4 llamadas
        self.assertEqual((rows[ur.RANGE_AFTER].calls, rows[ur.RANGE_AFTER].tokens.total.total), (4, 2800))
        # sin version: v5 + v6 = 600+700 = 1300 en 2 llamadas
        self.assertEqual((rows[ur.RANGE_NONE].calls, rows[ur.RANGE_NONE].tokens.total.total), (2, 1300))
        self.assertTrue(rows[ur.RANGE_DOUBTFUL].inflated)
        self.assertFalse(rows[ur.RANGE_BEFORE].inflated or rows[ur.RANGE_AFTER].inflated)
        self.assertEqual(sum(r.calls for r in m.total.versions), m.total.calls)
        q = m.quality
        self.assertEqual((q.without_version, q.unrecognized_version), (1, 1))
        # varios rangos distintos: v7 (anterior y dudoso), v8 (anterior y posterior) y v11 (dudoso y posterior)
        self.assertEqual(q.multiple_ranges, 3)
        # mayores que 2.1.326: v2, v3, v4, v8, v9, v10, v11 -> 7 llamadas
        self.assertEqual(q.unverified_calls, 7)
        self.assertEqual(m.unverified_versions,
                         ("2.1.327", "2.1.327-rc1", "2.1.328", "2.1.328-beta", "2.1.330", "2.1.340"))
        self.assertEqual(m.verified_max, "2.1.326")
        seen = dict(m.versions_seen)
        self.assertEqual(seen["2.1.309"], 3)     # v0, v7, v8
        self.assertEqual(seen["2.1.311"], 1)
        self.assertEqual([k for k, _ in m.versions_seen][:4], ["2.1.309", "2.1.310", "2.1.311", "2.1.315"])
        self.assertNotIn("(otra version)", seen)

    def test_no_version_row_is_labelled_as_unrecognizable_and_counters_stay_apart(self):
        # la fila reune llamadas sin version y con version no reconocible; la etiqueta lo dice y los
        # contadores de calidad las separan
        self.assertEqual(ur.RANGE_NONE, "sin version reconocible")
        self.assertEqual(ur.VERSION_RANGES[-1], ur.RANGE_NONE)
        calls = [mk(0, versions=()), mk(1, versions=()), mk(2, versions=("(otra version)",)),
                 mk(3, versions=("2.1.330",))]
        m = agg(calls)
        rows = {r.range: r.calls for r in m.total.versions}
        self.assertEqual(rows[ur.RANGE_NONE], 3)
        self.assertEqual((m.quality.without_version, m.quality.unrecognized_version), (2, 1))
        ur.RANGE_NONE.encode("ascii")

    def test_each_scope_has_its_own_breakdown_and_a_new_version_is_unverified(self):
        calls = [mk(0, versions=("9.9.9",)), mk(1, agent="scout", versions=("2.1.300",))]
        m = agg(calls)
        self.assertEqual(m.unverified_versions, ("9.9.9",))
        self.assertEqual(m.quality.unverified_calls, 1)
        rows = {r.range: r.calls for r in m.total.versions}
        self.assertEqual((rows[ur.RANGE_BEFORE], rows[ur.RANGE_AFTER]), (1, 1))
        forge = [a for a in m.agents if a.agent == "forge"][0]
        self.assertEqual({r.range: r.calls for r in forge.metrics.versions}[ur.RANGE_AFTER], 1)

    def test_excluded_calls_count_in_versions_calls_but_not_in_tokens(self):
        m = agg([mk(0, versions=("2.1.300",)), damaged(1, versions=("2.1.300",))], check_damage=False)
        row = [r for r in m.total.versions if r.range == ur.RANGE_BEFORE][0]
        self.assertEqual((row.calls, row.tokens.n), (2, 1))


class ConsecutiveRepeats(unittest.TestCase):
    @staticmethod
    def _t(a, b):
        return {"start": dt(10, 10, 0, a), "end": dt(10, 10, 0, b)}

    def repeats(self, calls):
        return agg(calls).total.repeats

    def test_sequential_same_agent_counts_the_later_call(self):
        self.assertEqual(self.repeats([mk(0, **self._t(0, 10)), mk(1, **self._t(11, 20))]), 1)

    def test_three_in_a_row_count_two(self):
        self.assertEqual(self.repeats([mk(0, **self._t(0, 1)), mk(1, **self._t(2, 3)), mk(2, **self._t(4, 5))]), 2)

    def test_parallel_calls_do_not_count(self):
        self.assertEqual(self.repeats([mk(0, **self._t(0, 10)), mk(1, **self._t(5, 15))]), 0)

    def test_touching_calls_do_not_count(self):
        # la anterior debe terminar ESTRICTAMENTE antes de que empiece la siguiente
        self.assertEqual(self.repeats([mk(0, **self._t(0, 10)), mk(1, **self._t(10, 20))]), 0)

    def test_other_agent_in_between_breaks_the_chain(self):
        calls = [mk(0, **self._t(0, 10)), mk(1, agent="scout", **self._t(11, 12)), mk(2, **self._t(13, 20))]
        self.assertEqual(self.repeats(calls), 0)

    def test_parallel_pair_then_a_later_call(self):
        # A [0,10], B [2,12] en paralelo; C [13,14]: la anterior de C es B (termino en 12) -> cuenta
        calls = [mk(0, **self._t(0, 10)), mk(1, **self._t(2, 12)), mk(2, **self._t(13, 14))]
        self.assertEqual(self.repeats(calls), 1)

    def test_different_sessions_do_not_chain(self):
        calls = [mk(0, session="s1", **self._t(0, 10)), mk(1, session="s2", **self._t(11, 20))]
        self.assertEqual(self.repeats(calls), 0)

    def test_same_agent_name_in_other_group_is_not_a_repeat(self):
        calls = [mk(0, agent="(otro agente)", agent_group="otros", **self._t(0, 1)),
                 mk(1, agent="(otro agente)", agent_group="plugin:(no-valido)", **self._t(2, 3))]
        self.assertEqual(self.repeats(calls), 0)

    def test_order_independent_attributed_to_the_agent_and_calls_without_times_skipped(self):
        calls = [mk(0, **self._t(0, 1)), mk(1, **self._t(2, 3)), mk(2, agent="scout", **self._t(4, 5)),
                 mk(3, start=None, end=None, fallback_time=dt(10))]
        for order in (calls, calls[::-1], [calls[2], calls[0], calls[3], calls[1]]):
            m = agg(order)
            self.assertEqual({a.agent: a.metrics.repeats for a in m.agents}, {"forge": 1, "scout": 0})
            self.assertEqual(m.total.repeats, 1)

    def test_damaged_call_that_kept_its_times_still_takes_part(self):
        m = agg([mk(0, **self._t(0, 1)), damaged(1, **self._t(2, 3))], check_damage=False)
        self.assertEqual(m.total.repeats, 1)

    def test_same_agent_means_same_internal_key_not_same_visible_label(self):
        def plugin(n, key, a, b):
            return mk(n, agent="plugin:pl", agent_group="plugin:pl", agent_key=key, **self._t(a, b))

        def other(n, key, a, b):
            return mk(n, agent="(otro agente)", agent_group="otros", agent_key=key, **self._t(a, b))

        # dos agentes distintos del mismo plugin, seguidos: no es repeticion
        self.assertEqual(self.repeats([plugin(0, "pa", 0, 1), plugin(1, "pb", 2, 3)]), 0)
        # el mismo agente dos veces: si
        self.assertEqual(self.repeats([plugin(0, "pa", 0, 1), plugin(1, "pa", 2, 3)]), 1)
        # dos agentes de usuario distintos bajo `(otro agente)`: no; el mismo: si
        self.assertEqual(self.repeats([other(0, "ua", 0, 1), other(1, "ub", 2, 3)]), 0)
        self.assertEqual(self.repeats([other(0, "ua", 0, 1), other(1, "ua", 2, 3)]), 1)
        # A B A con A y B del mismo conjunto: B rompe la cadena
        self.assertEqual(self.repeats([other(0, "ua", 0, 1), other(1, "ub", 2, 3), other(2, "ua", 4, 5)]), 0)
        # se atribuye al agente por etiqueta visible: el agregado por (agente, conjunto) lo suma
        m = agg([other(0, "ua", 0, 1), other(1, "ua", 2, 3), other(2, "ub", 4, 5)])
        self.assertEqual({(a.agent, a.group): a.metrics.repeats for a in m.agents}, {("(otro agente)", "otros"): 1})

    def test_calls_without_meta_are_never_marked_as_repeats(self):
        # decision: sin meta no hay identidad de agente (pueden ser agentes distintos), asi que una
        # llamada sin meta nunca se marca; si participa en la cadena y rompe la de otros agentes
        def nometa(n, a, b):
            return mk(n, agent="(sin-meta)", agent_group="sin-meta", has_meta=False, **self._t(a, b))

        self.assertEqual(self.repeats([nometa(0, 0, 1), nometa(1, 2, 3), nometa(2, 4, 5)]), 0)
        calls = [mk(0, **self._t(0, 1)), nometa(1, 2, 3), mk(2, **self._t(4, 5))]
        self.assertEqual(self.repeats(calls), 0)        # la llamada sin meta rompe la cadena de forge
        self.assertEqual(self.repeats([mk(0, **self._t(0, 1)), mk(1, **self._t(2, 3)), nometa(2, 4, 5)]), 1)

    def test_tie_on_start_and_end_is_broken_by_the_traversal_ordinal_never_by_call_id(self):
        # X (forge, seq mayor) e Y (scout, seq menor) empiezan y terminan a la vez; Z (scout) viene
        # despues. Con desempate por seq el orden es Y, X, Z: la anterior de Z es X (forge): 0.
        # Sin el desempate, el orden de entrada (X, Y, Z) daria 1. Los call_id van AL REVES de los seq:
        # si el desempate fuera call_id, el resultado seria el contrario.
        x = mk(0, seq=9, call_id="c1", agent="forge", **self._t(0, 10))
        y = mk(1, seq=1, call_id="c9", agent="scout", **self._t(0, 10))
        z = mk(2, seq=5, call_id="c5", agent="scout", **self._t(20, 30))
        for order in ([x, y, z], [z, y, x], [y, z, x], [x, z, y]):
            self.assertEqual(self.repeats(order), 0)
        # con los seq invertidos el orden es X, Y, Z: la anterior de Z es Y (scout): 1
        x2, y2 = mk(0, seq=1, call_id="c1", agent="forge", **self._t(0, 10)), \
            mk(1, seq=9, call_id="c9", agent="scout", **self._t(0, 10))
        for order in ([x2, y2, z], [z, y2, x2], [y2, z, x2]):
            self.assertEqual(self.repeats(order), 1)

    def test_adjacency_is_an_inferred_signal_with_documented_limits(self):
        # A1 [0,100], A2 [10,20], A3 [30,40] del mismo agente: A3 se marca aunque corre en paralelo
        # con A1 (la anterior inmediata es A2, que ya termino); A2 no (A1 aun no termina)
        def secs(a, b):
            base = dt(10, 10)
            return {"start": base + datetime.timedelta(seconds=a), "end": base + datetime.timedelta(seconds=b)}

        calls = [mk(1, **secs(0, 100)), mk(2, **secs(10, 20)), mk(3, **secs(30, 40))]
        self.assertEqual(agg(calls).total.repeats, 1)
        flagged = ur.repeat_flags(calls)
        self.assertEqual(flagged, frozenset(["c003"]))
        # una llamada sin `start` no rompe la cadena (ni siquiera participa)
        calls = [mk(0, **self._t(0, 1)), mk(1, start=None, end=None, fallback_time=dt(10), agent="scout"),
                 mk(2, **self._t(2, 3))]
        self.assertEqual(agg(calls).total.repeats, 1)
        # la llamada cuya anterior quedo fuera de la ventana no se marca
        old = datetime.datetime(2026, 1, 1, tzinfo=UTC)
        calls = [mk(0, start=old, end=old + datetime.timedelta(seconds=1)), mk(1, **self._t(2, 3))]
        self.assertEqual(agg(calls).total.repeats, 0)
        self.assertEqual(agg(calls, window=ur.make_window(TODAY, all_time=True)).total.repeats, 1)
        # sobreestima los flujos secuenciales legitimos: dos revisiones por el mismo agente en pasos
        # distintos de un plan cuentan igual que un reintento
        self.assertEqual(self.repeats([mk(0, **self._t(0, 1)), mk(1, **self._t(50, 51))]), 1)

    def test_limitations_text_for_the_report_is_fixed_text_and_covers_each_limit(self):
        self.assertIsInstance(ur.REPEAT_LIMITATIONS, tuple)
        self.assertEqual(len(ur.REPEAT_LIMITATIONS), 6)
        for line in ur.REPEAT_LIMITATIONS:
            line.encode("utf-8")
        self.assertIn("señal", ur.REPEAT_LIMITATIONS[0])
        joined = " ".join(ur.REPEAT_LIMITATIONS)
        for needle in ("inferida", "paralelo", "sin hora de inicio", "fuera de la ventana", "sin meta",
                       "secuenciales"):
            self.assertIn(needle, joined)


class AggregationDeterminismAndPurity(unittest.TestCase):
    def _many(self):
        rnd = random.Random(7)
        agents = (("forge", "SyncLayer"), ("scout", "SyncLayer"), ("(otro agente)", "otros"),
                  ("plugin:pl", "plugin:pl"))
        calls = []
        for i in range(40):
            name, group = agents[i % 4]
            calls.append(mk(i, agent=name, agent_group=group, project="p-0000000%d" % (i % 3),
                            session="s%d" % (i % 5), input_tokens=rnd.randrange(1, 5000),
                            tools=rnd.randrange(0, 9),
                            versions=(rnd.choice(("2.1.300", "2.1.315", "2.1.330")),),
                            model=rnd.choice(("claude-opus-4-1", "mixto")),
                            **span(rnd.randrange(0, 120), day=1 + i % 28)))
        return calls

    def test_same_input_same_output_in_any_order(self):
        calls = self._many()
        base = agg(calls)
        rnd = random.Random(1)
        for _ in range(4):
            shuffled = list(calls)
            rnd.shuffle(shuffled)
            other = agg(shuffled)
            self.assertEqual(other, base)
            self.assertEqual(repr(other), repr(base))
        self.assertEqual(repr(agg(calls)), repr(base))

    def test_aggregation_does_no_io(self):
        calls = self._many()

        def boom(*a, **k):
            raise AssertionError("E/S en la agregacion")

        with mock.patch("builtins.open", boom), mock.patch.object(os, "stat", boom),                 mock.patch.object(os, "lstat", boom), mock.patch.object(os, "scandir", boom),                 mock.patch.object(os, "listdir", boom), mock.patch.object(os, "open", boom),                 mock.patch.object(os, "fstat", boom):
            agg(calls)
            agg(calls, window=ur.make_window(TODAY, all_time=True))
            agg(self._many()[:0], window=ur.make_window(TODAY))

    # Todo lo que `aggregate_calls` puede alcanzar (funciones, clases y constantes del modulo, por
    # nombre). Lista BLANCA y cerrada: un nombre nuevo hace fallar la prueba y obliga a revisarlo.
    PURE_REACHABLE = frozenset((
        "aggregate_calls", "make_window", "Window", "Dist", "distribution", "TokenStats", "VersionRow",
        "ScopeMetrics", "AgentMetrics", "GroupMetrics", "ProjectMetrics", "DataQuality", "UsageMetrics",
        "_range_of", "_numeric_versions", "version_range", "_spans_ranges", "_call_moment",
        "_duration_seconds", "token_stats", "repeat_flags", "_scope", "_data_quality", "_by_key",
        "check_damaged", "_schema_message", "_versions_text", "_recent_first", "is_unverified",
        "version_key", "SchemaError", "ReadResult",
        "MAX_DAMAGED_PERCENT", "MAX_SHOWN_VERSIONS", "RANGE_AFTER", "RANGE_BEFORE", "RANGE_DOUBTFUL",
        "RANGE_NONE", "READ_QUALITY_LABELS", "SMALL_N", "VERIFIED_MAX", "VERSION_RANGES", "WINDOW_DAYS",
        "WARN_ID_CAP", "WARN_ID_REPEATED", "WARN_NO_MESSAGE_ID", "_DOUBTFUL_FROM", "_DOUBTFUL_TO",
        "_VERSION_PARTS_RE", "MSG_TODAY_REQUIRED", "MSG_WINDOW_RANGE", "MSG_WINDOW_INVALID", "NO_META_KEY",
        # T4: skills, validacion de tipos de la ventana
        "skill_metrics", "SkillRow", "SkillGroupRow", "SkillAgentRow", "SkillQuality", "SkillMetrics",
        "OTHER_SKILL", "ORIGIN_MAIN", "ORIGIN_SUBAGENT", "WARN_SKILL_ID_REPEATED",
        "WARN_SKILL_ID_CAP", "_is_date", "MSG_WINDOW_TYPES",
        "WARN_MAIN_HARDLINK", "WARN_MAIN_CAP", "WARN_MAIN_UNREADABLE", "WARN_ALIAS_COLLISION",
    ))
    # Nombres de funcion que el codigo alcanzable puede llamar (ademas de los de PURE_REACHABLE).
    CALLABLE_OK = frozenset((
        # integrados
        "ValueError", "bool", "frozenset", "int", "isinstance", "len", "list", "max", "min", "set", "sorted",
        "str", "sum", "tuple", "zip", "any", "all", "range", "dict", "enumerate", "reversed",
        # metodos de contenedores, de re y de las fechas
        "Counter", "defaultdict", "add", "append", "sort", "items", "values", "get", "match", "join",
        "timedelta", "astimezone", "replace", "date", "contains", "__init__", "__post_init__", "field",
        "dataclass", "super", "format", "isoformat", "groups", "id",
    ))
    FORBIDDEN = frozenset((
        "now", "utcnow", "fromtimestamp", "__import__", "importlib", "io", "getattr", "setattr",
        "hasattr", "Path", "tempfile", "open", "os", "sys", "subprocess", "shutil", "pathlib", "print",
        "input", "eval", "exec", "compile", "globals", "locals", "vars", "stat", "lstat", "fstat",
        "scandir", "listdir", "read", "write", "readline", "time", "environ", "getenv", "socket",
    ))
    # Funciones del lector que hacen E/S: la agregacion no puede alcanzarlas ni de forma indirecta.
    READER_IO_FUNCTIONS = ("_read_call", "_enum_sessions", "_read_project_folder", "derive_folder_name",
                           "read_calls", "_read_session", "_open_regular", "_list_dir", "_read_meta",
                           "_scan_project_folder", "_iter_objects", "utc_today", "_default_claude_dir")

    @staticmethod
    def _module_tree():
        with open(SCRIPT, "rb") as f:
            return ast.parse(f.read().decode("utf-8"))

    def _reachable(self):
        top = {}
        for node in self._module_tree().body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                top[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        top[target.id] = node
        seen, todo = set(), ["aggregate_calls"]
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            for n in ast.walk(top[name]):
                if isinstance(n, ast.Name) and n.id in top:
                    todo.append(n.id)
        return seen, top

    def test_aggregation_reaches_only_pure_code(self):
        seen, top = self._reachable()
        self.assertEqual(seen, set(self.PURE_REACHABLE))
        for name in self.READER_IO_FUNCTIONS:
            self.assertNotIn(name, seen)
        for name in seen:
            node = top[name]
            if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                continue   # constantes del modulo (p. ej. un re.compile al importar): no se ejecutan por llamada
            params = {a.arg for a in ast.walk(node) if isinstance(a, ast.arg)}   # `key(c)`, `pred(c)`
            params |= {f.name for f in ast.walk(node) if isinstance(f, ast.FunctionDef)}   # `count` anidada
            for n in ast.walk(node):
                self.assertNotIsInstance(n, (ast.Import, ast.ImportFrom), name)
                if isinstance(n, ast.Name):
                    self.assertNotIn(n.id, self.FORBIDDEN, name)
                if isinstance(n, ast.Attribute):
                    self.assertNotIn(n.attr, self.FORBIDDEN, name)
                if isinstance(n, ast.Call):
                    callee = n.func.id if isinstance(n.func, ast.Name) else (
                        n.func.attr if isinstance(n.func, ast.Attribute) else None)
                    self.assertIsNotNone(callee, name)
                    self.assertIn(callee, set(self.PURE_REACHABLE) | self.CALLABLE_OK | params,
                                  "%s llama a %s" % (name, callee))
        # `utc_today` (la unica que lee el reloj) existe pero no la alcanza ninguna funcion pura
        self.assertIn("utc_today", {n.name for n in self._module_tree().body if isinstance(n, ast.FunctionDef)})

    def test_purity_check_itself_rejects_forbidden_calls(self):
        # autoprueba: el mismo criterio sobre trozos con E/S debe fallar
        for snippet in ("import io", "x = getattr(a, 'b')", "p = Path('.')", "t = tempfile.mkdtemp()",
                        "d = datetime.datetime.now()", "m = __import__('os')", "importlib.import_module('os')",
                        "open('x')", "os.fstat(3)", "os.open('x', 0)"):
            names = set()
            for n in ast.walk(ast.parse(snippet)):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    names.add("import")
                if isinstance(n, ast.Name):
                    names.add(n.id)
                if isinstance(n, ast.Attribute):
                    names.add(n.attr)
            self.assertTrue(names & (self.FORBIDDEN | {"import"}), snippet)

    def test_results_are_frozen_and_hold_no_call_or_session_identifiers(self):
        m = agg([mk(0, call_id="IDENT-CALL", session="IDENT-SESSION")])
        text = repr(m)
        self.assertNotIn("IDENT-CALL", text)
        self.assertNotIn("IDENT-SESSION", text)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            m.total.calls = 5


class AggregationOverSyntheticTree(ReaderBase):
    FOLDER_A = "c--Users-" + us.M_FOLDER + "-proj"

    def _tree(self):
        tree = us.Tree(self.base)
        ts = "2026-03-10T10:00:%02dZ"
        a1 = [us.user(ts % 0, version="2.1.309"),
              us.assistant("m1", ts % 3, usage_value=us.usage(10, 5, 2, 3), version="2.1.309",
                           blocks=[us.tool_use_block("t1", "Read"), us.tool_use_block("t2", "Bash")]),
              us.assistant("m2", ts % 6, usage_value=us.usage(20, 10, 4, 6), version="2.1.309"),
              us.assistant("m3", ts % 10, usage_value=us.usage(30, 15, 6, 9), version="2.1.309")]
        tree.subagent(self.FOLDER_A, us.M_SESSION + "-1", "a1", a1)
        tree.subagent(self.FOLDER_A, us.M_SESSION + "-1", "a2",
                      [us.user(ts % 20), us.assistant("m4", ts % 30, usage_value=us.usage(1, 1, 1, 1))])
        tree.subagent(self.FOLDER_A, us.M_SESSION + "-2", "a3", [us.assistant("m5", "2026-03-12T09:00:00Z")],
                      meta={"agentType": "scout"})
        tree.subagent(self.FOLDER_A, us.M_SESSION + "-2", "a4", [us.assistant("m6", "2026-03-12T09:05:00Z")],
                      meta=None)
        tree.subagent(self.FOLDER_A, us.M_SESSION + "-1", "a5",
                      [us.assistant("m7", "2026-01-01T09:00:00Z", version="2.1.300")])   # fuera de la ventana
        empty = tree.subagent(self.FOLDER_A, us.M_SESSION + "-3", "a6", [], meta={"agentType": "oracle"})
        stamp = dt(15, 12).timestamp()
        os.utime(empty, (stamp, stamp))
        tree.subagent("c--otra", us.M_SESSION + "-9", "a7",
                      [us.assistant("m8", "2026-03-20T08:00:00Z", version="2.1.311")],
                      meta={"agentType": "pl:" + us.M_TYPE})
        return tree

    def test_hand_computed_metrics(self):
        res = self.read(self._tree(), check_damage=False)
        m = ur.aggregate_calls(res, today=TODAY)
        q = m.quality
        self.assertEqual((q.calls_read, q.calls_in_window, q.calls_outside_window), (7, 6, 1))
        self.assertEqual((q.without_start, q.placed_by_fallback, q.without_usage, q.without_meta,
                          q.tokens_calls, q.excluded, q.hardlinks), (1, 1, 1, 1, 5, 0, 0))
        self.assertEqual((m.total.calls, m.total.sessions, m.total.calls_per_session_tenths), (6, 4, 15))
        agents = {(a.agent, a.group): a.metrics for a in m.agents}
        self.assertEqual(set(agents), {("forge", "SyncLayer"), ("scout", "SyncLayer"), ("oracle", "SyncLayer"),
                                       ("(sin-meta)", "sin-meta"), ("plugin:pl", "plugin:pl")})
        self.assertEqual([(a.agent, a.group) for a in m.agents][0], ("forge", "SyncLayer"))
        forge = agents[("forge", "SyncLayer")]
        # a1: input 10+20+30=60, salida 30, caches 12 y 18 -> 120 tokens, 3 peticiones; a2: 4 tokens, 1 peticion
        self.assertEqual((forge.calls, forge.sessions, forge.calls_per_session_tenths), (2, 1, 20))
        t = forge.tokens
        # totales [4, 120]: mediana (4+120)/2=62; p90 posicion 2 -> 120. Entrada [1, 60]: (1+60)/2=30,5 -> 31
        self.assertEqual((t.n, t.total.median, t.total.p90, t.input_tokens.median), (2, 62, 120, 31))
        self.assertEqual((t.requests.median, t.requests.total), (2, 4))     # [1, 3] -> 2
        self.assertEqual((forge.tools.median, forge.tools.p90), (1, 2))     # [0, 2]: (0+2)/2=1; posicion 2 -> 2
        self.assertEqual((forge.duration.median, forge.duration.p90), (10, 10))   # a1 10 s, a2 10 s
        self.assertEqual(forge.repeats, 1)     # a2 empieza (10:00:20) despues de que a1 termina (10:00:10)
        self.assertEqual(forge.models, (("claude-opus-4-1", 2),))
        rows = {r.range: r for r in m.total.versions}
        self.assertEqual((rows[ur.RANGE_BEFORE].calls, rows[ur.RANGE_BEFORE].tokens.total.total), (1, 120))
        self.assertEqual((rows[ur.RANGE_DOUBTFUL].calls, rows[ur.RANGE_DOUBTFUL].tokens.total.total), (1, 20))
        self.assertEqual((rows[ur.RANGE_AFTER].calls, rows[ur.RANGE_AFTER].tokens.total.total), (3, 44))
        self.assertEqual((rows[ur.RANGE_NONE].calls, rows[ur.RANGE_NONE].tokens.n), (1, 0))
        self.assertEqual([(g.group, g.metrics.calls) for g in m.groups],
                         [("SyncLayer", 4), ("plugin:pl", 1), ("sin-meta", 1)])
        self.assertEqual([p.metrics.calls for p in m.projects], [5, 1])
        self.assertEqual(m.projects[0].project, res.calls[0].project)
        self.assertEqual(m.warnings, ())

    def test_agent_key_tells_agents_of_one_plugin_apart_and_never_shows_the_raw_type(self):
        tree = us.Tree(self.base)
        ts = "2026-03-10T10:00:%02dZ"
        raws = ("pl:" + us.M_TYPE + "1", "pl:" + us.M_TYPE + "2", "pl:" + us.M_TYPE + "2", us.M_TYPE + "3")
        for i, raw in enumerate(raws):
            tree.subagent("c--p", "s1", "a%d" % i,
                          [us.assistant("m%d" % i, ts % (i * 10)), us.assistant("n%d" % i, ts % (i * 10 + 5))],
                          meta={"agentType": raw})
        tree.subagent("c--p", "s1", "z", [us.assistant("mz", ts % 50)], meta=None)
        res = self.read(tree)
        calls = res.calls
        keys = {c.agent_group + "|" + c.agent_key for c in calls}
        self.assertEqual(len(keys), 4)   # pl1, pl2 (x2), otros, sin-meta
        plugin_calls = [c for c in calls if c.agent_group == "plugin:pl"]
        self.assertEqual(len(plugin_calls), 3)
        self.assertEqual(len({c.agent_key for c in plugin_calls}), 2)
        for c, raw in zip([x for x in calls if x.agent_group != "sin-meta"], raws):
            self.assertEqual(c.agent_key, ur._digest(raw, res._key).hex())
        self.assertEqual([c.agent_key for c in calls if c.agent_group == "sin-meta"], [ur.NO_META_KEY])
        # un agentType crudo y distinto de otro nunca comparte clave
        self.assertNotEqual(plugin_calls[0].agent_key, plugin_calls[1].agent_key)
        m = ur.aggregate_calls(res, today=TODAY)
        self.assertEqual({g.group: g.agents for g in m.groups}, {"plugin:pl": 2, "otros": 1, "sin-meta": 1})
        self.assertEqual(m.total.repeats, 1)          # a2 repite a a1; a1 no repite a a0 (otro agente del plugin)
        # ni la clave ni el agentType crudo salen en repr/str de la llamada ni del resultado
        for c in calls:
            for text in (repr(c), str(c), repr(m)):
                self.assertNotIn(c.agent_key, text)
        self.assert_no_markers(m, *calls, [str(c) for c in calls])
        self.assertNotIn("agent_key", repr(calls[0]))

    def test_nothing_sensitive_in_the_result(self):
        res = self.read(self._tree(), check_damage=False)
        text = repr(ur.aggregate_calls(res, today=TODAY))
        self.assert_no_markers(text)
        for call in res.calls:
            self.assertNotIn(call.call_id, text)
            self.assertNotIn(call.session, text)
        self.assertNotIn("c--otra", text)
        text.encode("ascii")

    def test_warnings_and_read_quality_come_from_the_read_result(self):
        tree = us.Tree(self.base)
        line = us.assistant("x", "2026-03-10T10:00:00Z")
        del line["message"]["id"]
        tree.subagent("c--p", "s1", "a1", [line])
        tree.subagent("c--p", "s1", "a2", [us.assistant("dup", "2026-03-10T10:00:01Z")])
        tree.subagent("c--p", "s1", "a3", [us.assistant("dup", "2026-03-10T10:00:02Z")])
        res = self.read(tree)
        m = ur.aggregate_calls(res, today=TODAY)
        self.assertEqual(m.warnings, tuple(res.warnings))
        self.assertEqual(len(m.warnings), 2)
        rq = dict(m.read_quality)
        self.assertEqual((rq["usage sin message.id"], rq["message.id repetido entre archivos"]), (1, 1))
        self.assertEqual(rq["hardlinks duplicados dentro de projects"], 0)
        # el archivo con todos sus ids repetidos tiene 0 peticiones: no entra en los tokens
        self.assertEqual(m.quality.all_ids_repeated, 1)
        self.assertEqual(m.total.tokens.n, 2)
        # una lista de llamadas suelta no trae avisos
        self.assertEqual(ur.aggregate_calls(res.calls, today=TODAY).warnings, ())

    def test_hardlinks_are_counted_in_quality(self):
        tree = us.Tree(self.base)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        target = outer.subagent("c--x", "s9", "a9", [us.assistant("h1", "2026-03-10T10:00:00Z")], meta=None)
        sub = os.path.join(tree.folder("c--p"), "s1", "subagents")
        os.makedirs(sub)
        self.hardlink(target, os.path.join(sub, "agent-h.jsonl"))
        m = ur.aggregate_calls(self.read(tree), today=TODAY)
        self.assertEqual(m.quality.hardlinks, 1)

    def test_oversize_and_model_mismatch_quality(self):
        q = agg([mk(0, oversize_lines=2), mk(1, model_mismatch=True)]).quality
        self.assertEqual((q.oversize_lines, q.model_mismatch), (2, 1))


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


# --- T4: conteo de uso de skills ---
SK_TS = "2026-03-10T10:00:%02dZ"


def su(n, **kw):
    """SkillUse a mano. Por defecto: la skill `brainstorm` (conjunto otros) invocada desde la sesion
    principal s1 el 10 de marzo a las 10:00 UTC."""
    fields = dict(skill="brainstorm", group="otros", origin="sesion", project="p-00000001",
                  session="s1", moment=dt(10, 10), agent=None, agent_group=None)
    fields.update(kw)
    return ur.SkillUse(**fields)


# Nombres de prueba para la lista de skills integradas: BUILTIN_SKILLS esta vacia (sin evidencia), asi que
# las pruebas del MECANISMO de lista cerrada la sustituyen por estos.
TEST_BUILTIN_SKILLS = frozenset(("review", "init"))


class SkillClassification(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ur, "BUILTIN_SKILLS", TEST_BUILTIN_SKILLS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_names_by_closed_lists_and_narrow_pattern(self):
        other = ur.OTHER_SKILL
        self.assertEqual(other, "(otra skill)")
        cases = (
            ("brainstorm", ("brainstorm", "otros")),
            ("my_skill-2", ("my_skill-2", "otros")),
            ("0abc", ("0abc", "otros")),
            ("x" * 64, ("x" * 64, "otros")),            # 1 + 63 caracteres: el maximo
            ("x" * 65, (other, "otros")),
            ("review", ("review", "integrado")),
            ("init", ("init", "integrado")),
            # plugin:skill -> solo el prefijo validado; lo que hay tras el primer ":" no se muestra
            ("superpowers:brainstorming", ("plugin:superpowers", "plugin:superpowers")),
            ("a:b:c", ("plugin:a", "plugin:a")),
            ("pl:" + us.M_SKILL_TAIL, ("plugin:pl", "plugin:pl")),
            ("pl:", ("plugin:pl", "plugin:pl")),
            ("a" * 32 + ":x", ("plugin:" + "a" * 32, "plugin:" + "a" * 32)),
            ("a" * 33 + ":x", (other, "plugin:(no-valido)")),
            ("Mi:skill", (other, "plugin:(no-valido)")),
            (":x", (other, "plugin:(no-valido)")),
            ("p_q:x", (other, "plugin:(no-valido)")),
            # nombres que no pasan la lista permitida
            ("", (other, "otros")),
            ("Brainstorm", (other, "otros")),
            ("a b", (other, "otros")),
            (us.M_SKILL, (other, "otros")),
            ("ok\n", (other, "otros")),
            ("-x", (other, "otros")),
            ("x/y", (other, "otros")),
            ("x.y", (other, "otros")),
            ("x@y", (other, "otros")),
            ("café", (other, "otros")),
            # no cadenas
            (None, (other, "otros")),
            (5, (other, "otros")),
            (True, (other, "otros")),
            ({"a": 1}, (other, "otros")),
            (["x"], (other, "otros")),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(ur.classify_skill(raw), expected)
                for text in ur.classify_skill(raw):
                    self.assertNotIn("ZZMARK", text)

    def test_synclayer_ships_no_skills_today_and_the_set_is_honoured(self):
        self.assertEqual(ur.SYNCLAYER_SKILLS, frozenset())
        with mock.patch.object(ur, "SYNCLAYER_SKILLS", frozenset(("mine",))):
            self.assertEqual(ur.classify_skill("mine"), ("mine", "SyncLayer"))
            self.assertEqual(ur.classify_skill("other"), ("other", "otros"))

    def test_builtin_names_pass_the_narrow_pattern_and_never_collide_with_synclayer(self):
        for name in ur.BUILTIN_SKILLS | ur.SYNCLAYER_SKILLS:
            self.assertRegex(name, ur.SKILL_NAME_RE.pattern)
            self.assertNotIn(":", name)
        self.assertFalse(ur.BUILTIN_SKILLS & ur.SYNCLAYER_SKILLS)

    def test_pattern_does_not_admit_a_colon(self):
        self.assertNotIn(":", ur.SKILL_NAME_RE.pattern)
        self.assertIsNone(ur.SKILL_NAME_RE.match("a:b"))
        self.assertIsNotNone(ur.SKILL_NAME_RE.match("a_b-c1"))
        # el nombre con ":" nunca llega al patron: sale como plugin
        self.assertEqual(ur.classify_skill("a:b"), ("plugin:a", "plugin:a"))

    def test_user_skill_names_are_shown_as_is_documented_as_asymmetric_privacy_risk(self):
        # una skill de usuario sale tal cual; un agente de usuario sale como "(otro agente)"
        self.assertEqual(ur.classify_skill("mi-skill-privada"), ("mi-skill-privada", "otros"))
        self.assertEqual(ur.classify_agent("mi-agente-privado"), (ur.OTHER_AGENT, "otros"))
        self.assertIn("asimetric", ur.classify_skill.__doc__)
        self.assertIn("USUARIO", ur.classify_skill.__doc__)
        self.assertIn("(otra skill)", ur.classify_skill.__doc__)
        self.assertIn("T6", ur.classify_skill.__doc__)


class SkillBuiltinDefault(unittest.TestCase):
    def test_builtin_list_is_empty_without_evidence(self):
        self.assertEqual(ur.BUILTIN_SKILLS, frozenset())
        for name in ("init", "review", "security-review", "simplify", "loop"):
            self.assertEqual(ur.classify_skill(name), (name, "otros"))


class SkillReading(ReaderBase):
    FOLDER = "c--p"

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(ur, "BUILTIN_SKILLS", TEST_BUILTIN_SKILLS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def main(self, tree, sid, items, folder=None, **kw):
        return tree.main_session(folder or self.FOLDER, sid, items, **kw)

    def uses(self, res):
        return [(u.skill, u.group, u.origin) for u in res.skill_uses]

    def test_skill_invoked_twice_in_one_session_and_once_in_another(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [
            us.user(SK_TS % 0, sidechain=False),
            us.skill_line("a1", SK_TS % 1, ["brainstorm"]),
            us.skill_line("a2", SK_TS % 5, ["brainstorm", "review"]),
        ])
        self.main(tree, "s2", [us.skill_line("b1", SK_TS % 9, ["brainstorm"])])
        res = self.read(tree)
        self.assertEqual(res.calls, [])    # una sesion sin subagentes no produce llamadas de agente
        self.assertEqual(len(res.skill_uses), 4)
        m = agg(res)
        s = m.skills
        # brainstorm: 3 invocaciones (2 en s1, 1 en s2) en 2 sesiones; review: 1 en s1
        self.assertEqual([(r.skill, r.group, r.calls, r.main_calls, r.subagent_calls, r.sessions) for r in s.rows],
                         [("brainstorm", "otros", 3, 3, 0, 2), ("review", "integrado", 1, 1, 0, 1)])
        self.assertEqual((s.calls, s.sessions, s.main_calls, s.subagent_calls), (4, 2, 4, 0))
        # por conjunto: otros = brainstorm (3 llamadas, 1 skill, 2 sesiones); integrado = review (1, 1, 1)
        self.assertEqual([(g.group, g.skills, g.calls, g.sessions) for g in s.groups],
                         [("otros", 1, 3, 2), ("integrado", 1, 1, 1)])
        self.assertEqual(s.by_agent, ())
        q = s.quality
        self.assertEqual((q.uses_read, q.in_window, q.outside_window, q.without_time, q.other_name), (4, 4, 0, 0, 0))
        self.assertEqual(m.window, ur.make_window(TODAY))
        self.assertEqual(res.quality["sesiones principales leidas"], 2)

    def test_repeated_lines_and_repeated_block_ids_count_once_blocks_without_id_each_time(self):
        tree = us.Tree(self.base)
        line = us.skill_line("a1", SK_TS % 1, ["brainstorm"])
        other_line_same_block = us.assistant("a9", SK_TS % 2, blocks=[us.skill_block("a1-s0", "brainstorm")],
                                             sidechain=False)
        no_id = us.assistant("c1", SK_TS % 3, sidechain=False, blocks=[
            {"type": "tool_use", "name": "Skill", "input": {"skill": "review"}},
            {"type": "tool_use", "id": 7, "name": "Skill", "input": {"skill": "review"}},
        ])
        self.main(tree, "s1", [line, line, other_line_same_block, no_id])
        res = self.read(tree)
        # el bloque a1-s0 cuenta una vez; los dos bloques sin id (ausente o no cadena) cuentan cada uno
        self.assertEqual(self.uses(res), [("brainstorm", "otros", "sesion"), ("review", "integrado", "sesion"),
                                          ("review", "integrado", "sesion")])
        self.assertEqual(res.quality["skills: tool_use sin id"], 2)
        # repetir una linea dentro del MISMO archivo no es un id repetido entre archivos
        self.assertEqual(res.quality["skills: id repetido entre archivos"], 0)
        self.assertEqual(res.warnings, [])

    def test_same_tool_use_id_in_main_and_subagent_counts_once_and_is_reported(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("dup", SK_TS % 1, ["brainstorm"])])
        tree.subagent(self.FOLDER, "s1", "a1", [us.user(SK_TS % 2), us.skill_line("dup", SK_TS % 3, ["brainstorm"],
                                                                                    sidechain=True)])
        res = self.read(tree)
        self.assertEqual(self.uses(res), [("brainstorm", "otros", "sesion")])   # la sesion principal se lee primero
        self.assertEqual(res.quality["skills: id repetido entre archivos"], 1)
        self.assertIn(ur.WARN_SKILL_ID_REPEATED, res.warnings)
        self.assertEqual(len(res.calls), 1)    # el subagente sigue siendo una llamada

    def test_subagent_skills_are_linked_to_the_agent_that_invoked_them(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("m1", SK_TS % 1, ["x"])])
        tree.subagent(self.FOLDER, "s1", "a1", [us.user(SK_TS % 2), us.skill_line("f1", SK_TS % 3, ["x", "review"],
                                                                                     sidechain=True)])
        tree.subagent(self.FOLDER, "s1", "a2", [us.skill_line("n1", SK_TS % 4, ["x"], sidechain=True)], meta=None)
        tree.subagent(self.FOLDER, "s1", "a3", [us.skill_line("p1", SK_TS % 5, ["x"], sidechain=True)],
                      meta={"agentType": "pl:" + us.M_TYPE})
        tree.subagent(self.FOLDER, "s1", "a4", [us.skill_line("u1", SK_TS % 6, ["x"], sidechain=True)],
                      meta={"agentType": us.M_TYPE})
        tree.subagent(self.FOLDER, "s1", "a5", [us.skill_line("g1", SK_TS % 7, ["x"], sidechain=True)],
                      meta={"agentType": ""})
        res = self.read(tree)
        self.assertEqual(len(res.skill_uses), 7)
        by_origin = collections.Counter(u.origin for u in res.skill_uses)
        self.assertEqual(by_origin, {"sesion": 1, "subagente": 6})
        main_use = [u for u in res.skill_uses if u.origin == "sesion"][0]
        self.assertEqual((main_use.agent, main_use.agent_group), (None, None))
        m = agg(res)
        s = m.skills
        # x: 6 invocaciones (1 principal + 5 de subagentes) en UNA sesion (los subagentes comparten la de su sesion)
        self.assertEqual([(r.skill, r.calls, r.main_calls, r.subagent_calls, r.sessions) for r in s.rows],
                         [("x", 6, 1, 5, 1), ("review", 1, 0, 1, 1)])
        self.assertEqual(s.sessions, 1)
        # por agente: solo las de subagentes; (otro agente) agrupa al de usuario; el vacio es el agente por defecto
        self.assertEqual([(r.agent, r.agent_group, r.skill, r.skill_group, r.calls) for r in s.by_agent], [
            ("(otro agente)", "otros", "x", "otros", 1),
            ("(sin-meta)", "sin-meta", "x", "otros", 1),
            ("forge", "SyncLayer", "review", "integrado", 1),
            ("forge", "SyncLayer", "x", "otros", 1),
            ("general-purpose", "integrado", "x", "otros", 1),
            ("plugin:pl", "plugin:pl", "x", "otros", 1),
        ])
        # la skill y la llamada del subagente comparten el resumen de sesion (clave por ejecucion)
        sub_use = [u for u in res.skill_uses if u.origin == "subagente"][0]
        self.assertEqual(sub_use.session, res.calls[0].session)
        self.assertEqual(sub_use.session, main_use.session)
        self.assertEqual(sub_use.project, res.calls[0].project)

    def test_markers_in_args_skill_names_and_the_rest_of_the_main_session_never_appear(self):
        tree = us.Tree(self.base)
        blocks = [
            us.skill_block("k1", "brainstorm", args=us.M_ARGS, **{us.M_UNKNOWN_INPUT_KEY: us.M_INPUT}),
            us.skill_block("k2", us.M_SKILL, args={"nested": [us.M_ARGS, us.M_PROMPT]}),
            us.skill_block("k3", "pl:" + us.M_SKILL_TAIL, args=None),
            us.skill_block("k4", "review", args=us.M_ARGS * 100),
            us.tool_use_block("k5", "Agent", {"subagent_type": "forge", "prompt": us.M_PROMPT,
                                                 "description": us.M_DESCRIPTION}),
            us.tool_use_block("k6", "Read", {"file_path": us.M_CWD}),
        ]
        self.main(tree, "s1", [
            us.user(SK_TS % 0, sidechain=False),
            us.assistant("m1", SK_TS % 1, blocks=blocks + [us.text_block()], sidechain=False,
                         **{us.M_UNKNOWN_KEY: us.M_CONTENT}),
            us.tool_result_line(SK_TS % 2),
        ])
        tree.subagent(self.FOLDER, "s1", "a1", [us.skill_line("z1", SK_TS % 3, [us.M_SKILL], sidechain=True)],
                      meta={"agentType": "pl:" + us.M_SKILL_TAIL, "description": us.M_DESCRIPTION})
        res = self.read(tree)
        m = agg(res)
        self.assertEqual([(r.skill, r.group, r.calls) for r in m.skills.rows], [
            ("(otra skill)", "otros", 2), ("brainstorm", "otros", 1), ("plugin:pl", "plugin:pl", 1),
            ("review", "integrado", 1)])
        self.assertEqual(m.skills.quality.other_name, 2)
        everything = (res.skill_uses, m, m.skills, res.quality, res.schema, res.versions, res.warnings,
                      res.calls, [str(u) for u in res.skill_uses])
        self.assert_no_markers(*everything)
        self.assertNotIn("args", repr(everything))
        repr(everything).encode("ascii")

    def test_main_session_with_truncated_last_line_keeps_the_complete_lines(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm"]),
                               '{"type": "assistant", "timestamp": "2026-03-10T10:0' + us.M_CONTENT],
                  final_newline=False)
        res = self.read(tree)
        self.assertEqual(self.uses(res), [("brainstorm", "otros", "sesion")])
        self.assertEqual(res.quality["sesiones principales con ultima linea truncada"], 1)
        self.assertEqual(res.quality["lineas corruptas (sesion principal)"], 0)
        self.assert_no_markers(res.quality, res.skill_uses)

    def test_corrupt_oversize_and_non_object_lines_are_counted_and_skipped(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm"]),
                               "no es json " + us.M_CONTENT, "[1, 2]",
                               us.skill_line("a2", SK_TS % 2, ["review"])])
        res = self.read(tree)
        self.assertEqual(len(res.skill_uses), 2)
        self.assertEqual(res.quality["lineas corruptas (sesion principal)"], 1)
        self.assertEqual(res.quality["lineas que no son objeto (sesion principal)"], 1)
        # las del lector de subagentes no se tocan
        self.assertEqual(res.quality["lineas corruptas"], 0)
        tree2 = us.Tree(os.path.join(self.base, "b"))
        self.main(tree2, "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm"]),
                                '{"type": "assistant", "x": "' + "y" * 4000 + '"}',
                                us.skill_line("a2", SK_TS % 2, ["review"])])
        with mock.patch.object(ur, "MAX_LINE_BYTES", 2000):
            res2 = self.read(tree2)
        self.assertEqual(res2.quality["lineas oversize (sesion principal)"], 1)
        self.assertEqual([u.skill for u in res2.skill_uses], ["brainstorm", "review"])

    def test_malformed_skill_values_count_as_other_skill_and_are_reported(self):
        tree = us.Tree(self.base)
        blocks = [
            {"type": "tool_use", "id": "b1", "name": "Skill", "input": {"skill": 5}},
            {"type": "tool_use", "id": "b2", "name": "Skill", "input": {"skill": None}},
            {"type": "tool_use", "id": "b3", "name": "Skill", "input": {"skill": {"a": us.M_SKILL}}},
            {"type": "tool_use", "id": "b4", "name": "Skill", "input": {"skill": [us.M_SKILL]}},
            {"type": "tool_use", "id": "b5", "name": "Skill", "input": {"args": us.M_ARGS}},
            {"type": "tool_use", "id": "b6", "name": "Skill", "input": us.M_INPUT},
            {"type": "tool_use", "id": "b7", "name": "Skill"},
            {"type": "tool_use", "id": "b8", "name": "Skill", "input": {"skill": us.M_SKILL}},
        ]
        self.main(tree, "s1", [us.assistant("m1", SK_TS % 1, blocks=blocks, sidechain=False)])
        res = self.read(tree)
        self.assertEqual(self.uses(res), [("(otra skill)", "otros", "sesion")] * 8)
        self.assertEqual(res.quality["skills: nombre no cadena"], 7)   # b8 es cadena, solo no valida
        self.assert_no_markers(res.skill_uses, res.quality)

    def test_only_skill_tool_use_in_assistant_lines_of_real_requests_counts(self):
        tree = us.Tree(self.base)
        skill = us.skill_block("a1-s0", "brainstorm")
        self.main(tree, "s1", [
            us.assistant("m1", SK_TS % 1, sidechain=False, blocks=[
                us.tool_use_block("t1", "Agent", {"skill": "brainstorm"}),
                us.tool_use_block("t2", "Task", {"skill": "brainstorm"}),
                us.tool_use_block("t3", "skill", {"skill": "brainstorm"}),
                us.tool_use_block("t4", "Skills", {"skill": "brainstorm"}),
                {"type": "text", "id": "t5", "name": "Skill", "input": {"skill": "brainstorm"}},
                {"type": "tool_result", "id": "t6", "name": "Skill", "input": {"skill": "brainstorm"}},
            ]),
            us.user(SK_TS % 2, sidechain=False, **{"message": {"role": "user", "content": [skill]}}),
            us.assistant("m3", SK_TS % 3, model="<synthetic>", blocks=[skill], sidechain=False),
            us.assistant("m4", SK_TS % 4, blocks="no es una lista " + us.M_CONTENT, sidechain=False),
            {"type": "assistant", "timestamp": SK_TS % 5, "message": "texto " + us.M_CONTENT},
        ])
        res = self.read(tree)
        self.assertEqual(res.skill_uses, [])
        self.assertEqual(res.quality["sesiones principales leidas"], 1)

    def test_main_session_failures_leave_no_partial_counts(self):
        # archivo mayor que el tope por fstat: omitido entero
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("a%d" % i, SK_TS % i, ["brainstorm"]) for i in range(20)])
        with mock.patch.object(ur, "MAX_FILE_BYTES", 2000):
            res = self.read(tree)
        self.assertEqual(res.skill_uses, [])
        self.assertEqual(res.quality["sesiones principales omitidas por tope de tamano"], 1)
        # crecimiento a mitad de lectura (fstat engana): tampoco deja nada
        with mock.patch.object(ur, "MAX_FILE_BYTES", 2000), \
                mock.patch.object(ur.os, "fstat", ReaderHardlinksAndLimits._lying_fstat()):
            res = self.read(tree)
        self.assertEqual(res.skill_uses, [])
        self.assertEqual(res.quality["sesiones principales omitidas por tope de tamano"], 1)
        # error de E/S a mitad
        real = ur._iter_objects

        def failing(f, info):
            it = real(f, info)
            yield next(it)
            raise OSError("fallo " + us.M_CONTENT)

        with mock.patch.object(ur, "_iter_objects", failing):
            res = self.read(tree)
        self.assertEqual(res.skill_uses, [])
        self.assertEqual(res.quality["sesiones principales ilegibles"], 1)
        # conjunto de ids por archivo por encima del tope
        with mock.patch.object(ur, "MAX_IDS_PER_FILE", 5):
            res = self.read(tree)
        self.assertEqual(res.skill_uses, [])
        self.assertEqual(res.quality["sesiones principales omitidas por tope de tamano"], 1)
        self.assertEqual(res.warnings, [ur.WARN_MAIN_CAP])
        # sin fallos: las 20
        self.assertEqual(len(self.read(tree).skill_uses), 20)
        self.assert_no_markers(res.quality, res.skill_uses)

    def test_unopenable_main_session_is_counted_unreadable(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm"])])
        with mock.patch.object(ur, "_open_regular", side_effect=OSError("no se abre")):
            res = self.read(tree)
        self.assertEqual(res.skill_uses, [])
        self.assertEqual(res.quality["sesiones principales ilegibles"], 1)
        self.assertEqual(res.warnings, [ur.WARN_MAIN_UNREADABLE])

    def test_hardlinked_main_session_is_not_read_and_is_counted(self):
        tree = us.Tree(self.base)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        target = outer.main_session("c--x", "s9", [us.skill_line("a1", SK_TS % 1, ["brainstorm"])])
        self.hardlink(target, os.path.join(tree.folder(self.FOLDER), "s1.jsonl"))
        res = self.read(tree)
        self.assertEqual(res.skill_uses, [])
        self.assertEqual(res.quality["sesiones principales omitidas por enlace duro"], 1)
        self.assertEqual(res.quality["sesiones principales leidas"], 0)
        self.assertEqual(res.warnings, [ur.WARN_MAIN_HARDLINK])
        # y llegan a las metricas junto con el resto de los avisos
        self.assertEqual(agg(res).warnings, (ur.WARN_MAIN_HARDLINK,))

    def test_main_session_warnings_are_fixed_text_and_limitations_are_documented(self):
        for text in (ur.WARN_MAIN_HARDLINK, ur.WARN_MAIN_CAP, ur.WARN_MAIN_UNREADABLE) + ur.SKILL_LIMITATIONS:
            text.encode("utf-8")
            self.assertNotIn("ZZMARK", text)
        self.assertEqual(len({ur.WARN_MAIN_HARDLINK, ur.WARN_MAIN_CAP, ur.WARN_MAIN_UNREADABLE}), 3)
        # sin sesiones omitidas no hay aviso
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm"])])
        self.assertEqual(self.read(tree).warnings, [])
        # limitaciones para T5: linea corrupta (subconteo silencioso) y skills con /nombre
        self.assertIsInstance(ur.SKILL_LIMITATIONS, tuple)
        self.assertEqual(len(ur.SKILL_LIMITATIONS), 2)
        joined = " ".join(ur.SKILL_LIMITATIONS)
        for needle in ("corrupta", "esconder", "/nombre", "no se cuentan"):
            self.assertIn(needle, joined)

    def test_corrupt_line_in_a_main_session_or_subagent_hides_an_invocation_silently(self):
        # la limitacion documentada: la sesion se lee igual y la invocacion perdida no deja rastro
        tree = us.Tree(self.base)
        lines = [us.skill_line("a1", SK_TS % 1, ["brainstorm"]), "{esto no es json",
                 us.skill_line("a2", SK_TS % 3, ["brainstorm"])]
        self.main(tree, "s1", lines)
        tree.subagent(self.FOLDER, "s1", "a1", [us.assistant("m1", SK_TS % 4), "{corrupta",
                                                us.skill_line("b1", SK_TS % 5, ["brainstorm"], sidechain=True)])
        res = self.read(tree, check_damage=False)
        self.assertEqual([u.origin for u in res.skill_uses], ["sesion", "sesion", "subagente"])
        self.assertEqual(res.quality["lineas corruptas (sesion principal)"], 1)
        self.assertEqual(res.calls[0].damage, "linea intermedia corrupta")
        self.assertEqual(res.warnings, [])             # y no hay ningun aviso: subconteo silencioso

    def test_symlinked_main_session_is_not_read(self):
        tree = us.Tree(self.base)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        target = outer.main_session("c--x", "s9", [us.skill_line("a1", SK_TS % 1, ["brainstorm"])])
        if not self.make_link(target, os.path.join(tree.folder(self.FOLDER), "s1.jsonl"), is_dir=False):
            self.skipTest("el sistema no permite crear el enlace")
        res = self.read(tree)
        self.assertEqual(res.skill_uses, [])
        self.assertEqual(res.quality["enlaces omitidos"], 1)

    def test_structural_signature_applies_to_main_sessions_too(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [{"x": 1}, {"y": us.M_CONTENT}])
        with self.assertRaises(ur.SchemaError) as cm:
            self.read(tree)
        self.assertIn(ur.CHK_NO_TYPE, cm.exception.message)
        self.assert_no_markers(cm.exception.message)
        tree = us.Tree(os.path.join(self.base, "b"))
        line = us.skill_line("a1", "ayer " + us.M_CONTENT, ["brainstorm"])
        self.main(tree, "s1", [line])
        with self.assertRaises(ur.SchemaError) as cm:
            self.read(tree)
        self.assertIn(ur.CHK_TS, cm.exception.message)
        self.assert_no_markers(cm.exception.message)
        # otros tipos de linea pueden no traer hora
        tree = us.Tree(os.path.join(self.base, "c"))
        self.main(tree, "s1", [{"type": "summary", "summary": "x"}, us.skill_line("a1", SK_TS % 1, ["brainstorm"])])
        self.assertEqual(len(self.read(tree).skill_uses), 1)

    def test_window_is_decided_by_the_timestamp_of_the_tool_use_line(self):
        tree = us.Tree(self.base)
        lines = [
            us.skill_line("w1", "2026-03-01T23:59:59Z", ["brainstorm"]),          # antes de since: fuera
            us.skill_line("w2", "2026-03-02T00:00:00Z", ["brainstorm"]),          # primer instante de since: dentro
            us.skill_line("w3", "2026-03-31T23:59:59.999999Z", ["brainstorm"]),   # ultimo de until: dentro
            us.skill_line("w4", "2026-04-01T00:00:00Z", ["brainstorm"]),          # despues de until: fuera
            us.skill_line("w5", "2026-03-02T01:00:00+02:00", ["brainstorm"]),     # 23:00Z del 1: fuera
            us.skill_line("w6", "2026-03-15T12:00:00", ["review"]),               # sin zona: UTC, dentro
        ]
        self.main(tree, "s1", lines)
        res = self.read(tree)
        self.assertEqual(len(res.skill_uses), 6)
        m = agg(res)
        self.assertEqual([(r.skill, r.calls) for r in m.skills.rows], [("brainstorm", 2), ("review", 1)])
        q = m.skills.quality
        self.assertEqual((q.uses_read, q.in_window, q.outside_window), (6, 3, 3))
        m = agg(res, window=ur.make_window(TODAY, all_time=True))
        self.assertEqual((m.skills.calls, m.skills.quality.outside_window), (6, 0))

    def test_subagent_file_damage_decides_whether_its_skills_count(self):
        tree = us.Tree(self.base)
        # linea intermedia corrupta: el archivo conserva herramientas y horas, y tambien sus skills
        tree.subagent(self.FOLDER, "s1", "a1", [us.skill_line("c1", SK_TS % 1, ["brainstorm"], sidechain=True),
                                                "no es json", us.assistant("c2", SK_TS % 2)])
        # archivo omitido por tope: no deja nada
        tree.subagent(self.FOLDER, "s1", "a2", [us.skill_line("t%d" % i, SK_TS % i, ["review"], sidechain=True)
                                                for i in range(20)])
        with mock.patch.object(ur, "MAX_FILE_BYTES", 4000):
            res = self.read(tree, check_damage=False)
        by_status = {c.damage: c for c in res.calls}
        self.assertEqual(set(by_status), {"linea intermedia corrupta", "tope"})
        self.assertEqual([(u.skill, u.agent) for u in res.skill_uses], [("brainstorm", "forge")])

    def test_two_names_of_one_inode_count_the_skills_once(self):
        tree = us.Tree(self.base)
        first = tree.subagent(self.FOLDER, "s1", "a1", [us.skill_line("h1", SK_TS % 1, ["brainstorm"], sidechain=True)])
        sub2 = os.path.join(tree.folder(self.FOLDER), "s2", "subagents")
        os.makedirs(sub2)
        self.hardlink(first, os.path.join(sub2, "agent-a2.jsonl"))
        res = self.read(tree)
        self.assertEqual(len(res.calls), 1)
        self.assertEqual(len(res.skill_uses), 1)
        self.assertEqual(res.quality["skills: id repetido entre archivos"], 0)

    def test_hardlinked_subagent_transcript_is_read_and_its_skills_count(self):
        tree = us.Tree(self.base)
        outer = us.Tree(os.path.join(self.base, "afuera"))
        target = outer.subagent("c--x", "s9", "a9", [us.skill_line("h1", SK_TS % 1, ["brainstorm"], sidechain=True)],
                                meta=None)
        sub = os.path.join(tree.folder(self.FOLDER), "s1", "subagents")
        os.makedirs(sub)
        self.hardlink(target, os.path.join(sub, "agent-h.jsonl"))
        res = self.read(tree)
        self.assertEqual([(u.skill, u.agent) for u in res.skill_uses], [("brainstorm", "(sin-meta)")])

    def test_global_id_set_is_capped_and_reported(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm", "review"])])
        self.main(tree, "s2", [us.skill_line("b1", SK_TS % 2, ["brainstorm"])])
        with mock.patch.object(ur, "MAX_IDS_GLOBAL", 1):
            res = self.read(tree)
        self.assertEqual(len(res.skill_uses), 3)           # no se omite nada: lo que no se recuerda se cuenta aparte
        self.assertEqual(res.quality["skills: ids sin deduplicar (tope)"], 2)
        self.assertIn(ur.WARN_SKILL_ID_CAP, res.warnings)

    def test_project_filter_and_sessions_without_subagents_dir(self):
        tree = us.Tree(self.base)
        proj = os.path.join(self.base, "my proj")
        os.makedirs(proj)
        folder = us.folder_name_for(os.path.abspath(proj))
        self.main(tree, "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm"])], folder=folder)
        self.main(tree, "s2", [us.skill_line("b1", SK_TS % 2, ["review"])], folder="c--otra")
        res = ur.read_calls(tree.claude_dir, project_dir=proj)
        self.assertEqual([u.skill for u in res.skill_uses], ["brainstorm"])
        self.assertEqual(len(ur.read_calls(tree.claude_dir).skill_uses), 2)

    def test_skill_records_are_deterministic_for_a_fixed_key_and_have_no_raw_content(self):
        tree = us.Tree(self.base)
        self.main(tree, "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm", us.M_SKILL])])
        key = b"d" * 16
        a = ur.read_calls(tree.claude_dir, digest_key=key)
        b = ur.read_calls(tree.claude_dir, digest_key=key)
        self.assertEqual(a.skill_uses, b.skill_uses)
        for u in a.skill_uses:
            self.assertRegex(u.session, r"^[0-9a-f]{16}$")
            self.assertRegex(u.project, r"^p-[0-9a-f]{8}$")
            self.assertIsInstance(u.moment, datetime.datetime)
            self.assertEqual(u.moment.utcoffset(), datetime.timedelta(0))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            a.skill_uses[0].skill = "x"

    def test_reader_does_not_read_input_args(self):
        # `args` puede ser un objeto enorme o con contenido: el lector no lo mira. Con `args` de formas
        # raras el resultado es identico.
        results = []
        for i, args in enumerate((us.M_ARGS, None, [us.M_ARGS] * 50, {"a": {"b": us.M_ARGS}}, 12345, True)):
            tree = us.Tree(os.path.join(self.base, "t%d" % i))
            self.main(tree, "s1", [us.assistant("m1", SK_TS % 1, sidechain=False,
                                                blocks=[us.skill_block("k1", "brainstorm", args=args)])])
            res = ur.read_calls(tree.claude_dir, digest_key=b"a" * 16)
            results.append(repr(res.skill_uses))
        self.assertEqual(len(set(results)), 1)


class SkillAggregation(unittest.TestCase):
    def test_rows_groups_and_agent_links_by_hand(self):
        fa = dict(agent="forge", agent_group="SyncLayer", origin="subagente")
        uses = [
            su(1), su(2), su(3, session="s2"),
            su(4, skill="review", group="integrado"),
            su(5, skill="plugin:pl", group="plugin:pl", session="s2", **fa),
            su(6, session="s1", **fa),
            su(7, agent="(otro agente)", agent_group="otros", origin="subagente"),
            su(8, skill="(otra skill)", session="s3"),
        ]
        m = ur.aggregate_calls([], today=TODAY, skill_uses=uses)
        s = m.skills
        # 8 invocaciones en 3 sesiones; principal: 1, 2, 3, 4, 8 = 5; subagentes: 5, 6, 7 = 3
        self.assertEqual((s.calls, s.sessions, s.main_calls, s.subagent_calls), (8, 3, 5, 3))
        # brainstorm: 1, 2, 3, 6, 7 = 5 (3 principal + 2 de subagentes) en s1 y s2; el resto, 1 cada una:
        # orden por llamadas descendente y luego nombre: "(otra skill)" < "plugin:pl" < "review"
        self.assertEqual([(r.skill, r.group, r.calls, r.main_calls, r.subagent_calls, r.sessions) for r in s.rows], [
            ("brainstorm", "otros", 5, 3, 2, 2),
            ("(otra skill)", "otros", 1, 1, 0, 1),
            ("plugin:pl", "plugin:pl", 1, 0, 1, 1),
            ("review", "integrado", 1, 1, 0, 1),
        ])
        # otros = brainstorm 5 + (otra skill) 1 = 6 llamadas, 2 skills, sesiones s1, s2, s3 = 3
        self.assertEqual([(g.group, g.skills, g.calls, g.sessions) for g in s.groups], [
            ("otros", 2, 6, 3), ("integrado", 1, 1, 1), ("plugin:pl", 1, 1, 1)])
        self.assertEqual([(r.agent, r.agent_group, r.skill, r.skill_group, r.calls) for r in s.by_agent], [
            ("(otro agente)", "otros", "brainstorm", "otros", 1),
            ("forge", "SyncLayer", "brainstorm", "otros", 1),
            ("forge", "SyncLayer", "plugin:pl", "plugin:pl", 1),
        ])
        q = s.quality
        self.assertEqual((q.uses_read, q.in_window, q.outside_window, q.without_time, q.other_name), (8, 8, 0, 0, 1))

    def test_window_boundaries_by_date_in_utc_and_uses_without_time(self):
        east = datetime.timezone(datetime.timedelta(hours=2))
        uses = [
            su(1, moment=dt(2, 0, 0, 0)),                                   # primer instante de since: dentro
            su(2, moment=dt(31, 23, 59, 59, 999999)),                       # ultimo de until: dentro
            su(3, moment=dt(1, 23, 59, 59, 999999)),                        # fuera
            su(4, moment=dt(1, month=4)),                                   # fuera
            su(5, moment=datetime.datetime(2026, 3, 2, 1, 0, tzinfo=east)),   # 23:00Z del 1: fuera
            su(6, moment=datetime.datetime(2026, 3, 5, 12, 0)),             # sin zona: UTC, dentro
            su(7, moment=None),                                             # sin hora: solo con --all
        ]
        m = ur.aggregate_calls([], today=TODAY, skill_uses=uses)
        q = m.skills.quality
        self.assertEqual((m.skills.calls, q.uses_read, q.in_window, q.outside_window, q.without_time), (3, 7, 3, 4, 1))
        m = ur.aggregate_calls([], window=ur.make_window(TODAY, all_time=True), skill_uses=uses)
        q = m.skills.quality
        self.assertEqual((m.skills.calls, q.in_window, q.outside_window, q.without_time), (7, 7, 0, 1))

    def test_no_skills_gives_zeros_and_calls_alone_carry_none(self):
        m = ur.aggregate_calls([mk(0)], today=TODAY)
        s = m.skills
        self.assertEqual((s.calls, s.sessions, s.main_calls, s.subagent_calls, s.rows, s.groups, s.by_agent),
                         (0, 0, 0, 0, (), (), ()))
        self.assertEqual((s.quality.uses_read, s.quality.in_window), (0, 0))

    def test_result_is_deterministic_frozen_and_without_session_identifiers(self):
        uses = [su(i, session="IDENT-SESSION-%d" % (i % 3), skill="s%d" % (i % 4),
                   moment=dt(1 + i % 28), agent="forge" if i % 2 else None,
                   agent_group="SyncLayer" if i % 2 else None, origin="subagente" if i % 2 else "sesion")
                for i in range(40)]
        base = ur.aggregate_calls([], today=TODAY, skill_uses=uses)
        rnd = random.Random(3)
        for _ in range(4):
            shuffled = list(uses)
            rnd.shuffle(shuffled)
            other = ur.aggregate_calls(iter([]), today=TODAY, skill_uses=iter(shuffled))
            self.assertEqual(other, base)
            self.assertEqual(repr(other), repr(base))
        self.assertNotIn("IDENT-SESSION", repr(base))
        self.assertNotIn("p-00000001", repr(base.skills))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            base.skills.calls = 1

    def test_read_result_skills_are_taken_automatically_and_an_explicit_list_wins(self):
        res = ur.ReadResult()
        res.skill_uses.append(su(1))
        self.assertEqual(ur.aggregate_calls(res, today=TODAY).skills.calls, 1)
        self.assertEqual(ur.aggregate_calls(res, today=TODAY, skill_uses=[su(1), su(2)]).skills.calls, 2)
        self.assertEqual(ur.aggregate_calls(res.calls, today=TODAY).skills.calls, 0)

    # LISTA BLANCA de los campos de los dataclasses Skill*: un campo nuevo (p. ej. tokens o duracion) hace
    # fallar la prueba y obliga a decidir si una skill puede llevarlo (3.6: solo conteos y distribucion).
    SKILL_FIELDS = {
        "SkillRow": ("skill", "group", "calls", "main_calls", "subagent_calls", "sessions"),
        "SkillGroupRow": ("group", "skills", "calls", "sessions"),
        "SkillAgentRow": ("agent", "agent_group", "skill", "skill_group", "calls"),
        "SkillQuality": ("uses_read", "in_window", "outside_window", "without_time", "other_name"),
        "SkillMetrics": ("calls", "sessions", "main_calls", "subagent_calls", "rows", "groups", "by_agent",
                         "quality"),
    }

    def test_comparison_across_groups_is_only_counts_and_distribution(self):
        # no hay tokens, duracion ni costo atribuido a una skill: los dataclasses solo tienen conteos
        for cls_name, expected in self.SKILL_FIELDS.items():
            cls = getattr(ur, cls_name)
            self.assertEqual(tuple(f.name for f in dataclasses.fields(cls)), expected, cls_name)
        # y no hay otro dataclass Skill* sin revisar
        found = {n for n in dir(ur) if n.startswith("Skill") and dataclasses.is_dataclass(getattr(ur, n))}
        found -= {"SkillUse"}       # la invocacion cruda (interna, no sale en ningun resultado)
        self.assertEqual(found, set(self.SKILL_FIELDS))

    def test_version_range_is_computed_once_per_call(self):
        # Minor 9: antes se calculaba ~16 veces por llamada (por rango y ambito)
        calls = [mk(i, agent="a%d" % (i % 3), agent_group="otros", project="p-0000000%d" % (i % 2),
                    versions=("2.1.300", "2.1.315")) for i in range(12)]
        real = ur.version_range
        counter = collections.Counter()

        def counting(call):
            counter[call.call_id] += 1
            return real(call)

        with mock.patch.object(ur, "version_range", counting):
            m = agg(calls)
        self.assertEqual(m.total.calls, 12)
        self.assertEqual(set(counter.values()), {1})
        self.assertEqual(len(counter), 12)
        self.assertEqual(m.total.versions[1].calls, 12)    # y el resultado no cambia


class ReaderRandomKey(ReaderBase):
    """T4 (Minor 6): call_id, session y agent_key llevan una clave aleatoria por ejecucion."""

    def _tree(self):
        tree = us.Tree(self.base)
        tree.main_session("c--p", "s1", [us.skill_line("a1", SK_TS % 1, ["brainstorm"])])
        tree.subagent("c--p", "s1", "a1", [us.assistant("m1", SK_TS % 2)])
        tree.subagent("c--p", "s1", "a2", [us.assistant("m2", SK_TS % 3)], meta={"agentType": "pl:" + us.M_TYPE})
        tree.subagent("c--p", "s1", "a3", [us.assistant("m3", SK_TS % 4)], meta=None)
        return tree

    def test_two_default_reads_give_different_identifiers_but_the_same_aliases(self):
        tree = self._tree()
        a, b = self.read(tree), self.read(tree)
        self.assertEqual(len(a.calls), 3)
        for x, y in zip(a.calls, b.calls):
            self.assertNotEqual(x.call_id, y.call_id)
            self.assertNotEqual(x.session, y.session)
            self.assertEqual(x.project, y.project)           # el alias del reporte global si es estable
            self.assertEqual((x.agent, x.agent_group, x.input_tokens), (y.agent, y.agent_group, y.input_tokens))
        self.assertNotEqual(a.calls[0].agent_key, b.calls[0].agent_key)
        self.assertNotEqual(a.skill_uses[0].session, b.skill_uses[0].session)
        # las claves por agente siguen distinguiendo agentes dentro de una ejecucion
        self.assertEqual(len({c.agent_key for c in a.calls}), 3)
        self.assertNotEqual(a._key, b._key)
        self.assertEqual(len(a._key), 16)

    def test_fixed_key_is_reproducible_and_changes_every_identifier(self):
        tree = self._tree()
        a = ur.read_calls(tree.claude_dir, digest_key=b"1" * 16)
        b = ur.read_calls(tree.claude_dir, digest_key=b"1" * 16)
        c = ur.read_calls(tree.claude_dir, digest_key=b"2" * 16)
        self.assertEqual(a.calls, b.calls)
        for x, z in zip(a.calls, c.calls):
            self.assertNotEqual((x.call_id, x.session, x.agent_key), (z.call_id, z.session, z.agent_key))
        # y no son el resumen sin clave de nada que un tercero pueda recalcular
        for x in a.calls:
            self.assertNotEqual(x.session, ur._digest("c--p\0s1").hex())
            self.assertNotEqual(x.call_id, ur._digest("c--p\0s1\0agent-a1").hex())

    def test_aggregates_and_metrics_hold_no_identifier_of_the_run(self):
        tree = self._tree()
        res = self.read(tree)
        m = ur.aggregate_calls(res, today=TODAY)
        text = repr(m) + repr(m.skills) + repr(m.agents) + repr(m.groups) + repr(m.projects)
        text += repr(m.quality) + repr(m.read_quality) + repr(m.skills.quality)
        self.assertEqual(m.total.calls, 3)
        for c in res.calls:
            for ident in (c.call_id, c.session, c.agent_key):
                self.assertNotIn(ident, text)
        for u in res.skill_uses:
            self.assertNotIn(u.session, text)
        self.assertNotIn(res._key.hex(), text)
        self.assertNotIn(repr(res._key), text)
        self.assert_no_markers(text)
        # tampoco ningun hex de 16 caracteres (el patron de los resumenes); el alias p-<8 hex> es de 8
        self.assertEqual(re.findall(r"\b[0-9a-f]{16}\b", text), [])

    def test_call_record_is_never_serialised_by_the_tool(self):
        # T5 a T7 no deben serializar un CallRecord ni un SkillUse (asdict, vars, pickle, __dict__):
        # llevan resumenes con la clave de la ejecucion. Esta prueba revisa el codigo de la herramienta.
        with open(SCRIPT, "rb") as f:
            tree = ast.parse(f.read().decode("utf-8"))
        banned = {"asdict", "astuple", "vars", "pickle", "marshal", "shelve", "__dict__", "copyreg",
                  "__reduce__", "__getstate__", "__reduce_ex__", "__getstate__", "fields", "copy", "deepcopy",
                  "getmembers", "__slots__", "__repr__", "__str__", "__format__", "__setstate__"}
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in banned:
                seen.add(node.id)
            elif isinstance(node, ast.Attribute) and node.attr in banned:
                seen.add(node.attr)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name.split(".")[0] in banned:
                        seen.add(alias.name)
        self.assertEqual(seen, set())
        # `str(call)` / `repr(call)` / `format(call)` / f-string sobre un CallRecord o un SkillUse: ninguna
        # llamada a str/repr/format/print recibe `call`, `c`, `use`, `u` ni sus campos con clave
        keyed = {"call_id", "session", "agent_key", "seq", "_key"}
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
                    "str", "repr", "format", "print", "ascii"):
                for arg in node.args:
                    for sub in ast.walk(arg):
                        if isinstance(sub, ast.Attribute) and sub.attr in keyed:
                            used.add(sub.attr)
                        if isinstance(sub, ast.Name) and sub.id in ("call", "use", "calls", "uses", "res"):
                            used.add(sub.id)
            elif isinstance(node, ast.FormattedValue):
                for sub in ast.walk(node.value):
                    if (isinstance(sub, ast.Attribute) and sub.attr in keyed) or (
                            isinstance(sub, ast.Name) and sub.id in ("call", "use", "calls", "uses")):
                        used.add("f-string")
        self.assertEqual(used, set())
        # y la autoprueba: el criterio ve un uso prohibido
        probe = ast.parse("import pickle\nx = dataclasses.asdict(c)\ny = vars(c)\nz = c.__dict__\n"
                          "w = getattr(c, '__dict__')\nv = dataclasses.fields(c)\nu = copy.copy(c)\n"
                          "t = c.__repr__()")
        found = {n.id for n in ast.walk(probe) if isinstance(n, ast.Name)} | \
                {n.attr for n in ast.walk(probe) if isinstance(n, ast.Attribute)} | \
                {n.value for n in ast.walk(probe) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertTrue(found & banned >= {"asdict", "vars", "__dict__", "fields", "copy", "__repr__"})
        for snippet in ("x = str(call)", "x = repr(u.session)", "x = format(c.call_id)", "print(call.agent_key)",
                        "x = f'{call.session}'", "x = f'{uses}'"):
            probe = ast.parse(snippet)
            hit = False
            for node in ast.walk(probe):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
                        "str", "repr", "format", "print", "ascii"):
                    hit = hit or any(
                        (isinstance(sub, ast.Attribute) and sub.attr in keyed)
                        or (isinstance(sub, ast.Name) and sub.id in ("call", "use", "calls", "uses", "res"))
                        for arg in node.args for sub in ast.walk(arg))
                elif isinstance(node, ast.FormattedValue):
                    hit = hit or any(
                        (isinstance(sub, ast.Attribute) and sub.attr in keyed)
                        or (isinstance(sub, ast.Name) and sub.id in ("call", "use", "calls", "uses"))
                        for sub in ast.walk(node.value))
            self.assertTrue(hit, snippet)
        # los identificadores con clave tienen repr=False (marcadores en los campos de la llamada)
        for cls, names in ((ur.CallRecord, ("call_id", "session", "agent_key", "seq")), (ur.SkillUse, ("session",))):
            by_name = {f.name: f for f in dataclasses.fields(cls)}
            for name in names:
                self.assertFalse(by_name[name].repr, "%s.%s" % (cls.__name__, name))
        call = mk(1, call_id="MARK-CALL-ID", session="MARK-SESSION", agent_key="MARK-AGENT-KEY", seq=987654)
        use = su(1, session="MARK-USE-SESSION")
        for text in (repr(call), str(call), repr(use), str(use)):
            for marker in ("MARK-CALL-ID", "MARK-SESSION", "MARK-AGENT-KEY", "987654", "MARK-USE-SESSION"):
                self.assertNotIn(marker, text)
        self.assertIn("agent='forge'", repr(call))      # y el resto de los campos si salen


class ReaderDeterminism(ReaderBase):
    """T4 (auditor, Important): mismos argumentos y mismos datos dan las mismas metricas aunque la clave
    aleatoria de cada lectura cambie. Ningun orden ni desempate puede depender de call_id, session o
    agent_key (llevan la clave): el desempate es el ordinal de recorrido `seq`."""

    ALL = ur.make_window(TODAY, all_time=True)

    def _tie_tree(self, base=None):
        # A (forge) y B (scout) empiezan y terminan a la vez; C (forge) viene despues, en la misma sesion
        tree = us.Tree(base or self.base)
        tree.subagent("c--p", "s1", "a1", [us.assistant("ma", T0 + "1Z")], meta={"agentType": "forge"})
        tree.subagent("c--p", "s1", "a2", [us.assistant("mb", T0 + "1Z")], meta={"agentType": "scout"})
        tree.subagent("c--p", "s1", "a3", [us.assistant("mc", T0 + "5Z")], meta={"agentType": "forge"})
        return tree

    def _metrics(self, tree):
        res = self.read(tree, check_damage=False)       # sin digest_key: clave aleatoria nueva
        return ur.aggregate_calls(res, window=self.ALL, check_damage=False)

    def test_ties_on_start_and_end_give_the_same_metrics_in_every_read(self):
        tree = self._tie_tree()
        first = self._metrics(tree)
        for _ in range(20):
            again = self._metrics(tree)
            self.assertEqual(again, first)
            self.assertEqual(repr(again), repr(first))
        # el orden de recorrido (a1, a2, a3) manda: B (scout) queda entre A y C, asi que C no repite
        self.assertEqual(first.total.repeats, 0)

    def test_ties_give_the_same_metrics_when_the_tied_pair_is_the_same_agent(self):
        tree = us.Tree(self.base)
        for i, agent in enumerate(("forge", "forge", "scout", "forge", "scout")):
            ts = T0 + ("1Z" if i < 3 else "5Z")
            tree.subagent("c--p", "s1", "a%d" % i, [us.assistant("m%d" % i, ts)], meta={"agentType": agent})
        first = self._metrics(tree)
        for _ in range(20):
            self.assertEqual(self._metrics(tree), first)

    def test_metrics_do_not_depend_on_the_random_key_over_the_rich_tree(self):
        tree = rich_tree(self.base)
        self._tie_tree()
        us.Tree(self.base).subagent("c--q", "s7", "b1", [us.assistant("n1", T0 + "2Z")], meta={"agentType": "plugin:x"})
        first = self._metrics(tree)
        self.assertGreater(first.total.calls, 5)
        seen_keys = set()
        for _ in range(8):
            res = self.read(tree, check_damage=False)
            seen_keys.add(res._key)
            m = ur.aggregate_calls(res, window=self.ALL, check_damage=False)
            self.assertEqual(m, first)
            self.assertEqual(repr(m), repr(first))
        self.assertGreater(len(seen_keys), 1)            # las claves SI cambiaron entre lecturas

    def test_seq_is_the_traversal_ordinal_and_stays_out_of_repr(self):
        tree = self._tie_tree()
        res = self.read(tree)
        self.assertEqual([c.seq for c in res.calls], [0, 1, 2])
        self.assertNotIn("seq", repr(res.calls[0]))
        # y no cambia con la clave
        again = self.read(tree)
        self.assertEqual([c.seq for c in again.calls], [0, 1, 2])

    def test_call_record_and_skill_use_repr_hold_no_run_identifier(self):
        tree = self._tie_tree()
        tree.main_session("c--p", "s1", [us.skill_line("k1", SK_TS % 1, ["brainstorm"])])
        res = self.read(tree)
        for c in res.calls:
            text = repr(c) + str(c)
            for ident in (c.call_id, c.session, c.agent_key):
                self.assertNotIn(ident, text)
            for name in ("call_id", "session", "agent_key", "seq"):
                self.assertNotIn(name + "=", text)
        self.assertEqual(len(res.skill_uses), 1)
        for u in res.skill_uses:
            text = repr(u) + str(u)
            self.assertNotIn(u.session, text)
            self.assertNotIn("session=", text)


class AgentKeyAndSentinel(ReaderBase):
    def test_agent_key_uses_the_canonical_name_empty_is_the_default_agent(self):
        tree = us.Tree(self.base)
        for i, raw in enumerate(("", "general-purpose", "forge", "")):
            tree.subagent("c--p", "s1", "a%d" % i, [us.assistant("m%d" % i, T0 + "%dZ" % i)], meta={"agentType": raw})
        res = self.read(tree)
        keys = [c.agent_key for c in res.calls]
        self.assertEqual(keys[0], keys[1])        # "" y general-purpose son el mismo agente
        self.assertEqual(keys[0], keys[3])
        self.assertNotEqual(keys[0], keys[2])
        self.assertEqual(keys[0], ur._digest(ur.DEFAULT_AGENT, res._key).hex())
        self.assertEqual([c.agent for c in res.calls][:2], ["general-purpose", "general-purpose"])
        # y el conteo de agentes de un conjunto los junta
        m = ur.aggregate_calls(res, window=ur.make_window(TODAY, all_time=True))
        self.assertEqual({g.group: g.agents for g in m.groups}, {"integrado": 1, "SyncLayer": 1})
        # las repeticiones: "" despues de general-purpose es el mismo agente
        repeats = ur.repeat_flags([mk(0, agent="general-purpose", agent_group="integrado", agent_key=keys[0],
                                      **span(1)),
                                   mk(1, agent="general-purpose", agent_group="integrado", agent_key=keys[1],
                                      start=dt(10, 10, 0, 5), end=dt(10, 10, 0, 6))])
        self.assertEqual(repeats, frozenset(["c001"]))

    def test_no_meta_sentinel_is_outside_the_digest_space(self):
        # la constante anterior era un blake2b de 8 bytes: un agentType fabricado la reproducia y una
        # llamada con meta se tomaba por una sin meta. Ahora no es un digest hexadecimal.
        self.assertNotRegex(ur.NO_META_KEY, r"^[0-9a-f]{16}$")
        self.assertEqual(ur.NO_META_KEY, "<sin-meta>")
        tree = us.Tree(self.base)
        crafted = "\0sin-meta"
        for i in range(2):
            tree.subagent("c--p", "s1", "a%d" % i, [us.assistant("m%d" % i, T0 + "%dZ" % (i * 3)),
                                                    us.assistant("n%d" % i, T0 + "%dZ" % (i * 3 + 1))],
                          meta={"agentType": crafted})
        tree.subagent("c--p", "s1", "z", [us.assistant("mz", T0 + "9Z")], meta=None)
        res = self.read(tree)
        crafted_calls = [c for c in res.calls if c.has_meta]
        self.assertEqual(len(crafted_calls), 2)
        for c in res.calls:
            if c.has_meta:
                self.assertRegex(c.agent_key, r"^[0-9a-f]{16}$")
                self.assertNotEqual(c.agent_key, ur.NO_META_KEY)
            else:
                self.assertEqual(c.agent_key, ur.NO_META_KEY)
        # el agente fabricado participa como cualquier otro: su segunda llamada es una repeticion
        self.assertEqual(ur.repeat_flags(crafted_calls), frozenset([crafted_calls[1].call_id]))


class MakeWindowTypes(unittest.TestCase):
    def test_wrong_types_give_a_clear_value_error_never_a_type_error(self):
        d = datetime.date
        bad_values = (datetime.datetime(2026, 3, 31, 12, 0), datetime.datetime(2026, 3, 31, tzinfo=UTC),
                      "2026-03-31", 20260331, 1.5, True, [d(2026, 3, 31)], b"2026-03-31")
        for bad in bad_values:
            with self.subTest(today=bad):
                with self.assertRaises(ValueError) as cm:
                    ur.make_window(bad)
                self.assertEqual(str(cm.exception), ur.MSG_WINDOW_TYPES)
            with self.subTest(since=bad):
                with self.assertRaises(ValueError) as cm:
                    ur.make_window(TODAY, since=bad)
                self.assertEqual(str(cm.exception), ur.MSG_WINDOW_TYPES)
            with self.subTest(until=bad):
                with self.assertRaises(ValueError) as cm:
                    ur.make_window(TODAY, until=bad)
                self.assertEqual(str(cm.exception), ur.MSG_WINDOW_TYPES)
        # `today` ausente solo falla si hace falta; con since y until explicitos no se usa
        with self.assertRaises(ValueError) as cm:
            ur.make_window(None)
        self.assertEqual(str(cm.exception), ur.MSG_WINDOW_TYPES)
        w = ur.make_window(None, since=d(2026, 3, 1), until=d(2026, 3, 2))
        self.assertEqual((w.since, w.until), (d(2026, 3, 1), d(2026, 3, 2)))
        # un `today` malo no importa con all_time; la mezcla con fechas se rechaza igual
        self.assertTrue(ur.make_window("x", all_time=True).is_all)
        with self.assertRaises(ValueError):
            ur.make_window(TODAY, all_time=True, since=datetime.datetime(2026, 3, 1))
        # `days` debe ser un entero positivo
        for days in (0, -3, "30", 2.5, None, True):
            with self.subTest(days=days):
                with self.assertRaises(ValueError):
                    ur.make_window(TODAY, days=days)
        self.assertEqual(ur.make_window(TODAY, days=1).since, TODAY)
        # una ventana valida no cambia
        self.assertEqual(ur.make_window(TODAY).since, d(2026, 3, 2))
        self.assertEqual(ur.make_window(TODAY, since=d(2026, 3, 10)).until, TODAY)
        with self.assertRaises(ValueError):
            ur.make_window(TODAY, since=d(2026, 3, 10), until=d(2026, 3, 9))


# --- T5: reporte de proyecto (texto Markdown, funcion pura) ---
ALIAS = "p-0a1b2c3d"
BAR_FULL = "\u2588"
BAR_EMPTY = "\u2591"
ACCENTED = "\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00c1\u00c9\u00cd\u00d3\u00da\u00d1\u00fc"


def render(source, uses=None, alias=ALIAS, **kw):
    """Agrega `source` (llamadas) y genera el reporte de proyecto."""
    if isinstance(source, ur.UsageMetrics):
        metrics = source
    else:
        metrics = agg(source, skill_uses=uses) if uses is not None else agg(source)
    return ur.render_project_report(metrics, alias, **kw)


def md_tables(text):
    """Bloques de lineas consecutivas que empiezan por '|' (tablas Markdown)."""
    blocks, cur = [], []
    for line in text.split("\n"):
        if line.startswith("|"):
            cur.append(line)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def columns(line):
    """Numero de celdas de una fila (los `\\|` escapados no separan)."""
    return len(re.split(r"(?<!\\)\|", line)) - 2


def cells_of(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]


def table_with(text, header_start):
    for block in md_tables(text):
        if block[0].startswith(header_start):
            return block
    raise AssertionError("tabla no encontrada: " + header_start)


def sample_calls():
    """Cinco llamadas: forge x2 (sesiones s1, s2), scout, un agente de plugin y otro de usuario."""
    return [
        mk(1, session="s1", input_tokens=100, output_tokens=50, cache_creation_tokens=20,
           cache_read_tokens=30, tools=3, **span(60)),
        mk(2, session="s2", input_tokens=10, output_tokens=5, cache_creation_tokens=2,
           cache_read_tokens=3, tools=1, **span(20)),
        mk(3, session="s1", agent="scout", agent_group="SyncLayer", versions=("2.1.315",), tools=0,
           **span(5, hour=11)),
        mk(4, session="s1", agent="plugin:pl", agent_group="plugin:pl", versions=("2.1.300",),
           **span(8, hour=12)),
        mk(5, session="s3", agent="(otro agente)", agent_group="otros", versions=("2.1.340",),
           **span(9, hour=13)),
    ]


class ReportBars(unittest.TestCase):
    def test_bar_is_ten_chars_proportional_to_the_max_with_a_one_block_floor(self):
        bar = ur._bar
        self.assertEqual(bar(100, 100), BAR_FULL * 10)
        self.assertEqual(bar(0, 100), BAR_EMPTY * 10)
        self.assertEqual(bar(1, 1000), BAR_FULL + BAR_EMPTY * 9)     # distinto de cero: minimo un bloque
        self.assertEqual(bar(50, 100), BAR_FULL * 5 + BAR_EMPTY * 5)
        # redondeo al mas cercano, medio hacia arriba: 14 de 100 = 1,4 -> 1; 15 = 1,5 -> 2; 16 -> 2
        self.assertEqual(bar(14, 100).count(BAR_FULL), 1)
        self.assertEqual(bar(15, 100).count(BAR_FULL), 2)
        self.assertEqual(bar(16, 100).count(BAR_FULL), 2)
        self.assertEqual(bar(94, 100).count(BAR_FULL), 9)
        self.assertEqual(bar(95, 100).count(BAR_FULL), 10)
        for v in range(0, 101):
            self.assertEqual(len(bar(v, 100)), 10)
        # maximo cero o ausente: barra vacia, sin dividir entre cero
        self.assertEqual(bar(0, 0), BAR_EMPTY * 10)
        self.assertEqual(bar(5, 0), BAR_EMPTY * 10)
        self.assertEqual(bar(None, 10), BAR_EMPTY * 10)
        # un valor mayor que el maximo no se sale de la barra
        self.assertEqual(bar(500, 100), BAR_FULL * 10)
        # enormes: sin perdida de precision
        big = 10 ** 18
        self.assertEqual(bar(big, big), BAR_FULL * 10)
        self.assertEqual(bar(big // 2, big), BAR_FULL * 5 + BAR_EMPTY * 5)


class ReportNumberFormats(unittest.TestCase):
    def test_numbers_are_plain_integers_and_none_is_a_dash(self):
        self.assertEqual(ur._num(0), "0")
        self.assertEqual(ur._num(1234567), "1234567")       # sin separador de miles (3.6 del plan)
        self.assertEqual(ur._num(10 ** 18), "1000000000000000000")
        self.assertEqual(ur._num(None), "-")

    def test_percent_rounds_half_up_and_flags_less_than_one(self):
        pct = ur._percent
        self.assertEqual(pct(1, 2), "50 %")
        self.assertEqual(pct(1, 3), "33 %")        # 33,33
        self.assertEqual(pct(2, 3), "67 %")        # 66,67
        self.assertEqual(pct(1, 8), "13 %")        # 12,5 -> medio hacia arriba
        self.assertEqual(pct(5, 1000), "1 %")      # 0,5 -> 1
        self.assertEqual(pct(4, 1000), "<1 %")     # 0,4 no es cero pero redondea a 0
        self.assertEqual(pct(0, 10), "0 %")
        self.assertEqual(pct(10, 10), "100 %")
        self.assertEqual(pct(0, 0), "-")           # sin base no hay porcentaje

    def test_tenths_use_a_dot(self):
        self.assertEqual(ur._tenths(15), "1.5")
        self.assertEqual(ur._tenths(20), "2.0")
        self.assertEqual(ur._tenths(5), "0.5")
        self.assertEqual(ur._tenths(1234), "123.4")
        self.assertEqual(ur._tenths(None), "-")


class ReportEscaping(unittest.TestCase):
    def test_code_cell_never_breaks_a_table(self):
        code = ur._code
        self.assertEqual(code("forge"), "`forge`")
        self.assertEqual(code("a|b"), "`a\\|b`")
        self.assertEqual(code("a`b"), "`a'b`")
        self.assertEqual(code("a\nb\rc\td"), "`a?b?c?d`")
        self.assertEqual(code("a\\b"), "`a/b`")
        self.assertEqual(code("\u00e9\u2588"), "`??`")          # fuera de ASCII imprimible
        self.assertEqual(code(""), "`(vacio)`")
        self.assertEqual(code(None), "`(no cadena)`")
        self.assertEqual(code(123), "`(no cadena)`")
        long = code("x" * 500)
        self.assertEqual(len(long), ur.MAX_CELL_CHARS + 2)
        self.assertTrue(long.endswith("...`"))

    def test_hostile_names_keep_the_columns(self):
        calls = [mk(1, agent="a|b\nc`d\\e" + "x" * 100, agent_group="otros|x", model="m|\nn",
                    models=("m|\nn",)),
                 mk(2, agent="(otro agente)", agent_group="plugin:p|q")]
        text = render(calls)
        for block in md_tables(text):
            self.assertEqual(len({columns(line) for line in block}), 1, block[0])
        self.assertNotIn("\r", text)
        self.assertNotIn("a|b", text)


class ReportShape(unittest.TestCase):
    def setUp(self):
        self.text = render(sample_calls(), generated=datetime.date(2026, 4, 1))

    def test_bytes_are_lf_ascii_plus_bars_and_end_with_one_newline(self):
        text = self.text
        self.assertTrue(text.startswith("<!-- synclayer-usage-report v1 -->\n"))
        self.assertEqual(ur.REPORT_MARKER, "<!-- synclayer-usage-report v1 -->")
        self.assertNotIn("\r", text)
        self.assertFalse(text.startswith("\ufeff"))
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))
        self.assertNotIn("\n\n\n", text)
        # el reporte lleva tildes y eñes (decision del propietario): ASCII, las barras y esas letras
        allowed = {BAR_FULL, BAR_EMPTY} | set(ACCENTED)
        for ch in text:
            self.assertTrue(ch in allowed or ch == "\n" or " " <= ch <= "~", repr(ch))
        self.assertTrue(any(ch in ACCENTED for ch in text))
        raw = text.encode("utf-8")
        self.assertEqual(raw.decode("utf-8"), text)
        self.assertNotIn(b"\r", raw)
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))

    def test_sections_in_order_with_the_planned_titles(self):
        titles = [line for line in self.text.split("\n") if line.startswith("#")]
        self.assertEqual(titles[:11], [
            "# Reporte de uso de subagentes: proyecto " + ALIAS,
            "## Resumen",
            "## Llamadas por agente",
            "## Tokens por llamada",
            "## Duración y herramientas",
            "## Modelo real",
            "## Por conjunto",
            "## Skills",
            "## Versiones de Claude Code",
            "## Calidad de los datos",
            "## Cómo leer estos números",
        ])
        self.assertEqual(titles[-1], "## Pie")

    def test_table_headers_match_the_plan(self):
        heads = [block[0] for block in md_tables(self.text)]
        self.assertIn("| Agente | Conjunto | Llamadas | Barra | Sesiones | Llamadas/sesión | Repeticiones (inferido) |",
                      heads)
        self.assertIn("| Agente | Conjunto | n | Tokens (suma) | Barra | Mediana | p90 | Entrada (med.) |"
                      " Salida (med.) | Caché escrita (med.) | Caché leída (med.) | Peticiones (med.) |", heads)
        self.assertIn("| Agente | Conjunto | Duración aprox. s (med.) | p90 | Herramientas (med.) | p90 |", heads)
        self.assertIn("| Agente | Conjunto | Modelo | Llamadas |", heads)
        self.assertIn("| Conjunto | Agentes | Llamadas | Barra | Tokens/llamada (med.) | p90 |"
                      " Duración aprox. s (med.) | Herramientas (med.) |", heads)
        self.assertIn("| Rango | Llamadas | Tokens/llamada (med.) | p90 | Nota |", heads)
        self.assertIn("| Versión | Llamadas | Nota |", heads)

    def test_every_table_has_the_same_column_count_in_all_rows_and_a_separator(self):
        blocks = md_tables(self.text)
        self.assertGreaterEqual(len(blocks), 8)
        for block in blocks:
            self.assertGreaterEqual(len(block), 3, block[0])     # cabecera, separador y una fila
            self.assertRegex(block[1], r"^\|(---:?\|)+$")
            self.assertEqual(len({columns(line) for line in block}), 1, block[0])

    def test_header_has_window_alias_schema_and_the_injected_date_only(self):
        head = self.text.split("## Resumen")[0]
        self.assertIn("2026-03-02 a 2026-03-31 (UTC, ambos inclusive)", head)
        self.assertIn(ALIAS, head)
        self.assertIn("Esquema del reporte: 1", head)
        self.assertIn("Generado: 2026-04-01", head)
        self.assertIn("no lo subas a git", head)
        # sin fecha inyectada no hay linea de fecha, y el reporte no lee el reloj
        self.assertNotIn("Generado", render(sample_calls()))
        self.assertIn("Generado: 2030-01-02", render(sample_calls(), generated=datetime.date(2030, 1, 2)))

    def test_header_data_are_one_bullet_per_line_so_gfm_does_not_merge_them(self):
        # varias lineas `> texto` seguidas forman UN parrafo en GFM: cada dato va en su propia linea `> - `
        head = self.text.split("## Resumen")[0].split("\n")
        quoted = [line for line in head if line.startswith(">")]
        self.assertGreaterEqual(len(quoted), 6)
        for line in quoted:
            self.assertTrue(line.startswith("> - "), line)
        self.assertIn("> - Ventana: 2026-03-02 a 2026-03-31 (UTC, ambos inclusive)", head)
        self.assertIn("> - Llamadas: 5 en 3 sesiones", head)
        self.assertIn("> - Generado: 2026-04-01", head)
        self.assertIn("> - Reporte local: no lo subas a git.", head)
        self.assertTrue(any(line.startswith("> - AVISO: ") for line in head))
        # el bloque de cita no se interrumpe y el titulo va antes, con una linea en blanco
        first = head.index(quoted[0])
        self.assertEqual(head[first - 1], "")
        self.assertEqual(head[first:first + len(quoted)], quoted)

    def test_all_time_window_is_named(self):
        text = render(agg(sample_calls(), window=ur.make_window(TODAY, all_time=True)))
        self.assertIn("todo el historial", text.split("## Resumen")[0])

    def test_footer_has_schema_tool_verified_max_alias_and_privacy_warnings(self):
        foot = self.text.split("## Pie")[1]
        self.assertIn("- report_schema: 1", foot)
        self.assertIn("- herramienta: tools/usage_report.py", foot)
        self.assertIn("- ultima_version_verificada: `" + ur.VERIFIED_MAX + "`", foot)
        self.assertIn("- proyecto: " + ALIAS, foot)
        self.assertIn("no contiene contenido de conversaciones ni rutas, pero revela volumen de uso", foot)
        self.assertIn("hash sin sal", foot)
        self.assertIn("No es anonimato", foot)
        self.assertIn("quien conozca o adivine el nombre de la carpeta puede recalcularlo", foot)
        self.assertNotIn("quien conozca la ruta", foot)
        self.assertIn("mismo nombre que uno de SyncLayer cuenta como SyncLayer", foot)

    def test_footer_warns_that_the_skill_prefix_is_model_written_and_that_models_use_a_wide_pattern(self):
        foot = self.text.split("## Pie")[1]
        self.assertIn("sale de texto que escribe el modelo: puede ser cualquier cadena `[a-z0-9-]{1,32}`", foot)
        self.assertIn("patrón amplio", foot)
        self.assertNotIn("nombres de plugins privados", self.text)


class ReportDeterminism(unittest.TestCase):
    def test_same_input_same_bytes_in_any_order(self):
        calls = sample_calls()
        day = datetime.date(2026, 4, 1)
        base = render(calls, generated=day).encode("utf-8")
        rnd = random.Random(5)
        for _ in range(5):
            shuffled = list(calls)
            rnd.shuffle(shuffled)
            self.assertEqual(render(shuffled, generated=day).encode("utf-8"), base)
        self.assertEqual(render(calls, generated=day).encode("utf-8"), base)

    def test_does_not_read_the_clock(self):
        class Boom(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                raise AssertionError("el generador leyo el reloj")

            @classmethod
            def utcnow(cls):
                raise AssertionError("el generador leyo el reloj")

        metrics = agg(sample_calls())
        with mock.patch.object(datetime, "datetime", Boom), \
                mock.patch("time.time", side_effect=AssertionError("reloj")):
            ur.render_project_report(metrics, ALIAS)

    def test_does_no_io(self):
        metrics = agg(sample_calls())

        def boom(*a, **k):
            raise AssertionError("E/S en el generador")

        with mock.patch("builtins.open", boom), mock.patch.object(os, "stat", boom), \
                mock.patch.object(os, "lstat", boom), mock.patch.object(os, "scandir", boom), \
                mock.patch.object(os, "listdir", boom), mock.patch.object(os, "open", boom), \
                mock.patch.object(os, "fstat", boom), mock.patch("sys.stdout", new=None), \
                mock.patch("sys.stderr", new=None):
            ur.render_project_report(metrics, ALIAS)

    def test_input_metrics_are_not_modified(self):
        metrics = agg(sample_calls())
        before = repr(metrics)
        ur.render_project_report(metrics, ALIAS)
        self.assertEqual(repr(metrics), before)


class ReportArguments(unittest.TestCase):
    def test_alias_must_be_p_plus_eight_lowercase_hex(self):
        metrics = agg(sample_calls())
        for bad in ("", "p-123", "p-0A1B2C3D", "p-0a1b2c3d4", "c--Users-me-proj", "p-0a1b2c3g", None, 5,
                    "p-0a1b2c3d\n", "../p-0a1b2c3d", "C:\\proj", " p-0a1b2c3d"):
            with self.subTest(alias=bad):
                with self.assertRaises(ValueError):
                    ur.render_project_report(metrics, bad)
        ur.render_project_report(metrics, "p-00000000")

    def test_generated_must_be_a_date_or_none(self):
        metrics = agg(sample_calls())
        for bad in (datetime.datetime(2026, 4, 1, 12), "2026-04-01", 20260401, True):
            with self.subTest(generated=bad):
                with self.assertRaises(ValueError):
                    ur.render_project_report(metrics, ALIAS, generated=bad)
        ur.render_project_report(metrics, ALIAS, generated=None)

    def test_metrics_must_be_usage_metrics(self):
        for bad in (None, [], "texto", agg(sample_calls()).total):
            with self.subTest(kind=type(bad).__name__):
                with self.assertRaises(ValueError):
                    ur.render_project_report(bad, ALIAS)

    def test_error_messages_do_not_echo_the_value(self):
        with self.assertRaises(ValueError) as cm:
            ur.render_project_report(agg(sample_calls()), "ZZMARK-alias-secreto")
        self.assertNotIn("ZZMARK", str(cm.exception))


class ReportAgentTables(unittest.TestCase):
    def setUp(self):
        self.text = render(sample_calls())

    def row(self, header_start, first_cell):
        for line in table_with(self.text, header_start)[2:]:
            if line.startswith("| " + first_cell + " |"):
                return cells_of(line)
        raise AssertionError((header_start, first_cell))

    def test_calls_table_values_by_hand(self):
        # forge: 2 llamadas en 2 sesiones (s1, s2) -> 1.0 por sesion; max de llamadas = 2 -> barra llena
        cells = self.row("| Agente | Conjunto | Llamadas", "`forge`")
        self.assertEqual(cells[:3], ["`forge`", "`SyncLayer`", "2"])
        self.assertEqual(cells[3], BAR_FULL * 10)
        self.assertEqual(cells[4:6], ["2", "1.0"])
        # scout: 1 llamada -> 1 de 2 = media barra; 1 sesion
        cells = self.row("| Agente | Conjunto | Llamadas", "`scout`")
        self.assertEqual(cells[2:6], ["1", BAR_FULL * 5 + BAR_EMPTY * 5, "1", "1.0"])
        # el orden es el de las metricas: llamadas descendente, luego nombre
        names = [cells_of(line)[0] for line in md_tables(self.text)[0][2:]]
        self.assertEqual(names, ["`forge`", "`(otro agente)`", "`plugin:pl`", "`scout`"])

    def test_tokens_table_values_by_hand(self):
        # forge: llamada 1 = 100+50+20+30 = 200 tokens, llamada 2 = 10+5+2+3 = 20. suma 220; n = 2 (< 10: *)
        # mediana (20+200+1)//2 = 110; p90 posicion 2 = 200; entrada [10, 100] -> (10+100+1)//2 = 55
        cells = self.row("| Agente | Conjunto | n | Tokens", "`forge`")
        self.assertEqual(cells[:4], ["`forge`", "`SyncLayer`", "2 *", "220"])
        self.assertEqual(cells[5:7], ["110 *", "200 *"])
        self.assertEqual(cells[7], "55")           # entrada (med.)
        self.assertEqual(cells[8], "28")           # salida [5, 50] -> (5+50+1)//2 = 28
        self.assertEqual(cells[9], "11")           # cache escrita [2, 20] -> (2+20+1)//2 = 11
        self.assertEqual(cells[10], "17")          # cache leida [3, 30] -> (3+30+1)//2 = 17
        self.assertEqual(cells[11], "1")           # peticiones [1, 1] -> 1
        # la barra de tokens es proporcional al maximo de la columna (forge 220; scout 20 = 9 %: 1 bloque)
        self.assertEqual(cells[4], BAR_FULL * 10)
        cells = self.row("| Agente | Conjunto | n | Tokens", "`scout`")
        self.assertEqual(cells[2:4], ["1 *", "20"])
        self.assertEqual(cells[4], BAR_FULL + BAR_EMPTY * 9)

    def test_duration_and_tools_by_hand(self):
        # forge: duraciones [60, 20] -> (20+60+1)//2 = 40, p90 60; herramientas [3, 1] -> 2, p90 3
        cells = self.row("| Agente | Conjunto | Duración", "`forge`")
        self.assertEqual(cells[:2], ["`forge`", "`SyncLayer`"])
        self.assertEqual(cells[2:6], ["40 *", "60 *", "2 *", "3 *"])
        cells = self.row("| Agente | Conjunto | Duración", "`scout`")
        self.assertEqual(cells[2:6], ["5 *", "5 *", "0 *", "0 *"])

    def test_model_table_one_row_per_agent_and_model(self):
        calls = [mk(1, model="claude-opus-4-1"), mk(2, model="claude-sonnet-4-5", models=("claude-sonnet-4-5",)),
                 mk(3, model="mixto", models=("claude-opus-4-1", "claude-sonnet-4-5"))]
        block = table_with(render(calls), "| Agente | Conjunto | Modelo")
        self.assertEqual(block[2:], [
            "| `forge` | `SyncLayer` | `claude-opus-4-1` | 1 |",
            "| `forge` | `SyncLayer` | `claude-sonnet-4-5` | 1 |",
            "| `forge` | `SyncLayer` | `mixto` | 1 |",
        ])

    def test_small_marker_only_when_n_is_under_ten(self):
        calls = [mk(i, session="s%d" % i) for i in range(10)]
        text = render(calls)
        block = table_with(text, "| Agente | Conjunto | n |")
        self.assertIn("| `forge` | `SyncLayer` | 10 | 200 |", block[2])
        self.assertNotIn("*", block[2])
        # n = 10 en todas partes: ninguna tabla lleva `*` ni leyenda (la guia final si nombra la marca)
        self.assertNotIn("pocas muestras", text.split("## Cómo leer")[0])
        text = render(calls[:9])
        block = table_with(text, "| Agente | Conjunto | n |")
        self.assertIn("| `forge` | `SyncLayer` | 9 * | 180 |", block[2])
        self.assertIn("pocas muestras", text.split("## Tokens por llamada")[1].split("## Duración")[0])

    def test_none_medians_are_a_dash_and_real_zero_is_zero(self):
        # sin usage: n = 0, medianas None; la duracion y las herramientas si existen
        text = render([no_usage(1, tools=0)])
        self.assertEqual(cells_of(table_with(text, "| Agente | Conjunto | n |")[2]),
                         ["`forge`", "`SyncLayer`", "0", "0", BAR_EMPTY * 10, "-", "-", "-", "-", "-", "-", "-"])
        self.assertEqual(cells_of(table_with(text, "| Agente | Conjunto | Duración")[2]),
                         ["`forge`", "`SyncLayer`", "10 *", "10 *", "0 *", "0 *"])
        # tokens cero reales (usable con 0 tokens): "0", no "-"
        text = render([mk(1, input_tokens=0, output_tokens=0, cache_creation_tokens=0, cache_read_tokens=0)])
        self.assertEqual(cells_of(table_with(text, "| Agente | Conjunto | n |")[2])[:7],
                         ["`forge`", "`SyncLayer`", "1 *", "0", BAR_EMPTY * 10, "0 *", "0 *"])

    def test_huge_token_values_print_in_full(self):
        big = 10 ** 15
        text = render([mk(1, input_tokens=3 * big, output_tokens=0, cache_creation_tokens=0,
                          cache_read_tokens=0)])
        self.assertIn("| 1 * | 3000000000000000 |", table_with(text, "| Agente | Conjunto | n |")[2])
        self.assertIn("3000000000000000 *", table_with(text, "| Agente | Conjunto | n |")[2])
        self.assertIn("Tokens (suma de las llamadas con estadísticas): 3000000000000000", text)

    def test_repeats_column_counts_inferred_repetitions(self):
        calls = [mk(1, **span(10)), mk(2, **span(10, hour=11))]      # la segunda repite a la primera
        self.assertEqual(cells_of(table_with(render(calls), "| Agente | Conjunto | Llamadas")[2])[-1], "1")

    def test_single_agent_report_is_well_formed(self):
        text = render([mk(1)])
        self.assertEqual(len(md_tables(text)[0]), 3)
        self.assertIn("Llamadas: 1 en 1 sesión", text.split("## Llamadas por agente")[0])

    def test_group_table(self):
        block = table_with(self.text, "| Conjunto | Agentes")
        # SyncLayer: forge, scout (2 agentes, 3 llamadas); luego los de 1 llamada por nombre
        self.assertEqual(cells_of(block[2])[:4], ["`SyncLayer`", "2", "3", BAR_FULL * 10])
        self.assertEqual([cells_of(line)[0] for line in block[2:]], ["`SyncLayer`", "`otros`", "`plugin:pl`"])

    def test_row_cap_adds_a_note(self):
        calls = [mk(i, agent="plugin:p%d" % i, agent_group="plugin:p%d" % i, session="s%d" % i)
                 for i in range(ur.MAX_TABLE_ROWS + 5)]
        text = render(calls)
        self.assertEqual(len(md_tables(text)[0]) - 2, ur.MAX_TABLE_ROWS)
        self.assertIn("Se muestran las %d primeras filas de %d" % (ur.MAX_TABLE_ROWS, ur.MAX_TABLE_ROWS + 5), text)

    def test_every_per_agent_table_and_the_group_table_are_capped_with_a_note(self):
        # un agente y un conjunto por llamada: llamadas, tokens, duracion, modelo y por conjunto (5 tablas)
        total = ur.MAX_TABLE_ROWS + 5
        calls = [mk(i, agent="plugin:p%d" % i, agent_group="plugin:p%d" % i, session="s%d" % i)
                 for i in range(total)]
        text = render(calls)
        heads = ("| Agente | Conjunto | Llamadas", "| Agente | Conjunto | n |", "| Agente | Conjunto | Duración",
                 "| Agente | Conjunto | Modelo", "| Conjunto | Agentes")
        for head in heads:
            self.assertEqual(len(table_with(text, head)) - 2, ur.MAX_TABLE_ROWS, head)
        self.assertEqual(text.count("Se muestran las %d primeras filas de %d." % (ur.MAX_TABLE_ROWS, total)), 5)

    def test_same_visible_name_in_two_groups_is_told_apart_in_every_per_agent_table(self):
        # T3 agrupa por (agente, conjunto): `(otro agente)` sale en `otros` y en `plugin:(no-valido)`, y un
        # agente hostil tambien. Las tres tablas por agente llevan la columna Conjunto y no hay etiquetas
        # compuestas. REGLA para T6 (reporte global): toda tabla por agente lleva `Conjunto`.
        calls = [mk(1, agent="(otro agente)", agent_group="otros"),
                 mk(2, agent="(otro agente)", agent_group="plugin:(no-valido)"),
                 mk(3, agent="a|b\nZZHOST", agent_group="otros")]
        text = render(calls)
        for head in ("| Agente | Conjunto | Llamadas", "| Agente | Conjunto | n |", "| Agente | Conjunto | Duración",
                     "| Agente | Conjunto | Modelo"):
            rows = [cells_of(line)[:2] for line in table_with(text, head)[2:]]
            self.assertEqual(len(rows), 3, head)
            self.assertEqual(len({tuple(r) for r in rows}), 3, head)
            self.assertIn(["`(otro agente)`", "`otros`"], rows, head)
            self.assertIn(["`(otro agente)`", "`plugin:(no-valido)`"], rows, head)
            self.assertNotIn("ZZHOST|", "".join(table_with(text, head)))
        # el conteo del resumen coincide con su texto: pares (nombre, conjunto)
        self.assertIn("- Agentes distintos (por nombre y conjunto): 3", text)
        self.assertNotIn("por nombre visible", text)
        # y con un solo conjunto por nombre, ambos criterios darian lo mismo
        self.assertIn("- Agentes distintos (por nombre y conjunto): 1", render([mk(1), mk(2)]))


class ReportZeroCalls(unittest.TestCase):
    def test_empty_window_report_has_no_agent_tables_but_keeps_the_frame(self):
        text = render([])
        self.assertTrue(text.startswith(ur.REPORT_MARKER + "\n"))
        self.assertIn("Sin llamadas a subagentes en la ventana.", text)
        self.assertNotIn("## Llamadas por agente", text)
        self.assertNotIn("## Tokens por llamada", text)
        self.assertNotIn("## Versiones de Claude Code", text)
        for title in ("## Resumen", "## Skills", "## Calidad de los datos", "## Cómo leer estos números", "## Pie"):
            self.assertIn(title, text)
        for block in md_tables(text):
            self.assertEqual(len({columns(line) for line in block}), 1)
        self.assertIn("- proyecto: " + ALIAS, text)

    def test_all_calls_outside_the_window(self):
        text = render([mk(1, start=dt(1, month=1), end=dt(1, 0, 1, month=1))])
        self.assertIn("Sin llamadas a subagentes en la ventana.", text)
        self.assertIn("| Llamadas leídas (todas las ventanas) | 1 |", text)
        self.assertIn("| Llamadas fuera de la ventana | 1 |", text)

    def test_no_division_by_zero_anywhere_with_zero_calls(self):
        render([])
        render([], uses=[su(1)])
        render(agg([], window=ur.make_window(TODAY, all_time=True)))


class ReportVersions(unittest.TestCase):
    def test_range_table_has_the_three_ranges_and_marks_the_doubtful_one(self):
        block = table_with(render(sample_calls()), "| Rango")
        names = [cells_of(line)[0] for line in block[2:]]
        self.assertEqual(names, ["`<2.1.310`", "`2.1.310-2.1.327`", "`>=2.1.328`"])
        self.assertIn("dudoso", block[3])
        self.assertIn("inflados", block[3])
        self.assertNotIn("dudoso", block[2])
        self.assertNotIn("dudoso", block[4])
        # llamadas por rango: 2.1.300 -> 1; 2.1.315 -> 1; 2.1.330 (x2) + 2.1.340 -> 3
        self.assertEqual([cells_of(line)[1] for line in block[2:]], ["1", "1", "3"])

    def test_unrecognised_range_row_only_when_there_are_such_calls(self):
        block = table_with(render([mk(1, versions=())]), "| Rango")
        self.assertEqual([cells_of(line)[0] for line in block[2:]],
                         ["`<2.1.310`", "`2.1.310-2.1.327`", "`>=2.1.328`", "`sin version reconocible`"])

    def test_versions_seen_table_flags_doubtful_and_unverified(self):
        block = table_with(render(sample_calls()), "| Versión |")
        rows = {cells_of(line)[0]: cells_of(line) for line in block[2:]}
        self.assertEqual(list(rows), ["`2.1.300`", "`2.1.315`", "`2.1.330`", "`2.1.340`"])
        self.assertIn("dudosa", rows["`2.1.315`"][2])
        self.assertIn("no verificada", rows["`2.1.340`"][2])
        self.assertNotIn("dudosa", rows["`2.1.300`"][2])
        self.assertEqual(rows["`2.1.300`"][2], "")
        self.assertIn("no verificada", rows["`2.1.330`"][2])    # 2.1.330 > VERIFIED_MAX (2.1.326)

    def test_doubtful_range_notice_in_the_header_only_when_calls_fall_in_it(self):
        with_notice = render(sample_calls()).split("## Resumen")[0]
        self.assertIn("AVISO", with_notice)
        self.assertIn("2.1.310 a 2.1.327", with_notice)
        self.assertIn("inflados por reintentos (corregido en 2.1.328)", with_notice)
        clean = render([mk(1, versions=("2.1.300",)), mk(2, versions=("2.1.309",))]).split("## Resumen")[0]
        self.assertNotIn("AVISO", clean)
        self.assertNotIn("inflados", clean)

    def test_boundaries_309_310_327_328(self):
        for version, doubtful in (("2.1.309", False), ("2.1.310", True), ("2.1.327", True), ("2.1.328", False)):
            with self.subTest(version=version):
                head = render([mk(1, versions=(version,))]).split("## Resumen")[0]
                self.assertEqual("inflados" in head, doubtful)

    def test_unverified_version_notice(self):
        head = render([mk(1, versions=("2.1.340",))]).split("## Resumen")[0]
        self.assertIn("AVISO", head)
        self.assertIn("posteriores a la última verificada (`" + ur.VERIFIED_MAX + "`)", head)
        self.assertIn("`2.1.340`", head)

    def test_versions_table_cap_keeps_the_most_recent_and_drops_the_oldest(self):
        calls = [mk(i, versions=("3.0.%d" % i,), session="s%d" % i) for i in range(ur.MAX_VERSION_ROWS + 4)]
        text = render(calls)
        block = table_with(text, "| Versión |")
        self.assertEqual(len(block) - 2, ur.MAX_VERSION_ROWS)
        shown = [cells_of(line)[0] for line in block[2:]]
        # las 40 mas recientes: 3.0.4 a 3.0.43; la mas antigua (3.0.0) y las 3 siguientes desaparecen
        self.assertEqual(shown, ["`3.0.%d`" % i for i in range(4, ur.MAX_VERSION_ROWS + 4)])
        self.assertIn("`3.0.%d`" % (ur.MAX_VERSION_ROWS + 3), shown)
        self.assertNotIn("`3.0.0`", shown)
        self.assertIn("Solo se muestran las %d versiones más recientes; se omiten las 4 versiones más antiguas."
                      % ur.MAX_VERSION_ROWS, text)
        # una sola omitida: singular
        one = render([mk(i, versions=("3.0.%d" % i,), session="s%d" % i) for i in range(ur.MAX_VERSION_ROWS + 1)])
        self.assertIn("se omite la versión más antigua.", one)
        self.assertNotIn("`3.0.0`", [cells_of(line)[0] for line in table_with(one, "| Versión |")[2:]])


class ReportNotices(unittest.TestCase):
    def head(self, source, **kw):
        return render(source, **kw).split("## Resumen")[0]

    def test_clean_data_has_no_notice(self):
        self.assertNotIn("AVISO", self.head([mk(1, versions=("2.1.300",))]))

    def test_reader_warnings_appear_in_the_header_verbatim(self):
        res = ur.ReadResult()
        res.calls.append(mk(1, versions=("2.1.300",)))
        res.quality["usage sin message.id"] = 2
        res.quality["message.id repetido entre archivos"] = 1
        res.quality["message.id sin deduplicar entre archivos (tope)"] = 1
        head = self.head(agg(res))
        for warning in (ur.WARN_NO_MESSAGE_ID, ur.WARN_ID_REPEATED, ur.WARN_ID_CAP):
            self.assertIn("> - AVISO: " + warning, head)
        # cada contador con aviso propio sale UNA vez en la cabecera: su aviso, sin resumen de incidencias
        self.assertEqual(head.count("AVISO"), 3)
        self.assertNotIn("la lectura tuvo incidencias", head)

    def test_a_counter_with_its_own_warning_is_not_repeated_in_the_header_summary(self):
        res = ur.ReadResult()
        res.calls.append(mk(1, versions=("2.1.300",)))
        res.quality["message.id repetido entre archivos"] = 1
        head = self.head(agg(res))
        self.assertEqual(head.count("AVISO"), 1)
        self.assertIn("> - AVISO: " + ur.WARN_ID_REPEATED, head)
        # el detalle de Calidad de los datos si lo lista
        self.assertIn("| `message.id repetido entre archivos` | 1 |", render(agg(res)))
        # con otro contador sin aviso propio, el resumen cuenta solo ese
        res.quality["lineas corruptas"] = 2
        head = self.head(agg(res))
        self.assertEqual(head.count("AVISO"), 2)
        self.assertIn("la lectura tuvo incidencias en 1 contador (", head)
        # si el aviso no esta entre los de las metricas, el contador si cuenta en el resumen
        m = dataclasses.replace(agg(res), warnings=())
        self.assertIn("la lectura tuvo incidencias en 2 contadores (", render(m).split("## Resumen")[0])

    def test_informative_counters_are_not_incidents(self):
        res = ur.ReadResult()
        res.calls.append(mk(1, versions=("2.1.300",)))
        res.quality["lineas synthetic excluidas"] = 7
        res.quality["hardlinks duplicados dentro de projects"] = 2
        text = render(agg(res))
        self.assertNotIn("AVISO", text)
        self.assertNotIn("la lectura tuvo incidencias", text)
        # se listan aparte, rotulados como informativos, no como incidencias
        self.assertIn("contadores informativos (no son incidencias)", text)
        self.assertIn("| `lineas synthetic excluidas` | 7 |", text)
        self.assertIn("| `hardlinks duplicados dentro de projects` | 2 |", text)
        self.assertNotIn("contadores distintos de cero", text)

    def test_unknown_warning_text_is_not_copied(self):
        m = dataclasses.replace(agg([mk(1)]), warnings=("ZZMARK texto libre con ruta C:\\x", ur.WARN_ID_CAP))
        text = ur.render_project_report(m, ALIAS)
        self.assertNotIn("ZZMARK", text)
        self.assertIn("> - AVISO: aviso no reconocido", text)
        self.assertIn(ur.WARN_ID_CAP, text)

    def test_excluded_and_time_notices(self):
        calls = [mk(i) for i in range(30)] + [damaged(30), mk(31, start=None, end=None, fallback_time=dt(10, 5))]
        head = self.head(calls)
        self.assertIn("1 llamada dañada queda fuera de los tokens, la duración y las herramientas", head)
        self.assertIn("1 llamada sin hora de inicio", head)
        self.assertIn("ubicada por la fecha de modificación del archivo (aproximada)", head)

    def test_plural_forms(self):
        calls = [mk(i) for i in range(60)] + [damaged(60), damaged(61)]
        head = self.head(calls)
        self.assertIn("2 llamadas dañadas quedan fuera de los tokens, la duración y las herramientas", head)

    def test_hardlinks_accepted_notice_singular_and_plural(self):
        head = self.head([mk(1, hardlink=True), mk(2)])
        self.assertIn("1 llamada leída de un enlace duro aceptado.", head)
        head = self.head([mk(1, hardlink=True), mk(2, hardlink=True), mk(3)])
        self.assertIn("2 llamadas leídas de enlaces duros aceptados.", head)
        self.assertNotIn("enlace duro aceptado.", head)

    def test_read_quality_summary_and_detail(self):
        res = ur.ReadResult()
        res.calls.append(mk(1))
        res.quality["archivos con ultima linea truncada"] = 3
        res.quality["lineas corruptas"] = 2
        text = ur.render_project_report(agg(res), ALIAS)
        head = text.split("## Resumen")[0]
        self.assertIn("> - AVISO: la lectura tuvo incidencias en 2 contadores (detalle en Calidad de los datos)",
                      head)
        self.assertIn("| `archivos con ultima linea truncada` | 3 |", text)
        self.assertIn("| `lineas corruptas` | 2 |", text)
        self.assertNotIn("| `lineas oversize descartadas` |", text)      # en cero no se pinta
        res.quality["lineas corruptas"] = 0
        self.assertIn("incidencias en 1 contador (", ur.render_project_report(agg(res), ALIAS))

    def test_closed_lists_split_every_read_counter_into_incident_or_informative(self):
        labels = set(ur.READ_QUALITY_LABELS)
        incidents, info = set(ur.READ_INCIDENT_LABELS), set(ur.READ_INFO_LABELS)
        self.assertEqual(incidents | info, labels)
        self.assertEqual(incidents & info, set())
        self.assertEqual(info, {"lineas synthetic excluidas", "hardlinks duplicados dentro de projects",
                                "sesiones principales leidas"})
        # los contadores con aviso propio son incidencias y su aviso es uno de los conocidos
        for label, warning in ur.READ_WARNED.items():
            self.assertIn(label, incidents)
            self.assertIn(warning, ur.KNOWN_WARNINGS)
        # y son exactamente los que el lector convierte en aviso
        res = ur.ReadResult()
        for label in ur.READ_WARNED:
            res.quality[label] = 1
        self.assertEqual(set(res.warnings), set(ur.READ_WARNED.values()))
        self.assertEqual(len(res.warnings), len(ur.READ_WARNED))

    def test_main_sessions_read_is_a_base_count_not_an_incident(self):
        res = ur.ReadResult()
        res.calls.append(mk(1, versions=("2.1.300",)))
        res.quality["sesiones principales leidas"] = 4
        text = ur.render_project_report(agg(res), ALIAS)
        self.assertNotIn("AVISO", text)
        self.assertIn("| Sesiones principales leídas (solo para contar skills) | 4 |", text)
        self.assertNotIn("Lectura completa", text)

    def test_read_quality_labels_outside_the_closed_list_are_dropped(self):
        m = dataclasses.replace(agg([mk(1)]), read_quality=(("ZZMARK etiqueta", 9), ("lineas corruptas", 1)))
        text = ur.render_project_report(m, ALIAS)
        self.assertNotIn("ZZMARK", text)
        self.assertIn("| `lineas corruptas` | 1 |", text)

    def test_quality_table_always_has_the_four_base_rows_and_hides_zero_problems(self):
        block = table_with(render([mk(1, versions=("2.1.300",))]), "| Concepto")
        self.assertEqual([cells_of(line)[0] for line in block[2:]], [
            "Llamadas leídas (todas las ventanas)", "Llamadas en la ventana", "Llamadas fuera de la ventana",
            "Llamadas con estadísticas de tokens"])
        self.assertEqual([cells_of(line)[1] for line in block[2:]], ["1", "1", "0", "1"])

    def test_quality_rows_for_problem_counts(self):
        calls = [mk(1), damaged(2), no_usage(3), mk(4, hardlink=True),
                 mk(5, agent="(sin-meta)", agent_group="sin-meta", has_meta=False, status="sin_meta")]
        text = render(ur.aggregate_calls(calls, today=TODAY, check_damage=False))
        for needle in ("| Llamadas dañadas (fuera de tokens, duración y herramientas) | 1 |",
                       "| Llamadas sin usage | 1 |", "| Enlaces duros aceptados (hardlinks) | 1 |",
                       "| Llamadas sin meta (agente `(sin-meta)`) | 1 |"):
            self.assertIn(needle, text)

    def test_each_conditional_quality_row_prints_its_own_field(self):
        # un valor distinto por campo: cualquier fila que lea el campo equivocado, o que falte, falla
        fields = (
            ("Llamadas dañadas (fuera de tokens, duración y herramientas)", "excluded"),
            ("Llamadas dañadas por línea intermedia corrupta", "excluded_corrupt_line"),
            ("Llamadas dañadas por archivo ilegible", "excluded_unreadable"),
            ("Llamadas dañadas por tope de tamaño", "excluded_cap"),
            ("Llamadas sin hora de inicio", "without_start"),
            ("Llamadas ubicadas por la fecha de modificación del archivo (aproximada)", "placed_by_fallback"),
            ("Llamadas sin ninguna hora (leídas en total)", "without_any_time"),
            ("Llamadas sin usage", "without_usage"),
            ("Llamadas con todos sus `message.id` ya contados en otro archivo", "all_ids_repeated"),
            ("Llamadas sin meta (agente `(sin-meta)`)", "without_meta"),
            ("Llamadas sin versión", "without_version"),
            ("Llamadas con versión no reconocible", "unrecognized_version"),
            ("Llamadas con versiones en varios rangos", "multiple_ranges"),
            ("Llamadas con una versión posterior a la verificada", "unverified_calls"),
            ("Enlaces duros aceptados (hardlinks)", "hardlinks"),
            ("Líneas sobredimensionadas descartadas", "oversize_lines"),
            ("Llamadas con modelo distinto del que declara el meta", "model_mismatch"),
        )
        base = agg([mk(1)])
        quality = dataclasses.replace(base.quality, **{f: 100 + i for i, (_, f) in enumerate(fields)})
        text = render(dataclasses.replace(base, quality=quality))
        rows = {cells_of(line)[0]: cells_of(line)[1] for line in table_with(text, "| Concepto")[2:]}
        for i, (label, _) in enumerate(fields):
            self.assertEqual(rows.get(label), str(100 + i), label)
        # en cero, ninguna se pinta
        zero = dataclasses.replace(base.quality, **{f: 0 for _, f in fields})
        rows = [cells_of(line)[0] for line in table_with(render(dataclasses.replace(base, quality=zero)),
                                                            "| Concepto")[2:]]
        self.assertEqual(len(rows), 4)


class ReportSkills(unittest.TestCase):
    @staticmethod
    def skills_section(text):
        return text.split("## Skills")[1].split("## Versiones")[0].split("## Calidad")[0]

    def test_no_skills_prints_a_line_and_no_empty_rows(self):
        section = self.skills_section(render([mk(1)]))
        self.assertIn("Sin invocaciones de skills en la ventana", section)
        self.assertNotIn("|", section)
        self.assertNotIn("SyncLayer", section)           # conjunto de skills de SyncLayer vacio: sin fila
        self.assertIn("No se atribuyen tokens a una skill", section)

    def test_skills_tables_by_hand(self):
        fa = dict(agent="forge", agent_group="SyncLayer", origin="subagente")
        uses = [su(1), su(2), su(3, session="s2"), su(4, skill="review", group="integrado"),
                su(5, skill="plugin:pl", group="plugin:pl", session="s2", **fa), su(6, session="s1", **fa)]
        section = self.skills_section(render([mk(1)], uses=uses))
        self.assertIn("Invocaciones: 6 en 2 sesiones (4 en la sesión principal, 2 en subagentes)", section)
        tables = md_tables(section)
        # por skill: brainstorm 4 (3 principal + 1 subagente) en s1 y s2; review 1; plugin:pl 1 (subagente)
        self.assertEqual(tables[0][0],
                         "| Skill | Conjunto | Invocaciones | Barra | Sesiones | Sesión principal | Subagente |")
        third = BAR_FULL * 3 + BAR_EMPTY * 7       # 1 de 4 = 2,5 -> 3 bloques (medio hacia arriba)
        self.assertEqual(tables[0][2], "| `brainstorm` | `otros` | 4 | " + BAR_FULL * 10 + " | 2 | 3 | 1 |")
        self.assertEqual(tables[0][3], "| `plugin:pl` | `plugin:pl` | 1 | " + third + " | 1 | 0 | 1 |")
        self.assertEqual(tables[0][4], "| `review` | `integrado` | 1 | " + third + " | 1 | 1 | 0 |")
        # por conjunto: otros 4 (1 skill), integrado 1, plugin:pl 1; sin fila de SyncLayer
        self.assertEqual(tables[1][0], "| Conjunto | Skills | Invocaciones | Sesiones |")
        self.assertEqual([cells_of(line)[0] for line in tables[1][2:]], ["`otros`", "`integrado`", "`plugin:pl`"])
        # por agente: solo las hechas dentro de subagentes
        self.assertEqual(tables[2][0], "| Agente | Conjunto del agente | Skill | Invocaciones |")
        self.assertEqual(tables[2][2:], ["| `forge` | `SyncLayer` | `brainstorm` | 1 |",
                                         "| `forge` | `SyncLayer` | `plugin:pl` | 1 |"])
        for block in tables:
            self.assertEqual(len({columns(line) for line in block}), 1)

    def test_agent_table_absent_when_no_subagent_invoked_a_skill(self):
        section = self.skills_section(render([mk(1)], uses=[su(1)]))
        self.assertEqual(len(md_tables(section)), 2)
        self.assertNotIn("Conjunto del agente", section)

    def test_zero_rows_are_never_drawn(self):
        # filas con 0 invocaciones (p. ej. el conjunto SyncLayer de skills, vacio): no se pintan
        empty = ur.SkillMetrics(
            calls=1, sessions=1, main_calls=1, subagent_calls=0,
            rows=(ur.SkillRow("a", "otros", 1, 1, 0, 1), ur.SkillRow("b", "SyncLayer", 0, 0, 0, 0)),
            groups=(ur.SkillGroupRow("otros", 1, 1, 1), ur.SkillGroupRow("SyncLayer", 0, 0, 0)),
            by_agent=(ur.SkillAgentRow("forge", "SyncLayer", "a", "otros", 0),),
            quality=ur.SkillQuality(1, 1, 0, 0, 0))
        text = render(dataclasses.replace(agg([mk(1)]), skills=empty))
        section = self.skills_section(text)
        self.assertNotIn("SyncLayer", section)
        self.assertNotIn("Conjunto del agente", section)
        self.assertNotIn("`b`", section)
        self.assertIn("| `a` | `otros` | 1 |", section)

    def test_skills_without_calls_still_report(self):
        self.assertIn("| `brainstorm` | `otros` | 1 |", render([], uses=[su(1)]))

    def test_skill_quality_rows(self):
        uses = [su(1, skill="(otra skill)"), su(2, moment=None), su(3, moment=dt(1, month=1))]
        text = render([mk(1)], uses=uses)
        self.assertIn("| Skills: invocaciones con nombre no válido (se muestran como `(otra skill)`) | 1 |", text)
        self.assertIn("| Skills: invocaciones fuera de la ventana | 2 |", text)
        self.assertIn("| Skills: invocaciones sin hora (solo cuentan con todo el historial) | 1 |", text)

    def test_skill_rows_cap(self):
        uses = [su(i, skill="sk%d" % i, session="s%d" % i) for i in range(ur.MAX_TABLE_ROWS + 3)]
        section = self.skills_section(render([mk(1)], uses=uses))
        self.assertEqual(len(md_tables(section)[0]) - 2, ur.MAX_TABLE_ROWS)
        self.assertIn("Se muestran las %d primeras filas de %d" % (ur.MAX_TABLE_ROWS, ur.MAX_TABLE_ROWS + 3), section)

    def test_skill_group_and_agent_tables_are_capped_too(self):
        total = ur.MAX_TABLE_ROWS + 3
        uses = [su(i, skill="sk%d" % i, group="plugin:g%d" % i, session="s%d" % i, origin="subagente",
                   agent="plugin:a%d" % i, agent_group="plugin:a%d" % i) for i in range(total)]
        section = self.skills_section(render([mk(1)], uses=uses))
        tables = md_tables(section)
        self.assertEqual(len(tables), 3)
        for block in tables:
            self.assertEqual(len(block) - 2, ur.MAX_TABLE_ROWS, block[0])
        self.assertEqual(section.count("Se muestran las %d primeras filas de %d." % (ur.MAX_TABLE_ROWS, total)), 3)


class ReportReadingGuide(unittest.TestCase):
    def setUp(self):
        self.text = render(sample_calls())
        self.guide = self.text.split("## Cómo leer estos números")[1].split("## Pie")[0]

    def test_it_dumps_both_limitation_tuples_verbatim(self):
        for line in ur.REPEAT_LIMITATIONS + ur.SKILL_LIMITATIONS:
            self.assertIn("- " + line + "\n", self.guide)

    def test_it_says_what_is_not_measured(self):
        self.assertIn("No mide la calidad del resultado", self.guide)
        self.assertIn("No muestra costos", self.guide)
        self.assertIn("precio de lista", self.guide)
        self.assertIn("n < 10", self.guide)
        self.assertIn("formato interno de Claude Code", self.guide)
        self.assertIn("indicativo", self.guide)
        self.assertIn("inferencia", self.guide.lower())

    # Raices prohibidas (sin tildes: el texto se normaliza antes). Lista blanca: las frases fijas EXACTAS que
    # niegan el costo y el precio; nada mas puede contener esas raices.
    FORBIDDEN = re.compile(r"\b(ahorr|cost[eo]|gast|precio|barat|eficien|eficaz|optim|mejor|peor|rapid|"
                           r"rendimiento|ventaja|superior|dinero|economic)")
    ALLOWED_PHRASES = (ur.HOW_TO_READ[0], ur.HOW_TO_READ[1])
    # El TEXTO LITERAL de las tres frases blancas (dos aqui y GLOBAL_COMPARES[1]) queda fijado: si alguien anade
    # una raiz prohibida dentro de una de ellas, `forbidden_hits` ya no la veria (se borra la frase entera) y
    # esta prueba falla.
    PINNED = (
        "No mide la calidad del resultado de un agente ni el costo en dinero: una llamada con menos tokens no"
        " dice nada sobre su resultado.",
        "No muestra costos. Los tokens no son una factura (la caché leída se cobra distinto) y cualquier costo"
        " sería una estimación a precio de lista; aquí no se calcula.",
        "No compara la calidad del resultado de un agente, ni el costo real, ni el ahorro de nadie: esas cifras no salen"
        " de las transcripciones.",
    )

    def test_the_allowed_phrases_are_pinned_to_their_literal_text(self):
        self.assertEqual(ur.HOW_TO_READ[0], self.PINNED[0])
        self.assertEqual(ur.HOW_TO_READ[1], self.PINNED[1])
        self.assertEqual(ur.GLOBAL_COMPARES[1], self.PINNED[2])

    def test_the_new_stems_are_caught(self):
        for sentence in ("mejor rendimiento", "una ventaja clara", "es superior", "cuesta dinero",
                         "es económico", "el rendimiento"):
            with self.subTest(sentence=sentence):
                self.assertTrue(self.forbidden_hits(sentence), sentence)

    @classmethod
    def forbidden_hits(cls, text):
        for phrase in cls.ALLOWED_PHRASES:
            text = text.replace(phrase, "")
        plain = "".join(ch for ch in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(ch))
        return cls.FORBIDDEN.findall(plain)

    def test_forbidden_stems_catch_the_variants_a_plain_word_list_missed(self):
        for sentence in ("el coste total", "el gasto es menor", "el precio", "las mejores llamadas", "es eficaz",
                         "el modo óptimo", "es más rápido", "ahorra tokens", "es barato", "peor resultado",
                         "mejor opción", "más eficiente", "cualquier costo real", "costos bajos"):
            with self.subTest(sentence=sentence):
                self.assertTrue(self.forbidden_hits(sentence), sentence)
        # las frases blancas exactas pasan; cambiarles una palabra ya no
        for phrase in self.ALLOWED_PHRASES:
            self.assertEqual(self.forbidden_hits(phrase), [])
        self.assertTrue(self.forbidden_hits(self.ALLOWED_PHRASES[1] + " Es más barato."))
        self.assertTrue(self.forbidden_hits(self.ALLOWED_PHRASES[1].replace("costo", "coste")))

    def test_no_saving_cost_or_quality_claims_anywhere(self):
        texts = (self.text, render([]), render([mk(1)], uses=[su(1)]), render(sample_calls(), uses=[su(1)]),
                 render(golden_calls()))
        for text in texts:
            self.assertEqual(self.forbidden_hits(text), [])
            low = text.lower()
            for word in ("$", "usd", "dolar", "dólar", "euro"):
                self.assertNotIn(word, low, word)
        # la frase blanca esta de verdad en el reporte (no se prueba contra un texto vacio)
        for phrase in self.ALLOWED_PHRASES:
            self.assertIn(phrase, self.text)

    def test_section_has_subsections_for_repeats_and_skills(self):
        self.assertIn("### Repeticiones (inferido)", self.guide)
        self.assertIn("### Skills", self.guide)


class ReportPrivacy(ReaderBase):
    FOLDER = "c--Users-" + us.M_FOLDER + "-proj"

    def _text(self, **kw):
        tree = us.Tree(self.base)
        ts = "2026-03-10T10:00:%02dZ"
        tree.main_session(self.FOLDER, us.M_SESSION + "-1", [us.skill_line("sm1", ts % 1, ["brainstorm"])])
        tree.subagent(self.FOLDER, us.M_SESSION + "-1", "a1",
                      [us.user(ts % 0), us.assistant("m1", ts % 3, blocks=[us.tool_use_block("t1", "Read")]),
                       us.skill_line("sa1", ts % 5, ["plugin:" + us.M_SKILL_TAIL])],
                      meta={"agentType": "pl:" + us.M_TYPE, "description": us.M_DESCRIPTION})
        tree.subagent(self.FOLDER, us.M_SESSION + "-2", "a2",
                      [us.assistant("m2", ts % 20, model=us.M_MODEL, version=us.M_VERSION)])
        tree.subagent("c--otro-proyecto", "s9", "a9", [us.assistant("m9", ts % 30)])
        self.res = self.read(tree, check_damage=False)
        metrics = ur.aggregate_calls(self.res, today=TODAY)
        return ur.render_project_report(metrics, ur._project_alias(self.FOLDER), **kw), metrics

    def test_no_marker_path_identifier_or_other_alias_in_the_text(self):
        text, metrics = self._text()
        for marker in us.ALL_MARKERS:
            self.assertNotIn(marker, text)
        for c in self.res.calls:
            self.assertNotIn(c.call_id, text)
            self.assertNotIn(c.session, text)
            self.assertNotIn(c.agent_key, text)
        self.assertEqual(re.findall(r"\b[0-9a-f]{16}\b", text), [])
        self.assertNotIn("c--otro-proyecto", text)
        self.assertNotIn(self.FOLDER, text)
        # solo aparece el alias propio, nunca el de otro proyecto de las metricas
        other = ur._project_alias("c--otro-proyecto")
        self.assertIn(other, {p.project for p in metrics.projects})
        self.assertNotIn(other, text)
        self.assertEqual(set(re.findall(r"\bp-[0-9a-f]{8}\b", text)), {ur._project_alias(self.FOLDER)})
        for bad in ("\\", "C:", "/Users", "ZZMARK"):
            self.assertNotIn(bad, text)

    def test_text_shows_only_closed_list_labels(self):
        text, _ = self._text()
        self.assertIn("`plugin:pl`", text)       # solo el prefijo validado de un agente de plugin
        self.assertNotIn(us.M_TYPE, text)
        self.assertNotIn(us.M_MODEL, text)
        self.assertIn("`(otro modelo)`", text)    # el modelo que no pasa el filtro sale con su etiqueta cerrada

    def test_generator_receives_only_aggregated_metrics(self):
        import inspect
        params = list(inspect.signature(ur.render_project_report).parameters)
        self.assertEqual(params, ["metrics", "project_alias", "generated"])


class ReportSourceHygiene(unittest.TestCase):
    def test_tool_source_is_ascii_with_lf_and_the_bars_come_from_escapes(self):
        with open(SCRIPT, "rb") as f:
            raw = f.read()
        raw.decode("ascii")
        self.assertNotIn(b"\r", raw)
        self.assertEqual(ur.BAR_FULL, "\u2588")
        self.assertEqual(ur.BAR_EMPTY, "\u2591")
        self.assertIn(b'BAR_FULL = "\\u2588"', raw)
        self.assertIn(b'BAR_EMPTY = "\\u2591"', raw)

    def test_source_carries_the_accents_as_escapes(self):
        # el modulo sigue siendo ASCII (arriba); el REPORTE lleva tildes, que salen de escapes \u00xx
        with open(SCRIPT, "rb") as f:
            raw = f.read()
        for escape in (b"\\u00f3", b"\\u00e9", b"\\u00ed", b"\\u00f1"):
            self.assertIn(escape, raw)
        self.assertNotIn("ó".encode("utf-8"), raw)

    def test_fixed_report_texts_are_ascii_or_accented_spanish_and_utf8(self):
        fixed = (ur.HOW_TO_READ + ur.PRIVACY_NOTES + ur.REPEAT_LIMITATIONS + ur.SKILL_LIMITATIONS
                 + tuple(ur.KNOWN_WARNINGS) + (ur.NOTE_DOUBTFUL_RANGE, ur.NOTE_NO_RANGE, ur.UNKNOWN_WARNING))
        for text in fixed:
            for ch in text:
                self.assertTrue(" " <= ch <= "~" or ch in ACCENTED, (ch, text))
            self.assertEqual(text.encode("utf-8").decode("utf-8"), text)
        for text in (ur.REPORT_MARKER, ur.TOOL_NAME):
            text.encode("ascii")
        self.assertEqual(ur.REPORT_SCHEMA, 1)
        # las etiquetas que pasan por `_code` siguen en ASCII (`_code` cambia lo no ASCII por `?`)
        for text in ur.READ_QUALITY_LABELS + ur.VERSION_RANGES:
            text.encode("ascii")

    def test_report_has_no_unaccented_spanish_words_outside_code(self):
        res = ur.ReadResult()
        res.calls.extend(sample_calls())
        res.quality["lineas corruptas"] = 1
        res.quality["lineas synthetic excluidas"] = 1
        res.quality["message.id repetido entre archivos"] = 1
        texts = (render(sample_calls(), uses=[su(1), su(2, origin="subagente", agent="forge",
                                                        agent_group="SyncLayer")]),
                 render(agg(res)), render([]), render(golden_calls(), generated=datetime.date(2026, 4, 1)))
        bare = re.compile(r"\b(sesion|duracion|numeros?|cache|linea|lineas|danad[oa]s?|ultim[ao]|tamano|"
                          r"senal|estadisticas?|leid[oa]s?|invocacion|version|mas|"
                          r"aqui|numericamente|posicion|estimacion|modificacion|aparicion|alcanzo|legitimos|"
                          r"informacion|unica|metricas?|peticion|conversacion|opcion|ningun|despues|tambien)\b",
                          re.IGNORECASE)
        for text in texts:
            outside = "\n".join(re.sub(r"`[^`]*`", "", line) for line in text.split("\n"))
            self.assertEqual(bare.findall(outside), [])


class ReportOverSyntheticTree(ReaderBase):
    def test_report_from_a_read_tree_is_valid_and_deterministic(self):
        tree = us.Tree(self.base)
        ts = "2026-03-10T10:00:%02dZ"
        for i in range(3):
            tree.subagent("c--proj", "s%d" % (i % 2), "a%d" % i,
                          [us.user(ts % (i * 10)),
                           us.assistant("m%d" % i, ts % (i * 10 + 5), usage_value=us.usage(10 * (i + 1), 5, 2, 3),
                                        blocks=[us.tool_use_block("t%d" % i, "Bash")])],
                          meta={"agentType": ("forge", "scout", "auditor")[i]})
        alias = ur._project_alias("c--proj")
        text = ur.render_project_report(ur.aggregate_calls(self.read(tree), today=TODAY), alias)
        again = ur.render_project_report(ur.aggregate_calls(self.read(tree), today=TODAY), alias)
        self.assertEqual(text, again)       # claves de digest distintas por lectura: mismos bytes
        for block in md_tables(text):
            self.assertEqual(len({columns(line) for line in block}), 1)
        self.assertIn("Llamadas: 3 en 2 sesiones", text)

    def test_hostile_agent_type_and_model_from_the_reader_keep_every_table_intact(self):
        # lector -> agregacion -> reporte con `|` y saltos de linea en agentType, meta.model y model de las lineas
        tree = us.Tree(self.base)
        ts = "2026-03-10T10:00:%02dZ"
        hostile = ("a|b\nZZHOST", "Bad Prefix|x:zz\r\nZZHOST", "forge")
        for i, agent_type in enumerate(hostile):
            tree.subagent("c--proj", "s%d" % i, "a%d" % i,
                          [us.user(ts % (i * 10)),
                           us.assistant("m%d" % i, ts % (i * 10 + 5), model="x|y\nZZHOST%d" % i,
                                        blocks=[us.tool_use_block("t%d" % i, "Bash")])],
                          meta={"agentType": agent_type, "model": "m|\nZZHOST"})
        alias = ur._project_alias("c--proj")
        text = ur.render_project_report(ur.aggregate_calls(self.read(tree), today=TODAY), alias)
        self.assertNotIn("ZZHOST", text)
        self.assertNotIn("\r", text)
        for block in md_tables(text):
            self.assertEqual(len({columns(line) for line in block}), 1, block[0])
        # nada se corto a media tabla: cada linea que empieza por `|` termina en `|`
        for line in text.split("\n"):
            if line.startswith("|"):
                self.assertTrue(line.endswith("|"), line)
        # los dos `(otro agente)` (conjuntos `otros` y `plugin:(no-valido)`) se distinguen en las tres tablas
        for head in ("| Agente | Conjunto | Llamadas", "| Agente | Conjunto | n |",
                     "| Agente | Conjunto | Duración", "| Agente | Conjunto | Modelo"):
            rows = {tuple(cells_of(line)[:2]) for line in table_with(text, head)[2:]}
            self.assertIn(("`(otro agente)`", "`otros`"), rows, head)
            self.assertIn(("`(otro agente)`", "`plugin:(no-valido)`"), rows, head)
        self.assertIn("- Agentes distintos (por nombre y conjunto): 3", text)
        self.assertIn("`(otro modelo)`", text)


class ReportSmallSampleLegend(unittest.TestCase):
    LEGEND = "`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco."

    @classmethod
    def tables_with_legend(cls, text):
        """[(cabecera, lleva `*`, lleva leyenda)] de cada tabla: la leyenda es el parrafo que sigue a la tabla
        (y a su nota de filas omitidas) hasta el siguiente titulo."""
        lines = text.split("\n")
        out, i = [], 0
        while i < len(lines):
            if not lines[i].startswith("|"):
                i += 1
                continue
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            block = lines[i:j]
            after = []
            k = j
            while k < len(lines) and not lines[k].startswith(("#", "|")):
                after.append(lines[k])
                k += 1
            marked = any(re.search(r" \* \|", line) for line in block[2:])
            out.append((block[0], marked, cls.LEGEND in after))
            i = j
        return out

    def test_every_table_with_a_star_has_the_legend_and_no_other_does(self):
        text = render(sample_calls())
        tables = self.tables_with_legend(text)
        self.assertGreaterEqual(sum(1 for _, marked, _ in tables if marked), 4)
        for head, marked, legend in tables:
            self.assertEqual(marked, legend, head)
        self.assertEqual(text.count(self.LEGEND), sum(1 for _, marked, _ in tables if marked))

    def test_tokens_n_over_ten_and_duration_n_five_puts_the_legend_only_under_the_small_tables(self):
        calls = ([mk(i, session="s%d" % i) for i in range(5)]
                 + [mk(i, session="s%d" % i, start=None, end=None, fallback_time=dt(10, 5))
                    for i in range(5, 10)])
        text = render(calls)
        by_head = {head: (marked, legend) for head, marked, legend in self.tables_with_legend(text)}
        tokens = [v for h, v in by_head.items() if h.startswith("| Agente | Conjunto | n |")][0]
        duration = [v for h, v in by_head.items() if h.startswith("| Agente | Conjunto | Duración")][0]
        group = [v for h, v in by_head.items() if h.startswith("| Conjunto | Agentes")][0]
        self.assertEqual(tokens, (False, False))      # n = 10 llamadas con tokens
        self.assertEqual(duration, (True, True))      # n = 5 con duracion
        self.assertEqual(group, (True, True))         # la mediana de duracion del conjunto
        for head, (marked, legend) in by_head.items():
            self.assertEqual(marked, legend, head)
        # la seccion de tokens no la lleva; la de duracion si
        sections = text.split("\n## ")
        tokens_section = [s for s in sections if s.startswith("Tokens por llamada")][0]
        duration_section = [s for s in sections if s.startswith("Duración y herramientas")][0]
        self.assertNotIn("pocas muestras", tokens_section)
        self.assertIn(self.LEGEND, duration_section)

    def test_legend_comes_after_the_row_cap_note(self):
        calls = [mk(i, agent="plugin:p%d" % i, agent_group="plugin:p%d" % i, session="s%d" % i)
                 for i in range(ur.MAX_TABLE_ROWS + 2)]
        text = render(calls)
        note = "Se muestran las %d primeras filas de %d." % (ur.MAX_TABLE_ROWS, ur.MAX_TABLE_ROWS + 2)
        tokens = text.split("## Tokens por llamada")[1].split("## Duración")[0]
        self.assertLess(tokens.index(note), tokens.index(self.LEGEND))

    def test_no_legend_without_stars(self):
        text = render([mk(i, session="s%d" % i) for i in range(10)])
        self.assertNotIn("pocas muestras", text.split("## Cómo leer")[0])
        self.assertNotIn("`*`", text.split("## Cómo leer")[0])


class ReportHostileFields(unittest.TestCase):
    HOSTILE = ("## ZZH", "a\rb", "x\x1b[31mred", "rtl\u202etxt", "<script>alert(1)</script>",
               "[a](javascript:x)", "x|y\n## Inyectado")

    def render_hostile(self, **replace):
        base = agg(sample_calls())
        fields = dict(versions_seen=tuple((h, 1) for h in self.HOSTILE), unverified_versions=self.HOSTILE,
                      verified_max="[a](javascript:x)\r## ZZV\u202e<script>")
        fields.update(replace)
        return ur.render_project_report(dataclasses.replace(base, **fields), ALIAS)

    def assert_nothing_injected(self, text):
        for bad in ("\r", "\x1b", "\u202e"):
            self.assertNotIn(bad, text)
        for line in text.split("\n"):
            self.assertFalse(line.startswith(("## ZZ", "## Inyectado")), line)
            outside = re.sub(r"`[^`]*`", "", line)       # lo que queda fuera de los fragmentos de codigo
            for bad in ("<script", "javascript:", "](", "## "):
                if not line.startswith("#"):
                    self.assertNotIn(bad, outside, line)
        for block in md_tables(text):
            self.assertEqual(len({columns(line) for line in block}), 1, block[0])

    def test_versions_seen_unverified_and_verified_max_are_sanitized_everywhere(self):
        text = self.render_hostile()
        self.assert_nothing_injected(text)
        head = text.split("## Resumen")[0]
        self.assertIn("(`[a](javascript:x)?## ZZV?<script>`)", head)       # verified_max por _code, con `?`
        self.assertIn("`x|y?## Inyectado`".replace("|", "\\|"), head)      # una version hostil en el aviso
        foot = text.split("## Pie")[1]
        self.assertIn("- ultima_version_verificada: `[a](javascript:x)?## ZZV?<script>`", foot)
        # la cabecera: el rango de versiones sale por _code
        self.assertIn("> - Claude Code: versiones `## ZZH` a ", head)

    def test_a_single_hostile_version_in_the_header_is_a_code_span(self):
        text = self.render_hostile(versions_seen=(("<script>x", 2),), unverified_versions=())
        self.assertIn("> - Claude Code: versión `<script>x`", text)
        self.assert_nothing_injected(text)

    def test_unverified_list_is_capped_and_every_item_is_code(self):
        many = tuple("9.0.%d" % i for i in range(ur.MAX_SHOWN_VERSIONS + 3))
        text = self.render_hostile(unverified_versions=many)
        head = text.split("## Resumen")[0]
        self.assertIn("`9.0.%d`" % (ur.MAX_SHOWN_VERSIONS + 2), head)       # la mas reciente primero
        self.assertIn("(+3 más)", head)
        self.assertNotIn("`9.0.0`", head)
        self.assert_nothing_injected(text)


class ReportProjectsAndAliases(unittest.TestCase):
    def test_more_than_one_alias_in_the_metrics_does_not_fail_and_only_the_given_one_prints(self):
        # T7 puede leer varias carpetas (--transcripts-dir, un worktree tiene otro alias): `metrics.projects`
        # trae varios y el generador solo imprime el alias que recibe
        calls = [mk(1, project="p-00000001"), mk(2, project="p-00000002"), mk(3, project="p-00000003")]
        metrics = agg(calls)
        self.assertEqual(len(metrics.projects), 3)
        text = ur.render_project_report(metrics, ALIAS)
        self.assertEqual(set(re.findall(r"\bp-[0-9a-f]{8}\b", text)), {ALIAS})
        self.assertIn("Llamadas: 3 en 1 sesión", text)

    def test_c_and_capital_c_folder_names_give_the_same_alias(self):
        self.assertEqual(ur._project_alias("c--proj"), ur._project_alias("C--proj"))
        calls = [mk(1, project=ur._project_alias("c--proj")), mk(2, project=ur._project_alias("C--proj"))]
        self.assertEqual(len(agg(calls).projects), 1)


# Archivo dorado: el reporte completo de un caso pequeno (dos llamadas, una sesion, sin skills). Los valores se
# calcularon a mano: suma 200 + 20 = 220 tokens; mediana de [20, 200] = (20+200+1)//2 = 110 y p90 = 200;
# duraciones [60, 5] -> (5+60+1)//2 = 33; herramientas [3, 0] -> (0+3+1)//2 = 2; barra de scout en tokens
# 20 de 200 = 1 bloque (minimo uno); 2 llamadas / 1 sesion = 2.0. La version 9.0.0 es posterior a VERIFIED_MAX
# (que el golden NO fija: `@VM@` se sustituye por `ur.VERIFIED_MAX`, asi subirlo no rompe la prueba).
GOLDEN_PROJECT_REPORT_TEMPLATE = (
    '<!-- synclayer-usage-report v1 -->\n'
    '# Reporte de uso de subagentes: proyecto p-0a1b2c3d\n'
    '\n'
    '> - Ventana: 2026-03-02 a 2026-03-31 (UTC, ambos inclusive)\n'
    '> - Llamadas: 2 en 1 sesi\u00f3n\n'
    '> - Claude Code: versiones `2.1.300` a `9.0.0` (2 versiones)\n'
    '> - Esquema del reporte: 1\n'
    '> - Generado: 2026-04-01\n'
    '> - Reporte local: no lo subas a git.\n'
    '> - AVISO: hay versiones de Claude Code posteriores a la \u00faltima verificada (`@VM@`): `9.0.0`. El formato interno puede haber cambiado.\n'
    '\n'
    '## Resumen\n'
    '\n'
    '- Llamadas: 2 en 1 sesi\u00f3n (2.0 llamadas por sesi\u00f3n)\n'
    '- Agentes distintos (por nombre y conjunto): 2\n'
    '- Tokens (suma de las llamadas con estad\u00edsticas): 220 en 2 llamadas\n'
    '- Repeticiones consecutivas (inferido): 0\n'
    '- Llamadas en el rango de versi\u00f3n dudoso (2.1.310 a 2.1.327): 0 de 2 (0 %)\n'
    '- Skills: 0 invocaciones en 0 sesiones\n'
    '\n'
    '## Llamadas por agente\n'
    '\n'
    '| Agente | Conjunto | Llamadas | Barra | Sesiones | Llamadas/sesi\u00f3n | Repeticiones (inferido) |\n'
    '|---|---|---:|---|---:|---:|---:|\n'
    '| `forge` | `SyncLayer` | 1 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 1 | 1.0 | 0 |\n'
    '| `scout` | `SyncLayer` | 1 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 1 | 1.0 | 0 |\n'
    '\n'
    '## Tokens por llamada\n'
    '\n'
    '| Agente | Conjunto | n | Tokens (suma) | Barra | Mediana | p90 | Entrada (med.) | Salida (med.) | Cach\u00e9 escrita (med.) | Cach\u00e9 le\u00edda (med.) | Peticiones (med.) |\n'
    '|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|\n'
    '| `forge` | `SyncLayer` | 1 * | 200 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 200 * | 200 * | 100 | 50 | 20 | 30 | 1 |\n'
    '| `scout` | `SyncLayer` | 1 * | 20 | \u2588\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591 | 20 * | 20 * | 10 | 5 | 2 | 3 | 1 |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    '## Duraci\u00f3n y herramientas\n'
    '\n'
    '| Agente | Conjunto | Duraci\u00f3n aprox. s (med.) | p90 | Herramientas (med.) | p90 |\n'
    '|---|---|---:|---:|---:|---:|\n'
    '| `forge` | `SyncLayer` | 60 * | 60 * | 3 * | 3 * |\n'
    '| `scout` | `SyncLayer` | 5 * | 5 * | 0 * | 0 * |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    '## Modelo real\n'
    '\n'
    '| Agente | Conjunto | Modelo | Llamadas |\n'
    '|---|---|---|---:|\n'
    '| `forge` | `SyncLayer` | `claude-opus-4-1` | 1 |\n'
    '| `scout` | `SyncLayer` | `claude-opus-4-1` | 1 |\n'
    '\n'
    '## Por conjunto\n'
    '\n'
    '| Conjunto | Agentes | Llamadas | Barra | Tokens/llamada (med.) | p90 | Duraci\u00f3n aprox. s (med.) | Herramientas (med.) |\n'
    '|---|---:|---:|---|---:|---:|---:|---:|\n'
    '| `SyncLayer` | 2 | 2 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 110 * | 200 * | 33 * | 2 * |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    '## Skills\n'
    '\n'
    'Sin invocaciones de skills en la ventana.\n'
    '\n'
    'No se atribuyen tokens a una skill: corre en el contexto de la sesi\u00f3n que la invoca.\n'
    '\n'
    '## Versiones de Claude Code\n'
    '\n'
    'Por rango de versi\u00f3n:\n'
    '\n'
    '| Rango | Llamadas | Tokens/llamada (med.) | p90 | Nota |\n'
    '|---|---:|---:|---:|---|\n'
    '| `<2.1.310` | 1 | 200 * | 200 * |  |\n'
    '| `2.1.310-2.1.327` | 0 | - | - | dudoso: tokens posiblemente inflados por reintentos (corregido en 2.1.328) |\n'
    '| `>=2.1.328` | 1 | 20 * | 20 * |  |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    'Comparar entre rangos es solo indicativo.\n'
    '\n'
    'Versiones vistas:\n'
    '\n'
    '| Versi\u00f3n | Llamadas | Nota |\n'
    '|---|---:|---|\n'
    '| `2.1.300` | 1 |  |\n'
    '| `9.0.0` | 1 | no verificada (mayor que `@VM@`) |\n'
    '\n'
    '## Calidad de los datos\n'
    '\n'
    '| Concepto | Cantidad |\n'
    '|---|---:|\n'
    '| Llamadas le\u00eddas (todas las ventanas) | 2 |\n'
    '| Llamadas en la ventana | 2 |\n'
    '| Llamadas fuera de la ventana | 0 |\n'
    '| Llamadas con estad\u00edsticas de tokens | 2 |\n'
    '| Llamadas con una versi\u00f3n posterior a la verificada | 1 |\n'
    '\n'
    '## C\u00f3mo leer estos n\u00fameros\n'
    '\n'
    '- No mide la calidad del resultado de un agente ni el costo en dinero: una llamada con menos tokens no dice nada sobre su resultado.\n'
    '- No muestra costos. Los tokens no son una factura (la cach\u00e9 le\u00edda se cobra distinto) y cualquier costo ser\u00eda una estimaci\u00f3n a precio de lista; aqu\u00ed no se calcula.\n'
    '- Una llamada es un archivo de subagente (`agent-<id>.jsonl`). Los tokens por llamada suman entrada, salida, cach\u00e9 escrita y cach\u00e9 le\u00edda; una respuesta repartida en varias l\u00edneas se cuenta una vez (se deduplica por `message.id`).\n'
    '- La duraci\u00f3n es aproximada: \u00faltima marca de tiempo menos la primera. Incluye esperas de herramientas y de permisos.\n'
    '- Con n < 10 llamadas (marca `*`, pocas muestras) la mediana y el p90 dicen poco.\n'
    '- Mediana: con n par, media de los dos centrales redondeada al entero (medio hacia arriba). p90: el valor en la posici\u00f3n ceil(0,9 n) de la lista ordenada. Los porcentajes se redondean al entero m\u00e1s cercano (medio hacia arriba); `<1 %` es un valor distinto de cero que redondea a 0.\n'
    '- Las repeticiones son una inferencia, no un reintento confirmado (ver abajo).\n'
    '- Las versiones 2.1.310 a 2.1.327 de Claude Code pueden inflar los tokens por reintentos y no se corrige num\u00e9ricamente. Comparar entre rangos de versi\u00f3n es solo indicativo.\n'
    '- Los n\u00fameros dependen de un formato interno de Claude Code que no est\u00e1 garantizado y puede cambiar sin aviso.\n'
    '- Solo se leen las carpetas de transcripciones elegidas para este proyecto: las sesiones abiertas desde una subcarpeta o un worktree viven en otra carpeta y no se incluyen salvo que se indique.\n'
    '\n'
    '### Repeticiones (inferido)\n'
    '\n'
    '- Las repeticiones son una se\u00f1al inferida por horas de inicio y fin, no un reintento confirmado.\n'
    '- Una llamada puede marcarse aunque corra en paralelo con otra anterior del mismo agente: solo se mira la anterior inmediata por hora de inicio (A1 0-100, A2 10-20, A3 30-40: se marca A3).\n'
    '- Las llamadas sin hora de inicio no participan en la cadena ni la rompen.\n'
    '- La primera llamada de la ventana no se marca, aunque su anterior quedara fuera de la ventana.\n'
    '- Las llamadas sin meta nunca se marcan, pero rompen la cadena de los dem\u00e1s agentes.\n'
    '- En flujos secuenciales leg\u00edtimos (el mismo agente en pasos distintos de un plan) sobreestima.\n'
    '\n'
    '### Skills\n'
    '\n'
    '- Una l\u00ednea corrupta en medio de una sesi\u00f3n principal o de un subagente se descarta y puede esconder una invocaci\u00f3n de Skill: el conteo de skills puede ser menor que el real.\n'
    '- Las skills que el usuario invoca con /nombre no generan un bloque tool_use de Skill y no se cuentan: solo se cuentan las que invoca el modelo.\n'
    '\n'
    '## Pie\n'
    '\n'
    '- report_schema: 1\n'
    '- herramienta: tools/usage_report.py\n'
    '- ultima_version_verificada: `@VM@`\n'
    '- proyecto: p-0a1b2c3d\n'
    '\n'
    '- Este archivo no contiene contenido de conversaciones ni rutas, pero revela volumen de uso. Es local: no lo subas a git ni lo compartas sin revisarlo.\n'
    '- El alias `p-<8 hex>` es un hash sin sal del nombre de la carpeta del proyecto: quien conozca o adivine el nombre de la carpeta puede recalcularlo. No es anonimato.\n'
    '- Los nombres de skills de usuario salen tal cual: pueden revelar nombres privados. El prefijo de una skill de plugin (`plugin:<prefijo>`) sale de texto que escribe el modelo: puede ser cualquier cadena `[a-z0-9-]{1,32}`, no solo un nombre de plugin.\n'
    '- Los nombres de modelo salen de las transcripciones con un patrón amplio (`claude-` y tramos de palabra de hasta 12 caracteres): un id de modelo personalizado puede salir tal cual.\n'
    '- Un agente de proyecto con el mismo nombre que uno de SyncLayer cuenta como SyncLayer.\n'
)
GOLDEN_PROJECT_REPORT = GOLDEN_PROJECT_REPORT_TEMPLATE.replace("@VM@", ur.VERIFIED_MAX)


def golden_calls():
    return [mk(1, session="s1", input_tokens=100, output_tokens=50, cache_creation_tokens=20,
               cache_read_tokens=30, tools=3, versions=("2.1.300",), **span(60)),
            mk(2, agent="scout", session="s1", versions=("9.0.0",), tools=0, **span(5, hour=11))]


class ReportGolden(unittest.TestCase):
    def test_small_report_matches_the_golden_text_byte_for_byte(self):
        text = render(golden_calls(), generated=datetime.date(2026, 4, 1))
        self.assertEqual(text, GOLDEN_PROJECT_REPORT)
        self.assertEqual(text.encode("utf-8"), GOLDEN_PROJECT_REPORT.encode("utf-8"))

    def test_golden_does_not_depend_on_the_current_verified_max(self):
        # si C4 sube VERIFIED_MAX, el golden sigue valiendo mientras 9.0.0 siga siendo posterior
        with mock.patch.object(ur, "VERIFIED_MAX", "3.5.0"):
            text = render(golden_calls(), generated=datetime.date(2026, 4, 1))
        self.assertEqual(text, GOLDEN_PROJECT_REPORT_TEMPLATE.replace("@VM@", "3.5.0"))

    def test_golden_changes_with_each_input(self):
        base = render(golden_calls(), generated=datetime.date(2026, 4, 1))
        self.assertNotEqual(render(golden_calls(), generated=datetime.date(2026, 4, 2)), base)
        self.assertNotEqual(render(golden_calls(), alias="p-00000000", generated=datetime.date(2026, 4, 1)), base)
        self.assertNotEqual(render(golden_calls()[:1], generated=datetime.date(2026, 4, 1)), base)


class ReportPurity(unittest.TestCase):
    """Todo lo que `render_project_report` puede alcanzar (funciones, clases y constantes del modulo, por
    nombre). Lista BLANCA y cerrada: un nombre nuevo hace fallar la prueba y obliga a revisarlo."""
    REACHABLE = frozenset((
        "render_project_report", "_header_section", "_summary_section", "_agent_sections", "_group_section",
        "_skills_section", "_version_section", "_quality_section", "_guide_section", "_footer_section",
        "_notices", "_window_text", "_versions_header", "_read_incidents", "_read_count", "_range_calls",
        "_bar", "_num", "_tenths", "_percent", "_plural", "_code", "_small", "_table",
        "_capped_table", "_raw_table", "_legend", "_read_info", "_unwarned_incidents", "_bullets", "_is_date",
        "_range_of", "_recent_codes", "is_unverified", "version_key", "LEGEND_SMALL", "READ_INCIDENT_LABELS",
        "READ_INFO_LABELS", "READ_WARNED",
        "ALIAS_RE", "BAR_EMPTY", "BAR_FULL", "BAR_WIDTH", "HOW_TO_READ", "KNOWN_WARNINGS", "LABEL_MAIN_READ",
        "MAX_CELL_CHARS", "MAX_SHOWN_VERSIONS", "MAX_TABLE_ROWS", "MAX_VERSION_ROWS", "MSG_REPORT_ALIAS",
        "MSG_REPORT_DATE", "MSG_REPORT_METRICS", "MSG_WINDOW_INVALID", "NOTE_DOUBTFUL_RANGE", "NOTE_NO_RANGE",
        "PRIVACY_NOTES", "REPORT_MARKER", "REPORT_SCHEMA", "SMALL_MARK", "TOOL_NAME", "UNKNOWN_WARNING",
        "REPEAT_LIMITATIONS", "SKILL_LIMITATIONS", "READ_QUALITY_LABELS", "SMALL_N", "VERIFIED_MAX",
        "RANGE_AFTER", "RANGE_BEFORE", "RANGE_DOUBTFUL", "RANGE_NONE", "_DOUBTFUL_FROM", "_DOUBTFUL_TO",
        "_VERSION_PARTS_RE", "WARN_ID_CAP", "WARN_ID_REPEATED", "WARN_NO_MESSAGE_ID",
        "WARN_SKILL_ID_CAP", "WARN_SKILL_ID_REPEATED", "WARN_MAIN_HARDLINK", "WARN_MAIN_CAP",
        "WARN_MAIN_UNREADABLE", "WARN_ALIAS_COLLISION", "_group_table", "_group_label", "_model_rows",
        "AGENT_GROUPS", "OTHER_GROUP", "NO_META_GROUP", "HIDDEN_COUNT_GROUPS", "PLUGIN_PREFIX_RE",
        # tipos de las metricas (isinstance)
        "UsageMetrics", "ScopeMetrics", "DataQuality", "Dist", "TokenStats", "SkillMetrics", "SkillQuality",
        "Window",
    ))
    CALLABLE_OK = frozenset((
        "ValueError", "any", "append", "astimezone", "dataclass", "date", "divmod", "groups", "int", "isinstance",
        "isoformat", "join", "len", "list", "match", "max", "min", "replace", "sorted", "sum", "tuple", "extend",
        "startswith", "get", "items",
        # parametro de `_model_rows`: la funcion pura que el llamador inyecta (`_global_model_label` o None)
        "label_of",
    ))

    def test_report_reaches_only_pure_code(self):
        helper = AggregationDeterminismAndPurity()
        tree = helper._module_tree()
        top = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                top[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        top[target.id] = node
        seen, todo = set(), ["render_project_report"]
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            for n in ast.walk(top[name]):
                if isinstance(n, ast.Name) and n.id in top:
                    todo.append(n.id)
        self.assertEqual(seen, set(self.REACHABLE))
        for name in AggregationDeterminismAndPurity.READER_IO_FUNCTIONS:
            self.assertNotIn(name, seen)
        for name in seen:
            node = top[name]
            if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                continue
            for n in ast.walk(node):
                self.assertNotIsInstance(n, (ast.Import, ast.ImportFrom), name)
                if isinstance(n, ast.Name):
                    self.assertNotIn(n.id, AggregationDeterminismAndPurity.FORBIDDEN, name)
                if isinstance(n, ast.Attribute):
                    self.assertNotIn(n.attr, AggregationDeterminismAndPurity.FORBIDDEN, name)
                if isinstance(n, ast.Call):
                    callee = n.func.id if isinstance(n.func, ast.Name) else (
                        n.func.attr if isinstance(n.func, ast.Attribute) else None)
                    self.assertIsNotNone(callee, name)
                    self.assertIn(callee, set(self.REACHABLE) | self.CALLABLE_OK, "%s llama a %s" % (name, callee))
        # `utc_today` (la unica que lee el reloj) no la alcanza el generador
        self.assertNotIn("utc_today", seen)


# --- T6: reporte global (texto Markdown, funcion pura) ---
G_DAY = datetime.date(2026, 4, 1)
PA, PB, PC = "p-aaaaaaa1", "p-bbbbbbb2", "p-ccccccc3"
GLOBAL_HEADINGS = [
    "## Resumen", "## Por conjunto", "## Llamadas por agente", "## Tokens por llamada",
    "## Duración y herramientas", "## Modelo real", "## Por proyecto", "## Skills",
    "## Versiones de Claude Code", "## Qué compara y qué no", "## Calidad de los datos",
    "## Cómo leer estos números", "## Pie",
]


def render_global(source, uses=None, **kw):
    """Agrega `source` (llamadas de TODOS los proyectos) y genera el reporte global."""
    if isinstance(source, ur.UsageMetrics):
        metrics = source
    else:
        metrics = agg(source, skill_uses=uses) if uses is not None else agg(source)
    return ur.render_global_report(metrics, **kw)


def global_calls():
    """Cinco llamadas, dos proyectos (PA, PB) y tres conjuntos.
    forge (PA, a1, 200 tokens, 60 s, 3 herramientas), scout (PA, a1, 20 tokens, 5 s), agente de plugin (PB, b1),
    agente de usuario (PB, b1) y otro agente de usuario (PA, a2), los tres con 20 tokens."""
    return [
        mk(1, project=PA, session="a1", input_tokens=100, output_tokens=50, cache_creation_tokens=20,
           cache_read_tokens=30, tools=3, **span(60)),
        mk(2, project=PA, session="a1", agent="scout", versions=("2.1.315",), tools=0, **span(5, hour=11)),
        mk(3, project=PB, session="b1", agent="plugin:pl", agent_group="plugin:pl", versions=("2.1.300",),
           **span(8, hour=12)),
        mk(4, project=PB, session="b1", agent="(otro agente)", agent_group="otros", **span(9, hour=13)),
        mk(5, project=PA, session="a2", agent="(otro agente)", agent_group="otros", **span(9, hour=14)),
    ]


def headings(text):
    return [line for line in text.split("\n") if line.startswith("## ")]


def section_of(text, title):
    """Cuerpo de la seccion `## title` hasta el siguiente `## `."""
    return text.split("\n## " + title + "\n")[1].split("\n## ")[0]


class GlobalAlias(unittest.TestCase):
    STRICT = re.compile(r"^p-[0-9a-f]{8}\Z")

    def test_alias_is_p_plus_eight_lowercase_hex_for_any_folder_name(self):
        for name in ("c--proj", "C--proj", "c--Users-me-My-Project", "", "a b", "café", "\udc80x",
                     "x" * 300, "../x", "c--" + "中"):
            with self.subTest(name=name):
                alias = ur._project_alias(name)
                self.assertRegex(alias, self.STRICT)
                self.assertTrue(ur.ALIAS_RE.match(alias))

    def test_alias_re_is_anchored_at_both_ends(self):
        for bad in ("p-0a1b2c3d\n", "xp-0a1b2c3d", "p-0a1b2c3d ", "p-0A1B2C3D", "p-0a1b2c3", "p-0a1b2c3d4",
                    "P-0a1b2c3d", "p_0a1b2c3d", "p-0a1b2c3g", "p-0a1b2c3d\r", ""):
            with self.subTest(alias=bad):
                self.assertIsNone(ur.ALIAS_RE.match(bad))
        self.assertTrue(ur.ALIAS_RE.match("p-0a1b2c3d"))

    def test_c_and_capital_c_give_the_same_alias_and_distinct_names_differ(self):
        self.assertEqual(ur._project_alias("c--proj"), ur._project_alias("C--proj"))
        self.assertEqual(ur._project_alias("c--Proj"), ur._project_alias("C--PROJ"))
        self.assertNotEqual(ur._project_alias("c--proj"), ur._project_alias("c--proj2"))
        # el alias no lleva el nombre ni la clave de la ejecucion: recalculable (hash sin sal)
        import hashlib
        self.assertEqual(ur._project_alias("c--proj"),
                         "p-" + hashlib.sha256(b"c--proj").hexdigest()[:8])


class GlobalReportShape(unittest.TestCase):
    def setUp(self):
        self.text = render_global(global_calls(), generated=G_DAY)

    def test_marker_title_and_section_order(self):
        lines = self.text.split("\n")
        self.assertEqual(lines[0], "<!-- synclayer-usage-report v1 -->")
        self.assertEqual(lines[1], "# Reporte global de uso de subagentes")
        self.assertEqual(headings(self.text), GLOBAL_HEADINGS)

    def test_bytes_utf8_without_bom_lf_and_final_newline(self):
        raw = self.text.encode("utf-8")
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", raw)
        self.assertTrue(self.text.endswith("\n"))
        self.assertFalse(self.text.endswith("\n\n"))
        self.assertEqual(raw.decode("utf-8"), self.text)

    def test_header_has_window_counts_versions_schema_privacy_and_no_project_alias_line(self):
        head = self.text.split("## Resumen")[0]
        self.assertIn("> - Ventana: 2026-03-02 a 2026-03-31 (UTC, ambos inclusive)", head)
        self.assertIn("> - Llamadas: 5 en 3 sesiones en 2 proyectos", head)
        self.assertIn("> - Claude Code: versiones `2.1.300` a `2.1.330` (3 versiones)", head)
        self.assertIn("> - Esquema del reporte: 1", head)
        self.assertIn("> - Generado: 2026-04-01", head)
        self.assertIn("proyectos numerados por volumen, sin nombres ni rutas ni alias", head)
        self.assertIn("privado por defecto", head)
        self.assertIn("no lo subas a git", head)
        self.assertIn("compártelo solo después de revisarlo", head)
        self.assertNotIn("p-<8 hex>", head)
        self.assertIn("AVISO: 1 llamada con versiones de Claude Code de 2.1.310 a 2.1.327", head)
        self.assertNotIn("proyecto " + PA, head)
        # sin fecha inyectada no hay linea de fecha (ni reloj)
        self.assertNotIn("Generado", render_global(global_calls()))

    def test_summary_counts_projects_and_groups(self):
        summary = section_of(self.text, "Resumen")
        self.assertIn("- Llamadas: 5 en 3 sesiones (1.7 llamadas por sesión)", summary)
        self.assertIn("- Proyectos con llamadas en la ventana: 2", summary)
        self.assertIn("- Conjuntos con llamadas: 3", summary)
        self.assertIn("- Agentes distintos (por nombre y conjunto): 4", summary)

    def test_group_table_by_hand(self):
        # SyncLayer: forge (200) y scout (20): mediana (20+200+1)//2 = 110, p90 200; duracion [60, 5] -> 33;
        # herramientas [3, 0] -> 2. otros: dos llamadas de 20 tokens y 9 s. plugin:pl: una llamada.
        block = table_with(self.text, "| Conjunto | Agentes | Llamadas | Barra")
        self.assertEqual(cells_of(block[0]), ["Conjunto", "Agentes", "Llamadas", "Barra", "Tokens/llamada (med.)",
                                              "p90", "Duración aprox. s (med.)", "Herramientas (med.)"])
        self.assertEqual([cells_of(line)[0] for line in block[2:]], ["`SyncLayer`", "`otros`", "`plugin:pl`"])
        self.assertEqual(cells_of(block[2]), ["`SyncLayer`", "2", "2", BAR_FULL * 10, "110 *", "200 *", "33 *", "2 *"])
        # `otros` (agentes de usuario): la columna `Agentes` no se muestra, revelaria cuantos agentes de usuario hay
        self.assertEqual(cells_of(block[3]), ["`otros`", "-", "2", BAR_FULL * 10, "20 *", "20 *", "9 *", "0 *"])
        self.assertEqual(cells_of(block[4]), ["`plugin:pl`", "1", "1", BAR_FULL * 5 + BAR_EMPTY * 5, "20 *", "20 *",
                                              "8 *", "0 *"])

    def test_group_detail_table_has_the_comparable_columns_by_hand(self):
        block = table_with(self.text, "| Conjunto | Sesiones")
        self.assertEqual(cells_of(block[0]), [
            "Conjunto", "Sesiones", "Llamadas/sesión", "n", "Tokens (suma)", "Duración aprox. s (p90)",
            "Herramientas (p90)", "Repeticiones (inferido)", "Repeticiones (% de llamadas)"])
        # SyncLayer: 1 sesion (a1), 2 llamadas -> 2.0; n 2; suma 220; p90 de duracion 60 y de herramientas 3
        self.assertEqual(cells_of(block[2]), ["`SyncLayer`", "1", "2.0", "2 *", "220", "60 *", "3 *", "0", "0 %"])
        # otros: sesiones b1 y a2 -> 2 sesiones, 1.0 llamadas por sesion
        self.assertEqual(cells_of(block[3]), ["`otros`", "2", "1.0", "2 *", "40", "9 *", "0 *", "0", "0 %"])

    def test_repetitions_are_a_count_and_a_percentage_of_the_calls(self):
        calls = [mk(1, project=PA, session="a1", **span(10, hour=9)), mk(2, project=PA, session="a1", **span(10, hour=10)),
                 mk(3, project=PA, session="a1", agent="scout", **span(10, hour=11)),
                 mk(4, project=PA, session="a1", agent="scout", **span(10, hour=12))]
        block = table_with(render_global(calls), "| Conjunto | Sesiones")
        # forge repite una vez y scout otra: 2 de 4 llamadas del conjunto SyncLayer
        self.assertEqual(cells_of(block[2])[-2:], ["2", "50 %"])

    def test_agent_tables_all_carry_the_group_column(self):
        for start in ("| Agente | Conjunto | Llamadas", "| Agente | Conjunto | n |", "| Agente | Conjunto | Duración",
                      "| Agente | Conjunto | Modelo"):
            block = table_with(self.text, start)
            self.assertEqual(len({columns(line) for line in block}), 1)
        calls = table_with(self.text, "| Agente | Conjunto | Llamadas")
        self.assertEqual(cells_of(calls[0]), ["Agente", "Conjunto", "Llamadas", "Barra", "Sesiones", "Llamadas/sesión",
                                              "Repeticiones (inferido)"])

    def test_two_other_agent_rows_in_different_groups_stay_apart(self):
        calls = [mk(1, project=PA, agent="(otro agente)", agent_group="otros"),
                 mk(2, project=PA, session="s2", agent="(otro agente)", agent_group="plugin:(no-valido)")]
        text = render_global(calls)
        block = table_with(text, "| Agente | Conjunto | Llamadas")
        self.assertEqual([cells_of(line)[:2] for line in block[2:]],
                         [["`(otro agente)`", "`otros`"], ["`(otro agente)`", "`plugin:(no-valido)`"]])
        self.assertIn("- Agentes distintos (por nombre y conjunto): 2", text)

    def test_project_table_by_hand_with_aliases_only(self):
        block = table_with(self.text, "| Proyecto")
        self.assertEqual(cells_of(block[0]), ["Proyecto", "Sesiones", "Llamadas", "Barra", "Tokens (suma)"])
        # PA: sesiones a1 y a2, llamadas 1, 2 y 5, tokens 200 + 20 + 20; PB: b1, llamadas 3 y 4, 20 + 20.
        # Barra de PB: 2 de 3 = 6,67 -> 7 bloques
        self.assertEqual(cells_of(block[2]), ["`proyecto 1`", "2", "3", BAR_FULL * 10, "240"])
        self.assertEqual(cells_of(block[3]), ["`proyecto 2`", "1", "2", BAR_FULL * 7 + BAR_EMPTY * 3, "40"])
        # el global no imprime ningun alias `p-` + 8 hexadecimales (ni los de las metricas ni uno inventado)
        self.assertEqual(re.findall(r"p-[0-9a-f]{8}", self.text), [])
        self.assertNotIn("p-<8 hex>", self.text)

    def test_every_table_has_one_column_count_per_row(self):
        for block in md_tables(self.text):
            self.assertEqual(len({columns(line) for line in block}), 1, block[0])

    def test_version_section_has_the_three_ranges_and_the_doubtful_one_is_flagged(self):
        versions = section_of(self.text, "Versiones de Claude Code")
        self.assertIn("| `<2.1.310` | 1 |", versions)
        self.assertIn("| `2.1.310-2.1.327` | 1 |", versions)
        self.assertIn("| `>=2.1.328` | 3 |", versions)
        self.assertIn("dudoso: tokens posiblemente inflados", versions)
        self.assertIn("Comparar entre rangos es solo indicativo.", versions)

    def test_footer_has_schema_tool_verified_max_and_scope(self):
        foot = self.text.split("## Pie")[1]
        self.assertIn("- report_schema: 1", foot)
        self.assertIn("- herramienta: tools/usage_report.py", foot)
        self.assertIn("- ultima_version_verificada: `%s`" % ur.VERIFIED_MAX, foot)
        self.assertIn("- alcance: global (todos los proyectos leídos)", foot)
        self.assertNotIn("- proyecto:", foot)


class GlobalComparison(unittest.TestCase):
    ONE = "no hay con qué comparar"

    def test_a_single_group_says_there_is_nothing_to_compare_with(self):
        text = render_global([mk(1, project=PA), mk(2, project=PB, session="s2")])
        self.assertIn(self.ONE, section_of(text, "Por conjunto"))
        self.assertIn("- Conjuntos con llamadas: 1", text)

    def test_two_or_more_groups_do_not_say_it(self):
        self.assertNotIn(self.ONE, render_global(global_calls()))

    def test_no_calls_does_not_claim_a_single_group(self):
        self.assertNotIn(self.ONE, render_global([]))

    @staticmethod
    def no_meta(n, **kw):
        return mk(n, project=PA, session="s%d" % n, agent="(sin-meta)", agent_group="sin-meta", has_meta=False,
                  status="sin_meta", **kw)

    def test_sin_meta_is_not_a_group_of_agents_for_the_count_the_comparison_and_the_ratio(self):
        # un conjunto real y muchas llamadas sin meta: no hay con que comparar; `sin-meta` no cuenta como conjunto
        text = render_global([mk(1, project=PA)] + [self.no_meta(10 + i) for i in range(30)])
        self.assertIn(self.ONE, section_of(text, "Por conjunto"))
        self.assertIn("- Conjuntos con llamadas: 1", text)
        self.assertNotIn("volúmenes muy distintos", section_of(text, "Por conjunto"))
        # la fila existe (las llamadas son reales) y el texto explica por que no es un conjunto
        block = table_with(text, "| Conjunto | Agentes | Llamadas | Barra")
        self.assertEqual([cells_of(line)[0] for line in block[2:]], ["`sin-meta`", "`SyncLayer`"])
        self.assertIn("`sin-meta` reúne las llamadas sin archivo meta: no es un conjunto de agentes",
                      section_of(text, "Por conjunto"))
        # con dos conjuntos reales y el mismo volumen, 30 llamadas sin meta no disparan el aviso de volumenes
        two = render_global([mk(1, project=PA), mk(2, project=PA, session="z", agent="(otro agente)",
                                                   agent_group="otros")] + [self.no_meta(10 + i) for i in range(30)])
        self.assertNotIn(self.ONE, section_of(two, "Por conjunto"))
        self.assertNotIn("volúmenes muy distintos", section_of(two, "Por conjunto"))
        self.assertIn("- Conjuntos con llamadas: 2", two)

    def test_only_sin_meta_calls_say_neither_a_single_group_nor_a_count(self):
        text = render_global([self.no_meta(1), self.no_meta(2)])
        self.assertNotIn(self.ONE, text)
        self.assertIn("- Conjuntos con llamadas: 0", text)

    def test_the_sin_meta_line_only_shows_when_there_are_sin_meta_calls(self):
        self.assertNotIn("reúne las llamadas sin archivo meta", render_global(global_calls()))

    def test_very_different_volumes_get_a_note_from_ten_to_one(self):
        many = [mk(i, project=PA, session="s%d" % i) for i in range(10)]
        other = [mk(100, project=PA, session="z", agent="(otro agente)", agent_group="otros")]
        text = render_global(many + other)
        self.assertIn("volúmenes muy distintos (de 1 a 10 llamadas)", section_of(text, "Por conjunto"))
        nine = render_global(many[:9] + other)
        self.assertNotIn("volúmenes muy distintos", section_of(nine, "Por conjunto"))

    def test_group_by_version_range_table_flags_the_doubtful_range_and_skips_empty_ones(self):
        block = table_with(render_global(global_calls()), "| Conjunto | Rango")
        self.assertEqual(cells_of(block[0]), ["Conjunto", "Rango", "Llamadas", "n", "Mediana", "p90", "Nota"])
        rows = {tuple(cells_of(line)[:2]): cells_of(line) for line in block[2:]}
        self.assertEqual(set(rows), {("`SyncLayer`", "`2.1.310-2.1.327`"), ("`SyncLayer`", "`>=2.1.328`"),
                                     ("`otros`", "`>=2.1.328`"), ("`plugin:pl`", "`<2.1.310`")})
        doubtful = rows[("`SyncLayer`", "`2.1.310-2.1.327`")]
        self.assertEqual(doubtful[2:6], ["1", "1 *", "20 *", "20 *"])
        self.assertIn("dudoso: tokens posiblemente inflados", doubtful[6])
        self.assertEqual(rows[("`otros`", "`>=2.1.328`")][6], "")

    def test_group_without_token_stats_shows_dashes(self):
        text = render_global([no_usage(1, project=PA), mk(2, project=PA, session="s2", agent="(otro agente)",
                                                          agent_group="otros")])
        block = table_with(text, "| Conjunto | Agentes | Llamadas | Barra")
        self.assertEqual(cells_of(block[2])[4:6], ["-", "-"])

    def test_every_table_with_a_star_has_the_legend_and_no_other_does(self):
        text = render_global(global_calls())
        tables = ReportSmallSampleLegend.tables_with_legend(text)
        self.assertGreaterEqual(sum(1 for _, marked, _ in tables if marked), 5)
        for head, marked, legend in tables:
            self.assertEqual(marked, legend, head)
        self.assertEqual(text.count(ReportSmallSampleLegend.LEGEND), sum(1 for _, marked, _ in tables if marked))
        big = render_global([mk(i, project=PA, session="s%d" % i) for i in range(10)]
                            + [mk(100 + i, project=PA, session="t%d" % i, agent="(otro agente)", agent_group="otros")
                               for i in range(10)])
        self.assertNotIn("pocas muestras", big.split("## Cómo leer")[0])


class GlobalGroupsAndModels(unittest.TestCase):
    @staticmethod
    def tokens(n, project, value, **kw):
        return mk(n, project=project, session="s%d" % n, input_tokens=0, output_tokens=value, cache_creation_tokens=0,
                  cache_read_tokens=0, **kw)

    def test_a_group_spread_over_several_projects_is_measured_over_all_its_calls(self):
        # SyncLayer: [10, 20, 30] en PA y [1000] en PB. Sobre las 4 llamadas: mediana (20+30)/2 = 25, p90 = la 4.a = 1000.
        # Promediar por proyecto daria (20 + 1000)/2 = 510 de mediana
        calls = [self.tokens(1, PA, 10), self.tokens(2, PA, 20), self.tokens(3, PA, 30), self.tokens(4, PB, 1000)]
        text = render_global(calls)
        row = cells_of(table_with(text, "| Conjunto | Agentes | Llamadas | Barra")[2])
        self.assertEqual(row, ["`SyncLayer`", "1", "4", BAR_FULL * 10, "25 *", "1000 *", "10 *", "0 *"])
        detail = cells_of(table_with(text, "| Conjunto | Sesiones")[2])
        self.assertEqual(detail[:5], ["`SyncLayer`", "4", "1.0", "4 *", "1060"])
        agent = cells_of(table_with(text, "| Agente | Conjunto | n |")[2])
        self.assertEqual(agent[5:7], ["25 *", "1000 *"])
        # los proyectos siguen separados en su tabla: PA tiene tres llamadas y PB una
        projects = table_with(text, "| Proyecto")
        self.assertEqual([cells_of(line)[2] for line in projects[2:]], ["3", "1"])

    def test_agents_column_hides_the_count_of_user_and_unknown_groups_only(self):
        calls = [mk(1, project=PA, agent="forge", agent_group="SyncLayer", agent_key="a"),
                 mk(2, project=PA, session="s2", agent="scout", agent_group="SyncLayer", agent_key="b"),
                 mk(3, project=PA, session="s3", agent="(otro agente)", agent_group="otros", agent_key="c"),
                 mk(4, project=PA, session="s4", agent="(otro agente)", agent_group="otros", agent_key="d"),
                 mk(5, project=PA, session="s5", agent="(otro agente)", agent_group="plugin:(no-valido)",
                    agent_key="e"),
                 mk(6, project=PA, session="s6", agent="Explore", agent_group="integrado", agent_key="f"),
                 mk(7, project=PA, session="s7", agent="plugin:pl", agent_group="plugin:pl", agent_key="g"),
                 mk(8, project=PA, session="s8", agent="plugin:pl", agent_group="plugin:pl", agent_key="h"),
                 mk(9, project=PA, session="s9", agent="x", agent_group="ZZ-raro", agent_key="i")]
        block = table_with(render_global(calls), "| Conjunto | Agentes | Llamadas | Barra")
        shown = {cells_of(line)[0]: cells_of(line)[1] for line in block[2:]}
        self.assertEqual(shown, {"`SyncLayer`": "2", "`otros`": "-", "`plugin:(no-valido)`": "-", "`integrado`": "1",
                                 "`plugin:pl`": "2", "`(otro conjunto)`": "-"})

    def test_the_project_report_keeps_its_agents_column(self):
        calls = [mk(1, agent="(otro agente)", agent_group="otros", agent_key="c"),
                 mk(2, session="s2", agent="(otro agente)", agent_group="otros", agent_key="d")]
        block = table_with(render(calls), "| Conjunto | Agentes | Llamadas | Barra")
        self.assertEqual(cells_of(block[2])[:2], ["`otros`", "2"])

    def test_an_unknown_group_label_never_prints_in_any_agent_or_group_table(self):
        raw = "ZZMARK-g|\n## G"
        calls = [mk(1, project=PA, agent="forge", agent_group=raw), mk(2, project=PA, session="s2")]
        text = render_global(calls)
        self.assertNotIn("ZZMARK", text)
        for start in ("| Agente | Conjunto | Llamadas", "| Agente | Conjunto | n |", "| Agente | Conjunto | Duración",
                      "| Agente | Conjunto | Modelo", "| Conjunto | Agentes | Llamadas", "| Conjunto | Sesiones",
                      "| Conjunto | Rango"):
            block = table_with(text, start)
            self.assertTrue(any("`(otro conjunto)`" in line for line in block), start)
        # el reporte de proyecto aplica el mismo mapeo
        self.assertNotIn("ZZMARK", render(calls))

    def test_group_label_maps_the_closed_lists_and_valid_plugin_prefixes_and_nothing_else(self):
        for label in ("SyncLayer", "integrado", "otros", "plugin:(no-valido)", "sin-meta", "plugin:pl", "plugin:a-1"):
            self.assertEqual(ur._group_label(label), label)
        for raw in ("ZZ", "plugin:", "plugin:Mayus", "plugin:x" + "y" * 40, "plugin:a b", None, 5, "", "plugin:x\n"):
            self.assertEqual(ur._group_label(raw), ur.OTHER_GROUP, repr(raw))

    def test_model_ids_outside_the_closed_pieces_print_as_other_model_in_the_global_only(self):
        merger = "claude-sonnet-acme-merger-q3"
        calls = [mk(1, project=PA, model=merger), mk(2, project=PA, session="s2", model="claude-sonnet-acme-x"),
                 mk(3, project=PA, session="s3", model="claude-opus-4-1-20250805")]
        text = render_global(calls)
        self.assertNotIn("acme", text)
        block = table_with(text, "| Agente | Conjunto | Modelo")
        # los dos ids fuera de la lista cerrada son UNA fila `(otro modelo)` con sus llamadas sumadas
        self.assertEqual([cells_of(line)[2:] for line in block[2:]],
                         [["`(otro modelo)`", "2"], ["`claude-opus-4-1-20250805`", "1"]])
        # el reporte de proyecto conserva el patron amplio (y lo advierte en el pie)
        self.assertIn(merger, render(calls))

    def test_global_model_label_accepts_family_numbers_date_and_latest_only(self):
        for ok in ("claude-opus-4-1", "claude-opus-4-1-20250805", "claude-3-5-sonnet-20241022", "claude-3-7-sonnet-latest",
                   "claude-haiku-4-5", "claude-sonnet-4.5", "claude-opus-4-5@20251101", "claude-fable-5-2",
                   "claude-instant-1.2", "opus", "sonnet", "haiku", "fable", "(otro modelo)"):
            self.assertEqual(ur._global_model_label(ok), ok, ok)
        for bad in ("claude-sonnet-acme-merger-q3", "claude-opus-4-1-ZZ", "claude-sonnet-4-latestx", "claude-opus-4-1[1m]",
                    "claude-sonnet-4-5-thinking", "<synthetic>", "inherit", "gpt-4", "claude-", "claude-opus-123",
                    "claude-opus-4-1-2025080", "claude-opus-4-1\n", None, 5, "", "claude-" + "opus-1-" * 20):
            self.assertEqual(ur._global_model_label(bad), "(otro modelo)", repr(bad))


class GlobalProjects(unittest.TestCase):
    def test_row_cap_with_note_and_omitted_calls(self):
        total = ur.MAX_TABLE_ROWS + 5
        calls = [mk(i, project="p-%08x" % i, session="s%d" % i) for i in range(total)]
        text = render_global(calls)
        block = table_with(text, "| Proyecto")
        self.assertEqual(len(block) - 2, ur.MAX_TABLE_ROWS)
        projects = section_of(text, "Por proyecto")
        self.assertIn("Se muestran las %d primeras filas de %d." % (ur.MAX_TABLE_ROWS, total), projects)
        self.assertIn("Las 5 filas omitidas suman 5 llamadas.", projects)
        self.assertIn("- Proyectos con llamadas en la ventana: %d" % total, text)

    def test_thousands_of_projects_stay_bounded(self):
        calls = [mk(i, project="p-%08x" % i, session="s%d" % i) for i in range(3000)]
        text = render_global(calls)
        self.assertEqual(len(table_with(text, "| Proyecto")) - 2, ur.MAX_TABLE_ROWS)
        self.assertIn("Las 2960 filas omitidas suman 2960 llamadas.", text)
        self.assertLess(len(text), 60_000)

    def test_no_row_cap_note_below_the_cap(self):
        self.assertNotIn("filas omitidas", render_global(global_calls()))

    def test_no_alias_whatever_it_looks_like_ever_prints(self):
        # el global numera los proyectos (`proyecto N`) y no imprime ningun alias: ni uno valido ni uno hostil
        base = agg(global_calls())
        hostile = ("c--Users-ZZMARK-proj", "p-0a1b2c3d\n", "x|y\n## Inyectado", "p-ZZ", "", None, 5, "..\\x",
                   "p-0a1b2c3d")
        projects = tuple(ur.ProjectMetrics(h, base.projects[0].metrics) for h in hostile) + base.projects
        text = ur.render_global_report(dataclasses.replace(base, projects=projects))
        self.assertNotIn("ZZMARK", text)
        self.assertNotIn("Inyectado", text)
        self.assertNotIn("alias no valido", text)
        self.assertEqual(re.findall(r"p-[0-9a-f]{8}", text), [])
        block = table_with(text, "| Proyecto")
        self.assertEqual([cells_of(line)[0] for line in block[2:]],
                         ["`proyecto %d`" % n for n in range(1, len(hostile) + 3)])
        for table in md_tables(text):
            self.assertEqual(len({columns(line) for line in table}), 1, table[0])

    def test_a_project_with_zero_calls_is_a_row_of_zeros_with_an_empty_bar(self):
        # `aggregate_calls` nunca crea un proyecto sin llamadas; el generador, si se lo pasan, lo tolera
        base = agg(global_calls())
        zero = ur.ProjectMetrics(PC, agg([]).total)
        text = ur.render_global_report(dataclasses.replace(base, projects=base.projects + (zero,)))
        block = table_with(text, "| Proyecto")
        self.assertEqual(cells_of(block[-1]), ["`proyecto 3`", "0", "0", BAR_EMPTY * 10, "0"])

    def test_projects_are_numbered_by_calls_then_sessions_then_tokens_and_never_by_alias(self):
        # PA "p-aaaaaaa1" < PB < PC en orden de alias; el numero sigue los valores visibles, no el alias
        calls = [mk(1, project=PA, session="s1"),
                 mk(2, project=PB, session="s1"), mk(3, project=PB, session="s2"),
                 mk(4, project=PC, session="s1", input_tokens=1000), mk(5, project=PC, session="s1")]
        block = table_with(render_global(calls), "| Proyecto")
        rows = [cells_of(line) for line in block[2:]]
        # PB: 2 llamadas y 2 sesiones (1.o); PC: 2 llamadas, 1 sesion (2.o); PA: 1 llamada (3.o)
        self.assertEqual([r[:3] for r in rows], [["`proyecto 1`", "2", "2"], ["`proyecto 2`", "1", "2"],
                                                  ["`proyecto 3`", "1", "1"]])
        # mismas llamadas y sesiones: manda la suma de tokens (visible); PA tiene el alias menor
        tie = [mk(1, project=PA, session="s1"), mk(2, project=PB, session="s1", input_tokens=500)]
        rows = [cells_of(line) for line in table_with(render_global(tie), "| Proyecto")[2:]]
        self.assertEqual([r[-1] for r in rows], ["510", "20"])

    def test_tied_projects_give_the_same_bytes_whatever_their_aliases(self):
        # empatadas en todo lo visible, las filas son identicas: el orden por alias no se nota
        def calls(a, b):
            return [mk(1, project=a, session="s1"), mk(2, project=b, session="s2")]
        base = render_global(calls(PA, PB), generated=G_DAY)
        self.assertEqual(render_global(calls(PB, PA), generated=G_DAY), base)
        self.assertEqual(render_global(calls("p-00000000", "p-ffffffff"), generated=G_DAY), base)

    def test_the_project_numbering_is_the_same_for_the_same_folders_read_in_any_order(self):
        block = table_with(render_global(list(reversed(global_calls()))), "| Proyecto")
        self.assertEqual([cells_of(line)[:3] for line in block[2:]], [["`proyecto 1`", "2", "3"],
                                                                      ["`proyecto 2`", "1", "2"]])

    def test_huge_values_print_whole(self):
        big = 10 ** 18
        text = render_global([mk(1, project=PA, input_tokens=big)])
        block = table_with(text, "| Proyecto")
        self.assertEqual(cells_of(block[2])[-1], str(big + 10))
        self.assertIn(str(big + 10), text)
        self.assertNotRegex(text, r"\d,\d{3}")

    def test_numbering_note_and_the_fixed_line_about_projects_that_do_not_appear(self):
        projects = section_of(render_global(global_calls()), "Por proyecto")
        self.assertIn("numerados por volumen de llamadas, de más a menos (desempate por sesiones y luego por tokens)",
                      projects)
        self.assertIn("La numeración puede cambiar entre ejecuciones y no coincide con el alias del reporte de proyecto.",
                      projects)
        self.assertIn("Un proyecto leído con todas sus llamadas fuera de la ventana, o solo con skills, no aparece.",
                      projects)
        self.assertNotIn("hash", projects)
        self.assertNotIn("p-<8 hex>", projects)

    def test_a_project_read_only_for_skills_or_outside_the_window_does_not_appear(self):
        # `aggregate_calls` solo crea un proyecto con llamadas dentro de la ventana
        far = mk(2, project=PB, session="b1", start=dt(5, 10, month=1), end=dt(5, 10, 0, 10, month=1))
        text = render_global([mk(1, project=PA), far], uses=[su(1, project=PC)])
        block = table_with(text, "| Proyecto")
        self.assertEqual([cells_of(line)[:3] for line in block[2:]], [["`proyecto 1`", "1", "1"]])
        self.assertIn("- Proyectos con llamadas en la ventana: 1", text)


class GlobalSkills(unittest.TestCase):
    @staticmethod
    def skills(text):
        return section_of(text, "Skills")

    def test_user_skill_names_never_print_and_group_as_other_skill(self):
        # tres invocaciones de dos skills de usuario en dos sesiones: una sola fila, con las sesiones del conjunto
        # (2: la suma de las sesiones de cada skill daria 3)
        uses = [su(1, skill="alfa", session="s1"), su(2, skill="beta", session="s1"),
                su(3, skill="alfa", session="s2")]
        text = render_global([mk(1, project=PA)], uses=uses)
        section = self.skills(text)
        self.assertNotIn("alfa", text)
        self.assertNotIn("beta", text)
        tables = md_tables(section)
        self.assertEqual(tables[0][2], "| `(otra skill)` | `otros` | 3 | " + BAR_FULL * 10 + " | 2 | 3 | 0 |")
        self.assertEqual(len(tables[0]), 3)
        # `Skills` no se muestra (`-`): dira cuantas skills de usuario distintas hay (aqui 2: alfa y beta)
        self.assertEqual(tables[1][2], "| `otros` | - | 3 | 2 |")      # 3 invocaciones, 2 sesiones
        self.assertIn("se agrupan como `(otra skill)`", section)

    def test_closed_list_skills_show_by_name(self):
        uses = [su(1, skill="review", group="integrado"), su(2, skill="propia", group="SyncLayer"),
                su(3, skill="alfa")]
        with mock.patch.object(ur, "BUILTIN_SKILLS", frozenset(("review",))), \
                mock.patch.object(ur, "SYNCLAYER_SKILLS", frozenset(("propia",))):
            text = render_global([mk(1, project=PA)], uses=uses)
        tables = md_tables(self.skills(text))
        names = [cells_of(line)[:2] for line in tables[0][2:]]
        self.assertEqual(sorted(names), [["`(otra skill)`", "`otros`"], ["`propia`", "`SyncLayer`"],
                                         ["`review`", "`integrado`"]])
        self.assertNotIn("alfa", text)

    def test_a_name_outside_the_closed_list_in_a_closed_group_is_grouped(self):
        # defensa: un nombre que la lista cerrada no conoce no sale aunque venga en el conjunto `integrado`
        sk = ur.skill_metrics([su(1, skill="secreta", group="integrado")], ur.make_window(TODAY))
        text = ur.render_global_report(dataclasses.replace(agg([mk(1, project=PA)]), skills=sk))
        self.assertNotIn("secreta", text)
        self.assertIn("| `(otra skill)` | `integrado` | 1 |", text)

    PLUGIN_AGENT = dict(agent="plugin:pl", agent_group="plugin:pl")

    def test_plugin_prefix_shows_only_when_it_also_appeared_as_an_agent_and_the_footer_says_so(self):
        uses = [su(1, skill="plugin:pl", group="plugin:pl", session="s1"),
                su(2, skill="plugin:pl", group="plugin:pl", session="s2")]
        text = render_global([mk(1, project=PA, **self.PLUGIN_AGENT)], uses=uses)
        self.assertIn("| `plugin:pl` | `plugin:pl` | 2 |", self.skills(text))
        foot = text.split("## Pie")[1]
        self.assertIn("El prefijo de una skill de plugin sale de texto que escribe el modelo: solo se muestra si ese"
                      " prefijo también apareció como agente en esta lectura; el resto se agrupa como"
                      " `plugin:(otro)`.", foot)
        self.assertNotIn("nombres de plugins privados", text)
        self.assertNotIn("sale tal cual en los agentes y en las skills", text)

    def test_a_plugin_prefix_seen_only_in_a_skill_groups_as_plugin_other(self):
        # `zzsecreto` y `otro-p` solo salen como prefijo de skill (texto que escribe el modelo): no se muestran
        uses = [su(1, skill="plugin:zzsecreto", group="plugin:zzsecreto", session="s1"),
                su(2, skill="plugin:otro-p", group="plugin:otro-p", session="s2"),
                su(3, skill="plugin:pl", group="plugin:pl", session="s2")]
        text = render_global([mk(1, project=PA, **self.PLUGIN_AGENT)], uses=uses)
        section = self.skills(text)
        self.assertNotIn("zzsecreto", text)
        self.assertNotIn("otro-p", text)
        tables = md_tables(section)
        # las dos skills de prefijo no visto son UNA fila, con las invocaciones sumadas y las sesiones desconocidas
        self.assertEqual(sorted(cells_of(line)[:3] for line in tables[0][2:]),
                         [["`(otra skill)`", "`plugin:(otro)`", "2"], ["`plugin:pl`", "`plugin:pl`", "1"]])
        self.assertEqual(cells_of(tables[0][2])[4], "-")
        by_group = {cells_of(line)[0]: cells_of(line) for line in tables[1][2:]}
        self.assertEqual(set(by_group), {"`plugin:(otro)`", "`plugin:pl`"})
        self.assertEqual(by_group["`plugin:(otro)`"], ["`plugin:(otro)`", "-", "2", "-"])
        self.assertEqual(by_group["`plugin:pl`"][1:], ["1", "1", "1"])

    def test_a_plugin_prefix_that_only_an_agent_invoking_skills_revealed_also_counts_as_seen(self):
        # el agente `plugin:pl` no tiene llamadas propias en la ventana, pero invoco una skill: su conjunto se vio
        uses = [su(1, skill="plugin:pl", group="plugin:pl", origin="subagente", **self.PLUGIN_AGENT)]
        text = render_global([mk(1, project=PA)], uses=uses)
        self.assertIn("| `plugin:pl` | `plugin:pl` | 1 |", self.skills(text))

    def test_the_by_agent_table_follows_the_same_plugin_rule(self):
        fa = dict(agent="forge", agent_group="SyncLayer", origin="subagente")
        uses = [su(1, skill="plugin:zz", group="plugin:zz", **fa), su(2, skill="plugin:pl", group="plugin:pl", **fa)]
        text = render_global([mk(1, project=PA, **self.PLUGIN_AGENT)], uses=uses)
        self.assertNotIn("plugin:zz", text)
        tables = md_tables(self.skills(text))
        self.assertEqual(sorted(tables[2][2:]), ["| `forge` | `SyncLayer` | `(otra skill)` | 1 |",
                                                 "| `forge` | `SyncLayer` | `plugin:pl` | 1 |"])

    def test_hostile_group_label_does_not_print(self):
        rows = (ur.SkillRow("x", "ZZMARK-g|\n## I", 2, 2, 0, 1),)
        groups = (ur.SkillGroupRow("ZZMARK-g|\n## I", 1, 2, 1),)
        sk = ur.SkillMetrics(calls=2, sessions=1, main_calls=2, subagent_calls=0, rows=rows, groups=groups,
                             by_agent=(), quality=ur.SkillQuality(2, 2, 0, 0, 0))
        text = ur.render_global_report(dataclasses.replace(agg([mk(1, project=PA)]), skills=sk))
        self.assertNotIn("ZZMARK", text)
        self.assertNotIn("\n## I", text)
        self.assertIn("`(otro conjunto)`", text)

    def test_two_hostile_groups_are_one_row_and_one_group_not_two_identical_ones(self):
        rows = (ur.SkillRow("x", "ZZ-uno", 2, 2, 0, 1), ur.SkillRow("y", "ZZ-dos", 3, 1, 2, 2))
        groups = (ur.SkillGroupRow("ZZ-uno", 1, 2, 1), ur.SkillGroupRow("ZZ-dos", 1, 3, 2))
        sk = ur.SkillMetrics(calls=5, sessions=2, main_calls=3, subagent_calls=2, rows=rows, groups=groups,
                             by_agent=(ur.SkillAgentRow("forge", "SyncLayer", "x", "ZZ-uno", 1),
                                       ur.SkillAgentRow("forge", "SyncLayer", "y", "ZZ-dos", 2)),
                             quality=ur.SkillQuality(5, 5, 0, 0, 0))
        text = ur.render_global_report(dataclasses.replace(agg([mk(1, project=PA)]), skills=sk))
        tables = md_tables(self.skills(text))
        self.assertEqual(tables[0][2], "| `(otra skill)` | `(otro conjunto)` | 5 | " + BAR_FULL * 10 + " | - | 3 | 2 |")
        self.assertEqual(len(tables[0]), 3)
        self.assertEqual(tables[1][2:], ["| `(otro conjunto)` | - | 5 | - |"])
        self.assertEqual(tables[2][2:], ["| `forge` | `SyncLayer` | `(otra skill)` | 3 |"])

    def test_subset_merge_without_a_known_session_count_prints_a_dash(self):
        # el conjunto `integrado` mezcla una skill de la lista cerrada y una fuera de ella: las sesiones del
        # subconjunto agrupado no se conocen (no se suman las del conjunto)
        rows = (ur.SkillRow("review", "integrado", 2, 2, 0, 1), ur.SkillRow("zeta", "integrado", 1, 1, 0, 1))
        groups = (ur.SkillGroupRow("integrado", 2, 3, 2),)
        sk = ur.SkillMetrics(calls=3, sessions=2, main_calls=3, subagent_calls=0, rows=rows, groups=groups,
                             by_agent=(), quality=ur.SkillQuality(3, 3, 0, 0, 0))
        with mock.patch.object(ur, "BUILTIN_SKILLS", frozenset(("review",))):
            text = ur.render_global_report(dataclasses.replace(agg([mk(1, project=PA)]), skills=sk))
        tables = md_tables(self.skills(text))
        self.assertEqual(tables[0][2], "| `review` | `integrado` | 2 | " + BAR_FULL * 10 + " | 1 | 2 | 0 |")
        self.assertEqual(tables[0][3], "| `(otra skill)` | `integrado` | 1 | " + BAR_FULL * 5 + BAR_EMPTY * 5
                         + " | - | 1 | 0 |")
        # el conjunto mezcla nombres ocultos: su columna `Skills` (2) revelaria cuantos hay
        self.assertEqual(tables[1][2], "| `integrado` | - | 3 | 2 |")

    def test_a_group_whose_names_all_show_keeps_its_skill_count(self):
        rows = (ur.SkillRow("review", "integrado", 2, 2, 0, 1), ur.SkillRow("init", "integrado", 1, 1, 0, 1))
        groups = (ur.SkillGroupRow("integrado", 2, 3, 2),)
        sk = ur.SkillMetrics(calls=3, sessions=2, main_calls=3, subagent_calls=0, rows=rows, groups=groups,
                             by_agent=(), quality=ur.SkillQuality(3, 3, 0, 0, 0))
        with mock.patch.object(ur, "BUILTIN_SKILLS", frozenset(("review", "init"))):
            text = ur.render_global_report(dataclasses.replace(agg([mk(1, project=PA)]), skills=sk))
        self.assertEqual(md_tables(self.skills(text))[1][2], "| `integrado` | 2 | 3 | 2 |")

    def test_by_agent_table_hides_user_skill_names_and_merges_rows(self):
        fa = dict(agent="forge", agent_group="SyncLayer", origin="subagente")
        uses = [su(1, skill="alfa", **fa), su(2, skill="beta", **fa), su(3, skill="plugin:pl", group="plugin:pl", **fa)]
        text = render_global([mk(1, project=PA, **self.PLUGIN_AGENT)], uses=uses)
        tables = md_tables(self.skills(text))
        self.assertEqual(tables[2][0], "| Agente | Conjunto del agente | Skill | Invocaciones |")
        self.assertEqual(tables[2][2:], ["| `forge` | `SyncLayer` | `(otra skill)` | 2 |",
                                         "| `forge` | `SyncLayer` | `plugin:pl` | 1 |"])
        self.assertNotIn("alfa", text)

    def test_no_skills_prints_a_line_and_the_no_tokens_note(self):
        section = self.skills(render_global(global_calls()))
        self.assertIn("Sin invocaciones de skills en la ventana", section)
        self.assertNotIn("|", section)
        self.assertIn("No se atribuyen tokens a una skill", section)

    def test_skill_tables_are_capped(self):
        total = ur.MAX_TABLE_ROWS + 3
        uses = [su(i, skill="plugin:p%d" % i, group="plugin:p%d" % i, session="s%d" % i) for i in range(total)]
        calls = [mk(i, project=PA, session="s%d" % i, agent="plugin:p%d" % i, agent_group="plugin:p%d" % i)
                 for i in range(total)]
        section = self.skills(render_global(calls, uses=uses))
        self.assertEqual(len(md_tables(section)[0]) - 2, ur.MAX_TABLE_ROWS)
        self.assertIn("Se muestran las %d primeras filas de %d" % (ur.MAX_TABLE_ROWS, total), section)

    def test_skills_without_calls_still_report_and_an_unseen_prefix_groups(self):
        text = render_global([], uses=[su(1, skill="plugin:pl", group="plugin:pl")])
        self.assertIn("| `(otra skill)` | `plugin:(otro)` | 1 |", text)
        self.assertNotIn("`plugin:pl`", text)
        seen = render_global([], uses=[su(1, skill="plugin:pl", group="plugin:pl", origin="subagente",
                                          **self.PLUGIN_AGENT)])
        self.assertIn("| `plugin:pl` | `plugin:pl` | 1 |", seen)

    def test_the_closing_line_states_the_plugin_rule(self):
        section = self.skills(render_global([mk(1, project=PA)], uses=[su(1)]))
        self.assertIn("el prefijo de plugin (`plugin:<prefijo>`) solo se muestra si también apareció como agente",
                      section)
        self.assertIn("`plugin:(otro)`", section)


class GlobalCompareSection(unittest.TestCase):
    def setUp(self):
        self.text = render_global(global_calls())
        self.section = section_of(self.text, "Qué compara y qué no")

    def test_it_says_what_is_compared_and_what_is_not(self):
        for needle in ("llamadas", "tokens por llamada", "duración", "herramientas", "skills", "repeticiones inferidas",
                       "No compara la calidad del resultado", "ni el costo real", "ni el ahorro",
                       "indicativo", "volúmenes muy distintos", "versiones de Claude Code distintas",
                       "no un reintento confirmado"):
            self.assertIn(needle, self.section, needle)

    def test_it_says_what_each_group_contains_and_what_the_agents_column_counts(self):
        line = ur.GLOBAL_COMPARES[-1]
        self.assertTrue(line.startswith("Contenido de cada conjunto: "))
        for needle in ("`integrado`, los agentes integrados de Claude Code", "`SyncLayer`, los agentes de este repositorio",
                       "con el mismo nombre cuenta como SyncLayer", "`plugin:<prefijo>`, todos los agentes de ese plugin"
                       " en una sola fila", "`otros`, los agentes de usuario", "`sin-meta`, las llamadas sin archivo meta,"
                       " que no es un conjunto de agentes", "`Agentes` cuenta tipos de agente distintos, no filas",
                       "no se muestra (`-`) en `otros` ni en `plugin:(no-valido)`"):
            self.assertIn(needle, line, needle)
        self.assertIn("- " + line + "\n", self.section + "\n")

    def test_it_is_always_present_even_without_calls(self):
        self.assertIn("## Qué compara y qué no", render_global([]))

    def test_it_dumps_the_fixed_paragraphs(self):
        for line in ur.GLOBAL_COMPARES:
            self.assertIn("- " + line + "\n", self.section + "\n")

    def test_the_reading_guide_dumps_both_limitation_tuples_and_names_all_projects(self):
        guide = section_of(self.text, "Cómo leer estos números")
        for line in ur.REPEAT_LIMITATIONS + ur.SKILL_LIMITATIONS + ur.HOW_TO_READ_GLOBAL:
            self.assertIn("- " + line + "\n", guide + "\n")
        self.assertNotIn("elegidas para este proyecto", guide)
        self.assertIn("todas las carpetas de transcripciones", guide)
        self.assertEqual(ur.HOW_TO_READ_GLOBAL[:-1], ur.HOW_TO_READ[:-1])

    ALLOWED = (ur.HOW_TO_READ[0], ur.HOW_TO_READ[1], ur.GLOBAL_COMPARES[1])

    def test_no_saving_cost_or_quality_claims_beyond_the_fixed_denials(self):
        texts = (self.text, render_global([]), render_global([mk(1, project=PA)], uses=[su(1)]),
                 render_global(golden_calls()))
        for text in texts:
            for phrase in self.ALLOWED:
                text = text.replace(phrase, "")
            plain = "".join(ch for ch in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(ch))
            self.assertEqual(ReportReadingGuide.FORBIDDEN.findall(plain), [])
            for word in ("$", "usd", "dolar", "euro"):
                self.assertNotIn(word, plain, word)
        for phrase in self.ALLOWED:
            self.assertIn(phrase, self.text)


class GlobalPrivacy(ReaderBase):
    FOLDER = "c--Users-" + us.M_FOLDER + "-proj"
    OTHER = "c--Users-" + us.M_FOLDER + "-otro"

    def _text(self):
        tree = us.Tree(self.base)
        ts = "2026-03-10T10:00:%02dZ"
        # caso 11 del plan sobre el texto global: marcadores en el resultado de herramienta (M_RESULT) y en el
        # nombre de una skill de usuario (M_SKILL), ademas de los de contenido, carpeta, sesion, modelo y tipo
        tree.main_session(self.FOLDER, us.M_SESSION + "-1", [us.skill_line("sm1", ts % 1, ["brainstorm"]),
                                                             us.tool_result_line(ts % 2),
                                                             us.skill_line("sm2", ts % 4, [us.M_SKILL])])
        tree.subagent(self.FOLDER, us.M_SESSION + "-1", "a1",
                      [us.user(ts % 0), us.assistant("m1", ts % 3, blocks=[us.tool_use_block("t1", "Read")]),
                       us.tool_result_line(ts % 4),
                       us.skill_line("sa1", ts % 5, ["plugin:" + us.M_SKILL_TAIL, us.M_SKILL])],
                      meta={"agentType": "pl:" + us.M_TYPE, "description": us.M_DESCRIPTION})
        tree.subagent(self.FOLDER, us.M_SESSION + "-2", "a2",
                      [us.assistant("m2", ts % 20, model=us.M_MODEL, version=us.M_VERSION)])
        tree.subagent(self.OTHER, us.M_SESSION + "-9", "a9", [us.assistant("m9", ts % 30)])
        self.res = self.read(tree, check_damage=False)
        self.metrics = ur.aggregate_calls(self.res, today=TODAY)
        return ur.render_global_report(self.metrics, generated=G_DAY)

    def test_no_marker_path_folder_or_internal_identifier_in_the_text(self):
        text = self._text()
        for marker in us.ALL_MARKERS:
            self.assertNotIn(marker, text)
        for c in self.res.calls:
            for value in (c.call_id, c.session, c.agent_key):
                self.assertNotIn(value, text)
        for folder in (self.FOLDER, self.OTHER):
            self.assertNotIn(folder, text)
        self.assertEqual(re.findall(r"\b[0-9a-f]{16}\b", text), [])
        for bad in ("\\", "C:", "/Users", "ZZMARK", "brainstorm"):
            self.assertNotIn(bad, text)
        # ningun alias sale: los proyectos van numerados (`proyecto N`), ni el de las metricas ni uno cualquiera
        for folder in (self.FOLDER, self.OTHER):
            self.assertNotIn(ur._project_alias(folder), text)
        self.assertEqual(re.findall(r"p-[0-9a-f]{8}", text), [])
        self.assertEqual([cells_of(line)[0] for line in table_with(text, "| Proyecto")[2:]],
                         ["`proyecto 1`", "`proyecto 2`"])

    def test_labels_come_only_from_the_closed_lists(self):
        text = self._text()
        self.assertIn("`plugin:pl`", text)
        self.assertNotIn(us.M_TYPE, text)
        self.assertIn("`(otro modelo)`", text)
        self.assertIn("`(otra skill)`", text)          # `brainstorm` y M_SKILL, agrupadas
        # el prefijo `plugin` de la skill de plugin no se vio como agente (el agente es `plugin:pl`): no sale
        self.assertIn("`(otra skill)` | `plugin:(otro)`", text)
        self.assertNotIn("`plugin:plugin`", text)

    def test_generator_receives_only_aggregated_metrics_and_a_date(self):
        import inspect
        self.assertEqual(list(inspect.signature(ur.render_global_report).parameters), ["metrics", "generated"])

    def test_the_text_is_the_same_whatever_the_digest_keys_of_each_read(self):
        first = self._text()
        self.assertEqual(self._text(), first)

    def test_project_report_of_one_project_never_prints_the_alias_of_the_other(self):
        self._text()
        mine = ur.render_project_report(self.metrics, ur._project_alias(self.FOLDER))
        self.assertNotIn(ur._project_alias(self.OTHER), mine)


class GlobalAliasCollision(ReaderBase):
    LABEL = "alias de proyecto repetido entre carpetas"

    def _two_folders(self):
        tree = us.Tree(self.base)
        ts = "2026-03-10T10:00:%02dZ"
        tree.subagent("c--uno", "s1", "a1", [us.user(ts % 0), us.assistant("m1", ts % 5)], meta={"agentType": "forge"})
        tree.subagent("c--dos", "s2", "a2", [us.user(ts % 20), us.assistant("m2", ts % 25)],
                      meta={"agentType": "scout"})
        return tree

    def test_distinct_folders_with_the_same_alias_are_grouped_and_reported(self):
        tree = self._two_folders()
        with mock.patch.object(ur, "_project_alias", lambda name: "p-deadbeef"):
            res = self.read(tree, check_damage=False)
        self.assertEqual(res.quality[self.LABEL], 1)
        self.assertIn(ur.WARN_ALIAS_COLLISION, res.warnings)
        metrics = ur.aggregate_calls(res, today=TODAY)
        self.assertEqual([(p.project, p.metrics.calls, p.metrics.sessions) for p in metrics.projects],
                         [("p-deadbeef", 2, 2)])
        text = ur.render_global_report(metrics)
        self.assertIn("> - AVISO: " + ur.WARN_ALIAS_COLLISION, text)
        self.assertEqual(len(table_with(text, "| Proyecto")) - 2, 1)
        self.assertEqual(cells_of(table_with(text, "| Proyecto")[2])[:3], ["`proyecto 1`", "2", "2"])
        self.assertIn("| `alias de proyecto repetido entre carpetas` | 1 |", text)
        # el limite queda dicho en la calidad del global: con numeros ordinales las dos carpetas siguen siendo UN proyecto
        self.assertIn(ur.GLOBAL_ALIAS_LIMIT, section_of(text, "Calidad de los datos"))
        self.assertIn("se cuentan como un solo proyecto", ur.GLOBAL_ALIAS_LIMIT)
        self.assertIn("se agrupan como un solo proyecto", ur.WARN_ALIAS_COLLISION)
        self.assertNotIn("una sola fila", ur.WARN_ALIAS_COLLISION)

    def test_three_folders_with_the_same_alias_are_one_collision_not_two(self):
        res = ur.ReadResult()
        res._key = b"k" * 16
        alias = ur._project_alias("c--a")
        res._alias_folders.update({(alias, "c--a"), (alias, "c--b"), (alias, "c--c")})
        self.assertEqual(ur._count_alias_collisions(res), 1)
        res._alias_folders.update({("p-00000001", "c--x"), ("p-00000001", "c--y")})
        self.assertEqual(ur._count_alias_collisions(res), 2)
        res._alias_folders.add(("p-00000002", "c--solo"))
        self.assertEqual(ur._count_alias_collisions(res), 2)

    def test_distinct_aliases_are_neither_counted_nor_warned(self):
        res = self.read(self._two_folders(), check_damage=False)
        self.assertEqual(res.quality[self.LABEL], 0)
        self.assertNotIn(ur.WARN_ALIAS_COLLISION, res.warnings)
        self.assertEqual(len(ur.aggregate_calls(res, today=TODAY).projects), 2)

    def test_folders_that_only_differ_in_case_share_the_alias_without_a_collision(self):
        # `c--` y `C--` son el mismo proyecto (mismo nombre en minusculas): no es una colision
        res = ur.ReadResult()
        res._key = b"k" * 16
        a, b = os.path.join(self.base, "a"), os.path.join(self.base, "b")
        os.makedirs(a)
        os.makedirs(b)
        ur._read_project_folder(a, "c--proj", res)
        ur._read_project_folder(b, "C--proj", res)
        self.assertEqual(ur._count_alias_collisions(res), 0)
        res._alias_folders.add((ur._project_alias("c--proj"), "c--otra-cosa"))
        self.assertEqual(ur._count_alias_collisions(res), 1)

    def test_the_folder_names_are_released_when_the_read_ends(self):
        res = self.read(self._two_folders(), check_damage=False)
        self.assertIsNone(res._alias_folders)

    def test_the_counter_is_an_incident_and_has_its_own_warning(self):
        self.assertIn(self.LABEL, ur.READ_INCIDENT_LABELS)
        self.assertNotIn(self.LABEL, ur.READ_INFO_LABELS)
        self.assertEqual(ur.READ_WARNED[self.LABEL], ur.WARN_ALIAS_COLLISION)
        self.assertIn(ur.WARN_ALIAS_COLLISION, ur.KNOWN_WARNINGS)
        ur.WARN_ALIAS_COLLISION.encode("utf-8")


class GlobalDeterminismAndArguments(unittest.TestCase):
    def test_same_input_same_bytes_in_any_order(self):
        calls = global_calls()
        base = render_global(calls, generated=G_DAY).encode("utf-8")
        rnd = random.Random(11)
        for _ in range(5):
            shuffled = list(calls)
            rnd.shuffle(shuffled)
            self.assertEqual(render_global(shuffled, generated=G_DAY).encode("utf-8"), base)

    def test_does_not_read_the_clock_or_do_io(self):
        metrics = agg(global_calls())

        def boom(*a, **k):
            raise AssertionError("E/S o reloj en el generador global")

        class Boom(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                raise AssertionError("reloj")

        with mock.patch.object(datetime, "datetime", Boom), mock.patch("time.time", side_effect=boom), \
                mock.patch("builtins.open", boom), mock.patch.object(os, "stat", boom), \
                mock.patch.object(os, "lstat", boom), mock.patch.object(os, "scandir", boom), \
                mock.patch.object(os, "listdir", boom), mock.patch.object(os, "open", boom), \
                mock.patch("sys.stdout", new=None), mock.patch("sys.stderr", new=None):
            ur.render_global_report(metrics)

    def test_input_metrics_are_not_modified(self):
        metrics = agg(global_calls())
        before = repr(metrics)
        ur.render_global_report(metrics)
        self.assertEqual(repr(metrics), before)

    def test_generated_must_be_a_date_or_none(self):
        metrics = agg(global_calls())
        for bad in (datetime.datetime(2026, 4, 1, 12), "2026-04-01", 20260401, True):
            with self.subTest(generated=bad):
                with self.assertRaises(ValueError):
                    ur.render_global_report(metrics, generated=bad)
        ur.render_global_report(metrics, generated=None)

    def test_metrics_must_be_usage_metrics_and_the_error_does_not_echo_it(self):
        for bad in (None, [], "ZZMARK-texto", agg(global_calls()).total):
            with self.subTest(kind=type(bad).__name__):
                with self.assertRaises(ValueError) as cm:
                    ur.render_global_report(bad)
                self.assertNotIn("ZZMARK", str(cm.exception))

    def test_render_does_not_serialize_calls(self):
        # el generador no ve CallRecord, SkillUse ni ReadResult: solo UsageMetrics
        with self.assertRaises(ValueError):
            ur.render_global_report(ur.ReadResult())
        with self.assertRaises(ValueError):
            ur.render_global_report(global_calls())


class GlobalZeroCalls(unittest.TestCase):
    def test_no_calls_prints_the_fixed_sections_and_no_tables_of_agents(self):
        text = render_global([], generated=G_DAY)
        self.assertEqual(headings(text), ["## Resumen", "## Skills", "## Qué compara y qué no",
                                          "## Calidad de los datos", "## Cómo leer estos números", "## Pie"])
        self.assertIn("Sin llamadas a subagentes en la ventana.", text)
        self.assertIn("- Proyectos con llamadas en la ventana: 0", text)
        self.assertNotIn("| Agente |", text)
        self.assertNotIn("| Proyecto |", text)

    def test_all_time_window_header(self):
        metrics = ur.aggregate_calls(global_calls(), window=ur.make_window(TODAY, all_time=True))
        self.assertIn("> - Ventana: todo el historial (sin ventana)", ur.render_global_report(metrics))


class GlobalSourceHygiene(unittest.TestCase):
    def test_fixed_global_texts_are_ascii_or_accented_spanish_and_utf8(self):
        fixed = (ur.GLOBAL_COMPARES + ur.GLOBAL_PRIVACY_NOTES + ur.HOW_TO_READ_GLOBAL + ur.GLOBAL_PROJECT_NOTES
                 + (ur.WARN_ALIAS_COLLISION, ur.GLOBAL_ALIAS_LIMIT, ur.GLOBAL_SIN_META_NOTE, ur.GLOBAL_SKILLS_NOTE))
        for text in fixed:
            for ch in text:
                self.assertTrue(" " <= ch <= "~" or ch in ACCENTED, (ch, text))
            self.assertEqual(text.encode("utf-8").decode("utf-8"), text)
        for text in (ur.OTHER_GROUP, ur.OTHER_PLUGIN_GROUP) + tuple(ur.SKILL_GROUPS) + tuple(ur.AGENT_GROUPS):
            text.encode("ascii")      # pasan por `_code`, que cambia lo no ASCII por `?`

    def test_global_report_has_no_unaccented_spanish_words_outside_code(self):
        res = ur.ReadResult()
        res.calls.extend(global_calls())
        res.quality["lineas corruptas"] = 1
        res.quality["alias de proyecto repetido entre carpetas"] = 1
        texts = (render_global(global_calls(), uses=[su(1), su(2, origin="subagente", agent="forge",
                                                               agent_group="SyncLayer")]),
                 render_global(agg(res)), render_global([]), render_global(global_golden_calls(), generated=G_DAY))
        bare = re.compile(r"\b(sesion|duracion|numeros?|cache|linea|lineas|danad[oa]s?|ultim[ao]|tamano|"
                          r"senal|estadisticas?|leid[oa]s?|invocacion|version|mas|volumenes|minusculas|revisalo|"
                          r"aqui|numericamente|posicion|estimacion|modificacion|colision|"
                          r"informacion|unica|metricas?|peticion|conversacion|opcion|ningun|despues|tambien)\b",
                          re.IGNORECASE)
        for text in texts:
            outside = "\n".join(re.sub(r"`[^`]*`", "", line) for line in text.split("\n"))
            self.assertEqual(bare.findall(outside), [])
            # `que` suelto es una palabra valida sin tilde: solo se vigila el interrogativo del titulo
            self.assertNotRegex(outside, r"## Que ")


class GlobalHostileFields(unittest.TestCase):
    def test_versions_and_labels_are_sanitized_in_the_global_too(self):
        base = agg(global_calls())
        hostile = ("## ZZH", "x\x1b[31mred", "rtl‮txt", "<script>alert(1)</script>", "x|y\n## Inyectado")
        text = ur.render_global_report(dataclasses.replace(
            base, versions_seen=tuple((h, 1) for h in hostile), unverified_versions=hostile,
            verified_max="[a](javascript:x)\r## ZZV‮<script>"))
        ReportHostileFields().assert_nothing_injected(text)
        self.assertIn("- ultima_version_verificada: `[a](javascript:x)?## ZZV?<script>`", text)

    def test_group_labels_with_pipes_and_newlines_keep_every_table_intact(self):
        calls = [mk(1, project=PA, agent="a|b\n## X", agent_group="x|y\n## Y"),
                 mk(2, project=PA, session="s2", agent="forge", agent_group="SyncLayer")]
        text = render_global(calls)
        for block in md_tables(text):
            self.assertEqual(len({columns(line) for line in block}), 1, block[0])
        for line in text.split("\n"):
            self.assertFalse(line.startswith(("## X", "## Y")), line)


class GlobalOverSyntheticTree(ReaderBase):
    def test_report_from_a_read_tree_is_valid_deterministic_and_has_one_row_per_project(self):
        tree = us.Tree(self.base)
        ts = "2026-03-10T10:00:%02dZ"
        for p, folder in enumerate(("c--uno", "c--dos", "c--tres")):
            for i in range(p + 1):
                tree.subagent(folder, "s%d" % i, "a%d" % i,
                              [us.user(ts % (i * 10)),
                               us.assistant("m%d" % i, ts % (i * 10 + 5), usage_value=us.usage(10, 5, 2, 3),
                                            blocks=[us.tool_use_block("t%d" % i, "Bash")])],
                              meta={"agentType": ("forge", "pl:x", "zzz")[p]})
        text = ur.render_global_report(ur.aggregate_calls(self.read(tree), today=TODAY))
        again = ur.render_global_report(ur.aggregate_calls(self.read(tree), today=TODAY))
        self.assertEqual(text, again)
        block = table_with(text, "| Proyecto")
        self.assertEqual([cells_of(line)[2] for line in block[2:]], ["3", "2", "1"])
        self.assertEqual([cells_of(line)[0] for line in block[2:]], ["`proyecto 1`", "`proyecto 2`", "`proyecto 3`"])
        for folder in ("c--uno", "c--dos", "c--tres"):
            self.assertNotIn(folder, text)
            self.assertNotIn(ur._project_alias(folder), text)
        self.assertIn("- Conjuntos con llamadas: 3", text)


# Archivo dorado del reporte global: dos proyectos, tres llamadas, dos conjuntos. Los valores se calcularon a
# mano: PA tiene forge (200 tokens, 60 s, 3 herramientas, 2.1.300) y scout (20 tokens, 5 s, 0 herramientas, 9.0.0)
# en una sesion; PB tiene un agente de plugin (20 tokens, 8 s, 0 herramientas, 2.1.300) en otra. Conjunto
# SyncLayer: mediana de [20, 200] = (20+200+1)//2 = 110, p90 200, duracion [60, 5] -> 33, herramientas [3, 0] -> 2,
# 1 sesion y 2.0 llamadas por sesion. Proyectos: PA 2 llamadas y 220 tokens; PB 1 llamada y 20 tokens, barra de 1 de
# 2 = 5 bloques. 3 llamadas / 2 sesiones = 1.5. Nada de esto depende de VERIFIED_MAX (`@VM@`).
def global_golden_calls():
    return [
        mk(1, project=PA, session="a1", input_tokens=100, output_tokens=50, cache_creation_tokens=20,
           cache_read_tokens=30, tools=3, versions=("2.1.300",), **span(60)),
        mk(2, project=PA, session="a1", agent="scout", versions=("9.0.0",), tools=0, **span(5, hour=11)),
        mk(3, project=PB, session="b1", agent="plugin:pl", agent_group="plugin:pl", versions=("2.1.300",), tools=0,
           **span(8, hour=12)),
    ]


GOLDEN_GLOBAL_REPORT_TEMPLATE = (
    '<!-- synclayer-usage-report v1 -->\n'
    '# Reporte global de uso de subagentes\n'
    '\n'
    '> - Ventana: 2026-03-02 a 2026-03-31 (UTC, ambos inclusive)\n'
    '> - Llamadas: 3 en 2 sesiones en 2 proyectos\n'
    '> - Claude Code: versiones `2.1.300` a `9.0.0` (2 versiones)\n'
    '> - Esquema del reporte: 1\n'
    '> - Generado: 2026-04-01\n'
    '> - Alcance: todos los proyectos le\u00eddos; proyectos numerados por volumen, sin nombres ni rutas ni alias.\n'
    '> - Reporte privado por defecto: lleva el volumen de uso de cada proyecto; no lo subas a git y comp\u00e1rtelo solo despu\u00e9s de revisarlo.\n'
    '> - AVISO: hay versiones de Claude Code posteriores a la \u00faltima verificada (`@VM@`): `9.0.0`. El formato interno puede haber cambiado.\n'
    '\n'
    '## Resumen\n'
    '\n'
    '- Llamadas: 3 en 2 sesiones (1.5 llamadas por sesi\u00f3n)\n'
    '- Proyectos con llamadas en la ventana: 2\n'
    '- Conjuntos con llamadas: 2\n'
    '- Agentes distintos (por nombre y conjunto): 3\n'
    '- Tokens (suma de las llamadas con estad\u00edsticas): 240 en 3 llamadas\n'
    '- Repeticiones consecutivas (inferido): 0\n'
    '- Llamadas en el rango de versi\u00f3n dudoso (2.1.310 a 2.1.327): 0 de 3 (0 %)\n'
    '- Skills: 0 invocaciones en 0 sesiones\n'
    '\n'
    '## Por conjunto\n'
    '\n'
    '| Conjunto | Agentes | Llamadas | Barra | Tokens/llamada (med.) | p90 | Duraci\u00f3n aprox. s (med.) | Herramientas (med.) |\n'
    '|---|---:|---:|---|---:|---:|---:|---:|\n'
    '| `SyncLayer` | 2 | 2 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 110 * | 200 * | 33 * | 2 * |\n'
    '| `plugin:pl` | 1 | 1 | \u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591\u2591 | 20 * | 20 * | 8 * | 0 * |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    'Detalle por conjunto:\n'
    '\n'
    '| Conjunto | Sesiones | Llamadas/sesi\u00f3n | n | Tokens (suma) | Duraci\u00f3n aprox. s (p90) | Herramientas (p90) | Repeticiones (inferido) | Repeticiones (% de llamadas) |\n'
    '|---|---:|---:|---:|---:|---:|---:|---:|---:|\n'
    '| `SyncLayer` | 1 | 2.0 | 2 * | 220 | 60 * | 3 * | 0 | 0 % |\n'
    '| `plugin:pl` | 1 | 1.0 | 1 * | 20 | 8 * | 0 * | 0 | 0 % |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    'Tokens por llamada, por conjunto y rango de versi\u00f3n:\n'
    '\n'
    '| Conjunto | Rango | Llamadas | n | Mediana | p90 | Nota |\n'
    '|---|---|---:|---:|---:|---:|---|\n'
    '| `SyncLayer` | `<2.1.310` | 1 | 1 * | 200 * | 200 * |  |\n'
    '| `SyncLayer` | `>=2.1.328` | 1 | 1 * | 20 * | 20 * |  |\n'
    '| `plugin:pl` | `<2.1.310` | 1 | 1 * | 20 * | 20 * |  |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    '## Llamadas por agente\n'
    '\n'
    '| Agente | Conjunto | Llamadas | Barra | Sesiones | Llamadas/sesi\u00f3n | Repeticiones (inferido) |\n'
    '|---|---|---:|---|---:|---:|---:|\n'
    '| `forge` | `SyncLayer` | 1 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 1 | 1.0 | 0 |\n'
    '| `plugin:pl` | `plugin:pl` | 1 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 1 | 1.0 | 0 |\n'
    '| `scout` | `SyncLayer` | 1 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 1 | 1.0 | 0 |\n'
    '\n'
    '## Tokens por llamada\n'
    '\n'
    '| Agente | Conjunto | n | Tokens (suma) | Barra | Mediana | p90 | Entrada (med.) | Salida (med.) | Cach\u00e9 escrita (med.) | Cach\u00e9 le\u00edda (med.) | Peticiones (med.) |\n'
    '|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|\n'
    '| `forge` | `SyncLayer` | 1 * | 200 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 200 * | 200 * | 100 | 50 | 20 | 30 | 1 |\n'
    '| `plugin:pl` | `plugin:pl` | 1 * | 20 | \u2588\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591 | 20 * | 20 * | 10 | 5 | 2 | 3 | 1 |\n'
    '| `scout` | `SyncLayer` | 1 * | 20 | \u2588\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591 | 20 * | 20 * | 10 | 5 | 2 | 3 | 1 |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    '## Duraci\u00f3n y herramientas\n'
    '\n'
    '| Agente | Conjunto | Duraci\u00f3n aprox. s (med.) | p90 | Herramientas (med.) | p90 |\n'
    '|---|---|---:|---:|---:|---:|\n'
    '| `forge` | `SyncLayer` | 60 * | 60 * | 3 * | 3 * |\n'
    '| `plugin:pl` | `plugin:pl` | 8 * | 8 * | 0 * | 0 * |\n'
    '| `scout` | `SyncLayer` | 5 * | 5 * | 0 * | 0 * |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    '## Modelo real\n'
    '\n'
    '| Agente | Conjunto | Modelo | Llamadas |\n'
    '|---|---|---|---:|\n'
    '| `forge` | `SyncLayer` | `claude-opus-4-1` | 1 |\n'
    '| `plugin:pl` | `plugin:pl` | `claude-opus-4-1` | 1 |\n'
    '| `scout` | `SyncLayer` | `claude-opus-4-1` | 1 |\n'
    '\n'
    '## Por proyecto\n'
    '\n'
    'Los proyectos van numerados por volumen de llamadas, de m\u00e1s a menos (desempate por sesiones y luego por tokens). La numeraci\u00f3n puede cambiar entre ejecuciones y no coincide con el alias del reporte de proyecto.\n'
    '\n'
    'Un proyecto le\u00eddo con todas sus llamadas fuera de la ventana, o solo con skills, no aparece.\n'
    '\n'
    '| Proyecto | Sesiones | Llamadas | Barra | Tokens (suma) |\n'
    '|---|---:|---:|---|---:|\n'
    '| `proyecto 1` | 1 | 2 | \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588 | 220 |\n'
    '| `proyecto 2` | 1 | 1 | \u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591\u2591 | 20 |\n'
    '\n'
    '## Skills\n'
    '\n'
    'Sin invocaciones de skills en la ventana.\n'
    '\n'
    'No se atribuyen tokens a una skill: corre en el contexto de la sesi\u00f3n que la invoca.\n'
    '\n'
    '## Versiones de Claude Code\n'
    '\n'
    'Por rango de versi\u00f3n:\n'
    '\n'
    '| Rango | Llamadas | Tokens/llamada (med.) | p90 | Nota |\n'
    '|---|---:|---:|---:|---|\n'
    '| `<2.1.310` | 2 | 110 * | 200 * |  |\n'
    '| `2.1.310-2.1.327` | 0 | - | - | dudoso: tokens posiblemente inflados por reintentos (corregido en 2.1.328) |\n'
    '| `>=2.1.328` | 1 | 20 * | 20 * |  |\n'
    '\n'
    '`*`: n < 10, pocas muestras. La mediana y el p90 dicen poco.\n'
    '\n'
    'Comparar entre rangos es solo indicativo.\n'
    '\n'
    'Versiones vistas:\n'
    '\n'
    '| Versi\u00f3n | Llamadas | Nota |\n'
    '|---|---:|---|\n'
    '| `2.1.300` | 2 |  |\n'
    '| `9.0.0` | 1 | no verificada (mayor que `@VM@`) |\n'
    '\n'
    '## Qu\u00e9 compara y qu\u00e9 no\n'
    '\n'
    '- Compara entre conjuntos de agentes solo estas cifras: llamadas y llamadas por sesi\u00f3n, tokens por llamada (mediana y p90), duraci\u00f3n aproximada, herramientas por llamada, uso de skills (invocaciones y sesiones) y repeticiones inferidas.\n'
    '- No compara la calidad del resultado de un agente, ni el costo real, ni el ahorro de nadie: esas cifras no salen de las transcripciones.\n'
    '- Dos conjuntos hacen trabajos distintos: una cifra menor de tokens por llamada no dice nada sobre el resultado.\n'
    '- Comparar conjuntos con vol\u00famenes muy distintos (pocas llamadas frente a muchas) o con versiones de Claude Code distintas es solo indicativo: con n < 10 la mediana y el p90 dicen poco (marca `*`), y los tokens de las versiones 2.1.310 a 2.1.327 pueden estar inflados por reintentos.\n'
    '- Las skills solo se comparan por n\u00famero de invocaciones y de sesiones: corren en el contexto de la sesi\u00f3n que las invoca y no se les atribuyen tokens.\n'
    '- Las repeticiones son inferidas, no un reintento confirmado: salen de las horas de inicio y fin de dos llamadas seguidas del mismo agente en una sesi\u00f3n. Pueden ser un reintento, un paso de un plan o un encargo nuevo, y la herramienta no puede distinguirlos; por eso se muestran como `Repeticiones (inferido)` y como porcentaje de las llamadas.\n'
    '- Contenido de cada conjunto: `integrado`, los agentes integrados de Claude Code; `SyncLayer`, los agentes de este repositorio (un agente de proyecto con el mismo nombre cuenta como SyncLayer); `plugin:<prefijo>`, todos los agentes de ese plugin en una sola fila; `otros`, los agentes de usuario; `sin-meta`, las llamadas sin archivo meta, que no es un conjunto de agentes y no entra en la comparaci\u00f3n. `Agentes` cuenta tipos de agente distintos, no filas, y no se muestra (`-`) en `otros` ni en `plugin:(no-valido)`.\n'
    '\n'
    '## Calidad de los datos\n'
    '\n'
    '| Concepto | Cantidad |\n'
    '|---|---:|\n'
    '| Llamadas le\u00eddas (todas las ventanas) | 3 |\n'
    '| Llamadas en la ventana | 3 |\n'
    '| Llamadas fuera de la ventana | 0 |\n'
    '| Llamadas con estad\u00edsticas de tokens | 3 |\n'
    '| Llamadas con una versi\u00f3n posterior a la verificada | 1 |\n'
    '\n'
    'Proyectos: dos carpetas distintas con el mismo alias interno (colisi\u00f3n de 32 bits, improbable) se cuentan como un solo proyecto; la cabecera lo avisa cuando ocurre.\n'
    '\n'
    '## C\u00f3mo leer estos n\u00fameros\n'
    '\n'
    '- No mide la calidad del resultado de un agente ni el costo en dinero: una llamada con menos tokens no dice nada sobre su resultado.\n'
    '- No muestra costos. Los tokens no son una factura (la cach\u00e9 le\u00edda se cobra distinto) y cualquier costo ser\u00eda una estimaci\u00f3n a precio de lista; aqu\u00ed no se calcula.\n'
    '- Una llamada es un archivo de subagente (`agent-<id>.jsonl`). Los tokens por llamada suman entrada, salida, cach\u00e9 escrita y cach\u00e9 le\u00edda; una respuesta repartida en varias l\u00edneas se cuenta una vez (se deduplica por `message.id`).\n'
    '- La duraci\u00f3n es aproximada: \u00faltima marca de tiempo menos la primera. Incluye esperas de herramientas y de permisos.\n'
    '- Con n < 10 llamadas (marca `*`, pocas muestras) la mediana y el p90 dicen poco.\n'
    '- Mediana: con n par, media de los dos centrales redondeada al entero (medio hacia arriba). p90: el valor en la posici\u00f3n ceil(0,9 n) de la lista ordenada. Los porcentajes se redondean al entero m\u00e1s cercano (medio hacia arriba); `<1 %` es un valor distinto de cero que redondea a 0.\n'
    '- Las repeticiones son una inferencia, no un reintento confirmado (ver abajo).\n'
    '- Las versiones 2.1.310 a 2.1.327 de Claude Code pueden inflar los tokens por reintentos y no se corrige num\u00e9ricamente. Comparar entre rangos de versi\u00f3n es solo indicativo.\n'
    '- Los n\u00fameros dependen de un formato interno de Claude Code que no est\u00e1 garantizado y puede cambiar sin aviso.\n'
    '- Se leen todas las carpetas de transcripciones de `projects/`: las sesiones abiertas desde una subcarpeta o un worktree viven en otra carpeta y salen como otro proyecto.\n'
    '\n'
    '### Repeticiones (inferido)\n'
    '\n'
    '- Las repeticiones son una se\u00f1al inferida por horas de inicio y fin, no un reintento confirmado.\n'
    '- Una llamada puede marcarse aunque corra en paralelo con otra anterior del mismo agente: solo se mira la anterior inmediata por hora de inicio (A1 0-100, A2 10-20, A3 30-40: se marca A3).\n'
    '- Las llamadas sin hora de inicio no participan en la cadena ni la rompen.\n'
    '- La primera llamada de la ventana no se marca, aunque su anterior quedara fuera de la ventana.\n'
    '- Las llamadas sin meta nunca se marcan, pero rompen la cadena de los dem\u00e1s agentes.\n'
    '- En flujos secuenciales leg\u00edtimos (el mismo agente en pasos distintos de un plan) sobreestima.\n'
    '\n'
    '### Skills\n'
    '\n'
    '- Una l\u00ednea corrupta en medio de una sesi\u00f3n principal o de un subagente se descarta y puede esconder una invocaci\u00f3n de Skill: el conteo de skills puede ser menor que el real.\n'
    '- Las skills que el usuario invoca con /nombre no generan un bloque tool_use de Skill y no se cuentan: solo se cuentan las que invoca el modelo.\n'
    '\n'
    '## Pie\n'
    '\n'
    '- report_schema: 1\n'
    '- herramienta: tools/usage_report.py\n'
    '- ultima_version_verificada: `@VM@`\n'
    '- alcance: global (todos los proyectos le\u00eddos)\n'
    '\n'
    '- Este archivo es privado por defecto: no contiene contenido de conversaciones, rutas, nombres de carpeta ni alias de proyecto, pero revela el volumen de uso de cada proyecto. Comp\u00e1rtelo solo despu\u00e9s de revisarlo.\n'
    '- Los proyectos se numeran por volumen en cada ejecuci\u00f3n: la numeraci\u00f3n puede cambiar entre ejecuciones y no se puede cruzar con el alias del reporte de proyecto. Con un alias de 32 bits, dos carpetas distintas pueden dar el mismo alias interno (improbable): se cuentan como un solo proyecto y la cabecera lo avisa.\n'
    '- El prefijo de un agente de plugin (`plugin:<prefijo>`) lo escribe Claude Code. El prefijo de una skill de plugin sale de texto que escribe el modelo: solo se muestra si ese prefijo tambi\u00e9n apareci\u00f3 como agente en esta lectura; el resto se agrupa como `plugin:(otro)`. Los nombres de skills de usuario no salen: se agrupan como `(otra skill)`.\n'
    '- Los nombres de modelo que no son de una lista cerrada (familias conocidas, n\u00fameros y fechas) salen como `(otro modelo)`. En los conjuntos `otros` y `plugin:(no-valido)` y en los conjuntos de skills con nombres agrupados no se muestra cu\u00e1ntos agentes ni cu\u00e1ntas skills distintos hay (`-`).\n'
    '- Un agente de proyecto con el mismo nombre que uno de SyncLayer cuenta como SyncLayer.\n'
)


class GlobalGolden(unittest.TestCase):
    def test_small_global_report_matches_the_golden_text_byte_for_byte(self):
        text = render_global(global_golden_calls(), generated=G_DAY)
        self.assertEqual(text, GOLDEN_GLOBAL_REPORT_TEMPLATE.replace("@VM@", ur.VERIFIED_MAX))

    def test_golden_does_not_depend_on_the_current_verified_max(self):
        with mock.patch.object(ur, "VERIFIED_MAX", "3.5.0"):
            text = render_global(global_golden_calls(), generated=G_DAY)
        self.assertEqual(text, GOLDEN_GLOBAL_REPORT_TEMPLATE.replace("@VM@", "3.5.0"))

    def test_golden_changes_with_each_input(self):
        base = render_global(global_golden_calls(), generated=G_DAY)
        self.assertNotEqual(render_global(global_golden_calls(), generated=datetime.date(2026, 4, 2)), base)
        self.assertNotEqual(render_global(global_golden_calls()[:2], generated=G_DAY), base)
        moved = global_golden_calls()
        moved[2] = dataclasses.replace(moved[2], project=PA)     # un proyecto menos
        self.assertIn("en 1 proyecto", render_global(moved, generated=G_DAY))
        self.assertNotEqual(render_global(moved, generated=G_DAY), base)


class GlobalPurity(unittest.TestCase):
    """Todo lo que `render_global_report` puede alcanzar: lista BLANCA y cerrada, como ReportPurity."""
    PROJECT_ONLY = frozenset((
        "render_project_report", "_header_section", "_skills_section", "_footer_section", "PRIVACY_NOTES",
        "MSG_REPORT_ALIAS",
    ))
    GLOBAL_EXTRA = frozenset((
        "render_global_report", "_global_header_section", "_global_group_section", "_global_project_section",
        "_global_skills_section", "_global_compare_section", "_global_footer_section", "_group_table",
        "_group_detail_table", "_group_range_table", "_skill_shown", "_skill_group_label",
        "_global_skill_rows", "_global_skill_groups", "_global_agent_skill_rows", "GLOBAL_COMPARES",
        "GLOBAL_PRIVACY_NOTES", "HOW_TO_READ_GLOBAL", "MSG_GLOBAL_METRICS", "VOLUME_RATIO", "OTHER_GROUP",
        "OTHER_SKILL", "SYNCLAYER_SKILLS", "BUILTIN_SKILLS", "PLUGIN_PREFIX_RE", "SKILL_GROUPS",
        "_global_model_label", "_plugin_groups_seen", "_live_group_calls", "_global_quality_section",
        "GLOBAL_MODEL_RE", "_GLOBAL_MODEL_WORD", "_MODEL_NUM", "MODEL_ALIASES", "OTHER_LABELS", "OTHER_MODEL",
        "OTHER_PLUGIN_GROUP", "GLOBAL_PROJECT_NOTES", "GLOBAL_SIN_META_NOTE", "GLOBAL_ALIAS_LIMIT",
        "GLOBAL_SKILLS_NOTE",
    ))

    def test_global_report_reaches_only_pure_code(self):
        helper = AggregationDeterminismAndPurity()
        tree = helper._module_tree()
        top = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                top[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        top[target.id] = node
        seen, todo = set(), ["render_global_report"]
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            for n in ast.walk(top[name]):
                if isinstance(n, ast.Name) and n.id in top:
                    todo.append(n.id)
        allowed = (set(ReportPurity.REACHABLE) - self.PROJECT_ONLY) | self.GLOBAL_EXTRA
        extra = seen - allowed
        self.assertEqual(extra, set(), "nombres nuevos alcanzables: revisalos y anadelos a la lista blanca")
        for name in ("render_global_report", "_global_header_section", "_global_footer_section"):
            self.assertIn(name, seen)
        self.assertNotIn("render_project_report", seen)
        for name in AggregationDeterminismAndPurity.READER_IO_FUNCTIONS:
            self.assertNotIn(name, seen)
        self.assertNotIn("utc_today", seen)
        self.assertNotIn("_project_alias", seen)     # el generador no calcula alias: lee los de las metricas
        callable_ok = ReportPurity.CALLABLE_OK | {"get", "setdefault", "items", "startswith", "sort", "set", "add",
                                                  "update", "enumerate", "frozenset"}
        for name in seen:
            node = top[name]
            if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                continue
            for n in ast.walk(node):
                self.assertNotIsInstance(n, (ast.Import, ast.ImportFrom), name)
                if isinstance(n, ast.Name):
                    self.assertNotIn(n.id, AggregationDeterminismAndPurity.FORBIDDEN, name)
                if isinstance(n, ast.Attribute):
                    self.assertNotIn(n.attr, AggregationDeterminismAndPurity.FORBIDDEN, name)
                if isinstance(n, ast.Call):
                    callee = n.func.id if isinstance(n.func, ast.Name) else (
                        n.func.attr if isinstance(n.func, ast.Attribute) else None)
                    self.assertIsNotNone(callee, name)
                    self.assertIn(callee, seen | callable_ok | set(ReportPurity.REACHABLE), "%s llama a %s" % (name, callee))


if __name__ == "__main__":
    unittest.main()
