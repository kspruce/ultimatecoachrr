"""Builds programme.csv and tests.csv for the Thundering Herd 2027/28 S&C
programme (four tracks: Home strength, Gym, Throwing, Speed).

Every track runs weeks 1-51, so programme week N is season-plan week N
(week 1 starts Monday 4 October 2027). The season calendar it follows
(events, trials, peak and taper) is in imports/season-plan-export/.

Run it from the repository root to rebuild the two CSV files after changing
a progression here:

    python imports/programmes/thundering-herd-2027-28/build_programme.py

If you edit the CSV files by hand or in the app instead, they are the
master copy and this script is only a record of how they were first built.
"""
import csv, os, re, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else 'imports/programmes/thundering-herd-2027-28'
COLS = ['track', 'track_first_week', 'track_start_offset', 'week', 'week_title', 'week_type', 'week_objective',
        'week_skills', 'session', 'session_type', 'requirement', 'alternative_group', 'session_minutes',
        'session_focus', 'warmup', 'cooldown', 'coaching_cues', 'session_video', 'log_fields',
        'exercise', 'block', 'sets', 'reps', 'distance_m', 'duration_s', 'rest', 'intensity', 'tempo',
        'instructions', 'exercise_video']
ROWS = []

EVENTS = {23: 'Solent warm-up', 26: 'UKU Tour 1', 29: 'Herdlodge', 30: 'EUCS Spring (1s only)',
          31: 'UKU Tour 2', 37: 'UKU Tour 3', 42: 'UKU Regionals', 43: 'EUCS Summer (1s only)',
          49: 'UKU Nationals (1s)'}
ONES_ONLY = {30, 43, 49}


def phase(n):
    if n <= 11: return 1
    if n <= 13: return 0
    if n <= 24: return 2
    if n <= 37: return 3
    if n <= 43: return 4
    return 5


def ex(name, sets='', reps='', block='', dist='', dur='', rest='', intensity='', tempo='', note='', video=''):
    return dict(exercise=name, block=block, sets=str(sets), reps=str(reps), distance_m=str(dist), duration_s=str(dur),
                rest=rest, intensity=intensity, tempo=tempo, instructions=note, exercise_video=video)


def sess(title, stype, minutes, exercises=(), req='required', group='', focus='', warmup='', cooldown='', cues='',
         video='', log='duration_minutes, rpe'):
    return dict(session=title, session_type=stype, requirement=req, alternative_group=group,
                session_minutes=str(minutes), session_focus=focus, warmup=warmup, cooldown=cooldown,
                coaching_cues=cues, session_video=video, log_fields=log, exercises=list(exercises))


def week(track, n, title, sessions=(), kind='', objective='', skills=''):
    base = dict(track=track, track_first_week='1', track_start_offset='0', week=str(n))
    wk = dict(week_title=title, week_type=kind, week_objective=objective, week_skills=skills)
    if not sessions:
        ROWS.append({**base, **wk})
        return
    first_week_row = True
    for s in sessions:
        exs = s['exercises'] or [None]
        meta = {k: v for k, v in s.items() if k != 'exercises'}
        for i, e in enumerate(exs):
            row = dict(base)
            row['session'] = s['session']
            if first_week_row:
                row.update(wk)
                first_week_row = False
            if i == 0:
                row.update(meta)
            if e:
                row.update(e)
            ROWS.append(row)


# ==========================================================================
# Home strength
# ==========================================================================
HS = 'Home strength'
HS_WARM = ('3 minutes: 10 leg swings each way, 10 hip circles, 10 slow squats, 5 walk-outs to a push-up position, '
           '20 seconds of fast feet.')
HS_COOL = '2 minutes: calf, hip-flexor and hamstring stretches, 30 seconds each side.'
A_DAY = ('Your hard leg day at home. Do it on the day furthest from both training sessions, and never the day '
         'before training or an event.')
B_DAY = ('The lighter session. Any day that is not the day before training or an event; leave a clear day after '
         'session A if you can.')
JUMP_RULE = 'Jumps come first, while you are fresh. Rest 45-60 s between sets. Stop a set when jumps get lower or landings get noisy.'
A_CUES = 'Land quietly: knees over toes, chest up, hips back. Slow on the way down, strong on the way up. Quality before reps.'
B_CUES = 'Hips level on single-leg work. Long spine when you hinge. Lower slowly on hamstring work and stop before form goes.'
LOG_HS = 'duration_minutes, rpe, soreness'


def contacts(jumps):
    total = 0
    for j in jumps:
        sets = int(re.match(r'\d+', j['sets']).group())
        reps = int(re.match(r'\d+', j['reps']).group())
        total += sets * reps * (2 if 'per' in j['reps'] else 1)
    return total


def J(name, sets, reps, note):
    return ex(name, sets, reps, block='Jumps', rest='45-60 s', note=note)


POGO = lambda s, r: J('Pogo hops', s, r, 'Small, fast bounces on the balls of your feet with stiff ankles and almost straight knees. Short ground contact.')
SJ_STICK = lambda s, r: J('Squat jump and stick', s, r, 'Jump from a quarter squat, land on two feet and freeze for 2 s.')
BROAD_STICK = lambda s, r: J('Broad jump and stick', s, r, 'Jump forwards off two feet, land softly and freeze for 2 s. Walk back.')
SKATER_STICK = lambda s, r: J('Skater bound and stick', s, f'{r} per side', 'Bound sideways from one leg to the other and freeze for 1 s on each landing: the push of a cut.')
CMJ = lambda s, r: J('Countermovement jumps, continuous', s, r, 'Dip and jump as high as you can, land and go again straight away.')
BROAD_CONT = lambda s, r: J('Broad jumps, continuous', s, r, 'Link the jumps together: land, then jump again without a pause.')
SKATER = lambda s, r: J('Skater bounds, continuous', s, f'{r} per side', 'Side to side without a pause, pushing hard off the outside leg.')
SL_HOP = lambda s, r: J('Single-leg forward hops', s, f'{r} per leg', 'Hop forwards on one leg, short and quick. Stick the last landing for 2 s.')
TUCK = lambda s, r: J('Tuck jumps', s, r, 'Jump and bring your knees up, land softly and go again. Stay tall.')
DROP = lambda s, r: J('Drop jump from a low step', s, r, 'Step off a 20-30 cm step, land and jump straight up as fast as you can. Spend as little time on the ground as possible.')

JUMPS = {
    40: [POGO(2, 10), SJ_STICK(2, 5), BROAD_STICK(2, 5)],
    48: [POGO(2, 12), SJ_STICK(2, 6), SKATER_STICK(2, 3)],
    56: [POGO(2, 12), CMJ(2, 6), BROAD_STICK(2, 4), SKATER_STICK(2, 3)],
    60: [POGO(2, 12), CMJ(2, 6), BROAD_STICK(2, 6), SKATER_STICK(2, 3)],
    64: [POGO(2, 12), CMJ(2, 6), BROAD_CONT(2, 4), SKATER(2, 5)],
    70: [POGO(2, 15), CMJ(2, 6), BROAD_CONT(2, 4), SKATER(2, 5)],
    76: [POGO(2, 15), CMJ(2, 6), BROAD_CONT(2, 4), SKATER(2, 5), SL_HOP(1, 3)],
    80: [POGO(2, 15), TUCK(2, 5), BROAD_CONT(2, 5), SKATER(2, 5), SL_HOP(1, 5)],
    84: [POGO(2, 15), TUCK(2, 5), BROAD_CONT(2, 5), SKATER(2, 5), SL_HOP(1, 7)],
    90: [POGO(2, 15), TUCK(2, 6), BROAD_CONT(2, 5), SKATER(2, 6), SL_HOP(1, 7)],
    96: [POGO(2, 15), TUCK(2, 6), BROAD_CONT(2, 6), SKATER(2, 6), SL_HOP(1, 9)],
    100: [POGO(2, 15), TUCK(2, 6), BROAD_CONT(2, 6), SKATER(2, 6), SL_HOP(1, 8), DROP(1, 6)],
    26: [POGO(2, 10), SJ_STICK(2, 3)],
    20: [POGO(2, 10)],
    "taper40": [POGO(2, 10), TUCK(2, 4), BROAD_CONT(2, 3), SKATER(1, 3)],
}
for key, js in JUMPS.items():
    want = 40 if key == 'taper40' else key
    assert contacts(js) == want, (key, contacts(js))

LAND = {
    1: [ex('Snap-down and stick', 2, 5, block='Landings', note='From tall on your toes, drop fast into a quarter squat and freeze for 2 s. Quiet feet, knees over toes, chest up.'),
        ex('Step-off landing', 2, 5, block='Landings', note='Step off the bottom stair, land on two feet and freeze for 2 s.')],
    2: [ex('Jump and stick', 2, 5, block='Landings', note='A small jump straight up. Land on two feet and freeze for 2 s.'),
        ex('Single-leg step-off landing', 2, '4 per leg', block='Landings', note='Step off the bottom stair and land on one leg. Freeze for 2 s with the knee over the toes.')],
    3: [ex('Broad jump and stick', 2, 4, block='Landings', note='Jump forwards off two feet, land softly and freeze for 2 s.'),
        ex('Single-leg hop and stick', 2, '4 per leg', block='Landings', note='A short hop forwards on one leg. Freeze for 2 s before the next one.')],
}

