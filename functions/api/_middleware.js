/**
 * API Middleware: 驗證 Google ID Token + email 白名單。
 * 只有通過驗證的請求才能存取完整版資料。
 */

import * as jose from "jose";

const GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs";
const GOOGLE_ISSUER = "https://accounts.google.com";

let jwks = null;

function getJWKS() {
  if (!jwks) {
    jwks = jose.createRemoteJWKSet(new URL(GOOGLE_JWKS_URL));
  }
  return jwks;
}

export async function onRequest(context) {
  const { request, env } = context;

  // 從 Authorization header 取得 token
  const authHeader = request.headers.get("Authorization");
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    // 無 token：放行，讓 handler 回傳公開版資料
    return await context.next();
  }

  const token = authHeader.slice(7);
  const clientId = env.GOOGLE_CLIENT_ID;
  const allowedEmails = (env.ALLOWED_EMAILS || "").split(",").map((e) => e.trim().toLowerCase());

  if (!clientId) {
    return new Response(JSON.stringify({ error: "伺服器未設定 Google Client ID" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
    // 驗證 JWT 簽章、issuer、audience、expiration
    const { payload } = await jose.jwtVerify(token, getJWKS(), {
      issuer: GOOGLE_ISSUER,
      audience: clientId,
    });

    const email = (payload.email || "").toLowerCase();

    // 檢查 email 白名單
    if (!allowedEmails.includes(email)) {
      return new Response(JSON.stringify({ error: "此帳號無存取權限" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    }

    // 通過驗證，繼續處理請求
    context.data.userEmail = email;
    context.data.userName = payload.name || email;
    return await context.next();
  } catch (err) {
    return new Response(JSON.stringify({ error: "Token 驗證失敗" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
}
