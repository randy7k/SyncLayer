"""Pruebas de la Fase 6: renombrado de agentes (T1 la referencia y los ensayos; T7 el cambio atomico).

Casos del plan docs/plans/2026-11-27-fase6-renombrado-de-agentes.md: 1 (tabla), 2 (V1 a V4 de los nombres
nuevos), 3 (T7: ningun nombre viejo queda como palabra en los once textos ni en install.ps1 fuera de
$LegacyRoles), 4 (los once textos del repositorio), 5 (prueba puente: los hashes del repositorio son los del
fixture), 6 (supuestos 5, 6 y 7), 7 y 8 (parametrizacion y mutacion de control), 17 (coherencia del
repositorio renombrado), 18 (hooks:, tools:, model: y color: fijados antes del cambio), 20 (parte estatica:
$LegacyRoles y la clave vieja) y 21 (reporte de uso).
No tocan ~/.claude ni ejecutan install.ps1. Sin PowerShell: solo biblioteca estandar.
"""

import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import tokenize
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "assets", "brand", "src"))

import aliases_ref as ar  # noqa: E402
import levels_ref as lr  # noqa: E402
import names as nm  # noqa: E402  (fuente unica de los nombres de rol vivos)
import rename_ref as rr  # noqa: E402
import test_aliases as ta  # noqa: E402  (INVENTORY: recuentos de las formas de cada rol)
import usage_report as ur  # noqa: E402
from agents_data import AGENTS  # noqa: E402
from names import (ANALYST, DEBUGGER, DEVELOPER, PLANNER, QA, RESEARCHER, REVIEWER, SECURITY,  # noqa: E402
                   WRITER)

bm = ar.bm
ROOT = ar.ROOT
OLD_ROLES = sorted(rr.RENAME)        # los nombres anteriores (claves de la tabla del renombrado)
NEW_NAMES = ["anubis", "hector", "heimdall", "hermes", "salomon", "shakespeare", "sherlock", "sindri"]
OLD_OF = {new: old for old, new in rr.RENAME.items()}   # nombre nuevo -> nombre anterior
# Hash canonico de hooks/agent_guard.py fijado el 2026-11-27, antes del cambio: el renombrado no lo toca.
HOOK_SHA256 = "76082df93c06473b4c616e448ab2415ae4a2ab5139be028e6dc1c293db06ef32"


class RenameTable(unittest.TestCase):
    """Caso 1."""

    def test_case1_eight_pairs(self):
        # Los nombres nuevos son los roles de names.py; los viejos, las claves de la tabla (y names.LEGACY, copia
        # escrita a mano aparte).
        self.assertEqual(set(rr.RENAME.values()), {ANALYST, RESEARCHER, DEVELOPER, QA, REVIEWER, SECURITY,
                                                   DEBUGGER, WRITER})
        self.assertEqual(rr.RENAME, nm.LEGACY)
        self.assertEqual(len(rr.RENAME), 8)

    def test_case1_planner_is_outside_and_names_are_unique(self):
        self.assertNotIn(PLANNER, rr.RENAME)
        self.assertNotIn(PLANNER, rr.RENAME.values())
        self.assertEqual(set(rr.RENAME.values()), set(nm.ROLES) - {PLANNER})
        self.assertEqual(sorted(rr.RENAME.values()), NEW_NAMES)
        self.assertEqual(len(set(rr.RENAME.values())), 8)
        self.assertEqual(len(set(rr.RENAME)), 8)

    def test_case1_new_names_are_the_live_roles_and_the_old_ones_are_gone(self):
        # Tras T7 los roles de install.ps1 y agents/ son los nuevos; ningun nombre viejo es un rol ni un archivo.
        self.assertEqual(sorted(set(ar.roles()) - {PLANNER}), NEW_NAMES)
        listed = sorted(f[:-3] for f in os.listdir(lr.AGENTS_DIR) if f.endswith(".md"))
        self.assertEqual(sorted(set(listed) - {PLANNER}), NEW_NAMES)
        self.assertEqual(set(listed) & set(rr.RENAME), set())
        self.assertEqual(set(ar.roles()) & set(rr.RENAME), set())

    def test_case1_names_are_plain_lowercase_without_accents(self):
        # P12: sin tilde (Salomon, Hector): una forma con tilde no es ninguna de las tres formas del reemplazo.
        for old, new in rr.RENAME.items():
            with self.subTest(old=old):
                self.assertRegex(new, r"^[a-z]+\Z")
                self.assertTrue(new.isascii())


