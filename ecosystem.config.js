module.exports = {
  apps: [
    {
      name: "car-ads-watchdog",
      script: "watchdog.py",
      interpreter: "C:\\projects\\car-ads-ai\\car-ads-ai\\venv\\Scripts\\python.exe",
      cwd: "C:\\projects\\car-ads-ai\\car-ads-ai",
      env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "car-ads-api",
      script: "C:\\projects\\car-ads-ai\\car-ads-ai\\venv\\Scripts\\uvicorn.exe",
      args: "api:app --host 127.0.0.1 --port 8001",
      cwd: "C:\\projects\\car-ads-ai\\car-ads-ai",
      env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "car-ads-web",
      script: "index.js",
      cwd: "C:\\projects\\car-ads-ai\\car-ads-web",
    },
  ],
};
