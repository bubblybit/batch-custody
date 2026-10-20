# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import hashlib
import json
import re
from datetime import datetime, timezone


def _require(ok: bool,message: str) -> None:
    if not ok:
        raise gl.vm.UserError('[EXPECTED] '+message)


def _canon(value) -> str:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)


def _hash(value) -> str:
    return hashlib.sha256(_canon(value).encode('utf-8')).hexdigest()


def _now() -> int:
    t=datetime.fromisoformat(gl.message_raw['datetime'].replace('Z','+00:00'))
    if t.tzinfo is None:
        t=t.replace(tzinfo=timezone.utc)
    d=t.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)
    return d.days*86400+d.seconds


def _pairs(pairs: list) -> dict:
    out={}
    for key,value in pairs:
        _require(key not in out,'duplicate JSON key')
        out[key]=value
    return out


def _parse(text: str,limit: int):
    _require(isinstance(text,str) and 1<=len(text)<=limit,'JSON size')
    try:
        return json.loads(text,object_pairs_hook=_pairs)
    except (ValueError,RecursionError):
        raise gl.vm.UserError('[EXPECTED] invalid JSON')


def _id(value: str) -> None:
    _require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value) is not None,'invalid identifier')


def _url(value: str) -> None:
    match=re.fullmatch(r'https://raw\.githubusercontent\.com/[A-Za-z0-9-]{1,39}/([A-Za-z0-9_.-]{1,100})/[0-9a-f]{40}/([A-Za-z0-9_.~/-]+)',value) if isinstance(value,str) and len(value)<=512 else None
    _require(match is not None and match[1] not in ('.','..') and all(x not in ('','.','..') for x in match[2].split('/')),'commit-pinned public content required')


def _manifest(text: str) -> list:
    values=_parse(text,12000)
    _require(isinstance(values,list) and 1<=len(values)<=8,'manifest must have 1..8 items')
    seen=set()
    for item in values:
        _require(isinstance(item,dict) and set(item)=={'item_id','url','sha256','quantity'},'manifest fields')
        _id(item['item_id']);_url(item['url'])
        _require(item['item_id'] not in seen,'duplicate item ID')
        seen.add(item['item_id'])
        _require(isinstance(item['sha256'],str) and re.fullmatch(r'[0-9a-f]{64}',item['sha256']) is not None,'invalid SHA256')
        _require(type(item['quantity']) is int and 1<=item['quantity']<=1000000000,'quantity must be positive exact integer')
    return sorted(values,key=lambda x:x['item_id'])


def _capture(manifest: list,binding: dict) -> dict:
    def leader() -> dict:
        observed=[]
        for item in manifest:
            response=gl.nondet.web.get(item['url'],headers={'Accept':'application/octet-stream'})
            if response.status!=200 or response.body is None or not 1<=len(response.body)<=16384:
                raise gl.vm.UserError('[SOURCE] unavailable or oversized manifest content')
            digest=hashlib.sha256(response.body).hexdigest()
            if digest!=item['sha256']:
                raise gl.vm.UserError('[SOURCE] manifest content digest mismatch')
            observed.append({'item_id':item['item_id'],'url':item['url'],'sha256':digest,'bytes':len(response.body),'quantity':item['quantity']})
        return {'binding':binding,'manifest_sha256':_hash(manifest),'observed':observed}
    def validator(proposed: gl.vm.Result) -> bool:
        if not isinstance(proposed,gl.vm.Return):
            return False
        try:
            # Independently retrieve every object, hash its actual bytes and bind the offer.
            return _canon(leader())==_canon(proposed.calldata)
        except Exception:
            return False
    return gl.vm.run_nondet_unsafe(leader,validator)


