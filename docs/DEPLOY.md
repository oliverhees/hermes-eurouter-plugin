# Deployment & Betrieb

## Standard-Installation (Hermes Desktop oder CLI, lokal)

**Der einfachste Weg:** Sag es deinem Hermes im Chat — er installiert selbst
(fertiger Copy-Paste-Prompt im [README](../README.md#setup), Abschnitt Setup).

Oder selbst im Terminal, ein Befehl, kein git nötig:

```bash
curl -sL https://raw.githubusercontent.com/oliverhees/hermes-eurouter-plugin/main/install.sh | bash
```

Oder klassisch per Clone (praktisch für Updates via `git pull`):

```bash
git clone https://github.com/oliverhees/hermes-eurouter-plugin.git
cd hermes-eurouter-plugin
./install.sh
```

Hinweis für Fortgeschrittene: `hermes plugins install` (der offizielle
Plugin-Befehl) legt Model-Provider-Plugins aktuell an einen Ort, den Hermes'
Provider-Discovery nicht scannt — deshalb dieser Installer. Sobald Upstream
das unterstützt, stellen wir um.

Danach `EUROUTER_API_KEY=eur_...` in `~/.hermes/.env` eintragen und Hermes
komplett neu starten. Der Provider "EU Router" erscheint im Modell-Picker,
darunter deine Routing Rules beim Namen.

Voraussetzung: mindestens eine aktivierte Routing Rule in deinem
EU-Router-Account ([https://eurouter.ai](https://www.eurouter.ai?ref=06ZUHPBK) → Routing Rules). Ohne Regeln
zeigt der Picker ersatzweise den generischen Modellkatalog.

## Updates

```bash
cd hermes-eurouter-plugin
git pull
./install.sh
```

Hermes danach neu starten. `install.sh` leert automatisch den
Modell-Listen-Cache (der sonst bis zu 1 Stunde den alten Stand serviert).

## Optional: Self-Heal-Shim

```bash
./install.sh --with-shim
```

Installiert einen Wrapper unter `~/.local/bin/hermes`, der bei jedem
`hermes`-Aufruf im Terminal:

1. die Plugin-Dateien gegen dein Repo-Clone abgleicht und bei Bedarf
   wiederherstellt, und
2. nach jedem erkannten Hermes-Update einen Endzustand-Probelauf macht —
   bricht das Plugin durch eine Hermes-interne Änderung, bekommst du sofort
   eine Warnung samt Desktop-Notification statt eines kryptischen
   GUI-Fehlers.

Ein bestehendes `~/.local/bin/hermes` wird vorher als `.bak` gesichert.
Hinweis: Der Shim greift bei Terminal-Starts (`hermes`, `hermes desktop`,
`hermes update`). Startest du die Desktop-App direkt über das App-Icon,
läuft er nicht — das Plugin selbst funktioniert davon unabhängig.

## Konfiguration: Output-Limit (`EUROUTER_MAX_TOKENS`)

Ohne `max_tokens` reserviert EU Router das volle Modell-Output-Budget; bei
Routen auf 1M-Kontext-Upstreams endet das mit HTTP 400 "Estimated total
tokens (…) exceeds model context window". Das Plugin setzt deshalb bei
jedem Request ein Limit: einen vom Aufrufer gesetzten Wert (z.B. 4096 des
Goal-Judges, `model.max_tokens`, `auxiliary.<task>.max_tokens`), sonst
den Default 32768. Überschreiben per `EUROUTER_MAX_TOKENS=<zahl>` in
`~/.hermes/.env` (bzw. der `.env` des Profils); `EUROUTER_MAX_TOKENS=off`
schaltet das Plugin-Limit ab.

Einzelne Upstreams hinter einer Route haben niedrigere Output-Limits
(beobachtet: 64000, 16000). Meldet EU Router "max_tokens (X) exceeds model
limit (Y)", merkt sich das Plugin Y pro Modell, lässt Hermes den Request
wiederholen und begrenzt ab dann auf Y. Gespeichert in
`~/.hermes/cache/eurouter-output-limits.json` — Datei löschen setzt das zurück.

## Troubleshooting

| Symptom | Erste Anlaufstelle |
| --- | --- |
| "Unknown provider 'eurouter'" | `~/.hermes/logs/eurouter-plugin.log` — dort steht, welche Integration gebrochen ist |
| Routen fehlen im Picker | Im Picker "Refresh Models" klicken (1h-Cache), API-Key prüfen, Regeln im EU-Router-Account aktiviert? |
| "Model switch failed" | Hermes neu starten (Plugin-Code wird nur beim Start geladen), dann Log prüfen |
| Fix wirkt "wie nicht passiert" | `install.sh` erneut ausführen — es leert den Disk-Cache der Modell-Listen |
| HTTP 400 "Estimated total tokens … exceeds model context window" | Plugin ≥ 2.2.0 installiert? `EUROUTER_MAX_TOKENS` zu hoch gesetzt? |

Alle Degradationen schreibt das Plugin mit Zeitstempel und exakter Ursache
nach `~/.hermes/logs/eurouter-plugin.log`. Bitte diese Zeilen bei
Support-Anfragen in der [AIIANER Community](https://aiianer.de)
mitschicken.
