import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import QAQueues from "@/pages/QAQueues";
import Batches from "@/pages/Batches";
import BatchDetail from "@/pages/BatchDetail";
import Products from "@/pages/Products";
import Customers from "@/pages/Customers";
import Instruments from "@/pages/Instruments";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";
import { ChangePasswordGate } from "@/components/auth/ChangePasswordGate";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Samples from "@/pages/Samples";
import SampleDetail from "@/pages/SampleDetail";
import Specifications from "@/pages/Specifications";
import QAReview from "@/pages/QAReview";
import AuditTrail from "@/pages/AuditTrail";
import OOSLog from "@/pages/OOSLog";
import UsersPage from "@/pages/UsersPage";
import "@/App.css";

const QA_ROLES = ["admin", "qa"];
const ADMIN_ROLES = ["admin"];

function Protected({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8 text-sm text-slate-500">Checking session…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role))
    return <div className="p-8 text-sm text-red-700" data-testid="access-denied">Access denied for your role.</div>;
  if (user.must_change_password)
    return (
      <Layout>
        <ChangePasswordGate />
      </Layout>
    );
  return (
    <Layout>
      <ChangePasswordGate />
      {children}
    </Layout>
  );
}

function LoginRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8 text-sm text-slate-500">Checking session…</div>;
  if (user) return <Navigate to="/" replace />;
  return <Login />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" richColors />
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route path="/" element={<Protected><Dashboard /></Protected>} />
          <Route path="/samples" element={<Protected><Samples /></Protected>} />
          <Route path="/qa-queues" element={<Protected roles={QA_ROLES}><QAQueues /></Protected>} />
          <Route path="/batches" element={<Protected><Batches /></Protected>} />
          <Route path="/batches/:id" element={<Protected><BatchDetail /></Protected>} />
          <Route path="/products" element={<Protected><Products /></Protected>} />
          <Route path="/customers" element={<Protected><Customers /></Protected>} />
          <Route path="/instruments" element={<Protected><Instruments /></Protected>} />
          <Route path="/samples/:id" element={<Protected><SampleDetail /></Protected>} />
          <Route path="/specifications" element={<Protected><Specifications /></Protected>} />
          <Route path="/qa-review" element={<Protected roles={QA_ROLES}><QAReview /></Protected>} />
          <Route path="/oos" element={<Protected><OOSLog /></Protected>} />
          <Route path="/audit" element={<Protected><AuditTrail /></Protected>} />
          <Route path="/users" element={<Protected roles={["admin"]}><UsersPage /></Protected>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
