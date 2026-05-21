# Claude Code Tool Wire Format

## Tool schema

```json
{
  "name": "Bash",
  "description": "Run a shell command",
  "input_schema": {
    "type": "object",
    "properties": {
      "command": { "type": "string" }
    },
    "required": ["command"]
  },
  "strict": true,
  "eager_input_streaming": true,
  "defer_loading": true,
  "cache_control": { "type": "ephemeral", "ttl": "5m" }
}
```

| 字段 | 服务端处理 |
|---|---|
| `name` | 必须保留，响应 tool_use 使用同名。 |
| `description` | 传给上游模型。 |
| `input_schema` | JSON Schema；转换为上游工具格式。 |
| `strict` | 可忽略；支持结构化输出时可启用强校验。 |
| `eager_input_streaming` | 可忽略；Claude Code 能处理普通 JSON delta。 |
| `defer_loading` | 可忽略或实现 ToolSearch。 |
| `cache_control` | 可忽略或透传。 |

## Tool choice

```json
{ "type": "auto" }
{ "type": "any" }
{ "type": "tool", "name": "Bash" }
```

## Tool use block

```json
{
  "type": "tool_use",
  "id": "toolu_1",
  "name": "Bash",
  "input": { "command": "ls" }
}
```

流式时 `input` 通过 `input_json_delta.partial_json` 分片发送。

## Tool result block

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_1",
  "content": "stdout text",
  "is_error": false
}
```

`content` 也可能是 content block array；网关应宽松接收。

## MCP names

MCP 工具名格式：

```text
mcp__<server_name>__<tool_name>
```

server name 中 `-` 通常会变成 `_`。网关不需要连接 MCP，只要把名字当普通工具名处理即可。

## Server tool

Claude Code 可能识别 `server_tool_use` 或 advisor 类型。外部大模型网关最小实现不需要主动生成；如果收到历史消息里的 `server_tool_use`，按普通 assistant content block 保留即可。
