from flask import (
    Blueprint, abort, render_template, redirect, url_for, flash,
    request, jsonify, current_app, render_template_string, make_response
)
from flask_login import login_required, current_user
from app import db
from app.models.session import SessionPlan, SessionComponent, Attendance, SessionRSVP
from app.models.drill import SavedDrill, DrillDiagram
from app.models.player import Player
from datetime import datetime, timedelta
import json
from jinja2.utils import htmlsafe_json_dumps
import base64
import hmac
from flask_wtf.csrf import CSRFProtect
from app.utils.utils import admin_required, coach_required
from app.utils.season import scope_sessions
from app.utils.editor_diagrams import save_editor_diagrams
from app.forms.session import (
    SessionRSVPForm, SessionPlanForm, DrillForm, 
    SessionComponentForm, SessionFilterForm, AdminBulkRSVPForm,
)
from secrets import token_urlsafe
from app.utils.rsvp import (
    LABELS as rsvp_labels, STATUSES as RSVP_STATUSES, answers as rsvp_answers, attendee_visibility,
    counts as rsvp_counts, expected_players, plan_visible, set_rsvp,
)

csrf = CSRFProtect()

bp = Blueprint('session', __name__, url_prefix='/sessions')


# Existing Session Routes
@bp.route('/')
@login_required
def index():
    form = SessionFilterForm()
    
    # Get filter parameters
    focus_area = request.args.get('focus_area', '')
    date_range = request.args.get('date_range', 'all')
    session_type = request.args.get('session_type', '')
    
    # Set form values from query parameters
    if focus_area:
        form.focus_area.data = focus_area
    if date_range:
        form.date_range.data = date_range
    if session_type:
        form.session_type.data = session_type
    
    # Build query based on filters
    query = SessionPlan.query.filter_by(team_organization_id=get_current_team_id())
    
    if focus_area:
        query = query.filter(SessionPlan.focus_area == focus_area)
    
    if session_type:
        query = query.filter(SessionPlan.session_type == session_type)

    # Season plan filters (season / phase / block / squad)
    season = request.args.get('season', '')
    phase = request.args.get('phase', '')
    block = request.args.get('block', '')
    squad = request.args.get('squad', '')
    team_plans = SessionPlan.query.filter_by(team_organization_id=get_current_team_id())

    def distinct_values(*columns):
        rows = team_plans.with_entities(*columns).filter(columns[0].isnot(None)).distinct().all()
        return sorted(rows, key=lambda r: tuple('' if v is None else v for v in r))

    form.season.choices = [('', 'All Seasons')] + [(s, s) for (s,) in distinct_values(SessionPlan.season)]
    form.phase.choices = [('', 'All Phases')] + [
        (str(n), name or f'Phase {n}')
        for n, name in distinct_values(SessionPlan.phase_number, SessionPlan.phase_name)]
    form.block.choices = [('', 'All Blocks')] + [(b, b) for (b,) in distinct_values(SessionPlan.block)]
    form.squad.choices = [('', 'All Squads')] + [
        (value, label) for value, label in SessionPlan.SQUAD_CHOICES
        if value in {s for (s,) in distinct_values(SessionPlan.squad)}]
    form.season.data, form.phase.data, form.block.data, form.squad.data = season, phase, block, squad

    if season:
        query = query.filter(SessionPlan.season == season)
    else:
        query = scope_sessions(query)  # the club season being viewed
    if phase.isdigit():
        query = query.filter(SessionPlan.phase_number == int(phase))
    if block:
        query = query.filter(SessionPlan.block == block)
    if squad:
        query = query.filter(SessionPlan.squad == squad)
    
    if date_range != 'all':
        today = datetime.now().date()
        if date_range == 'past_week':
            start_date = today - timedelta(days=7)
        elif date_range == 'past_month':
            start_date = today - timedelta(days=30)
        elif date_range == 'past_year':
            start_date = today - timedelta(days=365)
        
        query = query.filter(SessionPlan.date >= start_date)
    
    # Get sessions and sort by date (newest first); a season's plans in week order
    if season:
        sessions = query.order_by(SessionPlan.week_number.asc(), SessionPlan.squad.asc(),
                                  SessionPlan.id.asc()).all()
    else:
        sessions = query.order_by(SessionPlan.date.desc()).all()

    # Build per-type sequential numbers (ascending by date, so earliest = #1)
    # First collect ALL sessions for the team ordered oldest-first to assign numbers
    all_sessions_ordered = SessionPlan.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SessionPlan.date.asc(), SessionPlan.id.asc()).all()
    type_counters = {}
    session_type_numbers = {}
    for s in all_sessions_ordered:
        stype = s.session_type or 'invited_training'
        type_counters[stype] = type_counters.get(stype, 0) + 1
        session_type_numbers[s.id] = type_counters[stype]

    # Get upcoming sessions (future dates)
    upcoming_sessions = SessionPlan.query.filter(
        SessionPlan.date >= datetime.now().date(),
        SessionPlan.team_organization_id == get_current_team_id()
    ).order_by(SessionPlan.date).limit(5).all()

    # Build a set of session IDs that the current user has already RSVPed for
    user_rsvped_sessions = set()
    if current_user.is_authenticated and current_user.player:
        from app.models.session import SessionRSVP
        existing_rsvps = SessionRSVP.query.filter_by(
            player_id=current_user.player.id
        ).all()
        user_rsvped_sessions = {r.session_id for r in existing_rsvps}

    return render_template(
        'session/index.html',
        sessions=sessions,
        upcoming_sessions=upcoming_sessions,
        form=form,
        session_type_numbers=session_type_numbers,
        user_rsvped_sessions=user_rsvped_sessions
    )

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@coach_required
def add_session():
    form = SessionPlanForm()
    squads = _squad_choices(form)

    if form.validate_on_submit():
        
        session_plan = SessionPlan(
            title=form.title.data,
            date=form.date.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            location=form.location.data,
            focus_area=form.focus_area.data,
            notes=form.notes.data,
            session_type=form.session_type.data,
            is_published=form.is_published.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        session_plan.squads = [s for s in squads if s.id in (form.squads.data or [])]
        
        db.session.add(session_plan)
        db.session.commit()
        
        flash(f'Session "{session_plan.title}" has been created. Now plan what you\'ll do.', 'success')
        return redirect(url_for('training.plan', session_id=session_plan.id))

    if request.method == 'GET' and request.args.get('date'):  # "add on this day" from the calendar
        try:
            form.date.data = datetime.strptime(request.args['date'], '%Y-%m-%d').date()
        except ValueError:
            pass
    return render_template('session/session_form.html', form=form, title='Add Session Plan')


def _squad_choices(form):
    """Fill the form's squad choices with the team's squads; returns them."""
    from app.utils.season import team_squads
    squads = team_squads(get_current_team_id())
    form.squads.choices = [(s.id, s.name) for s in squads]
    return squads

# Drill Library Routes
@bp.route('/drills')
@login_required
def drills():
    """Display the team's drill library, filtered by the search form"""
    query = SavedDrill.query.filter_by(team_organization_id=get_current_team_id())
    q = request.args.get('q', '').strip()
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(SavedDrill.title.ilike(like), SavedDrill.description.ilike(like)))
    skill_level = request.args.get('skill_level', '').strip()
    if skill_level:
        query = query.filter(SavedDrill.skill_level == skill_level)
    focus_area = request.args.get('focus_area', '').strip()
    if focus_area:
        query = query.filter(SavedDrill.focus_area.ilike(f'%{focus_area}%'))
    drills = query.order_by(SavedDrill.title).all()
    
    return render_template('session/drills/list.html', drills=drills)

