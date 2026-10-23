"""Everything that belongs to one team: for a team's own data download and
for deleting a team.

Works from the table definitions, so new tables are covered without editing
this file: a table with team_organization_id (or a foreign key to the team)
holds the team's rows directly; any other table holds the rows that point
at one of the team's rows (association tables, player feedback, ...).
Rows shared between teams (team_organization_id empty) are never included.
"""
import base64
import csv
import io
import json
import zipfile
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import or_, select

from app import db

# Never put these in a download: passwords, sign-in secrets, and live links
# that would let someone join the team
SECRET_COLUMNS = {
    'user': {'password_hash', 'totp_secret', 'totp_recovery_codes'},
    'invite_token': {'token'},
    'team_signup_invite': {'token'},
}


def team_conditions(team_id):
    """{table: where-clause selecting this team's rows}, parents first."""
    conditions = {}
    for table in db.metadata.sorted_tables:  # parents before children
        if table.name == 'team_organization':
            conditions[table] = table.c.id == team_id
        elif 'team_organization_id' in table.c:
            conditions[table] = table.c.team_organization_id == team_id
        else:
            links = []
            for fk in table.foreign_keys:
                parent = fk.column.table
                if parent is table or parent not in conditions:
                    continue
                if parent.name == 'team_organization':
                    links.append(fk.parent == team_id)
                else:
                    links.append(fk.parent.in_(select(fk.column).where(conditions[parent])))
            if links:
                conditions[table] = or_(*links)
    return conditions


def members_only_here(team_id):
    """The team's members who aren't on any other team (deleting the team
    deletes their accounts)."""
    from app.models.team_membership import TeamMembership
    from app.models.user import User
    return (User.query.filter(User.memberships.any(TeamMembership.team_organization_id == team_id),
                              ~User.memberships.any(TeamMembership.team_organization_id != team_id),
                              User.is_superadmin.is_(False)).all())


def delete_team_data(team_id):
    """Delete every row that belongs to a team, children before parents,
    including the team itself. Superadmins, and members who are also on
    another team, are moved off it rather than deleted. The caller commits."""
    from app.models.user import User

    # Accounts deleted with the team are the ones whose home is the team, so
    # first move everyone who stays to another team they're on (or none)
    for user in User.query.filter_by(team_organization_id=team_id).all():
        others = [m for m in user.memberships if m.team_organization_id != team_id]
        if others or user.is_superadmin:
            user.leave_team(team_id)
    db.session.flush()
    deleted = {}
    for table, condition in reversed(list(team_conditions(team_id).items())):
        result = db.session.execute(table.delete().where(condition))
        if result.rowcount:
            deleted[table.name] = result.rowcount
    return deleted


def _plain(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'base64': base64.b64encode(bytes(value)).decode('ascii')}
    return value


def team_tables(team_id):
    """{table name: [row dicts]} of the team's data, secrets left out."""
    tables = {}
    for table, condition in team_conditions(team_id).items():
        if table.name == 'user':
            # Every member's account, not only those whose home team it is
            membership = db.metadata.tables['team_membership']
            condition = table.c.id.in_(select(membership.c.user_id)
                                       .where(membership.c.team_organization_id == team_id))
        hidden = SECRET_COLUMNS.get(table.name, set())
        rows = db.session.execute(table.select().where(condition)).mappings().all()
        if rows:
            tables[table.name] = [{k: _plain(v) for k, v in row.items() if k not in hidden}
                                  for row in rows]
    return tables


README = """{team} - data download from Ultimate Coach
Made {made} UTC by {user}.

json/  every table as JSON, exactly as stored (images as base64)
csv/   the same tables to open in a spreadsheet

Passwords, sign-in secrets and live invite links are left out.
Each row's id matches the ids other tables refer to (e.g. player_id).
"""


def team_export_zip(team, user):
    """The team's data as a zip (bytes)."""
    tables = team_tables(team.id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('README.txt', README.format(team=team.name, user=user.username,
                                               made=datetime.utcnow().strftime('%Y-%m-%d %H:%M')))
        for name, rows in tables.items():
            z.writestr(f'json/{name}.json', json.dumps(rows, indent=2, default=str))
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ('(image)' if isinstance(v, dict) and 'base64' in v
                                     else json.dumps(v) if isinstance(v, (list, dict)) else v)
                                 for k, v in row.items()})
            z.writestr(f'csv/{name}.csv', out.getvalue())
    return buffer.getvalue()
