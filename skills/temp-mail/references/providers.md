# Temp-Mail Provider Configuration Reference

This skill reads a single JSON config file, expected by default at:

- `~/.hermes/email/temp-mail.json`

Top-level fields:

- `default_provider`: preferred provider instance name or provider type
- `request_timeout`: single HTTP request timeout in seconds
- `wait_timeout`: total polling timeout in seconds
- `wait_interval`: sleep between polling attempts in seconds
- `selection_strategy`: one of `priority`, `fallback`, `round_robin`
- `providers`: list of provider configs

## Provider fields shared by all providers

- `name`: user-chosen provider instance name; should be unique
- `type`: provider type identifier
- `enable`: whether the provider is eligible for use
- `priority`: higher numbers are preferred first under `priority`/`fallback`

## Supported provider types

### tempmail_lol

Fields:
- `api_key` optional but commonly used
- `domain` optional list; entries may include `*.` wildcard prefixes

Example:

```json
{
  "name": "primary-tempmail",
  "type": "tempmail_lol",
  "enable": true,
  "priority": 100,
  "api_key": "YOUR_API_KEY",
  "domain": ["example.com", "*.example.net"]
}
```

### duckmail

Fields:
- `api_key` required
- `default_domain` optional; defaults to `duckmail.sbs`

### gptmail

Fields:
- `api_key` required
- `default_domain` optional

Notes:
- Shared keys may work intermittently if the daily pool is exhausted.
- In this environment, a shared GPTMail key is known to reset around 08:00 daily and may fail when the shared quota is consumed.

### aliasvault

Fields:
- `base_url` optional, defaults to `https://app.aliasvault.net/api`
- `username` required
- `password` required

Notes:
- This provider is account-backed, not anonymous temp-mail API key based.
- It logs into a real AliasVault account, creates an alias by editing the encrypted vault, then reads mailbox contents through the AliasVault API.
- `2FA` is not supported by the current implementation.
- The account must actually have available private/public email domains in the vault.

### moemail

Fields:
- `api_base` required; for the documented public API, use `https://moemail.app`
- `api_key` required
- `domain` required list
- `expiry_time` optional integer; API examples show milliseconds, so use values like `3600000` for one hour

Notes:
- A valid API key alone may not be enough. The service can return HTTP 403 if the account role does not include OpenAPI access or has no API quota.

### cloudflare_temp_email

Fields:
- `api_base` required
- `admin_password` required
- `domain` required list

### inbucket

Fields:
- `api_base` required
- `domain` required list
- `random_subdomain` optional boolean

### yyds_mail

Fields:
- `api_base` optional, defaults to `https://maliapi.215.im/v1`
- `api_key` required
- `domain` optional list
- `subdomain` optional
- `wildcard` optional boolean

## Selection strategy

### priority
Always try enabled providers in descending `priority` order.

### fallback
Same ordering as `priority`, but intended as the default registration workflow: keep trying next provider when mailbox creation fails.

### round_robin
The current helper still returns enabled providers in deterministic order, but this strategy name reserves the intent that future scheduling may rotate across providers rather than always preferring the same one.

## Mailbox session shape

Mailbox creation returns:

```json
{
  "provider": "tempmail_lol",
  "provider_instance": "primary-tempmail",
  "provider_ref": "tempmail_lol#1",
  "address": "abc123@example.com",
  "session": {
    "provider": "tempmail_lol",
    "provider_ref": "tempmail_lol#1",
    "address": "abc123@example.com",
    "token": "..."
  },
  "created_at": "2026-05-10T07:20:00+00:00"
}
```

Persist the entire returned object if you plan to wait for mail later. The `session` sub-object contains provider-specific state like `token`, `email_id`, or `mailbox_name`.
