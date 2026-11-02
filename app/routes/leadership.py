"""The Leadership hub: where coaches, captains and team admins share ideas,
articles and footage and talk them over, plus the agenda for the next
leadership meeting and the leadership handbook (app/routes/handbook.py).

Leaders only, and only for teams with the Leadership hub switched on (the
leadership_handbook_enabled setting): for everyone else every page is a 404.
New posts and replies can go to a private Discord channel set up under
Discord settings; never to the team channel.
"""
import threading
from datetime import datetime

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import and_, or_

from app import db, login
from app.models.clip import Clip
from app.models.leadership import LeadershipComment, LeadershipPost, LeadershipRead
from app.routes.handbook import feature_enabled, is_leader
from app.utils.leadership import ago, clean_url, domain, format_timestamp, is_video_link, render_text, start_from, video_for
from app.utils.team_filter import get_current_team_id

bp = Blueprint('leadership', __name__, url_prefix='/leadership')

MAX_TITLE, MAX_TEXT = 200, 20000
bp.add_app_template_filter(ago, 'lh_ago')


@bp.before_request
def check_access():
    if not current_user.is_authenticated:
        return login.unauthorized()
    if not feature_enabled(get_current_team_id()) or not is_leader():
        abort(404)


def hub_on():
    return is_leader() and feature_enabled(get_current_team_id())


def unread_count(user=None, team_id=None):
    """Posts (not archived) with something the leader hasn't seen."""
    user = user or current_user
    team_id = team_id or get_current_team_id()
    if not team_id or not user.is_authenticated:
        return 0
    return (LeadershipPost.query
            .outerjoin(LeadershipRead, and_(LeadershipRead.post_id == LeadershipPost.id,
                                            LeadershipRead.user_id == user.id))
            .filter(LeadershipPost.team_organization_id == team_id, LeadershipPost.status != 'archived',
                    or_(LeadershipRead.id.is_(None), LeadershipRead.seen_at < LeadershipPost.last_activity_at))
            .count())


@bp.app_context_processor
def leadership_nav():
    """leadership_nav() is true when the nav should show the hub;
    leadership_unread() is the badge on it."""
    def unread():
        try:
            return unread_count() if hub_on() else 0
        except Exception:  # never let the badge break a page
            db.session.rollback()
            return 0
    return {'leadership_nav': hub_on, 'leadership_unread': unread}


# ── Helpers ────────────────────────────────────────────────────────────────

def _post_or_404(post_id):
    post = db.session.get(LeadershipPost, post_id)
    if post is None or post.team_organization_id != get_current_team_id():
        abort(404)
    return post


def _can_change(item):
    """Authors change their own posts and replies; team admins (captains
    included) change anyone's."""
    return current_user.is_admin or item.author_id == current_user.id


def _mark_read(post):
    read = LeadershipRead.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    if read is None:
        db.session.add(LeadershipRead(user_id=current_user.id, post_id=post.id, seen_at=datetime.utcnow()))
    else:
        read.seen_at = datetime.utcnow()


def _team_clip(clip_id):
    if not clip_id or not str(clip_id).isdigit():
        return None
    clip = db.session.get(Clip, int(clip_id))
    return clip if clip and clip.team_organization_id == get_current_team_id() else None


def _to_discord(team_id, payload):
    """Post to the leadership channel after the response, so a slow Discord
    never holds up the page. Inline under tests."""
    from app.discord import notify
    app = current_app._get_current_object()
    if app.testing:
        notify.post_leaders(team_id, payload)
        return

    def run():
        with app.app_context():
            try:
                notify.post_leaders(team_id, payload)
            except Exception as e:  # never let a post break anything
                app.logger.warning('Leadership hub Discord post failed: %s', e)
    threading.Thread(target=run, daemon=True).start()


def _announce_post(post):
    from app.discord import messages
    text = (post.body or '')[:300] + ('…' if len(post.body or '') > 300 else '')
    _to_discord(post.team_organization_id, messages.announcement(
        f'{post.kind_label}: {post.title}', f'{text}\n— {post.author_name}'.strip(),
        messages.link('leadership.view', post_id=post.id), messages.GOLD))


def _announce_comment(post, comment):
    from app.discord import messages
    text = comment.body[:300] + ('…' if len(comment.body) > 300 else '')
    _to_discord(post.team_organization_id, messages.announcement(
        f'💬 {comment.author_name} replied: {post.title}', text,
        messages.link('leadership.view', post_id=post.id, _anchor=f'c{comment.id}'), messages.BLUE))


