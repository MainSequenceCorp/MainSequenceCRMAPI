from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.finance.metatables import Base, metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-finance",
    identifier="erp_finance.alembic_version",
    schema=None,
    table_name="erp_finance__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.finance",
    migration_namespace="erp-finance",
    script_location="src.erp.finance.migrations:",
    version_location_prefix="src.erp.finance.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
