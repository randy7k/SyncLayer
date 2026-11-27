"""Pruebas de la documentacion de la Fase 6, T8 (comprobaciones estaticas, solo biblioteca estandar).

Casos del plan docs/plans/2026-11-27-fase6-renombrado-de-agentes.md: 22 (README y guia: la seccion «Nombres
anteriores», ningun nombre anterior como palabra fuera de las zonas marcadas, sin Salomon ni Hector con tilde, sin
promesas, nada de lo que esta marcado [G1] dicho como probado) y 23 (inventario y manifiesto al dia tras editar la
guia; la prueba puente y su fixture retirados). T9 amplia el caso 22 a CLAUDE.md y docs/brand/.
Las comprobaciones son funciones que reciben el texto, para poder alimentarlas con textos mutados. Los nombres salen
de rename_ref (anteriores) y names (vigentes): aqui no se escribe ninguno.
"""

import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import names  # noqa: E402
import rename_ref as rr  # noqa: E402
from test_levels import promise_hits  # noqa: E402
from test_phase5_docs import inventory_problems_of_roles, read_text, section  # noqa: E402
import aliases_ref as ar  # noqa: E402

README = os.path.join(ROOT, "README.md")
GUIDE = os.path.join(ROOT, "docs", "agentes.md")
PREV_TITLE = "Nombres anteriores"
PREV_START = "<!-- nombres-anteriores:inicio -->"
PREV_END = "<!-- nombres-anteriores:fin -->"
TIMELINE = "Línea de tiempo y avance"
OLD_NAMES = sorted(rr.RENAME)
ACCENTED = ("Salomón", "Héctor")
# Frases que el apartado de limites debe traer (limites nuevos de T8).
LIMIT_PHRASES = ("estado ausente", "agente propio", "V7", "es el nombre anterior de otro rol")
UNVERIFIED = re.compile(r"no (est[aá]n? )?verificad[oa]s?|sin verificar|no se comprob[oó]", re.I)


def old_word_hits(text):
    """[(linea, nombre)] de los nombres anteriores como palabra (limite de palabra: letra o digito o _), sin
    distinguir mayusculas. «escribe» y compania no cuentan: son otra palabra."""
    hits = []
    for lineno, line in enumerate(text.split("\n"), 1):
        for name in OLD_NAMES:
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", line, re.I):
                hits.append((lineno, name))
    return hits


def previous_zone(md):
    """Texto entre los marcadores de «Nombres anteriores» (sin ellos); None si faltan, se repiten o van al reves."""
    if md.count(PREV_START) != 1 or md.count(PREV_END) != 1:
        return None
    a, b = md.index(PREV_START), md.index(PREV_END)
    return md[a + len(PREV_START):b] if a < b else None


def outside_zones(md):
    """El README sin la zona marcada de «Nombres anteriores» y sin la seccion «Línea de tiempo y avance» (del
    encabezado al final o a la siguiente `## `). Sin marcadores, solo quita la linea de tiempo."""
    zone = previous_zone(md)
    if zone is not None:
        md = md.replace(PREV_START + zone + PREV_END, "")
    sec = section(md, TIMELINE)
    if sec is not None:
        md = md.replace("## " + TIMELINE, "", 1).replace(sec, "", 1)
    return md


def sentences(text):
    text = re.sub(r"\n> ?", "\n", text)   # las citas de bloque parten las frases
    return [" ".join(s.split()) for s in re.split(r"\n\s*\n|\n(?=\||- )|(?<=[.!?])\s+", text) if s.strip()]


def previous_names_problems(md):
    """Problemas de la seccion «Nombres anteriores» del README (caso 22)."""
    zone = previous_zone(md)
    if zone is None:
        return ["faltan los marcadores de «%s» (o no son uno solo, en orden)" % PREV_TITLE]
    problems = []
    sec = section(md, PREV_TITLE)
    if sec is None or PREV_END not in sec:
        problems.append("la seccion «%s» no va entre los marcadores" % PREV_TITLE)
    for old, new in sorted(rr.RENAME.items()):
        row = re.compile(r"^\|\s*`%s`\s*\|\s*`%s`\s*\|" % (re.escape(old), re.escape(new)), re.M)
        if not row.search(zone):
            problems.append("falta la fila `%s` -> `%s`" % (old, new))
    # La tabla de alias para conservar los nombres de antes: un bloque json con los ocho pares nuevo -> viejo.
    blocks = re.findall(r"```json\n(.*?)```", zone, re.S)
    ok = False
    for block in blocks:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if data == {"aliases": {new: old for old, new in rr.RENAME.items()}}:
            ok = True
    if not ok:
        problems.append("falta el bloque json con los ocho alias para conservar los nombres anteriores")
    for needle in ("HUERFANO", "stderr", "`-DryRun`", "(otro agente)", "SyncLayer", "no se borra", "no se abre",
                   "no se respalda") + LIMIT_PHRASES:
        if needle not in zone:
            problems.append("falta «%s»" % needle)
    if not UNVERIFIED.search(zone):
        problems.append("falta la marca «no verificado»")
    for s in sentences(zone):
        if re.search(r"claude code real|g1", s, re.I) and not UNVERIFIED.search(s):
            problems.append("frase de Claude Code real o G1 sin marca de no verificado: " + s[:60])
    if promise_hits(zone):
        problems.append("promesas o porcentajes: %s" % promise_hits(zone))
    return problems


