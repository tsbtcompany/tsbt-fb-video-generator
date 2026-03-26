"""
TSBT Video Generator Control Panel v2.0 (Cloud Edition)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Supabase-backed Streamlit app for anywhere-access storyboard editing.
Uses lightweight httpx REST calls (no heavy supabase SDK needed).
Deploy to Streamlit Community Cloud for free multi-PC access.
"""

import streamlit as st
import json
import httpx
import os
import sys
import subprocess
from pathlib import Path

# ═══════════════════════════════════════════════════
# Supabase REST Helper (lightweight, no SDK needed)
# ═══════════════════════════════════════════════════
def supabase_query(table: str, select: str = "*", filters: dict = None, ilike: dict = None, limit: int = 1000):
    """Execute a Supabase REST API query using httpx. Returns [] on error."""
    try:
        url = f"{st.secrets['SUPABASE_URL']}/rest/v1/{table}"
        headers = {
            "apikey": st.secrets["SUPABASE_KEY"],
            "Authorization": f"Bearer {st.secrets['SUPABASE_KEY']}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        params = {"select": select, "limit": str(limit)}
        if filters:
            for col, val in filters.items():
                params[col] = f"eq.{val}"
        if ilike:
            for col, val in ilike.items():
                params[col] = f"ilike.*{val}*"
        
        resp = httpx.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []

# ═══════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════
SCENE_LABELS = [
    "P1 — 표지 (Cover)",
    "P2 — 핵심 제원 (Core Specs)",
    "P3 — 트림 라인업 (Trim Lineup)",
    "P4 — 안전·구조 (Safety & Structure)",
    "P5 — 유지 관리 (Ownership Value)",
    "P6 — 이슈·리콜 (Known Issues)",
    "P7 — 전문가 리뷰 (Expert Analysis)",
    "P8 — 아웃트로 (Outro)",
]

LANGUAGES = {
    "🇰🇷 한국어 (Korean)": "Korean",
    "🇦🇪 아랍어 (Arabic)": "Arabic",
    "🇺🇸 영어 (English)": "English",
}

TEMPLATE_MODES = {
    "📋 Standard Review (8장 상세)": "standard",
    "🥊 VS Match (차량 비교 숏폼)": "vs_match"
}

# ═══════════════════════════════════════════════════
# Page Config & Custom CSS
# ═══════════════════════════════════════════════════
st.set_page_config(
    page_title="TSBT Video Generator",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');
    .stApp {
        background: linear-gradient(135deg, #0a0f1a 0%, #1a2540 100%);
        font-family: 'Inter', sans-serif;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1117 0%, #1c2d3a 100%);
    }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        background-color: rgba(255,255,255,0.05);
        border-radius: 8px 8px 0 0;
        padding: 8px 16px; font-weight: 600;
    }
    .stButton > button { border-radius: 12px; font-weight: 700; padding: 0.6rem 1.2rem; }
    h1 {
        background: linear-gradient(90deg, #69F0AE, #00D4FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 900 !important;
    }
    /* Scene tab content */
    .stTextArea textarea { font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════
# DB Helper — Supabase REST API
# ═══════════════════════════════════════════════════
@st.cache_data(ttl=600)
def load_brand_model_year():
    """Load distinct brand → model → year hierarchy from Supabase (paginated)."""
    url = f"{st.secrets['SUPABASE_URL']}/rest/v1/1_02_tsbt_trims"
    headers = {
        "apikey": st.secrets["SUPABASE_KEY"],
        "Authorization": f"Bearer {st.secrets['SUPABASE_KEY']}",
        "Content-Type": "application/json",
        "Prefer": "count=exact",
    }
    
    all_rows = []
    page_size = 1000
    offset = 0
    
    while True:
        h = {**headers, "Range": f"{offset}-{offset + page_size - 1}"}
        resp = httpx.get(url, headers=h, params={"select": "brand,model_name,year"}, timeout=20)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    
    hierarchy = {}
    seen = set()
    for row in all_rows:
        key = (row.get("brand"), row.get("model_name"), row.get("year"))
        if None in key or key in seen:
            continue
        seen.add(key)
        brand, model_name, year = key
        hierarchy.setdefault(brand, {}).setdefault(model_name, [])
        if year not in hierarchy[brand][model_name]:
            hierarchy[brand][model_name].append(year)
    
    for brand in hierarchy:
        for model in hierarchy[brand]:
            hierarchy[brand][model].sort(reverse=True)
    return hierarchy

@st.cache_data(ttl=60)
def load_video_logs():
    """Fetch video generation logs to display status badges."""
    url = f"{st.secrets['SUPABASE_URL']}/rest/v1/tsbt_video_logs"
    headers = {
        "apikey": st.secrets["SUPABASE_KEY"],
        "Authorization": f"Bearer {st.secrets['SUPABASE_KEY']}",
        "Content-Type": "application/json",
    }
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        h = {**headers, "Range": f"{offset}-{offset + page_size - 1}"}
        try:
            resp = httpx.get(url, headers=h, timeout=15)
            resp.raise_for_status()
            batch = resp.json()
            if not batch: break
            all_rows.extend(batch)
            if len(batch) < page_size: break
            offset += page_size
        except Exception:
            break
            
    log_map = {}
    for r in all_rows:
        log_map[(r.get("brand"), r.get("model_name"), r.get("year"))] = r.get("status")
    return all_rows, log_map

def upsert_video_log(brand, model_name, year, status):
    """Upsert the status of a video generation."""
    url = f"{st.secrets['SUPABASE_URL']}/rest/v1/tsbt_video_logs"
    headers = {
        "apikey": st.secrets["SUPABASE_KEY"],
        "Authorization": f"Bearer {st.secrets['SUPABASE_KEY']}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    payload = {
        "brand": brand,
        "model_name": model_name,
        "year": year,
        "status": status
    }
    try:
        httpx.post(url, headers=headers, json=payload, timeout=10)
        load_video_logs.clear()  # Clear cache to reflect updates
    except Exception as e:
        print(f"Log upsert failed: {e}")

# ═══════════════════════════════════════════════════
# AI Generator — Gemini (Cloud-compatible)
# ═══════════════════════════════════════════════════
def fetch_vehicle_markdown_from_supabase(brand, model_name, year):
    """Build markdown source from Supabase tables for Gemini prompt."""
    # 1. Trims
    trims = supabase_query(
        "1_02_tsbt_trims",
        select="trim_name,engine_cc,fuel_type,max_power_hp,max_torque_kgm,drivetrain,transmission,curb_weight_kg",
        filters={"brand": brand, "model_name": model_name, "year": year},
        limit=50
    )
    # 2. Reviews (motorgraph)
    reviews_mg = supabase_query("2_01_motorgraph_reviews", select="title,content", ilike={"title": model_name}, limit=5)
    # 3. Reviews (autoview)
    reviews_av = supabase_query("2_02_autoview_reviews", select="title,content", ilike={"title": model_name}, limit=5)
    # 4. KNCAP
    kncap = supabase_query("3_09_01_kncap", select="*", ilike={"model_name": model_name}, limit=5)
    # 5. IIHS
    iihs = supabase_query("3_09_04_iihs", select="*", ilike={"model": model_name}, limit=5)
    # 6. Recalls
    recalls = supabase_query("3_10_01_molit_recalls", select="*", ilike={"model_name": model_name}, limit=10)
    
    md = f"# {year} {brand} {model_name}\n\n"
    
    md += "## 트림 및 제원 정보\n\n"
    if trims:
        engine_types = set()
        for t in trims:
            md += f"- **{t.get('trim_name', 'N/A')}**: {t.get('engine_cc', '')}cc {t.get('fuel_type', '')} | {t.get('max_power_hp', '')}hp | {t.get('max_torque_kgm', '')}kgm | {t.get('drivetrain', '')} | {t.get('transmission', '')} | {t.get('curb_weight_kg', '')}kg\n"
            if t.get('fuel_type') and t.get('engine_cc'):
                engine_types.add(f"{t['fuel_type']} {t['engine_cc']}cc")
        md += f"\n파워트레인 라인업: {', '.join(engine_types)}\n\n"
    
    md += "## 전문가 리뷰\n\n"
    for r in (reviews_mg or []) + (reviews_av or []):
        md += f"### {r.get('title', '')}\n{(r.get('content', '') or '')[:500]}\n\n"
    
    md += "## 안전 등급\n\n"
    for k in (kncap or []):
        md += f"- KNCAP: {json.dumps(k, ensure_ascii=False)}\n"
    for i in (iihs or []):
        md += f"- IIHS: {json.dumps(i, ensure_ascii=False)}\n"
    
    md += "\n## 리콜 이력\n\n"
    if recalls:
        for rc in recalls:
            md += f"- {json.dumps(rc, ensure_ascii=False)}\n"
    else:
        md += "해당 기간 리콜 이력 없음\n"
    
    return md


def generate_vs_storyboard_cloud(brand_a, model_a, year_a, brand_b, model_b, year_b):
    """Generate VS Match storyboard using Gemini API with Supabase data from two cars."""
    from google import genai
    from google.genai import types
    
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY가 설정되지 않았습니다.")
        return None
    
    client = genai.Client(api_key=api_key)
    md_a = fetch_vehicle_markdown_from_supabase(brand_a, model_a, year_a)
    md_b = fetch_vehicle_markdown_from_supabase(brand_b, model_b, year_b)
    
    # Deep Think's masterful VS Prompt
    prompt = f"""
    # ROLE & PERSONA
    당신은 중동 자동차 수출 시장(UAE, 사우디, 요르단 등)에 정통한 15년 차 베테랑 딜러이자, 전 세계에서 가장 텐션이 높은 'UFC 격투기 매치 메인 해설자'입니다. 
    당신의 임무는 입력된 두 대의 차량(Car A vs Car B) 데이터를 링 위에 올린 파이터처럼 취급하여, 중동 바이어들의 도파민을 터뜨리고 당장 컨테이너에 차를 싣고 싶게 만드는 5개 씬(Scene)의 숏폼 대본을 작성하는 것입니다.

    # TARGET AUDIENCE & CORE HOOKS
    - 타겟: 철저히 실용성과 수익성에 미쳐있는 중동 현지의 중고차 바이어.
    - 환장하는 포인트 3가지 (반드시 스크립트에 녹일 것): 
      1) 사막의 폭염을 견디는 '에어컨 성능과 엔진 내구성'
      2) 동네 카센터에서도 싸게 고치는 '부품 수급력 (수리비 지옥 회피)'
      3) 3년 뒤 되팔아도 마진이 든든한 '감가상각 방어율 (Resale Value)'

    # ROLE & PERSONA
    당신은 한국 중고차를 글로벌(특히 중동)로 수출하는 'TSBT' 플랫폼의 최고 에이스 세일즈 컨설턴트입니다. 
    당신의 목표는 두 대의 차량(Car A vs Car B) 중 하나를 깎아내리거나 패배자로 만드는 것이 **절대 아닙니다.** 두 차량 모두 완판해야 할 훌륭한 수출 매물이므로, **각 차량이 어떤 타겟 바이어(용도, 취향, 예산)에게 적합한지 밸런스 있게 큐레이션 하여 시청자가 두 차 모두 매력적으로 느끼게 만드는 숏폼 영상 대본(5개 씬)**을 작성하는 것입니다.

    # 🚫 CRITICAL BUSINESS RULES (절대 위반 금지)
    1. **절대 비하 금지 (No Bashing):** 한 차량을 '쓰레기, 고장 덩어리, 수리비 폭탄' 등으로 표현하지 마십시오. "A는 이런 매력, B는 저런 매력"의 긍정적인 톤을 유지하세요.
    2. **현기차 플랫폼 공유 팩트 준수:** 현대(Hyundai)와 기아(Kia)처럼 파워트레인이나 에어컨 부품을 공유하는 형제 차량인 경우, 억지 비교를 절대 하지 마십시오. 오히려 "두 차량 모두 사막에 최적화된 미친 에어컨과 완벽한 부품 수급을 공유한다!"며 둘 다 극찬하십시오.
    3. **비교 기준은 '우열'이 아닌 '성향/타겟'입니다:** 
       - 디자인 (클래식/중후함 vs 스포티/트렌디)
       - 타겟 고객 (패밀리/택시/법인 vs 젊은층/개인오너)
       - 셋팅 (부드러운 승차감 vs 다이내믹한 주행)
    4. 다국어 최적화: `narration_en`은 에너지가 넘치는 영어로, `narration_ar`는 피가 끓어오르는 세일즈 지향적 현지 아랍어로 작성하세요.

    # SCENE STRUCTURE & HOOKS
    - Scene 1 [face_off]: 매치업 소개. "같은 뼈대, 완전히 다른 매력! 사막을 달릴 두 형제의 대결, 당신의 타겟은?"
    - Scene 2 [gauge_style]: 외관 디자인과 분위기(Vibe) 성향 비교 게이지. (예: 중후함 vs 날렵함)
    - Scene 3 [gauge_target]: 주요 타겟층 및 현지 활용도 비교 게이지. (예: 택시/패밀리 vs 개인오너)
    - Scene 4 [gauge_shared]: 공통의 장점 어필 게이지. (예: 완벽한 에어컨, 저렴한 유지비 공유 팩트 찬양)
    - Scene 5 [dual_cta]: 최종 선택 유도. "승자는 없습니다. 당신의 시장에 맞는 차를 선택해 컨테이너를 채우세요! 지금 댓글로 문의하세요!"

    # OUTPUT REQUIREMENT (UI Data)
    비교 수치(`ui_gauge_percent`)를 줄 때는 100 vs 0 처럼 극단적으로 주지 마십시오. 이는 '우열'이 아니라 **'해당 성향의 강도'**를 의미합니다.
    (예: '스포티함' 라운드라면 K5는 95, 쏘나타는 60. '비즈니스 세단 느낌' 라운드라면 쏘나타는 95, K5는 60 등 각자의 장점 라운드에서 높은 점수를 받게 배분하십시오.)

    # 🚫 UI TEXT LENGTH RULES (절대 규칙 - 화면 레이아웃 붕괴 방지)
    JSON 결과물에서 화면 UI에 직접 렌더링될 텍스트(`metric_label`, `display_text` 등)는 숏폼 화면에 맞게 **매우 짧고 타격감 있는 '단어/명사형'**으로만 작성해야 합니다. 절대 서술형 문장을 쓰지 마십시오.
    1. `metric_label` (라운드 주제): **최대 2~3단어 이내** (예: "타겟 고객", "에어컨 성능", "디자인 성향")
    2. `car_a_stats.display_text`, `car_b_stats.display_text` (해당 차량의 강점 키워드): **최대 10자 이내의 단어** (예: "패밀리/택시", "젊은층", "CLASSIC", "SPORTY")

    # INPUT DATA
    [Car A (Red Corner)]
    {md_a}
    
    [Car B (Blue Corner)]
    {md_b}

    # OUTPUT FORMAT
    OUTPUT ONLY THE EXACT JSON STRUCTURE PROVIDED IN THE INSTRUCTION, DO NOT USE MARKDOWN BLOCK.
    {{
      "match_info": {{
        "title_en": "...", "target_audience": "...", "final_winner_id": "none",
        "car_a": {{ "id": "car_a", "name": "...", "corner": "red", "img_url": "" }},
        "car_b": {{ "id": "car_b", "name": "...", "corner": "blue", "img_url": "" }}
      }},
      "scenes": [
        {{
          "scene_number": 1, "layout_type": "face_off",
          "caption": "...", "narration_en": "...", "narration_ar": "...",
          "comparison_data": null
        }},
        {{
          "scene_number": 2, "layout_type": "gauge_style",
          "caption": "...", "narration_en": "...", "narration_ar": "...",
          "comparison_data": {{
            "metric_label": "Design Vibe", "higher_is_better": true, "round_winner_id": "...",
            "car_a_stats": {{ "display_text": "Classic", "ui_gauge_percent": 95 }},
            "car_b_stats": {{ "display_text": "Sporty", "ui_gauge_percent": 60 }}
          }}
        }},
        {{
          "scene_number": 3, "layout_type": "gauge_target",
          // ... schema continues ...
        }},
        {{
          "scene_number": 4, "layout_type": "gauge_shared",
          // ... schema continues ...
        }},
        {{
          "scene_number": 5, "layout_type": "dual_cta",
          "caption": "Your Choice?", "narration_en": "...", "narration_ar": "...",
          "comparison_data": null
        }}
      ]
    }}
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.8,
        ),
    )
    try:
        data = json.loads(response.text)
        data["template"] = "vs_match"  # mark for React renderer
        return data
    except Exception:
        return {"raw_text": response.text}




def generate_storyboard_cloud(brand, model_name, year, language="Korean"):
    """Generate storyboard using Gemini API with Supabase data."""
    from google import genai
    from google.genai import types
    from pydantic import BaseModel, Field
    
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY가 설정되지 않았습니다.")
        return None
    
    client = genai.Client(api_key=api_key)
    md_text = fetch_vehicle_markdown_from_supabase(brand, model_name, year)
    
    class Scene(BaseModel):
        scene_number: int
        visual_idea: str = Field(description="Visual layout or background suggestion")
        caption: str = Field(description="Bold on-screen title/header")
        body_text: list[str] = Field(description="2~4 impactful bullet points")
        narration: str = Field(description="Short narration for voiceover")

    class Storyboard(BaseModel):
        title: str
        target_audience: str
        scenes: list[Scene] = Field(description="Exactly 8 scenes")
    
    prompt = f"""
    You are a professional automotive content director targeting export buyers in the Middle East (Dubai).
    Based on the following TSBT vehicle data, generate a highly engaging 8-scene vertical video (9:16) storyboard.
    Premium, export-focused, professional yet cinematic tone.
    
    CRITICAL: EVERYTHING (captions, body_text, narration) MUST BE IN: {language.upper()}.
    Keep brand names and standards like 'IIHS', 'KNCAP' in English.
    DO NOT mention new car prices.
    
    [TSBT Vehicle Data]
    {md_text}
    
    STRICT 8-PAGE CONTENT RULE:
    Scene 1 (Cover): 감성적 headline. body_text 5개: [0] 연식+브랜드+모델명, [1] 2~3문장 차량 철학 태그라인, [2~4] 하이라이트 수치 3개.
    Scene 2 (Core Specs): "CORE SPECIFICATIONS". body_text에 11~14 스펙 전부. "라벨 | 값 단위" 형식.
    Scene 3 (Trim Lineup): "TRIM LINEUP". body_text에 트림 4~5개 + 파워트레인 요약.
    Scene 4 (Safety): "SAFETY & STRUCTURE". body_text 5개: 에어백, KNCAP, IIHS, AHSS%, 추가 안전팩트.
    Scene 5 (Ownership): "OWNERSHIP VALUE". body_text 7~8개. CRITICAL: This content targets GLOBAL export buyers. 
        DO NOT include country-specific data (no Korean 자동차세, no local currency prices, no local service center info).
        Instead use UNIVERSAL maintenance specs: 연비(복합), 엔진오일 규격(예: 5W-30) + 교환주기(km), 타이어 규격(예: 225/45R17) + 교환주기(km), 
        브레이크패드 교환주기(km), 냉각수/미션오일 교환주기, 소모품 수급 난이도(글로벌 기준 1~5), 감가상각 특성.
        Format: "라벨 | 값" (예: "엔진오일 규격 | 5W-30, 매 10,000km").
    Scene 6 (Issues): "KNOWN ISSUES". body_text 5~6개 이슈 + 안심 메시지.
    Scene 7 (Expert): "EXPERT ANALYSIS". body_text 6개: TSBT 점수, 장점 3, 단점 2.
    Scene 8 (Outro): caption "TSBT — 세상의 모든 자동차 데이터". body_text 빈 배열 [].
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Storyboard,
            temperature=0.7,
        ),
    )
    
    try:
        return json.loads(response.text)
    except Exception:
        return {"raw_text": response.text}

# ═══════════════════════════════════════════════════
# Session State Init
# ═══════════════════════════════════════════════════
if "storyboard" not in st.session_state:
    st.session_state.storyboard = None

# ═══════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🚗 TSBT Video Generator")
    st.markdown("---")

    st.markdown("### 📋 템플릿 선택")
    selected_template_label = st.radio("포맷", list(TEMPLATE_MODES.keys()), index=0, label_visibility="collapsed")
    selected_template = TEMPLATE_MODES[selected_template_label]
    
    st.markdown("---")

    try:
        hierarchy = load_brand_model_year()
        all_logs, log_map = load_video_logs()
    except Exception as e:
        st.error(f"⚠️ Supabase 연결 실패: {e}")
        hierarchy = {}
        all_logs, log_map = [], {}
    
    brand_list = sorted(hierarchy.keys()) if hierarchy else []

    def build_car_selector(prefix, hierarchy, log_map):
        b = st.selectbox(f"[{prefix}] 브랜드", brand_list, index=0 if brand_list else None, key=f"{prefix}_brand")
        m_list = sorted(hierarchy.get(b, {}).keys()) if b else []
        m = st.selectbox(f"[{prefix}] 모델", m_list, index=0 if m_list else None, key=f"{prefix}_model")
        
        y_list = hierarchy.get(b, {}).get(m, []) if b and m else []
        y_map = {}
        for yr in y_list:
            status = log_map.get((b, m, yr))
            dl = f"{yr} (✅ 렌더링)" if status == "RENDERED" else f"{yr} (📝 대본)" if status == "DRAFTED" else str(yr)
            y_map[dl] = yr
        yl = st.selectbox(f"[{prefix}] 연식", list(y_map.keys()), index=0 if y_map else None, key=f"{prefix}_year")
        return b, m, y_map.get(yl)

    if selected_template == "standard":
        st.markdown("### 🚗 타겟 차량 선택")
        selected_brand, selected_model, selected_year = build_car_selector("Standard", hierarchy, log_map)
    else:
        st.markdown("### 🥊 코너 A (Red) 선택")
        brand_a, model_a, year_a = build_car_selector("A", hierarchy, log_map)
        st.markdown("### 🚙 코너 B (Blue) 선택")
        brand_b, model_b, year_b = build_car_selector("B", hierarchy, log_map)


    if all_logs:
        import pandas as pd
        df_logs = pd.DataFrame(all_logs)
        csv = df_logs.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📊 전체 작업 현황 엑셀 다운로드",
            data=csv,
            file_name="tsbt_video_logs.csv",
            mime="text/csv",
            help="지금까지 DRAFTED 되거나 RENDERED 된 차종의 CSV를 추출합니다."
        )

    st.markdown("---")
    st.markdown("### 🌐 출력 언어")
    lang_label = st.radio("언어", list(LANGUAGES.keys()), index=0, label_visibility="collapsed")
    selected_lang = LANGUAGES[lang_label]

    st.markdown("---")
    st.markdown("### 🤖 AI 스토리보드 생성")
    if st.button("🚀 Gemini로 자동 생성", use_container_width=True, type="primary"):
        if selected_template == "standard":
            if not selected_brand or not selected_model or not selected_year:
                st.error("차량을 선택해주세요!")
            else:
                with st.spinner(f"🔄 {selected_year} {selected_brand} {selected_model} 생성 중..."):
                    result = generate_storyboard_cloud(selected_brand, selected_model, selected_year, selected_lang)
                    if result and "scenes" in result:
                        st.session_state.storyboard = result
                        upsert_video_log(selected_brand, selected_model, selected_year, "DRAFTED")
                        st.success("✅ 생성 완료! (DB에 저장됨)")
                        st.rerun()
                    else:
                        st.error("생성 실패.")
        else:
            if not brand_a or not brand_b:
                st.error("A와 B 차량을 모두 선택해주세요!")
            else:
                with st.spinner(f"🥊 {model_a} VS {model_b} 매치업 생성 중..."):
                    result = generate_vs_storyboard_cloud(brand_a, model_a, year_a, brand_b, model_b, year_b)
                    if result and "scenes" in result:
                        st.session_state.storyboard = result
                        upsert_video_log(brand_a, model_a, year_a, "DRAFTED")
                        upsert_video_log(brand_b, model_b, year_b, "DRAFTED")
                        st.success("✅ 매치업 생성 완료!")
                        st.rerun()
                    else:
                        st.error(f"생성 실패: {result}")

    st.markdown("---")
    st.markdown("### 📂 기존 JSON 불러오기")
    uploaded = st.file_uploader("JSON 업로드", type=["json"], label_visibility="collapsed")
    if uploaded:
        try:
            st.session_state.storyboard = json.load(uploaded)
            st.success("✅ 로드 완료!")
            st.rerun()
        except Exception as e:
            st.error(f"파싱 실패: {e}")

# ═══════════════════════════════════════════════════
# MAIN AREA
# ═══════════════════════════════════════════════════
st.markdown("# 🎬 TSBT Video Generator Control Panel")

if st.session_state.storyboard is None:
    st.info("👈 사이드바에서 모델 선택 → **AI 생성** 또는 JSON 업로드")
    st.stop()

data = st.session_state.storyboard
scenes = data.get("scenes", [])

col1, col2 = st.columns(2)
with col1:
    data["title"] = st.text_input("📌 타이틀", value=data.get("title", ""), key="title_input")
with col2:
    data["target_audience"] = st.text_input("🎯 타겟 오디언스", value=data.get("target_audience", ""), key="audience_input")

st.markdown("---")

# ── Dynamic Scene Editor ──
tabs = st.tabs([f"Scene {i+1}" for i in range(len(scenes))])
for idx, tab in enumerate(tabs):
    scene = scenes[idx]
    with tab:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"#### 🎬 {scene.get('layout_type', 'Scene')} {idx + 1}")
            scene["caption"] = st.text_input("Caption", value=scene.get("caption", ""), key=f"cap_{idx}")
            
            # Support both Standard and VS structures
            nar = scene.get("narration_ar", scene.get("narration", ""))
            scene["narration_ar"] if "narration_ar" in scene else scene.setdefault("narration", nar)
            new_nar = st.text_area("Narration (AR/Default)", value=nar, height=100, key=f"nar_{idx}")
            if "narration_ar" in scene: scene["narration_ar"] = new_nar
            else: scene["narration"] = new_nar
            
            if "visual_idea" in scene:
                scene["visual_idea"] = st.text_area("Visual Idea", value=scene.get("visual_idea", ""), height=80, key=f"vis_{idx}")
        with c2:
            st.markdown("#### 📝 Data / Body Text")
            if "body_text" in scene:
                body_str = "\n".join(scene.get("body_text", []))
                new_body = st.text_area("Body", value=body_str, height=300, key=f"body_{idx}", label_visibility="collapsed")
                scene["body_text"] = [line for line in new_body.split("\n") if line.strip()]
            elif "comparison_data" in scene and scene["comparison_data"]:
                cd = scene["comparison_data"]
                st.code(json.dumps(cd, indent=2, ensure_ascii=False), language="json")
                if st.checkbox(f"Edit JSON (Scene {idx+1})", key=f"edit_json_{idx}"):
                    edited_json = st.text_area("JSON", value=json.dumps(cd, indent=2, ensure_ascii=False), height=250, key=f"json_ta_{idx}")
                    try:
                        scene["comparison_data"] = json.loads(edited_json)
                    except:
                        st.error("Invalid JSON format")

