# freemchosting UC 版 — SeleniumBase undetected Chrome + xdotool 物理点击(参考 zampto 方案)
import os
import time
import json
import random
import subprocess
import requests
import re
from seleniumbase import SB
from selenium.webdriver.common.by import By

PROXY_URL = os.getenv("PROXY", "")
COOKIE2 = os.getenv("COOKIE2")
COOKIE3 = os.getenv("COOKIE3")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

MAIN_URL = "https://client.freemchosting.com/login"
DASHBOARD_URL = "https://client.freemchosting.com/dashboard"
TARGET_URL = "https://client.freemchosting.com/rewards"
Credit_URL = "https://client.freemchosting.com/account/credits"

# ============ CF Turnstile helper(移植自 zampto) ============
_EXPAND_JS = """(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden') {
            el.style.overflow = 'visible';
            el.style.zIndex = '999999';
        }
        el.style.minWidth = 'max-content';
    }
    return 'done';
})()"""

_SOLVED_JS = """(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()"""

_HAS_CF_IFRAME_JS = """(function(){
    var ifs = document.querySelectorAll('iframe');
    for (var i=0;i<ifs.length;i++){
        var s = (ifs[i].src||'').toLowerCase();
        if (s.indexOf('captcha')>=0 || s.indexOf('nerventual')>=0 || s.indexOf('turnstile')>=0 || s.indexOf('challenges')>=0) {
            return true;
        }
    }
    return false;
})()"""

_COORDS_JS = """(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.indexOf('captcha')>=0 || src.indexOf('nerventual')>=0 || src.indexOf('turnstile')>=0 || src.indexOf('challenges')>=0) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()"""

_WININFO_JS = """(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()"""

_INJECT_TOKEN_LISTENER_JS = """(function() {
    if (window.__cf_token_listener_injected__) return;
    window.__cf_token_listener_injected__ = true;
    window.__cf_turnstile_token__ = '';
    window.addEventListener('message', function(e) {
        try {
            var d = e.data;
            if (!d || typeof d !== 'object') return;
            if (d.event === 'food') return;
            var token = d.token || d.response;
            if (token && token.length > 20) {
                window.__cf_turnstile_token__ = token;
                var inputs = document.querySelectorAll(
                    'input[name="cf-turnstile-response"], input[name="cf_turnstile_response"]'
                );
                for (var i = 0; i < inputs.length; i++) {
                    try {
                        var nativeSet = Object.getOwnPropertyDescriptor(
                            HTMLInputElement.prototype, 'value'
                        ).set;
                        nativeSet.call(inputs[i], token);
                        inputs[i].dispatchEvent(new Event('input',  {bubbles: true}));
                        inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                    } catch(err) {
                        inputs[i].value = token;
                    }
                }
            }
        } catch(err) {}
    });
})()"""

_READ_CAPTURED_TOKEN_JS = """(function(){
    return window.__cf_turnstile_token__ || '';
})()"""


def _eval_js(sb, js, default=None):
    try:
        return sb.execute_script(js)
    except Exception:
        return default


def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls],
                               capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]],
                               timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass


def _xdotool_click(x, y):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")


def _click_turnstile(sb):
    coords = _eval_js(sb, _COORDS_JS, default=None)
    if not coords:
        print("[cf] unable to locate turnstile coords")
        return
    wi = _eval_js(sb, _WININFO_JS, default={"sx": 0, "sy": 0, "oh": 800, "ih": 768})
    bar = wi["oh"] - wi["ih"]
    ax = coords["cx"] + wi["sx"]
    ay = coords["cy"] + wi["sy"] + bar
    _xdotool_click(ax, ay)


def is_turnstile_present(sb):
    return bool(_eval_js(sb, _HAS_CF_IFRAME_JS, default=False))


def is_turnstile_solved(sb):
    if bool(_eval_js(sb, _SOLVED_JS, default=False)):
        return True
    cap = str(_eval_js(sb, _READ_CAPTURED_TOKEN_JS, default="") or "")
    return len(cap) > 20


