"""WEHAGO business-promotion expense statement calculations.

The six uploaded ledgers determine the account amount and the cost/selling
division.  Evidence-specific fields remain editable because a ledger title or
description alone cannot prove private use, foreign-region use, or whether a
remittance statement was submitted.
"""

FIELDS = [
    'private',
    'condolence_unused', 'condolence_total',
    'foreign_unused', 'foreign_total',
    'farmer_unsubmitted', 'farmer_total',
    'general_unused', 'general_total',
    'culture', 'traditional_market', 'local_gift',
]


def transaction_amount(row):
    """Use debit turnover, never a running balance."""
    value = row.get('debit')
    if value is None:
        value = row.get('amount', 0)
    return int(value or 0)


def division(kind):
    return '도' if str(kind).endswith(',원가)') else '판'


def automatic_values(kind, amount, condolence_threshold=200000, general_threshold=30000):
    """Conservative defaults that the worker can correct per transaction."""
    kind = str(kind)
    amount = int(amount or 0)
    condolence = '경조사비' in kind and abs(amount) > int(condolence_threshold)
    general = '경조사비' not in kind and abs(amount) > int(general_threshold)
    undocumented = '기타접대비' in kind
    return {
        'private': 0,
        'condolence_unused': amount if condolence else 0,
        'condolence_total': amount if condolence else 0,
        'foreign_unused': 0,
        'foreign_total': 0,
        'farmer_unsubmitted': 0,
        'farmer_total': 0,
        'general_unused': amount if general and undocumented else 0,
        'general_total': amount if general else 0,
        'culture': 0,
        'traditional_market': 0,
        'local_gift': 0,
    }


def build_rows(ledger_rows, overrides=None, condolence_threshold=200000, general_threshold=30000):
    overrides = overrides or {}
    out = []
    for source in ledger_rows:
        amount = transaction_amount(source)
        values = automatic_values(source.get('kind', ''), amount, condolence_threshold, general_threshold)
        saved = overrides.get(str(source.get('id')), {})
        for field in FIELDS:
            if field in saved:
                values[field] = int(saved.get(field) or 0)
        out.append({
            'id': int(source.get('id')),
            'kind': source.get('kind', ''),
            'division': division(source.get('kind', '')),
            'date': source.get('posting_date', ''),
            'counterparty': source.get('counterparty', ''),
            'description': source.get('description', ''),
            'source_name': source.get('source_name', ''),
            'amount': amount,
            **values,
        })
    return out


def overrides_from_rows(rows):
    return {
        str(row['id']): {field: int(row.get(field) or 0) for field in FIELDS}
        for row in rows
    }


def _triple(rows, field):
    pan = sum(int(row.get(field) or 0) for row in rows if row['division'] == '판')
    do = sum(int(row.get(field) or 0) for row in rows if row['division'] == '도')
    return {'합계': pan + do, '판': pan, '도': do}


def summary(rows):
    account = _triple(rows, 'amount')
    private = _triple(rows, 'private')
    condolence_unused = _triple(rows, 'condolence_unused')
    condolence_total = _triple(rows, 'condolence_total')
    foreign_unused = _triple(rows, 'foreign_unused')
    foreign_total = _triple(rows, 'foreign_total')
    farmer_unsubmitted = _triple(rows, 'farmer_unsubmitted')
    farmer_total = _triple(rows, 'farmer_total')
    general_unused = _triple(rows, 'general_unused')
    general_total = _triple(rows, 'general_total')
    culture = _triple(rows, 'culture')
    traditional = _triple(rows, 'traditional_market')
    local_gift = _triple(rows, 'local_gift')

    def subtract(a, b):
        return {key: a[key] - b[key] for key in ['합계', '판', '도']}

    def add(*items):
        return {key: sum(item[key] for item in items) for key in ['합계', '판', '도']}

    unused_disallowance = add(condolence_unused, foreign_unused, farmer_unsubmitted, general_unused)
    disallowance = add(private, unused_disallowance)
    return [
        ('⑤ 계정금액', account),
        ('⑥ 기업업무추진비 계상액 중 사적사용 경비', private),
        ('⑦ 기업업무추진비 해당금액 (⑤-⑥)', subtract(account, private)),
        ('경조사비 중 기준금액 초과액', None),
        ('⑨ 신용카드 등 미사용금액', condolence_unused),
        ('⑩ 총 초과금액', condolence_total),
        ('국외지역 지출액', None),
        ('⑪ 신용카드 등 미사용금액', foreign_unused),
        ('⑫ 총 지출액', foreign_total),
        ('농어민 지출액', None),
        ('⑬ 송금명세서 미제출금액', farmer_unsubmitted),
        ('⑭ 총 지출액', farmer_total),
        ('기업업무추진비 중 기준금액 초과액', None),
        ('⑮ 신용카드 등 미사용금액', general_unused),
        ('⑯ 총 초과금액', general_total),
        ('⑰ 신용카드 등 미사용 부인액 (⑨+⑪+⑬+⑮)', unused_disallowance),
        ('⑱ 기업업무추진비 부인액 (⑥+⑰)', disallowance),
        ('문화사업 기업업무추진비', culture),
        ('전통시장 기업업무추진비', traditional),
        ('지역사랑상품권 기업업무추진비', local_gift),
    ]


def validate(rows):
    errors = []
    for row in rows:
        amount = abs(int(row.get('amount') or 0))
        for field in FIELDS:
            value = int(row.get(field) or 0)
            if abs(value) > amount:
                errors.append(f"ID {row['id']}의 {field} 금액 {value:,}원이 차변금액 {row['amount']:,}원을 초과합니다.")
    return errors
