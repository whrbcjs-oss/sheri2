"""Construction-company real-capital review, statement import and reports."""
from __future__ import annotations

from html import escape
from io import BytesIO, StringIO
from pathlib import Path
import csv
import math
import re
import sys
import unicodedata

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


ITEM_COLUMNS = ["구분", "계정과목", "원천금액", "차감액", "인정조정액", "판정", "근거·비고", "출처"]
LICENSE_COLUMNS = ["면허명·업종", "요구자본금", "중복·겸업 조정액", "적용연도", "근거·비고"]
TRIAL_COLUMNS = ["계정과목", "차변잔액", "대변잔액", "구분", "분류", "특수처리", "순금액", "근거·비고", "출처"]
TRIAL_REVIEW_COLUMNS = ["계정과목", "차변잔액", "대변잔액", "구분", "분류", "특수처리", "순금액", "지침 매핑", "근거·비고", "검토상태", "출처"]
TRIAL_GROUPS = ["자산", "부채", "제외", "미분류"]
TRIAL_CLASSES = ["인정", "일반", "부실", "겸업", "검토 필요", ""]
SPECIAL_OPTIONS = ["현금", "예금", "유가증권", "공사미수금", "받을채권", "대여금", "선급금", "보증금", "재고자산", "유형자산", "무형자산", "자산 차감", "퇴직급여충당", "충당부채", "겸업안분", ""]
DECISION_OPTIONS = ["전액 인정", "일부 인정", "전액 차감", "검토 필요"]
CATEGORY_OPTIONS = ["자본", "차감검토", "인정조정"]

CAPITAL_ALIASES = {
    "자본총계": ["자본총계", "자기자본"],
    "납입자본금": ["납입자본금"],
    "자본금": ["자본금"],
    "자본잉여금": ["자본잉여금"],
    "이익잉여금": ["이익잉여금", "결손금"],
    "기타포괄손익누계액": ["기타포괄손익누계액"],
}
REVIEW_ALIASES = {
    "미수금": ["미수금", "공사미수금"],
    "관계회사대여금": ["관계회사대여금"],
    "주임종단기채권": ["주임종단기채권", "주임종단기대여금"],
    "단기대여금": ["단기대여금"],
    "장기대여금": ["장기대여금"],
    "미수수익": ["미수수익"],
    "선급금": ["선급금"],
    "선급비용": ["선급비용"],
    "미완성공사": ["미완성공사", "미완성공사(분양)"],
    "임목": ["임목"],
    "토지": ["토지"],
    "건물": ["건물"],
    "개발비": ["개발비"],
    "소프트웨어": ["소프트웨어"],
    "임차보증금": ["임차보증금"],
    "회원권": ["회원권"],
}

DEFAULT_ACCOUNT_MAP = {
    "현금": ("자산", "인정", "현금"), "보통예금": ("자산", "인정", "예금"), "제예금": ("자산", "인정", "예금"),
    "당좌예금": ("자산", "인정", "예금"), "정기예금": ("자산", "인정", "예금"),
    "정기적금": ("자산", "인정", "예금"), "단기매매증권": ("자산", "부실", ""), "유가증권": ("자산", "검토 필요", "유가증권"),
    "공사미수금": ("자산", "인정", "공사미수금"), "받을어음": ("자산", "검토 필요", ""),
    "대손충당금": ("자산", "인정", "자산 차감"), "미수금": ("자산", "검토 필요", ""),
    "선급금": ("자산", "검토 필요", ""), "선급비용": ("자산", "인정", ""),
    "미완성공사(도급)": ("자산", "검토 필요", "재고자산"),
    "가지급금": ("자산", "부실", ""), "단기대여금": ("자산", "검토 필요", "대여금"), "관계회사대여금": ("자산", "검토 필요", "대여금"), "주임종단기채권": ("자산", "검토 필요", "대여금"), "미수수익": ("자산", "검토 필요", "받을채권"), "전도금": ("자산", "검토 필요", ""),
    "장기대여금": ("자산", "부실", ""), "부가세대급금": ("자산", "검토 필요", ""),
    "토지": ("자산", "검토 필요", ""), "건물": ("자산", "검토 필요", ""),
    "건물감가상각누계액": ("자산", "인정", "자산 차감"), "구축물": ("자산", "인정", ""),
    "기계장치": ("자산", "인정", ""), "시설장치": ("자산", "검토 필요", "유형자산"), "기계장치감가상각누계액": ("자산", "인정", "자산 차감"),
    "차량운반구": ("자산", "인정", ""), "차량운반구감가상각누계액": ("자산", "인정", "자산 차감"),
    "비품": ("자산", "인정", ""), "공기구비품": ("자산", "검토 필요", "유형자산"), "비품감가상각누계액": ("자산", "인정", "자산 차감"),
    "공제조합출자금": ("자산", "인정", ""), "임차보증금": ("자산", "검토 필요", "보증금"), "기타보증금": ("자산", "검토 필요", "보증금"),
    "특허권": ("자산", "검토 필요", ""), "소프트웨어": ("자산", "검토 필요", ""),
    "개발비": ("자산", "부실", ""), "이연법인세자산": ("자산", "부실", ""),
    "장기투자증권": ("자산", "부실", ""), "외상매입금": ("부채", "일반", ""),
    "미지급금": ("부채", "일반", ""), "미지급비용": ("부채", "일반", ""),
    "미지급세금": ("부채", "일반", ""), "미지급법인세": ("부채", "일반", ""),
    "예수금": ("부채", "일반", ""), "부가세예수금": ("부채", "일반", ""),
    "선수금": ("부채", "일반", ""), "단기차입금": ("부채", "일반", ""),
    "유동성장기부채": ("부채", "일반", ""), "장기차입금": ("부채", "일반", ""),
    "퇴직급여충당부채": ("부채", "일반", "퇴직급여충당"), "퇴직급여충당금": ("부채", "일반", "퇴직급여충당"),
    "하자보수충당부채": ("부채", "일반", ""), "공사손실충당부채": ("부채", "일반", ""),
    "자본금": ("제외", "", ""), "자본잉여금": ("제외", "", ""),
    "이익잉여금": ("제외", "", ""), "미처분이익잉여금": ("제외", "", ""),
}

