#!/usr/bin/env python3
"""吞噬星空同人割草系统：Python 3.9+，无第三方依赖。"""
import argparse
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

ROOT = Path(__file__).resolve().parent
ROLES = {'攻击','防御','控制','辅助'}
MECHANICS = {'boost','range','saving','reduction','projectile','hits','chain','pierce','orbit','return','shield','orbit_shield','targets','zones','duration','dot','burn','radius','death','trail','block','cooldown','reflect','dodge','decoy','tethers','marks','stacks','amplitude','gene','regen','kill_recovery','conversion','clone','contract','commands','slow','delay','warning','transfer'}
CAPS = {'bonus_pct':50,'range_bonus_pct':50,'cost_reduction_pct':25,'damage_reduction_pct':25,'reflection_pct':25,'dodge_bonus_pp':10,'per_stack_bonus_pct':10,'amplitude_bonus_pct':50,'gene_bonus_pct':10,'heal_pct_per_s':1,'recovery_pct':5,'conversion_pct':30,'slow_pct':25,'clones':3,'duration_s':6,'delay_s':1,'warning_s':0.5,'radius_factor':0.8,'lifespan_s':60}
COUNTS = {'projectiles','hits','targets','orbit_count','shields','zones','decoys','tethers','marks','clones','contracts','command_channels'}
EXPECTED = {'metal':100,'wood':100,'water':100,'fire':100,'earth':100,'wind':100,'lightning':100,'light':100,'space':1000,'time':1000,'blade':200,'sword':200,'spear':200,'staff':200,'axe':200,'unarmed':200,'movement':200,'controller':200,'illusion':300,'soul':500,'beast':300,'body':200,'gene':1000,'special':500,'training':1000,'will':10000}

def read_json(path):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result: raise ValueError(f'JSON重复键：{k}（{path}）')
            result[k]=v
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique)

def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def catalog_hash(skills,pools,config):
    return hashlib.sha256(canonical([skills,pools,config])).hexdigest()

def load_catalog(root=ROOT):
    data=root/'data'
    return read_json(data/'skills.json'),read_json(data/'skill_pools.json'),read_json(data/'config.json')

