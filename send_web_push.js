const webpush = require("web-push");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});

process.stdin.on("end", async () => {
  try {
    const request = JSON.parse(input || "{}");
    const { subscription, payload, vapid } = request;
    if (!subscription || !subscription.endpoint) {
      throw new Error("missing subscription endpoint");
    }
    if (!vapid || !vapid.publicKey || !vapid.privateKey) {
      throw new Error("missing VAPID keys");
    }
    webpush.setVapidDetails(
      process.env.FRUIT_AUTO_VAPID_SUBJECT || "mailto:fruit-auto@example.com",
      vapid.publicKey,
      vapid.privateKey
    );
    const options = {
      TTL: Math.max(0, Number(payload?.ttlSeconds ?? 300) || 0),
      urgency: payload?.urgency || "high",
    };
    await webpush.sendNotification(subscription, JSON.stringify(payload || {}), options);
    process.stdout.write(JSON.stringify({ ok: true }));
  } catch (error) {
    process.stdout.write(
      JSON.stringify({
        ok: false,
        statusCode: error.statusCode || null,
        body: error.body || null,
        message: error.message,
      })
    );
    process.exit(1);
  }
});
