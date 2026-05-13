# Codex session log detection strategy

## Problem

The user-facing request is simple: copy the current Codex session log into the current project.

The hard part is that a script running inside a Codex-driven shell may not receive a stable, official `CURRENT_CODEX_LOG_FILE` environment variable. Therefore, the skill should not rely on one signal.

## Expected log location

Common Codex CLI session logs are JSONL files under:

```text
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
```

When `CODEX_HOME` is set, use:

```text
$CODEX_HOME/sessions/YYYY/MM/DD/
```

## Ranking signals

The script ranks candidates with these signals:

| Signal | Weight | Rationale |
|---|---:|---|
| Explicit session id env var | Very high | If a future Codex version exposes a stable id, this should dominate. |
| Current git root appears in JSONL content | Very high | Best project-level signal. |
| Current working directory appears in JSONL content | High | Strong if the agent ran commands from this project. |
| Project directory name appears | Low | Useful fallback but collision-prone. |
| Current git branch appears | Low/medium | Helpful in active development sessions. |
| Recent file modification | Medium | Current session is usually among the most recent logs. |
| File changed during active check | Medium/high | Useful if the session is still being written. |

## Failure modes

1. Multiple Codex agents are active in the same project.
2. Several sessions were started in the same repo within a short time.
3. The log content does not include cwd/git metadata.
4. Codex Desktop or IDE imported sessions from another environment.
5. Session logs were moved, compacted, truncated, or not flushed yet.

In these cases, the script should show top candidates and require manual selection unless `--allow-low-confidence` is passed.

## Recommended repository policy

Add this to `.gitignore` unless logs are intentionally archived:

```gitignore
.codex-session-logs/
```

Session logs may contain sensitive data.
