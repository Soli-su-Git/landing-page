# Landing page di Soli ☀️

La pagina pubblica della community **soli**: chi siamo, i venti gruppi
regionali con il link, i topic del forum e dove ci trovi fuori da Telegram.

👉 **<https://soli-su-git.github.io/landing-page/>**

Il bot che gestisce i gruppi sta in un altro repo,
[Soli-su-Git/solizia](https://github.com/Soli-su-Git/solizia).

## Come funziona

La pagina **non si scrive a mano**: si genera. A ogni push su `main` — e una
volta al giorno, perché gli iscritti cambiano anche quando nessuno tocca il
codice — GitHub Actions la ricostruisce e la pubblica. Nel repo non c'è nessuna
pagina: ci sono le sorgenti.

```
build_page.py        costruisce la pagina
page_template.html   testo, struttura e stile (la parte che si modifica a mano)
icons/               le icone dei social, un file SVG per rete
data/routing.json    i gruppi e i topic, copia di quelli del bot
CHANGELOG.md         la versione della pagina: il titolo più recente
```

Da dove vengono i dati:

| Cosa | Da dove |
|---|---|
| Gruppi regionali e topic | `data/routing.json`, ripreso dal repo del bot a ogni build |
| Titolo, foto e iscritti di ogni gruppo | Telegram, al momento del build |
| Testo della pagina | `page_template.html` |

Gli iscritti sono **arrotondati** (`~330`, `~160`, `8`): un numero al dettaglio
invecchia fra un build e l'altro. Dove un numero non si riesce a leggere la
scheda non dice niente, invece di dichiarare un gruppo vuoto che vuoto non è.

## Guardarla prima di pubblicarla

```bash
make setup          # virtualenv con pytest e ruff
echo "BOT_TOKEN=..." > .env    # opzionale: senza, niente numeri né foto
make open           # costruisce site/ e la apre nel browser
```

Altri comandi: `make page-offline` (senza chiamare Telegram), `make routing`
(riscarica gruppi e topic dal repo del bot), `make check` (lint + test),
`make bump MESSAGE="feat: ..."` prima di ogni commit.

## Aggiungere un gruppo o un topic

Non si fa qui: si aggiunge una riga a `REGION_TO_HANDLE` (o a `FORUM_TOPICS`)
nel repo del bot e si lancia `make routing` lì. Al resto pensa la CI. Una sola
fonte, così la pagina non manda mai la gente in un gruppo che il bot non usa più.

## Cosa serve su GitHub

Tre cose, una volta sola, nelle impostazioni del repo:

1. **Settings → Pages → Source: GitHub Actions** — senza, il workflow costruisce
   la pagina e non la pubblica.
2. **Settings → Secrets and variables → Actions**, due segreti:
   - `BOT_TOKEN` — il token del bot, per iscritti e foto;
   - `SOLIZIA_TOKEN` — un token con lettura sul repo del bot (che è privato),
     per riprendere gruppi e topic.
3. Questo repo dev'essere **pubblico**: GitHub Pages sui repo privati è a
   pagamento.

Se un segreto manca la pagina esce lo stesso, più povera: senza `BOT_TOKEN`
niente numeri né foto, senza `SOLIZIA_TOKEN` i gruppi sono quelli dell'ultima
copia committata.
