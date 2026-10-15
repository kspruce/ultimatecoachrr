"""Import a season of session plans, drills, standard cards and drill diagrams
from a "herd-session-v1" JSON file. Used by `flask import-season`.

The import is an upsert keyed on external_id (per team):
  1. SavedDrills (drills, then cards) are created or updated, and each drill's
     diagrams are rebuilt if the files or their labels changed.
  2. SessionPlans are created or updated.
  3. Each imported session's components are rebuilt, in order, if they changed.

Nothing that isn't in the file is ever deleted. Running the same file twice
reports everything as unchanged. Everything is validated before anything is
written, and the whole import is one transaction (rolled back for dry runs).
"""
import base64
import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from flask import current_app
from sqlalchemy import func

from app import db
from app.models.drill import SavedDrill, DrillDiagram
from app.models.session import SessionPlan, SessionComponent

SCHEMA = 'herd-session-v1'
SQUADS = {'joint', '1s', '2s'}
SESSION_TYPES = {value for value, _ in SessionPlan.SESSION_TYPE_CHOICES}
RASTER_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.gif': 'image/gif', '.webp': 'image/webp'}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Column lengths, checked up front so a long title fails validation rather
# than half-way through a Postgres transaction.
DRILL_LIMITS = {'external_id': 100, 'title': 100, 'source': 200, 'card_code': 20,
                'focus_area': 100, 'equipment_needed': 200, 'skill_level': 20}
SESSION_LIMITS = {'external_id': 100, 'title': 100, 'season': 20, 'phase_name': 100,
                  'block': 200, 'squad': 10, 'run_by': 100, 'kit': 255,
                  'location': 100, 'focus_area': 100}
COMPONENT_LIMITS = {'title': 100, 'focus_area': 100}
DIAGRAM_LIMITS = {'caption': 255, 'step_label': 100, 'source': 100}


class SeasonImportError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('\n'.join(errors))


@dataclass
class ImportSummary:
    dry_run: bool = False
    counts: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)

    def record(self, kind, status, label):
        self.counts.setdefault(kind, {'created': 0, 'updated': 0, 'unchanged': 0})
        self.counts[kind][status] += 1
        if status != 'unchanged':
            self.lines.append(f'{status:>9}  {kind:<10} {label}')

    def report(self):
        out = ['DRY RUN: nothing was written' if self.dry_run else 'Import complete']
        out.extend(self.lines)
        for kind, c in self.counts.items():
            out.append(f"{kind}: {c['created']} created, {c['updated']} updated, "
                       f"{c['unchanged']} unchanged")
        return '\n'.join(out)


class _IdAllocator:
    """The app assigns ids as max(id)+1 (see add_session/add_drill in
    routes/session.py) because the Postgres sequences are not trusted after
    the data move. Do the same here, handing out ids without flushing."""

    def __init__(self):
        self._next = {}

    def __call__(self, model):
        if model not in self._next:
            self._next[model] = (db.session.query(func.max(model.id)).scalar() or 0) + 1
        value = self._next[model]
        self._next[model] += 1
        return value


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _check_lengths(errors, where, values, limits):
    for key, limit in limits.items():
        value = values.get(key)
        if isinstance(value, str) and len(value) > limit:
            errors.append(f'{where}: {key} is {len(value)} characters (max {limit})')


def _parse_date(value, where, errors, key):
    if value in (None, ''):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        errors.append(f'{where}: {key} must be YYYY-MM-DD, got {value!r}')
        return None


def _parse_time(value, where, errors, key):
    if value in (None, ''):
        return None
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        errors.append(f'{where}: {key} must be HH:MM, got {value!r}')
        return None


def _optional_int(value, where, errors, key):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f'{where}: {key} must be a whole number, got {value!r}')
        return None
    return value


