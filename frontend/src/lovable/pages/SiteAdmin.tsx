// @ts-nocheck
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield, ShieldCheck, Plus, Pencil, Trash2, Eye, ArrowLeft, Search, Users, DollarSign, Crown, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/hooks/use-toast";
import OperationsConsole from "@/lovable/pages/site-admin/OperationsConsole";

// Mock admin auth
const CURRENT_USER = {
  id: "user-001",
  name: "Site Admin",
  email: "admin@fantasyhockey.com",
  role: "master_admin" as "master_admin" | "admin" | "user",
};

interface League {
  id: string;
  name: string;
  commissioner: string;
  commissionerEmail: string;
  format: string;
  teams: number;
  maxTeams: number;
  tier: "premium" | "basic";
  status: "active" | "suspended" | "archived";
  feesPaid: number;
  feesTotal: number;
  season: string;
  createdAt: string;
  draftDate: string;
  playersPerTeam: number;
}

const initialLeagues: League[] = [
  { id: "lg-001", name: "Arctic Thunder League", commissioner: "Mike Johnson", commissionerEmail: "mike@email.com", format: "H2H Points", teams: 12, maxTeams: 12, tier: "premium", status: "active", feesPaid: 10, feesTotal: 12, season: "2025-26", createdAt: "2024-09-01", draftDate: "2024-10-05", playersPerTeam: 23 },
  { id: "lg-002", name: "Northern Lights Fantasy", commissioner: "Sarah Chen", commissionerEmail: "sarah@email.com", format: "Rotisserie", teams: 10, maxTeams: 10, tier: "premium", status: "active", feesPaid: 10, feesTotal: 10, season: "2025-26", createdAt: "2024-08-15", draftDate: "2024-09-28", playersPerTeam: 20 },
  { id: "lg-003", name: "Puck Dynasty", commissioner: "James Wu", commissionerEmail: "james@email.com", format: "H2H Each Category", teams: 8, maxTeams: 10, tier: "basic", status: "active", feesPaid: 6, feesTotal: 8, season: "2025-26", createdAt: "2024-09-10", draftDate: "2024-10-12", playersPerTeam: 18 },
  { id: "lg-004", name: "Frozen Assets", commissioner: "Emily Davis", commissionerEmail: "emily@email.com", format: "Points-based", teams: 14, maxTeams: 14, tier: "premium", status: "active", feesPaid: 14, feesTotal: 14, season: "2025-26", createdAt: "2024-07-20", draftDate: "2024-09-15", playersPerTeam: 25 },
  { id: "lg-005", name: "Ice Breakers United", commissioner: "Tom Bradley", commissionerEmail: "tom@email.com", format: "H2H Most Categories", teams: 12, maxTeams: 12, tier: "basic", status: "suspended", feesPaid: 4, feesTotal: 12, season: "2025-26", createdAt: "2024-09-05", draftDate: "2024-10-08", playersPerTeam: 22 },
  { id: "lg-006", name: "Slapshot Syndicate", commissioner: "Rachel Kim", commissionerEmail: "rachel@email.com", format: "H2H Points", teams: 10, maxTeams: 12, tier: "basic", status: "active", feesPaid: 8, feesTotal: 10, season: "2025-26", createdAt: "2024-08-25", draftDate: "2024-10-01", playersPerTeam: 20 },
  { id: "lg-007", name: "Winter Classic League", commissioner: "David Park", commissionerEmail: "david@email.com", format: "Rotisserie", teams: 16, maxTeams: 16, tier: "premium", status: "archived", feesPaid: 16, feesTotal: 16, season: "2024-25", createdAt: "2023-09-01", draftDate: "2023-10-05", playersPerTeam: 23 },
  { id: "lg-008", name: "Hatty League", commissioner: "Alex Morgan", commissionerEmail: "alex@email.com", format: "Points-based", teams: 6, maxTeams: 8, tier: "basic", status: "active", feesPaid: 4, feesTotal: 6, season: "2025-26", createdAt: "2024-10-01", draftDate: "2024-11-01", playersPerTeam: 18 },
];

