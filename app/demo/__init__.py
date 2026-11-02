"""The demo team: a made-up club with a season's worth of everything, and a
shared read-only login anyone can use to look round (User.is_demo).

`flask seed-demo` builds it; run it again with --reset to rebuild it, with
the dates moved on so it always looks like a team mid-season. Games are
recorded through the stat-taker's own endpoints, so the stats pages show
what a real team's would. Plays and drill diagrams come from diagrams.json
(see build_diagrams.py)."""
import base64
import hashlib
import json
import os
import random
import re
import secrets
from datetime import date, datetime, time, timedelta

from flask import url_for

from app import db

DEMO_SLUG = 'demo'
DEMO_TEAM_NAME = 'Riverside Kites'
DEMO_USERNAME = 'demo'
DEMO_PASSWORD = 'demo'
OWNER_USERNAME = 'demo-head-coach'

DIAGRAMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'diagrams.json')

PLAYERS = [
    # name, number, gender, position
    ('Maya Okafor', 7, 'female', 'handler'), ('Tom Bradley', 12, 'male', 'handler'),
    ('Priya Nair', 3, 'female', 'cutter'), ('Sam Whitfield', 22, 'male', 'cutter'),
    ('Ellie Brooks', 9, 'female', 'hybrid'), ('Jonah Reyes', 4, 'male', 'handler'),
    ('Hana Sato', 18, 'female', 'cutter'), ('Callum Fraser', 31, 'male', 'cutter'),
    ('Grace Mensah', 11, 'female', 'handler'), ('Luis Ortega', 8, 'male', 'hybrid'),
    ('Freya Lindqvist', 15, 'female', 'cutter'), ('Dev Patel', 27, 'male', 'cutter'),
    ('Zoe Carter', 2, 'female', 'cutter'), ('Oscar Novak', 19, 'male', 'handler'),
    ('Aisha Rahman', 23, 'female', 'hybrid'), ('Ben Achterberg', 5, 'male', 'cutter'),
    ('Ruby Walsh', 14, 'female', 'cutter'), ('Kai Tanaka', 10, 'male', 'hybrid'),
]

DRILLS = [
    dict(key='box-drill', title='Box drill', focus_area='Throwing', skill_level='beginner',
         recommended_duration=15, min_players=8, equipment_needed='4 cones, 4 discs',
         description='Four lines on the corners of a 20 x 15 yard box. Throw to the next corner '
                     'and follow your throw. Switch direction every couple of minutes.',
         setup_instructions='Cones in a box, a line behind each cone, discs at two opposite corners.'),
    dict(key='under-deep-drill', title='Under–deep', focus_area='Cutting', skill_level='intermediate',
         recommended_duration=15, min_players=6, equipment_needed='2 cones, discs',
         description='Cut under, catch, give it back, then plant and go deep for the lead pass.',
         setup_instructions='Thrower line on the centre cone, cutter line 15 yards downfield and wide.'),
    dict(title='Three-person mark', focus_area='Throwing', skill_level='beginner', recommended_duration=10,
         min_players=3, equipment_needed='1 disc per three',
         description='Thrower, marker and receiver. The marker forces one way; the thrower pivots '
                     'and breaks the mark. Rotate every five throws.'),
    dict(title='Endzone drill', focus_area='Endzone offence', skill_level='intermediate',
         recommended_duration=20, min_players=10, equipment_needed='cones, discs',
         description='Disc on the brick, stack in the endzone. Run the split and the isolation '
                     'against live defence; score in under 5 throws.'),
    dict(title='Cup zone walk-through', focus_area='Zone defence', skill_level='intermediate',
         recommended_duration=15, min_players=14, equipment_needed='discs, bibs',
         description='Offence swings the disc slowly; the cup, wings and deep move together. Speed it up '
                     'once everyone is in the right place.'),
    dict(title='Hex warm-up', focus_area='Warm-up', skill_level='beginner', recommended_duration=10,
         min_players=6, description='Six players in a hexagon passing around and across, moving to '
                                    'space after each throw.'),
    dict(title='Mark and pivot ladder', focus_area='Throwing', skill_level='beginner',
         recommended_duration=10, min_players=2,
         description='Pairs, 10 yards apart. Five forehands, five backhands, five around-breaks, '
                     'five inside-breaks. Step out further each round.'),
    dict(title='7v7 scrimmage with calls', focus_area='Game play', skill_level='advanced',
         recommended_duration=30, min_players=14,
         description='Games to 5. Each O-line point the handler calls a play from the playbook.'),
]

