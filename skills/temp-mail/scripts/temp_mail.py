#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import re
import string
import sqlite3
import tempfile
import uuid
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email import message_from_string, policy
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import requests

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover
    curl_requests = None


DEFAULT_CONFIG_PATH = Path.home() / ".hermes" / "email" / "temp-mail.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_mailbox_name() -> str:
    return (
        f"{''.join(random.choices(string.ascii_lowercase, k=5))}"
        f"{''.join(random.choices(string.digits, k=random.randint(1, 3)))}"
        f"{''.join(random.choices(string.ascii_lowercase, k=random.randint(1, 3)))}"
    )


def _random_subdomain_label() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(4, 10)))


def _parse_received_at(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _extract_content(data: dict[str, Any]) -> tuple[str, str]:
    text_content = str(data.get("text_content") or data.get("text") or data.get("body") or data.get("content") or "")
    html_content = str(data.get("html_content") or data.get("html") or data.get("html_body") or data.get("body_html") or "")
    if text_content or html_content:
        return text_content, html_content
    raw = data.get("raw")
    if not isinstance(raw, str) or not raw.strip():
        return "", ""
    try:
        parsed = message_from_string(raw, policy=policy.default)
    except Exception:
        return raw, ""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in parsed.walk() if parsed.is_multipart() else [parsed]:
        if part.get_content_maintype() == "multipart":
            continue
        try:
            payload = part.get_content()
        except Exception:
            payload = ""
        if not payload:
            continue
        if part.get_content_type() == "text/html":
            html_parts.append(str(payload))
        else:
            plain_parts.append(str(payload))
    return "\n".join(plain_parts).strip(), "\n".join(html_parts).strip()


def _extract_text_candidates(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("address", "email", "name", "value"):
            if value.get(key):
                out.extend(_extract_text_candidates(value.get(key)))
        return out
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_extract_text_candidates(item))
        return out
    return []


def _message_matches_email(data: dict[str, Any], email: str) -> bool:
    target = str(email or "").strip().lower()
    candidates: list[str] = []
    for key in ("to", "mailTo", "receiver", "receivers", "address", "email", "envelope_to"):
        if key in data:
            candidates.extend(_extract_text_candidates(data.get(key)))
    return not target or not candidates or any(target in str(item).strip().lower() for item in candidates if str(item).strip())


def _message_tracking_ref(message: dict[str, Any]) -> str:
    provider = str(message.get("provider") or "").strip()
    mailbox = str(message.get("mailbox") or "").strip()
    message_id = str(message.get("message_id") or "").strip()
    if message_id:
        return f"id:{provider}:{mailbox}:{message_id}"
    received_at = message.get("received_at")
    received_value = received_at.isoformat() if isinstance(received_at, datetime) else str(received_at or "")
    content = "\n".join(str(message.get(key) or "") for key in ("subject", "sender", "text_content", "html_content"))
    digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
    return f"content:{provider}:{mailbox}:{received_value}:{digest}"


def _extract_code(message: dict[str, Any], code_lengths: list[int] | None = None) -> str | None:
    lengths = sorted({int(v) for v in (code_lengths or [4, 5, 6, 7, 8]) if int(v) > 0})
    content = f"{message.get('subject', '')}\n{message.get('text_content', '')}\n{message.get('html_content', '')}".strip()
    if not content:
        return None
    for length in sorted(lengths, reverse=True):
        match = re.search(rf"(?:Verification code|code is|代码为|验证码|PIN|OTP)[:\s]*(\d{{{length}}})", content, re.I)
        if match and match.group(1) != "177010":
            return match.group(1)
    for length in sorted(lengths, reverse=True):
        match = re.search(rf"background-color:\s*#F3F3F3[^>]*>[\s\S]*?(\d{{{length}}})[\s\S]*?</", content, re.I)
        if match and match.group(1) != "177010":
            return match.group(1)
    for length in sorted(lengths, reverse=True):
        pattern = rf">\s*(\d{{{length}}})\s*<|(?<![#&])\b(\d{{{length}}})\b"
        for code in re.findall(pattern, content):
            value = code[0] or code[1]
            if value and value != "177010":
                return value
    return None


def _extract_link(message: dict[str, Any], allowed_hosts: list[str] | None = None) -> str | None:
    content = f"{message.get('subject', '')}\n{message.get('text_content', '')}\n{message.get('html_content', '')}".strip()
    if not content:
        return None
    candidates = re.findall(r"https?://[^\s\"'<>\)]+", content)
    if not candidates:
        return None
    normalized_hosts = [h.strip().lower() for h in (allowed_hosts or []) if h.strip()]
    if normalized_hosts:
        for url in candidates:
            try:
                host = (urlparse(url).hostname or "").lower()
            except Exception:
                host = ""
            if any(host == allowed or host.endswith(f".{allowed}") for allowed in normalized_hosts):
                return url
    return candidates[0]


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _write_json_file(path_value: str, data: Any) -> None:
    path = Path(path_value).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


@dataclass
class AppConfig:
    path: Path
    data: dict[str, Any]

    @property
    def default_provider(self) -> str:
        return str(self.data.get("default_provider") or "").strip()

    @property
    def request_timeout(self) -> float:
        return float(self.data.get("request_timeout") or 30)

    @property
    def wait_timeout(self) -> float:
        return float(self.data.get("wait_timeout") or 120)

    @property
    def wait_interval(self) -> float:
        return float(self.data.get("wait_interval") or 2)

    @property
    def selection_strategy(self) -> str:
        strategy = str(self.data.get("selection_strategy") or "fallback").strip().lower()
        return strategy if strategy in {"priority", "fallback", "round_robin"} else "fallback"

    @property
    def providers(self) -> list[dict[str, Any]]:
        items = self.data.get("providers") or []
        return [item for item in items if isinstance(item, dict)]


class TempMailError(RuntimeError):
    pass


class TempMailApp:
    def __init__(self, config: AppConfig):
        self.config = config

    @classmethod
    def load(cls, config_path: str | None = None) -> "TempMailApp":
        path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH
        if not path.exists():
            raise TempMailError(f"config not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise TempMailError(f"failed to parse config: {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise TempMailError("config root must be an object")
        return cls(AppConfig(path=path, data=data))

    def enabled_providers(self) -> list[dict[str, Any]]:
        items = []
        for index, item in enumerate(self.config.providers, start=1):
            if not item.get("enable"):
                continue
            merged = dict(item)
            merged.setdefault("name", f"{merged.get('type', 'provider')}-{index}")
            merged["provider_ref"] = f"{merged.get('type', 'unknown')}#{index}"
            items.append(merged)
        if not items:
            raise TempMailError("no enabled providers in config")
        return items

    def select_providers(self, provider_name: str = "", provider_type: str = "") -> list[dict[str, Any]]:
        items = self.enabled_providers()
        if provider_name:
            exact = [item for item in items if str(item.get("name") or "") == provider_name]
            if not exact:
                raise TempMailError(f"provider name not found or disabled: {provider_name}")
            return exact
        if provider_type:
            exact = [item for item in items if str(item.get("type") or "") == provider_type]
            if not exact:
                raise TempMailError(f"provider type not found or disabled: {provider_type}")
            return exact

        default_provider = self.config.default_provider
        if default_provider:
            preferred = [
                item for item in items
                if str(item.get("name") or "") == default_provider or str(item.get("type") or "") == default_provider
            ]
            others = [item for item in items if item not in preferred]
            if preferred:
                items = preferred + others

        strategy = self.config.selection_strategy
        if strategy in {"priority", "fallback"}:
            items.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
            return items
        if strategy == "round_robin":
            items.sort(key=lambda item: (int(item.get("priority") or 0), str(item.get("name") or "")), reverse=True)
            return items
        return items

    def create_mailbox(self, provider_name: str = "", provider_type: str = "", username: str = "") -> dict[str, Any]:
        errors: list[str] = []
        for entry in self.select_providers(provider_name, provider_type):
            provider = self._provider_from_entry(entry)
            try:
                mailbox = provider.create_mailbox(username or None)
                return {
                    "provider": mailbox.get("provider") or entry.get("type"),
                    "provider_instance": entry.get("name"),
                    "provider_ref": mailbox.get("provider_ref") or entry.get("provider_ref"),
                    "address": mailbox.get("address"),
                    "session": mailbox,
                    "created_at": _utc_now_iso(),
                }
            except Exception as exc:
                errors.append(f"{entry.get('name')}: {exc}")
            finally:
                provider.close()
        raise TempMailError("failed to create mailbox via configured providers: " + " | ".join(errors))

    def wait_for_message(
        self,
        mailbox_bundle: dict[str, Any],
        timeout: float | None = None,
        sender_contains: str = "",
        subject_contains: str = "",
    ) -> dict[str, Any]:
        session = dict(mailbox_bundle.get("session") or mailbox_bundle)
        provider = self._provider_for_session(session)
        deadline = time.monotonic() + float(timeout if timeout is not None else self.config.wait_timeout)
        try:
            while time.monotonic() < deadline:
                message = provider.fetch_latest_message(session)
                if message and self._matches_filters(message, sender_contains, subject_contains):
                    return self._normalize_message(message, session, mailbox_bundle)
                time.sleep(max(0.2, self.config.wait_interval))
        finally:
            provider.close()
        raise TempMailError("timed out waiting for matching email")

    def wait_for_code(
        self,
        mailbox_bundle: dict[str, Any],
        timeout: float | None = None,
        sender_contains: str = "",
        subject_contains: str = "",
        code_lengths: list[int] | None = None,
    ) -> dict[str, Any]:
        session = dict(mailbox_bundle.get("session") or mailbox_bundle)
        provider = self._provider_for_session(session)
        deadline = time.monotonic() + float(timeout if timeout is not None else self.config.wait_timeout)
        seen_value = session.setdefault("_seen_code_message_refs", [])
        if not isinstance(seen_value, list):
            seen_value = []
            session["_seen_code_message_refs"] = seen_value
        seen_refs = {str(item) for item in seen_value}
        try:
            while time.monotonic() < deadline:
                message = provider.fetch_latest_message(session)
                if not message or not self._matches_filters(message, sender_contains, subject_contains):
                    time.sleep(max(0.2, self.config.wait_interval))
                    continue
                ref = _message_tracking_ref(message)
                if ref in seen_refs:
                    time.sleep(max(0.2, self.config.wait_interval))
                    continue
                code = _extract_code(message, code_lengths=code_lengths)
                if code:
                    seen_value.append(ref)
                    normalized = self._normalize_message(message, session, mailbox_bundle)
                    return {
                        "kind": "code",
                        "provider": normalized.get("provider"),
                        "provider_instance": normalized.get("provider_instance"),
                        "address": normalized.get("address"),
                        "code": code,
                        "subject": normalized.get("subject"),
                        "sender": normalized.get("sender"),
                        "received_at": normalized.get("received_at"),
                        "message": normalized,
                        "session": session,
                    }
                time.sleep(max(0.2, self.config.wait_interval))
        finally:
            provider.close()
        raise TempMailError("timed out waiting for verification code")

    def wait_for_link(
        self,
        mailbox_bundle: dict[str, Any],
        timeout: float | None = None,
        sender_contains: str = "",
        subject_contains: str = "",
        allowed_hosts: list[str] | None = None,
    ) -> dict[str, Any]:
        session = dict(mailbox_bundle.get("session") or mailbox_bundle)
        provider = self._provider_for_session(session)
        deadline = time.monotonic() + float(timeout if timeout is not None else self.config.wait_timeout)
        seen_value = session.setdefault("_seen_link_message_refs", [])
        if not isinstance(seen_value, list):
            seen_value = []
            session["_seen_link_message_refs"] = seen_value
        seen_refs = {str(item) for item in seen_value}
        try:
            while time.monotonic() < deadline:
                message = provider.fetch_latest_message(session)
                if not message or not self._matches_filters(message, sender_contains, subject_contains):
                    time.sleep(max(0.2, self.config.wait_interval))
                    continue
                ref = _message_tracking_ref(message)
                if ref in seen_refs:
                    time.sleep(max(0.2, self.config.wait_interval))
                    continue
                link = _extract_link(message, allowed_hosts=allowed_hosts)
                if link:
                    seen_value.append(ref)
                    normalized = self._normalize_message(message, session, mailbox_bundle)
                    return {
                        "kind": "link",
                        "provider": normalized.get("provider"),
                        "provider_instance": normalized.get("provider_instance"),
                        "address": normalized.get("address"),
                        "link": link,
                        "subject": normalized.get("subject"),
                        "sender": normalized.get("sender"),
                        "received_at": normalized.get("received_at"),
                        "message": normalized,
                        "session": session,
                    }
                time.sleep(max(0.2, self.config.wait_interval))
        finally:
            provider.close()
        raise TempMailError("timed out waiting for verification link")

    def _matches_filters(self, message: dict[str, Any], sender_contains: str = "", subject_contains: str = "") -> bool:
        sender = str(message.get("sender") or "").lower()
        subject = str(message.get("subject") or "").lower()
        if sender_contains and sender_contains.lower() not in sender:
            return False
        if subject_contains and subject_contains.lower() not in subject:
            return False
        return True

    def _normalize_message(self, message: dict[str, Any], session: dict[str, Any], mailbox_bundle: dict[str, Any]) -> dict[str, Any]:
        received = message.get("received_at")
        received_value = received.isoformat() if isinstance(received, datetime) else str(received or "")
        return {
            "provider": message.get("provider") or session.get("provider"),
            "provider_instance": mailbox_bundle.get("provider_instance"),
            "provider_ref": session.get("provider_ref"),
            "address": session.get("address"),
            "message_id": message.get("message_id"),
            "subject": str(message.get("subject") or ""),
            "sender": str(message.get("sender") or ""),
            "text_content": str(message.get("text_content") or ""),
            "html_content": str(message.get("html_content") or ""),
            "received_at": received_value,
            "raw": message.get("raw"),
        }

    def _provider_for_session(self, session: dict[str, Any]) -> "BaseMailProvider":
        provider_ref = str(session.get("provider_ref") or "")
        provider_name = str(session.get("provider") or "")
        for entry in self.enabled_providers():
            if provider_ref and entry.get("provider_ref") == provider_ref:
                return self._provider_from_entry(entry)
        for entry in self.enabled_providers():
            if provider_name and entry.get("type") == provider_name:
                return self._provider_from_entry(entry)
        raise TempMailError(f"no enabled provider matches mailbox session: provider={provider_name}, ref={provider_ref}")

    def _provider_from_entry(self, entry: dict[str, Any]) -> "BaseMailProvider":
        type_name = str(entry.get("type") or "")
        conf = {
            "request_timeout": self.config.request_timeout,
            "wait_timeout": self.config.wait_timeout,
            "wait_interval": self.config.wait_interval,
            "user_agent": "Mozilla/5.0",
        }
        if type_name == "cloudflare_temp_email":
            return CloudflareTempMailProvider(entry, conf)
        if type_name == "tempmail_lol":
            return TempMailLolProvider(entry, conf)
        if type_name == "duckmail":
            return DuckMailProvider(entry, conf)
        if type_name == "gptmail":
            return GptMailProvider(entry, conf)
        if type_name == "aliasvault":
            return AliasVaultProvider(entry, conf)
        if type_name == "moemail":
            return MoEmailProvider(entry, conf)
        if type_name == "inbucket":
            return InbucketMailProvider(entry, conf)
        if type_name == "yyds_mail":
            return YydsMailProvider(entry, conf)
        raise TempMailError(f"unsupported provider type: {type_name}")


class BaseMailProvider:
    name = "unknown"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        self.entry = entry
        self.conf = conf
        self.provider_ref = str(entry.get("provider_ref") or "")

    def close(self) -> None:
        pass


class CloudflareTempMailProvider(BaseMailProvider):
    name = "cloudflare_temp_email"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        super().__init__(entry, conf)
        if curl_requests is None:
            raise TempMailError("curl_cffi is required for cloudflare_temp_email")
        self.api_base = str(entry["api_base"]).rstrip("/")
        self.admin_password = str(entry["admin_password"]).strip()
        self.domain = entry.get("domain") or []
        self.session = curl_requests.Session(impersonate="chrome")

    def _request(self, method: str, path: str, headers: dict | None = None, params: dict | None = None, payload: dict | None = None, expected: tuple[int, ...] = (200,)):
        response = self.session.request(
            method.upper(),
            f"{self.api_base}{path}",
            headers={"Content-Type": "application/json", "User-Agent": self.conf["user_agent"], **(headers or {})},
            params=params,
            json=payload,
            timeout=self.conf["request_timeout"],
            verify=False,
        )
        if response.status_code not in expected:
            raise TempMailError(f"CloudflareTempMail request failed: {method} {path}, HTTP {response.status_code}, body={response.text[:300]}")
        return {} if response.status_code == 204 else response.json()

    def create_mailbox(self, username: str | None = None) -> dict[str, Any]:
        domain = _next_domain(self.domain)
        data = self._request(
            "POST",
            "/admin/new_address",
            headers={"x-admin-auth": self.admin_password},
            payload={"enablePrefix": True, "name": username or _random_mailbox_name(), "domain": domain},
        )
        address = str(data.get("address") or "").strip()
        token = str(data.get("jwt") or "").strip()
        if not address or not token:
            raise TempMailError("CloudflareTempMail missing address or jwt")
        return {"provider": self.name, "provider_ref": self.provider_ref, "address": address, "token": token}

    def fetch_latest_message(self, mailbox: dict[str, Any]) -> dict[str, Any] | None:
        data = self._request("GET", "/api/mails", headers={"Authorization": f"Bearer {mailbox['token']}"}, params={"limit": 10, "offset": 0})
        raw = list(data.get("results") or []) if isinstance(data, dict) else data if isinstance(data, list) else []
        messages = [item for item in raw if isinstance(item, dict) and _message_matches_email(item, str(mailbox.get("address") or ""))]
        if not messages:
            return None
        item = messages[0]
        text_content, html_content = _extract_content(item)
        sender = item.get("from") or item.get("sender") or ""
        if isinstance(sender, dict):
            sender = sender.get("address") or sender.get("email") or sender.get("name") or ""
        return {
            "provider": self.name,
            "mailbox": mailbox["address"],
            "message_id": str(item.get("id") or item.get("_id") or ""),
            "subject": str(item.get("subject") or ""),
            "sender": str(sender),
            "text_content": text_content,
            "html_content": html_content,
            "received_at": _parse_received_at(item.get("createdAt") or item.get("created_at") or item.get("receivedAt") or item.get("date") or item.get("timestamp")),
            "raw": item,
        }

    def close(self) -> None:
        self.session.close()


class TempMailLolProvider(BaseMailProvider):
    name = "tempmail_lol"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        super().__init__(entry, conf)
        self.api_key = str(entry.get("api_key") or "").strip()
        self.domain = [str(item).strip() for item in (entry.get("domain") or []) if str(item).strip()]
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": conf["user_agent"], "Accept": "application/json", "Content-Type": "application/json"})
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    @staticmethod
    def _resolve_domain(domain: str) -> tuple[str, bool]:
        text = str(domain or "").strip().lower()
        if text.startswith("*.") and len(text) > 2:
            return f"{_random_subdomain_label()}.{text[2:]}", True
        return text, False

    def _request(self, method: str, path: str, params: dict | None = None, payload: dict | None = None, expected: tuple[int, ...] = (200,)):
        response = self.session.request(method.upper(), f"https://api.tempmail.lol/v2{path}", params=params, json=payload, timeout=self.conf["request_timeout"], verify=False)
        if response.status_code not in expected:
            raise TempMailError(f"TempMail.lol request failed: {method} {path}, HTTP {response.status_code}, body={response.text[:300]}")
        data = response.json()
        if not isinstance(data, dict):
            raise TempMailError("TempMail.lol returned non-object payload")
        return data

    def create_mailbox(self, username: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.domain:
            domain, force_random_prefix = self._resolve_domain(random.choice(self.domain))
            payload["domain"] = domain
            if force_random_prefix:
                payload["prefix"] = _random_mailbox_name()
        if username and "prefix" not in payload:
            payload["prefix"] = username
        data = self._request("POST", "/inbox/create", payload=payload, expected=(200, 201))
        address = str(data.get("address") or "").strip()
        token = str(data.get("token") or "").strip()
        if not address or not token:
            raise TempMailError("TempMail.lol missing address or token")
        return {"provider": self.name, "provider_ref": self.provider_ref, "address": address, "token": token}

    def fetch_latest_message(self, mailbox: dict[str, Any]) -> dict[str, Any] | None:
        data = self._request("GET", "/inbox", params={"token": mailbox["token"]})
        items = data.get("emails") or data.get("messages") or []
        messages = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
        if not messages:
            return None
        item = max(
            messages,
            key=lambda value: (
                (_parse_received_at(value.get("created_at") or value.get("createdAt") or value.get("date") or value.get("received_at") or value.get("timestamp")) or datetime.fromtimestamp(0, tz=timezone.utc)).timestamp(),
                str(value.get("id") or value.get("token") or ""),
            ),
        )
        text_content, html_content = _extract_content(item)
        return {
            "provider": self.name,
            "mailbox": mailbox["address"],
            "message_id": str(item.get("id") or item.get("token") or ""),
            "subject": str(item.get("subject") or ""),
            "sender": str(item.get("from") or item.get("from_address") or ""),
            "text_content": text_content,
            "html_content": html_content,
            "received_at": _parse_received_at(item.get("created_at") or item.get("createdAt") or item.get("date") or item.get("received_at") or item.get("timestamp")),
            "raw": item,
        }

    def close(self) -> None:
        self.session.close()


class DuckMailProvider(BaseMailProvider):
    name = "duckmail"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        super().__init__(entry, conf)
        self.api_key = str(entry["api_key"]).strip()
        self.default_domain = str(entry.get("default_domain") or "duckmail.sbs").strip() or "duckmail.sbs"
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": conf["user_agent"], "Accept": "application/json", "Content-Type": "application/json"})

    def _request(self, method: str, path: str, token: str = "", use_api_key: bool = False, params: dict | None = None, payload: dict | None = None, expected: tuple[int, ...] = (200, 201, 204)):
        headers = {"Authorization": f"Bearer {self.api_key if use_api_key else token}"} if use_api_key or token else {}
        response = self.session.request(method.upper(), f"https://api.duckmail.sbs{path}", headers=headers, params=params, json=payload, timeout=self.conf["request_timeout"], verify=False)
        if response.status_code not in expected:
            raise TempMailError(f"DuckMail request failed: {method} {path}, HTTP {response.status_code}, body={response.text[:300]}")
        return {} if response.status_code == 204 else response.json()

    @staticmethod
    def _items(data: Any):
        return data if isinstance(data, list) else data.get("hydra:member") or data.get("member") or data.get("data") or []

    def create_mailbox(self, username: str | None = None) -> dict[str, Any]:
        password = "".join(random.choices(string.ascii_letters + string.digits, k=12))
        address = f"{username or _random_mailbox_name()}@{self.default_domain}"
        payload = {"address": address, "password": password}
        account = self._request("POST", "/accounts", use_api_key=True, payload=payload)
        token_data = self._request("POST", "/token", use_api_key=True, payload=payload)
        return {
            "provider": self.name,
            "provider_ref": self.provider_ref,
            "address": address,
            "token": str(token_data.get("token") or ""),
            "password": password,
            "account_id": str(account.get("id") or ""),
        }

    def fetch_latest_message(self, mailbox: dict[str, Any]) -> dict[str, Any] | None:
        data = self._request("GET", "/messages", token=str(mailbox.get("token") or ""), params={"page": 1})
        items = self._items(data)
        if not items:
            return None
        item = items[0]
        message_id = str(item.get("id") or item.get("@id") or "").replace("/messages/", "")
        if message_id:
            item = self._request("GET", f"/messages/{message_id}", token=str(mailbox.get("token") or ""))
        sender = item.get("from") or ""
        if isinstance(sender, dict):
            sender = sender.get("address") or sender.get("name") or ""
        html_content = item.get("html") or ""
        if isinstance(html_content, list):
            html_content = "".join(str(value) for value in html_content)
        return {
            "provider": self.name,
            "mailbox": mailbox["address"],
            "message_id": message_id,
            "subject": str(item.get("subject") or ""),
            "sender": str(sender),
            "text_content": str(item.get("text") or item.get("text_content") or ""),
            "html_content": str(html_content),
            "received_at": _parse_received_at(item.get("createdAt") or item.get("created_at") or item.get("receivedAt") or item.get("date")),
            "raw": item,
        }

    def close(self) -> None:
        self.session.close()


class GptMailProvider(BaseMailProvider):
    name = "gptmail"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        super().__init__(entry, conf)
        self.api_key = str(entry["api_key"]).strip()
        self.default_domain = str(entry.get("default_domain") or "").strip()
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": conf["user_agent"], "Accept": "application/json", "Content-Type": "application/json", "X-API-Key": self.api_key})

    def _request(self, method: str, path: str, params: dict | None = None, payload: dict | None = None):
        response = self.session.request(method.upper(), f"https://mail.chatgpt.org.uk{path}", params=dict(params or {}), json=payload, timeout=self.conf["request_timeout"], verify=False)
        if response.status_code != 200:
            raise TempMailError(f"GPTMail request failed: {method} {path}, HTTP {response.status_code}, body={response.text[:300]}")
        data = response.json()
        return data["data"] if isinstance(data, dict) and "data" in data else data

    def create_mailbox(self, username: str | None = None) -> dict[str, Any]:
        payload = {key: value for key, value in {"prefix": username, "domain": self.default_domain}.items() if value}
        data = self._request("POST" if payload else "GET", "/api/generate-email", payload=payload or None)
        return {"provider": self.name, "provider_ref": self.provider_ref, "address": str(data["email"])}

    def fetch_latest_message(self, mailbox: dict[str, Any]) -> dict[str, Any] | None:
        data = self._request("GET", "/api/emails", params={"email": mailbox["address"]})
        emails = data if isinstance(data, list) else data.get("emails") or []
        if not emails:
            return None
        item = max(emails, key=lambda value: (float(value.get("timestamp") or 0), str(value.get("id") or "")))
        if item.get("id"):
            item = self._request("GET", f"/api/email/{item['id']}")
        return {
            "provider": self.name,
            "mailbox": mailbox["address"],
            "message_id": str(item.get("id") or ""),
            "subject": str(item.get("subject") or ""),
            "sender": str(item.get("from_address") or ""),
            "text_content": str(item.get("content") or ""),
            "html_content": str(item.get("html_content") or ""),
            "received_at": _parse_received_at(item.get("timestamp") or item.get("created_at")),
            "raw": item,
        }

    def close(self) -> None:
        self.session.close()


class AliasVaultProvider(BaseMailProvider):
    name = "aliasvault"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        super().__init__(entry, conf)
        self.base_url = str(entry.get("base_url") or "https://app.aliasvault.net/api").rstrip("/")
        self.username = str(entry.get("username") or "").strip()
        self.password = str(entry.get("password") or "").strip()
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": conf["user_agent"], "Accept": "application/json", "Content-Type": "application/json"})

    def _build_url(self, endpoint: str) -> str:
        return self.base_url + "/v1/" + endpoint

    def _read_json(self, response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except Exception as exc:
            raise TempMailError(f"AliasVault returned non-JSON response: HTTP {response.status_code}") from exc
        if response.ok:
            return data
        message = data.get("title") or data.get("message") or response.text
        raise TempMailError(message or f"AliasVault HTTP {response.status_code}")

    def _derive_password_material(self, password: str, salt: str, encryption_type: str, encryption_settings: str) -> tuple[str, str]:
        if encryption_type != "Argon2Id":
            raise TempMailError(f"AliasVault unsupported encryption type: {encryption_type}")
        try:
            from argon2.low_level import Type, hash_secret_raw
        except Exception as exc:
            raise TempMailError("argon2-cffi is required for aliasvault") from exc
        settings = json.loads(encryption_settings)
        key = hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt.encode("utf-8"),
            time_cost=settings["Iterations"],
            memory_cost=settings["MemorySize"],
            parallelism=settings["DegreeOfParallelism"],
            hash_len=32,
            type=Type.ID,
        )
        return key.hex().upper(), base64.b64encode(key).decode("ascii")

    def _login(self) -> dict[str, Any]:
        if not self.username or not self.password:
            raise TempMailError("AliasVault requires username and password")
        login_init = self.session.post(self._build_url("Auth/login"), json={"username": self.username.lower()}, timeout=self.conf["request_timeout"], verify=False)
        login_response = self._read_json(login_init)
        password_hash_hex, password_key_base64 = self._derive_password_material(
            password=self.password,
            salt=login_response["salt"],
            encryption_type=login_response["encryptionType"],
            encryption_settings=login_response["encryptionSettings"],
        )
        try:
            from srptools import SRPClientSession, SRPContext, constants
        except Exception as exc:
            raise TempMailError("srptools is required for aliasvault") from exc
        srp_identity = (login_response.get("srpIdentity") or self.username.lower()).strip().lower()
        context = SRPContext(srp_identity, password_hash_hex, prime=constants.PRIME_2048, generator=constants.PRIME_2048_GEN, hash_func=hashlib.sha256)
        client_session = SRPClientSession(context)
        _, proof, _ = client_session.process(login_response["serverEphemeral"], login_response["salt"])
        if isinstance(proof, bytes):
            proof = proof.decode("ascii")
        validate = self.session.post(
            self._build_url("Auth/validate"),
            json={
                "username": self.username.lower(),
                "rememberMe": True,
                "clientPublicEphemeral": client_session.public.upper(),
                "clientSessionProof": str(proof).upper(),
            },
            timeout=self.conf["request_timeout"],
            verify=False,
        )
        data = self._read_json(validate)
        if data.get("requiresTwoFactor"):
            raise TempMailError("AliasVault account requires two-factor authentication, which is not supported")
        token_data = data.get("token") or {}
        token = str(token_data.get("token") or "").strip()
        if not token:
            raise TempMailError("AliasVault login succeeded but token is missing")
        return {
            "access_token": token,
            "refresh_token": str(token_data.get("refreshToken") or "").strip(),
            "password_key_base64": password_key_base64,
            "username": self.username.lower(),
        }

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _decrypt_vault_blob(self, encrypted_blob: str, password_key_base64: str) -> str:
        raw = base64.b64decode(encrypted_blob)
        iv, ciphertext = raw[:12], raw[12:]
        plaintext = AESGCM(base64.b64decode(password_key_base64)).decrypt(iv, ciphertext, None)
        return plaintext.decode("utf-8")

    def _encrypt_vault_blob(self, decrypted_base64: str, password_key_base64: str) -> str:
        iv = os.urandom(12)
        ciphertext = AESGCM(base64.b64decode(password_key_base64)).encrypt(iv, decrypted_base64.encode("utf-8"), None)
        return base64.b64encode(iv + ciphertext).decode("ascii")

    def _open_sqlite(self, db_base64: str):
        raw = base64.b64decode(db_base64)
        fd, db_path = tempfile.mkstemp(prefix="aliasvault-", suffix=".db")
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        connection = sqlite3.connect(db_path)
        return connection, db_path

    def _fetch_vault(self, token: str, password_key_base64: str) -> dict[str, Any]:
        response = self.session.get(self._build_url("Vault"), headers=self._auth_headers(token), timeout=self.conf["request_timeout"], verify=False)
        payload = self._read_json(response)
        payload["_vault_base64"] = self._decrypt_vault_blob(payload["vault"]["blob"], password_key_base64)
        return payload

    def _save_vault(self, payload: dict[str, Any], token: str, password_key_base64: str) -> None:
        vault = payload["vault"]
        decrypted_base64 = payload.get("_vault_base64")
        if not decrypted_base64:
            raise TempMailError("AliasVault missing decrypted vault payload")
        encrypted_blob = self._encrypt_vault_blob(decrypted_base64, password_key_base64)
        vault["blob"] = encrypted_blob
        now = _utc_now_iso()
        upload_payload = {
            "username": vault["username"],
            "blob": encrypted_blob,
            "version": vault["version"],
            "currentRevisionNumber": vault["currentRevisionNumber"],
            "credentialsCount": self._count_active_items(decrypted_base64),
            "createdAt": now,
            "updatedAt": now,
            "encryptionPublicKey": vault.get("encryptionPublicKey", ""),
            "emailAddressList": vault.get("emailAddressList") or [],
            "privateEmailDomainList": vault.get("privateEmailDomainList") or [],
            "hiddenPrivateEmailDomainList": vault.get("hiddenPrivateEmailDomainList") or [],
            "publicEmailDomainList": vault.get("publicEmailDomainList") or [],
        }
        response = self.session.post(self._build_url("Vault"), headers=self._auth_headers(token), json=upload_payload, timeout=self.conf["request_timeout"], verify=False)
        data = self._read_json(response)
        if data.get("status") != 0:
            raise TempMailError(f"AliasVault upload failed with status {data.get('status')}")
        vault["currentRevisionNumber"] = data["newRevisionNumber"]

    def _count_active_items(self, decrypted_base64: str) -> int:
        connection, db_path = self._open_sqlite(decrypted_base64)
        try:
            row = connection.execute("SELECT COUNT(*) FROM Items WHERE IsDeleted = 0 AND DeletedAt IS NULL").fetchone()
            return int(row[0]) if row else 0
        finally:
            connection.close()
            os.remove(db_path)

    def _create_alias_entry(self, payload: dict[str, Any], email: str) -> None:
        vault = payload["vault"]
        connection, db_path = self._open_sqlite(payload["_vault_base64"])
        try:
            now = _utc_now_iso()
            item_id = str(uuid.uuid4())
            field_id = str(uuid.uuid4())
            connection.execute("INSERT INTO Items (Id, Name, ItemType, LogoId, FolderId, CreatedAt, UpdatedAt, IsDeleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (item_id, email, "Login", None, None, now, now, 0))
            connection.execute("INSERT INTO FieldValues (Id, ItemId, FieldDefinitionId, FieldKey, Value, Weight, CreatedAt, UpdatedAt, IsDeleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (field_id, item_id, None, "login.email", email, 0, now, now, 0))
            connection.commit()
            with open(db_path, "rb") as handle:
                payload["_vault_base64"] = base64.b64encode(handle.read()).decode("ascii")
        finally:
            connection.close()
            os.remove(db_path)
        addresses = list(vault.get("emailAddressList") or [])
        if email not in addresses:
            addresses.append(email)
        vault["emailAddressList"] = addresses

    def _list_encryption_keys(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        connection, db_path = self._open_sqlite(payload["_vault_base64"])
        try:
            rows = connection.execute("SELECT PublicKey, PrivateKey FROM EncryptionKeys WHERE IsDeleted = 0").fetchall()
            return [{"public_key": row[0], "private_key": row[1]} for row in rows]
        finally:
            connection.close()
            os.remove(db_path)

    def _load_private_key(self, jwk_json: str) -> rsa.RSAPrivateKey:
        jwk = json.loads(jwk_json)
        def decode_int(value: str) -> int:
            padded = value + "=" * (-len(value) % 4)
            return int.from_bytes(base64.urlsafe_b64decode(padded), "big")
        numbers = rsa.RSAPrivateNumbers(
            p=decode_int(jwk["p"]),
            q=decode_int(jwk["q"]),
            d=decode_int(jwk["d"]),
            dmp1=decode_int(jwk["dp"]),
            dmq1=decode_int(jwk["dq"]),
            iqmp=decode_int(jwk["qi"]),
            public_numbers=rsa.RSAPublicNumbers(e=decode_int(jwk["e"]), n=decode_int(jwk["n"])),
        )
        return numbers.private_key()

    def _decrypt_symmetric_key(self, encrypted_key_b64: str, public_key: str, keys: list[dict[str, str]]) -> bytes:
        key_record = next((item for item in keys if item["public_key"] == public_key), None)
        if key_record is None:
            raise TempMailError("AliasVault matching encryption key not found in vault")
        private_key = self._load_private_key(key_record["private_key"])
        return private_key.decrypt(base64.b64decode(encrypted_key_b64), padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))

    def _decrypt_field(self, ciphertext_b64: str, symmetric_key: bytes) -> str:
        raw = base64.b64decode(ciphertext_b64)
        iv, ciphertext = raw[:12], raw[12:]
        plaintext = AESGCM(symmetric_key).decrypt(iv, ciphertext, None)
        return plaintext.decode("utf-8")

    def create_mailbox(self, username: str | None = None) -> dict[str, Any]:
        auth = self._login()
        payload = self._fetch_vault(auth["access_token"], auth["password_key_base64"])
        vault = payload["vault"]
        domains = list(vault.get("privateEmailDomainList") or []) + list(vault.get("publicEmailDomainList") or [])
        domain = domains[0] if domains else ""
        if not domain:
            raise TempMailError("AliasVault has no available email domains")
        email = f"{username or _random_mailbox_name()}@{domain}"
        self._create_alias_entry(payload, email)
        self._save_vault(payload, auth["access_token"], auth["password_key_base64"])
        return {
            "provider": self.name,
            "provider_ref": self.provider_ref,
            "address": email,
            "access_token": auth["access_token"],
            "password_key_base64": auth["password_key_base64"],
        }

    def fetch_latest_message(self, mailbox: dict[str, Any]) -> dict[str, Any] | None:
        token = str(mailbox.get("access_token") or "").strip()
        password_key_base64 = str(mailbox.get("password_key_base64") or "").strip()
        if not token or not password_key_base64:
            raise TempMailError("AliasVault mailbox missing access_token or password_key_base64")
        address = str(mailbox.get("address") or "").strip()
        response = self.session.get(self._build_url(f"EmailBox/{address}"), headers=self._auth_headers(token), timeout=self.conf["request_timeout"], verify=False)
        data = self._read_json(response)
        mails = data.get("mails") or []
        messages = [item for item in mails if isinstance(item, dict)]
        if not messages:
            return None
        item = messages[0]
        message_id = int(item.get("id") or 0)
        if not message_id:
            return None
        detail_response = self.session.get(self._build_url(f"Email/{message_id}"), headers=self._auth_headers(token), timeout=self.conf["request_timeout"], verify=False)
        detail = self._read_json(detail_response)
        payload = self._fetch_vault(token, password_key_base64)
        keys = self._list_encryption_keys(payload)
        symmetric_key = self._decrypt_symmetric_key(detail["encryptedSymmetricKey"], detail["encryptionKey"], keys)
        sender_local = self._decrypt_field(detail["fromLocal"], symmetric_key) if detail.get("fromLocal") else ""
        sender_domain = self._decrypt_field(detail["fromDomain"], symmetric_key) if detail.get("fromDomain") else ""
        sender_display = self._decrypt_field(detail["fromDisplay"], symmetric_key) if detail.get("fromDisplay") else ""
        subject = self._decrypt_field(detail["subject"], symmetric_key) if detail.get("subject") else ""
        html_content = self._decrypt_field(detail["messageHtml"], symmetric_key) if detail.get("messageHtml") else ""
        text_content = self._decrypt_field(detail["messagePlain"], symmetric_key) if detail.get("messagePlain") else ""
        sender = sender_display or "@".join(part for part in [sender_local, sender_domain] if part)
        return {
            "provider": self.name,
            "mailbox": address,
            "message_id": str(message_id),
            "subject": subject,
            "sender": sender,
            "text_content": text_content,
            "html_content": html_content,
            "received_at": _parse_received_at(detail.get("createdAt") or detail.get("created_at") or detail.get("receivedAt") or detail.get("date") or detail.get("timestamp")),
            "raw": detail,
        }

    def close(self) -> None:
        self.session.close()


class MoEmailProvider(BaseMailProvider):
    name = "moemail"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        super().__init__(entry, conf)
        if curl_requests is None:
            raise TempMailError("curl_cffi is required for moemail")
        self.api_base = str(entry["api_base"]).rstrip("/")
        self.api_key = str(entry["api_key"]).strip()
        raw_domains = entry.get("domain") or []
        self.domain = [str(item).strip() for item in raw_domains] if isinstance(raw_domains, list) else [str(raw_domains).strip()] if str(raw_domains).strip() else []
        self.expiry_time = int(entry.get("expiry_time") or 0)
        self.session = curl_requests.Session(impersonate="chrome")

    def _request(self, method: str, path: str, params: dict | None = None, payload: dict | None = None, expected: tuple[int, ...] = (200,)):
        response = self.session.request(
            method.upper(),
            f"{self.api_base}{path}",
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json", "User-Agent": self.conf["user_agent"]},
            params=params,
            json=payload,
            timeout=self.conf["request_timeout"],
            verify=False,
        )
        if response.status_code not in expected:
            raise TempMailError(f"MoEmail request failed: {method} {path}, HTTP {response.status_code}, body={response.text[:300]}")
        data = response.json()
        if not isinstance(data, dict):
            raise TempMailError("MoEmail returned non-object payload")
        return data

    def create_mailbox(self, username: str | None = None) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/api/emails/generate",
            payload={"name": username or _random_mailbox_name(), "expiryTime": self.expiry_time, "domain": _next_domain(self.domain)},
            expected=(200, 201),
        )
        address = str(data.get("email") or "").strip()
        email_id = str(data.get("id") or data.get("email_id") or "").strip()
        if not address or not email_id:
            raise TempMailError("MoEmail missing email or id")
        return {"provider": self.name, "provider_ref": self.provider_ref, "address": address, "email_id": email_id}

    def fetch_latest_message(self, mailbox: dict[str, Any]) -> dict[str, Any] | None:
        email_id = str(mailbox.get("email_id") or "").strip()
        if not email_id:
            raise TempMailError("MoEmail mailbox missing email_id")
        data = self._request("GET", f"/api/emails/{email_id}")
        items = data.get("messages") or []
        messages = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
        if not messages:
            return None
        _, item = max(
            enumerate(messages),
            key=lambda pair: (
                (_parse_received_at(pair[1].get("createdAt") or pair[1].get("created_at") or pair[1].get("receivedAt") or pair[1].get("date") or pair[1].get("timestamp")) or datetime.fromtimestamp(0, tz=timezone.utc)).timestamp(),
                pair[0],
            ),
        )
        message_id = str(item.get("id") or item.get("message_id") or item.get("_id") or "").strip()
        detail = self._request("GET", f"/api/emails/{email_id}/{message_id}") if message_id else {"message": item}
        message = detail.get("message") if isinstance(detail.get("message"), dict) else detail
        text_content, html_content = _extract_content(message)
        sender = message.get("from") or message.get("sender") or ""
        if isinstance(sender, dict):
            sender = sender.get("address") or sender.get("email") or sender.get("name") or ""
        return {
            "provider": self.name,
            "mailbox": mailbox["address"],
            "message_id": message_id,
            "subject": str(message.get("subject") or item.get("subject") or ""),
            "sender": str(sender),
            "text_content": text_content,
            "html_content": html_content,
            "received_at": _parse_received_at(message.get("createdAt") or message.get("created_at") or message.get("receivedAt") or message.get("date") or message.get("timestamp") or item.get("createdAt") or item.get("created_at") or item.get("receivedAt") or item.get("date") or item.get("timestamp")),
            "raw": detail,
        }

    def close(self) -> None:
        self.session.close()


class InbucketMailProvider(BaseMailProvider):
    name = "inbucket"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        super().__init__(entry, conf)
        self.api_base = str(entry["api_base"]).rstrip("/")
        raw_domains = entry.get("domain") or []
        self.domain = [str(item).strip() for item in raw_domains] if isinstance(raw_domains, list) else [str(raw_domains).strip()] if str(raw_domains).strip() else []
        self.random_subdomain = bool(entry.get("random_subdomain", True))
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": conf["user_agent"], "Accept": "application/json"})

    def _request(self, method: str, path: str, expected: tuple[int, ...] = (200,)):
        response = self.session.request(method.upper(), f"{self.api_base}{path}", timeout=self.conf["request_timeout"], verify=False)
        if response.status_code not in expected:
            raise TempMailError(f"Inbucket request failed: {method} {path}, HTTP {response.status_code}, body={response.text[:300]}")
        if response.status_code == 204:
            return {}
        content_type = str(response.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            return response.json()
        return response.text

    def create_mailbox(self, username: str | None = None) -> dict[str, Any]:
        if not self.domain:
            raise TempMailError("Inbucket requires at least one domain")
        local_part = username or _random_mailbox_name()
        base_domain = random.choice(self.domain)
        domain = f"{_random_subdomain_label()}.{base_domain}" if self.random_subdomain else base_domain
        address = f"{local_part}@{domain}"
        return {
            "provider": self.name,
            "provider_ref": self.provider_ref,
            "address": address,
            "base_domain": base_domain,
            "mailbox_name": local_part,
        }

    def fetch_latest_message(self, mailbox: dict[str, Any]) -> dict[str, Any] | None:
        mailbox_name = str(mailbox.get("mailbox_name") or str(mailbox.get("address") or "").partition("@")[0]).strip()
        if not mailbox_name:
            raise TempMailError("Inbucket mailbox missing mailbox_name")
        data = self._request("GET", f"/api/v1/mailbox/{mailbox_name}")
        items = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        if not items:
            return None
        items.sort(
            key=lambda value: (
                (_parse_received_at(value.get("date")) or datetime.fromtimestamp(0, tz=timezone.utc)).timestamp(),
                str(value.get("id") or ""),
            ),
            reverse=True,
        )
        address = str(mailbox.get("address") or "").strip()
        for item in items:
            message_id = str(item.get("id") or "").strip()
            if not message_id:
                continue
            detail = self._request("GET", f"/api/v1/mailbox/{mailbox_name}/{message_id}")
            if not isinstance(detail, dict):
                continue
            header = detail.get("header") if isinstance(detail.get("header"), dict) else {}
            body = detail.get("body") if isinstance(detail.get("body"), dict) else {}
            normalized = {
                "provider": self.name,
                "mailbox": mailbox_name,
                "message_id": message_id,
                "subject": str(detail.get("subject") or item.get("subject") or ""),
                "sender": str(detail.get("from") or item.get("from") or ""),
                "text_content": str(body.get("text") or ""),
                "html_content": str(body.get("html") or ""),
                "received_at": _parse_received_at(detail.get("date") or item.get("date")),
                "to": header.get("To") if isinstance(header, dict) else None,
                "raw": detail,
            }
            if _message_matches_email(normalized, address):
                return normalized
        return None

    def close(self) -> None:
        self.session.close()


class YydsMailProvider(BaseMailProvider):
    name = "yyds_mail"

    def __init__(self, entry: dict[str, Any], conf: dict[str, Any]):
        super().__init__(entry, conf)
        self.api_base = str(entry.get("api_base") or "https://maliapi.215.im/v1").rstrip("/")
        self.api_key = str(entry["api_key"]).strip()
        self.domain = [str(item).strip() for item in (entry.get("domain") or []) if str(item).strip()]
        self.subdomain = str(entry.get("subdomain") or "").strip()
        self.wildcard = bool(entry.get("wildcard"))
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": conf["user_agent"], "Accept": "application/json", "Content-Type": "application/json"})

    def _request(self, method: str, path: str, token: str = "", params: dict | None = None, payload: dict | None = None, expected: tuple[int, ...] = (200, 201, 204)):
        headers = {"Authorization": f"Bearer {token}"} if token else {"X-API-Key": self.api_key}
        response = self.session.request(method.upper(), f"{self.api_base}{path}", headers=headers, params=params, json=payload, timeout=self.conf["request_timeout"], verify=False)
        if response.status_code not in expected:
            raise TempMailError(f"YYDSMail request failed: {method} {path}, HTTP {response.status_code}, body={response.text[:300]}")
        if response.status_code == 204:
            return {}
        data = response.json()
        if isinstance(data, dict) and data.get("success") is False:
            raise TempMailError(f"YYDSMail request failed: {data.get('errorCode') or data.get('error')}")
        return data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)) else data

    @staticmethod
    def _items(data: Any):
        return data if isinstance(data, list) else data.get("items") or data.get("messages") or data.get("data") or []

    def create_mailbox(self, username: str | None = None) -> dict[str, Any]:
        payload = {"localPart": username or _random_mailbox_name()}
        if self.domain:
            payload["domain"] = random.choice(self.domain)
        if self.subdomain:
            payload["subdomain"] = self.subdomain
        data = self._request("POST", "/accounts/wildcard" if self.wildcard else "/accounts", payload=payload)
        address = str(data.get("address") or data.get("email") or "").strip()
        token = str(data.get("token") or data.get("temp_token") or data.get("tempToken") or data.get("access_token") or "").strip()
        if not address or not token:
            raise TempMailError("YYDSMail missing address or token")
        return {"provider": self.name, "provider_ref": self.provider_ref, "address": address, "token": token, "account_id": str(data.get("id") or "")}

    def fetch_latest_message(self, mailbox: dict[str, Any]) -> dict[str, Any] | None:
        data = self._request("GET", "/messages", token=str(mailbox.get("token") or ""), params={"address": mailbox["address"]})
        messages = [item for item in self._items(data) if isinstance(item, dict)]
        if not messages:
            return None
        item = max(
            messages,
            key=lambda value: (
                (_parse_received_at(value.get("createdAt") or value.get("created_at") or value.get("receivedAt") or value.get("date") or value.get("timestamp")) or datetime.fromtimestamp(0, tz=timezone.utc)).timestamp(),
                str(value.get("id") or ""),
            ),
        )
        message_id = str(item.get("id") or item.get("message_id") or "").strip()
        if message_id:
            item = self._request("GET", f"/messages/{message_id}", token=str(mailbox.get("token") or ""), params={"address": mailbox["address"]})
        text_content, html_content = _extract_content(item)
        sender = item.get("from") or item.get("sender") or ""
        if isinstance(sender, dict):
            sender = sender.get("address") or sender.get("email") or sender.get("name") or ""
        return {
            "provider": self.name,
            "mailbox": mailbox["address"],
            "message_id": message_id,
            "subject": str(item.get("subject") or ""),
            "sender": str(sender),
            "text_content": text_content,
            "html_content": html_content,
            "received_at": _parse_received_at(item.get("createdAt") or item.get("created_at") or item.get("receivedAt") or item.get("date") or item.get("timestamp")),
            "raw": item,
        }

    def close(self) -> None:
        self.session.close()


def _next_domain(domains: list[str]) -> str:
    cleaned = [str(item).strip() for item in domains if str(item).strip()]
    if not cleaned:
        raise TempMailError("provider domain list is empty")
    return random.choice(cleaned)


def _load_json_arg(raw: str) -> Any:
    if raw == "-":
        return json.load(sys.stdin)
    path = Path(raw).expanduser()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(raw)


def _load_mailbox_arg(mailbox: str = "", session_file: str = "") -> dict[str, Any]:
    if session_file:
        data = _load_json_arg(session_file)
    elif mailbox:
        data = _load_json_arg(mailbox)
    else:
        raise TempMailError("either --mailbox or --session-file is required")
    if not isinstance(data, dict):
        raise TempMailError("mailbox input must be a JSON object")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified temporary email helper for Hermes skills")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to temp-mail.json")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-providers", help="List enabled providers")
    p_list.add_argument("--json", action="store_true")

    p_create = sub.add_parser("create", help="Create a mailbox")
    p_create.add_argument("--provider", default="", help="Provider instance name")
    p_create.add_argument("--provider-type", default="", help="Provider type")
    p_create.add_argument("--username", default="", help="Desired mailbox prefix")
    p_create.add_argument("--json", action="store_true")
    p_create.add_argument("--out", default="", help="Write JSON result to this file")

    p_message = sub.add_parser("wait-message", help="Wait for a message")
    p_message.add_argument("--mailbox", help="Mailbox JSON or path to JSON file")
    p_message.add_argument("--session-file", required=True, help="Path to saved mailbox/session JSON file")
    p_message.add_argument("--timeout", type=float, default=None)
    p_message.add_argument("--sender-contains", default="")
    p_message.add_argument("--subject-contains", default="")
    p_message.add_argument("--json", action="store_true")
    p_message.add_argument("--out", default="", help="Write JSON result to this file")

    p_code = sub.add_parser("wait-code", help="Wait for a verification code")
    p_code.add_argument("--mailbox", help="Mailbox JSON or path to JSON file")
    p_code.add_argument("--session-file", required=True, help="Path to saved mailbox/session JSON file")
    p_code.add_argument("--timeout", type=float, default=None)
    p_code.add_argument("--sender-contains", default="")
    p_code.add_argument("--subject-contains", default="")
    p_code.add_argument("--code-lengths", default="4,5,6,7,8")
    p_code.add_argument("--json", action="store_true")
    p_code.add_argument("--out", default="", help="Write JSON result to this file")

    p_link = sub.add_parser("wait-link", help="Wait for a verification link")
    p_link.add_argument("--mailbox", help="Mailbox JSON or path to JSON file")
    p_link.add_argument("--session-file", required=True, help="Path to saved mailbox/session JSON file")
    p_link.add_argument("--timeout", type=float, default=None)
    p_link.add_argument("--sender-contains", default="")
    p_link.add_argument("--subject-contains", default="")
    p_link.add_argument("--allowed-hosts", default="")
    p_link.add_argument("--json", action="store_true")
    p_link.add_argument("--out", default="", help="Write JSON result to this file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        app = TempMailApp.load(args.config)
        if args.command == "list-providers":
            providers = app.enabled_providers()
            if args.json:
                _print_json(providers)
            else:
                for item in providers:
                    print(f"{item['name']}\t{item.get('type')}\tenabled={bool(item.get('enable'))}\tpriority={int(item.get('priority') or 0)}")
            return 0

        if args.command == "create":
            result = app.create_mailbox(provider_name=args.provider, provider_type=args.provider_type, username=args.username)
            if args.out:
                _write_json_file(args.out, result)
            _print_json(result) if (args.json or args.out) else print(result.get("address"))
            return 0

        mailbox = _load_mailbox_arg(getattr(args, "mailbox", ""), getattr(args, "session_file", ""))

        if args.command == "wait-message":
            result = app.wait_for_message(
                mailbox,
                timeout=args.timeout,
                sender_contains=args.sender_contains,
                subject_contains=args.subject_contains,
            )
            if args.out:
                _write_json_file(args.out, result)
            _print_json(result) if (args.json or args.out) else print(result.get("subject") or "")
            return 0

        if args.command == "wait-code":
            code_lengths = [int(part) for part in str(args.code_lengths).split(",") if part.strip()]
            result = app.wait_for_code(
                mailbox,
                timeout=args.timeout,
                sender_contains=args.sender_contains,
                subject_contains=args.subject_contains,
                code_lengths=code_lengths,
            )
            if args.out:
                _write_json_file(args.out, result)
            _print_json(result) if (args.json or args.out) else print(result.get("code") or "")
            return 0

        if args.command == "wait-link":
            allowed_hosts = [part.strip() for part in str(args.allowed_hosts).split(",") if part.strip()]
            result = app.wait_for_link(
                mailbox,
                timeout=args.timeout,
                sender_contains=args.sender_contains,
                subject_contains=args.subject_contains,
                allowed_hosts=allowed_hosts,
            )
            if args.out:
                _write_json_file(args.out, result)
            _print_json(result) if (args.json or args.out) else print(result.get("link") or "")
            return 0

        raise TempMailError(f"unknown command: {args.command}")
    except TempMailError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
