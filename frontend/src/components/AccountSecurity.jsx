import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import api, { formatApiError } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';

export default function AccountSecurity() {
  const {user} = useAuth();
  const navigate = useNavigate();
  const [current,setCurrent] = useState('');
  const [password,setPassword] = useState('');
  const [confirm,setConfirm] = useState('');
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState('');
  const [error,setError] = useState('');
  async function change(event) {
    event.preventDefault(); if (busy) return;
    setError(''); setMessage('');
    if (password !== confirm) {setError('Passwords must match');return;}
    setBusy(true);
    try {
      await api.post('/auth/change-password',{current_password:current,new_password:password});
      try {localStorage.setItem('auth_logout',String(Date.now()));} catch {}
      window.dispatchEvent(new CustomEvent('auth-expired')); navigate('/login');
    } catch (failure) {setError(formatApiError(failure));} finally {setBusy(false);}
  }
  async function resend() {
    if(busy)return; setBusy(true); setError('');
    try {const {data}=await api.post('/auth/resend-verification');setMessage(data.message);}
    catch(failure){setError(formatApiError(failure));}finally{setBusy(false);}
  }
  return <section className="mt-4 p-4 border border-white/10 rounded space-y-4">
    <h2 className="text-lg font-bold">Account security</h2>
    <p>{user?.email_verified ? 'Email verified' : 'Email not verified'}{user?.pending_email ? ` · Pending address: ${user.pending_email}` : ''}</p>
    {(!user?.email_verified || user?.pending_email) && <Button type="button" disabled={busy} onClick={resend}>Send verification email</Button>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <form onSubmit={change} className="space-y-3">
      <Label htmlFor="security-current">Current password</Label><Input id="security-current" type="password" autoComplete="current-password" required value={current} onChange={e=>setCurrent(e.target.value)} />
      <Label htmlFor="security-new">New password</Label><Input id="security-new" type="password" autoComplete="new-password" required value={password} onChange={e=>setPassword(e.target.value)} />
      <p>At least 8 characters, one uppercase letter and one number.</p>
      <Label htmlFor="security-confirm">Confirm new password</Label><Input id="security-confirm" type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)} />
      <Button type="submit" disabled={busy}>Change password</Button><p>Changing your password signs out all sessions.</p>
    </form>
  </section>;
}
