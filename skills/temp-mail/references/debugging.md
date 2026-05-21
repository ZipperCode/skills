# Temp-Mail Debugging Guide

## 1. Config not found

Symptom:
- script returns `config not found`

Fix:
- create `~/.hermes/email/temp-mail.json`
- or pass `--config /path/to/temp-mail.json`

## 2. No enabled providers

Symptom:
- `no enabled providers in config`

Fix:
- set at least one provider object with `"enable": true`
- verify JSON syntax and provider placement under `providers`

## 3. Mailbox creation fails for the primary provider

Likely causes:
- invalid `api_key`
- wrong `api_base`
- missing required provider fields
- provider API changed

Fix:
- test with `python temp_mail.py list-providers`
- then run `python temp_mail.py create --provider <name> --json`
- if the mailbox will be reused, test `python temp_mail.py create --provider <name> --out /tmp/mailbox.json --json`
- verify credentials and endpoints
- if using `fallback`, ensure a backup provider is enabled

## 4. Mailbox creates successfully but no email arrives

Likely causes:
- target site never sent the message
- provider inbox polling is too short
- disposable domain blocked by the site
- wrong recipient mailbox matched

Fix:
- extend `wait_timeout`
- use `wait-message` first to inspect the raw latest email
- prefer `--session-file /tmp/mailbox.json` when reusing a saved mailbox bundle
- filter on sender or subject only if you are sure
- try a different provider/domain

## 5. Email arrives but code extraction fails

Likely causes:
- email contains a magic link instead of a numeric code
- code length is not in the default 4-8 range
- email uses unusual formatting

Fix:
- run `wait-message --json` and inspect `text_content` / `html_content`
- try `wait-link`
- override `--code-lengths`, for example `--code-lengths 6`

## 6. Link extraction returns the wrong URL

Likely causes:
- email contains tracking links before the real confirmation link

Fix:
- use `--allowed-hosts example.com,auth.example.com`
- inspect the normalized message JSON and tighten the filter

## 7. Inbucket receives nothing

Likely causes:
- `api_base` is wrong
- the generated mailbox domain does not route into Inbucket
- subdomain behavior mismatches the local deployment

Fix:
- verify Inbucket web/API is reachable
- start with `random_subdomain: false`
- confirm your local MX/mail routing is set up for the chosen domain

## 8. curl_cffi provider fails at startup

Symptom:
- `curl_cffi is required for ...`

Fix:
- install `curl_cffi`
- or disable providers that need it (`cloudflare_temp_email`, `moemail`)

## 9. Fallback never reaches the backup provider

Likely causes:
- the provider does not fail during creation, only during message wait
- the current helper only auto-fallbacks on create, not during inbox waiting

Fix:
- manually create with a different provider instance
- if needed, extend the script later to support fallback during wait operations

## 10. Disposable domains blocked by the target site

Symptom:
- registration form rejects the address or verification mail is never sent

Fix:
- switch to a different provider/domain pool
- use a provider with custom or less-common domains
- if the site blocks temp mail by policy, this workflow may not succeed

## 11. Saved session file works inconsistently

Likely causes:
- only the address was saved, not the full mailbox bundle
- a command used a stale or overwritten JSON file

Fix:
- always save the full `create` result with `--out /tmp/mailbox.json`
- reuse that file with `--session-file /tmp/mailbox.json`
- inspect the JSON and confirm it still contains provider/session fields such as `provider`, `provider_ref`, `address`, and any provider token


## 13. Code wait times out after clicking "send code"

Likely causes:
- the site blocked delivery behind a slider CAPTCHA or puzzle verification
- the send-code action never actually completed on the website

Fix:
- inspect the page for text like `请完成安全验证` or slider/puzzle prompts
- complete the anti-bot challenge before blaming the email provider
- only run `wait-code` after the site confirms the code was actually sent
- if automation cannot solve the challenge reliably, ask the user to complete it manually and then resume polling
