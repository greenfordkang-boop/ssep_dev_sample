# 구글 시트 쓰기 권한 설정 가이드 (gspread)

## 개요
이 가이드는 Streamlit Cloud에서 구글 시트에 읽기/쓰기 권한을 설정하는 방법을 설명합니다.

## 1. Google Cloud Console 설정

### 1.1 프로젝트 생성
1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택

### 1.2 API 활성화
1. "API 및 서비스" > "라이브러리"로 이동
2. 다음 API를 활성화:
   - **Google Sheets API**
   - **Google Drive API**

### 1.3 서비스 계정 생성
1. "API 및 서비스" > "사용자 인증 정보"로 이동
2. "사용자 인증 정보 만들기" > "서비스 계정" 선택
3. 서비스 계정 이름 입력 (예: `ssep-sheets-service`)
4. "만들기" 클릭
5. 역할은 선택하지 않고 "완료" 클릭

### 1.4 서비스 계정 키 생성
1. 생성된 서비스 계정 클릭
2. "키" 탭으로 이동
3. "키 추가" > "새 키 만들기" 선택
4. 키 유형: **JSON** 선택
5. "만들기" 클릭 → JSON 파일이 다운로드됨

## 2. 구글 시트 공유 설정

1. 구글 시트 열기: https://docs.google.com/spreadsheets/d/12C5nfRZVfakXGm6tWx9vbRmM36LtsjWBnQUR_VjAz2s
2. 우측 상단 "공유" 버튼 클릭
3. 서비스 계정 이메일 주소 입력 (JSON 파일의 `client_email` 필드에 있음)
4. 권한: **편집자** 선택
5. "완료" 클릭

## 3. Streamlit Cloud Secrets 설정

### 3.1 JSON 파일 내용 확인
다운로드한 JSON 파일을 열어서 전체 내용을 복사합니다.

### 3.2 Streamlit Cloud에서 설정
1. Streamlit Cloud 대시보드 접속
2. 앱 선택 > "Settings" > "Secrets" 클릭
3. 다음 형식으로 입력 (권장):

```toml
[connections.gsheets]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...
(여기에 실제 private key 내용 전체를 붙여넣으세요)
...
-----END PRIVATE KEY-----"""
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
```

**중요**: 
- `private_key`는 **세 개의 큰따옴표(`"""`)**로 감싸서 여러 줄 문자열로 입력하세요.
- JSON 파일의 `private_key` 값을 그대로 복사하여 붙여넣으세요 (줄바꿈 포함).
- `[connections.gsheets]` 형식이 권장됩니다 (코드와 일치).
- 기존 `[gcp_service_account]` 형식도 지원됩니다 (하위 호환성).
- **"Incorrect padding" 오류가 발생하면 `private_key` 포맷을 확인하세요.**

### 3.3 JSON을 TOML로 변환하는 방법
JSON 파일의 각 필드를 TOML 형식으로 변환:
- `"type"` → `type = "..."`
- `"project_id"` → `project_id = "..."`
- 등등...

또는 온라인 변환 도구를 사용할 수 있습니다.

## 4. 앱 재배포

1. Secrets 저장 후 앱이 자동으로 재시작됩니다
2. 또는 "Reboot app" 버튼 클릭

## 5. 확인

1. 앱에서 데이터 수정
2. 구글 시트에서 변경사항 확인
3. 앱 재시작 후에도 데이터가 유지되는지 확인

## 문제 해결

### gspread 초기화 실패 / "Incorrect padding" 오류
- **`private_key` 포맷 확인**: 세 개의 큰따옴표(`"""`)로 감싸서 여러 줄 문자열로 입력했는지 확인
- JSON 파일의 `private_key` 값을 그대로 복사했는지 확인 (줄바꿈 포함)
- Secrets 설정이 올바른지 확인
- 서비스 계정 이메일이 시트에 공유되었는지 확인
- API가 활성화되었는지 확인

### 권한 오류
- 서비스 계정에 "편집자" 권한이 부여되었는지 확인
- Google Sheets API와 Drive API가 활성화되었는지 확인

### 데이터가 저장되지 않음
- gspread가 정상적으로 초기화되었는지 확인
- 시트 ID가 올바른지 확인
- 에러 메시지 확인

## 참고

- gspread가 설정되지 않으면 자동으로 CSV 방식(읽기 전용)으로 fallback됩니다
- 로컬 파일은 항상 백업으로 저장됩니다

