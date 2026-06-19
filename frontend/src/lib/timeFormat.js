/**
 * Formatte une date/timestamp dans le fuseau horaire du lieu surveillé.
 *
 * La timezone est récupérée depuis le backend (Open-Meteo retourne
 * automatiquement la TZ IANA basée sur lat/lon, et gère DST été/hiver).
 *
 * Default = Europe/Paris (Lourdes par défaut). Le Dashboard appelle
 * setLocalTimezone() après le premier fetch /api/weather/current.
 *
 * Toutes les composantes de l'app DOIVENT passer par ce helper au lieu
 * d'appeler directement Date.prototype.toLocaleString — sinon l'heure
 * affichée serait celle du navigateur du visiteur, pas du lieu surveillé.
 */

let _localTimezone = "Europe/Paris";

export function setLocalTimezone(tz) {
  if (tz && typeof tz === "string") _localTimezone = tz;
}

export function getLocalTimezone() {
  return _localTimezone;
}

/** Convertit une valeur (timestamp s ou ms, ISO string, Date) en Date. */
function toDate(value) {
  if (value instanceof Date) return value;
  if (typeof value === "number") {
    // Heuristic: seconds vs milliseconds
    return new Date(value < 1e12 ? value * 1000 : value);
  }
  return new Date(value);
}

/** Format date + heure complet en heure locale du lieu surveillé. */
export function fmtLocal(value, options = {}, tz = _localTimezone) {
  return toDate(value).toLocaleString("fr-FR", { timeZone: tz, ...options });
}

/** Format heure uniquement (HH:MM par défaut). */
export function fmtLocalTime(value, options = {}, tz = _localTimezone) {
  return toDate(value).toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz,
    ...options,
  });
}

/** Format date uniquement. */
export function fmtLocalDate(value, options = {}, tz = _localTimezone) {
  return toDate(value).toLocaleDateString("fr-FR", {
    timeZone: tz,
    ...options,
  });
}

/** Retourne l'abréviation TZ courante (ex: "GMT+2" ou "CEST"). */
export function getTimezoneAbbreviation() {
  try {
    const formatter = new Intl.DateTimeFormat("fr-FR", {
      timeZone: _localTimezone,
      timeZoneName: "shortOffset",
    });
    const parts = formatter.formatToParts(new Date());
    const tzPart = parts.find((p) => p.type === "timeZoneName");
    return tzPart?.value || "";
  } catch {
    return "";
  }
}