PLAYS = [
    dict(key='ho-centre', name='Ho stack: centre cut', type='offense', call='Lanes', signal='Flat hand',
         is_core=True, situations='pull,hold,vs_person',
         description='Our default offence. Clear the middle, hit the under, then go to space deep.',
         notes='Inside cutters go first. If the under is not there, swing it to H2 or H3 and reset.'),
    dict(key='vert-under-deep', name='Vert stack: open-side under', type='offense', call='Stack',
         signal='Fist', is_core=True, situations='hold,vs_person,upwind',
         description='Front of the stack takes the open-side under; back of the stack times the deep '
                     'cut off the catch.'),
    dict(key='endzone-split', name='Endzone split', type='offense', call='Split', signal='Two fingers',
         situations='endzone,timeout', description='From the brick: front and back of the stack go to '
                                                   'opposite corners. Hit whichever is open.'),
    dict(key='cup-zone', name='Cup zone', type='defense', call='Cup', signal='Cupped hands',
         is_core=True, situations='upwind,break,vs_zone',
         description='Three in the cup, two wings, a mid-mid and a deep-deep. Make them throw 20 passes '
                     'into the wind.'),
]

OPPONENTS = ['Harbour Hawks', 'Northfield Flyers', 'Granite City', 'Lakeside Lightning',
             'Old Mill Ultimate', 'Coastal Breeze']


def demo_user():
    from app.models.user import User
    return User.query.filter_by(is_demo=True).order_by(User.id).first()


def demo_team():
    from app.models.team_organization import TeamOrganization
    return TeamOrganization.query.filter_by(slug=DEMO_SLUG).first()


def remove(app):
    """Delete the demo team and its accounts. Returns whether there was one."""
    from app.models.user import User
    from app.utils.team_data import delete_team_data

    team = demo_team()
    if team is None:
        return False
    delete_team_data(team.id)
    for username in (DEMO_USERNAME, OWNER_USERNAME):
        user = User.query.filter_by(username=username).first()
        if user is not None and not user.memberships:
            db.session.delete(user)
    db.session.commit()
    return True


def build(app, today=None, record_games=True):
    """Make the demo team. Returns it. Raises if it's already there."""
    if demo_team() is not None:
        raise ValueError('The demo team is already set up (use --reset to rebuild it).')
    today = today or date.today()
    with app.test_request_context():  # url_for for the diagram images
        team_id, owner_id, demo_id = _team_and_people(today)
        players = _players(team_id, today)
        drills = _drills(team_id, owner_id)
        plays = _plays(team_id, owner_id)
        _sessions(team_id, players, drills, plays, today)
        _theory(team_id, owner_id, plays)
        _fitness(team_id, owner_id, players, today)
        db.session.commit()
    tournaments = _tournaments(team_id, players, today)
    if record_games:
        _record_games(app, team_id, owner_id, players, tournaments, today)
    _scouting_and_feedback(team_id, owner_id, players, tournaments, today)
    db.session.commit()
    return demo_team()


# ── People ──────────────────────────────────────────────────────

def _team_and_people(today):
    from app.models.team_organization import TeamOrganization
    from app.models.team_settings import TeamSettings
    from app.models.user import User

    team = TeamOrganization(name=DEMO_TEAM_NAME, slug=DEMO_SLUG, division='mixed',
                            description='A made-up club to show what Ultimate Coach does. '
                                        'Look round as their coach: nothing you do here is saved.')
    db.session.add(team)
    db.session.flush()
    db.session.add(TeamSettings(team_id=team.id, primary_color='#0b5d7a', accent_color='#f2a541',
                                season_plan_enabled=False, leadership_handbook_enabled=False,
                                discord_enabled=False))

    owner = User.query.filter_by(username=OWNER_USERNAME).first()
    if owner is None:
        owner = User(username=OWNER_USERNAME, role='admin')
        db.session.add(owner)
    # Nobody signs in as the head coach: they're who wrote the demo content
    owner.set_password(secrets.token_urlsafe(32))
    owner.team_organization_id = None
    owner.join_team(team.id, 'admin')

    demo = User.query.filter_by(username=DEMO_USERNAME).first()
    if demo is None:
        demo = User(username=DEMO_USERNAME, role='coach')
        db.session.add(demo)
    demo.is_demo = True
    demo.set_password(DEMO_PASSWORD)
    demo.team_organization_id = None
    demo.join_team(team.id, 'coach')
    db.session.flush()
    return team.id, owner.id, demo.id


