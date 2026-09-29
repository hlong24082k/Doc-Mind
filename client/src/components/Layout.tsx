import React from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Menu, MessageSquare, FileText, LogOut } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { useAuthStore } from "@/store/authStore";

interface LayoutProps {
  children: React.ReactNode;
}

const navItems = [
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/chat", label: "New Chat", icon: MessageSquare },
];

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const logout = useAuthStore((state) => state.logout);

  const handleLogout = () => {
    logout();
    toast({
      title: "Logged Out",
      description: "You have been successfully logged out.",
    });
    navigate("/login");
  };

  const renderNavLinks = (className?: string) =>
    navItems.map((item) => {
      const Icon = item.icon;
      const isActive = location.pathname === item.to;
      return (
        <Link
          key={item.to}
          to={item.to}
          className={
            className ||
            `flex items-center gap-3 rounded-lg px-3 py-2 transition-all ${
              isActive
                ? "bg-muted text-primary font-semibold"
                : "text-muted-foreground hover:text-primary"
            }`
          }
        >
          <Icon className="h-4 w-4" />
          {item.label}
        </Link>
      );
    });

  return (
    <div className="grid min-h-screen w-full md:grid-cols-[220px_1fr] lg:grid-cols-[280px_1fr]">
      {/* Desktop Sidebar */}
      <aside className="hidden border-r bg-muted/40 md:block">
        <div className="flex h-full max-h-screen flex-col gap-2">
          <div className="flex h-14 items-center border-b px-4 lg:h-[60px] lg:px-6">
            <Link to="/" className="flex items-center gap-2 font-semibold">
              <MessageSquare className="h-6 w-6" />
              <span>Doc-Mind</span>
            </Link>
          </div>
          <div className="flex-1">
            <nav className="grid items-start px-2 text-sm font-medium lg:px-4">
              {renderNavLinks()}
            </nav>
          </div>
          <div className="mt-auto p-4">
            <Separator className="my-4" />
            <Button
              variant="ghost"
              className="w-full justify-start"
              onClick={handleLogout}
            >
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
      </aside>

      {/* Mobile Header and Sidebar */}
      <div className="flex flex-col">
        <header className="flex h-14 items-center gap-4 border-b bg-muted/40 px-4 lg:h-[60px] lg:px-6 md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" className="shrink-0 md:hidden">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle navigation menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="flex flex-col">
              <div className="flex items-center gap-2 font-semibold mb-4">
                <MessageSquare className="h-6 w-6" />
                <span>Doc-Mind</span>
              </div>
              <nav className="grid gap-2 text-base font-medium">
                {renderNavLinks(
                  "flex items-center gap-4 rounded-xl px-3 py-2 text-muted-foreground hover:text-foreground"
                )}
              </nav>
              <div className="mt-auto">
                <Separator className="my-4" />
                <Button
                  variant="ghost"
                  className="w-full justify-start"
                  onClick={handleLogout}
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  Logout
                </Button>
              </div>
            </SheetContent>
          </Sheet>
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <MessageSquare className="h-6 w-6" />
            <span>Doc-Mind</span>
          </Link>
        </header>

        <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;