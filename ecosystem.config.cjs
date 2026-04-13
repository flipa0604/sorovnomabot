/**
 * PM2 bilan ishga tushirish (bot + web-admin).
 *
 * Server (Linux):
 *   cd /path/to/sorovnomabot
 *   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
 *   npm i -g pm2
 *   pm2 start ecosystem.config.cjs
 *   pm2 save
 *   pm2 startup   # tizim qayta yuklanganda avtomatik (ko'rsatma chiqadi)
 *
 * To'xtatish / qayta yuklash:
 *   pm2 stop sorovnomabot-bot sorovnomabot-web
 *   pm2 restart sorovnomabot-bot sorovnomabot-web
 */
const path = require("path");

const root = __dirname;
const isWin = process.platform === "win32";
const python = isWin
  ? path.join(root, ".venv", "Scripts", "python.exe")
  : path.join(root, ".venv", "bin", "python");

module.exports = {
  apps: [
    {
      name: "sorovnomabot-bot",
      cwd: root,
      script: "bot.py",
      interpreter: python,
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_restarts: 30,
      min_uptime: "8s",
      exp_backoff_restart_delay: 200,
      time: true,
      error_file: path.join(root, "logs", "bot-error.log"),
      out_file: path.join(root, "logs", "bot-out.log"),
      merge_logs: true,
    },
    {
      name: "sorovnomabot-web",
      cwd: root,
      script: "run_admin_web.py",
      interpreter: python,
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_restarts: 30,
      min_uptime: "8s",
      exp_backoff_restart_delay: 200,
      time: true,
      error_file: path.join(root, "logs", "web-error.log"),
      out_file: path.join(root, "logs", "web-out.log"),
      merge_logs: true,
    },
  ],
};
