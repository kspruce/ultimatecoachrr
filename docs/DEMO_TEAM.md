# The demo team

A made-up club, **Riverside Kites**, with a season's worth of everything, and
a shared login anyone can use to look round it as their coach. It's for
showing the site to clubs: in a meeting, in an email or in a Reddit post.

## Setting it up

As a site superadmin: **Teams** (the team management page) → **Demo team** →
**Set up the demo team**. It takes about 15 seconds.

Or from a shell on the server:

```bash
flask seed-demo            # set it up
flask seed-demo --reset    # delete it and build it again
flask seed-demo --remove   # delete it and the demo login
```

Its dates are worked out from the day it's built: the last six weeks of
sessions, two tournaments already played and one coming up. **Rebuild it
every month or two** (the same button, or `--reset`) so it still looks like a
team mid-season.

## Trying it

Once it's set up, **Try the demo** appears on the login page, the home page
and the About page. It signs the visitor in as `demo` (password `demo`, if
you'd rather give people a username and password).

The demo login is a **coach** on the demo team, so it sees everything a
coach sees, but it's read-only (`User.is_demo`, enforced with guests in
`block_guest_writes` in `app/__init__.py`). Nothing anyone does there is
saved, so people can't break it or change it for the next visitor. It also
can't link a Discord account or make public share links. A banner on every
page says it's a demo, with a link to set up their own team.

The demo login only belongs to the demo team, so it can't see any other team.

## What's in it

- 18 players, with fitness tests (two rounds), goals and coach feedback
- 10 weekly sessions (6 past with attendance, 4 to come with RSVPs), built
  from 8 drills
- 4 plays drawn in the play editor, animated: ho stack, vertical stack,
  endzone split and cup zone, plus 2 drills with animated diagrams
- Two tournaments with 6 games recorded through the stat-taker, so the stats
  pages are full, and one tournament coming up with its schedule and replies
- A scouting report on the next opponent
- Theory articles with the plays embedded

The content is in `app/demo/__init__.py`. Plays and drill diagrams are drawn
from `app/demo/diagram_specs.js` and saved in `app/demo/diagrams.json`. To
change them, edit the specs and run (fabric 5.3.0 from
`npm pack fabric@5.3.0`):

```bash
python -m app.demo.build_diagrams path/to/fabric.min.js
```

## Doing things live in a demo

The demo login can't record a game or make changes. To show that part live,
sign in with your own superadmin account and switch to the demo team, then
rebuild it afterwards.
