"""Pruebas de los subcomandos `project` y `global` de tools/usage_report.py (T7: escritura).

Todo corre sobre arboles SINTETICOS en carpetas temporales (`--claude-dir` y `--project-dir`
siempre explicitos); nunca se toca el ~/.claude real ni transcripciones reales.
"""

import ast
import contextlib
import datetime
import io
import os
import re
import stat
import subprocess
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_usage_report as tur  # noqa: E402
import usage_report as ur  # noqa: E402
import usage_synth as us  # noqa: E402

SCRIPT = os.path.join(ROOT, "tools", "usage_report.py")
WIN = ("--since", "2026-03-01", "--until", "2026-03-31")
TMP_NAME_RE = re.compile(r"^\.(\.gitignore|usage-report\.md|synclayer-usage\.md)\.[0-9a-f]{16}\.tmp\Z")


def temps_under(path):
    found = []
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            if name.endswith(".tmp"):
                found.append(os.path.join(dirpath, name))
    return found


class CliBase(tur.Base):
    def make_project(self, name="mi proyecto"):
        path = os.path.join(self.base, name)
        os.makedirs(path, exist_ok=True)
        return path

    def folder_of(self, proj):
        return us.folder_name_for(os.path.abspath(proj))

    def add_calls(self, tree, folder, count=2, session="s1", day="2026-03-05", prefix="a"):
        for i in range(count):
            tree.subagent(folder, session, "%s%d" % (prefix, i), [
                us.user("%sT10:00:00Z" % day),
                us.assistant("%s-m%d" % (prefix, i), "%sT10:00:%02dZ" % (day, i + 1)),
            ])

    def project_tree(self, count=2, proj=None):
        proj = proj or self.make_project()
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj), count)
        return tree, proj

    def project(self, tree, proj, *extra, win=True):
        args = ["project", "--claude-dir", tree.claude_dir, "--project-dir", proj]
        if win:
            args += list(WIN)
        return self.run_main(*args, *extra)

    def glob(self, tree, *extra, win=True):
        args = ["global", "--claude-dir", tree.claude_dir]
        if win:
            args += list(WIN)
        return self.run_main(*args, *extra)

    @staticmethod
    def report_path(proj):
        return os.path.join(proj, ".synclayer", "usage-report.md")

    @staticmethod
    def read_bytes(path):
        with open(path, "rb") as f:
            return f.read()


class CommandLineShape(CliBase):
    def test_no_out_flag_and_fixed_destinations(self):
        tree, proj = self.project_tree()
        for sub in ("project", "global"):
            code, out, err = self.run_main(sub, "--claude-dir", tree.claude_dir, "--out", "x")
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
        help_text = ur._build_parser().format_help()
        self.assertNotIn("--out", help_text)

    def test_window_flags_validation(self):
        tree, proj = self.project_tree()
        base = ["project", "--claude-dir", tree.claude_dir, "--project-dir", proj]
        for extra in (["--all", "--since", "2026-03-01"], ["--all", "--until", "2026-03-31"],
                      ["--since", "2026-13-40"], ["--since", "20260301"], ["--until", "manana"],
                      ["--since", "2026-04-01", "--until", "2026-03-01"]):
            code, out, err = self.run_main(*base, *extra)
            self.assertEqual(code, 2, extra)
            self.assertEqual(out, "")
            self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))
            self.assertNotIn("Traceback", err)
        self.assertEqual(self.run_main(*base, "--all")[0], 0)

    def test_default_window_is_last_30_days_ending_today(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        folder = self.folder_of(proj)
        self.add_calls(tree, folder, count=1, day="2026-03-05", session="s1", prefix="a")
        self.add_calls(tree, folder, count=1, day="2026-02-01", session="s2", prefix="b")
        with mock.patch.object(ur, "utc_today", return_value=datetime.date(2026, 3, 31)):
            code, out, err = self.project(tree, proj, "--stdout", win=False)
        self.assertEqual(code, 0, err)
        self.assertIn("> - Ventana: 2026-03-02 a 2026-03-31", out)
        self.assertIn("> - Llamadas: 1 en 1 sesi\u00f3n", out)

    def test_project_dir_defaults_to_current_directory(self):
        tree, proj = self.project_tree()
        with mock.patch.object(ur.os, "getcwd", return_value=proj):
            code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, *WIN)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(self.report_path(proj)))


