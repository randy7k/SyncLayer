"""Pruebas de borde de punta a punta de tools/usage_report.py (cierre del nucleo de la Fase 2).

Complementan test_usage_report.py y test_usage_report_cli.py: ventana en los bordes por CLI, `--all`,
transcripciones vacias, nombres de carpeta raros, claves faltantes o con tipo equivocado, lineas
truncadas, umbral de dano medido sobre la ventana, exit 1/2/3/130 y mensajes sin fuga.

Todo sobre arboles SINTETICOS en carpetas temporales con `--claude-dir` y `--project-dir`
explicitos; nunca se toca el ~/.claude real ni transcripciones reales.
"""

import datetime
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_usage_report as tur  # noqa: E402
import test_usage_report_cli as tcli  # noqa: E402
import usage_report as ur  # noqa: E402
import usage_synth as us  # noqa: E402

CALLS_RE = re.compile(r"^> - Llamadas: (\d+)", re.M)


def calls_in(text):
    m = CALLS_RE.search(text)
    if not m:
        raise AssertionError("cabecera sin 'Llamadas'")
    return int(m.group(1))


class EdgeBase(tcli.CliBase):
    def one_call_tree(self, builder, proj=None):
        proj = proj or self.make_project()
        tree = us.Tree(self.base)
        builder(tree, self.folder_of(proj))
        return tree, proj

    def stdout_project(self, tree, proj, *extra):
        return self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--stdout", *extra)

    def written(self, tree, proj):
        """Hay algo escrito por la herramienta (en el proyecto o en claude-dir)?"""
        return (os.path.exists(os.path.join(proj, ".synclayer"))
                or os.path.exists(os.path.join(tree.claude_dir, "synclayer-usage.md")))


