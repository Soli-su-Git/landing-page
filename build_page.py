#!/usr/bin/env python3
"""Genera la pagina pubblica della community: `docs/site/index.html`.

I dati non si scrivono a mano: i gruppi regionali e i topic vengono da
`src/solizia/routing.py`, titoli e numero di iscritti da Telegram. Quindi
aggiungere un gruppo alla pagina vuol dire aggiungere una riga a
`REGION_TO_HANDLE`, non toccare l'HTML.

    make page              # con i dati freschi da Telegram (serve BOT_TOKEN)
    make page-offline      # solo le tabelle del repo, senza numeri

Due file in uscita, e la differenza conta:

- `docs/site/index.html` — la pagina pubblica. Mostra una **fascia**
  ("attivo", "in crescita", ...), non il numero: "8 iscritti" accanto alla
  Valle d'Aosta scoraggia dall'entrare proprio nei gruppi che hanno più
  bisogno di gente.
- `docs/stats.json` — i numeri veri, per chi guida la community. Sta **fuori**
  da `docs/site/`, che è l'unica cartella pubblicata: se finisse lì dentro
  renderebbe pubblici i numeri che la pagina nasconde.

`getChat` e `getChatMemberCount` funzionano sui gruppi pubblici anche se il bot
non è dentro — ma non se è stato bannato: in quel caso il gruppo resta in
pagina senza numero, e `docs/stats.json` ne registra il motivo.

Le foto dei gruppi vengono scaricate in `docs/site/img/` e referenziate con un
percorso relativo. **Non si può linkare direttamente il file su Telegram**:
l'indirizzo di scarico contiene il token del bot, che in una pagina pubblica
sarebbe come pubblicare la password.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# `changelog_version` dice dove sta la versione della pagina (il titolo della
# sezione più recente del suo changelog): importarla evita di riscrivere qui
# quella regola e di farla divergere.
from bump_version import SITO_CHANGELOG, changelog_version
from solizia.routing import FORUM_TOPICS, REGION_TO_HANDLE, topic_display_name

API = "https://api.telegram.org"

#: Il guscio HTML della pagina, accanto a questo script.
TEMPLATE = "page_template.html"

#: Dove finiscono le foto dei gruppi, dentro la cartella pubblicata.
IMAGES_DIR = "img"

#: Quante volte riprovare una chiamata caduta per motivi di rete, e quanto
#: aspettare fra un tentativo e l'altro.
ATTEMPTS = 3
RETRY_WAIT_SEC = 1.0

#: Lato dell'avatar in pagina: la foto "small" di Telegram è 160px, quindi
#: resta nitida anche su uno schermo a tripla densità.
AVATAR_PX = 44

#: Lato della foto del gruppo principale, in cima alla pagina.
HERO_PX = 76

#: Gruppo principale: è un forum pubblico, quindi i topic hanno un link vero.
MAIN_GROUP = "solisutelegram"

#: Dove sta la community fuori da Telegram.
SOCIALS: list[tuple[str, str, str]] = [
    ("Telegram", "Soli ☀️ — il gruppo principale", f"https://t.me/{MAIN_GROUP}"),
    ("Instagram", "@solisuig", "https://instagram.com/solisuig"),
    ("TikTok", "@solisutiktok", "https://tiktok.com/@solisutiktok"),
]

#: Soglia minima di iscritti -> fascia mostrata in pagina, dalla più alta.
BANDS: list[tuple[int, str]] = [
    (150, "attivo"),
    (50, "in crescita"),
    (1, "piccolo"),
]
BAND_UNKNOWN = "in avvio"

TITLE = "Soli ☀️ — la community"
TAGLINE = "Venti gruppi regionali, un forum, e nessun algoritmo che decide chi incontri."


@dataclass
class Group:
    """Un gruppo regionale, con quello che si è riusciti a leggere da Telegram."""

    region: str
    handle: str
    title: str | None = None
    members: int | None = None
    error: str | None = None
    image: str | None = None  # percorso relativo alla pagina, es. "img/soliabruzzo.jpg"

    @property
    def url(self) -> str:
        return f"https://t.me/{self.handle.lstrip('@')}"

    @property
    def band(self) -> str:
        if self.members is None or self.members <= 0:
            return BAND_UNKNOWN
        for floor, label in BANDS:
            if self.members >= floor:
                return label
        return BAND_UNKNOWN

    @property
    def badge(self) -> str:
        """Quello che la scheda mostra: quanti sono, "in avvio", o niente.

        Tre casi diversi, e vale la pena non confonderli: un numero se c'è, "in
        avvio" se il gruppo è davvero vuoto, e **niente** se non si è riusciti a
        leggerlo — un gruppo illeggibile non è un gruppo vuoto, e scriverlo
        sarebbe dire una cosa che non si sa.

        `band` resta, ma solo per `stats.json` e per smorzare la scheda.
        """
        if self.members is None:
            return ""
        if self.members <= 0:
            return BAND_UNKNOWN
        return approx_members(self.members)

    @property
    def display_title(self) -> str:
        return self.title or f"Soli {self.region}"

    @property
    def initials(self) -> str:
        """Le iniziali, per il tondo al posto della foto quando non c'è.

        "Emilia-Romagna" -> "ER", "Valle d'Aosta" -> "VA" (le parole di una
        lettera sola non contano), "Abruzzo" -> "A".
        """
        words = [w for w in re.split(r"[^\w]+", self.region, flags=re.UNICODE) if len(w) > 1]
        return "".join(word[0] for word in words[:2]).upper()

    @property
    def slug(self) -> str:
        return self.handle.lstrip("@").lower()


@dataclass
class Snapshot:
    """Quello che si sa dei gruppi in un dato giorno."""

    groups: list[Group]
    main_members: int | None = None
    main_image: str | None = None
    generated_on: str = field(default_factory=lambda: date.today().isoformat())

    @property
    def total_members(self) -> int:
        return sum(g.members or 0 for g in self.groups)


def _fetch(url: str, timeout: int = 15, attempts: int = ATTEMPTS) -> bytes:
    """GET con qualche tentativo, perché un errore di rete qui mente in pagina.

    Un "connection reset" su `getChatMemberCount` è bastato a far uscire la
    Campania come gruppo senza iscritti: 76 persone diventate "in avvio" per un
    pacchetto perso. Gli errori HTTP invece non si ritentano, sono risposte.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError:
            raise
        except Exception as error:  # rete assente, DNS, timeout, reset
            last = error
            if attempt + 1 < attempts:
                time.sleep(RETRY_WAIT_SEC * (attempt + 1))
    raise last if last else RuntimeError("fetch fallito senza errore")