class NewNamesAsAliases(unittest.TestCase):
    """Caso 2: V1 a V4 con las listas de install.ps1. Tras T7 la tabla se prueba al reves (P3): cada nombre nuevo
    es el rol y el nombre viejo, un alias valido (la forma soportada de conservar los nombres viejos)."""

    def test_case2_the_whole_table_passes_the_validation(self):
        self.assertIsNone(ar.validate_table(dict(OLD_OF)))
        self.assertIsNone(ar.validate_table(dict(OLD_OF), bm.managed_files(ar.ROOT)))

    def test_case2_each_pair_passes_on_its_own(self):
        for new, old in OLD_OF.items():
            with self.subTest(new=new):
                self.assertIsNone(ar.validate_table({new: old}))

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


def old_word_hits(text):
    """[(linea, nombre)] de los nombres anteriores como palabra (limite de palabra de la enmienda E1, sin distinguir
    mayusculas) en un texto ASCII o ISO-8859-1. Una subcadena de otra palabra no cuenta."""
    hits = []
    for lineno, line in enumerate(text.split("\n"), 1):
        for name in OLD_ROLES:
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", line, re.I):
                hits.append((lineno, name))
    return hits


class NoOldNameLeft(unittest.TestCase):
    """Caso 3 tras T7 (el reves del supuesto 4): ningun nombre anterior queda como palabra en los once textos
    gestionados ni en install.ps1 fuera de la linea de $LegacyRoles."""

    def test_case3_no_old_name_in_the_eleven_managed_texts(self):
        for path, data in rr.repo_texts().items():
            with self.subTest(path=path):
                text = data.decode("iso-8859-1")
                self.assertEqual(old_word_hits(text), [])
                self.assertEqual(ar.role_hits(text, dict(rr.RENAME)), [])

    def test_case3_install_script_names_the_old_ones_only_in_legacy_roles(self):
        text = lr.script_text()
        hits = old_word_hits(text)
        lines = text.split("\n")
        self.assertTrue(hits)
        for lineno, name in hits:
            self.assertTrue(lines[lineno - 1].startswith("$LegacyRoles = @("), (lineno, name, lines[lineno - 1]))
        self.assertEqual({name for _l, name in hits}, set(rr.RENAME))

    def test_case3_the_scan_sees_a_mutated_copy_and_ignores_substrings(self):
        for path, data in rr.repo_texts().items():
            with self.subTest(path=path):
                mutated = data.decode("iso-8859-1") + "\n" + OLD_ROLES[0].capitalize() + "\n"
                self.assertEqual([n for _l, n in old_word_hits(mutated)], [OLD_ROLES[0]])
        self.assertEqual(old_word_hits("escribe describe reescribe sobrescribe"), [])
        self.assertEqual(old_word_hits("x%sy %s2" % (OLD_ROLES[0], OLD_ROLES[0])), [])
        self.assertEqual(old_word_hits("(%s) %s-uno" % (OLD_ROLES[0].upper(), OLD_ROLES[1])),
                         [(1, OLD_ROLES[0]), (1, OLD_ROLES[1])])


