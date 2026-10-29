import os
import re
from collections import OrderedDict
from datetime import date, datetime

from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.models.scouting import (ScoutingReport, OpponentPlayer, ScoutingClip, POSITIONS, TAG_LABELS,
                                 OFFENSE_TAGS, DEFENSE_TAGS, DEFENDER_ROLES, ROLE_LABELS, THREAT_ROLES, COUNTERS,
                                 POSITION_THREATS, can_mark, defender_gender, defender_label, rank_defenders,
                                 format_time, games_against, matchup_reasons, opponent_key, suggest_matchups)
from app.models.player import Player
from app.models.game import Game
from app.forms.scouting import (ScoutingReportForm, OpponentPlayerForm, ScoutingClipForm, ScoutingFilterForm,
                                BulkPlayersForm)
from app.utils.utils import coach_required
from app.utils.team_filter import get_current_team_id, team_row_or_404

bp = Blueprint('scouting', __name__, url_prefix='/scouting')


# Tag key -> label, for the templates (and the macros they import)
bp.add_app_template_global(TAG_LABELS, 'scouting_tag_labels')
bp.add_app_template_filter(format_time, 'scouting_time')
bp.add_app_template_global(ROLE_LABELS, 'scouting_role_labels')


@bp.app_template_filter('role_labels')
def role_labels(value):
    """'huck_stopper,deep_d' -> 'Huck stopper, Deep defender'."""
    return ', '.join(ROLE_LABELS.get(k, k) for k in (value or '').split(',') if k)


def _report_or_404(report_id):
    return team_row_or_404(ScoutingReport, report_id)


def _players(report):
    players = report.players.filter_by(team_organization_id=get_current_team_id()).all()
    return sorted(players, key=lambda p: p.sort_key)


def _clips(report):
    return (report.clips.filter_by(team_organization_id=get_current_team_id())
            .order_by(ScoutingClip.created_at).all())


def _newest_first(query):
    """Dated reports newest first, then undated ones, most recently edited first."""
    return query.order_by(ScoutingReport.date.is_(None), ScoutingReport.date.desc(),
                          ScoutingReport.updated_at.desc())


def _counts(model, report_ids, *criteria):
    if not report_ids:
        return {}
    return dict(db.session.query(model.scouting_report_id, func.count(model.id))
                .filter(model.scouting_report_id.in_(report_ids), *criteria)
                .group_by(model.scouting_report_id).all())


def _record(games):
    """Head-to-head record from games that have a score."""
    played = [g for g in games if (g.our_score or 0) or (g.their_score or 0)]
    return {
        'played': len(played),
        'wins': sum(1 for g in played if g.is_win),
        'losses': sum(1 for g in played if g.is_loss),
        'ties': sum(1 for g in played if g.is_tie),
    }


@bp.route('/')
@login_required
def index():
    form = ScoutingFilterForm(request.args)
    team_id = get_current_team_id()

    query = ScoutingReport.query.filter_by(team_organization_id=team_id)
    q = (form.q.data or '').strip()
    if q:
        query = query.filter(ScoutingReport.team_name.ilike(f'%{q}%'))
    tournament_id = form.tournament_id.data
    if tournament_id not in {value for value, _ in form.tournament_id.choices}:
        tournament_id = 0  # not one of this team's tournaments
    if tournament_id:
        query = query.filter(ScoutingReport.tournament_id == tournament_id)
    date_from, date_to = form.date_from.data, form.date_to.data
    if date_from:
        query = query.filter(ScoutingReport.date >= date_from)
    if date_to:
        query = query.filter(ScoutingReport.date <= date_to)
    reports = _newest_first(query).all()

    tag = form.tag.data if form.tag.data in TAG_LABELS else ''
    if tag:
        reports = [r for r in reports if tag in r.offense_tag_list + r.defense_tag_list]

    ids = [r.id for r in reports]
    counts = {
        'players': _counts(OpponentPlayer, ids),
        'clips': _counts(ScoutingClip, ids),
        'threats': _counts(OpponentPlayer, ids, OpponentPlayer.is_key_threat.is_(True)),
    }

    group = form.group.data if form.group.data in ('opponent', 'tournament') else ''
    groups = OrderedDict()
    for report in reports:
        if not group:
            key, heading = 'all', None
        elif group == 'tournament':
            key = report.tournament_id or 0
            heading = report.tournament.name if report.tournament else 'No tournament'
        else:
            key = report.opponent_key
            heading = report.team_name
        groups.setdefault(key, {'heading': heading, 'opponent': report.team_name, 'reports': []})
        groups[key]['reports'].append(report)

    filtered = bool(q or tournament_id or tag or date_from or date_to)

    # Each filter in use, with a link that drops just that one
    params = {'q': q or None, 'tournament_id': tournament_id or None, 'tag': tag or None,
              'date_from': date_from.isoformat() if date_from else None,
              'date_to': date_to.isoformat() if date_to else None, 'group': group or None}
    labels = {
        'q': f'"{q}"',
        'tournament_id': dict(form.tournament_id.choices).get(tournament_id),
        'tag': TAG_LABELS.get(tag),
        'date_from': f'From {date_from.strftime("%d %b %Y")}' if date_from else None,
        'date_to': f'To {date_to.strftime("%d %b %Y")}' if date_to else None,
    }
    active_filters = [(label, url_for('scouting.index', **{k: v for k, v in params.items() if k != key and v}))
                      for key, label in labels.items() if params[key]]

    return render_template('scouting/index.html', form=form, groups=list(groups.values()), group=group,
                           active_filters=active_filters,
                           counts=counts, report_count=len(reports), filtered=filtered,
                           any_reports=filtered or bool(reports) or ScoutingReport.query.filter_by(
                               team_organization_id=team_id).first() is not None)


