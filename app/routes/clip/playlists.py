"""Playlists: clips in a chosen order, watched back to back."""
from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.forms.clip import PlaylistForm
from app.models import Clip
from app.models.clip_playlist import ClipPlaylist, ClipPlaylistItem
from app.routes.clip import bp
from app.routes.clip.helpers import sees_hidden_clips
from app.utils.clip_video import is_veo_link
from app.utils.media_embed import youtube_id
from app.utils.team_filter import get_current_team_id


def _playlist_or_404(playlist_id):
    return ClipPlaylist.query.filter_by(
        id=playlist_id, team_organization_id=get_current_team_id()).first_or_404()


def _require_manager():
    """Coaches and admins build playlists; everyone on the team watches them."""
    if not sees_hidden_clips():
        abort(403)


def _renumber(playlist):
    for position, item in enumerate(playlist.items):
        item.position = position


def _duration(items):
    return sum(i.clip.duration for i in items if i.clip.duration)


@bp.route('/playlists')
@login_required
def playlists():
    team_id = get_current_team_id()
    lists = (ClipPlaylist.query.filter_by(team_organization_id=team_id)
             .order_by(ClipPlaylist.updated_at.desc()).all())
    sees_hidden = sees_hidden_clips()
    rows = [(p, p.visible_items(sees_hidden)) for p in lists]
    return render_template('clip/playlists.html', rows=rows, duration=_duration)


@bp.route('/playlists/new', methods=['GET', 'POST'])
@login_required
def new_playlist():
    _require_manager()
    form = PlaylistForm()
    if form.validate_on_submit():
        playlist = ClipPlaylist(title=form.title.data.strip(), description=form.description.data,
                                created_by_id=current_user.id,
                                team_organization_id=get_current_team_id())
        db.session.add(playlist)
        db.session.flush()
        clip_id = request.args.get('clip_id', type=int)
        if clip_id:
            _add_clip(playlist, clip_id)
        db.session.commit()
        flash(f'Playlist "{playlist.title}" created.', 'success')
        return redirect(url_for('clip.edit_playlist', playlist_id=playlist.id))
    return render_template('clip/playlist_form.html', form=form, playlist=None)


@bp.route('/playlists/<int:playlist_id>')
@login_required
def view_playlist(playlist_id):
    playlist = _playlist_or_404(playlist_id)
    items = playlist.visible_items(sees_hidden_clips())
    tracks = [{
        'id': item.id,
        'title': item.clip.title,
        'note': item.note or '',
        'clip_url': url_for('clip.view_clip', clip_id=item.clip.id),
        'video_id': youtube_id(item.clip.youtube_link or '') if item.clip.video_source != 'veo' else None,
        'veo_link': item.clip.youtube_link if is_veo_link(item.clip.youtube_link) else None,
        'start': item.clip.start_time or 0,
        'end': item.clip.end_time,
        'hidden': item.clip.is_hidden,
    } for item in items]
    start = request.args.get('item', type=int)
    start_index = next((i for i, t in enumerate(tracks) if t['id'] == start), 0)
    return render_template('clip/playlist_view.html', playlist=playlist, items=items,
                           tracks=tracks, start_index=start_index, total=_duration(items))


@bp.route('/playlists/<int:playlist_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_playlist(playlist_id):
    _require_manager()
    playlist = _playlist_or_404(playlist_id)
    form = PlaylistForm(obj=playlist)
    if form.validate_on_submit():
        playlist.title = form.title.data.strip()
        playlist.description = form.description.data
        db.session.commit()
        flash('Playlist saved.', 'success')
        return redirect(url_for('clip.edit_playlist', playlist_id=playlist.id))
    in_list = {item.clip_id for item in playlist.items}
    addable = [c for c in Clip.query.filter_by(team_organization_id=playlist.team_organization_id)
               .order_by(Clip.created_at.desc()).all() if c.id not in in_list]
    return render_template('clip/playlist_form.html', form=form, playlist=playlist,
                           addable=addable, total=_duration(playlist.items))


@bp.route('/playlists/<int:playlist_id>/delete', methods=['POST'])
@login_required
def delete_playlist(playlist_id):
    _require_manager()
    playlist = _playlist_or_404(playlist_id)
    title = playlist.title
    db.session.delete(playlist)
    db.session.commit()
    flash(f'Playlist "{title}" deleted. The clips themselves are untouched.', 'success')
    return redirect(url_for('clip.playlists'))


def _add_clip(playlist, clip_id):
    """Append a team clip to the playlist. Returns the clip, or None if it's
    not the team's or already in the list."""
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=playlist.team_organization_id).first()
    if not clip or any(item.clip_id == clip.id for item in playlist.items):
        return None
    last = db.session.query(func.max(ClipPlaylistItem.position)).filter_by(playlist_id=playlist.id).scalar()
    playlist.items.append(ClipPlaylistItem(clip_id=clip.id, position=(last if last is not None else -1) + 1,
                                           team_organization_id=playlist.team_organization_id))
    playlist.updated_at = datetime.utcnow()
    return clip


@bp.route('/playlists/<int:playlist_id>/items', methods=['POST'])
@login_required
def add_to_playlist(playlist_id):
    _require_manager()
    playlist = _playlist_or_404(playlist_id)
    clip_id = request.form.get('clip_id', type=int)
    clip = _add_clip(playlist, clip_id) if clip_id else None
    db.session.commit()
    if clip:
        flash(f'Added "{clip.title}" to "{playlist.title}".', 'success')
    else:
        flash('That clip is already in the playlist.', 'info')
    if request.form.get('back') == 'clip' and clip_id:
        return redirect(url_for('clip.view_clip', clip_id=clip_id))
    return redirect(url_for('clip.edit_playlist', playlist_id=playlist.id))


def _item_or_404(playlist, item_id):
    item = next((i for i in playlist.items if i.id == item_id), None)
    if item is None:
        abort(404)
    return item


@bp.route('/playlists/<int:playlist_id>/items/<int:item_id>/move/<any(up, down):direction>', methods=['POST'])
@login_required
def move_playlist_item(playlist_id, item_id, direction):
    _require_manager()
    playlist = _playlist_or_404(playlist_id)
    item = _item_or_404(playlist, item_id)
    items = list(playlist.items)
    i = items.index(item)
    j = i - 1 if direction == 'up' else i + 1
    if 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
        for position, it in enumerate(items):
            it.position = position
        playlist.updated_at = datetime.utcnow()
        db.session.commit()
    return redirect(url_for('clip.edit_playlist', playlist_id=playlist.id) + f'#item-{item.id}')


@bp.route('/playlists/<int:playlist_id>/items/<int:item_id>/remove', methods=['POST'])
@login_required
def remove_playlist_item(playlist_id, item_id):
    _require_manager()
    playlist = _playlist_or_404(playlist_id)
    item = _item_or_404(playlist, item_id)
    playlist.items.remove(item)
    _renumber(playlist)
    playlist.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f'Removed "{item.clip.title}" from the playlist.', 'info')
    return redirect(url_for('clip.edit_playlist', playlist_id=playlist.id))


@bp.route('/playlists/<int:playlist_id>/notes', methods=['POST'])
@login_required
def save_playlist_notes(playlist_id):
    """Save the "watch for" note on every item at once."""
    _require_manager()
    playlist = _playlist_or_404(playlist_id)
    for item in playlist.items:
        if f'note-{item.id}' in request.form:
            item.note = request.form[f'note-{item.id}'].strip()[:300] or None
    db.session.commit()
    flash('Notes saved.', 'success')
    return redirect(url_for('clip.edit_playlist', playlist_id=playlist.id))
