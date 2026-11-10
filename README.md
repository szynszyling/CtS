# Circle to Search for KDE Plasma

Press **Meta+Shift+G**, then circle, highlight, scribble or tap something on your screen. Text becomes a blue selection with Copy/Translate actions; images get adjustable white corner brackets. Google results open automatically in an expandable sheet over your frozen desktop.

The appearance follows Google's original demonstrations: a neutral scrim, white gesture strokes, blue text highlights, a bottom search pill, and a results sheet with Google-style light and dark palettes. See the [reference notes](docs/REFERENCE.md) for sources, comparisons and desktop limitations.

## GPU OCR and self-hosting

CtS now has a **Vulkan GPU OCR backend**, supplied as a separate headless Docker service. It has been tested on the local Radeon 610M with English, kana/kanji, small dark-background text and vertical Japanese. Models remain loaded between selections; character boxes preserve selection handles and Latin word snapping. The same service can run on your own server, with Intel HD 630 compatibility to be checked against that server’s Vulkan driver.

```sh
python3 tools/setup_ocr_docker.py --gpu-name AMD --client
```

This builds and starts a local authenticated GPU container and selects it for the desktop app. **⋮ → Text recognition…** offers **Local GPU (managed by CtS)**, **Self-hosted CtS server**, and **Local Tesseract (CPU)**. CtS sets up/starts its local backend when you save Local GPU settings; server mode accepts your server address and token. You can check the actual device and enable optional local fallback. Server mode sends the frozen monitor image and regional crops to your configured server. Local Tesseract remains the default before server configuration.

On the synthetic 1920×1080 desktop, native GPU selections completed in **322 ms for English** and **226 ms for a Japanese underline** while background OCR continued. The server lets gesture requests interrupt background work between model calls; a full scan no longer holds up every new selection. Timings depend on hardware and content.

See the [backend deployment guide](server/README.md) for Docker Compose, Intel server setup, SSH tunnels, API details and real GPU checks.

## Install or update

Requires Python 3.10+, PySide6 (including Qt WebEngine), Spectacle and Tesseract. On Arch Linux:

```sh
sudo pacman -S pyside6 spectacle tesseract layer-shell-qt python-dbus
python3 install.py
```

The installer copies the app to `~/.local/share/circle-to-search`, creates `~/.local/bin/circle-to-search`, adds a launcher and registers **Meta+Shift+G**. An existing shortcut is preserved. It respects `XDG_DATA_HOME`.

On Wayland, LayerShellQt gives the selection surface an overlay role instead of a normal application-window role. It appears directly without Plasma's normal window opening animation. Automatic appearance follows Plasma’s selected color scheme, including changes while CtS is open. **⋮ → Theme** also offers Light and Dark overrides, which are remembered. English labels/results and translation targets remain independent of Plasma’s locale.

The overlay prepares its graphics surface before showing, so opening the embedded browser does not recreate it as a smaller window. An opaque cover in the selected theme stays over the browser until matching results are rendered, including tab changes and theme switches.

The Wayland surface uses the overlay layer with KWin's `utility` classification. A custom layer-shell namespace is treated as a normal window by KWin and still receives opening/closing effects; the utility classification excludes this overlay from the standard Scale, Fade and Popup effects. Plasma's global effect settings stay unchanged. The app supplies its own short transitions for the scrim, controls, selection highlights, active tab underline, and results-sheet opening, expansion, collapse and dismissal. The desktop image stays fixed in place throughout.

The Copy/Translate popup stays above the results sheet and browser, with an opaque capsule matching the theme and a thin gray divider. It fades and slides in/out and moves smoothly with the selection. Repeated layout updates do not restart its entrance animation.

English, Japanese and vertical Japanese models from Tesseract's official `tessdata_best` repository are included in the installation. Missing models are downloaded from a pinned revision and verified by SHA-256. System-wide language packs are not needed for these languages. The model license and provenance are in `circle_to_search/tessdata`.

To run directly from a checkout, fetch models first:

```sh
python3 tools/fetch_models.py
python3 -m circle_to_search
```

## Use

| Action | Control |
| --- | --- |
| Search an image or object | Circle it, scribble over it, or tap it |
| Select words | Draw a line across or just under the text |
| Select kana/kanji | Draw across the characters, or tap a character |
| Change text selection | Drag either blue handle |
| Resize an image selection | Drag a white corner |
| Move an image selection | Drag inside the selection |
| Force an image crop over text | **Shift + drag** |
| Copy or translate selected text | Floating **Copy / Translate** pill |
| Refine a search | Type in the search field and press **Enter** |
| Expand or collapse results | Click or drag the sheet's top handle |
| Clear selection/results | **Esc**, or the sheet's back button |
| Close | **Esc** again, top-left **×**, or right-click the desktop |
| Save/copy image | Top-right **⋮** menu |
| Follow Plasma or choose Light/Dark | **⋮ → Theme → Automatic (Plasma) / Light / Dark** |
| Select vertical Japanese | **⋮ → Vertical Japanese text**, or start with `--vertical` |
| Move the floating search bar | Drag the **Google G** in any direction |
| Move and resize results together | Drag their **Google G** or top handle diagonally |
| Place the search bar at top/bottom | **⋮ → Move search bar to top/bottom** |

