"""Pruebas de la Fase 6, T1: referencia del renombrado de agentes, colisiones y ensayo en memoria.

Casos del plan docs/plans/2026-11-27-fase6-renombrado-de-agentes.md: 1 (tabla), 2 (V1 a V4 de los nombres
nuevos), 3 (ningun nombre nuevo aparece hoy), 4 (ensayo en memoria con la transformacion de alias), 5 (prueba
puente: hashes esperados), 6 (supuestos 5, 6 y 7) y 18 (parte previa: hooks:, tools:, model: y color: fijados).
No tocan ~/.claude ni install.ps1. Sin PowerShell: solo biblioteca estandar.
"""

import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aliases_ref as ar  # noqa: E402
import levels_ref as lr  # noqa: E402
import names as nm  # noqa: E402  (fuente unica de los nombres de rol vivos)
import rename_ref as rr  # noqa: E402
import test_aliases as ta  # noqa: E402  (INVENTORY: recuentos de las formas de cada rol)
from names import (ANALYST, DEBUGGER, DEVELOPER, PLANNER, QA, RESEARCHER, REVIEWER, SECURITY,  # noqa: E402
                   WRITER)

bm = ar.bm
OLD_ROLES = sorted(set(nm.ROLES) - {PLANNER})
NEW_NAMES = ["anubis", "hector", "heimdall", "hermes", "salomon", "shakespeare", "sherlock", "sindri"]


class RenameTable(unittest.TestCase):
    """Caso 1."""

    def test_case1_eight_pairs(self):
        self.assertEqual(rr.RENAME, {ANALYST: "heimdall", RESEARCHER: "hermes", DEVELOPER: "sindri",
                                     QA: "anubis", REVIEWER: "salomon", SECURITY: "hector",
                                     DEBUGGER: "sherlock", WRITER: "shakespeare"})
        self.assertEqual(len(rr.RENAME), 8)

    def test_case1_planner_is_outside_and_names_are_unique(self):
        self.assertNotIn(PLANNER, rr.RENAME)
        self.assertNotIn(PLANNER, rr.RENAME.values())
        self.assertEqual(sorted(rr.RENAME), OLD_ROLES)
        self.assertEqual(sorted(rr.RENAME.values()), NEW_NAMES)
        self.assertEqual(len(set(rr.RENAME.values())), 8)

    def test_case1_old_names_are_the_live_roles_but_the_planner(self):
        # Hoy los roles de install.ps1 y agents/ son los viejos: son las claves de la tabla.
        self.assertEqual(sorted(set(ar.roles()) - {PLANNER}), sorted(rr.RENAME))
        listed = sorted(f[:-3] for f in os.listdir(lr.AGENTS_DIR) if f.endswith(".md"))
        self.assertEqual(sorted(set(listed) - {PLANNER}), sorted(rr.RENAME))

    def test_case1_names_are_plain_lowercase_without_accents(self):
        # P12: sin tilde (Salomon, Hector): una forma con tilde no es ninguna de las tres formas del reemplazo.
        for old, new in rr.RENAME.items():
            with self.subTest(old=old):
                self.assertRegex(new, r"^[a-z]+\Z")
                self.assertTrue(new.isascii())


