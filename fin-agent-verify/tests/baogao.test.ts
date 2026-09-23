// ======================================================================
// baogao（报告组装与 Markdown 排版）单元测试 —— 期望值全部手工验算写死
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_baogao.py（15 用例，
// 期望数字逐字保留，禁止改数字迁就实现）。
//
// 设计原则：
//     1. 结构回归：八单元各一节一表（"一个分析项目对应一张数据表"）
//        + 三个附表；
//     2. 显示回归：金额 = 元（两位小数千分位）、比率 = 百分比、
//        周转率 = 次、布尔 = 是/否、缺数 = "—"——全部锁定；
//     3. 容错回归：上游缺省 → "（缺料）"占位，绝不抛错。
//
// 【上游构造说明】Python 版以 import 调用八单元真实函数（daoru_csv /
//     gengxin_gundong_yusuan / jisuan_chayi / chai_fen / panduan_huanlu /
//     chai_jimu / jisuan_bsc / jisuan_kpi / jisuan_suyuan /
//     shengcheng_zhenggai / shengcheng_kanban）构造全链路上游；TS 版按
//     转写约定改用【结构 interface 字面量】（字段名与上游 dataclass 逐字
//     一致），字面值 = 上述 Python 函数在同一输入下的冻结输出（逐对象
//     dump 核对，与 algo/tests/test_baogao.py 的 quanlian_shuru 同源）。
//     baogao 是鸭子类型消费方——只认形状不认出处，测试即验证此契约。
//
// 【转写设计裁决·修正1】Python baogao.py 单元 3 脚注硬编码「5%黄/10%红」
//     为历史残留；TS 版脚注改由 HUANG_YUZHI_BPS=1500 / HONG_YUZHI_BPS=3000
//     常量动态生成（黄档 15% / 红档 30%）。Python 测试**没有**断言脚注含
//     '5%'/'10%' 子串（全部 15 用例均不触及该脚注文案），故无需改写任何
//     期望断言——此处留痕说明，杜绝后续按旧文案补断言造成漂移。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音。
// 运行方式（验证区目录下）：
//     cd /d/AppProject/fin-agent-verify && node --test tests/baogao.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import {
  type BgShuru,
  type BscJieguo,
  type ChaifenJieguo,
  type ChayiJieguo,
  type DaoruJieguo,
  type GunDongJieguo,
  type JimuJieguo,
  type KanbanShuju,
  type KpiJieguo,
  type PanDuanJieguo,
  type SuyuanJieguo,
  type ZhenggaiJieguo,
  shengcheng_baogao_md,
} from '../../plugins/fin-agent/src/baogao.ts'

/** 演示录入：营收预算/实际两行（数据录入节的数据源）。
 * Python 版调 daoru_csv 解析 8 列 CSV；TS 版直接给出其冻结输出
 * （hanghao/gengxin_shijian 本模块不消费，鸭子契约未含，字面量从简）。
 * 8 列表头与 data_ingest 规范一致——报告表数据即录入层原样：
 *   预算基础,2026-Q1,营收,220000.00,元,预算表V3,2026-01-15,年初定稿
 *   实时经营,2026-Q1,营收,210000.00,元,ERP导出,2026-04-02,Q1实际
 */
function yanshi_ruku(): DaoruJieguo {
  return {
    yusuan: [{
      leibie: '预算基础', qijian: '2026-Q1', kemu: '营收',
      shuzhi: 22_000_000, danwei: '元', laiyuan: '预算表V3', beizhu: '年初定稿',
    }],
    shishi: [{
      leibie: '实时经营', qijian: '2026-Q1', kemu: '营收',
      shuzhi: 21_000_000, danwei: '元', laiyuan: 'ERP导出', beizhu: 'Q1实际',
    }],
    hangye: [],
    biangeng: [],
    jujue: [],
  }
}

/** 构造八单元全链路上游（数字与端到端演示同源，可交叉核对）。
 * 本函数即「八单元串联」的测试化版本——与 Python 测试共用同一套演示
 * 数字（滚动 433,311 / 差异红一行 / Holmes 拆分 / 混合纠错 / BSC 74），
 * 每个字面量都是上游函数在 Python 测试输入下的冻结输出。
 */
