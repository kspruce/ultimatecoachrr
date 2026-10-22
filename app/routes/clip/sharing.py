"""Share links and annotation exports."""
import csv
import io
import re
import time
from datetime import datetime

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, URLSafeSerializer

from app import db
from app.models import Clip, ClipAnnotation
from app.models.annotation import seconds_to_timestamp
from app.routes.clip import bp
from app.routes.clip.helpers import get_clip_or_404, visible_annotations
from app.utils.clip_video import shared_embed_url
from app.utils.team_filter import get_current_team_id


def get_share_serializer():
    """Serializer for generating and verifying share tokens."""
    # Different salt for safety and future rotation
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='clip-share-v1')


@bp.route('/<int:clip_id>/share_link', methods=['POST'])
@login_required
def create_share_link(clip_id):
    """
    Create a signed, time-limited share link for a clip's annotations.
    By default expires in 7 days. Adjust by sending form field 'expires_days'.
    """
    # Only allow admins/coaches or the clip creator to create share links
    team_id = get_current_team_id()
    clip = get_clip_or_404(clip_id)

    if not (current_user.is_admin or getattr(current_user, 'is_coach', False) or clip.created_by_id == current_user.id):
        return jsonify({'error': 'Not authorized'}), 403
    if clip.is_hidden:
        return jsonify({'error': 'This clip is hidden from players. Unhide it before sharing.'}), 400

    try:
        expires_days = int(request.form.get('expires_days', 7))
        expires_days = max(1, min(90, expires_days))  # clamp between 1 and 90 days
    except (ValueError, TypeError):
        expires_days = 7

    payload = {
        'clip_id': clip.id,
        'team_id': team_id,
        'v': clip.share_version or 0,
        'exp': int(time.time()) + expires_days * 86400  # unix timestamp expiry
    }
    s = get_share_serializer()
    token = s.dumps(payload)

    share_url = url_for('clip.shared_clip_view', token=token, _external=True)
    return jsonify({'url': share_url, 'expires_days': expires_days})


@bp.route('/<int:clip_id>/revoke_share_links', methods=['POST'])
@login_required
def revoke_share_links(clip_id):
    """Invalidate every share link handed out for this clip so far."""
    clip = get_clip_or_404(clip_id)
    if not (current_user.is_admin or getattr(current_user, 'is_coach', False) or clip.created_by_id == current_user.id):
        abort(403)
    clip.share_version = (clip.share_version or 0) + 1
    db.session.commit()
    flash(f'Existing share links for "{clip.title}" no longer work.', 'info')
    return redirect(url_for('clip.view_clip', clip_id=clip.id))


@bp.route('/share/<token>')
def shared_clip_view(token):
    """
    Public, read-only view of a clip and its annotations, accessible via signed token.
    No login required.
    """
    s = get_share_serializer()
    try:
        data = s.loads(token)
    except BadSignature:
        return render_template('error.html', error_message='This share link is not valid.'), 400

    # Check expiry
    if int(time.time()) > int(data.get('exp', 0)):
        return render_template('error.html', error_message='This share link has expired.'), 410

    clip_id = data.get('clip_id')
    team_id = data.get('team_id')
    if not clip_id or not team_id:
        return render_template('error.html', error_message='This share link is not valid.'), 400

    # Enforce team scoping
    clip = Clip.query.filter_by(id=clip_id, team_organization_id=team_id).first_or_404()
    if clip.is_hidden:
        abort(404)
    if data.get('v', 0) != (clip.share_version or 0):
        return render_template('error.html', error_message='This share link has been revoked.'), 410

    # Shared views only expose 'team' annotations — never coaches-only or private
    annotations = (ClipAnnotation.query
                   .filter_by(clip_id=clip.id, visibility='team')
                   .order_by(ClipAnnotation.timestamp).all())

    embed_url = shared_embed_url(clip)

    # Human-readable expiry
    expires_at = datetime.fromtimestamp(int(data['exp']))

    return render_template(
        'clip/shared_clip.html',
        clip=clip,
        annotations=annotations,
        embed_url=embed_url,
        expires_at=expires_at,
        seconds_to_timestamp=seconds_to_timestamp  # pass helper for formatting
    )


