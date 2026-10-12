"""Static checks on the dashboard: libraries only from allowed CDNs (pinned), local Earth texture."""
import re

from pipeline.config import PROJECT_ROOT

DASHBOARD = PROJECT_ROOT / "dashboard"
ALLOWED_LIBRARY_HOSTS = {"cdn.jsdelivr.net", "cdnjs.cloudflare.com"}
# Links the page shows to people (not loaded as code or styles).
LINK_HOSTS = {"api.nasa.gov", "ssd-api.jpl.nasa.gov", "visibleearth.nasa.gov", "www.w3.org"}


def page_sources():
    files = [DASHBOARD / "index.php", *sorted((DASHBOARD / "assets" / "js").glob("*.js")),
             *sorted((DASHBOARD / "assets" / "css").glob("*.css"))]
    return {f: f.read_text() for f in files}


def test_libraries_only_from_allowed_cdns_with_exact_versions():
    for path, text in page_sources().items():
        for url in re.findall(r"https?://[^\s\"'<>)]+", text):
            host = url.split("/")[2]
            if host in LINK_HOSTS:
                continue
            assert host in ALLOWED_LIBRARY_HOSTS, f"{path.name}: {url}"
            if url.rstrip("/").count("/") == 2:
                continue   # bare host, e.g. <link rel="preconnect">: loads nothing
            assert re.search(r"@\d+\.\d+\.\d+/", url), f"{path.name}: version not pinned in {url}"


def test_earth_texture_is_local_and_small():
    texture = DASHBOARD / "assets" / "img" / "earth_bluemarble_2048.jpg"
    assert texture.exists()
    assert texture.read_bytes()[:3] == b"\xff\xd8\xff"          # JPEG
    assert texture.stat().st_size < 1_000_000
    assert "assets/img/earth_bluemarble_2048.jpg" in (DASHBOARD / "assets" / "js" / "space.js").read_text()


def test_database_text_is_never_inserted_as_html():
    # innerHTML is only allowed in format.js's icon() helper, which uses a fixed set of SVG paths.
    for path, text in page_sources().items():
        if path.suffix != ".js":
            continue
        uses = [line for line in text.splitlines() if ".innerHTML" in line]
        if path.name == "format.js":
            assert len(uses) == 1 and "ICONS[name]" in uses[0]
        else:
            assert not uses, f"{path.name} uses innerHTML"