@bp.route('/opponent')
@login_required
def opponent():
    name = request.args.get('name', '')
    key = opponent_key(name)
    if not key:
        return redirect(url_for('scouting.index'))
    team_id = get_current_team_id()
    reports = [r for r in _newest_first(ScoutingReport.query.filter_by(team_organization_id=team_id)).all()
               if r.opponent_key == key]
    games = games_against(team_id, key)
    if not reports and not games:
        flash(f'Nothing on "{name}" yet.', 'info')
        return redirect(url_for('scouting.index'))
    display_name = reports[0].team_name if reports else games[0].opponent
    return render_template('scouting/opponent.html', name=display_name, reports=reports, games=games,
                           record=_record(games),
                           counts={'players': _counts(OpponentPlayer, [r.id for r in reports]),
                                   'clips': _counts(ScoutingClip, [r.id for r in reports])})


def _set_plays(report, form):
    """The plays picked on the form (the form only offers the team's)."""
    picked = set(form.play_ids.data or [])
    report.plays = [p for p in form.plays if p.id in picked]


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@coach_required
def add_report():
    form = ScoutingReportForm()
    game = None
    game_id = request.args.get('game_id', type=int)
    if game_id:
        game = Game.query.filter_by(id=game_id, team_organization_id=get_current_team_id()).first()
    if game and request.method == 'GET':
        # Starting from a game: fill in what we already know
        form.team_name.data = game.opponent
        form.date.data = game.date
        form.game_id.data = game.id
        form.tournament_id.data = game.tournament_id or 0

    if form.validate_on_submit():
        report = ScoutingReport(team_organization_id=get_current_team_id())
        form.populate_obj(report)
        _set_plays(report, form)
        db.session.add(report)
        db.session.commit()
        flash(f'Scouting report for "{report.team_name}" has been created!', 'success')
        return redirect(url_for('scouting.detail', report_id=report.id))

    previous = None
    name = form.team_name.data
    if name:
        previous = next((r for r in _newest_first(ScoutingReport.query.filter_by(
            team_organization_id=get_current_team_id())).all() if r.opponent_key == opponent_key(name)), None)
    return render_template('scouting/report_form.html', form=form, title='Add Scouting Report',
                           previous=previous, game=game)


