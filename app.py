# -*- coding: utf-8 -*-
"""枫独 · OPC 经营助手 —— GOAI 无界应用大赛 AI+金融 赛道 Demo

入口：python app.py
架构：联网搜索匹配（核心，需网络）+ 规则判定资格 + LLM（理解/搜索词/合规问答）
联网搜索不可用（断网/受限）时：降级本地通用政策库 + 规则引擎 → 不白屏、不造假（保命兜底，非核心）

运行前设置（增强 LLM 语义理解 / 搜索词生成 / 合规问答）：
    set MODELSCOPE_API_KEY=ms-xxx      (Windows)
    export MODELSCOPE_API_KEY=ms-xxx   (Linux)
    （联网搜索更稳可配 BING_SEARCH_API_KEY 或 SEARXNG_URL）
"""
import sys
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 中文编码
except Exception:
    pass

import gradio as gr

from policies import available_regions, region_info, REGION_LABELS, general
from utils import business_profile as bp
from utils.rule_engine import summary, match_policies
from utils.state_model import compute_indices, build_recommendations
from utils import api_client
from utils import policy_searcher
from prompts import agent_prompts

# ---------------------------------------------------------------- 素材加载（base64 内嵌，跨环境无路径问题）
def _asset_b64(filename: str) -> str:
    """读取 assets/<filename> 转 base64 data URI，找不到返回空串。"""
    import base64
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", filename)
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    ext = filename.rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    return f"data:{mime};base64,{b64}"


LOGO_B64 = _asset_b64("logo.webp") or _asset_b64("logo.png")
BANNER_B64 = _asset_b64("banner.webp") or _asset_b64("banner.png")
# 全页背景图：bg.webp（18KB 压缩版，视觉同原图，省 1.7MB）
# 主版显示背景图；高对比版（投影）用 CSS 隐藏 → 纯白高可读
BG_B64 = _asset_b64("bg.webp") or _asset_b64("bg.png")
# 地区横幅用压缩版（2KB，可安全放进 CSS background）
REGION_BANNER_B64 = _asset_b64("region_banner_small.webp") or _asset_b64("region_banner.png")


# ---------------------------------------------------------------- 枫叶色板（浅暖橙红系）
MAPLE_RED = "#C84B31"       # 枫红（顶栏/强调）
MAPLE_GOLD = "#E0A03C"      # 枫金（数据强调）
BG = "#F1AE86"              # 页面背景：浅枫橙红（浅亮暖色，枫叶感）
BG_DEEP = "#F4BC99"          # 组件底：偏白橙红（Tab 内容/卡片底）
PANEL = "#FCE7D2"            # 组件面板：偏白橙红（下拉/输入/对话框底）
PANEL_LIGHT = "#F6CBA6"      # 组件面板亮阶（hover/选中）
TEXT = "#4A2C1A"            # 主文字：深棕
TEXT_SUB = "#8A5A3A"         # 次文字：暖棕
TEXT_DARK = "#FFF6EF"       # 深色底上的亮字（驾驶舱内）
COCKPIT = "#A64E30"          # 驾驶舱：橙红容器（局部深色，非大范围）
COCKPIT_DEEP = "#8A3D24"     # 橙红加深（进度条轨道/卡片底）
COCKPIT_BORDER = "#E08A5E"   # 橙红亮边
BUBBLE_USER = "#F6CBA6"      # 用户气泡：浅杏橙
BUBBLE_AI = "#FCE7D2"        # AI 气泡：偏白橙红

# ---------------------------------------------------------------- 高对比主题（备用版：投影仪专用）
# 决赛投影仪高光下，暖橙主题易泛白 → 用 UI_THEME=high_contrast 切换成纯白底黑字高对比版。
# 平时默认暖橙主版，投影糊了再切换。同一份代码，两套主题，互不影响。
HC_BG = "#FFFFFF"            # 纯白背景
HC_TEXT = "#000000"          # 纯黑文字
HC_ACCENT = "#0052CC"        # 蓝色强调（可读性最高的强调色）
HC_PANEL = "#F5F5F5"         # 浅灰面板（组件底，对比清晰）
HC_BORDER = "#888888"        # 中等灰边框
HC_RED = "#CC0000"          # 风险红

# 高对比颜色覆盖块（叠加在完整主版 CSS 之后 → 布局与主版一致，只换色）
HC_OVERLAY = """
/* ===== 高对比投影版：纯白底 + 纯黑字 + 蓝强调（叠加在主版 CSS 后）===== */
html { background: #ffffff !important; }
body { background: #ffffff !important; color: #000000 !important; }
gradio-app, .gradio-app, .gradio-container { background: #ffffff !important; }
#full-bg { display: none !important; }   /* 隐藏背景图，纯白更清晰 */
#brand-bar, #brand-bar.brand-bar-gradient { background: #0052CC !important; }
.brand-content { background: #0052CC !important; color: #ffffff !important; }
.brand-title, .brand-sub, .brand-content * { color: #ffffff !important; }
.brand-banner-img { opacity: 0.2 !important; }
/* 地区标签：纯蓝底白字（原白字白底看不清） */
.region-pill { background: #0d47a1 !important; color: #ffffff !important;
  border: 1px solid #ffffff !important; }
.gradio-container label, .gradio-container .block, .gradio-container .form,
.gradio-container textarea, .gradio-container input[type="text"],
.gradio-container select { background: #ffffff !important; color: #000000 !important;
  border: 2px solid #444444 !important; }
.gradio-container textarea::placeholder, .gradio-container input::placeholder { color: #555555 !important; }
.gradio-container [role="tab"] { color: #000000 !important; font-weight: 700 !important; }
.gradio-container [role="tab"].selected { background: #0052CC !important; color: #ffffff !important; }
.gradio-container .tabitem { background: #ffffff !important; border: 2px solid #aaaaaa !important; }
.gradio-container .prose, .gradio-container .markdown,
.gradio-container .prose :is(p, h1, h2, h3, h4, ul, ol, li, strong, em, span, blockquote, code) {
  color: #000000 !important; }
.wrapper:has(.bubble-wrap) { background: #f0f0f0 !important; }
.bubble-wrap { background: #f0f0f0 !important; }
.bubble-wrap *, .message-row *, .bot.message *, .user.message *,
.message, .message *, .bot .message, .user .message { color: #000000 !important; }
.message-row.bubble.bot-row .bot.message,
.message-row.bubble.user-row .user.message { background: #f5f5f5 !important; color: #000000 !important;
  border: 2px solid #666666 !important; }
.gradio-container .prose blockquote { background: #f0f0f0 !important; color: #000000 !important;
  border-left: 4px solid #0052CC !important; }
.wrapper:has(.bubble-wrap) .icon-button-wrapper,
.wrapper:has(.bubble-wrap) .icon-button { background: #e8e8e8 !important; }
.wrapper:has(.bubble-wrap) .icon-button,
.wrapper:has(.bubble-wrap) .icon-button *,
.wrapper:has(.bubble-wrap) .icon-button svg,
.wrapper:has(.bubble-wrap) .icon-button svg * { color: #000000 !important; fill: #000000 !important; }
.wrapper:has(.bubble-wrap) .icon-button { --bg-color: #e8e8e8 !important; }
.wrapper:has(.bubble-wrap) label { color: #000000 !important; }
/* 合规横幅：深蓝底白字（原浅粉红字对比弱，覆盖 inline style） */
.hc-banner { background: #0d47a1 !important; border-color: #0d47a1 !important; color: #ffffff !important; }
.hc-banner * { color: #ffffff !important; }
.cockpit { background: #ffffff !important; color: #000000 !important; border: 3px solid #000000 !important; }
.cockpit * { color: #000000 !important; }
.cockpit-head { color: #0052CC !important; border-bottom: 2px solid #000000 !important; }
.cockpit-head, .cockpit .metric-label, .cockpit .progress, .cockpit .section-title,
.cockpit .material, .cockpit .cockpit-footer, .cockpit .metric .lab { color: #000000 !important; }
.cockpit .metric .big { color: #000000 !important; }
.cockpit .gold { color: #0052CC !important; }
.cockpit .bar { background: #e0e0e0 !important; }
.cockpit .bar-fill { background: #b0b0b0 !important; color: #000000 !important; }
.metric .big { color: #000000 !important; font-weight: 800 !important; }
.gold { color: #0052CC !important; }
.risk-low { color: #006600 !important; } .risk-mid { color: #B26A00 !important; } .risk-high { color: #CC0000 !important; }
#maple-btn { background: #0052CC !important; color: #fff !important; font-weight: 700 !important; }
#reset-btn { background: #333333 !important; color: #ffffff !important; border: 1px solid #ffffff !important; }
#prefill-btn { background: #0052CC !important; color: #fff !important; }
.gradio-container .prose a { color: #0052CC !important; font-weight: 700 !important; }
.bar { background: #e0e0e0 !important; }
.bar-fill { background: #0052CC !important; color: #fff !important; }
.region-dd { background-image: none !important; background: #ffffff !important; }
.region-dd .wrap, .region-dd .wrap-inner, .region-dd .secondary-wrap { background: #ffffff !important; }
.gradio-container option { background: #ffffff !important; color: #000000 !important; }
.gradio-container footer, .gradio-container > footer,
footer[aria-label="Gradio footer navigation"] { display: none !important; }
"""

