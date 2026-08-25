"""Light UI system for the Project Kairos.

Design language: calm neutral slate surfaces, near-black ink for primary
actions, no decorative accent colours. Light is forced everywhere, including
BaseWeb inputs and dropdown popovers, so nothing renders dark.
"""
from __future__ import annotations

import streamlit as st

try:
    import markdown2
except Exception:  # pragma: no cover
    markdown2 = None

# ---- Preline UI design tokens (Tailwind gray scale + blue-600 primary) ----
INK = "#1F2937"       # gray-800 — headings / primary text
BODY = "#4B5563"      # gray-600 — body text
MUTED = "#6B7280"     # gray-500 — secondary
FAINT = "#9CA3AF"     # gray-400 — tertiary
LINE = "#E5E7EB"      # gray-200 — borders
LINE2 = "#F3F4F6"     # gray-100 — faint dividers / hover
PANEL = "#F3F4F6"     # gray-100 — filled inputs / stronger surfaces
SURFACE = "#F9FAFB"   # gray-50 — borderless card/panel fill (on a white canvas)
CARD = "#FFFFFF"
BG = "#FFFFFF"        # white app canvas — surfaces are distinguished by soft fills, not borders
ACCENT = "#2563EB"    # blue-600 — primary (Preline)
ACCENT_SOFT = "#EFF6FF"  # blue-50
ACCENT_DK = "#1D4ED8"    # blue-700 (hover)
GOOD = "#16A34A"; WARN = "#D97706"; BAD = "#DC2626"   # green-600 / amber-600 / red-600
# light borderless app-shell sidebar (soft gray-50 fill separates it from the white canvas)
NAV = "#F9FAFB"       # sidebar ground (gray-50)
NAV2 = "#EFF2F7"      # hover item
NAV_TXT = "#374151"   # gray-700 — nav text
NAV_MUT = "#6B7280"   # gray-500 — muted
NAV_LINE = "#EEF0F4"  # faint divider (used sparingly)

# Native, always-available premium font stacks — no network dependency (remote webfonts
# were silently failing behind corporate networks and dropping the whole app to an ugly
# serif fallback). On macOS this resolves to SF Pro, on Windows to Segoe UI.
SANS = ('-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "Inter", Roboto, '
        '"Helvetica Neue", Arial, sans-serif')
DISPLAY = ('-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", "Inter", Roboto, '
           '"Helvetica Neue", Arial, sans-serif')
MONO = 'ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace'

