"""Account/evidence allocation matrix following the uploaded Excel layout."""
from decimal import Decimal,ROUND_FLOOR
from html import escape
import re
import joint_store as db

BUCKETS=['tax_supply','invoice','receipt','vat']
SECTIONS=[('Ⅰ 재료비',['원재료','가설재']),('Ⅱ 노무비',['급여·상여금','퇴직급여','임금']),('Ⅲ 경비',['외주비','중기임차료','복리후생비','여비교통비','접대비','통신비','수도광열비','기술연구개발비','세금과공과','지급임차료','수선비','보험료','차량유지비','운반비','유류비','교육훈련비','도서인쇄비','퇴직공제부금비','소모품비','지급수수료','안전관리비','설계용역비','전력비','보상비','협회비','유가증권처분손실','잡비']),('Ⅳ 자산',['임차보증금','기타보증금','시설장치','공구기구비품'])]

def account(value):
    clean=re.sub(r'\([^)]*\)|[\s·.]','',str(value))
    aliases={'재료비':'원재료','급여':'급여·상여금','급여상여금':'급여·상여금','노무비':'임금','장비비':'중기임차료','기타영수증':'잡비','퇴직공제부금':'퇴직공제부금비'}
    standard={re.sub(r'[\s·.]','',x):x for _,names in SECTIONS for x in names}
    return standard.get(clean,aliases.get(clean,str(value).strip()))

def install(c):
    c.execute('''CREATE TABLE IF NOT EXISTS jv_allocation_details(ledger_id INTEGER NOT NULL REFERENCES jv_ledger(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),tax_supply TEXT NOT NULL,invoice TEXT NOT NULL,receipt TEXT NOT NULL,vat TEXT NOT NULL,rule TEXT NOT NULL,PRIMARY KEY(ledger_id,member_id))''')

def parts(amount,members,owner_id):
    amount=db.num(amount);out={m['id']:(amount*db.num(m['share'])/100).to_integral_value(rounding=ROUND_FLOOR) for m in members if m['company_id']!=owner_id}
    owner=next(m['id'] for m in members if m['company_id']==owner_id);out[owner]=amount-sum(out.values(),Decimal(0));return out

def allocate(c,p,month=None,rebuild=False):
    import joint_workflow as flow
    raw=db.ledger(c,p);ms=db.members(c,p);project=next(x for x in db.projects(c) if x['id']==p)
    months=sorted({r['allocation_month'] for r in raw if month is None or r['allocation_month']==month})
    count=0
    with c:
        for period in months:
            if flow.is_closed(c,p,period):
                if rebuild:flow.ensure_open(c,p,period)
                continue
            entries=[r for r in raw if r['allocation_month']==period]
            existing=db.allocations(c,p,period,period)
            if existing and not rebuild:
                existing_ids={a['ledger_id'] for a in existing}
                if any(r['id'] not in existing_ids for r in entries):raise ValueError('해당월에 기존 배분이 있습니다. 기존 수정액·정산 연결을 확인한 뒤 양식 기준 재배분을 사용하세요.')
                continue
            if rebuild:
                for r in entries:flow.ensure_claim_unassigned(c,p,r['id'])
            grouped={}
            for r in entries:grouped.setdefault(account(r['account']),[]).append(r)
            for group in grouped.values():
                cumulative={k:Decimal(0) for k in BUCKETS};previous={k:{m['id']:Decimal(0) for m in ms} for k in BUCKETS}
                for r in sorted(group,key=lambda x:x['id']):
                    detail={m['id']:{} for m in ms}
                    # Difference of cumulative floors: account subtotal matches INT exactly.
                    for k in BUCKETS:
                        cumulative[k]+=db.num(r[k]);current=parts(cumulative[k],ms,project['owner_id'])
                        for m in ms:detail[m['id']][k]=current[m['id']]-previous[k][m['id']]
                        previous[k]=current
                    for m in ms:
                        values=detail[m['id']];base=sum((values[k] for k in BUCKETS[:3]),Decimal(0));vat=values['vat']
                        c.execute('INSERT INTO jv_allocations(ledger_id,member_id,share,base,vat,original_base,original_vat,reason) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ledger_id,member_id) DO UPDATE SET share=excluded.share,base=excluded.base,vat=excluded.vat,original_base=excluded.original_base,original_vat=excluded.original_vat,reason=excluded.reason',(r['id'],m['id'],m['share'],str(base),str(vat),str(base),str(vat),''))
                        c.execute('INSERT INTO jv_allocation_details VALUES(?,?,?,?,?,?,?) ON CONFLICT(ledger_id,member_id) DO UPDATE SET tax_supply=excluded.tax_supply,invoice=excluded.invoice,receipt=excluded.receipt,vat=excluded.vat,rule=excluded.rule',(r['id'],m['id'],*[str(values[k]) for k in BUCKETS],'account_floor_owner_remainder'))
                    count+=1
    return count

