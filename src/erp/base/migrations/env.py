from metatables.migrations.env import run_mainsequence_alembic_env
from src.erp.base.migrations import migration

run_mainsequence_alembic_env(default_provider=migration)
