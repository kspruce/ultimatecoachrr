# Stats review (November 2026)

A check of every number the stats pages show: is the definition sensible for
ultimate, does the code calculate it correctly, does the same stat give the
same number everywhere, and do the pages say what the code does. Then the
2027/28 season plan's "Measuring improvement" stats: which the site has,
which were added, and which need new recording.

Every formula now has a test on a small game worked out by hand, with the
sums in the comments: `tests/test_stats_worked.py`, using
`tests/worked_games.py` to record tiny games through the stat-taker's own
endpoints. Coaches can see the counting rules at `/stats/ratings#counting`
("How the stats are counted", linked from the dashboard and team page).

## The rules every stat now follows

These are the usual conventions in ultimate stats (UltiAnalytics, UFA, the
Ultiworld "four metrics" articles, BBSM). Where the site already had a
convention, it's kept and now applied everywhere.

| Rule | Definition |
| --- | --- |
| Callahan | A goal **and** a block (+2 in +/-), and a possession that ends in a goal. Game Day and the ratings already did this. |
| Turnover | Throwaway, drop or stall. A stall is the holder's turnover, not a throw. A dropped pull is a drop. |
| Drop | The receiver's turnover. It counts against the receiver's catching, not the thrower's completion. |
| Player completion | The thrower's passes caught ÷ passes thrown (a drop isn't the thrower's incomplete). |
| Team completion | The team's passes caught ÷ passes thrown: a drop is an incomplete pass. |
| Catch / drop rate | Passes caught (or dropped) ÷ passes that reached the player. A pickup isn't a catch. |
| Touch | Every time the disc came to a player: a throw, a stall, a goal caught or a drop. |
| Possession | Receiving the pull, then every time we win the disc back: block, forced or unforced turnover, Callahan. Worked out from the event types, as the recorder does, not from `Event.is_offensive` or the order events load in. |
| Hold / break % | O-line (D-line) points we scored ÷ O-line (D-line) points **that ended in a goal**. A point stopped by the cap or half time is neither (it still counts as a point played). |
| Huck | 20 m+ long and 15 m+ upfield (`throwing.throw_kind`). |
| Break throw | Crosses 3 m+ to the side the mark is stopping; needs the point's force recorded. |
| Full stats | A point with at least one recorded play on the stat taker (a substitution alone isn't one). Per-point rates only count these. |
| A player with no points on a line | Has no O-line (D-line) +/- per point: shown as a dash and left out of teammates' medians and ranks, not counted as 0. |

## What was wrong, what changed, and by how much

Numbers are from the test season in `tests/stats_data.py` (2 tournaments, 6
games, 66 points, 16 players), the closest thing to real data in the repo;
the size of each change on the club's own games depends on how often the
situation comes up, so each row also says what drives it.

| # | What coaches saw | What was wrong | Change on the test season | What drives it on real data |
| --- | --- | --- | --- | --- |
| 1 | **Possessions / goal** (team page) | Only blocks counted as winning the disc back (forced and unforced turnovers and Callahans were missed), and only possessions in points we scored were counted. It could come out below 1, which is impossible. | 0.90 → **1.73** | Every regain that wasn't a block, and every possession in a point we didn't score. |
| 2 | **Possessions gained / D-point** (team and game pages) | Same: blocks only. The game page also counted regains on O points, and divided by Game Day-only D points too. | team 0.13 → **0.37**; one game 0.40 → 0.00 (its regains were all on O points) | Forced/unforced turnovers and Callahans per D point. |
| 3 | **Hold %, break %, clean hold/break %, O/D-line conversion** (team page, game page, dashboard, team radar, trends, each player's line conversion, optimal lines) | A point stopped by the cap or half time, or still being recorded, counted as not held / not broken. | no change (every test point ended in a goal) | Each unfinished O point lowered hold % by about hold% ÷ O points; same for D. |
| 4 | **Goals, blocks, +/-, O/D-line +/-, goals and blocks per point** (dashboard table and leaders, game page table, CSV exports, player API, team goals/blocks per point, team radar blocks per D-point, the public result card, the player page headline) | A Callahan wasn't counted as a goal or a block (the ratings, box score and Game Day did count it). | 4 of 16 players' +/- up by **2**; team goals per point 0.39 → **0.45**; team blocks per D-point 0.13 → **0.27** | +1 goal, +1 block, +2 +/- per Callahan. |
| 5 | **Player page headline** (Goals, Assists, Blocks, Turnovers) | Full-stat points only, next to a Points tile that counts every point; the box score lower down counted every point. | — | Now the season box score (every point), matching the Points tile. |
| 6 | **"Forced Turnovers"** (player page, Defensive tab) | Showed blocks + forced turnovers. | — | Now **Takeaways**: blocks + forced turnovers + Callahans, as in the printable report and dashboard. |
| 7 | **Team completion** (dashboard headline, team page, team radar, team trend) | Drops weren't counted at all, so they never lowered it. | 90.9% → **89.1%** | Drops ÷ passes. |
| 8 | **Drop rate** (player page, focus areas) and **team catch rate** | Pickups counted as receptions, and passes caught just before a goal (retyped as assists) didn't. | team drop rate 2.20% → 2.17%; one player 11.1% → 9.1% | Pickups and assists per player. |
| 9 | **Throwaways, turnovers, completion, turnovers per touch** (every page) | A throwaway recorded as the first play of a point (pull picked up, no pickup tapped) had no stored throw, so it was missing everywhere except the turnover log. | none in the test data | One turnover per such point. |
| 10 | **Hucks, hucks per point** (player page, team metrics, CSV) | Any throw over 20 m in any direction, so a long swing backwards was a huck; huck completion % already used 20 m+ long and 15 m+ upfield. | team hucks per point 0.80 → 0.79 | Long cross-field and backwards throws. |
| 11 | **Per-point rates** (everywhere) | A point with only a substitution recorded counted as a full-stat point with no plays. | none in the test data | One extra point in the divisor per such point. |
| 12 | **O-line / D-line +/- per point** (player ratings card) | A D-line-only player showed O-line +/- of +0.00, was ranked on it, and every such teammate's 0 pulled the median down (and vice versa). | — | Now a dash, left out of the median. |
| 13 | **Game Day completion** (Game Day game, tournament and season pages) | A player's rate was holds ÷ (holds + throwaways), though every throwaway follows a hold already counted, and a stalled player was 100%. The game's team rate was the unweighted average of players' rates. The tournament and season "Completion" was (goals + assists) ÷ (goals + assists + turns), which isn't a completion rate. | worked example: player 50% → 0%, game 90% → 80%, tournament 50% → 80% | Now (catches + pickups − stalls − throwaways) ÷ (catches + pickups − stalls), summed for the team; a dash when only the box score was kept. |
| 14 | **Team summary holds / breaks** (internal, not shown) | Counted either team's holds and breaks. | 44 → 22 holds, 22 → 8 breaks | Not displayed, but now right if used. |
| 15 | **Performance Trends "Break Percentage"** (team page chart) | The share of points broken by either team, drawn next to "D-Line Efficiency" (our break %) as if it were ours. | — | Number unchanged; relabelled "Breaks by either team (% of points)". The other lines are now labelled Hold % and Break %. |
| 16 | **Completion / catch rate with no data** (player page) | Showed 0.0% for a player with no throws (or no passes to them). | — | Now a dash. |

Not changed, but explained on the pages: a player's completion doesn't count
a drop against the thrower (team completion does); the ratings' "blocks" are
blocks and Callahans, not forced turnovers (BBSM's convention; takeaways
include forced turnovers); the team and game pages' O/D-line conversion
rates are hold % and break % (relabelled so they aren't confused with the
base metrics' conversion rate).

### A test changed

`tests/test_stats_dashboard.py::test_plus_minus_is_the_same_everywhere`
checked +/- = goals + assists + blocks − turnovers with Callahans left out.
It now checks the corrected formula, (goals + Callahans) + assists + (blocks
+ Callahans) − turnovers, on the same pages, just as strictly.

### Performance

No extra queries on the dashboard or team pages from the fixes. Measured on
a 24-game season: dashboard 129 queries (unchanged), team page 34 → 32
(the catch-rate query went; the season plan card adds one), game page
45 → 44, player page 411 (unchanged; most of it is the per-game history,
one set of queries per game, which was already the case). The stats cache
still clears on any change to stats data; nothing new is cached.

## Every stat, where it appears, and whether it was correct

✔ correct · ✘ was wrong, fixed (number in the table above) · ✎ label or
explanation fixed.

### Team page (`/stats/team`)

| Stat | Definition | Status |
| --- | --- | --- |
| Games played, record, win % | Games with a result; wins ÷ games played | ✔ |
| Total points played | Every point | ✔ |
| Hold % / O-line points held | O-line points we scored ÷ O-line points that ended in a goal | ✘ 3 ✎ |
| Clean hold % | O-line points scored with no turnover ÷ full-stat O-line points that ended in a goal | ✘ 3 |
| Goals after a turnover ("Regained Possessions") | Points we scored after turning it over (full stats) | ✔ |
| Avg turnovers / O-point | Our turnovers on full-stat O points ÷ those points | ✔ |
| Break % / D-line points broken | D-line points we scored ÷ D-line points that ended in a goal | ✘ 3 ✎ |
| Clean break % | D-line points scored with no turnover of ours ÷ full-stat D points that ended in a goal | ✘ 3 |
| Possessions / goal | Our possessions ÷ goals (full stats) | ✘ 1 |
| Possessions gained / D-point | Regains on D-line points ÷ full-stat D points | ✘ 2 |
| Team radars: hold, break, completion, huck and break-side completion, turnovers / O-point, blocks and takeaways / D-point, "got the disc", "scored after getting it" | As named; percentiles against the team's own tournaments (or games) | ✘ 3, 4, 7 (the rest ✔) |
| Optimal O-/D-line | Players ranked by their line conversion, 5+ points | ✘ 3 |
| Ball security: team completion, turnovers per 10 touches, hucks, break side | `turnovers.handling_summary` | ✘ 7, 9 |
| Breakdown and zone tables, practice focus | Throwing completion by bucket (a drop is the receiver's) | ✔ ✎ |
| What turnovers cost | Our turnovers after which they scored before we got it back, by zone | ✔ |
| Ball security by player | Turnovers per 10 touches, 20+ touches | ✘ 9 |
| Ball security trend | Per game: turnovers / 10 touches, completion, huck completion, break share | ✘ 7 |
| Performance trends | Per game: hold %, break %, breaks by either team | ✘ 3 ✎ 15 |
| Season plan measures (new) | See below | new |

### Dashboard (`/stats/`)

| Stat | Definition | Status |
| --- | --- | --- |
| Headline: hold %, break %, clean holds | As on the team page, vs the season before | ✘ 3 |
| Headline: completion | Team completion | ✘ 7 |
| Headline: turnovers / point | Our turnovers ÷ full-stat points | ✘ 9, 11 |
| Coverage, points that don't add up | Full-stat points of all; points whose possession changes can't produce the result | ✔ |
| Player table: GP, Pts, Full, Pts/G, O % | Usage | ✔ |
| G, A, HA | Goals (with Callahans), assists, hockey assists; per full-stat point | ✘ 4 (G) |
| Cmp % | Player throwing completion | ✔ ✎ |
| Huck % | Huck completion | ✔ |
| TO | Turnovers; per 10 touches in per-point mode | ✘ 9 |
| Blk, Take | Blocks (with Callahans), takeaways; per D-point | ✘ 4 (Blk) |
| Pulls | Game Day pulls; share in bounds | ✔ |
| +/- | Goals + assists + blocks − turnovers, a Callahan +2 | ✘ 4 |
| PER, EPM, Eff | See ratings | ✔ |
| Leaders, line usage | From the table | ✘ 4 (goals, blocks) |
| On the field: scoring and turnover maps, open/break side by zone | Assists thrown and goals caught; turnover spots; break share and completion | ✘ 9 |
| Top throwing pairs | Completions thrower → receiver | ✔ |
| Recent games | Per game hold and break % | ✘ 3 |

### Game page (`/stats/game/<id>`)

| Stat | Definition | Status |
| --- | --- | --- |
| Final score | Game score | ✔ |
| Hold %, break % ("O/D-Line Efficiency") | As above | ✘ 3 ✎ |
| Breaks | D-line points we scored | ✔ |
| Clean hold %, clean break % | As above | ✘ 3 |
| Possessions gained / D-point | As above | ✘ 2 |
| Score progression | Score after each point; turnovers per point (full stats) | ✎ (a Game Day-only point said "Clean point") |
| Point distribution | Holds, broken, breaks, their holds | ✘ 3 |
| Player table | Pts, G, A, HA, Blk, completions (completion %), TO, +/-, PER, EPM, Eff | ✘ 4 |
| Heatmap, connections | Throw starts, goals, throwaways; completed passes | ✔ |

### Player page (`/stats/player/<id>`)

| Stat | Definition | Status |
| --- | --- | --- |
| Headline: games, points, goals, assists, blocks, turnovers | Season box score (every point) | ✘ 5 |
| Season box score, pulls | Full stats where recorded, Game Day otherwise; pulls from Game Day | ✔ |
| Throws, completions, completion rate | Player throwing completion | ✘ 9, 16 ✎ |
| Catches, catch rate | Completed passes caught; ÷ (caught + dropped) | ✔ ✘ 16 ✎ |
| Goals, assists, hockey assists | Goals include Callahans | ✘ 4 |
| Break throws (% of throws) | Break-side throws tried | ✔ |
| Throw distance, directions | Metres per throw; 16-point direction | ✔ |
| O-/D-line points, O-/D-line +/- | Points per line; +/- on that line's points | ✘ 4 |
| Blocks, Callahans, Takeaways ("Forced Turnovers") | Blocks with Callahans; blocks + forced + Callahans | ✘ 4, 6 |
| Profile radars | Percentiles among teammates: completion, goals/assists/hockey assists per point, huck completion, turnovers per 10 touches, blocks/takeaways per D-point, D-line +/- per point, pulls in, hang time | ✘ 4 (goals, blocks), 9 |
| Ratings card: PER, EPM, Eff, O-/D-line +/- per point | Median and rank among teammates with 10+ full-stat points | ✘ 12 |
| Improvement: handling vs team, focus areas, breakdown, zones, directions, turnover log, trends, period comparison, repeat focus | `app/stats/turnovers.py` | ✘ 8, 9 |
| Cutting: cuts from catches, looked-off taps, by type | `app/stats/cutting.py` | ✔ |
| Game history (and CSV) | Box score and ratings per game, each priced by that game's SE | ✘ 4 |

### Ratings page (`/stats/ratings`)

SE, goal equivalents, EPM, PER and Eff were checked against the code and
against a hand-worked game (`test_ratings_by_hand`): all ✔. The page's
"plain plus/minus" in the worked example now uses the site's +/- (with
Callahans), and the new section 9 lists the counting rules.

### Exports and API

Team, game and player-history CSVs, and `/stats/api/player-stats`: the same
numbers as the pages (✘ 4, 10 fixed). The CSVs gain `callahans`,
`completed_break_throws`, `yards_thrown`, `yards_received`, `touches` and
throwaways / drops / turnovers per 10 touches.

### Point page and Game Day

- Point page (`point_replay.py`): possessions, throws, completion, turns, Ds
  won, gain, longest, break throws and hucks (both completed), story. ✔
  (`test_point_replay_by_hand`).
- Game Day pages: box score and +/- per player (a Callahan +2) ✔;
  completion ✘ 13; turnovers per point (Game Day turns ÷ points played in
  the season's games) ✔ for games taken on Game Day.

## Season plan coverage

The plan's "Measuring improvement" team stats, on the team page's **Season
Plan Measures** card (`app/stats/measures.py`) unless noted.

| Plan stat | Status | Where / how |
| --- | --- | --- |
| Turnovers per point | **Already there** | Dashboard headline; also per point we had the disc (new, base metrics). |
| Completion rate | **Already there, fixed** (✘ 7) | Team completion counts drops as incomplete passes. |
| Breaks thrown | **Already there**, completed breaks **added** | Break throws tried and completed, team and player. Needs each point's force recorded (`Point.force_direction`); the card says how many throws had one. |
| Discs received by opponents by zone (break / reset / open) | **Needs new recording** | The stat taker records only the opponent's turnovers, not their passes. Recording each opponent completion with its start and end (as ours are) would give it: the break / open side from the force, and a reset as a dump or swing (`throw_kind`). |
| Offensive yardage | **Added** | Team metres upfield on completed passes (and per point); per player yards thrown and caught (player table on the card, CSVs). |
| Turnovers per touch, throwaways and drops separately | **Added** (touches were already there) | Throwaways, drops and all turnovers per 10 touches, per player. |
| Completed breaks (per player) | **Added** | Player table on the card, CSVs. |
| No-turn goals | **Added** | O-line, D-line and overall. |
| Breaks | **Already there** | Break count and break %; also on the card. |
| Conversion rate | **Added** | Goals ÷ points we had the disc. On O-line it equals hold %. |
| Perfect conversion rate | **Added** (the O-line one was already there as clean hold %) | No-turn goals ÷ points we had the disc. |
| Recovery rate | **Added** | Goals after a turnover ÷ (points we had the disc − no-turn goals). |
| Successful-defence rate | **Added** (was already on the team radar as "Got the disc", full-stat points only) | D points where we got the disc ÷ D points. |

The base metrics use only the four things the plan says a sideliner records
(score, O/D start, blocks, turnovers), so they count points only taken live
on Game Day too: on a Game Day-only D point we had the disc if we scored,
blocked, caught a Callahan or turned it over. They count points that ended
in a goal. Definitions follow Ultiworld's "Basic Team Analysis Using Four
Metrics" (Spin Ultimate, 2016), the basis of the Base Metric Analysis the
plan cites.

The "filmed games" stats (per-player turnovers per touch, completed breaks,
yardage) come from the full stat taker, which is how filmed games are
recorded; nothing extra is needed.

## Still open

- Opponents' passes (above) are the one plan stat that needs new recording.
- The player page runs one set of queries per game for the game history
  (about 400 queries for a 24-game season). It isn't a regression, but it's
  the next place to batch if the page gets slow.
- Points' O/D are read from `starting_position` for possessions and from
  `our_line_type` for line stats; the point form sets both, and they agree
  in all recorded data, so this was left alone.
