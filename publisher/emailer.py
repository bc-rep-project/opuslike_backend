import os, requests
from typing import List

def send_email(subject: str, html: str, to: List[str]):
    # Choose provider by env
    if os.getenv("SENDGRID_API_KEY"):
        return send_sendgrid(subject, html, to)
    elif os.getenv("MAILGUN_API_KEY") and os.getenv("MAILGUN_DOMAIN"):
        return send_mailgun(subject, html, to)
    else:
        raise RuntimeError("No email provider configured (set SENDGRID_API_KEY or MAILGUN_API_KEY/MAILGUN_DOMAIN)")

def send_sendgrid(subject: str, html: str, to: List[str]):
    key = os.getenv("SENDGRID_API_KEY")
    from_addr = os.getenv("EMAIL_FROM", "no-reply@example.com")
    data = {
        "personalizations": [{"to": [{"email": t} for t in to]}],
        "from": {"email": from_addr},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}]
    }
    r = requests.post("https://api.sendgrid.com/v3/mail/send",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json=data, timeout=15)
    if r.status_code >= 300:
        raise RuntimeError(f"SendGrid error: {r.status_code} {r.text}")
    return True

def send_mailgun(subject: str, html: str, to: List[str]):
    key = os.getenv("MAILGUN_API_KEY")
    domain = os.getenv("MAILGUN_DOMAIN")
    from_addr = os.getenv("EMAIL_FROM", f"no-reply@{domain}")
    r = requests.post(f"https://api.mailgun.net/v3/{domain}/messages",
                      auth=("api", key),
                      data={"from": from_addr,
                            "to": to,
                            "subject": subject,
                            "html": html},
                      timeout=15)
    if r.status_code >= 300:
        raise RuntimeError(f"Mailgun error: {r.status_code} {r.text}")
    return True
