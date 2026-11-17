from __future__ import annotations

from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from src.erp.people.metatables import Base, metatable_provider_models

CodeRepositoryAlembicVersion = build_alembic_version_metatable(
    class_name="CodeRepositoryAlembicVersion",
    namespace="erp-people",
    identifier="src.erp.people.alembic_version",
    schema="public",
    table_name="erp_people__alembic_version",
)

migration = build_metatable_migration_provider(
    package="src.erp.people",
    migration_namespace="erp-people",
    script_location="src.erp.people.migrations:",
    version_location_prefix="src.erp.people.migrations:versions",
    target_metadata=Base.metadata,
    alembic_registry=CodeRepositoryAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["CodeRepositoryAlembicVersion", "migration"]
