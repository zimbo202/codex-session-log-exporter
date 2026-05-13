# Codex Session Log Exporter Usage Guide

`codex-session-log-exporter` is a Codex skill for exporting the current Codex session log from `~/.codex/sessions` into the active project directory.

It copies the selected JSONL log file and, by default, also creates a readable Markdown transcript.

## Environment Requirements

- Codex CLI or Codex IDE session logs must exist under `$CODEX_HOME/sessions` or `~/.codex/sessions`.
- Python 3.10 or newer is recommended.
- No third-party Python packages are required.
- `git` is optional, but recommended. When available, the script uses the current git root and branch as extra signals to identify the correct session log.
- Run the script from the project directory where you want the exported log to be copied.

If `CODEX_HOME` is not set, the script uses:

```text
~/.codex
```

## Installation

### Install As A Repo Skill

Copy this skill directory into the target repository:

```text
.agents/skills/codex-session-log-exporter/
```

Then run it from that repository:

```bash
python3 .agents/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

### Install Globally

Copy this skill directory into the global Codex skills directory:

```text
~/.codex/skills/codex-session-log-exporter/
```

Then run it from any project directory:

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

Restart Codex after installing a new global skill so Codex can discover it.

## Basic Usage

From the project root:

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

Default output:

```text
.codex-session-logs/
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.jsonl
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.md
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.meta.json
```

The `.jsonl` file is the raw Codex session log. The `.md` file is a readable transcript. The `.meta.json` file records the source path, destination path, confidence score, matching reasons, and top candidate logs.

## Usage Examples

### Export JSONL And Markdown

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

This is the default behavior.

### Export Only The Raw JSONL Log

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --no-markdown
```

Use this when you only need the original Codex log file.

### Choose A Candidate Manually

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --choose
```

Use this when multiple recent Codex sessions are present and you want to select the correct one yourself.

### Allow Low-Confidence Best Effort

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --allow-low-confidence
```

Use this only when you understand the ambiguity and still want the script to copy the best-scored candidate.

### Use A Custom Codex Home

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --codex-home /path/to/codex-home
```

Use this if your Codex logs are not under `~/.codex`.

### Use A Custom Output Subdirectory

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --dest-subdir exported-codex-logs
```

This writes files under:

```text
exported-codex-logs/
```

### Keep Full Tool Output In Markdown

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --markdown-max-tool-lines 0
```

By default, very long tool outputs are truncated in the Markdown transcript. The raw JSONL is always copied unchanged.

## How The Script Finds The Current Session

The script does not simply copy the newest `rollout-*.jsonl` file. It scores candidates using several signals:

- Explicit session id environment variables, when available.
- Whether the current working directory appears in the log.
- Whether the current git root appears in the log.
- Whether the current git branch appears in the log.
- Whether the project directory name appears in the log.
- File modification recency.
- Whether the log file appears to still be active.
- Session id-like values found in the filename or log content.

If the best candidate score is below the confidence threshold, the script stops unless you use `--choose` or `--allow-low-confidence`.

## Recommended Gitignore

Add this to the project `.gitignore`:

```gitignore
.codex-session-logs/
```

If you use a custom output subdirectory, ignore that directory instead.

## Security Notes

Codex session logs can contain sensitive information, including:

- prompts and instructions;
- file contents;
- command output;
- paths and environment details;
- secrets, tokens, credentials, or proprietary code.

Review exported `.jsonl`, `.md`, and `.meta.json` files before sharing or committing them. Do not upload logs externally unless you have explicitly confirmed they are safe to share.

## Troubleshooting

### No Logs Found

Check where Codex stores sessions:

```bash
echo "${CODEX_HOME:-$HOME/.codex}"
find "${CODEX_HOME:-$HOME/.codex}/sessions" -name '*.jsonl' | tail
```

If logs are elsewhere, pass `--codex-home`.

### Wrong Session Selected

Run with manual selection:

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --choose
```

Review the score reasons printed for each candidate.

### Markdown Is Too Large

Reduce the number of tool-result lines:

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --markdown-max-tool-lines 80
```

Or skip Markdown:

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --no-markdown
```

### Markdown Is Missing Some Raw Detail

The Markdown transcript is designed for reading. It may truncate long tool output according to `--markdown-max-tool-lines`. Use the copied `.jsonl` file as the authoritative raw log.
