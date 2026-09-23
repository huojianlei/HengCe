// ======================================================================
// zhenggai（整改数据底座）单元测试 —— 期望值全部手工验算写死
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_zhenggai.py（11 用例，
// 期望值逐字保留，禁止改数字迁就实现）。
//
// 设计原则：
//     1. 规则回归：判定指令项（双环/混合→预算修订案、单环→行为整改、
//        复核提示→人工复核）+ 预警项（红=强制/黄=关注）逐条锁定；
//     2. 责任模块 = 科目→模块映射（复用 building_blocks 默认映射）+ 积木高亮；
//     3. 排序：高 → 中 → 低（稳定排序）；进度初始全"待整改"。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音。
// 运行方式（验证区目录下）：
//     node --test tests/zhenggai.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
// 被测模块与上游构造：真实模块现算夹具（鸭子类型契约——无需适配层）
import type { ChayiShuru, YujingDang } from '../../plugins/fin-agent/src/variance.ts'
import { jisuan_chayi } from '../../plugins/fin-agent/src/variance.ts'
import type { PanDuanShuru } from '../../plugins/fin-agent/src/loop-decision.ts'
import { panduan_huanlu } from '../../plugins/fin-agent/src/loop-decision.ts'
import type { JimuHang } from '../../plugins/fin-agent/src/building-blocks.ts'
import { chai_jimu } from '../../plugins/fin-agent/src/building-blocks.ts'
import type { ZhenggaiShuru } from '../../plugins/fin-agent/src/zhenggai.ts'
import { shengcheng_zhenggai } from '../../plugins/fin-agent/src/zhenggai.ts'

// ----------------------------------------------------------------------
// 夹具区（与 Python 版逐字对应；期望值全部手工推演写死，禁止现算自证）
// ----------------------------------------------------------------------

/** 红预警差异：材料价格 100,000 → 110,000 元（差异率 10% = 1000 基点）。 */
function hong_chayi() {
  // 自定义档位 红≥1000（默认已改 15%/30%，此处显式传旧线以覆盖下游规则）
  const dang_lie: [YujingDang, YujingDang] = [
    { ming_cheng: '红', yan_se: '红', yu_fen: 1000 },
    { ming_cheng: '黄', yan_se: '黄', yu_fen: 500 },
  ]
  const hang_lie: ChayiShuru[] = [
    { qijian: '2026-Q1', kemu: '材料价格差异', fangxiang: '成本类',
      chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 11_000_000 },
  ]
  return jisuan_chayi(hang_lie, dang_lie)
}

/** 黄预警差异：办公费 100,000 → 105,000 元（差异率 5% = 500 基点）。 */
function huang_chayi() {
  // 自定义档位 红 10%/黄 5%：500 ∈ [500, 1000) → 黄 → 关注整改（中）
  const dang_lie: [YujingDang, YujingDang] = [
    { ming_cheng: '红', yan_se: '红', yu_fen: 1000 },
    { ming_cheng: '黄', yan_se: '黄', yu_fen: 500 },
  ]
  const hang_lie: ChayiShuru[] = [
    { qijian: '2026-Q1', kemu: '办公费', fangxiang: '成本类',
      chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 10_500_000 },
  ]
  return jisuan_chayi(hang_lie, dang_lie)
}

/** 积木结果：材料价格差异 → 采购模块（高亮 = 采购模块）。 */
function jimu_caigou() {
  // 高亮规则（积木 D3）：不利模块中 |差额| 最大者 = 采购模块
  // 材料价格差异按默认映射归采购模块（材料价格关键词先于材料）
  const hang: JimuHang = { qijian: '2026-Q1', kemu: '材料价格差异',
    chae_fen: 1_000_000, fa: 'A', yujing: '红', chalv_bps: 1000 }
  return chai_jimu([hang])
}

