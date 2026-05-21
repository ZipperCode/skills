# Claude Code Context Management Wire Format

## context_management

```json
{
  "context_management": {
    "edits": [
      {
        "type": "clear_tool_uses_20250919",
        "trigger": { "type": "input_tokens", "value": 180000 },
        "clear_at_least": { "type": "input_tokens", "value": 140000 },
        "clear_tool_inputs": ["Bash", "Shell", "PowerShell", "Glob", "Grep", "FileRead", "WebFetch", "WebSearch"]
      },
      {
        "type": "clear_thinking_20251015",
        "keep": "all"
      }
    ]
  }
}
```

## clear_tool_uses_20250919

| 字段 | 含义 |
|---|---|
| `trigger` | 到达多少 input tokens 后触发。 |
| `clear_at_least` | 至少清理多少 tokens。 |
| `keep` | 保留多少 tool uses。 |
| `clear_tool_inputs` | 清理哪些工具输入。 |
| `exclude_tools` | 不清理哪些工具。 |

外部网关可忽略该策略。

## clear_thinking_20251015

```json
{ "type": "clear_thinking_20251015", "keep": "all" }
{ "type": "clear_thinking_20251015", "keep": { "type": "thinking_turns", "value": 1 } }
```

外部网关可忽略该策略。

## cache_control

```json
{ "type": "ephemeral", "scope": "org", "ttl": "1h" }
{ "type": "ephemeral", "ttl": "5m" }
```

可能出现在 system text block、message content block、tool schema。

## cache_reference

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_1",
  "cache_reference": "toolu_1",
  "content": "..."
}
```

## cache_edits

```json
{
  "type": "cache_edits",
  "edits": [{ "type": "delete", "cache_reference": "toolu_1" }]
}
```

不支持缓存时可忽略。

## Usage cache fields

响应 usage 建议包含：

```json
{
  "input_tokens": 100,
  "output_tokens": 10,
  "cache_read_input_tokens": 0,
  "cache_creation_input_tokens": 0
}
```
