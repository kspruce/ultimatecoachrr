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

# What our players are good at marking...
DEFENDER_ROLES = [
    ('handler_d', 'Handler defender'),
    ('huck_stopper', 'Huck stopper'),
    ('deep_d', 'Deep defender'),
    ('hassler', 'Hassler / mark'),
    ('fast_d', 'Fast defender'),
    ('aerial_d', 'Tall / aerial'),
]
# ...what makes one of their players dangerous...
THREAT_ROLES = [
    ('main_handler', 'Main handler'),
    ('hucker', 'Hucker'),
    ('deep_threat', 'Deep threat'),
    ('give_go', 'Give-and-go'),
    ('fast_cutter', 'Fast cutter'),
    ('under_cutter', 'Under cutter'),
    ('big_target', 'Big target / aerial'),
    ('break_thrower', 'Break thrower'),
]
# ...and which of our strengths answer each threat, best first
COUNTERS = {
    'main_handler': ['handler_d', 'hassler'],
    'hucker': ['huck_stopper', 'hassler'],
    'deep_threat': ['deep_d', 'aerial_d', 'fast_d'],
    'give_go': ['handler_d', 'fast_d'],
    'fast_cutter': ['fast_d', 'deep_d'],
    'under_cutter': ['fast_d', 'handler_d'],
    'big_target': ['aerial_d', 'deep_d'],
    'break_thrower': ['hassler', 'handler_d'],
}
# When a player has no threat types yet, their position says roughly what they do
POSITION_THREATS = {'handler': ['main_handler'], 'cutter': ['fast_cutter', 'deep_threat'],
                    'hybrid': ['give_go']}
ROLE_LABELS = dict(DEFENDER_ROLES + THREAT_ROLES)

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
    # What makes them dangerous (keys of THREAT_ROLES), comma-separated
    threat_roles = db.Column(db.String(255), nullable=True)
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
    def label(self):
        """'#10 Jamie', or just '#10' when that's all we know."""
        if self.jersey_number and self.name not in (f'#{self.jersey_number}', self.jersey_number):
            return f'#{self.jersey_number} {self.name}'
        return self.name if not self.jersey_number else f'#{self.jersey_number}'

    @property
    def threat_role_list(self):
        return _tag_list(self.threat_roles)

    @property
    def on_matchup_board(self):
        """Worth a matchup: flagged, typed, highly rated or already given a marker."""
        return bool(self.is_key_threat or self.threat_roles or self.matched_player_id
                    or self.threat_level in ('elite', 'high'))

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


def _gender(value):
    return value if value in ('male', 'female') else None


def defender_gender(player):
    return _gender(player.gender_match or player.gender)


def threats_of(opponent):
    """Their threat types, or what their position suggests when none are set."""
    return opponent.threat_role_list or POSITION_THREATS.get(opponent.position, [])


def fit_score(threats, defender_roles):
    """How well a defender's strengths answer these threats (first-listed answer counts double)."""
    ours = set(defender_roles)
    return sum(2 if COUNTERS[t][0] in ours else 1 if ours & set(COUNTERS[t][1:]) else 0
               for t in threats if t in COUNTERS)


def defender_label(player, with_roles=True):
    """'#12 Sam · Fast defender, Deep defender'."""
    label = f'#{player.jersey_number} {player.name}' if player.jersey_number is not None else player.name
    roles = [ROLE_LABELS.get(r, r) for r in _tag_list(player.defensive_roles)]
    return f'{label} · {", ".join(roles)}' if with_roles and roles else label


def rank_defenders(opponent, defenders):
    """(good fits best first, everyone else): who of ours suits marking them."""
    threats = threats_of(opponent)
    scored = [(fit_score(threats, _tag_list(d.defensive_roles)), d) for d in defenders if can_mark(opponent, d)]
    good = [d for score, d in sorted(scored, key=lambda x: -x[0]) if score > 0]
    return good, [d for d in defenders if d not in good]


def matchup_reasons(opponent, defender):
    """[(their threat label, our strength label)] that make this a good pairing."""
    threats = threats_of(opponent)
    ours = set(_tag_list(defender.defensive_roles))
    reasons = []
    for threat in threats:
        for role in COUNTERS.get(threat, []):
            if role in ours:
                reasons.append((ROLE_LABELS[threat], ROLE_LABELS[role]))
                break
    return reasons


def can_mark(opponent, defender):
    """In mixed, players mark someone of their own gender match (when both are known)."""
    theirs, ours = _gender(opponent.gender), defender_gender(defender)
    return not (theirs and ours and theirs != ours)


def suggest_matchups(opponents, defenders):
    """{opponent id: (defender, reasons)} for the board's players that have no marker yet.

    Most dangerous first, each takes the free defender whose strengths answer
    the most of their threats (the first-listed answer counts double). Each of
    our players is suggested once, and nobody already marking someone is used.
    """
    taken = {o.matched_player_id for o in opponents if o.matched_player_id}
    free = [d for d in defenders if d.id not in taken]
    suggestions = {}
    for opponent in sorted((o for o in opponents if o.on_matchup_board and not o.matched_player_id),
                           key=lambda o: o.sort_key):
        threats = threats_of(opponent)
        best, best_score = None, 0
        for defender in free:
            if not can_mark(opponent, defender):
                continue
            ours = set(_tag_list(defender.defensive_roles))
            score = fit_score(threats, ours)
            # Between equals, keep the more versatile defenders for later threats
            if score > best_score or (score == best_score and score and best
                                      and len(ours) < len(_tag_list(best.defensive_roles))):
                best, best_score = defender, score
        if best:
            suggestions[opponent.id] = (best, matchup_reasons(opponent, best))
            free.remove(best)
    return suggestions
