"""Clicks through the product page and the console in a real (headless) browser, like a visitor and a supervisor.

Run it against a copy with test data before a release or a demo, never against the live console (it changes
incident statuses):

    pip install playwright && playwright install chromium
    E2E_URL=http://localhost:3005 E2E_EMAIL=... E2E_PASSWORD=... python e2e/check_site.py

E2E_URL is a console (the Vite dev server or the Docker frontend). Exit code 0 = every check passed.
"""
import asyncio
import os
import re
import sys

from playwright.async_api import Page, async_playwright

URL = os.getenv("E2E_URL", "http://localhost:3005").rstrip("/")
EMAIL = os.getenv("E2E_EMAIL", "")
PASSWORD = os.getenv("E2E_PASSWORD", "")
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{f'  ({detail})' if detail and not ok else ''}", flush=True)


async def no_overflow(page: Page) -> int:
    return await page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


async def product_page(page: Page):
    await page.goto(URL + "/")
    check("product page: headline shown", await page.locator("h1").first.is_visible())
    # the logo goes back to the start
    await page.mouse.wheel(0, 4000)
    await page.wait_for_timeout(800)
    await page.locator("header a[href='/']").first.click()
    await page.wait_for_timeout(1200)
    check("product page: logo scrolls to the top", await page.evaluate("window.scrollY") < 5)
    # "Try it yourself": boxes appear after the scan, and the incident card after that
    await page.locator("#try").scroll_into_view_if_needed()
    await page.get_by_role("tab").nth(1).click()
    await page.wait_for_timeout(2200)
    boxes = await page.locator("#try .try-box").count()
    check("try it: the model's boxes appear", boxes > 0, f"{boxes} boxes")
    check("try it: the alert email is shown", await page.locator("#try").get_by_text("What to do now").is_visible())


async def console(page: Page):
    await page.goto(URL + "/login")
    await page.get_by_label("Email").fill(EMAIL)
    await page.get_by_label("Password", exact=True).fill(PASSWORD)
    await page.get_by_role("button", name="Sign in").click()
    await page.wait_for_url("**/app", timeout=10_000)
    check("sign in: lands on the console home", page.url.endswith("/app"))
    await page.wait_for_timeout(2500)
    headline = page.get_by_text(re.compile(r"(incidents? (is|are) waiting|All clear)")).first
    check("home: one plain sentence at the top", await headline.is_visible())

    got_it = page.get_by_role("button", name="Got it")
    if await got_it.count():
        await got_it.first.click()
        check("home: welcome note closes", await page.get_by_text("Welcome to SiteSentry").count() == 0)

    on_it = page.get_by_role("button", name="I'm on it")
    if await on_it.count():
        # the card moves out of the first four once someone is on it, so check the count of "on it" incidents
        async def on_it_total() -> int:
            res = await page.request.get(URL + "/api/incidents?status=acknowledged&limit=1")
            return int(res.headers.get("x-total-count", "0"))
        before = await on_it_total()
        await on_it.first.click()
        await page.wait_for_timeout(1500)
        check("home: 'I'm on it' works", await on_it_total() > before)
    else:
        check("home: 'I'm on it' works", True, "skipped: nothing open")

    await page.goto(URL + "/app/incidents")
    await page.wait_for_timeout(2000)
    rows = page.locator("main ul li a")
    check("incidents: list shows incidents", await rows.count() > 0)
    if await rows.count():
        await rows.first.click()
        await page.wait_for_timeout(2000)
        check("incident page: starts with what to do", await page.get_by_text("What to do now").is_visible())
        # keyboard: A = I'm on it (only when the incident is still open)
        if await page.get_by_role("button", name="I'm on it").count():
            await page.keyboard.press("a")
            await page.wait_for_timeout(1500)
            check("incident page: key A marks it 'on it'", await page.get_by_text("is on it").count() > 0)

    await page.goto(URL + "/app/cameras")
    await page.wait_for_timeout(2500)
    check("cameras: danger map or its empty note", await page.get_by_text("Where incidents happen").is_visible())
    edit = page.get_by_role("button", name="Edit zones")
    if await edit.count():
        await edit.click()
        await page.wait_for_timeout(1500)
        check("cameras: zone editor opens with the zones", await page.get_by_text("Zones on this camera").is_visible()
              and await page.locator("svg polygon").count() > 0)
    await page.goto(URL + "/app/analytics")
    await page.wait_for_timeout(2000)
    check("analytics: plain summary first", await page.get_by_text("In short").is_visible())
    await page.goto(URL + "/app/no-such-page")
    await page.wait_for_timeout(1000)
    check("console 404: friendly page", await page.get_by_text("This page isn't here").is_visible())

    for path in ("/app/cameras", "/app/analytics", "/app/notifications", "/app/rules"):
        await page.goto(URL + path)
        await page.wait_for_timeout(1500)
        check(f"page opens: {path}", await page.locator("h1").first.is_visible())


async def arabic(page: Page):
    await page.goto(URL + "/app")
    await page.evaluate("localStorage.setItem('sitesentry.lang', 'ar')")
    await page.reload()
    await page.wait_for_timeout(2000)
    check("arabic: page is right-to-left", await page.evaluate("document.documentElement.dir") == "rtl")
    await page.evaluate("localStorage.setItem('sitesentry.lang', 'en')")


async def phone(page: Page):
    for path in ("/", "/app", "/app/incidents", "/app/cameras", "/app/analytics", "/app/rules"):
        await page.goto(URL + path)
        await page.wait_for_timeout(1500)
        extra = await no_overflow(page)
        check(f"phone: {path} fits the screen", extra <= 1, f"{extra}px too wide")


async def main():
    if not (EMAIL and PASSWORD):
        sys.exit("Set E2E_EMAIL and E2E_PASSWORD (an account on the test copy).")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        desktop = await (await browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")).new_page()
        await product_page(desktop)
        await console(desktop)
        await arabic(desktop)
        # the phone shares the desktop's session cookie
        cookies = await desktop.context.cookies()
        mobile_ctx = await browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        await mobile_ctx.add_cookies(cookies)
        await phone(await mobile_ctx.new_page())
        await browser.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
