import json, glob, os

with open('temp_out.txt', 'w', encoding='utf-8') as fout:
    for f in glob.glob('*.ipynb'):
        fout.write(f'--- {os.path.basename(f)} ---\n')
        try:
            data = json.load(open(f, encoding='utf-8'))
            for cell in data.get('cells', []):
                for out in cell.get('outputs', []):
                    if out.get('output_type') == 'error':
                        fout.write(f'EXECUTION ERROR: {out.get("ename")} : {out.get("evalue")}\n')
                    elif 'text' in out:
                        text = ''.join(out['text'])
                        if 'error' in text.lower() or 'fail' in text.lower() or '결측' in text or '누락' in text:
                            fout.write(f'TEXT MATCH: {text.strip()[:200]}...\n')
        except Exception as e:
            fout.write(f'Failed to parse: {e}\n')