class WindowEdgesEndToEnd(EdgeBase):
    """Caso 10 por la CLI completa: la ventana es por fecha UTC de la PRIMERA marca, extremos
    inclusivos, y la zona horaria se normaliza antes de comparar."""

    INSIDE = (
        "2026-03-01T00:00:00Z",                  # primer instante de since
        "2026-03-01T00:00:00.000000+00:00",
        "2026-03-31T23:59:59.999999Z",           # ultimo instante de until
        "2026-03-01T05:00:00+05:00",             # = 2026-03-01T00:00Z
        "2026-04-01T04:30:00+05:00",             # = 2026-03-31T23:30Z
        "2026-03-31T20:00:00-03:00",             # = 2026-03-31T23:00Z
        "2026-03-02T00:00:00",                   # sin zona: se toma como UTC
    )
    OUTSIDE = (
        "2026-02-28T23:59:59.999999Z",           # un microsegundo antes de since
        "2026-04-01T00:00:00Z",                  # primer instante tras until
        "2026-03-31T23:30:00-05:00",             # = 2026-04-01T04:30Z (fecha local aun es 31)
        "2026-03-01T01:00:00+05:00",             # = 2026-02-28T20:00Z (fecha local ya es 1)
        "2026-03-31T21:00:00-03:00",             # = 2026-04-01T00:00Z exacto
    )

    def build(self, tree, folder):
        for i, ts in enumerate(self.INSIDE):
            tree.subagent(folder, "in%d" % i, "i%d" % i, [us.user(ts), us.assistant("mi%d" % i, ts)])
        for i, ts in enumerate(self.OUTSIDE):
            tree.subagent(folder, "out%d" % i, "o%d" % i, [us.user(ts), us.assistant("mo%d" % i, ts)])
        # empieza antes de la ventana y termina dentro: fuera (cuenta la primera marca)
        tree.subagent(folder, "ssb", "sb", [us.user("2026-02-28T23:59:50Z"), us.assistant("msb", "2026-03-01T00:00:10Z")])
        # empieza dentro y termina despues: dentro
        tree.subagent(folder, "ssa", "sa", [us.user("2026-03-31T23:59:50Z"), us.assistant("msa", "2026-04-01T00:00:10Z")])

    def test_project_and_global_agree_on_the_inclusive_utc_window(self):
        tree, proj = self.one_call_tree(self.build)
        expected = len(self.INSIDE) + 1
        code, out, err = self.stdout_project(tree, proj, *tcli.WIN)
        self.assertEqual(code, 0, err)
        self.assertEqual(calls_in(out), expected)
        code, out, err = self.run_main("global", "--claude-dir", tree.claude_dir, "--stdout", *tcli.WIN)
        self.assertEqual(code, 0, err)
        self.assertEqual(calls_in(out), expected)

    def test_one_day_window_keeps_only_that_utc_date(self):
        tree, proj = self.one_call_tree(self.build)
        code, out, err = self.stdout_project(tree, proj, "--since", "2026-03-31", "--until", "2026-03-31")
        self.assertEqual(code, 0, err)
        # 2026-03-31 UTC: 23:59:59.999999Z, 23:30Z (+05:00), 23:00Z (-03:00) y el straddle que empieza 23:59:50Z
        self.assertEqual(calls_in(out), 4)
        code, out, err = self.stdout_project(tree, proj, "--since", "2026-04-01", "--until", "2026-04-01")
        self.assertEqual(calls_in(out), len(self.OUTSIDE) - 2)   # 04-01T00:00Z (x2) y 04-01T04:30Z; 02-28 fuera
        self.assertIn("Ventana: 2026-04-01 a 2026-04-01", out)

    def test_only_until_gives_the_30_dates_ending_there_inclusive(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        folder = self.folder_of(proj)
        for i, day in enumerate(("2026-03-02", "2026-03-01", "2026-04-01", "2026-03-31", "2026-04-02")):
            tree.subagent(folder, "s%d" % i, "a%d" % i, [us.user(day + "T12:00:00Z"), us.assistant("m%d" % i, day + "T12:00:01Z")])
        code, out, err = self.stdout_project(tree, proj, "--until", "2026-03-31")
        self.assertEqual(code, 0, err)
        self.assertIn("Ventana: 2026-03-02 a 2026-03-31", out)   # 30 fechas: 02-03 ... 31-03
        self.assertEqual(calls_in(out), 2)   # 03-02 y 03-31 dentro; 03-01, 04-01 y 04-02 fuera


class AllWindow(EdgeBase):
    def build(self, tree, folder):
        for i, ts in enumerate(("2001-01-01T00:00:00Z", "2026-03-05T10:00:00Z", "2099-12-31T23:59:59Z")):
            tree.subagent(folder, "s%d" % i, "a%d" % i, [us.user(ts), us.assistant("m%d" % i, ts)])

    def test_all_includes_the_far_past_and_far_future_default_does_not(self):
        tree, proj = self.one_call_tree(self.build)
        code, out, err = self.stdout_project(tree, proj, "--all")
        self.assertEqual(code, 0, err)
        self.assertEqual(calls_in(out), 3)
        self.assertIn("Ventana: todo el historial", out)
        with mock.patch.object(ur, "utc_today", return_value=datetime.date(2026, 3, 31)):
            code, out, err = self.stdout_project(tree, proj)
        self.assertEqual(calls_in(out), 1)
        code, out, err = self.run_main("global", "--claude-dir", tree.claude_dir, "--stdout", "--all")
        self.assertEqual(calls_in(out), 3)

    def test_global_window_flag_errors_are_exit_2_and_write_nothing(self):
        tree, proj = self.one_call_tree(self.build)
        for extra in (["--all", "--since", "2026-03-01"], ["--all", "--until", "2026-03-31"],
                      ["--since", "2026-04-01", "--until", "2026-03-01"], ["--since", "2026-02-30"],
                      ["--until", "0001-01-05"]):
            code, out, err = self.run_main("global", "--claude-dir", tree.claude_dir, *extra)
            self.assertEqual(code, 2, extra)
            self.assertEqual(out, "")
            self.assertNotIn("Traceback", err)
            self.assertFalse(self.written(tree, proj), extra)

    def test_global_with_an_empty_window_is_exit_0_and_says_zero_calls(self):
        tree, proj = self.one_call_tree(self.build)
        code, out, err = self.run_main("global", "--claude-dir", tree.claude_dir,
                                       "--since", "2010-01-01", "--until", "2010-01-31")
        self.assertEqual(code, 0, err)
        self.assertIn("0 llamadas", out)
        text = self.read_bytes(os.path.join(tree.claude_dir, "synclayer-usage.md")).decode("utf-8")
        self.assertEqual(calls_in(text), 0)


class EmptyTranscripts(EdgeBase):
    """Archivos vacios o en blanco: son llamadas sin hora, no un fallo; nada de division por cero."""

    GARBAGE = re.compile(r"\bnan\b|\binf\b|None|Traceback|ZeroDivision", re.I)

    def check_ok(self, tree, proj, calls):
        for argv in (("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all", "--stdout"),
                     ("global", "--claude-dir", tree.claude_dir, "--all", "--stdout")):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 0, err)
            self.assertEqual(calls_in(out), calls)
            self.assertEqual(err, "")
            self.assertIsNone(self.GARBAGE.search(out), self.GARBAGE.search(out))
        code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all")
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(self.report_path(proj)))

    def test_zero_byte_and_blank_subagent_files_are_calls_without_time(self):
        good = [us.user("2026-03-05T10:00:00Z"), us.assistant("m1", "2026-03-05T10:00:05Z")]

        def build(tree, folder):
            tree.subagent(folder, "s1", "empty", [])
            tree.subagent(folder, "s1", "blank", ["   ", "", "\t"])
            tree.subagent(folder, "s1", "good", good)
        tree, proj = self.one_call_tree(build)
        self.check_ok(tree, proj, 3)
        code, out, err = self.stdout_project(tree, proj, "--all")
        self.assertIn("2 llamadas sin hora de inicio", out)

    def test_only_empty_files_still_give_a_report(self):
        tree, proj = self.one_call_tree(lambda t, f: t.subagent(f, "s1", "empty", []))
        self.check_ok(tree, proj, 1)

    def test_zero_byte_main_session_is_harmless(self):
        def build(tree, folder):
            tree.main_session(folder, "s1", [])
            tree.subagent(folder, "s1", "a1", [us.user("2026-03-05T10:00:00Z"), us.assistant("m1", "2026-03-05T10:00:05Z")])
        tree, proj = self.one_call_tree(build)
        self.check_ok(tree, proj, 1)

    def test_empty_files_never_leak_into_the_window_of_another_period(self):
        """Sin hora, la llamada se ubica por mtime (ahora): fuera de una ventana vieja."""
        tree, proj = self.one_call_tree(lambda t, f: t.subagent(f, "s1", "empty", []))
        code, out, err = self.stdout_project(tree, proj, "--since", "2001-01-01", "--until", "2001-01-31")
        self.assertEqual(code, 0, err)
        self.assertEqual(calls_in(out), 0)


