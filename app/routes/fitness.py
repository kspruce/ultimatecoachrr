# app/routes/fitness.py
"""Fitness: four standard tests, everyone's PBs, an opt-in team leaderboard
and a guide to running and improving on each test."""
from datetime import datetime

from flask import abort, Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models.fitness import FitnessGoal, FitnessMetric, FitnessRecord
from app.models.player import Player
from app.utils.team_filter import get_current_team_id

bp = Blueprint('fitness', __name__, url_prefix='/fitness')

LEADERBOARD_SIZE = 10


def _team_id_or_redirect():
    team_id = get_current_team_id()
    if team_id is None:
        flash('Please select a team first', 'warning')
    return team_id


def _own_player(player):
    me = getattr(current_user, 'player', None)
    return me is not None and me.id == player.id


def _player_or_404(player_id):
    """The player, if the current user may see and log their results:
    coaches and admins for anyone on their team, players for themselves."""
    player = Player.query.filter_by(id=player_id,
                                    team_organization_id=get_current_team_id()).first_or_404()
    if not (current_user.is_coach or _own_player(player)):
        abort(403)
    return player


def _better(metric, a, b):
    """True if value a beats value b on this metric."""
    return a < b if not metric.higher_is_better else a > b


def _pbs(team_id, metrics, player_ids=None):
    """{(player_id, metric_id): best record} for these metrics."""
    query = FitnessRecord.query.filter(
        FitnessRecord.team_organization_id == team_id,
        FitnessRecord.metric_id.in_([m.id for m in metrics]))
    if player_ids is not None:
        query = query.filter(FitnessRecord.player_id.in_(player_ids))
    by_id = {m.id: m for m in metrics}
    best = {}
    for record in query.order_by(FitnessRecord.date_recorded):
        key = (record.player_id, record.metric_id)
        if key not in best or _better(by_id[record.metric_id], record.value, best[key].value):
            best[key] = record
    return best


def _leaderboards(team_id, metrics):
    """Per test, the opted-in active players ranked on their PBs."""
    players = Player.query.filter_by(team_organization_id=team_id, active=True,
                                     fitness_leaderboard=True).all()
    pbs = _pbs(team_id, metrics, [p.id for p in players])
    boards = []
    for metric in metrics:
        rows = [pbs[(p.id, metric.id)] for p in players if (p.id, metric.id) in pbs]
        rows.sort(key=lambda r: r.value, reverse=metric.higher_is_better)
        boards.append({'metric': metric, 'records': rows[:LEADERBOARD_SIZE]})
    return boards, len(players)


@bp.route('/')
@login_required
def index():
    """The hub: your PBs, the leaderboard, the tests and, for coaches, the squad."""
    team_id = _team_id_or_redirect()
    if team_id is None:
        return redirect(url_for('team.select_team'))

    metrics = FitnessMetric.standard()
    me = getattr(current_user, 'player', None)
    if me is not None and me.team_organization_id != team_id:
        me = None
    my_pbs = _pbs(team_id, metrics, [me.id]) if me else {}

    leaderboards, opted_in = _leaderboards(team_id, metrics)

    squad = []
    if current_user.is_coach:
        players = Player.query.filter_by(team_organization_id=team_id, active=True) \
                              .order_by(Player.name).all()
        pbs = _pbs(team_id, metrics, [p.id for p in players])
        squad = [{'player': p, 'pbs': [pbs.get((p.id, m.id)) for m in metrics]} for p in players]

    return render_template('fitness/index.html', metrics=metrics, me=me,
                           my_pbs=[my_pbs.get((me.id, m.id)) for m in metrics] if me else [],
                           leaderboards=leaderboards, opted_in=opted_in, squad=squad)


@bp.route('/tests')
@login_required
def tests_guide():
    """How to run each test and how to get better at it."""
    return render_template('fitness/tests.html', metrics=FitnessMetric.standard())


