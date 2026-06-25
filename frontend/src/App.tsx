import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import AdminPage from "./pages/AdminPage";
import AnnotatePage from "./pages/AnnotatePage";
import AutoAnnotatePage from "./pages/AutoAnnotatePage";
import DocumentsPage from "./pages/DocumentsPage";
import LabelsPage from "./pages/LabelsPage";
import LoginPage from "./pages/LoginPage";
import MembersPage from "./pages/MembersPage";
import ProjectLayout from "./pages/ProjectLayout";
import ProjectsPage from "./pages/ProjectsPage";
import RulesPage from "./pages/RulesPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="center-screen">Loading…</div>;
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/" element={<ProjectsPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/projects/:projectId" element={<ProjectLayout />}>
        <Route index element={<Navigate to="annotate" replace />} />
        <Route path="annotate" element={<AnnotatePage />} />
        <Route path="annotate/:documentId" element={<AnnotatePage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="labels" element={<LabelsPage />} />
        <Route path="rules" element={<RulesPage />} />
        <Route path="auto" element={<AutoAnnotatePage />} />
        <Route path="members" element={<MembersPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
