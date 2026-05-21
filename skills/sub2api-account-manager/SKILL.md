---
name: sub2api-account-manager
description: Manage Sub2API account credentials via JSON files. Use when uploading, querying, or updating account authentication data in Sub2API backend. Supports OAuth, API Key, Setup Token, Upstream, and Bedrock credential types with schema validation.
---

# Sub2API Account Credential Manager

管理 Sub2API 后台账号认证数据的工作流。

## 功能概览

1. **上传认证 JSON 文件** - 创建新账号
2. **查询数据库中的账号** - 按平台/类型筛选
3. **更新认证数据** - 修改现有账号

## 工作流程

### 1. 上传认证文件

```
用户提供 JSON 文件 → 验证格式 → 通过 API 创建账号
```

**验证步骤：**
1. 读取用户提供的 JSON 文件
2. 检查必填字段: `name`, `platform`, `type`, `credentials`
3. 根据 `type` 验证 `credentials` 结构
4. 参考 [account-credential-schema.md](references/account-credential-schema.md) 进行格式校验

**API 调用：**
```bash
POST /api/v1/admin/accounts
Content-Type: application/json

{
  "name": "Account Name",
  "platform": "anthropic|gemini|openai|antigravity|bedrock",
  "type": "oauth|apikey|setup-token|upstream|bedrock",
  "credentials": { ... },
  "extra": { ... },
  "concurrency": 3,
  "priority": 50
}
```

### 2. 查询账号列表

按平台和类型筛选账号：

```bash
GET /api/v1/admin/accounts?platform=anthropic&type=oauth&page=1&page_size=20
```

**响应字段：**
- `id` - 账号 ID
- `name` - 账号名称
- `platform` - 平台
- `type` - 认证类型
- `status` - 状态 (active/error/disabled)
- `schedulable` - 是否可调度
- `last_used_at` - 最后使用时间

### 3. 更新账号

```bash
PUT /api/v1/admin/accounts/{id}
Content-Type: application/json

{
  "name": "New Name",
  "credentials": { ... },
  "extra": { ... }
}
```

## 认证类型验证规则

| type | credentials 必填字段 |
|------|---------------------|
| `oauth` | `access_token`, `refresh_token`, `expires_at` |
| `apikey` | `api_key` |
| `setup-token` | `session_key` |
| `upstream` | `base_url`, `api_key` |
| `bedrock` | `auth_mode` + (`access_key_id`/`secret_access_key` 或 `api_key`) |

详细字段规范见 [references/account-credential-schema.md](references/account-credential-schema.md)。

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `Invalid request` | JSON 格式错误或缺少必填字段 | 检查 JSON 结构和必填字段 |
| `rate_multiplier must be >= 0` | 计费倍率为负数 | 设置正确的倍率值 |
| `type must be oneof` | 认证类型不在允许列表中 | 使用 oauth/apikey/setup-token/upstream/bedrock |

## 示例：批量导入

1. 准备 JSON 文件数组
2. 逐个验证格式
3. 调用批量创建 API：

```bash
POST /api/v1/admin/accounts/batch
Content-Type: application/json

{
  "accounts": [
    { "name": "...", "platform": "...", ... },
    { "name": "...", "platform": "...", ... }
  ]
}
```
