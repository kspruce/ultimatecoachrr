"""A team admin can download all their team's data and delete their team.
Checked against two fully used teams: nothing of the other team's leaks into
the download or is touched by the delete."""
import io
import json
import zipfile

import pytest

from app import db
from app.models.team_organization import TeamOrganization
from app.models.user import User
from app.utils.team_data import team_tables
from tests import rich_data, stats_data


@pytest.fixture
def teams(app):
    alpha, bravo = rich_data.build(app)
    admin = User.query.filter_by(username='alpha-admin').one()
    admin.set_password('admin-pass')
    db.session.commit()
    coach = User.query.filter_by(username='alpha-coach').one()
    return {'alpha': alpha, 'bravo': bravo,
            'admin': stats_data.Client(app, admin.id, alpha),
            'coach': stats_data.Client(app, coach.id, alpha)}


# Things only the other team has (its season plan text mentions "bravo")
BRAVO = ('Bravo Player', 'bravo-admin', 'bravo-coach', 'bravo side stack', 'bravo huck',
         'bravo rivals', 'bravo 40m sprint', 'bravo Tour')
ALPHA = tuple(m.replace('bravo', 'alpha').replace('Bravo', 'Alpha') for m in BRAVO)


def _mentions(text, markers):
    return any(m in text for m in markers)


def _rows(snapshot):
    return {(table, row) for table, rows in snapshot.items() for row in rows}


def test_download_has_every_team_row_and_nothing_else(teams):
    r = teams['admin'].get('/team/settings/data/export')
    assert r.status_code == 200 and r.mimetype == 'application/zip'
    z = zipfile.ZipFile(io.BytesIO(r.data))
    names = z.namelist()
    assert 'README.txt' in names and 'csv/player.csv' in names
    exported = {n[5:-5]: json.loads(z.read(n)) for n in names if n.startswith('json/')}

    # Every row of every table with a team column is there
    for table, rows in rich_data.snapshot(teams['alpha']).items():
        assert len(exported.get(table, [])) == len(rows), table
    assert exported['drill_diagram'][0]['image_data']  # diagram images come along
    assert exported['play_tag_association'] and exported['player_feedback']

    everything = b''.join(z.read(n) for n in names).decode()
    assert not _mentions(everything, BRAVO) and _mentions(everything, ALPHA)
    for table, rows in exported.items():
        assert all(row.get('team_organization_id') in (None, teams['alpha']) for row in rows), table
    assert 'password_hash' not in everything and 'pbkdf2:' not in everything and 'scrypt:' not in everything


def test_only_team_admins_can_download_or_delete(teams):
    assert teams['coach'].get('/team/settings/data').status_code == 403
    assert teams['coach'].get('/team/settings/data/export').status_code == 403
    teams['coach'].post('/team/settings/data/delete',
                        data={'confirm_name': 'Alpha', 'password': 'coach-pass'})
    assert db.session.get(TeamOrganization, teams['alpha']) is not None
    page = teams['admin'].get('/team/settings/data').get_data(as_text=True)
    assert 'Download all data' in page and 'Delete team and all data' in page


@pytest.mark.parametrize('name,password', [('alpha', 'admin-pass'), ('Alpha', 'wrong')])
def test_delete_needs_the_exact_name_and_password(teams, name, password):
    teams['admin'].post('/team/settings/data/delete', data={'confirm_name': name, 'password': password})
    assert db.session.get(TeamOrganization, teams['alpha']) is not None


def test_deleting_a_team_removes_all_of_it_and_none_of_the_other(app, teams):
    before = rich_data.snapshot()
    expected = sum(len(rows) for rows in team_tables(teams['alpha']).values())

    r = teams['admin'].post('/team/settings/data/delete',
                            data={'confirm_name': 'Alpha', 'password': 'admin-pass'})
    assert r.status_code == 302
    db.session.remove()
    after = rich_data.snapshot()

    removed = _rows(before) - _rows(after)
    assert _rows(after) <= _rows(before)  # nothing else changed
    assert len(removed) == expected
    assert not any(_mentions(str(row), BRAVO) for _, row in removed)
    assert not any(_mentions(str(row), ALPHA) for _, row in _rows(after))
    assert db.session.get(TeamOrganization, teams['alpha']) is None
    assert teams['admin'].get('/team/settings/data').status_code == 302  # logged out
