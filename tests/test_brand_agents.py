import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "assets", "brand", "src"))

from agents_data import AGENTS  # noqa: E402


def frontmatter(path):
    with open(path, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path}: sin frontmatter"
    return m.group(1)


def field(fm, key):
    m = re.search(rf"^{key}:[ \t]*(.+)$", fm, re.M)
    return m.group(1).strip() if m else None


class BrandAgentsSync(unittest.TestCase):
    def test_nine_agents_match_files(self):
        files = sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md"))
        self.assertEqual(sorted(a[0] for a in AGENTS), files,
                         "AGENTS (assets/brand/src/agents_data.py) y agents/*.md no listan los mismos agentes")

    def test_fields_match_frontmatter(self):
        for name, _role, model, tools, writes, guarded in AGENTS:
            with self.subTest(agent=name):
                fm = frontmatter(os.path.join(ROOT, "agents", f"{name}.md"))
                hint = f"; actualiza agents_data.py o agents/{name}.md y regenera los SVG"
                self.assertEqual(field(fm, "name"), name, f"{name}: name{hint}")
                self.assertEqual(field(fm, "model"), model, f"{name}: model{hint}")
                self.assertEqual(field(fm, "tools"), tools, f"{name}: tools{hint}")
                self.assertEqual(re.search(r"^hooks:", fm, re.M) is not None, guarded,
                                 f"{name}: guarded vs 'hooks:'{hint}")
                has_write = any(t in tools.split(", ") for t in ("Edit", "Write"))
                self.assertEqual(bool(writes), has_write,
                                 f"{name}: writes vs Edit/Write en tools{hint}")


if __name__ == "__main__":
    unittest.main()
