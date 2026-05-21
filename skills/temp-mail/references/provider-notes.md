# Provider Notes

## Working providers in this environment

These notes capture real-world behavior observed while wiring this skill into live provider accounts.

### duckmail
- Works with `default_domain: duckmail.sbs`.
- Mailbox creation was verified successfully with a live API key.

### yyds_mail
- Works with a live API key even when no explicit `domain` or `subdomain` is configured.
- Provider-managed default domains are sufficient for mailbox creation.

### gptmail
- A shared key can work for mailbox creation.
- Shared quota is roughly 20,000 calls/day and appears to reset around 08:00.
- If requests suddenly fail, shared quota exhaustion is a plausible first diagnosis.

### moemail
- Public API base should be `https://moemail.app` rather than `https://api.moemail.app`.
- Provider implementation requires `curl_cffi` locally.
- Even with a valid key, API use can fail with HTTP 403 if the account lacks OpenAPI access or quota.

### aliasvault
- This is an account-backed provider, not anonymous temp-mail.
- Current implementation requires Python packages: `argon2-cffi`, `srptools`, and `cryptography`.
- Current implementation was validated against the default service at `https://app.aliasvault.net/api`.
- Alias creation succeeded with a real account and produced addresses on `aliasvault.net`.
- Session bundles contain sensitive material such as `access_token` and `password_key_base64`; treat saved mailbox JSON as secret.
- Current implementation does not support 2FA-protected accounts.

## Website registration caveats

### Sites with slider / puzzle verification
- Some websites will block email-code delivery behind a visual challenge such as a slider CAPTCHA.
- In those cases, complete the anti-bot challenge first, then trigger `wait-code`.
- If the browser automation cannot reliably solve the challenge, pause and ask the user to complete it manually, then resume the mailbox polling flow.

### Email not arriving after clicking send code
- Confirm the site actually accepted the send-code action.
- If a visual challenge appeared, do not treat `wait-code` timeout as a provider failure until the challenge is cleared.
