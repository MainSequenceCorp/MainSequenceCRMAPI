"""Email capture on owned disposable PostgreSQL, with no live account or CRM data."""
import base64
import shutil
import subprocess
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from api.erp.crm.main import create_app
from metatables import MetaTableCompiledSQLOperation
from src.erp.crm.emails.gmail import GmailEmails
from src.erp.crm.google_workspace.security import Sealer
from src.erp.crm.metatables import Base, MODELS
from src.erp.crm.repositories.errors import ResourceConflict
from src.erp.crm.repositories.records import VersionedRecordStore
from src.erp.crm.repositories.resources.store import GovernedResourceStore

SOURCE = str(uuid.UUID(int=99001))

@pytest.fixture(scope='module')
def email_postgres():
    if not shutil.which('docker'):
        pytest.skip('Email SQL checks require Docker postgres:17')
    name = 'crm-email-test-' + uuid.uuid4().hex
    def docker(*args):
        return subprocess.run(['docker', *args], check=True, capture_output=True, text=True, timeout=40).stdout.strip()
    try:
        docker('run', '--rm', '-d', '--name', name, '-e', 'POSTGRES_USER=crm_fixture', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-p', '127.0.0.1::5432', 'postgres:17')
        port = int(docker('port', name, '5432/tcp').rsplit(':', 1)[1])
        engine = sa.create_engine(sa.URL.create('postgresql+psycopg', username='crm_fixture', host='127.0.0.1', port=port, database='postgres'), hide_parameters=True)
        deadline = time.monotonic() + 30
        while True:
            try:
                with engine.connect() as db:
                    db.exec_driver_sql('SELECT 1')
                break
            except sa.exc.OperationalError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(.2)
        Base.metadata.create_all(engine)
        yield engine
        engine.dispose()
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=40)

