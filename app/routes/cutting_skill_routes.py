from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required
from app import db
from app.models.point import Point
from app.models.cutting_skill import CuttingSkill

bp = Blueprint('cutting_skill', __name__, url_prefix='/cutting-skills')

@bp.route('/record/<int:point_id>', methods=['POST'])
@login_required
def record_cutting_skill(point_id):
    try:
        data = request.get_json()
        point = Point.query.get_or_404(point_id)
        
        # Create new cutting skill record
        cutting_skill = CuttingSkill(
            point_id=point_id,
            player_id=int(data['player_id']),
            cutting_type=data['cutting_type'],
            outcome=data['outcome'],
            field_position_x=float(data.get('field_position_x', 0)),
            field_position_y=float(data.get('field_position_y', 0))
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
        cutting_skills = CuttingSkill.query.filter_by(point_id=point_id).all()
        return jsonify([skill.to_dict() for skill in cutting_skills]), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/delete/<int:skill_id>', methods=['DELETE'])
@login_required
def delete_cutting_skill(skill_id):
    try:
        skill = CuttingSkill.query.get_or_404(skill_id)
        db.session.delete(skill)
        db.session.commit()
        return jsonify({'message': 'Cutting skill deleted successfully'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500