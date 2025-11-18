import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { store, persistor } from './app/store';
import { Provider } from 'react-redux';
import { PersistGate } from 'redux-persist/integration/react';

import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage"; // Import the new SignupPage
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import Layout from "./components/Layout";

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isLoggedIn = localStorage.getItem("isLoggedIn") === "true";
  if (!isLoggedIn) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const App = () => (
  <Provider store={store}>
    <PersistGate loading={null} persistor={persistor}>
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
    </PersistGate>
  </Provider>
);

export default App;