def validate_catalog(skills,pools,config):
    errors=[]
    def require(ok,msg):
        if not ok: errors.append(msg)
    require(skills.get('schema_version')==pools.get('schema_version')==config.get('schema_version')==1,'schema_version必须为1')
    require(bool(skills.get('catalog_version')),'缺少catalog_version')
    plist=pools.get('pools',[]); slist=skills.get('skills',[])
    pids=[p.get('id') for p in plist]; sids=[s.get('id') for s in slist]
    require(len(pids)==26 and set(pids)==set(EXPECTED),'必须完整保留26个约定技能池')
    require(len(set(pids))==len(pids),'技能池ID重复')
    require(len(set(sids))==len(sids),'技能ID重复：同ID只能有一条权威记录')
    require(len({s.get('name') for s in slist})==len(slist),'技能重名：请复用统一ID或明确改名')
    members={pid:[] for pid in pids}
    for p in plist:
        require(type(p.get('price_base_points'))==int and p['price_base_points']>0,f'{p.get("id")}价格必须为正整数原始积分')
        require(bool(p.get('name')) and bool(p.get('identity')),f'{p.get("id")}缺少名称或定位')
    param_keys=set(CAPS)|COUNTS|{'cooldown_s','preparation_s'}
    for s in slist:
        sid=s.get('id','<缺失ID>'); ownership=s.get('pools',[])
        require(isinstance(sid,str) and bool(re.fullmatch(r'[A-Za-z0-9_]+',sid)),f'{sid}需要只包含ASCII字母、数字或下划线的稳定ID')
        require(s.get('role') in ROLES,f'{sid}主功能无效')
        require(s.get('mechanic') in MECHANICS,f'{sid}机制无效')
        require(bool(s.get('subject')) and bool(s.get('activation')),f'{sid}缺少效果语义或触发方式')
        require(bool(ownership) and len(set(ownership))==len(ownership),f'{sid}归属为空或重复')
        for pid in ownership:
            require(pid in members,f'{sid}归属未知池{pid}')
            if pid in members: members[pid].append(s)
        base=s.get('baseline',{})
        require(base.get('energy_budget_pct')==10 and base.get('cooldown_s')==8 and bool(base.get('range')),f'{sid}基础预算/冷却/R缺失或违反统一约定')
        require(bool(s.get('requirements')),f'{sid}缺少使用条件')
        levels=s.get('levels',[])
        require(len(levels)==5 and [v.get('level') for v in levels]==[1,2,3,4,5],f'{sid}必须完整且按序固定Lv1–Lv5')
        previous=None
        for level in levels:
            params=level.get('parameters',{})
            require(bool(level.get('text')) and bool(params),f'{sid}缺少等级文本或数值')
            require(len(params)==1,f'{sid}每级须有一项明确的成长参数，其他条件写入固定文本')
            for key,value in params.items():
                numeric=type(value) in (int,float) and Decimal(str(value)).is_finite()
                require(numeric,f'{sid}.{key}不是有限数值')
                if not numeric: continue
                require(key in param_keys,f'{sid}.{key}未注册参数，请同步扩展规范及校验')
                require(value>0,f'{sid}.{key}必须大于0')
                if key in CAPS: require(value<=CAPS[key],f'{sid}.{key}超过单技能上限{CAPS[key]}')
                if key in COUNTS: require(type(value)==int and value<=12,f'{sid}.{key}必须为1–12的整数')
                if key in {'cooldown_s','preparation_s'}: require(8<=value<=86400,f'{sid}.{key}时间范围越界')
                if previous:
                    require(key in previous,f'{sid}等级间参数不一致')
                    if key in previous:
                        decreasing=key in {'cooldown_s','preparation_s'}
                        require(value<=previous[key] if decreasing else value>=previous[key],f'{sid}等级成长方向错误')
            previous=params
    for pid,ss in members.items():
        require(len(ss)>=max(11,config.get('min_skills_per_pool',11)),f'{pid}仅{len(ss)}个，须超过10个')
    require(config.get('initial_slots')==3,'初始技能槽必须为3')
    require(config.get('max_skill_level')==5,'技能上限必须为5')
    require(config.get('normal_choices')==2 and config.get('reward_choices')==3,'普通二选一、奖励三选一')
    require(config.get('quality_enabled') is False and config.get('fusion_enabled') is False,'品质及融合必须关闭')
    currency=config.get('currency',{})
    require(currency.get('conversion_divisor')==1000 and currency.get('conversion_once') is True and currency.get('decimal_places')==3,'换算必须一次1000:1并保留三位精度')
    require(currency.get('initial_balance_base_points')==0,'初始积分应为0，示例收入请另行记账')
    milestones=config.get('slot_milestones',[])
    require(len(milestones)==3 and len({x.get('id') for x in milestones})==3 and all(x.get('slots_added')==1 for x in milestones),'初版仅设3次主线各扩1槽')
    reward=config.get('reward_base_points',{})
    require(all(type(v)==int and v>0 for v in reward.values()),'奖励必须为正整数原始积分')
    require(all(n in reward for n in ['初级兽兵','中级兽兵','高级兽兵','初级兽将','中级兽将','高级兽将','初级领主','中级领主','高级领主','王级怪兽','皇级怪兽']),'地球怪兽固定奖励档位不完整')
    limits=config.get('limits',{})
    require(limits=={'single_bonus_pct':50,'single_damage_reduction_pct':25,'total_bonus_pct':50,'total_damage_reduction_pct':50,'total_cost_reduction_pct':50,'total_slow_pct':50,'total_dodge_bonus_pp':30,'recovery_per_10s_pct':5,'control_duration_s':6,'max_clones':3},'数值总上限不符合初版规范；改版时需同步修改校验及说明')
    if errors: raise ValueError('校验失败：\n'+'\n'.join(errors))
    return members