class NewNamesAsAliases(unittest.TestCase):
    """Caso 2: V1 a V4 con las listas actuales de install.ps1."""

    def test_case2_the_whole_table_passes_the_validation(self):
        self.assertIsNone(ar.validate_table(dict(rr.RENAME)))

    def test_case2_each_pair_passes_on_its_own(self):
        for old, new in rr.RENAME.items():
            with self.subTest(new=new):
                self.assertIsNone(ar.validate_table({old: new}))

    def test_case2_v1_to_v4_one_by_one(self):
        reserved, yaml = ar.reserved(), ar.yaml_words()
        for new in rr.RENAME.values():
            with self.subTest(new=new):
                self.assertRegex(new, r"^[a-z][a-z0-9_-]{0,63}\Z")                       # V1
                self.assertNotIn(new, yaml)                                              # V2
                self.assertIsNotNone(bm.ALLOWED.match("agents/" + new + ".md"))          # V3
                self.assertNotIn(new, reserved)                                          # V4

    def test_case2_no_clash_ignoring_case(self):
        # NTFS no distingue mayusculas: los nueve nombres (con el del planificador) son distintos sin distinguirlas.
        names = [PLANNER] + list(rr.RENAME.values())
        self.assertEqual(len({n.lower() for n in names}), 9)
        self.assertEqual(len({n.casefold() for n in names}), 9)
        lowered_reserved = {n.lower() for n in ar.reserved()} | {n.lower() for n in ar.yaml_words()}
        self.assertEqual({n.lower() for n in names} & lowered_reserved, set())

    def test_case2_control_a_bad_name_is_rejected(self):
        # Que la prueba no sea vacua: un integrado, una palabra YAML y un rol vivo si se rechazan.
        self.assertIn("integrado", ar.validate_table({DEVELOPER: "explore"}))
        self.assertIn("YAML", ar.validate_table({DEVELOPER: "yes"}))
        self.assertIn("otro agente", ar.validate_table({DEVELOPER: RESEARCHER}))
        self.assertIn("contiene", ar.validate_table({DEVELOPER: "hermes-" + RESEARCHER}))


class NoNewNameToday(unittest.TestCase):
    """Caso 3 (supuesto 4): ningun nombre nuevo aparece hoy, en ninguna capitalizacion ni como subcadena."""

    def setUp(self):
        self.files = rr.scan_files()

    def test_case3_scan_covers_managed_files_script_tools_and_tests(self):
        paths = set(self.files)
        for rel in ("agents/%s.md" % PLANNER, "agents/%s.md" % DEVELOPER, "rules/agentes.md", "hooks/agent_guard.py",
                    "docs/agentes.md", "install.ps1", "tools/build_manifest.py", "tools/usage_report.py",
                    "tests/test_aliases.py", "tests/aliases_ref.py"):
            self.assertIn(rel, paths)
        self.assertEqual([p for p in paths if p in rr.OWN_FILES], [])
        self.assertEqual([p for p in paths if "__pycache__" in p or p.endswith(".pyc")], [])
        self.assertGreaterEqual(len(paths), 34)

    def test_case3_no_new_name_today(self):
        self.assertEqual(rr.new_name_hits(self.files), [])

    def test_case3_adding_hermes_to_a_managed_text_fails(self):
        # Mutacion sobre una copia en memoria: nada se escribe en el repositorio.
        for rel in ("rules/agentes.md", "docs/agentes.md", "agents/%s.md" % DEVELOPER):
            with self.subTest(rel=rel):
                mutated = dict(self.files)
                mutated[rel] = mutated[rel] + b"\nHermes\n"
                self.assertEqual(rr.new_name_hits(mutated), [(rel, "hermes")])
                self.assertEqual(rr.new_name_hits(self.files), [])

    def test_case3_detects_any_capitalization_and_substrings(self):
        for text in (b"hermes", b"Hermes", b"HERMES", b"hErMeS", b"xhermesx", b"ahectorb", b"_SINDRI_"):
            with self.subTest(text=text):
                self.assertTrue(rr.new_name_hits({"x.txt": text}))
        self.assertEqual(rr.new_name_hits({"x.txt": b"escribe describe hermano hera"}), [])


