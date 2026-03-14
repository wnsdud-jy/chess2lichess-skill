from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


def load_module():
    module_path = (
        Path(__file__).resolve().parent.parent
        / "c2l"
        / "scripts"
        / "run_c2l_analysis.py"
    )
    spec = importlib.util.spec_from_file_location("run_c2l_analysis", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


class RunC2LAnalysisTests(unittest.TestCase):
    def make_stub_command(self, payload: dict[str, object]) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        script_path = Path(temp_dir.name) / "stub_c2l.py"
        script_path.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env python3
                import json
                payload = {payload!r}
                print("noise before json")
                print(json.dumps(payload))
                """
            ),
            encoding="utf-8",
        )
        os.chmod(script_path, 0o755)
        return f"{sys.executable} {script_path}"

    def test_parse_c2l_json_line_ignores_noise(self):
        payload = MODULE.parse_c2l_json_line(
            'noise\n{"success": false}\n{"success": true, "analysis_url": "https://lichess.org/abc"}\n'
        )
        self.assertTrue(payload["success"])
        self.assertEqual(payload["analysis_url"], "https://lichess.org/abc")

    def test_extract_lichess_game_id(self):
        self.assertEqual(
            MODULE.extract_lichess_game_id("https://lichess.org/abc123"),
            "abc123",
        )
        self.assertEqual(
            MODULE.extract_lichess_game_id("https://lichess.org/analysis/xyz789"),
            "xyz789",
        )
        self.assertIsNone(
            MODULE.extract_lichess_game_id(
                "https://lichess.org/analysis/standard/rnbqkbnr"
            )
        )

    def test_normalize_short_chesscom_url(self):
        self.assertEqual(
            MODULE.normalize_chesscom_game_url(
                "https://www.chess.com/game/123456789?tab=review"
            ),
            "https://www.chess.com/game/live/123456789?tab=review",
        )

    def test_resolve_c2l_command_prefers_explicit_override(self):
        command, source = MODULE.resolve_c2l_command(
            explicit_command=f"{sys.executable} /tmp/fake-c2l.py"
        )
        self.assertEqual(source, "explicit")
        self.assertEqual(command[0], sys.executable)

    def test_resolve_c2l_command_reports_install_guidance_when_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(MODULE.shutil, "which", return_value=None):
                with self.assertRaises(FileNotFoundError) as excinfo:
                    MODULE.resolve_c2l_command(repo_root=None)

        self.assertIn("c2l is not installed", str(excinfo.exception))
        self.assertIn("C2L_COMMAND", str(excinfo.exception))

    def test_analyze_url_normalizes_short_input_before_running_c2l(self):
        payload = {
            "input_url": "https://www.chess.com/game/live/123456789",
            "success": True,
            "game_id": "abc123",
            "analysis_url": "https://lichess.org/abc123",
            "pgn": "1. e4 e5 2. Nf3 Nc6",
            "retries": 0,
            "error": None,
        }

        with mock.patch.object(MODULE, "resolve_c2l_command", return_value=(["c2l"], "path")):
            with mock.patch.object(
                MODULE,
                "run_c2l",
                return_value=(
                    payload,
                    mock.Mock(returncode=0, stderr=""),
                ),
            ) as run_c2l:
                result = MODULE.analyze_url(
                    "https://www.chess.com/game/123456789",
                    skip_enrichment=True,
                    timeout_seconds=5,
                )

        run_c2l.assert_called_once_with(
            "https://www.chess.com/game/live/123456789",
            ["c2l"],
            5,
        )
        self.assertEqual(
            result["original_input_url"],
            "https://www.chess.com/game/123456789",
        )
        self.assertEqual(
            result["input_url"],
            "https://www.chess.com/game/live/123456789",
        )

    def test_analyze_url_with_stub_and_skipped_enrichment(self):
        payload = {
            "input_url": "https://www.chess.com/game/live/123456789",
            "success": True,
            "game_id": "abc123",
            "analysis_url": "https://lichess.org/abc123",
            "pgn": "1. e4 e5 2. Nf3 Nc6",
            "retries": 1,
            "error": None,
        }
        with mock.patch.dict(
            os.environ,
            {"C2L_COMMAND": self.make_stub_command(payload)},
            clear=False,
        ):
            result = MODULE.analyze_url(
                "https://www.chess.com/game/live/123456789",
                skip_enrichment=True,
                timeout_seconds=5,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["game_id"], "abc123")
        self.assertEqual(result["c2l_command_source"], "env")
        self.assertFalse(result["enrichment"]["ok"])
        self.assertIn("Skipped enrichment", result["enrichment"]["warnings"][0])

    def test_analyze_url_handles_enrichment_failure(self):
        payload = {
            "input_url": "https://www.chess.com/game/live/123456789",
            "success": True,
            "game_id": "abc123",
            "analysis_url": "https://lichess.org/abc123",
            "pgn": "1. d4 d5 2. c4",
            "retries": 0,
            "error": None,
        }
        with mock.patch.dict(
            os.environ,
            {"C2L_COMMAND": self.make_stub_command(payload)},
            clear=False,
        ):
            with mock.patch.object(
                MODULE,
                "enrich_lichess_context",
                side_effect=RuntimeError("boom"),
            ):
                result = MODULE.analyze_url(
                    "https://www.chess.com/game/live/123456789",
                    timeout_seconds=5,
                )

        self.assertTrue(result["success"])
        self.assertFalse(result["enrichment"]["ok"])
        self.assertIn("boom", result["enrichment"]["warnings"][0])


if __name__ == "__main__":
    unittest.main()
