from app import db
from datetime import datetime

class ExportLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    export_type = db.Column(db.String(50), nullable=False)
    file_path = db.Column(db.String(200), nullable=False)
    parameters = db.Column(db.Text, nullable=True)  # JSON string of export parameters
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='exports')
    
    def __repr__(self):
        return f'<ExportLog {self.export_type} by {self.user_id}>'
