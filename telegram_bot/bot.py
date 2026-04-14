import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

AUTHORIZED_IDS: set[int] = set()
BOT_TOKEN: str = ""
PROJECT_DIR: str = ""
DEPLOY_TIMEOUT = 300
MAX_LOG_LINES = 30


def load_config():
    global AUTHORIZED_IDS, BOT_TOKEN, PROJECT_DIR
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    PROJECT_DIR = os.environ.get("PROJECT_DIR", "/app")
    user_ids = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    AUTHORIZED_IDS = {
        int(uid.strip())
        for uid in user_ids.split(",")
        if uid.strip().isdigit()
    }


def is_authorized(user_id: int) -> bool:
    return user_id in AUTHORIZED_IDS


def run_script(script_path: str, args: list[str] | None = None, timeout: int = DEPLOY_TIMEOUT) -> tuple[bool, str]:
    cmd = ["bash", script_path] + (args or [])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_DIR,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return result.returncode == 0, output[-4000:]
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except Exception as e:
        return False, f"Error: {e}"


def parse_target(args: list[str] | None) -> tuple[str, list[str]]:
    if not args:
        return "production", []
    if args[0] in ("staging", "stg"):
        return "staging", args[1:]
    return "production", args


def get_service(target: str) -> str:
    return "web" if target == "production" else "staging-web"


def authorized_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return
        if not is_authorized(update.effective_user.id):
            await update.message.reply_text("Unauthorized.")
            logger.warning(
                "Unauthorized access from user %s (%s)",
                update.effective_user.id,
                update.effective_user.username,
            )
            return
        return await func(update, context)
    return wrapper


@authorized_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "*Board Game Club - Server Commands*\n\n"
        "/deploy \\[staging] \\- Deploy latest code\n"
        "/rollback \\[staging] \\[SHA|list] \\- Rollback to previous deploy\n"
        "/restart \\[staging] \\- Restart container\n"
        "/reset staging \\- Reset staging database\n"
        "/status \\- Show container status\n"
        "/logs \\[staging] \\- Show recent logs\n"
        "/help \\- Show this message"
    )
    await update.message.reply_text(msg, parse_mode="MarkdownV2")


@authorized_only
async def cmd_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target, _ = parse_target(context.args)
    await update.message.reply_text(f"Starting {target} deploy...")
    script = f"{PROJECT_DIR}/scripts/deploy.sh"
    success, output = run_script(script, [target])
    status = "successful" if success else "FAILED"
    await update.message.reply_text(f"Deploy {status}!\n```\n{output}\n```")


@authorized_only
async def cmd_rollback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target, remaining = parse_target(context.args)

    if not remaining or remaining[0] == "list":
        history_file = f"{PROJECT_DIR}/scripts/.deploy_history_{target}"
        try:
            with open(history_file) as f:
                lines = f.readlines()
        except FileNotFoundError:
            await update.message.reply_text("No deploy history found.")
            return

        lines = [l.strip() for l in lines if l.strip()][-5:]
        if not lines:
            await update.message.reply_text("No deploy history found.")
            return

        msg = f"Recent {target} deploys:\n"
        for line in lines:
            parts = line.split("|")
            if len(parts) == 2:
                sha_short = parts[1][:8]
                msg += f"  `{sha_short}` \\- {parts[0]}\n"
        msg += f"\nUse `/rollback {target if target == 'staging' else ''} <sha>` to rollback\\."
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
        return

    sha = remaining[0]
    service = get_service(target)
    await update.message.reply_text(f"Rolling back {target} to {sha[:8]}...")

    script = f"{PROJECT_DIR}/scripts/rollback.sh"
    success, output = run_script(script, [target, sha])
    status = "successful" if success else "FAILED"
    await update.message.reply_text(f"Rollback {status}!\n```\n{output}\n```")


@authorized_only
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target, _ = parse_target(context.args)
    service = get_service(target)
    await update.message.reply_text(f"Restarting {target} ({service})...")

    success, output = run_script(
        "/bin/bash", ["-c", f"cd {PROJECT_DIR} && docker compose restart {service}"],
        timeout=60,
    )
    status = "successful" if success else "FAILED"
    await update.message.reply_text(f"Restart {status}!\n```\n{output}\n```")


@authorized_only
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target, remaining = parse_target(context.args)
    if target != "staging":
        await update.message.reply_text("Reset is only available for staging.")
        return

    await update.message.reply_text("Resetting staging database...")
    script = f"{PROJECT_DIR}/scripts/reset_staging.sh"
    seed = "--seed" in remaining
    args = ["--seed"] if seed else []
    success, output = run_script(script, args, timeout=120)
    status = "successful" if success else "FAILED"
    await update.message.reply_text(f"Reset {status}!\n```\n{output}\n```")


@authorized_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success, output = run_script(
        "/bin/bash",
        ["-c", f"cd {PROJECT_DIR} && docker compose ps --format 'table {{{{.Name}}}}\t{{{{.Status}}}}\t{{{{.State}}}}'"],
        timeout=30,
    )
    if success:
        await update.message.reply_text(f"```\n{output}\n```")
    else:
        await update.message.reply_text(f"Failed to get status:\n```\n{output}\n```")


@authorized_only
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target, _ = parse_target(context.args)
    service = get_service(target)
    success, output = run_script(
        "/bin/bash",
        ["-c", f"cd {PROJECT_DIR} && docker compose logs --tail {MAX_LOG_LINES} {service}"],
        timeout=30,
    )
    if success:
        truncated = output[-4000:]
        await update.message.reply_text(f"```\n{truncated}\n```")
    else:
        await update.message.reply_text(f"Failed to get logs:\n```\n{output}\n```")


def main():
    load_config()
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return
    if not AUTHORIZED_IDS:
        print("WARNING: TELEGRAM_ALLOWED_USER_IDS not set - no one can use the bot")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("deploy", cmd_deploy))
    app.add_handler(CommandHandler("rollback", cmd_rollback))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("logs", cmd_logs))

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
