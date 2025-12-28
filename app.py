import streamlit as st
import pandas as pd
import datetime
import time
import json
import os
from io import BytesIO

# Google Sheets 연동 (온라인 데이터 저장 및 백업)
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False
    st.warning("Google Sheets 라이브러리가 설치되지 않았습니다. 로컬 파일을 사용합니다.")

# -----------------------------------------------------------------------------
# 1. 초기 설정 및 상수 (constants.ts, types.ts 대응)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="신성EP 통합 샘플 관리 대장", layout="wide", page_icon="🏭")

DATA_FILE = "ssep_data.json"
HISTORY_FILE = "ssep_history.json"

# Google Sheets 설정 (환경 변수 또는 Streamlit Secrets에서 가져오기)
# Streamlit Cloud에서는 st.secrets를 사용, 로컬에서는 환경 변수 사용
USE_GOOGLE_SHEETS = os.getenv("USE_GOOGLE_SHEETS", "false").lower() == "true"

# Google Sheets 설정
if USE_GOOGLE_SHEETS and GOOGLE_SHEETS_AVAILABLE:
    try:
        # Streamlit Secrets에서 설정 가져오기 (배포 시)
        if hasattr(st, 'secrets') and 'google_sheets' in st.secrets:
            creds_info = st.secrets['google_sheets']
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = Credentials.from_service_account_info(creds_info, scopes=scope)
            gc = gspread.authorize(creds)
            SPREADSHEET_ID = st.secrets['google_sheets']['spreadsheet_id']
        # 환경 변수에서 설정 가져오기 (로컬 개발 시)
        elif os.getenv("GOOGLE_SHEETS_CREDENTIALS"):
            import json as json_module
            creds_json = json_module.loads(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = Credentials.from_service_account_info(creds_json, scopes=scope)
            gc = gspread.authorize(creds)
            SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        else:
            USE_GOOGLE_SHEETS = False
            gc = None
            SPREADSHEET_ID = None
    except Exception as e:
        USE_GOOGLE_SHEETS = False
        gc = None
        SPREADSHEET_ID = None
        st.warning(f"Google Sheets 설정 오류: {e}. 로컬 파일을 사용합니다.")
else:
    gc = None
    SPREADSHEET_ID = None

# 초기 데이터 (템플릿 구조에 맞춤)
INITIAL_DATA = [
    {
        "NO": 1001,
        "접수일": "2024-12-01",
        "업체명": "INFAC 일렉스",
        "부서": "개발",
        "담당자": "신동규 책임",
        "차종": "YB CUV PE2",
        "품번": "PWA2024018",
        "품명": "WIRE ASSY_TOUCH+NFC(LHD)",
        "출하장소": "천안공장",
        "요청수량": 360,
        "납기일": "2024-12-20",
        "샘플단가": 0,
        "샘플금액": 0,
        "요청사항": "검사성적서 필수 포함",
        "도면접수일": "",
        "자재 요청일": "",
        "자재준비": "",
        "샘플 완료일": "",
        "출하일": "",
        "운송편": "",
        "비고": "자재 수급 중"
    },
    {
        "NO": 1002,
        "접수일": "2024-12-02",
        "업체명": "현대자동차",
        "부서": "선행개발",
        "담당자": "김철수 책임",
        "차종": "NE PE",
        "품번": "HWA-2024-001",
        "품명": "LV CABLE ASSY",
        "출하장소": "남양연구소",
        "요청수량": 50,
        "납기일": "2024-12-15",
        "샘플단가": 0,
        "샘플금액": 0,
        "요청사항": "라벨링 위치 준수",
        "도면접수일": "",
        "자재 요청일": "",
        "자재준비": "",
        "샘플 완료일": "",
        "출하일": "",
        "운송편": "",
        "비고": "커넥터 수입 지연 (ETA 12/10)"
    }
]

# -----------------------------------------------------------------------------
# 2. 데이터 로드 및 저장 함수 (LocalStorage 대체)
# -----------------------------------------------------------------------------
def calculate_progress_status(row):
    """진행상태를 계산하는 함수"""
    # 출하일이 있으면 출하완료
    if pd.notnull(row.get('출하일')) and row.get('출하일') is not None and row.get('출하일') != "":
        return "출하완료"
    # 샘플 완료일이 있으면 생산중
    elif pd.notnull(row.get('샘플 완료일')) and row.get('샘플 완료일') is not None and row.get('샘플 완료일') != "":
        return "생산중"
    # 자재준비가 있으면 자재준비중
    elif pd.notnull(row.get('자재준비')) and row.get('자재준비') is not None and row.get('자재준비') != "":
        return "자재준비중"
    # 접수일이 있으면 접수
    elif pd.notnull(row.get('접수일')) and row.get('접수일') is not None and row.get('접수일') != "":
        return "접수"
    else:
        return ""

def update_progress_status(df):
    """데이터프레임의 모든 행에 대해 진행상태를 계산하여 업데이트"""
    if df.empty:
        return df
    
    df['진행상태'] = df.apply(calculate_progress_status, axis=1)
    return df

def load_data_from_google_sheets():
    """Google Sheets에서 데이터 로드"""
    try:
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet("데이터")
        data = worksheet.get_all_records()
        if not data:
            return None
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Google Sheets 로드 오류: {e}")
        return None

def create_backup_manual():
    """수동 백업 생성"""
    if USE_GOOGLE_SHEETS and GOOGLE_SHEETS_AVAILABLE:
        return save_data_to_google_sheets(st.session_state.df, st.session_state.deleted_history, create_backup=True)
    else:
        # 로컬 파일 백업
        save_data_to_local()
        return True

def get_backup_list():
    """백업 목록 가져오기"""
    if USE_GOOGLE_SHEETS and GOOGLE_SHEETS_AVAILABLE:
        try:
            spreadsheet = gc.open_by_key(SPREADSHEET_ID)
            all_sheets = spreadsheet.worksheets()
            backup_sheets = [s for s in all_sheets if s.title.startswith("백업_")]
            backup_sheets.sort(key=lambda x: x.title, reverse=True)
            return backup_sheets
        except Exception as e:
            st.error(f"백업 목록 조회 오류: {e}")
            return []
    else:
        # 로컬 파일 백업 정보
        backups = []
        if os.path.exists(DATA_FILE):
            file_time = datetime.datetime.fromtimestamp(os.path.getmtime(DATA_FILE))
            backups.append({
                "name": "로컬 파일 백업",
                "date": file_time.strftime('%Y-%m-%d %H:%M:%S'),
                "type": "local"
            })
        return backups

def download_backup_from_sheets(backup_sheet_name):
    """Google Sheets 백업 다운로드"""
    try:
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        backup_worksheet = spreadsheet.worksheet(backup_sheet_name)
        data = backup_worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Excel로 변환
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        return output.getvalue()
    except Exception as e:
        st.error(f"백업 다운로드 오류: {e}")
        return None

def save_data_to_google_sheets(df, history, create_backup=False):
    """Google Sheets에 데이터 저장"""
    try:
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        
        # 데이터 시트 업데이트
        try:
            worksheet = spreadsheet.worksheet("데이터")
        except:
            worksheet = spreadsheet.add_worksheet(title="데이터", rows=1000, cols=30)
        
        # DataFrame을 리스트로 변환
        df_copy = df.copy()
        date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
        for col in date_columns:
            if col in df_copy.columns:
                df_copy[col] = df_copy[col].apply(lambda x: str(x) if pd.notnull(x) and x is not None else "")
        
        # 헤더와 데이터 준비
        headers = df_copy.columns.tolist()
        values = [headers] + df_copy.values.tolist()
        
        # 시트 클리어 후 새 데이터 쓰기
        worksheet.clear()
        worksheet.update(values, value_input_option='USER_ENTERED')
        
        # 히스토리 시트 업데이트
        try:
            history_worksheet = spreadsheet.worksheet("삭제내역")
        except:
            history_worksheet = spreadsheet.add_worksheet(title="삭제내역", rows=1000, cols=30)
        
        if history:
            # history를 안전하게 변환
            history_list = []
            for item in history:
                if isinstance(item, dict):
                    # 딕셔너리의 모든 값을 문자열로 변환
                    clean_item = {}
                    for key, value in item.items():
                        if value is None:
                            clean_item[key] = ""
                        elif isinstance(value, (datetime.date, datetime.datetime)):
                            clean_item[key] = str(value)
                        elif not isinstance(value, (str, int, float, bool)):
                            clean_item[key] = str(value)
                        else:
                            clean_item[key] = value
                    history_list.append(clean_item)
                elif item is not None:
                    # 딕셔너리가 아닌 경우 문자열로 변환
                    history_list.append({"data": str(item)})
            
            if history_list:
                history_headers = list(history_list[0].keys())
                history_values = [history_headers] + [[str(v) if v is not None else "" for v in row.values()] for row in history_list]
                history_worksheet.clear()
                history_worksheet.update(history_values, value_input_option='USER_ENTERED')
        
        # 백업 시트 생성 (타임스탬프 포함) - 최근 10개만 유지 (create_backup=True일 때만)
        if create_backup:
            try:
                backup_sheet_name = f"백업_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                backup_worksheet = spreadsheet.add_worksheet(title=backup_sheet_name, rows=1000, cols=30)
                backup_worksheet.update(values, value_input_option='USER_ENTERED')
                
                # 오래된 백업 시트 삭제 (최근 10개만 유지)
                all_sheets = spreadsheet.worksheets()
                backup_sheets = [s for s in all_sheets if s.title.startswith("백업_")]
                backup_sheets.sort(key=lambda x: x.title, reverse=True)
                if len(backup_sheets) > 10:
                    for old_sheet in backup_sheets[10:]:
                        spreadsheet.del_worksheet(old_sheet)
            except:
                pass  # 백업 실패해도 계속 진행
        
        return True
    except Exception as e:
        st.error(f"Google Sheets 저장 오류: {e}")
        return False

def convert_dataframe_types(df):
    """데이터프레임의 타입 변환 (공통 함수)"""
    if df.empty:
        return df
    
    # 날짜 컬럼을 datetime 타입으로 변환
    date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
            # 빈 날짜는 None으로 처리
            df[col] = df[col].where(pd.notnull(df[col]), None)
    
    # 숫자 컬럼을 숫자 타입으로 변환
    numeric_columns = ['요청수량', '샘플단가', '샘플금액', 'NO']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].where(pd.notnull(df[col]), 0)
    
    # 문자열 컬럼을 문자열 타입으로 변환 (float로 잘못 인식되는 것을 방지)
    text_columns = ['업체명', '부서', '담당자', '차종', '품번', '품명', '출하장소', '요청사항', '자재준비', '운송편', '비고', '진행상태']
    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).replace('nan', '').replace('None', '')
    
    return df

