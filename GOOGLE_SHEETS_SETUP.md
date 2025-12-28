# Google Sheets 연결 설정 가이드

## 📋 개요
이 앱은 `st-gsheets-connection` 라이브러리를 사용하여 Google Sheets와 실시간으로 연결됩니다.

## 🔧 설정 단계

### 1. Google Cloud Console 설정

#### 1.1 프로젝트 생성
1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. 프로젝트 이름: "신성EP 샘플 관리" (또는 원하는 이름)

#### 1.2 Google Sheets API 활성화
1. "API 및 서비스" > "라이브러리" 메뉴로 이동
2. "Google Sheets API" 검색 후 활성화
3. "Google Drive API"도 검색 후 활성화 (필수)

#### 1.3 서비스 계정 생성
1. "API 및 서비스" > "사용자 인증 정보" 메뉴로 이동
2. "사용자 인증 정보 만들기" > "서비스 계정" 선택
3. 서비스 계정 정보 입력:
   - 이름: "ssep-sheets-service"
   - 설명: "신성EP 샘플 관리 시스템용"
4. "만들기" 클릭

#### 1.4 서비스 계정 키 생성
1. 생성된 서비스 계정을 클릭
2. "키" 탭으로 이동
3. "키 추가" > "새 키 만들기" 선택
4. 키 유형: **JSON** 선택
5. "만들기" 클릭 → JSON 파일이 자동으로 다운로드됨
6. **중요**: 이 JSON 파일을 안전하게 보관하세요!

#### 1.5 서비스 계정 이메일 확인
- 서비스 계정의 이메일 주소를 복사 (예: `ssep-sheets-service@your-project.iam.gserviceaccount.com`)
- 이 이메일 주소는 다음 단계에서 사용됩니다

### 2. Google Sheets 공유 설정

#### 2.1 스프레드시트 열기
- 연결할 스프레드시트 URL:
  ```
  https://docs.google.com/spreadsheets/d/1IsBdfSpLDAughGyjr2APO4_LxPWxC0Pbj0h4jTjyz5U/edit
  ```

#### 2.2 서비스 계정에 공유
1. 스프레드시트에서 "공유" 버튼 클릭
2. 서비스 계정 이메일 주소 입력 (1.5에서 복사한 이메일)
3. 권한: **편집자** 선택
4. "알림 보내기" 체크 해제 (선택사항)
5. "공유" 클릭

### 3. secrets.toml 파일 설정

#### 3.1 파일 생성
1. 프로젝트 루트에 `.streamlit` 폴더 생성 (없는 경우)
2. `.streamlit/secrets.toml` 파일 생성

#### 3.2 JSON 키 파일 내용 복사
다운로드한 서비스 계정 JSON 파일을 열고, 다음 형식으로 `secrets.toml`에 입력:

```toml
[connections.gsheets]
type = "service_account"
project_id = "your-project-id-here"
private_key_id = "your-private-key-id-here"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n"
client_email = "ssep-sheets-service@your-project.iam.gserviceaccount.com"
client_id = "your-client-id-here"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
```

#### 3.3 JSON 파일에서 값 추출 방법
다운로드한 JSON 파일의 구조:
```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "...",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "..."
}
```

각 값을 그대로 `secrets.toml`에 복사하되, `private_key`의 경우 줄바꿈 문자(`\n`)를 그대로 유지해야 합니다.

### 4. 라이브러리 설치

터미널에서 다음 명령어 실행:
```bash
pip install -r requirements.txt
```

또는 직접 설치:
```bash
pip install st-gsheets-connection
```

### 5. 앱 실행 및 확인

1. 앱 실행:
   ```bash
   streamlit run app.py
   ```
   또는
   ```bash
   run.bat
   ```

2. 로그인 후 "📊 샘플관리 현황판" 메뉴로 이동
3. 상단에 "📋 접수된 샘플 요청 목록"이 표시되는지 확인
4. Google Sheets의 데이터가 실시간으로 표시되는지 확인

## ⚠️ 주의사항

### 보안
- **절대 `secrets.toml` 파일을 Git에 커밋하지 마세요!**
- `.gitignore`에 `.streamlit/secrets.toml`이 포함되어 있는지 확인하세요
- 서비스 계정 JSON 파일도 절대 공유하지 마세요

### 권한 문제 해결
만약 "권한이 없습니다" 오류가 발생하면:
1. Google Sheets에서 서비스 계정 이메일이 공유되어 있는지 확인
2. 서비스 계정의 권한이 "편집자"인지 확인
3. Google Sheets API와 Google Drive API가 활성화되어 있는지 확인

### 데이터 형식
- Google Sheets의 첫 번째 행은 헤더(컬럼명)여야 합니다
- 컬럼명은 한글로 되어 있어야 합니다 (업체명, 품명, 납기일, 진행상태 등)
- 데이터는 두 번째 행부터 시작합니다

## 🔍 문제 해결

### 오류: "Google Sheets 연결 오류"
- `secrets.toml` 파일이 올바른 위치에 있는지 확인 (`.streamlit/secrets.toml`)
- JSON 키 파일의 값이 올바르게 복사되었는지 확인
- `private_key`의 줄바꿈 문자(`\n`)가 올바르게 입력되었는지 확인

### 오류: "권한이 없습니다"
- Google Sheets에서 서비스 계정 이메일을 공유했는지 확인
- 서비스 계정의 권한이 "편집자"인지 확인

### 데이터가 표시되지 않음
- Google Sheets에 데이터가 있는지 확인
- 첫 번째 행이 헤더(컬럼명)인지 확인
- 앱을 새로고침하거나 재시작

## 📞 추가 도움말

- [st-gsheets-connection 공식 문서](https://github.com/streamlit/gsheets-connection)
- [Google Sheets API 문서](https://developers.google.com/sheets/api)
- [Streamlit Secrets 관리](https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management)


