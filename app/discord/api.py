"""Talking to Discord over its HTTP API.

The site runs one Discord application (bot) for every team. The site's
owner creates it once in the Discord developer portal and sets four
variables:

  DISCORD_CLIENT_ID      the application's ID
  DISCORD_CLIENT_SECRET  its OAuth2 client secret
  DISCORD_BOT_TOKEN      its bot token
  DISCORD_PUBLIC_KEY     its public key (checks button clicks came from Discord)

Teams then add the bot to their server with one click, and players connect
their Discord account by signing in with it. Button clicks arrive at
/discord/interactions as signed HTTP requests, so nothing has to stay
connected to Discord: there is no gateway connection or bot thread.

Teams can instead paste a channel webhook URL; posts then go out without
buttons.
"""
import logging
import time
from urllib.parse import urlencode

import requests
from flask import current_app

logger = logging.getLogger(__name__)

API = 'https://discord.com/api/v10'
TIMEOUT = 10
# View channel, send messages, embed links, read message history
BOT_PERMISSIONS = 1024 | 2048 | 16384 | 65536
TEXT_CHANNEL_TYPES = (0, 5)  # text and announcement channels


class DiscordError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _config(key):
    return (current_app.config.get(key) or '').strip()


def bot_ready():
    """Is the site's Discord application set up (so teams get one-click setup
    and players get buttons)?"""
    return all(_config(k) for k in ('DISCORD_CLIENT_ID', 'DISCORD_CLIENT_SECRET',
                                    'DISCORD_BOT_TOKEN', 'DISCORD_PUBLIC_KEY'))


def _request(method, url, retry=True, **kwargs):
    kwargs.setdefault('timeout', TIMEOUT)
    try:
        response = requests.request(method, url, **kwargs)
    except requests.RequestException as e:
        raise DiscordError(f'Could not reach Discord: {e}') from e
    if response.status_code == 429 and retry:
        wait = min(float((response.json() or {}).get('retry_after', 1)), 10)
        time.sleep(wait)
        return _request(method, url, retry=False, **kwargs)
    if response.status_code >= 400:
        try:
            message = response.json().get('message', response.text)
        except ValueError:
            message = response.text
        raise DiscordError(f'Discord said: {message} ({response.status_code})', response.status_code)
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def bot(method, path, **kwargs):
    headers = {'Authorization': f"Bot {_config('DISCORD_BOT_TOKEN')}"}
    return _request(method, API + path, headers=headers, **kwargs)


# ── Messages ───────────────────────────────────────────────────────────────

def send_channel(channel_id, payload):
    return bot('POST', f'/channels/{channel_id}/messages', json=payload)


def send_dm(discord_user_id, payload):
    channel = bot('POST', '/users/@me/channels', json={'recipient_id': str(discord_user_id)})
    return send_channel(channel['id'], payload)


def send_webhook(url, payload):
    """Post through a channel webhook. Webhooks can't carry buttons, so any
    are left off (messages built in messages.py also link to the site)."""
    payload = {k: v for k, v in payload.items() if k != 'components'}
    payload.setdefault('username', 'Ultimate Coach')
    return _request('POST', url, json=payload, params={'wait': 'true'})


def is_webhook_url(url):
    return bool(url) and url.startswith(('https://discord.com/api/webhooks/',
                                         'https://discordapp.com/api/webhooks/',
                                         'https://ptb.discord.com/api/webhooks/',
                                         'https://canary.discord.com/api/webhooks/'))


# ── Servers ────────────────────────────────────────────────────────────────

def guild(guild_id):
    return bot('GET', f'/guilds/{guild_id}')


def text_channels(guild_id):
    """[(id, name)] of the server's text channels, in the server's order."""
    channels = bot('GET', f'/guilds/{guild_id}/channels') or []
    channels = [c for c in channels if c.get('type') in TEXT_CHANNEL_TYPES]
    channels.sort(key=lambda c: (c.get('position', 0), c['name']))
    return [(c['id'], c['name']) for c in channels]


def leave_guild(guild_id):
    return bot('DELETE', f'/users/@me/guilds/{guild_id}')


# ── Signing in with Discord ────────────────────────────────────────────────

def authorize_url(state, redirect_uri, add_bot=False):
    """Where to send someone to sign in with Discord (and, with add_bot, to
    add the site's bot to a server they run)."""
    params = {'client_id': _config('DISCORD_CLIENT_ID'), 'response_type': 'code',
              'redirect_uri': redirect_uri, 'state': state, 'prompt': 'none',
              'scope': 'identify bot' if add_bot else 'identify'}
    if add_bot:
        params['permissions'] = str(BOT_PERMISSIONS)
        params['prompt'] = 'consent'
    return 'https://discord.com/oauth2/authorize?' + urlencode(params)


def exchange_code(code, redirect_uri):
    """The token response for a sign-in code. After adding the bot it also
    holds the server ('guild') it was added to."""
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri}
    return _request('POST', API + '/oauth2/token', data=data,
                    auth=(_config('DISCORD_CLIENT_ID'), _config('DISCORD_CLIENT_SECRET')))


def signed_in_user(access_token):
    return _request('GET', API + '/users/@me', headers={'Authorization': f'Bearer {access_token}'})


def display_name(user):
    return (user.get('global_name') or user.get('username') or '')[:100]


# ── The application itself (site setup) ───────────────────────────────────

def application():
    return bot('GET', '/applications/@me')


def set_interactions_url(url):
    """Point the application's button clicks at this site. Discord checks
    the URL answers its signed ping before saving it."""
    return bot('PATCH', '/applications/@me', json={'interactions_endpoint_url': url})


def verify_signature(signature, timestamp, body):
    """Did Discord sign this request (Ed25519 over timestamp + body)?"""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(_config('DISCORD_PUBLIC_KEY')))
        key.verify(bytes.fromhex(signature or ''), (timestamp or '').encode() + body)
        return True
    except (InvalidSignature, ValueError):
        return False
