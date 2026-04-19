import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Trophy, Users, Sword, ChartLine, ArrowRight, Star } from '@phosphor-icons/react';

export default function LandingPage() {
  const features = [
    {
      icon: Trophy,
      title: 'Multiple League Formats',
      description: 'Dynasty, Keeper, Redraft, Best Ball - play your way with customizable rules.'
    },
    {
      icon: Sword,
      title: 'Competitive Scoring',
      description: 'Head-to-Head, Rotisserie, Guillotine, All-Play - every format you need.'
    },
    {
      icon: Users,
      title: 'Real-Time Drafts',
      description: 'Live draft rooms with instant pick updates and auction support.'
    },
    {
      icon: ChartLine,
      title: 'Salary Cap Management',
      description: 'Full contract management for the ultimate dynasty experience.'
    },
  ];

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="landing-page">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center opacity-30"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1609935061446-c0b5236fee71?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzV8MHwxfHNlYXJjaHwzfHxob2NrZXklMjBzdGFkaXVtJTIwbGlnaHRzJTIwbmlnaHR8ZW58MHx8fHwxNzc2MDUwOTI4fDA&ixlib=rb-4.1.0&q=85')`
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[#0A0A0A]/80 to-[#0A0A0A]" />
        
        {/* Nav */}
        <nav className="relative z-10 flex items-center justify-between p-6 max-w-7xl mx-auto">
          <div className="flex items-center gap-2">
            <Trophy size={32} weight="duotone" className="text-[#00D2FF]" />
            <span className="font-heading text-xl font-bold tracking-tight text-white">DYNASTY DREAMS</span>
          </div>
          <div className="flex items-center gap-4">
            <Link to="/login">
              <Button variant="ghost" className="text-white hover:bg-white/10" data-testid="hero-login">
                Sign In
              </Button>
            </Link>
            <Link to="/register">
              <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" data-testid="hero-register">
                Get Started
              </Button>
            </Link>
          </div>
        </nav>

        {/* Hero Content */}
        <div className="relative z-10 max-w-7xl mx-auto px-6 pt-20 pb-32 text-center">
          <div className="inline-flex items-center gap-2 bg-[#00D2FF]/10 border border-[#00D2FF]/30 rounded-full px-4 py-2 mb-6">
            <Star size={16} weight="fill" className="text-[#00D2FF]" />
            <span className="text-[#00D2FF] text-sm font-medium">NHL Fantasy Sports Platform</span>
          </div>
          <h1 className="font-heading text-5xl sm:text-6xl lg:text-7xl font-black tracking-tight text-white mb-6">
            BUILD YOUR<br />
            <span className="text-[#00D2FF]">DYNASTY</span>
          </h1>
          <p className="text-xl text-[#A1A1AA] max-w-2xl mx-auto mb-10">
            The most powerful NHL fantasy sports platform. Create leagues, draft players, 
            manage contracts, and dominate the competition.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/register">
              <Button size="lg" className="bg-[#00D2FF] text-black hover:bg-[#33DBFF] px-8 py-6 text-lg" data-testid="hero-cta">
                Start Free
                <ArrowRight size={20} className="ml-2" />
              </Button>
            </Link>
            <Link to="/leagues">
              <Button size="lg" variant="outline" className="border-white/20 text-white hover:bg-white/5 px-8 py-6 text-lg">
                Browse Leagues
              </Button>
            </Link>
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
          <Link to="/register">
            <Button size="lg" className="bg-[#00D2FF] text-black hover:bg-[#33DBFF] px-12 py-6 text-lg">
              Create Your Account
              <ArrowRight size={20} className="ml-2" />
            </Button>
          </Link>
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
