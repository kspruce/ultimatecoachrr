"""Coach feedback: notes stay with the coaches until they're shared, the
player then reads them under My Feedback (and on their profile), and notes
can be written from a game or a clip. Old notes-box entries come across."""
import importlib.util
import os
from datetime import datetime

import pytest

from app import db
from app.models.clip import Clip
from app.models.feedback import PlayerFeedback
from app.models.game import Game
from app.models.onboarding import UserOnboarding
from app.models.session import SessionPlan
from app.models.user import User
from tests import stats_data


def make_user(team, username, role, player=None):
    user = User(username=username, email=f'{username}@example.com', role=role,
                is_admin_flag=(role == 'admin'), team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOnboarding(user_id=user.id, welcomed_role=role, completed_steps=[]))
    if player is not None:
        player.user_id = user.id
    return user


@pytest.fixture
def club(app):
    team = stats_data.build_team()
    other = stats_data.build_team('Herd 2028', 'herd-2028')
    ann, ben = stats_data.build_players(team, 2)
    stranger = stats_data.build_players(other, 1)[0]
    coach = make_user(team, 'coach', 'coach')
    ann_user = make_user(team, 'ann', 'player', ann)
    ben_user = make_user(team, 'ben', 'player', ben)
    other_coach = make_user(other, 'othercoach', 'coach')
    game = Game(opponent='Ka-Pow', team_organization_id=team.id)
    other_game = Game(opponent='Secret opponent', team_organization_id=other.id)
    session = SessionPlan(title='Tuesday training', team_organization_id=team.id)
    db.session.add_all([game, other_game, session])
    db.session.flush()
    clip = Clip(title='Huck from the brick', game_id=game.id, team_organization_id=team.id)
    db.session.add(clip)
    db.session.commit()
    return {'team': team.id, 'other': other.id, 'ann': ann.id, 'ben': ben.id, 'stranger': stranger.id,
            'coach': coach.id, 'ann_user': ann_user.id, 'ben_user': ben_user.id, 'other_coach': other_coach.id,
            'game': game.id, 'other_game': other_game.id, 'session': session.id, 'clip': clip.id}


def login(app, club, who, team='team'):
    return stats_data.Client(app, club[who], club[team])


def text(response):
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def add_note(c, club, content, **form):
    return c.post(f"/players/{club['ann']}/feedback/add", data={'content': content, **form})


def test_notes_stay_with_coaches_until_shared(app, club):
    coach = login(app, club, 'coach')
    assert add_note(coach, club, 'Lazy on the mark').status_code == 302
    assert add_note(coach, club, 'Great hucks today', shared='1', context_tag='Drill').status_code == 302

    ann = login(app, club, 'ann_user')
    mine = text(ann.get('/feedback/mine'))
    assert 'Great hucks today' in mine and 'Lazy on the mark' not in mine
    profile = text(ann.get(f"/team/player/{club['ann']}"))
    assert 'Great hucks today' in profile and 'Lazy on the mark' not in profile
    # Nobody else's notes, and coaches' pages stay closed
    assert 'Great hucks today' not in text(login(app, club, 'ben_user').get('/feedback/mine'))
    assert ann.get(f"/players/{club['ann']}/feedback").status_code == 403

    # The coach sees both, and which one the player can read
    page = text(coach.get(f"/players/{club['ann']}/feedback"))
    assert 'Lazy on the mark' in page and 'Great hucks today' in page
    assert 'Coaches only' in page and 'Shared' in page

    # Sharing the private one later
    private = PlayerFeedback.query.filter_by(content='Lazy on the mark').one()
    coach.post(f'/feedback/{private.id}/share')
    assert 'Lazy on the mark' in text(ann.get('/feedback/mine'))


def test_new_notes_are_counted_until_the_player_reads_them(app, club):
    coach = login(app, club, 'coach')
    add_note(coach, club, 'Nice cut', shared='1')
    add_note(coach, club, 'Keep it up', shared='1')

    ann = login(app, club, 'ann_user')
    home = text(ann.get('/'))
    assert '2 new notes from your coaches' in home
    mine = text(ann.get('/feedback/mine'))
    assert '2 new' in mine
    assert PlayerFeedback.query.filter(PlayerFeedback.seen_at.is_(None)).count() == 0
    assert 'new notes from your coaches' not in text(ann.get('/'))
    assert 'Shared · seen' in text(coach.get(f"/players/{club['ann']}/feedback"))


