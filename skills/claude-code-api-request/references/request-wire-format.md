# Claude Code 网关 HTTP Wire Format

## 公共头

| Header | 必需 | 网关处理 |
|---|---|---|
| `Authorization` | 否 | Bearer token。 |
| `x-api-key` | 否 | API key。 |
| `anthropic-version` | 否 | 常见 `2023-06-01`。 |
| `anthropic-beta` | 否 | 逗号分隔 beta。 |
| `x-app` | 否 | 通常 `cli`。 |
| `User-Agent` | 否 | 记录即可。 |
| `X-Claude-Code-Session-Id` | 否 | 用于会话级日志/限流。 |
| `x-client-request-id` | 否 | 用于请求关联。 |
| `x-claude-remote-container-id` | 否 | 可忽略。 |
| `x-claude-remote-session-id` | 否 | 可忽略。 |

## POST /v1/messages

### Query

`beta=true` 可出现，服务端应接受。

### Body 字段

| 字段 | 类型 | 处理 |
|---|---|---|
| `model` | string | 必需；映射到上游模型。 |
| `messages` | array | 必需；见 conversation skill。 |
| `system` | string/array | 可选；推荐支持 text block array。 |
| `tools` | array | 可选；见 tools skill。 |
| `tool_choice` | object | 可选；`auto`/`any`/`tool`。 |
| `max_tokens` | number | 输出上限；缺失时给默认值。 |
| `stream` | boolean | `true` 走 SSE，`false` 走完整 JSON。 |
| `thinking` | object | 可选；`adaptive` 或 `enabled`。 |
| `temperature` | number | 可选。 |
| `metadata` | object | 可选；记录/透传。 |
| `betas` | array | 可选；body beta。 |
| `context_management` | object | 可选；见 compaction skill。 |
| `output_config` | object | 可选；结构化输出/effort。 |
| `speed` | string | 可选；`fast` 可忽略。 |
| `anthropic_beta` | array | 可选；兼容 Bedrock body beta。 |
| `anti_distillation` | array | 可选；外部网关可忽略。 |
| `anthropic_internal` | object | 可选；外部网关可忽略。 |

### 非流式响应

```json
{
  "id": "msg_gateway_1",
  "type": "message",
  "role": "assistant",
  "model": "claude-sonnet-4-5",
  "content": [{ "type": "text", "text": "ok" }],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 10,
    "output_tokens": 2,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0
  }
}
```

## POST /v1/messages/count_tokens

请求字段同 `/v1/messages` 的统计子集：`model`、`messages`、`system`、`tools`、`thinking`、`betas`。

响应：

```json
{ "input_tokens": 10 }
```

## Files API

### POST /v1/files

Headers:

- `Authorization: Bearer <token>`
- `anthropic-version: 2023-06-01`
- `anthropic-beta: files-api-2025-04-14,oauth-2025-04-20`

Multipart fields:

- `file`
- `purpose=user_data`

响应至少包含：

```json
{ "id": "file_1", "filename": "a.txt", "size_bytes": 12 }
```

### GET /v1/files

Query:

- `after_created_at`
- `after_id`

响应：

```json
{ "data": [], "has_more": false }
```

### GET /v1/files/{file_id}/content

返回文件二进制。404 表示不存在，403 表示无权限。

## GET /v1/models

响应：

```json
{
  "data": [
    { "id": "claude-sonnet-4-5", "type": "model", "display_name": "Claude Sonnet 4.5" }
  ],
  "has_more": false
}
```

## 错误格式

```json
{
  "type": "error",
  "error": { "type": "invalid_request_error", "message": "..." }
}
```

状态码建议：400 invalid request，401 auth，403 permission，408 timeout，409 conflict，429 rate limit，500/502/503/504 api error，529 overloaded。
