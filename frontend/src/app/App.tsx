import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./Layout";
import { CollectionsPage } from "../pages/CollectionsPage";
import { CollectionPage } from "../pages/CollectionPage";
import { ConversationPage } from "../pages/ConversationPage";
import { SettingsPage } from "../pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<CollectionsPage />} />
          <Route path="/collections/:collectionId" element={<CollectionPage />} />
          <Route path="/conversations/:conversationId" element={<ConversationPage />} />
          <Route path="/settings" element={<Navigate to="/settings/models" replace />} />
          <Route path="/settings/models" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
