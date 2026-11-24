#!/usr/bin/env python3
"""Turn reviewed listing and website evidence into a private owner report."""

import argparse
from base64 import b64encode
from dataclasses import dataclass
from datetime import date
from html import escape
import json
from pathlib import Path
from urllib.parse import urlsplit


GOOGLE = 'https://support.google.com/business/answer/'
ASSETS = Path(__file__).with_name('assets')


@dataclass(frozen=True)
class Fix:
    title: str
    when: str
    minutes: int
    impact: int
    fields: tuple[str, ...]
    why: str
    steps: tuple[str, ...]
    done: str
    guide: tuple[str, str] | None = None
    copy: tuple[str, str] | None = None


FIXES = {
    'broken_website': Fix(
        'Fix the Website button on Google', 'Today', 10, 4, ('working_url',),
        'A working Website link lets customers get to your site from Maps.',
        ('In your Google Business Profile, go to Edit profile and find the Website field.',
         'Replace the address with {working_url} and save.',
         'Once the edit appears, open your listing on a phone, tap Website, and check that it loads the right page.'),
        'The Website button opens {working_url} on a phone.',
        ('Google’s profile editing guide', GOOGLE + '3039617'),
    ),
    'broken_estimate_button': Fix(
        'Repair the estimate button on {page}', 'Today', 15, 4, ('page', 'editor_path', 'working_url'),
        'Someone who already wants to ask for an estimate can get stuck after tapping the button.',
        ('In your existing website editor, open {editor_path}.',
         'Select the estimate button. Replace its link with {working_url}, then save and publish the edit.',
         'Open the public page on a phone and tap the same button. Use a marked test submission to check your own inbox.'),
        'The button opens the working estimate form and your test request arrives in the right inbox.',
    ),
    'contradictory_hours': Fix(
        'Correct the hours customers see', 'Today', 10, 3, ('day', 'hours'),
        'Accurate hours tell customers when someone can take their call.',
        ('In your Google Business Profile, go to Edit profile → Hours.',
         'Set {day} to {hours}, the hours your shop confirmed. Save the change.',
         'Check your public listing after Google updates it. Set holiday hours separately when those hours differ.'),
        'Maps shows {hours} for {day}, and those hours match what your shop can cover.',
        ('Google’s hours guide', GOOGLE + '15300403'),
    ),
    'missing_service': Fix(
        'Add {service} to your Google listing', 'This week', 10, 2, ('service', 'description'),
        'Customers can see that you offer {service} right on your listing.',
        ('In your Google Business Profile, choose Edit services.',
         'Choose an existing {service} entry or add it as a custom service if needed.',
         'Add the description below and save. After the edit appears, check Services on the public profile.'),
        '{service} appears on the public listing with the description you approved.',
        ('Google’s services guide', GOOGLE + '9455399'), ('Service description to paste', '{description}'),
    ),
    'stale_reviews': Fix(
        'Ask for reviews when a job is done', 'This week', 15, 2, (),
        'Recent reviews show homeowners how jobs like theirs went.',
        ('In your Google Business Profile, go to Read reviews → Get more reviews and copy your review link.',
         'Add the note below to your invoice or job-completion message. Use the same invitation for every completed job.',
         'Test the review link in a private browser window to confirm it points to your business. Leave incentives out of the request.'),
        'The next completed job includes a working review link. In 30 days, check how many requests went out and how many new reviews appeared.',
        ('Google’s review link and policy guide', GOOGLE + '3474122'),
        ('Review request to paste', 'Thanks for choosing {business}. If you’d like to share how the job went, here’s our Google review link: [paste your link].'),
    ),
    'no_recent_job_photos': Fix(
        'Add photos from a {job} job', 'Next completed job', 15, 1, ('job',),
        'Show homeowners what the work looked like before and after.',
        ('Take a wide photo before you start, then one from the same angle when you finish. Use photos you own and have permission to share.',
         'In your Google Business Profile, go to Photos → Add photos and upload the pair.',
         'After the photos appear, confirm you can see them on the public profile. Keep the originals for the relevant service page.'),
        'The public listing shows two clear photos from the actual {job} job.',
        ('Google’s photo guide', GOOGLE + '6103862'),
    ),
    'missing_service_area': Fix(
        'Make your service area visible', 'This week', 15, 2, ('towns',),
        'A customer can check whether you serve their town before asking for a quote.',
        ('In your Google Business Profile, go to Edit profile → Location.',
         'Edit the service area and add the towns your shop confirmed: {towns}. Save the change.',
         'Check the published profile and compare it with your website’s service area.'),
        'The profile and the website agree on the area your crew covers.',
        ('Google’s service area guide', GOOGLE + '9157481'),
    ),
}


