"""Persistence and import helpers for receivable/payable confirmations."""
import csv
import io
import json
import re
import secrets
import sqlite3
from datetime import date

import pandas as pd

import collaboration as shared


SIDES = ('채권', '채무', '미분류')
STATUS_ORDER = {'작성 중': 0, '발송 준비': 1, '서버 접수': 2, '회신 수신': 3, '차이 검토': 4, '확인 완료': 5}
RECEIVABLE_WORDS = ('공사미수금', '외상매출금', '받을어음', '미수금', '미수수익', '대여금', '보증금', '선급금')
PAYABLE_WORDS = ('외상매입금', '지급어음', '미지급금', '미지급비용', '차입금', '예수금', '선수금', '보증금예수')


def rows(c, sql, args=()):
    cur = c.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur]


def clean(value, limit=250):
    value = '' if value is None else str(value).strip()
    if len(value) > limit or any(ord(ch) < 32 and ch not in '\n\t' for ch in value):
        raise ValueError('입력값의 길이 또는 제어문자를 확인하세요.')
    return value


def normalized(value):
    return ''.join(ch for ch in str(value or '').casefold() if ch.isalnum())


def amount(value):
    if value is None or value == '':
        return 0
    try:
        if pd.isna(value):
            return 0
    except (TypeError, ValueError):
        pass
    text = str(value).strip().replace(',', '').replace('원', '').replace('₩', '')
    negative = text.startswith('(') and text.endswith(')')
    text = text.strip('()')
    try:
        result = int(round(float(text or 0)))
    except (ValueError, TypeError):
        raise ValueError(f'금액을 확인하세요: {value}')
    return -result if negative else result


def infer_side(account, debit=0, credit=0):
    key = normalized(account)
    if any(normalized(word) in key for word in RECEIVABLE_WORDS):
        return '채권'
    if any(normalized(word) in key for word in PAYABLE_WORDS):
        return '채무'
    if abs(amount(debit)) > abs(amount(credit)):
        return '채권'
    if abs(amount(credit)) > abs(amount(debit)):
        return '채무'
    return '미분류'


