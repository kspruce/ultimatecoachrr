# app/routes/theory.py
"""Theory hub: sections of topics for players to read, written by the
coaches (anyone with coach rights, captains included). Every page is a 404
when the team has Theory switched off in its feature settings.

Topics can be drafts (only coaches see them), carry an uploaded or linked
cover photo, YouTube/Vimeo videos, tags and linked drills. Players mark
topics as read; coaches can ask the team to read a topic by a date and see
who has.
"""
import base64
import hashlib
from collections import defaultdict
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, jsonify, make_response, redirect, render_template,
                   request, url_for)
from flask_login import current_user

from app import db, login
from app.forms.theory import TheoryAssignmentForm, TheorySectionForm, TheoryTopicForm
from app.models.clip import Clip
from app.models.drill import SavedDrill
from app.routes.clip.helpers import sees_hidden_clips
from app.models.team_settings import TeamSettings
from app.models.theory import (TheoryAssignment, TheoryImage, TheoryRead, TheorySection, TheoryTag,
                               TheoryTopic, TheoryVideo, unique_slug, video_embed_url)
from app.utils import theory as hub
from app.utils import theory_import
from app.utils.team_filter import get_current_team_id

bp = Blueprint('theory', __name__, url_prefix='/theory')

MAX_VIDEOS = 10


def playbook_on(team_id):
    settings = TeamSettings.query.filter_by(team_id=team_id).first() if team_id else None
    return settings is None or bool(settings.playbook_enabled)


def team_plays(team_id):
    """The playbook plays a topic can link to or show (drafts for coaches)."""
    from app.models.playbook import Play
    if not playbook_on(team_id):
        return []
    query = Play.query.filter_by(team_organization_id=team_id)
    if not can_edit():
        query = query.filter(Play.status != 'draft')
    return query.order_by(Play.type.desc(), Play.name).all()


def render_content(text, team_id):
    """A topic's markdown as HTML, with any [[play:<id>]] shown as that play."""
    from app.utils.playbook import embed_plays
    html = current_app.jinja_env.filters['markdown'](text or '')
    return embed_plays(html, team_id, include_drafts=can_edit()) if playbook_on(team_id) else html


def feature_enabled(team_id):
    settings = TeamSettings.query.filter_by(team_id=team_id).first() if team_id else None
    return settings is None or bool(settings.theory_enabled)


def can_edit():
    return current_user.is_authenticated and current_user.is_coach


def coach_only():
    if not can_edit():
        abort(403)


def wants_json():
    return (request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.accept_mimetypes.best == 'application/json')


@bp.before_request
def check_access():
    if not current_user.is_authenticated:
        return login.unauthorized()
    if not feature_enabled(get_current_team_id()):
        abort(404)


@bp.context_processor
def theory_context():
    return {'can_edit': can_edit()}


def in_order(model):
    """Order by `order` with unnumbered rows last (Postgres and SQLite sort
    NULLs differently), then by when they were added."""
    return (model.order.is_(None), model.order, model.id)


def team_sections(team_id):
    return TheorySection.query.filter_by(team_organization_id=team_id).order_by(*in_order(TheorySection)).all()


def visible_topics(query):
    """Drafts only for coaches."""
    return query if can_edit() else query.filter(TheoryTopic.published.is_(True))


def section_topics(section):
    return visible_topics(section.topics.filter_by(team_organization_id=section.team_organization_id)) \
        .order_by(*in_order(TheoryTopic)).all()


def topic_or_404(topic_id):
    topic = TheoryTopic.query.filter_by(id=topic_id, team_organization_id=get_current_team_id()).first_or_404()
    if not topic.published and not can_edit():
        abort(404)
    return topic


def renumber(rows):
    for i, row in enumerate(rows, start=1):
        row.order = i


def move(rows, row, direction):
    """Swap row with its neighbour in `rows` (already in order)."""
    i = rows.index(row)
    j = i - 1 if direction == 'up' else i + 1
    if 0 <= j < len(rows):
        rows[i], rows[j] = rows[j], rows[i]
    renumber(rows)


# ── Reading ────────────────────────────────────────────────────────────────

