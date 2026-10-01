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

from solizia.routing import FORUM_TOPICS, REGION_TO_HANDLE, topic_display_name

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_page.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_page", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_page"] = module
    spec.loader.exec_module(module)
    return module


build_page = _load_module()


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
    for topic_id in FORUM_TOPICS:
        assert f"https://t.me/{build_page.MAIN_GROUP}/{topic_id}" in html
        assert build_page.pretty_topic(topic_id) in html


def test_topic_names_are_readable():
    """ "C2c" e "Dr. martens day" vanno bene in una scheda admin, non in pagina."""
    assert build_page.pretty_topic(39829) == "C2C"
    assert build_page.pretty_topic(43552) == "Dr. Martens Day"
    assert build_page.pretty_topic(75056) == "I Cani"
    # il nome che usa il bot non cambia
    assert topic_display_name(39829) == "C2c"


def test_socials_are_linked(snapshot):
    html = build_page.render(snapshot)
    for _network, _label, url in build_page.SOCIALS:
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


def test_bands_replace_the_raw_numbers(snapshot):
    """La decisione che regge la pagina: fasce fuori, numeri dentro stats.json."""
    body = _body(build_page.render(snapshot))
    block = _groups_block(body)

    assert block.strip()
    assert not any(char.isdigit() for char in block), "un numero di iscritti è finito in pagina"
    for band in ("attivo", "in crescita", "piccolo", build_page.BAND_UNKNOWN):
        assert band in block
    # il conteggio esatto del gruppo principale non si pubblica: solo arrotondato
    assert "2371" not in body
    assert "2.371" not in body


def test_main_group_size_is_rounded_down(snapshot):
    assert "oltre 2.300 persone" in build_page.render(snapshot)


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
