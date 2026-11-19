"""Construction-company management-ratio checks and association PDF imports."""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from io import BytesIO, StringIO
from pathlib import Path
import csv
import math
import re
import statistics
import sys

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


RATIOS = {
    "debt_ratio": {
        "label": "부채비율", "unit": "%", "direction": "lower", "formula": "부채총계 ÷ 자기자본",
        "aliases": ["부채비율"], "points": [8.0, 7.2, 6.4, 5.6, 4.8], "thresholds": [50, 75, 100, 125],
    },
    "current_ratio": {
        "label": "유동비율", "unit": "%", "direction": "higher", "formula": "유동자산 ÷ 유동부채",
        "aliases": ["유동비율"], "points": [8.0, 7.2, 6.4, 5.6, 4.8], "thresholds": [150, 120, 100, 70],
    },
    "borrowing_ratio": {
        "label": "차입금의존도", "unit": "%", "direction": "lower", "formula": "차입금 ÷ 총자산",
        "aliases": ["차입금의존도", "차입금 의존도"], "points": [4.0, 3.6, 3.2, 2.8, 2.4], "thresholds": [50, 75, 100, 125],
    },
    "interest_coverage": {
        "label": "이자보상배율", "unit": "배", "direction": "higher", "formula": "영업이익 ÷ 이자비용",
        "aliases": ["이자보상배율", "이자 보상배율"], "points": [4.0, 3.6, 3.2, 2.8, 2.4], "thresholds": [150, 100, 50, 10],
    },
    "sales_profit_ratio": {
        "label": "매출액순이익률", "unit": "%", "direction": "higher", "formula": "세전이익 ÷ 매출액",
        "aliases": ["매출액순이익률", "매출액 순이익율", "매출순이익율"], "points": [3.0, 2.7, 2.4, 2.1, 1.8],
        "thresholds": [100, 75, 50, 10],
    },
    "asset_profit_ratio": {
        "label": "총자산순이익률", "unit": "%", "direction": "higher", "formula": "세전이익 ÷ 총자산",
        "aliases": ["총자산순이익률", "총자산 순이익율"], "points": [1.0, .9, .8, .7, .6], "thresholds": [150, 100, 50, 10],
    },
    "cash_flow_ratio": {
        "label": "현금흐름비율", "unit": "%", "direction": "higher", "formula": "영업활동현금흐름 ÷ 총자산",
        "aliases": ["현금흐름비율", "현금 흐름 비율"], "points": [2.0, 1.8, 1.6, 1.4, 1.2], "thresholds": [150, 120, 100, 70],
    },
    "asset_turnover": {
        "label": "자산회전율", "unit": "회", "direction": "higher", "formula": "매출액 ÷ 평균총자산",
        "aliases": ["자산회전율", "자산 회전율"], "points": [3.0, 2.7, 2.4, 2.1, 1.8], "thresholds": [150, 100, 50, 10],
    },
    "tech_investment_ratio": {
        "label": "기술개발투자율", "unit": "%", "direction": "higher", "formula": "기술개발비 ÷ 건설매출액",
        "aliases": ["기술개발투자율", "기술개발 투자율"], "points": [4.0, 3.6, 3.2, 2.8, 2.4], "thresholds": [150, 100, 50, 10],
    },
    "business_years": {
        "label": "영업기간", "unit": "년", "direction": "direct", "formula": "설립일 ～ 결산일",
        "aliases": ["영업기간", "영업 기간"], "points": [2.0, 1.8, 1.6, 1.4], "thresholds": [10, 5, 3],
    },
}

FINANCIAL_FIELDS = {
    "debt_total": ("부채총계", ["부채총계", "부채 총계"]),
    "equity_total": ("자기자본", ["자본총계", "자기자본"]),
    "current_assets": ("유동자산", ["유동자산"]),
    "current_liabilities": ("유동부채", ["유동부채"]),
    "borrowings": ("차입금", ["차입금", "단기차입금", "장기차입금"]),
    "total_assets": ("기말총자산", ["자산총계", "부채및자본총계", "부채 및 자본 총계"]),
    "beginning_assets": ("기초총자산", ["전기자산총계", "자산총계(전기)", "부채및자본총계(전기)"]),
    "operating_profit": ("영업이익", ["영업이익"]),
    "interest_expense": ("이자비용", ["이자비용"]),
    "pre_tax_income": ("세전이익", ["법인세비용차감전순이익", "세전이익"]),
    "operating_cash_flow": ("영업활동현금흐름", ["영업활동으로인한현금흐름", "영업활동현금흐름", "영업활동 현금흐름"]),
    "sales": ("매출액", ["매출액", "매출총액"]),
    "construction_sales": ("건설매출액", ["공사수입", "건설매출액", "공사매출액"]),
    "tech_development": ("기술개발비", ["기술개발비", "기술개발투자비"]),
}


