import os
import shutil
from datetime import datetime
import sys

def print_status(message):
    """Helper function to print status messages"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def fix_cutting_skill():
    """Fix the cutting skill tracking feature"""
    try:
        print_status("Starting to fix cutting skill tracking feature...")
        
        # 1. Fix the cutting_skill.py file
        cutting_skill_path = 'app/models/cutting_skill.py'
        if os.path.exists(cutting_skill_path):
            with open(cutting_skill_path, 'r') as f:
                content = f.read()
            
            # Check if we need to update the relationship
            if 'back_populates' in content and 'backref' not in content:
                print_status("Updating cutting_skill.py to use backref instead of back_populates")
                content = content.replace(
                    "player = db.relationship('Player', back_populates='cutting_skills')",
                    "player = db.relationship('Player', foreign_keys=[player_id], backref=db.backref('cutting_skills', lazy='dynamic'))"
                )
                with open(cutting_skill_path, 'w') as f:
                    f.write(content)
        else:
            print_status(f"Error: {cutting_skill_path} does not exist")
            return 1
        
        # 2. Fix the routes file
        routes_dir = 'app/routes'
        routes_file = os.path.join(routes_dir, 'cutting_skill.py')
        routes_file_backup = os.path.join(routes_dir, 'cutting_skill_routes.py')
        
        if not os.path.exists(routes_file) and os.path.exists(routes_file_backup):
            print_status(f"Copying {routes_file_backup} to {routes_file}")
            shutil.copy(routes_file_backup, routes_file)
        
        # 3. Fix the app/__init__.py file
        init_file = 'app/__init__.py'
        if os.path.exists(init_file):
            with open(init_file, 'r') as f:
                content = f.read()
            
            # Check if the blueprint registration is correct
            if 'from app.routes.cutting_skill_routes import bp as cutting_skill_routes_bp' in content:
                print_status("Fixing blueprint registration in app/__init__.py")
                content = content.replace(
                    'from app.routes.cutting_skill_routes import bp as cutting_skill_routes_bp',
                    'from app.routes.cutting_skill import bp as cutting_skill_bp'
                )
                content = content.replace(
                    'app.register_blueprint(cutting_skill_routes_bp)',
                    'app.register_blueprint(cutting_skill_bp)'
                )
                with open(init_file, 'w') as f:
                    f.write(content)
            
            # Check if the model import is correct
            if 'Cutting_Skill' in content:
                print_status("Fixing model import in app/__init__.py")
                content = content.replace('Cutting_Skill', 'CuttingSkill')
                with open(init_file, 'w') as f:
                    f.write(content)
        
        # 4. Fix the app/models/__init__.py file
        models_init_file = 'app/models/__init__.py'
        if os.path.exists(models_init_file):
            with open(models_init_file, 'r') as f:
                content = f.read()
            
            # Check if CuttingSkill is imported
            if 'from app.models.cutting_skill import CuttingSkill' not in content:
                print_status("Adding CuttingSkill import to app/models/__init__.py")
                # Add import at the end of the file
                content += '\nfrom app.models.cutting_skill import CuttingSkill\n'
                with open(models_init_file, 'w') as f:
                    f.write(content)
        
        # 5. Fix the point.py file to use backref instead of back_populates
        point_file = 'app/models/point.py'
        if os.path.exists(point_file):
            with open(point_file, 'r') as f:
                content = f.read()
            
            # Check if we need to update the relationship
            if 'cutting_skills = db.relationship' in content:
                print_status("Removing explicit relationship from point.py (will use backref instead)")
                # Remove the explicit relationship line
                lines = content.split('\n')
                new_lines = []
                for line in lines:
                    if 'cutting_skills = db.relationship' not in line:
                        new_lines.append(line)
                content = '\n'.join(new_lines)
                with open(point_file, 'w') as f:
                    f.write(content)
        
        print_status("Fix completed successfully!")
        return 0
        
    except Exception as e:
        print_status(f"Error during fix: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(fix_cutting_skill())