class OddFolderNames(EdgeBase):
    """Caso 13 por la CLI: carpetas de proyecto con puntos, tildes, corchetes, emoji, guiones."""

    NAMES = ("mi.proyecto v1.2", "ñandú [x] (1)", "emoji \U0001F600 dir", "a--b  c", "-guion", "UPPER Case",
             "x" * 120)

    def test_each_name_finds_its_own_calls_and_never_prints_the_folder(self):
        for name in self.NAMES:
            try:
                proj = self.make_project(name)
            except OSError:
                self.skipTest("el sistema no admite el nombre " + ascii(name))
            tree = us.Tree(self.base, claude_name="claude " + str(abs(hash(name))))
            folder = self.folder_of(proj)
            self.add_calls(tree, folder, count=2)
            other = os.path.join(self.base, "otro " + str(abs(hash(name))))
            os.makedirs(other)
            self.add_calls(tree, self.folder_of(other), count=5, prefix="z")   # no debe contarse
            code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *tcli.WIN)
            self.assertEqual(code, 0, (name, err))
            self.assertIn("2 llamadas", out, name)
            text = self.read_bytes(self.report_path(proj)).decode("utf-8")
            self.assertEqual(calls_in(text), 2, name)
            for hidden in (folder, name, self.base, os.path.basename(proj)):
                self.assertNotIn(hidden, out + err + text, name)
            self.assertEqual(tcli.temps_under(self.base), [])


