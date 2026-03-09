function togglePwd() {
  const p = document.getElementById("pwd");
  p.type = p.type === "password" ? "text" : "password";
}

document.getElementById("signinBtn").addEventListener("click", async () => {
  const email = document.getElementById("signinEmail")?.value.trim();
  const password = document.getElementById("pwd")?.value;
  const selectedRole = document.querySelector("input[name='signinRole']:checked")?.value || "customer";

  if (!email || !password) {
    alert("Please enter email and password.");
    return;
  }

  try {
    const res = await fetch("http://localhost:5000/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, role: selectedRole })
    });
    const body = await res.json();
    if (!res.ok) {
      alert(body.error || "Login failed.");
      return;
    }
    const role = body.user?.role || selectedRole;
    localStorage.setItem("snapit_role", role);
    localStorage.setItem("snapit_user", JSON.stringify(body.user));
    if (role && role.includes("seller")) {
      window.location.href = "seller-dashboard.html";
    } else {
      window.location.href = "product.html";
    }
  } catch (err) {
    console.error(err);
    alert("Could not sign in. Is the backend running?");
  }
});