GUIDELINE_NAME = "건설업체 기업진단지침(사용자 제공본)"
GUIDELINE_STATUS = "사용자 제공본 · 시행일/고시번호 미확인"
GUIDELINE_RULES = [
    {"code":"cash_limit","article":"제14조","title":"현금 1% 한도","aliases":["현금","전도금","현금성자산"],"recommendation":"자동계산","auto_kind":"cash","condition":"현금실사 인정액 중 재무제표 자본총계 1% 초과액은 부실자산","evidence":"현금실사표, 현금출납장","summary":"예금을 제외한 현금은 확인액만 인정하고 자본총계의 1% 초과액을 부실자산으로 본다.","priority":10},
    {"code":"deposit_average","article":"제15조","title":"예금 평균잔액 평가","aliases":["보통예금","당좌예금","정기예금","정기적금","증권예탁금","예금"],"recommendation":"조건부 인정","auto_kind":"deposit","condition":"진단기준일 현재잔액과 기준일 포함 30일 평균잔액 중 작은 금액 인정","evidence":"예금잔액증명서, 60일 은행거래실적증명, 금융거래확인서","summary":"평균잔액 초과분은 불인정하고 허위·일시조달 예금은 부실, 사용제한 예금은 겸업자산으로 본다.","priority":20},
    {"code":"restricted_deposit","article":"제15조제4항","title":"사용제한 예금","aliases":["질권설정예금","사용제한예금","장기금융상품"],"recommendation":"겸업 후보","auto_kind":"review","condition":"질권 설정 등 사용·인출 제한 여부 확인","evidence":"금융거래확인서, 질권설정계약서","summary":"사용 또는 인출이 제한된 예금과 직접 관련 차입금을 각각 겸업자산·겸업부채로 처리한다.","priority":15},
    {"code":"securities","article":"제16조","title":"유가증권 평가","aliases":["단기매매증권","매도가능증권","만기보유증권","투자주식","유가증권","출자금"],"recommendation":"겸업 후보","auto_kind":"review","condition":"공제조합출자금·특수목적법인 지분·잔고증명 유가증권의 예외 및 사용제한 확인","evidence":"잔고증명서, 계약서, 출자확인서, 금융자료","summary":"예외에 해당하지 않는 유가증권은 겸업자산이며 예외자산은 취득원가 또는 시가로 평가한다.","priority":30},
    {"code":"receivables","article":"제17조","title":"매출채권·미수금 평가","aliases":["공사미수금","분양미수금","외상매출금","받을어음","미수금","미수수익","장기성매출채권"],"recommendation":"부실 후보","auto_kind":"receivable","condition":"사업관련성, 실재성, 발생일 2년 경과, 공공기관·소송·담보 예외 확인","evidence":"계약서, 세금계산서, 거래처원장, 금융 회수내역, 채권연령표, 담보자료","summary":"대손충당금을 차감하고 원칙적으로 2년 이상 경과 받을채권을 부실자산으로 본다.","priority":40},
    {"code":"inventory","article":"제18조","title":"재고자산 평가","aliases":["원재료","재료","재고자산","미성공사","완성주택","완성상가","수목","용지"],"recommendation":"부실 후보","auto_kind":"review","condition":"취득 후 1년 이내, 진단대상사업 보유목적·현장 관련성 및 시가 확인","evidence":"거래명세서, 금융자료, 현장일지, 실사자료, 공사원가명세서","summary":"원자재 등은 원칙적으로 부실이나 1년 이내 사업관련 보유가 입증되면 인정하고 무관 재고는 겸업자산으로 본다.","priority":50},
    {"code":"related_loan","article":"제19조","title":"가지급금·대여금","aliases":["가지급금","단기대여금","장기대여금","관계회사대여금","관계사대여금","주임종단기채권","주임종대여금"],"recommendation":"부실/겸업 후보","auto_kind":"loan","condition":"특수관계자이면 부실, 비특수관계자이면 겸업, 종업원 주택·우리사주 예외 확인","evidence":"거래처원장, 특수관계자명세, 대여계약서, 금융자료","summary":"상대방과 대여목적에 따라 부실·겸업·예외 인정으로 구분한다.","priority":35},
    {"code":"prepayments","article":"제20조","title":"선급금 평가","aliases":["선급금","선급비용","선납세금","선급공사원가"],"recommendation":"부실 후보","auto_kind":"review","condition":"계약 규정, 금융 지급, 계약이행·진행상황 및 열거된 인정사유 확인","evidence":"계약서, 금융자료, 기성정산내역, 계약 진행자료","summary":"원칙적 부실 후보이나 건설사업 관련 계약과 지급·진행이 확인되는 열거 항목은 실질자산으로 인정한다.","priority":45},
    {"code":"lease_deposit","article":"제21조","title":"임차·기타 보증금","aliases":["임차보증금","전세보증금","리스보증금","보증금","공탁금"],"recommendation":"부실/겸업 후보","auto_kind":"review","condition":"실재성, 부동산 여부, 사업장 인접성, 임직원주택, 시가초과, 사업 직접제공 여부 확인","evidence":"임대차계약서, 금융자료, 확정일자, 임대인 세무자료, 시가자료, 보관증","summary":"사실과 다르거나 시가초과 등은 부실, 사업에 직접 제공되지 않으면 겸업자산으로 본다.","priority":55},
    {"code":"other_investments","article":"제22조","title":"기타 투자자산","aliases":["장기투자증권","투자자산","기타비유동자산","회원권"],"recommendation":"겸업 후보","auto_kind":"review","condition":"지침의 별도 인정규정 존재 여부 확인","evidence":"계정명세서, 계약서, 사업관련성 입증자료","summary":"별도로 정하지 않은 투자자산과 기타비유동자산은 겸업자산으로 본다.","priority":60},
    {"code":"tangible_assets","article":"제23조","title":"유형자산 평가","aliases":["토지","건물","구축물","기계장치","차량운반구","비품","건설중인자산"],"recommendation":"조건부 인정","auto_kind":"tangible","condition":"법적·실질적 소유권, 사업관련성, 임대·운휴, 일부 임대면적 및 감가상각 적정성 확인","evidence":"등기부등본, 등록원부, 취득계약서, 감가상각명세서, 임대현황, 면적자료","summary":"소유권 없는 자산은 부실, 사업무관 임대·운휴분은 겸업이며 일부 임대는 면적비율로 계산한다.","priority":70},
    {"code":"intangibles","article":"제24조","title":"무형자산 평가","aliases":["영업권","개발비","소프트웨어","특허권","상표권","산업재산권","사용수익기부자산","무형자산"],"recommendation":"부실 후보","auto_kind":"intangible","condition":"기부채납 사용수익권·산업재산권·부동산물권 예외 및 상각액 확인","evidence":"취득계약서, 인허가기관 확인서, 기부채납계약, 상각명세서","summary":"무형자산은 원칙적으로 부실이며 직접 관련된 열거 예외만 상각 후 인정한다.","priority":25},
    {"code":"offbook_debt","article":"제25조","title":"부외부채 확인","aliases":["차입금","미지급금","미지급비용","미지급세금","미지급법인세","예수금"],"recommendation":"부외부채 검토","auto_kind":"liability","condition":"금융기관 조회, 은행거래 지급내역, 세무신고서와 장부 부채 비교","evidence":"금융거래확인서, 신용정보조회서, 세무신고서, 지급내역","summary":"장부에 누락된 금융·세무·비용 관련 부채를 확인하여 실질부채에 가산한다.","priority":80},
    {"code":"provisions","article":"제25조제3항","title":"충당부채 평가","aliases":["퇴직급여충당부채","하자보수충당부채","공사손실충당부채","보증충당부채"],"recommendation":"조건부 인정","auto_kind":"liability","condition":"기업회계기준에 따른 적정 계상 및 부족분 확인","evidence":"퇴직급여추계액, 충당부채명세서, 공사손실 검토자료","summary":"장부 충당부채와 적정 추계액을 비교하여 누락 부족분을 실질부채에 가산한다.","priority":75},
    {"code":"capital_adjustment","article":"제26조","title":"자본 평가","aliases":["자본금","자본잉여금","이익잉여금","미처분이익잉여금"],"recommendation":"직접 차감 검토","auto_kind":"capital","condition":"등기자본금 및 적법한 세무신고 없는 자본 증액 여부 확인","evidence":"법인등기사항증명서, 세무신고서, 이익잉여금처분계산서","summary":"납입자본금은 등기자본금으로 하고 부적법하게 증액한 이익잉여금 등은 실질자본에서 직접 차감한다.","priority":90},
    {"code":"concurrent_allocation","article":"제28조","title":"겸업자본 안분","aliases":["공통자산","공통부채","겸업자산","겸업부채"],"recommendation":"겸업 안분","auto_kind":"allocation","condition":"실지귀속 우선, 불분명한 공통항목은 수입금액비율, 불가능하면 면적·종업원수 등 합리적 비율","evidence":"사업별 수입금액, 구분회계자료, 사용면적, 종업원 현황","summary":"겸업자산·부채의 직접 귀속 후 공통항목을 정해진 순서로 안분한다.","priority":100},
]


def norm(value):
    # Some Korean accounting workbooks visually distribute account names by
    # inserting ordinary spaces, zero-width characters or HANGUL FILLER code
    # points.  Compare only normalized letters and numbers so those display
    # characters cannot prevent a registered guideline alias from matching.
    text=unicodedata.normalize("NFKC","" if value is None else str(value)).lower()
    return "".join(ch for ch in text if ch.isalnum() and "FILLER" not in unicodedata.name(ch,""))


def number(value):
    if value in (None, "", "-") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value))) if math.isfinite(float(value)) else None
    text = str(value).strip().replace(",", "").replace("원", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return int(round(float(text)))
    except (TypeError, ValueError):
        return None


def _matrixes(name, content):
    lower = str(name).lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        return [("CSV", list(csv.reader(StringIO(text))))]
    if lower.endswith(".xls"):
        try:
            import xlrd
        except ImportError:
            wheel = Path(__file__).resolve().parent / "vendor" / "xlrd-2.0.2-py2.py3-none-any.whl"
            if wheel.is_file() and str(wheel) not in sys.path:
                sys.path.insert(0, str(wheel))
            import xlrd
        book = xlrd.open_workbook(file_contents=content, on_demand=True)
        return [(book.sheet_by_index(i).name,
                 [[cell.value for cell in book.sheet_by_index(i).row(r)] for r in range(book.sheet_by_index(i).nrows)])
                for i in range(book.nsheets)]
    if not lower.endswith(".xlsx"):
        raise ValueError("XLS, XLSX 또는 CSV 재무자료만 업로드할 수 있습니다.")
    book = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)
    return [(ws.title, [list(row) for row in ws.iter_rows(values_only=True)]) for ws in book]


