import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

from app.core.logging import get_logger
from app.services import settings_service

logger = get_logger("email")


class EmailSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender(EmailSender):
    """Dev-mode sender: logs the email instead of delivering it, so password-reset flows are
    testable before real SMTP credentials are configured."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.info("email.console_send", to=to, subject=subject, body=body)


class SMTPEmailSender(EmailSender):
    def send(self, to: str, subject: str, body: str) -> None:
        msg = MIMEText(body)
        msg["Subject"] = subject
        sender = settings_service.get_str_sync("smtp_from")
        msg["From"] = sender
        msg["To"] = to
        with smtplib.SMTP(
            settings_service.get_str_sync("smtp_host"),
            settings_service.get_int_sync("smtp_port", 587),
        ) as server:
            server.starttls()
            user = settings_service.get_str_sync("smtp_user")
            if user:
                server.login(user, settings_service.get_str_sync("smtp_password"))
            server.sendmail(sender, [to], msg.as_string())


def get_email_sender() -> EmailSender:
    # Deliberately not cached: switching delivery method in the admin UI must take effect on the
    # next email, and building either sender is free.
    if settings_service.get_str_sync("email_backend") == "smtp":
        return SMTPEmailSender()
    return ConsoleEmailSender()


def send_password_reset_email(to: str, reset_link: str) -> None:
    get_email_sender().send(
        to=to,
        subject="Reset your ai.sumitgroups.com password",
        body=f"Click the link to reset your password (valid for 1 hour): {reset_link}",
    )