def raw_email(uid='m1', thread='th1', text='Reviewed proposal body', timestamp=1000):
    return {'id': uid, 'threadId': thread, 'internalDate': str(timestamp), 'payload': {
        'mimeType': 'text/plain', 'headers': [{'name': k, 'value': v} for k, v in {
            'From': 'Eric Example <eric@example.com>', 'To': 'Mailbox <owner@example.com>',
            'Subject': 'Proposal', 'Date': 'Tue, 10 Nov 2026 09:00:00 +0100', 'Message-ID': f'<{uid}@example.test>',
        }.items()], 'body': {'data': base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')}}}

@pytest.fixture
def email_api(email_postgres, monkeypatch, signed_caller, config_file):
    def no_network(*args, **kwargs):
        pytest.fail('Email tests must not call platform or external services')
    monkeypatch.setattr('requests.sessions.Session.request', no_network)
    config_file(solution_selling=True, google_workspace=True)
    with email_postgres.connect() as db:
        transaction = db.begin()
        calls, source_calls = [], []
        actor = uuid.uuid4()
        grants = {'crm.read', 'crm.create', 'crm.edit', 'crm.archive', 'crm.transfer.import'}
        def execute(payload):
            MetaTableCompiledSQLOperation.model_validate(payload)
            assert payload['data_source_uid'] == SOURCE
            calls.append(payload)
            return {'rows': [dict(row) for row in db.exec_driver_sql(payload['statement']['sql'], payload['statement']['parameters']).mappings()]}
        monkeypatch.setattr('src.erp.crm.repositories.gateway.MetaTable.execute_operation', execute)
        registry = SimpleNamespace(data_source_uid=SOURCE)
        store = GovernedResourceStore(registry)
        source_uid, grant_uid = uuid.uuid4(), uuid.uuid4()
        now = datetime.now(UTC)
        db.execute(sa.insert(MODELS['source_connection']), {'uid': source_uid, 'created_at': now, 'updated_at': now, 'version': 1,
            'name': 'Disposable Google source', 'adapter_id': 'google-workspace-v1', 'source_account_key': 'fixture', 'configuration': {}})
        grant = {'uid': grant_uid, 'actor_uid': actor, 'source_connection_uid': source_uid, 'google_sub': 'fixture-sub',
                 'display_email': 'owner@example.com', 'granted_scopes': ['https://www.googleapis.com/auth/gmail.readonly'],
                 'refresh_ciphertext': 'fixture-not-a-token', 'status': 'connected', 'version': 1, 'created_at': now, 'updated_at': now}
        db.execute(sa.insert(MODELS['google_oauth_connection']), grant)
        source = {'m1': raw_email()}
        def google(request):
            source_calls.append(request)
            if request.url.path.endswith('/messages'):
                return httpx.Response(200, json={'messages': [{'id': key} for key in source], 'nextPageToken': None})
            if '/threads/' in request.url.path:
                tid = request.url.path.rsplit('/', 1)[1]
                return httpx.Response(200, json={'id': tid, 'messages': [m for m in source.values() if m['threadId'] == tid]})
            return httpx.Response(200, json=source[request.url.path.rsplit('/', 1)[1]])
        class OAuth:
            http = httpx.Client(transport=httpx.MockTransport(google))
            sealer = Sealer(b'e' * 32)
            def access_token(self, user, source_name):
                if user != actor or grant['status'] != 'connected':
                    raise ResourceConflict('Reconnect Google')
                assert source_name == 'gmail'
                return 'fixture-access', grant
        oauth = OAuth()
        monkeypatch.setattr('src.erp.crm.emails.service.configured_google', lambda: oauth)
        app = create_app()
        app.state.crm_policy = SimpleNamespace(capabilities=lambda uid: grants if uid == actor else {'crm.read'})
        app.state.crm_directory = SimpleNamespace(is_selectable=lambda uid: uid == actor)
        app.state.crm_resources = store
        app.state.crm_record_store = VersionedRecordStore(registry)
        app.state.crm_google_service = oauth
        with TestClient(app, headers=signed_caller(actor)) as client:
            yield SimpleNamespace(client=client, db=db, actor=actor, grants=grants, calls=calls, source_calls=source_calls,
                                  source=source, grant=grant, oauth=oauth, store=store)
        transaction.rollback()

def contact(env):
    response = env.client.post('/api/crm/v1/contacts/', json={'first_name': 'Disposable email fixture'})
    assert response.status_code == 201, response.text
    return response.json()['uid']

def import_one(env):
    cid = contact(env)
    preview = env.client.post('/extensions/google/email-previews/', json={'message_id': 'm1', 'contact_uid': cid})
    assert preview.status_code == 200, preview.text
    command = {'preview_token': preview.json()['preview_token'], 'contact_uid': cid, 'audience': 'shared_crm_readers'}
    saved = env.client.post('/extensions/google/email-imports/', json=command)
    assert saved.status_code == 201, saved.text
    return saved.json(), command

def test_manual_history_search_and_body_free_collections(email_api):
    env = email_api
    payload = {'contact_uid': contact(env), 'sender': {'email': 'eric@example.com'}, 'subject': 'Manual log',
               'body_text': 'Durable searchable history', 'sent_at': '2026-11-10T09:00:00Z'}
    response = env.client.post('/api/crm/v1/email-messages/', json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['source'] == 'manual' and not saved['thread']['sync_enabled']
    assert env.client.get(f"/api/crm/v1/email-messages/{saved['uid']}/").json()['body_text'] == payload['body_text']
    listed = env.client.get('/api/crm/v1/email-messages/', params={'search': 'searchable'}).json()
    assert listed['pageInfo']['totalItems'] == 1 and 'body_text' not in listed['items'][0]
    assert env.client.post('/api/crm/v1/email-messages/', json={**payload, 'source': 'gmail'}).status_code == 422
    assert env.client.get('/api/crm/v1/email-messages/discovery/?page_size=10').status_code == 422
    assert env.client.get('/api/crm/v1/email-messages/', params={'filters': '{"actor_uid":"forged"}'}).status_code == 422

def test_search_preview_and_repeat_import_never_enroll_sync(email_api):
    env = email_api
    searched = env.client.post('/extensions/google/email-search/', json={'query': 'from:eric@example.com', 'time_min': '2026-11-01T00:00:00Z', 'time_max': '2026-11-10T00:00:00Z'})
    assert searched.status_code == 200, searched.text
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_thread').scalar_one() == 0
    saved, command = import_one(env)
    assert not saved['thread']['sync_enabled'] and saved['provider_message_id'] == 'm1'
    again = env.client.post('/extensions/google/email-imports/', json=command)
    assert again.status_code == 201, again.text
    assert again.json()['uid'] == saved['uid']
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_message').scalar_one() == 1
    audit = env.db.exec_driver_sql("SELECT changes::text FROM mainsequence_crm__activity_event WHERE kind='email_captured'").scalar_one()
    assert 'proposal body' not in audit
    env.source_calls.clear()
    assert env.client.post(f"/extensions/google/email-threads/{saved['thread_uid']}/sync/", json={}).status_code == 409
    assert not env.source_calls

def test_sync_only_selected_thread_and_new_messages(email_api):
    env = email_api
    saved, _ = import_one(env)
    tid = saved['thread_uid']
    selection = env.client.post(f'/extensions/google/email-threads/{tid}/selection/', json={'expected_version': saved['thread']['version'], 'enabled': True})
    assert selection.status_code == 200, selection.text
    boundary = selection.json()['sync_after_ms']
    env.source.update(m2=raw_email('m2', timestamp=boundary+1000), older=raw_email('older', timestamp=boundary-1), unrelated=raw_email('unrelated', thread='unselected', timestamp=boundary+2000))
    env.source_calls.clear()
    for _ in range(2):
        response = env.client.post(f'/extensions/google/email-threads/{tid}/sync/', json={})
        assert response.status_code == 200, response.text
    assert set(env.db.exec_driver_sql('SELECT provider_message_id FROM mainsequence_crm__email_message').scalars()) == {'m1', 'm2'}
    assert all(request.url.path.endswith(('/threads/th1', '/messages/m2')) for request in env.source_calls)
    assert all(request.url.params.get('format') == 'metadata' for request in env.source_calls if '/threads/' in request.url.path)
    assert not any('/messages/older' in request.url.path or '/messages/unrelated' in request.url.path for request in env.source_calls)
    assert env.client.post(f'/extensions/google/email-threads/{tid}/selection/', json={'expected_version': 1, 'enabled': False}).status_code == 409
    latest = env.client.get(f"/api/crm/v1/email-messages/{saved['uid']}/").json()
    assert env.client.post(f'/extensions/google/email-threads/{tid}/selection/', json={'expected_version': latest['thread']['version'], 'enabled': False}).status_code == 200
    count = len(env.source_calls)
    assert env.client.post(f'/extensions/google/email-threads/{tid}/sync/', json={}).status_code == 409
    assert len(env.source_calls) == count
    env.grants.clear()
    assert env.client.get(f"/api/crm/v1/email-messages/{saved['uid']}/").status_code == 403
    assert env.client.get('/api/crm/v1/email-messages/?search=proposal').status_code == 403

def test_follow_up_reuses_task_and_completion_clears_lead_next_action(email_api):
    env = email_api
    saved, _ = import_one(env)
    response = env.client.post('/extensions/solution-selling/leads/', json={'contact_uid': saved['contact_uid'], 'status': 'contacted'})
    assert response.status_code == 201, response.text
    lead = response.json()
    response = env.client.post(f"/api/crm/v1/email-messages/{saved['uid']}/follow-up/", json={'owner_uid': str(env.actor), 'lead_uid': lead['uid'], 'expected_lead_version': lead['version']})
    assert response.status_code == 201, response.text
    task = response.json()
    assert task['source_email_message_uid'] == saved['uid']
    assert env.client.post(f"/api/crm/v1/email-messages/{saved['uid']}/follow-up/", json={}).json()['uid'] == task['uid']
    current = env.client.get(f"/api/crm/v1/tasks/{task['uid']}/").json()
    assert env.client.post(f"/api/crm/v1/tasks/{task['uid']}/complete/", json={'expected_version': current['version']}).status_code == 200
    lead = env.client.get(f"/extensions/solution-selling/leads/{lead['uid']}/").json()
    assert lead['next_task_uid'] is None and lead['status'] == 'contacted'

def test_audit_failure_rolls_back_conversation_and_message(email_api):
    env = email_api
    uid = contact(env)
    env.db.exec_driver_sql("ALTER TABLE mainsequence_crm__activity_event ADD CONSTRAINT fixture_email_audit_failure CHECK (kind <> 'email_captured')")
    savepoint = env.db.begin_nested()
    with pytest.raises(sa.exc.IntegrityError):
        env.client.post('/api/crm/v1/email-messages/', json={'contact_uid': uid, 'sender': {'email': 'eric@example.com'}, 'subject': 'Rollback', 'body_text': 'private body'})
    savepoint.rollback()
    for table in ('email_message', 'email_thread', 'interaction'):
        assert env.db.exec_driver_sql(f'SELECT count(*) FROM mainsequence_crm__{table}').scalar_one() == 0

def test_html_fallback_is_text_without_active_content():
    raw = raw_email(text="<p>Hello &amp; welcome</p><script>steal()</script><img src='https://tracking.invalid/pixel'>")
    raw['payload']['mimeType'] = 'text/html'
    parsed = GmailEmails(None).parse('unused', raw, {'display_email': 'owner@example.com'})
    assert parsed['body_text'] == 'Hello & welcome'

def test_account_change_permission_revocation_and_commit_selection_fence(email_api):
    env = email_api
    saved, _ = import_one(env)
    tid = saved['thread_uid']
    selection = env.client.post(f'/extensions/google/email-threads/{tid}/selection/', json={'expected_version': 1, 'enabled': True})
    assert selection.status_code == 200
    env.grant['google_sub'] = 'different-account'
    count = len(env.source_calls)
    assert env.client.post(f'/extensions/google/email-threads/{tid}/sync/', json={}).status_code == 409
    assert len(env.source_calls) == count
    env.grant['google_sub'] = 'fixture-sub'
    env.source['m2'] = raw_email('m2', timestamp=selection.json()['sync_after_ms'] + 1000)
    original_get = env.oauth.http.get
    def pause_during_read(*args, **kwargs):
        response = original_get(*args, **kwargs)
        env.db.exec_driver_sql('UPDATE mainsequence_crm__email_thread SET sync_enabled=false, version=version+1 WHERE uid=%s::uuid', (tid,))
        return response
    env.oauth.http.get = pause_during_read
    assert env.client.post(f'/extensions/google/email-threads/{tid}/sync/', json={}).status_code == 409
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_message').scalar_one() == 1
    env.oauth.http.get = original_get
    latest = env.client.get(f"/api/crm/v1/email-messages/{saved['uid']}/").json()['thread']
    assert env.client.post(f'/extensions/google/email-threads/{tid}/selection/', json={'expected_version': latest['version'], 'enabled': True}).status_code == 200
    def revoke_during_read(*args, **kwargs):
        response = original_get(*args, **kwargs)
        env.grants.discard('crm.create')
        return response
    env.oauth.http.get = revoke_during_read
    assert env.client.post(f'/extensions/google/email-threads/{tid}/sync/', json={}).status_code == 403
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_message').scalar_one() == 1


def test_reuse_existing_task_preserves_business_fields_and_rejects_wrong_contact(email_api):
    env = email_api
    saved, _ = import_one(env)
    original = env.client.post('/api/crm/v1/tasks/', json={'contact_uid': saved['contact_uid'], 'text': 'Previously agreed action', 'due_at': '2026-11-15T09:00:00Z'})
    assert original.status_code == 201, original.text
    task = original.json()
    result = env.client.post(f"/api/crm/v1/email-messages/{saved['uid']}/follow-up/", json={'existing_task_uid': task['uid'], 'expected_task_version': task['version'], 'text': 'Must not overwrite', 'due_at': '2027-01-01T00:00:00Z'})
    assert result.status_code == 201, result.text
    assert result.json()['text'] == task['text'] and result.json()['due_at'] == task['due_at']
    assert env.client.patch(f"/api/crm/v1/tasks/{task['uid']}/", json={'expected_version': result.json()['version'], 'changes': {'contact_uid': contact(env)}}).status_code == 409


def test_email_mcp_reads_match_rest_and_forged_actor_is_rejected(email_api, signed_caller):
    from tests.erp.crm.agent.test_mcp_tools import call
    env = email_api
    saved, _ = import_one(env)
    headers = signed_caller(uuid.uuid4(), requester={'sub': str(env.actor), 'is_organization_admin': False})
    result = call(env.client, 'crm_email_messages_get', {'uid': saved['uid']}, headers=headers)
    assert result['isError'] is False, result
    assert result['structuredContent']['data'] == env.client.get(f"/api/crm/v1/email-messages/{saved['uid']}/").json()
    result = call(env.client, 'crm_email_messages_get', {'uid': saved['uid'], 'actor_uid': str(env.actor)}, headers=headers)
    assert result['isError'] is True
    assert result['structuredContent']['code'] == 'invalid_arguments'

def test_additive_provider_migration_and_email_read_in_fresh_process(email_postgres):
    """Apply the actual provider history on a separate private database, then restart the reader."""
    import json
    import sys
    from alembic import command
    from metatables.migrations import alembic_config_for_provider
    from src.crm.migrations import migration
    database = 'crm_email_migration_' + uuid.uuid4().hex
    with email_postgres.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.exec_driver_sql(f'CREATE DATABASE "{database}"')
        engine = sa.create_engine(email_postgres.url.set(database=database), hide_parameters=True)
        try:
            config = alembic_config_for_provider(migration, sqlalchemy_url=engine.url.render_as_string(hide_password=False))
            with engine.connect() as db:
                config.attributes['connection'] = db
                command.upgrade(config, 'head')
                db.commit()
                assert db.exec_driver_sql('SELECT version_num FROM mainsequence_crm__alembic_version').scalar_one() == '0015'
                stamp = datetime.now(UTC)
                cid, iid, tid, mid, actor = (uuid.uuid4() for _ in range(5))
                def version(uid):
                    return dict(uid=uid, version=1, created_at=stamp, updated_at=stamp)
                db.execute(sa.insert(MODELS['contact']), {**version(cid), 'first_name':'Disposable restart fixture', 'emails':[], 'phones':[], 'socials':{}})
                db.execute(sa.insert(MODELS['interaction']), {**version(iid), 'participants':[{'contact_uid':str(cid),'role':'attendee'}], 'subject':'Restart fixture', 'kind':'email', 'status':'completed'})
                db.execute(sa.insert(MODELS['email_thread']), {**version(tid), 'contact_uid':cid, 'interaction_uid':iid, 'actor_uid':actor, 'source_key':'restart-fixture', 'sync_enabled':False})
                db.execute(sa.insert(MODELS['email_message']), {**version(mid), 'thread_uid':tid, 'source_key':'restart-fixture', 'source':'manual', 'sender':{'email':'sender@example.com'}, 'to':[], 'cc':[], 'subject':'Restart fixture', 'body_text':'Persisted body after interpreter restart', 'body_state':'complete'})
                db.commit()
            result = subprocess.run([sys.executable, '-c', '''
import json, sys, sqlalchemy as sa
from src.erp.crm.metatables import MODELS
from src.erp.crm.emails.store import EmailStore
from src.erp.crm.repositories.gateway import MetaTable
from types import SimpleNamespace
engine=sa.create_engine(sys.argv[1])
with engine.connect() as db:
    def execute(payload):
        return {'rows':[dict(row) for row in db.exec_driver_sql(payload['statement']['sql'],payload['statement']['parameters']).mappings()]}
    MetaTable.execute_operation=execute
    row=EmailStore(SimpleNamespace(data_source_uid=sys.argv[3])).detail(sys.argv[2])
    print(json.dumps({'body':row['body_text'],'sync':db.execute(sa.select(MODELS['email_thread'].__table__.c.sync_enabled)).scalar_one()}))
''', engine.url.render_as_string(hide_password=False), str(mid), SOURCE], check=True, capture_output=True, text=True, timeout=30)
            assert json.loads(result.stdout) == {'body':'Persisted body after interpreter restart', 'sync':False}
        finally:
            engine.dispose()
            admin.exec_driver_sql(f'DROP DATABASE "{database}" WITH (FORCE)')


def test_email_wire_collections_and_discovery_match_pinned_sdk(email_api):
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    env = email_api
    import_one(env)
    import os
    frontend = Path(os.environ.get('CRM_FRONTEND_ROOT', str(Path(__file__).resolve().parents[5] / 'main-sequence-crm-5f1b0619-9997-449c-b986-36990ae49e14')))
    root = frontend / 'node_modules/@dev-mainsequence/command-center-sdk/contracts'
    manifest = json.loads((root/'manifest.json').read_text())
    schemas = [json.loads((root/item['file']).read_text()) for item in manifest['schemas']]
    registry = Registry().with_resources((schema['$id'], Resource.from_contents(schema)) for schema in schemas)
    for item, schema in zip(manifest['schemas'], schemas):
        if item['contract'] not in {'command-center.resource_collection@v1','command-center.resource_discovery@v1'}:
            continue
        validator = Draft202012Validator(schema, registry=registry)
        for name in item['fixtures']['valid']:
            validator.validate(json.loads((root/name).read_text()))
        for name in item['fixtures']['invalid']:
            assert list(validator.iter_errors(json.loads((root/name).read_text())))
        path = '/api/crm/v1/email-messages/' + ('discovery/' if 'discovery' in item['contract'] else '')
        response = env.client.get(path)
        assert response.status_code == 200, response.text
        validator.validate(response.json())


def conversation_context(env):
    cid = contact(env)
    lead = env.client.post('/extensions/solution-selling/leads/', json={'contact_uid': cid, 'status': 'contacted'}).json()
    return {'contact_uid': cid, 'lead_uid': lead['uid'], 'expected_lead_version': lead['version']}


def review_conversation(env, context, **extra):
    response = env.client.post('/extensions/google/email-conversation-previews/', json={**context, 'message_id': 'm1', **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_selected_conversation_history_has_explicit_lead_and_shared_reader(email_api, signed_caller):
    import json
    from tests.erp.crm.agent.test_mcp_tools import call
    env = email_api
    env.source.update(m2=raw_email('m2'), m3=raw_email('m3'))
    context = conversation_context(env)
    filters = {'lead_uid': context['lead_uid']}
    assert env.client.get('/api/crm/v1/email-messages/', params={'filters': json.dumps(filters)}).json()['pageInfo']['totalItems'] == 0
    preview = review_conversation(env, context)
    assert len(preview['items']) == 3
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_message').scalar_one() == 0
    command = {**context, 'review_token': preview['review_token'], 'message_ids': ['m1', 'm3'], 'audience': 'shared_crm_readers'}
    result = call(env.client, 'crm_gmail_conversation_import', command, headers=signed_caller(uuid.uuid4(), requester={'sub': str(env.actor), 'is_organization_admin': False}))
    assert not result['isError'], result
    saved = result['structuredContent']['data']
    assert {r['provider_message_id'] for r in saved['items']} == {'m1', 'm3'}
    assert not saved['sync_enabled']
    assert env.client.post('/extensions/google/email-conversation-imports/', json=command).status_code == 201
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_message').scalar_one() == 2
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_lead_link').scalar_one() == 1
    assert env.db.exec_driver_sql('SELECT next_task_uid FROM mainsequence_crm__solution_selling_lead').scalar_one() is None
    reader = signed_caller(uuid.uuid4())
    calls = len(env.source_calls)
    read = env.client.get(f"/api/crm/v1/email-messages/{saved['items'][0]['uid']}/", headers=reader)
    assert read.status_code == 200, read.text
    assert read.json()['body_text'] == 'Reviewed proposal body'
    assert read.json()['lead_uids'] == [context['lead_uid']]
    assert not read.json()['thread']['can_manage_sync']
    listed = env.client.get('/api/crm/v1/email-messages/', params={'filters': json.dumps(filters)}, headers=reader).json()
    assert listed['pageInfo']['totalItems'] == 2 and all('body_text' not in item for item in listed['items'])
    assert env.client.post('/extensions/google/email-conversation-previews/', json={**context, 'message_id': 'm1'}, headers=reader).status_code == 403
    assert env.client.post(f"/extensions/google/email-threads/{saved['thread_uid']}/sync/", json={}, headers=reader).status_code == 403
    assert len(env.source_calls) == calls
    env.grants.clear()
    assert env.client.get('/api/crm/v1/email-messages/', params={'filters': json.dumps(filters)}).status_code == 403
    assert env.client.get(f"/api/crm/v1/email-messages/{saved['items'][0]['uid']}/").status_code == 403
    result = call(env.client, 'crm_email_messages_list', {'filters': filters}, headers=signed_caller(uuid.uuid4(), requester={'sub': str(env.actor), 'is_organization_admin': False}))
    assert result['isError']


def test_conversation_review_fences_selection_context_content_and_audience(email_api):
    env = email_api
    context = conversation_context(env)
    preview = review_conversation(env, context)
    command = {**context, 'review_token': preview['review_token'], 'message_ids': ['m1'], 'audience': 'shared_crm_readers'}
    env.source['new'] = raw_email('new')
    assert env.client.post('/extensions/google/email-conversation-imports/', json={**command, 'message_ids': ['new']}).status_code == 409
    assert env.client.post('/extensions/google/email-conversation-imports/', json={**command, 'audience': 'private'}).status_code == 422
    assert env.client.post('/extensions/google/email-conversation-imports/', json={k:v for k,v in command.items() if k != 'audience'}).status_code == 422
    assert env.client.post('/extensions/google/email-conversation-imports/', json={**command, 'lead_uid': None, 'expected_lead_version': None}).status_code == 409
    env.source['m1'] = raw_email(text='Changed after review')
    assert env.client.post('/extensions/google/email-conversation-imports/', json=command).status_code == 409
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_message').scalar_one() == 0
    preview = review_conversation(env, context)
    env.db.exec_driver_sql('UPDATE mainsequence_crm__solution_selling_lead SET version=version+1 WHERE uid=%s::uuid', (context['lead_uid'],))
    assert env.client.post('/extensions/google/email-conversation-imports/', json={**command, 'review_token': preview['review_token']}).status_code == 409


def test_conversation_review_paging_never_broadens_import(email_api):
    env = email_api
    env.source.update({f'm{i}': raw_email(f'm{i}', timestamp=i*1000) for i in range(2, 28)})
    context = conversation_context(env)
    first = review_conversation(env, context)
    assert len(first['items']) == 25 and first['total_messages'] == 27 and first['next_offset'] == 25
    second = review_conversation(env, context, offset=25)
    assert len(second['items']) == 2 and second['next_offset'] is None
    selected = second['items'][0]['provider_message_id']
    command = {**context, 'review_token': first['review_token'], 'message_ids': [selected], 'audience': 'shared_crm_readers'}
    assert env.client.post('/extensions/google/email-conversation-imports/', json=command).status_code == 409
    command['review_token'] = second['review_token']
    assert env.client.post('/extensions/google/email-conversation-imports/', json=command).status_code == 201
    assert list(env.db.exec_driver_sql('SELECT provider_message_id FROM mainsequence_crm__email_message').scalars()) == [selected]


def test_conversation_batch_and_lead_link_roll_back_when_audit_fails(email_api):
    env = email_api
    env.source['m2'] = raw_email('m2')
    context = conversation_context(env)
    preview = review_conversation(env, context)
    env.db.exec_driver_sql("ALTER TABLE mainsequence_crm__activity_event ADD CONSTRAINT fixture_conversation_audit_failure CHECK (kind <> 'email_captured')")
    savepoint = env.db.begin_nested()
    with pytest.raises(sa.exc.IntegrityError):
        env.client.post('/extensions/google/email-conversation-imports/', json={**context, 'review_token': preview['review_token'], 'message_ids': ['m1', 'm2'], 'audience': 'shared_crm_readers'})
    savepoint.rollback()
    for table in ('email_message', 'email_thread', 'email_lead_link', 'interaction'):
        assert env.db.exec_driver_sql(f'SELECT count(*) FROM mainsequence_crm__{table}').scalar_one() == 0


def test_two_mailbox_owners_keep_separate_sources_and_sync_authority(email_api, signed_caller):
    env = email_api
    context = conversation_context(env)
    first_review = review_conversation(env, context)
    command = {**context, 'review_token': first_review['review_token'], 'message_ids': ['m1'], 'audience': 'shared_crm_readers'}
    first = env.client.post('/extensions/google/email-conversation-imports/', json=command).json()
    second_actor = uuid.uuid4()
    second_grant = {**env.grant, 'uid': uuid.uuid4(), 'actor_uid': second_actor, 'google_sub': 'second-mailbox', 'display_email': 'second@example.com'}
    env.db.execute(sa.insert(MODELS['google_oauth_connection']), second_grant)
    env.client.app.state.crm_policy = SimpleNamespace(capabilities=lambda uid: env.grants)
    owner_access = env.oauth.access_token
    env.oauth.access_token = lambda actor, name: ('fixture-access', second_grant) if actor == second_actor else owner_access(actor, name)
    second_headers = signed_caller(second_actor)
    response = env.client.post('/extensions/google/email-conversation-previews/', json={**context, 'message_id': 'm1'}, headers=second_headers)
    assert response.status_code == 200, response.text
    # First owner's review cannot be used by the second owner even with full CRM permissions.
    assert env.client.post('/extensions/google/email-conversation-imports/', json=command, headers=second_headers).status_code == 409
    second = env.client.post('/extensions/google/email-conversation-imports/', json={**command, 'review_token': response.json()['review_token']}, headers=second_headers)
    assert second.status_code == 201, second.text
    assert second.json()['thread_uid'] != first['thread_uid']
    assert env.db.exec_driver_sql('SELECT count(*) FROM mainsequence_crm__email_message').scalar_one() == 2
    read = env.client.get(f"/api/crm/v1/email-messages/{first['items'][0]['uid']}/", headers=second_headers).json()
    assert read['possible_duplicate'] and not read['thread']['can_manage_sync']
    assert env.client.post(f"/extensions/google/email-threads/{first['thread_uid']}/selection/", json={'expected_version': read['thread']['version'], 'enabled': True}, headers=second_headers).status_code == 403
    assert env.client.post(f"/extensions/google/email-threads/{first['thread_uid']}/sync/", json={}, headers=second_headers).status_code == 403


def test_contact_merge_preserves_conversation_and_explicit_lead_link(email_api):
    env = email_api
    env.grants.add('crm.merge')
    context = conversation_context(env)
    preview = review_conversation(env, context)
    imported = env.client.post('/extensions/google/email-conversation-imports/', json={**context, 'review_token': preview['review_token'], 'message_ids': ['m1'], 'audience': 'shared_crm_readers'}).json()
    survivor = contact(env)
    request = {'loser_uid': context['contact_uid'], 'field_resolutions': {}}
    response = env.client.post(f'/api/crm/v1/contacts/{survivor}/merge/preview/', json=request)
    assert response.status_code == 200, response.text
    plan = response.json()
    response = env.client.post(f'/api/crm/v1/contacts/{survivor}/merge/', json={**request, 'expected_version': plan['survivor_version'], 'loser_expected_version': plan['loser_version'], 'plan_hash': plan['plan_hash']})
    assert response.status_code == 200, response.text
    saved = env.client.get(f"/api/crm/v1/email-messages/{imported['items'][0]['uid']}/").json()
    assert saved['contact_uid'] == survivor and saved['lead_uids'] == [context['lead_uid']]
    lead = env.client.get(f"/extensions/solution-selling/leads/{context['lead_uid']}/").json()
    assert lead['contact_uid'] == survivor


def test_saved_conversation_cannot_change_kind_or_drop_its_contact(email_api):
    env = email_api
    saved, _ = import_one(env)
    uid = saved['interaction_uid']
    existing = env.client.get(f'/api/crm/v1/interactions/{uid}/').json()
    for changes, status in (({'kind': 'call'}, 409), ({'participants': [{'contact_uid': contact(env), 'role': 'attendee'}]}, 409)):
        response = env.client.patch(f'/api/crm/v1/interactions/{uid}/', json={'expected_version': existing['version'], 'changes': changes})
        assert response.status_code == status, response.text
    assert env.client.get(f'/api/crm/v1/interactions/{uid}/').json()['kind'] == 'email'