def _players(team_id, today):
    from app.models.player import Player

    players = []
    for i, (name, number, gender, position) in enumerate(PLAYERS):
        players.append(Player(
            name=name, jersey_number=number, gender=gender, position=position, active=True,
            line_preference='O-line' if i % 3 == 0 else ('D-line' if i % 3 == 1 else None),
            joined_team_date=today - timedelta(days=200 + 40 * (i % 5)), team_organization_id=team_id,
            short_term_goals='Get my backhand break to the open side' if i % 4 == 0 else None))
    db.session.add_all(players)
    db.session.flush()
    return players


# ── Drills, plays, sessions ─────────────────────────────────────

def _diagrams(owner, key, source):
    """The drawing `key` from diagrams.json, as the editor would have saved it."""
    from app.models.drill import DrillDiagram

    with open(DIAGRAMS) as f:
        drawing = json.load(f)[key]
    stages = drawing['editor']['stages']
    saved = []
    for i, image in enumerate(drawing['images']):
        png = base64.b64decode(image['png'])
        svg = image['svg']
        diagram = DrillDiagram(
            source=source, team_organization_id=owner.team_organization_id, order=1000 + i,
            step_label=stages[i]['name'] if len(stages) > 1 else None,
            caption=(stages[i]['notes'] or '')[:255] or None,
            image_data=image['png'], image_mime='image/png', image_hash=hashlib.sha256(png).hexdigest(),
            svg_data=svg, svg_hash=hashlib.sha256(svg.encode()).hexdigest(),
            editor_json=json.dumps(drawing['editor']) if i == 0 else json.dumps({'stage': i + 1}))
        owner.diagrams.append(diagram)
        saved.append(diagram)
    db.session.flush()
    for diagram in saved:
        diagram.image_url = url_for('session.drill_diagram_image', diagram_id=diagram.id,
                                    filename=f'{diagram.image_hash[:16]}.png')
        diagram.svg_url = url_for('session.drill_diagram_svg', diagram_id=diagram.id,
                                  filename=f'{diagram.svg_hash[:16]}.svg')


def _drills(team_id, owner_id):
    from app.models.drill import SavedDrill

    drills = {}
    for spec in DRILLS:
        spec = dict(spec)
        key = spec.pop('key', None)
        drill = SavedDrill(created_by=owner_id, team_organization_id=team_id, **spec)
        db.session.add(drill)
        db.session.flush()
        if key:
            _diagrams(drill, key, 'Drill editor')
        drills[drill.title] = drill
    return drills


def _plays(team_id, owner_id):
    from app.models.playbook import Play

    plays = {}
    for order, spec in enumerate(PLAYS, 1):
        spec = dict(spec)
        key = spec.pop('key')
        play = Play(status='active', sort_order=order, created_by=owner_id, team_organization_id=team_id,
                    **spec)
        db.session.add(play)
        db.session.flush()
        _diagrams(play, key, 'Play editor')
        plays[key] = play
    return plays


SESSION_TEMPLATES = [
    ('Throwing under pressure', 'Throwing', [
        ('warmup', 'Hex warm-up', 15), ('drill', 'Mark and pivot ladder', 15), ('drill', 'Three-person mark', 15),
        ('water', None, 5), ('drill', 'Box drill', 15), ('scrimmage', '7v7 scrimmage with calls', 25)]),
    ('Cutting and spacing', 'Offence', [
        ('warmup', 'Hex warm-up', 15), ('drill', 'Under–deep', 20), ('discussion', None, 10),
        ('drill', 'Endzone drill', 20), ('scrimmage', '7v7 scrimmage with calls', 25)]),
    ('Zone defence', 'Defence', [
        ('warmup', 'Hex warm-up', 15), ('drill', 'Cup zone walk-through', 20), ('water', None, 5),
        ('drill', 'Box drill', 15), ('scrimmage', '7v7 scrimmage with calls', 30)]),
]


