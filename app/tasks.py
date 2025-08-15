# app/tasks.py
from app import db
from app.models.task_queue import TaskQueue
import threading
import time
import traceback

# Dictionary to store task functions
task_registry = {}

def register_task(name):
    """Decorator to register a task function"""
    def decorator(func):
        task_registry[name] = func
        return func
    return decorator

def queue_task(task_name, **kwargs):
    """Add a task to the queue"""
    task = TaskQueue(task_name=task_name)
    task.set_params(kwargs)
    db.session.add(task)
    db.session.commit()
    return task.id

def process_tasks(app):
    """Process tasks in the queue"""
    with app.app_context():
        while True:
            # Get the oldest pending task
            task = TaskQueue.query.filter_by(status='pending').order_by(TaskQueue.created_at).first()
            
            if task:
                # Mark as running
                task.status = 'running'
                db.session.commit()
                
                try:
                    # Get the task function
                    task_func = task_registry.get(task.task_name)
                    
                    if task_func:
                        # Execute the task
                        result = task_func(**task.get_params())
                        
                        # Mark as completed
                        task.status = 'completed'
                        task.set_result(result or {})
                    else:
                        # Task not found
                        task.status = 'failed'
                        task.error = f"Task {task.task_name} not registered"
                except Exception as e:
                    # Mark as failed
                    task.status = 'failed'
                    task.error = f"{str(e)}\n{traceback.format_exc()}"
                
                # Save changes
                db.session.commit()
            
            # Sleep for a bit to avoid hammering the database
            time.sleep(5)

def start_task_processor(app):
    """Start the task processor in a background thread"""
    thread = threading.Thread(target=process_tasks, args=(app,), daemon=True)
    thread.start()
    return thread

# Define tasks
@register_task('process_point_stats')
def process_point_stats(point_id):
    """Process statistics for a point"""
    from app.models.point import Point
    from app.models.throws import Throw
    from app.models.stats import PlayerPointStats
    from app import cache
    
    print(f"Processing stats for point {point_id}")
    
    point = Point.query.get(point_id)
    if not point:
        print(f"Point {point_id} not found")
        return {"error": "Point not found"}
    
    # Calculate Adjusted Expected Contribution for each throw
    throws = Throw.query.filter_by(point_id=point.id).order_by(Throw.created_at).all()
    
    # Track field position and possession
    field_position = 0  # 0-100 scale, higher is closer to scoring
    possession_team = "offense" if point.our_line_type == "O-line" else "defense"
    
    # Dictionary to track player aEC totals
    player_aec = {}
    
    for throw in throws:
        # Calculate field position change
        if throw.x_start is not None and throw.x_end is not None:
            # Normalize field position based on offensive direction
            if possession_team == "offense":
                old_position = throw.x_start
                new_position = throw.x_end
            else:
                old_position = 100 - throw.x_start
                new_position = 100 - throw.x_end
                
            position_change = new_position - old_position
        else:
            position_change = 0
            
        # Calculate base aEC
        if throw.throw_type == 'assist':
            # Assists are worth 1.0
            aec = 1.0
        elif throw.throw_type == 'throwaway':
            # Turnovers have negative value based on field position
            aec = -0.5 - (new_position / 200)  # Worse if closer to scoring
        elif throw.is_completion:
            # Completions are valued based on field position improvement
            # and strategic value (e.g., breaking the mark)
            strategic_value = 0.1 if throw.break_throw else 0.0
            position_value = max(0, position_change / 100)
            aec = position_value + strategic_value
        else:
            aec = -0.5  # Default negative value for incompletions
            
        # Store the calculated aEC
        throw.adjusted_expected_contribution = aec
        db.session.add(throw)
        
        # Track player totals
        if throw.thrower_id not in player_aec:
            player_aec[throw.thrower_id] = 0
        player_aec[throw.thrower_id] += aec
    
    # Update player point stats with aEC
    for player_id, total_aec in player_aec.items():
        stats = PlayerPointStats.query.filter_by(
            player_id=player_id,
            point_id=point.id
        ).first()
        
        if not stats:
            stats = PlayerPointStats(
                player_id=player_id,
                point_id=point.id
            )
            db.session.add(stats)
        
        stats.adjusted_expected_contribution = total_aec
    
    db.session.commit()
    
    # Clear cache keys related to this game
    cache.clear()
    
    print(f"Completed stats processing for point {point_id}")
    return {"status": "success", "point_id": point_id}
