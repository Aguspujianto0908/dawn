import requests
import json
import logging
import time
import asyncio
import telegram
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import colorlog
from fake_useragent import UserAgent
import urllib3
CONFIG_FILE = "config.json"
PROXY_FILE = "proxies.txt"
# Setup logging with color
log_colors = {
    'DEBUG': 'cyan',
    'INFO': 'green',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'SUCCESS': 'blue'
}
formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
    log_colors=log_colors
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)
# Adding a custom SUCCESS level between INFO and WARNING
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")
def log_success(message, *args, **kwargs):
    if logger.isEnabledFor(SUCCESS_LEVEL):
        logger._log(SUCCESS_LEVEL, message, args, **kwargs)
logging.success = log_success
def read_config(filename=CONFIG_FILE):
    try:
        with open(filename, 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError:
        logging.error(f"Configuration file '{filename}' not found.")
        return {}
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in '{filename}'.")
        return {}
def read_proxies(filename=PROXY_FILE):
    proxies = []
    try:
        with open(filename, 'r') as file:
            for line in file:
                proxy = line.strip()
                if proxy:
                    proxies.append(proxy)
    except FileNotFoundError:
        logging.error(f"Proxy file '{filename}' not found.")
    return proxies
def parse_proxy(proxy):
    """Parse proxy string into format for requests."""
    proxy_url = urlparse(proxy)
    if proxy_url.scheme in ['http', 'https', 'socks5']:
        if proxy_url.username and proxy_url.password:
            return {
                'http': f"{proxy_url.scheme}://{proxy_url.username}:{proxy_url.password}@{proxy_url.hostname}:{proxy_url.port}",
                'https': f"{proxy_url.scheme}://{proxy_url.username}:{proxy_url.password}@{proxy_url.hostname}:{proxy_url.port}",
            }
        else:
            return {
                'http': f"{proxy_url.scheme}://{proxy_url.hostname}:{proxy_url.port}",
                'https': f"{proxy_url.scheme}://{proxy_url.hostname}:{proxy_url.port}",
            }
    return {}
def create_session(proxy=None):
    session = requests.Session()
    if proxy:
        proxies = parse_proxy(proxy)
        logging.info(f"Using proxy: {proxy}")
        session.proxies.update(proxies)
    return session
config = read_config(CONFIG_FILE)
bot_token = config.get("telegram_bot_token")
chat_id = config.get("telegram_chat_id")
use_proxy = config.get("use_proxy", False)
use_telegram = config.get("use_telegram", False)
poll_interval = config.get("poll_interval", 120)  # Default to 120 seconds if not specified
if use_telegram and (not bot_token or not chat_id):
    logging.error("Missing 'bot_token' or 'chat_id' in 'config.json'.")
    exit(1)
bot = telegram.Bot(token=bot_token) if use_telegram else None
keepalive_url = "https://www.aeropres.in/chromeapi/dawn/v1/userreward/keepalive"
get_points_url = "https://www.aeropres.in/api/atom/v1/userreferral/getpoint"
extension_id = "fpdkjdnhkakefebpekbdhillbhonfjjp"
_v = "1.0.7"
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ua = UserAgent()
def read_account(filename="config.json"):
    try:
        with open(filename, 'r') as file:
            data = json.load(file)
            accounts = data.get("accounts", [])
            return accounts
    except FileNotFoundError:
        logging.error(f"Config file '{filename}' not found.")
        return []
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in '{filename}'.")
        return []
def total_points(headers, session):
    try:
        response = session.get(get_points_url, headers=headers, verify=False)
        response.raise_for_status()
        json_response = response.json()
        if json_response.get("status"):
            reward_point_data = json_response["data"]["rewardPoint"]
            referral_point_data = json_response["data"]["referralPoint"]
            total_points = (
                reward_point_data.get("points", 0) +
                reward_point_data.get("registerpoints", 0) +
                reward_point_data.get("signinpoints", 0) +
                reward_point_data.get("twitter_x_id_points", 0) +
                reward_point_data.get("discordid_points", 0) +
                reward_point_data.get("telegramid_points", 0) +
                reward_point_data.get("bonus_points", 0) +
                referral_point_data.get("commission", 0)
            )
            return total_points
        else:
            logging.warning(f"Warning: {json_response.get('message', 'Unknown error when fetching points')}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching points: {e}")
    return 0
def keep_alive(headers, email, session):
    keepalive_payload = {
        "username": email,
        "extensionid": extension_id,
        "numberoftabs": 0,
        "_v": _v
    }
    headers["User-Agent"] = ua.random
    try:
        response = session.post(keepalive_url, headers=headers, json=keepalive_payload, verify=False)
        response.raise_for_status()
        json_response = response.json()
        if 'message' in json_response:
            return True, json_response['message']
        else:
            return False, "Message not found in response"
    except requests.exceptions.RequestException as e:
        return False, str(e)
async def telegram_message(message):
    if use_telegram:
        try:
            # Using Markdown instead of HTML to simplify formatting
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Error sending Telegram message: {e}")
def process_account(account, proxy=None):
    email = account["email"]
    token = account["token"]
    session = create_session(proxy=proxy)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": ua.random
    }
    logging.info(f"Processing account: {email}")
    points = total_points(headers, session)
    success, status_message = keep_alive(headers, email, session)
    if success:
        logging.success(f"Account {email} keep-alive success, points earned: {points:,.0f}")
        if use_telegram:
            asyncio.run(telegram_message(
                f"🌟 *Success Notification* 🌟\n\n"
                f"👤 *Account:* {email}\n"
                f"✅  *Status:* Keep Alive Successful\n"
                f"💰 *Points Earned:* {points:,.0f}"
            ))
    else:
        logging.error(f"Account {email} keep-alive failed: {status_message}")
        if use_telegram:
            asyncio.run(telegram_message(
                f"⚠️ *Error Notification* ⚠️\n\n"
                f"👤 *Account:* {email}\n"
                f"❌  *Status:* Keep Alive Failed\n"
                f"⚠️ *Error Message:* {status_message}"
            ))
def main():
    accounts = read_account()
    proxies = read_proxies()
    while True:
        with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
            for account in accounts:
                proxy = proxies[0] if use_proxy and proxies else None
                executor.submit(process_account, account, proxy)
        logging.info(f"Sleeping for {poll_interval} seconds...")
        time.sleep(poll_interval)
if __name__ == "__main__":
    main()