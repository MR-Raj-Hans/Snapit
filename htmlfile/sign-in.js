function togglePwd() {
  const p = document.getElementById("pwd");
  p.type = p.type === "password" ? "text" : "password";
}

document.getElementById("signinBtn").addEventListener("click", () => {
  alert("Sign in clicked");
});
