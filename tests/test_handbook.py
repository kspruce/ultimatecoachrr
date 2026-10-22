"""Leadership handbook: the source file's pages, the import, cleaning
edited HTML, and who can see it (leaders on teams that switch it on)."""
import os

from app import db
from app.models.handbook import HandbookPage
from app.models.team_organization import TeamOrganization
from app.models.team_settings import TeamSettings
from app.utils.handbook import SECTION_KEYS, clean_html, import_handbook, link_pages, parse_handbook
from tests.test_season_plan import NAV_PAGE, client, herd  # noqa: F401

SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'imports', 'leadership-handbook', 'handbook.html')


def enable(team_id, on=True):
    TeamSettings.query.filter_by(team_id=team_id).one().leadership_handbook_enabled = on
    db.session.commit()


def do_import(team_id, **kw):
    return import_handbook(SOURCE, db.session.get(TeamOrganization, team_id), **kw)


def test_source_file_parses_in_section_order():
    with open(SOURCE, encoding='utf-8') as f:
        pages = parse_handbook(f.read())
    slugs = [p['slug'] for p in pages]
    assert len(pages) == 59 and len(set(slugs)) == 59
    assert slugs[0] == 'herd-way' and 'about' not in slugs
    assert [SECTION_KEYS.index(p['section']) for p in pages] == sorted(SECTION_KEYS.index(p['section']) for p in pages)
    captain = next(p for p in pages if p['slug'] == 'captain-class')
    assert captain['title'] == 'What great captains do' and captain['lead'].startswith('Sam Walker')
    assert 'Relentless effort' in captain['body_html'] and '<header>' not in captain['body_html']
    # every link between pages points at a page that exists
    for p in pages:
        for target in __import__('re').findall(r'href="#([^"]+)"', p['body_html']):
            assert target in slugs, (p['slug'], target)


def test_clean_html_keeps_formatting_and_drops_anything_active():
    dirty = ('<p class="x" onclick="evil()">Hi <b>there</b></p><script>alert(1)</script>'
             '<a href="javascript:alert(1)">bad</a><a href="#spirit">good</a>'
             '<img src=x onerror=alert(1)><div style="color:red"><h4>Head</h4>'
             '<iframe src="https://evil"></iframe><a href="https://example.com">out</a>')
    clean = clean_html(dirty)
    assert '<p class="x">Hi <b>there</b></p>' in clean
    for bad in ('script', 'onclick', 'javascript', 'onerror', '<img', 'style=', 'iframe', 'alert'):
        assert bad not in clean
    assert '<a rel="noopener noreferrer">bad</a>' in clean
    assert '<a href="#spirit" rel="noopener noreferrer">good</a>' in clean
    assert clean.count('<div>') == clean.count('</div>')  # unclosed tags are closed
    assert clean_html('5 < 6 & <b>x') == '5 &lt; 6 &amp; <b>x</b>'


def test_link_pages():
    assert link_pages('<a href="#spirit">s</a>', lambda s: f'/handbook/{s}') == '<a href="/handbook/spirit">s</a>'


def test_import_dry_run_reimport_and_replace(app, herd):
    report = do_import(herd['team'], dry_run=True)
    assert len(report.created) == 59 and HandbookPage.query.count() == 0

    do_import(herd['team'])
    assert HandbookPage.query.count() == 59
    page = HandbookPage.query.filter_by(slug='spirit').one()
    page.title = 'Spirit, our way'
    db.session.commit()

    report = do_import(herd['team'])
    assert not report.created and len(report.kept) == 59
    assert HandbookPage.query.filter_by(slug='spirit').one().title == 'Spirit, our way'

    report = do_import(herd['team'], replace=True)
    assert len(report.updated) == 59
    assert HandbookPage.query.filter_by(slug='spirit').one().title == 'Spirit is part of the fun'


def test_toggle_is_off_by_default(app, herd):
    assert TeamSettings.query.filter_by(team_id=herd['team']).one().leadership_handbook_enabled is False


def test_off_hides_the_nav_and_every_route_is_404(app, herd):
    do_import(herd['team'])
    c = client(app, herd, 'captain')
    assert '/handbook/' not in c.get(NAV_PAGE).get_data(as_text=True)
    for url in ('/handbook/', '/handbook/spirit', '/handbook/spirit/edit'):
        assert c.get(url).status_code == 404, url


def test_leaders_read_search_and_navigate(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    for who in ('coach', 'captain'):
        c = client(app, herd, who)
        assert '/handbook/' in c.get(NAV_PAGE).get_data(as_text=True)
        home = c.get('/handbook/').get_data(as_text=True)
        assert 'How we lead Herd' in home and 'Lessons from great teams' in home and 'Fast break' in home

    c = client(app, herd, 'coach')
    page = c.get('/handbook/spirit').get_data(as_text=True)
    assert 'Spirit is part of the fun' in page and 'Play hard, play fair' in page
    assert 'href="/handbook/safe-play"' in page                   # page links point at pages
    assert 'Every player matters' in page and 'Freedom to fail' in page  # previous and next
    assert c.get('/handbook/nope').status_code == 404

    results = c.get('/handbook/?q=timeout').get_data(as_text=True)
    assert 'href="/handbook/timeouts"' in results
    assert 'Nothing matches' in c.get('/handbook/?q=zzzzqqq').get_data(as_text=True)


def test_leaders_edit_and_the_html_is_cleaned(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    c = client(app, herd, 'captain')
    assert 'Edit page' in c.get('/handbook/spirit/edit').get_data(as_text=True)
    r = c.post('/handbook/spirit/edit', data={
        'title': 'Spirit', 'lead': 'Our take.',
        'body_html': '<p>Call it fair.</p><script>alert(1)</script>'})
    assert r.status_code == 302
    page = HandbookPage.query.filter_by(slug='spirit').one()
    assert (page.title, page.lead, page.body_html) == ('Spirit', 'Our take.', '<p>Call it fair.</p>')
    assert c.post('/handbook/spirit/edit', data={'title': ' ', 'body_html': 'x'}).status_code == 200
    assert HandbookPage.query.filter_by(slug='spirit').one().body_html == '<p>Call it fair.</p>'


def test_players_never_see_it(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    c = client(app, herd, 'player')
    assert '/handbook/' not in c.get(NAV_PAGE).get_data(as_text=True)
    for url in ('/handbook/', '/handbook/spirit', '/handbook/spirit/edit'):
        assert c.get(url).status_code == 404, url
    assert c.post('/handbook/spirit/edit', data={'title': 'x'}).status_code == 404


def test_other_teams_pages_are_not_reachable(app, herd):
    from tests import stats_data
    from tests.test_teams import make_user
    do_import(herd['team'])
    other = stats_data.build_team('Other', 'other-team')
    db.session.add(TeamSettings(team_id=other.id, leadership_handbook_enabled=True))
    db.session.commit()
    coach = make_user(other, 'othercoach', role='coach')
    c = stats_data.Client(app, coach.id, other.id)
    assert c.get('/handbook/spirit').status_code == 404
    assert 'The handbook is empty' in c.get('/handbook/').get_data(as_text=True)