class ManagedTexts(unittest.TestCase):
    """Caso 4: los once textos del repositorio. Antes de T7 era el ensayo en memoria de la transformacion de alias
    con la tabla del renombrado; tras T7 los textos del repositorio son esa salida (el caso 5 los ata por hash)."""

    def setUp(self):
        self.expected = rr.repo_texts()

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
        # V8: ningun nombre viejo, usado como alias, coincide con una ruta del manifiesto actual.
        self.assertIsNone(ar.validate_table(dict(OLD_OF), bm.managed_files(ar.ROOT)))
        before = {rel: ar.repo_text(rel) for rel in ar.text_files()}
        rr.repo_texts()
        self.assertEqual({rel: ar.repo_text(rel) for rel in ar.text_files()}, before)

    def test_case4_no_unclassified_word_and_no_old_name_left(self):
        for path, data in self.expected.items():
            with self.subTest(path=path):
                text = data.decode("iso-8859-1")
                counts, other = ar.inventory(text)
                self.assertEqual(other, [], "palabra con un nombre de rol que no es ninguna de las tres formas")
                self.assertEqual(ar.role_hits(text, dict(rr.RENAME)), [], "queda un nombre viejo como palabra")
                self.assertEqual(old_word_hits(text), [])
                _new_counts, new_other = rr.word_counts(text, NEW_NAMES)
                self.assertEqual(new_other, [], "palabra con un nombre nuevo que no es ninguna de las tres formas")

    def test_case4_counts_are_preserved_one_to_one(self):
        # La transformacion fue uno a uno: los recuentos de INVENTORY (conservados desde antes del cambio) son los de
        # los nombres nuevos en cada texto, forma a forma, contados aparte con rr.word_counts.
        for path, counts in ta.INVENTORY.items():
            with self.subTest(path=path):
                text = self.expected[path].decode("iso-8859-1")
                new_counts, other = rr.word_counts(text, NEW_NAMES + [PLANNER])
                self.assertEqual(other, [])
                self.assertEqual({n: v for n, v in new_counts.items() if any(v)}, counts)

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
        for text in ("hermeś", "āhermes", "sindriĀ", "x́anubis"):
            with self.subTest(text=text):
                self.assertTrue(rr.foreign_letter_hits(text))
        for text in ("hermesé", "éhermes", "hermes, anubis", "hermes"):
            with self.subTest(text=text):
                self.assertEqual(rr.foreign_letter_hits(text), [])

    def test_case4_the_name_line_matches_the_file_and_the_frontmatter_closes(self):
        for role in ar.roles():
            with self.subTest(role=role):
                lines = self.expected["agents/%s.md" % role].decode("iso-8859-1").split("\n")
                self.assertEqual(lines[0], "---")
                close = lines.index("---", 1)
                self.assertEqual([l for l in lines[1:close] if l.startswith("name:")], ["name: " + role])
                self.assertEqual(len([l for l in lines[1:close] if l.startswith("description:")]), 1)

    def test_case4_the_old_paths_are_not_keys_and_do_not_exist(self):
        for old, new in rr.RENAME.items():
            with self.subTest(old=old):
                self.assertNotIn("agents/%s.md" % old, self.expected)
                self.assertFalse(os.path.exists(os.path.join(ar.ROOT, "agents", old + ".md")))
                self.assertIn(b"\nname: " + new.encode("ascii") + b"\n", self.expected["agents/%s.md" % new])


class BridgeFixture(unittest.TestCase):
    """Caso 5: prueba puente. Vive de T1 a T7; T8 la retira. Antes de T7 el fixture eran los hashes que produciria la
    transformacion; tras T7 son los hashes de los once textos del repositorio."""

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

    def test_case5_repository_hashes_match_the_fixture(self):
        self.assertEqual(rr.repo_hashes(), self.fixture()["files"])

    def test_case5_the_manifest_carries_the_fixture_hashes(self):
        with open(os.path.join(ROOT, "install-manifest.json"), "rb") as f:
            listed = {e["path"]: e["sha256"] for e in json.loads(f.read().decode("utf-8"))["files"]}
        self.assertEqual({p: listed[p] for p in self.fixture()["files"]}, self.fixture()["files"])

    def test_case5_fixture_is_ascii_with_lf_and_final_newline(self):
        with open(rr.FIXTURE, "rb") as f:
            raw = f.read()
        # core.autocrlf: el checkout puede dejar CRLF; se normaliza antes de comparar.
        norm = raw.replace(b"\r\n", b"\n")
        self.assertTrue(norm.isascii())
        self.assertTrue(norm.endswith(b"\n"))
        self.assertEqual(norm, rr.fixture_bytes(rr.repo_hashes()))

    def test_write_refuses_on_an_already_renamed_repository(self):
        # Tras T7 los roles vivos ya son los nuevos: --write se niega con el mensaje fijo y no escribe.
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "fixture.json")
            with mock.patch.object(rr, "FIXTURE", target), mock.patch.object(sys, "stderr", io.StringIO()) as err:
                self.assertEqual(rr.main(["--write"]), 1)
            self.assertFalse(os.path.exists(target))
            self.assertEqual(err.getvalue(), rr.MSG_REFUSED + "\n")
            with mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(rr.main([]), 2)

    def test_case5_a_changed_byte_or_name_changes_the_hashes(self):
        fixture = self.fixture()["files"]
        for path, raw in rr.repo_texts().items():
            with self.subTest(path=path):
                self.assertNotEqual(bm.canonical_sha256(raw + b" "), fixture[path])
                self.assertNotEqual(bm.canonical_sha256(raw.replace(b"\n", b"\n ", 1)), fixture[path])
        swapped = rr.repo_texts()["agents/%s.md" % DEVELOPER].replace(DEVELOPER.encode(), ANALYST.encode())
        self.assertNotEqual(bm.canonical_sha256(swapped), fixture["agents/%s.md" % DEVELOPER])

    def test_case5_hashes_are_canonical_sha256_of_lf_bytes(self):
        data = self.fixture()["files"]
        for path, raw in rr.repo_texts().items():
            with self.subTest(path=path):
                self.assertEqual(bm.canonical_sha256(raw), data[path])
                self.assertEqual(bm.canonical_sha256(raw.replace(b"\n", b"\r\n")), data[path])


