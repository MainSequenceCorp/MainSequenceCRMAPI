from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.reporting.metatables import Base
from src.erp.reporting.migrations.registry import metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace='erp-reporting',
    identifier='erp_reporting.alembic_version',
    schema=None,
    table_name='erp_reporting__alembic_version',
)

migration = build_metatable_migration_provider(
    package='src.erp.reporting',
    migration_namespace='erp-reporting',
    script_location="src.erp.reporting.migrations:",
    version_location_prefix="src.erp.reporting.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