class ProjectWrites(CliBase):
    def test_writes_report_and_exact_gitignore(self):
        tree, proj = self.project_tree()
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_bytes(os.path.join(proj, ".synclayer", ".gitignore")), b"*\n")
        text = self.read_bytes(self.report_path(proj)).decode("utf-8")
        self.assertTrue(text.startswith(ur.REPORT_MARKER + "\n"))
        self.assertIn("> - Llamadas: 2 en 1 sesi\u00f3n", text)
        self.assertEqual(sorted(os.listdir(os.path.join(proj, ".synclayer"))), [".gitignore", "usage-report.md"])
        self.assertEqual(temps_under(self.base), [])
        self.assertEqual(err, "")

    def test_final_message_has_no_path_without_show_paths(self):
        tree, proj = self.project_tree()
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("reporte de proyecto escrito"), out)
        self.assertIn("2 llamadas", out)
        for text in (out, err):
            for bad in (self.base, os.path.basename(self.base), "usage-report", ".synclayer", "mi proyecto"):
                self.assertNotIn(bad, text)
        code, out, err = self.project(tree, proj, "--show-paths")
        self.assertEqual(code, 0)
        self.assertIn(self.report_path(proj), out)

    def test_overwrites_own_report_and_is_deterministic(self):
        tree, proj = self.project_tree()
        with mock.patch.object(ur, "utc_today", return_value=datetime.date(2026, 4, 1)):
            self.assertEqual(self.project(tree, proj)[0], 0)
            first = self.read_bytes(self.report_path(proj))
            self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertEqual(self.read_bytes(self.report_path(proj)), first)
        self.assertEqual(temps_under(self.base), [])

    def test_empty_window_is_exit_0_and_writes(self):
        tree, proj = self.project_tree()
        code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj,
                                       "--since", "2030-01-01", "--until", "2030-01-31")
        self.assertEqual(code, 0, err)
        self.assertIn("0 llamadas", out)
        self.assertTrue(os.path.isfile(self.report_path(proj)))

    def test_existing_exact_gitignore_is_left_alone(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        gi = os.path.join(sdir, ".gitignore")
        with open(gi, "wb") as f:
            f.write(b"*\n")
        before = os.stat(gi).st_mtime_ns
        self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertEqual(os.stat(gi).st_mtime_ns, before)
        self.assertEqual(self.read_bytes(gi), b"*\n")

    def test_gitignore_must_be_exactly_star_newline(self):
        # una linea `*` mas `!usage-report.md` volveria a incluir el reporte: exit 1 y no se edita
        for content in (b"*\n!usage-report.md\n", b"*", b"*\r\n", b"\n*\n", b"", b"# x\n*\n", b"**\n",
                        b"*\n\n", b"/*\n"):
            with self.subTest(content=content):
                proj = self.make_project("p%d" % abs(hash(content)))
                tree = us.Tree(os.path.join(self.base, "t%d" % abs(hash(content))))
                self.add_calls(tree, self.folder_of(proj))
                sdir = os.path.join(proj, ".synclayer")
                os.makedirs(sdir)
                gi = os.path.join(sdir, ".gitignore")
                with open(gi, "wb") as f:
                    f.write(content)
                code, out, err = self.project(tree, proj)
                self.assertEqual(code, 1)
                self.assertIn("gitignore", err)
                self.assertEqual(self.read_bytes(gi), content)
                self.assertFalse(os.path.exists(self.report_path(proj)))
                self.assertEqual(temps_under(proj), [])

    def test_gitignore_symlink_or_directory_refused(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(os.path.join(sdir, ".gitignore"))   # una carpeta, no un archivo
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(self.report_path(proj)))

    def test_foreign_destination_not_overwritten(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        for content in (b"# mis notas\n", b"", b" " + ur.REPORT_MARKER.encode() + b"\n",
                        ur.REPORT_MARKER.encode() + b" extra\n", ur.REPORT_MARKER.encode() + b"\rX\n",
                        b"\xef\xbb\xbf" + ur.REPORT_MARKER.encode() + b"\n",
                        ur.REPORT_MARKER.encode()[:-1] + b"\n"):
            with self.subTest(content=content):
                with open(self.report_path(proj), "wb") as f:
                    f.write(content)
                created = []
                real_open = os.open

                def spy(path, flags, *a, **k):
                    if flags & os.O_CREAT:
                        created.append(path)
                    return real_open(path, flags, *a, **k)

                with mock.patch.object(ur.os, "open", spy):
                    code, out, err = self.project(tree, proj)
                self.assertEqual(code, 1)
                self.assertEqual(self.read_bytes(self.report_path(proj)), content)
                self.assertEqual(temps_under(proj), [])
                # el destino ajeno se detecta ANTES de crear nada (ni .gitignore ni temporal)
                self.assertEqual(os.listdir(sdir), ["usage-report.md"])
                self.assertEqual(created, [])

    def test_marked_destination_is_overwritten_without_backup(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        for first in (ur.REPORT_MARKER.encode() + b"\n" + b"viejo\n" * 10,
                      ur.REPORT_MARKER.encode() + b"\r\nviejo\r\n",
                      ur.REPORT_MARKER.encode()):
            with self.subTest(first=first[:40]):
                with open(self.report_path(proj), "wb") as f:
                    f.write(first)
                code, out, err = self.project(tree, proj)
                self.assertEqual(code, 0, err)
                self.assertNotIn(b"viejo", self.read_bytes(self.report_path(proj)))
                self.assertEqual(sorted(os.listdir(sdir)), [".gitignore", "usage-report.md"])

    def test_marker_read_is_bounded(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        with open(self.report_path(proj), "wb") as f:
            f.write(ur.REPORT_MARKER.encode() + b"\n" + b"x" * (3 * 1024 * 1024))
        reads = []
        real = ur._open_regular

        class Spy:
            def __init__(self, f):
                self.f = f

            def read(self, *a):
                reads.append(a)
                return self.f.read(*a)

            def __getattr__(self, name):
                return getattr(self.f, name)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

        def spy(path, *a, **k):
            f = real(path, *a, **k)
            return Spy(f) if os.path.basename(path) == "usage-report.md" else f

        with mock.patch.object(ur, "_open_regular", spy):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0, err)
        self.assertTrue(reads)
        for a in reads:
            self.assertEqual(len(a), 1)
            self.assertIsInstance(a[0], int)
            self.assertLessEqual(a[0], 256)

    def test_foreign_destination_error_has_no_path_unless_asked(self):
        tree, proj = self.project_tree()
        os.makedirs(os.path.join(proj, ".synclayer"))
        with open(self.report_path(proj), "wb") as f:
            f.write(b"ajeno")
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertNotIn(self.base, err)
        self.assertNotIn(".synclayer", err)
        code, out, err = self.project(tree, proj, "--show-paths")
        self.assertEqual(code, 1)
        self.assertIn(self.report_path(proj), err)


class OnlyAllowedWrites(CliBase):
    def _record(self):
        calls, opens = [], []
        real_os_open, real_open = os.open, open

        def fake_os_open(path, flags, *a, **k):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                calls.append((os.fspath(path), flags, a[0] if a else k.get("mode", 0o777)))
            return real_os_open(path, flags, *a, **k)

        def fake_open(file, mode="r", *a, **k):
            if any(c in mode for c in "wax+"):
                opens.append(file)
            return real_open(file, mode, *a, **k)

        return calls, opens, fake_os_open, fake_open

    def test_only_temp_files_inside_the_fixed_folders_are_opened_for_writing(self):
        tree, proj = self.project_tree()
        calls, opens, fake_os_open, fake_open = self._record()
        with mock.patch.object(ur.os, "open", fake_os_open), mock.patch("builtins.open", fake_open):
            self.assertEqual(self.project(tree, proj)[0], 0)
            self.assertEqual(self.glob(tree)[0], 0)
        self.assertEqual(opens, [])
        self.assertEqual(len(calls), 3)   # .gitignore, usage-report.md y synclayer-usage.md (todos temporales)
        folders = {os.path.dirname(c[0]) for c in calls}
        self.assertEqual(folders, {os.path.join(proj, ".synclayer"), tree.claude_dir})
        for path, flags, mode in calls:
            self.assertRegex(os.path.basename(path), TMP_NAME_RE)
            self.assertTrue(flags & os.O_CREAT and flags & os.O_EXCL, path)
            self.assertFalse(flags & os.O_TRUNC)
            self.assertEqual(mode, 0o600)

    def test_stdout_mode_opens_nothing_for_writing(self):
        tree, proj = self.project_tree()
        calls, opens, fake_os_open, fake_open = self._record()
        before = (tur.snapshot(self.base))
        with mock.patch.object(ur.os, "open", fake_os_open), mock.patch("builtins.open", fake_open):
            self.assertEqual(self.project(tree, proj, "--stdout")[0], 0)
            self.assertEqual(self.glob(tree, "--stdout")[0], 0)
        self.assertEqual(calls, [])
        self.assertEqual(opens, [])
        self.assertEqual(tur.snapshot(self.base), before)

    def test_temp_names_are_random(self):
        tree, proj = self.project_tree()
        names = []
        real = os.open

        def spy(path, flags, *a, **k):
            if flags & os.O_CREAT:
                names.append(os.path.basename(os.fspath(path)))
            return real(path, flags, *a, **k)

        for _ in range(2):
            with mock.patch.object(ur.os, "open", spy):
                self.assertEqual(self.project(tree, proj)[0], 0)
        report_tmps = [n for n in names if "usage-report.md" in n]
        self.assertEqual(len(report_tmps), 2)
        self.assertNotEqual(report_tmps[0], report_tmps[1])

    def test_no_subprocess_and_no_out_in_source(self):
        with open(SCRIPT, "rb") as f:
            src = f.read().decode("utf-8")
        self.assertNotIn("import subprocess", src)
        self.assertNotIn("os.system", src)
        self.assertEqual(src.count("os.O_WRONLY"), 1)   # un solo sitio abre para escribir
        self.assertNotIn('"--out"', src)


class Atomicity(CliBase):
    def test_replace_failure_leaves_nothing(self):
        # en Windows `os.replace` falla si otro proceso tiene el destino abierto: exit 1 sin restos
        tree, proj = self.project_tree()
        before = tur.snapshot(proj)
        with mock.patch.object(ur.os, "replace", side_effect=PermissionError(13, us.M_CONTENT)):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertNotIn(us.M_CONTENT, out + err)
        self.assertIn("reemplaz", err)
        self.assertEqual(tur.snapshot(proj), before)   # ni .synclayer ni temporales
        self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))

    def test_replace_failure_keeps_old_report_and_removes_temp(self):
        tree, proj = self.project_tree()
        self.assertEqual(self.project(tree, proj)[0], 0)
        old = self.read_bytes(self.report_path(proj))
        with mock.patch.object(ur.os, "replace", side_effect=PermissionError(13, "x")):
            code, out, err = self.project(tree, proj, "--all", win=False)
        self.assertEqual(code, 1)
        self.assertEqual(self.read_bytes(self.report_path(proj)), old)
        self.assertEqual(temps_under(proj), [])
        self.assertTrue(os.path.isdir(os.path.join(proj, ".synclayer")))   # no era nuestra: se conserva

    def test_global_replace_failure_leaves_nothing(self):
        tree, proj = self.project_tree()
        before = tur.snapshot(tree.claude_dir)
        with mock.patch.object(ur.os, "replace", side_effect=PermissionError(13, "x")):
            code, out, err = self.glob(tree)
        self.assertEqual(code, 1)
        self.assertEqual(tur.snapshot(tree.claude_dir), before)

    @unittest.skipUnless(os.name == "nt", "el bloqueo de un archivo abierto es propio de Windows")
    def test_destination_open_in_another_handle_windows(self):
        tree, proj = self.project_tree()
        self.assertEqual(self.project(tree, proj)[0], 0)
        old = self.read_bytes(self.report_path(proj))
        with open(self.report_path(proj), "rb"):
            code, out, err = self.project(tree, proj, "--all", win=False)
        self.assertEqual(code, 1, err)
        self.assertIn("reemplaz", err)
        self.assertEqual(self.read_bytes(self.report_path(proj)), old)
        self.assertEqual(temps_under(proj), [])

    def test_write_error_mid_way_removes_the_temp(self):
        tree, proj = self.project_tree()
        with mock.patch.object(ur.os, "write", side_effect=OSError(28, us.M_CONTENT)):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertNotIn(us.M_CONTENT, out + err)
        self.assertEqual(tur.snapshot(proj), [])

    def test_keyboard_interrupt_during_write_removes_temp_and_folder(self):
        tree, proj = self.project_tree()
        with mock.patch.object(ur.os, "replace", side_effect=KeyboardInterrupt):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 130)
        self.assertEqual(tur.snapshot(proj), [])

    def _swap_lstat(self, target):
        """Tras crear el temporal, el primer lstat de `target` devuelve un enlace simbolico simulado."""
        real_lstat, real_open = os.lstat, os.open
        state = {"armed": False, "done": False}
        norm = os.path.normcase(os.path.abspath(target))

        def fake_open(path, flags, *a, **k):
            fd = real_open(path, flags, *a, **k)
            if os.fspath(path).endswith(".tmp"):
                state["armed"] = True
            return fd

        def fake_lstat(path, *a, **k):
            if state["armed"] and not state["done"] and os.path.normcase(os.path.abspath(os.fspath(path))) == norm:
                state["done"] = True
                return os.stat_result((stat.S_IFLNK | 0o777,) + (0,) * 9)
            return real_lstat(path, *a, **k)

        return state, fake_open, fake_lstat

    def test_lstat_repeated_before_replace_project_synclayer_projectdir_claudedir(self):
        # (el reporte de proyecto no escribe en claude-dir: su repeticion se prueba en el global)
        old = ur.REPORT_MARKER.encode() + b"\nviejo\n"
        for which in ("synclayer", "project"):
            with self.subTest(which=which):
                base = os.path.join(self.base, which)
                os.makedirs(base)
                proj = os.path.join(base, "proj")
                sdir = os.path.join(proj, ".synclayer")
                os.makedirs(sdir)
                with open(os.path.join(sdir, ".gitignore"), "wb") as f:
                    f.write(b"*\n")
                with open(os.path.join(sdir, "usage-report.md"), "wb") as f:
                    f.write(old)
                tree = us.Tree(base)
                self.add_calls(tree, self.folder_of(proj))
                target = sdir if which == "synclayer" else proj
                state, fake_open, fake_lstat = self._swap_lstat(target)
                with mock.patch.object(ur.os, "open", fake_open), mock.patch.object(ur.os, "lstat", fake_lstat):
                    code, out, err = self.project(tree, proj)
                self.assertTrue(state["done"], which)
                self.assertEqual(code, 1, err)
                self.assertEqual(sorted(os.listdir(sdir)), [".gitignore", "usage-report.md"])
                self.assertEqual(self.read_bytes(os.path.join(sdir, "usage-report.md")), old)
                self.assertEqual(temps_under(proj), [])

    def test_lstat_repeated_before_replace_global_claude_dir(self):
        tree, proj = self.project_tree()
        before = tur.snapshot(tree.claude_dir)
        state, fake_open, fake_lstat = self._swap_lstat(tree.claude_dir)
        with mock.patch.object(ur.os, "open", fake_open), mock.patch.object(ur.os, "lstat", fake_lstat):
            code, out, err = self.glob(tree)
        self.assertTrue(state["done"])
        self.assertEqual(code, 1, err)
        self.assertEqual(tur.snapshot(tree.claude_dir), before)

    def test_destination_replaced_by_foreign_file_before_replace(self):
        # el marcador se vuelve a comprobar justo antes del reemplazo
        tree, proj = self.project_tree()
        self.assertEqual(self.project(tree, proj)[0], 0)
        real_fsync = os.fsync

        def swap(fd):
            real_fsync(fd)
            with open(self.report_path(proj), "wb") as f:
                f.write(b"ajeno")

        with mock.patch.object(ur.os, "fsync", swap):
            code, out, err = self.project(tree, proj, "--all", win=False)
        self.assertEqual(code, 1)
        self.assertEqual(self.read_bytes(self.report_path(proj)), b"ajeno")
        self.assertEqual(temps_under(proj), [])