class DryRunInMemory(unittest.TestCase):
    """Caso 4: la transformacion de alias de la Fase 4 con la tabla del renombrado, sin escribir nada."""

    def setUp(self):
        self.expected = rr.expected_texts()

    def sources(self):
        return {"agents/%s.md" % r: ar.repo_text("agents/%s.md" % r) for r in ar.roles()}

    def test_case4_eleven_texts_with_the_new_paths_as_keys(self):
        self.assertEqual(len(self.expected), 11)
        self.assertEqual(sorted(self.expected), sorted(
            ["agents/%s.md" % PLANNER] + ["agents/%s.md" % n for n in NEW_NAMES]
            + ["rules/agentes.md", "docs/agentes.md"]))
        for path, data in self.expected.items():
            with self.subTest(path=path):
                self.assertIsInstance(data, bytes)
                self.assertNotIn(b"\r", data)

    def test_case4_the_table_is_valid_and_the_inputs_are_untouched(self):
        # V8: ningun nombre nuevo coincide con una ruta del manifiesto actual.
        self.assertIsNone(ar.validate_table(dict(rr.RENAME), bm.managed_files(ar.ROOT)))
        before = {rel: ar.repo_text(rel) for rel in ar.text_files()}
        rr.expected_texts()
        self.assertEqual({rel: ar.repo_text(rel) for rel in ar.text_files()}, before)

    def test_case4_no_unclassified_word_and_no_old_name_left(self):
        for path, data in self.expected.items():
            with self.subTest(path=path):
                text = data.decode("iso-8859-1")
                counts, other = ar.inventory(text)
                self.assertEqual(other, [], "palabra con un nombre viejo que no es ninguna de las tres formas")
                self.assertEqual({r: v for r, v in counts.items() if any(v) and r != PLANNER}, {},
                                 "queda un nombre viejo como palabra")
                self.assertEqual(ar.role_hits(text, dict(rr.RENAME)), [])
                _new_counts, new_other = rr.word_counts(text, NEW_NAMES)
                self.assertEqual(new_other, [], "palabra con un nombre nuevo que no es ninguna de las tres formas")

    def test_case4_counts_are_preserved_one_to_one(self):
        # La transformacion es uno a uno: los recuentos de INVENTORY pasan al nombre nuevo, forma a forma.
        for old_path, counts in ta.INVENTORY.items():
            new_path = rr.new_path(old_path)
            with self.subTest(old=old_path, new=new_path):
                text = self.expected[new_path].decode("iso-8859-1")
                new_counts, other = rr.word_counts(text, NEW_NAMES + [PLANNER])
                self.assertEqual(other, [])
                want = {rr.RENAME.get(role, role): v for role, v in counts.items()}
                self.assertEqual({n: v for n, v in new_counts.items() if any(v)}, want)

    def test_case4_substring_count_equals_form_count(self):
        # Ningun nombre nuevo es subcadena de otra palabra: cada aparicion (sin distinguir mayusculas) es una forma.
        for path, data in self.expected.items():
            text = data.decode("iso-8859-1")
            new_counts, _other = rr.word_counts(text, NEW_NAMES)
            for name in NEW_NAMES:
                with self.subTest(path=path, name=name):
                    self.assertEqual(len(re.findall(re.escape(name), text, re.I)), sum(new_counts[name]))

    def test_case4_no_new_name_in_sensitive_zones(self):
        for path in ("rules/agentes.md", "docs/agentes.md"):
            with self.subTest(path=path):
                text = self.expected[path].decode("iso-8859-1")
                zones = ar.sensitive_zones(text)
                self.assertTrue(zones or path == "rules/agentes.md")
                self.assertEqual([(z, n) for z in zones for n in NEW_NAMES if n in z.lower()], [])

    def test_case4_new_names_are_not_next_to_a_foreign_letter(self):
        # Misma condicion que aliases_ref.foreign_letter_hits (letras y marcas combinantes), los once textos.
        for path, data in self.expected.items():
            with self.subTest(path=path):
                self.assertEqual(rr.foreign_letter_hits(data.decode("utf-8")), [])

    def test_case4_foreign_letter_check_sees_letters_and_combining_marks(self):
        for text in ("hermes\u0301", "\u0101hermes", "sindri\u0100", "x\u0301anubis"):
            with self.subTest(text=text):
                self.assertTrue(rr.foreign_letter_hits(text))
        for text in ("hermes\u00e9", "\u00e9hermes", "hermes, anubis", "hermes"):
            with self.subTest(text=text):
                self.assertEqual(rr.foreign_letter_hits(text), [])

    def test_case4_only_name_description_and_body_change_and_hooks_stay(self):
        for old in ar.roles():
            new = rr.RENAME.get(old, old)
            with self.subTest(old=old):
                src = ar.repo_text("agents/%s.md" % old).split("\n")
                out = self.expected["agents/%s.md" % new].decode("iso-8859-1").split("\n")
                close = src.index("---", 1)
                self.assertEqual(len(out), len(src))
                self.assertEqual(out.index("---", 1), close)
                self.assertEqual([l for l in out[1:close] if l.startswith("name:")], ["name: " + new])
                for i, (a, b) in enumerate(zip(src, out)):
                    if a == b:
                        continue
                    if 0 < i < close:
                        self.assertTrue(a.startswith(("name:", "description:")), "cambio en el frontmatter: %r" % a)
                    else:
                        self.assertTrue(ar.role_hits(a, dict(rr.RENAME)), "cambio sin nombre viejo: %r" % a)
                if "hooks:" in src:
                    h = src.index("hooks:")
                    self.assertEqual(out[h:close], src[h:close])

    def test_case4_the_old_path_is_not_a_key_and_the_new_one_holds_the_transformed_agent(self):
        # Solo la clave de ruta es nueva: el agente de cada rol viejo vive bajo la ruta del nombre nuevo.
        for old, new in rr.RENAME.items():
            with self.subTest(old=old):
                self.assertNotIn("agents/%s.md" % old, self.expected)
                self.assertIn(b"\nname: " + new.encode("ascii") + b"\n", self.expected["agents/%s.md" % new])


