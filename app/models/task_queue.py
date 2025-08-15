# app/models/task_queue.py
from app import db
from datetime import datetime
import json

class TaskQueue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(100), nullable=False)
    params = db.Column(db.Text, nullable=False)  # JSON-encoded parameters
    status = db.Column(db.String(20), default='pending')  # pending, running, completed, failed
    result = db.Column(db.Text, nullable=True)  # JSON-encoded result
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_params(self, params_dict):
        self.params = json.dumps(params_dict)
    
    def get_params(self):
        return json.loads(self.params) if self.params else {}
    
    def set_result(self, result_dict):
        self.result = json.dumps(result_dict)
    
    def get_result(self):
        return json.loads(self.result) if self.result else {}
