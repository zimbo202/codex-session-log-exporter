# Codex Session Log Exporter 使用指南

`codex-session-log-exporter` 是一个 Codex skill，用于从 `~/.codex/sessions` 中导出当前 Codex session log，并复制到当前项目目录。

它会复制选中的 JSONL 日志文件，并且默认额外生成一个可读的 Markdown 转录文件。

## 环境需求

- Codex CLI 或 Codex IDE 的 session log 必须存在于 `$CODEX_HOME/sessions` 或 `~/.codex/sessions` 下。
- 推荐使用 Python 3.10 或更新版本。
- 不需要任何第三方 Python 包。
- `git` 是可选依赖，但推荐安装。可用时，脚本会使用当前 git root 和 branch 作为额外信号来识别正确的 session log。
- 请从你希望保存导出日志的项目目录中运行脚本。

如果没有设置 `CODEX_HOME`，脚本会使用：

```text
~/.codex
```

## 安装方法

### 安装为仓库级 Skill

将这个 skill 目录复制到目标仓库：

```text
.agents/skills/codex-session-log-exporter/
```

然后在该仓库中运行：

```bash
python3 .agents/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

### 全局安装

将这个 skill 目录复制到全局 Codex skills 目录：

```text
~/.codex/skills/codex-session-log-exporter/
```

然后可以在任意项目目录中运行：

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

安装新的全局 skill 后，需要重启 Codex，Codex 才能发现它。

## 基本用法

在项目根目录中运行：

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

默认输出：

```text
.codex-session-logs/
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.jsonl
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.md
  codex-session-YYYYMMDD-HHMMSS-<session-id-or-hash>.meta.json
```

`.jsonl` 文件是原始 Codex session log。`.md` 文件是可读的转录文档。`.meta.json` 文件记录源路径、目标路径、置信分数、匹配原因和排名靠前的候选日志。

## 在 Session 对话中使用

安装并重启 Codex 后，可以直接在 Codex 对话中用自然语言请求导出当前 session log。Codex 会根据你的描述选择是否生成 Markdown。

### 只导出当前 Session Log

你可以说：

```text
导出当前 Codex session log
```

或：

```text
把当前 Codex session log 复制到项目目录
```

效果：

- Codex 会识别当前 session 对应的 JSONL 日志文件。
- 日志会被复制到当前项目的 `.codex-session-logs/` 目录。
- 会生成 `.jsonl` 和 `.meta.json`。
- 不会生成 `.md`，因为你没有明确要求转换 Markdown。

等价命令：

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --no-markdown
```

### 导出当前 Session Log 并转换为 Markdown

你可以说：

```text
导出当前 Codex session log，并转换为md
```

或：

```text
导出当前会话日志，同时生成可读的 Markdown
```

效果：

- Codex 会识别当前 session 对应的 JSONL 日志文件。
- 日志会被复制到当前项目的 `.codex-session-logs/` 目录。
- 会生成 `.jsonl`、`.md` 和 `.meta.json`。
- `.md` 文件会把用户消息、助手消息、工具调用和工具结果整理成更易阅读的 Markdown 转录文档。

等价命令：

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

### 明确要求不转换 Markdown

你可以说：

```text
导出当前 Codex session log，不需要转换md
```

或：

```text
只导出原始 JSONL，不要生成 Markdown
```

效果：

- Codex 只复制原始 JSONL 日志。
- 会生成 `.jsonl` 和 `.meta.json`。
- 不会生成 `.md`。

等价命令：

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --no-markdown
```

## 使用示例

### 导出 JSONL 和 Markdown

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir .
```

这是默认行为。

### 仅导出原始 JSONL 日志

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --no-markdown
```

当你只需要原始 Codex 日志文件时使用这个命令。

### 手动选择候选日志

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --choose
```

当存在多个最近的 Codex session，并且你希望自己选择正确日志时使用这个命令。

### 允许低置信度的最佳尝试

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --allow-low-confidence
```

只有在你理解当前存在歧义，并且仍然希望脚本复制得分最高的候选日志时，才使用这个选项。

### 使用自定义 Codex Home

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --codex-home /path/to/codex-home
```

如果你的 Codex 日志不在 `~/.codex` 下，可以使用这个选项。

### 使用自定义输出子目录

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --dest-subdir exported-codex-logs
```

这会把文件写入：

```text
exported-codex-logs/
```

### 在 Markdown 中保留完整工具输出

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --markdown-max-tool-lines 0
```

默认情况下，Markdown 转录文件会截断特别长的工具输出。原始 JSONL 文件始终会被完整复制，不会被修改。

## 脚本如何识别当前 Session

脚本不会简单地复制最新的 `rollout-*.jsonl` 文件。它会根据多个信号对候选日志打分：

- 显式 session id 环境变量，如果存在。
- 当前工作目录是否出现在日志内容中。
- 当前 git root 是否出现在日志内容中。
- 当前 git branch 是否出现在日志内容中。
- 项目目录名是否出现在日志内容中。
- 文件修改时间是否足够近。
- 日志文件是否看起来仍在活跃写入。
- 文件名或日志内容中发现的类似 session id 的值。

如果得分最高的候选日志低于置信度阈值，脚本会停止，除非你使用 `--choose` 或 `--allow-low-confidence`。

## 推荐的 Gitignore 设置

将以下内容加入项目的 `.gitignore`：

```gitignore
.codex-session-logs/
```

如果你使用了自定义输出子目录，请忽略对应的目录。

## 安全注意事项

Codex session log 可能包含敏感信息，包括：

- prompts 和 instructions；
- 文件内容；
- 命令输出；
- 路径和环境细节；
- secrets、tokens、credentials 或专有代码。

在分享或提交导出的 `.jsonl`、`.md` 和 `.meta.json` 文件之前，请先审阅内容。除非你已经明确确认日志可以安全分享，否则不要把日志上传到外部系统。

## 故障排查

### 找不到日志

检查 Codex session 的存储位置：

```bash
echo "${CODEX_HOME:-$HOME/.codex}"
find "${CODEX_HOME:-$HOME/.codex}/sessions" -name '*.jsonl' | tail
```

如果日志在其他位置，请传入 `--codex-home`。

### 选中了错误的 Session

使用手动选择模式：

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --choose
```

查看每个候选日志打印出的得分原因。

### Markdown 文件太大

减少工具结果保留的行数：

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --markdown-max-tool-lines 80
```

或者跳过 Markdown：

```bash
python3 ~/.codex/skills/codex-session-log-exporter/scripts/copy_codex_session_log.py --output-dir . --no-markdown
```

### Markdown 缺少部分原始细节

Markdown 转录文件是为阅读设计的。它可能会根据 `--markdown-max-tool-lines` 截断较长的工具输出。请将复制出的 `.jsonl` 文件作为权威的原始日志。