def _form_values(post=None):
    """The post form's values, from the request or the post."""
    if request.method == 'POST':
        f = request.form
        return {'kind': f.get('kind', 'idea'), 'title': (f.get('title') or '').strip(),
                'url': (f.get('url') or '').strip(), 'body': (f.get('body') or '').strip(),
                'start': (f.get('start') or '').strip(), 'clip_id': f.get('clip_id') or '',
                'on_agenda': bool(f.get('on_agenda'))}
    if post is not None:
        return {'kind': post.kind, 'title': post.title, 'url': post.url or '', 'body': post.body or '',
                'start': format_timestamp(post.start_seconds) if post.start_seconds else '',
                'clip_id': post.clip_id or '', 'on_agenda': post.on_agenda}
    return {'kind': request.args.get('kind', 'idea'), 'title': '', 'url': '', 'body': '', 'start': '',
            'clip_id': request.args.get('clip', ''), 'on_agenda': False}


def _apply(post, values):
    """Copy the form onto the post. A list of problems, empty if it's fine."""
    problems = []
    if not values['title']:
        problems.append('Give it a title.')
    url = None
    if values['url']:
        url = clean_url(values['url'])
        if url is None:
            problems.append("That link doesn't look right. Paste the whole address, starting https://")
    if values['start'] and start_from(values['start']) is None:
        problems.append('Start time should look like 1:30 or 1:02:03.')
    if problems:
        return problems
    kind = values['kind'] if values['kind'] in LeadershipPost.KIND_KEYS else 'idea'
    clip = _team_clip(values['clip_id'])
    if kind != 'footage' and (clip or (url and is_video_link(url))):
        kind = 'footage'  # a video link is footage, whatever was picked
    post.kind = kind
    post.title = values['title'][:MAX_TITLE]
    post.url = url
    post.body = values['body'][:MAX_TEXT] or None
    post.clip_id = clip.id if clip else None
    post.start_seconds = start_from(values['start'], url)
    post.on_agenda = values['on_agenda']
    return []


# ── Pages ──────────────────────────────────────────────────────────────────

@bp.route('/')
def index():
    team_id = get_current_team_id()
    kind = request.args.get('kind', '')
    status = request.args.get('status', '')
    q = (request.args.get('q') or '').strip()
    query = LeadershipPost.query.filter_by(team_organization_id=team_id)
    if kind in LeadershipPost.KIND_KEYS:
        query = query.filter_by(kind=kind)
    if status in LeadershipPost.STATUS_KEYS:
        query = query.filter_by(status=status)
    else:
        status = ''
        query = query.filter(LeadershipPost.status != 'archived')
    posts = query.order_by(LeadershipPost.pinned.desc(), LeadershipPost.last_activity_at.desc()).all()
    if q:
        words = q.lower().split()

        def text(p):
            return ' '.join([p.title, p.body or '', p.url or ''] + [c.body for c in p.comments]).lower()
        posts = [p for p in posts if all(w in text(p) for w in words)]

    seen = dict(db.session.query(LeadershipRead.post_id, LeadershipRead.seen_at)
                .filter(LeadershipRead.user_id == current_user.id,
                        LeadershipRead.post_id.in_([p.id for p in posts] or [0])).all())
    unread = {p.id for p in posts if p.id not in seen or seen[p.id] < p.last_activity_at}
    agenda = LeadershipPost.query.filter_by(team_organization_id=team_id, on_agenda=True).count()
    return render_template('leadership/index.html', title='Leadership hub', posts=posts, unread=unread,
                           kind=kind, status=status, q=q, kinds=LeadershipPost.KINDS,
                           statuses=LeadershipPost.STATUSES, agenda_count=agenda, domain=domain)


@bp.route('/new', methods=['GET', 'POST'])
def new():
    values = _form_values()
    clip = _team_clip(values['clip_id'])
    if request.method == 'POST':
        post = LeadershipPost(team_organization_id=get_current_team_id(), author_id=current_user.id)
        problems = _apply(post, values)
        if not problems:
            post.last_activity_at = post.created_at = datetime.utcnow()
            db.session.add(post)
            db.session.flush()
            _mark_read(post)
            db.session.commit()
            _announce_post(post)
            flash('Shared with the leadership group.', 'success')
            return redirect(url_for('leadership.view', post_id=post.id))
        for problem in problems:
            flash(problem, 'danger')
    elif clip is not None:
        values.update(kind='footage', title=clip.title or '')
    return render_template('leadership/form.html', title='Share with leaders', values=values, clip=clip,
                           kinds=LeadershipPost.KINDS, post=None)


