import pytest
from datetime import datetime,timezone,timedelta
from bson import ObjectId
from routes import analytics_ux,db_hygiene,admin_players
from tests.router_test_utils import isolated_router_app

def admin():return {'_id':str(ObjectId()),'email':'expanded-data@acceptance.local','role':'admin','permission_tier':'senior_admin'}
def freeze(monkeypatch):
 clock=datetime(2026,10,16,12,tzinfo=timezone.utc)
 class Frozen(datetime):
  @classmethod
  def now(cls,tz=None):return clock
 monkeypatch.setattr(analytics_ux,'datetime',Frozen);return clock

@pytest.mark.asyncio
async def test_GAP06_pageviews_inclusive_window_and_dau_oracle(monkeypatch):
 now=freeze(monkeypatch);cut=now-timedelta(days=7)
 async with isolated_router_app(analytics_ux,user=admin()) as c:
  await c.db.analytics_pageviews.insert_many([
   {'path':'/a','user_id':'a','ts':(cut-timedelta(microseconds=1)).isoformat()},
   {'path':'/a','user_id':'a','ts':cut.isoformat()},
   {'path':'/a','user_id':'b','ts':(cut+timedelta(microseconds=1)).isoformat()},
   {'path':'/b','user_id':None,'ts':now.isoformat()}])
  r=await c.client.get('/api/analytics-ux/pageviews-summary?days=7');assert r.status_code==200,r.text
  d=r.json();assert d['total_views']==3
  assert {p['path']:p['views'] for p in d['top_paths']}=={'/a':2,'/b':1}
  assert d['dau_series']==[{'day':cut.date().isoformat(),'dau':2}]

@pytest.mark.asyncio
async def test_GAP06_adoption_numerator_uses_same_nonadmin_population_as_denominator(monkeypatch):
 now=freeze(monkeypatch)
 async with isolated_router_app(analytics_ux,user=admin()) as c:
  a,b,owner=ObjectId(),ObjectId(),ObjectId()
  await c.db.users.insert_many([{'_id':a,'role':'user'},{'_id':b,'role':'user'},{'_id':owner,'role':'admin'}])
  await c.db.analytics_pageviews.insert_many([{'path':'/trade-analyzer','user_id':str(uid),'ts':now.isoformat()} for uid in (a,owner)])
  await c.db.analytics_events.insert_many([{'event_name':'trade_analyzer_run','user_id':uid,'ts':now.isoformat()} for uid in [str(a),str(a),str(owner),None]])
  r=await c.client.get('/api/analytics-ux/feature-adoption?days=30');assert r.status_code==200,r.text
  d=r.json();assert d['total_users']==2
  f=next(x for x in d['features'] if x['feature']=='trade_analyzer')
  assert (f['discovered'],f['used'],f['returned'],f['discovered_pct'],f['used_pct'])==(1,1,1,50.0,50.0),f

@pytest.mark.asyncio
async def test_GAP06_onboarding_counts_native_registration_datetime_records(monkeypatch):
 now=freeze(monkeypatch)
 async with isolated_router_app(analytics_ux,user=admin()) as c:
  a,b=ObjectId(),ObjectId()
  await c.db.users.insert_many([{'_id':a,'role':'user','created_at':now-timedelta(days=1),'email_verified':True,'avatar_url':'fixture-avatar'}, {'_id':b,'role':'user','created_at':now-timedelta(days=1)}])
  await c.db.teams.insert_one({'owner_id':str(a),'lineup':{'player-fixture':{'slot':'C'}}})
  r=await c.client.get('/api/analytics-ux/onboarding-funnel?days=60');assert r.status_code==200,r.text
  d=r.json();assert d['total_new_users']==2,f'Expected 2 recently registered users stored in native registration timestamp format: {d}'
  assert [x['users'] for x in d['stages']]==[2,1,1,1,1]

