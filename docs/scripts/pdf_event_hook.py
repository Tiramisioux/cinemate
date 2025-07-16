# pdf_event_hook.py  – inject a “Download PDF” button into Material’s header
from bs4 import BeautifulSoup
from mkdocs.structure.pages import Page

def inject_link(html: str, href: str, page: Page, logger):
    soup = BeautifulSoup(html, "html.parser")

    # Material ≥9: header is <div class="md-header__inner">
    header = soup.select_one(".md-header__inner")
    if not header:
        # Material ≤8 fallback
        header = soup.select_one(".md-header-nav")
    if not header:
        return html

    a = soup.new_tag(
        "a",
        href=href,
        title="Download full PDF",
        **{"class": "md-header__button md-icon"}
    )
    a.append(BeautifulSoup(
        '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">'
        '<path d="M5 20h14v-2H5m14-8h-4V3h-4v7H9l5 5 5-5z"/></svg>', "html.parser")
    )
    header.append(a)
    logger.info("Injected PDF button on %s", page.url)
    return str(soup)
