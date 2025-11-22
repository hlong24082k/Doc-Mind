import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./global/globals.css";

createRoot(document.getElementById("root")!).render(<App />);
