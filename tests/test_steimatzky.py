"""Offline checks for Hebrew parsing, pagination, covers and Calibre integration."""

import io
import json
from html import escape
from pathlib import Path
from queue import Queue
import sys
from threading import Event
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.steimatzky_html import BASE, book_id, image_url, search_page, details_page
from src.steimatzky_client import search
from src.steimatzky_cover import download
from src.steimatzky_plugin import SfarimSteimatzkyPlugin
from src.book_matching import normalize, rank_books

COVER = BASE + '/pub/media/catalog/product/cache/full/0/1/0123.jpg'
SEARCH = '''<ul class="product-items"><li class="product-item">
<div class="product-is_book">1</div><div class="product-category-name">
<a href="/0123">שפה : מבוא</a></div><div class="author"><a>יובל אילון</a></div>
</li></ul><a class="action next" href="?p=2">Next</a>'''


def product(**overrides):
    metadata = {'@type': 'book', 'sku': '0123', 'name': 'שפה : מבוא',
                'author': ['יובל אילון', 'מחבר שני'], 'publisher': 'הוצאה לדוגמה',
                'datePublished': '2021', 'isbn': '9780306406157',
                'image': COVER.replace('/full/', '/thumb/')}
    metadata.update(overrides)
    gallery = {'Idus_Product/js/gallery': {'data': [
        {'type': 'image', 'isMain': False, 'full': COVER.replace('0123', 'back')},
        {'type': 'image', 'isMain': True, 'full': COVER, 'thumb': metadata['image']}]}}
    return ('<html><script type="application/ld+json">' + json.dumps(metadata) + '</script>'
            '<h1 class="product-page-name">שפה : מבוא</h1>'
            '<li class="product-detail"><span>שפה:</span><span>עברית</span></li>'
            '<li class="product-detail"><span>תחום:</span><span>עיון</span></li>'
            '<li class="product-detail"><span>תת תחום:</span><span>עיון</span></li>'
            '<li class="product-detail description"><span class="product-short-desc">סיפור בשנת 1990</span>'
            '<span class="product-rest-desc">טקסט &lt;b&gt;נוסף&lt;/b&gt;</span></li>'
            '<div data-gallery-role="gallery-placeholder" data-mage-init="' + escape(json.dumps(gallery), quote=True) + '"></div></html>')


class HtmlTests(unittest.TestCase):
    def test_utf8_cards_and_deduplication(self):
        books, more = search_page((SEARCH + SEARCH).encode())
        self.assertTrue(more)
        self.assertEqual(books, [{'id': '0123', 'title': 'שפה : מבוא', 'authors': ['יובל אילון']}])

    def test_non_books_and_foreign_links_are_excluded(self):
        data = SEARCH.replace('>1<', '>0<') + SEARCH.replace('href="/0123"', 'href="https://example.com/0123"')
        self.assertEqual(search_page(data)[0], [])
        self.assertEqual(search_page('<html><p>No results</p></html>'), ([], False))

    def test_details_hebrew_and_full_main_cover(self):
        book = details_page(product().encode(), '0123')
        self.assertEqual(book['authors'], ['יובל אילון', 'מחבר שני'])
        self.assertEqual(book['publisher'], 'הוצאה לדוגמה')
        self.assertEqual(book['year'], 2021)
        self.assertEqual(book['tags'], ['עיון'])
        self.assertEqual(book['cover'], COVER)
        self.assertIn('1990', book['comments'])

    def test_no_invented_year_or_isbn(self):
        book = details_page(product(datePublished='', isbn=''), '0123')
        self.assertIsNone(book['year'])
        self.assertEqual(book['isbn'], '')
        self.assertIsNone(details_page(product(datePublished='2011 / 2021'), '0123')['year'])

    def test_nonbook_and_wrong_identity_are_rejected(self):
        with self.assertRaises(ValueError):
            details_page(product(), '999')
        with self.assertRaises(ValueError):
            details_page(product(**{'@type': 'Product'}), '0123')

    def test_malformed_gallery_falls_back_to_catalog_image(self):
        data = product().replace('data-mage-init=', 'broken-gallery=')
        self.assertEqual(details_page(data, '0123')['cover'], COVER.replace('/full/', '/thumb/'))

    def test_url_validation_preserves_leading_zero(self):
        self.assertEqual(book_id('/0123'), '0123')
        self.assertIsNone(book_id('https://steimatzky.co.il.evil.test/0123'))
        self.assertIsNone(book_id('/checkout/cart/add'))
        self.assertIsNone(image_url('https://example.com/cover.jpg'))
        self.assertIsNone(image_url(BASE + '/pub/media/catalog/product/placeholder/book_back.jpg'))

    def test_hebrew_normalization_and_author_relevance(self):
        self.assertEqual(normalize('שָׂפָה'), normalize('שפה'))
        books = [{'id': '1', 'title': 'שפה : מבוא', 'authors': ['אחר']},
                 {'id': '2', 'title': 'שפה : מבוא', 'authors': ['יובל אילון']},
                 {'id': '3', 'title': 'אוכל טעים', 'authors': ['יובל אילון']}]
        self.assertEqual([b['id'] for b in rank_books(books, 'שפה', ['יובל אילון'])], ['2', '1'])


