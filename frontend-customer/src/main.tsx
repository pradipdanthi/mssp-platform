import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { BrandProvider } from "./config/BrandContext";
import { EntitlementsProvider } from "./config/EntitlementsContext";
import "./styles.css";
import "./kevantic-app.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrandProvider>
      <BrowserRouter>
        <AuthProvider>
          <EntitlementsProvider>
            <App />
          </EntitlementsProvider>
        </AuthProvider>
      </BrowserRouter>
    </BrandProvider>
  </React.StrictMode>
);
