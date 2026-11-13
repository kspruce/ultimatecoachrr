# Notes for Claude

## Live site (Railway)

- Hosted on Railway; it deploys from the branch the service is connected to
  (usually `main`). Run CLI commands on the live site with `railway ssh`,
  then `cd /app && export FLASK_APP=run.py`.
- **Herd 2028 team:** TeamOrganization id **6**, slug **`Herd-2028`**.
  Slug lookups are case-sensitive, so use the capital H
  (`--team Herd-2028`), even though the season plan manifest says
  `herd-2028`.

Updating Herd 2028's drills and season plan sessions:

```bash
flask import-season imports/drills/grut-drills.json --team-org 6
flask import-season imports/drills/herd-drills.json --team-org 6
flask import-season-plan imports/season-plan-export --team Herd-2028   # also rebuilds built sessions
```

Add `--dry-run` to any of them to check first without writing.
