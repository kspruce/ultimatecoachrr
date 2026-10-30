"""Saving what the drill editor (static/js/drill_editor.js) draws: for a drill
(session blueprint's /api/drills) or a playbook play (/playbook/api/plays).
Both keep their stages as DrillDiagram rows, served by the session
blueprint's diagram image routes."""
import base64
import hashlib
import json

from flask import request, url_for

from app import db
from app.models.drill import DrillDiagram

EDITOR_DIAGRAM_ORDER = 1000  # after any imported diagrams
MAX_EDITOR_PNG = 5 * 1024 * 1024
MAX_EDITOR_TEXT = 2 * 1024 * 1024
MAX_EDITOR_STAGES = 20


def save_editor_diagrams(owner, source='Drill editor'):
    """Store the posted drawing as the owner's (a SavedDrill's or a Play's)
    editor diagrams: a PNG and an SVG per stage, with the editor's JSON on
    the first. Returns an error message, or None."""
    pngs = request.files.getlist('diagram')
    editor = request.form.get('editor')
    if not pngs or not editor:
        return None  # details only
    if len(pngs) > MAX_EDITOR_STAGES:
        return f'A drawing can have up to {MAX_EDITOR_STAGES} stages.'
    images = []
    for png in pngs:
        png_bytes = png.read(MAX_EDITOR_PNG + 1)
        if len(png_bytes) > MAX_EDITOR_PNG or not png_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'The diagram image is not a PNG or is too large.'
        images.append(png_bytes)
    svgs = request.form.getlist('svg')
    names = request.form.getlist('stage_name')
    notes = request.form.getlist('stage_notes')
    if len(editor) > MAX_EDITOR_TEXT or any(len(svg) > MAX_EDITOR_TEXT for svg in svgs):
        return 'The diagram is too large to save.'
    try:
        json.loads(editor)
    except ValueError:
        return 'The diagram data is not valid.'

    def item(values, i):
        return (values[i].strip() or None) if i < len(values) else None

    existing = owner.editor_diagrams
    for old in existing[len(images):]:
        owner.diagrams.remove(old)  # delete-orphan cascade removes the row
    saved = []
    for i, png_bytes in enumerate(images):
        if i < len(existing):
            diagram = existing[i]
        else:
            diagram = DrillDiagram(source=source, team_organization_id=owner.team_organization_id)
            owner.diagrams.append(diagram)
        svg = item(svgs, i)
        diagram.order = EDITOR_DIAGRAM_ORDER + i
        # A single drawing needs no "Stage 1" heading
        diagram.step_label = (item(names, i) or f'Stage {i + 1}')[:100] if len(images) > 1 else None
        diagram.caption = (item(notes, i) or '')[:255] or None
        diagram.image_data = base64.b64encode(png_bytes).decode('ascii')
        diagram.image_mime = 'image/png'
        diagram.image_hash = hashlib.sha256(png_bytes).hexdigest()
        diagram.svg_data = svg
        diagram.svg_hash = hashlib.sha256(svg.encode()).hexdigest() if svg else None
        diagram.editor_json = editor if i == 0 else json.dumps({'stage': i + 1})
        saved.append(diagram)
    db.session.flush()  # the URLs need the ids
    for diagram in saved:
        diagram.image_url = url_for('session.drill_diagram_image', diagram_id=diagram.id,
                                    filename=f'{diagram.image_hash[:16]}.png')
        diagram.svg_url = (url_for('session.drill_diagram_svg', diagram_id=diagram.id,
                                   filename=f'{diagram.svg_hash[:16]}.svg')
                           if diagram.svg_hash else None)
    return None


def data_uri(diagram):
    """The diagram's PNG inline, for the PDF export (which mustn't fetch
    from the site)."""
    if not diagram.image_data:
        return None
    return f'data:{diagram.image_mime or "image/png"};base64,{diagram.image_data}'
