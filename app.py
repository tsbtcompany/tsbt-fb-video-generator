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
    Scene 5 (Ownership): "OWNERSHIP VALUE". body_text 7~8개 유지비 항목.
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

    st.markdown("### 📋 타겟 모델 선택")
    try:
        hierarchy = load_brand_model_year()
    except Exception as e:
        st.error(f"⚠️ Supabase 연결 실패: {e}")
        hierarchy = {}
    
    brand_list = sorted(hierarchy.keys()) if hierarchy else []
    selected_brand = st.selectbox("브랜드", brand_list, index=0 if brand_list else None)

    model_list = sorted(hierarchy.get(selected_brand, {}).keys()) if selected_brand else []
    selected_model = st.selectbox("모델", model_list, index=0 if model_list else None)

    year_list = hierarchy.get(selected_brand, {}).get(selected_model, []) if selected_brand and selected_model else []
    selected_year = st.selectbox("연식", year_list, index=0 if year_list else None)

    st.markdown("---")
    st.markdown("### 🌐 출력 언어")
    lang_label = st.radio("언어", list(LANGUAGES.keys()), index=0, label_visibility="collapsed")
    selected_lang = LANGUAGES[lang_label]

    st.markdown("---")
    st.markdown("### 🤖 AI 스토리보드 생성")
    if st.button("🚀 Gemini로 자동 생성", use_container_width=True, type="primary"):
        if not selected_brand or not selected_model or not selected_year:
            st.error("브랜드, 모델, 연식을 모두 선택해주세요!")
        else:
            with st.spinner(f"🔄 {selected_year} {selected_brand} {selected_model} 생성 중..."):
                result = generate_storyboard_cloud(selected_brand, selected_model, selected_year, selected_lang)
                if result and "scenes" in result:
                    st.session_state.storyboard = result
                    st.success("✅ 생성 완료!")
                    st.rerun()
                else:
                    st.error("생성 실패. 다시 시도해주세요.")

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

# ── 8-Tab Scene Editor ──
tabs = st.tabs(SCENE_LABELS[:len(scenes)])
for idx, tab in enumerate(tabs):
    if idx >= len(scenes):
        break
    scene = scenes[idx]
    with tab:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"#### 🎬 Scene {idx + 1}")
            scene["caption"] = st.text_input("Caption", value=scene.get("caption", ""), key=f"cap_{idx}")
            scene["narration"] = st.text_area("Narration", value=scene.get("narration", ""), height=100, key=f"nar_{idx}")
            scene["visual_idea"] = st.text_area("Visual Idea", value=scene.get("visual_idea", ""), height=80, key=f"vis_{idx}")
        with c2:
            st.markdown("#### 📝 Body Text (한 줄 = 한 항목)")
            body_str = "\n".join(scene.get("body_text", []))
            new_body = st.text_area("Body", value=body_str, height=300, key=f"body_{idx}", label_visibility="collapsed")
            scene["body_text"] = [line for line in new_body.split("\n") if line.strip()]
            st.caption(f"📊 항목: **{len(scene['body_text'])}**개 | 글자: **{sum(len(l) for l in scene['body_text'])}**자")

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
                    st.success(f"✅ 렌더링 완료!")
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
