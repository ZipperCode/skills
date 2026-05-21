# Provider Patterns for Temporary Email APIs

This note captures common provider behaviors discovered while analyzing a multi-provider temp-mail implementation. Use it as a design reference when building or adapting a provider client.

## Common mailbox-creation outputs

Most providers need a normalized mailbox session that includes:
- `provider`
- `provider_ref`
- `address`

Often-required provider-specific fields:
- `token` — bearer-like token used to read messages
- `email_id` — mailbox identifier used for later detail fetches
- `account_id` — provider-side account record
- `password` — sometimes needed to exchange for a token
- `mailbox_name` — useful for mailbox-path APIs such as Inbucket

## Common creation patterns

### Direct inbox-create API
Examples of behavior patterns:
- `POST /inbox/create`
- response includes `address` + `token`

### Account-then-token API
Examples of behavior patterns:
- `POST /accounts`
- `POST /token`
- mailbox session needs both the generated address and the issued token

### Generate-email API
Examples of behavior patterns:
- `GET /api/generate-email`
- `POST /api/generate-email` with optional prefix/domain overrides

### Self-hosted mailbox pattern
Examples of behavior patterns:
- address is synthesized locally from `local_part@domain`
- provider API is only used for later polling, not for mailbox creation itself

## Common polling patterns

### Token-based inbox fetch
- request uses a token query param or `Authorization` header
- fetch returns a list of emails/messages
- client chooses the newest item by timestamp + stable ID

### List-then-detail pattern
- first call returns summary items only
- second call fetches message detail by `message_id`
- detail may contain HTML/text bodies missing from the summary

### Mailbox-path polling
- API path includes mailbox name from the address local-part
- message detail path may be `/mailbox/{name}/{message_id}`
- recipient filtering is especially important for wildcard or shared-domain setups

## Normalization hints

Normalize each message to:
- `subject`
- `sender`
- `text_content`
- `html_content`
- `received_at`
- `message_id`
- `raw`

Useful raw provider fields that often map well:
- sender: `from`, `from_address`, `sender`
- recipient: `to`, `mailTo`, `receiver`, `receivers`, `address`, `envelope_to`
- time: `created_at`, `createdAt`, `receivedAt`, `date`, `timestamp`
- text: `text`, `body`, `content`, `text_content`
- html: `html`, `html_body`, `body_html`, `html_content`

## OTP extraction hints

A robust extractor should:
- inspect subject + text + HTML together
- prefer explicit patterns like `verification code`, `code is`, `验证码`
- then fallback to standalone numeric groups
- ignore provider/system placeholders if they are known to recur

## Design lesson

For long-term maintainability, keep provider-specific quirks in code or support files, but keep the orchestration skill focused on the invariant workflow: create mailbox -> trigger email -> poll -> normalize -> extract code/link.
