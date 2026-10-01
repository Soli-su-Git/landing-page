# Changelog della pagina pubblica

La versione di [`site/index.html`](site/index.html), che **non** è quella del
bot: la pagina e il bot cambiano per motivi diversi, quindi hanno due numeri
separati (il bot sta in `pyproject.toml` + [`../CHANGELOG.md`](../CHANGELOG.md)).
Il titolo della sezione più recente, qui sotto, *è* la versione della pagina:
la legge `build_page.py` per scriverla nel footer.

Una riga per commit, dalla versione più recente. La aggiorna
`make bump-sito MESSAGE="feat(sito): ..."`, che guarda solo gli oggetti con
l'ambito `(sito)`.

## 1.0.1 — 2026-10-01

- fix(sito): le schede dei gruppi sono tutte alte uguali

## 1.0.0 — 2026-10-01

- feat(sito): la pagina dice la sua versione
- docs(sito): README e CLAUDE.md dicono che la pagina mostra i numeri
- refactor(sito): la classe CSS del numero si chiama count, non band
- feat(sito): la pagina mostra quanti iscritti ha ogni gruppo
- feat(sito): approssimazione degli iscritti per ordine di grandezza
- feat(sito): pagina pubblica dei gruppi e dei social, generata dai dati del bot
