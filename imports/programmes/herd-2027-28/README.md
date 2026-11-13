# Thundering Herd 2027/28: programmes for the season plan

| Phase | Programme |
| --- | --- |
| 1. Foundations | A copy of the off-season programme (`../thundering-herd-2025-26`), see below |
| 2. Pressure and trials | The same off-season copy (it runs to Trial 1) |
| 3. Early season | `phase-3-early-season`: In-season 2028: Early season |
| 4. Regionals | `phase-4-regionals`: In-season 2028: Regionals |
| 5. Nationals | `phase-5-nationals`: In-season 2028: Nationals peak and taper (1s) |

## Off-season (Phases 1 and 2)

The off-season programme is 16 weeks long. Copy it (rather than changing the 2025/26 one, which
holds last season's logs), then in the copy's Settings:

- Schedule: **calendar**, start **4 Oct 2027**.
- Pause: **2 weeks from 20 Dec 2027** (the Christmas break).

It then runs from plan week 1 to plan week 18 (Trial 1). Sprint retests fall in week 10, the
week the plan re-runs benchmarks. Link the copy to both Phase 1 and Phase 2. Phase 2 weeks 19-24
(Trials 2-3 to squads announced) have no programme sessions.

## In-season (Phases 3-5)

Calendar programmes that start on the phase's first Monday:

| Folder | Start | Weeks | Tracks | Benchmarks |
| --- | --- | --- | --- | --- |
| `phase-3-early-season` | 2028-03-20 | 13 | Strength & power, Game speed, Throwing (optional) | Week 11 (optional check) |
| `phase-4-regionals` | 2028-06-19 | 6 | Speed & power, Mental skills | — |
| `phase-5-nationals` | 2028-07-31 | 8 | Fitness, Mental skills | Week 8 (final) |

- Each strength session comes **with or without a gym**. They are alternatives, so either one
  counts. The gym version continues the off-season Gym track's lifts (box squat, kettlebell swings,
  jumping lunges, bench, chin-ups) at 2-3 sets of 2-3 at RPE ~7-8.
- Event, Easter and taper weeks are lighter, and their sessions are optional. Game-speed work is
  replaced by the event itself.
- Hard leg sessions shouldn't fall on consecutive days, or within three days of a tournament.

Import each folder from Training > Programmes > Import spreadsheet (`programme.csv` and
`tests.csv`), or from the command line:

```
flask import-programme imports/programmes/herd-2027-28/phase-3-early-season --team <slug> --name "In-season 2028: Early season" --start 2028-03-20
```

Then publish it and link it under Season plan > Edit plan > Phases.
