# Railway Migration Guide

## What's Changing

| | Before | After |
|---|---|---|
| App hosting | EC2 via Applikku | Railway |
| Database | PostgreSQL on EC2 | Railway managed Postgres |
| File storage | AWS S3 | **AWS S3 (unchanged)** |
| Domain | ultimatecoach.applikuapp.com | Custom domain via Railway |

Your S3 bucket stays exactly as-is — no file migration needed.

---

## Step 1: Prep your repo

The following files have already been added/updated:

- `Procfile` — already existed and is correct (`web: gunicorn run:app`, `release: flask db upgrade`)
- `railway.toml` — added (tells Railway how to build and run)
- `config.py` — fixed `DATA_EXPORT_DIR` default from `/app/data_exports` → `/tmp/data_exports`

**Commit and push these changes to GitHub before continuing.**

```bash
git add Procfile railway.toml config.py
git commit -m "chore: railway deployment config"
git push
```

---

## Step 2: Create your Railway project

1. Go to [railway.app](https://railway.app) and sign up / log in
2. Click **New Project** → **Deploy from GitHub repo**
3. Authorize Railway to access your GitHub, then select your repo
4. Railway will detect the Python app and start building — let it fail for now (no env vars yet)

---

## Step 3: Add a PostgreSQL database

1. In your Railway project, click **+ New** → **Database** → **Add PostgreSQL**
2. Railway creates a Postgres instance and automatically sets `DATABASE_URL` in your app's environment
3. No extra config needed — your `config.py` already reads `DATABASE_URL` and handles the `postgres://` → `postgresql://` fix

---

## Step 4: Set environment variables

In Railway → your app service → **Variables**, add the following. Copy values from your current `.env` file:

```
SECRET_KEY=<your secret key>
FLASK_ENV=production
FLASK_DEBUG=0

# AWS S3 — keep using your existing bucket
AWS_ACCESS_KEY=<your key>
AWS_SECRET_KEY=<your secret>
AWS_REGION=us-east-1
AWS_BUCKET_NAME=<your bucket>

# Optional
BASE_URL=https://<your-app>.railway.app   # update after deploy
TEAM_REGISTRATION_CODE=<if you use one>
MAIL_SERVER=<if configured>
MAIL_PORT=<if configured>
MAIL_USERNAME=<if configured>
MAIL_PASSWORD=<if configured>
ADMIN_EMAIL=<your email>
```

> `DATABASE_URL` is set automatically by the Railway Postgres plugin — don't add it manually.

---

## Step 5: Migrate your existing data using the built-in export/import tool

Your app has a built-in data migration tool at `/admin/enhanced-data-management`. Use it — no `pg_dump` or command-line tools needed.

### Part A — Export from your current site (on EC2/Applikku)

1. Log in to your **current site** as admin
2. Go to `/admin/enhanced-data-management`
3. Click **Export JSON ZIP** — this downloads a `.zip` file containing all your data as JSON files, one per table
4. Save the ZIP to your computer

### Part B — Import into Railway after deploy

> Complete Steps 6 (redeploy) first so the Railway database is set up and all tables exist.

1. Log in to your **Railway app** as admin
2. Go to `/admin/enhanced-data-management`
3. Under **Import**, upload the ZIP file you downloaded in Part A
4. Leave "Clear existing data" **unchecked** (the Railway DB is already empty)
5. Click import — the tool will import all tables in the correct dependency order and **automatically reset PostgreSQL sequences** when done

> The sequence reset at the end is important — it ensures new records created after the import don't collide with the imported IDs. Your app handles this automatically.

---

## Step 6: Trigger a redeploy

After setting all env vars, Railway should auto-deploy. If not:

Railway → your app service → **Deployments** → **Redeploy**

Watch the deploy logs. You should see:
- `flask db upgrade` running (from the `release` command in Procfile)
- `gunicorn` starting successfully

---

## Step 7: Test your app

1. Railway gives you a public URL like `https://your-app.up.railway.app`
2. Open it and test: log in, check that file uploads to S3 work, verify the database has your data
3. Hit the `/debug-info` endpoint to confirm S3 and DB are connected correctly

---

## Step 8: Connect your custom domain

1. Buy/transfer your domain if needed, or use your existing one
2. Railway → your app service → **Settings** → **Networking** → **Custom Domain**
3. Add your domain (e.g. `ultimatecoach.com`)
4. Railway shows you a CNAME record to add in your DNS provider
5. Add the CNAME, wait for DNS to propagate (~5–60 min)
6. Update `BASE_URL` in Railway env vars to your custom domain

---

## Step 9: Shut down Applikku + EC2

Once you've confirmed the Railway app is working:

1. Update any DNS records pointing to the EC2 IP to point to Railway instead
2. Cancel your Applikku subscription
3. Stop/terminate your EC2 instance
4. (Optional) keep S3 — you're already paying for it and Railway uses it too

---

## Costs

| Service | Estimated cost |
|---|---|
| Railway Hobby plan | ~$5/month |
| Railway Postgres | ~$5/month (or free on Hobby for small DBs) |
| AWS S3 | unchanged (typically < $1–2/month for a small app) |

---

## Troubleshooting

**Build fails:** Check that `requirements.txt` is committed. Railway uses Nixpacks to auto-detect Python.

**`flask db upgrade` fails on deploy:** Check `DATABASE_URL` is set correctly in Railway Variables.

**S3 uploads not working:** Confirm `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `AWS_BUCKET_NAME` are set in Railway Variables.

**App crashes on start:** Check Railway deploy logs. The `/debug-info` endpoint is useful once the app is partially up.
