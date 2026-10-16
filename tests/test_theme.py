"""Team colours: the helpers that keep any colour pair readable, the colours
page, and the colours reaching every page through base.html."""
from app import db
from app.models.team_settings import TeamSettings
from app.models.user import User
from app.utils import theme
from tests import stats_data


def test_normalize_hex():
    assert theme.normalize_hex('#6e1f2f') == '#6E1F2F'
    assert theme.normalize_hex('abc') == '#AABBCC'
    assert theme.normalize_hex(' #1D3461 ') == '#1D3461'
    assert theme.normalize_hex('red') is None
    assert theme.normalize_hex('#12345') is None
    assert theme.normalize_hex('') is None
    assert theme.normalize_hex(None) is None


def test_text_on_picks_the_readable_colour():
    assert theme.text_on('#1D3461') == theme.LIGHT_TEXT   # navy -> cream text
    assert theme.text_on('#E9C46A') == theme.DARK_TEXT    # mustard -> dark text
    assert theme.text_on('#FFFFFF') == theme.DARK_TEXT


def test_palette_defaults_and_readable_links():
    palette = theme.team_palette(None)
    assert palette['primary'] == theme.DEFAULT_PRIMARY
    assert palette['accent'] == theme.DEFAULT_ACCENT
    # A light primary still gives links that read on the page backgrounds
    light = theme.team_palette(TeamSettings(primary_color='#F2E8CF', accent_color='#9E2A2B'))
    assert theme.contrast_ratio(light['ink_light'], theme.LIGHT_PAPER) >= 4.5
    assert theme.contrast_ratio(light['ink_dark'], theme.DARK_CARD) >= 4.5
    css = theme.theme_css(light)
    assert '--club:#F2E8CF' in css and '--on-club:#1E1A18' in css


def test_presets_are_valid_colours():
    for name, primary, accent in theme.PRESETS:
        assert theme.normalize_hex(primary) == primary, name
        assert theme.normalize_hex(accent) == accent, name


def _coach_client(app, role='coach'):
    team = stats_data.build_team()
    user = User(username='coachy', email='coachy@example.com', role=role,
                is_admin_flag=role == 'admin', team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.commit()
    return team, stats_data.Client(app, user.id, team.id)


def test_coach_saves_team_colours_and_every_page_uses_them(app):
    team, client = _coach_client(app)
    team_id = team.id
    assert client.get('/team/settings/colours').status_code == 200

    r = client.post('/team/settings/colours', data={
        'action': 'save', 'primary_color': '1d3461', 'accent_color': '#e8833a'})
    assert r.status_code == 302
    with app.app_context():
        settings = TeamSettings.query.filter_by(team_id=team_id).one()
        assert (settings.primary_color, settings.accent_color) == ('#1D3461', '#E8833A')
        assert settings.show_kit_stripe is False  # checkbox left unticked

    page = client.get('/').get_data(as_text=True)
    assert '--club:#1D3461' in page and '--accent:#E8833A' in page


def test_bad_colours_are_rejected_and_reset_restores_defaults(app):
    team, client = _coach_client(app)
    team_id = team.id
    client.post('/team/settings/colours', data={
        'action': 'save', 'primary_color': '#1D3461', 'accent_color': '#E8833A', 'show_kit_stripe': 'on'})
    client.post('/team/settings/colours', data={
        'action': 'save', 'primary_color': 'javascript:alert(1)', 'accent_color': '#E8833A'})
    with app.app_context():
        assert TeamSettings.query.filter_by(team_id=team_id).one().primary_color == '#1D3461'

    client.post('/team/settings/colours', data={'action': 'reset'})
    with app.app_context():
        settings = TeamSettings.query.filter_by(team_id=team_id).one()
        assert settings.primary_color is None and settings.accent_color is None
    assert f'--club:{theme.DEFAULT_PRIMARY}' in client.get('/').get_data(as_text=True)


def test_players_cannot_change_colours(app):
    team, client = _coach_client(app, role='player')
    team_id = team.id
    client.post('/team/settings/colours', data={
        'action': 'save', 'primary_color': '#000000', 'accent_color': '#FFFFFF'})
    with app.app_context():
        settings = TeamSettings.query.filter_by(team_id=team_id).first()
        assert settings is None or settings.primary_color is None