class BridgeFixture(unittest.TestCase):
    """Caso 5: prueba puente. Vive de T1 a T7; T8 la retira. Tras T7 los hashes son los del repositorio."""

    def fixture(self):
        with open(rr.FIXTURE, "rb") as f:
            return json.loads(f.read().decode("utf-8"))

    def test_case5_fixture_shape(self):
        data = self.fixture()
        self.assertEqual(list(data), ["schema", "algorithm", "eol", "files"])
        self.assertEqual((data["schema"], data["algorithm"], data["eol"]), (1, "sha256", "lf"))
        self.assertEqual(len(data["files"]), 11)
        self.assertEqual(list(data["files"]), sorted(data["files"]))
        for path, digest in data["files"].items():
            with self.subTest(path=path):
                self.assertRegex(digest, r"^[0-9a-f]{64}\Z")
                self.assertIsNotNone(bm.ALLOWED.match(path))

    def test_case5_expected_texts_match_the_fixture(self):
        self.assertEqual(rr.expected_hashes(), self.fixture()["files"])

    def test_case5_fixture_is_ascii_with_lf_and_final_newline(self):
        with open(rr.FIXTURE, "rb") as f:
            raw = f.read()
        # core.autocrlf: el checkout puede dejar CRLF; se normaliza antes de comparar.
        norm = raw.replace(b"\r\n", b"\n")
        self.assertTrue(norm.isascii())
        self.assertTrue(norm.endswith(b"\n"))
        self.assertEqual(norm, rr.fixture_bytes())

    def test_write_refuses_on_an_already_renamed_repository(self):
        renamed = [PLANNER] + sorted(rr.RENAME.values())
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "fixture.json")
            with mock.patch.object(rr, "FIXTURE", target), mock.patch.object(ar, "roles", lambda: renamed), \
                    mock.patch.object(sys, "stderr", io.StringIO()) as err:
                self.assertEqual(rr.main(["--write"]), 1)
            self.assertFalse(os.path.exists(target))
            self.assertEqual(err.getvalue(), rr.MSG_REFUSED + "\n")
            with mock.patch.object(rr, "FIXTURE", target), mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(rr.main(["--write"]), 0)
            with open(target, "rb") as f:
                self.assertEqual(f.read(), rr.fixture_bytes())
            with mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(rr.main([]), 2)

    def test_case5_changing_a_pair_changes_the_hashes(self):
        fixture = self.fixture()["files"]
        swapped = dict(rr.RENAME, **{ANALYST: "hermes", RESEARCHER: "heimdall"})
        self.assertIsNone(ar.validate_table(swapped))
        got = rr.expected_hashes(table=swapped)
        self.assertNotEqual(got, fixture)
        # Una pareja distinta toca sus dos agentes, las reglas y la guia (nombran a ambos).
        self.assertNotEqual(got["agents/hermes.md"], fixture["agents/hermes.md"])
        self.assertNotEqual(got["rules/agentes.md"], fixture["rules/agentes.md"])
        self.assertNotEqual(got["docs/agentes.md"], fixture["docs/agentes.md"])
        planner_path = "agents/%s.md" % PLANNER
        self.assertEqual(got[planner_path] == fixture[planner_path], False)  # el planificador nombra al analista

    def test_case5_a_renamed_name_changes_the_hashes(self):
        other = dict(rr.RENAME, **{DEVELOPER: "sindrix"})
        self.assertNotEqual(rr.expected_hashes(table=other), self.fixture()["files"])

    def test_case5_hashes_are_canonical_sha256_of_lf_bytes(self):
        data = self.fixture()["files"]
        for path, raw in rr.expected_texts().items():
            with self.subTest(path=path):
                self.assertEqual(bm.canonical_sha256(raw), data[path])
                self.assertEqual(bm.canonical_sha256(raw.replace(b"\n", b"\r\n")), data[path])


