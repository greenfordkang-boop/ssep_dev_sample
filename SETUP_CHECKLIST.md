# ✅ Google Sheets 연결 설정 체크리스트

## 📋 설정 완료 확인 항목

### 1. 라이브러리 설치 확인
- [ ] `pip install -r requirements.txt` 실행 완료
- [ ] `st-gsheets-connection` 라이브러리가 설치되었는지 확인
  ```bash
  pip list | grep st-gsheets-connection
  ```

### 2. Google Cloud Console 설정
- [ ] Google Cloud 프로젝트 생성 완료
- [ ] Google Sheets API 활성화 완료
- [ ] Google Drive API 활성화 완료
- [ ] 서비스 계정 생성 완료
- [ ] 서비스 계정 JSON 키 파일 다운로드 완료
- [ ] 서비스 계정 이메일 주소 확인 (예: `xxx@xxx.iam.gserviceaccount.com`)

### 3. Google Sheets 공유 설정
- [ ] Google Sheets 열기: https://docs.google.com/spreadsheets/d/1IsBdfSpLDAughGyjr2APO4_LxPWxC0Pbj0h4jTjyz5U/edit
- [ ] "공유" 버튼 클릭
- [ ] 서비스 계정 이메일 주소 입력
- [ ] 권한: **편집자** 선택
- [ ] "공유" 완료

### 4. secrets.toml 파일 설정
- [ ] `.streamlit` 폴더 생성 확인
- [ ] `.streamlit/secrets.toml` 파일 생성 확인
- [ ] 서비스 계정 JSON 키 파일의 모든 값이 올바르게 입력되었는지 확인
- [ ] `private_key`의 줄바꿈 문자(`\n`)가 올바르게 입력되었는지 확인

### 5. 앱 실행 및 테스트
- [ ] `streamlit run app.py` 또는 `run.bat` 실행
- [ ] 로그인 성공
- [ ] "📊 샘플관리 현황판" 메뉴로 이동
- [ ] "📋 접수된 샘플 요청 목록"이 표시되는지 확인
- [ ] Google Sheets의 데이터가 실시간으로 표시되는지 확인

## 🔍 문제 해결

### 오류: "Google Sheets 연결 오류"
**원인**: secrets.toml 파일이 없거나 잘못 설정됨
**해결**:
1. `.streamlit/secrets.toml` 파일이 존재하는지 확인
2. 파일 내용이 올바른지 확인
3. 서비스 계정 JSON 키 파일과 비교하여 값이 일치하는지 확인

### 오류: "권한이 없습니다"
**원인**: Google Sheets에 서비스 계정이 공유되지 않음
**해결**:
1. Google Sheets에서 "공유" 버튼 클릭
2. 서비스 계정 이메일 주소 확인
3. 서비스 계정 이메일을 "편집자" 권한으로 추가

### 데이터가 표시되지 않음
**원인**: Google Sheets의 첫 번째 행이 헤더가 아니거나 데이터 형식이 맞지 않음
**해결**:
1. Google Sheets의 첫 번째 행이 컬럼명(헤더)인지 확인
2. 컬럼명이 한글로 되어 있는지 확인 (업체명, 품명, 납기일, 진행상태 등)
3. 데이터가 두 번째 행부터 시작하는지 확인

### "최신 데이터 로드 실패" 경고
**원인**: Google Sheets 연결 실패 또는 데이터 형식 문제
**해결**:
1. 인터넷 연결 확인
2. Google Sheets가 공개되어 있거나 서비스 계정이 공유되어 있는지 확인
3. 터미널의 오류 메시지 확인

## 📝 secrets.toml 파일 예시

```toml
[connections.gsheets]
type = "service_account"
project_id = "your-project-id-123456"
private_key_id = "abc123def456..."
private_key = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...\n-----END PRIVATE KEY-----\n"
client_email = "ssep-service@your-project.iam.gserviceaccount.com"
client_id = "123456789012345678901"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/ssep-service%40your-project.iam.gserviceaccount.com"
```

## ✅ 최종 확인

모든 체크리스트를 완료한 후:
1. 앱을 실행합니다
2. 로그인합니다
3. "📊 샘플관리 현황판" 메뉴로 이동합니다
4. 상단에 "📋 접수된 샘플 요청 목록"이 표시되는지 확인합니다
5. Google Sheets의 데이터가 실시간으로 표시되는지 확인합니다

**성공 시**: 카드 형태로 업체명, 품목명, 납기일, 진행상황이 표시됩니다! 🎉