# ---------------------------------------------------------------- CSS（浅暖橙红系）
# 全页背景改为纯色（bg 图由 HTML img 层负责，避免 CSS base64 膨胀）
CSS = f"""
:root {{
  --maple-red: {MAPLE_RED};
  --maple-gold: {MAPLE_GOLD};
  --bg: {BG};
  --text: {TEXT};
  --cockpit: {COCKPIT};
}}
/* html 背景=兜底色（画在根画布，负z图片之上）；body 必须透明，
   否则 body 背景作为 in-flow 内容在第3层绘制，会盖住 z-index:-1 的全页背景图 */
html {{
  background: {BG} !important;
}}
body {{
  background: transparent !important;
  color: {TEXT};
  font-family: "Microsoft YaHei", sans-serif;
}}
/* gradio-app 自带不透明白底会盖住全页背景图 → 一并透明 */
gradio-app, .gradio-app {{
  background: transparent !important;
}}
.gradio-container {{
  /* 透明：让 #full-bg 全页背景图透出来（横幅修复后误盖为纯色导致背景图消失） */
  background: transparent !important;
  max-width: 100% !important;
}}
/* 全页背景 img 层：fixed 铺满，透明容器下可见；html/body 纯色兜底 */
#full-bg {{
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  z-index: -1; object-fit: cover; pointer-events: none;
  display: block;
}}
#brand-bar {{
  position: relative; overflow: hidden;
  color: #fff; padding: 0; border-radius: 0 0 16px 16px;
  margin-bottom: 12px;
  box-shadow: 0 3px 14px rgba(200, 75, 49, 0.25);
}}
#brand-bar.brand-bar-gradient {{
  background: linear-gradient(135deg, {MAPLE_RED} 0%, #A83A22 100%);
  padding: 18px 28px; display: flex; align-items: center; gap: 14px;
}}
.brand-banner-img {{
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  object-fit: cover; z-index: 0; pointer-events: none;
}}
.brand-content {{
  position: relative; z-index: 1;
  display: flex; align-items: center; gap: 14px;
  padding: 18px 28px; min-height: 72px;
  /* 半透明暖枫红渐变遮罩：左侧文字区有对比度，右侧横幅自然露出 */
  background: linear-gradient(90deg, rgba(200, 75, 49, 0.72) 0%,
              rgba(200, 75, 49, 0.4) 55%, rgba(200, 75, 49, 0) 100%);
}}
.brand-logo {{
  width: 46px; height: 46px; border-radius: 10px; background: rgba(255,255,255,0.15);
  display: flex; align-items: center; justify-content: center; font-size: 26px;
  border: 1.5px solid rgba(255,255,255,0.35); flex-shrink: 0;
}}
.brand-logo-img {{
  width: 52px; height: 52px; object-fit: contain; border-radius: 10px;
  background: rgba(255, 246, 239, 0.45); padding: 4px;
  box-shadow: 0 2px 10px rgba(200, 75, 49, 0.4);
  flex-shrink: 0;
}}
.brand-title {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; }}
.brand-sub {{ font-size: 12.5px; opacity: 0.85; margin-top: 2px; }}
.region-pill {{
  margin-left: auto; background: rgba(255,255,255,0.18); padding: 6px 14px;
  border-radius: 20px; font-size: 13px; border: 1px solid rgba(255,255,255,0.3);
}}
.status-ok {{ color: #9FD99F; font-weight: 600; }}
.status-demo {{ color: {MAPLE_GOLD}; font-weight: 600; }}

/* 驾驶舱（赤陶深容器） */
.cockpit {{
  background: {COCKPIT}; color: {TEXT_DARK}; border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.25);
}}
.cockpit-head {{ font-size: 15px; font-weight: 700; color: {MAPLE_GOLD};
  border-bottom: 1px solid rgba(255,255,255,0.16); padding-bottom: 8px; margin-bottom: 10px; }}
.metric-label {{ font-size: 12px; color: #E3C9B0; margin: 10px 0 4px; }}
.bar {{ background: {COCKPIT_DEEP}; height: 16px; border-radius: 8px; overflow: hidden; }}
.bar-fill {{ height: 16px; border-radius: 8px;
  background: linear-gradient(90deg, {MAPLE_RED}, {MAPLE_GOLD});
  color: #fff; font-size: 11px; line-height: 16px; text-align: center; font-weight: 600; }}
.bar-fill.gold {{ background: linear-gradient(90deg, {MAPLE_GOLD}, #F2C25E); }}
.cockpit-row {{ display: flex; gap: 10px; margin: 12px 0; }}
.metric {{ flex: 1; background: rgba(255,255,255,0.08); border-radius: 10px;
  padding: 10px 8px; text-align: center; }}
.metric .lab {{ font-size: 11px; color: #E3C9B0; }}
.metric .big {{ font-size: 22px; font-weight: 800; margin-top: 4px; }}
.gold {{ color: {MAPLE_GOLD}; }}
.risk-low {{ color: #7FD08A; }} .risk-mid {{ color: {MAPLE_GOLD}; }} .risk-high {{ color: #FF7A70; }}
.section-title {{ font-size: 12px; color: #E3C9B0; margin: 12px 0 6px; font-weight: 600; }}
.material {{ font-size: 12.5px; padding: 4px 0; line-height: 1.5; }}
.material .ok {{ color: #9BD29B; }}
.material .warn {{ color: {MAPLE_GOLD}; }}
.cockpit-footer {{ margin-top: 14px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.16);
  font-size: 11.5px; color: #E3C9B0; }}
.progress {{ font-size: 12.5px; color: #E3C9B0; margin: 8px 0; }}

/* 卡片 & 按钮（深暖） */
.card {{ background: {BG_DEEP}; border: 1px solid {COCKPIT_BORDER}; border-radius: 14px; padding: 14px 16px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.2); }}
.footnote {{ font-size: 11.5px; color: {TEXT_SUB}; margin-top: 8px; line-height: 1.6; }}
#maple-btn {{
  background: {MAPLE_RED} !important; border: none !important; color: #fff !important;
  border-radius: 10px !important; font-weight: 600;
}}
#maple-btn:hover {{ background: #A83A22 !important; }}
#reset-btn {{ background: {COCKPIT_DEEP} !important; color: {TEXT_DARK} !important; border: 1px solid {COCKPIT_BORDER} !important; }}
#prefill-btn {{ background: {MAPLE_GOLD} !important; color: #3A2015 !important; border: none !important; font-weight: 600; }}

/* 对话区：暖橙底（比 BG_DEEP 深一档、明亮） */
.wrapper:has(.bubble-wrap) {{
  background: #EEB085 !important;
  border-radius: 14px !important;
  border: 1px solid {COCKPIT_BORDER} !important;
}}
/* 消息滚动容器：深色模式下 Gradio 会给它近黑底 rgb(28,25,23)+白字
   → 强制暖色底 + 深棕文字（深浅色模式通用，避免"对话框还是黑的"） */
.bubble-wrap {{
  background: #EEB085 !important;
  color: {TEXT} !important;
}}
.bubble-wrap * {{
  color: {TEXT} !important;
}}
/* 气泡（Gradio 6 真实类名：.message-row.bubble.bot-row .bot.message / user 同构） */
.message-row.bubble.bot-row .bot.message {{
  background: {BUBBLE_AI} !important; color: {TEXT} !important;
  border-radius: 12px !important;
  border: 1px solid rgba(200, 75, 49, 0.18) !important;
  box-shadow: none !important;
}}
.message-row.bubble.user-row .user.message {{
  background: {BUBBLE_USER} !important; color: {TEXT} !important;
  border-radius: 12px !important;
  border: 1px solid rgba(200, 75, 49, 0.25) !important;
}}
/* 对话标题 & 顶部按钮图标：暖深棕，避免暗色观感 */
.wrapper:has(.bubble-wrap) label {{
  color: {TEXT} !important;
}}
/* Chatbot 顶栏图标按钮（分享/清空/复制）：深色模式下 --block-background-fill 是近黑 rgb(41,37,36)
   → 强制暖色底 + 深棕图标，深浅色通用 */
.wrapper:has(.bubble-wrap) .icon-button-wrapper {{
  background: #E8A878 !important;
}}
.wrapper:has(.bubble-wrap) .icon-button {{
  background: #E8A878 !important;
  --bg-color: #E8A878 !important;
}}
.wrapper:has(.bubble-wrap) .icon-button svg {{
  color: {TEXT} !important;
}}
/* 旧选择器兜底（部分 Gradio 版本仍用 .gr-chatbot） */
.gr-chatbot .message.user {{
  background: {BUBBLE_USER} !important; color: {TEXT} !important;
  border-radius: 12px !important;
}}
.gr-chatbot .message.bot {{
  background: {BUBBLE_AI} !important; color: {TEXT} !important;
  border-radius: 12px !important;
}}

/* ---- 统一组件深暖背景（覆盖 gradio 默认白底） ---- */
.gradio-container label, .gradio-container .block, .gradio-container .form {{
  background: transparent !important;
}}
.gradio-container select {{
  background: {PANEL} !important;
  color: {TEXT_DARK} !important;
  border: 1px solid {COCKPIT_BORDER} !important;
  border-radius: 10px !important;
  padding: 8px 12px !important;
}}
.gradio-container option {{ background: {PANEL} !important; color: {TEXT_DARK} !important; }}
.gradio-container textarea, .gradio-container input[type="text"] {{
  background: {PANEL} !important;
  color: {TEXT} !important;                /* 深棕文字：亮字(TEXT_DARK)在暖底上看不清 */
  caret-color: {TEXT} !important;
  border: 1px solid {COCKPIT_BORDER} !important;
  border-radius: 10px !important;
}}
.gradio-container textarea::placeholder, .gradio-container input[type="text"]::placeholder {{
  color: rgba(74, 44, 26, 0.55) !important;   /* 半透明深棕 placeholder */
}}
.gradio-container textarea:focus, .gradio-container input[type="text"]:focus {{
  border-color: {MAPLE_GOLD} !important;
  box-shadow: 0 0 0 2px rgba(224, 160, 60, 0.2) !important;
}}
.gradio-container label span {{
  color: {TEXT} !important;
}}
.gradio-container .prose, .gradio-container .markdown,
.gradio-container .prose :is(p, h1, h2, h3, h4, ul, ol, li, strong, em, span, blockquote, code) {{
  background: transparent !important;
  color: {TEXT} !important;
}}
/* Markdown 里的链接：深棕描边可点，但颜色保持可读（深色模式 Gradio 会置白） */
.gradio-container .prose a {{
  color: {MAPLE_RED} !important;
  font-weight: 600 !important;
  text-decoration: underline !important;
}}
.gradio-container .prose blockquote {{
  background: {BG_DEEP} !important;
  color: {TEXT} !important;
  border-left: 4px solid {MAPLE_RED} !important;
  border-radius: 8px;
  padding: 10px 14px !important;
}}

/* ---- 地区选择器横幅背景 ---- */
/* 地区选择器：压缩横幅背景 + 无边框 + 清晰文字 */
/* gradio .block 边框由 CSS 变量控制 → 用变量归零最有效 */
.region-dd {{
  --block-border-width: 0 !important;
  --block-border-color: transparent !important;
  --block-shadow: none !important;
  background-image: url('{REGION_BANNER_B64}') !important;
  background-size: cover !important;
  background-position: center !important;
  border-radius: 12px !important;
  padding: 8px 12px !important;
  margin-bottom: 8px !important;
  border: 0 none !important;
  border-width: 0 !important;
  border-style: none !important;
  border-color: transparent !important;
  outline: none !important;
  box-shadow: none !important;
}}
/* info 文字：原 Gradio 灰(#a8a29e)看不清 → 加粗深棕 + 浅色描影 */
.region-dd .info-text {{
  color: {TEXT} !important;
  font-weight: 700 !important;
  font-size: 12.5px !important;
  text-shadow: 0 0 3px rgba(252, 231, 210, 0.95), 0 0 8px rgba(252, 231, 210, 0.8);
}}
/* container=False 把 label 变成 sr-only 视觉隐藏 → 恢复显示为标题 */
.region-dd span[data-testid="block-info"] {{
  position: static !important;
  width: auto !important;
  height: auto !important;
  clip: auto !important;
  clip-path: none !important;
  margin: 0 0 4px !important;
  padding: 0 !important;
  overflow: visible !important;
  display: block !important;
  color: {TEXT} !important;
  font-weight: 700 !important;
  font-size: 14px !important;
}}
/* 下拉字段：Gradio 灰白 #F5F5F4 → 暖面板色（Gradio 6 是 input+div.wrap，非原生 select） */
.region-dd .wrap, .region-dd .wrap-inner, .region-dd .secondary-wrap {{
  background: rgba(252, 231, 210, 0.92) !important;
  border: none !important;
}}
.region-dd input[role="listbox"] {{
  background: transparent !important;
  color: {TEXT} !important;
  font-weight: 600 !important;
  border: none !important;
}}
/* 选项弹层：白底 → 暖面板 */
.region-dd .options {{
  background: {PANEL} !important;
  border: 1px solid {COCKPIT_BORDER} !important;
  border-radius: 10px !important;
  box-shadow: 0 6px 20px rgba(0,0,0,0.15) !important;
}}
.region-dd .options .item {{
  color: {TEXT} !important;
}}
.region-dd .options .item.selected,
.region-dd .options .item.active,
.region-dd .options .item:hover {{
  background: {PANEL_LIGHT} !important;
  color: {TEXT} !important;
}}

/* ---- Tab 标签（深暖）---- Gradio 6 真实结构是 [role="tab"]，非旧 .tab-nav */
.gradio-container [role="tab"] {{
  background: transparent !important;
  color: {TEXT} !important;               /* 深棕，深色模式下默认白字看不清 */
  font-weight: 600 !important;
  border-radius: 10px 10px 0 0 !important;
  border: none !important;
}}
.gradio-container [role="tab"]:hover {{
  background: {PANEL} !important; color: {TEXT} !important;
}}
.gradio-container [role="tab"].selected {{
  background: {PANEL} !important;
  color: {MAPLE_RED} !important;
  font-weight: 700 !important;
  border-bottom: 3px solid {MAPLE_GOLD} !important;
}}
/* Tab 内容容器 */
.gradio-container .tabitem {{
  background: {BG_DEEP} !important;
  border-radius: 0 14px 14px 14px !important;
  padding: 16px !important;
  border: 1px solid {COCKPIT_BORDER} !important;
}}

/* 卡片 & 按钮区背景（深暖） */
.card {{ background: {BG_DEEP} !important; border: 1px solid {COCKPIT_BORDER} !important; border-radius: 14px; padding: 14px 16px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.2); }}

/* 隐藏 Gradio 底部导航（通过 API 使用 / 使用 Gradio 构建 / 设置） */
.gradio-container footer, .gradio-container > footer,
footer[aria-label="Gradio footer navigation"] {{
  display: none !important;
}}
"""

