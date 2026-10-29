"""Playbook helpers: tags and roles typed by name, who has learned what,
someone's usual role, and plays shown inside theory articles."""
import re

from flask import render_template
from markupsafe import Markup

from app import db
from app.models.playbook import (Play, PlayAssignment, PlayerPosition, PlayerUsualRole, PlayLearned, PlayTag,
                                 PlayToLearn)
from app.utils.theory import parse_tags


def in_order():
    """Manual order first (lower = first), then name."""
    return (db.func.coalesce(Play.sort_order, 999999), Play.name, Play.id)


def tags_for(text, team_id):
    """The team's PlayTags for comma-separated names, adding new ones."""
    existing = {t.name.lower(): t for t in PlayTag.query.filter_by(team_organization_id=team_id)}
    tags = []
    for name in parse_tags(text):
        name = name[:30]
        tag = existing.get(name.lower())
        if tag is None:
            tag = PlayTag(name=name, team_organization_id=team_id)
            db.session.add(tag)
            existing[name.lower()] = tag
        if tag not in tags:
            tags.append(tag)
    return tags


def position_for(name, team_id, cache):
    """The team's role called `name` (any case), added if it's new."""
    key = name.lower()
    if key not in cache:
        position = PlayerPosition(name=name, team_organization_id=team_id)
        db.session.add(position)
        cache[key] = position
    return cache[key]


def team_positions(team_id):
    return PlayerPosition.query.filter_by(team_organization_id=team_id).order_by(PlayerPosition.name).all()


def tidy_up(team_id):
    """Drop tags and roles nothing uses any more."""
    for tag in PlayTag.query.filter_by(team_organization_id=team_id):
        if not db.session.query(Play.id).filter(Play.tags.contains(tag)).first():
            db.session.delete(tag)
    for position in team_positions(team_id):
        used = (PlayAssignment.query.filter_by(position_id=position.id).first()
                or PlayerUsualRole.query.filter_by(position_id=position.id).first())
        if not used:
            db.session.delete(position)


def learned_ids(user_id, team_id):
    return {play_id for (play_id,) in db.session.query(PlayLearned.play_id)
            .filter_by(user_id=user_id, team_organization_id=team_id)}


def usual_role(user_id, team_id):
    row = PlayerUsualRole.query.filter_by(user_id=user_id, team_organization_id=team_id).first()
    return row.position if row else None


def to_learn_unlearned(user_id, team_id):
    """[PlayToLearn] the team's been asked to learn and this person hasn't,
    soonest due first (plays in use only)."""
    learned = learned_ids(user_id, team_id)
    rows = (PlayToLearn.query.join(Play, Play.id == PlayToLearn.play_id)
            .filter(PlayToLearn.team_organization_id == team_id, Play.status == 'active').all())
    rows = [r for r in rows if r.play_id not in learned]
    return sorted(rows, key=lambda r: (r.due_date is None, r.due_date, r.created_at))


# ── Plays inside theory articles: [[play:12]] on a line of its own ─────────

PLAY_EMBED = re.compile(r'(?:<p>\s*)?\[\[play:(\d+)\]\](?:\s*</p>)?')


def embed_plays(html, team_id, include_drafts=False):
    """Swap each [[play:<id>]] in rendered markdown for the play's card
    (the team's plays only; drafts only for coaches)."""
    html = str(html)
    ids = {int(i) for i in PLAY_EMBED.findall(html)}
    if not ids:
        return Markup(html)
    query = Play.query.filter(Play.id.in_(ids), Play.team_organization_id == team_id)
    if not include_drafts:
        query = query.filter(Play.status != 'draft')
    plays = {p.id: p for p in query}

    def card(match):
        play = plays.get(int(match.group(1)))
        return render_template('playbook/_embed.html', play=play) if play else ''
    return Markup(PLAY_EMBED.sub(card, html))
