"""Discord pages: a team's setup (add the bot, pick a channel, choose what
gets posted), players connecting their account, the site's one-off setup,
and the endpoint Discord sends button clicks to.
"""
import logging

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app import csrf, db
from app.discord import api, interactions, messages, notify
from app.models.team_organization import TeamOrganization
from app.models.team_settings import TeamSettings
from app.models.user import User
from app.utils.team_filter import get_current_team_id

logger = logging.getLogger(__name__)
discord_bp = Blueprint('discord', __name__, url_prefix='/discord')

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _settings(team_id):
    settings = TeamSettings.query.filter_by(team_id=team_id).first()
    if settings is None:
        settings = TeamSettings(team_id=team_id)
        db.session.add(settings)
        db.session.flush()
    return settings


def _require_team_admin():
    if not current_user.is_admin:
        abort(403)
    return TeamOrganization.query.get_or_404(get_current_team_id())


def _callback_url():
    return url_for('discord.callback', _external=True)


def _state(kind, team_id=None):
    """A signed state for the sign-in round trip, kept in the session too
    so it can't be replayed by someone else."""
    signer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='discord-oauth')
    state = signer.dumps({'kind': kind, 'user': current_user.id, 'team': team_id})
    session['discord_state'] = state
    return state


def _read_state(state):
    signer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='discord-oauth')
    if not state or state != session.pop('discord_state', None):
        return None
    try:
        data = signer.loads(state, max_age=900)
    except BadSignature:
        return None
    return data if data.get('user') == current_user.id else None


def _link_account(user, discord_user):
    """Point a Discord account at this login (and away from any other)."""
    discord_id = str(discord_user['id'])
    User.query.filter(User.discord_id == discord_id, User.id != user.id).update(
        {'discord_id': None, 'discord_username': None})
    user.discord_id = discord_id
    user.discord_username = api.display_name(discord_user)


# ── The team's setup ───────────────────────────────────────────────────────

@discord_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    team = _require_team_admin()
    settings = _settings(team.id)
    bot_ready = api.bot_ready()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'channel' and settings.discord_guild_id:
            channel_id = request.form.get('channel_id', '')
            try:
                allowed = {cid for cid, _ in api.text_channels(settings.discord_guild_id)}
            except api.DiscordError as e:
                flash(f"Couldn't read your server's channels. {e}", 'danger')
                return redirect(url_for('discord.settings'))
            if channel_id not in allowed:
                flash('Pick one of your server\'s text channels.', 'danger')
                return redirect(url_for('discord.settings'))
            settings.discord_notification_channel_id = channel_id
            settings.discord_enabled = True
            db.session.commit()
            ok = notify.post(team.id, messages.plain(
                f"👋 Ultimate Coach will post {team.name}'s training here. "
                "Tap the buttons on each session to say whether you're coming."), settings)
            flash('Channel saved' + (' and a hello message posted.' if ok else
                  ", but the bot couldn't post there. Check it can see and send messages in that channel."),
                  'success' if ok else 'warning')
        elif action == 'webhook':
            url = request.form.get('webhook_url', '').strip()
            if url and not api.is_webhook_url(url):
                flash('That isn\'t a Discord webhook URL. It starts with https://discord.com/api/webhooks/', 'danger')
                return redirect(url_for('discord.settings'))
            settings.discord_webhook_url = url or None
            if url:
                settings.discord_enabled = True
            db.session.commit()
            if url:
                ok = notify.post(team.id, messages.plain(f'👋 Ultimate Coach will post {team.name}\'s training here.'),
                                 settings)
                flash('Webhook saved' + (' and a test message posted.' if ok else
                      ", but posting to it failed. Check the URL."), 'success' if ok else 'warning')
            else:
                flash('Webhook removed.', 'success')
        elif action == 'posts':
            settings.discord_enabled = bool(request.form.get('discord_enabled'))
            settings.discord_notify_upcoming_events = bool(request.form.get('week_post'))
            settings.discord_notify_new_events = bool(request.form.get('new_events'))
            settings.discord_notify_new_items = bool(request.form.get('new_items'))
            day = request.form.get('week_post_day', '0')
            settings.discord_week_post_day = int(day) if day.isdigit() and int(day) < 7 else 0
            db.session.commit()
            flash('Discord settings saved.', 'success')
        elif action == 'post_week':
            sent = notify.post_week(team, settings=settings)
            flash(f'Posted {sent} session{"s" if sent != 1 else ""} for the coming week.' if sent else
                  'Nothing posted: no sessions in the next 7 days, or no channel set up yet.',
                  'success' if sent else 'info')
        elif action == 'disconnect':
            if settings.discord_guild_id and bot_ready:
                try:
                    api.leave_guild(settings.discord_guild_id)
                except api.DiscordError as e:
                    logger.info('Leaving guild %s: %s', settings.discord_guild_id, e)
            settings.discord_guild_id = settings.discord_guild_name = None
            settings.discord_notification_channel_id = None
            settings.discord_enabled = bool(settings.discord_webhook_url)
            db.session.commit()
            flash('Discord server disconnected.', 'success')
        return redirect(url_for('discord.settings'))

    channels, channel_error = [], None
    if settings.discord_guild_id and bot_ready:
        try:
            channels = api.text_channels(settings.discord_guild_id)
        except api.DiscordError as e:
            channel_error = str(e)
    db.session.commit()  # the settings row, if it was just made
    linked = User.query.filter(User.discord_id.isnot(None),
                               User.memberships.any(team_organization_id=team.id)).count()
    return render_template('discord/settings.html', team=team, settings=settings, bot_ready=bot_ready,
                           channels=channels, channel_error=channel_error, weekdays=WEEKDAYS,
                           linked=linked, target=notify.channel_target(settings))