class AssumptionsFiveToSeven(unittest.TestCase):
    """Caso 6: supuestos 5, 6 y 7 del plan."""

    def test_case6_assumption5_manifest_is_sorted_and_new_order_changes(self):
        paths = bm.managed_files(ar.ROOT)
        self.assertEqual(paths, sorted(paths))
        with open(os.path.join(ar.ROOT, "install-manifest.json"), "rb") as f:
            listed = [e["path"] for e in json.loads(f.read().decode("utf-8"))["files"]]
        self.assertEqual(listed, sorted(listed))
        new_paths = sorted(rr.new_path(p) for p in paths)
        self.assertNotEqual(new_paths, paths)
        agents = [p for p in new_paths if p.startswith("agents/")]
        self.assertEqual(agents[0], "agents/anubis.md")
        self.assertEqual(agents, ["agents/%s.md" % n for n in ["anubis", PLANNER] + NEW_NAMES[1:]])
        self.assertEqual(len(new_paths), 12)

    def test_case6_assumption6_read_ps_list_reads_an_empty_list(self):
        for text in ("$LegacyRoles = @()\n", "$LegacyRoles = @()\r\n", "x\n$LegacyRoles = @()\nz\n"):
            with self.subTest(text=text):
                self.assertEqual(lr.read_ps_list("LegacyRoles", text), [])
        self.assertEqual(lr.read_ps_list("LegacyRoles", "$LegacyRoles = @('a|b', 'c|d')\n"), ["a|b", "c|d"])

    def test_case6_assumption7_no_test_compares_the_svgs_with_agents_data(self):
        users = []
        for name in sorted(os.listdir(HERE)):
            if not name.endswith(".py") or name in rr.OWN_NAMES:
                continue
            with open(os.path.join(HERE, name), "rb") as f:
                text = f.read().decode("utf-8")
            if "agents_data" in text:
                users.append(name)
            if re.search(r"\.svg\b", text, re.I) and name != "test_brand_agents.py":
                self.fail("la prueba %s lee SVG de marca" % name)
        self.assertEqual(users, ["test_brand_agents.py"])
        with open(os.path.join(HERE, "test_brand_agents.py"), "rb") as f:
            self.assertIsNone(re.search(rb"\.svg\b", f.read(), re.I))


class FrozenFrontmatter(unittest.TestCase):
    """Caso 18, parte previa: hooks:, tools:, model: y color: fijados como datos."""

    def test_case18_frozen_data_equals_the_repository_today(self):
        frozen = rr.frozen_frontmatter()
        self.assertEqual(sorted(frozen), sorted(ar.roles()))
        for role in ar.roles():
            with self.subTest(role=role):
                self.assertEqual(frozen[role], rr.frontmatter_parts(ar.repo_text("agents/%s.md" % role)))

    def test_case18_the_guards_are_as_documented(self):
        frozen = rr.frozen_frontmatter()
        modes = {role: [l.split("agent_guard.py\" ")[1].rstrip("'") for l in parts["hooks"] if "agent_guard.py" in l]
                 for role, parts in frozen.items()}
        self.assertEqual(modes, {PLANNER: [], REVIEWER: ["readonly --allow-temp"], DEBUGGER: ["readonly --allow-temp"],
                                 DEVELOPER: [], ANALYST: [], RESEARCHER: [], WRITER: [],
                                 QA: ["tests-only"], SECURITY: ["readonly --allow-temp"]})

    def test_case18_transformed_texts_keep_the_frozen_lines(self):
        expected = rr.expected_texts()
        for role, parts in rr.frozen_frontmatter().items():
            new = rr.RENAME.get(role, role)
            with self.subTest(role=role, new=new):
                got = rr.frontmatter_parts(expected["agents/%s.md" % new].decode("iso-8859-1"))
                self.assertEqual(got, parts)

    def test_case18_a_changed_line_is_detected(self):
        frozen = rr.frozen_frontmatter()
        text = ar.repo_text("agents/%s.md" % QA).replace("tests-only", "readonly --allow-temp")
        self.assertNotEqual(rr.frontmatter_parts(text), frozen[QA])
        text = ar.repo_text("agents/%s.md" % DEVELOPER).replace("model: sonnet", "model: opus")
        self.assertNotEqual(rr.frontmatter_parts(text), frozen[DEVELOPER])