class Permissions(CliBase):
    def test_mode_0600_passed_to_os_open_for_every_created_file(self):
        tree, proj = self.project_tree()
        modes = []
        real = os.open

        def spy(path, flags, *a, **k):
            if flags & os.O_CREAT:
                modes.append(a[0] if a else k.get("mode"))
            return real(path, flags, *a, **k)

        with mock.patch.object(ur.os, "open", spy):
            self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertEqual(modes, [0o600, 0o600])

    def test_fchmod_called_with_0600_when_available(self):
        # `create=True`: en Windows `os.fchmod` no existe; el codigo lo usa si esta (hasattr)
        tree, proj = self.project_tree()
        with mock.patch.object(ur.os, "fchmod", create=True) as fchmod:
            self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertEqual([c.args[1] for c in fchmod.call_args_list], [0o600, 0o600])

    @unittest.skipUnless(os.name == "posix", "los permisos POSIX no existen en Windows")
    def test_file_is_0600_even_with_umask_zero(self):
        tree, proj = self.project_tree()
        old = os.umask(0)
        try:
            self.assertEqual(self.project(tree, proj)[0], 0)
            self.assertEqual(self.glob(tree)[0], 0)
        finally:
            os.umask(old)
        for path in (self.report_path(proj), os.path.join(tree.claude_dir, "synclayer-usage.md"),
                     os.path.join(proj, ".synclayer", ".gitignore")):
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600, path)

    @unittest.skipUnless(hasattr(os, "fchmod"), "sin fchmod")
    def test_fchmod_called_before_writing(self):
        tree, proj = self.project_tree()
        order = []
        real_fchmod, real_write = os.fchmod, os.write

        def fchmod(fd, mode):
            order.append(("chmod", mode))
            return real_fchmod(fd, mode)

        def write(fd, data):
            order.append(("write", 0))
            return real_write(fd, data)

        with mock.patch.object(ur.os, "fchmod", fchmod), mock.patch.object(ur.os, "write", write):
            self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertEqual(order[0], ("chmod", 0o600))
        self.assertIn(("write", 0), order)