function quanlian_shuru(): BgShuru {
  const ruku = yanshi_ruku()
  // 滚动：营收两期（Q1 届满 210,000 + Q2 口径 A 重算 223,311.00——
  // 企业 1% vs 行业 0.5% 差值恰达 50 基点阈值，边界即启用）
  const gundong: GunDongJieguo = {
    qijian_mingxi: [
      { qijian: '2026-Q1', zhuangtai: '已届满',
        chushi_yusuan_fen: 22_000_000, shuzhi_fen: 21_000_000 },
      { qijian: '2026-Q2', zhuangtai: '剩余期',
        chushi_yusuan_fen: 22_000_000, shuzhi_fen: 22_331_100 },
    ],
    chushi_zonge_fen: 44_000_000, // 440,000.00 元
    gundong_zonge_fen: 43_331_100, // 433,311.00 元
    chae_fen: -668_900, // -6,689.00 元（预算下调）
  }
  // 差异：期间费用红预警一行（2,000,000 → 2,200,000 分，差异率 10%→红）
  // （Python 测试用自定义档位 红≥10%/黄≥5% 保持"红预警"演示意图）
  const chayi: ChayiJieguo = {
    xiang: [{
      qijian: '2026-Q1', kemu: '期间费用', fangxiang: '成本类',
      chushi_fen: 2_000_000, gundong_fen: null, shiji_fen: 2_200_000,
      jizhun_fen: 2_000_000, chae_fen: 200_000, chalv_bps: 1000,
      fa: 'A', yujing: '红',
    }],
    heji_chae_fen: 200_000,
    heji_fa: 'A',
    hong_shu: 1, huang_shu: 0, wu_shu: 0, wufa_shu: 0,
  }
  // 拆分：Holmes 例题（规划 3,360.00 / 执行 -1,060.00 / 恒等式成立）
  const chaifen: ChaifenJieguo = {
    yuandan_zong_fen: 230_000, yuandan_zong_fa: 'A',
    guihua_zong_fen: 336_000, guihua_zong_fa: 'A',
    zhixing_zong_fen: -106_000, zhixing_zong_fa: 'F',
    jiage_guihua_fen: 220_000, jiage_guihua_fa: 'F',
    jiage_zhixing_fen: 30_000, jiage_zhixing_fa: 'F',
    yongliang_guihua_fen: -560_000, yongliang_guihua_fa: 'A',
    yongliang_zhixing_fen: 76_000, yongliang_zhixing_fa: 'F',
    cancha_fen: 4_000,
    hengdengshi_chengli: true,
  }
  // 判定：规划+执行双显著+登记 → 混合纠错模式（情形 4、shenpi=true）
  const panduan: PanDuanJieguo = {
    qingxing: 4,
    panduan: '混合纠错模式',
    jiuzheng: '混合纠错模式：双环流程优先——预算修订案提交人工审批，同步下发单环行为整改；本周期不修改预算基准',
    yiju: {
      '门检基点': 100,
      '差异率基点': 1000,
      '规划差异显著': true,
      '执行差异显著': true,
      '结构变更登记': true,
      '语义归类': '无法判断',
    },
    shenpi: true,
    beizhu: '情形 4 = 结构性变更与显著执行偏差同时发生',
  }
  // 积木：费用行 → 费用模块独占（占比 100.00%、核心问题模块 = 费用模块）
  const jimu: JimuJieguo = {
    mokuai_lie: [
      { mokuai: '收入模块', chae_fen: 0, fa: '—', zhanbi_bps: 0, hang_shu: 0 },
      { mokuai: '成本模块', chae_fen: 0, fa: '—', zhanbi_bps: 0, hang_shu: 0 },
      { mokuai: '费用模块', chae_fen: 200_000, fa: 'A', zhanbi_bps: 10_000, hang_shu: 1 },
      { mokuai: '采购模块', chae_fen: 0, fa: '—', zhanbi_bps: 0, hang_shu: 0 },
    ],
    weiguishu_lie: [],
    jing_heji_fen: 200_000,
    hexin_mokuai: '费用模块',
    weiguishu_zhanbi_bps: 0,
  }
  // BSC：定稿 §6 例题（75/80/70/60 × 40/30/20/10 → 总分 74 → 合格）
  const bsc: BscJieguo = {
    caijing_defen: 75, kehu_defen: 80, neibu_defen: 70, xuexi_defen: 60,
    quanzhong: [40, 30, 20, 10],
    zongfen: 74,
    dengji: '合格',
    caijing_bps: 7500, kehu_bps: 8000, neibu_bps: 7000, xuexi_bps: 6000,
  }
  // KPI：15 项（成本控制率分母缺失 → null 缺数；资产周转 0.2625 次）
  const kpi: KpiJieguo = {
    yingshou_dachenglv_bps: 9545,
    chengben_kongzhilv_bps: null,
    feiyong_pianchalv_bps: 1000,
    maolilv_bps: 5000,
    jinglirunlv_bps: 3000,
    xiaoshou_lirunlv_bps: 4000,
    zichan_zhouzhuanlv_bps: 2625,
    zijin_zhouzhuanlv_bps: 9767,
    caigou_chengben_bian_donglv_bps: 625,
    gongyinglian_lvyuelv_bps: 9500,
    channeng_liyonglv_bps: 8500,
    jiaofu_zhouqi_tian: 7,
    kehu_manyilv_bps: 9000,
    yewu_jindu_bps: 7500,
    yichang_shijian_shu: 3,
  }
  // 溯源：两 KPI 均负向作用（正向 TOP3 为空 → 8.1 表显式 "—"）
  const suyuan: SuyuanJieguo = {
    xiang: [
      { kpi_mingcheng: '采购成本变动率', yingxianglv_bps: 625,
        shuzhi_fangxiang: '上升', zuoyong: '负向作用', zhanbi_bps: 2727 },
      { kpi_mingcheng: '交付周期', yingxianglv_bps: 1667,
        shuzhi_fangxiang: '上升', zuoyong: '负向作用', zhanbi_bps: 7273 },
    ],
    zhengxiang_top3: [],
    fuxiang_top3: ['交付周期', '采购成本变动率'],
    gongshi: '影响率 =（变更后数值 − 变更前数值）÷ 原始预算数值 × 100%',
  }
  // 整改：混合纠错 → 预算修订案（审批=是）；红行 → 强制整改（审批=否）
  const zhenggai: ZhenggaiJieguo = {
    qingdan: [
      { leixing: '预算修订案', youxianji: '高', zeren_mokuai: '费用模块',
        qijian: '', kemu: '',
        miaoshu: '判定 混合纠错模式：预算修订案（人工审批后下周期生效）',
        shenpi: true, zhuangtai: '待整改' },
      { leixing: '强制整改', youxianji: '高', zeren_mokuai: '费用模块',
        qijian: '2026-Q1', kemu: '期间费用',
        miaoshu: '2026-Q1 期间费用 差额 2,000.00 元 预警 红',
        shenpi: false, zhuangtai: '待整改' },
    ],
    zong_shu: 2, gao_shu: 2, zhong_shu: 0, di_shu: 0,
  }
  // 看板：附表 C 只消费 yujing_huizong 四档计数（鸭子最小契约）
  const kanban: KanbanShuju = {
    yujing_huizong: { hong_shu: 1, huang_shu: 0, wu_shu: 0, wufa_shu: 0 },
  }
  return {
    ruku, gundong, chayi, chaifen, panduan, jimu, bsc,
    kpi, suyuan, zhenggai, kanban,
  }
}

