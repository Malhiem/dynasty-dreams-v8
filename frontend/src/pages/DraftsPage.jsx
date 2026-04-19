import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import Navbar from '@/components/layout/Navbar';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Calendar, Plus, Clock, Users, Play } from '@phosphor-icons/react';

export default function DraftsPage() {
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // For now, show placeholder - drafts will be fetched when leagues have drafts
    setLoading(false);
    setDrafts([]);
  }, []);

  const columns = [
    { key: 'league_name', label: 'League' },
    { key: 'draft_type', label: 'Type', render: (v) => v?.replace('_', ' ').toUpperCase() },
    { key: 'scheduled_time', label: 'Scheduled', render: (v) => new Date(v).toLocaleString() },
    { key: 'rounds', label: 'Rounds' },
    { 
      key: 'status', 
      label: 'Status', 
      render: (v) => (
        <span className={`badge ${
          v === 'active' ? 'badge-success' : 
          v === 'completed' ? 'badge-info' : 'badge-warning'
        }`}>
          {v}
        </span>
      )
    },
  ];

  return (
    <div className="min-h-screen bg-[#0A0A0A]" data-testid="drafts-page">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="font-heading text-4xl font-bold tracking-tight text-white">DRAFTS</h1>
            <p className="text-[#A1A1AA]">View and manage your league drafts</p>
          </div>
        </div>

        {/* Draft Info Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="surface p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-[#FF9F0A]/20 rounded">
                <Clock size={24} className="text-[#FF9F0A]" />
              </div>
              <div>
                <p className="text-[#A1A1AA] text-sm">Upcoming</p>
                <p className="text-white font-heading text-2xl font-bold">0</p>
              </div>
            </div>
          </div>
          <div className="surface p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-[#34C759]/20 rounded">
                <Play size={24} className="text-[#34C759]" />
              </div>
              <div>
                <p className="text-[#A1A1AA] text-sm">Active</p>
                <p className="text-white font-heading text-2xl font-bold">0</p>
              </div>
            </div>
          </div>
          <div className="surface p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-[#00D2FF]/20 rounded">
                <Users size={24} className="text-[#00D2FF]" />
              </div>
              <div>
                <p className="text-[#A1A1AA] text-sm">Completed</p>
                <p className="text-white font-heading text-2xl font-bold">0</p>
              </div>
            </div>
          </div>
        </div>

        {/* Drafts Table */}
        {loading ? (
          <div className="surface p-8 text-center text-[#A1A1AA]">
            Loading drafts...
          </div>
        ) : drafts.length === 0 ? (
          <div className="surface p-12 text-center">
            <Calendar size={64} className="text-[#52525B] mx-auto mb-4" />
            <h3 className="text-xl text-white font-semibold mb-2">No drafts scheduled</h3>
            <p className="text-[#A1A1AA] mb-6">Join or create a league to participate in drafts</p>
            <Link to="/leagues">
              <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]">
                Browse Leagues
              </Button>
            </Link>
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={drafts}
            testId="drafts-table"
          />
        )}
      </main>
    </div>
  );
}