def money(value):
    d=Decimal(str(value))
    if not d.is_finite(): raise ValueError('积分必须为有限数值')
    return format(d,'f') if d%1 else str(int(d))

def stamp(): return datetime.now(timezone.utc).isoformat()

def initial_state(config):
    return {'schema_version':1,'name':'主角（待命名）','realm':'学徒级','currency_unit':'旧积分','converted':False,
      'balance':'0','total_income':'0','total_expense':'0','owned':{},'equipped':[],
      'slots':config['initial_slots'],'claimed_milestones':[],'claimed_rewards':[],
      'pending_offer':None,'ledger':[],'draw_history':[],'revision':0}

def divisor(state,config): return config['currency']['conversion_divisor'] if state['converted'] else 1

def eligible(skills,pool,owned):
    return [s['id'] for s in skills['skills'] if pool in s['pools'] and owned.get(s['id'],0)<5]

def check_state(state,skills,config):
    ids={s['id'] for s in skills['skills']}
    if state.get('schema_version')!=1: raise ValueError('角色schema_version错误')
    for key in ('balance','total_income','total_expense'):
        val=Decimal(state[key]); scaled=val*divisor(state,config)
        if not val.is_finite() or val<0 or scaled!=scaled.to_integral_value(): raise ValueError(f'{key}积分非法或精度不足')
    if Decimal(state['balance'])!=Decimal(state['total_income'])-Decimal(state['total_expense']): raise ValueError('余额与累计收支不一致')
    if any(sid not in ids or type(lv)!=int or not 1<=lv<=5 for sid,lv in state['owned'].items()): raise ValueError('角色技能ID或等级错误')
    if len(state['equipped'])!=len(set(state['equipped'])) or len(state['equipped'])>state['slots'] or any(sid not in state['owned'] for sid in state['equipped']): raise ValueError('装备技能无效/重复/超槽')
    milestone_ids={m['id'] for m in config['slot_milestones']}
    claimed=state['claimed_milestones']
    if len(set(claimed))!=len(claimed) or not set(claimed)<=milestone_ids or state['slots']!=3+len(claimed): raise ValueError('扩槽与主线记录不一致')
    if state['currency_unit']!=('新积分' if state['converted'] else '旧积分'): raise ValueError('积分单位与换算状态不一致')
    net=sum(e['delta_base_points'] for e in state['ledger'])
    income=sum(e['delta_base_points'] for e in state['ledger'] if e['delta_base_points']>0)
    expense=-sum(e['delta_base_points'] for e in state['ledger'] if e['delta_base_points']<0)
    if (net,income,expense)!=tuple(int(Decimal(state[k])*divisor(state,config)) for k in ('balance','total_income','total_expense')): raise ValueError('账本与角色收支不一致')

def entry(state,delta_base,kind,detail,config):
    value=Decimal(delta_base)/divisor(state,config)
    if Decimal(state['balance'])+value<0: raise ValueError('积分不足')
    state['balance']=money(Decimal(state['balance'])+value)
    field='total_income' if delta_base>0 else 'total_expense'
    state[field]=money(Decimal(state[field])+abs(value))
    state['ledger'].append({'at':stamp(),'kind':kind,'detail':detail,'delta_base_points':delta_base,'amount':money(value),'unit':state['currency_unit']})

