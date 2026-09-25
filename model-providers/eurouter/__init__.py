"""EU Router provider profile — USER PLUGIN (see plugin.yaml for why here).

EU Router (eurouter.ai) is an OpenAI/OpenRouter-API-compatible aggregator
whose distinguishing feature is EU data-residency guarantees: all inference
requests are processed entirely within the EU. Account-level "Routing Rules"
(https://www.eurouter.ai/docs/api/routing-rules) decide which model+provider
combination actually serves a request.

===========================================================================
DESIGN CONTRACT (v2.1.0, 2026-08-09) — read before touching anything
===========================================================================
Six consecutive days of daily Hermes updates broke this integration six
times. Post-mortem: every single breakage came from depending on something
that is NOT part of Hermes' official plugin contract. This file now follows
one rule above all others:

    The ONLY hard dependencies are the officially documented plugin surface:
      - ``providers.register_provider`` and ``providers.base.ProviderProfile``
        with its overridable hooks (fetch_models / build_extra_body /
        build_api_kwargs_extras) — documented in providers/__init__.py's own
        module docstring as the user-plugin extension point, explicitly
        designed so user plugins under ``$HERMES_HOME/plugins/model-providers/``
        override bundled ones ("Later registrations with the same name
        replace earlier ones").
    Everything else (HERMES_OVERLAYS, _LABEL_OVERRIDES, _PROVIDER_MODELS)
    is a PRIVATE internal that may change any day. Each such integration:
      1. lives in its own isolated try/except (one breaking never kills
         another, and NEVER kills the plugin import),
      2. introspects the current API shape (dataclasses.fields) instead of
         assuming yesterday's signature,
      3. reports degradation LOUDLY via _log_issue() to
         ``$HERMES_HOME/logs/eurouter-plugin.log`` — so the day something
         drifts, the log names the exact broken integration instead of the
         GUI showing a cryptic error.

FORK-API TRAP (the 2026-08-09 breakage, day six): earlier versions of this
plugin used ``ProviderProfile.routing_preference_keys`` and
``self.filter_routing_preferences(...)``. BOTH exist only in Oliver's old
fork commit ("Add EU Router provider with EU data-residency routing rules"),
NEVER in upstream — confirmed via ``git log --all -S routing_preference_keys``
showing exactly one (fork) commit. They only appeared to work while that old
cherry-pick sat in the checkout; the first clean-upstream update removed
them and the plugin import died with "type object 'ProviderProfile' has no
attribute 'routing_preference_keys'" → "Unknown provider 'eurouter'".
RULE: before using ANY attribute/method of a Hermes class here, verify it
exists in the CLEAN upstream checkout (git log --all -S <name> must show
upstream commits, not just our fork's).

===========================================================================
WHY THIS FILE LIVES HERE AND NOT IN THE hermes-agent REPO
===========================================================================
Live-Befund 2026-08-07: code in the ``~/.hermes/hermes-agent`` git checkout
(bundled ``plugins/model-providers/``) is wiped by Hermes' auto-updater
(git stash/pull/pop resolves delete/modify conflicts by DELETING local
files). This user-plugin location is outside the checkout and is the
official, documented extension point. Source of truth + versioning: your
clone of the plugin's git repo (public home:
https://github.com/oliverhees/hermes-eurouter-plugin) + the optional
self-heal shim at ``~/.local/bin/hermes``. RULE: never edit the live copy
directly — edit the repo clone, re-run the install/deploy script.

===========================================================================
Routing Rules as picker entries (Live-Befund 2026-08-07)
===========================================================================
EU Router's public catalog lists 130+ models, but an account can only CALL
models bound to one of its configured Routing Rules — everything else 404s.
So ``fetch_models`` returns the account's enabled rules BY NAME (Oliver's
explicit ask: "ich will die Routes auswählen"), slugified to dashes because
``validate_requested_model`` rejects any id containing whitespace ("Model
names cannot contain spaces."). The desktop UI's generic label logic
(model-status-label.ts::prettifyBase) turns dashes back into spaces for
display, so the picker still shows "EU Compliance 3".

``build_api_kwargs_extras`` then resolves the selected slug back to its
rule and rewrites the outgoing request: top-level ``model`` becomes the
rule's real bound model (EU Router validates ``model`` against its real
catalog BEFORE looking at ``rule_id`` — live-verified via curl), and
``rule_id`` goes into ``extra_body`` (NOT top_level: openai-python's typed
``.create()`` rejects unknown top-level kwargs — "unexpected keyword
argument 'rule_id'", live-verified). Backward compat: a session storing a
raw model id still matches via the rule's ``model`` field.

===========================================================================
THREE private registries + the disk cache (Live-Befunde 2026-08-07)
===========================================================================
1. ``providers/`` registry (official, via register_provider) — picker/
   request building.
2. ``hermes_cli/providers.py::HERMES_OVERLAYS`` — identity resolution on
   switch; missing → "Unknown provider 'eurouter'".
3. ``hermes_cli/models.py::_PROVIDER_MODELS`` — validate_requested_model's
   own catalog check (its live probe bypasses our fetch_models); missing →
   "Model `X` was not found in this provider's model listing".
Plus: ``$HERMES_HOME/provider_models_cache.json`` disk-caches picker lists
for 1h keyed by credential fingerprint, NOT by plugin code — after any
change here, clear the "eurouter" key (deploy.sh does this) or a stale list
survives restarts and masks the fix.

Failure-mode philosophy: routing lookups are FAIL-SOFT (a failed rules
fetch degrades to an un-routed request — worse routing, never a blocked
chat). Deliberately the opposite of Datenschleuse's fail-CLOSED PII
masking: getting routing wrong is a quality issue, getting masking wrong
leaks data.
"""

