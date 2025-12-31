import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
from datetime import datetime

st.set_page_config(page_title="신성EP 샘플 관리 대장", layout="wide")

SHEET_ID = "1aHe7GQsPnZfMjZVPy4jt0elCEADKubWSSeonhZTKR9E"
WORKSHEET_NAME = "Form_Responses 1"  # Google Form 실제 응답 탭 이름

DEFAULT_COLUMNS = [
    "NO",
    "접수일",
    "업체명",
    "부서",
    "담당자",
    "차종",
    "품번",
    "품명",
    "출하장소",
    "요청수량",
    "납기일",
    "요청사항",
    "도면접수일",
    "자재 요청일",
    "자재준비",
    "샘플 완료일",
    "출하일",
    "운송편",
    "비고",
    "샘플단가",
    "샘플금액",
    "진행상태",
]

def get_credentials_info():
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        info = dict(st.secrets["connections"]["gsheets"])
    elif "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
    else:
        st.error("st.secrets 에 service account 정보가 없습니다.")
        st.stop()
    pk = info.get("private_key", "")
    if isinstance(pk, str) and "\\n" in pk:
        info["private_key"] = pk.replace("\\n", "\n")
    return info

@st.cache_resource
def get_worksheet():
    info = get_credentials_info()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SHEET_ID)
    if WORKSHEET_NAME:
        try:
            ws = sh.worksheet(WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=30)
            # 새 시트 생성 시 기본 헤더는 시트 구조에 맞게 설정
    else:
        ws = sh.sheet1
    return ws

def load_sheet_as_dataframe():
    ws = get_worksheet()
    values = ws.get_all_values()
    
    if not values:
        # 시트가 완전히 비어있을 경우에만 기본값을 사용 (최소한의 안전장치)
        df = pd.DataFrame(columns=["NO", "접수일", "업체명", "품명"]) 
        return df, ws

    # 2) 실제 헤더 행 찾기 (시트의 첫 번째 행을 헤더로 확정)
    # 구글 시트가 맞다고 하셨으므로 첫 번째 행(values[0])을 컬럼명으로 사용합니다.
    header = [str(h).strip() for h in values[0] if h] 
    data_rows = values[1:]

    # 3) 데이터프레임 생성
    df = pd.DataFrame(data_rows, columns=header)

    # 4) NO 컬럼 자동 부여 (앱 내 관리용)
    if "NO" in df.columns:
        df["NO"] = range(1, len(df) + 1)
    else:
        df.insert(0, "NO", range(1, len(df) + 1))

    # 5) 숫자 컬럼(수량, 금액 등) 자동 변환 로직
    # 시트의 제목열 이름에 맞춰서 필터링
    for col in df.columns:
        if any(keyword in col for keyword in ["수량", "단가", "금액", "가격"]):
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[^0-9.-]', '', regex=True), errors='coerce').fillna(0).astype(int)

    return df, ws

def save_dataframe_to_sheet(df: pd.DataFrame, ws):
    """
    개선된 저장 함수:
    1. 데이터 타입을 보존 (숫자는 숫자로)
    2. 불필요한 clear()를 피하고 batch_update를 고려
    """
    try:
        # 1. 시트의 기존 헤더 위치 탐색 (기존 로직 유지)
        values = ws.get_all_values()
        header_idx = 0
        for i, row in enumerate(values):
            row_stripped = [str(c).strip() for c in row]
            if "NO" in row_stripped and ("업체명" in row_stripped or "품명" in row_stripped):
                header_idx = i
                break
        
        # 2. 보존해야 할 상단 행(필터 등) 추출
        preserved_rows = values[:header_idx]
        
        # 3. 저장할 데이터 준비 (NaN 처리 및 타입 최적화)
        df_to_save = df.copy()
        # 숫자로 변환 가능한 컬럼들 처리
        num_cols = ["요청수량", "샘플단가", "샘플금액"]
        for col in num_cols:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_numeric(df_to_save[col], errors='coerce').fillna(0)

        # 날짜 컬럼 처리
        date_cols = ["접수일", "납기일", "도면접수일", "자재 요청일", "샘플 완료일", "출하일"]
        for col in date_cols:
            if col in df_to_save.columns:
                df_to_save[col] = df_to_save[col].apply(
                    lambda x: x.strftime("%Y-%m-%d") if hasattr(x, 'strftime') and x is not None else str(x) if x else ""
                )

        # NaN을 빈 문자열로 변환
        df_to_save = df_to_save.fillna("")

        # 헤더와 데이터 결합
        header = df_to_save.columns.tolist()
        data_body = df_to_save.values.tolist()
        
        # 4. 전체 데이터 구성
        final_output = preserved_rows + [header] + data_body
        
        # 5. [중요] clear() 후 바로 update() 하여 공백 시간을 최소화
        ws.clear()
        if final_output:
            ws.update('A1', final_output)
        
        return True
    except Exception as e:
        st.error(f"데이터 정합성 오류 발생: {e}")
        return False

