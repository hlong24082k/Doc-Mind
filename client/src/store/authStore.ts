import { create } from "zustand";
import { authService } from "@/api/services/auth.service";
import type { LoginRequest } from "@/api/types/auth";

type AuthStatus = "idle" | "loading" | "succeeded" | "failed";

interface AuthState {
  isAuthenticated: boolean;
  user: { username: string } | null;
  status: AuthStatus;
  error: string | null;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (credentials: LoginRequest) => Promise<void>;
  logout: () => void;
  setUser: (user: { username: string } | null) => void;
  clearError: () => void;
}

const hasWindow = typeof window !== "undefined";

const getInitialAuthState = (): boolean => {
  if (!hasWindow) {
    return false;
  }
  return window.localStorage.getItem("isLoggedIn") === "true";
};

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: getInitialAuthState(),
  user: null,
  status: "idle",
  error: null,

  login: async (credentials) => {
    set({ status: "loading", error: null });
    try {
      await authService.login(credentials);

      set({
        status: "succeeded",
        isAuthenticated: true,
        user: { username: credentials.username },
      });
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data
          ?.message ||
        (error as { message?: string })?.message ||
        "Login failed";

      set({
        status: "failed",
        error: message,
        isAuthenticated: false,
        user: null,
      });

      throw new Error(message);
    }
  },

  register: async (credentials) => {
    set({ status: "loading", error: null });
    try {
      await authService.register(credentials);
      set({ status: "succeeded" });
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { message?: string } }; message?: string })?.response?.data
          ?.message ||
        (error as { message?: string })?.message ||
        "Registration failed";

      set({
        status: "failed",
        error: message,
      });

      throw new Error(message);
    }
  },

  logout: () => {
    authService.logout();
    set({
      isAuthenticated: false,
      user: null,
      status: "idle",
      error: null,
    });
  },

  setUser: (user) => set({ user }),

  clearError: () => set({ error: null }),
}));