def _call(token: str, method: str, **params: str) -> dict:
    url = f"{API}/bot{token}/{method}?{urllib.parse.urlencode(params)}"
    try:
        return json.loads(_fetch(url))
    except urllib.error.HTTPError as error:
        try:
            return json.load(error)
        except ValueError:
            return {"ok": False, "description": f"HTTP {error.code}"}
    except Exception as error:  # rete assente, DNS, timeout
        return {"ok": False, "description": f"{type(error).__name__}: {error}"}


def _download_photo(token: str, file_id: str, destination: Path) -> bool:
    """Scarica una foto di gruppo in `destination`. → riuscito o no.

    Due passi: `getFile` dà il percorso, poi il file si prende da
    `/file/bot<token>/<percorso>`. Quell'URL **non** va in pagina: contiene il
    token.
    """
    info = _call(token, "getFile", file_id=file_id)
    if not info.get("ok"):
        return False
    path = info["result"].get("file_path")
    if not path:
        return False
    url = f"{API}/file/bot{token}/{path}"
    try:
        data = _fetch(url, timeout=30)
    except Exception:
        return False
    if not data:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return True


def fetch_snapshot(token: str, images_dir: Path | None = None) -> Snapshot:
    """Interroga Telegram gruppo per gruppo. Un errore non ferma gli altri."""
    groups = []
    for region, handle in REGION_TO_HANDLE.items():
        group = Group(region=region, handle=handle)
        chat = _call(token, "getChat", chat_id=handle)
        if chat.get("ok"):
            group.title = chat["result"].get("title")
            count = _call(token, "getChatMemberCount", chat_id=handle)
            if count.get("ok"):
                group.members = int(count["result"])
            else:
                group.error = str(count.get("description"))
            photo = chat["result"].get("photo") or {}
            file_id = photo.get("small_file_id")
            if images_dir is not None and file_id:
                name = f"{group.slug}.jpg"
                if _download_photo(token, file_id, images_dir / name):
                    group.image = f"{IMAGES_DIR}/{name}"
        else:
            group.error = str(chat.get("description"))
        groups.append(group)

    count = _call(token, "getChatMemberCount", chat_id=f"@{MAIN_GROUP}")
    main_chat = _call(token, "getChat", chat_id=f"@{MAIN_GROUP}")
    main_image = None
    file_id = ((main_chat.get("result") or {}).get("photo") or {}).get("small_file_id")
    if images_dir is not None and file_id:
        name = f"{MAIN_GROUP}.jpg"
        if _download_photo(token, file_id, images_dir / name):
            main_image = f"{IMAGES_DIR}/{name}"

    return Snapshot(
        groups=groups,
        main_members=int(count["result"]) if count.get("ok") else None,
        main_image=main_image,
    )


