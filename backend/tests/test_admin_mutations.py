"""Acceptance probes run only with explicitly configured disposable Mongo."""
import asyncio
from datetime import datetime,timezone,timedelta
import pytest
from bson import ObjectId
from fastapi import HTTPException
from routes import admin_user_actions as actions,moderation,platform_ops,admin_players
from tests.router_test_utils import isolated_router_app

def admin(tier='senior_admin'):
 return {'_id':str(ObjectId()),'email':'expanded-admin@acceptance.local','role':'admin','permission_tier':tier}
async def target(db,**fields):
 oid=ObjectId();await db.users.insert_one({'_id':oid,'email':f'{oid}@acceptance.local','username':f'expanded{str(oid)[-10:]}','status':'active','is_active':True,**fields});return str(oid)

@pytest.mark.parametrize('offset,allowed',[(-1,True),(0,True),(1,False)])
def test_GAP02_suspension_exact_expiry_boundary(monkeypatch,offset,allowed):
 import services.account_access as access
 clock=datetime(2026,10,16,12,tzinfo=timezone.utc)
 class Frozen(datetime):
  @classmethod
  def now(cls,tz=None):return clock
 monkeypatch.setattr(access,'datetime',Frozen)
 user={'status':'suspended','ban_expires_at':(clock+timedelta(seconds=offset)).isoformat()}
 if allowed:access.require_active(user)
 else:
  with pytest.raises(HTTPException) as error:access.require_active(user)
  assert error.value.status_code==401

@pytest.mark.asyncio
@pytest.mark.parametrize('tier,action,payload,expected',[
 ('moderator','warning',{'reason':'fixture'},200),
 ('moderator','suspend',{'duration_days':1,'reason':'fixture'},403),
 ('admin','ban-permanent',{'confirm':True,'reason':'fixture'},403),
 ('admin','permission-tier',{'tier':'senior_admin','reason':'fixture'},403),
 ('senior_admin','ban-permanent',{'confirm':True,'reason':'fixture'},200)])
async def test_GAP01_account_tier_action_matrix(tier,action,payload,expected):
 async with isolated_router_app(actions,user=admin(tier)) as c:
  uid=await target(c.db);before=await c.db.users.find_one({'_id':ObjectId(uid)})
  r=await c.client.post(f'/api/admin/platform/users/{uid}/{action}',json=payload)
  assert r.status_code==expected,r.text
  if expected==403:
   assert await c.db.users.find_one({'_id':ObjectId(uid)})==before
   assert await c.db.admin_user_actions.count_documents({})==0

@pytest.mark.asyncio
@pytest.mark.parametrize('payload',[{'duration_days':1,'reason':''},{'duration_days':1,'reason':'   '},{'duration_days':'not-a-number','reason':'fixture'}])
async def test_GAP02_invalid_suspension_is_rejected_without_write(payload):
 async with isolated_router_app(actions,user=admin()) as c:
  c.client._transport.raise_app_exceptions=False
  uid=await target(c.db);before=await c.db.users.find_one({'_id':ObjectId(uid)})
  r=await c.client.post(f'/api/admin/platform/users/{uid}/suspend',json=payload)
  assert r.status_code in (400,422),f'Invalid required input accepted: {r.status_code} {r.text}'
  assert await c.db.users.find_one({'_id':ObjectId(uid)})==before
  assert await c.db.admin_user_actions.count_documents({})==0

@pytest.mark.asyncio
async def test_GAP01_permission_tier_requires_reason():
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await target(c.db);r=await c.client.post(f'/api/admin/platform/users/{uid}/permission-tier',json={'tier':'admin','reason':''})
  assert r.status_code in (400,422),f'Tier changed without required reason: {r.status_code}'
  assert not (await c.db.users.find_one({'_id':ObjectId(uid)})).get('permission_tier')

@pytest.mark.asyncio
async def test_GAP07_sso_unlink_only_selected_provider_and_audits():
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await target(c.db,linked_sso_accounts=[{'provider':'google','subject':'fixture-google'},{'provider':'apple','subject':'fixture-apple'}],password_hash='fixture-fallback-hash')
  other=await target(c.db,linked_sso_accounts=['google']);control=await c.db.users.find_one({'_id':ObjectId(other)})
  r=await c.client.post(f'/api/admin/platform/users/{uid}/unlink-sso',json={'provider':'google'})
  assert r.status_code==200,r.text
  doc=await c.db.users.find_one({'_id':ObjectId(uid)})
  assert doc['linked_sso_accounts']==[{'provider':'apple','subject':'fixture-apple'}]
  assert doc['password_hash']=='fixture-fallback-hash'
  assert await c.db.users.find_one({'_id':ObjectId(other)})==control
  assert await c.db.admin_user_actions.count_documents({'action':'unlink_sso','target_user_id':uid})==1