def _right_amount(matrix, row_index, column):
    row = matrix[row_index]
    candidates = []
    for value_column in range(column + 1, len(row)):
        value = number(row[value_column])
        if value is None:
            continue
        header = norm(" ".join(str(matrix[up][value_column] or "") for up in range(max(0, row_index - 8), row_index) if value_column < len(matrix[up])))
        score = 0
        if any(word in header for word in ["당기", "기말", "현재"]):score += 60
        if "잔액" in header:score += 35
        if "금액" in header:score += 10
        if any(word in header for word in ["전기", "기초"]):score -= 60
        candidates.append((score, -value_column, value))
    if not candidates:return None
    # When no header is recognizable, retain the first amount to the right.
    if max(score for score, _, _ in candidates) == 0:return max(candidates, key=lambda item:item[1])[2]
    return max(candidates, key=lambda item:(item[0], abs(item[2]), item[1]))[2]


def extract_statement(name, content):
    """Extract exact account labels while leaving legal recognition to the reviewer."""
    found = {}
    alias_map = []
    for account, aliases in CAPITAL_ALIASES.items():
        alias_map.extend((norm(alias), "자본", account) for alias in aliases)
    for account, aliases in REVIEW_ALIASES.items():
        alias_map.extend((norm(alias), "차감검토", account) for alias in aliases)
    for sheet_name, matrix in _matrixes(name, content):
        for row_no, row in enumerate(matrix, 1):
            for column, cell in enumerate(row):
                label = norm(cell)
                if not label:
                    continue
                match = next(((category, account) for alias, category, account in alias_map if alias == label), None)
                if not match:
                    continue
                amount = _right_amount(matrix, row_no - 1, column)
                if amount is None:
                    continue
                category, account = match
                key = (category, account)
                if key not in found:
                    found[key] = {
                        "구분": category, "계정과목": account, "원천금액": amount,
                        "차감액": 0, "인정조정액": 0,
                        "판정": "전액 인정" if category == "자본" else "검토 필요",
                        "근거·비고": "", "출처": f"{sheet_name} {row_no}행",
                    }
    items = list(found.values())
    # A reported total is safer than summing its components twice.
    if any(row["구분"] == "자본" and row["계정과목"] == "자본총계" for row in items):
        items = [row for row in items if row["구분"] != "자본" or row["계정과목"] == "자본총계"]
    items.sort(key=lambda row: (CATEGORY_OPTIONS.index(row["구분"]), row["계정과목"]))
    return {"items": items, "found": len(items)}


def _uploaded_account_mapping(matrixes):
    mapping = dict(DEFAULT_ACCOUNT_MAP)
    for sheet_name, matrix in matrixes:
        if "계정매핑" not in norm(sheet_name):
            continue
        header_row = next((i for i, row in enumerate(matrix) if any(norm(value) == "계정과목" for value in row) and any(norm(value) == "구분" for value in row)), None)
        if header_row is None:
            continue
        headers = {norm(value): column for column, value in enumerate(matrix[header_row]) if value not in (None, "")}
        for row in matrix[header_row + 1:]:
            if headers.get("계정과목", 10**6) >= len(row):continue
            account = str(row[headers["계정과목"]] or "").strip()
            if not account:continue
            def cell(key):
                column = headers.get(key)
                return str(row[column] or "").strip() if column is not None and column < len(row) else ""
            mapping[account] = (cell("구분") or "미분류", cell("분류"), cell("특수처리"))
    return mapping


def _header_index(headers, aliases):
    for alias in aliases:
        if norm(alias) in headers:return headers[norm(alias)]
    return None


def trial_reflected_amount(debit, credit, group, special=""):
    """Return the balance used for diagnosis from the account's normal side.

    The uploaded report already supplies the balance by debit/credit side.  A
    normal asset therefore uses its debit balance, a normal liability uses its
    credit balance, and only a contra-asset uses the credit balance negatively.
    The opposite-side amount is reviewed separately and is never subtracted
    from the normal-side balance.
    """
    debit=max(0,number(debit) or 0);credit=max(0,number(credit) or 0)
    if group=="자산":return -credit if special=="자산 차감" else debit
    if group=="부채":return credit
    return 0


def trial_opposite_balance(debit, credit, group, special=""):
    """Return an amount shown on the side opposite to the selected account type."""
    debit=max(0,number(debit) or 0);credit=max(0,number(credit) or 0)
    if group=="자산":return debit if special=="자산 차감" else credit
    if group=="부채":return debit
    return 0


def _trial_header(matrix):
    """Find account and ending-balance columns, including two-line trial headers."""
    for i,row in enumerate(matrix):
        candidate={norm(value):column for column,value in enumerate(row) if value not in (None,"")}
        account_col=_header_index(candidate,["계정과목","계정명","과목"])
        if account_col is None:continue
        # Korean trial balances commonly use a two-line header:
        # 차변(잔액/합계) | 계정과목 | 대변(합계/잔액).
        if i+1<len(matrix):
            sub=[norm(value) for value in matrix[i+1]]
            left=[column for column in range(min(account_col,len(sub))) if sub[column]=="잔액"]
            right=[column for column in range(account_col+1,len(sub)) if sub[column]=="잔액"]
            has_debit=any(norm(value)=="차변" and column<account_col for column,value in enumerate(row))
            has_credit=any(norm(value)=="대변" and column>account_col for column,value in enumerate(row))
            if has_debit and has_credit and left and right:
                return {"header_row":i,"data_start":i+2,"headers":candidate,"account_col":account_col,"debit_col":left[-1],"credit_col":right[-1],"amount_col":None,"two_line":True}
        debit_col=_header_index(candidate,["차변잔액","차변금액","차변"]);credit_col=_header_index(candidate,["대변잔액","대변금액","대변"]);amount_col=_header_index(candidate,["당기금액","당기","금액","잔액"])
        if (debit_col is not None and credit_col is not None) or amount_col is not None:
            return {"header_row":i,"data_start":i+1,"headers":candidate,"account_col":account_col,"debit_col":debit_col,"credit_col":credit_col,"amount_col":amount_col,"two_line":False}
    return None


def extract_balance_sheet_totals(name,content):
    """Read authoritative current-year totals from a balance sheet."""
    totals={};sources={};aliases={"자산총계":"assets","부채총계":"liabilities","자본총계":"equity","부채및자본총계":"liabilities_equity"}
    for sheet_name,matrix in _matrixes(name,content):
        for row_index,row in enumerate(matrix):
            for column,value in enumerate(row):
                key=aliases.get(norm(value))
                if not key:continue
                amount=_right_amount(matrix,row_index,column)
                if amount is None:continue
                totals[key]=amount;sources[key]=f"{sheet_name} {row_index+1}행"
    complete=all(key in totals for key in ["assets","liabilities","equity"])
    difference=(totals.get("assets",0)-totals.get("liabilities",0)-totals.get("equity",0)) if complete else None
    return {"totals":totals,"sources":sources,"complete":complete,"difference":difference}