# ---------------------------------------------------------------- 主题选择
# UI_THEME=high_contrast → 高对比投影版（主版完整布局 + 纯白黑字蓝覆盖）
# 否则默认暖橙主版。两个主题共用同一份布局 CSS，高对比只叠加颜色覆盖 → 布局不崩。
import os as _os
USE_HC = _os.getenv("UI_THEME", "") == "high_contrast"
HC_CSS = CSS + HC_OVERLAY


# ---------------------------------------------------------------- 驾驶舱渲染
def _status_class(level: str) -> str:
    return {"低": "risk-low", "中": "risk-mid", "高": "risk-high"}.get(level, "risk-mid")


def render_cockpit(profile: dict, region: str, indices: dict | None = None,
                   summ: dict | None = None, partial: bool = False) -> str:
    """渲染驾驶舱 HTML。partial=True 表示材料预审采集过程中。"""
    info = region_info(region)
    region_label = info.get("name", region)
    status_txt = info.get("data_status", "")
    status_cls = "status-ok" if "真实" in status_txt else "status-demo"

    head = (f"📊 经营驾驶舱 · {region_label}"
            f" <span class='{status_cls}' style='font-size:11px'>（{status_txt}）</span>")

    if partial or indices is None:
        filled = sum(1 for k, v in profile.items()
                     if not k.startswith("_") and v not in (None, "", [], {}))
        total = len(bp.FIELD_KEYS)
        pct = round(filled / total * 100)
        return f"""
        <div class="cockpit">
          <div class="cockpit-head">{head}</div>
          <div class="metric-label">经营信息采集进度</div>
          <div class="bar"><div class="bar-fill" style="width:{pct}%">{pct}%</div></div>
          <div class="progress">已收集 {filled}/{total} 项 · 继续回答 AI 的问题即可</div>
          <div class="metric-label">已识别字段</div>
          <div class="material">{bp.summarize(profile) or '—'}</div>
          <div class="cockpit-footer">🛡️ 辅助参考 · 不替代专业机构 · 来源可溯源</div>
        </div>"""

    risk = indices["risk"]
    checklist = summ["checklist"] if summ else []
    missing = [m for m in checklist if m["status"] == "缺失"]
    pending = [m for m in checklist if m["status"] == "待确认"]
    auto = [m for m in checklist if m["status"] == "自动"]
    todo = len(missing)
    health = indices["health"]

    mat_html = ""
    for m in (missing + pending)[:6]:
        if m["status"] == "缺失":
            mat_html += f'<div class="material"><span class="warn">⚠️ {m["name"]}</span></div>'
        else:
            mat_html += f'<div class="material"><span class="warn">⏳ {m["name"]}</span></div>'
    shown = len((missing + pending)[:6])
    total = len(checklist)
    if auto:
        mat_html += f'<div class="material"><span class="ok">✅ 自动享受 {len(auto)} 项（系统直享，无需材料）</span></div>'
    if shown + len(auto) < total:
        mat_html += f'<div class="progress">还有 {total - shown - len(auto)} 项 · 共 {total} 项</div>'
    if not missing and not pending and not auto:
        mat_html = '<div class="material"><span class="ok">✅ 材料齐全</span></div>'

    rate = summ["match_rate"] if summ else 0
    recs = build_recommendations(profile, indices)
    rec_html = "".join(f"<li>{r}</li>" for r in recs[:3])

    return f"""
    <div class="cockpit">
      <div class="cockpit-head">{head}</div>
      <div class="metric-label">经营健康度</div>
      <div class="bar"><div class="bar-fill" style="width:{health}%">{health}%</div></div>
      <div class="cockpit-row">
        <div class="metric"><div class="lab">政策机会</div><div class="big gold">{indices['policy_opportunity']}</div></div>
        <div class="metric"><div class="lab">风险等级</div><div class="big {_status_class(risk['level'])}">{risk['level']}</div></div>
        <div class="metric"><div class="lab">待办</div><div class="big">{todo}</div></div>
      </div>
      <div class="section-title">缺失材料</div>
      {mat_html}
      <div class="metric-label">政策匹配度 {rate}%</div>
      <div class="bar"><div class="bar-fill gold" style="width:{rate}%"></div></div>
      <div class="section-title">行动建议</div>
      <ol style="margin:4px 0 0;padding-left:18px;font-size:12.5px;line-height:1.7;">{rec_html}</ol>
      <div class="cockpit-footer">🛡️ 辅助参考 · 不替代专业机构 · 来源可溯源</div>
    </div>"""


