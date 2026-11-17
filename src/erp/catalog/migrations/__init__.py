from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.catalog.metatables import Base
from src.erp.catalog.migrations.registry import metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-catalog",
    identifier="erp_catalog.alembic_version",
    schema=None,
    table_name="erp_catalog__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.catalog",
    migration_namespace="erp-catalog",
    script_location="src.erp.catalog.migrations:",
    version_location_prefix="src.erp.catalog.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
