import io
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "agent_guard.py")
sys.path.insert(0, os.path.dirname(SCRIPT))

import agent_guard  # noqa: E402


def bash(cmd, allow_temp=False):
    return agent_guard.check(
        "readonly", allow_temp, {"tool_name": "Bash", "tool_input": {"command": cmd}})


def tests_only(tool, _cwd=None, **ti):
    payload = {"tool_name": tool, "tool_input": ti}
    if _cwd is not None:
        payload["cwd"] = _cwd
    return agent_guard.check("tests-only", False, payload)


class GuardTestCase(unittest.TestCase):
    def assertBlocked(self, cmd, needle=None, allow_temp=False):
        reason = bash(cmd, allow_temp)
        self.assertIsNotNone(reason, "debio bloquear: %r" % cmd)
        self.assertIn("Bloqueado por agent_guard (readonly)", reason)
        if needle is not None:
            self.assertIn(needle, reason, "motivo equivocado para %r" % cmd)
        return reason

    def assertAllowed(self, cmd, allow_temp=False):
        self.assertIsNone(bash(cmd, allow_temp), "debio permitir: %r" % cmd)


class ReadonlyAllow(GuardTestCase):
    def test_allowed(self):
        for cmd in [
            "git diff", "git log", "git show HEAD", "git status", "git blame f.py",
            "git fetch", "git fetch origin", "pytest", "python manage.py test", "npm test",
            "ls -la", "cat f", "grep -rn foo .", "find . -name '*.py'",
            'grep "a > b" file', 'git log --format="%h | %s"', "git log | head",
            "echo hi > /dev/null", "echo hi > NUL", "echo hi > nul", "cmd 2>&1",
            "cmd >&2", "cmd 1>&2", "cmd 2>/dev/null", "cmd &> /dev/null",
            "wc -l < file", "cat <<< hello", "git branch", "git branch -a", "git branch -r",
            "git branch -v", "git branch -vv", "git branch --list", "git branch --show-current",
            "git branch --contains abc123", "git branch --merged", "git branch --no-merged",
            "git stash list", "git stash show", "git tag", "git tag -l", "git tag --list",
            "git worktree list", "git config --get user.name", "git config --list",
            "git config -l", "git config --get-regexp alias", "git remote", "git remote -v",
            "git remote show origin", "git remote get-url origin",
            "git -C repo log", "git --no-pager diff",
            "git --git-dir=.git status", "git -P log", "echo $(git rev-parse HEAD)",
            "FOO=1 pytest", "sudo cat /etc/hosts", "timeout 10 pytest", "time git status",
            "pip list", "pip3 show x", "python -m pytest", "npm run build", "npm ls",
            "sed -n 1,5p f", "sed -e 's/i/x/' f", "perl -ne 'print' f", "perl -Mstrict -e 1",
            "command -v rm", "git status\ncat f", "echo 'a; rm x'", 'echo "$(date)"',
            "cat > /dev/null <<EOF\nrm -rf x\nEOF",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(bash(cmd))

    def test_non_bash_tool_ignored(self):
        self.assertIsNone(agent_guard.check(
            "readonly", False, {"tool_name": "Write", "tool_input": {"file_path": "x"}}))


class ReadonlyBlock(GuardTestCase):
    def test_blocked(self):
        for cmd in [
            "git commit -m x", "git add .", "git push", "git pull", "git merge x",
            "git rebase main", "git reset --hard", "git checkout main", "git switch x",
            "git restore f", "git clean -fd", "git rm f", "git mv a b", "git apply p",
            "git am p", "git cherry-pick x", "git revert x", "git init", "git clone u",
            "git gc", "git prune", "git update-ref a b", "git update-index x",
            "git filter-branch", "git submodule update", "git stash", "git stash pop",
            "git tag v1", "git tag -d v1", "git branch new", "git branch -d x",
            "git branch -D x", "git branch -m a b", "git branch -M a", "git branch -c a b",
            "git branch -C a b", "git branch --delete x", "git branch --move a b",
            "git branch --copy a b", "git worktree add ../x", "git config user.name x",
            "git config --global --unset x", "git remote add o u", "git remote remove o",
            "git -C repo commit -m x", "git -c a=b commit", "git --no-pager commit",
            "git --git-dir=.git push",
            "rm f", "rmdir d", "mv a b", "cp a b", "touch f", "mkdir d", "chmod +x f",
            "chown u f", "ln -s a b", "tee f", "truncate -s 0 f", "dd if=a of=b",
            "install a b", "patch -p1", "del f", "erase f", "rd d", "ren a b", "move a b",
            "copy a b", "xcopy a b", "robocopy a b", "Remove-Item f", "remove-item f",
            "Set-Content f x", "Add-Content f x", "Out-File f", "New-Item f", "Move-Item a b",
            "Copy-Item a b", "Rename-Item a b", "Clear-Content f",
            "sed -i s/a/b/ f", "sed --in-place s/a/b/ f", "sed -ni p f", "sed -i.bak s/a/b/ f",
            "perl -pi -e 's/a/b/' f", "perl -i.bak -e 1 f",
            "pip install x", "pip3 uninstall x", "python -m pip install x",
            "python3 -m pip uninstall x", "npm install", "npm i x", "npm ci",
            "npm uninstall x", "npm update", "npm link", "npm publish", "yarn add x",
            "yarn remove x", "yarn install", "yarn upgrade", "pnpm add x", "pnpm remove x",
            "pnpm install", "pnpm update", "apt install x", "apt-get remove x",
            "brew install x", "choco upgrade x", "winget uninstall x", "scoop install x",
            "find . -delete", "find . -exec rm {} \\;", "find . -name x -exec rm -f {} +",
            "echo hi > out.txt", "echo hi >> out.txt", "echo hi >| out.txt",
            "echo hi &> out.txt", "echo hi &>> out.txt", "cmd 2> err.txt", "cmd 1>out",
            "cmd 2>>err.txt", "cmd >&out.txt", "echo hi>out.txt",
            "git status && git commit -m x", "git status; rm f", "git log || rm f",
            "git log | tee f", "git status & rm f", "git status\nrm f",
            "echo $(rm -rf x)", "echo `rm -rf x`", 'echo "$(rm -rf x)"',
            "sudo rm f", "env FOO=1 rm f", "FOO=1 git commit", "timeout 5 rm f",
            "nohup rm f", "command rm f", "/usr/bin/git commit", "git.exe commit",
            "(cd x && rm f)", "if true; then rm f; fi",
            "diff <(rm x) y",
        ]:
            with self.subTest(cmd=cmd):
                reason = self.assertBlocked(cmd)
                self.assertNotIn("de forma segura", reason)  # no un error de analisis

    def test_message_spanish_and_names_command(self):
        msg = bash("git commit -m x")
        self.assertIn("Bloqueado por agent_guard (readonly)", msg)
        self.assertIn("'git commit'", msg)
        self.assertIn("solo lectura", msg)
        self.assertIn("'> out.txt'", bash("echo hi > out.txt"))

    def test_quoted_redirect_in_chain(self):
        self.assertIsNone(bash('echo "a > b" && grep "x | y" f'))
        self.assertIsNotNone(bash('echo "a > b" && echo c > f'))

    def test_invalid_command_payload(self):
        self.assertIsNotNone(agent_guard.check(
            "readonly", False, {"tool_name": "Bash", "tool_input": {}}))
        self.assertIsNotNone(agent_guard.check(
            "readonly", False, {"tool_name": "Bash", "tool_input": {"command": 5}}))


class AllowTemp(GuardTestCase):
    def t(self, cmd):
        return bash(cmd, allow_temp=True)

    def test_allowed(self):
        for cmd in [
            "rm /tmp/x", "rm -rf /tmp/dir/sub", "rm /var/tmp/x", "mkdir -p /tmp/a/b",
            "touch /tmp/f", "rmdir /tmp/d", "cp a /tmp/b", "cp -r src /tmp/dest",
            "mv /tmp/a /tmp/b", "echo x | tee /tmp/f", "echo hi > /tmp/out.txt",
            "echo hi >> /tmp/out.txt", "cmd 2> /tmp/err", "rm $TMPDIR/x", "rm $TEMP/x",
            "rm $TMP/x", "rm /tmp/a /tmp/b",
            "rm C:/Users/u/AppData/Local/Temp/x", "rm 'C:/Users/u/AppData/Local/Temp/x'",
            "rm ${TMPDIR}/x", "echo x > ${TEMP}/a", "touch ${TMP}/b",
            "touch /c/Users/u/AppData/Local/Temp/x", "echo hi > /dev/null",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.t(cmd), cmd)

    def test_backslash_paths_blocked(self):
        # bash los interpreta distinto (`%TEMP%\x` -> `%TEMP%x`): se bloquean, usar `/`.
        for cmd in ["rm %TEMP%\\x", "rm %TMP%\\x", "rm C:\\Users\\u\\AppData\\Local\\Temp\\x",
                    "rm 'C:\\Users\\u\\AppData\\Local\\Temp\\x'", "cp a %TEMP%\\",
                    'echo x > "/tmp/a\\b"', "rm /tmp/.\\./etc/x"]:
            # (sin comillas, `/tmp/a\\b` es `/tmp/ab` para bash: ya es un temporal legitimo)
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(self.t(cmd), cmd)

    def test_env_prefixes(self):
        with mock.patch.dict(os.environ, {"TMPDIR": "/scratch/work", "TEMP": "D:\\Tmp"}):
            self.assertIsNone(self.t("rm /scratch/work/x"))
            self.assertIsNone(self.t("rm D:/Tmp/x"))
            self.assertIsNotNone(self.t("rm /scratch/other/x"))

    def test_blocked(self):
        for cmd in [
            "rm /home/u/x", "rm /tmp/x /home/u/y", "rm /tmp", "rm /tmp/", "rm -rf /",
            "rm /tmp/../etc/passwd", "rm /tmp/a/../../b", "mkdir /tmp/../x",
            "echo hi > out.txt", "echo hi > /tmp/../x", "echo hi > /tmpx/f",
            "cp /tmp/a b", "cp a", "mv /tmp/a b", "mv a /tmp/b", "mv /tmp/a",
            "touch f", "rm", "echo x | tee f", "rm /tmp/$(echo ..)",
            "chmod +x /tmp/x", "ln -s a /tmp/b", "dd of=/tmp/x", "Remove-Item /tmp/x",
            "git commit -m x", "sed -i s/a/b/ /tmp/f", "pip install x", "npm install",
            "git add /tmp/x", "find /tmp -delete", "find /tmp -exec rm {} \\;",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(self.t(cmd), cmd)

    def test_braces_and_links_and_builtin(self):
        for cmd in ["rm {src/app.py,x/appdata/local/temp/y}", "rm /tmp/{a,b}",
                    "cp -l src/app.py /tmp/x", "cp --link a /tmp/x", "cp -s a /tmp/x",
                    "cp --symbolic-link a /tmp/x", "cp -al a /tmp/x", "cp --sym a /tmp/x",
                    "builtin rm x"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(self.t(cmd), cmd)
        self.assertIsNotNone(bash("builtin rm x"))
        self.assertIsNone(self.t("cp a /tmp/b"))

    def test_find_exec_temp(self):
        self.assertIsNone(self.t("find /tmp -exec rm /tmp/x \\;"))

    def test_without_flag_temp_still_blocked(self):
        self.assertIsNotNone(bash("rm /tmp/x"))
        self.assertIsNotNone(bash("echo hi > /tmp/x"))


class TestsOnly(unittest.TestCase):
    def test_allowed_paths(self):
        for p in [
            "tests/test_a.py", "C:\\proj\\tests\\a.py", "C:\\proj\\Test\\a.txt",
            "src/__tests__/a.js", "spec/a.rb", "specs/a.rb", "proj/fixtures/data.json",
            "proj/testdata/x.bin", "e2e/login.ts", "cypress/e2e/a.cy.ts",
            "playwright/a.ts", "src/test_foo.py", "src/foo_test.go", "src/foo.test.ts",
            "src/foo.spec.js", "src/conftest.py", "src/FooTests.cs", "src/FooTest.java",
            "src/FooTests.java", "C:\\proj\\src\\foo.spec.tsx", "SRC\\TESTS\\A.PY",
            "C:\\proj\\SRC\\TEST_FOO.PY",
        ]:
            for tool, key in (("Write", "file_path"), ("Edit", "file_path"),
                              ("NotebookEdit", "notebook_path")):
                with self.subTest(path=p, tool=tool):
                    self.assertIsNone(tests_only(tool, "C:\\proj", **{key: p}))

    def test_blocked_paths(self):
        for p in [
            "src/app.py", "C:\\proj\\src\\app.py", "README.md", "latest.py", "src/contest.py",
            "src/testing/a.py", "src/tests.py", "src/attest.py", "src/Foo.cs",
            "tests/../src/app.py", "C:\\proj\\tests\\..\\src\\a.py", "", "   ",
        ]:
            with self.subTest(path=p):
                reason = tests_only("Write", "C:\\proj", file_path=p)
                self.assertIsNotNone(reason)
                self.assertIn("tests-only", reason)

    def test_missing_path_blocked(self):
        self.assertIsNotNone(tests_only("Write"))
        self.assertIsNotNone(tests_only("Edit", file_path=None))
        self.assertIsNotNone(tests_only("NotebookEdit", file_path="tests/a.ipynb"))
        self.assertIsNotNone(agent_guard.check(
            "tests-only", False, {"tool_name": "Write", "tool_input": "x"}))

    def test_other_tools_ignored(self):
        self.assertIsNone(agent_guard.check("tests-only", False, {"tool_name": "Read"}))

    def test_message_names_path(self):
        self.assertIn("src/app.py", tests_only("Write", file_path="src/app.py"))


def tests_bash(cmd, cwd="C:/proj"):
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    if cwd is not None:
        payload["cwd"] = cwd
    return agent_guard.check("tests-only", False, payload)


class TestsOnlyBash(unittest.TestCase):
    def test_blocked(self):
        for cmd in [
            "sed -i s/a/b/ src/app.py", "echo x > src/app.py", "rm src/app.py", "git add .",
            "touch src/x", "echo x > tests/../src/a.py", "cd src && echo x > tests/a.py",
            "echo x > /otro/proyecto/tests/a.py", "echo x > C:/otro/tests/a.py",
            "echo x > C:\\otro\\tests\\a.py", "echo x >> src\\app.py",
            "pushd src; touch tests/a", "popd && rm tests/a",
            "echo x > $HOME/tests/a.py", "echo x > ~/tests/a.py", "echo x > %CD%/tests/a",
            "echo x > $(pwd)/tests/a", "rm tests/a src/b", "cp tests/a src/b",
            "cp -t src tests/a", "mv tests/a src/b", "tee src/log.txt", "pip install x",
            "find . -delete", "find tests -exec rm src/x \\;", "echo x > tests/a.py; rm src/x",
            "rm tests/../src/x", "echo x > C:/proj/src/app.py", "echo x > C:/proj/../a/tests/x",
            "rm {src/app.py,x/tests/y}", "rm src/{app.py,a_test.x}",
            "touch src/{app.py,a_test.x}", "cp tests/a {src/app.py,x/tests/y}",
            "find src -name app.py -exec rm {{},a_test.b} \\;",
            "cp -l src/app.py tests/a.py", "cp --link src/app.py tests/a.py",
            "cp -s C:/proj/src/app.py tests/a.py", "cp -rs C:/proj/src tests/x",
            "cp -al a /tmp/x",
            "builtin cd .. && rm -rf tests/", "env -C .. rm -rf tests/",
            "env --chdir=.. rm tests/a", "sudo -D .. rm tests/a", "sudo --chdir=.. rm tests/a",
            "find / -maxdepth 0 -execdir rm -rf home/u/other/tests/ \\;",
            "find / -maxdepth 0 -okdir rm -rf home/u/other/tests/ \\;",
            "echo x > C:src/tests/a", "rm -rf /",
        ]:
            with self.subTest(cmd=cmd):
                reason = tests_bash(cmd)
                self.assertIsNotNone(reason, "debio bloquear: %r" % cmd)
                self.assertIn("(tests-only)", reason)

    def test_blocked_message(self):
        reason = tests_bash("echo x > src/app.py")
        self.assertIn("solo escribe en pruebas", reason)
        self.assertNotIn("(readonly)", reason)

    def test_allowed(self):
        for cmd in [
            "python -B -m unittest discover -s tests", "pytest -q", "npm test",
            "echo x > tests/out.txt", "touch tests/fixtures/a.json", "tee tests/log.txt",
            "echo x > /tmp/a", "cat src/app.py", "git diff", "git status",
            "echo x > C:/proj/tests/a.txt", "mkdir tests/new", "mkdir -p tests/a/b",
            "rm tests/old.txt", "cp src/app.py tests/fixtures/app.py",
            "cp -t tests/fixtures src/app.py", "mv tests/a tests/b", "echo x > src/test_a.py",
            "echo x > tests/a 2>/dev/null", "pytest -q > tests/out.log",
            "echo x | tee tests/a.txt tests/b.txt", "find tests -exec rm tests/x \\;",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(tests_bash(cmd), "debio permitir: %r" % cmd)

    def test_windows_backslash_paths_blocked(self):
        # sin comillas el parser elimina `\` como bash (`tests\out.txt` -> `testsout.txt`, que no
        # es ruta de pruebas); entre comillas se rechaza cualquier ruta con `\` (usar `/`).
        for cmd in ["echo x >> tests\\out.txt", "echo x > C:\\proj\\tests\\a.txt"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd))

    def test_without_cwd_only_temp(self):
        self.assertIsNotNone(tests_bash("echo x > tests/a.txt", cwd=None))
        self.assertIsNotNone(tests_bash("echo x > tests/a.txt", cwd="   "))
        self.assertIsNotNone(tests_bash("echo x > C:/proj/tests/a.txt", cwd=None))
        self.assertIsNotNone(tests_bash("echo x > tests/a.txt", cwd="relativo"))
        self.assertIsNone(tests_bash("echo x > /tmp/a", cwd=None))
        self.assertIsNone(tests_bash("pytest -q", cwd=None))

    def test_posix_cwd(self):
        self.assertIsNone(tests_bash("echo x > /home/u/proj/tests/a", cwd="/home/u/proj"))
        self.assertIsNotNone(tests_bash("echo x > /home/u/other/tests/a", cwd="/home/u/proj"))

    def test_missing_command_blocked(self):
        for ti in ({}, {"command": None}, {"command": 5}, "x"):
            with self.subTest(ti=ti):
                reason = agent_guard.check(
                    "tests-only", False,
                    {"tool_name": "Bash", "tool_input": ti, "cwd": "C:/proj"})
                self.assertIsNotNone(reason)
                self.assertIn("(tests-only)", reason)

    def test_unparsable_blocked(self):
        reason = tests_bash("echo 'x > tests/a")
        self.assertIsNotNone(reason)
        self.assertIn("(tests-only)", reason)

    def test_cp_links_blocked_variants(self):
        for cmd in ["cp --li src/app.py tests/a.py", "cp --symbolic-link a tests/b",
                    "cp --sym a tests/b", "cp -rl a tests/b", "cp -ls a tests/b"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd))
        self.assertIn("enlace", tests_bash("cp -l src/app.py tests/a.py"))

    def test_cp_plain_allowed(self):
        self.assertIsNone(tests_bash("cp a tests/b"))
        self.assertIsNone(tests_bash("cp -r src tests/fixtures/x"))
        self.assertIsNone(tests_bash("cp -t tests/fixtures src/app.py"))

    def test_dir_change_variants_blocked(self):
        for cmd in ["chdir .. && rm tests/a", "sl .. ; rm tests/a", "builtin pushd .. && rm tests/a",
                    "env --ch=.. rm tests/a", "env -iC .. rm tests/a", "env --chdir .. rm tests/a",
                    "sudo --chdir .. rm tests/a", "doas -D .. rm tests/a",
                    "find tests -execdir rm tests/x \\;"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd))

    def test_env_sudo_without_chdir_allowed(self):
        self.assertIsNone(tests_bash("env FOO=1 rm tests/a"))
        self.assertIsNone(tests_bash("sudo -u x rm tests/a"))

    def test_dir_change_message(self):
        reason = tests_bash("cd src && rm tests/a")
        self.assertIn("rutas relativas", reason)
        self.assertIn("sin cambiar de directorio", reason)
        self.assertNotIn("--allow-temp", reason)
        reason = tests_bash("cd .. && echo x > tests/a")
        self.assertIn("rutas relativas", reason)
        self.assertNotIn("--allow-temp", reason)
        reason = tests_bash("echo x > tests/a", cwd=None)
        self.assertNotIn("--allow-temp", reason)
        self.assertIn("directorio temporal", reason)

    def test_readonly_unchanged(self):
        reason = bash("echo x > tests/a.txt")
        self.assertIn("(readonly)", reason)
        self.assertIsNotNone(bash("rm tests/a.txt", allow_temp=True))


class Cli(unittest.TestCase):
    def run_guard(self, args, stdin):
        if not isinstance(stdin, bytes):
            stdin = stdin.encode("utf-8")
        return subprocess.run([sys.executable, SCRIPT] + args, input=stdin,
                              capture_output=True, timeout=30)

    def payload(self, cmd):
        return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                           "tool_input": {"command": cmd}, "cwd": "C:\\proj"})

    def test_allow_exit0_silent(self):
        r = self.run_guard(["readonly"], self.payload("git diff"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"")
        self.assertEqual(r.stderr, b"")

    def test_block_exit2_stderr(self):
        r = self.run_guard(["readonly"], self.payload("git commit -m x"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Bloqueado por agent_guard", r.stderr.decode("utf-8"))

    def test_block_unicode_command(self):
        r = self.run_guard(["readonly"], self.payload("echo ñandú > salida.txt"))
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr)

    def test_allow_temp_flag(self):
        self.assertEqual(self.run_guard(["readonly", "--allow-temp"],
                                        self.payload("rm /tmp/x")).returncode, 0)
        self.assertEqual(self.run_guard(["readonly"], self.payload("rm /tmp/x")).returncode, 2)

    def test_tests_only_cli(self):
        ok = json.dumps({"tool_name": "Write", "cwd": "C:\\p", "tool_input": {"file_path": "C:\\p\\tests\\a.py"}})
        bad = json.dumps({"tool_name": "Write", "cwd": "C:\\p", "tool_input": {"file_path": "C:\\p\\src\\a.py"}})
        self.assertEqual(self.run_guard(["tests-only"], ok).returncode, 0)
        r = self.run_guard(["tests-only"], bad)
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr)

    def test_invalid_json(self):
        r = self.run_guard(["readonly"], "no es json")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr)

    def test_empty_stdin(self):
        self.assertEqual(self.run_guard(["readonly"], "").returncode, 2)

    def test_invalid_utf8(self):
        self.assertEqual(self.run_guard(["readonly"], b"\xff\xfe\x00{").returncode, 2)

    def test_non_object_json(self):
        for s in ("[]", '"x"', "5", "null"):
            with self.subTest(s=s):
                self.assertEqual(self.run_guard(["readonly"], s).returncode, 2)

    def test_unknown_or_missing_mode(self):
        p = self.payload("git diff")
        for args in ([], ["bogus"], ["--allow-temp"], ["readonly", "extra"]):
            with self.subTest(args=args):
                r = self.run_guard(args, p)
                self.assertEqual(r.returncode, 2)
                self.assertTrue(r.stderr)


