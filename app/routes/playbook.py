# app/routes/playbook.py
import json
from datetime import datetime

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify, current_app, abort
)
from flask_login import login_required, current_user
from app import db
from app.models.playbook import Play, Formation, PlayTag, PlayAssignment, PlayerPosition
from app.forms.playbook import PlayForm, FormationForm, PositionAssignmentForm
from app.utils.roles import drawing_role_ids, drawing_state, plays_by_role, team_roles
from app.utils.utils import admin_required, coach_required
from app.utils.team_filter import get_current_team_id
from app.utils.editor_diagrams import save_editor_diagrams

bp = Blueprint('playbook', __name__, url_prefix='/playbook')


def _play_order():
    """Manual sort order first (lower = first), then name."""
    return (db.func.coalesce(Play.sort_order, 999999), Play.name)


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


def _run_export_job(app, job_id, team_id, team_name, type_filter, tag_id):
    from app.utils.playbook_export import (
        generate_playbook_pdf, cache_key, store_cached_pdf
    )
    # test_request_context: templates render in background threads with an
    # anonymous user instead of crashing in context processors.
    with app.test_request_context():
        job = _export_jobs.get(job_id)
        if job is None:
            return
        try:
            formations = Formation.query.filter_by(team_organization_id=team_id) \
                .order_by(Formation.name).all()
            plays = Play.query.filter_by(team_organization_id=team_id) \
                .order_by(*_play_order()).all()

            def progress(pct, label):
                j = _export_jobs.get(job_id)
                if j is not None:
                    j['pct'] = pct
                    j['label'] = label

            pdf_bytes = generate_playbook_pdf(
                formations, plays, team_name,
                type_filter=type_filter, tag_id=tag_id, progress=progress)

            key = cache_key(team_id, formations, plays, type_filter, tag_id)
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
@login_required
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
    formations = Formation.query.filter_by(team_organization_id=team_id) \
        .order_by(Formation.name).all()
    plays = Play.query.filter_by(team_organization_id=team_id) \
        .order_by(*_play_order()).all()
    cached = cached_pdf(team_id, cache_key(team_id, formations, plays, type_filter, tag_id))
    if cached:
        job.update(state='ready', pct=100, label='Ready', pdf=cached,
                   filename=_export_filename(team_name, type_filter))
        return jsonify({'job_id': job_id, 'state': 'ready'})

    app = current_app._get_current_object()
    _threading.Thread(
        target=_run_export_job,
        args=(app, job_id, team_id, team_name, type_filter, tag_id),
        daemon=True
    ).start()
    return jsonify({'job_id': job_id, 'state': 'running'})


@bp.route('/export/status/<job_id>')
@login_required
def export_status(job_id):
    job = _export_jobs.get(job_id)
    if job is None or job['team_id'] != get_current_team_id():
        return jsonify({'state': 'unknown'}), 404
    payload = {'state': job['state'], 'pct': job['pct'], 'label': job['label']}
    if job['state'] == 'ready':
        payload['download_url'] = url_for('playbook.export_download', job_id=job_id)
    return jsonify(payload)


