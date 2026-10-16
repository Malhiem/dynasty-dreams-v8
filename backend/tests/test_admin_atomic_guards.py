"""Fault injection and operation identity tests for Admin financial/appeal writes."""
import asyncio
import pytest
from bson import ObjectId
from pymongo.errors import OperationFailure
from fastapi import HTTPException
from routes import admin_user_actions as actions,moderation
from services.admin_mutations import credit,resolve_appeal
from tests.router_test_utils import isolated_router_app

def admin():return {'_id':str(ObjectId()),'role':'admin','permission_tier':'senior_admin','email':'atomic@acceptance.local'}
async def user(c,**values):
 oid=ObjectId();await c.db.users.insert_one({'_id':oid,'email':f'{oid}@acceptance.local','promo_credits_cents':0,**values});return str(oid)

@pytest.mark.asyncio
async def test_same_key_concurrent_retries_have_one_credit_and_one_audit():
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await user(c);path=f'/api/admin/platform/users/{uid}/promo-credit'
  replies=await asyncio.gather(*[c.client.post(path,json={'amount_cents':100,'note':'Same intent'},headers={'Idempotency-Key':'concurrent-retry'}) for _ in range(2)])
  assert [r.status_code for r in replies]==[200,200],[r.text for r in replies]
  assert replies[0].json()==replies[1].json()
  assert (await c.db.users.find_one({'_id':ObjectId(uid)}))['promo_credits_cents']==100
  assert await c.db.admin_user_actions.count_documents({'action':'promo_credit'})==1
  assert await c.db.admin_credit_operations.count_documents({})==1

@pytest.mark.asyncio
async def test_reusing_key_with_changed_input_conflicts_without_second_effect():
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await user(c);path=f'/api/admin/platform/users/{uid}/promo-credit';headers={'Idempotency-Key':'one-intent'}
  assert (await c.client.post(path,json={'amount_cents':100},headers=headers)).status_code==200
  assert (await c.client.post(path,json={'amount_cents':200},headers=headers)).status_code==409
  assert (await c.db.users.find_one({'_id':ObjectId(uid)}))['promo_credits_cents']==100
  assert await c.db.admin_user_actions.count_documents({})==1

@pytest.mark.asyncio
async def test_credit_audit_write_failure_rolls_back_balance_and_operation(monkeypatch):
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await user(c);collection_type=type(c.db.admin_user_actions);original=collection_type.insert_one
  async def fail(collection,*args,**kwargs):
   if collection.name=='admin_user_actions':raise OperationFailure('Injected audit failure')
   return await original(collection,*args,**kwargs)
  monkeypatch.setattr(collection_type,'insert_one',fail)
  path=f'/api/admin/platform/users/{uid}/promo-credit';data={'amount_cents':100};headers={'Idempotency-Key':'fault-retry'}
  assert (await c.client.post(path,json=data,headers=headers)).status_code==503
  assert (await c.db.users.find_one({'_id':ObjectId(uid)}))['promo_credits_cents']==0
  assert await c.db.admin_credit_operations.count_documents({})==0
  monkeypatch.setattr(collection_type,'insert_one',original)
  assert (await c.client.post(path,json=data,headers=headers)).status_code==200
  assert (await c.db.users.find_one({'_id':ObjectId(uid)}))['promo_credits_cents']==100

@pytest.mark.asyncio
async def test_appeal_audit_failure_rolls_back_decision_and_sanction(monkeypatch):
 async with isolated_router_app(moderation,user=admin()) as c:
  uid=await user(c,status='banned');aid=ObjectId();await c.db.user_appeals.insert_one({'_id':aid,'user_id':uid,'status':'open'})
  typ=type(c.db.admin_user_actions);original=typ.insert_one
  async def fail(collection,*args,**kwargs):
   if collection.name=='admin_user_actions':raise OperationFailure('Injected appeal audit failure')
   return await original(collection,*args,**kwargs)
  monkeypatch.setattr(typ,'insert_one',fail)
  assert (await c.client.post(f'/api/admin/platform/appeals/{aid}/resolve',json={'action':'approved'})).status_code==503
  assert (await c.db.user_appeals.find_one({'_id':aid}))['status']=='open'
  assert (await c.db.users.find_one({'_id':ObjectId(uid)}))['status']=='banned'

@pytest.mark.asyncio
async def test_approved_appeal_and_replay_keep_one_consistent_audit():
 async with isolated_router_app(moderation,user=admin()) as c:
  uid=await user(c,status='banned');aid=ObjectId();await c.db.user_appeals.insert_one({'_id':aid,'user_id':uid,'status':'open'})
  path=f'/api/admin/platform/appeals/{aid}/resolve'
  assert (await c.client.post(path,json={'action':'approved','note':'Reviewed'})).status_code==200
  assert (await c.client.post(path,json={'action':'denied'})).status_code in (404,409)
  assert (await c.db.users.find_one({'_id':ObjectId(uid)}))['status']=='active'
  assert (await c.db.user_appeals.find_one({'_id':aid}))['status']=='approved'
  assert await c.db.admin_user_actions.count_documents({'action':'appeal_resolved'})==1

@pytest.mark.asyncio
async def test_currency_mismatch_does_not_relabel_nonzero_balance():
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await user(c,promo_credits_cents=100,promo_currency='usd')
  r=await c.client.post(f'/api/admin/platform/users/{uid}/promo-credit',json={'amount_cents':100,'currency':'cad'})
  assert r.status_code==409
  assert (await c.db.users.find_one({'_id':ObjectId(uid)}))['promo_currency']=='usd'
  assert await c.db.admin_user_actions.count_documents({})==0

@pytest.mark.asyncio
async def test_legacy_null_balance_starts_at_zero():
 async with isolated_router_app(actions,user=admin()) as c:
  uid=await user(c,promo_credits_cents=None)
  r=await c.client.post(f'/api/admin/platform/users/{uid}/promo-credit',json={'amount_cents':100})
  assert r.status_code==200,r.text
  assert r.json()['new_balance_cents']==100