def handle_turnstile(sb, max_wait_sec=120):
    """单次 xdotool 物理点击 + 长等 token(移植 zampto)"""
    print("检测到 Cloudflare 验证,开始处理(单次点击 + 长等模式)...", flush=True)
    try:
        sb.execute_script(_INJECT_TOKEN_LISTENER_JS)
    except Exception:
        pass
    time.sleep(2)
    if is_turnstile_solved(sb):
        print("已通过(已有 token)", flush=True)
        return True
    for _ in range(3):
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.5)
    if is_turnstile_solved(sb):
        print("已通过(撑开后捕获)", flush=True)
        return True
    try:
        sb.execute_script(
            "var a = document.querySelector('input[name=\"cf-turnstile-response\"]');"
            "if (a && a.parentElement) {"
            "  a.parentElement.scrollIntoView({behavior:'smooth', block:'center'});"
            "}"
        )
    except Exception:
        pass
    time.sleep(1.5)
    _click_turnstile(sb)
    print("Turnstile 点击完成(单次 xdotool)", flush=True)
    deadline = time.time() + max_wait_sec
    poll = 0.5
    elapsed = 0.0
    while time.time() < deadline:
        time.sleep(poll)
        elapsed += poll
        if is_turnstile_solved(sb):
            print(f"Turnstile 通过(等待 {elapsed:.1f}s)", flush=True)
            return True
    print(f"Turnstile 未通过(已等待 {max_wait_sec}s,无 token)", flush=True)
    return False


def click_continue_in_captcha_frame(sb):
    """切到 captcha iframe 点 Continue(#go)"""
    try:
        driver = sb.driver
        for i, f in enumerate(driver.find_elements(By.TAG_NAME, "iframe")):
            src = f.get_attribute("src") or ""
            if "captcha" in src or "nerventual" in src:
                driver.switch_to.frame(f)
                print(f"已切入 captcha frame #{i}", flush=True)
                # 等 #go 可用
                deadline = time.time() + 60
                while time.time() < deadline:
                    try:
                        go = driver.find_element(By.ID, "go")
                        if go.is_enabled():
                            go.click()
                            print("✅ Continue 已点击", flush=True)
                            break
                    except Exception:
                        pass
                    time.sleep(1)
                driver.switch_to.default_content()
                return True
    except Exception as e:
        print(f"continue 点击失败: {e}", flush=True)
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
    return False


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wait_el(sb, sel, timeout=30):
    """JS 轮询等待元素;'//' 开头按 XPath(UC/CDP 模式必须用 JS)"""
    if sel.startswith(("//", "./", "(")):
        js = f"return document.evaluate('{sel}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue !== null"
    else:
        js = f"return document.querySelectorAll('{sel}').length > 0"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if sb.execute_script(js):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def click_js(sb, sel):
    """JS 点击(滚动 + click)"""
    if sel.startswith(("//", "./", "(")):
        js = f"""var e = document.evaluate('{sel}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; if (e) {{ e.scrollIntoView({{block:'center'}}); e.click(); }}"""
    else:
        js = f"""var e = document.querySelector('{sel}'); if (e) {{ e.scrollIntoView({{block:'center'}}); e.click(); }}"""
    sb.execute_script(js)


