"""La pagina pubblica: che contenga tutti i gruppi e non i numeri veri.

Nessuna chiamata di rete: si costruisce uno `Snapshot` a mano e si guarda
l'HTML che ne esce.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "build_page.py"


class _FakeResponse:
    """Il minimo che serve a `with urllib.request.urlopen(...) as r: r.read()`."""

    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _load_module():
    spec = importlib.util.spec_from_file_location("build_page", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_page"] = module
    spec.loader.exec_module(module)
    return module


build_page = _load_module()

# le tabelle arrivano dal repo del bot, non più da un import
REGION_TO_HANDLE = build_page.regions()
TOPICS = {topic["id"]: topic["nome"] for topic in build_page.routing()["topic"]}


@pytest.fixture
def snapshot():
    """Un gruppo per fascia, più uno illeggibile, più il resto a zero."""
    members = {
        "Lombardia": 336,
        "Toscana": 85,
        "Valle d'Aosta": 8,
        "Basilicata": 0,
    }
    groups = []
    for region, handle in REGION_TO_HANDLE.items():
        group = build_page.Group(region=region, handle=handle, title=f"Soli {region}")
        if region == "Piemonte":
            group.error = "Forbidden: bot was kicked from the supergroup chat"
        else:
            group.members = members.get(region, 42)
        groups.append(group)
    return build_page.Snapshot(groups=groups, main_members=2371, generated_on="2026-10-01")


def test_every_region_is_on_the_page(snapshot):
    html = build_page.render(snapshot)
    for region, handle in REGION_TO_HANDLE.items():
        assert f"https://t.me/{handle.lstrip('@')}" in html, region
        assert handle in html, region


def test_every_active_topic_is_linked(snapshot):
    html = build_page.render(snapshot)
    for topic_id, name in TOPICS.items():
        assert f"https://t.me/{build_page.MAIN_GROUP}/{topic_id}" in html
        assert build_page.pretty_topic(name) in html


def test_topic_names_are_readable():
    """ "C2c" e "Dr. martens day" vanno bene in una scheda admin, non in pagina."""
    assert build_page.pretty_topic("C2c") == "C2C"
    assert build_page.pretty_topic("Dr. martens day") == "Dr. Martens Day"
    assert build_page.pretty_topic("I cani") == "I Cani"


def test_socials_are_linked(snapshot):
    html = build_page.render(snapshot)
    for _network, _label, url, _glyph in build_page.SOCIALS:
        assert url in html
    assert "instagram.com/solisuig" in html
    assert "tiktok.com/@solisutiktok" in html
    assert "t.me/solisutelegram" in html


def _body(html: str) -> str:
    """La pagina senza il foglio di stile: nel CSS "0.85rem" non è un iscritto."""
    before, _, rest = html.partition("<style>")
    _, _, after = rest.partition("</style>")
    return before + after


def _groups_block(page: str) -> str:
    """Le sole schede dei gruppi, con le entity sciolte (`&#x27;` ha una cifra dentro)."""
    _, _, rest = page.partition('<ul class="groups">')
    block, _, _ = rest.partition("</ul>")
    return unescape(block)


def test_cards_show_how_many_members(snapshot):
    """Ogni scheda dice quanti sono, arrotondato — e il gruppo senza numero lo dice."""
    block = _groups_block(_body(build_page.render(snapshot)))

    assert "~330" in block  # Lombardia, 336
    assert "~80" in block  # Toscana, 85
    assert "8" in block  # Valle d'Aosta, esatto perché sotto i 20
    assert build_page.BAND_UNKNOWN in block  # Basilicata (0) e Piemonte (illeggibile)
    for band in ("attivo", "in crescita", "piccolo"):
        assert band not in block, f"la fascia {band} è rimasta in pagina"


def test_exact_counts_are_not_published(snapshot):
    """Un numero al dettaglio invecchia fra due `make page`: in pagina va arrotondato."""
    body = _body(build_page.render(snapshot))
    for exact in ("336", "2371", "2.371", "85"):
        assert exact not in _groups_block(body), exact
    assert "2371" not in body
    assert "2.371" not in body


def test_main_group_size_is_rounded_down(snapshot):
    html = build_page.render(snapshot)
    assert "~2.300 persone" in html
    # 336 + 85 + 8 + 0 + 15 gruppi a 42 = 1059 -> arrotondato alle centinaia
    assert "~1.000" in html


def test_band_thresholds():
    def band(members):
        return build_page.Group(region="X", handle="@x", members=members).band

    assert band(336) == "attivo"
    assert band(150) == "attivo"
    assert band(149) == "in crescita"
    assert band(50) == "in crescita"
    assert band(49) == "piccolo"
    assert band(1) == "piccolo"
    assert band(0) == build_page.BAND_UNKNOWN
    assert band(None) == build_page.BAND_UNKNOWN


def test_unreadable_group_stays_on_the_page(snapshot):
    """Piemonte ha bannato il bot: resta in pagina, senza fascia inventata."""
    html = build_page.render(snapshot)
    assert "https://t.me/solipiemonte" in html
    assert 'class="group unknown"' in html


def test_stats_json_keeps_the_numbers_and_the_errors(snapshot):
    payload = json.loads(build_page.stats_json(snapshot))
    assert payload["gruppo_principale"]["iscritti"] == 2371
    assert payload["gruppi"][0]["regione"] == "Lombardia"
    assert payload["gruppi"][0]["iscritti"] == 336
    piemonte = next(g for g in payload["gruppi"] if g["regione"] == "Piemonte")
    assert piemonte["iscritti"] is None
    assert "kicked" in piemonte["errore"]


def test_offline_snapshot_has_every_group_and_no_numbers():
    snapshot = build_page.offline_snapshot()
    assert len(snapshot.groups) == len(REGION_TO_HANDLE)
    assert all(group.members is None for group in snapshot.groups)
    assert build_page.render(snapshot).count("</li>") >= len(REGION_TO_HANDLE)


def test_rounding():
    assert build_page.round_down(2371) == 2300
    assert build_page.round_down(1406) == 1400
    assert build_page.round_down(42) == 0
    assert build_page.thousands(2300) == "2.300"


def test_approx_members_rounds_by_order_of_magnitude():
    """Grandi arrotondati, piccoli esatti: "~0" direbbe meno di "8"."""
    assert build_page.approx_members(2372) == "~2.300"
    assert build_page.approx_members(1581) == "~1.500"
    assert build_page.approx_members(336) == "~330"
    assert build_page.approx_members(174) == "~170"
    assert build_page.approx_members(46) == "~40"
    assert build_page.approx_members(20) == "~20"
    assert build_page.approx_members(19) == "19"
    assert build_page.approx_members(8) == "8"
    assert build_page.approx_members(1) == "1"


def test_page_version_comes_from_the_changelog(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog della pagina\n\n## 2.1.0 — 2026-11-01\n\n- feat: x\n")
    assert build_page.page_version(changelog) == "2.1.0"


def test_page_version_without_a_changelog(tmp_path):
    assert build_page.page_version(tmp_path / "manca.md") == "0.0.0"


def test_footer_carries_the_page_version(snapshot):
    html = build_page.render(snapshot)
    assert f"v{build_page.page_version()}," in html


# -- le foto dei gruppi ---------------------------------------------------------


def test_cards_show_the_group_photo(snapshot):
    for group in snapshot.groups:
        group.image = f"img/{group.slug}.jpg"
    block = _groups_block(_body(build_page.render(snapshot)))
    assert '<img class="avatar" src="img/soliabruzzo.jpg" alt=""' in block
    assert 'loading="lazy"' in block
    assert block.count("<img") == len(snapshot.groups)


def test_a_group_without_a_photo_gets_its_initials(snapshot):
    block = _groups_block(_body(build_page.render(snapshot)))  # nessuna image impostata
    assert "<img" not in block
    assert '<span class="avatar initials" aria-hidden="true">ER</span>' in block


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        ("Emilia-Romagna", "ER"),
        ("Valle d'Aosta", "VA"),
        ("Friuli Venezia Giulia", "FV"),
        ("Trentino-Alto Adige", "TA"),
        ("Abruzzo", "A"),
    ],
)
def test_initials(region, expected):
    assert build_page.Group(region=region, handle="@x").initials == expected


def test_the_page_never_carries_the_bot_token(snapshot):
    """L'URL di scarico di Telegram contiene il token: in pagina non ci va."""
    for group in snapshot.groups:
        group.image = f"img/{group.slug}.jpg"
    html = build_page.render(snapshot)
    assert "/file/bot" not in html
    assert "api.telegram.org" not in html


