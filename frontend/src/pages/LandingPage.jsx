import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { formatApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Trophy, Users, Sword, ChartLine, ArrowRight, Star, Eye, EyeSlash,
} from '@phosphor-icons/react';

/**
 * Iter 232N.20 — Landing page with an inline sign-in / register card.
 * Root ("/") no longer bounces logged-out visitors to /login; the login
 * form lives right beside the hero copy so a returning user can sign in
 * in one step, and new users can flip the same card into "Create your
 * account" mode. The standalone /login and /register routes still exist
 * (deep links, password reset return-to, etc.) — this is purely an
 * additive first-run affordance.
 *
 * Also removes the "Browse Leagues" button — the marketing hero now
 * focuses on the single conversion action ("Start Free" / sign-in).
 */
export default function LandingPage() {
  const features = [
    {
      icon: Trophy,
      title: 'Multiple League Formats',
      description: 'Dynasty, Keeper, Redraft, Best Ball - play your way with customizable rules.',
    },
    {
      icon: Sword,
      title: 'Competitive Scoring',
      description: 'Head-to-Head, Rotisserie, Guillotine, All-Play - every format you need.',
    },
    {
      icon: Users,
      title: 'Real-Time Drafts',
      description: 'Live draft rooms with instant pick updates and auction support.',
    },
    {
      icon: ChartLine,
      title: 'Salary Cap Management',
      description: 'Full contract management for the ultimate dynasty experience.',
    },
  ];

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="landing-page">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center opacity-30"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1609935061446-c0b5236fee71?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzV8MHwxfHNlYXJjaHwzfHxob2NrZXklMjBzdGFkaXVtJTIwbGlnaHRzJTIwbmlnaHR8ZW58MHx8fHwxNzc2MDUwOTI4fDA&ixlib=rb-4.1.0&q=85')`,
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[#0A0A0A]/80 to-[#0A0A0A]" />

        {/* Nav */}
        <nav className="relative z-10 flex items-center justify-between p-6 max-w-7xl mx-auto">
          <div className="flex items-center gap-2">
            <Trophy size={32} weight="duotone" className="text-[#00D2FF]" />
            <span className="font-heading text-xl font-bold tracking-tight text-white">DYNASTY DREAMS</span>
          </div>
          {/* Iter 232N.20 — Nav CTAs point at the inline card via anchor
              scroll so the hero action stays a single-click affair.
              The /login + /register routes still work for direct links. */}
          <div className="flex items-center gap-2">
            <a href="#auth-card">
              <Button variant="ghost" className="text-white hover:bg-white/10" data-testid="hero-login">
                Sign In
              </Button>
            </a>
            <a href="#auth-card">
              <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" data-testid="hero-register">
                Get Started
              </Button>
            </a>
          </div>
        </nav>

        {/* Hero + Inline Auth Card side-by-side */}
        <div className="relative z-10 max-w-7xl mx-auto px-6 pt-12 pb-24 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div className="text-center lg:text-left">
            <div className="inline-flex items-center gap-2 bg-[#00D2FF]/10 border border-[#00D2FF]/30 rounded-full px-4 py-2 mb-6">
              <Star size={16} weight="fill" className="text-[#00D2FF]" />
              <span className="text-[#00D2FF] text-sm font-medium">NHL Fantasy Sports Platform</span>
            </div>
            <h1 className="font-heading text-5xl sm:text-6xl lg:text-7xl font-black tracking-tight text-white mb-6">
              BUILD YOUR<br />
              <span className="text-[#00D2FF]">DYNASTY</span>
            </h1>
            <p className="text-xl text-[#A1A1AA] max-w-2xl mb-10">
              The most powerful NHL fantasy sports platform. Create leagues, draft players,
              manage contracts, and dominate the competition.
            </p>
          </div>

          {/* Inline auth card */}
          <div id="auth-card" className="w-full max-w-md mx-auto lg:mx-0 lg:ml-auto">
            <InlineAuthCard />
          </div>
        </div>
      </div>

      {/* Features Section */}
      <section className="py-20 bg-[#0A0A0A]">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="font-heading text-4xl font-bold text-white mb-4">EVERYTHING YOU NEED</h2>
            <p className="text-[#A1A1AA] text-lg">Built for serious fantasy managers</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((feature, i) => (
              <div
                key={i}
                className="surface p-6 hover:border-[#00D2FF]/30 transition-colors"
              >
                <feature.icon size={40} weight="duotone" className="text-[#00D2FF] mb-4" />
                <h3 className="font-heading text-xl font-bold text-white mb-2">{feature.title}</h3>
                <p className="text-[#A1A1AA]">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-[#141414]">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="font-heading text-4xl font-bold text-white mb-4">READY TO DOMINATE?</h2>
          <p className="text-[#A1A1AA] text-lg mb-8">
            Join thousands of fantasy managers building their championship dynasties.
          </p>
          <a href="#auth-card">
            <Button size="lg" className="bg-[#00D2FF] text-black hover:bg-[#33DBFF] px-12 py-6 text-lg" data-testid="landing-cta-bottom">
              Create Your Account
              <ArrowRight size={20} className="ml-2" />
            </Button>
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-[#0A0A0A] border-t border-white/10">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Trophy size={24} weight="duotone" className="text-[#00D2FF]" />
              <span className="font-heading font-bold text-white">DYNASTY DREAMS</span>
            </div>
            <p className="text-[#A1A1AA] text-sm">© 2026 Dynasty Dreams. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

/**
 * Iter 232N.20 — Inline sign-in / register card on the landing page.
 * Toggle at the top switches between the two modes so a returning user
 * signs in without navigating away, and a new user can sign up in the
 * same visual context. Reuses `useAuth().login` / `.register` from the
 * standalone /login + /register pages verbatim — no auth semantics
 * diverge from those routes.
 */
function InlineAuthCard() {
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, register, user } = useAuth();
  const navigate = useNavigate();

  // If the user is already authenticated (returning visitor with a
  // live session), bounce them straight to /dashboard. Same guard the
  // standalone /login page uses — keeps the landing page from
  // rendering a redundant form to logged-in users.
  useEffect(() => {
    if (user) navigate('/dashboard', { replace: true });
  }, [user, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      // Persist remember-me BEFORE the auth call so the /login page's
      // auto-clear effect reads the right value on the next visit.
      try {
        localStorage.setItem('auth_remember', remember ? 'true' : 'false');
      } catch { /* noop */ }
      if (mode === 'signin') {
        await login(email, password);
      } else {
        // AuthContext signature: register(email, password, username).
        await register(email, password, name);
      }
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="surface p-6 sm:p-8 border-white/10 bg-[#141414]/90 backdrop-blur-md rounded-2xl shadow-xl shadow-black/40"
      data-testid="landing-auth-card"
    >
      <div className="flex items-center gap-2 mb-1">
        <div className="flex-1 flex bg-black/40 rounded-lg p-1">
          <button
            type="button"
            onClick={() => { setMode('signin'); setError(''); }}
            className={`flex-1 py-2 rounded-md text-sm font-semibold transition-colors ${
              mode === 'signin'
                ? 'bg-[#00D2FF] text-black'
                : 'text-[#A1A1AA] hover:text-white'
            }`}
            data-testid="landing-auth-tab-signin"
            aria-pressed={mode === 'signin'}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setMode('register'); setError(''); }}
            className={`flex-1 py-2 rounded-md text-sm font-semibold transition-colors ${
              mode === 'register'
                ? 'bg-[#00D2FF] text-black'
                : 'text-[#A1A1AA] hover:text-white'
            }`}
            data-testid="landing-auth-tab-register"
            aria-pressed={mode === 'register'}
          >
            Create Account
          </button>
        </div>
      </div>

      <h3 className="font-heading text-2xl font-bold text-white mt-6 mb-1">
        {mode === 'signin' ? 'Welcome back' : 'Start free'}
      </h3>
      <p className="text-sm text-[#A1A1AA] mb-6">
        {mode === 'signin'
          ? 'Sign in to jump back into your leagues.'
          : 'One account. Every league. No credit card required.'}
      </p>

      {error && (
        <div
          className="bg-[#FF3B30]/20 border border-[#FF3B30]/50 text-[#FF3B30] px-3 py-2 rounded mb-4 text-sm"
          data-testid="landing-auth-error"
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {mode === 'register' && (
          <div>
            <Label htmlFor="landing-name" className="text-[#A1A1AA]">Name</Label>
            <Input
              id="landing-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              required
              data-testid="landing-auth-name"
              className="mt-2 bg-black/40 border-white/10 text-white placeholder:text-[#52525B] focus:ring-[#00D2FF]"
            />
          </div>
        )}

        <div>
          <Label htmlFor="landing-email" className="text-[#A1A1AA]">Email</Label>
          <Input
            id="landing-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
            data-testid="landing-auth-email"
            className="mt-2 bg-black/40 border-white/10 text-white placeholder:text-[#52525B] focus:ring-[#00D2FF]"
          />
        </div>

        <div>
          <Label htmlFor="landing-password" className="text-[#A1A1AA]">Password</Label>
          <div className="relative mt-2">
            <Input
              id="landing-password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === 'signin' ? 'Your password' : 'Create a password'}
              required
              minLength={mode === 'register' ? 8 : undefined}
              data-testid="landing-auth-password"
              className="bg-black/40 border-white/10 text-white placeholder:text-[#52525B] focus:ring-[#00D2FF] pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#A1A1AA] hover:text-white"
              aria-label="Toggle password visibility"
            >
              {showPassword ? <EyeSlash size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>

        {mode === 'signin' && (
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-[#A1A1AA] cursor-pointer">
              <input
                type="checkbox"
                className="rounded border-white/10 bg-black/40"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                data-testid="landing-auth-remember"
              />
              Remember me
            </label>
            <Link to="/forgot-password" className="text-sm text-[#00D2FF] hover:underline">
              Forgot password?
            </Link>
          </div>
        )}

        <Button
          type="submit"
          disabled={loading}
          data-testid="landing-auth-submit"
          className="w-full bg-[#00D2FF] text-black font-semibold hover:bg-[#33DBFF] disabled:opacity-50"
        >
          {loading
            ? (mode === 'signin' ? 'Signing in…' : 'Creating account…')
            : (mode === 'signin' ? 'Sign In' : 'Create Account')}
        </Button>
      </form>

      <p className="mt-6 text-center text-xs text-[#52525B]">
        {mode === 'signin' ? (
          <>Prefer the full page?{' '}
            <Link to="/login" className="text-[#00D2FF] hover:underline">Open the sign-in screen</Link>
          </>
        ) : (
          <>Already have an account?{' '}
            <button
              type="button"
              onClick={() => { setMode('signin'); setError(''); }}
              className="text-[#00D2FF] hover:underline"
              data-testid="landing-auth-switch-signin"
            >
              Sign in
            </button>
          </>
        )}
      </p>
    </div>
  );
}
