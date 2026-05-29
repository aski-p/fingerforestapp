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
      "mailto:fruit-auto@localhost",
      vapid.publicKey,
      vapid.privateKey
    );
    await webpush.sendNotification(subscription, JSON.stringify(payload || {}));
    process.stdout.write(JSON.stringify({ ok: true }));
  } catch (error) {
    process.stdout.write(
      JSON.stringify({
        ok: false,
        statusCode: error.statusCode || null,
        message: error.message,
      })
    );
    process.exit(1);
  }
});