def load_data():
    if 'df' not in st.session_state:
        # Google Sheets 사용 시
        if USE_GOOGLE_SHEETS and GOOGLE_SHEETS_AVAILABLE:
            df = load_data_from_google_sheets()
            if df is not None and not df.empty:
                st.session_state.df = convert_dataframe_types(df)
                # 진행상태 계산 및 업데이트
                st.session_state.df = update_progress_status(st.session_state.df)
            else:
                st.session_state.df = pd.DataFrame(INITIAL_DATA)
                st.session_state.df = convert_dataframe_types(st.session_state.df)
                st.session_state.df = update_progress_status(st.session_state.df)
                # 초기 데이터를 Google Sheets에 저장
                save_data_to_google_sheets(st.session_state.df, [])
        # 로컬 파일 사용 시
        elif os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    st.session_state.df = pd.DataFrame(data)
                    # 날짜 컬럼을 datetime 타입으로 변환
                    date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
                    for col in date_columns:
                        if col in st.session_state.df.columns:
                            st.session_state.df[col] = pd.to_datetime(st.session_state.df[col], errors='coerce').dt.date
                            # 빈 날짜는 None으로 처리
                            st.session_state.df[col] = st.session_state.df[col].where(pd.notnull(st.session_state.df[col]), None)
                # 숫자 컬럼을 숫자 타입으로 변환
                numeric_columns = ['요청수량', '샘플단가', '샘플금액', 'NO']
                for col in numeric_columns:
                    if col in st.session_state.df.columns:
                        st.session_state.df[col] = pd.to_numeric(st.session_state.df[col], errors='coerce')
                        st.session_state.df[col] = st.session_state.df[col].where(pd.notnull(st.session_state.df[col]), 0)
                # 문자열 컬럼을 문자열 타입으로 변환 (float로 잘못 인식되는 것을 방지)
                text_columns = ['업체명', '부서', '담당자', '차종', '품번', '품명', '출하장소', '요청사항', '자재준비', '운송편', '비고', '진행상태']
                for col in text_columns:
                    if col in st.session_state.df.columns:
                        st.session_state.df[col] = st.session_state.df[col].astype(str).replace('nan', '').replace('None', '')
                # 진행상태 계산 및 업데이트
                st.session_state.df = update_progress_status(st.session_state.df)
            except:
                st.session_state.df = pd.DataFrame(INITIAL_DATA)
                st.session_state.df = convert_dataframe_types(st.session_state.df)
                st.session_state.df = update_progress_status(st.session_state.df)
        else:
            st.session_state.df = pd.DataFrame(INITIAL_DATA)
            st.session_state.df = convert_dataframe_types(st.session_state.df)
            st.session_state.df = update_progress_status(st.session_state.df)

    if 'deleted_history' not in st.session_state:
        # Google Sheets 사용 시
        if USE_GOOGLE_SHEETS and GOOGLE_SHEETS_AVAILABLE:
            try:
                spreadsheet = gc.open_by_key(SPREADSHEET_ID)
                history_worksheet = spreadsheet.worksheet("삭제내역")
                history_data = history_worksheet.get_all_records()
                st.session_state.deleted_history = history_data if history_data else []
            except:
                st.session_state.deleted_history = []
        # 로컬 파일 사용 시
        elif os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    st.session_state.deleted_history = json.load(f)
            except:
                st.session_state.deleted_history = []
        else:
            st.session_state.deleted_history = []

def save_data():
    # Google Sheets 사용 시
    if USE_GOOGLE_SHEETS and GOOGLE_SHEETS_AVAILABLE:
        success = save_data_to_google_sheets(st.session_state.df, st.session_state.deleted_history, create_backup=False)
        if not success:
            # Google Sheets 저장 실패 시 로컬 파일로 백업
            save_data_to_local()
    else:
        # 로컬 파일 저장
        save_data_to_local()