class Regressions(GuardTestCase):
    def test_must_stay_allowed(self):
        for cmd in [
            "git diff", 'git log --format="%h > %s" | head', "git show HEAD:src/a.py",
            "git -C . stash list", "git stash show -p stash@{0}", "pytest -q 2>&1 | tail -5",
            "python -B -m pytest tests > /dev/null 2>&1; echo $?", 'rg "a|b;c>d" src',
            "grep -E 'x>y' f 2>&1 | head", 'find . -name "*.py" -newer f', "ls > NUL 2>&1",
            "python - <<'EOF'\nprint(\"it's\")\nEOF", "git branch -vv --sort=-committerdate",
            "git -C 'C:\\proj x' log", "git fetch",
        ]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)


class HeredocAndParsing(GuardTestCase):
    def test_heredoc_variants_then_command(self):
        for delim_form in ["EOF", "'EOF'", '"EOF"', "\\EOF", "E\\OF", "'E'OF"]:
            for op in ("<<", "<<-"):
                cmd = "cat %s%s\nhello\nEOF\nrm -rf x" % (op, delim_form)
                with self.subTest(cmd=cmd):
                    self.assertBlocked(cmd, "'rm'")
                ok = "cat %s%s\nrm -rf x\nEOF\nls" % (op, delim_form)
                with self.subTest(cmd=ok):
                    self.assertAllowed(ok)

    def test_heredoc_dash_strips_tabs(self):
        self.assertAllowed("cat <<-EOF\n\trm x\n\tEOF\nls")
        self.assertBlocked("cat <<-EOF\n\tx\n\tEOF\nrm f", "'rm'")

    def test_heredoc_inside_command_substitution(self):
        self.assertBlocked("echo \"$(cat <<'EOF'\nit's fine\nEOF\n)\" && rm f", "'rm'")
        self.assertBlocked("echo \"$(cat <<EOF\nsay \"hi\" it's\nEOF\n)\" && rm f", "'rm'")
        self.assertAllowed("echo \"$(cat <<'EOF'\nit's fine\nEOF\n)\" && ls")
        self.assertBlocked("x=$(cat <<'EOF'\n\"unbalanced\nEOF\n); rm f", "'rm'")

    def test_unterminated_constructs_fail_closed(self):
        for cmd in ["echo 'abc", 'echo "abc', "echo $(ls", "echo `ls", "cat <<EOF\nabc",
                    "cat <<EOF", "cat <<'EOF'\nabc\n", "echo $'abc", "diff <(ls", "echo \"$(ls\"",
                    "[[ -f x", "cat <<"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "de forma segura")

    def test_ansi_c_quoting(self):
        self.assertBlocked("echo $'a\\'b' > f", "'> f'")
        self.assertAllowed("echo $'a\\'b' > /dev/null")
        self.assertAllowed("echo $'a\\'b'")
        self.assertBlocked("echo $'it\\'s' && rm f", "'rm'")

    def test_line_continuation(self):
        self.assertBlocked("git \\\ncommit -m x", "'git commit'")
        self.assertBlocked("ec\\\nho hi > f", "'> f'")
        self.assertBlocked("echo a \\\n  > out.txt", "'> out.txt'")
        self.assertAllowed("git \\\n  log \\\n  --oneline")

    def test_dev_stream_redirect_targets(self):
        for t in ["/dev/stderr", "/dev/stdout", "/dev/tty", "/dev/fd/1", "/dev/fd/12"]:
            self.assertAllowed("echo hi > %s" % t)
            self.assertAllowed("echo hi >> %s" % t)
        self.assertBlocked("echo hi > /dev/fdx", "'> /dev/fdx'")
        self.assertBlocked("echo hi > /dev/sda", "'> /dev/sda'")

    def test_comparisons_are_not_redirections(self):
        for cmd in [
            "(( a > b ))", "(( a < b )) && echo y", "if (( x > 1 )); then echo y; fi",
            "[[ a > b ]]", "[[ $a < $b ]] && echo y", "if [[ x > y ]]; then echo y; fi",
            "for ((i=0; i<3; i++)); do echo $i; done", "echo $(( 1 << 2 ))", "echo $((a>b))",
            "[[ \"a>b\" == x ]]",
        ]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_comparison_constructs_still_see_substitutions_and_what_follows(self):
        self.assertBlocked("(( a > b )) && rm f", "'rm'")
        self.assertBlocked("[[ a > b ]] && echo c > f", "'> f'")
        self.assertBlocked("[[ $(rm f) == x ]]", "'rm'")
        self.assertBlocked("(( $(rm f) > 1 ))", "'rm'")
        self.assertBlocked("echo $(( $(rm f) + 1 ))", "'rm'")
        self.assertBlocked("[[ \"it's $(rm f)\" == x ]]", "'rm'")
        self.assertBlocked("echo [[ a ]] > f", "'> f'")  # no esta en posicion de comando