class NamesModule(unittest.TestCase):
    """tests/names.py contra el repositorio: es la referencia escrita a mano, independiente de install.ps1."""

    def test_roles_are_the_agents_dir_and_sorted(self):
        listed = sorted(f[:-3] for f in os.listdir(lr.AGENTS_DIR) if f.endswith(".md"))
        self.assertEqual(nm.ROLES, listed)
        self.assertEqual(len(nm.ROLES), 9)
        self.assertEqual(len(set(nm.ROLES)), 9)

    def test_script_lists_equal_the_reference(self):
        self.assertEqual(lr.read_ps_list("AliasRoles"), nm.ROLES)
        self.assertEqual(lr.read_ps_list("LevelAgents"), nm.LEVEL_ROLES)

    def test_fixed_and_level_roles_partition_the_roles(self):
        self.assertEqual(sorted(nm.LEVEL_ROLES + nm.FIXED), nm.ROLES)
        self.assertEqual(set(nm.LEVEL_ROLES) & set(nm.FIXED), set())

    def test_guarded_equals_the_hooks_of_the_agents(self):
        modes = {}
        for role in nm.ROLES:
            parts = rr.frontmatter_parts(ar.repo_text("agents/%s.md" % role))
            found = [l.split("agent_guard.py\" ")[1].rstrip("'") for l in parts["hooks"] if "agent_guard.py" in l]
            if found:
                modes[role] = found[0]
        self.assertEqual(modes, nm.GUARDED)

    def test_legacy_is_empty_until_the_change(self):
        self.assertEqual(nm.LEGACY, {})


# --- caso 7: ningun nombre viejo literal en las pruebas parametrizadas ---

INSTALL_FILE = "test_install.py"

PARAMETRIZED = ("test_aliases.py", "aliases_ref.py", "test_levels.py", "levels_ref.py", "test_plans.py",
                "plans_ref.py", "test_manifest.py", "test_phase5_docs.py", "test_rename.py", "test_brand_agents.py",
                "test_install.py")
# Lista cerrada de excepciones: {archivo: [identificadores que se quitan antes de buscar]}. Dos entradas: el
# identificador del diccionario de palabras de aliases_ref.py (<ROL>_WORDS con el rol del escritor; nombre
# fijado por el plan, T2 y T4) y su uso desde test_install.py (ar.<ROL>_WORDS). Ningun otro literal de un nombre viejo se permite en la lista; ademas se quitan antes de
# buscar las palabras espanolas con la subcadena del nombre del escritor.
ALLOWED_TOKENS = {"aliases_ref.py": [nm.WRITER.upper() + "_WORDS"],
                  "test_install.py": ["ar." + nm.WRITER.upper() + "_WORDS"]}
_SPANISH_WORDS = re.compile("escriben|escribe|describe|reescribe|sobrescribe", re.I)
_CONSTANT_TOKEN = re.compile(r"\b" + nm.DEBUGGER.upper() + r"\b")   # el identificador names.DEBUGGER


def old_names():
    return sorted(set(nm.ROLES) | set(nm.LEGACY))


def old_name_hits(text, old=None):
    """[(linea, nombre)] de los nombres viejos como subcadena (cualquier capitalizacion). Se quitan antes las
    palabras espanolas con la subcadena del escritor y el identificador de la constante del depurador."""
    old = old_names() if old is None else old
    text = _CONSTANT_TOKEN.sub("", _SPANISH_WORDS.sub("", text))
    hits = []
    for lineno, line in enumerate(text.split("\n"), 1):
        low = line.lower()
        hits += [(lineno, n) for n in old if n in low]
    return hits


