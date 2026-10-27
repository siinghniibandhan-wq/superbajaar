import React from "react";
import { createRoot } from "react-dom/client";
import App from "../frontend/src/app/App.jsx";
import "../frontend/src/styles.css";

createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
