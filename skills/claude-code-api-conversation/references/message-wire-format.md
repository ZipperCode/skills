# Claude Code Message Wire Format

## Message

```json
{
  "role": "user",
  "content": [
    { "type": "text", "text": "hello" }
  ]
}
```

```json
{
  "role": "assistant",
  "content": [
    { "type": "text", "text": "hello" }
  ]
}
```

## Content blocks

### text

```json
{ "type": "text", "text": "hello", "cache_control": { "type": "ephemeral" } }
```

### tool_use

```json
{ "type": "tool_use", "id": "toolu_1", "name": "Bash", "input": { "command": "ls" } }
```

### tool_result

```json
{ "type": "tool_result", "tool_use_id": "toolu_1", "content": "stdout", "is_error": false }
```

### image

```json
{
  "type": "image",
  "source": { "type": "base64", "media_type": "image/png", "data": "..." }
}
```

### document

```json
{
  "type": "document",
  "source": { "type": "base64", "media_type": "application/pdf", "data": "..." }
}
```

### thinking

```json
{ "type": "thinking", "thinking": "...", "signature": "..." }
```

### redacted_thinking

```json
{ "type": "redacted_thinking", "data": "..." }
```

### server_tool_use

```json
{ "type": "server_tool_use", "id": "srv_1", "name": "advisor", "input": {} }
```

### cache_edits

```json
{
  "type": "cache_edits",
  "edits": [{ "type": "delete", "cache_reference": "toolu_1" }]
}
```

## System block

```json
{
  "type": "text",
  "text": "system prompt",
  "cache_control": { "type": "ephemeral", "scope": "org", "ttl": "1h" }
}
```

## Pairing rule

Valid tool round:

```json
[
  {
    "role": "assistant",
    "content": [{ "type": "tool_use", "id": "toolu_1", "name": "Bash", "input": { "command": "ls" } }]
  },
  {
    "role": "user",
    "content": [{ "type": "tool_result", "tool_use_id": "toolu_1", "content": "result" }]
  }
]
```

外部网关可以不主动修复历史，但不能因为可恢复的 pairing 问题返回 500。
