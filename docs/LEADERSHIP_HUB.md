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
- **Team clips**: on a clip, More → **Discuss with leaders** starts a post
  that plays that clip's section.
- **Meeting agenda**: posts marked "Add to agenda". Mark items actioned or
  take them off; "Meeting done: clear it" empties the list.
- **Handbook**: the leadership handbook (`/handbook`), now a tab of the hub.

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
`app/utils/leadership.py`, `app/templates/leadership/`,
`app/static/css/leadership.css`, `notify.post_leaders`, migration
`b6d8f0a2c4e6`, tests in `tests/test_leadership_hub.py`.
