"""Draws the demo team's plays and drill diagrams (diagram_specs.js) with the
site's own drawing code in headless Chromium, and writes them to
diagrams.json for `flask seed-demo`. Only needed when the specs change:

    python -m app.demo.build_diagrams path/to/fabric.min.js

fabric.min.js is fabric 5.3.0 (what the editor loads from the CDN), e.g.
from `npm pack fabric@5.3.0`."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_JS = os.path.join(HERE, '..', 'static', 'js')
OUT = os.path.join(HERE, 'diagrams.json')


def build(fabric_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        kwargs = {}
        if os.path.exists('/opt/pw-browsers/chromium'):
            kwargs['executable_path'] = '/opt/pw-browsers/chromium'
        browser = p.chromium.launch(**kwargs)
        page = browser.new_page()
        page.set_content('<!doctype html><html><body></body></html>')
        page.add_script_tag(path=fabric_path)
        page.add_script_tag(path=os.path.join(STATIC_JS, 'drill_diagram.js'))
        page.add_script_tag(path=os.path.join(HERE, 'diagram_specs.js'))
        drawings = page.evaluate("""async () => {
            const out = {};
            for (const spec of window.DEMO_DRAWINGS) out[spec.key] = await window.buildDrawing(spec);
            return out;
        }""")
        browser.close()
    with open(OUT, 'w') as f:
        json.dump(drawings, f, separators=(',', ':'))
    return drawings


if __name__ == '__main__':
    drawings = build(sys.argv[1])
    print(f'Wrote {len(drawings)} drawings to {OUT} ({os.path.getsize(OUT) // 1024} KB)')
