from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SelectMultipleField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Optional, URL, Length, ValidationError
from app.models.game import Game
from app.models.player import Player
from app.models.point import Point
from app.models.clip import ClipTag
from app.utils.clip_video import check_link, format_timestamp, link_start_seconds, parse_timestamp
from app.utils.team_filter import get_current_team_id
from flask_login import current_user

# Categories a clip tag can belong to
CLIP_TAG_CATEGORIES = [
    'Video Type',
    'Game Context',
    'Training Type',
    'Skill Focus',
    'Strategic Focus',
    'Player Development',
    'Analysis',
]

VIDEO_SOURCES = [('youtube', 'YouTube'), ('veo', 'Veo')]


class TimestampField(StringField):
    """A time in the video, typed as 90, 1:30 or 1:02:03; data is seconds."""

    def _value(self):
        if self.raw_data:
            return self.raw_data[0]
        return format_timestamp(self.data)

    def process_formdata(self, valuelist):
        self.data = None
        text = valuelist[0].strip() if valuelist else ''
        if text:
            try:
                self.data = parse_timestamp(text)
            except ValueError:
                raise ValueError('Use m:ss or h:mm:ss, e.g. 1:30')


def _team_id():
    return get_current_team_id() if current_user.is_authenticated else None


def game_choices(team_id, blank):
    """The team's games, newest first, after a blank choice."""
    choices = [(0, blank)]
    if team_id:
        choices += [
            (g.id, f"vs {g.opponent} ({g.date.strftime('%Y-%m-%d') if g.date else 'No date'})")
            for g in Game.query.filter_by(team_organization_id=team_id).order_by(Game.date.desc()).all()
        ]
    return choices


def player_choices(team_id):
    """The team's active players."""
    if not team_id:
        return []
    return [(p.id, f"{p.name} (#{p.jersey_number})")
            for p in Player.query.filter_by(team_organization_id=team_id, active=True)
                                 .order_by(Player.name).all()]


def tag_choices(team_id, prefix_category=False):
    """The team's active tags as a tree, grouped by category.

    By default each category gets a disabled "─── Category ───" header row;
    with prefix_category every tag is labelled "[Category] name" instead.
    """
    if not team_id:
        return []
    tags = ClipTag.query.filter_by(
        team_organization_id=team_id,
        is_active=True
    ).order_by(ClipTag.category, ClipTag.name).all()

    categories = {}
    for tag in tags:
        categories.setdefault(tag.category or 'Other', []).append(tag)

    choices = []

    def add(tag, category, level):
        label = f"{'  ' * level}↳ {tag.name}" if level else tag.name
        choices.append((tag.id, f"[{category}] {label}" if prefix_category else label))
        for child in tag.children.filter_by(is_active=True).order_by(ClipTag.name).all():
            add(child, category, level + 1)

    for category in sorted(categories):
        if not prefix_category:
            choices.append((-1, f"─── {category} ───"))
        for tag in categories[category]:
            if tag.parent_tag_id is None:
                add(tag, category, 0)
    return choices


class ClipForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    game_id = SelectField('Game', coerce=int, validators=[Optional()])
    point_id = SelectField('Point', coerce=int, validators=[Optional()])
    video_source = SelectField('Video Source',
        choices=VIDEO_SOURCES,
        default='youtube',
        validators=[DataRequired()]
    )
    youtube_link = StringField('Video Link', validators=[DataRequired(), URL()])
    start_time = TimestampField('Start Time')
    end_time = TimestampField('End Time')
    description = TextAreaField('Description', validators=[Optional()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
    players = SelectMultipleField('Players', coerce=int, validators=[Optional()])
    is_featured = BooleanField('Featured Clip')
    submit = SubmitField('Save Clip')

    def __init__(self, *args, **kwargs):
        super(ClipForm, self).__init__(*args, **kwargs)
        team_id = _team_id()

        self.game_id.choices = game_choices(team_id, 'Select Game')

        # The page refills the point list when the game changes; the server has
        # to know the chosen game's points too or a picked point won't validate.
        self.point_id.choices = [(0, 'Select Point')]
        if team_id and self.game_id.data:
            self.point_id.choices += [
                (p.id, f"Point {p.point_number}")
                for p in Point.query.join(Game, Game.id == Point.game_id).filter(
                    Point.game_id == self.game_id.data,
                    Game.team_organization_id == team_id
                ).order_by(Point.point_number).all()
            ]

        self.tags.choices = tag_choices(team_id)
        self.players.choices = player_choices(team_id)

    def validate_youtube_link(self, field):
        error = check_link(self.video_source.data, field.data)['error']
        if error:
            raise ValidationError(error)

    def validate_start_time(self, field):
        # A YouTube link shared "at current time" carries t=…; use it as the start
        if field.data is None and self.video_source.data == 'youtube':
            field.data = link_start_seconds(self.youtube_link.data)

    def validate_end_time(self, field):
        if field.data is not None and self.start_time.data is not None and field.data <= self.start_time.data:
            raise ValidationError('The end must be after the start.')


class ClipTagForm(FlaskForm):
    name = StringField('Tag Name', validators=[DataRequired(), Length(max=100)])
    category = SelectField('Category',
        choices=[('', 'Select Category')] + [(c, c) for c in CLIP_TAG_CATEGORIES],
        validators=[Optional()]
    )
    parent_tag_id = SelectField('Parent Tag (Optional)', coerce=int, validators=[Optional()])
    color = StringField('Color (Hex)', validators=[Optional(), Length(max=7)], default='#3F51B5')
    description = TextAreaField('Description', validators=[Optional()])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Tag')

    def __init__(self, *args, **kwargs):
        super(ClipTagForm, self).__init__(*args, **kwargs)
        team_id = _team_id()

        self.parent_tag_id.choices = [(0, 'None (Root Tag)')]
        if team_id:
            self.parent_tag_id.choices += [
                (t.id, t.full_path) for t in ClipTag.query.filter_by(
                    team_organization_id=team_id,
                    is_active=True
                ).order_by(ClipTag.category, ClipTag.name).all()
            ]


class ClipFilterForm(FlaskForm):
    game_id = SelectField('Game', coerce=int, validators=[Optional()])
    tags = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
    tag_category = SelectField('Tag Category',
        choices=[('', 'All Categories')] + [(c, c) for c in CLIP_TAG_CATEGORIES],
        validators=[Optional()]
    )
    player_id = SelectField('Player', coerce=int, validators=[Optional()])
    video_source = SelectField('Video Source',
        choices=[('', 'All Sources')] + VIDEO_SOURCES,
        validators=[Optional()]
    )
    is_featured = SelectField('Featured Only',
        choices=[
            ('', 'All Clips'),
            ('1', 'Featured Only')
        ],
        validators=[Optional()]
    )
    sort_by = SelectField('Sort By',
        choices=[
            ('created_desc', 'Newest First'),
            ('created_asc', 'Oldest First'),
            ('title_asc', 'Title (A-Z)'),
            ('views_desc', 'Most Viewed'),
            ('annotations_desc', 'Most Annotated')
        ],
        default='created_desc',
        validators=[Optional()]
    )
    submit = SubmitField('Filter')

    def __init__(self, *args, **kwargs):
        super(ClipFilterForm, self).__init__(*args, **kwargs)
        team_id = _team_id()

        self.game_id.choices = game_choices(team_id, 'All Games')
        self.tags.choices = tag_choices(team_id, prefix_category=True)
        self.player_id.choices = [(0, 'All Players')] + player_choices(team_id)


class PlaylistForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=120)])
    description = TextAreaField('What is it for?', validators=[Optional()])
    submit = SubmitField('Save Playlist')