class MissingAndWrongKeys(EdgeBase):
    TS = "2026-03-05T10:00:05Z"

    def lines(self, assistant_line):
        return [us.user("2026-03-05T10:00:00Z"), assistant_line]

    def assistant_with(self, **message_changes):
        line = us.assistant("m1", self.TS)
        for key, value in message_changes.items():
            if value is KeyError:
                line["message"].pop(key, None)
            else:
                line["message"][key] = value
        return line

    def test_tolerated_shapes_are_exit_0_one_call_and_never_an_unexpected_error(self):
        variants = {
            "sin message": {"type": "assistant", "timestamp": self.TS},
            "message cadena": {"type": "assistant", "timestamp": self.TS, "message": "x"},
            "message lista": {"type": "assistant", "timestamp": self.TS, "message": [us.usage()]},
            "content cadena": self.assistant_with(content="texto " + us.M_CONTENT),
            "content ausente": self.assistant_with(content=KeyError),
            "content con basura": self.assistant_with(content=[1, None, "x", [], {"type": "tool_use"},
                                                               {"type": "tool_use", "id": None, "name": []}]),
            "id entero": self.assistant_with(id=5),
            "id lista": self.assistant_with(id=[1]),
            "id nulo": self.assistant_with(id=None),
            "modelo entero": self.assistant_with(model=7),
            "modelo ausente": self.assistant_with(model=KeyError),
            "sin usage": self.assistant_with(usage=KeyError),
            "version entera": us.assistant("m1", self.TS, version=7),
            "version ausente": {k: v for k, v in us.assistant("m1", self.TS).items() if k != "version"},
            "isSidechain cadena": us.assistant("m1", self.TS, isSidechain="si"),
        }
        self.assertGreater(len(variants), 10)
        for label, line in variants.items():
            tree, proj = self.one_call_tree(lambda t, f, line=line: t.subagent(f, "s1", "a0", self.lines(line)))
            for argv in (("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all", "--stdout"),
                         ("global", "--claude-dir", tree.claude_dir, "--all", "--stdout")):
                code, out, err = self.run_main(*argv)
                self.assertEqual(code, 0, (label, err))
                self.assertNotIn("no previsto", err, label)
                self.assertEqual(calls_in(out), 1, label)
                self.assertNotIn(us.M_CONTENT, out + err, label)

    def test_non_object_lines_and_odd_encodings_are_tolerated(self):
        good = [us.user("2026-03-05T10:00:00Z"), us.assistant("m1", self.TS)]
        variants = {
            "lineas no objeto": [good[0], "[1,2]", "null", "7", '"texto"', good[1]],
            "CRLF": [__import__("json").dumps(item) + "\r" for item in good],
            "BOM": [b"\xef\xbb\xbf" + __import__("json").dumps(good[0]).encode()] + [good[1]],
        }
        for label, items in variants.items():
            tree, proj = self.one_call_tree(lambda t, f, items=items: t.subagent(f, "s1", "a0", items))
            code, out, err = self.stdout_project(tree, proj, "--all")
            self.assertEqual(code, 0, (label, err))
            self.assertEqual(calls_in(out), 1, label)
            self.assertNotIn("no previsto", err, label)

    def test_unknown_schema_variants_are_exit_3_with_nothing_written_and_no_leak(self):
        bad_meta = [b"\xff\xfe", b"", b"[]", b'{"agentType": 5}', b'{"toolUseId": "x"}']
        variants = {}
        for i, raw in enumerate(bad_meta):
            variants["meta %d" % i] = dict(items=self.lines(us.assistant("m1", self.TS)), meta=raw)
        variants["usage objeto vacio"] = dict(items=self.lines(us.assistant("m1", self.TS, usage_value={})))
        variants["falta un campo de tokens"] = dict(
            items=self.lines(us.assistant("m1", self.TS, usage_value={"input_tokens": 1})))
        variants["token bool"] = dict(items=self.lines(us.assistant("m1", self.TS, usage_value=us.usage(inp=True))))
        variants["token negativo"] = dict(items=self.lines(us.assistant("m1", self.TS, usage_value=us.usage(out=-1))))
        variants["token flotante"] = dict(items=self.lines(us.assistant("m1", self.TS, usage_value=us.usage(cache_r=1.5))))
        # `usage: null` esta presente y no es objeto: segun 3.4 es esquema desconocido (falla cerrado)
        variants["usage nulo"] = dict(items=self.lines(self.assistant_with(usage=None)))
        variants["usage lista"] =dict(items=self.lines(us.assistant("m1", self.TS, usage_value=[1])))
        variants["timestamp entero"] = dict(items=[us.user(1700000000), us.assistant("m1", self.TS)])
        variants["timestamp ausente"] = dict(
            items=[{k: v for k, v in us.assistant("m1", self.TS).items() if k != "timestamp"}])
        variants["sin type"] = dict(items=[{"timestamp": self.TS, "message": {"content": us.M_CONTENT}}])
        for label, spec in variants.items():
            hostile = [dict(item, gitBranch=us.M_BRANCH, cwd=us.M_CWD) if isinstance(item, dict) else item
                       for item in spec["items"]]
            meta = spec.get("meta", {"agentType": us.M_TYPE, "toolUseId": "t", "description": us.M_DESCRIPTION})
            tree, proj = self.one_call_tree(
                lambda t, f, h=hostile, m=meta: t.subagent(f, us.M_SESSION, "a0", h, meta=m))
            before = tur.snapshot(self.base)
            for argv in (("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all"),
                         ("global", "--claude-dir", tree.claude_dir, "--all"),
                         ("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all", "--stdout")):
                code, out, err = self.run_main(*argv)
                self.assertEqual(code, 3, (label, argv[0], err))
                self.assertEqual(out, "", label)
                self.assertTrue(err.startswith("error: esquema desconocido"), (label, err))
                for marker in us.ALL_MARKERS:
                    self.assertNotIn(marker, err, (label, marker))
            self.assertEqual(tur.snapshot(self.base), before, label)

    def test_exit_3_message_sanitizes_hostile_versions_of_failing_and_healthy_files(self):
        def build(tree, folder):
            tree.subagent(folder, "s1", "ok", [us.user("2026-03-05T10:00:00Z", version=us.M_VERSION),
                                                us.assistant("m1", self.TS, version=us.M_VERSION, model=us.M_MODEL)],
                          meta={"agentType": us.M_TYPE})
            tree.subagent(folder, "s1", "bad", [us.user("2026-03-05T10:00:00Z", version=us.M_VERSION),
                                                 us.assistant("m2", self.TS, version=us.M_VERSION, usage_value="x")])
        tree, proj = self.one_call_tree(build)
        code, out, err = self.stdout_project(tree, proj, "--all")
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertNotIn("ZZMARK", err)
        self.assertNotIn(us.M_VERSION.split()[0], err)


