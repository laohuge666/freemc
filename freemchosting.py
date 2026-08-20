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
            page.goto("https://api.ipify.org?format=json", timeout=60000)
            ip = json.loads(page.text_content("body"))["ip"]
            self.log(f"IP: {ip}")

            # ================= LOGIN =================
            self.log("🔗 进入主站")
            page.goto(MAIN_URL, wait_until="domcontentloaded", timeout=90000)
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
            for _try in range(3):
                try:
                    page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=90000)
                    break
                except Exception as e:
                    self.log(f"⚠️ 面板加载失败(第{_try+1}次): {str(e)[:80]}")
                    time.sleep(8)
            self.human_wait()
            #self.dump_debug(page, "dashboard", "dashboard loaded")

            # ================= Credit =================
            self.log("📂 进入账户Credit面板")
            page.goto(Credit_URL, wait_until="domcontentloaded", timeout=90000)
            self.human_wait()
            credit_before = self.get_credit(page)
            if credit_before is None:
                self.log("❌进入账户Credit面板无法找到Credit,请检查Cookies")
                self.dump_debug(page, "❌进入账户Credit面板无法找到Credit,请检查Cookies", "Credit loaded")
                return
            #self.dump_debug(page, "Credit", "Credit loaded")
            
            # ================= REWARD =================
            self.log("📂 进入账户奖励面板")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90000)
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
            self.log("🎯 点击广告内任务(文章)")
            page.wait_for_selector("#taskList", timeout=60000)
            page.wait_for_selector("#taskList .task", timeout=60000)
            # 点击任务 0(重试机制:点击后检查是否开始,没开始则再点)
            for _ in range(3):
                try:
                    page.click("#taskList .task[data-i='0']", timeout=10000)
                except Exception:
                    page.evaluate("document.querySelector('#taskList .task[data-i=\"0\"]')?.click()")
                time.sleep(6)
                try:
                    cls = page.evaluate("() => document.querySelector('#taskList .task[data-i=\"0\"]')?.className || ''")
                    self.log(f"点击后任务0状态: {cls[:70]}")
                    if "done" in cls or "spin" in cls or "active" in cls or "start" in cls:
                        break
                except Exception:
                    pass
                # 检查是否打开了新窗口(文章链接)
                try:
                    if len(page.context.pages) > 1:
                        np_ = page.context.pages[-1]
                        self.log(f"新窗口: {np_.url[:80]}")
                        np_.wait_for_load_state(timeout=15000)
                        time.sleep(45)
                        np_.close()
                        page.bring_to_front()
                        break
                except Exception:
                    pass
            self.log("⏳ 等待文章任务完成(约50秒)...")
            for i in range(30):
                time.sleep(10)
                try:
                    cls = page.evaluate("() => document.querySelector('#taskList .task[data-i=\"0\"]')?.className || ''")
                    if "done" in cls:
                        self.log("✅ 文章任务完成")
                        break
                except Exception:
                    pass
                if i in (2, 5, 9, 14):
                    try:
                        t0 = page.evaluate("() => document.querySelector('#taskList .task[data-i=\"0\"]')?.className || 'N/A'")
                        t1 = page.evaluate("() => document.querySelector('#taskList .task[data-i=\"1\"]')?.className || 'N/A'")
                        n = page.evaluate("() => document.querySelectorAll('#taskList .task').length")
                        self.log(f"⏳ 任务状态[{i*10+10}s] task0={t0[:60]} task1={t1[:60]} 任务数={n}")
                    except Exception as e:
                        self.log(f"⏳ 状态读取失败: {e}")

            # ================= HUMAN VERIFY =================
            self.log("🎯 点击人机验证任务(Confirm you are human)")
            try:
                el = page.locator("#taskList .task[data-i='1']")
                el.scroll_into_view_if_needed(timeout=10000)
                el.click(force=True, timeout=15000)
            except Exception:
                try:
                    page.evaluate("document.querySelector('#taskList .task[data-i=\"1\"]')?.click()")
                except Exception:
                    page.click("div.task:has-text('Confirm')", force=True)
            self.log("⏳ 等待 Turnstile 验证码...")
            frame = None
            # 1) 先等 iframe 元素出现在 DOM(未触发的 iframe 不在 page.frames 里)
            try:
                page.wait_for_selector('iframe[src*="captcha"], iframe[src*="nerventual"], iframe[src*="verify"], iframe[src*="turnstile"]', timeout=120000)
                self.log("✅ captcha iframe 元素已出现")
            except Exception as e:
                self.log(f"⚠️ iframe 元素未出现: {e}")
            # 2) 从 frames 枚举
            for f in page.frames:
                if "captcha" in f.url or "nerventual" in f.url or "verify" in f.url:
                    frame = f
                    break
            # 3) 兜底:用 frame_element().content_frame()
            if not frame:
                try:
                    el = page.query_selector('iframe[src*="captcha"], iframe[src*="nerventual"], iframe[src*="verify"]')
                    if el:
                        for _ in range(12):  # 等 content_frame 就绪(最长 60s)
                            frame = el.content_frame()
                            if frame:
                                break
                            time.sleep(5)
                except Exception:
                    pass
            if not frame:
                self.log("❌ 未找到验证码 iframe")
                all_frames = [f.url[:120] for f in page.frames]
                self.log(f"当前 frames: {all_frames}")
                self.dump_debug(page, "captcha_iframe_missing")
            else:
                self.log(f"✅ 验证码 iframe: {frame.url[:80]}")
                # xdotool 物理点击 Turnstile checkbox(zampto 方案:真实鼠标事件)
                try:
                    import subprocess
                    # 等 iframe 真正加载(frame.url 非空)
                    for _ in range(12):
                        if any("nerventual" in f.url or "captcha" in f.url for f in page.frames):
                            break
                        time.sleep(5)
                    el = page.query_selector('iframe[src*="captcha"], iframe[src*="nerventual"]')
                    if el:
                        page.evaluate("document.querySelector('iframe[src*=\"captcha\"], iframe[src*=\"nerventual\"]')?.scrollIntoView({block:'center'})")
                        time.sleep(2)
                        box = el.bounding_box()
                        win = page.evaluate("() => ({sx: window.screenX || 0, sy: window.screenY || 0, oH: window.outerHeight || 0, iH: window.innerHeight || 0})")
                        bar = max(win['oH'] - win['iH'], 0)
                        # 多点尝试:在 iframe 上部区域点击多个候选点覆盖 checkbox 位置
                        # (checkbox ≈ iframe 左上角偏移;Turnstile widget 在 captcha 页顶部)
                        points = [
                            (box['x'] + 187, box['y'] + 45),   # OCR 标定主候选
                            (box['x'] + 187, box['y'] + 30),
                            (box['x'] + 160, box['y'] + 55),
                            (box['x'] + 220, box['y'] + 45),
                            (box['x'] + box['width'] / 2, box['y'] + box['height'] / 2),  # iframe 中心
                        ]
                        for i, (px, py) in enumerate(points):
                            cx = win['sx'] + px
                            cy = win['sy'] + bar + py
                            subprocess.run(["xdotool", "mousemove", "--sync", str(int(cx)), str(int(cy))], check=False)
                            subprocess.run(["xdotool", "click", "1"], check=False)
                            self.log(f"🎯 xdotool 点击 Turnstile #{i+1} @ ({int(cx)}, {int(cy)})")
                            time.sleep(3)
                            # 检查 token 是否已生成
                            try:
                                solved = page.evaluate("() => { const b = document.querySelector('#go'); const inp = document.querySelector('input[name=\"cf-turnstile-response\"]'); return (b && !b.disabled) || (inp && inp.value && inp.value.length > 20); }")
                                if solved:
                                    self.log("✅ 点击后 token 已生成!")
                                    break
                            except Exception:
                                pass
                except Exception as e:
                    self.log(f"⚠️ xdotool 点击失败: {e}")
                try:
                    frame.wait_for_function(
                        "() => { const b = document.querySelector('#go'); return b && !b.disabled; }",
                        timeout=150000
                    )
                    self.log("🎉 Turnstile 通过,点击 Continue")
                    frame.click("#go")
                except Exception as e:
                    self.log(f"❌ Turnstile 超时/失败: {e}")
                    self.dump_debug(page, "turnstile_fail")
            # 等人机验证任务 done
            for _ in range(12):
                time.sleep(10)
                try:
                    cls = page.evaluate("() => document.querySelector('#taskList .task[data-i=\"1\"]')?.className || ''")
                    if "done" in cls:
                        self.log("✅ 人机验证完成")
                        break
                except Exception:
                    pass

            # ================= CLAIM =================
            self.log("⏳ Waiting Claim Reward available...")
            page.wait_for_function("""
            () => {
                const btn = document.querySelector("#unlockBtn");
                return btn && !btn.disabled;
            }
            """, timeout=120000)   # 任务完成后解锁
            self.log("🎉 Claim Reward")
            page.locator("#unlockBtn").click()
            time.sleep(5)

            # ================= Credit =================
            self.log("📂 再次进入账户Credit面板")
            page.goto(Credit_URL, wait_until="domcontentloaded", timeout=90000)
            self.human_wait()
            credit_after = self.get_credit(page)
            #self.dump_debug(page, "Credit", "Credit loaded")
            
            self.dump_debug(page, "🚀Freemchosting 自动领Credit", f"🕒执行脚本前Credit余额: {credit_before}\n🎉执行脚本后Credit余额: {credit_after}")

            self.log("✅ 流程完毕")

            browser.close()


if __name__ == "__main__":
    FreemchostingClaimPW().run()
