from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.inventory.metatables import Base, metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-inventory",
    identifier="erp_inventory.alembic_version",
    schema=None,
    table_name="erp_inventory__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.inventory",
    migration_namespace="erp-inventory",
    script_location="src.erp.inventory.migrations:",
    version_location_prefix="src.erp.inventory.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
