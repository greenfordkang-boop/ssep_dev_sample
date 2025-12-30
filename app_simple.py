import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
from datetime import datetime

# ----------------------------
# 기본 설정
# ----------------------------
st.set_page_config(page_title="신성EP 샘플 관리 대장", layout="wide")

# 샘플관리대장 구글 시트 ID
SHEET_ID = "1aHe7GQsPnZfMjZVPy4jt0elCEADKubWSSeonhZTKR9E"
# 어떤 탭을 쓸지: None 이면 첫 번째 탭(sheet1)
WORKSHEET_NAME = None  # 예: "Form_Responses" 로 고정하고 싶으면 문자열로 지정

# 기본 컬럼 세트 (시트가 비어있을 때 사용)
DEFAULT_COLUMNS = [
    "NO",
    "접수일",
    "업체명",
    "품번",
    "품명",
    "차종",
    "요청수량",
    "납기일",
    "요청사항",
    "샘플단가",
    "샘플금액",
    "운송편",
    "비고",
]


# ----------------------------
# 구글 인증 및 시트 접근
# ----------------------------
def get_credentials_info():
    """
    st.secrets 에서 서비스 계정 정보를 가져온다.
    private_key 의 \\n 문제도 같이 해결.
    """
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        creds_info = dict(st.secrets["connections"]["gsheets"])
    elif "gcp_service_account" in st.secrets:
        creds_info = dict(st.secrets["gcp_service_account"])
    else:
        st.error("st.secrets 에 service account 정보가 없습니다.")
        st.stop()

    pk = creds_info.get("private_key", "")
    # 백슬래시 n 으로 들어온 경우 실제 줄바꿈으로 치환
    if "\\n" in pk:
        creds_info["private_key"] = pk.replace("\\n", "\n")
    
    # 더 강력한 private_key 처리 (기존 app.py 로직 반영)
    if "private_key" in creds_info:
        private_key = creds_info["private_key"]
        
        # 문자열이 아닌 경우 문자열로 변환
        if not isinstance(private_key, str):
            private_key = str(private_key)
        
        # 이스케이프된 \n을 실제 줄바꿈으로 변환 (여러 번 반복)
        while "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")
        
        # PEM 형식 검증
        if "-----BEGIN PRIVATE KEY-----" not in private_key or "-----END PRIVATE KEY-----" not in private_key:
            st.error("❌ private_key가 올바른 PEM 형식이 아닙니다.")
            st.stop()
        
        # BEGIN과 END 마커 사이의 내용만 추출하여 정리
        begin_marker = "-----BEGIN PRIVATE KEY-----"
        end_marker = "-----END PRIVATE KEY-----"
        
        begin_idx = private_key.find(begin_marker)
        end_idx = private_key.find(end_marker)
        
        if begin_idx == -1 or end_idx == -1:
            st.error("❌ private_key의 BEGIN/END 마커를 찾을 수 없습니다.")
            st.stop()
        
        # 마커와 키 내용 추출
        key_content = private_key[begin_idx + len(begin_marker):end_idx].strip()
        
        # 키 내용에서 공백과 줄바꿈 정리 (base64 문자열만 남김)
        key_content = "".join(key_content.split())
        
        # 올바른 PEM 형식으로 재구성 (64자마다 줄바꿈)
        formatted_key = begin_marker + "\n"
        for i in range(0, len(key_content), 64):
            formatted_key += key_content[i:i+64] + "\n"
        formatted_key += end_marker + "\n"
        
        creds_info["private_key"] = formatted_key
    
    return creds_info


@st.cache_resource
def get_worksheet():
    """
    gspread 클라이언트를 만들고,
    SHEET_ID 의 워크시트를 돌려준다.
    WORKSHEET_NAME 이 지정되어 있으면 그 탭,
    아니면 첫 번째 탭(sheet1)을 사용.
    """
    try:
        creds_info = get_credentials_info()
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = service_account.Credentials.from_service_account_info(
            creds_info, scopes=scopes
        )
        client = gspread.authorize(credentials)

        sh = client.open_by_key(SHEET_ID)

        if WORKSHEET_NAME:
            try:
                ws = sh.worksheet(WORKSHEET_NAME)
            except gspread.WorksheetNotFound:
                # 없으면 새로 만들고 헤더만 세팅
                ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=30)
                ws.append_row(DEFAULT_COLUMNS)
        else:
            ws = sh.sheet1  # 첫 번째 탭

        return ws
    except Exception as e:
        st.error(f"구글 시트 연결 실패: {e}")
        st.stop()


# ----------------------------
# 시트 → DataFrame
# ----------------------------
def load_sheet_as_dataframe():
    try:
        ws = get_worksheet()
        values = ws.get_all_values()

        if not values:
            # 완전 빈 시트인 경우
            df = pd.DataFrame(columns=DEFAULT_COLUMNS)
            return df, ws

        header = values[0]
        data_rows = values[1:]

        # 길이 맞추기
        max_len = len(header)
        normalized = []
        for row in data_rows:
            if len(row) < max_len:
                row = row + [""] * (max_len - len(row))
            else:
                row = row[:max_len]
            normalized.append(row)

        df = pd.DataFrame(normalized, columns=[str(h).strip() for h in header])

        # NO 컬럼이 없으면 자동 생성
        if "NO" not in df.columns:
            df.insert(0, "NO", range(1, len(df) + 1))
        else:
            # 비어 있으면 채워주기
            if df["NO"].isna().any() or (df["NO"] == "").any():
                df["NO"] = pd.to_numeric(df["NO"], errors="coerce")
                next_no = int(df["NO"].max()) + 1 if df["NO"].notna().any() else 1
                for i, v in df["NO"].items():
                    if pd.isna(v):
                        df.at[i, "NO"] = next_no
                        next_no += 1
            df["NO"] = df["NO"].astype(int)

        # 운송편 컬럼 없으면 생성
        if "운송편" not in df.columns:
            df["운송편"] = ""

        # 숫자 컬럼 후보 → 내부적으로는 숫자형으로 관리
        qty_col_candidates = ["요청수량", "수량"]
        price_cols = ["샘플단가", "샘플금액"]

        qty_col = None
        for c in qty_col_candidates:
            if c in df.columns:
                qty_col = c
                break

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
            if c in df.columns:
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
        date_cols = ["접수일", "납기일"]
        for col in date_cols:
            if col in df.columns:
                # 문자열 날짜를 date 객체로 변환 시도
                def parse_date(x):
                    x = str(x).strip()
                    if not x or x.lower() in ['nan', 'none', 'n/a', '']:
                        return None
                    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                        try:
                            return datetime.strptime(x, fmt).date()
                        except:
                            continue
                    return None
                
                df[col] = df[col].apply(parse_date)

        return df, ws
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame(columns=DEFAULT_COLUMNS), None


