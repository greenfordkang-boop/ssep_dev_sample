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
        error_msg = str(e)
        if "429" in error_msg or "Quota exceeded" in error_msg or "quota" in error_msg.lower():
            st.error("""
            ⚠️ **Google Sheets API 할당량 초과**
            
            API 호출이 너무 많아 일시적으로 차단되었습니다.
            
            **해결 방법:**
            1. 잠시 기다린 후 (1-2분) 다시 시도하세요
            2. "🔄 구글 시트에서 다시 불러오기" 버튼을 자주 누르지 마세요
            3. 데이터를 수정한 후에는 "💾 변경 내용 저장" 버튼만 사용하세요
            
            **참고:** Google Sheets API는 분당 읽기 요청 수에 제한이 있습니다.
            """)
        else:
            st.error(f"❌ gspread 클라이언트 초기화 실패: {e}")
        st.stop()


# ================================
# 시트 선택 / 로드 / 저장
# ================================
@st.cache_resource(ttl=300)  # 5분간 캐시
def pick_worksheet():
    """시트 탭 선택 (자동 탐색 또는 지정된 탭) - 캐시 적용"""
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
        error_msg = str(e)
        if "429" in error_msg or "Quota exceeded" in error_msg or "quota" in error_msg.lower():
            st.error("""
            ⚠️ **Google Sheets API 할당량 초과**
            
            API 호출이 너무 많아 일시적으로 차단되었습니다.
            
            **해결 방법:**
            1. 잠시 기다린 후 (1-2분) 다시 시도하세요
            2. "🔄 구글 시트에서 다시 불러오기" 버튼을 자주 누르지 마세요
            3. 데이터를 수정한 후에는 "💾 변경 내용 저장" 버튼만 사용하세요
            
            **참고:** Google Sheets API는 분당 읽기 요청 수에 제한이 있습니다.
            """)
        else:
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


def sanitize_column_names_for_editor(df: pd.DataFrame) -> pd.DataFrame:
    """
    st.data_editor 에 넣기 전에 컬럼 이름을 정리한다.
    - 빈 컬럼명: '열1', '열2' ... 로 채움
    - 중복 컬럼명: 두 번째부터는 '_2', '_3' suffix 를 붙여 유일하게 만듦
    - 원본 df 는 수정하지 않고, 복사본을 리턴
    - Streamlit이 허용하지 않는 특수 문자 제거
    """
    original_cols = list(df.columns)
    new_cols = []
    seen = {}

    for idx, col in enumerate(original_cols):
        name = str(col).strip()

        # 1) 비어있으면 '열{번호}' 로 채움
        if not name or name == "":
            name = f"열{idx + 1}"

        # 2) Streamlit이 허용하지 않는 문자 제거 (줄바꿈, 탭 등)
        name = name.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        # 연속된 공백을 하나로
        name = " ".join(name.split())

        # 3) 중복 방지
        base = name
        count = seen.get(base, 0)
        if count > 0:
            # 두 번째부터는 "_2", "_3" suffix
            name = f"{base}_{count + 1}"
        seen[base] = count + 1

        # 4) 최종 검증: 여전히 비어있으면 강제로 이름 부여
        if not name or name == "":
            name = f"열{idx + 1}"

        new_cols.append(name)

    df_fixed = df.copy()
    df_fixed.columns = new_cols
    
    # 최종 검증: 모든 컬럼명이 유일하고 비어있지 않은지 확인
    if len(new_cols) != len(set(new_cols)):
        # 중복이 있으면 다시 처리
        seen_final = {}
        final_cols = []
        for col in new_cols:
            base = str(col).strip()
            if not base or base == "":
                base = f"열{len(final_cols) + 1}"
            count = seen_final.get(base, 0)
            if count > 0:
                col = f"{base}_{count + 1}"
            else:
                col = base
            seen_final[base] = count + 1
            final_cols.append(col)
        df_fixed.columns = final_cols
        new_cols = final_cols
    
    # 최종 검증: 빈 컬럼명이 있는지 확인 및 수정
    final_cols_list = list(df_fixed.columns)
    for i, col in enumerate(final_cols_list):
        col_str = str(col).strip()
        if not col_str or col_str == "" or col_str.lower() in ['nan', 'none', 'n/a']:
            final_cols_list[i] = f"열{i + 1}"
    df_fixed.columns = final_cols_list
    
    # 최종 검증: 중복이 여전히 있는지 확인
    if len(df_fixed.columns) != len(set(df_fixed.columns)):
        # 중복이 있으면 인덱스 기반으로 강제 고유화
        final_unique_cols = []
        seen_unique = {}
        for i, col in enumerate(df_fixed.columns):
            col_str = str(col).strip()
            if not col_str or col_str == "":
                col_str = f"열{i + 1}"
            if col_str in seen_unique:
                col_str = f"{col_str}_{i}"
            seen_unique[col_str] = True
            final_unique_cols.append(col_str)
        df_fixed.columns = final_unique_cols
    
    return df_fixed


