"""Email service (Resend)."""
from __future__ import annotations

import asyncio
import logging
import os

import resend

logger = logging.getLogger("storm.email")


def _api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "")


def _sender() -> str:
    return os.environ.get("SENDER_EMAIL", "")


def _public_url() -> str:
    return os.environ.get("PUBLIC_APP_URL", "").rstrip("/")


def _render_verification_html(name: str, verify_url: str) -> str:
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:24px;background:#F8FAFC;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0F172A">
  <table role="presentation" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #E2E8F0">
    <tr><td style="padding:32px 32px 16px">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:0.3em;color:#94A3B8;text-transform:uppercase;margin-bottom:8px">Storm Monitoring</div>
      <h1 style="margin:0;font-size:28px;font-weight:900;letter-spacing:-0.02em">Confirme ton inscription.</h1>
    </td></tr>
    <tr><td style="padding:0 32px 24px">
      <p style="margin:16px 0 0;line-height:1.6;color:#334155">Bonjour {name},</p>
      <p style="margin:8px 0 0;line-height:1.6;color:#334155">
        Tu viens de créer un compte sur Storm Monitoring. Pour activer ton compte
        et accéder à l'application, clique sur le bouton ci-dessous :
      </p>
    </td></tr>
    <tr><td style="padding:0 32px 32px;text-align:center">
      <a href="{verify_url}" style="display:inline-block;padding:14px 28px;background:#0F172A;color:#fff;text-decoration:none;font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;font-weight:600">Activer mon compte →</a>
      <p style="margin:24px 0 0;font-size:11px;color:#94A3B8;line-height:1.6">
        Ou copie-colle ce lien dans ton navigateur :<br>
        <a href="{verify_url}" style="color:#475569;word-break:break-all">{verify_url}</a>
      </p>
    </td></tr>
    <tr><td style="padding:20px 32px;background:#F1F5F9;border-top:1px solid #E2E8F0">
      <p style="margin:0;font-size:12px;color:#64748B;line-height:1.5">
        Si tu n'es pas à l'origine de cette inscription, ignore ce mail —
        ton adresse ne sera pas activée tant que ce lien n'est pas cliqué.
      </p>
    </td></tr>
    <tr><td style="padding:16px 32px;text-align:center">
      <p style="margin:0;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:0.2em;color:#94A3B8;text-transform:uppercase">
        Build &amp; Idea by Quentin Dumont
      </p>
    </td></tr>
  </table>
</body></html>"""


async def send_verification_email(to_email: str, name: str, token: str) -> bool:
    """Send verification email. Returns True on success, False otherwise."""
    api_key = _api_key()
    if not api_key:
        logger.error("RESEND_API_KEY not set — verification mail NOT sent to %s", to_email)
        logger.error("Manual verify URL: %s/verify-email?token=%s", _public_url(), token)
        return False
    resend.api_key = api_key
    verify_url = f"{_public_url()}/verify-email?token={token}"
    params = {
        "from": _sender(),
        "to": [to_email],
        "subject": "Confirme ton inscription · Storm Monitoring",
        "html": _render_verification_html(name, verify_url),
    }
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Verification email sent to %s (resend id=%s)", to_email, result.get("id"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("Resend send failed for %s: %s", to_email, exc)
        return False
