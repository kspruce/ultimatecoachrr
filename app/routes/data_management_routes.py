"""
Enhanced data management routes for Flask Application
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_login import login_required, current_user
from app.utils.utils import admin_required
from app.utils.enhanced_data_manager import EnhancedDataManager
import os
import json
import shutil
from werkzeug.utils import secure_filename
import tempfile
import zipfile
import logging
from datetime import datetime
import math

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='[%(asctime)s] %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# Create blueprint
bp = Blueprint('data_management', __name__, url_prefix='/admin')

# Initialize data manager
manager = None

def get_manager():
    global manager
    if manager is None:
        # Always use /tmp directory which should be writable
        export_dir = '/tmp/data_exports'
        manager = EnhancedDataManager(export_dir=export_dir)
    return manager


@bp.route('/enhanced-data-management')
@login_required
@admin_required
def data_management():
    """Enhanced data management interface."""
    manager = get_manager()  # Get the manager instance
    model_info = manager.get_model_info()

    
    # Get available exports with details
    exports = manager.get_available_exports()
    
    # Calculate total records
    total_records = sum(model['record_count'] for model in model_info['models'].values())
    
    # Get last export date
    last_export = exports[0]['date'] if exports else None
    
    return render_template('admin/enhanced_data_management.html', 
                         model_info=model_info, 
                         exports=exports,
                         total_records=total_records,
                         last_export=last_export,
                         export_dir=manager.export_dir)

@bp.route('/export-data', methods=['POST'])
@login_required
@admin_required
def export_data_route():
    """Export data via web interface."""
    try:
        export_name = request.form.get('export_name', '').strip()
        include_metadata = request.form.get('include_metadata') == 'on'
        export_format = request.form.get('export_format', 'json')
        
        # Generate custom name if provided
        custom_name = None
        if export_name:
            safe_name = secure_filename(export_name)
            custom_name = f"data_exports_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Always generate in-memory export for direct download
        memory_file, filename = get_manager().export_all_data(
            timestamp=True if not custom_name else False,
            custom_name=custom_name,
            format=export_format,
            in_memory=True  # Always use in-memory for direct download
        )
        
        # Send file directly to browser
        return send_file(
            memory_file,
            as_attachment=True,
            download_name=filename,
            mimetype='application/zip'
        )
                
    except Exception as e:
        logger.error(f"Export failed: {e}")
        flash(f'❌ Export failed: {str(e)}', 'error')
        return redirect(url_for('data_management.data_management'))




@bp.route('/import-data', methods=['POST'])
@login_required
@admin_required
def import_data_route():
    """Import data via web interface."""
    import_type = request.form.get('import_type', '')
    
    if import_type == 'file_upload':
        # File upload
        if 'import_file' not in request.files or not request.files['import_file'].filename:
            flash('❌ No file selected for upload', 'error')
            return redirect(url_for('data_management.data_management'))
            
        import_file = request.files['import_file']
        clear_existing = request.form.get('clear_existing') == 'on'
        
        try:
            # Save uploaded file to temporary location
            temp_dir = tempfile.mkdtemp()
            temp_file = os.path.join(temp_dir, secure_filename(import_file.filename))
            import_file.save(temp_file)
            
            # Import from ZIP file
            summary = get_manager().import_from_zip(temp_file, clear_existing=clear_existing)
            
            # Clean up
            shutil.rmtree(temp_dir)
            
            if summary['status'] == 'completed':
                total_records = sum(
                    info.get('records_imported', 0) 
                    for info in summary['results'].values() 
                    if isinstance(info, dict)
                )
                
                # Count errors
                total_errors = sum(
                    len(info.get('errors', [])) 
                    for info in summary['results'].values() 
                    if isinstance(info, dict)
                )
                
                if total_errors > 0:
                    flash(f'⚠️ Data imported with warnings! {total_records} records imported, {total_errors} errors occurred.', 'warning')
                else:
                    flash(f'✅ Data imported successfully! {total_records} records imported.', 'success')
            else:
                flash(f'❌ Import failed: {summary.get("error", "Unknown error")}', 'error')
                
        except Exception as e:
            logger.error(f"Import failed: {e}")
            flash(f'❌ Import failed: {str(e)}', 'error')
            
    elif import_type == 'directory_import':
        # Directory import
        import_dir = request.form.get('import_dir')
        clear_existing = request.form.get('clear_existing') == 'on'
        
        if not import_dir:
            flash('❌ Please specify an import directory', 'error')
            return redirect(url_for('data_management.data_management'))
        
        if not os.path.exists(import_dir):
            flash(f'❌ Import directory does not exist: {import_dir}', 'error')
            return redirect(url_for('data_management.data_management'))
        
        try:
            summary = get_manager().import_all_data(import_dir, clear_existing=clear_existing)
            
            # Process summary and show appropriate message
            # (same as in the file upload case)
            
        except Exception as e:
            logger.error(f"Import failed: {e}")
            flash(f'❌ Import failed: {str(e)}', 'error')
    else:
        flash('❌ Invalid import type', 'error')

@bp.route('/export-details/<path:export_path>')
@login_required
@admin_required
def export_details(export_path):
    """Get detailed information about an export."""
    try:
        if not os.path.exists(export_path):
            return jsonify({'error': 'Export not found'}), 404
        
        details = {}
        
        # Load metadata
        metadata_path = os.path.join(export_path, 'metadata.json')
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                details['metadata'] = json.load(f)
        
        # Load summary
        summary_path = os.path.join(export_path, 'export_summary.json')
        if os.path.exists(summary_path):
            with open(summary_path, 'r') as f:
                details['summary'] = json.load(f)
        
        # Get file list
        files = []
        for filename in os.listdir(export_path):
            filepath = os.path.join(export_path, filename)
            if os.path.isfile(filepath):
                file_info = {
                    'name': filename,
                    'size': format_file_size(os.path.getsize(filepath)),
                    'modified': datetime.fromtimestamp(
                        os.path.getmtime(filepath)
                    ).strftime('%Y-%m-%d %H:%M:%S')
                }
                files.append(file_info)
        
        details['files'] = files
        details['total_size'] = get_directory_size(export_path)
        
        return jsonify(details)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/download-export')
@login_required
@admin_required
def download_export():
    """Download an export as a ZIP file."""
    export_path = request.args.get('path')
    
    if not export_path or not os.path.exists(export_path):
        flash('❌ Export not found', 'error')
        return redirect(url_for('data_management.data_management'))
    
    try:
        # Check if ZIP already exists
        zip_path = export_path + '.zip'
        if not os.path.exists(zip_path):
            # Create a ZIP file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(export_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, export_path)
                        zipf.write(file_path, arcname)
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=os.path.basename(zip_path),
            mimetype='application/zip'
        )
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        flash(f'❌ Download failed: {str(e)}', 'error')
        return redirect(url_for('data_management.data_management'))

@bp.route('/download-excel')
@login_required
@admin_required
def download_excel():
    """Download data as Excel file."""
    table_name = request.args.get('table')
    manager = get_manager()  # Get the manager instance
    model_info = manager.get_model_info()
    
    try:
        output, filename = manager.export_to_excel(table_name)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        logger.error(f"Excel export failed: {e}")
        flash(f'❌ Excel export failed: {str(e)}', 'error')
        return redirect(url_for('data_management.data_management'))

@bp.route('/delete-export', methods=['POST'])
@login_required
@admin_required
def delete_export():
    """Delete an export directory."""
    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            export_path = data.get('path')
        else:
            export_path = request.form.get('path')
        
        if not export_path or not os.path.exists(export_path):
            if request.is_json:
                return jsonify({'error': 'Export not found'}), 404
            else:
                flash('❌ Export not found', 'error')
                return redirect(url_for('data_management.data_management'))
        
        # Delete the directory
        shutil.rmtree(export_path)
        
        # Delete ZIP file if it exists
        zip_path = export_path + '.zip'
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        if request.is_json:
            return jsonify({'success': True, 'message': f'Export {export_path} deleted successfully'})
        else:
            flash(f'✅ Export {os.path.basename(export_path)} deleted successfully', 'success')
            return redirect(url_for('data_management.data_management'))
        
    except Exception as e:
        logger.error(f"Delete export failed: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'❌ Delete failed: {str(e)}', 'error')
            return redirect(url_for('data_management.data_management'))


@bp.route('/model-details/<table_name>')
@login_required
@admin_required
def model_details_api(table_name):
    """Get detailed information about a specific model."""
    manager = get_manager()  # Get the manager instance
    model_info = manager.get_model_info()
    try:
        if table_name not in manager.models:
            return jsonify({'error': 'Model not found'}), 404
        
        model = manager.models[table_name]
        
        # Get sample data (first 5 records)
        sample_records = []
        try:
            records = model.query.limit(5).all()
            for record in records:
                record_dict = {}
                for column in model.__table__.columns:
                    value = getattr(record, column.name)
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    record_dict[column.name] = value
                sample_records.append(record_dict)
        except Exception as e:
            logger.warning(f"Could not fetch sample data for {table_name}: {e}")
        
        # Get model info
        info = manager.get_model_info()
        model_info = info['models'][table_name]
        model_info['sample_data'] = sample_records
        
        return jsonify(model_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_directory_size(path):
    """Get the total size of a directory in bytes, formatted as human-readable string."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return format_file_size(total_size)

def format_file_size(size_bytes):
    """Format file size in bytes as human-readable string."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


