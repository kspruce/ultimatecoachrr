# Setting up email

Email is optional. Without it everything still works:

- Coaches make **password reset links** from User Management and send them however they like (WhatsApp, text, etc.).
- You copy **team sign-up links** from Team Sign-ups and send them yourself.

Once email is set up, the site also:

- emails a reset link when someone uses **Forgot password?** on the login page (if their account has an email address),
- emails team sign-up links when you enter an address,
- emails `ADMIN_EMAIL` whenever a new team registers.

> **Railway blocks SMTP below its Pro plan** (you'll see `Network is unreachable`).
> Use Brevo or Resend below: they send over HTTPS, which isn't blocked.

## Option A: Brevo (recommended, no domain needed)

Free for 300 emails a day. You can send from a Gmail address.

1. Sign up at https://www.brevo.com.
2. **Senders, Domains & Dedicated IPs → Senders → Add a sender**: enter the address to send from
   (e.g. `ultimatecoach00@gmail.com`) and click the confirmation link Brevo emails to it.
3. **SMTP & API → API Keys → Generate a new API key**, name it `Ultimate Coach`, copy it.
   (Brevo may ask you to activate the transactional email platform first; follow its prompts.)
4. In Railway → your app service → **Variables**:

| Variable | Value |
|---|---|
| `BREVO_API_KEY` | the API key (starts with `xkeysib-`) |
| `MAIL_DEFAULT_SENDER` | `Ultimate Coach <ultimatecoach00@gmail.com>` (must be the sender you verified) |
| `ADMIN_EMAIL` | where you want new-team alerts |

Any `MAIL_SERVER`/`MAIL_*` SMTP variables can stay or go: an API key takes priority.

Sending from a `@gmail.com` address through another service can land in spam more often.
Once you own a domain, verify it in Brevo (Senders, Domains → Domains) and send from
an address on it.

## Option B: Resend (needs your own domain)

Free for 3,000 emails a month. Add your domain at https://resend.com/domains (a few DNS
records), create an API key, then set `RESEND_API_KEY` and
`MAIL_DEFAULT_SENDER=Ultimate Coach <coach@yourdomain.com>`.

## Option C: SMTP (Railway Pro or another host)

| Variable | Example |
|---|---|
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `587` (or `465` with `MAIL_USE_SSL=true`, `MAIL_USE_TLS=false`) |
| `MAIL_USE_TLS` | `true` |
| `MAIL_USERNAME` | `ultimatecoach00@gmail.com` |
| `MAIL_PASSWORD` | for Gmail, a 16-character [App Password](https://myaccount.google.com/apppasswords) (needs 2-Step Verification) |
| `MAIL_DEFAULT_SENDER` | `Ultimate Coach <ultimatecoach00@gmail.com>` |

## Test it

Log in as superadmin → menu → **Team Sign-ups** → **Email** → **Send test email**.
If it fails, the error from the email service is shown on the page, for example:

- `api.brevo.com said 401`: the API key is wrong.
- `api.brevo.com said 400 ... sender ... not valid`: `MAIL_DEFAULT_SENDER` isn't a verified Brevo sender.
- `Network is unreachable`: SMTP is blocked; use Brevo or Resend.

Then ask your players to add an email address under **Account Settings** so they can reset their own passwords.
