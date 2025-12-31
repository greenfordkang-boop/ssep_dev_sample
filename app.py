import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
from datetime import datetime
import shutil
import os

st.set_page_config(page_title="신성EP 샘플 관리 대장", layout="wide")

SHEET_ID = "1aHe7GQsPnZfMjZVPy4jt0elCEADKubWSSeonhZTKR9E"
WORKSHEET_NAME = "Form_Responses 1"  # Google Form 실제 응답 탭 이름

# 1. 구글 시트와 앱의 순서를 100% 일치시키기 위한 기준 리스트
# 시트에 적힌 실제 제목과 정확히 일치해야 합니다.
COLUMN_ORDER = [
    "타임스탬프", "신청일자", "업체명", "부서명", "성함", 
    "차종(모델)", "품명", "part no", "요청수량", "납기일", "납기일(예정)",
    "요청사항", "연락처", "이메일", "운송편", "비고", 
    "샘플단가", "샘플금액", "도면접수일", "자재준비", "샘플 완료일", 
    "출하일", "진행상태", "출하 장소"
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
    
    if not values or len(values) < 1:
        return pd.DataFrame(columns=["NO"] + COLUMN_ORDER), ws

    # 1. 시트의 실제 헤더와 데이터를 분리합니다. 
    raw_header = [str(h).strip() for h in values[0]]
    raw_data = values[1:]

    # 2. 시트 원본 순서대로 데이터프레임을 생성합니다. 
    df = pd.DataFrame(raw_data, columns=raw_header)

    # 3. [데이터 밀림 방지 로직] - COLUMN_ORDER에 정의된 모든 컬럼을 순서대로 보장
    # 시트에 없는 열은 빈 값("")으로 생성하여 밀림을 방지합니다.
    for col in COLUMN_ORDER:
        if col not in df.columns:
            df[col] = ""  # 시트에 없는 열은 빈 값으로 생성

    # 4. [중요] COLUMN_ORDER 순서로 엄격히 재배치 (데이터 밀림 완전 방지)
    df_reordered = pd.DataFrame()
    for col in COLUMN_ORDER:
        if col in df.columns:
            df_reordered[col] = df[col]
        else:
            df_reordered[col] = ""
    df = df_reordered.copy()

    # 5. [중요] 숫자 컬럼을 먼저 변환 (fillna 전에 처리하여 타입 유지)
    num_cols = ["요청수량", "샘플단가", "샘플금액"]
    for col in num_cols:
        if col in df.columns:
            # 문자열로 변환 후 숫자만 추출하여 정수로 변환
            df[col] = df[col].astype(str).str.replace(r'[^0-9\-]', '', regex=True)
            df[col] = df[col].replace('', '0').replace('-', '0')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    # 6. 숫자 컬럼이 아닌 나머지 컬럼의 NaN 값을 빈 문자열로 처리
    for col in df.columns:
        if col not in num_cols:
            df[col] = df[col].fillna("")

    # 7. 샘플금액 자동 계산: 요청수량 * 샘플단가
    if "요청수량" in df.columns and "샘플단가" in df.columns and "샘플금액" in df.columns:
        df["샘플금액"] = (df["요청수량"] * df["샘플단가"]).astype(int)

    # 8. 진행상태 자동 트리거 로직
    if "진행상태" not in df.columns:
        df["진행상태"] = ""
    
    # 진행상태 자동 설정 (우선순위: 출하일 > 샘플 완료일 > 자재준비 > 기본값)
    for idx in df.index:
        status = "접수"  # 기본값
        
        # 1순위: 출하일이 있으면 "출하완료"
        if "출하일" in df.columns:
            출하일값 = str(df.at[idx, "출하일"]).strip()
            if 출하일값 and 출하일값 != "" and 출하일값.lower() != "nan":
                status = "출하완료"
            else:
                # 2순위: 샘플 완료일이 있으면 "생산완료"
                if "샘플 완료일" in df.columns:
                    완료일값 = str(df.at[idx, "샘플 완료일"]).strip()
                    if 완료일값 and 완료일값 != "" and 완료일값.lower() != "nan":
                        status = "생산완료"
                    else:
                        # 3순위: 자재준비가 "완료"이면 "생산중"
                        if "자재준비" in df.columns:
                            자재준비값 = str(df.at[idx, "자재준비"]).strip()
                            if 자재준비값 == "완료":
                                status = "생산중"
        
        df.at[idx, "진행상태"] = status

    # 9. NO(번호) 컬럼은 앱 전용이므로 맨 앞에 추가합니다. 
    df.insert(0, "NO", range(1, len(df) + 1))
    df["NO"] = df["NO"].astype(int)

    return df, ws

def save_dataframe_to_sheet(df: pd.DataFrame, ws):
    """저장 시 NO를 제외하고 COLUMN_ORDER 순서로 시트에 기록합니다."""
    try:
        # NO 컬럼은 시트 저장용이 아니므로 제외합니다. 
        to_save = df[COLUMN_ORDER].copy().fillna("")
        
        ws.clear() # 기존 데이터를 지우고 새로 씁니다. 
        # 헤더를 포함하여 한 번에 업데이트합니다. 
        ws.update('A1', [to_save.columns.tolist()] + to_save.values.tolist())
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 실패: {e}")
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
            
            st.markdown("---")
            st.markdown("### 🔄 백업/복원")
            
            # 현재 상태를 백업 버전으로 저장
            if st.button("💾 현재 상태 백업 (Ver1로 저장)", help="현재 app.py를 app_ver1.py로 백업합니다"):
                try:
                    if os.path.exists("app.py"):
                        shutil.copy("app.py", "app_ver1.py")
                        st.success("✅ 백업 완료: app_ver1.py에 저장되었습니다.")
                    else:
                        st.error("❌ app.py 파일을 찾을 수 없습니다.")
                except Exception as e:
                    st.error(f"❌ 백업 실패: {e}")
            
            # Ver1로 복원
            if st.button("⏮️ Ver1로 복원", help="app_ver1.py를 app.py로 복원합니다"):
                try:
                    if os.path.exists("app_ver1.py"):
                        shutil.copy("app_ver1.py", "app.py")
                        st.success("✅ 복원 완료: app_ver1.py를 app.py로 복원했습니다.")
                        st.info("⚠️ 페이지를 새로고침하거나 앱을 재시작해야 변경사항이 적용됩니다.")
                    else:
                        st.error("❌ app_ver1.py 파일을 찾을 수 없습니다.")
                except Exception as e:
                    st.error(f"❌ 복원 실패: {e}")
            
            st.markdown("---")
            
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
    
    # 고객사 로그인 시 간략한 일정 표시
    if role == "고객사":
        st.subheader("📅 접수건수 일정 현황")
        
        # 표시할 컬럼 정의
        schedule_cols = []
        col_mapping = {
            "접수일자": "신청일자",
            "품명": "품명",
            "part no": "part no",
            "요청내역": "요청사항",
            "상태": "진행상태",
            "납기일(예정)": "납기일(예정)"  # 관리자가 입력한 예상 납기일
        }
        
        # 실제 컬럼명으로 매핑
        display_cols = []
        actual_cols = []
        for display_name, actual_col in col_mapping.items():
            if actual_col in df.columns:
                display_cols.append(display_name)
                actual_cols.append(actual_col)
        
        if actual_cols:
            # 간략한 일정 테이블 생성
            schedule_df = df[actual_cols].copy()
            schedule_df.columns = display_cols
            
            # 납기일(예정)이 있는 경우 날짜 형식 정리
            if "납기일(예정)" in schedule_df.columns:
                # 날짜 형식으로 변환 시도
                def format_date_safe(val):
                    if pd.isna(val) or val == "" or str(val).strip() == "":
                        return "-"
                    try:
                        # 날짜 객체인 경우
                        if isinstance(val, (datetime.date, datetime.datetime)):
                            return val.strftime("%Y-%m-%d")
                        # 문자열인 경우 파싱 시도
                        date_val = parse_date_safe(str(val))
                        if date_val:
                            return date_val.strftime("%Y-%m-%d")
                        return str(val).strip() if str(val).strip() else "-"
                    except:
                        return str(val).strip() if str(val).strip() else "-"
                
                schedule_df["납기일(예정)"] = schedule_df["납기일(예정)"].apply(format_date_safe)
            
            # 접수일자 형식 정리
            if "접수일자" in schedule_df.columns:
                schedule_df["접수일자"] = schedule_df["접수일자"].astype(str).str.strip()
                schedule_df["접수일자"] = schedule_df["접수일자"].replace("", "-").replace("nan", "-")
            
            # 빈 값 처리
            schedule_df = schedule_df.fillna("-")
            
            # 테이블로 표시 (인덱스 없이)
            st.dataframe(
                schedule_df,
                use_container_width=True,
                hide_index=True,
                height=min(400, 50 + len(schedule_df) * 35)  # 행 높이에 따라 동적 조정
            )
            
            st.caption(f"총 {len(schedule_df)}건의 접수건이 있습니다.")
        else:
            st.info("일정 정보를 표시할 데이터가 없습니다.")
        
        st.markdown("---")
    
    # 미출하건 필터 체크박스
    filter_pending = st.checkbox("🚚 미출하건만 보기", key="filter_pending", help="진행상태가 '출하완료'가 아닌 건만 표시합니다")
    
    # 필터링 적용
    if filter_pending:
        if "진행상태" in df.columns:
            df = df[df["진행상태"].astype(str) != "출하완료"].copy()
            st.info(f"📊 미출하건 필터 적용: {len(df)}건 표시 중")
    
    st.subheader("📋 샘플 목록 편집")

    # 2) 편집용 데이터 준비 (에디터에 보이는 게 기준)
    edit_df = df.copy()
    
    # COLUMN_ORDER 순서로 컬럼 재정렬 (NO는 맨 앞, 나머지는 COLUMN_ORDER 순서)
    # NO가 있으면 맨 앞에, 그 다음 COLUMN_ORDER 순서대로
    ordered_cols = ["NO"] if "NO" in edit_df.columns else []
    for col in COLUMN_ORDER:
        if col in edit_df.columns:
            ordered_cols.append(col)
    # COLUMN_ORDER에 없는 다른 컬럼들도 추가 (예: _삭제 등)
    for col in edit_df.columns:
        if col not in ordered_cols:
            ordered_cols.append(col)
    edit_df = edit_df[ordered_cols].copy()
    
    # [중요] 숫자 컬럼 타입 재확인 및 변환 (st.data_editor 전에 필수)
    num_cols = ["요청수량", "샘플단가", "샘플금액"]
    for col in num_cols:
        if col in edit_df.columns:
            # 타입이 숫자가 아니면 강제 변환
            try:
                if not pd.api.types.is_integer_dtype(edit_df[col]):
                    # 문자열로 변환 후 숫자만 추출
                    edit_df[col] = edit_df[col].astype(str).str.replace(r'[^0-9\-]', '', regex=True)
                    edit_df[col] = edit_df[col].replace('', '0').replace('-', '0')
                    edit_df[col] = pd.to_numeric(edit_df[col], errors='coerce').fillna(0).astype(int)
            except Exception as e:
                # 변환 실패 시 0으로 설정
                edit_df[col] = 0
                edit_df[col] = edit_df[col].astype(int)
    
    # ✅ 행 삭제용 체크박스 컬럼 추가 (먼저 추가하여 타입 확정)
    if "_삭제" not in edit_df.columns:
        edit_df["_삭제"] = False
    edit_df["_삭제"] = edit_df["_삭제"].astype(bool)
    
    # 2. st.data_editor 설정 시 타입 명시
    column_config = {}
    
    # NO 컬럼: 수정 불가
    if "NO" in edit_df.columns:
        column_config["NO"] = st.column_config.NumberColumn("NO", disabled=True, format="%d")
    
    # 타임스탬프: 수정 불가
    if "타임스탬프" in edit_df.columns:
        column_config["타임스탬프"] = st.column_config.TextColumn("타임스탬프", disabled=True)
    
    # 요청수량: 숫자 형식, 수정 가능하도록 설정
    if "요청수량" in edit_df.columns:
        # 타입이 정수형인지 확인하고, 아니면 강제 변환
        if not pd.api.types.is_integer_dtype(edit_df["요청수량"]):
            try:
                edit_df["요청수량"] = edit_df["요청수량"].astype(str).str.replace(r'[^0-9\-]', '', regex=True)
                edit_df["요청수량"] = edit_df["요청수량"].replace('', '0').replace('-', '0')
                edit_df["요청수량"] = pd.to_numeric(edit_df["요청수량"], errors='coerce').fillna(0).astype(int)
            except:
                edit_df["요청수량"] = 0
                edit_df["요청수량"] = edit_df["요청수량"].astype(int)
        # NumberColumn 설정 (disabled=False로 명시하여 수정 가능하게)
        # format="%,d"는 Streamlit에서 지원하지 않으므로 "%d" 사용
        column_config["요청수량"] = st.column_config.NumberColumn(
            "요청수량", 
            format="%d",  # 천단위 콤마 없이 정수 형식
            disabled=False  # 수정 가능하도록 명시
        )
    
    # 샘플단가: 천단위 콤마 형식
    if "샘플단가" in edit_df.columns:
        column_config["샘플단가"] = st.column_config.NumberColumn("샘플단가", format="#,###")
    
    # 샘플금액: 천단위 콤마 형식, 수정 불가 (자동 계산)
    if "샘플금액" in edit_df.columns:
        column_config["샘플금액"] = st.column_config.NumberColumn("샘플금액", format="#,###", disabled=True)

    # 운송편: Selectbox
    if "운송편" in edit_df.columns:
        column_config["운송편"] = st.column_config.SelectboxColumn(
            "운송편",
            options=["", "항공", "선박", "핸드캐리"],
            required=False,
        )
    
    # 자재준비: Selectbox
    if "자재준비" in edit_df.columns:
        column_config["자재준비"] = st.column_config.SelectboxColumn(
            "자재준비",
            options=["", "준비중", "완료"],
            required=False,
        )
    
    # 진행상태: Selectbox, 수정 불가 권장 (자동 계산되므로)
    if "진행상태" in edit_df.columns:
        column_config["진행상태"] = st.column_config.SelectboxColumn(
            "진행상태",
            options=["접수", "자재준비", "생산중", "생산완료", "출하완료"],
            disabled=True,  # 자동 계산되므로 수정 불가
        )
    
    # 납기일: 날짜 형식
    if "납기일" in edit_df.columns:
        column_config["납기일"] = st.column_config.DateColumn("납기일")
    
    # 납기일(예정): 날짜 형식, 관리자가 입력 가능
    if "납기일(예정)" in edit_df.columns:
        column_config["납기일(예정)"] = st.column_config.DateColumn("납기일(예정)")

    # 삭제 체크박스 컬럼
    if "_삭제" in edit_df.columns:
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

            # 4-2) 운송편 값 정리
            if "운송편" in to_save.columns:
                valid = {"", "항공", "선박", "핸드캐리"}
                to_save["운송편"] = to_save["운송편"].fillna("")
                to_save["운송편"] = to_save["운송편"].apply(
                    lambda x: x if x in valid else str(x)
                )

            # 4-3) 자재준비 값 정리
            if "자재준비" in to_save.columns:
                valid = {"", "준비중", "완료"}
                to_save["자재준비"] = to_save["자재준비"].fillna("")
                to_save["자재준비"] = to_save["자재준비"].apply(
                    lambda x: x if x in valid else str(x)
                )

            # 4-4) 수량/단가 숫자 처리
            if qty_col and qty_col in to_save.columns:
                to_save[qty_col] = (
                    to_save[qty_col]
                    .fillna(0)
                    .astype(str)
                    .str.replace(r"[^0-9\\-]", "", regex=True)
                    .replace("", "0")
                    .astype(int)
                )
            if "샘플단가" in to_save.columns:
                to_save["샘플단가"] = (
                    to_save["샘플단가"]
                    .fillna(0)
                    .astype(str)
                    .str.replace(r"[^0-9\\-]", "", regex=True)
                    .replace("", "0")
                    .astype(int)
                )

            # 4-5) 샘플금액 자동 재계산: 요청수량 * 샘플단가
            if "요청수량" in to_save.columns and "샘플단가" in to_save.columns and "샘플금액" in to_save.columns:
                to_save["샘플금액"] = (to_save["요청수량"] * to_save["샘플단가"]).astype(int)

            # 4-6) 진행상태 자동 재계산 (우선순위: 출하일 > 샘플 완료일 > 자재준비 > 기본값)
            if "진행상태" in to_save.columns:
                for idx in to_save.index:
                    status = "접수"  # 기본값
                    
                    # 1순위: 출하일이 있으면 "출하완료"
                    if "출하일" in to_save.columns:
                        출하일값 = str(to_save.at[idx, "출하일"]).strip()
                        if 출하일값 and 출하일값 != "" and 출하일값.lower() != "nan":
                            status = "출하완료"
                        else:
                            # 2순위: 샘플 완료일이 있으면 "생산완료"
                            if "샘플 완료일" in to_save.columns:
                                완료일값 = str(to_save.at[idx, "샘플 완료일"]).strip()
                                if 완료일값 and 완료일값 != "" and 완료일값.lower() != "nan":
                                    status = "생산완료"
                                else:
                                    # 3순위: 자재준비가 "완료"이면 "생산중"
                                    if "자재준비" in to_save.columns:
                                        자재준비값 = str(to_save.at[idx, "자재준비"]).strip()
                                        if 자재준비값 == "완료":
                                            status = "생산중"
                    
                    to_save.at[idx, "진행상태"] = status

            # 4-7) 시트 저장
            ok = save_dataframe_to_sheet(to_save, ws)
            if ok:
                st.success("구글 시트에 저장되었습니다.")
                st.rerun()

    with b2:
        if st.button("🔄 시트 다시 불러오기"):
            st.rerun()

if __name__ == "__main__":
    main()
