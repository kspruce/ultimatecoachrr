from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, Field, SelectField, SelectMultipleField,
                     StringField, SubmitField, TextAreaField)
from wtforms.validators import DataRequired, Length, Optional, URL, ValidationError
from wtforms.widgets import CheckboxInput, ListWidget, TextInput

from app.models.game import Game
from app.models.player import Player
from app.models.scouting import (DEFENSE_TAGS, OFFENSE_TAGS, POSITIONS, extract_youtube_id, format_time,
                                 parse_moments, parse_time)
from app.models.tournament import Tournament
from app.utils.team_filter import get_current_team_id

RATING_CHOICES = [('', 'Not rated'), ('1', '1 - Poor'), ('2', '2 - Below Average'), ('3', '3 - Average'),
                  ('4', '4 - Good'), ('5', '5 - Excellent')]


def rating_field(label):
    return SelectField(label, choices=RATING_CHOICES, validators=[Optional()],
                       coerce=lambda x: int(x) if x not in (None, '') else None)


class ModelForm(FlaskForm):
    """populate_obj that leaves the submit button and CSRF token off the model."""

    def populate_obj(self, obj):
        for name, field in self._fields.items():
            if name not in ('submit', 'csrf_token'):
                field.populate_obj(obj, name)


class TimeField(Field):
    """Seconds, typed as '90', '1:30' or '1:01:30'."""
    widget = TextInput()

    def _value(self):
        if self.raw_data:
            return self.raw_data[0]
        return format_time(self.data)

    def process_formdata(self, valuelist):
        self.data = None
        if valuelist and valuelist[0].strip():
            try:
                self.data = parse_time(valuelist[0])
            except ValueError:
                raise ValueError('Use minutes:seconds, e.g. 1:30')


class CheckboxListField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class TagField(CheckboxListField):
    """Stored as a comma-separated string of keys."""

    def process_data(self, value):
        if isinstance(value, str):
            value = [v for v in value.split(',') if v]
        super().process_data(value)

    def populate_obj(self, obj, name):
        setattr(obj, name, ','.join(self.data or []) or None)


def game_label(game):
    return f"vs {game.opponent} ({game.date.strftime('%Y-%m-%d') if game.date else 'No date'})"


class ScoutingReportForm(ModelForm):
    team_name = StringField('Opponent', validators=[DataRequired(), Length(max=100)])
    date = DateField('Date', format='%Y-%m-%d', validators=[Optional()])
    tournament_id = SelectField('Tournament', coerce=int, validators=[Optional()])
    game_id = SelectField('Game', coerce=int, validators=[Optional()])
    offense_tags = TagField('Offence looks', choices=OFFENSE_TAGS, validators=[Optional()])
    defense_tags = TagField('Defence looks', choices=DEFENSE_TAGS, validators=[Optional()])
    offense_strategy = TextAreaField('Offensive Strategy', validators=[Optional()])
    defense_strategy = TextAreaField('Defensive Strategy', validators=[Optional()])
    strengths = TextAreaField('Strengths', validators=[Optional()])
    weaknesses = TextAreaField('Weaknesses', validators=[Optional()])
    notes = TextAreaField('Additional Notes', validators=[Optional()])
    game_plan = TextAreaField('How we beat them', validators=[Optional()])
    o_line_plan = TextAreaField('O-line plan', validators=[Optional()])
    d_line_plan = TextAreaField('D-line plan', validators=[Optional()])
    submit = SubmitField('Save Scouting Report')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Tournaments and games from the current team only
        team_id = get_current_team_id()
        self.tournaments = (Tournament.query.filter_by(team_organization_id=team_id)
                            .order_by(Tournament.start_date.desc()).all())
        self.games = (Game.query.filter_by(team_organization_id=team_id)
                      .order_by(Game.date.desc()).all())
        self.tournament_id.choices = [(0, 'None')] + [(t.id, t.name) for t in self.tournaments]
        self.game_id.choices = [(0, 'None')] + [(g.id, game_label(g)) for g in self.games]
        if self.tournament_id.data is None:
            self.tournament_id.data = 0
        if self.game_id.data is None:
            self.game_id.data = 0

    def populate_obj(self, obj):
        super().populate_obj(obj)
        obj.tournament_id = self.tournament_id.data or None
        obj.game_id = self.game_id.data or None


