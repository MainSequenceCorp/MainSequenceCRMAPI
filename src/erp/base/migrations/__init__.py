"""Independent Base provider; explicit models and uniquely named version table."""

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.base.metatables import MODELS, Base

BaseAlembicVersion = build_alembic_version_metatable(
    class_name="BaseAlembicVersion",
    namespace="erp-base",
    identifier="erp_base.alembic_version",
    schema=None,
    table_name="erp_base__alembic_version",
)
migration = build_metatable_migration_provider(
    package="src.erp.base",
    migration_namespace="erp-base",
    script_location="src.erp.base.migrations:",
    version_location_prefix="src.erp.base.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=BaseAlembicVersion,
    metatable_models=MODELS,
)
