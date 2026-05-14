"""
구글시트 → data.json
매일 09:00 KST에 GitHub Actions가 이 스크립트를 실행해
EBIZ_MK_기획전 시트(표준화입력시트) 데이터를 받아와 data.json으로 저장합니다.
"""

import os
import json
import gspread
from google.oauth2.service_account import Credentials


HEADER_MAP = {
    "브랜드": "BRAND",
    "채널 구분": "CHANNEL",
    "구분": "CATEGORY",
    "유형": "TYPE",
    "단독 표시 여부": "EXCLUSIVE",
    "기획전명": "PROMOTION_NAME",
    "시작일": "START_DATE",
    "종료일": "END_DATE",
    "진행 상태": "STATUS",
    "노출 구좌": "SLOT",
    "보고 장표 이미지": "IMAGE_URL",
    "혜택 유형": "BENEFIT_TYPE",
    "혜택 스킴 (세부)": "BENEFIT_DETAIL",
    "목표 매출 (천원)": "TARGET_SALES_KRW_K",
    "MD 코멘트": "MD_COMMENT",
    "제출여부": "SUBMITTED",
    "제출마감일": "SUBMIT_DEADLINE",
    "남은 기간": "REMAINING",
}


def normalize(row):
    return {HEADER_MAP.get(k, k): v for k, v in row.items()}


def fetch_data():
    print("🚀 시트 데이터 가져오기 시작...")

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    service_account_info = json.loads(os.environ['GOOGLE_JSON_KEY'])
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    client = gspread.authorize(creds)

    sheet_id = os.environ['SHEET_ID']
    sheet = client.open_by_key(sheet_id).sheet1

    raw_rows = sheet.get_all_records()
    rows = [normalize(r) for r in raw_rows]
    rows = [r for r in rows if r.get("BRAND")]

    print(f"✅ {len(rows)}개 행 로드 완료")

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print("✅ data.json 저장 완료")


if __name__ == "__main__":
    fetch_data()
