# app/routes/playbook.py
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify, current_app, abort, session
)
from flask_login import login_required, current_user
from app import db
from app.models.playbook import Play, Formation, PlayTag, PlayAssignment, PlayerPosition
from app.forms.playbook import PlayForm, FormationForm, PositionAssignmentForm
from werkzeug.utils import secure_filename
import os
import json
from app.utils.storage import store_file, delete_file, get_file_url
from app.utils.utils import admin_required
from app.utils.team_filter import get_current_team_id

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
    with app.app_context():
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
    """Per-position view: pick a position, see its instructions across all plays."""
    team_id = get_current_team_id()
    positions = PlayerPosition.query.filter_by(team_organization_id=team_id) \
        .order_by(PlayerPosition.name).all()

    selected = None
    assignments = []
    if position_id:
        selected = PlayerPosition.query.filter_by(
            id=position_id, team_organization_id=team_id).first_or_404()
        assignments = PlayAssignment.query.filter_by(
            position_id=selected.id, team_organization_id=team_id
        ).join(Play, PlayAssignment.play_id == Play.id) \
         .order_by(Play.type, *_play_order()).all()

    return render_template('playbook/position_view.html',
                           positions=positions, selected=selected,
                           assignments=assignments)


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
        # Find the highest existing play ID and add 1
        highest_id = db.session.query(db.func.max(Play.id)).scalar() or 0
        next_id = highest_id + 1

        play = Play(
            id=next_id,  # Explicitly set the ID to avoid conflicts
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

    return render_template('playbook/play_detail.html', play=play)

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
        # Find the highest existing formation ID and add 1
        highest_id = db.session.query(db.func.max(Formation.id)).scalar() or 0
        next_id = highest_id + 1

        formation = Formation(
            id=next_id,  # Explicitly set the ID to avoid conflicts
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
    return render_template('404.html'), 404

@bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.is_json:
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500
    return render_template('500.html'), 500

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
@admin_required
def manage_assignments(play_id):
    play = Play.query.filter_by(
        id=play_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    form = PositionAssignmentForm()

    # Get all positions for the dropdown (filter by team)
    form.position_id.choices = [(p.id, p.name) for p in PlayerPosition.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(PlayerPosition.name).all()]

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
            # Find the highest existing assignment ID and add 1
            highest_id = db.session.query(db.func.max(PlayAssignment.id)).scalar() or 0
            next_id = highest_id + 1

            assignment = PlayAssignment(
                id=next_id,  # Explicitly set the ID
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
@admin_required
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