def details(c,p,month):return db.rows(c,'SELECT d.* FROM jv_allocation_details d JOIN jv_ledger l ON l.id=d.ledger_id WHERE l.project_id=? AND l.allocation_month=?',(p,month))

def revise(c,p,ledger_id,changes):
    import joint_workflow as flow
    raw=next((x for x in db.ledger(c,p) if x['id']==ledger_id),None)
    if not raw:raise ValueError('원장을 확인하세요.')
    flow.ensure_open(c,p,raw['allocation_month']);flow.ensure_claim_unassigned(c,p,ledger_id)
    old=db.rows(c,'SELECT * FROM jv_allocations WHERE ledger_id=?',(ledger_id,))
    if {r['member_id'] for r in old}!={int(r['member_id']) for r in changes}:raise ValueError('모든 회원사의 증빙별 배분액을 함께 입력하세요.')
    for k in BUCKETS:
        if sum((db.num(r[k]) for r in changes),Decimal(0))!=db.num(raw[k]):raise ValueError('증빙별 공급가액·VAT 합계가 원장과 일치해야 합니다.')
    if any(not r['reason'].strip() for r in changes):raise ValueError('수정 사유를 입력하세요.')
    with c:
        for r in changes:
            c.execute('UPDATE jv_allocations SET base=?,vat=?,reason=? WHERE ledger_id=? AND member_id=?',(str(sum((db.num(r[k]) for k in BUCKETS[:3]),Decimal(0))),str(db.num(r['vat'])),r['reason'],ledger_id,r['member_id']))
            c.execute('INSERT INTO jv_allocation_details VALUES(?,?,?,?,?,?,?) ON CONFLICT(ledger_id,member_id) DO UPDATE SET tax_supply=excluded.tax_supply,invoice=excluded.invoice,receipt=excluded.receipt,vat=excluded.vat,rule=excluded.rule',(ledger_id,r['member_id'],*[str(db.num(r[k])) for k in BUCKETS],'manual'))

def effective_details(raw,allocations,stored):
    exact={(x['ledger_id'],x['member_id']):x for x in stored};source={r['id']:r for r in raw};result={};unknown=set()
    for a in allocations:
        key=a['ledger_id'],a['member_id'];r=source[a['ledger_id']]
        if key in exact:result[key]={k:db.num(exact[key][k]) for k in BUCKETS};continue
        nonzero=[k for k in BUCKETS[:3] if db.num(r[k])]
        values={k:Decimal(0) for k in BUCKETS};values['vat']=db.num(a['vat'])
        if len(nonzero)==1:values[nonzero[0]]=db.num(a['base'])
        elif db.num(a['base']):unknown.add(key)
        result[key]=values
    return result,unknown

