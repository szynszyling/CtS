<p align="center">
  <img src="assets/circle-to-search.svg" width="76" alt="Circle to Search icon">
</p>

<h1 align="center">Circle to Search 🔎</h1>

<p align="center"><b>Circle it. Select it. Search it.</b><br>
Search text and images without leaving what you’re doing.</p>

<p align="center">
  <a href="docs/INSTALL.md">Installation</a> ·
  <a href="server/README.md">OCR server</a> ·
  <a href="docs/screenshots/README.md">Screenshots</a> ·
  <a href="docs/DEVELOPMENT.md">Development</a>
</p>

Press **Meta + Shift + G** on Plasma or **Win + Shift + G** on Windows, draw around something on your screen, and see Google results in a floating panel. Draw a line through or underneath words to select text instead.

<!-- Screenshot slot: add docs/screenshots/overview.png, then uncomment:
![Circle to Search showing a selection and search results](docs/screenshots/overview.png)
-->

## What can it do? ✨

- **🔍 Search images:** circle an object or picture to search with Google Lens.
- **📝 Select text:** underline words, scribble over them, or tap a word. Copy or translate your selection.
- **🇯🇵 Read Japanese:** select kana, kanji and vertical text, as well as English.
- **🌗 Match your desktop:** light, dark, or automatic appearance following Plasma.
- **↔️ Make room:** move the search bar, move and expand the results, and adjust your selection.
- **🏠 Choose where text is read:** on your computer, on its GPU, or on your own OCR server.

*OCR means text recognition: turning the words in a screenshot into selectable text.*

Open **⋮ → Display language** to choose English or Polski. Google Search, Lens and Translate follow that choice. Open **⋮ → OCR languages…** to choose and download models for local Tesseract. Available packs include Polish, other Latin-script languages, Ukrainian, Russian, Bulgarian, Serbian Cyrillic, Greek, Japanese, Korean and Chinese. The GPU and server engines have their own language support.

## Supported systems 🖥️

| System | Status |
| --- | --- |
| Linux with KDE Plasma 6 | ✅ Available; tested on Arch Linux and Wayland |
| Windows x64 | ✅ Native overlay, tray shortcut and Vulkan OCR |
| macOS | 🗂️ Structure prepared; app not available yet |
| OCR server | 🐳 Available as a Linux AMD64 Docker image |

This project brings a Circle to Search-style interaction to the desktop. It is an independent project, not an official Google application. Some Android-only features are not available.

## Maintenance 🛠️

CtS is a personal project maintained in my spare time. Updates, support and response times are not guaranteed. Contributions and forks are welcome, but reviews may take time.

## Get started 🚀

### 1. Install

On **Windows x64**, run the small Setup executable from [GitHub Releases](https://github.com/szynszyling/CtS/releases/latest). It downloads the app and adds a Start menu entry. A portable ZIP is also available. See the [Windows guide](packaging/windows/README.md) for startup shortcuts and local CPU OCR.

On **Arch Linux with KDE Plasma**, download and extract this repository, then open a terminal in its folder and run:

```sh
sudo pacman -S --needed pyside6 qt6-webengine qt6-svg spectacle tesseract layer-shell-qt python-dbus
python3 install.py
```

The installer adds **Circle to Search** to your application menu and sets the shortcut **Meta + Shift + G**. The first installation downloads the English and Japanese text-recognition models.

Using another KDE Linux distribution, or updating an existing installation? See the [installation guide](docs/INSTALL.md).

### 2. Select something

Press **Meta + Shift + G** (Plasma) or **Win + Shift + G** (Windows). Your screen freezes while you make a selection:

| What you want | What to do |
| --- | --- |
| Search a picture or object | Draw around it, scribble over it, or tap it |
| Select words | Draw through or underneath the text |
| Change selected text | Drag a blue handle |
| Change an image crop | Drag a white corner |
| Copy or translate text | Use the **Copy / Translate** popup |
| Move the search bar | Drag its **Google G** |
| Move or expand results | Drag the panel’s top handle |
| Start another selection | Press **Esc** |
| Close the app | Press **Esc** again, or click **×** |

Search starts when you finish a selection. You can turn automatic searching off in the **⋮** menu if you only want to select and copy.

### 3. Adjust it to suit you

Open **⋮** for appearance, text recognition and vertical Japanese settings. You can start with the defaults—no Docker or server setup is needed for ordinary text selection.

## Want GPU or server text recognition? ⚡

Open **⋮ → Text recognition** and choose:

| Choice | Where it runs | What you need |
| --- | --- | --- |
| **Local Tesseract (CPU)** | Your computer | Nothing beyond the normal installation |
| **Local GPU (managed by CtS)** | Your computer’s GPU | A Vulkan GPU; Docker on Linux, native worker on Windows |
| **Self-hosted CtS server** | Your own server or NAS | Its address and OCR token |

For the server, save just **[compose.yaml](compose.yaml)** in a folder on your NAS, fill in its OCR token and render-group number, and run `docker compose up -d`. CtS joins the existing external Docker network **`server`**, shared with SWAG. Docker pulls `ghcr.io/szynszyling/cts-ocr:latest` from the public registry without a login. You do not need a repository clone, `.env` file or source files on the NAS. See the [single-file setup guide](server/README.md) and [SWAG configuration](server/REMOTE_ACCESS.md).

## A few useful things to know 💡

- Selected text or image crops go to Google when you search. Translation sends the selected text when requested.
- Local text recognition stays on your computer. Server recognition sends the screenshot and selection crops to the server you configured.
- Clicking a result opens your normal browser and closes CtS.
- Google may ask for verification or block embedded searches. Complete the verification in the panel, or use **Open in browser**.
- Text-recognition accuracy and speed depend on your hardware, text size and font. A GPU is not always faster than a CPU.

Need help? Start with [installation and troubleshooting](docs/INSTALL.md). Technical details, command-line options and instructions for adding another OS are in the [developer guide](docs/DEVELOPMENT.md).

## License 📄

CtS's original code is available under the [MIT license](LICENSE). Third-party code, OCR models, dependencies and Google artwork retain their own terms; see [third-party notices](THIRD_PARTY.md).
