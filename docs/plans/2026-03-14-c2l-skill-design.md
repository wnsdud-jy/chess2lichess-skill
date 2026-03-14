# c2l Skill Design

**Date:** 2026-03-14

**Goal:** Create a Codex skill that accepts a `chess.com` live game URL, runs the local `c2l` CLI, retrieves the resulting `lichess` analysis URL plus structured game data, and produces a Korean explanation of the game.

## Chosen Approach

Use a script-backed skill rather than a prompt-only or browser-scraping design.

- Prompt-only is lightweight but fragile because command discovery, JSON parsing, and fallback handling would be repeated by the model.
- Browser scraping can expose richer UI state, but it is slower and more brittle than API-first processing.
- A helper script gives deterministic execution while keeping the language-model work focused on interpretation and explanation.

## Scope

The first version should support:

- One `chess.com/game/live/...` URL per invocation
- Local execution of the `c2l` CLI without opening a browser
- Extraction of `analysis_url`, `pgn`, `game_id`, and retry/error information from `c2l --json`
- Best-effort enrichment from `lichess` using the imported game ID and official export endpoints when available
- Korean explanation covering opening, turning points, notable mistakes, and a final direct link to the `lichess` analysis page

The first version should not support:

- Automatic browser control
- Multiple URLs in one user request
- Guaranteed engine-grade annotations when `lichess` export data is unavailable

## File Layout

The skill repository root remains `/home/wnsdud/dev/chess2lichess-skill`.
The actual skill folder should be `/home/wnsdud/dev/chess2lichess-skill/c2l`.

Expected contents:

- `c2l/SKILL.md`
- `c2l/agents/openai.yaml`
- `c2l/scripts/run_c2l_analysis.py`
- `tests/test_run_c2l_analysis.py`

Documentation lives under:

- `docs/plans/2026-03-14-c2l-skill-design.md`
- `docs/plans/2026-03-14-c2l-skill.md`

## Runtime Flow

1. The user invokes the skill with a `chess.com` live game URL.
2. The skill runs `scripts/run_c2l_analysis.py`.
3. The helper script resolves a `c2l` executable in this order:
   - `c2l` on `PATH`
   - local repository binary or wrapper under `/home/wnsdud/dev/chess2lichess`
   - direct `cargo run --manifest-path ... --bin c2l --` fallback when needed
4. The script executes `c2l --json --no-open <url>`.
5. The script parses the JSON line output and normalizes:
   - input URL
   - `analysis_url`
   - imported `lichess` game ID
   - `pgn`
   - retry count
   - raw stderr/stdout for debugging when failures occur
6. If a `lichess` game ID is available, the script attempts to fetch official export data for deeper context.
7. The skill instructs Codex to explain the game in Korean using the structured output, while falling back to PGN-only reasoning if enrichment is unavailable.

## Explanation Contract

The model output should be short, useful, and stable. It should include:

- the likely opening or early-game plan
- two to four turning points
- at least one strong move and one costly move if identifiable
- a short summary of why the final result happened
- the final `lichess` analysis URL

When imported-game export or evaluation data is unavailable, the model should explicitly say the summary is based on PGN flow and `lichess` import context rather than full engine annotations.

## Error Handling

- Reject empty or non-`chess.com/game/live` inputs
- Surface a clear error if `c2l` cannot be found
- Preserve `c2l` failure messages when import or PGN extraction fails
- Treat `lichess` enrichment as optional; do not fail the whole workflow if only enrichment fails
- Avoid browser-opening side effects by always passing `--no-open`

## Verification

- Validate the skill scaffold with `quick_validate.py`
- Run unit tests for command resolution and JSON parsing
- Run a representative execution with a stub `c2l` binary to verify end-to-end script behavior
- If a public game URL is available during development, run one live smoke test
