import time
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


@st.cache_data(ttl=300, show_spinner=False)
def get_files_from_folder(folder_id: str):
    """폴더 안의 모든 이미지 파일 가져오기 (5분 캐시)"""
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
        batch = results.get("files", [])
        for f in batch:
            if f.get("id") and f.get("name"):
                files.append({"id": f["id"], "name": f["name"]})
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    return files


def to_thumb(file_id: str, width: int = 1000) -> str:
    """Google Drive 썸네일 URL 생성"""
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{width}"


# ==============================
# Streamlit UI 설정 & 상태
# ==============================
st.set_page_config(page_title="BCA Flashcards", layout="wide")

if "mode" not in st.session_state:
    st.session_state.mode = "home"
if "cards" not in st.session_state:
    st.session_state.cards = []                 # 현재 표시/사용 중인 카드(썸네일 URL 목록)
if "current" not in st.session_state:
    st.session_state.current = 0                # 프레젠테이션 인덱스
if "selected_cards" not in st.session_state:
    st.session_state.selected_cards = []        # 갤러리에서 체크된 카드

# GAME용 상태
if "cards_backup" not in st.session_state:
    st.session_state.cards_backup = None        # 랜덤 2/3장 실행 전 원본 cards 보관
if "memory_deck" not in st.session_state:
    st.session_state.memory_deck = []           # 메모리 게임용 덱 (URL 리스트)
if "memory_flipped" not in st.session_state:
    st.session_state.memory_flipped = []        # 이번 턴에 뒤집힌 인덱스(최대 2)
if "memory_matched" not in st.session_state:
    st.session_state.memory_matched = []        # 매칭된 카드 인덱스들

# Auto-play 상태
if "auto_play" not in st.session_state:
    st.session_state.auto_play = False          # 자동 넘김 토글
if "auto_interval" not in st.session_state:
    st.session_state.auto_interval = 3          # 자동 넘김 간격(초)


# ==============================
# 1단계: 단어 입력 화면
# ==============================
if st.session_state.mode == "home":
    st.title("BCA Flashcards")
    st.subheader("Type words (comma separated), then press Enter.")

    words = st.text_input(
        "Flashcards",
        placeholder="e.g., bucket, apple, maze, rabbit",
        label_visibility="collapsed",
        key="word_input"
    )

    if words:
        all_files = get_files_from_folder(FOLDER_ID)

        # 확장자 제거 + 소문자 변환 맵 구축
        file_map = {
            f["name"].rsplit(".", 1)[0].strip().lower(): f["id"]
            for f in all_files
            if f.get("name")
        }

        # 공백/빈 토큰 제거
        tokens = [t.strip().lower() for t in words.split(",") if t.strip()]

        selected = []
        for w in tokens:
            if w in file_map:
                selected.append(to_thumb(file_map[w]))

        if selected:
            # 다음 화면에서 선택 체크박스 기본값으로 쓰기 위해 복사
            st.session_state.cards = selected
            st.session_state.selected_cards = selected.copy()
            st.session_state.current = 0
            st.session_state.mode = "gallery"
            st.rerun()
        else:
            st.warning("⚠️ No matching flashcards found in the Drive folder. Try different words.")


# ==============================
# 2단계: 갤러리 미리보기 화면
# ==============================
elif st.session_state.mode == "gallery":
    st.title("BCA Flashcards")
    st.subheader("Preview your flashcards below. Select the ones you want for presentation.")

    # -------------------------
    # Add More 입력창 토글
    # -------------------------
    if "show_input" not in st.session_state:
        st.session_state.show_input = False
    # 갤러리 첫 진입 시 선택 기본값을 cards로
    if not st.session_state.selected_cards and st.session_state.cards:
        st.session_state.selected_cards = st.session_state.cards.copy()

    if st.button("➕ Add More"):
        st.session_state.show_input = not st.session_state.show_input
        st.rerun()

    if st.session_state.show_input:
        new_words = st.text_input(
            "Add Flashcards",
            placeholder="e.g., rabbit, lion, sun",
            label_visibility="collapsed",
            key="word_input_gallery"
        )
        if st.button("Add Now"):
            if new_words:
                all_files = get_files_from_folder(FOLDER_ID)
                file_map = {
                    f["name"].rsplit(".", 1)[0].strip().lower(): f["id"]
                    for f in all_files
                    if f.get("name")
                }
                to_add = []
                for w in [w.strip().lower() for w in new_words.split(",") if w.strip()]:
                    if w in file_map:
                        to_add.append(to_thumb(file_map[w]))

                if to_add:
                    # 중복 제거 + 순서 유지
                    st.session_state.cards = list(dict.fromkeys(st.session_state.cards + to_add))

            st.session_state.show_input = False
            st.rerun()

    # -------------------------
    # 갤러리
    # -------------------------
    if st.session_state.cards:
        new_selection = []
        num_cols = 8   # 🔹 기본 8열
        cols = st.columns(num_cols)

        for i, url in enumerate(st.session_state.cards):
            with cols[i % num_cols]:
                st.image(url, use_container_width=True)
                # 이전 선택값을 기본값으로 사용
                default_checked = url in st.session_state.selected_cards
                checked = st.checkbox(f"Card {i+1}", key=f"chk_{i}", value=default_checked)
                if checked:
                    new_selection.append(url)

        # 현재 보이는 모든 체크 상태를 반영
        st.session_state.selected_cards = new_selection

        # -------------------------
        # 버튼 (왼쪽 정렬) + GAME 드롭다운
        # -------------------------
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1.5, 6])

        # ▶ Presentation (기본)
        with col1:
            if st.button("▶ Presentation"):
                # 선택한 카드가 있으면 그것만, 아니면 전체 사용
                st.session_state.cards = st.session_state.selected_cards or st.session_state.cards
                if not st.session_state.cards:
                    st.warning("⚠️ No cards to present.")
                else:
                    st.session_state.current = 0
                    st.session_state.mode = "present"
                    st.rerun()

        # 🎮 GAME 드롭다운 (Presentation 옆)
        with col2:
            choice = st.selectbox(
                "GAME",
                ["메뉴 선택", "랜덤 2장", "랜덤 3장", "메모리 게임 (2 pairs)"],
                index=0,
                key="game_choice"
            )
            start_game = st.button("Start")

            if start_game and choice != "메뉴 선택":
                base = st.session_state.selected_cards or st.session_state.cards
                if not base:
                    st.warning("⚠️ 먼저 카드들을 불러오거나 선택해줘.")
                else:
                    if choice == "랜덤 2장":
                        if len(base) < 2:
                            st.warning("⚠️ 최소 2장이 필요해.")
                        else:
                            st.session_state.cards_backup = st.session_state.cards.copy()
                            st.session_state.cards = random.sample(base, 2)
                            st.session_state.current = 0
                            st.session_state.mode = "present"
                            # 오토플레이 초기화
                            st.session_state.auto_play = False
                            st.rerun()

                    elif choice == "랜덤 3장":
                        if len(base) < 3:
                            st.warning("⚠️ 최소 3장이 필요해.")
                        else:
                            st.session_state.cards_backup = st.session_state.cards.copy()
                            st.session_state.cards = random.sample(base, 3)
                            st.session_state.current = 0
                            st.session_state.mode = "present"
                            st.session_state.auto_play = False
                            st.rerun()

                    elif choice == "메모리 게임 (2 pairs)":
                        if len(base) < 2:
                            st.warning("⚠️ 최소 서로 다른 카드 2장이 필요해.")
                        else:
                            p = random.sample(base, 2)
                            deck = p * 2
                            random.shuffle(deck)
                            st.session_state.memory_deck = deck
                            st.session_state.memory_flipped = []
                            st.session_state.memory_matched = []
                            st.session_state.mode = "memory_game"
                            # 오토플레이는 프레젠테이션 전용이므로 끔
                            st.session_state.auto_play = False
                            st.rerun()

        # 홈으로
        with col3:
            if st.button("🏠 Back to Home"):
                st.session_state.mode = "home"
                st.rerun()

    else:
        st.warning("⚠️ No cards loaded. Please go back and try again.")


