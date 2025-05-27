from flask import Blueprint, render_template, request, jsonify, abort, current_app
from flask_login import login_required, current_user
from app import db
from app.models.drill import Drill, DrillFrame

# Create Blueprint
drill_bp = Blueprint('drills', __name__, url_prefix='/drills')

@drill_bp.route('/editor', methods=['GET'])
@drill_bp.route('/editor/<int:drill_id>', methods=['GET'])
@login_required
def editor(drill_id=None):
    """Render the drill editor page"""
    drill = None
    if drill_id:
        drill = Drill.query.get_or_404(drill_id)
        # Check if user has permission to edit this drill
        if drill.created_by != current_user.id:
            abort(403)
    
    return render_template('drills/editor.html', drill=drill)

@drill_bp.route('/view/<int:drill_id>', methods=['GET'])
def view_drill(drill_id):
    """View a drill (public or owned by current user)"""
    drill = Drill.query.get_or_404(drill_id)
    
    # Check permissions
    if not drill.is_public and (not current_user.is_authenticated or drill.created_by != current_user.id):
        abort(403)
    
    return render_template('drills/view.html', drill=drill)

# API endpoints for AJAX operations
@drill_bp.route('/api/drills', methods=['POST'])
@login_required
def create_drill():
    """Create a new drill"""
    data = request.json
    
    new_drill = Drill(
        title=data.get('title', 'Untitled Drill'),
        description=data.get('description', ''),
        created_by=current_user.id,
        is_public=data.get('is_public', False)
    )
    
    db.session.add(new_drill)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'drill_id': new_drill.id
    })

@drill_bp.route('/api/drills/<int:drill_id>', methods=['PUT'])
@login_required
def update_drill(drill_id):
    """Update drill properties"""
    drill = Drill.query.get_or_404(drill_id)
    
    # Check permissions
    if drill.created_by != current_user.id:
        abort(403)
    
    data = request.json
    
    if 'title' in data:
        drill.title = data['title']
    if 'description' in data:
        drill.description = data['description']
    if 'is_public' in data:
        drill.is_public = data['is_public']
    
    db.session.commit()
    
    return jsonify({'success': True})

@drill_bp.route('/api/drills/<int:drill_id>/frames', methods=['POST'])
@login_required
def add_frame(drill_id):
    """Add a new frame to the drill"""
    drill = Drill.query.get_or_404(drill_id)
    
    # Check permissions
    if drill.created_by != current_user.id:
        abort(403)
    
    data = request.json
    
    # Get the next sequence number
    next_seq = 1
    if drill.frames:
        next_seq = max(frame.sequence for frame in drill.frames) + 1
    
    new_frame = DrillFrame(
        drill_id=drill_id,
        sequence=data.get('sequence', next_seq),
        name=data.get('name', f'Frame {next_seq}'),
        elements=data.get('elements', [])
    )
    
    db.session.add(new_frame)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'frame_id': new_frame.id,
        'sequence': new_frame.sequence
    })

@drill_bp.route('/api/frames/<int:frame_id>', methods=['PUT'])
@login_required
def update_frame(frame_id):
    """Update a frame's elements"""
    frame = DrillFrame.query.get_or_404(frame_id)
    
    # Check permissions via the parent drill
    drill = Drill.query.get(frame.drill_id)
    if drill.created_by != current_user.id:
        abort(403)
    
    data = request.json
    
    if 'elements' in data:
        frame.elements = data['elements']
    if 'name' in data:
        frame.name = data['name']
    if 'sequence' in data:
        frame.sequence = data['sequence']
    
    db.session.commit()
    
    return jsonify({'success': True})

@drill_bp.route('/api/frames/<int:frame_id>', methods=['DELETE'])
@login_required
def delete_frame(frame_id):
    """Delete a frame"""
    frame = DrillFrame.query.get_or_404(frame_id)
    
    # Check permissions via the parent drill
    drill = Drill.query.get(frame.drill_id)
    if drill.created_by != current_user.id:
        abort(403)
    
    db.session.delete(frame)
    db.session.commit()
    
    return jsonify({'success': True})

@drill_bp.route('/api/drills/<int:drill_id>', methods=['GET'])
def get_drill(drill_id):
    """Get drill details and frames"""
    drill = Drill.query.get_or_404(drill_id)
    
    # Check permissions
    if not drill.is_public and (not current_user.is_authenticated or drill.created_by != current_user.id):
        abort(403)
    
    # Get creator info if available
    creator = None
    if drill.created_by:
        from your_app.models.user import User  # Import here to avoid circular imports
        creator = User.query.get(drill.created_by)
    
    # Get frames
    frames = DrillFrame.query.filter_by(drill_id=drill_id).order_by(DrillFrame.sequence).all()
    
    # Format response
    response = {
        'id': drill.id,
        'title': drill.title,
        'description': drill.description,
        'created_by': drill.created_by,
        'created_at': drill.created_at.isoformat(),
        'is_public': drill.is_public,
        'creator': {
            'id': creator.id,
            'username': creator.username
        } if creator else None,
        'frames': [{
            'id': frame.id,
            'sequence': frame.sequence,
            'name': frame.name,
            'elements': frame.elements
        } for frame in frames]
    }
    
    return jsonify(response)
