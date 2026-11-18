"""Draft sessions for the season plan's weeks (Season plan > Sessions >
Create draft sessions), so coaches can plan weeks ahead in the session
planner before any session notes are written.

For each chosen week that has a theme but no session notes, a joint
session table is written into the week's notes, from the standard session
shape or one of the team's saved session templates, and the week is built.
New sessions start unpublished, so players see nothing until a coach
publishes them. From then on the week and its session stay in step both
ways (season_sessions.reconcile, season_writeback.write_back).
"""
from datetime import datetime

from app import db
from app.models.schedule import SessionTemplate
from app.utils import session_outline as so
from app.utils.season_sessions import build_sessions

# The shape every session takes unless a template is picked (the starter
# templates' "How we train" page). The skill row carries the week's theme.
STANDARD_SHAPE = [
    {'title': 'Warm-up', 'duration_minutes': 15, 'description': 'Dynamic warm-up, then throwing in pairs'},
    {'title': 'Skill', 'duration_minutes': 25, 'description': "This week's theme as a drill or a small game"},
    {'title': 'Game', 'duration_minutes': 30, 'description': 'A small-sided game whose rules reward the skill'},
    {'title': 'Scrimmage', 'duration_minutes': 30, 'description': 'Full game; one thing to look for from the theme'},
    {'title': 'Close', 'duration_minutes': 5, 'description': 'What went well, one thing to work on'},
]


def draftable(week):
    """A week the button can fill: not a break, no session notes yet, and
    something to plan around (a theme or a block)."""
    if week.is_break or (week.session_detail_md or '').strip():
        return False
    return bool(week.joint_theme or week.block or any((week.squad_themes or {}).values()))


def template_blocks(plan, template_id=None):
    """The blocks drafts start from: a saved session template of the plan's
    team, else the standard shape."""
    if template_id:
        template = SessionTemplate.query.filter_by(id=template_id,
                                                   team_organization_id=plan.team_organization_id).first()
        if template is not None and template.blocks:
            # A block on a library drill is written with the drill's title,
            # so building links it back to the drill
            from app.models.drill import SavedDrill
            ids = [b.get('drill_id') for b in template.blocks if b.get('drill_id')]
            titles = dict(db.session.query(SavedDrill.id, SavedDrill.title).filter(
                SavedDrill.id.in_(ids), SavedDrill.team_organization_id == plan.team_organization_id)) if ids else {}
            return [dict(b, title=titles.get(b.get('drill_id')) or b['title']) for b in template.blocks]
    return STANDARD_SHAPE


def _theme(week):
    return week.joint_theme or next((v for v in (week.squad_themes or {}).values() if v), None) or week.block


def notes_for(week, blocks, standard=False):
    """A week's session notes: a joint table of the blocks."""
    total = sum(b.get('duration_minutes') or 0 for b in blocks)
    label = f'**Joint session (about {total} minutes)**' if total else '**Joint session**'
    table = so.Table(kind='joint', label=label, columns=[('time', 'Time'), ('activity', 'Activity'),
                                                         ('how', 'How it runs'), ('source', 'Source')])
    t = 0
    for b in blocks:
        how = b.get('description') or None
        if standard and b['title'] == 'Skill' and _theme(week):
            how = f'{_theme(week)}. {how}'
        table.rows.append({'time': so.clock(t), 'activity': b['title'], 'how': how, 'source': None})
        t += b.get('duration_minutes') or 0
    return so.render(so.Outline(parts=[table]))


def create_drafts(plan, weeks=None, template_id=None):
    """Write draft session notes into `weeks` (default: every draftable
    week) and build their sessions unpublished. Returns (weeks filled,
    the build report). The caller commits."""
    weeks = [w for w in (weeks if weeks is not None else plan.weeks) if draftable(w)]
    blocks = template_blocks(plan, template_id)
    standard = blocks is STANDARD_SHAPE
    for week in weeks:
        week.session_detail_md = notes_for(week, blocks, standard=standard)
    db.session.flush()
    report = build_sessions(plan, weeks=weeks, commit=False, draft=True) if weeks else None
    if weeks and plan.sessions_built_at is None:
        # From now on, editing a week keeps its sessions in step
        plan.sessions_built_at = datetime.utcnow()
    return weeks, report
