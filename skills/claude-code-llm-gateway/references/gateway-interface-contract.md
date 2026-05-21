# Claude Code 大模型请求网关接口合同

## 范围

本合同只覆盖 Claude Code 的大模型请求网关面：Messages、SSE、Token Counting、Files、Models，以及这些接口共用的鉴权、Beta、错误兼容语义。

不覆盖：Claude.ai 登录 OAuth 流程、`/api/claude_cli/bootstrap`、`/v1/sessions/*`、CCR worker、session ingress、team memory sync、remote managed settings。

## 公共请求头

| Header | 处理要求 |
|---|---|
| `Authorization: Bearer <token>` | 接受。可映射为平台 token、用户 token 或上游 token。 |
| `x-api-key` | 接受。与 Bearer 同时存在时按你的平台策略决定优先级。 |
| `anthropic-version` | 接受，常见值 `2023-06-01`。不识别时不要失败。 |
| `anthropic-beta` | 接受逗号分隔 beta。影响能力开关，也可仅记录/透传。 |
| `x-app` | Claude Code 通常为 `cli`。可用于识别客户端。 |
| `User-Agent` | 记录即可。 |
| `X-Claude-Code-Session-Id` | 会话级 ID。建议用于日志、限流和 trace。 |
| `x-client-request-id` | 第一方请求关联 ID。建议原样写入日志并在错误中保留。 |
| `x-claude-remote-container-id` / `x-claude-remote-session-id` | 远程环境提示。模型网关可忽略。 |

## POST /v1/messages

### Query

Claude Code 可能调用 `/v1/messages?beta=true`。服务端应接受 `beta=true`，不要把它当成不同接口。

### Request Body

| 字段 | 要求 |
|---|---|
| `model` | 必需。可在网关内映射为实际上游模型。 |
| `messages` | 必需。Anthropic message array。 |
| `system` | 可选。字符串或 text block array；Claude Code 通常发送 text block array。 |
| `tools` | 可选。Anthropic tool schema array。 |
| `tool_choice` | 可选。支持 `auto`、`any`、`tool`。 |
| `max_tokens` | 必需或默认。Claude Code 常用 8000，也可能升到 64000。 |
| `stream` | `true` 或 `false`。缺省时按 `false` 处理更安全。 |
| `thinking` | 可选。支持 `adaptive` 或 `enabled/budget_tokens`。 |
| `temperature` | 可选。thinking 禁用时常见。 |
| `metadata` | 可选。记录即可。 |
| `betas` | 可选。SDK body beta。 |
| `context_management` | 可选。不会实现也应容忍。 |
| `output_config` | 可选。结构化输出、effort、task budget 可能在这里。 |
| `speed` | 可选，常见值 `fast`。不支持时忽略。 |
| `anthropic_beta` | 可选，Bedrock 风格 body beta。 |
| `anti_distillation` / `anthropic_internal` | 可选，内部扩展。外部网关可忽略。 |

### Non-Streaming Response

返回完整 message：

```json
{
  "id": "msg_gateway_...",
  "type": "message",
  "role": "assistant",
  "model": "claude-sonnet-4-5",
  "content": [{ "type": "text", "text": "..." }],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 100,
    "output_tokens": 20,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0
  }
}
```

### Streaming Response

返回 `Content-Type: text/event-stream`。每个事件使用 SSE：

```text
event: message_start
data: {"type":"message_start","message":{...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":1}}

event: message_stop
data: {"type":"message_stop"}
```

## POST /v1/messages/count_tokens

请求体与 `/v1/messages` 的可统计部分一致：`model`、`messages`、`system`、`tools`、`thinking`、`betas`。

最小响应：

```json
{ "input_tokens": 1234 }
```

如果无法精确统计，可以用稳定估算。不要返回字符串；Claude Code 会检查 `input_tokens` 是否为 number。

## Files API

### POST /v1/files

- `Content-Type: multipart/form-data`
- 表单字段：
  - `file`: 文件内容
  - `purpose`: Claude Code 使用 `user_data`
- 建议要求 beta：`files-api-2025-04-14,oauth-2025-04-20`，但网关可宽松接受。

响应：

```json
{
  "id": "file_...",
  "type": "file",
  "filename": "name.ext",
  "size_bytes": 123,
  "created_at": "2026-05-21T00:00:00Z"
}
```

### GET /v1/files

支持查询参数：

| 参数 | 用途 |
|---|---|
| `after_created_at` | 只列出该时间之后创建的文件。 |
| `after_id` | 分页游标。 |

响应：

```json
{
  "data": [{ "id": "file_...", "filename": "name.ext", "size_bytes": 123 }],
  "has_more": false
}
```

### GET /v1/files/{file_id}/content

返回二进制 body。404 表示文件不存在，403 表示无权限。

## GET /v1/models

返回可迭代 models list。最小响应：

```json
{
  "data": [
    {
      "id": "claude-sonnet-4-5",
      "type": "model",
      "display_name": "Claude Sonnet 4.5",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "has_more": false
}
```

如果你的网关做模型别名，`id` 应该包含 Claude Code 配置里会发送的模型名，或能被网关映射。

## 错误响应

推荐形态：

```json
{
  "type": "error",
  "error": {
    "type": "rate_limit_error",
    "message": "rate limited"
  }
}
```

| HTTP | 建议 `error.type` | Claude Code 期望 |
|---|---|---|
| 400 | `invalid_request_error` | 通常不可重试。字段不支持时尽量忽略而不是 400。 |
| 401 | `authentication_error` | 触发 token/key 刷新或失败。 |
| 403 | `permission_error` | 通常不可重试；CCR 场景除外。 |
| 408 | `timeout_error` | 可重试。 |
| 409 | `conflict_error` | 可重试。 |
| 429 | `rate_limit_error` | 可重试；可带 `retry-after`。 |
| 500/502/503/504 | `api_error` | 可重试。 |
| 529 | `overloaded_error` | 可重试；前台请求会有限重试。 |

## 实现建议

- 对未知字段采用“忽略或透传”，不要默认拒绝。
- 对不支持的 beta 采用“降级能力”，不要默认拒绝。
- SSE 中断或 0 事件会触发 Claude Code 的非流式 fallback；网关应优先保证 stream 至少能输出 `message_start` 和最终 stop。
- 如果上游不是 Anthropic 模型，网关要负责把 OpenAI/自定义响应转换成 Anthropic content block 与 SSE event。
