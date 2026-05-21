---
name: herosms-api
description: HeroSMS 虚拟号码短信接收服务 API 指导。用于获取虚拟手机号码、接收验证码短信、管理激活状态。当用户需要调用 HeroSMS API、集成短信接收功能、使用 SMS-Activate 兼容接口、获取虚拟号码接收 OTP 验证码时触发。关键词：herosms, sms-activate, virtual number, otp, verification code, 虚拟号码, 验证码接收, 短信激活。
---

# HeroSMS API 指导

## Overview

HeroSMS 是虚拟号码短信接收服务，提供两类 API：
1. **原生 REST API**: `https://hero-sms.com/api/v1` - 新版 API
2. **SMS-Activate 兼容 API**: `https://hero-sms.com/stubs/handler_api.php` - 兼容 SMS-Activate 软件

认证方式：所有请求需携带 API Key（通过 `api_key` 参数或 Authorization Header）。

## 核心工作流

```
1. getBalance → 查询余额
2. getNumber → 获取号码（返回 activationId 和 phoneNumber）
3. getStatus → 轮询等待短信（STATUS_WAIT_CODE → STATUS_OK:code）
4. setStatus(6) → 完成激活确认
   或 setStatus(8) → 取消激活（2分钟内不可取消）
```

## SMS-Activate API 快速参考

| Action | 方法 | 功能 | 关键参数 |
|--------|------|------|---------|
| getBalance | GET | 查询余额 | api_key |
| getNumber | GET | 获取号码 | api_key, service, country, operator(可选) |
| getNumberV2 | GET | 获取号码(增强) | api_key, service, country |
| setStatus | GET | 更改状态 | api_key, id, status |
| getStatus | GET | 获取状态 | api_key, id |
| getStatusV2 | GET | 获取状态(增强) | api_key, id |
| getActiveActivations | GET | 活动激活列表 | api_key, start, limit |
| getHistory | GET | 激活历史 | api_key, start, end, offset, size |
| getCountries | GET | 国家列表 | api_key |
| getServicesList | GET | 服务列表 | api_key |
| getOperators | GET | 运营商列表 | api_key, service, country |
| getPrices | GET | 价格查询 | api_key, service(可选), country(可选) |
| reactivate | POST | 重新激活号码 | api_key, id |
| prolong | POST | 延长激活时间 | api_key, id, hours |
| getRentNumber | GET | 租赁号码 | api_key, service, country, time |

## 状态代码

**getStatus 返回值：**

| 状态 | 含义 | 说明 |
|------|------|------|
| STATUS_WAIT_CODE | 等待短信 | 号码已就绪，等待验证码 |
| STATUS_WAIT_RETRY:seconds | 等待重试 | 等待用户输入验证码确认 |
| STATUS_WAIT_RESEND | 等待重发 | 可请求重发短信 |
| STATUS_OK:code | 已收到验证码 | code 为验证码内容 |
| STATUS_CANCEL | 已取消 | 激活已取消 |

**setStatus 参数值：**

| 值 | 含义 | 使用场景 |
|----|------|---------|
| 3 | 请求重发短信 | STATUS_WAIT_RESEND 状态下可用 |
| 6 | 完成激活 | 收到验证码后确认 |
| 8 | 取消激活 | 2分钟内不可取消 |

## 常见错误

| 错误代码 | 含义 | 处理建议 |
|----------|------|---------|
| NO_KEY | 未提供 API Key | 检查 api_key 参数 |
| BAD_KEY | API Key 无效 | 验证 API Key 是否正确 |
| NO_NUMBERS | 无可用号码 | 尝试其他国家或服务 |
| BAD_SERVICE | 服务名称错误 | 检查 service 参数值 |
| WRONG_COUNTRY | 国家 ID 错误 | 使用 getCountries 获取有效国家列表 |
| NO_ACTIVATION | 激活 ID 不存在 | 检查 activationId |
| BANNED | 账户被临时封禁 | 查看 banned_until 时间 |
| EARLY_CANCEL_DENIED | 2分钟内不可取消 | 等待后再取消 |

## 服务代码示例

常用服务代码（使用 getServicesList 获取完整列表）：

| 代码 | 服务 |
|------|------|
| tg | Telegram |
| ig | Instagram |
| fb | Facebook |
| vk | VK |
| wa | WhatsApp |
| go | Google |
| am | Amazon |
| gg | Gmail |

## 国家代码示例

常用国家代码（使用 getCountries 获取完整列表）：

| 代码 | 国家 |
|------|------|
| 0 | 俄罗斯 |
| 6 | 印度尼西亚 |
| 16 | 哈萨克斯坦 |
| 48 | 英国 |
| 50 | 德国 |
| 51 | 法国 |
| 90 | 土耳其 |

## Webhook 配置

实时短信通知（无需轮询）：
- 方法：POST
- Content-Type：application/json
- 超时：3秒
- 重试：至少7次，间隔20-30秒
- 白名单 IP：`84.32.223.53`, `185.138.88.87`

Webhook 请求体：
```json
{
  "activationId": "123456789",
  "phoneNumber": "79584******",
  "smsCode": "12345",
  "smsText": "Your code is 12345"
}
```

## 完整 API 参考

详细 API 规范见 [references/api_openapi.json](references/api_openapi.json)（完整 OpenAPI 3.1.0 规范）。