def matrix_data(project,members,raw,allocations,prior=(),stored=(),prior_known=True):
    by_account={};pieces,unknown=effective_details(raw,allocations,stored)
    def blank(label):return dict(label=label,previous=Decimal(0),current={k:Decimal(0) for k in BUCKETS},companies={m['id']:{**{k:Decimal(0) for k in BUCKETS},'base':Decimal(0)} for m in members},unknown=False)
    for r in raw:
        v=by_account.setdefault(account(r['account']),blank(account(r['account'])))
        for k in BUCKETS:v['current'][k]+=db.num(r[k])
    for r in prior:
        v=by_account.setdefault(account(r['account']),blank(account(r['account'])))
        v['previous']+=sum((db.num(r[k]) for k in BUCKETS),Decimal(0))
    lookup={r['id']:r for r in raw}
    for a in allocations:
        key=a['ledger_id'],a['member_id'];v=by_account[account(lookup[a['ledger_id']]['account'])];target=v['companies'][a['member_id']]
        for k in BUCKETS:target[k]+=pieces[key][k]
        target['base']+=db.num(a['base']);v['unknown']|=key in unknown
    def add(label,records):
        v=blank(label)
        for r in records:
            v['previous']+=r['previous'];v['unknown']|=r['unknown']
            for k in BUCKETS:v['current'][k]+=r['current'][k]
            for m in members:
                for k in BUCKETS+['base']:v['companies'][m['id']][k]+=r['companies'][m['id']][k]
        return v
    lines=[];expense=[];assets=[];known={x for _,names in SECTIONS for x in names}
    for section,names in SECTIONS:
        lines.append({'section':section})
        group=[by_account.get(name,blank(name)) for name in names]
        lines.extend(group)
        if section.startswith('Ⅳ'):assets=group
        else:expense.extend(group)
        if section.startswith('Ⅲ'):
            lines.append(dict(add('공사원가 계',expense),subtotal=True))
            other=[v for name,v in by_account.items() if name not in known]
            if other:lines.append({'section':'분류 확인 계정'});lines.extend(other)
    gross=add('공급가액 합계',list(by_account.values()));lines.append(dict(gross,subtotal=True))
    deduction=blank('공제액 (회원사투입)');owners={m['company_id']:m['id'] for m in members}
    for r in raw:
        if r['company_id']!=project['owner_id']:
            amount=sum((db.num(r[k]) for k in BUCKETS[:3]),Decimal(0));deduction['current']['receipt']+=amount
            target=deduction['companies'][owners[r['company_id']]];target['receipt']+=amount;target['base']+=amount
    deduction['previous']=sum((sum((db.num(r[k]) for k in BUCKETS[:3]),Decimal(0)) for r in prior if r['company_id']!=project['owner_id']),Decimal(0))
    lines.append(dict(deduction,subtotal=True));net=add('기성청구액',[gross])
    net['previous']-=deduction['previous']
    for k in BUCKETS:net['current'][k]-=deduction['current'][k]
    for m in members:
        for k in BUCKETS+['base']:net['companies'][m['id']][k]-=deduction['companies'][m['id']][k]
    lines.append(dict(net,total=True))
    detail_keys={(d['ledger_id'],d['member_id']) for d in stored}
    return dict(project=project,members=members,lines=lines,prior_known=prior_known,unknown=bool(unknown),legacy=any((a['ledger_id'],a['member_id']) not in detail_keys for a in allocations))