class AssumptionsFiveToSeven(unittest.TestCase):
    """Caso 6: supuestos 5, 6 y 7 del plan."""

    def test_case6_assumption5_manifest_is_sorted_and_the_new_order_holds(self):
        paths = bm.managed_files(ar.ROOT)
        self.assertEqual(paths, sorted(paths))
        with open(os.path.join(ar.ROOT, "install-manifest.json"), "rb") as f:
            listed = [e["path"] for e in json.loads(f.read().decode("utf-8"))["files"]]
        self.assertEqual(listed, sorted(listed))
        self.assertEqual(listed, paths)
        agents = [p for p in paths if p.startswith("agents/")]
        self.assertEqual(agents[0], "agents/anubis.md")
        self.assertEqual(agents, ["agents/%s.md" % n for n in sorted(NEW_NAMES + [PLANNER])])
        self.assertEqual(len(paths), 12)

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
    """Caso 18: hooks:, tools:, model: y color: fijados como datos antes del cambio (por nombre anterior)."""

    def frozen_by_new_name(self):
        return {rr.RENAME.get(old, old): parts for old, parts in rr.frozen_frontmatter().items()}

    def test_case18_frozen_data_equals_the_repository_now(self):
        frozen = rr.frozen_frontmatter()
        self.assertEqual(sorted(frozen), sorted(set(rr.RENAME) | {PLANNER}))
        by_new = self.frozen_by_new_name()
        self.assertEqual(sorted(by_new), sorted(ar.roles()))
        for role in ar.roles():
            with self.subTest(role=role):
                self.assertEqual(by_new[role], rr.frontmatter_parts(ar.repo_text("agents/%s.md" % role)))

    def test_case18_the_guards_are_as_documented(self):
        modes = {role: [l.split("agent_guard.py\" ")[1].rstrip("'") for l in parts["hooks"] if "agent_guard.py" in l]
                 for role, parts in self.frozen_by_new_name().items()}
        self.assertEqual(modes, {PLANNER: [], REVIEWER: ["readonly --allow-temp"], DEBUGGER: ["readonly --allow-temp"],
                                 DEVELOPER: [], ANALYST: [], RESEARCHER: [], WRITER: [],
                                 QA: ["tests-only"], SECURITY: ["readonly --allow-temp"]})

    def test_case18_the_repository_texts_keep_the_frozen_lines(self):
        texts = rr.repo_texts()
        for role, parts in self.frozen_by_new_name().items():
            with self.subTest(role=role):
                got = rr.frontmatter_parts(texts["agents/%s.md" % role].decode("iso-8859-1"))
                self.assertEqual(got, parts)

    def test_case18_a_changed_line_is_detected(self):
        frozen = self.frozen_by_new_name()
        text = ar.repo_text("agents/%s.md" % QA).replace("tests-only", "readonly --allow-temp")
        self.assertNotEqual(rr.frontmatter_parts(text), frozen[QA])
        text = ar.repo_text("agents/%s.md" % DEVELOPER).replace("model: sonnet", "model: opus")
        self.assertNotEqual(rr.frontmatter_parts(text), frozen[DEVELOPER])

    def test_case18_the_hook_script_is_unchanged(self):
        with open(os.path.join(ROOT, "hooks", "agent_guard.py"), "rb") as f:
            self.assertEqual(bm.canonical_sha256(f.read()), HOOK_SHA256)
        with open(os.path.join(ROOT, "install-manifest.json"), "rb") as f:
            listed = {e["path"]: e["sha256"] for e in json.loads(f.read().decode("utf-8"))["files"]}
        self.assertEqual(listed["hooks/agent_guard.py"], HOOK_SHA256)