@pytest.mark.asyncio
async def test_GAP07_real_merge_transfers_ownership_and_repeat_is_idempotent():
 async with isolated_router_app(actions,user=admin()) as c:
  source=await target(c.db,promo_credits_cents=100);dest=await target(c.db,promo_credits_cents=50)
  tid=ObjectId();await c.db.teams.insert_one({'_id':tid,'owner_id':source,'wins':0,'roster':[]})
  path=f'/api/admin/platform/users/{dest}/merge-accounts'
  r=await c.client.post(path,json={'source_user_id':source,'reason':'Synthetic identity merge'})
  assert r.status_code==200,r.text
  assert not r.json().get('mocked'),r.text
  assert (await c.db.teams.find_one({'_id':tid}))['owner_id']==dest
  assert (await c.db.users.find_one({'_id':ObjectId(dest)}))['promo_credits_cents']==150
  repeat=await c.client.post(path,json={'source_user_id':source,'reason':'Retry'})
  assert repeat.status_code==200 and repeat.json().get('already_merged')
  assert (await c.db.users.find_one({'_id':ObjectId(dest)}))['promo_credits_cents']==150

@pytest.mark.asyncio
async def test_GAP04_concurrent_promo_credits_cannot_lose_one_update(monkeypatch):
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await target(c.db,promo_credits_cents=0);original=actions._load_user;ready=asyncio.Event();arrivals=0
  async def load(user_id):
   nonlocal arrivals
   doc=await original(user_id);arrivals+=1
   if arrivals==2:ready.set()
   await asyncio.wait_for(ready.wait(),5);return doc
  monkeypatch.setattr(actions,'_load_user',load)
  responses=await asyncio.gather(*[c.client.post(f'/api/admin/platform/users/{uid}/promo-credit',json={'amount_cents':100,'note':f'Independent credit {i}'}) for i in range(2)])
  assert all(r.status_code==200 for r in responses)
  balance=(await c.db.users.find_one({'_id':ObjectId(uid)}))['promo_credits_cents']
  assert balance==200,f'Two successful independent credits should total 200; actual={balance}'

@pytest.mark.asyncio
async def test_GAP04_same_credit_retry_key_cannot_apply_twice():
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await target(c.db,promo_credits_cents=0);path=f'/api/admin/platform/users/{uid}/promo-credit'
  for _ in range(2):
   r=await c.client.post(path,json={'amount_cents':100,'note':'Same operation retried'},headers={'Idempotency-Key':'expanded-credit-operation-1'})
   assert r.status_code in (200,201,409),r.text
  balance=(await c.db.users.find_one({'_id':ObjectId(uid)}))['promo_credits_cents']
  assert balance==100,f'Same operation retried credited twice; actual={balance}'

@pytest.mark.asyncio
async def test_GAP04_opposing_appeal_decisions_have_one_winner(monkeypatch):
 async with isolated_router_app(moderation,user=admin()) as c:
  uid=await target(c.db,status='banned');aid=ObjectId()
  await c.db.user_appeals.insert_one({'_id':aid,'user_id':uid,'status':'open'})
  collection_type=type(c.db.user_appeals);original=collection_type.find_one;ready=asyncio.Event();arrivals=0
  async def find(collection,query,*args,**kwargs):
   nonlocal arrivals
   doc=await original(collection,query,*args,**kwargs)
   if collection.name=='user_appeals' and query.get('status')=='open':
    arrivals+=1
    if arrivals==2:ready.set()
    await asyncio.wait_for(ready.wait(),5)
   return doc
  monkeypatch.setattr(collection_type,'find_one',find)
  path=f'/api/admin/platform/appeals/{aid}/resolve'
  replies=await asyncio.gather(c.client.post(path,json={'action':'approved','note':'A'}),c.client.post(path,json={'action':'denied','note':'B'}))
  codes=[r.status_code for r in replies]
  assert sum(x==200 for x in codes)==1,f'Conflicting decisions both succeeded: {codes}'

@pytest.mark.asyncio
async def test_GAP05_notes_do_not_cross_target_and_wrong_target_delete_is_denied():
 async with isolated_router_app(platform_ops,user=admin()) as c:
  a,b=await target(c.db),await target(c.db)
  r=await c.client.post(f'/api/admin/platform/users/{a}/mod-notes',json={'body':'<script>inert fixture</script>','category':'general'})
  assert r.status_code==200,r.text
  note=r.json()['note_id']
  other=await c.client.get(f'/api/admin/platform/users/{b}/mod-notes');assert other.json()['notes']==[]
  delete=await c.client.delete(f'/api/admin/platform/users/{b}/mod-notes/{note}')
  assert delete.status_code in (403,404),f'Wrong target delete not rejected: {delete.status_code}'
  assert await c.db.user_mod_notes.count_documents({'_id':ObjectId(note),'user_id':a})==1

@pytest.mark.asyncio
async def test_GAP10_unknown_csv_and_sync_tokens_do_not_mutate_players():
 async with isolated_router_app(admin_players,user=admin()) as c:
  pid=ObjectId();await c.db.players.insert_one({'_id':pid,'name':'Expanded control','nhl_id':'expanded-control'})
  before=await c.db.players.find_one({'_id':pid})
  for path,data in [('/api/admin/players/csv/commit',{'preview_token':'unknown-expanded-token'}),('/api/admin/players/sync/apply',{'sync_token':'unknown-expanded-token'})]:
   r=await c.client.post(path,json=data);assert r.status_code in (400,404,409,410),r.text
   assert await c.db.players.find_one({'_id':pid})==before
