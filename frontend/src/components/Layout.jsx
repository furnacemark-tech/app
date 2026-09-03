import { useNavigate } from "react-router-dom";
import { useState } from "react";
import {
  LayoutDashboard,
  FlaskConical,
  ClipboardCheck,
  Ruler,
  ScrollText,
  Users,
  AlertTriangle,
  Boxes,
  PackageCheck,
  Building2,
  Gauge,
  ListChecks,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Sidebar, TopBar } from "@/components/Chrome";

const ALL_ROLES = ["admin", "qa", "qc"];
const QA_ROLES = ["admin", "qa"];

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, roles: ALL_ROLES, testId: "nav-dashboard" },
  { to: "/samples", label: "Samples", icon: FlaskConical, roles: ALL_ROLES, testId: "nav-samples" },
  { to: "/batches", label: "Batches", icon: Boxes, roles: ALL_ROLES, testId: "nav-batches" },
  { to: "/products", label: "Products", icon: PackageCheck, roles: ALL_ROLES, testId: "nav-products" },
  { to: "/instruments", label: "Instruments", icon: Gauge, roles: ALL_ROLES, testId: "nav-instruments" },
  { to: "/customers", label: "Customers", icon: Building2, roles: ALL_ROLES, testId: "nav-customers" },
  { to: "/qa-review", label: "QA Review", icon: ClipboardCheck, roles: QA_ROLES, testId: "nav-qa-review" },
  { to: "/qa-queues", label: "QA Queues", icon: ListChecks, roles: QA_ROLES, testId: "nav-qa-queues" },
  { to: "/specifications", label: "Specifications", icon: Ruler, roles: ALL_ROLES, testId: "nav-specifications" },
  { to: "/oos", label: "OOS Log", icon: AlertTriangle, roles: ALL_ROLES, testId: "nav-oos" },
  { to: "/audit", label: "Audit Trail", icon: ScrollText, roles: ALL_ROLES, testId: "nav-audit" },
  { to: "/users", label: "Users", icon: Users, roles: ["admin"], testId: "nav-users" },
];

export const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const items = NAV.filter((n) => n.roles.includes(user?.role));

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex">
      <Sidebar items={items} open={open} onNavigate={() => setOpen(false)} />
      <div className="flex-1 min-w-0">
        <TopBar user={user} onToggleMenu={() => setOpen(!open)} onLogout={handleLogout} />
        <main className="p-4 sm:p-6 max-w-[1600px]">{children}</main>
      </div>
    </div>
  );
};
