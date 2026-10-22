"""Leadership handbook: pages for captains, coaches and admins on how we
lead, coach and build the team. Only for teams with the Leadership handbook
feature switched on, and only for leaders: for everyone else every page here
is a 404.

Pages are loaded with `flask import-handbook` and edited here.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db, login
from app.models.handbook import HandbookPage
from app.models.team_settings import TeamSettings
from app.utils.handbook import SECTIONS, SECTION_TITLES, clean_html, link_pages, text_of
from app.utils.team_filter import get_current_team_id

bp = Blueprint('handbook', __name__, url_prefix='/handbook')


def feature_enabled(team_id):
    if not team_id:
        return False
    settings = TeamSettings.query.filter_by(team_id=team_id).first()
    return bool(settings and settings.leadership_handbook_enabled)


def is_leader(user=None):
    """Coaches, captains and admins (captains are team admins, so is_coach
    covers all three)."""
    user = user or current_user
    return user.is_authenticated and user.is_coach


def team_pages(team_id):
    return (HandbookPage.query.filter_by(team_organization_id=team_id)
            .order_by(HandbookPage.position, HandbookPage.id).all())


def grouped(pages):
    """[(key, title, blurb, [pages])] for the sections that have pages."""
    groups = []
    for key, title, blurb in SECTIONS:
        in_section = [p for p in pages if p.section == key]
        if in_section:
            groups.append((key, title, blurb, in_section))
    return groups


def page_url(slug):
    return url_for('handbook.page', slug=slug)


@bp.before_request
def check_access():
    if not current_user.is_authenticated:
        return login.unauthorized()
    if not feature_enabled(get_current_team_id()) or not is_leader():
        abort(404)


@bp.app_context_processor
def handbook_nav():
    """handbook_nav() is true when the nav should show the handbook."""
    def show():
        return is_leader() and feature_enabled(get_current_team_id())
    return {'handbook_nav': show}


@bp.route('/')
def index():
    pages = team_pages(get_current_team_id())
    q = (request.args.get('q') or '').strip()
    results = None
    if q:
        words = q.lower().split()
        scored = []
        for p in pages:
            title, lead, body = p.title.lower(), (p.lead or '').lower(), text_of(p.body_html).lower()
            if all(w in title or w in lead or w in body for w in words):
                score = sum(5 * (w in title) + 2 * (w in lead) + (w in body) for w in words)
                scored.append((score, p.position, p))
        results = [p for _, _, p in sorted(scored, key=lambda t: (-t[0], t[1]))]
    return render_template('handbook/index.html', title='Leadership handbook', groups=grouped(pages), pages=pages, q=q,
                           results=results, section_titles=SECTION_TITLES)


@bp.route('/<slug>')
def page(slug):
    pages = team_pages(get_current_team_id())
    current = next((p for p in pages if p.slug == slug), None)
    if current is None:
        abort(404)
    i = pages.index(current)
    section_first = next(p for p in pages if p.section == current.section)
    return render_template('handbook/page.html', page=current, title=current.title, groups=grouped(pages),
                           body=link_pages(current.body_html, page_url),
                           prev_page=pages[i - 1] if i > 0 else None,
                           next_page=pages[i + 1] if i + 1 < len(pages) else None,
                           section_title=SECTION_TITLES.get(current.section, current.section),
                           section_first=section_first)


@bp.route('/<slug>/edit', methods=['GET', 'POST'])
def edit(slug):
    current = HandbookPage.query.filter_by(team_organization_id=get_current_team_id(), slug=slug).first_or_404()
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        if not title:
            flash('A page needs a title.', 'danger')
        else:
            current.title = title[:200]
            current.lead = (request.form.get('lead') or '').strip()
            current.body_html = clean_html(request.form.get('body_html') or '')
            db.session.commit()
            flash('Page saved.', 'success')
            return redirect(url_for('handbook.page', slug=current.slug))
    return render_template('handbook/edit.html', page=current, title=f'Edit {current.title}', groups=grouped(team_pages(current.team_organization_id)),
                           section_title=SECTION_TITLES.get(current.section, current.section))
