// ======================================================================
// planning_operational（规划/执行差异拆分）单元测试 —— 期望值全部手工验算
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_planning_operational.py（6 用例）。
// 期望值逐字保留——禁止为绿改数字（算法正确性以 tests 期望值为准）。
//
// 设计原则：
//     1. 回归基准 = 定稿 v2.1 §3 的 Holmes Ltd 案例（三总量+四细分+残差）；
//     2. 两套符号口径各有专测（总量正=A；细分正=F）；
//     3. 退化（修订=标准）与校验组各一组；恒等式与残差关系为内部铁律。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音（与 Python 逐字对应）。
// 运行方式（插件目录下）：node --test tests/planning-split.test.ts
// ======================================================================

import { test } from 'node:test'
import assert from 'node:assert/strict'

// 被测模块（相对导入必须带 .ts 扩展名；类型为纯 TS 导出，须带 type 修饰符——
// Node 原生类型剥离不做类型导入省略，值导入会因运行时无此导出而报错）
import { type ChaifenShuru, ChaifenCuowu, chai_fen } from '../../plugins/fin-agent/src/planning-split.ts'

/** Holmes Ltd 输入（定稿 v2.1 §3）：标准 7kg×400 分；修订 8kg×380 分；产量 1,400；耗用 11,000kg；成本 4,150,000 分（=41,500 元，金额 ×100 转分）。 */
function holmes(): ChaifenShuru {
  return {
    biaozhun_danjia_fen: 400, biaozhun_yongliang: 7,
    xiuding_danjia_fen: 380, xiuding_yongliang: 8,
    shiji_chanliang: 1400, shiji_yongliang: 11000,
    shiji_chengben_fen: 4_150_000,
  }
}

// ----------------------------------------------------------------------
// Holmes 案例回归——与定稿例题逐值一致（最重要的用例组）
// ----------------------------------------------------------------------

test('TestHolmesGuiGui.test_sange_zongliang：三总量 + FA + 恒等式：2,300A = 3,360A + (−1,060)F', () => {
  const jg = chai_fen(holmes())
  // 原标准总 = 4,150,000 − 1,400×7×400 = +230,000 分（2,300 元）→ A
  assert.deepStrictEqual([jg.yuandan_zong_fen, jg.yuandan_zong_fa], [230_000, 'A'])
  // 规划总 = 1,400×8×380 − 1,400×7×400 = +336,000 分（3,360 元）→ A
  assert.deepStrictEqual([jg.guihua_zong_fen, jg.guihua_zong_fa], [336_000, 'A'])
  // 执行总 = 4,150,000 − 4,256,000 = −106,000 分（−1,060 元）→ F
  assert.deepStrictEqual([jg.zhixing_zong_fen, jg.zhixing_zong_fa], [-106_000, 'F'])
  // 恒等式标志必须成立
  assert.equal(jg.hengdengshi_chengli, true)
})

test('TestHolmesGuiGui.test_sixiang_xibao：四项细分（ACCA 符号：正 = F）+ 残差，全部对上例题', () => {
  const jg = chai_fen(holmes())
  // 价格规划 = (400−380)×11,000 = +220,000 分（2,200 元 F）
  assert.deepStrictEqual([jg.jiage_guihua_fen, jg.jiage_guihua_fa], [220_000, 'F'])
  // 价格执行 = 380×11,000 − 4,150,000 = +30,000 分（300 元 F）
  assert.deepStrictEqual([jg.jiage_zhixing_fen, jg.jiage_zhixing_fa], [30_000, 'F'])
  // 用量规划 = (7−8)×1,400×400 = −560,000 分（−5,600 元 A）
  assert.deepStrictEqual([jg.yongliang_guihua_fen, jg.yongliang_guihua_fa], [-560_000, 'A'])
  // 用量执行 = (8×1,400−11,000)×380 = +76,000 分（760 元 F）
  assert.deepStrictEqual([jg.yongliang_zhixing_fen, jg.yongliang_zhixing_fa], [76_000, 'F'])
  // 残差 = (11,200−11,000)×(400−380) = 4,000 分（40 元）
  assert.equal(jg.cancha_fen, 4_000)
  // 细分合计（F 口径）= −234,000：与总量的差恰为残差（P3 关系的显式断言）
  const he = jg.jiage_guihua_fen + jg.jiage_zhixing_fen + jg.yongliang_guihua_fen + jg.yongliang_zhixing_fen
  assert.equal(-he - jg.cancha_fen, jg.yuandan_zong_fen)
})