# ==============================
# 3단계: Presentation 전체화면 모드 (+ 자동 넘김)
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

        # 컨트롤 1줄: Prev / Exit / Next
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("◀ Prev", use_container_width=True):
                st.session_state.current = (st.session_state.current - 1) % len(st.session_state.cards)
                st.rerun()
        with c2:
            if st.button("Exit", use_container_width=True):
                # 랜덤 2/3장으로 들어왔으면 원본 복구
                if st.session_state.cards_backup:
                    st.session_state.cards = st.session_state.cards_backup
                    st.session_state.cards_backup = None
                # 오토플레이 끄기
                st.session_state.auto_play = False
                st.session_state.mode = "gallery"
                st.rerun()
        with c3:
            if st.button("Next ▶", use_container_width=True):
                st.session_state.current = (st.session_state.current + 1) % len(st.session_state.cards)
                st.rerun()

        # 컨트롤 2줄: Auto ▶ / Interval
        c4, c5 = st.columns([1, 3])
        with c4:
            st.session_state.auto_play = st.toggle("Auto ▶ (자동 넘김)", value=st.session_state.auto_play)
        with c5:
            st.session_state.auto_interval = st.slider(
                "Interval (seconds)",
                min_value=1, max_value=20, value=st.session_state.auto_interval, step=1
            )

        # 오토플레이 수행 (서버 사이드 sleep → 다음 카드로 이동 후 rerun)
        if st.session_state.auto_play and len(st.session_state.cards) > 0:
            time.sleep(st.session_state.auto_interval)
            st.session_state.current = (st.session_state.current + 1) % len(st.session_state.cards)
            st.rerun()
    else:
        st.info("No cards to present. Go back to Gallery.")


# ==============================
# 4단계: 메모리 게임 (2 pairs)
# ==============================
elif st.session_state.mode == "memory_game":
    st.title("🎮 Memory Game — 2 Pairs")

    deck = st.session_state.memory_deck  # 총 4장 (2쌍), 섞여 있음
    if not deck:
        st.info("덱이 비어 있어. 갤러리에서 GAME → 메모리 게임(2 pairs)로 시작해줘.")
    else:
        cols = st.columns(2)  # 2x2 배치
        for i, url in enumerate(deck):
            with cols[i % 2]:
                if i in st.session_state.memory_matched or i in st.session_state.memory_flipped:
                    st.image(url, use_container_width=True)
                else:
                    if st.button(f"Card {i+1}", key=f"mem_{i}"):
                        st.session_state.memory_flipped.append(i)
                        # 두 장 뒤집혔으면 판정
                        if len(st.session_state.memory_flipped) == 2:
                            i1, i2 = st.session_state.memory_flipped
                            if deck[i1] == deck[i2]:
                                st.session_state.memory_matched.extend([i1, i2])
                            st.session_state.memory_flipped = []
                        st.rerun()

        matched = len(st.session_state.memory_matched) // 2
        st.markdown(f"**Matched:** {matched}/2")

        if matched == 2:
            st.success("🎉 All matched!")

    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    with b1:
        if st.button("⬅ Exit to Gallery"):
            st.session_state.mode = "gallery"
            st.rerun()
    with b2:
        if st.button("🏠 Home"):
            st.session_state.mode = "home"
            st.rerun()
