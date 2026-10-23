import re
from datetime import datetime

from app import db

# Structured tags a coach can pick for an opponent's offence and defence.
OFFENSE_TAGS = [
    ('vertical', 'Vertical stack'),
    ('horizontal', 'Horizontal stack'),
    ('side_stack', 'Side stack'),
    ('split_stack', 'Split stack'),
    ('ho_stack', 'Ho stack'),
    ('iso', 'Iso / clear-out'),
    ('hucks_early', 'Hucks early'),
    ('dump_swing', 'Dump-swing patient'),
    ('hammers', 'Hammers / overheads'),
]
DEFENSE_TAGS = [
    ('person', 'Person'),
    ('zone', 'Zone'),
    ('cup', 'Cup'),
    ('junk', 'Junk / clam'),
    ('poach', 'Poaches lanes'),
    ('force_forehand', 'Forces forehand'),
    ('force_backhand', 'Forces backhand'),
    ('straight_up', 'Straight up'),
    ('trap', 'Trap on the sideline'),
    ('zone_in_wind', 'Zone in wind'),
]
TAG_LABELS = dict(OFFENSE_TAGS + DEFENSE_TAGS)

POSITIONS = ('handler', 'cutter', 'hybrid')

_YOUTUBE_PATTERNS = [
    r'(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/|youtube\.com/shorts/|youtube\.com/live/)([A-Za-z0-9_-]{6,})',
]


def extract_youtube_id(url):
    """The video id in a YouTube link, or None."""
    for pattern in _YOUTUBE_PATTERNS:
        match = re.search(pattern, url or '')
        if match:
            return match.group(1)
    return None


def opponent_key(name):
    """Team names compared without case or extra spaces ('Bad  Skid' == 'bad skid')."""
    return ' '.join((name or '').lower().split())


def parse_time(text):
    """'90', '1:30' or '1:01:30' -> seconds. Raises ValueError for anything else."""
    text = (text or '').strip()
    if not re.fullmatch(r'\d+(:\d{1,2}){0,2}', text):
        raise ValueError(text)
    parts = [int(p) for p in text.split(':')]
    if any(p >= 60 for p in parts[1:]):
        raise ValueError(text)
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def format_time(seconds):
    """Seconds -> 'm:ss' (or 'h:mm:ss')."""
    if seconds is None:
        return ''
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