def _load_file(images_dir, rel_path, where, errors, svg=False):
    """Read and check one diagram file. Returns (bytes, mime) or None."""
    if not isinstance(rel_path, str) or not rel_path:
        errors.append(f'{where}: file path missing')
        return None
    if images_dir is None:
        errors.append(f'{where}: has diagrams but no --images-dir was given')
        return None
    root = os.path.realpath(images_dir)
    path = os.path.realpath(os.path.join(root, rel_path))
    if os.path.commonpath([root, path]) != root:
        errors.append(f'{where}: {rel_path} is outside --images-dir')
        return None
    if not os.path.isfile(path):
        errors.append(f'{where}: file not found: {rel_path}')
        return None
    ext = os.path.splitext(path)[1].lower()
    if svg:
        if ext != '.svg':
            errors.append(f'{where}: svg must be a .svg file, got {rel_path}')
            return None
        mime = 'image/svg+xml'
    else:
        if ext not in RASTER_TYPES:
            errors.append(f'{where}: {rel_path} must be one of {", ".join(sorted(RASTER_TYPES))}')
            return None
        mime = RASTER_TYPES[ext]
    if os.path.getsize(path) > MAX_IMAGE_BYTES:
        errors.append(f'{where}: {rel_path} is larger than {MAX_IMAGE_BYTES // (1024 * 1024)}MB')
        return None
    with open(path, 'rb') as f:
        data = f.read()
    if svg:
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            errors.append(f'{where}: {rel_path} is not UTF-8 text')
            return None
        if '<svg' not in text:
            errors.append(f'{where}: {rel_path} does not look like an SVG')
            return None
    else:
        from PIL import Image
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception:
            errors.append(f'{where}: {rel_path} is not a readable image')
            return None
    return data, mime


def _cards_description(card):
    """Cards are stored as SavedDrills; their summary and sections become a
    Markdown description so the existing drill pages show them."""
    parts = []
    if card.get('summary'):
        parts.append(card['summary'].strip())
    for section in card.get('sections') or []:
        heading = (section.get('heading') or '').strip()
        lines = [f'- {line}' for line in section.get('lines') or []]
        block = (f'**{heading}**\n\n' if heading else '') + '\n'.join(lines)
        parts.append(block.strip())
    return '\n\n'.join(p for p in parts if p) or None


def _notes_markdown(notes):
    if notes is None:
        return None
    if isinstance(notes, str):
        return notes or None
    return '\n'.join(f'- {n}' for n in notes) or None


