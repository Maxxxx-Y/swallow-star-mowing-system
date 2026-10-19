# 《吞噬星空》同人割草系统

可直接用于小说记账和真正随机抽取的初版项目。所有内容都是同人系统设计，技能并非原著秘术原文。26个技能池、316个唯一技能；各池至少12项，特殊技能池更大。同技能可跨池共享ID与等级。

## 从这里开始

- [技能池目录及价格](docs/技能池目录.md)：进入各池查看所有技能及完整Lv1–Lv5。
- [抽取规则](docs/抽取规则.md)：等概率二选一、重复升级、满级移出、仓库与槽位。
- [积分与配置](docs/积分与配置.md)：固定怪兽奖励、1000:1换算、稀少主线扩槽。
- [数值规范](docs/数值规范.md)：预算、能量分配、叠加上限和高级能力使用条件。
- [新增技能指南](docs/新增技能指南.md)：自己加技能、改配置、更新版本。
- [命令使用](docs/命令使用.md)：正式抽取和独立试抽。
- [角色状态](state/character.md)：初始3槽、0积分、空仓库；正式存档为同目录的character.json。
- [校验报告](reports/catalog_validation.json)：技能数量、跨池共享、功能分布及技能库摘要。
- [交付及取舍记录](docs/交付记录.md)：沿用约定和本次明确的操作边界。

## 运行

需要macOS/Linux上的Python 3.9或以上，无需安装依赖。在本文件所在目录打开终端：

```sh
python3 system.py validate
python3 system.py pools
python3 system.py status
```

角色初始没有积分。发生真实剧情战斗后记账，再抽取：

```sh
python3 system.py kill 初级兽将 10 --event 第一章-荒野战斗
python3 system.py draw metal
python3 system.py choose 1
```

上述示例会记入正式存档，只有对应剧情实际发生时才执行。单纯测试请看[独立试抽](docs/命令使用.md)。新技能先入库，用`equip 技能ID`装备，最多同时生效3项。所有JSON均可用文本编辑器查看。

抽取器负责随机、升级、收支和存档；战斗中的命中、抵抗、能量和冷却由写作时依照固定规则判定，本项目不包含战斗模拟器。

运行完整验证：

```sh
python3 -m unittest discover -s tests -v
```
