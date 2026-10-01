# Changelog della pagina

La versione di questa pagina, che **non** è quella del bot: stanno in due repo
e cambiano per motivi diversi. Il titolo della sezione più recente, qui sotto,
*è* la versione: la legge `build_page.py` per scriverla nel footer.

Una riga per commit, dalla versione più recente. La aggiorna
`make bump MESSAGE="feat: ..."`.

Le voci fino alla 1.3.2 portano l'ambito `(sito)`: allora la pagina stava
insieme al bot, nello stesso repo, e quell'ambito serviva a tenere separate le
due versioni.

## 2.0.0 — 2026-10-01

- feat!: la pagina vive in un repo suo

## 1.3.2 — 2026-10-01

- chore(sito): la pagina generata non sta più nel repo

## 1.3.1 — 2026-10-01

- ci(sito): la pagina si pubblica da sola su GitHub Pages

## 1.3.0 — 2026-10-01

- feat(sito): le icone dei social accanto ai link

## 1.2.0 — 2026-10-01

- feat(sito): la foto del gruppo principale in cima alla pagina

## 1.1.2 — 2026-10-01

- fix(sito): un gruppo illeggibile non si dichiara vuoto

## 1.1.1 — 2026-10-01

- fix(sito): una chiamata caduta non svuota un gruppo

## 1.1.0 — 2026-10-01

- feat(sito): ogni scheda ha la foto del gruppo

## 1.0.1 — 2026-10-01

- fix(sito): le schede dei gruppi sono tutte alte uguali

## 1.0.0 — 2026-10-01

- feat(sito): la pagina dice la sua versione
- docs(sito): README e CLAUDE.md dicono che la pagina mostra i numeri
- refactor(sito): la classe CSS del numero si chiama count, non band
- feat(sito): la pagina mostra quanti iscritti ha ogni gruppo
- feat(sito): approssimazione degli iscritti per ordine di grandezza
- feat(sito): pagina pubblica dei gruppi e dei social, generata dai dati del bot
