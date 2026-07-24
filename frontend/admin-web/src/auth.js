// Auth de la demo (mock). En producción se sustituye por Amazon Cognito, cuyo
// User Pool ya está provisionado en terraform/auth.tf: login → JWT → se envía en
// la cabecera Authorization al API (que lo valida con el JWT authorizer).
const KEY = "newsnow_admin_session";

export function getSession() {
  const raw = localStorage.getItem(KEY);
  return raw ? JSON.parse(raw) : null;
}

export function login(email, password) {
  if (!email || !password) throw new Error("Introduce email y contraseña.");
  // Mock: cualquier credencial vale y guardamos un "token" de pega.
  const session = { email, token: "mock-jwt-token" };
  localStorage.setItem(KEY, JSON.stringify(session));
  return session;
}

export function logout() {
  localStorage.removeItem(KEY);
}
