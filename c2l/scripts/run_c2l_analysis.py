#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

DEFAULT_REPO_ROOT: Path | None = None
DEFAULT_TIMEOUT_SECONDS = 90
CHESSCOM_GAME_URL_RE = re.compile(
    r"^https?://(www\.)?chess\.com/game(?:/live)?/\d+/?(?:\?.*)?$"
)
INSTALL_HINT = (
    "c2l is not installed. Install chess2lichess so the `c2l` command is available on PATH, "
    "or set C2L_COMMAND to the executable command. Optionally pass --repo-root to a local "
    "chess2lichess checkout."
)


def normalize_chesscom_game_url(url: str) -> str:
    trimmed = url.strip()
    if not CHESSCOM_GAME_URL_RE.match(trimmed):
        raise ValueError("Expected one chess.com game URL.")

    parsed = urlparse.urlparse(trimmed)
    path = parsed.path.rstrip("/")
    if re.fullmatch(r"/game/\d+", path):
        path = path.replace("/game/", "/game/live/", 1)
        return urlparse.urlunparse(parsed._replace(path=path))
    return trimmed


def parse_command(command: str) -> list[str]:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("Received an empty c2l command override.")
    return argv


def resolve_c2l_command(
    explicit_command: str | None = None, repo_root: Path | None = DEFAULT_REPO_ROOT
) -> tuple[list[str], str]:
    if explicit_command:
        return parse_command(explicit_command), "explicit"

    env_command = os.environ.get("C2L_COMMAND")
    if env_command:
        return parse_command(env_command), "env"

    path_command = shutil.which("c2l")
    if path_command:
        return [path_command], "path"

    if repo_root is not None:
        for binary_name in ("release", "debug"):
            candidate = repo_root / "target" / binary_name / "c2l"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return [str(candidate)], f"repo-target-{binary_name}"

        cargo = shutil.which("cargo")
        manifest_path = repo_root / "Cargo.toml"
        if cargo and manifest_path.is_file():
            return (
                [
                    cargo,
                    "run",
                    "--quiet",
                    "--manifest-path",
                    str(manifest_path),
                    "--bin",
                    "c2l",
                    "--",
                ],
                "cargo-run",
            )

    raise FileNotFoundError(INSTALL_HINT)


def parse_c2l_json_line(stdout_text: str) -> dict[str, Any]:
    for line in reversed([line.strip() for line in stdout_text.splitlines() if line.strip()]):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("Could not find a JSON object in c2l output.")