# Strength blocks by level: (A exercises, B exercises)
def strength(level, sets):
    s = sets
    if level == 1:
        a = [ex('Bodyweight squat', s, 12, 'A1', tempo='3-1-1', note='Sit down between your heels. Knees track over toes; whole foot on the floor.'),
             ex('Split squat', s, '8 per leg', 'A2', tempo='2-1-1', note='Tall body, front knee over the middle of the foot. Push through the whole front foot.'),
             ex('Push-up', s, '8-12', 'B1', note='Hands on a chair or step if you can\'t reach 8 on the floor. Body in one line.'),
             ex('Side plank', 2, '', 'B2', dur=20, note='Each side. Elbow under shoulder, hips high.'),
             ex('Single-leg balance', 2, '', 'C', dur=30, note='Each leg, on your pivot foot first. Eyes forward, then turn your head from side to side.')]
        b = [ex('Hip hinge (good morning)', s, 12, 'A1', tempo='2-1-1', note='Hands on hips, soft knees. Push your hips back with a long spine until you feel your hamstrings.'),
             ex('Glute bridge', s, 12, 'A2', note='Squeeze for 2 s at the top. Ribs down.'),
             ex('Reverse lunge', s, '8 per leg', 'B1', note='Step back and lower under control. Tall body.'),
             ex('Copenhagen side plank, short lever', 2, '', 'B2', dur=15, note='Each side. Top knee on a chair, bottom leg hanging. Lift your hips. This protects the groin.'),
             ex('Calf raise', s, 15, 'C1', tempo='2-1-2', note='Two legs, on the edge of a step. All the way up, all the way down.'),
             ex('Dead bug', 2, '8 per side', 'C2', note='Lower back stays on the floor. Opposite arm and leg, slowly.'),
             ex('Single-leg balance with reach', 2, '5 reaches per leg', 'D', note='Stand on one leg and reach the other foot to the points of a clock.')]
    elif level == 2:
        a = [ex('Tempo squat', s, 10, 'A1', tempo='4-1-1', note='Four seconds down, pause, stand up fast.'),
             ex('Rear-foot-elevated split squat', s, '8 per leg', 'A2', tempo='2-1-1', note='Back foot on a chair or sofa. Hips level, front knee over the foot.'),
             ex('Push-up', s, '10-15', 'B1', note='Raise your feet if 15 is easy.'),
             ex('Side plank with top-leg lift', 2, '', 'B2', dur=20, note='Each side. Lift and lower the top leg slowly.'),
             ex('Single-leg balance, eyes closed', 2, '', 'C', dur=20, note='Each leg. Stand near a wall.')]
        b = [ex('Single-leg Romanian deadlift', s, '8 per leg', 'A1', tempo='2-0-2', note='Hips level, hinge from the hip, long spine. Touch a wall for balance if you need to.'),
             ex('Single-leg glute bridge', s, '8 per leg', 'A2', note='Hips level; squeeze for 2 s at the top.'),
             ex('Lateral lunge', s, '8 per side', 'B1', note='Sit back into the bent leg; the other leg stays straight. Push back hard: this is your change of direction.'),
             ex('Copenhagen side plank, short lever', 2, '', 'B2', dur=20, note='Each side.'),
             ex('Single-leg calf raise', s, '10 per leg', 'C1', tempo='2-1-2', note='On a step. Hold a wall lightly.'),
             ex('Hamstring walk-out', 2, 5, 'C2', note='From a glute bridge, walk your heels out until your legs are nearly straight, then walk back. Hips stay up.'),
             ex('Dead bug, straight legs', 2, '10 per side', 'D', note='Lower back stays on the floor.')]
    elif level == 3:
        a = [ex('Squat with a loaded backpack', s, 10, 'A1', intensity='RPE 7', tempo='3-1-1', note='Books or water bottles in a backpack, hugged to your chest. Add load when 10 is easy.'),
             ex('Rear-foot-elevated split squat with backpack', s, '8 per leg', 'A2', intensity='RPE 7', tempo='2-1-1', note='Hips level; control the bottom.'),
             ex('Push-up', s, 'Stop 2 short of failure', 'B1', note='Feet raised, or a backpack on, if you pass 15.'),
             ex('Plank shoulder taps', 2, '10 per side', 'B2', note='Feet wide. Hips stay still as you tap.'),
             ex('Single-leg balance with a disc', 2, '', 'C', dur=30, note='Each leg. Flip a disc up and catch it, or fake throws, without putting the other foot down.')]
        b = [ex('Single-leg Romanian deadlift with backpack', s, '8 per leg', 'A1', intensity='RPE 7', tempo='2-0-2', note='Hold the backpack in the opposite hand to the standing leg.'),
             ex('Hamstring walk-out', s, 5, 'A2', note='Slow on the way out.'),
             ex('Cossack squat', s, '6 per side', 'B1', note='A deep lateral lunge, as low as you can keep the heel down.'),
             ex('Copenhagen side plank, long lever', 2, '', 'B2', dur=15, note='Each side. Top foot on the chair, leg straight. Go back to the knee version if your groin complains.'),
             ex('Single-leg calf raise', s, '12 per leg', 'C1', tempo='2-1-3', note='Three seconds down.'),
             ex('Nordic lower, assisted', 2, 3, 'C2', note='Kneel with your feet hooked under a sofa. Lower your body forwards as slowly as you can, catch yourself with your hands and push back up.'),
             ex('Side plank with rotation', 2, '8 per side', 'D', note='Thread the top arm under your body and back.')]
    elif level == 4:
        a = [ex('Squat with a loaded backpack', s, 8, 'A1', intensity='RPE 7-8', tempo='3-1-X', note='Slow down, fast up. Heavier than before Christmas.'),
             ex('Rear-foot-elevated split squat with backpack', s, '8 per leg', 'A2', intensity='RPE 7-8', tempo='2-1-X', note='Drive up fast.'),
             ex('Push-up, hard version', s, '8-12', 'B1', note='Feet raised, backpack on, or a slow 3 s lower.'),
             ex('Side plank with top-leg lift', 2, '', 'B2', dur=25, note='Each side.'),
             ex('Pivot-foot balance and fakes', 2, '10 fakes per leg', 'C', note='Stand on your pivot foot only and make ten full, real-looking fakes with a disc.')]
        b = [ex('Single-leg Romanian deadlift with backpack', s, '8 per leg', 'A1', intensity='RPE 7-8', tempo='2-0-2', note='Add load before reps.'),
             ex('Nordic lower, assisted', s, '3-4', 'A2', note='As slow as you can for as far as you can. Never the day before training.'),
             ex('Lateral lunge to single-leg stand', s, '6 per side', 'B1', note='Push out of the lunge hard and finish balanced on the pushing leg.'),
             ex('Copenhagen side plank, long lever', 2, '', 'B2', dur=20, note='Each side.'),
             ex('Single-leg calf raise', s, '12 per leg', 'C1', tempo='2-1-3'),
             ex('Bent-knee calf raise', 2, 12, 'C2', note='Knees bent about 30 degrees, two legs. This loads the lower calf.'),
             ex('Dead bug, straight legs', 2, '10 per side', 'D')]
    elif level == 5:  # in season
        a = [ex('Single-leg squat to a chair', s, '6 per leg', 'A1', tempo='3-1-X', note='Sit back to a chair on one leg and stand up without rocking. Use a lower chair as it gets easy.'),
             ex('Split squat with backpack', s, '8 per leg', 'A2', intensity='RPE 7', tempo='2-1-X'),
             ex('Push-up', s, 'Stop 2 short of failure', 'B1'),
             ex('Side plank', 2, '', 'B2', dur=30, note='Each side.'),
             ex('Pivot-foot balance and fakes', 2, '10 fakes per leg', 'C', note='On your pivot foot only: ten full fakes with a disc.')]
        b = [ex('Single-leg Romanian deadlift with backpack', s, '8 per leg', 'A1', intensity='RPE 7', tempo='2-0-2'),
             ex('Nordic lower, assisted', s, 4, 'A2', note='Keeping these in all season protects your hamstrings. At least two days before training or an event.'),
             ex('Copenhagen side plank, long lever', 2, '', 'B1', dur=20, note='Each side.'),
             ex('Lateral lunge', s, '6 per side', 'B2', note='Push back hard.'),
             ex('Single-leg calf raise', s, '12 per leg', 'C1', tempo='2-1-3'),
             ex('Dead bug, straight legs', 2, '10 per side', 'C2')]
    else:  # 7: peak
        a = [ex('Single-leg squat to a chair', s, '5 per leg', 'A1', tempo='2-1-X', note='Few reps, perfect and fast on the way up.'),
             ex('Push-up', s, 10, 'B1', note='Fast and clean.'),
             ex('Side plank', 2, '', 'B2', dur=30, note='Each side.')]
        b = [ex('Single-leg Romanian deadlift with backpack', s, '6 per leg', 'A1', tempo='2-0-2'),
             ex('Nordic lower, assisted', s, 3, 'A2', note='At least three days before the rehearsal game or Nationals.'),
             ex('Copenhagen side plank, long lever', 2, '', 'B1', dur=15, note='Each side.'),
             ex('Single-leg calf raise', s, '10 per leg', 'C1', tempo='2-1-2')]
    return a, b