class TruncatedAndDamagedEndToEnd(EdgeBase):
    def test_truncated_last_line_in_every_file_is_never_damage_and_is_reported(self):
        def build(tree, folder):
            for i in range(12):
                tree.subagent(folder, "s%d" % i, "a%d" % i,
                              [us.user("2026-03-05T10:00:00Z"), us.assistant("m%d" % i, "2026-03-05T10:00:05Z"),
                               '{"type": "assistant", "timestamp": "2026-03-05T10:00:09Z", "message": {"con'],
                              final_newline=False)
        tree, proj = self.one_call_tree(build)
        for argv in (("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all", "--stdout"),
                     ("global", "--claude-dir", tree.claude_dir, "--all", "--stdout")):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 0, err)
            self.assertEqual(calls_in(out), 12)
            self.assertRegex(out, r"`archivos con ultima linea truncada`\s*\|\s*12 \|")
            self.assertNotIn("ZZMARK", out + err)

    def _damaged(self, tree, folder, count, day, prefix):
        for i in range(count):
            tree.subagent(folder, prefix + str(i), prefix + str(i),
                          [us.user(day + "T10:00:00Z"), "esto no es json " + us.M_CONTENT,
                           us.assistant(prefix + "m%d" % i, day + "T10:00:05Z")])

    def test_damage_threshold_is_measured_on_the_window_not_on_the_whole_history(self):
        def build(tree, folder):
            self.add_calls(tree, folder, count=20, day="2026-03-05", prefix="g")
            self._damaged(tree, folder, 30, "2025-01-10", "old")   # 60 % del historial, 0 % de la ventana
        tree, proj = self.one_call_tree(build)
        for argv in (("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *tcli.WIN),
                     ("global", "--claude-dir", tree.claude_dir, *tcli.WIN)):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 0, err)
            self.assertIn("20 llamadas", out)
        code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all")
        self.assertEqual(code, 3)

    def test_threshold_boundary_one_of_twenty_passes_two_of_twenty_fails(self):
        for damaged, expected in ((1, 0), (2, 3)):
            proj = self.make_project("proy %d" % damaged)
            tree = us.Tree(self.base, claude_name="claude %d" % damaged)
            folder = self.folder_of(proj)
            self.add_calls(tree, folder, count=20 - damaged, prefix="g")
            self._damaged(tree, folder, damaged, "2026-03-06", "bad")
            code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *tcli.WIN)
            self.assertEqual(code, expected, (damaged, err))
            if expected == 0:
                self.assertIn("20 llamadas", out)
            else:
                self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))
            self.assertNotIn("ZZMARK", out + err)


