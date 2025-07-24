# app/models/fitness.py
from app import db
from datetime import datetime

class FitnessMetric(db.Model):
    __tablename__ = 'fitness_metric'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    unit = db.Column(db.String(20), nullable=False)
    higher_is_better = db.Column(db.Boolean, default=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Use string reference for the relationship
    records = db.relationship('FitnessRecord', back_populates='metric', lazy='dynamic')
    
    def __repr__(self):
        return f'<FitnessMetric {self.name}>'
    
    @property
    def team_average(self):
        """Calculate team average for this metric"""
        from sqlalchemy import func
        result = db.session.query(func.avg(FitnessRecord.value)).filter_by(metric_id=self.id).scalar()
        return round(result, 2) if result else None
    
    @property
    def record_holder(self):
        """Get the record holder for this metric"""
        if self.higher_is_better:
            record = self.records.order_by(FitnessRecord.value.desc()).first()
        else:
            record = self.records.order_by(FitnessRecord.value).first()
        return record


class FitnessRecord(db.Model):
    __tablename__ = 'fitness_record'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    metric_id = db.Column(db.Integer, db.ForeignKey('fitness_metric.id'), nullable=False)
    value = db.Column(db.Float, nullable=False)
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    # Use string references for the relationships
    player = db.relationship('Player', back_populates='fitness_records')
    metric = db.relationship('FitnessMetric', back_populates='records')
    
    def __repr__(self):
        return f'<FitnessRecord {self.id}: {self.value}>'
