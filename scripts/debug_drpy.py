#!/usr/bin/env python3
"""AI 循环调试 drpyS 脚本：生成→测试→修复→再测试"""
import sys, os, json, time, requests, subprocess, re
from pathlib import Path

# 配置
DRPY_NODE = "http://127.0.0.1:5757"
SPIDER_JS_DIR = Path("/home/user/Doubao/chats/2992679393100546/peekpro_analysis/fix_deps/drpy-node2.0.4-merged-final/spider/js")
KEEPER_DIR = Path("/home/user/Doubao/chats/2992679393100546/shuyuan-keeper")
sys.path.insert(0, str(KEEPER_DIR / "scripts"))

from keeper import (
    convert_legado_to_drpy, validate_drpy_script,
    AI_BASE, AI_KEY, AI_MODEL, get_session
)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def fetch_site_html(url, timeout=10):
    """拉取站点HTML做分析"""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        return r.text[:3000]  # 前3KB
    except Exception as e:
        return f"Error: {e}"

def test_module(module_name, wd="斗破苍穹"):
    """通过 T4 接口测试模块，返回 (success, message, data)"""
    import urllib.parse
    encoded = urllib.parse.quote(module_name)
    wd_enc = urllib.parse.quote(wd)
    url = f"{DRPY_NODE}/api/{encoded}?wd={wd_enc}&refresh=1"
    try:
        r = requests.get(url, timeout=20)
        text = r.text
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {text[:200]}", None
        try:
            data = r.json()
        except:
            return False, f"非JSON: {text[:200]}", None
        if "error" in data:
            return False, f"运行错误: {data['error']}", data
        lst = data.get("list", [])
        if not lst:
            return False, "搜索返回空列表", data
        return True, f"返回{len(lst)}条结果", data
    except Exception as e:
        return False, f"请求异常: {e}", None

def ai_repair_script(original_script, error_msg, site_html, legado_info, attempt):
    """根据错误信息让AI修复脚本"""
    prompt = (
        f"drpyS脚本运行失败了。请修复它。\n\n"
        f"【当前脚本】\n{original_script[:3000]}\n\n"
        f"【错误信息】\n{error_msg}\n\n"
        f"【站点实际HTML片段】\n{site_html[:2000]}\n\n"
        f"【Legado书源信息】\n{legado_info[:1000]}\n\n"
        f"请修复脚本中的问题，确保：\n"
        f"1. 搜索URL正确（从HTML中找真实的搜索表单action）\n"
        f"2. CSS选择器正确（从HTML中找真实的列表class）\n"
        f"3. 用 let {{input}} = this; 开头\n"
        f"4. 用 cheerio.load(html) 解析\n"
        f"5. 列表项用 {{title,url,desc,pic_url}}\n"
        f"6. 用 setResult(d) 返回\n\n"
        f"只输出修复后的完整JS代码，不要解释。"
    )
    try:
        resp = get_session().post(
            AI_BASE.rstrip("/") + "/chat/completions",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + AI_KEY},
            json={
                "model": AI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            },
            timeout=90
        )
        if resp.status_code == 200:
            text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            m = re.search(r'```(?:javascript|js)?\s*(.*?)```', text, re.S)
            if m:
                return m.group(1).strip()
            if "var rule" in text:
                return text.strip()
    except Exception as e:
        print(f"  AI修复调用失败: {e}")
    return None

def debug_one_book(book_source, max_retries=3):
    """调试单个书源"""
    name = book_source.get("bookSourceName", "未知")
    url = book_source.get("bookSourceUrl", "")
    module_name = f"{name.replace('/', '_')[:20]}[书]"
    
    print(f"\n=== 调试: {name} ===")
    print(f"  站点: {url}")
    
    # 先检查站点是否活着
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=8)
        if r.status_code != 200:
            print(f"  ❌ 站点死了 (HTTP {r.status_code})")
            return None
        site_html = r.text[:3000]
    except Exception as e:
        print(f"  ❌ 站点无法访问: {e}")
        return None
    
    # 第1次生成
    print(f"  [1/{max_retries}] 生成初始脚本...")
    script = convert_legado_to_drpy(book_source)
    if not script:
        print(f"  ❌ AI生成失败")
        return None
    
    # Legado信息用于修复
    legado_info = json.dumps({
        "search": book_source.get("ruleSearch", {}),
        "bookInfo": book_source.get("ruleBookInfo", {}),
        "content": book_source.get("ruleContent", {}),
    }, ensure_ascii=False)
    
    for attempt in range(1, max_retries + 1):
        # 验证脚本格式
        if not validate_drpy_script(script):
            print(f"  [尝试{attempt}] 格式验证失败，重试AI...")
            script = convert_legado_to_drpy(book_source)
            if not script:
                continue
        
        # 写入drpy-node
        script_file = SPIDER_JS_DIR / f"{module_name}.js"
        script_file.write_text(script, encoding="utf-8")
        
        # 测试
        time.sleep(1)  # 等drpy-node加载
        success, msg, data = test_module(module_name)
        
        if success:
            print(f"  ✅ 成功! {msg}")
            # 保存到keeper仓库
            keeper_script_dir = KEEPER_DIR / "docs" / "spider" / "js"
            keeper_script_dir.mkdir(parents=True, exist_ok=True)
            (keeper_script_dir / f"{module_name}.js").write_text(script, encoding="utf-8")
            return script
        else:
            print(f"  [尝试{attempt}] 失败: {msg}")
            if attempt < max_retries:
                print(f"  → AI修复中...")
                repaired = ai_repair_script(script, msg, site_html, legado_info, attempt)
                if repaired:
                    script = repaired
                else:
                    print(f"  → AI修复失败，换个角度重试")
                    # 重新生成
                    script = convert_legado_to_drpy(book_source)
    
    print(f"  ❌ {max_retries}次尝试后仍失败")
    return None


def main():
    books = json.loads((KEEPER_DIR / "docs" / "valid.json").read_text(encoding="utf-8"))
    limit = int(os.environ.get("DEBUG_LIMIT", "5"))
    
    # 找活着的站点
    alive_books = []
    for i, b in enumerate(books[:100]):
        url = b.get("bookSourceUrl", "")
        if not url.startswith("http"):
            continue
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=5)
            if r.status_code == 200:
                alive_books.append((i, b))
                print(f"  [{i}] {b['bookSourceName'][:25]} 活着")
                if len(alive_books) >= limit:
                    break
        except:
            pass
    
    print(f"\n找到 {len(alive_books)} 个存活站点，开始调试...")
    
    success = 0
    for idx, (i, b) in enumerate(alive_books):
        result = debug_one_book(b)
        if result:
            success += 1
        print(f"\n进度: {idx+1}/{len(alive_books)}, 成功: {success}")
    
    print(f"\n=== 完成: {success}/{len(alive_books)} 成功 ===")


if __name__ == "__main__":
    main()