CSS = f"""
<style>

:root {{ color-scheme: light !important; }}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main {{
  background-color:{BG} !important; }}
#MainMenu, header[data-testid="stHeader"], footer {{ visibility:hidden; height:0; }}
[data-testid="stToolbar"] {{ display:none; }}
/* work canvas: capped + centered so the full app (264px rail + content) frames to ~1440 */
.block-container {{ padding-top:2.6rem; padding-bottom:5rem; max-width:1180px; margin:0 auto;
  padding-left:3rem; padding-right:3rem; background:transparent !important; }}

/* persistent left nav, never collapses, fixed width — force it visible even when
   Streamlit tries to auto-collapse it at narrow/HiDPI viewports */
[data-testid="stSidebar"] {{ min-width:264px !important; max-width:264px !important;
  transform:none !important; margin-left:0 !important; left:0 !important; visibility:visible !important; }}
[data-testid="stSidebar"][aria-expanded="false"] {{ margin-left:0 !important; transform:none !important; }}
[data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"], button[data-testid="baseButton-headerNoPadding"] {{ display:none !important; }}
[data-testid="stSidebarResizeHandle"] {{ display:none !important; }}

html, body, [class*="css"], .stMarkdown, p, span, div, label, li, input, textarea, button {{
  font-family:{SANS};
  color:{BODY}; -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
}}
.stMarkdown p, .stMarkdown li {{ font-size:14.5px; line-height:1.65; }}
/* ---- type scale (consistent H1/H2/H3/H4 across the app), system display face ---- */
h1,h2,h3,h4,.cs-hero .h,.cs-header .cs-title,.cs-steph {{
  font-family:{DISPLAY}; color:{INK}; font-weight:700; }}
.main h1 {{ font-size:28px; font-weight:700; letter-spacing:-.02em; line-height:1.2; margin:.3rem 0 .7rem; }}
.main h2 {{ font-size:20px; font-weight:600; letter-spacing:-.015em; margin:1.5rem 0 .6rem; }}
.main h3 {{ font-size:16px; font-weight:600; letter-spacing:-.01em; margin:1.15rem 0 .45rem; }}
.main h4 {{ font-size:12.5px; font-weight:700; letter-spacing:.5px; text-transform:uppercase;
  color:{MUTED}; margin:.7rem 0 .3rem; }}
a {{ color:{ACCENT}; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
::selection {{ background:{ACCENT_SOFT}; }}
hr {{ border:none !important; border-top:1px solid {LINE} !important; margin:1.15rem 0 !important; }}
/* generous, calm vertical rhythm - breathing room between blocks */
[data-testid="stVerticalBlock"] {{ gap:1rem; }}
[data-testid="stCaptionContainer"], .stCaption {{ color:{MUTED} !important; }}
[data-testid="stCaptionContainer"] p {{ font-size:12.5px !important; line-height:1.55 !important; color:{MUTED} !important; }}

/* ============================ slim context strip (replaces the old header card) ==== */
.cs-context {{ display:flex; flex-wrap:wrap; gap:16px; align-items:center;
  margin:0 0 4px; padding:0; }}
.cs-chip {{ display:inline-flex; align-items:baseline; gap:6px; font-size:12px; white-space:nowrap; }}
.cs-chip .k {{ color:{FAINT}; font-weight:600; text-transform:uppercase; font-size:9.5px; letter-spacing:.8px; }}
.cs-chip .v {{ color:{INK}; font-weight:600; font-size:12.5px; }}

/* ============================ step heading ============================ */
.cs-stepk {{ font-size:10.5px; font-weight:700; letter-spacing:1.3px; text-transform:uppercase;
  color:{ACCENT}; margin-bottom:5px; }}
.cs-steph {{ font-size:26px; font-weight:700; color:{INK}; margin:0 0 12px; letter-spacing:-.02em; line-height:1.18; }}
.cs-progress {{ height:4px; background:{LINE2}; border-radius:999px;
  margin:0 0 20px; overflow:hidden; }}
/* one consistent in-body section header used across every step */
.cs-section {{ margin:20px 0 8px; }}
.cs-section .t {{ font-size:15px; font-weight:700; color:{INK}; letter-spacing:-.01em; }}
.cs-section .s {{ font-size:12.5px; color:{MUTED}; margin-top:2px; line-height:1.5; }}
.cs-progress > i {{ display:block; height:100%; border-radius:999px; transition:width .35s cubic-bezier(.4,0,.2,1);
  background:{ACCENT}; }}

/* ============================ dark navigation rail ============================ */
[data-testid="stSidebar"] {{ background:{NAV} !important; border-right:none; box-shadow:none; }}
[data-testid="stSidebar"] * {{ color:{NAV_TXT}; }}
[data-testid="stSidebar"] .block-container {{ padding:1.4rem 1rem 1.2rem; }}
/* full-height rail so the compact status + settings cluster sticks to the bottom */
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div:first-child {{
  display:flex; flex-direction:column; min-height:calc(100vh - 3rem); }}
[data-testid="stSidebar"] hr {{ border-top:1px solid {NAV_LINE} !important; margin:1rem 0 !important; }}
/* compact status line — small dots + one-word state, pushed to the bottom of the rail */
.cs-railstat {{ margin-top:auto; padding-top:14px; border-top:1px solid {NAV_LINE};
  display:flex; flex-direction:column; gap:7px; margin-bottom:10px; }}
.cs-railstat span {{ display:flex; align-items:center; gap:8px; font-size:11.5px; color:{NAV_MUT}; }}
.cs-railstat i {{ width:7px; height:7px; border-radius:50%; flex:0 0 7px; }}
[data-testid="stSidebar"] label {{ color:{NAV_MUT} !important; font-size:10.5px !important;
  text-transform:uppercase; letter-spacing:.7px; font-weight:600; }}
/* sidebar selectbox (light Preline) */
[data-testid="stSidebar"] [data-baseweb="select"] > div {{ background:{CARD} !important;
  border-color:{LINE} !important; color:{INK} !important; border-radius:8px !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] div, [data-testid="stSidebar"] [data-baseweb="select"] span {{ color:{INK} !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] svg {{ fill:{MUTED} !important; }}
/* sidebar buttons (light Preline secondary) */
[data-testid="stSidebar"] .stButton > button {{ background:{CARD} !important; color:{INK} !important;
  border:1px solid {LINE} !important; box-shadow:0 1px 2px rgba(0,0,0,.04) !important; font-weight:500 !important; }}
[data-testid="stSidebar"] .stButton > button:hover {{ background:{PANEL} !important; color:{INK} !important; border-color:#D1D5DB !important; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ color:{NAV_MUT} !important; }}

.cs-brand {{ display:flex; align-items:center; gap:10px; padding-top:2px; }}
.cs-brand .m {{ width:32px; height:32px; border-radius:8px;
  background:{ACCENT}; color:#fff;
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:14px;
  box-shadow:0 1px 2px rgba(0,0,0,.08); }}
.cs-brand .t {{ font-size:15px; font-weight:600; color:{INK} !important; letter-spacing:-.01em; }}
.cs-brand-sub {{ font-size:9.5px; color:{NAV_MUT} !important; margin:5px 0 22px 42px; text-transform:uppercase;
  letter-spacing:.9px; font-weight:600; }}
/* vertical nav (Preline app-shell): rounded item, blue-soft active, no spine clutter */
.cs-step {{ display:flex; align-items:center; gap:11px; padding:8px 10px; border-radius:8px; margin:2px 0;
  position:relative; transition:background .12s ease; }}
.cs-step:hover:not(.now) {{ background:{LINE2}; }}
.cs-step .n {{ width:22px; height:22px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:10.5px; font-weight:600; flex:0 0 22px;
  background:{PANEL}; color:{MUTED}; border:1px solid {LINE}; transition:all .15s ease; }}
.cs-step .lbl {{ font-size:13px; color:{NAV_TXT}; letter-spacing:-.005em; }}
.cs-step.done .n {{ background:{ACCENT_SOFT}; color:{ACCENT}; border-color:#BFDBFE; }}
.cs-step.done .lbl {{ color:{NAV_TXT}; }}
.cs-step.now {{ background:{ACCENT_SOFT}; }}
.cs-step.now .n {{ background:{ACCENT}; color:#fff; border-color:{ACCENT}; }}
.cs-step.now .lbl {{ color:{ACCENT_DK}; font-weight:600; }}

/* ============================ reasoning widget (borderless soft panel) ============================ */
.cs-reason {{ background:{SURFACE}; border:none; border-radius:12px;
  padding:16px 18px; box-shadow:none; position:sticky; top:16px; }}
.cs-reason .rh {{ font-size:10.5px; font-weight:700; letter-spacing:1px; text-transform:uppercase;
  color:{FAINT}; margin-bottom:9px; display:flex; align-items:center; gap:7px; }}
.cs-reason .rt {{ font-size:14.5px; font-weight:700; color:{INK}; margin:0 0 9px; line-height:1.3; letter-spacing:-.01em; }}
.cs-reason .rb, .cs-reason .rb p, .cs-reason .rb li {{ font-size:12.6px; line-height:1.62; color:{BODY};
  hyphens:none; overflow-wrap:break-word; word-break:normal; }}
.cs-reason .rb strong {{ color:{INK}; font-weight:600; }}
.cs-reason .rb ul {{ margin:6px 0; padding-left:16px; }}
.cs-reason .rb li {{ margin-bottom:5px; }}
.cs-reason .rb code {{ background:{CARD}; border:none; padding:1px 6px; border-radius:5px;
  font-size:11.5px; color:{INK}; }}
.cs-pills {{ margin-top:13px; padding-top:11px; border-top:none; }}
.cs-pill {{ display:inline-block; font-size:9.5px; font-weight:600; color:{MUTED}; letter-spacing:.2px;
  background:{CARD}; border:none; padding:3px 9px; border-radius:6px; margin:0 4px 5px 0; }}

/* ============================ buttons ============================ */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
[data-testid="stBaseButton-secondary"] {{
  border-radius:8px !important; font-weight:500 !important; font-size:13.5px !important;
  border:1px solid {LINE} !important; background:{CARD} !important; color:{INK} !important;
  padding:.55rem 1.1rem !important; min-height:2.6rem !important; line-height:1.2 !important;
  white-space:nowrap !important; box-shadow:0 1px 2px rgba(16,24,40,.05) !important;
  transition:background .13s ease, border-color .13s ease, box-shadow .13s ease !important; }}
.stButton > button *, .stDownloadButton > button *, .stFormSubmitButton > button *,
[data-testid="stBaseButton-secondary"] *, [data-testid="stBaseButton-primary"] * {{
  color:inherit !important; fill:inherit !important; white-space:nowrap !important; margin:0 !important; }}
.stButton > button:hover, .stDownloadButton > button:hover {{
  border-color:#D1D5DB !important; background:{PANEL} !important; color:{INK} !important; }}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
  outline:none !important; box-shadow:0 0 0 3px {ACCENT_SOFT} !important; border-color:{ACCENT} !important; }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"],
[data-testid="stBaseButton-primary"] {{
  background:{ACCENT} !important; color:#fff !important;
  border:1px solid {ACCENT} !important; font-weight:500 !important;
  box-shadow:0 1px 2px rgba(16,24,40,.08) !important; }}
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{
  background:{ACCENT_DK} !important; border-color:{ACCENT_DK} !important; color:#fff !important; }}
.stButton > button:disabled, [data-testid="stBaseButton-primary"]:disabled,
[data-testid="stBaseButton-secondary"]:disabled {{
  background:{PANEL} !important; color:{FAINT} !important; border:1px solid {LINE} !important;
  box-shadow:none !important; opacity:1 !important; cursor:not-allowed !important; }}
.stButton > button:disabled * {{ color:{FAINT} !important; }}

/* ============================ INPUTS — borderless soft fill ============================ */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"],
.stTextInput input, .stTextArea textarea, .stNumberInput input,
[data-baseweb="select"] input, [data-baseweb="textarea"] {{
  background-color:{PANEL} !important; color:{INK} !important;
  border:1px solid transparent !important; border-radius:8px !important; }}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {{ color:{FAINT} !important; }}
/* focus: lift to white + blue ring, no hard border */
.stTextInput div[data-baseweb="input"]:focus-within, .stTextArea div[data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within {{
  background-color:{CARD} !important;
  border-color:{ACCENT} !important; box-shadow:0 0 0 3px {ACCENT_SOFT} !important; }}
[data-baseweb="select"] div, [data-baseweb="select"] span, [data-baseweb="select"] svg {{ color:{INK} !important; fill:{MUTED} !important; }}
/* dropdown popover menu */
[data-baseweb="popover"], [data-baseweb="menu"], ul[role="listbox"], [role="listbox"] {{
  background-color:{CARD} !important; border:1px solid {LINE} !important; }}
[role="option"], li[role="option"] {{ background-color:{CARD} !important; color:{INK} !important; }}
[role="option"]:hover, li[role="option"]:hover, [aria-selected="true"][role="option"] {{
  background-color:{PANEL} !important; color:{INK} !important; }}
/* multiselect tags — Preline soft blue badge */
[data-baseweb="tag"] {{ background-color:{ACCENT_SOFT} !important; color:{ACCENT_DK} !important;
  border:1px solid #BFDBFE !important; border-radius:6px !important; }}
[data-baseweb="tag"] span, [data-baseweb="tag"] svg {{ color:{ACCENT_DK} !important; fill:{ACCENT_DK} !important; }}
/* radio */
.stRadio [role="radiogroup"] label {{ color:{BODY} !important; }}
/* file uploader */
[data-testid="stFileUploaderDropzone"] {{ background:{PANEL} !important; border:1px dashed {LINE} !important; }}
[data-testid="stFileUploaderDropzone"] * {{ color:{BODY} !important; }}

/* ============================ misc ============================ */
[data-testid="stMetric"] {{ background:{SURFACE}; border:none; border-radius:12px;
  padding:14px 16px; box-shadow:none; }}
[data-testid="stMetricValue"] {{ color:{INK}; font-size:1.55rem; font-weight:700; letter-spacing:-.02em; }}
[data-testid="stMetricLabel"] {{ color:{MUTED}; }}
[data-testid="stMetricLabel"] p {{ font-size:12px !important; font-weight:600 !important;
  text-transform:uppercase; letter-spacing:.3px; color:{MUTED} !important; }}
/* --- tabs: borderless pill tabs (soft blue active, no underline, no divider) --- */
.stTabs [data-baseweb="tab-list"] {{
  gap:6px !important; border-bottom:none !important;
  margin-bottom:8px !important; flex-wrap:wrap !important; row-gap:4px !important; }}
.stTabs [data-baseweb="tab"] {{
  font-weight:500 !important; font-size:13.5px !important; color:{BODY} !important;
  padding:7px 14px !important; border-radius:8px !important;
  white-space:nowrap !important; background:transparent !important; border:none !important; }}
.stTabs [data-baseweb="tab"] * {{ color:inherit !important; font-weight:inherit !important; }}
.stTabs [data-baseweb="tab"]:hover {{ background:{SURFACE} !important; color:{INK} !important; }}
.stTabs [data-baseweb="tab"][aria-selected="true"] {{
  color:{ACCENT_DK} !important; font-weight:600 !important; background:{ACCENT_SOFT} !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none !important; }}
.stTabs [data-baseweb="tab-panel"] {{ padding-top:14px !important; }}
div[data-testid="stExpander"] {{ border:none !important; border-radius:12px; margin-bottom:8px;
  box-shadow:none !important; overflow:hidden; background:{SURFACE}; }}
div[data-testid="stExpander"] summary {{ padding:12px 16px !important; }}
div[data-testid="stExpander"] summary:hover {{ background:{LINE2} !important; }}
div[data-testid="stExpander"] summary p, div[data-testid="stExpander"] summary span {{
  font-weight:600 !important; color:{INK} !important; font-size:13.5px !important; }}
/* FAQ section header — sets the accordion apart from body prose */
.cs-faq-head {{ font-family:{DISPLAY}; font-weight:700; font-size:20px;
  color:{INK}; margin:26px 0 2px; padding-top:16px; border-top:1px solid {LINE};
  display:flex; align-items:center; gap:10px; }}
.cs-faq-head::before {{ content:""; width:4px; height:19px; border-radius:3px; background:{ACCENT}; }}
.cs-faq-sub {{ color:{MUTED}; font-size:13px; margin:0 0 12px 15px; }}
/* ============================ pre-flight quality panel + gate chips ============================ */
.cs-qhead {{ display:flex; align-items:center; gap:9px; font-size:14px; color:{INK};
  letter-spacing:-.01em; margin:1px 0 12px; flex-wrap:wrap; }}
.cs-qhead b {{ font-weight:750; }}
.cs-qdot {{ width:9px; height:9px; border-radius:50%; flex:0 0 9px; }}
.cs-q-good .cs-qdot {{ background:{GOOD}; box-shadow:0 0 0 4px {GOOD}22; }}
.cs-q-warn .cs-qdot {{ background:{WARN}; box-shadow:0 0 0 4px {WARN}22; }}
.cs-q-bad  .cs-qdot {{ background:{BAD};  box-shadow:0 0 0 4px {BAD}22; }}
.cs-qmeta {{ margin-left:auto; font-size:12px; color:{MUTED}; font-weight:500;
  font-variant-numeric:tabular-nums; }}
.cs-gates {{ display:flex; flex-wrap:wrap; gap:7px; }}
.cs-gate {{ display:inline-flex; align-items:center; gap:6px; font-size:11.5px; font-weight:600;
  padding:5px 11px; border-radius:8px; border:1px solid transparent; white-space:nowrap;
  letter-spacing:.1px; cursor:default; transition:transform .1s ease; }}
.cs-gate:hover {{ transform:translateY(-1px); }}
.cs-gate-pass {{ background:#E9F7F0; color:#0B7A54; border-color:#CDEBDF; }}
.cs-gate-warn {{ background:#FBF3E2; color:#8A6410; border-color:#F1E2C0; }}
.cs-gate-fail {{ background:#FBEBEC; color:#B0293A; border-color:#F3D3D6; }}

/* alerts: prominent + well-padded so errors/success read at a glance
   (Streamlit tints the background per kind - red/amber/green/blue - we keep that
   and add generous padding, a rounded shape, and readable text) */
[data-testid="stAlert"] {{ border-radius:10px !important; padding:12px 15px !important;
  box-shadow:none !important; }}
[data-testid="stAlert"] p {{ font-size:13.5px !important; line-height:1.55 !important; font-weight:500 !important; }}
/* container cards (st.container(border=True)) — BORDERLESS: soft gray-50 fill, no border, no shadow */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius:14px !important;
  border:none !important; background:{SURFACE} !important; box-shadow:none !important; }}
hr {{ border-color:{LINE} !important; }}
.stSelectbox label, .stTextInput label, .stTextArea label, .stMultiSelect label, .stRadio label {{
  font-weight:600 !important; color:{INK} !important; }}
[data-testid="stDataFrame"] {{ border:1px solid {LINE}; border-radius:10px; }}
/* --- code / JSON / popover: Streamlit defaults can render dark, force light & readable --- */
[data-testid="stCode"], [data-testid="stCode"] pre, .stCode, .stCode pre, pre {{
  background:{PANEL} !important; border:1px solid {LINE} !important; border-radius:9px !important; }}
[data-testid="stCode"] code, [data-testid="stCode"] pre *, .stCode pre *, pre code, pre span {{
  color:{INK} !important; background:transparent !important; }}
[data-testid="stJson"] {{ background:{PANEL} !important; border:1px solid {LINE} !important;
  border-radius:9px !important; padding:4px 10px !important; }}
[data-testid="stJson"] * {{ color:{INK} !important; }}
[data-testid="stPopoverBody"], [data-testid="stPopoverBody"] > div {{ background:{CARD} !important; }}
[data-testid="stPopoverBody"] p, [data-testid="stPopoverBody"] span,
[data-testid="stPopoverBody"] li, [data-testid="stPopoverBody"] div {{ color:{BODY} !important; }}
[data-testid="stPopoverBody"] strong {{ color:{INK} !important; }}

/* --- intent badges --- */
.cs-ib {{ display:inline-block; font-size:10px; font-weight:700; letter-spacing:.4px;
  padding:2px 8px; border-radius:6px; text-transform:uppercase; }}
.cs-ib.informational {{ background:#E4EEFB; color:#1E4E8C; }}
.cs-ib.commercial {{ background:#FBF0DA; color:#8A6410; }}
.cs-ib.transactional {{ background:#E3F2E8; color:#1E6B3A; }}
.cs-ib.navigational {{ background:#EEE7F7; color:#5B3B8C; }}
.cs-ib.local {{ background:#DCF2F0; color:#106B62; }}
.cs-ib.other {{ background:#EDF1F5; color:#334155; }}
/* optimization-plan bucket cards */
.cs-bucket {{ border:1px solid {LINE}; border-radius:12px; padding:14px 16px; margin-bottom:10px; }}
.cs-bucket .bh {{ font-family:{SANS}; font-weight:700; font-size:13px;
  letter-spacing:.4px; text-transform:uppercase; margin-bottom:6px; display:flex; align-items:center; gap:8px; }}
.cs-bucket.retain {{ border-left:4px solid #1E6B3A; }} .cs-bucket.retain .bh {{ color:#1E6B3A; }}
.cs-bucket.enhance {{ border-left:4px solid #8A6410; }} .cs-bucket.enhance .bh {{ color:#8A6410; }}
.cs-bucket.prune {{ border-left:4px solid #9A2B2B; }} .cs-bucket.prune .bh {{ color:#9A2B2B; }}
.cs-bucket.create {{ border-left:4px solid #1E4E8C; }} .cs-bucket.create .bh {{ color:#1E4E8C; }}
.cs-bucket .bb, .cs-bucket .bb li, .cs-bucket .bb p {{ font-size:12.8px; line-height:1.55; color:{BODY}; }}

/* --- query fan-out cards --- */
.cs-forationale {{ background:{ACCENT_SOFT}; border:1px solid #E0E2FB;
  border-radius:11px; padding:11px 15px; margin:6px 0 14px; font-size:13px; color:{BODY}; line-height:1.55; }}
.cs-forationale b {{ color:{INK}; }}
.cs-foq {{ padding:3px 0 7px; }}
.cs-foq .q {{ font-size:14px; font-weight:650; color:{INK}; line-height:1.4; }}
.cs-foq .bar {{ height:5px; background:{LINE2}; border-radius:999px; margin:7px 0 6px; overflow:hidden; max-width:300px; }}
.cs-foq .bar > i {{ display:block; height:100%; border-radius:999px;
  background:{ACCENT}; }}
.cs-foq .meta {{ font-size:11px; color:{MUTED}; margin-bottom:4px; letter-spacing:.1px; }}
.cs-foq .meta b {{ color:{BODY}; }}
.cs-foq .rz {{ font-size:12.3px; color:{BODY}; line-height:1.5; margin:2px 0; }}
.cs-foq .rz b {{ color:{INK}; }}
.cs-foq .rz a {{ color:{ACCENT}; text-decoration:underline; }}
.cs-cov {{ display:inline-block; font-size:10.5px; font-weight:600; border-radius:6px; padding:1px 7px; margin-left:6px; }}
.cs-foq .rz {{ font-size:12.3px; }}
/* --- Qforia fan-out table (grouped under each original query) --- */
.cs-foorig {{ margin:16px 0 4px; padding:8px 12px; background:{ACCENT_SOFT};
  border:1px solid #E0E2FB; border-radius:8px; line-height:1.45; }}
.cs-foorig .on {{ display:inline-block; font-size:10px; font-weight:800; letter-spacing:.5px;
  text-transform:uppercase; color:{ACCENT}; margin-right:6px; }}
.cs-foorig .oq {{ font-size:14.5px; font-weight:700; color:{INK}; }}
.cs-foorig .oc {{ font-size:11px; color:{MUTED}; margin-left:6px; white-space:nowrap; }}
.cs-foqq {{ font-size:13.3px; font-weight:600; color:{INK}; line-height:1.4; }}
.cs-fometa {{ font-size:12.2px; color:{BODY}; line-height:1.45; }}
.cs-qf {{ display:inline-block; font-size:10.5px; font-weight:700; border-radius:6px;
  padding:2px 8px; line-height:1.5; }}

/* --- impact badges + enhancement cards --- */
.cs-imp {{ display:inline-block; font-size:10.5px; font-weight:700; letter-spacing:.3px; border-radius:6px;
  padding:2px 9px; text-transform:uppercase; }}
.cs-imp.high {{ background:#E4EEFB; color:#1E4E8C; }}
.cs-imp.medium {{ background:#EDF1F5; color:#334155; }}
.cs-imp.low {{ background:#F1F5F9; color:#64748B; }}
.cs-enh-t {{ font-size:15px; font-weight:700; color:{INK}; margin:0 0 6px; }}
.cs-enh-row {{ display:flex; gap:10px; font-size:13px; margin:3px 0; }}
.cs-enh-row .k {{ flex:0 0 60px; color:{MUTED}; font-weight:600; }}
.cs-enh-row .v {{ color:{BODY}; }}
.cs-ent {{ display:inline-block; font-size:12px; color:#3730A3; background:#EEF2FF; border:1px solid #E0E7FF;
  border-radius:8px; padding:4px 11px; margin:0 6px 6px 0; }}

/* --- PR calendar month cards --- */
.cs-cal .m {{ font-size:11px; font-weight:700; letter-spacing:.5px; text-transform:uppercase;
  color:{MUTED}; display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; }}
.cs-cal .t {{ font-size:14px; font-weight:700; color:{INK}; line-height:1.3; min-height:54px; }}
.cs-cal .meta {{ font-size:11px; color:{MUTED}; margin:6px 0 2px; }}
.cs-cal .sc {{ font-size:11px; font-weight:600; color:{BODY}; }}
.cs-cal .wy {{ font-size:11.5px; color:{MUTED}; line-height:1.45; margin-top:6px; }}

/* --- PR calendar: month header + per-story cards with score bars --- */
.cs-prmonth {{ font-size:12px; font-weight:700; letter-spacing:.7px; text-transform:uppercase;
  color:{ACCENT}; margin:18px 0 9px; padding-bottom:6px; border-bottom:1px solid {LINE};
  display:flex; align-items:center; gap:8px; }}
.cs-rk {{ display:inline-block; font-size:9px; font-weight:700; text-transform:uppercase;
  letter-spacing:.4px; padding:1px 7px; border-radius:5px; }}
.cs-rk.primary {{ background:{INK}; color:#fff; }}
.cs-rk.secondary {{ background:{PANEL}; color:{MUTED}; border:1px solid {LINE}; }}
.cs-prti {{ font-size:14.5px; font-weight:700; color:{INK}; line-height:1.34; margin:9px 0 4px; min-height:38px; }}
.cs-prmt {{ font-size:11px; color:{MUTED}; margin-bottom:8px; }}
.cs-prscore {{ font-size:12.5px; font-weight:700; color:{INK}; margin:2px 0 6px; }}
.cs-prscore .pv {{ color:{ACCENT}; }}
.cs-prdim {{ display:flex; align-items:center; gap:7px; margin:3px 0; font-size:10px; color:{MUTED}; }}
.cs-prdim .lb {{ flex:0 0 94px; }}
.cs-prpips {{ display:flex; gap:3px; }}
.cs-prpips i {{ width:15px; height:6px; border-radius:2px; background:{LINE2};
  border:1px solid {LINE}; display:inline-block; }}
.cs-prpips i.on {{ background:{ACCENT}; border-color:{ACCENT}; }}
.cs-prwhy {{ font-size:11.8px; color:{BODY}; line-height:1.5; margin:8px 0 2px; }}
.cs-prwhy b {{ color:{INK}; }}
.cs-prg {{ font-size:11.5px; color:{BODY}; line-height:1.55; margin:3px 0; }}
.cs-prg b {{ color:{INK}; }}
.cs-prg .node {{ display:inline-block; font-family:{MONO}; font-size:10px;
  background:{PANEL}; border:1px solid {LINE}; color:{MUTED}; border-radius:5px; padding:1px 6px; margin:2px 4px 0 0; }}

/* --- landing / objective hero + option cards --- */
.cs-hero {{ margin:2px 0 26px; }}
.cs-hero .h {{ font-size:32px; font-weight:700; letter-spacing:-.025em; color:{INK}; margin:0 0 11px; line-height:1.08; max-width:15ch; }}
.cs-hero .s {{ font-size:15px; color:{MUTED}; max-width:600px; line-height:1.6; margin:0; }}
.cs-opt {{ padding:6px 4px 12px; }}
.cs-opt .iconbadge {{ width:44px; height:44px; border-radius:12px; display:flex; align-items:center;
  justify-content:center; color:{ACCENT}; background:{ACCENT_SOFT};
  border:1px solid #DBEAFE; margin-bottom:14px; box-shadow:none; }}
.cs-opt .ic {{ font-size:24px; line-height:1; }}
.cs-opt .ti {{ font-size:17px; font-weight:700; color:{INK}; margin:2px 0 6px; letter-spacing:-.01em; }}
.cs-opt .de {{ font-size:13.5px; color:{MUTED}; line-height:1.6; min-height:64px; }}
.cs-hint {{ font-size:12.5px; color:{FAINT}; margin-top:18px; text-align:center; }}
.cs-hint b {{ color:{BODY}; }}
/* --- grounding-source square tiles (business step) --- */
.cs-srctile {{ border:1px solid {LINE}; border-radius:5px; background:{CARD}; padding:16px 16px 14px;
  margin-bottom:8px; min-height:88px; transition:border-color .12s ease, box-shadow .12s ease; }}
.cs-srctile.on {{ border-color:{ACCENT}; box-shadow:0 0 0 3px {ACCENT_SOFT}; }}
.cs-srctile .ti {{ font-size:15px; font-weight:700; color:{INK}; letter-spacing:-.01em; }}
.cs-srctile .de {{ font-size:12.5px; color:{MUTED}; margin-top:5px; line-height:1.5; }}
/* --- Preferences: grounded brand-voice / persona preset tiles --- */
.cs-preftile {{ border:1px solid {LINE}; border-radius:10px; background:{CARD}; padding:14px 15px 12px;
  margin-bottom:6px; min-height:96px; transition:border-color .12s ease, box-shadow .12s ease; }}
.cs-preftile.on {{ border-color:{ACCENT}; box-shadow:0 0 0 3px {ACCENT_SOFT}; background:{ACCENT_SOFT}; }}
.cs-preftile .ti {{ font-size:15px; font-weight:750; color:{INK}; letter-spacing:-.01em; }}
.cs-preftile .de {{ font-size:12.5px; color:{BODY}; margin-top:5px; line-height:1.5; }}
/* --- standard generation status bar (every AI/Odin step) --- */
.cs-genstamp {{ display:flex; align-items:center; gap:8px; font-size:12.5px; color:{MUTED};
  padding:8px 2px; }}
.cs-genstamp b {{ color:{BODY}; font-weight:650; }}
.cs-genstamp .dot {{ width:7px; height:7px; border-radius:999px; background:{GOOD};
  box-shadow:0 0 0 3px {GOOD}22; display:inline-block; }}
.cs-genhint {{ font-size:12px; color:{MUTED}; padding:9px 2px; }}
/* --- form field label + preference preview --- */
.cs-fieldlabel {{ font-size:12px; font-weight:700; color:{INK}; text-transform:uppercase;
  letter-spacing:.4px; margin:0 0 6px; }}
.cs-prefsum {{ font-size:13px; font-weight:650; color:{INK}; margin-bottom:6px; }}
.cs-prefbody {{ font-size:13px; color:{BODY}; line-height:1.6; }}
/* --- Choose Topic: wrap the faceted tabs in a big framed tile --- */
.cs-pickerwrap {{ border:1px solid {LINE}; border-radius:14px; background:{CARD};
  padding:6px 16px 12px; box-shadow:0 1px 2px rgba(20,27,46,.03); margin-top:6px; }}
/* --- section label (small caps eyebrow used inline) --- */
.cs-eyebrow {{ font-size:10.5px; font-weight:700; letter-spacing:1.1px; text-transform:uppercase;
  color:{FAINT}; margin:2px 0 8px; }}
/* --- lede: the one-line intro under a step heading --- */
.cs-lede {{ font-size:14.5px; color:{BODY}; line-height:1.6; margin:0 0 14px; max-width:720px; }}
.cs-lede b {{ color:{INK}; font-weight:600; }}

/* --- standardized tag (one badge style used across the app) --- */
.cs-tag2 {{ display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:600;
  padding:2px 9px; border-radius:999px; border:1px solid {LINE}; background:{PANEL}; color:{BODY};
  white-space:nowrap; letter-spacing:.1px; }}
.cs-tag2.accent {{ background:{ACCENT_SOFT}; border-color:#E0E2FB; color:{ACCENT}; }}
.cs-tag2.ink {{ background:{INK}; border-color:{INK}; color:#fff; }}

/* --- product footer: sticky at the bottom, spanning the content area, minimal --- */
.cs-footer {{ position:fixed; left:264px; right:0; bottom:0; z-index:40;
  padding:10px 3rem; border-top:1px solid {LINE}; background:rgba(247,248,251,.86);
  backdrop-filter:saturate(1.2) blur(10px); -webkit-backdrop-filter:saturate(1.2) blur(10px);
  display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; }}
.cs-footer .l {{ display:flex; align-items:center; gap:9px; font-size:12.5px; color:{MUTED}; }}
.cs-footer .l .m {{ width:20px; height:20px; border-radius:6px; background:{ACCENT};
  color:#fff; display:inline-flex; align-items:center; justify-content:center; font-weight:800; font-size:10px; }}
.cs-footer .l b {{ color:{INK}; font-weight:700; }}
.cs-footer .r {{ font-size:12px; color:{FAINT}; }}
.cs-footer .r .dot {{ color:{FAINT}; margin:0 5px; }}
.cs-footer .r a {{ color:{ACCENT}; font-weight:700; text-decoration:none; }}
.cs-footer .r a:hover {{ text-decoration:underline; }}

/* ================= GLOBAL BORDERLESS PASS (surfaces read via soft fills + spacing, never lines) ================= */
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"], [data-testid="stMetric"],
[data-testid="stAlert"], [data-testid="stNotification"], [data-testid="stDataFrame"], [data-testid="stTable"],
[data-testid="stJson"], [data-testid="stCode"], [data-testid="stCode"] pre, .stCode, .stCode pre, pre,
[data-testid="stFileUploaderDropzone"], [data-baseweb="tag"],
.cs-bucket, .cs-pickerwrap, .cs-srctile, .cs-preftile, .cs-forationale, .cs-foorig,
.cs-gate, .cs-tag2, .cs-ent, .cs-qf, .cs-cov, .cs-step .n, .cs-reason .rb code, .cs-pill {{
  border:none !important; }}
.cs-faq-head {{ border-top:none !important; }}
.cs-bucket {{ border-left:none !important; background:{SURFACE} !important; }}
.cs-pills, .cs-chips, .cs-chips-empty, .cs-prmonth {{ border-top:none !important; border-bottom:none !important; }}
/* filled surfaces stay legible on the white canvas without a border */
[data-testid="stCode"], [data-testid="stCode"] pre, .stCode, pre, [data-testid="stJson"] {{ background:{SURFACE} !important; }}
[data-testid="stDataFrame"], [data-testid="stFileUploaderDropzone"] {{ background:{SURFACE} !important; }}
.cs-srctile, .cs-preftile, .cs-pickerwrap {{ background:{SURFACE} !important; box-shadow:none !important; }}
.cs-srctile.on, .cs-preftile.on {{ background:{ACCENT_SOFT} !important; box-shadow:none !important; }}
/* secondary / sidebar buttons -> soft filled (borderless), gray-100 so they read on gray-50 cards */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
[data-testid="stBaseButton-secondary"], [data-testid="stSidebar"] .stButton > button {{
  border:none !important; background:{PANEL} !important; color:{INK} !important; }}
.stButton > button:hover, .stDownloadButton > button:hover,
[data-testid="stSidebar"] .stButton > button:hover {{ background:{LINE} !important; border:none !important; }}
/* primary keeps its solid blue fill (no visible border) */
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"],
[data-testid="stBaseButton-primary"] {{ border:none !important; background:{ACCENT} !important; }}
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{ background:{ACCENT_DK} !important; }}
/* dividers: pure spacing, no rule */
hr {{ border:none !important; background:transparent !important; height:0 !important; margin:16px 0 !important; }}
</style>
"""

