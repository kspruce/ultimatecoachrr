"""Every GET page renders without a server error, with a recorded season
loaded and an admin logged in. Catches broken templates and routes."""
import re

import pytest

from app import db

from tests import stats_data

# Routes that call out to other services or start a browser.
SKIP = re.compile(r'pdf|discord|youtube|/auth/logout|download|/export', re.I)


@pytest.fixture
def client(app):
    team = stats_data.build_team()
    admin = stats_data.build_admin(team)
    players = stats_data.build_players(team)
    return stats_data.record_season(app, team, admin, players, games_per_tournament=1,
                                    points_per_game=5)


def test_every_get_page_renders(app, client):
    app.config['PROPAGATE_EXCEPTIONS'] = False  # collect every 500, don't stop at the first
    failures = []
    rules = sorted({r.rule for r in app.url_map.iter_rules()
                    if 'GET' in r.methods and not r.rule.startswith('/static')})
    for rule in rules:
        if SKIP.search(rule):
            continue
        url = re.sub(r'<(?:int:)?\w+>', '1', rule)
        url = re.sub(r'<(?:string|path):\w+>', 'x', url)
        response = client.get(url)
        if response.status_code >= 500:
            failures.append(f'{response.status_code} {url}')
    assert not failures, '\n'.join(failures)


def test_no_two_routes_share_a_url(app):
    """Flask silently uses whichever blueprint registered first, which is how
    the old data management and calendar RSVP pages hid the newer ones."""
    seen = {}
    for rule in app.url_map.iter_rules():
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            key = (rule.rule, method)
            assert key not in seen, f'{rule.rule} {method}: {seen.get(key)} and {rule.endpoint}'
            seen[key] = rule.endpoint


def test_removed_pages_are_gone(app, client):
    assert client.get('/team/debug').status_code == 404
    assert 'session.rsvp' == next(r.endpoint for r in app.url_map.iter_rules()
                                  if r.rule == '/sessions/<int:session_id>/rsvp')


def test_session_pdf_download(app, client, monkeypatch):
    from app.utils import pdf
    rendered = {}

    def fake(html):
        rendered['html'] = html
        return b'%PDF-1.4 fake'
    monkeypatch.setattr(pdf, 'html_to_pdf', fake)
    from app.models.session import SessionPlan
    from app.models.team_organization import TeamOrganization
    team_id = TeamOrganization.query.first().id
    db.session.add(SessionPlan(id=1, title='Split 2s', team_organization_id=team_id))
    db.session.commit()
    assert b'Download PDF' in client.get('/sessions/1/detail').data
    r = client.get('/sessions/1/export_pdf')
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert r.data.startswith(b'%PDF') and 'Split 2s' in rendered['html']
    assert 'session_1_split-2s.pdf' in r.headers['Content-Disposition']
