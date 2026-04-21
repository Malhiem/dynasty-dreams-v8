// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Settings, UserPlus, Trash2, Mail, Shield } from "lucide-react";
import { useState } from "react";
import { toast } from "@/hooks/use-toast";

interface Owner {
  id: string;
  teamName: string;
  ownerName: string;
  email: string;
  joinedDate: string;
  role: "commissioner" | "owner";
  lastLogin: string;
  loginCount: number;
}

const initialOwners: Owner[] = [
  { id: "1", teamName: "Arctic Wolves", ownerName: "Mike Johnson", email: "mike.j@email.com", joinedDate: "2022-09-01", role: "commissioner", lastLogin: "2026-02-07 09:15", loginCount: 342 },
  { id: "2", teamName: "Blizzard Kings", ownerName: "Sarah Chen", email: "sarah.c@email.com", joinedDate: "2022-09-01", role: "owner", lastLogin: "2026-02-06 21:30", loginCount: 289 },
  { id: "3", teamName: "Frozen Thunder", ownerName: "Jake Williams", email: "jake.w@email.com", joinedDate: "2022-09-01", role: "owner", lastLogin: "2026-02-07 08:45", loginCount: 215 },
  { id: "4", teamName: "Ice Phantoms", ownerName: "Emily Davis", email: "emily.d@email.com", joinedDate: "2022-09-15", role: "owner", lastLogin: "2026-02-05 14:20", loginCount: 178 },
  { id: "5", teamName: "Northern Lights", ownerName: "Chris Martinez", email: "chris.m@email.com", joinedDate: "2022-10-01", role: "owner", lastLogin: "2026-02-07 07:00", loginCount: 301 },
  { id: "6", teamName: "Polar Bears", ownerName: "Amanda Lee", email: "amanda.l@email.com", joinedDate: "2022-09-01", role: "owner", lastLogin: "2026-02-04 18:10", loginCount: 156 },
  { id: "7", teamName: "Snow Hawks", ownerName: "David Brown", email: "david.b@email.com", joinedDate: "2023-01-10", role: "owner", lastLogin: "2026-01-28 11:05", loginCount: 87 },
  { id: "8", teamName: "Tundra Titans", ownerName: "Rachel Kim", email: "rachel.k@email.com", joinedDate: "2022-09-01", role: "owner", lastLogin: "2026-02-06 16:40", loginCount: 264 },
  { id: "9", teamName: "Winter Wolves", ownerName: "Tom Anderson", email: "tom.a@email.com", joinedDate: "2022-09-01", role: "owner", lastLogin: "2026-02-07 10:00", loginCount: 198 },
  { id: "10", teamName: "Glacier Force", ownerName: "Lisa Park", email: "lisa.p@email.com", joinedDate: "2023-06-15", role: "owner", lastLogin: "2026-02-03 09:30", loginCount: 112 },
  { id: "11", teamName: "Avalanche Elite", ownerName: "Ryan Scott", email: "ryan.s@email.com", joinedDate: "2022-09-01", role: "owner", lastLogin: "2026-02-06 22:15", loginCount: 245 },
  { id: "12", teamName: "Frost Giants", ownerName: "Megan Taylor", email: "megan.t@email.com", joinedDate: "2022-09-01", role: "owner", lastLogin: "2026-02-07 06:50", loginCount: 277 },
];

