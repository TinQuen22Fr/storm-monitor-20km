import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("storm_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const LOURDES = { lat: 43.0951, lon: -0.0434, radius: 20 };

export const getCurrent = (lat = LOURDES.lat, lon = LOURDES.lon) =>
  api.get("/weather/current", { params: { lat, lon } }).then((r) => r.data);

export const getForecast = (lat = LOURDES.lat, lon = LOURDES.lon) =>
  api.get("/weather/forecast", { params: { lat, lon } }).then((r) => r.data);

export const getHistory = (lat = LOURDES.lat, lon = LOURDES.lon, radius_km = LOURDES.radius) =>
  api.get("/weather/history", { params: { lat, lon, radius_km } }).then((r) => r.data);

export const getZones = (lat = LOURDES.lat, lon = LOURDES.lon, radius_km = LOURDES.radius) =>
  api.get("/storms/zones", { params: { lat, lon, radius_km } }).then((r) => r.data);

export const getStrikes = (lat = LOURDES.lat, lon = LOURDES.lon, radius_km = LOURDES.radius, since) =>
  api.get("/lightning/strikes", { params: { lat, lon, radius_km, since } }).then((r) => r.data);

export const getSevere = (lat = LOURDES.lat, lon = LOURDES.lon, hours = 24, radius_km = LOURDES.radius) =>
  api.get("/weather/severe", { params: { lat, lon, hours, radius_km } }).then((r) => r.data);

export const getRainNowcast = (lat = LOURDES.lat, lon = LOURDES.lon) =>
  api.get("/weather/rain-nowcast", { params: { lat, lon } }).then((r) => r.data);

export const getAirQuality = (lat = LOURDES.lat, lon = LOURDES.lon) =>
  api.get("/airquality", { params: { lat, lon } }).then((r) => r.data);

export const getSevereGrid = (param = "t850", hour = 0) =>
  api.get("/weather/severe/grid", { params: { param, hour } }).then((r) => r.data);

export const getSevereGridBulk = () =>
  // Cold-start on a weak Kimsufi Atom may need 30-60 s to (a) reach Open-Meteo
  // over the upstream link, (b) parse the ~1.5 MB JSON, (c) compute the 9
  // per-param matrices. Use a generous timeout for THIS endpoint only.
  api.get("/weather/severe/grid/bulk", { timeout: 90000 }).then((r) => r.data);

export const getSevereProfile = (lat = LOURDES.lat, lon = LOURDES.lon, hour = 0) =>
  api.get("/weather/severe/profile", { params: { lat, lon, hour } }).then((r) => r.data);

export const authRegister = (email, password, name) =>
  api.post("/auth/register", { email, password, name }).then((r) => r.data);

export const authLogin = (email, password) =>
  api.post("/auth/login", { email, password }).then((r) => r.data);

export const authMe = () => api.get("/auth/me").then((r) => r.data);

export const authVerifyEmail = (token) =>
  api.post("/auth/verify-email", { token }).then((r) => r.data);

export const authResendVerification = (email) =>
  api.post("/auth/resend-verification", { email }).then((r) => r.data);

export const adminListUsers = () => api.get("/admin/users").then((r) => r.data);
export const adminDeleteUser = (id) => api.delete(`/admin/users/${id}`).then((r) => r.data);
export const adminForceVerify = (id) => api.post(`/admin/users/${id}/verify`).then((r) => r.data);
export const adminToggleDisable = (id) => api.post(`/admin/users/${id}/disable`).then((r) => r.data);

export const listFavorites = () => api.get("/favorites").then((r) => r.data);
export const createFavorite = (fav) => api.post("/favorites", fav).then((r) => r.data);
export const deleteFavorite = (id) => api.delete(`/favorites/${id}`).then((r) => r.data);

/**
 * Observations terrain communautaires (C2).
 * NB: le token JWT (si présent en localStorage) est déjà injecté automatiquement
 * dans le header `Authorization: Bearer <token>` par l'intercepteur `api` ci-dessus.
 * L'API backend accepte toutefois les observations anonymes (user optionnel).
 */
export const postObservation = (payload) =>
  api.post("/observations", payload).then((r) => r.data);

export const getObservations = (params = {}) =>
  api.get("/observations", { params: { window_s: 7200, ...params } }).then((r) => r.data);

/** Modération admin des observations citoyennes (nécessite un compte is_admin). */
export const adminListObservations = () =>
  api.get("/admin/observations").then((r) => r.data);

export const adminUpdateObservationStatus = (obsId, status) =>
  api.patch(`/admin/observations/${obsId}/status`, { status }).then((r) => r.data);

/** Open-Meteo Geocoding API (gratuit, sans clé) */
export const geocodeSearch = (query) =>
  axios
    .get("https://geocoding-api.open-meteo.com/v1/search", {
      params: { name: query, count: 8, language: "fr", format: "json" },
    })
    .then((r) => r.data?.results || []);
