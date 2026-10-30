# app/routes/playbook.py
"""The playbook: offence and defence plays. Coaches (captains and admins
too) write and draw them; everyone on the team reads them, marks them
learned and flicks through the game-day cards. Every page is a 404 when the
team has the Playbook switched off.

A play is a Draft (coaches only), In use, or Retired (still readable, but
off the cards, the PDF and game plans). Team concepts moved to Theory; their
old links redirect there.
"""
import json
import re
from datetime import datetime

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify, current_app, abort
)
from flask_login import current_user
from markupsafe import escape

from app import db, login
from app.forms.playbook import LearnForm, PlayForm
from app.models.clip import Clip
from app.models.drill import SavedDrill
from app.models.playbook import (Formation, Play, PlayAssignment, PlayerPosition, PlayLearned,
                                 PlaySetup, PlayToLearn, GameCallPlay, DEFENCE_VIEWS, PLAY_STATUSES, PLAY_TYPES,
                                 SITUATIONS)
from app.models.team_settings import TeamSettings
from app.models.theory import TheoryImage, TheorySection, TheoryTopic
from app.utils import playbook as pb
from app.utils import theory as hub
from app.utils.editor_diagrams import save_editor_diagrams
from app.utils.roles import drawing_role_ids, drawing_state, plays_by_role, team_roles
from app.utils.team_filter import get_current_team_id

bp = Blueprint('playbook', __name__, url_prefix='/playbook')

TYPES = dict(PLAY_TYPES)
STATUSES = dict(PLAY_STATUSES)
MAX_ROLES = 15


def _play_order():
    """Manual sort order first (lower = first), then name."""
    return pb.in_order()


def settings_for(team_id):
    return TeamSettings.query.filter_by(team_id=team_id).first() if team_id else None


def feature_on(name, team_id=None):
    settings = settings_for(team_id or get_current_team_id())
    return settings is None or bool(getattr(settings, name, True))


def can_edit():
    """Coaches, captains and admins."""
    return current_user.is_authenticated and current_user.is_coach


def coach_only():
    if not can_edit():
        abort(403)


def wants_json():
    return (request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.accept_mimetypes.best == 'application/json')


PUBLIC_ENDPOINTS = {'playbook.shared_play'}


@bp.before_request
def check_access():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None  # a share link: checked by its token
    if not current_user.is_authenticated:
        return login.unauthorized()
    if not feature_on('playbook_enabled'):
        abort(404)


@bp.context_processor
def playbook_context():
    return {'can_edit': can_edit(), 'TYPES': TYPES, 'STATUSES': STATUSES}


def team_plays(team_id, include_drafts=None):
    query = Play.query.filter_by(team_organization_id=team_id)
    if not (can_edit() if include_drafts is None else include_drafts):
        query = query.filter(Play.status != 'draft')
    return query


def play_or_404(play_id):
    play = Play.query.filter_by(id=play_id, team_organization_id=get_current_team_id()).first_or_404()
    if play.is_draft and not can_edit():
        abort(404)
    return play


def my_role_ids(team_id):
    """The signed-in player's roles this season (Team → Roles), main role first."""
    from app.routes.roles import roles_season
    from app.utils.roles import player_roles
    from app.utils.season import roster_entry
    player = current_user.player if current_user.is_authenticated else None
    if player is None:
        return []
    return [r.role_id for r in player_roles(roster_entry(player, roles_season(team_id)))]


def my_main_role(team_id):
    ids = my_role_ids(team_id)
    return db.session.get(PlayerPosition, ids[0]) if ids else None


def export_plays(team_id):
    """What goes in the PDF: plays in use."""
    return Play.query.filter_by(team_organization_id=team_id, status='active').order_by(*_play_order()).all()


# ── Background export jobs (progress reporting) ──────────────────
# In-memory job store. Fine for a single gunicorn worker; jobs are
# pruned after 30 minutes.
import threading as _threading
import time as _time
import uuid as _uuid

_export_jobs = {}
_export_jobs_lock = _threading.Lock()


def _prune_export_jobs():
    cutoff = _time.time() - 1800
    with _export_jobs_lock:
        for jid in [j for j, v in _export_jobs.items() if v['ts'] < cutoff]:
            _export_jobs.pop(jid, None)


def _export_filters():
    type_filter = request.args.get('type')
    if type_filter not in ('offense', 'defense'):
        type_filter = None
    tag_id = request.args.get('tag', type=int)
    return type_filter, tag_id


def _export_filename(team_name, type_filter):
    from datetime import datetime
    suffix = f'_{type_filter}' if type_filter else ''
    return (f"{team_name.replace(' ', '_').lower()}_playbook{suffix}"
            f"_{datetime.now():%Y-%m-%d}.pdf")


def _run_export_job(app, job_id, team_id, team_name, type_filter, tag_id, base_url=None):
    from app.utils.playbook_export import (
        generate_playbook_pdf, cache_key, store_cached_pdf
    )
    # test_request_context: templates render in background threads with an
    # anonymous user instead of crashing in context processors. base_url:
    # the site's address, for the links in the QR codes.
    with app.test_request_context(base_url=base_url):
        job = _export_jobs.get(job_id)
        if job is None:
            return
        try:
            plays = export_plays(team_id)

            def progress(pct, label):
                j = _export_jobs.get(job_id)
                if j is not None:
                    j['pct'] = pct
                    j['label'] = label

            pdf_bytes = generate_playbook_pdf(
                plays, team_name,
                type_filter=type_filter, tag_id=tag_id, progress=progress)

            key = cache_key(team_id, plays, type_filter, tag_id)
            store_cached_pdf(team_id, key, pdf_bytes)

            job.update(state='ready', pct=100, label='Ready',
                       pdf=pdf_bytes,
                       filename=_export_filename(team_name, type_filter))
        except ImportError:
            current_app.logger.error('Playbook export: playwright is not installed')
            job.update(state='error',
                       label='PDF export is not available on this server (Playwright missing).')
        except Exception as e:
            current_app.logger.error(f'Playbook export failed: {e}')
            job.update(state='error', label='Export failed — check the server logs.')


