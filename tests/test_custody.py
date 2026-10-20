"""Real GenLayer storage/state transitions; only public HTTP is mocked."""
import copy
import json
from pathlib import Path
import re
import pytest
from gltest.direct import create_address

ROOT=Path(__file__).parents[1]
MANIFEST=json.loads((ROOT/'fixtures/manifest.json').read_text())
ALICE=create_address('custodian-alice')
BOB=create_address('custodian-bob')
CAROL=create_address('custodian-carol')

def hex_address(value):
    # Before SDK setup create_address returns bytes; afterwards it returns Address.
    return value.as_hex.lower() if hasattr(value,'as_hex') else '0x'+value.hex()

def deploy(vm,build):
    vm.warp('2026-10-21T00:00:00Z')
    c=build(str(ROOT/'batch_custody.py'),sdk_version='v0.2.12')
    assert hasattr(c,'open_batch'),'BatchCustody API not implemented'
    return c

def serve(vm,changed=False):
    for item in MANIFEST:
        body=(ROOT/('fixtures/public-readme.txt' if item['item_id']=='guide' else 'fixtures/public-license.txt')).read_text(encoding='utf-8')
        vm.mock_web(re.escape(item['url']),{'status':200,'body':body+('changed' if changed else '')})

def batch(vm,c):
    serve(vm)
    return c.open_batch('manuals',json.dumps(MANIFEST))

def offer(c,lot,receiver=ALICE,nonce='nonce1',amounts=None,revision=0,ttl=60):
    return c.propose_transfer('manuals',lot,revision,json.dumps(amounts or {'guide':4,'license':2}),hex_address(receiver),nonce,ttl)


@pytest.mark.parametrize('repo',['.','..'])
def test_dot_repository_cannot_change_the_commit_namespace(direct_vm,direct_deploy,repo):
    c=deploy(direct_vm,direct_deploy)
    values=copy.deepcopy(MANIFEST)
    for i,item in enumerate(values):
        body=(ROOT/('fixtures/public-readme.txt' if item['item_id']=='guide' else 'fixtures/public-license.txt')).read_text(encoding='utf-8')
        item['url']='https://raw.githubusercontent.com/example/'+repo+'/'+'a'*40+'/main/file'+str(i)+'.txt'
        direct_vm.mock_web(re.escape(item['url']),{'status':200,'body':body})
    with direct_vm.expect_revert('commit-pinned'):
        c.open_batch('dotrepo',json.dumps(values))

