import { useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/StatusBadge";

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", initials: "", role: "qc" });

  const load = () => api.get("/users").then(({ data }) => setUsers(data));
  useEffect(() => {
    load();
  }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/users", form);
      toast.success("User created");
      setOpen(false);
      setForm({ email: "", password: "", name: "", initials: "", role: "qc" });
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  const toggle = async (u) => {
    try {
      await api.patch(`/users/${u.id}`, { active: !u.active });
      toast.success(`${u.email} ${u.active ? "deactivated" : "activated"}`);
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  const changeRole = async (u, role) => {
    try {
      await api.patch(`/users/${u.id}`, { role });
      toast.success("Role updated");
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-5" data-testid="users-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">User Management</h1>
          <p className="text-sm text-slate-600 mt-1">Admin only. Role changes are audited.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="add-user-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white">
              <UserPlus className="w-4 h-4 mr-1.5" /> Add user
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-white" aria-describedby="create-user-desc">
            <DialogHeader>
              <DialogTitle>Create user</DialogTitle>
              <p id="create-user-desc" className="text-sm text-slate-600">
                Assign a role to control what this user can access.
              </p>
            </DialogHeader>
            <form onSubmit={create} className="space-y-3" data-testid="create-user-form">
              <div>
                <Label className="label-caps">Full name</Label>
                <Input data-testid="user-name-input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="label-caps">Initials</Label>
                  <Input data-testid="user-initials-input" required value={form.initials} onChange={(e) => setForm({ ...form, initials: e.target.value })} />
                </div>
                <div>
                  <Label className="label-caps">Role</Label>
                  <select
                    data-testid="user-role-select"
                    className="w-full h-9 border border-slate-300 rounded px-2 text-sm bg-white"
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                  >
                    <option value="qc">QC</option>
                    <option value="qa">QA</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
              </div>
              <div>
                <Label className="label-caps">Email</Label>
                <Input type="email" data-testid="user-email-input" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </div>
              <div>
                <Label className="label-caps">Password (min 8 chars)</Label>
                <Input type="password" data-testid="user-password-input" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <Button type="submit" data-testid="submit-user-btn" className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white">
                Create user
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Initials</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody data-testid="users-table-body">
            {users.map((u) => (
              <TableRow key={u.id} data-testid={`user-row-${u.email}`}>
                <TableCell className="font-medium">{u.name}</TableCell>
                <TableCell className="font-mono text-xs">{u.initials}</TableCell>
                <TableCell className="text-xs">{u.email}</TableCell>
                <TableCell>
                  <select
                    data-testid={`role-select-${u.email}`}
                    className="border border-slate-300 rounded px-2 py-1 text-xs bg-white"
                    value={u.role}
                    onChange={(e) => changeRole(u, e.target.value)}
                  >
                    <option value="qc">QC</option>
                    <option value="qa">QA</option>
                    <option value="admin">Admin</option>
                  </select>
                </TableCell>
                <TableCell>
                  <StatusBadge value={u.active ? "Approved" : "Requires Investigation"} />
                </TableCell>
                <TableCell>
                  <Button size="sm" variant="outline" data-testid={`toggle-user-${u.email}`} onClick={() => toggle(u)}>
                    {u.active ? "Deactivate" : "Activate"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
