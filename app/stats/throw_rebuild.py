"""A point's stored throws, rebuilt from its events.

The Throw table is derived data: every row follows from the point's events
in the order they were recorded (see app/stats/point_replay.py for the
rules). Rebuilding the whole point after any change (an event recorded or
undone, the point edited, a player deleted) keeps it consistent, rather than
patching individual throws as events come and go.

What gets a row:
- a completed pass between two of our touches in the same possession
  ('regular', or 'assist' / 'hockey_assist' when it's the pass into the
  goal / into the assist);
- a throwaway ('throwaway', incomplete), thrown from the last touch, or from
  where the disc was won back when no catch was recorded.

What doesn't:
- the pickup that starts a possession (after a pull, a block or their
  turnover): nobody threw it;
- a drop: that's the receiver's turnover, not an incomplete throw for the
  thrower (it is still drawn on the point page);
- substitutions, which aren't play.

Nothing else refers to a throw's id, so the rows are simply replaced.
"""
from app import db
from app.models.event import Event
from app.models.throws import Throw
from app.stats.point_replay import build_point_replay


def throws_for_point(point, events=None):
    """The Throw rows a point's events describe (not added to the session)."""
    if events is None:
        events = Event.query.filter_by(point_id=point.id).all()
    replay = build_point_replay(point, events, with_positions_only=False)
    rows = []
    for t in replay['throws']:
        if not t['counted']:
            continue
        if t['complete']:
            throw_type = t['role']
        else:
            throw_type = 'throwaway'
        rows.append(Throw(
            point_id=point.id,
            thrower_id=t['thrower_id'],
            receiver_id=t['receiver_id'],
            throwing_event_id=t['throwing_event_id'],
            receiving_event_id=t['receiving_event_id'],
            x_start=t['x1'], y_start=t['y1'], x_end=t['x2'], y_end=t['y2'],
            distance=t['distance'],
            is_completion=t['complete'],
            throw_type=throw_type,
            is_offensive=True,
            break_throw=t['break'],
            force_direction=point.force_direction,
            opposition_team=(point.game.opponent or '')[:50] or None if point.game else None,
            team_organization_id=point.team_organization_id,
        ))
    return rows


def rebuild_point_throws(point):
    """Replace a point's stored throws with the ones its events describe.
    Flushes but doesn't commit. Returns (removed, added)."""
    # The old throws go first: they may point at an event the caller has
    # just deleted, which the database won't let go while they do.
    with db.session.no_autoflush:
        old = Throw.query.filter_by(point_id=point.id).all()
    for throw in old:
        db.session.delete(throw)
    removed = len(old)
    db.session.flush()  # the throws, then new or deleted events
    events = Event.query.filter_by(point_id=point.id).all()
    rows = throws_for_point(point, events)
    db.session.add_all(rows)
    db.session.flush()
    return removed, len(rows)


def rebuild_throws(points):
    """Rebuild every point given. Returns (points, removed, added)."""
    removed = added = 0
    count = 0
    for point in points:
        r, a = rebuild_point_throws(point)
        removed += r
        added += a
        count += 1
    return count, removed, added