def extract_trial_balance(name, content):
    """Read debit/credit balances and classifications without replacing source amounts."""
    matrixes = _matrixes(name, content);mapping = _uploaded_account_mapping(matrixes)
    normalized_mapping = {norm(account): value for account, value in mapping.items()}
    output = []
    for sheet_name, matrix in matrixes:
        if "계정매핑" in norm(sheet_name) or "사용법" in norm(sheet_name) or "실질자본금" == norm(sheet_name):continue
        found_header=_trial_header(matrix)
        if not found_header:continue
        header_row=found_header["header_row"];data_start=found_header["data_start"];headers=found_header["headers"];account_col=found_header["account_col"];debit_col=found_header["debit_col"];credit_col=found_header["credit_col"];amount_col=found_header["amount_col"]
        group_col=_header_index(headers,["구분"]);class_col=_header_index(headers,["분류"]);special_col=_header_index(headers,["특수처리"]);net_col=_header_index(headers,["순금액","잔액"]);note_col=_header_index(headers,["근거·비고","비고"])
        for row_no,row in enumerate(matrix[data_start:],data_start+1):
            if account_col >= len(row):continue
            account=str(row[account_col] or "").strip();account_norm=norm(account)
            if not account or account_norm in ["월계","누계"] or re.fullmatch(r"\d{1,2}월계",account_norm):continue
            # The user only needs the asset/liability section for real-capital
            # diagnosis.  Stop before paid-in capital and never search or add
            # equity/income-statement rows below it.
            if account_norm in ["자본금","납입자본금"]:break
            if account_norm in ["계", "합계", "총계", "자산총계", "부채총계", "자본총계", "부채및자본총계"]:continue
            default_group,default_class,default_special=normalized_mapping.get(account_norm,("미분류","",""))
            def read(column,default=""):
                return str(row[column] or "").strip() if column is not None and column < len(row) else default
            group=read(group_col,default_group) or default_group;classification=read(class_col,default_class);special=read(special_col,default_special)
            if group not in TRIAL_GROUPS:group="미분류"
            if classification not in TRIAL_CLASSES:classification="검토 필요" if group=="자산" else ""
            if "대손충당금" in account_norm or "감가상각누계액" in account_norm:
                group="자산";special="자산 차감"
            if debit_col is not None and credit_col is not None:
                debit=number(row[debit_col]) if debit_col < len(row) else 0;credit=number(row[credit_col]) if credit_col < len(row) else 0
            else:
                amount=number(row[amount_col]) if amount_col is not None and amount_col < len(row) else 0
                debit=amount if group=="자산" else 0;credit=amount if group in ["부채","제외"] else 0
            debit=debit or 0;credit=credit or 0
            if not debit and not credit:continue
            calculated=trial_reflected_amount(debit,credit,group,special)
            supplied=number(row[net_col]) if net_col is not None and net_col < len(row) else None
            net=calculated if supplied is None or group in ["자산","부채"] else supplied
            output.append({"계정과목":account,"차변잔액":debit,"대변잔액":credit,"구분":group,"분류":classification,"특수처리":special,"순금액":net,"근거·비고":read(note_col),"출처":f"{sheet_name} {row_no}행"})
    imported_adjustments={};reference_required_capital=None
    input_labels={"예금결산일전후30일평균잔액":"deposit_average","공사미수금중인정기간2년초과분":"expired_receivables","기타부실자산조정차감액":"other_bad_assets","퇴직급여추계액결산일전원퇴직가정":"retirement_estimate","기타부외부채미지급세금등":"other_offbook_liabilities"}
    for sheet_name,matrix in matrixes:
        if "실질자본금" not in norm(sheet_name):continue
        for row in matrix:
            if len(row)<2:continue
            if norm(row[0]) in ["등록기준자본금보유면허기준","등록기준자본금"] and number(row[1]) is not None:reference_required_capital=number(row[1])
            key=input_labels.get(norm(row[0]));value=number(row[1])
            if key and value is not None:imported_adjustments[key]=value
    return {"trial_rows":output,"adjustments":imported_adjustments,"reference_required_capital":reference_required_capital,"found":len(output),"unclassified":sum(1 for row in output if row["구분"]=="미분류")}


def rows_before_capital(rows):
    """Retain source order only through the liability section."""
    output=[]
    for row in rows or []:
        if norm(row.get("계정과목","")) in ["자본금","납입자본금"]:break
        output.append(dict(row))
    return output


def clean_trial_rows(rows):
    cleaned=[]
    for raw in rows or []:
        account_value=raw.get("계정과목","");account="" if account_value is None or str(account_value).strip().lower()=="nan" else str(account_value).strip()
        if not account:continue
        debit=max(0,number(raw.get("차변잔액")) or 0);credit=max(0,number(raw.get("대변잔액")) or 0)
        group=str(raw.get("구분","") or "미분류");group=group if group in TRIAL_GROUPS else "미분류"
        classification=str(raw.get("분류","") or "");classification=classification if classification in TRIAL_CLASSES else "검토 필요" if group=="자산" else ""
        special=str(raw.get("특수처리","") or "");special=special if special in SPECIAL_OPTIONS else ""
        net=trial_reflected_amount(debit,credit,group,special)
        manual_confirmed=raw.get("수동확정",False)
        if isinstance(manual_confirmed,str):manual_confirmed=manual_confirmed.strip().lower() in ["1","true","yes","y","확정"]
        cleaned.append({"계정과목":account,"차변잔액":debit,"대변잔액":credit,"구분":group,"분류":classification,"특수처리":special,"순금액":net,"근거·비고":str(raw.get("근거·비고","") or "").strip(),"출처":str(raw.get("출처","직접입력") or "직접입력").strip(),"수동확정":bool(manual_confirmed)})
    return cleaned


def calculate_trial_balance(trial_rows, adjustments, licenses, year=None, statement_totals=None):
    rows=clean_trial_rows(trial_rows);adjustments=dict(adjustments or {});license_rows=clean_licenses(licenses,year or 0)
    trial_assets=sum(row["순금액"] for row in rows if row["구분"]=="자산")
    trial_liabilities=sum(row["순금액"] for row in rows if row["구분"]=="부채")
    statement_totals=dict(statement_totals or {});has_statement=all(number(statement_totals.get(key)) is not None for key in ["assets","liabilities","equity"])
    accounting_assets=number(statement_totals.get("assets")) if has_statement else trial_assets
    accounting_liabilities=number(statement_totals.get("liabilities")) if has_statement else trial_liabilities
    accounting_equity=number(statement_totals.get("equity")) if has_statement else accounting_assets-accounting_liabilities
    statement_difference=accounting_assets-accounting_liabilities-accounting_equity
    asset_reconciliation=trial_assets-accounting_assets;liability_reconciliation=trial_liabilities-accounting_liabilities
    classified_bad=sum(row["순금액"] for row in rows if row["구분"]=="자산" and row["분류"]=="부실")
    cash=sum(row["순금액"] for row in rows if row["구분"]=="자산" and row["특수처리"]=="현금")
    cash_excess=max(0,cash-max(0,accounting_equity)*.01)
    deposits=sum(row["순금액"] for row in rows if row["구분"]=="자산" and row["특수처리"]=="예금")
    deposit_average=adjustments.get("deposit_average")
    deposit_average=None if deposit_average in (None,"") else number(deposit_average)
    deposit_adjustment=max(0,deposits-deposit_average) if deposit_average is not None else 0
    expired=max(0,number(adjustments.get("expired_receivables")) or 0);other_bad=max(0,number(adjustments.get("other_bad_assets")) or 0)
    bad_total=classified_bad+cash_excess+deposit_adjustment+expired+other_bad
    concurrent_assets=sum(row["순금액"] for row in rows if row["구분"]=="자산" and row["분류"]=="겸업")
    review_assets=sum(max(0,row["순금액"]) for row in rows if row["구분"]=="자산" and row["분류"]=="검토 필요")
    real_assets=accounting_assets-bad_total-concurrent_assets-review_assets
    retirement_book=sum(row["순금액"] for row in rows if row["구분"]=="부채" and row["특수처리"]=="퇴직급여충당")
    retirement_estimate=adjustments.get("retirement_estimate");retirement_estimate=None if retirement_estimate in (None,"") else number(retirement_estimate)
    retirement_offbook=max(0,(retirement_estimate or 0)-retirement_book) if retirement_estimate is not None else 0
    other_offbook=max(0,number(adjustments.get("other_offbook_liabilities")) or 0)
    concurrent_liabilities=sum(row["순금액"] for row in rows if row["구분"]=="부채" and row["분류"]=="겸업")
    real_liabilities=accounting_liabilities+retirement_offbook+other_offbook-concurrent_liabilities
    real_capital=real_assets-real_liabilities
    detailed=[]
    for row in license_rows:
        applied=max(0,row["요구자본금"]+row["중복·겸업 조정액"]);detailed.append({**row,"최종 적용자본금":applied})
    required=sum(row["최종 적용자본금"] for row in detailed);surplus=real_capital-required
    unclassified=sum(1 for row in rows if row["구분"]=="미분류" and (row["차변잔액"] or row["대변잔액"]))
    review_count=sum(1 for row in rows if row["구분"]=="자산" and row["분류"]=="검토 필요" and row["순금액"]!=0)
    reconciliation_issue=has_statement and (abs(statement_difference)>1 or abs(asset_reconciliation)>1 or abs(liability_reconciliation)>1)
    status="면허기준 미등록" if required<=0 else "검토 중" if unclassified or review_count or reconciliation_issue else "충족" if surplus>=0 else "미달"
    return {"trial_rows":rows,"licenses":detailed,"accounting_assets":accounting_assets,"accounting_liabilities":accounting_liabilities,"accounting_equity":accounting_equity,"trial_assets":trial_assets,"trial_liabilities":trial_liabilities,"has_statement_totals":has_statement,"statement_difference":statement_difference,"asset_reconciliation":asset_reconciliation,"liability_reconciliation":liability_reconciliation,"reconciliation_issue":reconciliation_issue,"classified_bad":classified_bad,"cash":cash,"cash_excess":int(round(cash_excess)),"deposits":deposits,"deposit_average":deposit_average,"deposit_adjustment":deposit_adjustment,"expired_receivables":expired,"other_bad_assets":other_bad,"bad_total":bad_total,"concurrent_assets":concurrent_assets,"review_assets":review_assets,"real_assets":real_assets,"retirement_book":retirement_book,"retirement_estimate":retirement_estimate,"retirement_offbook":retirement_offbook,"other_offbook_liabilities":other_offbook,"concurrent_liabilities":concurrent_liabilities,"real_liabilities":real_liabilities,"real_capital":real_capital,"required":required,"surplus":surplus,"status":status,"unclassified":unclassified,"review_count":review_count}