def parse_date_safe(x):
    x = str(x).strip()
    if not x:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(x, fmt).date()
        except Exception:
            continue
    return None

# 논리적 중복 컬럼 제거: '요청수량'과 '요청수량_2' 같이 있으면 원본만 남기고 뒤의 것 삭제
def drop_logical_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    keep = []
    main_for_base = {}

    for col in cols:
        base = col
        # 뒤에 "_숫자"가 붙은 패턴이면 베이스 이름만 사용
        if "_" in col and col.rsplit("_", 1)[1].isdigit():
            base = col.rsplit("_", 1)[0]

        if base not in main_for_base:
            main_for_base[base] = col
            keep.append(col)
        else:
            # 이미 베이스가 있고,
            # 기존 메인 컬럼명이 "_숫자"로 끝나고,
            # 지금 컬럼명이 베이스 그대로라면 교체
            prev = main_for_base[base]
            if "_" in prev and prev.rsplit("_", 1)[1].isdigit() and prev != base and col == base:
                keep.remove(prev)
                keep.append(col)
                main_for_base[base] = col
            # 그 외의 경우는 버림 (중복 컬럼 제거)

    return df[keep]

# 간단 로그인 시스템 ---------------------------------
ADMIN_ID = "admin"
ADMIN_PW = "1234"

CLIENTS = {
    # 아이디: (비밀번호, 업체명)
    "infac": ("1234", "infac"),
    "sample": ("1234", "sample"),  # 필요하면 나중에 추가 / 수정
}

def require_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.client_name = None

    if st.session_state.logged_in:
        with st.sidebar:
            st.markdown(f"**접속자:** {st.session_state.role}")
            if st.session_state.role == "고객사" and st.session_state.client_name:
                st.markdown(f"**고객사:** {st.session_state.client_name}")
            if st.button("로그아웃"):
                st.session_state.logged_in = False
                st.session_state.role = None
                st.session_state.client_name = None
                st.rerun()
        return

    st.title("로그인")

    role = st.radio("역할을 선택하세요", ["관리자", "고객사"], key="login_role")
    user_id = st.text_input("아이디")
    user_pw = st.text_input("비밀번호", type="password")

    if st.button("로그인"):
        if role == "관리자":
            if user_id == ADMIN_ID and user_pw == ADMIN_PW:
                st.session_state.logged_in = True
                st.session_state.role = "관리자"
                st.session_state.client_name = None
                st.success("관리자 로그인 성공")
                st.rerun()
            else:
                st.error("관리자 아이디 또는 비밀번호가 올바르지 않습니다.")
        else:
            if user_id in CLIENTS and CLIENTS[user_id][0] == user_pw:
                st.session_state.logged_in = True
                st.session_state.role = "고객사"
                st.session_state.client_name = CLIENTS[user_id][1]
                st.success(f"고객사 '{st.session_state.client_name}' 로그인 성공")
                st.rerun()
            else:
                st.error("고객사 아이디 또는 비밀번호가 올바르지 않습니다.")

    st.stop()