@bp.route('/export/start')
def export_start():
    """Kick off a background export; returns a job id to poll."""
    from app.models.team_organization import TeamOrganization
    from app.utils.playbook_export import cache_key, cached_pdf

    _prune_export_jobs()

    team_id = get_current_team_id()
    team = TeamOrganization.query.get(team_id) if team_id else None
    team_name = team.name if team else 'Team'
    type_filter, tag_id = _export_filters()

    job_id = _uuid.uuid4().hex
    job = {'ts': _time.time(), 'team_id': team_id, 'user_id': current_user.id,
           'state': 'running', 'pct': 2, 'label': 'Starting…',
           'pdf': None, 'filename': None}
    with _export_jobs_lock:
        _export_jobs[job_id] = job

    # Cache fast-path: nothing changed since the last export
    plays = export_plays(team_id)
    cached = cached_pdf(team_id, cache_key(team_id, plays, type_filter, tag_id))
    if cached:
        job.update(state='ready', pct=100, label='Ready', pdf=cached,
                   filename=_export_filename(team_name, type_filter))
        return jsonify({'job_id': job_id, 'state': 'ready'})

    app = current_app._get_current_object()
    _threading.Thread(
        target=_run_export_job,
        args=(app, job_id, team_id, team_name, type_filter, tag_id, request.host_url),
        daemon=True
    ).start()
    return jsonify({'job_id': job_id, 'state': 'running'})


@bp.route('/export/status/<job_id>')
def export_status(job_id):
    job = _export_jobs.get(job_id)
    if job is None or job['team_id'] != get_current_team_id():
        return jsonify({'state': 'unknown'}), 404
    payload = {'state': job['state'], 'pct': job['pct'], 'label': job['label']}
    if job['state'] == 'ready':
        payload['download_url'] = url_for('playbook.export_download', job_id=job_id)
    return jsonify(payload)


@bp.route('/export/download/<job_id>')
def export_download(job_id):
    from io import BytesIO
    from flask import send_file
    job = _export_jobs.get(job_id)
    if (job is None or job['state'] != 'ready'
            or job['team_id'] != get_current_team_id()):
        abort(404)
    return send_file(BytesIO(job['pdf']), mimetype='application/pdf',
                     as_attachment=True, download_name=job['filename'])


@bp.route('/export.pdf')
def export_pdf():
    """Export the playbook as a PDF. Optional filters: ?type=offense|defense, ?tag=<id>."""
    from io import BytesIO
    from datetime import datetime
    from flask import send_file
    from app.models.team_organization import TeamOrganization
    from app.utils.playbook_export import (
        generate_playbook_pdf, cache_key, cached_pdf, store_cached_pdf
    )

    team_id = get_current_team_id()
    team = TeamOrganization.query.get(team_id) if team_id else None
    team_name = team.name if team else 'Team'

    type_filter = request.args.get('type')
    if type_filter not in ('offense', 'defense'):
        type_filter = None
    tag_id = request.args.get('tag', type=int)

    plays = export_plays(team_id)

    def respond(pdf_bytes):
        suffix = f'_{type_filter}' if type_filter else ''
        filename = (f"{team_name.replace(' ', '_').lower()}_playbook{suffix}"
                    f"_{datetime.now():%Y-%m-%d}.pdf")
        return send_file(BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)

    # Serve from cache when nothing has changed
    key = cache_key(team_id, plays, type_filter, tag_id)
    cached = cached_pdf(team_id, key)
    if cached:
        return respond(cached)

    try:
        pdf_bytes = generate_playbook_pdf(plays, team_name,
                                          type_filter=type_filter, tag_id=tag_id)
    except ImportError:
        current_app.logger.error('Playbook export: playwright is not installed')
        flash('PDF export is not available: Playwright is not installed on the server.', 'danger')
        return redirect(url_for('playbook.index'))
    except Exception as e:
        current_app.logger.error(f'Playbook export failed: {e}')
        flash('PDF export failed. Please try again or check the server logs.', 'danger')
        return redirect(url_for('playbook.index'))

    store_cached_pdf(team_id, key, pdf_bytes)
    return respond(pdf_bytes)



# ── Reading ────────────────────────────────────────────────────────────────

def search(plays, q):
    """Plays matching every word of q, best first (name and call, then tags,
    then the text and roles)."""
    words = q.lower().split()
    scored = []
    for p in plays:
        title = f'{p.name} {p.call or ""}'.lower()
        tags = ' '.join(t.name.lower() for t in p.tags)
        body = ' '.join([hub.plain_text(p.description), p.signal or '',
                         *(f'{a.position.name if a.position else ""} {a.instructions}' for a in p.assignments)]).lower()
        if all(w in title or w in tags or w in body for w in words):
            scored.append((-sum(5 * (w in title) + 3 * (w in tags) + (w in body) for w in words), p.name.lower(), p))
    return [p for _, _, p in sorted(scored, key=lambda s: s[:2])]


@bp.route('/')
def index():
    team_id = get_current_team_id()
    type_filter = request.args.get('type') if request.args.get('type') in TYPES else None
    show_retired = request.args.get('show') == 'retired'
    tag = (request.args.get('tag') or '').strip()
    q = (request.args.get('q') or '').strip()
    situation = request.args.get('when') if request.args.get('when') in dict(SITUATIONS) else None
    core_only = request.args.get('core') == '1'

    every = team_plays(team_id).order_by(*_play_order()).all()
    in_use = [p for p in every if p.status == 'active']
    plays = [p for p in every if p.is_retired == show_retired]
    if type_filter:
        plays = [p for p in plays if p.type == type_filter]
    if tag:
        plays = [p for p in plays if any(t.name.lower() == tag.lower() for t in p.tags)]
    if situation:
        plays = [p for p in plays if situation in p.situation_keys]
    if core_only:
        plays = [p for p in plays if p.is_core]
    if q:
        plays = search(plays, q)
    tag_names = sorted({t.name for p in every for t in p.tags}, key=str.lower)

    learned = pb.learned_ids(current_user.id, team_id)
    to_learn, learn_counts, team_size = [], {}, 0
    if can_edit():
        to_learn = sorted(PlayToLearn.query.filter_by(team_organization_id=team_id).all(),
                          key=lambda r: (r.due_date is None, r.due_date, r.created_at))
        if to_learn:
            team_size = len(hub.team_readers(team_id))
            ids = [r.play_id for r in to_learn]
            learn_counts = dict(db.session.query(PlayLearned.play_id, db.func.count(PlayLearned.id))
                                .filter(PlayLearned.play_id.in_(ids)).group_by(PlayLearned.play_id).all())
    else:
        to_learn = pb.to_learn_unlearned(current_user.id, team_id)

    return render_template('playbook/index.html', title='Playbook', plays=plays, type_filter=type_filter,
                           show_retired=show_retired, tag=tag, q=q, tag_names=tag_names,
                           grouped=not (q or type_filter), situation=situation, core_only=core_only,
                           situations=[(k, v) for k, v in SITUATIONS if any(k in p.situation_keys for p in every)],
                           has_core=any(p.is_core for p in every),
                           to_redraw=[p for p in every if can_edit() and not p.is_retired and not p.editor_diagram]
                           if can_edit() else [],
                           learned=learned, to_learn=to_learn, learn_counts=learn_counts, team_size=team_size,
                           known=len([p for p in in_use if p.id in learned]), total_in_use=len(in_use),
                           my_role=my_main_role(team_id),
                           has_retired=any(p.is_retired for p in every))


