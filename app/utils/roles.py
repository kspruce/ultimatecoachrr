"""Team roles and who holds them each season (Team → Roles, player profiles,
the playbook). See app/models/team_role.py."""
import json

from app import db
from app.models.playbook import PlayerPosition
from app.models.season import SeasonRoster
from app.models.team_role import PlayerRole

ASSIGNED, PREFERRED = PlayerRole.ASSIGNED, PlayerRole.PREFERRED

# Offered to a team with no roles yet; they're edited from there
STARTER_ROLES = [
    ('O', 'Centre handler', 'Runs the offence from the middle: resets, swings, breaks.'),
    ('O', 'Reset handler', 'Gives the reset and keeps the disc moving across the field.'),
    ('O', 'Initiation cutter', 'First cut of the stack: makes the first big under or deep.'),
    ('O', 'Deep cutter', 'Holds the deep space and takes the huck.'),
    ('O', 'Under cutter', 'Works the unders and continues the flow.'),
    ('D', 'Handler mark', 'Marks and pressures their handlers; stops the easy reset.'),
    ('D', 'Downfield defender', 'Marks a cutter; takes away their first look.'),
    ('D', 'Deep defender', 'Protects the deep space and reads the huck.'),
    ('D', 'Cup', 'Zone: the cup around the disc.'),
    ('D', 'Wing', 'Zone: the wings, stopping the swing and the line.'),
]
LINE_ORDER = {'O': 0, 'D': 1}


def team_roles(team_id):
    """The team's roles: O-line, then D-line, then either; in their order."""
    roles = PlayerPosition.query.filter_by(team_organization_id=team_id).all()
    return sorted(roles, key=lambda r: (LINE_ORDER.get(r.line or '', 2), r.sort_order or 0, r.name.lower()))


def add_starter_roles(team_id):
    for n, (line, name, description) in enumerate(STARTER_ROLES, start=1):
        db.session.add(PlayerPosition(team_organization_id=team_id, line=line, name=name,
                                      description=description, sort_order=n))


def next_order(team_id):
    last = db.session.query(db.func.max(PlayerPosition.sort_order)).filter_by(team_organization_id=team_id).scalar()
    return (last or 0) + 1


def _rows(roster, kind):
    return [r for r in roster.roles if r.kind == kind]


def role_rows(role, season, kind=ASSIGNED):
    """Who holds `role` in `season`, first choice first."""
    return (PlayerRole.query.join(SeasonRoster, PlayerRole.season_roster_id == SeasonRoster.id)
            .filter(PlayerRole.role_id == role.id, PlayerRole.kind == kind, SeasonRoster.season_id == season.id)
            .order_by(PlayerRole.depth, PlayerRole.id).all())


def _renumber(role, season):
    for n, row in enumerate(role_rows(role, season), start=1):
        row.depth = n


def assign(roster, role):
    """Give the player `role` this season, last in the depth order. Their
    first role becomes their main one."""
    existing = next((r for r in _rows(roster, ASSIGNED) if r.role_id == role.id), None)
    if existing:
        return existing
    depth = len(role_rows(role, roster.season)) + 1
    row = PlayerRole(team_organization_id=roster.team_organization_id, roster=roster, role=role,
                     kind=ASSIGNED, depth=depth, is_main=not _rows(roster, ASSIGNED))
    db.session.add(row)
    return row


def unassign(row):
    roster, role, was_main = row.roster, row.role, row.is_main
    roster.roles.remove(row)
    db.session.flush()
    _renumber(role, roster.season)
    if was_main:
        others = sorted(_rows(roster, ASSIGNED), key=lambda r: r.depth)
        if others:
            others[0].is_main = True


def move(row, step):
    """Up (-1) or down (+1) the role's depth order."""
    rows = role_rows(row.role, row.roster.season)
    i = rows.index(row)
    j = i + step
    if 0 <= j < len(rows):
        rows[i], rows[j] = rows[j], rows[i]
        for n, r in enumerate(rows, start=1):
            r.depth = n


def make_main(row):
    for r in _rows(row.roster, ASSIGNED):
        r.is_main = r.id == row.id