class Parametrization(unittest.TestCase):
    """Caso 7: parametrizacion sin cambio de comportamiento."""

    def test_case7_no_old_name_literal_outside_the_closed_list(self):
        for name in PARAMETRIZED:
            with self.subTest(file=name):
                with open(os.path.join(HERE, name), "rb") as f:
                    text = f.read().decode("utf-8")
                for token in ALLOWED_TOKENS.get(name, []):
                    self.assertIn(token, text)   # la excepcion existe: si deja de usarse, se retira
                    text = text.replace(token, "")
                found = [(n, l) for l, n in old_name_hits(text)]
                self.assertEqual(found, [], "nombre viejo literal en %s" % name)

    def test_case7_the_scan_detects_literals_and_skips_spanish_words(self):
        old = ["alfa", "delta", "tau"]
        self.assertEqual(old_name_hits("x\nuna Alfa y DELTA\n", old), [(2, "alfa"), (2, "delta")])
        self.assertEqual(old_name_hits("alfa_x y xtau", old), [(1, "alfa"), (1, "tau")])
        self.assertEqual(old_name_hits("escribe describe reescribe sobrescribe Escriben", [WRITER]), [])
        self.assertEqual(old_name_hits("%s %s" % (WRITER.capitalize(), WRITER.upper()), [WRITER]), [(1, WRITER)])
        self.assertEqual(old_name_hits(nm.DEBUGGER.upper() + " " + nm.DEBUGGER.upper(), [nm.DEBUGGER]), [])
        self.assertEqual(old_name_hits(nm.DEBUGGER, [nm.DEBUGGER]), [(1, nm.DEBUGGER)])

    def test_case7_the_full_scan_covers_test_install_and_is_not_empty(self):
        # test_install.py esta en PARAMETRIZED entero (T3 y T4), sin cortes ni excepciones de nombres viejos: se
        # comprueba que la lista lo incluye y que el texto escaneado trae los extremos del archivo.
        self.assertIn(INSTALL_FILE, PARAMETRIZED)
        with open(os.path.join(HERE, INSTALL_FILE), "rb") as f:
            text = f.read().decode("utf-8")
        self.assertGreater(text.count(chr(10)), 8000)
        # sin quitar el token, el escaneo ve contenido real: las unicas lineas con hit son las que traen el token
        token = ALLOWED_TOKENS[INSTALL_FILE][0]
        lines = text.split(chr(10))
        expected = sorted(i + 1 for i, l in enumerate(lines) if token in l)
        self.assertTrue(expected)
        self.assertEqual(sorted({ln for ln, _n in old_name_hits(text)}), expected)

    def test_case7_names_py_and_rename_ref_are_the_only_homes_of_the_names(self):
        # names.py define las constantes; rename_ref.py guarda la tabla del renombrado (claves = nombres viejos).
        for name in ("names.py", "rename_ref.py"):
            with open(os.path.join(HERE, name), "rb") as f:
                self.assertTrue(old_name_hits(f.read().decode("utf-8")), name)


# --- caso 8: mutacion de control ---

MUTATED = {"PLANNER": "kappa", "ANALYST": "lambda", "RESEARCHER": "sigma", "DEVELOPER": "omega", "QA": "tau",
           "REVIEWER": "rho", "SECURITY": "phi", "DEBUGGER": "chi", "WRITER": "psi"}

# Pruebas puras (no leen install.ps1, agents/ ni la documentacion): deben pasar con otros nueve nombres.
PURE = {
    "test_aliases": ["WordBoundary", "HighByteBoundary",
                     "ReferenceTransform.test_empty_effective_table_returns_the_canonical_bytes",
                     "ReferenceTransform.test_agent_name_description_and_cross_references",
                     "ReferenceTransform.test_body_name_line_is_body",
                     "ReferenceTransform.test_defective_frontmatter_is_rejected",
                     "ReferenceTransform.test_crlf_and_high_bytes",
                     "ReferenceTransform.test_state_for3",
                     "ReferenceTransform.test_dest_for"],
    "test_levels": ["TableComparison.test_promise_guard_catches_savings_claims",
                    "RealAgentsRender.test_reference_renderer_edge_cases"],
    "test_plans": ["LeftBoundary", "SinglePass"],
}
# Mismos modulos de pruebas que se vuelven a importar con los nombres mutados.
_FRESH = ("names", "aliases_ref", "plans_ref")


