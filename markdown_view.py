import base64
import html
import os
import re
import struct
import webbrowser
from urllib.parse import unquote

import sublime
import sublime_plugin

from . import mdrender
from .mdrender import code_html, esc

SETTINGS = 'MarkdownView.sublime-settings'
BUTTON_KEY = 'markdown_view_button'
MD_EXTENSIONS = ('.md', '.markdown', '.mdown', '.mkd', '.mkdn')
IMAGE_TYPES = {'.png': 'png', '.jpg': 'jpeg', '.jpeg': 'jpeg', '.gif': 'gif'}
LANG_ALIASES = {
    'js': 'JavaScript', 'javascript': 'JavaScript', 'ts': 'TypeScript', 'typescript': 'TypeScript',
    'py': 'Python', 'python': 'Python', 'c++': 'C++', 'cpp': 'C++', 'cs': 'C#', 'csharp': 'C#',
    'sh': 'Bash', 'bash': 'Bash', 'shell': 'Bash', 'zsh': 'Bash', 'console': 'Bash',
    'ps': 'PowerShell', 'ps1': 'PowerShell', 'powershell': 'PowerShell', 'bat': 'Batch File',
    'cmd': 'Batch File', 'json': 'JSON', 'jsonc': 'JSON', 'yml': 'YAML', 'yaml': 'YAML',
    'md': 'Markdown', 'markdown': 'Markdown', 'html': 'HTML', 'xml': 'XML', 'css': 'CSS',
    'rs': 'Rust', 'rust': 'Rust', 'go': 'Go', 'lua': 'Lua', 'rb': 'Ruby', 'java': 'Java',
    'sql': 'SQL', 'diff': 'Diff', 'patch': 'Diff', 'cmake': 'CMake', 'ini': 'INI', 'toml': 'TOML',
}

# Source view id -> preview sheet.
PREVIEWS = {}
_pending = {}

CSS = '''
html, body { background-color: var(--background); color: var(--foreground); }
body { font-family: "Segoe UI", system-ui, sans-serif; font-size: %(size)dpx; padding: 0.75rem 2rem 2rem 2rem; }
a { color: var(--bluish); text-decoration: none; }
p { margin: 0 0 1rem 0; }
h1, h2, h3, h4, h5, h6 { font-weight: bold; margin: 1.5rem 0 1rem 0; }
h1, h2 { padding-bottom: 0.3rem; border-bottom: 1px solid color(var(--foreground) alpha(0.15)); }
h1 { font-size: 2em; }
h2 { font-size: 1.5em; }
h3 { font-size: 1.25em; }
h4 { font-size: 1em; }
h5 { font-size: 0.875em; }
h6 { font-size: 0.85em; color: color(var(--foreground) alpha(0.6)); }
.hr { border-top: 0.25rem solid color(var(--foreground) alpha(0.2)); margin: 1.5rem 0; }
code, .kbd { font-family: "Cascadia Mono", Consolas, monospace; font-size: 0.85em;
    background-color: color(var(--foreground) alpha(0.1)); border-radius: 0.3rem; padding: 0.1rem 0.35rem; }
.kbd { border: 1px solid color(var(--foreground) alpha(0.25)); }
.code { font-family: "Cascadia Mono", Consolas, monospace; font-size: 0.85em; line-height: 1.45;
    background-color: color(var(--foreground) alpha(0.06)); border-radius: 0.4rem; padding: 1rem; margin: 0 0 1rem 0; }
.bar { padding: 0 0 0 0.25rem; margin: 0 0 1rem 0; }
.quote-bar { background-color: color(var(--foreground) alpha(0.25)); }
.quote { background-color: var(--background); color: color(var(--foreground) alpha(0.7)); padding: 0 0 0 1rem; }
.alert { background-color: var(--background); padding: 0.5rem 0 0.1rem 1rem; }
.alert-title { font-weight: bold; margin: 0 0 0.5rem 0; }
ul, ol { margin: 0 0 1rem 0; padding: 0 0 0 2rem; }
li { margin: 0.25rem 0; }
li ul, li ol { margin: 0; }
.task { color: color(var(--foreground) alpha(0.7)); }
.strike { text-decoration: line-through; color: color(var(--foreground) alpha(0.6)); }
.mark { background-color: color(var(--yellowish) alpha(0.3)); }
.fn { color: var(--bluish); }
.table { font-family: "Cascadia Mono", Consolas, monospace; font-size: 0.85em; margin: 0 0 1rem 0; }
.tr { padding: 0.3rem 0; border-bottom: 1px solid color(var(--foreground) alpha(0.2)); }
.th { font-weight: bold; background-color: color(var(--foreground) alpha(0.06));
    border-top: 1px solid color(var(--foreground) alpha(0.2)); }
.odd { background-color: color(var(--foreground) alpha(0.04)); }
.sep { color: color(var(--foreground) alpha(0.25)); }
.table code { padding: 0; border-radius: 0; font-size: 1em; }
.summary { font-weight: bold; margin: 0 0 0.5rem 0; }
.details, .pre { margin: 0 0 1rem 0; }
.toolbar { margin: 0 0 1rem 0; }
.toolbar a { color: var(--foreground); background-color: color(var(--foreground) alpha(0.08));
    border-radius: 0.3rem; padding: 0.2rem 0.6rem; font-size: 0.9em; }
img { margin: 0.25rem 0; }
'''


