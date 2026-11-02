"""Ask the leaders: players ask the coaches and captains a question, about a
clip, play, theory topic, drill or session (or anything), and follow the
answers under My Questions.

A question is a post in the Leadership hub (app/routes/leadership.py) with
from_player set. Every leader sees it there. The player sees their own
questions and the replies not marked leaders-only, and can follow up.
Only for teams with the Leadership hub switched on; guests can't ask.
Leaders who press "Ask the leaders" go straight to the hub's share form.
"""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db, login
from app.models.leadership import LeadershipComment, LeadershipPost, LeadershipRead
from app.routes.handbook import feature_enabled, is_leader
from app.routes.leadership import MAX_TEXT, MAX_TITLE, _announce_comment, _announce_post, _mark_read
from app.utils import ask_leaders
from app.utils.leadership import render_text, video_for
from app.utils.team_filter import get_current_team_id

bp = Blueprint('questions', __name__, url_prefix='/questions')


def can_ask(user=None):
    user = user or current_user
    return (user.is_authenticated and not user.is_guest and feature_enabled(get_current_team_id()))


@bp.before_request
def check_access():
    if not current_user.is_authenticated:
        return login.unauthorized()
    if not can_ask():
        abort(404)


def my_questions(user=None, team_id=None):
    user = user or current_user
    return (LeadershipPost.query.filter_by(team_organization_id=team_id or get_current_team_id(),
                                           author_id=user.id, from_player=True)
            .order_by(LeadershipPost.last_activity_at.desc()).all())


def unanswered_news(posts, user):
    """The ids of the user's questions with a reply they haven't seen."""
    seen = dict(db.session.query(LeadershipRead.post_id, LeadershipRead.seen_at)
                .filter(LeadershipRead.user_id == user.id,
                        LeadershipRead.post_id.in_([p.id for p in posts] or [0])).all())
    news = set()
    for p in posts:
        last = max((c.created_at for c in p.visible_comments() if c.author_id != user.id), default=None)
        if last and (p.id not in seen or seen[p.id] < last):
            news.add(p.id)
    return news


def unseen_answers(user=None):
    user = user or current_user
    if not user.is_authenticated or user.is_guest or is_leader(user):
        return 0
    team_id = get_current_team_id()
    if not feature_enabled(team_id):
        return 0
    return len(unanswered_news(my_questions(user, team_id), user))


@bp.app_context_processor
def questions_nav():
    """ask_leaders_on(): show "Ask the leaders" buttons; my_questions_nav():
    show My Questions (non-leaders); unseen_answers(): its badge;
    ask_url(kind, id): where the button goes for this user."""
    def on():
        try:
            return can_ask()
        except Exception:
            db.session.rollback()
            return False

    def nav():
        return on() and not is_leader()

    def unseen():
        try:
            return unseen_answers()
        except Exception:  # never let the badge break a page
            db.session.rollback()
            return 0

    def ask_url(kind, subject_id):
        about = f'{kind}:{subject_id}'
        return url_for('leadership.new', about=about) if is_leader() else url_for('questions.ask', about=about)

    def recent(limit=5):
        """(the user's latest questions, the ids with news) for their profile."""
        if not nav():
            return [], set()
        posts = my_questions()
        return posts[:limit], unanswered_news(posts[:limit], current_user)

    return {'ask_leaders_on': on, 'my_questions_nav': nav, 'unseen_answers': unseen, 'ask_url': ask_url,
            'my_recent_questions': recent}


def _mine_or_404(post_id):
    post = db.session.get(LeadershipPost, post_id)
    if (post is None or not post.from_player or post.author_id != current_user.id
            or post.team_organization_id != get_current_team_id()):
        abort(404)
    return post


# ── Pages ──────────────────────────────────────────────────────────────────

@bp.route('/')
def index():
    if is_leader():
        return redirect(url_for('leadership.index', who='players'))
    posts = my_questions()
    subjects = {p.id: ask_leaders.describe(p.subject_type, p.subject_id) if p.subject_type else None
                for p in posts}
    return render_template('questions/index.html', title='My questions', posts=posts,
                           news=unanswered_news(posts, current_user), subjects=subjects)


@bp.route('/ask', methods=['GET', 'POST'])
def ask():
    about = request.values.get('about', '')
    if is_leader():
        return redirect(url_for('leadership.new', about=about or None))
    kind, subject_id = ask_leaders.parse(about)
    row = ask_leaders.find(kind, subject_id)
    subject = ask_leaders.describe(kind, subject_id, row) if row is not None else None
    title = (request.form.get('title') or '').strip()
    body = (request.form.get('body') or '').strip()
    if request.method == 'POST':
        if not body:
            flash('Write your question first.', 'danger')
        else:
            post = LeadershipPost(team_organization_id=get_current_team_id(), author_id=current_user.id,
                                  kind='question', from_player=True, body=body[:MAX_TEXT],
                                  title=(title or (f"About {subject['title']}" if subject else body))[:MAX_TITLE])
            if subject is not None:
                post.subject_type, post.subject_id = kind, row.id
                if kind == 'clip':
                    post.clip_id = row.id
            post.last_activity_at = post.created_at = datetime.utcnow()
            db.session.add(post)
            db.session.flush()
            _mark_read(post)
            db.session.commit()
            _announce_post(post)
            flash('Sent to the coaches and captains. Their answers show up here.', 'success')
            return redirect(url_for('questions.view', post_id=post.id))
    elif subject is not None:
        title = f"About {subject['title']}"
    return render_template('questions/ask.html', title='Ask the leaders', subject=subject,
                           about=about if subject else '', values={'title': title, 'body': body})


@bp.route('/<int:post_id>')
def view(post_id):
    post = _mine_or_404(post_id)
    _mark_read(post)
    db.session.commit()
    subject = ask_leaders.describe(post.subject_type, post.subject_id) if post.subject_type else None
    video = video_for(post) if post.clip_id and subject else None  # only while they can still see the clip
    seekable = bool(video and video['embed_url'])
    return render_template('questions/view.html', title=post.title, post=post, subject=subject, video=video,
                           comments=post.visible_comments(), render=lambda text: render_text(text, seekable))


@bp.route('/<int:post_id>/reply', methods=['POST'])
def reply(post_id):
    post = _mine_or_404(post_id)
    body = (request.form.get('body') or '').strip()[:MAX_TEXT]
    if not body:
        flash('Write something first.', 'warning')
        return redirect(url_for('questions.view', post_id=post.id))
    comment = LeadershipComment(post_id=post.id, author_id=current_user.id, body=body)
    db.session.add(comment)
    post.last_activity_at = datetime.utcnow()
    if post.status != 'open':
        post.status = 'open'  # a follow-up re-opens it
    db.session.flush()
    _mark_read(post)
    db.session.commit()
    _announce_comment(post, comment)
    return redirect(url_for('questions.view', post_id=post.id, _anchor=f'c{comment.id}'))


@bp.route('/<int:post_id>/delete', methods=['POST'])
def delete(post_id):
    """A player can take a question back until someone has answered it."""
    post = _mine_or_404(post_id)
    if post.comments and any(c.author_id != current_user.id for c in post.comments):
        flash("It's been answered, so it stays. You can follow up instead.", 'warning')
        return redirect(url_for('questions.view', post_id=post.id))
    LeadershipRead.query.filter_by(post_id=post.id).delete()
    db.session.delete(post)
    db.session.commit()
    flash('Question deleted.', 'success')
    return redirect(url_for('questions.index'))
