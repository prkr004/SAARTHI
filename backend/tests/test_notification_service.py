from __future__ import annotations

from backend.app.services.notification_service import NotificationService


def test_notification_service_uses_fresh_runtime_settings(monkeypatch):
    monkeypatch.setenv("SAARTHI_NOTIFICATION_PROVIDER", "noop")

    first = NotificationService().send_approval_email(
        recipient_email="user@example.com",
        full_name="User One",
    )
    assert first.sent is False
    assert first.warning == "Notification provider is disabled."

    # Simulate updating .env/runtime env while process stays alive.
    monkeypatch.setenv("SAARTHI_NOTIFICATION_PROVIDER", "console")

    second = NotificationService().send_approval_email(
        recipient_email="user@example.com",
        full_name="User One",
    )
    assert second.sent is True
    assert second.warning is None