class InterruptEndToEnd(EdgeBase):
    def test_ctrl_c_in_any_phase_is_exit_130_without_output_or_files(self):
        tree, proj = self.one_call_tree(lambda t, f: self.add_calls(t, f, count=2))
        before = tur.snapshot(self.base)
        for phase in ("read_calls", "_aggregate", "render_project_report", "render_global_report"):
            for argv in (("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *tcli.WIN),
                         ("global", "--claude-dir", tree.claude_dir, *tcli.WIN),
                         ("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--stdout", *tcli.WIN)):
                if phase == "render_project_report" and argv[0] != "project":
                    continue
                if phase == "render_global_report" and argv[0] != "global":
                    continue
                with mock.patch.object(ur, phase, side_effect=KeyboardInterrupt):
                    code, out, err = self.run_main(*argv)
                self.assertEqual(code, 130, (phase, argv[0]))
                self.assertEqual(out, "", (phase, argv[0]))
                self.assertEqual(err, "interrumpido\n", (phase, argv[0]))
                self.assertEqual(tur.snapshot(self.base), before, (phase, argv[0]))


class LangPrivacyEndToEnd(tcli.CliBase):
    """Caso 42: las pruebas de «sin fuga» y «sin rutas sin --show-paths», repetidas con `--lang en`; los mensajes de la
    CLI siguen en espanol."""

    _assert_clean = tcli.EndToEndNoLeak._assert_clean
    _rich = tcli.EndToEndNoLeak._rich

    def test_exit_0_reports_stdout_and_stderr_in_english(self):
        tree, proj = self._rich()
        for extra in ((), ("--stdout",), ("--stdout", "--show-paths")):
            code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj,
                                           "--all", "--lang", "en", *extra)
            self.assertEqual(code, 0, err)
            if "--show-paths" not in extra:
                self._assert_clean(out, err)
                self.assertNotIn(proj, out + err)
            else:
                self._assert_clean(out.replace(proj, ""), err)
        code, out, err = self.run_main("global", "--claude-dir", tree.claude_dir, "--all", "--lang", "en")
        self.assertEqual(code, 0, err)
        self._assert_clean(out, err)
        self.assertNotIn(tree.claude_dir, out + err)
        code, out_g, err = self.run_main("global", "--claude-dir", tree.claude_dir, "--all", "--stdout", "--lang", "en")
        self._assert_clean(out_g, err)
        project_text = self.read_bytes(self.report_path(proj)).decode("utf-8")
        global_text = self.read_bytes(os.path.join(tree.claude_dir, "synclayer-usage.md")).decode("utf-8")
        self._assert_clean(project_text, global_text, out_g)
        self.assertEqual(out_g, global_text)
        for text in (project_text, global_text):
            self.assertIn("usage report", text)
            self.assertNotIn("Reporte", text)
            self.assertNotIn("c--Users", text)
            self.assertNotIn(os.path.basename(self.base), text)
            self.assertNotIn(self.folder_of(proj), text)
            self.assertTrue(all(ch == "\n" or " " <= ch <= "~" or ch in ("█", "░") for ch in text))
        self.assertNotIn(us.M_SESSION, project_text + global_text)
        self.assertEqual(tcli.temps_under(self.base), [])

    def test_exit_1_and_3_outputs_with_lang_en_are_spanish_and_clean(self):
        tree, proj = self._rich()
        other = self.make_project("sin transcripciones " + us.M_FOLDER)
        before = tur.snapshot(self.base)
        code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", other,
                                       "--all", "--lang", "en")
        self.assertEqual(code, 1)
        self._assert_clean(out, err)
        self.assertTrue(err.startswith("error: el proyecto no tiene transcripciones"), err)
        self.assertNotIn(other, err)
        code, out, err = self.run_main("global", "--claude-dir", os.path.join(self.base, us.M_FOLDER), "--all",
                                       "--lang", "en")
        self.assertEqual(code, 1)
        self.assertNotIn(self.base, err)
        self.assertEqual(tur.snapshot(self.base), before)
        bad_base = os.path.join(self.base, "malo")
        os.makedirs(bad_base)
        proj3 = self.make_project("tres " + us.M_FOLDER)
        tree3 = us.Tree(bad_base)
        for i in range(10):
            tree3.subagent(self.folder_of(proj3), us.M_SESSION, "a%d" % i,
                           [us.user("2026-03-01T10:00:00Z"), "basura " + us.M_CONTENT])
        before = tur.snapshot(self.base)
        for argv in (["project", "--claude-dir", tree3.claude_dir, "--project-dir", proj3, "--all", "--lang", "en"],
                     ["global", "--claude-dir", tree3.claude_dir, "--all", "--lang", "en"]):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 3)
            self.assertTrue(err.startswith("error: esquema desconocido"), err)
            self._assert_clean(out, err)
        self.assertEqual(tur.snapshot(self.base), before)

    def test_username_not_in_english_output(self):
        tree, proj = self._rich()
        user = os.path.basename(os.path.expanduser("~"))
        outs = []
        for argv in (["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all", "--lang", "en"],
                     ["global", "--claude-dir", tree.claude_dir, "--all", "--lang", "en"]):
            code, out, err = self.run_main(*argv)
            outs += [out, err]
        outs.append(self.read_bytes(self.report_path(proj)).decode("utf-8"))
        outs.append(self.read_bytes(os.path.join(tree.claude_dir, "synclayer-usage.md")).decode("utf-8"))
        if len(user) > 3:
            for text in outs:
                self.assertNotIn(user.lower(), text.lower())

    def test_hostile_synthetic_names_never_break_the_english_tables_or_leak_markers(self):
        tree = tur.rich_tree(self.base)
        proj = self.make_project(us.M_FOLDER + " x")
        os.rename(os.path.join(tree.projects, "c--Users-" + us.M_FOLDER + "-proj"),
                  os.path.join(tree.projects, self.folder_of(proj)))
        code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all",
                                       "--stdout", "--lang", "en")
        self.assertEqual(code, 0, err)
        for block in tur.md_tables(out):
            self.assertEqual(len({tur.columns(line) for line in block}), 1, block[0])
        self._assert_clean(out, err)


if __name__ == "__main__":
    unittest.main()