Latin text snaps to words. Japanese character boxes allow partial phrases to be selected without adding spaces between kana and kanji. Full-screen OCR runs in the background using the selected local or self-hosted backend. If you finish a gesture before it is ready, a priority OCR scan reads just the nearby text, retaining word/character context. Successful text selection can complete immediately from that smaller region. An inconclusive regional scan waits for the full result before choosing image search. Large gestures reuse the full scan.

The existing high-accuracy Japanese/English models remain in use. Background completion expands the available handle coverage when it agrees with the selected phrase; it never substitutes different recognized text into an existing selection. Nearly straight underlines snap to one nearby line so closely spaced rows are not accidentally combined; taller scribbles can still select multiple lines.

Each monitor has an overlay; finish a gesture on one monitor. Current Spectacle versions capture all monitors at consistent scale. Older versions capture the monitor containing the pointer. An object tap starts a 200px adjustable crop; circling defines the region more precisely.

Drag the **Google G** to move the floating search bar freely in both directions. Inside results, drag either the **Google G** or the top handle: horizontal movement shifts the sheet, while upward/downward movement expands/shrinks it in the same gesture. Direction can change at any point without releasing the mouse. Clicking the top handle still expands or collapses the sheet. Positions stay within the screen and remain where you put them while changing result pages or expanding the sheet. Text-field dragging continues to select query text normally.

Visible controls and the results sheet consume pointer input throughout opening, loading and dismissal, so clicks do not start a selection on the frozen desktop behind them. The sheet reserves its destination as soon as its opening transition starts; uncovered desktop areas remain selectable.

## Options

```sh
python3 -m circle_to_search --no-auto-search  # select/copy locally; Enter searches
python3 -m circle_to_search --vertical        # vertical Japanese
python3 -m circle_to_search --external        # browser results instead of embedded
python3 -m circle_to_search --theme dark      # session override: auto, light or dark
python3 -m circle_to_search --mode box
python3 -m circle_to_search --ocr-language eng+pol
python3 -m circle_to_search --ocr-backend gpu  # CtS-managed local GPU
python3 -m circle_to_search --ocr-backend server --ocr-server http://127.0.0.1:8766 --ocr-token-file /path/to/token
python3 -m circle_to_search --image /path/to/picture.png
```

The default language setting is `jpn+eng`. Install matching system Tesseract packs for other languages. `CTS_OCR_LANGUAGE` sets the launcher's language preference. Missing language data is reported instead of silently falling back to English.

## Data and service behavior

Screen capture happens locally. OCR uses local Tesseract by default; configuring server mode sends the frozen monitor image and priority crops to your selected OCR server. Spectacle's full-desktop PNG is deleted before selection; the frozen image stays in memory. **By default, releasing a selection starts a Google search**: selected text goes to Google Search; the selected rectangular image crop goes directly to Google Lens. Use `--no-auto-search` or turn off automatic searching in the overflow menu to select and copy without searching. Translation sends text when requested. Clipboard actions use your normal desktop clipboard/history.

Embedded results use the app's own browser profile; it does not import your browser's login or cookies. Google's verification pages remain open and interactive, and persistent cookies are kept between launches so verification is not immediately discarded. The profile and cache use Qt's standard application data/cache locations under `circle-to-search`. Clicking a result link hands it to your system's default browser or link handler and dismisses CtS on every monitor. New-tab links, app links and the sheet's external-browser button use the same close-and-open behavior. Search tabs, image previews, Translate and verification remain inside the sheet. If Lens upload fails, save the crop from **⋮**, then use **⋮ → Open Google Lens** and upload it manually.

Image uploads happen inside the same browser session as Lens results, retaining the upload's cookies and verification state. Searches use Google's public web route with English requested; changing tabs preserves the query and Lens session. The same native **AI Mode / All / Images / Videos / Shopping / News / Forums / More / Tools** bar stays visible across search views. Google's redundant navigation is hidden. Translate's Sign in and Google apps controls are hidden while its translation inputs remain usable.

AI Mode uses a separate header cleanup path because its answer lives outside the normal results container. Answer text, citations and follow-up input remain visible inside the sheet.

