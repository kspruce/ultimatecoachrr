"""Playbook overhaul: concepts move to Theory; status, call and signal;
links to theory, drills and clips; learning plays

Revision ID: d7f9b1c3e5a7
Revises: c3e5a7b9d1f4
Create Date: 2026-10-29 12:00:00.000000

- play: status (existing plays stay "In use"), call, signal, updated_by;
  image_url up to 500 characters (uploaded photos and long links)
- play_assignment.order, so a play's roles keep the order they're written in
- team concepts (formation rows) become Theory topics in an "Our system"
  section of each team that has any (published, as they were visible to
  everyone); their plays are linked to the new topic and the formation
  keeps moved_to_topic_id so old links redirect. Nothing is deleted.
- position instructions left behind by deleted plays are removed
- play_topic / play_drill / play_clip link tables
- play_learned, play_to_learn (who's learned which play; plays to learn)
"""
import re
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from slugify import slugify


revision = 'd7f9b1c3e5a7'
down_revision = 'c3e5a7b9d1f4'
branch_labels = None
depends_on = None


def _embed_url(html):
    if not html:
        return None
    m = re.search(r'src=["\']([^"\']+)["\']', html)
    if m:
        return m.group(1)
    html = html.strip()
    return html if html.startswith('http') else None


def _concepts_to_theory():
    bind = op.get_bind()
    meta = sa.MetaData()
    formation = sa.Table('formation', meta, autoload_with=bind)
    section = sa.Table('theory_section', meta, autoload_with=bind)
    topic = sa.Table('theory_topic', meta, autoload_with=bind)
    play = sa.Table('play', meta, autoload_with=bind)
    links = sa.Table('play_topic_association', meta, autoload_with=bind)

    rows = bind.execute(sa.select(formation).where(formation.c.team_organization_id.isnot(None))
                        .order_by(formation.c.team_organization_id, formation.c.type.desc(), formation.c.name)).all()
    now = datetime.utcnow()
    section_for = {}
    for f in rows:
        team_id = f.team_organization_id
        if team_id not in section_for:
            taken = {s for (s,) in bind.execute(sa.select(section.c.slug).where(
                section.c.team_organization_id == team_id))}
            slug, n = 'our-system', 2
            while slug in taken:
                slug, n = f'our-system-{n}', n + 1
            last = bind.execute(sa.select(sa.func.max(section.c.order)).where(
                section.c.team_organization_id == team_id)).scalar()
            result = bind.execute(section.insert().values(
                name='Our system', slug=slug, order=(last or 0) + 1, team_organization_id=team_id,
                description='How we play: the ideas our plays are built on. (Moved here from the playbook.)',
                created_at=now, updated_at=now))
            section_for[team_id] = [result.inserted_primary_key[0], 0]
        section_id, order = section_for[team_id]
        section_for[team_id][1] = order + 1

        parts = []
        side = {'offense': 'An offence concept.', 'defense': 'A defence concept.'}.get(f.type)
        if side:
            parts.append(f'*{side}*')
        if f.description:
            parts.append(f.description.strip())
        if f.imgur_url:
            parts.append(f'![{f.name}]({f.imgur_url})')
        url = _embed_url(f.ultiplay_embed)
        if url and url.startswith('https://'):
            parts.append(f'[Watch the animation]({url})')
        result = bind.execute(topic.insert().values(
            section_id=section_id, name=f.name[:100], slug=slugify(f.name)[:100], content='\n\n'.join(parts),
            order=order + 1, published=True, created_by=f.created_by, team_organization_id=team_id,
            created_at=f.created_at or now, updated_at=f.updated_at or now))
        topic_id = result.inserted_primary_key[0]
        bind.execute(formation.update().where(formation.c.id == f.id).values(moved_to_topic_id=topic_id))
        for (play_id,) in bind.execute(sa.select(play.c.id).where(play.c.formation_id == f.id)):
            bind.execute(links.insert().values(play_id=play_id, topic_id=topic_id))


def upgrade():
    with op.batch_alter_table('play') as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=10), nullable=False, server_default='active'))
        batch_op.add_column(sa.Column('call', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('signal', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('updated_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_play_updated_by_user', 'user', ['updated_by'], ['id'])
        batch_op.alter_column('image_url', existing_type=sa.String(length=255), type_=sa.String(length=500))

    with op.batch_alter_table('play_assignment') as batch_op:
        batch_op.add_column(sa.Column('order', sa.Integer(), nullable=True))

    with op.batch_alter_table('formation') as batch_op:
        batch_op.add_column(sa.Column('moved_to_topic_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_formation_moved_to_topic', 'theory_topic', ['moved_to_topic_id'], ['id'],
                                    ondelete='SET NULL')

    op.create_table(
        'play_topic_association',
        sa.Column('play_id', sa.Integer(), sa.ForeignKey('play.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('topic_id', sa.Integer(), sa.ForeignKey('theory_topic.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'play_drill_association',
        sa.Column('play_id', sa.Integer(), sa.ForeignKey('play.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('drill_id', sa.Integer(), sa.ForeignKey('saved_drill.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'play_clip_association',
        sa.Column('play_id', sa.Integer(), sa.ForeignKey('play.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('clip_id', sa.Integer(), sa.ForeignKey('clip.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'play_learned',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('play_id', sa.Integer(), sa.ForeignKey('play.id', ondelete='CASCADE'), nullable=False),
        sa.Column('learned_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'play_id', name='uq_play_learned_user_play'),
    )
    for column in ('team_organization_id', 'user_id', 'play_id'):
        op.create_index(f'ix_play_learned_{column}', 'play_learned', [column])
    op.create_table(
        'play_to_learn',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_organization_id', sa.Integer(), sa.ForeignKey('team_organization.id'), nullable=False),
        sa.Column('play_id', sa.Integer(), sa.ForeignKey('play.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('assigned_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_play_to_learn_team_organization_id', 'play_to_learn', ['team_organization_id'])

    # Instructions whose play was deleted (deleting a play didn't take them with it)
    op.execute('DELETE FROM play_assignment WHERE play_id IS NULL OR play_id NOT IN (SELECT id FROM play)')

    _concepts_to_theory()


def downgrade():
    # The topics made from concepts stay in Theory; the concepts are untouched
    op.drop_index('ix_play_to_learn_team_organization_id', table_name='play_to_learn')
    op.drop_table('play_to_learn')
    for column in ('team_organization_id', 'user_id', 'play_id'):
        op.drop_index(f'ix_play_learned_{column}', table_name='play_learned')
    op.drop_table('play_learned')
    op.drop_table('play_clip_association')
    op.drop_table('play_drill_association')
    op.drop_table('play_topic_association')
    with op.batch_alter_table('formation') as batch_op:
        batch_op.drop_constraint('fk_formation_moved_to_topic', type_='foreignkey')
        batch_op.drop_column('moved_to_topic_id')
    with op.batch_alter_table('play_assignment') as batch_op:
        batch_op.drop_column('order')
    with op.batch_alter_table('play') as batch_op:
        batch_op.drop_constraint('fk_play_updated_by_user', type_='foreignkey')
        batch_op.drop_column('updated_by')
        batch_op.drop_column('signal')
        batch_op.drop_column('call')
        batch_op.drop_column('status')
        batch_op.alter_column('image_url', existing_type=sa.String(length=500), type_=sa.String(length=255))