def safe_url(value):
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return False
    try:
        url = urlsplit(value)
        return url.scheme in ('http', 'https') and bool(url.hostname) and url.username is None and url.password is None
    except ValueError:
        return False


def valid_date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def present(value):
    return isinstance(value, str) and bool(value.strip())


def select_fixes(case):
    """Return one verified finding per action, ordered by impact then effort."""
    report_date = valid_date(case.get('checked_on'))
    if report_date is None or not all(present(case.get(key)) for key in ('business', 'town')):
        raise ValueError('Provide a business, town, and ISO checked_on date.')
    findings = case.get('findings')
    if not isinstance(findings, list):
        raise ValueError('Provide a findings list.')
    eligible = {}
    for item in findings:
        if not isinstance(item, dict) or item.get('verified') is not True or item.get('owner_can_do') is not True:
            continue
        kind = item.get('kind')
        fix = FIXES.get(kind) if isinstance(kind, str) else None
        checked = valid_date(item.get('checked_on'))
        values = item.get('values', {})
        if (fix is None or checked is None or checked > report_date or not safe_url(item.get('source'))
                or ('comparison_source' in item and not safe_url(item['comparison_source']))
                or not present(item.get('observed')) or not isinstance(values, dict)
                or not all(present(values.get(key)) for key in fix.fields)
                or ('working_url' in fix.fields and not safe_url(values['working_url']))):
            continue
        if kind in eligible and eligible[kind][0] >= checked:
            continue
        fields = {key: values[key].strip() for key in fix.fields}
        fields['business'] = case['business'].strip()
        eligible[kind] = (checked, item, fix, fields)
    ranked = sorted(eligible.values(), key=lambda row: (-row[2].impact, row[2].minutes, -row[0].toordinal(), row[1]['kind']))
    return ranked[:5]


def select_strengths(case):
    """Keep up to three distinct observations supported by a source."""
    report_date = valid_date(case['checked_on'])
    legacy = 'strengths' not in case
    candidates = [case.get('strength')] if legacy else case['strengths']
    if not isinstance(candidates, list):
        return []
    seen = set()
    strengths = []
    for item in candidates:
        if (not isinstance(item, dict) or item.get('verified') is not True
                or not present(item.get('observed')) or not safe_url(item.get('source'))):
            continue
        checked = valid_date(item.get('checked_on'))
        if ((checked is None and ('checked_on' in item or not legacy))
                or (checked is not None and checked > report_date)
                or (not legacy and not present(item.get('title')))
                or ('comparison_source' in item and not safe_url(item['comparison_source']))):
            continue
        key = ' '.join(item['observed'].casefold().split())
        if key in seen:
            continue
        seen.add(key)
        strengths.append((item, checked))
        if len(strengths) == 3:
            break
    return strengths