def norm(value):
    return re.sub(r"[\s\n\r()·._\-ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]", "", str(value or "")).lower()


def number(value):
    if value in (None, "", "-"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    text = str(value).strip().replace(",", "").replace("%", "").replace("배", "").replace("회", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        result = float(text)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _pdf_text(content):
    try:
        from pypdf import PdfReader
    except ImportError:
        bundled = Path(__file__).resolve().parent / "vendor" / "pypdf-6.10.0.zip"
        if bundled.is_file() and str(bundled) not in sys.path:
            sys.path.insert(0, str(bundled))
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF 판독 모듈이 없습니다. 최신 업데이트를 다시 적용하세요.") from exc
    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ValueError("협회 PDF를 읽을 수 없습니다. 암호 또는 파일 손상 여부를 확인하세요.") from exc


def publication_year(text, filename=""):
    candidates = re.findall(r"(?:19|20)\d{2}", f"{filename}\n{text[:3000]}")
    years = [int(v) for v in candidates if 1990 <= int(v) <= date.today().year + 2]
    return max(years) if years else date.today().year - 1


def extract_pdf_ratios(content, filename=""):
    """Best-effort extraction; every result remains editable before saving."""
    text = _pdf_text(content)
    compact_lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    values = {}
    pattern = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?\s*(?:%|배|회|년)?")
    for key, spec in RATIOS.items():
        found = None
        for i, line in enumerate(compact_lines):
            if not any(norm(alias) in norm(line) for alias in spec["aliases"]):
                continue
            aliases_at = [line]
            if i + 1 < len(compact_lines):
                aliases_at.append(compact_lines[i + 1])
            if i + 2 < len(compact_lines):
                aliases_at.append(compact_lines[i + 2])
            joined = " ".join(aliases_at)
            pos = min((joined.find(alias) for alias in spec["aliases"] if alias in joined), default=0)
            candidates = []
            for token in pattern.findall(joined[max(0, pos):]):
                value = number(token)
                if value is None or (1900 <= value <= 2100 and not any(u in token for u in "%배회년")):
                    continue
                unit_match = spec["unit"] in token
                candidates.append((unit_match, value))
            if candidates:
                unit_values = [v for matched, v in candidates if matched]
                found = unit_values[0] if unit_values else candidates[0][1]
                break
        values[key] = found
    return {"year": publication_year(text, filename), "ratios": values, "text": text,
            "warning": "" if text.strip() else "문자 추출이 되지 않는 스캔 PDF입니다. 공시값을 직접 입력해 주세요."}


def _matrixes(name, content):
    lower = name.lower()
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


def extract_financial_statement(name, content):
    results = {key: None for key in FINANCIAL_FIELDS}
    evidence = {}
    for sheet_name, matrix in _matrixes(name, content):
        for row_index, row in enumerate(matrix, 1):
            for col_index, cell in enumerate(row):
                cell_norm = norm(cell)
                if not cell_norm:
                    continue
                for key, (_, aliases) in FINANCIAL_FIELDS.items():
                    # Exact normalized labels avoid mistaking ratio headings
                    # such as "차입금의존도" or "매출액순이익률" for source accounts.
                    if results[key] is not None or not any(norm(alias) == cell_norm for alias in aliases):
                        continue
                    right = [number(v) for v in row[col_index + 1:]]
                    right = [v for v in right if v is not None]
                    if right:
                        results[key] = right[0]
                        evidence[key] = f"{sheet_name} {row_index}행"
                        if key == "total_assets" and results["beginning_assets"] is None and len(right) > 1:
                            results["beginning_assets"] = right[1]
                            evidence["beginning_assets"] = f"{sheet_name} {row_index}행 전기금액"
    return {"values": results, "evidence": evidence,
            "missing": [key for key, value in results.items() if value is None]}


def financial_ratios(values, year):
    v = {key: float(values.get(key) or 0) for key in FINANCIAL_FIELDS}
    def pct(num, den):
        return num / den * 100 if den else None
    established = values.get("established_date")
    years = None
    if established:
        try:
            started = datetime.fromisoformat(str(established)[:10]).date()
            ended = date(int(year), 12, 31)
            years = max(0, ended.year - started.year - ((ended.month, ended.day) < (started.month, started.day)))
        except ValueError:
            pass
    average_assets = (v["beginning_assets"] + v["total_assets"]) / 2 if v["beginning_assets"] and v["total_assets"] else v["total_assets"]
    return {
        "debt_ratio": pct(v["debt_total"], v["equity_total"]),
        "current_ratio": pct(v["current_assets"], v["current_liabilities"]),
        "borrowing_ratio": pct(v["borrowings"], v["total_assets"]),
        "interest_coverage": v["operating_profit"] / v["interest_expense"] if v["interest_expense"] else None,
        "sales_profit_ratio": pct(v["pre_tax_income"], v["sales"]),
        "asset_profit_ratio": pct(v["pre_tax_income"], v["total_assets"]),
        "cash_flow_ratio": pct(v["operating_cash_flow"], v["total_assets"]),
        "asset_turnover": v["sales"] / average_assets if average_assets else None,
        "tech_investment_ratio": pct(v["tech_development"], v["construction_sales"]),
        "business_years": years,
    }


def _remove_level_outliers(values):
    values = [float(v) for v in values]
    if len(values) < 4:
        return values, 0
    med = statistics.median(values)
    deviations = [abs(v - med) for v in values]
    mad = statistics.median(deviations)
    cleaned = list(values)
    removed = 0
    if mad == 0:
        limit = max(abs(med) * .5, .01)
        for i, value in enumerate(values):
            if abs(value - med) > limit:
                cleaned[i] = med
                removed += 1
    else:
        for i, value in enumerate(values):
            if .6745 * abs(value - med) / mad > 3.5:
                cleaned[i] = med
                removed += 1
    return cleaned, removed


def trend_forecast(points):
    """Recent-year weighted linear trend with robust level outlier handling."""
    pairs = sorted((int(year), float(value)) for year, value in points if value is not None)[-5:]
    if not pairs:
        return {"value": None, "lower": None, "upper": None, "confidence": "자료없음", "years": [], "outliers": 0, "r2": 0}
    years = [p[0] for p in pairs]
    raw = [p[1] for p in pairs]
    values, outliers = _remove_level_outliers(raw)
    if len(pairs) == 1:
        return {"value": values[0], "lower": values[0], "upper": values[0], "confidence": "낮음", "years": years, "outliers": outliers, "r2": 0}
    weights = list(range(1, len(pairs) + 1))
    sw = sum(weights)
    xbar = sum(w * x for w, x in zip(weights, years)) / sw
    ybar = sum(w * y for w, y in zip(weights, values)) / sw
    denominator = sum(w * (x - xbar) ** 2 for w, x in zip(weights, years))
    slope = sum(w * (x - xbar) * (y - ybar) for w, x, y in zip(weights, years, values)) / denominator if denominator else 0
    intercept = ybar - slope * xbar
    fitted = [intercept + slope * x for x in years]
    residuals = [y - fit for y, fit in zip(values, fitted)]
    sse = sum(w * r * r for w, r in zip(weights, residuals))
    sst = sum(w * (y - ybar) ** 2 for w, y in zip(weights, values))
    r2 = 1 - sse / sst if sst else 1.0
    forecast = max(0.0, intercept + slope * (years[-1] + 1))
    rmse = math.sqrt(sse / sw) if sw else 0
    spread = max(rmse * 1.64, abs(slope) * .35)
    confidence = "높음" if len(pairs) >= 5 and r2 >= .75 and not outliers else "보통" if len(pairs) >= 4 and r2 >= .4 else "낮음"
    if outliers and confidence == "높음":
        confidence = "보통"
    return {"value": forecast, "lower": max(0.0, forecast - spread), "upper": forecast + spread,
            "confidence": confidence, "years": years, "outliers": outliers, "r2": max(0.0, min(1.0, r2)), "slope": slope}


def trend_chart_points(forecast):
    """Return fitted history plus the forecast year so a one-value forecast is visible as a line and point."""
    years = list((forecast or {}).get("years") or [])
    value = (forecast or {}).get("value")
    if value is None or not years:
        return []
    target_year = max(years) + 1
    slope = float((forecast or {}).get("slope") or 0)
    return [(year, max(0.0, float(value) - slope * (target_year - year))) for year in years + [target_year]]


def grade_ratio(key, actual, official):
    spec = RATIOS[key]
    if actual is None:
        return {"relative": None, "grade": "-", "score": 0, "judgement": "자료확인"}
    if spec["direction"] == "direct":
        thresholds = spec["thresholds"]
        index = 0 if actual >= thresholds[0] else 1 if actual >= thresholds[1] else 2 if actual >= thresholds[2] else 3
        grade = "ABCD"[index]
        return {"relative": None, "grade": grade, "score": spec["points"][index], "judgement": "양호" if index <= 1 else "보완"}
    if official in (None, 0):
        return {"relative": None, "grade": "-", "score": 0, "judgement": "공시자료확인"}
    relative = actual / official * 100
    thresholds = spec["thresholds"]
    if spec["direction"] == "lower":
        index = 0 if relative < thresholds[0] else 1 if relative < thresholds[1] else 2 if relative < thresholds[2] else 3 if relative < thresholds[3] else 4
    else:
        index = 0 if relative >= thresholds[0] else 1 if relative >= thresholds[1] else 2 if relative >= thresholds[2] else 3 if relative >= thresholds[3] else 4
    grade = "ABCDE"[index]
    return {"relative": relative, "grade": grade, "score": spec["points"][index], "judgement": "양호" if index <= 1 else "보완"}


def evaluation_rows(actual, prior_official, forecasts):
    rows = []
    for key, spec in RATIOS.items():
        current = actual.get(key)
        official = prior_official.get(key) if prior_official else None
        forecast = forecasts.get(key, {})
        grade = grade_ratio(key, current, official)
        rows.append({"key": key, "점검 항목": spec["label"], "당사비율": current, "전년도 기준": official,
                     "예상 업종비율": forecast.get("value"), "예상 하한": forecast.get("lower"), "예상 상한": forecast.get("upper"),
                     "신뢰도": forecast.get("confidence", "자료없음"), "평균대비율": grade["relative"],
                     "등급": grade["grade"], "평점": grade["score"], "판정": grade["judgement"], "계산식": spec["formula"]})
    return rows


def publication_has_values(record):
    return any(value not in (None, 0) for value in (record.get("ratios") or {}).values())


def latest_official_ratios(records):
    """Return the most recent non-zero value for every ratio and its source year."""
    values, years = {}, {}
    ordered = sorted(records, key=lambda row: int(row.get("publication_year") or 0))
    for key in RATIOS:
        source = next((row for row in reversed(ordered) if (row.get("ratios") or {}).get(key) not in (None, 0)), None)
        values[key] = source["ratios"][key] if source else None
        years[key] = int(source["publication_year"]) if source else None
    return values, years


def format_ratio(key, value):
    if value is None:
        return "-"
    unit = RATIOS[key]["unit"]
    precision = 2 if unit in ("%", "배", "회") else 0
    return f"{value:,.{precision}f}{unit}"


REPORT_SOURCES = {
    "debt_ratio": [("부채총계", "debt_total"), ("자기자본", "equity_total")],
    "current_ratio": [("유동자산", "current_assets"), ("유동부채", "current_liabilities")],
    "borrowing_ratio": [("차입금", "borrowings"), ("총자산", "total_assets")],
    "interest_coverage": [("영업이익", "operating_profit"), ("이자비용", "interest_expense")],
    "sales_profit_ratio": [("세전이익", "pre_tax_income"), ("매출액", "sales")],
    "asset_profit_ratio": [("세전이익", "pre_tax_income"), ("총자산", "total_assets")],
    "cash_flow_ratio": [("영업활동현금흐름", "operating_cash_flow"), ("총자산", "total_assets")],
    "asset_turnover": [("매출액", "sales"), ("평균 총자산", "average_assets")],
    "tech_investment_ratio": [("기술개발비", "tech_development"), ("건설매출액", "construction_sales")],
    "business_years": [("설립일", "established_date")],
}


def _criteria(key):
    spec = RATIOS[key]
    if key == "business_years":
        labels = ["A. 10년 이상", "B. 5년 이상", "C. 3년 이상", "D. 3년 미만"]
    elif spec["direction"] == "lower":
        labels = ["A. 50% 미만", "B. 75% 미만", "C. 100% 미만", "D. 125% 미만", "E. 125% 이상"]
    else:
        thresholds = spec["thresholds"]
        labels = [f"{grade}. {threshold:g}% 이상" for grade, threshold in zip("ABCD", thresholds)] + [f"E. {thresholds[-1]:g}% 미만"]
    return list(zip(labels, spec["points"]))


def _source_amounts(values):
    raw = dict(values or {})
    beginning = float(number(raw.get("beginning_assets")) or 0)
    ending = float(number(raw.get("total_assets")) or 0)
    raw["average_assets"] = (beginning + ending) / 2 if beginning and ending else ending
    result = {}
    for key, rows in REPORT_SOURCES.items():
        converted = []
        for label, source_key in rows:
            if source_key == "established_date":
                converted.append((label, str(raw.get(source_key) or "-"), False))
            else:
                converted.append((label, float(number(raw.get(source_key)) or 0) / 1000, True))
        result[key] = converted
    return result


def assessment_blocks(values, actual, prior_official, forecasts, publications):
    """Build the approved company-sheet rows; cash-flow ratio is intentionally absent."""
    sources = _source_amounts(values)
    blocks = []
    for key, spec in RATIOS.items():
        history = [float(r["ratios"][key]) for r in publications[-5:] if r.get("ratios", {}).get(key) not in (None, 0)]
        grade = grade_ratio(key, actual.get(key), (prior_official or {}).get(key))
        blocks.append({
            "key": key, "label": spec["label"], "unit": spec["unit"], "sources": sources[key],
            "five_year_average": None if key == "business_years" else sum(history) / len(history) if history else None,
            "official": (prior_official or {}).get(key), "forecast": None if key == "business_years" else (forecasts.get(key) or {}).get("value"),
            "actual": actual.get(key), "relative": grade["relative"], "grade": grade["grade"],
            "score": grade["score"], "criteria": _criteria(key),
        })
    return blocks


def _excel_ratio(cell, key, value, relative=False):
    if value is None:
        cell.value = "-"
        return
    if relative or RATIOS[key]["unit"] == "%":
        cell.value = float(value) / 100
        cell.number_format = "0.00%"
    elif RATIOS[key]["unit"] == "배":
        cell.value = float(value); cell.number_format = '0.00"배"'
    elif RATIOS[key]["unit"] == "회":
        cell.value = float(value); cell.number_format = '0.00"회"'
    else:
        cell.value = float(value); cell.number_format = '0"년"'


def management_report_workbook(company_name, year, values, actual, prior_official, forecasts, publications, official_year=None):
    blocks = assessment_blocks(values, actual, prior_official, forecasts, publications)
    book = openpyxl.Workbook(); sheet = book.active
    safe_name = re.sub(r"[\\/*?:\[\]]", "", f"{year}.{company_name}")[:31] or "경영상태평가"
    sheet.title = safe_name
    sheet.merge_cells("A1:J1"); sheet["A1"] = f"{year}년 경영상태평가표"
    sheet.merge_cells("A2:B2"); sheet["A2"] = company_name
    sheet.merge_cells("G2:J2"); sheet["G2"] = f"{official_year or year-1}년 공식기준 및 최근 5개년 추세 예상 · 단위: 천원"
    headers = ["심사 항목", "기초 금액", "5개년\n평균", "업체평균율\n전년도 기준", "업체 예상\n평균비율", "당사비율", "평균대비율", "등급 기준", "평점", "해당등급"]
    for col, value in enumerate(headers, 1): sheet.cell(3, col, value)
    thin = Side(style="thin", color="666666"); medium = Side(style="medium", color="555555")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="D9DEDC"); forecast_fill = PatternFill("solid", fgColor="FFF7C7")
    title_fill = PatternFill("solid", fgColor="F4F6F5"); good_fill = PatternFill("solid", fgColor="E5F4EC")
    warn_fill = PatternFill("solid", fgColor="FFF1D6"); bad_fill = PatternFill("solid", fgColor="FDE7E5")
    blue = "175F9F"; orange = "A35A00"; row = 4
    for index, block in enumerate(blocks, 1):
        lines = block["criteria"]; height = len(lines); end = row + height - 1
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        sheet.cell(row, 1, f"{index}. {block['label']}"); sheet.cell(row, 1).fill = title_fill
        for offset, (label, amount, numeric) in enumerate(block["sources"], 1):
            if row + offset > end: break
            sheet.cell(row + offset, 1, label); sheet.cell(row + offset, 2, amount)
            if numeric: sheet.cell(row + offset, 2).number_format = "#,##0"
        for col, key_name in [(3, "five_year_average"), (4, "official"), (5, "forecast"), (6, "actual"), (7, "relative"), (10, "grade")]:
            sheet.merge_cells(start_row=row, start_column=col, end_row=end, end_column=col)
            cell = sheet.cell(row, col)
            if key_name == "grade":
                cell.value = block[key_name]
                cell.font = Font(name="맑은 고딕", size=13, bold=True, color="087A4F" if block[key_name] in ("A", "B") else "A35A00" if block[key_name] == "C" else "B42318")
                cell.fill = good_fill if block[key_name] in ("A", "B") else warn_fill if block[key_name] == "C" else bad_fill
            else:
                _excel_ratio(cell, block["key"], block[key_name], relative=key_name == "relative")
                cell.font = Font(name="맑은 고딕", size=9, color=orange if col == 5 else blue)
                if col == 5: cell.fill = forecast_fill
        for offset, (label, points) in enumerate(lines):
            sheet.cell(row + offset, 8, label); sheet.cell(row + offset, 9, points)
            sheet.cell(row + offset, 9).number_format = "0.0"
        for r in range(row, end + 1):
            for c in range(1, 11):
                cell = sheet.cell(r, c); cell.border = border
                cell.alignment = Alignment(horizontal="right" if c in (2,3,4,5,6,7,9) else "center", vertical="center", wrap_text=True)
                if c in (2,3,4,6,7,9) and not cell.font.color: cell.font = Font(name="맑은 고딕", size=9, color=blue)
            sheet.row_dimensions[r].height = 14
        for c in range(1, 11): sheet.cell(row, c).border = Border(left=sheet.cell(row,c).border.left, right=sheet.cell(row,c).border.right, top=medium, bottom=sheet.cell(row,c).border.bottom)
        row = end + 1
    total = sum(float(block["score"] or 0) for block in blocks)
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8); sheet.cell(row, 1, "※ 업체 예상평균비율은 최근 최대 5개년 최근연도 가중 추세 및 이상치 보정값입니다.")
    sheet.cell(row, 9, "총 평점"); sheet.cell(row, 10, total); sheet.cell(row, 10).number_format = "0.0\"점\""
    for c in range(1, 11): sheet.cell(row,c).border=border; sheet.cell(row,c).alignment=Alignment(horizontal="right" if c>=9 else "left",vertical="center")
    sheet["A1"].font = Font(name="맑은 고딕", size=16, bold=True); sheet["A1"].alignment = Alignment(horizontal="center")
    sheet["A2"].font = Font(name="맑은 고딕", size=11, bold=True); sheet["G2"].alignment = Alignment(horizontal="right")
    for cell in sheet[3]: cell.fill=header_fill; cell.border=border; cell.font=Font(name="맑은 고딕",size=9,bold=True); cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
    sheet["E3"].fill = PatternFill("solid", fgColor="FFF3A2"); sheet.row_dimensions[3].height = 28
    widths=[18,14,11,12,13,11,12,17,8,10]
    for i,width in enumerate(widths,1): sheet.column_dimensions[get_column_letter(i)].width=width
    sheet.sheet_view.showGridLines=False; sheet.freeze_panes="A4"; sheet.print_area=f"A1:J{row}"; sheet.print_options.horizontalCentered=True
    sheet.page_setup.orientation="landscape"; sheet.page_setup.paperSize=sheet.PAPERSIZE_A4; sheet.page_setup.fitToWidth=1; sheet.page_setup.fitToHeight=1
    sheet.sheet_properties.pageSetUpPr.fitToPage=True; sheet.page_margins.left=.2; sheet.page_margins.right=.2; sheet.page_margins.top=.3; sheet.page_margins.bottom=.3
    output=BytesIO(); book.save(output); return output.getvalue()