def test_notes_from_a_game_and_a_clip(app, club):
    coach = login(app, club, 'coach')
    game_page = text(coach.get(f"/games/{club['game']}"))
    assert 'Player feedback' in game_page
    add_note(coach, club, 'Good D on their handler', game_id=club['game'], context_tag='In-game', shared='1',
             next=f"/games/{club['game']}#player-feedback")
    note = PlayerFeedback.query.one()
    assert note.game_id == club['game'] and note.context_tag == 'In-game' and note.coach_id == club['coach']
    assert 'Good D on their handler' in text(coach.get(f"/games/{club['game']}"))

    clip_page = text(coach.get(f"/clips/{club['clip']}"))
    assert 'tab-feedback' in clip_page
    add_note(coach, club, 'Watch your footwork here', clip_id=club['clip'], shared='1')
    assert PlayerFeedback.query.filter_by(clip_id=club['clip']).count() == 1

    mine = text(login(app, club, 'ann_user').get('/feedback/mine'))
    assert 'vs Ka-Pow' in mine and 'Huck from the brick' in mine
    # Players don't get the coaches' forms
    ann = login(app, club, 'ann_user')
    assert 'tab-feedback' not in text(ann.get(f"/clips/{club['clip']}"))
    assert 'Player feedback' not in text(ann.get(f"/games/{club['game']}"))


def test_quick_capture_can_share(app, club):
    coach = login(app, club, 'coach')
    r = coach.post(f"/sessions/{club['session']}/feedback/save",
                   json={'player_id': club['ann'], 'content': 'Sharp today', 'context_tag': 'Drill', 'shared': True})
    assert r.get_json()['success']
    assert PlayerFeedback.query.one().shared
    assert 'Sharp today' in text(login(app, club, 'ann_user').get('/feedback/mine'))


def test_other_teams_cant_reach_your_feedback(app, club):
    coach = login(app, club, 'coach')
    add_note(coach, club, 'Ours')
    note = PlayerFeedback.query.one()

    outsider = login(app, club, 'other_coach', 'other')
    assert outsider.post(f"/players/{club['ann']}/feedback/add", data={'content': 'Hi'}).status_code == 404
    assert outsider.post(f'/feedback/{note.id}/share').status_code == 404
    assert outsider.post(f'/feedback/{note.id}/delete').status_code == 404
    assert not PlayerFeedback.query.get(note.id).shared

    # Another team's game id is dropped, and so is a redirect off the site
    r = add_note(coach, club, 'Linked?', game_id=club['other_game'], next='https://evil.example/')
    assert r.headers['Location'].endswith(f"/players/{club['ann']}/feedback")
    assert PlayerFeedback.query.filter_by(content='Linked?').one().game_id is None


def test_old_notes_box_entries_come_across():
    path = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions',
                        'e9a1c3d5f7b0_feedback_shared_with_players.py')
    spec = importlib.util.spec_from_file_location('feedback_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    entries = migration.notes_box_entries('[16 Mar 2026]\nGreat marking\n---\nWork on your flick\n---\n\n')
    assert entries == [(datetime(2026, 3, 16), 'Great marking'), (None, 'Work on your flick')]
    assert migration.notes_box_entries(None) == []


def test_notes_outlive_their_game_and_clip(app, club):
    coach = login(app, club, 'coach')
    add_note(coach, club, 'About the clip', clip_id=club['clip'], game_id=club['game'])
    assert coach.post(f"/games/delete/{club['game']}").status_code == 302
    assert Game.query.get(club['game']) is None
    db.session.expire_all()
    note = PlayerFeedback.query.one()
    if db.engine.dialect.name == 'postgresql':  # SQLite doesn't enforce the keys
        assert note.game_id is None and note.clip_id is None
    assert 'About the clip' in text(coach.get(f"/players/{club['ann']}/feedback"))
