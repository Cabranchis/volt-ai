/**
 * Where each reservoir XM reports sits on the map, and the name people know it by.
 * XM publishes no coordinates, so these are placed by hand at about 0.1 degrees (10 km): enough
 * to put a bubble in the right valley of a country-sized map, never to survey a dam. Keys are the
 * names XM uses in its daily series (ListadoEmbalses).
 */
export interface ReservoirSite {
  label: string;
  lat: number;
  lon: number;
}

export const RESERVOIR_SITES: Readonly<Record<string, ReservoirSite>> = {
  "AGREGADO BOGOTA": { label: "Agregado Bogotá", lat: 5.0, lon: -73.85 },
  ALTOANCHICAYA: { label: "Alto Anchicayá", lat: 3.62, lon: -76.9 },
  AMANI: { label: "Amaní (Miel I)", lat: 5.55, lon: -74.95 },
  BETANIA: { label: "Betania", lat: 2.7, lon: -75.43 },
  CALIMA1: { label: "Calima", lat: 3.94, lon: -76.52 },
  CHUZA: { label: "Chuza (Chingaza)", lat: 4.65, lon: -73.72 },
  "EL QUIMBO": { label: "El Quimbo", lat: 2.23, lon: -75.62 },
  ESMERALDA: { label: "Esmeralda (Chivor)", lat: 4.93, lon: -73.37 },
  GUAVIO: { label: "Guavio", lat: 4.79, lon: -73.24 },
  ITUANGO: { label: "Ituango", lat: 7.13, lon: -75.66 },
  MIRAFLORES: { label: "Miraflores", lat: 6.78, lon: -75.25 },
  MUNA: { label: "Muña", lat: 4.52, lon: -74.26 },
  PENOL: { label: "Peñol (Guatapé)", lat: 6.24, lon: -75.17 },
  PLAYAS: { label: "Playas", lat: 6.33, lon: -75.02 },
  "PORCE II": { label: "Porce II", lat: 6.82, lon: -75.12 },
  "PORCE III": { label: "Porce III", lat: 6.93, lon: -74.98 },
  PRADO: { label: "Prado", lat: 3.76, lon: -74.88 },
  PUNCHINA: { label: "Punchiná", lat: 6.2, lon: -74.96 },
  RIOGRANDE2: { label: "Riogrande II", lat: 6.5, lon: -75.45 },
  SALVAJINA: { label: "Salvajina", lat: 2.97, lon: -76.7 },
  "SAN LORENZO": { label: "San Lorenzo", lat: 6.13, lon: -75.0 },
  TOPOCORO: { label: "Topocoro (Sogamoso)", lat: 6.95, lon: -73.5 },
  TRONERAS: { label: "Troneras", lat: 6.73, lon: -75.28 },
  URRA1: { label: "Urrá", lat: 8.0, lon: -76.24 },
};

/** The readable name of a reservoir; an unknown one falls back to XM's own name. */
export function reservoirLabel(name: string): string {
  return RESERVOIR_SITES[name]?.label ?? name.charAt(0) + name.slice(1).toLowerCase();
}