class BatchCustody(gl.Contract):
    issuer: Address
    batches: TreeMap[str,str]
    lots: TreeMap[str,str]
    offers: TreeMap[str,str]
    used_nonces: TreeMap[str,str]

    def __init__(self):
        self.issuer=gl.message.sender_address

    def _batch(self,batch_id: str) -> dict:
        _require(batch_id in self.batches,'unknown batch')
        return json.loads(self.batches[batch_id])

    def _lot(self,lot_id: str) -> dict:
        _require(lot_id in self.lots,'unknown lot')
        return json.loads(self.lots[lot_id])

    def _offer(self,offer_id: str) -> dict:
        _require(offer_id in self.offers,'unknown offer')
        return json.loads(self.offers[offer_id])

    def _save_lot(self,lot_id: str,lot: dict) -> None:
        self.lots[lot_id]=_canon(lot)

    def _new_lot(self,lot_id: str,batch_id: str,holder: str,quantities: dict,parent: str,now: int) -> None:
        _require(lot_id not in self.lots,'output lot collision')
        self._save_lot(lot_id,{'lot_id':lot_id,'batch_id':batch_id,'holder':holder,'quantities':quantities,'status':'ACTIVE','revision':0,'locked_offer':'','parent_offer':parent,'created_at':now})

    @gl.public.write
    def open_batch(self,batch_id: str,manifest_json: str) -> str:
        _require(gl.message.sender_address==self.issuer,'issuer only');_id(batch_id)
        _require(batch_id not in self.batches,'batch already issued')
        manifest=_manifest(manifest_json)
        binding={'chain_id':int(gl.message.chain_id),'contract':gl.message.contract_address.as_hex.lower(),'batch_id':batch_id,'issuer':self.issuer.as_hex.lower(),'opened_at':_now()}
        packet=_capture(manifest,binding)
        root_id=_hash(['BatchCustody-v1-root',binding,manifest])
        totals={x['item_id']:x['quantity'] for x in manifest}
        self._new_lot(root_id,batch_id,self.issuer.as_hex.lower(),totals,'',_now())
        self.batches[batch_id]=_canon({'batch_id':batch_id,'manifest':manifest,'manifest_sha256':_hash(manifest),'binding':binding,'initial_totals':totals,'lots':[root_id],'offers':[],'initial_capture':packet})
        return root_id

    @gl.public.write
    def propose_transfer(self,batch_id: str,lot_id: str,expected_revision: int,amounts_json: str,recipient: str,nonce: str,ttl_seconds: int) -> str:
        b=self._batch(batch_id);lot=self._lot(lot_id);sender=gl.message.sender_address.as_hex.lower()
        _require(lot['batch_id']==batch_id,'wrong batch')
        _require(lot['holder']==sender,'holder only')
        _require(lot['status']=='ACTIVE','lot not active')
        _require(type(expected_revision) is int and expected_revision==lot['revision'],'stale revision')
        _id(nonce)
        nonce_key=_hash([batch_id,sender,nonce])
        _require(nonce_key not in self.used_nonces,'sender nonce used')
        _require(type(ttl_seconds) is int and 60<=ttl_seconds<=86400,'TTL must be 60..86400 seconds')
        if isinstance(recipient,Address):
            recipient=recipient.as_hex
        _require(isinstance(recipient,str) and re.fullmatch(r'0x[0-9a-fA-F]{40}',recipient) is not None and recipient.lower() not in (sender,'0x'+'00'*20),'invalid named recipient')
        recipient=recipient.lower()
        amounts=_parse(amounts_json,2048)
        _require(isinstance(amounts,dict) and 1<=len(amounts)<=8,'invalid amount vector')
        _require(all(key in lot['quantities'] and type(value) is int and 1<=value<=lot['quantities'][key] for key,value in amounts.items()),'amount exceeds available quantity or invalid integer')
        _require(len(b['offers'])<64,'batch offer capacity')
        revision=lot['revision']+1
        offer_binding={'chain_id':int(gl.message.chain_id),'contract':gl.message.contract_address.as_hex.lower(),'batch_id':batch_id,'source_lot':lot_id,'source_revision':revision,'sender':sender,'recipient':recipient,'amounts':amounts,'nonce':nonce,'created_at':_now(),'deadline':_now()+ttl_seconds,'manifest_sha256':b['manifest_sha256']}
        offer_id=_hash(['BatchCustody-v1-offer',offer_binding])
        _require(offer_id not in self.offers,'offer collision')
        self.offers[offer_id]=_canon(dict(offer_binding,offer_id=offer_id,status='PENDING',finished_at=0,recipient_lot='',remainder_lot=''))
        lot['status']='LOCKED';lot['revision']=revision;lot['locked_offer']=offer_id
        self._save_lot(lot_id,lot)
        b['offers'].append(offer_id);self.batches[batch_id]=_canon(b)
        self.used_nonces[nonce_key]=offer_id
        return offer_id

    def _pending(self,offer_id: str) -> tuple:
        offer=self._offer(offer_id)
        _require(offer['status']=='PENDING','offer not pending')
        lot=self._lot(offer['source_lot'])
        _require(lot['status']=='LOCKED' and lot['locked_offer']==offer_id and lot['revision']==offer['source_revision'],'source lock mismatch')
        return offer,lot

    @gl.public.write
    def accept_transfer(self,offer_id: str) -> dict:
        offer,lot=self._pending(offer_id)
        _require(gl.message.sender_address.as_hex.lower()==offer['recipient'],'recipient only')
        _require(_now()<offer['deadline'],'offer expired')
        b=self._batch(offer['batch_id'])
        remainder={key:value-offer['amounts'].get(key,0) for key,value in lot['quantities'].items() if value-offer['amounts'].get(key,0)>0}
        _require(len(b['lots'])+(2 if remainder else 1)<=64,'batch lot capacity')
        # Freeze pre-transition offer data. The receipt must not refer back to
        # the subsequently mutated offer or to its own acceptance_capture.
        packet=_capture(b['manifest'],{'operation':'accept','accepted_at':_now(),'offer':json.loads(_canon(offer)),'source_quantities':lot['quantities']})
        _require(packet['manifest_sha256']==b['manifest_sha256'],'manifest changed')
        recipient_lot=_hash(['BatchCustody-v1-output',offer_id,'recipient'])
        remainder_lot=_hash(['BatchCustody-v1-output',offer_id,'remainder']) if remainder else ''
        self._new_lot(recipient_lot,offer['batch_id'],offer['recipient'],offer['amounts'],offer_id,_now())
        b['lots'].append(recipient_lot)
        if remainder:
            self._new_lot(remainder_lot,offer['batch_id'],offer['sender'],remainder,offer_id,_now())
            b['lots'].append(remainder_lot)
        lot['status']='SPENT';lot['locked_offer']=''
        self._save_lot(offer['source_lot'],lot)
        offer['status']='ACCEPTED';offer['finished_at']=_now();offer['recipient_lot']=recipient_lot;offer['remainder_lot']=remainder_lot;offer['acceptance_capture']=packet
        self.offers[offer_id]=_canon(offer);self.batches[offer['batch_id']]=_canon(b)
        return {'recipient_lot':recipient_lot,'remainder_lot':remainder_lot}

    def _release(self,offer_id: str,offer: dict,lot: dict,status: str) -> None:
        offer['status']=status;offer['finished_at']=_now()
        lot['status']='ACTIVE';lot['locked_offer']=''
        self.offers[offer_id]=_canon(offer)
        self._save_lot(offer['source_lot'],lot)

    @gl.public.write
    def cancel_transfer(self,offer_id: str) -> None:
        offer,lot=self._pending(offer_id)
        _require(gl.message.sender_address.as_hex.lower()==offer['sender'],'sender only')
        self._release(offer_id,offer,lot,'CANCELED')

    @gl.public.write
    def expire_transfer(self,offer_id: str) -> None:
        offer,lot=self._pending(offer_id)
        _require(_now()>=offer['deadline'],'offer not expired')
        self._release(offer_id,offer,lot,'EXPIRED')

    @gl.public.view
    def get_batch(self,batch_id: str) -> dict:
        return self._batch(batch_id)

    @gl.public.view
    def get_lot(self,lot_id: str) -> dict:
        return self._lot(lot_id)

    @gl.public.view
    def get_offer(self,offer_id: str) -> dict:
        return self._offer(offer_id)

    @gl.public.view
    def audit_batch(self,batch_id: str) -> dict:
        b=self._batch(batch_id);totals={key:0 for key in b['initial_totals']};active=0;locked=0
        for lot_id in b['lots']:
            lot=self._lot(lot_id)
            if lot['status'] in ('ACTIVE','LOCKED'):
                for key,value in lot['quantities'].items():
                    totals[key]+=value
                if lot['status']=='LOCKED':
                    locked+=1
                else:
                    active+=1
        return {'initial_totals':b['initial_totals'],'live_totals':totals,'conserved':_canon(totals)==_canon(b['initial_totals']),'active_lots':active,'locked_lots':locked,'total_lots':len(b['lots']),'total_offers':len(b['offers'])}

    @gl.public.view
    def get_configuration(self) -> dict:
        return {'issuer':self.issuer.as_hex.lower(),'protocol':'BatchCustody-v1','max_items':8,'max_lots':64,'max_offers':64,'max_content_bytes':16384}
