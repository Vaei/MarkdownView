"""GitHub-flavoured Markdown to Sublime minihtml.

minihtml has no tables or <pre>, so tables are drawn as monospace rows and code blocks keep
their whitespace with &nbsp; and <br>.
"""
import html
import re

ALERTS = {
    'NOTE': ('\u24d8', 'bluish', 'Note'),
    'TIP': ('\U0001f4a1', 'greenish', 'Tip'),
    'IMPORTANT': ('\u2757', 'purplish', 'Important'),
    'WARNING': ('\u26a0', 'yellowish', 'Warning'),
    'CAUTION': ('\u26d4', 'redish', 'Caution'),
}

FENCE_RE = re.compile(r'^( {0,3})(`{3,}|~{3,})[ \t]*([^`\s]*)[^`]*$')
ATX_RE = re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$')
HR_RE = re.compile(r'^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$')
QUOTE_RE = re.compile(r'^ {0,3}> ?')
LIST_RE = re.compile(r'^( {0,3})([-*+]|\d{1,9}[.)])([ \t]+|$)(.*)$')
HTML_BLOCK_RE = re.compile(r'^ {0,3}<(!--|/?[A-Za-z][\w-]*)(?:\s|/?>|$)')
SETEXT_RE = re.compile(r'^ {0,3}(=+|-+)[ \t]*$')
TABLE_DELIM_RE = re.compile(r'^ *\|? *:?-+:? *(?:\| *:?-+:? *)*\|? *$')
REF_DEF_RE = re.compile(r'''^ {0,3}\[([^\]^][^\]]*)\]:[ \t]*<?(\S+?)>?(?:[ \t]+["'(](.*)["')])?[ \t]*$''')
ALERT_RE = re.compile(r'^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*$', re.I)
TASK_RE = re.compile(r'^\[([ xX])\][ \t]+')

LINK_TEXT = r'\[((?:[^\[\]\\]|\\.|\[[^\[\]]*\])*)\]'
LINK_DEST = r'''\(\s*<?((?:[^\s()<>\\]|\\.|\([^\s()]*\))*)>?(?:\s+("[^"]*"|'[^']*'|\([^)]*\)))?\s*\)'''
IMAGE_RE = re.compile('!' + LINK_TEXT + LINK_DEST)
LINK_RE = re.compile(LINK_TEXT + LINK_DEST)
REF_LINK_RE = re.compile('(!?)' + LINK_TEXT + r'(?:\[([^\]]*)\])?')
TAG_RE = re.compile(r'</?[A-Za-z][\w-]*(?:\s+(?:[^<>"\']|"[^"]*"|\'[^\']*\')*)?/?>')
ATTR_RE = re.compile(r'''([\w-]+)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)''')
BARE_URL_RE = re.compile(r'''(?<![\w/"'=\x00])((?:https?://|www\.)[^\s<\x00]*[^\s<\x00.,:;"')\]!?*_~])''')