def guideline_matches(trial_rows,rules,calculation):
    """Return traceable rule candidates; never invent missing factual evidence."""
    output=[]
    for row in clean_trial_rows(trial_rows):
        account_norm=norm(row["계정과목"])
        for rule in sorted((r for r in rules if r.get("active",True)),key=lambda r:int(r.get("priority",999))):
            aliases=rule.get("aliases",[])
            if isinstance(aliases,str):aliases=[part.strip() for part in aliases.split(',') if part.strip()]
            if not any(norm(alias) and (norm(alias)==account_norm or norm(alias) in account_norm) for alias in aliases):continue
            kind=rule.get("auto_kind","review");recommendation=rule.get("recommendation","검토 필요");amount=None;reason=rule.get("condition") or rule.get("condition_text","")
            if kind=="cash":
                amount=int(calculation.get("cash_excess",0));recommendation="부실" if amount>0 else "인정";reason=f'현금 인정액 {calculation.get("cash",0):,}원 - 자본총계 1% 한도 {max(0,calculation.get("accounting_equity",0))*.01:,.0f}원'
            elif kind=="deposit":
                average=calculation.get("deposit_average")
                if average is None:recommendation="평균잔액 입력 필요"
                else:amount=int(calculation.get("deposit_adjustment",0));recommendation="일부 부실" if amount>0 else "조건부 인정";reason=f'장부 예금 {calculation.get("deposits",0):,}원 / 30일 평균 {average:,}원'
            elif kind=="intangible" and any(word in account_norm for word in ["특허권","산업재산권","사용수익기부자산"]):recommendation="예외 인정 검토"
            elif kind=="liability":recommendation="부외부채 검토"
            output.append({"계정과목":row["계정과목"],"순금액":row["순금액"],"현재분류":row["분류"] or row["구분"],"조문":rule.get("article","") ,"진단규칙":rule.get("title","") ,"권고판정":recommendation,"자동조정액":amount,"확인조건":reason,"필요증빙":rule.get("evidence","") ,"규칙코드":rule.get("code") or rule.get("rule_code","")})
    return output


def _summary_account(account):
    """Identify statement headings/totals that must never be added as accounts."""
    raw=str(account or "").strip();key=norm(raw).replace("<","").replace(">","")
    headings={"자산","유동자산","당좌자산","재고자산","비유동자산","투자자산","유형자산","무형자산","기타비유동자산","부채","유동부채","비유동부채","자본","자본총계","부채총계","자산총계","부채및자본총계"}
    decorated=any(mark in raw for mark in ["<",">","[","]","【","】"])
    return key in headings and (decorated or "총계" in key)


def _plain_text(value):
    if value is None:return ""
    text=str(value).strip()
    return "" if text.lower() in ["nan","<na>","none"] else text


def _rule_for_account(account,rules):
    account_key=norm(account);candidates=[]
    for rule in rules or []:
        if not rule.get("active",True):continue
        aliases=rule.get("aliases",[])
        if isinstance(aliases,str):aliases=[part.strip() for part in aliases.split(",") if part.strip()]
        for alias in aliases:
            alias_key=norm(alias)
            if not alias_key:continue
            if alias_key==account_key:candidates.append((0,int(rule.get("priority",999)),rule,99));break
            if alias_key in account_key or account_key in alias_key:candidates.append((1,int(rule.get("priority",999)),rule,94));break
    return min(candidates,key=lambda item:(item[0],item[1]))[2:] if candidates else (None,0)


def _rule_defaults(account,rule,default):
    """Create a conservative draft. Evidence-dependent legal judgments stay review-only."""
    account_key=norm(account);group,classification,special=default
    if rule:
        kind=str(rule.get("auto_kind","review"))
        if kind=="capital":group,classification,special="제외","",""
        elif kind in ["liability"]:group,classification="부채","일반"
        else:group="자산"
        special_by_kind={"cash":"현금","deposit":"예금","receivable":"공사미수금" if "공사미수금" in account_key else "받을채권","loan":"대여금","inventory":"재고자산","tangible":"유형자산","intangible":"무형자산","allocation":"겸업안분"}
        special=special_by_kind.get(kind,special)
        code=rule.get("code") or rule.get("rule_code","")
        if code=="securities":special="유가증권"
        elif code=="prepayments":special="선급금"
        elif code=="lease_deposit":special="보증금"
        elif code=="provisions":special="퇴직급여충당" if "퇴직급여" in account_key else "충당부채"
        # Only mechanical classifications are finalized. Factual exceptions
        # remain yellow for the worker to decide after checking evidence.
        if group=="자산":classification="인정" if kind in ["cash","deposit"] else "검토 필요"
    if "대손충당금" in account_key or "감가상각누계액" in account_key:
        group,classification,special="자산","인정","자산 차감"
    return group or "미분류",classification,special


def auto_map_trial_rows(rows,rules,overwrite=False):
    """Apply registered guideline aliases while preserving worker decisions by default."""
    defaults={norm(account):value for account,value in DEFAULT_ACCOUNT_MAP.items()};output=[]
    for raw in rows or []:
        row=dict(raw);account=_plain_text(row.get("계정과목",""))
        if not account:continue
        if _summary_account(account):
            row.update({"구분":"제외","분류":"","특수처리":"","순금액":0,"지침 매핑":"제목·집계행 자동판정 · 신뢰도 99%","검토상태":"⚪ 자동 제외"})
            if not _plain_text(row.get("근거·비고","")):row["근거·비고"]="개별 계정이 아닌 구분·합계행으로 중복합산에서 제외"
            output.append(row);continue
        rule,confidence=_rule_for_account(account,rules);default=defaults.get(norm(account),("미분류","",""));suggested=_rule_defaults(account,rule,default)
        manual_confirmed=row.get("수동확정",False)
        if isinstance(manual_confirmed,str):manual_confirmed=manual_confirmed.strip().lower() in ["1","true","yes","y","확정"]
        manual_confirmed=bool(manual_confirmed)
        current_group=_plain_text(row.get("구분","")) or "미분류";current_class=_plain_text(row.get("분류",""));current_special=_plain_text(row.get("특수처리",""))
        if not manual_confirmed:
            if overwrite or current_group=="미분류":current_group=suggested[0]
            if overwrite or not current_class:current_class=suggested[1]
            if overwrite or not current_special:current_special=suggested[2]
        if current_group not in TRIAL_GROUPS:current_group="미분류"
        if current_class not in TRIAL_CLASSES:current_class="검토 필요" if current_group=="자산" else ""
        if current_special not in SPECIAL_OPTIONS:current_special=""
        debit=max(0,number(row.get("차변잔액")) or 0);credit=max(0,number(row.get("대변잔액")) or 0)
        net=trial_reflected_amount(debit,credit,current_group,current_special)
        article=str(rule.get("article","") if rule else "");title=str(rule.get("title","") if rule else "")
        mapping=f'{article} {title} · 신뢰도 {confidence}%' if rule else "기본 계정사전 · 신뢰도 90%" if norm(account) in defaults else "지침 매핑 없음"
        condition=str((rule.get("condition") or rule.get("condition_text") or "") if rule else "")
        note=_plain_text(row.get("근거·비고",""))
        if not note and condition:note=condition
        opposite_amount=trial_opposite_balance(debit,credit,current_group,current_special)
        opposite_balance=opposite_amount>0
        if manual_confirmed:
            status="✅ 작업자 확정"
            if opposite_balance:
                warning=f"반대편 잔액 {opposite_amount:,.0f}원은 반영금액에서 차감하지 않았습니다. 작업자가 확인 후 확정한 값입니다."
                if not note:note=warning
                elif warning not in note:note=note+" | "+warning
        elif current_group=="미분류":status="🔵 미분류"
        elif opposite_balance:
            status="🟡 금액 확인";current_class="검토 필요" if current_group=="자산" else current_class
            warning=f"반대편 잔액 {opposite_amount:,.0f}원은 반영금액에서 차감하지 않았습니다. 원본 열과 계정 구분을 확인하세요."
            if not note:note=warning
            elif warning not in note:note=note+" | "+warning
        elif current_class=="검토 필요":status="🟡 검토 필요"
        else:status="🟢 자동 초안"
        row.update({"차변잔액":debit,"대변잔액":credit,"구분":current_group,"분류":current_class,"특수처리":current_special,"순금액":net,"지침 매핑":mapping,"근거·비고":note,"검토상태":status,"수동확정":manual_confirmed})
        output.append(row)
    return output