class OpponentPlayerForm(ModelForm):
    name = StringField('Player Name', validators=[DataRequired(), Length(max=100)])
    jersey_number = StringField('Jersey Number', validators=[Optional(), Length(max=10)])
    position = SelectField('Position', choices=[('', 'Select...')] + [(p, p.title()) for p in POSITIONS],
                           validators=[Optional()])
    height = StringField('Height', validators=[Optional(), Length(max=20)])
    gender = SelectField('Gender', choices=[
        ('', 'Select...'),
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], validators=[Optional()])
    throwing_ability = rating_field('Throwing')
    cutting_ability = rating_field('Cutting')
    defensive_ability = rating_field('Defence')
    athletic_ability = rating_field('Athleticism')
    is_key_threat = BooleanField('Key threat')
    matched_player_id = SelectField('Marked by', coerce=int, validators=[Optional()])
    preferred_throws = StringField('Preferred Throws', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Player')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ours = (Player.query.filter_by(team_organization_id=get_current_team_id(), active=True)
                .order_by(Player.name).all())
        self.matched_player_id.choices = [(0, 'Nobody yet')] + [(p.id, p.name) for p in ours]
        if self.matched_player_id.data is None:
            self.matched_player_id.data = 0

    def populate_obj(self, obj):
        super().populate_obj(obj)
        obj.matched_player_id = self.matched_player_id.data or None
        obj.position = self.position.data or None
        obj.gender = self.gender.data or None


class BulkPlayersForm(FlaskForm):
    roster = TextAreaField('Roster', validators=[DataRequired()])
    submit = SubmitField('Add Players')


class ScoutingClipForm(ModelForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=100)])
    youtube_link = StringField('YouTube Link', validators=[DataRequired(), URL(), Length(max=200)])
    start_time = TimeField('Start', validators=[Optional()])
    end_time = TimeField('End', validators=[Optional()])
    clip_type = SelectField('Clip Type', choices=[
        ('', 'Select...'),
        ('offense', 'Offense'),
        ('defense', 'Defense'),
        ('set_play', 'Set Play'),
        ('pull', 'Pull'),
        ('other', 'Other')
    ], validators=[Optional()])
    opponent_player_id = SelectField('Player', coerce=int, validators=[Optional()])
    moments = TextAreaField('More moments in this video', validators=[Optional()])
    description = TextAreaField('Description', validators=[Optional()])
    submit = SubmitField('Save Clip')

    def __init__(self, *args, report=None, **kwargs):
        super().__init__(*args, **kwargs)
        players = sorted(report.players.all(), key=lambda p: p.name.lower()) if report else []
        self.opponent_player_id.choices = [(0, 'Whole team')] + [
            (p.id, f'#{p.jersey_number} {p.name}' if p.jersey_number else p.name) for p in players]
        if self.opponent_player_id.data is None:
            self.opponent_player_id.data = 0

    def validate_youtube_link(self, field):
        if not extract_youtube_id(field.data):
            raise ValidationError('That is not a YouTube video link.')

    def validate_end_time(self, field):
        if field.data is not None and self.start_time.data is not None and field.data <= self.start_time.data:
            raise ValidationError('The end must be after the start.')

    def validate_moments(self, field):
        try:
            parse_moments(field.data)
        except ValueError as e:
            raise ValidationError(f'Could not read "{e}". Start each line with a time, e.g. 1:23 or 1:23-1:40.')

    def populate_obj(self, obj):
        super().populate_obj(obj)
        obj.youtube_link = f'https://www.youtube.com/watch?v={extract_youtube_id(self.youtube_link.data)}'
        obj.opponent_player_id = self.opponent_player_id.data or None
        obj.clip_type = self.clip_type.data or None
        obj.moments = (self.moments.data or '').strip() or None


class ScoutingFilterForm(FlaskForm):
    class Meta:
        csrf = False

    q = StringField('Search', validators=[Optional()])
    tournament_id = SelectField('Tournament', coerce=int, validators=[Optional()])
    tag = SelectField('Look', choices=[('', 'Any look')] + OFFENSE_TAGS + DEFENSE_TAGS, validators=[Optional()])
    date_from = DateField('From', format='%Y-%m-%d', validators=[Optional()])
    date_to = DateField('To', format='%Y-%m-%d', validators=[Optional()])
    group = SelectField('Show', choices=[('', 'Newest first'), ('opponent', 'By opponent'), ('tournament', 'By tournament')],
                        validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate tournament choices from the current team only
        self.tournament_id.choices = [(0, 'All tournaments')] + [
            (t.id, t.name) for t in Tournament.query.filter_by(team_organization_id=get_current_team_id())
            .order_by(Tournament.start_date.desc()).all()
        ]