def save_data_to_local():
    """로컬 파일에 데이터 저장 (백업용)"""
    # DataFrame을 dict list로 변환하여 JSON 저장
    # 날짜 타입을 문자열로 변환
    df_copy = st.session_state.df.copy()
    date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
    for col in date_columns:
        if col in df_copy.columns:
            # date 타입을 문자열로 변환 (None은 빈 문자열로)
            df_copy[col] = df_copy[col].apply(lambda x: str(x) if pd.notnull(x) and x is not None else "")
    
    data = df_copy.to_dict('records')
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # deleted_history를 JSON 직렬화 가능한 형태로 변환
    history_data = []
    if st.session_state.deleted_history:
        for item in st.session_state.deleted_history:
            if isinstance(item, dict):
                # 딕셔너리의 모든 값을 문자열로 변환
                clean_item = {}
                for key, value in item.items():
                    if value is None:
                        clean_item[key] = ""
                    elif isinstance(value, (datetime.date, datetime.datetime)):
                        clean_item[key] = str(value)
                    elif not isinstance(value, (str, int, float, bool, list, dict)):
                        clean_item[key] = str(value)
                    else:
                        clean_item[key] = value
                history_data.append(clean_item)
            elif item is not None:
                # 딕셔너리가 아닌 경우 문자열로 변환
                history_data.append({"data": str(item)})
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)