@bp.route('/')
def index():
    team_id = get_current_team_id()
    sections = team_sections(team_id)
    topics = hub.ordered_topics(team_id, include_drafts=can_edit())
    published = [t for t in topics if t.published]
    read = hub.read_ids(current_user.id, team_id)

    by_section = defaultdict(list)
    for t in topics:
        by_section[t.section_id].append(t)

    q = (request.args.get('q') or '').strip()
    tag = (request.args.get('tag') or '').strip()
    results = None
    if q or tag:
        pool = [t for t in topics if not tag or any(x.name.lower() == tag.lower() for x in t.tags)]
        results = hub.search(pool, q) if q else pool

    # Searching finds the playbook's plays too
    play_results = []
    if q and not tag:
        from app.routes.playbook import search as search_plays
        play_results = search_plays([p for p in team_plays(team_id) if not p.is_retired], q)

    tag_names = sorted({x.name for t in topics for x in t.tags}, key=str.lower)

    assigned = []
    for a in TheoryAssignment.query.filter_by(team_organization_id=team_id).all():
        if a.topic.published or can_edit():
            assigned.append(a)
    assigned.sort(key=lambda a: (a.due_date is None, a.due_date, a.created_at))
    readers_count = len(hub.team_readers(team_id)) if can_edit() and assigned else 0
    read_counts = {}
    if can_edit() and assigned:
        ids = [a.topic_id for a in assigned]
        for topic_id, n in (db.session.query(TheoryRead.topic_id, db.func.count(TheoryRead.id))
                            .filter(TheoryRead.topic_id.in_(ids)).group_by(TheoryRead.topic_id)):
            read_counts[topic_id] = n

    recent = sorted(published, key=lambda t: t.last_edited_at or datetime.min, reverse=True)[:3]
    return render_template('theory/index.html', title='Theory',
                           sections=sections, by_section=by_section, read=read,
                           q=q, tag=tag, results=results, tag_names=tag_names, play_results=play_results,
                           snippet=hub.snippet,
                           continue_topic=hub.continue_reading(current_user.id, team_id, published, read),
                           assigned=assigned, read_counts=read_counts, readers_count=readers_count,
                           recent=recent, drafts=[t for t in topics if not t.published],
                           total_published=len(published),
                           total_read=len([t for t in published if t.id in read]))


@bp.route('/section/<string:slug>')
def section(slug):
    team_id = get_current_team_id()
    section = TheorySection.query.filter_by(slug=slug, team_organization_id=team_id).first_or_404()
    topics = section_topics(section)
    all_sections = team_sections(team_id)
    counts = dict(db.session.query(TheoryTopic.section_id, db.func.count(TheoryTopic.id))
                  .filter(TheoryTopic.team_organization_id == team_id,
                          *([] if can_edit() else [TheoryTopic.published.is_(True)]))
                  .group_by(TheoryTopic.section_id).all())
    return render_template('theory/section.html', title=section.name, section=section, topics=topics,
                           all_sections=all_sections, counts=counts,
                           read=hub.read_ids(current_user.id, team_id), plain_text=hub.plain_text)


@bp.route('/topic/<int:topic_id>')
def topic(topic_id):
    topic = topic_or_404(topic_id)
    topics = section_topics(topic.section)
    i = next((n for n, t in enumerate(topics) if t.id == topic.id), 0)
    read = hub.read_ids(current_user.id, topic.team_organization_id)
    readers = None
    if can_edit():
        readers = (TheoryRead.query.filter_by(topic_id=topic.id).count(), len(hub.team_readers(topic.team_organization_id)))
    return render_template('theory/topic.html', title=topic.name, topic=topic,
                           section_topics=topics, current_idx=i,
                           prev_topic=topics[i - 1] if i > 0 else None,
                           next_topic=topics[i + 1] if i + 1 < len(topics) else None,
                           is_read=topic.id in read, read=read, readers=readers, clips=visible_clips(topic),
                           body=render_content(topic.content, topic.team_organization_id),
                           plays=[p for p in team_plays(topic.team_organization_id) if p in topic.plays])


