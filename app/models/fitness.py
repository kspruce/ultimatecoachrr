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
    
    @classmethod
    def create_default_metrics(cls):
        """Create default fitness metrics for ultimate frisbee"""
        metrics = [
            # Sprinting Metrics
            {
                'name': '20-Yard Sprint',
                'description': 'Measures short-burst acceleration, critical for making quick cuts. Start from standstill.',
                'unit': 'seconds',
                'higher_is_better': False,
                'active': True
            },
            {
                'name': '40-Yard Sprint',
                'description': 'Evaluates medium-distance speed, important for deep cuts. Start from standstill.',
                'unit': 'seconds',
                'higher_is_better': False,
                'active': True
            },
            {
                'name': 'Flying 20',
                'description': 'Sprint time for 20 yards after a 10-yard running start, measuring top speed.',
                'unit': 'seconds',
                'higher_is_better': False,
                'active': True
            },
            {
                'name': '5-10-5 Shuttle/Pro Agility',
                'description': 'Sprint 5 yards to the right, 10 yards to the left, then 5 yards back to start.',
                'unit': 'seconds',
                'higher_is_better': False,
                'active': True
            },
            {
                'name': 'Change of Direction Speed',
                'description': 'Time to complete a zigzag course with sharp 90-degree cuts.',
                'unit': 'seconds',
                'higher_is_better': False,
                'active': True
            },
            
            # Endurance Metrics
            {
                'name': 'Beep Test/Yo-Yo Test',
                'description': 'Progressive shuttle run test measuring aerobic capacity. Record the highest level completed.',
                'unit': 'level',
                'higher_is_better': True,
                'active': True
            },
            {
                'name': '1-Mile Run',
                'description': 'Measures sustained running capacity over one mile distance.',
                'unit': 'min:sec',
                'higher_is_better': False,
                'active': True
            },
            {
                'name': '300-Yard Shuttle',
                'description': 'Run back and forth between two lines 25 yards apart six times.',
                'unit': 'seconds',
                'higher_is_better': False,
                'active': True
            },
            {
                'name': 'Ultimate-Specific Conditioning Test',
                'description': 'Complete 10 full-field cuts with disc catches in minimal time.',
                'unit': 'points',
                'higher_is_better': True,
                'active': True
            },
            {
                'name': 'Recovery Heart Rate',
                'description': 'Heart rate 1 minute after completing a standardized sprint workout.',
                'unit': 'BPM',
                'higher_is_better': False,
                'active': True
            },
            
            # Power & Jumping Metrics
            {
                'name': 'Vertical Jump',
                'description': 'Maximum vertical leap from standing position.',
                'unit': 'inches',
                'higher_is_better': True,
                'active': True
            },
            {
                'name': 'Broad Jump',
                'description': 'Maximum horizontal jump from standing position.',
                'unit': 'inches',
                'higher_is_better': True,
                'active': True
            },
            {
                'name': 'Box Jump',
                'description': 'Highest box that can be jumped onto from standing position.',
                'unit': 'inches',
                'higher_is_better': True,
                'active': True
            },
            
            # Throwing Power & Accuracy
            {
                'name': 'Maximum Pull Distance',
                'description': 'Maximum distance of controlled pull throw.',
                'unit': 'yards',
                'higher_is_better': True,
                'active': True
            },
            {
                'name': 'Throwing Accuracy',
                'description': 'Points scored hitting targets at various distances in 1 minute.',
                'unit': 'points',
                'higher_is_better': True,
                'active': True
            },
            
            # Strength & Core Metrics
            {
                'name': 'Plank Hold',
                'description': 'Maximum time maintaining proper plank position.',
                'unit': 'seconds',
                'higher_is_better': True,
                'active': True
            },
            {
                'name': 'Push-Ups',
                'description': 'Maximum number of proper form push-ups completed.',
                'unit': 'count',
                'higher_is_better': True,
                'active': True
            },
            {
                'name': 'Pull-Ups',
                'description': 'Maximum number of proper form pull-ups completed.',
                'unit': 'count',
                'higher_is_better': True,
                'active': True
            },
            {
                'name': 'Squat Endurance',
                'description': 'Maximum number of bodyweight squats in 1 minute.',
                'unit': 'count',
                'higher_is_better': True,
                'active': True
            },
            
            # Ultimate-Specific Skills
            {
                'name': 'Lateral Quickness Drill',
                'description': 'Time to complete a defensive footwork drill with lateral movements.',
                'unit': 'seconds',
                'higher_is_better': False,
                'active': True
            },
            {
                'name': 'Jump & Reach',
                'description': 'Maximum height reached when jumping for a disc.',
                'unit': 'inches',
                'higher_is_better': True,
                'active': True
            }
        ]
        
        # Check if metrics already exist to avoid duplicates
        existing_metrics = {m.name for m in cls.query.all()}
        
        metrics_added = 0
        for metric_data in metrics:
            if metric_data['name'] not in existing_metrics:
                metric = cls(**metric_data)
                db.session.add(metric)
                metrics_added += 1
        
        db.session.commit()
        return metrics_added


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
