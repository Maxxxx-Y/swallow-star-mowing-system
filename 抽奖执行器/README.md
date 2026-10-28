# 抽奖执行器

负责按已确认配置执行随机抽取、扣除积分、发放或升级技能、保存日志。候选结果由程序生成，不由AI根据剧情需要决定。

## 本目录

- [命令使用](命令使用.md)：记账、抽取、选择、装备和独立试抽。
- `system.py`：随机抽取、存档及数据校验程序。
- `tests/`：抽取、记账、跨池升级和边界测试。
- [技能库校验报告](reports/catalog_validation.json)、[测试结果](reports/test_results.json)：检查记录。

输入配置来自[系统设计师/data](../系统设计师/data)，最终状态与完整收支/抽取历史统一保存到[设定管理员/state/character.json](../设定管理员/state/character.json)。日志属于执行结果，和余额放在同一存档可避免两份记录不一致。

## 最常用命令

在项目根目录运行：

```sh
python3 抽奖执行器/system.py status
python3 抽奖执行器/system.py pools
python3 抽奖执行器/system.py draw metal
python3 抽奖执行器/system.py choose 1
```

付费抽取需有足够积分。新技能先入库，再显式装备。未结算候选会保留，不能重新生成候选、绕过扣款或按剧情改结果。

试验请使用`--state /tmp/自己命名的新存档.json`，不要把示例战斗记入正式角色。新增规则、改技能效果或改价格由系统设计师提出并经作者确认，执行器只读取已确认版本。
