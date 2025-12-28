# 온라인 배포 가이드

## Google Sheets 연동 설정

### 1. Google Cloud Console 설정

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. "API 및 서비스" > "라이브러리"로 이동
4. 다음 API 활성화:
   - Google Sheets API
   - Google Drive API

### 2. 서비스 계정 생성

1. "API 및 서비스" > "사용자 인증 정보"로 이동
2. "사용자 인증 정보 만들기" > "서비스 계정" 선택
3. 서비스 계정 이름 입력 후 생성
4. 생성된 서비스 계정 클릭 > "키" 탭 > "키 추가" > "JSON" 선택
5. 다운로드된 JSON 파일 저장

### 3. Google Sheets 스프레드시트 생성

1. [Google Sheets](https://sheets.google.com/)에서 새 스프레드시트 생성
2. 스프레드시트 제목 설정 (예: "신성EP 샘플 관리 시스템")
3. 스프레드시트 URL에서 ID 추출:
   - URL 형식: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`
   - `SPREADSHEET_ID` 부분 복사
4. 생성한 서비스 계정 이메일을 스프레드시트에 편집자 권한으로 공유

### 4. Streamlit Cloud 배포 시 설정

1. Streamlit Cloud에 프로젝트 연결
2. "Settings" > "Secrets" 메뉴로 이동
3. 다음 형식으로 secrets 추가:

```toml
[google_sheets]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
spreadsheet_id = "your-spreadsheet-id"
```

### 5. 로컬 개발 시 설정 (선택사항)

환경 변수 설정:
```bash
export USE_GOOGLE_SHEETS=true
export GOOGLE_SHEETS_CREDENTIALS='{"type":"service_account",...}'
export GOOGLE_SHEETS_SPREADSHEET_ID="your-spreadsheet-id"
```

## 배포 후 확인사항

- 모든 브라우저에서 동일한 데이터가 표시되는지 확인
- 데이터 변경 시 즉시 반영되는지 확인
- Google Sheets에서 백업 시트가 자동 생성되는지 확인

## 백업

- Google Sheets에 자동으로 타임스탬프가 포함된 백업 시트 생성
- 로컬 파일도 백업으로 유지됨 (Google Sheets 저장 실패 시)



