"""Measured A4 lead-contractor cover letter; a physical 18mm seal stays unscaled."""
import re
SEAL_MM=18
CSS='''
@page{size:A4 portrait;margin:20mm}
.document-letter.letter-v2:has(.lead-letter-a4){width:210mm;min-width:210mm;max-width:210mm;padding:20mm;background:white;margin:16px auto}
.letter-v2 .official-letter.lead-letter-a4{width:170mm;height:256mm;min-height:256mm;padding:0;margin:0;display:flex;flex-direction:column;font-size:10.5pt;line-height:1.5}
.lead-letter-a4 .lead-letter-content{flex:0 0 auto;width:100%;overflow:visible}
.letter-v2 .lead-letter-a4 .letter-company{font-size:22pt;line-height:1.25;margin:0 0 5mm}
.letter-v2 .lead-letter-a4 .letter-address{font-size:8pt;line-height:1.4;padding-bottom:2mm}
.letter-v2 .lead-letter-a4 .letter-top{margin:4mm 0 2mm;min-height:0}
.letter-v2 .lead-letter-a4 .letter-fields{font-size:10pt;line-height:1.45}
.letter-v2 .lead-letter-a4 .letter-fields>div{margin:1mm 0}
.letter-v2 .lead-letter-a4 .letter-rule{margin:2mm 0}
.letter-v2 .lead-letter-a4 .letter-paragraphs{margin:3mm 0}
.letter-v2 .lead-letter-a4 .letter-paragraphs p{margin:2mm 0}
.letter-v2 .lead-letter-a4 .letter-table-wrap{margin:3mm 0 4mm}
.letter-v2 .lead-letter-a4 #letter-amounts{font-size:8.5pt}
.letter-v2 .lead-letter-a4 #letter-amounts td,.letter-v2 .lead-letter-a4 #letter-amounts th{padding:1.5mm 1mm;line-height:1.35}
.letter-v2 .lead-letter-a4 .letter-tail{font-size:10pt;line-height:1.5}
.letter-v2 .lead-letter-a4 .bank{margin:3mm 0}
.letter-v2 .lead-letter-a4 .attachments{margin:2mm 0;gap:3mm}
.letter-v2 .lead-letter-a4 .letter-signature{flex:0 0 auto;margin:auto 0 0;padding:3mm 22mm 0 0;min-height:24mm;font-size:15pt;line-height:1.65;letter-spacing:2px;break-inside:avoid}
.letter-v2 .lead-letter-a4 .letter-signature:has(.sender-lines){padding:3mm 0 0;min-height:24mm;display:flex;align-items:center;justify-content:flex-end;gap:4mm;letter-spacing:0}
.letter-v2 .lead-letter-a4 .sender-lines{width:51mm;max-width:calc(100% - 22mm);flex:0 1 51mm}
.letter-v2 .lead-letter-a4 .sender-line{font-size:15pt;line-height:1.65}
.letter-v2 .lead-letter-a4 .seal,.letter-v2 .lead-letter-a4 .letter-signature:has(.sender-lines) .seal{width:18mm!important;height:18mm!important;min-width:18mm!important;max-width:18mm!important;min-height:18mm!important;max-height:18mm!important;object-fit:contain;flex:0 0 18mm;right:0;bottom:0}
.lead-letter-a4.lead-letter-overflow{height:auto;min-height:256mm}
@media print{
.document-letter.letter-v2:has(.lead-letter-a4){width:170mm;min-width:0;max-width:none;margin:0;padding:0}
.letter-v2 .official-letter.lead-letter-a4{width:170mm;padding:0;margin:0}
}
'''
FIT_SCRIPT='''<script>(function(){
function fit(){
var page=document.querySelector('.lead-letter-a4');if(!page)return;
var body=page.querySelector('.lead-letter-content'),tail=page.querySelector('.letter-signature');if(!body||!tail)return;
page.classList.remove('lead-letter-overflow');body.style.zoom='1';body.style.width='100%';
var box=page.getBoundingClientRect(),footer=tail.getBoundingClientRect(),room=box.height-footer.height-2;
for(var i=0;i<5&&body.getBoundingClientRect().height>room;i++){
var current=parseFloat(body.style.zoom)||1;
var scale=Math.max(.8,current*room/body.getBoundingClientRect().height*.995);
if(Math.abs(scale-current)<.001)break;
body.style.zoom=String(scale);body.style.width=String(100/scale)+'%';
}
if(body.getBoundingClientRect().height>room+1)page.classList.add('lead-letter-overflow');
}
window.addEventListener('load',fit);window.addEventListener('beforeprint',fit);
if(document.fonts)document.fonts.ready.then(fit);fit();
})();</script>'''

def wrap(body):
 body=re.sub(r'<article class="official-letter(?: letter-flow)?">','<article class="official-letter lead-letter-a4"><div class="lead-letter-content">',body,count=1)
 return body.replace('<div class="letter-signature">','</div><div class="letter-signature">',1)
