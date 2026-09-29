import type {
  LoginRequest,
  LoginResponse
} from "@/api/types/auth.ts";

import {
  apiAuthLogin,
  apiRegister
} from "../config.ts";
import { apiFetch } from "../apiClient.ts";


/**
 * Handles authentication: login, refresh, logout.
 */
export const authService = {
  async register({ username, password }: LoginRequest): Promise<void> {
    const _ = await apiFetch<void>(apiRegister, {
      method: "POST",
      auth: false,
      body: JSON.stringify({ username, password }),
    }); 
  },

  /**
   * Perform login and store tokens.
   */
  async login({ username, password }: LoginRequest): Promise<LoginResponse> {
    const formBody = new URLSearchParams({
      username,
      password,
    });

    const response = await apiFetch<LoginResponse>(apiAuthLogin, {
      method: "POST",
      auth: false,
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formBody,
    });

    localStorage.setItem("access_token", response.access_token);
    localStorage.setItem("token_type", response.token_type);
    localStorage.setItem("isLoggedIn", "true");
    return response;
  },

  logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("token_type");
    localStorage.removeItem("isLoggedIn");
  },
};