def test_named_acceptance_splits_conserved_public_manifest(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    assert c.get_lot(root)['status']=='LOCKED'
    assert c.audit_batch('manuals')['conserved'] is True
    with direct_vm.prank(ALICE):out=c.accept_transfer(oid)
    assert c.get_lot(root)['status']=='SPENT'
    assert c.get_lot(out['recipient_lot'])['quantities']=={'guide':4,'license':2}
    assert c.get_lot(out['remainder_lot'])['quantities']=={'guide':6,'license':5}
    assert c.get_lot(out['recipient_lot'])['holder']==hex_address(ALICE)
    assert c.audit_batch('manuals')['live_totals']=={'guide':10,'license':7}
    assert direct_vm.run_validator() is True

def test_only_named_recipient_can_accept(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    with direct_vm.prank(BOB):
        with direct_vm.expect_revert('recipient only'):c.accept_transfer(oid)
    with direct_vm.expect_revert('recipient only'):c.accept_transfer(oid)

def test_locked_and_spent_inputs_cannot_double_split(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    with direct_vm.expect_revert('not active'):offer(c,root,nonce='other',revision=1)
    with direct_vm.prank(ALICE):c.accept_transfer(oid)
    with direct_vm.prank(ALICE):
        with direct_vm.expect_revert('not pending'):c.accept_transfer(oid)
    with direct_vm.expect_revert('not active'):offer(c,root,nonce='third',revision=1)

def test_downstream_holder_can_transfer_received_lot(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    with direct_vm.prank(ALICE):out=c.accept_transfer(oid)
    with direct_vm.prank(ALICE):second=offer(c,out['recipient_lot'],BOB,'nonce1',{'guide':4,'license':2})
    with direct_vm.prank(BOB):out2=c.accept_transfer(second)
    assert out2['remainder_lot']==''
    assert c.get_lot(out2['recipient_lot'])['holder']==hex_address(BOB)
    assert c.audit_batch('manuals')['conserved'] is True

def test_cancellation_retains_revision_and_burns_sender_nonce(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    direct_vm.clear_mocks();c.cancel_transfer(oid)
    assert c.get_lot(root)['status']=='ACTIVE' and c.get_lot(root)['revision']==1
    with direct_vm.expect_revert('stale revision'):offer(c,root,nonce='fresh',revision=0)
    with direct_vm.expect_revert('nonce used'):offer(c,root,revision=1)
    with direct_vm.prank(ALICE):
        with direct_vm.expect_revert('not pending'):c.accept_transfer(oid)
    assert c.get_offer(offer(c,root,nonce='fresh',revision=1))['status']=='PENDING'

def test_expiry_boundary_allows_anyone_cleanup_offline(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    with direct_vm.prank(BOB):
        with direct_vm.expect_revert('not expired'):c.expire_transfer(oid)
    direct_vm.warp('2026-10-21T00:01:00Z');direct_vm.clear_mocks()
    with direct_vm.prank(ALICE):
        with direct_vm.expect_revert('expired'):c.accept_transfer(oid)
    with direct_vm.prank(BOB):c.expire_transfer(oid)
    assert c.get_offer(oid)['status']=='EXPIRED'
    assert c.get_lot(root)['status']=='ACTIVE'
    assert c.audit_batch('manuals')['live_totals']=={'guide':10,'license':7}

def test_unauthorized_issue_propose_cancel(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    with direct_vm.prank(CAROL):
        with direct_vm.expect_revert('issuer only'):c.open_batch('other',json.dumps(MANIFEST))
        with direct_vm.expect_revert('holder only'):offer(c,root)
        with direct_vm.expect_revert('sender only'):c.cancel_transfer(oid)

@pytest.mark.parametrize('amounts',[{'guide':11},{'unknown':1},{'guide':0},{'guide':True},{'guide':-1},{}])
def test_bad_quantities_never_reserve(direct_vm,direct_deploy,amounts):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c)
    with direct_vm.expect_revert('amount'):c.propose_transfer('manuals',root,0,json.dumps(amounts),hex_address(ALICE),'nonce1',60)
    assert c.get_lot(root)['status']=='ACTIVE'

def test_changed_source_prevents_accept_without_destroying_offer(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    direct_vm.clear_mocks();serve(direct_vm,True)
    with direct_vm.prank(ALICE):
        with direct_vm.expect_revert('SOURCE'):c.accept_transfer(oid)
    assert c.get_offer(oid)['status']=='PENDING'
    assert c.audit_batch('manuals')['conserved'] is True
    c.cancel_transfer(oid)
    assert c.get_lot(root)['status']=='ACTIVE'

def test_validator_recomputes_all_content_and_offer_binding(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c);oid=offer(c,root)
    with direct_vm.prank(ALICE):c.accept_transfer(oid)
    assert direct_vm.run_validator() is True
    assert direct_vm.run_validator(leader_result={'verified':True,'manifest':MANIFEST}) is False
    direct_vm.clear_mocks();serve(direct_vm,True)
    assert direct_vm.run_validator() is False

@pytest.mark.parametrize('kind',['duplicate','boolean','mutable','wrong-sha'])
def test_manifest_is_strict_and_content_locked(direct_vm,direct_deploy,kind):
    c=deploy(direct_vm,direct_deploy);serve(direct_vm);m=copy.deepcopy(MANIFEST)
    if kind=='duplicate':m.append(m[0])
    elif kind=='boolean':m[0]['quantity']=True
    elif kind=='mutable':m[0]['url']=m[0]['url'].replace('e685f1f12c4c357787d48390692a654baf576f03','main')
    else:m[0]['sha256']='00'*32
    with direct_vm.expect_revert():c.open_batch('bad',json.dumps(m))

def test_invalid_receiver_ttl_and_revision_do_not_lock(direct_vm,direct_deploy):
    c=deploy(direct_vm,direct_deploy);root=batch(direct_vm,c)
    with direct_vm.expect_revert('stale revision'):offer(c,root,revision=1)
    with direct_vm.expect_revert('TTL'):offer(c,root,ttl=59)
    with direct_vm.expect_revert('recipient'):c.propose_transfer('manuals',root,0,'{"guide":1}','0x'+'00'*20,'n',60)
    assert c.get_lot(root)['revision']==0