def mutated_names_module():
    mod = type(sys)("names")
    for const, value in MUTATED.items():
        setattr(mod, const, value)
    mod.ROLES = sorted(MUTATED.values())
    mod.LEVEL_ROLES = [mod.PLANNER, mod.DEVELOPER, mod.QA, mod.WRITER, mod.RESEARCHER, mod.ANALYST]
    mod.FIXED = [mod.REVIEWER, mod.SECURITY, mod.DEBUGGER]
    mod.GUARDED = {mod.QA: "tests-only", mod.REVIEWER: "readonly --allow-temp",
                   mod.SECURITY: "readonly --allow-temp", mod.DEBUGGER: "readonly --allow-temp"}
    mod.LEGACY = {}
    return mod


def run_with_mutated_names(module_name, ids):
    """Importa de nuevo `tests/<module_name>.py` (y aliases_ref y plans_ref) con `names` mutado y corre `ids`
    (clases o Clase.metodo). Devuelve (resultado, modulo, salida). Restaura sys.modules al terminar."""
    saved = {key: sys.modules.get(key) for key in _FRESH}
    sys.modules["names"] = mutated_names_module()
    for key in _FRESH[1:]:
        sys.modules.pop(key, None)
    try:
        spec = importlib.util.spec_from_file_location("mutated_" + module_name,
                                                      os.path.join(HERE, module_name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        loader = unittest.TestLoader()
        suite = unittest.TestSuite(loader.loadTestsFromName(i, mod) for i in ids)
        out = io.StringIO()
        result = unittest.TextTestRunner(stream=out, verbosity=0).run(suite)
        return result, mod, out.getvalue()
    finally:
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


class MutationControl(unittest.TestCase):
    """Caso 8: con names.py cambiado en memoria a otros nueve nombres, las pruebas puras siguen pasando."""

    def test_case8_the_pure_tests_pass_with_other_nine_names(self):
        for module_name, ids in PURE.items():
            with self.subTest(module=module_name):
                result, _mod, out = run_with_mutated_names(module_name, ids)
                self.assertGreater(result.testsRun, 0)
                self.assertTrue(result.wasSuccessful(), out)

    def test_case8_the_modules_really_read_the_mutated_names(self):
        for module_name, attr in (("test_aliases", "NINE"), ("test_plans", "NINE")):
            with self.subTest(module=module_name):
                _result, mod, _out = run_with_mutated_names(module_name, PURE[module_name][:1])
                self.assertEqual(sorted(getattr(mod, attr)), sorted(MUTATED.values()))
        _result, mod, _out = run_with_mutated_names("test_aliases", PURE["test_aliases"][:1])
        self.assertEqual(mod.ROLES, sorted(MUTATED.values()))
        self.assertEqual(mod.LEVEL_ROLES, [MUTATED[k] for k in ("PLANNER", "DEVELOPER", "QA", "WRITER",
                                                                 "RESEARCHER", "ANALYST")])
        _result, mod, _out = run_with_mutated_names("test_levels", PURE["test_levels"][:1])
        self.assertEqual(mod.FIXED, [MUTATED[k] for k in ("REVIEWER", "SECURITY", "DEBUGGER")])

    def test_case8_control_a_test_that_reads_the_repository_fails(self):
        # Que el control no sea vacuo: una prueba que compara con install.ps1 si falla con los nombres mutados.
        result, _mod, _out = run_with_mutated_names(
            "test_aliases", ["ClosedLists.test_case1_alias_roles_match_agents_dir"])
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(result.wasSuccessful())
        result, _mod, _out = run_with_mutated_names("test_plans", ["RealRepository"])
        self.assertFalse(result.wasSuccessful())

    def test_case8_sys_modules_is_restored(self):
        before = {key: sys.modules.get(key) for key in _FRESH}
        run_with_mutated_names("test_plans", PURE["test_plans"])
        self.assertIs(sys.modules["names"], nm)
        for key in _FRESH:
            self.assertIs(sys.modules.get(key), before[key])
        self.assertEqual(nm.ROLES, sorted(nm.ROLES))
        self.assertNotIn(nm.PLANNER, MUTATED.values())


if __name__ == "__main__":
    unittest.main()
