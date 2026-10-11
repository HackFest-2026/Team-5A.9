import argparse,pathlib
from common import load,save
from contract_models import MODELS
from request_models import Request
def validate(package):
    import jsonschema
    p=pathlib.Path(package);docs={};checks=[]
    for name,model in MODELS.items():
        raw=load(p/'catalog'/f'{name}.json');parsed=model.model_validate(raw);schema=model.model_json_schema();save(p/'catalog/schemas'/f'{name}.schema.json',schema);jsonschema.validate(raw,schema);docs[name]=raw;checks.append({'document':name,'pydantic':'pass','json_schema':'pass'})
    save(p/'catalog/schemas/request.schema.json',Request.model_json_schema())
    mids={m['id']:m for m in docs['measures']['items']};wids={w['id']:w for w in docs['widgets']['items']};vids={v['id'] for v in docs['views']['items']}
    for ch in docs['charts']['items']:
        if ch['measure_id'] not in mids or mids[ch['measure_id']]['status']!='verified':raise ValueError('Chart references unverified measure')
        if ch['widget_id'] not in wids:raise ValueError('Missing widget')
        if not (p/ch['query_file']).is_file() or not (p/ch['evidence_file']).is_file():raise ValueError('Chart SQL/evidence missing')
    for w in wids.values():
        if w['view_id'] not in vids:raise ValueError('Unknown widget view')
        if w['measure_id'] is not None and (w['measure_id'] not in mids or mids[w['measure_id']]['status']!='verified'):raise ValueError('Published widget uses unverified measure')
    for v in docs['views']['items']:
        if any(w not in wids for w in v['widgets']):raise ValueError('View/widget mismatch')
    save(p/'evidence/contract_validation.json',{'status':'pass','documents':checks,'reference_integrity':'pass','implementation':'Pydantic models plus generated JSON schemas; business truth independently validated','agent_success':'not-measured'})
    print('Contract validated',flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);a=ap.parse_args();validate(a.package)