# ---------------------------------------------------------------- 文本渲染
def render_report(profile: dict, summ: dict, indices: dict, title: str = "预审结果", real_search: bool = False) -> str:
    """诊断完成后的报告文本（对话流里展示）。

    real_search=True 表示已有实时搜索结果（单独区块展示），不再重复渲染通用方向库。
    """
    lines = []
    lines.append(f"📋 **{title}**")
    matched = summ["matched_policies"]
    # 区分：国家级自动享受（无需操作） vs 地区差异化可申请（需要你去做）
    local_matched = [p for p in matched if p.get("region") != "national"]
    national_matched = [p for p in matched if p.get("region") == "national"]
    if local_matched:
        lines.append(f"✅ 你符合 **{len(local_matched)} 项地区政策**可申请：")
        for p in local_matched[:4]:
            lines.append(f"- **{p['name']}**（{p['amount']}）\n  · 条件：{'；'.join(p['eligibility'][:2])}\n  · 来源：{p['source']} [查看]({p['source_url']})")
        if len(local_matched) > 4:
            lines.append(f"  …还有 {len(local_matched)-4} 项")
        # 顾问式解读（P5：激活 EXPLAIN_PROMPT，LLM 有 key 时对 top 政策生成；失败静默降级为纯规则列表）
        if api_client.is_api_available():
            try:
                top = local_matched[0]
                sys_p = agent_prompts.EXPLAIN_PROMPT.format(
                    policy_name=top["name"],
                    amount=top.get("amount", ""),
                    eligibility="；".join(top.get("eligibility", [])[:3]),
                    materials="、".join(m.get("name", "") for m in top.get("materials", [])[:3]) or "以官方清单为准",
                    source=top.get("source", ""),
                    source_url=top.get("source_url", ""),
                    key_point=top.get("key_point", ""))
                raw, _ = api_client.generate(sys_p, "", temperature=0.4, max_tokens=300)
                txt = (raw or "").strip()
                if txt:
                    lines.append(f"\n🤖 **顾问解读**（{top['name']}）：\n{txt}")
            except Exception:
                pass  # LLM 失败 → 保持纯规则列表，不阻塞报告
    elif summ.get("region_status", "").startswith("通用参考") and not real_search:
        # 未收录地区且实时搜索失败 → 展示通用政策方向（零造假：标注需核验，不算可申请）
        lines.append("📌 实时搜索暂不可用，为你列出**常见政策方向**（具体以当地官方为准）：")
        for p in general.POLICIES[:6]:
            lines.append(f"- **{p['name']}**（{p['amount']}）")
        lines.append("\n> 这些是通用参考，**不代表当地一定有/金额一致**。用 ④政策导入 粘贴当地真实政策原文，可自动入库匹配。")
    else:
        lines.append("当前无直接可申请的地区政策（部分资格待确认，可继续补充信息）。")
    if national_matched:
        lines.append(f"\n🎯 **另 {len(national_matched)} 项全国通用政策自动享受**（无需申请）：")
        lines.append("  " + "、".join(p["name"] for p in national_matched))

    missing = [m for m in summ["checklist"] if m["status"] == "缺失"]
    pending = [m for m in summ["checklist"] if m["status"] == "待确认"]
    if missing or pending:
        # 修复（S4）：缺失与待确认都需提示，不能只统计"缺失"——否则用户未确认材料时会误报"材料完整"
        lines.append(f"\n⚠️ **建议准备/确认材料**（缺 {len(missing)} 项 · 待确认 {len(pending)} 项）：")
        for m in (missing + pending)[:5]:
            if m["status"] == "缺失":
                lines.append(f"- {m['name']}" + (f"（{m['format_note']}）" if m.get("format_note") else ""))
            else:
                lines.append(f"- {m['name']}（待确认是否已备）")
        if len(missing) + len(pending) > 5:
            lines.append(f"  …共 {len(missing) + len(pending)} 项")
    else:
        lines.append("\n✅ 材料清单完整。")

    risk = indices["risk"]
    if risk["risks"]:
        lines.append(f"\n🔍 **风险提示（等级：{risk['level']}）**")
        for r in risk["risks"][:3]:
            lines.append(f"- {r['desc']} → {r['advice']}")

    lines.append("\n🛡️ 以上为辅助参考，不替代专业机构/金融机构最终判断，政策以官方最新文件为准。")
    return "\n".join(lines)


# ---------------------------------------------------------------- 材料预审状态机
_REGION_CODE_BY_LABEL = {v: k for k, v in REGION_LABELS.items()}


def _region_code(name_or_code: str) -> str:
    """把地区名/下拉值转成下拉可用值（label→code；未收录地区保留原名自定义）。"""
    if name_or_code in REGION_LABELS:
        return name_or_code
    return _REGION_CODE_BY_LABEL.get(name_or_code, name_or_code)


def _looks_like_off_topic(text: str) -> bool:
    """判断回答是否明显跑题（跳过/不知道），此时不应把原文硬塞进字段。"""
    return any(k in text for k in ("不知道", "不清楚", "跳过", "下一个", "随便", "换一个"))


# ---------------------------------------------------------------- 涉法红线拦截（合规硬约束）
# 命中即红牌拒绝：绝不把造假/虚报/偷逃税意图带进政策匹配流程。
_LEGAL_REDLINE = [
    "骗补", "造假", "虚报", "隐瞒", "伪造", "做假账", "假账", "洗钱", "贿赂",
    "避税", "偷税", "逃税", "漏税", "虚开", "冒用", "冒充", "伪造公章", "套用他人",
    "补办个假的", "办个假的", "假的毕业证", "假材料", "假发票",
]

_REDLINE_REPLY = (
    "🚫 **已停止**：你提到的情况可能涉及虚报/造假/偷逃税，这属于违法违规行为，"
    "我不能协助。\n\n如果你需要的是合法经营建议，可以继续描述你的真实经营情况，"
    "我会帮你梳理合规的补贴申请路径。"
)


def _has_redline(text: str) -> bool:
    """检测是否命中涉法红线。返回 True 表示应拒绝。"""
    t = (text or "").strip()
    return any(k in t for k in _LEGAL_REDLINE)


# ---------------------------------------------------------------- 政策原文有效性（防乱码污染）
def _looks_like_policy(text: str) -> bool:
    """政策原文至少含一个政策要素，否则拒绝入库（防乱码/随手粘贴污染政策库）。"""
    return any(k in text for k in ("补贴", "优惠", "减免", "资助", "奖励", "支持",
                                   "申请", "条件", "万元", "元/", "元。", "毕业生",
                                   "企业", "就业", "创业", "认定", "申报"))


def llm_extract_profile(user_text: str, profile: dict) -> dict:
    """LLM 理解用户自然语言 → 抽取经营字段（不穷举，模型理解任意表达）。

    架构：LLM 优先理解，规则仅无 key 兜底。有 MODELSCOPE_API_KEY 时，
    用户说"我做直播带货的"由模型理解输出 industry=直播带货，而非正则穷举。
    失败静默返回空 dict，由规则兜底。
    """
    if not api_client.is_api_available():
        return {}
    try:
        sys_p = agent_prompts.EXTRACT_PROMPT.format(user_text=user_text)
        user_p = f"当前已收集的经营信息：{bp.to_llm_context(profile)}。只抽取本次新增的字段。"
        raw, _ = api_client.generate(sys_p, user_p, temperature=0.2, max_tokens=800)
        parsed = bp.parse_llm_json(raw)
        # 过滤：只保留不在 profile 里的新增字段（LLM 理解更准，覆盖规则结果）
        return {k: v for k, v in parsed.items() if v and not profile.get(k)}
    except Exception:
        return {}


