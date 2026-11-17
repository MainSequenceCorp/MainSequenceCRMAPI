from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.sales.metatables import Base
from src.erp.sales.migrations.registry import metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-sales",
    identifier="erp_sales.alembic_version",
    schema=None,
    table_name="erp_sales__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.sales",
    migration_namespace="erp-sales",
    script_location="src.erp.sales.migrations:",
    version_location_prefix="src.erp.sales.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