from __future__ import annotations

import dataclasses
import datetime
import inspect
import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

ROUTING_RULES_URL = "https://api.eurouter.ai/api/v1/routing-rules"
_EUROUTER_BASE_URL = "https://api.eurouter.ai/api/v1"


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "") or (Path.home() / ".hermes"))


_ISSUE_LOG = _hermes_home() / "logs" / "eurouter-plugin.log"


def _log_issue(msg: str) -> None:
    """Loud, durable degradation diagnostics. Never raises.

    Every optional integration reports its failure here — this file is the
    FIRST place to look when EU Router misbehaves after a Hermes update.
    (Six days of silent ``logger.debug`` swallowing taught this lesson.)
    """
    try:
        logger.warning("eurouter plugin: %s", msg)
    except Exception:
        pass
    try:
        _ISSUE_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with _ISSUE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {msg}\n")
    except Exception:
        pass


# Small, rarely-changing list — re-fetching on every chat turn would add
# avoidable latency. 5 minutes; "Refresh Models" is the manual override.
_ROUTING_RULES_CACHE_TTL_SECONDS = 300.0

# {api_key: (fetched_at_monotonic, rules)} — keyed per api_key so a
# multi-key setup never serves one account's rules to another's requests.
_routing_rules_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _fetch_routing_rules(api_key: str, timeout: float = 8.0) -> list[dict[str, Any]] | None:
    """Fetch this account's ENABLED routing rules, in-process cached.

    Returns None on any failure (network, auth, shape) — fail-soft, see
    module docstring. Uses Hermes' hardened opener when available (redirect
    credential policy), plain urllib otherwise — the security helper is a
    private internal and must not be a hard dependency.
    """
    now = time.monotonic()
    cached = _routing_rules_cache.get(api_key)
    if cached is not None and now - cached[0] < _ROUTING_RULES_CACHE_TTL_SECONDS:
        return cached[1]

    req = urllib.request.Request(f"{ROUTING_RULES_URL}?include_disabled=false")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Accept", "application/json")

    try:
        opener = None
        try:
            from hermes_cli.urllib_security import open_credentialed_url as opener
        except Exception:
            opener = None
        if opener is not None:
            resp_ctx = opener(req, timeout=timeout)
        else:
            resp_ctx = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — fixed https URL
        with resp_ctx as resp:
            data = json.loads(resp.read().decode())
        rules = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rules, list):
            logger.debug("routing-rules fetch: unexpected response shape")
            return None
        # Defense in depth: never trust a remote API to enforce its own
        # enabled-only filter param.
        rules = [r for r in rules if isinstance(r, dict) and r.get("enabled", True)]
        _routing_rules_cache[api_key] = (now, rules)
        return rules
    except Exception as exc:
        logger.debug("routing-rules fetch failed: %s", exc)
        return None