def primer(n_contacts=26):
    return [*JUMPS[n_contacts],
            ex('Bodyweight squat', 1, 10, 'A1', note='Smooth and fast.'),
            ex('Split squat', 1, '6 per leg', 'A2'),
            ex('Push-up', 1, 10, 'B1'),
            ex('Single-leg Romanian deadlift', 1, '6 per leg', 'B2'),
            ex('Copenhagen side plank, short lever', 1, '', 'C1', dur=15, note='Each side.'),
            ex('Calf raise', 1, 12, 'C2')]


HS_PLAN = {}  # week -> (title, kind, objective, level, sets, jumps key or None, mode)
def hs_normal(weeks, title, objective, level, sets, jumps=None, land=None, skills=''):
    for n in weeks:
        HS_PLAN[n] = dict(mode='normal', title=title, objective=objective, level=level, sets=sets,
                          jumps=jumps.get(n) if isinstance(jumps, dict) else jumps, land=land, skills=skills)

hs_normal(range(1, 5), 'Foundation 1: learn the positions', 'Learn to squat, hinge, lunge and land well before adding anything. Two sessions of 20-25 minutes.', 1, 3, land=1,
          skills='Knees over toes; quiet landings held for 2 s; hips level on one leg.')
hs_normal(range(5, 9), 'Foundation 2: single-leg control', 'Move the work onto one leg, because cutting and jumping happen on one leg. Landings go to one leg too.', 2, 3, land=2,
          skills='Slow lowering; single-leg landings with the knee over the toes.')
hs_normal(range(9, 12), 'Foundation 3: add load', 'Load the same movements with a backpack and jump forwards into a held landing. This is the base the January jumps are built on.', 3, 3, land=3,
          skills='RPE 7: two or three reps left at the end of each set.')
hs_normal([14, 15, 16, 17, 19, 20, 21, 22], 'Strength and first jumps', 'General strength peaks before the season starts, and plyometrics begin: about 40 ground contacts in session A, building to about 60.', 4, 3,
          jumps={14: 40, 15: 40, 16: 48, 17: 48, 19: 40, 20: 40, 21: 56, 22: 60},
          skills='Jumps first while fresh; stop when they get lower. Fast up on strength work.')
hs_normal([24, 25, 27, 28, 32, 33, 34, 35, 36, 38, 39, 40, 41], 'Power in season', 'Hold strength with two sets and keep building jumps towards 100 contacts. Events and training come first: these sessions stay short.', 5, 2,
          jumps={24: 64, 25: 70, 27: 70, 28: 76, 32: 80, 33: 84, 34: 90, 35: 80, 36: 90, 38: 90, 39: 96, 40: 100, 41: 60},
          skills='Two sets, full effort. Jumps are springy and fast, not tiring.')
hs_normal([45, 46, 47], 'Peak for Nationals', 'The highest-quality jump work of the year, with very little strength volume. Legs should feel springy, not heavy.', 7, 2,
          jumps={45: 80, 46: 100, 47: 100}, skills='Maximum intent on every jump; long rests.')

HS_NOTES = {
    19: 'Trial 2 this week: keep these two sessions at least two days away from the trial.',
    20: 'Trial 3 this week: keep these two sessions at least two days away from the trial.',
    35: 'Mid-season skill tests this week: jump volume holds at 80 so you arrive fresh.',
    41: 'Rehearsal week before Regionals: jump volume drops to 60 and nothing new is added.',
    45: '2s: your step-up camp starts this week. Follow the same sessions.',
    47: 'Do session A at least two days before the rehearsal game. This is the last hard leg session before Nationals.',
}

for n in range(1, 52):
    ev = EVENTS.get(n)
    if n in HS_PLAN:
        p = HS_PLAN[n]
        a, b = strength(p['level'], p['sets'])
        if p['jumps']:
            lead = JUMPS[p['jumps']]
            c = contacts(lead)
            a_focus = f'{A_DAY} {JUMP_RULE} Jump contacts this session: {c}.'
        else:
            lead = LAND[p['land']]
            a_focus = f'{A_DAY} Landings come first: every landing is held still for 2 s. These are practice for the jumps that start in January.'
        b_focus = B_DAY
        if n in HS_NOTES:
            a_focus += ' ' + HS_NOTES[n]
        week(HS, n, p['title'], [
            sess('Home strength A: legs and landings', 'strength', 25, lead + a, focus=a_focus, warmup=HS_WARM,
                 cooldown=HS_COOL, cues=A_CUES, log=LOG_HS),
            sess('Home strength B: hips, hamstrings and trunk', 'strength', 20, b, focus=b_focus, warmup=HS_WARM,
                 cooldown=HS_COOL, cues=B_CUES, log=LOG_HS),
        ], objective=p['objective'], skills=p['skills'])
    elif n in (12, 13):
        week(HS, n, 'Christmas break: tick over', [
            sess('Home strength: tick over', 'strength', 15, [
                ex('Bodyweight squat', 2, 12, note='Circuit: one set of each exercise, then repeat.'),
                ex('Reverse lunge', 2, '8 per leg'), ex('Push-up', 2, 10), ex('Glute bridge', 2, 12),
                ex('Side plank', 2, '', dur=20, note='Each side.'), ex('Calf raise', 2, 15),
                ex('Single-leg balance', 2, '', dur=30, note='Each leg.')],
                req='optional', focus='One easy circuit a week over the break. No jumps. Any day.', warmup=HS_WARM, cooldown=HS_COOL, log=LOG_HS)],
            kind='deload', objective='Keep the habit going without adding load. The jumps start in January.')
    elif n == 18:
        week(HS, n, 'Deload: Trial 1 and the skill tests', [
            sess('Home strength: primer', 'strength', 15, primer(26),
                 focus='One short session early in the week, at least three days before Trial 1 (skill tests, the 50 m sprint and agility tests). Jump contacts: 26.',
                 warmup=HS_WARM, cooldown=HS_COOL, cues='Everything fast and easy. You should finish feeling better than when you started.', log=LOG_HS)],
            kind='deload', objective='Arrive at the trial tests fresh.')
    elif n == 44:
        week(HS, n, 'Recovery week', [
            sess('Recovery: mobility and easy strength', 'recovery', 15, [
                ex('Hip and ankle mobility flow', 1, '', dur=240, note='Deep squat hold, hip-flexor stretch, ankle rocks, thoracic rotations.'),
                ex('Glute bridge', 2, 12), ex('Calf raise', 2, 12, tempo='2-1-2'), ex('Side plank', 2, '', dur=20, note='Each side.'),
                ex('Single-leg balance', 2, '', dur=30, note='Each leg.')],
                req='optional', focus='After Regionals and EUCS: no jumps, nothing hard. Tell a captain about any niggle now, so it can be managed through the peak.',
                log=LOG_HS)],
            kind='deload', objective='Rest legs and heads after two big weekends. Recovery is what makes the peak possible.')
    elif n == 48:
        week(HS, n, 'Taper', [
            sess('Home strength: taper primer', 'strength', 15, [*JUMPS['taper40'], ex('Single-leg squat to a chair', 1, '5 per leg', 'A1'),
                                                           ex('Push-up', 1, 10, 'B1'), ex('Copenhagen side plank, short lever', 1, '', 'C1', dur=15, note='Each side.'),
                                                           ex('Calf raise', 1, 12, 'C2')],
                 focus='One session, early in the week. Cut the volume, keep the speed: 40 fast jump contacts with long rests. 2s: no taper needed, so repeat week 47 instead if you want to keep building through the step-up camp.',
                 warmup=HS_WARM, cooldown=HS_COOL, cues='Fast and fresh. Feeling a bit flat early in a taper is normal.', log=LOG_HS)],
            kind='deload', objective='Arrive at Nationals fresh and sharp. Sleep, food and water matter more this week than extra training.')
    elif n == 49:
        week(HS, n, 'Nationals week', [
            sess('Home strength: Nationals primer', 'strength', 10, [*JUMPS[20], ex('Bodyweight squat', 1, 8, 'A1', note='Fast.'),
                                                              ex('Hip and ankle mobility flow', 1, '', 'B', dur=180)],
                 focus='Monday or Tuesday only. 20 pogo hops, a few squats and mobility. 2s: repeat week 47 instead, or rest.',
                 warmup=HS_WARM, log=LOG_HS)],
            kind='deload', objective='Nothing that could leave you sore. The work is done.')
    elif n == 50:
        week(HS, n, 'Rest', kind='rest', objective='No sessions. Rest after the season.')
    elif n == 51:
        a, b = strength(1, 2)
        week(HS, n, 'Off-season restart', [
            sess('Home strength: easy restart', 'strength', 20, LAND[1] + a, req='optional',
                 focus='The season ends with low-intensity training two or three times a week, not a full stop. This is week 1\'s session A with two sets.',
                 warmup=HS_WARM, cooldown=HS_COOL, cues=A_CUES, log=LOG_HS)],
            kind='deload', objective='Keep moving through the off-season: one or two months of easy training, then next season\'s programme.')
    else:  # event deload weeks
        extra = []
        if n in ONES_ONLY:
            extra = [sess('Not playing this weekend? Repeat last full week', 'strength', 25, req='optional',
                          focus='2s and anyone not at the event: repeat the Home strength A and B sessions from the last full training week instead of deloading.',
                          log=LOG_HS)]
        week(HS, n, f'Deload: {ev}', [
            sess('Home strength: primer', 'strength', 15, primer(26),
                 focus=f'{ev} this weekend. One short session early in the week, at least three days before the first game. Jump contacts: 26.',
                 warmup=HS_WARM, cooldown=HS_COOL, cues='Everything fast and easy. You should finish feeling better than when you started.', log=LOG_HS),
            *extra], kind='deload', objective=f'Arrive fresh for {ev}. No session in the two days before or the day after.')