class BytesAndStdout(CliBase):
    def test_written_report_is_utf8_lf_without_bom(self):
        tree, proj = self.project_tree()
        self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertEqual(self.glob(tree)[0], 0)
        for path in (self.report_path(proj), os.path.join(tree.claude_dir, "synclayer-usage.md")):
            data = self.read_bytes(path)
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"\r", data)
            self.assertTrue(data.endswith(b"\n"))
            self.assertTrue(data.startswith(ur.REPORT_MARKER.encode("ascii") + b"\n"))
            self.assertIn("\u2588".encode("utf-8"), data)   # barras: UTF-8, no cp1252
            data.decode("utf-8")

    def test_stdout_writes_utf8_bytes_to_buffer_and_no_files(self):
        tree, proj = self.project_tree()
        before = tur.snapshot(self.base)
        # una consola cp1252 con traduccion de saltos: por `print` fallaria o daria CRLF
        for argv in (("project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *WIN, "--stdout"),
                     ("global", "--claude-dir", tree.claude_dir, *WIN, "--stdout")):
            wrapper = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\r\n")
            err = io.StringIO()
            with contextlib.redirect_stdout(wrapper), contextlib.redirect_stderr(err):
                code = ur.main(list(argv))
            self.assertEqual(code, 0, err.getvalue())
            data = wrapper.buffer.getvalue()
            self.assertTrue(data.startswith(ur.REPORT_MARKER.encode("ascii") + b"\n"))
            self.assertNotIn(b"\r", data)
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
            self.assertIn("\u2588".encode("utf-8"), data)
            data.decode("utf-8")
            self.assertEqual(err.getvalue(), "")
        self.assertEqual(tur.snapshot(self.base), before)
        self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))

    def test_stdout_flushes_the_buffer(self):
        tree, proj = self.project_tree()

        class Out:
            def __init__(self):
                self.buffer = mock.Mock()

            def write(self, text):
                raise AssertionError("print/write de texto: debe usar .buffer")

            def flush(self):
                pass

        out = Out()
        with mock.patch.object(sys, "stdout", out):
            code = ur.main(["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *WIN, "--stdout"])
        self.assertEqual(code, 0)
        out.buffer.write.assert_called_once()
        out.buffer.flush.assert_called()

    def test_subprocess_stdout_bytes(self):
        tree, proj = self.project_tree()
        for argv in (["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *WIN, "--stdout"],
                     ["global", "--claude-dir", tree.claude_dir, *WIN, "--stdout"]):
            proc = subprocess.run([sys.executable, "-B", SCRIPT, *argv], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stderr, b"")
            self.assertTrue(proc.stdout.startswith(ur.REPORT_MARKER.encode("ascii") + b"\n"))
            self.assertNotIn(b"\r", proc.stdout)
            self.assertIn("\u2588".encode("utf-8"), proc.stdout)
            proc.stdout.decode("utf-8")
        self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))
        self.assertEqual(os.listdir(tree.claude_dir), ["projects"])

    def test_subprocess_write_and_no_pycache(self):
        tree, proj = self.project_tree()
        proc = subprocess.run([sys.executable, "-B", SCRIPT, "project", "--claude-dir", tree.claude_dir,
                               "--project-dir", proj, *WIN], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.isfile(self.report_path(proj)))
        self.assertNotIn(self.base.encode(), proc.stdout + proc.stderr)


class FailuresWriteNothing(CliBase):
    """Casos 16 y riesgo 9: exit 1 o 3 no dejan `.synclayer/` ni temporales y no crean carpetas."""

    def test_missing_projects_dir(self):
        proj = self.make_project()
        claude = os.path.join(self.base, "claude sin projects")
        os.makedirs(claude)
        before = tur.snapshot(self.base)
        for argv in (["project", "--claude-dir", claude, "--project-dir", proj, *WIN],
                     ["global", "--claude-dir", claude, *WIN]):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 1)
            self.assertIn("projects", err)
            self.assertEqual(out, "")
        self.assertEqual(tur.snapshot(self.base), before)

    def test_missing_claude_dir_is_not_created(self):
        proj = self.make_project()
        claude = os.path.join(self.base, "no existe")
        for argv in (["project", "--claude-dir", claude, "--project-dir", proj, *WIN],
                     ["global", "--claude-dir", claude, *WIN]):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(claude))
        self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))

    def test_missing_project_dir_is_not_created(self):
        tree = us.Tree(self.base)
        proj = os.path.join(self.base, "no existe")
        self.add_calls(tree, self.folder_of(proj))
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(proj))

    def test_project_without_transcripts_hints_at_transcripts_dir(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        self.add_calls(tree, "c--otro-proyecto")
        before = tur.snapshot(self.base)
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertIn("--transcripts-dir", err)
        self.assertEqual(out, "")
        self.assertEqual(tur.snapshot(self.base), before)

    def test_global_without_any_transcripts(self):
        tree = us.Tree(self.base)
        before = tur.snapshot(self.base)
        code, out, err = self.glob(tree)
        self.assertEqual(code, 1)
        self.assertEqual(tur.snapshot(self.base), before)

    def test_unknown_schema_exit_3_writes_nothing(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        folder = self.folder_of(proj)
        for i in range(10):
            tree.subagent(folder, "s1", "a%d" % i, [us.user("2026-03-01T10:00:00Z"), "basura " + us.M_CONTENT])
        before = tur.snapshot(self.base)
        for argv in (["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all"],
                     ["global", "--claude-dir", tree.claude_dir, "--all"],
                     ["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all", "--stdout"]):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 3)
            self.assertEqual(out, "")
            self.assertNotIn(us.M_CONTENT, err)
        self.assertEqual(tur.snapshot(self.base), before)

    def test_schema_error_in_reader_exit_3(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        tree.subagent(self.folder_of(proj), "s1", "a1", [us.assistant("m1", "2026-03-01T10:00:00Z", usage_value="x")])
        before = tur.snapshot(self.base)
        code, out, err = self.project(tree, proj, "--all", win=False)
        self.assertEqual(code, 3)
        self.assertEqual(tur.snapshot(self.base), before)

    def test_unexpected_error_is_class_name_only(self):
        tree, proj = self.project_tree()
        before = tur.snapshot(self.base)
        for target in ("aggregate_calls", "render_project_report", "render_global_report"):
            argv = (["global", "--claude-dir", tree.claude_dir, *WIN] if "global" in target else
                    ["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *WIN])
            with mock.patch.object(ur, target, side_effect=ValueError(us.M_CONTENT + us.M_CWD)):
                code, out, err = self.run_main(*argv)
            self.assertEqual(code, 1)
            self.assertEqual(err, "error: error no previsto (ValueError)\n")
            self.assertEqual(out, "")
        self.assertEqual(tur.snapshot(self.base), before)


class LinksRefused(CliBase):
    """Caso 18 y riesgo 1: enlaces y junctions no se siguen."""

    def _link(self, target, link, is_dir=True):
        if not self.make_link(target, link, is_dir):
            self.skipTest("el sistema no deja crear el enlace")

    def test_synclayer_link_refused_and_target_untouched(self):
        tree, proj = self.project_tree()
        elsewhere = os.path.join(self.base, "otro lugar")
        os.makedirs(elsewhere)
        self._link(elsewhere, os.path.join(proj, ".synclayer"))
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertEqual(os.listdir(elsewhere), [])
        self.assertEqual(temps_under(self.base), [])

    def test_destination_link_refused_and_target_untouched(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        victim = os.path.join(self.base, "victima.txt")
        with open(victim, "wb") as f:
            f.write(ur.REPORT_MARKER.encode() + b"\ncontenido ajeno\n")
        self._link(victim, self.report_path(proj), is_dir=False)
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertEqual(self.read_bytes(victim), ur.REPORT_MARKER.encode() + b"\ncontenido ajeno\n")
        self.assertEqual(temps_under(self.base), [])

    def test_gitignore_link_refused(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        victim = os.path.join(self.base, "victima.txt")
        with open(victim, "wb") as f:
            f.write(b"*\n")
        self._link(victim, os.path.join(sdir, ".gitignore"), is_dir=False)
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(self.report_path(proj)))

    def test_project_dir_link_refused(self):
        tree, proj = self.project_tree()
        link = os.path.join(self.base, "enlace al proyecto")
        self._link(proj, link)
        tree2 = us.Tree(self.base)
        self.add_calls(tree2, self.folder_of(link))
        code, out, err = self.project(tree, link)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))

    def test_claude_dir_link_refused_for_global(self):
        tree, proj = self.project_tree()
        link = os.path.join(self.base, "enlace a claude")
        self._link(tree.claude_dir, link)
        before = tur.snapshot(tree.claude_dir)
        code, out, err = self.run_main("global", "--claude-dir", link, *WIN)
        self.assertEqual(code, 1)
        self.assertEqual(tur.snapshot(tree.claude_dir), before)

    def test_global_destination_link_refused(self):
        tree, proj = self.project_tree()
        victim = os.path.join(self.base, "victima.txt")
        with open(victim, "wb") as f:
            f.write(ur.REPORT_MARKER.encode() + b"\najeno\n")
        self._link(victim, os.path.join(tree.claude_dir, "synclayer-usage.md"), is_dir=False)
        code, out, err = self.glob(tree)
        self.assertEqual(code, 1)
        self.assertEqual(self.read_bytes(victim), ur.REPORT_MARKER.encode() + b"\najeno\n")

    def test_link_inside_projects_is_not_followed(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        self.add_calls(tree, "c--real-folder")
        self._link(os.path.join(tree.projects, "c--real-folder"), os.path.join(tree.projects, self.folder_of(proj)))
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))
        # el global solo lee la carpeta real
        code, out, err = self.glob(tree)
        self.assertEqual(code, 0, err)
        self.assertIn("2 llamadas", out)


class TranscriptsDir(CliBase):
    def test_extra_folder_is_read_and_counted_in_the_header(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj), count=2)
        self.add_calls(tree, "c--worktree-feature", count=3, prefix="w", session="s9")
        code, out, err = self.project(tree, proj, "--transcripts-dir", "c--worktree-feature")
        self.assertEqual(code, 0, err)
        self.assertIn("5 llamadas", out)
        text = self.read_bytes(self.report_path(proj)).decode("utf-8")
        self.assertIn("> - Carpetas de transcripciones le\u00eddas: 2", text)
        self.assertIn("> - Llamadas: 5 en 2 sesiones", text)
        # sin la opcion, solo la carpeta derivada
        code, out, err = self.project(tree, proj)
        self.assertIn("2 llamadas", out)
        text = self.read_bytes(self.report_path(proj)).decode("utf-8")
        self.assertIn("> - Carpetas de transcripciones le\u00eddas: 1", text)

    def test_repeatable_and_case_insensitive(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        self.add_calls(tree, "c--wt-uno", count=1, prefix="u", session="s1")
        self.add_calls(tree, "c--wt-dos", count=1, prefix="d", session="s2")
        code, out, err = self.project(tree, proj, "--transcripts-dir", "C--WT-UNO", "--transcripts-dir", "c--wt-dos")
        self.assertEqual(code, 0, err)
        self.assertIn("2 llamadas", out)
        self.assertIn("2 carpetas", out)

    def test_only_plain_folder_names_accepted(self):
        tree, proj = self.project_tree()
        before = tur.snapshot(self.base)
        for bad in ("..", ".", "a/b", "a\\b", os.path.abspath(tree.projects), "/etc", "C:\\x", "",
                    "con", "a b", "nombre.", "..\\..", "x" + us.M_CONTENT):
            code, out, err = self.project(tree, proj, "--transcripts-dir", bad)
            self.assertEqual(code, 2, bad)
            self.assertEqual(out, "")
            self.assertNotIn(us.M_CONTENT, err)
            self.assertNotIn(tree.projects, err)
        self.assertEqual(tur.snapshot(self.base), before)

    def test_valid_name_not_in_projects_is_exit_1(self):
        tree, proj = self.project_tree()
        before = tur.snapshot(self.base)
        code, out, err = self.project(tree, proj, "--transcripts-dir", "c--no-existe")
        self.assertEqual(code, 1)
        self.assertIn("--transcripts-dir", err)
        self.assertNotIn("c--no-existe", err)
        self.assertEqual(tur.snapshot(self.base), before)

    def test_not_accepted_by_global(self):
        tree, proj = self.project_tree()
        code, out, err = self.run_main("global", "--claude-dir", tree.claude_dir, "--transcripts-dir", "c--x")
        self.assertEqual(code, 2)

    def test_extra_folder_link_is_refused(self):
        tree, proj = self.project_tree()
        elsewhere = os.path.join(self.base, "fuera")
        os.makedirs(elsewhere)
        if not self.make_link(elsewhere, os.path.join(tree.projects, "c--enlace")):
            self.skipTest("el sistema no deja crear el enlace")
        code, out, err = self.project(tree, proj, "--transcripts-dir", "c--enlace")
        self.assertEqual(code, 1)


class FilterAndHeader(CliBase):
    def test_filter_by_folder_not_by_alias(self):
        # con una colision de alias, filtrar por alias mezclaria el volumen de otro proyecto
        proj = self.make_project()
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj), count=1, prefix="a", session="s1")
        self.add_calls(tree, "c--otro-proyecto", count=4, prefix="b", session="s2")
        with mock.patch.object(ur, "_project_alias", return_value="p-00000000"):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0, err)
        self.assertIn("1 llamada,", out)
        text = self.read_bytes(self.report_path(proj)).decode("utf-8")
        self.assertIn("> - Llamadas: 1 en 1 sesi\u00f3n", text)

    def test_without_transcripts_dir_there_is_one_alias_equal_to_the_given(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj), count=2)
        self.add_calls(tree, "c--otro-proyecto", count=3, prefix="o", session="s2")
        seen = {}
        real = ur.render_project_report

        def spy(metrics, alias, generated=None):
            seen["aliases"] = {p.project for p in metrics.projects}
            seen["alias"] = alias
            seen["folders"] = metrics.folders_read
            return real(metrics, alias, generated)

        with mock.patch.object(ur, "render_project_report", spy):
            self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertEqual(seen["aliases"], {seen["alias"]})
        self.assertEqual(seen["alias"], ur._project_alias(self.folder_of(proj)))
        self.assertEqual(seen["folders"], 1)
        text = self.read_bytes(self.report_path(proj)).decode("utf-8")
        self.assertIn("# Reporte de uso de subagentes: proyecto " + seen["alias"], text)

    def test_inconsistent_alias_is_an_error(self):
        tree, proj = self.project_tree()
        real = ur.aggregate_calls

        def agg(*a, **k):
            metrics = real(*a, **k)
            bad = ur.dataclasses.replace(metrics.projects[0], project="p-ffffffff")
            return ur.dataclasses.replace(metrics, projects=(bad,))

        with mock.patch.object(ur, "aggregate_calls", agg):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(proj, ".synclayer")))

    def test_folders_read_is_exposed_by_the_reader_and_metrics(self):
        proj = self.make_project()
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj), count=1)
        self.add_calls(tree, "c--otra", count=1, prefix="o", session="s2")
        res = ur.read_calls(tree.claude_dir, project_dir=proj, check_damage=False)
        self.assertEqual((res.folders_read, res.sessions_read), (1, 1))
        res2 = ur.read_calls(tree.claude_dir, check_damage=False)
        self.assertEqual((res2.folders_read, res2.sessions_read), (2, 2))
        self.assertEqual(ur.aggregate_calls(res2, today=datetime.date(2026, 3, 31)).folders_read, 2)
        res3 = ur.read_calls(tree.claude_dir, project_dir=proj, check_damage=False, extra_folders=["c--otra"])
        self.assertEqual(res3.folders_read, 2)
        # una lista de CallRecord no sabe cuantas carpetas se leyeron: 0 y la cabecera no lo dice
        self.assertEqual(ur.aggregate_calls(res2.calls, today=datetime.date(2026, 3, 31)).folders_read, 0)
        self.assertNotIn("Carpetas de transcripciones",
                         ur.render_project_report(ur.aggregate_calls(res2.calls, today=datetime.date(2026, 3, 31)),
                                                  "p-0a1b2c3d"))

    def test_c_and_capital_c_folders_both_read(self):
        # caso 13: en NTFS no pueden coexistir: se parchea el listado de projects/
        proj = self.make_project("proyecto con espacios")
        tree = us.Tree(self.base)
        folder = self.folder_of(proj)
        other = folder.swapcase()
        self.assertNotEqual(folder, other)
        self.add_calls(tree, folder, count=1, prefix="a", session="s1")
        if not os.path.exists(os.path.join(tree.projects, other)):
            self.add_calls(tree, other, count=1, prefix="b", session="s2")
        real_list = ur._list_dir

        def fake_list(path):
            if path == tree.projects:
                return [(folder, "dir"), (other, "dir")]
            return real_list(path)

        with mock.patch.object(ur, "_list_dir", fake_list):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0, err)
        text = self.read_bytes(self.report_path(proj)).decode("utf-8")
        self.assertIn("> - Carpetas de transcripciones le\u00eddas: 2", text)
        self.assertEqual(len(set(re.findall(r"\bp-[0-9a-f]{8}\b", text))), 1)

    def test_paths_with_spaces_and_backslashes_in_cwd_field(self):
        # los `cwd` sinteticos llevan barras invertidas y espacios; la carpeta se deriva de --project-dir
        proj = self.make_project("con espacios  y   mas")
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj), count=2)
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0, err)
        self.assertIn("2 llamadas", out)
        self.assertNotIn(us.M_CWD, self.read_bytes(self.report_path(proj)).decode("utf-8"))