// ---------------------------------------------------------------------
// TestJiegou · 结构回归：八单元 + 三附表各一节，一个分析项目一张表
// ---------------------------------------------------------------------
describe('TestJiegou · 结构回归：八单元 + 三附表各一节', () => {
  test('test_badanyuan_jie_cunzai: 八个单元节标题与三个附表标题全部出现', () => {
    // 结构契约：节顺序 = 方案 B 步骤顺序（1 录入 … 8 溯源 + 三附表）
    const md = shengcheng_baogao_md(quanlian_shuru())
    const biaoti = [
      '总览 · 三重对比汇总',
      '单元 1 · 数据录入', '单元 2 · 滚动预算', '单元 3 · 差异计算',
      '单元 4 · 规划/执行拆分', '单元 5 · 单双环判定',
      '单元 6 · 积木拆解', '单元 7 · 平衡计分卡', '单元 8 · 变更溯源',
      '附表 A · KPI 指标库', '附表 B · 整改清单', '附表 C · 预警汇总',
    ]
    for (const t of biaoti) {
      assert.ok(md.includes(t), `缺少节标题：${t}`)
    }
  })

  test('test_mei_danyuan_you_biao: 每节至少一张表（分隔行 | --- 计数 ≥ 11）', () => {
    // 分隔行 '| ---' 即表头下的那行——每张表恰一个；
    // 全链路下含总览/单元1 双表/单元6 双表/C.1 定位 → 计数显著大于 11
    const md = shengcheng_baogao_md(quanlian_shuru())
    const ci = md.split('| ---').length - 1
    assert.ok(ci >= 11, `分隔行计数 ${ci} 应 ≥ 11`)
  })
})