@bp.route('/team-leaderboard')
@login_required
def team_leaderboard():
    return redirect(url_for('fitness.index', _anchor='leaderboard'))


@bp.route('/player/<int:player_id>')
@login_required
def player_fitness(player_id):
    """One player's PBs, history and targets, and a form to log a result."""
    player = _player_or_404(player_id)
    team_id = player.team_organization_id
    metrics = FitnessMetric.standard()

    records = FitnessRecord.query.filter_by(player_id=player.id, team_organization_id=team_id) \
                                 .order_by(FitnessRecord.date_recorded.desc()).all()
    targets = {g.metric_id: g for g in FitnessGoal.query.filter_by(
        player_id=player.id, team_organization_id=team_id, completed=False)}
    pbs = _pbs(team_id, metrics, [player.id])

    tests = []
    for metric in metrics:
        history = [r for r in records if r.metric_id == metric.id]
        pb = pbs.get((player.id, metric.id))
        target = targets.get(metric.id)
        tests.append({'metric': metric, 'pb': pb, 'history': history,
                      'target': target,
                      'progress': target.progress(pb.value if pb else None) if target else None})

    # Results on tests the club no longer runs: kept, shown as PBs only
    standard_ids = {m.id for m in metrics}
    older = {}
    for record in records:
        if record.metric_id in standard_ids:
            continue
        best = older.get(record.metric_id)
        if best is None or _better(record.metric, record.value, best.value):
            older[record.metric_id] = record

    return render_template('fitness/player_fitness.html', player=player, tests=tests,
                           older=sorted(older.values(), key=lambda r: r.metric.name),
                           own=_own_player(player),
                           today=datetime.utcnow().date().isoformat())


def _parse_date(value):
    if not value:
        return datetime.utcnow()
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return None


def _standard_metric_or_404(metric_id):
    metric = db.session.get(FitnessMetric, metric_id)
    if metric is None or metric.test is None:
        abort(404)
    return metric


def _complete_goals(player_id, metric_id, value, team_id):
    for goal in FitnessGoal.query.filter_by(player_id=player_id, metric_id=metric_id,
                                            completed=False, team_organization_id=team_id):
        if goal.is_met_by(value):
            goal.completed = True
            goal.completed_date = datetime.utcnow()
            flash(f'Target hit for {goal.metric.name}!', 'success')


@bp.route('/record/<int:player_id>', methods=['GET', 'POST'])
@login_required
def record_fitness(player_id):
    """Log one result for a player."""
    player = _player_or_404(player_id)
    back = redirect(url_for('fitness.player_fitness', player_id=player.id))
    if request.method == 'GET':
        return back

    metric = _standard_metric_or_404(request.form.get('metric_id', type=int) or 0)
    value = request.form.get('value', type=float)
    date = _parse_date(request.form.get('date'))
    if value is None or value <= 0 or date is None:
        flash('Enter a result above zero and a valid date.', 'danger')
        return back

    team_id = player.team_organization_id
    previous = _pbs(team_id, [metric], [player.id]).get((player.id, metric.id))
    db.session.add(FitnessRecord(player_id=player.id, metric_id=metric.id, value=value,
                                 notes=request.form.get('notes') or None, date_recorded=date,
                                 team_organization_id=team_id))
    _complete_goals(player.id, metric.id, value, team_id)
    db.session.commit()
    if previous is None or _better(metric, value, previous.value):
        flash(f'New PB: {metric.format(value)} {metric.unit} on the {metric.name}.', 'success')
    else:
        flash(f'{metric.name} result saved.', 'success')
    return back


@bp.route('/record/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record = FitnessRecord.query.filter_by(id=record_id,
                                           team_organization_id=get_current_team_id()).first_or_404()
    player = _player_or_404(record.player_id)
    db.session.delete(record)
    db.session.commit()
    flash('Result deleted.', 'success')
    return redirect(url_for('fitness.player_fitness', player_id=player.id))


