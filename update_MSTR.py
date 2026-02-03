import json
import time
import re
import os
import smtplib  # 이메일 발송용 추가
from email.mime.text import MIMEText  # 이메일 본문 구성용 추가
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 1. 시크릿 정보 로드 (사장님이 정의하신 이름 그대로)
firebase_key = os.environ.get('FIREBASE_KEY')
GMAIL_USER = os.environ.get('MY_GMAIL_USER')
GMAIL_PW = os.environ.get('MY_GMAIL_PW')
is_github = firebase_key is not None

# 2. Firebase 초기화
try:
    if not firebase_admin._apps:
        if is_github:
            key_dict = json.loads(firebase_key)
            cred = credentials.Certificate(key_dict)
        else:
            cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {'databaseURL': 'https://strategy-mnav-default-rtdb.firebaseio.com/'})
except Exception as e:
    print(f"Firebase 초기화 실패: {e}"); exit()

# [신규] 이메일 발송 함수
def send_email_alert(subject, body):
    """지메일을 사용하여 카카오 메일로 알림 전송"""
    if not GMAIL_USER or not GMAIL_PW:
        print("🚨 이메일 시크릿 설정이 누락되어 메일을 보낼 수 없습니다.")
        return

    receiver = "stinlove@kakao.com"
    msg = MIMEText(body)
    msg['Subject'] = f"🚨 [스트래티지 대시보드 문제발생] {subject}"
    msg['From'] = GMAIL_USER
    msg['To'] = receiver

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PW)
            server.send_message(msg)
            print(f"📧 알림 메일 발송 완료: {receiver}")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

def clean_num(text):
    if not text: return 0
    text = text.split('\n')[0]
    cleaned = re.sub(r'[^\d.]', '', str(text))
    try:
        return float(cleaned) if '.' in cleaned else int(cleaned)
    except: return 0

def run_engine():
    url = "https://www.strategy.com"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        print(f"[{datetime.now()}] 데이터 수집 시작...")
        driver.get(url)
        time.sleep(15) 

        elements = driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, p, span, div")
        all_content = [el.text.strip() for el in elements if el.text.strip()]

        def get_by_key(key_num):
            try:
                idx = int(key_num) - 1
                return all_content[idx]
            except: return ""

        extracted = {
            "mstrPrice":       clean_num(get_by_key("19")),
            "marketCap":       clean_num(get_by_key("40")),
            "enterpriseValue": clean_num(get_by_key("46")),
            "btcReserve":      clean_num(get_by_key("83")),
            "btcPrice":        clean_num(get_by_key("89")),
            "btcQuantity":     clean_num(get_by_key("95")),
            "usdReserve":      clean_num(get_by_key("107")),
            "debt":            clean_num(get_by_key("127")),
            "pref":            clean_num(get_by_key("137"))
        }

        valid_values = [v for v in extracted.values() if v > 0]
        valid_count = len(valid_values)

        # 데이터 부족 시 메일 발송
        if valid_count < 9:
            err_msg = f"유효 데이터 부족 ({valid_count}/9). 수집된 데이터: {json.dumps(extracted)}"
            print(f"🚨 {err_msg}")
            send_email_alert("데이터 수집 오류 발생", err_msg)
            return

        # mNAV 계산
        extracted["mnav"] = round(extracted["enterpriseValue"] / extracted["btcReserve"], 4) if extracted["btcReserve"] != 0 else 0
        extracted["updatetime"] = datetime.utcnow().strftime("%b %d, %Y, %H:%M UTC")

        # Firebase 전송
        db.reference('/params').update(extracted)
        print("\n🚀 Firebase 'params' 업데이트 완료!")

    except Exception as e:
        error_info = f"런타임 오류 발생: {str(e)}"
        print(f"❌ {error_info}")
        send_email_alert("엔진 작동 중단 알림", error_info)
    finally:
        driver.quit()

if __name__ == "__main__":
    run_engine()
