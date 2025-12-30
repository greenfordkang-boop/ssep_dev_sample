import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
from datetime import datetime

# ================================
# 기본 설정
# ================================
st.set_page_config(page_title="신성EP 샘플 관리 대장", layout="wide")

# 구글 시트 ID
SHEET_ID = "1aHe7GQsPnZfMjZVPy4jt0elCEADKubWSSeonhZTKR9E"

# 특정 탭 이름 지정 (None이면 자동 탐색)
TARGET_WORKSHEET_TITLE = None

# 기본 컬럼 구조
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


# ================================
# 구글 인증
# ================================
def get_credentials_info():
    """st.secrets에서 서비스 계정 정보 가져오기"""
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        info = dict(st.secrets["connections"]["gsheets"])
    elif "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
    else:
        st.error("⚠️ st.secrets에 서비스 계정 정보가 없습니다.")
        st.stop()

    # private_key 처리 강화
    pk = info.get("private_key", "")
    if pk:
        if not isinstance(pk, str):
            pk = str(pk)
        
        # 이스케이프된 \n을 실제 줄바꿈으로 변환
        while "\\n" in pk:
            pk = pk.replace("\\n", "\n")
        
        # PEM 형식 검증
        if "-----BEGIN PRIVATE KEY-----" not in pk or "-----END PRIVATE KEY-----" not in pk:
            st.error("❌ private_key가 올바른 PEM 형식이 아닙니다.")
            st.stop()
        
        # BEGIN과 END 마커 사이의 내용 추출 및 정리
        begin_marker = "-----BEGIN PRIVATE KEY-----"
        end_marker = "-----END PRIVATE KEY-----"
        
        begin_idx = pk.find(begin_marker)
        end_idx = pk.find(end_marker)
        
        if begin_idx == -1 or end_idx == -1:
            st.error("❌ private_key의 BEGIN/END 마커를 찾을 수 없습니다.")
            st.stop()
        
        key_content = pk[begin_idx + len(begin_marker):end_idx].strip()
        key_content = "".join(key_content.split())
        
        # 올바른 PEM 형식으로 재구성 (64자마다 줄바꿈)
        formatted_key = begin_marker + "\n"
        for i in range(0, len(key_content), 64):
            formatted_key += key_content[i:i+64] + "\n"
        formatted_key += end_marker + "\n"
        
        info["private_key"] = formatted_key
    
    return info


@st.cache_resource
def get_gspread_client():
    """gspread 클라이언트 생성"""
    try:
        info = get_credentials_info()
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"❌ gspread 클라이언트 초기화 실패: {e}")
        st.stop()