def _sessions(team_id, players, drills, plays, today):
    from app.models.session import Attendance, SessionComponent, SessionPlan, SessionRSVP

    rng = random.Random(11)
    tuesday = today - timedelta(days=(today.weekday() - 1) % 7)
    for week in range(-6, 4):
        day = tuesday + timedelta(weeks=week)
        title, focus, parts = SESSION_TEMPLATES[(week + 6) % len(SESSION_TEMPLATES)]
        session = SessionPlan(
            title=title, date=day, start_time=time(19, 0), end_time=time(21, 0),
            location='Riverside Park, pitch 2', focus_area=focus, team_organization_id=team_id,
            session_type='invited_training',
            aim=f'{focus}: make it automatic under pressure before the next tournament.',
            notes='Bring light and dark tops. Floodlights on from 7.')
        db.session.add(session)
        db.session.flush()
        for order, (kind, drill_title, minutes) in enumerate(parts, 1):
            drill = drills.get(drill_title)
            component = SessionComponent(
                session_id=session.id, order=order, component_type=kind, duration_minutes=minutes,
                drill_id=drill.id if drill else None, team_organization_id=team_id,
                title=drill_title or dict(SessionComponent.COMPONENT_TYPE_CHOICES)[kind],
                focus_area=drill.focus_area if drill else None,
                coach_cue='Eyes up before you catch it.' if kind == 'drill' and order == 2 else None)
            db.session.add(component)
            if drill_title == 'Endzone drill':
                component.plays.append(plays['endzone-split'])
            if drill_title == 'Cup zone walk-through':
                component.plays.append(plays['cup-zone'])
        if day < today:
            for p in players:
                status = rng.choices(['present', 'present', 'present', 'late', 'absent'])[0]
                db.session.add(Attendance(session_id=session.id, player_id=p.id, status=status,
                                          team_organization_id=team_id))
        elif week <= 2:
            for p in players:
                if rng.random() < (0.8 if week <= 1 else 0.4):
                    status = rng.choices(['attending', 'attending', 'attending', 'maybe', 'not_attending'])[0]
                    db.session.add(SessionRSVP(session_id=session.id, player_id=p.id, status=status,
                                               team_organization_id=team_id))


# ── Theory and fitness ──────────────────────────────────────────

THEORY = [
    ('Offence', 'How we attack: our stacks, who goes when, and how we score.', [
        ('Ho stack basics', 'ho-centre',
         'The ho stack spreads the field: three handlers across the back, four cutters level across the '
         'field.\n\n**Inside cutters go first.** The middle two clear deep and come back under; the '
         'outside two stay wide so the lane stays open.\n\n{play}\n\n### What to watch\n\n'
         '- Cut into space, not towards the disc.\n- If you don\'t get it, clear back to your spot.'),
        ('Reading the force', None,
         'Before you cut, look at the mark. **Open side** is where the marker is letting them throw; '
         '**break side** is behind the mark.\n\n- Handlers: take what the force gives you, break when '
         'the mark is late.\n- Cutters: start on the break side, cut to the open side.'),
    ]),
    ('Defence', 'Our zones and how we mark.', [
        ('Cup zone', 'cup-zone',
         'Use the cup when it is windy or when we need a break. Three in the cup, two wings, a '
         'mid-mid and a deep-deep.\n\n{play}\n\n**The cup moves with the disc.** Don\'t chase: slide '
         'and close the gap.'),
    ]),
]


def _theory(team_id, owner_id, plays):
    from app.models.theory import TheorySection, TheoryTopic

    for order, (name, description, topics) in enumerate(THEORY, 1):
        section = TheorySection(name=name, slug=f'demo-{name.lower()}', description=description,
                                order=order, team_organization_id=team_id)
        db.session.add(section)
        db.session.flush()
        for t_order, (title, play_key, content) in enumerate(topics, 1):
            play = plays.get(play_key) if play_key else None
            content = content.replace('{play}', f'[[play:{play.id}]]' if play else '')
            topic = TheoryTopic(section_id=section.id, name=title, content=content, order=t_order,
                                published=True, created_by=owner_id, team_organization_id=team_id)
            if play:
                topic.plays.append(play)
            db.session.add(topic)


