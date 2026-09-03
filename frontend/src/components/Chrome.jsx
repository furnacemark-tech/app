import { NavLink } from "react-router-dom";
import { LogOut, Menu, FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";

export const Sidebar = ({ items, open, onNavigate }) => (
  <aside
    className={`${open ? "block" : "hidden"} lg:block fixed lg:static z-40 inset-y-0 left-0 w-60 bg-white border-r border-slate-200 no-print`}
  >
    <div className="h-14 flex items-center px-4 border-b border-slate-200">
      <div className="w-7 h-7 bg-[#002FA7] flex items-center justify-center rounded-sm mr-2">
        <FlaskConical className="w-4 h-4 text-white" />
      </div>
      <div>
        <div className="font-semibold text-sm leading-tight">SYNTH LIMS</div>
        <div className="text-[10px] text-slate-500 tracking-wider">v1.0</div>
      </div>
    </div>
    <nav className="p-2 space-y-0.5">
      {items.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/"}
          data-testid={n.testId}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-2.5 px-3 py-2 text-sm rounded transition-colors duration-200 ${
              isActive ? "bg-[#002FA7] text-white font-medium" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
            }`
          }
        >
          <n.icon className="w-4 h-4" />
          {n.label}
        </NavLink>
      ))}
    </nav>
  </aside>
);

export const TopBar = ({ user, onToggleMenu, onLogout }) => (
  <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 no-print">
    <button className="lg:hidden p-2" data-testid="mobile-menu-btn" onClick={onToggleMenu}>
      <Menu className="w-5 h-5" />
    </button>
    <div className="hidden lg:block label-caps">Laboratory Information Management System</div>
    <div className="flex items-center gap-3">
      <div className="text-right leading-tight">
        <div className="text-sm font-medium" data-testid="current-user-name">
          {user?.name}
        </div>
        <div className="text-[11px] uppercase tracking-wider text-[#002FA7] font-semibold" data-testid="current-user-role">
          {user?.role}
        </div>
      </div>
      <Button variant="outline" size="sm" data-testid="logout-btn" onClick={onLogout}>
        <LogOut className="w-4 h-4" />
      </Button>
    </div>
  </header>
);
