"""SMTP delivery for HR recruitment communications."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


class CandidateEmailConfigurationError(RuntimeError):
    pass


class CandidateEmailDeliveryError(RuntimeError):
    pass


def send_candidate_email(*, recipient: str, subject: str, body: str) -> None:
    host=os.getenv("SB_HR_SMTP_HOST","").strip()
    sender=os.getenv("SB_HR_SMTP_FROM","").strip()
    username=os.getenv("SB_HR_SMTP_USERNAME","").strip()
    password=os.getenv("SB_HR_SMTP_PASSWORD","")
    try:
        port=int(os.getenv("SB_HR_SMTP_PORT","587"))
    except ValueError as exc:
        raise CandidateEmailConfigurationError("SB_HR_SMTP_PORT must be a valid port number") from exc
    if not host or not sender or not username or not password:
        raise CandidateEmailConfigurationError(
            "Recruitment email is not configured. Set SB_HR_SMTP_HOST, "
            "SB_HR_SMTP_PORT, SB_HR_SMTP_FROM, SB_HR_SMTP_USERNAME and SB_HR_SMTP_PASSWORD."
        )
    if not 1 <= port <= 65535:
        raise CandidateEmailConfigurationError("SB_HR_SMTP_PORT must be between 1 and 65535")
    message=EmailMessage()
    message["From"]=sender
    message["To"]=recipient
    message["Subject"]=subject.strip()
    message.set_content(body)
    try:
        with smtplib.SMTP(host,port,timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(username,password)
            smtp.send_message(message)
    except (OSError,smtplib.SMTPException) as exc:
        raise CandidateEmailDeliveryError("Recruitment email could not be delivered by the configured SMTP server") from exc
