"""Pruebas de los alias de agentes (Fase 4, T1): listas cerradas de install.ps1, inventario de los
textos del repositorio y referencia independiente (aliases_ref.py). Casos del plan: 1 ($AliasRoles contra
agents/*.md), 2 ($ReservedAliases y $YamlWords), 3 (inventario), 4 (frontmatter real), 5 (zonas
sensibles), 6 (nueve alias sobre el repositorio real), 7 (orden con el nivel) y 8 (validacion V1 a V7).
El caso 54 (install.ps1 en ASCII, sin asterisco ni construcciones prohibidas) lo cubren las pruebas
estaticas existentes de test_install.py y test_levels.py. Sin PowerShell: solo biblioteca estandar.
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aliases_ref as ar  # noqa: E402
import levels_ref as lr  # noqa: E402

ROLES = ["atlas", "auditor", "debugger", "forge", "oracle", "scout", "scribe", "sentinel", "shield"]
LEVEL_ROLES = ["atlas", "forge", "sentinel", "scribe", "scout", "oracle"]
RESERVED = ["explore", "plan", "general-purpose", "claude", "statusline-setup", "claude-code-guide", "web-fetch",
            "fork", "output-style-setup"]
YAML_WORDS = ["true", "false", "null", "yes", "no", "on", "off", "y", "n"]

# Nueve alias validos a la vez (ninguno contiene un rol como palabra).
NINE = {"atlas": "mapa", "auditor": "revisor", "debugger": "cazador", "forge": "dev", "oracle": "guia",
        "scout": "explorador", "scribe": "redactor", "sentinel": "amigo-qa", "shield": "guardia"}

# Caso 3: apariciones de cada rol por archivo, [minuscula, Capitalizada, MAYUSCULAS], con limite de palabra.
# «escribe», «describe», «reescribe», «sobrescribe» y «escriben» no cuentan. Con la regla de E1 los
# SENTINEL y AUDITOR de docs/agentes.md pegados a una comilla angular si cuentan (uno mas cada uno). Si la
# guia o las reglas ganan o pierden una mencion, esta tabla falla: hay que revisar el cambio y actualizarla.
INVENTORY = {
    "agents/atlas.md": {"atlas": [1, 0, 2], "oracle": [0, 0, 1]},
    "agents/auditor.md": {"auditor": [1, 0, 2], "shield": [0, 0, 1]},
    "agents/debugger.md": {"debugger": [1, 0, 2], "forge": [0, 0, 1]},
    "agents/forge.md": {"atlas": [0, 0, 1], "forge": [1, 0, 2]},
    "agents/oracle.md": {"oracle": [1, 0, 2]},
    "agents/scout.md": {"scout": [1, 0, 2]},
    "agents/scribe.md": {"scribe": [1, 0, 2]},
    "agents/sentinel.md": {"sentinel": [1, 0, 2]},
    "agents/shield.md": {"shield": [1, 0, 2]},
    "rules/agentes.md": {"atlas": [5, 0, 0], "auditor": [10, 1, 0], "debugger": [2, 0, 0], "forge": [10, 1, 0],
                         "oracle": [5, 0, 0], "scout": [3, 0, 0], "scribe": [4, 0, 0], "sentinel": [8, 0, 0],
                         "shield": [8, 0, 0]},
    "docs/agentes.md": {"atlas": [2, 0, 3], "auditor": [3, 0, 8], "debugger": [3, 0, 4], "forge": [4, 0, 6],
                        "oracle": [2, 0, 4], "scout": [2, 0, 2], "scribe": [2, 0, 3], "sentinel": [4, 0, 6],
                        "shield": [3, 0, 5]},
}



def u(text):
    """Texto Unicode como lo ve la referencia: UTF-8 decodificado en ISO-8859-1 (un byte, un caracter)."""
    return text.encode("utf-8").decode("iso-8859-1")


def description_is_one_line(front, idx):
    """La linea siguiente a description: es el cierre (ultima del frontmatter) o una linea `clave:`."""
    nxt = front[idx + 1] if idx + 1 < len(front) else "---"
    return nxt == "---" or bool(re.match(r"[A-Za-z][A-Za-z0-9_-]*:", nxt))


def agent_bytes(role):
    return ar.repo_text("agents/%s.md" % role).encode("iso-8859-1")


def agent_source(role, name=None, description="descripcion de prueba", extra=(), body="Cuerpo de prueba.\n"):
    lines = ["---", "name: " + (role if name is None else name), "description: " + description,
             "tools: Read, Grep"] + list(extra) + ["---", body]
    return "\n".join(lines).encode("iso-8859-1")


class ClosedLists(unittest.TestCase):
    """Casos 1 y 2: las listas de install.ps1."""

    def test_case1_alias_roles_match_agents_dir(self):
        names = sorted(f[:-3] for f in os.listdir(lr.AGENTS_DIR) if f.endswith(".md"))
        self.assertEqual(len(names), 9)
        self.assertEqual(lr.read_ps_list("AliasRoles"), names)
        self.assertEqual(lr.read_ps_list("AliasRoles"), ROLES)
        self.assertEqual(ar.roles(), ROLES)

    def test_case1_roles_cover_the_level_agents(self):
        self.assertTrue(set(lr.read_ps_list("LevelAgents")) <= set(ar.roles()))

    def test_case2_reserved_and_yaml_words(self):
        self.assertEqual(lr.read_ps_list("ReservedAliases"), RESERVED)
        self.assertEqual(lr.read_ps_list("YamlWords"), YAML_WORDS)
        for name in ("AliasRoles", "ReservedAliases", "YamlWords"):
            values = lr.read_ps_list(name)
            self.assertEqual(len(values), len(set(values)), name)
            self.assertEqual([v for v in values if v != v.lower()], [], name)

    def test_case2_each_list_is_assigned_once_and_in_one_line(self):
        text = lr.script_text()
        for name in ("AliasRoles", "ReservedAliases", "YamlWords"):
            self.assertEqual(len(re.findall(r"^\$" + name + r"\b", text, re.M)), 1, name)

    def test_reader_handles_crlf(self):
        crlf = lr.script_text().replace("\n", "\r\n")
        for name in ("AliasRoles", "ReservedAliases", "YamlWords"):
            self.assertEqual(lr.read_ps_list(name, crlf), lr.read_ps_list(name))


class RepositoryInventory(unittest.TestCase):
    """Casos 3 a 5: lo que dicen los once textos que el instalador transformara."""

    def setUp(self):
        self.roles = ROLES  # el inventario no depende de install.ps1

    def test_case3_inventory_per_file(self):
        self.assertEqual(ar.text_files(), ["agents/%s.md" % r for r in ROLES] + ["rules/agentes.md", "docs/agentes.md"])
        self.assertEqual(sorted(INVENTORY), sorted(ar.text_files()))
        for rel in ar.text_files():
            with self.subTest(file=rel):
                counts, other = ar.inventory(ar.repo_text(rel))
                self.assertEqual(other, [], "palabra con un rol que no es ninguna de las tres formas")
                self.assertEqual({r: v for r, v in counts.items() if any(v)}, INVENTORY[rel])

    def test_case3_scribe_substrings_do_not_count(self):
        text = "escribe describe reescribe sobrescribe Describe escriben scribe SCRIBE Scribe"
        counts, other = ar.inventory(text)
        self.assertEqual(counts["scribe"], [1, 1, 1])
        self.assertEqual(other, [])

    def test_case3_inventory_detects_a_new_form(self):
        counts, other = ar.inventory(u("la sCribe y el forge2 y x_sentinel y Sentinel\u00e9 y \u00f1forge"))
        self.assertEqual(sorted(w for _r, w in other),
                         sorted(["forge2", "sCribe", "x_sentinel", u("Sentinel\u00e9"), u("\u00f1forge")]))
        self.assertEqual(counts["forge"], [0, 0, 0])

    def test_case3_roles_next_to_punctuation_count_as_replaceable(self):
        # E1: la comilla angular, la raya y el espacio duro son limite, no letra.
        counts, other = ar.inventory(u("\u00abSENTINEL s\u00f3lo escribe tests\u00bb y \u2014forge\u00a0"))
        self.assertEqual((counts["sentinel"], counts["forge"], other), ([0, 0, 1], [1, 0, 0], []))

    def test_case4_one_line_description_helper(self):
        # `front` son las lineas entre los dos --- : si description: es la ultima, la siguiente es el cierre.
        self.assertTrue(description_is_one_line(["name: x", "description: d"], 1))
        self.assertTrue(description_is_one_line(["description: d", "tools: Read"], 0))
        self.assertFalse(description_is_one_line(["description: d", "  sigue"], 0))
        self.assertFalse(description_is_one_line(["description: d", "continuacion"], 0))

    def test_case5_combining_marks_next_to_a_role_are_detected(self):
        import unicodedata
        nfd = unicodedata.normalize("NFD", "forgé SCRIBÉ")  # "forge" y "SCRIBE" con U+0301 tras la e
        self.assertEqual(nfd, "forge\u0301 SCRIBE\u0301")
        self.assertEqual(ar.foreign_letter_hits(nfd), [("forge", "\u0301"), ("scribe", "\u0301")])
        # El instalador lo reemplazaria y el acento quedaria sobre la primera letra del alias.
        self.assertEqual(ar.transform_text(u(nfd), {"forge": "dev"}), u("dev\u0301 SCRIBE\u0301"))
        # La forma precompuesta (NFC) no es marca combinante: es una letra de U+00C0 a U+00FF, que el limite respeta.
        self.assertEqual(ar.foreign_letter_hits("forgeé"), [])

    def test_case4_real_frontmatter(self):
        for role in ROLES:
            with self.subTest(role=role):
                lines = ar.repo_text("agents/%s.md" % role).split("\n")
                close = lines.index("---", 1)
                front = lines[1:close]
                self.assertEqual(lines[0], "---")
                self.assertEqual([l for l in front if l.startswith("name:")], ["name: " + role])
                descs = [i for i, l in enumerate(front) if l.startswith("description:")]
                self.assertEqual(len(descs), 1)
                self.assertTrue(description_is_one_line(front, descs[0]), "description: no es de una linea")
                self.assertRegex(front[descs[0]], r"^description: [\x20-\x7e]+$")
                for i, line in enumerate(front):
                    if i == descs[0] or line.startswith("name:"):
                        continue
                    low = line.lower()
                    self.assertEqual([r for r in ROLES if r in low], [], "rol en el frontmatter: " + line)

    def test_case5_no_role_in_sensitive_zones(self):
        for rel in ("rules/agentes.md", "docs/agentes.md"):
            with self.subTest(file=rel):
                text = ar.repo_text(rel)
                self.assertEqual(ar.role_hits_in_zones(text), [])
        self.assertTrue(ar.sensitive_zones(ar.repo_text("docs/agentes.md")), "el bloque cercado de la guia no se vio")

    def test_case5_the_eleven_texts_are_valid_utf8(self):
        # Supuesto 10: el limite de palabra de E1 lee las letras acentuadas como la pareja C3 + continuacion.
        for rel in ar.text_files():
            with self.subTest(file=rel):
                text = ar.utf8_text(rel)
                self.assertEqual(text.encode("utf-8"), ar.repo_text(rel).encode("iso-8859-1"))

    def test_case5_no_role_next_to_a_foreign_letter(self):
        # Una letra fuera de ASCII y de U+00C0 a U+00FF seria limite: el reemplazo la cruzaria.
        for rel in ar.text_files():
            with self.subTest(file=rel):
                self.assertEqual(ar.foreign_letter_hits(ar.utf8_text(rel)), [])
        self.assertEqual(ar.foreign_letter_hits("forge\u0142 y \u0141SCRIBE"),
                         [("forge", "\u0142"), ("scribe", "\u0141")])
        self.assertEqual(ar.foreign_letter_hits("forge\u00e9 \u00abSCRIBE\u00bb"), [])

    def test_case5_forge_inside_a_fenced_block_is_detected(self):
        # Mutacion sobre una copia en memoria: nada se escribe en docs/agentes.md.
        text = ar.repo_text("docs/agentes.md")
        self.assertIn("\n```\n", text)
        mutated = text.replace("\n```\n", "\n```\nforge\n", 1)
        self.assertNotEqual(mutated, text)
        self.assertEqual(ar.role_hits_in_zones(mutated), [("forge", "forge")])

    def test_case5_link_targets_and_urls_are_detected(self):
        self.assertTrue(ar.role_hits_in_zones("ver [guia](agents/forge.md) aqui"))
        self.assertTrue(ar.role_hits_in_zones("[x]: docs/Sentinel.md\n"))
        self.assertTrue(ar.role_hits_in_zones("https://ejemplo.org/atlas/x"))
        self.assertTrue(ar.role_hits_in_zones("~~~\nSHIELD\n~~~\n"))
        self.assertEqual(ar.role_hits_in_zones("usa `forge` y FORGE en prosa, [forge](https://ejemplo.org/x)"), [])


class ReferenceTransform(unittest.TestCase):
    """Caso 6 y 7: la referencia sobre el repositorio real, y sus bordes."""

    def test_case6_nine_aliases_on_the_real_agents(self):
        self.assertIsNone(ar.validate_table(NINE))
        for role in ROLES:
            with self.subTest(role=role):
                src = ar.repo_text("agents/%s.md" % role).split("\n")
                out = ar.transform_agent(agent_bytes(role), role, NINE).decode("iso-8859-1").split("\n")
                close = src.index("---", 1)
                self.assertEqual(len(out), len(src))
                self.assertEqual(out.index("---", 1), close)
                self.assertEqual(out[1:close].count("name: " + NINE[role]), 1)
                for i, (a, b) in enumerate(zip(src, out)):
                    if a == b:
                        continue
                    in_front = 0 < i < close
                    allowed = a.startswith(("name:", "description:")) if in_front else bool(ar.role_hits(a, NINE))
                    self.assertTrue(allowed, "cambio inesperado en la linea %d: %r" % (i, a))
                if "hooks:" in src:
                    h = src.index("hooks:")
                    self.assertEqual(out[h:close], src[h:close], "el bloque hooks: cambio")
                self.assertEqual([l for l in out if ar.role_hits(l, NINE)], [])
                # Sin residuo: ningun nombre de rol, salvo las subcadenas permitidas (escribe, describe...).
                counts, other = ar.inventory("\n".join(out))
                self.assertEqual({r: v for r, v in counts.items() if any(v)}, {})
                self.assertEqual(other, [])

    def test_case6_nine_aliases_on_the_two_texts(self):
        for rel in ("rules/agentes.md", "docs/agentes.md"):
            with self.subTest(file=rel):
                src = ar.repo_text(rel)
                out = ar.transform_doc(src.encode("iso-8859-1"), NINE).decode("iso-8859-1")
                self.assertEqual(out.count("\n"), src.count("\n"))
                self.assertEqual(ar.role_hits(out, NINE), [])
                # Sin residuo: ningun nombre de rol, salvo escribe, escriben, describe, reescribe y sobrescribe.
                counts, other = ar.inventory(out)
                self.assertEqual({r: v for r, v in counts.items() if any(v)}, {})
                self.assertEqual(other, [])

    def test_case7_alias_and_level_commute(self):
        table = lr.read_script_table()
        for role in LEVEL_ROLES:
            src = agent_bytes(role)
            for level in (1, 2, 3, 4):
                with self.subTest(role=role, level=level):
                    model, effort = table[(level, role)]
                    first_alias = lr.render_expected(ar.transform_agent(src, role, NINE), model, effort)
                    first_level = ar.transform_agent(lr.render_expected(src, model, effort), role, NINE)
                    self.assertEqual(first_alias, first_level)

    def test_empty_effective_table_returns_the_canonical_bytes(self):
        raw = b"---\r\nname: forge\r\ndescription: x\r\n---\r\ncuerpo forge\r\n"
        for table in ({}, {"forge": "forge"}):
            self.assertEqual(ar.transform_agent(raw, "forge", table), raw.replace(b"\r\n", b"\n"))
            self.assertEqual(ar.transform_doc(raw, table), raw.replace(b"\r\n", b"\n"))

    def test_agent_name_description_and_cross_references(self):
        src = agent_source("forge", description="FORGE implements the ATLAS plan",
                           body="You are FORGE. Ask scout; agents/forge.md y @agent-forge. Forge (Sonnet): ok\n")
        out = ar.transform_agent(src, "forge", {"forge": "dev", "atlas": "mapa"}).decode("iso-8859-1")
        self.assertIn("\nname: dev\n", out)
        self.assertIn("description: DEV implements the MAPA plan\n", out)
        self.assertIn("You are DEV. Ask scout; agents/dev.md y @agent-dev. Dev (Sonnet): ok", out)
        # Sin alias propio: name: intacto, el cuerpo cambia solo donde nombra al otro.
        out = ar.transform_agent(src, "forge", {"atlas": "mapa"}).decode("iso-8859-1")
        self.assertIn("\nname: forge\n", out)
        self.assertIn("You are FORGE.", out)
        self.assertIn("MAPA plan", out)
        self.assertNotIn("DEV", out)

    def test_body_name_line_is_body(self):
        src = agent_source("forge", body="name: forge\n")
        out = ar.transform_agent(src, "forge", {"forge": "dev"}).decode("iso-8859-1")
        self.assertTrue(out.endswith("---\nname: dev\n"), out)

    def test_defective_frontmatter_is_rejected(self):
        table = {"forge": "dev"}
        good = agent_source("forge")
        ar.transform_agent(good, "forge", table)
        text = good.decode("iso-8859-1")
        bad = {
            "sin name": text.replace("name: forge\n", ""),
            "name duplicado": text.replace("name: forge\n", "name: forge\nname: forge\n"),
            "name con otro valor": text.replace("name: forge\n", "name: otro\n"),
            "description multilinea": text.replace("description: descripcion de prueba\n",
                                                   "description: descripcion\n  sigue aqui\n"),
            "sin description": text.replace("description: descripcion de prueba\n", ""),
            "description duplicada": text.replace("tools:", "description: otra\ntools:"),
            "description con indicador": text.replace("description: descripcion", "description: *descripcion"),
            "rol en tools": text.replace("tools: Read, Grep", "tools: Agent(forge), Read"),
            "rol en hooks": text.replace("tools: Read, Grep", "tools: Read\nhooks:\n  x: forge"),
            "sin cierre": text.rsplit("---", 1)[0],
            "sin apertura": text[4:],
        }
        for label, data in bad.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    ar.transform_agent(data.encode("iso-8859-1"), "forge", table)

    def test_crlf_and_high_bytes(self):
        lf = agent_source("forge", body="Ca\xf1on \xe2\x80\x94 FORGE y \xc2\xabFORGE\n")
        crlf = lf.replace(b"\n", b"\r\n")
        a = ar.transform_agent(lf, "forge", {"forge": "dev"})
        self.assertEqual(ar.transform_agent(crlf, "forge", {"forge": "dev"}), a)
        # Pegado a la comilla angular un nombre si cambia (E1); la raya tambien es limite.
        self.assertIn(b"\xc2\xabDEV", a)
        self.assertIn(b"\xe2\x80\x94 DEV y", a)

    def test_state_for3(self):
        manifest = {"files": [{"path": "agents/sentinel.md", "sha256": "a" * 64},
                              {"path": "rules/agentes.md", "sha256": "b" * 64}]}
        out = ar.state_for3(manifest, {"agents/sentinel.md": "c" * 64}, 3,
                            {"agents/sentinel.md": "agents/amigo-qa.md"})
        import json
        obj = json.loads(out)
        self.assertEqual(list(obj), ["schema", "algorithm", "eol", "files"])
        self.assertEqual(obj["schema"], 3)
        self.assertEqual(list(obj["files"][0]), ["path", "sha256", "written", "level", "dest"])
        self.assertEqual(obj["files"][0]["dest"], "agents/amigo-qa.md")
        self.assertEqual(obj["files"][0]["written"], "c" * 64)
        self.assertEqual(obj["files"][1]["dest"], "rules/agentes.md")
        self.assertEqual(obj["files"][1]["written"], "b" * 64)
        self.assertEqual(out, (json.dumps(obj, indent=2, ensure_ascii=True) + "\n").encode("ascii"))

    def test_dest_for(self):
        self.assertEqual(ar.dest_for("agents/sentinel.md", {"sentinel": "amigo-qa"}), "agents/amigo-qa.md")
        self.assertEqual(ar.dest_for("agents/forge.md", {"sentinel": "amigo-qa"}), "agents/forge.md")
        self.assertEqual(ar.dest_for("agents/forge.md", {"forge": "forge"}), "agents/forge.md")
        self.assertEqual(ar.dest_for("rules/agentes.md", NINE), "rules/agentes.md")
        self.assertEqual(ar.dest_for("hooks/agent_guard.py", NINE), "hooks/agent_guard.py")


class WordBoundary(unittest.TestCase):
    """Formas del alias, limite de palabra y una sola pasada."""

    def test_forms_are_ordinal_and_distinct(self):
        self.assertEqual(ar.forms({"forge": "dev"}), {"forge": "dev", "Forge": "Dev", "FORGE": "DEV"})
        self.assertEqual(ar.forms({"sentinel": "amigo-qa"}),
                         {"sentinel": "amigo-qa", "Sentinel": "Amigo-qa", "SENTINEL": "AMIGO-QA"})
        self.assertEqual(ar.forms({"forge": "forge"}), {})

    def test_four_forms_of_the_name(self):
        t = {"forge": "dev"}
        self.assertEqual(ar.transform_text("`forge` Forge (Sonnet): FORGE @agent-forge agents/forge.md", t),
                         "`dev` Dev (Sonnet): DEV @agent-dev agents/dev.md")
        t = {"sentinel": "amigo-qa"}
        self.assertEqual(ar.transform_text("@agent-sentinel Sentinel SENTINEL", t),
                         "@agent-amigo-qa Amigo-qa AMIGO-QA")

    def test_scribe_substrings_are_untouched(self):
        t = {"scribe": "redactor"}
        text = "escribe describe reescribe sobrescribe Describe escriben Escribe"
        self.assertEqual(ar.transform_text(text, t), text)
        self.assertEqual(ar.transform_text("scribe, Scribe y SCRIBE", t), "redactor, Redactor y REDACTOR")

    def test_other_spellings_and_glued_words_are_untouched(self):
        t = {"forge": "dev"}
        for text in ("sCribe forge2 xforge forge_x _forge Forges FORGEs forgeX", "sCribe", "fOrge", "foRGE"):
            self.assertEqual(ar.transform_text(text, t), text)
        for glued, expected in (("-forge-", "-dev-"), ("/forge.", "/dev."), ("(forge)", "(dev)"), ("@forge", "@dev")):
            self.assertEqual(ar.transform_text(glued, t), expected)

    def test_single_pass_does_not_rescan_replacements(self):
        # Reemplazos sucesivos rol por rol darian "oracle-a-a": forge pasa a scout-a y scout se volveria a reemplazar.
        t = {"forge": "scout-a", "scout": "oracle-a"}
        self.assertEqual(ar.transform_text("forge scout", t), "scout-a oracle-a")
        t = {"forge": "qa", "scout": "qa2"}
        self.assertEqual(ar.transform_text("forge scout qa2", t), "qa qa2 qa2")

    def test_swap_is_a_single_pass(self):
        self.assertEqual(ar.transform_text("forge scribe", {"forge": "scribe", "scribe": "forge"}), "scribe forge")


class HighByteBoundary(unittest.TestCase):
    """Caso 55 (E1): letra = [A-Za-z0-9_] o la pareja C3 + continuacion; todo otro byte alto es limite."""

    T = {"forge": "dev", "scribe": "redactor", "sentinel": "amigo-qa"}

    def test_case55_punctuation_and_symbols_are_a_boundary(self):
        marks = ["\u00ab", "\u00bb", "\u00bf", "\u00a1", "\u201c", "\u201d", "\u2018", "\u2019", "\u2014",
                 "\u2013", "\u2026", "\u2192", "\u00a0", "\u2225"]
        for mark in marks:
            with self.subTest(mark=hex(ord(mark))):
                self.assertEqual(ar.transform_text(u(mark + "forge"), self.T), u(mark + "dev"))
                self.assertEqual(ar.transform_text(u("FORGE" + mark), self.T), u("DEV" + mark))
                self.assertEqual(ar.transform_text(u(mark + "Sentinel" + mark), self.T), u(mark + "Amigo-qa" + mark))

    def test_case55_the_sentence_of_the_guide(self):
        text = u("\u00abSENTINEL s\u00f3lo escribe tests\u00bb y \u00abSCRIBE, FORGE y")
        self.assertEqual(ar.transform_text(text, self.T),
                         u("\u00abAMIGO-QA s\u00f3lo escribe tests\u00bb y \u00abREDACTOR, DEV y"))

    def test_case55_an_accented_letter_next_to_the_name_is_not_a_boundary(self):
        for text in ("Sentinel\u00e9", "\u00f1forge", "\u00e9SCRIBE", "SCRIBE\u00c1", "forge\u00fc", "\u00d1FORGE"):
            with self.subTest(text=text):
                self.assertEqual(ar.transform_text(u(text), self.T), u(text))

    def test_case55_scribe_substrings_still_untouched(self):
        text = u("\u00abescribe\u00bb describe reescribe sobrescribe \u00bfEscribe?")
        self.assertEqual(ar.transform_text(text, self.T), text)

    def test_case55_recognised_limits_of_the_rule(self):
        # Limites reconocidos del plan, fijados para que un cambio no pase desapercibido.
        # La multiplicacion y la division (C3 97 y C3 B7) cuentan como letra: no hay coincidencia pegada a ellas.
        for text in ("\u00d7forge", "forge\u00f7", "\u00f7FORGE", "SCRIBE\u00d7"):
            self.assertEqual(ar.transform_text(u(text), self.T), u(text), text)
        # Una letra fuera de U+00C0 a U+00FF es limite (el caso 5 comprueba que ningun texto real la usa).
        self.assertEqual(ar.transform_text(u("\u0142forge forge\u0141 \u0152SCRIBE"), self.T),
                         u("\u0142dev dev\u0141 \u0152REDACTOR"))
        # Un \xC3 suelto y una continuacion sin \xC3 delante son limite.
        self.assertEqual(ar.transform_text("\xc3forge forge\xc3 \xc3 forge", self.T), "\xc3dev dev\xc3 \xc3 dev")
        self.assertEqual(ar.transform_text("\xa9forge forge\xa9 \xc2\xa9SCRIBE", self.T),
                         "\xa9dev dev\xa9 \xc2\xa9REDACTOR")
        # \xC3 seguido de un byte fuera de 0x80 a 0xBF no forma una letra.
        self.assertEqual(ar.transform_text("\xc3\xc0forge", self.T), "\xc3\xc0dev")

    def test_case55_pattern_has_no_variable_width_lookbehind_nor_ignorecase(self):
        pat = ar._pattern(ar.forms(self.T))
        self.assertEqual(pat.flags & re.IGNORECASE, 0)
        self.assertEqual(pat.pattern.count("(?<!"), 2)
        self.assertEqual(pat.pattern.count("(?!"), 2)


class TableValidation(unittest.TestCase):
    """Caso 8: cada regla V1 a V7 con un caso que falla y otro que pasa."""

    def assertProblem(self, aliases, fragment, **kw):
        problem = ar.validate_table(aliases, **kw)
        self.assertIsNotNone(problem, aliases)
        self.assertIn(fragment, problem)
        for value in aliases.values() if isinstance(aliases, dict) else ():
            if isinstance(value, str) and len(value) > 3 and value not in ROLES:
                self.assertNotIn(value, problem, "el mensaje no debe traer el valor del alias")

    def test_valid_tables(self):
        for ok in ({}, {"forge": "dev"}, NINE, {"forge": "forge"}, {"forge": "a" * 64},
                   {"sentinel": "amigo-qa", "forge": "dev"}, {"forge": "forge_2"}, {"forge": "forgery"},
                   {"forge": "sentinels"}, {"forge": "com10"}, {"forge": "yes-no"}, {"forge": "x1"}):
            with self.subTest(ok=ok):
                self.assertIsNone(ar.validate_table(ok))

    def test_types_and_keys(self):
        for bad in (None, [], ["forge"], "forge", 3, True):
            self.assertProblem(bad, "aliases debe ser un objeto")
        for key in ("qa", "Forge", "", "agents"):
            self.assertProblem({key: "dev"}, "rol desconocido en aliases")
        for value in (None, 3, True, ["dev"], {"a": "b"}):
            self.assertProblem({"forge": value}, "debe ser texto")

    def test_v1_character_set_and_length(self):
        for bad in ("", "Dev", "DEV", "a b", "a:b", "a.b", "a/b", "a\\b", "-dev", "1dev", "123", "1e3", "0x1f",
                    "_dev", "a" * 65, "dév", "dev\n", "dev\nhooks", "a#b", "'dev'"):
            with self.subTest(bad=bad):
                self.assertProblem({"forge": bad}, "solo admite a-z, 0-9, _ y -")

    def test_v1_ordinal_names_fail_by_case(self):
        for bad in ("Explore", "PLAN", "Forge"):
            self.assertProblem({"scribe": bad}, "solo admite a-z, 0-9, _ y -")

    def test_v2_yaml_words(self):
        for word in YAML_WORDS:
            with self.subTest(word=word):
                self.assertProblem({"forge": word}, "palabra reservada de YAML")

    def test_v3_windows_reserved_names(self):
        for word in ("con", "prn", "aux", "nul", "com0", "com1", "com9", "lpt0", "lpt1", "lpt9"):
            with self.subTest(word=word):
                self.assertProblem({"forge": word}, "nombre reservado de Windows")
        for ok in ("com10", "lpt10", "conx", "nulo"):
            self.assertIsNone(ar.validate_table({"forge": ok}), ok)

    def test_v4_builtin_agents(self):
        for word in RESERVED:
            with self.subTest(word=word):
                self.assertProblem({"forge": word}, "agente integrado de Claude Code")
        self.assertIsNone(ar.validate_table({"forge": "explorer"}))
        self.assertIsNone(ar.validate_table({"forge": "planner"}))

    def test_v5_alias_equal_to_another_role_and_cycles(self):
        self.assertProblem({"forge": "scribe"}, "nombre de otro agente de SyncLayer")
        self.assertProblem({"forge": "scribe", "scribe": "forge"}, "nombre de otro agente de SyncLayer")
        self.assertProblem({"forge": "scribe", "scribe": "sentinel", "sentinel": "forge"},
                           "nombre de otro agente de SyncLayer")
        self.assertIsNone(ar.validate_table({"forge": "forge", "scribe": "scribe"}))

    def test_v6_duplicates(self):
        self.assertProblem({"forge": "dev", "scribe": "dev"}, "forge y scribe tienen el mismo alias")
        self.assertIsNone(ar.validate_table({"forge": "dev", "scribe": "dev2"}))

    def test_v7_alias_containing_a_role(self):
        for bad in ("dev-sentinel", "forge-2", "sentinel-dev", "a-forge-b", "x-scribe"):
            with self.subTest(bad=bad):
                self.assertProblem({"oracle": bad}, "contiene el nombre de un agente de SyncLayer")
        # El alias del propio rol tampoco puede contener el rol (la salida lo dejaria).
        self.assertProblem({"forge": "forge-2"}, "contiene el nombre de un agente de SyncLayer")

    def test_v8_manifest_collision(self):
        paths = ["agents/forge.md", "agents/dev.md", "agents/scribe.md", "rules/agentes.md"]
        self.assertProblem({"forge": "dev"}, "coincide con otro archivo del manifiesto", manifest_paths=paths)
        self.assertIsNone(ar.validate_table({"forge": "dev"}))
        self.assertIsNone(ar.validate_table({"forge": "dev2"}, manifest_paths=paths))
        self.assertIsNone(ar.validate_table({"forge": "dev", "scribe": "otro"}, manifest_paths=["agents/forge.md"]))

    def test_v8_covers_roles_whose_file_is_not_in_the_manifest(self):
        # E2: el destino de cualquier alias efectiva se compara con todas las rutas, este o no el rol en el manifiesto.
        paths = ["agents/alfa.md", "rules/agentes.md"]
        self.assertProblem({"forge": "alfa"}, "coincide con otro archivo del manifiesto", manifest_paths=paths)
        self.assertProblem({"forge": "alfa"}, "coincide con otro archivo del manifiesto",
                           manifest_paths=paths + ["agents/forge.md"])
        for ok in ({"forge": "beta"}, {"forge": "forge"}, {}):
            self.assertIsNone(ar.validate_table(ok, manifest_paths=paths), ok)
            self.assertIsNone(ar.validate_table(ok, manifest_paths=paths + ["agents/forge.md"]), ok)


if __name__ == "__main__":
    unittest.main()
