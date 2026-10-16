"""Email delivery: Brevo/Resend over HTTPS take priority over SMTP."""
import json
from unittest import mock

from app.utils import email as email_utils


def _sent_requests(app, **config):
    app.config.update(MAIL_DEFAULT_SENDER='Ultimate Coach <coach@example.com>', **config)
    msg = email_utils._build_message(app.config, 'player@example.com', 'Hi', 'Body text')
    response = mock.MagicMock(status=201)
    response.__enter__.return_value = response
    with mock.patch.object(email_utils, 'urlopen', return_value=response) as urlopen, \
            mock.patch.object(email_utils.smtplib, 'SMTP') as smtp:
        email_utils._deliver(app.config, msg)
    return [call.args[0] for call in urlopen.call_args_list], smtp


def test_brevo_api_is_used_instead_of_smtp(app):
    requests, smtp = _sent_requests(app, BREVO_API_KEY='brevo-key', MAIL_SERVER='smtp.gmail.com')
    assert email_utils.email_provider(app) == 'brevo'
    assert not smtp.called
    (request,) = requests
    assert request.full_url == 'https://api.brevo.com/v3/smtp/email'
    assert request.get_header('Api-key') == 'brevo-key'
    assert json.loads(request.data) == {
        'sender': {'name': 'Ultimate Coach', 'email': 'coach@example.com'},
        'to': [{'email': 'player@example.com'}],
        'subject': 'Hi', 'textContent': 'Body text\n'}


def test_resend_api(app):
    requests, smtp = _sent_requests(app, RESEND_API_KEY='re_key')
    (request,) = requests
    assert request.full_url == 'https://api.resend.com/emails'
    assert request.get_header('Authorization') == 'Bearer re_key'
    assert json.loads(request.data)['from'] == 'Ultimate Coach <coach@example.com>'


def test_no_sender_means_email_is_off(app):
    app.config.update(BREVO_API_KEY='brevo-key', MAIL_DEFAULT_SENDER=None)
    assert not email_utils.email_configured(app)