// ----------------------------------------------------------------------
// 退化场景：无结构变更（修订 = 标准）
// ----------------------------------------------------------------------

test('TestTuihua.test_guihua_guii_ling：修订=标准：规划总差异 = 0，全部差异归执行；残差 = 0', () => {
  const jg = chai_fen({
    biaozhun_danjia_fen: 400, biaozhun_yongliang: 7,
    xiuding_danjia_fen: 400, xiuding_yongliang: 7,
    shiji_chanliang: 1400, shiji_yongliang: 11000,
    shiji_chengben_fen: 4_150_000,
  })
  assert.equal(jg.guihua_zong_fen, 0)
  assert.equal(jg.guihua_zong_fa, '—')
  // 执行总 = 原标准总（规划为零时两者重合）
  assert.equal(jg.zhixing_zong_fen, jg.yuandan_zong_fen)
  // 单价相同 → 残差恒为 0（细分为精确分解，无交叉项）
  assert.equal(jg.cancha_fen, 0)
})

test('TestTuihua.test_wanmei_zhixing：完美执行（实际恰等于修订标准）：执行总 = 0，全部差异归规划', () => {
  // 实际成本 = 修订标准成本 = 1,400×8×380 = 4,256,000 分
  const jg = chai_fen({
    biaozhun_danjia_fen: 400, biaozhun_yongliang: 7,
    xiuding_danjia_fen: 380, xiuding_yongliang: 8,
    shiji_chanliang: 1400, shiji_yongliang: 8 * 1400,
    shiji_chengben_fen: 1_400 * 8 * 380,
  })
  assert.equal(jg.zhixing_zong_fen, 0)
  assert.equal(jg.zhixing_zong_fa, '—')
  assert.equal(jg.yuandan_zong_fen, jg.guihua_zong_fen)  // 336,000
})

// ----------------------------------------------------------------------
// 输入校验：脏数据必须被拒绝
// ----------------------------------------------------------------------

test('TestJiaoyan.test_chanliang_ling：产量为 0 → 拒绝（单位成本失去分母，拆分无数学前提）', () => {
  assert.throws(
    () => chai_fen({
      biaozhun_danjia_fen: 400, biaozhun_yongliang: 7,
      xiuding_danjia_fen: 380, xiuding_yongliang: 8,
      shiji_chanliang: 0, shiji_yongliang: 11000,
      shiji_chengben_fen: 4_150_000,
    }),
    ChaifenCuowu,
  )
})

test('TestJiaoyan.test_feifa_shuzhi：负数 / 浮点 / 布尔 / 非实例 → 拒绝', () => {
  // 负单价 / 浮点成本 / 布尔用量（Python 的 bool 传入以 as unknown as number 复刻）
  const huai_list: readonly ChaifenShuru[] = [
    // 负单价
    { biaozhun_danjia_fen: -1, biaozhun_yongliang: 7, xiuding_danjia_fen: 380, xiuding_yongliang: 8, shiji_chanliang: 1400, shiji_yongliang: 11000, shiji_chengben_fen: 4_150_000 },
    // 浮点成本
    { biaozhun_danjia_fen: 400, biaozhun_yongliang: 7, xiuding_danjia_fen: 380, xiuding_yongliang: 8, shiji_chanliang: 1400, shiji_yongliang: 11000, shiji_chengben_fen: 100.5 },
    // 布尔用量
    { biaozhun_danjia_fen: 400, biaozhun_yongliang: true as unknown as number, xiuding_danjia_fen: 380, xiuding_yongliang: 8, shiji_chanliang: 1400, shiji_yongliang: 11000, shiji_chengben_fen: 4_150_000 },
  ]
  for (const huai of huai_list) {
    assert.throws(() => chai_fen(huai), ChaifenCuowu)
  }
  // 非实例：字符串不是 ChaifenShuru
  assert.throws(() => chai_fen('不是输入对象' as unknown as ChaifenShuru), ChaifenCuowu)
})
