# 海岑薄膜测厚校准交班

白班按固定规程采集参考头、量规和测厚头读数。夜班在校准库关闭后使用单一稳定工况的交班曲线，核定生产样本。次班按原号领取签报，复核当时实际采用的规程、冻结和站件。

## 运行

使用 Python 3.11，依赖均来自标准库。在项目根目录运行。

```text
python3 -B check_project.py
python3 -B -m examples.demo
```

`check_project.py` 由交付环境提供。在只有业务源码的独立副本中，可直接运行 `python3 -B -m unittest discover -s tests -t .`。演示和回归使用临时 SQLite 文件。演示先使用旧站件断源签报，再从勘误后的校准库发行新件，最后重开应用库领取两份签报。

## 正常交班

1. 主管登记工装、具名量规、读数单位及合格限，得到固定规程号。
2. 标定员按规程提交具名三通道行及稳定工况组，得到记录修订号。
3. 标定员按原行号提交勘误，选择确切修订冻结，保留父修订供复查。
4. 发行员用冻结号和单个组号发行 V1 曲线站件。
5. 质控员首纳原件，保留接纳号，随后关闭校准库。
6. 夜班按接纳号、工装和一批有序样本核定实际修正厚度。
7. 签报将有序输入、明细、首件出处和回执一起提交。
8. 次班按报告号领取已存正文及回执，可同时复查采用后继件的另一份签报。

## Python 接口

调用方持有两个相互独立的 `sqlite3.Connection`，分别连接校准库和应用库。使用空闲连接调用以下接口。初始化可以重复执行，连接关闭由调用方管理。

| 操作 | 接口及结果 |
| --- | --- |
| 校准库初始化 | `ProtocolStore(source).initialize()`，然后 `CalibrationLedger(source).initialize()` |
| 规程登记 | `ProtocolStore.register(Fixture(...), GaugeSpec(...), UnitConversion(...), ThicknessLimits(...))` 返回规程号，`get` 按号读取 |
| 记录和分组 | `submit_trial_revision(ledger, protocols, protocol_id, rows, groups, parent_id=...)` 返回新修订号。省略父号从空视图开始。指定父号时继承旧行和组，同名新组更新该后继修订的成员名单 |
| 具名勘误 | `amend_trial_row(ledger, protocols, parent_id, row_id, replacement)` 返回后继号，替换行保留该行号 |
| 冻结 | `freeze_revision(ledger, revision_id)` 返回固定冻结号，同一修订重复冻结沿用原号。`get_frozen_calibration` 读取视图，`read_frozen_group(frozen, group_id)` 只解析指定组 |
| 发行 | `issue_v1_station_piece(ledger, protocols, freeze_id, group_id)` 返回确定性原件字节。同一冻结和组可以重复交付 |
| 应用库初始化 | `AdmissionInventory(offline).initialize()` 以及 `ArchiveStorage(offline).initialize()` |
| 首纳和取件 | `admit_station_piece(inventory, raw)` 返回接纳号，`get_accepted_piece(inventory, acceptance_id)` 返回原字节及已解码站件 |
| 签报 | `sign_review(inventory, storage, ReviewBatch(acceptance_id, fixture_id, samples))` 返回 `(ReviewReport, SignatureReceipt)`。每个样本用 `SampleInput(sample_id, reference, thickness)` 提交 |
| 按号领取 | `retrieve_report(storage, report_id)` 返回含 `.report`、`.provenance` 和 `.receipt` 的历史记录 |

数据类型位于各职责模块中。规程类型位于 `protocol`，原行 `TrialRow(row_id, unit, reference_head, gauge, thickness_head)` 和 `TrialGroup(group_id, row_ids)` 位于 `measurement`，核定请求类型位于 `application/samples.py`。各业务调用的实际用例见 `examples/demo.py`。`store_revision` 和 `claim` 是相应业务入口使用的持久层方法，分别接收已验收的修订视图和已解码核验的发行身份及原字节。

## 计算与失败语义

量值接受 `Fraction`、整数、整数字符串、分数字符串和有限十进制字符串。布尔值及浮点数报 `ValueError`。规程声明一种原始读数单位及正有理换算比例，原始记录按声明单位提交。应用读数和规程合格限统一使用 μm。参考读数为参考头减量规，偏差为测厚头减量规。

V1 原件是带版本、发行身份、工装、规程、冻结、记录修订、组、统一单位、合格限和节点的 UTF-8 JSON。站件的有理值为字符串。节点按参考读数严格升序。同读数同偏差可以折叠，同读数异偏差时该组拒发。交付保留确切原字节，同发行身份只有逐字节相同的重投沿用首接纳号。JSON 空白差异仍是字节差异。

在相邻节点之间用有理数线性插值。闭域两端可用，单节点只支持该点。实际修正厚度等于实测厚度减偏差。修正厚度落在含两端的合格区间内时为 `pass`，其他可计算厚度为 `out_of_limits`。显式空厚度为 `missing`，有厚度但读数超出闭域为 `outside_curve`，两种状态均无修正值。厚度零照常计算，样本明细保持输入顺序。

未知编号报 `KeyError`。非法读值、失配、坏件及冲突报 `ValueError`。批次验收失败无新增修订或签报，旧记录保持可读。签报的正文和回执同次提交，SQLite 写入或提交错误向调用方传递，事务回滚后可重试。校准勘误及应用库重开后，原报告按号返回原正文、原接纳件及回执。

`examples/calibration.json`、`examples/night-request.json` 和 `examples/expected.json` 是同一交班的入料、请求和手算预期。节点 `(0, 0)` 与 `(2, 1)` 在读数 `1` 处给出偏差 `1/2`，厚度 `10` 修正为 `19/2`，恰达合格下限。