# ================================
# 시트 선택 / 로드 / 저장
# ================================
def pick_worksheet():
    """시트 탭 선택 (자동 탐색 또는 지정된 탭)"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID)

        # 1) 지정된 탭 이름으로 찾기
        if TARGET_WORKSHEET_TITLE:
            try:
                ws = sh.worksheet(TARGET_WORKSHEET_TITLE)
                return ws
            except gspread.WorksheetNotFound:
                st.warning(f"⚠️ '{TARGET_WORKSHEET_TITLE}' 탭을 찾을 수 없습니다. 자동 탐색합니다.")

        # 2) 헤더 기반 자동 탐색
        candidates = ["NO", "업체명", "품명"]
        for ws in sh.worksheets():
            try:
                header = ws.row_values(1)
                header = [str(h).strip() for h in header]
                if any(c in header for c in candidates):
                    return ws
            except Exception:
                continue

        # 3) 첫 번째 탭 사용
        return sh.sheet1
    except Exception as e:
        st.error(f"❌ 시트 접근 실패: {e}")
        st.stop()


def parse_date_safe(x):
    """안전하게 날짜 문자열을 date 객체로 변환"""
    x = str(x).strip()
    if not x or x.lower() in ['nan', 'none', 'n/a', '']:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(x, fmt).date()
        except Exception:
            continue
    return None


def load_sheet_as_dataframe():
    """구글 시트 → DataFrame (데이터 자동 삭제 절대 안 함)"""
    try:
        ws = pick_worksheet()
        values = ws.get_all_values()

        if not values:
            df = pd.DataFrame(columns=DEFAULT_COLUMNS)
            return df, ws

        header = values[0]
        data_rows = values[1:]

        # 헤더가 비어있으면 기본 컬럼 사용
        if not any(str(h).strip() for h in header):
            header = DEFAULT_COLUMNS
            data_rows = []

        # 행 길이 맞추기
        max_len = len(header)
        normalized = []
        for row in data_rows:
            if len(row) < max_len:
                row = row + [""] * (max_len - len(row))
            else:
                row = row[:max_len]
            normalized.append(row)

        df = pd.DataFrame(normalized, columns=[str(h).strip() for h in header])

        # 기본 컬럼이 없으면 추가 (빈 값으로)
        for col in DEFAULT_COLUMNS:
            if col not in df.columns:
                df[col] = ""

        # NO 컬럼 처리 (고유 숫자 유지)
        if "NO" not in df.columns or df["NO"].isna().all() or (df["NO"] == "").all():
            df["NO"] = range(1, len(df) + 1)
        else:
            # 비어있는 NO 채우기
            df["NO"] = pd.to_numeric(df["NO"], errors="coerce")
            next_no = int(df["NO"].max()) + 1 if df["NO"].notna().any() else 1
            for i, v in df["NO"].items():
                if pd.isna(v):
                    df.at[i, "NO"] = next_no
                    next_no += 1
        df["NO"] = df["NO"].astype(int)

        # 숫자 컬럼 정리 (내부용)
        qty_col = None
        for c in ["요청수량", "수량"]:
            if c in df.columns:
                qty_col = c
                break

        price_cols = [c for c in ["샘플단가", "샘플금액"] if c in df.columns]

        if qty_col:
            df[qty_col] = (
                df[qty_col]
                .replace("", 0)
                .fillna(0)
                .astype(str)
                .str.replace(r"[^0-9\-]", "", regex=True)
                .replace("", "0")
                .astype(int)
            )

        for c in price_cols:
            df[c] = (
                df[c]
                .replace("", 0)
                .fillna(0)
                .astype(str)
                .str.replace(r"[^0-9\-]", "", regex=True)
                .replace("", "0")
                .astype(int)
            )

        # 날짜 컬럼 처리
        date_cols = ["접수일", "납기일", "도면접수일", "자재 요청일", "샘플 완료일", "출하일"]
        for col in date_cols:
            if col in df.columns:
                df[col] = df[col].apply(parse_date_safe)

        return df, ws
    except Exception as e:
        st.error(f"❌ 데이터 로드 실패: {e}")
        return pd.DataFrame(columns=DEFAULT_COLUMNS), None


def save_dataframe_to_sheet(df: pd.DataFrame, ws):
    """DataFrame → 구글 시트 전체 덮어쓰기 (데이터 자동 삭제 절대 안 함)"""
    try:
        df_to_save = df.copy()

        # NaN → "" 변환
        df_to_save = df_to_save.fillna("")

        # 날짜 컬럼을 문자열로 변환
        date_cols = ["접수일", "납기일", "도면접수일", "자재 요청일", "샘플 완료일", "출하일"]
        for col in date_cols:
            if col in df_to_save.columns:
                df_to_save[col] = df_to_save[col].apply(
                    lambda x: x.strftime("%Y-%m-%d") if hasattr(x, 'strftime') and x is not None else str(x) if x else ""
                )

        # 헤더와 데이터 준비
        header = list(df_to_save.columns)
        data = df_to_save.astype(str).values.tolist()

        # 전체 덮어쓰기
        ws.clear()
        ws.append_row(header)
        if data:
            ws.append_rows(data)
        return True
    except Exception as e:
        st.error(f"⚠️ 구글 시트 저장 실패: {e}")
        return False


# ================================
# 메인 UI
# ================================
def main():
    st.title("🏭 신성EP 샘플 관리 대장")

    # 데이터 로드
    if "df" not in st.session_state or "ws_title" not in st.session_state:
        df, ws = load_sheet_as_dataframe()
        st.session_state.df = df
        st.session_state.ws_title = ws.title if ws else ""
        st.session_state.ws = ws
    else:
        df = st.session_state.df
        ws = st.session_state.get("ws") or pick_worksheet()

    st.caption(f"현재 연결된 시트 ID: {SHEET_ID}, 탭: {st.session_state.ws_title}")
    st.caption(f"로드된 데이터: {len(df)}행, {len(df.columns)}개 컬럼")

    # 숫자 컬럼 이름 찾기
    qty_col = "요청수량" if "요청수량" in df.columns else ("수량" if "수량" in df.columns else None)
    price_cols = [c for c in ["샘플단가", "샘플금액"] if c in df.columns]

    # ----- 상단 대시보드 -----
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("총 샘플 건수", f"{len(df):,} 건")

    with col2:
        if qty_col:
            total_qty = int(df[qty_col].fillna(0).sum())
            st.metric("총 요청 수량", f"{total_qty:,.0f} EA")
        else:
            st.metric("총 요청 수량", "설정 필요")

    with col3:
        completed = 0
        if "진행상태" in df.columns:
            completed = (df["진행상태"].astype(str) == "완료").sum()
        st.metric("완료 건수", f"{completed:,} 건")

    with col4:
        delayed = 0
        if "납기일" in df.columns:
            today = datetime.today().date()
            dates = df["납기일"]
            mask = dates.notna()
            if "진행상태" in df.columns:
                not_done = df["진행상태"].astype(str) != "완료"
                delayed = ((dates < today) & mask & not_done).sum()
            else:
                delayed = ((dates < today) & mask).sum()
        st.metric("납기 지연 건수", f"{delayed:,} 건")

    st.markdown("---")
    st.subheader("📋 샘플 목록 / 관리")

    # ----- 편집용 DF -----
    edit_df = df.copy()

    # 컬럼 설정
    column_config = {}

    # NO는 읽기 전용
    if "NO" in edit_df.columns:
        column_config["NO"] = st.column_config.NumberColumn("NO", format="%d", disabled=True)

    # 날짜 컬럼
    date_cols = ["접수일", "납기일", "도면접수일", "자재 요청일", "샘플 완료일", "출하일"]
    for col in date_cols:
        if col in edit_df.columns:
            column_config[col] = st.column_config.DateColumn(col)

    # 운송편: SelectboxColumn (항공/선박/핸드캐리만 선택 가능)
    if "운송편" in edit_df.columns:
        column_config["운송편"] = st.column_config.SelectboxColumn(
            "운송편",
            options=["", "항공", "선박", "핸드캐리"],
            required=False,
        )

    # 숫자 컬럼 포맷 (천단위 콤마)
    if qty_col and qty_col in edit_df.columns:
        column_config[qty_col] = st.column_config.NumberColumn(qty_col, format="%,d")
    for c in price_cols:
        if c in edit_df.columns:
            column_config[c] = st.column_config.NumberColumn(c, format="%,.0f")

    # 데이터 에디터
    edited_df = st.data_editor(
        edit_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config=column_config,
        key="main_editor",
    )

    st.markdown("")

    # ----- 버튼 영역 -----
    btn1, btn2 = st.columns(2)

    with btn1:
        if st.button("💾 변경 내용 저장", type="primary", use_container_width=True):
            # 운송편 값 정리 (옵션 외 값은 그대로 유지)
            if "운송편" in edited_df.columns:
                valid_opts = {"", "항공", "선박", "핸드캐리"}
                edited_df["운송편"] = edited_df["운송편"].fillna("")
                edited_df["운송편"] = edited_df["운송편"].apply(
                    lambda x: x if x in valid_opts else str(x)
                )

            # 숫자 컬럼 재정리 (문자 제거 후 int 변환)
            if qty_col and qty_col in edited_df.columns:
                edited_df[qty_col] = (
                    edited_df[qty_col]
                    .fillna(0)
                    .astype(str)
                    .str.replace(r"[^0-9\-]", "", regex=True)
                    .replace("", "0")
                    .astype(int)
                )
            for c in price_cols:
                if c in edited_df.columns:
                    edited_df[c] = (
                        edited_df[c]
                        .fillna(0)
                        .astype(str)
                        .str.replace(r"[^0-9\-]", "", regex=True)
                        .replace("", "0")
                        .astype(int)
                    )

            # NO 컬럼 고유성 유지 (중복 체크)
            if "NO" in edited_df.columns:
                # 빈 NO 채우기
                edited_df["NO"] = pd.to_numeric(edited_df["NO"], errors="coerce")
                next_no = int(edited_df["NO"].max()) + 1 if edited_df["NO"].notna().any() else 1
                for i, v in edited_df["NO"].items():
                    if pd.isna(v):
                        edited_df.at[i, "NO"] = next_no
                        next_no += 1
                edited_df["NO"] = edited_df["NO"].astype(int)

            # 세션에 반영
            st.session_state.df = edited_df

            # 구글 시트에 저장
            ok = save_dataframe_to_sheet(edited_df, ws)
            if ok:
                st.success("✅ 구글 시트에 저장되었습니다.")
                st.rerun()
            else:
                st.error("⚠️ 저장 중 오류가 발생했습니다.")

    with btn2:
        if st.button("🔄 구글 시트에서 다시 불러오기", use_container_width=True):
            new_df, new_ws = load_sheet_as_dataframe()
            st.session_state.df = new_df
            st.session_state.ws_title = new_ws.title if new_ws else ""
            st.session_state.ws = new_ws
            st.success("🔄 최신 데이터를 다시 불러왔습니다.")
            st.rerun()


if __name__ == "__main__":
    main()
