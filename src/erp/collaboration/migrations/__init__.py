from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.collaboration.metatables import Base, metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-collaboration",
    identifier="erp_collaboration.alembic_version",
    schema=None,
    table_name="erp_collaboration__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.collaboration",
    migration_namespace="erp-collaboration",
    script_location="src.erp.collaboration.migrations:",
    version_location_prefix="src.erp.collaboration.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
