"""Pruebas de la documentacion de la Fase 5, T7 (comprobaciones estaticas, solo biblioteca estandar).

Casos del plan: 44 (README: seccion «Perfiles por proyecto» con prioridad, `permissions.deny`, `Agent(` y
la marca de «no verificado» junto a `hooks:`; ninguna frase da por hecho que la guarda se hereda o se
pierde), 45 (las secciones nuevas del README pasan `promise_hits`) y 46 (archivos gestionados tras
documentar: inventario de roles, inventario de `docs/plans`, sincronia del manifiesto, doce archivos).
T8 agrega el caso 47 (guia, README, CLAUDE.md y HISTORY.md con `plans_dir` y `--lang`).
Las comprobaciones son funciones que reciben el texto, para poder alimentarlas con textos mutados.
"""

import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import aliases_ref as ar  # noqa: E402
import plans_ref as pr  # noqa: E402
from test_aliases import INVENTORY  # noqa: E402
from test_levels import promise_hits  # noqa: E402

README = os.path.join(ROOT, "README.md")
PROFILES = "Perfiles por proyecto"
PLANS = "Carpeta de planes"
LIMITS = "Límites del instalador"
# Frases de la lista de reglas (L1 a L5) de la seccion de la carpeta de planes.
PLANS_RULE_PHRASES = ("hasta 64 caracteres", "nombre de dispositivo de Windows")
# Frases que darian por hecho la herencia o la perdida de la guarda.
FACT_PATTERNS = [r"\bse\s+hereda\b", r"\bse\s+heredan\b", r"\bhereda\s+(la|el)\b", r"\bse\s+pierde\b",
                 r"\bse\s+pierden\b", r"\bpierde\s+(la|el)\s+(guarda|bloque)", r"\bheredar[aá]\b",
                 r"\bperder[aá]\s+(la|el)\b", r"(?<!«)\bsin\s+(la\s+)?guarda\b",r"\bconserva(n)?\s+(la\s+)?guarda\b",
                 r"\bguarda\s+sigue\b", r"\bmantiene\s+(la\s+)?guarda\b"]
# El matiz debe estar en la MISMA oracion (o fila) que la frase.
HEDGES = ("no verificado", "no esta documentado", "no está documentado", "no hay fusion",
          "no hay fusión")