def visible_clips(clips, team_id):
    from app.routes.clip.helpers import sees_hidden_clips
    return [c for c in clips if c.team_organization_id == team_id and (sees_hidden_clips() or not c.is_hidden)]


def visible_topics(play):
    if not feature_on('theory_enabled', play.team_organization_id):
        return []
    return [t for t in play.theory_topics if t.team_organization_id == play.team_organization_id
            and (t.published or can_edit())]


@bp.route('/plays/<int:play_id>')
def view_play(play_id):
    play = play_or_404(play_id)
    team_id = play.team_organization_id

    # Drawn in stages: the page plays them as an animation. Players given
    # roles: pick a role to see just their path (one stage too).
    state = drawing_state(play)
    drawn_roles = drawing_role_ids(state)
    animation = state if state and (len(state.get('stages') or []) > 1 or drawn_roles
                                    or play.defence_view in ('faded', 'hidden')) else None
    roles = team_roles(team_id)
    said = {a.position_id: a for a in play.assignments}
    who = [{'role': r, 'assignment': said.get(r.id), 'drawn': r.id in drawn_roles}
           for r in roles if r.id in said or r.id in drawn_roles]

    # Previous / next among the same side's plays
    siblings = [p for p in team_plays(team_id).filter_by(type=play.type).order_by(*_play_order())
                if p.is_retired == play.is_retired]
    ids = [p.id for p in siblings]
    i = ids.index(play.id) if play.id in ids else 0

    # The player's own role in it: the first of theirs it has (main role first)
    mine_ids = my_role_ids(team_id)
    mine = next(({'role': w['role'], 'assignment': w['assignment'], 'drawn': w['drawn']}
                 for rid in mine_ids for w in who if w['role'].id == rid), None)
    learners = None
    if can_edit():
        learners = (PlayLearned.query.filter_by(play_id=play.id).count(), len(hub.team_readers(team_id)))
    reports = [r for r in play.scouting_reports if r.team_organization_id == team_id] \
        if feature_on('scouting_enabled', team_id) else []
    sessions = sorted({c.session for c in play.session_components
                       if c.session and c.team_organization_id == team_id},
                      key=lambda s: s.date or datetime.min.date(), reverse=True)
    return render_template('playbook/play_detail.html', title=play.name, play=play, animation=animation,
                           prev_play=siblings[i - 1] if i > 0 else None,
                           next_play=siblings[i + 1] if i + 1 < len(siblings) else None,
                           position=(i + 1, len(siblings)),
                           who=who, animation_roles=[r for r in roles if r.id in drawn_roles],
                           animation_defence=play.defence_view, animation_name=play.name,
                           coming=coming_sessions(team_id) if can_edit() else [],
                           in_games=_in_games(play),
                           mine=mine, is_learned=play.id in pb.learned_ids(current_user.id, team_id),
                           learners=learners, topics=visible_topics(play),
                           clips=visible_clips(play.clips, team_id), reports=reports, sessions=sessions[:5])


@bp.route('/plays/<int:play_id>/drawing.json')
def play_drawing(play_id):
    """The play's drawing, for playing it in place (cards, the playbook
    list, sessions: play_preview.js)."""
    play = play_or_404(play_id)
    state = drawing_state(play)
    if not state:
        abort(404)
    response = jsonify({'drawing': state, 'defence': play.defence_view or 'show', 'name': play.name,
                        'url': url_for('playbook.view_play', play_id=play.id)})
    response.headers['Cache-Control'] = 'private, no-cache'
    return response


@bp.route('/plays/<int:play_id>/learned', methods=['POST'])
def mark_learned(play_id):
    play = play_or_404(play_id)
    row = PlayLearned.query.filter_by(user_id=current_user.id, play_id=play.id).first()
    want = request.form.get('read', '1') != '0'
    if want and row is None:
        db.session.add(PlayLearned(user_id=current_user.id, play_id=play.id,
                                   team_organization_id=play.team_organization_id))
    elif not want and row is not None:
        db.session.delete(row)
    db.session.commit()
    if wants_json():
        return jsonify({'read': want})
    flash(f'"{play.name}" marked as learned.' if want else f'"{play.name}" is back on your list to learn.', 'success')
    return redirect(url_for('playbook.view_play', play_id=play.id))