def extract_lichess_game_id(analysis_url: str | None) -> str | None:
    if not analysis_url:
        return None

    parsed = urlparse.urlparse(analysis_url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None

    if parts[0] == "analysis":
        if len(parts) >= 3 and parts[1] == "standard":
            return None
        return parts[-1] if len(parts) > 1 else None

    if parts[0] == "study":
        return parts[-1] if len(parts) > 1 else None

    return parts[-1]


def run_c2l(
    url: str, command_argv: list[str], timeout_seconds: int
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    process = subprocess.run(
        [*command_argv, "--json", "--no-open", url],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )

    payload = parse_c2l_json_line(process.stdout)
    return payload, process


def fetch_url(
    url: str, timeout_seconds: int, accept: str | None = None
) -> tuple[str, dict[str, str], str]:
    headers = {"User-Agent": "c2l-skill/1.0"}
    if accept:
        headers["Accept"] = accept
    request = urlrequest.Request(url, headers=headers)

    with urlrequest.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        text = body.decode(charset, errors="replace")
        header_map = dict(response.headers.items())
        return text, header_map, response.geturl()


def parse_json_or_ndjson(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue

    return None


def normalize_enrichment_payload(
    source: str,
    request_url: str,
    final_url: str,
    headers: dict[str, str],
    text: str,
    game_id: str,
) -> dict[str, Any] | None:
    content_type = headers.get("Content-Type", "")
    lowered = text.lstrip().lower()

    if "text/html" in content_type or lowered.startswith("<!doctype html") or lowered.startswith(
        "<html"
    ):
        return None

    json_payload = parse_json_or_ndjson(text)
    if isinstance(json_payload, dict):
        return {
            "ok": True,
            "source": source,
            "game_id": game_id,
            "request_url": request_url,
            "final_url": final_url,
            "content_type": content_type,
            "json": json_payload,
            "pgn": json_payload.get("pgn"),
            "warnings": [],
        }

    stripped = text.strip()
    if stripped:
        return {
            "ok": True,
            "source": source,
            "game_id": game_id,
            "request_url": request_url,
            "final_url": final_url,
            "content_type": content_type,
            "json": None,
            "pgn": stripped,
            "warnings": [],
        }

    return None


def enrich_lichess_context(
    game_id: str, timeout_seconds: int, analysis_url: str | None = None
) -> dict[str, Any]:
    warnings: list[str] = []
    query = urlparse.urlencode(
        {
            "evals": "true",
            "accuracy": "true",
            "clocks": "true",
            "opening": "true",
            "literate": "true",
            "pgnInJson": "true",
        }
    )
    candidates = [
        (
            "game-export",
            f"https://lichess.org/game/export/{game_id}?{query}",
            "application/json, application/x-chess-pgn;q=0.9, text/plain;q=0.8",
        ),
        (
            "imports-export",
            f"https://lichess.org/api/games/export/imports?ids={game_id}&{query}",
            "application/x-ndjson, application/json;q=0.9, text/plain;q=0.8",
        ),
    ]

    for source, request_url, accept in candidates:
        try:
            text, headers, final_url = fetch_url(
                request_url, timeout_seconds=timeout_seconds, accept=accept
            )
        except urlerror.HTTPError as exc:
            warnings.append(f"{source}: HTTP {exc.code}")
            continue
        except urlerror.URLError as exc:
            warnings.append(f"{source}: {exc.reason}")
            continue
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"{source}: {exc}")
            continue

        payload = normalize_enrichment_payload(
            source=source,
            request_url=request_url,
            final_url=final_url,
            headers=headers,
            text=text,
            game_id=game_id,
        )
        if payload is not None:
            payload["warnings"] = warnings
            if analysis_url:
                payload["analysis_url"] = analysis_url
            return payload
        warnings.append(f"{source}: unusable response")

    return {
        "ok": False,
        "source": None,
        "game_id": game_id,
        "analysis_url": analysis_url,
        "json": None,
        "pgn": None,
        "warnings": warnings,
    }


def analyze_url(
    url: str,
    c2l_command: str | None = None,
    repo_root: Path | None = DEFAULT_REPO_ROOT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    skip_enrichment: bool = False,
) -> dict[str, Any]:
    normalized_url = normalize_chesscom_game_url(url)
    command_argv, command_source = resolve_c2l_command(c2l_command, repo_root=repo_root)
    c2l_payload, process = run_c2l(normalized_url, command_argv, timeout_seconds)

    analysis_url = c2l_payload.get("analysis_url")
    game_id = c2l_payload.get("game_id") or extract_lichess_game_id(analysis_url)
    result = {
        "input_url": c2l_payload.get("input_url") or normalized_url,
        "original_input_url": url,
        "success": bool(c2l_payload.get("success")),
        "analysis_url": analysis_url,
        "game_id": game_id,
        "pgn": c2l_payload.get("pgn"),
        "retries": int(c2l_payload.get("retries") or 0),
        "error": c2l_payload.get("error"),
        "c2l_command": command_argv,
        "c2l_command_source": command_source,
        "c2l_returncode": process.returncode,
        "c2l_stderr": process.stderr.strip() or None,
    }

    if skip_enrichment:
        result["enrichment"] = {
            "ok": False,
            "source": None,
            "game_id": game_id,
            "analysis_url": analysis_url,
            "json": None,
            "pgn": None,
            "warnings": ["Skipped enrichment by request."],
        }
        return result

    if not analysis_url or not game_id:
        result["enrichment"] = {
            "ok": False,
            "source": None,
            "game_id": game_id,
            "analysis_url": analysis_url,
            "json": None,
            "pgn": None,
            "warnings": ["No lichess game id available for enrichment."],
        }
        return result

    try:
        result["enrichment"] = enrich_lichess_context(
            game_id=game_id,
            timeout_seconds=timeout_seconds,
            analysis_url=analysis_url,
        )
    except Exception as exc:  # pragma: no cover - defensive
        result["enrichment"] = {
            "ok": False,
            "source": None,
            "game_id": game_id,
            "analysis_url": analysis_url,
            "json": None,
            "pgn": None,
            "warnings": [f"Enrichment failed: {exc}"],
        }

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run c2l, capture the lichess analysis URL, and enrich the result."
    )
    parser.add_argument("url", help="chess.com live game URL")
    parser.add_argument(
        "--c2l-command",
        help="Override the c2l command. If omitted, use C2L_COMMAND or discovery.",
    )
    parser.add_argument(
        "--repo-root",
        help="Optional local chess2lichess repository root containing the c2l Cargo.toml",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Timeout for c2l and lichess requests",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Return only c2l output without lichess export attempts",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the final JSON payload",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        payload = analyze_url(
            url=args.url,
            c2l_command=args.c2l_command,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            timeout_seconds=args.timeout_seconds,
            skip_enrichment=args.skip_enrichment,
        )
        exit_code = 0 if payload.get("success") else 1
    except Exception as exc:
        payload = {
            "input_url": args.url,
            "success": False,
            "analysis_url": None,
            "game_id": None,
            "pgn": None,
            "retries": 0,
            "error": str(exc),
            "enrichment": {
                "ok": False,
                "source": None,
                "game_id": None,
                "analysis_url": None,
                "json": None,
                "pgn": None,
                "warnings": [str(exc)],
            },
        }
        exit_code = 1

    indent = 2 if args.pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
