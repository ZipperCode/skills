---
name: account-credential-schema
description: Sub2API 账号认证凭证 JSON Schema 定义，包含所有平台和认证类型的字段规范
---

# 账号认证凭证 Schema

## 目录

1. [OAuth 类型](#oauth-类型)
2. [API Key 类型](#api-key-类型)
3. [Setup Token 类型](#setup-token-类型)
4. [Upstream 类型](#upstream-类型)
5. [Bedrock 类型](#bedrock-类型)
6. [Extra 扩展字段](#extra-扩展字段)

---

## OAuth 类型

用于 Anthropic、Gemini、Antigravity、OpenAI 等平台的 OAuth 认证。

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `access_token` | string | 访问令牌 |
| `refresh_token` | string | 刷新令牌 |
| `expires_at` | string | 过期时间 (ISO 8601 格式) |

### 示例

```json
{
  "access_token": "ya29.a0AfB...",
  "refresh_token": "1//0gB...",
  "expires_at": "2025-05-16T10:30:00Z"
}
```

---

## API Key 类型

用于直接使用 API Key 访问的账号。

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `api_key` | string | API 密钥 |

### 示例

```json
{
  "api_key": "sk-ant-api03-..."
}
```

---

## Setup Token 类型

用于 Anthropic 的 Setup Token 认证（仅限推理权限）。

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_key` | string | 会话密钥 |

### 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `org_id` | string | 组织 ID |

### 示例

```json
{
  "session_key": "session-xxx...",
  "org_id": "org-xxx"
}
```

---

## Upstream 类型

用于透传到上游 API 的账号配置。

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `base_url` | string | 上游 API 基础 URL |
| `api_key` | string | API 密钥 |

### 示例

```json
{
  "base_url": "https://api.example.com",
  "api_key": "sk-xxx"
}
```

---

## Bedrock 类型

用于 AWS Bedrock 服务的账号。

### 认证模式

通过 `auth_mode` 字段区分：

#### SigV4 签名模式

| 字段 | 类型 | 说明 |
|------|------|------|
| `auth_mode` | string | 固定值 `"sigv4"` |
| `access_key_id` | string | AWS Access Key ID |
| `secret_access_key` | string | AWS Secret Access Key |
| `region` | string | AWS 区域 (可选，默认 us-east-1) |

#### API Key 模式

| 字段 | 类型 | 说明 |
|------|------|------|
| `auth_mode` | string | 固定值 `"apikey"` |
| `api_key` | string | Bedrock API Key |

### 示例

```json
// SigV4 模式
{
  "auth_mode": "sigv4",
  "access_key_id": "AWS_ACCESS_KEY_ID_EXAMPLE",
  "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
  "region": "us-east-1"
}

// API Key 模式
{
  "auth_mode": "apikey",
  "api_key": "bedrock-api-key-xxx"
}
```

---

## Extra 扩展字段

Extra 字段用于存储平台特定的额外信息。

### 通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `model_mapping` | object | 模型名称映射 |
| `model_whitelist` | array | 可用模型白名单 |
| `privacy_mode` | string | 隐私模式 (`"standard"` / `"strict"`) |
| `base_rpm` | number | 基础 RPM 限制 |

### CRS 相关字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `crs_account_id` | string | CRS 同步账号 ID |
| `crs_channel_id` | string | CRS 渠道 ID |

### 示例

```json
{
  "model_mapping": {
    "claude-opus-4-6": "claude-opus-4-6-thinking"
  },
  "model_whitelist": [
    "claude-opus-4-6-thinking",
    "claude-sonnet-4-6"
  ],
  "privacy_mode": "standard",
  "base_rpm": 60
}
```

---

## 平台类型对照表

| 平台 | 认证类型 | 说明 |
|------|----------|------|
| `anthropic` | oauth, setup-token, apikey | Claude API |
| `gemini` | oauth | Google Gemini |
| `openai` | oauth, apikey | OpenAI GPT |
| `antigravity` | oauth | Antigravity 服务 |
| `bedrock` | bedrock | AWS Bedrock |

---

## 完整账号 JSON 示例

```json
{
  "name": "Claude OAuth Account",
  "notes": "Production account",
  "platform": "anthropic",
  "type": "oauth",
  "credentials": {
    "access_token": "ya29.a0AfB...",
    "refresh_token": "1//0gB...",
    "expires_at": "2025-05-16T10:30:00Z"
  },
  "extra": {
    "model_whitelist": ["claude-opus-4-6-thinking"],
    "privacy_mode": "standard"
  },
  "proxy_id": null,
  "concurrency": 5,
  "priority": 50,
  "rate_multiplier": 1.0
}
```
