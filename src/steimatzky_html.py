"""Parse public Steimatzky search cards and book pages without executing scripts."""

import json
import re
from urllib.parse import urljoin, urlsplit

from lxml import html

BASE = 'https://www.steimatzky.co.il'


def by_class(root, name):
    """Match a whole HTML class, avoiding similarly named containers."""
    return root.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), $name)]', name=' ' + name + ' ')


def text(node):
    """Normalize visible text while preserving Hebrew and word boundaries."""
    return ' '.join(' '.join(node.itertext()).split())


def document(data):
    """The site's HTML is UTF-8, including pages without charset declarations."""
    return html.fromstring(data, parser=html.HTMLParser(encoding='utf-8'))


def book_id(url):
    """Accept only the catalog's numeric product URLs; preserve leading zeros."""
    parts = urlsplit(urljoin(BASE, url))
    if parts.scheme != 'https' or parts.netloc.lower() not in ('steimatzky.co.il', 'www.steimatzky.co.il'):
        return None
    path = parts.path.strip('/')
    return path if re.fullmatch(r'[0-9]+', path) else None


def image_url(value):
    """Accept public catalog images, excluding the site's placeholder graphics."""
    if not isinstance(value, str):
        return None
    url = urljoin(BASE, value)
    parts = urlsplit(url)
    if (parts.scheme == 'https' and parts.netloc.lower() in ('steimatzky.co.il', 'www.steimatzky.co.il')
            and parts.path.startswith('/pub/media/catalog/product/') and '/placeholder/' not in parts.path):
        return url
    return None


def names(value):
    """Read structured author lists without guessing splits inside Hebrew names."""
    if isinstance(value, list):
        return list(dict.fromkeys(name for item in value for name in names(item)))
    if isinstance(value, dict):
        return names(value.get('name', ''))
    return [' '.join(value.split())] if isinstance(value, str) and value.strip() else []


def search_page(data):
    """Read only book result cards and indicate whether another page exists."""
    root = document(data)
    result, seen = [], set()
    for card in by_class(root, 'product-item'):
        flags = by_class(card, 'product-is_book')
        if not flags or text(flags[0]) != '1':
            continue
        title_nodes = by_class(card, 'product-category-name')
        if not title_nodes:
            continue
        title_node = title_nodes[0]
        links = title_node.xpath('.//a/@href')
        ident = book_id(links[0]) if links else None
        if not ident or ident in seen or not text(title_node):
            continue
        seen.add(ident)
        author_nodes = by_class(card, 'author')
        result.append({'id': ident, 'title': text(title_node),
                       'authors': names(text(author_nodes[0])) if author_nodes else []})
    has_next = bool(root.xpath('//a[contains(concat(" ",normalize-space(@class)," ")," next ")]/@href'))
    return result, has_next


def structured_books(root):
    """Read Book JSON-LD, tolerating unrelated or malformed structured data."""
    def visit(value):
        if isinstance(value, list):
            for item in value:
                yield from visit(item)
        elif isinstance(value, dict):
            kinds = value.get('@type', [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if 'book' in [kind.lower() for kind in kinds if isinstance(kind, str)]:
                yield value
            yield from visit(value.get('@graph', []))
    for script in root.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            yield from visit(json.loads(script))
        except (ValueError, TypeError):
            continue


def cover_url(root, metadata):
    """Prefer the main gallery image's explicit full URL, never a back cover."""
    for encoded in root.xpath('//*[@data-gallery-role]/@data-mage-init'):
        try:
            gallery = json.loads(encoded).get('Idus_Product/js/gallery', {}).get('data', [])
            images = [item for item in gallery if isinstance(item, dict) and item.get('type', 'image') == 'image']
            if images:
                main = next((item for item in images if item.get('isMain')), images[0])
                for key in ('full', 'img'):
                    url = image_url(main.get(key))
                    if url:
                        return url
        except (ValueError, TypeError, AttributeError):
            continue
    # Older pages may only expose their catalog image, so retain that fallback.
    return image_url(metadata.get('image')) or next((url for url in
        (image_url(value) for value in root.xpath('//meta[@property="og:image"]/@content')) if url), None)


def details_page(data, expected_id):
    """Extract source-provided fields, leaving absent dates and ISBNs unset."""
    root = document(data)
    metadata = next((entry for entry in structured_books(root) if str(entry.get('sku', '')) == expected_id), None)
    if metadata is None:
        raise ValueError('The page does not identify the requested SKU as a book.')
    fields = {}
    for row in by_class(root, 'product-detail'):
        spans = row.xpath('./span')
        if len(spans) == 2 and 'description' not in row.get('class', '').split():
            fields[text(spans[0]).rstrip(':').strip()] = text(spans[1])
    headings = by_class(root, 'product-page-name')
    title = text(headings[0]) if headings else metadata.get('name', '')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Book title is missing.')
    descriptions = by_class(root, 'product-short-desc') + by_class(root, 'product-rest-desc')
    comments = ' '.join(text(node) for node in descriptions).strip()
    year_text = fields.get('שנת הוצאה', '') or fields.get('שנת פרסום', '') or metadata.get('datePublished', '')
    match = re.fullmatch(r'([12][0-9]{3})(?:-\d{2}(?:-\d{2})?)?', str(year_text).strip())
    publishers = names(fields.get('הוצאה לאור') or metadata.get('publisher'))
    return {'id': expected_id, 'title': title.strip(),
            'authors': names(fields.get('מחבר/ת') or metadata.get('author')),
            'publisher': ', '.join(publishers), 'comments': comments,
            'tags': list(dict.fromkeys(fields[key] for key in ('תחום', 'תת תחום') if fields.get(key))),
            'language': fields.get('שפה', ''),
            'year': int(match.group(1)) if match else None,
            'isbn': metadata.get('isbn') or fields.get('ISBN') or '',
            'cover': cover_url(root, metadata)}
