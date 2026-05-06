"""SMTP delivery for proposal PDFs (attachments)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from limye_api.config import Settings


class ProposalEmailError(Exception):
    """Raised when the proposal email could not be sent."""


def smtp_configured(settings: Settings) -> bool:
    host = (getattr(settings, "SMTP_HOST", None) or "").strip()
    from_addr = (getattr(settings, "SMTP_FROM_EMAIL", None) or "").strip()
    return bool(host and from_addr)


def _email_body_text(has_estimate: bool) -> str:
    if has_estimate:
        estimate_line = (
            "2. Solar proposal — illustrative investment summary, savings outlook, incentives, "
            "and cost breakdown\r\n"
        )
    else:
        estimate_line = (
            "2. Solar proposal — design overview (request an in-app estimate to include "
            "savings and incentive detail in future saves)\r\n"
        )
    return (
        "Hello,\r\n\r\n"
        "Thank you for exploring solar with LIMYÈ.\r\n\r\n"
        "Attached you will find two PDF documents:\r\n\r\n"
        "1. Solar roof design — your layout and key system specifications\r\n"
        f"{estimate_line}\r\n"
        "If you have questions or would like next steps toward installation, reply to this email "
        "or continue in the LIMYÈ app.\r\n\r\n"
        "Warm regards,\r\n"
        "The LIMYÈ Team\r\n"
    )


def send_proposal_email_sync(
    settings: Settings,
    to_email: str,
    design_pdf: bytes,
    estimate_pdf: bytes,
    *,
    has_full_estimate: bool,
) -> None:
    """Send multipart email with two PDF attachments. Raises ProposalEmailError on failure."""
    if not smtp_configured(settings):
        raise ProposalEmailError("SMTP is not configured (SMTP_HOST / SMTP_FROM_EMAIL).")

    from_email = settings.SMTP_FROM_EMAIL.strip()
    from_name = (getattr(settings, "SMTP_FROM_NAME", None) or "LIMYÈ").strip()
    host = settings.SMTP_HOST.strip()
    port = int(getattr(settings, "SMTP_PORT", 587) or 587)
    user = (getattr(settings, "SMTP_USER", None) or "").strip()
    password = getattr(settings, "SMTP_PASSWORD", None) or ""
    use_tls = bool(getattr(settings, "SMTP_USE_TLS", True))

    msg = EmailMessage()
    msg["Subject"] = "Your LIMYÈ solar documents"
    msg["From"] = f'"{from_name}" <{from_email}>'
    msg["To"] = to_email
    msg.set_content(_email_body_text(has_full_estimate))

    msg.add_attachment(
        design_pdf,
        maintype="application",
        subtype="pdf",
        filename="Limye-Solar-Design.pdf",
    )
    msg.add_attachment(
        estimate_pdf,
        maintype="application",
        subtype="pdf",
        filename="Limye-Solar-Proposal.pdf",
    )

    ctx = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=45) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
            return

        with smtplib.SMTP(host, port, timeout=45) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls(context=ctx)
                smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    except ProposalEmailError:
        raise
    except (
        smtplib.SMTPAuthenticationError,
        smtplib.SMTPRecipientsRefused,
        smtplib.SMTPServerDisconnected,
        smtplib.SMTPResponseException,
        OSError,
    ) as e:
        hint = getattr(e, "smtp_code", None)
        extras = getattr(e, "smtp_error", b"")
        tail = ""
        if hint is not None:
            tail = f" (SMTP {hint}"
            if extras:
                try:
                    tail += f" {extras.decode('utf-8', errors='replace')}"
                except Exception:  # noqa: BLE001
                    tail += " …"
            tail += ")"
        raise ProposalEmailError(f"Email could not be delivered: {e}{tail}") from e


__all__ = ["ProposalEmailError", "send_proposal_email_sync", "smtp_configured"]
