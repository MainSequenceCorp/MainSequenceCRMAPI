from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.purchasing.metatables import Base
from src.erp.purchasing.migrations.registry import metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-purchasing",
    identifier="erp_purchasing.alembic_version",
    schema=None,
    table_name="erp_purchasing__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.purchasing",
    migration_namespace="erp-purchasing",
    script_location="src.erp.purchasing.migrations:",
    version_location_prefix="src.erp.purchasing.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
