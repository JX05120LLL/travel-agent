const ACCESS_TOKEN_STORAGE_KEY = "travel_agent_access_token";
const SESSION_STORAGE_KEY = "travel_agent_session_id";
const {
  mode,
  registerEndpoint,
  loginEndpoint,
  meEndpoint,
  appPage,
  loginPage,
} = window.TRAVEL_AGENT_AUTH_CONFIG;

const authStatus = document.getElementById("authStatus");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const loginUsernameInput = document.getElementById("loginUsername");
const loginPasswordInput = document.getElementById("loginPassword");
const registerUsernameInput = document.getElementById("registerUsername");
const registerPasswordInput = document.getElementById("registerPassword");
const loginSubmitBtn = document.getElementById("loginSubmitBtn");
const registerSubmitBtn = document.getElementById("registerSubmitBtn");


function setAuthStatus(message, type = "info") {
  if (!authStatus) {
    return;
  }
  authStatus.textContent = message || "";
  authStatus.classList.remove("is-error", "is-success");
  if (type === "error") {
    authStatus.classList.add("is-error");
  } else if (type === "success") {
    authStatus.classList.add("is-success");
  }
}


function setSubmitLoading(kind, loading) {
  if (kind === "login" && loginSubmitBtn) {
    loginSubmitBtn.disabled = loading;
    loginSubmitBtn.textContent = loading ? "登录中..." : "登录";
  }
  if (kind === "register" && registerSubmitBtn) {
    registerSubmitBtn.disabled = loading;
    registerSubmitBtn.textContent = loading ? "注册中..." : "注册";
  }
}


function setAccessToken(token) {
  if (token) {
    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  }
}


function clearStoredSessionSelection() {
  localStorage.removeItem(SESSION_STORAGE_KEY);
}


async function fetchAuthenticatedUser(token) {
  if (!token) {
    return null;
  }
  const response = await fetch(meEndpoint, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`校验登录状态失败：${response.status}`);
  }
  return response.json();
}


async function handleLoginSubmit(event) {
  event.preventDefault();
  const username = loginUsernameInput?.value.trim() || "";
  const password = loginPasswordInput?.value || "";
  if (!username || !password) {
    setAuthStatus("请输入用户名和密码。", "error");
    return;
  }

  setSubmitLoading("login", true);
  setAuthStatus("");
  try {
    const response = await fetch(loginEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ username, password }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `登录失败：${response.status}`);
    }

    setAccessToken(payload.access_token || "");
    clearStoredSessionSelection();
    window.location.href = appPage;
  } catch (error) {
    setAuthStatus(error.message || "登录失败，请重试。", "error");
  } finally {
    setSubmitLoading("login", false);
  }
}


async function handleRegisterSubmit(event) {
  event.preventDefault();
  const username = registerUsernameInput?.value.trim() || "";
  const password = registerPasswordInput?.value || "";
  if (!username || !password) {
    setAuthStatus("请输入注册用户名和密码。", "error");
    return;
  }

  setSubmitLoading("register", true);
  setAuthStatus("");
  try {
    const response = await fetch(registerEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ username, password }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `注册失败：${response.status}`);
    }

    const loginUrl = new URL(loginPage, window.location.origin);
    loginUrl.searchParams.set("username", payload.username || username);
    loginUrl.searchParams.set("registered", "1");
    window.location.href = loginUrl.toString();
  } catch (error) {
    setAuthStatus(error.message || "注册失败，请重试。", "error");
  } finally {
    setSubmitLoading("register", false);
  }
}


async function initializeAuthPage() {
  const existingToken = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY) || "";
  if (existingToken) {
    try {
      const user = await fetchAuthenticatedUser(existingToken);
      if (user) {
        clearStoredSessionSelection();
        window.location.href = appPage;
        return;
      }
      setAccessToken("");
    } catch (_error) {
      setAccessToken("");
    }
  }

  if (mode === "login") {
    const params = new URLSearchParams(window.location.search);
    const username = params.get("username") || "";
    const registered = params.get("registered") === "1";
    if (loginUsernameInput && username) {
      loginUsernameInput.value = username;
    }
    if (registered) {
      setAuthStatus("注册成功，请登录。", "success");
    }
    loginUsernameInput?.focus();
  } else {
    registerUsernameInput?.focus();
  }
}


loginForm?.addEventListener("submit", handleLoginSubmit);
registerForm?.addEventListener("submit", handleRegisterSubmit);
initializeAuthPage();