STYLE = '''
#owner-report {
  --ink:#18181b; --quiet:#52525b; --sheet:#fff; --band:#f4f4f5; --line:#e4e4e7;
  --link:#0563c1; --on-dark:#ededef; --dark-line:#52525b;
  max-width:1100px; margin:0 auto; padding:0 0 28px;
  color:var(--ink); background:var(--sheet); overflow-wrap:anywhere;
  font:16px/1.48 "Xorion Instrument Sans",-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
}
#owner-report * { box-sizing:border-box; }
#owner-report p, #owner-report h1, #owner-report h2 { margin:0; }
#owner-report a { color:var(--link); text-underline-offset:.16em; }
#owner-report :is(a,button,summary):focus-visible { outline:2px solid var(--ink); outline-offset:3px; }
#owner-report .masthead {
  display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap;
  min-height:58px; padding:10px 0; border-bottom:1px solid var(--dark-line);
}
#owner-report .cover { background:var(--ink); color:var(--sheet); padding:0 clamp(18px,4.2vw,45px) clamp(20px,4.2vw,45px); }
#owner-report .brand { display:inline-flex; gap:9px; align-items:center; font-weight:700; }
#owner-report .mark { display:block; width:31px; height:31px; }
#owner-report .print {
  min-height:40px; padding:6px 12px; background:transparent; border:1px solid var(--dark-line);
  border-radius:8px; color:var(--sheet); font:inherit; font-size:.825rem; font-weight:600; cursor:pointer;
}
#owner-report .print:focus-visible { outline-color:var(--sheet); }
#owner-report .print:hover { border-color:var(--sheet); }
#owner-report .headline {
  display:grid; grid-template-columns:minmax(0,1.12fr) minmax(0,1fr);
  align-items:center; gap:clamp(18px,4vw,45px); padding-top:clamp(20px,4vw,38px);
}
#owner-report .kicker { color:var(--on-dark); font-weight:650; font-size:.85rem; margin-bottom:9px; }
#owner-report h1 { font-size:clamp(2rem,5.7vw,3.8rem); line-height:1.02; letter-spacing:-.046em; font-weight:650; }
#owner-report .promise { max-width:32ch; margin-top:11px; color:var(--on-dark); font-size:clamp(1rem,2.1vw,1.2rem); }
#owner-report .meta { color:var(--quiet); font-size:.825rem; }
#owner-report .identity { margin-top:13px; color:var(--on-dark); }
#owner-report .first {
  background:var(--sheet); color:var(--ink); padding:clamp(14px,2.5vw,24px);
  border:1px solid var(--line); border-radius:8px;
}
#owner-report .first h2 { margin-top:4px; font-size:clamp(1.22rem,2.7vw,1.65rem); line-height:1.16; letter-spacing:-.022em; }
#owner-report .first p { margin-top:7px; color:var(--quiet); }
#owner-report .first-link {
  display:inline-flex; align-items:center; min-height:42px; margin-top:12px; padding:6px 12px;
  border:1px solid var(--ink); border-radius:8px; background:var(--ink); color:var(--sheet);
  font-weight:650; font-size:.88rem; text-decoration:none;
}
#owner-report .first-link:hover { background:#27272a; }
#owner-report .body { padding:0 clamp(18px,4.2vw,45px); }
#owner-report .strengths { padding:20px 0 16px; border-bottom:1px solid var(--line); }
#owner-report .strengths h2 { font-size:1.25rem; line-height:1.2; letter-spacing:-.018em; }
#owner-report .strength-list {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%, 240px),1fr)); gap:14px 24px;
  list-style:none; margin:11px 0 0; padding:0;
}
#owner-report .strength-list li { padding-left:10px; border-left:2px solid var(--line); }
#owner-report .strength-list p { color:var(--quiet); margin-top:3px; }
#owner-report .strength-source { margin-top:4px; }
#owner-report .index-title { margin:22px 0 9px; line-height:1.2; font-size:1.25rem; letter-spacing:-.018em; }
#owner-report .fix-pane { border-top:1px solid var(--line); scroll-margin-top:12px; }
#owner-report .fix-pane:last-child { border-bottom:1px solid var(--line); }
#owner-report summary {
  display:grid; grid-template-columns:1.75rem minmax(0,1fr) auto 1rem; align-items:center; gap:9px;
  min-height:56px; padding:10px 8px; list-style:none; cursor:pointer;
}
#owner-report summary::-webkit-details-marker { display:none; }
#owner-report summary:hover, #owner-report details[open] summary { background:var(--band); }
#owner-report summary::after { content:'+'; color:var(--quiet); line-height:1; }
#owner-report details[open] summary::after { content:'−'; }
#owner-report .rank { color:var(--quiet); font-weight:650; font-size:.8rem; font-variant-numeric:tabular-nums; }
#owner-report .fix-label { font-weight:650; line-height:1.3; }
#owner-report .time { color:var(--quiet); font-size:.8rem; }
#owner-report .fix-detail { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.8fr); gap:20px; padding:16px 8px; }
#owner-report .evidence { border-left:2px solid var(--line); padding:9px 11px; background:var(--band); align-self:start; }
#owner-report .evidence .meta { display:block; margin-top:4px; }
#owner-report .evidence p, #owner-report .copy p { margin-top:3px; }
#owner-report .why { margin-top:8px; }
#owner-report .plan-label { font-weight:650; }
#owner-report .plan { padding-left:1.35em; margin:8px 0 0; }
#owner-report .plan li + li { margin-top:5px; }
#owner-report .plan li::marker { font-weight:650; }
#owner-report .copy { margin-top:13px; padding:9px 11px; background:var(--band); }
#owner-report .copy-head { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }
#owner-report .copy-button {
  min-height:44px; padding:4px 10px; border:1px solid var(--line); border-radius:8px;
  color:var(--ink); background:var(--sheet); font:inherit; font-size:.825rem; cursor:pointer;
}
#owner-report .copy-button[hidden] { display:none; }
#owner-report .done { margin-top:14px; padding-top:10px; border-top:1px solid var(--line); }
#owner-report .guide { margin-top:7px; }
#owner-report footer { color:var(--quiet); margin-top:20px; font-size:.825rem; }
@media(max-width:640px) {
  #owner-report .headline, #owner-report .fix-detail { grid-template-columns:minmax(0,1fr); }
  #owner-report summary { grid-template-columns:1.5rem minmax(0,1fr) 1rem; gap:3px 6px; }
  #owner-report summary .time { grid-column:2; }
  #owner-report summary::after { grid-area:1/3/3/4; }
}
@media print {
  #owner-report { max-width:none; padding:0; }
  #owner-report .cover { background:var(--sheet); color:var(--ink); padding:0; }
  #owner-report :is(.kicker,.promise,.identity) { color:var(--quiet); }
  #owner-report .masthead { min-height:0; padding:0; border-bottom:1px solid var(--line); }
  #owner-report .mark { filter:brightness(0); }
  #owner-report :is(.print,.first,.copy-button,.copy-status), #owner-report summary::after { display:none; }
  #owner-report .headline { display:block; padding:12px 0; }
  #owner-report .body { padding:0; }
  #owner-report .strengths { break-inside:avoid; }
  #owner-report h1 { font-size:25pt; }
  #owner-report .fix-pane { break-inside:avoid; }
  #owner-report .fix-pane::details-content { content-visibility:visible; }
  #owner-report summary { display:flex; justify-content:flex-start; min-height:0; padding:7px 0; }
  #owner-report .fix-detail { gap:12px; padding:0 0 8px; }
}
'''

