---
name: temp-mail-orchestration
description: "Use when you need provider-agnostic temporary email workflows: create inboxes, wait for verification mail, extract codes or magic links, and support site registrations using preconfigured mail APIs."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [email, temp-mail, otp, verification, registration, api]
    related_skills: [himalaya, hermes-agent-skill-authoring]
---

# Temporary Email Orchestration

## Overview

This skill defines a provider-agnostic workflow for temporary email services used during website sign-up, login verification, sandbox account creation, and similar flows. It assumes the mailbox provider is accessed through HTTP APIs rather than IMAP/SMTP.

The main goal is to normalize a messy ecosystem of temp-mail providers into one repeatable agent workflow:
1. Choose a configured provider.
2. Create a mailbox.
3. Use the mailbox in the target site flow.
4. Poll for messages.
5. Extract either a verification code or a magic link.
6. Return structured results that later steps can consume.

This is intentionally independent of any one project. It is the class-level skill to consult whenever the user says things like "use a temp email", "register with email verification", or "wait for the verification code".

## When to Use

Use this skill when:
- A task requires a disposable or programmatically controlled email address.
- The user has already configured one or more email-provider API keys/base URLs.
- You need to register on a website and retrieve an OTP or confirmation link.
- You need a stable mailbox workflow that can swap providers without changing the rest of the automation.

Do not use this skill for:
- Normal personal email via IMAP/SMTP; use `himalaya` instead.
- Human-in-the-loop inbox browsing where the provider has no usable API.
- Cases where the site explicitly blocks disposable domains and the user has not provided alternatives.

## Canonical Workflow

### 1. Confirm the execution model
Prefer a unified script or helper service if the environment has one. If none exists, implement the provider calls directly with Python or shell+curl for the current task.

The preferred long-term architecture is:
- **Code layer:** one reusable script/service that knows how to talk to providers.
- **Skill layer:** this workflow, provider selection rules, extraction rules, and debugging guidance.

### 2. Load provider configuration
Expect a config object shaped roughly like:

```json
{
  "request_timeout": 30,
  "wait_timeout": 60,
  "wait_interval": 2,
  "providers": [
    {
      "type": "tempmail_lol",
      "enable": true,
      "api_key": "...",
      "domain": ["example.com"]
    }
  ]
}
```

Minimum behavior:
- Read timeout and polling settings.
- Ignore disabled providers.
- Fail fast if no provider is enabled.
- Preserve provider-specific fields untouched.

### 3. Create a mailbox
Return a normalized mailbox session object. At minimum, include:

```json
{
  "provider": "tempmail_lol",
  "provider_ref": "tempmail_lol#1",
  "address": "name@example.com"
}
```

Provider-specific auth/session fields may also be required, for example:
- `token`
- `email_id`
- `account_id`
- `password`
- `mailbox_name`

Important rules:
- Preserve whatever the provider returns that will be required for later polling.
- Treat the mailbox session as stateful input for later `wait-for-mail` / `wait-for-code` steps.
- If multiple providers are enabled, prefer deterministic selection or round-robin instead of hidden randomness.

### 4. Use the mailbox in the target flow
Once the address is created:
- Fill the email field in the target site/app.
- Trigger the verification email.
- Record any contextual filters that help later, such as expected sender or subject fragments.

Useful filters to carry forward:
- expected sender domain
- subject keywords
- whether the site usually sends OTP vs magic link

### 5. Poll for the latest relevant message
Normalize inbound mail to a common structure:

```json
{
  "provider": "tempmail_lol",
  "mailbox": "name@example.com",
  "message_id": "12345",
  "subject": "Your verification code",
  "sender": "no-reply@example.com",
  "text_content": "...",
  "html_content": "...",
  "received_at": "2026-05-10T07:20:00Z",
  "raw": {}
}
```

Polling rules:
- Respect the configured timeout.
- Sleep between attempts using `wait_interval`.
- If the provider returns multiple messages, sort by received time and stable ID.
- Prefer exact mailbox/recipient matching where the provider includes recipient metadata.

### 6. Extract the verification artifact
Try these in order:
1. Verification code (OTP / PIN).
2. Magic link / confirmation URL.
3. Fallback: return the normalized message so downstream logic can inspect it.

Recommended result shapes:

```json
{
  "kind": "code",
  "code": "123456",
  "subject": "Your verification code",
  "sender": "no-reply@example.com"
}
```

```json
{
  "kind": "link",
  "url": "https://example.com/verify?...",
  "subject": "Confirm your email",
  "sender": "no-reply@example.com"
}
```

## Standard Operations

### Operation: create mailbox
Inputs:
- provider name, optional
- desired username/prefix, optional
- config