# Celdas de la tabla de niveles fijadas antes del cambio (caso 17: las 24 celdas no cambian, solo el nombre de la fila).
LEVEL_CELLS = {
    4: {PLANNER: ("opus", "-"), DEVELOPER: ("sonnet", "-"), QA: ("sonnet", "-"), WRITER: ("sonnet", "-"),
        RESEARCHER: ("sonnet", "-"), ANALYST: ("haiku", "-")},
    3: {PLANNER: ("opus", "medium"), DEVELOPER: ("sonnet", "-"), QA: ("sonnet", "-"), WRITER: ("sonnet", "medium"),
        RESEARCHER: ("sonnet", "-"), ANALYST: ("haiku", "-")},
    2: {PLANNER: ("sonnet", "medium"), DEVELOPER: ("sonnet", "medium"), QA: ("sonnet", "-"),
        WRITER: ("sonnet", "low"), RESEARCHER: ("sonnet", "medium"), ANALYST: ("haiku", "-")},
    1: {PLANNER: ("sonnet", "medium"), DEVELOPER: ("sonnet", "low"), QA: ("sonnet", "medium"),
        WRITER: ("haiku", "medium"), RESEARCHER: ("sonnet", "low"), ANALYST: ("haiku", "-")},
}


class RenamedRepository(unittest.TestCase):
    """Caso 17: el repositorio con los nombres nuevos es coherente en todas sus tablas."""

    def test_case17_agents_dir_has_the_nine_new_names_and_none_of_the_old(self):
        listed = sorted(f for f in os.listdir(lr.AGENTS_DIR))
        self.assertEqual(listed, ["%s.md" % n for n in nm.ROLES])
        self.assertEqual(len(listed), 9)
        for old in rr.RENAME:
            self.assertFalse(os.path.exists(os.path.join(lr.AGENTS_DIR, old + ".md")), old)

    def test_case17_name_line_equals_the_file_name(self):
        for role in nm.ROLES:
            with self.subTest(role=role):
                front = ar.repo_text("agents/%s.md" % role).split("\n---\n")[0].split("\n")
                self.assertEqual([l for l in front if l.startswith("name:")], ["name: " + role])

    def test_case17_install_lists_equal_the_reference(self):
        self.assertEqual(lr.read_ps_list("AliasRoles"), nm.ROLES)
        self.assertEqual(lr.read_ps_list("LevelAgents"), nm.LEVEL_ROLES)
        rows = lr.read_level_rows()
        self.assertEqual(len(rows), 24)
        self.assertEqual({agent for _l, agent, _m, _e in rows}, set(nm.LEVEL_ROLES))
        self.assertEqual(set(nm.FIXED) & {agent for _l, agent, _m, _e in rows}, set())

    def test_case17_the_24_cells_are_the_ones_from_before_the_change(self):
        script = lr.read_script_table()
        readme = lr.read_readme_table()
        want = {(level, role): cell for level, row in LEVEL_CELLS.items() for role, cell in row.items()}
        self.assertEqual(len(want), 24)
        self.assertEqual(script, want)
        self.assertEqual({k: v for k, v in readme.items() if k[0] != 5}, want)
        self.assertEqual({agent for level, agent in readme if level == 5} - set(nm.ROLES), set())

    def test_case17_manifest_paths_and_hashes(self):
        with open(os.path.join(ROOT, "install-manifest.json"), "rb") as f:
            listed = {e["path"]: e["sha256"] for e in json.loads(f.read().decode("utf-8"))["files"]}
        self.assertEqual(sorted(listed), sorted(["agents/%s.md" % r for r in nm.ROLES]
                                                + ["docs/agentes.md", "hooks/agent_guard.py", "rules/agentes.md"]))
        for path, digest in rr.repo_hashes().items():
            self.assertEqual(listed[path], digest, path)

    def test_case17_brand_data_and_usage_report_list_the_new_names(self):
        self.assertEqual(sorted(a[0] for a in AGENTS), nm.ROLES)
        self.assertEqual(sorted(ur.SYNCLAYER_AGENTS), nm.ROLES)

    def test_case17_the_guards_are_the_same_modes_on_the_same_agents(self):
        for role in nm.ROLES:
            with self.subTest(role=role):
                parts = rr.frontmatter_parts(ar.repo_text("agents/%s.md" % role))
                found = {l.split("agent_guard.py\" ")[1].rstrip("'") for l in parts["hooks"] if "agent_guard.py" in l}
                self.assertEqual(found, {nm.GUARDED[role]} if role in nm.GUARDED else set())