@bp.route('/topic/<int:topic_id>/read', methods=['POST'])
def mark_read(topic_id):
    topic = topic_or_404(topic_id)
    row = TheoryRead.query.filter_by(user_id=current_user.id, topic_id=topic.id).first()
    want = request.form.get('read', '1') != '0'
    if want and row is None:
        db.session.add(TheoryRead(user_id=current_user.id, topic_id=topic.id,
                                  team_organization_id=topic.team_organization_id))
    elif not want and row is not None:
        db.session.delete(row)
    db.session.commit()
    if wants_json():
        return jsonify({'read': want})
    if want:
        # On to the next topic in the section, if there is one
        topics = section_topics(topic.section)
        ids = [t.id for t in topics]
        if topic.id in ids and ids.index(topic.id) + 1 < len(ids):
            flash(f'Marked "{topic.name}" as read.', 'success')
            return redirect(url_for('theory.topic', topic_id=ids[ids.index(topic.id) + 1]))
    return redirect(url_for('theory.topic', topic_id=topic.id))


@bp.route('/image/<int:image_id>')
def image(image_id):
    return serve_image(TheoryImage.query.filter_by(id=image_id, team_organization_id=get_current_team_id())
                       .first_or_404())


def serve_image(image):
    """An uploaded photo (the playbook's are kept here too), cached by the browser."""
    etag = hashlib.sha1(image.data[:4096].encode('ascii') + str(image.id).encode()).hexdigest()
    if request.if_none_match and etag in request.if_none_match:
        return '', 304
    response = make_response(base64.b64decode(image.data))
    response.headers['Content-Type'] = image.mime_type
    response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
    response.set_etag(etag)
    return response


# ── Coaches: who has read it, asking the team to read it ──────────────────

@bp.route('/topic/<int:topic_id>/readers', methods=['GET', 'POST'])
def readers(topic_id):
    coach_only()
    topic = topic_or_404(topic_id)
    form = TheoryAssignmentForm(obj=topic.assignment)
    if form.validate_on_submit():
        assignment = topic.assignment or TheoryAssignment(topic=topic, team_organization_id=topic.team_organization_id,
                                                          assigned_by=current_user.id)
        assignment.due_date = form.due_date.data
        assignment.note = (form.note.data or '').strip() or None
        db.session.add(assignment)
        db.session.commit()
        flash(f'The team has been asked to read "{topic.name}".' if topic.published
              else 'Saved. Players will see it once the topic is published.', 'success')
        return redirect(url_for('theory.readers', topic_id=topic.id))
    reads = {r.user_id: r.read_at for r in topic.reads}
    people = [(user, name, reads.get(user.id)) for user, name in hub.team_readers(topic.team_organization_id)]
    people.sort(key=lambda p: (p[2] is None, p[1].lower()))
    return render_template('theory/readers.html', title=f'Who has read {topic.name}', topic=topic, form=form,
                           people=people, read_count=sum(1 for p in people if p[2]))


@bp.route('/topic/<int:topic_id>/unassign', methods=['POST'])
def unassign(topic_id):
    coach_only()
    topic = topic_or_404(topic_id)
    if topic.assignment:
        db.session.delete(topic.assignment)
        db.session.commit()
        flash('No longer assigned.', 'success')
    return redirect(hub.local_next(url_for('theory.readers', topic_id=topic.id)))


# ── Sections ───────────────────────────────────────────────────────────────

@bp.route('/add_section', methods=['GET', 'POST'])
def add_section():
    coach_only()
    team_id = get_current_team_id()
    form = TheorySectionForm()
    if form.validate_on_submit():
        last = db.session.query(db.func.max(TheorySection.order)).filter_by(team_organization_id=team_id).scalar()
        section = TheorySection(name=form.name.data.strip(), description=(form.description.data or '').strip(),
                                order=(last or 0) + 1, team_organization_id=team_id,
                                slug=unique_slug(TheorySection, form.name.data, team_id))
        db.session.add(section)
        db.session.commit()
        flash(f'Section "{section.name}" added.', 'success')
        return redirect(url_for('theory.section', slug=section.slug))
    return render_template('theory/section_form.html', form=form, title='New section')


@bp.route('/edit_section/<int:section_id>', methods=['GET', 'POST'])
def edit_section(section_id):
    coach_only()
    section = TheorySection.query.filter_by(id=section_id, team_organization_id=get_current_team_id()).first_or_404()
    form = TheorySectionForm(obj=section)
    if form.validate_on_submit():
        section.name = form.name.data.strip()
        section.description = (form.description.data or '').strip()
        db.session.commit()
        flash(f'Section "{section.name}" saved.', 'success')
        return redirect(url_for('theory.section', slug=section.slug))
    return render_template('theory/section_form.html', form=form, section=section, title='Edit section')