def _fitness(team_id, owner_id, players, today):
    from app.models.fitness import FitnessGoal, FitnessMetric, FitnessRecord

    rng = random.Random(5)
    sprint = FitnessMetric(name='40m sprint', unit='s', higher_is_better=False, team_organization_id=team_id,
                           description='From a standing start, best of two.')
    bronco = FitnessMetric(name='Bronco test', unit='s', higher_is_better=False, team_organization_id=team_id,
                           description='20-40-60 m shuttles, five times through.')
    jump = FitnessMetric(name='Vertical jump', unit='cm', higher_is_better=True, team_organization_id=team_id)
    db.session.add_all([sprint, bronco, jump])
    db.session.flush()
    for p in players:
        base = {sprint.id: rng.uniform(5.4, 6.6) - (0.4 if p.gender == 'male' else 0),
                bronco.id: rng.uniform(290, 360) - (25 if p.gender == 'male' else 0),
                jump.id: rng.uniform(32, 48) + (10 if p.gender == 'male' else 0)}
        for weeks_ago, better in ((10, 0), (2, 1)):
            for metric in (sprint, bronco, jump):
                value = base[metric.id]
                if better:
                    value = value * (1.04 if metric.higher_is_better else 0.97)
                db.session.add(FitnessRecord(
                    player_id=p.id, metric_id=metric.id, value=round(value, 1 if metric.unit == 's' else 0),
                    date_recorded=datetime.combine(today - timedelta(weeks=weeks_ago), time(19, 30)),
                    team_organization_id=team_id))
    for p in players[:4]:
        db.session.add(FitnessGoal(player_id=p.id, metric_id=sprint.id, created_by=owner_id,
                                   target_value=round(5.2 if p.gender == 'male' else 5.7, 1),
                                   target_date=today + timedelta(weeks=8), team_organization_id=team_id))


# ── Tournaments and games ───────────────────────────────────────

def _tournaments(team_id, players, today):
    from app.models.game import Game
    from app.models.tournament import Tournament
    from app.models.tournament_rsvp import TournamentRSVP

    rng = random.Random(3)
    specs = [('Spring Open', -42, 'Northfield'), ('Regional Championships', -14, 'Granite City'),
             ('Summer Cup', 24, 'Harbour Park')]
    made = []
    for name, offset, place in specs:
        start = today + timedelta(days=offset)
        t = Tournament(name=name, start_date=start, end_date=start + timedelta(days=1), location=place,
                       squad_size_target=16, team_organization_id=team_id,
                       rsvp_deadline=start - timedelta(days=10),
                       selection_published=offset < 0)
        db.session.add(t)
        db.session.flush()
        for p in players:
            if offset < 0:
                db.session.add(TournamentRSVP(tournament_id=t.id, player_id=p.id, status='attending',
                                              selection='picked', team_organization_id=team_id))
            elif rng.random() < 0.8:
                db.session.add(TournamentRSVP(
                    tournament_id=t.id, player_id=p.id, team_organization_id=team_id,
                    status=rng.choices(['attending', 'attending', 'maybe', 'not_attending'])[0],
                    responded_at=datetime.combine(today, time(12, 0))))
        if offset > 0:  # the schedule's out: the home page's "next game"
            for g, (opponent, hour) in enumerate((('Harbour Hawks', 9), ('Lakeside Lightning', 11),
                                                  ('Granite City', 14))):
                db.session.add(Game(tournament_id=t.id, opponent=opponent, date=start, start_time=time(hour, 0),
                                    field=f'Pitch {g + 1}', team_organization_id=team_id))
        made.append(t)
    db.session.commit()
    return made


FIELD_LENGTH, FIELD_WIDTH = 100.0, 37.0