class ReleaseKeyAndObjects(CliBase):
    def _spy(self):
        real = ur.ReadResult.release_key
        return mock.patch.object(ur.ReadResult, "release_key", autospec=True, side_effect=real)

    def test_release_key_called_on_success_and_on_exit_3(self):
        tree, proj = self.project_tree()
        for argv in (["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *WIN],
                     ["global", "--claude-dir", tree.claude_dir, *WIN],
                     ["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *WIN, "--stdout"]):
            with self._spy() as spy:
                self.assertEqual(self.run_main(*argv)[0], 0)
            self.assertEqual(spy.call_count, 1, argv)
        proj2 = self.make_project("otro")
        tree2 = us.Tree(os.path.join(self.base, "t2"))
        for i in range(10):
            tree2.subagent(self.folder_of(proj2), "s1", "a%d" % i, [us.user("2026-03-01T10:00:00Z"), "basura"])
        with self._spy() as spy:
            self.assertEqual(self.run_main("project", "--claude-dir", tree2.claude_dir, "--project-dir", proj2,
                                           "--all")[0], 3)
        self.assertEqual(spy.call_count, 1)

    def test_release_key_called_when_aggregation_fails_unexpectedly(self):
        tree, proj = self.project_tree()
        with self._spy() as spy, mock.patch.object(ur, "aggregate_calls", side_effect=ValueError("x")):
            self.assertEqual(self.project(tree, proj)[0], 1)
        self.assertEqual(spy.call_count, 1)

    def test_key_is_none_after_a_run(self):
        tree, proj = self.project_tree()
        keep = []
        real = ur.read_calls

        def spy(*a, **k):
            res = real(*a, **k)
            keep.append(res)
            return res

        with mock.patch.object(ur, "read_calls", spy):
            self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertIsNone(keep[0]._key)

    def test_source_never_serializes_reader_objects(self):
        with open(SCRIPT, "rb") as f:
            src = f.read().decode("utf-8")
        start = src.index("# --- Subcomandos project y global (T7) ---")
        end = src.index("def _build_parser")
        tree = ast.parse(src[start:end])
        banned = {"asdict", "vars", "repr", "dumps", "dump", "pickle", "deepcopy", "astuple", "ascii"}
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if name in banned:
                    offenders.append((name, node.lineno))
        self.assertEqual(offenders, [])
        self.assertNotIn("__dict__", src[start:end])
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)])   # sin f-strings

    def test_no_object_reprs_in_any_output(self):
        tree, proj = self.project_tree()
        for argv in (["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *WIN, "--show-paths"],
                     ["global", "--claude-dir", tree.claude_dir, *WIN, "--show-paths"]):
            code, out, err = self.run_main(*argv)
            for word in ("ReadResult", "CallRecord", "SkillUse", "UsageMetrics", "<usage_report", "0x"):
                self.assertNotIn(word, out + err)


class GitWarnings(CliBase):
    def _fake_index(self, repo, rel_paths, junk=b"x" * 40):
        git = os.path.join(repo, ".git")
        os.makedirs(git, exist_ok=True)
        data = b"DIRC\x00\x00\x00\x02"
        for rel in rel_paths:
            data += junk + rel.encode("utf-8") + b"\x00\x00\x00"
        with open(os.path.join(git, "index"), "wb") as f:
            f.write(data)

    def _forbid_processes(self):
        stack = contextlib.ExitStack()
        for mod, name in ((subprocess, "run"), (subprocess, "Popen"), (subprocess, "call"),
                          (subprocess, "check_output"), (os, "system")):
            stack.enter_context(mock.patch.object(mod, name, side_effect=AssertionError("proceso externo")))
        self.addCleanup(stack.close)

    def test_tracked_report_warns_and_still_writes(self):
        self._forbid_processes()
        tree, proj = self.project_tree()
        self._fake_index(proj, ["README.md", ".synclayer/usage-report.md", "src/a.py"])
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0)
        self.assertEqual(err, "aviso: " + ur.GIT_NOTICE_PROJECT + "\n")
        self.assertTrue(os.path.isfile(self.report_path(proj)))
        self.assertNotIn(self.base, err)
        self.assertNotIn(".synclayer", err.replace("usage-report", ""))   # sin ruta: solo el nombre fijo

    def test_untracked_report_does_not_warn(self):
        self._forbid_processes()
        tree, proj = self.project_tree()
        self._fake_index(proj, ["README.md", "docs/usage-report.md", ".synclayer/otra.md"])
        code, out, err = self.project(tree, proj)
        self.assertEqual((code, err), (0, ""))

    def test_longer_tracked_name_with_same_prefix_does_not_warn(self):
        # la aguja lleva el NUL final: `usage-report.md.bak` no es `usage-report.md`
        tree, proj = self.project_tree()
        self._fake_index(proj, [".synclayer/usage-report.md.bak"])
        code, out, err = self.project(tree, proj)
        self.assertEqual((code, err), (0, ""))

    def test_no_git_no_warning(self):
        tree, proj = self.project_tree()
        self.assertEqual(self.project(tree, proj)[2], "")

    def test_repo_root_above_project_dir(self):
        self._forbid_processes()
        repo = os.path.join(self.base, "repo raiz")
        proj = os.path.join(repo, "sub dir", "proyecto")
        os.makedirs(proj)
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj))
        self._fake_index(repo, ["sub dir/proyecto/.synclayer/usage-report.md"])
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0)
        self.assertIn(ur.GIT_NOTICE_PROJECT, err)

    def test_needle_split_across_chunks_is_found(self):
        tree, proj = self.project_tree()
        self._fake_index(proj, [".synclayer/usage-report.md"])
        for size in (1, 3, 7, 16):
            with mock.patch.object(ur, "GIT_INDEX_CHUNK", size):
                code, out, err = self.project(tree, proj)
            self.assertEqual(code, 0)
            self.assertIn(ur.GIT_NOTICE_PROJECT, err, size)

    def test_git_file_pointing_to_gitdir(self):
        tree, proj = self.project_tree()
        realgit = os.path.join(self.base, "gitdir real")
        os.makedirs(realgit)
        with open(os.path.join(realgit, "index"), "wb") as f:
            f.write(b"DIRC" + b"x" * 40 + b".synclayer/usage-report.md\x00\x00")
        with open(os.path.join(proj, ".git"), "wb") as f:
            f.write(b"gitdir: ../gitdir real\n")
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 0)
        self.assertIn(ur.GIT_NOTICE_PROJECT, err)

    def test_oversized_or_unreadable_index_is_silent(self):
        tree, proj = self.project_tree()
        self._fake_index(proj, [".synclayer/usage-report.md"])
        with mock.patch.object(ur, "MAX_GIT_INDEX_BYTES", 10):
            code, out, err = self.project(tree, proj)
        self.assertEqual((code, err), (0, ""))
        os.makedirs(os.path.join(proj, ".git", "index2"))
        os.remove(os.path.join(proj, ".git", "index"))
        os.makedirs(os.path.join(proj, ".git", "index"))   # una carpeta, no un archivo
        code, out, err = self.project(tree, proj)
        self.assertEqual((code, err), (0, ""))

    def test_stdout_mode_does_not_warn(self):
        tree, proj = self.project_tree()
        self._fake_index(proj, [".synclayer/usage-report.md"])
        code, out, err = self.project(tree, proj, "--stdout")
        self.assertEqual((code, err), (0, ""))

    def test_global_in_a_git_repository_warns_and_writes(self):
        tree, proj = self.project_tree()
        os.makedirs(os.path.join(tree.claude_dir, ".git"))
        code, out, err = self.glob(tree)
        self.assertEqual(code, 0)
        self.assertEqual(err, "aviso: " + ur.GIT_NOTICE_GLOBAL + "\n")
        self.assertNotIn(self.base, err)
        self.assertTrue(os.path.isfile(os.path.join(tree.claude_dir, "synclayer-usage.md")))
        # `.git` como archivo (worktree o submodulo) tambien cuenta
        os.rmdir(os.path.join(tree.claude_dir, ".git"))
        with open(os.path.join(tree.claude_dir, ".git"), "wb") as f:
            f.write(b"gitdir: x\n")
        self.assertIn(ur.GIT_NOTICE_GLOBAL, self.glob(tree)[2])

    def test_global_without_git_does_not_warn(self):
        tree, proj = self.project_tree()
        code, out, err = self.glob(tree)
        self.assertEqual((code, err), (0, ""))

    def test_global_stdout_in_git_repo_does_not_warn(self):
        tree, proj = self.project_tree()
        os.makedirs(os.path.join(tree.claude_dir, ".git"))
        self.assertEqual(self.glob(tree, "--stdout")[2], "")