@bp.route('/delete_section/<int:section_id>', methods=['POST'])
def delete_section(section_id):
    coach_only()
    team_id = get_current_team_id()
    section = TheorySection.query.filter_by(id=section_id, team_organization_id=team_id).first_or_404()
    name = section.name
    db.session.delete(section)
    db.session.flush()
    hub.drop_unused_tags(team_id)
    db.session.commit()
    flash(f'Section "{name}" deleted.', 'success')
    return redirect(url_for('theory.index'))


@bp.route('/section/<int:section_id>/move', methods=['POST'])
def move_section(section_id):
    coach_only()
    sections = team_sections(get_current_team_id())
    section = next((s for s in sections if s.id == section_id), None) or abort(404)
    move(sections, section, request.form.get('direction'))
    db.session.commit()
    if wants_json():
        return jsonify({'ok': True})
    return redirect(hub.local_next(url_for('theory.index')))


# ── Topics ─────────────────────────────────────────────────────────────────

def team_drills(team_id):
    return SavedDrill.query.filter_by(team_organization_id=team_id).order_by(SavedDrill.title).all()


def team_clips(team_id):
    return Clip.query.filter_by(team_organization_id=team_id).order_by(Clip.created_at.desc()).all()


def visible_clips(topic):
    """The topic's clips this viewer may watch (hidden ones are for coaches)."""
    return [c for c in topic.clips if c.team_organization_id == topic.team_organization_id
            and (sees_hidden_clips() or not c.is_hidden)]


def videos_from_form():
    """[(url, title)] from the form's video rows, and any problems."""
    urls = request.form.getlist('video_url')
    titles = request.form.getlist('video_title')
    videos, errors = [], []
    for n, url in enumerate(urls):
        url = url.strip()
        if not url:
            continue
        if not video_embed_url(url):
            errors.append(f'"{url[:60]}" isn\'t a YouTube or Vimeo link.')
            continue
        title = (titles[n] if n < len(titles) else '').strip()[:200]
        videos.append((url[:500], title))
    if len(videos) > MAX_VIDEOS:
        errors.append(f'A topic can have up to {MAX_VIDEOS} videos.')
    return videos, errors


def topic_form_page(form, topic=None, videos=None, drills=None):
    team_id = get_current_team_id()
    if videos is None:
        videos = [(v.url, v.title) for v in topic.related_videos] if topic else []
    tag_names = sorted({t.name for t in TheoryTag.query.filter_by(team_organization_id=team_id)}, key=str.lower)
    return render_template('theory/topic_form.html', form=form, topic=topic, videos=videos,
                           drills=drills if drills is not None else team_drills(team_id), tag_names=tag_names,
                           clips=team_clips(team_id), plays=team_plays(team_id),
                           title='Edit topic' if topic else 'New topic')


def save_topic(form, topic):
    """Fill topic from a valid form; returns an error message or None."""
    # (no flushing a half-filled topic while the drills and tags are looked up)
    with db.session.no_autoflush:
        return _save_topic(form, topic)


def _save_topic(form, topic):
    team_id = get_current_team_id()
    section = TheorySection.query.filter_by(id=form.section_id.data, team_organization_id=team_id).first()
    if section is None:
        return 'Choose a section.'
    videos, errors = videos_from_form()
    if errors:
        return ' '.join(errors)
    action = request.form.get('action', 'save')
    published = {'publish': True, 'draft': False}.get(action, topic.published if topic.id else False)
    if published and not (form.content.data or '').strip():
        return 'Write something before publishing (or save it as a draft).'

    if topic.section_id != section.id:
        last = db.session.query(db.func.max(TheoryTopic.order)).filter_by(section_id=section.id).scalar()
        topic.order = (last or 0) + 1
    topic.section_id = section.id
    topic.section = section
    topic.name = form.name.data.strip()
    topic.content = form.content.data or ''
    topic.image_url = (form.image_url.data or '').strip() or None
    topic.published = published
    topic.team_organization_id = team_id
    topic.updated_by = current_user.id

    drill_ids = set(form.related_drills.data or [])
    topic.related_drills = [d for d in team_drills(team_id) if d.id in drill_ids]
    clip_ids = set(form.clips.data or [])
    topic.clips = [c for c in team_clips(team_id) if c.id in clip_ids]
    if playbook_on(team_id):
        play_ids = set(form.plays.data or [])
        topic.plays = [p for p in team_plays(team_id) if p.id in play_ids]
    topic.tags = hub.tags_for(hub.parse_tags(form.tags.data), team_id)

    old = {v.url: v for v in topic.related_videos}
    topic.related_videos = []
    for n, (url, title) in enumerate(videos, start=1):
        video = old.pop(url, None) or TheoryVideo(url=url, team_organization_id=team_id)
        video.title = title or video.title or hub.fetch_video_title(url) or 'Video'
        video.order = n
        topic.related_videos.append(video)
    return None


