import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./styles/tokens.css";
import "./styles/base.css";
import App from "./App";
import { HubProvider, ToastProvider } from "./lib/store";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastProvider>
      <HubProvider>
        <App />
      </HubProvider>
    </ToastProvider>
  </StrictMode>,
);