@bp.route('/export/download/<job_id>')
@login_required
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
@login_required
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

    formations = Formation.query.filter_by(team_organization_id=team_id) \
        .order_by(Formation.name).all()
    plays = Play.query.filter_by(team_organization_id=team_id) \
        .order_by(*_play_order()).all()

    def respond(pdf_bytes):
        suffix = f'_{type_filter}' if type_filter else ''
        filename = (f"{team_name.replace(' ', '_').lower()}_playbook{suffix}"
                    f"_{datetime.now():%Y-%m-%d}.pdf")
        return send_file(BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)

    # Serve from cache when nothing has changed
    key = cache_key(team_id, formations, plays, type_filter, tag_id)
    cached = cached_pdf(team_id, key)
    if cached:
        return respond(cached)

    try:
        pdf_bytes = generate_playbook_pdf(formations, plays, team_name,
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


@bp.route('/positions')
@bp.route('/positions/<int:position_id>')
@login_required
def position_view(position_id=None):
    """By role: pick a role and see every play it's in, with what it does
    and a link that shows just its path. A player who hasn't picked one
    starts on their main role."""
    team_id = get_current_team_id()
    positions = team_roles(team_id)
    mine = my_role_ids(team_id)
    if position_id is None and mine:
        return redirect(url_for('playbook.position_view', position_id=mine[0]))

    selected = None
    entries = []
    if position_id:
        selected = PlayerPosition.query.filter_by(
            id=position_id, team_organization_id=team_id).first_or_404()
        for play in plays_by_role(team_id).get(selected.id, []):
            assignment = next((a for a in play.assignments if a.position_id == selected.id), None)
            entries.append({'play': play, 'assignment': assignment,
                            'drawn': selected.id in drawing_role_ids(drawing_state(play))})

    return render_template('playbook/position_view.html',
                           positions=positions, selected=selected, entries=entries, mine=mine)


def my_role_ids(team_id):
    """The signed-in player's roles this season, main role first."""
    from app.routes.roles import roles_season
    from app.utils.roles import player_roles
    from app.utils.season import roster_entry
    player = current_user.player if current_user.is_authenticated else None
    if player is None:
        return []
    return [r.role_id for r in player_roles(roster_entry(player, roles_season(team_id)))]


# Main Routes
@bp.route('/')
@login_required
def index():
    """Display playbook overview"""
    offensive_plays = Play.query.filter_by(
        type='offense',
        team_organization_id=get_current_team_id()
    ).order_by(*_play_order()).all()

    defensive_plays = Play.query.filter_by(
        type='defense',
        team_organization_id=get_current_team_id()
    ).order_by(*_play_order()).all()

    formations = Formation.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(Formation.name).all()

    all_tags = PlayTag.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(PlayTag.name).all()

    return render_template('playbook/index.html',
                         offensive_plays=offensive_plays,
                         defensive_plays=defensive_plays,
                         formations=formations,
                         all_tags=all_tags)

# Play Routes
@bp.route('/plays/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_play():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))

    form = PlayForm()

    # Update formation choices to only include formations from current team
    form.formation_id.choices = [(0, 'None')] + [
        (f.id, f.name) for f in Formation.query.filter_by(
            team_organization_id=get_current_team_id()
        ).order_by(Formation.name).all()
    ]

    # Update tag choices to only include tags from current team
    form.tags.choices = [(t.id, t.name) for t in PlayTag.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(PlayTag.name).all()]

    if form.validate_on_submit():

        play = Play(
            name=form.name.data,
            type=form.type.data,
            description=form.description.data,
            notes=form.notes.data,
            ultiplay_embed=form.ultiplay_embed.data,
            image_url=form.image_url.data,
            sort_order=form.sort_order.data,
            created_by=current_user.id,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )

        if form.formation_id.data and form.formation_id.data > 0:
            # Verify formation belongs to current team
            formation = Formation.query.filter_by(
                id=form.formation_id.data,
                team_organization_id=get_current_team_id()
            ).first()

            if formation:
                play.formation_id = formation.id

        # Handle tags if any are selected
        if form.tags.data:
            for tag_id in form.tags.data:
                # Verify tag belongs to current team
                tag = PlayTag.query.filter_by(
                    id=tag_id,
                    team_organization_id=get_current_team_id()
                ).first()

                if tag:
                    play.tags.append(tag)

        db.session.add(play)
        db.session.commit()

        flash(f'Play "{play.name}" has been created!', 'success')
        return redirect(url_for('playbook.index'))

    return render_template('playbook/play_form.html', form=form, title='Add Play')


@bp.route('/plays/<int:play_id>')
@login_required
def view_play(play_id):
    play = Play.query.filter_by(
        id=play_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    # Drawn in stages: the page plays them as an animation. Players given
    # roles: pick a role to see just their path (one stage too).
    state = drawing_state(play)
    drawn_roles = drawing_role_ids(state)
    animation = state if state and (len(state.get('stages') or []) > 1 or drawn_roles) else None
    roles = team_roles(play.team_organization_id)
    said = {a.position_id: a for a in play.assignments}
    who = [{'role': r, 'assignment': said.get(r.id), 'drawn': r.id in drawn_roles}
           for r in roles if r.id in said or r.id in drawn_roles]
    who += [{'role': a.position, 'assignment': a, 'drawn': False} for a in play.assignments
            if a.position is None]

    return render_template('playbook/play_detail.html', play=play, animation=animation, who=who,
                           animation_roles=[r for r in roles if r.id in drawn_roles])


# ── Game-day cards: the playbook on a phone ──────────────────────
@bp.route('/cards')
@login_required
def cards():
    """One card per play, drawing first, for looking over before a game.
    ?type=offense|defense filters; ?report=<scouting report> shows the plays
    picked for that game."""
    from app.models.scouting import ScoutingReport
    team_id = get_current_team_id()
    report = None
    report_id = request.args.get('report', type=int)
    if report_id:
        report = ScoutingReport.query.filter_by(id=report_id, team_organization_id=team_id).first_or_404()
        plays = report.plays_in_order
    else:
        plays = Play.query.filter_by(team_organization_id=team_id).order_by(Play.type.desc(), *_play_order()).all()
    type_filter = request.args.get('type')
    if type_filter in ('offense', 'defense'):
        plays = [p for p in plays if p.type == type_filter]
    else:
        type_filter = None
    # Each card's link picks out the player's own role, when it's in the drawing
    mine = my_role_ids(team_id)
    my_path = {}
    for play in plays:
        drawn = drawing_role_ids(drawing_state(play)) if mine else set()
        my_path[play.id] = next((r for r in mine if r in drawn), None)
    return render_template('playbook/cards.html', plays=plays, report=report, type_filter=type_filter,
                           my_path=my_path)


# ── Drawing a play in the drill editor ───────────────────────────
@bp.route('/plays/draw')
@bp.route('/plays/<int:play_id>/draw')
@login_required
@admin_required
def draw_play(play_id=None):
    """Draw a play on the field, in stages, with the drill editor."""
    play = None
    editor_state = None
    if play_id:
        play = Play.query.filter_by(id=play_id, team_organization_id=get_current_team_id()).first_or_404()
        if play.editor_diagram:
            editor_state = json.loads(play.editor_diagram.editor_json)
    formations = (Formation.query.filter_by(team_organization_id=get_current_team_id())
                  .order_by(Formation.name).all())
    return render_template('playbook/play_editor.html', play=play, drill=None, editor_state=editor_state,
                           formations=formations, other_diagrams=[],
                           roles=[{'id': r.id, 'name': r.name, 'line': r.line or ''}
                                  for r in team_roles(get_current_team_id())],
                           new_type=request.args.get('type') if request.args.get('type') in ('offense', 'defense') else 'offense')


def _apply_play_fields(play, data):
    play.name = (data.get('title') or 'Untitled Play').strip()[:100]
    play.description = data.get('description') or None
    play.notes = data.get('notes') or None
    if data.get('type') in ('offense', 'defense'):
        play.type = data['type']
    play.type = play.type or 'offense'
    try:
        formation_id = int(data.get('formation_id') or 0)
    except (TypeError, ValueError):
        formation_id = 0
    formation = Formation.query.filter_by(id=formation_id, team_organization_id=get_current_team_id()).first() \
        if formation_id else None
    play.formation_id = formation.id if formation else None


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
@login_required
@admin_required
def create_drawn_play():
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
@login_required
@admin_required
def update_drawn_play(play_id):
    play = Play.query.filter_by(id=play_id, team_organization_id=get_current_team_id()).first_or_404()
    _apply_play_fields(play, _play_payload())
    error = save_editor_diagrams(play, source='Play editor')
    if error:
        db.session.rollback()
        return jsonify({'success': False, 'message': error}), 400
    play.updated_at = datetime.utcnow()  # the PDF cache goes by it
    db.session.commit()
    return _play_saved(play)

@bp.route('/plays/<int:play_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_play(play_id):
    play = Play.query.filter_by(
        id=play_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    form = PlayForm(obj=play)

    # Update formation choices to only include formations from current team
    form.formation_id.choices = [(0, 'None')] + [
        (f.id, f.name) for f in Formation.query.filter_by(
            team_organization_id=get_current_team_id()
        ).order_by(Formation.name).all()
    ]

    # Update tag choices to only include tags from current team
    form.tags.choices = [(t.id, t.name) for t in PlayTag.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(PlayTag.name).all()]

    if form.validate_on_submit():
        play.name = form.name.data
        play.type = form.type.data
        play.description = form.description.data
        play.notes = form.notes.data
        play.ultiplay_embed = form.ultiplay_embed.data
        play.image_url = form.image_url.data
        play.sort_order = form.sort_order.data

        if form.formation_id.data and form.formation_id.data > 0:
            # Verify formation belongs to current team
            formation = Formation.query.filter_by(
                id=form.formation_id.data,
                team_organization_id=get_current_team_id()
            ).first()

            if formation:
                play.formation_id = formation.id
            else:
                play.formation_id = None
        else:
            play.formation_id = None

        db.session.commit()
        flash(f'Play "{play.name}" has been updated!', 'success')
        return redirect(url_for('playbook.view_play', play_id=play.id))

    return render_template('playbook/play_form.html', form=form, play=play, title='Edit Play')


# Formation Routes
@bp.route('/formations/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_formation():
    form = FormationForm()
    if form.validate_on_submit():

        formation = Formation(
            name=form.name.data,
            type=form.type.data,
            description=form.description.data,
            ultiplay_embed=form.ultiplay_embed.data,
            imgur_url=form.imgur_url.data,
            created_by=current_user.id,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )

        # Debug print
        current_app.logger.debug(f"Creating formation with imgur_url: {formation.imgur_url}")

        db.session.add(formation)
        db.session.commit()

        flash(f'Team concept "{formation.name}" has been created!', 'success')
        return redirect(url_for('playbook.index'))

    return render_template('playbook/formation_form.html', form=form, title='Add Team Concept')

# Error handlers
@bp.errorhandler(404)
def not_found_error(error):
    if request.is_json:
        return jsonify({
            'success': False,
            'message': 'Resource not found'
        }), 404
    return render_template('error.html', error_message='Page not found.'), 404

@bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.is_json:
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500
    return render_template('error.html', error_message='Something went wrong. Please try again.'), 500

@bp.route('/formations/edit/<int:formation_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_formation(formation_id):
    formation = Formation.query.filter_by(
        id=formation_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    form = FormationForm(obj=formation)

    if form.validate_on_submit():
        formation.name = form.name.data
        formation.type = form.type.data
        formation.description = form.description.data
        formation.ultiplay_embed = form.ultiplay_embed.data

        # Make sure this line is present
        formation.imgur_url = form.imgur_url.data

        # Debug print
        current_app.logger.debug(f"Saving formation with imgur_url: {formation.imgur_url}")

        db.session.commit()
        flash(f'Team concept "{formation.name}" has been updated!', 'success')
        return redirect(url_for('playbook.view_formation', formation_id=formation.id))

    return render_template('playbook/formation_form.html', form=form, formation=formation, title='Edit Formation')

# Also add a delete route for formations
@bp.route('/plays/<int:play_id>/delete', methods=['POST'])  # Changed to match JS URL
@login_required
@admin_required
def delete_play(play_id):
    if not current_user.is_admin:
        return jsonify({
            'success': False,
            'message': 'Permission denied'
        }), 403

    play = Play.query.filter_by(
        id=play_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    try:
        title = play.name
        db.session.delete(play)
        db.session.commit()

        flash(f'Play "{title}" has been deleted!', 'success')
        return redirect(url_for('playbook.index'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting play: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while deleting the play.'
        }), 500

@bp.route('/formations/<int:formation_id>/delete', methods=['POST'])  # Changed to match JS URL
@login_required
@admin_required
def delete_formation(formation_id):
    if not current_user.is_admin:
        return jsonify({
            'success': False,
            'message': 'Permission denied'
        }), 403

    formation = Formation.query.filter_by(
        id=formation_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    # Check if formation is being used by any plays
    plays_using_formation = Play.query.filter_by(
        formation_id=formation_id,
        team_organization_id=get_current_team_id()
    ).all()

    if plays_using_formation:
        return jsonify({
            'success': False,
            'message': 'Cannot delete formation that is being used by plays.'
        }), 400

    try:
        name = formation.name
        db.session.delete(formation)
        db.session.commit()

        flash(f'Formation "{name}" has been deleted!', 'success')
        return redirect(url_for('playbook.index'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting formation: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while deleting the formation.'
        }), 500


@bp.route('/formation/<int:formation_id>')
@login_required
def view_formation(formation_id):
    formation = Formation.query.filter_by(
        id=formation_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    # Get plays that use this formation
    related_plays = Play.query.filter_by(
        formation_id=formation_id,
        team_organization_id=get_current_team_id()
    ).all()

    # Debug print
    current_app.logger.debug(f"Formation ID: {formation.id}, Name: {formation.name}")
    current_app.logger.debug(f"Imgur URL: {formation.imgur_url}")

    return render_template('playbook/view_formation.html',
                          formation=formation,
                          related_plays=related_plays)

@bp.route('/plays/<int:play_id>/assignments', methods=['GET', 'POST'])
@login_required
@coach_required
def manage_assignments(play_id):
    play = Play.query.filter_by(
        id=play_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    form = PositionAssignmentForm()

    # Get all positions for the dropdown (filter by team)
    form.position_id.choices = [(r.id, f'{r.name} ({r.line_label})') for r in team_roles(get_current_team_id())]

    if form.validate_on_submit():
        # Check if assignment for this position already exists
        existing = PlayAssignment.query.filter_by(
            play_id=play.id,
            position_id=form.position_id.data,
            team_organization_id=get_current_team_id()
        ).first()

        if existing:
            existing.instructions = form.instructions.data
            flash('Position assignment updated', 'success')
        else:

            assignment = PlayAssignment(
                play_id=play.id,
                position_id=form.position_id.data,
                instructions=form.instructions.data,
                team_organization_id=get_current_team_id()  # Add team organization ID
            )
            db.session.add(assignment)
            flash('Position assignment added', 'success')

        db.session.commit()
        return redirect(url_for('playbook.manage_assignments', play_id=play.id))

    # Get existing assignments
    assignments = PlayAssignment.query.filter_by(
        play_id=play.id,
        team_organization_id=get_current_team_id()
    ).all()

    return render_template('playbook/assignments.html',
                          play=play, form=form, assignments=assignments)

@bp.route('/plays/<int:play_id>/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
@coach_required
def delete_assignment(play_id, assignment_id):
    # Verify the play belongs to the current team
    play = Play.query.filter_by(
        id=play_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    assignment = PlayAssignment.query.filter_by(
        id=assignment_id,
        play_id=play_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    # Verify the assignment belongs to the specified play
    if assignment.play_id != play_id:
        abort(404)

    db.session.delete(assignment)
    db.session.commit()
    flash('Assignment deleted', 'success')
    return redirect(url_for('playbook.manage_assignments', play_id=play_id))
