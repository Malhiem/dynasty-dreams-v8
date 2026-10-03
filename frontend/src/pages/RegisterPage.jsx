import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { formatApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Trophy, Eye, EyeSlash, Check, X } from '@phosphor-icons/react';

export default function RegisterPage() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const usernameValid = /^[a-zA-Z0-9_-]{3,24}$/.test(username);

  const passwordChecks = [
    { label: 'Username 3–24 chars (letters, numbers, _ or -)', valid: usernameValid },
    { label: 'At least 8 characters', valid: password.length >= 8 },
    { label: 'One uppercase letter', valid: /[A-Z]/.test(password) },
    { label: 'One number', valid: /\d/.test(password) },
    { label: 'Passwords match', valid: password === confirmPassword && password.length > 0 },
  ];

  const allChecksPass = passwordChecks.every((c) => c.valid);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!allChecksPass) {
      setError('Please meet all requirements');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await register(email, password, username);
      navigate('/dashboard');
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" data-testid="register-page">
      {/* Left side - Hero Image */}
      <div className="hidden lg:flex lg:w-1/2 relative">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1609935061446-c0b5236fee71?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzV8MHwxfHNlYXJjaHwzfHxob2NrZXklMjBzdGFkaXVtJTIwbGlnaHRzJTIwbmlnaHR8ZW58MHx8fHwxNzc2MDUwOTI4fDA&ixlib=rb-4.1.0&q=85')`
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0A0A0A] via-[#0A0A0A]/80 to-transparent" />
        <div className="relative z-10 flex flex-col justify-center p-12">
          <Trophy size={64} weight="duotone" className="text-[#00D2FF] mb-6" />
          <h1 className="font-heading text-5xl font-bold tracking-tight text-white mb-4">JOIN THE LEAGUE</h1>
          <p className="text-xl text-[#A1A1AA] max-w-md">Create your account and start building your championship dynasty today.</p>
        </div>
      </div>

      {/* Right side - Register Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-[#0A0A0A]">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <Trophy size={40} weight="duotone" className="text-[#00D2FF]" />
            <span className="font-heading text-2xl font-bold tracking-tight text-white">DYNASTY DREAMS</span>
          </div>

          <h2 className="font-heading text-3xl font-bold text-white mb-2">CREATE ACCOUNT</h2>
          <p className="text-[#A1A1AA] mb-8">Start your dynasty journey</p>

          {error && (
            <div className="bg-[#FF3B30]/20 border border-[#FF3B30]/50 text-[#FF3B30] px-4 py-3 rounded mb-6" data-testid="register-error">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <Label htmlFor="username" className="text-[#A1A1AA]">Username</Label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value.trim())}
                placeholder="Pick a unique username"
                required
                minLength={3}
                maxLength={24}
                pattern="^[a-zA-Z0-9_-]+$"
                data-testid="register-username"
                className="mt-2 bg-[#141414] border-white/10 text-white placeholder:text-[#52525B]"
              />
              <p className="text-xs text-[#52525B] mt-1">3–24 chars · letters, numbers, underscore or hyphen</p>
            </div>

            <div>
              <Label htmlFor="email" className="text-[#A1A1AA]">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                required
                data-testid="register-email"
                className="mt-2 bg-[#141414] border-white/10 text-white placeholder:text-[#52525B]"
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
                  placeholder="Create a password"
                  required
                  data-testid="register-password"
                  className="bg-[#141414] border-white/10 text-white placeholder:text-[#52525B] pr-10"
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

            <div>
              <Label htmlFor="confirmPassword" className="text-[#A1A1AA]">Confirm Password</Label>
              <Input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm your password"
                required
                data-testid="register-confirm-password"
                className="mt-2 bg-[#141414] border-white/10 text-white placeholder:text-[#52525B]"
              />
            </div>

            {/* Password requirements */}
            <div className="space-y-2">
              {passwordChecks.map((check, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  {check.valid ? (
                    <Check size={16} className="text-[#34C759]" weight="bold" />
                  ) : (
                    <X size={16} className="text-[#52525B]" />
                  )}
                  <span className={check.valid ? 'text-[#34C759]' : 'text-[#52525B]'}>{check.label}</span>
                </div>
              ))}
            </div>

            <Button
              type="submit"
              disabled={loading || !allChecksPass}
              data-testid="register-submit"
              className="w-full bg-[#00D2FF] text-black font-semibold hover:bg-[#33DBFF] disabled:opacity-50"
            >
              {loading ? 'Creating account...' : 'Create Account'}
            </Button>
          </form>

          <p className="mt-8 text-center text-[#A1A1AA]">
            Already have an account?{' '}
            <Link to="/login" className="text-[#00D2FF] hover:underline" data-testid="register-login-link">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