def settings():
    return sublime.load_settings(SETTINGS)


def is_markdown(view):
    if not view or not view.is_valid():
        return False
    if view.match_selector(0, 'text.html.markdown'):
        return True
    name = view.file_name() or ''
    return name.lower().endswith(MD_EXTENSIONS)


def source_for_sheet(sheet):
    if sheet is None:
        return None
    for view_id, preview in PREVIEWS.items():
        if preview.id() == sheet.id():
            return sublime.View(view_id)
    return None


def subl_href(command, args=None):
    return 'subl:%s %s' % (command, sublime.encode_value(args or {}))


def image_size(data, kind):
    try:
        if kind == 'png':
            return struct.unpack('>II', data[16:24])
        if kind == 'gif':
            return struct.unpack('<HH', data[6:10])
        if kind == 'jpeg':
            i = 2
            while i < len(data):
                marker, length = data[i + 1], struct.unpack('>H', data[i + 2:i + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack('>HH', data[i + 5:i + 9])
                    return w, h
                i += 2 + length
    except (struct.error, IndexError):
        pass
    return None


class Highlighter:
    """Colours code with Sublime's own syntaxes, read back from a hidden output panel."""

    def __init__(self, window):
        self.window = window
        self.panel = None

    @staticmethod
    def find_syntax(lang):
        lang = lang.lower()
        for name in (LANG_ALIASES.get(lang), lang):
            if name:
                found = [s for s in sublime.find_syntax_by_name(name) if not s.hidden]
                if found:
                    return found[0]
        return sublime.find_syntax_for_file('file.' + lang)

    def __call__(self, code, lang):
        if not self.window or not settings().get('highlight_code', True):
            return None
        syntax = self.find_syntax(lang)
        if not syntax or syntax.scope == 'text.plain':
            return None
        if self.panel is None:
            self.panel = self.window.create_output_panel('markdown_view_highlight', unlisted=True)
            self.panel.settings().set('auto_indent', False)
        panel = self.panel
        panel.assign_syntax(syntax)
        panel.run_command('markdown_view_set_text', {'text': code})
        default = panel.style()['foreground']
        out = []
        for region, scope in panel.extract_tokens_with_scopes(sublime.Region(0, panel.size())):
            style = panel.style_for_scope(scope)
            text = code_html(panel.substr(region))
            if style.get('bold'):
                text = '<b>%s</b>' % text
            if style.get('italic'):
                text = '<i>%s</i>' % text
            fg = style.get('foreground', default)
            out.append(text if fg == default else '<span style="color: %s;">%s</span>' % (fg, text))
        return ''.join(out)


def build_html(view):
    base = os.path.dirname(view.file_name() or '')

    def link(url):
        return subl_href('markdown_view_open_link', {'url': url, 'base': base})

    def image(src, alt, title, width):
        if re.match(r'[a-z]+:', src, re.I) and not src.lower().startswith('file:'):
            return '<a href="%s">\U0001f5bc %s</a>' % (html.escape(link(src)), esc(alt or src))
        path = os.path.normpath(os.path.join(base, unquote(re.sub(r'^file:/*', '', src))))
        kind = IMAGE_TYPES.get(os.path.splitext(path)[1].lower())
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError:
            data = None
        if not kind or data is None:
            return '<span class="task">\U0001f5bc %s</span>' % esc(alt or src)
        size = image_size(data, kind)
        attrs = ''
        if size:
            w, h = size
            target = min(width or w, settings().get('max_image_width', 800))
            attrs = ' width="%d" height="%d"' % (target, round(h * target / w)) if w else ''
        return '<img src="data:image/%s;base64,%s"%s>' % (kind, base64.b64encode(data).decode('ascii'), attrs)

    # Looked up through the module so an edited mdrender.py takes effect when Sublime reloads it.
    renderer = mdrender.Renderer(link=link, image=image, highlight=Highlighter(view.window()))
    body = renderer.render(view.substr(sublime.Region(0, view.size())))
    toolbar = '<div class="toolbar"><a href="%s">✎ Edit</a></div>' % html.escape(subl_href('markdown_view_toggle'))
    css = CSS % {'size': settings().get('font_size', 15)}
    return '<html><body id="markdown-view"><style>%s</style>%s%s</body></html>' % (css, toolbar, body)


def preview_title(view):
    name = os.path.basename(view.file_name() or '') or view.name() or 'untitled'
    return '\U0001f441 ' + name


def close_sheet(sheet):
    if hasattr(sheet, 'close'):
        sheet.close()
        return
    window = sheet.window()
    if window:
        window.focus_sheet(sheet)
        window.run_command('close_file')


def live_preview(view_id):
    sheet = PREVIEWS.get(view_id)
    if not sheet:
        return None
    if sheet.window() is None:
        del PREVIEWS[view_id]
        return None
    return sheet


class MarkdownViewToggleCommand(sublime_plugin.WindowCommand):
    def run(self):
        window = self.window
        source = source_for_sheet(window.active_sheet())
        if source:
            sheet = PREVIEWS.pop(source.id())
            close_sheet(sheet)
            if source.is_valid():
                window.focus_view(source)
            return
        view = window.active_view()
        if not is_markdown(view):
            return
        sheet = live_preview(view.id())
        if sheet:
            window.focus_sheet(sheet)
            return
        group, index = window.get_sheet_index(view.sheet())
        sheet = window.new_html_sheet(preview_title(view), build_html(view), group=group)
        window.set_sheet_index(sheet, group, index + 1)
        window.focus_sheet(sheet)
        PREVIEWS[view.id()] = sheet

    def is_enabled(self):
        return bool(source_for_sheet(self.window.active_sheet()) or is_markdown(self.window.active_view()))

    def is_visible(self):
        return self.is_enabled()


class MarkdownViewSetTextCommand(sublime_plugin.TextCommand):
    def run(self, edit, text):
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)


class MarkdownViewOpenLinkCommand(sublime_plugin.WindowCommand):
    def run(self, url, base=''):
        if url.startswith('#'):
            return
        if re.match(r'[a-z][a-z0-9+.-]*:', url, re.I) and not url.lower().startswith('file:'):
            webbrowser.open(url)
            return
        path = unquote(re.sub(r'^file:/*', '', url).split('#')[0])
        path = os.path.normpath(os.path.join(base, path))
        if os.path.isdir(path):
            self.window.run_command('open_dir', {'dir': path})
        elif os.path.exists(path):
            self.window.open_file(path)
        else:
            sublime.status_message('Markdown View: not found: ' + path)


class MarkdownViewListener(sublime_plugin.EventListener):
    def on_activated_async(self, view):
        self.update_button(view)

    def on_load_async(self, view):
        self.update_button(view)

    def on_post_save_async(self, view):
        self.update_button(view)

    def update_button(self, view):
        if not is_markdown(view) or not settings().get('show_button', True):
            view.erase_regions(BUTTON_KEY)
            return
        window = view.window()
        if not window:
            return
        line = view.line(0)
        button = '<a href="toggle">\U0001f441 Preview</a>'
        view.add_regions(BUTTON_KEY, [line], '', '', sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE,
                         annotations=[button],
                         on_navigate=lambda href: window.run_command('markdown_view_toggle'))

    def on_modified_async(self, view):
        if not live_preview(view.id()) or not settings().get('live_update', True):
            return
        token = _pending[view.id()] = _pending.get(view.id(), 0) + 1
        sublime.set_timeout_async(lambda: self.refresh(view, token), settings().get('update_delay_ms', 300))

    def refresh(self, view, token):
        if _pending.get(view.id()) != token or not view.is_valid():
            return
        sheet = live_preview(view.id())
        if sheet:
            sheet.set_contents(build_html(view))

    def on_close(self, view):
        sheet = PREVIEWS.pop(view.id(), None)
        _pending.pop(view.id(), None)
        if sheet and sheet.window():
            close_sheet(sheet)
