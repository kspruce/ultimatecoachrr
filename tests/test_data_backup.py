"""The admin "Export JSON ZIP" backup must include tables with date/time
columns and restore them. It used to skip any table holding a plain date."""
import json
import zipfile
from datetime import date, time

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
