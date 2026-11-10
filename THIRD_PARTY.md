# Third-party components and artwork

CtS's original code is covered by the [MIT license](LICENSE). The license does
not replace the terms of third-party code, models, dependencies or artwork.

## Desktop dependencies and models

- [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/licenses.html) and Qt
  modules retain their upstream licenses, including LGPLv3/GPLv3 or commercial
  terms as applicable. Distributors must comply with the licenses of the Qt
  modules they include.
- Tesseract English and Japanese models come from
  [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) and retain their
  [Apache 2.0 license](circle_to_search/tessdata/LICENSE). Their exact revision
  and checksums are recorded in
  [the model manifest](circle_to_search/tessdata/models.json).
- System dependencies, including Tesseract, Spectacle and LayerShellQt, retain
  their own licenses. CtS's MIT license does not relicense them.

## OCR server

See [the server's third-party notices](server/THIRD_PARTY.md) for the adapted
ncnn implementation, OCR models and associated licenses. Other Python and
system dependencies in the image retain the notices shipped with their
distributions.

## Google artwork and services

`circle_to_search/icons/google.png` and `circle_to_search/icons/lens.svg` are
Google artwork provided for the project by its author. These assets and Google's
names and trademarks are excluded from CtS's MIT license. CtS does not grant
rights to them or claim affiliation with Google. The source artwork's
redistribution permissions have not yet been verified.

Google Search, Lens and Translate remain external services subject to their own
terms. Their page content is not licensed by this repository.
