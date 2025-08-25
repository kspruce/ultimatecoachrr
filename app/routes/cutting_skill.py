from flask import Blueprint, jsonify, request, render_template, session
from flask_login import login_required, current_user
from app_factory import db
from app.models.point import Point
from app.models.cutting_skill import CuttingSkill

bp = Blueprint('cutting_skill', __name__, url_prefix='/cutting-skills')

# Helper function to get current team ID
def get_current_team_id():
    """Get the current team ID based on user role."""
    if current_user.is_admin:
        return session.get('current_team_id')
    return current_user.team_organization_id

@bp.route('/record/<int:point_id>', methods=['POST'])
@login_required
def record_cutting_skill(point_id):
    try:
        team_id = get_current_team_id()
        if team_id is None and current_user.is_admin:
            return jsonify({'error': 'Please select a team first'}), 400
            
        data = request.get_json()
        
        # Verify point belongs to current team
        point = Point.query.filter_by(id=point_id, team_organization_id=team_id).first_or_404()
        
        # Create new cutting skill record
        cutting_skill = CuttingSkill(
            point_id=point_id,
            player_id=int(data['player_id']),
            cutting_type=data['cutting_type'],
            outcome=data['outcome'],
            field_position_x=float(data.get('field_position_x', 0)),
            field_position_y=float(data.get('field_position_y', 0)),
            team_organization_id=team_id  # Add team ID
        )
        
        db.session.add(cutting_skill)
        db.session.commit()
        
        return jsonify(cutting_skill.to_dict()), 201
    
    except Exception as e:
        print("Error recording cutting skill:", str(e))
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@bp.route('/list/<int:point_id>', methods=['GET'])
@login_required
def list_cutting_skills(point_id):
    try:
        team_id = get_current_team_id()
        if team_id is None and current_user.is_admin:
            return jsonify({'error': 'Please select a team first'}), 400
            
        # Verify point belongs to current team
        point = Point.query.filter_by(id=point_id, team_organization_id=team_id).first_or_404()
        
        # Filter by team and point
        cutting_skills = CuttingSkill.query.filter_by(
            point_id=point_id,
            team_organization_id=team_id
        ).all()
        
        return jsonify([skill.to_dict() for skill in cutting_skills]), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/delete/<int:skill_id>', methods=['DELETE'])
@login_required
def delete_cutting_skill(skill_id):
    try:
        team_id = get_current_team_id()
        if team_id is None and current_user.is_admin:
            return jsonify({'error': 'Please select a team first'}), 400
            
        # Verify skill belongs to current team
        skill = CuttingSkill.query.filter_by(
            id=skill_id,
            team_organization_id=team_id
        ).first_or_404()
        
        db.session.delete(skill)
        db.session.commit()
        return jsonify({'message': 'Cutting skill deleted successfully'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