# -----------------------------------------------------------------------------
# 3. 로그인 화면 (LoginScreen.tsx 대응)
# -----------------------------------------------------------------------------
def login_screen():
    st.markdown("""
    <style>
    .login-container { margin-top: 100px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 신성EP 샘플 관리 시스템")
        st.write("Authorized Access Only")
        
        with st.form("login_form"):
            username = st.text_input("아이디")
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인")
            
            if submitted:
                # 간단한 인증 로직 (실제 사용시 DB 연동 권장)
                if username == "admin" and password == "1234":
                    st.session_state.user = {"name": "관리자", "role": "ADMIN", "companyName": "신성오토텍"}
                    st.success("로그인 성공!")
                    st.rerun()
                elif username == "user" and password == "1234":
                    st.session_state.user = {"name": "홍길동", "role": "CUSTOMER", "companyName": "현대자동차"}
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 잘못되었습니다.")

# -----------------------------------------------------------------------------
# 4. 메인 애플리케이션 (App.tsx 대응)
# -----------------------------------------------------------------------------
def main_app():
    user = st.session_state.user
    
    # --- 사이드바 및 네비게이션 ---
    with st.sidebar:
        st.title(f"👤 {user['name']}님")
        st.caption(f"{user['role']} | {user['companyName']}")
        
        menu = st.radio("메뉴 선택", ["📊 샘플관리 현황판", "📝 신규 샘플 의뢰", "🗑️ 휴지통 (삭제 내역)", "💾 백업 관리"])
        
        st.divider()
        if st.button("로그아웃"):
            del st.session_state.user
            st.rerun()
            
        st.divider()
        st.info("💡 팁: 테이블에서 데이터를 직접 수정할 수 있습니다. (엔터 키 입력 시 자동 저장)")

    # --- 1. 샘플관리 현황판 (Dashboard & Table) ---
    if menu == "📊 샘플관리 현황판":
        st.title("🏭 신성EP 샘플 관리 현황판")
        st.markdown(f"**v7.2 Python Edition** | 현재 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # 최신 데이터 가져오기 (항상 최신 상태 유지)
        # 진행상태를 먼저 업데이트하여 최신 상태 보장
        st.session_state.df = update_progress_status(st.session_state.df)
        df = st.session_state.df.copy()
        
        # [검색 및 필터] - 대시보드 계산 전에 필터 적용
        col_search, col_filter1, col_filter2 = st.columns([2, 1, 1])
        with col_search:
            search_term = st.text_input("🔍 통합 검색 (업체명, 품번, 차종...)", "")
        with col_filter1:
            # CUSTOMER는 본인 회사만 볼 수 있으므로 업체 필터 비활성화
            if user['role'] == 'ADMIN':
                company_filter = st.selectbox("업체 필터", ["전체"] + list(df['업체명'].unique()) if not df.empty and '업체명' in df.columns else [])
            else:
                # CUSTOMER는 본인 회사만 표시
                company_filter = "전체"
                st.info(f"📋 {user['companyName']} 데이터만 표시됩니다")
        with col_filter2:
            completion_filter = st.selectbox("완료 상태", ["전체", "미완료", "완료"])
        
        # [컬럼별 필터] - 제목열 필터 기능 (필터링 로직 전에 UI 배치)
        with st.expander("📋 컬럼별 필터", expanded=False):
            col_filter_col1, col_filter_col2, col_filter_col3, col_filter_col4 = st.columns(4)
            with col_filter_col1:
                filter_업체명 = st.multiselect("업체명", 
                    options=list(df['업체명'].unique()) if not df.empty and '업체명' in df.columns else [],
                    default=[])
                filter_부서 = st.multiselect("부서",
                    options=list(df['부서'].unique()) if not df.empty and '부서' in df.columns else [],
                    default=[])
                filter_차종 = st.multiselect("차종",
                    options=list(df['차종'].unique()) if not df.empty and '차종' in df.columns else [],
                    default=[])
            with col_filter_col2:
                filter_진행상태 = st.multiselect("진행상태",
                    options=["접수", "자재준비중", "생산중", "출하완료"],
                    default=[])
                filter_출하장소 = st.multiselect("출하장소",
                    options=list(df['출하장소'].unique()) if not df.empty and '출하장소' in df.columns else [],
                    default=[])
                filter_담당자 = st.multiselect("담당자",
                    options=list(df['담당자'].unique()) if not df.empty and '담당자' in df.columns else [],
                    default=[])
            with col_filter_col3:
                filter_품번 = st.text_input("품번 필터", "")
                filter_품명 = st.text_input("품명 필터", "")
                filter_자재준비 = st.multiselect("자재준비",
                    options=list(df['자재준비'].unique()) if not df.empty and '자재준비' in df.columns and df['자재준비'].notna().any() else [],
                    default=[])
            with col_filter_col4:
                filter_납기일_시작 = st.date_input("납기일 시작", value=None, key="due_date_start")
                filter_납기일_종료 = st.date_input("납기일 종료", value=None, key="due_date_end")
                filter_출하일_시작 = st.date_input("출하일 시작", value=None, key="ship_date_start")
                filter_출하일_종료 = st.date_input("출하일 종료", value=None, key="ship_date_end")
        
        # 필터링 로직 (대시보드와 테이블 모두 동일한 필터 적용)
        filtered_df = df.copy()
        # CUSTOMER는 본인 회사의 모든 샘플 요청을 볼 수 있도록 필터링
        if user['role'] != 'ADMIN' and '업체명' in filtered_df.columns:
            # 업체명이 정확히 일치하는 모든 데이터 표시
            filtered_df = filtered_df[filtered_df['업체명'] == user['companyName']]
            
        if search_term:
            mask = filtered_df.astype(str).apply(lambda x: x.str.contains(search_term, case=False)).any(axis=1)
            filtered_df = filtered_df[mask]
        # ADMIN만 업체 필터 사용 가능 (CUSTOMER는 이미 필터링됨)
        if user['role'] == 'ADMIN' and company_filter != "전체" and '업체명' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['업체명'] == company_filter]
        if completion_filter == "완료" and '출하일' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['출하일'].notna() & (filtered_df['출하일'] != "")]
        elif completion_filter == "미완료" and '출하일' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['출하일'].isna() | (filtered_df['출하일'] == "")]
        
        # 컬럼별 필터 적용
        if filter_업체명 and '업체명' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['업체명'].isin(filter_업체명)]
        if filter_부서 and '부서' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['부서'].isin(filter_부서)]
        if filter_차종 and '차종' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['차종'].isin(filter_차종)]
        if filter_진행상태 and '진행상태' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['진행상태'].isin(filter_진행상태)]
        if filter_출하장소 and '출하장소' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['출하장소'].isin(filter_출하장소)]
        if filter_담당자 and '담당자' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['담당자'].isin(filter_담당자)]
        if filter_품번 and '품번' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['품번'].astype(str).str.contains(filter_품번, case=False, na=False)]
        if filter_품명 and '품명' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['품명'].astype(str).str.contains(filter_품명, case=False, na=False)]
        if filter_자재준비 and '자재준비' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['자재준비'].isin(filter_자재준비)]
        if filter_납기일_시작 and '납기일' in filtered_df.columns:
            filtered_df = filtered_df[
                (filtered_df['납기일'].notna()) & 
                (pd.to_datetime(filtered_df['납기일'], errors='coerce') >= pd.Timestamp(filter_납기일_시작))
            ]
        if filter_납기일_종료 and '납기일' in filtered_df.columns:
            filtered_df = filtered_df[
                (filtered_df['납기일'].notna()) & 
                (pd.to_datetime(filtered_df['납기일'], errors='coerce') <= pd.Timestamp(filter_납기일_종료))
            ]
        if filter_출하일_시작 and '출하일' in filtered_df.columns:
            filtered_df = filtered_df[
                (filtered_df['출하일'].notna()) & 
                (pd.to_datetime(filtered_df['출하일'], errors='coerce') >= pd.Timestamp(filter_출하일_시작))
            ]
        if filter_출하일_종료 and '출하일' in filtered_df.columns:
            filtered_df = filtered_df[
                (filtered_df['출하일'].notna()) & 
                (pd.to_datetime(filtered_df['출하일'], errors='coerce') <= pd.Timestamp(filter_출하일_종료))
            ]
        
        # 필터링된 데이터프레임의 진행상태도 업데이트 (원본과 동기화)
        filtered_df = update_progress_status(filtered_df)
        
        # 선택 상태 초기화
        if 'selected_rows' not in st.session_state:
            st.session_state.selected_rows = set()
        
        # 선택된 행만 대시보드 집계를 위한 데이터 준비
        dashboard_df = filtered_df.copy()
        if st.session_state.selected_rows:
            # 선택된 행만 필터링
            if 'NO' in filtered_df.columns:
                dashboard_df = filtered_df[filtered_df['NO'].isin(st.session_state.selected_rows)]
            else:
                dashboard_df = filtered_df[filtered_df.index.isin(st.session_state.selected_rows)]
        
        # [통계 대시보드] - 선택된 행이 있으면 선택된 행만, 없으면 필터링된 전체 데이터 기준으로 계산
        # 통계 계산용 변수 초기화
        total_orders = 0
        total_qty = 0
        completed_count = 0
        delayed_count = 0
        completion_rate = 0
        
        if not dashboard_df.empty:
            total_orders = len(dashboard_df)
            # 요청수량을 숫자 타입으로 변환 후 합계 계산
            if '요청수량' in dashboard_df.columns:
                total_qty = pd.to_numeric(dashboard_df['요청수량'], errors='coerce').fillna(0).sum()
            # 출하일이 있는 건수로 완료 건수 계산 (더 정확한 체크)
            if '출하일' in dashboard_df.columns:
                for idx, row in dashboard_df.iterrows():
                    출하일값 = row.get('출하일')
                    # 출하일이 None이 아니고, 빈 문자열이 아니고, NaN이 아닌 경우
                    if pd.notnull(출하일값) and 출하일값 is not None:
                        if isinstance(출하일값, str):
                            if 출하일값.strip() != "":
                                completed_count += 1
                        else:
                            # date 타입이거나 다른 타입인 경우
                            completed_count += 1
            # 납기일이 지난 건수 계산
            today = datetime.date.today()
            if '납기일' in dashboard_df.columns:
                for idx, row in dashboard_df.iterrows():
                    납기일값 = row.get('납기일')
                    출하일값 = row.get('출하일')
                    
                    # 납기일이 유효한 경우만 체크
                    if pd.notnull(납기일값) and 납기일값 is not None:
                        # 납기일을 date 타입으로 변환
                        due_date = None
                        if isinstance(납기일값, str):
                            try:
                                due_date = pd.to_datetime(납기일값).date()
                            except:
                                pass
                        elif isinstance(납기일값, datetime.date):
                            due_date = 납기일값
                        
                        # 출하일이 없거나 비어있는지 체크
                        출하일없음 = False
                        if pd.isna(출하일값) or 출하일값 is None:
                            출하일없음 = True
                        elif isinstance(출하일값, str):
                            if 출하일값.strip() == "":
                                출하일없음 = True
                        
                        # 납기일이 지났고 출하일이 없으면 지연
                        if due_date and due_date < today and 출하일없음:
                            delayed_count += 1
            
            completion_rate = int((completed_count / total_orders * 100)) if total_orders > 0 else 0
        
        # 통계 표시 (선택된 행이 있으면 표시)
        selected_info = ""
        if st.session_state.selected_rows:
            selected_count = len(st.session_state.selected_rows)
            selected_info = f" (선택된 {selected_count}건 기준)"
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("총 주문 건수", f"{total_orders}건", help=f"필터링된 데이터{selected_info} 기준" if selected_info else "필터링된 데이터 기준")
        c2.metric("총 요청 수량", f"{int(total_qty)} EA", help=f"필터링된 데이터{selected_info} 기준" if selected_info else "필터링된 데이터 기준")
        c3.metric("완료 건수", f"{completed_count}건", help=f"필터링된 데이터{selected_info} 기준" if selected_info else "필터링된 데이터 기준")
        c4.metric("납기 지연", f"{delayed_count}건", delta_color="inverse", delta=f"{delayed_count}건" if delayed_count > 0 else None, help=f"필터링된 데이터{selected_info} 기준" if selected_info else "필터링된 데이터 기준")
        c5.metric("완료율", f"{completion_rate}%", help=f"필터링된 데이터{selected_info} 기준" if selected_info else "필터링된 데이터 기준")
        
        st.divider()
        
        # 체크박스 컬럼 추가
        filtered_df_with_select = filtered_df.copy()
        if 'NO' in filtered_df.columns:
            select_values = [row_id in st.session_state.selected_rows for row_id in filtered_df['NO'].tolist()]
            filtered_df_with_select.insert(0, '선택', select_values)
        else:
            # NO 컬럼이 없으면 인덱스 사용
            select_values = [idx in st.session_state.selected_rows for idx in filtered_df.index]
            filtered_df_with_select.insert(0, '선택', select_values)
        
        # 선택 컬럼을 명시적으로 boolean 타입으로 변환
        filtered_df_with_select['선택'] = filtered_df_with_select['선택'].astype(bool)
        
        # [일괄 작업 버튼]
        if not filtered_df.empty:
            col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
            with col_btn1:
                if st.button("✅ 전체 선택", use_container_width=True):
                    if 'NO' in filtered_df.columns:
                        st.session_state.selected_rows = set(filtered_df['NO'].tolist())
                    else:
                        st.session_state.selected_rows = set(filtered_df.index.tolist())
                    st.rerun()
            with col_btn2:
                if st.button("❌ 선택 해제", use_container_width=True):
                    st.session_state.selected_rows = set()
                    st.rerun()
            with col_btn3:
                if 'NO' in filtered_df.columns:
                    selected_count = len([row_id for row_id in filtered_df['NO'].tolist() if row_id in st.session_state.selected_rows])
                else:
                    selected_count = len([idx for idx in filtered_df.index if idx in st.session_state.selected_rows])
                st.info(f"선택된 건수: **{selected_count}건**")
            with col_btn4:
                pass
            
            # 선택된 행이 있을 때 일괄 작업 버튼 표시
            if st.session_state.selected_rows:
                st.divider()
                col_action1, col_action2, col_action3, col_action4 = st.columns(4)
                
                with col_action1:
                    new_shipment_date = st.date_input("일괄 출하일 설정", value=datetime.date.today(), key="batch_shipment_date")
                    if st.button("📅 출하일 일괄 설정", use_container_width=True, type="primary"):
                        if 'NO' in filtered_df.columns:
                            selected_ids = [row_id for row_id in filtered_df['NO'].tolist() if row_id in st.session_state.selected_rows]
                            for row_id in selected_ids:
                                idx = st.session_state.df[st.session_state.df['NO'] == row_id].index
                                if not idx.empty:
                                    st.session_state.df.loc[idx[0], '출하일'] = new_shipment_date
                        else:
                            selected_indices = [idx for idx in filtered_df.index if idx in st.session_state.selected_rows]
                            for idx in selected_indices:
                                if idx < len(st.session_state.df):
                                    st.session_state.df.loc[idx, '출하일'] = new_shipment_date
                        # 진행상태 업데이트
                        st.session_state.df = update_progress_status(st.session_state.df)
                        save_data()
                        st.success(f"{len(selected_ids) if 'NO' in filtered_df.columns else len(selected_indices)}건의 출하일이 설정되었습니다.")
                        st.rerun()
                
                with col_action2:
                    if st.button("🗑️ 선택 항목 삭제", use_container_width=True, type="secondary"):
                        if 'NO' in filtered_df.columns:
                            selected_ids = [row_id for row_id in filtered_df['NO'].tolist() if row_id in st.session_state.selected_rows]
                            deleted_items = []
                            for row_id in selected_ids:
                                row_data = st.session_state.df[st.session_state.df['NO'] == row_id]
                                if not row_data.empty:
                                    item_dict = row_data.iloc[0].to_dict()
                                    item_dict['deletedAt'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    deleted_items.append(item_dict)
                                    st.session_state.df = st.session_state.df[st.session_state.df['NO'] != row_id]
                        else:
                            selected_indices = [idx for idx in filtered_df.index if idx in st.session_state.selected_rows]
                            deleted_items = []
                            for idx in selected_indices:
                                if idx < len(st.session_state.df):
                                    item_dict = st.session_state.df.iloc[idx].to_dict()
                                    item_dict['deletedAt'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    deleted_items.append(item_dict)
                                    st.session_state.df = st.session_state.df.drop(index=idx)
                        
                        if deleted_items:
                            st.session_state.deleted_history.extend(deleted_items)
                            st.session_state.selected_rows = set()
                            save_data()
                            st.success(f"{len(deleted_items)}건이 삭제되어 휴지통으로 이동했습니다.")
                            st.rerun()
                
                with col_action3:
                    new_material_prep = st.text_input("일괄 자재준비 입력", key="batch_material_prep")
                    if st.button("📦 자재준비 일괄 업데이트", use_container_width=True):
                        if 'NO' in filtered_df.columns:
                            selected_ids = [row_id for row_id in filtered_df['NO'].tolist() if row_id in st.session_state.selected_rows]
                            for row_id in selected_ids:
                                idx = st.session_state.df[st.session_state.df['NO'] == row_id].index
                                if not idx.empty:
                                    st.session_state.df.loc[idx[0], '자재준비'] = new_material_prep
                        else:
                            selected_indices = [idx for idx in filtered_df.index if idx in st.session_state.selected_rows]
                            for idx in selected_indices:
                                if idx < len(st.session_state.df):
                                    st.session_state.df.loc[idx, '자재준비'] = new_material_prep
                        # 진행상태 업데이트
                        st.session_state.df = update_progress_status(st.session_state.df)
                        save_data()
                        st.success(f"{len(selected_ids) if 'NO' in filtered_df.columns else len(selected_indices)}건의 자재준비가 업데이트되었습니다.")
                        st.rerun()
                
                with col_action4:
                    progress_options = ["접수", "자재준비중", "생산중", "출하완료"]
                    new_progress_status = st.selectbox("일괄 진행상태 변경", progress_options, key="batch_progress_status")
                    if st.button("📊 진행상태 일괄 변경", use_container_width=True, type="primary"):
                        if 'NO' in filtered_df.columns:
                            selected_ids = [row_id for row_id in filtered_df['NO'].tolist() if row_id in st.session_state.selected_rows]
                            updated_count = 0
                            for row_id in selected_ids:
                                idx = st.session_state.df[st.session_state.df['NO'] == row_id].index
                                if not idx.empty:
                                    # 진행상태에 따라 관련 필드 자동 업데이트
                                    if new_progress_status == "출하완료":
                                        st.session_state.df.loc[idx[0], '출하일'] = datetime.date.today()
                                    elif new_progress_status == "생산중":
                                        if pd.isna(st.session_state.df.loc[idx[0], '샘플 완료일']) or st.session_state.df.loc[idx[0], '샘플 완료일'] == "":
                                            st.session_state.df.loc[idx[0], '샘플 완료일'] = datetime.date.today()
                                    elif new_progress_status == "자재준비중":
                                        if pd.isna(st.session_state.df.loc[idx[0], '자재준비']) or st.session_state.df.loc[idx[0], '자재준비'] == "":
                                            st.session_state.df.loc[idx[0], '자재준비'] = "진행중"
                                    updated_count += 1
                        else:
                            selected_indices = [idx for idx in filtered_df.index if idx in st.session_state.selected_rows]
                            updated_count = 0
                            for idx in selected_indices:
                                if idx < len(st.session_state.df):
                                    # 진행상태에 따라 관련 필드 자동 업데이트
                                    if new_progress_status == "출하완료":
                                        st.session_state.df.loc[idx, '출하일'] = datetime.date.today()
                                    elif new_progress_status == "생산중":
                                        if pd.isna(st.session_state.df.loc[idx, '샘플 완료일']) or st.session_state.df.loc[idx, '샘플 완료일'] == "":
                                            st.session_state.df.loc[idx, '샘플 완료일'] = datetime.date.today()
                                    elif new_progress_status == "자재준비중":
                                        if pd.isna(st.session_state.df.loc[idx, '자재준비']) or st.session_state.df.loc[idx, '자재준비'] == "":
                                            st.session_state.df.loc[idx, '자재준비'] = "진행중"
                                    updated_count += 1
                        # 진행상태 업데이트
                        st.session_state.df = update_progress_status(st.session_state.df)
                        # 원본 데이터프레임도 업데이트된 상태로 저장
                        save_data()
                        st.success(f"{updated_count}건의 진행상태가 변경되었습니다.")
                        # 즉시 페이지 새로고침하여 변경사항 반영
                        time.sleep(0.5)
                        st.rerun()
                
                st.divider()
            
        # 원본 데이터프레임의 진행상태를 항상 최신으로 유지
        st.session_state.df = update_progress_status(st.session_state.df)
        
        # 필터링된 데이터프레임의 진행상태도 업데이트 (원본과 동기화)
        filtered_df = update_progress_status(filtered_df)
        
        # 컬럼 순서 정의 (이미지 템플릿 순서)
        column_order = ['NO', '접수일', '업체명', '부서', '담당자', '차종', '품번', '품명', '출하장소', 
                       '요청수량', '납기일', '요청사항', '도면접수일', '자재 요청일', '자재준비', 
                       '샘플 완료일', '출하일', '운송편', '비고', '샘플단가', '샘플금액', '진행상태']
        
        # 컬럼 순서에 맞게 재정렬 (존재하는 컬럼만)
        existing_columns = [col for col in column_order if col in filtered_df_with_select.columns]
        other_columns = [col for col in filtered_df_with_select.columns if col not in existing_columns and col != '선택']
        filtered_df_with_select = filtered_df_with_select[['선택'] + existing_columns + other_columns]
        
        # [메인 테이블] - 데이터 편집 가능 (템플릿 구조에 맞춤)
        edited_df = st.data_editor(
            filtered_df_with_select,
            column_config={
                "선택": st.column_config.CheckboxColumn("선택", width="small"),
                "NO": st.column_config.NumberColumn("NO.", disabled=True, format="%d"),
                "접수일": st.column_config.DateColumn("접수일"),
                "업체명": st.column_config.TextColumn("업체명"),
                "부서": st.column_config.TextColumn("부서"),
                "담당자": st.column_config.TextColumn("담당자"),
                "차종": st.column_config.TextColumn("차종"),
                "품번": st.column_config.TextColumn("품번"),
                "품명": st.column_config.TextColumn("품명"),
                "출하장소": st.column_config.TextColumn("출하장소"),
                "요청수량": st.column_config.NumberColumn("요청수량", format="%d"),
                "납기일": st.column_config.DateColumn("납기일"),
                "샘플단가": st.column_config.NumberColumn("샘플단가", format="%.0f"),
                "샘플금액": st.column_config.NumberColumn("샘플금액", format="%.0f"),
                "요청사항": st.column_config.TextColumn("요청사항"),
                "도면접수일": st.column_config.DateColumn("도면접수일"),
                "자재 요청일": st.column_config.DateColumn("자재 요청일"),
                "자재준비": st.column_config.TextColumn("자재준비"),
                "샘플 완료일": st.column_config.DateColumn("샘플 완료일"),
                "출하일": st.column_config.DateColumn("출하일"),
                "운송편": st.column_config.TextColumn("운송편"),
                "비고": st.column_config.TextColumn("비고"),
                "진행상태": st.column_config.SelectboxColumn(
                    "진행상태",
                    options=["접수", "자재준비중", "생산중", "출하완료"],
                    required=False
                ),
            },
            use_container_width=True,
            num_rows="dynamic",
            key="data_editor"
        )
        
        # 선택 상태 업데이트
        if '선택' in edited_df.columns:
            if 'NO' in edited_df.columns:
                current_selected = set(edited_df[edited_df['선택'] == True]['NO'].tolist())
            else:
                current_selected = set(edited_df[edited_df['선택'] == True].index.tolist())
            if current_selected != st.session_state.selected_rows:
                st.session_state.selected_rows = current_selected
                st.rerun()
        
        # 선택 컬럼 제거하여 나머지 처리
        edited_df = edited_df.drop(columns=['선택']) if '선택' in edited_df.columns else edited_df
        
        # [변경 사항 저장 로직]
        # st.data_editor는 session_state의 df를 직접 수정하지 않고 수정된 복사본을 리턴함
        # 따라서 원본 df를 업데이트하는 로직이 필요
        # 선택 컬럼을 제거한 후 비교
        edited_df_clean = edited_df.copy()
        if not edited_df_clean.equals(filtered_df):
            # 전체 DF에서 현재 필터링된 부분만 업데이트
            for index, row in edited_df_clean.iterrows():
                # 원본 데이터프레임의 해당 NO를 가진 행 업데이트
                if 'NO' in row:
                    idx = st.session_state.df[st.session_state.df['NO'] == row['NO']].index
                else:
                    # NO가 없으면 인덱스로 찾기
                    idx = st.session_state.df.index[st.session_state.df.index == index]
                
                if not idx.empty:
                    # 날짜 타입 유지
                    date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
                    for col in date_columns:
                        if col in row and isinstance(row[col], str) and row[col]:
                            try:
                                row[col] = pd.to_datetime(row[col], errors='coerce').date()
                            except:
                                pass
                    
                    # 진행상태가 변경된 경우 관련 필드 자동 업데이트
                    if '진행상태' in row and '진행상태' in st.session_state.df.columns:
                        original_status = st.session_state.df.loc[idx[0], '진행상태']
                        new_status = row.get('진행상태')
                        if original_status != new_status:
                            if new_status == "출하완료":
                                if pd.isna(st.session_state.df.loc[idx[0], '출하일']) or st.session_state.df.loc[idx[0], '출하일'] == "":
                                    row['출하일'] = datetime.date.today()
                            elif new_status == "생산중":
                                if pd.isna(st.session_state.df.loc[idx[0], '샘플 완료일']) or st.session_state.df.loc[idx[0], '샘플 완료일'] == "":
                                    row['샘플 완료일'] = datetime.date.today()
                            elif new_status == "자재준비중":
                                if pd.isna(st.session_state.df.loc[idx[0], '자재준비']) or st.session_state.df.loc[idx[0], '자재준비'] == "":
                                    row['자재준비'] = "진행중"
                    
                    st.session_state.df.loc[idx[0]] = row
            # 진행상태 업데이트
            st.session_state.df = update_progress_status(st.session_state.df)
            save_data()
            st.toast("✅ 데이터가 저장되었습니다!")

        # [엑셀 다운로드 및 업로드]
        c1, c2, c3 = st.columns(3)
        with c1:
            # Excel 템플릿 다운로드
            def create_template():
                template_df = pd.DataFrame(columns=['NO', '접수일', '업체명', '부서', '담당자', '차종', '품번', '품명', 
                                                   '출하장소', '요청수량', '납기일', '요청사항', '도면접수일', 
                                                   '자재 요청일', '자재준비', '샘플 완료일', '출하일', '운송편', '비고', 
                                                   '샘플단가', '샘플금액'])
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    template_df.to_excel(writer, index=False, sheet_name='Sheet1')
                return output.getvalue()
            
            template_data = create_template()
            st.download_button("📋 엑셀 템플릿 다운로드", data=template_data, file_name="sample_template.xlsx", 
                             mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        with c2:
            # Excel 데이터 다운로드
            def to_excel(df):
                output = BytesIO()
                # 컬럼 순서 정의
                column_order = ['NO', '접수일', '업체명', '부서', '담당자', '차종', '품번', '품명', '출하장소', 
                               '요청수량', '납기일', '요청사항', '도면접수일', '자재 요청일', '자재준비', 
                               '샘플 완료일', '출하일', '운송편', '비고', '샘플단가', '샘플금액', '진행상태']
                # 존재하는 컬럼만 선택하여 순서대로 정렬
                existing_cols = [col for col in column_order if col in df.columns]
                df_export = df[existing_cols].copy()
                # 날짜를 문자열로 변환
                date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
                for col in date_columns:
                    if col in df_export.columns:
                        df_export[col] = df_export[col].apply(lambda x: str(x) if pd.notnull(x) and x is not None else "")
                
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False, sheet_name='Sheet1')
                return output.getvalue()
            
            excel_data = to_excel(filtered_df)
            st.download_button("📥 엑셀 다운로드", data=excel_data, file_name="sample_requests.xlsx", 
                             mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        with c3:
            if user['role'] == 'ADMIN':
                uploaded_file = st.file_uploader("📤 엑셀 업로드 (데이터 병합)", type=['xlsx', 'xls'])
                if uploaded_file:
                    try:
                        new_data = pd.read_excel(uploaded_file)
                        # 컬럼명을 한글로 변환 (영문 컬럼명이 있을 경우 대비)
                        column_mapping = {
                            'NO': 'NO', 'no': 'NO', 'No': 'NO',
                            '접수일': '접수일', 'requestDate': '접수일',
                            '업체명': '업체명', 'companyName': '업체명',
                            '부서': '부서', 'department': '부서',
                            '담당자': '담당자', 'contactPerson': '담당자',
                            '차종': '차종', 'carModel': '차종',
                            '품번': '품번', 'partNumber': '품번',
                            '품명': '품명', 'partName': '품명',
                            '출하장소': '출하장소', 'shippingLocation': '출하장소',
                            '요청수량': '요청수량', 'quantity': '요청수량',
                            '납기일': '납기일', 'dueDate': '납기일',
                            '샘플단가': '샘플단가', 'samplePrice': '샘플단가',
                            '샘플금액': '샘플금액', 'sampleAmount': '샘플금액',
                            '요청사항': '요청사항', 'requirements': '요청사항',
                            '도면접수일': '도면접수일', 'drawingReceiptDate': '도면접수일',
                            '자재 요청일': '자재 요청일', 'materialRequestDate': '자재 요청일',
                            '자재준비': '자재준비', 'materialPreparation': '자재준비',
                            '샘플 완료일': '샘플 완료일', 'sampleCompletionDate': '샘플 완료일',
                            '출하일': '출하일', 'shipmentDate': '출하일',
                            '운송편': '운송편', 'shippingMethod': '운송편',
                            '비고': '비고', 'remarks': '비고'
                        }
                        new_data = new_data.rename(columns=column_mapping)
                        
                        # NO 컬럼이 없으면 자동 생성
                        if 'NO' not in new_data.columns:
                            # 기존 최대 NO 값 찾기
                            if not st.session_state.df.empty and 'NO' in st.session_state.df.columns:
                                max_no = st.session_state.df['NO'].max()
                                start_no = int(max_no) + 1 if pd.notnull(max_no) else int(datetime.datetime.now().timestamp())
                            else:
                                start_no = int(datetime.datetime.now().timestamp())
                            
                            # 새로운 NO 생성
                            new_data['NO'] = range(start_no, start_no + len(new_data))
                            st.info(f"엑셀 파일에 'NO' 컬럼이 없어 자동으로 생성했습니다. (시작 번호: {start_no})")
                        
                        # NO 중복 체크 및 병합 로직
                        if 'NO' in st.session_state.df.columns:
                            current_nos = st.session_state.df['NO'].tolist()
                            to_add = []
                            for _, row in new_data.iterrows():
                                row_no = row.get('NO')
                                # NO가 없거나 중복되지 않은 경우 추가
                                if pd.isna(row_no) or row_no == "" or row_no not in current_nos:
                                    # NO가 없으면 자동 생성
                                    if pd.isna(row_no) or row_no == "":
                                        if not st.session_state.df.empty and 'NO' in st.session_state.df.columns:
                                            max_no = st.session_state.df['NO'].max()
                                            row_no = int(max_no) + 1 if pd.notnull(max_no) else int(datetime.datetime.now().timestamp())
                                        else:
                                            row_no = int(datetime.datetime.now().timestamp())
                                        row['NO'] = row_no
                                    to_add.append(row.to_dict())
                            
                            if to_add:
                                # 날짜 컬럼 변환
                                date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
                                for item in to_add:
                                    for col in date_columns:
                                        if col in item and item[col]:
                                            try:
                                                item[col] = pd.to_datetime(item[col], errors='coerce').date()
                                            except:
                                                item[col] = None
                                
                                new_df = pd.DataFrame(to_add)
                                st.session_state.df = pd.concat([new_df, st.session_state.df], ignore_index=True)
                                # 진행상태 업데이트
                                st.session_state.df = update_progress_status(st.session_state.df)
                                save_data()
                                st.success(f"{len(to_add)}개 항목이 추가되었습니다.")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.warning("추가할 새로운 데이터(새로운 NO)가 없습니다.")
                        else:
                            # 원본 데이터프레임에 NO 컬럼이 없는 경우도 처리
                            if 'NO' not in new_data.columns:
                                new_data['NO'] = range(1, len(new_data) + 1)
                            
                            # 날짜 컬럼 변환
                            date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
                            for col in date_columns:
                                if col in new_data.columns:
                                    new_data[col] = pd.to_datetime(new_data[col], errors='coerce').dt.date
                            
                            new_data = update_progress_status(new_data)
                            st.session_state.df = pd.concat([new_data, st.session_state.df], ignore_index=True) if not st.session_state.df.empty else new_data
                            save_data()
                            st.success(f"{len(new_data)}개 항목이 추가되었습니다.")
                            time.sleep(1)
                            st.rerun()
                    except Exception as e:
                        st.error(f"업로드 실패: {e}")

    # --- 2. 신규 샘플 의뢰 (간결한 의뢰서) ---
    elif menu == "📝 신규 샘플 의뢰":
        st.header("신규 샘플 제작 의뢰서")
        st.info("💡 필수 정보만 입력해주세요. 나머지 정보는 관리자가 입력합니다.")
        
        with st.form("request_form"):
            col1, col2 = st.columns(2)
            with col1:
                company_name = st.text_input("1. 업체명 *", value=user['companyName'] if user['role']=='CUSTOMER' else "", help="필수 입력")
                department = st.text_input("2. 부서 *", help="필수 입력")
                contact = st.text_input("3. 담당자/직급 *", help="필수 입력")
                car_model = st.text_input("4. 차종 *", help="필수 입력")
                
            with col2:
                part_no = st.text_input("5. 품번 *", help="필수 입력")
                part_name = st.text_input("6. 품명 *", help="필수 입력")
                qty = st.number_input("7. 샘플수량 *", min_value=1, value=1, help="필수 입력")
                due_date = st.date_input("8. 납기일 *", datetime.date.today() + datetime.timedelta(days=7), help="필수 입력")
            
            requirements = st.text_area("9. 요청사항 *", placeholder="요청사항을 입력해주세요", help="필수 입력")
            
            submitted = st.form_submit_button("의뢰 등록", use_container_width=True, type="primary")
            
            if submitted:
                # 필수 필드 검증
                if not company_name or not department or not contact or not car_model or not part_no or not part_name or not requirements:
                    st.error("❌ 필수 항목을 모두 입력해주세요.")
                else:
                    # NO 생성 (기존 최대값 + 1 또는 타임스탬프 기반)
                    if not st.session_state.df.empty and 'NO' in st.session_state.df.columns:
                        max_no = st.session_state.df['NO'].max()
                        new_no = int(max_no) + 1 if pd.notnull(max_no) else int(datetime.datetime.now().timestamp())
                    else:
                        new_no = int(datetime.datetime.now().timestamp())
                    
                    # 접수일은 오늘 날짜로 자동 설정
                    req_date = datetime.date.today()
                    
                    new_entry = {
                        "NO": new_no,
                        "접수일": req_date,
                        "업체명": company_name,
                        "부서": department,
                        "담당자": contact,
                        "차종": car_model,
                        "품번": part_no,
                        "품명": part_name,
                        "출하장소": "",  # 관리자가 입력
                        "요청수량": qty,
                        "납기일": due_date,
                        "샘플단가": 0,  # 관리자가 입력
                        "샘플금액": 0,  # 관리자가 입력
                        "요청사항": requirements,
                        "도면접수일": None,  # 관리자가 입력
                        "자재 요청일": None,  # 관리자가 입력
                        "자재준비": "",  # 관리자가 입력
                        "샘플 완료일": None,  # 관리자가 입력
                        "출하일": None,  # 관리자가 입력
                        "운송편": "",  # 관리자가 입력
                        "비고": ""  # 관리자가 입력
                    }
                    
                    # DataFrame 상단에 추가
                    st.session_state.df = pd.concat([pd.DataFrame([new_entry]), st.session_state.df], ignore_index=True)
                    # 진행상태 업데이트
                    st.session_state.df = update_progress_status(st.session_state.df)
                    save_data()
                    st.success("✅ 의뢰가 성공적으로 등록되었습니다! 관리자가 나머지 정보를 입력합니다.")
                    time.sleep(1.5)
                    st.rerun()

    # --- 3. 휴지통 (DeletionHistoryPanel.tsx 대응) ---
    elif menu == "🗑️ 휴지통 (삭제 내역)":
        st.header("삭제된 항목 복구")
        
        history = st.session_state.deleted_history
        if not history:
            st.info("휴지통이 비어있습니다.")
        else:
            for item in history:
                company_name = item.get('업체명') or item.get('companyName', '알수없음')
                part_name = item.get('품명') or item.get('partName', '알수없음')
                deleted_at = item.get('deletedAt', '알수없음')
                item_id = item.get('NO') or item.get('id', '알수없음')
                
                with st.expander(f"{company_name} - {part_name} (삭제일: {deleted_at})"):
                    st.json(item)
                    if st.button("복구", key=f"restore_{item_id}"):
                        # 복구 로직
                        restored_item = item.copy()
                        if 'deletedAt' in restored_item:
                            del restored_item['deletedAt']
                        
                        st.session_state.df = pd.concat([pd.DataFrame([restored_item]), st.session_state.df], ignore_index=True)
                        
                        # 휴지통에서 제거
                        item_key = item.get('NO') or item.get('id')
                        st.session_state.deleted_history = [i for i in st.session_state.deleted_history 
                                                           if (i.get('NO') or i.get('id')) != item_key]
                        
                        save_data()
                        st.success("복구 완료!")
                        st.rerun()

    # --- 4. 백업 관리 ---
    elif menu == "💾 백업 관리":
        st.header("💾 백업 관리")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("백업 생성")
            if st.button("🔄 수동 백업 생성", use_container_width=True, type="primary"):
                with st.spinner("백업 생성 중..."):
                    success = create_backup_manual()
                    if success:
                        st.success("✅ 백업이 성공적으로 생성되었습니다!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ 백업 생성에 실패했습니다.")
        
        with col2:
            st.subheader("백업 정보")
            if USE_GOOGLE_SHEETS and GOOGLE_SHEETS_AVAILABLE:
                st.info("📊 Google Sheets 백업 사용 중")
                st.caption("자동 백업: 데이터 저장 시마다 실행")
                st.caption("백업 보관: 최근 10개")
            else:
                st.info("💾 로컬 파일 백업 사용 중")
                st.caption("백업 위치: 프로젝트 폴더")
        
        st.divider()
        
        st.subheader("백업 목록")
        backups = get_backup_list()
        
        if not backups:
            st.info("백업이 없습니다.")
        else:
            if USE_GOOGLE_SHEETS and GOOGLE_SHEETS_AVAILABLE:
                # Google Sheets 백업 목록
                st.write(f"**총 {len(backups)}개의 백업이 있습니다.**")
                
                for i, backup_sheet in enumerate(backups):
                    backup_name = backup_sheet.title
                    # 백업_20241215_143022 형식에서 날짜 추출
                    try:
                        date_str = backup_name.replace("백업_", "")
                        if len(date_str) >= 15:
                            year = date_str[:4]
                            month = date_str[4:6]
                            day = date_str[6:8]
                            hour = date_str[9:11]
                            minute = date_str[11:13]
                            second = date_str[13:15]
                            formatted_date = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                        else:
                            formatted_date = backup_name
                    except:
                        formatted_date = backup_name
                    
                    with st.expander(f"📦 {formatted_date} - {backup_name}"):
                        col_dl, col_info = st.columns([1, 2])
                        with col_dl:
                            backup_data = download_backup_from_sheets(backup_name)
                            if backup_data:
                                st.download_button(
                                    label="💾 Excel 파일 다운로드",
                                    data=backup_data,
                                    file_name=f"{backup_name}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"dl_{i}"
                                )
                        with col_info:
                            st.caption(f"백업 시트: {backup_name}")
                            st.caption(f"생성일: {formatted_date}")
            else:
                # 로컬 파일 백업 정보
                for backup in backups:
                    with st.expander(f"📦 {backup['name']}"):
                        st.write(f"**생성일**: {backup['date']}")
                        st.write(f"**위치**: {DATA_FILE}, {HISTORY_FILE}")
                        # 현재 데이터를 Excel로 다운로드
                        df_copy = st.session_state.df.copy()
                        date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
                        for col in date_columns:
                            if col in df_copy.columns:
                                df_copy[col] = df_copy[col].apply(lambda x: str(x) if pd.notnull(x) and x is not None else "")
                        
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_copy.to_excel(writer, index=False, sheet_name='Sheet1')
                        
                        st.download_button(
                            label="💾 Excel 파일 다운로드",
                            data=output.getvalue(),
                            file_name=f"백업_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_local"
                        )
        
        st.divider()
        st.subheader("백업 설정")
        st.info("""
        **자동 백업**
        - Google Sheets 사용 시: 데이터 저장 시마다 자동으로 백업 생성
        - 최근 10개의 백업이 자동으로 유지됩니다
        
        **수동 백업**
        - 위의 '수동 백업 생성' 버튼을 클릭하여 언제든지 백업을 생성할 수 있습니다
        """)

# -----------------------------------------------------------------------------
# 앱 실행 진입점
# -----------------------------------------------------------------------------
load_data()

if 'user' not in st.session_state:
    login_screen()
else:
    main_app()