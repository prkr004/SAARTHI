"""Notification service abstraction for user approval workflow."""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    sent: bool
    warning: str | None = None


class NotificationService:
    """Sends approval/rejection notifications via configurable providers."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def send_approval_email(self, *, recipient_email: str | None, full_name: str) -> NotificationResult:
        subject = "SAARTHI access request approved"
        body = (
            f"Hello {full_name},\n\n"
            "Your SAARTHI account request has been approved by the administrator. "
            "You can now sign in to the platform.\n\n"
            "Regards,\n"
            "SAARTHI Admin"
        )
        return self._send_email(recipient_email=recipient_email, subject=subject, body=body)

    def send_rejection_email(
        self,
        *,
        recipient_email: str | None,
        full_name: str,
        review_reason: str | None,
    ) -> NotificationResult:
        reason_block = ""
        if review_reason:
            reason_block = f"\nReason: {review_reason}\n"

        subject = "SAARTHI access request update"
        body = (
            f"Hello {full_name},\n\n"
            "Your SAARTHI account request has been reviewed and was not approved at this time."
            f"{reason_block}\n"
            "You may contact your administrator for clarification.\n\n"
            "Regards,\n"
            "SAARTHI Admin"
        )
        return self._send_email(recipient_email=recipient_email, subject=subject, body=body)

    def _send_email(self, *, recipient_email: str | None, subject: str, body: str) -> NotificationResult:
        provider = self._settings.notification_provider.strip().lower()

        if not recipient_email:
            return NotificationResult(sent=False, warning="User email not available; notification skipped.")

        if provider == "noop":
            logger.info(
                "Notification provider disabled (noop)",
                extra={"recipient_email": recipient_email, "subject": subject},
            )
            return NotificationResult(sent=False, warning="Notification provider is disabled.")

        if provider == "console":
            logger.info(
                "Notification email (console)",
                extra={
                    "recipient_email": recipient_email,
                    "subject": subject,
                    "body_preview": body[:400],
                },
            )
            return NotificationResult(sent=True)

        if provider != "smtp":
            return NotificationResult(sent=False, warning=f"Unsupported notification provider: {provider}")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._settings.notification_from_email
        message["To"] = recipient_email
        message.set_content(body)

        try:
            if self._settings.notification_smtp_use_ssl:
                with smtplib.SMTP_SSL(
                    self._settings.notification_smtp_host,
                    self._settings.notification_smtp_port,
                    timeout=self._settings.notification_smtp_timeout_seconds,
                ) as smtp:
                    self._smtp_authenticate(smtp)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(
                    self._settings.notification_smtp_host,
                    self._settings.notification_smtp_port,
                    timeout=self._settings.notification_smtp_timeout_seconds,
                ) as smtp:
                    if self._settings.notification_smtp_use_starttls:
                        smtp.starttls()
                    self._smtp_authenticate(smtp)
                    smtp.send_message(message)
            return NotificationResult(sent=True)
        except Exception as exc:  # pragma: no cover - depends on external provider
            logger.exception("Notification send failed", extra={"recipient_email": recipient_email})
            return NotificationResult(sent=False, warning=f"Notification delivery failed: {exc}")

    def _smtp_authenticate(self, smtp: smtplib.SMTP) -> None:
        username = self._settings.notification_smtp_username
        password = self._settings.notification_smtp_password
        if username and password:
            smtp.login(username, password)