def main():
    # 0) 로그인 체크 (미로그인 시 여기서 stop)
    require_login()

    # 1) 시트 데이터 로드
    df, ws = load_sheet_as_dataframe()

    # 논리적 중복 컬럼 제거 (ex: '요청수량', '요청수량_2')
    df = drop_logical_duplicate_columns(df)

    # 역할에 따라 데이터 필터링
    role = st.session_state.get("role")
    client_name = st.session_state.get("client_name")

    if role == "고객사" and client_name and "업체명" in df.columns:
        df = df[df["업체명"] == client_name].copy()

    st.caption(f"현재 시트 ID: {SHEET_ID}, 탭: {ws.title}")
    st.caption(f"현재 로그인: {role} / 표시 데이터: {len(df)}건")

    # 숫자 컬럼 이름
    qty_col = "요청수량" if "요청수량" in df.columns else ("수량" if "수량" in df.columns else None)
    price_cols = [c for c in ["샘플단가", "샘플금액"] if c in df.columns]

    # ----- 제목 필터 (대시보드 집계용) -----
    # 👉 이 입력창에 값을 넣으면, 아래 대시보드 숫자가 그 기준으로만 집계됩니다.
    stats_df = df.copy()
    if "제목" in stats_df.columns:
        title_filter = st.text_input(
            "제목 필터 (대시보드 집계용)",
            key="title_filter",
            placeholder="제목에 포함될 키워드를 입력하세요.",
        )
        if title_filter.strip():
            stats_df = stats_df[
                stats_df["제목"].astype(str).str.contains(title_filter, case=False, na=False)
            ].copy()

    # ----- 상단 대시보드 (한 줄에 모두 표시) -----
    st.subheader("📊 샘플 대시보드")

    # 총건수, 수량, 출하완료, 미납, 완료율, 납기지연 → 6개 한 줄
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    # 1) 총 샘플 건수
    with c1:
        st.metric("총 샘플 건수", f"{len(stats_df):,} 건")

    # 2) 총 요청 수량
    with c2:
        if qty_col and qty_col in stats_df.columns:
            total_qty = int(stats_df[qty_col].fillna(0).sum())
            st.metric("총 요청 수량", f"{total_qty:,.0f} EA")
        else:
            st.metric("총 요청 수량", "-")

    # 3) 출하완료 건수
    with c3:
        completed = 0
        if "진행상태" in stats_df.columns:
            completed = (stats_df["진행상태"].astype(str) == "출하완료").sum()
        st.metric("출하완료 건수", f"{completed:,} 건")

    # 4) 미납 건수 (= 전체 - 출하완료)
    with c4:
        pending = max(len(stats_df) - completed, 0)
        st.metric("미납 건수", f"{pending:,} 건")

    # 5) 완료율
    with c5:
        completion_rate = (completed / len(stats_df) * 100) if len(stats_df) > 0 else 0
        st.metric("완료율", f"{completion_rate:,.1f} %")

    # 6) 납기 지연 건수 (같은 줄에 표시)
    with c6:
        delayed = 0
        if "납기일" in stats_df.columns:
            today = datetime.today().date()
            dates = stats_df["납기일"].apply(parse_date_safe)
            mask = dates.notna()
            if "진행상태" in stats_df.columns:
                not_done = stats_df["진행상태"].astype(str) != "출하완료"
                delayed = ((dates < today) & mask & not_done).sum()
            else:
                delayed = ((dates < today) & mask).sum()
        st.metric("납기 지연 건수", f"{delayed:,} 건")

    st.markdown("---")
    st.subheader("📋 샘플 목록 편집")

    # 2) 편집용 데이터 준비 (에디터에 보이는 게 기준)
    edit_df = df.copy()
    column_config = {}

    # NO는 읽기 전용
    if "NO" in edit_df.columns:
        column_config["NO"] = st.column_config.NumberColumn("NO", disabled=True, format="%d")

    # 수량 컬럼
    if qty_col and qty_col in edit_df.columns:
        column_config[qty_col] = st.column_config.NumberColumn(qty_col, format="%,d")

    # 금액 컬럼
    for c in price_cols:
        column_config[c] = st.column_config.NumberColumn(c, format="%,.0f")

    # 운송편 컬럼
    if "운송편" in edit_df.columns:
        column_config["운송편"] = st.column_config.SelectboxColumn(
            "운송편",
            options=["", "항공", "선박", "핸드캐리"],
            required=False,
        )

    # ✅ 행 삭제용 체크박스 컬럼 추가
    if "_삭제" not in edit_df.columns:
        edit_df["_삭제"] = False
    column_config["_삭제"] = st.column_config.CheckboxColumn(
        "삭제",
        help="체크한 행은 저장 시 삭제됩니다.",
    )

    # 📋 여기서 사용자가 필터/정렬/수정/삭제 체크 모두 수행
    edited_df = st.data_editor(
        edit_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config=column_config,
        key="main_editor",
    )

    # 4) 저장 / 다시 불러오기
    b1, b2 = st.columns(2)
    with b1:
        if st.button("💾 변경 내용 저장", type="primary"):
            to_save = edited_df.copy()

            # 4-1) 삭제 체크된 행 제거
            if "_삭제" in to_save.columns:
                to_save = to_save[~to_save["_삭제"].fillna(False)].drop(columns=["_삭제"])

            # 4-2) 운송편 값 정리 (기존 로직 유지)
            if "운송편" in to_save.columns:
                valid = {"", "항공", "선박", "핸드캐리"}
                to_save["운송편"] = to_save["운송편"].fillna("")
                to_save["운송편"] = to_save["운송편"].apply(
                    lambda x: x if x in valid else str(x)
                )

            # 4-3) 수량/단가/금액 숫자 처리 (기존 로직 유지)
            if qty_col and qty_col in to_save.columns:
                to_save[qty_col] = (
                    to_save[qty_col]
                    .fillna(0)
                    .astype(str)
                    .str.replace(r"[^0-9\\-]", "", regex=True)
                    .replace("", "0")
                    .astype(int)
                )
            for c in price_cols:
                to_save[c] = (
                    to_save[c]
                    .fillna(0)
                    .astype(str)
                    .str.replace(r"[^0-9\\-]", "", regex=True)
                    .replace("", "0")
                    .astype(int)
                )

            # 4-4) 출하일 있으면 진행상태 자동 '출하완료'
            if "출하일" in to_save.columns and "진행상태" in to_save.columns:
                mask = to_save["출하일"].astype(str).str.strip() != ""
                to_save.loc[mask, "진행상태"] = "출하완료"

            # 4-5) 시트 저장
            ok = save_dataframe_to_sheet(to_save, ws)
            if ok:
                st.success("구글 시트에 저장되었습니다.")

    with b2:
        if st.button("🔄 시트 다시 불러오기"):
            st.rerun()

if __name__ == "__main__":
    main()