# -- errori di rete -------------------------------------------------------------


def test_fetch_retries_network_errors(monkeypatch):
    """Un reset non deve diventare un gruppo senza iscritti."""
    calls = []

    def flaky(url, timeout=0):
        calls.append(url)
        if len(calls) < 3:
            raise OSError("connection reset by peer")
        return _FakeResponse(b"ok")

    monkeypatch.setattr(build_page.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(build_page.time, "sleep", lambda _s: None)
    assert build_page._fetch("https://example.invalid/x") == b"ok"
    assert len(calls) == 3


def test_fetch_gives_up_after_the_attempts(monkeypatch):
    monkeypatch.setattr(
        build_page.urllib.request,
        "urlopen",
        lambda url, timeout=0: (_ for _ in ()).throw(OSError("giù")),
    )
    monkeypatch.setattr(build_page.time, "sleep", lambda _s: None)
    with pytest.raises(OSError):
        build_page._fetch("https://example.invalid/x")


def test_http_errors_are_not_retried(monkeypatch):
    """Un 403 è una risposta, non un incidente: ritentarlo non cambia niente."""
    calls = []

    def forbidden(url, timeout=0):
        calls.append(url)
        raise build_page.urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(build_page.urllib.request, "urlopen", forbidden)
    with pytest.raises(build_page.urllib.error.HTTPError):
        build_page._fetch("https://example.invalid/x")
    assert len(calls) == 1


def test_an_unreadable_group_claims_nothing(snapshot):
    """Illeggibile non è vuoto: la scheda del Piemonte non porta nessun tondino."""
    block = _groups_block(_body(build_page.render(snapshot)))
    piemonte = block[block.index("solipiemonte") : block.index("solipuglia")]
    assert 'class="count"' not in piemonte
    assert build_page.BAND_UNKNOWN not in piemonte
    # il gruppo davvero vuoto invece lo dice
    basilicata = block[block.index("solibasilicata") : block.index("solicalabria")]
    assert build_page.BAND_UNKNOWN in basilicata


def test_badge_tells_the_three_cases_apart():
    def badge(members, error=None):
        return build_page.Group(region="X", handle="@x", members=members, error=error).badge

    assert badge(336) == "~330"
    assert badge(8) == "8"
    assert badge(0) == build_page.BAND_UNKNOWN
    assert badge(None, error="Forbidden: bot was kicked") == ""


def test_the_main_group_photo_is_at_the_top(snapshot):
    snapshot.main_image = "img/solisutelegram.jpg"
    html = build_page.render(snapshot)
    assert '<img class="hero-photo" src="img/solisutelegram.jpg"' in html


def test_without_the_main_photo_the_header_still_stands(snapshot):
    assert snapshot.main_image is None
    body = _body(build_page.render(snapshot))
    assert "hero-photo" not in body
    assert "<h1>Soli" in body


def test_every_social_carries_its_icon(snapshot):
    body = _body(build_page.render(snapshot))
    block = body[body.index('<ul class="socials">') :]
    assert block.count('<svg class="icon"') == len(build_page.SOCIALS)
    # disegnate con currentColor: seguono il tema invece di avere due versioni
    assert "currentColor" in block
    assert "<img" not in block[: block.index("</ul>")]


@pytest.mark.parametrize("name", ["telegram", "instagram", "tiktok"])
def test_the_icon_files_are_there(name):
    assert build_page.icon(name).startswith('<svg class="icon"')


def test_a_missing_icon_does_not_break_the_page():
    assert build_page.icon("mastodon") == ""


# -- le tabelle che arrivano dal repo del bot -----------------------------------


def test_routing_json_has_every_region_and_topic():
    data = build_page.routing()
    assert len(data["regioni"]) == 20
    assert data["topic"], "nessun topic: il file è vuoto o di un'altra forma"
    assert all(topic["id"] and topic["nome"] for topic in data["topic"])


def test_a_missing_routing_file_says_what_to_do(tmp_path):
    with pytest.raises(SystemExit) as caduta:
        build_page.routing(tmp_path / "manca.json")
    assert "make routing" in str(caduta.value)