def _prepare(data, images_dir, team_org_id):
    """Validate the whole file and turn it into plain dicts ready to write.
    Raises SeasonImportError listing every problem found."""
    errors = []
    if not isinstance(data, dict):
        raise SeasonImportError(['top level must be a JSON object'])
    if data.get('schema') != SCHEMA:
        errors.append(f'schema must be {SCHEMA!r}, got {data.get("schema")!r}')
    season = data.get('season')
    if not isinstance(season, str) or not season:
        errors.append('season is required, e.g. "2027/28"')

    drills = []
    seen_drills = set()

    def add_drill(raw, where, is_card):
        ext = raw.get('external_id')
        if not isinstance(ext, str) or not ext:
            errors.append(f'{where}: external_id is required')
            return
        where = f'{where} {ext}'
        if ext in seen_drills:
            errors.append(f'{where}: duplicate external_id')
        seen_drills.add(ext)
        if not raw.get('title'):
            errors.append(f'{where}: title is required')
        values = {
            'external_id': ext,
            'title': raw.get('title'),
            'source': raw.get('source'),
            'focus_area': raw.get('focus_area'),
            'equipment_needed': raw.get('equipment_needed'),
            'skill_level': raw.get('skill_level'),
            'recommended_duration': _optional_int(raw.get('recommended_duration'), where, errors,
                                                  'recommended_duration'),
            'min_players': _optional_int(raw.get('min_players'), where, errors, 'min_players'),
            'max_players': _optional_int(raw.get('max_players'), where, errors, 'max_players'),
            'is_standard_card': is_card,
            'card_code': raw.get('card_code') if is_card else None,
        }
        if is_card:
            values['description'] = _cards_description(raw)
            values['setup_instructions'] = raw.get('setup_instructions')
        else:
            values['description'] = raw.get('description')
            values['setup_instructions'] = raw.get('setup_instructions')
        _check_lengths(errors, where, values, DRILL_LIMITS)

        diagrams = []
        for i, d in enumerate(raw.get('diagrams') or [], start=1):
            dwhere = f'{where} diagram {i}'
            image = _load_file(images_dir, d.get('file'), dwhere, errors)
            svg = _load_file(images_dir, d['svg'], dwhere, errors, svg=True) if d.get('svg') else None
            dvalues = {'caption': d.get('caption'), 'step_label': d.get('step_label'),
                       'source': d.get('source')}
            _check_lengths(errors, dwhere, dvalues, DIAGRAM_LIMITS)
            if image:
                diagrams.append({
                    **dvalues,
                    'order': i,
                    'image_bytes': image[0],
                    'image_mime': image[1],
                    'image_hash': hashlib.sha256(image[0]).hexdigest(),
                    'svg_text': svg[0].decode('utf-8') if svg else None,
                    'svg_hash': hashlib.sha256(svg[0]).hexdigest() if svg else None,
                })
        drills.append({'values': values, 'diagrams': diagrams})

    for i, raw in enumerate(data.get('drills') or [], start=1):
        add_drill(raw, f'drills[{i}]', is_card=False)
    for i, raw in enumerate(data.get('cards') or [], start=1):
        add_drill(raw, f'cards[{i}]', is_card=True)

    existing_drill_ids = {
        ext for (ext,) in db.session.query(SavedDrill.external_id).filter(
            SavedDrill.team_organization_id == team_org_id,
            SavedDrill.external_id.isnot(None)).all()
    }

    sessions = []
    seen_sessions = set()
    for i, raw in enumerate(data.get('sessions') or [], start=1):
        ext = raw.get('external_id')
        where = f'sessions[{i}]'
        if not isinstance(ext, str) or not ext:
            errors.append(f'{where}: external_id is required')
            continue
        where = f'{where} {ext}'
        if ext in seen_sessions:
            errors.append(f'{where}: duplicate external_id')
        seen_sessions.add(ext)
        if not raw.get('title'):
            errors.append(f'{where}: title is required')
        squad = raw.get('squad')
        if squad is not None and squad not in SQUADS:
            errors.append(f'{where}: squad must be one of {sorted(SQUADS)}, got {squad!r}')
        session_type = raw.get('session_type')
        if session_type is not None and session_type not in SESSION_TYPES:
            errors.append(f'{where}: session_type must be one of {sorted(SESSION_TYPES)}')

        points = raw.get('learning_points', raw.get('points'))
        if points is not None and not (isinstance(points, list)
                                       and all(isinstance(p, str) for p in points)):
            errors.append(f'{where}: points must be a list of strings')
        terms = raw.get('key_terms', raw.get('words'))
        if terms is not None and not (isinstance(terms, list) and all(
                isinstance(t, list) and len(t) == 2 and all(isinstance(x, str) for x in t)
                for t in terms)):
            errors.append(f'{where}: words must be a list of [term, meaning] pairs')

        start_time = _parse_time(raw.get('start_time'), where, errors, 'start_time')
        end_time = _parse_time(raw.get('end_time'), where, errors, 'end_time')
        length = _optional_int(raw.get('length_minutes'), where, errors, 'length_minutes')
        if start_time and not end_time and length:
            end_time = (datetime.combine(date.min, start_time) + timedelta(minutes=length)).time()

        values = {
            'external_id': ext,
            'title': raw.get('title'),
            'season': season,
            'phase_number': _optional_int(raw.get('phase_number'), where, errors, 'phase_number'),
            'phase_name': raw.get('phase'),
            'block': raw.get('block'),
            'week_number': _optional_int(raw.get('week'), where, errors, 'week'),
            'week_commencing': _parse_date(raw.get('week_commencing'), where, errors,
                                           'week_commencing'),
            'squad': squad,
            'aim': raw.get('aim'),
            'learning_points': points,
            'key_terms': terms,
            'run_by': raw.get('run_by'),
            'kit': raw.get('kit'),
            'sources': raw.get('sources'),
            'notes': _notes_markdown(raw.get('notes')),
            'date': _parse_date(raw.get('date'), where, errors, 'date'),
            'start_time': start_time,
            'end_time': end_time,
            'location': raw.get('location'),
            'focus_area': raw.get('focus_area'),
        }
        if session_type:
            values['session_type'] = session_type
        _check_lengths(errors, where, values, SESSION_LIMITS)

        components = []
        for j, act in enumerate(raw.get('activities') or [], start=1):
            awhere = f'{where} activity {j}'
            ctype = act.get('type')
            if ctype not in SessionComponent.COMPONENT_TYPES:
                errors.append(f'{awhere}: type must be one of {SessionComponent.COMPONENT_TYPES}, '
                              f'got {ctype!r}')
            if not act.get('name'):
                errors.append(f'{awhere}: name is required')
            drill_ext = act.get('drill_id')
            if drill_ext and drill_ext not in seen_drills and drill_ext not in existing_drill_ids:
                errors.append(f'{awhere}: drill_id {drill_ext!r} is not in this file or the database')
            cvalues = {
                'title': act.get('name'),
                'description': act.get('how'),
                'coach_cue': act.get('coach'),
                'duration_minutes': _optional_int(act.get('mins'), awhere, errors, 'mins'),
                'component_type': ctype,
                'focus_area': act.get('focus_area'),
                'notes': _notes_markdown(act.get('notes')),
                'order': j,
                'drill_external_id': drill_ext or None,
            }
            _check_lengths(errors, awhere, cvalues, COMPONENT_LIMITS)
            components.append(cvalues)
        sessions.append({'values': values, 'components': components})

    if errors:
        raise SeasonImportError(errors)
    return drills, sessions


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _apply(obj, values):
    """Set attributes; return True if anything changed."""
    changed = False
    for key, value in values.items():
        if getattr(obj, key) != value:
            setattr(obj, key, value)
            changed = True
    return changed


