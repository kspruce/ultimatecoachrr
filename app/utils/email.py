"""Sending email, when it's configured.

Email goes out through Brevo's or Resend's web API when BREVO_API_KEY or
RESEND_API_KEY is set (these use HTTPS, which works on hosts such as
Railway's lower plans that block SMTP), otherwise over SMTP via MAIL_SERVER.

Email is optional. email_configured() says whether a way to send and a
sender are set; callers fall back to showing a link to copy when it isn't.
Messages go out on a background thread so a slow mail server never holds up
a page (and so response times don't reveal whether an address has an
account).
"""
import json
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from flask import current_app

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 20


def email_provider(app=None):
    """How email is sent: 'brevo', 'resend', 'smtp', or None if not set up."""
    config = (app or current_app).config
    if not config.get('MAIL_DEFAULT_SENDER'):
        return None
    if config.get('BREVO_API_KEY'):
        return 'brevo'
    if config.get('RESEND_API_KEY'):
        return 'resend'
    if config.get('MAIL_SERVER'):
        return 'smtp'
    return None


def email_configured(app=None):
    return email_provider(app) is not None


def is_real_email(address):
    """True for an address an email could actually be delivered to."""
    if not address or address.endswith('@no-email.placeholder'):
        return False
    return '@' in parseaddr(address)[1]


def _build_message(config, to, subject, body):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = config['MAIL_DEFAULT_SENDER']
    msg['To'] = to
    msg.set_content(body)
    return msg


def _post_json(url, headers, payload):
    request = Request(url, data=json.dumps(payload).encode(), method='POST',
                      headers={'Content-Type': 'application/json',
                               'Accept': 'application/json', **headers})
    try:
        with urlopen(request, timeout=SMTP_TIMEOUT) as response:
            return response.status
    except HTTPError as e:
        # Surface the service's own explanation (bad key, unverified sender...)
        detail = e.read().decode(errors='replace')[:300]
        raise RuntimeError(f'{url.split("/")[2]} said {e.code}: {detail}') from None


def _deliver_api(provider, config, msg):
    name, sender = parseaddr(msg['From'])
    if provider == 'brevo':
        _post_json('https://api.brevo.com/v3/smtp/email',
                   {'api-key': config['BREVO_API_KEY']},
                   {'sender': {'name': name or 'Ultimate Coach', 'email': sender},
                    'to': [{'email': msg['To']}],
                    'subject': msg['Subject'],
                    'textContent': msg.get_content()})
    else:
        _post_json('https://api.resend.com/emails',
                   {'Authorization': f"Bearer {config['RESEND_API_KEY']}"},
                   {'from': msg['From'], 'to': [msg['To']],
                    'subject': msg['Subject'], 'text': msg.get_content()})


def _deliver(config, msg):
    provider = ('brevo' if config.get('BREVO_API_KEY')
                else 'resend' if config.get('RESEND_API_KEY') else 'smtp')
    if provider != 'smtp':
        _deliver_api(provider, config, msg)
        return

    host, port = config['MAIL_SERVER'], config.get('MAIL_PORT') or 587
    context = ssl.create_default_context()
    if config.get('MAIL_USE_SSL'):
        server = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
    with server:
        if not config.get('MAIL_USE_SSL') and config.get('MAIL_USE_TLS'):
            server.starttls(context=context)
        if config.get('MAIL_USERNAME'):
            server.login(config['MAIL_USERNAME'], config.get('MAIL_PASSWORD') or '')
        server.send_message(msg)


def send_email(to, subject, body, wait=False):
    """Send a plain-text email. Returns False if email isn't configured or the
    address can't receive mail. With wait=True the email is sent before
    returning and errors are raised (used by the admin "send test email"
    button); otherwise it's sent in the background and errors are logged."""
    app = current_app._get_current_object()
    if not email_configured(app) or not is_real_email(to):
        return False

    config = dict(app.config)
    msg = _build_message(config, to, subject, body)

    if app.config.get('TESTING'):
        # Tests read sent messages from here instead of talking to a server
        app.extensions.setdefault('sent_emails', []).append(msg)
        return True
    if wait:
        _deliver(config, msg)
        return True

    def run():
        try:
            _deliver(config, msg)
        except Exception as e:
            logger.error('Could not send email "%s" to %s: %s', subject, to, e)

    threading.Thread(target=run, daemon=True).start()
    return True
