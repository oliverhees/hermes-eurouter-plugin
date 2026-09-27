# Changelog

Alle nennenswerten Änderungen an diesem Plugin stehen hier, neueste zuerst.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [2.1.1] - 2026-09-27

### Geprüft
- Kompatibilität live gegen den aktuellen Stand von
  `NousResearch/hermes-agent@main` verifiziert (Commit `fb2dded`,
  2026-09-27): alle von diesem Plugin verwendeten Felder aus
  `ProviderProfile` (`name`, `aliases`, `env_vars`, `display_name`,
  `description`, `signup_url`, `base_url`, `models_url`,
  `fallback_models`) und `HermesOverlay` (`transport`, `is_aggregator`,
  `auth_type`, `extra_env_vars`, `base_url_override`) existieren dort
  unverändert. Kein Bruch gefunden, keine Anpassung nötig.
- `model-providers/eurouter/__init__.py` selbst wurde in dieser Prüfung
  nicht verändert (siehe den separaten Fix vom 2026-09-10 unten, der schon
  vor dieser Prüfung auf `main` lag).

### Dokumentiert
- Klargestellt, dass Model-Provider-Plugins wie dieses bewusst nicht
  unter Settings → Plugins in Hermes Desktop erscheinen (kein Bug,
  sondern permanentes Hermes-Design) — belegt durch direkte Prüfung von
  `hermes_cli/plugins.py` und `apps/desktop/src/store/agent-plugins.ts`.
  Die zuvor in `docs/DEPLOY.md` stehende Formulierung "sobald Upstream
  das unterstützt, stellen wir um" war dadurch überholt und wurde
  korrigiert.
- `CHANGELOG.md` neu eingeführt (dieses Dokument, rückwirkend aus der
  bestehenden Commit-Historie rekonstruiert).

## [Unversioniert] - 2026-09-10

### Geändert
- `fetch_models` fail-closed statt fail-open: ohne passende Routing Rule
  zeigt der Picker jetzt ausschließlich die letzte bekannte Routen-Liste
  statt auf den generischen `/v1/models`-Katalog auszuweichen. Verhindert,
  dass Modelle im Picker erscheinen, die der Account laut EU Router gar
  nicht aufrufen darf.

## [2.1.0] - 2026-08-09

### Hinzugefügt
- Design-Vertrag im Modul-Docstring von `__init__.py`: nur der offiziell
  dokumentierte Plugin-Vertrag (`register_provider`, `ProviderProfile`)
  gilt als harte Abhängigkeit; alle privaten Integrationen (Registry #2
  `HERMES_OVERLAYS`, Registry #3 `_PROVIDER_MODELS`, Label-Override)
  laufen isoliert und degradieren laut statt die Provider-Registrierung
  mitzureißen.
- Routing Rules erscheinen als Picker-Einträge (Name statt Rohmodell),
  Auswahl löst sich beim Request in gebundenes Modell + `rule_id` auf.
- AIIANER-Branding, echtes Logo/Banner, Dual-Lizenz (AGPL-3.0 +
  kommerziell), korrekte Nous-Research-Attribution für Hermes selbst.
- Affiliate-Ref in allen Signup-Links zu eurouter.ai.

## [Unversioniert] - 2026-08-20

### Hinzugefügt
- `install.sh` bootstrapped sich selbst per Tarball, wenn es außerhalb
  eines Repo-Clones läuft — Ein-Zeilen-Installation ganz ohne `git`.
- Copy-Paste-Prompt in der README, mit dem Hermes das Plugin per
  Terminal-Zugriff selbst installiert (agentische Installation).