// ---------------------------------------------------------------------
// TestXianshi · 显示回归：金额/比率/周转率/布尔/缺数格式逐项锁定
// ---------------------------------------------------------------------
describe('TestXianshi · 显示回归：显示格式逐项锁定', () => {
  test('test_jine_xianshi: 金额显示 210,000.00 / 220,000.00 / 负号前置 -1,060.00', () => {
    // 显示层整数实现：分→元 divmod + 千分位，无浮点参与
    const md = shengcheng_baogao_md(quanlian_shuru())
    assert.ok(md.includes('210,000.00'), '实际收入 210,000.00') // 实际收入
    assert.ok(md.includes('220,000.00'), '预算收入 220,000.00') // 预算收入
    assert.ok(md.includes('-1,060.00'), '执行总差异 -1,060.00') // 执行总差异（负号前置）
  })

  test('test_bilv_xianshi: 比率显示 10.00% / +6.25% / 100.00%', () => {
    // 带符号只用于影响率列——数值上升/下降的语义显式化
    const md = shengcheng_baogao_md(quanlian_shuru())
    assert.ok(md.includes('10.00%'), '差异率 1000 基点') // 差异率 1000 基点
    assert.ok(md.includes('+6.25%'), '采购影响率 +625 基点') // 采购影响率 +625 基点
    assert.ok(md.includes('100.00%'), '积木费用模块独占占比') // 积木费用模块独占占比
  })

  test('test_zhouzhuanlv_xianshi: 周转率显示 0.2625 次 / 0.9767 次（去尾零）', () => {
    const md = shengcheng_baogao_md(quanlian_shuru())
    // 手算：资产 = 210,000/800,000 = 0.2625 次；资金 = 210,000/215,000 = 0.9767 次
    assert.ok(md.includes('| 资产周转率 | 0.2625 次 |'), '资产周转率行')
    assert.ok(md.includes('| 资金周转率 | 0.9767 次 |'), '资金周转率行')
  })

  test('test_buer_xianshi: 布尔显示 审批标志 = 是；恒等式成立 = 是', () => {
    // 布尔统一是/否（null → "—"）——审计报告不允许 True/False 混入
    const md = shengcheng_baogao_md(quanlian_shuru())
    assert.ok(md.includes('| 需人工审批 | 是 |'), '需人工审批行')
    assert.ok(md.includes('| 恒等式成立（规划 + 执行 = 原标准总） | 是 |'), '恒等式行')
  })

  test('test_queshu_xianshi: 缺数显示输出 "—"（占位非空串）', () => {
    // 缺数纪律的展示出口：宁显 "—" 不填空串/零——审计可查
    const md = shengcheng_baogao_md(quanlian_shuru())
    assert.ok(md.includes('—'), 'md 应含缺数占位符 —')
  })
})