def _diagram_url(endpoint, diagram, digest, ext):
    # Built from the URL map rather than url_for: url_for needs a request
    # context, and the app's teardown_request (error_handlers.py) calls
    # db.session.remove(), which would throw away this import's pending work.
    adapter = current_app.url_map.bind('localhost')
    return adapter.build(endpoint, {'diagram_id': diagram.id,
                                    'filename': f'{digest[:16]}.{ext}'})


def _sync_diagrams(drill, wanted, team_org_id, next_id):
    def key(order, image_hash, svg_hash, caption, step_label, source):
        return (order, image_hash, svg_hash, caption, step_label, source)

    current = [key(d.order, d.image_hash, d.svg_hash, d.caption, d.step_label, d.source)
               for d in drill.diagrams]
    target = [key(w['order'], w['image_hash'], w['svg_hash'], w['caption'], w['step_label'],
                  w['source']) for w in wanted]
    if current == target:
        return False

    for old in list(drill.diagrams):
        drill.diagrams.remove(old)  # delete-orphan cascade removes the row
    for w in wanted:
        diagram = DrillDiagram(
            id=next_id(DrillDiagram),
            order=w['order'],
            caption=w['caption'],
            step_label=w['step_label'],
            source=w['source'],
            image_data=base64.b64encode(w['image_bytes']).decode('ascii'),
            image_mime=w['image_mime'],
            image_hash=w['image_hash'],
            svg_data=w['svg_text'],
            svg_hash=w['svg_hash'],
            team_organization_id=team_org_id,
        )
        ext = w['image_mime'].split('/')[1].replace('jpeg', 'jpg')
        diagram.image_url = _diagram_url('session.drill_diagram_image', diagram,
                                         w['image_hash'], ext)
        if w['svg_text']:
            diagram.svg_url = _diagram_url('session.drill_diagram_svg', diagram,
                                           w['svg_hash'], 'svg')
        drill.diagrams.append(diagram)
    return True


def _component_key(c):
    return (c.order, c.title, c.description, c.coach_cue, c.duration_minutes,
            c.component_type, c.focus_area, c.notes, c.drill_id)


