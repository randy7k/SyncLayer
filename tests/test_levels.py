"""Pruebas de la tabla de niveles (Fase 3, T1): la de install.ps1 ($LevelRows), la del README y las
reglas R1 a R5 con las que se construyo. Desde T4 la tabla se usa para renderizar los niveles 1 a 4 (ConvertTo-LevelBytes).

Casos del plan: 1 (install.ps1 contra README), 2 (lista cerrada), 3 (R2, R3, R4), 4 (nivel 5 contra
agents/*.md), 5 (los seis agentes reales son renderizables) y 40 (install.ps1 estatico). Las
comprobaciones son funciones que reciben la tabla: unas pruebas las alimentan con tablas
mutadas para demostrar que cada regla detecta su violacion. Solo una clase usa PowerShell.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

import build_manifest as bm  # noqa: E402
import levels_ref as lr  # noqa: E402
import names  # noqa: E402  (fuente unica de los nombres de rol)
from names import ANALYST, DEVELOPER, PLANNER, QA, RESEARCHER, REVIEWER, WRITER  # noqa: E402

POWERSHELL = shutil.which("powershell")
AGENTS = list(names.LEVEL_ROLES)
FIXED = list(names.FIXED)
MODEL_ORDER = {"haiku": 0, "sonnet": 1, "opus": 2, "claude-fable-5-2": 3}
EFFORT_ORDER = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4, "-": 5}
OFFICIAL_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
ALIASES = {"opus", "sonnet", "haiku"}


PROMISE_PATTERNS = [r"\d+\s*%", r"reduc", r"abarat", r"ahorra\b", r"ahorrar", r"garantiz",
                    r"gratis", r"mejora\w*\s+(la\s+)?calidad", r"mejores?\s+calidad", r"(baja|recorta|rebaja)\w*\s+(el\s+)?costos?",
                    r"más\s+barat"]


def promise_hits(text):
    """Patrones de promesa de ahorro que aparecen en el texto (guarda reutilizable para la
    documentacion de T7). El texto honesto «no promete ahorro de tokens ni de costo» no los activa."""
    flat = " ".join(text.split()).lower()
    return [p for p in PROMISE_PATTERNS if re.search(p, flat)]


# --- comprobaciones sobre una tabla {(nivel, agente): (modelo, esfuerzo)} ---

def cells_1_to_4(table):
    return {k: v for k, v in table.items() if 1 <= k[0] <= 4}


def table_differences(a, b):
    """Celdas distintas o presentes en una sola tabla (caso 1)."""
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def rank(cell):
    return (MODEL_ORDER[cell[0]], EFFORT_ORDER[cell[1]])


def r2_violations(table):
    """R2: por agente, al bajar un nivel (5 a 1) el par no sube (orden lexicografico)."""
    bad = []
    for agent in AGENTS:
        for level in range(5, 1, -1):
            if rank(table[(level - 1, agent)]) > rank(table[(level, agent)]):
                bad.append((agent, level, level - 1))
    return bad


def r3_violations(table):
    return sorted(k for k, (model, effort) in table.items() if model == "haiku" and effort == "low")


def r4_violations(table):
    """R4: niveles contiguos (1 a 5) difieren en al menos un agente."""
    return [(level, level - 1) for level in range(5, 1, -1)
            if all(table[(level, a)] == table[(level - 1, a)] for a in AGENTS)]


def r5_violations(table):
    """R5: niveles 1 a 4 con solo alias y los cinco esfuerzos oficiales (o sin effort:)."""
    return sorted(k for k, (model, effort) in cells_1_to_4(table).items()
                  if model not in ALIASES or (effort != "-" and effort not in OFFICIAL_EFFORTS))


def single_assignment_problems(text):
    """Variables de la tabla que no se asignan exactamente una vez en install.ps1."""
    text = text.replace("\r\n", "\n")
    return [n for n in ("LevelRows", "LevelAgents", "AllowedModels", "AllowedEfforts")
            if len(re.findall(r"\$" + n + r"\s*(\[[^\]]*\]\s*)?\+?=", text)) != 1]


def full_table():
    """Niveles 1 a 4 de install.ps1 mas el nivel 5 del README."""
    table = dict(lr.read_script_table())
    table.update({k: v for k, v in lr.read_readme_table().items() if k[0] == 5})
    return table


class TableComparison(unittest.TestCase):

    def test_case1_install_ps1_table_equals_readme_table(self):
        script = lr.read_script_table()
        readme = cells_1_to_4(lr.read_readme_table())
        self.assertEqual(len(script), 24)
        self.assertEqual(len(readme), 24)
        self.assertEqual(table_differences(script, readme), [])

    def test_case1_one_changed_cell_in_one_place_fails(self):
        # Mutaciones: una celda cambiada solo en install.ps1 o solo en el README se detecta. La celda
        # sale de la tabla leida: un cambio legitimo hecho en los dos sitios no rompe esta prueba.
        ps = lr.script_text()
        md = lr._read_text(lr.README)
        self.assertEqual(table_differences(lr.read_script_table(ps), cells_1_to_4(lr.read_readme_table(md))), [])
        level, agent, model, effort = lr.read_level_rows(ps)[0]
        other = "low" if effort != "low" else "medium"
        old_row = "'%d|%s|%s|%s'" % (level, agent, model, effort)
        ps_mut = ps.replace(old_row, "'%d|%s|%s|%s'" % (level, agent, model, other))
        self.assertNotEqual(ps_mut, ps)
        self.assertEqual(
            table_differences(lr.read_script_table(ps_mut), cells_1_to_4(lr.read_readme_table(md))),
            [(level, agent)])
        nl = chr(10)
        lines = md.split(nl)
        start = lines.index(lr.BEGIN_MARK)
        i = next(n for n in range(start, len(lines)) if lines[n].startswith("| `%s` |" % agent))
        cells = lines[i].strip().strip("|").split("|")
        cells[1 + [5, 4, 3, 2, 1].index(level)] = " `%s`, `%s` " % (model, other)
        lines[i] = "|" + "|".join(cells) + "|"
        md_mut = nl.join(lines)
        self.assertNotEqual(md_mut, md)
        self.assertEqual(
            table_differences(lr.read_script_table(ps), cells_1_to_4(lr.read_readme_table(md_mut))),
            [(level, agent)])

    def test_readme_table_has_five_levels_and_six_agents(self):
        readme = lr.read_readme_table()
        self.assertEqual(sorted(readme), sorted((l, a) for l in range(1, 6) for a in AGENTS))

    def test_readme_section_is_not_a_savings_promise(self):
        md = lr._read_text(lr.README)
        section = md.split("## Niveles", 1)[1].split(chr(10) + "## ", 1)[0]
        flat = " ".join(section.split())
        self.assertIn("orden razonado, no una medición", flat)
        self.assertEqual(promise_hits(section), [])

    def test_promise_guard_catches_savings_claims(self):
        # Mutaciones: cada frase de promesa debe ser detectada por la guarda; el texto honesto, no.
        for bad in ("Reduce el costo un 40 %.", "Ahorra tokens.", "Ahorrar costo.", "Es más barato.",
                    "Garantizamos menos gasto.", "Es gratis.", "Mejora la calidad.", "Mejores calidad.",
                    "Baja el costo.", "Un 30% menos.", "Abarata la factura."):
            with self.subTest(bad=bad):
                self.assertTrue(promise_hits(bad), bad)
        self.assertEqual(promise_hits("No promete ahorro de tokens ni de costo."), [])


class ClosedList(unittest.TestCase):

    def test_case2_rows_and_lists(self):
        rows = lr.read_level_rows()
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({(r[0], r[1]) for r in rows}), 24)
        self.assertEqual(lr.read_ps_list("LevelAgents"), AGENTS)
        self.assertEqual(lr.read_ps_list("AllowedModels"), ["opus", "sonnet", "haiku"])
        self.assertEqual(lr.read_ps_list("AllowedEfforts"), ["-", "low", "medium", "high", "xhigh", "max"])
        models = set(lr.read_ps_list("AllowedModels"))
        efforts = set(lr.read_ps_list("AllowedEfforts"))
        for level, agent, model, effort in rows:
            self.assertIn(level, (1, 2, 3, 4))
            self.assertIn(agent, AGENTS)
            self.assertIn(model, models)
            self.assertIn(effort, efforts)
        self.assertEqual({r[0] for r in rows}, {1, 2, 3, 4})

    def test_case2_fixed_agents_are_not_in_the_table(self):
        names = {r[1] for r in lr.read_level_rows()} | set(lr.read_ps_list("LevelAgents"))
        names |= {a for (_l, a) in lr.read_readme_table()}
        for fixed in FIXED:
            self.assertNotIn(fixed, names)

    def test_case2_each_table_variable_is_assigned_once(self):
        # Una reasignacion posterior dejaria a las pruebas leyendo la tabla original.
        text = lr.script_text()
        self.assertEqual(single_assignment_problems(text), [])
        nl = chr(10)
        mutated = text.replace(nl + "function Get-LevelTableProblem",
                               nl + "$LevelRows[3] = '4|" + DEVELOPER + "|opus|max'" + nl + "function Get-LevelTableProblem")
        self.assertNotEqual(mutated, text)
        self.assertEqual(single_assignment_problems(mutated), ["LevelRows"])
        mutated = text + nl + "$AllowedModels += 'gpt'" + nl
        self.assertEqual(single_assignment_problems(mutated), ["AllowedModels"])
        mutated = text + nl + "$LevelAgents = @('" + REVIEWER + "')" + nl
        self.assertEqual(single_assignment_problems(mutated), ["LevelAgents"])

    def test_case2_duplicate_row_is_rejected_by_the_reader(self):
        ps = lr.script_text().replace("'1|%s|haiku|-'" % ANALYST, "'1|%s|sonnet|low'" % RESEARCHER)
        with self.assertRaises(ValueError):
            lr.read_script_table(ps)

    def test_reader_handles_crlf(self):
        ps = lr.script_text().replace("\n", "\r\n")
        self.assertEqual(lr.read_script_table(ps), lr.read_script_table())
        md = lr._read_text(lr.README).replace("\n", "\r\n")
        self.assertEqual(lr.read_readme_table(md), lr.read_readme_table())


class Rules(unittest.TestCase):

    def setUp(self):
        self.table = full_table()

    def test_case3_r2_no_cell_goes_up_when_the_level_goes_down(self):
        self.assertEqual(r2_violations(self.table), [])

    def test_case3_r3_no_haiku_with_low(self):
        self.assertEqual(r3_violations(self.table), [])

    def test_case3_r4_contiguous_levels_differ(self):
        self.assertEqual(r4_violations(self.table), [])

    def test_r5_only_aliases_and_official_efforts(self):
        self.assertEqual(r5_violations(self.table), [])

    def test_case4_r1_level_5_is_the_repository_frontmatter(self):
        readme = lr.read_readme_table()
        for agent in AGENTS:
            fm = lr.repo_frontmatter(agent)
            models = [l for l in fm if l.startswith("model:")]
            self.assertEqual(len(models), 1, agent)
            self.assertEqual(readme[(5, agent)][0], models[0][len("model:"):].strip(), agent)
            self.assertFalse([l for l in fm if l.startswith("effort:")], agent)
            self.assertEqual(readme[(5, agent)][1], "-", agent)
        for path in glob.glob(os.path.join(lr.AGENTS_DIR, "*.md")):
            name = os.path.splitext(os.path.basename(path))[0]
            self.assertFalse([l for l in lr.repo_frontmatter(name) if l.startswith("effort:")], name)

    def test_case4_fixed_agents_stay_opus_without_effort(self):
        for name in FIXED:
            fm = lr.repo_frontmatter(name)
            self.assertIn("model: opus", fm)
            self.assertFalse([l for l in fm if l.startswith("effort:")], name)

    # --- mutaciones: romper cada regla hace fallar su comprobacion ---

    def mutated(self, key, cell):
        table = dict(self.table)
        table[key] = cell
        return table

    def test_mutation_r2(self):
        self.assertTrue(r2_violations(self.mutated((3, DEVELOPER), ("sonnet", "low"))))
        self.assertTrue(r2_violations(self.mutated((4, PLANNER), ("sonnet", "medium"))))
        self.assertTrue(r2_violations(self.mutated((1, ANALYST), ("sonnet", "-"))))

    def test_mutation_r3(self):
        self.assertTrue(r3_violations(self.mutated((1, WRITER), ("haiku", "low"))))

    def test_mutation_r4(self):
        table = dict(self.table)
        for agent in AGENTS:
            table[(3, agent)] = table[(4, agent)]
        self.assertTrue(r4_violations(table))

    def test_mutation_r5(self):
        self.assertTrue(r5_violations(self.mutated((2, RESEARCHER), ("claude-fable-5-2", "-"))))
        self.assertTrue(r5_violations(self.mutated((2, RESEARCHER), ("sonnet", "ultra"))))


class RealAgentsRender(unittest.TestCase):

    def real_bytes(self, agent):
        with open(os.path.join(lr.AGENTS_DIR, agent + ".md"), "rb") as f:
            return f.read().replace(b"\r\n", b"\n")

    def test_case5_real_agents_render_at_every_level(self):
        table = lr.read_script_table()
        for agent in AGENTS:
            src = self.real_bytes(agent)
            src_lines = src.decode("iso-8859-1").split("\n")
            close_in = src_lines.index("---", 1)
            for level in (1, 2, 3, 4):
                with self.subTest(agent=agent, level=level):
                    model, effort = table[(level, agent)]
                    out = lr.render_expected(src, model, effort).decode("iso-8859-1").split("\n")
                    extra = 1 if effort != "-" else 0
                    close_out = out.index("---", 1)
                    self.assertEqual(out[0], "---")
                    self.assertEqual(len(out), len(src_lines) + extra)
                    # Las lineas que ya no estan son solo model: o effort:; las nuevas, solo las de la celda.
                    gone = [l for l in src_lines if l not in out]
                    new = [l for l in out if l not in src_lines]
                    self.assertTrue(all(l.startswith(("model:", "effort:")) for l in gone), gone)
                    self.assertTrue(all(l.startswith(("model:", "effort:")) for l in new), new)
                    fm_out = out[1:close_out]
                    self.assertEqual([l for l in fm_out if l.startswith("model:")], ["model: " + model])
                    efforts = [l for l in fm_out if l.startswith("effort:")]
                    self.assertEqual(efforts, [] if effort == "-" else ["effort: " + effort])
                    # El resto del frontmatter y el cuerpo, identicos y en el mismo orden.
                    keep = lambda ls: [l for l in ls if not l.startswith(("model:", "effort:"))]
                    self.assertEqual(keep(fm_out), keep(src_lines[1:close_in]))
                    self.assertEqual(out[close_out:], src_lines[close_in:])

    def test_case5_qa_hooks_block_is_identical(self):
        src = self.real_bytes(QA)
        text = src.decode("iso-8859-1")
        self.assertIn("\nhooks:", text)

        def hooks(t):
            lines = t.split("\n")
            return lines[lines.index("hooks:"):lines.index("---", 1)]

        for level in (1, 2, 3, 4):
            model, effort = lr.read_script_table()[(level, QA)]
            out = lr.render_expected(src, model, effort).decode("iso-8859-1")
            self.assertEqual(hooks(out), hooks(text), level)

    def test_case5_effort_is_inserted_right_after_model(self):
        out = lr.render_expected(self.real_bytes(DEVELOPER), "sonnet", "low").decode("iso-8859-1").split("\n")
        i = out.index("model: sonnet")
        self.assertEqual(out[i + 1], "effort: low")

    def test_reference_renderer_edge_cases(self):
        base = b"---\nname: x\nmodel: sonnet\n---\ncuerpo\nmodel: otra\n"
        # Celda igual al origen: bytes identicos.
        self.assertEqual(lr.render_expected(base, "sonnet", "-"), base)
        # effort: presente y celda con valor: se sustituye en su sitio; con '-' se conserva.
        withe = b"---\nmodel: sonnet\neffort: high\n---\n"
        self.assertEqual(lr.render_expected(withe, "haiku", "medium"), b"---\nmodel: haiku\neffort: medium\n---\n")
        self.assertEqual(lr.render_expected(withe, "haiku", "-"), b"---\nmodel: haiku\neffort: high\n---\n")
        # model: indentado no cuenta (la sangria va despues de model:; antes se rechaza: hueco envolvente).
        indented = b"---\nmodel: sonnet\nhooks:\n  model: z\n---\n"
        self.assertEqual(lr.render_expected(indented, "opus", "-"),
                         b"---\nmodel: opus\nhooks:\n  model: z\n---\n")
        with self.assertRaises(ValueError):
            lr.render_expected(b"---\nhooks:\n  model: z\nmodel: sonnet\n---\n", "opus", "-")
        for bad in (b"---\nname: x\n---\n", b"---\nmodel: a\nmodel: b\n---\n",
                    b"---\nmodel: a\neffort: low\neffort: low\n---\n", b"---\nmodel: a\n",
                    b"\xef\xbb\xbf---\nmodel: a\n---\n", b"\n---\nmodel: a\n---\n"):
            with self.assertRaises(ValueError):
                lr.render_expected(bad, "opus", "low")


class StaticInstallScript(unittest.TestCase):
    """Caso 40: install.ps1 sigue en ASCII, sin BOM, sin construcciones prohibidas."""

    def setUp(self):
        with open(lr.SCRIPT, "rb") as f:
            self.raw = f.read()

    def test_case40_ascii_no_bom_no_forbidden_constructs(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual([i for i, b in enumerate(self.raw) if b > 0x7F], [])
        text = self.raw.decode("ascii")
        self.assertNotIn("&&", text)
        self.assertNotIn("??", text)
        self.assertNotIn("*", text)
        self.assertNotRegex(text, r"(?i)invoke-expression|\biex\b")

    def test_case40_paso_markers_are_intact(self):
        text = self.raw.decode("ascii").replace("\r\n", "\n")
        found = re.findall(r"^    # Paso (\d+):", text, re.M)
        self.assertEqual(found, [str(n) for n in range(1, 11)])


@unittest.skipUnless(POWERSHELL, "no hay powershell.exe en el PATH")
class TableValidationAtStartup(unittest.TestCase):
    """La tabla se valida al arrancar: un valor fuera de la lista da exit 1 y no escribe nada."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="sync layer ", ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.src = os.path.join(self.tmp, "origen")
        self.home = os.path.join(self.tmp, "home")
        self.target = os.path.join(self.tmp, "destino")
        os.makedirs(self.src)
        os.makedirs(self.home)
        files = {"agents/alfa.md": b"---\nmodel: sonnet\n---\n", "rules/agentes.md": b"r\n",
                 "hooks/agent_guard.py": b"g\n", "docs/agentes.md": b"d\n"}
        for rel, data in files.items():
            path = os.path.join(self.src, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        with open(os.path.join(self.src, "install-manifest.json"), "wb") as f:
            f.write(bm.render(bm.build_manifest(self.src, sorted(files))).encode("ascii"))

    def run_script(self, text):
        with open(os.path.join(self.src, "install.ps1"), "wb") as f:
            f.write(text.encode("ascii"))
        env = dict(os.environ)
        env.update({"USERPROFILE": self.home, "HOME": self.home})
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
             os.path.join(self.src, "install.ps1"), "-Target", self.target, "-DryRun"],
            cwd=self.tmp, env=env, timeout=120, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")

    def test_real_table_is_accepted(self):
        code, _out, err = self.run_script(lr.script_text())
        self.assertEqual(code, 0, err)
        self.assertNotIn("tabla de niveles", err)

    def test_bad_tables_exit_1_with_a_clear_message(self):
        text = lr.script_text()
        rows = lr.read_level_rows(text)
        lv, ag, mo, ef = rows[0]
        row = "'%d|%s|%s|%s'" % (lv, ag, mo, ef)
        cases = {
            "modelo": (row, "'%d|%s|gpt|%s'" % (lv, ag, ef)),
            "esfuerzo": (row, "'%d|%s|%s|ultra'" % (lv, ag, mo)),
            "agente": (row, "'%d|%s|%s|%s'" % (lv, REVIEWER, mo, ef)),
            "nivel": (row, "'5|%s|%s|%s'" % (ag, mo, ef)),
            "repetida": ("'%d|%s|%s|%s'" % rows[1], row),
            "mal formada": (row, "'%d|%s|%s'" % (lv, ag, mo)),
            "falta una": ("'%d|%s|%s|%s',\n    '%d|%s|%s|%s'\n" % (rows[-2] + rows[-1]),
                          "'%d|%s|%s|%s'\n" % rows[-2]),
        }
        for name, (old, new) in cases.items():
            with self.subTest(caso=name):
                mutated = text.replace(old, new)
                self.assertNotEqual(mutated, text)
                code, _out, err = self.run_script(mutated)
                self.assertEqual(code, 1, err)
                self.assertIn("la tabla de niveles de install.ps1 no es valida", err)
                self.assertTrue(err.isascii(), repr(err))
                self.assertFalse(os.path.exists(self.target))


if __name__ == "__main__":
    unittest.main()
