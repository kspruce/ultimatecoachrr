# Thundering Herd 2027/28: a programme for each phase

One calendar programme per phase of the 2027/28 season plan, taken from the plan's
*Fitness without a track or gym*, *Skills curriculum* and *Measuring improvement*
sections and the week-by-week themes. Fitness mostly happens at training; these
programmes cover the work players do on their own between sessions.

| Folder | Name | Start (Monday) | Weeks | Tracks | Benchmarks |
| --- | --- | --- | --- | --- | --- |
| `phase-1-foundations` | Phase 1 Foundations: home programme | 2027-10-04 | 13 (11 + Christmas) | Home strength, Throwing, Movement | Movement weeks 1 and 10 |
| `phase-2-pressure-and-trials` | Phase 2 Pressure and trials: strength, plyometrics and sprints | 2028-01-03 | 11 | Strength & plyometrics, Repeated sprints, Throwing under pressure | Week 5 (Trial 1) |
| `phase-3-early-season` | Phase 3 Early season: in-season maintenance | 2028-03-20 | 13 | Strength & power, Game speed, Throwing (optional) | Week 11 (optional check) |
| `phase-4-regionals` | Phase 4 Regionals: speed and mental skills | 2028-06-19 | 6 | Speed & power, Mental skills | — |
| `phase-5-nationals` | Phase 5 Nationals: rebuild, peak and taper (1s) | 2028-07-31 | 8 | Fitness, Mental skills | Week 8 (final) |

Each programme follows the same rules:

- Event, trial and Easter weeks are lighter (deload); sessions there are optional.
- Weeks covered by a tournament or trial have no conditioning (rest).
- Hard leg sessions should not fall on consecutive days.
- Plyometrics build from about 40 contacts in Phase 2 to 80-100 at the Phase 5 peak.
- The four benchmarks are hucking alley, Get 10, 5-10-5 and catching under pressure.

Import each from Training > Programmes > Import spreadsheet (upload `programme.csv` and
`tests.csv`), or from the command line:

```
flask import-programme imports/programmes/herd-2027-28/phase-1-foundations --team <slug> --name "Phase 1 Foundations: home programme" --start 2027-10-04
```

Then publish it and link it under Season plan > Edit plan > Phases.