@st.cache_data(ttl=60)  # 1분간 캐시 (데이터는 자주 변경될 수 있으므로 짧게)
def load_sheet_as_dataframe_cached():
    """구글 시트 → DataFrame (캐시 적용)"""
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

        # 중복 컬럼 제거 (공백 정규화 후 중복 제거)
        # 예: "출하 장소"와 "출하장소" 중 하나만 유지
        cols_to_remove = []
        seen_cols = {}
        
        for col in df.columns:
            col_normalized = str(col).strip().replace(" ", "")  # 공백 제거하여 비교
            if col_normalized in seen_cols:
                # 중복 발견: 나중에 나온 컬럼을 제거 대상으로 표시
                cols_to_remove.append(col)
            else:
                seen_cols[col_normalized] = col
        
        # 중복 컬럼 제거
        if cols_to_remove:
            df = df.drop(columns=cols_to_remove)
        
        # 특정 중복 패턴 명시적 처리
        # "출하 장소"와 "출하장소" 중 "출하 장소" (공백 포함) 제거
        if "출하 장소" in df.columns and "출하장소" in df.columns:
            df = df.drop(columns=["출하 장소"])

        # "출하장소" 다음 컬럼부터 특정 컬럼들 제거
        # NO, 접수일, 담당자, 차종부터 자재요청일까지 삭제
        if "출하장소" in df.columns:
            출하장소_idx = list(df.columns).index("출하장소")
            # 출하장소 다음 컬럼부터 확인
            cols_after_출하장소 = list(df.columns)[출하장소_idx + 1:]
            
            # 삭제할 컬럼 목록
            cols_to_delete = []
            for col in cols_after_출하장소:
                col_str = str(col).strip()
                # NO, 접수일, 담당자(또는 담당), 차종부터 자재요청일(또는 자재 요청일)까지
                if col_str in ["NO", "접수일"]:
                    cols_to_delete.append(col)
                elif "담당" in col_str:  # 담당자, 담당 등
                    cols_to_delete.append(col)
                elif col_str == "차종":
                    cols_to_delete.append(col)
                elif "자재" in col_str and "요청" in col_str:  # 자재요청일, 자재 요청일 등
                    cols_to_delete.append(col)
                    break  # 자재요청일까지 포함하므로 여기서 중단
                elif col_str in ["품번", "품명", "부서"]:  # 차종과 자재요청일 사이의 컬럼들
                    cols_to_delete.append(col)
            
            # 컬럼 삭제
            if cols_to_delete:
                df = df.drop(columns=cols_to_delete)

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
        error_msg = str(e)
        if "429" in error_msg or "Quota exceeded" in error_msg or "quota" in error_msg.lower():
            st.error("""
            ⚠️ **Google Sheets API 할당량 초과**
            
            데이터를 불러오는 중 API 호출 제한에 걸렸습니다.
            
            **해결 방법:**
            1. 잠시 기다린 후 (1-2분) "🔄 구글 시트에서 다시 불러오기" 버튼을 클릭하세요
            2. 너무 자주 새로고침하지 마세요
            3. 세션 상태에 저장된 데이터를 계속 사용할 수 있습니다
            """)
        else:
            st.error(f"❌ 데이터 로드 실패: {e}")
        return pd.DataFrame(columns=DEFAULT_COLUMNS), None