def _slugify_rule_name(name: str) -> str:
    """"EU Compliance 3" -> "EU-Compliance-3" — Hermes rejects model ids
    containing whitespace (validate_requested_model) before a switch ever
    reaches this plugin. The desktop UI turns dashes back into spaces for
    display, so this round-trips losslessly for rule names without literal
    dashes."""
    return re.sub(r"\s+", "-", name.strip())


def _rule_for_selection(api_key: str, selection: str) -> dict[str, Any] | None:
    """The rule *selection* refers to — matched by SLUGIFIED name first
    (current picker behavior), then by the rule's bound MODEL (older
    sessions storing a raw model id). None if neither matches. On name
    collision the first rule (API list order) wins — documented limitation.
    """
    rules = _fetch_routing_rules(api_key)
    if not rules:
        return None
    for rule in rules:
        name = rule.get("name")
        if isinstance(name, str) and _slugify_rule_name(name) == selection:
            return rule
    for rule in rules:
        if rule.get("model") == selection:
            return rule
    return None


def _sync_provider_models_catalog(names: list[str]) -> None:
    """Mirror *names* into ``hermes_cli.models._PROVIDER_MODELS`` (private
    registry #3 — the validate_requested_model gate; see module docstring).
    Isolated + loud: if the internal moves, route names disappear from the
    switch gate ("Model X was not found...") but nothing else breaks, and
    the log says exactly why."""
    try:
        from hermes_cli.models import _PROVIDER_MODELS

        _PROVIDER_MODELS["eurouter"] = list(names)
    except Exception as exc:
        _log_issue(
            f"registry #3 (_PROVIDER_MODELS) sync failed: {type(exc).__name__}: {exc} — "
            "switching to a route will fail its catalog check until this plugin is adapted"
        )


# Last successfully computed picker list — served when a later fetch fails
# entirely, so a flaky routing-rules endpoint degrades to "yesterday's
# routes" instead of an empty picker that LOOKS like the old breakage.
_last_good_route_names: list[str] = []


# ---------------------------------------------------------------------------
# Output-token cap (Live-Befund 2026-09-25, Kanban t_fd3b89f0)
# ---------------------------------------------------------------------------
# A request WITHOUT max_tokens makes EU Router budget the model's full
# max_completion_tokens as output. For routes landing on a 1M-window upstream
# (deepseek-v4-flash-0731 advertises max_completion_tokens == context_length)
# every such request 400s, even a 12-token prompt:
#   "Estimated total tokens (1048589) exceeds model context window (1048576).
#    Reduce message length or max_tokens."
# Hermes omits max_tokens on this provider in two places:
#   1. Main agent loop: sends the caller/config value, else the profile's
#      get_max_tokens() — official hook, overridden below.
#   2. Auxiliary calls (goal judge, titles, compression, ...):
#      agent/auxiliary_client.py::_forwards_max_tokens() is a hard-coded
#      provider allow-list without eurouter, so even an explicit value (the
#      goal judge's 4096) is dropped. The only plugin surface on that path is
#      build_api_kwargs_extras()'s top_level dict (merged AFTER that check),
#      which is not handed the caller's value — _aux_caller_max_tokens()
#      recovers it read-only from the calling frame (private internal,
#      fail-soft: default cap when it can't be found).
# The cap must also stay under the UPSTREAM's own output limit, which varies
# per upstream behind one route (live 2026-09-25: 64000 for a
# deepseek-v4-flash upstream, 16000 for a glm-5.2 one) and is not published.
# Exceeding it 400s with "max_tokens (65536) exceeds model limit (64000).";
# Hermes' output-cap parser doesn't know that wording, treats it as context
# overflow and gives up. So classify_api_error (official profile hook) turns
# it into a plain retry and remembers the limit per model; the retry's
# rebuilt request then asks get_max_tokens() again and gets the learned
# limit. Learned limits persist in $HERMES_HOME/cache/ because every kanban
# worker is a fresh process — delete the file to forget them.
# Override the default with EUROUTER_MAX_TOKENS (e.g. in the profile's .env);
# "0"/"off" restores the old behavior (no plugin-side cap).
_DEFAULT_MAX_TOKENS = 32768
_MAX_TOKENS_ENV = "EUROUTER_MAX_TOKENS"
_AUX_MODULE = "agent.auxiliary_client"
_LIMITS_FILE = _hermes_home() / "cache" / "eurouter-output-limits.json"
_OUTPUT_LIMIT_RE = re.compile(r"max_tokens\s*\(\s*(\d+)\s*\)\s*exceeds model limit\s*\(\s*(\d+)\s*\)", re.IGNORECASE)

