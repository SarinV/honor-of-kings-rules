"""Regression tests for dangerous routing expansion and incomplete updates."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update", ROOT / "scripts/update.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))["sources"]


class RuleSafetyTests(unittest.TestCase):
    def test_preserves_suffix_semantics_and_ignores_comments(self):
        records = update.parse_rules("\ufeff#!name=王者\nDOMAIN-SUFFIX, SGAMEGLOBAL.COM\nDOMAIN, login.example.com # comment\n", "classical")
        accepted, excluded = update.select_rules(SOURCES[0], records, POLICY)
        self.assertEqual([record["rule"] for record in accepted], ["DOMAIN-SUFFIX,sgameglobal.com", "DOMAIN,login.example.com"])
        self.assertEqual(excluded, [])

    def test_known_upstream_broad_rules_never_leak_into_outputs(self):
        source = "\n".join([
            "DOMAIN-SUFFIX,sgameglobal.com", "DOMAIN-SUFFIX,intlgame.com",
            "IP-CIDR,183.192.65.101/16,no-resolve", "IP-CIDR,43.132.55.55/16,no-resolve",
            "DOMAIN-KEYWORD,sgameglobal.com", "DOMAIN-SUFFIX,appsflyersdk.com", "DOMAIN-SUFFIX,qq.com",
        ])
        accepted, excluded = update.select_rules(SOURCES[0], update.parse_rules(source, "classical"), POLICY)
        self.assertEqual({record["rule"] for record in accepted}, {"DOMAIN-SUFFIX,sgameglobal.com", "DOMAIN-SUFFIX,intlgame.com"})
        self.assertEqual(len(excluded), 5)

    def test_shared_services_are_opt_in_and_do_not_import_other_games(self):
        text = "gcloudcs.com @!cn # shared\nwegame.com\ninclude:pubg\nfull:login.gcloudsdk.com\n"
        accepted, excluded = update.select_rules(SOURCES[1], update.parse_rules(text, "geosite"), POLICY)
        self.assertEqual([item["rule"] for item in accepted], ["DOMAIN-SUFFIX,gcloudcs.com"])
        self.assertEqual(accepted[0]["profile"], "extended-only")
        self.assertEqual(len(excluded), 3)

    def test_unexpected_html_catch_all_and_policy_injection_fail(self):
        for text in ["<html>error</html>", "MATCH,DIRECT", "DOMAIN-SUFFIX,example.com,PROXY", "DOMAIN-SUFFIX,*", "DOMAIN-SUFFIX,com", "DOMAIN-SUFFIX,-bad.example", "# nothing"]:
            with self.subTest(text=text), self.assertRaises(update.UpdateError):
                update.parse_rules(text, "classical")

    def test_disappearing_game_anchor_fails(self):
        bundles = [(SOURCES[0], b"DOMAIN-SUFFIX,other-game.example\n", {})]
        with self.assertRaisesRegex(update.UpdateError, "Required HOK"):
            update.build_outputs(bundles, POLICY)

    def test_mass_deletion_cannot_be_hidden_by_new_additions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rules").mkdir()
            (root / "rules/HonorOfKings.list").write_text("DOMAIN,a.example\nDOMAIN,b.example\nDOMAIN,c.example\n", encoding="utf-8")
            with self.assertRaisesRegex(update.UpdateError, "Too many removed"):
                update.check_removals(root, {"HonorOfKings": ["DOMAIN,x.example", "DOMAIN,y.example", "DOMAIN,z.example"]}, POLICY)

    def test_upstream_failure_preserves_every_published_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in ("sources.json", "policy.json"):
                shutil.copyfile(ROOT / file, root / file)
            (root / "rules").mkdir()
            (root / "rules/HonorOfKings.list").write_text("last good version\n", encoding="utf-8")
            before = {str(file.relative_to(root)): file.read_bytes() for file in root.rglob("*") if file.is_file()}

            def failed_fetch(source, *args):
                if source["id"] == SOURCES[1]["id"]:
                    raise update.UpdateError("Simulated timeout")
                return source, b"DOMAIN-SUFFIX,sgameglobal.com\nDOMAIN-SUFFIX,intlgame.com\n", {}

            with self.assertRaisesRegex(update.UpdateError, "Simulated timeout"):
                update.run(root=root, fetcher=failed_fetch)
            after = {str(file.relative_to(root)): file.read_bytes() for file in root.rglob("*") if file.is_file()}
            self.assertEqual(before, after)

    def test_download_retries_transient_failure(self):
        class Response:
            url = "https://raw.githubusercontent.com/owner/repo/main/rule.list"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, limit):
                return b"DOMAIN-SUFFIX,sgameglobal.com\n"

        with patch.object(update, "urlopen", side_effect=[update.URLError("temporary"), Response()]) as mocked, patch.object(update.time, "sleep"):
            content = update.download(Response.url)
            self.assertIn(b"sgameglobal.com", content)
            self.assertEqual(mocked.call_count, 2)

    def test_cross_origin_redirect_is_blocked_before_following(self):
        request = update.Request("https://api.github.com/repos/owner/repo", headers={"Authorization": "Bearer test-only"})
        with self.assertRaisesRegex(update.UpdateError, "cross-origin"):
            update.SameOriginRedirect().redirect_request(request, None, 302, "Found", {}, "https://example.com/collect")

    def test_committed_snapshots_are_reproducible(self):
        # This uses the real source snapshots, parser, selection policy and generated outputs.
        if not (ROOT / "data/status.json").exists():
            self.skipTest("Initial upstream fetch has not run yet")
        update.run(root=ROOT, offline=True, check=True)


if __name__ == "__main__":
    unittest.main()