def offline_snapshot() -> Snapshot:
    """Le sole tabelle del repo: la pagina si costruisce anche senza token."""
    return Snapshot(groups=[Group(region=r, handle=h) for r, h in REGION_TO_HANDLE.items()])


def thousands(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def round_down(value: int, step: int = 100) -> int:
    """Arrotonda per difetto: "oltre 2.300" non invecchia come "2.371"."""
    return value // step * step


def approx_members(value: int) -> str:
    """Quanti sono, arrotondato per difetto a seconda dell'ordine di grandezza.

    Un numero esatto invecchia fra una rigenerazione e l'altra (il gruppo
    principale ha fatto +1 fra due `make page` di prova), quindi si arrotonda —
    ma solo dove c'è qualcosa da arrotondare: sotto i 20 iscritti un "~0" o un
    "~10" direbbe meno del numero vero.

        2372 -> "~2.300"    336 -> "~330"    46 -> "~40"    8 -> "8"
    """
    if value >= 1000:
        step = 100
    elif value >= 20:
        step = 10
    else:
        step = 1
    rounded = round_down(value, step)
    return thousands(rounded) if step == 1 else f"~{thousands(rounded)}"


MONTHS = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)


def italian_date(iso: str) -> str:
    """2026-10-01 -> "1 ottobre 2026". In `stats.json` la data resta ISO."""
    year, month, day = (int(part) for part in iso.split("-"))
    return f"{day} {MONTHS[month - 1]} {year}"


def pretty_topic(topic_id: int) -> str:
    """Il nome del topic come lo legge una persona.

    `topic_display_name` capitalizza la prima keyword e basta — "c2c" diventa
    "C2c", "dr. martens day" diventa "Dr. martens day". In una scheda agli admin
    va bene, su una pagina pubblica no.
    """
    return topic_display_name(topic_id).title()


def page_version(repo: Path | None = None) -> str:
    """La versione della pagina, dal suo changelog. Non è quella del bot."""
    root = repo or Path(__file__).resolve().parents[1]
    return changelog_version(root / SITO_CHANGELOG)


def active_topics() -> list[tuple[int, str]]:
    """I topic non commentati in `FORUM_TOPICS`, in ordine alfabetico."""
    topics = [(topic_id, pretty_topic(topic_id)) for topic_id in FORUM_TOPICS]
    return sorted(topics, key=lambda item: item[1].lower())


def _count(group: Group) -> str:
    """Il tondino con il numero, o nulla se quel numero non si sa."""
    if not group.badge:
        return ""
    return f'<span class="count" title="iscritti">{escape(group.badge)}</span>'


def _avatar(group: Group) -> str:
    """La foto del gruppo, o un tondo con le iniziali se non c'è.

    `alt` vuoto di proposito: il nome del gruppo sta nella riga accanto, e
    farlo rileggere da uno screen reader sarebbe solo un doppione.
    """
    if group.image:
        return (
            f'<img class="avatar" src="{escape(group.image)}" alt=""'
            f' width="{AVATAR_PX}" height="{AVATAR_PX}" loading="lazy">'
        )
    return f'<span class="avatar initials" aria-hidden="true">{escape(group.initials)}</span>'


