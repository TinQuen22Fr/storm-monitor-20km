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

export const getHistory = (lat = LOURDES.lat, lon = LOURDES.lon) =>
  api.get("/weather/history", { params: { lat, lon } }).then((r) => r.data);

export const getZones = (lat = LOURDES.lat, lon = LOURDES.lon, radius_km = LOURDES.radius) =>
  api.get("/storms/zones", { params: { lat, lon, radius_km } }).then((r) => r.data);

export const getStrikes = (lat = LOURDES.lat, lon = LOURDES.lon, radius_km = LOURDES.radius, since) =>
  api.get("/lightning/strikes", { params: { lat, lon, radius_km, since } }).then((r) => r.data);

export const authRegister = (email, password, name) =>
  api.post("/auth/register", { email, password, name }).then((r) => r.data);

export const authLogin = (email, password) =>
  api.post("/auth/login", { email, password }).then((r) => r.data);

export const authMe = () => api.get("/auth/me").then((r) => r.data);

export const listFavorites = () => api.get("/favorites").then((r) => r.data);
export const createFavorite = (fav) => api.post("/favorites", fav).then((r) => r.data);
export const deleteFavorite = (id) => api.delete(`/favorites/${id}`).then((r) => r.data);
