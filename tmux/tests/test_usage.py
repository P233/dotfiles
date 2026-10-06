import datetime
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/usage.py"
spec = importlib.util.spec_from_file_location("tmux_usage", SCRIPT)
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)
NOW = 1_800_000_000
NOW_ISO = datetime.datetime.fromtimestamp(NOW, datetime.timezone.utc).isoformat()


def window(minutes, used, **extra):
    return {"windowMinutes": minutes, "usedPercent": used, **extra}


def visible(text):
    return re.sub(r"#\[[^]]*\]", "", text)


def summary(text):
    return " ".join(visible(text).split())


class QuotaDisplayTests(unittest.TestCase):
    def test_claude_shows_both_remaining_windows(self):
        cache = {"updated_at": NOW, "windows": usage.quota_windows({
            "primary": window(300, 43), "secondary": window(10080, 21),
        })}
        self.assertEqual(summary(usage.render("claude", cache, NOW)), "Claude 57% — 79% —")

    def test_weekly_primary_keeps_claude_five_hour_position_unknown(self):
        cache = {"updated_at": NOW, "windows": usage.quota_windows({
            "primary": window(10080, 16),
        })}
        self.assertEqual(summary(usage.render("claude", cache, NOW)), "Claude — — 84% —")
        self.assertEqual(summary(usage.render("codex", cache, NOW)), "Codex 84% —")

    def test_codex_shows_only_five_hour_percentage_even_when_weekly_quota_is_low(self):
        cache = {"updated_at": NOW, "windows": usage.quota_windows({
            "primary": window(300, 22), "secondary": window(10080, 92),
        })}
        self.assertEqual(summary(usage.render("codex", cache, NOW)), "Codex 78% —")

    def test_zero_used_is_real_but_a_placeholder_is_unknown(self):
        cache = {"updated_at": NOW, "windows": usage.quota_windows({
            "primary": window(300, 0),
            "secondary": window(10080, 0, isSyntheticPlaceholder=True),
        })}
        self.assertEqual(summary(usage.render("claude", cache, NOW)), "Claude 100% — — —")

    def test_model_specific_weekly_quota_is_not_the_account_weekly_quota(self):
        cache = {"updated_at": NOW, "windows": usage.quota_windows({
            "primary": None, "secondary": None, "tertiary": window(10080, 21),
        })}
        self.assertEqual(summary(usage.render("claude", cache, NOW)), "Claude — — — —")

    def test_progress_endpoints_and_unknown_keep_the_same_width(self):
        for remaining, expected in ((0, " 0%       — "),
                                    (50, " 50%      — "),
                                    (100, " 100%     — ")):
            cache = {"updated_at": NOW, "windows": {"5h": {
                "remaining": remaining, "resets_at": None,
            }}}
            with self.subTest(remaining=remaining):
                self.assertEqual(visible(usage.render("codex", cache, NOW)), "Codex " + expected)
                self.assertEqual(len(expected), 12)
                self.assertEqual(len(visible(usage.render("codex", cache, NOW + 301))), 18)
        self.assertEqual(visible(usage.render("codex", {}, NOW)), "Codex  —        — ")

    def test_fill_boundary_changes_background_but_keeps_percentage_text_white(self):
        for provider, color in (("codex", "#74aaff"), ("claude", "#d97757")):
            cache = {"updated_at": NOW, "windows": {
                "5h": {"remaining": 20, "resets_at": None},
                "7d": {"remaining": 20, "resets_at": None},
            }}
            with self.subTest(provider=provider):
                # At 20%, the fill ends inside "20%", but its text stays white.
                bar = (f"#[nobold,fg=#ffffff,bg={color}] 2"
                       "#[bg=#44475a]0%      — #[default]")
                expected = f"{provider.title()} {bar}" + (f" {bar}" if provider == "claude" else "")
                self.assertEqual(usage.render(provider, cache, NOW), expected)

    def test_countdown_text_stays_white_when_fill_ends_inside_it(self):
        cache = {"updated_at": NOW, "windows": {
            "5h": {"remaining": 80, "resets_at": NOW + 120},
        }}
        self.assertEqual(usage.render("codex", cache, NOW),
                         "Codex #[nobold,fg=#ffffff,bg=#74aaff] 80%     2"
                         "#[bg=#44475a]m #[default]")

    def test_cli_renders_both_inline_claude_windows_from_the_shared_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_dir = root / "cache/tmux-usage"
            cache_dir.mkdir(parents=True)
            cache = {"updated_at": time.time(), "attempted_at": time.time(), "windows": {
                "5h": {"remaining": 57, "resets_at": None},
                "7d": {"remaining": 79, "resets_at": None},
            }}
            usage.write_cache(cache_dir / "claude.json", cache)
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), "claude"],
                                    env={"XDG_CACHE_HOME": str(root / "cache")},
                                    capture_output=True, text=True, check=True)
            # A Claude status read never queries, so it prints the cached line once.
            self.assertEqual(visible(result.stdout), "Claude " + " 57%      — "
                             + " " + " 79%      — " + "\n")

    def test_invalid_measurements_remain_unknown(self):
        for invalid in (None, True, -1, 101, 10 ** 400, float("nan"),
                        float("inf"), -float("inf"), "43"):
            with self.subTest(invalid=invalid):
                windows = usage.quota_windows({"primary": window(300, invalid)})
                self.assertEqual(windows, {})

    def test_reset_deadline_invalidates_the_old_percentage(self):
        cache = {"updated_at": NOW, "windows": {
            "5h": {"remaining": 57, "resets_at": NOW},
            "7d": {"remaining": 79, "resets_at": NOW + 1000},
        }}
        self.assertEqual(summary(usage.render("claude", cache, NOW)), "Claude \uf021 0m 79% 17m")

    def test_codex_reset_does_not_switch_to_weekly_quota(self):
        cache = {"updated_at": NOW, "windows": {
            "5h": {"remaining": 57, "resets_at": NOW},
            "7d": {"remaining": 79, "resets_at": NOW + 86400},
        }}
        self.assertEqual(summary(usage.render("codex", cache, NOW)), "Codex \uf021 0m")

    def test_countdown_uses_short_units_and_updates_without_refresh(self):
        for seconds, expected in ((1, "1m"), (60, "1m"), (61, "2m"),
                                  (3599, "1h"), (7200, "2h"),
                                  (86399, "1d"), (3 * 86400, "3d")):
            cache = {"updated_at": NOW, "windows": {
                "5h": {"remaining": 78, "resets_at": NOW + seconds},
            }}
            with self.subTest(seconds=seconds):
                self.assertEqual(summary(usage.render("codex", cache, NOW)), f"Codex 78% {expected}")
        cache = {"updated_at": NOW, "windows": {
            "5h": {"remaining": 78, "resets_at": NOW + 120},
        }}
        self.assertEqual(summary(usage.render("codex", cache, NOW)), "Codex 78% 2m")
        self.assertEqual(summary(usage.render("codex", cache, NOW + 60)), "Codex 78% 1m")

    def test_countdown_right_padding_and_width_across_units_and_reset_states(self):
        for seconds, ending in ((None, "    — "), (0, "   0m "),
                                (60, "   1m "), (3540, "  59m "),
                                (3600, "   1h "), (86400, "   1d ")):
            cache = {"updated_at": NOW, "windows": {
                "5h": {"remaining": 78, "resets_at": None if seconds is None else NOW + seconds},
            }}
            with self.subTest(seconds=seconds):
                text = visible(usage.render("codex", cache, NOW))
                self.assertEqual(len(text), 18)
                self.assertEqual(text[-6:], ending)

    def test_each_claude_bar_has_its_own_reset_countdown(self):
        cache = {"updated_at": NOW, "windows": usage.quota_windows({
            "primary": window(300, 43, resetsAt=datetime.datetime.fromtimestamp(
                NOW + 7200, datetime.timezone.utc).isoformat()),
            "secondary": window(10080, 21, resetsAt=datetime.datetime.fromtimestamp(
                NOW + 3 * 86400, datetime.timezone.utc).isoformat()),
        })}
        self.assertEqual(summary(usage.render("claude", cache, NOW)), "Claude 57% 2h 79% 3d")

    def test_longest_percentage_and_countdown_fit_twelve_cells(self):
        cache = {"updated_at": NOW, "error": "ValueError", "windows": {
            "5h": {"remaining": 100, "resets_at": NOW + 3540},
        }}
        self.assertEqual(visible(usage.render("codex", cache, NOW)), "Codex  100%~  59m ")

    def test_an_unexpected_far_future_deadline_cannot_widen_the_bar(self):
        cache = {"updated_at": NOW, "error": "ValueError", "windows": {
            "5h": {"remaining": 100, "resets_at": NOW + 1000 * 86400},
        }}
        self.assertEqual(visible(usage.render("codex", cache, NOW)), "Codex  100%~ >99d ")

    def test_codex_credit_balance_follows_its_bar_in_compact_form(self):
        windows = {"7d": {"remaining": 84, "resets_at": NOW + 86400}}
        for credits, expected in ((850, " 850"), (999.4, " 999"), (999.5, " 1.0k"),
                                  (62096.2, " 62.1k"), (999_949, " 999.9k"),
                                  (999_950, " 1.0M"), (0, "")):
            with self.subTest(credits=credits):
                cache = {"updated_at": NOW, "credits": credits, "windows": windows}
                self.assertEqual(summary(usage.render("codex", cache, NOW)), "Codex 84% 1d" + expected)
        cache = {"updated_at": NOW, "credits": 62096.2, "windows": windows}
        self.assertEqual(summary(usage.render("codex", cache, NOW + 901)), "Codex — —")
        self.assertEqual(summary(usage.render("claude", cache, NOW)), "Claude — — 84% 1d")

    def test_stale_and_expired_data_are_visible(self):
        cache = {"updated_at": NOW, "windows": {
            "7d": {"remaining": 84, "resets_at": None},
        }}
        self.assertEqual(summary(usage.render("codex", cache, NOW + 301)), "Codex 84%~ —")
        self.assertEqual(summary(usage.render("codex", cache, NOW + 901)), "Codex — —")

    def test_refresh_caches_only_quota_and_is_rate_limited(self):
        row = {"provider": "codex", "identity": {"email": "fixture@example.invalid"},
               "credits": {"remaining": 62096.2, "events": [{"id": "fixture@example.invalid"}]},
               "usage": {"updatedAt": NOW_ISO, "primary": window(300, 43),
                         "secondary": window(10080, 21)}}
        result = subprocess.CompletedProcess([], 0, json.dumps([row]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex.json"
            with patch.object(usage.time, "time", return_value=NOW), \
                    patch.object(usage, "fetch", return_value=result) as fetch:
                usage.refresh("codex", path)
                usage.refresh("codex", path)
                fetch.assert_called_once_with("codex")
            cache = json.loads(path.read_text())
            self.assertEqual(set(cache), {"attempted_at", "updated_at", "windows", "credits"})
            self.assertNotIn("fixture@example.invalid", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_only_a_valid_codex_credit_balance_is_kept(self):
        for provider, credits, expected in (
                ("codex", {"remaining": 62096.2, "balanceReadSucceeded": True}, 62096.2),
                ("codex", {"remaining": 62096.2, "balanceReadSucceeded": False}, None),
                ("codex", {"remaining": -1}, None), ("codex", {"remaining": True}, None),
                ("codex", {"remaining": "62096"}, None), ("codex", None, None),
                ("claude", {"remaining": 62096.2}, None)):
            row = {"provider": provider, "credits": credits,
                   "usage": {"updatedAt": NOW_ISO, "primary": window(300, 43)}}
            with self.subTest(provider=provider, credits=credits):
                measurement = usage.parse_usage(provider, subprocess.CompletedProcess(
                    [], 0, json.dumps([row])))
                self.assertEqual(measurement.get("credits"), expected)

    def test_failed_refresh_retains_data_with_a_stale_marker(self):
        cache = {"updated_at": NOW, "windows": {
            "7d": {"remaining": 84, "resets_at": None},
        }}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex.json"
            usage.write_cache(path, cache)
            with patch.object(usage.time, "time", return_value=NOW + 1), \
                    patch.object(usage, "fetch", side_effect=ValueError("fixture provider error")):
                result, failure = usage.refresh("codex", path)
            self.assertEqual(failure, "ValueError")
            self.assertEqual(summary(usage.render("codex", result, NOW + 1)), "Codex 84%~ —")
            self.assertNotIn("fixture provider error", path.read_text())

    def test_unusable_provider_results_are_rejected(self):
        measured = {"provider": "codex", "usage": {"updatedAt": NOW_ISO, "primary": window(300, 43)}}
        for stdout, returncode in (("", 0), (json.dumps([None, "invalid"]), 0),
                                   (json.dumps({"provider": "codex", "usage": []}), 0),
                                   (json.dumps({"provider": "codex", "usage": "invalid"}), 0),
                                   (json.dumps({**measured, "error": "fixture"}), 0),
                                   (json.dumps(measured), 1)):
            with self.subTest(stdout=stdout, returncode=returncode), self.assertRaises(ValueError):
                usage.parse_usage("codex", subprocess.CompletedProcess([], returncode, stdout))

    def test_invalid_cache_shapes_are_discarded_before_rendering(self):
        invalid = [[], {"updated_at": "broken"}, {"attempted_at": True},
                   {"updated_at": float("nan")}, {"windows": []},
                   {"windows": {"5h": "invalid"}},
                   {"windows": {"5h": {"remaining": 101}}},
                   {"windows": {"5h": {"remaining": True}}},
                   {"windows": {"5h": {"remaining": 78, "resets_at": "bad"}}},
                   {"windows": {"5h": {"remaining": 78, "updated_at": None}}},
                   {"credits": True}, {"credits": -1}, {"credits": "62096"},
                   {"credits": 1e10}, {"error": {"message": "not sanitized"}}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex.json"
            for cache in invalid:
                with self.subTest(cache=cache):
                    path.write_text(json.dumps(cache))
                    loaded = usage.read_cache(path)
                    self.assertEqual(loaded, {})
                    self.assertEqual(summary(usage.render("codex", loaded, NOW)), "Codex — —")

    def test_cli_discards_a_null_window_timestamp_without_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory) / "tmux-usage"
            cache_dir.mkdir()
            usage.write_cache(cache_dir / "claude.json", {"updated_at": NOW, "windows": {
                "5h": {"remaining": 50, "resets_at": None, "updated_at": None},
            }})
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), "claude"],
                                    env={"XDG_CACHE_HOME": directory}, capture_output=True,
                                    text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(summary(result.stdout), "Claude — — — —")
            self.assertEqual(result.stderr, "")

    def test_cache_reader_keeps_only_sanitized_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex.json"
            # Earlier caches also stored an exhaustion marker in each window.
            usage.write_cache(path, {"updated_at": NOW, "identity": "fixture@example.invalid",
                                     "credits": 62096.2,
                                     "windows": {"5h": {"remaining": 0, "resets_at": None,
                                                        "exhausted": True,
                                                        "identity": "fixture@example.invalid"}}})
            self.assertEqual(set(usage.read_cache(path)), {"updated_at", "windows", "credits"})
            self.assertEqual(set(usage.read_cache(path)["windows"]["5h"]), {"remaining", "resets_at"})

    def test_timeout_stops_the_probe_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "child-survived"
            binary = root / "probe"
            child = f"import time,pathlib; time.sleep(0.6); pathlib.Path({str(marker)!r}).touch()"
            binary.write_text("#!/usr/bin/python3\nimport subprocess,time\n"
                              f"subprocess.Popen(['/usr/bin/python3', '-c', {child!r}])\n"
                              "time.sleep(5)\n")
            binary.chmod(0o700)
            with patch.object(usage, "BINARY", binary), patch.object(usage, "FETCH_TIMEOUT", 0.2):
                with self.assertRaises(subprocess.TimeoutExpired):
                    usage.fetch("claude")
            time.sleep(0.7)
            self.assertFalse(marker.exists(), "the timed-out child continued running")


if __name__ == "__main__":
    unittest.main()
