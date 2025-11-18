import { combineReducers } from '@reduxjs/toolkit';
import authReducer from '@/features/authSlice';
// Import other reducers as you create them, e.g.:
// import counterReducer from '../features/counter/counterSlice';

const rootReducer = combineReducers({
  auth: authReducer,
  // counter: counterReducer, // Add other reducers here
});

export default rootReducer;

// Define the RootState type for better TypeScript support
export type RootState = ReturnType<typeof rootReducer>;