/** 双环判定：结构变更登记 + 规划差异显著（情形 3）。 */
function panduan_shuanghuan() {
  // 判定表五情形详见 loop_decision 模块头（定稿 §4.4）
  // 规划差异 900,000/10,000,000 = 9% 显著（≥100 基点）且已登记 → 双环
  const shuru: PanDuanShuru = {
    chalv_bps: 1000, guihua_zong_fen: 900_000, zhixing_zong_fen: 100_000,
    yuandan_cbf_fen: 10_000_000, jie_gou_biangeng: true, bianma: '供应商涨价',
  }
  // 演示锚点保持在原定稿 1% 门限口径下复现（可会计复核）
  return panduan_huanlu(shuru, 100, 100)
}

// ----------------------------------------------------------------------
// TestLiti · 例题回归：双环 + 红预警 + 积木高亮 → 两条高优先级整改项
// ----------------------------------------------------------------------
describe('TestLiti · 例题回归：双环 + 红预警 + 积木高亮 → 两条高优先级整改项', () => {
  test('test_shuanghuan_hong: 清单 = [预算修订案(高,采购), 强制整改(高,采购)]；计数 2/2', () => {
    // 责任模块来源：判定项取积木高亮、预警项取科目映射——两路一致
    const jg = shengcheng_zhenggai({
      chayi: hong_chayi(), jimu: jimu_caigou(), panduan: panduan_shuanghuan(),
    } as ZhenggaiShuru)
    // 高亮=采购模块且强制整改责任模块同为采购 → 不重复追加高亮提示项
    assert.deepEqual(
      jg.qingdan.map((x) => [x.leixing, x.youxianji, x.zeren_mokuai]),
      [['预算修订案', '高', '采购模块'], ['强制整改', '高', '采购模块']],
    )
    assert.deepEqual([jg.gao_shu, jg.zhong_shu, jg.di_shu], [2, 0, 0])
    // 进度三态：初始全"待整改"（计算层只生成底座，进度流转属后续）
    assert.deepEqual(
      [jg.daizhenggai_shu, jg.jinxingzhong_shu, jg.wancheng_shu], [2, 0, 0],
    )
    // 预算修订案必人工审批（定稿 §9 步骤 8 审批闭环）；强制整改不用
    assert.equal(jg.qingdan[0]!.shenpi, true)
    assert.equal(jg.qingdan[1]!.shenpi, false)
    // 金额显示锁定（T-29#8 元主单位 + 千分位逗号，两位小数——描述零浮点）
    assert.equal(
      jg.qingdan[1]!.miaoshu,
      '2026-Q1 材料价格差异 差额 10,000.00 元 预警 红',
    )
  })
})

