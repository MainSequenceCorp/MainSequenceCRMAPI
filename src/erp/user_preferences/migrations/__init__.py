from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
    build_metatable_model_registry,
)
from src.erp.user_preferences.metatables import MODELS, OWNER_NAMESPACE, Base

package = "src.erp.user_preferences"
namespace = OWNER_NAMESPACE
CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace=namespace,
    identifier="erp_user_preferences.alembic_version",
    schema=None,
    table_name="erp_user_preferences__alembic_version",
)
migration = build_metatable_migration_provider(
    package=package,
    migration_namespace=namespace,
    script_location=f"{package}.migrations:",
    version_location_prefix=f"{package}.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=build_metatable_model_registry(list(MODELS), base=Base),
)