def auto_mapping_summary(rows):
    statuses=[str(row.get("검토상태","") or "") for row in rows or []]
    return {"전체":len(statuses),"자동처리":sum("자동 초안" in value for value in statuses),"작업자확정":sum("작업자 확정" in value for value in statuses),"검토필요":sum("검토 필요" in value or "금액 확인" in value or "미분류" in value for value in statuses),"제외":sum("자동 제외" in value for value in statuses)}


def clean_items(items):
    cleaned = []
    for raw in items or []:
        account_value = raw.get("계정과목", "")
        account = "" if account_value is None or str(account_value).strip().lower() == "nan" else str(account_value).strip()
        if not account:
            continue
        category = str(raw.get("구분", "차감검토") or "차감검토")
        if category not in CATEGORY_OPTIONS:
            category = "차감검토"
        decision = str(raw.get("판정", "검토 필요") or "검토 필요")
        if decision not in DECISION_OPTIONS:
            decision = "검토 필요"
        source_amount = number(raw.get("원천금액")) or 0
        deduction = max(0, number(raw.get("차감액")) or 0)
        adjustment = number(raw.get("인정조정액")) or 0
        if category == "차감검토" and decision == "전액 차감" and deduction == 0:
            deduction = max(0, source_amount)
        cleaned.append({
            "구분": category, "계정과목": account, "원천금액": source_amount,
            "차감액": deduction, "인정조정액": adjustment, "판정": decision,
            "근거·비고": str(raw.get("근거·비고", "") or "").strip(),
            "출처": str(raw.get("출처", "직접입력") or "직접입력").strip(),
        })
    return cleaned


def clean_licenses(licenses, year):
    cleaned = []
    for raw in licenses or []:
        name_value = raw.get("면허명·업종", "")
        name = "" if name_value is None or str(name_value).strip().lower() == "nan" else str(name_value).strip()
        if not name:
            continue
        required = max(0, number(raw.get("요구자본금")) or 0)
        adjustment = number(raw.get("중복·겸업 조정액")) or 0
        cleaned.append({
            "면허명·업종": name, "요구자본금": required,
            "중복·겸업 조정액": adjustment,
            "적용연도": int(number(raw.get("적용연도")) or year),
            "근거·비고": str(raw.get("근거·비고", "") or "").strip(),
        })
    return cleaned


def calculate(items, licenses, year=None):
    rows = clean_items(items)
    license_rows = clean_licenses(licenses, year or 0)
    capital_rows = [row for row in rows if row["구분"] == "자본"]
    reported_total = [row for row in capital_rows if norm(row["계정과목"]) in ["자본총계", "자기자본"]]
    capital = sum(row["원천금액"] for row in (reported_total or capital_rows))
    deduction = sum(row["차감액"] for row in rows if row["구분"] == "차감검토")
    adjustment = sum(row["인정조정액"] for row in rows)
    real_capital = capital - deduction + adjustment
    detailed = []
    for row in license_rows:
        applied = max(0, row["요구자본금"] + row["중복·겸업 조정액"])
        detailed.append({**row, "최종 적용자본금": applied})
    required = sum(row["최종 적용자본금"] for row in detailed)
    surplus = real_capital - required
    unresolved = sum(1 for row in rows if row["구분"] == "차감검토" and row["판정"] == "검토 필요")
    status = "면허기준 미입력" if required <= 0 else "검토 중" if unresolved else "충족" if surplus >= 0 else "미충족"
    return {
        "items": rows, "licenses": detailed, "capital": capital, "deduction": deduction,
        "adjustment": adjustment, "real_capital": real_capital, "required": required,
        "surplus": surplus, "status": status,
        "unresolved": unresolved,
    }


def _money(value):
    return f"{int(value or 0):,}"


def report_workbook(company, year, result):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = f"{year}.실질자본금"[:31]
    dark, green, pale, yellow, red = "173F59", "087A4F", "EAF3F7", "FFF2A8", "FCE8E6"
    thin = Side(style="thin", color="AAB8BF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    sheet.merge_cells("A1:H1");sheet["A1"] = f"{year}년 실질자본금 적격여부 검토표"
    sheet["A1"].font = Font(name="맑은 고딕", size=18, bold=True, color="FFFFFF")
    sheet["A1"].fill = PatternFill("solid", fgColor=dark);sheet["A1"].alignment = Alignment(horizontal="center")
    sheet.merge_cells("A2:D2");sheet["A2"] = f"결산법인  {company}"
    sheet.merge_cells("E2:H2");sheet["E2"] = f"결산연도  {year}년"
    for cell in sheet[2]:cell.fill = PatternFill("solid", fgColor=pale);cell.font = Font(name="맑은 고딕", bold=True, color=dark);cell.alignment = Alignment(horizontal="center")
    headers = ITEM_COLUMNS
    sheet.append(headers)
    for row in result["items"]:sheet.append([row.get(key, "") for key in headers])
    start = 3
    for cell in sheet[start]:cell.fill = PatternFill("solid", fgColor=green);cell.font = Font(name="맑은 고딕", bold=True, color="FFFFFF");cell.alignment = Alignment(horizontal="center")
    summary_row = sheet.max_row + 2
    summary = [("자본총계", result["capital"]), ("차감대상 자산", result["deduction"]), ("인정 조정액", result["adjustment"]), ("실질자본금", result["real_capital"]), ("최종 필요자본금", result["required"]), ("충족 여유액(부족액)", result["surplus"])]
    for offset, (label, value) in enumerate(summary):
        row = summary_row + offset;sheet.cell(row, 1, label);sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4);sheet.cell(row, 2, value)
        sheet.cell(row, 1).font = Font(name="맑은 고딕", bold=True);sheet.cell(row, 2).font = Font(name="맑은 고딕", bold=True, color="D92C25" if offset >= 3 else "126BB0")
        for col in range(1, 5):sheet.cell(row, col).fill = PatternFill("solid", fgColor=yellow if offset >= 3 else pale);sheet.cell(row, col).border = border
        sheet.cell(row, 2).number_format = "#,##0;[Red]-#,##0";sheet.cell(row, 2).alignment = Alignment(horizontal="right")
    license_start = summary_row
    sheet.merge_cells(start_row=license_start, start_column=5, end_row=license_start, end_column=8);sheet.cell(license_start, 5, "회사별 면허 기준자본금")
    sheet.cell(license_start, 5).fill = PatternFill("solid", fgColor=green);sheet.cell(license_start, 5).font = Font(name="맑은 고딕", bold=True, color="FFFFFF");sheet.cell(license_start, 5).alignment = Alignment(horizontal="center")
    license_headers = ["면허명·업종", "요구자본금", "조정액", "최종 적용자본금"]
    for col, label in enumerate(license_headers, 5):sheet.cell(license_start + 1, col, label)
    for i, row in enumerate(result["licenses"], license_start + 2):
        values = [row["면허명·업종"], row["요구자본금"], row["중복·겸업 조정액"], row["최종 적용자본금"]]
        for col, value in enumerate(values, 5):sheet.cell(i, col, value)
    max_row = max(sheet.max_row, license_start + len(result["licenses"]) + 1)
    for row in sheet.iter_rows(min_row=3, max_row=max_row, min_col=1, max_col=8):
        for cell in row:
            cell.border = border;cell.font = cell.font.copy(name="맑은 고딕");cell.alignment = Alignment(horizontal="right" if cell.column in [3,4,5,6,7,8] and isinstance(cell.value, (int, float)) else "center", vertical="center", wrap_text=True)
            if isinstance(cell.value, (int, float)):cell.number_format = "#,##0;[Red]-#,##0"
    for col, width in enumerate([13,22,16,16,16,18,28,18], 1):sheet.column_dimensions[get_column_letter(col)].width = width
    sheet.freeze_panes = "A4";sheet.sheet_view.showGridLines = False;sheet.print_area = f"A1:H{max_row}";sheet.page_setup.orientation = "landscape";sheet.page_setup.fitToWidth = 1;sheet.sheet_properties.pageSetUpPr.fitToPage = True
    output = BytesIO();book.save(output);return output.getvalue()