class LegacyTable(unittest.TestCase):
    """Caso 20, parte estatica: $LegacyRoles real y la clave vieja."""

    def test_case20_legacy_roles_real_equals_the_reference(self):
        self.assertEqual(lr.read_ps_list("LegacyRoles"), ["%s|%s" % (o, n) for o, n in rr.RENAME.items()])
        self.assertEqual(lr.read_ps_list("LegacyRoles"), ["%s|%s" % (o, n) for o, n in nm.LEGACY.items()])
        self.assertEqual(ar.legacy(), rr.RENAME)

    def test_case20_an_old_key_in_aliases_names_both_roles_and_not_the_value(self):
        for old, new in rr.RENAME.items():
            with self.subTest(old=old):
                reason = ar.validate_table({old: "secreto"})
                self.assertEqual(reason, "el rol %s ahora se llama %s: cambia la clave en aliases" % (old, new))
                self.assertNotIn("secreto", reason)

    def test_case20_old_names_as_alias_values_are_valid(self):
        self.assertIsNone(ar.validate_table({new: old for old, new in rr.RENAME.items()}))


class UsageReportNames(unittest.TestCase):
    """Caso 21: los nueve nuevos y los ocho anteriores se clasifican como SyncLayer (los goldens no cambian)."""

    def test_case21_new_and_old_names_classify_as_synclayer(self):
        for name in nm.ROLES + OLD_ROLES:
            with self.subTest(name=name):
                self.assertEqual(ur.classify_agent(name), (name, "SyncLayer"))

    def test_case21_the_lists_are_closed_and_disjoint(self):
        self.assertEqual(ur.SYNCLAYER_AGENTS, frozenset(nm.ROLES))
        self.assertEqual(ur.SYNCLAYER_LEGACY_AGENTS, frozenset(rr.RENAME))
        self.assertEqual(ur.SYNCLAYER_AGENTS & ur.SYNCLAYER_LEGACY_AGENTS, frozenset())

    def test_case21_other_spellings_stay_unknown(self):
        for name in ("Heimdall", "SINDRI", "sindri ", "hector\n", "Salomon", "zeta-uno"):
            with self.subTest(name=name):
                self.assertEqual(ur.classify_agent(name), ("(otro agente)", "otros"))


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
        # Se compara el CONJUNTO de modos de guarda de cada agente, no solo el primero que aparezca.
        modes = {}
        for role in nm.ROLES:
            parts = rr.frontmatter_parts(ar.repo_text("agents/%s.md" % role))
            found = {l.split("agent_guard.py\" ")[1].rstrip("'") for l in parts["hooks"] if "agent_guard.py" in l}
            if found:
                modes[role] = found
        self.assertEqual(modes, {role: {mode} for role, mode in nm.GUARDED.items()})

    def test_legacy_is_the_rename_table(self):
        self.assertEqual(nm.LEGACY, rr.RENAME)
        self.assertEqual(sorted(nm.LEGACY.values()), sorted(set(nm.ROLES) - {PLANNER}))
        self.assertEqual(set(nm.LEGACY) & set(nm.ROLES), set())


# --- caso 7: ningun nombre literal en las pruebas parametrizadas ---

INSTALL_FILE = "test_install.py"

PARAMETRIZED = ("test_aliases.py", "aliases_ref.py", "test_levels.py", "levels_ref.py", "test_plans.py",
                "plans_ref.py", "test_manifest.py", "test_phase5_docs.py", "test_rename.py", "test_brand_agents.py",
                "test_install.py")
# Se buscan como subcadena, sin distinguir mayusculas: los nombres anteriores (en todos los archivos) y los nombres
# vigentes (en todos salvo test_rename.py, que los lista a proposito: NEW_NAMES, MUTATED, el caso 17).
# Lista cerrada de excepciones: identificadores de Python que llevan un nombre anterior dentro. Se quitan antes de
# buscar SOLO los tokens de tipo identificador (tokenize), no un literal de cadena que diga lo mismo.
#   - el identificador global de la constante de names.py cuyo nombre en mayusculas es el de un nombre anterior
#     de la constante del depurador de names.py, en cualquier archivo;
#   - el identificador del diccionario de palabras de aliases_ref.py (<ROL>_WORDS; nombre fijado por el plan, T2 y
#     T4) en aliases_ref.py y test_install.py.
# Ademas se quitan antes de buscar las palabras espanolas con la subcadena de un nombre anterior (escribe...).
GLOBAL_IDENTIFIERS = sorted(n for n in dir(nm) if n.isupper() and n.lower() in rr.RENAME)
_WORDS_IDENTIFIERS = sorted(n for n in dir(ar) if any(o in n.lower() for o in rr.RENAME))
ALLOWED_IDENTIFIERS = {"aliases_ref.py": _WORDS_IDENTIFIERS, "test_install.py": _WORDS_IDENTIFIERS}
_SPANISH_WORDS = re.compile("escriben|escribe|describe|reescribe|sobrescribe", re.I)


