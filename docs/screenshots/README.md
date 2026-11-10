# Add screenshots 📸

Put screenshots directly in **`docs/screenshots/`**. PNG is a good default.

Suggested filenames:

| File | What to show | Placement |
| --- | --- | --- |
| `overview.png` | A selection with the results panel open | Main README, just below the introduction |
| `text-selection.png` | Underlined text with blue handles and Copy/Translate | Below the main README’s controls table |
| `dark-mode.png` | The app in dark mode | Below the feature list |
| `japanese.png` | Kana/kanji or a vertical Japanese selection | Optional Japanese example |

The main README already has a commented screenshot slot for `overview.png`. After adding the image, replace that comment with:

```markdown
![Circle to Search showing a selection and search results](docs/screenshots/overview.png)
```

For another image, add a similar line at the suggested place:

```markdown
![Selecting text with Copy and Translate](docs/screenshots/text-selection.png)
```

Use real app captures, crop unnecessary empty space, and check that private messages, account details and tokens are not visible. Around **1400–1920 pixels wide** is usually readable without making the repository unnecessarily large. Keep filenames lowercase with hyphens. Only add links for screenshots that exist, so the README has no broken image placeholders.
