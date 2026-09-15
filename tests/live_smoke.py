"""Opt-in live test of the built ZIP, without installing or changing a library."""

from pathlib import Path
from queue import Queue
from threading import Event
from calibre.customize.zipplugin import loader
from calibre.utils.logging import default_log
from calibre.utils.imghdr import identify


def main():
    root = Path(__file__).resolve().parents[1]
    version = (root / 'version.txt').read_text().strip()
    plugin = loader.load(str(root / ('sfarim_steimatzky_v' + version + '.zip')))(None)
    results = Queue()
    error = plugin.identify(default_log, results, Event(), title='אבא עשיר אבא עני לבני נוער',
                            authors=['רוברט קיוסאקי ושרון לכטר'])
    assert not error, error
    matches = []
    while not results.empty():
        matches.append(results.get())
    mi = next(m for m in matches if m.identifiers.get('steimatzky') == '013620090')
    assert mi.authors and mi.publisher
    assert mi.title == 'אבא עשיר אבא עני לבני נוער'
    # This page has no publication date: it must not be invented from other numbers.
    assert mi.pubdate is None
    covers = Queue()
    # Fresh instance also tests cover-only lookup without a pre-populated cache.
    cover_plugin = type(plugin)(None)
    error = cover_plugin.download_cover(default_log, covers, Event(), identifiers=mi.identifiers)
    assert not error, error
    assert not covers.empty(), 'No cover returned'
    fmt, width, height = identify(covers.get()[1])
    assert width >= 1000 and height >= 1000, 'Expected the full gallery image'
    print('LIVE PASS:', plugin.name, plugin.version, 'cover:', fmt, width, height)


if __name__ == '__main__':
    main()
