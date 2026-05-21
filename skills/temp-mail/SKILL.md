---
name: temp-mail
description: "Use when you need a single unified temporary-email workflow: configure provider APIs once, create disposable inboxes, wait for verification emails, extract OTP codes or confirmation links, and support provider fallback during site registrations."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [email, temp-mail, otp, verification, registration, provider-routing]
    related_skills: [himalaya, temp-mail-orchestration, hermes-agent-skill-authoring]
---

# Temp-Mail

## Overview

This skill provides one unified entry point for temporary email workflows. It is designed for tasks like signing up for websites, receiving one-time passwords, opening email confirmation links, and swapping between multiple disposable-email providers without changing the rest of the automation.

The intended architecture is simple:
- One skill: `temp-mail`
- One user config file: `~/.hermes/email/temp-mail.json`
- One helper script: `scripts/temp_mail.py`
- Multiple provider definitions behind the scenes

The user configures provider credentials once. After that, the agent can create inboxes, wait for mail, extract verification artifacts, and use those results in browser or API registration flows.

## When to Use

Use this skill when:
- You need a disposable or API-controlled email address.
- A website requires email verification during sign-up or login.
- You need to retrieve either a numeric OTP or a magic confirmation link.
- The user already has temp-mail provider API keys or base URLs.
- You want one skill to route across multiple providers with a common interface.

Do not use this skill for:
- Normal personal mailbox operations over IMAP/SMTP; use `himalaya` instead.
- Long-term mailbox management.
- Cases where the target site requires a real non-disposable mailbox and the user has not provided one.

## Files Included

- `templates/temp-mail.json` — starter config template
- `references/providers.md` — provider schema and field reference
- `references/debugging.md` — troubleshooting guide
- `references/debugging.md` — troubleshooting guide
- `references/provider-notes.md` — concise real-world provider quirks and session-backed notes
- `scripts/temp_mail.py` — unified CLI helper

## Default Config Location

The helper script expects config at:

```text
~/.hermes/email/temp-mail.json
```

Copy the template into place and fill in your real credentials:

```bash
mkdir -p ~/.hermes/email
cp ~/.hermes/skills/email/temp-mail/templates/temp-mail.json ~/.hermes/email/temp-mail.json
```

Then edit the file and replace placeholder keys/domains.

## Unified Workflow

### 1. Load config
Read `~/.hermes/email/temp-mail.json` unless the task explicitly supplies another config path.

### 2. Select a provider
Selection precedence:
1. Explicit provider instance requested by the user
2. Explicit provider type requested by the user
3. `default_provider`
4. Remaining enabled providers, ordered by `selection_strategy`

### 3. Create a mailbox
Use the helper script to create a disposable inbox and return a structured mailbox bundle.

### 4. Persist the mailbox session
If follow-up polling will happen later, save the returned mailbox bundle with `--out /path/to/mailbox.json`.

### 5. Use the mailbox in the target site
Enter the email address into the registration/login form and trigger the verification email.

### 6. Wait for verification mail
Poll the selected provider using the returned mailbox session object.

### 7. Extract the artifact
Try to extract, in order:
1. numeric verification code
2. confirmation / magic link
3. full normalized message for manual inspection

## Script Commands

All commands are run through the helper script:

```bash
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py --config ~/.hermes/email/temp-mail.json <command>
```

### List enabled providers

```bash
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py list-providers
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py list-providers --json
```

### Create a mailbox

```bash
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --provider primary-tempmail --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --provider-type duckmail --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --username myprefix --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --out /tmp/mailbox.json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --provider primary-tempmail --out /tmp/mailbox.json --json
```

### Wait for a message

```bash
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-message --session-file /tmp/mailbox.json --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-message --mailbox /tmp/mailbox.json --sender-contains github --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-message --session-file /tmp/mailbox.json --subject-contains verify --out /tmp/message.json
```

### Wait for a verification code

```bash
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-code --session-file /tmp/mailbox.json --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-code --mailbox /tmp/mailbox.json --code-lengths 6 --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-code --session-file /tmp/mailbox.json --sender-contains github --out /tmp/code.json
```

### Wait for a confirmation link

```bash
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-link --session-file /tmp/mailbox.json --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-link --mailbox /tmp/mailbox.json --allowed-hosts github.com,auth.github.com --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-link --session-file /tmp/mailbox.json --allowed-hosts example.com,auth.example.com --out /tmp/link.json
```

## Convenience Options

- `--out /path/to/file.json`
  - Available on `create`, `wait-message`, `wait-code`, `wait-link`
  - Writes the structured JSON result to a file for later reuse
  - Also prints JSON to stdout when `--out` is used

- `--session-file /path/to/mailbox.json`
  - Available on `wait-message`, `wait-code`, `wait-link`
  - Explicit alias for “read mailbox/session JSON from this file”
  - More readable than overloading `--mailbox` with a file path

- `--mailbox '<json>'`
  - Still supported when the mailbox bundle is passed inline as raw JSON

## Return Shapes

### Mailbox bundle

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

### Normalized message

```json
{
  "provider": "tempmail_lol",
  "provider_instance": "primary-tempmail",
  "provider_ref": "tempmail_lol#1",
  "address": "abc123@example.com",
  "message_id": "12345",
  "subject": "Your verification code",
  "sender": "no-reply@example.com",
  "text_content": "Your code is 123456",
  "html_content": "<p>Your code is <b>123456</b></p>",
  "received_at": "2026-05-10T07:20:00+00:00",
  "raw": {}
}
```