// ---------------------------------------------------------------------
// TestDanjiZhi · 关键数值回归：各单元核心数字与上游输出一致
// （不重算、不失真——排版层唯一承诺的回归锁）
// ---------------------------------------------------------------------
describe('TestDanjiZhi · 关键数值回归：与上游输出一致', () => {
  test('test_gundong_shuzhi: 滚动表两期合计 433,311.00、滚动差异 -6,689.00', () => {
    const md = shengcheng_baogao_md(quanlian_shuru())
    // 手算：Q1 届满 210,000 + Q2 220,000×1.01×1.005 = 223,311 → 合计 433,311；
    // 差异 = 433,311 − 440,000 = -6,689（预算下调，负号前置显示）
    assert.ok(md.includes('| 年度合计 | — | 440,000.00 | 433,311.00 |'), '年度合计行')
    assert.ok(md.includes('-6,689.00'), '滚动差异 -6,689.00')
  })

  test('test_chayi_shuzhi: 差异表差额 2,000.00、F/A = A、预警 = 红', () => {
    // 期间费用 2,000,000 分 → 2,000.00 元；差异率 10% → 红档
    const md = shengcheng_baogao_md(quanlian_shuru())
    assert.ok(md.includes('2,000.00'), '差额 2,000.00')
    assert.ok(md.includes('| A | 红 |'), 'F/A 与预警列')
  })

  test('test_panding_shuzhi: 判定 = 混合纠错模式、情形 = 4、门检基点 = 100', () => {
    // 依据明细（yiju 快照）逐条入表——答辩溯源可直接引用本表
    const md = shengcheng_baogao_md(quanlian_shuru())
    assert.ok(md.includes('| 判定 | 混合纠错模式 |'), '判定行')
    assert.ok(md.includes('| 情形 | 4 |'), '情形行')
    assert.ok(md.includes('| 门检基点 | 100 |'), '门检基点行')
  })

  test('test_bsc_shuzhi: BSC 表（T-29#7 四列含达成率）总分 74、等级 合格、权重 40%', () => {
    const md = shengcheng_baogao_md(quanlian_shuru())
    // 达成率列 = 得分溯源（线性折算说明在节尾注记）
    assert.ok(md.includes('| 财务 | 75.00% | 75 | 40% |'), '财务行')
    assert.ok(md.includes('| 总分 | — | 74 | — |'), '总分行')
    assert.ok(md.includes('| 等级 | — | 合格 | — |'), '等级行')
    assert.ok(md.includes('维度得分 = KPI 达成率 × 100'), '节尾注记')
  })

  test('test_kpi_shuzhi: KPI 表营收达成率 95.45%、交付周期 7 天、异常事项 3 次', () => {
    // 15 项按定稿清单顺序，三类单位分派显示（pct/ci/tian·ci_shu）
    const md = shengcheng_baogao_md(quanlian_shuru())
    assert.ok(md.includes('| 营收达成率 | 95.45% |'), '营收达成率行')
    assert.ok(md.includes('| 交付周期 | 7 天 |'), '交付周期行')
    assert.ok(md.includes('| 异常事项数量 | 3 次 |'), '异常事项行')
  })

  test('test_zhenggai_shuzhi: 整改表预算修订案 + 强制整改；合计行出现', () => {
    // 混合纠错模式 → 预算修订案（审批=是）；红行 → 强制整改——两条各占一行
    const md = shengcheng_baogao_md(quanlian_shuru())
    assert.ok(md.includes('预算修订案'), '预算修订案')
    assert.ok(md.includes('强制整改'), '强制整改')
    assert.ok(md.includes('合计：'), '合计行')
  })
})

// ---------------------------------------------------------------------
// TestRongcuo · 容错回归：上游缺省 → （缺料）占位，绝不抛错
// ---------------------------------------------------------------------
describe('TestRongcuo · 容错回归：上游缺省占位', () => {
  test('test_kong_shuru: 全部缺省报告仍完整（抬头 + 12 节 + 缺料占位）', () => {
    // 12 个组装块（总览 + 8 单元 + 3 附表）——结构完整性契约；
    // 注意附表 C 全缺料时按 Python 口径渲染一行 "—"（非"（缺料）"），
    // 而抬头说明行自带 1 处 "（缺料）" 字样——两者相抵后计数恰为 12
    const md = shengcheng_baogao_md({})
    assert.ok(md.includes('数据计算测试报告'), '抬头')
    assert.ok(md.includes('（缺料）'), '缺料占位')
    const ci = md.split('（缺料）').length - 1
    assert.equal(ci, 12) // 12 块全缺（11 节占位 + 抬头 1 处）
  })

  test('test_quedingxing: 确定性——同输入两次排版完全一致', () => {
    // 排版纯函数：行顺序稳定是报告可比对的前提
    const shuru = quanlian_shuru()
    assert.equal(shengcheng_baogao_md(shuru), shengcheng_baogao_md(shuru))
  })
})
