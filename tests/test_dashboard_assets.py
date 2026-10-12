"""Static checks on the dashboard: everything loads locally (vendored, verified), local Earth texture."""
import hashlib
import re

from pipeline.config import PROJECT_ROOT

DASHBOARD = PROJECT_ROOT / "dashboard"
VENDOR = DASHBOARD / "assets" / "vendor"
# Links the page shows to people (opened by a click, never loaded as code, styles or fonts).
LINK_HOSTS = {"api.nasa.gov", "ssd-api.jpl.nasa.gov", "visibleearth.nasa.gov", "www.w3.org"}


def page_sources():
    files = [DASHBOARD / "index.php", *sorted((DASHBOARD / "assets" / "js").glob("*.js")),
             *sorted((DASHBOARD / "assets" / "css").glob("*.css")), VENDOR / "fonts" / "fonts.css"]
    return {f: f.read_text() for f in files}


def test_nothing_is_loaded_from_external_hosts():
    for path, text in page_sources().items():
        code = re.sub(r"<!--.*?-->|/\*.*?\*/|^\s*//.*$", "", text, flags=re.S | re.M)   # ignore comments
        for url in re.findall(r"https?://[^\s\"'<>)]+", code):
            assert url.split("/")[2] in LINK_HOSTS, f"{path.name} loads an external URL: {url}"


def test_vendored_files_have_licences_and_match_recorded_hashes():
    readme = (VENDOR / "README.md").read_text()
    rows = re.findall(r"\| `[^`]+` \| `[^`]+` \| `([^`]+)` \| [\d,]+ \| `([0-9a-f]{16})…`", readme)
    assert len(rows) == 14
    for local, sha_prefix in rows:
        assert hashlib.sha256((VENDOR / local).read_bytes()).hexdigest().startswith(sha_prefix), local
    for licence in ["three/LICENSE", "chartjs/LICENSE.md", "fonts/inter/LICENSE", "fonts/space-grotesk/LICENSE"]:
        assert (VENDOR / licence).stat().st_size > 500, licence


def test_index_uses_the_vendored_copies():
    index = (DASHBOARD / "index.php").read_text()
    for path in ["assets/vendor/three/three.module.min.js", "assets/vendor/chartjs/chart.umd.js",
                 "assets/vendor/fonts/fonts.css"]:
        assert path in index
        assert (DASHBOARD / path).exists()
    for font in re.findall(r"url\(\./([^)]+)\)", (VENDOR / "fonts" / "fonts.css").read_text()):
        assert (VENDOR / "fonts" / font).exists(), font


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