def process_chat(user_text: str, profile: dict, chat: list, region: str):
    """材料预审：用户输入 → 抽取字段 → 追问 or 出报告。

    地区以「用户消息里明确说的城市」优先，否则用下拉值；并同步下拉。
    追问时若用户回答当前字段但关键词没抽到 → yes/no 枚举兜底，保证进度前进。
    """
    chat = chat or []
    user_text = (user_text or "").strip()
    if not user_text:
        return "", profile, region, chat, render_cockpit(profile, region, partial=True), ""
    chat.append({"role": "user", "content": user_text})

    # 涉法红线拦截：命中立即拒绝，绝不带进匹配流程（合规硬约束）
    if _has_redline(user_text):
        chat.append({"role": "assistant", "content": _REDLINE_REPLY})
        region_out = _region_code(profile.get("region") or region)
        return ("", profile, region_out, chat,
                render_cockpit(profile, region_out, partial=True), "⛔ 已拦截")

    # ---- 抽取：LLM 优先理解（有 key），规则兜底（无 key / LLM 失败）----
    extracted = {}
    # ① LLM 理解：模型从自然语言抽取任意字段（行业/地区/注册类型等，不穷举）
    llm_ext = llm_extract_profile(user_text, profile)
    if llm_ext:
        extracted.update(llm_ext)
    # ② 规则兜底：LLM 没抽到的字段用句法模式/数字规则补充（零值枚举，不预置城市/行业表）
    rule_ext = bp.extract_from_text(user_text, profile)
    for k, v in rule_ext.items():
        if v and k not in extracted:
            extracted[k] = v
    # ③ 追问兜底：用户回答当前被问字段但都没抽到 → 尽力识别，保证进度前进
    missing = bp.pending_ask(profile)
    if missing and missing[0]["key"] not in extracted and not profile.get(missing[0]["key"]):
        q_key = missing[0]["key"]
        if q_key in ("social_security", "corp_account", "biz_scope_ai"):
            v = bp.parse_yes_no(user_text)
            if v:
                extracted[q_key] = v
        elif q_key in ("revenue", "duration", "cash_buffer", "order_cycle", "team_size", "grad_year"):
            v = bp.extract_loose_number(user_text, q_key)
            if v:
                extracted[q_key] = v
        else:
            # 自由文本字段：仅当回答简短、非跑题、且没提供其他字段信息时，直接记录原文
            other_fields = [k for k in extracted if k != q_key]
            if len(user_text) <= 40 and not _looks_like_off_topic(user_text) and not other_fields:
                extracted[q_key] = user_text

    new_keys = [k for k, v in extracted.items() if v and not profile.get(k)]
    profile.update(extracted)
    if new_keys:
        chat.append({"role": "assistant",
                     "content": f"✅ 已记录：{'、'.join(bp_summarize_key(k, v) for k, v in extracted.items() if k in new_keys)}"})

    # 地区：用户消息里明确说的城市 > 已有值 > 下拉当前值（兜底）
    # 注意：extract 对已填字段不返回，所以"用户消息已说城市"= extracted['region'] 命中。
    # 兜底只用下拉 code 转换中文，绝不覆盖用户已说的城市。
    if extracted.get("region"):
        profile["region"] = extracted["region"]
    elif not profile.get("region"):
        # 下拉值兜底（用户改了地区下拉/输入了自定义地区，且尚无地区）
        dd_region = REGION_LABELS.get(region, region) if region else ""
        if dd_region:
            profile["region"] = dd_region
    region_out = _region_code(profile["region"])
    region_val = profile["region"]

    if not bp.is_ask_complete(profile):
        # ---- 追问防死循环：同字段问满 3 次自动跳过；全部跳过则进诊断 ----
        # 追问源 = 必填缺失 + 关键非必填（grad_year/team_size，决定政策匹配，P4 修复）
        prof_ask = dict(profile.get("_ask_count", {}))
        prof_skip = set(profile.get("_skip_fields", []))
        # 本轮抽到新字段 → 正常交流，重置所有计数（防止"用户答别的字段"误触发跳过）
        if new_keys:
            prof_ask = {k: 0 for k in prof_ask}
        # 找一个"未跳过 3 次"的缺失字段来问
        target_key = None
        for f in bp.pending_ask(profile):
            if f["key"] not in prof_skip:
                target_key = f["key"]
                break
        if target_key is not None:
            prof_ask[target_key] = prof_ask.get(target_key, 0) + 1
            if prof_ask[target_key] >= 3:
                # 问满 3 次仍无进展 → 标记跳过，本轮先提示再问下一个
                prof_skip.add(target_key)
                prof_ask.pop(target_key, None)
                chat.append({"role": "assistant",
                             "content": f"▶️ 这个信息可以先跳过（已问多次未获有效回答），继续下一个问题。"})
                # 重新找下一个未跳过的字段
                target_key = None
                for f in bp.pending_ask(profile):
                    if f["key"] not in prof_skip:
                        target_key = f["key"]
                        break
        if target_key is not None:
            q = next(f["ask"] for f in bp.FIELDS if f["key"] == target_key)
            question = polish_question(q, profile) if api_client.is_api_available() else q
            chat.append({"role": "assistant", "content": f"🤔 {question}"})
        else:
            # 必填字段全部被跳过 → 不无限追问，直接出部分结果
            chat.append({"role": "assistant",
                         "content": "已收集到能收集的信息，为你生成当前可判断的结果…"})
            profile["_pending_complete"] = True
        profile["_ask_count"] = prof_ask
        profile["_skip_fields"] = sorted(prof_skip)
        cockpit = render_cockpit(profile, region_out, partial=True)
        filled = sum(1 for k, v in profile.items()
                     if not k.startswith("_") and v not in (None, "", [], {}))
        status = f"⏳ 已收集 {filled}/{len(bp.FIELD_KEYS)} 项 · 回答上方的 AI 问题继续"
        return "", profile, region_out, chat, cockpit, status

    # 完整 → 匹配 + 诊断（一律用 region code 匹配政策库，profile['region'] 仅中文展示用）
    summ = summary(profile, region_out)
    indices = compute_indices(profile, region_out)
    is_unknown = summ.get("region_status", "").startswith("通用参考")

    # 未收录地区 → 实时搜索当地政策（核心：搜索词=LLM理解行业生成，非类目穷举）；失败给显式降级提示
    search_block = ""
    if is_unknown:
        # 有 key 时 LLM 生成精准搜索词（理解任意行业）；无 key 用用户原话行业兜底
        llm_gen = (lambda s, u: api_client.generate(s, u, temperature=0.3, max_tokens=120)) \
            if api_client.is_api_available() else None
        keyword = policy_searcher.generate_query(region_val, profile, llm_gen)
        search_block = policy_searcher.search_and_format(region_val, keyword=keyword)
        if not search_block:
            # 网络受限/搜索失败：不哑火，明确告知评委是环境限制，并引导本地通用库
            search_block = policy_searcher.unavailable_notice(region_val)
        # LLM 增强：有 key 时基于搜索结果整理更精准的方向（可叠加）
        if api_client.is_api_available():
            llm_pol = lookup_local_policies(region_val, profile)
            if llm_pol:
                search_block += "\n" + llm_pol

    report = render_report(profile, summ, indices, real_search=bool(search_block))
    if search_block:
        report += search_block
    chat.append({"role": "assistant", "content": report})
    cockpit = render_cockpit(profile, region_out, indices, summ, partial=False)
    status = "✅ 预审完成 · 可切换地区或修改信息重新诊断"
    return "", profile, region_out, chat, cockpit, status


def bp_summarize_key(k: str, v: str) -> str:
    label = next((f["label"] for f in bp.FIELDS if f["key"] == k), k)
    return f"{label}={v}"


def polish_question(question: str, profile: dict) -> str:
    """用 LLM 把规则问题说成人话；失败回退规则问题。"""
    try:
        profile_sum = bp.to_llm_context(profile)
        sys_p = agent_prompts.Q_A_PROMPT.format(
            profile_summary=profile_sum, field_label="", question=question)
        content, _ = api_client.chat(
            [{"role": "system", "content": sys_p},
             {"role": "user", "content": f"请把这个问题说得更口语化：{question}"}],
            max_tokens=120)
        content = content.strip().split("\n")[0].strip()
        if 4 < len(content) < 60:
            return content
    except Exception:
        pass
    return question


# ---------------------------------------------------------------- 经营诊断
def run_diagnosis(profile_inputs: dict, region: str):
    """经营诊断：填表 → 三指数 + 驾驶舱 + 报告。"""
    profile = bp.empty_profile()
    profile.update({k: (v or "").strip() for k, v in profile_inputs.items() if v})
    if region:
        # code（wenzhou/guangzhou…）→ 中文展示名；自定义中文（福建/广州…）直接用
        profile["region"] = REGION_LABELS.get(region, region)

    missing = bp.missing_fields(profile)
    if missing:
        first = ", ".join(f["label"] for f in missing[:3])
        return (render_cockpit(profile, region, partial=True),
                f"⚠️ 还缺：{first}（共 {len(missing)} 项），请补充后重试")
    summ = summary(profile, region)
    indices = compute_indices(profile, region)
    cockpit = render_cockpit(profile, region, indices, summ, partial=False)

    # 未收录地区 → 实时搜索当地政策（与 Tab1 一致，搜索词=LLM/原话行业）；失败给显式降级提示
    search_block = ""
    if summ.get("region_status", "").startswith("通用参考"):
        # code（wenzhou/guangzhou…）→ 中文名；自定义输入（福建/广州…）直接用中文
        region_name = REGION_LABELS.get(region) or profile.get("region") or region
        llm_gen = (lambda s, u: api_client.generate(s, u, temperature=0.3, max_tokens=120)) \
            if api_client.is_api_available() else None
        keyword = policy_searcher.generate_query(region_name, profile, llm_gen)
        search_block = policy_searcher.search_and_format(region_name, keyword=keyword)
        if not search_block:
            search_block = policy_searcher.unavailable_notice(region_name)

    report = render_report(profile, summ, indices, title="诊断结果", real_search=bool(search_block))
    if search_block:
        report += search_block
    return cockpit, report


# ---------------------------------------------------------------- 合规问答
COMPLIANCE_MOCK = {
    "小微": "小型微利企业年应纳税所得额不超过 300 万元，实际税负约 5%，季度申报时系统自动享受，无需单独备案。辅助参考，以税务部门最新口径为准。",
    "报税": "一人公司/个体户报税注意：①小规模纳税人月销售额 10 万以下（季度 30 万）免征增值税；②小型微利企业实际税负约 5%；③补贴收入通常不征企业所得税，但以当地税务口径为准；④建议从 Day 1 记清收入/成本/研发支出，避免年底补账。辅助参考，以税务部门最新口径为准。",
    "增值税": "月销售额 10 万以下（按季 30 万）的小规模纳税人免征增值税，申报时系统自动判断。辅助参考，以官方公告为准。",
    "社保": "一人公司/个体户可缴灵活就业社保，多项温州创业补贴要求缴纳社保（如创业带动就业补贴、人才租房补贴），建议尽早开通。辅助参考。",
    "加计": "研发费用可在税前加计扣除，需建立研发费用辅助账。对单人软件公司，大模型 API 费用可计入研发投入。辅助参考，以税务申报要求为准。",
    "双软": "软件企业两免三减半需通过双软认定（软件产品登记 + 软件企业认定），建议找代理机构办理（¥3,000-8,000 一次性）。辅助参考。",
}


