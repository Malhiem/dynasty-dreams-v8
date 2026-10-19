import {test,expect} from '@playwright/test';
import {actors,dispose,league} from '../support/access-history';
import {database,result} from '../support/h2h';
import {MobileExperiencePage} from '../pages/mobile-experience/mobile-experience.page';

test('concurrent chat retries persist one message and reject reused IDs with new content',async()=>{
 const a=await actors();try{
  const l=await league(a);const channels=await result(await a.manager.api.get(`/api/chat/channels?league_id=${l.id}`));
  const c=channels.channels.find((c:any)=>c.kind==='channel');const url=`/api/chat/channels/${c._id}/messages`;
  const data={content:`Idempotent ${crypto.randomUUID()}`,client_message_id:crypto.randomUUID()};
  const responses=await Promise.all([a.manager.api.post(url,{data}),a.manager.api.post(url,{data})]);
  for(const response of responses)expect(response.ok(),await response.text()).toBeTruthy();
  const rows=await Promise.all(responses.map(response=>result(response)));expect(rows[0]._id).toBe(rows[1]._id);
  expect(await database(db=>db.collection('chat_messages').countDocuments({channel_id:c._id,content:data.content}))).toBe(1);
  expect((await a.manager.api.post(url,{data:{...data,content:'Changed content'}})).status()).toBe(409);
  expect((await a.outsider.api.post(url,{data})).status()).toBe(403);
  const other=await a.manager2.api.post(url,{data:{...data,content:'Another member intent'}});expect(other.ok(),await other.text()).toBeTruthy();
  expect((await other.json())._id).not.toBe(rows[0]._id);
  expect((await a.manager.api.post(url,{data:{...data,client_message_id:'x'.repeat(129)}})).status()).toBe(400);
  expect((await a.manager.api.post(url,{data:{...data,client_message_id:crypto.randomUUID()}})).ok()).toBeTruthy();
  expect(await database(db=>db.collection('chat_messages').countDocuments({channel_id:c._id,content:data.content}))).toBe(2);
 }finally{await dispose(a);}
});

test('retry after committed chat response loss reconciles to one message',async({page,context})=>{
 const a=await actors();try{
  const l=await league(a);await context.addCookies((await a.manager.api.storageState()).cookies);
  await context.addInitScript(id=>localStorage.setItem('dd_active_league_id',id),l.id);
  const ui=new MobileExperiencePage(page);await ui.goto('/chat');await expect(ui.input).toBeEnabled();await ui.dismissInstallIfPresent();
  let lost=false;await page.route('**/api/chat/channels/*/messages',async route=>{
   if(route.request().method()==='POST'&&!lost){lost=true;await route.fetch();await route.abort('connectionreset');}else await route.continue();
  });
  const text=`Lost response ${crypto.randomUUID()}`;await ui.input.fill(text);await ui.send.click();
  await expect(page.getByText(/Could not send message/)).toBeVisible();await expect(ui.input).toHaveValue(text);
  await expect(ui.send).toBeEnabled();await ui.send.click();await expect(ui.input).toHaveValue('');
  expect(await database(db=>db.collection('chat_messages').countDocuments({league_id:l.id,content:text}))).toBe(1);
 }finally{await dispose(a);}
});
