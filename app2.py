import re
import math
import random
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account

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
    """
    t = token.strip().lower()
    if not t:
        return []
    pattern = re.compile(rf'(?<![a-z]){re.escape(t)}\d+(?![a-z])')
    return [n for n in norms if pattern.search(n)]

# ==============================
# Streamlit UI 상태
# ==============================
st.set_page_config(page_title="BCA Flashcards", layout="wide")

if "mode" not in st.session_state:
    st.session_state.mode = "home"
if "cards" not in st.session_state:
    st.session_state.cards = []              # 썸네일 URL 리스트 (전체)
if "selected_cards" not in st.session_state:
    st.session_state.selected_cards = []     # 갤러리에서 체크된 것
if "current" not in st.session_state:
    st.session_state.current = 0             # present index
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "All"       # Gallery: All / 3-per
if "page" not in st.session_state:
    st.session_state.page = 0                # Gallery 3-per page
if "present_triplet" not in st.session_state:
    st.session_state.present_triplet = False # Present 3-up view
if "tries" not in st.session_state:
    st.session_state.tries = 0               # Memory tries
if "memory_deck" not in st.session_state:
    st.session_state.memory_deck = []        # Memory deck (urls)
if "memory_flipped" not in st.session_state:
    st.session_state.memory_flipped = []     # indices of flipped this turn
if "memory_matched" not in st.session_state:
    st.session_state.memory_matched = []     # indices matched

# ==============================
# 1단계: 단어 입력 화면
# ==============================
if st.session_state.mode == "home":
    st.title("BCA Flashcards")
    st.subheader("Type words (comma separated) → only `word+number` filenames are used.")

    words = st.text_input(
        "Flashcards",
        placeholder="e.g., land, cat, apple",
        label_visibility="collapsed",
        key="word_input"
    )

    col_a, col_b = st.columns([1,1])
    with col_a:
        if st.button("Search"):
            if words:
                files = list_drive_files(FOLDER_ID)
                id_by_norm, _ = build_maps(files)
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

                if selected:
                    st.session_state.cards = selected
                    st.session_state.selected_cards = selected.copy()
                    st.session_state.mode = "gallery"
                    st.session_state.page = 0
                    st.session_state.current = 0
                    st.rerun()
                else:
                    st.warning("⚠️ No matching flashcards for the word+number pattern.")

    with col_b:
        if st.button("Clear"):
            st.session_state.cards = []
            st.session_state.selected_cards = []
            st.session_state.page = 0
            st.rerun()

# ==============================
# 2단계: 갤러리 미리보기 화면
# ==============================
elif st.session_state.mode == "gallery":
    st.title("BCA Flashcards")
    st.subheader("Preview your flashcards. Select for presentation or memory game.")

    # ----- 상단 컨트롤 바 -----
    c1, c2, c3, c4, c5 = st.columns([1,1,1,1,2])
    with c1:
        st.session_state.view_mode = st.selectbox("View", options=["All", "3 per page"], index=0 if st.session_state.view_mode=="All" else 1)
    with c2:
        if st.button("🔀 Shuffle"):
            random.shuffle(st.session_state.cards)
            # 선택 상태도 동일한 순서로 재정렬(선택 유지)
            current_set = set(st.session_state.selected_cards)
            st.session_state.selected_cards = [c for c in st.session_state.cards if c in current_set]
            # 페이지/프레젠트 인덱스 리셋
            st.session_state.page = 0
            st.session_state.current = 0
            st.rerun()
    with c3:
        if st.button("🏠 Home"):
            st.session_state.mode = "home"
            st.rerun()
    with c4:
        # 메모리 게임용 페어 수 선택(선택된 카드 기반)
        max_pairs = max(1, min(12, len(st.session_state.selected_cards)//1))  # 한 장당 1페어로 해도 되고, 아래에서 2배가 됨
        pairs = st.number_input("Pairs", min_value=1, max_value=min(12, max_pairs), value=min(6, max_pairs), step=1)
    with c5:
        pass

    # ----- 갤러리 표시 -----
    cards = st.session_state.cards
    show_cards = cards
    if st.session_state.view_mode == "3 per page":
        total = len(cards)
        pages = max(1, math.ceil(total / 3))
        st.markdown(f"**Page** {st.session_state.page+1} / {pages}")
        start = st.session_state.page * 3
        end = start + 3
        show_cards = cards[start:end]

    # 그리드 그리기
    if show_cards:
        # 3-per면 3열, 전체면 8열
        num_cols = 3 if st.session_state.view_mode == "3 per page" else 8
        cols = st.columns(num_cols)
        new_selection = []
        for i, url in enumerate(show_cards):
            # 실제 인덱스 (전체 기준)
            real_idx = cards.index(url)
            with cols[i % num_cols]:
                st.image(url, use_container_width=True)
                key = f"chk_{real_idx}"
                default_checked = st.session_state.get(key, url in st.session_state.selected_cards)
                checked = st.checkbox(f"Card {real_idx+1}", key=key, value=default_checked)
                if checked:
                    new_selection.append(url)

        # 전체 기준으로 선택 업데이트
        # 체크박스는 현재 보이는 카드만 컨트롤되므로 기존 선택 + 현재 새 체크 결과를 통합
        # 우선 현재 보이는 카드의 체크 결과를 반영
        current_visible_set = set(show_cards)
        merged = []
        for c in cards:
            if c in current_visible_set:
                if c in new_selection:
                    merged.append(c)
            else:
                if c in st.session_state.selected_cards:
                    merged.append(c)
        st.session_state.selected_cards = merged

    # ----- 페이지 네비게이션 -----
    if st.session_state.view_mode == "3 per page" and cards:
        total = len(cards)
        pages = max(1, math.ceil(total / 3))
        p1, p2, p3 = st.columns([1,1,6])
        with p1:
            if st.button("◀ Prev Page"):
                st.session_state.page = (st.session_state.page - 1) % pages
                st.rerun()
        with p2:
            if st.button("Next Page ▶"):
                st.session_state.page = (st.session_state.page + 1) % pages
                st.rerun()

    st.markdown("---")
    # ----- 액션 버튼들 -----
    a1, a2, a3, a4 = st.columns([1,1,2,2])
    with a1:
        if st.button("▶ Presentation"):
            st.session_state.mode = "present"
            st.session_state.current = 0
            st.rerun()
    with a2:
        if st.button("🔀 Shuffle & Start"):
            random.shuffle(st.session_state.cards)
            st.session_state.current = 0
            st.session_state.mode = "present"
            st.rerun()
    with a3:
        st.session_state.present_triplet = st.toggle("3장 뷰 (Presentation)", value=st.session_state.present_triplet)
    with a4:
        if st.button("🎮 Memory Game"):
            # 선택된 카드에서 pairs 만큼 샘플 → 각 카드 2장씩 만들어 덱 구성
            base = st.session_state.selected_cards or st.session_state.cards
            if len(base) == 0:
                st.warning("⚠️ Select at least 1 card.")
            else:
                k = min(int(pairs), len(base))
                sample = random.sample(base, k=k)
                deck = sample * 2
                random.shuffle(deck)
                st.session_state.memory_deck = deck
                st.session_state.memory_flipped = []
                st.session_state.memory_matched = []
                st.session_state.tries = 0
                st.session_state.mode = "memory_game"
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

    cards = st.session_state.cards
    if cards:
        if st.session_state.present_triplet:
            # 3장 뷰
            idx = st.session_state.current
            show = [cards[idx % len(cards)],
                    cards[(idx+1) % len(cards)],
                    cards[(idx+2) % len(cards)]]
            cols = st.columns(3)
            for i, url in enumerate(show):
                with cols[i]:
                    st.markdown(f"<div class='present-img'><img src='{url}'></div>", unsafe_allow_html=True)
        else:
            # 1장 뷰
            url = cards[st.session_state.current]
            st.markdown(f"<div class='present-img'><img src='{url}'></div>", unsafe_allow_html=True)

        # 컨트롤
        col1, col2, col3 = st.columns([1,1,1])
        with col1:
            if st.button("◀ Prev", use_container_width=True):
                step = 3 if st.session_state.present_triplet else 1
                st.session_state.current = (st.session_state.current - step) % len(cards)
                st.rerun()
        with col2:
            if st.button("Exit", use_container_width=True):
                st.session_state.mode = "gallery"
                st.rerun()
        with col3:
            if st.button("Next ▶", use_container_width=True):
                step = 3 if st.session_state.present_triplet else 1
                st.session_state.current = (st.session_state.current + step) % len(cards)
                st.rerun()

# ==============================
# 4단계: 메모리 게임 모드 (업그레이드)
# ==============================
elif st.session_state.mode == "memory_game":
    st.title("🎮 Memory Game")

    deck = st.session_state.memory_deck  # url 리스트 (페어 2배 후 셔플된 상태)
    if not deck:
        st.info("No memory deck. Go back to Gallery and start the Memory Game.")
    else:
        cols = st.columns(4)
        for i, url in enumerate(deck):
            with cols[i % 4]:
                if i in st.session_state.memory_matched or i in st.session_state.memory_flipped:
                    st.image(url, use_container_width=True)
                else:
                    if st.button(f"Card {i+1}", key=f"mem_{i}"):
                        st.session_state.memory_flipped.append(i)
                        if len(st.session_state.memory_flipped) == 2:
                            i1, i2 = st.session_state.memory_flipped
                            st.session_state.tries += 1
                            # 같은 이미지면 매칭
                            if deck[i1] == deck[i2]:
                                st.session_state.memory_matched.extend([i1, i2])
                            st.session_state.memory_flipped = []
                        st.rerun()

        # 상태 바
        matched_pairs = len(st.session_state.memory_matched) // 2
        total_pairs = len(deck) // 2
        st.markdown(f"**Matched:** {matched_pairs}/{total_pairs}  |  **Tries:** {st.session_state.tries}")

        if matched_pairs == total_pairs and total_pairs > 0:
            st.success("🎉 All matched! Great memory!")

    # 버튼들
    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2, b3 = st.columns([1,1,1])
    with b1:
        if st.button("🔀 Reshuffle"):
            random.shuffle(st.session_state.memory_deck)
            st.session_state.memory_flipped = []
            st.session_state.memory_matched = []
            st.session_state.tries = 0
            st.rerun()
    with b2:
        if st.button("⬅ Exit to Gallery"):
            st.session_state.mode = "gallery"
            st.rerun()
    with b3:
        if st.button("🏠 Home"):
            st.session_state.mode = "home"
            st.rerun()
