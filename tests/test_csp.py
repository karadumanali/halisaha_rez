"""CSP inline stil/olay işleyicilerini engeller → şablonlarda kullanılmamalı."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INLINE = re.compile(r'''<[^>]*\s(style|on[a-z]+)\s*=\s*["']''', re.I)


def _files():
    for base, ext in (('templates', '.html'), (os.path.join('static', 'js'), '.js')):
        for dirpath, _, names in os.walk(os.path.join(ROOT, base)):
            for n in names:
                if n.endswith(ext):
                    yield os.path.join(dirpath, n)


def test_no_inline_styles_or_handlers():
    bad = []
    for path in _files():
        text = open(path, encoding='utf-8').read()
        for m in INLINE.finditer(text):
            line = text.count('\n', 0, m.start()) + 1
            bad.append(f'{os.path.relpath(path, ROOT)}:{line}')
    assert not bad, 'CSP tarafından engellenen inline stil/olay: ' + ', '.join(bad)
