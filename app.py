import streamlit as st
import pandas as pd
import datetime
import time
import json
import os
from io import BytesIO
import urllib.request
import urllib.error

# gspread 관련 import (선택적)
try:
    import gspread
    from google.oauth2 import service_account
    USE_GSPREAD = True
except ImportError:
    USE_GSPREAD = False
    gspread = None
    service_account = None

# -----------------------------------------------------------------------------
# 1. 초기 설정 및 상수
# -----------------------------------------------------------------------------
st.set_page_config(page_title="신성EP 통합 샘플 관리 대장", layout="wide", page_icon="🏭")

DATA_FILE = "ssep_data.json"
HISTORY_FILE = "ssep_history.json"

# [중요] 구글 시트 설정
# 구글 폼 응답 시트 ID: 12C5nfRZVfakXGm6tWx9vbRmM36LtsjWBnQUR_VjAz2s
SHEET_ID = "12C5nfRZVfakXGm6tWx9vbRmM36LtsjWBnQUR_VjAz2s"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

# gspread 클라이언트 초기화 (선택적)
@st.cache_resource
def init_gspread_client():
    """gspread 클라이언트 초기화"""
    if not USE_GSPREAD:
        return None
    
    try:
        # Streamlit secrets에서 서비스 계정 정보 가져오기
        # [connections.gsheets] 형식 우선, 없으면 [gcp_service_account] 형식 사용
        credentials_info = None
        
        if 'connections' in st.secrets and 'gsheets' in st.secrets['connections']:
            # st.connection 방식: [connections.gsheets]
            credentials_info = dict(st.secrets['connections']['gsheets'])
        elif 'gcp_service_account' in st.secrets:
            # 기존 방식: [gcp_service_account] (하위 호환성)
            credentials_info = dict(st.secrets['gcp_service_account'])
        
        if credentials_info:
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            )
            gc = gspread.authorize(credentials)
            return gc
        else:
            return None
    except Exception as e:
        st.warning(f"gspread 초기화 실패: {e}")
        return None

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
    if pd.notnull(row.get('출하일')) and row.get('출하일') != "":
        return "출하완료"
    elif pd.notnull(row.get('샘플 완료일')) and row.get('샘플 완료일') != "":
        return "생산중"
    elif pd.notnull(row.get('자재준비')) and row.get('자재준비') != "":
        return "자재준비중"
    elif pd.notnull(row.get('접수일')) and row.get('접수일') != "":
        return "접수"
    else:
        return "접수"

def update_progress_status(df):
    """데이터프레임의 모든 행에 대해 진행상태를 계산하여 업데이트"""
    if df.empty:
        return df
    
    df['진행상태'] = df.apply(calculate_progress_status, axis=1)
    return df