# ----------------------------
# DataFrame → 시트 저장
# ----------------------------
def save_dataframe_to_sheet(df: pd.DataFrame):
    """
    절대 데이터 자동삭제 안 함.
    화면에서 보이는 df 전체를 그대로 시트에 덮어쓴다.
    """
    try:
        ws = get_worksheet()

        # 저장 전에 NaN → "" 처리
        df_to_save = df.copy()
        df_to_save = df_to_save.fillna("")

        # 날짜 컬럼을 문자열로 변환
        date_cols = ["접수일", "납기일"]
        for col in date_cols:
            if col in df_to_save.columns:
                df_to_save[col] = df_to_save[col].apply(
                    lambda x: x.strftime("%Y-%m-%d") if hasattr(x, 'strftime') and x is not None else str(x) if x else ""
                )

        # 헤더 + 데이터
        header = list(df_to_save.columns)
        data = df_to_save.astype(str).values.tolist()

        ws.clear()
        ws.append_row(header)
        if data:
            ws.append_rows(data)
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 실패: {e}")
        return False


# ----------------------------
# 메인 화면
# ----------------------------
def main():
    st.title("🏭 신성EP 샘플 관리 대장")

    # 데이터 로드
    if "df" not in st.session_state:
        df, ws = load_sheet_as_dataframe()
        st.session_state.df = df
        st.session_state.ws_title = ws.title if ws else ""
    else:
        df = st.session_state.df

    st.caption(f"현재 연결된 시트 ID: {SHEET_ID}, 탭: {st.session_state.get('ws_title', '')}")

    # 숫자 컬럼 이름 찾기
    qty_col = "요청수량" if "요청수량" in df.columns else ("수량" if "수량" in df.columns else None)
    price_cols = [c for c in ["샘플단가", "샘플금액"] if c in df.columns]

    # 상단 요약 카드
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_rows = len(df)
        st.metric("총 샘플 건수", f"{total_rows:,} 건")

    with col2:
        if qty_col:
            total_qty = int(df[qty_col].fillna(0).sum())
            st.metric("총 요청 수량", f"{total_qty:,.0f} EA")
        else:
            st.metric("총 요청 수량", "-")

    with col3:
        # 완료 건수: 진행상태가 "완료" 인 경우 (있으면)
        completed = 0
        if "진행상태" in df.columns:
            completed = (df["진행상태"].astype(str) == "완료").sum()
        st.metric("완료 건수", f"{completed:,} 건")

    with col4:
        # 납기 지연: 납기일 < 오늘 이고, 완료가 아닌 건
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

    st.subheader("📋 샘플 관리 대장 편집")

    # 편집용 df
    edit_df = df.copy()

    # Streamlit 데이터 에디터 설정
    column_config = {}

    # NO는 읽기 전용처럼 표시
    if "NO" in edit_df.columns:
        column_config["NO"] = st.column_config.NumberColumn("NO", disabled=True, format="%d")

    # 날짜 컬럼 설정
    date_cols = ["접수일", "납기일"]
    for col in date_cols:
        if col in edit_df.columns:
            column_config[col] = st.column_config.DateColumn(col)

    # 운송편: 항공 / 선박 / 핸드캐리 선택
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

    edited_df = st.data_editor(
        edit_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config=column_config,
        key="main_editor",
    )

    st.markdown("")

    col_btn1, col_btn2 = st.columns(2)

    with col_btn1:
        if st.button("💾 변경 내용 저장", type="primary"):
            # 운송편 값 정리 (옵션 외 값은 일단 그대로 두되, None → "")
            if "운송편" in edited_df.columns:
                edited_df["운송편"] = edited_df["운송편"].fillna("")
                valid_opts = {"", "항공", "선박", "핸드캐리"}
                edited_df["운송편"] = edited_df["운송편"].apply(
                    lambda x: x if x in valid_opts else str(x)
                )

            # 숫자 컬럼 다시 안전하게 숫자로 변환
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

            # 세션 및 시트에 저장
            st.session_state.df = edited_df
            ok = save_dataframe_to_sheet(edited_df)
            if ok:
                st.success("구글 시트에 저장되었습니다.")
                st.rerun()
            else:
                st.error("저장 중 문제가 발생했습니다.")

    with col_btn2:
        if st.button("🔄 구글 시트에서 다시 불러오기"):
            new_df, ws = load_sheet_as_dataframe()
            st.session_state.df = new_df
            st.session_state.ws_title = ws.title if ws else ""
            st.success("구글 시트에서 최신 데이터를 다시 불러왔습니다.")
            st.rerun()


if __name__ == "__main__":
    main()