def create_offer(state,pool,skills,pools,config,reward_token=None):
    if state['pending_offer']: raise ValueError('已有待选择候选，请先choose；不能重抽或取消')
    ps={p['id']:p for p in pools['pools']}
    if pool not in ps: raise ValueError('未知技能池')
    if reward_token and reward_token in state['claimed_rewards']: raise ValueError('该剧情奖励编号已使用')
    candidates=eligible(skills,pool,state['owned'])
    if not candidates: raise ValueError('该池已抽空，不扣积分')
    count=min(3 if reward_token else 2,len(candidates))
    cost=0 if reward_token else ps[pool]['price_base_points']
    if Decimal(state['balance'])*divisor(state,config)<cost: raise ValueError('积分不足')
    # 正式抽取只使用操作系统熵，不提供可反复试种子的接口。
    choices=secrets.SystemRandom().sample(candidates,count)
    if cost: entry(state,-cost,'抽取',pool,config)
    if reward_token: state['claimed_rewards'].append(reward_token)
    state['pending_offer']={'id':secrets.token_hex(8),'at':stamp(),'pool':pool,'choices':choices,
      'catalog_hash':catalog_hash(skills,pools,config),'candidate_count':len(candidates),
      'price_base_points':cost,'reward_token':reward_token,
      'owned_levels_at_offer':{sid:state['owned'].get(sid,0) for sid in choices}}
    return copy.deepcopy(state['pending_offer'])

def choose(state,number,skills,pools,config):
    offer=state['pending_offer']
    if not offer: raise ValueError('没有待选择候选，请先draw')
    if offer['catalog_hash']!=catalog_hash(skills,pools,config): raise ValueError('抽取后技能库/配置已变更；请恢复抽取时版本再选择，禁止重抽改结果')
    if not 1<=number<=len(offer['choices']): raise ValueError('选项编号越界')
    sid=offer['choices'][number-1]
    if state['owned'].get(sid,0)!=offer['owned_levels_at_offer'][sid]: raise ValueError('待选技能等级已被外部修改')
    old=state['owned'].get(sid,0)
    if old>=5: raise ValueError('该技能已满级')
    state['owned'][sid]=old+1
    # 新技能始终入库；显式equip才占用槽位。
    state['draw_history'].append({**offer,'selected':sid,'from_level':old,'to_level':old+1,'resolved_at':stamp()})
    state['pending_offer']=None
    return sid,old+1

def upgrade_currency(state,config):
    if state['pending_offer']: raise ValueError('先完成待选抽取，再进行系统升级')
    if state['converted']: raise ValueError('已完成1000:1换算，不可重复换算')
    for key in ('balance','total_income','total_expense'):
        state[key]=money(Decimal(state[key])/config['currency']['conversion_divisor'])
    state['converted']=True; state['currency_unit']='新积分'; state['realm']='行星级'
    # 历史账本保留原币种及原始金额；状态视图按当前币种统一显示。
    state['ledger'].append({'at':stamp(),'kind':'系统升级','detail':'首次进入行星级，余额及累计收支1000:1换算','delta_base_points':0,'amount':'0','unit':'新积分'})