def load_data_from_google_sheets():
    """구글 시트에서 데이터를 읽어와 앱 형식에 맞게 변환 (gspread 우선, CSV fallback)"""
    df = None
    
    # 1. gspread를 사용한 읽기 시도
    if USE_GSPREAD:
        gc = init_gspread_client()
        if gc:
            try:
                spreadsheet = gc.open_by_key(SHEET_ID)
                # 첫 번째 워크시트 가져오기
                worksheet = spreadsheet.sheet1
                # 모든 데이터 가져오기
                records = worksheet.get_all_records()
                if records:
                    df = pd.DataFrame(records)
                else:
                    # 헤더만 있는 경우
                    headers = worksheet.row_values(1)
                    df = pd.DataFrame(columns=headers)
            except Exception as e:
                st.warning(f"gspread로 데이터 로드 실패, CSV 방식으로 시도: {e}")
                df = None
    
    # 2. gspread 실패 시 CSV 방식으로 fallback
    if df is None or df.empty:
        try:
            # CSV 데이터 읽기 (에러 나는 줄은 건너뜀)
            # urllib을 사용하여 더 명확한 에러 처리
            try:
                with urllib.request.urlopen(SPREADSHEET_URL, timeout=10) as response:
                    df = pd.read_csv(response, on_bad_lines='skip', encoding='utf-8')
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    st.error("""
                    **❌ 구글 시트 접근 권한 오류 (401 Unauthorized)**
                    
                    **해결 방법:**
                    1. 구글 시트를 열어주세요: https://docs.google.com/spreadsheets/d/12C5nfRZVfakXGm6tWx9vbRmM36LtsjWBnQUR_VjAz2s
                    2. 우측 상단의 **"공유"** 버튼을 클릭하세요
                    3. **"링크가 있는 모든 사용자"** 또는 **"모든 사용자"**에게 **"뷰어"** 권한을 부여하세요
                    4. 설정 후 잠시 기다린 뒤 "데이터 새로고침" 버튼을 클릭하세요
                    
                    ⚠️ 시트가 비공개로 설정되어 있으면 CSV export가 작동하지 않습니다.
                    """)
                    return None
                elif e.code == 403:
                    st.error("""
                    **❌ 구글 시트 접근 거부 (403 Forbidden)**
                    
                    시트에 대한 접근 권한이 없습니다. 시트 소유자에게 접근 권한을 요청하세요.
                    """)
                    return None
                else:
                    raise e
        except urllib.error.URLError as e:
            st.error(f"**❌ 네트워크 오류**: 구글 시트에 연결할 수 없습니다. 인터넷 연결을 확인하세요.\n\n오류: {e}")
            return None
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                st.error("""
                **❌ 구글 시트 접근 권한 오류 (401 Unauthorized)**
                
                **해결 방법:**
                1. 구글 시트를 열어주세요: https://docs.google.com/spreadsheets/d/12C5nfRZVfakXGm6tWx9vbRmM36LtsjWBnQUR_VjAz2s
                2. 우측 상단의 **"공유"** 버튼을 클릭하세요
                3. **"링크가 있는 모든 사용자"** 또는 **"모든 사용자"**에게 **"뷰어"** 권한을 부여하세요
                4. 설정 후 잠시 기다린 뒤 "데이터 새로고침" 버튼을 클릭하세요
                
                ⚠️ 시트가 비공개로 설정되어 있으면 CSV export가 작동하지 않습니다.
                """)
            else:
                st.error(f"**❌ 구글 시트 데이터 로드 실패**: {error_msg}\n\n로컬 파일을 사용합니다.")
            return None
        
        # CSV 로드 후 데이터 확인
        if df is None or df.empty:
            return None
        
        # CSV에서 로드한 데이터 처리
        # 구글 폼 헤더를 앱 내부 컬럼명으로 변경 (매핑)
        # 접수일 처리: 신청일자 우선, 없으면 타임스탬프 사용
        if '신청일자' in df.columns:
            df['접수일'] = df['신청일자']
        elif '타임스탬프' in df.columns:
            df['접수일'] = df['타임스탬프']
        
        # 컬럼 매핑 (모든 가능한 컬럼명을 매핑)
        rename_map = {
            # 새 폼 구조
            '업체명 입력': '업체명',
            '담당자 성함 입력': '담당자',
            '품목명 입력': '품명',
            '요청수량 입력': '요청수량',
            '납기희망일 입력': '납기일',
            '요청사항 및 비고 입력': '요청사항',
            '연락처 입력': '연락처',
            '이메일 입력': '이메일',
            # 기존 폼 구조 (하위 호환성)
            '담당자 성함': '담당자',
            '품목명': '품명',
            '납기희망일': '납기일',
            '요청사항 및 비고': '요청사항'
        }
        df = df.rename(columns=rename_map)

        # 날짜 형식 정리 (타임스탬프 2024. 12. 28... -> 2024-12-28)
        if '접수일' in df.columns:
            df['접수일'] = pd.to_datetime(df['접수일'], errors='coerce').dt.date
        
        # 없는 컬럼 채우기 (앱 작동을 위해 필수)
        required_cols = ['NO', '부서', '차종', '품번', '출하장소', '자재준비', '샘플 완료일', '출하일', '비고', '샘플단가', '샘플금액', '운송편', '도면접수일', '자재 요청일']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""  # 빈 값으로 생성

        # NO(주문번호) 자동 생성 (없으면 인덱스 기반으로 생성)
        # 구글 폼에는 NO가 없으므로 1000번부터 시작해서 자동으로 붙임
        if 'NO' not in df.columns or df['NO'].isnull().all() or (df['NO'] == "").all():
            df['NO'] = range(1001, 1001 + len(df))
    
    # 데이터가 있는 경우 처리 (gspread로 로드한 경우)
    if df is not None and not df.empty:
        # 2. 구글 폼 헤더를 앱 내부 컬럼명으로 변경 (매핑)
        # 새 폼 구조: 타임스탬프, 신청일자, 업체명 입력, 담당자 성함 입력, 연락처 입력, 이메일 입력, 품목명 입력, 요청수량 입력, 납기희망일 입력, 요청사항 및 비고 입력
        
        # 접수일 처리: 신청일자 우선, 없으면 타임스탬프 사용
        if '신청일자' in df.columns:
            df['접수일'] = df['신청일자']
        elif '타임스탬프' in df.columns:
            df['접수일'] = df['타임스탬프']
        
        # 컬럼 매핑 (모든 가능한 컬럼명을 매핑)
        rename_map = {
            # 새 폼 구조
            '업체명 입력': '업체명',
            '담당자 성함 입력': '담당자',
            '품목명 입력': '품명',
            '요청수량 입력': '요청수량',
            '납기희망일 입력': '납기일',
            '요청사항 및 비고 입력': '요청사항',
            '연락처 입력': '연락처',
            '이메일 입력': '이메일',
            # 기존 폼 구조 (하위 호환성)
            '담당자 성함': '담당자',
            '품목명': '품명',
            '납기희망일': '납기일',
            '요청사항 및 비고': '요청사항'
        }
        df = df.rename(columns=rename_map)

        # 3. 날짜 형식 정리 (타임스탬프 2024. 12. 28... -> 2024-12-28)
        if '접수일' in df.columns:
            df['접수일'] = pd.to_datetime(df['접수일'], errors='coerce').dt.date
        
        # 4. 없는 컬럼 채우기 (앱 작동을 위해 필수)
        required_cols = ['NO', '부서', '차종', '품번', '출하장소', '자재준비', '샘플 완료일', '출하일', '비고', '샘플단가', '샘플금액', '운송편', '도면접수일', '자재 요청일']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""  # 빈 값으로 생성

        # 5. NO(주문번호) 자동 생성 (없으면 인덱스 기반으로 생성)
        # 구글 폼에는 NO가 없으므로 1000번부터 시작해서 자동으로 붙임
        if 'NO' not in df.columns or df['NO'].isnull().all() or (df['NO'] == "").all():
            df['NO'] = range(1001, 1001 + len(df))
    
    # 함수 마지막에 df 반환 (없으면 None)
    if df is None or df.empty:
        return None
    return df

