from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.projects.metatables import Base, metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-projects",
    identifier="erp_projects.alembic_version",
    schema=None,
    table_name="erp_projects__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.projects",
    migration_namespace="erp-projects",
    script_location="src.erp.projects.migrations:",
    version_location_prefix="src.erp.projects.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
