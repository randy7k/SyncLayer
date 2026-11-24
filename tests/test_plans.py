"""Pruebas de la carpeta de planes (Fase 5, T1): constantes de install.ps1, inventario de los textos del
repositorio y referencia independiente (plans_ref.py). Casos del plan: 1 (constantes), 2 (inventario),
3 (zonas sensibles), 4 (validacion L1 a L5), 5 (limite izquierdo), 6 (una sola pasada), 7 (repositorio real),
8 (orden con alias y nivel), 9 (nombres de dispositivo) y 31 (install.ps1 sigue limpio). Sin PowerShell: solo
biblioteca estandar.
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aliases_ref as ar  # noqa: E402
import levels_ref as lr  # noqa: E402
import plans_ref as pr  # noqa: E402

NINE = {"atlas": "mapa", "auditor": "revisor", "debugger": "cazador", "forge": "dev", "oracle": "guia",
        "scout": "explorador", "scribe": "redactor", "sentinel": "amigo-qa", "shield": "guardia"}
THREE_FILES = ["agents/atlas.md", "docs/agentes.md", "rules/agentes.md"]


def repo_files():
    return {rel: pr.repo_bytes(rel) for rel in pr.managed_paths()}


def text_paths():
    return ar.text_files()


class Constants(unittest.TestCase):
    """Caso 1."""

    def test_case1_constants_match_the_reference(self):
        default, pattern, max_length = pr.script_constants()
        self.assertEqual(default, pr.DEFAULT)
        self.assertEqual(default, "docs/plans")
        self.assertEqual(pattern, pr.PATTERN_PS)
        self.assertEqual(max_length, pr.MAX_LENGTH)
        self.assertEqual(max_length, 64)

    def test_case1_default_passes_its_own_validation(self):
        default, pattern, max_length = pr.script_constants()
        self.assertIsNone(pr.validate_plans_dir(default))
        self.assertLessEqual(len(default), max_length)
        # \z de .NET es \Z en Python: el patron del script acepta la carpeta por defecto.
        self.assertTrue(re.match(pattern.replace(r"\z", r"\Z"), default))

    def test_case1_each_constant_is_assigned_once_in_one_line(self):
        text = lr.script_text()
        for name in ("PlansDirDefault", "PlansDirPattern", "PlansDirMaxLength"):
            self.assertEqual(len(re.findall(r"^\$" + name + r"\b", text, re.M)), 1, name)

    def test_case1_the_script_pattern_agrees_with_the_reference_on_samples(self):
        _, pattern, _ = pr.script_constants()
        rx = re.compile(pattern.replace(r"\z", r"\Z"))
        samples = ["planes", "docs/planes", "a/b/c/d", "a/b/c/d/e", "..", "docs/../x", "/docs", "docs/", "docs//x",
                   "Docs", "docs/plans.v2", "docs plans", "a" * 32, "a" * 33, "docs\n", "docs\nx", "doc\u00f1s", ""]
        for value in samples:
            with self.subTest(value=value):
                shape_ok = pr.validate_plans_dir(value) in (None, pr.MSG_DEVICE, pr.MSG_ROLE) and len(value) <= 64
                self.assertEqual(bool(rx.match(value)) and len(value) <= 64, shape_ok)

    def test_reader_handles_crlf(self):
        crlf = lr.script_text().replace("\n", "\r\n")
        self.assertEqual(pr.script_constants(crlf), pr.script_constants())

    def test_reader_fails_when_a_constant_is_missing_or_repeated(self):
        text = lr.script_text()
        gone = text.replace("$PlansDirMaxLength = 64", "$Otra = 64")
        with self.assertRaises(ValueError):
            pr.script_constants(gone)
        twice = text + "\n$PlansDirDefault = 'docs/plans'\n"
        with self.assertRaises(ValueError):
            pr.script_constants(twice)


class Inventory(unittest.TestCase):
    """Casos 2 y 3 sobre el repositorio real y sobre copias en memoria."""

    def test_case2_inventory_of_the_repository(self):
        files = repo_files()
        self.assertEqual(len(files), 12)
        self.assertEqual(pr.inventory_problems(files), [])
        for rel in THREE_FILES:
            self.assertEqual(files[rel].decode("iso-8859-1").count("docs/plans"), 1, rel)
            self.assertIn(b"`docs/plans/", files[rel], rel)
        self.assertNotIn(b"docs/plans", files["hooks/agent_guard.py"])

    def test_case2_a_fourth_occurrence_fails_the_inventory(self):
        for rel in sorted(repo_files()):
            with self.subTest(file=rel):
                files = repo_files()
                files[rel] = files[rel] + b"\nOtra: `docs/plans/x.md`\n"
                self.assertNotEqual(pr.inventory_problems(files), [])

    def test_case2_an_occurrence_in_the_frontmatter_or_the_hook_fails(self):
        files = repo_files()
        files["agents/forge.md"] = files["agents/forge.md"].replace(b"description: ", b"description: `docs/plans/` ", 1)
        problems = pr.inventory_problems(files)
        self.assertTrue(any("frontmatter" in p for p in problems), problems)
        files = repo_files()
        files["hooks/agent_guard.py"] += b"\n# docs/plans/\n"
        self.assertTrue(any("hook" in p for p in pr.inventory_problems(files)))

    def test_case2_an_agent_without_a_closing_fence_is_reported_not_raised(self):
        files = repo_files()
        files["agents/forge.md"] = b"---\nname: forge\ndescription: x\nUsa `docs/plans/`\n"
        problems = pr.inventory_problems(files)
        self.assertTrue(any("sin cierre" in p for p in problems), problems)

    def test_case2_a_non_replaceable_occurrence_fails(self):
        files = repo_files()
        files["rules/agentes.md"] = files["rules/agentes.md"].replace(b"`docs/plans/", b"`mydocs/plans/", 1)
        self.assertTrue(any("reemplazable" in p for p in pr.inventory_problems(files)))

    def test_case2_no_other_segment_before_plans_in_the_managed_texts(self):
        files = {rel: pr.repo_bytes(rel) for rel in text_paths()}
        self.assertEqual(len(files), 11)
        self.assertEqual(pr.segment_problems(files), [])

    def test_case2_a_forge_plans_form_fails_the_segment_check(self):
        for extra in (b"\nVer forge/plans/x.md\n", b"\nmydocs/plans/x\n", b"\n`x-y_1/plans/`\n"):
            with self.subTest(extra=extra):
                files = {rel: pr.repo_bytes(rel) for rel in text_paths()}
                files["rules/agentes.md"] += extra
                self.assertNotEqual(pr.segment_problems(files), [])

    def test_case3_no_occurrence_in_sensitive_zones(self):
        self.assertEqual(pr.zone_problems(repo_files()), [])

    def test_case3_a_fenced_block_a_link_and_a_url_are_detected(self):
        base = repo_files()
        for label, extra in (("bloque", b"\n```\ndocs/plans/x\n```\n"),
                             ("bloque con tildes", b"\n~~~\ndocs/plans/x\n~~~\n"),
                             ("enlace", b"\n[x](docs/plans/x.md)\n"),
                             ("referencia", b"\n[x]: docs/plans/x.md\n"),
                             ("url", b"\nhttps://example.com/docs/plans/x\n")):
            with self.subTest(zone=label):
                files = dict(base)
                files["rules/agentes.md"] = files["rules/agentes.md"] + extra
                self.assertNotEqual(pr.zone_problems(files), [])


class Validation(unittest.TestCase):
    """Caso 4: cada regla L1 a L5 con un caso que pasa y uno que falla."""

    VALID = ["planes", "docs/planes", "a/b/c/d", "forge_x", "forges", "a" * 32, "/".join(["a" * 15] * 4),
             "docs/plans", "0", "a-b_c", "x" + "/y" * 3, "con1x", "xlpt1", "comm", "scouts"]
    INVALID = ["a/b/c/d/e", "..", "docs/../x", "/docs", "docs/", "docs//x", "Docs", "docs/plans.v2", "docs plans",
               "a" * 65, "/".join(["a" * 32, "b" * 32]), "a" * 33, "nul", "docs/com1", "docs/forge", "atlas-planes",
               "", ".", "-a", "_a", "docs\\planes", "c:", "docs/pl`ans", "docs/pl'ans", "docs\nx", "docs\n",
               "doc\u00f1s", "docs/planes ", " docs", "docs/", "a/b/c/d/", "docs/Planes", "DOCS"]

    def test_case4_valid_values(self):
        for value in self.VALID:
            with self.subTest(value=value):
                self.assertIsNone(pr.validate_plans_dir(value))

    def test_case4_invalid_values(self):
        for value in self.INVALID:
            with self.subTest(value=value):
                self.assertIsNotNone(pr.validate_plans_dir(value))

    def test_case4_each_rule_gives_its_own_reason(self):
        self.assertEqual(pr.validate_plans_dir(None), pr.MSG_TYPE)           # L1
        self.assertEqual(pr.validate_plans_dir(["docs"]), pr.MSG_TYPE)
        self.assertEqual(pr.validate_plans_dir(1), pr.MSG_TYPE)
        self.assertEqual(pr.validate_plans_dir(True), pr.MSG_TYPE)
        self.assertEqual(pr.validate_plans_dir({}), pr.MSG_TYPE)
        self.assertEqual(pr.validate_plans_dir("Docs"), pr.MSG_SHAPE)        # L2
        self.assertEqual(pr.validate_plans_dir("a/b/c/d/e"), pr.MSG_SHAPE)
        self.assertEqual(pr.validate_plans_dir("a" * 33), pr.MSG_SHAPE)
        self.assertEqual(pr.validate_plans_dir("/".join(["a" * 20] * 4)), pr.MSG_SHAPE)  # L3: 83 caracteres
        self.assertEqual(pr.validate_plans_dir("docs/com1"), pr.MSG_DEVICE)  # L4
        self.assertEqual(pr.validate_plans_dir("nul"), pr.MSG_DEVICE)
        self.assertEqual(pr.validate_plans_dir("docs/forge"), pr.MSG_ROLE)   # L5
        self.assertEqual(pr.validate_plans_dir("atlas-planes"), pr.MSG_ROLE)

    def test_case4_length_limit_is_64_in_total(self):
        ok = "/".join(["a" * 15] * 4)  # 63
        self.assertEqual(len(ok), 63)
        self.assertIsNone(pr.validate_plans_dir(ok))
        self.assertIsNone(pr.validate_plans_dir("/".join(["a" * 16] + ["a" * 15] * 3)))  # 64
        self.assertEqual(pr.validate_plans_dir("/".join(["a" * 16] * 3 + ["a" * 17])), pr.MSG_SHAPE)  # 68

    def test_case4_messages_never_contain_the_value(self):
        # Prueba debil a proposito: los mensajes son constantes. La version util (el exit 1 del instalador no
        # imprime el valor) es el caso 12 de T2.
        for value in self.INVALID + [None, 1, [], {}]:
            problem = pr.validate_plans_dir(value)
            if isinstance(value, str) and value:
                self.assertNotIn(value, problem or "")

    def test_case4_messages_are_ascii_without_accents(self):
        for msg in (pr.MSG_TYPE, pr.MSG_SHAPE, pr.MSG_DEVICE, pr.MSG_ROLE):
            msg.encode("ascii")

    def test_case4_every_role_is_rejected_as_a_whole_segment_or_a_hyphen_piece(self):
        for role in ar.roles():
            for value in (role, "docs/" + role, role + "-x", "x-" + role, "x-" + role + "-y"):
                with self.subTest(value=value):
                    self.assertEqual(pr.validate_plans_dir(value), pr.MSG_ROLE)
            for value in (role + "s", role + "_x", "x" + role, role[:-1]):
                with self.subTest(value=value):
                    self.assertIsNone(pr.validate_plans_dir(value))


class LeftBoundary(unittest.TestCase):
    """Caso 5."""

    def run_text(self, text, folder="docs/planes"):
        return pr.transform_text(text.encode("ascii"), folder).decode("ascii")

    def test_case5_matches_are_replaced(self):
        for src, want in (("`docs/plans/x`", "`docs/planes/x`"), ("(docs/plans/x", "(docs/planes/x"),
                          ("docs/plans/x", "docs/planes/x"), (" docs/plans/x", " docs/planes/x"),
                          ("\ndocs/plans/x", "\ndocs/planes/x"), ('"docs/plans/x', '"docs/planes/x'),
                          (">docs/plans/x", ">docs/planes/x"), (":docs/plans/x", ":docs/planes/x"),
                          ("a docs/plans/ y docs/plans/", "a docs/planes/ y docs/planes/")):
            with self.subTest(src=src):
                self.assertEqual(self.run_text(src), want)

    def test_case5_non_matches_are_untouched(self):
        for src in ("mydocs/plans/", "x/docs/plans/", ".docs/plans/", "-docs/plans/", "docs/plans", "_docs/plans/",
                    "9docs/plans/", "Adocs/plans/", "zdocs/plans/", "docs/plans-x/", "docs/planss/", "Docs/plans/",
                    "docs/Plans/"):
            with self.subTest(src=src):
                self.assertEqual(self.run_text(src), src)

    def test_case5_the_expression_has_no_ignorecase_and_a_fixed_width_lookbehind(self):
        with open(pr.__file__, "rb") as f:
            body = f.read().decode("utf-8").split('"""', 2)[2]
        self.assertNotIn("IGNORECASE", body)
        self.assertIsNone(re.search(r"\bre\.I\b", body))
        self.assertEqual(re.findall(r"\(\?<!?[^)]*\)", pr._MATCH_RE.pattern), ["(?<![A-Za-z0-9_./-])"])
        self.assertEqual(pr._MATCH_RE.flags & re.IGNORECASE, 0)