def create_backup_manual():
    """수동 백업 생성"""
    save_data_to_local()
    return True

def get_backup_list():
    """백업 목록 가져오기"""
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
    """백업 다운로드"""
    try:
        df = st.session_state.df.copy()
        date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
        for col in date_columns:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: str(x) if pd.notnull(x) and x is not None else "")
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        return output.getvalue()
    except Exception as e:
        st.error(f"백업 다운로드 오류: {e}")
        return None

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

def get_deleted_nos():
    """삭제된 NO 목록을 반환하는 함수"""
    deleted_nos = set()
    if 'deleted_history' in st.session_state and st.session_state.deleted_history:
        for item in st.session_state.deleted_history:
            if isinstance(item, dict):
                no = item.get('NO') or item.get('no') or item.get('id')
                if no is not None and pd.notnull(no):
                    deleted_nos.add(int(no) if isinstance(no, (int, float)) else no)
    return deleted_nos

def load_data():
    """데이터 로드 메인 함수"""
    # 삭제 기록 먼저 초기화 (save_data_to_local() 호출 전에 필요)
    if 'deleted_history' not in st.session_state:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    st.session_state.deleted_history = json.load(f)
            except:
                st.session_state.deleted_history = []
        else:
            st.session_state.deleted_history = []
    
    # 삭제된 NO 목록 가져오기
    deleted_nos = get_deleted_nos()
    
    if 'df' not in st.session_state:
        # 1. 구글 시트에서 최신 데이터 가져오기 시도
        df = load_data_from_google_sheets()
        
        if df is not None and not df.empty:
            st.session_state.df = convert_dataframe_types(df)
            st.session_state.df = update_progress_status(st.session_state.df)
            # 삭제된 NO 필터링 (중요: 삭제된 데이터는 제외)
            if 'NO' in st.session_state.df.columns and deleted_nos:
                before_count = len(st.session_state.df)
                st.session_state.df = st.session_state.df[~st.session_state.df['NO'].isin(deleted_nos)]
                after_count = len(st.session_state.df)
                if before_count != after_count:
                    # 삭제된 항목이 필터링되었음을 로그에 기록 (필요시)
                    pass
            # 구글 시트 데이터가 있으면 로컬에도 백업 저장
            save_data_to_local() 
        elif os.path.exists(DATA_FILE):
            # 2. 구글 시트 실패 시 로컬 파일 로드
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    st.session_state.df = pd.DataFrame(data)
                    st.session_state.df = convert_dataframe_types(st.session_state.df)
                    st.session_state.df = update_progress_status(st.session_state.df)
                    # 삭제된 NO 필터링
                    if 'NO' in st.session_state.df.columns and deleted_nos:
                        st.session_state.df = st.session_state.df[~st.session_state.df['NO'].isin(deleted_nos)]
            except:
                st.session_state.df = pd.DataFrame(INITIAL_DATA)
                st.session_state.df = convert_dataframe_types(st.session_state.df)
                st.session_state.df = update_progress_status(st.session_state.df)
        else:
            st.session_state.df = pd.DataFrame(INITIAL_DATA)
            st.session_state.df = convert_dataframe_types(st.session_state.df)
            st.session_state.df = update_progress_status(st.session_state.df)
    else:
        # df가 이미 있는 경우에도 삭제된 NO 필터링 (구글 시트 새로고침 시 대비)
        if 'NO' in st.session_state.df.columns and deleted_nos:
            before_count = len(st.session_state.df)
            st.session_state.df = st.session_state.df[~st.session_state.df['NO'].isin(deleted_nos)]
            after_count = len(st.session_state.df)
            if before_count != after_count:
                # 삭제된 항목이 필터링되었음을 확인
                save_data_to_local()  # 필터링된 데이터 저장

