import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'系统设计师'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import system as app

class CatalogTests(unittest.TestCase):
    def setUp(self): self.s,self.p,self.c=app.load_catalog()
    def test_full_catalog_and_five_distinct_levels(self):
        pools=app.validate_catalog(self.s,self.p,self.c)
        self.assertEqual(len(pools),26)
        self.assertTrue(all(len(ss)>10 for ss in pools.values()))
        for skill in self.s['skills']:
            self.assertEqual(len({v['text'] for v in skill['levels']}),5,skill['id'])
    def test_initial_prices_and_rewards(self):
        self.assertEqual({p['id']:p['price_base_points'] for p in self.p['pools']},app.EXPECTED)
        self.assertEqual([self.c['reward_base_points'][name] for name in ['初级兽兵','中级兽兵','高级兽兵','初级兽将','中级兽将','高级兽将','初级领主','中级领主','高级领主','王级怪兽','皇级怪兽']],[1,2,3,10,20,30,100,200,300,1000,3000])
    def test_identity_distribution(self):
        pools=app.validate_catalog(self.s,self.p,self.c)
        for pid in ['metal','fire']:
            self.assertGreater(sum(s['role']=='攻击' for s in pools[pid]),len(pools[pid])/2)
        self.assertGreater(sum(s['role']=='防御' for s in pools['earth']),len(pools['earth'])/2)
    def test_duplicate_skill_id_rejected(self):
        self.s['skills'].append(copy.deepcopy(self.s['skills'][0]))
        with self.assertRaises(ValueError): app.validate_catalog(self.s,self.p,self.c)
    def test_missing_level_rejected(self):
        self.s['skills'][0]['levels'].pop()
        with self.assertRaises(ValueError): app.validate_catalog(self.s,self.p,self.c)
    def test_unknown_pool_rejected(self):
        self.s['skills'][0]['pools'].append('fake')
        with self.assertRaises(ValueError): app.validate_catalog(self.s,self.p,self.c)
    def test_numeric_overcap_rejected(self):
        self.s['skills'][0]['levels'][4]['parameters']['bonus_pct']=51
        with self.assertRaises(ValueError): app.validate_catalog(self.s,self.p,self.c)
    def test_fractional_target_rejected(self):
        next(s for s in self.s['skills'] if s['mechanic']=='targets')['levels'][0]['parameters']['targets']=1.5
        with self.assertRaises(ValueError): app.validate_catalog(self.s,self.p,self.c)
    def test_nonfinite_rejected(self):
        self.s['skills'][0]['levels'][0]['parameters']['bonus_pct']=float('inf')
        with self.assertRaises(ValueError): app.validate_catalog(self.s,self.p,self.c)
    def test_wrong_growth_rejected(self):
        self.s['skills'][0]['levels'][1]['parameters']['bonus_pct']=1
        with self.assertRaises(ValueError): app.validate_catalog(self.s,self.p,self.c)
    def test_data_parameter_and_text_consistent_with_initial_design(self):
        from tools.build_catalog import effect
        for s in self.s['skills']:
            for lv in s['levels']:
                expected=effect(s['mechanic'],s['subject'],next(iter(lv['parameters'].values())))
                self.assertEqual(expected['text'],lv['text'],s['id'])
                self.assertEqual(expected['parameters'],lv['parameters'],s['id'])
    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json'; p.write_text('{"id":1,"id":2}')
            with self.assertRaises(ValueError): app.read_json(p)