def claim_problems(text):
    """Frases de Claude Code real o G1 sin marca de no verificado, y promesas o porcentajes, en un texto."""
    problems = []
    for s in sentences(text):
        if re.search(r"claude code real|g1", s, re.I) and not UNVERIFIED.search(s):
            problems.append("frase de Claude Code real o G1 sin marca de no verificado: " + s[:60])
    if promise_hits(text):
        problems.append("promesas o porcentajes: %s" % promise_hits(text))
    return problems


# Las secciones del reporte de uso traen cifras medidas y porcentajes legitimos (umbral de archivos danados,
# prueba sintetica de rendimiento) y la palabra «garantia» negada: no pasan promise_hits, y no son promesas.
MEASURED_SECTIONS = ("Reporte de uso", "Límites del reporte de uso")


def promise_scope(md):
    """El texto sin las secciones de MEASURED_SECTIONS."""
    for title in MEASURED_SECTIONS:
        sec = section(md, title)
        if sec is not None:
            md = md.replace(sec, "", 1)
    return md


def doc_problems(md, outside=None):
    """Problemas comunes a README y guia: nombres anteriores como palabra fuera de las zonas marcadas y los
    nombres con tilde (en todo el texto, zonas incluidas). `outside` es el texto ya sin zonas."""
    outside = md if outside is None else outside
    problems = ["nombre anterior `%s` en la linea %d" % (n, l) for l, n in old_word_hits(outside)]
    problems += ["nombre con tilde %s" % word for word in ACCENTED if word.lower() in md.lower()]
    problems += claim_problems(promise_scope(outside))
    return problems


class PreviousNamesSection(unittest.TestCase):
    """Caso 22: README."""

    def setUp(self):
        self.md = read_text(README)

    def test_case22_real_readme_has_the_section(self):
        self.assertEqual(previous_names_problems(self.md), [])

    def test_case22_no_old_name_outside_the_marked_zones(self):
        self.assertEqual(doc_problems(self.md, outside_zones(self.md)), [])

    def test_case22_the_zones_do_hold_the_old_names(self):
        # Si la zona no tuviera nombres anteriores, la exclusion no seria lo que se prueba.
        self.assertTrue(old_word_hits(previous_zone(self.md)))
        self.assertNotEqual(outside_zones(self.md), self.md)

    def test_case22_detects_each_missing_piece(self):
        zone = previous_zone(self.md)
        old, new = sorted(rr.RENAME.items())[0]
        mutants = {
            "faltan los marcadores": self.md.replace(PREV_START, ""),
            "no va entre los marcadores": self.md.replace(PREV_END, "").replace("## " + PREV_TITLE, PREV_END
                                                                                 + "\n## " + PREV_TITLE),
            "falta la fila": self.md.replace("| `%s` | `%s` |" % (old, new), "| `x` | `y` |"),
            "falta el bloque json": self.md.replace(zone, zone.replace("```json", "```text")),
            "falta «HUERFANO»": self.md.replace(zone, zone.replace("HUERFANO", "huerfano")),
            "falta «agente propio»": self.md.replace(zone, zone.replace("agente propio", "agente suyo")),
            "falta «estado ausente»": self.md.replace(zone, zone.replace("estado ausente", "sin estado")),
            "falta «es el nombre anterior de otro rol»": self.md.replace(
                zone, zone.replace("es el nombre anterior de otro rol", "es otra cosa")),
            "falta la marca": self.md.replace(zone, UNVERIFIED.sub("probado", zone)),
        }
        for expected, mutated in mutants.items():
            with self.subTest(expected=expected):
                self.assertNotEqual(mutated, self.md)
                self.assertTrue(any(expected in p for p in previous_names_problems(mutated)), expected)

    def test_case22_detects_a_claim_about_real_claude_code_without_the_mark(self):
        zone = previous_zone(self.md)
        mutated = self.md.replace(zone, zone + "\nEn Claude Code real los dos nombres conviven sin problema.\n")
        self.assertTrue(any("Claude Code real" in p for p in previous_names_problems(mutated)))
        hedged = self.md.replace(zone, zone + "\nEn Claude Code real: no verificado.\n")
        self.assertEqual(previous_names_problems(hedged), [])

    def test_case22_detects_a_promise_in_the_section(self):
        zone = previous_zone(self.md)
        for bad in ("Ahorra tokens.", "Un 30 % menos."):
            with self.subTest(bad=bad):
                mutated = self.md.replace(zone, zone + "\n" + bad + "\n")
                self.assertTrue(any("promesas" in p for p in previous_names_problems(mutated)))

    def test_case22_detects_an_old_name_outside_and_ignores_the_zones(self):
        old = OLD_NAMES[0]
        for text in ("Usa a %s para esto." % old, "Usa a **%s**." % old.upper(), "(%s-2)" % old.capitalize()):
            with self.subTest(text=text):
                mutated = self.md.replace("## Requisitos", text + "\n\n## Requisitos")
                self.assertNotEqual(mutated, self.md)
                self.assertTrue(doc_problems(mutated, outside_zones(mutated)))
        inside = self.md.replace(PREV_END, "Aqui va %s.\n%s" % (old, PREV_END))
        self.assertEqual(doc_problems(inside, outside_zones(inside)), [])
        timeline = self.md.replace("## " + TIMELINE, "## " + TIMELINE + "\n\nHito de %s.\n" % old)
        self.assertEqual(doc_problems(timeline, outside_zones(timeline)), [])

    def test_case22_claims_and_promises_are_checked_outside_the_zones_too(self):
        for bad, expected in (("En Claude Code real todo funciona.", "Claude Code real"), ("Ahorra tokens.", "promesas")):
            with self.subTest(bad=bad):
                mutated = self.md.replace("## Requisitos", bad + chr(10) * 2 + "## Requisitos")
                self.assertTrue(any(expected in p for p in doc_problems(mutated, outside_zones(mutated))))

    def test_case22_other_words_are_not_hits(self):
        for text in ("escribe describe reescribe sobrescribe", "x%sy %s2 _%s" % ((OLD_NAMES[0],) * 3)):
            with self.subTest(text=text):
                self.assertEqual(old_word_hits(text), [])

    def test_case22_accented_names_are_rejected_everywhere(self):
        for word in ACCENTED:
            with self.subTest(word=word):
                mutated = self.md.replace(PREV_END, word + "\n" + PREV_END)
                self.assertTrue(any("tilde" in p for p in doc_problems(mutated, outside_zones(mutated))))

    def test_case22_the_zone_is_removed_once_and_in_order(self):
        self.assertIsNone(previous_zone("a " + PREV_END + " b " + PREV_START))
        self.assertIsNone(previous_zone(PREV_START + PREV_START + PREV_END))
        self.assertEqual(previous_zone("a " + PREV_START + "x" + PREV_END + " b"), "x")