// ----------------------------------------------------------------------
// TestPandingZhiling · 判定指令项：双轨/单环/复核提示三条规则逐一锁定
// ----------------------------------------------------------------------
describe('TestPandingZhiling · 判定指令项：双轨/单环/复核提示三条规则逐一锁定', () => {
  test('test_shuanggui_yusuan_xiuding: 双轨 → 预算修订案（高、必审批）', () => {
    // 双轨与双环同出口：预算修订案 + 人工审批（定稿 §4.2 职责拆分）
    // 规划+执行双显著且已登记 → 双轨（判定表情形 4 = 混合纠错模式）
    const shuru: PanDuanShuru = {
      chalv_bps: 1500, guihua_zong_fen: 1_000_000, zhixing_zong_fen: 500_000,
      yuandan_cbf_fen: 10_000_000, jie_gou_biangeng: true, bianma: '原材料替换',
    }
    // 示例差异率低于 25% 新默认门限，传 100 沿用原口径
    const pd = panduan_huanlu(shuru, 100, 100)
    const jg = shengcheng_zhenggai({ panduan: pd } as ZhenggaiShuru)
    assert.equal(jg.qingdan[0]!.leixing, '预算修订案')
    assert.equal(jg.qingdan[0]!.shenpi, true)
  })

  test('test_danhuan_xingwei_zhiling: 单环 → 行为整改指令（中、不审批、不改预算基准）', () => {
    // 单环语义：纠正当下执行动作，年度预算基准方案不动
    // 执行差异显著 + 无登记 → 单环（情形 2）
    const shuru: PanDuanShuru = {
      chalv_bps: 800, guihua_zong_fen: null, zhixing_zong_fen: 800_000,
      yuandan_cbf_fen: 10_000_000, jie_gou_biangeng: false, bianma: '',
    }
    // 800 基点同样低于 25% 新默认，统一走原口径注入
    const pd = panduan_huanlu(shuru, 100, 100)
    const jg = shengcheng_zhenggai({ panduan: pd } as ZhenggaiShuru)
    assert.equal(jg.qingdan[0]!.leixing, '行为整改指令')
    assert.equal(jg.qingdan[0]!.youxianji, '中')
    assert.equal(jg.qingdan[0]!.shenpi, false)
  })

  test('test_fuhe_tishi: 复核提示 → 人工复核项（中）；LLM 只能提示不能直接双环', () => {
    // 复核提示是 LLM 语义归类的唯一出口（升级提示，绝不直接触发双环）
    // 与 loop_decision 知识点 6 同款构造：注入假 LLM 归类"结构变动"
    // + 有变更文本但无登记 → 升级为复核提示（护栏 FR-8）
    const shuru: PanDuanShuru = {
      chalv_bps: 587, guihua_zong_fen: null, zhixing_zong_fen: 2_300_000,
      yuandan_cbf_fen: 39_200_000, jie_gou_biangeng: false,
      bianma: '永久更换核心供应商',
      yuyi_guilei: (wenben: string) => '结构变动', // 注入假 LLM 归类函数
    }
    // Holmes 数字锚点不动，门限走原定稿口径
    const pd = panduan_huanlu(shuru, 100, 100)
    const jg = shengcheng_zhenggai({ panduan: pd } as ZhenggaiShuru)
    assert.equal(jg.qingdan[0]!.leixing, '人工复核')
    assert.equal(jg.qingdan[0]!.youxianji, '中')
  })
})

// ----------------------------------------------------------------------
// TestYujingXiang · 预警项：红=强制（高）、黄=关注（中）；责任模块按科目映射
// ----------------------------------------------------------------------
describe('TestYujingXiang · 预警项：红=强制（高）、黄=关注（中）；责任模块按科目映射', () => {
  test('test_huang_guanzhu: 只有黄预警 → 关注整改（中），责任模块 = 费用模块（办公费）', () => {
    // 办公费 ∈ 费用模块关键词（映射增强后锁定，防回归——与积木模块同表）
    const jg = shengcheng_zhenggai({ chayi: huang_chayi() } as ZhenggaiShuru)
    assert.deepEqual(
      jg.qingdan.map((x) => [x.leixing, x.youxianji, x.zeren_mokuai]),
      [['关注整改', '中', '费用模块']],
    )
  })

  test('test_weiguishu_kemu: 科目映射不中 → 责任模块 = 未归属（不静默丢弃）', () => {
    // 宁可交人工补映射，也不猜测归属——与积木模块 D1 兜底同纪律
    // 神秘科目不含任何关键词 → 未归属
    const dang_lie: [YujingDang, YujingDang] = [
      { ming_cheng: '红', yan_se: '红', yu_fen: 1000 },
      { ming_cheng: '黄', yan_se: '黄', yu_fen: 500 },
    ]
    const chayi = jisuan_chayi([
      { qijian: '2026-Q1', kemu: '神秘科目', fangxiang: '成本类',
        chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 11_000_000 },
    ], dang_lie)
    const jg = shengcheng_zhenggai({ chayi } as ZhenggaiShuru)
    assert.equal(jg.qingdan[0]!.zeren_mokuai, '未归属')
  })

  test('test_gaoliang_tishi_xuanji: 积木高亮 ≠ 预警行责任模块 → 追加关注整改提示项', () => {
    // 高亮提示优先级取中——红/黄预警行才是强制入口
    // 预警行是"办公费"（费用模块），积木高亮是"采购模块"——两者不同
    const hang: JimuHang = { qijian: '2026-Q1', kemu: '材料价格差异',
      chae_fen: 1_000_000, fa: 'A', yujing: '红', chalv_bps: 1000 }
    const jimu = chai_jimu([hang])
    const jg = shengcheng_zhenggai({ chayi: huang_chayi(), jimu } as ZhenggaiShuru)
    // 两条关注整改：一条来自黄预警、一条来自高亮提示（责任模块采购）
    assert.deepEqual(jg.qingdan.map((x) => x.leixing), ['关注整改', '关注整改'])
    assert.equal(jg.qingdan[1]!.zeren_mokuai, '采购模块')
  })

  test('test_gaoliang_chongfu_bu_xuanji: 积木高亮已存在于强制整改项 → 不重复追加提示项', () => {
    // 去重规则：高亮与预警行责任模块一致时不重复列示（清单干净）
    // 红预警责任模块=采购模块 与高亮一致 → 只有 1 条强制整改
    const jg = shengcheng_zhenggai({ chayi: hong_chayi(), jimu: jimu_caigou() } as ZhenggaiShuru)
    assert.equal(jg.qingdan.length, 1)
  })
})

