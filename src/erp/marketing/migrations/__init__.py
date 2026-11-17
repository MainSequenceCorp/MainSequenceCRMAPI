from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.marketing.metatables import Base, metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-marketing",
    identifier="erp_marketing.alembic_version",
    schema=None,
    table_name="erp_marketing__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.marketing",
    migration_namespace="erp-marketing",
    script_location="src.erp.marketing.migrations:",
    version_location_prefix="src.erp.marketing.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
