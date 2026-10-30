# Role-based onboarding plan

> **Status: implemented.** Code lives in `app/onboarding.py` (steps and role lists),
> `app/routes/onboarding.py` (`/welcome`), `app/models/onboarding.py`, migration
> `77b543744ffe`, and `tests/test_onboarding.py`. Differences from the original plan:
>
> - **Captains run their team.** `captain` now shares the top team level with `admin`
>   (`ROLE_ORDER`, `TEAM_ADMIN_ROLES` in `app/models/user.py`), so `is_admin` is true for
>   captains on their own team. Only superadmins reach other teams, switch teams, control
>   team sign-up and use site-wide data tools. Captains and team admins can't manage each
>   other (same level); the superadmin manages everyone.
> - The welcome redirect happens only from the dashboard, so deep links (Discord, email,
>   `?next=`) are never hijacked.
> - Manual "go and look" steps tick off when opened from the checklist (`/welcome/go/<key>`).
> - Coaches can't add plays or fitness metrics (admin-only routes), so those steps sit on the
>   admin/captain lists; coaches get the game-day and squad steps instead.
> - Nudges (4.3): new users (3-30 days old) whose checklist isn't done get one email
>   listing what's left (`onboarding.send_nudges`, run nightly by `app/scheduler.py`,
>   stored in `user_onboarding.nudged_at`). It respects the account's email setting and
>   skips anyone who hid the checklist. Discord nudges are not built.
> - The How to Use guide was rewritten (4.3) from `app/help_guide.py`, which also feeds the
>   About page, the Features settings page and each checklist step's "How it works" link.

A plan for first-run onboarding for each team role: **admin, coach, captain, player**
(plus how stat takers, guests and superadmins are handled). It's written against the
code as it stands, so every step links to a route that already exists.

## What already exists

| Piece | Where | Notes |
|---|---|---|
| Roles | `app/models/user.py` `ROLE_ORDER` | guest 0, player 1, stat_taker 2, captain 3, coach 4, admin 5 |
| Role checks | `User.is_admin / is_coach / is_stat_taker`, `app/utils/utils.py` decorators, `app/utils/permissions.py` | There's no `is_captain`, and a captain can't do anything a stat taker can't |
| Admin entry | `auth.register_team` → creates the team, `role='admin'`, redirects to `team.bulk_import` | The only "onboarding" so far is that flash message |
| Player entry | `auth.join_team` (join code), `auth.accept_invite` (per-player token), `auth.add_user` | After joining, `_after_joining()` sends them to `auth.link_player` if there are unlinked roster rows |
| Feature toggles | `TeamSettings.*_enabled` | Onboarding must skip steps for features the team has turned off |
| Help page | `main.how_to_use` / `templates/how_to_use.html` | It already has step-card styles (`.htu-step`) we can reuse |

## Design principles

1. **Work out "done" from real data wherever possible.** "Import your roster" is done once
   the team has a `Player`, and "Link your profile" is done once `user.player` is set.
   That way nobody has to tick boxes, and anyone who already finished the work (existing
   teams) sees it as done straight away.
2. **Store only what can't be worked out:** whether the welcome screen has been seen,
   whether the checklist was dismissed, and steps that are just "read/look at this".
3. **One step list in code, filtered by role level and feature toggles.** No per-role
   templates to keep in sync.
4. **Never block.** Onboarding is a welcome page plus a dismissible dashboard card. No
   step is ever required to use the app.

---

## Phase 1: Foundation (data and step registry)

### 1.1 Model and migration

Add `app/models/onboarding.py`:

