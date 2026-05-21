# Claude Code SSE Event Wire Format

## SSE frame

```text
event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hi"}}

```

## message_start

```json
{
  "type": "message_start",
  "message": {
    "id": "msg_...",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5",
    "content": [],
    "stop_reason": null,
    "stop_sequence": null,
    "usage": { "input_tokens": 10, "output_tokens": 0 }
  }
}
```

## content_block_start

Text:

```json
{ "type": "content_block_start", "index": 0, "content_block": { "type": "text", "text": "" } }
```

Tool:

```json
{
  "type": "content_block_start",
  "index": 0,
  "content_block": { "type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {} }
}
```

Thinking:

```json
{ "type": "content_block_start", "index": 0, "content_block": { "type": "thinking", "thinking": "", "signature": "" } }
```

## content_block_delta

| Delta | Payload | 适用 block |
|---|---|---|
| `text_delta` | `{ "type":"text_delta", "text":"..." }` | `text` |
| `input_json_delta` | `{ "type":"input_json_delta", "partial_json":"..." }` | `tool_use` / `server_tool_use` |
| `thinking_delta` | `{ "type":"thinking_delta", "thinking":"..." }` | `thinking` |
| `signature_delta` | `{ "type":"signature_delta", "signature":"..." }` | `thinking` |
| `citations_delta` | provider-specific | 可忽略 |

## content_block_stop

```json
{ "type": "content_block_stop", "index": 0 }
```

## message_delta

```json
{
  "type": "message_delta",
  "delta": { "stop_reason": "end_turn", "stop_sequence": null },
  "usage": { "output_tokens": 20 }
}
```

`stop_reason` 常见值：

| 值 | 含义 |
|---|---|
| `end_turn` | 正常结束 |
| `tool_use` | 客户端应执行工具并继续下一轮 |
| `max_tokens` | 输出被截断 |
| `stop_sequence` | 命中停止序列 |
| `refusal` | 模型拒绝 |
| `model_context_window_exceeded` | 上下文窗口耗尽 |

## message_stop

```json
{ "type": "message_stop" }
```

## Usage

建议至少返回：

```json
{
  "input_tokens": 10,
  "output_tokens": 20,
  "cache_read_input_tokens": 0,
  "cache_creation_input_tokens": 0
}
```

## 坏流判定

Claude Code 会把这些视为坏流并可能 fallback：

- 没有任何事件。
- 没有 `message_start`。
- 有 `message_start` 但没有完成任何 content block 且没有 stop reason。
- SSE 创建阶段返回 404。
- 中途断开、超时或非 Anthropic event JSON。
