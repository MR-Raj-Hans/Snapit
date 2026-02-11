function togglePwd() {
    const p = document.getElementById("pwd");
    p.type = p.type === "password" ? "text" : "password";
}

async function signup() {
    const name = document.getElementById("signupName")?.value.trim();
    const email = document.getElementById("signupEmail")?.value.trim();
    const password = document.getElementById("pwd")?.value;

    if (!name || !email || !password) {
        alert("Please fill in name, email, and password.");
        return;
    }

    try {
        const res = await fetch("http://localhost:5000/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, email, password })
        });
        const body = await res.json();
        if (!res.ok) {
            alert(body.error || "Sign up failed.");
            return;
        }
        localStorage.setItem("snapit_user", JSON.stringify(body.user));
        window.location.href = "sign in.html";
    } catch (err) {
        console.error(err);
        alert("Could not sign up. Is the backend running?");
    }
}
