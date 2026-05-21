# Skill Splitting Guidance for Temp-Mail Workflows

This session established an important scope rule: the user does **not** want project-specific email skills. They want reusable, provider-agnostic skills that work across arbitrary site-registration tasks once provider credentials are already configured.

## What to build

Prefer class-level skills such as:
- `temp-mail-orchestration`
- `temp-mail-provider-config`
- `temp-mail-code-extraction`
- `temp-mail-debugging`

## What not to build first

Avoid narrow skills named after:
- one repository
- one website
- one provider only
- one registration target

Examples of bad first cuts:
- `chatgpt2api-mail-provider`
- `register-xxx-with-duckmail`
- `tempmail-lol-only-registration`

## Reason

The reusable value is the workflow:
- create temp mailbox
- receive verification mail
- extract code or link
- complete verification on an arbitrary site

Provider specifics should be support material or companion skills, not the top-level identity of the library.