@discord_bp.route('/add')
@login_required
def add_bot():
    """Send a team admin to Discord to add the site's bot to their server."""
    team = _require_team_admin()
    if not api.bot_ready():
        flash("The site's Discord bot isn't set up yet.", 'warning')
        return redirect(url_for('discord.settings'))
    return redirect(api.authorize_url(_state('install', team.id), _callback_url(), add_bot=True))


@discord_bp.route('/connect')
@login_required
def connect():
    """Players (and coaches) connect their Discord account by signing in."""
    if not api.bot_ready():
        flash("Discord isn't set up on this site yet.", 'warning')
        return redirect(url_for('auth.profile'))
    return redirect(api.authorize_url(_state('connect'), _callback_url()))


@discord_bp.route('/link-account')
@login_required
def link_account():
    """Old address of the connect page."""
    return redirect(url_for('discord.connect'))


@discord_bp.route('/disconnect', methods=['POST'])
@login_required
def disconnect():
    current_user.discord_id = None
    current_user.discord_username = None
    db.session.commit()
    flash('Your Discord account is no longer connected.', 'success')
    return redirect(url_for('auth.profile'))


@discord_bp.route('/callback')
@login_required
def callback():
    state = _read_state(request.args.get('state'))
    if state is None:
        flash('That Discord sign-in had expired. Please try again.', 'warning')
        return redirect(url_for('main.index'))
    if request.args.get('error'):
        flash('Discord sign-in was cancelled.', 'info')
        return redirect(url_for('discord.settings') if state['kind'] == 'install' else url_for('auth.profile'))
    try:
        token = api.exchange_code(request.args.get('code', ''), _callback_url())
        discord_user = api.signed_in_user(token['access_token'])
    except (api.DiscordError, KeyError) as e:
        flash(f'Discord sign-in failed. {e}', 'danger')
        return redirect(url_for('main.index'))

    _link_account(current_user, discord_user)
    if state['kind'] == 'install':
        if not current_user.is_admin or state.get('team') != get_current_team_id():
            db.session.commit()
            abort(403)
        guild = token.get('guild') or {}
        if not guild.get('id'):
            db.session.commit()
            flash("Discord didn't say which server the bot was added to. Please try again.", 'danger')
            return redirect(url_for('discord.settings'))
        settings = _settings(state['team'])
        settings.discord_guild_id = str(guild['id'])
        settings.discord_guild_name = (guild.get('name') or '')[:100]
        settings.discord_notification_channel_id = guild.get('system_channel_id') or None
        settings.discord_enabled = True
        if settings.discord_notify_upcoming_events is None or not settings.discord_notification_channel_id:
            settings.discord_notify_upcoming_events = True
        db.session.commit()
        flash(f"The bot is in {settings.discord_guild_name or 'your server'}. Now pick the channel it posts in.",
              'success')
        return redirect(url_for('discord.settings'))

    db.session.commit()
    flash(f"Discord connected as {current_user.discord_username}. You can now answer with Discord's buttons.",
          'success')
    return redirect(url_for('auth.profile'))


# ── The site's own setup (superadmins) ─────────────────────────────────────

@discord_bp.route('/setup', methods=['GET', 'POST'])
@login_required
def setup_guide():
    if not current_user.is_superadmin:
        if current_user.is_admin:
            return redirect(url_for('discord.settings'))
        abort(403)
    interactions_url = url_for('discord.interactions_endpoint', _external=True)
    status = {key: bool((current_app.config.get(key) or '').strip()) for key in
              ('DISCORD_CLIENT_ID', 'DISCORD_CLIENT_SECRET', 'DISCORD_BOT_TOKEN', 'DISCORD_PUBLIC_KEY')}
    app_info = None
    if request.method == 'POST' and api.bot_ready():
        try:
            api.set_interactions_url(interactions_url)
            flash('Done: Discord sends button clicks to this site now.', 'success')
        except api.DiscordError as e:
            flash(f"Discord wouldn't save it. {e}", 'danger')
        return redirect(url_for('discord.setup_guide'))
    if api.bot_ready():
        try:
            app_info = api.application()
        except api.DiscordError as e:
            flash(f"Couldn't check the bot with Discord. {e}", 'danger')
    return render_template('discord/setup_guide.html', status=status, app_info=app_info,
                           interactions_url=interactions_url, callback_url=_callback_url())


# ── Button clicks ──────────────────────────────────────────────────────────

@discord_bp.route('/interactions', methods=['POST'])
@csrf.exempt
def interactions_endpoint():
    body = request.get_data()
    if not api.bot_ready() or not api.verify_signature(request.headers.get('X-Signature-Ed25519'),
                                                       request.headers.get('X-Signature-Timestamp'), body):
        return 'invalid request signature', 401
    try:
        return jsonify(interactions.handle(request.get_json(force=True) or {}))
    except Exception:
        logger.exception('Discord interaction failed')
        db.session.rollback()
        return jsonify(interactions.reply('Something went wrong saving that. Please try again on the site.'))
