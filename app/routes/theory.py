# app/routes/theory.py
import re

from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.clip import Clip
from app.models.drill import SavedDrill
from app.models.theory import TheorySection, TheoryTopic
from app.routes.clip.helpers import sees_hidden_clips
from app.forms.theory import TheorySectionForm, TheoryTopicForm
from app.utils.utils import coach_required
from app.utils.team_filter import get_current_team_id

bp = Blueprint('theory', __name__, url_prefix='/theory')


def team_sections(team_id):
    return (TheorySection.query.filter_by(team_organization_id=team_id)
            .order_by(db.func.coalesce(TheorySection.order, 999999), TheorySection.name).all())


def section_topics(section, team_id):
    return (section.topics.filter_by(team_organization_id=team_id)
            .order_by(db.func.coalesce(TheoryTopic.order, 999999), TheoryTopic.name).all())


def contents(team_id):
    """[(section, [topics])] in reading order."""
    return [(s, section_topics(s, team_id)) for s in team_sections(team_id)]


def plain(markdown_text):
    """Roughly the words of some Markdown, for searching and snippets."""
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', markdown_text or '')  # images
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)            # links keep their words
    text = re.sub(r'[#>*_`|~-]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def search(groups, q):
    """Topics matching every word of q, best first (title over text)."""
    words = q.lower().split()
    scored = []
    for section, topics in groups:
        for t in topics:
            title, body, where = t.name.lower(), plain(t.content).lower(), section.name.lower()
            if all(w in title or w in body or w in where for w in words):
                score = sum(5 * (w in title) + 2 * (w in where) + (w in body) for w in words)
                scored.append((-score, t.name.lower(), t, section))
    return [(t, section) for _, _, t, section in sorted(scored, key=lambda r: r[:2])]


@bp.route('/')
@login_required
def index():
    team_id = get_current_team_id()
    groups = contents(team_id)
    q = (request.args.get('q') or '').strip()
    results = search(groups, q) if q else None
    first = next((topics[0] for _, topics in groups if topics), None)
    return render_template('theory/index.html', groups=groups, q=q, results=results, first=first,
                           snippet=lambda t: plain(t.content)[:160])


@bp.route('/section/<string:slug>')
@login_required
def section(slug):
    team_id = get_current_team_id()
    section = TheorySection.query.filter_by(slug=slug, team_organization_id=team_id).first_or_404()
    groups = contents(team_id)
    topics = next(topics for s, topics in groups if s.id == section.id)
    return render_template('theory/section.html', section=section, topics=topics, groups=groups,
                           snippet=lambda t: plain(t.content)[:160])


@bp.route('/topic/<int:topic_id>')
@login_required
def topic(topic_id):
    team_id = get_current_team_id()
    topic = TheoryTopic.query.filter_by(id=topic_id, team_organization_id=team_id).first_or_404()
    groups = contents(team_id)
    # Previous / next run through the whole guide, section by section
    reading = [t for _, topics in groups for t in topics]
    i = next((n for n, t in enumerate(reading) if t.id == topic.id), 0)
    clips = [c for c in topic.clips if c.team_organization_id == team_id
             and (sees_hidden_clips() or not c.is_hidden)]
    drills = [d for d in topic.related_drills if d.team_organization_id == team_id]
    return render_template('theory/topic.html', topic=topic, groups=groups, title=topic.name,
                           prev_topic=reading[i - 1] if i > 0 else None,
                           next_topic=reading[i + 1] if i + 1 < len(reading) else None,
                           clips=clips, drills=drills)


# Section Management
@bp.route('/add_section', methods=['GET', 'POST'])
@login_required
@coach_required
def add_section():
    form = TheorySectionForm()
    if form.validate_on_submit():
        
        section = TheorySection(
            name=form.name.data,
            slug=TheorySection.free_slug(get_current_team_id(), form.name.data),
            description=form.description.data,
            order=form.order.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        db.session.add(section)
        try:
            db.session.commit()
            flash(f'Section "{section.name}" has been created!', 'success')
            return redirect(url_for('theory.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating section: {str(e)}', 'danger')
    
    return render_template('theory/section_form.html', form=form, title='Add Section')

@bp.route('/edit_section/<int:section_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_section(section_id):
    section = TheorySection.query.filter_by(
        id=section_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = TheorySectionForm(obj=section)
    
    if form.validate_on_submit():
        section.name = form.name.data
        section.description = form.description.data
        section.order = form.order.data
        
        try:
            db.session.commit()
            flash(f'Section "{section.name}" has been updated!', 'success')
            return redirect(url_for('theory.section', slug=section.slug))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating section: {str(e)}', 'danger')
    
    return render_template('theory/section_form.html', form=form, section=section, title='Edit Section')

@bp.route('/delete_section/<int:section_id>', methods=['POST'])
@login_required
@coach_required
def delete_section(section_id):
    section = TheorySection.query.filter_by(
        id=section_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    name = section.name
    
    try:
        db.session.delete(section)
        db.session.commit()
        flash(f'Section "{name}" has been deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting section: {str(e)}', 'danger')
    
    return redirect(url_for('theory.index'))

# Topic Management
def _offer_links(form):
    """The team's drills and clips to link a topic to."""
    team_id = get_current_team_id()
    form.drill_rows = SavedDrill.query.filter_by(team_organization_id=team_id).order_by(SavedDrill.title).all()
    form.clip_rows = Clip.query.filter_by(team_organization_id=team_id).order_by(Clip.created_at.desc()).all()
    form.related_drills.choices = [(d.id, d.title) for d in form.drill_rows]
    form.clips.choices = [(c.id, c.title or f'Clip {c.id}') for c in form.clip_rows]


def _save_links(topic, form):
    drills, clips = set(form.related_drills.data or []), set(form.clips.data or [])
    topic.related_drills = [d for d in form.drill_rows if d.id in drills]
    topic.clips = [c for c in form.clip_rows if c.id in clips]


@bp.route('/add_topic', methods=['GET', 'POST'])
@login_required
@coach_required
def add_topic():
    form = TheoryTopicForm()
    _offer_links(form)
    if request.method == 'GET' and request.args.get('section', type=int):
        form.section_id.data = request.args.get('section', type=int)

    # Only show sections from current team
    form.section_id.choices = [(s.id, s.name) for s in TheorySection.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(TheorySection.name).all()]
    
    if form.validate_on_submit():
        # Verify section belongs to current team
        section = TheorySection.query.filter_by(
            id=form.section_id.data,
            team_organization_id=get_current_team_id()
        ).first()
        
        if not section:
            flash('Invalid section selected.', 'danger')
            return render_template('theory/topic_form.html', form=form, title='Add Topic')
        
        
        topic = TheoryTopic(
            name=form.name.data,
            content=form.content.data,
            section_id=form.section_id.data,
            order=form.order.data,
            created_by=current_user.id,
            image_url=form.image_url.data,  # Use the URL directly
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        _save_links(topic, form)

        db.session.add(topic)
        try:
            db.session.commit()
            flash(f'Topic "{topic.name}" has been created!', 'success')
            return redirect(url_for('theory.topic', topic_id=topic.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating topic: {str(e)}', 'danger')
    
    return render_template('theory/topic_form.html', form=form, title='Add Topic')

@bp.route('/edit_topic/<int:topic_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_topic(topic_id):
    topic = TheoryTopic.query.filter_by(
        id=topic_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = TheoryTopicForm(obj=topic)
    _offer_links(form)
    if request.method == 'GET':
        form.related_drills.data = [d.id for d in topic.related_drills]
        form.clips.data = [c.id for c in topic.clips]

    # Only show sections from current team
    form.section_id.choices = [(s.id, s.name) for s in TheorySection.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(TheorySection.name).all()]
    
    if form.validate_on_submit():
        # Verify section belongs to current team
        section = TheorySection.query.filter_by(
            id=form.section_id.data,
            team_organization_id=get_current_team_id()
        ).first()
        
        if not section:
            flash('Invalid section selected.', 'danger')
            return render_template('theory/topic_form.html', form=form, topic=topic, title='Edit Topic')
        
        topic.name = form.name.data
        topic.content = form.content.data
        topic.section_id = form.section_id.data
        topic.order = form.order.data
        topic.image_url = form.image_url.data  # Update the URL directly
        
        _save_links(topic, form)

        try:
            db.session.commit()
            flash(f'Topic "{topic.name}" has been updated!', 'success')
            return redirect(url_for('theory.topic', topic_id=topic.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating topic: {str(e)}', 'danger')
    
    return render_template('theory/topic_form.html', form=form, topic=topic, title='Edit Topic')

@bp.route('/delete_topic/<int:topic_id>', methods=['POST'])
@login_required
@coach_required
def delete_topic(topic_id):
    topic = TheoryTopic.query.filter_by(
        id=topic_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    section_slug = topic.section.slug
    name = topic.name
    
    try:
        db.session.delete(topic)
        db.session.commit()
        flash(f'Topic "{name}" has been deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting topic: {str(e)}', 'danger')
    
    return redirect(url_for('theory.section', slug=section_slug))


# Error Handlers
@bp.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error_message='Page not found.'), 404

@bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('error.html', error_message='Something went wrong. Please try again.'), 500