Outputs:
- normalized mailbox session object

### Operation: wait for mail
Inputs:
- mailbox session
- timeout override, optional
- sender/subject filters, optional

Outputs:
- normalized latest relevant mail object

### Operation: wait for code
Inputs:
- mailbox session
- timeout override, optional

Outputs:
- normalized code result or null/timeout

### Operation: wait for magic link
Inputs:
- mailbox session
- timeout override, optional

Outputs:
- normalized link result or null/timeout

## Extraction Rules

Use all available content channels:
- subject
- plain text body
- HTML body
- raw MIME content if necessary

For OTP extraction, common robust heuristics are:
- look for explicit phrases such as `verification code`, `code is`, `验证码`
- inspect HTML snippets where the code is visually highlighted
- fallback to standalone digit groups in the expected length range
- ignore obvious constants and placeholders when you know a provider/system emits them

When processing multiple messages, avoid re-consuming the same mail by tracking a stable message reference based on:
- message ID if present
- otherwise provider + mailbox + timestamp + content hash

## Provider Strategy

Recommended selection strategy:
1. Use an explicitly requested provider if the user names one.
2. Otherwise use a preferred default.
3. If multiple providers are enabled, allow fallback or round-robin.
4. If a provider creates inboxes but repeatedly fails to receive mail, downgrade it and try another one.

Provider-specific details belong in support files or a companion config skill; this orchestration skill should stay provider-agnostic.

See also: `references/provider-patterns.md` and `references/skill-splitting-guidance.md`.

## Structured Return Contract

Whenever possible, return machine-friendly structures rather than prose-only descriptions. Downstream steps should be able to consume:
- mailbox address
- mailbox session state
- latest message metadata
- extracted code or link
- timeout/failure reason

Good example:

```json
{
  "mailbox": {
    "provider": "duckmail",
    "provider_ref": "duckmail#1",
    "address": "abc123@duckmail.sbs",
    "token": "..."
  },
  "result": {
    "kind": "code",
    "code": "654321",
    "subject": "Verify your login",
    "sender": "security@example.com"
  }
}
```

## Common Pitfalls

1. **Confusing skill knowledge with runtime capability.**
   A skill can teach the workflow, but it does not automatically create an API client. Prefer a reusable script/service when possible.

2. **Creating a mailbox without preserving provider session fields.**
   Many providers need a token, mailbox ID, or account ID for later polling. If you throw that away, you cannot fetch mail reliably.

3. **Assuming every site sends a numeric OTP.**
   Many sites send magic links instead. Always support both code extraction and URL extraction.

4. **Reading only plain text or only HTML.**
   Some providers populate one better than the other. Always inspect both.

5. **Polling the inbox without recipient matching.**
   Shared or wildcard inboxes may contain multiple messages. Match recipient fields where available.

6. **Reusing the same message repeatedly.**
   Track seen message references so an earlier email does not get mistaken for the latest verification attempt.

7. **Treating provider failures as site failures.**
   Differentiate: mailbox creation failure, no inbound email, extraction failure, or target site rejection.

8. **Using temp-mail domains on sites that block them.**
   If the site rejects the address before sending mail, switch domains/providers before debugging extraction logic.

9. **Continuing into wait-for-code after a client-side domain rejection.**
   Inline form errors like `该域名邮箱不受支持` mean the target blocked the mailbox before any email was triggered. This is a site-acceptance problem, not a polling or parsing failure.

## Verification Checklist
   Inline form errors like `该域名邮箱不受支持` mean the target blocked the mailbox before any email was triggered. This is a site-acceptance problem, not a polling or parsing failure.

## Verification Checklist

- [ ] At least one provider is enabled and credentials/base URLs are present.
- [ ] Mailbox creation returns a usable address and any required session fields.
- [ ] The target site accepted the address and actually triggered an email.
- [ ] Polling uses timeout + wait interval rather than a tight loop.
- [ ] Latest message is normalized into subject/text/html/timestamp fields.
- [ ] Both OTP extraction and magic-link extraction were considered.
- [ ] Duplicate/previous messages are not being re-consumed.
- [ ] Final result is returned in a structured form usable by later automation.

## One-Shot Recipes

### Register on a site with temp mail
1. Load config and choose provider.
2. Create mailbox.
3. Submit the address to the target site.
4. Wait for the first relevant inbound message.
5. Extract code or link.
6. Complete verification in the browser or API flow.

### Retry with provider fallback
1. Attempt primary provider.
2. If mailbox creation fails, switch provider immediately.
3. If mailbox creation succeeds but no mail arrives within timeout, try another provider/domain.
4. If mail arrives but no code is extracted, inspect HTML + link paths before declaring failure.