class _Recorder:
    """Posts to the stat-taker's endpoints as the head coach, like the
    sideline screen does."""

    def __init__(self, app, user_id, team_id):
        from app.models.user import User
        self.app = app
        self.client = app.test_client()
        with app.app_context(), self.client.session_transaction(base_url='https://localhost') as s:
            s['_user_id'] = db.session.get(User, user_id).get_id()
            s['_fresh'] = True
            s['current_team_id'] = team_id
        # The page's CSRF token, sent back with each post like the sideline
        # screen does (CSRF stays on: this may run on the live site)
        self.headers = {'Referer': 'https://localhost/'}
        if app.config.get('WTF_CSRF_ENABLED', True):
            with app.app_context():
                page = self.client.get('/stats/', base_url='https://localhost').get_data(as_text=True)
            token = re.search(r'name="csrf-token" content="([^"]+)"', page)
            if token is None:
                raise RuntimeError('Could not sign in to record the demo games.')
            self.headers['X-CSRFToken'] = token.group(1)

    def post(self, url, **kw):
        # Each in its own app context, as in production (so the signed-in
        # user and the DB session don't outlive the request)
        with self.app.app_context():
            r = self.client.post(url, base_url='https://localhost', headers=self.headers, **kw)
        if r.status_code not in (200, 201):
            raise RuntimeError(f'{url}: {r.status_code} {r.get_data(as_text=True)[:200]}')
        return r


def _play_point(rec, rng, point_id, on_offence, line, strength):
    """A plausible sequence of events for one point. Returns nothing: the
    finish_point endpoint works out who scored."""
    def post(player_id, event_type, x, y, **extra):
        rec.post(f'/stats/record/{point_id}', json={
            'player_id': player_id, 'event_type': event_type, 'field_position_x': round(x, 1),
            'field_position_y': round(y, 1), 'is_offensive': extra.pop('is_offensive', True), **extra})

    if not on_offence:
        if rng.random() > strength - 0.1:
            post(rng.choice(line), 'scored_on', 0, rng.uniform(5, 30), is_offensive=False)
            return
        post(rng.choice(line), rng.choice(['block', 'block', 'forced_turnover']),
             rng.uniform(30, 80), rng.uniform(3, 34), is_offensive=False)
    x, y = 20.0, FIELD_WIDTH / 2
    holder = rng.choice(line)
    post(holder, 'catch', x, y)
    for _ in range(rng.randint(3, 9)):
        receiver = rng.choice([p for p in line if p != holder])
        x = min(FIELD_LENGTH - 1, x + rng.uniform(-6, 20))
        y = max(1, min(FIELD_WIDTH - 1, y + rng.uniform(-14, 14)))
        roll = rng.random()
        if roll < 0.08:
            post(holder, 'throwaway', x, y)
            if rng.random() > strength:
                post(rng.choice(line), 'scored_on', 0, rng.uniform(5, 30), is_offensive=False)
                return
            post(rng.choice(line), 'block', x, y, is_offensive=False)
            holder = rng.choice(line)
            post(holder, 'catch', x, y)
            continue
        if roll < 0.11:
            post(receiver, 'drop', x, y)
            post(rng.choice(line), 'scored_on', 0, rng.uniform(5, 30), is_offensive=False)
            return
        post(receiver, 'catch', x, y)
        holder = receiver
    scorer = rng.choice([p for p in line if p != holder])
    post(scorer, 'goal', rng.uniform(90, 99), rng.uniform(3, 34))
    if rng.random() < 0.5:
        rec.post(f'/stats/record_cutting_skill/{point_id}', json={
            'player_id': scorer, 'cutting_type': rng.choice(['open_deep', 'open_under', 'break_deep',
                                                             'break_under']),
            'outcome': rng.choice(['open_thrown_to', 'guarded_thrown_to', 'open_looked_off']),
            'field_position_x': 80, 'field_position_y': 18})


