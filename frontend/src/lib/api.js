import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Auth relies on httpOnly cookies. This in-memory token is only a same-tab
// fallback for the current session and is never persisted to storage.
let accessToken = null;
export const setAccessToken = (token) => {
  accessToken = token;
};

const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});

export function apiError(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (detail && typeof detail.message === "string") {
    const issues = Array.isArray(detail.instrument_issues)
      ? detail.instrument_issues
          .map((issue) => `${issue.parameter}: ${issue.reason}`)
          .join("; ")
      : "";
    return issues ? `${detail.message} ${issues}` : detail.message;
  }
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export default api;
