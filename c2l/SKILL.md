---
name: c2l
description: Run the local chess2lichess CLI for a chess.com game URL, capture the resulting lichess analysis URL and PGN, optionally enrich it with lichess export data, and explain the game in Korean. Use when the user mentions c2l, chess2lichess, or provides a `chess.com/game/{id}` or `chess.com/game/live/{id}` URL and wants conversion plus an AI game summary.
---

# c2l

## Quick Start

When the user provides one `chess.com/game/...` or `chess.com/game/live/...` URL, run:

```bash
python ./scripts/run_c2l_analysis.py "<url>"
```

Read the JSON output, then explain the game in Korean.

If the JSON `error` says `c2l is not installed`, tell the user to install `chess2lichess` so the
`c2l` command is available on `PATH`, or set `C2L_COMMAND` to the executable command.

## Workflow

1. Require exactly one `chess.com` game URL.
2. Accept both `https://www.chess.com/game/<id>` and `https://www.chess.com/game/live/<id>`.
3. Normalize the short form to the `live` form before invoking `c2l`.
4. Run `./scripts/run_c2l_analysis.py` with the URL.
5. Read these fields first:
   - `analysis_url`
   - `pgn`
   - `game_id`
   - `enrichment`
   - `error`
6. If `success` is `false`, surface the error clearly and stop.
7. If `success` is `true`, explain the game in Korean using:
   - the opening or early-game plan
   - two to four turning points
   - at least one good move and one costly move if identifiable
   - a short reason for the final result
   - the final `analysis_url`

## Explanation Rules

- Prefer the `enrichment` block when it contains usable lichess export data.
- Fall back to PGN-only reasoning when enrichment is missing or partial.
- Say explicitly when the explanation is based on PGN flow rather than full lichess export data.
- Keep the explanation concise and readable for a human, not engine jargon first.
- End with the final `lichess` analysis link.

## Execution Notes

- The helper script already forces `c2l --json --no-open`; do not open a browser.
- The helper script tries `c2l` on `PATH` first.
- Set `C2L_COMMAND` if a session needs a custom executable command.
- If `c2l` is unavailable, explicitly tell the user to install `chess2lichess` first.
- `--repo-root` is only an optional local fallback for sessions that already have a checkout.
- Treat lichess enrichment as best-effort. Do not fail the whole task if only enrichment fails.