class SinglePass(unittest.TestCase):
    """Caso 6."""

    def test_case6_replacements_are_not_scanned_again(self):
        src = b"`docs/plans/a` y `docs/plans/b`\n"
        for folder in ("docs/plans-v2", "x/docs/plans", "docs/plans2", "plans"):
            with self.subTest(folder=folder):
                once = pr.transform_text(src, folder)
                self.assertEqual(once, src.replace(b"docs/plans/", folder.encode() + b"/"))
                # Reaplicar la misma carpeta no vuelve a reemplazar nada: el literal viejo ya no esta con limite.
                self.assertEqual(pr.transform_text(once, folder), once)

    def test_case6_the_self_check_passes_and_counts_replacements(self):
        text = "x\n`docs/plans/a`\nmydocs/plans/\n`docs/plans/b`\n"
        out = pr.transform_text(text.encode(), "x/docs/plans").decode()
        self.assertEqual(out.count("x/docs/plans/"), 2)
        self.assertIn("mydocs/plans/", out)

    def test_case6_the_self_check_detects_a_corrupted_result(self):
        src = "`docs/plans/a`\n"
        with self.assertRaises(ValueError):
            pr._check(src, "`docs/planes/a`\n`extra`\n", "docs/planes")
        with self.assertRaises(ValueError):
            pr._check(src, "`docs/planes/b`\n", "docs/planes")
        with self.assertRaises(ValueError):
            pr._check(src, "`docs/plans/a`\n", "docs/planes")

    def test_case6_invalid_folder_raises_without_the_value(self):
        with self.assertRaises(ValueError) as cm:
            pr.transform_text(b"`docs/plans/a`", "Docs/X")
        self.assertNotIn("Docs/X", str(cm.exception))

    def test_default_or_absent_folder_gives_the_canonical_bytes(self):
        src = b"`docs/plans/a`\r\nx\r\n"
        self.assertEqual(pr.transform_text(src, None), b"`docs/plans/a`\nx\n")
        self.assertEqual(pr.transform_text(src, "docs/plans"), b"`docs/plans/a`\nx\n")

    def test_agent_rules(self):
        body = b"---\nname: x\ndescription: d\n---\nUsa `docs/plans/a.md`.\n"
        self.assertEqual(pr.transform_agent(body, "planes"), body.replace(b"docs/plans/", b"planes/"))
        for bad in (b"---\nname: x\ndescription: usa docs/plans/\n---\ncuerpo\n",
                    b"name: x\n---\ncuerpo docs/plans/\n", b"---\nname: x\ncuerpo docs/plans/\n"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    pr.transform_agent(bad, "planes")
        # Un agente sin cuerpo y sin LF final.
        self.assertEqual(pr.transform_agent(b"---\nname: x\n---", "planes"), b"---\nname: x\n---")


class RealRepository(unittest.TestCase):
    """Caso 7."""

    def test_case7_three_lines_in_three_files_change(self):
        files = repo_files()
        changed = []
        for rel in text_paths():
            canon = files[rel]
            out = pr.expected_bytes(rel, canon, plans_dir="docs/planes")
            if out == canon:
                continue
            changed.append(rel)
            a, b = canon.decode("iso-8859-1").split("\n"), out.decode("iso-8859-1").split("\n")
            self.assertEqual(len(a), len(b), rel)
            diff = [i for i in range(len(a)) if a[i] != b[i]]
            self.assertEqual(len(diff), 1, rel)
            self.assertEqual(b[diff[0]], a[diff[0]].replace("docs/plans/", "docs/planes/"), rel)
            self.assertNotIn(b"\r", out)
            self.assertEqual(out.endswith(b"\n"), canon.endswith(b"\n"), rel)
            self.assertNotIn(b"docs/plans/", out, rel)
        self.assertEqual(sorted(changed), THREE_FILES)

    def test_case7_the_other_nine_files_are_identical_and_atlas_front_is_intact(self):
        files = repo_files()
        for rel in pr.managed_paths():
            if rel in THREE_FILES:
                continue
            with self.subTest(file=rel):
                self.assertEqual(pr.expected_bytes(rel, files[rel], plans_dir="docs/planes"), files[rel])
        atlas = files["agents/atlas.md"]
        out = pr.expected_bytes("agents/atlas.md", atlas, plans_dir="docs/planes")
        def front(b):
            lines = b.decode("iso-8859-1").split("\n")
            return lines[:lines.index("---", 1) + 1]

        self.assertEqual(front(out), front(atlas))

    def test_case7_without_a_folder_the_bytes_are_the_canonical_ones(self):
        files = repo_files()
        for plans in (None, "docs/plans"):
            for rel in pr.managed_paths():
                self.assertEqual(pr.expected_bytes(rel, files[rel], plans_dir=plans), files[rel], rel)

    def test_case7_crlf_source_gives_the_same_result(self):
        files = repo_files()
        for rel in THREE_FILES:
            crlf = files[rel].replace(b"\n", b"\r\n")
            self.assertEqual(pr.expected_bytes(rel, crlf, plans_dir="docs/planes"),
                             pr.expected_bytes(rel, files[rel], plans_dir="docs/planes"), rel)


class Commutation(unittest.TestCase):
    """Caso 8: el orden de alias, carpeta y nivel no cambia el resultado."""

    ORDERS = [("alias", "plans", "level"), ("plans", "alias", "level"), ("level", "alias", "plans"),
              ("alias", "level", "plans"), ("plans", "level", "alias"), ("level", "plans", "alias")]

    def test_case8_six_orders_agree_on_the_eleven_texts(self):
        files = repo_files()
        for level in (1, 2, 3, 4, 5):
            for folder in ("docs/planes", "x/docs/plans", "planes"):
                for rel in text_paths():
                    with self.subTest(level=level, folder=folder, file=rel):
                        results = {order: pr.expected_bytes(rel, files[rel], level, NINE, folder, order)
                                   for order in self.ORDERS}
                        self.assertEqual(len(self.ORDERS), 6)
                        self.assertEqual(len(set(results.values())), 1)

    def test_case8_the_composition_does_what_it_says(self):
        files = repo_files()
        out = pr.expected_bytes("agents/atlas.md", files["agents/atlas.md"], 3, NINE, "docs/planes").decode()
        self.assertIn("name: mapa\n", out)
        self.assertIn("`docs/planes/YYYY-MM-DD-<topic>.md`", out)
        self.assertNotIn("docs/plans/", out)
        model, effort = lr.read_script_table()[(3, "atlas")]
        self.assertIn("model: " + model + "\n", out)
        self.assertNotIn("atlas", out)

    def test_case8_the_hook_is_never_transformed(self):
        files = repo_files()
        hook = files["hooks/agent_guard.py"]
        self.assertEqual(pr.expected_bytes("hooks/agent_guard.py", hook, 3, NINE, "docs/planes"), hook)

    def test_case8_the_order_must_be_a_permutation(self):
        with self.assertRaises(ValueError):
            pr.expected_bytes("rules/agentes.md", b"x\n", order=("alias", "plans"))


class Devices(unittest.TestCase):
    """Caso 9."""

    def test_case9_device_names_are_the_ones_of_allowed_pattern(self):
        m = re.search(r"^\$AllowedPattern = '(.*)'$", lr.script_text(), re.M)
        self.assertIsNotNone(m)
        group = re.search(r"\(\?!\(([^)]*)\)\\\.\)", m.group(1)).group(1)
        names = []
        for alt in group.split("|"):
            r = re.fullmatch(r"([a-z]+)\[0-9\]", alt)
            names += [r.group(1) + str(i) for i in range(10)] if r else [alt]
        self.assertEqual(sorted(names), sorted(pr.DEVICE_NAMES))
        self.assertEqual(len(pr.DEVICE_NAMES), len(set(pr.DEVICE_NAMES)))

    def test_case9_every_device_name_is_rejected_as_a_segment(self):
        for name in pr.DEVICE_NAMES:
            for value in (name, "docs/" + name, name + "/docs"):
                with self.subTest(value=value):
                    self.assertEqual(pr.validate_plans_dir(value), pr.MSG_DEVICE)


def stray_cr(text):
    """Un CR que no va seguido de LF (el indice de git guarda LF; el checkout puede dejar CRLF)."""
    return re.search(r"\r(?!\n)", text) is not None


class ScriptStaysClean(unittest.TestCase):
    """Caso 31. ASCII, comodines, &&, ??, iex y datos personales: StaticChecks de test_install.py."""

    def test_case31_install_script_is_clean(self):
        with open(lr.SCRIPT, "rb") as f:
            raw = f.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\x00", raw)
        self.assertNotIn(b"\x08", raw)
        text = raw.decode("ascii")
        self.assertFalse(stray_cr(text), "hay un CR suelto")
        self.assertEqual(len([x for x in text.split("\n") if x.strip().startswith("# Alias:")]), 1)

    def test_case31_line_endings_are_lf_or_crlf_but_never_a_stray_cr(self):
        text = lr.script_text()
        self.assertFalse(stray_cr(text))
        self.assertFalse(stray_cr(text.replace("\n", "\r\n")))
        self.assertTrue(stray_cr(text + "\rx"))
        self.assertTrue(stray_cr("a\r\r\nb"))


if __name__ == "__main__":
    unittest.main()
