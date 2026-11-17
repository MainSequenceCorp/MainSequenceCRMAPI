from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.commerce.metatables import Base
from src.erp.commerce.migrations.registry import metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace='erp-commerce',
    identifier='erp_commerce.alembic_version',
    schema=None,
    table_name='erp_commerce__alembic_version',
)

migration = build_metatable_migration_provider(
    package='src.erp.commerce',
    migration_namespace='erp-commerce',
    script_location="src.erp.commerce.migrations:",
    version_location_prefix="src.erp.commerce.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
