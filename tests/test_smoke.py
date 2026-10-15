"""Every GET page renders without a server error, with a recorded season
loaded and an admin logged in. Catches broken templates and routes."""
import re

import pytest

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
