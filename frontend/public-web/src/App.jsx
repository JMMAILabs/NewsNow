import { useEffect, useState } from "react";
import { getArticles, getDailySummary } from "./api";

export default function App() {
  const [articles, setArticles] = useState([]);
  const [daily, setDaily] = useState(null);
  const [mock, setMock] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([
      getArticles().then((r) => {
        setArticles(r.articles);
        setMock((m) => m || r.mock);
        setError((e) => e || r.error);
      }),
      getDailySummary().then((r) => {
        setDaily(r.daily);
        setMock((m) => m || r.mock);
        setError((e) => e || r.error);
      }),
    ]).finally(() => setLoading(false));
  }, []);

  return (
    <div className="app">
      <header className="site-header">
        <h1>
          News<span>Now</span>
        </h1>
        <p>Las noticias del día, resumidas por IA.</p>
        {mock && <span className="badge">datos de ejemplo · sin API conectada</span>}
      </header>

      {loading && <p className="loading">Cargando las noticias del día…</p>}

      {!loading && error && (
        <p className="error">
          No se han podido cargar las noticias en este momento. Vuelve a intentarlo
          en unos minutos.
        </p>
      )}

      {daily && (
        <section className="daily">
          <h2>🗞️ Resumen del día</h2>
          <p className="intro">{daily.intro}</p>
          <ul>
            {(daily.highlights || []).map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
          <p className="digest">{daily.digest}</p>
        </section>
      )}

      <main className="grid">
        {articles.map((a) => (
          <article key={a.id} className="card">
            <span className="cat">{a.category}</span>
            <h3>{a.title}</h3>
            <p>{a.summary || a.body}</p>
            <div className="tags">
              {(a.tags || []).map((t) => (
                <span key={t}>#{t}</span>
              ))}
            </div>
          </article>
        ))}
      </main>

      <footer className="site-footer">NewsNow · MVP · servido desde S3 + CloudFront</footer>
    </div>
  );
}
