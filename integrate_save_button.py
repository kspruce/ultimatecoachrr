#!/usr/bin/env python
"""
Script to integrate the "Save Stats" button functionality with your existing stats.py file.
This script will:
1. Create necessary directories
2. Copy the stats_storage.py model file to app/models/
3. Copy the stats_storage_routes.py file to app/routes/
4. Copy the stats_storage.js file to static/js/
5. Create the templates directory for stats management
6. Copy the manage.html and compare.html templates to app/templates/stats/
7. Apply the necessary changes to the HTML files to add the "Save Stats" button
"""

import os
import shutil
import re
import sys

def create_directory(directory):
    """Create directory if it doesn't exist"""
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Created directory: {directory}")

def copy_file(src, dest):
    """Copy file from src to dest"""
    shutil.copy2(src, dest)
    print(f"Copied {src} to {dest}")

def add_save_button_to_file(file_path):
    """Add the 'Save Stats' button to HTML files"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Find the header section
    header_section_pattern = r'(<!-- Header Section -->.*?<div class="row mb-4">.*?<div class="col-md-\d+">.*?<h1>.*?</h1>.*?</div>)'
    header_section_match = re.search(header_section_pattern, content, re.DOTALL)
    
    if header_section_match:
        header_section = header_section_match.group(1)
        # Add the save button div after the header div
        modified_header = header_section + '\n        <div class="col-md-4 text-end">\n            <button id="saveStatsBtn" class="btn btn-primary">\n                <i class="bi bi-save"></i> Save Stats to Database\n            </button>\n        </div>'
        content = content.replace(header_section, modified_header)
        print(f"Added save button to {file_path}")
    else:
        print(f"Warning: Could not find header section in {file_path}")
    
    # Add the JavaScript file reference before the end of the block scripts
    if '{% block scripts %}' in content:
        script_pattern = r'({% block scripts %}.*?)({% endblock %})'
        script_match = re.search(script_pattern, content, re.DOTALL)
        
        if script_match:
            script_content = script_match.group(1)
            script_end = script_match.group(2)
            modified_script = script_content + '\n<script src="{{ url_for(\'static\', filename=\'js/stats_storage.js\') }}"></script>\n' + script_end
            content = content.replace(script_match.group(0), modified_script)
            print(f"Added script reference to {file_path}")
        else:
            print(f"Warning: Could not find script block in {file_path}")
    else:
        # If there's no scripts block, add one before the end of the file
        content = content + '\n\n{% block scripts %}\n<script src="{{ url_for(\'static\', filename=\'js/stats_storage.js\') }}"></script>\n{% endblock %}'
        print(f"Added new script block to {file_path}")
    
    # Write the modified content back to the file
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

def add_using_saved_stats_alert(file_path):
    """Add the 'using saved stats' alert to HTML files"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Find the container div
    container_pattern = r'(<div class="container-fluid">)'
    container_match = re.search(container_pattern, content)
    
    if container_match:
        container_div = container_match.group(1)
        # Add the alert div after the container div
        alert_div = container_div + '\n    {% if using_saved_stats %}\n    <div class="alert alert-info">\n        <i class="bi bi-info-circle"></i> Using saved stats. <a href="#" id="recalculateStatsBtn" class="alert-link">Recalculate</a>\n    </div>\n    {% endif %}'
        content = content.replace(container_div, alert_div)
        print(f"Added saved stats alert to {file_path}")
    else:
        print(f"Warning: Could not find container div in {file_path}")
    
    # Write the modified content back to the file
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

def add_recalculate_script(file_path):
    """Add the recalculate script to HTML files"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Add the JavaScript for the recalculate button
    if '{% block scripts %}' in content:
        script_pattern = r'({% block scripts %}.*?)({% endblock %})'
        script_match = re.search(script_pattern, content, re.DOTALL)
        
        if script_match:
            script_content = script_match.group(1)
            script_end = script_match.group(2)
            recalculate_script = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    const recalculateBtn = document.getElementById('recalculateStatsBtn');
    if (recalculateBtn) {
        recalculateBtn.addEventListener('click', function(e) {
            e.preventDefault();
            // Add a parameter to force recalculation
            const url = new URL(window.location.href);
            url.searchParams.set('recalculate', 'true');
            window.location.href = url.toString();
        });
    }
});
</script>
"""
            modified_script = script_content + recalculate_script + script_end
            content = content.replace(script_match.group(0), modified_script)
            print(f"Added recalculate script to {file_path}")
        else:
            print(f"Warning: Could not find script block in {file_path}")
    else:
        # If there's no scripts block, add one before the end of the file
        recalculate_script = """
{% block scripts %}
<script src="{{ url_for('static', filename='js/stats_storage.js') }}"></script>
<script>
document.addEventListener('DOMContentLoaded', function() {
    const recalculateBtn = document.getElementById('recalculateStatsBtn');
    if (recalculateBtn) {
        recalculateBtn.addEventListener('click', function(e) {
            e.preventDefault();
            // Add a parameter to force recalculation
            const url = new URL(window.location.href);
            url.searchParams.set('recalculate', 'true');
            window.location.href = url.toString();
        });
    }
});
</script>
{% endblock %}
"""
        content = content + recalculate_script
        print(f"Added new script block with recalculate script to {file_path}")
    
    # Write the modified content back to the file
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

def main():
    """Main function to integrate the save button functionality"""
    # Create necessary directories
    create_directory('app/models')
    create_directory('app/routes')
    create_directory('app/templates/stats')
    create_directory('static/js')
    
    # Copy model files
    copy_file('app/models/stats_storage.py', 'app/models/stats_storage.py')
    
    # Copy route files
    copy_file('app/routes/stats_storage_routes.py', 'app/routes/stats_storage_routes.py')
    
    # Copy JavaScript files
    copy_file('static/js/stats_storage.js', 'static/js/stats_storage.js')
    
    # Copy template files
    copy_file('app/templates/stats/manage.html', 'app/templates/stats/manage.html')
    copy_file('app/templates/stats/compare.html', 'app/templates/stats/compare.html')
    
    # Add save button to HTML files
    html_files = ['index.html', 'team_stats.html', 'game_stats.html', 'player_stats.html']
    for html_file in html_files:
        if os.path.exists(html_file):
            add_save_button_to_file(html_file)
            add_using_saved_stats_alert(html_file)
            add_recalculate_script(html_file)
        else:
            print(f"Warning: {html_file} not found")
    
    print("\nIntegration complete!")
    print("\nNext steps:")
    print("1. Update your __init__.py file to register the stats_storage_bp blueprint")
    print("2. Update your stats.py file using the instructions in stats_integration_patch.md")
    print("3. Run the migration script to create the new tables")
    print("4. Restart your application")

if __name__ == "__main__":
    main()