# ==========================================================================
# Gym (optional)
# ==========================================================================
GYM = 'Gym'
GYM_WARM = '8-10 minutes: easy bike or row, leg swings, hip openers, then two light warm-up sets of the first lift.'
GYM_RULE = ('Optional, for players with gym access. It replaces the strength block of Home strength A that week: do '
            'that session\'s jumps as part of your warm-up, lift here, and log both. Never the day before training or an event.')
GYM_CUES = 'Train for intensity, not volume. Leave one or two reps in the tank; full rest before heavy or fast sets. Technique first, load second.'


def acc(rounds, reps, rpe, note=''):
    r = reps
    return sess('Gym: accessory and stability', 'strength', 45, [
        ex('Reverse lunge', rounds, f'{r} per side', '1', intensity=rpe, tempo='2-0-2', note='Tall torso; front knee over mid-foot; push through the full foot.'),
        ex('Single-leg Romanian deadlift', rounds, f'{r} per side', '2', intensity=rpe, tempo='2-0-2', note='Hips level; hinge from the hip; long spine.'),
        ex('Lateral box step-up', rounds, f'{r} per side', '3', intensity=rpe, tempo='2-0-2', note='Level hips; control the step down; don\'t push off the trailing leg.'),
        ex('Alternating dumbbell chest press', rounds, f'{r} per arm', '4', intensity=rpe, tempo='2-0-2'),
        ex('Bent-over single-arm row', rounds, f'{r} per arm', '5', intensity=rpe, tempo='2-0-2', note='Row to the pocket without shrugging.'),
        ex('Single-leg medicine ball throw and catch', rounds, '5 per side', '6', tempo='Explosive', note='No medicine ball: Pallof press, 8-10 per side.'),
    ], req='optional', focus=f'Circuit: one set of each exercise in order, {rounds} rounds. 15-30 s between exercises, 2-3 min between rounds. Best for players newer to lifting. {note}'.strip(),
        warmup=GYM_WARM, cues=GYM_CUES)


def snp(squat, jump, hinge, bench, chin, minutes=60, note='', title='Gym: strength and power'):
    exs = [ex('Barbell box squat', squat[0], squat[1], 'A1', rest='60-90 s to A2', intensity=squat[2], tempo=squat[3]),
           ex(jump[0], jump[1], jump[2], 'A2', rest='2-3 min, then repeat A1/A2', tempo='Explosive', note=jump[3] if len(jump) > 3 else '')]
    for h in hinge:
        exs.append(ex(h[0], h[1], h[2], h[3], rest='60-90 s', intensity=h[4], tempo=h[5]))
    exs.append(ex('Bench press', bench[0], bench[1], 'C1', rest='60-90 s to C2', intensity=bench[2], tempo='2-1-X'))
    exs.append(ex('Chin-up', chin[0], chin[1], 'C2', rest='60-90 s, then back to C1', intensity=chin[2], tempo='Controlled'))
    return sess(title, 'strength', minutes, exs, req='optional',
                focus=f'For experienced lifters. Pair A1 with A2 and C1 with C2. {note}'.strip(), warmup=GYM_WARM, cues=GYM_CUES)


CORE = {
    1: [('Plank', 30), ('Side plank right', 30), ('Side plank left', 30), ('Back extension', 30), ('Swiss ball rotation (each side)', 30)],
    2: [('Plank', 30), ('Side plank right', 30), ('Side plank left', 30), ('Pallof press right', 30), ('Pallof press left', 30), ('Landmine rotation (each side)', 30)],
    3: [('Plank', 40), ('Side plank right', 40), ('Side plank left', 40), ('Back extension', 40), ('Russian twists', 40)],
}
def core(i):
    return sess(f'Core workout {i}', 'strength', 15, [ex(name, 2, '', dur=d, rest='15 s') for name, d in CORE[i]], req='optional',
                focus='Circuit, 2 rounds. 15 s between moves, 60 s after the last. Brace and breathe behind the brace.', log='duration_minutes')

KB = lambda sets, reps, how='': ('Kettlebell swings', sets, reps, 'B', how, 'Explosive')
RDL = lambda sets, reps, rpe: ('Romanian deadlift', sets, reps, 'B2', rpe, '3-1-1')