def _record_games(app, team_id, owner_id, players, tournaments, today):
    from app.models.game import Game
    from app.models.point import LineUp, Point

    rng = random.Random(7)
    women = [p.id for p in players if p.gender == 'female']
    men = [p.id for p in players if p.gender == 'male']
    rec = _Recorder(app, owner_id, team_id)
    opponents = iter(OPPONENTS)
    for t in tournaments:
        if t.start_date >= today:
            continue
        for g in range(3):
            strength = rng.uniform(0.62, 0.85)  # how well we play (a good team, not unbeatable)
            game = Game(tournament_id=t.id, opponent=next(opponents, f'Opponent {g + 1}'),
                        date=t.start_date + timedelta(days=g // 2), start_time=time(9 + 2 * (g % 2), 0),
                        field=f'Pitch {g + 1}', team_organization_id=team_id)
            db.session.add(game)
            db.session.commit()
            game_id = game.id
            ours = theirs = 0
            n = 0
            our_pull = True
            while max(ours, theirs) < 13 and n < 25:
                n += 1
                # We receive (O-line) unless we scored the last one
                line_type = 'D-line' if our_pull else 'O-line'
                four_women = n % 4 in (1, 2)
                point = Point(game_id=game_id, point_number=n, our_line_type=line_type,
                              our_score_before=ours, their_score_before=theirs,
                              starting_position='offense' if line_type == 'O-line' else 'defense',
                              point_outcome='scored', gender_ratio='4F3M' if four_women else '3F4M',
                              majority_gender='female' if four_women else 'male',
                              force_direction='forehand' if n % 3 else 'backhand',
                              team_organization_id=team_id)
                db.session.add(point)
                db.session.commit()
                point_id = point.id
                n_women = 4 if four_women else 3
                line = rng.sample(women, n_women) + rng.sample(men, 7 - n_women)
                db.session.add_all([LineUp(point_id=point_id, player_id=pid, team_organization_id=team_id)
                                    for pid in line])
                db.session.commit()
                _play_point(rec, rng, point_id, line_type == 'O-line', line, strength)
                rec.post(f'/stats/finish_point/{point_id}')
                db.session.expire_all()
                point = db.session.get(Point, point_id)
                our_pull = point.our_score_after > ours
                ours, theirs = point.our_score_after, point.their_score_after


# ── Scouting and feedback ───────────────────────────────────────

def _scouting_and_feedback(team_id, owner_id, players, tournaments, today):
    from app.models.feedback import PlayerFeedback, PlayerGoal
    from app.models.game import Game
    from app.models.scouting import OpponentPlayer, ScoutingReport

    upcoming = tournaments[-1]
    rematch = Game.query.filter_by(tournament_id=upcoming.id, opponent='Harbour Hawks').first()
    report = ScoutingReport(
        team_name='Harbour Hawks', date=today - timedelta(days=14), tournament_id=upcoming.id,
        game_id=rematch.id if rematch else None,
        team_organization_id=team_id, offense_tags='Ho stack,Hucks', defense_tags='Person,Cup zone',
        offense_strategy='Ho stack off the pull; looks deep on the first two throws.',
        defense_strategy='Force forehand person defence; cup zone upwind.',
        strengths='Two big throwers who hit the deep space early.',
        weaknesses='Short handler movement against a cup: they get stuck on the sideline.',
        game_plan='Take away the first deep look: deep-deep starts 5 yards further back. Cup upwind.',
        o_line_plan='Patient: hit the under, swing, then go deep once their wings pinch.',
        d_line_plan='Cup zone upwind, force flick downwind.')
    db.session.add(report)
    db.session.flush()
    db.session.add_all([
        OpponentPlayer(scouting_report_id=report.id, name='#21 tall handler', jersey_number='21',
                       position='handler', throwing_ability=5, cutting_ability=3, defensive_ability=3,
                       athletic_ability=4, preferred_throws='Hammer, long backhand', is_key_threat=True,
                       notes='Looks deep first. Make them throw the short one.', team_organization_id=team_id),
        OpponentPlayer(scouting_report_id=report.id, name='#4 fast cutter', jersey_number='4',
                       position='cutter', throwing_ability=3, cutting_ability=5, defensive_ability=4,
                       athletic_ability=5, is_key_threat=True, notes='Always cuts deep off the first catch.',
                       team_organization_id=team_id),
    ])
    notes = [
        (0, 'keep', 'Your break-side hucks in the last game were the best on the team. Keep looking for them.'),
        (2, 'work_on', 'Clear out quicker after a cut that doesn\'t get the disc: you were sitting in the lane.'),
        (3, 'note', 'Great energy on the sideline at Regionals.'),
        (5, 'work_on', 'Mark: stay on your toes and keep the force. You were getting broken on the inside.'),
        (8, 'keep', 'Calm resets under pressure. That\'s exactly what we want from a handler.'),
    ]
    for i, kind, text in notes:
        db.session.add(PlayerFeedback(player_id=players[i].id, coach_id=owner_id, content=text, kind=kind,
                                      context_tag='Tournament', shared=True))
    for i, title in ((0, 'Break the mark with a backhand around'), (2, 'Lead the team in blocks this season'),
                     (6, 'Make the O-line by the Summer Cup')):
        db.session.add(PlayerGoal(team_organization_id=team_id, player_id=players[i].id, title=title,
                                  horizon='short', created_by=owner_id))