def render(snapshot: Snapshot) -> str:
    """Riempie `page_template.html`: una pagina sola, senza dipendenze esterne.

    Il template sta in un file suo e non in una f-string perché nel CSS le
    graffe sono graffe: qui non vanno raddoppiate e si legge come HTML.
    """
    groups = sorted(snapshot.groups, key=lambda g: g.region)

    cards = "\n".join(
        f"""        <li class="group{' unknown' if g.band == BAND_UNKNOWN else ''}">
          <a href="{escape(g.url)}">
            {_avatar(g)}
            <span class="name">{escape(g.display_title)}</span>
            <span class="handle">{escape(g.handle)}</span>
            {_count(g)}
          </a>
        </li>"""
        for g in groups
    )

    topics = "\n".join(
        f'          <li><a href="https://t.me/{MAIN_GROUP}/{topic_id}">{escape(name)}</a></li>'
        for topic_id, name in active_topics()
    )

    socials = "\n".join(
        f'          <li><a href="{escape(url)}"><strong>{escape(network)}</strong>'
        f"<span>{escape(label)}</span></a></li>"
        for network, label, url in SOCIALS
    )

    if snapshot.main_members:
        size = (
            f"Siamo <strong>{approx_members(snapshot.main_members)} persone</strong> nel gruppo"
            f" principale, più <strong>{approx_members(snapshot.total_members)}</strong>"
            " nei venti gruppi regionali."
        )
    else:
        size = (
            "Il gruppo principale raccoglie tutta la community, "
            "i gruppi regionali la dividono per zona."
        )

    hero = ""
    if snapshot.main_image:
        hero = (
            f'<img class="hero-photo" src="{escape(snapshot.main_image)}"'
            f' alt="" width="{HERO_PX}" height="{HERO_PX}">'
        )

    template = Template((Path(__file__).parent / TEMPLATE).read_text(encoding="utf-8"))
    return template.substitute(
        hero=hero,
        title=escape(TITLE),
        tagline=escape(TAGLINE),
        main_url=f"https://t.me/{MAIN_GROUP}",
        size=size,
        cards=cards,
        topics=topics,
        socials=socials,
        generated=escape(italian_date(snapshot.generated_on)),
        version=escape(page_version()),
    )


def stats_json(snapshot: Snapshot) -> str:
    """I numeri veri, per chi guida la community. Non finisce fra i file pubblicati."""
    payload = {
        "aggiornato": snapshot.generated_on,
        "gruppo_principale": {"handle": f"@{MAIN_GROUP}", "iscritti": snapshot.main_members},
        "totale_gruppi_regionali": snapshot.total_members,
        "gruppi": [
            {
                "regione": g.region,
                "handle": g.handle,
                "titolo": g.title,
                "iscritti": g.members,
                "fascia": g.band,
                "errore": g.error,
            }
            for g in sorted(snapshot.groups, key=lambda g: -(g.members or 0))
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="non interrogare Telegram: pagina senza numeri né fasce reali",
    )
    parser.add_argument("--output", type=Path, default=Path("docs/site/index.html"))
    parser.add_argument("--stats", type=Path, default=Path("docs/stats.json"))
    args = parser.parse_args(argv)

    if args.offline:
        snapshot = offline_snapshot()
    else:
        token = os.environ.get("BOT_TOKEN", "").strip()
        if not token:
            try:
                from dotenv import load_dotenv
            except ImportError:
                load_dotenv = None
            if load_dotenv is not None:
                load_dotenv()
                token = os.environ.get("BOT_TOKEN", "").strip()
        if not token:
            print(
                "Manca BOT_TOKEN (in .env o nell'ambiente). "
                "Per la pagina senza numeri: make page-offline",
                file=sys.stderr,
            )
            return 1
        snapshot = fetch_snapshot(token, images_dir=args.output.parent / IMAGES_DIR)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(snapshot), encoding="utf-8")
    with_photo = sum(1 for group in snapshot.groups if group.image)
    print(f"{args.output}  ({len(snapshot.groups)} gruppi, {with_photo} con foto)")

    if not args.offline:
        args.stats.parent.mkdir(parents=True, exist_ok=True)
        args.stats.write_text(stats_json(snapshot), encoding="utf-8")
        unreadable = [g for g in snapshot.groups if g.members is None]
        print(f"{args.stats}  (totale regionali: {snapshot.total_members})")
        for group in unreadable:
            print(f"  ! {group.region} ({group.handle}): {group.error or 'nessun numero'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