def atomic_save(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

@contextmanager
def locked(path):
    import fcntl  # macOS / Linux；避免两个终端同时扣款和覆写。
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with Path(str(path)+'.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(f,fcntl.LOCK_UN)

def status_md(state,skills,config):
    sm={s['id']:s for s in skills['skills']}
    lines=['# 角色状态','',f'姓名：{state["name"]}  ',f'境界：{state["realm"]}  ',f'积分：{state["balance"]} {state["currency_unit"]}  ',f'累计收入：{state["total_income"]}；累计支出：{state["total_expense"]}  ',f'槽位：{len(state["equipped"])}/{state["slots"]}  ',f'存档修订：{state["revision"]}；已完成主线扩槽：{len(state["claimed_milestones"])}','',
      '本文件由存档生成。JSON为唯一状态源；编辑此Markdown不会修改存档。','', '## 已获得技能','', '| ID | 技能 | 等级 | 状态 | 当前固定效果 |','|---|---|---:|---|---|']
    for sid,lv in state['owned'].items():
        s=sm[sid]
        lines.append(f'| {sid} | {s["name"]} | Lv{lv} | {"装备" if sid in state["equipped"] else "仓库"} | {s["levels"][lv-1]["text"]} |')
    if not state['owned']: lines.append('| — | 尚无技能 | — | — | 首次抽取后入库，再手动装备 |')
    lines+=['','## 待选抽取','']
    offer=state['pending_offer']
    if offer:
        lines.append(f'抽取编号：{offer["id"]}；技能库摘要：`{offer["catalog_hash"]}`')
        for n,sid in enumerate(offer['choices'],1):
            lv=state['owned'].get(sid,0)+1
            lines.append(f'{n}. {sm[sid]["name"]}（{sid}）→ Lv{lv}：{sm[sid]["levels"][lv-1]["text"]}')
    else: lines.append('无。')
    lines+=['','## 最近收支（按当前积分单位显示）','','| 时间 UTC | 事项 | 原始旧积分 | 当前单位金额 |','|---|---|---:|---:|']
    for e in state['ledger'][-20:]:
        lines.append(f'| {e["at"]} | {e["kind"]}：{e["detail"]} | {e["delta_base_points"]} | {money(Decimal(e["delta_base_points"])/divisor(state,config))} |')
    return '\n'.join(lines)+'\n'

def render_catalog(skills,pools,config,root=ROOT):
    members=validate_catalog(skills,pools,config)
    docs=root/'docs'/'技能池'; docs.mkdir(parents=True,exist_ok=True)
    summary=['# 技能池目录','','技能权威定义在 `data/skills.json`。此处按池展开，同ID跨池共享等级。每级都列完整效果；共同预算及约束见《数值规范》。','', '| 技能池 | ID | 旧积分价格 | 新积分价格 | 技能数 | 攻击 | 防御 | 控制 | 辅助 |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for p in pools['pools']:
        ss=members[p['id']]; counts={r:sum(s['role']==r for s in ss) for r in ROLES}
        summary.append(f'| [{p["name"]}](技能池/{p["id"]}.md) | {p["id"]} | {p["price_base_points"]} | {money(Decimal(p["price_base_points"])/1000)} | {len(ss)} | {counts["攻击"]} | {counts["防御"]} | {counts["控制"]} | {counts["辅助"]} |')
        lines=[f'# {p["name"]}','','定位：'+p['identity'],f'抽取价格：{p["price_base_points"]}旧积分 / {money(Decimal(p["price_base_points"])/1000)}新积分；{len(ss)}项，同池等概率。','']
        for s in ss:
            lines += [f'## {s["name"]}（{s["id"]}）','',f'主功能：{s["role"]}；所属池：'+ '、'.join(s['pools']),f'触发：{s["activation"]}。',
              '共同条件：'+'；'.join(s['requirements'])+'。','', '| 等级 | 固定效果 |','|---|---|']
            lines += [f'| Lv{v["level"]} | {v["text"]} |' for v in s['levels']]
            lines+=['']
        (docs/(p['id']+'.md')).write_text('\n'.join(lines),encoding='utf-8')
    (root/'docs'/'技能池目录.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    report={'catalog_hash':catalog_hash(skills,pools,config),'unique_skills':len(skills['skills']),
      'pool_memberships':sum(map(len,members.values())),'shared_skills':sum(len(s['pools'])>1 for s in skills['skills']),
      'pools':{pid:{'count':len(ss),'roles':{r:sum(s['role']==r for s in ss) for r in sorted(ROLES)}} for pid,ss in members.items()},'validation':'PASS'}
    atomic_save(root/'reports'/'catalog_validation.json',report)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,default=ROOT/'state'/'character.json',help='独立存档路径，试抽请指向examples或/tmp')
    sub=parser.add_subparsers(dest='cmd',required=True)
    for name in ('validate','render','init','status','upgrade-planetary','pools'): sub.add_parser(name)
    draw=sub.add_parser('draw'); draw.add_argument('pool'); draw.add_argument('--reward-token',help='仅用于已获得的剧情奖励；免费三选一，编号一次性')
    ch=sub.add_parser('choose'); ch.add_argument('number',type=int)
    for name in ('equip','unequip'):
        p=sub.add_parser(name); p.add_argument('skill')
    kill=sub.add_parser('kill'); kill.add_argument('tier'); kill.add_argument('count',type=int); kill.add_argument('--event',required=True,help='唯一战斗事件编号，防止重复记账')
    slot=sub.add_parser('unlock-slot'); slot.add_argument('milestone')
    args=parser.parse_args()
    skills,pools,config=load_catalog(); members=validate_catalog(skills,pools,config)
    if args.cmd=='validate':
        print(f'PASS：26池，{len(skills["skills"])}个唯一技能，{sum(map(len,members.values()))}个池内名额；每池最少{min(map(len,members.values()))}项。'); return
    if args.cmd=='render':
        r=render_catalog(skills,pools,config); print(f'已生成26池中文技能表及校验报告：{r["unique_skills"]}个唯一技能。'); return
    if args.cmd=='pools':
        for p in pools['pools']: print(f'{p["id"]:12} {p["name"]:8} {p["price_base_points"]}旧积分 / {money(Decimal(p["price_base_points"])/1000)}新积分  {len(members[p["id"]])}项')
        return
    with locked(args.state):
        if args.cmd=='init':
            if args.state.exists(): raise ValueError('存档已存在，拒绝覆盖')
            state=initial_state(config)
        else:
            if not args.state.exists(): raise ValueError('存档不存在，请先init')
            state=read_json(args.state); check_state(state,skills,config)
        changed=args.cmd!='status'
        if args.cmd=='draw': create_offer(state,args.pool,skills,pools,config,args.reward_token)
        elif args.cmd=='choose':
            sid,lv=choose(state,args.number,skills,pools,config); print(f'已获得/升级 {sid} → Lv{lv}（入库；equip装备）。')
        elif args.cmd=='kill':
            if args.count<=0: raise ValueError('击杀数必须大于0')
            if not args.event.strip(): raise ValueError('战斗事件编号不可为空')
            if args.tier not in config['reward_base_points']: raise ValueError('未知奖励档位；请先通过版本更新添加，不临时估算')
            if any(e['kind']=='击杀' and e['detail']['event']==args.event for e in state['ledger']): raise ValueError('该事件已记账')
            entry(state,config['reward_base_points'][args.tier]*args.count,'击杀',{'event':args.event,'tier':args.tier,'count':args.count},config)
        elif args.cmd=='upgrade-planetary': upgrade_currency(state,config)
        elif args.cmd=='equip':
            if args.skill not in state['owned']: raise ValueError('尚未获得该技能')
            if args.skill in state['equipped']: raise ValueError('技能已装备')
            if len(state['equipped'])>=state['slots']: raise ValueError('槽位已满，请先unequip再equip')
            state['equipped'].append(args.skill)
        elif args.cmd=='unequip':
            if args.skill not in state['equipped']: raise ValueError('该技能未装备')
            state['equipped'].remove(args.skill)
        elif args.cmd=='unlock-slot':
            if args.milestone not in {m['id'] for m in config['slot_milestones']}: raise ValueError('无此主线里程碑')
            if args.milestone in state['claimed_milestones']: raise ValueError('该主线已扩槽')
            state['claimed_milestones'].append(args.milestone); state['slots']+=1
        check_state(state,skills,config)
        if changed:
            state['revision']+=1; atomic_save(args.state,state)
        md=status_md(state,skills,config)
        args.state.with_suffix('.md').write_text(md,encoding='utf-8')
        if args.cmd in {'draw','status'}: print(md)
        else: print(f'已保存：{args.state}；余额 {state["balance"]}{state["currency_unit"]}。')

if __name__=='__main__':
    try: main()
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(str(error),file=sys.stderr); sys.exit(1)