def save_data_to_google_sheets():
    """구글 시트에 데이터 저장 (gspread 사용)"""
    if not USE_GSPREAD:
        return False
    
    gc = init_gspread_client()
    if not gc:
        return False
    
    try:
        spreadsheet = gc.open_by_key(SHEET_ID)
        worksheet = spreadsheet.sheet1
        
        # 데이터프레임 준비
        df_copy = st.session_state.df.copy()
        
        # 날짜를 문자열로 변환
        date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
        for col in date_columns:
            if col in df_copy.columns:
                df_copy[col] = df_copy[col].apply(lambda x: str(x) if pd.notnull(x) and x is not None else "")
        
        # None 값을 빈 문자열로 변환
        df_copy = df_copy.fillna("")
        
        # 컬럼 순서 정의
        column_order = ['NO', '접수일', '업체명', '부서', '담당자', '차종', '품번', '품명', '출하장소', 
                       '요청수량', '납기일', '요청사항', '도면접수일', '자재 요청일', '자재준비', 
                       '샘플 완료일', '출하일', '운송편', '비고', '샘플단가', '샘플금액', '진행상태']
        
        # 존재하는 컬럼만 선택
        existing_cols = [col for col in column_order if col in df_copy.columns]
        other_cols = [col for col in df_copy.columns if col not in existing_cols]
        df_copy = df_copy[existing_cols + other_cols]
        
        # 헤더와 데이터 준비
        headers = df_copy.columns.tolist()
        values = df_copy.values.tolist()
        
        # 시트 전체 지우기
        worksheet.clear()
        
        # 헤더 쓰기
        worksheet.append_row(headers)
        
        # 데이터 쓰기
        if values:
            worksheet.append_rows(values)
        
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 실패: {e}")
        return False

def save_data():
    """데이터 저장 (구글 시트 + 로컬 파일)"""
    # 1. 구글 시트에 저장 시도 (gspread 사용)
    google_success = save_data_to_google_sheets()
    
    # 2. 로컬 파일에도 저장 (백업)
    save_data_to_local()
    
    if google_success:
        st.toast("✅ 데이터가 구글 시트와 로컬 파일에 저장되었습니다.")
    else:
        st.toast("⚠️ 구글 시트 저장 실패. 로컬 파일에만 저장되었습니다.")

