from flask import Blueprint, render_template, request, jsonify, abort, current_app, session
from flask_login import login_required, current_user
from app import db
from app.models.drill import Drill, DrillFrame

# Create Blueprint
drill_bp = Blueprint('drills', __name__, url_prefix='/drills')

# Helper function to get current team ID
def get_current_team_id():
    """Get the current team ID based on user role."""
    if current_user.is_admin:
        return session.get('current_team_id')
    return current_user.team_organization_id

@drill_bp.route('/editor', methods=['GET'])
@drill_bp.route('/editor/<int:drill_id>', methods=['GET'])
@login_required
def editor(drill_id=None):
    """Render the drill editor page"""
    team_id = get_current_team_id()
    if team_id is None and current_user.is_admin:
        abort(400, "Please select a team first")
        
    drill = None
    if drill_id:
        # Filter by team ID as well
        drill = Drill.query.filter_by(
            id=drill_id,
            team_organization_id=team_id
        ).first_or_404()
        
        # Additional permission check if needed
        if drill.created_by != current_user.id and not current_user.is_admin:
            abort(403)
    
    return render_template('drills/editor.html', drill=drill)

@drill_bp.route('/view/<int:drill_id>', methods=['GET'])
def view_drill(drill_id):
    """View a drill (public or owned by current user)"""
    team_id = None
    if current_user.is_authenticated:
        team_id = get_current_team_id()
    
    # Filter by team ID if authenticated
    if team_id:
        drill = Drill.query.filter_by(
            id=drill_id,
            team_organization_id=team_id
        ).first_or_404()
    else:
        # For public access, only show public drills
        drill = Drill.query.filter_by(
            id=drill_id,
            is_public=True
        ).first_or_404()
    
    # Check permissions
    if not drill.is_public and (not current_user.is_authenticated or drill.created_by != current_user.id):
        abort(403)
    
    return render_template('drills/view.html', drill=drill)

# API endpoints for AJAX operations
@drill_bp.route('/api/drills', methods=['POST'])
@login_required
def create_drill():
    """Create a new drill"""
    team_id = get_current_team_id()
    if team_id is None and current_user.is_admin:
        return jsonify({'error': 'Please select a team first'}), 400
        
    data = request.json
    
    new_drill = Drill(
        title=data.get('title', 'Untitled Drill'),
        description=data.get('description', ''),
        created_by=current_user.id,
        is_public=data.get('is_public', False),
        team_organization_id=team_id  # Add team ID
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
    team_id = get_current_team_id()
    if team_id is None and current_user.is_admin:
        return jsonify({'error': 'Please select a team first'}), 400
        
    # Filter by team ID
    drill = Drill.query.filter_by(
        id=drill_id,
        team_organization_id=team_id
    ).first_or_404()
    
    # Check permissions
    if drill.created_by != current_user.id and not current_user.is_admin:
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
    team_id = get_current_team_id()
    if team_id is None and current_user.is_admin:
        return jsonify({'error': 'Please select a team first'}), 400
        
    # Filter by team ID
    drill = Drill.query.filter_by(
        id=drill_id,
        team_organization_id=team_id
    ).first_or_404()
    
    # Check permissions
    if drill.created_by != current_user.id and not current_user.is_admin:
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
        elements=data.get('elements', []),
        team_organization_id=team_id  # Add team ID
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
    team_id = get_current_team_id()
    if team_id is None and current_user.is_admin:
        return jsonify({'error': 'Please select a team first'}), 400
        
    # Filter by team ID
    frame = DrillFrame.query.filter_by(
        id=frame_id,
        team_organization_id=team_id
    ).first_or_404()
    
    # Check permissions via the parent drill
    drill = Drill.query.filter_by(
        id=frame.drill_id,
        team_organization_id=team_id
    ).first_or_404()
    
    if drill.created_by != current_user.id and not current_user.is_admin:
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
    team_id = get_current_team_id()
    if team_id is None and current_user.is_admin:
        return jsonify({'error': 'Please select a team first'}), 400
        
    # Filter by team ID
    frame = DrillFrame.query.filter_by(
        id=frame_id,
        team_organization_id=team_id
    ).first_or_404()
    
    # Check permissions via the parent drill
    drill = Drill.query.filter_by(
        id=frame.drill_id,
        team_organization_id=team_id
    ).first_or_404()
    
    if drill.created_by != current_user.id and not current_user.is_admin:
        abort(403)
    
    db.session.delete(frame)
    db.session.commit()
    
    return jsonify({'success': True})

@drill_bp.route('/api/drills/<int:drill_id>', methods=['GET'])
def get_drill(drill_id):
    """Get drill details and frames"""
    team_id = None
    if current_user.is_authenticated:
        team_id = get_current_team_id()
    
    # Filter by team ID if authenticated
    if team_id:
        drill = Drill.query.filter_by(
            id=drill_id,
            team_organization_id=team_id
        ).first_or_404()
    else:
        # For public access, only show public drills
        drill = Drill.query.filter_by(
            id=drill_id,
            is_public=True
        ).first_or_404()
    
    # Check permissions
    if not drill.is_public and (not current_user.is_authenticated or drill.created_by != current_user.id):
        abort(403)
    
    # Get creator info if available
    creator = None
    if drill.created_by:
        from app.models.user import User  # Import here to avoid circular imports
        creator = User.query.get(drill.created_by)
    
    # Get frames - filter by team ID
    frames = DrillFrame.query.filter_by(
        drill_id=drill_id,
        team_organization_id=team_id
    ).order_by(DrillFrame.sequence).all()
    
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