class GitReadOnlyForms(GuardTestCase):
    def test_allowed(self):
        for cmd in [
            "git config user.name", "git config --global user.email", "git config get user.name",
            "git config list", "git config --local core.editor", "git config -f .gitmodules --get x",
            "git tag --sort=-creatordate", "git tag --sort -creatordate", "git tag -n",
            "git tag -n5", "git tag --contains abc123", "git tag --points-at HEAD",
            "git tag --merged HEAD", "git tag --no-merged main", "git tag --format '%(refname)'",
            "git tag -l 'v*'", "git tag -n 'v*'", "git tag --contains abc 'v*'",
            "git submodule status", "git submodule summary", "git submodule",
            "git submodule --quiet status",
            "git bisect log", "git bisect visualize", "git bisect view",
            "git format-patch -1 HEAD --stdout", "git notes", "git notes list", "git notes show HEAD",
            "git sparse-checkout list", "git reflog", "git reflog show HEAD", "git reflog -n 5",
            "git symbolic-ref HEAD", "git symbolic-ref --short HEAD", "git bundle verify x.bundle",
            "git bundle list-heads x.bundle", "git archive HEAD | tar -t",
        ]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_config_blocked(self):
        for cmd in [
            "git config user.name x", "git config --global user.email a@b", "git config set a b",
            "git config set a", "git config unset a", "git config edit", "git config --edit",
            "git config -e", "git config rename-section a b", "git config remove-section a",
            "git config --unset a", "git config --unset-all a", "git config --add a b",
            "git config --replace-all a b", "git config --rename-section a b",
            "git config --remove-section a", "git config --global --get-all x --unset y",
        ]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'git config'")

    def test_tag_blocked(self):
        for cmd in [
            "git tag v1", "git tag -d v1", "git tag -a v1 -m x", "git tag -s v1", "git tag -u K v1",
            "git tag -f v1", "git tag -m x v1", "git tag -F f v1", "git tag --delete v1",
            "git tag --force v1", "git tag v1 abc123", "git tag --sort=x v1", "git tag -l -d v1",
            "git tag --contains abc -d v1",
        ]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'git tag'")

    def test_submodule_blocked(self):
        for cmd in ["git submodule update", "git submodule add u p", "git submodule init",
                    "git submodule foreach 'rm x'", "git submodule sync", "git submodule deinit x"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'git submodule'")

    def test_other_mutating_forms_blocked(self):
        for cmd, needle in [
            ("git bisect start", "'git bisect'"), ("git bisect good", "'git bisect'"),
            ("git bisect reset", "'git bisect'"), ("git bisect", "'git bisect'"),
            ("git format-patch -1 HEAD", "'git format-patch'"),
            ("git format-patch -o out main", "'git format-patch'"),
            ("git diff --output=out.patch", "--output"), ("git diff --output out.patch", "--output"),
            ("git log --output=x", "--output"), ("git show --output out HEAD", "--output"),
            ("git -C r diff --output=out.patch", "--output"),
            ("git archive -o out.zip HEAD", "'git archive -o'"),
            ("git archive --output=out.zip HEAD", "--output"),
            ("git archive --output out.zip HEAD", "--output"),
            ("git archive -oout.zip HEAD", "'git archive -o'"),
            ("git notes add -m x", "'git notes'"), ("git notes remove", "'git notes'"),
            ("git notes --ref x append -m y", "'git notes'"),
            ("git sparse-checkout set src", "'git sparse-checkout'"),
            ("git sparse-checkout disable", "'git sparse-checkout'"),
            ("git sparse-checkout", "'git sparse-checkout'"),
            ("git reflog expire --all", "'git reflog'"), ("git reflog delete HEAD@{1}", "'git reflog'"),
            ("git symbolic-ref HEAD refs/heads/x", "'git symbolic-ref'"),
            ("git symbolic-ref -d HEAD", "'git symbolic-ref'"),
            ("git bundle create x.bundle HEAD", "'git bundle'"),
            ("git bundle unbundle x.bundle", "'git bundle'"),
        ]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, needle)


class ShellToolsAndPackages(GuardTestCase):
    def test_package_managers_blocked(self):
        for cmd, needle in [
            ("pnpm i", "'pnpm i'"), ("pnpm rm x", "'pnpm rm'"), ("pnpm up", "'pnpm up'"),
            ("npm add x", "'npm add'"), ("npm rm x", "'npm rm'"), ("npm un x", "'npm un'"),
            ("npm r x", "'npm r'"), ("npm up", "'npm up'"), ("npm it", "'npm it'"),
            ("yarn", "'yarn'"), ("yarn --frozen-lockfile", "'yarn'"),
            ("apt purge x", "'apt purge'"), ("apt-get dist-upgrade", "'apt-get dist-upgrade'"),
            ("apt autoremove", "'apt autoremove'"), ("apt-get purge x", "'apt-get purge'"),
            ("pip3.11 install x", "'pip3.11 install'"), ("pip3.12 uninstall x", "'pip3.12"),
            ("pip3 install x", "'pip3 install'"), ("python3.11 -m pip3.11 install x", "pip"),
            ("python -m pip3 install x", "pip"),
        ]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, needle)

    def test_package_managers_read_only_allowed(self):
        for cmd in ["yarn --version", "yarn -v", "yarn --help", "yarn list", "pnpm ls",
                    "pnpm run build", "npm run test", "npm view x", "apt list", "apt show x",
                    "pip3.11 list", "pip3.11 show x", "python3.11 -m pip3.11 list"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_file_writers_blocked(self):
        for cmd, needle in [
            ("unlink f", "'unlink'"), ("sort -o out f", "'sort -o'"),
            ("sort --output out f", "'sort -o'"), ("sort --output=out f", "'sort -o'"),
            ("sort -ro out f", "'sort -o'"), ("sort -oout f", "'sort -o'"),
            ("curl -o out http://x", "'curl'"), ("curl -O http://x", "'curl'"),
            ("curl --output out http://x", "'curl'"), ("curl --remote-name http://x", "'curl'"),
            ("curl -sSLo out http://x", "'curl'"), ("curl -sO http://x", "'curl'"),
            ("curl --output=out http://x", "'curl'"),
            ("wget http://x", "'wget'"), ("wget -O out http://x", "'wget'"),
            ("wget -q http://x", "'wget'"), ("wget -O - http://x > out", "'> out'"),
        ]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, needle)

    def test_file_writers_allowed(self):
        for cmd in ["sort f", "sort -n -k2 f", "sort -u -t, -k1,1 f | head", "curl http://x",
                    "curl -sSL http://x | head", "curl -X POST -H 'a: b' http://x",
                    "wget -O - http://x", "wget -O- http://x", "wget -qO- http://x",
                    "wget -qO - http://x", "wget --spider http://x",
                    "wget --output-document=- http://x", "wget --output-document - http://x"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_perl_inplace_with_l_and_0(self):
        for cmd in ["perl -lpi -e 's/a/b/' f", "perl -lpi.bak -e 1 f", "perl -l -pi -e 1 f",
                    "perl -0pi -e 1 f", "perl -0777pi -e 1 f", "perl -l0pi -e 1 f",
                    "perl -l012 -i -e 1 f", "perl -pi -e 1 f"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'perl'")
        for cmd in ["perl -lne 'print' f", "perl -0777ne 'print' f", "perl -l -e 1",
                    "perl -le 'print 1'", "perl -ne 'print' f"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)


class AllowTempFindings(GuardTestCase):
    def test_target_directory(self):
        self.assertBlocked("cp -t /home/u/proj /tmp/a", "'cp'", allow_temp=True)
        self.assertBlocked("cp --target-directory=/home/u/proj /tmp/a", "'cp'", allow_temp=True)
        self.assertBlocked("cp --target-directory /home/u/proj /tmp/a", "'cp'", allow_temp=True)
        self.assertBlocked("cp -rt /home/u/proj /tmp/a", "'cp'", allow_temp=True)
        self.assertBlocked("cp -t/home/u/proj /tmp/a", "'cp'", allow_temp=True)
        self.assertBlocked("mv -t /home/u/proj /tmp/a", "'mv'", allow_temp=True)
        self.assertBlocked("mv -t /tmp/d a", "'mv'", allow_temp=True)
        self.assertBlocked("cp -t /tmp/d", "'cp'", allow_temp=True)
        self.assertAllowed("cp -t /tmp/d a b", allow_temp=True)
        self.assertAllowed("cp --target-directory=/tmp/d a", allow_temp=True)
        self.assertAllowed("cp -t /tmp/ /home/u/a", allow_temp=True)
        self.assertAllowed("mv -t /tmp/d /tmp/a /tmp/b", allow_temp=True)

    def test_exact_temp_dir_is_a_copy_move_destination(self):
        for cmd in ["cp a b /tmp/", "cp a /tmp", "cp -r a /tmp/", "mv /tmp/a /tmp/",
                    "mv /tmp/a /tmp", "cp a $TMPDIR", "cp a $TMPDIR/",
                    "cp a /var/tmp/", "cp a C:/Users/u/AppData/Local/Temp/",
                    "cp a C:/Users/u/AppData/Local/Temp"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)
        for cmd in ["cp a /tmpx/", "cp a /tmp/../", "cp a %TEMP%/", "cp a /home/", "mv a /tmp/", "mv /tmp/ /tmp/b",
                    "cp /tmp/ b", "mv /tmp /tmp/b"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, allow_temp=True)

    def test_exact_temp_dir_not_deletable(self):
        for cmd in ["rm /tmp", "rm /tmp/", "rmdir /tmp", "rmdir /tmp/", "rm -rf $TMPDIR",
                    "rm $TMPDIR/", "touch /tmp/", "mkdir /tmp"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, allow_temp=True)

    def test_dev_streams_with_allow_temp(self):
        self.assertAllowed("echo hi > /dev/stderr", allow_temp=True)


class TestsOnlyAncestors(unittest.TestCase):
    def blocked(self, path, cwd, tool="Write"):
        reason = tests_only(tool, cwd, file_path=path)
        self.assertIsNotNone(reason, "debio bloquear %r (cwd=%r)" % (path, cwd))
        self.assertIn("tests-only", reason)

    def allowed(self, path, cwd, tool="Write"):
        self.assertIsNone(tests_only(tool, cwd, file_path=path), "debio permitir %r" % path)

    def test_ancestor_named_like_test_dir_does_not_enable_writes(self):
        self.blocked("C:\\Users\\test\\proj\\src\\app.py", "C:\\Users\\test\\proj")
        self.blocked("/home/spec/proj/src/app.py", "/home/spec/proj")
        self.blocked("D:\\e2e\\shop\\src\\main.py", "D:\\e2e\\shop")
        self.blocked("/home/tests/x/src/a.py", "/home/tests/x")

    def test_inside_cwd_test_dirs_work(self):
        self.allowed("C:\\Users\\test\\proj\\tests\\a.py", "C:\\Users\\test\\proj")
        self.allowed("/home/spec/proj/tests/a.py", "/home/spec/proj")
        self.allowed("D:\\e2e\\shop\\e2e\\login.ts", "D:\\e2e\\shop")
        self.allowed("C:\\p\\src\\fixtures\\d.json", "C:\\p\\")

    def test_cwd_forms_and_case(self):
        self.allowed("C:\\Users\\u\\proj\\tests\\a.py", "/c/Users/u/proj")
        self.allowed("/c/Users/u/proj/tests/a.py", "C:\\Users\\u\\proj")
        self.allowed("/mnt/c/Users/u/proj/tests/a.py", "C:\\Users\\u\\proj")
        self.allowed("c:/users/u/PROJ/Tests/a.py", "C:\\Users\\u\\proj")
        self.allowed("C:/Users/u/proj/tests/a.py", "C:/Users/u/proj/")
        self.blocked("/c/Users/test/proj/src/a.py", "C:\\Users\\test\\proj")
        self.blocked("C:\\Users\\test\\proj\\src\\a.py", "/c/Users/test/proj")

    def test_outside_cwd_or_no_cwd_only_temp(self):
        # Ronda 6: fuera de cwd (o sin cwd) una ruta absoluta solo vale si es temporal
        # (antes solo contaba el nombre del archivo: `~/.claude/rules/evil.test.md` pasaba).
        self.blocked("/other/tests/a.py", "/home/u/proj")
        self.blocked("/other/tests/a.py", None)
        self.blocked("/other/tests/a.py", "")
        self.blocked("/other/tests/a.py", "   ")
        self.blocked("/home/u/projx/tests/a.py", "/home/u/proj")  # prefijo parcial no es hijo
        self.blocked("/other/src/test_a.py", "/home/u/proj")
        self.blocked("/other/src/test_a.py", None)
        self.blocked("C:\\x\\src\\b.spec.ts", None)
        self.blocked("C:\\x\\tests\\b.ts", None)
        self.allowed("/tmp/src/test_a.py", "/home/u/proj")
        self.allowed("/tmp/src/test_a.py", None)
        self.allowed("C:\\Users\\u\\AppData\\Local\\Temp\\b.spec.ts", None)
        self.blocked("/tmp/src/a.py", None)

    def test_relative_path_evaluated_as_given(self):
        self.allowed("tests/a.py", None)
        self.allowed("tests/a.py", "/home/u/proj")
        self.blocked("src/a.py", "/home/tests/proj")

    def test_dotdot_still_blocked(self):
        self.blocked("tests/../src/a.py", "/home/u/proj")
        self.blocked("/home/u/proj/tests/../src/a.py", "/home/u/proj")
        self.blocked("/home/u/proj/../tests/a.py", "/home/u/proj")
        self.blocked("C:\\p\\tests\\..\\src\\a.py", "C:\\p")

    def test_all_edit_tools_use_cwd(self):
        self.blocked("/home/spec/proj/src/a.py", "/home/spec/proj", "Edit")
        self.assertIsNotNone(tests_only("NotebookEdit", "/home/spec/proj",
                                        notebook_path="/home/spec/proj/src/a.ipynb"))
        self.assertIsNone(tests_only("NotebookEdit", "/home/spec/proj",
                                     notebook_path="/home/spec/proj/tests/a.ipynb"))

    def test_case_sensitive_test_patterns(self):
        for p in ["src/main/java/Latest.java", "src/Contests.cs", "src/Attests.java",
                  "src/latest.java", "src/Contest.java", "src/FooTESTS.cs", "src/footest.java"]:
            with self.subTest(path=p):
                self.blocked(p, "C:\\proj")
        for p in ["src/FooTest.java", "src/FooTests.java", "src/FooTests.cs", "FooTest.java",
                  "C:\\proj\\src\\FooTests.cs"]:
            with self.subTest(path=p):
                self.allowed(p, "C:\\proj")
        self.allowed("src/tests/Latest.java", "C:\\proj")  # bajo carpeta de pruebas


class EntryPoint(unittest.TestCase):
    def run_main(self, args, data, check_side_effect=None):
        stdin = mock.Mock()
        stdin.buffer = io.BytesIO(data)
        stderr = mock.Mock()
        stderr.buffer = io.BytesIO()
        patches = [mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stderr", stderr)]
        if check_side_effect is not None:
            patches.append(mock.patch.object(agent_guard, "check", side_effect=check_side_effect))
        for p in patches:
            p.start()
        try:
            code = agent_guard.main(args)
        finally:
            for p in patches:
                p.stop()
        return code, stderr.buffer.getvalue().decode("utf-8")

    def payload(self, cmd="git diff"):
        return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}).encode("utf-8")

    def test_internal_error_returns_2(self):
        for exc in (RuntimeError("boom"), RecursionError(), MemoryError(), KeyError("k"),
                    ValueError("v"), KeyboardInterrupt()):
            with self.subTest(exc=type(exc).__name__):
                code, err = self.run_main(["readonly"], self.payload(), exc)
                self.assertEqual(code, 2)
                self.assertIn("agent_guard", err)
                self.assertIn(type(exc).__name__, err)

    def test_system_exit_codes(self):
        for raised in (0, 2):
            with self.subTest(code=raised):
                with self.assertRaises(SystemExit) as cm:
                    self.run_main(["readonly"], self.payload(), SystemExit(raised))
                self.assertEqual(cm.exception.code, raised)
        for raised in (1, 3, 127, "x", None):
            with self.subTest(code=raised):
                code, err = self.run_main(["readonly"], self.payload(), SystemExit(raised))
                self.assertEqual(code, 2)
                self.assertTrue(err)

    def test_normal_paths(self):
        self.assertEqual(self.run_main(["readonly"], self.payload("git diff"))[0], 0)
        code, err = self.run_main(["readonly"], self.payload("git commit"))
        self.assertEqual(code, 2)
        self.assertIn("'git commit'", err)

    def test_bom_is_stripped(self):
        code, _ = self.run_main(["readonly"], b"\xef\xbb\xbf" + self.payload("git diff"))
        self.assertEqual(code, 0)
        code, err = self.run_main(["readonly"], b"\xef\xbb\xbf" + self.payload("rm f"))
        self.assertEqual(code, 2)
        self.assertIn("'rm'", err)


class CliFindings(unittest.TestCase):
    """Cada hallazgo pasa por el proceso real: codigo de salida observado."""

    def run_guard(self, args, stdin):
        if not isinstance(stdin, bytes):
            stdin = stdin.encode("utf-8")
        return subprocess.run([sys.executable, "-B", SCRIPT] + args, input=stdin,
                              capture_output=True, timeout=60)

    def bash_code(self, cmd, args=("readonly",)):
        p = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "C:\\proj"})
        return self.run_guard(list(args), p)

    def write_code(self, path, cwd):
        p = json.dumps({"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": cwd})
        return self.run_guard(["tests-only"], p).returncode

    def test_finding_1_ancestor_dirs(self):
        self.assertEqual(self.write_code("C:\\Users\\test\\proj\\src\\app.py",
                                         "C:\\Users\\test\\proj"), 2)
        self.assertEqual(self.write_code("/home/spec/proj/src/app.py", "/home/spec/proj"), 2)
        self.assertEqual(self.write_code("D:\\e2e\\shop\\src\\main.py", "D:\\e2e\\shop"), 2)
        self.assertEqual(self.write_code("D:\\e2e\\shop\\tests\\main.py", "D:\\e2e\\shop"), 0)

    def test_findings_2_3_parsing(self):
        for cmd in ["cat <<\\EOF\nhello\nEOF\nrm -rf x",
                    "echo \"$(cat <<'EOF'\nit's fine\nEOF\n)\" && rm f",
                    "echo $'a\\'b' > f", "echo 'abc", "cat <<EOF\nabc"]:
            with self.subTest(cmd=cmd):
                r = self.bash_code(cmd)
                self.assertEqual(r.returncode, 2)
                self.assertTrue(r.stderr)

    def test_finding_4_read_only_git_allowed(self):
        for cmd in ["git config user.name", "git config --global user.email",
                    "git config get user.name", "git config list", "git tag --sort=-creatordate",
                    "git tag -n", "git tag --contains abc123", "git tag --points-at HEAD",
                    "git submodule status", "git submodule summary"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash_code(cmd).returncode, 0)

    def test_finding_5_mutating_git_blocked(self):
        for cmd in ["git bisect start", "git format-patch -1 HEAD", "git diff --output=out.patch",
                    "git diff --output out.patch", "git archive -o out.zip HEAD",
                    "git notes add -m x", "git sparse-checkout set src", "git reflog expire --all",
                    "git reflog delete HEAD@{1}", "git symbolic-ref HEAD refs/heads/x",
                    "git bundle create x HEAD"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash_code(cmd).returncode, 2)

    def test_findings_6_7_minor_blocks(self):
        for cmd, needle in [("pnpm i", "'pnpm i'"), ("npm rm x", "'npm rm'"), ("yarn", "'yarn'"),
                            ("apt purge x", "'apt purge'"),
                            ("pip3.11 install x", "'pip3.11 install'"), ("unlink f", "'unlink'"),
                            ("sort -o out f", "'sort -o'"),
                            ("curl -o out http://x", "'curl'"), ("wget http://x", "'wget'"),
                            ("perl -lpi -e 's/a/b/' f", "'perl'")]:
            with self.subTest(cmd=cmd):
                r = self.bash_code(cmd)
                self.assertEqual(r.returncode, 2)
                self.assertIn(needle, r.stderr.decode("utf-8"))

    def test_finding_8_allow_temp(self):
        a = ["readonly", "--allow-temp"]
        self.assertEqual(self.bash_code("cp -t /home/u/proj /tmp/a", a).returncode, 2)
        self.assertEqual(self.bash_code("cp a b /tmp/", a).returncode, 0)
        self.assertEqual(self.bash_code("rm /tmp/", a).returncode, 2)

    def test_finding_9_redirect_false_positives(self):
        for cmd in ["echo hi > /dev/stderr", "echo hi > /dev/stdout", "echo hi > /dev/tty",
                    "echo hi > /dev/fd/2", "(( a > b ))", "[[ a > b ]]"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash_code(cmd).returncode, 0)

    def test_finding_10_deep_json_fails_closed(self):
        r = self.run_guard(["readonly"], b"[" * 200000)
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr)
        r = self.run_guard(["tests-only"], b"{\"a\":" * 100000)
        self.assertEqual(r.returncode, 2)

    def test_finding_10_bom(self):
        p = b"\xef\xbb\xbf" + json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "git diff"}}).encode("utf-8")
        self.assertEqual(self.run_guard(["readonly"], p).returncode, 0)

    def test_finding_11_case_sensitive_patterns(self):
        self.assertEqual(self.write_code("src/main/java/Latest.java", "C:\\proj"), 2)
        self.assertEqual(self.write_code("src/Contests.cs", "C:\\proj"), 2)
        self.assertEqual(self.write_code("src/FooTest.java", "C:\\proj"), 0)


