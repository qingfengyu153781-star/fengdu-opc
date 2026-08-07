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
.gradio-container table, .gradio-container table th, .gradio-container table td {
  background: #ffffff !important; color: #000000 !important;
  border: 1px solid #444444 !important; }
.gradio-container table th { background: #f0f0f0 !important; color: #000000 !important; }
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

/* ---- Markdown 表格（地区对比等）：Gradio 深色模式默认白底白字，覆盖成暖色主题 ---- */
.gradio-container table,
.gradio-container .prose table,
.gradio-container .markdown table,
.gradio-container table.markdown-table {{
  background: {PANEL} !important;
  color: {TEXT} !important;
  border-collapse: collapse !important;
  border-radius: 8px !important;
  overflow: hidden !important;
  margin: 6px 0 10px !important;
}}
.gradio-container table th,
.gradio-container table td {{
  background: transparent !important;
  color: {TEXT} !important;
  border: 1px solid {COCKPIT_BORDER} !important;
  padding: 8px 12px !important;
  text-align: left !important;
  font-size: 13px !important;
  line-height: 1.5 !important;
}}
.gradio-container table th {{
  background: {BG_DEEP} !important;
  color: {MAPLE_RED} !important;
  font-weight: 700 !important;
  white-space: nowrap !important;
}}
.gradio-container table tr:nth-child(even) td {{
  background: {BG_DEEP} !important;
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

/* 2026-08-07 深色模式可读性修复：gr.HTML 内 <b> 与 Accordion 标题在 gradio 深色主题下默认白字，看不清 */
/* 合规边界横幅：强制浅粉底深红字（覆盖 gradio 深色模式把 <b> 变白的问题） */
.hc-banner {{ background: #FDE8E8 !important; border: 1px solid #E5484D !important; color: #C0392B !important; }}
.hc-banner * {{ color: #C0392B !important; }}
/* 三指数说明 Accordion 标题：默认黑字可读（覆盖 gradio 深色模式白字，gradio6 实际结构=button.label-wrap 内 span） */
.gradio-container button.label-wrap,
.gradio-container button.label-wrap * {{
  color: #000000 !important;
}}
.gradio-container details summary,
.gradio-container details summary *,
.gradio-container .accordion-heading,
.gradio-container .accordion-heading * {{
  color: #000000 !important;
}}

/* 隐藏 Chatbot 组件顶部的标题框（Tab1「对话」/ Tab3 默认「Chatbot」）。
   gradio6 Chatbot 的 block 内含独有元素 div[data-testid="status-tracker"]，
   用 :has() 精确匹配该 block 内的 label[data-testid="block-label"]（只隐藏 Chatbot，不动 Textbox） */
.block:has(> [data-testid="status-tracker"]) > .wrapper > label[data-testid="block-label"] {{
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
        # F19（2026-08-07）：缺失材料加"去哪办"来源机构提示（从政策 source 提取）
        where = m.get("source", "") or ""
        where_html = (f' <span style="font-size:10.5px;color:#E3C9B0;">→ {where[:18]}</span>'
                      if where and len(where) < 24 else "")
        if m["status"] == "缺失":
            mat_html += f'<div class="material"><span class="warn">⚠️ {m["name"]}</span>{where_html}</div>'
        else:
            mat_html += f'<div class="material"><span class="warn">⏳ {m["name"]}</span>{where_html}</div>'
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
        _m, _p = len(missing), len(pending)
        if _m and _p:
            lines.append(f"\n⚠️ **建议准备/确认材料**（{_m} 项缺失 · {_p} 项待确认）：")
        elif _m:
            lines.append(f"\n⚠️ **建议优先准备材料**（缺 {_m} 项）：")
        else:
            lines.append(f"\n⚠️ **请确认以下材料是否已备**（{_p} 项待确认）：")
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


def _region_display(code_or_name: str) -> str:
    """code→展示名（'wenzhou'→'温州'）；已是中文则原样（供输入框回显，2026-08-07 UI 调整）。"""
    return REGION_LABELS.get(code_or_name, code_or_name)


def _looks_like_off_topic(text: str) -> bool:
    """判断回答是否明显跑题（跳过/不知道），此时不应把原文硬塞进字段。"""
    return any(k in text for k in ("不知道", "不清楚", "跳过", "下一个", "随便", "换一个"))


def _looks_like_garbage(text: str) -> bool:
    """判断输入是否是无意义/乱码（胡言乱语防护，F17 修复）。

    用户可能输入乱码/无意义句子，系统不应把"奘馕肏犇""今天天气好"当成
    注册类型/地区等真实字段记录（会污染 profile，导致政策路由错误）。
    检测特征：
      - 3+ 连续相同字符（"啊啊啊啊""111111"）
      - 纯标点/emoji/符号
      - 生僻字（GBK 罕见/非常用字，如 奘馕肏犇 这类在正常经营表达中不出现）
      - 常见城市/行业/经营词的"表意密度"过低
    """
    t = (text or "").strip()
    if not t:
        return True
    # 连续重复字符（3+）
    if re.search(r"(.)\1{2,}", t):
        return True
    # 纯标点/符号/emoji（无汉字无字母数字）
    if not re.search(r"[一-鿿0-9A-Za-z]", t):
        return True
    # 生僻字检测：乱码多是 GBK 二级字/非常用字（如 奘/馕/犇），正常经营表达（摄影/青岛/餐饮）全是一级常用字。
    # 用 GBK 编码级别判定：一级字（0xB0A1-0xD7F9，现代汉语常用字表 3755 字）视为正常，
    # 含二级字/无法 GBK 编码的字 → 乱码。精准区分"奘馕肏犇"(乱码) vs "青岛/摄影"(正常)。
    hanzi = re.findall(r"[一-鿿]", t)
    if len(hanzi) >= 2:
        rare = [ch for ch in hanzi if not _is_gbk_common(ch)]
        if len(rare) >= max(1, len(hanzi) // 2):
            return True
    return False


def _is_gbk_common(ch: str) -> bool:
    """判断汉字是否为 GBK 一级常用字（现代汉语常用字表前 3755 字）。"""
    try:
        b = ch.encode("gbk")
        if len(b) == 1:
            return True  # ASCII
        hi = b[0]
        return 0xB0 <= hi <= 0xD7  # GBK 一级区
    except Exception:
        return False  # 无法 GBK 编码（更生僻）


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
        return "", profile, _region_display(region), chat, render_cockpit(profile, region, partial=True), ""
    chat.append({"role": "user", "content": user_text})

    # 涉法红线拦截：命中立即拒绝，绝不带进匹配流程（合规硬约束）
    if _has_redline(user_text):
        chat.append({"role": "assistant", "content": _REDLINE_REPLY})
        region_out = _region_code(profile.get("region") or region)
        return ("", profile, _region_display(region_out), chat,
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
        if extracted:
            # 本轮已识别到其他字段（如客户集中度/现金流），说明用户在补充信息而非回答当前问题
            # → 不做宽松数字兜底，防止把"单客户60%"的 60 误塞进 team_size（团队规模=60 bug）
            pass
        elif q_key in ("social_security", "corp_account", "biz_scope_ai"):
            v = bp.parse_yes_no(user_text)
            if v:
                extracted[q_key] = v
        elif q_key in ("revenue", "duration", "cash_buffer", "order_cycle", "team_size", "grad_year"):
            v = bp.extract_loose_number(user_text, q_key)
            if v:
                extracted[q_key] = v
        else:
            # 自由文本字段：仅当回答简短、非跑题、非垃圾、且没提供其他字段信息时，直接记录原文
            other_fields = [k for k in extracted if k != q_key]
            if q_key == "region":
                # region 只接受纯地名短回答（如"重庆""广州"），拒绝"客户比较分散"这类非地名
                # 和乱码（"奘馕肏犇"也是 2-4 汉字，需垃圾检测）——否则会把无关回答当地区，导致政策路由错误
                if (re.match(r"^[一-龥]{2,4}$", user_text)
                        and not _looks_like_off_topic(user_text)
                        and not _looks_like_garbage(user_text)):
                    extracted[q_key] = user_text
            elif (len(user_text) <= 40
                  and not _looks_like_off_topic(user_text)
                  and not _looks_like_garbage(user_text)
                  and not other_fields):
                # 封闭选项字段（reg_type/social_security/education/biz_scope_ai/corp_account）不直录任意文本——
                # 只接受用户回答"选项"里的值或数字字段的自然值；乱码/无意义句子不记录（F17 修复）
                if q_key in ("reg_type", "social_security", "education", "biz_scope_ai", "corp_account"):
                    fdef = next((f for f in bp.FIELDS if f["key"] == q_key), None)
                    opts = fdef.get("options", []) if fdef else []
                    # 封闭选项：只有回答与某个选项部分匹配才记录；否则视为无效回答（不塞垃圾）
                    if not opts or not any(o in user_text for o in opts):
                        pass
                    else:
                        extracted[q_key] = user_text
                else:
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
        return "", profile, _region_display(region_out), chat, cockpit, status

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
    return "", profile, _region_display(region_out), chat, cockpit, status


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
    # 注意 dict 遍历顺序 = 命中顺序：长的/具体的关键词放前面，避免被短词抢答
    "月销售额": "月销售额 10 万以下（按季 30 万）的小规模纳税人免征增值税，申报时系统自动判断。辅助参考，以官方公告为准。",
    "小型微利": "小型微利企业年应纳税所得额不超过 300 万元，实际税负约 5%，季度申报时系统自动享受，无需单独备案。辅助参考，以税务部门最新口径为准。",
    "小微企业": "小微企业通常指小型微利企业：年应纳税所得额≤300万、从业人数≤300人、资产总额≤5000万，实际税负约 5%（季度申报自动享受）。辅助参考，以官方口径为准。",
    "小规模纳税人": "月销售额 10 万以下（按季 30 万）的小规模纳税人免征增值税；年销售额超 500 万自动转为一般纳税人。辅助参考，以税务最新口径为准。",
    "一般纳税人": "年销售额超 500 万通常需登记一般纳税人；小规模纳税人可自愿转登记，但进项抵扣规则不同，建议先咨询税务。辅助参考。",
    "报税": "一人公司/个体户报税注意：①小规模纳税人月销售额 10 万以下（季度 30 万）免征增值税；②小型微利企业实际税负约 5%；③补贴收入通常不征企业所得税，但以当地税务口径为准；④建议从 Day 1 记清收入/成本/研发支出，避免年底补账。辅助参考，以税务部门最新口径为准。",
    "增值税": "月销售额 10 万以下（按季 30 万）的小规模纳税人免征增值税；超过则按 1% 或适用税率征收（政策会调整，以当期公告为准）。辅助参考。",
    "个税": "个体户经营所得按 5%-35% 五级累进；个人独资/合伙企业合伙人同样按经营所得计税。辅助参考，以税务最新口径为准。",
    "企业所得税": "小微企业实际税负约 5%（年应纳税所得额≤300万）；一般企业 25%。一人有限责任公司独立法人，需缴纳企业所得税。辅助参考。",
    "发票": "小规模纳税人可自开增值税普通发票；月销售额 10 万以下免征增值税但需如实申报。专票需咨询当地税务能否代开。辅助参考。",
    "开票": "小规模纳税人可自开增值税普通发票；月销售额 10 万以下免征增值税但需如实申报。专票需咨询当地税务能否代开。辅助参考。",
    "社保": "一人公司/个体户可缴灵活就业社保，多项温州创业补贴要求缴纳社保（如创业带动就业补贴、人才租房补贴），建议尽早开通。辅助参考。",
    "医保": "灵活就业可缴职工医保或城乡居民医保；职工医保报销比例通常更高、有个人账户。一人生意建议至少配一份医保。辅助参考。",
    "公积金": "个体户/灵活就业在部分地区可自愿缴存公积金（看当地政策），租房、买房贷款有用。辅助参考，以当地公积金中心为准。",
    "加计": "研发费用可在税前加计扣除，需建立研发费用辅助账。对单人软件公司，大模型 API 费用可计入研发投入。辅助参考，以税务申报要求为准。",
    "双软": "软件企业两免三减半需通过双软认定（软件产品登记 + 软件企业认定），建议找代理机构办理（¥3,000-8,000 一次性）。辅助参考。",
    "软著": "软件著作权登记约 1-3 个月，费用数百元（可自行通过版权局或代办）。软著是申请双软、高新、部分创业补贴的常见材料。辅助参考。",
    "合同": "建议用书面合同明确：服务内容/交付物、金额与付款节点、验收标准、知识产权归属、违约责任。一人生意也建议签，保护自己。辅助参考，具体条款咨询律师。",
    "公司注册": "一人公司注册流程：核名→准备材料→提交登记→领取执照→刻章→银行开户→税务登记。个体户类似但更简。部分地区免费代办。辅助参考。",
    "营业执照": "营业执照办理：政务服务网/市监部门登记，个体户或一人公司均可。办完需按时年报（每年 6 月底前），逾期进经营异常名录。辅助参考。",
    "经营异常": "年报逾期或地址失联会进经营异常名录，影响贷款与信誉。发现后尽快补报并向市监申请移出。辅助参考。",
    "创业贷款": "创业担保贷款各地额度常见 10-30 万、可贴息，需当地人社局推荐+银行审批，一般要求有营业执照、正常经营。辅助参考，以当地政策为准。",
    "补贴": "常见创业补贴：一次性创业补贴、场地/租金减免、社保补贴、创业带动就业补贴。资格看学历/毕业年限/注册类型/社保，各地不同，以当地人社为准。辅助参考。",
    "个转企": "个体工商户可转型升级为有限责任公司（个转企），多地有配套补贴或税收延续政策，办理前咨询当地市监。辅助参考。",
    "账": "一人生意也建议记账：收入/成本/研发/发票分清楚，年底报税和申补贴都要用。可用免费记账软件，或找代账（约 ¥200-500/月）。辅助参考。",
    "代账": "小微企业代账服务常见 ¥200-500/月，含记账+报税。可节省时间，但务必选有资质机构并核对账目。辅助参考。",
    "知识产权": "一人公司也建议保护：商标注册（约 ¥300/类/次）、软著登记、专利（视行业）。商标有恶意抢注风险，早注册早安心。辅助参考。",
    "商标": "商标注册约 ¥300/类（官网申请），注册周期 6-12 个月。建议注册前先查重，避免驳回或侵权。辅助参考。",
    "灵活就业": "灵活就业人员可缴养老+医疗（本地户籍或居住证），缴费比例低于企业职工。多项补贴需社保，尽早开通。辅助参考，以当地社保局为准。",
    "劳务": "个人劳务报酬所得按 20%-40% 预扣预缴个税，次年汇算清缴可退税。长期稳定接单可考虑注册个体户/公司节税并合规开票。辅助参考。",
    "风险": "常见经营风险：社保断缴、客户集中、现金流不足、发票合规、年报逾期。建议定期用「②经营健康诊断」自查三指数。辅助参考。",
    "查账": "税务机关可能抽查账目，务必保留收入/成本/发票凭证至少 5 年。一人生意也不例外。辅助参考。",
    "注销": "不再经营需办理注销（税务清税→工商注销），逾期未注销可能进黑名单。建议咨询代办或当地市监。辅助参考。",
    "年报": "每年 1-6 月需报企业/个体户年报，逾期进经营异常名录。这是最容易忽略的合规项。辅助参考。",
}


def compliance_chat(message, history):
    history = history or []
    history.append({"role": "user", "content": message})

    # 涉法红线拦截（合规硬约束，LLM 之前先拦）
    if _has_redline(message):
        history.append({"role": "assistant", "content": _REDLINE_REPLY})
        return history, ""

    # 实时联网搜索（免费，独立于 LLM；失败静默）
    # E3 增强：有 key 时先生成精准搜索词再搜（理解任意表达），无 key 用裸问题搜
    _search_q = message
    if api_client.is_api_available():
        try:
            _sys = ("你是政策检索专家。把用户问题转成 1 条精准的搜索引擎查询词（中文，8-20字），"
                    "只输出查询词本身，不要解释。")
            _raw, _ = api_client.generate(_sys, f"问题：{message}", temperature=0.3, max_tokens=60)
            _q = (_raw or "").strip().split("\n")[0].strip().strip("“”\"'。")
            if 4 <= len(_q) <= 40:
                _search_q = _q
        except Exception:
            pass  # 生成失败 → 用裸问题搜（不白屏）
    web_block = policy_searcher.format_web_search(_search_q)

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
    """政策导入：粘贴原文 → LLM 结构化 → 追加到 policies/<region>.py。

    热加载（2026-08-07 修复）：入库成功后返回 (msg, 地区展示名, 地区 code)，
    顶部地区输入框自动填为入库地区、共享 region_state 同步为 code——本次会话即可用，无需重启。
    失败路径返回 (msg, None, None)（输入框与地区 state 不变）。
    """
    policy_text = (policy_text or "").strip()
    if not policy_text:
        return "请先粘贴政策原文。", None, None
    if not _looks_like_policy(policy_text):
        return ("⚠️ **未能识别为政策原文**：请粘贴包含政策名称、金额、资格条件的完整政策文本"
                "（如政府公告原文）。已拒绝入库，防止错误数据污染政策库。"), None, None
    if api_client.is_api_available():
        try:
            sys_p = agent_prompts.POLICY_IMPORT_PROMPT.format(region=region, policy_text=policy_text)
            raw, model = api_client.generate(sys_p, "", temperature=0.2, max_tokens=2500)
            parsed = _parse_import_json(raw)
            if parsed:
                n = _write_policies_file(region, parsed)
                return (f"✅ 已入库 **{n} 条**政策（AI 结构化）\n\n"
                        f"地区「{region}」政策库已更新，**本次会话即可用**（已切到「{region}」，无需重启）。\n\n"
                        f"⚠️ 请人工核对入库内容与原文一致——AI 结构化可能出错，以官方文件为准。\n\n"
                        f"💡 更多该地区政策可用 **⑤ 政策动态** 实时搜索 → 一键入库。"), region, _slug(region)
            # AI 失败 → 回退规则解析
            parsed = _parse_policy_rules(policy_text)
            if parsed:
                n = _write_policies_file(region, parsed)
                return (f"✅ 已入库 **{n} 条**政策（规则解析）\n\n"
                        f"地区「{region}」政策库已更新，**本次会话即可用**。\n\n"
                        f"⚠️ 规则解析识别有限，请人工核对入库内容与官方原文一致。\n\n"
                        f"💡 更多该地区政策可用 **⑤ 政策动态** 实时搜索 → 一键入库。"), region, _slug(region)
            return "⚠️ 无法解析政策结构，请检查原文格式或稍后重试。", None, None
        except Exception as e:
            return f"⚠️ 导入失败：{e}，请稍后重试。", None, None
    # 离线 → 规则解析（零 LLM 依赖也能导入）
    parsed = _parse_policy_rules(policy_text)
    if parsed:
        n = _write_policies_file(region, parsed)
        return (f"✅ 已入库 **{n} 条**政策（离线规则解析）\n\n"
                f"地区「{region}」政策库已更新，**本次会话即可用**（已切到「{region}」，无需重启）。\n\n"
                f"⚠️ 规则解析识别有限，请人工核对入库内容与官方原文一致。\n\n"
                f"💡 更多该地区政策可用 **⑤ 政策动态** 实时搜索 → 一键入库。"), region, _slug(region)
    return "⚠️ 未能识别政策结构，请检查原文格式后重试。", None, None


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
    """把新地区注册进运行中的 REGIONS + REGION_LABELS（内存热加载，免重启即用），
    并持久化进 policies/__init__.py（重启后仍生效）。

    2026-08-07 热加载修复：此前导入政策后必须重启服务下拉才出现新地区——
    现在写完 policies/<code>.py 后立即 reload 模块 + 更新内存 REGIONS/REGION_LABELS，
    import_policy 同步返回新下拉选项，本次会话即可切换使用。
    """
    import importlib
    # ① 内存热注册：reload 该地区模块（首次导入后 reload 一次拿到最新内容），
    #    更新 policies 模块的 REGIONS / REGION_LABELS（app 层引用的是同一 dict 对象，自动同步）
    try:
        mod = importlib.import_module(f"policies.{code}")
        importlib.reload(mod)
        import policies
        policies.REGIONS[code] = mod
        policies.REGION_LABELS[code] = name
    except Exception:
        pass  # 内存注册失败不阻塞文件持久化（重启后仍生效）
    # ② 持久化注册（重启后仍生效）
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


# ---------------------------------------------------------------- Tab⑤ 政策动态 · 地区对比（F18，2026-08-07）
# 哲学：政策内容全部靠模型实时搜索发现（零预置库），用户可自定义搜索词。
_PHOTOGRAPHER_PROFILE = {
    "reg_type": "个体工商户", "industry": "摄影", "duration": "2年", "revenue": "3万/月",
    "social_security": "无", "cash_buffer": "4个月", "client_concentration": "单客户60%",
    "team_size": "1人", "education": "本科", "grad_year": "2022", "order_cycle": "1-3个月/单",
    "has_materials": "营业执照,身份证",
}


def _search_result_to_policy(r: dict) -> dict | None:
    """搜索结果 → 可入库 policy dict（带真实来源 URL，供一键入库）。

    标题即为政策名（截断 50 字）；detail 是官方原文提炼的金额/资格/材料。
    入库后 data_status 标「导入数据·待核对」——不污染政策机会指数（零造假）。
    """
    title = (r.get("title") or "").strip()
    if not title or not _policy_name_ok(title):
        return None
    detail = r.get("detail", {}) or {}
    return {
        "name": title[:50],
        "region": "",
        "category": "实时搜索",
        "amount": detail.get("amount", "以官方文件为准"),
        "eligibility": detail.get("eligibility") or ["以官方文件为准"],
        "materials": [{"name": m, "required": True}
                      for m in (detail.get("materials") or ["以当地官方要求为准"])],
        "source": (r.get("url") or "搜索引擎结果")[:80],
        "source_url": r.get("url") or "",
        "difficulty": "待评估",
        "timing": "以当地官方为准",
        "key_point": "实时搜索获得，入库前请人工核对与官方原文一致",
        "update_date": "2026-08",
    }


def _format_opc_results(region: str, results: list[dict]) -> str:
    """把搜索结果格式化成报告段落（官方优先、来源可溯源、结构化要素）。"""
    lines = [f"🔍 **实时搜索「{region}」政策结果**（来源：网页搜索，官方优先，需点开核验）："]
    for r in results[:6]:
        tag = {"官方": "🏛 官方", "信息平台": "📄 信息平台", "需核验": "🔗 第三方"}.get(r.get("official"), "")
        line = f"- {tag} **{r['title']}**\n  · [查看来源]({r['url']})"
        if r.get("snippet"):
            line += f"\n  · {r['snippet']}"
        detail = r.get("detail", {}) or {}
        if detail.get("amount"):
            line += f"\n  · 💰 {detail['amount']}"
        if detail.get("eligibility"):
            line += f"\n  · ✅ 资格：{'；'.join(detail['eligibility'][:2])}"
        if detail.get("materials"):
            line += f"\n  · 📋 材料：{'、'.join(detail['materials'])}"
        lines.append(line)
    lines.append("\n> 以上为搜索引擎实时结果，🏛官方来源可作申请依据；💰/✅/📋 为抓取原文提炼，具体以官方最新文件为准。")
    lines.append("> 💡 若某条正是你需要的政策，点下方「✅ 一键入库」保存到本地库（离线也能用）。入库前请人工核对与官方原文一致。")
    return "\n".join(lines)


def do_dyn_search(region: str, keyword: str, desc: str):
    """Tab⑤ 政策动态搜索：三档搜索词（用户关键词 > 描述提炼 > 自动热点词）。

    返回 (展示md, 可入库policies, 地区code, 状态信息)。
    """
    region = (region or "杭州").strip()
    keyword = (keyword or "").strip()
    desc = (desc or "").strip()
    llm_fn = api_client.generate if api_client.is_api_available() else None

    # 用户留空关键词但填了描述 → 先用 AI 提炼关键词（有 LLM 时）
    if not keyword and desc and llm_fn is not None:
        kw = policy_searcher.generate_keyword_from_desc(desc, region, llm_fn)
        if kw:
            keyword = kw
    if not keyword and desc and llm_fn is None:
        # 无 LLM：给出提示，仍用自动词搜索
        pass

    results = policy_searcher.search_opc_policies(region, keyword, _PHOTOGRAPHER_PROFILE, llm_fn)
    if not results:
        return policy_searcher.unavailable_notice(region), [], region, "搜索无结果（网络受限或该地区政策较少）"

    md = _format_opc_results(region, results)
    # 构造可入库 policy（官方来源优先，取前 5 条）
    pols = []
    for r in results:
        p = _search_result_to_policy(r)
        if p and len(pols) < 5:
            pols.append(p)
    status = f"搜到 {len(results)} 条结果，其中 {len(pols)} 条可入库"
    return md, pols, region, status


def do_import_searched(policies: list, region: str):
    """Tab⑤ 一键入库：把实时搜索到的政策写入本地库（用户手动确认后）。

    复用 import_policy 的 _write_policies_file + _register_region（热注册免重启）。
    返回 (msg, 地区名, 地区code)。
    """
    region = (region or "").strip()
    if not policies:
        return "暂无搜到的政策可入库，请先在上方搜索。", None, None
    pols = [p for p in policies if _policy_name_ok(p.get("name", ""))]
    if not pols:
        return "搜索结果的名称不规范，无法入库（已过滤垃圾/纯数字名）。", None, None
    n = _write_policies_file(region, pols)
    return (f"✅ 已入库 **{n} 条**到「{region}」（实时搜索结果，data_status 标「导入数据·待核对」）\n\n"
            f"已自动切换地区到「{region}」，本次会话即可用（重启后仍生效）。\n\n"
            f"⚠️ 入库内容来自网页搜索，请**人工核对**与官方原文一致。",
            region, _slug(region))


def compare_regions(region_a: str, region_b: str) -> str:
    """Tab⑤ 地区对比：同一经营画像，对比两地区政策机会/健康/可申请政策。

    已收录地区（温州）用规则引擎真实计算；未收录地区（杭州等）政策机会为 0，
    明确提示靠「政策动态」实时搜索获取——零造假，不预置。
    """
    region_a = (region_a or "温州").strip()
    region_b = (region_b or "杭州").strip()
    p = bp.empty_profile()
    p.update(_PHOTOGRAPHER_PROFILE)
    p["region"] = region_a

    def _col(region: str) -> dict:
        code = _region_code(region)
        idx = compute_indices(p, code)
        info = region_info(code)
        names = "、".join(idx["policy_names_local"][:3]) or "暂无（未收录→实时搜索）"
        return {
            "status": info.get("data_status", ""),
            "opp": idx["policy_opportunity"],
            "health": idx["health"],
            "names": names,
            "code": code,
        }

    a, b = _col(region_a), _col(region_b)
    lines = [
        "### 🔁 地区对比（同一经营画像）",
        "**画像**：个体工商户 · 摄影 · 2年 · 月入3万 · 无社保 · 本科(2022毕业)",
        "",
        "| 维度 | " + region_a + " | " + region_b + " |",
        "|------|------|------|",
        f"| 数据状态 | {a['status']} | {b['status']} |",
        f"| 政策机会 | **{a['opp']}** 项 | **{b['opp']}** 项 |",
        f"| 健康指数 | {a['health']} | {b['health']} |",
        f"| 可申请 | {a['names']} | {b['names']} |",
        "",
    ]
    lines.append("> 📌 **未收录地区**（data_status 含「需核验」）政策机会为 0——政策靠上方「政策动态」实时搜索获取，"
                 "不是系统漏算。国家级通用政策（小型微利/增值税/六税两费）两地区都自动享受。")
    if "真实" not in a["status"]:
        lines.append(f"> 💡 想对比「{region_a}」实际能申什么？在上方搜政策 → 一键入库，政策机会立刻变真实数字。")
    elif "真实" not in b["status"]:
        lines.append(f"> 💡 想对比「{region_b}」实际能申什么？在上方搜政策 → 一键入库，政策机会立刻变真实数字。")
    return "\n".join(lines)


def suggest_compliance_questions() -> str:
    """合规问答「💡 让模型推荐该问的问题」：LLM 生成 3 个建议问题。

    有 key → 模型基于合规知识概览生成（不硬编码）；无 key → 降级固定 3 个通用问题。
    返回 markdown 文本（显示在 Chatbot 里）。
    """
    fixed = (
        "1. **一人公司报税有什么要注意的？**\n"
        "2. **小规模纳税人月销售额多少免征增值税？**\n"
        "3. **个体户没交社保，影响申请补贴吗？**\n"
    )
    if not api_client.is_api_available():
        return "💡 **建议从这些问题开始问**（未配置 LLM API，以下为通用建议）：\n\n" + fixed
    try:
        sys_p = (
            "你是「枫独·OPC经营助手」。根据以下合规知识概览，为一名一人公司/个体户创业者"
            "推荐 3 个最值得问的经营/税务/合规问题。\n"
            "要求：\n1. 贴近一人公司场景（税务/社保/补贴/合同）\n"
            "2. 每个问题一句话、口语化\n"
            "3. 只输出问题清单，编号 1/2/3，不要解释\n\n"
            f"知识概览：{agent_prompts.COMPLIANCE_KNOWLEDGE[:300]}"
        )
        content, _ = api_client.chat(
            [{"role": "system", "content": sys_p},
             {"role": "user", "content": "推荐 3 个问题"}],
            max_tokens=200)
        content = (content or "").strip()
        if len(content) >= 10:
            return "💡 **模型推荐的问题**（点上方问题输入框直接问）：\n\n" + content
    except Exception:
        pass
    return "💡 **建议从这些问题开始问**：\n\n" + fixed


# ---------------------------------------------------------------- 页面布局
def build_ui():
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
            <div class="region-pill" id="region-pill">地区可输入</div>
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

        # 2026-08-07 UI 调整：地区选择器从下拉改为纯输入框（评委需求），功能不变——
        # 输入任意城市/省份即切换地区（回车生效），政策跟随；温州/杭州自动映射已收录库，
        # 其他地区走实时搜索 + 通用兜底。
        # region_state 存当前生效地区 code，供诊断 Tab 共享（诊断不再单独设地区下拉）。
        region_input = gr.Textbox(value="温州",
                                  label="📍 经营地区（输入城市/省份即切换，不同地区政策不同）",
                                  info="输入任意城市/省份（如：温州 / 杭州 / 重庆）→ 回车生效：国家级通用政策始终生效，地区政策跟随切换。未收录地区自动实时搜索当地政策，可在④导入政策。",
                                  container=False,
                                  elem_classes="region-dd",
                                  placeholder="如：温州 / 杭州 / 重庆 / 北京")
        region_state = gr.State("wenzhou")

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
                               [chat_input, profile_state, chat_state, region_input],
                               [chat_input, profile_state, region_input, chatbot, cockpit, status])
                chat_input.submit(process_chat,
                                  [chat_input, profile_state, chat_state, region_input],
                                  [chat_input, profile_state, region_input, chatbot, cockpit, status])

                def on_region_change(region, profile):
                    """输入地区（回车/失焦）→ 同步 profile 地区 + 更新共享地区 code + 立即重算驾驶舱。

                    region 可能是中文（温州）或 code（wenzhou）；profile['region'] 存展示名，
                    region_state 存 code（供诊断 Tab 共享），render_cockpit 用展示名保持标题正确。
                    """
                    profile = profile or bp.empty_profile()
                    region = region or "温州"
                    profile["region"] = REGION_LABELS.get(region, region)
                    code = _region_code(profile["region"])
                    if bp.is_complete(profile):
                        try:
                            summ = summary(profile, code)
                            indices = compute_indices(profile, code)
                            return profile, render_cockpit(profile, region, indices, summ, partial=False), code
                        except Exception:
                            pass
                    return profile, render_cockpit(profile, region, partial=True), code
                region_input.submit(on_region_change, [region_input, profile_state],
                                    [profile_state, cockpit, region_state])
                region_input.blur(on_region_change, [region_input, profile_state],
                                  [profile_state, cockpit, region_state])

                def do_reset():
                    return bp.empty_profile(), [], [], render_cockpit(bp.empty_profile(), "wenzhou", partial=True), "已重置"
                reset_btn.click(do_reset, None, [profile_state, chat_state, chatbot, cockpit, status])

            # ---------- Tab2 经营诊断 ----------
            with gr.Tab("② 经营健康诊断"):
                gr.Markdown("> **场景**：填写（或一键带入示例）你的经营数据，AI 输出 6 维状态向量 + 三指数 + 行动建议。")
                with gr.Row():
                    with gr.Column(scale=5):
                        # 2026-08-07 UI 调整：诊断 Tab 不再单独设地区下拉——统一用顶部「经营地区」输入框
                        # （region_state 共享，自动跟随顶部输入的地区）。
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
                            reset_diag_btn = gr.Button("🔄 重新开始", elem_id="reset-btn", size="sm")
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

                def run_diag(reg_type, industry, duration, revenue, social, buffer, client, team, edu, grad, order_cycle, materials, region):
                    # region 来自顶部共享 region_state（code，如 wenzhou / 自定义中文），诊断跟随顶部输入的地区
                    inputs = {"reg_type": reg_type, "industry": industry, "duration": duration,
                              "revenue": revenue, "social_security": social, "cash_buffer": buffer,
                              "client_concentration": client, "team_size": team, "education": edu,
                              "grad_year": grad, "order_cycle": order_cycle, "has_materials": materials}
                    return run_diagnosis(inputs, region)

                prefill_btn.click(do_prefill, None,
                                  [d_reg_type, d_industry, d_duration, d_revenue, d_social,
                                   d_buffer, d_client, d_team, d_edu, d_grad, d_order_cycle, d_materials])
                diag_btn.click(run_diag,
                               [d_reg_type, d_industry, d_duration, d_revenue,
                                d_social, d_buffer, d_client, d_team, d_edu, d_grad, d_order_cycle,
                                d_materials, region_state],
                               [d_cockpit, d_report])

                def do_reset_diag():
                    """诊断 Tab 重新开始：清空所有输入 + 重置驾驶舱与报告。"""
                    blanks = [""] * 12
                    return blanks + [render_cockpit(bp.empty_profile(), "wenzhou", partial=True), ""]
                reset_diag_btn.click(do_reset_diag, None,
                                     [d_reg_type, d_industry, d_duration, d_revenue, d_social,
                                      d_buffer, d_client, d_team, d_edu, d_grad, d_order_cycle,
                                      d_materials, d_cockpit, d_report])

            # ---------- Tab3 合规问答 ----------
            with gr.Tab("③ 经营合规问答"):
                gr.Markdown("> **场景**：问税务/合同/开票/社保问题。已接入 AI 深度回答 + 实时联网搜索，离线时由内置知识库兜底。")
                c_chat = gr.Chatbot(height=430, label="")  # label="" 去掉 gradio 默认的 "Chatbot" 标题框
                with gr.Row():
                    c_input = gr.Textbox(placeholder="例如：一人公司报税有什么要注意的？", scale=6, container=False)
                    c_btn = gr.Button("发送", elem_id="maple-btn", scale=1)
                with gr.Row():
                    c_suggest_btn = gr.Button("💡 让模型推荐该问的问题", elem_id="prefill-btn", size="sm")
                    c_suggest_out = gr.HTML()
                c_btn.click(compliance_chat, [c_input, c_chat], [c_chat, c_input])
                c_input.submit(compliance_chat, [c_input, c_chat], [c_chat, c_input])
                c_suggest_btn.click(suggest_compliance_questions, None, [c_suggest_out])

            # ---------- Tab4 政策导入 ----------
            with gr.Tab("④ 政策导入（多地区扩展）"):
                gr.Markdown("> **场景**：你有某地真实政策原文 → 粘贴给 AI → 自动结构化入库该地区 → 地区下拉即可切换使用。\n\n⚠️ AI 结构化可能出错，入库后请人工核对与官方文件一致。")
                with gr.Row():
                    imp_region = gr.Textbox(label="目标地区", value="杭州", placeholder="如：杭州 / 北京 / 广州")
                    imp_btn = gr.Button("入库政策", elem_id="maple-btn")
                imp_text = gr.Textbox(label="政策原文", lines=8,
                                      placeholder="粘贴政策原文（含名称、金额、资格条件、申请材料、来源）…")
                imp_result = gr.Markdown()
                # 热加载：入库成功后顶部地区输入框填入库地区 + 共享 region_state 同步（本次会话即用，无需重启）
                imp_btn.click(import_policy, [imp_region, imp_text],
                              [imp_result, region_input, region_state])

            # ---------- Tab5 政策动态 · 地区对比 ----------
            with gr.Tab("⑤ 政策动态 · 地区对比"):
                gr.Markdown("> **场景**：实时搜索任意地区的最新政策（官方优先、来源可溯源）。搜索词**三档**：留空用 AI 自动生成；或输入指定关键词精准搜；或描述需求让 AI 提炼关键词。搜到的政策可**一键入库**本地库，之后离线也能用。")
                with gr.Row():
                    with gr.Column(scale=7):
                        dyn_region = gr.Textbox(label="地区", value="杭州",
                                                placeholder="如：杭州 / 北京 / 重庆")
                        dyn_keyword = gr.Textbox(label="搜索关键词（留空用 AI 自动生成）",
                                                 placeholder="如：工位注册 / Token券 / 创业担保贷款 / 一次性创业补贴 …（留空自动）",
                                                 info="留空 → AI 自动生成；输入 → 想搜什么就搜什么")
                        dyn_desc = gr.Textbox(label="💬 描述你想查什么（可选，AI 提炼关键词）",
                                              placeholder="如：我想看杭州怎么支持一人公司 / 小微企业有什么税收优惠")
                        with gr.Row():
                            dyn_ai_kw_btn = gr.Button("💬 AI 生成关键词", elem_id="prefill-btn")
                            dyn_search_btn = gr.Button("🔍 开始搜索", elem_id="maple-btn")
                        dyn_result = gr.Markdown()
                        dyn_import_btn = gr.Button("✅ 一键入库到本地库（人工核对后）", elem_id="reset-btn")
                        dyn_import_msg = gr.Markdown()
                        # 隐藏态：存当前搜索结果（可入库 policies）+ 当前搜索地区
                        dyn_policies = gr.State([])
                        dyn_code = gr.State("hangzhou")
                    with gr.Column(scale=5):
                        gr.Markdown("### 🔁 地区对比（同一画像）")
                        cmp_a = gr.Textbox(label="地区 A", value="温州", placeholder="如：温州 / 杭州")
                        cmp_b = gr.Textbox(label="地区 B", value="杭州", placeholder="如：温州 / 杭州")
                        cmp_btn = gr.Button("🔁 对比两地区", elem_id="maple-btn")
                        cmp_result = gr.Markdown()

                def do_ai_kw(desc, region):
                    """描述需求 → AI 提炼搜索关键词回填。无 LLM 给提示。"""
                    desc = (desc or "").strip()
                    region = (region or "杭州").strip()
                    if not desc:
                        return "请输入你的需求描述（如：我想看杭州怎么支持一人公司）。"
                    if not api_client.is_api_available():
                        return "未配置 LLM API，请直接在上方「搜索关键词」框手动输入关键词。"
                    kw = policy_searcher.generate_keyword_from_desc(
                        desc, region, api_client.generate)
                    if kw:
                        return kw
                    return "AI 未能提炼出关键词，请尝试手动输入或换一种描述。"

                dyn_ai_kw_btn.click(do_ai_kw, [dyn_desc, dyn_region], [dyn_keyword])
                dyn_search_btn.click(do_dyn_search,
                                     [dyn_region, dyn_keyword, dyn_desc],
                                     [dyn_result, dyn_policies, dyn_code, dyn_import_msg])
                dyn_import_btn.click(do_import_searched,
                                     [dyn_policies, dyn_code],
                                     [dyn_import_msg, region_input, region_state])
                cmp_btn.click(compare_regions, [cmp_a, cmp_b], [cmp_result])

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
