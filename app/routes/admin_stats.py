from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from app.models.stats import PlayerStats, TeamStats
from app.utils.utils import admin_required
from app.tasks.stats_calculation import run_stats_recalculation_task # We will create this task next

bp = Blueprint('admin_stats', __name__, url_prefix='/admin/stats')

@bp.route('/')
@login_required
@admin_required
def index():
    dirty_player_stats_count = PlayerStats.query.filter_by(is_dirty=True).count()
    dirty_team_stats_count = TeamStats.query.filter_by(is_dirty=True).count()
    return render_template('admin/stats_dashboard.html', 
                           dirty_player_stats_count=dirty_player_stats_count,
                           dirty_team_stats_count=dirty_team_stats_count)

@bp.route('/recalculate', methods=['POST'])
@login_required
@admin_required
def recalculate():
    # In a production app, this would trigger a background job.
    # For simplicity here, we'll run it synchronously and show a message.
    try:
        run_stats_recalculation_task()
        flash('Statistics recalculation has been completed.', 'success')
    except Exception as e:
        flash(f'An error occurred during recalculation: {e}', 'danger')
    return redirect(url_for('admin_stats.index'))

@bp.route('/mark-dirty', methods=['POST'])
@login_required
@admin_required
def mark_dirty():
    # This is a simple way to mark all stats for recalculation
    PlayerStats.query.update({'is_dirty': True})
    TeamStats.query.update({'is_dirty': True})
    db.session.commit()
    flash('All statistics have been marked as dirty and will be recalculated on the next run.', 'info')
    return redirect(url_for('admin_stats.index'))