def management_report_html(company_name, year, values, actual, prior_official, forecasts, publications, official_year=None):
    blocks = assessment_blocks(values, actual, prior_official, forecasts, publications)
    rows=[]
    for index, block in enumerate(blocks,1):
        criteria=block["criteria"]; height=len(criteria); sources=list(block["sources"])
        for offset,(label,points) in enumerate(criteria):
            cells=[]
            if offset==0: cells.append(f'<td colspan="2" class="name">{index}. {escape(block["label"])}</td>')
            else:
                source=sources[offset-1] if offset-1<len(sources) else ("","",False)
                amount=f'{source[1]:,.0f}' if source[2] else escape(str(source[1]))
                cells.append(f'<td class="source">{escape(source[0])}</td><td class="money">{amount}</td>')
            if offset==0:
                values_to_show=[block["five_year_average"],block["official"],block["forecast"],block["actual"],block["relative"]]
                for position,value in enumerate(values_to_show):
                    shown=(f'{value:,.2f}%' if position==4 and value is not None else format_ratio(block["key"],value))
                    cells.append(f'<td rowspan="{height}" class="ratio {"forecast" if position==2 else ""}">{escape(shown)}</td>')
            cells.append(f'<td>{escape(label)}</td><td class="money blue">{points:.1f}</td>')
            if offset==0: cells.append(f'<td rowspan="{height}" class="actual-grade grade-{escape(str(block["grade"]).lower())}">{escape(str(block["grade"]))}</td>')
            rows.append(f'<tr class="{"group" if offset==0 else ""}">{"".join(cells)}</tr>')
    total=sum(float(block["score"] or 0) for block in blocks)
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{escape(str(year))}년 {escape(company_name)} 경영상태평가표</title><style>
    @page{{size:A4 landscape;margin:6mm}}*{{box-sizing:border-box}}body{{font-family:"Malgun Gothic",sans-serif;color:#111;margin:0}}button{{margin-bottom:6px;padding:5px 10px}}h1{{font-size:18px;text-align:center;margin:0 0 6px}}.meta{{display:flex;justify-content:space-between;font-size:10px;margin-bottom:5px}}table{{border-collapse:collapse;width:100%;table-layout:fixed;font-size:8px}}th,td{{border:1px solid #555;padding:2px 3px;height:13px;text-align:center}}th{{background:#d9dedc}}th.expected{{background:#fff3a2}}td.name{{background:#f4f6f5;text-align:left;font-weight:bold}}td.source{{text-align:left;padding-left:8px}}td.money,td.ratio{{text-align:right;color:#175f9f;font-variant-numeric:tabular-nums}}td.forecast{{background:#fffbe0;color:#a35a00;font-weight:bold}}tr.group td{{border-top-width:2px}}.actual-grade{{font-size:12px;font-weight:bold}}.grade-a,.grade-b{{background:#e5f4ec;color:#087a4f}}.grade-c{{background:#fff1d6;color:#a35a00}}.grade-d,.grade-e{{background:#fde7e5;color:#b42318}}.foot{{display:flex;justify-content:space-between;font-size:8px;margin-top:4px}}@media print{{button{{display:none}}}}
    </style></head><body><button onclick="window.print()">인쇄·PDF 저장</button><h1>{year}년 경영상태평가표</h1><div class="meta"><b>{escape(company_name)}</b><span>{official_year or year-1}년 공식기준 및 최근 5개년 추세 예상 · 단위: 천원</span></div><table><colgroup>{''.join(f'<col style="width:{w}%">' for w in [15,11,9,9,10,9,9,13,7,8])}</colgroup><thead><tr><th>심사 항목</th><th>기초 금액</th><th>5개년<br>평균</th><th>업체평균율<br>전년도 기준</th><th class="expected">업체 예상<br>평균비율</th><th>당사비율</th><th>평균대비율</th><th>등급 기준</th><th>평점</th><th>해당등급</th></tr></thead><tbody>{''.join(rows)}</tbody></table><div class="foot"><span>※ 업체 예상평균비율은 최근 최대 5개년 최근연도 가중 추세 및 이상치 보정값입니다.</span><b>총 평점 {total:,.1f}점</b></div></body></html>'''.encode("utf-8")
