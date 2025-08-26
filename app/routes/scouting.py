from flask import current_app, Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from app import db
from app.models.scouting import ScoutingReport, OpponentPlayer, ScoutingClip
from app.models.tournament import Tournament
from app.models.game import Game
from app.forms.scouting import ScoutingReportForm, OpponentPlayerForm, ScoutingClipForm, ScoutingFilterForm
import re
from flask_wtf.csrf import CSRFProtect
from app.utils.utils import admin_required, coach_required, stat_taker_required

csrf = CSRFProtect()

bp = Blueprint('scouting', __name__, url_prefix='/scouting')

# Helper function to get current team ID
def get_current_team_id():
    if current_user.is_admin:
        return session.get('current_team_id')
    return current_user.team_organization_id

@bp.route('/')
@login_required
def index():
    form = ScoutingFilterForm()
    
    # Get filter parameters
    tournament_id = request.args.get('tournament_id', type=int)
    
    # Set form values from query parameters
    if tournament_id:
        form.tournament_id.data = tournament_id
    
    # Build query based on filters
    query = ScoutingReport.query.filter_by(team_organization_id=get_current_team_id())
    
    if tournament_id:
        # Verify tournament belongs to current team
        tournament = Tournament.query.filter_by(
            id=tournament_id,
            team_organization_id=get_current_team_id()
        ).first()
        
        if tournament:
            query = query.filter(ScoutingReport.tournament_id == tournament_id)
    
    # Get reports and sort by date (newest first)
    reports = query.order_by(ScoutingReport.date.desc()).all()
    
    return render_template('scouting/index.html', reports=reports, form=form)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@coach_required
