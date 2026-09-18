"""The freeze, as a rule rather than a sticker on the fridge.

The scientific engine is closed: semantics qualified, assumptions closed
(fourteen, zero open), mutation 137/137 across the engine and the path around
it. Instrumentation qualification tests the plumbing and must not edit the
engine to make its own tests pass — that is how a freeze becomes decorative.

If instrumentation qualification genuinely requires an engine change, it is not
a quick fix. It is:

    freeze violation
      -> open an amendment in reactivity-power-design.md
      -> state which assumption turned out to be wrong
      -> re-run the gates that assumption supported
      -> update the pins below IN THAT COMMIT, with the amendment cited

Failing this test is therefore not a nuisance. It is the procedure starting.
"""

import hashlib
import pathlib
import unittest

#: sha256 of the frozen engine, pinned 2026-09-18.
FROZEN = {
    "extractor/model.py": "7e1d84732b827d8028e81d72d756755c4b3d42947e48616531c7894f6a8af955",
    "extractor/extract.py": "471407addcbcb8d3af501712c9c98c7b0bbd998b4a6a2420c5a9afc9ea2fe2fb",
    "extractor/estimands.py": "d690392cd1be8a2d25e550aab6a5acd1c8e520acd519ab795fef29f869afa57d"
}


class ExtractorFreezeTests(unittest.TestCase):

    def test_the_frozen_engine_is_unchanged(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        for name, expected in FROZEN.items():
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, (
                name + " changed while the extractor is frozen. If this is a "
                "deliberate amendment, follow the procedure in this module's "
                "docstring and update the pin in the same commit; if it is a "
                "convenience fix for an instrumentation test, it is the wrong fix"
            ))

    def test_the_freeze_covers_the_whole_engine(self):
        """A file added to `extractor/` outside the pins would be unfrozen by
        omission — the quietest way to keep editing a closed component."""
        root = pathlib.Path(__file__).resolve().parent.parent / "extractor"
        engine = {"extractor/" + p.name for p in root.glob("*.py")
                  if p.name != "__init__.py"}
        self.assertEqual(engine, set(FROZEN), "an engine module is not pinned")


if __name__ == "__main__":
    unittest.main()