const TeamsOwners = () => {
  const [owners, setOwners] = useState<Owner[]>(initialOwners);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");
  const [newOwnerName, setNewOwnerName] = useState("");
  const [newEmail, setNewEmail] = useState("");

  const handleAddOwner = () => {
    if (!newTeamName.trim() || !newOwnerName.trim() || !newEmail.trim()) {
      toast({ title: "Missing fields", description: "Please fill in all fields.", variant: "destructive" });
      return;
    }

    const newOwner: Owner = {
      id: Date.now().toString(),
      teamName: newTeamName,
      ownerName: newOwnerName,
      email: newEmail,
      joinedDate: new Date().toISOString().split("T")[0],
      role: "owner",
      lastLogin: "Never",
      loginCount: 0,
    };

    setOwners(prev => [...prev, newOwner]);
    setNewTeamName("");
    setNewOwnerName("");
    setNewEmail("");
    setAddDialogOpen(false);
    toast({ title: "Owner added", description: `${newOwnerName} has been added as owner of ${newTeamName}.` });
  };

  const handleRemoveOwner = (owner: Owner) => {
    setOwners(prev => prev.filter(o => o.id !== owner.id));
    toast({ title: "Owner removed", description: `${owner.ownerName} has been removed from ${owner.teamName}.` });
  };

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/20 border border-primary/30">
            <Settings className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Teams & Owners</h1>
            <p className="text-muted-foreground">Manage team ownership across the league</p>
          </div>
        </div>

        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>League Roster</CardTitle>
              <CardDescription>{owners.length} teams in the league</CardDescription>
            </div>
            <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="ice" size="sm">
                  <UserPlus className="h-4 w-4 mr-2" />
                  Add Owner
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-card border-border">
                <DialogHeader>
                  <DialogTitle>Add New Owner</DialogTitle>
                  <DialogDescription>Add a new team and owner to the league.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2">
                    <Label>Team Name</Label>
                    <Input
                      placeholder="e.g. Arctic Wolves"
                      value={newTeamName}
                      onChange={e => setNewTeamName(e.target.value)}
                      className="bg-secondary border-border"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Owner Name</Label>
                    <Input
                      placeholder="e.g. John Smith"
                      value={newOwnerName}
                      onChange={e => setNewOwnerName(e.target.value)}
                      className="bg-secondary border-border"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Email</Label>
                    <Input
                      type="email"
                      placeholder="e.g. john@email.com"
                      value={newEmail}
                      onChange={e => setNewEmail(e.target.value)}
                      className="bg-secondary border-border"
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setAddDialogOpen(false)}>Cancel</Button>
                  <Button onClick={handleAddOwner}>Add Owner</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-muted-foreground">Team</TableHead>
                  <TableHead className="text-muted-foreground">Owner</TableHead>
                  <TableHead className="text-muted-foreground">Email</TableHead>
                  <TableHead className="text-muted-foreground">Role</TableHead>
                  <TableHead className="text-muted-foreground">Last Login</TableHead>
                  <TableHead className="text-muted-foreground">Logins</TableHead>
                  <TableHead className="text-muted-foreground">Joined</TableHead>
                  <TableHead className="text-muted-foreground text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {owners.map(owner => (
                  <TableRow key={owner.id} className="border-border">
                    <TableCell className="font-medium">{owner.teamName}</TableCell>
                    <TableCell>{owner.ownerName}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Mail className="h-3.5 w-3.5" />
                        {owner.email}
                      </div>
                    </TableCell>
                    <TableCell>
                      {owner.role === "commissioner" ? (
                        <Badge variant="default" className="gap-1">
                          <Shield className="h-3 w-3" />
                          Commissioner
                        </Badge>
                      ) : (
                        <Badge variant="secondary">Owner</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">{owner.lastLogin}</TableCell>
                    <TableCell className="text-muted-foreground">{owner.loginCount}</TableCell>
                    <TableCell className="text-muted-foreground">{owner.joinedDate}</TableCell>
                    <TableCell className="text-right">
                      {owner.role !== "commissioner" && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive hover:bg-destructive/10">
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent className="bg-card border-border">
                            <AlertDialogHeader>
                              <AlertDialogTitle>Remove Owner</AlertDialogTitle>
                              <AlertDialogDescription>
                                Are you sure you want to remove {owner.ownerName} from {owner.teamName}? This action cannot be undone.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction
                                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                onClick={() => handleRemoveOwner(owner)}
                              >
                                Remove
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
};

export default TeamsOwners;
