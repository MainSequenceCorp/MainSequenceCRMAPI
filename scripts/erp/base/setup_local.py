"""Apply Base's migrations and starter records to verified local MetaTables only."""

from api.erp.base.identity import ALL_CAPABILITIES
from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.seed import seed
from src.erp.base.service import Service
from src.erp.base.store import Store, require_local_runtime

if __name__ == "__main__":
    configure_local_client()
    print("Verified local DataSource:", require_local_runtime())
    upgrade_application("src.erp.base.migrations:migration")
    user = User.get_authenticated_user_details()
    print(
        "Starter records added:", seed(Service(Store(local_only=True), user.uid, ALL_CAPABILITIES))
    )
