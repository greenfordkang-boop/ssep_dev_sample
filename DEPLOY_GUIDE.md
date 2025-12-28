# 🚀 배포 가이드

## 방법 1: Streamlit Community Cloud (추천 - 무료, 간단)

### 1단계: GitHub에 코드 업로드

1. **GitHub 계정 생성** (없는 경우)
   - https://github.com/ 접속
   - 새 계정 생성

2. **새 저장소(Repository) 생성**
   - GitHub에서 "New repository" 클릭
   - 저장소 이름 입력 (예: `ssep-sample-system`)
   - Public 또는 Private 선택
   - "Create repository" 클릭

3. **로컬 파일을 GitHub에 업로드**
   ```bash
   # Git 초기화 (아직 안 했다면)
   git init
   
   # 파일 추가
   git add app.py requirements.txt README_DEPLOYMENT.md
   
   # 커밋
   git commit -m "Initial commit"
   
   # GitHub 저장소 연결 (YOUR_USERNAME과 YOUR_REPO_NAME을 실제 값으로 변경)
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   
   # 업로드
   git branch -M main
   git push -u origin main
   ```

   또는 GitHub 웹사이트에서 직접 파일을 업로드할 수도 있습니다.

### 2단계: Streamlit Cloud에 배포

1. **Streamlit Cloud 접속**
   - https://share.streamlit.io/ 접속
   - "Sign in with GitHub" 클릭하여 GitHub 계정으로 로그인

2. **앱 배포**
   - "New app" 클릭
   - Repository: 방금 만든 GitHub 저장소 선택
   - Branch: `main` 선택
   - Main file path: `app.py` 입력
   - "Deploy!" 클릭

3. **배포 완료**
   - 몇 분 후 앱이 배포됩니다
   - 고유한 URL이 생성됩니다 (예: `https://your-app.streamlit.app`)

### 3단계: Google Sheets 연동 (선택사항)

Google Sheets를 사용하려면:

1. **Google Cloud Console 설정**
   - https://console.cloud.google.com/ 접속
   - 새 프로젝트 생성
   - "API 및 서비스" > "라이브러리"에서 다음 API 활성화:
     - Google Sheets API
     - Google Drive API

2. **서비스 계정 생성**
   - "API 및 서비스" > "사용자 인증 정보" > "사용자 인증 정보 만들기" > "서비스 계정"
   - 서비스 계정 이름 입력 후 생성
   - 생성된 계정 클릭 > "키" 탭 > "키 추가" > "JSON" 선택
   - JSON 파일 다운로드

3. **Google Sheets 스프레드시트 생성**
   - https://sheets.google.com/ 에서 새 스프레드시트 생성
   - 스프레드시트 URL에서 ID 추출:
     ```
     https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
     ```
   - 서비스 계정 이메일(JSON 파일의 `client_email`)을 스프레드시트에 편집자 권한으로 공유

4. **Streamlit Cloud Secrets 설정**
   - Streamlit Cloud 대시보드에서 앱 선택
   - "Settings" > "Secrets" 클릭
   - 다음 형식으로 입력:
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
   - JSON 파일의 내용을 복사하여 위 형식에 맞게 입력
   - "Save" 클릭

5. **앱 재배포**
   - Streamlit Cloud에서 "Reboot app" 클릭
   - Google Sheets 연동이 활성화됩니다

---

## 방법 2: Docker를 사용한 자체 서버 배포

### Dockerfile 생성

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### 배포 명령어

```bash
# Docker 이미지 빌드
docker build -t ssep-app .

# 컨테이너 실행
docker run -p 8501:8501 ssep-app
```

---

## 방법 3: 로컬 서버에서 직접 실행

### Windows (PowerShell)

```powershell
# 가상환경 생성 (선택사항)
python -m venv venv
.\venv\Scripts\Activate.ps1

# 라이브러리 설치
pip install -r requirements.txt

# 앱 실행
streamlit run app.py
```

### Linux/Mac

```bash
# 가상환경 생성 (선택사항)
python3 -m venv venv
source venv/bin/activate

# 라이브러리 설치
pip install -r requirements.txt

# 앱 실행
streamlit run app.py
```

---

## 배포 후 확인사항

✅ 모든 브라우저에서 동일한 URL로 접속 가능  
✅ 데이터 변경 시 즉시 반영  
✅ Google Sheets 사용 시 자동 백업 확인  
✅ 로그인 기능 정상 작동  

---

## 문제 해결

### 앱이 실행되지 않는 경우
- `requirements.txt`에 모든 라이브러리가 포함되어 있는지 확인
- Streamlit Cloud 로그 확인 (Settings > Logs)

### Google Sheets 연동 오류
- 서비스 계정이 스프레드시트에 공유되었는지 확인
- Secrets 설정이 올바른지 확인
- API가 활성화되었는지 확인

### 데이터가 표시되지 않는 경우
- Google Sheets 설정이 올바른지 확인
- 로컬 파일 모드로 전환하여 테스트

---

## 보안 권장사항

1. **비밀번호 변경**: 기본 비밀번호(`1234`)를 강력한 비밀번호로 변경
2. **환경 변수 사용**: 민감한 정보는 Secrets에 저장
3. **HTTPS 사용**: Streamlit Cloud는 자동으로 HTTPS 제공
4. **접근 제어**: 필요시 추가 인증 레이어 구현

---

## 추가 리소스

- [Streamlit Cloud 문서](https://docs.streamlit.io/streamlit-community-cloud)
- [Google Sheets API 문서](https://developers.google.com/sheets/api)
- [Streamlit 공식 문서](https://docs.streamlit.io/)