def load_sheet_as_dataframe():
    """구글 시트 → DataFrame (캐시 래퍼)"""
    return load_sheet_as_dataframe_cached()


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

    # 데이터 로드 (세션 상태 우선 사용, API 호출 최소화)
    if "df" not in st.session_state or "ws_title" not in st.session_state:
        try:
            df, ws = load_sheet_as_dataframe()
            st.session_state.df = df
            st.session_state.ws_title = ws.title if ws else ""
            st.session_state.ws = ws
        except Exception as e:
            # API 오류 시 기존 세션 데이터 사용
            if "df" in st.session_state:
                df = st.session_state.df
                ws = st.session_state.get("ws")
                st.warning("⚠️ 최신 데이터를 불러올 수 없습니다. 기존 데이터를 표시합니다.")
            else:
                error_msg = str(e)
                if "429" in error_msg or "Quota exceeded" in error_msg:
                    st.error("""
                    ⚠️ **API 할당량 초과**
                    
                    처음 로드 시 API 제한에 걸렸습니다. 1-2분 후 페이지를 새로고침하세요.
                    """)
                else:
                    st.error(f"❌ 데이터를 불러올 수 없습니다: {e}")
                st.stop()
    else:
        df = st.session_state.df
        ws = st.session_state.get("ws")

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
    
    # 컬럼 이름 정리 (빈 컬럼명, 중복 컬럼명 처리)
    # 원본 컬럼명 매핑 저장 (저장 시 복원용)
    original_cols = list(edit_df.columns)
    edit_df = sanitize_column_names_for_editor(edit_df)
    sanitized_cols = list(edit_df.columns)
    col_mapping = dict(zip(sanitized_cols, original_cols))  # 정리된 컬럼명 → 원본 컬럼명
    st.session_state.col_mapping = col_mapping

    # 컬럼 설정
    column_config = {}

    # 컬럼 설정 (정리된 컬럼명 기준으로 매핑)
    # 원본 컬럼명과 정리된 컬럼명 매핑
    reverse_mapping = {v: k for k, v in col_mapping.items()}  # 원본 → 정리된
    
    # NO는 읽기 전용
    if "NO" in reverse_mapping:
        no_col = reverse_mapping["NO"]
        column_config[no_col] = st.column_config.NumberColumn("NO", format="%d", disabled=True)

    # 날짜 컬럼
    date_cols_original = ["접수일", "납기일", "도면접수일", "자재 요청일", "샘플 완료일", "출하일"]
    for original_col in date_cols_original:
        if original_col in reverse_mapping:
            date_col = reverse_mapping[original_col]
            column_config[date_col] = st.column_config.DateColumn(original_col)

    # 운송편: SelectboxColumn (항공/선박/핸드캐리만 선택 가능)
    if "운송편" in reverse_mapping:
        transport_col = reverse_mapping["운송편"]
        column_config[transport_col] = st.column_config.SelectboxColumn(
            "운송편",
            options=["", "항공", "선박", "핸드캐리"],
            required=False,
        )

    # 숫자 컬럼 포맷 (천단위 콤마)
    if qty_col and qty_col in reverse_mapping:
        qty_col_sanitized = reverse_mapping[qty_col]
        column_config[qty_col_sanitized] = st.column_config.NumberColumn(qty_col, format="%,d")
    for price_col in price_cols:
        if price_col in reverse_mapping:
            price_col_sanitized = reverse_mapping[price_col]
            column_config[price_col_sanitized] = st.column_config.NumberColumn(price_col, format="%,.0f")

    # 데이터 에디터 전 최종 검증
    # 컬럼명이 비어있거나 중복되지 않았는지 확인
    if not edit_df.empty:
        cols = list(edit_df.columns)
        # 빈 컬럼명 체크
        empty_cols = [i for i, c in enumerate(cols) if not str(c).strip() or str(c).strip() == ""]
        if empty_cols:
            st.error(f"⚠️ 빈 컬럼명 감지 (인덱스: {empty_cols}). 자동 수정합니다.")
            for i in empty_cols:
                edit_df.columns.values[i] = f"열{i + 1}"
        
        # 중복 컬럼명 체크
        if len(cols) != len(set(cols)):
            duplicates = [c for c in cols if cols.count(c) > 1]
            st.error(f"⚠️ 컬럼명 중복 감지: {set(duplicates)}. 자동 수정합니다.")
            # 중복 제거
            seen_dup = {}
            new_cols_dup = []
            for i, col in enumerate(edit_df.columns):
                col_str = str(col).strip()
                if not col_str or col_str == "":
                    col_str = f"열{i + 1}"
                if col_str in seen_dup:
                    col_str = f"{col_str}_{i}"
                seen_dup[col_str] = True
                new_cols_dup.append(col_str)
            edit_df.columns = new_cols_dup
    
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
            # 정리된 컬럼명을 원본 컬럼명으로 복원
            col_mapping = st.session_state.get("col_mapping", {})
            if col_mapping:
                edited_df.columns = [col_mapping.get(col, col) for col in edited_df.columns]
            
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
            try:
                # 캐시 무효화 후 다시 로드
                load_sheet_as_dataframe_cached.clear()
                pick_worksheet.clear()
                new_df, new_ws = load_sheet_as_dataframe()
                st.session_state.df = new_df
                st.session_state.ws_title = new_ws.title if new_ws else ""
                st.session_state.ws = new_ws
                st.success("🔄 최신 데이터를 다시 불러왔습니다.")
                st.rerun()
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "Quota exceeded" in error_msg or "quota" in error_msg.lower():
                    st.error("""
                    ⚠️ **API 할당량 초과**
                    
                    너무 자주 새로고침하셨습니다. 1-2분 후 다시 시도해주세요.
                    현재 세션에 저장된 데이터를 계속 사용할 수 있습니다.
                    """)
                else:
                    st.error(f"❌ 데이터 불러오기 실패: {e}")


if __name__ == "__main__":
    main()
