#!/usr/bin/env python3
import os
import shutil
from datetime import datetime
import sys

def print_status(message):
    """Helper function to print status messages"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def fix_circular_reference():
    """Fix the circular reference between Point and CuttingSkill models"""
    try:
        print_status("Starting to fix circular reference between Point and CuttingSkill models...")
        
        # 1. Update the cutting_skill.py file
        cutting_skill_path = 'app/models/cutting_skill.py'
        if os.path.exists(cutting_skill_path):
            print_status(f"Updating {cutting_skill_path}")
            shutil.copy('cutting_skill.py', cutting_skill_path)
        else:
            print_status(f"Error: {cutting_skill_path} does not exist")
            return 1
        
        # 2. Update the point.py file
        point_path = 'app/models/point.py'
        if os.path.exists(point_path):
            print_status(f"Updating {point_path}")
            shutil.copy('point.py', point_path)
        else:
            print_status(f"Error: {point_path} does not exist")
            return 1
        
        print_status("Fix completed successfully!")
        print_status("Now run your reset_db.py script to reset the database.")
        return 0
        
    except Exception as e:
        print_status(f"Error during fix: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(fix_circular_reference())