def save_data_to_local():
    """로컬 파일에 데이터 저장 (백업용)"""
    df_copy = st.session_state.df.copy()
    # 날짜를 문자열로 변환
    date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
    for col in date_columns:
        if col in df_copy.columns:
            df_copy[col] = df_copy[col].apply(lambda x: str(x) if pd.notnull(x) and x is not None else "")
    
    data = df_copy.to_dict('records')
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # deleted_history 저장
    history_data = []
    deleted_history = st.session_state.get('deleted_history', [])
    if deleted_history:
        for item in deleted_history:
            if isinstance(item, dict):
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
        
        menu_options = ["📊 샘플관리 현황판", "📝 신규 샘플 의뢰", "🗑️ 휴지통 (삭제 내역)", "💾 백업 관리"]
        if user['role'] == 'ADMIN':
            menu_options.append("📁 데이터 관리")
        menu = st.radio("메뉴 선택", menu_options)
        
        st.divider()
        if st.button("🔄 데이터 새로고침 (구글폼 동기화)"):
            # 강제로 다시 로드 (삭제된 데이터는 자동으로 필터링됨)
            if 'df' in st.session_state:
                del st.session_state.df
            st.rerun()
        
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
        st.info("💡 '데이터 새로고침' 버튼을 누르면 구글 폼에서 들어온 최신 주문이 표시됩니다.")
        
        # 최신 데이터 가져오기 (항상 최신 상태 유지)
        # 진행상태를 먼저 업데이트하여 최신 상태 보장
        if 'df' in st.session_state and not st.session_state.df.empty:
            st.session_state.df = update_progress_status(st.session_state.df)
        df = st.session_state.df.copy() if 'df' in st.session_state else pd.DataFrame()
        
        if df.empty:
            st.warning("데이터가 없습니다. 구글 폼으로 접수하거나 로컬 데이터를 확인하세요.")
            st.stop()  # 데이터가 없으면 여기서 중단
        
        # 접수 목록 실시간 표시 (리스트 형태)
        st.subheader("📋 접수된 샘플 요청 목록")
        if not df.empty and '업체명' in df.columns:
            # 최근 접수된 항목들을 표시 (최대 20개)
            # 고객 필터링 적용 (관리자는 전체, 고객은 본인 회사만)
            display_df = df.copy()
            if user['role'] != 'ADMIN' and '업체명' in display_df.columns:
                display_df = display_df[display_df['업체명'] == user['companyName']]
            
            if '접수일' in display_df.columns:
                display_df = display_df.sort_values('접수일', ascending=False, na_position='last')
            display_df = display_df.head(20)
            
            # 클릭된 항목을 저장할 session_state 초기화
            if 'clicked_item_no' not in st.session_state:
                st.session_state.clicked_item_no = None
            
            # 리스트 형태로 표시 (테이블 형식)
            list_data = []
            for idx, row in display_df.iterrows():
                item_no = row.get('NO', idx)
                업체명 = row.get('업체명', 'N/A')
                품명 = row.get('품명', 'N/A')
                납기일 = row.get('납기일', 'N/A')
                진행상태 = row.get('진행상태', 'N/A')
                접수일 = row.get('접수일', 'N/A')
                
                # 진행상태에 따른 색상
                status_color = {
                    '출하완료': '#28a745',
                    '생산중': '#ffc107',
                    '자재준비중': '#17a2b8',
                    '접수': '#6c757d'
                }.get(진행상태, '#6c757d')
                
                # 날짜 형식 안전하게 변환
                def safe_date_format(date_value):
                    """날짜 값을 안전하게 문자열로 변환"""
                    if pd.isna(date_value) or date_value is None:
                        return 'N/A'
                    if isinstance(date_value, str):
                        return date_value
                    if isinstance(date_value, (datetime.date, datetime.datetime)):
                        try:
                            return date_value.strftime('%Y-%m-%d')
                        except:
                            return str(date_value)
                    return str(date_value)
                
                list_data.append({
                    'NO': item_no,
                    '접수일': safe_date_format(접수일),
                    '업체명': 업체명,
                    '품명': 품명,
                    '납기일': safe_date_format(납기일),
                    '진행상태': 진행상태
                })
            
            # 리스트를 데이터프레임으로 변환하여 표시
            if list_data:
                list_df = pd.DataFrame(list_data)
                
                # 헤더 표시
                header_cols = st.columns([0.5, 1.2, 1.5, 2.5, 2, 1.2, 1.2, 1.5])
                with header_cols[0]:
                    st.write("**순번**")
                with header_cols[1]:
                    st.write("**NO**")
                with header_cols[2]:
                    st.write("**접수일**")
                with header_cols[3]:
                    st.write("**업체명**")
                with header_cols[4]:
                    st.write("**품명**")
                with header_cols[5]:
                    st.write("**납기일**")
                with header_cols[6]:
                    st.write("**진행상태**")
                with header_cols[7]:
                    st.write("**작업**")
                st.divider()
                
                # 각 행 표시
                for i, row in list_df.iterrows():
                    cols = st.columns([0.5, 1.2, 1.5, 2.5, 2, 1.2, 1.2, 1.5])
                    with cols[0]:
                        st.write(f"{i+1}")
                    with cols[1]:
                        st.write(f"**{row['NO']}**")
                    with cols[2]:
                        st.write(row['접수일'])
                    with cols[3]:
                        st.write(f"**{row['업체명']}**")
                    with cols[4]:
                        st.write(row['품명'])
                    with cols[5]:
                        st.write(row['납기일'])
                    with cols[6]:
                        # 진행상태 색상 적용
                        status_icon = {
                            '출하완료': '🟢',
                            '생산중': '🟡',
                            '자재준비중': '🔵',
                            '접수': '⚪'
                        }.get(row['진행상태'], '⚪')
                        st.write(f"{status_icon} {row['진행상태']}")
                    with cols[7]:
                        # 클릭 버튼
                        if st.button("📌 보기", key=f"view_{row['NO']}_{i}", use_container_width=True):
                            st.session_state.clicked_item_no = row['NO']
                            st.rerun()
                    
                    if i < len(list_df) - 1:
                        st.divider()
            else:
                st.info("접수된 샘플 요청이 없습니다.")
        
        st.divider()
        
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
        
        # 클릭된 항목이 있으면 알림 표시 및 필터 초기화 옵션 제공
        if st.session_state.clicked_item_no is not None:
            clicked_item = df[df['NO'] == st.session_state.clicked_item_no] if 'NO' in df.columns else pd.DataFrame()
            if not clicked_item.empty:
                item_info = clicked_item.iloc[0]
                st.success(f"📌 선택된 항목: NO.{st.session_state.clicked_item_no} - {item_info.get('업체명', 'N/A')} / {item_info.get('품명', 'N/A')}")
                col_reset1, col_reset2 = st.columns([1, 10])
                with col_reset1:
                    if st.button("❌ 필터 초기화", key="reset_clicked_item"):
                        st.session_state.clicked_item_no = None
                        st.rerun()
        
        # 필터링 로직 (대시보드와 테이블 모두 동일한 필터 적용)
        filtered_df = df.copy()
        # CUSTOMER는 본인 회사의 모든 샘플 요청을 볼 수 있도록 필터링
        if user['role'] != 'ADMIN' and '업체명' in filtered_df.columns:
            # 업체명이 정확히 일치하는 모든 데이터 표시
            filtered_df = filtered_df[filtered_df['업체명'] == user['companyName']]
        
        # 클릭된 항목이 있으면 해당 항목만 표시
        if st.session_state.clicked_item_no is not None and 'NO' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['NO'] == st.session_state.clicked_item_no]
            
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
                            if 'deleted_history' not in st.session_state:
                                st.session_state.deleted_history = []
                            # 삭제된 항목을 deleted_history에 추가 (NO 확실히 저장)
                            for item in deleted_items:
                                # NO가 없으면 추가
                                if 'NO' not in item or pd.isna(item.get('NO')):
                                    # 인덱스나 다른 방법으로 NO 찾기
                                    if 'NO' in filtered_df.columns:
                                        # 이미 item_dict에 NO가 포함되어 있어야 함
                                        pass
                                st.session_state.deleted_history.append(item)
                            st.session_state.selected_rows = set()
                            # 삭제된 데이터는 df에서 제거되었으므로 저장
                            save_data()
                            st.success(f"{len(deleted_items)}건이 삭제되어 휴지통으로 이동했습니다. (삭제된 NO: {[item.get('NO', 'N/A') for item in deleted_items[:5]]}{'...' if len(deleted_items) > 5 else ''})")
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
            # toast는 save_data() 내부에서 표시되므로 여기서는 제거

        # [엑셀 다운로드 및 업로드]
        st.divider()
        st.subheader("📁 엑셀 파일 관리")
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
                st.markdown("**📤 엑셀 업로드 (예전 데이터 불러오기)**")
                st.caption("엑셀 파일을 업로드하면 기존 데이터에 병합됩니다.")
                uploaded_file = st.file_uploader("엑셀 파일 선택", type=['xlsx', 'xls'], label_visibility="collapsed")
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
        
        history = st.session_state.get('deleted_history', [])
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
                        if 'deleted_history' in st.session_state:
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
            st.info("💾 로컬 파일 백업 사용 중")
            st.caption("백업 위치: 프로젝트 폴더")
            st.caption("⚠️ CSV 방식은 읽기 전용입니다")
        
        st.divider()
        
        st.subheader("백업 목록")
        backups = get_backup_list()
        
        if not backups:
            st.info("백업이 없습니다.")
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
        **데이터 저장**
        - CSV 방식은 읽기 전용이므로 변경사항은 로컬 파일에만 저장됩니다
        - 앱을 재시작하면 구글 폼의 최신 데이터로 다시 로드됩니다
        
        **수동 백업**
        - 위의 '수동 백업 생성' 버튼을 클릭하여 언제든지 백업을 생성할 수 있습니다
        """)
    
    # --- 5. 데이터 관리 (관리자 전용) ---
    elif menu == "📁 데이터 관리":
        st.header("📁 데이터 관리")
        st.info("💡 예전 데이터를 엑셀 파일로 업로드하여 시스템에 추가할 수 있습니다.")
        
        st.divider()
        st.subheader("📤 예전 데이터 업로드")
        
        col_info, col_upload = st.columns([1, 1])
        
        with col_info:
            st.markdown("""
            **사용 방법:**
            1. 엑셀 파일을 준비하세요 (템플릿 다운로드 가능)
            2. 파일을 업로드하면 기존 데이터에 자동으로 병합됩니다
            3. 중복된 NO는 자동으로 건너뜁니다
            4. NO가 없으면 자동으로 생성됩니다
            
            **지원 형식:**
            - .xlsx (Excel 2007 이상)
            - .xls (Excel 97-2003)
            """)
        
        with col_upload:
            # 엑셀 템플릿 다운로드
            def create_upload_template():
                template_df = pd.DataFrame(columns=[
                    'NO', '접수일', '업체명', '부서', '담당자', '차종', '품번', '품명', 
                    '출하장소', '요청수량', '납기일', '요청사항', '도면접수일', 
                    '자재 요청일', '자재준비', '샘플 완료일', '출하일', '운송편', '비고', 
                    '샘플단가', '샘플금액'
                ])
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    template_df.to_excel(writer, index=False, sheet_name='Sheet1')
                return output.getvalue()
            
            template_data = create_upload_template()
            st.download_button(
                "📋 업로드용 템플릿 다운로드", 
                data=template_data, 
                file_name="data_upload_template.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            st.divider()
            
            uploaded_file = st.file_uploader(
                "📤 엑셀 파일 업로드", 
                type=['xlsx', 'xls'],
                help="예전 데이터가 포함된 엑셀 파일을 선택하세요"
            )
            
            if uploaded_file:
                with st.spinner("파일을 읽는 중..."):
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
                        
                        st.success(f"✅ 파일 읽기 완료: {len(new_data)}개 행 발견")
                        
                        # 미리보기
                        with st.expander("📋 업로드할 데이터 미리보기", expanded=True):
                            st.dataframe(new_data.head(10), use_container_width=True)
                            if len(new_data) > 10:
                                st.caption(f"총 {len(new_data)}개 행 중 처음 10개만 표시됩니다.")
                        
                        # NO 컬럼이 없으면 자동 생성
                        if 'NO' not in new_data.columns:
                            if not st.session_state.df.empty and 'NO' in st.session_state.df.columns:
                                max_no = st.session_state.df['NO'].max()
                                start_no = int(max_no) + 1 if pd.notnull(max_no) else 1001
                            else:
                                start_no = 1001
                            new_data['NO'] = range(start_no, start_no + len(new_data))
                            st.info(f"ℹ️ 'NO' 컬럼이 없어 자동으로 생성했습니다. (시작 번호: {start_no})")
                        
                        # 업로드 확인
                        st.divider()
                        col_confirm1, col_confirm2 = st.columns(2)
                        with col_confirm1:
                            if st.button("✅ 데이터 업로드 실행", use_container_width=True, type="primary"):
                                # NO 중복 체크 및 병합 로직
                                if 'NO' in st.session_state.df.columns:
                                    current_nos = st.session_state.df['NO'].tolist()
                                    to_add = []
                                    duplicates = []
                                    
                                    for _, row in new_data.iterrows():
                                        row_no = row.get('NO')
                                        if pd.isna(row_no) or row_no == "":
                                            # NO가 없으면 자동 생성
                                            if not st.session_state.df.empty and 'NO' in st.session_state.df.columns:
                                                max_no = st.session_state.df['NO'].max()
                                                row_no = int(max_no) + 1 if pd.notnull(max_no) else int(datetime.datetime.now().timestamp())
                                            else:
                                                row_no = int(datetime.datetime.now().timestamp())
                                            row['NO'] = row_no
                                            to_add.append(row.to_dict())
                                        elif row_no not in current_nos:
                                            to_add.append(row.to_dict())
                                        else:
                                            duplicates.append(row_no)
                                    
                                    if duplicates:
                                        st.warning(f"⚠️ 중복된 NO {len(duplicates)}개는 건너뜁니다: {duplicates[:5]}{'...' if len(duplicates) > 5 else ''}")
                                    
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
                                        st.success(f"✅ {len(to_add)}개 항목이 성공적으로 추가되었습니다!")
                                        if duplicates:
                                            st.info(f"ℹ️ 중복 항목 {len(duplicates)}개는 제외되었습니다.")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.warning("⚠️ 추가할 새로운 데이터가 없습니다. 모든 항목이 이미 존재하거나 중복입니다.")
                                else:
                                    # 원본 데이터프레임에 NO 컬럼이 없는 경우
                                    if 'NO' not in new_data.columns:
                                        new_data['NO'] = range(1001, 1001 + len(new_data))
                                    
                                    # 날짜 컬럼 변환
                                    date_columns = ['접수일', '납기일', '도면접수일', '자재 요청일', '샘플 완료일', '출하일']
                                    for col in date_columns:
                                        if col in new_data.columns:
                                            new_data[col] = pd.to_datetime(new_data[col], errors='coerce').dt.date
                                    
                                    new_data = update_progress_status(new_data)
                                    st.session_state.df = pd.concat([new_data, st.session_state.df], ignore_index=True) if not st.session_state.df.empty else new_data
                                    save_data()
                                    st.success(f"✅ {len(new_data)}개 항목이 성공적으로 추가되었습니다!")
                                    time.sleep(2)
                                    st.rerun()
                        
                        with col_confirm2:
                            if st.button("❌ 취소", use_container_width=True):
                                st.info("업로드가 취소되었습니다.")
                                st.rerun()
                                
                    except Exception as e:
                        st.error(f"❌ 업로드 실패: {str(e)}")
                        st.exception(e)
        
        st.divider()
        st.subheader("📊 현재 데이터 통계")
        if not st.session_state.df.empty:
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            with col_stat1:
                st.metric("총 데이터 건수", f"{len(st.session_state.df)}건")
            with col_stat2:
                if '업체명' in st.session_state.df.columns:
                    unique_companies = st.session_state.df['업체명'].nunique()
                    st.metric("등록된 업체 수", f"{unique_companies}개")
            with col_stat3:
                if 'NO' in st.session_state.df.columns:
                    max_no = st.session_state.df['NO'].max()
                    st.metric("최대 NO", f"{int(max_no) if pd.notnull(max_no) else 'N/A'}")
        else:
            st.info("현재 데이터가 없습니다.")

# -----------------------------------------------------------------------------
# 앱 실행 진입점
# -----------------------------------------------------------------------------
load_data()

if 'user' not in st.session_state:
    login_screen()
else:
    main_app()