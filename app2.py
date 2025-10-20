import re
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
from streamlit_js_eval import streamlit_js_eval  # 사용 안 해도 기존 구조 유지

# ==============================
# Google Drive 연결 설정 (Secrets 사용)
# ==============================
creds = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/drive.readonly"]
)
service = build("drive", "v3", credentials=creds)
FOLDER_ID = "10ZRhsEccCCy9qo-RB_z2VuMRUReLbIuL"  # Flashcards 이미지 폴더 ID

def get_files_from_folder(folder_id):
    """폴더 안의 모든 이미지 파일 가져오기"""
    query = f"'{folder_id}' in parents and mimeType contains 'image/'"
    files = []
    page_token = None
    while True:
        results = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name)",
            pageSize=200,
            pageToken=page_token
        ).execute()
        files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    return files

# ==============================
# Utils
# ==============================
def normalize(name: str) -> str:
    base = name.rsplit(".", 1)[0]
    return base.strip().lower()

@st.cache_data(ttl=300, show_spinner=False)
def list_drive_files(folder_id: str):
    """Drive에서 (id, norm_name, raw_name) 리스트 캐시"""
    files = get_files_from_folder(folder_id)
    return [
        {"id": f["id"], "norm": normalize(f["name"]), "raw": f["name"]}
        for f in files
    ]

def build_maps(files):
    """빠른 조회용 맵들"""
    id_by_norm = {f["norm"]: f["id"] for f in files}
    raw_by_norm = {f["norm"]: f["raw"] for f in files}
    return id_by_norm, raw_by_norm

def to_thumb(file_id: str, width=1000) -> str:
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{width}"

def find_word_number_matches(token: str, norms: list[str]) -> list[str]:
    """
    모든 단어에 대해 '단어+숫자' 형태만 매칭 (영문자 경계 기준)
    예) land1, my_land12, cat007, green_apple2 (OK)
       island2, landlord3, land-12, apple_v2, land12a (X)
    규칙:
      - 단어 앞은 영문자가 아닌 문자여야 함 (?<![a-z])
      - 단어 그대로 일치 (re.escape)
      - 바로 뒤에 숫자가 1개 이상 \d+
      - 숫자 뒤는 영문자가 아님 (?![a-z])
    """
    t = token.strip().lower()
    if not t:
        return []
    pattern = re.compile(rf'(?<![a-z]){re.escape(t)}\d+(?![a-z])')
    return [n for n in norms if pattern.search(n)]

# ==============================
# Streamlit UI 설정
# ==============================
st.set_page_config(page_title="BCA Flashcards", layout="wide")

if "mode" not in st.session_state:
    st.session_state.mode = "home"
if "cards" not in st.session_state:
    st.session_state.cards = []
if "current" not in st.session_state:
    st.session_state.current = 0

# ==============================
# 1단계: 단어 입력 화면
# ==============================
if st.session_state.mode == "home":
    st.title("BCA Flashcards")
    st.subheader("Type words (comma separated), then press Enter.\nOnly files matching word+number will be used.")

    words = st.text_input(
        "Flashcards",
        placeholder="e.g., land, cat, apple",
        label_visibility="collapsed",
        key="word_input"
    )

    if words:
        files = list_drive_files(FOLDER_ID)
        id_by_norm, raw_by_norm = build_maps(files)
        all_norms = list(id_by_norm.keys())

        tokens = [w.strip().lower() for w in words.split(",") if w.strip()]
        matched_norms = []
        for t in tokens:
            matched_norms.extend(find_word_number_matches(t, all_norms))

        # 중복 제거 + 입력 순서 유지
        seen = set()
        ordered_norms = []
        for n in matched_norms:
            if n not in seen:
                seen.add(n)
                ordered_norms.append(n)

        selected = [to_thumb(id_by_norm[n]) for n in ordered_norms]

        # 매칭 미리보기
        if ordered_norms:
            st.caption(
                "Matched (word+number): " +
                ", ".join(ordered_norms[:30]) +
                ("..." if len(ordered_norms) > 30 else "")
            )

        if selected:
            st.session_state.cards = selected
            st.session_state.mode = "gallery"
            st.rerun()
        else:
            st.warning("⚠️ No matching flashcards found for word+number pattern. Try different keywords.")

