"""Account lifecycle acceptance against an explicitly disposable HTTP/Mongo stack."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
import pytest
import requests
from bson import ObjectId
from tests.security_http_fixtures import security_db, security_users, API_URL, PASSWORD

def post(path, payload=None, headers=None):
    return requests.post(API_URL+'/api'+path,json=payload or {},headers=headers or {},timeout=15)

def me(user):
    return requests.get(API_URL+'/api/auth/me',headers=user['headers'],timeout=15)

def mail_token(db,email,subject):
    mail=db.account_test_mail.find_one({'to':email,'subject':subject},sort=[('created_at',-1)])
    assert mail and mail.get('link')
    return parse_qs(urlparse(mail['link']).query)['token'][0]

@pytest.mark.parametrize('password',['short','lowercase123','UPPERCASEONLY','NoNumbersHere','A1'+'x'*71,'A1'+'é'*36])
def test_registration_enforces_password_policy(password,security_db):
    name='invalid_'+uuid.uuid4().hex[:8]
    response=post('/auth/register',{'username':name,'email':name+'@example.com','password':password})
    assert response.status_code==422,response.text
    assert not security_db.users.find_one({'username':name})

def test_registration_case_collision_and_simultaneous_duplicate(security_users,security_db):
    user=security_users()
    collision=post('/auth/register',{'username':user['username'].upper(),'email':uuid.uuid4().hex+'@example.com','password':PASSWORD})
    assert collision.status_code==400
    assert collision.json()['detail']=='Email or username is already in use'
    name='race_'+uuid.uuid4().hex[:8]
    payload={'username':name,'email':name+'@example.com','password':PASSWORD}
    with ThreadPoolExecutor(2) as pool:
        statuses=list(pool.map(lambda _:post('/auth/register',payload).status_code,range(2)))
    assert sorted(statuses)==[200,400]
    assert security_db.users.count_documents({'email':payload['email']})==1

def test_verification_generated_link_single_use_and_resend_throttle(security_users,security_db):
    user=security_users()
    token=mail_token(security_db,user['email'],'Verify your email')
    assert not me(user).json()['email_verified']
    assert post('/auth/resend-verification',headers=user['headers']).status_code==429
    assert post('/auth/verify-email',{'token':token}).status_code==200
    assert me(user).json()['email_verified']
    assert post('/auth/verify-email',{'token':token}).status_code==400

def test_resend_invalidates_previous_verification_link(security_users,security_db):
    user=security_users();old=mail_token(security_db,user['email'],'Verify your email')
    security_db.users.update_one({'_id':ObjectId(user['id'])},{'$set':{'verification_sent_at':datetime.now(timezone.utc)-timedelta(minutes=2)}})
    assert post('/auth/resend-verification',headers=user['headers']).status_code==200
    new=mail_token(security_db,user['email'],'Verify your email')
    assert new!=old
    assert post('/auth/verify-email',{'token':old}).status_code==400
    assert post('/auth/verify-email',{'token':new}).status_code==200

def test_expired_verification_cannot_change_account(security_users,security_db):
    user=security_users();token=mail_token(security_db,user['email'],'Verify your email')
    security_db.users.update_one({'_id':ObjectId(user['id'])},{'$set':{'verification_expires':datetime.now(timezone.utc)-timedelta(seconds=1)}})
    assert post('/auth/verify-email',{'token':token}).status_code==400
    assert not me(user).json()['email_verified']

def test_email_change_requires_password_and_confirmation(security_users,security_db):
    user=security_users();new='changed_'+uuid.uuid4().hex+'@example.com'
    security_db.users.update_one({'_id':ObjectId(user['id'])},{'$unset':{'verification_sent_at':''}})
    url=API_URL+'/api/users/me/profile'
    for password in (None,'Incorrect123'):
        response=requests.put(url,headers=user['headers'],json={'email':new,'current_password':password},timeout=15)
        assert response.status_code==400,response.text
    response=requests.put(url,headers=user['headers'],json={'email':new,'current_password':PASSWORD},timeout=15)
    assert response.status_code==200,response.text
    assert me(user).json()['email']==user['email']
    assert post('/auth/login',{'email':new,'password':PASSWORD}).status_code==401
    token=mail_token(security_db,new,'Verify your email')
    assert post('/auth/verify-email',{'token':token}).status_code==200
    assert me(user).json()['email']==new
    assert post('/auth/login',{'email':new,'password':PASSWORD}).status_code==200
    assert post('/auth/login',{'email':user['email'],'password':PASSWORD}).status_code==401
    assert security_db.account_test_mail.find_one({'to':user['email'],'subject':'Your account email changed'})

def test_username_change_persists_and_records_history(security_users,security_db):
    user=security_users();name='renamed.'+uuid.uuid4().hex[:10]
    response=requests.put(API_URL+'/api/users/me/profile',headers=user['headers'],json={'username':name},timeout=15)
    assert response.status_code==200,response.text
    assert me(user).json()['username']==name and me(user).json()['name']==name
    assert security_db.account_history.find_one({'user_id':user['id'],'action':'username_change','after':name})
    response=requests.put(API_URL+'/api/users/me/profile',headers=user['headers'],json={'username':name.upper()},timeout=15)
    assert response.status_code==200,response.text

@pytest.mark.parametrize('status',['banned','deleted','deactivated','merged','suspended'])
def test_unavailable_accounts_lose_login_access_and_refresh(status,security_users,security_db):
    user=security_users()
    security_db.users.update_one({'_id':ObjectId(user['id'])},{'$set':{'status':status}})
    assert me(user).status_code==401
    assert post('/auth/refresh',headers={'Authorization':'Bearer '+user['refresh_token']}).status_code==401
    assert post('/auth/login',{'email':user['email'],'password':PASSWORD}).status_code in (401,403)

def test_force_logout_real_endpoint_then_fresh_login(security_users):
    user=security_users();admin=post('/auth/login',{'email':os.environ['ADMIN_EMAIL'],'password':os.environ['ADMIN_PASSWORD']}).json()
    response=post('/admin/platform/users/'+user['id']+'/force-logout',headers={'Authorization':'Bearer '+admin['access_token']})
    assert response.status_code==200,response.text
    assert me(user).status_code==401
    assert post('/auth/refresh',headers={'Authorization':'Bearer '+user['refresh_token']}).status_code==401
    login=post('/auth/login',{'email':user['email'],'password':PASSWORD})
    assert login.status_code==200,login.text
    assert requests.get(API_URL+'/api/auth/me',headers={'Authorization':'Bearer '+login.json()['access_token']},timeout=15).status_code==200
    assert post('/auth/refresh',headers={'Authorization':'Bearer '+login.json()['refresh_token']}).status_code==200

def test_logout_revokes_copied_cookie_tokens(security_users):
    user=security_users()
    with requests.Session() as client:
        login=client.post(API_URL+'/api/auth/login',json={'email':user['email'],'password':PASSWORD},timeout=15).json()
        assert client.post(API_URL+'/api/auth/logout',timeout=15).status_code==200
    assert requests.get(API_URL+'/api/auth/me',headers={'Authorization':'Bearer '+login['access_token']},timeout=15).status_code==401
    assert post('/auth/refresh',headers={'Authorization':'Bearer '+login['refresh_token']}).status_code==401

def test_recovery_link_resets_password_and_revokes_all_credentials(security_users,security_db):
    user=security_users()
    assert post('/auth/forgot-password',{'email':user['email']}).status_code==200
    token=mail_token(security_db,user['email'],'Reset your password')
    password='ChangedPassword2026!'
    assert post('/auth/reset-password',{'token':token,'new_password':'weak'}).status_code==422
    assert post('/auth/reset-password',{'token':token,'new_password':password}).status_code==200
    assert post('/auth/reset-password',{'token':token,'new_password':PASSWORD}).status_code==400
    assert me(user).status_code==401
    assert post('/auth/refresh',headers={'Authorization':'Bearer '+user['refresh_token']}).status_code==401
    assert post('/auth/login',{'email':user['email'],'password':PASSWORD}).status_code==401
    assert post('/auth/login',{'email':user['email'],'password':password}).status_code==200

def test_reset_link_concurrent_replay_and_expiry(security_users,security_db):
    user=security_users();post('/auth/forgot-password',{'email':user['email']})
    token=mail_token(security_db,user['email'],'Reset your password')
    with ThreadPoolExecutor(2) as pool:
        statuses=list(pool.map(lambda _:post('/auth/reset-password',{'token':token,'new_password':'Concurrent2026!'}).status_code,range(2)))
    assert sorted(statuses)==[200,400]
    expired='expired_'+uuid.uuid4().hex
    security_db.password_reset_tokens.insert_one({'token':expired,'user_id':user['id'],'used':False,'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)})
    assert post('/auth/reset-password',{'token':expired,'new_password':'ExpiredReset2026!'}).status_code==400

def test_forgot_password_generic_and_invalid_inputs(security_users):
    user=security_users()
    existing=post('/auth/forgot-password',{'email':user['email']})
    unknown=post('/auth/forgot-password',{'email':uuid.uuid4().hex+'@example.com'})
    throttled=post('/auth/forgot-password',{'email':user['email']})
    assert existing.status_code==unknown.status_code==throttled.status_code==200
    assert existing.json()==unknown.json()==throttled.json()
    assert post('/auth/forgot-password',{'email':'invalid'}).status_code==422
    assert post('/auth/reset-password',{'new_password':'NewPassword123'}).status_code==422

def test_change_password_requires_current_and_revokes_old_session(security_users):
    user=security_users()
    for current,new in [('wrong','NewPassword123'),(PASSWORD,'weak')]:
        assert post('/auth/change-password',{'current_password':current,'new_password':new},user['headers']).status_code in (400,422)
    assert post('/auth/change-password',{'current_password':PASSWORD,'new_password':'NewPassword123'},user['headers']).status_code==200
    assert me(user).status_code==401
    assert post('/auth/login',{'email':user['email'],'password':PASSWORD}).status_code==401
    assert post('/auth/login',{'email':user['email'],'password':'NewPassword123'}).status_code==200

@pytest.mark.parametrize('remember',[True,False])
def test_remember_me_cookie_persistence(remember,security_users):
    user=security_users()
    response=post('/auth/login',{'email':user['email'],'password':PASSWORD,'remember':remember})
    assert response.status_code==200
    for cookie in response.cookies:
        assert (cookie.expires is not None)==remember
    refreshed=post('/auth/refresh',headers={'Authorization':'Bearer '+response.json()['refresh_token']})
    assert refreshed.status_code==200
    assert (refreshed.cookies['access_token'] is not None)
    for cookie in refreshed.cookies:
        assert (cookie.expires is not None)==remember

def test_mobile_logout_revokes_refresh_for_same_session(security_users):
    user=security_users()
    assert post('/auth/logout',headers=user['headers']).status_code==200
    assert post('/auth/refresh',headers={'Authorization':'Bearer '+user['refresh_token']}).status_code==401

def test_admin_reset_delivers_a_working_link(security_users,security_db):
    user=security_users();admin=post('/auth/login',{'email':os.environ['ADMIN_EMAIL'],'password':os.environ['ADMIN_PASSWORD']}).json()
    response=post('/admin/platform/users/'+user['id']+'/reset-password',headers={'Authorization':'Bearer '+admin['access_token']})
    assert response.status_code==200,response.text
    assert response.json()['delivered'] and not response.json()['mocked']
    token=mail_token(security_db,user['email'],'Reset your password')
    assert post('/auth/reset-password',{'token':token,'new_password':'AdminResetPassword2026!'}).status_code==200

@pytest.mark.parametrize('path',['register','login','forgot-password','reset-password','verify-email','change-password'])
def test_malformed_json_object_rejected(path):
    assert requests.post(API_URL+'/api/auth/'+path,json=[],timeout=15).status_code==(401 if path == "change-password" else 422)

def test_deactivate_reactivate_requires_new_login(security_users):
    user=security_users();admin=post('/auth/login',{'email':os.environ['ADMIN_EMAIL'],'password':os.environ['ADMIN_PASSWORD']}).json()
    headers={'Authorization':'Bearer '+admin['access_token']}
    prefix='/admin/platform/users/'+user['id']
    assert post(prefix+'/deactivate',{'reason':'Disposable test'},headers).status_code==200
    assert me(user).status_code==401
    assert post(prefix+'/reactivate',headers=headers).status_code==200
    assert me(user).status_code==401
    assert post('/auth/login',{'email':user['email'],'password':PASSWORD}).status_code==200

def test_force_logout_disconnects_live_socket_and_rejects_reconnect(security_users):
    import socketio
    from threading import Event
    user=security_users();socket=socketio.Client();disconnected=Event()
    socket.on('disconnect',lambda *args:disconnected.set())
    socket.connect(API_URL,auth={'token':user['access_token']},socketio_path='api/socket.io',transports=['polling'])
    try:
        admin=post('/auth/login',{'email':os.environ['ADMIN_EMAIL'],'password':os.environ['ADMIN_PASSWORD']}).json()
        assert post('/admin/platform/users/'+user['id']+'/force-logout',headers={'Authorization':'Bearer '+admin['access_token']}).status_code==200
        assert disconnected.wait(5),'Revoked live connection remained open'
        other=socketio.Client()
        with pytest.raises(socketio.exceptions.ConnectionError):
            other.connect(API_URL,auth={'token':user['access_token']},socketio_path='api/socket.io',transports=['polling'])
    finally:
        socket.disconnect()


def test_revoke_one_session_leaves_other_session_valid(security_users,security_db):
    first=security_users()
    second=post('/auth/login',{'email':first['email'],'password':PASSWORD}).json()
    import jwt
    sid=jwt.decode(first['access_token'],os.environ['JWT_SECRET'],algorithms=['HS256'])['session_id']
    admin=post('/auth/login',{'email':os.environ['ADMIN_EMAIL'],'password':os.environ['ADMIN_PASSWORD']}).json()
    result=post('/admin/platform/users/'+first['id']+'/revoke-session',{'session_id':sid},{'Authorization':'Bearer '+admin['access_token']})
    assert result.status_code==200,result.text
    assert me(first).status_code==401
    assert post('/auth/refresh',headers={'Authorization':'Bearer '+first['refresh_token']}).status_code==401
    assert requests.get(API_URL+'/api/auth/me',headers={'Authorization':'Bearer '+second['access_token']},timeout=15).status_code==200

def test_admin_delete_retains_team_history_and_revokes_account(security_users,security_db):
    user=security_users()
    tid=security_db.teams.insert_one({'owner_id':user['id'],'name':'Disposable historic team','wins':3}).inserted_id
    admin=post('/auth/login',{'email':os.environ['ADMIN_EMAIL'],'password':os.environ['ADMIN_PASSWORD']}).json()
    result=post('/admin/platform/users/'+user['id']+'/delete',{'confirm':True,'reason':'Disposable fixture'},{'Authorization':'Bearer '+admin['access_token']})
    assert result.status_code==200,result.text
    assert me(user).status_code==401
    assert post('/auth/refresh',headers={'Authorization':'Bearer '+user['refresh_token']}).status_code==401
    doc=security_db.users.find_one({'_id':ObjectId(user['id'])})
    assert doc['status']=='deleted' and not doc['is_active']
    assert 'verification_email' not in doc and 'password_hash' not in doc
    assert security_db.teams.find_one({'_id':tid})['wins']==3

def test_admin_username_edit_respects_collision_and_releases_previous_name(security_users):
    user=security_users();other=security_users();admin=post('/auth/login',{'email':os.environ['ADMIN_EMAIL'],'password':os.environ['ADMIN_PASSWORD']}).json()
    headers={'Authorization':'Bearer '+admin['access_token']};path='/admin/platform/users/'+user['id']+'/edit-username'
    assert post(path,{'username':other['username'].upper()},headers).status_code==409
    assert post(path,{'username':'bad name'},headers).status_code==400
    name='admin_'+uuid.uuid4().hex[:10]
    assert post(path,{'username':name},headers).status_code==200
    assert me(user).json()['username']==name
    assert post('/auth/register',{'username':user['username'],'email':uuid.uuid4().hex+'@example.com','password':PASSWORD}).status_code==200


def test_logout_during_impersonation_clears_admin_backup(security_users,security_db):
    user=security_users();security_db.users.update_one({'_id':ObjectId(user['id'])},{'$set':{'is_test_account':True}})
    with requests.Session() as client:
        assert client.post(API_URL+'/api/auth/login',json={'email':os.environ['ADMIN_EMAIL'],'password':os.environ['ADMIN_PASSWORD']},timeout=15).status_code==200
        assert client.post(API_URL+'/api/auth/impersonate-start',json={'target_user_id':user['id']},timeout=15).status_code==200
        assert client.cookies.get('admin_token_backup')
        assert client.post(API_URL+'/api/auth/logout',timeout=15).status_code==200
        assert not client.cookies.get('admin_token_backup')
        assert client.post(API_URL+'/api/auth/impersonate-stop',timeout=15).status_code==400

def test_failed_refresh_clears_revoked_cookies(security_users):
    user=security_users()
    with requests.Session() as client:
        client.cookies.set('access_token',user['access_token']);client.cookies.set('refresh_token','bogus')
        response=client.post(API_URL+'/api/auth/refresh',timeout=15)
        assert response.status_code==401
        assert 'access_token=' in response.headers['Set-Cookie'] and 'refresh_token=' in response.headers['Set-Cookie']
        assert 'Max-Age=0' in response.headers['Set-Cookie']
