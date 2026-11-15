"""Rebuild imports/drills/*.json: add the new entries, then give every drill
its problem area and phase, the plan's harder/easier and Ask lines, and the
weeks the plan really uses it. Usage: build_drills.py <scratch> [--write]"""
import collections
import glob
import json
import os
import re
import sys

S = sys.argv[1]
WRITE = '--write' in sys.argv
sys.path.insert(0, '.')
sys.path.insert(0, S)
from app.utils.season_plan_import import load_export, parse_export  # noqa: E402
from app.utils.season_sessions import parse_week_notes, drill_key, match_drill  # noqa: E402
import newdrills  # noqa: E402
try:
    import enrich
except ImportError:
    enrich = None

TABS = 'imports/season-plan-export/tabs'
HERD, GRUT = 'imports/drills/herd-drills.json', 'imports/drills/grut-drills.json'

FOCUS_RENAME = {'Cutting': 'Getting open', 'Reading the pitch': 'Seeing the field', 'Retention': 'Keeping the disc',
                'Benchmarks': 'Skill tests'}
AREA = {
    'Getting open': 'Getting open', 'Footwork': 'Getting open',
    'Seeing the field': 'Seeing the field', 'Tempo': 'Seeing the field', 'Transitions': 'Seeing the field',
    'Breaking the mark': 'Breaking the mark',
    'Keeping the disc': 'Keeping the disc', 'Handling': 'Keeping the disc',
    'Throwing': 'The throwing and catching base', 'Catching': 'The throwing and catching base',
    'Hucking': 'The throwing and catching base',
    'Marking': 'The defence toolkit (marking and 1v1 defence)', 'Defence': 'The defence toolkit (marking and 1v1 defence)',
    'Team defence': 'The defence toolkit (team defence)', 'Zone defence': 'The defence toolkit (zones)',
    'Offence': 'The offence toolkit (structures)', 'Set pieces': 'The offence toolkit (set pieces)',
    'Endzone offence': 'The offence toolkit (endzone)', 'Zone offence': 'The offence toolkit (zone offence)',
    'Fitness': 'Fitness', 'Skill tests': 'Measuring improvement',
}
PHASES = [(1, 11, 'Phase 1 (technique)'), (14, 24, 'Phase 2 (under pressure)'), (25, 43, 'Phases 3-4 (in the team)'),
          (44, 51, 'Phase 5 (Nationals: nothing new)')]


def slug(title):
    return 'herd-' + re.sub(r'[^a-z0-9]+', '-', re.sub(r'\([^)]*\)', '', title.lower()).replace("'", '')).strip('-')


def weeks_text(weeks):
    weeks = sorted(weeks)
    if not weeks:
        return None
    if len(weeks) == 1:
        return f'week {weeks[0]}.'
    return 'weeks ' + ', '.join(map(str, weeks[:-1])) + f' and {weeks[-1]}.'


def phase_text(weeks):
    labels = [label for lo, hi, label in PHASES if any(lo <= w <= hi for w in weeks)]
    if not labels:
        return None
    return ', '.join(labels[:-1]) + (' and ' if len(labels) > 1 else '') + labels[-1]


def bullets(items):
    return '\n'.join(f'- {i}' for i in items)


def new_entry(d):
    parts = [d['intro'] + (' ' + newdrills.OUTLINE if d['outline'] else '')]
    parts.append('**How it runs**\n\n' + '\n'.join(f'{i}. {step}' for i, step in enumerate(d['how'], 1)))
    parts.append('**Coaching points**\n\n' + bullets(d['points']))
    return {
        'external_id': slug(d['title']), 'title': d['title'], 'description': '\n\n'.join(parts),
        'setup_instructions': d['setup'], 'source': d['source'], 'focus_area': d['focus'],
        'equipment_needed': d['equip'], 'recommended_duration': d['mins'], 'min_players': d['minp'],
        'max_players': d['maxp'], 'skill_level': d['level'],
    }