```python
class UserOnboarding(db.Model):
    __tablename__ = 'user_onboarding'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'),
                        unique=True, nullable=False)
    welcomed_role = db.Column(db.String(20))       # role the welcome screen was last shown for
    dismissed_at = db.Column(db.DateTime)          # checklist card hidden
    completed_steps = db.Column(db.JSON, default=list)  # manual step keys only
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- Import it in `app/models/__init__.py`.
- Migration: `flask db revision -m "add user_onboarding"` with
  `down_revision = 'd5e6f7a8b9c0'` (the current head, `add_team_colours_to_team_settings`).
- Storing `welcomed_role` instead of a boolean means a **promotion** (player → captain,
  coach → admin) shows the welcome again, for the new role.
- **Backfill in the migration:** add a row for every existing user with
  `welcomed_role = role` and `dismissed_at = now()`, so current users aren't hit with a
  welcome screen. They can still open the checklist from the user menu.
- Add `user_onboarding` to `_detach_user_rows()` in `app/routes/auth.py` (or rely on
  `ondelete='CASCADE'`) so deleting a user still works.

### 1.2 Step registry: `app/onboarding.py`

```python
@dataclass(frozen=True)
class Step:
    key: str
    title: str
    description: str
    endpoint: str                      # url_for target
    min_role: str = 'player'           # shown to this role level and above
    max_role: str | None = None        # e.g. player-only steps
    feature: str | None = None         # TeamSettings flag, e.g. 'sessions_enabled'
    check: Callable[[User, TeamOrganization], bool] | None = None  # None = manual step
    optional: bool = False
    url_kwargs: Callable | None = None # for steps that need an id

