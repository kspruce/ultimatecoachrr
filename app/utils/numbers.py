"""Shirt numbers: one player per number across the whole club (1s and 2s
alike), 0 to 99. New players pick a free one when they set up their
account; it stays provisional until a coach confirms it."""
from app.models.player import Player, ReservedNumber

NUMBERS = range(0, 100)


def holders(team_id):
    """{number: player} for the club's active players with a number."""
    return {p.jersey_number: p for p in Player.query.filter(
        Player.team_organization_id == team_id, Player.active.is_(True),
        Player.jersey_number.isnot(None)).order_by(Player.name)}


def reserved(team_id):
    """{number: ReservedNumber} held back by captains or coaches."""
    return {r.number: r for r in ReservedNumber.query.filter_by(team_organization_id=team_id)}


def free_numbers(team_id, player=None):
    """Numbers nobody else active in the club wears and nobody has
    reserved (the player's own number counts as free for them)."""
    taken, held_back = holders(team_id), reserved(team_id)
    return [n for n in NUMBERS
            if n not in held_back and (n not in taken or (player is not None and taken[n].id == player.id))]


def can_pick(player):
    """New players pick when they have no number, or only a provisional one."""
    return player is not None and (player.jersey_number is None or player.number_provisional)


def parse_pick(player, raw):
    """(number or None, error or None) for a number posted at sign-up.
    Blank means decide later."""
    raw = (raw or '').strip()
    if not raw or not can_pick(player):
        return None, None
    if not raw.isdigit() or int(raw) not in NUMBERS:
        return None, 'Pick a shirt number from 0 to 99.'
    number = int(raw)
    if number not in free_numbers(player.team_organization_id, player):
        return None, f"Number {number} isn't free any more. Pick another."
    return number, None


def give_provisional(player, number):
    """Save the player's pick, on their profile and this season's roster.
    The caller commits."""
    from app.utils.season import current_season, roster_entry
    player.jersey_number = number
    player.number_provisional = True
    entry = roster_entry(player, current_season(player.team_organization_id))
    if entry is not None:
        entry.jersey_number = number


def provisional(team_id):
    return (Player.query.filter_by(team_organization_id=team_id, active=True, number_provisional=True)
            .filter(Player.jersey_number.isnot(None)).order_by(Player.jersey_number).all())


def set_number(player, number):
    """A captain or coach gives `player` a number (or none): confirmed, on
    their profile and this season's roster. The caller commits."""
    from app.utils.season import current_season, roster_entry
    player.jersey_number = number
    player.number_provisional = False
    entry = roster_entry(player, current_season(player.team_organization_id))
    if entry is not None:
        entry.jersey_number = number