REPORT_SCRIPT = '''<script>
(() => {
  const report = document.getElementById('owner-report');
  const fixes = [...report.querySelectorAll('.fix-pane')];
  let closedForPrint;

  report.querySelector('.first-link')?.addEventListener('click', event => {
    if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    event.preventDefault();
    fixes[0].open = true;
    fixes[0].querySelector('summary').focus({ preventScroll: true });
    fixes[0].scrollIntoView({ block: 'start' });
  });
  report.querySelectorAll('.copy-button').forEach(button => {
    const block = button.closest('.copy');
    const value = block.querySelector('.copy-value');
    const status = block.querySelector('.copy-status');
    button.hidden = false;
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(value.textContent);
        status.textContent = 'Copied.';
      } catch {
        const range = document.createRange();
        range.selectNodeContents(value);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        status.textContent = 'Text selected. Copy it from here.';
      }
    });
  });
  report.querySelector('.print')?.addEventListener('click', () => window.print());
  window.addEventListener('beforeprint', () => {
    closedForPrint ??= fixes.filter(fix => !fix.open);
    closedForPrint.forEach(fix => { fix.open = true; });
  });
  window.addEventListener('afterprint', () => {
    closedForPrint?.forEach(fix => { fix.open = false; });
    closedForPrint = undefined;
  });
})();
</script>'''