class DrawTests(unittest.TestCase):
    def setUp(self):
        self.s,self.p,self.c=app.load_catalog(); self.state=app.initial_state(self.c)
        app.entry(self.state,100000,'测试收入','仅内存',self.c)
    def offer(self,pool='metal',token=None): return app.create_offer(self.state,pool,self.s,self.p,self.c,token)
    def select_id(self,sid,pool):
        # 仅测试替换随机源，正式命令没有此接口。
        def pick(pop,n): return [sid]+[x for x in pop if x!=sid][:n-1]
        with patch.object(app.secrets.SystemRandom,'sample',side_effect=pick): self.offer(pool)
        return app.choose(self.state,1,self.s,self.p,self.c)
    def test_real_random_unique_and_unbiased_sampler_contract(self):
        candidates=app.eligible(self.s,'metal',{})
        with patch.object(app.secrets.SystemRandom,'sample',wraps=app.secrets.SystemRandom().sample) as sampler:
            offer=self.offer()
            sampler.assert_called_once_with(candidates,2)
        self.assertEqual(len(set(offer['choices'])),2)
        self.assertTrue(set(offer['choices'])<=set(candidates))
        # 均匀性由标准库无放回sample保证，不用波动的频率测试替代算法检查。
    def test_cross_pool_upgrade_and_global_full_removal(self):
        shared=next(s for s in self.s['skills'] if set(['metal','blade'])<=set(s['pools']))
        sid=shared['id']
        for n in range(5): self.assertEqual(self.select_id(sid,'metal' if n%2==0 else 'blade'),(sid,n+1))
        self.assertNotIn(sid,app.eligible(self.s,'metal',self.state['owned']))
        self.assertNotIn(sid,app.eligible(self.s,'blade',self.state['owned']))
        self.assertEqual(len(self.state['owned']),1)
    def test_charge_once_and_pending_prevents_reroll(self):
        self.offer(); old=copy.deepcopy(self.state)
        with self.assertRaises(ValueError): self.offer()
        self.assertEqual(self.state,old)
        app.choose(self.state,1,self.s,self.p,self.c)
        self.assertEqual(self.state['balance'],'99900')
        self.assertEqual(self.state['equipped'],[])
    def test_offer_persists_across_save_and_load(self):
        offer=self.offer()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'state.json'; app.atomic_save(p,self.state)
            loaded=app.read_json(p);app.check_state(loaded,self.s,self.c)
            self.assertEqual(loaded['pending_offer'],offer)
            app.choose(loaded,2,self.s,self.p,self.c)
            self.assertEqual(len(loaded['draw_history']),1)
    def test_invalid_choice_no_mutation(self):
        self.offer(); before=copy.deepcopy(self.state)
        with self.assertRaises(ValueError): app.choose(self.state,3,self.s,self.p,self.c)
        self.assertEqual(self.state,before)
    def test_insufficient_funds_no_change(self):
        self.state=app.initial_state(self.c); before=copy.deepcopy(self.state)
        with self.assertRaises(ValueError): self.offer()
        self.assertEqual(self.state,before)
    def test_empty_pool_no_charge(self):
        self.state['owned']={sid:5 for sid in app.eligible(self.s,'metal',{})}
        before=copy.deepcopy(self.state)
        with self.assertRaises(ValueError): self.offer()
        self.assertEqual(self.state,before)
    def test_single_candidate_full_price(self):
        ids=app.eligible(self.s,'metal',{});self.state['owned']={sid:5 for sid in ids[1:]}
        self.assertEqual(self.offer()['choices'],ids[:1])
        self.assertEqual(self.state['balance'],'99900')
    def test_free_reward_three_choices_and_no_duplicate_token(self):
        offer=self.offer(token='main-001');self.assertEqual(len(offer['choices']),3)
        self.assertEqual(self.state['balance'],'100000')
        app.choose(self.state,3,self.s,self.p,self.c)
        with self.assertRaises(ValueError): self.offer(token='main-001')
    def test_version_change_blocks_choice(self):
        self.offer();self.s['catalog_version']='1.0.1'
        before=copy.deepcopy(self.state)
        with self.assertRaises(ValueError): app.choose(self.state,1,self.s,self.p,self.c)
        self.assertEqual(self.state,before)
    def test_conversion_exact_income_expense_price_and_small_reward(self):
        self.state=app.initial_state(self.c)
        app.entry(self.state,1001,'测试','仅内存',self.c)
        self.offer();app.choose(self.state,1,self.s,self.p,self.c)
        app.upgrade_currency(self.state,self.c)
        self.assertEqual([self.state[k] for k in ['balance','total_income','total_expense']],['0.901','1.001','0.1'])
        self.offer();app.choose(self.state,1,self.s,self.p,self.c)
        app.entry(self.state,1,'测试','兽兵',self.c)
        self.assertEqual(self.state['balance'],'0.802')
        app.check_state(self.state,self.s,self.c)
        with self.assertRaises(ValueError): app.upgrade_currency(self.state,self.c)
    def test_pending_prevents_conversion(self):
        self.offer()
        with self.assertRaises(ValueError): app.upgrade_currency(self.state,self.c)
    def test_pool_can_really_be_exhausted(self):
        for sid in app.eligible(self.s,'metal',{}):
            for _ in range(5): self.select_id(sid,'metal')
        self.assertEqual(app.eligible(self.s,'metal',self.state['owned']),[])
        self.assertEqual(len(self.state['draw_history']),5*len(app.eligible(self.s,'metal',{})))

