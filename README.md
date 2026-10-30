# Markdown View

Read Markdown inside Sublime Text 4, rendered like a GitHub page in your own colour scheme. One key toggles between editing and viewing.

## Install

1. In Sublime Text, open **Preferences > Browse Packages...**
2. Clone this repository into that folder as `MarkdownView`:

   ```
   git clone https://github.com/<you>/MarkdownView.git MarkdownView
   ```

   Or download the ZIP and extract it there, renaming the folder to `MarkdownView`.
3. Open any `.md` file and press `Alt+M`.

Requires Sublime Text 4 (build 4126 or newer). No other packages needed.

## Use

- `Alt+M` opens the preview next to the file, and from the preview returns to the file.
- Or click **👁 Preview** at the end of the first line, **✎ Edit** at the top of the preview, the right-click menu, or **Markdown View: Toggle Edit/View** in the Command Palette.
- The preview updates as you type.

## Troubleshooting

- **Nothing happens on `Alt+M`:** the file must be Markdown (`.md` syntax or extension). Check for a clash in **Preferences > Key Bindings**.
- **No preview or button:** open the console (`` Ctrl+` ``) and look for errors mentioning `MarkdownView`. Check the folder is named `MarkdownView` and sits directly in the Packages folder.
- **Web images show as links:** Sublime can only display local PNG, JPG and GIF files. SVGs and remote images appear as links.
- **Tables use a monospace font:** Sublime's HTML has no tables or widths, so columns are lined up by character count. Emoji and CJK text in a table can push a column out of line.

## Settings

**Preferences: Markdown View Settings** in the Command Palette.

| Setting | Default | |
|---|---|---|
| `show_button` | `true` | Preview button on the first line |
| `font_size` | `15` | Body text size in pixels |
| `live_update` | `true` | Re-render while typing |
| `update_delay_ms` | `300` | Delay before re-rendering |
| `highlight_code` | `true` | Colour code blocks with Sublime's syntaxes |
| `max_image_width` | `800` | Images wider than this are scaled down |

To change the key, add to your user key bindings:

```json
{ "keys": ["ctrl+k", "ctrl+m"], "command": "markdown_view_toggle" }
```