class GuideNames(unittest.TestCase):
    """Caso 22: guia."""

    def setUp(self):
        self.md = read_text(GUIDE)

    def test_case22_guide_has_no_old_name_and_no_accent(self):
        self.assertEqual(doc_problems(self.md), [])

    def test_case22_guide_points_to_the_previous_names_section(self):
        self.assertIn("«%s»" % PREV_TITLE, self.md)
        self.assertEqual(promise_hits(self.md), [])

    def test_case22_guide_detects_a_claim_without_the_mark_and_a_promise(self):
        for bad, expected in ((chr(10) * 2 + "En Claude Code real todo funciona." + chr(10), "Claude Code real"),
                              (chr(10) * 2 + "Ahorra tokens." + chr(10), "promesas")):
            with self.subTest(bad=bad):
                self.assertTrue(any(expected in p for p in doc_problems(self.md + bad)))

    def test_case22_guide_detects_an_old_name(self):
        mutated = self.md + "\nUsa a %s.\n" % OLD_NAMES[0]
        self.assertTrue(doc_problems(mutated))


class InventoryAndBridge(unittest.TestCase):
    """Caso 23."""

    def test_case23_inventory_is_up_to_date_after_editing_the_guide(self):
        texts = {rel: ar.repo_text(rel) for rel in ar.text_files()}
        self.assertEqual(inventory_problems_of_roles(texts), [])

    def test_case23_inventory_detects_a_new_mention_in_the_guide(self):
        texts = {rel: ar.repo_text(rel) for rel in ar.text_files()}
        texts["docs/agentes.md"] += "\nUsa a %s.\n" % names.DEVELOPER
        self.assertTrue(inventory_problems_of_roles(texts))

    def test_case23_manifest_is_in_sync(self):
        proc = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "tools", "build_manifest.py"), "--check"],
                              cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))

    def test_case23_the_bridge_test_and_its_fixture_are_retired(self):
        self.assertFalse(os.path.exists(os.path.join(HERE, "rename_expected.json")))
        for attr in ("FIXTURE", "expected_texts", "expected_hashes", "fixture_bytes", "main"):
            with self.subTest(attr=attr):
                self.assertFalse(hasattr(rr, attr))
        with open(os.path.join(HERE, "test_rename.py"), "rb") as f:
            text = f.read().decode("utf-8")
        self.assertNotIn("class BridgeFixture", text)
        self.assertNotIn("rename_expected", text)
        self.assertNotIn("rename_expected.json", rr.OWN_NAMES)


if __name__ == "__main__":
    unittest.main()
