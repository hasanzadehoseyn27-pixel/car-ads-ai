const fastify = require("fastify")({ logger: false });
const path = require("path");

fastify.register(require("@fastify/cors"), { origin: "*" });
fastify.register(require("@fastify/static"), {
  root: path.join(__dirname, "public"),
  prefix: "/",
});

const ANALYTICS_SERVICE_URL = "http://127.0.0.1:8001";

fastify.get("/api/car-ads-analytics", async (req, reply) => {
  const hours = req.query.hours || 24;
  const onlyNew =
    req.query.only_new !== undefined ? req.query.only_new : "true";
  const search = req.query.search;
  try {
    let url = `${ANALYTICS_SERVICE_URL}/analytics?hours=${hours}&only_new=${onlyNew}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await fetch(url);
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
  const trim = req.query.trim;
  const onlyNew =
    req.query.only_new !== undefined ? req.query.only_new : "true";
  if (!carName) {
    reply.code(400);
    return { error: "پارامتر car_name الزامی است" };
  }
  try {
    let url = `${ANALYTICS_SERVICE_URL}/ads?car_name=${encodeURIComponent(
      carName
    )}&hours=${hours}&only_new=${onlyNew}`;
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

fastify.get("/api/car-ads-used-cars", async (req, reply) => {
  const hours = req.query.hours || 24;
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/used-cars?hours=${hours}`
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

fastify.get("/api/car-ads-archive", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/archive`);
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

fastify.get("/api/car-ads-account-status", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/account-status`);
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

fastify.post(
  "/api/car-ads-channels/extract-from-group-with-progress",
  async (req, reply) => {
    try {
      const res = await fetch(
        `${ANALYTICS_SERVICE_URL}/channels/extract-from-group-with-progress`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(req.body),
        }
      );
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
  }
);

fastify.post(
  "/api/car-ads-channels/start-extraction-run",
  async (req, reply) => {
    try {
      const res = await fetch(
        `${ANALYTICS_SERVICE_URL}/channels/start-extraction-run`,
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
  }
);

fastify.post("/api/car-ads-channels/rescan-group", async (req, reply) => {
  try {
    const res = await fetch(`${ANALYTICS_SERVICE_URL}/channels/rescan-group`, {
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

fastify.delete(
  "/api/car-ads-monitored-groups/:groupUsername",
  async (req, reply) => {
    try {
      const res = await fetch(
        `${ANALYTICS_SERVICE_URL}/channels/monitored-groups/${encodeURIComponent(
          req.params.groupUsername
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
  }
);

fastify.get("/api/car-ads-monitored-groups", async (req, reply) => {
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/channels/monitored-groups`
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

fastify.get("/api/car-ads-extraction-log", async (req, reply) => {
  const groupUsername = req.query.group_username;
  try {
    let url = `${ANALYTICS_SERVICE_URL}/channels/extraction-log`;
    if (groupUsername) {
      url += `?group_username=${encodeURIComponent(groupUsername)}`;
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

fastify.get("/api/car-ads-extraction-progress", async (req, reply) => {
  const runId = req.query.run_id;
  if (!runId) {
    reply.code(400);
    return { error: "پارامتر run_id الزامی است" };
  }
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/channels/extraction-progress?run_id=${encodeURIComponent(
        runId
      )}`
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

fastify.post("/api/car-ads-extraction-progress/clear", async (req, reply) => {
  const runId = req.query.run_id;
  try {
    const res = await fetch(
      `${ANALYTICS_SERVICE_URL}/channels/extraction-progress/clear?run_id=${encodeURIComponent(
        runId
      )}`,
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
