import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { formatApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function PasswordRecoveryPage({ reset = false }) {
  const [params] = useSearchParams();
  const [email,setEmail] = useState('');
  const [password,setPassword] = useState('');
  const [confirm,setConfirm] = useState('');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [message,setMessage] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setError('');
    if (reset && (password.length < 8 || !/[A-Z]/.test(password) || !/[0-9]/.test(password) || password !== confirm)) {
      setError('Use at least 8 characters, one uppercase letter and one number. Passwords must match.'); return;
    }
    setBusy(true);
    try {
      const { data } = await axios.post(`${process.env.REACT_APP_BACKEND_URL}/api/auth/${reset ? 'reset-password' : 'forgot-password'}`,
        reset ? {token:params.get('token') || '',new_password:password} : {email}, {withCredentials:true});
      setMessage(data.message); setPassword(''); setConfirm('');
      if (reset) window.dispatchEvent(new CustomEvent('auth-expired'));
    } catch (failure) { setError(formatApiError(failure)); }
    finally { setBusy(false); }
  }
  return <main className="min-h-screen bg-[#0A0A0A] text-white flex items-center justify-center p-4">
    <div className="w-full max-w-md space-y-6">
      <h1 className="text-2xl font-bold">{reset ? 'Reset password' : 'Forgot password'}</h1>
      {error && <p role="alert">{error}</p>}
      {message ? <p role="status">{message}</p> : <form onSubmit={submit} className="space-y-4">
        {reset ? <>
          <Label htmlFor="new-password">New password</Label>
          <Input id="new-password" type="password" autoComplete="new-password" required value={password} onChange={e=>setPassword(e.target.value)} />
          <p>At least 8 characters, one uppercase letter and one number.</p>
          <Label htmlFor="confirm-password">Confirm password</Label>
          <Input id="confirm-password" type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)} />
        </> : <>
          <Label htmlFor="recovery-email">Email</Label>
          <Input id="recovery-email" type="email" autoComplete="email" required value={email} onChange={e=>setEmail(e.target.value)} />
        </>}
        <Button className="w-full" disabled={busy} type="submit">{busy ? 'Submitting…' : reset ? 'Reset password' : 'Send reset link'}</Button>
      </form>}
      <p><Link to="/login">Sign in</Link> · <Link to="/forgot-password">Request a new reset link</Link></p>
    </div>
  </main>;
}