def run():
    log("🚀 Freemchosting UC 版启动")
    sb_args = {}
    if PROXY_URL:
        sb_args["proxy"] = PROXY_URL

    with SB(uc=True, test=True, locale="en", headless2=False, **sb_args) as sb:
        log("浏览器启动成功")

        # IP 检查
        try:
            sb.open("https://api.ipify.org/?format=json", timeout=30)
            log(f"当前 IP: {sb.get_text('body')}")
        except Exception as e:
            log(f"IP 检查失败: {e}")

        # 登录态
        log("🔗 进入主站")
        sb.open(MAIN_URL, timeout=60)
        time.sleep(random.uniform(3, 5))
        sb.driver.add_cookie({"name": "paymenter_remember", "value": COOKIE2, "domain": "client.freemchosting.com", "path": "/"})
        sb.driver.add_cookie({"name": "paymenter_session", "value": COOKIE3, "domain": "client.freemchosting.com", "path": "/"})
        time.sleep(1)
        sb.open(DASHBOARD_URL, timeout=60)
        time.sleep(random.uniform(4, 6))
        log(f"面板 URL: {sb.get_current_url()}")

        # Credit
        log("📂 进入Credit面板")
        sb.open(Credit_URL, timeout=60)
        time.sleep(random.uniform(4, 6))
        try:
            sb.wait_for_element("p.text-primary-100", timeout=30)
            texts = [t.text for t in sb.find_elements("p.text-primary-100")]
            total = 0
            for text in texts:
                m = re.search(r"Credit\s+([\d,]+)", text)
                if m:
                    total += float(m.group(1).replace(",", "."))
            log(f"Credit before: {round(total, 2)}")
        except Exception as e:
            log(f"Credit 读取失败(可能 cookie 无效): {e}")
            sb.save_screenshot("debug_credit_fail.png")
            return

        # 奖励页
        log("📂 进入奖励面板")
        sb.open(TARGET_URL, timeout=60)
        time.sleep(random.uniform(4, 6))

        # Generate Offer
        log("🔗 生成广告链接")
        if not wait_el(sb, "//button[contains(text(),'Generate Offer')]", timeout=30):
            log("❌ Generate Offer 按钮未找到")
            sb.save_screenshot("debug_gen_fail.png")
            return
        click_js(sb, "//button[contains(text(),'Generate Offer')]")
        time.sleep(random.uniform(5, 8))

        # Start
        log("🔗 开始点击广告")
        if not wait_el(sb, "//a[contains(text(),'Start')]", timeout=60):
            log("❌ Start 链接未找到")
            sb.save_screenshot("debug_start_fail.png")
            return
        click_js(sb, "//a[contains(text(),'Start')]")
        time.sleep(random.uniform(5, 8))

        # Start 后处理新窗口/诊断
        try:
            handles = sb.driver.window_handles
            log(f"窗口数: {len(handles)}")
            if len(handles) > 1:
                sb.driver.switch_to.window(handles[-1])
                time.sleep(2)
                log(f"已切到新窗口: {sb.get_current_url()}")
        except Exception as e:
            log(f"窗口处理: {e}")
        log(f"当前 URL: {sb.get_current_url()}")

        # 任务 0(JS 操作)
        log("🎯 点击广告内任务(文章)")
        if not wait_el(sb, "#taskList .task", timeout=60):
            log("❌ taskList 未出现")
            sb.save_screenshot("debug_tasklist_fail.png")
            return
        click_js(sb, "#taskList .task[data-i='0']")
        log("⏳ 等待文章任务完成(约50秒)...")
        for _ in range(30):
            time.sleep(10)
            try:
                cls = sb.execute_script("var e = document.querySelector('#taskList .task[data-i=\"0\"]'); return e ? (e.className || '') : ''")
                if "done" in cls:
                    log("✅ 文章任务完成")
                    break
            except Exception:
                pass

        # 任务 1(Turnstile)
        log("🎯 点击人机验证任务(Confirm you are human)")
        if wait_el(sb, "#taskList .task[data-i='1']", timeout=15):
            click_js(sb, "#taskList .task[data-i='1']")
        else:
            try:
                sb.execute_script("document.querySelector('#taskList .task[data-i=\"1\"]')?.click()")
            except Exception:
                pass
        log("⏳ 等待 Turnstile 验证码...")
        for _ in range(24):
            time.sleep(5)
            if is_turnstile_present(sb):
                log("✅ Turnstile iframe 出现")
                break
        ok = handle_turnstile(sb, max_wait_sec=150)
        if ok:
            log("🎉 Turnstile 通过!")
            click_continue_in_captcha_frame(sb)
        else:
            log("❌ Turnstile 未通过")
            sb.save_screenshot("debug_turnstile_fail.png")

        # 等人机验证任务 done
        for _ in range(12):
            time.sleep(10)
            try:
                cls = sb.execute_script("var e = document.querySelector('#taskList .task[data-i=\"1\"]'); return e ? (e.className || '') : ''")
                if "done" in cls:
                    log("✅ 人机验证完成")
                    break
            except Exception:
                pass

        # Claim
        log("⏳ Waiting Claim Reward available...")
        try:
            deadline = time.time() + 120
            ready = False
            while time.time() < deadline:
                ready = bool(sb.execute_script("var e = document.querySelector('#unlockBtn'); return e ? !e.disabled : false"))
                if ready:
                    break
                time.sleep(2)
            if ready:
                log("🎉 Claim Reward")
                click_js(sb, "#unlockBtn")
                time.sleep(5)
            else:
                log("❌ unlockBtn 未解锁")
                sb.save_screenshot("debug_unlock_fail.png")
        except Exception as e:
            log(f"❌ Claim 失败: {e}")
            sb.save_screenshot("debug_unlock_fail.png")

        # Credit after
        try:
            sb.open(Credit_URL, timeout=60)
            time.sleep(4)
            sb.wait_for_element("p.text-primary-100", timeout=30)
            texts = [t.text for t in sb.find_elements("p.text-primary-100")]
            total = 0
            for text in texts:
                m = re.search(r"Credit\s+([\d,]+)", text)
                if m:
                    total += float(m.group(1).replace(",", "."))
            log(f"Credit after: {round(total, 2)}")
        except Exception as e:
            log(f"Credit after 读取失败: {e}")

        log("✅ 流程完毕")
        sb.save_screenshot("debug_final.png")


if __name__ == "__main__":
    run()