class CLITests(unittest.TestCase):
    def run_cli(self,state,*args):
        return subprocess.run([sys.executable,str(app.EXECUTOR_ROOT/'system.py'),'--state',str(state),*args],capture_output=True,text=True)
    def test_cli_full_flow_reject_duplicate_kill_and_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/'hero.json'
            for args in [('init',),('kill','初级兽将','10','--event','fight1'),('draw','metal'),('choose','1')]:
                r=self.run_cli(state,*args);self.assertEqual(r.returncode,0,r.stderr)
            s=app.read_json(state);sid=next(iter(s['owned']))
            self.assertEqual(self.run_cli(state,'equip',sid).returncode,0)
            self.assertNotEqual(self.run_cli(state,'kill','初级兽将','10','--event','fight1').returncode,0)
            self.assertEqual(self.run_cli(state,'unlock-slot','main_earth_end').returncode,0)
            self.assertNotEqual(self.run_cli(state,'unlock-slot','main_earth_end').returncode,0)
            self.assertNotEqual(self.run_cli(state,'init').returncode,0)
            final=app.read_json(state);self.assertEqual(final['slots'],4);self.assertEqual(final['equipped'],[sid])
            self.assertTrue(state.with_suffix('.md').exists())
    def test_three_slots_and_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/'hero.json';self.run_cli(state,'init')
            s=app.read_json(state)
            skills=app.load_catalog()[0]['skills'][:4]
            s['owned']={x['id']:1 for x in skills};app.atomic_save(state,s)
            for skill in skills[:3]: self.assertEqual(self.run_cli(state,'equip',skill['id']).returncode,0)
            self.assertNotEqual(self.run_cli(state,'equip',skills[3]['id']).returncode,0)
            self.assertEqual(len(app.read_json(state)['equipped']),3)
    def test_negative_kill_and_unknown_tier_do_not_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/'hero.json';self.run_cli(state,'init');raw=state.read_bytes()
            self.assertNotEqual(self.run_cli(state,'kill','初级兽兵','-1','--event','bad').returncode,0)
            self.assertNotEqual(self.run_cli(state,'kill','恒星级','1','--event','bad').returncode,0)
            self.assertEqual(state.read_bytes(),raw)
    def test_two_processes_one_offer_one_charge(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/'hero.json';self.run_cli(state,'init')
            self.run_cli(state,'kill','初级兽将','20','--event','fund')
            command=[sys.executable,str(app.EXECUTOR_ROOT/'system.py'),'--state',str(state),'draw','metal']
            procs=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
            for p in procs: p.communicate(timeout=10)
            self.assertEqual(sorted(p.returncode for p in procs),[0,1])
            result=app.read_json(state)
            self.assertEqual(result['balance'],'100')
            self.assertEqual(len(result['ledger']),2)
            self.assertEqual(len(result['pending_offer']['choices']),2)

class LayoutTests(unittest.TestCase):
    def test_existing_character_and_catalog_have_one_canonical_location(self):
        self.assertTrue((app.ADMIN_ROOT/'state'/'character.json').is_file())
        self.assertTrue((app.DESIGN_ROOT/'data'/'skills.json').is_file())
        self.assertFalse((app.ROOT/'state').exists())
        self.assertFalse((app.ROOT/'data').exists())
        from tools.build_catalog import ROOT as builder_root
        self.assertEqual(builder_root,app.DESIGN_ROOT)

    def test_command_can_run_outside_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([sys.executable,str(app.EXECUTOR_ROOT/'system.py'),'validate'],cwd=tmp,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('PASS',result.stdout)

    def test_render_preserves_three_role_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)
            report=app.render_catalog(*app.load_catalog(),root=target)
            self.assertEqual(report['validation'],'PASS')
            self.assertEqual(len(list((target/'系统设计师'/'docs'/'技能池').glob('*.md'))),26)
            self.assertTrue((target/'抽奖执行器'/'reports'/'catalog_validation.json').is_file())
            self.assertFalse((target/'docs').exists())
            self.assertFalse((target/'reports').exists())

    def test_default_state_uses_administrator_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            admin=Path(tmp)/'设定管理员'
            with patch.object(app,'ADMIN_ROOT',admin),patch.object(sys,'argv',['system.py','init']),contextlib.redirect_stdout(io.StringIO()):
                app.main()
            saved=app.read_json(admin/'state'/'character.json')
            self.assertEqual(saved['balance'],'0')
            self.assertEqual(saved['slots'],3)
            self.assertTrue((admin/'state'/'character.md').is_file())

if __name__=='__main__': unittest.main()
