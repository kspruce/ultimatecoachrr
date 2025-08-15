# app/routes/tasks.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from app.models.task_queue import TaskQueue
from app.utils.utils import admin_required

bp = Blueprint('tasks', __name__, url_prefix='/tasks')

@bp.route('/')
@login_required
@admin_required
def index():
    """Show task queue status"""
    tasks = TaskQueue.query.order_by(TaskQueue.created_at.desc()).limit(100).all()
    return render_template('tasks/index.html', tasks=tasks)

@bp.route('/retry/<int:task_id>', methods=['POST'])
@login_required
@admin_required
def retry_task(task_id):
    """Retry a failed task"""
    task = TaskQueue.query.get_or_404(task_id)
    if task.status == 'failed':
        task.status = 'pending'
        task.error = None
        db.session.commit()
        flash(f'Task {task_id} has been queued for retry', 'success')
    else:
        flash(f'Only failed tasks can be retried', 'warning')
    return redirect(url_for('tasks.index'))
