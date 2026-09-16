"""Rebuild combined summaries and the two-page report from recorded rows."""
import csv
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'results'
source = RESULTS / 'chat_evaluation/per_item_chat_gpt-6-astra.csv'
target = RESULTS / 'per_item_chat_gpt-6-astra.csv'
if target.exists() and target.read_bytes() != source.read_bytes():
    raise RuntimeError('Existing Astra result differs; resolve before rebuilding.')
target.write_bytes(source.read_bytes())
items = [json.loads(line) for line in (ROOT/'Data/items.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
labels = {'positive','negative','neutral','mixed'}
def percentile(values, p):
    if not values: return ''
    values=sorted(values); pos=(len(values)-1)*p; low=int(pos)
    return values[low]+(values[min(low+1,len(values)-1)]-values[low])*(pos-low)
def save_csv(path, rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
summaries=[]; all_rows=[]; failures={}
for path in sorted(RESULTS.glob('per_item_*.csv')):
    with path.open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
    assert len(rows)==len(items)
    for row,item in zip(rows,items):
        assert (row['item_id'],row['text'],row['reference_answer'])==(item['id'],item['text'],item['label'])
        output=row['generated_answer'].strip().lower()
        row['correct']=str(int(not row['error'] and output in labels and output==row['reference_answer'].strip().lower()))
    lat=[float(r['latency_ms']) for r in rows if r['latency_ms']]
    s=dict(provider=rows[0]['provider'],model=rows[0]['model'],items=len(rows),correct=sum(int(r['correct']) for r in rows))
    s.update(accuracy=s['correct']/s['items'],parse_errors=sum(not r['error'] and r['generated_answer'].strip().lower() not in labels for r in rows),execution_errors=sum(bool(r['error']) for r in rows),p50_latency_ms=percentile(lat,.5),p95_latency_ms=percentile(lat,.95))
    for key in ['input_tokens','output_tokens']:
        s[key]=sum(int(r[key]) for r in rows) if all(r[key] for r in rows) else ''
    summaries.append(s); all_rows+=rows; failures[s['model']]=[r for r in rows if r['correct']=='0']
save_csv(RESULTS/'summary.csv',summaries)
save_csv(RESULTS/'combined_per_item.csv',all_rows)
groq=next(s for s in summaries if s['provider']=='groq')
cost=(groq['input_tokens']*.075+groq['output_tokens']*.30)/1e6
cost1000=cost/75*1000

styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='Body',fontName='Helvetica',fontSize=9,leading=12,spaceAfter=5))
styles.add(ParagraphStyle(name='SmallText',fontName='Helvetica',fontSize=7.6,leading=10,spaceAfter=4))
styles.add(ParagraphStyle(name='Section',fontName='Helvetica-Bold',fontSize=11,leading=14,spaceBefore=8,spaceAfter=5,textColor=colors.HexColor('#16445b')))
story=[]
def p(text,style='Body'): return Paragraph(text,styles[style])
def add(text,style='Body'): story.append(p(text,style))
def table(data,widths):
    t=Table([[p(str(x),'SmallText') for x in row] for row in data],colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4edf2')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#16445b')),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')])]))
    story.append(t)
add('Project 0 - Sentiment Classification Bake-Off','Title')
add('CS496 AI Engineering | Combined evidence report | 16 September 2026','SmallText')
add('1. Task and data','Section')
add('Classify each short text as positive, negative, neutral, or mixed. Example 001: "Not bad at all - honestly better than the one I paid twice as much for." Reference: positive. Scoring trims whitespace, lowercases, and requires an exact label; other output, refusal, timeout, or execution failure is wrong.')
add('The repository dataset contains 75 English items: 18 positive, 19 negative, 19 neutral, and 19 mixed. It includes negation, sarcasm, factual descriptions, and competing opinions. All items form the test set; no separate development split, original data provenance, or completed two-person label review is documented. Reference labels are retained unchanged. The source is benchmark/Data/items.jsonl, not the earlier SQL task.')
add('2. Setup and comparability','Section')
add('Recorded runs: Groq openai/gpt-oss-20b; Ollama tinyllama:1.1b; Ollama qwen2.5:14b. The checked-in runner uses one sequential call per item, the same system/user messages, temperature 0, and a 256-token output limit. The prompt defines each sentiment and says "Return ONLY one label" with no punctuation or explanation. Historical run timestamps, model digests, local hardware, and decoding tokens/second were not recorded in these CSVs; exact run settings cannot be independently verified.')
add('<b>Astra disclosure:</b> gpt-6-astra answers were authored in the current conversation after reference labels were visible. They are a non-blind chat evaluation, not 75 independent API calls. Its accuracy is descriptive only; latency, token usage, and cost are unavailable. This does not satisfy the assignment\'s top-API-model run requirement.')
add('3. Results recomputed from per-item CSVs','Section')
data=[['Model / source','Correct','Accuracy','Parse / exec','p50 ms','p95 ms']]
for s in summaries:
    name=s['model']+(' (chat*)' if s['provider']=='chat_nonblind' else '')
    data.append([name,f"{s['correct']}/75",f"{s['accuracy']:.2%}",f"{s['parse_errors']} / {s['execution_errors']}",f"{s['p50_latency_ms']:.1f}" if s['p50_latency_ms']!='' else 'N/A',f"{s['p95_latency_ms']:.1f}" if s['p95_latency_ms']!='' else 'N/A'])