def set_roles(roster, roles, kind, main_role_id=None):
    """The player's roles of `kind` this season become exactly `roles`."""
    wanted = {r.id: r for r in roles}
    for row in list(_rows(roster, kind)):
        if row.role_id not in wanted:
            if kind == ASSIGNED:
                unassign(row)
            else:
                roster.roles.remove(row)
    have = {r.role_id for r in _rows(roster, kind)}
    for role in roles:
        if role.id not in have:
            if kind == ASSIGNED:
                assign(roster, role)
            else:
                db.session.add(PlayerRole(team_organization_id=roster.team_organization_id, roster=roster,
                                          role=role, kind=PREFERRED, depth=1, is_main=False))
    db.session.flush()
    if kind == ASSIGNED:
        rows = _rows(roster, ASSIGNED)
        main = next((r for r in rows if r.role_id == main_role_id), None)
        if main is None and rows and not any(r.is_main for r in rows):
            main = min(rows, key=lambda r: r.depth)
        if main is not None:
            make_main(main)


def player_roles(roster, kind=ASSIGNED):
    """The player's roles this season, main role first."""
    if roster is None:
        return []
    rows = _rows(roster, kind)
    return sorted(rows, key=lambda r: (not r.is_main, LINE_ORDER.get(r.role.line or '', 2), r.role.sort_order or 0))


def board(team_id, season, team):
    """Each role with who holds it, and a warning when it needs someone."""
    roster = [r for r in season.roster if r.on_team and r.player] if season else []
    mixed = (team.division or '').lower() == 'mixed'
    roles = []
    for role in team_roles(team_id):
        rows = [r for r in role_rows(role, season) if r.roster.on_team] if season else []
        genders = {(r.roster.player.gender or '').lower() for r in rows} - {''}
        warning = None
        if not rows:
            warning = 'Nobody yet'
        elif len(rows) == 1:
            warning = 'Only one player'
        elif mixed and len(genders) == 1:
            warning = 'Only women' if genders == {'female'} else 'Only men' if genders == {'male'} else None
        wanted_by = [r.roster for r in role_rows(role, season, PREFERRED)
                     if r.roster.on_team and r.season_roster_id not in {a.season_roster_id for a in rows}] if season else []
        roles.append({'role': role, 'rows': rows, 'warning': warning, 'wanted_by': wanted_by,
                      'free': sorted((r for r in roster if r.id not in {a.roster.id for a in rows}),
                                     key=lambda r: r.player.name.lower())})
    with_role = {r.season_roster_id for r in PlayerRole.query.join(SeasonRoster).filter(
        SeasonRoster.season_id == season.id, PlayerRole.kind == ASSIGNED)} if season else set()
    unassigned = sorted((r for r in roster if r.id not in with_role), key=lambda r: r.player.name.lower())
    return roles, unassigned


def copy_roles(previous, season, player_ids):
    """A new season starts with last season's roles and preferences for the
    players carried over (coaches change them from there)."""
    if previous is None or previous.id == season.id:
        return
    new = {r.player_id: r for r in season.roster if r.player_id in player_ids}
    for old in previous.roster:
        target = new.get(old.player_id)
        if target is None or target.roles:
            continue
        for row in old.roles:
            db.session.add(PlayerRole(team_organization_id=season.team_organization_id, roster=target,
                                      role_id=row.role_id, kind=row.kind, depth=row.depth, is_main=row.is_main))
    db.session.flush()
    # Players who didn't carry over leave gaps in the depth order
    for role in team_roles(season.team_organization_id):
        _renumber(role, season)


# ── Roles in the playbook ──────────────────────────────────────────────────

def drawing_state(play):
    """The play's editable drawing (all stages), or None."""
    diagram = play.editor_diagram
    if diagram is None:
        return None
    try:
        return json.loads(diagram.editor_json)
    except ValueError:
        return None


def drawing_role_ids(state):
    """The ids of the roles the drawing's players are."""
    ids = set()
    for stage in (state or {}).get('stages') or [{'objects': (state or {}).get('objects') or []}]:
        for o in stage.get('objects') or []:
            try:
                if o.get('herdRole'):
                    ids.add(int(o['herdRole']))
            except (TypeError, ValueError):
                pass
    return ids


def plays_by_role(team_id):
    """{role id: [plays]} for every play that has the role in its drawing or
    says what it does."""
    from app.models.playbook import Play, PlayAssignment
    found = {}
    for play in Play.query.filter_by(team_organization_id=team_id).all():
        ids = drawing_role_ids(drawing_state(play))
        ids |= {a.position_id for a in PlayAssignment.query.filter_by(play_id=play.id) if a.position_id}
        for role_id in ids:
            found.setdefault(role_id, []).append(play)
    order = lambda p: (p.type != 'offense', p.sort_order is None, p.sort_order or 0, p.name.lower())  # noqa: E731
    return {role_id: sorted(plays, key=order) for role_id, plays in found.items()}
