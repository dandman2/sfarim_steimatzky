"""Bounded, cancellable public catalog requests through Calibre's browser."""

from contextlib import closing
from urllib.parse import urlencode

from .steimatzky_html import BASE, book_id, search_page, details_page


def read(browser, url, timeout):
    """Close mechanize responses explicitly; they are not context managers."""
    with closing(browser.open(url, timeout=timeout)) as response:
        return response.read()


def search(browser, title, abort, timeout, pages, log):
    """Visit descending relevance pages once, keeping candidates if a later page fails."""
    results, seen = [], set()
    for page in range(1, pages + 1):
        if abort.is_set() or (page > 1 and abort.wait(0.5)):
            break
        url = BASE + '/catalogsearch/result/?' + urlencode({'q': title, 'p': page})
        try:
            books, more = search_page(read(browser, url, timeout))
        except Exception:
            if not results:
                raise
            log.exception('Steimatzky search pagination failed; retaining earlier results.')
            break
        added = 0
        for book in books:
            if book['id'] not in seen:
                results.append(book)
                seen.add(book['id'])
                added += 1
        if not more or not added:
            break
    return results


def details(browser, ident, timeout):
    """Fetch only a numeric Steimatzky product URL and verify its book identity."""
    if book_id('/' + ident) != ident:
        raise ValueError('Invalid Steimatzky identifier.')
    return details_page(read(browser, BASE + '/' + ident, timeout), ident)
