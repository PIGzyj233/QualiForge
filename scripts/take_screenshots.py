from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:5173/")
    page.wait_for_timeout(1500)
    page.click("button[type=submit]")
    page.wait_for_timeout(2500)

    ws_id = page.url.split("/w/")[1].split("/")[0]
    print("workspace:", ws_id)

    screens = [
        ("/w/" + ws_id, "docs/screenshots/screenshot-overview.png"),
        ("/w/" + ws_id + "/admin", "docs/screenshots/screenshot-admin.png"),
        ("/w/" + ws_id + "/settings", "docs/screenshots/screenshot-ai-settings.png"),
    ]

    for path, out in screens:
        page.goto("http://localhost:5173" + path)
        page.wait_for_timeout(1500)
        page.screenshot(path=out)
        print("done:", out)

    # Find project links
    page.goto("http://localhost:5173/w/" + ws_id)
    page.wait_for_timeout(1500)
    links = page.query_selector_all("a")
    project_hrefs = []
    for l in links:
        href = l.get_attribute("href") or ""
        if "/p/" in href:
            project_hrefs.append(href)
            print("project link:", href)

    if project_hrefs:
        # Get project id
        proj_href = project_hrefs[0]
        proj_id = proj_href.split("/p/")[1].split("/")[0]
        base = f"/w/{ws_id}/p/{proj_id}"
        project_screens = [
            (base + "/overview", "docs/screenshots/screenshot-project-overview.png"),
            (base + "/library", "docs/screenshots/screenshot-library.png"),
            (base + "/diff", "docs/screenshots/screenshot-diff.png"),
            (base + "/plans", "docs/screenshots/screenshot-plans.png"),
        ]
        for path, out in project_screens:
            page.goto("http://localhost:5173" + path)
            page.wait_for_timeout(1500)
            page.screenshot(path=out)
            print("done:", out)

    browser.close()
    print("all done")
