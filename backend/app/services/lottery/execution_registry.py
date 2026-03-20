"""Explicit execution registry for per-agent provider/model bindings."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from ...config import Config
from ...utils.llm_client import LLMClient
from .execution_models import ExecutionProfile, ModelSpec, ProviderSpec, ResolvedExecutionBinding


DEFAULT_PROFILE_ID = "default"
DEFAULT_PROVIDER_ID = "default"
DEFAULT_MODEL_ID = "default"
CONFIG_DIR = Path(__file__).resolve().parent


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class ExecutionRegistry:
    """Read ``execution_config.yaml`` and resolve manual execution bindings."""

    def __init__(self, config_path: Path | None = None) -> None:
        raw = _load_yaml(config_path or _config_path())
        self._providers = _parse_providers(raw.get("providers"))
        self._models = _parse_models(raw.get("models"))
        self._profiles = _parse_profiles(raw.get("profiles"))
        _merge_env_provider_presets(self._providers, self._models, self._profiles)
        self._role_defaults = dict(raw.get("role_defaults") or {})
        self._group_overrides = dict(raw.get("group_overrides") or {})
        self._agent_overrides = dict(raw.get("agent_overrides") or {})
        self._decision_weights = dict(raw.get("decision_weights") or {})
        self._happy8_feature_profile = dict(raw.get("happy8_feature_profile") or {})
        self._ensure_fallback_entries()

    def export_catalog(self) -> dict[str, Any]:
        return {
            "providers": [self._provider_payload(item) for item in self._providers.values()],
            "models": [self._model_payload(item) for item in self._models.values()],
            "profiles": [self._profile_payload(item) for item in self._profiles.values()],
            "role_defaults": dict(self._role_defaults),
            "group_overrides": dict(self._group_overrides),
            "agent_overrides": dict(self._agent_overrides),
            "decision_weights": dict(self._decision_weights),
            "happy8_feature_profile": dict(self._happy8_feature_profile),
        }

    def decision_weights(self) -> dict[str, float]:
        return {key: float(value) for key, value in self._decision_weights.items()}

    def happy8_feature_profile(self) -> dict[str, Any]:
        return dict(self._happy8_feature_profile)

    def normalize_overrides(self, overrides: Mapping[str, Any] | None) -> dict[str, dict[str, str]]:
        payload = dict(overrides or {})
        return {
            "group_overrides": _string_map(payload.get("group_overrides")),
            "agent_overrides": _string_map(payload.get("agent_overrides")),
        }

    def resolve_profile(
        self,
        agent_id: str,
        role_kind: str,
        group: str | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> ExecutionProfile:
        profile_id = self._profile_id_for(agent_id, role_kind, group, overrides)
        return self._profiles.get(profile_id, self._fallback_profile())

    def resolve_binding(
        self,
        agent_id: str,
        role_kind: str,
        group: str | None = None,
        overrides: Mapping[str, Any] | None = None,
        routing_mode: str = "active",
    ) -> ResolvedExecutionBinding:
        profile_id = self._profile_id_for(agent_id, role_kind, group, overrides)
        profile = self._profiles.get(profile_id, self._fallback_profile())
        model = self.resolve_model(profile.model_id)
        provider = self.resolve_provider(model.provider_id or profile.provider_id)
        model_id = model.model_id if model.model_id != DEFAULT_MODEL_ID else (Config.LLM_MODEL_NAME or DEFAULT_MODEL_ID)
        return ResolvedExecutionBinding(
            agent_id=agent_id,
            role_kind=role_kind,
            group=group,
            profile_id=profile.profile_id,
            provider_id=provider.provider_id,
            model_id=model_id,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            json_mode=profile.json_mode,
            retry_count=profile.retry_count,
            retry_backoff_ms=profile.retry_backoff_ms,
            timeout_s=profile.timeout_s,
            prompt_style=profile.prompt_style,
            fallback_profile_ids=profile.fallback_profile_ids,
            routing_mode=routing_mode,
            metadata={
                "provider_kind": provider.kind,
                "supports_json_mode": model.supports_json_mode,
                "capability_tags": list(model.capability_tags),
                "cost_hint": model.cost_hint,
                "max_context": model.max_context,
            },
        )

    def resolve_provider(self, provider_id: str) -> ProviderSpec:
        return self._providers.get(provider_id, self._fallback_provider())

    def resolve_model(self, model_id: str) -> ModelSpec:
        return self._models.get(model_id, self._fallback_model())

    def build_client(self, profile: ExecutionProfile) -> LLMClient:
        provider = self.resolve_provider(profile.provider_id)
        api_key = _env_or_default(provider.api_key_env, Config.LLM_API_KEY)
        base_url = provider.base_url or Config.LLM_BASE_URL
        model_name = profile.model_id if profile.model_id != DEFAULT_MODEL_ID else Config.LLM_MODEL_NAME
        return LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            retry_count=profile.retry_count,
            retry_backoff_ms=profile.retry_backoff_ms,
        )

    def profile(self, profile_id: str) -> ExecutionProfile:
        return self._profiles.get(profile_id, self._fallback_profile())

    def _profile_id_for(
        self,
        agent_id: str,
        role_kind: str,
        group: str | None,
        overrides: Mapping[str, Any] | None,
    ) -> str:
        normalized = self.normalize_overrides(overrides)
        if agent_id in normalized["agent_overrides"]:
            return normalized["agent_overrides"][agent_id]
        if agent_id in self._agent_overrides:
            return self._agent_overrides[agent_id]
        if group and group in normalized["group_overrides"]:
            return normalized["group_overrides"][group]
        if group and group in self._group_overrides:
            return self._group_overrides[group]
        return self._role_defaults.get(role_kind, DEFAULT_PROFILE_ID)

    def _ensure_fallback_entries(self) -> None:
        if DEFAULT_PROVIDER_ID not in self._providers:
            self._providers[DEFAULT_PROVIDER_ID] = self._fallback_provider()
        if DEFAULT_MODEL_ID not in self._models:
            self._models[DEFAULT_MODEL_ID] = self._fallback_model()
        if DEFAULT_PROFILE_ID not in self._profiles:
            self._profiles[DEFAULT_PROFILE_ID] = self._fallback_profile()

    def _provider_payload(self, item: ProviderSpec) -> dict[str, Any]:
        return {
            "provider_id": item.provider_id,
            "kind": item.kind,
            "base_url": item.base_url,
            "api_key_env": item.api_key_env,
            "timeout_s": item.timeout_s,
        }

    def _model_payload(self, item: ModelSpec) -> dict[str, Any]:
        return {
            "model_id": item.model_id,
            "provider_id": item.provider_id,
            "capability_tags": list(item.capability_tags),
            "supports_json_mode": item.supports_json_mode,
            "max_context": item.max_context,
            "cost_hint": item.cost_hint,
        }

    def _profile_payload(self, item: ExecutionProfile) -> dict[str, Any]:
        return {
            "profile_id": item.profile_id,
            "provider_id": item.provider_id,
            "model_id": item.model_id,
            "temperature": item.temperature,
            "max_tokens": item.max_tokens,
            "json_mode": item.json_mode,
            "retry_count": item.retry_count,
            "retry_backoff_ms": item.retry_backoff_ms,
            "timeout_s": item.timeout_s,
            "prompt_style": item.prompt_style,
            "fallback_profile_ids": list(item.fallback_profile_ids),
        }

    @staticmethod
    def _fallback_provider() -> ProviderSpec:
        return ProviderSpec(provider_id=DEFAULT_PROVIDER_ID, kind="openai_compatible")

    @staticmethod
    def _fallback_model() -> ModelSpec:
        return ModelSpec(model_id=DEFAULT_MODEL_ID, provider_id=DEFAULT_PROVIDER_ID)

    @staticmethod
    def _fallback_profile() -> ExecutionProfile:
        return ExecutionProfile(
            profile_id=DEFAULT_PROFILE_ID,
            provider_id=DEFAULT_PROVIDER_ID,
            model_id=DEFAULT_MODEL_ID,
        )


def _parse_providers(raw: Any) -> dict[str, ProviderSpec]:
    if not isinstance(raw, list):
        return {}
    result: dict[str, ProviderSpec] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        provider_id = _optional_str(item.get("provider_id"))
        if not provider_id:
            continue
        result[provider_id] = ProviderSpec(
            provider_id=provider_id,
            kind=str(item.get("kind", "openai_compatible")),
            base_url=_optional_str(item.get("base_url")),
            api_key_env=_optional_str(item.get("api_key_env")),
            extra_headers=_string_map(item.get("extra_headers")),
            timeout_s=int(item.get("timeout_s", 120)),
        )
    return result


def _parse_models(raw: Any) -> dict[str, ModelSpec]:
    if not isinstance(raw, list):
        return {}
    result: dict[str, ModelSpec] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        model_id = _optional_str(item.get("model_id"))
        if not model_id:
            continue
        tags = item.get("capability_tags") or []
        result[model_id] = ModelSpec(
            model_id=model_id,
            provider_id=str(item.get("provider_id", DEFAULT_PROVIDER_ID)),
            capability_tags=tuple(str(tag) for tag in tags),
            supports_json_mode=bool(item.get("supports_json_mode")),
            max_context=_optional_int(item.get("max_context")),
            cost_hint=_optional_str(item.get("cost_hint")),
        )
    return result


def _parse_profiles(raw: Any) -> dict[str, ExecutionProfile]:
    if not isinstance(raw, list):
        return {}
    result: dict[str, ExecutionProfile] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        profile_id = _optional_str(item.get("profile_id"))
        if not profile_id:
            continue
        result[profile_id] = ExecutionProfile(
            profile_id=profile_id,
            provider_id=str(item.get("provider_id", DEFAULT_PROVIDER_ID)),
            model_id=str(item.get("model_id", DEFAULT_MODEL_ID)),
            temperature=float(item.get("temperature", 0.7)),
            max_tokens=int(item.get("max_tokens", 2000)),
            json_mode=bool(item.get("json_mode", False)),
            retry_count=int(item.get("retry_count", 2)),
            retry_backoff_ms=int(item.get("retry_backoff_ms", 1500)),
            timeout_s=int(item.get("timeout_s", 120)),
            prompt_style=str(item.get("prompt_style", "strict_json")),
            fallback_profile_ids=tuple(_string_list(item.get("fallback_profile_ids"))),
        )
    return result


def _config_path() -> Path:
    raw = getattr(Config, "EXECUTION_CONFIG_PATH", None)
    return Path(raw) if raw else CONFIG_DIR / "execution_config.yaml"


def _env_or_default(env_name: str | None, fallback: str | None) -> str | None:
    if env_name:
        value = os.environ.get(env_name)
        if value:
            return value
    return fallback


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        left = _optional_str(key)
        right = _optional_str(item)
        if left and right:
            result[left] = right
    return result


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [text for item in value if (text := _optional_str(item))]


def _merge_env_provider_presets(
    providers: dict[str, ProviderSpec],
    models: dict[str, ModelSpec],
    profiles: dict[str, ExecutionProfile],
) -> None:
    for preset in _env_provider_presets():
        _merge_env_provider(providers, models, profiles, preset)


def _env_provider_presets() -> list[dict[str, str]]:
    presets = []
    if preset := _env_provider_preset(
        DEFAULT_PROVIDER_ID,
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL_NAME",
    ):
        presets.append(preset)
    seen = {item["provider_id"] for item in presets}
    for suffix in _env_provider_suffixes():
        provider_id = suffix.lower()
        if provider_id in seen:
            continue
        if preset := _env_provider_preset(
            provider_id,
            f"LLM_{suffix}_BASE_URL",
            f"LLM_{suffix}_API_KEY",
            f"LLM_{suffix}_MODEL_NAME",
        ):
            presets.append(preset)
            seen.add(provider_id)
    return presets


def _env_provider_suffixes() -> list[str]:
    suffixes = []
    for name in os.environ:
        if not name.startswith("LLM_") or not name.endswith("_MODEL_NAME"):
            continue
        middle = name[len("LLM_") : -len("_MODEL_NAME")]
        if not middle:
            continue
        if middle in {"BASE", "API", "MODEL"}:
            continue
        suffixes.append(middle)
    return sorted(set(suffixes))


def _env_provider_preset(
    provider_id: str,
    base_env: str,
    key_env: str,
    model_env: str,
) -> dict[str, str] | None:
    base_url = _optional_str(os.environ.get(base_env))
    model_id = _optional_str(os.environ.get(model_env))
    if not model_id:
        return None
    return {
        "provider_id": provider_id,
        "base_url": base_url or Config.LLM_BASE_URL,
        "api_key_env": key_env,
        "model_id": model_id,
    }


def _merge_env_provider(
    providers: dict[str, ProviderSpec],
    models: dict[str, ModelSpec],
    profiles: dict[str, ExecutionProfile],
    preset: Mapping[str, str],
) -> None:
    provider_id = str(preset["provider_id"])
    model_id = str(preset["model_id"])
    current_provider = providers.get(provider_id)
    if current_provider is None:
        providers[provider_id] = ProviderSpec(
            provider_id=provider_id,
            kind="openai_compatible",
            base_url=_optional_str(preset.get("base_url")),
            api_key_env=_optional_str(preset.get("api_key_env")),
        )
    else:
        providers[provider_id] = replace(
            current_provider,
            base_url=current_provider.base_url or _optional_str(preset.get("base_url")),
            api_key_env=current_provider.api_key_env or _optional_str(preset.get("api_key_env")),
        )
    if model_id not in models:
        models[model_id] = ModelSpec(
            model_id=model_id,
            provider_id=provider_id,
            capability_tags=("json",),
            supports_json_mode=True,
        )
    if provider_id != DEFAULT_PROVIDER_ID:
        _clone_default_profiles_for_provider(profiles, provider_id, model_id)


def _clone_default_profiles_for_provider(
    profiles: dict[str, ExecutionProfile],
    provider_id: str,
    model_id: str,
) -> None:
    templates = [
        item
        for item in profiles.values()
        if item.provider_id == DEFAULT_PROVIDER_ID and item.model_id == DEFAULT_MODEL_ID
    ]
    for item in templates:
        profile_id = f"{provider_id}_{item.profile_id}"
        if profile_id in profiles:
            continue
        profiles[profile_id] = replace(
            item,
            profile_id=profile_id,
            provider_id=provider_id,
            model_id=model_id,
        )