@bp.route('/add_topic', methods=['GET', 'POST'])
def add_topic():
    coach_only()
    team_id = get_current_team_id()
    sections = team_sections(team_id)
    if not sections:
        flash('Add a section first: topics live in sections.', 'info')
        return redirect(url_for('theory.add_section'))
    form = TheoryTopicForm()
    form.section_id.choices = [(s.id, s.name) for s in sections]
    if request.method == 'GET':
        wanted = request.args.get('section_id', type=int)
        form.section_id.data = wanted if any(s.id == wanted for s in sections) else sections[0].id
    if form.validate_on_submit():
        topic = TheoryTopic(created_by=current_user.id, team_organization_id=team_id, published=False)
        error = save_topic(form, topic)
        if error is None:
            db.session.add(topic)
            db.session.commit()
            flash(f'"{topic.name}" published.' if topic.published else f'"{topic.name}" saved as a draft.', 'success')
            return redirect(url_for('theory.topic', topic_id=topic.id, saved=1))
        db.session.rollback()
        flash(error, 'danger')
        return topic_form_page(form, videos=videos_from_form()[0])
    return topic_form_page(form)


@bp.route('/edit_topic/<int:topic_id>', methods=['GET', 'POST'])
def edit_topic(topic_id):
    coach_only()
    team_id = get_current_team_id()
    topic = topic_or_404(topic_id)
    form = TheoryTopicForm(obj=topic)
    form.section_id.choices = [(s.id, s.name) for s in team_sections(team_id)]
    if request.method == 'GET':
        form.tags.data = ', '.join(t.name for t in topic.tags)
        form.related_drills.data = [d.id for d in topic.related_drills]
        form.clips.data = [c.id for c in topic.clips]
        form.plays.data = [p.id for p in topic.plays]
    if form.validate_on_submit():
        was_published = topic.published
        error = save_topic(form, topic)
        if error is None:
            hub.drop_unused_tags(team_id)
            db.session.commit()
            if topic.published and not was_published:
                flash(f'"{topic.name}" published.', 'success')
            elif was_published and not topic.published:
                flash(f'"{topic.name}" moved back to drafts: players can\'t see it now.', 'success')
            else:
                flash('Saved.', 'success')
            return redirect(url_for('theory.topic', topic_id=topic.id, saved=1))
        db.session.rollback()
        flash(error, 'danger')
        return topic_form_page(form, topic=db.session.get(TheoryTopic, topic_id), videos=videos_from_form()[0])
    return topic_form_page(form, topic=topic)


@bp.route('/delete_topic/<int:topic_id>', methods=['POST'])
def delete_topic(topic_id):
    coach_only()
    team_id = get_current_team_id()
    topic = topic_or_404(topic_id)
    section_slug, name = topic.section.slug, topic.name
    db.session.delete(topic)
    db.session.flush()
    hub.drop_unused_tags(team_id)
    db.session.commit()
    flash(f'Topic "{name}" deleted.', 'success')
    return redirect(url_for('theory.section', slug=section_slug))


@bp.route('/topic/<int:topic_id>/publish', methods=['POST'])
def publish(topic_id):
    coach_only()
    topic = topic_or_404(topic_id)
    if not (topic.content or '').strip():
        flash('Write something before publishing.', 'danger')
        return redirect(url_for('theory.edit_topic', topic_id=topic.id))
    topic.published = True
    topic.updated_by = current_user.id
    db.session.commit()
    flash(f'"{topic.name}" published: the team can read it now.', 'success')
    return redirect(url_for('theory.topic', topic_id=topic.id))