class ClientTests(unittest.TestCase):
    def test_response_without_context_manager_is_closed(self):
        response = Mock(spec=['read', 'close'])
        response.read.return_value = SEARCH.encode()
        browser = Mock()
        browser.open.return_value = response
        self.assertEqual(search(browser, 'שפה', Event(), 30, 1, Mock())[0]['id'], '0123')
        response.close.assert_called_once()

    def test_pagination_deduplicates_and_stops_repeats(self):
        browser = Mock()
        second = SEARCH + SEARCH.replace('0123', '0124')
        browser.open.side_effect = [io.BytesIO(p.encode()) for p in (SEARCH, second, second)]
        results = search(browser, 'שפה', Event(), 30, 5, Mock())
        self.assertEqual([b['id'] for b in results], ['0123', '0124'])
        self.assertEqual(browser.open.call_count, 3)
        self.assertIn('p=2', browser.open.call_args_list[1].args[0])

    def test_later_network_failure_preserves_results(self):
        browser = Mock()
        browser.open.side_effect = [io.BytesIO(SEARCH.encode()), OSError('offline')]
        self.assertEqual(len(search(browser, 'שפה', Event(), 30, 3, Mock())), 1)

    def test_cancelled_search_has_no_request(self):
        abort = Event()
        abort.set()
        browser = Mock()
        self.assertEqual(search(browser, 'שפה', abort, 30, 3, Mock()), [])
        browser.open.assert_not_called()


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.plugin = SfarimSteimatzkyPlugin(None)
        self.book = details_page(product(), '0123')
        self.log, self.abort = Mock(), Event()

    def test_metadata_and_cover_cache(self):
        queue = Queue()
        with patch('src.steimatzky_client.details', return_value=self.book):
            self.plugin.identify(self.log, queue, self.abort, identifiers={'steimatzky': '0123'})
        self.assertEqual(queue.qsize(), 1)
        mi = queue.get()
        self.assertEqual(mi.pubdate.year, 2021)
        self.assertEqual(mi.isbn, '9780306406157')
        self.assertEqual(mi.languages, ['heb'])
        self.assertEqual(mi.authors, self.book['authors'])
        self.assertEqual(mi.source_relevance, 0)
        self.assertIn('&lt;b&gt;', mi.comments)
        self.assertEqual(self.plugin.get_cached_cover_url(mi.identifiers), COVER)
        self.assertEqual(self.plugin.get_book_url(mi.identifiers)[2], BASE + '/0123')

    def test_failed_identifier_falls_back_to_search(self):
        queue = Queue()
        with patch('src.steimatzky_client.details', side_effect=[ValueError(), self.book]), patch('src.steimatzky_client.search', return_value=[self.book]):
            self.plugin.identify(self.log, queue, self.abort, title='שפה', identifiers={'steimatzky': '999'})
        self.assertEqual(queue.qsize(), 1)

    def test_cancellation_skips_lookup(self):
        self.abort.set()
        with patch('src.steimatzky_client.details') as fetch:
            self.plugin.identify(self.log, Queue(), self.abort, identifiers={'steimatzky': '0123'})
            fetch.assert_not_called()

    def test_cover_only_performs_identify_and_download(self):
        queue = Queue()
        with patch('src.steimatzky_client.details', return_value=self.book), patch('src.steimatzky_plugin.download_steimatzky_cover', return_value=b'valid image') as fetch:
            self.plugin.download_cover(self.log, queue, self.abort, identifiers={'steimatzky': '0123'})
        self.assertEqual(queue.get()[1], b'valid image')
        self.assertEqual(fetch.call_args.args[1], COVER)

    def test_invalid_cover_bytes_are_not_returned(self):
        browser = Mock()
        browser.open.return_value = io.BytesIO(b'<html>error</html>')
        with self.assertRaises(ValueError):
            download(browser, COVER, self.abort, 30, self.log)

    def test_cancellation_after_cover_fetch_returns_nothing(self):
        def fetch(*args):
            self.abort.set()
            return b'not needed'
        with patch('src.steimatzky_cover.read', side_effect=fetch):
            self.assertIsNone(download(Mock(), COVER, self.abort, 30, self.log))


if __name__ == '__main__':
    suite = unittest.TestSuite()
    for case in (HtmlTests, ClientTests, PluginTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if outcome.wasSuccessful() else 1)
