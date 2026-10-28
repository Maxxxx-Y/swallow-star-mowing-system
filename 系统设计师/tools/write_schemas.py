"""从运行时参数注册表生成供编辑器使用的JSON Schema。"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'抽奖执行器'))
import system

ROOT=system.DESIGN_ROOT
BASE={'$schema':'https://json-schema.org/draft/2020-12/schema'}
S={'type':'string','minLength':1}
INT={'type':'integer','minimum':1}
def obj(props,required=None,**extra):
    return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False,**extra}
def arr(items,**extra): return {'type':'array','items':items,**extra}
def write(name,value):
    folder=ROOT/'schemas';folder.mkdir(exist_ok=True)
    (folder/name).write_text(json.dumps({**BASE,**value},ensure_ascii=False,indent=2)+'\n')

params={k:{'type':'number','exclusiveMinimum':0,'maximum':cap} for k,cap in system.CAPS.items()}
params.update({k:{'type':'integer','minimum':1,'maximum':12} for k in system.COUNTS})
params.update({k:{'type':'number','minimum':8,'maximum':86400} for k in ['cooldown_s','preparation_s']})
level=obj({'level':{'type':'integer','minimum':1,'maximum':5},'text':S,'parameters':{'type':'object','properties':params,'minProperties':1,'maxProperties':1,'additionalProperties':False}})
skill=obj({'id':{'type':'string','pattern':'^[A-Za-z0-9_]+$'},'name':S,'pools':arr({'enum':list(system.EXPECTED)},minItems=1,uniqueItems=True),'role':{'enum':sorted(system.ROLES)},'mechanic':{'enum':sorted(system.MECHANICS)},'subject':S,'activation':S,'baseline':obj({'energy_budget_pct':{'const':10},'cooldown_s':{'const':8},'range':S}),'requirements':arr(S,minItems=1),'levels':arr(level,minItems=5,maxItems=5)})
write('skills.schema.json',obj({'schema_version':{'const':1},'catalog_version':S,'skills':arr(skill,minItems=1)}))
pool=obj({'id':{'enum':list(system.EXPECTED)},'name':S,'category':S,'price_base_points':INT,'identity':S})
write('skill_pools.schema.json',obj({'schema_version':{'const':1},'pools':arr(pool,minItems=26,maxItems=26)}))
config=system.read_json(ROOT/'data'/'config.json')
config_props={}
for key,val in config.items():
    if key=='slot_milestones': config_props[key]=arr(obj({'id':S,'name':S,'slots_added':{'const':1}}),minItems=3,maxItems=3)
    elif key=='reward_base_points': config_props[key]={'type':'object','additionalProperties':INT,'minProperties':11}
    elif key=='currency': config_props[key]=obj({k:{'const':v} for k,v in val.items()})
    elif key=='limits': config_props[key]=obj({k:{'const':v} for k,v in val.items()})
    elif key in {'system_version','future_reward_policy'}: config_props[key]=S
    else: config_props[key]={'const':val}
write('config.schema.json',obj(config_props))
decimal={'type':'string','pattern':r'^\d+(\.\d{1,3})?$'}
offer=obj({'id':S,'at':S,'pool':{'enum':list(system.EXPECTED)},'choices':arr(S,minItems=1,maxItems=3,uniqueItems=True),'catalog_hash':{'type':'string','pattern':'^[0-9a-f]{64}$'},'candidate_count':INT,'price_base_points':{'type':'integer','minimum':0},'reward_token':{'type':['string','null']},'owned_levels_at_offer':{'type':'object','additionalProperties':{'type':'integer','minimum':0,'maximum':4}}})
draw_props=offer['properties'].copy();draw_props.update({'selected':S,'from_level':{'type':'integer','minimum':0,'maximum':4},'to_level':{'type':'integer','minimum':1,'maximum':5},'resolved_at':S})
ledger=obj({'at':S,'kind':S,'detail':{'type':['string','object']},'delta_base_points':{'type':'integer'},'amount':{'type':'string'},'unit':{'enum':['旧积分','新积分']}})
state_props={'schema_version':{'const':1},'name':S,'realm':S,'currency_unit':{'enum':['旧积分','新积分']},'converted':{'type':'boolean'},'balance':decimal,'total_income':decimal,'total_expense':decimal,'owned':{'type':'object','additionalProperties':{'type':'integer','minimum':1,'maximum':5}},'equipped':arr(S,uniqueItems=True),'slots':{'type':'integer','minimum':3,'maximum':6},'claimed_milestones':arr(S,uniqueItems=True),'claimed_rewards':arr(S,uniqueItems=True),'pending_offer':{'anyOf':[{'type':'null'},offer]},'ledger':arr(ledger),'draw_history':arr(obj(draw_props)),'revision':{'type':'integer','minimum':0}}
write('character.schema.json',obj(state_props))