Automatic mode reads Plasma’s `kdeglobals` window colors, resolves named color schemes when needed, and watches for live changes, including atomic file replacement. Manual preferences are saved separately in `~/.config/circle-to-search/appearance.conf` (or under `XDG_CONFIG_HOME`). CtS uses Qt’s GTK3 platform theme in its own process to deliver the same light/dark preference to WebEngine; the KDE plugin ignores app-local overrides on the tested system. The Google-style native palette covers fields, tabs, buttons, menus, popups, selection colors and loading/error states. Google Translate’s own theme switch is synchronized with the app, including its stored preference, so its inputs, language menus and actions also match. Its dark surface tokens use the same palette as the surrounding sheet, avoiding a darker rectangle inside the app. Images retain their original colors. Verification stays interactive when changing themes; isolated Google challenge frames may keep their own colors. Your desktop settings are unchanged. A Google HTTP 403 is reported as access denied, separately from an interactive verification or rate-limit page; login is not guaranteed to resolve a Google block.

Lens uses Google's web-upload endpoint, which is not a supported public API and can change or be rate-limited. Google's Android object segmentation, audio search, live scrolling translation and account-specific phone features are not part of this KDE implementation. Google's web results can differ from Android's.

## Verify

```sh
python3 tools/fetch_models.py
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
python3 tools/preview.py
```

Tests cover gestures, exact crop contents, handles, scaling and monitor offsets, inline search, model output, and kana/kanji selection. Real local OCR checks include 12–24px horizontal Japanese, small light text on a dark background, and vertical Japanese character positions. Tests do not capture your desktop or send image/text searches.

`python3 tools/desktop_smoke.py` exercises live desktop capture, the Wayland overlay role and native interaction without uploading the capture. `python3 tools/web_smoke.py` checks an English query and uploads a public Eiffel Tower fixture from `/tmp/cts-references/lens-eiffel.jpg`, requiring actual landmark matches and image cards. It keeps Google verification interactive if needed. These require a graphical Plasma session. The fixture is [Eiffel Tower 01 by buggolo on Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Eiffel_Tower_01.jpg); it is used locally for development and is not packaged.

`python3 tools/surface_smoke.py` checks full-screen geometry and pixel samples through three real browser transitions from dark to light test documents, without contacting Google. The live web check also switches Google Images/Videos tabs and monitors for opposite-theme frames and geometry changes. Add `--dark` to check dark appearance, or `--auto` to use Plasma’s current theme.

`python3 tools/theme_smoke.py` verifies native and real browser light/dark preferences, opaque popup/divider pixels, loading frames, live automatic changes and manual overrides using temporary settings and local HTML. It does not change Plasma’s settings or contact Google.

`python3 tools/motion_smoke.py` checks intermediate animation frames and stable fullscreen geometry, traces the actual Wayland layer role, and checks exclusion from the installed KWin Scale/Fade/Popup effect policies. It uses a synthetic desktop and local HTML. The surface check also includes an offline AI Mode layout regression. `python3 tools/ai_smoke.py` verifies a real AI Mode answer with a public test question in the app's own Google session.

`python3 tools/interaction_smoke.py` routes pointer events through the real native window to check bar/sheet dragging, input blocking before browser loading completes, and selecting uncovered areas. It uses a synthetic desktop and local HTML without capture or network requests.

`python3 tools/text_actions_smoke.py` checks popup opacity and divider pixels over an accelerated browser, button input, sheet stacking during expansion/collapse, and intermediate entrance/exit animation frames. It uses only synthetic content and local HTML.

`python3 tools/link_smoke.py` checks native result-link clicks and CtS dismissal using an intercepted desktop handler. Add `--case newtab` or `--case app` for alternate link types. These use local HTML with network requests blocked. `--real-opener` instead opens example.org through the system's configured handler for a real desktop handoff check.

`python3 tools/ocr_benchmark.py` times full-screen and regional OCR on a synthetic desktop. `python3 tools/selection_smoke.py` measures actual native first-selection latency; add `--japanese` to check an underline over small kanji/kana. Neither captures your desktop nor sends searches. On the tested 1920×1080 Wayland fixture, English selection completed in 0.40s and a Japanese underline in 0.56s while the full scan was still running (roughly 4–5s). Actual latency depends on the selected area, text and hardware. These older timings describe the local Tesseract path. The new Vulkan service performs neural-network inference on the GPU; see its [deployment and verification guide](server/README.md).

To stage an installation without altering launchers or shortcuts:

```sh
python3 install.py --prefix /tmp/circle-to-search-stage
```

## Remove

Remove Circle to Search in KDE's Shortcuts settings, then delete `~/.local/bin/circle-to-search`, `~/.local/share/circle-to-search`, `~/.local/share/applications/io.github.circle_to_search.desktop`, and `~/.local/share/icons/hicolor/scalable/apps/circle-to-search.svg` (use your configured `XDG_DATA_HOME` if different).
