# HeroSMS API 详细参考

## 目录

1. [服务器地址](#服务器地址)
2. [认证](#认证)
3. [SMS-Activate API](#sms-activate-api)
4. [Emails API](#emails-api)
5. [Activations API](#activations-api)
6. [Webhooks](#webhooks)
7. [数据模型](#数据模型)

---

## 服务器地址

| 服务器 | URL | 说明 |
|--------|-----|------|
| HeroSMS API | `https://hero-sms.com/api/v1` | 原生 REST API |
| SMS-Activate 兼容 | `https://hero-sms.com/stubs/handler_api.php` | 兼容 SMS-Activate 软件 |

---

## 认证

所有请求需要 API Key 认证：

**Query 参数方式：**
```
?api_key=YOUR_API_KEY&action=getBalance
```

**Header 方式：**
```
Authorization: Bearer YOUR_API_KEY
```

---

## SMS-Activate API

### getBalance - 查询余额

**请求：**
```
GET https://hero-sms.com/stubs/handler_api.php?api_key={key}&action=getBalance
```

**响应：**
```
ACCESS_BALANCE:100.50
```

---

### getNumber - 获取号码

**请求：**
```
GET https://hero-sms.com/stubs/handler_api.php?api_key={key}&action=getNumber&service={service}&country={country}
```

**参数：**
| 参数 | 必填 | 说明 |
|------|------|------|
| service | 是 | 服务代码（如 tg, ig, fb） |
| country | 是 | 国家代码 |
| operator | 否 | 运营商（any/mtn/vodafone 等） |
| max_price | 否 | 最高价格限制 |
| phone_exception | 否 | 排除特定号码前缀 |

**响应：**
```
ACCESS_NUMBER:123456789:7912345678
```
格式：`ACCESS_NUMBER:{activationId}:{phoneNumber}`

---

### getNumberV2 - 获取号码（增强版）

**响应（JSON）：**
```json
{
  "activationId": "635468024",
  "phoneNumber": "79584******",
  "activationCost": 12.5,
  "currency": 840,
  "countryCode": 6,
  "countryPhoneCode": 62,
  "canGetAnotherSms": true,
  "activationTime": "2026-02-18T16:11:33+00:00",
  "activationEndTime": "2026-02-18T18:11:23+00:00",
  "activationOperator": "any"
}
```

---

### setStatus - 更改激活状态

**请求：**
```
GET https://hero-sms.com/stubs/handler_api.php?api_key={key}&action=setStatus&id={id}&status={status}
```

**状态值：**
| 值 | 含义 | 使用场景 |
|----|------|---------|
| 3 | 请求重发短信 | 等待重发状态可用 |
| 6 | 完成激活 | 收到验证码后确认 |
| 8 | 取消激活 | 返还资金（前2分钟不可） |

**响应：**
- `ACCESS_RETRY_GET` - 等待新短信
- `ACCESS_ACTIVATION` - 激活完成
- `ACCESS_CANCEL` - 激活取消
- `EARLY_CANCEL_DENIED` - 2分钟内不可取消

---

### getStatus - 获取激活状态

**请求：**
```
GET https://hero-sms.com/stubs/handler_api.php?api_key={key}&action=getStatus&id={id}
```

**响应状态：**
| 状态 | 说明 |
|------|------|
| `STATUS_WAIT_CODE` | 等待短信 |
| `STATUS_WAIT_RETRY:{seconds}` | 等待验证码确认 |
| `STATUS_WAIT_RESEND` | 可请求重发 |
| `STATUS_OK:{code}` | 已收到验证码 |
| `STATUS_CANCEL` | 激活已取消 |

---

### getStatusV2 - 获取状态（增强版）

**响应（JSON）：**
```json
{
  "verificationType": 2,
  "sms": {
    "dateTime": "2026-02-18 16:11:33",
    "code": "12345",
    "text": "Your code is 12345"
  },
  "call": {
    "from": "79584******",
    "text": "Your verification code is 12345",
    "code": "12345",
    "dateTime": "2026-02-18 16:11:33",
    "url": "https://voice.file.url",
    "parsingCount": 1
  }
}
```

---

### getActiveActivations - 活动激活列表

**请求：**
```
GET ?api_key={key}&action=getActiveActivations&start=0&limit=100
```

**响应：**
```json
{
  "status": "success",
  "data": [
    {
      "activationId": "635468021",
      "serviceCode": "vk",
      "phoneNumber": "79********1",
      "activationCost": 12.5,
      "activationStatus": "4",
      "smsCode": "12345",
      "smsText": "Your code is 12345",
      "activationTime": "2022-06-01 16:59:16",
      "countryCode": "2",
      "countryName": "Kazakhstan",
      "canGetAnotherSms": "1",
      "currency": 840
    }
  ]
}
```

---

### getHistory - 激活历史

**请求：**
```
GET ?api_key={key}&action=getHistory&start={unix_timestamp}&end={unix_timestamp}&offset=0&size=100
```

---

### getCountries - 国家列表

**请求：**
```
GET ?api_key={key}&action=getCountries
```

---

### getServicesList - 服务列表

**请求：**
```
GET ?api_key={key}&action=getServicesList
```

---

### getPrices - 价格查询

**请求：**
```
GET ?api_key={key}&action=getPrices&service={service}&country={country}
```

**响应：**
```json
[
  {
    "baa": {
      "cost": 0.08,
      "count": 25370,
      "physicalCount": 14528
    }
  }
]
```

---

### reactivate - 重新激活号码

**请求（POST）：**
```
POST ?api_key={key}&action=reactivate&id={id}
```

---

### prolong - 延长激活时间

**请求（POST）：**
```
POST ?api_key={key}&action=prolong&id={id}&hours={hours}
```

---

## Emails API

### GET /emails - 获取邮箱激活列表

**请求：**
```
GET https://hero-sms.com/api/v1/emails?search={search}&size=10&page=1
```

**状态筛选：**
| ID | 状态 |
|----|------|
| 3 | 活动中 |
| 4 | 已完成 |
| 5 | 已取消 |
| 6 | 已过期 |

---

### POST /emails - 购买邮箱激活

**请求：**
```json
{
  "site": "telegram.com",
  "domain": "gmail.com"
}
```

---

### POST /emails/batch - 批量购买邮箱

**请求：**
```json
{
  "site": "telegram.com",
  "domain": "gmail.com",
  "count": 5
}
```

---

### GET /emails/{emailId} - 检查邮箱状态

---

### DELETE /emails/{emailId} - 取消邮箱激活

---

### GET /emails/domains - 获取可用域名

---

## Activations API

### GET /activations/offers - 激活优惠

**请求：**
```
GET https://hero-sms.com/api/v1/activations/offers?services={service}&countries={country}
```

**响应：**
```json
{
  "data": {
    "ig": {
      "6": {
        "prices": {
          "default": 0.0334,
          "retail": 0.0334,
          "min": 0.0334
        },
        "counts": {
          "total": 39166,
          "physical": 25787,
          "defaultPrice": 31838
        }
      }
    }
  }
}
```

---

## Webhooks

### 配置

- **方法**: POST
- **Content-Type**: application/json
- **超时**: 3秒
- **重试**: 至少7次，间隔20-30秒
- **白名单IP**: `84.32.223.53`, `185.138.88.87`

### 请求体

```json
{
  "activationId": "123456789",
  "phoneNumber": "79584******",
  "smsCode": "12345",
  "smsText": "Your code is 12345"
}
```

---

## 数据模型

### EmailActivation

| 字段 | 类型 | 说明 |
|------|------|------|
| id | integer | 激活ID |
| email | string | 邮箱地址 |
| site | string | 目标网站 |
| domain | string | 邮箱域名 |
| status | integer | 状态码 |
| cost | float | 费用 |
| createdAt | datetime | 创建时间 |

### ActivationStatusV2

| 字段 | 类型 | 说明 |
|------|------|------|
| verificationType | integer | 验证类型(1=SMS,2=Call) |
| sms.code | string | 验证码 |
| sms.text | string | 短信全文 |
| sms.dateTime | datetime | 接收时间 |
| call.code | string | 语音验证码 |
| call.url | string | 语音文件URL |

---

## 完整 OpenAPI 规范

详见 [api_openapi.json](api_openapi.json)（OpenAPI 3.1.0 规范，5127行完整文档）。