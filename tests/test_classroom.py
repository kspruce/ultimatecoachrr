"""Classroom sessions: parsed from the plan's classroom tab, refined by
coaches, and shown to players only when a coach opens them."""
from datetime import datetime

from app import db
from app.models.season_plan import ClassroomResource, ClassroomSession, SeasonPlan
from app.utils.media_embed import embed_url, is_web_url
from app.utils.season_plan_import import load_export, parse_export, split_classroom_sections
from tests.test_season_plan import EXPORT, client, do_import, enable, herd, needs_export  # noqa: F401


def session(code):
    return ClassroomSession.query.filter_by(code=code).one()


def open_to_players():
    SeasonPlan.query.one().players_see_classroom = True
    db.session.commit()


# --------------------------------------------------------------------------
# Embeds
# --------------------------------------------------------------------------

def test_embed_urls():
    yt = 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'
    assert embed_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30') == yt
    assert embed_url('https://youtu.be/dQw4w9WgXcQ') == yt
    assert embed_url('https://www.youtube.com/live/dQw4w9WgXcQ?si=x') == yt
    assert embed_url('https://vimeo.com/123456/abcdef12') == 'https://player.vimeo.com/video/123456?h=abcdef12'
    assert embed_url('https://drive.google.com/file/d/1AbC-d_E/view?usp=sharing') == \
        'https://drive.google.com/file/d/1AbC-d_E/preview'
    assert embed_url('https://docs.google.com/presentation/d/1XyZ/edit#slide=id.p') == \
        'https://docs.google.com/presentation/d/1XyZ/embed'
    assert embed_url('https://zoom.us/rec/share/abc') is None  # shown as a button instead
    assert embed_url('https://www.youtube.com/watch?v=<script>') is None
    assert not is_web_url('javascript:alert(1)') and not is_web_url('ftp://x') and is_web_url('https://x.org')


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def test_split_classroom_sections():
    md = ('## Phase 1\n\n### C1 · Week 3 (w/c 18 Oct) · Online · How we learn\n\n**Goal:** learn.\n\n'
          '### C2 · Week 7 · In person · Leaders · Belonging\nbody\n\n## Phase 2\nnot C2')
    sections = split_classroom_sections(md)
    assert sections['C1'] == ('Week 3 (w/c 18 Oct) · Online · How we learn', '**Goal:** learn.')
    assert sections['C2'] == ('Week 7 · In person · Leaders · Belonging', 'body')


@needs_export
def test_parses_the_twelve_sessions_from_the_export():
    data = parse_export(*load_export(EXPORT))
    sessions = {c['code']: c for c in data['classroom']}
    assert list(sessions) == [f'C{n}' for n in range(1, 13)]
    c1, c3, c11 = sessions['C1'], sessions['C3'], sessions['C11']
    assert (c1['week_number'], c1['format'], c1['audience']) == (3, 'Online', 'All')
    assert c1['title'] == 'How we learn: the Heckler and the Hero'
    assert c1['goal'].startswith('everyone understands why Herd trains')
    assert '**Hook:**' in c1['plan_md'] and '### C2' not in c1['plan_md']
    assert "Questions we'll discuss" in c1['prep_md'] and 'What does your Heckler say' in c1['prep_md']
    assert 'inner game journal' in c1['prep_md']
    assert c3['audience'] == 'Captains, player leaders and anyone interested'
    assert c11['audience'] == '1s' and c11['week_number'] == 46
    assert sessions['C7']['goal'] is None and sessions['C7']['prep_md']  # no goal, but the idea
    assert all(c['prep_md'] for c in sessions.values())


@needs_export
def test_import_links_sessions_to_weeks(app, herd):
    do_import(herd['team'])
    assert ClassroomSession.query.count() == 12
    assert session('C4').week.week_number == 14
    assert [c.code for c in session('C4').week.classroom_sessions] == ['C4']


@needs_export
def test_reimport_keeps_coach_refinements(app, herd):
    do_import(herd['team'])
    cs = session('C1')
    cs.title = 'My better title'
    cs.prep_md = 'Watch this first'
    cs.summary_md = 'We talked'
    cs.join_url = 'https://zoom.us/j/1'
    cs.starts_at = datetime(2027, 10, 20, 19, 30)
    cs.plan_md = 'edited plan'
    cs.resources.append(ClassroomResource(team_organization_id=herd['team'], kind='video',
                                          title='Recording', url='https://youtu.be/dQw4w9WgXcQ'))
    db.session.commit()

    report = do_import(herd['team'])
    assert report.removed == []
    db.session.expire_all()
    cs = session('C1')
    assert (cs.title, cs.prep_md, cs.summary_md, cs.join_url) == \
        ('My better title', 'Watch this first', 'We talked', 'https://zoom.us/j/1')
    assert cs.starts_at == datetime(2027, 10, 20, 19, 30) and len(cs.resources) == 1
    assert cs.plan_md.startswith('**Goal:**')  # the facilitator plan follows the export
    assert ClassroomSession.query.count() == 12


@needs_export
def test_dry_run_writes_no_classroom_sessions(app, herd):
    report = do_import(herd['team'], dry_run=True)
    assert report.counts['classroom sessions'] == 12
    assert ClassroomSession.query.count() == 0


# --------------------------------------------------------------------------
# Pages and access
# --------------------------------------------------------------------------

