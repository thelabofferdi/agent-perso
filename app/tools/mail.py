"""Envoi d'e-mails via SMTP. L'appel est soumis à approbation humaine côté agent."""

import asyncio
import re
import smtplib
import ssl
from email.message import EmailMessage

from app.config import ToolError, get_settings

_EMAIL_RE = re.compile(r"^[^@\s,;]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$")
DISCLAIMER = "\n\n--\nEnvoyé par un agent IA à la demande de l'utilisateur."


def _send(msg: EmailMessage) -> None:
    s = get_settings()
    if s.smtp_port == 465:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ssl.create_default_context(), timeout=20) as srv:
            srv.login(s.smtp_user, s.smtp_password.replace(" ", ""))
            srv.send_message(msg)
    else:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as srv:
            srv.starttls(context=ssl.create_default_context())
            srv.login(s.smtp_user, s.smtp_password.replace(" ", ""))
            srv.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un e-mail réel. L'utilisateur confirme avant l'envoi : fournir destinataire, objet et corps complets."""
    s = get_settings()
    if s.missing("smtp_user", "smtp_password"):
        raise ToolError("SMTP_USER / SMTP_PASSWORD ne sont pas configurés.")
    if not _EMAIL_RE.match(to.strip()):
        raise ToolError(f"Adresse e-mail invalide : {to!r}")
    if not subject.strip() or not body.strip():
        raise ToolError("L'objet et le contenu de l'e-mail ne peuvent pas être vides.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to.strip(), subject.strip()
    msg.set_content(body + DISCLAIMER)
    try:
        await asyncio.to_thread(_send, msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise ToolError(f"Échec de l'envoi SMTP : {exc.__class__.__name__}") from exc
    return f"E-mail envoyé à {to.strip()} (objet : {subject.strip()})."
