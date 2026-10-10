"""Single-use email verification stored atomically on the account."""
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from services.account_access import require_active
from services.account_mail import send_link

async def issue(db, deps, user, email=None):
    require_active(user)
    now=datetime.now(timezone.utc)
    token=secrets.token_urlsafe(32)
    target=(email or user['email']).lower()
    result=await db.users.update_one({'_id':ObjectId(user['_id']), '$or':[{'verification_sent_at':{'$lt':now-timedelta(minutes=1)}},{'verification_sent_at':{'$exists':False}}]},
        {'$set':{'verification_hash':hashlib.sha256(token.encode()).hexdigest(),'verification_expires':now+timedelta(hours=1),'verification_email':target,'verification_sent_at':now}})
    if not result.modified_count:
        raise HTTPException(429,'Please wait a minute before requesting another verification email')
    await send_link(db,deps,target,'Verify your email','/verify-email',token)

async def complete(db, token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    query={'verification_hash':digest,'verification_expires':{'$gt':datetime.now(timezone.utc)}}
    user=await db.users.find_one(query)
    if not user: raise HTTPException(400,'Invalid or expired verification link')
    require_active(user)
    email=user['verification_email']
    try:
        result=await db.users.update_one({**query,'_id':user['_id']},
            {'$set':{'email':email,'email_verified':True},'$unset':{'verification_hash':'','verification_email':'','verification_expires':''}})
    except DuplicateKeyError:
        raise HTTPException(400,'Email change could not be completed')
    if not result.modified_count: raise HTTPException(400,'Invalid or expired verification link')
    await db.account_history.insert_one({'user_id':str(user['_id']),'action':'verify_email','at':datetime.now(timezone.utc)})
    return user
