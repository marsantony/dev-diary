/**
 * GET /api/summaries
 *
 * Query params:
 *   type=daily&date=YYYY-MM-DD  → 完整版每日摘要
 *   type=weekly&date=YYYY-MM-DD → 完整版週報
 *   type=list                   → 列出所有可用日期
 */

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const type = url.searchParams.get("type");
  const date = url.searchParams.get("date");

  const headers = { "Content-Type": "application/json" };

  if (type === "list") {
    const meta = await env.DEV_DIARY_KV.get("meta:latest", "json");
    return new Response(JSON.stringify(meta || {}), { headers });
  }

  if (!type || !date) {
    return new Response(JSON.stringify({ error: "缺少 type 或 date 參數" }), {
      status: 400,
      headers,
    });
  }

  if (!["daily", "weekly"].includes(type)) {
    return new Response(JSON.stringify({ error: "type 必須是 daily 或 weekly" }), {
      status: 400,
      headers,
    });
  }

  // 驗證日期格式
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return new Response(JSON.stringify({ error: "date 格式錯誤，需要 YYYY-MM-DD" }), {
      status: 400,
      headers,
    });
  }

  const isAuthenticated = !!context.data.userEmail;
  const key = `${isAuthenticated ? "private" : "public"}:${type}:${date}`;
  const data = await env.DEV_DIARY_KV.get(key, "json");

  if (!data) {
    return new Response(JSON.stringify({ error: "找不到資料" }), {
      status: 404,
      headers,
    });
  }

  return new Response(JSON.stringify(data), { headers });
}
