#!/usr/bin/env python3
"""
Copy the most likely current Codex session JSONL log into the current project.

Why this script exists:
- Codex session logs are stored as JSONL files under ~/.codex/sessions/YYYY/MM/DD.
- In a busy environment, "latest modified file" is not always enough.
- This script ranks candidates using project-path, git-root, recency, active-write,
  and optional session-id signals.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable

SESSION_ID_ENV_KEYS = [
    "CODEX_SESSION_ID",
    "CODEX_THREAD_ID",
    "CODEX_CONVERSATION_ID",
    "OPENAI_CODEX_SESSION_ID",
    "OPENAI_CODEX_THREAD_ID",
]

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
DEFAULT_MARKDOWN_MAX_TOOL_LINES = 200


def run(cmd: list[str], cwd: Path) -> str | None:
    try:
        return subprocess.check_output(cmd, cwd=str(cwd), stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def git_root(cwd: Path) -> Path | None:
    out = run(["git", "rev-parse", "--show-toplevel"], cwd)
    return Path(out).resolve() if out else None


def git_branch(cwd: Path) -> str | None:
    return run(["git", "branch", "--show-current"], cwd)


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()


def iter_log_candidates(home: Path) -> Iterable[Path]:
    sessions = home / "sessions"
    if not sessions.exists():
        return []
    # Prefer rollout files but include all JSONL as fallback.
    files = list(sessions.glob("**/rollout-*.jsonl"))
    if not files:
        files = list(sessions.glob("**/*.jsonl"))
    return files


def read_sample(path: Path, max_head: int = 80, max_tail: int = 120) -> tuple[list[str], int]:
    """
    Return head+tail lines without loading very large logs fully.
    Also return total sampled byte-ish count for diagnostics.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return [], 0

    if len(lines) <= max_head + max_tail:
        sample = lines
    else:
        sample = lines[:max_head] + lines[-max_tail:]
    return sample, sum(len(x) for x in sample)


def flatten_json_values(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from flatten_json_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from flatten_json_values(v)
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        yield "" if obj is None else str(obj)


def content_text_from_sample(lines: list[str]) -> str:
    values: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
            values.extend(flatten_json_values(obj))
        except Exception:
            values.append(s)
    return "\n".join(values)


def is_active_file(path: Path, wait_seconds: float = 0.8) -> bool:
    try:
        before = path.stat()
        time.sleep(wait_seconds)
        after = path.stat()
        return after.st_size > before.st_size or after.st_mtime > before.st_mtime
    except Exception:
        return False


def extract_session_id(path: Path, text: str) -> str:
    m = UUID_RE.search(path.name)
    if m:
        return m.group(0)
    m = UUID_RE.search(text)
    if m:
        return m.group(0)
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    return digest


def score_candidate(
    path: Path,
    cwd: Path,
    root: Path | None,
    branch: str | None,
    explicit_session_ids: list[str],
    now: float,
    check_active: bool,
) -> dict[str, Any]:
    stat = path.stat()
    age_seconds = max(0.0, now - stat.st_mtime)
    sample, sampled_chars = read_sample(path)
    text = content_text_from_sample(sample)

    score = 0
    reasons: list[str] = []

    # Explicit session-id match is strongest.
    for sid in explicit_session_ids:
        if sid and (sid in path.name or sid in text):
            score += 100
            reasons.append(f"explicit session id matched: {sid}")

    cwd_s = str(cwd)
    root_s = str(root) if root else None

    if cwd_s and cwd_s in text:
        score += 40
        reasons.append("current working directory appears in log content")

    if root_s and root_s in text:
        score += 45
        reasons.append("git root appears in log content")

    # Path basename/project name is weaker but useful when full paths are absent.
    project_names = {cwd.name}
    if root:
        project_names.add(root.name)
    for name in sorted(project_names):
        if name and name in text:
            score += 8
            reasons.append(f"project name appears in log content: {name}")
            break

    if branch and branch in text:
        score += 10
        reasons.append(f"git branch appears in log content: {branch}")

    # Recency scoring. Current session should normally be recent.
    if age_seconds <= 5 * 60:
        score += 30
        reasons.append("modified within 5 minutes")
    elif age_seconds <= 30 * 60:
        score += 20
        reasons.append("modified within 30 minutes")
    elif age_seconds <= 6 * 3600:
        score += 10
        reasons.append("modified within 6 hours")
    elif age_seconds <= 24 * 3600:
        score += 5
        reasons.append("modified within 24 hours")

    active = False
    if check_active:
        active = is_active_file(path)
        if active:
            score += 25
            reasons.append("file changed while checking; likely active")

    session_id = extract_session_id(path, text)

    return {
        "path": str(path),
        "score": score,
        "reasons": reasons,
        "mtime": stat.st_mtime,
        "age_seconds": age_seconds,
        "size_bytes": stat.st_size,
        "sampled_chars": sampled_chars,
        "session_id": session_id,
        "active": active,
    }


def safe_timestamp(ts: float | None = None) -> str:
    d = dt.datetime.fromtimestamp(ts or time.time())
    return d.strftime("%Y%m%d-%H%M%S")


def write_meta(meta_path: Path, payload: dict[str, Any]) -> None:
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                records.append(obj)
    return records


def parse_json_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if not ((text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))):
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def md_fenced(content: Any, info: str = "") -> str:
    text = "" if content is None else str(content)
    max_run = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    fence = "`" * max(3, max_run + 1)
    return f"{fence}{info}\n{text}\n{fence}"


