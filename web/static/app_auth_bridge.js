const appLoginPage = window.TRAVEL_AGENT_CONFIG?.loginPage || "/login";
const originalFetch = window.fetch.bind(window);
const logoutBtnBridge = document.getElementById("logoutBtn");

window.fetch = async function fetchWithAuthRedirect(input, init) {
  const response = await originalFetch(input, init);
  if (response.status === 401) {
    localStorage.removeItem("travel_agent_access_token");
    window.location.replace(appLoginPage);
  }
  return response;
};

logoutBtnBridge?.addEventListener("click", () => {
  window.setTimeout(() => {
    localStorage.removeItem("travel_agent_access_token");
    window.location.replace(appLoginPage);
  }, 0);
});

window.setTimeout(() => {
  if (!localStorage.getItem("travel_agent_access_token")) {
    window.location.replace(appLoginPage);
  }
}, 0);