// ----------------------------------------------------------------------
// TestPaixuJishu · 排序与计数：高 → 中 → 低（稳定）；空输入 → 全零
// ----------------------------------------------------------------------
describe('TestPaixuJishu · 排序与计数：高 → 中 → 低（稳定）；空输入 → 全零', () => {
  test('test_paixu: 红(高) + 单环(中) + 黄(中) → 顺序 [强制整改, 行为整改指令, 关注整改]', () => {
    // 高在前、中在后；同级按生成顺序（判定项先于预警项）
    const shuru_pd: PanDuanShuru = {
      chalv_bps: 800, guihua_zong_fen: null, zhixing_zong_fen: 800_000,
      yuandan_cbf_fen: 10_000_000, jie_gou_biangeng: false, bianma: '',
    }
    // 800 基点同样低于 25% 新默认，统一走原口径注入
    const pd = panduan_huanlu(shuru_pd, 100, 100)
    const dang_lie: [YujingDang, YujingDang] = [
      { ming_cheng: '红', yan_se: '红', yu_fen: 1000 },
      { ming_cheng: '黄', yan_se: '黄', yu_fen: 500 },
    ]
    const chayi = jisuan_chayi([
      { qijian: '2026-Q1', kemu: '材料价格差异', fangxiang: '成本类',
        chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 11_000_000 },
      { qijian: '2026-Q1', kemu: '办公费', fangxiang: '成本类',
        chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 10_500_000 },
    ], dang_lie)
    const jg = shengcheng_zhenggai({ chayi, panduan: pd } as ZhenggaiShuru)
    // 排序稳定性：两条"中"保持生成顺序（行为整改指令在前）
    assert.deepEqual(
      jg.qingdan.map((x) => x.leixing),
      ['强制整改', '行为整改指令', '关注整改'],
    )
    assert.deepEqual([jg.gao_shu, jg.zhong_shu, jg.di_shu, jg.zong_shu], [1, 2, 0, 3])
  })

  test('test_kong_shuru: 全部上游缺省 → 空清单、全零计数（聚合层容错）', () => {
    // 聚合层职责：只组装不重算——上游缺失就空着，由看板层显示「无」
    // 端到端脚本某阶段缺失时不允许崩——空清单即合法输出
    const jg = shengcheng_zhenggai({} as ZhenggaiShuru)
    assert.deepEqual(jg.qingdan, [])
    assert.deepEqual([jg.gao_shu, jg.zhong_shu, jg.di_shu, jg.zong_shu], [0, 0, 0, 0])
  })

  test('test_quedingxing: 确定性：同输入两次调用结果完全一致（纯函数纪律）', () => {
    // 清单顺序与计数均须稳定——AI 层文案起草依赖顺序稳定
    // 纯函数要求：无 I/O、无全局状态 → 同输入必同输出（深比较全字段）
    const shuru = {
      chayi: hong_chayi(), jimu: jimu_caigou(), panduan: panduan_shuanghuan(),
    } as ZhenggaiShuru
    assert.deepEqual(shengcheng_zhenggai(shuru), shengcheng_zhenggai(shuru))
  })
})
