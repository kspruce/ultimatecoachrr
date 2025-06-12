from flask import current_app, url_for
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
from .s3_utils import upload_file_to_s3, delete_file_from_s3
import logging

logger = logging.getLogger(__name__)

class StorageError(Exception):
    """Custom exception for storage operations"""
    pass

def get_unique_filename(filename):
    """Generate a unique filename while preserving extension"""
    if not filename:
        return None
    
    # Get the file extension
    ext = ''
    if '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[1].lower()
    
    # Generate unique filename
    unique_name = f"{uuid.uuid4().hex}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}{ext}"
    return secure_filename(unique_name)

def validate_file(file, allowed_types=None):
    """
    Validate file type and size
    :param file: FileStorage object
    :param allowed_types: List of allowed file extensions
    :return: (bool, str) - (is_valid, error_message)
    """
    if not file:
        return False, "No file provided"

    # Check file size
    try:
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)  # Reset file pointer
        
        if size > current_app.config['MAX_CONTENT_LENGTH']:
            max_mb = current_app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024)
            return False, f"File too large. Maximum size is {max_mb}MB"
    except Exception as e:
        return False, f"Error checking file size: {str(e)}"

    # Check file type if specified
    if allowed_types:
        if '.' not in file.filename:
            return False, "No file extension provided"
        
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_types:
            return False, f"File type not allowed. Allowed types: {', '.join(allowed_types)}"

    return True, None

def store_file(file, folder, filename=None, allowed_types=None):
    """
    Store a file using the configured storage system (S3 or local)
    
    :param file: FileStorage object
    :param folder: Destination folder
    :param filename: Optional custom filename
    :param allowed_types: Optional list of allowed file extensions
    :return: tuple (url, path)
    """
    try:
        # Validate file
        is_valid, error_message = validate_file(file, allowed_types)
        if not is_valid:
            raise StorageError(error_message)

        # Generate unique filename if not provided
        if not filename:
            filename = get_unique_filename(file.filename)

        # Use S3 if configured, otherwise use local storage
        if current_app.config.get('AWS_ACCESS_KEY'):
            return store_file_s3(file, folder, filename)
        else:
            return store_file_local(file, folder, filename)

    except Exception as e:
        logger.error(f"Error storing file: {str(e)}")
        raise StorageError(f"Failed to store file: {str(e)}")

def store_file_s3(file, folder, filename):
    """
    Store file in S3
    :return: tuple (url, s3_key)
    """
    try:
        s3_path = f"{folder}/{filename}"
        url, s3_key = upload_file_to_s3(file, s3_path)
        
        if not url:
            raise StorageError("Failed to upload file to S3")
        
        return url, s3_key

    except Exception as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        raise StorageError(f"S3 upload failed: {str(e)}")

def store_file_local(file, folder, filename):
    """
    Store file in local filesystem
    :return: tuple (url, file_path)
    """
    try:
        # Create folder if it doesn't exist
        folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(folder_path, exist_ok=True)

        # Save file
        file_path = os.path.join(folder_path, filename)
        file.save(file_path)

        # Generate URL for local file
        url = url_for('static', filename=os.path.join(folder, filename))
        
        return url, file_path

    except Exception as e:
        logger.error(f"Error saving file locally: {str(e)}")
        raise StorageError(f"Local file save failed: {str(e)}")

def delete_file(file_path):
    """
    Delete a file from storage
    :param file_path: S3 key or local file path
    :return: bool indicating success
    """
    try:
        if current_app.config.get('AWS_ACCESS_KEY'):
            return delete_file_from_s3(file_path)
        else:
            local_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_path)
            if os.path.exists(local_path):
                os.remove(local_path)
                return True
            return False

    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        return False

def get_file_url(file_path):
    """
    Get URL for a stored file
    :param file_path: S3 key or local file path
    :return: URL string
    """
    try:
        if not file_path:
            return None

        if current_app.config.get('AWS_ACCESS_KEY'):
            return f"https://{current_app.config['AWS_BUCKET_NAME']}.s3.amazonaws.com/{file_path}"
        else:
            return url_for('static', filename=file_path)

    except Exception as e:
        logger.error(f"Error generating file URL: {str(e)}")
        return None

def cleanup_temp_files():
    """
    Clean up temporary files older than 24 hours
    """
    try:
        temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
        if not os.path.exists(temp_dir):
            return

        current_time = datetime.now()
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
            if (current_time - file_modified).days >= 1:
                try:
                    os.remove(file_path)
                    logger.info(f"Cleaned up temporary file: {filename}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {filename}: {str(e)}")

    except Exception as e:
        logger.error(f"Error during temp file cleanup: {str(e)}")

def get_storage_stats():
    """
    Get storage statistics
    :return: dict with storage information
    """
    try:
        stats = {
            'using_s3': bool(current_app.config.get('AWS_ACCESS_KEY')),
            'upload_folder': current_app.config['UPLOAD_FOLDER'],
            'max_file_size_mb': current_app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024),
            'allowed_extensions': current_app.config['ALLOWED_EXTENSIONS'],
            'directories': {}
        }

        # Get local directory sizes
        if os.path.exists(current_app.config['UPLOAD_FOLDER']):
            for folder in ['drills', 'playbook', 'theory', 'temp']:
                folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
                if os.path.exists(folder_path):
                    size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(folder_path)
                        for filename in filenames
                    )
                    stats['directories'][folder] = {
                        'size_mb': size / (1024 * 1024),
                        'file_count': sum(len(files) for _, _, files in os.walk(folder_path))
                    }

        return stats

    except Exception as e:
        logger.error(f"Error getting storage stats: {str(e)}")
        return None
