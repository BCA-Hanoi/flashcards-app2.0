import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
from streamlit_js_eval import streamlit_js_eval

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
    st.subheader("Type words (comma separated), then press Enter.")

    words = st.text_input(
        "Flashcards",
        placeholder="e.g., bucket, apple, maze, rabbit",
        label_visibility="collapsed",
        key="word_input"
    )

    if words:
        all_files = get_files_from_folder(FOLDER_ID)

        # 확장자 제거 + 소문자 변환
        file_map = {
            f["name"].rsplit(".", 1)[0].strip().lower(): f["id"]
            for f in all_files
        }

        selected = []
        for w in [w.strip().lower() for w in words.split(",")]:
            if w in file_map:
                # ✅ 썸네일 API 사용 (sz=w1000 : 최대 1000px)
                selected.append(
                    f"https://drive.google.com/thumbnail?id={file_map[w]}&sz=w1000"
                )

        if selected:
            st.session_state.cards = selected
            st.session_state.mode = "gallery"
            st.rerun()
        else:
            st.warning("⚠️ No matching flashcards found. Try again.")


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
    if "selected_cards" not in st.session_state:
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
                file_map = {f["name"].rsplit(".", 1)[0].strip().lower(): f["id"] for f in all_files}
                to_add = []
                for w in [w.strip().lower() for w in new_words.split(",")]:
                    if w in file_map:
                        to_add.append(f"https://drive.google.com/thumbnail?id={file_map[w]}&sz=w1000")

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
                default_checked = st.session_state.get(f"chk_{i}", url in st.session_state.selected_cards)
                checked = st.checkbox(f"Card {i+1}", key=f"chk_{i}", value=default_checked)
                if checked:
                    new_selection.append(url)

        st.session_state.selected_cards = new_selection

        # -------------------------
        # 버튼 (왼쪽 정렬)
        # -------------------------
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, _ = st.columns([1,1,6])  # 버튼 2개 왼쪽, 나머지 공간 비움
        with col1:
            if st.button("▶ Presentation"):
                if st.session_state.selected_cards:
                    st.session_state.cards = st.session_state.selected_cards.copy()
                st.session_state.mode = "present"
                st.session_state.current = 0
                st.rerun()
        with col2:
            if st.button("🏠 Back to Home"):
                st.session_state.mode = "home"
                st.rerun()
    else:
        st.warning("⚠️ No cards loaded. Please go back and try again.")


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