@bp.route('/topic/<int:topic_id>/move', methods=['POST'])
def move_topic(topic_id):
    coach_only()
    topic = topic_or_404(topic_id)
    topics = topic.section.topics.order_by(*in_order(TheoryTopic)).all()
    move(topics, topic, request.form.get('direction'))
    db.session.commit()
    if wants_json():
        return jsonify({'ok': True})
    return redirect(hub.local_next(url_for('theory.section', slug=topic.section.slug)))


@bp.route('/organise', methods=['GET', 'POST'])
def organise():
    """Every topic with a section picker, to move many between sections in
    one save, and a box for a new section to move them into."""
    coach_only()
    team_id = get_current_team_id()
    sections = team_sections(team_id)
    if request.method == 'POST' and request.form.get('action') == 'add_section':
        name = ' '.join((request.form.get('name') or '').split())[:100]
        if not name:
            flash('Give the new section a name.', 'danger')
        elif any(s.name.lower() == name.lower() for s in sections):
            flash(f'There is already a section called "{name}".', 'danger')
        else:
            section = TheorySection(name=name, order=max([s.order or 0 for s in sections] + [0]) + 1,
                                    team_organization_id=team_id,
                                    slug=unique_slug(TheorySection, name, team_id))
            db.session.add(section)
            db.session.commit()
            flash(f'Section "{name}" added. Pick it for the topics you want in it, then save.', 'success')
            return redirect(url_for('theory.organise', _anchor=f'section-{section.id}'))
        return redirect(url_for('theory.organise'))

    topics = {s.id: s.topics.filter_by(team_organization_id=team_id).order_by(*in_order(TheoryTopic)).all()
              for s in sections}
    if request.method == 'POST':
        by_id = {s.id: s for s in sections}
        moves = []
        for section in sections:
            for topic in topics[section.id]:
                target = by_id.get(request.form.get(f'section_{topic.id}', type=int))
                if target is not None and target.id != section.id:
                    moves.append((topic, target))
        for topic, target in moves:
            last = db.session.query(db.func.max(TheoryTopic.order)).filter_by(section_id=target.id).scalar()
            topic.section_id, topic.section = target.id, target
            topic.order = (last or 0) + 1
            db.session.flush()
        db.session.commit()
        if moves:
            flash(f'Moved {len(moves)} topic{"s" if len(moves) != 1 else ""}. '
                  'Moved topics go to the end of their new section.', 'success')
        else:
            flash('Nothing to move: every topic is where it was.', 'info')
        return redirect(url_for('theory.organise'))
    return render_template('theory/organise.html', title='Organise sections', sections=sections, topics=topics)


@bp.route('/import', methods=['GET', 'POST'])
def import_cards():
    """Upload a markdown file of cards (app/utils/theory_import.py); they
    arrive as drafts in the section the file names."""
    coach_only()
    errors = []
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            errors = ['Choose a Markdown (.md) file to upload.']
        else:
            try:
                report = theory_import.import_cards(theory_import.decode(file.read()), get_current_team_id(),
                                                    current_user.id, replace=bool(request.form.get('replace')))
            except theory_import.TheoryImportError as e:
                db.session.rollback()
                errors = e.errors
            else:
                db.session.commit()
                flash(report.summary() + ' Publish each one when you want the team to read it.', 'success')
                if len(report.sections) > 1:
                    return redirect(url_for('theory.index'))
                return redirect(url_for('theory.section', slug=report.section.slug))
    return render_template('theory/import.html', title='Import cards', errors=errors), 400 if errors else 200


@bp.route('/preview', methods=['POST'])
def preview():
    """The editor's Preview tab: the markdown as players will see it."""
    coach_only()
    return jsonify({'html': str(render_content(request.form.get('content'), get_current_team_id()))})


@bp.route('/images', methods=['POST'])
def upload_image():
    coach_only()
    file = request.files.get('image')
    if not file or not file.filename:
        return jsonify({'error': 'Choose a photo to upload.'}), 400
    try:
        image = hub.save_image(file, get_current_team_id(), current_user.id)
    except hub.ImageError as e:
        return jsonify({'error': str(e)}), 400
    db.session.commit()
    url = url_for('theory.image', image_id=image.id)
    current_app.logger.info('Theory photo %s uploaded (%sx%s)', image.id, image.width, image.height)
    return jsonify({'url': url, 'width': image.width, 'height': image.height})