@bp.route('/plays/<int:play_id>/learners', methods=['GET', 'POST'])
def learners(play_id):
    """Who has learned it, and asking the team to learn it."""
    coach_only()
    from app.models.tournament import Tournament
    play = play_or_404(play_id)
    form = LearnForm(obj=play.to_learn)
    coming = (Tournament.query.filter(Tournament.team_organization_id == play.team_organization_id,
                                      db.or_(Tournament.start_date.is_(None),
                                             Tournament.start_date >= datetime.utcnow().date()))
              .order_by(Tournament.start_date).all())
    if play.to_learn and play.to_learn.tournament and play.to_learn.tournament not in coming:
        coming.insert(0, play.to_learn.tournament)
    form.tournament_id.choices = [(0, 'No tournament')] + [
        (t.id, t.name + (f" ({t.start_date.strftime('%-d %b')})" if t.start_date else '')) for t in coming]
    if request.method == 'GET' and not play.to_learn:
        form.tournament_id.data = 0
    if form.validate_on_submit():
        row = play.to_learn or PlayToLearn(play=play, team_organization_id=play.team_organization_id,
                                           assigned_by=current_user.id)
        tournament = next((t for t in coming if t.id == form.tournament_id.data), None)
        row.tournament_id = tournament.id if tournament else None
        # Learning for a tournament: by its first day unless a date's given
        row.due_date = form.due_date.data or (tournament.start_date if tournament else None)
        row.note = (form.note.data or '').strip() or None
        db.session.add(row)
        db.session.commit()
        flash(f'The team has been asked to learn "{play.name}".' if play.status == 'active'
              else "Saved. Players will see it once the play is in use.", 'success')
        return redirect(url_for('playbook.learners', play_id=play.id))
    done = {r.user_id: r.learned_at for r in play.learned}
    people = [(user, name, done.get(user.id)) for user, name in hub.team_readers(play.team_organization_id)]
    people.sort(key=lambda p: (p[2] is None, p[1].lower()))
    return render_template('playbook/learners.html', title=f'Who knows {play.name}', play=play, form=form,
                           people=people, learned_count=sum(1 for p in people if p[2]))


@bp.route('/plays/<int:play_id>/unassign', methods=['POST'])
def unassign(play_id):
    coach_only()
    play = play_or_404(play_id)
    if play.to_learn:
        db.session.delete(play.to_learn)
        db.session.commit()
        flash('No longer asking the team to learn it.', 'success')
    return redirect(url_for('playbook.learners', play_id=play.id))


@bp.route('/positions')
@bp.route('/positions/<int:position_id>')
def position_view(position_id=None):
    """By role: pick a role and see every play it's in, with what it does
    and a link that shows just its path. A player with roles starts on their
    main one."""
    team_id = get_current_team_id()
    positions = team_roles(team_id)
    mine = my_role_ids(team_id)
    if position_id is None and mine:
        return redirect(url_for('playbook.position_view', position_id=mine[0]))
    selected = None
    entries = []
    if position_id:
        selected = next((p for p in positions if p.id == position_id), None) or abort(404)
        for play in plays_by_role(team_id).get(selected.id, []):
            if play.is_draft and not can_edit() or play.is_retired:
                continue
            assignment = next((a for a in play.assignments if a.position_id == selected.id), None)
            entries.append({'play': play, 'assignment': assignment,
                            'drawn': selected.id in drawing_role_ids(drawing_state(play))})
    return render_template('playbook/position_view.html', title='Plays by role', positions=positions,
                           selected=selected, entries=entries, mine=mine)


# ── Game-day cards: the playbook on a phone ──────────────────────
@bp.route('/cards')
def cards():
    """One card per play in use, drawing first, for looking over before a
    game. ?type=offense|defense filters; ?report=<scouting report> shows the
    plays picked for that game."""
    from app.models.scouting import ScoutingReport
    team_id = get_current_team_id()
    report = None
    report_id = request.args.get('report', type=int)
    if report_id:
        report = ScoutingReport.query.filter_by(id=report_id, team_organization_id=team_id).first_or_404()
        plays = [p for p in report.plays_in_order if p.team_organization_id == team_id and not p.is_draft]
    else:
        plays = Play.query.filter_by(team_organization_id=team_id, status='active') \
            .order_by(Play.type.desc(), *_play_order()).all()
    type_filter = request.args.get('type')
    if type_filter in ('offense', 'defense'):
        plays = [p for p in plays if p.type == type_filter]
    else:
        type_filter = None
    situation = request.args.get('when') if request.args.get('when') in dict(SITUATIONS) else None
    if situation:
        plays = [p for p in plays if situation in p.situation_keys]
    core_only = request.args.get('core') == '1'
    if core_only:
        plays = [p for p in plays if p.is_core]
    # Each card shows the player's own role first, and links to their path
    # when it's in the drawing
    mine = my_role_ids(team_id)
    my_path, my_part = {}, {}
    for play in plays:
        drawn = drawing_role_ids(drawing_state(play)) if mine else set()
        my_path[play.id] = next((r for r in mine if r in drawn), None)
        my_part[play.id] = next((a for r in mine for a in play.assignments if a.position_id == r), None)
    return render_template('playbook/cards.html', plays=plays, report=report, type_filter=type_filter,
                           my_path=my_path, my_part=my_part, learned=pb.learned_ids(current_user.id, team_id),
                           situation=situation, core_only=core_only, situations=SITUATIONS)


# ── Drawing a play in the drill editor ───────────────────────────
@bp.route('/plays/draw')
@bp.route('/plays/<int:play_id>/draw')
def draw_play(play_id=None):
    """Draw a play on the field, in stages, with the drill editor."""
    coach_only()
    play = None
    editor_state = None
    team_id = get_current_team_id()
    if play_id:
        play = play_or_404(play_id)
        if play.editor_diagram:
            editor_state = json.loads(play.editor_diagram.editor_json)
    elif request.args.get('setup', type=int):
        # A new play starting from a saved set-up
        setup = PlaySetup.query.filter_by(id=request.args.get('setup', type=int), team_organization_id=team_id).first_or_404()
        saved = json.loads(setup.state_json)
        editor_state = {'version': 2, 'field': saved.get('field') or {},
                        'stages': [{'name': setup.name, 'notes': '', 'objects': saved.get('objects') or []}]}
    setups = PlaySetup.query.filter_by(team_organization_id=team_id).order_by(PlaySetup.name).all()
    return render_template('playbook/play_editor.html', play=play, drill=None, editor_state=editor_state,
                           setups=[{'id': x.id, 'name': x.name, 'type': x.type or '',
                                    'objects': json.loads(x.state_json).get('objects') or []} for x in setups],
                           other_diagrams=[], statuses=PLAY_STATUSES,
                           roles=[{'id': r.id, 'name': r.name, 'line': r.line or ''}
                                  for r in team_roles(get_current_team_id())],
                           new_type=request.args.get('type') if request.args.get('type') in TYPES else 'offense')