class GlobalWrites(CliBase):
    def test_writes_global_report_without_synclayer_folder(self):
        tree, proj = self.project_tree()
        code, out, err = self.glob(tree)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("reporte global escrito"), out)
        self.assertIn("2 llamadas", out)
        for bad in (self.base, "synclayer-usage", "projects"):
            self.assertNotIn(bad, out + err)
        self.assertEqual(sorted(os.listdir(tree.claude_dir)), ["projects", "synclayer-usage.md"])
        text = self.read_bytes(os.path.join(tree.claude_dir, "synclayer-usage.md")).decode("utf-8")
        self.assertTrue(text.startswith(ur.REPORT_MARKER + "\n"))
        self.assertIn("# Reporte global de uso de subagentes", text)
        code, out, err = self.glob(tree, "--show-paths")
        self.assertIn(os.path.join(tree.claude_dir, "synclayer-usage.md"), out)

    def test_foreign_destination_not_overwritten(self):
        tree, proj = self.project_tree()
        dest = os.path.join(tree.claude_dir, "synclayer-usage.md")
        with open(dest, "wb") as f:
            f.write(b"mis notas\n")
        created = []
        real_open = os.open

        def spy(path, flags, *a, **k):
            if flags & os.O_CREAT:
                created.append(path)
            return real_open(path, flags, *a, **k)

        with mock.patch.object(ur.os, "open", spy):
            code, out, err = self.glob(tree)
        self.assertEqual(code, 1)
        self.assertEqual(self.read_bytes(dest), b"mis notas\n")
        self.assertEqual(temps_under(self.base), [])
        self.assertEqual(sorted(os.listdir(tree.claude_dir)), ["projects", "synclayer-usage.md"])
        self.assertEqual(created, [])

    def test_marked_destination_is_overwritten(self):
        tree, proj = self.project_tree()
        dest = os.path.join(tree.claude_dir, "synclayer-usage.md")
        with open(dest, "wb") as f:
            f.write(ur.REPORT_MARKER.encode() + b"\nviejo\n")
        self.assertEqual(self.glob(tree)[0], 0)
        self.assertNotIn(b"viejo", self.read_bytes(dest))

    def test_global_reads_all_projects(self):
        tree, proj = self.project_tree()
        self.add_calls(tree, "c--otro", count=3, prefix="o", session="s2")
        code, out, err = self.glob(tree)
        self.assertIn("5 llamadas", out)
        self.assertIn("2 proyectos", out)

    def test_destination_is_a_directory(self):
        tree, proj = self.project_tree()
        os.makedirs(os.path.join(tree.claude_dir, "synclayer-usage.md"))
        code, out, err = self.glob(tree)
        self.assertEqual(code, 1)
        self.assertEqual(temps_under(self.base), [])


