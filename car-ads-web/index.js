const fastify = require("fastify")({ logger: false });
const path = require("path");

fastify.register(require("@fastify/cors"), { origin: "*" });
fastify.register(require("@fastify/static"), {
  root: path.join(__dirname, "public"),
  prefix: "/",
});

// آدرس سرویس داخلی car-ads-ai (همون api.py / uvicorn)
const ANALYTICS_SERVICE_URL = "http://127.0.0.1:8001";

fastify.get("/api/car-ads-analytics", async (req, reply) => {
  const hours = req.query.hours || 24;
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/analytics?hours=${hours}`
    );
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return {
      error:
        "سرویس car-ads-ai در دسترس نیست — مطمئن شو api.py با uvicorn اجرا شده",
      detail: err.message,
    };
  }
});

fastify.get("/api/car-ads-ads", async (req, reply) => {
  const hours = req.query.hours || 24;
  const carName = req.query.car_name;
  const trim = req.query.trim; // undefined یعنی گروه «بدون تیپ مشخص»
  if (!carName) {
    reply.code(400);
    return { error: "پارامتر car_name الزامی است" };
  }
  try {
    let url = `${ANALYTICS_SERVICE_URL}/ads?car_name=${encodeURIComponent(
      carName
    )}&hours=${hours}`;
    if (trim !== undefined) {
      url += `&trim=${encodeURIComponent(trim)}`;
    }
    const res = await fetch(url);
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.get("/api/car-ads-daily-report", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/daily-report`);
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.get("/api/car-ads-wanted-ads", async (req, reply) => {
  const hours = req.query.hours || 168;
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/wanted-ads?hours=${hours}`
    );
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.get("/api/car-ads-no-price-ads", async (req, reply) => {
  const hours = req.query.hours || 168;
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/no-price-ads?hours=${hours}`
    );
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.get("/api/car-ads-channel-preview", async (req, reply) => {
  const username = req.query.username;
  if (!username) {
    reply.code(400);
    return { found: false, error: "پارامتر username الزامی است" };
  }
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/channel-preview?username=${encodeURIComponent(
        username
      )}`
    );
    if (!res.ok) {
      reply.code(502);
      return { found: false, error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return {
      found: false,
      error: "سرویس car-ads-ai در دسترس نیست",
      detail: err.message,
    };
  }
});

fastify.get("/api/car-ads-channels", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/channels`);
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.post("/api/car-ads-channels", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/channels`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.delete("/api/car-ads-channels/:username", async (req, reply) => {
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/channels/${encodeURIComponent(
        req.params.username
      )}`,
      {
        method: "DELETE",
      }
    );
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.get("/api/car-ads-settings", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/settings`);
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.post("/api/car-ads-settings", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.get("/api/car-ads-price-alerts", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/price-alerts`);
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.post("/api/car-ads-price-alerts", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/price-alerts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    const json = await res.json();
    if (!res.ok) {
      reply.code(res.status);
      return { error: json.detail || "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return json;
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.delete("/api/car-ads-price-alerts/:id", async (req, reply) => {
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/price-alerts/${encodeURIComponent(
        req.params.id
      )}`,
      {
        method: "DELETE",
      }
    );
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.get("/api/car-ads-alert-matches", async (req, reply) => {
  const unseenOnly = req.query.unseen_only || "false";
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/alert-matches?unseen_only=${unseenOnly}`
    );
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.post("/api/car-ads-alert-matches/mark-seen", async (req, reply) => {
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/alert-matches/mark-seen`,
      {
        method: "POST",
      }
    );
    if (!res.ok) {
      reply.code(502);
      return { error: "سرویس car-ads-ai پاسخ درستی نداد" };
    }
    return await res.json();
  } catch (err) {
    reply.code(502);
    return { error: "سرویس car-ads-ai در دسترس نیست", detail: err.message };
  }
});

fastify.listen({ port: 3050, host: "0.0.0.0" }, (err) => {
  if (err) throw err;
  console.log("car-ads-web backend running on http://localhost:3050");
});