def compliance_chat(message, history):
    history = history or []
    history.append({"role": "user", "content": message})

    # 涉法红线拦截（合规硬约束，LLM 之前先拦）
    if _has_redline(message):
        history.append({"role": "assistant", "content": _REDLINE_REPLY})
        return history, ""

    # 实时联网搜索（免费，独立于 LLM；失败静默）
    web_block = policy_searcher.format_web_search(message)

    if api_client.is_api_available():
        try:
            msgs = [{"role": "system", "content": agent_prompts.COMPLIANCE_PROMPT.format(
                question=message, knowledge=agent_prompts.COMPLIANCE_KNOWLEDGE)}]
            msgs += [{"role": h["role"], "content": h["content"]} for h in history[-6:]]
            answer, _ = api_client.chat(msgs, temperature=0.5, max_tokens=800)
            answer = answer.strip()
            if web_block:
                answer += "\n\n" + web_block
            else:
                answer += "\n\n" + policy_searcher.format_unavailable(message)
            history.append({"role": "assistant", "content": answer})
            return history, ""
        except Exception:
            pass
    # mock 兜底
    answer = "「枫独」目前以离线知识库作答（未配置 LLM API）：\n\n"
    hit = next((v for k, v in COMPLIANCE_MOCK.items() if k in message), None)
    answer += hit or "这个问题涉及专业判断，建议咨询当地税务/法务专业人员。"
    answer += "\n\n🛡️ 辅助参考，不替代专业机构判断。"
    if web_block:
        answer += "\n\n" + web_block
    history.append({"role": "assistant", "content": answer})
    return history, ""


# ---------------------------------------------------------------- 政策导入
def import_policy(region: str, policy_text: str):
    """政策导入：粘贴原文 → LLM 结构化 → 追加到 policies/<region>.py。"""
    policy_text = (policy_text or "").strip()
    if not policy_text:
        return "请先粘贴政策原文。"
    if not _looks_like_policy(policy_text):
        return ("⚠️ **未能识别为政策原文**：请粘贴包含政策名称、金额、资格条件的完整政策文本"
                "（如政府公告原文）。已拒绝入库，防止错误数据污染政策库。")
    if api_client.is_api_available():
        try:
            sys_p = agent_prompts.POLICY_IMPORT_PROMPT.format(region=region, policy_text=policy_text)
            raw, model = api_client.generate(sys_p, "", temperature=0.2, max_tokens=2500)
            parsed = _parse_import_json(raw)
            if parsed:
                n = _write_policies_file(region, parsed)
                return (f"✅ 已入库 **{n} 条**政策（AI 结构化）\n\n"
                        f"地区「{region}」政策库已更新，可在驾驶舱下拉选择后重新匹配。\n\n"
                        f"⚠️ 请人工核对入库内容与原文一致——AI 结构化可能出错，以官方文件为准。")
            # AI 失败 → 回退规则解析
            parsed = _parse_policy_rules(policy_text)
            if parsed:
                n = _write_policies_file(region, parsed)
                return (f"✅ 已入库 **{n} 条**政策（规则解析）\n\n"
                        f"地区「{region}」政策库已更新。\n\n"
                        f"⚠️ 规则解析识别有限，请人工核对入库内容与官方原文一致。")
            return "⚠️ 无法解析政策结构，请检查原文格式或稍后重试。"
        except Exception as e:
            return f"⚠️ 导入失败：{e}，请稍后重试。"
    # 离线 → 规则解析（零 LLM 依赖也能导入）
    parsed = _parse_policy_rules(policy_text)
    if parsed:
        n = _write_policies_file(region, parsed)
        return (f"✅ 已入库 **{n} 条**政策（离线规则解析）\n\n"
                f"地区「{region}」政策库已更新，可在驾驶舱下拉选择后重新匹配。\n\n"
                f"⚠️ 规则解析识别有限，请人工核对入库内容与官方原文一致。")
    return "⚠️ 未能识别政策结构，请检查原文格式后重试。"


def _parse_import_json(raw: str) -> list[dict]:
    import json, re
    text = re.sub(r"```(?:json)?", "", raw).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    policies = data.get("policies", []) if isinstance(data, dict) else []
    out = []
    for p in policies:
        if isinstance(p, dict) and p.get("name"):
            out.append({
                "name": str(p.get("name", "")).strip(),
                "region": "",
                "category": p.get("category", "其他"),
                "amount": str(p.get("amount", "以官方文件为准")),
                "eligibility": p.get("eligibility") or [],
                "materials": p.get("materials") or [],
                "source": str(p.get("source", "")),
                "source_url": str(p.get("source_url", "")),
                "difficulty": p.get("difficulty", "待评估"),
                "timing": str(p.get("timing", "")),
                "key_point": str(p.get("key_point", "")),
                "update_date": "2026-08",
            })
    return out


def _parse_json_array(raw: str) -> list[dict]:
    """解析 LLM 输出的 JSON 数组（可能是纯数组或包在 markdown 代码块里）。"""
    import json, re
    text = re.sub(r"```(?:json)?", "", raw).strip()
    # 优先找数组
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, dict) and p.get("name")]


def lookup_local_policies(region: str, profile: dict) -> str:
    """LLM 生成当地政策方向（仅未收录地区 + 有 key 时）。失败返回空串。"""
    try:
        sys_p = agent_prompts.POLICY_LOOKUP_PROMPT.format(region=region,
                                                           profile_summary=bp.to_llm_context(profile))
        raw, model = api_client.generate(sys_p, "", temperature=0.4, max_tokens=2000)
        items = _parse_json_array(raw)
        if not items:
            return ""
        lines = [f"\n🤖 **AI 按「{region}」检索的政策方向**（{model}，仅供参考，需以当地官方为准）："]
        for p in items[:6]:
            lines.append(f"- **{p['name']}**（{p.get('amount', '以当地官方为准')}）\n  · {p.get('key_point', '')[:40]}")
        lines.append("\n> 以上为 AI 依据公开知识整理的**政策方向**，不代表当地一定有/金额一致，请以官方最新文件为准。")
        return "\n".join(lines)
    except Exception:
        return ""


def _parse_policy_rules(text: str) -> list[dict]:
    """规则引擎版政策解析（零 LLM 依赖）：从政策原文抽取结构化字段。

    离线也能用——抽取名称/金额/资格条件/材料/来源，供 ④政策导入 兜底。
    识别范围有限，抽不全的字段留默认 + 标注需人工核对。
    """
    text = (text or "").strip()
    if not text:
        return []

    # 名称：优先取第一行或含"补贴/资助/优惠/减免/支持/奖励"的行
    name = ""
    for line in text.splitlines():
        line = line.strip()
        if line and any(k in line for k in ("补贴", "资助", "优惠", "减免", "支持", "奖励", "创业")):
            name = line[:50]
            break
    if not name:
        # 取第一行
        first = next((l for l in text.splitlines() if l.strip()), "")
        name = first[:50]

    # 金额
    amount = ""
    m = re.search(r"([¥￥]?\s*[\d,]+(?:\.\d+)?\s*(?:万元?|元)|最高[^。；；\n]{0,12}?|每个?年[^。；；\n]{0,12}?)", text)
    if m:
        amount = m.group(1).strip()[:30]
    if not amount:
        m2 = re.search(r"([\d,]+\.?\d*\s*万元?|[\d,]+\.?\d*\s*元)", text)
        if m2:
            amount = m2.group(1).strip()[:30]
    if not amount:
        amount = "以官方文件为准"

    # 资格条件：找含"以下""条件""应具备""要求""须"的句子，或含数字/学历/年限的句子
    eligibility = []
    seen = set()
    for line in text.splitlines():
        line = line.strip().rstrip("。；;")
        if not line or len(line) > 80:
            continue
        if any(k in line for k in ("学历", "毕业", "年", "注册", "缴纳", "参保", "社保", "企业",
                                   "符合", "条件", "要求", "须", "需", "入驻", "缴纳", "经营")):
            key = line[:20]
            if key not in seen:
                seen.add(key)
                eligibility.append(line)
        if len(eligibility) >= 4:
            break
    if not eligibility:
        eligibility = ["以当地官方文件为准"]

    # 申请材料：找含"材料""身份证""营业执照""申请表"的行
    materials = []
    for line in text.splitlines():
        line = line.strip()
        for kw in ("身份证", "营业执照", "毕业证", "学历", "申请表", "材料", "社保", "证明", "合同", "发票", "照片"):
            if kw in line:
                materials.append({"name": line[:40], "required": True})
                break
        if len(materials) >= 6:
            break
    if not materials:
        materials = [{"name": "以当地官方要求为准", "required": True}]

    # 来源：找含"官网/平台/部门/局/中心"的行
    source = "以官方文件为准"
    for line in text.splitlines():
        line = line.strip()
        if any(k in line for k in ("人社局", "人社", "局", "平台", "中心", "官网", "政务", "委", "办")):
            source = line[:40]
            break

    return [{
        "name": name,
        "region": "",
        "category": "其他",
        "amount": amount,
        "eligibility": eligibility,
        "materials": materials,
        "source": source,
        "source_url": "",
        "difficulty": "待评估",
        "timing": "以当地官方为准",
        "key_point": "规则解析自动入库，请人工核对与官方原文一致",
        "update_date": "2026-08",
    }]


def _policy_name_ok(name: str) -> bool:
    """导入政策名校验：防测试垃圾/纯数字污染政策库。

    只拦明显垃圾（长度<4 / 纯数字 / 占位词），不拦真实政策名
    （如"人才驿站免费住宿"可能不含'补贴/创业'字样，但对 _looks_like_policy 而言是合法的）。
    """
    n = (name or "").strip()
    if len(n) < 4:
        return False
    if n.isdigit():
        return False
    if n in ("待补充", "以官方文件为准", "以当地官方为准", "待导入", "待核对"):
        return False
    return True


