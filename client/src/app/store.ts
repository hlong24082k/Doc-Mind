import { configureStore } from "@reduxjs/toolkit";
import {
    persistStore,
    persistReducer,
    FLUSH,
    REHYDRATE,
    PAUSE,
    PERSIST,
    PURGE,
    REGISTER,
} from "redux-persist";
import storage from "redux-persist/lib/storage";
import rootReducer from "@/app/reducer"; // Import your combined root reducer

const persistConfig = {
    key: "root",
    version: 1,
    storage,
    // Add whitelist or blacklist here if you want to persist only specific parts of your state
    // For example, to persist only the 'auth' slice:
    // whitelist: ['auth'],
    // If you want to persist everything EXCEPT 'auth', you'd use a blacklist:
    // blacklist: ['auth'],
    // In our auth slice, we're already managing persistence via localStorage for tokens,
    // so you might choose not to persist the auth slice itself with redux-persist,
    // or persist it and manage token removal within the logout action.
    // For simplicity, let's whitelist 'auth' for now if you want the state values to persist.
    // However, given your `authService.ts` already uses localStorage directly,
    // persisting the `auth` slice might lead to duplicate storage.
    // A common pattern is to only persist sensitive info like tokens in `localStorage` directly
    // and use `redux-persist` for other, less sensitive UI state.
    // For now, let's assume you want `auth` state to be persisted by redux-persist as well.
    // If your authSlice `isAuthenticated`, `accessToken`, etc. are derived from localStorage,
    // you might not need to persist the auth slice itself with redux-persist, or adjust how it initializes.
    // Let's assume you want `redux-persist` to manage the state after it's loaded initially.
    whitelist: ['auth'], // Example: only persist the auth slice
};

const persistedReducer = persistReducer(persistConfig, rootReducer); // Use your combined rootReducer here

export const store = configureStore({
    reducer: persistedReducer,
    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: {
                // Ignore these action types from redux-persist
                ignoredActions: [FLUSH, REHYDRATE, PAUSE, PERSIST, PURGE, REGISTER],
            },
        }),
});

export let persistor = persistStore(store);

// Optional: Export types for better useSelector/useDispatch typing
export type AppDispatch = typeof store.dispatch;