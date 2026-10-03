import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Trophy, Users, Calendar, User, SignOut, List, X, ChartLineUp } from '@phosphor-icons/react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const navLinks = [
    { path: '/dashboard', label: 'Dashboard', icon: ChartLineUp },
    { path: '/leagues', label: 'Leagues', icon: Trophy },
    { path: '/players', label: 'Players', icon: Users },
    { path: '/drafts', label: 'Drafts', icon: Calendar },
  ];

  const isActive = (path) => location.pathname === path;

  return (
    <nav className="bg-[#141414] border-b border-white/10 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2" data-testid="nav-logo">
            <Trophy size={32} weight="duotone" className="text-[#00D2FF]" />
            <span className="font-heading text-xl font-bold tracking-tight text-white">DYNASTY DREAMS</span>
          </Link>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-6">
            {user && navLinks.map(({ path, label, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                data-testid={`nav-${label.toLowerCase()}`}
                className={`flex items-center gap-2 px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(path)
                    ? 'text-[#00D2FF] border-b-2 border-[#00D2FF]'
                    : 'text-[#A1A1AA] hover:text-white'
                }`}
              >
                <Icon size={18} weight={isActive(path) ? 'duotone' : 'regular'} />
                {label}
              </Link>
            ))}
          </div>

          {/* Right side */}
          <div className="hidden md:flex items-center gap-4">
            {user ? (
              // Iter 202 — User profile/avatar removed from the top navbar
              // (lives in the sidebar's user card instead). Keep the
              // logout button here for one-click sign-out from any page.
              <Button
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                data-testid="nav-logout"
                className="text-[#A1A1AA] hover:text-white hover:bg-white/5"
              >
                <SignOut size={18} />
              </Button>
            ) : (
              <>
                <Link to="/login">
                  <Button variant="ghost" size="sm" data-testid="nav-login" className="text-white">
                    Sign In
                  </Button>
                </Link>
                <Link to="/register">
                  <Button size="sm" data-testid="nav-register" className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]">
                    Get Started
                  </Button>
                </Link>
              </>
            )}
          </div>

          {/* Mobile menu button */}
          <button
            className="md:hidden p-2 text-white"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            data-testid="nav-mobile-menu"
          >
            {mobileMenuOpen ? <X size={24} /> : <List size={24} />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-[#141414] border-t border-white/10 py-4">
          {user ? (
            <>
              {navLinks.map(({ path, label, icon: Icon }) => (
                <Link
                  key={path}
                  to={path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3 text-sm font-medium ${
                    isActive(path) ? 'text-[#00D2FF] bg-[#00D2FF]/10' : 'text-[#A1A1AA]'
                  }`}
                >
                  <Icon size={20} />
                  {label}
                </Link>
              ))}
              <button
                onClick={() => { handleLogout(); setMobileMenuOpen(false); }}
                className="flex items-center gap-3 px-4 py-3 text-sm font-medium text-[#A1A1AA] w-full"
              >
                <SignOut size={20} />
                Sign Out
              </button>
            </>
          ) : (
            <div className="px-4 space-y-2">
              <Link to="/login" onClick={() => setMobileMenuOpen(false)}>
                <Button variant="ghost" className="w-full justify-start">Sign In</Button>
              </Link>
              <Link to="/register" onClick={() => setMobileMenuOpen(false)}>
                <Button className="w-full bg-[#00D2FF] text-black">Get Started</Button>
              </Link>
            </div>
          )}
        </div>
      )}
    </nav>
  );
}
