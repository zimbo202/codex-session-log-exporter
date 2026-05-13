# codex-session-log-exporter

A Codex skill for copying the current Codex session JSONL log into the current project directory and writing a readable Markdown transcript next to it.

## Install in a repo

Place this directory at:

```text
.agents/skills/codex-session-log-exporter/
```

Codex can discover repo skills from `.agents/skills`.

## Install globally

Place this directory under your global skills directory, for example:

```text
~/.agents/skills/codex-session-log-exporter/
```

## Usage

From a project directory:

```bash
python3 .agents/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

Output:

```text
.codex-session-logs/
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.jsonl
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.md
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.meta.json
```

The Markdown file keeps user and assistant messages readable, renders tool calls as sections, and wraps tool results in collapsible `<details>` blocks. It follows the same normalization ideas used by public Python converters such as `cc2md` and `codex-transcripts`, while staying dependency-free.

Skip Markdown generation:

```bash
python3 .agents/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --no-markdown
```

If detection is ambiguous:

```bash
python3 .agents/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --choose
```

Best-effort mode:

```bash
python3 .agents/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --allow-low-confidence
```

## Git ignore

Recommended:

```gitignore
.codex-session-logs/
```

## Why not just copy the newest file?

Because several Codex sessions can be active or recently modified, and IDE/Desktop/import flows can produce local session files that are not the current project session. This skill ranks candidates by project path, git root, branch, recency, active-write status, and explicit session id environment variables when available.