INTENTS = ("informational", "commercial", "transactional", "navigational", "local")


def intent_badge(intent: str) -> str:
    cls = (intent or "").strip().lower()
    if cls not in INTENTS:
        cls = "other"
    return f'<span class="cs-ib {cls}">{(intent or "-")}</span>'


def _esc(s: str) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def subgraph_svg(nodes: list, relations: list, width: int = 460, height: int = 300) -> str:
    """Render a compact radial CMG subgraph (nodes + labelled relations) as SVG."""
    import math

    norm = []
    for n in (nodes or [])[:7]:
        if isinstance(n, dict):
            norm.append({"id": str(n.get("id", "")), "label": str(n.get("label") or n.get("id") or "")})
        else:
            norm.append({"id": str(n), "label": str(n)})
    if not norm:
        return "<div style='color:#94A3B8;font-size:12px'>No CMG nodes cited for this block.</div>"

    cx, cy, R = width / 2, height / 2, min(width, height) / 2 - 46
    by_key = {}
    pos = {}
    for i, nd in enumerate(norm):
        ang = -math.pi / 2 + 2 * math.pi * i / len(norm)
        x, y = cx + R * math.cos(ang), cy + R * math.sin(ang)
        if len(norm) == 1:
            x, y = cx, cy
        pos[i] = (x, y)
        by_key[nd["id"].lower()] = i
        by_key[nd["label"].lower()] = i

    def find(ref):
        r = str(ref or "").lower()
        if r in by_key:
            return by_key[r]
        for k, idx in by_key.items():
            if r and (r in k or k in r):
                return idx
        return None

    edges = []
    for rel in (relations or [])[:12]:
        if isinstance(rel, dict):
            s, t, lab = rel.get("source"), rel.get("target"), rel.get("rel") or rel.get("type") or ""
        else:
            continue
        si, ti = find(s), find(t)
        if si is not None and ti is not None and si != ti:
            edges.append((si, ti, str(lab)))

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="Helvetica Neue,Arial,sans-serif">']
    for si, ti, lab in edges:
        x1, y1 = pos[si]; x2, y2 = pos[ti]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        parts.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                     f'stroke="#CBD5E1" stroke-width="1.4"/>')
        if lab:
            parts.append(f'<text x="{mx:.0f}" y="{my:.0f}" font-size="9" fill="#64748B" '
                         f'text-anchor="middle">{_esc(lab[:16])}</text>')
    for i, nd in enumerate(norm):
        x, y = pos[i]
        label = nd["label"]
        label = label if len(label) <= 20 else label[:19] + "…"
        w = max(58, min(150, 7 * len(label) + 16))
        parts.append(f'<rect x="{x-w/2:.0f}" y="{y-13:.0f}" width="{w}" height="26" rx="7" '
                     f'fill="#0F2740"/>')
        parts.append(f'<text x="{x:.0f}" y="{y+4:.0f}" font-size="10.5" fill="#fff" '
                     f'text-anchor="middle">{_esc(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def grounding_graph_svg(nodes: list, relations: list, width: int = 760, height: int = 470) -> str:
    """Whole-content knowledge graph: grounded entities clustered by type around an Odin
    hub, with the real 1-hop relationships drawn. Nodes cited in the draft are solid navy;
    retrieved-but-uncited nodes are hollow. `nodes` = [{id,label,type,used}]."""
    import math
    from collections import OrderedDict

    norm = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        lab = str(n.get("label") or n.get("id") or "").strip()
        if not lab:
            continue
        norm.append({"id": str(n.get("id") or lab), "label": lab,
                     "type": str(n.get("type") or "entity"), "used": bool(n.get("used"))})
    if not norm:
        return "<div style='color:#94A3B8;font-size:12px'>No grounded entities to display.</div>"

    groups: "OrderedDict[str, list]" = OrderedDict()
    for nd in norm:
        groups.setdefault(nd["type"], []).append(nd)
    ordered_types = sorted(groups, key=lambda t: -len(groups[t]))

    cx, cy = width / 2, height / 2
    R_out = min(width, height) / 2 - 60
    R_in = R_out - 46
    N = len(norm)
    pos, by_key, type_labels = {}, {}, []
    idx = 0
    a = -math.pi / 2
    for t in ordered_types:
        members = groups[t]
        sector = 2 * math.pi * len(members) / N
        for k, nd in enumerate(members):
            ang = a + sector * (k + 0.5) / len(members)
            r = R_out if k % 2 == 0 else R_in
            pos[idx] = (cx + r * math.cos(ang), cy + r * math.sin(ang), ang)
            by_key[nd["id"].lower()] = idx
            by_key[nd["label"].lower()] = idx
            nd["_i"] = idx
            idx += 1
        mid = a + sector / 2
        type_labels.append((cx + (R_out + 30) * math.cos(mid),
                            cy + (R_out + 30) * math.sin(mid), t, mid))
        a += sector

    def find(ref):
        r = str(ref or "").lower()
        if r in by_key:
            return by_key[r]
        for kk, ii in by_key.items():
            if r and (r in kk or kk in r):
                return ii
        return None

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="Helvetica Neue,Arial,sans-serif">']
    seen_e = set()
    for rel in relations or []:
        if not isinstance(rel, dict):
            continue
        si, ti = find(rel.get("source")), find(rel.get("target"))
        if si is None or ti is None or si == ti or (si, ti) in seen_e:
            continue
        seen_e.add((si, ti))
        x1, y1, _ = pos[si]; x2, y2, _ = pos[ti]
        parts.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                     f'stroke="#D6DEE8" stroke-width="1"/>')
    parts.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="24" fill="#0F2740"/>')
    parts.append(f'<text x="{cx:.0f}" y="{cy+4:.0f}" font-size="10" fill="#fff" '
                 f'text-anchor="middle">Odin</text>')
    for tx, ty, t, mid in type_labels:
        anc = "start" if math.cos(mid) >= 0 else "end"
        parts.append(f'<text x="{tx:.0f}" y="{ty:.0f}" font-size="8.5" fill="#94A3B8" '
                     f'text-anchor="{anc}" font-weight="700">'
                     f'{_esc(t.replace("_"," ").upper()[:18])}</text>')
    for nd in norm:
        x, y, ang = pos[nd["_i"]]
        used = nd["used"]
        parts.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="4.5" '
                     f'fill="{"#0F2740" if used else "#FFFFFF"}" '
                     f'stroke="{"#0F2740" if used else "#CBD5E1"}" stroke-width="1.3"/>')
        lab = nd["label"]
        lab = lab if len(lab) <= 20 else lab[:19] + "…"
        anc = "start" if math.cos(ang) >= 0 else "end"
        dx = 7 if math.cos(ang) >= 0 else -7
        parts.append(f'<text x="{x+dx:.0f}" y="{y+3:.0f}" font-size="8.5" '
                     f'fill="{"#0F172A" if used else "#64748B"}" '
                     f'font-weight="{"700" if used else "400"}" text-anchor="{anc}">{_esc(lab)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def run_with_progress(fn, *, expected_seconds: float, label: str = "Working…"):
    """Run a blocking call in a worker thread while animating a real progress bar with a
    live ETA countdown. `claude -p` can't stream progress, so the bar is time-based: it
    advances toward `expected_seconds`, holds at 95% if the call overruns, and snaps to
    100% on completion. Returns fn()'s result (and re-raises its exception)."""
    import concurrent.futures as _cf
    import time as _t
    bar = st.progress(0.0, text=f"{label} · starting…")
    with _cf.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        start = _t.time()
        while not fut.done():
            el = _t.time() - start
            frac = min(0.95, el / max(1.0, expected_seconds))
            if el < expected_seconds:
                mins, secs = divmod(int(expected_seconds - el), 60)
                eta = f"~{mins}m {secs:02d}s left" if mins else f"~{secs}s left"
                bar.progress(frac, text=f"{label} · {eta}")
            else:
                bar.progress(0.95, text=f"{label} · wrapping up… ({int(el)}s elapsed)")
            _t.sleep(1.0)
        bar.progress(1.0, text=f"{label} · done ")
        return fut.result()


def gen_status_bar(*, has_data: bool, generated_at: str | None, generate_label: str,
                   key: str, regenerate_label: str = "Regenerate", busy_hint: str = "") -> str | None:
    """Standard generation control shown on every AI/Odin step.

    When nothing is cached: a single primary button (`generate_label`). When a cached
    result exists: a slim 'Generated <timestamp>' line with a quiet 'Regenerate' button.
    Returns 'generate', 'regenerate', or None. Keeps the pattern identical everywhere."""
    from lib import cache as _cache
    if not has_data:
        c1, c2 = st.columns([1.4, 3])
        clicked = c1.button(generate_label, type="primary", key=f"gen_{key}", use_container_width=True)
        if busy_hint:
            c2.markdown(f"<div class='cs-genhint'>{busy_hint}</div>", unsafe_allow_html=True)
        return "generate" if clicked else None
    ts = _cache.human_ts(generated_at)
    c1, c2 = st.columns([3.4, 1])
    c1.markdown(f"<div class='cs-genstamp'><span class='dot'></span> Ready · generated "
                f"<b>{ts or 'earlier'}</b></div>", unsafe_allow_html=True)
    clicked = c2.button(f"{regenerate_label}", key=f"regen_{key}", use_container_width=True)
    return "regenerate" if clicked else None


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def header(chips: list[tuple[str, str]] | None):
    """Slim in-flow context strip: just the run's chosen settings as quiet inline tags.
    No card, no repeated branding (the rail already brands the app), no placeholder."""
    chips = chips or []
    if not chips:
        return
    chip_html = "".join(
        f'<span class="cs-chip"><span class="k">{k}</span><span class="v">{v}</span></span>'
        for k, v in chips)
    st.markdown(f'<div class="cs-context">{chip_html}</div>', unsafe_allow_html=True)


def footer():
    st.markdown("""
<div class="cs-footer">
  <div class="l"><span class="m">K</span><span><b>Project Kairos</b>: Grounded Content Intelligence</span></div>
  <div class="r"><a href="mailto:siddharth.p@milestoneinternet.com">Support</a>
    <span class="dot">·</span> Milestone Internet <span class="dot">·</span> KAIROS x Odin</div>
</div>
""", unsafe_allow_html=True)


def step_heading(label: str, current: int, total: int, show_title: bool = True):
    pct = int(round(100 * current / max(1, total - 1))) if total > 1 else 100
    title = f'<div class="cs-steph">{label}</div>' if show_title else ""
    st.markdown(
        f'<div class="cs-stepk">Step {current+1} of {total}</div>'
        f'{title}'
        f'<div class="cs-progress"><i style="width:{pct}%"></i></div>',
        unsafe_allow_html=True)


def _md_inline(s: str) -> str:
    """Render the tiny markdown subset used in ledes/section titles (**bold**, `code`) as HTML,
    so they can live inside our styled containers."""
    import re
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s or "")
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def lede(text: str):
    """The single lead-paragraph style every step opens with (consistent size/color/rhythm)."""
    st.markdown(f"<p class='cs-lede'>{_md_inline(text)}</p>", unsafe_allow_html=True)


