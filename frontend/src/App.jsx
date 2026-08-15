import { BrowserRouter, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import "leaflet/dist/leaflet.css";
import "@/App.css";
import AdminPage from "@/pages/AdminPage";
import Dashboard from "@/pages/Dashboard";
import DetectorPage from "@/pages/DetectorPage";
import DetectorTunePage from "@/pages/DetectorTunePage";
import GrelePage from "@/pages/GrelePage";
import History from "@/pages/History";
import PrevisionsPage from "@/pages/PrevisionsPage";
import VerifyEmailPage from "@/pages/VerifyEmailPage";
import VigilancePage from "@/pages/VigilancePage";
import ReplayPage from "@/pages/ReplayPage";
import { AuthProvider } from "@/lib/auth";
import { initNativePush } from "@/lib/push";
import { Toaster } from "@/components/ui/sonner";
import { NativeAppExit } from "@/components/NativeAppExit";
import { SafeAreaTop } from "@/components/SafeAreaTop";

function App() {
  // APK : ré-arme les listeners push natifs à chaque lancement (affichage des
  // notifications FCM reçues au premier plan + re-liaison du token au compte)
  useEffect(() => {
    initNativePush();
  }, []);

  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/vigilance" element={<VigilancePage />} />
          <Route path="/grele" element={<GrelePage />} />
          <Route path="/previsions" element={<PrevisionsPage />} />
          <Route path="/replay" element={<ReplayPage />} />
          <Route path="/detector" element={<DetectorPage />} />
          <Route path="/detector/tune" element={<DetectorTunePage />} />
          <Route path="/historique" element={<History />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </BrowserRouter>
      <NativeAppExit />
      <SafeAreaTop />
      <Toaster position="top-right" />
    </AuthProvider>
  );
}

export default App;