def steps_for(user, team) -> list[Step]
def progress(user, team) -> dict        # {'steps': [(step, done)], 'done': n, 'total': n, 'complete': bool}
def mark_done(user, key) / dismiss(user) / reset(user)
```

- Filter by `user.role_level()` and `team.settings.<feature>`.
- Run the `check` functions as cheap `EXISTS` queries (`.first() is not None`, the same
  as `_unlinked_players_exist`). The dashboard runs all of them on each load, so keep
  each one to a single indexed query (the `team_organization_id` indexes already exist).
- Add `is_captain` to `User` (`role_level() >= ROLE_ORDER['captain']`) for templates.

### 1.3 Tests: `tests/test_onboarding.py`

- `steps_for()` returns the right keys for each role, and drops steps whose feature is off.
- Each `check` flips to done once you create the matching row (Player, SessionRSVP, and so on).
- Promotion: changing `user.role` to a higher role makes `needs_welcome()` true again.
- Backfilled users don't get redirected.

---

## Phase 2: Surfaces (where onboarding appears)

### 2.1 Blueprint: `app/routes/onboarding.py` (`/welcome`)

| Route | Purpose |
|---|---|
| `GET /welcome` | Role-specific welcome page: short intro, what this role can do, the checklist, and a "Take me to step 1" button |
| `POST /welcome/step/<key>` | Mark a **manual** step as done (CSRF-protected form, like the rest of the app) |
| `POST /welcome/dismiss` | Hide the dashboard card |
| `POST /welcome/reset` | "Show me the getting-started guide again" (from the user menu) |

Register it in `app/__init__.py` next to the other blueprints.

### 2.2 First-login redirect

Add a `before_app_request` hook in the onboarding blueprint, or a helper called at the
end of `login`, `join_team`, `accept_invite` and `register_team`:

- If the user is authenticated, not a guest, and `welcomed_role != user.role`, redirect
  **once** to `/welcome` and set `welcomed_role` there.
- Skip static, API/JSON, logout, the `/welcome` routes themselves, and any request with
  a safe `next` param (respect deep links from Discord and emails).
- Keep the existing flows that already work: `register_team` should still go to
  `team.bulk_import` first (it's step 1 of the admin checklist anyway), and
  `_after_joining()` should still go to `link_player` first. Either let those happen and
  show `/welcome` on the next page load, or point their "Continue" button at `/welcome`.

### 2.3 Dashboard checklist card

- New partial `templates/onboarding/_checklist_card.html`, included at the top of
  `templates/index.html`.
- In `main.index`, add `onboarding = progress(current_user, team)` to the template
  context, but only if the user hasn't dismissed it and not everything is complete.
- Show a progress bar ("3 of 6 done"), each step as a link with a ✓ when done, an "I've
  done this" button for manual steps, and a ✕ to dismiss.
- Once every required step is done, show a single "You're all set 🎉" and hide the card
  automatically on the next visit.

### 2.4 User menu entry

In `base.html`'s user dropdown (around the `is_coach` / `is_admin` items), add
**"Getting started"** → `/welcome`, so dismissed users can find the guide again.

### 2.5 Better empty states

The dashboard already shows "No games scheduled. *Add one*" to coaches. Apply the same
idea to empty list pages that players see (sessions, tournaments, playbook) with
role-aware copy: coaches see "Create one", players see "Your coach hasn't added any
yet". This step is small and can be done any time.

---

## Phase 3: Role checklists (content)

Keys are stable identifiers. ✅ = auto-detected, ☐ = manual.

### Admin (team creator, `role='admin'`)

Arrives from `register_team`. Goal: a usable team with people in it.

| # | Key | Step | Link | Done when |
|---|---|---|---|---|
| 1 | `roster_imported` | Import your roster | `team.bulk_import` | ✅ team has ≥1 `Player` |
| 2 | `team_branded` | Set team colours and logo | `team.colour_settings` | ✅ `settings.primary_color` set (or ☐) |
| 3 | `features_chosen` | Turn off modules you won't use | `team.feature_settings` | ☐ |
| 4 | `staff_added` | Add a coach or captain | `auth.add_user` | ✅ another user on the team with level ≥ captain |
| 5 | `players_invited` | Turn on the join link or send invites | `auth.users` | ✅ `team.join_enabled` or any `InviteToken` for the team |
| 6 | `first_event` | Add your first tournament or game | `tournament.index` | ✅ any `Tournament` or `Game` |
| 7 | `discord` *(optional)* | Connect Discord | Discord settings | ✅ `settings.discord_enabled` |

Admins also see a **team progress panel** (Phase 4.2).

### Coach (`role='coach'`)

Usually added by an admin via `add_user`. Goal: plan and run the season.

| # | Key | Step | Link | Done when | Feature |
|---|---|---|---|---|---|
| 1 | `roster_reviewed` | Check the roster and positions | `team.index` | ☐ | |
| 2 | `first_session` | Plan your first practice | `session.index` | ✅ any `SessionPlan` | `sessions_enabled` |
| 3 | `first_drill` | Save or browse drills | drills list | ✅ any `SavedDrill` (or ☐) | `drills_enabled` |
| 4 | `first_event` | Add a tournament or game | `tournament.index` | ✅ any `Tournament`/`Game` | |
| 5 | `players_invited` | Get players signed up | `auth.users` | ✅ as for admin | |
| 6 | `first_play` *(optional)* | Add a play to the playbook | `playbook.index` | ✅ any `Play` | `playbook_enabled` |
| 7 | `fitness_setup` *(optional)* | Set up fitness tests | `fitness.manage_metrics` | ✅ any `FitnessMetric` | `fitness_enabled` |

Steps 4–5 are shared with admins. Since `min_role='coach'` includes admins, an admin
sees each shared step once.

### Captain (`role='captain'`)

Today a captain has the same powers as a stat taker. The onboarding should be honest
about that: focus on running the line on game day and keeping the team organised.

| # | Key | Step | Link | Done when | Feature |
|---|---|---|---|---|---|
| 1 | `profile_linked` | Link your player profile | `auth.link_player` | ✅ `user.player` | |
| 2 | `email_added` | Add an email for password resets | `auth.account` | ✅ `user.email` | |
| 3 | `gameday_tour` | Learn the game-day stat tracker | `gameday.index` | ☐ | `gameday_enabled` |
| 4 | `squad_checked` | Check who's coming to the next tournament | next tournament's RSVPs | ☐ | |
| 5 | `rsvp_given` | RSVP to your next session or tournament | `calendar.index` | ✅ any RSVP for `user.player` | |
| 6 | `playbook_viewed` *(optional)* | Review your positions in the playbook | `playbook.position_view` | ☐ | `playbook_enabled` |

**Decision for you:** if captains should have real extra powers (for example taking
attendance, editing lines, or posting feedback), add a `captain_required` decorator and
an `is_captain` property, apply them to those routes, and add matching steps here. That
can be a separate PR, since the checklist doesn't depend on it.

**Stat takers** get steps 1, 2, 3 and 5 from this list for free by setting
`min_role='stat_taker'` on them.

### Player (`role='player'`)

Arrives from a join link, an invite or `add_user`. Goal: linked, reachable, RSVPing.

| # | Key | Step | Link | Done when | Feature |
|---|---|---|---|---|---|
| 1 | `profile_linked` | Pick your name from the roster | `auth.link_player` | ✅ `user.player` | |
| 2 | `email_added` | Add your email | `auth.account` | ✅ `user.email` | |
| 3 | `rsvp_given` | RSVP to your next practice or tournament | `calendar.index` | ✅ any `SessionRSVP`/`TournamentRSVP` for `user.player` | |
| 4 | `stats_viewed` | See your stats | `team.player_detail(user.player.id)` | ☐ | `stats_enabled` |
| 5 | `playbook_viewed` *(optional)* | Learn your positions | `playbook.position_view` | ☐ | `playbook_enabled` |
| 6 | `fitness_goals` *(optional)* | Set a fitness goal | player goals page | ✅ any `FitnessGoal` for the player | `fitness_enabled` |
| 7 | `discord_linked` *(optional)* | Link your Discord | `discord` link_account | ✅ `user.discord_id` | team has Discord on |

Steps that need `user.player` (4 and 6) should show "Link your profile first" until
step 1 is done, instead of a broken link.

### Not onboarded

- **Guest:** read-only demo account. No redirect and no card. At most a one-line banner:
  "You're viewing a demo team."
- **Superadmin:** sees the checklist for their team role. Site tools stay outside onboarding.

---

## Phase 4: Follow-through

### 4.1 Role changes

In `auth.edit_user`, when `user.role` changes to a **higher** level, do nothing extra:
`welcomed_role != role` already triggers the welcome on their next visit. Optionally
flash "They'll see a short intro to their new role next time they log in" to the person
who made the change.

### 4.2 Team progress for admins and coaches

Add a column or badge to `auth.users` (`templates/auth/users.html`) per member:
**linked profile / has email / has RSVPed**, using the same `check` functions. Add a
dashboard tile for coaches: "8 of 22 players haven't linked their profile → view".
This is the step that gets a whole team onboarded, not just the person setting it up.
Pair it with the existing per-player invite button (`auth.create_invite`) so a coach can
nudge whoever is missing.

### 4.3 Nudges (optional, later)

- Discord or email reminder to unlinked players a few days after the join link is turned
  on, using `app/utils/email.py` / `app/discord/notifications.py`.
- Rewrite `how_to_use.html` into per-role sections and link each checklist step's
  "learn more" there.

---

## Suggested PR order

1. **PR 1: Foundation.** Model, migration with backfill, `app/onboarding.py` registry
   with all four role lists, `is_captain`, and tests. No UI yet, so it's safe to merge.
2. **PR 2: Surfaces.** `/welcome` blueprint, first-login redirect, dashboard card, user
   menu link. Smoke tests in `tests/test_smoke.py` that `/welcome` renders for each role.
3. **PR 3: Team progress.** Status on the users page and the coach dashboard tile.
4. **PR 4 (optional):** captain permissions, nudges, how-to-use rewrite.

## Testing checklist

- [ ] Register a new team → bulk import → `/welcome` shows the admin list, with roster ✓ after import
- [ ] Coach added via `add_user` → first login lands on `/welcome` with coach steps
- [ ] Player joins with a join code → `link_player` → `/welcome`, with steps 1 and 2 updating live
- [ ] Turning off `sessions_enabled` removes the session steps
- [ ] Promoting a player to captain shows the captain welcome once
- [ ] Existing users after the migration: no redirect, card hidden, "Getting started" link works
- [ ] Guest: no redirect, no card
- [ ] Deep link with `?next=` isn't hijacked by the welcome redirect
- [ ] Deleting a user with an onboarding row works
