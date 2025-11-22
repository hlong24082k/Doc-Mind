import Router from "@/router";

import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";


const App = () => (
  <TooltipProvider>
    <Toaster />
    <Sonner />
    <Router />
  </TooltipProvider>
);

export default App;