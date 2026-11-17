"""Run the real Reporting UI and local worker with tracked disposable owner fixtures."""
import argparse
import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from sqlalchemy import update
from tests.erp.commerce.conftest import commerce
from tests.erp.reporting.conftest import reporting
from tests.erp.reporting.test_local_reporting import commercial
from tests.erp.sales.conftest import business, services

from src.erp.reporting.metatables import Run
from src.erp.reporting.service import now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--frontend', type=Path, required=True)
    args = parser.parse_args()
    generators = []
    f = None
    try:
        parent = business.__wrapped__(services.__wrapped__())
        f = next(parent)
        generators.append(parent)
        child = commerce.__wrapped__(f)
        f = next(child)
        generators.append(child)
        child = reporting.__wrapped__(f)
        f = next(child)
        generators.append(child)
        checkout = commercial(f)
        s = f['reporting']
        # Persist real failure/recovery fixtures through the owned service; no browser mocks.
        failed = f['queue_report']()
        factory = s.sources.factories.pop('sales')
        failed = s.advance(failed['uid'], failed['version'])
        s.sources.factories['sales'] = factory
        interrupted = f['queue_report']()
        claimed, _ = s.claim(interrupted['uid'], interrupted['version'])
        s.store.write([update(Run).where(Run.uid == UUID(claimed['uid'])).values(lease_until=now()-timedelta(seconds=1))])
        fixture = {'customer':f['base'].get('parties',f['payload']['customer_uid']), 'checkout':checkout, 'failed':failed, 'interrupted':claimed}
        with TemporaryDirectory(prefix='reporting-browser-') as directory:
            path, owned = Path(directory)/'fixture.json', Path(directory)/'owned.json'
            path.write_text(json.dumps(fixture,default=str))
            owned.write_text('[]')
            try:
                subprocess.run(['node','tests/erp/reporting/browser/reporting.browser.mjs'],cwd=args.frontend,env={**os.environ,'REPORTING_BROWSER_FIXTURE':str(path),'REPORTING_BROWSER_OWNED':str(owned),'REPORTING_API_CHECKOUT':str(Path.cwd())},check=True)
            finally:
                for kind,uid in json.loads(owned.read_text()):
                    f['reporting_owned'][kind].append(UUID(uid))
    finally:
        for generator in reversed(generators):
            try:
                next(generator)
            except StopIteration:
                pass


if __name__ == '__main__':
    main()