class EndToEndNoLeak(CliBase):
    """Caso 11: marcadores unicos; nada en reportes, stdout ni stderr, tampoco en exit 1 y 3."""

    def _assert_clean(self, *texts):
        joined = "\n".join(texts)
        for marker in us.ALL_MARKERS:
            self.assertNotIn(marker, joined, marker)
        self.assertNotIn("Traceback", joined)

    def _rich(self):
        proj = self.make_project(us.M_FOLDER + " proyecto")
        tree = tur.rich_tree(self.base)
        os.rename(os.path.join(tree.projects, "c--Users-" + us.M_FOLDER + "-proj"),
                  os.path.join(tree.projects, self.folder_of(proj)))
        return tree, proj

    def test_exit_0_reports_stdout_and_stderr(self):
        tree, proj = self._rich()
        for extra in ((), ("--stdout",), ("--stdout", "--show-paths")):
            code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", proj,
                                           "--all", *extra)
            self.assertEqual(code, 0, err)
            if "--show-paths" not in extra:
                self._assert_clean(out, err)
            else:
                self._assert_clean(out.replace(proj, ""), err)
        code, out, err = self.run_main("global", "--claude-dir", tree.claude_dir, "--all")
        self.assertEqual(code, 0, err)
        self._assert_clean(out, err)
        code, out_g, err = self.run_main("global", "--claude-dir", tree.claude_dir, "--all", "--stdout")
        self._assert_clean(out_g, err)
        project_text = self.read_bytes(self.report_path(proj)).decode("utf-8")
        global_text = self.read_bytes(os.path.join(tree.claude_dir, "synclayer-usage.md")).decode("utf-8")
        self._assert_clean(project_text, global_text, out_g)
        self.assertEqual(out_g, global_text)
        for text in (project_text, global_text):
            self.assertNotIn("c--Users", text)
            self.assertNotIn(os.path.basename(self.base), text)
            self.assertNotIn(self.folder_of(proj), text)
        self.assertNotIn(us.M_SESSION, project_text + global_text)
        self.assertEqual(temps_under(self.base), [])

    def test_exit_1_and_3_outputs(self):
        tree, proj = self._rich()
        other = self.make_project("sin transcripciones " + us.M_FOLDER)
        before = tur.snapshot(self.base)
        code, out, err = self.run_main("project", "--claude-dir", tree.claude_dir, "--project-dir", other, "--all")
        self.assertEqual(code, 1)
        self._assert_clean(out, err)
        code, out, err = self.run_main("project", "--claude-dir", os.path.join(self.base, us.M_FOLDER),
                                       "--project-dir", proj, "--all")
        self.assertEqual(code, 1)
        self._assert_clean(out, err)
        self.assertEqual(tur.snapshot(self.base), before)
        # exit 3: carpeta con basura
        bad_base = os.path.join(self.base, "malo")
        os.makedirs(bad_base)
        proj3 = self.make_project("tres " + us.M_FOLDER)
        tree3 = us.Tree(bad_base)
        for i in range(10):
            tree3.subagent(self.folder_of(proj3), us.M_SESSION, "a%d" % i,
                           [us.user("2026-03-01T10:00:00Z"), "basura " + us.M_CONTENT])
        before = tur.snapshot(self.base)
        for argv in (["project", "--claude-dir", tree3.claude_dir, "--project-dir", proj3, "--all"],
                     ["global", "--claude-dir", tree3.claude_dir, "--all"]):
            code, out, err = self.run_main(*argv)
            self.assertEqual(code, 3)
            self._assert_clean(out, err)
        self.assertEqual(tur.snapshot(self.base), before)

    def test_username_not_in_output(self):
        tree, proj = self._rich()
        user = os.path.basename(os.path.expanduser("~"))
        outs = []
        for argv in (["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, "--all"],
                     ["global", "--claude-dir", tree.claude_dir, "--all"]):
            code, out, err = self.run_main(*argv)
            outs += [out, err]
        outs.append(self.read_bytes(self.report_path(proj)).decode("utf-8"))
        outs.append(self.read_bytes(os.path.join(tree.claude_dir, "synclayer-usage.md")).decode("utf-8"))
        if len(user) > 3:
            for text in outs:
                self.assertNotIn(user.lower(), text.lower())


class ReviewRoundFixes(CliBase):
    """Ronda de correcciones tras auditor y shield (A a E y pruebas 1 y 3)."""

    def _only_replace_fails_for(self, name, exc):
        real = os.replace

        def fake(src, dst):
            if os.path.basename(dst) == name:
                raise exc
            return real(src, dst)

        return mock.patch.object(ur.os, "replace", fake)

    # A: gitdir UNC o de dispositivo
    def test_gitdir_unc_and_device_targets_are_never_touched(self):
        base = os.path.join(self.base, "repo")
        os.makedirs(base)
        dot = os.path.join(base, ".git")
        seen = []
        real_lstat, real_open = os.lstat, os.open

        def spy_lstat(path, *a, **k):
            seen.append(os.fspath(path))
            return real_lstat(path, *a, **k)

        def spy_open(path, *a, **k):
            seen.append(os.fspath(path))
            return real_open(path, *a, **k)

        for target in ("//host.invalid/share/x", "\\\\host.invalid\\share\\x", "\\\\?\\C:\\x", "\\\\.\\PhysicalDrive0",
                       "//?/UNC/host.invalid/share"):
            with self.subTest(target=target):
                with open(dot, "wb") as f:
                    f.write(("gitdir: " + target + "\n").encode("utf-8"))
                del seen[:]
                with mock.patch.object(ur.os, "lstat", spy_lstat), mock.patch.object(ur.os, "open", spy_open):
                    got = ur._gitdir_from_file(dot, base)
                self.assertIsNone(got)
                self.assertFalse([p for p in seen if "host.invalid" in p or "PhysicalDrive" in p], seen)
        # y de extremo a extremo: sin aviso y sin tocar esa ruta
        tree, proj = self.project_tree()
        with open(os.path.join(proj, ".git"), "wb") as f:
            f.write(b"gitdir: //host.invalid/share/x\n")
        del seen[:]
        with mock.patch.object(ur.os, "lstat", spy_lstat), mock.patch.object(ur.os, "open", spy_open):
            code, out, err = self.project(tree, proj)
        self.assertEqual((code, err), (0, ""))
        self.assertFalse([p for p in seen if "host.invalid" in p], seen)

    # B: .gitignore suelto
    def test_gitignore_created_by_this_run_is_removed_if_the_report_fails(self):
        for label, exc, expected in (("os", PermissionError(13, "x"), 1), ("ctrl-c", KeyboardInterrupt(), 130)):
            with self.subTest(label=label):
                base = os.path.join(self.base, label)
                os.makedirs(base)
                proj = os.path.join(base, "proj")
                sdir = os.path.join(proj, ".synclayer")
                os.makedirs(sdir)    # .synclayer preexistente, sin .gitignore
                tree = us.Tree(base)
                self.add_calls(tree, self.folder_of(proj))
                initial = os.listdir(sdir)
                with self._only_replace_fails_for("usage-report.md", exc):
                    code, out, err = self.project(tree, proj)
                self.assertEqual(code, expected, err)
                self.assertEqual(os.listdir(sdir), initial)

    def test_preexisting_gitignore_is_kept_when_the_report_fails(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        with open(os.path.join(sdir, ".gitignore"), "wb") as f:
            f.write(b"*\n")
        with self._only_replace_fails_for("usage-report.md", PermissionError(13, "x")):
            self.assertEqual(self.project(tree, proj)[0], 1)
        self.assertEqual(os.listdir(sdir), [".gitignore"])

    def test_gitignore_not_removed_if_it_is_not_ours_after_a_failure(self):
        # un .gitignore ajeno aparecido en la carrera no se borra: el borrado exige el contenido exacto
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        real = os.replace

        def fake(src, dst):
            if os.path.basename(dst) == "usage-report.md":
                with open(os.path.join(sdir, ".gitignore"), "wb") as f:
                    f.write(b"mio\n")
                raise PermissionError(13, "x")
            return real(src, dst)

        with mock.patch.object(ur.os, "replace", fake):
            self.assertEqual(self.project(tree, proj)[0], 1)
        self.assertEqual(self.read_bytes(os.path.join(sdir, ".gitignore")), b"mio\n")

    # 1: segunda comprobacion del .gitignore antes del replace
    def test_gitignore_rechecked_before_replace(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        gi = os.path.join(sdir, ".gitignore")
        bad = b"*\n!usage-report.md\n"
        real_fsync = os.fsync
        state = {"done": False}

        def swap(fd):
            real_fsync(fd)
            if not state["done"]:
                state["done"] = True
                with open(gi, "wb") as f:
                    f.write(bad)

        with mock.patch.object(ur.os, "fsync", swap):
            code, out, err = self.project(tree, proj)
        self.assertTrue(state["done"])
        self.assertEqual(code, 1)
        self.assertEqual(self.read_bytes(gi), bad)
        self.assertEqual(os.listdir(sdir), [".gitignore"])
        self.assertFalse(os.path.exists(self.report_path(proj)))

    # 3: el .gitignore se reemplaza antes que el reporte
    def test_gitignore_replaced_before_the_report(self):
        tree, proj = self.project_tree()
        order = []
        real = os.replace

        def spy(src, dst):
            order.append(os.path.basename(dst))
            return real(src, dst)

        with mock.patch.object(ur.os, "replace", spy):
            self.assertEqual(self.project(tree, proj)[0], 0)
        self.assertEqual(order, [".gitignore", "usage-report.md"])

    # C: aviso de git del global tambien por carpetas padre
    def test_global_warns_when_a_parent_folder_has_git(self):
        parent = os.path.join(self.base, "dotfiles")
        os.makedirs(os.path.join(parent, ".git"))
        tree = us.Tree(parent, claude_name="sub claude")
        self.add_calls(tree, "c--p")
        code, out, err = self.glob(tree)
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "aviso: " + ur.GIT_NOTICE_GLOBAL + "\n")
        self.assertNotIn(parent, err)
        self.assertTrue(os.path.isfile(os.path.join(tree.claude_dir, "synclayer-usage.md")))

    def test_global_climb_is_bounded(self):
        parent = os.path.join(self.base, "dotfiles2")
        os.makedirs(os.path.join(parent, ".git"))
        tree = us.Tree(os.path.join(parent, "a", "b", "c"))
        self.add_calls(tree, "c--p")
        with mock.patch.object(ur, "MAX_GIT_PARENTS", 2):
            self.assertEqual(self.glob(tree)[2], "")
        self.assertIn(ur.GIT_NOTICE_GLOBAL, self.glob(tree)[2])

    # D: --show-paths sin UnicodeEncodeError
    def _cp1252_run(self, argv):
        out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
        err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ur.main(argv)
        out.flush()
        err.flush()
        return code, out.buffer.getvalue().decode("cp1252"), err.buffer.getvalue().decode("cp1252")

    def test_show_paths_with_a_char_outside_the_console_encoding_still_succeeds(self):
        proj = self.make_project("proy \u4e2d\u6587")
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj))
        code, out, err = self._cp1252_run(["project", "--claude-dir", tree.claude_dir, "--project-dir", proj,
                                          *WIN, "--show-paths"])
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(self.report_path(proj)))
        self.assertTrue(out.startswith("reporte de proyecto escrito"), out)
        self.assertIn("?", out)
        self.assertEqual(err, "")
        code, out, err = self._cp1252_run(["global", "--claude-dir", tree.claude_dir, *WIN, "--show-paths"])
        self.assertEqual(code, 0, err)

    def test_show_paths_error_message_with_unencodable_path_keeps_its_exit_code(self):
        proj = self.make_project("proy \u4e2d\u6587")
        tree = us.Tree(self.base)
        self.add_calls(tree, self.folder_of(proj))
        os.makedirs(os.path.join(proj, ".synclayer"))
        with open(self.report_path(proj), "wb") as f:
            f.write(b"ajeno")
        code, out, err = self._cp1252_run(["project", "--claude-dir", tree.claude_dir, "--project-dir", proj,
                                          *WIN, "--show-paths"])
        self.assertEqual(code, 1)
        self.assertIn("no se sobrescribe", err)
        self.assertNotIn("no previsto", err)

    def test_print_failure_after_a_successful_write_does_not_change_the_exit_code(self):
        tree, proj = self.project_tree()

        class Broken:
            def write(self, text):
                raise OSError(5, "tuberia rota")

            def flush(self):
                raise OSError(5, "tuberia rota")

        with mock.patch.object(sys, "stdout", Broken()):
            code = ur.main(["project", "--claude-dir", tree.claude_dir, "--project-dir", proj, *WIN])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(self.report_path(proj)))

    # E: micro-ventanas de Ctrl+C
    def test_ctrl_c_between_mkdir_and_the_check_removes_the_new_folder(self):
        tree, proj = self.project_tree()
        before = tur.snapshot(proj)
        real = ur._check_dir

        def fake(path, what):
            if what == ur.WHAT_SYNCLAYER:
                raise KeyboardInterrupt
            return real(path, what)

        with mock.patch.object(ur, "_check_dir", fake):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 130)
        self.assertEqual(tur.snapshot(proj), before)

    def test_ctrl_c_right_after_creating_the_temp_removes_it(self):
        tree, proj = self.project_tree()
        before = tur.snapshot(proj)
        real_open = os.open

        def fake(path, flags, *a, **k):
            fd = real_open(path, flags, *a, **k)
            if os.fspath(path).endswith(".tmp"):
                os.close(fd)
                raise KeyboardInterrupt
            return fd

        with mock.patch.object(ur.os, "open", fake):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 130)
        self.assertEqual(tur.snapshot(proj), before)
        self.assertEqual(temps_under(proj), [])

    def test_failed_temp_creation_does_not_delete_a_foreign_file(self):
        # O_EXCL fallo porque el nombre ya existia: no es nuestro y no se intenta borrar
        tree, proj = self.project_tree()
        os.makedirs(os.path.join(proj, ".synclayer"))
        real_open = os.open

        def fake(path, flags, *a, **k):
            if flags & os.O_CREAT:
                raise FileExistsError(17, "x")
            return real_open(path, flags, *a, **k)

        with mock.patch.object(ur.os, "open", fake), mock.patch.object(ur, "_unlink_quiet") as unlink:
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        unlink.assert_not_called()