### Code result

```json
{
  "kind": "code",
  "provider": "tempmail_lol",
  "provider_instance": "primary-tempmail",
  "address": "abc123@example.com",
  "code": "123456",
  "subject": "Your verification code",
  "sender": "no-reply@example.com",
  "received_at": "2026-05-10T07:20:00+00:00",
  "message": {}
}
```

### Link result

```json
{
  "kind": "link",
  "provider": "tempmail_lol",
  "provider_instance": "primary-tempmail",
  "address": "abc123@example.com",
  "link": "https://example.com/verify?token=***",
  "subject": "Confirm your email",
  "sender": "no-reply@example.com",
  "received_at": "2026-05-10T07:20:00+00:00",
  "message": {}
}
```

## Provider Dispatch Rules

The helper supports these strategy names:
- `priority`
- `fallback`
- `round_robin`

Current behavior:
- mailbox creation auto-fallbacks across enabled providers in configured order
- waiting operations use the provider already encoded in the mailbox session

This means fallback is strongest during creation. If a mailbox is created successfully but later fails to receive mail, you may need to create a new mailbox on another provider and retry the target site flow.

## Recommended Agent Behavior

When using this skill in a real task:
1. Confirm the config file exists.
2. Create a mailbox with `--json` or `--out /tmp/mailbox.json`.
3. If follow-up polling is required, prefer `--out /tmp/mailbox.json` at create time.
4. Use the email address in the website flow.
5. If a provider is account-backed rather than API-key-backed, confirm credential requirements before promising anonymous temp-mail behavior.
6. Prefer provider-specific notes in `references/provider-notes.md` when a provider has quota, entitlement, or account-model caveats.
7. Prefer `wait-code` first when the provider/message pattern is known to send OTPs.
8. Prefer `wait-link` when the site uses magic links.
9. If the expected artifact is unclear, use `wait-message --json` to inspect the latest mail.
10. Return structured results and only then summarize them in prose.
11. When the target site presents a slider/puzzle CAPTCHA before sending a code, clear that challenge first; otherwise `wait-code` timeouts are not meaningful diagnostics.
12. If the registration form rejects the address immediately with a message indicating unsupported/disallowed domain, stop the inbox polling path and switch to another provider/domain or a non-disposable mailbox. Treat this as target-site domain blocking, not a temp-mail delivery failure.

## One-Shot Recipes

### Register on a website with OTP email

1. Create mailbox:
   ```bash
   python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --out /tmp/mailbox.json --json
   ```
2. Use the returned `address` in the site registration form.
3. Wait for code:
   ```bash
   python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-code --session-file /tmp/mailbox.json --json
   ```
4. Copy the returned `code` into the site.

### Register on a website with confirmation link

1. Create mailbox.
2. Trigger the email.
3. Wait for link:
   ```bash
   python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-link --session-file /tmp/mailbox.json --json
   ```
4. Open the returned `link` in browser automation.

### Prefer a specific provider

```bash
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --provider backup-duckmail --json
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py create --provider-type duckmail --json
```

### Inspect before extraction

```bash
python ~/.hermes/skills/email/temp-mail/scripts/temp_mail.py wait-message --session-file /tmp/mailbox.json --out /tmp/message.json --json
```

Then inspect `/tmp/message.json` if extraction rules need refinement.

## Common Pitfalls

1. Saving only the email address and losing the mailbox session bundle.
   - Waiting commands need the full mailbox/session JSON, not just `user@example.com`.

2. Using `--mailbox /path/file.json` when teammates expect explicit file semantics.
   - Prefer `--session-file /path/file.json` for clarity.

3. Assuming wait-time fallback switches providers automatically.
   - It does not. Create a new mailbox on another provider if the current inbox never receives the mail.

4. Forgetting to replace placeholder API keys in `~/.hermes/email/temp-mail.json`.
   - The template is safe-by-default and will not work until real credentials are added.

5. Enabling `moemail` before local dependency setup is complete.
   - The current provider implementation requires `curl_cffi`; if it is missing, creation fails immediately with `curl_cffi is required for moemail` before any API-level diagnosis.

6. Assuming all providers need explicit domain configuration.
   - `yyds_mail` can succeed without `domain` or `subdomain`, using provider-managed default domains.

7. Assuming every provider is anonymous temp-mail with just an API key.
   - `aliasvault` is account-backed and needs username/password; it also may fail if the account uses 2FA.

8. Forgetting provider-level service constraints.
   - GPTMail shared keys may fail when daily shared quota is exhausted; MoEmail may reject API use due to missing OpenAPI entitlement or quota.

## Verification Checklist

- [ ] `~/.hermes/email/temp-mail.json` exists
- [ ] At least one provider has `"enable": true`
- [ ] `list-providers --json` returns enabled providers
- [ ] `create --out /tmp/mailbox.json --json` succeeds
- [ ] `/tmp/mailbox.json` contains a full mailbox/session object
- [ ] `wait-message`, `wait-code`, or `wait-link` can read the saved session file
- [ ] Placeholder credentials have been replaced before real provider testing
