import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import update_aas_web_ui as updater


def release(tag, **extra):
    return {"tag_name": tag, "published_at": "2026-10-21T10:00:00Z", **extra}


class ReleaseTests(unittest.TestCase):
    def test_only_new_stable_releases_in_current_major_are_eligible(self):
        releases = [
            release("v2-261020"), release("v2-261013"), release("v2-260924"),
            release("v2-261022", draft=True), release("v2-261023", prerelease=True),
            release("v2-261024-rc1"), release("v3-261025"),
            release("v2-261032"), release("v2-261026", published_at=None),
            release("v2-261019"),
        ]
        self.assertEqual(updater.latest_release(releases, "v2-261013"), "v2-261020")

    def test_never_downgrades_or_updates_equal_version(self):
        self.assertIsNone(updater.latest_release([release("v2-261013")], "v2-261013"))
        self.assertIsNone(updater.latest_release([release("v2-260924")], "v2-261013"))

    def test_unsupported_current_tag_fails(self):
        with self.assertRaises(ValueError):
            updater.latest_release([release("v2-261020")], "latest")

    @patch.object(updater, "request_json")
    def test_fetches_all_release_pages(self, request):
        request.side_effect = [[release("v2-261020")] * 100, [release("v2-261019")]]
        self.assertEqual(len(updater.fetch_releases("test-token")), 101)
        self.assertIn("page=2", request.call_args.args[0])
        self.assertEqual(request.call_args.args[1]["Authorization"], "Bearer test-token")


class ImageTests(unittest.TestCase):
    @patch.object(updater, "request_json", return_value={"token": "registry-token"})
    @patch.object(updater.urllib.request, "urlopen")
    def test_manifest_is_checked_with_registry_token(self, urlopen, _):
        self.assertTrue(updater.image_available("v2-261020"))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.method, "HEAD")
        self.assertTrue(request.full_url.endswith("/eclipsebasyx/aas-gui/manifests/v2-261020"))
        self.assertEqual(request.get_header("Authorization"), "Bearer registry-token")

    @patch.object(updater, "request_json", return_value={"token": "registry-token"})
    @patch.object(updater.urllib.request, "urlopen")
    def test_only_missing_manifest_is_treated_as_unavailable(self, urlopen, _):
        for status in (401, 403, 404, 429, 500):
            with self.subTest(status=status):
                urlopen.side_effect = urllib.error.HTTPError("url", status, "error", {}, None)
                if status == 404:
                    self.assertFalse(updater.image_available("v2-261020"))
                else:
                    with self.assertRaises(urllib.error.HTTPError):
                        updater.image_available("v2-261020")


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.chart = self.root / "charts/basyx"
        self.chart.mkdir(parents=True)
        self.values = (
            "other:\n  image:\n    tag: keep-me\n"
            "aasWebGui:\n  enabled: false\n  image:\n"
            "    repository: eclipsebasyx/aas-gui\n    pullPolicy: Always\n"
            "    tag: v2-261013\n\n  imagePullSecrets: []\n"
            "next:\n  image:\n    tag: also-keep-me\n"
        )
        (self.chart / "values.yaml").write_text(self.values)
        (self.chart / "Chart.yaml").write_text('name: basyx\nversion: 3.16.9\nappVersion: "1.1.2"\n')
        (self.root / "README.md").write_text(
            "# BaSyx\n\n## Upgrade A Deployment\n\n### Upgrading to chart 3.16.9\n\nOld note.\n"
        )
        self.releases = [release("v2-261020")]

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_update_changes_only_ui_tag_chart_patch_and_upgrade_note(self, _):
        result = updater.prepare_update(self.root, self.releases, lambda _: True)
        self.assertEqual(result["tag"], "v2-261020")
        self.assertEqual(result["chart-version"], "3.16.10")
        self.assertEqual((self.chart / "values.yaml").read_text(), self.values.replace("v2-261013", "v2-261020"))
        self.assertEqual((self.chart / "Chart.yaml").read_text(), 'name: basyx\nversion: 3.16.10\nappVersion: "1.1.2"\n')
        readme = (self.root / "README.md").read_text()
        self.assertIn("Chart 3.16.10 updates the default AAS Web UI image to `v2-261020`.", readme)
        self.assertLess(readme.index("### Upgrading to chart 3.16.10"), readme.index("### Upgrading to chart 3.16.9"))
        before = self.snapshot()
        self.assertEqual(updater.prepare_update(self.root, self.releases, lambda _: self.fail("unnecessary image lookup")), {})
        self.assertEqual(self.snapshot(), before)

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_missing_image_leaves_all_files_unchanged(self, _):
        before = self.snapshot()
        self.assertEqual(updater.prepare_update(self.root, self.releases, lambda _: False), {})
        self.assertEqual(self.snapshot(), before)

    def test_invalid_chart_or_readme_causes_no_partial_edits(self):
        for path, text in [(self.chart / "Chart.yaml", "version: 3.16.9-rc1\n"), (self.root / "README.md", "# Missing notes\n")]:
            with self.subTest(path=path):
                original = path.read_text()
                path.write_text(text)
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    updater.prepare_update(self.root, self.releases, lambda _: True)
                self.assertEqual(self.snapshot(), before)
                path.write_text(original)

    def test_custom_repository_is_rejected(self):
        (self.chart / "values.yaml").write_text(self.values.replace(updater.IMAGE, "custom/image"))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            updater.prepare_update(self.root, self.releases, lambda _: True)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
