"""Account mail uses SendGrid; only disposable E2E stacks capture links."""
import os
from html import escape
from urllib.parse import urlencode
from starlette.concurrency import run_in_threadpool
from datetime import datetime, timezone

async def send_link(db, deps, email, subject, path, token):
    origin=os.environ.get('FRONTEND_URL','http://localhost:3000').rstrip('/')
    link=origin+path+'?'+urlencode({'token':token})
    html=f'<p>{escape(subject)}</p><p><a href="{escape(link,quote=True)}">Continue</a></p>'
    if os.environ.get('E2E_MODE')=='true':
        await db.account_test_mail.insert_one({'to':email,'subject':subject,'link':link,'created_at':datetime.now(timezone.utc)})
        return True
    result=await run_in_threadpool(deps['send_sendgrid_email'],email,subject,html)
    if result.get('status')!='sent':
        deps['logger'].error('Account email could not be delivered')
        return False
    return True


async def send_notice(db,deps,email,subject,text):
    if os.environ.get('E2E_MODE')=='true':
        await db.account_test_mail.insert_one({'to':email,'subject':subject,'text':text,'created_at':datetime.now(timezone.utc)})
        return
    result=await run_in_threadpool(deps['send_sendgrid_email'],email,subject,'<p>'+escape(text)+'</p>')
    if result.get('status')!='sent': deps['logger'].error('Account notice could not be delivered')