@needs_export
def test_coach_sees_list_detail_and_plan(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    c = client(app, herd, 'coach')
    listing = c.get('/season-plan/classroom').get_data(as_text=True)
    assert 'How we learn: the Heckler and the Hero' in listing and 'C12' in listing
    page = c.get('/season-plan/classroom/c1').get_data(as_text=True)  # codes are case-insensitive
    assert 'Before the session' in page and 'Session plan' in page and 'Gallwey' in page
    assert c.get('/season-plan/classroom/C99').status_code == 404
    week = c.get('/season-plan/week/3').get_data(as_text=True)
    assert '/season-plan/classroom/C1' in week
    assert '/season-plan/classroom/C1' in c.get('/season-plan/weeks').get_data(as_text=True)
    overview = c.get('/season-plan/?on=2027-10-19').get_data(as_text=True)
    assert 'Classroom C1' in overview


@needs_export
def test_coach_edits_a_session_and_manages_resources(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    c = client(app, herd, 'coach')
    r = c.post('/season-plan/classroom/C1/edit', data={
        'title': 'How we learn', 'format': 'Online', 'audience': 'All', 'goal': 'Learn',
        'prep_md': 'Prep', 'plan_md': 'Plan', 'summary_md': 'We discussed', 'commitments_md': 'Journal',
        'start_date': '2027-10-20', 'start_time': '19:30', 'duration_minutes': '45',
        'join_url': 'https://zoom.us/j/123', 'summary_published': 'on'})
    assert r.status_code == 302
    cs = session('C1')
    assert cs.starts_at == datetime(2027, 10, 20, 19, 30) and cs.duration_minutes == 45
    assert cs.summary_published and cs.join_url == 'https://zoom.us/j/123'

    bad = c.post('/season-plan/classroom/C1/edit', data={'title': 'x', 'join_url': 'javascript:alert(1)'})
    assert bad.status_code == 400
    assert session('C1').join_url == 'https://zoom.us/j/123'

    c.post('/season-plan/classroom/C1/resources',
           data={'kind': 'video', 'title': 'Recording', 'url': 'https://youtu.be/dQw4w9WgXcQ'})
    c.post('/season-plan/classroom/C1/resources',
           data={'kind': 'slides', 'title': 'Slides', 'url': 'https://docs.google.com/presentation/d/1XyZ/edit'})
    c.post('/season-plan/classroom/C1/resources', data={'kind': 'link', 'url': 'javascript:alert(1)'})
    cs = session('C1')
    assert [r.title for r in cs.resources] == ['Recording', 'Slides']
    slides = cs.resources[1]
    c.post(f'/season-plan/classroom/C1/resources/{slides.id}/move', data={'direction': 'up'})
    db.session.expire_all()
    assert [r.title for r in session('C1').resources] == ['Slides', 'Recording']

    page = c.get('/season-plan/classroom/C1?on=2027-10-25').get_data(as_text=True)
    assert 'youtube-nocookie.com/embed/dQw4w9WgXcQ' in page
    assert 'docs.google.com/presentation/d/1XyZ/embed' in page
    assert 'Recording available' in page and 'Join the session' not in page  # it's over
    before = c.get('/season-plan/classroom/C1?on=2027-10-19').get_data(as_text=True)
    assert 'Join the session' in before and 'https://zoom.us/j/123' in before

    c.post(f'/season-plan/classroom/C1/resources/{slides.id}/delete')
    db.session.expire_all()
    assert [r.title for r in session('C1').resources] == ['Recording']


@needs_export
def test_players_see_classroom_only_when_opened(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    cs = session('C2')
    cs.summary_md = 'Draft notes'
    cs.resources.append(ClassroomResource(team_organization_id=herd['team'], kind='link',
                                          title='Coach crib sheet', url='https://example.com/crib',
                                          coaches_only=True))
    cs.resources.append(ClassroomResource(team_organization_id=herd['team'], kind='slides',
                                          title='Team slides', url='https://example.com/slides', order=2))
    db.session.commit()

    player = client(app, herd, 'player')
    assert player.get('/season-plan/classroom').status_code == 404
    assert player.get('/season-plan/classroom/C2').status_code == 404

    open_to_players()
    assert player.get('/season-plan/').headers['Location'].endswith('/season-plan/classroom')
    page = player.get('/season-plan/classroom/C2').get_data(as_text=True)
    assert 'Before the session' in page and 'Team slides' in page
    assert 'Coach crib sheet' not in page   # coaches-only resource
    assert 'Draft notes' not in page        # summary not published
    assert 'Spaghetti' not in page and 'spaghetti' not in page  # facilitator plan is coaches-only

    cs = session('C2')
    cs.summary_published = True
    db.session.commit()
    assert 'Draft notes' in player.get('/season-plan/classroom/C2').get_data(as_text=True)

    # Players can't edit or add resources
    assert player.post('/season-plan/classroom/C2/edit', data={'title': 'x'}).status_code == 302
    assert player.post('/season-plan/classroom/C2/resources',
                       data={'url': 'https://example.com'}).status_code == 302
    assert session('C2').title != 'x' and len(session('C2').resources) == 2


@needs_export
def test_classroom_404s_when_the_feature_is_off(app, herd):
    do_import(herd['team'])
    c = client(app, herd, 'coach')
    assert c.get('/season-plan/classroom').status_code == 404
    assert c.get('/season-plan/classroom/C1/edit').status_code == 404
