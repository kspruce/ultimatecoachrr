"""Two teams with something in as many tables as possible: a recorded
season, imported drills (with diagram images) and sessions, a season plan,
users, playbook, clips, scouting, fitness, theory and feedback. Used to
check that backups and team exports leave nothing behind."""
import json
import os
from datetime import date, datetime

from app import db
from app.models.clip import Clip, ClipTag
from app.models.clip_playlist import ClipPlaylist, ClipPlaylistItem
from app.models.feedback import PlayerFeedback
from app.models.fitness import FitnessMetric, FitnessRecord, FitnessGoal
from app.models.playbook import Formation, Play, PlayTag
from app.models.scouting import ScoutingReport, OpponentPlayer
from app.models.session import SessionPlan, SessionRSVP, Attendance
from app.models.team_settings import TeamSettings
from app.models.theory import TheorySection, TheoryTopic
from app.models.user import User
from tests import stats_data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')
SEASON_PLAN = os.path.join(ROOT, 'imports', 'season-plan-export')


def build_team(app, name, slug):
    """One fully used team. Returns its id."""
    from app.utils.season_import import import_season
    from app.utils.season_plan_import import import_season_plan

    team = stats_data.build_team(name, slug)
    team_id = team.id
    db.session.add(TeamSettings(team_id=team_id, season_plan_enabled=True))
    admin = stats_data.build_admin(team, f'{slug}-admin', superadmin=False)
    coach = User(username=f'{slug}-coach', email=f'{slug}-coach@example.com', role='coach',
                 team_organization_id=team_id)
    coach.set_password('coach-pass')
    db.session.add(coach)
    db.session.commit()
    players = stats_data.build_players(team, 14)
    stats_data.record_season(app, team, admin, players, games_per_tournament=1, points_per_game=2)

    with open(os.path.join(FIXTURES, 'sample_season.json')) as f:
        import_season(json.load(f), os.path.join(FIXTURES, 'season_images'), team_id)
    if os.path.isdir(SEASON_PLAN):
        import_season_plan(SEASON_PLAN, db.session.get(type(team), team_id))

    player_id = players[0].id
    session = SessionPlan.query.filter_by(team_organization_id=team_id).first()
    db.session.add_all([
        SessionRSVP(session_id=session.id, player_id=player_id, status='yes',
                    team_organization_id=team_id),
        Attendance(session_id=session.id, player_id=player_id, status='present',
                   team_organization_id=team_id),
        PlayerFeedback(player_id=player_id, coach_id=coach.id, content='Great cuts',
                       context_tag='General'),
    ])
    tag = PlayTag(name=f'{slug} horizontal', team_organization_id=team_id)
    formation = Formation(name=f'{slug} vert stack', team_organization_id=team_id)
    db.session.add_all([tag, formation])
    db.session.flush()
    db.session.add(Play(name=f'{slug} side stack', formation_id=formation.id, tags=[tag],
                        team_organization_id=team_id))
    clip_tag = ClipTag(name=f'{slug} huck', team_organization_id=team_id)
    clip = Clip(title=f'{slug} highlight', youtube_link='https://youtu.be/abc12345678',
                start_time=5, end_time=20, team_organization_id=team_id, tags=[clip_tag])
    report = ScoutingReport(team_name=f'{slug} rivals', date=date(2026, 6, 1),
                            team_organization_id=team_id)
    db.session.add_all([clip, report])
    db.session.flush()
    db.session.add(OpponentPlayer(scouting_report_id=report.id, name='Their handler',
                                  team_organization_id=team_id))
    db.session.add(ClipPlaylist(title=f'{slug} film session', team_organization_id=team_id, items=[
        ClipPlaylistItem(clip_id=clip.id, position=0, note='Watch the mark', team_organization_id=team_id)]))
    metric = FitnessMetric(name=f'{slug} 40m sprint', unit='s', team_organization_id=team_id)
    section = TheorySection(name=f'{slug} cutting', slug=f'{slug}-cutting',
                            team_organization_id=team_id)
    db.session.add_all([metric, section])
    db.session.flush()
    db.session.add_all([
        FitnessRecord(player_id=player_id, metric_id=metric.id, value=5.4,
                      date_recorded=datetime(2026, 5, 1), team_organization_id=team_id),
        FitnessGoal(player_id=player_id, metric_id=metric.id, target_value=5.0,
                    team_organization_id=team_id),
        TheoryTopic(section_id=section.id, name='Timing', content='**Go** early',
                    team_organization_id=team_id),
    ])
    db.session.commit()
    return team_id


def build(app):
    """Two teams; returns (first_team_id, second_team_id)."""
    return build_team(app, 'Alpha', 'alpha'), build_team(app, 'Bravo', 'bravo')


def snapshot(team_id=None):
    """Every row of every table as comparable tuples, keyed by table name.
    With team_id, only tables that have a team column, filtered to it."""
    rows = {}
    for name, table in sorted(db.metadata.tables.items()):
        query = table.select()
        if team_id is not None:
            if 'team_organization_id' not in table.c:
                continue
            query = query.where(table.c.team_organization_id == team_id)
        result = db.session.execute(query).mappings().all()
        rows[name] = sorted((tuple(sorted((k, repr(v)) for k, v in r.items())) for r in result))
    return rows
