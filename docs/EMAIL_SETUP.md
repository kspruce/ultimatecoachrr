# Setting up email

Email is optional. Without it everything still works:

- Coaches make **password reset links** from User Management and send them however they like (WhatsApp, text, etc.).
- You copy **team sign-up links** from Team Sign-ups and send them yourself.

Once email is set up, the site also:

- emails a reset link when someone uses **Forgot password?** on the login page (if their account has an email address),
- emails team sign-up links when you enter an address,
- emails `ADMIN_EMAIL` whenever a new team registers.

## 1. Pick a sending service

Any service that offers SMTP will do. Good options with a free tier:

| Service | Free tier | Notes |
|---|---|---|
| [Brevo](https://www.brevo.com) | 300 emails/day | Easiest: works without your own domain to start with |
| [Resend](https://resend.com) | 3,000 emails/month | Needs a domain you own (add a few DNS records) |
| Gmail | ~500/day | Needs 2-step verification and an [App Password](https://myaccount.google.com/apppasswords). Fine for a small site |

For a site used by teams around the world, sending from your own domain (with the DNS records the service gives you) keeps emails out of spam folders.

## 2. Add the settings in Railway

Railway → your app service → **Variables**:

| Variable | Example | |
|---|---|---|
| `MAIL_SERVER` | `smtp-relay.brevo.com` | SMTP host from your provider |
| `MAIL_PORT` | `587` | 587 for TLS (most providers), 465 for SSL |
| `MAIL_USE_TLS` | `true` | Use with port 587 |
| `MAIL_USE_SSL` | `false` | Set `true` (and TLS `false`) for port 465 |
| `MAIL_USERNAME` | your SMTP login | |
| `MAIL_PASSWORD` | your SMTP password / API key | |
| `MAIL_DEFAULT_SENDER` | `Ultimate Coach <coach@yourdomain.com>` | Must be an address your provider lets you send from |
| `ADMIN_EMAIL` | your address | Gets new-team alerts |

Provider SMTP hosts: Brevo `smtp-relay.brevo.com`, Resend `smtp.resend.com` (username `resend`, password = API key), Gmail `smtp.gmail.com`.

Railway redeploys automatically when you save variables.

## 3. Test it

Log in as superadmin → menu → **Team Sign-ups** → **Email** → **Send test email**. If it fails, the error from the mail server is shown on the page.

Then ask your players to add an email address under **Account Settings** so they can reset their own passwords.