class HeredocSubstitutions(GuardTestCase):
    def test_unquoted_body_runs_substitutions(self):
        for cmd in ["cat <<EOF\n$(rm -rf x)\nEOF", "cat <<EOF\n`rm -rf x`\nEOF",
                    "x=$(cat <<EOF\n$(rm f)\nEOF\n)", "cat <<-EOF\n\t$(rm f)\n\tEOF",
                    "cat <<EOF\nit's $(rm f)\nEOF", "cat <<A <<B\nx\nA\n$(rm f)\nB",
                    "cat <<EOF\n$(echo $(rm f))\nEOF"]:
            with self.subTest(cmd=cmd):
                reason = self.assertBlocked(cmd, "'rm'")
                self.assertNotIn("de forma segura", reason)

    def test_quoted_delimiter_bodies_are_skipped(self):
        for q in ["'EOF'", '"EOF"', "\\EOF", "$'EOF'", '$"EOF"', "E\\OF"]:
            for body in ["$(rm x)", "`rm x`"]:
                cmd = "cat <<%s\n%s\nEOF" % (q, body)
                with self.subTest(cmd=cmd):
                    self.assertAllowed(cmd)

    def test_unquoted_harmless_bodies_allowed(self):
        self.assertAllowed("cat <<EOF\n$(date) it's\nEOF")
        self.assertAllowed("cat <<EOF\n\\$(rm x)\nEOF")
        self.assertAllowed("cat <<EOF\njust text\nEOF\nls")

    def test_ansi_and_locale_quoted_delimiters(self):
        self.assertBlocked("cat <<$'EOF'\nbody\nEOF\nrm -rf x\n$EOF", "'rm'")
        self.assertAllowed("cat <<$'EOF'\nbody\nEOF\nls")
        self.assertBlocked('cat <<$"EOF"\nbody\nEOF\nrm -rf x', "'rm'")
        self.assertAllowed('cat <<$"EOF"\nbody\nEOF\nls')


class OutputTargets(GuardTestCase):
    def test_allowed(self):
        for cmd in ["curl -s -o /dev/null -w '%{http_code}' http://localhost:8080",
                    "curl -o - http://x", "curl -o- http://x", "curl -so /dev/null http://x",
                    "curl --output /dev/null http://x", "curl --output=- http://x",
                    "curl -XPOST http://x", "wget -q -O /dev/null http://x", "wget -O - u",
                    "wget -qO/dev/null u", "wget --output-document=/dev/null u",
                    "echo x | tee", "echo a | tee /dev/null", "echo a | tee -a /dev/null",
                    "sort -o /dev/stdout f", "sort -o - f", "sort -t o f"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_blocked(self):
        for cmd, needle in [("curl -o out.html http://x", "'curl'"),
                            ("curl -o- -o out http://x", "'curl'"),
                            ("curl -s -o f -w '%{http_code}' http://x", "'curl'"),
                            ("curl --output out.html http://x", "'curl'"),
                            ("curl -O http://x", "'curl'"),
                            ("wget -O f u", "'wget'"), ("wget -O /dev/null -O f u", "'wget'"),
                            ("wget -qO f u", "'wget'"), ("tee f", "'tee'"),
                            ("echo a | tee /dev/null f", "'tee'"),
                            ("echo a | tee -a f", "'tee'"), ("sort -o f g", "'sort -o'"),
                            ("sort --output=f g", "'sort -o'")]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, needle)

    def test_tee_with_allow_temp(self):
        self.assertAllowed("echo x | tee", allow_temp=True)
        self.assertAllowed("echo x | tee /dev/null /tmp/f", allow_temp=True)
        self.assertBlocked("echo x | tee f", "'tee'", allow_temp=True)


class PackageAliases(GuardTestCase):
    def test_npm_aliases_blocked(self):
        for sub in ["remove", "unlink", "upgrade", "udpate", "in", "ins", "inst", "insta",
                    "instal", "isnt", "isnta", "isntal", "isntall", "clean-install", "ic",
                    "install-clean", "isntall-clean", "install-test", "install-ci-test", "cit"]:
            with self.subTest(sub=sub):
                self.assertBlocked("npm %s" % sub, "'npm %s'" % sub)
        self.assertBlocked("npm version patch", "'npm version'")
        self.assertBlocked("npm audit fix", "'npm audit fix'")
        self.assertBlocked("npm audit fix --force", "'npm audit fix'")

    def test_pnpm_yarn_aliases_blocked(self):
        for cmd, needle in [("pnpm uninstall x", "'pnpm uninstall'"), ("pnpm un x", "'pnpm un'"),
                            ("pnpm upgrade", "'pnpm upgrade'"), ("yarn up", "'yarn up'"),
                            ("yarn --cwd sub", "'yarn'"), ("yarn --cwd sub add x", "'yarn add'"),
                            ("npm --prefix sub install", "'npm install'")]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, needle)

    def test_read_only_forms_allowed(self):
        for cmd in ["npm audit", "npm version", "npm audit signatures", "yarn --version",
                    "yarn --cwd sub list", "npm --prefix sub ls"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)