def _apply_play_fields(play, data):
    play.name = (data.get('title') or 'Untitled Play').strip()[:100]
    play.description = data.get('description') or None
    play.notes = data.get('notes') or None
    if 'call' in data:
        play.call = (data.get('call') or '').strip()[:60] or None
    if data.get('type') in TYPES and data['type'] != play.type:
        play.type = data['type']
        play.sort_order = next_order(play.team_organization_id, play.type)
    play.type = play.type or 'offense'
    if data.get('status') in STATUSES:
        play.status = data['status']
    play.status = play.status or 'active'
    play.updated_by = current_user.id


def _play_payload():
    try:
        data = json.loads(request.form.get('data') or '{}')
    except ValueError:
        abort(400)
    return data if isinstance(data, dict) else {}


def _play_saved(play, status=200):
    return jsonify({'success': True, 'play_id': play.id,
                    'editor_url': url_for('playbook.draw_play', play_id=play.id),
                    'detail_url': url_for('playbook.view_play', play_id=play.id)}), status


@bp.route('/api/plays', methods=['POST'])
def create_drawn_play():
    coach_only()
    play = Play(created_by=current_user.id, team_organization_id=get_current_team_id())
    _apply_play_fields(play, _play_payload())
    db.session.add(play)
    error = save_editor_diagrams(play, source='Play editor')
    if error:
        db.session.rollback()
        return jsonify({'success': False, 'message': error}), 400
    db.session.commit()
    return _play_saved(play, 201)


@bp.route('/api/plays/<int:play_id>', methods=['PUT'])
def update_drawn_play(play_id):
    coach_only()
    play = play_or_404(play_id)
    _apply_play_fields(play, _play_payload())
    error = save_editor_diagrams(play, source='Play editor')
    if error:
        db.session.rollback()
        return jsonify({'success': False, 'message': error}), 400
    play.updated_at = datetime.utcnow()  # the PDF cache goes by it
    db.session.commit()
    return _play_saved(play)


# ── Writing a play ───────────────────────────────────────────────

def next_order(team_id, play_type):
    last = db.session.query(db.func.max(Play.sort_order)).filter_by(team_organization_id=team_id,
                                                                    type=play_type).scalar()
    return (last or 0) + 1


def link_choices(team_id):
    """What a play can be linked to: theory topics, drills and clips."""
    topics = []
    if feature_on('theory_enabled', team_id):
        topics = (TheoryTopic.query.join(TheorySection, TheorySection.id == TheoryTopic.section_id)
                  .filter(TheoryTopic.team_organization_id == team_id)
                  .order_by(TheorySection.order, TheoryTopic.order, TheoryTopic.name).all())
    drills = SavedDrill.query.filter_by(team_organization_id=team_id).order_by(SavedDrill.title).all()
    clips = Clip.query.filter_by(team_organization_id=team_id).order_by(Clip.created_at.desc()).all() \
        if feature_on('clip_enabled', team_id) else []
    return topics, drills, clips


def roles_from_form():
    """[(role id, instructions)] from the form's role rows, and any problem.
    Roles are the team's (Team → Roles)."""
    team = {r.id: r for r in team_roles(get_current_team_id())}
    ids = request.form.getlist('role_id')
    texts = request.form.getlist('role_text')
    roles, seen = [], set()
    for n, raw in enumerate(ids):
        role = team.get(int(raw)) if raw.isdigit() else None
        text = (texts[n] if n < len(texts) else '').strip()
        if role is None and not text:
            continue
        if role is None:
            return roles, 'Pick a role for each row.'
        roles.append((role.id, text))
        if not text:
            return roles, f'Say what {role.name} does, or remove it.'
        if role.id in seen:
            return roles, f'{role.name} is in the list twice.'
        seen.add(role.id)
    if len(roles) > MAX_ROLES:
        return roles, f'A play can have up to {MAX_ROLES} roles.'
    return roles, None


def form_page(form, play=None, roles=None):
    team_id = get_current_team_id()
    if roles is None:
        roles = [(a.position_id, a.instructions) for a in play.assignments] if play else []
    topics, drills, clips = link_choices(team_id)
    tag_names = sorted({t.name for p in Play.query.filter_by(team_organization_id=team_id) for t in p.tags},
                       key=str.lower)
    return render_template('playbook/play_form.html', form=form, play=play, roles=roles,
                           team_roles=team_roles(team_id), tag_names=tag_names,
                           topics=topics, drills=drills, clips=clips,
                           topic_items=[(t.id, t.name, t.section.name + ('' if t.published else ' · draft'))
                                        for t in topics],
                           drill_items=[(d.id, d.title, d.focus_area) for d in drills],
                           clip_items=[(c.id, c.title or f'Clip {c.id}', f'vs {c.game.opponent}' if c.game else None)
                                       for c in clips],
                           title='Edit play' if play else 'New play')


def save_play(form, play):
    """Fill play from a valid form; returns an error message or None."""
    with db.session.no_autoflush:
        team_id = get_current_team_id()
        roles, error = roles_from_form()
        if error:
            return error
        if play.type != form.type.data or play.sort_order is None:
            play.sort_order = next_order(team_id, form.type.data)
        play.name = form.name.data.strip()
        play.type = form.type.data
        play.status = form.status.data
        play.call = (form.call.data or '').strip() or None
        play.signal = (form.signal.data or '').strip() or None
        play.description = form.description.data or None
        play.notes = form.notes.data or None
        play.image_url = (form.image_url.data or '').strip() or None
        if request.form.get('remove_embed'):  # new Ultiplays links can't be added
            play.ultiplay_embed = None
        play.team_organization_id = team_id
        play.updated_by = current_user.id
        play.tags = pb.tags_for(form.tags.data, team_id)
        play.is_core = bool(form.is_core.data)
        if form.defence_view.data in dict(DEFENCE_VIEWS):
            play.defence_view = None if form.defence_view.data == 'show' else form.defence_view.data
        play.situations = ','.join(k for k, _ in SITUATIONS if k in (form.situations.data or [])) or None

        topics, drills, clips = link_choices(team_id)
        wanted = set(form.topics.data or [])
        # Links to topics this coach can't pick right now (Theory off) stay put
        play.theory_topics = [t for t in topics if t.id in wanted] if topics else play.theory_topics
        wanted = set(form.drills.data or [])
        play.drills = [d for d in drills if d.id in wanted]
        if feature_on('clip_enabled', team_id):
            wanted = set(form.clips.data or [])
            play.clips = [c for c in clips if c.id in wanted]

        old = {a.position_id: a for a in play.assignments}
        play.assignments = []
        for n, (role_id, text) in enumerate(roles, start=1):
            assignment = old.pop(role_id, None) or PlayAssignment(team_organization_id=team_id, position_id=role_id)
            assignment.instructions = text
            assignment.order = n
            play.assignments.append(assignment)
    return None


