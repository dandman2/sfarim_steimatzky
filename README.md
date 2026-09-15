# Sfarim Steimatzky

Standalone Calibre metadata-source plugin for [Steimatzky](https://www.steimatzky.co.il).
It searches public book pages and offers matches through Calibre's normal metadata dialog.
No website account, API key, extra Python packages, or other Sfarim plugin is needed.

## Installation and use

1. In Calibre, open **Preferences → Plugins → Load plugin from file**.
2. Select `sfarim_steimatzky_v1.1.zip`, accept Calibre's plugin prompt, and restart Calibre.
3. Check **Preferences → Metadata download** and enable **Sfarim Steimatzky**.
4. Select a book with a title and preferably an author. Use **Edit metadata → Download metadata** or **Download cover**.

Adding a book alone does not run this plugin. To test the source independently, temporarily
enable only Sfarim Steimatzky for the metadata download, then restore your preferred sources.
The plugin does not install itself, change the library automatically, or alter other plugins.

## Metadata and matching

- Searches the public search form by title; ranks results using normalized Hebrew title and author text.
- Reads only cards marked as books, excluding games and other merchandise.
- Deduplicates product IDs across pages and stops at the configured limit or repeated pages.
- Fetches title, author, publisher, synopsis, categories and language when supplied.
- Reads publication year and valid ISBN only when explicitly supplied by the book page.
  Many tested pages omit both. Dates in the synopsis, filenames and image timestamps are never publication dates.
- Keeps the site's numeric product SKU as a `steimatzky` identifier, preserving leading zeros.
  A SKU is not an ISBN. An existing Steimatzky identifier enables direct lookup.
- ISBN-only search is not implemented; supply a title or Steimatzky identifier.
- Structured author lists are preserved. A combined author string on the site remains combined;
  Hebrew conjunctions inside names are not split by guessing.
- Multiple plausible matches remain available for manual selection, including alternate editions.

## Full-size covers

Uses the main book-page gallery image's explicit `full` URL, ahead of `img` or catalog thumbnails.
Back-cover gallery images do not replace the main cover. Downloads are validated as images before
Calibre receives them. If a page lacks a gallery full image, the page's normal image is a fallback;
its resolution depends on the source. The live validation checks a full image of at least 1000 pixels per side.

## Settings and errors

Under **Preferences → Plugins → Metadata source → Sfarim Steimatzky → Customize plugin**:

- Maximum metadata candidates: default 5, bounded to 1–20.
- Maximum search pages: default 3, bounded to 1–5.

Requests use Calibre's browser and timeout, with a short delay between pages and details.
Cancellation stops further work. Network and parsing errors go to Calibre's metadata job log;
results from successful earlier pages remain available if a later page fails. This scraper depends
on the public HTML structure and may need an update if the website changes.

## Build the next release

Run `build_plugin.cmd` from any working directory, with Python 3.9+ on PATH.
The builder reads `version.txt`, increments its minor integer, updates the internal Calibre
version and creates `sfarim_steimatzky_v<major>.<minor>.zip` in this folder.
The first supplied ZIP is 1.1; the next successful run creates 1.2. The recorded version means
the last successfully exported version. Versions 1.9 and 1.10 are consecutive releases.

Only `src/` is packaged. The builder prevents simultaneous builds and overwriting an existing ZIP,
validates the archive before publishing it, and rolls back version changes if committing fails.
Each release must be loaded into Calibre manually, followed by a restart.

## Validation

Use Calibre's Python for plugin tests (it supplies lxml and the Calibre modules). To isolate test preferences:

```powershell
$env:CALIBRE_CONFIG_DIRECTORY = Join-Path $env:TEMP 'steimatzky-plugin-validation'
& 'C:\Program Files\Calibre2\calibre-debug.exe' -e .\tests\test_steimatzky.py
python .\tests\test_build_plugin.py
& 'C:\Program Files\Calibre2\calibre-debug.exe' -e .\tests\live_smoke.py
```

The first two commands test offline parsing/integration and temporary build copies.
The last command uses the live website and loads the current ZIP without installing it.
No test adds, changes, or removes library books.