def md_inline_code(value: Any) -> str:
    text = "" if value is None else str(value)
    if "`" not in text:
        return f"`{text}`"
    escaped = text.replace("`", "\\u0060")
    return f"`{escaped}`"


def truncate_lines(text: str, max_lines: int) -> str:
    if max_lines <= 0:
        return text
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    head = max(1, max_lines // 2)
    tail = max(1, max_lines - head)
    omitted = len(lines) - head - tail
    return "\n".join(lines[:head] + [f"... ({omitted} lines omitted) ..."] + lines[-tail:])


def normalize_tool_output(output: Any) -> str:
    if output is None:
        return ""
    if not isinstance(output, str):
        return json_dumps(output)

    text = output.strip("\n")
    if text.startswith("Chunk ID:") and "\nOutput:\n" in text:
        header, body = text.split("\nOutput:\n", 1)
        body = body.strip("\n")
        if body:
            return f"{header}\n\nOutput:\n{body}"
        return header

    parsed = parse_json_maybe(text)
    if parsed is not text:
        return json_dumps(parsed)
    return text


def markdown_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in {"input_text", "output_text", "text"}:
            text = item.get("text", "")
            if text:
                parts.append(str(text).strip())
            continue
        if item_type in {"input_image", "image"}:
            url = item.get("image_url") or item.get("url")
            if isinstance(url, str) and url and not url.startswith("data:") and len(url) <= 500:
                parts.append(f"![image]({url})")
            else:
                parts.append("*[embedded image omitted]*")
    return "\n\n".join(part for part in parts if part)


def first_session_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in records:
        if record.get("type") != "session_meta":
            continue
        payload = record.get("payload")
        if isinstance(payload, dict):
            return payload
    return {}


def first_turn_context(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in records:
        if record.get("type") != "turn_context":
            continue
        payload = record.get("payload")
        if isinstance(payload, dict):
            return payload
    return {}


def last_token_count_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for record in records:
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "token_count":
            found = payload
    return found


def first_user_message(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload", {})
        if not isinstance(payload, dict) or payload.get("type") != "user_message":
            continue
        text = str(payload.get("message", "")).strip()
        if text:
            return " ".join(text.split())[:100]

    for record in records:
        if record.get("type") == "response_item":
            payload = record.get("payload", {})
            if isinstance(payload, dict) and payload.get("type") == "message" and payload.get("role") == "user":
                text = markdown_text_from_content(payload.get("content"))
                if text.startswith("<environment_context>") or text.startswith("<skill>"):
                    continue
                if text:
                    return " ".join(text.split())[:100]
    return None


def response_message_records_available(records: list[dict[str, Any]]) -> bool:
    for record in records:
        if record.get("type") != "response_item":
            continue
        payload = record.get("payload", {})
        if isinstance(payload, dict) and payload.get("type") == "message" and payload.get("role") in {"user", "assistant"}:
            return True
    return False


def user_event_messages_available(records: list[dict[str, Any]]) -> bool:
    for record in records:
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload", {})
        if isinstance(payload, dict) and payload.get("type") == "user_message":
            return True
    return False


def append_message_section(lines: list[str], role: str, timestamp: str | None, phase: str | None, body: str) -> None:
    label = "User" if role == "user" else "Assistant"
    if phase:
        label = f"{label} ({phase})"
    lines.append(f"## {label}")
    if timestamp:
        lines.append("")
        lines.append(f"*{timestamp}*")
    lines.append("")
    lines.append(body)
    lines.append("")


def render_reasoning_block(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for summary in payload.get("summary", []) or []:
        if isinstance(summary, dict):
            text = summary.get("text")
            if text:
                parts.append(str(text))
    for item in payload.get("content", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"reasoning_text", "text", "summary_text"} and item.get("text"):
            parts.append(str(item["text"]))
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def tool_args_from_payload(payload: dict[str, Any]) -> Any:
    if payload.get("type") == "function_call":
        return parse_json_maybe(payload.get("arguments", ""))
    if payload.get("type") == "custom_tool_call":
        return parse_json_maybe(payload.get("input", ""))
    return {}


def extract_patch_text(payload: dict[str, Any]) -> str:
    changes = payload.get("changes")
    if not isinstance(changes, dict) or not changes:
        return ""

    parts = ["*** Begin Patch"]
    for path, change in changes.items():
        if not isinstance(change, dict):
            continue
        change_type = change.get("type")
        move_path = change.get("move_path")
        if change_type == "add":
            parts.append(f"*** Add File: {path}")
            content = str(change.get("content", ""))
            parts.extend(f"+{line}" for line in content.splitlines())
            continue
        if change_type == "update":
            parts.append(f"*** Update File: {path}")
            if move_path:
                parts.append(f"*** Move to: {move_path}")
            diff = str(change.get("unified_diff", "")).strip("\n")
            if diff:
                parts.extend(diff.splitlines())
            continue
        if change_type == "delete":
            parts.append(f"*** Delete File: {path}")
    parts.append("*** End Patch")
    return "\n".join(parts)


def render_tool_call(name: str, args: Any, call_id: str | None, timestamp: str | None) -> str:
    input_obj = args if isinstance(args, dict) else {"value": args}
    lines = [f"### Tool: {name}"]
    if timestamp:
        lines.extend(["", f"*{timestamp}*"])
    if call_id:
        lines.extend(["", f"**Call ID:** {md_inline_code(call_id)}"])

    lower_name = name.lower()
    if name == "exec_command":
        if input_obj.get("workdir"):
            lines.append(f"**Workdir:** {md_inline_code(input_obj.get('workdir'))}")
        if input_obj.get("justification"):
            lines.append(f"**Justification:** {input_obj.get('justification')}")
        lines.extend(["", md_fenced(input_obj.get("cmd", ""), "bash")])
        extra = {
            k: v
            for k, v in input_obj.items()
            if k not in {"cmd", "workdir", "justification", "yield_time_ms", "max_output_tokens"}
        }
        if extra:
            lines.extend(["", md_fenced(json_dumps(extra), "json")])
        return "\n".join(lines)

    if name == "write_stdin":
        if input_obj.get("session_id"):
            lines.append(f"**Session:** {md_inline_code(input_obj.get('session_id'))}")
        if input_obj.get("chars"):
            lines.extend(["", md_fenced(input_obj.get("chars"), "text")])
        return "\n".join(lines)

    if lower_name in {"apply_patch", "applypatch"}:
        patch = ""
        for key in ("patch", "input", "content", "diff", "raw", "value"):
            value = input_obj.get(key)
            if isinstance(value, str) and value.strip():
                patch = value
                break
        lines.append("Applying patch")
        if patch:
            lines.extend(["", md_fenced(patch, "diff")])
        return "\n".join(lines)

    if name in {"open", "find", "click", "screenshot", "search_query", "image_query"} or lower_name.startswith("web"):
        lines.extend(["", md_fenced(json_dumps(input_obj), "json")])
        return "\n".join(lines)

    if input_obj:
        lines.extend(["", md_fenced(json_dumps(input_obj), "json")])
    return "\n".join(lines)


def render_tool_result(name: str, output: Any, call_id: str | None, timestamp: str | None, max_tool_lines: int) -> str:
    body = truncate_lines(normalize_tool_output(output), max_tool_lines)
    summary = f"Result: {name}"
    header_lines = [f"**Result: {name}**"]
    if timestamp:
        header_lines.append(f"*{timestamp}*")
    if call_id:
        header_lines.append(f"**Call ID:** {md_inline_code(call_id)}")
    header_lines.extend(["", md_fenced(body, "text")])
    body_md = "\n".join(header_lines)
    return f"<details><summary>{summary}</summary>\n\n{body_md}\n\n</details>"


def render_markdown_transcript(jsonl_path: Path, max_tool_lines: int = DEFAULT_MARKDOWN_MAX_TOOL_LINES) -> str:
    records = read_jsonl_records(jsonl_path)
    session = first_session_payload(records)
    turn_context = first_turn_context(records)
    token_count = last_token_count_payload(records)
    first_title = first_user_message(records)
    title = first_title or session.get("id") or jsonl_path.stem

    lines = [
        f"# Codex Session: {title}",
        "",
        f"**Session ID:** {md_inline_code(session.get('id') or jsonl_path.stem)}  ",
        f"**Source JSONL:** {md_inline_code(jsonl_path)}  ",
    ]
    if session.get("cwd"):
        lines.append(f"**Working Directory:** {md_inline_code(session.get('cwd'))}  ")
    if session.get("timestamp"):
        lines.append(f"**Started:** {session.get('timestamp')}  ")
    if session.get("originator"):
        lines.append(f"**Originator:** {md_inline_code(session.get('originator'))}  ")
    if session.get("cli_version"):
        lines.append(f"**Codex CLI:** {md_inline_code(session.get('cli_version'))}  ")
    if turn_context.get("model"):
        lines.append(f"**Model:** {md_inline_code(turn_context.get('model'))}  ")
    if turn_context.get("effort"):
        lines.append(f"**Reasoning Effort:** {md_inline_code(turn_context.get('effort'))}  ")

    info = token_count.get("info", {}) if isinstance(token_count, dict) else {}
    total_usage = info.get("total_token_usage", {}) if isinstance(info, dict) else {}
    if isinstance(total_usage, dict) and total_usage.get("total_tokens") is not None:
        lines.append(f"**Total Tokens:** {md_inline_code(total_usage.get('total_tokens'))}  ")

    lines.extend(["", "---", ""])

    has_response_messages = response_message_records_available(records)
    has_user_event_messages = user_event_messages_available(records)
    call_names: dict[str, str] = {}
    rendered_anything = False

    for record in records:
        record_type = record.get("type")
        payload = record.get("payload", {})
        timestamp = record.get("timestamp")
        if not isinstance(payload, dict):
            payload = {}

        if record_type == "response_item":
            payload_type = payload.get("type")

            if payload_type == "message":
                role = payload.get("role")
                if role not in {"user", "assistant"}:
                    continue
                if role == "user" and has_user_event_messages:
                    continue
                text = markdown_text_from_content(payload.get("content"))
                if text:
                    append_message_section(lines, role, timestamp, payload.get("phase"), text)
                    rendered_anything = True
                continue

            if payload_type in {"function_call", "custom_tool_call"}:
                name = str(payload.get("name") or "tool")
                call_id = payload.get("call_id")
                if call_id:
                    call_names[str(call_id)] = name
                lines.append(render_tool_call(name, tool_args_from_payload(payload), str(call_id) if call_id else None, timestamp))
                lines.append("")
                rendered_anything = True
                continue

            if payload_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = payload.get("call_id")
                name = call_names.get(str(call_id), "tool")
                lines.append(render_tool_result(name, payload.get("output"), str(call_id) if call_id else None, timestamp, max_tool_lines))
                lines.append("")
                rendered_anything = True
                continue

            if payload_type == "local_shell_call":
                call_id = payload.get("call_id")
                action = payload.get("action", {})
                args = {
                    "cmd": " ".join(action.get("command", []) or []),
                    "workdir": action.get("working_directory"),
                    "timeout_ms": action.get("timeout_ms"),
                    "status": payload.get("status"),
                }
                if call_id:
                    call_names[str(call_id)] = "local_shell_call"
                lines.append(render_tool_call("local_shell_call", args, str(call_id) if call_id else None, timestamp))
                lines.append("")
                rendered_anything = True
                continue

            if payload_type in {"web_search_call", "web_fetch_call"}:
                call_id = payload.get("call_id")
                name = str(payload_type)
                if call_id:
                    call_names[str(call_id)] = name
                lines.append(render_tool_call(name, payload.get("action", payload), str(call_id) if call_id else None, timestamp))
                lines.append("")
                rendered_anything = True
                continue

            if payload_type == "reasoning":
                reasoning = render_reasoning_block(payload)
                if reasoning:
                    lines.append("<details><summary>Reasoning summary</summary>\n")
                    lines.append(reasoning)
                    lines.append("\n</details>\n")
                    rendered_anything = True
                continue

            if payload_type in {"compaction", "compacted"}:
                lines.append("## Context Compaction\n")
                lines.append(str(payload.get("message") or "Context compacted."))
                lines.append("")
                rendered_anything = True
                continue

        if record_type == "event_msg" and payload.get("type") == "patch_apply_end":
            call_id = payload.get("call_id")
            name = "apply_patch"
            if call_id:
                call_names[str(call_id)] = name
            patch = extract_patch_text(payload)
            if patch:
                lines.append(render_tool_call(name, {"patch": patch}, str(call_id) if call_id else None, timestamp))
                lines.append("")
            result_parts = [str(payload.get(key, "")).strip() for key in ("stdout", "stderr") if payload.get(key)]
            result = "\n\n".join(part for part in result_parts if part)
            if result:
                lines.append(render_tool_result(name, result, str(call_id) if call_id else None, timestamp, max_tool_lines))
                lines.append("")
            rendered_anything = True
            continue

        if (not has_response_messages or has_user_event_messages) and record_type == "event_msg":
            event_type = payload.get("type")
            if event_type == "user_message":
                text = str(payload.get("message", "")).strip()
                if text:
                    append_message_section(lines, "user", timestamp, None, text)
                    rendered_anything = True
                continue
            if has_response_messages:
                continue
            if event_type == "agent_message":
                text = str(payload.get("message", "")).strip()
                if text:
                    append_message_section(lines, "assistant", timestamp, payload.get("phase"), text)
                    rendered_anything = True
                continue

    if not rendered_anything:
        lines.append("_No user or assistant transcript items were found in this JSONL file._")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Security note: review this transcript before committing or sharing it. "
        "Codex logs can contain prompts, file contents, command output, credentials, and other sensitive data."
    )
    lines.append("")
    return "\n".join(lines)


def write_markdown_transcript(jsonl_path: Path, markdown_path: Path, max_tool_lines: int) -> None:
    markdown_path.write_text(
        render_markdown_transcript(jsonl_path, max_tool_lines=max_tool_lines),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy current Codex session log into project directory.")
    parser.add_argument("--output-dir", default=".", help="Project/output directory. Default: current directory.")
    parser.add_argument("--codex-home", default=None, help="Codex home directory. Default: $CODEX_HOME or ~/.codex.")
    parser.add_argument("--dest-subdir", default=".codex-session-logs", help="Destination subdirectory under output-dir.")
    parser.add_argument("--min-confidence", type=int, default=55, help="Minimum score required to copy without --allow-low-confidence.")
    parser.add_argument("--allow-low-confidence", action="store_true", help="Copy best candidate even when confidence is low.")
    parser.add_argument("--choose", action="store_true", help="Interactively choose from top candidates.")
    parser.add_argument("--top", type=int, default=8, help="Number of top candidates to show.")
    parser.add_argument("--no-active-check", action="store_true", help="Skip active-write check.")
    parser.add_argument("--no-markdown", action="store_true", help="Do not write a readable Markdown transcript.")
    parser.add_argument(
        "--markdown-max-tool-lines",
        type=int,
        default=DEFAULT_MARKDOWN_MAX_TOOL_LINES,
        help="Maximum lines to keep from each tool result in Markdown. Use 0 for no truncation.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    cwd = Path.cwd().resolve()
    root = git_root(cwd)
    branch = git_branch(cwd)

    home = Path(args.codex_home).expanduser().resolve() if args.codex_home else codex_home()
    candidates = list(iter_log_candidates(home))
    if not candidates:
        print(f"No Codex JSONL logs found under {home / 'sessions'}", file=sys.stderr)
        return 2

    explicit_session_ids = list(dict.fromkeys(os.environ[k] for k in SESSION_ID_ENV_KEYS if os.environ.get(k)))
    now = time.time()
    scored = [
        score_candidate(
            p,
            cwd=cwd,
            root=root,
            branch=branch,
            explicit_session_ids=explicit_session_ids,
            now=now,
            check_active=not args.no_active_check,
        )
        for p in candidates
    ]
    scored.sort(key=lambda x: (x["score"], x["mtime"]), reverse=True)

    print("Top Codex session log candidates:")
    for i, item in enumerate(scored[: args.top], start=1):
        age_min = item["age_seconds"] / 60
        print(f"{i:>2}. score={item['score']:<3} age={age_min:>7.1f}m size={item['size_bytes']:<9} {item['path']}")
        for reason in item["reasons"][:5]:
            print(f"    - {reason}")

    chosen = scored[0]
    if args.choose:
        raw = input(f"Choose candidate [1-{min(args.top, len(scored))}] or Enter for 1: ").strip()
        if raw:
            idx = int(raw)
            if idx < 1 or idx > min(args.top, len(scored)):
                print("Invalid choice.", file=sys.stderr)
                return 2
            chosen = scored[idx - 1]

    if chosen["score"] < args.min_confidence and not args.allow_low_confidence and not args.choose:
        print(
            f"\nBest candidate score {chosen['score']} is below min confidence {args.min_confidence}.",
            file=sys.stderr,
        )
        print("Rerun with --choose to select manually, or --allow-low-confidence for best effort.", file=sys.stderr)
        return 3

    dest_dir = output_dir / args.dest_subdir
    dest_dir.mkdir(parents=True, exist_ok=True)

    src = Path(chosen["path"])
    stamp = safe_timestamp(chosen["mtime"])
    session_id = chosen["session_id"]
    dest = dest_dir / f"codex-session-{stamp}-{session_id}.jsonl"
    meta = dest.with_suffix(".meta.json")
    markdown = dest.with_suffix(".md")

    shutil.copy2(src, dest)

    markdown_error = None
    if not args.no_markdown:
        try:
            write_markdown_transcript(dest, markdown, args.markdown_max_tool_lines)
        except Exception as exc:
            markdown_error = str(exc)

    payload = {
        "source": str(src),
        "destination": str(dest),
        "markdown_destination": str(markdown) if not args.no_markdown and markdown_error is None else None,
        "markdown_error": markdown_error,
        "copied_at": dt.datetime.now().isoformat(timespec="seconds"),
        "score": chosen["score"],
        "reasons": chosen["reasons"],
        "session_id": session_id,
        "cwd": str(cwd),
        "git_root": str(root) if root else None,
        "git_branch": branch,
        "codex_home": str(home),
        "all_top_candidates": scored[: args.top],
        "warning": "Review before committing: Codex logs may contain secrets, proprietary code, prompts, file contents, and command output.",
    }
    write_meta(meta, payload)

    print(f"\nCopied Codex session log:\n  from: {src}\n  to:   {dest}")
    if args.no_markdown:
        print("Markdown transcript: skipped by --no-markdown")
    elif markdown_error is not None:
        print(f"Markdown transcript failed: {markdown_error}", file=sys.stderr)
    else:
        print(f"Markdown transcript:\n  {markdown}")
    print(f"Metadata:\n  {meta}")
    print("\nRecommended .gitignore entry:\n  .codex-session-logs/")
    return 4 if markdown_error is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
