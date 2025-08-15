# app/tasks.py (New Content)

from app import db, cache, create_app
from app.models.point import Point
from app.models.throws import Throw
from app.models.stats import PlayerPointStats
import time
import traceback

# This dictionary will hold our task functions
_task_registry = {}

def register_task(name):
    """A decorator to register a function as a background task."""
    def decorator(func):
        _task_registry[name] = func
        return func
    return decorator

def queue_task(task_name, **kwargs):
    """A helper to add a task to the database queue."""
    from app.models.task_queue import TaskQueue
    import json

    task = TaskQueue(task_name=task_name)
    task.set_params(kwargs)
    db.session.add(task)
    db.session.commit()
    print(f"Task '{task_name}' with params {kwargs} has been queued.")
    return task.id

def run_worker():
    """
    This is the main loop for our worker process.
    It will continuously check the database for new tasks.
    """
    app = create_app()
    with app.app_context():
        print("Starting background worker loop...")
        while True:
            from app.models.task_queue import TaskQueue
            task = TaskQueue.query.filter_by(status='pending').order_by(TaskQueue.created_at).first()

            if task:
                print(f"Found task {task.id}: {task.task_name}")
                task.status = 'running'
                db.session.commit()

                try:
                    task_func = _task_registry.get(task.task_name)
                    if task_func:
                        result = task_func(**task.get_params())
                        task.status = 'completed'
                        task.set_result(result or {})
                    else:
                        task.status = 'failed'
                        task.error = f"Task '{task.task_name}' not registered."
                except Exception as e:
                    print(f"Task {task.id} failed: {e}")
                    traceback.print_exc()
                    task.status = 'failed'
                    task.error = traceback.format_exc()
                
                db.session.commit()
            else:
                # If no tasks, wait for a bit before checking again
                time.sleep(10)

# --- Define your tasks below ---

@register_task('process_point_stats')
def process_point_stats(point_id):
    """
    This is the background task for calculating stats.
    """
    print(f"Processing stats for point {point_id}...")
    
    point = Point.query.get(point_id)
    if not point:
        print(f"Point {point_id} not found. Aborting task.")
        return {"error": "Point not found"}

    # --- aEC Calculation Logic ---
    throws = Throw.query.filter_by(point_id=point.id).all()
    player_aec = {}

    for throw in throws:
        aec = 0.0
        if throw.x_start is not None and throw.x_end is not None:
            position_change = (throw.x_end - throw.x_start) / 100.0
            aec += position_change

        if throw.throw_type == 'assist':
            aec += 1.0
        elif throw.throw_type in ['throwaway', 'drop']:
            aec -= 0.5
        elif throw.is_completion:
            aec += 0.05
        
        throw.adjusted_expected_contribution = aec
        
        if throw.thrower_id not in player_aec:
            player_aec[throw.thrower_id] = 0.0
        player_aec[throw.thrower_id] += aec

    db.session.commit()

    # --- Update PlayerPointStats ---
    for player_id, total_aec in player_aec.items():
        stats_record = PlayerPointStats.query.filter_by(player_id=player_id, point_id=point.id).first()
        if not stats_record:
            stats_record = PlayerPointStats(player_id=player_id, point_id=point.id)
            db.session.add(stats_record)
        
        stats_record.adjusted_expected_contribution = total_aec
    
    db.session.commit()
    
    # --- Invalidate the Cache ---
    cache.clear()
    print(f"Cache cleared. Finished stats processing for point {point_id}.")
    return {"status": "success", "point_id": point_id}
