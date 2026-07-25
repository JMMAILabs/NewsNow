// Cliente del API público.
// - Producción (build en S3+CloudFront): NO se define VITE_API_URL → se llama al
//   MISMO origen (`/articles`, `/daily-summary`), que la distribución de CloudFront
//   cachea en el edge (TTL corto). Así la portada absorbe los picos y el fan-in de
//   los shards del GSI se sirve desde la caché, no golpea DynamoDB en cada request.
// - `npm run dev` sin API: datos de ejemplo (mock), para ver la web sin backend.
// - Se puede forzar una URL absoluta (VITE_API_URL, p. ej. contra API GW directo)
//   o el mock (VITE_USE_MOCK=true).
const API_BASE = import.meta.env.VITE_API_URL || "";
const USE_MOCK =
  import.meta.env.VITE_USE_MOCK === "true" ||
  (import.meta.env.DEV && !import.meta.env.VITE_API_URL);

const MOCK = {
  articles: [
    {
      id: "a1",
      category: "tecnología",
      title: "NewsNow lanza su nueva plataforma de noticias en la nube",
      summary:
        "El periódico digital NewsNow ha presentado una plataforma serverless capaz " +
        "de escalar sola durante los picos de tráfico, con un asistente de IA que " +
        "resume las noticias.",
      tags: ["nube", "serverless", "ia"],
    },
    {
      id: "a2",
      category: "economía",
      title: "Los influencers impulsan el tráfico de los medios digitales",
      summary:
        "Un estudio revela aumentos de tráfico de hasta el 400% en pocas horas cuando " +
        "los medios colaboran con influencers, lo que exige infraestructuras elásticas.",
      tags: ["influencers", "tráfico", "medios"],
    },
    {
      id: "a3",
      category: "tecnología",
      title: "La IA generativa transforma las redacciones periodísticas",
      summary:
        "Cada vez más periódicos usan modelos de lenguaje para titulares, clasificación " +
        "y resúmenes automáticos, siempre con supervisión humana.",
      tags: ["ia", "periodismo"],
    },
  ],
  daily: {
    intro: "La tecnología y la economía digital protagonizan la jornada.",
    highlights: [
      "NewsNow lanza su plataforma serverless en la nube",
      "Los influencers disparan el tráfico de los medios",
      "La IA generativa entra en las redacciones",
    ],
    digest:
      "NewsNow ha estrenado una plataforma en la nube que escala sola ante los picos " +
      "de tráfico e integra un asistente de IA para resumir noticias. En paralelo, el " +
      "auge de los influencers dispara el tráfico de los medios, lo que refuerza la " +
      "necesidad de infraestructuras elásticas. Y la IA generativa se consolida como " +
      "apoyo editorial, siempre bajo supervisión humana.",
  },
};

async function getJSON(path, fallback) {
  if (USE_MOCK) return { data: fallback, mock: true };
  try {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(String(res.status));
    return { data: await res.json(), mock: false };
  } catch {
    return { data: fallback, mock: true }; // API caída o inaccesible → datos de ejemplo
  }
}

export async function getArticles() {
  const { data, mock } = await getJSON("/articles", { articles: MOCK.articles });
  return { articles: data.articles || MOCK.articles, mock };
}

export async function getDailySummary() {
  const { data, mock } = await getJSON("/daily-summary", MOCK.daily);
  return { daily: data, mock };
}