class FinalRoundFixes(CliBase):
    """Cierre del nucleo de la Fase 2: hardlinks, limpieza estrecha y textos de privacidad verdaderos."""

    def _hardlink(self, src, dst):
        try:
            os.link(src, dst)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("el sistema no deja crear enlaces duros")

    def test_hardlinked_destination_gives_the_kind_message_not_the_unreadable_one(self):
        tree, proj = self.project_tree()
        self.assertEqual(self.project(tree, proj)[0], 0)
        self._hardlink(self.report_path(proj), os.path.join(self.base, "segundo nombre.md"))
        old = self.read_bytes(self.report_path(proj))
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertIn(ur.MSG_DEST_HARDLINK, err)
        self.assertNotIn(ur.MSG_DEST_UNREADABLE, err)
        self.assertEqual(self.read_bytes(self.report_path(proj)), old)
        self.assertEqual(temps_under(proj), [])
        # el global, igual
        self.assertEqual(self.glob(tree)[0], 0)
        dest = os.path.join(tree.claude_dir, "synclayer-usage.md")
        self._hardlink(dest, os.path.join(self.base, "otro nombre.md"))
        code, out, err = self.glob(tree)
        self.assertEqual(code, 1)
        self.assertIn(ur.MSG_DEST_HARDLINK, err)
        self.assertNotIn(ur.MSG_DEST_UNREADABLE, err)

    def test_hardlinked_gitignore_is_refused_with_the_gitignore_message(self):
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        os.makedirs(sdir)
        gi = os.path.join(sdir, ".gitignore")
        with open(gi, "wb") as f:
            f.write(b"*\n")
        self._hardlink(gi, os.path.join(self.base, "gi segundo.txt"))
        code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertIn("gitignore", err)
        self.assertFalse(os.path.exists(self.report_path(proj)))

    def test_cleanup_only_deletes_the_names_this_run_wrote(self):
        # .synclayer recien creada; el .gitignore falla al reemplazarse y alguien planto usage-report.md:
        # ese archivo no lo escribio esta corrida y no se borra (la carpeta queda, no esta vacia)
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        real = os.replace

        def fake(src, dst):
            if os.path.basename(dst) == ".gitignore":
                with open(os.path.join(sdir, "usage-report.md"), "wb") as f:
                    f.write(b"plantado")
                raise PermissionError(13, "x")
            return real(src, dst)

        with mock.patch.object(ur.os, "replace", fake):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertEqual(self.read_bytes(os.path.join(sdir, "usage-report.md")), b"plantado")

    def test_cleanup_repeats_the_lstat_of_the_folder_before_each_unlink(self):
        # tras el primer borrado, `.synclayer` pasa a verse como enlace: no se borra nada mas
        tree, proj = self.project_tree()
        sdir = os.path.join(proj, ".synclayer")
        real_replace, real_lstat, real_unlink = os.replace, os.lstat, os.unlink
        state = {"unlinked": False}
        norm = os.path.normcase(os.path.abspath(sdir))

        def fake_replace(src, dst):
            if os.path.basename(dst) == "usage-report.md":
                with open(os.path.join(sdir, "usage-report.md"), "wb") as f:
                    f.write(b"plantado")
                raise PermissionError(13, "x")
            return real_replace(src, dst)

        def fake_unlink(path, *a, **k):
            real_unlink(path, *a, **k)
            if os.path.basename(path) == ".gitignore":
                state["unlinked"] = True

        def fake_lstat(path, *a, **k):
            if state["unlinked"] and os.path.normcase(os.path.abspath(os.fspath(path))) == norm:
                return os.stat_result((stat.S_IFLNK | 0o777,) + (0,) * 9)
            return real_lstat(path, *a, **k)

        with mock.patch.object(ur.os, "replace", fake_replace), mock.patch.object(ur.os, "unlink", fake_unlink), \
                mock.patch.object(ur.os, "lstat", fake_lstat):
            code, out, err = self.project(tree, proj)
        self.assertEqual(code, 1)
        self.assertTrue(state["unlinked"])
        self.assertEqual(self.read_bytes(os.path.join(sdir, "usage-report.md")), b"plantado")

    def test_privacy_texts_do_not_claim_there_is_no_content(self):
        for notes in (ur.PRIVACY_NOTES, ur.GLOBAL_PRIVACY_NOTES):
            joined = " ".join(notes)
            self.assertNotIn("no contiene contenido de conversaciones", joined)
            self.assertIn("no copia mensajes, prompts", joined)
        project = ur.PRIVACY_NOTES[0]
        self.assertIn("nombres de skill que escribe el modelo", project)
        self.assertIn("ids de modelo que pasan un patrón", project)
        self.assertIn("64 caracteres por celda", project)
        self.assertIn("aunque la skill no exista", project)
        self.assertIn("Es local", project)
        glob = ur.GLOBAL_PRIVACY_NOTES[0]
        self.assertIn("agrupa", glob)
        self.assertIn("(otra skill)", glob)
        self.assertIn("(otro modelo)", glob)

    def test_inspect_text_does_not_claim_content_free_output(self):
        header = ur.render_inspect(ur._Stats()).split("\n")[1]
        self.assertNotIn("Nunca valores de contenido", header)
        self.assertIn("revise antes de pegar", header)
        self.assertNotIn("segura de pegar", ur.__doc__)

    def test_module_docstring_lists_every_exit_code(self):
        doc = ur.__doc__
        start = doc.index("Codigos de salida")
        block = doc[start:start + 900]
        for code in ("0 correcto", "1 entorno", "2 uso incorrecto", "3 esquema", "130"):
            self.assertIn(code, block)
        self.assertIn("5 %", block)


if __name__ == "__main__":
    unittest.main()
