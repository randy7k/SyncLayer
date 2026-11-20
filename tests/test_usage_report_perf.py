"""Pruebas de rendimiento y de equivalencia del lector de tools/usage_report.py (Fase 2, C4).

Dos clases de pruebas, sobre arboles SINTETICOS en carpetas temporales (nunca el ~/.claude real):

- Equivalencia: el lector optimizado da el MISMO resultado que una implementacion de referencia
  sencilla (las funciones por linea tal como eran antes de la optimizacion, copiadas aqui), incluso
  con lineas raras (blancos, \\x0c, BOM, corruptas, truncadas, oversize, tipos mal formados).
- Tope de trabajo: nada de trabajo repetido por linea o por archivo (un json.loads por linea, una
  clasificacion de version/modelo por valor distinto y por archivo, buffer de lectura grande).
"""

import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import usage_report as ur  # noqa: E402
import usage_synth as us  # noqa: E402

KEY = b"k" * 16


# --- referencia: el comportamiento por linea anterior a la optimizacion -----------------------

def ref_iter_objects(f, info):
    while True:
        line = f.readline(ur.MAX_LINE_BYTES + 1)
        if not line:
            return
        info.bytes_read += len(line)
        if info.bytes_read > ur.MAX_FILE_BYTES:
            raise ur._TooBig()
        has_newline = line.endswith(b"\n")
        if len(line) > ur.MAX_LINE_BYTES and not has_newline:
            info.oversize += 1
            while True:
                chunk = f.readline(ur.MAX_LINE_BYTES)
                info.bytes_read += len(chunk)
                if info.bytes_read > ur.MAX_FILE_BYTES:
                    raise ur._TooBig()
                if not chunk or chunk.endswith(b"\n"):
                    break
            continue
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except (ValueError, RecursionError):
            if has_newline:
                info.corrupt += 1
            else:
                info.truncated_tail = True
            continue
        if isinstance(obj, dict):
            yield obj
        else:
            info.not_object += 1