@bp.route('/player/<int:player_id>/target/<int:metric_id>', methods=['POST'])
@login_required
def set_target(player_id, metric_id):
    """Set or clear a player's target on one test."""
    player = _player_or_404(player_id)
    metric = _standard_metric_or_404(metric_id)
    back = redirect(url_for('fitness.player_fitness', player_id=player.id))

    raw = '' if request.form.get('clear') else (request.form.get('target_value') or '').strip()
    target = None
    if raw:
        try:
            target = float(raw)
        except ValueError:
            target = None
        if target is None or target <= 0:
            flash('Enter a target above zero.', 'danger')
            return back

    team_id = player.team_organization_id
    goal = None
    if target is not None:
        goal = FitnessGoal(player_id=player.id, metric=metric, target_value=target,
                           created_by=current_user.id, team_organization_id=team_id)
        pb = _pbs(team_id, [metric], [player.id]).get((player.id, metric.id))
        if pb and goal.is_met_by(pb.value):
            flash(f'The PB of {metric.format(pb.value)} {metric.unit} already beats that. Aim higher!',
                  'info')
            return back

    FitnessGoal.query.filter_by(player_id=player.id, metric_id=metric.id, completed=False,
                                team_organization_id=team_id).delete()
    if goal is not None:
        db.session.add(goal)
    db.session.commit()
    flash(f'{metric.name} target {"set" if goal else "cleared"}.', 'success')
    return back


@bp.route('/player/<int:player_id>/leaderboard', methods=['POST'])
@login_required
def toggle_leaderboard(player_id):
    """Players opt themselves in or out of the leaderboard."""
    player = _player_or_404(player_id)
    if not _own_player(player):
        abort(403)
    player.fitness_leaderboard = request.form.get('opt_in') == '1'
    db.session.commit()
    flash('You are on the leaderboard.' if player.fitness_leaderboard
          else 'You are off the leaderboard.', 'success')
    if request.form.get('next') == 'hub':
        return redirect(url_for('fitness.index', _anchor='leaderboard'))
    return redirect(url_for('fitness.player_fitness', player_id=player.id))


@bp.route('/test-day', methods=['GET', 'POST'])
@login_required
def test_day():
    """Coaches enter one test's results for the whole squad."""
    if not current_user.is_coach:
        abort(403)
    team_id = _team_id_or_redirect()
    if team_id is None:
        return redirect(url_for('team.select_team'))

    metrics = FitnessMetric.standard()
    metric = _standard_metric_or_404(request.args.get('metric_id', type=int) or metrics[0].id)
    players = Player.query.filter_by(active=True, team_organization_id=team_id) \
                          .order_by(Player.name).all()

    if request.method == 'POST':
        date = _parse_date(request.form.get('date'))
        if date is None:
            flash('Enter a valid date.', 'danger')
            return redirect(url_for('fitness.test_day', metric_id=metric.id))
        saved = skipped = 0
        for player in players:
            raw = (request.form.get(f'value_{player.id}') or '').strip()
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                value = 0
            if value <= 0:
                skipped += 1
                continue
            db.session.add(FitnessRecord(player_id=player.id, metric_id=metric.id, value=value,
                                         date_recorded=date, team_organization_id=team_id))
            _complete_goals(player.id, metric.id, value, team_id)
            saved += 1
        db.session.commit()
        flash(f'Saved {saved} {metric.name} result{"s" if saved != 1 else ""}.', 'success')
        if skipped:
            flash(f'{skipped} result{"s were" if skipped != 1 else " was"} not a number above zero '
                  'and was skipped.', 'warning')
        return redirect(url_for('fitness.test_day', metric_id=metric.id))

    pbs = _pbs(team_id, [metric], [p.id for p in players])
    return render_template('fitness/test_day.html', metrics=metrics, metric=metric,
                           rows=[{'player': p, 'pb': pbs.get((p.id, metric.id))} for p in players],
                           today=datetime.utcnow().date().isoformat())
