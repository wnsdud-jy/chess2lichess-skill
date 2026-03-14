# chess2lichess-skill

`c2l` is a Codex skill that turns a `chess.com` game URL into a `lichess` analysis link and a
Korean game summary.

## Requirements

- `c2l` must be installed and available on `PATH`, or
- `C2L_COMMAND` must point at a working `c2l` executable command

If neither is available, the helper script returns an error telling the user to install
`chess2lichess` first.

## Usage

From the skill directory:

```bash
python ./c2l/scripts/run_c2l_analysis.py "https://www.chess.com/game/live/123456789"
```

Optional local fallback:

```bash
python ./c2l/scripts/run_c2l_analysis.py \
  --repo-root /path/to/chess2lichess \
  "https://www.chess.com/game/live/123456789"
```

## Install This Skill

Publish or share this repository path:

```text
https://github.com/wnsdud-jy/chess2lichess-skill/tree/main/c2l
```

Install with Codex skill installer using:

- repo: `wnsdud-jy/chess2lichess-skill`
- path: `c2l`

After installation, restart Codex so the new skill is loaded.