st.markdown("---")

# ═══════════════════════════════════════════════════
# BOTTOM ACTIONS — Unified Local/Cloud
# ═══════════════════════════════════════════════════

# Detect local rendering environment
RENDER_SCRIPT = Path(__file__).parent.parent / "render_video.py"
IS_LOCAL = RENDER_SCRIPT.exists()

json_str = json.dumps(data, indent=2, ensure_ascii=False)
safe_title = (data.get("title", "output") or "output")[:20].replace(" ", "_").replace("/", "_")

if IS_LOCAL:
    # ── LOCAL MODE: Full pipeline ──
    st.success("🖥️ **로컬 렌더링 모드** — 이 PC에서 영상 렌더링이 가능합니다!")
    col_json, col_render = st.columns(2)
    
    with col_json:
        st.download_button(
            "📥 JSON 다운로드",
            data=json_str,
            file_name=f"storyboard_{safe_title}.json",
            mime="application/json",
            use_container_width=True,
        )
    
    with col_render:
        output_name = st.text_input("출력 파일명", value=f"{safe_title}.mp4", label_visibility="collapsed")
        if st.button("🎬 영상 렌더링", use_container_width=True, type="primary"):
            # Save temp JSON
            temp_json = Path(__file__).parent.parent / "_cloud_render_temp.json"
            with open(temp_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            output_path = Path(__file__).parent.parent / output_name
            
            with st.spinner("🔄 Remotion 렌더링 중... (약 2~3분 소요)"):
                cmd = [sys.executable, str(RENDER_SCRIPT), "--input", str(temp_json), "--output", str(output_path)]
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(RENDER_SCRIPT.parent))
                
                if result.returncode == 0 and output_path.exists():
                    upsert_video_log(selected_brand, selected_model, selected_year, "RENDERED")
                    st.success(f"✅ 렌더링 완료! (DB 기록됨)")
                    with open(output_path, "rb") as f:
                        st.download_button(
                            "📥 MP4 다운로드",
                            data=f.read(),
                            file_name=output_name,
                            mime="video/mp4",
                            use_container_width=True,
                        )
                else:
                    st.error(f"렌더링 실패:\n{result.stderr[:500] if result.stderr else 'Unknown error'}")
else:
    # ── CLOUD MODE: JSON download only ──
    col_dl, col_help = st.columns(2)
    with col_dl:
        st.download_button(
            "📥 JSON 다운로드 (렌더링용)",
            data=json_str,
            file_name=f"storyboard_{safe_title}.json",
            mime="application/json",
            use_container_width=True,
            type="primary",
        )
    with col_help:
        st.info("💡 렌더링 PC에서:\n`py render_video.py --input 파일.json`")

st.markdown("---")
st.caption(f"TSBT Video Generator v2.0 {'(Local 🖥️)' if IS_LOCAL else '(Cloud ☁️)'} — Supabase + Gemini + Remotion")
