import json
import os
import shutil
import tempfile
import unittest

from core import load, model

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "fixtures")


class ModelTests(unittest.TestCase):
    def test_identifier_and_title_are_required(self):
        with self.assertRaises(model.ModelError):
            model.UserNeed("", "title")
        with self.assertRaises(model.ModelError):
            model.UserNeed("UN-001", "")

    def test_unknown_severity_is_rejected(self):
        with self.assertRaises(model.ModelError):
            model.Hazard("HAZ-001", "h", "apocalyptic", "remote")

    def test_unknown_probability_is_rejected(self):
        with self.assertRaises(model.ModelError):
            model.Hazard("HAZ-001", "h", "serious", "sometimes")

    def test_unknown_run_result_is_rejected(self):
        with self.assertRaises(model.ModelError):
            model.TestRun("RUN-001", "VER-001", "mostly-fine", "2026-01-01")

    def test_duplicate_id_is_rejected(self):
        d = model.DesignFile()
        d.add(model.UserNeed("UN-001", "a"))
        with self.assertRaises(model.ModelError):
            d.add(model.UserNeed("UN-001", "b"))

    def test_severity_ordering(self):
        low = model.Hazard("H-1", "x", "minor", "remote")
        high = model.Hazard("H-2", "x", "catastrophic", "remote")
        self.assertLess(low.severity_index(), high.severity_index())

    def test_identifier_format_check(self):
        self.assertTrue(model.UserNeed("UN-001", "x").well_formed_id())
        self.assertTrue(model.UserNeed("SRS-1234", "x").well_formed_id())
        self.assertFalse(model.UserNeed("un-001", "x").well_formed_id())
        self.assertFalse(model.UserNeed("REQUIREMENT-1", "x").well_formed_id())

    def test_extra_fields_are_preserved(self):
        need = model.UserNeed("UN-001", "x", author="mg", source="interview")
        self.assertEqual(need.extra["author"], "mg")

    def test_counts_and_len(self):
        d = model.DesignFile()
        d.add(model.UserNeed("UN-001", "a"))
        d.add(model.Requirement("SRS-001", "b"))
        self.assertEqual(len(d), 2)
        self.assertEqual(d.counts()["needs"], 1)


class LoadTests(unittest.TestCase):
    def test_loads_the_fixture(self):
        design = load.load(os.path.join(FIXTURES, "design.json"))
        counts = design.counts()
        self.assertEqual(counts["needs"], 6)
        self.assertEqual(counts["requirements"], 14)
        self.assertEqual(counts["hazards"], 5)
        self.assertEqual(counts["verifications"], 13)
        self.assertEqual(counts["runs"], 15)

    def test_missing_required_field_names_the_section_and_entry(self):
        with self.assertRaises(load.LoadError) as ctx:
            load.from_dict({"needs": [{"title": "no id"}]})
        self.assertIn("needs", str(ctx.exception))

    def test_bad_severity_names_the_offending_entry(self):
        with self.assertRaises(load.LoadError) as ctx:
            load.from_dict({"hazards": [
                {"id": "HAZ-001", "title": "h", "severity": "nope", "probability": "remote"}]})
        self.assertIn("HAZ-001", str(ctx.exception))
        self.assertIn("severity", str(ctx.exception))

    def test_unknown_section_is_rejected(self):
        with self.assertRaises(load.LoadError) as ctx:
            load.from_dict({"widgets": []})
        self.assertIn("widgets", str(ctx.exception))

    def test_underscore_sections_are_allowed_as_comments(self):
        design = load.from_dict({"_comment": "notes for humans", "needs": []})
        self.assertEqual(len(design), 0)

    def test_top_level_must_be_an_object(self):
        with self.assertRaises(load.LoadError):
            load.from_dict([])

    def test_dangling_links_load_without_error(self):
        # The loader deliberately does not resolve links. An incomplete design
        # file has to load so the analyser can report on it.
        design = load.from_dict({
            "requirements": [{"id": "SRS-001", "title": "x", "needs": ["UN-404"]}],
        })
        self.assertEqual(len(design.requirements), 1)

    def test_optional_fields_default_sensibly(self):
        design = load.from_dict({"requirements": [{"id": "SRS-001", "title": "x"}]})
        req = design.requirements["SRS-001"]
        self.assertEqual(req.needs, [])
        self.assertFalse(req.safety_related)

    def test_invalid_json_is_reported_clearly(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "broken.json")
            with open(path, "w") as handle:
                handle.write("{not json")
            with self.assertRaises(load.LoadError) as ctx:
                load.load(path)
            self.assertIn("not valid JSON", str(ctx.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class LoadDirTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, name, payload):
        with open(os.path.join(self.dir, name), "w") as handle:
            json.dump(payload, handle)

    def test_merges_multiple_files(self):
        self._write("a.json", {"needs": [{"id": "UN-001", "title": "a"}]})
        self._write("b.json", {"requirements": [{"id": "SRS-001", "title": "b", "needs": ["UN-001"]}]})
        design = load.load_dir(self.dir)
        self.assertEqual(design.counts()["needs"], 1)
        self.assertEqual(design.counts()["requirements"], 1)

    def test_duplicate_ids_across_files_are_rejected(self):
        self._write("a.json", {"needs": [{"id": "UN-001", "title": "a"}]})
        self._write("b.json", {"needs": [{"id": "UN-001", "title": "b"}]})
        with self.assertRaises(load.LoadError) as ctx:
            load.load_dir(self.dir)
        self.assertIn("UN-001", str(ctx.exception))

    def test_non_json_files_are_ignored(self):
        self._write("a.json", {"needs": [{"id": "UN-001", "title": "a"}]})
        with open(os.path.join(self.dir, "notes.txt"), "w") as handle:
            handle.write("ignore me")
        design = load.load_dir(self.dir)
        self.assertEqual(design.counts()["needs"], 1)


if __name__ == "__main__":
    unittest.main()