@bp.route('/edit/<int:report_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_report(report_id):
    report = _report_or_404(report_id)
    form = ScoutingReportForm(obj=report)
    if request.method == 'GET':
        form.play_ids.data = [p.id for p in report.plays]

    if form.validate_on_submit():
        form.populate_obj(report)
        _set_plays(report, form)
        db.session.commit()
        flash(f'Scouting report for "{report.team_name}" has been updated!', 'success')
        return redirect(url_for('scouting.detail', report_id=report.id))

    return render_template('scouting/report_form.html', form=form, report=report, title='Edit Scouting Report')


@bp.route('/delete/<int:report_id>', methods=['POST'])
@login_required
@coach_required
def delete_report(report_id):
    report = _report_or_404(report_id)
    team_name = report.team_name
    db.session.delete(report)
    db.session.commit()
    flash(f'Scouting report for "{team_name}" has been deleted.', 'success')
    return redirect(url_for('scouting.index'))


@bp.route('/<int:report_id>/copy', methods=['POST'])
@login_required
@coach_required
def copy_report(report_id):
    """A new report that starts from this one: same analysis, plan and players, no clips."""
    source = _report_or_404(report_id)
    team_id = get_current_team_id()
    game = None
    game_id = request.form.get('game_id', type=int)
    if game_id:
        game = Game.query.filter_by(id=game_id, team_organization_id=team_id).first()

    report = ScoutingReport(
        team_organization_id=team_id,
        team_name=source.team_name,
        date=game.date if game else date.today(),
        tournament_id=game.tournament_id if game else None,
        game_id=game.id if game else None,
    )
    for column in ('offense_strategy', 'defense_strategy', 'strengths', 'weaknesses', 'notes',
                   'offense_tags', 'defense_tags', 'game_plan', 'o_line_plan', 'd_line_plan'):
        setattr(report, column, getattr(source, column))
    report.plays = list(source.plays)
    db.session.add(report)
    db.session.flush()
    for player in _players(source):
        db.session.add(OpponentPlayer(
            scouting_report_id=report.id, team_organization_id=team_id,
            **{c: getattr(player, c) for c in (
                'name', 'jersey_number', 'position', 'height', 'gender', 'throwing_ability',
                'cutting_ability', 'defensive_ability', 'athletic_ability', 'preferred_throws', 'notes',
                'is_key_threat', 'matched_player_id')}))
    db.session.commit()
    flash(f'New report for "{report.team_name}" started from the one on '
          f'{source.date.strftime("%d %b %Y") if source.date else "an earlier date"}. Update what has changed.',
          'success')
    return redirect(url_for('scouting.edit_report', report_id=report.id))


@bp.route('/<int:report_id>/link_game', methods=['POST'])
@login_required
@coach_required
def link_game(report_id):
    report = _report_or_404(report_id)
    game_id = request.form.get('game_id', type=int)
    game = Game.query.filter_by(id=game_id, team_organization_id=get_current_team_id()).first_or_404() \
        if game_id else None
    report.game_id = game.id if game else None
    if game and not report.tournament_id:
        report.tournament_id = game.tournament_id
    db.session.commit()
    if game:
        flash(f'Scouting report linked to the game vs {game.opponent}.', 'success')
    else:
        flash('Scouting report unlinked from its game.', 'success')
    next_url = request.form.get('next', '')
    if not next_url.startswith('/') or next_url.startswith('//') or '\\' in next_url:
        next_url = url_for('scouting.detail', report_id=report.id)  # only back to a page on this site
    return redirect(next_url)


@bp.route('/<int:report_id>')
@login_required
def detail(report_id):
    report = _report_or_404(report_id)
    players = _players(report)
    team_id = get_current_team_id()
    history = [r for r in _newest_first(ScoutingReport.query.filter(
        ScoutingReport.team_organization_id == team_id, ScoutingReport.id != report.id)).all()
        if r.opponent_key == report.opponent_key]
    games = games_against(team_id, report.opponent_key)
    return render_template('scouting/detail.html', report=report, players=players, clips=_clips(report),
                           history=history, games=games, record=_record(games), next_game=_next_game(games),
                           reasons={p.id: matchup_reasons(p, p.matched_player) for p in players if p.matched_player},
                           uncovered=[p for p in players if p.on_matchup_board and not p.matched_player_id],
                           offense_tags=OFFENSE_TAGS, defense_tags=DEFENSE_TAGS,
                           key_players=[p for p in players if p.on_matchup_board],
                           defender_label=defender_label,
                           panel=key_player_panel(report, _defenders(players)) if current_user.is_coach else None)


def _next_game(games):
    """The soonest unplayed game from today on, if there is one."""
    upcoming = [g for g in games if g.date and g.date >= date.today() and not (g.our_score or g.their_score)]
    return min(upcoming, key=lambda g: g.date) if upcoming else None


def _wants_json():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'


# Where a quick note goes: section -> (report column, label, is it a one-per-line list)
NOTE_SECTIONS = {
    'offense': ('offense_strategy', 'Offence', False),
    'defense': ('defense_strategy', 'Defence', False),
    'strength': ('strengths', 'Strengths', True),
    'weakness': ('weaknesses', 'Weaknesses', True),
    'note': ('notes', 'Notes', False),
}


def _append_line(existing, line):
    return f'{existing.rstrip()}\n{line}' if (existing or '').strip() else line


@bp.route('/<int:report_id>/note', methods=['POST'])
@login_required
@coach_required
def add_note(report_id):
    """A quick line added while watching: to a section of the report or to one player."""
    report = _report_or_404(report_id)
    text = ' '.join((request.form.get('text') or '').split())[:1000]
    section = request.form.get('section', 'note')
    if not text:
        message, ok = 'Type a note first.', False
    else:
        # The time on the coach's phone, e.g. "14:05", so notes read in order
        clock = request.form.get('time', '')
        stamped = f'[{clock}] {text}' if re.fullmatch(r'\d{1,2}:\d{2}', clock) else text
        player = None
        if section.startswith('player:'):
            player = OpponentPlayer.query.filter_by(id=int(section[7:]) if section[7:].isdigit() else 0,
                                                    scouting_report_id=report.id).first()
        if player:
            player.notes = _append_line(player.notes, stamped)
            where = player.name
        elif section in NOTE_SECTIONS:
            column, where, is_list = NOTE_SECTIONS[section]
            setattr(report, column, _append_line(getattr(report, column), text if is_list else stamped))
        else:
            message, ok, where = 'Pick where the note goes.', False, None
        if section in NOTE_SECTIONS or player:
            report.updated_at = datetime.utcnow()
            db.session.commit()
            message, ok = f'Added to {where}.', True

    if _wants_json():
        return jsonify({'success': ok, 'message': message}), (200 if ok else 400)
    flash(message, 'success' if ok else 'danger')
    return redirect(url_for('scouting.detail', report_id=report.id))


@bp.route('/<int:report_id>/tag', methods=['POST'])
@login_required
@coach_required
def toggle_tag(report_id):
    """Switch one offence or defence look on or off."""
    report = _report_or_404(report_id)
    tag = request.form.get('tag', '')
    column = ('offense_tags' if tag in dict(OFFENSE_TAGS) else
              'defense_tags' if tag in dict(DEFENSE_TAGS) else None)
    if not column:
        if _wants_json():
            return jsonify({'success': False, 'message': 'Unknown look.'}), 400
        return redirect(url_for('scouting.detail', report_id=report.id))
    tags = [t for t in (getattr(report, column) or '').split(',') if t]
    on = tag not in tags
    tags = tags + [tag] if on else [t for t in tags if t != tag]
    setattr(report, column, ','.join(tags) or None)
    report.updated_at = datetime.utcnow()
    db.session.commit()
    if _wants_json():
        return jsonify({'success': True, 'on': on, 'label': TAG_LABELS[tag]})
    return redirect(url_for('scouting.detail', report_id=report.id))


@bp.route('/sw.js')
def service_worker():
    """Keeps the game cards a phone has opened readable when the signal drops.
    Served from /scouting/ so it can only ever handle scouting pages."""
    response = send_file(os.path.join(current_app.static_folder, 'js', 'scouting_sw.js'),
                         mimetype='application/javascript', max_age=0)
    response.headers['Cache-Control'] = 'no-cache'
    return response


@bp.route('/<int:report_id>/card')
@login_required
def card(report_id):
    """One printable page for the sideline."""
    report = _report_or_404(report_id)
    players = _players(report)
    threats = [p for p in players if p.is_key_threat or p.threat_level in ('elite', 'high')][:6]
    matchups = [p for p in players if p.matched_player]
    games = [g for g in games_against(get_current_team_id(), report.opponent_key)
             if (g.our_score or 0) or (g.their_score or 0)]
    return render_template('scouting/card.html', report=report, threats=threats, matchups=matchups,
                           reasons={p.id: matchup_reasons(p, p.matched_player) for p in matchups},
                           uncovered=[p for p in players if p.on_matchup_board and not p.matched_player_id],
                           last_game=games[0] if games else None, record=_record(games),
                           rendered_at=datetime.utcnow().isoformat() + 'Z')


def _defenders(opponents=()):
    """Our active players, plus anyone who has left but is still down to mark someone."""
    team_id = get_current_team_id()
    players = Player.query.filter_by(team_organization_id=team_id, active=True).all()
    have = {p.id for p in players}
    missing = {o.matched_player_id for o in opponents if o.matched_player_id and o.matched_player_id not in have}
    if missing:
        players += Player.query.filter(Player.id.in_(missing), Player.team_organization_id == team_id).all()
    return sorted(players, key=lambda p: p.name.lower())


def key_player_panel(report, defenders):
    """What the 'Add key player' panel needs, including what the page's
    script uses to float the best markers to the top as threats are picked."""
    return {
        'report': report,
        'threat_roles': THREAT_ROLES,
        'positions': POSITIONS,
        'defenders': defenders,
        'data': {
            'counters': COUNTERS,
            'positionThreats': POSITION_THREATS,
            'labels': ROLE_LABELS,
            'defenders': [{'id': d.id, 'roles': [r for r in (d.defensive_roles or '').split(',') if r],
                           'gender': defender_gender(d)} for d in defenders],
        },
    }


@bp.route('/<int:report_id>/key_player', methods=['POST'])
@login_required
@coach_required
def add_key_player(report_id):
    """'Their #10 is a cutter who wants it open under; our #12 marks them', in one go."""
    report = _report_or_404(report_id)
    number = (request.form.get('jersey_number') or '').strip().lstrip('#')[:10]
    name = (request.form.get('name') or '').strip()[:100]
    back = 'matchups' if request.form.get('back') == 'matchups' else 'detail'
    back_url = url_for(f'scouting.{back}', report_id=report.id)
    if not number and not name:
        flash('Give their number or name.', 'danger')
        return redirect(back_url)

    position = request.form.get('position') if request.form.get('position') in POSITIONS else None
    threats = [t for t in request.form.getlist('threat_roles') if t in dict(THREAT_ROLES)]
    gender = request.form.get('gender') if request.form.get('gender') in ('male', 'female') else None
    ours = {d.id: d for d in _defenders()}
    marker = ours.get(request.form.get('matched_player_id', type=int))
    player = OpponentPlayer(
        scouting_report_id=report.id, team_organization_id=get_current_team_id(),
        name=name or f'#{number}', jersey_number=number or None, position=position, gender=gender,
        threat_roles=','.join(threats) or None, is_key_threat=True,
        notes=(request.form.get('notes') or '').strip() or None,
        matched_player_id=marker.id if marker else None)
    db.session.add(player)
    report.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f'{player.name} added{" — " + defender_label(marker, with_roles=False) + " marks them" if marker else ""}.',
          'success')
    if request.form.get('add_another'):
        return redirect(back_url + '?add=key#keyPlayer')
    return redirect(back_url + ('#matchups' if back == 'detail' else ''))