def _write_policies_file(region: str, policies: list[dict]) -> int:
    """把结构化政策写入 policies/<region>.py 并注册。

    防护（P3 修复）：新导入 + 读回的历史政策都经过 _policy_name_ok 过滤，
    杜绝 '11111' 这类测试垃圾再次入库。
    """
    import os

    code = _slug(region)
    # policies 包目录 = 本文件所在目录下 policies/
    pkg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policies")
    path = os.path.join(pkg_dir, f"{code}.py")
    # 若文件已存在，读回现有政策追加（同时过滤历史脏数据）
    existing = []
    if os.path.exists(path):
        try:
            import importlib
            mod = importlib.import_module(f"policies.{code}")
            existing = [p for p in getattr(mod, "POLICIES", []) if _policy_name_ok(p.get("name", ""))]
        except Exception:
            existing = []

    # 新导入同样过滤（LLM 结构化的 name 可能乱，规则解析可能抽到数字行）
    policies = [p for p in policies if _policy_name_ok(p.get("name", ""))]

    nxt_id = len(existing) + 1
    for i, p in enumerate(policies):
        p["id"] = f"IMP-{nxt_id + i}"
        p["region"] = code

    new_policies = existing + policies
    # 生成代码
    from datetime import datetime
    today = "2026-08"
    body_lines = [
        f'# -*- coding: utf-8 -*-',
        f'"""政策导入生成（{today}）—— 来源：用户粘贴原文 + LLM 结构化，请人工核对。"""',
        "",
        'REGION = {',
        f'    "name": "{region}",',
        f'    "code": "{code}",',
        f'    "data_status": "导入数据·待核对",',
        f'    "update_date": "{today}",',
        '    "note": "由政策导入功能生成，请核对与官方文件一致",',
        '}',
        "",
        "POLICIES = [",
    ]
    for p in new_policies:
        body_lines.append("    {")
        for k in ["id", "name", "region", "category", "amount", "source", "source_url",
                  "difficulty", "timing", "key_point", "update_date"]:
            body_lines.append(f'        "{k}": {_py_str(p.get(k, ""))},')
        body_lines.append('        "eligibility": ' + repr(p.get("eligibility", [])) + ",")
        body_lines.append('        "materials": ' + repr(p.get("materials", [])) + ",")
        body_lines.append("    },")
    body_lines.append("]")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body_lines))

    # 注册到 REGIONS
    _register_region(code, region)
    return len(policies)


def _py_str(s) -> str:
    return repr(str(s).replace("'", "\\'"))


_CITY_PINYIN = {
    "温州": "wenzhou", "杭州": "hangzhou", "北京": "beijing", "上海": "shanghai",
    "广州": "guangzhou", "深圳": "shenzhen", "厦门": "xiamen", "福州": "fuzhou",
    "南京": "nanjing", "苏州": "suzhou", "成都": "chengdu", "重庆": "chongqing",
    "武汉": "wuhan", "西安": "xian", "天津": "tianjin", "青岛": "qingdao",
    "宁波": "ningbo", "长沙": "changsha", "合肥": "hefei", "郑州": "zhengzhou",
    "济南": "jinan", "昆明": "kunming", "大连": "dalian", "沈阳": "shenyang",
    "哈尔滨": "haerbin", "长春": "changchun", "太原": "taiyuan", "石家庄": "shijiazhuang",
    "南昌": "nanchang", "贵阳": "guiyang", "南宁": "nanning", "兰州": "lanzhou",
    "乌鲁木齐": "wulumuqi", "呼和浩特": "huhehaote", "银川": "yinchuan",
    "西宁": "xining", "拉萨": "lasa", "海口": "haikou", "三亚": "sanya",
    "东莞": "dongguan", "佛山": "foshan", "泉州": "quanzhou", "浙江": "zhejiang",
    "福建": "fujian", "广东": "guangdong", "江苏": "jiangsu", "山东": "shandong",
    "四川": "sichuan", "湖北": "hubei", "湖南": "hunan", "河南": "henan",
    "河北": "hebei", "陕西": "shaanxi", "安徽": "anhui", "江西": "jiangxi",
    "辽宁": "liaoning", "吉林": "jilin", "黑龙江": "heilongjiang",
    "云南": "yunnan", "贵州": "guizhou", "广西": "guangxi", "山西": "shanxi",
    "甘肃": "gansu", "新疆": "xinjiang", "内蒙古": "neimenggu", "海南": "hainan",
    "青海": "qinghai", "宁夏": "ningxia", "西藏": "xizang", "台湾": "taiwan",
}


def _slug(name: str) -> str:
    """地区名 → 拼音 code（用于文件名/注册 key）。未收录城市用 province_city 兜底。"""
    name = (name or "").strip()
    if name in _CITY_PINYIN:
        return _CITY_PINYIN[name]
    # 兜底：取第一个汉字拼音首字母不可靠 → 用 pinyin 无依赖 → 用 transliteration 简单表
    # 这里用「sanitize + 固定后缀」保证安全唯一
    import re
    clean = re.sub(r"[^a-zA-Z0-9]", "", name.lower())
    if clean:
        return "custom_" + clean
    return "custom_region"


def _register_region(code: str, name: str):
    """把新地区注册进 policies/__init__.py 的 REGIONS + REGION_LABELS。"""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policies", "__init__.py")
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    # 已注册则跳过（检查 REGIONS 里是否已有该 code）
    import re as _re
    if _re.search(rf'"re"{code}"\s*:', src) or f'"{code}":' in src:
        return
    # 动态加载模块
    anchor = '    "hangzhou": hangzhou,\n'
    if anchor in src:
        src = src.replace(anchor, anchor + f'    "{code}": __import__("policies.{code}", fromlist=["{code}"]),\n', 1)
    else:
        # 没有 hangzhou 锚点（理论不会）→ 插到 REGIONS 开头后
        src = src.replace('REGIONS = {\n', f'REGIONS = {{\n    "{code}": __import__("policies.{code}", fromlist=["{code}"]),\n', 1)
    src = src.replace(
        'REGION_LABELS = {\n    "national": "国家级（全国通用）",\n',
        f'REGION_LABELS = {{\n    "national": "国家级（全国通用）",\n    "{code}": "{name}",\n', 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)


