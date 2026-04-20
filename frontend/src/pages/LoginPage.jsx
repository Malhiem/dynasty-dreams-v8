import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { formatApiError } from '@/lib/api';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Trophy, Eye, EyeSlash } from '@phosphor-icons/react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [cleared, setCleared] = useState(false);
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/dashboard';

  // If the user already has a valid session, jump straight to the app.
  useEffect(() => {
    if (user) navigate(from, { replace: true });
  }, [user, from, navigate]);

  const handleClearSession = async () => {
    try {
      // Ask the server to clear the HttpOnly auth cookies.
      await axios.post(`${BACKEND_URL}/api/auth/logout`, {}, { withCredentials: true });
    } catch (e) {
      // ignore — still try client-side wipe
    }
    // Wipe anything non-HttpOnly on the client side too.
    document.cookie.split(';').forEach((c) => {
      const name = c.split('=')[0].trim();
      document.cookie = `${name}=; Max-Age=0; path=/`;
    });
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch (e) { /* noop */ }
    setCleared(true);
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left side - Hero Image */}
      <div className="hidden lg:flex lg:w-1/2 relative">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1765302966993-0633da24b61d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1ODF8MHwxfHNlYXJjaHwxfHxpY2UlMjBob2NrZXklMjBwbGF5ZXIlMjBhY3Rpb24lMjBkYXJrfGVufDB8fHx8MTc3NjA1MDkyOHww&ixlib=rb-4.1.0&q=85')`
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0A0A0A] via-[#0A0A0A]/80 to-transparent" />
        <div className="relative z-10 flex flex-col justify-center p-12">
          <Trophy size={64} weight="duotone" className="text-[#00D2FF] mb-6" />
          <h1 className="font-heading text-5xl font-bold tracking-tight text-white mb-4">DYNASTY DREAMS</h1>
          <p className="text-xl text-[#A1A1AA] max-w-md">Build your dynasty. Dominate the ice. The ultimate NHL fantasy sports experience.</p>
        </div>
      </div>

      {/* Right side - Login Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-[#0A0A0A]">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <Trophy size={40} weight="duotone" className="text-[#00D2FF]" />
            <span className="font-heading text-2xl font-bold tracking-tight text-white">DYNASTY DREAMS</span>
          </div>

          <h2 className="font-heading text-3xl font-bold text-white mb-2">WELCOME BACK</h2>
          <p className="text-[#A1A1AA] mb-8">Sign in to your account to continue</p>

          {error && (
            <div className="bg-[#FF3B30]/20 border border-[#FF3B30]/50 text-[#FF3B30] px-4 py-3 rounded mb-6" data-testid="login-error">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <Label htmlFor="email" className="text-[#A1A1AA]">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                required
                data-testid="login-email"
                className="mt-2 bg-[#141414] border-white/10 text-white placeholder:text-[#52525B] focus:ring-[#00D2FF]"
              />
            </div>

            <div>
              <Label htmlFor="password" className="text-[#A1A1AA]">Password</Label>
              <div className="relative mt-2">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                  data-testid="login-password"
                  className="bg-[#141414] border-white/10 text-white placeholder:text-[#52525B] focus:ring-[#00D2FF] pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#A1A1AA] hover:text-white"
                >
                  {showPassword ? <EyeSlash size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-[#A1A1AA]">
                <input type="checkbox" className="rounded border-white/10 bg-[#141414]" />
                Remember me
              </label>
              <Link to="/forgot-password" className="text-sm text-[#00D2FF] hover:underline">
                Forgot password?
              </Link>
            </div>

            <Button
              type="submit"
              disabled={loading}
              data-testid="login-submit"
              className="w-full bg-[#00D2FF] text-black font-semibold hover:bg-[#33DBFF] disabled:opacity-50"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>

          <p className="mt-8 text-center text-[#A1A1AA]">
            Don't have an account?{' '}
            <Link to="/register" className="text-[#00D2FF] hover:underline" data-testid="login-register-link">
              Create one
            </Link>
          </p>

          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={handleClearSession}
              data-testid="login-clear-session-btn"
              className="text-xs text-[#52525B] hover:text-[#A1A1AA] underline underline-offset-4"
            >
              {cleared ? 'Session cleared — try signing in again' : 'Having trouble signing in? Clear session'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