@bp.route('/<int:report_id>/matchups', methods=['GET', 'POST'])
@login_required
def matchups(report_id):
    """Who marks whom: the coach's picks, and suggestions from what each side is good at."""
    report = _report_or_404(report_id)
    opponents = _players(report)
    defenders = _defenders(opponents)

    if request.method == 'POST':
        if not current_user.is_coach:
            flash('Only coaches can change matchups.', 'danger')
            return redirect(url_for('scouting.matchups', report_id=report.id))
        ours = {d.id: d for d in defenders}
        theirs = {o.id: o for o in opponents}
        for o in opponents:
            field = f'match-{o.id}'
            if field in request.form:
                chosen = request.form.get(field, type=int)
                o.matched_player_id = chosen if chosen in ours else None
        message = 'Matchups saved.'
        use = request.form.get('use', '')
        if re.fullmatch(r'\d+:\d+', use):
            opponent_id, defender_id = (int(x) for x in use.split(':'))
            if opponent_id in theirs and defender_id in ours:
                theirs[opponent_id].matched_player_id = defender_id
                message = f'{ours[defender_id].name} marks {theirs[opponent_id].name}.'
        if request.form.get('use_all'):
            suggested = suggest_matchups(opponents, defenders)
            for opponent_id, (defender, _) in suggested.items():
                theirs[opponent_id].matched_player_id = defender.id
            message = (f'Used {len(suggested)} suggestion{"s" if len(suggested) != 1 else ""}.' if suggested
                       else 'No suggestions to use.')
        report.updated_at = datetime.utcnow()
        db.session.commit()
        flash(message, 'success')
        return redirect(url_for('scouting.matchups', report_id=report.id))

    suggestions = suggest_matchups(opponents, defenders)
    board = [o for o in opponents if o.on_matchup_board]
    marking = {}
    for o in opponents:
        if o.matched_player_id:
            marking.setdefault(o.matched_player_id, []).append(o)
    return render_template('scouting/matchups.html', report=report, board=board,
                           ranked={o.id: rank_defenders(o, defenders) for o in opponents},
                           defender_label=defender_label, panel=key_player_panel(report, defenders),
                           others=[o for o in opponents if not o.on_matchup_board], defenders=defenders,
                           suggestions=suggestions, reasons={o.id: matchup_reasons(o, o.matched_player)
                                                             for o in opponents if o.matched_player},
                           doubled={pid: os for pid, os in marking.items() if len(os) > 1},
                           can_mark=can_mark, roles_set=any(d.defensive_roles for d in defenders),
                           typed=any(o.threat_roles for o in opponents))