def parse_moments(text):
    """Lines like '1:23 Huck to the end zone' or '1:23-1:40 Zone look'
    -> [{'start': 83, 'end': None, 'label': ...}]. Raises ValueError naming the bad line."""
    moments = []
    for line in (text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^(\d+(?::\d{1,2}){0,2})\s*(?:[-–]\s*(\d+(?::\d{1,2}){0,2}))?\s*(.*)$', line)
        if not match:
            raise ValueError(line)
        start = parse_time(match.group(1))
        end = parse_time(match.group(2)) if match.group(2) else None
        if end is not None and end <= start:
            raise ValueError(line)
        moments.append({'start': start, 'end': end, 'label': match.group(3).strip()})
    return moments


def _tag_list(value):
    return [t for t in (value or '').split(',') if t]


class ScoutingReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    offense_strategy = db.Column(db.Text, nullable=True)
    defense_strategy = db.Column(db.Text, nullable=True)
    strengths = db.Column(db.Text, nullable=True)
    weaknesses = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # Comma-separated keys from OFFENSE_TAGS / DEFENSE_TAGS
    offense_tags = db.Column(db.String(255), nullable=True)
    defense_tags = db.Column(db.String(255), nullable=True)
    # How we plan to beat them
    game_plan = db.Column(db.Text, nullable=True)
    o_line_plan = db.Column(db.Text, nullable=True)
    d_line_plan = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    # The backref in TeamOrganization handles the team relationship

    # Relationships
    tournament = db.relationship('Tournament', backref='scouting_reports')
    game = db.relationship('Game', backref='scouting_report', uselist=False)
    players = db.relationship('OpponentPlayer', backref='scouting_report', lazy='dynamic', cascade='all, delete-orphan')
    clips = db.relationship('ScoutingClip', backref='scouting_report', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ScoutingReport {self.team_name}>'

    @property
    def offense_tag_list(self):
        return _tag_list(self.offense_tags)

    @property
    def defense_tag_list(self):
        return _tag_list(self.defense_tags)

    @property
    def opponent_key(self):
        return opponent_key(self.team_name)

    @property
    def has_game_plan(self):
        return bool(self.game_plan or self.o_line_plan or self.d_line_plan)


class OpponentPlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scouting_report_id = db.Column(db.Integer, db.ForeignKey('scouting_report.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    jersey_number = db.Column(db.String(10), nullable=True)
    position = db.Column(db.String(20), nullable=True)  # handler, cutter, hybrid
    height = db.Column(db.String(20), nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    throwing_ability = db.Column(db.Integer, nullable=True)  # 1-5 scale
    cutting_ability = db.Column(db.Integer, nullable=True)  # 1-5 scale
    defensive_ability = db.Column(db.Integer, nullable=True)  # 1-5 scale
    athletic_ability = db.Column(db.Integer, nullable=True)  # 1-5 scale
    preferred_throws = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # Set by the coach: always shown first and called out on the game card
    is_key_threat = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Which of our players marks them
    matched_player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))

    matched_player = db.relationship('Player')
    clips = db.relationship('ScoutingClip', back_populates='opponent_player', lazy='dynamic')

    def __repr__(self):
        return f'<OpponentPlayer {self.name}>'

    @property
    def ratings(self):
        return [r for r in (self.throwing_ability, self.cutting_ability,
                            self.defensive_ability, self.athletic_ability) if r]

    @property
    def average_rating(self):
        ratings = self.ratings
        return sum(ratings) / len(ratings) if ratings else 0

    @property
    def threat_level(self):
        """'elite', 'high', 'medium', 'low' from the ratings, or None when unrated."""
        if not self.ratings:
            return None
        avg = self.average_rating
        if avg >= 4.5:
            return 'elite'
        if avg >= 3.5:
            return 'high'
        if avg >= 2.5:
            return 'medium'
        return 'low'

    @property
    def sort_key(self):
        """Key threats first, then by rating, then by name."""
        return (not self.is_key_threat, -self.average_rating, self.name.lower())


class ScoutingClip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scouting_report_id = db.Column(db.Integer, db.ForeignKey('scouting_report.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    youtube_link = db.Column(db.String(200), nullable=False)
    start_time = db.Column(db.Integer, nullable=True)  # in seconds
    end_time = db.Column(db.Integer, nullable=True)  # in seconds
    clip_type = db.Column(db.String(50), nullable=True)  # offense, defense, set play
    description = db.Column(db.Text, nullable=True)
    # Extra moments in the same video, one per line: '1:23-1:40 Label'
    moments = db.Column(db.Text, nullable=True)
    opponent_player_id = db.Column(db.Integer, db.ForeignKey('opponent_player.id', ondelete='SET NULL'),
                                   nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))

    opponent_player = db.relationship('OpponentPlayer', back_populates='clips')

    def __repr__(self):
        return f'<ScoutingClip {self.title}>'

    @property
    def video_id(self):
        return extract_youtube_id(self.youtube_link)

    @property
    def thumbnail_url(self):
        video_id = self.video_id
        return f'https://img.youtube.com/vi/{video_id}/mqdefault.jpg' if video_id else None

    def embed_url_for(self, start=None, end=None, autoplay=False):
        video_id = self.video_id
        if not video_id:
            return None
        params = []
        if start:
            params.append(f'start={start}')
        if end:
            params.append(f'end={end}')
        if autoplay:
            params.append('autoplay=1')
        params.append('rel=0')
        return f'https://www.youtube.com/embed/{video_id}?' + '&'.join(params)

    @property
    def youtube_embed_url(self):
        """The YouTube embed URL for this clip, starting and ending at its times."""
        return self.embed_url_for(self.start_time, self.end_time)

    @property
    def moment_list(self):
        try:
            return parse_moments(self.moments)
        except ValueError:
            return []


def games_against(team_id, key):
    """The team's games against an opponent (by opponent_key), newest first."""
    from app.models.game import Game
    games = (Game.query.filter_by(team_organization_id=team_id)
             .order_by(Game.date.is_(None), Game.date.desc(), Game.id.desc()).all())
    return [g for g in games if opponent_key(g.opponent) == key]


def scouting_for_game(game):
    """(the report linked to this game, other reports on the same opponent newest first)."""
    reports = (ScoutingReport.query.filter_by(team_organization_id=game.team_organization_id)
               .order_by(ScoutingReport.date.is_(None), ScoutingReport.date.desc(),
                         ScoutingReport.updated_at.desc()).all())
    linked = next((r for r in reports if r.game_id == game.id), None)
    key = opponent_key(game.opponent)
    others = [r for r in reports if r is not linked and r.opponent_key == key]
    return linked, others
