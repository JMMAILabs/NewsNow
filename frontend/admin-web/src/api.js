// CRUD de artículos contra el API. Sin VITE_API_URL → CRUD en memoria (mock),
// para poder probar el panel sin backend desplegado.
const API_URL = import.meta.env.VITE_API_URL || "";
const useMock = () => !API_URL;

let store = [
  {
    id: "a1",
    title: "NewsNow lanza su plataforma en la nube",
    category: "tecnología",
    body: "El periódico digital NewsNow ha presentado su nueva plataforma serverless...",
    status: "READY",
  },
  {
    id: "a2",
    title: "Los influencers impulsan el tráfico de los medios",
    category: "economía",
    body: "Un estudio revela aumentos de tráfico de hasta el 400%...",
    status: "READY",
  },
];

function headers(token, json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  if (token) h["Authorization"] = token;
  return h;
}

export async function listArticles() {
  if (useMock()) return { articles: [...store], mock: true };
  try {
    const res = await fetch(`${API_URL}/articles`);
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    return { articles: data.articles || [], mock: false };
  } catch {
    return { articles: [...store], mock: true };
  }
}

export async function createArticle(article, token) {
  if (useMock()) {
    const item = { ...article, id: Math.random().toString(36).slice(2, 10), status: "DRAFT" };
    store = [item, ...store];
    return item;
  }
  const res = await fetch(`${API_URL}/articles`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify(article),
  });
  return res.json();
}

export async function updateArticle(id, article, token) {
  if (useMock()) {
    store = store.map((a) => (a.id === id ? { ...a, ...article, status: "DRAFT" } : a));
    return { id, status: "updated" };
  }
  const res = await fetch(`${API_URL}/articles/${id}`, {
    method: "PUT",
    headers: headers(token),
    body: JSON.stringify(article),
  });
  return res.json();
}

export async function deleteArticle(id, token) {
  if (useMock()) {
    store = store.filter((a) => a.id !== id);
    return { id, status: "deleted" };
  }
  const res = await fetch(`${API_URL}/articles/${id}`, {
    method: "DELETE",
    headers: headers(token, false),
  });
  return res.json();
}