@bp.route('/defenders', methods=['GET', 'POST'])
@login_required
@coach_required
def defenders():
    """What each of our players is good at marking, for the matchup suggestions."""
    players = _defenders()
    valid = dict(DEFENDER_ROLES)
    if request.method == 'POST':
        for player in players:
            roles = [r for r in request.form.getlist(f'roles-{player.id}') if r in valid]
            player.defensive_roles = ','.join(roles) or None
        db.session.commit()
        flash('Defensive strengths saved.', 'success')
        back = request.args.get('report', type=int)
        if back and ScoutingReport.query.filter_by(id=back, team_organization_id=get_current_team_id()).first():
            return redirect(url_for('scouting.matchups', report_id=back))
        return redirect(url_for('scouting.defenders'))
    # Mixed teams mark by gender match, so group them that way
    groups = [(heading, [p for p in players if defender_gender(p) == key])
              for key, heading in (('female', 'Women-matching'), ('male', 'Men-matching'), (None, 'Others'))]
    return render_template('scouting/defenders.html', players=players, groups=groups, roles=DEFENDER_ROLES,
                           report_id=request.args.get('report', type=int))


@bp.route('/<int:report_id>/players')
@login_required
def players(report_id):
    report = _report_or_404(report_id)
    players = _players(report)
    clip_counts = dict(db.session.query(ScoutingClip.opponent_player_id, func.count(ScoutingClip.id))
                       .filter(ScoutingClip.scouting_report_id == report.id,
                               ScoutingClip.opponent_player_id.isnot(None))
                       .group_by(ScoutingClip.opponent_player_id).all())
    return render_template('scouting/players.html', report=report, players=players, clip_counts=clip_counts)


