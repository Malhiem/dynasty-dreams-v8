import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { formatApiError } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
export default function VerifyEmailPage() {
  const [params]=useSearchParams(); const {refreshUser}=useAuth();
  const [busy,setBusy]=useState(false); const [message,setMessage]=useState(''); const [error,setError]=useState('');
  async function verify(){
    if(busy)return; setBusy(true);setError('');
    try{const {data}=await axios.post(`${process.env.REACT_APP_BACKEND_URL}/api/auth/verify-email`,{token:params.get('token') || ''},{withCredentials:true});setMessage(data.message);await refreshUser();}
    catch(failure){setError(formatApiError(failure));}finally{setBusy(false);}
  }
  return <main className="min-h-screen bg-[#0A0A0A] text-white flex items-center justify-center p-4"><div className="w-full max-w-md space-y-6">
    <h1 className="text-2xl font-bold">Verify email</h1>
    {error && <p role="alert">{error}</p>}{message ? <p role="status">{message}</p> : <Button onClick={verify} disabled={busy}>{busy ? 'Verifying…' : 'Verify email'}</Button>}
    <p><Link to="/login">Sign in</Link> · <Link to="/profile/edit">Account settings and resend verification</Link></p>
  </div></main>;
}
