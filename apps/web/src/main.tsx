import { StrictMode } from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles/index.css";
import "./styles/app-shell.css";
import "./styles/panels.css";
import "./styles/database.css";
import "./styles/chat.css";
import "./styles/settings.css";
import "./styles/modal-menu.css";
import "./styles/workflow.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