def read_text(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8").replace("\r\n", "\n")


def section(md, title):
    """Cuerpo de la seccion `## <title...>` hasta la siguiente `## ` (o el final); None si falta."""
    m = re.search(r"^## " + re.escape(title) + r"[^\n]*\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1) if m else None


def profile_problems(md):
    """Problemas de la seccion «Perfiles por proyecto» (caso 44)."""
    sec = section(md, PROFILES)
    if sec is None:
        return ["falta la seccion «%s»" % PROFILES]
    problems = []
    low = sec.lower()
    if not re.search(r"prioridad", low):
        problems.append("falta la prioridad")
    if "permissions.deny" not in sec:
        problems.append("falta `permissions.deny`")
    if "Agent(" not in sec:
        problems.append("falta `Agent(`")
    rows = [l for l in sec.split("\n") if "hooks:" in l and "no verificado" in l.lower()]
    if not rows:
        problems.append("falta «no verificado» junto a `hooks:`")
    # Ninguna frase (parrafo, fila o elemento) afirma la herencia o la perdida de la guarda como hecho.
    for block in re.split(r"\n\s*\n|\n(?=\|)|(?<=[.!?])\s+", sec):
        flat = " ".join(block.split())
        lowered = flat.lower()
        if any(re.search(p, lowered) for p in FACT_PATTERNS) and not any(h in lowered for h in HEDGES):
            problems.append("frase que da por hecho la herencia o la perdida de la guarda: " + flat[:60])
    return problems


def promise_problems(md):
    """Secciones nuevas del README con promesas de ahorro o porcentajes (caso 45)."""
    problems = []
    for title in (PROFILES, PLANS):
        sec = section(md, title)
        if sec is None:
            problems.append("falta la seccion «%s»" % title)
        elif promise_hits(sec):
            problems.append("%s: %s" % (title, promise_hits(sec)))
    return problems


def inventory_problems_of_roles(texts):
    """Inventario de roles del caso 46 sobre {ruta: texto ISO-8859-1} de los once textos transformables."""
    problems = []
    if sorted(texts) != sorted(INVENTORY):
        problems.append("lista de textos distinta")
    for rel, text in sorted(texts.items()):
        counts, other = ar.inventory(text)
        if other:
            problems.append("%s: forma de rol desconocida" % rel)
        if {r: v for r, v in counts.items() if any(v)} != INVENTORY.get(rel):
            problems.append("%s: conteo de roles distinto" % rel)
    return problems


GUIDE = os.path.join(ROOT, "docs", "agentes.md")
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")
HISTORY = os.path.join(ROOT, "HISTORY.md")
USAGE = "Reporte de uso"
GUIDE_PLANS = "**Cambiar la carpeta de planes.**"


def guide_plans_block(md):
    """Apartado «Cambiar la carpeta de planes» de la guia (parrafo en negrita y sus vinetas); None si falta."""
    m = re.search(re.escape(GUIDE_PLANS) + r".*?(?=^## |^### |^\*\*[^\n]*\*\*|\Z)", md, re.S | re.M)
    return m.group(0) if m else None


def guide_problems(md):
    """Problemas de docs/agentes.md (caso 47). Roles y `docs/plans` ya los cubren los inventarios (caso 46)."""
    block = guide_plans_block(md)
    problems = []
    if block is None:
        problems.append("falta el apartado «Cambiar la carpeta de planes»")
    else:
        if "plans_dir" not in block:
            problems.append("guia: falta la clave `plans_dir`")
        if "no verificado" not in block.lower():
            problems.append("guia: falta la marca «no verificado»")
    usage = section(md, USAGE)
    if usage is None:
        problems.append("falta la seccion «%s»" % USAGE)
    elif not any(l.startswith("- ") and "`--lang" in l for l in usage.split("\n")):
        problems.append("guia: falta la vineta de `--lang`")
    return problems


def readme_lang_plans_problems(md):
    """Problemas del README (caso 47): `plans_dir` en su seccion y `--lang` en sinopsis y tabla."""
    problems = []
    plans = section(md, PLANS)
    if plans is None:
        problems.append("falta la seccion «%s»" % PLANS)
    else:
        for needle in ("plans_dir", "-DryRun", "Planes:"):
            if needle not in plans:
                problems.append("README: la carpeta de planes no menciona %s" % needle)
        for needle in PLANS_RULE_PHRASES:
            if needle not in plans:
                problems.append("README: la carpeta de planes no trae la regla «%s»" % needle)
        if not re.search(r"no (está )?verificado", plans.lower()):
            problems.append("README: la carpeta de planes no trae la marca «no verificado»")
    limits = section(md, LIMITS)
    if limits is None:
        problems.append("falta la seccion «%s»" % LIMITS)
    elif "plans_dir" not in limits:
        problems.append("README: «%s» no menciona plans_dir" % LIMITS)
    usage = section(md, USAGE)
    if usage is None:
        problems.append("falta la seccion «%s»" % USAGE)
        return problems
    for sub in ("project", "global"):
        m = re.search(r"usage_report\.py " + sub + r"\b(.*?)(?=usage_report\.py |^```)", usage, re.S | re.M)
        if not m or "[--lang es|en]" not in m.group(1):
            problems.append("README: la sinopsis de %s no lleva --lang" % sub)
    if not any(l.startswith("| `--lang") for l in usage.split("\n")):
        problems.append("README: la tabla de parametros no lleva --lang")
    return problems


def other_docs_problems(claude_md, history, extra_claude=()):
    """CLAUDE.md y HISTORY.md al dia (caso 47). `extra_claude`: agujas que la prueba real aun no exige."""
    problems = []
    for needle in ("plans_dir", "--lang", "# Planes:", "function ConvertTo-PlansBytes",
                   "Fase 5, T8: añade a `docs/agentes.md`") + tuple(extra_claude):
        if needle not in claude_md:
            problems.append("CLAUDE.md: falta %s" % needle)
    unreleased = re.search(r"^## \[Sin publicar\]\n(.*?)(?=^## \[|\Z)", history, re.S | re.M)
    if not unreleased or "Fase 5, T8" not in unreleased.group(1):
        problems.append("HISTORY.md: falta la entrada de la Fase 5, T8 en [Sin publicar]")
    return problems


class ProfilesSection(unittest.TestCase):
    """Caso 44."""

    def setUp(self):
        self.md = read_text(README)

    def test_case44_real_readme_has_everything(self):
        self.assertEqual(profile_problems(self.md), [])

    def test_case44_detects_each_missing_piece(self):
        sec = section(self.md, PROFILES)
        self.assertIsNotNone(sec)
        mutants = {
            "falta la seccion": self.md.replace("## " + PROFILES, "## Otra cosa"),
            "falta la prioridad": self.md.replace(sec, re.sub(r"(?i)prioridad", "orden", sec)),
            "falta `permissions.deny`": self.md.replace(sec, sec.replace("permissions.deny", "permisos")),
            "falta `Agent(`": self.md.replace(sec, sec.replace("Agent(", "Agente(")),
            "falta «no verificado»": self.md.replace(
                sec, "\n".join(l for l in sec.split("\n") if not ("hooks:" in l and "erificado" in l))),
        }
        for expected, mutated in mutants.items():
            with self.subTest(expected=expected):
                self.assertNotEqual(mutated, self.md)
                self.assertTrue(any(expected in p for p in profile_problems(mutated)), expected)

    def test_case44_detects_a_guard_claimed_as_fact(self):
        sec = section(self.md, PROFILES)
        for bad in ("La copia de proyecto hereda la guarda del agente global.",
                    "Con la copia de proyecto se pierde la guarda.",
                    "Sin el bloque hooks:, el agente corre sin la guarda.",
                    "La copia de proyecto conserva la guarda del global.",
                    "La guarda sigue activa en la copia de proyecto.",
                    "Se hereda la guarda; es un riesgo menor."):
            with self.subTest(bad=bad):
                mutated = self.md.replace(sec, sec + "\n" + bad + "\n")
                self.assertTrue(any("da por hecho" in p for p in profile_problems(mutated)))
        hedged = self.md.replace(sec, sec + "\nNo verificado: quiza se pierde la guarda.\n")
        self.assertEqual(profile_problems(hedged), [])
        same = self.md.replace(sec, sec + "\nLa copia de proyecto conserva la guarda: no verificado.\n")
        self.assertEqual(profile_problems(same), [])
        # El matiz en otra oracion no absuelve.
        other = self.md.replace(sec, sec + "\nLa guarda sigue activa. No verificado.\n")
        self.assertTrue(any("da por hecho" in p for p in profile_problems(other)))

    def test_case44_section_boundaries(self):
        self.assertIsNone(section("## Uno\ntexto\n", PROFILES))
        self.assertEqual(section("## Perfiles por proyecto\na\n## Otro\nb\n", PROFILES), "a\n")


class NoPromises(unittest.TestCase):
    """Caso 45."""

    def setUp(self):
        self.md = read_text(README)

    def test_case45_new_sections_have_no_promises(self):
        self.assertEqual(promise_problems(self.md), [])

    def test_case45_detects_a_promise_or_a_percentage(self):
        for title in (PROFILES, PLANS):
            sec = section(self.md, title)
            for bad in ("Ahorra tokens.", "Un 30 % menos."):
                with self.subTest(title=title, bad=bad):
                    mutated = self.md.replace(sec, sec + "\n" + bad + "\n")
                    self.assertTrue(any(p.startswith(title) for p in promise_problems(mutated)))

    def test_case45_a_missing_section_fails(self):
        self.assertTrue(promise_problems(self.md.replace("## " + PLANS, "## Otra")))


class PlansAndLangDocs(unittest.TestCase):
    """Caso 47."""

    def setUp(self):
        self.guide = read_text(GUIDE)
        self.readme = read_text(README)

    def test_case47_real_docs_are_complete(self):
        self.assertEqual(guide_problems(self.guide), [])
        self.assertEqual(readme_lang_plans_problems(self.readme), [])
        self.assertEqual(other_docs_problems(read_text(CLAUDE_MD), read_text(HISTORY)), [])

    def test_case47_guide_detects_each_missing_piece(self):
        block = guide_plans_block(self.guide)
        self.assertIsNotNone(block)
        usage = section(self.guide, USAGE)
        lang_line = [l for l in usage.split("\n") if l.startswith("- ") and "`--lang" in l][0]
        mutants = {
            "falta el apartado": self.guide.replace(GUIDE_PLANS, "**Otra cosa.**"),
            "falta la clave `plans_dir`": self.guide.replace(block, block.replace("plans_dir", "carpeta_x")),
            "falta la marca": self.guide.replace(block, re.sub(r"(?i)no verificado", "pendiente", block)),
            "falta la vineta": self.guide.replace(lang_line + "\n", "").replace(lang_line, ""),
        }
        for expected, mutated in mutants.items():
            with self.subTest(expected=expected):
                self.assertNotEqual(mutated, self.guide)
                self.assertTrue(any(expected in p for p in guide_problems(mutated)), expected)

    def test_case47_marca_fuera_del_apartado_no_vale(self):
        block = guide_plans_block(self.guide)
        mutated = self.guide.replace(block, re.sub(r"(?i)no verificado", "pendiente", block))
        mutated += "\nNo verificado.\n"
        self.assertTrue(any("marca" in p for p in guide_problems(mutated)))

    def test_case47_readme_detects_each_missing_piece(self):
        plans = section(self.readme, PLANS)
        usage = section(self.readme, USAGE)
        mutants = {
            "no menciona plans_dir": self.readme.replace(plans, plans.replace("plans_dir", "carpeta_x")),
            "la sinopsis de project": self.readme.replace(
                usage, usage.replace("[--show-paths]\n                                        [--lang es|en]",
                                     "[--show-paths]")),
            "la sinopsis de global": self.readme.replace(
                usage, usage.replace("[--show-paths] [--lang es|en]", "[--show-paths]")),
            "la tabla de parametros": self.readme.replace(
                usage, "\n".join(l for l in usage.split("\n") if not l.startswith("| `--lang"))),
            "falta la seccion": self.readme.replace("## " + PLANS, "## Otra cosa"),
        }
        for expected, mutated in mutants.items():
            with self.subTest(expected=expected):
                self.assertNotEqual(mutated, self.readme)
                self.assertTrue(any(expected in p for p in readme_lang_plans_problems(mutated)), expected)

    def test_case47_other_docs_detect_each_missing_piece(self):
        claude, history = read_text(CLAUDE_MD), read_text(HISTORY)
        for needle in ("plans_dir", "--lang", "# Planes:", "function ConvertTo-PlansBytes",
                       "Fase 5, T8: añade a `docs/agentes.md`"):
            with self.subTest(needle=needle):
                self.assertTrue(other_docs_problems(claude.replace(needle, "x"), history))
        self.assertTrue(other_docs_problems(claude, history.replace("Fase 5, T8", "Fase 5, Tx")))

    def test_case47_claude_md_anchor_is_required(self):
        claude, history = read_text(CLAUDE_MD), read_text(HISTORY)
        self.assertIn("function ConvertTo-PlansBytes", claude)
        mutated = claude.replace("function ConvertTo-PlansBytes", "function X")
        self.assertNotEqual(mutated, claude)
        self.assertTrue(any("function ConvertTo-PlansBytes" in p for p in other_docs_problems(mutated, history)))

    def test_case47_readme_rules_marker_and_limits(self):
        plans = section(self.readme, PLANS)
        limits = section(self.readme, LIMITS)
        self.assertIsNotNone(limits)
        mutants = {
            "hasta 64 caracteres": self.readme.replace(plans, plans.replace("hasta 64 caracteres", "un maximo")),
            "nombre de dispositivo de Windows": self.readme.replace(
                plans, plans.replace("nombre de dispositivo de Windows", "nombre reservado")),
            "no trae la marca": self.readme.replace(plans, re.sub(r"(?i)no (está )?verificado", "pendiente", plans)),
            "no menciona plans_dir": self.readme.replace(limits, limits.replace("plans_dir", "carpeta_x")),
            "falta la seccion «%s»" % LIMITS: self.readme.replace("## " + LIMITS, "## Otra cosa"),
        }
        for expected, mutated in mutants.items():
            with self.subTest(expected=expected):
                self.assertNotEqual(mutated, self.readme)
                self.assertTrue(any(expected in p for p in readme_lang_plans_problems(mutated)), expected)


class ManagedFilesAfterDocs(unittest.TestCase):
    """Caso 46."""

    def test_case46_still_twelve_managed_files(self):
        paths = pr.managed_paths()
        self.assertEqual(len(paths), 12)
        self.assertEqual(len(set(paths)), 12)

    def test_case46_roles_inventory_unchanged(self):
        texts = {rel: ar.repo_text(rel) for rel in ar.text_files()}
        self.assertEqual(inventory_problems_of_roles(texts), [])

    def test_case46_roles_inventory_detects_a_new_mention(self):
        texts = {rel: ar.repo_text(rel) for rel in ar.text_files()}
        texts["docs/agentes.md"] += "\nEl agente forge adapta.\n"
        self.assertTrue(inventory_problems_of_roles(texts))

    def test_case46_plans_inventory_unchanged(self):
        files = {rel: pr.repo_bytes(rel) for rel in pr.managed_paths()}
        self.assertEqual(pr.inventory_problems(files), [])

    def test_case46_plans_inventory_detects_a_new_literal(self):
        files = {rel: pr.repo_bytes(rel) for rel in pr.managed_paths()}
        files["docs/agentes.md"] += b"\nver docs/plans/otro\n"
        self.assertTrue(pr.inventory_problems(files))

    def test_case46_manifest_is_in_sync(self):
        proc = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "tools", "build_manifest.py"), "--check"],
                              cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