def strip_identifiers(text, identifiers):
    """El texto sin los tokens NAME de Python que sean uno de `identifiers` (reemplazados por espacios del mismo
    largo). Un literal de cadena o un comentario con el mismo texto se conserva."""
    lines = text.split("\n")
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.NAME and tok.string in identifiers:
            row, col = tok.start
            line = lines[row - 1]
            lines[row - 1] = line[:col] + " " * len(tok.string) + line[tok.end[1]:]
    return "\n".join(lines)


def scanned_names(file_name):
    """Nombres que no pueden aparecer literales en `file_name`: los anteriores y, salvo en test_rename.py, los vigentes."""
    names = set(rr.RENAME)
    if file_name != "test_rename.py":
        names |= set(nm.ROLES)
    return sorted(names)


def name_hits(text, names=None, identifiers=()):
    """[(linea, nombre)] de los nombres hallados como subcadena (cualquier capitalizacion), tras quitar las palabras
    espanolas con la subcadena de un nombre anterior y los identificadores indicados."""
    names = scanned_names("") if names is None else names
    text = strip_identifiers(_SPANISH_WORDS.sub("", text), identifiers)
    hits = []
    for lineno, line in enumerate(text.split("\n"), 1):
        low = line.lower()
        hits += [(lineno, n) for n in names if n in low]
    return hits


class Parametrization(unittest.TestCase):
    """Caso 7: parametrizacion sin cambio de comportamiento."""

    def test_case7_no_name_literal_outside_the_closed_list(self):
        for name in PARAMETRIZED:
            with self.subTest(file=name):
                with open(os.path.join(HERE, name), "rb") as f:
                    text = f.read().decode("utf-8")
                for ident in ALLOWED_IDENTIFIERS.get(name, []):
                    self.assertIn(ident, text)   # la excepcion existe: si deja de usarse, se retira
                identifiers = GLOBAL_IDENTIFIERS + ALLOWED_IDENTIFIERS.get(name, [])
                found = [(n, l) for l, n in name_hits(text, scanned_names(name), identifiers)]
                self.assertEqual(found, [], "nombre literal en %s" % name)

    def test_case7_the_closed_list_is_what_it_says(self):
        self.assertEqual(len(GLOBAL_IDENTIFIERS), 1)
        self.assertEqual(len(_WORDS_IDENTIFIERS), 1)
        self.assertEqual(GLOBAL_IDENTIFIERS, [OLD_OF[DEBUGGER].upper()])
        self.assertTrue(set(ALLOWED_IDENTIFIERS) <= set(PARAMETRIZED))

    def test_case7_the_scan_detects_literals_and_skips_spanish_words(self):
        old = ["alfa", "delta", "tau"]
        self.assertEqual(name_hits("x\nuna Alfa y DELTA\n", old), [(2, "alfa"), (2, "delta")])
        self.assertEqual(name_hits("alfa_x y xtau", old), [(1, "alfa"), (1, "tau")])
        self.assertEqual(name_hits("escribe describe reescribe sobrescribe Escriben", [OLD_OF[WRITER]]), [])
        self.assertEqual(name_hits("%s %s" % (OLD_OF[WRITER].capitalize(), OLD_OF[WRITER].upper()), [OLD_OF[WRITER]]),
                         [(1, OLD_OF[WRITER])])

    def test_case7_only_identifier_tokens_are_removed_not_string_literals(self):
        # Pendiente 1 de T2: un literal de cadena o un comentario con el texto del identificador si se ve.
        self.assertEqual(name_hits("x = TAU_W + a.TAU_W", ["tau"], ["TAU_W"]), [])
        self.assertEqual(name_hits("x = 'TAU_W'", ["tau"], ["TAU_W"]), [(1, "tau")])
        self.assertEqual(name_hits('x = "tau"  # TAU_W', ["tau"], ["TAU_W"]), [(1, "tau")])
        self.assertEqual(name_hits("x = 1  # TAU_W", ["tau"], ["TAU_W"]), [(1, "tau")])
        self.assertEqual(name_hits("x = TAU_W\ny = 'tau'", ["tau"], ["TAU_W"]), [(2, "tau")])
        self.assertEqual(name_hits("x = TAU_W", ["tau"], []), [(1, "tau")])

    def test_case7_the_full_scan_covers_test_install_and_is_not_empty(self):
        # test_install.py esta en PARAMETRIZED entero (T3 y T4), sin cortes ni excepciones de nombres: se comprueba
        # que la lista lo incluye y que el texto escaneado trae los extremos del archivo.
        self.assertIn(INSTALL_FILE, PARAMETRIZED)
        with open(os.path.join(HERE, INSTALL_FILE), "rb") as f:
            text = f.read().decode("utf-8")
        self.assertGreater(text.count(chr(10)), 8000)
        # sin quitar el identificador, el escaneo ve contenido real: las unicas lineas con hit son las que lo traen
        ident = ALLOWED_IDENTIFIERS[INSTALL_FILE][0]
        lines = text.split(chr(10))
        expected = sorted(i + 1 for i, l in enumerate(lines) if ident in l or GLOBAL_IDENTIFIERS[0] in l)
        self.assertTrue(expected)
        self.assertEqual(sorted({ln for ln, _n in name_hits(text, scanned_names(INSTALL_FILE))}), expected)

    def test_case7_names_py_and_rename_ref_hold_the_names_as_literals(self):
        # names.py define las constantes (nombres vigentes) y LEGACY (anteriores); rename_ref.py guarda la tabla del
        # renombrado: son los unicos sitios donde los nombres van escritos.
        for file_name in ("names.py", "rename_ref.py"):
            with open(os.path.join(HERE, file_name), "rb") as f:
                text = f.read().decode("utf-8")
            self.assertTrue(name_hits(text, sorted(rr.RENAME)), file_name)
        with open(os.path.join(HERE, "names.py"), "rb") as f:
            text = f.read().decode("utf-8")
        self.assertTrue(name_hits(text, sorted(rr.RENAME.values())))


