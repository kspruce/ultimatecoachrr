# app/utils/s3_utils.py

import boto3
from botocore.exceptions import ClientError
from flask import current_app
import uuid
from werkzeug.utils import secure_filename
from datetime import datetime

def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=current_app.config['AWS_ACCESS_KEY'],
        aws_secret_access_key=current_app.config['AWS_SECRET_KEY'],
        region_name=current_app.config['AWS_REGION']
    )

def upload_file_to_s3(file, folder, filename=None):
    """
    Upload a file to S3
    :param file: File object to upload
    :param folder: Folder name in S3 (e.g., 'drills', 'playbook')
    :param filename: Optional filename, if None will generate unique name
    :return: S3 URL if successful, None if failed
    """
    if not filename:
        # Generate unique filename
        ext = secure_filename(file.filename).split('.')[-1]
        filename = f"{uuid.uuid4().hex}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{ext}"
    
    # Create S3 path
    s3_path = f"{folder}/{filename}"
    
    try:
        s3_client = get_s3_client()
        extra_args = {}
        
        # Set content type if available
        if hasattr(file, 'content_type'):
            extra_args['ContentType'] = file.content_type
        
        # Upload file
        s3_client.upload_fileobj(
            file,
            current_app.config['AWS_BUCKET_NAME'],
            s3_path,
            ExtraArgs=extra_args
        )
        
        # Generate URL
        url = f"https://{current_app.config['AWS_BUCKET_NAME']}.s3.amazonaws.com/{s3_path}"
        return url, s3_path
    
    except ClientError as e:
        current_app.logger.error(f"S3 upload error: {str(e)}")
        return None, None

def check_s3_configuration():
    """Check if S3 is properly configured"""
    required_configs = ['AWS_ACCESS_KEY', 'AWS_SECRET_KEY', 'AWS_REGION', 'AWS_BUCKET_NAME']
    missing_configs = []
    
    for config in required_configs:
        if not current_app.config.get(config):
            missing_configs.append(config)
    
    if missing_configs:
        current_app.logger.error(f"Missing S3 configurations: {', '.join(missing_configs)}")
        return False
    
    try:
        s3_client = get_s3_client()
        s3_client.head_bucket(Bucket=current_app.config['AWS_BUCKET_NAME'])
        return True
    except Exception as e:
        current_app.logger.error(f"S3 configuration test failed: {str(e)}")
        return False

def delete_file_from_s3(s3_path):
    """
    Delete a file from S3
    :param s3_path: Path of file in S3 bucket
    :return: True if successful, False if failed
    """
    try:
        s3_client = get_s3_client()
        s3_client.delete_object(
            Bucket=current_app.config['AWS_BUCKET_NAME'],
            Key=s3_path
        )
        return True
    except ClientError as e:
        current_app.logger.error(f"S3 delete error: {str(e)}")
        return False