def gym_week(n):
    ev = EVENTS.get(n)
    c = [core((n - 1) % 3 + 1)] if n <= 24 and n not in (12, 13, 18, 23) else []
    if 1 <= n <= 6:
        return ('Off-season 1: volume and quality', '', 'Build work capacity and clean technique. Pick one gym session a week; experienced lifters can do both on different days.',
                [acc(3, 12, 'RPE 7'), snp((4, 6, 'RPE 6-7', '3-1-X'), ('Split squat jumping lunge', 3, '5 per leg'), [KB(3, 12)], (4, 6, 'RPE 6-7'), (4, 'AMRAP', 'Leave 2 in reserve'), note='Learn the lifts at a load you could do for 3 more reps.'), *c])
    if 7 <= n <= 11:
        return ('Off-season 2: build strength', '', 'Same movements, heavier. Add a Romanian deadlift so the hamstrings get loaded as well as the quads.',
                [acc(3, 10, 'RPE 7-8', 'Heavier than weeks 1-6 with perfect form.'), snp((4, 5, 'RPE 7', '3-1-X'), ('Split squat jumping lunge', 3, '6 per leg'), [KB(3, 12), RDL(3, 8, 'RPE 7')], (4, 5, 'RPE 7'), (4, 'AMRAP', 'Leave 1-2 in reserve')), *c])
    if n in (12, 13):
        return ('Christmas break: tick over', 'deload', 'One easy session if the gym is open. Two sets, nothing heavy.',
                [snp((2, 5, 'RPE 6', '3-1-X'), ('Squat jump', 2, 4), [KB(2, 10)], (2, 5, 'RPE 6'), (2, '5', 'Easy'), minutes=35, title='Gym: tick over', note='Two sets of everything.')])
    if 14 <= n <= 17:
        return ('Pre-season 1: maximum strength', '', 'The heaviest block of the year, before the season starts. Fewer reps, more load, long rests.',
                [acc(3, 8, 'RPE 8'), snp((4, 4, 'RPE 8', '3-1-X'), ('Box jump', 3, 4, 'Step down, don\'t jump down.'), [RDL(3, 6, 'RPE 7-8')], (4, 4, 'RPE 8'), (4, 'AMRAP, or 4 with added load', 'Leave 1 in reserve')), *c])
    if n == 18:
        return ('Deload: Trial 1 and the skill tests', 'deload', 'One light, fast session early in the week, or none.',
                [snp((2, 3, 'RPE 6', '2-1-X'), ('Box jump', 2, 3), [KB(2, 8)], (2, 3, 'RPE 6'), (2, 5, 'Easy'), minutes=30, title='Gym: primer', note='At least three days before Trial 1. Everything fast and easy.')])
    if n in (19, 20):
        return ('Pre-season 1: hold through trials', '', 'Hold strength with less volume while trials are on. At least two days before the trial.',
                [acc(2, 8, 'RPE 7'), snp((3, 4, 'RPE 7', '3-1-X'), ('Box jump', 3, 3), [RDL(2, 6, 'RPE 7')], (3, 4, 'RPE 7'), (3, 'AMRAP', 'Leave 2 in reserve'), minutes=50), *c])
    if 21 <= n <= 24 and n != 23:
        return ('Pre-season 2: strength to power', '', 'Keep the bar heavy but move it fast, and pair each lift with a jump or throw.',
                [acc(2, 8, 'RPE 7-8'), snp((3, 3, 'RPE 8', '2-1-X'), ('Box jump', 3, 3, 'Maximum height, full rest.'), [KB(4, 8, 'Heavy and fast')], (3, 3, 'RPE 8'), (3, 'AMRAP', 'Leave 2 in reserve'), minutes=50, note='Then 3 x 5 medicine ball chest throws or clap push-ups.'), *c])
    if n in (44, 49, 50):
        return ({44: 'Recovery week', 49: 'Nationals week', 50: 'Rest'}[n], 'rest', 'No gym this week.', [])
    if ev or n == 41:
        why = ev or 'Rehearsal week before Regionals'
        return (f'Deload: {why}', 'deload', 'One light, fast session early in the week, or none. Nothing in the three days before the first game.',
                [snp((2, 3, 'RPE 6', '2-1-X'), ('Squat jump', 2, 3), [KB(2, 8)], (2, 3, 'RPE 6'), (2, 5, 'Easy'), minutes=30, title='Gym: primer',
                     note=('2s and anyone not at the event: repeat last week\'s in-season session instead.' if n in ONES_ONLY else 'Everything fast and easy.'))])
    if 25 <= n <= 43:
        return ('In-season: keep strength, stay fresh', '', 'One gym session a week at most, early in the week. Low volume, still heavy enough to keep what you built.',
                [snp((3, '3-5', 'RPE 7-8', '2-1-X'), ('Squat jump', 2, 4), [KB(3, 8, 'Fast')], (3, 4, 'RPE 7-8'), (3, 'AMRAP', 'Leave 2 in reserve'), minutes=40, title='Gym: in-season strength and power'),
                 acc(2, 8, 'RPE 7', 'Alternate with the strength and power session week by week if you prefer.')])
    if 45 <= n <= 47:
        return ('Peak: low volume, high speed', '', 'Very little lifting, all of it fast. Stop every set while the bar is still moving quickly.',
                [snp((3, '2-3', 'RPE 7, as fast as possible', '2-1-X'), ('Box jump', 3, 3, 'Maximum intent, full rest.'), [KB(3, 6, 'Maximum speed')], (2, 3, 'RPE 7'), (2, 'AMRAP', 'Leave 3 in reserve'), minutes=40, title='Gym: peak power',
                     note='At least two days before the week 47 rehearsal game.' if n == 47 else '')])
    if n == 48:
        return ('Taper', 'deload', 'One short primer early in the week, then no more gym until after Nationals.',
                [snp((2, 3, 'RPE 6', '2-1-X'), ('Squat jump', 2, 3), [KB(2, 6)], (2, 3, 'RPE 6'), (2, 5, 'Easy'), minutes=30, title='Gym: primer', note='Monday or Tuesday. 2s: repeat week 47 instead if you want to keep building.')])
    if n == 51:
        return ('Off-season restart', 'deload', 'Off-season 1 starts again, lightly: one or two months of easy training, not a full stop.',
                [acc(2, 12, 'RPE 6', 'An easy restart.')])
    raise ValueError(n)

for n in range(1, 52):
    title, kind, obj, sessions = gym_week(n)
    if sessions:
        sessions[0]['session_focus'] = (GYM_RULE + ' ' + sessions[0]['session_focus']).strip()
    week(GYM, n, title, sessions, kind=kind, objective=obj)

# ==========================================================================
# Throwing at home
# ==========================================================================
TH = 'Throwing'
TH_RULE = ('15 minutes, about 100 throws, with your mentor pair if you can, or alone against a wall, fence or target. '
           'Picture a game situation for every throw, and repeat a throw straight after a miss. '
           'Write your throw count and any score in the notes.')
LOWREL = 'https://www.youtube.com/watch?v=qBLxsGFgPX8'
TURN = 'https://www.youtube.com/watch?v=zyWG3qKItHU'
T = lambda name, reps='', note='', dur='', dist='', video='': ex(name, '', reps, dur=dur, dist=dist, note=note, video=video)

