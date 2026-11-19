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
            "git -C repo log", "git --no-pager diff", "git -c core.pager=cat log",
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
            "rm $TMP/x", "rm %TEMP%\\x", "rm %TMP%\\x", "rm /tmp/a /tmp/b",
            "rm C:\\Users\\u\\AppData\\Local\\Temp\\x", "rm 'C:\\Users\\u\\AppData\\Local\\Temp\\x'",
            "touch /c/Users/u/AppData/Local/Temp/x", "echo hi > /dev/null",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.t(cmd), cmd)

    def test_env_prefixes(self):
        with mock.patch.dict(os.environ, {"TMPDIR": "/scratch/work", "TEMP": "D:\\Tmp"}):
            self.assertIsNone(self.t("rm /scratch/work/x"))
            self.assertIsNone(self.t("rm D:\\Tmp\\x"))
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
        self.assertIsNone(agent_guard.check(
            "tests-only", False, {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}))
        self.assertIsNone(agent_guard.check("tests-only", False, {"tool_name": "Read"}))

    def test_message_names_path(self):
        self.assertIn("src/app.py", tests_only("Write", file_path="src/app.py"))


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
                    "mv /tmp/a /tmp", "cp a $TMPDIR", "cp a $TMPDIR/", "cp a %TEMP%\\",
                    "cp a /var/tmp/", "cp a C:\\Users\\u\\AppData\\Local\\Temp\\",
                    "cp a C:\\Users\\u\\AppData\\Local\\Temp"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd, allow_temp=True)
        for cmd in ["cp a /tmpx/", "cp a /tmp/../", "cp a /home/", "mv a /tmp/", "mv /tmp/ /tmp/b",
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

    def test_outside_cwd_or_no_cwd_uses_basename_only(self):
        self.blocked("/other/tests/a.py", "/home/u/proj")
        self.blocked("/other/tests/a.py", None)
        self.blocked("/other/tests/a.py", "")
        self.blocked("/other/tests/a.py", "   ")
        self.blocked("/home/u/projx/tests/a.py", "/home/u/proj")  # prefijo parcial no es hijo
        self.allowed("/other/src/test_a.py", "/home/u/proj")
        self.allowed("/other/src/test_a.py", None)
        self.allowed("C:\\x\\src\\b.spec.ts", None)
        self.blocked("C:\\x\\tests\\b.ts", None)

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
        r, elapsed = self.run_cli("rm -rf x\n" + "(" * 20000)
        self.assertEqual(r.returncode, 2)
        self.assertIn("'rm'", r.stderr.decode("utf-8"))
        self.assertLess(elapsed, 2.0)

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


if __name__ == "__main__":
    unittest.main()
