function togglePwd() {
    const p = document.getElementById("pwd");
    p.type = p.type === "password" ? "text" : "password";
}

async function signupSeller() {
    const name = document.getElementById("signupName")?.value.trim();
    const email = document.getElementById("signupEmail")?.value.trim();
    const password = document.getElementById("pwd")?.value;
    const terms = document.getElementById("termsChk")?.checked;

    const owner = document.getElementById("sellerOwner")?.value.trim();
    const shop = document.getElementById("sellerShop")?.value.trim();
    const type = document.getElementById("sellerType")?.value;
    const sellerEmail = document.getElementById("sellerEmail")?.value.trim();
    const whatsapp = document.getElementById("sellerWhatsapp")?.value.trim();
    const phone = document.getElementById("sellerPhone")?.value.trim();
    const address = document.getElementById("sellerAddress")?.value.trim();
    const gst = document.getElementById("sellerGst")?.value.trim();
    const otp = document.getElementById("sellerOtp")?.value.trim();

    if (!name || !email || !password) {
        alert("Please fill name, email, and password.");
        return;
    }
    if (!terms) {
        alert("Please accept the terms to continue.");
        return;
    }
    if (!owner || !shop || !type || !address) {
        alert("Please fill owner, shop name, type, and address.");
        return;
    }

    const sellerDetails = {
        owner,
        shop,
        type,
        sellerEmail,
        whatsapp,
        phone,
        address,
        gst,
        otp
    };

    try {
        const res = await fetch("http://localhost:5000/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, email, password, role: "seller_offline", sellerDetails })
        });
        const body = await res.json();
        if (!res.ok) {
            alert(body.error || "Sign up failed.");
            return;
        }
        localStorage.setItem("snapit_role", "seller_offline");
        localStorage.setItem("snapit_user", JSON.stringify(body.user));
        window.location.href = "sign in.html";
    } catch (err) {
        console.error(err);
        alert("Could not sign up. Is the backend running?");
    }
}

async function sendOtp() {
    const whatsapp = document.getElementById("sellerWhatsapp")?.value.trim();
    if (!whatsapp) {
        alert("Enter WhatsApp number first.");
        return;
    }

    const btn = document.querySelector(".otp-btn");
    const prevText = btn.innerText;
    btn.disabled = true;
    btn.innerText = "Sending...";

    try {
        const res = await fetch("http://localhost:5000/auth/send-otp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone: whatsapp, channel: "whatsapp" })
        });
        const body = await res.json();
        if (!res.ok) {
            alert(body.error || "Could not send OTP.");
        } else {
            alert(body.message || "OTP sent to WhatsApp.");
        }
    } catch (err) {
        console.error(err);
        alert("Failed to send OTP. Is the backend running?");
    } finally {
        btn.disabled = false;
        btn.innerText = prevText;
    }
}