# {model as Hermes sends it (route slug): lowest upstream output limit seen}
_learned_limits: dict[str, int] | None = None


def _load_learned_limits() -> dict[str, int]:
    global _learned_limits
    if _learned_limits is None:
        _learned_limits = {}
        try:
            data = json.loads(_LIMITS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _learned_limits = {str(k): int(v) for k, v in data.items() if int(v) > 0}
        except FileNotFoundError:
            pass
        except Exception as exc:
            _log_issue(f"learned output limits unreadable ({type(exc).__name__}: {exc}); starting empty")
    return _learned_limits


def _remember_output_limit(model: str, limit: int) -> None:
    limits = _load_learned_limits()
    if limits.get(model, limit + 1) <= limit:
        return
    limits[model] = limit
    _log_issue(f"learned upstream output limit {limit} for model '{model}'; capping max_tokens there")
    try:
        _LIMITS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LIMITS_FILE.with_name(f"{_LIMITS_FILE.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(limits, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, _LIMITS_FILE)
    except Exception as exc:
        _log_issue(f"could not persist learned output limits ({type(exc).__name__}: {exc}); kept in memory")


def _capped(cap: int | None, model: str | None) -> int | None:
    """*cap* lowered to the learned upstream limit of *model*, if any."""
    if not cap or not model:
        return cap
    learned = _load_learned_limits().get(model)
    return min(cap, learned) if learned else cap


def _classify_api_error(error: Any = None, *, message: str | None = None, model: str | None = None,
                        **context: Any) -> dict[str, Any] | None:
    """ProviderProfile.classify_api_error: "max_tokens (X) exceeds model limit (Y)"
    → remember Y for *model* and retry (the rebuilt request is capped at Y).
    Everything else → None (Hermes' built-in classification)."""
    try:
        match = _OUTPUT_LIMIT_RE.search(" ".join(str(part) for part in (message, error) if part))
        if not match or not model:
            return None
        requested, limit = int(match.group(1)), int(match.group(2))
        if not 0 < limit < requested:
            return None
        _remember_output_limit(model, limit)
        return {"reason": "unknown", "retryable": True, "should_compress": False, "should_fallback": False}
    except Exception as exc:
        _log_issue(f"classify_api_error failed unexpectedly ({type(exc).__name__}: {exc}); built-in classification applies")
        return None


def _configured_max_tokens() -> int | None:
    """Default output cap: EUROUTER_MAX_TOKENS if set, else _DEFAULT_MAX_TOKENS;
    None when explicitly disabled."""
    raw = os.environ.get(_MAX_TOKENS_ENV, "").strip()
    if not raw:
        return _DEFAULT_MAX_TOKENS
    if raw.lower() in ("0", "off", "none", "false", "disabled"):
        return None
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    _log_issue(f"{_MAX_TOKENS_ENV}={raw!r} is not a positive integer; using {_DEFAULT_MAX_TOKENS}")
    return _DEFAULT_MAX_TOKENS


def _aux_caller_max_tokens() -> tuple[bool, int | None]:
    """``(on_aux_path, caller_max_tokens)`` for the build_api_kwargs_extras call
    in progress. The aux path is recognized by its DIRECT caller living in
    agent.auxiliary_client; the main transport path returns (False, None) so
    its own max_tokens handling (caller/config value, then get_max_tokens)
    stays untouched. Never raises."""
    frame = inspect.currentframe()
    try:
        # [0] this helper, [1] build_api_kwargs_extras, [2] its caller.
        caller = frame.f_back.f_back if frame else None
        if caller is None or caller.f_globals.get("__name__") != _AUX_MODULE:
            return False, None
        f = caller
        for _ in range(4):
            if f is None or f.f_globals.get("__name__") != _AUX_MODULE:
                break
            if "max_tokens" in f.f_code.co_varnames:
                value = f.f_locals.get("max_tokens")
                return True, value if isinstance(value, int) and value > 0 else None
            f = f.f_back
        _log_issue("aux path: caller max_tokens not found in agent.auxiliary_client frames; using default cap")
        return True, None
    except Exception as exc:
        # Path unknown: never risk overriding a main-loop caller/config value.
        _log_issue(f"aux max_tokens lookup failed ({type(exc).__name__}: {exc}); no plugin-side cap on this call")
        return False, None
    finally:
        del frame


class EuRouterProfile(ProviderProfile):
    """EU Router aggregator — Routing-Rules picker + rule_id request rewrite.

    RUNTIME fail-soft (advisor finding, 2026-08-09): import-time hardening
    alone doesn't protect the CALL path — upstream also drifts hook call
    conventions (validate_requested_model changed its signature in the same
    update that broke the import). Every hook therefore (a) accepts
    arbitrary extra kwargs via ``**context`` and (b) wraps its body so an
    unexpected runtime error degrades (logged, un-routed/plain request)
    instead of crashing the chat turn."""

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
        **context: Any,
    ) -> list[str] | None:
        """Restrict the picker to the account's routing rules, BY NAME.
        Never expose the generic catalog: models without a matching Routing
        Rule are not valid choices for this provider."""
        try:
            key = api_key or os.environ.get("EUROUTER_API_KEY", "")
            if key:
                rules = _fetch_routing_rules(key, timeout=timeout)
                if rules:
                    names: list[str] = []
                    seen: set[str] = set()
                    for rule in rules:
                        name = rule.get("name")
                        if not isinstance(name, str) or not name:
                            continue
                        slug = _slugify_rule_name(name)
                        if slug not in seen:
                            seen.add(slug)
                            names.append(slug)
                    if names:
                        _sync_provider_models_catalog(names)
                        _last_good_route_names[:] = names
                        return names
            # No valid Routing Rules: keep the picker fail-closed. The
            # generic model catalog contains models that this account may not
            # call and must never be presented as EUrouter routes.
            return list(_last_good_route_names) or None
        except Exception as exc:
            _log_issue(f"fetch_models failed unexpectedly ({type(exc).__name__}: {exc}); serving last good route list")
        return list(_last_good_route_names) or None

    def get_max_tokens(self, model: str | None = None, **context: Any) -> int | None:
        """Main-loop default output cap (the transport only asks when neither
        the caller nor the config set max_tokens). See "Output-token cap"."""
        try:
            return _capped(_configured_max_tokens(), model)
        except Exception as exc:
            _log_issue(f"get_max_tokens failed unexpectedly ({type(exc).__name__}: {exc}); using {_DEFAULT_MAX_TOKENS}")
            return _DEFAULT_MAX_TOKENS

    def build_extra_body(
        self, *, session_id: str | None = None, **context: Any
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        try:
            if session_id:
                body["session_id"] = session_id
            # ``filter_routing_preferences`` was a FORK-ONLY helper (see
            # module docstring, FORK-API TRAP). Upstream threads preferences
            # through ``context["provider_preferences"]`` as a plain dict
            # (same as the bundled openrouter plugin). Use the helper only
            # if it happens to exist; never require it.
            prefs = context.get("provider_preferences")
            filt = getattr(self, "filter_routing_preferences", None)
            if callable(filt):
                try:
                    prefs = filt(prefs)
                except Exception as exc:
                    _log_issue(f"filter_routing_preferences raised ({exc}); passing prefs unfiltered")
            if isinstance(prefs, dict) and prefs:
                body["provider"] = prefs
        except Exception as exc:
            _log_issue(f"build_extra_body failed unexpectedly ({type(exc).__name__}: {exc}); sending minimal body")
        return body

    def build_api_kwargs_extras(
        self,
        *,
        reasoning_config: dict | None = None,
        supports_reasoning: bool = False,
        model: str | None = None,
        **context: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Reasoning passthrough (extra_body.reasoning, OpenRouter shape) +
        route resolution: rewrite top-level ``model`` to the rule's real
        bound model and attach ``rule_id`` via extra_body.

        ``model`` → top_level: a real typed ``.create()`` parameter; the
        transport's dict-merge order lets top_level override the initial
        api_kwargs["model"] (live-verified).
        ``rule_id`` → extra_body ONLY: openai-python's typed ``.create()``
        rejects unknown top-level kwargs ("unexpected keyword argument
        'rule_id'", live-verified 2026-08-07). Do not move it back.
        ``max_tokens`` → top_level on the AUX path only (see "Output-token
        cap" above); the main loop gets it via get_max_tokens().
        """
        extra_body: dict[str, Any] = {}
        top_level: dict[str, Any] = {}
        try:
            on_aux_path, caller_max_tokens = _aux_caller_max_tokens()
            if on_aux_path:
                cap = _capped(caller_max_tokens or _configured_max_tokens(), model)
                if cap:
                    top_level["max_tokens"] = cap
        except Exception as exc:
            _log_issue(f"aux max_tokens cap failed unexpectedly ({type(exc).__name__}: {exc}); request goes out uncapped")
        try:
            if supports_reasoning:
                if reasoning_config is not None:
                    extra_body["reasoning"] = dict(reasoning_config)
                else:
                    extra_body["reasoning"] = {"enabled": True, "effort": "medium"}

            # No api_key parameter reaches this hook — the env var is what
            # Hermes itself resolves for this provider (env_vars below).
            key = os.environ.get("EUROUTER_API_KEY", "")
            if key and model:
                rule = _rule_for_selection(key, model)
                if rule:
                    bound_model = rule.get("model")
                    if isinstance(bound_model, str) and bound_model and bound_model != model:
                        top_level["model"] = bound_model
                    rule_id = rule.get("id")
                    if isinstance(rule_id, str) and rule_id:
                        extra_body["rule_id"] = rule_id
                elif model in _last_good_route_names:
                    # The picker stored a ROUTE name but the rules lookup just
                    # failed → the raw name would 404 at EU Router. Better a
                    # loud log now than a cryptic 404 for the user.
                    _log_issue(
                        f"route '{model}' could not be resolved (rules fetch failed?); "
                        "request will go out unrouted and may 404"
                    )
        except Exception as exc:
            _log_issue(f"build_api_kwargs_extras failed unexpectedly ({type(exc).__name__}: {exc}); sending un-routed request")
        return extra_body, top_level


# ---------------------------------------------------------------------------
# Profile construction — drift-tolerant.
#
# ProviderProfile is an upstream @dataclass; passing a kwarg for a field that
# no longer exists raises TypeError and (before v2.1.0) killed the whole
# plugin import. Now: introspect the CURRENT field set and only pass what
# exists, logging anything dropped. A last-resort minimal retry keeps the
# provider registered (name + key + base_url is enough to chat) even if the
# dataclass changes radically.
#
# NOTE deliberately ABSENT: ``routing_preference_keys`` — fork-only, never
# upstream (the 2026-08-09 day-six breakage; see FORK-API TRAP above). EU
# Router's compliance routing lives server-side in the account's Routing
# Rules, so nothing is lost client-side by not declaring extra pref keys.
# ---------------------------------------------------------------------------
_PROFILE_KWARGS: dict[str, Any] = {
    "name": "eurouter",
    "aliases": ("eu-router", "eur"),
    "env_vars": ("EUROUTER_API_KEY",),
    "display_name": "EU Router",
    "description": "EUrouter — EU-hosted, GDPR-compliant model routing",
    # Affiliate-Ref: user-facing signup link shown in Hermes' provider setup
    # UI — every marketing link to eurouter.ai carries Oliver's ref code
    # (API endpoints stay clean, they are functional URLs, not links).
    "signup_url": "https://www.eurouter.ai?ref=06ZUHPBK",
    "base_url": _EUROUTER_BASE_URL,
    "models_url": f"{_EUROUTER_BASE_URL}/models",
    # Deliberately EMPTY: hermes_cli/models.py's live-fetch caller MERGES
    # fallback_models into fetch_models() output — a non-empty list here
    # would re-inject un-routed raw models into the picker (the exact
    # 400-error bug fetch_models() exists to fix). fetch_models() already
    # handles the no-rules case by falling back to the generic catalog.
    "fallback_models": (),
    # A dataclass FIELD upstream (not a method): must be passed here, a
    # subclass method would be shadowed by the field's None default.
    "classify_api_error": _classify_api_error,
}


def _make_profile() -> EuRouterProfile:
    kwargs = dict(_PROFILE_KWARGS)
    try:
        valid = {f.name for f in dataclasses.fields(ProviderProfile)}
        dropped = sorted(k for k in kwargs if k not in valid)
        for k in dropped:
            kwargs.pop(k)
        if dropped:
            _log_issue(
                f"ProviderProfile no longer has field(s) {dropped}; constructing without them"
            )
    except Exception:
        pass  # introspection is best-effort; the TypeError retry below still guards
    try:
        return EuRouterProfile(**kwargs)
    except TypeError as exc:
        _log_issue(f"full profile construction failed ({exc}); retrying with minimal fields")
        return EuRouterProfile(
            name="eurouter",
            env_vars=("EUROUTER_API_KEY",),
            base_url=_EUROUTER_BASE_URL,
        )


eurouter = _make_profile()
register_provider(eurouter)


# ---------------------------------------------------------------------------
# Private-registry integrations — each isolated, each loud on failure.
# A breaking change in ONE degrades exactly that capability and logs it;
# it never takes down the plugin import or the other integrations.
# ---------------------------------------------------------------------------
def _register_switch_identity() -> None:
    """Registry #2: HERMES_OVERLAYS — identity resolution on model switch.
    Missing → "Unknown provider 'eurouter'" on switch (picker still lists
    the provider). Overlay kwargs are introspected against the CURRENT
    HermesOverlay dataclass so a renamed/removed field degrades to a
    partial overlay instead of a construction crash."""
    try:
        from hermes_cli.providers import HERMES_OVERLAYS, HermesOverlay
    except Exception as exc:
        _log_issue(
            f"registry #2 (HERMES_OVERLAYS) import failed: {type(exc).__name__}: {exc} — "
            "switching to 'eurouter' will fail with 'Unknown provider' until adapted"
        )
        return
    try:
        wanted: dict[str, Any] = {
            "transport": "openai_chat",
            "is_aggregator": True,
            "auth_type": "api_key",
            "extra_env_vars": ("EUROUTER_API_KEY",),
            "base_url_override": _EUROUTER_BASE_URL,
        }
        try:
            valid = {f.name for f in dataclasses.fields(HermesOverlay)}
            dropped = sorted(k for k in wanted if k not in valid)
            wanted = {k: v for k, v in wanted.items() if k in valid}
            if dropped:
                _log_issue(f"HermesOverlay no longer has field(s) {dropped}; registering without them")
        except Exception:
            pass
        HERMES_OVERLAYS.setdefault("eurouter", HermesOverlay(**wanted))
    except Exception as exc:
        _log_issue(f"registry #2 (HERMES_OVERLAYS) registration failed: {type(exc).__name__}: {exc}")


def _register_label() -> None:
    """Cosmetic only: picker/status label "EU Router" instead of "Eurouter"."""
    try:
        from hermes_cli.providers import _LABEL_OVERRIDES

        _LABEL_OVERRIDES.setdefault("eurouter", "EU Router")
    except Exception as exc:
        _log_issue(f"label override failed (cosmetic only): {type(exc).__name__}: {exc}")


_register_switch_identity()
_register_label()
