"""How a throw is classified for analysis: open or break side, what kind of
throw it was, and which part of the field it was thrown from.

Positions are always saved as if we attack the right-hand endzone: x runs
0-100 m upfield (endzones 0-18 and 82-100), y runs 0-37 m across the field.
Facing upfield, +y is the thrower's right, i.e. a right-hander's forehand
side and -y their backhand side.
"""
import math

FIELD_WIDTH = 37.0
CENTRE_Y = FIELD_WIDTH / 2
HUCK_DISTANCE = 20  # metres
# How far across the mark a throw has to go before it counts as a break.
BREAK_MIN_LATERAL = 3.0

# Point.force_direction -> which side (sign of y) the mark gives away
_BREAK_SIDE = {'forehand': -1, 'backhand': 1}


def break_side(force_direction, y_start):
    """+1/-1 for the side of the thrower that is the break side, or None
    when the force isn't one we can read a break from (zone, unknown...)."""
    if force_direction in _BREAK_SIDE:
        return _BREAK_SIDE[force_direction]
    if force_direction == 'middle' and y_start is not None:
        # Forced middle: the break is the throw towards the nearer sideline.
        return -1 if y_start < CENTRE_Y else 1
    return None


def is_break_throw(x_start, y_start, x_end, y_end, force_direction=None):
    """True for a throw that goes across the mark to the break side, False
    for an open-side throw, None when the force (or a position) is unknown."""
    if None in (x_start, y_start, x_end, y_end):
        return None
    side = break_side(force_direction, y_start)
    if side is None:
        return None
    return (y_end - y_start) * side >= BREAK_MIN_LATERAL


# --- throw kind --------------------------------------------------------------

THROW_KINDS = [
    ('dump_swing', 'Dumps & swings'),
    ('short', 'Short gainers'),
    ('mid', 'Mid-range'),
    ('huck', 'Hucks'),
]
THROW_KIND_LABELS = dict(THROW_KINDS)


def throw_kind(x_start, y_start, x_end, y_end):
    """'dump_swing' (backwards or flat), 'short' (< 15 m upfield), 'mid',
    or 'huck' (20 m+ upfield). None without positions."""
    if None in (x_start, y_start, x_end, y_end):
        return None
    gain = x_end - x_start
    distance = math.hypot(gain, y_end - y_start)
    if gain < 2:
        return 'dump_swing'
    if distance >= HUCK_DISTANCE and gain >= HUCK_DISTANCE * 0.75:
        return 'huck'
    if gain < 15:
        return 'short'
    return 'mid'


# --- field zones -------------------------------------------------------------

DEPTH_ZONES = [
    ('own_endzone', 'Own endzone', 0, 18),
    ('own_third', 'Own third', 18, 39),
    ('middle_third', 'Middle third', 39, 61),
    ('attacking_third', 'Attacking third', 61, 82),
    ('red_zone', 'Attacking endzone', 82, 100.01),
]
LANES = [
    ('left', 'Left sideline', 0, 12),
    ('centre', 'Middle', 12, 25),
    ('right', 'Right sideline', 25, 37.01),
]
DEPTH_LABELS = {key: label for key, label, _, _ in DEPTH_ZONES}
LANE_LABELS = {key: label for key, label, _, _ in LANES}


def _band(value, bands):
    if value is None:
        return None
    for key, _, low, high in bands:
        if low <= value < high:
            return key
    return bands[0][0] if value < bands[0][2] else bands[-1][0]


def depth_zone(x):
    return _band(x, DEPTH_ZONES)


def lane(y):
    return _band(y, LANES)


# --- direction (the 16-point throw direction radar) -------------------------

DIRECTIONS = ['E', 'ENE', 'NE', 'NNE', 'N', 'NNW', 'NW', 'WNW',
              'W', 'WSW', 'SW', 'SSW', 'S', 'SSE', 'SE', 'ESE']


def direction(x_start, y_start, x_end, y_end):
    """16-point direction: E is straight upfield, N the thrower's right
    (forehand side for a right-hander), W straight back, S their left."""
    if None in (x_start, y_start, x_end, y_end):
        return None
    degrees = math.degrees(math.atan2(y_end - y_start, x_end - x_start)) % 360
    return DIRECTIONS[int(((degrees + 11.25) % 360) // 22.5)]
