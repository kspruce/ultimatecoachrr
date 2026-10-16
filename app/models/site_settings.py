# app/models/site_settings.py
from app import db


class SiteSettings(db.Model):
    """Site-wide switches that only superadmins can change. There is one row."""
    __tablename__ = 'site_settings'

    id = db.Column(db.Integer, primary_key=True)

    # False: new teams can only sign up with a link from a superadmin.
    # True: anyone can register a team at /auth/register-team.
    open_team_registration = db.Column(db.Boolean, default=False, nullable=False)

    @classmethod
    def get(cls):
        """The settings row, created with defaults the first time it's needed."""
        settings = cls.query.order_by(cls.id).first()
        if settings is None:
            settings = cls(open_team_registration=False)
            db.session.add(settings)
            db.session.commit()
        return settings

    def __repr__(self):
        return f'<SiteSettings open_team_registration={self.open_team_registration}>'