table(data,[172,48,57,65,65,65])
add('Percentiles use linear interpolation over all recorded request latencies, including invalid outputs. The old scorer skipped invalid outputs, suppressing TinyLlama latency entirely. No recorded execution errors occurred. Refusals/timeouts were not separately tagged in the historical files. *Astra is excluded from measured performance and cost rankings.','SmallText')
add('4. Provisional model choice','Section')
add('Choose Qwen2.5 14B provisionally for this task: it has the strongest measured accuracy (72/75) and lower recorded p50/p95 than Groq, with zero parse errors. This is conditional on acceptable local hardware and operating cost. Prefer Groq when local capacity, deployment effort, or total cost favors API hosting. Reconsider after a blind Astra API run, human label review, and a larger held-out test. TinyLlama is unsuitable under this exact output contract.')
story.append(PageBreak())
add('Errors, cost, and remaining evidence','Title')
add('5. Wrong answers (reference / prediction)','Section')
data=[['Model','Item and text excerpt','Reference / output']]
for s in summaries:
    for r in failures[s['model']][:3]:
        text=r['text']; excerpt=text if len(text)<91 else text[:88]+'...'
        out=r['generated_answer'] or '[empty]'
        if len(out)>65: out=out[:62]+'...'
        data.append([s['model'],r['item_id']+': '+escape(excerpt),escape(r['reference_answer']+' / '+out)])
table(data,[112,244,116])
add('TinyLlama outputs are excerpts; full responses are in combined_per_item.csv. Astra has only two wrong answers, so a third cannot be supplied without inventing a failure. Qwen/Groq struggle with ironic praise; item 072 exposes an ambiguous boundary between factual functioning and favorable opinion.','SmallText')
add('6. Cost now, at 100x traffic, and break-even','Section')
add(f'Groq recorded {groq["input_tokens"]:,} input and {groq["output_tokens"]:,} output tokens. Using the current published standard rates of $0.075/input million and $0.30/output million: 75 requests cost ${cost:.6f}; <b>1,000 requests cost ${cost1000:.5f}</b>. At 100x the observed volume (7,500 requests), projected cost is ${cost*100:.5f}. These are list-price estimates from recorded usage, not invoices; they assume the same token mix and no tier/cache discounts.')
add('Local cost is not zero merely because no API is billed. For hourly hardware cost H, measured requests/hour R, and allocated labor cost L per request, local cost/1,000 = 1,000(H/R + L). Hardware, electricity, labor, and decoding throughput were not supplied, so numeric local costs and Astra cost remain N/A. At 100x volume, capacity and queueing must be remeasured.')
add(f'For fixed local cost F over a defined period and variable local cost v/request, break-even volume N = F / (a - v), where Groq a = ${cost/75:.8f}/request. This exists only when a &gt; v; otherwise positive fixed local costs never break even in that model. Missing F and v prevent a defensible numeric volume.')
add('7. Evidence and completion gaps','Section')
add('All four files match the same 75 IDs, texts, and labels. Combined results contain 300 rows. Before submission: complete two-person label checks; record data source, development/test policy, model/run dates, local hardware and tokens/second; run the flagship API blind; and supply local cost inputs. The report follows the required two-page structure but the available evidence does not yet satisfy every experimental requirement.','SmallText')
add('Sources: repository prompt.py, run.py and Data/items.jsonl; results/per_item_*.csv. Groq current pricing (accessed 16 Sep 2026): <link href="https://console.groq.com/docs/models" color="#16445b">console.groq.com/docs/models</link>. Dataset SHA-256: '+hashlib.sha256((ROOT/'Data/items.jsonl').read_bytes()).hexdigest()[:24]+'...','SmallText')
def footer(c,doc):
    c.setFont('Helvetica',8); c.setFillColor(colors.HexColor('#526571')); c.drawString(42,25,'CS496 | Project 0 | Evidence-based comparison'); c.drawRightString(A4[0]-42,25,str(doc.page))
SimpleDocTemplate(str(ROOT/'report.pdf'),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=32,bottomMargin=38,title='Project 0 - Sentiment Classification Bake-Off',author='Project team').build(story,onFirstPage=footer,onLaterPages=footer)
print(json.dumps(summaries,indent=2))
