import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage"; // Import the new SignupPage
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import Layout from "./components/Layout";
import { useAuthStore } from "./store/authStore";

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const fallbackIsLoggedIn =
    typeof window !== "undefined" && window.localStorage.getItem("isLoggedIn") === "true";

  if (!isAuthenticated && !fallbackIsLoggedIn) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const App = () => (
  <TooltipProvider>
    <Toaster />
    <Sonner />
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} /> {/* Add the signup route */}
        <Route path="/" element={<ProtectedRoute><Layout><Index /></Layout></ProtectedRoute>} />
        <Route path="/chat" element={<ProtectedRoute><Layout><ChatPage /></Layout></ProtectedRoute>} />
        <Route path="/chat/:documentId" element={<ProtectedRoute><Layout><ChatPage /></Layout></ProtectedRoute>} />
        <Route path="/documents" element={<ProtectedRoute><Layout><DocumentsPage /></Layout></ProtectedRoute>} />
        {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  </TooltipProvider>
);

export default App;