# --- caso 8: mutacion de control ---

_CONST_IDENT = GLOBAL_IDENTIFIERS[0]   # el identificador de names.py que coincide con un nombre anterior
MUTATED = {"PLANNER": "kappa", "ANALYST": "lambda", "RESEARCHER": "sigma", "DEVELOPER": "omega", "QA": "tau",
           "REVIEWER": "rho", "SECURITY": "phi", _CONST_IDENT: "chi", "WRITER": "psi"}

# Pruebas puras (no leen install.ps1, agents/ ni la documentacion): deben pasar con otros nueve nombres.
# Solo las de test_aliases dependen de los nombres (alias, formas, transformacion). Las de test_levels y test_plans
# (TableComparison.test_promise_guard..., RealAgentsRender.test_reference_renderer_edge_cases, LeftBoundary y
# SinglePass) no usan `names`: pasan con cualquier nombre y por eso NO prueban la mutacion; se listan solo para
# comprobar que los modulos se importan con `names` cambiado (pendiente 3 de T2).
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
    (clases o Clase.metodo). Devuelve (resultado, modulo, salida). Restaura sys.modules y sys.path al terminar."""
    saved = {key: sys.modules.get(key) for key in _FRESH}
    saved_path = list(sys.path)
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
        sys.path[:] = saved_path
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
        self.assertEqual(mod.FIXED, [MUTATED[k] for k in ("REVIEWER", "SECURITY", _CONST_IDENT)])

    def test_case8_control_a_test_that_reads_the_repository_fails(self):
        # Que el control no sea vacuo: una prueba que compara con install.ps1 si falla con los nombres mutados.
        result, _mod, _out = run_with_mutated_names(
            "test_aliases", ["ClosedLists.test_case1_alias_roles_match_agents_dir"])
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(result.wasSuccessful())
        result, _mod, _out = run_with_mutated_names("test_plans", ["RealRepository"])
        self.assertFalse(result.wasSuccessful())

    def test_case8_sys_modules_and_sys_path_are_restored(self):
        before = {key: sys.modules.get(key) for key in _FRESH}
        path_before = list(sys.path)
        run_with_mutated_names("test_plans", PURE["test_plans"])
        self.assertIs(sys.modules["names"], nm)
        for key in _FRESH:
            self.assertIs(sys.modules.get(key), before[key])
        self.assertEqual(sys.path, path_before)
        self.assertEqual(nm.ROLES, sorted(nm.ROLES))
        self.assertNotIn(nm.PLANNER, MUTATED.values())


if __name__ == "__main__":
    unittest.main()
