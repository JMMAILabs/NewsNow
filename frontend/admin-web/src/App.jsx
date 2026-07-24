import { useEffect, useState } from "react";
import { getSession, login, logout } from "./auth";
import { createArticle, deleteArticle, listArticles, updateArticle } from "./api";

const EMPTY = { title: "", category: "general", body: "" };

function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");
  const [err, setErr] = useState("");

  function submit(e) {
    e.preventDefault();
    try {
      onLogin(login(email, pass));
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <h1>
        News<span>Now</span> · Admin
      </h1>
      <p>Panel de edición de artículos</p>
      <input type="email" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input
        type="password"
        placeholder="contraseña"
        value={pass}
        onChange={(e) => setPass(e.target.value)}
      />
      {err && <span className="err">{err}</span>}
      <button type="submit">Entrar</button>
      <small>Demo: cualquier email/contraseña. En producción → Amazon Cognito.</small>
    </form>
  );
}

export default function App() {
  const [session, setSession] = useState(getSession());
  const [articles, setArticles] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);
  const [mock, setMock] = useState(false);

  async function refresh() {
    const r = await listArticles();
    setArticles(r.articles);
    setMock(r.mock);
  }

  useEffect(() => {
    if (session) refresh();
  }, [session]);

  if (!session) return <Login onLogin={setSession} />;

  async function submit(e) {
    e.preventDefault();
    if (editing) await updateArticle(editing, form, session.token);
    else await createArticle(form, session.token);
    setForm(EMPTY);
    setEditing(null);
    refresh();
  }

  function edit(a) {
    setForm({ title: a.title, category: a.category, body: a.body || "" });
    setEditing(a.id);
  }

  async function remove(id) {
    await deleteArticle(id, session.token);
    refresh();
  }

  return (
    <div className="admin">
      <header>
        <h1>
          News<span>Now</span> · Admin
        </h1>
        <div className="tools">
          {mock && <span className="badge">modo mock · sin API</span>}
          <span className="user">{session.email}</span>
          <button
            onClick={() => {
              logout();
              setSession(null);
            }}
          >
            Salir
          </button>
        </div>
      </header>

      <form className="editor" onSubmit={submit}>
        <h2>{editing ? "Editar artículo" : "Nuevo artículo"}</h2>
        <input
          placeholder="Título"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          required
        />
        <input
          placeholder="Categoría"
          value={form.category}
          onChange={(e) => setForm({ ...form, category: e.target.value })}
        />
        <textarea
          placeholder="Cuerpo de la noticia"
          rows={5}
          value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })}
          required
        />
        <div className="actions">
          <button type="submit">{editing ? "Guardar cambios" : "Crear artículo"}</button>
          {editing && (
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setForm(EMPTY);
                setEditing(null);
              }}
            >
              Cancelar
            </button>
          )}
        </div>
      </form>

      <ul className="list">
        {articles.map((a) => (
          <li key={a.id}>
            <div className="meta">
              <strong>{a.title}</strong>
              <span className="cat">{a.category}</span>
              {a.status && <span className={`st st-${a.status.toLowerCase()}`}>{a.status}</span>}
            </div>
            <div className="row-actions">
              <button onClick={() => edit(a)}>Editar</button>
              <button className="danger" onClick={() => remove(a.id)}>
                Borrar
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