def add_report():
    form = ScoutingReportForm()
    
    # Update tournament choices to only include tournaments from current team
    form.tournament_id.choices = [(0, 'None')] + [
        (t.id, t.name) for t in Tournament.query.filter_by(
            team_organization_id=get_current_team_id()
        ).order_by(Tournament.start_date.desc()).all()
    ]
    
    # Update game choices to only include games from current team
    form.game_id.choices = [(0, 'None')] + [
        (g.id, f"{g.opponent} ({g.date.strftime('%Y-%m-%d')})") for g in Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).order_by(Game.date.desc()).all()
    ]
    
    if form.validate_on_submit():
        # Find the highest existing report ID and add 1
        highest_id = db.session.query(db.func.max(ScoutingReport.id)).scalar() or 0
        next_id = highest_id + 1
        
        report = ScoutingReport(
            id=next_id,  # Explicitly set the ID to avoid conflicts
            team_name=form.team_name.data,
            date=form.date.data,
            tournament_id=form.tournament_id.data if form.tournament_id.data > 0 else None,
            game_id=form.game_id.data if form.game_id.data > 0 else None,
            offense_strategy=form.offense_strategy.data,
            defense_strategy=form.defense_strategy.data,
            strengths=form.strengths.data,
            weaknesses=form.weaknesses.data,
            notes=form.notes.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        
        db.session.add(report)
        db.session.commit()
        
        flash(f'Scouting report for "{report.team_name}" has been created!', 'success')
        return redirect(url_for('scouting.detail', report_id=report.id))
    
    return render_template('scouting/report_form.html', form=form, title='Add Scouting Report')

@bp.route('/edit/<int:report_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_report(report_id):
    report = ScoutingReport.query.filter_by(
        id=report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = ScoutingReportForm(obj=report)
    
    # Update tournament choices to only include tournaments from current team
    form.tournament_id.choices = [(0, 'None')] + [
        (t.id, t.name) for t in Tournament.query.filter_by(
            team_organization_id=get_current_team_id()
        ).order_by(Tournament.start_date.desc()).all()
    ]
    
    # Update game choices to only include games from current team
    form.game_id.choices = [(0, 'None')] + [
        (g.id, f"{g.opponent} ({g.date.strftime('%Y-%m-%d')})") for g in Game.query.filter_by(
            team_organization_id=get_current_team_id()
        ).order_by(Game.date.desc()).all()
    ]
    
    if form.validate_on_submit():
        report.team_name = form.team_name.data
        report.date = form.date.data
        
        # Verify tournament belongs to current team if selected
        if form.tournament_id.data > 0:
            tournament = Tournament.query.filter_by(
                id=form.tournament_id.data,
                team_organization_id=get_current_team_id()
            ).first()
            report.tournament_id = tournament.id if tournament else None
        else:
            report.tournament_id = None
            
        # Verify game belongs to current team if selected
        if form.game_id.data > 0:
            game = Game.query.filter_by(
                id=form.game_id.data,
                team_organization_id=get_current_team_id()
            ).first()
            report.game_id = game.id if game else None
        else:
            report.game_id = None
            
        report.offense_strategy = form.offense_strategy.data
        report.defense_strategy = form.defense_strategy.data
        report.strengths = form.strengths.data
        report.weaknesses = form.weaknesses.data
        report.notes = form.notes.data
        
        db.session.commit()
        
        flash(f'Scouting report for "{report.team_name}" has been updated!', 'success')
        return redirect(url_for('scouting.detail', report_id=report.id))
    
    return render_template('scouting/report_form.html', form=form, report=report, title='Edit Scouting Report')

@bp.route('/delete/<int:report_id>', methods=['POST'])
@login_required
@coach_required
def delete_report(report_id):
    try:
        report = ScoutingReport.query.filter_by(
            id=report_id,
            team_organization_id=get_current_team_id()
        ).first_or_404()
        
        team_name = report.team_name
        
        db.session.delete(report)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Scouting report for "{team_name}" has been deleted!'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting scouting report: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500




@bp.route('/<int:report_id>')
@login_required
def detail(report_id):
    report = ScoutingReport.query.filter_by(
        id=report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    players = report.players.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OpponentPlayer.jersey_number).all()
    
    clips = report.clips.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    return render_template('scouting/detail.html', report=report, players=players, clips=clips)

@bp.route('/<int:report_id>/players')
@login_required
@coach_required
def players(report_id):
    report = ScoutingReport.query.filter_by(
        id=report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    players = report.players.filter_by(
        team_organization_id=get_current_team_id()
    ).order_by(OpponentPlayer.jersey_number).all()
    
    return render_template('scouting/players.html', report=report, players=players)

@bp.route('/<int:report_id>/add_player', methods=['GET', 'POST'])
@login_required
@coach_required
def add_player(report_id):
    report = ScoutingReport.query.filter_by(
        id=report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = OpponentPlayerForm()
    
    if form.validate_on_submit():
        # Find the highest existing player ID and add 1
        highest_id = db.session.query(db.func.max(OpponentPlayer.id)).scalar() or 0
        next_id = highest_id + 1
        
        player = OpponentPlayer(
            id=next_id,  # Explicitly set the ID
            scouting_report_id=report.id,
            name=form.name.data,
            jersey_number=form.jersey_number.data,
            position=form.position.data,
            height=form.height.data,
            gender=form.gender.data,
            throwing_ability=form.throwing_ability.data,
            cutting_ability=form.cutting_ability.data,
            defensive_ability=form.defensive_ability.data,
            athletic_ability=form.athletic_ability.data,
            preferred_throws=form.preferred_throws.data,
            notes=form.notes.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        
        db.session.add(player)
        db.session.commit()
        
        flash(f'Player "{player.name}" has been added!', 'success')
        return redirect(url_for('scouting.players', report_id=report.id))
    
    return render_template('scouting/player_form.html', form=form, report=report, title='Add Player')

@bp.route('/edit_player/<int:player_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_player(player_id):
    player = OpponentPlayer.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    report = ScoutingReport.query.filter_by(
        id=player.scouting_report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = OpponentPlayerForm(obj=player)
    
    if form.validate_on_submit():
        player.name = form.name.data
        player.jersey_number = form.jersey_number.data
        player.position = form.position.data
        player.height = form.height.data
        player.gender = form.gender.data
        player.throwing_ability = form.throwing_ability.data
        player.cutting_ability = form.cutting_ability.data
        player.defensive_ability = form.defensive_ability.data
        player.athletic_ability = form.athletic_ability.data
        player.preferred_throws = form.preferred_throws.data
        player.notes = form.notes.data
        
        db.session.commit()
        
        flash(f'Player "{player.name}" has been updated!', 'success')
        return redirect(url_for('scouting.players', report_id=player.scouting_report_id))
    
    return render_template('scouting/player_form.html', form=form, player=player, report=report, title='Edit Player')

@bp.route('/delete_player/<int:player_id>', methods=['POST'])
@login_required
@coach_required
def delete_player(player_id):
    player = OpponentPlayer.query.filter_by(
        id=player_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    report_id = player.scouting_report_id
    name = player.name
    
    db.session.delete(player)
    db.session.commit()
    
    flash(f'Player "{name}" has been deleted!', 'success')
    return redirect(url_for('scouting.players', report_id=report_id))

@bp.route('/<int:report_id>/clips')
@login_required
def clips(report_id):
    report = ScoutingReport.query.filter_by(
        id=report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    clips = report.clips.filter_by(
        team_organization_id=get_current_team_id()
    ).all()
    
    return render_template('scouting/clips.html', report=report, clips=clips)

@bp.route('/<int:report_id>/add_clip', methods=['GET', 'POST'])
@login_required
@coach_required
def add_clip(report_id):
    report = ScoutingReport.query.filter_by(
        id=report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = ScoutingClipForm()
    
    if form.validate_on_submit():
        # Extract video ID from YouTube link
        youtube_link = form.youtube_link.data
        video_id = extract_youtube_id(youtube_link)
        
        if not video_id:
            flash('Invalid YouTube link. Please provide a valid YouTube URL.', 'danger')
            return render_template('scouting/clip_form.html', form=form, report=report, title='Add Clip')
        
        # Create standardized YouTube link
        standard_link = f'https://www.youtube.com/watch?v={video_id}'
        
        # Find the highest existing clip ID and add 1
        highest_id = db.session.query(db.func.max(ScoutingClip.id)).scalar() or 0
        next_id = highest_id + 1
        
        clip = ScoutingClip(
            id=next_id,  # Explicitly set the ID
            scouting_report_id=report.id,
            title=form.title.data,
            youtube_link=standard_link,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            clip_type=form.clip_type.data,
            description=form.description.data,
            team_organization_id=get_current_team_id()  # Add team organization ID
        )
        
        db.session.add(clip)
        db.session.commit()
        
        flash(f'Clip "{clip.title}" has been added!', 'success')
        return redirect(url_for('scouting.clips', report_id=report.id))
    
    return render_template('scouting/clip_form.html', form=form, report=report, title='Add Clip')

@bp.route('/edit_clip/<int:clip_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_clip(clip_id):
    clip = ScoutingClip.query.filter_by(
        id=clip_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    report = ScoutingReport.query.filter_by(
        id=clip.scouting_report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    form = ScoutingClipForm(obj=clip)
    
    if form.validate_on_submit():
        # Extract video ID from YouTube link
        youtube_link = form.youtube_link.data
        video_id = extract_youtube_id(youtube_link)
        
        if not video_id:
            flash('Invalid YouTube link. Please provide a valid YouTube URL.', 'danger')
            return render_template('scouting/clip_form.html', form=form, clip=clip, report=report, title='Edit Clip')
        
        # Create standardized YouTube link
        standard_link = f'https://www.youtube.com/watch?v={video_id}'
        
        clip.title = form.title.data
        clip.youtube_link = standard_link
        clip.start_time = form.start_time.data
        clip.end_time = form.end_time.data
        clip.clip_type = form.clip_type.data
        clip.description = form.description.data
        
        db.session.commit()
        
        flash(f'Clip "{clip.title}" has been updated!', 'success')
        return redirect(url_for('scouting.clips', report_id=clip.scouting_report_id))
    
    return render_template('scouting/clip_form.html', form=form, clip=clip, report=report, title='Edit Clip')

@bp.route('/delete_clip/<int:clip_id>', methods=['POST'])
@login_required
@coach_required
def delete_clip(clip_id):
    clip = ScoutingClip.query.filter_by(
        id=clip_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    report_id = clip.scouting_report_id
    title = clip.title
    
    db.session.delete(clip)
    db.session.commit()
    
    flash(f'Clip "{title}" has been deleted!', 'success')
    return redirect(url_for('scouting.clips', report_id=report_id))

@bp.route('/view_clip/<int:clip_id>')
@login_required
def view_clip(clip_id):
    clip = ScoutingClip.query.filter_by(
        id=clip_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    report = ScoutingReport.query.filter_by(
        id=clip.scouting_report_id,
        team_organization_id=get_current_team_id()
    ).first_or_404()
    
    return render_template('scouting/view_clip.html', clip=clip, report=report)

def extract_youtube_id(url):
    """Extract YouTube video ID from URL."""
    # Regular expressions to match various YouTube URL formats
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/|youtube\.com\/watch\?.*v=)([^&\n?#]+)',
        r'(?:youtube\.com\/shorts\/)([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

@bp.errorhandler(400)
def bad_request_error(error):
    return jsonify({
        'success': False,
        'message': 'Bad request - CSRF token missing or invalid'
    }), 400

@bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({
        'success': False,
        'message': 'Internal server error'
    }), 500
