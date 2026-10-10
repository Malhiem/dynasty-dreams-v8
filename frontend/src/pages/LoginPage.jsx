import { useState, useEffect, useRef } from 'react';
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
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [cleared, setCleared] = useState(false);
  const { login, user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/dashboard';
  // Iter 228f — Track that the user actively submitted the login form
  // in THIS session. Without this guard the Remember-Me auto-clear
  // useEffect below kept firing AFTER a successful login (because
  // `user` transitioned from null→authed during handleSubmit), and the
  // stored `auth_remember=false` branch would call logout() → killing
  // the freshly-created session → bouncing the user back to /login.
  // The "flash of dashboard then back to login" loop bug.
  const justLoggedInRef = useRef(false);

  // Iter 227 — "Remember me" governs whether a returning visitor with a
  // live session is auto-bounced to the dashboard. If the user did NOT
  // check Remember-me on their last sign-in, we proactively log them out
  // when they land on /login so the form is always clean for the next
  // person on a shared device. **Skipped immediately after a successful
  // login** (iter 228f) — handleSubmit handles the navigation itself.
  useEffect(() => {
    if (!user) return;
    if (justLoggedInRef.current) return; // Skip auto-clear right after login
    const stored = (typeof window !== 'undefined' && localStorage.getItem('auth_remember')) || 'false';
    if (stored === 'true') {
      navigate(from, { replace: true });
    } else {
      // Auto-clear the lingering session so the next visitor starts fresh
      logout().catch(() => { /* noop — UI still shows logged-out state */ });
    }
  }, [user, from, navigate, logout]);

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
    if (loading) return;
    setError('');
    setLoading(true);
    try {
      // Iter 228f — Mark "this is a fresh login" BEFORE we await so the
      // user-watching useEffect skips its auto-logout branch when user
      // state transitions from null→authed.
      justLoggedInRef.current = true;
      // Iter 227 — Persist remember-me BEFORE the login network call so
      // any concurrent re-render of the useEffect reads the right value.
      try {
        localStorage.setItem('auth_remember', remember ? 'true' : 'false');
      } catch { /* noop */ }
      await login(email, password, remember);
      navigate(from, { replace: true });
    } catch (err) {
      // On failure, allow the auto-clear effect to run again if needed
      justLoggedInRef.current = false;
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
            <div className="bg-[#FF3B30]/20 border border-[#FF3B30]/50 text-[#FF3B30] px-4 py-3 rounded mb-6" role="alert" data-testid="login-error">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <Label htmlFor="email" className="text-[#A1A1AA]">Email</Label>
              <Input
                autoComplete="email"
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
                  autoComplete="current-password"
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
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#A1A1AA] hover:text-white"
                >
                  {showPassword ? <EyeSlash size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-[#A1A1AA] cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded border-white/10 bg-[#141414]"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  data-testid="login-remember-me"
                />
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
            Don&apos;t have an account?{' '}
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
