import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { authService } from '@/api/services/auth.service'; // Adjust path as needed
import { LoginRequest, LoginResponse } from '@/api/types/auth'; // Adjust path as needed

// Define the shape of your authentication state
interface AuthState {
  isAuthenticated: boolean;
  user: { username: string } | null; // You might want to expand this with more user info
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

// Initial state for the auth slice
const initialState: AuthState = {
  isAuthenticated: localStorage.getItem('isLoggedIn') === 'true',
  user: null, // Initialize user as null, you might fetch this after login
  status: 'idle',
  error: null,
};

// Async Thunk for login
// createAsyncThunk automatically dispatches pending, fulfilled, and rejected actions
export const loginUser = createAsyncThunk(
  'auth/login',
  async (credentials: LoginRequest, { rejectWithValue }) => {
    try {
      const response = await authService.login(credentials);
      // The authService already stores tokens in localStorage,
      // but we return the response for the reducer to update the state
      return response;
    } catch (error: any) {
      // You can customize error handling based on your API response structure
      return rejectWithValue(error.response?.data?.message || error.message);
    }
  }
);

// Async Thunk for registration
export const registerUser = createAsyncThunk(
  'auth/register',
  async (credentials: LoginRequest, { rejectWithValue }) => {
    try {
      await authService.register(credentials);
      // Registration typically doesn't return tokens directly, just a success
      return;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || error.message);
    }
  }
);

// Auth Slice
export const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    // Synchronous logout action
    logout: (state) => {
      authService.logout(); // Clear localStorage
      state.isAuthenticated = false;
      state.user = null;
      state.status = 'idle';
      state.error = null;
    },
    // Action to manually set authentication status (e.g., from refresh token logic if you implement it)
    setAuthenticated: (state, action: PayloadAction<boolean>) => {
      state.isAuthenticated = action.payload;
    },
    // You could add an action to set user details after login if not part of login response
    setUser: (state, action: PayloadAction<{ username: string } | null>) => {
      state.user = action.payload;
    },
    clearAuthError: (state) => {
      state.error = null;
    }
  },
  extraReducers: (builder) => {
    builder
      // Login Thunk Reducers
      .addCase(loginUser.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(loginUser.fulfilled, (state, action: PayloadAction<LoginResponse>) => {
        state.status = 'succeeded';
        state.isAuthenticated = true;
        // Assuming your login response might have user info, otherwise you'd fetch it separately
        // For now, let's just set a dummy user based on the request, or you can leave it null
        // If your LoginResponse includes user info, you can set it like:
        // state.user = action.payload.user;
        // For this example, we'll set a placeholder
        state.user = { username: "logged_in_user" }; // Replace with actual user info from payload if available
      })
      .addCase(loginUser.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Login failed';
        state.isAuthenticated = false;
        state.user = null;
      })
      // Register Thunk Reducers
      .addCase(registerUser.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(registerUser.fulfilled, (state) => {
        state.status = 'succeeded';
        // After successful registration, you might want to automatically log them in
        // or redirect to a login page. For now, just set status.
      })
      .addCase(registerUser.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Registration failed';
      });
  },
});

// Export actions
export const { logout, setAuthenticated, setUser, clearAuthError } = authSlice.actions;

// Export the reducer
export default authSlice.reducer;
