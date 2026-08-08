import os
import time
import json
import random
import requests
import re

from playwright.sync_api import sync_playwright


# ================= ENV =================
PROXY_URL = os.getenv("PROXY", "")
COOKIE2 = os.getenv("COOKIE2") # 对应paymenter_remember=的cookies
COOKIE3 = os.getenv("COOKIE3") # 对应paymenter_session=的cookies
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

MAIN_URL = "https://client.freemchosting.com/login"
DASHBOARD_URL = "https://client.freemchosting.com/dashboard"
TARGET_URL = "https://client.freemchosting.com/rewards"
Credit_URL = "https://client.freemchosting.com/account/credits"

class FreemchostingClaimPW:

    def __init__(self):
        self.debug_dir = "debug"
        os.makedirs(self.debug_dir, exist_ok=True)

    def log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def human_wait(self, a=6, b=10):
        time.sleep(random.uniform(a, b))

    # ================= TG =================
    def send_telegram_photo(self, image_path, caption=""):
        try:
            if not TG_TOKEN or not TG_CHAT_ID:
                self.log("⚠️ TG 未配置")
                return

            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"

            with open(image_path, "rb") as f:
                requests.post(
                    url,
                    data={
                        "chat_id": TG_CHAT_ID,
                        "caption": caption[:1000]
                    },
                    files={"photo": f}
                )

            self.log("📨 TG 已发送")

        except Exception as e:
            self.log(f"❌ TG失败: {e}")

    # ================= DEBUG =================
    def dump_debug(self, page, name, msg=""):
        try:
            img = f"{self.debug_dir}/{name}.png"
            html = f"{self.debug_dir}/{name}.html"

            page.screenshot(path=img, full_page=True)

            with open(html, "w", encoding="utf-8") as f:
                f.write(page.content())

            self.log(f"📸 saved: {name}")

            self.send_telegram_photo(
                img,
                f"{name}\n{msg}\n{page.url}"
            )

        except Exception as e:
            self.log(f"❌ debug error: {e}")

    def get_credit(self,page):
        try:
            page.wait_for_selector("p.text-primary-100",timeout=30000)
            total = 0
            texts = page.locator("p.text-primary-100").all_inner_texts()
            for text in texts:
                num = re.search(r"Credit\s+([\d,]+)",text)
                if num:
                    value = num.group(1)
                    total += float(value.replace(",", "."))
            return round(total,2)
        except Exception as e:
            return None
        
    # ================= RUN =================
    def run(self):

        self.log("🚀 Freemchosting 自动领Credit启动")

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=False,
                proxy={"server": PROXY_URL} if PROXY_URL else None,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            )

            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"
            )

            context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            """)
            
            page = context.new_page()

            # ================= IP =================
            self.log("🌍 检查出口IP")
            page.goto("https://api.ipify.org?format=json")
            ip = json.loads(page.text_content("body"))["ip"]
            self.log(f"IP: {ip}")

            # ================= LOGIN =================
            self.log("🔗 进入主站")
            page.goto(MAIN_URL, wait_until="domcontentloaded")
            self.human_wait()

            context.add_cookies([
                {
                    "name": "paymenter_remember",
                    "value": COOKIE2,
                    "domain": "client.freemchosting.com",
                    "path": "/"
                },
                {
                    "name": "paymenter_session",
                    "value": COOKIE3,
                    "domain": "client.freemchosting.com",
                    "path": "/"
                }
            ])

            # ================= DASHBOARD =================
            self.log("📂 进入账户面板")
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            self.human_wait()
            #self.dump_debug(page, "dashboard", "dashboard loaded")

            # ================= Credit =================
            self.log("📂 进入账户Credit面板")
            page.goto(Credit_URL, wait_until="domcontentloaded")
            self.human_wait()
            credit_before = self.get_credit(page)
            if credit_before is None:
                self.log("❌进入账户Credit面板无法找到Credit,请检查Cookies")
                self.dump_debug(page, "❌进入账户Credit面板无法找到Credit,请检查Cookies", "Credit loaded")
                return
            #self.dump_debug(page, "Credit", "Credit loaded")
            
            # ================= REWARD =================
            self.log("📂 进入账户奖励面板")
            page.goto(TARGET_URL, wait_until="domcontentloaded")
            self.human_wait()
            #self.dump_debug(page, "reward", "reward loaded")

            # ================= GENERATE =================
            self.log("🔗 生成广告链接")
            page.wait_for_selector("button:has-text('Generate Offer')", timeout=30000)
            page.click("button:has-text('Generate Offer')")
            self.human_wait()
            #self.dump_debug(page, "Click Generate", "Click Generate")

            # ================= START =================
            self.log("🔗 开始点击广告")
            page.wait_for_selector("a:has-text('Start')", timeout=60000)
            page.click("a:has-text('Start')")
            self.human_wait()
            #self.dump_debug(page, "Click Start", "Click Start")

            # ================= TASK =================
            self.log("🎯 点击广告内任务")
            page.wait_for_selector("#taskList", timeout=60000)
            page.wait_for_selector("#taskList .task", timeout=60000)
            #self.dump_debug(page, "task_loaded", "task ready")
            page.click("#taskList .task")
            time.sleep(5)
            self.log("⏳ Waiting Claim Reward available...")
            page.wait_for_function("""
            () => {
                const btn = document.querySelector("#unlockBtn");
                return btn && !btn.disabled;
            }
            """, timeout=300000)   # 最长等5分钟
            self.log("🎉 Claim Reward")
            page.locator("#unlockBtn").click()
            time.sleep(5)

            # ================= Credit =================
            self.log("📂 再次进入账户Credit面板")
            page.goto(Credit_URL, wait_until="domcontentloaded")
            self.human_wait()
            credit_after = self.get_credit(page)
            #self.dump_debug(page, "Credit", "Credit loaded")
            
            self.dump_debug(page, "🚀Freemchosting 自动领Credit", f"🕒执行脚本前Credit余额: {credit_before}\n🎉执行脚本后Credit余额: {credit_after}")

            self.log("✅ 流程完毕")

            browser.close()


if __name__ == "__main__":
    FreemchostingClaimPW().run()