const STORAGE_KEY = "site-admin-leagues";

function loadLeagues(): League[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return initialLeagues;
}

function saveLeagues(leagues: League[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(leagues));
}

const emptyLeague: Omit<League, "id"> = {
  name: "", commissioner: "", commissionerEmail: "", format: "H2H Points",
  teams: 10, maxTeams: 12, tier: "basic", status: "active",
  feesPaid: 0, feesTotal: 10, season: "2025-26",
  createdAt: new Date().toISOString().split("T")[0], draftDate: "", playersPerTeam: 20,
};

export default function SiteAdmin() {
  const navigate = useNavigate();
  const [leagues, setLeagues] = useState<League[]>(loadLeagues);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterTier, setFilterTier] = useState<string>("all");
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [editingLeague, setEditingLeague] = useState<League | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState<Omit<League, "id">>(emptyLeague);

  // Auth guard
  if (CURRENT_USER.role !== "master_admin" && CURRENT_USER.role !== "admin") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center space-y-4">
            <AlertTriangle className="h-12 w-12 text-destructive mx-auto" />
            <h2 className="text-xl font-bold text-foreground">Access Denied</h2>
            <p className="text-muted-foreground">You do not have permission to access this page.</p>
            <Button onClick={() => navigate("/")} variant="outline">Return to Dashboard</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const filtered = leagues.filter((lg) => {
    const matchesSearch = lg.name.toLowerCase().includes(search.toLowerCase()) ||
      lg.commissioner.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = filterStatus === "all" || lg.status === filterStatus;
    const matchesTier = filterTier === "all" || lg.tier === filterTier;
    return matchesSearch && matchesStatus && matchesTier;
  });

  const stats = {
    total: leagues.length,
    active: leagues.filter((l) => l.status === "active").length,
    premium: leagues.filter((l) => l.tier === "premium").length,
    totalTeams: leagues.reduce((s, l) => s + l.teams, 0),
    totalFeesPaid: leagues.reduce((s, l) => s + l.feesPaid, 0),
    totalFeesOwed: leagues.reduce((s, l) => s + l.feesTotal, 0),
  };

  const persist = (updated: League[]) => { setLeagues(updated); saveLeagues(updated); };

  const openCreate = () => {
    setIsCreating(true);
    setEditingLeague(null);
    setFormData(emptyLeague);
    setEditModalOpen(true);
  };

  const openEdit = (league: League) => {
    setIsCreating(false);
    setEditingLeague(league);
    const { id, ...rest } = league;
    setFormData(rest);
    setEditModalOpen(true);
  };

  const handleSave = () => {
    if (!formData.name.trim()) {
      toast({ title: "Error", description: "League name is required.", variant: "destructive" });
      return;
    }
    if (isCreating) {
      const newLeague: League = { ...formData, id: `lg-${Date.now()}` };
      persist([...leagues, newLeague]);
      toast({ title: "League Created", description: `${formData.name} has been created.` });
    } else if (editingLeague) {
      persist(leagues.map((l) => (l.id === editingLeague.id ? { ...formData, id: editingLeague.id } : l)));
      toast({ title: "League Updated", description: `${formData.name} has been updated.` });
    }
    setEditModalOpen(false);
  };

  const confirmDelete = (league: League) => { setEditingLeague(league); setDeleteConfirmOpen(true); };
  const handleDelete = () => {
    if (!editingLeague) return;
    persist(leagues.filter((l) => l.id !== editingLeague.id));
    toast({ title: "League Deleted", description: `${editingLeague.name} has been removed.` });
    setDeleteConfirmOpen(false);
    setEditingLeague(null);
  };

  const toggleStatus = (league: League) => {
    const next = league.status === "active" ? "suspended" : "active";
    persist(leagues.map((l) => (l.id === league.id ? { ...l, status: next } : l)));
    toast({ title: `League ${next === "active" ? "Activated" : "Suspended"}`, description: league.name });
  };

  const statusColor = (s: string) => {
    if (s === "active") return "bg-[hsl(var(--success))]/20 text-[hsl(var(--success))] border-[hsl(var(--success))]/30";
    if (s === "suspended") return "bg-destructive/20 text-destructive border-destructive/30";
    return "bg-muted text-muted-foreground border-border";
  };

  const tierColor = (t: string) =>
    t === "premium"
      ? "bg-[hsl(var(--gold))]/20 text-[hsl(var(--gold))] border-[hsl(var(--gold))]/30"
      : "bg-secondary text-muted-foreground border-border";

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" onClick={() => navigate("/")}>
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center">
                <ShieldCheck className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-foreground tracking-tight">Site Administration</h1>
                <p className="text-xs text-muted-foreground">
                  {CURRENT_USER.role === "master_admin" ? "Master Admin" : "Admin"} · {CURRENT_USER.email}
                </p>
              </div>
            </div>
          </div>
          <Badge variant="outline" className="border-primary/40 text-primary gap-1.5">
            <Shield className="h-3 w-3" />
            {CURRENT_USER.role === "master_admin" ? "Master Admin" : "Admin"}
          </Badge>
        </div>
      </header>

      <div className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        <OperationsConsole />

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {[
            { label: "Total Leagues", value: stats.total, icon: Crown },
            { label: "Active", value: stats.active, icon: Eye },
            { label: "Premium", value: stats.premium, icon: ShieldCheck },
            { label: "Total Teams", value: stats.totalTeams, icon: Users },
            { label: "Fees Collected", value: `$${stats.totalFeesPaid * 50}`, icon: DollarSign },
            { label: "Fees Outstanding", value: `$${(stats.totalFeesOwed - stats.totalFeesPaid) * 50}`, icon: AlertTriangle },
          ].map(({ label, value, icon: Icon }) => (
            <Card key={label} className="bg-card border-border">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="h-9 w-9 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
                  <Icon className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="text-lg font-bold text-foreground">{value}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Toolbar */}
        <Card className="bg-card border-border">
          <CardContent className="p-4 flex flex-col md:flex-row gap-3 items-start md:items-center justify-between">
            <div className="flex gap-3 items-center flex-1 w-full md:w-auto">
              <div className="relative flex-1 md:max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input placeholder="Search leagues or commissioners..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 bg-secondary border-border" />
              </div>
              <Select value={filterStatus} onValueChange={setFilterStatus}>
                <SelectTrigger className="w-32 bg-secondary border-border"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="suspended">Suspended</SelectItem>
                  <SelectItem value="archived">Archived</SelectItem>
                </SelectContent>
              </Select>
              <Select value={filterTier} onValueChange={setFilterTier}>
                <SelectTrigger className="w-32 bg-secondary border-border"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Tiers</SelectItem>
                  <SelectItem value="premium">Premium</SelectItem>
                  <SelectItem value="basic">Basic</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={openCreate} className="bg-primary text-primary-foreground hover:bg-primary/90 gap-2">
              <Plus className="h-4 w-4" /> New League
            </Button>
          </CardContent>
        </Card>

        {/* Table */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-foreground">All Leagues ({filtered.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-muted-foreground">League</TableHead>
                  <TableHead className="text-muted-foreground">Commissioner</TableHead>
                  <TableHead className="text-muted-foreground">Format</TableHead>
                  <TableHead className="text-muted-foreground text-center">Teams</TableHead>
                  <TableHead className="text-muted-foreground text-center">Tier</TableHead>
                  <TableHead className="text-muted-foreground text-center">Status</TableHead>
                  <TableHead className="text-muted-foreground text-center">Fees Paid</TableHead>
                  <TableHead className="text-muted-foreground">Season</TableHead>
                  <TableHead className="text-muted-foreground text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((league) => (
                  <TableRow key={league.id} className="border-border hover:bg-secondary/50">
                    <TableCell className="font-medium text-foreground">{league.name}</TableCell>
                    <TableCell>
                      <div>
                        <p className="text-sm text-foreground">{league.commissioner}</p>
                        <p className="text-xs text-muted-foreground">{league.commissionerEmail}</p>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">{league.format}</TableCell>
                    <TableCell className="text-center text-foreground">{league.teams}/{league.maxTeams}</TableCell>
                    <TableCell className="text-center">
                      <Badge variant="outline" className={tierColor(league.tier)}>{league.tier}</Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant="outline" className={statusColor(league.status)}>{league.status}</Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      <span className={league.feesPaid === league.feesTotal ? "text-[hsl(var(--success))]" : "text-[hsl(var(--gold))]"}>
                        {league.feesPaid}/{league.feesTotal}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">{league.season}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex gap-1 justify-end">
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-primary" onClick={() => openEdit(league)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground" onClick={() => toggleStatus(league)}>
                          {league.status === "active" ? <AlertTriangle className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </Button>
                        {CURRENT_USER.role === "master_admin" && (
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => confirmDelete(league)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-12 text-muted-foreground">No leagues found.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* Edit / Create Modal */}
      <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
        <DialogContent className="max-w-lg bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">{isCreating ? "Create New League" : "Edit League"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground">League Name</Label>
              <Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} className="bg-secondary border-border" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Commissioner</Label>
                <Input value={formData.commissioner} onChange={(e) => setFormData({ ...formData, commissioner: e.target.value })} className="bg-secondary border-border" />
              </div>
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Email</Label>
                <Input value={formData.commissionerEmail} onChange={(e) => setFormData({ ...formData, commissionerEmail: e.target.value })} className="bg-secondary border-border" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Format</Label>
                <Select value={formData.format} onValueChange={(v) => setFormData({ ...formData, format: v })}>
                  <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["H2H Points", "H2H Each Category", "H2H Most Categories", "Points-based", "Rotisserie"].map((f) => (
                      <SelectItem key={f} value={f}>{f}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Tier</Label>
                <Select value={formData.tier} onValueChange={(v) => setFormData({ ...formData, tier: v as "premium" | "basic" })}>
                  <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="basic">Basic</SelectItem>
                    <SelectItem value="premium">Premium</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Teams</Label>
                <Input type="number" value={formData.teams} onChange={(e) => setFormData({ ...formData, teams: +e.target.value })} className="bg-secondary border-border" />
              </div>
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Max Teams</Label>
                <Input type="number" value={formData.maxTeams} onChange={(e) => setFormData({ ...formData, maxTeams: +e.target.value })} className="bg-secondary border-border" />
              </div>
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Roster Size</Label>
                <Input type="number" value={formData.playersPerTeam} onChange={(e) => setFormData({ ...formData, playersPerTeam: +e.target.value })} className="bg-secondary border-border" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Fees Paid</Label>
                <Input type="number" value={formData.feesPaid} onChange={(e) => setFormData({ ...formData, feesPaid: +e.target.value })} className="bg-secondary border-border" />
              </div>
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Fees Total</Label>
                <Input type="number" value={formData.feesTotal} onChange={(e) => setFormData({ ...formData, feesTotal: +e.target.value })} className="bg-secondary border-border" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Season</Label>
                <Input value={formData.season} onChange={(e) => setFormData({ ...formData, season: e.target.value })} className="bg-secondary border-border" />
              </div>
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground">Draft Date</Label>
                <Input type="date" value={formData.draftDate} onChange={(e) => setFormData({ ...formData, draftDate: e.target.value })} className="bg-secondary border-border" />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground">Status</Label>
              <Select value={formData.status} onValueChange={(v) => setFormData({ ...formData, status: v as League["status"] })}>
                <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="suspended">Suspended</SelectItem>
                  <SelectItem value="archived">Archived</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditModalOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} className="bg-primary text-primary-foreground">{isCreating ? "Create" : "Save Changes"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="max-w-sm bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">Delete League</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">Are you sure you want to permanently delete <strong className="text-foreground">{editingLeague?.name}</strong>? This action cannot be undone.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
