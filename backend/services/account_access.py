"""Shared account status and credential revocation policy."""
from datetime import datetime, timezone
from fastapi import HTTPException
from utils.refresh_tokens import predates_password_change

def require_active(user):
    if not user or user.get('is_active') is False or user.get('status', 'active') in ('banned','deleted','deactivated','merged'):
        raise HTTPException(401, 'Account unavailable')
    if user.get('status') == 'suspended':
        expiry = user.get('ban_expires_at')
        try:
            until = expiry if isinstance(expiry, datetime) else datetime.fromisoformat(str(expiry).replace('Z','+00:00'))
            if until.tzinfo is None: until = until.replace(tzinfo=timezone.utc)
            if until <= datetime.now(timezone.utc): return
        except (ValueError, TypeError): pass
        raise HTTPException(401, 'Account unavailable')

def require_session(user, payload):
    require_active(user)
    if int(payload.get('token_version',0)) != int(user.get('token_version') or 0) or predates_password_change(payload.get('iat'),user.get('password_changed_at')):
        raise HTTPException(401, 'Session revoked — please sign in again')

def validate_password(value):
    if len(value)<8 or not any(c.isupper() and c.isascii() for c in value) or not any(c.isdigit() and c.isascii() for c in value):
        raise ValueError('Password must contain at least 8 characters, one uppercase letter and one number')
    if len(value.encode('utf-8'))>72:
        raise ValueError('Password must be at most 72 UTF-8 bytes')
    return value


async def disconnect_sessions(deps, user_id, session_id=None):
    sio=deps.get('sio')
    if sio is None: return
    for sid,_ in list(sio.manager.get_participants('/',None)):
        try:
            session=await sio.get_session(sid)
            if session.get('user_id')==str(user_id) and (session_id is None or session.get('claims',{}).get('session_id')==session_id):
                await sio.disconnect(sid)
        except KeyError:
            continue