@bp.route('/plays/add', methods=['GET', 'POST'])
def add_play():
    coach_only()
    team_id = get_current_team_id()
    form = PlayForm()
    if request.method == 'GET':
        form.type.data = request.args.get('type') if request.args.get('type') in TYPES else 'offense'
        form.status.data = 'active'
    if form.validate_on_submit():
        play = Play(created_by=current_user.id, team_organization_id=team_id)
        error = save_play(form, play)
        if error is None:
            db.session.add(play)
            db.session.flush()
            pb.tidy_up(team_id)
            db.session.commit()
            if request.form.get('action') == 'draw':
                return redirect(url_for('playbook.draw_play', play_id=play.id))
            flash(f'"{play.name}" added to the playbook.' if play.status == 'active'
                  else f'"{play.name}" saved as a draft.', 'success')
            return redirect(url_for('playbook.view_play', play_id=play.id, saved=1))
        db.session.rollback()
        flash(error, 'danger')
        return form_page(form, roles=roles_from_form()[0])
    return form_page(form)


@bp.route('/plays/<int:play_id>/edit', methods=['GET', 'POST'])
def edit_play(play_id):
    coach_only()
    team_id = get_current_team_id()
    play = play_or_404(play_id)
    form = PlayForm(obj=play)
    if request.method == 'GET':
        form.defence_view.data = play.defence_view or 'show'
        form.tags.data = ', '.join(t.name for t in play.tags)
        form.situations.data = play.situation_keys
        form.topics.data = [t.id for t in play.theory_topics]
        form.drills.data = [d.id for d in play.drills]
        form.clips.data = [c.id for c in play.clips]
    if form.validate_on_submit():
        error = save_play(form, play)
        if error is None:
            db.session.flush()
            pb.tidy_up(team_id)
            play.updated_at = datetime.utcnow()  # the PDF cache goes by it
            db.session.commit()
            if request.form.get('action') == 'draw':
                return redirect(url_for('playbook.draw_play', play_id=play.id))
            flash('Saved.', 'success')
            return redirect(url_for('playbook.view_play', play_id=play.id, saved=1))
        db.session.rollback()
        flash(error, 'danger')
        return form_page(form, play=db.session.get(Play, play_id), roles=roles_from_form()[0])
    return form_page(form, play=play)


@bp.route('/plays/<int:play_id>/delete', methods=['POST'])
def delete_play(play_id):
    coach_only()
    team_id = get_current_team_id()
    play = play_or_404(play_id)
    name = play.name
    db.session.delete(play)
    db.session.flush()
    pb.tidy_up(team_id)
    db.session.commit()
    flash(f'"{name}" deleted.', 'success')
    return redirect(url_for('playbook.index'))


@bp.route('/plays/<int:play_id>/move', methods=['POST'])
def move_play(play_id):
    """Swap with the neighbouring play on the same side."""
    coach_only()
    play = play_or_404(play_id)
    plays = Play.query.filter_by(team_organization_id=play.team_organization_id, type=play.type) \
        .order_by(*_play_order()).all()
    i = plays.index(play)
    j = i - 1 if request.form.get('direction') == 'up' else i + 1
    if 0 <= j < len(plays):
        plays[i], plays[j] = plays[j], plays[i]
    for n, p in enumerate(plays, start=1):
        p.sort_order = n
    db.session.commit()
    return redirect(hub.local_next(url_for('playbook.index', type=play.type)))


@bp.route('/plays/<int:play_id>/status', methods=['POST'])
def set_status(play_id):
    """Publish a draft, retire a play or bring it back."""
    coach_only()
    play = play_or_404(play_id)
    status = request.form.get('status')
    if status in STATUSES:
        play.status = status
        play.updated_by = current_user.id
        play.updated_at = datetime.utcnow()
        db.session.commit()
        flash({'active': f'"{play.name}" is in use: the team can see it.',
               'retired': f'"{play.name}" retired: it\'s off the cards and the PDF.',
               'draft': f'"{play.name}" is a draft again: only coaches can see it.'}[status], 'success')
    return redirect(hub.local_next(url_for('playbook.view_play', play_id=play.id)))


# ── Plays not drawn yet (older image or embed links) ─────────────

@bp.route('/redraw')
def redraw():
    coach_only()
    plays = [p for p in team_plays(get_current_team_id()).order_by(Play.type.desc(), *_play_order())
             if not p.is_retired and not p.editor_diagram]
    return render_template('playbook/redraw.html', title='Plays to draw', plays=plays)


# ── Bulk add from Ultiplays (temporary) ──────────────────────────
# While the team's Ultiplays library is redrawn in the editor: paste the
# links and each becomes a draft play, keeping its link to redraw from.
# Goes when the ultiplay_embed columns are dropped.
MAX_IMPORT_LINES = 300
IFRAME_TITLE = re.compile(r'title=["\']([^"\']+)["\']', re.I)


def _import_line(line):
    """(name or None, embed code) from 'Name | link or embed code', or
    (None, None) when the line has no link."""
    name, _, code = line.rpartition('|') if '|' in line else ('', '', line)
    name, code = name.strip(), code.strip()
    if '<iframe' in code.lower():
        if not name:
            m = IFRAME_TITLE.search(code)
            name = m.group(1).strip() if m else ''
        return name or None, code
    if code.startswith('https://'):
        src = str(escape(code))
        return name or None, f'<iframe src="{src}" width="100%" height="450" frameborder="0" allowfullscreen></iframe>'
    return None, None