def connect():
    shared.DATA.mkdir(parents=True, exist_ok=True)
    c = shared.connect(shared.DATA / 'balance_confirmation.db')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS bc_profiles(
      company_name TEXT PRIMARY KEY,business_no TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',
      company_contact TEXT NOT NULL DEFAULT '',company_phone TEXT NOT NULL DEFAULT '',company_email TEXT NOT NULL DEFAULT '',
      audit_firm TEXT NOT NULL DEFAULT '',auditor_name TEXT NOT NULL DEFAULT '',auditor_phone TEXT NOT NULL DEFAULT '',
      auditor_email TEXT NOT NULL DEFAULT '',auditor_address TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS bc_audit_profile(
      id INTEGER PRIMARY KEY CHECK(id=1),audit_firm TEXT NOT NULL DEFAULT '',auditor_name TEXT NOT NULL DEFAULT '',
      auditor_phone TEXT NOT NULL DEFAULT '',auditor_email TEXT NOT NULL DEFAULT '',auditor_address TEXT NOT NULL DEFAULT '',
      version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS bc_counterparties(
      id INTEGER PRIMARY KEY,company_name TEXT NOT NULL,year INTEGER NOT NULL,counterparty TEXT NOT NULL,
      business_no TEXT NOT NULL DEFAULT '',balance_side TEXT NOT NULL,account TEXT NOT NULL,balance INTEGER NOT NULL,
      contact_name TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',
      address TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT '직접 입력',
      version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,
      UNIQUE(company_name,year,counterparty,account));
    CREATE INDEX IF NOT EXISTS bc_counterparty_case ON bc_counterparties(company_name,year,deleted);
    CREATE TABLE IF NOT EXISTS bc_imports(
      id INTEGER PRIMARY KEY,company_name TEXT NOT NULL,year INTEGER NOT NULL,filename TEXT NOT NULL,
      digest TEXT NOT NULL,row_count INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(company_name,year,digest));
    CREATE TABLE IF NOT EXISTS bc_dispatches(
      id INTEGER PRIMARY KEY,confirmation_no TEXT NOT NULL UNIQUE,company_name TEXT NOT NULL,year INTEGER NOT NULL,
      base_date TEXT NOT NULL,counterparty TEXT NOT NULL,recipient_email TEXT NOT NULL DEFAULT '',
      lines_json TEXT NOT NULL,total_balance INTEGER NOT NULL,status TEXT NOT NULL DEFAULT '작성 중',
      mail_job_id TEXT NOT NULL DEFAULT '',message_id TEXT NOT NULL DEFAULT '',sent_at TEXT NOT NULL DEFAULT '',
      replied_at TEXT NOT NULL DEFAULT '',reply_source TEXT NOT NULL DEFAULT '',reply_uid TEXT NOT NULL DEFAULT '',
      reply_from TEXT NOT NULL DEFAULT '',reply_subject TEXT NOT NULL DEFAULT '',balance_match TEXT NOT NULL DEFAULT '미판정',
      reply_note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,
      UNIQUE(company_name,year,counterparty));
    CREATE INDEX IF NOT EXISTS bc_dispatch_case ON bc_dispatches(company_name,year,status);
    ''')
    if not c.execute('SELECT 1 FROM bc_audit_profile WHERE id=1').fetchone():
        old = c.execute("""SELECT audit_firm,auditor_name,auditor_phone,auditor_email,auditor_address FROM bc_profiles
          WHERE audit_firm<>'' OR auditor_email<>'' ORDER BY company_name LIMIT 1""").fetchone()
        if old: c.execute('INSERT INTO bc_audit_profile VALUES(1,?,?,?,?,?,1)', tuple(old))
        else: c.execute('INSERT INTO bc_audit_profile(id) VALUES(1)')
    c.commit()
    return shared.protect(c)


def company_names():
    try:
        import corporate_close_store as corporate
        c = corporate.connect()
        try:
            result = [r['name'] for r in corporate.companies(c)]
        finally:
            c.close()
        if result:
            return result
    except Exception:
        pass
    return ['다혜건설㈜', '㈜효성', '㈜효성전문', '㈜한길', '㈜효성엘비데크']


def profile(c, company_name):
    row = c.execute('SELECT * FROM bc_profiles WHERE company_name=?', (company_name,)).fetchone()
    fields = ('company_name', 'business_no', 'address', 'company_contact', 'company_phone', 'company_email',
              'audit_firm', 'auditor_name', 'auditor_phone', 'auditor_email', 'auditor_address', 'version')
    result = dict(zip(fields, row)) if row else dict(company_name=company_name, business_no='', address='',
        company_contact='', company_phone='', company_email='', audit_firm='', auditor_name='', auditor_phone='',
        auditor_email='', auditor_address='', version=0)
    audit = c.execute('SELECT audit_firm,auditor_name,auditor_phone,auditor_email,auditor_address,version FROM bc_audit_profile WHERE id=1').fetchone()
    if audit:
        for key, value in zip(('audit_firm','auditor_name','auditor_phone','auditor_email','auditor_address','audit_version'), audit): result[key] = value
    else: result['audit_version'] = 0
    return result


def save_profile(c, company_name, values, expected, audit_expected=None):
    from mail_service import address as valid_email
    current = profile(c, company_name)
    if current['version'] != int(expected):
        raise ValueError('회계법인 정보가 다른 작업자에 의해 변경되었습니다. 다시 불러오세요.')
    if audit_expected is not None and current['audit_version'] != int(audit_expected):
        raise ValueError('공통 공인회계법인 정보가 다른 작업자에 의해 변경되었습니다. 다시 불러오세요.')
    data = {k: clean(values.get(k, ''), 500 if 'address' in k else 250) for k in
            ('business_no', 'address', 'company_contact', 'company_phone', 'company_email', 'audit_firm',
             'auditor_name', 'auditor_phone', 'auditor_email', 'auditor_address')}
    for key in ('company_email', 'auditor_email'):
        if data[key]:
            data[key] = valid_email(data[key])
    with c:
        if current['version']:
            c.execute('''UPDATE bc_profiles SET business_no=?,address=?,company_contact=?,company_phone=?,company_email=?,
              audit_firm=?,auditor_name=?,auditor_phone=?,auditor_email=?,auditor_address=?,version=version+1
              WHERE company_name=? AND version=?''', tuple(data[k] for k in data) + (company_name, expected))
        else:
            c.execute('''INSERT INTO bc_profiles(company_name,business_no,address,company_contact,company_phone,company_email,
              audit_firm,auditor_name,auditor_phone,auditor_email,auditor_address) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
              (company_name,) + tuple(data[k] for k in data))
        c.execute('''UPDATE bc_audit_profile SET audit_firm=?,auditor_name=?,auditor_phone=?,auditor_email=?,
          auditor_address=?,version=version+1 WHERE id=1''', tuple(data[k] for k in
          ('audit_firm','auditor_name','auditor_phone','auditor_email','auditor_address')))


def joint_companies():
    """Return every reusable joint-venture company field; missing values stay editable."""
    try:
        import joint_store
        c = joint_store.connect()
        try:
            result=[]
            for row in joint_store.companies(c):
                try: info=json.loads(row.get('info') or '{}')
                except (TypeError,json.JSONDecodeError): info={}
                email=c.execute('''SELECT e.email FROM jv_member_emails e JOIN jv_members m ON m.id=e.member_id
                  WHERE m.company_id=? AND TRIM(e.email)<>'' ORDER BY e.member_id DESC LIMIT 1''',(row['id'],)).fetchone()
                result.append({'name':row['name'],'code':row['code'],'business_no':info.get('사업자등록번호',''),
                  'contact_name':info.get('담당자',''),'email':email[0] if email else '',
                  'phone':info.get('담당자 연락처') or info.get('전화',''),'address':info.get('주소','')})
            return result
        finally: c.close()
    except Exception:
        return []


def counterparties(c, company_name, year, include_deleted=False):
    sql = 'SELECT * FROM bc_counterparties WHERE company_name=? AND year=?'
    args = [company_name, int(year)]
    if not include_deleted:
        sql += ' AND deleted=0'
    sql += ' ORDER BY counterparty,account,id'
    return rows(c, sql, args)


def _validated_record(row, company_name, year):
    from mail_service import address as valid_email
    counterparty = clean(row.get('거래처명', row.get('counterparty', '')), 200)
    account = clean(row.get('계정과목', row.get('account', '')), 200)
    if not counterparty or not account:
        raise ValueError('거래처명과 계정과목은 반드시 입력하세요.')
    side = clean(row.get('구분', row.get('balance_side', '미분류')), 20) or '미분류'
    if side not in SIDES:
        raise ValueError(f'{counterparty}의 구분은 채권·채무·미분류 중에서 선택하세요.')
    email = clean(row.get('메일주소', row.get('email', '')), 254)
    if email:
        email = valid_email(email)
    return dict(company_name=company_name, year=int(year), counterparty=counterparty,
        business_no=clean(row.get('사업자번호', row.get('business_no', '')), 50), balance_side=side,
        account=account, balance=abs(amount(row.get('채권채무 잔액', row.get('balance', 0)))),
        contact_name=clean(row.get('담당자명', row.get('contact_name', '')), 100), email=email,
        phone=clean(row.get('연락처', row.get('phone', '')), 100), address=clean(row.get('주소', row.get('address', '')), 500),
        note=clean(row.get('비고', row.get('note', '')), 500), source=clean(row.get('source', '직접 입력'), 250))


def save_counterparty_rows(c, company_name, year, records, remove_ids=()):
    clean_rows = [_validated_record(row, company_name, year) for row in records]
    with c:
        for row in clean_rows:
            existing = c.execute('''SELECT id FROM bc_counterparties WHERE company_name=? AND year=? AND counterparty=? AND account=?''',
                                 (company_name, int(year), row['counterparty'], row['account'])).fetchone()
            values = tuple(row[k] for k in ('business_no', 'balance_side', 'balance', 'contact_name', 'email', 'phone', 'address', 'note', 'source'))
            if existing:
                if row['source'].startswith('아마란스'):
                    c.execute('''UPDATE bc_counterparties SET balance_side=?,balance=?,source=?,deleted=0,version=version+1 WHERE id=?''',
                              (row['balance_side'], row['balance'], row['source'], existing[0]))
                else:
                    c.execute('''UPDATE bc_counterparties SET business_no=?,balance_side=?,balance=?,contact_name=?,email=?,phone=?,
                      address=?,note=?,source=?,deleted=0,version=version+1 WHERE id=?''', values + (existing[0],))
            else:
                c.execute('''INSERT INTO bc_counterparties(company_name,year,counterparty,business_no,balance_side,account,balance,
                  contact_name,email,phone,address,note,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (company_name, int(year), row['counterparty'], row['business_no'], row['balance_side'], row['account'], row['balance'],
                   row['contact_name'], row['email'], row['phone'], row['address'], row['note'], row['source']))
        ids = [int(x) for x in remove_ids if str(x).isdigit()]
        if ids:
            placeholders = ','.join('?' for _ in ids)
            c.execute(f'UPDATE bc_counterparties SET deleted=1,version=version+1 WHERE company_name=? AND year=? AND id IN ({placeholders})',
                      (company_name, int(year), *ids))


def save_counterparty_record(c, company_name, year, values, id=None, expected=None):
    row = _validated_record(values, company_name, year)
    row['source'] = '공동도급 업체명 불러오기' if values.get('joint_lookup') else '직접 입력'
    data = tuple(row[k] for k in ('counterparty','business_no','balance_side','account','balance','contact_name','email','phone','address','note','source'))
    try:
        with c:
            if id:
                current = c.execute('SELECT company_name,year,version FROM bc_counterparties WHERE id=? AND deleted=0', (int(id),)).fetchone()
                if not current or current[0] != company_name or current[1] != int(year): raise ValueError('수정할 계정 자료를 찾을 수 없습니다.')
                if expected is not None and current[2] != int(expected): raise ValueError('다른 작업자가 이 계정을 수정했습니다. 다시 불러오세요.')
                c.execute('''UPDATE bc_counterparties SET counterparty=?,business_no=?,balance_side=?,account=?,balance=?,contact_name=?,
                  email=?,phone=?,address=?,note=?,source=?,version=version+1 WHERE id=?''', data + (int(id),))
                return int(id)
            return c.execute('''INSERT INTO bc_counterparties(company_name,year,counterparty,business_no,balance_side,account,balance,
              contact_name,email,phone,address,note,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (company_name,int(year),row['counterparty'],row['business_no'],row['balance_side'],row['account'],row['balance'],
               row['contact_name'],row['email'],row['phone'],row['address'],row['note'],row['source'])).lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError('같은 거래처와 계정과목이 이미 등록되어 있습니다. 기존 항목을 선택해 수정하세요.') from exc


def delete_counterparty(c, company_name, year, id, expected, reason):
    reason = clean(reason, 500)
    if not reason: raise ValueError('삭제 사유를 입력하세요.')
    with c:
        changed = c.execute('''UPDATE bc_counterparties SET deleted=1,note=CASE WHEN note='' THEN ? ELSE note||' / 삭제: '||? END,
          version=version+1 WHERE id=? AND company_name=? AND year=? AND version=? AND deleted=0''',
          (reason,reason,int(id),company_name,int(year),int(expected))).rowcount
        if changed != 1: raise ValueError('계정 자료가 변경되었거나 이미 삭제되었습니다. 다시 불러오세요.')


ALIASES = {
    '거래처명': ('거래처명', '회사명', '업체명', '거래처', '상호', '상호명'),
    '사업자번호': ('사업자번호', '사업자등록번호', '등록번호'),
    '계정과목': ('계정과목', '계정명', '계정과목명'),
    '구분': ('구분', '채권채무구분', '채권채무'),
    '채권잔액': ('채권잔액', '채권금액'), '채무잔액': ('채무잔액', '채무금액'),
    '채권채무 잔액': ('채권채무잔액', '잔액', '기말잔액', '확인잔액'),
    '차변잔액': ('차변잔액', '차변'), '대변잔액': ('대변잔액', '대변'),
    '담당자명': ('담당자명', '담당자', '거래처담당자'),
    '메일주소': ('메일주소', '이메일', '이메일주소', 'email'),
    '연락처': ('연락처', '전화번호', '전화', '핸드폰'), '주소': ('주소', '소재지'), '비고': ('비고', '메모')}


def _column_map(columns):
    normalized_columns = {normalized(col): col for col in columns}
    result = {}
    for target, aliases in ALIASES.items():
        for alias in aliases:
            key = normalized(alias)
            if key in normalized_columns:
                result[target] = normalized_columns[key]
                break
    return result


def parse_upload(filename, payload):
    name = str(filename).lower()
    if name.endswith('.csv'):
        last = None
        for encoding in ('utf-8-sig', 'cp949', 'euc-kr'):
            try:
                frame = pd.read_csv(io.BytesIO(payload), encoding=encoding)
                break
            except UnicodeDecodeError as exc:
                last = exc
        else:
            raise ValueError('CSV 문자 인코딩을 확인하세요.') from last
    elif name.endswith(('.xlsx', '.xlsm')):
        frame = pd.read_excel(io.BytesIO(payload), dtype=object)
    else:
        raise ValueError('아마란스 자료는 XLSX 또는 CSV 파일로 올려주세요.')
    frame = frame.dropna(how='all').copy()
    mapping = _column_map(frame.columns)
    missing = [key for key in ('거래처명', '계정과목') if key not in mapping]
    if not any(key in mapping for key in ('채권잔액','채무잔액','채권채무 잔액','차변잔액','대변잔액')): missing.append('채권잔액')
    if missing:
        raise ValueError('필수 열을 찾지 못했습니다: ' + ', '.join(missing))
    result = []
    for _, source in frame.iterrows():
        counterparty = source.get(mapping['거래처명'])
        account = source.get(mapping['계정과목'])
        if pd.isna(counterparty) or pd.isna(account) or not str(counterparty).strip() or not str(account).strip():
            continue
        debit = amount(source.get(mapping.get('차변잔액'))) if mapping.get('차변잔액') else 0
        credit = amount(source.get(mapping.get('대변잔액'))) if mapping.get('대변잔액') else 0
        if mapping.get('채권잔액'):
            side = '채권'; balance = abs(amount(source.get(mapping['채권잔액'])))
        elif mapping.get('채무잔액'):
            side = '채무'; balance = abs(amount(source.get(mapping['채무잔액'])))
        else:
            raw_side = source.get(mapping.get('구분')) if mapping.get('구분') else ''
            side = str(raw_side).strip() if not pd.isna(raw_side) else ''
            if side not in SIDES: side = infer_side(account, debit, credit)
        if not mapping.get('채권잔액') and not mapping.get('채무잔액') and mapping.get('채권채무 잔액'):
            balance = abs(amount(source.get(mapping['채권채무 잔액'])))
        elif not mapping.get('채권잔액') and not mapping.get('채무잔액') and not mapping.get('채권채무 잔액'):
            balance = abs(debit - credit)
        row = {'거래처명': str(counterparty).strip(), '계정과목': str(account).strip(), '구분': side,
               '채권채무 잔액': balance, 'source': f'아마란스 · {filename}'}
        for target in ('사업자번호', '담당자명', '메일주소', '연락처', '주소', '비고'): row[target] = ''
        result.append(row)
    if not result:
        raise ValueError('등록할 거래처 잔액 자료가 없습니다.')
    return result


def group_counterparties(c, company_name, year):
    grouped = {}
    for row in counterparties(c, company_name, year):
        group = grouped.setdefault(row['counterparty'], {'counterparty': row['counterparty'], 'business_no': row['business_no'],
            'contact_name': row['contact_name'], 'email': row['email'], 'phone': row['phone'], 'address': row['address'],
            'lines': [], 'total': 0, 'side': row['balance_side'], 'needs_review': False})
        for field in ('business_no', 'contact_name', 'email', 'phone', 'address'):
            if not group[field] and row[field]:
                group[field] = row[field]
        group['lines'].append({'account': row['account'], 'side': row['balance_side'], 'balance': row['balance'], 'note': row['note']})
        group['total'] += row['balance']
        if row['balance_side'] == '미분류' or (group['side'] != row['balance_side'] and row['balance_side'] != '미분류'):
            group['needs_review'] = True
            group['side'] = '혼합'
    return list(grouped.values())


def _next_confirmation_no(c, year):
    prefix = f'CF-{int(year)}-'
    nums = []
    for row in c.execute('SELECT confirmation_no FROM bc_dispatches WHERE confirmation_no LIKE ?', (prefix + '%',)):
        match = re.fullmatch(re.escape(prefix) + r'(\d+)', row[0])
        if match:
            nums.append(int(match.group(1)))
    return prefix + f'{max(nums, default=0) + 1:04d}'


def prepare_dispatch(c, company_name, year, base_date, group):
    existing = c.execute('SELECT * FROM bc_dispatches WHERE company_name=? AND year=? AND counterparty=?',
                         (company_name, int(year), group['counterparty'])).fetchone()
    lines_json = json.dumps(group['lines'], ensure_ascii=False)
    with c:
        if existing:
            if existing['status'] in ('작성 중', '발송 준비'):
                c.execute('''UPDATE bc_dispatches SET base_date=?,recipient_email=?,lines_json=?,total_balance=?,status='발송 준비',
                  version=version+1 WHERE id=?''', (str(base_date), group['email'], lines_json, group['total'], existing['id']))
            return dispatch(c, existing['id'])
        number = _next_confirmation_no(c, year)
        id = c.execute('''INSERT INTO bc_dispatches(confirmation_no,company_name,year,base_date,counterparty,recipient_email,
          lines_json,total_balance,status) VALUES(?,?,?,?,?,?,?,?, '발송 준비')''',
          (number, company_name, int(year), str(base_date), group['counterparty'], group['email'], lines_json, group['total'])).lastrowid
    return dispatch(c, id)


def dispatch(c, id):
    result = rows(c, 'SELECT * FROM bc_dispatches WHERE id=?', (int(id),))
    if not result:
        raise ValueError('확인서 발송 자료를 찾을 수 없습니다.')
    result[0]['lines'] = json.loads(result[0]['lines_json'])
    return result[0]


def dispatches(c, company_name, year):
    result = rows(c, 'SELECT * FROM bc_dispatches WHERE company_name=? AND year=? ORDER BY confirmation_no', (company_name, int(year)))
    for row in result:
        row['lines'] = json.loads(row['lines_json'])
    return result


def mark_sent(c, id, job_id, message_id, status):
    mapped = '서버 접수' if status in ('서버 접수', '일부 서버 접수', '접수 확인 필요') else status
    with c:
        c.execute('''UPDATE bc_dispatches SET mail_job_id=?,message_id=?,status=?,sent_at=CURRENT_TIMESTAMP,version=version+1 WHERE id=?''',
                  (job_id, message_id or '', mapped, int(id)))


def mark_reply(c, id, source, reply_uid='', reply_from='', reply_subject='', replied_at='', balance_match='미판정', note=''):
    if balance_match not in ('미판정', '일치', '차이 있음'):
        raise ValueError('잔액 판정값을 확인하세요.')
    status = '확인 완료' if balance_match == '일치' else ('차이 검토' if balance_match == '차이 있음' else '회신 수신')
    with c:
        c.execute('''UPDATE bc_dispatches SET replied_at=?,reply_source=?,reply_uid=?,reply_from=?,reply_subject=?,
          balance_match=?,reply_note=?,status=?,version=version+1 WHERE id=?''',
          (replied_at or date.today().isoformat(), clean(source, 100), clean(reply_uid, 250), clean(reply_from, 254),
           clean(reply_subject, 500), balance_match, clean(note, 1000), status, int(id)))


def match_inbox(c, company_name, year, messages):
    candidates = dispatches(c, company_name, year)
    matched = []
    for message in messages:
        subject = str(message.get('subject', ''))
        references = ' '.join(str(message.get(k, '')) for k in ('in_reply_to', 'references'))
        found = None
        for row in candidates:
            if row['confirmation_no'] in subject or (row['message_id'] and row['message_id'] in references):
                found = row
                break
        if not found or found['replied_at']:
            continue
        mark_reply(c, found['id'], '네이트 IMAP 자동 연결', message.get('uid', ''), message.get('from', ''),
                   subject, message.get('date_iso', ''))
        matched.append(found['confirmation_no'])
    return matched


def summary(c, company_name, year):
    groups = group_counterparties(c, company_name, year)
    result = {'parties': len(groups), 'missing_email': sum(not g['email'] for g in groups), 'receivable': 0, 'payable': 0,
              'sent': 0, 'replied': 0}
    for group in groups:
        for line in group['lines']:
            if line['side'] == '채권': result['receivable'] += line['balance']
            elif line['side'] == '채무': result['payable'] += line['balance']
    for row in dispatches(c, company_name, year):
        if row['sent_at']: result['sent'] += 1
        if row['replied_at']: result['replied'] += 1
    return result
