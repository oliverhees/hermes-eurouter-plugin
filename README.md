<p align="center">
  <img src="assets/logo.png" alt="Hermes EU-Router-Plugin Logo" width="640" />
</p>

<h1 align="center">Hermes EU-Router-Plugin</h1>

<p align="center"><strong>Wähle in Hermes deine EU-Compliance-Routen statt roher Modelle.</strong></p>

<p align="center">
  <a href="#lizenz"><img src="https://img.shields.io/badge/Lizenz-AGPL--3.0%20%2B%20Kommerziell-red" alt="Lizenz" /></a>
  <img src="https://img.shields.io/badge/Nur%20f%C3%BCr-Hermes%20Desktop-red" alt="Nur für Hermes" />
  <img src="https://img.shields.io/badge/DSGVO-konform-red" alt="DSGVO" />
  <a href="https://aiianer.de"><img src="https://img.shields.io/badge/Community-AIIANER-black" alt="AIIANER Community" /></a>
</p>

---

## Was ist das Hermes EU-Router-Plugin?

Das Plugin bindet [EU Router](https://www.eurouter.ai?ref=06ZUHPBK) als Provider in Hermes ein und zeigt im Modell-Picker deine konfigurierten **Routing Rules** ("EU Compliance", …) statt der 130+ rohen Katalog-Modelle, von denen die meisten ohne passende Regel sowieso mit einem Fehler enden. Es ist für alle, die ihre KI-Anfragen DSGVO-konform über EU-Infrastruktur routen wollen, ohne bei jedem Chat an Modell-IDs zu denken. Und es ist update-sicher gebaut: Es lebt am offiziellen User-Plugin-Ort außerhalb des Hermes-Checkouts und überlebt die täglichen Hermes-Updates.

**Teil des AIIANER-Ökosystems:** Bei [AIIANER](https://aiianer.de) bauen wir
ein KI-Betriebssystem, das [Hermes Desktop](https://github.com/NousResearch/hermes-agent)
als Grundlage nutzt. Hermes selbst ist ein Open-Source-Projekt von
**Nous Research** — dieses Plugin ist eine unabhängige Community-Erweiterung
dafür und steht in keiner offiziellen Verbindung zu Nous Research.

## Features

- **Routen statt Modelle** — der Picker zeigt deine EU-Router-Routing-Rules beim Namen; das Plugin löst die Auswahl automatisch in das gebundene Modell plus `rule_id` auf
- **Update-sicher** — lebt unter `~/.hermes/plugins/model-providers/` (offizieller User-Plugin-Ort), hängt nur am dokumentierten Plugin-Vertrag und degradiert bei API-Drift kontrolliert statt zu crashen
- **Laute Diagnose** — jede Degradation landet mit exakter Ursache in `~/.hermes/logs/eurouter-plugin.log`; der optionale Shim prüft nach jedem Hermes-Update den Endzustand und meldet Brüche sofort

## Architektur

```
┌─────────────────────┐     ┌──────────────────────────────┐
│  Hermes Modell-     │     │  eurouter-Plugin             │
│  Picker             │────▶│  fetch_models()              │
│  "EU Compliance 2"  │     │  → Routing Rules per API     │
└─────────────────────┘     └──────────────┬───────────────┘
                                           │
                            ┌──────────────▼───────────────┐
                            │  build_api_kwargs_extras()   │
                            │  Route → gebundenes Modell   │
                            │  + rule_id in extra_body     │
                            └──────────────┬───────────────┘
                                           │
                            ┌──────────────▼───────────────┐
                            │  api.eurouter.ai             │
                            │  EU-Provider (z. B. Lyceum)  │
                            └──────────────────────────────┘
```

1. **Picker-Schicht:** `fetch_models()` holt deine aktivierten Routing Rules und zeigt sie beim Namen (Leerzeichen werden für Hermes zu Bindestrichen, die UI zeigt sie trotzdem mit Leerzeichen an).
2. **Request-Schicht:** Beim Senden löst das Plugin die gewählte Route auf, schreibt das echte gebundene Modell in den Request und hängt die `rule_id` an, damit EU Router serverseitig nach deiner Regel routet.
3. **Provider-Schicht:** EU Router führt den Request auf EU-Infrastruktur beim Provider aus, den deine Regel vorgibt.

## Setup

### Der einfachste Weg: Sag es einfach deinem Hermes 🤖

Hermes ist ein Agent mit Terminal-Zugriff — er kann das Plugin selbst
installieren. Kopiere diese Nachricht in deinen Hermes-Chat, bestätige die
Befehls-Ausführung, fertig:

> Installiere bitte das EU-Router-Plugin für mich. Führe dazu diesen Befehl aus:
> `curl -sL https://raw.githubusercontent.com/oliverhees/hermes-eurouter-plugin/main/install.sh | bash`
> Prüfe danach, ob unter `~/.hermes/plugins/model-providers/eurouter/` die Dateien
> `__init__.py` und `plugin.yaml` liegen, und sag mir, ob alles geklappt hat.
> Erinnere mich zum Schluss daran, meinen EUROUTER_API_KEY in `~/.hermes/.env`
> einzutragen und Hermes komplett neu zu starten.

### Oder selbst im Terminal — ein Befehl, kein git nötig:

```bash
curl -sL https://raw.githubusercontent.com/oliverhees/hermes-eurouter-plugin/main/install.sh | bash
```

Danach nur noch:

```bash
# 1. EU-Router-API-Key hinterlegen (Link zum Account: siehe unter dem Block)
#    in ~/.hermes/.env eintragen:
#    EUROUTER_API_KEY=eur_dein_key

# 2. Hermes komplett neu starten — fertig.
#    Der Provider "EU Router" erscheint im Modell-Picker mit deinen Routen.
```

Alternativ klassisch per Clone (praktisch, wenn du Updates per `git pull` ziehen willst):

```bash
git clone https://github.com/oliverhees/hermes-eurouter-plugin.git
cd hermes-eurouter-plugin && ./install.sh
```

👉 Account & API-Key gibt es bei [https://eurouter.ai](https://www.eurouter.ai?ref=06ZUHPBK) (→ API Keys).

Optional, für maximale Robustheit (Self-Heal + Healthcheck nach jedem Hermes-Update):

```bash
./install.sh --with-shim
```

## Deployment

Das Plugin läuft überall dort, wo Hermes Desktop oder die Hermes-CLI läuft — es wird direkt in deine lokale Hermes-Installation kopiert, ein eigener Server ist nicht nötig.

| Pfad | Wann nehmen | Doc |
| --- | --- | --- |
| **install.sh** | Standard: lokale Hermes-Desktop- oder CLI-Installation | [docs/DEPLOY.md](docs/DEPLOY.md) |

> 🎓 **Schritt-für-Schritt-Tutorials, Setups und Support** gibt es exklusiv in der
> [AIIANER Community](https://aiianer.de) — inklusive KI-Coach, der
> deine Fragen zu diesem Tool direkt beantwortet.

> 🛠️ **Du willst es nicht selbst aufsetzen?** Wir übernehmen das für dich:
> Server aufsetzen, Installation, Konfiguration — komplett einsatzbereit,
> auf Wunsch mit Wartungs- & Supportvertrag. Anfrage an **support@aiianer.de**
> oder direkt in der [AIIANER Community](https://aiianer.de).

## Status

Funktioniert und live verifiziert:

- Routing Rules erscheinen als Picker-Einträge und lassen sich auswählen
- Auswahl wird korrekt in gebundenes Modell + `rule_id` aufgelöst (echter End-to-End-Call gegen die EU-Router-API getestet)
- Überlebt Hermes-Updates: hängt nur am offiziellen Plugin-Vertrag, alle internen Integrationen degradieren kontrolliert und loggen laut
- Fallbacks: ohne konfigurierte Regeln zeigt der Picker den generischen Katalog; bei hängendem Rules-Endpoint die letzte bekannte Routen-Liste

Offen: Der Healthcheck-Shim greift nur bei Starts über den `hermes`-Befehl im Terminal (die Desktop-App spawnt ihr Backend direkt). Da die Robustheit im Plugin selbst steckt, ist das in der Praxis unkritisch; eine tiefere Integration ist angedacht.

---

## 🌍 Das AIIANER-Universum

| | |
| --- | --- |
| 🏠 **Community** | [aiianer.de](https://aiianer.de) — Kurse, Labs, Tutorials, KI-Coaches |
| 📺 **YouTube** | [youtube.com/@aiianer](https://www.youtube.com/@aiianer) — Tools, Tests, Deep-Dives |
| 🧠 **Lokyy Brain** | [github.com/oliverhees/lokyy-brain](https://github.com/oliverhees/lokyy-brain) — dein Second Brain, selbst gehostet |
| 🔒 **Datenschleuse** | DSGVO-Filter für deine KI — Tutorials in der Community |
| 📡 **Sichtradar** | [sichtradar.de](https://sichtradar.de) — empfiehlt die KI dich oder deine Konkurrenz? |
| 🤖 **Lokyy** | [lokyy.de](https://lokyy.de) — KI-Apps & Werkzeuge |

## Lizenz

Das Hermes EU-Router-Plugin ist **dual lizenziert**:

1. **AGPL-3.0** — für private Nutzung, Selbsthoster, Forschung und alle
   Projekte, die ihre Änderungen ebenfalls unter AGPL-3.0 offenlegen.
   Siehe [LICENSE](LICENSE).
2. **Kommerzielle Lizenz** — wer das Plugin in geschlossenen, kommerziellen
   Produkten oder Diensten einsetzen will, ohne eigenen Quellcode offenzulegen,
   benötigt eine kommerzielle Lizenz. Details in [LICENSING.md](LICENSING.md),
   Anfragen über die [AIIANER Community](https://aiianer.de) oder
   **support@aiianer.de**.

**Wartung, Support & Anpassungen** gibt es als Vertrag direkt vom Entwickler —
Details in [LICENSING.md](LICENSING.md).

## Sicherheit

Sicherheitslücken bitte **nicht** als öffentliches Issue melden.
Verantwortungsvolle Meldung: siehe [SECURITY.md](SECURITY.md).

## Marken

„AIIANER", „Lokyy", „Lokyy Brain", „Datenschleuse" und „Sichtradar"
sind Kennzeichen von Oliver Hees aka Aiianer. Die Lizenz des Quellcodes gewährt
**keine** Rechte an diesen Namen oder Logos. Forks müssen unter eigenem Namen
auftreten.

„Hermes" ist ein Open-Source-Projekt von **Nous Research**
([github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)).
„EU Router" / eurouter.ai ist ein Angebot des jeweiligen Betreibers.
Dieses Plugin ist ein unabhängiges Community-Projekt und steht in keiner
offiziellen Verbindung zu Nous Research oder eurouter.ai.

---

<p align="center">
  © 2026 <strong>Oliver Hees aka Aiianer</strong> ·
  <a href="https://aiianer.de">aiianer.de</a> ·
  Made with 🖤 im AIIANER-Universum
</p>