def ref_parse_ts(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except (ValueError, OverflowError):
        return None


def ref_token_tuple(usage):
    out = []
    for name in ur.TOKEN_FIELDS:
        value = usage.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        out.append(value)
    return tuple(out)


def ref_acc_head(obj, acc):
    acc.lines += 1
    kind = obj.get("type")
    if isinstance(kind, str):
        acc.typed += 1
    version = obj.get("version")
    if isinstance(version, str):
        acc.versions.add(ur.hist_label("version", version))
    ts = ref_parse_ts(obj.get("timestamp"))
    if ts is None:
        if kind in ("user", "assistant"):
            acc.schema.add(ur.CHK_TS)
    else:
        if acc.first is None or ts < acc.first:
            acc.first = ts
        if acc.last is None or ts > acc.last:
            acc.last = ts
    return kind, ts


def ref_acc_line(obj, acc):
    kind, ts = ref_acc_head(obj, acc)
    if kind != "assistant":
        return
    message = obj.get("message")
    if not isinstance(message, dict):
        return
    model = message.get("model")
    if model == ur.SYNTHETIC_MODEL:
        acc.synthetic += 1
        return
    if isinstance(model, str):
        acc.models.add(ur.hist_label("model", model))
    if "usage" in message:
        usage = message.get("usage")
        if not isinstance(usage, dict):
            acc.schema.add(ur.CHK_USAGE_OBJ)
        else:
            tokens = ref_token_tuple(usage)
            if tokens is None:
                acc.schema.add(ur.CHK_TOKENS)
            else:
                msg_id = message.get("id")
                if isinstance(msg_id, str):
                    key = ur._digest(msg_id)
                    if key not in acc.usage_by_id and len(acc.usage_by_id) >= ur.MAX_IDS_PER_FILE:
                        raise ur._TooBig()
                    acc.usage_by_id[key] = tokens
                else:
                    if len(acc.usage_no_id) >= ur.MAX_IDS_PER_FILE:
                        raise ur._TooBig()
                    acc.usage_no_id.append(tokens)
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                block_id = block.get("id")
                if isinstance(block_id, str):
                    key = ur._digest(block_id)
                    if key not in acc.tools and len(acc.tools) >= ur.MAX_IDS_PER_FILE:
                        raise ur._TooBig()
                    acc.tools.add(key)
                ur._acc_skill(block, ts, acc)


def reference_patches():
    return (mock.patch.object(ur, "_iter_objects", ref_iter_objects),
            mock.patch.object(ur, "_acc_head", ref_acc_head),
            mock.patch.object(ur, "_acc_line", ref_acc_line))


def snapshot(claude_dir):
    """Resultado completo de read_calls, o el mensaje del error si lanza."""
    try:
        res = ur.read_calls(claude_dir, check_damage=False, digest_key=KEY)
    except (ur.SchemaError, ur.EnvError) as exc:
        return ("error", type(exc).__name__, str(exc))
    return ("ok", res.calls, res.skill_uses, dict(res.quality), dict(res.schema), dict(res.versions),
            dict(res.schema_versions), res.sessions_read)


# --- arbol de bordes ----------------------------------------------------------------------------

def no_id(ts):
    line = us.assistant("x", ts)
    del line["message"]["id"]
    return line


def weird_lines():
    """Lineas en bytes, una por caso. Cada una va con su salto de linea al escribir."""
    ok = us.assistant("m-ok", "2026-11-01T10:00:00Z")
    j = json.dumps
    return [
        j(us.user("2026-11-01T09:59:00Z")).encode(),
        j(ok).encode(),
        b"   ",                                              # solo blancos
        b"",                                                 # linea vacia
        b"  " + j(us.assistant("m-lead", "2026-11-01T10:01:00Z")).encode(),   # blancos al inicio
        j(us.assistant("m-ff", "2026-11-01T10:02:00Z")).encode() + b"\x0c",   # \x0c al final
        j(us.assistant("m-vt", "2026-11-01T10:03:00Z")).encode() + b"\x0b",   # \x0b al final
        j(us.assistant("m-cr", "2026-11-01T10:04:00Z")).encode() + b"\r",     # CRLF
        b"\xef\xbb\xbf" + j(us.assistant("m-bom", "2026-11-01T10:05:00Z")).encode(),   # BOM
        b"[1, 2]",                                           # no es objeto
        b"42",
        b"null",
        b'{"type": "assistant", "timestamp": ',               # corrupta
        j(us.assistant("m-s1", "2026-11-01T11:00:00+05:00", version="2.1.315")).encode(),
        j(us.assistant("m-s1", "2026-11-01T11:00:00", version="2.1.315",
                       usage_value=us.usage(20, 30))).encode(),     # mismo id, otra hora sin zona
        j(us.assistant("m-bad", "2026-11-01T12:00:00Z", usage_value=us.usage(-1))).encode(),
        j(us.assistant("m-str", "2026-11-01T12:01:00Z", usage_value=us.usage(inp="7"))).encode(),
        j(us.assistant("m-bool", "2026-11-01T12:02:00Z", usage_value=us.usage(inp=True))).encode(),
        j(us.assistant("m-nousage-obj", "2026-11-01T12:03:00Z", usage_value="texto")).encode(),
        j(us.assistant("m-syn", "2026-11-01T12:04:00Z", model="<synthetic>")).encode(),
        j(us.assistant("m-model", "2026-11-01T12:05:00Z", model="ZZ raro")).encode(),
        j(us.assistant("m-ver", "2026-11-01T12:06:00Z", version="no es version")).encode(),
        j(us.assistant("m-ts", "no es hora")).encode(),
        j(us.assistant("m-tsnum", 12345)).encode(),
        j(us.assistant("m-future", "9999-12-31T23:59:59-23:59")).encode(),
        j(us.assistant("m-skill", "2026-11-01T12:07:00Z",
                       blocks=[us.skill_block("sk-1", "brainstorming"), us.tool_use_block("tu-1", "Bash"),
                               us.tool_use_block("tu-1", "Bash")])).encode(),
        j(us.assistant("m-skill2", "2026-11-01T12:08:00Z",
                       blocks=[us.skill_block("sk-1", "brainstorming")])).encode(),
        j(no_id("2026-11-01T12:09:00Z")).encode(),
        j(no_id("2026-11-01T12:10:00Z")).encode(),
        j(us.tool_result_line("2026-11-01T12:11:00Z")).encode(),
        j({"type": 5, "timestamp": "2026-11-01T12:12:00Z", "version": 3}).encode(),
        j(us.assistant("m-big", "2026-11-01T12:13:00Z", blocks=[us.text_block("y" * 300000)])).encode(),
    ]


def write_raw(path, lines, tail=b"", final_newline=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = b"\n".join(lines)
    if final_newline:
        data += b"\n"
    with open(path, "wb") as f:
        f.write(data + tail)


class EquivalenceBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tree = us.Tree(tmp.name)
        self.folder = "c--proj-edge"

    def sub_dir(self, sid):
        return os.path.join(self.tree.folder(self.folder), sid, "subagents")

    def compare(self):
        new = snapshot(self.tree.claude_dir)
        with reference_patches()[0], reference_patches()[1], reference_patches()[2]:
            old = snapshot(self.tree.claude_dir)
        self.assertEqual(old, new)
        return new


class EquivalenceWithOddLines(EquivalenceBase):
    def test_odd_lines_same_result(self):
        lines = weird_lines()
        # sin las lineas que hacen fallar el esquema: el resultado completo se compara
        keep = [ln for ln in lines if b"m-ts" not in ln and b"m-future" not in ln and b"m-bad" not in ln
                and b"m-str" not in ln and b"m-bool" not in ln and b"m-nousage-obj" not in ln
                and b'"type": 5' not in ln]
        for n in range(3):
            write_raw(os.path.join(self.sub_dir("s1"), "agent-a%d.jsonl" % n), keep)
        # truncada al final, con una linea intermedia corrupta (archivo danado) y sin salto final
        write_raw(os.path.join(self.sub_dir("s1"), "agent-trunc.jsonl"), keep[:4], b'{"type": "assis',
                  final_newline=True)
        write_raw(os.path.join(self.sub_dir("s1"), "agent-nofinal.jsonl"), keep[:6], final_newline=False)
        write_raw(os.path.join(self.tree.folder(self.folder), "s1.jsonl"), keep)
        kind = self.compare()
        self.assertEqual(kind[0], "ok")
        quality = kind[3]
        self.assertGreater(quality["lineas corruptas"], 0)
        self.assertGreater(quality["lineas que no son objeto"], 0)
        self.assertGreater(quality["message.id repetido entre archivos"], 0)

    def test_schema_failures_same_error(self):
        write_raw(os.path.join(self.sub_dir("s1"), "agent-a1.jsonl"), weird_lines())
        self.assertEqual(self.compare()[0], "error")

    def test_oversize_line_same_result(self):
        big = b'{"type": "assistant", "timestamp": "2026-11-01T10:00:00Z", "pad": "' \
              + b"x" * (ur.MAX_LINE_BYTES + 10) + b'"}'
        good = json.dumps(us.assistant("m-1", "2026-11-01T10:00:01Z")).encode()
        write_raw(os.path.join(self.sub_dir("s1"), "agent-big.jsonl"), [good, big, good])
        res = self.compare()
        self.assertEqual(res[3]["lineas oversize descartadas"], 1)

    def test_hardlinks_same_result(self):
        lines = [json.dumps(us.assistant("m-%d" % i, "2026-11-01T10:00:%02dZ" % i)).encode() for i in range(5)]
        first = os.path.join(self.sub_dir("s1"), "agent-a.jsonl")
        write_raw(first, lines)
        os.link(first, os.path.join(self.sub_dir("s1"), "agent-b.jsonl"))
        res = self.compare()
        self.assertEqual(res[3]["hardlinks duplicados dentro de projects"], 1)

    def test_random_mix_same_result(self):
        import random
        rnd = random.Random(3)
        versions = ["2.1.300", "2.1.330", "x", "2.1.340"]
        models = ["claude-opus-4-1", "claude-sonnet-4-5", "raro raro"]
        for n in range(12):
            items = []
            for i in range(60):
                mid = "m-%d-%d" % (n % 4, i % 25)   # ids repetidos dentro y entre archivos
                items.append(json.dumps(us.assistant(
                    mid, "2026-11-%02dT10:%02d:00Z" % (1 + rnd.randrange(20), i % 60),
                    version=rnd.choice(versions), model=rnd.choice(models),
                    usage_value=us.usage(rnd.randrange(50), rnd.randrange(50)))).encode())
            write_raw(os.path.join(self.sub_dir("s%d" % (n % 3)), "agent-r%02d.jsonl" % n), items)
        res = self.compare()
        self.assertEqual(res[0], "ok")


class IterObjectsEquivalence(unittest.TestCase):
    """_iter_objects y la referencia producen los mismos objetos y los mismos contadores."""

    def run_both(self, data):
        import io
        out = []
        for fn in (ur._iter_objects, ref_iter_objects):
            info = ur._LineInfo()
            objs = list(fn(io.BytesIO(data), info))
            out.append((objs, info.corrupt, info.truncated_tail, info.oversize, info.not_object,
                        info.bytes_read))
        self.assertEqual(out[0], out[1])
        return out[0]

    def test_whitespace_variants(self):
        for variant in (b'{"a": 1}\n', b'{"a": 1}\r\n', b'{"a": 1}\x0c\n', b'{"a": 1}\x0b\n',
                        b' {"a": 1}\n', b'\t{"a": 1} \n', b'\x0c{"a": 1}\n', b'{"a": 1}',
                        b'\xef\xbb\xbf{"a": 1}\n', b'\n\n \n', b'{"a": 1} {"b": 2}\n', b'{"a":\n',
                        b'{"a": 1}\x00\n', b'\x00{\x00"\x00\n', b' \x00{\x00\n', b'{}\n[]\n"x"\n'):
            self.run_both(variant)
            self.run_both(variant + variant)

    def test_empty_and_only_newline(self):
        self.assertEqual(self.run_both(b"")[0], [])
        self.assertEqual(self.run_both(b"\n")[0], [])


# --- tope de trabajo ------------------------------------------------------------------------------

class WorkCaps(EquivalenceBase):
    N_LINES = 40

    def build(self, files=3):
        for n in range(files):
            items = [json.dumps(us.assistant("m-%d-%d" % (n, i), "2026-11-01T10:00:%02dZ" % (i % 60))).encode()
                     for i in range(self.N_LINES)]
            write_raw(os.path.join(self.sub_dir("s1"), "agent-w%d.jsonl" % n), items)
            with open(os.path.join(self.sub_dir("s1"), "agent-w%d.meta.json" % n), "w") as f:
                json.dump({"agentType": "forge"}, f)
        write_raw(os.path.join(self.tree.folder(self.folder), "s1.jsonl"),
                  [json.dumps(us.assistant("m-main-%d" % i, "2026-11-01T10:00:00Z", sidechain=False)).encode()
                   for i in range(self.N_LINES)])

    def test_one_json_loads_per_line(self):
        self.build()
        real = json.loads
        with mock.patch.object(ur.json, "loads", side_effect=real) as loads:
            ur.read_calls(self.tree.claude_dir, digest_key=KEY)
        # 3 archivos x N lineas + sesion principal x N, mas 3 metas (una por archivo de subagente)
        self.assertEqual(loads.call_count, 4 * self.N_LINES + 3)

    def test_labels_computed_once_per_distinct_value(self):
        """La cache dura todo el proceso: se vacia antes y se cuenta una clasificacion por valor distinto."""
        ur._cached_version_label.cache_clear()
        ur._cached_model_label.cache_clear()
        self.build(files=2)
        calls = []
        real = ur.hist_label

        def counting(field, value):
            calls.append((field, value))
            return real(field, value)

        with mock.patch.object(ur, "hist_label", counting):
            ur.read_calls(self.tree.claude_dir, digest_key=KEY)
        # una version y un modelo distintos en todo el arbol; sin cache serian ~N llamadas por archivo
        self.assertEqual(len(calls), 2)

    def test_cache_keys_are_short_and_bounded(self):
        """Ninguna clave de mas de 64 caracteres llega a la cache (se retendria todo el proceso)."""
        seen = []
        for name in ("_cached_version_label", "_cached_model_label"):
            self.assertEqual(getattr(ur, name).cache_parameters()["maxsize"], 256)
        spies = []
        for name in ("_cached_version_label", "_cached_model_label"):
            inner = getattr(ur, name)

            def spy(value, inner=inner):
                seen.append(value)
                return inner(value)

            spies.append(mock.patch.object(ur, name, spy))
        huge = "9" * (1024 * 1024)
        with spies[0], spies[1]:
            self.assertEqual(ur._version_label(huge), ur.OTHER_LABELS["version"])
            self.assertEqual(ur._model_label_of_line(huge), ur.OTHER_LABELS["model"])
            self.assertEqual(ur._version_label("2.1.330"), "2.1.330")
            self.assertEqual(ur._model_label_of_line("claude-opus-4-1"), "claude-opus-4-1")
            self.assertEqual(ur._version_label("9" * 65), ur.OTHER_LABELS["version"])
            self.assertEqual(ur._model_label_of_line("claude-" + "a" * 60), ur.OTHER_LABELS["model"])
        self.assertTrue(seen)
        self.assertTrue(all(len(v) <= 64 for v in seen), [len(v) for v in seen])

    def test_label_wrappers_equal_hist_label(self):
        for value in ("2.1.330", "x", "", "1.2.3-rc1", "9" * 70, "2.1.330\n"):
            self.assertEqual(ur._version_label(value), ur.hist_label("version", value))
        for value in ("claude-opus-4-1", "ZZ raro", "", "claude-" + "a" * 80, "<synthetic>",
                      "claude-sonnet-4-5-20250929"):
            self.assertEqual(ur._model_label_of_line(value), ur.hist_label("model", value))

    def test_longest_valid_values_reach_the_cache_whole(self):
        # El tope de longitud de las claves no puede recortar un valor valido: un modelo
        # de 64 caracteres y una version de 33 deben salir tal cual, como con hist_label.
        model = "claude-opus" + "-abcdefghijkl" * 3 + "-abcdefghijk" + "-a"
        version = "9999.9999.999999-alpha999.999.999"
        self.assertEqual(len(model), 64)
        self.assertEqual(len(version), 33)
        self.assertEqual(ur.hist_label("model", model), model)
        self.assertEqual(ur.hist_label("version", version), version)
        self.assertEqual(ur._model_label_of_line(model), model)
        self.assertEqual(ur._version_label(version), version)

    def test_token_tuple_equals_reference(self):
        values = (True, False, 1.0, "7", None, -1, 0, 5, 10 ** 30, [1], {"a": 1})
        for value in values:
            usage = us.usage(inp=value)
            self.assertEqual(ur._token_tuple(usage), ref_token_tuple(usage), repr(value))
        self.assertEqual(ur._token_tuple({}), ref_token_tuple({}))

    def test_big_read_buffer_for_transcripts(self):
        self.build(files=1)
        sizes = []
        real = os.fdopen

        def spy(fd, mode="r", buffering=-1, *a, **kw):
            sizes.append(buffering)
            return real(fd, mode, buffering, *a, **kw)

        with mock.patch.object(ur.os, "fdopen", spy):
            ur.read_calls(self.tree.claude_dir, digest_key=KEY)
        # transcripcion de subagente, meta y sesion principal: las dos transcripciones con buffer grande
        self.assertEqual(sum(1 for s in sizes if s >= 128 * 1024), 2)

    def test_opens_per_call_are_bounded(self):
        self.build(files=3)
        opens = []
        real = os.open

        def spy(path, *a, **kw):
            opens.append(path)
            return real(path, *a, **kw)

        with mock.patch.object(ur.os, "open", spy):
            ur.read_calls(self.tree.claude_dir, digest_key=KEY)
        # por subagente: transcripcion + meta; mas la sesion principal; nada mas
        self.assertEqual(len(opens), 3 * 2 + 1)


if __name__ == "__main__":
    unittest.main()
