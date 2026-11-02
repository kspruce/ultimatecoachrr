# Leadership hub

A private space for coaches, captains and team admins to share ideas,
articles and footage, talk them over, and plan leadership meetings. The
leadership handbook lives inside it.

## Turning it on

Team settings → Features → **Leadership hub** (the existing
`leadership_handbook_enabled` switch; off by default). Players, stat takers,
guests and other teams get a 404 on every page.

## What's in it (`/leadership`)

- **Discussion**: posts of four kinds (Idea, Article, Footage, Question),
  each with an optional link and a reply thread. Pinned posts first, then
  latest activity. Filter by kind or status (Open / Actioned / Archived) and
  search posts and replies. Unread posts and new replies are marked, with a
  count on the nav link.
- **Footage**: YouTube links play in the page from the "start at" time
  (or the link's own `t=`). Veo links open on Veo. Times like `3:42` in a
  post or reply jump the video there.
- **Discuss with leaders**: clips, plays, theory topics, drills and session
  plans have a button that starts a post about that thing. For a clip, the
  post plays that part of the clip.
- **Meeting agenda**: posts marked "Add to agenda". Mark items actioned or
  take them off; "Meeting done: clear it" empties the list.
- **Handbook**: the leadership handbook (`/handbook`), now a tab of the hub.

## Ask the leaders (players)

Players (not guests) see **Ask the leaders** on the same pages. They can
also ask about anything from **My Questions** (in the Training menu, and on
their own profile under Development) at `/questions`.

- A player can only ask about things they can see. Draft plays, hidden
  clips, unpublished theory and other teams' things are left off the
  question.
- The question shows in the hub with the tag *Asked by …*, under the
  **From players** filter. The feed counts the player questions still
  waiting for a reply.
- On a player's question, leaders choose **Reply to <player>**, which the
  player sees, or **Leaders-only note**, which only leaders see.
- The player sees their question, the replies to them, and a badge when
  there's a new answer. If they've connected Discord, they also get a
  Discord message. They can follow up, which re-opens a closed question, and
  delete a question that nobody has answered yet.
- Only the asker and the leaders can see a question. Other players, stat
  takers and other teams get a 404.

Anyone in the leadership group can pin, change status or add to the agenda.
Authors edit and delete their own posts and replies. Team admins
(captains included) can edit or delete anyone's.

## Discord (optional)

Discord settings → **Leadership hub channel**: pick a channel in the
bot's server or paste a webhook. New posts and replies go there, and only
there. The team channel (or its webhook) can't be chosen, and with no leaders'
channel set nothing is sent.

## Code

`app/models/leadership.py`, `app/routes/leadership.py`,
`app/utils/leadership.py`, `app/templates/leadership/`, `app/routes/questions.py`,
`app/utils/ask_leaders.py` (what a question can be about), `app/templates/questions/`,
`app/static/css/leadership.css`, `notify.post_leaders`, migrations
`b6d8f0a2c4e6` and `c7e9a1b3d5f7`, tests in `tests/test_leadership_hub.py` and
`tests/test_ask_leaders.py`.
