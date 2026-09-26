"""Did the browser actually get the picture?

A page whose every thumbnail is a broken image answers 200 to `curl`, and that
is not a hypothetical: the interface builds absolute picture addresses from the
service's address, and in the container stack the address it calls
(`http://api:8000`) is one only its own server can resolve. So the last step of
the stack's smoke is a real browser: open the interface on the published port,
go to the page that shows the corpus, and ask the browser what it has —
`naturalWidth`, which is zero for a picture it could not fetch.

    uv run --group ui --group screenshots python scripts/stack_browser_check.py \\
        http://127.0.0.1:8511

It needs the browser Playwright installs (`uv run --group screenshots playwright
install chromium`), the same one `scripts/screenshots.py` uses.
"""

import sys

from playwright.sync_api import sync_playwright

#: The interface renders a picture only once the browser has fetched it, and a
#: cold stack is answering its first requests, so these are generous.
PAGE_TIMEOUT_MS = 60_000
SETTLE_MS = 2_500


def check(ui: str) -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(ui, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
            page.get_by_role("link", name="Browse").click()
            page.wait_for_selector("img", timeout=PAGE_TIMEOUT_MS)
            page.wait_for_timeout(SETTLE_MS)

            pictures = page.evaluate(
                """() => Array.from(document.images)
                       .filter(image => image.src.includes('/api/v1/assets/'))
                       .map(image => ({src: image.src, width: image.naturalWidth}))"""
            )
        finally:
            browser.close()

    if not pictures:
        print("browser-check: the corpus page showed no picture at all", file=sys.stderr)
        return 1

    broken = [one for one in pictures if one["width"] == 0]
    for one in pictures:
        print(f"browser-check: {one['width']:>5}px  {one['src']}")
    if broken:
        print(
            f"browser-check: {len(broken)} of {len(pictures)} pictures did not load — "
            "the browser was given an address it cannot reach",
            file=sys.stderr,
        )
        return 1
    print(f"browser-check: {len(pictures)} picture(s) fetched by the browser itself")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <interface url>", file=sys.stderr)
        return 2
    return check(argv[1].rstrip("/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