class TargetAbbreviations(GuardTestCase):
    def test_blocked_with_allow_temp(self):
        for cmd, needle in [("cp -rt/home/u/proj /tmp/a /tmp/b", "'cp'"),
                            ("mv -ft/home/u/proj /tmp/a /tmp/b", "'mv'"),
                            ("cp --target=/home/u/proj /tmp/a /tmp/b", "'cp'"),
                            ("cp --t=/home/u/proj /tmp/a /tmp/b", "'cp'"),
                            ("cp --target /home/u/proj /tmp/a", "'cp'"),
                            ("cp -rt /home/u/proj /tmp/a", "'cp'")]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, needle, allow_temp=True)

    def test_allowed_with_allow_temp(self):
        for cmd in ["cp -rt/tmp/d a b", "cp --target=/tmp/d a", "mv -ft /tmp/d /tmp/a",
                    "cp --t=/tmp/d a"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)

    def test_sort_output_abbreviations(self):
        for cmd in ["sort --out=x f", "sort --o=x f", "sort --outp x f", "sort --o x f"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'sort -o'")


class LinearCost(GuardTestCase):
    def run_cli(self, cmd):
        p = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        t0 = time.time()
        r = subprocess.run([sys.executable, "-B", SCRIPT, "readonly"], input=p.encode("utf-8"),
                           capture_output=True, timeout=60)
        return r, time.time() - t0

    def test_unclosed_parens_are_fast(self):
        cmd = "rm -rf x\n" + "(" * 20000
        t0 = time.time()
        reason = bash(cmd)  # el costo se mide en proceso: el subprocess es inestable
        self.assertLess(time.time() - t0, 1.0)
        self.assertIn("'rm'", reason)
        r, elapsed = self.run_cli(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("'rm'", r.stderr.decode("utf-8"))
        self.assertLess(elapsed, 5.0)

    def test_arithmetic_after_failed_attempt_still_fails_closed(self):
        self.assertBlocked("((((\nrm f")

    def test_too_long_command_fails_closed(self):
        reason = self.assertBlocked("echo " + "a" * 100001, "demasiado largo")
        self.assertIn("100000", reason)
        self.assertAllowed("echo " + "a" * 1000)
        r, _ = self.run_cli("echo " + "a" * 100001)
        self.assertEqual(r.returncode, 2)


class GitAndArithmeticFalsePositives(GuardTestCase):
    def test_allowed(self):
        for cmd in ["git tag -v v1", "git tag --verify v1", "git notes get-ref", "echo $[1<<2]",
                    "echo $[1>2]", "git hash-object f", "git lfs ls-files", "git lfs status",
                    "git rerere status", "git rerere diff", "nice -n 5 ls", "exec ls"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_old_arithmetic_still_sees_substitutions(self):
        self.assertBlocked("echo $[$(rm f)+1]", "'rm'")
        self.assertBlocked("echo $[1<<2] > f", "'> f'")


class MoreMutators(GuardTestCase):
    def test_git_mutators_blocked(self):
        for cmd, needle in [
                ("git replace a b", "'git replace'"),
                ("git hash-object -w f", "'git hash-object'"),
                ("git hash-object -tw f", "'git hash-object'"),
                ("git hash-object --stdin -w", "'git hash-object'"),
                ("git read-tree HEAD", "'git read-tree'"),
                ("git checkout-index -a", "'git checkout-index'"),
                ("git write-tree", "'git write-tree'"),
                ("git commit-tree T", "'git commit-tree'"),
                ("git maintenance run", "'git maintenance'"),
                ("git repack -a", "'git repack'"), ("git pack-refs --all", "'git pack-refs'"),
                ("git rerere forget f", "'git rerere'"), ("git rerere", "'git rerere'"),
                ("git lfs pull", "'git lfs'"), ("git lfs fetch", "'git lfs'"),
                ("git mergetool", "'git mergetool'"),
                ("git prune-packed", "'git prune-packed'"),
                ("git unpack-objects", "'git unpack-objects'"),
                ("git fast-import", "'git fast-import'"),
                ("git update-server-info", "'git update-server-info'")]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, needle)

    def test_wrapper_words_are_skipped(self):
        for cmd in ["exec rm f", "exec -a x rm f", "nice rm f", "nice -n 5 rm f", "nice -5 rm f",
                    "ionice rm f", "ionice -c 3 rm f", "ionice -c3 -n 4 rm f", "stdbuf -oL rm f",
                    "stdbuf -o L rm f", "setsid rm f", "setsid -f rm f", "nice ionice rm f"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'rm'")


class CliSecondRound(unittest.TestCase):
    def code(self, cmd, args=("readonly",)):
        p = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        return subprocess.run([sys.executable, "-B", SCRIPT] + list(args), input=p.encode("utf-8"),
                              capture_output=True, timeout=60)

    def test_exit_codes(self):
        for cmd, want in [("cat <<EOF\n$(rm -rf x)\nEOF", 2), ("cat <<'EOF'\n$(rm x)\nEOF", 0),
                          ("curl -s -o /dev/null -w '%{http_code}' http://x", 0),
                          ("curl -o out.html x", 2), ("echo x | tee", 0), ("tee f", 2),
                          ("npm isntall", 2), ("yarn --cwd sub", 2), ("npm audit", 0),
                          ("git tag -v v1", 0), ("git replace a b", 2), ("nice rm f", 2),
                          ("echo $[1<<2]", 0)]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.code(cmd).returncode, want)
        r = self.code("cp -rt/home/u/proj /tmp/a /tmp/b", ("readonly", "--allow-temp"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("'cp'", r.stderr.decode("utf-8"))


class BackslashEscapes(unittest.TestCase):
    def test_tests_only_blocked(self):
        for cmd in [
            "rm -rf tests/.\\.", "echo x > tests/.\\./src/app.py", "rm spec\\ial.py",
            "echo x > spec\\ial.py", "rm -rf test\\utils", "cp src/app.py playwright\\.config.ts",
            "echo x > C:/proj/src/test\\ing/x.py", "echo x > src'/tests'\\a",
            "echo x >> tests\\out.txt", "echo x > C:\\proj\\tests\\a.txt",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd), cmd)

    def test_ansi_c_escapes_fail_closed(self):
        for cmd in [
            "echo x > tests/$'\\x2e\\x2e'/src/app.py", "echo x > tests/.$'\\056'/src/app.py",
            "echo x > /tmp/$'\\x2e\\x2e'/c/proj/src/app.py", "echo $'\\u002e' > f",
            "echo $'a\\x41b'", "cat <<$'E\\x4fF'\nx\nEOF\nls",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(bash(cmd, allow_temp=True), cmd)
                self.assertIsNotNone(tests_bash(cmd), cmd)
        self.assertIn("de forma segura", bash("echo $'a\\x41b'"))
        self.assertIsNone(bash("echo $'it\\'s\\\\x'"))

    def test_base_strips_backslash_in_words(self):
        for cmd in ["r\\m -rf src", "c\\d .. && rm tests/a", "\\rm -rf src"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(bash(cmd), cmd)
                self.assertIsNotNone(tests_bash(cmd), cmd)
        self.assertIsNotNone(tests_bash("c\\d .. && rm tests/a"))
        # el parser ya elimina `\x` -> `x` fuera de comillas (como bash): `r\m` llega como
        # `rm` y `_base` solo resuelve rutas de Windows, que ahora solo llegan entre comillas.
        self.assertEqual(agent_guard._base("C:\\Windows\\System32\\rm.exe"), "rm")
        self.assertEqual(agent_guard._base(".\\rm"), "rm")
        self.assertEqual(agent_guard._base("..\\rm.exe"), "rm")
        self.assertIsNotNone(bash('"C:\\Windows\\System32\\rm.exe" -rf src'))
        self.assertIsNotNone(bash('".\\rm" -rf src'))

    def test_git_subcommand_backslash(self):
        self.assertIsNotNone(bash("git comm\\it -m x"))


class WrapperOptions(GuardTestCase):
    def test_blocked(self):
        for cmd in [
            "env -S 'rm -rf src'", "env --split-string='rm -rf src'", "env -iS 'rm src'",
            "env --split 'rm src'", "env --unset FOO rm -rf src", "env --unset=FOO rm -rf src",
            "env --un FOO rm -rf src", "env -u FOO rm -rf src", "env --argv0 x rm -rf src",
            "env -- rm -rf src", "env -a x rm -rf src",
            "timeout --kill-after 1 5 rm -rf src", "timeout --signal KILL 5 rm -rf src",
            "timeout --kill-after=1 5 rm -rf src", "timeout --sig KILL 5 rm -rf src",
            "timeout --preserve-status 5 rm -rf src", "timeout -s KILL 5 rm -rf src",
            "nice --adjustment 5 rm -rf src", "nice --adjustment=5 rm -rf src",
            "stdbuf --output L rm -rf src", "stdbuf --input=L --error L rm -rf src",
            "sudo --user root rm -rf src", "sudo --group g --host h rm -rf src",
            "sudo --prompt x rm -rf src", "doas -u root rm -rf src", "sudo -- rm -rf src",
            "builtin -- rm -rf src", "command -- rm -rf src", "exec -- rm -rf src",
            "coproc rm -rf src", "winpty rm -rf src", "winpty -Xallow-non-tty rm -rf src",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(bash(cmd), cmd)
                self.assertIsNotNone(tests_bash(cmd.replace("src", "src/app.py")), cmd)

    def test_env_split_string_has_reason(self):
        self.assertIn("env -S", bash("env -S 'ls'"))

    def test_dir_change_through_wrappers(self):
        for cmd in ["builtin -- cd .. ; rm -rf tests/", "env --unset FOO -C .. rm tests/a",
                    "timeout --kill-after 1 5 env -C .. rm tests/a",
                    "nice --adjustment 5 sudo -D .. rm tests/a",
                    "coproc cd .. ; rm -rf tests/"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd), cmd)

    def test_allowed(self):
        for cmd in ["env --unset FOO pytest", "timeout --kill-after 1 5 pytest",
                    "timeout --signal KILL 5 ls", "nice --adjustment 5 ls", "stdbuf --output L ls",
                    "sudo --user root cat f", "builtin -- echo hi", "winpty ls", "coproc ls"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(bash(cmd), cmd)
        self.assertIsNone(tests_bash("env --unset FOO rm tests/a"))
        self.assertIsNone(tests_bash("timeout --kill-after 1 5 rm tests/a"))


class FindFileOutputs(GuardTestCase):
    def test_blocked(self):
        for cmd in ["find . -fprint src/app.py", "find . -fprint0 src/app.py",
                    "find . -fprintf src/app.py '%p\\n'", "find . -fls src/app.py",
                    "find . -f\\print src/app.py", "find . -fprint /tmp/x"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "find")  # sin --allow-temp
                if "/tmp/" not in cmd:
                    self.assertIsNotNone(tests_bash(cmd), cmd)

    def test_allowed_destinations(self):
        self.assertAllowed("find . -fprint /tmp/x", allow_temp=True)
        self.assertAllowed("find . -fprintf /tmp/x '%p'", allow_temp=True)
        self.assertAllowed("find . -fprint /dev/null", allow_temp=True)
        self.assertBlocked("find . -fprint src/app.py", allow_temp=True)
        self.assertIsNone(tests_bash("find . -fprint tests/out.txt"))
        self.assertIsNone(tests_bash("find . -fprintf tests/out.txt '%p'"))
        self.assertIsNotNone(tests_bash("find . -fprint src/app.py"))
        self.assertIsNotNone(tests_bash("find . -fprintf src/app.py '%p'"))
        self.assertIsNotNone(tests_bash("find . -fprint"))
        self.assertIsNotNone(tests_bash("cd src && find . -fprint tests/out.txt"))


class ArchiveAndMoreWriters(GuardTestCase):
    def test_blocked(self):
        for cmd in [
            "shred f", "rsync a b", "scp a h:b", "tar -xf a.tar", "tar xf a.tar", "tar xzf a.tgz",
            "tar -xzf a.tgz", "tar --extract -f a.tar", "tar --get -f a.tar", "tar --ext -f a",
            "tar -C src -tf a.tar", "tar --directory=src -tf a.tar", "tar -tf a.tar -C src",
            "tar -zxvf a.tgz", "tar --dir src -tf a",
            "gzip f", "gunzip f.gz", "bzip2 f", "bunzip2 f.bz2", "xz f", "unxz f.xz",
            "gzip -d f.gz", "gzip -9 f", "xz -k f", "gzip -- f",
            "unzip a.zip", "unzip -o a.zip -d out", "7z x a.7z", "7za x a.7z", "7z e a.7z",
            "7z a out.7z f", "7z.exe x a.7z",
        ]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)
                self.assertBlocked(cmd, allow_temp=True)
                self.assertIsNotNone(tests_bash(cmd), cmd)

    def test_allowed(self):
        for cmd in ["tar -tf a.tar", "tar tf a.tar", "tar -tzf a.tgz", "tar --list -f a.tar",
                    "tar -tfx.tar", "tar --exclude=x -tf a.tar",
                    "gzip -c f", "gzip --stdout f", "gzip -t f.gz", "gzip -l f.gz", "gzip -cd f.gz",
                    "gunzip -c f.gz", "gunzip --test f.gz", "xz --list f.xz", "xz -dc f.xz",
                    "bzip2 -t f.bz2", "unzip -l a.zip", "unzip -t a.zip", "unzip -p a.zip x",
                    "7z l a.7z", "7z t a.7z", "7za l a.7z"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)


class IsTestPathHardening(unittest.TestCase):
    def test_rejected(self):
        for p in [".github/workflows/ci.test.yml", ".venv/Lib/site-packages/x_test.pth",
                  "venv/lib/a_test.py", "src/site-packages/a.spec.js", ".git/hooks/a.test.sh",
                  "app.py:x_test.py", "C:\\proj\\app.py:x_test.py", "tests/a.txt:stream",
                  "C:\\proj\\.github\\ci.test.yml", "/home/u/.venv/lib/x_test.pth",
                  "tests/.github/a.py"]:
            with self.subTest(p=p):
                self.assertFalse(agent_guard.is_test_path(p, "C:\\proj"), p)
                self.assertIsNotNone(tests_only("Write", "C:\\proj", file_path=p))

    def test_still_accepted(self):
        for p in ["C:\\proj\\tests\\a.py", "tests/a.py", "src/foo.test.ts", "C:/proj/spec/a.rb"]:
            with self.subTest(p=p):
                self.assertTrue(agent_guard.is_test_path(p, "C:\\proj"), p)
        # el nombre de un ancestro del cwd no cuenta
        self.assertTrue(agent_guard.is_test_path(
            "C:\\work\\venv\\proj\\tests\\a.py", "C:\\work\\venv\\proj"))


class TempBraceVariables(GuardTestCase):
    def test_allowed(self):
        for cmd in ["rm ${TMPDIR}/x", "rm ${TEMP}/a", "rm ${TMP}/b", "echo x > ${TMPDIR}/o",
                    "cp a ${TMPDIR}/b", "mkdir ${TMP}/d"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)

    def test_blocked(self):
        for cmd in ["rm {src/app.py,x/appdata/local/temp/y}", "rm /tmp/{a,b}",
                    "rm ${TMPDIR}", "rm ${OTHER}/x", "rm x/${TMPDIR}/y", "rm ${TMPDIR}/{a,b}",
                    "rm ${TMPDIR/../x}", "rm ${TMPDIR}/../x", "rm ${HOME}/x",
                    "rm ${TMPDIR:-/home}/x"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, allow_temp=True)
        self.assertBlocked("rm ${TMPDIR}/x")  # sin --allow-temp


class RoundFour(GuardTestCase):
    def blocked_everywhere(self, cmd):
        self.assertIsNotNone(bash(cmd), cmd)
        self.assertIsNotNone(bash(cmd, allow_temp=True), cmd)
        self.assertIsNotNone(tests_bash(cmd), cmd)

    # A: el parser emula a bash, `\x` -> `x` fuera de comillas
    def test_backslash_inside_words_is_removed(self):
        for cmd in [
            "/bin/r\\m -rf src", "nohup /bin/r\\m -rf src", "/usr/bin/gi\\t commit -m x",
            "/usr/bin/en\\v -C src touch x", "pip in\\stall x", "npm in\\stall",
            "python -m pi\\p install x", "sed --in-pl\\ace s/a/b/ f",
            "curl --out\\put f u", "sort --out\\put=f", "tar --ext\\ract -f a.tar",
            "cp --li\\nk a /tmp/x", "7z \\x a.7z",
        ]:
            with self.subTest(cmd=cmd):
                self.blocked_everywhere(cmd)

    def test_parser_matches_bash_for_backslash(self):
        self.assertEqual(agent_guard.parse_commands("echo x >> tests\\out.txt"),
                         [(["echo", "x"], [(">>", "testsout.txt")])])
        self.assertEqual(agent_guard.parse_commands("echo a\\ b"), [(["echo", "a b"], [])])
        self.assertEqual(agent_guard.parse_commands('echo "a\\.b"'), [(["echo", "a\\.b"], [])])
        self.assertEqual(agent_guard.parse_commands("echo 'a\\.b'"), [(["echo", "a\\.b"], [])])

    def test_backslash_reads_not_blocked_too_much(self):
        for cmd in ['grep "a\\.b" f', "sed 's/a\\.b/c/' f", "git log --format=%h\\ %s",
                    "git -C C:/proj status", "pytest tests/test_a.py", "echo a\\ b"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)
                self.assertAllowed(cmd, allow_temp=True)
                if "\\" in cmd and cmd != "sed 's/a\\.b/c/' f":
                    # modo estricto (ronda 5): tests-only rechaza `\` fuera de comillas simples
                    self.assertIn("sintaxis no admitida", tests_bash(cmd))
                else:
                    self.assertIsNone(tests_bash(cmd), cmd)

    def test_tests_only_unquoted_windows_path_stays_blocked(self):
        # bash lo ve como `testsout.txt`: no es una ruta de pruebas
        self.assertIsNotNone(tests_bash("echo x >> tests\\out.txt"))

    def test_quoted_windows_path_message_says_use_slash(self):
        for cmd, allow in [
            ('echo hi > "C:\\Users\\u\\AppData\\Local\\Temp\\x.txt"', True),
            ('rm "C:\\Users\\u\\AppData\\Local\\Temp\\x.txt"', True),
            ('cp a "C:\\Users\\u\\AppData\\Local\\Temp\\x.txt"', True),
        ]:
            with self.subTest(cmd=cmd):
                reason = self.assertBlocked(cmd, "usa '/'", allow_temp=allow)
                self.assertNotIn("solo se permite escribir bajo un directorio temporal", reason)
        for cmd in ['echo x > "tests\\out.txt"', 'rm "tests\\old.txt"']:
            with self.subTest(cmd=cmd):
                self.assertIn("usa '/'", tests_bash(cmd))

    # B: $"..."
    def test_dollar_double_quote(self):
        for cmd in ['$"rm" -rf src', 'git $"commit" -m x', 'env -C .. $"rm" -rf src',
                    '$"cd" .. && rm -rf tests/']:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd), cmd)
                if "cd" not in cmd:
                    self.assertIsNotNone(bash(cmd), cmd)
        self.assertAllowed('echo $"hi"')
        self.assertEqual(agent_guard.parse_commands('echo $"a b"'), [(["echo", "a b"], [])])

    # C: find -exec con cambio de directorio interno
    def test_find_exec_inner_dir_change(self):
        for cmd in [
            "find . -maxdepth 0 -exec env -C .. rm -rf tests/ \\;",
            "find . -maxdepth 0 -exec env --chdir=.. rm -rf tests/ \\;",
            "find . -maxdepth 0 -exec sudo -D .. rm -rf tests/ \\;",
            "find . -maxdepth 0 -exec timeout 5 env -C .. touch tests/x \\;",
            "find . -maxdepth 0 -ok env -C .. rm -rf tests/ \\;",
            "find . -exec find . -exec env -C .. rm tests/x \\; \\;",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd), cmd)
        self.assertIsNone(tests_bash("find tests -exec rm tests/x \\;"))
        self.assertIsNone(tests_bash("find . -exec env FOO=1 rm tests/x \\;"))

    def test_find_exec_terminator_then_more_actions(self):
        self.assertIsNotNone(tests_bash("find tests -exec rm tests/x \\; -execdir rm src/x \\;"))
        self.assertBlocked("find . -exec echo \\; -exec rm f \\;", "find -exec")
        self.assertAllowed("find . -exec echo {} \\; -name x")

    # D: coproc NAME { ...; }
    def test_coproc_with_name(self):
        for cmd in ["coproc foo { rm -rf src; }", "coproc foo { cd ..; rm -rf tests/; }",
                    "coproc _x1 { rm -rf src; }"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(bash(cmd), cmd)
                self.assertIsNotNone(tests_bash(cmd), cmd)
        self.assertAllowed("coproc foo { ls; }")
        self.assertAllowed("coproc ls")

    # E: costo de find -exec anidado
    def test_nested_find_exec_is_fast(self):
        cmd = "find . " + "-exec find . " * 30 + "-exec rm -rf src \\;"
        for fn in (lambda: bash(cmd), lambda: tests_bash(cmd.replace("src", "src/a"))):
            t0 = time.time()
            reason = fn()
            self.assertIsNotNone(reason)
            self.assertLess(time.time() - t0, 1.0)
        # caso permitido: antes se duplicaba por nivel (20 niveles ~5 s)
        ok_cmd = "find . " + "-exec find . " * 19 + "-exec echo x \\;"  # 20 niveles: el maximo
        t0 = time.time()
        self.assertIsNone(bash(ok_cmd))
        self.assertLess(time.time() - t0, 1.0)
        t0 = time.time()
        self.assertIsNone(tests_bash(ok_cmd))
        self.assertLess(time.time() - t0, 1.0)

    # F: $'...' con escapes simples
    def test_ansi_c_simple_escapes_allowed(self):
        for cmd in ["grep $'\\t' f", "printf $'%s\\t%s\\n' a b", "echo $'a\\nb'",
                    "echo $'\\a\\b\\e\\E\\f\\r\\v'"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)
        self.assertEqual(agent_guard.parse_commands("echo $'a\\tb\\nc'"),
                         [(["echo", "a\tb\nc"], [])])
        self.assertIsNotNone(bash("echo $'a\\tb' > f"))

    def test_ansi_c_complex_escapes_fail_closed(self):
        for cmd in ["echo $'\\x41'", "echo $'\\101'", "echo $'\\0'", "echo $'\\u0041'",
                    "echo $'\\U00000041'", "echo $'\\cA'", "echo $'\\q'", "echo $'a\\"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "de forma segura")

    # G: sudo -iu root
    def test_sudo_cluster_with_value_letter(self):
        for cmd in ["sudo -iu root rm -rf src", "sudo -Eu root rm -rf src",
                    "doas -nu root rm -rf src", "sudo -iuroot rm -rf src"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'rm'")
        self.assertAllowed("sudo -iu root cat f")
        self.assertIsNone(tests_bash("sudo -iu root rm tests/a"))
        self.assertIsNotNone(tests_bash("sudo -iu root rm src/a"))

    # H: %TEMP% es literal en bash
    def test_percent_temp_is_not_temp(self):
        for cmd in ["mkdir -p %TEMP%/x", "rm %TEMP%/x", "rm %TMP%/x", "touch %temp%/x",
                    "cp a %TEMP%/", "echo x > %TEMP%/a"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, allow_temp=True)
        self.assertFalse(agent_guard._is_temp("%TEMP%/x"))
        self.assertFalse(agent_guard._is_temp("%tmp%/x"))
        for cmd in ["rm $TEMP/x", "rm $TMP/x", "rm ${TEMP}/x", "rm $TMPDIR/x", "rm /tmp/x"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)

    # I: node_modules y .git como ultimo componente
    def test_node_modules_and_dot_git(self):
        for cmd in ["touch node_modules/p/x.test.js", "touch tests/node_modules/p/x.test.js",
                    "touch tests/.git", "rm -rf tests/.git", "touch tests/sub/.GIT"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd), cmd)
        for p in ["node_modules/p/x.test.js", "tests/.git", "C:/proj/tests/.git"]:
            with self.subTest(p=p):
                self.assertFalse(agent_guard.is_test_path(p, "C:/proj"), p)
                self.assertIsNotNone(tests_only("Write", "C:/proj", file_path=p))
        self.assertIsNone(tests_bash("touch tests/.gitkeep"))
        self.assertIsNone(tests_bash("touch tests/a.git"))


class StrictSyntax(unittest.TestCase):
    """Ronda 5: en tests-only + Bash se falla cerrado ante sintaxis que el parser no emula."""

    # payloads reales de los informes: deben bloquearse
    REAL_PAYLOADS = [
        "rm -rf *[_test.]*",
        "echo hola > app.p[y_test.]",
        "X=1 [[ x > src/app.py ]]",
        '"if" [[ x > src/app.py ]]',
        "[[ ( -n x )]]; rm -f src/app.py; [[ x ]]",
        "(( 1 << true\n))\nrm -f src/app.py\ntrue\n# ))",
        "echo $( # ) '\nrm -f src/app.py\n# '\n)",
        "echo `echo \\`rm -f src/app.py\\``",
        'echo "$\\\n(rm app.py)"',
        "cat <<EOF\nbody\nEO\\\nF\nrm app.py\nEOF",
        "function f { rm app.py; }; f",
        "coproc foo { rm -rf src; }",
        "rm -f $tmp/c/proj/src/app.py",
        "rm -f $temp/x",
        "x=; echo ${x:- #} > src/app.py",
        "cat <(true)# > src/app.py",
        "[[ -e <(rm -f src/app.py) ]]; true",
        "trap 'rm -f src/app.py' EXIT; true",
        "X+=1 rm -f src/app.py",
        "a[0]=1 rm -f src/app.py",
        '$"rm" -rf src',
        "echo $'\\x2e\\x2e'",
    ]

    def test_real_payloads_blocked(self):
        for cmd in self.REAL_PAYLOADS:
            with self.subTest(cmd=cmd):
                reason = tests_bash(cmd)
                self.assertIsNotNone(reason, "debio bloquear: %r" % cmd)
                self.assertIn("Bloqueado por agent_guard (tests-only)", reason)

    def test_syntax_rejected_with_message(self):
        for cmd in [r for r in self.REAL_PAYLOADS if not r.startswith(("trap", "X+="))]:
            with self.subTest(cmd=cmd):
                reason = tests_bash(cmd)
                self.assertIn("sintaxis no admitida en tests-only", reason)
                self.assertIn("Simplifica el comando", reason)

    def test_individual_constructs_rejected(self):
        for cmd in [
            "echo $x", "echo ${x}", "echo $(ls)", "echo $((1+2))", "echo $[1+2]", "echo $'a'",
            'echo $"a"', 'echo "$x"', 'echo "$(ls)"', 'echo "a`ls`b"', "echo `ls`", "echo a\\b",
            'echo "a\\b"', "echo a\\\nb", "(ls)", "ls)", "echo ((x", "{ ls; }", "echo {a,b}",
            "echo }", "echo a{}", "echo x{}y", "[[ x ]]", "[[x]]", "echo [abc]", "ls a[b", "ls a]",
            "ls [a]*", "cat <<EOF\nx\nEOF", "cat <<<x", "cat <<-EOF\nx\nEOF", "diff <(ls) f",
            "tee >(cat)", "ls\nls", "ls\r\nls", "ls # comentario", "# solo comentario",
            "ls;#x", "ls &", "ls & ls", "ls |& cat", "ls <& 3", "ls &&& ls", "ls;& ls",
            "ls >>& f",
        ]:
            with self.subTest(cmd=cmd):
                reason = tests_bash(cmd)
                self.assertIsNotNone(reason, "debio bloquear: %r" % cmd)
                self.assertIn("sintaxis no admitida", reason, cmd)
                self.assertIsNotNone(agent_guard._strict_syntax_reason(cmd), cmd)

    def test_allowed_examples(self):
        for cmd in [
            "python -B -m unittest discover -s tests 2>&1 | tail -5", "pytest -q tests/test_a.py",
            "git diff HEAD~1", "git show HEAD~1:src/app.py", "echo x > tests/out.txt",
            "ls tests && cat tests/a.py", 'grep -rn "foo bar" src',
            "find tests -name '*.py' -exec grep -l x {} \\;", "npm test", "cd tests && pytest -q",
            "ls tests || echo no", "ls; ls", "echo a 2>&1", "echo a &> /dev/null",
            "echo a &>> /dev/null", "echo a >& /dev/null", "echo a >&2", "echo a 1>&2",
            "wc -l < tests/a.py", "ls tests/*.py", "ls tests/?.py", "echo 'a$b `c` \\ ( ) { } [[ <<'",
            'echo "a b ( ) { } [[ [ ] # < > & ; |"', "[ -f tests/a.py ] && echo y",
            "test -f x", "echo a#b", "echo 'a'#b", "echo x |tee /dev/null", "ls\t-la",
            "cat 'a'\"b\"", "echo \"it's\"", "echo 'say \"hi\"'", "echo -- -x",
            "echo x >| /dev/null", "git log --format=%h", "echo a,b=c:d@e%f^g~h",
            "echo \"a\nb\"", "echo 'a\nb'",
            "find tests -exec grep -l x {} + ",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(agent_guard._strict_syntax_reason(cmd), cmd)
        for cmd in ["python -B -m unittest discover -s tests 2>&1 | tail -5",
                    "pytest -q tests/test_a.py", "git diff HEAD~1", "git show HEAD~1:src/app.py",
                    "echo x > tests/out.txt", "ls tests && cat tests/a.py",
                    'grep -rn "foo bar" src', "find tests -name '*.py' -exec grep -l x {} \\;",
                    "npm test", "cd tests && pytest -q"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(tests_bash(cmd), "debio permitir: %r" % cmd)

    def test_cd_still_cancels_path_ok(self):
        self.assertIsNotNone(tests_bash("cd src && echo x > tests/a.txt"))
        self.assertIsNone(tests_bash("cd tests && pytest -q"))

    def test_single_quotes_are_literal(self):
        self.assertIsNone(tests_bash("echo '$x `y` $(z) \\ ( ) { } [[ << # & \n'"))
        # la comilla simple no abre dentro de comillas dobles ni al reves
        self.assertIsNone(agent_guard._strict_syntax_reason("echo \"it's\" 'a\"b'"))
        self.assertIsNotNone(agent_guard._strict_syntax_reason("echo \"it's $x\""))
        self.assertIsNotNone(agent_guard._strict_syntax_reason("echo 'a' $x"))

    def test_unterminated_quote_blocked(self):
        for cmd in ["echo 'abc", 'echo "abc']:
            self.assertIsNotNone(tests_bash(cmd))

    def test_trap_forbidden(self):
        for cmd in ["trap 'rm -f src/app.py' EXIT", "trap '' INT", "command trap x EXIT",
                    "builtin trap x EXIT", "ls && trap x EXIT"]:
            with self.subTest(cmd=cmd):
                reason = tests_bash(cmd)
                self.assertIsNotNone(reason)
                self.assertIn("trap", reason)

    def test_assignment_prefix_forms(self):
        for cmd in ["X+=1 rm -f src/app.py", "X+=1 env rm src/app.py"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd))
                self.assertIsNotNone(bash(cmd))
        self.assertIsNotNone(bash("a[0]=1 rm f"))
        self.assertIsNone(tests_bash("X=1 rm tests/a"))

    def test_readonly_not_loosened_or_strict(self):
        # el modo estricto solo aplica a tests-only: readonly sigue aceptando estas formas
        for cmd in ["echo $(date)", "cat <<EOF\nx\nEOF", "echo ${HOME}", "(ls)", "[[ a > b ]]",
                    "ls # c", "echo `date`", "git status\ncat f"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(bash(cmd), cmd)
        self.assertIsNotNone(bash("echo $(rm f)"))

    def test_cli_exit_codes(self):
        def code(cmd):
            p = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                            "cwd": "C:\\proj"})
            return subprocess.run([sys.executable, "-B", SCRIPT, "tests-only"],
                                  input=p.encode("utf-8"), capture_output=True, timeout=30)
        r = code("echo $(date)")
        self.assertEqual(r.returncode, 2)
        self.assertIn("sintaxis no admitida", r.stderr.decode("utf-8"))
        self.assertEqual(code("pytest -q").returncode, 0)

    def test_backslash_message_says_use_slash(self):
        self.assertIn("usa '/'", tests_bash("echo x > C:\\proj\\tests\\a.py"))


class RoundFiveFixes(GuardTestCase):
    # a. path_ok rechaza [ ]
    def test_path_ok_rejects_brackets(self):
        path_ok = agent_guard._make_path_ok("C:/proj")
        for p in ["app.p[y_test.]", "tests/a[1].py", "tests/a]", "[x]"]:
            with self.subTest(p=p):
                self.assertFalse(path_ok(p))
        self.assertTrue(path_ok("tests/a.py"))

    # b. mayusculas en las variables de temp
    def test_temp_variable_case_sensitive(self):
        for p in ["$tmp/x", "$temp/x", "$tmpdir/x", "$Tmp/x", "${tmp}/x", "${temp}/x",
                  "${tmpdir}/x", "$TmpDir/x"]:
            with self.subTest(p=p):
                self.assertFalse(agent_guard._is_temp(p), p)
        for p in ["$TMPDIR/x", "$TEMP/x", "$TMP/x", "${TMPDIR}/x", "${TEMP}/x", "${TMP}/x"]:
            with self.subTest(p=p):
                self.assertTrue(agent_guard._is_temp(p), p)
        self.assertTrue(agent_guard._is_temp("$TMPDIR", allow_dir=True))
        self.assertFalse(agent_guard._is_temp("$tmpdir", allow_dir=True))
        self.assertBlocked("rm -f $tmp/x", allow_temp=True)
        self.assertBlocked("rm -f $temp/x", allow_temp=True)
        self.assertAllowed("rm -f $TEMP/x", allow_temp=True)
        self.assertTrue(agent_guard._is_temp("/TMP/x"))  # los prefijos de ruta siguen sin distinguir

    # c. find -exec ... +
    def test_find_exec_plus_only_after_braces(self):
        # `+` en otro sitio es un argumento: `tee + f` escribe en `+` y en `f`
        self.assertBlocked("find . -exec tee + f \\;", "find -exec")
        self.assertBlocked("find . -exec tee + src/app.py \\;", "find -exec")
        self.assertIsNotNone(tests_bash("find . -exec tee + src/app.py \\;"))
        self.assertBlocked("find . -exec rm + {} \\;", "find -exec")
        # `{} +` termina el -exec
        self.assertBlocked("find . -exec rm {} +", "find -exec")
        self.assertAllowed("find . -exec echo {} + -name x")
        self.assertAllowed("find . -exec echo {} +")

    # d. function NAME {
    def test_function_name_skipped(self):
        self.assertBlocked("function f { rm app.py; }; f", "'rm'")
        self.assertBlocked("function f { rm app.py; }", "'rm'")
        self.assertBlocked("function rm { rm f; }", "'rm'")
        self.assertAllowed("function f { ls; }")
        self.assertAllowed("function rm { ls; }")  # el nombre no es el comando
        self.assertBlocked("function f { rm app.py; }", "'rm'", allow_temp=True)

    # e. tar -c / zip
    def test_tar_create_destination(self):
        for cmd in ["tar -cf src/out.tar src", "tar cf out.tar src", "tar -czf out.tgz src",
                    "tar czf out.tgz src", "tar --create --file out.tar src",
                    "tar --create --file=out.tar src", "tar -rf out.tar a", "tar -uf out.tar a",
                    "tar -Af a.tar b.tar", "tar --append -f a.tar b", "tar --update -f a.tar b",
                    "tar --catenate -f a.tar b.tar", "tar -c -f out.tar a", "tar -cfout.tar a",
                    "tar -cvf out.tar a", "tar cvf out.tar a", "tar --cr --fi out.tar a",
                    "tar -c --file", "tar -cf"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'tar'")
                self.assertBlocked(cmd, "'tar'", allow_temp=True)
        for cmd in ["tar -cf /tmp/out.tar src", "tar cf /tmp/out.tar src", "tar -cf - src",
                    "tar --create --file=/tmp/o.tar src", "tar -cf - src | wc -c"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)
        self.assertBlocked("tar -cf /tmp/o.tar src")  # sin --allow-temp
        self.assertBlocked("tar -cf out.tar src")
        self.assertIsNone(tests_bash("tar -cf tests/out.tar src"))
        self.assertIsNotNone(tests_bash("tar -cf src/out.tar tests"))
        self.assertIsNone(tests_bash("tar -tf tests/out.tar"))

    def test_zip_destination(self):
        for cmd in ["zip out.zip a", "zip -r out.zip src", "zip -q out.zip a", "zip -r -9 out.zip s",
                    "zip -O out.zip in.zip"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'zip'")
                self.assertBlocked(cmd, "'zip'", allow_temp=True)
        self.assertAllowed("zip -r /tmp/out.zip src", allow_temp=True)
        self.assertAllowed("zip -r - src", allow_temp=True)
        self.assertAllowed("zip -O /tmp/o.zip a", allow_temp=True)
        self.assertBlocked("zip -r /tmp/out.zip src")
        self.assertIsNone(tests_bash("zip -r tests/out.zip src"))
        self.assertIsNotNone(tests_bash("zip -r src/out.zip tests"))

    # f. mas mutadores
    def test_more_file_mutators(self):
        for cmd in ["link a b", "mkfifo f", "mknod f p", "mktemp src/x.XXX", "dos2unix f",
                    "unix2dos f", "uniq in out", "uniq -c in out", "uniq -f 1 in out",
                    "history -w", "history -a", "history -aw", "history -w f"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(bash(cmd), cmd)
                self.assertIsNotNone(bash(cmd, allow_temp=True), cmd)
                self.assertIsNotNone(tests_bash(cmd), cmd)
        for cmd in ["uniq", "uniq in", "uniq -c in", "uniq -f 1 in", "uniq in /dev/null",
                    "uniq in -", "history", "history 5", "history -c"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    # g. sed --i y comandos w
    def test_sed_inplace_abbreviations(self):
        for cmd in ["sed --i s/a/b/ f", "sed --in s/a/b/ f", "sed --in-p s/a/b/ f",
                    "sed --i=.bak s/a/b/ f", "sed --in-place=.b s/a/b/ f"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'sed'")
        self.assertAllowed("sed --quiet p f")
        self.assertAllowed("sed --expression=p f")

    def test_sed_write_command(self):
        for cmd in ["sed -n 'w out' f", "sed 's/a/b/w out' f", "sed -n 's/a/b/gpw out' f",
                    "sed -e 'w out' f", "sed -ne 'w out' f", "sed --expression='w out' f",
                    "sed --expression 'w out' f", "sed -n '/x/w out' f", "sed -n '1,3w out' f",
                    "sed -n '$w out' f", "sed 'W out' f", "sed 's/a/b/;w out' f",
                    "sed -n 'p;w out' f", "sed '/a/{w out\n}' f", "sed -n '1!w out' f",
                    "sed -e p -e 'w out' f", "sed -n 'w /tmp/x' f", "sed -n 'w/dev/null2' f",
                    "sed -n 'wout' f", "sed -n 's|a|b|w out' f", "sed -n 'y/a/b/;w out' f"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'sed'")
        for cmd in ["sed -n 'w /dev/stdout' f", "sed -n 'w /dev/stderr' f",
                    "sed 's/a/b/w /dev/stdout' f", "sed -n 1,5p f", "sed 's/w/x/' f",
                    "sed 's/a/w b/' f", "sed -n '/w/p' f", "sed 'y/w/x/' f", "sed -n '/a/,/b/p' f",
                    "sed 's/a/b/g;s/c/d/' f", "sed '$!N;s/\\n/ /' f", "sed -e 's/a/b/' -e 'p' f",
                    "sed '/x/d' f", "sed 'a hello w x' f", "sed 's/a/b/I' f", "sed -E 's/(a)/\\1/' f",
                    "sed 's/a\\/w b/c/' f", "sed -n 'p' w"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    # h. $[ sin cerrar
    def test_old_arith_unterminated_fast(self):
        def run(mode, cmd):
            p = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "C:/proj"})
            r = subprocess.run([sys.executable, "-B", SCRIPT, mode], input=p.encode("utf-8"),
                               capture_output=True, timeout=60)
            return r.returncode
        for cmd in ["$[" * 40000, "rm -f src/app.py\n: " + "$[" * 3000]:
            for mode in ("readonly", "tests-only"):
                with self.subTest(mode=mode, n=len(cmd)):
                    t0 = time.time()  # tiempo en proceso; el subprocess solo da el codigo de salida
                    reason = agent_guard.check(mode, False, {
                        "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "C:/proj"})
                    self.assertLess(time.time() - t0, 1.0)
                    self.assertIsNotNone(reason)
                    self.assertEqual(run(mode, cmd), 2)
        self.assertIn("de forma segura", self.assertBlocked("echo $[1+2"))
        self.assertAllowed("echo $[1+2]")

    # i. find -exec anidado sin terminador
    def test_find_exec_nested_unterminated_fast(self):
        cmd = "find . " + "-exec find " * 9000
        for mode in ("readonly", "tests-only"):
            with self.subTest(mode=mode):
                payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "C:/proj"}
                t0 = time.time()  # tiempo en proceso; el subprocess solo da el codigo de salida
                self.assertIsNotNone(agent_guard.check(mode, False, payload))
                self.assertLess(time.time() - t0, 1.0)
                r = subprocess.run([sys.executable, "-B", SCRIPT, mode],
                                   input=json.dumps(payload).encode("utf-8"),
                                   capture_output=True, timeout=60)
                self.assertEqual(r.returncode, 2)

    def test_find_exec_depth_limit(self):
        deep = "find . " + "-exec find . " * 20 + "-exec echo x \\;"  # 21 niveles
        self.assertBlocked(deep, "de forma segura")
        ok = "find . " + "-exec find . " * 19 + "-exec echo x \\;"  # 20 niveles
        self.assertAllowed(ok)

    # j. pip / python -m / git
    def test_pip_forms(self):
        for cmd in ["python -mpip install x", "python3 -mpip uninstall x", "python -m pip install x",
                    "py -mpip install x", "pip --proxy X install y", "pip --proxy=X install y",
                    "pip --cache-dir c install y", "pip --timeout 5 uninstall y",
                    "pip --log f install y", "pip --retries 2 install y",
                    "python -m pip --proxy X install y", "python -Bmpip install x",
                    "python -B -mpip3 install x"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "pip")
        for cmd in ["python -mpip list", "pip --proxy X list", "pip --proxy install list",
                    "python -mpytest", "python -m pytest -q", "pip --version"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_git_stage_and_attr_source(self):
        self.assertBlocked("git stage .", "'git stage'")
        self.assertBlocked("git --attr-source X commit", "'git commit'")
        self.assertBlocked("git --attr-source X add f", "'git add'")
        self.assertAllowed("git --attr-source X log")
        self.assertAllowed("git --attr-source=X log")
        self.assertBlocked("git --attr-source=X commit", "'git commit'")

    # k. mensaje para rutas de Windows
    def test_drive_path_hint(self):
        for cmd in ["rm C:\\Users\\u\\AppData\\Local\\Temp\\x", "echo x > C:\\proj\\tests\\x.py",
                    "cp a C:\\proj\\tests\\x.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "usa '/'", allow_temp=True)


class RoundSixFixes(GuardTestCase):
    """Ronda 6 (la ultima): defectos verificados por auditor y shield contra bash real."""

    def both_block(self, cmds, allow_temp=False):
        for cmd in cmds:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(bash(cmd, allow_temp), "readonly debio bloquear: %r" % cmd)
                self.assertIsNotNone(tests_bash(cmd), "tests-only debio bloquear: %r" % cmd)

    def both_allow(self, cmds, allow_temp=False):
        for cmd in cmds:
            with self.subTest(cmd=cmd):
                self.assertIsNone(bash(cmd, allow_temp), "readonly debio permitir: %r" % cmd)
                self.assertIsNone(tests_bash(cmd), "tests-only debio permitir: %r" % cmd)

    # 1. globs `.?` / `.*` que pueden coincidir con `..`
    def test_dot_globs_blocked(self):
        for cmd in ["cp tests/evil.py tests/.?/src/app.py", "echo PWNED > tests/.*/src/app.py",
                    "rm -rf tests/.?/src",
                    "cp tests/x.py /c/Users/u/AppData/Local/Temp/.?/.?/.?/.?/.?/NotionGroup/x",
                    "rm tests/.*", "touch tests/.?x/a"]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd))
        self.assertIsNotNone(bash("cp a /tmp/.?/x", allow_temp=True))
        self.assertIsNotNone(bash("rm /tmp/.*/x", allow_temp=True))
        self.assertIsNotNone(bash("cp a /tmp/a/.?/x", allow_temp=True))
        self.assertFalse(agent_guard._is_temp("/tmp/.?/x"))
        self.assertFalse(agent_guard._make_path_ok("C:/proj")("tests/.?/a"))

    def test_plain_globs_still_allowed(self):
        for cmd in ["rm tests/tmp_*.json", "rm tests/*.pyc", "rm -r tests/__pycache__",
                    "echo x > tests/a?.txt", "touch tests/.gitkeep"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(tests_bash(cmd))
        self.assertIsNone(bash("rm /tmp/a_*.txt", allow_temp=True))

    # 2. .claude y companeros; fuera de cwd solo temporal en Write/Edit
    def test_non_test_dirs_extended(self):
        for d in (".claude", ".husky", ".vscode", ".idea"):
            for p in ("%s/rules/evil.test.md" % d, "C:/proj/%s/rules/evil.test.md" % d,
                      "tests/%s/x.test.md" % d):
                with self.subTest(path=p):
                    self.assertIsNotNone(tests_only("Write", "C:/proj", file_path=p))
                    self.assertFalse(agent_guard.is_test_path(p, "C:/proj"))
            cmd = "cp tests/evil.md %s/rules/evil.test.md" % d
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(tests_bash(cmd))

    def test_write_outside_cwd_blocked(self):
        for p in ["C:/Users/u/.claude/rules/evil.test.md", "C:/Users/u/.claude/agents/evil.test.md",
                  "C:/Users/u/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/"
                  "x.test.bat",
                  "C:/proj/.claude/rules/evil.test.md", "C:/other/tests/a.py",
                  "/home/u/.claude/rules/evil.test.md"]:
            for cwd in ("C:/proj", None):
                for tool, key in (("Write", "file_path"), ("Edit", "file_path"),
                                  ("NotebookEdit", "notebook_path")):
                    with self.subTest(path=p, cwd=cwd, tool=tool):
                        self.assertIsNotNone(tests_only(tool, cwd, **{key: p}))

    def test_write_temp_outside_cwd_allowed(self):
        for p in ["/tmp/a_test.py", "C:/Users/u/AppData/Local/Temp/x.test.py",
                  "C:\\Users\\u\\AppData\\Local\\Temp\\x.test.py",
                  "/c/Users/u/AppData/Local/Temp/x_test.py"]:
            for cwd in ("C:/proj", None):
                with self.subTest(path=p, cwd=cwd):
                    self.assertIsNone(tests_only("Write", cwd, file_path=p))
        self.assertIsNotNone(tests_only("Write", "C:/proj", file_path="/tmp/.claude/x_test.py"))
        self.assertIsNone(tests_only("Write", "C:/proj", file_path="C:/proj/tests/a.py"))
        self.assertIsNone(tests_only("Write", "C:/proj", file_path="tests/a.py"))

    # 3. nombres 8.3 con `~`
    def test_tilde_segment_rejected(self):
        for p in ["GITHUB~1/workflows/short_test.yml", "src/GITHUB~1/x_test.yml",
                  "tests/a~1.py", "C:/proj/GITHUB~1/workflows/short_test.yml"]:
            with self.subTest(path=p):
                self.assertFalse(agent_guard.is_test_path(p, "C:/proj"))
                self.assertIsNotNone(tests_only("Write", "C:/proj", file_path=p))
        self.assertTrue(agent_guard.is_test_path("C:/Users/RRIVER~1/proj/tests/a.py",
                                                 "C:/Users/RRIVER~1/proj"))

    # 4. ejecutores sin `$`
    def test_forbidden_commands_tests_only(self):
        for cmd in ["hash -p /bin/rm git", "hash git", "enable -f x.so y", "flock f rm src/c.py",
                    "watch rm src/c.py", "strace rm src/c.py", "ltrace rm src/c.py",
                    "ssh-agent rm src/c.py", "chroot / rm src/c.py",
                    "env chroot / rm src/c.py", "find tests -exec chroot / rm x \\;",
                    "find tests -exec enable -f x y \\;"]:
            with self.subTest(cmd=cmd):
                reason = tests_bash(cmd)
                self.assertIsNotNone(reason)
                self.assertIn("(tests-only)", reason)

    def test_wrappers_readonly(self):
        for cmd in ["hash -p /bin/rm git", "flock f rm src/c.py", "watch rm src/c.py",
                    "strace rm src/c.py", "ltrace rm src/c.py", "ssh-agent rm src/c.py",
                    "find . -exec flock f rm x \\;", "hash -ip /bin/rm git"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)
                self.assertBlocked(cmd, allow_temp=True)
        self.assertAllowed("hash")
        self.assertAllowed("hash -r")
        self.assertAllowed("hash git")

    def test_dangerous_assignments_tests_only(self):
        for cmd in ["GIT_EXTERNAL_DIFF=rm git diff", "GIT_PAGER=x git log", "PAGER=x git log",
                    "LESSOPEN=x less f", "LESSCLOSE=x less f", "TAPE=x tar -tf a", "PATH=/x ls",
                    "BASH_ENV=x ls", "ENV=x ls", "LD_PRELOAD=x ls", "GIT_EDITOR=x git log",
                    "EDITOR=x git log", "MY_VISUAL=x ls", "FOO=1 GIT_X=2 ls",
                    "env GIT_PAGER=x git log", "sudo PAGER=x ls", "PATH+=x ls",
                    "find tests -exec env PAGER=x ls \\;"]:
            with self.subTest(cmd=cmd):
                reason = tests_bash(cmd)
                self.assertIsNotNone(reason)
                self.assertIn("(tests-only)", reason)
        for cmd in ["FOO=1 pytest -q", "PYTHONPATH=src pytest", "env FOO=1 pytest",
                    "echo PATH=x", "CI=1 npm test"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(tests_bash(cmd))

    def test_git_dash_c_blocked(self):
        for cmd in ["git -c alias.z='!rm src/c.py' z", "git -c core.fsmonitor=x status",
                    "git -c diff.external=x diff", "git --config-env=a=B log",
                    "git --config-env a=B log", "git -c core.pager=cat log",
                    "git -C repo -c a=b log", "git difftool", "git grep -O foo",
                    "git grep --open-files-in-pager=x foo", "git grep -nOless foo",
                    "git grep --open-files-in-pager foo"]:
            self.both_block([cmd])
            self.assertIsNotNone(bash(cmd, allow_temp=True))
        self.both_allow(["git grep -n foo", "git grep -e O", "git grep -n -- -O",
                         "git -C repo log", "git --no-pager diff"])

    def test_sed_exec(self):
        for cmd in ["sed 'e rm src/b.py' f", "sed 's/a/b/e' f", "sed -e 'e' f",
                    "sed 's/a/b/ge' f", "sed '1e id' f", "sed -n 'p;e date' f",
                    "sed --expression='s/a/b/e' f", "sed '/x/{e date\n}' f"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'sed'")
                self.assertBlocked(cmd, "'sed'", allow_temp=True)
        for cmd in ["sed 's/e/x/' f", "sed 's/a/e/' f", "sed -n '/e/p' f", "sed 'y/e/x/' f",
                    "sed 'a e x' f", "sed 's/a/b/gp' f", "sed 's/a/b/;p' f", "sed '/x/d' f",
                    "sed 's/a/b/I' f", "sed -n 'p' e"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    # 5. tar estilo antiguo y --delete
    def test_tar_old_style_and_delete(self):
        for cmd in ["tar fx a.tar", "tar fxv a.tar", "tar vfx a.tar", "tar --delete -f src/a.tar m",
                    "tar --del -f src/a.tar m", "tar -f src/a.tar --delete m",
                    "tar --delete --file=src/a.tar m", "tar --dele -f a.tar m"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'tar'", allow_temp=True)
                self.assertIsNotNone(tests_bash(cmd))
        self.assertIsNone(tests_bash("tar --delete -f tests/a.tar m"))
        self.assertAllowed("tar --delete -f /tmp/a.tar m", allow_temp=True)
        self.assertBlocked("tar --delete -f /tmp/a.tar m")
        for cmd in ["tar tf a.tar", "tar tvf a.tar", "tar ft a.tar", "tar -tvf a.tar"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    # 6. destino numerico pegado a otra redireccion
    def test_numeric_redirect_target(self):
        for cmd in ["echo PWN >'2'<tests/a", "echo PWN >2<tests/a", "echo x > 2>/dev/null",
                    "echo x &> \\2>&1", "echo x >\\2", "echo x >\"2\""]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)
        self.assertIn(("&>", "2"), agent_guard.parse_commands("echo x &> \\2>&1")[0][1])
        self.assertIn((">", "2"), agent_guard.parse_commands("echo PWN >'2'<tests/a")[0][1])
        for cmd in ["cmd 2>&1", "cmd 2>/dev/null", "cmd >&2", "cmd 1>&2", "wc -l 0<f",
                    "cmd 2>&1 >/dev/null", "cmd >/dev/null 2>&1"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    # 7. escritores no cubiertos
    def test_more_writers_blocked(self):
        self.both_block([
            "awk -i inplace '{print}' f", "gawk -i inplace 1 f", "gawk -iinplace 1 f",
            "gawk --include=inplace 1 f", "gawk --include inplace 1 f",
            "ruby -i -pe 1 f", "ruby -pi.bak -e 1 f", "xxd -r in out", "xxd -r -p in out",
            "certutil -decode a b", "certutil -encode a b", "certutil -f -urlcache x y",
            "certutil /decode a b", "git merge-file a b c", "git merge-file -p a b c",
            "split f", "split f pre", "split -l 10 f", "csplit f 2", "csplit -f pre f 2",
            "cpio -i", "cpio -o", "ar x a.a", "ar xv a.a", "ar -x a.a", "zstd f",
            "zstd -d f.zst", "lz4 f", "ex f", "ed f", "vim -es f", "vi -s x f", "vim -Es f",
            "openssl enc -aes256 -in a -out src/b", "split --filter='rm x' f /tmp/p",
        ], allow_temp=True)
        self.assertBlocked("split f /tmp/p")  # sin --allow-temp

    def test_more_writers_allowed(self):
        self.both_allow([
            "awk '{print}' f", "gawk 1 f", "ruby -e 'puts 1'", "ruby -ne print f", "xxd f",
            "xxd -r f", "xxd -r f -", "xxd -r f /dev/null", "certutil -hashfile f SHA256",
            "split f /tmp/p", "split -l 10 f /tmp/p", "csplit -f /tmp/p f 2",
            "csplit --prefix=/tmp/p f 2", "zstd -c f", "zstd --stdout f", "zstd -dc f",
            "zstd -t f", "lz4 -c f", "vim f", "vi f", "git merge-base a b",
            "openssl enc -in a -out /tmp/b", "openssl enc -in a -out /dev/null",
            "openssl x509 -in a", "ar t a.a", "ar tv a.a",
        ], allow_temp=True)
        self.assertIsNone(tests_bash("openssl enc -in a -out tests/b"))
        self.assertIsNone(tests_bash("split f tests/p"))

    # 8. marcador de AppData\Local\Temp solo al inicio y bajo Users
    def test_appdata_temp_anchored(self):
        for p in ["src/AppData/Local/Temp/evil.py", "C:/proj/AppData/Local/Temp/x",
                  "/home/u/AppData/Local/Temp/x", "C:/Users/AppData/Local/Temp/x",
                  "C:/Users/u/x/AppData/Local/Temp/x", "C:/Users/u/AppData/Local/Temp"]:
            with self.subTest(path=p):
                self.assertFalse(agent_guard._is_temp(p), p)
        for p in ["C:/Users/u/AppData/Local/Temp/x", "/c/Users/u/AppData/Local/Temp/x",
                  "/mnt/c/Users/u/AppData/Local/Temp/x", "c:/users/U/appdata/local/temp/x",
                  "C:/Users/RRIVER~1/AppData/Local/Temp/a/b"]:
            with self.subTest(path=p):
                self.assertTrue(agent_guard._is_temp(p), p)
        self.assertTrue(agent_guard._is_temp("C:/Users/u/AppData/Local/Temp", allow_dir=True))
        self.assertFalse(agent_guard._is_temp("src/AppData/Local/Temp", allow_dir=True))
        self.assertIsNotNone(tests_bash("cp tests/evil.py src/AppData/Local/Temp/evil.py"))
        self.assertIsNotNone(bash("cp a src/AppData/Local/Temp/x", allow_temp=True))

    # 10. NUL y caracteres de control
    def test_control_chars_strict(self):
        for cmd in ["r\x00m src/app.py", "echo \x01 > tests/a", "echo '\x1f' > tests/a",
                    "echo x\x0b> src/a", "rm\x0csrc/app.py", "echo x > tests/a\x00"]:
            with self.subTest(cmd=cmd):
                reason = tests_bash(cmd)
                self.assertIsNotNone(reason)
                self.assertIn("(tests-only)", reason)
        self.assertIsNone(tests_bash("echo\tx > tests/a"))

    # 11. falsos positivos en readonly
    def test_mktemp(self):
        for cmd in ["mktemp", "mktemp -d", "mktemp /tmp/x.XXXX", "mktemp -d /tmp/x.XXXX",
                    "mktemp -p /tmp", "mktemp -p /tmp x.XXXX", "mktemp -t x.XXXX",
                    "mktemp --tmpdir", "mktemp --tmpdir x.XXXX", "mktemp -u",
                    "mktemp -d -t x.XXXX", "mktemp --suffix=.txt", "mktemp -dp /tmp"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)
                self.assertIsNone(tests_bash(cmd))
        for cmd in ["mktemp src/x.XXX", "mktemp -p src x.XXX", "mktemp -d src", "mktemp x.XXX",
                    "mktemp --tmpdir=src x", "mktemp -p /tmp ../x", "mktemp -p /tmp /etc/x",
                    "mktemp -p /tmp/.?/x"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, "'mktemp'", allow_temp=True)
        self.assertBlocked("mktemp", "'mktemp'")  # sin --allow-temp sigue bloqueado
        self.assertIsNone(tests_bash("mktemp tests/x.XXX"))
        self.assertIsNotNone(tests_bash("mktemp src/x.XXX"))

    def test_tar_stdout_and_temp_dir(self):
        for cmd in ["tar -xOf a.tar f", "tar -xf a.tar -O f", "tar --to-stdout -xf a.tar f",
                    "tar xOf a.tar f", "tar -xzOf a.tgz f", "tar -xOf a.tar f -C /tmp"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)
        for cmd in ["tar -tf a.tar -C /tmp", "tar -C /tmp -tf a.tar", "tar --directory=/tmp -tf a",
                    "tar -tf a.tar -C /tmp/x"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)
        for cmd in ["tar -xf a.tar", "tar -xf a.tar -C /tmp", "tar -tf a.tar -C src",
                    "tar -xOf a.tar -C src f", "tar -tf a.tar -C /tmp/../src",
                    "tar --to-command=rm -xf a.tar"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, allow_temp=True)
        self.assertBlocked("tar -tf a.tar -C /tmp")  # sin --allow-temp
        self.assertIsNone(tests_bash("tar -xOf tests/a.tar f"))


if __name__ == "__main__":
    unittest.main()