def render_matrix(data,month,printable=True):
    from joint_report import money
    esc=lambda s:escape(str(s));ms=data['members']
    def cell(value):return '<td class="number">'+esc(money(value))+'</td>'
    h='<h1>원 가 배 분 내 역 서</h1><div class="heading"><span>공사명 : '+esc(data['project']['name'])+'</span><span>배분연월 : '+esc(month)+' · 단위: 원</span></div>'
    h+='<div class="scroll"><table id="allocation-matrix"><thead><tr><th rowspan="3">과 목</th><th colspan="8">공 사 원 가 (공급가액 + 부가세)</th>'+''.join('<th colspan="5">'+esc(m['name'])+'</th>' for m in ms)+'<th rowspan="3">비고·검산</th></tr><tr><th rowspan="2">전월까지</th><th colspan="4">당월 원가</th><th rowspan="2">VAT</th><th rowspan="2">합계금액<br>(당월+VAT)</th><th rowspan="2">누계</th>'+''.join('<th colspan="5">'+esc(m['share'])+'%</th>' for m in ms)+'</tr><tr>'
    h+=''.join('<th>'+x+'</th>' for x in ['세금계산서','계산서','기타증빙','공급가액']+['세금계산서','계산서','기타','공급가액 계','VAT']*len(ms))+'</tr></thead><tbody>'
    for line in data['lines']:
        if 'section' in line:h+='<tr class="section"><td colspan="'+str(10+5*len(ms))+'">'+esc(line['section'])+'</td></tr>';continue
        cur=line['current'];supply=sum((cur[k] for k in BUCKETS[:3]),Decimal(0));gross=supply+cur['vat']
        h+='<tr class="'+('total' if line.get('total') else 'subtotal' if line.get('subtotal') else '')+'"><td>'+esc(line['label'])+'</td>'
        h+=(cell(line['previous']) if data['prior_known'] else '<td>미기록</td>')+''.join(cell(cur[k]) for k in BUCKETS[:3])+cell(supply)+cell(cur['vat'])+cell(gross)+(cell(line['previous']+gross) if data['prior_known'] else '<td>미기록</td>')
        for m in ms:
            part=line['companies'][m['id']]
            h+=(''.join('<td>확인 필요</td>' for _ in range(3)) if line['unknown'] else ''.join(cell(part[k]) for k in BUCKETS[:3]))+cell(part['base'])+cell(part['vat'])
        valid=sum((line['companies'][m['id']]['base'] for m in ms),Decimal(0))==supply and sum((line['companies'][m['id']]['vat'] for m in ms),Decimal(0))==cur['vat']
        h+='<td>'+('확인 필요' if line['unknown'] else '정상' if valid else '미배분·확인')+'</td></tr>'
    h+='</tbody></table></div><p>분류 확인 계정은 전체 공급가액에 포함하며 공사원가 계에는 중복 포함하지 않습니다.</p><p>합계금액은 당월 공급가액과 VAT의 합계입니다. 회사별 배분액을 다시 더하지 않습니다.</p>'
    if data.get('legacy'):h+='<p>기존 배분액을 보존한 자료입니다. 새 계산 기준은 미마감 월에서 정산 연결 확인 후 명시적으로 재배분할 수 있습니다.</p>'
    if data['unknown']:h+='<p>기존 혼합 증빙 배분은 금액을 보존했습니다. 증빙별 배분을 확인하거나 미마감 월에서 명시적으로 재배분하세요.</p>'
    button='<button onclick="window.print()">인쇄 / PDF 저장</button>' if printable else '<button disabled>월 마감 후 출력</button>'
    css='''*{box-sizing:border-box}body{font:14px/1.4 "Malgun Gothic",sans-serif;color:#111;margin:20px}h1{text-align:center;font-size:26px;letter-spacing:4px}.heading{display:flex;justify-content:space-between;margin:12px 0}.scroll{overflow:auto}table{border-collapse:collapse;min-width:2000px;width:100%;font-variant-numeric:tabular-nums}th,td{border:1px solid #333;padding:5px;text-align:right;white-space:nowrap}th{text-align:center;background:#f7f8f8}td{text-align:center}td.number{text-align:right}.section td{font-weight:bold;background:#eef4f6}.subtotal{background:#f1f2f3;font-weight:700}.total{background:#e0e5e9;font-weight:700}p{font-size:12px}button{padding:10px 16px;background:#009f57;color:white;border:0;margin-bottom:10px}@page{size:A3 landscape;margin:10mm}@media print{body{margin:0;font-size:9pt}button{display:none}.scroll{overflow:visible}table{min-width:0;font-size:8pt}th,td{padding:1.5px;line-height:1.2}tr{break-inside:avoid}h1{font-size:18pt;margin:8px 0}.heading{margin:6px 0}.section td,.subtotal,.total{print-color-adjust:exact}}'''
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>원가배분내역서</title><style>'+css+'</style><body>'+button+h+'</body></html>'