def render(case, fragment=False):
    rows = select_fixes(case)
    sample = case.get('sample') is True
    checked = valid_date(case['checked_on']).strftime('%B %d, %Y').replace(' 0', ' ')
    mark = b64encode((ASSETS / 'xorion-mark.svg').read_bytes()).decode('ascii')
    font = b64encode((ASSETS / 'instrument-sans-latin.woff2').read_bytes()).decode('ascii')
    font_license = (ASSETS / 'OFL-InstrumentSans.txt').read_text(encoding='utf-8').replace('--', '—')
    font_style = f'@font-face{{font-family:"Xorion Instrument Sans";src:url(data:font/woff2;base64,{font}) format("woff2");font-weight:400 700;font-display:swap}}'

    def action(number, row):
        seen, item, fix, fields = row

        def fill(value):
            return escape(value.format_map(fields))

        evidence = 'Example evidence' if sample else f'<a href="{escape(item["source"], quote=True)}">Open evidence</a>'
        if not sample and item.get('comparison_source'):
            evidence += f' · <a href="{escape(item["comparison_source"], quote=True)}">See comparison</a>'
        guide = f'<p class="guide meta"><a href="{escape(fix.guide[1])}">{escape(fix.guide[0])}</a></p>' if fix.guide else ''
        snippet = fix.copy
        if snippet is None and 'working_url' in fields:
            snippet = ('Address to paste', '{working_url}')
        copy = ''
        if snippet:
            label = escape(snippet[0])
            copy = f'''<div class="copy">
  <div class="copy-head"><b>{label}</b><button class="copy-button" type="button" aria-label="Copy {label.lower()}" hidden>Copy</button></div>
  <p class="copy-value">{fill(snippet[1])}</p><span class="copy-status meta" role="status"></span>
</div>'''
        steps = ''.join(f'<li>{fill(step)}</li>' for step in fix.steps)
        title = fill(fix.title)
        return f'''<details class="fix-pane" id="owner-fix-{number}">
  <summary>
    <span class="rank">{number:02}</span><span class="fix-label">{title}</span><span class="time">{escape(fix.when)} · about {fix.minutes} min</span>
  </summary>
  <div class="fix-detail">
    <div class="evidence"><b>What we saw</b><p>{escape(item['observed'])}</p><span class="meta">{escape(seen.isoformat())} · {evidence}</span><p class="why">{fill(fix.why)}</p></div>
    <div>
      <p class="plan-label">What to do</p>
      <ol class="plan">{steps}</ol>{copy}
      <p class="done"><b>Done when</b> {fill(fix.done)}</p>
      {guide}
    </div>
  </div>
</details>'''

    count = len(rows)
    sample_label = 'Fictional example · ' if sample else ''
    strength_html = ''
    strengths = []
    for item, checked_date in select_strengths(case):
        title = f'<b>{escape(item["title"])}</b>' if present(item.get('title')) else ''
        proof = ''
        if not sample:
            sources = f'<a href="{escape(item["source"], quote=True)}">See evidence</a>'
            if item.get('comparison_source'):
                sources += f' · <a href="{escape(item["comparison_source"], quote=True)}">See comparison</a>'
            date_label = f'{checked_date.isoformat()} · ' if checked_date else ''
            proof = f'<div class="strength-source meta">{date_label}{sources}</div>'
        strengths.append(f'<li>{title}<p>{escape(item["observed"])}</p>{proof}</li>')
    if strengths:
        strength_html = f'''<section class="strengths" aria-labelledby="owner-strengths-title">
  <h2 id="owner-strengths-title">What’s already working</h2>
  <ul class="strength-list">{''.join(strengths)}</ul>
</section>'''
    workspace = ''
    first = ''
    footer = ''
    promise = 'No verified changes to recommend yet.'
    if rows:
        actions = ''.join(action(number, row) for number, row in enumerate(rows, 1))
        index_title = 'Your fix' if count == 1 else 'Your fixes, in order'
        workspace = f'<section aria-labelledby="owner-fixes-title"><h2 class="index-title" id="owner-fixes-title">{index_title}</h2>{actions}</section>'
        promise = '1 fix you can do yourself.' if count == 1 else f'{count} fixes you can do yourself.'
        footer = '<footer>Times estimate the work itself. Edits may take longer to show up on Google.</footer>'
        _, item, fix, fields = rows[0]
        first = f'''<section class="first" aria-label="First fix">
  <div class="meta">Start here · about {fix.minutes} min</div>
  <h2>{escape(fix.title.format_map(fields))}</h2>
  <p>{escape(item['observed'])}</p>
  <a class="first-link" href="#owner-fix-1">See the steps <span aria-hidden="true">&nbsp;→</span></a>
</section>'''
    body = f'''<!--
{font_license}
-->
<style>{font_style}
{STYLE}</style>
<main id="owner-report">
  <header class="cover">
    <div class="masthead"><span class="brand"><img class="mark" src="data:image/svg+xml;base64,{mark}" width="31" height="31" alt="">Xorion Systems</span>{'' if fragment else '<button class="print" type="button">Print report</button>'}</div>
    <div class="headline">
      <div><div class="kicker">Free Google listing and website checkup</div><h1>{escape(case['business'])}</h1>
      <p class="promise">{promise}</p><div class="identity meta">{escape(case['town'])} · {sample_label}Checked {escape(checked)}</div></div>
      {first}
    </div>
  </header>
  <div class="body">
    {strength_html}
    {workspace}
    {footer}
  </div>
</main>{REPORT_SCRIPT}'''
    if fragment:
        return body
    return '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Owner action plan</title></head><body>' + body + '</body></html>\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--fragment', action='store_true', help='Render the owner view for an inline preview.')
    args = parser.parse_args()
    try:
        case = json.loads(args.evidence.read_text(encoding='utf-8'))
        if not isinstance(case, dict):
            raise ValueError('The report input must be a JSON object.')
        output = render(case, args.fragment)
        args.output.write_text(output, encoding='utf-8')
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
