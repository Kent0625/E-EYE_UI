# Local OCR runtime

- `tesseract.min.js` and `worker.min.js`: npm package `tesseract.js` 6.0.1, copied from its `dist` directory. License: `TESSERACT-JS-LICENSE.md`.
- `tesseract-core-lstm.wasm.js` and `tesseract-core-lstm.wasm`: npm package `tesseract.js-core` 6.1.2. License: `TESSERACT-CORE-LICENSE`.
- `eng.traineddata.gz`: retained from the existing Eye Result Reader project. SHA-256 of the uncompressed trained data: `5dc5d8d640a212c9d6184921ba103b186f50e0fed9ee716c53e6b312b400d747`.

The receipt interface sets explicit same-origin worker, core and language paths. It has no CDN fallback. `python -m scripts.check_receipt_ui` blocks external requests and verifies real OCR extraction and confirmed session pairing using a labelled synthetic receipt.