@bp.route('/import-ultiplays', methods=['GET', 'POST'])
def import_ultiplays():
    from app.utils.playbook_export import extract_embed_url
    coach_only()
    team_id = get_current_team_id()
    if request.method == 'GET':
        return render_template('playbook/import_ultiplays.html', title='Add plays from Ultiplays')
    play_type = request.form.get('type') if request.form.get('type') in TYPES else 'offense'
    lines = [ln.strip() for ln in (request.form.get('lines') or '').splitlines() if ln.strip()]
    if len(lines) > MAX_IMPORT_LINES:
        flash(f'Up to {MAX_IMPORT_LINES} at a time, please.', 'danger')
        return render_template('playbook/import_ultiplays.html', title='Add plays from Ultiplays',
                               lines=request.form.get('lines'), play_type=play_type)
    existing = Play.query.filter_by(team_organization_id=team_id).all()
    names = {p.name.lower() for p in existing}
    urls = {extract_embed_url(p.ultiplay_embed) for p in existing if p.ultiplay_embed}
    added, skipped = [], []
    order = next_order(team_id, play_type)
    for line in lines:
        name, code = _import_line(line)
        if code is None:
            skipped.append((line, 'no https:// link or embed code'))
            continue
        url = extract_embed_url(code)
        if not name:  # numbered after any already added this way
            n = 1
            while f'ultiplays play {n}' in names:
                n += 1
            name = f'Ultiplays play {n}'
        name = name[:100]
        if url in urls:
            skipped.append((line, 'that link is already in the playbook'))
            continue
        if name.lower() in names:
            skipped.append((line, f'there is already a play called "{name}"'))
            continue
        play = Play(name=name, type=play_type, status='draft', ultiplay_embed=code, sort_order=order,
                    created_by=current_user.id, updated_by=current_user.id, team_organization_id=team_id)
        db.session.add(play)
        added.append(play)
        names.add(name.lower())
        urls.add(url)
        order += 1
    db.session.commit()
    return render_template('playbook/import_ultiplays.html', title='Add plays from Ultiplays',
                           added=added, skipped=skipped, play_type=play_type)


# ── Share links: one play, readable without signing in ───────────

@bp.route('/plays/<int:play_id>/share', methods=['POST'])
def share_play(play_id):
    import secrets
    coach_only()
    play = play_or_404(play_id)
    if request.form.get('stop'):
        play.share_token = None
        flash('The share link no longer works.', 'success')
    else:
        play.share_token = secrets.token_urlsafe(24)
        flash('Share link made: anyone with it can see this play, without signing in.', 'success')
    db.session.commit()
    return redirect(url_for('playbook.view_play', play_id=play.id) + '#share')


@bp.route('/shared/<token>')
def shared_play(token):
    from app.utils.editor_diagrams import data_uri
    play = Play.query.filter_by(share_token=token).first() if len(token) >= 20 else None
    if play is None or play.is_draft or not feature_on('playbook_enabled', play.team_organization_id):
        return render_template('error.html', error_message='This share link is not valid any more.'), 404
    stages = [{'label': d.step_label, 'caption': d.caption, 'src': data_uri(d)} for d in play.editor_diagrams]
    return render_template('playbook/shared.html', play=play, stages=[st for st in stages if st['src']],
                           team=play.team_organization_id)


# ── Add a play to a session ──────────────────────────────────────

def _in_games(play):
    """How the play went when called, all time: totals and the last few games."""
    from app.models.point import Point
    points = Point.query.filter_by(called_play_id=play.id, team_organization_id=play.team_organization_id).all()
    if not points:
        return None
    total = pb.play_results(points).get(play.id)
    by_game = {}
    for p in points:
        by_game.setdefault(p.game, []).append(p)
    games = sorted(by_game, key=lambda g: (g.date is None, g.date), reverse=True)[:5]
    return {'total': total, 'rate': pb.rate(total) if total else None,
            'games': [(g, pb.play_results(by_game[g]).get(play.id)) for g in games]}


def coming_sessions(team_id):
    from app.models.session import SessionPlan
    return (SessionPlan.query.filter(SessionPlan.team_organization_id == team_id,
                                     SessionPlan.date >= datetime.utcnow().date())
            .order_by(SessionPlan.date).limit(12).all())


@bp.route('/plays/<int:play_id>/add-to-session', methods=['POST'])
def add_to_session(play_id):
    """Add a part to a coming session that works on this play (with its
    first linked drill, if it has one)."""
    from app.models.session import SessionComponent, SessionPlan
    coach_only()
    play = play_or_404(play_id)
    session = SessionPlan.query.filter_by(id=request.form.get('session_id', type=int),
                                          team_organization_id=play.team_organization_id).first_or_404()
    last = db.session.query(db.func.max(SessionComponent.order)).filter_by(session_id=session.id).scalar()
    drill = play.drills[0] if play.drills else None
    component = SessionComponent(session_id=session.id, team_organization_id=play.team_organization_id,
                                 title=play.name[:100], component_type='drill', order=(last or 0) + 1,
                                 description=f'Work on the {play.type_label.lower()} play "{play.name}".',
                                 drill_id=drill.id if drill else None,
                                 duration_minutes=drill.recommended_duration if drill else None,
                                 focus_area=play.call or None)
    db.session.add(component)
    db.session.flush()
    component.plays.append(play)
    db.session.commit()
    flash(f'"{play.name}" added to {session.title}.', 'success')
    return redirect(url_for('session.detail', session_id=session.id))


# ── A game's call sheet, and how the called plays went ───────────

def game_or_404(game_id):
    from app.models.game import Game
    return Game.query.filter_by(id=game_id, team_organization_id=get_current_team_id()).first_or_404()


def game_points(game):
    from app.models.point import Point
    return Point.query.filter_by(game_id=game.id, team_organization_id=game.team_organization_id).all()


