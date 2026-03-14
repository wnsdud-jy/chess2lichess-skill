---
name: c2l
description: Run the local chess2lichess CLI for a chess.com live game URL, capture the resulting lichess analysis URL and PGN, optionally enrich it with lichess export data, and explain the game in Korean. Use when the user mentions c2l, chess2lichess, or provides a chess.com/game/live URL and wants conversion plus an AI game summary.
---

# c2l

## Quick Start

When the user provides one `chess.com/game/live/...` URL, run:

```bash
python ./scripts/run_c2l_analysis.py "<url>"
```

Read the JSON output, then explain the game in Korean.

## Workflow

1. Require exactly one `chess.com` live game URL.
2. Run `./scripts/run_c2l_analysis.py` with the URL.
3. Read these fields first:
   - `analysis_url`
   - `pgn`
   - `game_id`
   - `enrichment`
   - `error`
4. If `success` is `false`, surface the error clearly and stop.
5. If `success` is `true`, explain the game in Korean using:
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
- The helper script tries `c2l` on `PATH` first, then local build fallbacks in `/home/wnsdud/dev/chess2lichess`.
- Set `C2L_COMMAND` if a session needs a custom executable command.
- Treat lichess enrichment as best-effort. Do not fail the whole task if only enrichment fails.