def apply_renames():
    files = sorted(glob.glob(f'{TABS}/0[4-8]-*.md'))
    texts = {f: open(f, encoding='utf-8').read() for f in files}
    for old, new, count in newdrills.RENAMES:
        found = sum(t.count(old) for t in texts.values())
        already = sum(t.count(new) for t in texts.values())
        if found == 0 and already >= count:
            continue
        assert found == count, (old, found, count)
        for f in texts:
            texts[f] = texts[f].replace(old, new)
    if WRITE:
        for f, t in texts.items():
            open(f, 'w', encoding='utf-8').write(t)
    return texts


def plan_usage(texts, keys):
    """key -> weeks, from the session tables; and the notes harvested per key."""
    manifest, tabs = load_export('imports/season-plan-export')
    tabs = [(tab, texts.get(os.path.join('imports/season-plan-export', tab['file']), text)) for tab, text in tabs]
    data = parse_export(manifest, tabs)
    used = collections.defaultdict(set)
    unmatched = []
    for w in data['weeks']:
        for s in parse_week_notes(w.get('session_detail_md') or '')['sessions']:
            for a in s['activities']:
                if a['component_type'] in ('water', 'warmup'):
                    continue
                k = match_drill(a['title'], keys)
                if k:
                    used[k].add(w['week_number'])
                elif a['component_type'] == 'drill':
                    unmatched.append((w['week_number'], s['squad'], a['title']))
    notes = collections.defaultdict(lambda: {'harder': [], 'easier': [], 'ask': [], 'push': []})
    week = None
    for f in sorted(texts):
        for line in texts[f].splitlines():
            m = re.match(r'^## Week (\d+)', line)
            if m:
                week = int(m.group(1))
            m = re.match(r'^- \*\*(.+?):\*\*\s*(.*)$', line.strip())
            if not m or week is None:
                continue
            name, text = m.group(1), m.group(2).strip()
            squad = None
            sm = re.search(r'\s*\(([^)]*)\)\s*$', name)
            if sm:
                squad, name = sm.group(1), name[:sm.start()]
            k = match_drill(name, keys)
            if not k:
                continue
            n = notes[k]
            if re.match(r'(harder|easier):', text, re.I):
                for kind, body in re.findall(r'(harder|easier):\s*(.*?)(?=;\s*(?:harder|easier):|$)', text, re.I):
                    body = body.strip(' .;')
                    if body:
                        n[kind.lower()].append((week, squad, body[0].upper() + body[1:] + '.'))
                continue
            am = re.search(r'\bAsk:\s*(.*)$', text)
            if am:
                for q in re.findall(r'"([^"]+)"', am.group(1)):
                    n['ask'].append(q.strip())
                text = text[:am.start()].strip()
            if text:
                n['push'].append((week, squad, text))
    return used, unmatched, notes


def uniq(items):
    seen, out = set(), []
    for i in items:
        k = re.sub(r'\W+', ' ', i.lower()).strip()
        if k and k not in seen:
            seen.add(k)
            out.append(i)
    return out


def squad_tag(squad, week):
    if squad and re.fullmatch(r'1s|2s', squad):
        return squad
    return None