@bp.route('/games/<int:game_id>/sheet', methods=['GET', 'POST'])
def call_sheet(game_id):
    """The plays planned for a game, in order, and how each went when called."""
    from app.models.scouting import scouting_for_game
    game = game_or_404(game_id)
    team_id = game.team_organization_id
    linked, others = scouting_for_game(game)
    report = linked or (others[0] if others else None)
    if request.method == 'POST':
        coach_only()
        plays = {p.id: p for p in Play.query.filter_by(team_organization_id=team_id).filter(Play.status != 'retired')}
        if request.form.get('action') == 'from_plan' and report:
            wanted = [p.id for p in report.plays_in_order if p.id in plays]
            notes = {}
        else:
            wanted = [int(x) for x in request.form.getlist('play_id') if x.isdigit() and int(x) in plays]
            notes = {pid: (request.form.get(f'note_{pid}') or '').strip()[:120] for pid in wanted}
        old = {row.play_id: row for row in game.call_sheet}
        seen = []
        game.call_sheet = []
        for n, play_id in enumerate(dict.fromkeys(wanted), start=1):
            row = old.pop(play_id, None) or GameCallPlay(team_organization_id=team_id, play_id=play_id)
            row.order = n
            if play_id in notes:
                row.note = notes[play_id] or None
            game.call_sheet.append(row)
            seen.append(play_id)
        db.session.commit()
        flash(f'Call sheet saved: {len(seen)} play{"s" if len(seen) != 1 else ""}.', 'success')
        return redirect(url_for('playbook.call_sheet', game_id=game.id))

    rows = [r for r in game.call_sheet if r.play and (not r.play.is_draft or can_edit())]
    results = pb.play_results(game_points(game))
    called_off_sheet = [db.session.get(Play, pid) for pid in results if pid not in {r.play_id for r in rows}]
    choices = []
    if can_edit():
        choices = [p for p in Play.query.filter_by(team_organization_id=team_id).filter(Play.status != 'retired')
                   .order_by(Play.type.desc(), *_play_order())]
    return render_template('playbook/call_sheet.html', title=f'Call sheet vs {game.opponent}', game=game, rows=rows,
                           results=results, rate=pb.rate, report=report, choices=choices,
                           called_off_sheet=[p for p in called_off_sheet if p and (not p.is_draft or can_edit())],
                           my_part=_my_parts([r.play for r in rows], team_id))


def _my_parts(plays, team_id):
    mine = my_role_ids(team_id)
    return {p.id: next((a for r in mine for a in p.assignments if a.position_id == r), None) for p in plays}


@bp.route('/results')
def results():
    """Every play called in games this season: how often, and how often we scored."""
    from app.models.game import Game
    from app.models.point import Point
    from app.utils.season import scope_games, viewing_season
    team_id = get_current_team_id()
    games = scope_games(Game.query.filter_by(team_organization_id=team_id), team_id).all()
    points = Point.query.filter(Point.game_id.in_([g.id for g in games]), Point.called_play_id.isnot(None)).all() \
        if games else []
    results = pb.play_results(points)
    plays = {p.id: p for p in team_plays(team_id).filter(Play.id.in_(list(results) or [0]))}
    rows = sorted(((plays[pid], r) for pid, r in results.items() if pid in plays),
                  key=lambda pr: (-pr[1]['called'], pr[0].name.lower()))
    season = viewing_season(team_id)
    return render_template('playbook/results.html', title='How our plays went', rows=rows, rate=pb.rate,
                           season=season, games_with_calls=len({p.game_id for p in points}))


# ── Set-ups: starting positions saved from the editor ────────────

@bp.route('/setups')
def setups():
    coach_only()
    rows = PlaySetup.query.filter_by(team_organization_id=get_current_team_id()).order_by(PlaySetup.name).all()
    return render_template('playbook/setups.html', title='Set-ups', setups=rows)


@bp.route('/setups', methods=['POST'])
def save_setup():
    """Save the editor's current stage as a set-up (JSON from the editor)."""
    coach_only()
    data = request.get_json(silent=True) or {}
    name = ' '.join((data.get('name') or '').split())[:80]
    objects = data.get('objects')
    if not name or not isinstance(objects, list):
        return jsonify({'success': False, 'message': 'Give the set-up a name.'}), 400
    state = json.dumps({'field': data.get('field') if isinstance(data.get('field'), dict) else {}, 'objects': objects})
    if len(state) > 500_000:
        return jsonify({'success': False, 'message': 'That stage is too big to save as a set-up.'}), 400
    png = data.get('png') or ''
    image = png.split(',', 1)[1] if png.startswith('data:image/png;base64,') else None
    if image and len(image) > 3_000_000:
        image = None
    setup = PlaySetup(team_organization_id=get_current_team_id(), name=name, state_json=state, image_data=image,
                      type=data.get('type') if data.get('type') in TYPES else None, created_by=current_user.id)
    db.session.add(setup)
    db.session.commit()
    return jsonify({'success': True, 'id': setup.id, 'name': setup.name}), 201


@bp.route('/setups/<int:setup_id>/image')
def setup_image(setup_id):
    import base64
    setup = PlaySetup.query.filter_by(id=setup_id, team_organization_id=get_current_team_id()).first_or_404()
    if not setup.image_data:
        abort(404)
    from flask import make_response
    response = make_response(base64.b64decode(setup.image_data))
    response.headers['Content-Type'] = 'image/png'
    response.headers['Cache-Control'] = 'private, max-age=3600'
    return response


@bp.route('/setups/<int:setup_id>/rename', methods=['POST'])
def rename_setup(setup_id):
    coach_only()
    setup = PlaySetup.query.filter_by(id=setup_id, team_organization_id=get_current_team_id()).first_or_404()
    name = ' '.join((request.form.get('name') or '').split())[:80]
    if name:
        setup.name = name
        db.session.commit()
    return redirect(url_for('playbook.setups'))


@bp.route('/setups/<int:setup_id>/delete', methods=['POST'])
def delete_setup(setup_id):
    coach_only()
    setup = PlaySetup.query.filter_by(id=setup_id, team_organization_id=get_current_team_id()).first_or_404()
    db.session.delete(setup)
    db.session.commit()
    flash(f'Set-up "{setup.name}" deleted. Plays drawn from it keep their drawings.', 'success')
    return redirect(url_for('playbook.setups'))


# ── Photos (kept with Theory's, in the database) ─────────────────

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
    return jsonify({'url': url_for('playbook.image', image_id=image.id)})


@bp.route('/image/<int:image_id>')
def image(image_id):
    from app.routes.theory import serve_image
    return serve_image(TheoryImage.query.filter_by(id=image_id, team_organization_id=get_current_team_id())
                       .first_or_404())


# ── Team concepts moved to Theory ────────────────────────────────

@bp.route('/formation/<int:formation_id>')
def view_formation(formation_id):
    formation = Formation.query.filter_by(id=formation_id, team_organization_id=get_current_team_id()).first_or_404()
    if formation.moved_to_topic_id and feature_on('theory_enabled'):
        return redirect(url_for('theory.topic', topic_id=formation.moved_to_topic_id))
    abort(404)
