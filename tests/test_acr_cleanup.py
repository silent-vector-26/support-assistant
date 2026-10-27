import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from acr_cleanup import plan_cleanup  # noqa: E402


def manifest(digest, tags, day):
    return {"digest": digest, "tags": tags, "lastUpdateTime": f"2026-10-{day:02d}T00:00:00Z"}


class AcrCleanupPlanTests(unittest.TestCase):
    def setUp(self):
        self.manifests = [
            manifest("sha256:a", ["t1"], 1),
            manifest("sha256:b", ["t2"], 2),
            manifest("sha256:c", ["t3"], 3),
            manifest("sha256:d", [], 4),
            manifest("sha256:e", ["t5"], 5),
        ]

    def digests(self, items):
        return {m["digest"] for m in items}

    def test_preserves_running_and_newest_rollbacks(self):
        preserved, deletable = plan_cleanup(self.manifests, "t5", keep=2)
        self.assertEqual(self.digests(preserved), {"sha256:e", "sha256:c", "sha256:b"})
        self.assertEqual(self.digests(deletable), {"sha256:a", "sha256:d"})

    def test_running_image_kept_even_when_oldest(self):
        preserved, deletable = plan_cleanup(self.manifests, "t1", keep=1)
        self.assertIn("sha256:a", self.digests(preserved))
        self.assertIn("sha256:e", self.digests(preserved))
        self.assertNotIn("sha256:a", self.digests(deletable))

    def test_digest_shared_with_preserved_tag_is_not_deleted(self):
        shared = [manifest("sha256:x", ["live", "old"], 1), manifest("sha256:y", ["new"], 2)]
        _, deletable = plan_cleanup(shared, "live", keep=1)
        self.assertEqual(deletable, [])

    def test_refuses_when_running_tag_missing_or_unknown(self):
        with self.assertRaises(ValueError):
            plan_cleanup(self.manifests, "missing", keep=2)
        with self.assertRaises(ValueError):
            plan_cleanup(self.manifests, "", keep=2)

    def test_requires_positive_keep(self):
        with self.assertRaises(ValueError):
            plan_cleanup(self.manifests, "t5", keep=0)


if __name__ == "__main__":
    unittest.main()
