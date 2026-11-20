# 断源纠偏表

海岑薄膜检测室现用一份稳定工况的标定件修正生产样本。新表供夜班在标定库关闭后使用。工位能看到参考读数，冷机与热机在同一读数处都可能有证据。若没有对两者都安全的纠偏量，工位必须能从表上查出。

## 发行与接纳

`release.issue.issue_v2_station_piece(ledger, protocols, freeze_id)` 返回来件字节。同一确切冻结发行确定性 V2 字节和发行号。采用该冻结的全部已登记组，至少一组，未归组的原行不参与。沿用规程的单位换算。每行归一化到 μm 后，参考读数为参考头减量规，厚度偏差为测厚头减量规。每一组代表该组所有读数与偏差对的闭凸包，含点、线段及垂直截面。组间取并。V2 保全各组的联合关系，原三通道记录及试验号留在校准库。

来件应带有 `version=2`、发行号、工装、规程、冻结号、记录修订号和统一单位，联合证据的内部表示由实现定义。用现有 `release.admission.admit_station_piece(inventory, raw)` 接纳 V1 或 V2。沿用首纳原字节的规则，逐字节相同的重投返回原接纳号，同发行号异字节报 `ValueError`。V2 发行号与 V1 区分。接纳前核验版次、出处字段及联合证据结构，坏件拒收。原接纳字节仍可按接纳号读取。

## 签发、领取和现场查表

- `application.review.sign_correction(inventory, storage, acceptance_id, window, limits, tolerance)` 返回 `(body, receipt)`。`window` 和 `limits` 各接收一对有理量，分别是闭读数窗和闭纠偏限位，允许相等端点。`tolerance` 是非负有理残差容差。量值沿用 README 的有理输入，统一为 μm。签发只用指定已接纳 V2 件及本次请求。
- `archive.history.retrieve_correction(storage, report_id)` 返回签发时固定的 `(body, receipt)`。`receipt` 沿用 `SignatureReceipt` 的报告号及回执号。使用原应用库初始化入口。正文与回执同次提交，写入或提交错误传给调用方，失败无新增且可用原请求重试。源端勘误及应用库重开后仍按原报告号领取存值。
- `application.review.lookup_correction(body, reading)` 仅用签发正文返回 `(state, correction)`，可纠偏时 `correction` 为 `Fraction`，其他状态为 `None`。`reading` 必须是窗内有理读数。用 V1 件签纠偏表或用 V2 件签 V1 样本报告均报 `ValueError`。非法请求报 `ValueError`，未知冻结、接纳或报告号报 `KeyError`。

`body` 是可直接用 JSON 保存的字典，包含 `report_id`、`provenance`、`window`、`limits`、`tolerance`、`segments`。`provenance` 固定 `acceptance_id`、`issuance_id`、`fixture_id`、`protocol_id`、`freeze_id`、`revision_id`。闭区间为两元素列表，正文有理值使用 V1 有理字符串。`segments` 按读数升序存放记录 `[left, right, left_closed, right_closed, state, instruction]`，两个开闭标志为布尔值。各段不交，完整覆盖闭窗内的所有实读数。孤点两端均闭。允许用多个相邻段表示同一状态。

对窗内每个读数，若无组支持这个读数，状态为 `no_evidence`。若有证据但不存在落在闭限位内且能使全部相容偏差的残差绝对值不超过容差的共用纠偏量，状态为 `uncorrectable`。两种状态的 `instruction` 均为 `null`。其余读数为 `correctable`，每段 `instruction` 为 `[slope, intercept]`，按 `slope * reading + intercept` 得到纠偏量。指令须在所签区间全程满足限位及残差要求，残差为偏差减纠偏量，等于容差时算达标。

## 交班样例

`examples/correction_fixture.py` 提供 `POINT_OVERLAP` 和 `TRIANGLE_AND_GAP`。可用 `seed_case(protocols, ledger, case)` 登记并取得 `(protocol_id, revision_id, freeze_id)`。运行 `python3 -B -m examples.correction_fixture` 可观察原 V1 如何分别核定两个稳定组及拒绝一组多值折线。

- `POINT_OVERLAP` 中冷组只支持 `(0,0)`，热组支持 `[0,1]` 上恒为 2 的偏差。用读数窗 `[0,1]`、限位 `[0,3]`、容差 `1/2` 签发。读数 0 为 `uncorrectable`，`(0,1]` 为 `correctable`，动作在 `[3/2,5/2]` 内。改用容差 1 签发，读数 0 的动作只能为 1。
- `TRIANGLE_AND_GAP` 中一组由 `(0,0)`、`(0,2)`、`(2,2)` 确定，另一组只支持 `(4,2)`。用读数窗 `[0,5]`、限位 `[0,3]`、容差 `1/2` 签发。`[0,1)` 为 `uncorrectable`，`[1,2]` 及读数 4 为 `correctable`，其余为 `no_evidence`。读数 1 的动作只能为 `3/2`。用单点窗 `[4,4]`，限位 `[0,1]` 时不可纠偏，限位 `[2,2]` 时动作只能为 2。

## 运行交付

沿用 `.pointwise-runtime.json`。`version` 保持 `1`，`kind` 保持 `cli`，`setup` 是准备命令的 argv 列表，`verify` 和 `demo` 各为一条 argv 命令。核验入口执行原回归及纠偏联动核验，保留失败退出码。演示入口展示实际接纳、关源签表、仅凭正文查表和重开领取。提交失败核验可参照 `tests/fixtures.py` 的延迟外键场景。保留 V1 接口、旧件、旧报告及原回归。
