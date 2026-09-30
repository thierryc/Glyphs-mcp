"""Public MCP verification, restricted to two owned disposable fonts."""
import asyncio,json,tempfile,uuid
from pathlib import Path
from fastmcp import Client

ROOT=Path(__file__).resolve().parent
INPUTS=ROOT/'live-inputs.json'
if INPUTS.exists():
    inputs=json.loads(INPUTS.read_text())
else:
    base=Path(tempfile.mkdtemp(prefix='glyphs-mcp-create-live-'))
    inputs=[{'family_name':'MCP Creation Live '+suffix[1:], 'idempotency_key':str(uuid.uuid4()),
             'destination':str(base/('Created'+suffix))} for suffix in ('.glyphs','.glyphspackage')]
    INPUTS.write_text(json.dumps(inputs,indent=2)+'\n')
report={'calls':[], 'checks':[]}
def record():
    (ROOT/'live-verification.json').write_text(json.dumps(report,indent=2)+'\n')
async def main():
    async with Client('http://127.0.0.1:9680/mcp/',timeout=30) as client:
        names=[tool.name for tool in await client.list_tools()]
        assert 'create_document' in names and len(names)==13
        async def call(name,args):
            response=await client.call_tool(name,args)
            body=response.data
            report['calls'].append({'name':name,'arguments':args,'result':body});record()
            if not body['ok']:raise RuntimeError(body['error'])
            return body['data']
        status=await call('get_status',{})
        manifest=json.loads((ROOT.parents[1]/'build/simple-native-scripting/manifest.json').read_text())
        assert status['codeHash']==manifest['sidecar']['codeHash']
        assert status['bridge']['codeHash']==manifest['bridge']['codeHash']
        assert 'document.create.v1' in status['writeCapabilities']
        original=await call('list_documents',{})
        report['originalDocuments']=original;record()
        for item in inputs:
            args={k:item[k] for k in ('family_name','idempotency_key')}
            result=await call('create_document',args)
            assert result['path'] is None and len(result['masterIds'])==len(result['instanceIds'])==1
            duplicate=await call('create_document',args)
            assert duplicate['id']==result['id']
            masters=await call('read_entities',{'document_id':result['id'],'entities':[{'kind':'masters','limit':100}],'fields':['id','name']})
            assert masters[0]['values']['items']==[{'id':result['masterIds'][0],'name':'Regular'}]
            saved=await call('save_document',{'document_id':result['id'],'destination':item['destination']})
            assert saved['documentId']==result['id']
            report['checks'].append({'destination':item['destination'],'documentId':result['id'],'duplicateReused':True,'masterReadVerified':True,'saveVerified':True});record()
        final=await call('list_documents',{})
        created_ids={row['documentId'] for row in report['checks']}
        assert len([doc for doc in final if doc['id'] in created_ids])==2
        for previous in original:
            matches=[doc for doc in final if doc['id']==previous['id']]
            assert len(matches)==1 and matches[0]['dirty']==previous['dirty'] and matches[0]['generation']==previous['generation']
        report['passed']=True;record()
        print(json.dumps({'passed':True,'checks':report['checks'],'host':status['bridge']['host']}))
asyncio.run(main())
