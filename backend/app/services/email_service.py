import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
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
        msg["From"] = settings.smtp_from
        msg["To"] = to
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, [to], msg.as_string())


@lru_cache
def get_email_sender() -> EmailSender:
    if settings.email_backend == "smtp":
        return SMTPEmailSender()
    return ConsoleEmailSender()


def send_password_reset_email(to: str, reset_link: str) -> None:
    get_email_sender().send(
        to=to,
        subject="Reset your ai.sumitgroups.com password",
        body=f"Click the link to reset your password (valid for 1 hour): {reset_link}",
    )