@bp.route('/<int:report_id>/add_player', methods=['GET', 'POST'])
@login_required
@coach_required
def add_player(report_id):
    report = _report_or_404(report_id)
    form = OpponentPlayerForm()

    if form.validate_on_submit():
        player = OpponentPlayer(scouting_report_id=report.id, team_organization_id=get_current_team_id())
        form.populate_obj(player)
        db.session.add(player)
        db.session.commit()
        flash(f'Player "{player.name}" has been added!', 'success')
        if request.form.get('add_another'):
            return redirect(url_for('scouting.add_player', report_id=report.id))
        return redirect(url_for('scouting.players', report_id=report.id))

    return render_template('scouting/player_form.html', form=form, report=report, title='Add Player',
                           draft_key=f'player-new-{report.id}')


ROSTER_LINE = re.compile(
    r'^#?\s*(?P<number>\d{1,3})?[\s.,:)\-–]*(?P<name>.*?)[\s,(\-–]*(?P<position>handler|cutter|hybrid)?\)?$',
    re.IGNORECASE)


def parse_roster(text):
    """'7 Jane Doe handler', '#12 Sam (cutter)', 'Alex' -> [{'jersey_number', 'name', 'position'}]."""
    players = []
    for line in (text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        match = ROSTER_LINE.match(line)
        name = (match.group('name') or '').strip(' -,') if match else ''
        if not name:
            continue
        players.append({
            'jersey_number': match.group('number'),
            'name': name[:100],
            'position': (match.group('position') or '').lower() or None,
        })
    return players


@bp.route('/<int:report_id>/add_players', methods=['GET', 'POST'])
@login_required
@coach_required
def add_players(report_id):
    report = _report_or_404(report_id)
    form = BulkPlayersForm()

    if form.validate_on_submit():
        parsed = parse_roster(form.roster.data)
        if not parsed:
            form.roster.errors.append('No players found. Put one player on each line.')
        else:
            for p in parsed:
                db.session.add(OpponentPlayer(scouting_report_id=report.id,
                                              team_organization_id=get_current_team_id(), **p))
            db.session.commit()
            flash(f'Added {len(parsed)} player{"s" if len(parsed) != 1 else ""}. Rate the ones that matter.',
                  'success')
            return redirect(url_for('scouting.players', report_id=report.id))

    return render_template('scouting/players_bulk.html', form=form, report=report, positions=POSITIONS)


@bp.route('/edit_player/<int:player_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_player(player_id):
    player = team_row_or_404(OpponentPlayer, player_id)
    report = _report_or_404(player.scouting_report_id)
    form = OpponentPlayerForm(obj=player)

    if form.validate_on_submit():
        form.populate_obj(player)
        db.session.commit()
        flash(f'Player "{player.name}" has been updated!', 'success')
        if request.args.get('back') == 'matchups':
            return redirect(url_for('scouting.matchups', report_id=player.scouting_report_id))
        return redirect(url_for('scouting.players', report_id=player.scouting_report_id))

    return render_template('scouting/player_form.html', form=form, player=player, report=report, title='Edit Player',
                           draft_key=f'player-{player.id}')


@bp.route('/delete_player/<int:player_id>', methods=['POST'])
@login_required
@coach_required
def delete_player(player_id):
    player = team_row_or_404(OpponentPlayer, player_id)
    report_id = player.scouting_report_id
    name = player.name

    ScoutingClip.query.filter_by(opponent_player_id=player.id).update({'opponent_player_id': None})
    db.session.delete(player)
    db.session.commit()

    flash(f'Player "{name}" has been deleted!', 'success')
    return redirect(url_for('scouting.players', report_id=report_id))


@bp.route('/<int:report_id>/clips')
@login_required
def clips(report_id):
    report = _report_or_404(report_id)
    clips = _clips(report)
    player = None
    player_id = request.args.get('player', type=int)
    if player_id:
        player = OpponentPlayer.query.filter_by(id=player_id, scouting_report_id=report.id).first()
        if player:
            clips = [c for c in clips if c.opponent_player_id == player.id]
    return render_template('scouting/clips.html', report=report, clips=clips, player=player)


@bp.route('/<int:report_id>/add_clip', methods=['GET', 'POST'])
@login_required
@coach_required
def add_clip(report_id):
    report = _report_or_404(report_id)
    form = ScoutingClipForm(report=report)
    if request.method == 'GET':
        form.opponent_player_id.data = request.args.get('player', 0, type=int)

    if form.validate_on_submit():
        clip = ScoutingClip(scouting_report_id=report.id, team_organization_id=get_current_team_id())
        form.populate_obj(clip)
        db.session.add(clip)
        db.session.commit()
        flash(f'Clip "{clip.title}" has been added!', 'success')
        return redirect(url_for('scouting.clips', report_id=report.id))

    return render_template('scouting/clip_form.html', form=form, report=report, title='Add Clip')


@bp.route('/edit_clip/<int:clip_id>', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_clip(clip_id):
    clip = team_row_or_404(ScoutingClip, clip_id)
    report = _report_or_404(clip.scouting_report_id)
    form = ScoutingClipForm(obj=clip, report=report)

    if form.validate_on_submit():
        form.populate_obj(clip)
        db.session.commit()
        flash(f'Clip "{clip.title}" has been updated!', 'success')
        return redirect(url_for('scouting.clips', report_id=clip.scouting_report_id))

    return render_template('scouting/clip_form.html', form=form, clip=clip, report=report, title='Edit Clip')


@bp.route('/delete_clip/<int:clip_id>', methods=['POST'])
@login_required
@coach_required
def delete_clip(clip_id):
    clip = team_row_or_404(ScoutingClip, clip_id)
    report_id = clip.scouting_report_id
    title = clip.title

    db.session.delete(clip)
    db.session.commit()

    flash(f'Clip "{title}" has been deleted!', 'success')
    return redirect(url_for('scouting.clips', report_id=report_id))


@bp.route('/view_clip/<int:clip_id>')
@login_required
def view_clip(clip_id):
    clip = team_row_or_404(ScoutingClip, clip_id)
    report = _report_or_404(clip.scouting_report_id)
    return render_template('scouting/view_clip.html', clip=clip, report=report)