@bp.route('/drills/add', methods=['GET', 'POST'])
@bp.route('/drills/add/<string:drill_type>', methods=['GET', 'POST'])
@login_required
@coach_required
def add_drill(drill_type='basic'):
    form = DrillForm()

    if form.validate_on_submit():
        
        drill = SavedDrill(
            title=form.title.data,
            description=form.description.data,
            setup_instructions=form.setup_instructions.data,
            recommended_duration=form.recommended_duration.data,
            min_players=form.min_players.data,
            max_players=form.max_players.data,
            skill_level=form.skill_level.data,
            focus_area=form.focus_area.data,
            equipment_needed=form.equipment_needed.data,
            ultiplay_embed=form.ultiplay_embed.data,
            created_by=current_user.id,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )

        db.session.add(drill)
        db.session.commit()

        flash(f'Drill "{drill.title}" has been created!', 'success')
        return redirect(url_for('session.drills'))

    return render_template('session/drills/form.html', form=form)

@bp.route('/drills/editor')
@bp.route('/drills/editor/<int:drill_id>')
@login_required
@coach_required
def drill_editor(drill_id=None):
    """Draw a drill diagram (players, cones, cuts and throws on a field)."""
    drill = None
    editor_state = None
    if drill_id:
        drill = SavedDrill.query.filter_by(
            id=drill_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        if drill.editor_diagram:
            editor_state = json.loads(drill.editor_diagram.editor_json)
    return render_template('session/drills/editor.html', drill=drill, editor_state=editor_state,
                           other_diagrams=[d for d in (drill.diagrams if drill else []) if not d.editor_json])


@bp.route('/drills/<int:drill_id>')
@login_required
def drill_detail(drill_id):
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    # Find the session ID associated with this drill (if any)
    session_component = SessionComponent.query.filter_by(
        drill_id=drill_id,
        team_organization_id=get_current_team_id()
    ).first()
    
    session_id = session_component.session_id if session_component else None

    # Drawn in stages: the page plays them as an animation
    animation = None
    if drill.editor_diagram:
        state = json.loads(drill.editor_diagram.editor_json)
        if len(state.get('stages') or []) > 1:
            animation = state

    return render_template('session/drills/detail.html', drill=drill, session_id=session_id,
                           animation=animation)


# Drill diagram images are stored in the database (see DrillDiagram). These
# routes are public so guest share links can show them; the filename must
# match the start of the image's hash, so ids alone can't be enumerated.
def _get_diagram_or_404(diagram_id, filename, digest_attr):
    diagram = DrillDiagram.query.get_or_404(diagram_id)
    digest = getattr(diagram, digest_attr)
    if not digest or filename.rsplit('.', 1)[0] != digest[:16]:
        abort(404)
    return diagram


def _immutable_response(body, mimetype):
    response = make_response(body)
    response.mimetype = mimetype
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.route('/drills/diagrams/<int:diagram_id>/<string:filename>')
def drill_diagram_image(diagram_id, filename):
    diagram = _get_diagram_or_404(diagram_id, filename, 'image_hash')
    if not diagram.image_data:
        abort(404)
    return _immutable_response(base64.b64decode(diagram.image_data), diagram.image_mime)


@bp.route('/drills/diagrams/<int:diagram_id>/svg/<string:filename>')
def drill_diagram_svg(diagram_id, filename):
    diagram = _get_diagram_or_404(diagram_id, filename, 'svg_hash')
    if not diagram.svg_data:
        abort(404)
    response = _immutable_response(diagram.svg_data, 'image/svg+xml')
    # SVG can carry script; stop it running if the file is opened directly.
    response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return response


# Drill API Routes (used by the drill editor, static/js/drill_editor.js)

def _int_or_none(value):
    try:
        return int(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _apply_editor_fields(drill, data):
    drill.title = (data.get('title') or 'Untitled Drill').strip()[:100]
    drill.description = data.get('description') or None
    drill.setup_instructions = data.get('setup_instructions') or None
    drill.recommended_duration = _int_or_none(data.get('recommended_duration'))
    drill.min_players = _int_or_none(data.get('min_players'))
    drill.max_players = _int_or_none(data.get('max_players'))
    drill.skill_level = (data.get('skill_level') or None) and data['skill_level'][:20]
    drill.focus_area = (data.get('focus_area') or None) and data['focus_area'][:100]
    drill.equipment_needed = (data.get('equipment_needed') or None) and data['equipment_needed'][:200]
    drill.is_public = bool(data.get('is_public'))


def _editor_payload():
    try:
        return json.loads(request.form.get('data') or '{}')
    except ValueError:
        abort(400)


@bp.route('/api/drills', methods=['POST'])
@login_required
@coach_required
def create_drill():
    """Create a drill from the drill editor."""
    drill = SavedDrill(created_by=current_user.id, team_organization_id=get_current_team_id())
    _apply_editor_fields(drill, _editor_payload())
    db.session.add(drill)
    error = save_editor_diagrams(drill)
    if error:
        db.session.rollback()
        return jsonify({'success': False, 'message': error}), 400
    db.session.commit()
    return jsonify({'success': True, 'drill_id': drill.id,
                    'editor_url': url_for('session.drill_editor', drill_id=drill.id),
                    'detail_url': url_for('session.drill_detail', drill_id=drill.id)}), 201


@bp.route('/api/drills/<int:drill_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def manage_drill(drill_id):
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    if request.method == 'GET':
        editor = drill.editor_diagram
        return jsonify({
            'success': True,
            'id': drill.id,
            'title': drill.title,
            'description': drill.description,
            'setup_instructions': drill.setup_instructions,
            'skill_level': drill.skill_level,
            'focus_area': drill.focus_area,
            'diagram_url': drill.first_diagram.image_url if drill.first_diagram else None,
            'editor': json.loads(editor.editor_json) if editor else None,
        })

    if not current_user.is_coach:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    if request.method == 'PUT':
        _apply_editor_fields(drill, _editor_payload())
        error = save_editor_diagrams(drill)
        if error:
            db.session.rollback()
            return jsonify({'success': False, 'message': error}), 400
        db.session.commit()
        return jsonify({'success': True, 'drill_id': drill.id,
                        'editor_url': url_for('session.drill_editor', drill_id=drill.id),
                        'detail_url': url_for('session.drill_detail', drill_id=drill.id)})

    # DELETE
    if drill.created_by != current_user.id and not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    SessionComponent.query.filter_by(drill_id=drill.id,
                                     team_organization_id=get_current_team_id()).delete()
    title = drill.title
    db.session.delete(drill)
    db.session.commit()
    return jsonify({'success': True, 'message': f'Drill "{title}" has been deleted'})


# Drill data API for component form auto-fill
@bp.route('/get_drill/<int:drill_id>')
@login_required
def get_drill(drill_id):
    """Return drill data as JSON for component form auto-fill"""
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()

    return jsonify({
        'id': drill.id,
        'title': drill.title,
        'description': drill.description or '',
        'setup_instructions': drill.setup_instructions or '',
        'recommended_duration': drill.recommended_duration,
        'min_players': drill.min_players,
        'max_players': drill.max_players,
        'skill_level': drill.skill_level or '',
        'focus_area': drill.focus_area or '',
        'equipment_needed': drill.equipment_needed or '',
        'ultiplay_embed': drill.ultiplay_embed or ''
    })


# Session Component Routes
@bp.route('/<int:session_id>/components')
@login_required
def components(session_id):
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    components = session_plan.components.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order).all()
    
    return render_template('session/components.html', session=session_plan, components=components)

@bp.route('/<int:session_id>/add_component', methods=['GET', 'POST'])
@login_required
@coach_required
def add_component(session_id):
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = SessionComponentForm()
    
    # Populate drill choices - only from current team
    form.drill_id.choices = [(0, 'None')] + [(d.id, d.title) for d in SavedDrill.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SavedDrill.title).all()]
    
    # Set default order to next available
    next_order = 1
    last_component = SessionComponent.query.filter_by(
        session_id=session_id,
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order.desc()).first()
    
    if last_component:
        next_order = last_component.order + 1
    form.order.data = next_order
    
    if form.validate_on_submit():
        
        component = SessionComponent(
            session_id=session_id,
            title=form.title.data,
            description=form.description.data,
            duration_minutes=form.duration_minutes.data,
            order=form.order.data,
            component_type=form.component_type.data,
            focus_area=form.focus_area.data,
            notes=form.notes.data,
            coach_cue=form.coach_cue.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        
        # If a saved drill was selected, associate it and copy its details
        if form.drill_id.data and form.drill_id.data > 0:
            drill = SavedDrill.query.filter_by(
                id=form.drill_id.data,
                team_organization_id=get_current_team_id()
            ).first()
            
            if drill:
                component.drill_id = drill.id
                if not form.description.data:
                    component.description = drill.description
                if not form.duration_minutes.data and drill.recommended_duration:
                    component.duration_minutes = drill.recommended_duration
                if not form.focus_area.data:
                    component.focus_area = drill.focus_area
        
        db.session.add(component)
        db.session.commit()
        
        flash(f'Component "{component.title}" has been added!', 'success')

        # Check if user wants to add another component
        if request.form.get('add_another'):
            return redirect(url_for('session.add_component', session_id=session_id))
        return redirect(url_for('session.detail', session_id=session_id))
    
    return render_template('session/component_form.html', form=form, session=session_plan, title='Add Session Component')

@bp.route('/edit_component/<int:component_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_component(component_id):
    component = SessionComponent.query.filter_by(
        id=component_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    session_plan = SessionPlan.query.filter_by(
        id=component.session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = SessionComponentForm(obj=component)
    
    # Populate drill choices - only from current team
    form.drill_id.choices = [(0, 'None')] + [(d.id, d.title) for d in SavedDrill.query.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SavedDrill.title).all()]
    
    if form.validate_on_submit():
        component.title = form.title.data
        component.description = form.description.data
        component.duration_minutes = form.duration_minutes.data
        component.order = form.order.data
        component.component_type = form.component_type.data
        component.focus_area = form.focus_area.data
        component.notes = form.notes.data
        component.coach_cue = form.coach_cue.data
        
        # Update drill association
        if form.drill_id.data and form.drill_id.data > 0:
            # Verify drill belongs to current team
            drill = SavedDrill.query.filter_by(
                id=form.drill_id.data,
                team_organization_id=get_current_team_id()
            ).first()
            
            if drill:
                component.drill_id = drill.id
            else:
                component.drill_id = None
        else:
            component.drill_id = None
        
        db.session.commit()
        
        flash(f'Component "{component.title}" has been updated!', 'success')
        return redirect(url_for('session.detail', session_id=component.session_id))
    
    return render_template('session/component_form.html', form=form, component=component, session=session_plan, title='Edit Session Component')

@bp.route('/delete_component/<int:component_id>', methods=['POST'])
@login_required
@coach_required
def delete_component(component_id):
    component = SessionComponent.query.filter_by(
        id=component_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    session_id = component.session_id
    title = component.title
    
    db.session.delete(component)
    db.session.commit()
    
    flash(f'Component "{title}" has been deleted!', 'success')
    return redirect(url_for('session.detail', session_id=session_id))

# Attendance Routes
@bp.route('/<int:session_id>/attendance', methods=['GET', 'POST'])
@login_required
@coach_required
def attendance(session_id):
    """The register: everyone the session is for, starting from what they
    said (Yes = present) until someone records what actually happened."""
    session_plan = _session_or_404(session_id)
    team_id = session_plan.team_organization_id
    records = {a.player_id: a for a in Attendance.query.filter_by(session_id=session_id)}
    answer_map = rsvp_answers([session_plan])
    answered = {pid for (_, pid) in answer_map}
    players = expected_players(session_plan, answered=answered | set(records))
    others = [p for p in Player.query.filter_by(team_organization_id=team_id, active=True)
              .order_by(Player.name) if p not in players]

    if request.method == 'POST':
        ids = {p.id for p in players + others}
        for player_id in ids:
            status = request.form.get(f'p{player_id}', '')
            record = records.get(player_id)
            if status in ATTENDANCE_STATUSES:
                if record is None:
                    record = Attendance(session_id=session_id, player_id=player_id, team_organization_id=team_id)
                    db.session.add(record)
                record.status = status
            elif record is not None and f'p{player_id}' in request.form:
                db.session.delete(record)
        db.session.commit()
        flash('Attendance saved.', 'success')
        return redirect(url_for('session.attendance', session_id=session_id))

    prefilled = not records
    rows = []
    for player in players:
        answer = answer_map.get((session_id, player.id))
        record = records.get(player.id)
        status = record.status if record else ('present' if answer and answer.status == 'attending' else '')
        rows.append({'player': player, 'answer': answer, 'status': status})
    return render_template('session/attendance.html', session=session_plan, rows=rows, others=others,
                           prefilled=prefilled, statuses=ATTENDANCE_STATUSES)


ATTENDANCE_STATUSES = ('present', 'late', 'excused', 'absent')


# RSVP Routes
def _session_or_404(session_id):
    return SessionPlan.query.filter_by(
        id=session_id, team_organization_id=get_current_team_id()).first_or_404()


@bp.route('/<int:session_id>/rsvp', methods=['GET', 'POST'])
@bp.route('/<int:session_id>/rsvp/<int:player_id>', methods=['GET', 'POST'])
@login_required
def rsvp(session_id, player_id=None):
    """A player's answer for one session; admins can answer for a player
    (the availability grid is the quick way to do that for many)."""
    session_plan = _session_or_404(session_id)
    if player_id is not None and not current_user.is_admin:
        abort(403)
    if player_id is None and not current_user.player:
        if current_user.is_coach:
            return redirect(url_for('training.grid'))
        flash('You need to link your account to a player before you can RSVP.', 'warning')
        return redirect(url_for('auth.link_player'))
    player = (Player.query.filter_by(id=player_id, team_organization_id=get_current_team_id()).first_or_404()
              if player_id is not None else current_user.player)

    existing_rsvp = SessionRSVP.query.filter_by(session_id=session_id, player_id=player.id).first()
    form = SessionRSVPForm(obj=existing_rsvp)
    if session_plan.is_cancelled and request.method == 'POST':
        flash('This session has been cancelled.', 'warning')
        return redirect(url_for('session.detail', session_id=session_id))
    if form.validate_on_submit():
        set_rsvp(session_plan, player, form.status.data, form.notes.data, keep_notes=False)
        db.session.commit()
        who = 'Your' if player_id is None else f'{player.name}\'s'
        flash(f'{who} answer is saved: {rsvp_labels[form.status.data]}.', 'success')
        if player_id is not None:
            return redirect(url_for('session.rsvps', session_id=session_id))
        return redirect(url_for('session.detail', session_id=session_id))

    return render_template('session/rsvp.html', form=form, session=session_plan,
                           existing_rsvp=existing_rsvp,
                           player=player if player_id is not None else None)


@bp.route('/<int:session_id>/admin_rsvp', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_rsvp(session_id):
    """Set the same answer for several players at once."""
    session_plan = _session_or_404(session_id)
    form = AdminBulkRSVPForm(team_organization_id=get_current_team_id())

    if form.validate_on_submit():
        status = form.status.data
        players = Player.query.filter(Player.id.in_(form.players.data),
                                      Player.team_organization_id == get_current_team_id()).all()
        for player in players:
            set_rsvp(session_plan, player, status, form.notes.data, keep_notes=False)
        db.session.commit()
        flash(f'{len(players)} players marked as {rsvp_labels[status]}.', 'success')
        return redirect(url_for('session.admin_rsvp', session_id=session_id, status=status))

    if request.method == 'GET':
        form.status.data = request.args.get('status', 'attending')
    current_status = form.status.data
    all_rsvps = SessionRSVP.query.filter_by(session_id=session_id).all()
    if request.method == 'GET':
        form.players.data = [r.player_id for r in all_rsvps if r.status == current_status]
    # Players already given another answer appear only under that answer
    elsewhere = {r.player_id for r in all_rsvps if r.status != current_status}
    form.players.choices = [(pid, label) for pid, label in form.players.choices if pid not in elsewhere]

    rsvps_by_status = {status: [r for r in all_rsvps if r.status == status] for status in RSVP_STATUSES}
    return render_template('session/admin_rsvp.html', session=session_plan, form=form,
                           rsvps_by_status=rsvps_by_status)


@bp.route('/<int:session_id>/rsvps')
@login_required
def rsvps(session_id):
    """Who is coming. Players see names, numbers or nothing, as the team
    chose in its session settings."""
    session_plan = _session_or_404(session_id)
    visibility = 'names' if current_user.is_coach else attendee_visibility(session_plan.team_organization_id)
    if visibility == 'hidden':
        flash('Your coaches keep who is coming to themselves.', 'info')
        return redirect(url_for('session.detail', session_id=session_id))

    answer_map = rsvp_answers([session_plan])
    answered = {pid for (_, pid) in answer_map}
    players = expected_players(session_plan, answered=answered)
    groups = {status: [] for status in RSVP_STATUSES + ('none',)}
    for player in players:
        answer = answer_map.get((session_plan.id, player.id))
        groups[answer.status if answer else 'none'].append((player, answer))

    return render_template('session/rsvps.html', session=session_plan, groups=groups,
                           names=(visibility == 'names'), show_unanswered=current_user.is_coach)


# Analytics Routes
@bp.route('/attendance_analytics')
@login_required
def attendance_analytics():
    # Get all sessions with dates, ordered by date
    today = datetime.now().date()

    sessions = SessionPlan.query.filter(
        SessionPlan.date != None,
        SessionPlan.date <= today,
        SessionPlan.team_organization_id == get_current_team_id(),
        SessionPlan.session_type != SessionPlan.SESSION_TYPE_POD
    ).order_by(SessionPlan.date).all()
    
    # Get all active players
    players = Player.query.filter_by(
        active=True,
        team_organization_id=get_current_team_id()
    ).order_by(Player.name).all()
    
    # Get selected player for individual trend
    selected_player_id = request.args.get('player_id', type=int)
    selected_player = None
    
    if selected_player_id:
        selected_player = Player.query.filter_by(
            id=selected_player_id,
            team_organization_id=get_current_team_id()
        ).first()
    
    # Calculate attendance statistics for each player
    player_stats = []
    for player in players:
        # Get attendance records for this player
        attendances = Attendance.query.join(SessionPlan).filter(
            Attendance.player_id == player.id,
            Attendance.team_organization_id == get_current_team_id(),
            SessionPlan.session_type != SessionPlan.SESSION_TYPE_POD
        ).all()
        
        # Count attendance by status
        present_count = sum(1 for a in attendances if a.status == 'present')
        late_count = sum(1 for a in attendances if a.status == 'late')
        absent_count = sum(1 for a in attendances if a.status == 'absent')
        excused_count = sum(1 for a in attendances if a.status == 'excused')
        
        # Calculate attendance rate
        total_sessions = len([
            s for s in sessions
            if not player.joined_team_date or s.date >= player.joined_team_date
        ])
        attended_sessions = present_count + late_count
        attendance_rate = (attended_sessions / total_sessions * 100) if total_sessions > 0 else 0
        
        player_stats.append({
            'player': player,
            'present': present_count,
            'late': late_count,
            'absent': absent_count,
            'excused': excused_count,
            'total_attended': attended_sessions,
            'attendance_rate': attendance_rate
        })
    
    # Sort player stats by attendance rate (descending)
    player_stats.sort(key=lambda x: x['attendance_rate'], reverse=True)
    
    # Calculate overall attendance statistics
    total_attendances = sum(p['total_attended'] for p in player_stats)
    total_possible = len(players) * len(sessions)
    overall_attendance_rate = (total_attendances / total_possible * 100) if total_possible > 0 else 0
    
    # Generate attendance trend data
    trend_data = []
    
    if selected_player:
        # Individual player trend
        attendance_by_session = {}
        attendances = Attendance.query.filter_by(
            player_id=selected_player.id,
            team_organization_id=get_current_team_id()
        ).all()
        
        for attendance in attendances:
            attendance_by_session[attendance.session_id] = attendance
        
        for session_plan in sessions:
            attendance = attendance_by_session.get(session_plan.id)
            status_value = 0  # Default: absent/unknown
            
            if attendance:
                if attendance.status == 'present':
                    status_value = 1
                elif attendance.status == 'late':
                    status_value = 0.5
                elif attendance.status == 'excused':
                    status_value = 0.25
            
            trend_data.append({
                'date': session_plan.date.strftime('%Y-%m-%d'),
                'title': session_plan.title,
                'status': attendance.status if attendance else 'unknown',
                'value': status_value
            })
    else:
        # Team trend
        for session_plan in sessions:
            present_count = Attendance.query.filter_by(
                session_id=session_plan.id, 
                status='present',
                team_organization_id=get_current_team_id()
            ).count()
            
            late_count = Attendance.query.filter_by(
                session_id=session_plan.id, 
                status='late',
                team_organization_id=get_current_team_id()
            ).count()
            
            absent_count = Attendance.query.filter_by(
                session_id=session_plan.id, 
                status='absent',
                team_organization_id=get_current_team_id()
            ).count()
            
            excused_count = Attendance.query.filter_by(
                session_id=session_plan.id, 
                status='excused',
                team_organization_id=get_current_team_id()
            ).count()
            
            trend_data.append({
                'date': session_plan.date.strftime('%Y-%m-%d'),
                'title': session_plan.title,
                'present': present_count,
                'late': late_count,
                'absent': absent_count,
                'excused': excused_count
            })
    
    return render_template(
        'session/attendance_analytics.html',
        sessions=sessions,
        players=players,
        player_stats=player_stats,
        overall_attendance_rate=overall_attendance_rate,
        trend_data=htmlsafe_json_dumps(trend_data),
        selected_player=selected_player
    )

@bp.route('/player_attendance/<int:player_id>')
@login_required
def player_attendance(player_id):
    player = Player.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Get all sessions with dates
    sessions = SessionPlan.query.filter(
        SessionPlan.date != None,
        SessionPlan.team_organization_id == get_current_team_id()
    ).order_by(SessionPlan.date).all()
    
    # Get attendance records for this player
    attendances = Attendance.query.filter_by(
        player_id=player_id,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Create a dictionary of attendance records by session ID
    attendance_by_session = {a.session_id: a for a in attendances}
    
    # Calculate attendance statistics
    present_count = sum(1 for a in attendances if a.status == 'present')
    late_count = sum(1 for a in attendances if a.status == 'late')
    absent_count = sum(1 for a in attendances if a.status == 'absent')
    excused_count = sum(1 for a in attendances if a.status == 'excused')
    
    total_sessions = len(sessions)
    attended_sessions = present_count + late_count
    attendance_rate = (attended_sessions / total_sessions * 100) if total_sessions > 0 else 0
    
    # Generate attendance trend data for chart
    trend_data = []
    for session_plan in sessions:
        attendance = attendance_by_session.get(session_plan.id)
        status = attendance.status if attendance else 'unknown'
        
        trend_data.append({
            'date': session_plan.date.strftime('%Y-%m-%d'),
            'title': session_plan.title,
            'status': status
        })
    
    # NEW CODE: Get tournament attendance data
    from app.models.tournament import Tournament
    from app.models.tournament_rsvp import TournamentRSVP
    from app.models.game import Game
    from app.models.game_player import GamePlayer
    
    # Get tournaments where the player was selected
    tournament_rsvps = TournamentRSVP.query.filter_by(
        player_id=player_id,
        team_organization_id=get_current_team_id()
    ).all()
    
    # Create a dictionary of tournament data
    tournament_data = {}
    
    for rsvp in tournament_rsvps:
        tournament = Tournament.query.filter_by(
            id=rsvp.tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if tournament:
            # Get games where player was assigned
            games = db.session.query(Game).join(
                GamePlayer, Game.id == GamePlayer.game_id
            ).filter(
                Game.tournament_id == tournament.id,
                GamePlayer.player_id == player_id,
                Game.team_organization_id == get_current_team_id(),
                GamePlayer.team_organization_id == get_current_team_id()
            ).all()
            
            tournament_data[tournament.id] = {
                'tournament': tournament,
                'rsvp': rsvp,
                'games': games
            }
    
    # Calculate tournament attendance statistics
    total_tournaments = len(tournament_data)
    tournaments_attending = sum(1 for t in tournament_data.values() if t['rsvp'].status == 'attending')
    tournaments_selected = sum(1 for t in tournament_data.values() if t['rsvp'].selected_by_admin)
    total_games = sum(len(t['games']) for t in tournament_data.values())
    
    return render_template(
        'session/player_attendance.html',
        player=player,
        sessions=sessions,
        attendance_by_session=attendance_by_session,
        present_count=present_count,
        late_count=late_count,
        absent_count=absent_count,
        excused_count=excused_count,
        attendance_rate=attendance_rate,
        trend_data=htmlsafe_json_dumps(trend_data),
        # Add tournament data to template context
        tournament_data=tournament_data,
        total_tournaments=total_tournaments,
        tournaments_attending=tournaments_attending,
        tournaments_selected=tournaments_selected,
        total_games=total_games
    )



# API Helper Functions
def get_csrf_token():
    """Get CSRF token from meta tag"""
    return render_template_string(
        '<meta name="csrf-token" content="{{ csrf_token() }}">'
    ).split('content="')[1].split('"')[0]

def validate_drill_data(data):
    """Validate drill data before saving"""
    required_fields = ['title']
    for field in required_fields:
        if field not in data or not data[field]:
            return False, f'Missing required field: {field}'
    return True, None

def clean_drill_elements(elements):
    """Clean and validate drill elements before saving"""
    valid_types = ['player', 'disc', 'cone', 'text', 'path']
    return [el for el in elements if el.get('type') in valid_types]

# Additional API Routes for Drill Management
@bp.route('/<int:session_id>/detail')
@login_required
def detail(session_id):
    """Show session details"""
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    components = session_plan.components.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order).all()
    
    attendances = session_plan.attendances.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    # Group attendances by status
    attendance_by_status = {
        'present': [],
        'absent': [],
        'late': [],
        'excused': []
    }
    
    for attendance in attendances:
        if attendance.status in attendance_by_status:
            attendance_by_status[attendance.status].append(attendance)

    my_answer = None
    if current_user.player:
        my_answer = rsvp_answers([session_plan], [current_user.player.id]).get(
            (session_plan.id, current_user.player.id))
    visibility = 'names' if current_user.is_coach else attendee_visibility(session_plan.team_organization_id)
    answer_counts = rsvp_counts(session_plan) if visibility != 'hidden' else None
    show_plan = plan_visible(session_plan, current_user)
    if not show_plan:
        components = []

    return render_template(
        'session/detail.html',
        session=session_plan,
        components=components,
        attendance_by_status=attendance_by_status,
        my_answer=my_answer,
        answer_counts=answer_counts,
        show_plan=show_plan,
    )

@bp.route('/edit/<int:session_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_session(session_id):
    """Edit an existing session"""
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = SessionPlanForm(obj=session_plan)
    squads = _squad_choices(form)
    if request.method == 'GET':
        form.squads.data = [s.id for s in session_plan.squads]

    if form.validate_on_submit():
        session_plan.title = form.title.data
        session_plan.date = form.date.data
        session_plan.start_time = form.start_time.data
        session_plan.end_time = form.end_time.data
        session_plan.location = form.location.data
        session_plan.focus_area = form.focus_area.data
        session_plan.notes = form.notes.data
        session_plan.session_type = form.session_type.data
        session_plan.is_published = form.is_published.data
        session_plan.squads = [s for s in squads if s.id in (form.squads.data or [])]
        
        db.session.commit()
        
        flash(f'Session plan "{session_plan.title}" has been updated!', 'success')
        return redirect(url_for('session.detail', session_id=session_plan.id))
    
    return render_template(
        'session/session_form.html',
        form=form,
        session=session_plan,
        title='Edit Session Plan'
    )

@bp.route('/delete/<int:session_id>', methods=['POST'])
@login_required
@coach_required
def delete_session(session_id):
    try:
        # Log the request
        current_app.logger.info(f"Delete request received for session {session_id}")
        
        session_plan = SessionPlan.query.filter_by(
            id=session_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        # Check if user has permission (optional)
        if not current_user.is_admin:
            current_app.logger.warning(f"User {current_user.id} attempted to delete session {session_id} without permission")
            flash('Permission denied', 'danger')
            return redirect(url_for('session.index'))

        title = session_plan.title

        # Delete associated records first
        SessionComponent.query.filter_by(
            session_id=session_id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        Attendance.query.filter_by(
            session_id=session_id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        SessionRSVP.query.filter_by(
            session_id=session_id,
            team_organization_id=get_current_team_id()
        ).delete()

        # Delete the session
        db.session.delete(session_plan)
        db.session.commit()

        current_app.logger.info(f"Successfully deleted session {session_id}")
        
        flash(f'Session "{title}" has been deleted!', 'success')
        return redirect(url_for('session.index'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting session {session_id}: {str(e)}")
        flash(f'Error deleting session: {str(e)}', 'danger')
        return redirect(url_for('session.index'))



@bp.route('/drills/edit/<int:drill_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_drill(drill_id):
    """Edit an existing drill"""
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = DrillForm(obj=drill)
    
    if form.validate_on_submit():
        drill.title = form.title.data
        drill.description = form.description.data
        drill.setup_instructions = form.setup_instructions.data
        drill.recommended_duration = form.recommended_duration.data
        drill.min_players = form.min_players.data
        drill.max_players = form.max_players.data
        drill.skill_level = form.skill_level.data
        drill.focus_area = form.focus_area.data
        drill.equipment_needed = form.equipment_needed.data
        drill.ultiplay_embed = form.ultiplay_embed.data
        drill.is_public = form.is_public.data if hasattr(form, 'is_public') else False
        
        db.session.commit()
        flash(f'Drill "{drill.title}" has been updated!', 'success')
        return redirect(url_for('session.drills'))
    
    return render_template(
        'session/drills/form.html',
        form=form,
        drill=drill,
        title='Edit Drill'
    )


@bp.route('/drills/delete/<int:drill_id>', methods=['POST'])
@login_required
@coach_required
def delete_drill(drill_id):
    """Delete a drill (form-based deletion)"""
    drill = SavedDrill.query.filter_by(
        id=drill_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    if drill.created_by != current_user.id and not current_user.is_admin:
        abort(403)

    try:
        # Delete associated components
        SessionComponent.query.filter_by(
            drill_id=drill.id,
            team_organization_id=get_current_team_id()
        ).delete()
        
        title = drill.title
        db.session.delete(drill)
        db.session.commit()
        
        flash(f'Drill "{title}" has been deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting drill: {str(e)}")
        flash('An error occurred while deleting the drill.', 'danger')

    return redirect(url_for('session.drills'))
    
@bp.errorhandler(401)
def unauthorized_error(error):
    return jsonify({
        'success': False,
        'message': 'Authentication required'
    }), 401

@bp.errorhandler(403)
def forbidden_error(error):
    return jsonify({
        'success': False,
        'message': 'Permission denied'
    }), 403

@bp.errorhandler(404)
def not_found_error(error):
    return jsonify({
        'success': False,
        'message': 'Resource not found'
    }), 404

@bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({
        'success': False,
        'message': 'Internal server error'
    }), 500


@bp.before_request
def before_request():
    """Log request information"""
    if 'static' in request.path:
        current_app.logger.debug(f"Static file request: {request.path}")

@bp.route('/<int:session_id>/export_pdf')
@login_required
def export_pdf(session_id):
    """Download the session plan as a PDF."""
    from io import BytesIO
    from flask import send_file
    from slugify import slugify
    from app.utils.pdf import html_to_pdf

    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    if not plan_visible(session_plan, current_user):
        flash("Your coaches haven't shared this plan yet.", 'info')
        return redirect(url_for('session.detail', session_id=session_id))

    components = session_plan.components.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order).all()

    attendance_by_status = {'present': [], 'absent': [], 'late': [], 'excused': []}
    for attendance in session_plan.attendances.filter_by(
            team_organization_id=get_current_team_id()):
        if attendance.status in attendance_by_status:
            attendance_by_status[attendance.status].append(attendance)

    html = render_template('session/pdf_export.html', session=session_plan,
                           components=components, attendance_by_status=attendance_by_status)
    try:
        pdf = html_to_pdf(html)
    except ImportError:
        current_app.logger.error('Session PDF export: playwright is not installed')
        flash('PDF export is not available: Playwright is not installed on the server.', 'danger')
        return redirect(url_for('session.detail', session_id=session_id))
    except Exception as e:
        current_app.logger.error(f'Session PDF export failed: {e}')
        flash('PDF export failed. Please try again or use the printable page.', 'danger')
        return redirect(url_for('session.detail', session_id=session_id))

    name = slugify(session_plan.title or 'session') or 'session'
    return send_file(BytesIO(pdf), mimetype='application/pdf', as_attachment=True,
                     download_name=f'session_{session_id}_{name}.pdf')

@bp.route('/<int:session_id>/printable')
@login_required
def printable_view(session_id):
    """Show printable view of session plan"""
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    if not plan_visible(session_plan, current_user):
        flash("Your coaches haven't shared this plan yet.", 'info')
        return redirect(url_for('session.detail', session_id=session_id))
    
    components = session_plan.components.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(SessionComponent.order).all()
    
    attendances = session_plan.attendances.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    # Group attendances by status
    attendance_by_status = {
        'present': [],
        'absent': [],
        'late': [],
        'excused': []
    }
    
    for attendance in attendances:
        if attendance.status in attendance_by_status:
            attendance_by_status[attendance.status].append(attendance)
    
    return render_template(
        'session/printable.html',
        session=session_plan,
        components=components,
        attendance_by_status=attendance_by_status
    )

        
# Add these imports to your existing imports at the top of session.py
from app.utils.team_filter import get_current_team_id

# Add this route to your session.py Blueprint

@bp.route('/<int:session_id>/guest/<string:share_token>')
def guest_view(session_id, share_token):
    """View session details without authentication using a share token"""
    session_plan = SessionPlan.query.filter_by(id=session_id).first_or_404()
    
    # Verify the share token matches
    if not session_plan.share_token or not hmac.compare_digest(session_plan.share_token, share_token):
        abort(404)  # Return 404 instead of 403 to hide existence
    
    # Check if token has expired (optional - if you added expiration)
    if hasattr(session_plan, 'share_token_expires') and session_plan.share_token_expires:
        if session_plan.share_token_expires < datetime.utcnow():
            abort(404)  # Token expired
    
    # Get components for this session
    components = session_plan.components.filter_by(
        team_organization_id=session_plan.team_organization_id
    ).order_by(SessionComponent.order).all()
    
    # Get attendance data
    attendances = session_plan.attendances.filter_by(
        team_organization_id=session_plan.team_organization_id
    ).all()
    
    # Group attendances by status
    attendance_by_status = {
        'present': [],
        'absent': [],
        'late': [],
        'excused': []
    }
    
    for attendance in attendances:
        if attendance.status in attendance_by_status:
            attendance_by_status[attendance.status].append(attendance)
    
    return render_template(
        'session/detail_guest.html',
        session=session_plan,
        components=components,
        attendance_by_status=attendance_by_status
    )


@bp.route('/<int:session_id>/generate-share-link')
@login_required
@coach_required
def generate_share_link(session_id):
    """Generate or retrieve a shareable guest link for a session"""
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Generate a share token if one doesn't exist
    if not session_plan.share_token:
        session_plan.share_token = token_urlsafe(32)
        
        # Optional: Set expiration date (e.g., 30 days from now)
        # Uncomment if you added share_token_expires to your model
        # session_plan.share_token_expires = datetime.utcnow() + timedelta(days=30)
        
        db.session.commit()
    
    # Generate the full share URL
    share_url = url_for('session.guest_view', 
                       session_id=session_plan.id, 
                       share_token=session_plan.share_token, 
                       _external=True)
    
    return jsonify({
        'success': True,
        'share_url': share_url,
        'share_token': session_plan.share_token
    })


@bp.route('/<int:session_id>/revoke-share-link', methods=['POST'])
@login_required
@coach_required
def revoke_share_link(session_id):
    """Revoke the shareable guest link for a session"""
    session_plan = SessionPlan.query.filter_by(
        id=session_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    # Clear the share token
    session_plan.share_token = None
    # session_plan.share_token_expires = None  # Uncomment if you added expiration
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Share link has been revoked'
    })
    
@bp.route('/<int:session_id>/quick_checkin', methods=['POST'])
@login_required
@admin_required
def quick_checkin(session_id):
    """Tap-to-mark attendance on the attendance page: one player's
    present / late / excused / absent, saved straight away."""
    session_plan = _session_or_404(session_id)
    data = request.get_json(silent=True) or {}
    player = Player.query.filter_by(
        id=data.get("player_id"), team_organization_id=session_plan.team_organization_id).first()
    if player is None:
        return {"status": "error", "message": "Player not found"}, 404
    status = data.get('status')
    if status not in ATTENDANCE_STATUSES:
        return {"status": "error", "message": "Unknown attendance status"}, 400

    record = Attendance.query.filter_by(session_id=session_id, player_id=player.id).first()
    if record is None:
        record = Attendance(session_id=session_id, player_id=player.id,
                            team_organization_id=session_plan.team_organization_id)
        db.session.add(record)
    record.status = status
    db.session.commit()
    return {"status": "ok", "player_id": player.id, "attendance": status}