def rebuild(drill, weeks, notes, extra, report):
    desc = drill['description'].strip()
    desc = re.sub(r'\n\n\*\*In the 2027/28 plan:\*\*.*$', '', desc, flags=re.S)
    desc = re.sub(r'\n\n\*\*Serves:\*\*[^\n]*', '', desc)
    title = drill['title']
    has = lambda pat: re.search(pat, desc) is not None  # noqa: E731
    extra = extra or {}

    # Serves line, after the first paragraph
    area = extra.get('area') or AREA[drill['focus_area']]
    phase = phase_text(weeks) or extra.get('phase')
    serves = f'**Serves:** {area[0].upper() + area[1:]}' + (f' · {phase}' if phase else '') + '.'
    first, _, rest = desc.partition('\n\n')
    desc = first + '\n\n' + serves + ('\n\n' + rest if rest else '')

    # Ask bullets into Coaching points
    asks = uniq((extra.get('ask') or []) + notes['ask'])
    asks = [q for q in asks if q not in desc][:3]
    if asks:
        lines = bullets(f'Ask: "{q}"' for q in asks)
        m = re.search(r'\*\*Coaching points\*\*\n\n(?:- .*\n?)+', desc)
        if m:
            end = m.end()
            block = desc[m.start():end].rstrip('\n')
            desc = desc[:m.start()] + block + '\n' + lines + desc[end:].replace('\n\n\n', '\n\n') if desc[end:] else \
                desc[:m.start()] + block + '\n' + lines
            desc = re.sub(r'(- Ask: "[^\n]*")\n(\*\*)', r'\1\n\n\2', desc)
        else:
            desc += '\n\n**Coaching points**\n\n' + lines
    if not has(r'Ask: "') and not asks:
        report['no_ask'].append(title)

    # 1s and 2s
    if not has(r'\*\*(1s and 2s|2s version)'):
        s1, s2 = extra.get('s1'), extra.get('s2')
        pushes = notes['push']
        if not s1:
            s1 = next((t for w, sq, t in pushes if squad_tag(sq, w) == '1s'), None)
        if not s2:
            s2 = next((t for w, sq, t in pushes if squad_tag(sq, w) == '2s'), None)
        if s1 or s2:
            rows = ([f'1s: {s1}'] if s1 else []) + ([f'2s: {s2}'] if s2 else [])
            desc += '\n\n**1s and 2s**\n\n' + bullets(rows)
        else:
            report['no_squads'].append(title)

    for kind in ('harder', 'easier'):
        if has(r'\*\*%s' % kind.capitalize()):
            continue
        items = uniq(([extra[kind]] if extra.get(kind) else []) + [t for w, sq, t in notes[kind]])[:3]
        if items:
            desc += f'\n\n**{kind.capitalize()}**\n\n' + bullets(items)
        else:
            report['no_' + kind].append(title)

    wt = weeks_text(weeks)
    desc += '\n\n**In the 2027/28 plan:** ' + (wt if wt else extra.get('option') or 'NOT USED')
    if not wt and not extra.get('option'):
        report['unused'].append(title)
    drill['description'] = desc


def main():
    herd = json.load(open(HERD, encoding='utf-8'))
    grut = json.load(open(GRUT, encoding='utf-8'))
    have = {d['external_id'] for d in herd['drills']}
    for d in newdrills.NEW:
        e = new_entry(d)
        if e['external_id'] in have:
            herd['drills'] = [e if x['external_id'] == e['external_id'] and x.get('_new') else x for x in herd['drills']]
            continue
        herd['drills'].append(e)
    newdata = {slug(d['title']): d for d in newdrills.NEW}
    for d in herd['drills'] + grut['drills']:
        d['focus_area'] = FOCUS_RENAME.get(d['focus_area'], d['focus_area'])
    for f in getattr(enrich, 'FIELDS', {}) if enrich else {}:
        pass
    texts = apply_renames()
    lib = {drill_key(d['title']): d for d in herd['drills'] + grut['drills']}
    assert len(lib) == len(herd['drills']) + len(grut['drills']), 'two drills share a name'
    used, unmatched, notes = plan_usage(texts, set(lib))
    report = collections.defaultdict(list)
    extras = dict(getattr(enrich, 'ENRICH', {})) if enrich else {}
    for key, d in lib.items():
        extra = dict(extras.get(d['title'], {}))
        nd = newdata.get(d['external_id'])
        if nd:
            for k in ('harder', 'easier', 's1', 's2', 'ask'):
                if nd.get(k) and not extra.get(k):
                    extra[k] = nd[k]
        if enrich:
            for field, value in getattr(enrich, 'FIELDS', {}).get(d['title'], {}).items():
                d[field] = value
            intro = getattr(enrich, 'INTRO', {}).get(d['title'])
            if intro:
                first, sep, rest = d['description'].partition('\n\n')
                d['description'] = intro + sep + rest
        rebuild(d, used.get(key, set()), notes[key], extra, report)
    print('drills', len(herd['drills']), len(grut['drills']))
    for k, v in report.items():
        print(k, len(v), '|', '; '.join(v))
    print('unmatched drill-type activities', len(unmatched))
    if '--unmatched' in sys.argv:
        for u in unmatched:
            print('  ', u)
    if WRITE:
        for path, data in ((HERD, herd), (GRUT, grut)):
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
                f.write('\n')
    return herd, grut


if __name__ == '__main__':
    main()
