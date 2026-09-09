"""Catalog.hs (annotation-web dogfood surface) must carry the RU source texts of
data/pilot/v0.1/form/dogfood-v7-items.yaml byte for byte, with the same ids and
the same target. Cross-language, read-only; skipped when run outside the repo."""

import re
import unittest
from pathlib import Path

from metrics.materialize import parse_dogfood_yaml

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "src/annotation-web/src/Catalog.hs"
YAML = ROOT / "data/pilot/v0.1/form/dogfood-v7-items.yaml"


def parse_catalog(text: str) -> list[dict]:
    items = []
    for block in re.split(r"\n  , Item\n|\n  \[ Item\n", text)[1:]:
        iid = re.search(r'itemId = "([^"]+)"', block).group(1)
        messages = [{"author": a.lower(), "text": t, "target": flag == "True"}
                    for a, t, flag in re.findall(r'Message "([AB])" "((?:[^"\\]|\\.)*)" (True|False)', block)]
        items.append({"item_id": iid, "messages": messages})
    return items


class CatalogMatchesDogfoodV7(unittest.TestCase):
    @unittest.skipUnless(CATALOG.exists() and YAML.exists(), "repository files not present")
    def test_catalog_equals_v7_yaml(self):
        _, yaml_items = parse_dogfood_yaml(YAML.read_text(encoding="utf-8"))
        catalog = parse_catalog(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual([i["item_id"] for i in catalog], [i["item_id"] for i in yaml_items])
        for c, y in zip(catalog, yaml_items):
            self.assertEqual([(m["author"], m["text"]) for m in c["messages"]],
                             [(m["author"], m["text"]) for m in y["messages"]], c["item_id"])
            self.assertEqual([m["target"] for m in c["messages"]].index(True), y["target_index"], c["item_id"])


if __name__ == "__main__":
    unittest.main()
