import json
import time
import re
import os
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 1. Firebase 설정 (어제와 동일)
firebase_key = os.environ.get('FIREBASE_KEY')
is_github = firebase_key is not None

try:
    if is_github:
        key_dict = json.loads(firebase_key)
        cred = credentials.Certificate(key_dict)
    else:
        cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {'databaseURL': 'https://strategy-mnav-default-rtdb.firebaseio.com/'})
except Exception as e:
    print(f"Firebase 초기화 실패: {e}"); exit()

def clean_num(text):
    """문자열에서 숫자와 소수점만 남기고 제거 (₿, $, %, 콤마 등 무시)"""
    if not text: return 0
    # 줄바꿈이 있는 경우 첫 줄의 숫자만 가져오도록 처리
    text = text.split('\n')[0]
    cleaned = re.sub(r'[^\d.]', '', str(text))
    try:
        return float(cleaned) if '.' in cleaned else int(cleaned)
    except: return 0

def send_telegram_alert(message):
    """텔레그램 알람 형식만 유지"""
    print(f"\n📢 [텔레그램 푸시 알람]: {message}")

def run_engine():
    url = "https://www.strategy.com"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        print(f"[{datetime.now()}] 데이터 수집 시작...")
        driver.get(url)
        time.sleep(15) 

        elements = driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, p, span, div")
        all_content = [el.text.strip() for el in elements if el.text.strip()]

        # ---------------------------------------------------------
        # 🎯 [이사님의 핵심 로직] 
        # 제이슨 번호(Key)를 넣으면 해당 텍스트를 찾아 숫자로 변환하는 함수
        # ---------------------------------------------------------
        def get_by_key(key_num):
            try:
                # 사장님이 보신 번호 "19"는 리스트 인덱스 18번입니다.
                idx = int(key_num) - 1
                return all_content[idx]
            except:
                return ""

        # 사장님이 지정하신 번호 그대로 매칭
        extracted = {
            "mstrPrice":       clean_num(get_by_key("19")),   # MSTR 가격
            "marketCap":       clean_num(get_by_key("40")),   # 마켓캡
            "enterpriseValue": clean_num(get_by_key("46")),   # EV
            "btcReserve":      clean_num(get_by_key("83")),   # BTC 리저브
            "btcPrice":        clean_num(get_by_key("89")),   # BTC 프라이스
            "btcQuantity":     clean_num(get_by_key("95")),   # BTC Qty
            "usdReserve":      clean_num(get_by_key("107")),  # USD 리저브
            "debt":            clean_num(get_by_key("127")),  # 부채
            "pref":            clean_num(get_by_key("137"))   # 우선주
        }

        # ---------------------------------------------------------
        # 검증 및 업데이트 (9개 인자 체크)
        valid_values = [v for v in extracted.values() if v > 0]
        valid_count = len(valid_values)

        # 로컬 확인용 파일 생성
        if not is_github:
            with open('strategy_check.json', 'w', encoding='utf-8') as f:
                json.dump(extracted, f, ensure_ascii=False, indent=4)
            print(f"✅ 검증용 JSON 생성됨 (유효데이터: {valid_count}/9)")

        if valid_count < 9:
            send_telegram_alert(f"유효 데이터 부족({valid_count}개). 업데이트 중단.")
            return

        # mNAV 계산 및 시간 추가
        extracted["mnav"] = round(extracted["enterpriseValue"] / extracted["btcReserve"], 4) if extracted["btcReserve"] != 0 else 0
        extracted["updatetime"] = datetime.utcnow().strftime("%b %d, %Y, %H:%M UTC")

        # Firebase 전송
        db.reference('/params').update(extracted)
        print("\n🚀 Firebase 'params' 업데이트 완료!")

    except Exception as e:
        send_telegram_alert(f"오류 발생: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_engine()