@bp.route('/<int:post_id>')
def view(post_id):
    post = _post_or_404(post_id)
    read = LeadershipRead.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    last_seen = read.seen_at if read else None
    _mark_read(post)
    db.session.commit()
    video = video_for(post)
    seekable = bool(video and video['embed_url'])
    return render_template('leadership/post.html', title=post.title, post=post, video=video,
                           render=lambda text: render_text(text, seekable), last_seen=last_seen,
                           can_change=_can_change, domain=domain, format_timestamp=format_timestamp,
                           statuses=LeadershipPost.STATUSES)


@bp.route('/<int:post_id>/edit', methods=['GET', 'POST'])
def edit(post_id):
    post = _post_or_404(post_id)
    if not _can_change(post):
        abort(403)
    values = _form_values(post)
    if request.method == 'POST':
        problems = _apply(post, values)
        if not problems:
            db.session.commit()
            flash('Saved.', 'success')
            return redirect(url_for('leadership.view', post_id=post.id))
        db.session.rollback()
        for problem in problems:
            flash(problem, 'danger')
    return render_template('leadership/form.html', title=f'Edit {post.title}', values=values,
                           clip=_team_clip(values['clip_id']), kinds=LeadershipPost.KINDS, post=post)


@bp.route('/<int:post_id>/delete', methods=['POST'])
def delete(post_id):
    post = _post_or_404(post_id)
    if not _can_change(post):
        abort(403)
    LeadershipRead.query.filter_by(post_id=post.id).delete()
    db.session.delete(post)
    db.session.commit()
    flash('Deleted.', 'success')
    return redirect(url_for('leadership.index'))


@bp.route('/<int:post_id>/comment', methods=['POST'])
def comment(post_id):
    post = _post_or_404(post_id)
    body = (request.form.get('body') or '').strip()[:MAX_TEXT]
    if not body:
        flash('Write something first.', 'warning')
        return redirect(url_for('leadership.view', post_id=post.id, _anchor='reply'))
    reply = LeadershipComment(post_id=post.id, author_id=current_user.id, body=body)
    db.session.add(reply)
    post.last_activity_at = datetime.utcnow()
    db.session.flush()
    _mark_read(post)
    db.session.commit()
    _announce_comment(post, reply)
    return redirect(url_for('leadership.view', post_id=post.id, _anchor=f'c{reply.id}'))


@bp.route('/comment/<int:comment_id>/delete', methods=['POST'])
def delete_comment(comment_id):
    reply = db.session.get(LeadershipComment, comment_id)
    if reply is None or reply.post.team_organization_id != get_current_team_id():
        abort(404)
    if not _can_change(reply):
        abort(403)
    post_id = reply.post_id
    db.session.delete(reply)
    db.session.commit()
    flash('Reply deleted.', 'success')
    return redirect(url_for('leadership.view', post_id=post_id))


@bp.route('/<int:post_id>/set', methods=['POST'])
def set_flag(post_id):
    """Pin, put on the agenda, or change the status: any leader can."""
    post = _post_or_404(post_id)
    what = request.form.get('what')
    if what == 'pinned':
        post.pinned = not post.pinned
    elif what == 'on_agenda':
        post.on_agenda = not post.on_agenda
    elif what == 'status' and request.form.get('status') in LeadershipPost.STATUS_KEYS:
        post.status = request.form['status']
        if post.status == 'archived':
            post.pinned = post.on_agenda = False
    else:
        abort(400)
    db.session.commit()
    back = request.form.get('back')
    if back == 'agenda':
        return redirect(url_for('leadership.agenda'))
    return redirect(url_for('leadership.view', post_id=post.id))


@bp.route('/agenda', methods=['GET', 'POST'])
def agenda():
    """What to talk about at the next leadership meeting."""
    team_id = get_current_team_id()
    posts = (LeadershipPost.query.filter_by(team_organization_id=team_id, on_agenda=True)
             .order_by(LeadershipPost.pinned.desc(), LeadershipPost.created_at).all())
    if request.method == 'POST':
        if request.form.get('action') == 'clear':
            for p in posts:
                p.on_agenda = False
            db.session.commit()
            flash('Agenda cleared, ready for the next meeting.', 'success')
        return redirect(url_for('leadership.agenda'))
    return render_template('leadership/agenda.html', title='Leadership agenda', posts=posts, domain=domain)
