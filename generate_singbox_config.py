import os
import json
import base64
import sys
from urllib.parse import urlparse, parse_qs, unquote

def generate_config(proxy_url):
    # 如果已经是 JSON 格式，直接原样返回
    proxy_url = proxy_url.strip()
    if proxy_url.startswith('{') and proxy_url.endswith('}'):
        try:
            json.loads(proxy_url)
            return proxy_url
        except:
            pass

    # 处理单节点链接
    parsed = urlparse(proxy_url)
    scheme = parsed.scheme.lower()
    
    outbound = {
        "tag": "proxy"
    }

    if scheme == "tuic":
        # tuic://uuid:password@host:port?congestion_control=bbr...
        outbound["type"] = "tuic"
        outbound["server"] = parsed.hostname
        outbound["server_port"] = parsed.port
        
        auth_user = unquote(parsed.username or "")
        auth_pass = unquote(parsed.password or "")
        
        if ":" in auth_user:
            outbound["uuid"], outbound["password"] = auth_user.split(":", 1)
        else:
            outbound["uuid"] = auth_user
            outbound["password"] = auth_pass
        
        params = parse_qs(parsed.query)
        outbound["congestion_control"] = params.get("congestion_control", ["bbr"])[0]
        outbound["udp_relay_mode"] = params.get("udp_relay_mode", ["quic-rfc"])[0]
        
        outbound["tls"] = {"enabled": True}
        if "sni" in params: outbound["tls"]["server_name"] = params["sni"][0]
        if "alpn" in params: outbound["tls"]["alpn"] = params["alpn"][0].split(',')
        if "insecure" in params and params["insecure"][0] in ["1", "true"]: outbound["tls"]["insecure"] = True

    elif scheme in ["hysteria2", "hy2"]:
        outbound["type"] = "hysteria2"
        outbound["server"] = parsed.hostname
        outbound["server_port"] = parsed.port
        outbound["password"] = unquote(parsed.username or "")
            
        params = parse_qs(parsed.query)
        outbound["tls"] = {"enabled": True}
        if "sni" in params: outbound["tls"]["server_name"] = params["sni"][0]
        if "insecure" in params and params["insecure"][0] in ["1", "true"]: outbound["tls"]["insecure"] = True

    elif scheme == "vless":
        outbound["type"] = "vless"
        outbound["server"] = parsed.hostname
        outbound["server_port"] = parsed.port
        outbound["uuid"] = unquote(parsed.username or "")
        params = parse_qs(parsed.query)
        if params.get("flow"):
            outbound["flow"] = params["flow"][0]
        sec = params.get("security", ["none"])[0]
        if sec in ["tls", "reality"] or params.get("tls", ["none"])[0] == "tls":
            outbound["tls"] = {
                "enabled": True,
                "server_name": params.get("sni", [""])[0] or params.get("host", [""])[0] or parsed.hostname
            }
            if params.get("fp"):
                outbound["tls"]["utls"] = {"enabled": True, "fingerprint": params["fp"][0]}
            if params.get("alpn"):
                outbound["tls"]["alpn"] = [x for x in params["alpn"][0].split(",") if x]
            if sec == "reality" or params.get("pbk"):
                outbound["tls"]["reality"] = {
                    "enabled": True,
                    "public_key": params.get("pbk", [""])[0],
                    "short_id": params.get("sid", [""])[0]
                }
        net = params.get("type", ["tcp"])[0]
        if net == "ws":
            ws_path = params.get("path", ["/"])[0]
            ws_transport = {
                "type": "ws",
                "path": ws_path,
                "headers": {"Host": params.get("host", [""])[0] or params.get("sni", [""])[0] or parsed.hostname}
            }
            if "?" in ws_path:
                path_only, query = ws_path.split("?", 1)
                ws_transport["path"] = path_only or "/"
                ws_params = parse_qs(query)
                if ws_params.get("ed"):
                    ws_transport["max_early_data"] = int(ws_params["ed"][0])
                    ws_transport["early_data_header_name"] = "Sec-WebSocket-Protocol"
            outbound["transport"] = ws_transport
        elif net == "grpc":
            outbound["transport"] = {"type": "grpc", "service_name": params.get("serviceName", [""])[0] or params.get("path", [""])[0]}
        elif net == "tcp" and params.get("host"):
            outbound["transport"] = {"type": "http", "host": [params["host"][0]], "path": params.get("path", ["/"])[0]}

    elif scheme == "trojan":
        outbound["type"] = "trojan"
        outbound["server"] = parsed.hostname
        outbound["server_port"] = parsed.port
        outbound["password"] = unquote(parsed.username or "")
        
        params = parse_qs(parsed.query)
        outbound["tls"] = {"enabled": True}
        if "sni" in params: outbound["tls"]["server_name"] = params["sni"][0]

    elif scheme in ["ss", "shadowsocks"]:
        # ss://base64(method:password)@host:port
        outbound["type"] = "shadowsocks"
        outbound["server"] = parsed.hostname
        outbound["server_port"] = parsed.port
        
        if parsed.username:
            try:
                decoded = base64.b64decode(parsed.username + "==").decode()
                if ":" in decoded:
                    outbound["method"], outbound["password"] = decoded.split(":", 1)
            except:
                outbound["method"] = unquote(parsed.username)
                outbound["password"] = unquote(parsed.password or "")

    elif scheme == "vmess":
        # 两种格式:
        #   1) vmess://base64(json_config)  — 旧版(标准 base64 含 +/ 字符,不能用 urlparse 的 netloc!会被 / 截断)
        #   2) vmess://uuid@host:port?type=ws&security=tls&... — 新版明文(v2rayN 导出)
        try:
            v_info = None
            body = proxy_url.split("://", 1)[1].split("#")[0]
            # 格式1:base64(JSON),容忍 base64url 字符与 padding 缺失
            try:
                b64 = body.replace('-', '+').replace('_', '/')
                b64 += '=' * (-len(b64) % 4)
                v_info = json.loads(base64.b64decode(b64).decode())
            except Exception:
                pass
            if v_info is None:
                # 格式2:明文 uuid@host:port?query
                parsed2 = urlparse("vmess://" + body)
                params = parse_qs(parsed2.query)
                sec = params.get("security", ["none"])[0]
                v_info = {
                    "add": parsed2.hostname,
                    "port": str(parsed2.port or 443),
                    "id": unquote(parsed2.username or ""),
                    "net": params.get("type", ["tcp"])[0],
                    "security": sec,
                    "tls": "tls" if sec in ["tls", "reality"] else "",
                    "path": params.get("path", [""])[0],
                    "host": params.get("host", [""])[0],
                    "sni": params.get("sni", [""])[0],
                    "fp": params.get("fp", [""])[0],
                    "alpn": params.get("alpn", [""])[0],
                    "flow": params.get("flow", [""])[0],
                    "pbk": params.get("pbk", [""])[0],
                    "sid": params.get("sid", [""])[0],
                }
            outbound["type"] = "vmess"
            outbound["server"] = v_info.get("add")
            outbound["server_port"] = int(v_info.get("port", 443))
            outbound["uuid"] = v_info.get("id")
            outbound["security"] = v_info.get("scy") or v_info.get("security") or "auto"
            outbound["alter_id"] = int(v_info.get("aid", 0))
            if v_info.get("flow"):
                outbound["flow"] = v_info["flow"]

            tls_on = v_info.get("tls") == "tls" or v_info.get("security") in ["tls", "reality"]
            if tls_on:
                outbound["tls"] = {
                    "enabled": True,
                    "server_name": v_info.get("sni") or v_info.get("host") or v_info.get("add")
                }
                if v_info.get("fp"):
                    outbound["tls"]["utls"] = {"enabled": True, "fingerprint": v_info.get("fp")}
                if v_info.get("alpn"):
                    outbound["tls"]["alpn"] = [x for x in v_info.get("alpn", "").split(",") if x]
                if v_info.get("security") == "reality" or v_info.get("pbk"):
                    outbound["tls"]["reality"] = {
                        "enabled": True,
                        "public_key": v_info.get("pbk", ""),
                        "short_id": v_info.get("sid", "")
                    }

            net = v_info.get("net")
            if net == "ws":
                ws_path = v_info.get("path") or "/"
                ws_headers = {"Host": v_info.get("host") or v_info.get("sni") or v_info.get("add")}
                ws_transport = {
                    "type": "ws",
                    "path": ws_path,
                    "headers": ws_headers
                }
                if "?" in ws_path:
                    path_only, query = ws_path.split("?", 1)
                    ws_transport["path"] = path_only or "/"
                    ws_params = parse_qs(query)
                    if ws_params.get("ed"):
                        ws_transport["max_early_data"] = int(ws_params["ed"][0])
                        ws_transport["early_data_header_name"] = "Sec-WebSocket-Protocol"
                outbound["transport"] = {
                    **ws_transport
                }
            elif net == "grpc":
                outbound["transport"] = {"type": "grpc", "service_name": v_info.get("path", "")}
            elif net == "tcp" and v_info.get("host"):
                outbound["transport"] = {"type": "http", "host": [v_info.get("host")], "path": v_info.get("path") or "/"}
        except:
            print("Failed to parse VMess config")
            sys.exit(1)

    elif scheme == "socks5":
        outbound["type"] = "socks"
        outbound["server"] = parsed.hostname
        outbound["server_port"] = parsed.port
        user = unquote(parsed.username or "")
        passwd = unquote(parsed.password or "")
        if user:
            outbound["username"] = user
            outbound["password"] = passwd

    else:
        # 其他协议回退到直接填入（可能是简单订阅或不支持的协议）
        print(f"Unknown scheme: {scheme}, please use full JSON for complex configs.")
        sys.exit(1)

    # 组装完整配置
    config = {
        "log": {"level": "info"},
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 8080
            }
        ],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"}
        ],
        "route": {
            "rules": [
                {
                    "inbound": ["mixed-in"],
                    "outbound": "proxy"
                }
            ]
        }
    }
    return json.dumps(config, indent=2)

if __name__ == "__main__":
    proxy_str = os.environ.get("PROXY_STR", "")
    if not proxy_str:
        print("PROXY_STR is empty")
        sys.exit(1)
        
    final_config = generate_config(proxy_str)
    with open("config.json", "w") as f:
        f.write(final_config)
    print("Successfully generated config.json")