@pytest.mark.asyncio
async def test_GAP06_cadence_independent_session_count_oracle(monkeypatch):
 now=freeze(monkeypatch)
 async with isolated_router_app(analytics_ux,user=admin()) as c:
  await c.db.analytics_pageviews.insert_many([{'user_id':uid,'path':'/fixture','ts':(now-timedelta(minutes=minutes)).isoformat()} for uid,minutes in [('a',100),('a',90),('b',80),('b',20)]])
  r=await c.client.get('/api/analytics-ux/engagement-cadence?days=7');assert r.status_code==200,r.text
  assert r.json()['active_user_count']==2
  assert r.json()['median_sessions_per_user_per_week']==1.5
  assert r.json()['median_session_length_seconds']==0.0

@pytest.mark.asyncio
async def test_GAP11_hygiene_report_read_only_sweep_keeps_legitimate_near_match_controls():
 async with isolated_router_app(db_hygiene,user=admin()) as c:
  uid,lid,tid,pid,did=[ObjectId() for _ in range(5)]
  await c.db.users.insert_one({'_id':uid,'email':'legitimate@acceptance.local','_test_seed':False})
  await c.db.leagues.insert_one({'_id':lid,'name':'Testimonial Hockey Club','commissioner_id':str(uid),'_test_seed':False})
  await c.db.teams.insert_one({'_id':tid,'name':'Control Team','league_id':str(lid),'owner_id':str(uid),'_test_seed':False})
  await c.db.players.insert_one({'_id':pid,'name':'Waiver Friendly','nhl_id':'expanded-near-match','_test_seed':False})
  await c.db.drafts.insert_one({'_id':did,'league_id':str(lid),'status':'active','team_abbrs':['CTR'],'_test_seed':False})
  suspect=ObjectId();await c.db.players.insert_one({'_id':suspect,'name':'ForceP-expanded-suspect','_test_seed':True})
  before={name:await c.db[name].find_one({'_id':oid}) for name,oid in [('users',uid),('leagues',lid),('teams',tid),('players',pid),('drafts',did)]}
  r=await c.client.get('/api/admin/db-hygiene/report');assert r.status_code==200,r.text
  assert await c.db.players.find_one({'_id':suspect}), 'Report deleted a suspect'
  for name,doc in before.items():assert await c.db[name].find_one({'_id':doc['_id']})==doc
  r=await c.client.post('/api/admin/db-hygiene/sweep',json={});assert r.status_code==200,r.text
  assert not await c.db.players.find_one({'_id':suspect})
  for name,doc in before.items():assert await c.db[name].find_one({'_id':doc['_id']})==doc,f'Legitimate {name} control changed'
  again=await c.client.post('/api/admin/db-hygiene/sweep',json={});assert again.status_code==200,again.text
  for name,doc in before.items():assert await c.db[name].find_one({'_id':doc['_id']})==doc

@pytest.mark.asyncio
async def test_GAP10_csv_preview_selection_and_consumed_token_replay():
 async with isolated_router_app(admin_players,user=admin()) as c:
  csv='nhl_id,name,position,team\nexpanded-unique-101,Expanded One,C,TOR\nexpanded-unique-102,Expanded Two,D,BOS\n'
  before=await c.db.players.count_documents({})
  p=await c.client.post('/api/admin/players/csv/preview',files={'file':('fixture.csv',csv,'text/csv')});assert p.status_code==200,p.text
  d=p.json();assert await c.db.players.count_documents({})==before
  r=await c.client.post('/api/admin/players/csv/commit',json={'preview_token':d['preview_token'],'apply_indices':[0]});assert r.status_code==200,r.text
  assert await c.db.players.count_documents({})==1
  assert await c.db.players.find_one({'name':'Expanded One'})
  assert not await c.db.players.find_one({'name':'Expanded Two'})
  repeat=await c.client.post('/api/admin/players/csv/commit',json={'preview_token':d['preview_token'],'apply_indices':[1]})
  assert repeat.status_code==410,repeat.text
  assert await c.db.players.count_documents({})==1