# ==============================
# 2단계: 갤러리 미리보기 화면
# ==============================
elif st.session_state.mode == "gallery":
    st.title("BCA Flashcards")
    st.subheader("Preview your flashcards below. Select the ones you want for presentation.")

    # Add More 입력창 토글
    if "show_input" not in st.session_state:
        st.session_state.show_input = False
    if "selected_cards" not in st.session_state:
        st.session_state.selected_cards = st.session_state.cards.copy()

    if st.button("➕ Add More"):
        st.session_state.show_input = not st.session_state.show_input
        st.rerun()

    if st.session_state.show_input:
        new_words = st.text_input(
            "Add Flashcards",
            placeholder="e.g., land, cat, apple (word+number only)",
            label_visibility="collapsed",
            key="word_input_gallery"
        )
        if st.button("Add Now"):
            if new_words:
                files = list_drive_files(FOLDER_ID)
                id_by_norm, raw_by_norm = build_maps(files)
                all_norms = list(id_by_norm.keys())

                tokens = [w.strip().lower() for w in new_words.split(",") if w.strip()]
                matched_norms = []
                for t in tokens:
                    matched_norms.extend(find_word_number_matches(t, all_norms))

                # 중복 제거 + 순서 유지
                seen = set()
                ordered_norms = []
                for n in matched_norms:
                    if n not in seen:
                        seen.add(n)
                        ordered_norms.append(n)

                to_add = [to_thumb(id_by_norm[n]) for n in ordered_norms]

                if to_add:
                    # 중복 제거 + 순서 유지
                    st.session_state.cards = list(dict.fromkeys(st.session_state.cards + to_add))
            st.session_state.show_input = False
            st.rerun()

    # 갤러리
    if st.session_state.cards:
        new_selection = []
        num_cols = 8   # 기본 8열
        cols = st.columns(num_cols)

        for i, url in enumerate(st.session_state.cards):
            with cols[i % num_cols]:
                st.image(url, use_container_width=True)
                default_checked = st.session_state.get(f"chk_{i}", url in st.session_state.selected_cards)
                checked = st.checkbox(f"Card {i+1}", key=f"chk_{i}", value=default_checked)
                if checked:
                    new_selection.append(url)

        st.session_state.selected_cards = new_selection

        # 버튼 (왼쪽 정렬)
        st.markdown("<br>", unsafe_allow_html=True)
        b1, b2, b3 = st.columns([1,1,6])
        with b1:
            if st.button("▶ Presentation"):
                st.session_state.mode = "present"
                st.session_state.current = 0
                st.rerun()
        with b2:
            if st.button("🎮 Memory Game"):
                if st.session_state.cards:
                    st.session_state.mode = "memory_game"
                    st.session_state.memory_flipped = []
                    st.session_state.memory_matched = []
                    st.rerun()
        with b3:
            if st.button("🏠 Home"):
                st.session_state.mode = "home"
                st.rerun()

# ==============================
# 3단계: Presentation 전체화면 모드
# ==============================
elif st.session_state.mode == "present":
    st.markdown(
        """
        <style>
            .block-container {padding:0; margin:0; max-width:100%;}
            header, footer, .stToolbar {visibility:hidden; height:0;}
            body {background:black; margin:0; padding:0;}
            .present-img {
                display:flex;
                justify-content:center;
                align-items:center;
                height:90vh;   /* 이미지 영역 */
            }
            .present-img img {
                max-height:90vh;
                max-width:90vw;
                border-radius:15px;
                box-shadow:0 0 40px rgba(255,255,255,0.3);
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.cards:
        url = st.session_state.cards[st.session_state.current]
        st.markdown(f"<div class='present-img'><img src='{url}'></div>", unsafe_allow_html=True)

        # 버튼은 present 모드에서만 표시
        col1, col2, col3 = st.columns([1,1,1])
        with col1:
            if st.button("◀ Prev", use_container_width=True):
                st.session_state.current = (st.session_state.current - 1) % len(st.session_state.cards)
                st.rerun()
        with col2:
            if st.button("Exit", use_container_width=True):
                st.session_state.mode = "gallery"
                st.rerun()
        with col3:
            if st.button("Next ▶", use_container_width=True):
                st.session_state.current = (st.session_state.current + 1) % len(st.session_state.cards)
                st.rerun()

# ==============================
# 4단계: 메모리 게임 모드
# ==============================
elif st.session_state.mode == "memory_game":
    st.title("🎮 Memory Game")

    cards = st.session_state.cards.copy()

    num_cols = 4
    cols = st.columns(num_cols)

    for i, url in enumerate(cards):
        with cols[i % num_cols]:
            if i in st.session_state.memory_matched:
                st.image(url, use_container_width=True)  # 매칭된 카드
            elif i in st.session_state.memory_flipped:
                st.image(url, use_container_width=True)  # 뒤집힌 카드
            else:
                if st.button(f"Card {i+1}", key=f"mem_{i}"):
                    st.session_state.memory_flipped.append(i)
                    if len(st.session_state.memory_flipped) == 2:
                        i1, i2 = st.session_state.memory_flipped
                        if cards[i1] == cards[i2]:
                            st.session_state.memory_matched.extend([i1, i2])
                        st.session_state.memory_flipped = []
                    st.rerun()

    # 버튼들
    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2 = st.columns([1,1])
    with b1:
        if st.button("⬅ Exit to Gallery"):
            st.session_state.mode = "gallery"
            st.rerun()
    with b2:
        if st.button("🏠 Home"):
            st.session_state.mode = "home"
            st.rerun()
