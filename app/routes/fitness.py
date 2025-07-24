# app/routes/fitness.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.fitness import FitnessMetric, FitnessRecord
from app.models.player import Player
from app.utils.utils import admin_required
from sqlalchemy import func
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import FloatField, TextAreaField, SubmitField, SelectField, StringField, BooleanField
from wtforms.validators import DataRequired, Optional, Length

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
    
    return render_template('fitness/index.html', 
                          metric_data=metric_data)

@bp.route('/player/<int:player_id>')
@login_required
def player_fitness(player_id):
    """View fitness data for a specific player"""
    player = Player.query.get_or_404(player_id)
    
    # Check permissions
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
    
    return render_template('fitness/player_fitness.html',
                          player=player,
                          sprinting_metrics=categorized_metrics['sprinting'],
                          endurance_metrics=categorized_metrics['endurance'],
                          power_metrics=categorized_metrics['power'],
                          strength_metrics=categorized_metrics['strength'],
                          skills_metrics=categorized_metrics['skills'],
                          radar_labels=radar_labels,
                          player_radar_data=player_radar_data,
                          team_radar_data=team_radar_data,
                          top_metrics=top_metrics)


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
    form.metric.choices = [(m.id, f"{m.name} ({m.unit})") for m in FitnessMetric.query.filter_by(active=True).all()]
    
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
            flash('Fitness record added successfully!', 'success')
            return redirect(url_for('fitness.player_fitness', player_id=player_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording fitness data: {str(e)}', 'danger')
    
    return render_template('fitness/record_form.html', 
                          form=form, 
                          player=player)

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
    
    return render_template('fitness/metric_history.html',
                          player=player,
                          metric=metric,
                          records=records,
                          team_average=team_avg,
                          record_holder=record_holder)

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
                          players=active_players)

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