# ---------------------------------------------------------------- 页面布局
def build_ui():
    regions = available_regions()
    region_choices = [(REGION_LABELS.get(r, r), r) for r in regions]

    # 顶栏：Logo 图优先，横幅背景优先；缺失回退 emoji + 渐变
    logo_html = (f'<img src="{LOGO_B64}" class="brand-logo-img" alt="枫独"/>'
                 if LOGO_B64 else '<div class="brand-logo">🍁</div>')
    banner_img = (f'<img src="{BANNER_B64}" class="brand-banner-img" alt=""/>'
                  if BANNER_B64 else '')
    bar_cls = "brand-bar" if BANNER_B64 else "brand-bar brand-bar-gradient"

    with gr.Blocks(title="枫独 · OPC 经营助手") as demo:
        # 全页背景图（img 层，absolute 铺满）
        if BG_B64:
            gr.HTML(f'<img src="{BG_B64}" id="full-bg" alt=""/>')
        gr.HTML(f"""
        <div id="brand-bar" class="{bar_cls}">
          {banner_img}
          <div class="brand-content">
            {logo_html}
            <div>
              <div class="brand-title">枫独 · OPC 经营助手</div>
              <div class="brand-sub">让一人公司把公司开明白 —— AI+金融 · 材料预审 / 经营诊断 / 合规问答</div>
            </div>
            <div class="region-pill" id="region-pill">地区可切换</div>
          </div>
        </div>
        """)

        # 合规边界显性横幅（首屏可见，符合"辅助不替代"赛制要求）
        gr.HTML("""
        <div class="hc-banner" style="background:#FDE8E8;border:1px solid #E5484D;color:#C0392B;
                    border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:13px;line-height:1.6;">
          🛡️ 本系统仅为<b>辅助经营顾问</b>，所有政策匹配与风险诊断结果<b>仅供参考</b>，
          不替代政府机构、金融机构或律师的最终专业判断。重大决策请咨询本地官方窗口。
        </div>
        """)

        region_dd = gr.Dropdown(choices=region_choices, value="wenzhou",
                                label="📍 经营地区（不同地区政策不同）",
                                info="切换地区：国家级通用政策始终生效，地区政策跟随切换。可直接输入任意城市/省份（未收录地区仅匹配全国通用政策，可在④导入政策）",
                                container=False,
                                elem_classes="region-dd",
                                allow_custom_value=True)

        with gr.Tabs():
            # ---------- Tab1 材料预审 ----------
            with gr.Tab("① 补贴材料预审"):
                gr.Markdown("> **场景**：一句话描述你的经营情况，AI 会主动追问关键信息，然后匹配可申请政策、生成材料清单、提示资格风险。")
                with gr.Row():
                    with gr.Column(scale=7):
                        chatbot = gr.Chatbot(height=430, label="对话",
                                             value=[{"role": "assistant",
                                                     "content": "👋 你好，我是枫独。描述一下你的经营情况吧，例如：\n\n**“我是温州个体工商户，开了2年，做摄影，月入3万，想申请创业补贴”**\n\n我会逐项问你几个关键问题，然后帮你预审材料。"}])
                        with gr.Row():
                            chat_input = gr.Textbox(placeholder="输入你的经营情况…", scale=6, container=False)
                            send_btn = gr.Button("发送", elem_id="maple-btn", scale=1)
                        status = gr.HTML()
                        reset_btn = gr.Button("🔄 重新开始", elem_id="reset-btn", size="sm")
                    with gr.Column(scale=5):
                        cockpit = gr.HTML(render_cockpit(bp.empty_profile(), "wenzhou", partial=True))

                profile_state = gr.State(bp.empty_profile())
                chat_state = gr.State([])

                send_btn.click(process_chat,
                               [chat_input, profile_state, chat_state, region_dd],
                               [chat_input, profile_state, region_dd, chatbot, cockpit, status])
                chat_input.submit(process_chat,
                                  [chat_input, profile_state, chat_state, region_dd],
                                  [chat_input, profile_state, region_dd, chatbot, cockpit, status])

                def on_region_change(region, profile):
                    """切换地区 → 同步 profile 地区 + 立即重算驾驶舱（地区标题/政策跟随）。"""
                    profile = profile or bp.empty_profile()
                    region = region or "wenzhou"
                    # region 可能是 code（wenzhou）或中文自定义（重庆）；存中文展示名
                    profile["region"] = REGION_LABELS.get(region, region)
                    if bp.is_complete(profile):
                        try:
                            summ = summary(profile, region)
                            indices = compute_indices(profile, region)
                            return profile, render_cockpit(profile, region, indices, summ, partial=False)
                        except Exception:
                            pass
                    return profile, render_cockpit(profile, region, partial=True)
                region_dd.change(on_region_change, [region_dd, profile_state], [profile_state, cockpit])

                def do_reset():
                    return bp.empty_profile(), [], [], render_cockpit(bp.empty_profile(), "wenzhou", partial=True), "已重置"
                reset_btn.click(do_reset, None, [profile_state, chat_state, chatbot, cockpit, status])

            # ---------- Tab2 经营诊断 ----------
            with gr.Tab("② 经营健康诊断"):
                gr.Markdown("> **场景**：填写（或一键带入示例）你的经营数据，AI 输出 6 维状态向量 + 三指数 + 行动建议。")
                with gr.Row():
                    with gr.Column(scale=5):
                        d_region = gr.Dropdown(choices=region_choices, value="wenzhou", label="地区",
                                               container=False, elem_classes="region-dd",
                                               allow_custom_value=True)
                        with gr.Row():
                            d_reg_type = gr.Textbox(label="注册类型", placeholder="个体工商户 / 一人有限责任公司")
                            d_industry = gr.Textbox(label="行业", placeholder="摄影 / 软件开发 / 餐饮…")
                        with gr.Row():
                            d_duration = gr.Textbox(label="经营时长", placeholder="2年")
                            d_revenue = gr.Textbox(label="月营收", placeholder="3万")
                        with gr.Row():
                            d_social = gr.Textbox(label="社保", placeholder="有 / 无")
                            d_buffer = gr.Textbox(label="现金流缓冲", placeholder="4个月")
                        with gr.Row():
                            d_client = gr.Textbox(label="客户集中度", placeholder="单客户60%")
                            d_team = gr.Textbox(label="团队人数", placeholder="1人")
                        d_edu = gr.Textbox(label="学历", placeholder="本科 / 专科 / 研究生")
                        d_grad = gr.Textbox(label="毕业年份", placeholder="2022")
                        d_order_cycle = gr.Textbox(label="订单周期", placeholder="如：1-3个月/单")
                        d_materials = gr.Textbox(label="已有材料", placeholder="如：营业执照/身份证（逗号分隔）")
                        with gr.Row():
                            diag_btn = gr.Button("🔍 开始诊断", elem_id="maple-btn")
                            prefill_btn = gr.Button("🍁 带入摄影师示例", elem_id="prefill-btn")
                        diag_note = gr.HTML()
                    with gr.Column(scale=5):
                        d_cockpit = gr.HTML(render_cockpit(bp.empty_profile(), "wenzhou", partial=True))
                        d_report = gr.Markdown()
                        # 算法透明度面板（P2-2g）：三指数怎么算，公式与代码一致，驳"查表器"质疑
                        with gr.Accordion("🔍 三指数是怎么算的？（透明可解释）", open=False):
                            gr.Markdown("""**健康指数** = 5 维等权 20% 平均：收入稳定性 + 现金流安全 + 成本控制 + 政策匹配 + 经营周期
每维带打分理由（见下方报告）——非黑盒、可解释。

**政策机会指数** = 地区差异化可申请政策数（国家级人人都有，不计入"机会"）。

**风险指数** = 规则引擎综合等级（低 / 中 / 高），含客户集中度 / 社保缺口 / 现金流缓冲三类风险。""")

                def do_prefill():
                    # 摄影师示例（PPT P7 案例）：带已有材料（营业执照/身份证）→ 驾驶舱显示「✅ 营业执照已备」
                    # 含订单周期「1-3个月/单」→ 6 维状态向量第 3 维「订单生命周期」可判（与 PPT P7 一致，S3）
                    vals = {"d_reg_type": "个体工商户", "d_industry": "摄影", "d_duration": "2年",
                            "d_revenue": "3万", "d_social": "无", "d_buffer": "4个月",
                            "d_client": "单客户60%", "d_team": "1人", "d_edu": "本科", "d_grad": "2022",
                            "d_order_cycle": "1-3个月/单",
                            "d_materials": "营业执照,身份证"}
                    return [vals.get(k, "") for k in ["d_reg_type", "d_industry", "d_duration", "d_revenue",
                                                       "d_social", "d_buffer", "d_client", "d_team", "d_edu",
                                                       "d_grad", "d_order_cycle", "d_materials"]]

                def run_diag(region, reg_type, industry, duration, revenue, social, buffer, client, team, edu, grad, order_cycle, materials):
                    inputs = {"reg_type": reg_type, "industry": industry, "duration": duration,
                              "revenue": revenue, "social_security": social, "cash_buffer": buffer,
                              "client_concentration": client, "team_size": team, "education": edu,
                              "grad_year": grad, "order_cycle": order_cycle, "has_materials": materials}
                    return run_diagnosis(inputs, region)

                prefill_btn.click(do_prefill, None,
                                  [d_reg_type, d_industry, d_duration, d_revenue, d_social,
                                   d_buffer, d_client, d_team, d_edu, d_grad, d_order_cycle, d_materials])
                diag_btn.click(run_diag,
                               [d_region, d_reg_type, d_industry, d_duration, d_revenue,
                                d_social, d_buffer, d_client, d_team, d_edu, d_grad, d_order_cycle, d_materials],
                               [d_cockpit, d_report])

                def on_d_region_change(region):
                    """Tab2 切换地区 → 驾驶舱标题跟随（未收录地区显示'未收录'）。"""
                    region = region or "wenzhou"
                    return render_cockpit(bp.empty_profile(), region, partial=True)
                d_region.change(on_d_region_change, [d_region], [d_cockpit])

            # ---------- Tab3 合规问答 ----------
            with gr.Tab("③ 经营合规问答"):
                gr.Markdown("> **场景**：问税务/合同/开票/社保问题。已接入 AI 深度回答，离线时由内置知识库兜底。")
                c_chat = gr.Chatbot(height=430)
                with gr.Row():
                    c_input = gr.Textbox(placeholder="例如：一人公司报税有什么要注意的？", scale=6, container=False)
                    c_btn = gr.Button("发送", elem_id="maple-btn", scale=1)
                c_btn.click(compliance_chat, [c_input, c_chat], [c_chat, c_input])
                c_input.submit(compliance_chat, [c_input, c_chat], [c_chat, c_input])

            # ---------- Tab4 政策导入 ----------
            with gr.Tab("④ 政策导入（多地区扩展）"):
                gr.Markdown("> **场景**：你有某地真实政策原文 → 粘贴给 AI → 自动结构化入库该地区 → 地区下拉即可切换使用。\n\n⚠️ AI 结构化可能出错，入库后请人工核对与官方文件一致（零造假原则）。")
                with gr.Row():
                    imp_region = gr.Textbox(label="目标地区", value="杭州", placeholder="如：杭州 / 北京 / 广州")
                    imp_btn = gr.Button("入库政策", elem_id="maple-btn")
                imp_text = gr.Textbox(label="政策原文", lines=8,
                                      placeholder="粘贴政策原文（含名称、金额、资格条件、申请材料、来源）…")
                imp_result = gr.Markdown()
                imp_btn.click(import_policy, [imp_region, imp_text], [imp_result])

        gr.HTML('<div class="footnote">🍁 枫独 · OPC 经营助手 — GOAI 无界应用大赛 AI+金融 赛道演示。'
                '数据来源：公开政策文件（温州 OPC 创业扶持申请操作指南等）。所有输出为辅助参考，'
                '不替代专业机构/金融机构最终判断。政策以官方最新文件为准。</div>')

    return demo


if __name__ == "__main__":
    demo = build_ui()
    # Gradio 6.x：css/theme 移到 launch()
    # 主题：默认暖橙主版；UI_THEME=high_contrast → 高对比投影备选版（决赛投影仪糊了时切换）
    if USE_HC:
        active_css, hue = HC_CSS, "blue"
    else:
        active_css, hue = CSS, "orange"
    theme = gr.themes.Base(primary_hue=hue, neutral_hue="stone",
                           font=["Microsoft YaHei", "sans-serif"])
    # 端口：GRADIO_SERVER_PORT 优先（便于多实例/测试），默认 7860
    port = int(_os.getenv("GRADIO_SERVER_PORT", "7860"))
    demo.launch(server_name="0.0.0.0", server_port=port, show_error=True,
                css=active_css, theme=theme)