def _sync_components(plan, wanted, drill_ids, team_org_id, next_id):
    target = [(w['order'], w['title'], w['description'], w['coach_cue'], w['duration_minutes'],
               w['component_type'], w['focus_area'], w['notes'],
               drill_ids.get(w['drill_external_id']))
              for w in wanted]
    existing = plan.components.order_by(SessionComponent.order).all()
    if [_component_key(c) for c in existing] == target:
        return False

    if existing:
        # Playbook links to these components go with them (the file is the
        # source of truth for imported sessions).
        from app.models.playbook import Play
        assoc = Play.play_session_component
        ids = [c.id for c in existing]
        db.session.execute(assoc.delete().where(assoc.c.component_id.in_(ids)))
        for c in existing:
            db.session.delete(c)
        db.session.flush()

    for w in wanted:
        db.session.add(SessionComponent(
            id=next_id(SessionComponent),
            session_id=plan.id,
            drill_id=drill_ids.get(w['drill_external_id']),
            title=w['title'],
            description=w['description'],
            coach_cue=w['coach_cue'],
            duration_minutes=w['duration_minutes'],
            component_type=w['component_type'],
            focus_area=w['focus_area'],
            notes=w['notes'],
            order=w['order'],
            team_organization_id=team_org_id,
        ))
    return True


def import_season(data, images_dir, team_org_id, dry_run=False):
    """Import a parsed season file. Returns an ImportSummary.
    Raises SeasonImportError if the file is invalid (nothing is written)."""
    from app.models.team_organization import TeamOrganization
    if db.session.get(TeamOrganization, team_org_id) is None:
        raise SeasonImportError([f'team organization {team_org_id} does not exist'])

    drills, sessions = _prepare(data, images_dir, team_org_id)
    summary = ImportSummary(dry_run=dry_run)
    next_id = _IdAllocator()

    try:
        drill_ids = {}
        for item in drills:
            values = item['values']
            drill = SavedDrill.query.filter_by(team_organization_id=team_org_id,
                                               external_id=values['external_id']).first()
            kind = 'card' if values['is_standard_card'] else 'drill'
            if drill is None:
                drill = SavedDrill(id=next_id(SavedDrill), team_organization_id=team_org_id,
                                   is_public=False)
                _apply(drill, values)
                db.session.add(drill)
                status = 'created'
            else:
                status = 'updated' if _apply(drill, values) else 'unchanged'
            db.session.flush()
            drill_ids[values['external_id']] = drill.id

            had_diagrams = bool(drill.diagrams)
            if _sync_diagrams(drill, item['diagrams'], team_org_id, next_id):
                summary.record('diagrams', 'updated' if had_diagrams else 'created',
                               f"{values['external_id']} ({len(item['diagrams'])})")
            elif item['diagrams']:
                summary.record('diagrams', 'unchanged', values['external_id'])
            summary.record(kind, status, f"{values['external_id']}: {values['title']}")

        # Drills referenced by sessions but defined in an earlier import.
        for item in sessions:
            for c in item['components']:
                ext = c['drill_external_id']
                if ext and ext not in drill_ids:
                    drill_ids[ext] = SavedDrill.query.filter_by(
                        team_organization_id=team_org_id, external_id=ext).one().id

        for item in sessions:
            values = item['values']
            plan = SessionPlan.query.filter_by(team_organization_id=team_org_id,
                                               external_id=values['external_id']).first()
            if plan is None:
                plan = SessionPlan(id=next_id(SessionPlan), team_organization_id=team_org_id)
                _apply(plan, values)
                db.session.add(plan)
                db.session.flush()
                status = 'created'
            else:
                status = 'updated' if _apply(plan, values) else 'unchanged'

            if _sync_components(plan, item['components'], drill_ids, team_org_id, next_id):
                summary.record('components', 'updated' if status != 'created' else 'created',
                               f"{values['external_id']} ({len(item['components'])})")
            else:
                summary.record('components', 'unchanged', values['external_id'])
            summary.record('session', status, f"{values['external_id']}: {values['title']}")

        db.session.flush()
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return summary


def load_season_file(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)
