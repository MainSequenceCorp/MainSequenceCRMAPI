from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.manufacturing.metatables import Base
from src.erp.manufacturing.migrations.registry import metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-manufacturing",
    identifier="erp_manufacturing.alembic_version",
    schema=None,
    table_name="erp_manufacturing__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.manufacturing",
    migration_namespace="erp-manufacturing",
    script_location="src.erp.manufacturing.migrations:",
    version_location_prefix="src.erp.manufacturing.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