TBLOCKS = [
    (range(1, 4), 'Phase 1: grip, balance and pivot', 'Balanced throws from a stable pivot: weight on the non-pivot foot, no extra step after the throw.',
     'Step, flick, point. Two hands on the disc whenever you can.',
     ('Balance and pivot', [T('Single-leg throwing', '10 backhands and 10 forehands on each leg', 'Throw standing on one leg, then the other. If you have to hop afterwards, the throw was off balance.'),
                            T('Compass throwing', '30', 'Pivot foot planted. Step to north, east, south and west in turn and throw from each. Alone: pick a target for each direction.'),
                            T('Flat throws, hold the finish', '30', 'Finish pointing at the target and hold for 2 s.', dist=15)]),
     ('70-pass and catching', [T('70-pass', '70', '10 each of flat, inside-out and outside-in backhands, the same on the forehand, then 10 hammers. Turn round halfway so you throw against the wind too.'),
                               T('Catching set', '30', '10 clap catches, 10 crab catches high, 10 crab catches low. Alone: flip the disc up or bounce it off a wall. Watch the rim all the way in.')])),
    (range(4, 7), 'Phase 1: throwing to space', 'Throw to the space, not the person, and shape the throw so it sits for the receiver.',
     'Lead the receiver. Height, a small angle, in front.',
     ('Lead passes and targets', [T('Lead passes to a moving target', '40', 'Your partner jogs or cuts; throw into the space ahead of them. Alone: throw to cones at 10, 20 and 30 m and score 2 for a hit, 1 for within two steps.'),
                                  T('Clock drill', '2 at each clock point', 'Pick a target and throw to it around the clock: flat, then exaggerating the curve each way.', dist=10),
                                  T('Huck shape at 70%', '10 backhands, 10 forehands', 'Inside-out early, flat in the middle, outside-in to finish. Control, not power.')]),
     ('70-pass with a picture', [T('70-pass with visualisation', '70', 'Before each throw, picture the cutter and the lane you are hitting.'),
                                 T('Moving target', '', 'Throw early into space and lead the receiver. Alone: throw, sprint to collect, repeat.', dur=300)])),
    (range(7, 10), 'Phase 1: pivots, fakes and release points', 'A fake has to look like a real throw. One decisive pivot beats three half-pivots.',
     'Full arm, eyes and shoulders on every fake. Pivot directly left or right.',
     ('Pivots and fakes', [T('Fake-fake-throw', '40', 'Two real-looking fakes, then the throw. Alone: use a mirror or a window to check the fake looks like the throw.'),
                           T('Shimmy, then step out', '30', 'Fake the first six inches of a pivot with your shoulders. If nothing would bite, finish the pivot and throw.'),
                           T('Threat position', '30', 'Flip the disc up, catch it, set your grip and pivot, and throw inside 2 s.')]),
     ('Wide and low', [T('Wide-and-low series', '10 forehands and 10 backhands of each', 'Pause at release, then no pause, then wider and lower. Check the disc angle and your posture at each pause.'),
                       T('Touch throws', '20', 'Front edge up; land it softly on the receiver\'s arms or on a jacket on the ground.', dist=10),
                       T('Off-hand throws', '20', 'Short backhands and forehands with your other hand.', dist=6)])),
    (range(10, 14), 'Phase 1 and the Christmas break: wide and low releases', 'Width and a low release beat the mark. The Christmas programme is part of the routine, not a one-off.',
     'Hold the finish for 2 s to prove your balance. Release below the knee.',
     ('The 10-minute low-release session (GRUT)', [T('10-minute low-release session (GRUT)', 'A few throws of each of the seven variations, forehand and backhand', 'Squat, squat and pause, wrist scrape, snap back, low and flat, and the rest: follow the video.', dur=600, video=LOWREL),
                                                   T('Wide release past a cone', '30', 'Step out past a cone to release and hold the finish for 2 s. Move the cone wider each round.')]),
     ('Get 10 and targets', [T('Get 10 with a partner as the marker', '10 against a forehand force, 10 against a backhand force', 'Break throws past an active marker to a third player or a target 10-15 m away. Count completions on each side. Alone: throw past a chair to a target.'),
                             T('Throwing to a target', '60', 'A post, a bag or a goalpost from 10, 15 and 20 m. Count hits out of 10 at each distance.')])),
    (range(14, 18), 'Phase 2: breaks under pressure', 'Catch in threat position and break early. Off-balance and half-pivot throws are skills we train on purpose.',
     'Break early, while the mark is still setting. Never the same throw twice in a row.',
     ('Get 10 and half pivots', [T('Get 10 with a partner as the marker', '2 rounds: 10 each side per round', 'Record both sides. A confident break thrower scores 8 or more on both.'),
                                 T('Half-pivot backhands', '30', 'Release before the non-pivot foot lands. You won\'t get distance; get it past the marker\'s shoulder.'),
                                 T('Around and inside breaks to a target', '30', 'Past a chair or bag as the marker. Alternate around and inside.')]),
     ('Quick release and throwing tired', [T('Catch, pivot, throw', '40', 'Quick release, then fake first, then change the release height. From a partner\'s pass or your own flip.'),
                                           T('Off-hand throws', '20', dist=6),
                                           T('Throwing tired', '4 rounds of 10', '20 s of fast feet or 5 burpees, then 10 throws straight away. Technique shouldn\'t change when you are out of breath.')])),
    (range(18, 23), 'Phase 2: beating a good mark; quick disc', 'Threaten both sides so the marker has to choose, and process the disc quickly.',
     'Threaten both sides. After the throw, move.',
     ('Get 10 and one crossover', [T('Get 10 with a partner as the marker', '2 rounds: 10 each side per round', 'Record both sides.'),
                                   T('One-crossover breaks', '30', 'You may bring the disc across your body once. Fake one side and throw the other without a second crossing.'),
                                   T('Zippy and soft', '30', 'Inside-out and outside-in, fast then floated, forehand then backhand. Step back three paces and repeat.')]),
     ('Quick throwing and trap escapes', [T('Quick throwing', '40', 'Catch and release as fast as you can with no wobble.', dist=10),
                                          T('Throws against a trap', '8 of each', 'Big around backhand, big around forehand, inside-out forehand, inside-out backhand high and low, fast off-hand pass.'),
                                          T('Throwing tired', '2 rounds of 10', '20 s of fast feet, then 10 throws.')])),
    (range(23, 28), 'Phase 3: wind before Tour 1, and breaks', 'Tour 1 is usually very windy. Low release upwind, high release downwind, more spin on everything.',
     'More spin. Low upwind, high downwind. Throw in every direction of the wind.',
     ('Wind', [T('Into and with the wind', '25 each way', 'Upwind: release low, nose down, extra spin. Downwind: release higher and let it carry.'),
               T('Crosswind swings', '30', 'Throw across the wind both ways with an outside-in curve into the wind.'),
               T('Get 10 with a partner as the marker', '10 each side', 'Run it across the wind and note which side the wind helped.')]),
     ('Breaks and touch', [T('Get 10 with a partner as the marker', '2 rounds: 10 each side per round', 'Record both sides.'),
                           T('Catch, pivot, throw', '30', 'Quick release into threat position.'),
                           T('Touch throws', '30', 'Soft, catchable throws at 5-10 m: the resets and dishes that keep the disc.')])),
    (range(28, 32), 'Phase 3: hucks, shape and the box', 'Hucks are about control, not power. Practise a little beyond your range, and count what lands in the box.',
     'Step sideways, pull it through, slightly inside-out (Card 10). Load it, snap it (Card 11).',
     ('Box hucking', [T('Box hucking at 75% of your range', '10 backhands, 10 forehands', 'Mark a 10 x 10 m box with cones. Count how many land in it on each side.'),
                      T('Hucks at 110% of your range', '10 backhands, 10 forehands', 'Overthrowing beats underthrowing. Technique doesn\'t change because the distance does.'),
                      T('Short throws on the walk back', '40', 'Flat and soft, to finish.')]),
     ('Range throws and wind', [T('Stationary range throws', '3 sets of 5 forehands and 5 backhands', 'Flat inside-out, roll curve, inside-out curve.'),
                                T('Into and with the wind', '15 each way'),
                                T('Get 10 with a partner as the marker', '10 each side', 'Record both sides.')])),
    (range(32, 38), 'Phase 3: hucks that find a cutter; breaks that continue', 'Set the huck up, and make every break lead somewhere. Tours 2 and 3 are where the confident break throwers are counted.',
     'Huck to the break side, over the defender\'s shoulder. Break to the receiver\'s outside shoulder.',
     ('Hucks to a cutter', [T('Lead pass to a cone at your range', '5 forehands and 5 backhands of each shape'),
                            T('Huck off a give-and-go', '5 forehands, 5 backhands', 'Dish, get it back on the move, set and huck before the mark would arrive. Alone: flip, catch on the move, huck.'),
                            T('Pump-fake one side, huck the other', '10'),
                            T('Short throws on the walk back', '40')]),
     ('Breaks into continuation', [T('Get 10 with a partner as the marker', '2 rounds: 10 each side per round', 'Record both sides: 8 or more on both is the standard.'),
                                   T('Break to the outside shoulder', '30', 'Throw the break wider than feels natural, so a receiver could keep running on the break side.'),
                                   T('Into and with the wind', '15 each way')])),
    (range(38, 44), 'Phase 4: your throws, at game speed', 'No new throws. The ones your role needs, faster and under control.',
     'Only throw to open players. Catch ready to throw.',
     ('Your three throws', [T('Your top three throws for your role', '20 of each', 'Agree them with your skill lead. Every one at game speed, with a fake or a pivot first.'),
                            T('Quick throwing', '40', 'Catch and release, no wobble.', dist=10)]),
     ('Hucks, breaks and escapes', [T('Box hucking at 75% of your range', '10 backhands, 10 forehands', 'Count the box.'),
                                    T('Get 10 with a partner as the marker', '10 each side', 'Record both sides.'),
                                    T('Throws against a trap', '5 of each'),
                                    T('Into and with the wind', '15 each way')])),
    (range(44, 50), 'Phase 5: hands before legs', 'Quick releases at game speed. Hands get worse faster than legs, so throwing goes up while running comes down.',
     'Game speed. Catch, look, release.',
     ('Quick releases', [T('Quick-release pairs or triangle', '60', 'Catch and release inside a second. Alone: off a wall.', dist=10),
                         T('Fake first', '20', 'One real fake, then release.'),
                         T('Change the release height', '20', 'Low, middle and high off the same pivot.')]),
     ('Variety and accuracy', [T('Never the same throw twice', '', 'Every throw different from the last: shape, height, side, speed.', dur=420),
                               T('Stationary accuracy', '30', 'To a target at 15 m; count the hits.'),
                               T('On the move', '20', 'One- to two-second throws to varied cuts, or to targets after a short run.')])),
]

