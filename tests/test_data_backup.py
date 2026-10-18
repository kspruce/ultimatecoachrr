"""The admin "Export JSON ZIP" backup must include tables with date/time
columns and restore them. It used to skip any table holding a plain date."""
import io
import json
import zipfile
from datetime import date, time

import pytest

from app import db
from app.models.session import SessionPlan
from app.models.drill import DrillDiagram
from app.utils.enhanced_data_manager import EnhancedDataManager


def test_json_zip_backup_round_trips_dates_and_times(app, team, tmp_path):
    plan = SessionPlan(id=1, title='Dated session', date=date(2027, 10, 16),
                       start_time=time(10, 0), end_time=time(12, 30),
                       week_commencing=date(2027, 10, 11), team_organization_id=team.id,
                       learning_points=['a', 'b'])
    db.session.add(plan)
    db.session.commit()

    manager = EnhancedDataManager(export_dir=str(tmp_path))
    buffer, name = manager.export_all_to_json_zip(timestamp=False)
    zip_path = tmp_path / name
    zip_path.write_bytes(buffer.getvalue())

    with zipfile.ZipFile(zip_path) as z:
        summary = json.loads(z.read('export_summary.json'))
        exported = json.loads(z.read('session_plan.json'))
    assert 'error' not in summary['session_plan'], summary['session_plan']
    assert exported[0]['date'] == '2027-10-16'
    assert exported[0]['start_time'] == '10:00:00'

    db.session.query(SessionPlan).delete()
    db.session.commit()

    manager.import_from_zip(str(zip_path))

    restored = db.session.get(SessionPlan, 1)
    assert restored.date == date(2027, 10, 16)
    assert restored.week_commencing == date(2027, 10, 11)
    assert restored.start_time == time(10, 0) and restored.end_time == time(12, 30)
    assert restored.learning_points == ['a', 'b']
    assert 'drill_diagram' in summary
    assert DrillDiagram.query.count() == 0


def test_backup_restores_users_and_blank_numbers(app, team, tmp_path):
    """user.is_admin is a column whose model attribute is is_admin_flag (the
    restore used to skip every user, and everything linked to them), and the
    live data has blank jersey numbers stored as ''."""
    import json
    from app.models.player import Player
    from app.models.user import User

    admin = User(username='coach', role='admin', is_admin_flag=True, team_organization_id=team.id)
    admin.set_password('x')
    db.session.add(admin)
    db.session.commit()
    player = Player(name='Blank Number', user_id=admin.id, team_organization_id=team.id)
    db.session.add(player)
    db.session.commit()

    manager = EnhancedDataManager(export_dir=str(tmp_path))
    buffer, name = manager.export_all_to_json_zip(timestamp=False)
    zip_path = tmp_path / name
    # Make the player file look like the live export (jersey_number as '')
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as z:
        files = {n: z.read(n) for n in z.namelist()}
    players = json.loads(files['player.json'])
    players[0]['jersey_number'] = ''
    files['player.json'] = json.dumps(players).encode()
    with zipfile.ZipFile(zip_path, 'w') as z:
        for n, data in files.items():
            z.writestr(n, data)

    db.session.query(Player).delete()
    db.session.query(User).delete()
    db.session.commit()

    manager.import_from_zip(str(zip_path))

    user = User.query.filter_by(username='coach').one()
    assert user.is_admin_flag is True and user.check_password('x')
    restored = Player.query.filter_by(name='Blank Number').one()
    assert restored.jersey_number is None and restored.user_id == user.id


def test_both_exports_include_link_tables(app, team, tmp_path):
    """Link tables (no model class) used to be left out of the "Export data"
    button's zip, so a restore lost clip tags, clip players and play components."""
    manager = EnhancedDataManager(export_dir=str(tmp_path))
    for buffer, _ in (manager.export_all_data(timestamp=False),
                      manager.export_all_to_json_zip(timestamp=False)):
        with zipfile.ZipFile(buffer) as z:
            names = z.namelist()
        assert 'assoc_clip_tag_relation.json' in names, names


def test_old_data_management_page_redirects_to_the_new_one(app, team):
    from tests import stats_data
    admin = stats_data.build_admin(team, 'kit')
    client = stats_data.Client(app, admin.id, team.id)
    r = client.get('/admin/data-management')
    assert r.status_code == 301
    assert r.headers['Location'].endswith('/admin/enhanced-data-management')
    # The new page's forms post here; the old page's handlers used to answer.
    endpoints = {rule.rule: rule.endpoint for rule in app.url_map.iter_rules()}
    for url in ('/admin/export-data', '/admin/import-data', '/admin/download-export',
                '/admin/delete-export'):
        assert endpoints[url].startswith('data_management.'), url
    assert client.get('/admin/enhanced-data-management').status_code == 200


def _download(client, export):
    if export == 'json-zip':
        r = client.get('/admin/export-json-zip')
    else:
        r = client.post('/admin/export-data', data={'export_format': 'json'})
    assert r.status_code == 200 and r.mimetype == 'application/zip', r.status_code
    return r.data


@pytest.mark.parametrize('export', ['json-zip', 'export-data'])
@pytest.mark.parametrize('restore', ['/admin/import-zip-file', '/admin/import-data'])
def test_whole_site_backup_restores_every_row(app, export, restore):
    """A superadmin downloads a backup, the data then changes (or is lost),
    and restoring with "clear existing" brings back exactly what was saved,
    and the site can still add new rows afterwards (Postgres id sequences)."""
    from app.models.team_organization import TeamOrganization
    from app.models.player import Player
    from app.models.game import Game
    from app.models.fitness import FitnessRecord
    from tests import rich_data, stats_data

    alpha, bravo = rich_data.build(app)
    boss = stats_data.build_admin(db.session.get(TeamOrganization, alpha), 'boss')
    client = stats_data.Client(app, boss.id, alpha)
    backup = _download(client, export)
    db.session.remove()
    saved = rich_data.snapshot()  # what the backup holds

    # Things go wrong after the backup
    Player.query.filter_by(team_organization_id=bravo).update({'name': 'Overwritten'})
    db.session.add(Game(opponent='Not in the backup', team_organization_id=alpha))
    db.session.query(FitnessRecord).delete()
    db.session.commit()

    r = client.post(restore, data={'import_file': (io.BytesIO(backup), 'backup.zip'),
                                   'clear_existing': 'on'},
                    content_type='multipart/form-data')
    assert r.status_code == 302
    db.session.remove()
    restored = rich_data.snapshot()
    for table in saved:
        assert restored[table] == saved[table], table
    assert sum(len(rows) for rows in saved.values()) > 400

    db.session.add_all([Player(name='Joined after restore', team_organization_id=alpha),
                        SessionPlan(title='Planned after restore', team_organization_id=alpha)])
    db.session.commit()