def section(title: str, sub: str | None = None):
    """One consistent in-body section header used across every step."""
    html = f"<div class='cs-section'><div class='t'>{_md_inline(title)}</div>"
    if sub:
        html += f"<div class='s'>{_md_inline(sub)}</div>"
    st.markdown(html + "</div>", unsafe_allow_html=True)


def step_rail(order: list[str], labels: dict[str, str], current: int):
    rows = ['<div class="cs-brand"><div class="m">K</div><div class="t">Project Kairos</div></div>',
            '<div class="cs-brand-sub">Content workflow</div>']
    for i, key in enumerate(order):
        cls = "done" if i < current else ("now" if i == current else "")
        mark = "" if i < current else str(i + 1)
        rows.append(f'<div class="cs-step {cls}"><div class="n">{mark}</div>'
                    f'<div class="lbl">{labels[key]}</div></div>')
    st.sidebar.markdown("\n".join(rows), unsafe_allow_html=True)


def reasoning_card(r: dict):
    if not r or not r.get("body"):
        return
    body_html = markdown2.markdown(r["body"]) if markdown2 else r["body"]
    pills = "".join(f'<span class="cs-pill">{p}</span>' for p in r.get("pillars", []))
    pill_block = f'<div class="cs-pills">{pills}</div>' if pills else ""
    st.markdown(f"""
<div class="cs-reason">
  <div class="rh">KAIROS Reasoning</div>
  <div class="rt">{r.get('title','')}</div>
  <div class="rb">{body_html}</div>
  {pill_block}
</div>
""", unsafe_allow_html=True)