FOCUS = {
    'Focus: breaking the mark': {
        1: [T('Three low-release variations (GRUT)', '10 of each, both sides', 'Squat and pause, wrist scrape, low and flat.', video=LOWREL),
            T('Wide release past a cone', '20', 'Hold the finish for 2 s.'),
            T('Get 10 with a partner as the marker', '10 each side', 'Record both sides.')],
        2: [T('Get 10 with a partner as the marker', '3 rounds: 10 each side per round', 'Record your best on each side. The target is 8 or more on both.'),
            T('Two pivots, never the same throw twice', '20', 'The extended-mark rule: stall 4, two pivots at most, a different throw every time.'),
            T('Half-pivot backhands', '20')],
        3: [T('Get 10 with a partner as the marker', '2 rounds: 10 each side per round', 'Record both sides.'),
            T('Break to a moving partner\'s outside shoulder', '30', 'So they can keep running on the break side.'),
            T('Inside-out early or around late: choose and commit', '20', 'Call the choice before you pivot.')],
        5: [T('Get 10 at stall-4 pace', '10 each side', 'Record both sides.'),
            T('Quick break off the catch', '30', 'Catch in threat position and break before a mark could set.')],
    },
    'Focus: getting open': {
        1: [T('Chop stop and go', '5 each side', 'Five or six hard steps, small fast steps to stop, stay low for a second, then go the other way.'),
            T('Jab step and go', '5 each side', 'Close to an imaginary defender, one hard jab, then accelerate away.'),
            T('Cut and catch with a partner', '10 under, 10 away', 'Your partner throws a lead pass; you return it. That is 20 catches for you and 20 lead passes for them.')],
        2: [T('1v1 from 15 m with a partner on your back shoulder', '10 reps: 5 under, 5 away', 'The cutting test, as practice. A third player throws; or the defender shadows and you catch your own flip. Count clean catches.'),
            T('Start before the thrower catches', '10', 'Your partner flips the disc up to themselves. Your cut starts while it is in the air, so you are open as they look up.'),
            T('Name your cut', '6', 'Tell the defender the cut, then win anyway.')],
        3: [T('Deep-cut timing', '8', 'Wait for the thrower to be set, start shallow, then be decisive. Glance sideways for the disc, not back.'),
            T('Continuation timing', '10', 'Start your cut as your partner catches, not after.'),
            T('1v1 from 15 m with a partner on your back shoulder', '10 reps: 5 under, 5 away', 'Count clean catches against your last test.')],
        5: [T('1v1 at game speed', '6 reps', 'Full speed, full rest between reps.'),
            T('Cut and catch with a partner', '10 under, 10 away', 'Catch ready to throw.')],
    },
    'Focus: catching and hucking': {
        1: [T('Catching ladder', '20 clap, 20 crab high and low, 10 one-handed each hand', 'Feet first: get your body behind the disc. Watch the rim all the way in.'),
            T('Turn and attack (GRUT)', '10', 'Face away; your partner puts up a floaty disc and calls "Up!". Turn, find it and attack it in front of you.', video=TURN),
            T('Rinkydink (GRUT)', '', 'Deliberately odd throws, caught one-handed at the rim.', dur=120)],
        2: [T('Catching at pace', '20', 'Run through the disc; don\'t slow down to catch.'),
            T('Catching with a distractor', '20', 'Your partner waves a hand or a disc across your eyeline as you catch.'),
            T('Box hucking', '10 backhands, 10 forehands', 'A 10 x 10 m box at 75% of your range. Count the box.')],
        3: [T('Box hucking', '20 backhands, 20 forehands', 'Count the box on each side and write it down.'),
            T('Attack the high point', '10', 'Your partner throws a floaty disc; catch it at the highest point you can reach.'),
            T('Huck to a moving partner', '10', 'They start shallow and go; lead them to the break side.')],
        5: [T('Catches at full speed', '20', 'Two hands wherever you can.'),
            T('Hucks at 75% of your range', '10', 'Count the box.')],
    },
    'Focus: marking and 1v1 defence': {
        1: [T('Marking base hold', '3 holds', 'Wide and low, weight on the balls of your feet, hips back, chest open, eyes up.', dur=20),
            T('Side shuffle with pause and reach', '6 each way', 'Shuffle 5 m, pause, reach without shifting your weight. Never cross your feet.', dist=5),
            T('Be the marker for your partner\'s Get 10', '10 each side', 'Count the throws you stop or spoil. Hands placed on purpose, not waved.')],
        2: [T('One-crossover game with a partner', '5 reps each side, then swap', 'The thrower may cross their body once. A break without a pivot is their win; a turnover or two pivots is yours. If you only have 10 minutes a week for marking, this is the one.'),
            T('Mirror drill', '4 rounds', 'Face your partner between two cones 5 m apart. They try to lose you; you stay in front.', dur=20),
            T('Triangle mark: zero pivot, then one pivot', '10', 'Hand takes the shown throw, body the around, shoulder the inside.')],
        3: [T('Keeping margins with a partner', '3 rounds', 'They move at random; you stay within an arm\'s length. 40 s on, 20 s off.', dur=40),
            T('One-crossover game with a partner', '5 reps each side, then swap'),
            T('Drop step and turn', '6 each side', 'Backpedal, drop step, open the hips and sprint 5 m without turning your back on the thrower.')],
        5: [T('Reactive shuffles', '4 rounds', 'React to your partner\'s fakes at game speed.', dur=15),
            T('Be the marker for your partner\'s quick breaks', '20', 'Set up in the first second after their catch.')],
    },
}
FOCUS_NOTE = ('Your third session of the week: pick the ONE focus session that matches your development focus (agreed with a '
              'skill lead after each full test round). Until your first one-to-one in weeks 1-3, pick your weakest baseline test. '
              'If the gap is a big one, follow the matching UAP module for four weeks instead and log it here.')

def focus_phase(n):
    p = phase(n)
    return {0: 1, 1: 1, 2: 2, 3: 3, 4: 3, 5: 5}[p]

for n in range(1, 52):
    if n == 50:
        week(TH, n, 'Rest', kind='rest', objective='No throwing programme this week. Throw for fun if you like.')
        continue
    if n == 51:
        week(TH, n, 'Season review: what changed', [
            sess('Throwing 1: 70-pass', 'throwing', 15, [T('70-pass', '70', 'The same set as week 1. Notice what has changed since October.')], focus=TH_RULE, log='duration_minutes'),
            sess('Throwing 2: one throw to develop', 'throwing', 15, [T('A throw you want for next season', '', 'Pick one and work on it. Tell your skill lead which.', dur=600)], req='optional', focus=TH_RULE, log='duration_minutes'),
        ], kind='deload', objective='The final skill tests are at training this week. Keep throwing through the off-season.')
        continue
    blk = next(b for b in TBLOCKS if n in b[0])
    _, title, objective, skills, (t1name, t1), (t2name, t2) = blk
    ev = EVENTS.get(n)
    extra = ''
    if n in (12, 13):
        extra = f' Christmas homework: watch theory Card {10 if n == 12 else 11} ({"backhand" if n == 12 else "forehand"} huck) before week 28.'
    if ev:
        extra = f' {ev} this weekend: do all three sessions before Thursday and keep them sharp.'
    if n == 44:
        extra = ' Recovery week: easy throwing only, no running between throws.'
    fp = focus_phase(n)
    focus_sessions = [sess(name, 'throwing', 15, variants[fp], req='alternative', group='focus',
                           focus=FOCUS_NOTE if i == 0 else 'Pick this one if it is your development focus.', log='duration_minutes')
                      for i, (name, variants) in enumerate(FOCUS.items())]
    week(TH, n, title, [
        sess(f'Throwing 1: {t1name}', 'throwing', 15, t1, focus=TH_RULE + extra, cues=skills, log='duration_minutes',
             video=LOWREL if 'low-release' in t1name else ''),
        sess(f'Throwing 2: {t2name}', 'throwing', 15, t2, focus=TH_RULE, cues=skills, log='duration_minutes'),
        *focus_sessions,
    ], kind='deload' if n in (12, 13, 44) else '', objective=objective, skills=skills)

# ==========================================================================
# Speed
# ==========================================================================
SP = 'Speed'
SP_WARM = ('8 minutes: easy jog, leg swings, walking lunges, A-skips, then three build-up runs over 30 m at 60, 75 and '
           '90%. Never sprint cold.')
SP_RULE = ('Optional, 15-20 minutes, on grass. Do it straight before Home strength A so the week still has one hard leg '
           'day at home. Every sprint is flat out with full rest: walk back and go when you feel ready. This is speed, '
           'not fitness: stop when a rep gets slower.')
ACC_CUES = 'Lean into the take-off with your whole body. Big arms drive big legs. No side-to-side movement. Rise gradually.'
TOP_CUES = 'Strong drive phase, then stay tall and relaxed at speed: loose face, loose hands. Let momentum carry you.'
TURN_CUES = 'Lean back towards where you are going. Wedge step, crossover with full hip extension, explosive getaway step.'
S = lambda name, sets='', reps='', dist='', rest='Walk back; go when fully recovered', note='': ex(name, sets, reps, dist=dist, rest=rest, note=note)

def sp(title, minutes, exs, cues, note=''):
    return sess(title, 'sprint', minutes, exs, req='optional', focus=(SP_RULE + ' ' + note).strip(), warmup=SP_WARM, cues=cues)

