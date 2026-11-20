"""Requester's preferences and existing administrator preview operations."""

from pydantic import BaseModel, Field

from api.erp.base.main import service_for as base_service
from src.erp.base.schemas import PreferenceInput
from src.erp.base.service import BaseError

from ..contracts import EmptyInput, Record
from ..owner_routes import OwnerRoutes


class LocaleUpdate(PreferenceInput):
    expected_version: int = Field(ge=0, strict=True)


class LocalePreference(BaseModel):
    preference: Record | None


def _saved(service):
    return next(iter(service.collection("preferences", page_size=1)["items"]), None)


def _locale_get(scope, _args):
    service = base_service(scope.apps["base"], local=scope.local)
    return {"preference": _saved(service)}


def _locale_update(scope, args):
    service = base_service(scope.apps["base"], local=scope.local)
    current = _saved(service)
    if args.expected_version != (current["version"] if current else 0):
        raise BaseError(409, "conflict", "Preferences changed. Read them again before editing.")
    values = {key: current[key] for key in PreferenceInput.model_fields} if current else {}
    values.update(args.model_dump(exclude={"expected_version"}, exclude_unset=True))
    return {
        "preference": service.save(
            "preferences",
            values,
            uid=current["uid"] if current else None,
            expected_version=args.expected_version if current else None,
        )
    }


def register_tools(registry):
    personal = "settings/settings-preferences"
    settings = OwnerRoutes(registry, "user_preferences", personal)
    settings.read(
        "settings_preferences_get", "/user-preferences/", "Read your ERP menu preferences."
    )
    settings.write(
        "settings_preferences_update",
        "PUT",
        "/user-preferences/",
        "Edit your ERP menu preferences with the expected version.",
    )
    registry.read(
        "settings_locale_preferences_get",
        owner="base",
        capabilities=("base.read",),
        skill=personal,
        description="Read your own Business Directory language and timezone preferences.",
        inputs=EmptyInput,
        output=LocalePreference,
        handler=_locale_get,
    )
    registry.operation(
        "settings_locale_preferences_update",
        owner="base",
        capabilities=("base.read",),
        skill=personal,
        description="Save your own language and timezone. Use version zero before your first saved record.",
        inputs=LocaleUpdate,
        output=LocalePreference,
        handler=_locale_update,
        kind="write",
    )

    administration = "settings/settings-administration"
    activation = OwnerRoutes(registry, "user_preferences", administration)
    activation.read(
        "settings_module_activation_get",
        "/modules/",
        "Read the Organization's versioned module activation policy.",
        organization_admin=True,
    )
    activation.preview(
        "settings_module_activation_preview",
        "/modules/preflight/",
        "Review proposed module dependencies and affected features without saving.",
        organization_admin=True,
    )
    configuration = OwnerRoutes(registry, "base", administration)
    for resource in ("operating-companies", "currencies", "languages", "number-sequences"):
        stem, path = "settings_" + resource.replace("-", "_"), f"/{resource}/"
        configuration.read(f"{stem}_list", path, f"Find Base-owned {resource}.", permission="read")
        configuration.read(
            f"{stem}_get",
            path + "{uid}/",
            f"Read one Base record in {resource}.",
            permission="read",
        )
        configuration.write(
            f"{stem}_create",
            "POST",
            path,
            f"Create a Base record in {resource}.",
            permission="configure",
        )
        configuration.write(
            f"{stem}_update",
            "PUT",
            path + "{uid}/",
            f"Edit a Base record in {resource}.",
            permission="configure",
        )