@bp.route('/export_annotations_md/<int:clip_id>')
@login_required
def export_annotations_markdown(clip_id):
    """
    Export annotations as Markdown for easy sharing/pasting.
    """
    clip = get_clip_or_404(clip_id)

    md_query = visible_annotations(ClipAnnotation.query.filter_by(clip_id=clip.id))
    annotations = md_query.order_by(ClipAnnotation.timestamp).all()

    lines = []
    lines.append(f"# {clip.title}")
    if clip.game:
        g_date = clip.game.date.strftime('%Y-%m-%d') if clip.game.date else ''
        lines.append(f"- Game: vs {clip.game.opponent}{f' ({g_date})' if g_date else ''}")
    if clip.point:
        lines.append(f"- Point: {clip.point.point_number}")
    if clip.youtube_link:
        lines.append(f"- Video: {clip.youtube_link}")
    lines.append("")  # blank line
    lines.append("## Annotations")
    lines.append("")

    for a in annotations:
        ts = seconds_to_timestamp(a.timestamp)
        title = a.title or ''
        event = (a.event_type.replace('_', ' ').title() if a.event_type else '')
        tags_str = ', '.join([t.name for t in a.tags]) if a.tags else ''
        players_str = ', '.join([p.name for p in a.players]) if a.players else ''
        creator = a.created_by.username if a.created_by else 'Unknown'
        key = " ⭐" if a.is_key_moment else ""
        notes = a.notes or ""

        lines.append(f"- [{ts}] {title}{key}")
        meta_bits = []
        if event: meta_bits.append(event)
        if tags_str: meta_bits.append(f"Tags: {tags_str}")
        if players_str: meta_bits.append(f"Players: {players_str}")
        meta_bits.append(f"By: {creator}")
        lines.append("  - " + " | ".join(meta_bits))
        if notes:
            # indent notes as a block
            for line in notes.splitlines():
                lines.append(f"  > {line}")
        lines.append("")  # blank line between annotations

    md = "\n".join(lines)
    return current_app.response_class(md, mimetype='text/markdown')


@bp.route('/export_annotations_csv/<int:clip_id>')
@login_required
def export_annotations_csv(clip_id):
    """Export clip annotations to CSV"""
    clip = get_clip_or_404(clip_id)

    csv_query = visible_annotations(ClipAnnotation.query.filter_by(clip_id=clip.id))
    annotations = csv_query.order_by(ClipAnnotation.timestamp).all()

    # Create a file-like buffer
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    
    # Write header with clip information
    writer.writerow(['Clip Information'])
    writer.writerow(['Title', clip.title])
    
    if clip.game:
        writer.writerow(['Game', f'vs {clip.game.opponent}'])
        if clip.game.date:
            writer.writerow(['Date', clip.game.date.strftime('%Y-%m-%d')])
    
    if clip.point:
        writer.writerow(['Point', clip.point.point_number])
    
    writer.writerow(['Video Link', clip.youtube_link])
    writer.writerow([])  # Empty row as separator
    
    # Write annotations header
    writer.writerow(['Timestamp', 'Title', 'Event Type', 'Our Score', 'Their Score', 
                    'Offense', 'Defense', 'Tags', 'Players', 'Creator', 'Key Moment', 'Notes'])
    
    # Write annotation data
    for annotation in annotations:
        # Format offense for display
        offense_display = ""
        if annotation.offense == 'horo':
            offense_display = "Horizontal"
        elif annotation.offense == 'vert':
            offense_display = "Vertical"
        elif annotation.offense == 'flow':
            offense_display = "Flow"
        else:
            offense_display = annotation.offense or ""
            
        # Format defense for display
        defense_display = ""
        if annotation.defense == 'match_flick':
            defense_display = "Match Flick"
        elif annotation.defense == 'match_backhand':
            defense_display = "Match Backhand"
        elif annotation.defense == 'match_middle':
            defense_display = "Match Middle"
        elif annotation.defense == 'zone':
            defense_display = "Zone"
        else:
            defense_display = annotation.defense or ""
        
        # Get tags
        tags_str = ', '.join([tag.name for tag in annotation.tags]) if annotation.tags else ''
        
        # Get players
        players_str = ', '.join([f"{p.name} (#{p.jersey_number})" for p in annotation.players]) if annotation.players else ''
        
        # Get creator
        creator = annotation.created_by.username if annotation.created_by else 'Unknown'
        
        writer.writerow([
            seconds_to_timestamp(annotation.timestamp),
            annotation.title or '',
            annotation.event_type.replace('_', ' ').title() if annotation.event_type else '',
            annotation.our_score or '',
            annotation.their_score or '',
            offense_display,
            defense_display,
            tags_str,
            players_str,
            creator,
            'Yes' if annotation.is_key_moment else 'No',
            annotation.notes or ""
        ])
    
    # Move to beginning of file
    buffer.seek(0)
    
    # Create filename with clip title (sanitized) and date
    safe_title = re.sub(r'[^\w\s-]', '', clip.title).strip().replace(' ', '_')
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f"{safe_title}_{date_str}_annotations.csv"
    
    return send_file(
        io.BytesIO(buffer.getvalue().encode()),
        as_attachment=True,
        download_name=filename,
        mimetype='text/csv'
    )