def speed_week(n):
    ev = EVENTS.get(n)
    if 1 <= n <= 4:
        if n == 1:
            return ('Baseline test and acceleration', '', 'The filmed 5-10-5 is run at the week 1 joint session. This week\'s session teaches the first three steps.',
                    [sp('Speed: acceleration technique', 20, [S('Falling starts', 4, '', 10, note='Lean until you fall, then lots of small, fast steps.'),
                                                              S('Sprints from standing', 6, '', 10, note='Drive phase only: stay low, head down, aggressive arms.')], ACC_CUES)])
        return ('Acceleration technique', '', 'Learn the first three steps: the lean, the drive and the arms.',
                [sp('Speed: acceleration technique', 20, [S('Falling starts', 4, '', 10, note='Lean until you fall, then lots of small, fast steps.'),
                                                          S('Sprints from standing', 8, '', 10, note='Drive phase only: stay low, head down, aggressive arms.'),
                                                          S('Sprints from standing', 2, '', 20, note='Rise gradually to upright.')], ACC_CUES)])
    if 5 <= n <= 8:
        return ('Acceleration from game positions', '', 'The same technique from the positions you start from in games.',
                [sp('Speed: game starts', 20, [S('From a layout position', 3, '', 15, note='Start face down. Explode up and forward in one motion; don\'t stand up first.'),
                                               S('From a marking stance', 3, '', 15, note='Start facing away from the finish. Quick pivot, immediate lean and drive.'),
                                               S('After a fake', 3, '', 15, note='Fake a throw, then explode into the sprint.'),
                                               S('Sprints from standing', 3, '', 20)], ACC_CUES)])
    if 9 <= n <= 11:
        return ('Out to 30 m', '', 'Stretch the acceleration to 30 m and meet top speed for the first time.',
                [sp('Speed: 30 m and flying 10s', 20, [S('Sprints from standing', 4, '', 20), S('Sprints from standing', 3, '', 30),
                                                       S('Flying 10 m', 3, '', 30, note='Build up over 20 m, then 10 m as fast as you can stay relaxed.')], TOP_CUES)])
    if n in (12, 13):
        return ('Christmas break: tick over', 'deload', 'One short session if the ground is safe. Skip it on frozen pitches.',
                [sp('Speed: tick over', 15, [S('Sprints from standing', 6, '', 20)], ACC_CUES)])
    if 14 <= n <= 17:
        return ('Top speed and the turn', '', 'Longer sprints and the 5-10-5 turn, ready for the trial tests in week 18 (50 m sprint, 5-10-5 and arrowhead agility).',
                [sp('Speed: flying 20s and turns', 20, [S('Sprints from standing', 3, '', 20), S('Flying 20 m', 3, '', 40, note='Build up over 20 m, then 20 m fast and relaxed.'),
                                                        S('Sprint', 2 if n < 16 else 3, '', 40 if n < 16 else 50, rest='Full recovery, 3 min', note='The trial distance by week 16.'),
                                                        S('5-10-5 shuttle', '', '2 slow each way, 2 fast each way', rest='1 min', note='Three cones 5 m apart. Perfect footwork on the slow reps; keep it on the fast ones.')], TOP_CUES + ' ' + TURN_CUES)])
    if n == 18:
        return ('Trial 1: athletic profile tests', 'deload', 'The filmed 5-10-5, the 50 m sprint with 5, 10 and 35 m splits, and the arrowhead agility test are run at Trial 1. No other speed work this week.',
                [sess('Athletic profile tests at Trial 1', 'sprint', 20, req='optional',
                      focus='Run at the joint trial session, after the full warm-up. Enter your results under Tests. Nothing to do at home.')])
    if 19 <= n <= 22:
        return ('Speed that repeats', '', 'Keep top speed and start linking sprints, as points do: short rests inside a set, full rest between sets.',
                [sp('Speed: sprints and short sets', 20, [S('Flying 20 m', 2, '', 40), S('Sprint', 2, '', 40, rest='Full recovery, 3 min'),
                                                          S('Short set: 4 x 20 m', 2, 4, 20, rest='30 s between sprints; 3 min between sets', note='Stop the set if a sprint is clearly slower.')], TOP_CUES)])
    if n in (44, 49, 50) or (ev and n not in (29,)):
        why = ev or {44: 'Recovery week', 50: 'Rest'}[n]
        return (f'No speed session: {why}', 'rest', 'Games give you all the sprinting you need this week.', [])
    if n == 29:
        return ('No speed session: Herdlodge', 'rest', 'The Herdlodge games cover it.', [])
    if n == 35:
        return ('Mid-season athletic profile test', 'deload', 'The filmed 5-10-5 is run with the mid-season skill tests at the week 35 joint session.',
                [sess('5-10-5 at the mid-season tests', 'sprint', 10, req='optional', focus='Run at the joint session. Enter your result under Tests. Nothing to do at home.')])
    if 24 <= n <= 43:
        return ('In-season top-up', '', 'Three or four flat-out sprints a week, early in the week, keep your top speed and protect your hamstrings. Training and games do the rest.',
                [sp('Speed: in-season top-up', 12, [S('Sprint', 2, '', 30), S('Sprint', 2, '', 40, rest='Full recovery, 3 min')], TOP_CUES,
                    note='Early in the week, at least two days before training or an event.' + (' Rehearsal week: two sprints only.' if n == 41 else ''))])
    if 45 <= n <= 47:
        return ('Peak: fast and fresh', '', 'Short, maximal sprints with long rests, timed for the peak two to three weeks before Nationals.',
                [sp('Speed: peak sprints', 15, [S('Sprints from standing', 4, '', 20), S('Flying 20 m', 2, '', 40), S('Sprint', 2, '', 30, rest='Full recovery, 3 min')], TOP_CUES,
                    note='At least two days before the week 47 rehearsal game.' if n == 47 else '')])
    if n == 48:
        return ('Taper', 'deload', 'Keep a little speed and no fatigue.',
                [sp('Speed: taper primer', 10, [S('Sprints from standing', 3, '', 20)], ACC_CUES, note='Monday or Tuesday only. 2s: repeat week 47 instead if you want to.')])
    if n == 51:
        return ('End-of-season athletic profile test', 'deload', 'The filmed 5-10-5 is run with the final skill tests at the week 51 joint session.',
                [sess('5-10-5 at the final tests', 'sprint', 10, req='optional', focus='Run at the joint session. Enter your result under Tests. Compare it with October.')])
    raise ValueError(n)

for n in range(1, 52):
    title, kind, obj, sessions = speed_week(n)
    if n == 1:
        sessions = [sess('5-10-5 at the baseline tests', 'sprint', 10, req='optional',
                         focus='The filmed 5-10-5 is run at the week 1 joint session. Enter your result under Tests.'), *sessions]
    week(SP, n, title, sessions, kind=kind, objective=obj)

# ==========================================================================
# Write
# ==========================================================================
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, 'programme.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=COLS, lineterminator='\n')
    w.writeheader()
    for r in ROWS:
        w.writerow({c: r.get(c, '') for c in COLS})

FULL = '18, 35, 51'
MINI = '6, 10, 15, 18, 22, 27, 32, 35, 40, 45, 51'
TESTS = [
    # test, unit, measurement, attempts, aggregation, better, min, max, description, instructions, milestone_track, baseline, retests
    ('Hucking alley: hucks in the lane', 'out of 10', 'count', 1, 'best', 'higher', 0, 10, 'Skill test: throwing range and accuracy',
     '10 hucks (5 backhand, 5 forehand) down a 20 m-wide lane marked with cones every 10 m. Count the hucks that land in the lane past 30 m. Throw the same way each round and note the wind.', TH, 1, FULL),
    ('Hucking alley: longest huck in the lane', 'm', 'distance', 1, 'best', 'higher', 10, 90, 'Skill test: throwing range',
     'The distance of your longest huck that landed in the lane, to the nearest 5 m.', TH, 1, FULL),
    ('Get 10: forehand force', 'out of 10', 'count', 1, 'best', 'higher', 0, 10, 'Skill test: breaking the mark',
     '10 break throws past an active marker forcing forehand, to a static receiver 10-15 m away on the break side. Stall 6. A completion is a throw the receiver catches without moving more than one step.', TH, 1, MINI),
    ('Get 10: backhand force', 'out of 10', 'count', 1, 'best', 'higher', 0, 10, 'Skill test: breaking the mark',
     'As the forehand-force test, with the marker forcing backhand. A confident break thrower scores 8 or more on both.', TH, 1, MINI),
    ('1v1 cutting test', 'out of 10', 'count', 1, 'best', 'higher', 0, 10, 'Skill test: getting open',
     'From a stack spot 15 m from the thrower, get open before stall 6 against a defender starting on your back shoulder. 10 reps: 5 under, 5 deep or away. Count clean catches. Defenders are 1s players at full intensity.', TH, 1, MINI),
    ('Catching under pressure', 'out of 20', 'count', 1, 'best', 'higher', 0, 20, 'Skill test: keeping the disc',
     '20 catches in the heads-on drill at full speed. Count clean catches.', TH, 1, FULL),
    ('5-10-5 agility shuttle (filmed)', 's', 'time', 2, 'best', 'lower', 3.5, 9, 'Athletic profile: change of direction. Recorded, not counted in the skill goal.',
     'Three cones 5 m apart. Start at the middle cone, go 5 m one way, 10 m back, 5 m to finish. One attempt starting each way. Film it and time from first movement to the line. Same surface and shoes each round.', SP, 1, FULL),
    ('50 m sprint', 's', 'time', 2, 'best', 'lower', 5, 12, 'Athletic profile at trials: speed',
     'Standing start behind the line; full recovery between attempts. Film from the side with cones at 5, 10, 35 and 50 m, and time from first movement.', SP, 18, ''),
    ('50 m sprint: 5 m split', 's', 'time', 2, 'best', 'lower', 0.7, 2.5, 'Athletic profile at trials: first steps', 'Taken from the film of the 50 m sprint.', SP, 18, ''),
    ('50 m sprint: 10 m split', 's', 'time', 2, 'best', 'lower', 1.3, 3.5, 'Athletic profile at trials: acceleration', 'Taken from the film of the 50 m sprint.', SP, 18, ''),
    ('50 m sprint: 35 m split', 's', 'time', 2, 'best', 'lower', 3.5, 9, 'Athletic profile at trials: reaching top speed', 'Taken from the film of the 50 m sprint.', SP, 18, ''),
    ('Arrowhead agility test', 's', 'time', 2, 'best', 'lower', 6, 15, 'Athletic profile at trials: agility',
     'The standard arrowhead course: sprint 10 m to the middle cone, cut to the side cone, round the far cone and sprint back. One attempt to the left and one to the right; the better time counts.', SP, 18, ''),
]
with open(os.path.join(OUT, 'tests.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['test', 'unit', 'measurement', 'attempts', 'aggregation', 'better', 'min', 'max', 'description',
                'instructions', 'milestone_track', 'baseline_week', 'retest_weeks'])
    for t in TESTS:
        w.writerow(t)
print(len(ROWS), 'rows')
