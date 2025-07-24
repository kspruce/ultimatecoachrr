# app/routes/fitness.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from app import db
from app.models.fitness import FitnessMetric, FitnessRecord
from app.models.player import Player
from app.utils.utils import admin_required
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import FloatField, TextAreaField, SubmitField, SelectField, StringField, BooleanField, DateField
from wtforms.validators import DataRequired, Optional, Length
import csv
import io
import tempfile

bp = Blueprint('fitness', __name__, url_prefix='/fitness')

class FitnessRecordForm(FlaskForm):
    metric = SelectField('Metric', coerce=int, validators=[DataRequired()])
    value = FloatField('Value', validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Record')

class FitnessMetricForm(FlaskForm):
    name = StringField('Metric Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    unit = StringField('Unit of Measurement', validators=[DataRequired(), Length(max=20)])
    higher_is_better = BooleanField('Higher Values Are Better', default=True)
    active = BooleanField('Active', default=True)
    submit = SubmitField('Save Metric')

class FitnessGoalForm(FlaskForm):
    target_value = FloatField('Target Value', validators=[DataRequired()])
    target_date = DateField('Target Date', validators=[DataRequired()])
    submit = SubmitField('Set Goal')

@bp.route('/')
@login_required
def index():
    """Main fitness dashboard"""
    metrics = FitnessMetric.query.filter_by(active=True).all()
    
    # Get team averages and record holders for each metric
    metric_data = []
    for metric in metrics:
        record_holder_entry = None
        if metric.record_holder:
            record_holder_entry = {
                'player': metric.record_holder.player,
                'value': metric.record_holder.value,
                'date': metric.record_holder.date_recorded
            }
            
        metric_data.append({
            'metric': metric,
            'average': metric.team_average,
            'record_holder': record_holder_entry
        })
    
    # Get recent fitness records
    recent_records = FitnessRecord.query.join(Player).filter(Player.active == True).order_by(
        FitnessRecord.date_recorded.desc()
    ).limit(10).all()
    
    return render_template('fitness/index.html', 
                          metric_data=metric_data,
                          recent_records=recent_records)

@bp.route('/player/<int:player_id>')
@login_required
def player_fitness(player_id):
    """View fitness data for a specific player"""
    player = Player.query.get_or_404(player_id)
    
    # Check permissions - only the player, coaches, or admins can view detailed fitness data
    if not (current_user.is_admin or 
            (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        flash('You do not have permission to view this player\'s fitness data.', 'danger')
        return redirect(url_for('team.player_detail', player_id=player_id))
    
    # Define metric categories
    categories = {
        'sprinting': ['20-Yard Sprint', '40-Yard Sprint', 'Flying 20', '5-10-5 Shuttle/Pro Agility', 'Change of Direction Speed'],
        'endurance': ['Beep Test/Yo-Yo Test', '1-Mile Run', '300-Yard Shuttle', 'Ultimate-Specific Conditioning Test', 'Recovery Heart Rate'],
        'power': ['Vertical Jump', 'Broad Jump', 'Box Jump'],
        'strength': ['Plank Hold', 'Push-Ups', 'Pull-Ups', 'Squat Endurance'],
        'skills': ['Maximum Pull Distance', 'Throwing Accuracy', 'Lateral Quickness Drill', 'Jump & Reach']
    }
    
    # Get all metrics
    all_metrics = FitnessMetric.query.filter_by(active=True).all()
    
    # Organize metrics by category
    categorized_metrics = {}
    for category, metric_names in categories.items():
        categorized_metrics[category] = []
        for metric in all_metrics:
            if metric.name in metric_names:
                # Get player's data for this metric
                latest_record = FitnessRecord.query.filter_by(
                    player_id=player_id, 
                    metric_id=metric.id
                ).order_by(FitnessRecord.date_recorded.desc()).first()
                
                history = FitnessRecord.query.filter_by(
                    player_id=player_id, 
                    metric_id=metric.id
                ).order_by(FitnessRecord.date_recorded).all()
                
                team_avg = metric.team_average
                
                record_holder = metric.record_holder
                
                categorized_metrics[category].append({
                    'metric': metric,
                    'latest': latest_record,
                    'history': history,
                    'team_average': team_avg,
                    'record_holder': record_holder
                })
    
    # Create a dictionary of all metric categories for the template
    all_metrics = {
        'sprinting_metrics': categorized_metrics['sprinting'],
        'endurance_metrics': categorized_metrics['endurance'],
        'power_metrics': categorized_metrics['power'],
        'strength_metrics': categorized_metrics['strength'],
        'skills_metrics': categorized_metrics['skills']
    }
    
    # Prepare radar chart data
    radar_labels = []
    player_radar_data = []
    team_radar_data = []
    
    # Select one representative metric from each category for the radar chart
    for category, metrics in categorized_metrics.items():
        if metrics:
            metric_data = metrics[0]
            radar_labels.append(metric_data['metric'].name)
            
            # Calculate percentile score (0-100)
            if metric_data['latest'] and metric_data['team_average']:
                value = float(metric_data['latest'].value)
                avg = float(metric_data['team_average'])
                
                # For metrics where lower is better, invert the calculation
                if not metric_data['metric'].higher_is_better:
                    if value > 0:  # Avoid division by zero
                        score = min(100, (avg / value) * 50)  # Scale appropriately
                    else:
                        score = 0
                else:
                    if avg > 0:  # Avoid division by zero
                        score = min(100, (value / avg) * 50)  # Scale appropriately
                    else:
                        score = 0
                
                player_radar_data.append(score)
            else:
                player_radar_data.append(0)
            
            team_radar_data.append(50)  # Team average is always at 50% on the radar
    
    # Find top metrics where player excels
    top_metrics = []
    all_player_metrics = []
    
    for category_metrics in categorized_metrics.values():
        for metric_data in category_metrics:
            if metric_data['latest'] and metric_data['team_average']:
                value = float(metric_data['latest'].value)
                avg = float(metric_data['team_average'])
                
                # Calculate how much better than average (as a percentage)
                if metric_data['metric'].higher_is_better:
                    if avg > 0:
                        percentile = int((value / avg - 1) * 100)
                    else:
                        percentile = 0
                else:
                    if value > 0:
                        percentile = int((avg / value - 1) * 100)
                    else:
                        percentile = 0
                
                all_player_metrics.append({
                    'name': metric_data['metric'].name,
                    'value': value,
                    'unit': metric_data['metric'].unit,
                    'percentile': percentile
                })
    
    # Sort by percentile and get top 4
    all_player_metrics.sort(key=lambda x: x['percentile'], reverse=True)
    top_metrics = all_player_metrics[:4]
    
    # Get fitness goals for this player
    fitness_goals = []
    try:
        # This assumes you have a FitnessGoal model - if not, leave as empty list
        from app.models.fitness import FitnessGoal
        goals = FitnessGoal.query.filter_by(player_id=player_id, completed=False).all()
        
        for goal in goals:
            # Get current value for this metric
            latest = FitnessRecord.query.filter_by(
                player_id=player_id,
                metric_id=goal.metric_id
            ).order_by(FitnessRecord.date_recorded.desc()).first()
            
            current_value = latest.value if latest else None
            
            # Calculate progress percentage
            if current_value is not None and goal.target_value != 0:
                if goal.metric.higher_is_better:
                    progress = min(100, (current_value / goal.target_value) * 100)
                    achieved = current_value >= goal.target_value
                else:
                    progress = min(100, (goal.target_value / current_value) * 100) if current_value > 0 else 0
                    achieved = current_value <= goal.target_value
            else:
                progress = 0
                achieved = False
            
            fitness_goals.append({
                'metric': goal.metric,
                'target_value': goal.target_value,
                'target_date': goal.target_date,
                'current_value': current_value,
                'progress': int(progress),
                'achieved': achieved
            })
    except ImportError:
        # FitnessGoal model doesn't exist yet
        pass
    
    # Get recent records for this player
    recent_records = FitnessRecord.query.filter_by(player_id=player_id).order_by(
        FitnessRecord.date_recorded.desc()
    ).limit(5).all()
    
    return render_template('fitness/player_fitness.html',
                          player=player,
                          sprinting_metrics=categorized_metrics['sprinting'],
                          endurance_metrics=categorized_metrics['endurance'],
                          power_metrics=categorized_metrics['power'],
                          strength_metrics=categorized_metrics['strength'],
                          skills_metrics=categorized_metrics['skills'],
                          all_metrics=all_metrics,
                          radar_labels=radar_labels,
                          player_radar_data=player_radar_data,
                          team_radar_data=team_radar_data,
                          top_metrics=top_metrics,
                          fitness_goals=fitness_goals,
                          recent_records=recent_records)

@bp.route('/record/<int:player_id>', methods=['GET', 'POST'])
@login_required
def record_fitness(player_id):
    """Record a new fitness metric for a player"""
    player = Player.query.get_or_404(player_id)
    
    # Check permissions
    if not (current_user.is_admin or 
            (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        flash('You do not have permission to record fitness data for this player.', 'danger')
        return redirect(url_for('team.player_detail', player_id=player_id))
    
    form = FitnessRecordForm()
    
    # Get all active metrics for the form dropdown
    active_metrics = FitnessMetric.query.filter_by(active=True).all()
    form.metric.choices = [(m.id, f"{m.name} ({m.unit})") for m in active_metrics]
    
    # Create a dictionary of metric descriptions for the JavaScript
    metric_descriptions = {m.id: m.description for m in active_metrics}
    
    if form.validate_on_submit():
        try:
            record = FitnessRecord(
                player_id=player_id,
                metric_id=form.metric.data,
                value=form.value.data,
                notes=form.notes.data,
                date_recorded=datetime.utcnow()
            )
            db.session.add(record)
            db.session.commit()
            
            # Check if this record achieves any goals
            try:
                from app.models.fitness import FitnessGoal
                metric = FitnessMetric.query.get(form.metric.data)
                goals = FitnessGoal.query.filter_by(
                    player_id=player_id,
                    metric_id=form.metric.data,
                    completed=False
                ).all()
                
                for goal in goals:
                    if (metric.higher_is_better and form.value.data >= goal.target_value) or \
                       (not metric.higher_is_better and form.value.data <= goal.target_value):
                        goal.completed = True
                        goal.completed_date = datetime.utcnow()
                        flash(f'Congratulations! You achieved your goal for {metric.name}!', 'success')
                
                db.session.commit()
            except ImportError:
                # FitnessGoal model doesn't exist yet
                pass
                
            flash('Fitness record added successfully!', 'success')
            return redirect(url_for('fitness.player_fitness', player_id=player_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording fitness data: {str(e)}', 'danger')
    
    # Get recent records for this player
    recent_records = FitnessRecord.query.filter_by(player_id=player_id).order_by(
        FitnessRecord.date_recorded.desc()
    ).limit(5).all()
    
    return render_template('fitness/record_form.html', 
                          form=form, 
                          player=player,
                          metric_descriptions=metric_descriptions,
                          recent_records=recent_records)

@bp.route('/metrics')
@login_required
@admin_required
def manage_metrics():
    """Manage fitness metrics (admin only)"""
    metrics = FitnessMetric.query.all()
    return render_template('fitness/manage_metrics.html', metrics=metrics)

@bp.route('/metrics/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_metric():
    """Add a new fitness metric (admin only)"""
    form = FitnessMetricForm()
    
    if form.validate_on_submit():
        try:
            metric = FitnessMetric(
                name=form.name.data,
                description=form.description.data,
                unit=form.unit.data,
                higher_is_better=form.higher_is_better.data,
                active=form.active.data
            )
            db.session.add(metric)
            db.session.commit()
            flash(f'Fitness metric "{metric.name}" added successfully!', 'success')
            return redirect(url_for('fitness.manage_metrics'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding fitness metric: {str(e)}', 'danger')
    
    return render_template('fitness/metric_form.html', 
                          form=form, 
                          title="Add New Fitness Metric")

@bp.route('/metrics/edit/<int:metric_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_metric(metric_id):
    """Edit an existing fitness metric (admin only)"""
    metric = FitnessMetric.query.get_or_404(metric_id)
    form = FitnessMetricForm(obj=metric)
    
    # Get player count for this metric
    player_count = db.session.query(FitnessRecord.player_id).filter_by(metric_id=metric_id).distinct().count()
    
    if form.validate_on_submit():
        try:
            metric.name = form.name.data
            metric.description = form.description.data
            metric.unit = form.unit.data
            metric.higher_is_better = form.higher_is_better.data
            metric.active = form.active.data
            
            db.session.commit()
            flash(f'Fitness metric "{metric.name}" updated successfully!', 'success')
            return redirect(url_for('fitness.manage_metrics'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating fitness metric: {str(e)}', 'danger')
    
    return render_template('fitness/metric_form.html', 
                          form=form, 
                          metric=metric,
                          player_count=player_count,
                          record_holder=metric.record_holder,
                          title="Edit Fitness Metric")

@bp.route('/metrics/delete/<int:metric_id>', methods=['POST'])
@login_required
@admin_required
def delete_metric(metric_id):
    """Delete a fitness metric (admin only)"""
    metric = FitnessMetric.query.get_or_404(metric_id)
    
    try:
        # Check if there are any records using this metric
        record_count = FitnessRecord.query.filter_by(metric_id=metric_id).count()
        
        if record_count > 0:
            # Instead of deleting, just mark as inactive
            metric.active = False
            db.session.commit()
            flash(f'Fitness metric "{metric.name}" has been deactivated because it has {record_count} records. Records are preserved.', 'warning')
        else:
            # Safe to delete if no records exist
            name = metric.name
            db.session.delete(metric)
            db.session.commit()
            flash(f'Fitness metric "{name}" has been deleted.', 'success')
            
        return redirect(url_for('fitness.manage_metrics'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing request: {str(e)}', 'danger')
        return redirect(url_for('fitness.manage_metrics'))

@bp.route('/record/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    """Delete a fitness record"""
    record = FitnessRecord.query.get_or_404(record_id)
    player_id = record.player_id
    
    # Check permissions
    if not (current_user.is_admin or 
            (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        flash('You do not have permission to delete this record.', 'danger')
        return redirect(url_for('fitness.player_fitness', player_id=player_id))
    
    try:
        metric_name = record.metric.name
        db.session.delete(record)
        db.session.commit()
        flash(f'Fitness record for {metric_name} deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting record: {str(e)}', 'danger')
    
    return redirect(url_for('fitness.player_fitness', player_id=player_id))

@bp.route('/team-leaderboard')
@login_required
def team_leaderboard():
    """Display leaderboards for all fitness metrics"""
    metrics = FitnessMetric.query.filter_by(active=True).all()
    
    leaderboards = []
    for metric in metrics:
        # Get top 5 records for this metric
        if metric.higher_is_better:
            top_records = FitnessRecord.query.filter_by(metric_id=metric.id)\
                .join(Player)\
                .filter(Player.active == True)\
                .order_by(FitnessRecord.value.desc())\
                .limit(5).all()
        else:
            top_records = FitnessRecord.query.filter_by(metric_id=metric.id)\
                .join(Player)\
                .filter(Player.active == True)\
                .order_by(FitnessRecord.value)\
                .limit(5).all()
        
        leaderboards.append({
            'metric': metric,
            'records': top_records
        })
    
    return render_template('fitness/leaderboard.html', leaderboards=leaderboards)

@bp.route('/player/<int:player_id>/history/<int:metric_id>')
@login_required
def player_metric_history(player_id, metric_id):
    """View detailed history for a specific player and metric"""
    player = Player.query.get_or_404(player_id)
    metric = FitnessMetric.query.get_or_404(metric_id)
    
    # Check permissions
    if not (current_user.is_admin or 
            (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        flash('You do not have permission to view this data.', 'danger')
        return redirect(url_for('team.player_detail', player_id=player_id))
    
    # Get all records for this player and metric
    records = FitnessRecord.query.filter_by(
        player_id=player_id,
        metric_id=metric_id
    ).order_by(FitnessRecord.date_recorded.desc()).all()
    
    # Get team average
    team_avg = metric.team_average
    
    # Get record holder
    if metric.higher_is_better:
        record_holder = FitnessRecord.query.filter_by(metric_id=metric_id)\
            .order_by(FitnessRecord.value.desc()).first()
    else:
        record_holder = FitnessRecord.query.filter_by(metric_id=metric_id)\
            .order_by(FitnessRecord.value).first()
    
    # Calculate best value and date
    best_value = None
    best_date = None
    if records:
        if metric.higher_is_better:
            best_record = max(records, key=lambda r: r.value)
        else:
            best_record = min(records, key=lambda r: r.value)
        best_value = best_record.value
        best_date = best_record.date_recorded
    
    # Calculate trend (% change over last 3 records)
    trend = 0
    if len(records) >= 3:
        recent_records = sorted(records[:3], key=lambda r: r.date_recorded, reverse=True)
        if recent_records[2].value > 0:  # Avoid division by zero
            change = (recent_records[0].value - recent_records[2].value) / recent_records[2].value
            # For metrics where lower is better, invert the trend
            trend = change * 100 if metric.higher_is_better else -change * 100
    
    return render_template('fitness/metric_history.html',
                          player=player,
                          metric=metric,
                          records=records,
                          team_average=team_avg,
                          record_holder=record_holder,
                          best_value=best_value,
                          best_date=best_date,
                          trend=trend)

@bp.route('/set-goal/<int:player_id>/<int:metric_id>', methods=['POST'])
@login_required
def set_goal(player_id, metric_id):
    """Set a fitness goal for a player"""
    player = Player.query.get_or_404(player_id)
    metric = FitnessMetric.query.get_or_404(metric_id)
    
    # Check permissions
    if not (current_user.is_admin or 
            (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        flash('You do not have permission to set goals for this player.', 'danger')
        return redirect(url_for('fitness.player_fitness', player_id=player_id))
    
    try:
        # This assumes you have a FitnessGoal model
        from app.models.fitness import FitnessGoal
        
        target_value = float(request.form.get('target_value'))
        target_date_str = request.form.get('target_date')
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        
        # Create the goal
        goal = FitnessGoal(
            player_id=player_id,
            metric_id=metric_id,
            target_value=target_value,
            target_date=target_date,
            created_at=datetime.utcnow(),
            completed=False
        )
        
        db.session.add(goal)
        db.session.commit()
        
        flash(f'Goal set for {metric.name}!', 'success')
    except ImportError:
        flash('Goal setting is not yet implemented.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error setting goal: {str(e)}', 'danger')
    
    return redirect(url_for('fitness.player_metric_history', player_id=player_id, metric_id=metric_id))

@bp.route('/batch-record', methods=['GET', 'POST'])
@login_required
@admin_required
def batch_record():
    """Record fitness data for multiple players at once (admin/coach only)"""
    metric_id = request.args.get('metric_id', type=int)
    
    if not metric_id:
        metrics = FitnessMetric.query.filter_by(active=True).all()
        return render_template('fitness/batch_select_metric.html', metrics=metrics)
    
    metric = FitnessMetric.query.get_or_404(metric_id)
    active_players = Player.query.filter_by(active=True).order_by(Player.name).all()
    
    # Get top records for this metric to display on the page
    if metric.higher_is_better:
        top_records = FitnessRecord.query.filter_by(metric_id=metric_id)\
            .join(Player)\
            .filter(Player.active == True)\
            .order_by(FitnessRecord.value.desc())\
            .limit(5).all()
    else:
        top_records = FitnessRecord.query.filter_by(metric_id=metric_id)\
            .join(Player)\
            .filter(Player.active == True)\
            .order_by(FitnessRecord.value)\
            .limit(5).all()
    
    if request.method == 'POST':
        try:
            records_added = 0
            for player in active_players:
                value_key = f'value_{player.id}'
                notes_key = f'notes_{player.id}'
                
                if value_key in request.form and request.form[value_key].strip():
                    try:
                        value = float(request.form[value_key])
                        notes = request.form.get(notes_key, '')
                        
                        record = FitnessRecord(
                            player_id=player.id,
                            metric_id=metric_id,
                            value=value,
                            notes=notes,
                            date_recorded=datetime.utcnow()
                        )
                        db.session.add(record)
                        records_added += 1
                    except ValueError:
                        # Skip invalid values
                        pass
            
            db.session.commit()
            flash(f'Successfully recorded {records_added} fitness values for {metric.name}.', 'success')
            return redirect(url_for('fitness.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording fitness data: {str(e)}', 'danger')
    
    return render_template('fitness/batch_record.html',
                          metric=metric,
                          players=active_players,
                          top_records=top_records)

@bp.route('/api/player/<int:player_id>/metrics/<int:metric_id>/chart-data')
@login_required
def api_player_metric_chart_data(player_id, metric_id):
    """API endpoint to get chart data for a player's metric history"""
    # Check permissions
    if not (current_user.is_admin or 
            (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        return jsonify({'error': 'Permission denied'}), 403
    
    records = FitnessRecord.query.filter_by(
        player_id=player_id,
        metric_id=metric_id
    ).order_by(FitnessRecord.date_recorded).all()
    
    data = {
        'labels': [record.date_recorded.strftime('%Y-%m-%d') for record in records],
        'values': [float(record.value) for record in records]
    }
    
    return jsonify(data)

@bp.route('/api/previous-values/<int:metric_id>')
@login_required
def api_previous_values(metric_id):
    """API endpoint to get the most recent values for a metric for all players"""
    # Check permissions for batch operations
    if not (current_user.is_admin or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        return jsonify({'error': 'Permission denied'}), 403
    
    # Subquery to get the most recent record for each player
    subquery = db.session.query(
        FitnessRecord.player_id,
        func.max(FitnessRecord.date_recorded).label('max_date')
    ).filter_by(metric_id=metric_id).group_by(FitnessRecord.player_id).subquery()
    
    # Join with the main table to get the actual records
    records = db.session.query(FitnessRecord).join(
        subquery,
        and_(
            FitnessRecord.player_id == subquery.c.player_id,
            FitnessRecord.date_recorded == subquery.c.max_date,
            FitnessRecord.metric_id == metric_id
        )
    ).all()
    
    # Format the response
    result = {}
    for record in records:
        result[record.player_id] = {
            'value': float(record.value),
            'notes': record.notes
        }
    
    return jsonify(result)

@bp.route('/export-data')
@login_required
@admin_required
def export_data():
    """Export all fitness data as CSV"""
    try:
        # Create a StringIO object to write CSV data
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        writer.writerow(['Player ID', 'Player Name', 'Metric ID', 'Metric Name', 'Value', 'Unit', 'Date Recorded', 'Notes'])
        
        # Query all fitness records with player and metric information
        records = db.session.query(
            FitnessRecord, Player, FitnessMetric
        ).join(
            Player, FitnessRecord.player_id == Player.id
        ).join(
            FitnessMetric, FitnessRecord.metric_id == FitnessMetric.id
        ).all()
        
        # Write data rows
        for record, player, metric in records:
            writer.writerow([
                player.id,
                player.name,
                metric.id,
                metric.name,
                record.value,
                metric.unit,
                record.date_recorded.strftime('%Y-%m-%d %H:%M:%S'),
                record.notes or ''
            ])
        
        # Reset the pointer to the beginning of the StringIO object
        output.seek(0)
        
        # Create a temporary file to store the CSV data
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w') as temp_file:
            temp_file.write(output.getvalue())
            temp_file_path = temp_file.name
        
        # Generate a timestamp for the filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Send the file as an attachment
        return send_file(
            temp_file_path,
            as_attachment=True,
            download_name=f'fitness_data_export_{timestamp}.csv',
            mimetype='text/csv'
        )
    
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'danger')
        return redirect(url_for('fitness.manage_metrics'))

class ImportForm(FlaskForm):
    csv_file = FileField('CSV File', validators=[
        FileRequired(),
        FileAllowed(['csv'], 'CSV files only!')
    ])
    submit = SubmitField('Import Data')

@bp.route('/import-data', methods=['POST'])
@login_required
@admin_required
def import_data():
    """Import fitness data from CSV"""
    if 'csv_file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('fitness.manage_metrics'))
    
    file = request.files['csv_file']
    
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('fitness.manage_metrics'))
    
    if file and file.filename.endswith('.csv'):
        try:
            # Read the CSV file
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.reader(stream)
            
            # Skip header row
            header = next(csv_reader)
            expected_header = ['Player ID', 'Player Name', 'Metric ID', 'Metric Name', 'Value', 'Unit', 'Date Recorded', 'Notes']
            
            # Check if header matches expected format
            if header != expected_header:
                flash('CSV file format is incorrect. Please use the export format as a template.', 'danger')
                return redirect(url_for('fitness.manage_metrics'))
            
            records_added = 0
            records_updated = 0
            records_skipped = 0
            
            for row in csv_reader:
                try:
                    player_id = int(row[0])
                    metric_id = int(row[2])
                    value = float(row[4])
                    date_str = row[6]
                    notes = row[7]
                    
                    # Check if player and metric exist
                    player = Player.query.get(player_id)
                    metric = FitnessMetric.query.get(metric_id)
                    
                    if not player or not metric:
                        records_skipped += 1
                        continue
                    
                    # Parse date
                    try:
                        date_recorded = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        date_recorded = datetime.utcnow()
                    
                    # Check if record already exists for this player, metric, and date
                    existing_record = FitnessRecord.query.filter_by(
                        player_id=player_id,
                        metric_id=metric_id,
                        date_recorded=date_recorded
                    ).first()
                    
                    if existing_record:
                        # Update existing record
                        existing_record.value = value
                        existing_record.notes = notes
                        records_updated += 1
                    else:
                        # Create new record
                        record = FitnessRecord(
                            player_id=player_id,
                            metric_id=metric_id,
                            value=value,
                            notes=notes,
                            date_recorded=date_recorded
                        )
                        db.session.add(record)
                        records_added += 1
                
                except Exception as e:
                    records_skipped += 1
                    continue
            
            db.session.commit()
            flash(f'Import complete: {records_added} records added, {records_updated} records updated, {records_skipped} records skipped.', 'success')
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error importing data: {str(e)}', 'danger')
    
    else:
        flash('Invalid file format. Please upload a CSV file.', 'danger')
    
    return redirect(url_for('fitness.manage_metrics'))

@bp.route('/player/<int:player_id>/goals')
@login_required
def player_goals(player_id):
    """View and manage fitness goals for a player"""
    player = Player.query.get_or_404(player_id)
    
    # Check permissions
    if not (current_user.is_admin or 
            (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        flash('You do not have permission to view this player\'s goals.', 'danger')
        return redirect(url_for('team.player_detail', player_id=player_id))
    
    try:
        # This assumes you have a FitnessGoal model
        from app.models.fitness import FitnessGoal
        
        # Get active goals
        active_goals = FitnessGoal.query.filter_by(
            player_id=player_id,
            completed=False
        ).order_by(FitnessGoal.target_date).all()
        
        # Get completed goals
        completed_goals = FitnessGoal.query.filter_by(
            player_id=player_id,
            completed=True
        ).order_by(FitnessGoal.completed_date.desc()).all()
        
        # Process goals to add current values and progress
        processed_active_goals = []
        for goal in active_goals:
            # Get current value for this metric
            latest = FitnessRecord.query.filter_by(
                player_id=player_id,
                metric_id=goal.metric_id
            ).order_by(FitnessRecord.date_recorded.desc()).first()
            
            current_value = latest.value if latest else None
            
            # Calculate progress percentage
            if current_value is not None and goal.target_value != 0:
                if goal.metric.higher_is_better:
                    progress = min(100, (current_value / goal.target_value) * 100)
                else:
                    progress = min(100, (goal.target_value / current_value) * 100) if current_value > 0 else 0
            else:
                progress = 0
            
            processed_active_goals.append({
                'goal': goal,
                'current_value': current_value,
                'progress': int(progress)
            })
        
        # Get available metrics for setting new goals
        available_metrics = FitnessMetric.query.filter_by(active=True).all()
        
        return render_template('fitness/player_goals.html',
                              player=player,
                              active_goals=processed_active_goals,
                              completed_goals=completed_goals,
                              available_metrics=available_metrics)
    
    except ImportError:
        flash('Goal tracking is not yet implemented.', 'warning')
        return redirect(url_for('fitness.player_fitness', player_id=player_id))

@bp.route('/goal/<int:goal_id>/complete', methods=['POST'])
@login_required
def complete_goal(goal_id):
    """Mark a goal as completed"""
    try:
        from app.models.fitness import FitnessGoal
        
        goal = FitnessGoal.query.get_or_404(goal_id)
        player_id = goal.player_id
        
        # Check permissions
        if not (current_user.is_admin or 
                (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
                (hasattr(current_user, 'role') and current_user.role == 'coach')):
            flash('You do not have permission to update this goal.', 'danger')
            return redirect(url_for('fitness.player_goals', player_id=player_id))
        
        goal.completed = True
        goal.completed_date = datetime.utcnow()
        db.session.commit()
        
        flash('Goal marked as completed!', 'success')
        return redirect(url_for('fitness.player_goals', player_id=player_id))
    
    except ImportError:
        flash('Goal tracking is not yet implemented.', 'warning')
        return redirect(url_for('fitness.index'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating goal: {str(e)}', 'danger')
        return redirect(url_for('fitness.index'))

@bp.route('/goal/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    """Delete a fitness goal"""
    try:
        from app.models.fitness import FitnessGoal
        
        goal = FitnessGoal.query.get_or_404(goal_id)
        player_id = goal.player_id
        
        # Check permissions
        if not (current_user.is_admin or 
                (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
                (hasattr(current_user, 'role') and current_user.role == 'coach')):
            flash('You do not have permission to delete this goal.', 'danger')
            return redirect(url_for('fitness.player_goals', player_id=player_id))
        
        db.session.delete(goal)
        db.session.commit()
        
        flash('Goal deleted successfully.', 'success')
        return redirect(url_for('fitness.player_goals', player_id=player_id))
    
    except ImportError:
        flash('Goal tracking is not yet implemented.', 'warning')
        return redirect(url_for('fitness.index'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting goal: {str(e)}', 'danger')
        return redirect(url_for('fitness.index'))

@bp.route('/add-goal/<int:player_id>', methods=['POST'])
@login_required
def add_goal(player_id):
    """Add a new fitness goal for a player"""
    player = Player.query.get_or_404(player_id)
    
    # Check permissions
    if not (current_user.is_admin or 
            (hasattr(current_user, 'player') and current_user.player and current_user.player.id == player_id) or 
            (hasattr(current_user, 'role') and current_user.role == 'coach')):
        flash('You do not have permission to add goals for this player.', 'danger')
        return redirect(url_for('fitness.player_fitness', player_id=player_id))
    
    try:
        from app.models.fitness import FitnessGoal
        
        metric_id = int(request.form.get('metric_id'))
        target_value = float(request.form.get('target_value'))
        target_date_str = request.form.get('target_date')
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        
        # Validate the metric exists
        metric = FitnessMetric.query.get_or_404(metric_id)
        
        # Create the goal
        goal = FitnessGoal(
            player_id=player_id,
            metric_id=metric_id,
            target_value=target_value,
            target_date=target_date,
            created_at=datetime.utcnow(),
            completed=False
        )
        
        db.session.add(goal)
        db.session.commit()
        
        flash(f'New goal for {metric.name} added successfully!', 'success')
        return redirect(url_for('fitness.player_goals', player_id=player_id))
    
    except ImportError:
        flash('Goal tracking is not yet implemented.', 'warning')
        return redirect(url_for('fitness.player_fitness', player_id=player_id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding goal: {str(e)}', 'danger')
        return redirect(url_for('fitness.player_fitness', player_id=player_id))

@bp.route('/fitness-model')
@login_required
def fitness_model():
    """Information about the fitness model and how metrics are calculated"""
    return render_template('fitness/fitness_model.html')