PASS_TAGS = {'b', 'strong', 'i', 'em', 'u', 'br', 'code', 'p', 'div', 'span', 'small', 'big',
             'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'hr'}
MAPPED_TAGS = {
    'kbd': '<span class="kbd">', 's': '<span class="strike">', 'del': '<span class="strike">',
    'strike': '<span class="strike">', 'ins': '<u>', 'mark': '<span class="mark">',
    'sub': '<small>', 'sup': '<small>', 'details': '<div class="details">',
    'summary': '<div class="summary">', 'pre': '<div class="pre">', 'blockquote': '<div class="quote">',
    'center': '<div>', 'tt': '<code>', 'dl': '<div>', 'dt': '<div class="dt">', 'dd': '<div class="dd">',
}
MAPPED_CLOSE = {k: '</' + re.match(r'<(\w+)', v).group(1) + '>' for k, v in MAPPED_TAGS.items()}


def esc(text):
    return html.escape(text, quote=False)


def esc_attr(text):
    return html.escape(text, quote=True)


def code_html(text):
    """Escaped text that keeps its spacing and line breaks in minihtml."""
    out = []
    for line in esc(text).split('\n'):
        body = line.lstrip(' ')
        out.append('&nbsp;' * (len(line) - len(body)) + body.replace('  ', ' &nbsp;'))
    return '<br>'.join(out)


def strip_tags(text):
    return html.unescape(re.sub(r'<[^>]+>', '', text))


def is_blank(line):
    return not line.strip()


class Renderer:
    """Callbacks let the host resolve links, images and syntax highlighting.

    link(url) -> href, image(src, alt, title, width) -> html, highlight(code, lang) -> html or None.
    """

    def __init__(self, link=None, image=None, highlight=None):
        self.link = link or (lambda url: url)
        self.image = image or (lambda src, alt, title, width: esc(alt))
        self.highlight = highlight or (lambda code, lang: None)
        self.refs = {}

    def render(self, text):
        text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ')
        if text.startswith('---\n'):
            end = text.find('\n---\n', 4)
            if end != -1:
                text = text[end + 5:]
        lines = self.collect_refs(text.split('\n'))
        return self.blocks(lines)

    def collect_refs(self, lines):
        out = []
        fence = None
        for line in lines:
            m = FENCE_RE.match(line)
            if fence:
                if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= len(fence) and not m.group(3):
                    fence = None
            elif m:
                fence = m.group(2)
            else:
                d = REF_DEF_RE.match(line)
                if d:
                    self.refs[self.norm(d.group(1))] = (d.group(2), d.group(3))
                    continue
            out.append(line)
        return out

    @staticmethod
    def norm(label):
        return ' '.join(label.lower().split())

    # Blocks

    def starts_block(self, line):
        return bool(FENCE_RE.match(line) or ATX_RE.match(line) or HR_RE.match(line) or QUOTE_RE.match(line)
                    or HTML_BLOCK_RE.match(line) or self.list_interrupts(line))

    @staticmethod
    def list_interrupts(line):
        m = LIST_RE.match(line)
        if not m or not m.group(4).strip():
            return False
        marker = m.group(2)
        return marker in '-*+' or marker[:-1] == '1'

    def blocks(self, lines, tight=False):
        out = []
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            if is_blank(line):
                i += 1
                continue

            m = FENCE_RE.match(line)
            if m:
                indent, fence, lang = len(m.group(1)), m.group(2), m.group(3)
                body = []
                i += 1
                while i < n:
                    c = FENCE_RE.match(lines[i])
                    if c and c.group(2)[0] == fence[0] and len(c.group(2)) >= len(fence) and not c.group(3):
                        i += 1
                        break
                    l = lines[i]
                    body.append(l[min(indent, len(l) - len(l.lstrip(' '))):])
                    i += 1
                out.append(self.code_block('\n'.join(body), lang))
                continue

            if line.startswith('    '):
                body = []
                while i < n and (lines[i].startswith('    ') or is_blank(lines[i])):
                    body.append(lines[i][4:])
                    i += 1
                while body and is_blank(body[-1]):
                    body.pop()
                out.append(self.code_block('\n'.join(body), ''))
                continue

            m = ATX_RE.match(line)
            if m:
                out.append(self.heading(len(m.group(1)), m.group(2) or ''))
                i += 1
                continue

            if HR_RE.match(line):
                out.append('<div class="hr"></div>')
                i += 1
                continue

            if QUOTE_RE.match(line):
                body = []
                while i < n and not is_blank(lines[i]):
                    l = lines[i]
                    if QUOTE_RE.match(l):
                        body.append(QUOTE_RE.sub('', l, 1))
                    elif body and not is_blank(body[-1]) and not self.starts_block(l):
                        body.append(l)
                    else:
                        break
                    i += 1
                out.append(self.quote(body))
                continue

            if HTML_BLOCK_RE.match(line):
                body = []
                comment = line.lstrip().startswith('<!--')
                while i < n:
                    body.append(lines[i])
                    i += 1
                    if comment and '-->' in body[-1]:
                        break
                    if not comment and (i >= n or is_blank(lines[i])):
                        break
                out.append(self.html_fragment('\n'.join(body)))
                continue

            if i + 1 < n and '|' in line and TABLE_DELIM_RE.match(lines[i + 1]):
                header = self.split_row(line)
                delims = self.split_row(lines[i + 1])
                if len(header) == len(delims):
                    rows = []
                    i += 2
                    while i < n and not is_blank(lines[i]) and '|' in lines[i] and not self.starts_block(lines[i]):
                        rows.append(self.split_row(lines[i]))
                        i += 1
                    out.append(self.table(header, delims, rows))
                    continue

            if LIST_RE.match(line):
                html_list, i = self.list_block(lines, i)
                out.append(html_list)
                continue

            para = [line]
            i += 1
            heading = 0
            while i < n and not is_blank(lines[i]):
                s = SETEXT_RE.match(lines[i])
                if s:
                    heading = 1 if s.group(1)[0] == '=' else 2
                    i += 1
                    break
                if self.starts_block(lines[i]):
                    break
                if '|' in lines[i] and i + 1 < n and TABLE_DELIM_RE.match(lines[i + 1]):
                    break
                para.append(lines[i])
                i += 1
            # Two trailing spaces mean a hard break, so they survive the strip.
            text = '\n'.join(l.strip() + ('  ' if l.endswith('  ') else '') for l in para)
            if heading:
                out.append(self.heading(heading, text))
            elif tight:
                out.append(self.inline(text))
            else:
                out.append('<p>%s</p>' % self.inline(text))
        return '\n'.join(out)

    def list_block(self, lines, i):
        n = len(lines)
        first = LIST_RE.match(lines[i])
        ordered = first.group(2)[-1] in '.)'
        kind = first.group(2)[-1] if ordered else first.group(2)
        start = int(first.group(2)[:-1]) if ordered else 1
        items = []
        loose = False
        while i < n:
            m = LIST_RE.match(lines[i])
            if not m or (m.group(2)[-1] if ordered else m.group(2)) != kind:
                break
            pad = len(m.group(3))
            indent = len(m.group(1)) + len(m.group(2)) + (pad if 0 < pad <= 4 else 1)
            body = [m.group(4) if pad <= 4 else lines[i][indent:]]
            i += 1
            while i < n:
                l = lines[i]
                if is_blank(l):
                    body.append('')
                    i += 1
                    continue
                if len(l) - len(l.lstrip(' ')) >= indent:
                    body.append(l[indent:])
                    i += 1
                    continue
                if is_blank(body[-1]) or LIST_RE.match(l) or self.starts_block(l):
                    break
                body.append(l)
                i += 1
            trailing_blank = False
            while body and is_blank(body[-1]):
                body.pop()
                trailing_blank = True
            following = LIST_RE.match(lines[i]) if i < n else None
            if trailing_blank and following and (following.group(2)[-1] if ordered else following.group(2)) == kind:
                loose = True
            if any(is_blank(b) for b in body[1:]) and not any(FENCE_RE.match(b) for b in body):
                loose = True
            items.append(body)
        parts = []
        for body in items:
            check = ''
            t = TASK_RE.match(body[0]) if body else None
            if t:
                body = [body[0][t.end():]] + body[1:]
                check = '<span class="task">%s</span> ' % ('\u2611' if t.group(1) != ' ' else '\u2610')
            parts.append('<li%s>%s%s</li>' % (' class="task-item"' if t else '', check, self.blocks(body, tight=not loose)))
        tag = 'ol' if ordered else 'ul'
        attr = ' start="%d"' % start if ordered and start != 1 else ''
        return '<%s%s>%s</%s>' % (tag, attr, ''.join(parts), tag), i

    @staticmethod
    def split_row(line):
        s = line.strip()
        if s.startswith('|'):
            s = s[1:]
        if s.endswith('|') and not s.endswith('\\|'):
            s = s[:-1]
        cells = re.split(r'(?<!\\)\|', s)
        return [c.strip().replace('\\|', '|') for c in cells]

    def heading(self, level, text):
        return '<h%d>%s</h%d>' % (level, self.inline(text.strip()), level)

    def code_block(self, code, lang):
        highlighted = self.highlight(code, lang) if lang else None
        return '<div class="code">%s</div>' % (highlighted if highlighted is not None else code_html(code))

    def quote(self, lines):
        alert = ALERT_RE.match(lines[0].strip()) if lines else None
        if alert:
            icon, color, title = ALERTS[alert.group(1).upper()]
            inner = self.blocks(lines[1:])
            return ('<div class="bar" style="background-color: var(--%s);"><div class="alert">'
                    '<div class="alert-title" style="color: var(--%s);">%s&nbsp; %s</div>%s</div></div>'
                    % (color, color, icon, title, inner))
        return '<div class="bar quote-bar"><div class="quote">%s</div></div>' % self.blocks(lines)

    def table(self, header, delims, rows):
        cols = len(header)
        aligns = []
        for d in delims:
            d = d.strip()
            aligns.append('c' if d.startswith(':') and d.endswith(':') else 'r' if d.endswith(':') else 'l')
        cells = [[self.inline(c) for c in header]]
        for r in rows:
            r = (r + [''] * cols)[:cols]
            cells.append([self.inline(c) for c in r])
        widths = [max(len(strip_tags(row[c])) for row in cells) for c in range(cols)]
        # Columns line up because every cell is padded to the same character count in a monospace font,
        # with &nbsp; throughout since minihtml collapses and wraps plain spaces.
        sep = '<span class="sep">&nbsp;│&nbsp;</span>'
        out = []
        for k, row in enumerate(cells):
            parts = []
            for c, cell in enumerate(row):
                gap = widths[c] - len(strip_tags(cell))
                left = gap // 2 if aligns[c] == 'c' else gap if aligns[c] == 'r' else 0
                cell = re.sub(r'(<[^>]*>)| ', lambda m: m.group(1) or '&nbsp;', cell)
                parts.append('&nbsp;' * left + cell + '&nbsp;' * (gap - left))
            cls = 'tr th' if k == 0 else 'tr odd' if k % 2 == 0 else 'tr'
            out.append('<div class="%s">%s%s%s</div>' % (cls, sep, sep.join(parts), sep))
        return '<div class="table">%s</div>' % ''.join(out)

    # Raw HTML

    def html_fragment(self, text):
        text = re.sub(r'<!--.*?(-->|$)', '', text, flags=re.S)
        if not text.strip():
            return ''
        return TAG_RE.sub(lambda m: self.html_tag(m.group(0)), text)

    def html_tag(self, tag):
        m = re.match(r'<(/?)([A-Za-z][\w-]*)', tag)
        closing, name = m.group(1), m.group(2).lower()
        attrs = {k.lower(): html.unescape(v.strip('"\'')) for k, v in ATTR_RE.findall(tag)}
        if name == 'img':
            width = attrs.get('width', '')
            return self.image(attrs.get('src', ''), attrs.get('alt', ''), attrs.get('title'),
                              int(width) if width.isdigit() else None)
        if name == 'a':
            if closing:
                return '</a>'
            if 'href' not in attrs:
                return '<a>'
            return '<a href="%s">' % esc_attr(self.link(attrs['href']))
        if name in PASS_TAGS:
            if name in ('br', 'hr'):
                return '<br>' if name == 'br' else '<div class="hr"></div>'
            return '<%s%s>' % (closing, name)
        if name in MAPPED_TAGS:
            return MAPPED_CLOSE[name] if closing else MAPPED_TAGS[name]
        return ''

    # Inlines

    def inline(self, text):
        stash = []

        def put(fragment):
            stash.append(fragment)
            return '\x00%d\x00' % (len(stash) - 1)

        def code_span(m):
            body = m.group(2).replace('\n', ' ')
            if len(body) > 2 and body.startswith(' ') and body.endswith(' ') and body.strip():
                body = body[1:-1]
            return put('<code>%s</code>' % esc(body).replace('  ', ' &nbsp;'))

        text = re.sub(r'(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)', code_span, text, flags=re.S)
        text = re.sub(r'( {2,}|\\)\n', lambda m: put('<br>'), text)
        text = re.sub(r'\\([!-/:-@\[-`{-~])', lambda m: put(esc(m.group(1))), text)
        text = re.sub(r'&(#\d+|#[xX][0-9a-fA-F]+|[A-Za-z]\w*);', lambda m: put(esc(html.unescape(m.group(0)))), text)
        text = re.sub(r'<((?:https?|ftp|mailto):[^\s<>]+)>', lambda m: put(self.anchor(m.group(1), esc(m.group(1)))), text)
        text = re.sub(r'<([^\s@<>]+@[^\s@<>]+\.[^\s@<>]+)>', lambda m: put(self.anchor('mailto:' + m.group(1), esc(m.group(1)))), text)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
        text = TAG_RE.sub(lambda m: put(self.html_tag(m.group(0))), text)

        def image(m):
            title = m.group(3)[1:-1] if m.group(3) else None
            return put(self.image(self.unescape_url(m.group(2)), strip_tags(self.inline(m.group(1))), title, None))

        def link(m):
            return put(self.anchor(self.unescape_url(m.group(2)), self.inline(m.group(1))))

        def ref_link(m):
            bang, label, ref = m.group(1), m.group(2), m.group(3)
            if label.startswith('^') and not bang and ref is None:
                return put('<small class="fn">[%s]</small>' % esc(label[1:]))
            key = self.norm(ref if ref else label)
            if key not in self.refs:
                return m.group(0)
            url, title = self.refs[key]
            if bang:
                return put(self.image(url, label, title, None))
            return put(self.anchor(url, self.inline(label)))

        text = IMAGE_RE.sub(image, text)
        text = LINK_RE.sub(link, text)
        text = REF_LINK_RE.sub(ref_link, text)
        text = BARE_URL_RE.sub(lambda m: put(self.anchor(('http://' if m.group(1).startswith('www.') else '') + m.group(1), esc(m.group(1)))), text)

        text = esc(text)
        text = re.sub(r'\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*', r'<b><i>\1</i></b>', text)
        text = re.sub(r'\*\*(?=\S)(.+?)(?<=\S)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)', r'<b>\1</b>', text)
        text = re.sub(r'\*(?=\S)(.+?)(?<=\S)\*', r'<i>\1</i>', text)
        text = re.sub(r'(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)', r'<i>\1</i>', text)
        text = re.sub(r'~~(?=\S)(.+?)(?<=\S)~~', r'<span class="strike">\1</span>', text)
        text = text.replace('\n', ' ')

        for _ in range(8):
            if '\x00' not in text:
                break
            text = re.sub(r'\x00(\d+)\x00', lambda m: stash[int(m.group(1))], text)
        return text

    @staticmethod
    def unescape_url(url):
        return re.sub(r'\\([!-/:-@\[-`{-~])', r'\1', url)

    def anchor(self, url, label_html):
        return '<a href="%s">%s</a>' % (esc_attr(self.link(url)), label_html)