def report_html(company, year, result):
    item_rows = "".join("<tr>" + "".join(f"<td class='{('num' if key in ['원천금액','차감액','인정조정액'] else '')}'>{_money(row[key]) if key in ['원천금액','차감액','인정조정액'] else escape(str(row[key]))}</td>" for key in ITEM_COLUMNS) + "</tr>" for row in result["items"])
    license_rows = "".join(f"<tr><td>{escape(row['면허명·업종'])}</td><td class='num'>{_money(row['요구자본금'])}</td><td class='num'>{_money(row['중복·겸업 조정액'])}</td><td class='num'>{_money(row['최종 적용자본금'])}</td><td>{escape(row['근거·비고'])}</td></tr>" for row in result["licenses"])
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>실질자본금 검토표</title><style>
    @page{{size:A4 landscape;margin:9mm}}body{{font-family:"Malgun Gothic",sans-serif;color:#173f59;margin:0}}button{{padding:7px 14px;margin-bottom:8px}}h1{{background:#173f59;color:#fff;padding:12px;text-align:center;font-size:20px;margin:0}}.identity{{display:flex;justify-content:space-between;background:#eaf3f7;padding:9px 14px;font-weight:700}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:10px 0}}.card{{border:1px solid #b9cbd4;border-radius:6px;padding:8px;text-align:center;background:#f7fafb}}.card strong{{display:block;color:#126bb0;font-size:16px;margin-top:4px}}.result{{background:#fff2a8}}.result strong{{color:#d92c25}}h2{{font-size:14px;background:#087a4f;color:white;padding:6px 8px;margin:12px 0 0}}table{{border-collapse:collapse;width:100%;font-size:9px}}th,td{{border:1px solid #aab8bf;padding:4px;text-align:center}}th{{background:#eaf3f7}}td.num{{text-align:right;color:#126bb0;font-variant-numeric:tabular-nums}}@media print{{button{{display:none}}}}</style></head><body>
    <button onclick="window.print()">인쇄 · PDF 저장</button><h1>{year}년 실질자본금 적격여부 검토표</h1><div class="identity"><span>결산법인　{escape(company)}</span><span>결산연도　{year}년</span><span>판정　{result['status']}</span></div>
    <div class="cards"><div class="card">자본총계<strong>{_money(result['capital'])}원</strong></div><div class="card">차감대상 자산<strong>{_money(result['deduction'])}원</strong></div><div class="card result">실질자본금<strong>{_money(result['real_capital'])}원</strong></div><div class="card result">여유액(부족액)<strong>{_money(result['surplus'])}원</strong></div></div>
    <h2>실질자본금 계산내역</h2><table><thead><tr>{''.join(f'<th>{escape(key)}</th>' for key in ITEM_COLUMNS)}</tr></thead><tbody>{item_rows}</tbody></table>
    <h2>회사별 면허 기준자본금</h2><table><thead><tr><th>면허명·업종</th><th>요구자본금</th><th>중복·겸업 조정액</th><th>최종 적용자본금</th><th>근거·비고</th></tr></thead><tbody>{license_rows}</tbody></table>
    <p style="font-size:9px;color:#667">면허별 법정 기준과 중복·겸업 조정은 현재 기준금액과 근거자료를 확인한 후 확정하십시오.</p></body></html>'''.encode("utf-8")


def _trial_summary_rows(result):
    return [
        ("회계상 금액","회계상 자산총계",result["accounting_assets"]),("회계상 금액","회계상 부채총계",result["accounting_liabilities"]),("회계상 금액","회계상 자본총계",result["accounting_equity"]),
        ("실질자산","(-) 계정분류상 부실자산",result["classified_bad"]),("실질자산","(-) 현금 한도초과분",result["cash_excess"]),("실질자산","(-) 예금 평균잔액 조정",result["deposit_adjustment"]),("실질자산","(-) 공사미수금 인정기간 초과분",result["expired_receivables"]),("실질자산","(-) 기타 부실자산 조정",result["other_bad_assets"]),("실질자산","부실자산 합계",result["bad_total"]),("실질자산","(-) 겸업자산",result["concurrent_assets"]),("실질자산","(-) 검토대기 자산",result.get("review_assets",0)),("실질자산","실질자산",result["real_assets"]),
        ("실질부채","회계상 부채총계",result["accounting_liabilities"]),("실질부채","(+) 퇴직급여 부외부채",result["retirement_offbook"]),("실질부채","(+) 기타 부외부채",result["other_offbook_liabilities"]),("실질부채","(-) 겸업부채",result["concurrent_liabilities"]),("실질부채","실질부채",result["real_liabilities"]),
        ("판정","실질자본금",result["real_capital"]),("판정","등록기준 자본금",result["required"]),("판정","여유(부족) 금액",result["surplus"]),
    ]


def _evaluation_category(row):
    account=norm(row.get("계정과목",""));special=row.get("특수처리","")
    if special in ["현금","예금"]:return "예금"
    if special=="공사미수금":return "공사미수금"
    if special=="받을채권":return "매출채권·미수금"
    if special=="유가증권":return "유가증권"
    if special=="대여금":return "대여금"
    if special=="선급금":return "선급금"
    if special=="보증금":return "보증금"
    if special=="재고자산":return "재고자산"
    if special=="유형자산":return "유형자산"
    if special=="무형자산":return "무형자산"
    if special=="자산 차감":return "매출채권·미수금" if "대손충당금" in account else "유형자산"
    return "기타자산"


def asset_liability_evaluation_rows(result):
    """Build the approved final diagnostic statement from calculated balances."""
    order=["예금","유가증권","매출채권·미수금","공사미수금","재고자산","대여금","선급금","보증금","유형자산","무형자산","기타자산"]
    buckets={name:{"amount":0,"deduction":0,"accounts":[]} for name in order}
    for row in result.get("trial_rows",[]):
        if row.get("구분")!="자산":continue
        category=_evaluation_category(row);bucket=buckets[category];bucket["amount"]+=int(row.get("순금액",0) or 0);bucket["accounts"].append(str(row.get("계정과목","") or ""))
        if row.get("분류") in ["부실","겸업","검토 필요"]:bucket["deduction"]+=max(0,int(row.get("순금액",0) or 0))
    buckets["예금"]["deduction"]+=int(result.get("cash_excess",0) or 0)+int(result.get("deposit_adjustment",0) or 0)
    buckets["공사미수금"]["deduction"]+=int(result.get("expired_receivables",0) or 0)
    buckets["기타자산"]["deduction"]+=int(result.get("other_bad_assets",0) or 0)
    output=[];numbering=1
    for category in order:
        bucket=buckets[category]
        if not bucket["amount"] and not bucket["deduction"]:continue
        accounts=', '.join(dict.fromkeys(name for name in bucket["accounts"] if name));note=("포함계정: "+accounts) if accounts else "진단 조정 입력액"
        if bucket["deduction"]:note+=" / 부실·겸업·검토대기 및 지침 조정 차감"
        output.append({"구분":f"{numbering}. {category}","재무제표 가액(A)":bucket["amount"],"부실/겸업자산 차감(B)":bucket["deduction"],"실질자산 가액(C=A-B)":bucket["amount"]-bucket["deduction"],"비고":note});numbering+=1
    output.append({"구분":"자산 총계","재무제표 가액(A)":result["accounting_assets"],"부실/겸업자산 차감(B)":result["bad_total"]+result["concurrent_assets"]+result.get("review_assets",0),"실질자산 가액(C=A-B)":result["real_assets"],"비고":"회계상 자산에서 부실·겸업·검토대기 자산 차감"})
    liability_note="모든 부채 및 부외부채 반영"
    if result.get("concurrent_liabilities"):liability_note+=" / 겸업부채 차감"
    output.append({"구분":"부채 총계","재무제표 가액(A)":result["accounting_liabilities"],"부실/겸업자산 차감(B)":None,"실질자산 가액(C=A-B)":result["real_liabilities"],"비고":liability_note})
    output.append({"구분":"실질자본금","재무제표 가액(A)":None,"부실/겸업자산 차감(B)":None,"실질자산 가액(C=A-B)":result["real_capital"],"비고":"실질자산 - 실질부채"})
    return output


def final_judgment(result):
    if result.get("required",0)<=0:return "검토 중","-","면허별 법정 자본금을 먼저 등록하세요."
    operator="≥" if result["real_capital"]>=result["required"] else "<"
    status="검토 중" if result.get("status") in ["검토 중","면허기준 미등록"] else "적격" if operator=="≥" else "부적격"
    text=f'● 실질자본금({_money(result["real_capital"])}원) {operator} 법정 자본금({_money(result["required"])}원) → [{status}]'
    return status,operator,text


def trial_report_workbook(company,year,result):
    book=openpyxl.Workbook();sheet=book.active;sheet.title="자산및부채평가"
    dark,pale,yellow="173F59","EAF3F7","FFF2A8";thin=Side(style="thin",color="333333");border=Border(left=thin,right=thin,top=thin,bottom=thin)
    sheet.merge_cells("A1:E1");sheet["A1"]="[자산 및 부채 평가 내역]";sheet["A1"].font=Font(name="맑은 고딕",size=16,bold=True);sheet["A1"].alignment=Alignment(horizontal="center")
    sheet.merge_cells("A2:C2");sheet["A2"]=f"결산법인: {company}";sheet.merge_cells("D2:E2");sheet["D2"]=f"결산연도: {year}년　(단위: 원)"
    headers=["구분","재무제표 가액\n(A)","부실/겸업자산 차감\n(B)","실질자산 가액\n(C=A-B)","비고"]
    for col,label in enumerate(headers,1):sheet.cell(4,col,label)
    rows=asset_liability_evaluation_rows(result)
    for row_no,row in enumerate(rows,5):
        for col,key in enumerate(["구분","재무제표 가액(A)","부실/겸업자산 차감(B)","실질자산 가액(C=A-B)","비고"],1):sheet.cell(row_no,col,row.get(key))
        if row["구분"] in ["자산 총계","부채 총계","실질자본금"]:
            for col in range(1,6):sheet.cell(row_no,col).font=Font(name="맑은 고딕",bold=True);sheet.cell(row_no,col).fill=PatternFill("solid",fgColor=yellow if row["구분"]=="실질자본금" else pale)
    final_row=5+len(rows)+2;status,operator,judgment=final_judgment(result);sheet.merge_cells(start_row=final_row,start_column=1,end_row=final_row,end_column=5);sheet.cell(final_row,1,"최종 판정\n    "+judgment);sheet.cell(final_row,1).font=Font(name="맑은 고딕",size=13,bold=True,color="087A4F" if status=="적격" else "D92C25" if status=="부적격" else "806300");sheet.cell(final_row,1).fill=PatternFill("solid",fgColor="E8F7EF" if status=="적격" else "FFF0EF" if status=="부적격" else "FFF8DC");sheet.cell(final_row,1).alignment=Alignment(horizontal="left",vertical="center",wrap_text=True);sheet.row_dimensions[final_row].height=42
    for row in sheet.iter_rows(min_row=4,max_row=final_row,min_col=1,max_col=5):
        for cell in row:
            cell.border=border
            if cell.row==4:cell.fill=PatternFill("solid",fgColor=pale);cell.font=Font(name="맑은 고딕",bold=True);cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
            elif cell.row!=final_row:cell.alignment=Alignment(horizontal="right" if cell.column in [2,3,4] else "center" if cell.column==1 else "left",vertical="center",wrap_text=True);cell.font=cell.font.copy(name="맑은 고딕");cell.number_format="#,##0;[Red]-#,##0;-"
    for col,width in enumerate([22,18,20,20,46],1):sheet.column_dimensions[get_column_letter(col)].width=width
    sheet.row_dimensions[4].height=35;sheet.sheet_view.showGridLines=False;sheet.print_area=f"A1:E{final_row}";sheet.page_setup.orientation="portrait";sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=1;sheet.sheet_properties.pageSetUpPr.fitToPage=True
    detail=book.create_sheet("계정분류상세");detail.append(["계정과목","차변잔액","대변잔액","구분","분류","특수처리","계정 반영금액","근거·비고","출처"])
    for row in result.get("trial_rows",[]):detail.append([row.get(key,"") for key in TRIAL_COLUMNS])
    for row in detail.iter_rows():
        for cell in row:cell.border=border;cell.alignment=Alignment(horizontal="right" if isinstance(cell.value,(int,float)) else "center",vertical="center",wrap_text=True);cell.number_format="#,##0;[Red]-#,##0" if isinstance(cell.value,(int,float)) else "General"
    for col,width in enumerate([22,16,16,13,14,18,16,44,18],1):detail.column_dimensions[get_column_letter(col)].width=width
    detail.freeze_panes="A2";detail.sheet_view.showGridLines=False
    output=BytesIO();book.save(output);return output.getvalue()


def trial_report_html(company,year,result):
    rows=asset_liability_evaluation_rows(result)
    body=[]
    for row in rows:
        strong=row["구분"] in ["자산 총계","부채 총계","실질자본금"]
        cells=[]
        for key in ["구분","재무제표 가액(A)","부실/겸업자산 차감(B)","실질자산 가액(C=A-B)","비고"]:
            value=row.get(key)
            if key in ["재무제표 가액(A)","부실/겸업자산 차감(B)","실질자산 가액(C=A-B)"]:
                rendered="-" if value is None else _money(value)
                cells.append(f"<td class='num'>{rendered}</td>")
            else:cells.append(f"<td>{escape(str(value or ''))}</td>")
        body.append(f"<tr class='{'total final-capital' if row['구분']=='실질자본금' else 'total' if strong else ''}'>"+''.join(cells)+"</tr>")
    status,operator,judgment=final_judgment(result);judgment_class="ok" if status=="적격" else "bad" if status=="부적격" else "pending"
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>자산 및 부채 평가 내역</title><style>
    @page{{size:A4 portrait;margin:12mm}}body{{font-family:"Malgun Gothic",sans-serif;color:#111;margin:0}}button{{padding:7px 14px;margin-bottom:10px}}h1{{font-size:19px;text-align:center;margin:8px 0 22px}}.meta{{display:flex;justify-content:space-between;font-size:11px;margin-bottom:8px}}table{{border-collapse:collapse;width:100%;font-size:10px}}th,td{{border:1px solid #333;padding:7px 6px;text-align:center;vertical-align:middle}}th{{background:#eaf3f7;font-weight:700}}td.num{{text-align:right;font-variant-numeric:tabular-nums}}td:last-child{{text-align:left}}tr.total td{{font-weight:700;background:#f2f6f8}}tr.final-capital td{{background:#fff2a8}}.judgment{{margin-top:20px;border:2px solid #333;padding:14px 18px;font-size:14px;font-weight:700;line-height:1.8}}.judgment.ok{{border-color:#087a4f;color:#087a4f;background:#e8f7ef}}.judgment.bad{{border-color:#d92c25;color:#d92c25;background:#fff0ef}}.judgment.pending{{border-color:#806300;color:#806300;background:#fff8dc}}.label{{color:#111;display:block}}@media print{{button{{display:none}}}}</style></head><body>
    <button onclick="window.print()">인쇄 · PDF 저장</button><h1>[자산 및 부채 평가 내역]</h1><div class="meta"><span>결산법인　{escape(company)}</span><span>(단위: 원)</span><span>결산연도　{year}년</span></div>
    <table><thead><tr><th>구분</th><th>재무제표 가액<br>(A)</th><th>부실/겸업자산 차감<br>(B)</th><th>실질자산 가액<br>(C=A-B)</th><th>비고</th></tr></thead><tbody>{''.join(body)}</tbody></table>
    <div class="judgment {judgment_class}"><span class="label">최종 판정</span>{escape(judgment)}</div></body></html>'''.encode("utf-8")
