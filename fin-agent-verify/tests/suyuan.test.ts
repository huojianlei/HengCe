// ======================================================================
// suyuan（经营变更双维溯源）单元测试 —— 期望值全部手工验算写死
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_suyuan.py（17 用例，
// 期望数字逐字保留，禁止改数字迁就实现）。
//
// 设计原则：
//     1. 回归基准 = 模块 docstring 的变更事件例题（原材料涨价+订单延迟+
//        产能提升）——影响率/作用方向/占比逐项锁定；
//     2. 作用方向 = 15 项 KPI 偏好表（越高越好 vs 越低越好）逐项锁定；
//     3. 占比分母 = Σ|净影响率|（同积木 D2）——合计恒 10000 基点是核心不变量。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音。
// 运行方式（验证区目录下）：
//     node --test tests/suyuan.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import type { SuyuanHang } from '../../plugins/fin-agent/src/suyuan.ts'
import { SuyuanCuowu, jisuan_suyuan } from '../../plugins/fin-agent/src/suyuan.ts'

/** 构造 docstring 例题的三行输入（变更事件：涨价+延迟+产能提升）。
 *
 *  Python 版以位置参数构造 frozen dataclass，TS 侧以同字段名对象字面量
 *  构造（SuyuanHang 接口 readonly 字段一一对应）。 */
function liti_hang(): SuyuanHang[] {
  return [
    { kpi_mingcheng: '采购成本变动率', bianhua_qian: 100_000, bianhua_hou: 108_000, yuan_yusuan: 100_000 },
    { kpi_mingcheng: '交付周期', bianhua_qian: 5, bianhua_hou: 8, yuan_yusuan: 5 },
    { kpi_mingcheng: '产能利用率', bianhua_qian: 800, bianhua_hou: 850, yuan_yusuan: 800 },
  ]
}

describe('TestLiti · 例题回归：影响率/数值方向/作用方向/占比/TOP3 全部对上', () => {
  test('test_yingxianglv: 三行影响率：+8% → 800、+60% → 6000、+6.25% → 625 基点', () => {
    // 手算：采购 (108000−100000)/100000 = +8%；交付 (8−5)/5 = +60%；
    // 产能 (850−800)/800 = +6.25%——全部按 yuan_yusuan 作分母
    const jg = jisuan_suyuan(liti_hang())
    assert.deepEqual(jg.xiang.map((x) => x.yingxianglv_bps), [800, 6000, 625])
    // 数值方向：三行都是上升
    assert.deepEqual(jg.xiang.map((x) => x.shuzhi_fangxiang), ['上升', '上升', '上升'])
  })

  test('test_zuoyong_pianhao: 偏好表：采购/交付周期越低越好（上升=负向）；产能越高越好（正向）', () => {
    // 偏好表即模块内 KPI_PIANHAO：作用方向 = 数值方向 × 偏好（四象限）
    const jg = jisuan_suyuan(liti_hang())
    assert.deepEqual(jg.xiang.map((x) => x.zuoyong), ['负向作用', '负向作用', '正向作用'])
  })

  test('test_zhanbi_he_10000: 占比分母 = 800+6000+625 = 7425；三行占比合计恒 10000', () => {
    const jg = jisuan_suyuan(liti_hang())
    assert.equal(jg.yingxiang_fenmu_bps, 7425)
    // 手算：800/7425=10.77%→1077；6000/7425=80.81%→8081；
    // 625/7425=8.42%→842（half-up）
    assert.deepEqual(jg.xiang.map((x) => x.zhanbi_bps), [1077, 8081, 842])
    assert.equal(jg.xiang.reduce((he, x) => he + (x.zhanbi_bps as number), 0), 10000)
  })

  test('test_top3: TOP3：正向 [产能利用率]；负向 [交付周期, 采购成本变动率]（降序）', () => {
    // 负向 TOP3 按 |影响率| 降序：交付 6000 > 采购 800
    const jg = jisuan_suyuan(liti_hang())
    assert.deepEqual(jg.zhengxiang_top3, ['产能利用率'])
    assert.deepEqual(jg.fuxiang_top3, ['交付周期', '采购成本变动率'])
  })

  test('test_gongshi_ziduan: 公式字段（T-29#4）：结果携带影响率计算公式文本', () => {
    // 公式与定稿 §8.3 口径一致——报告【计算公式】列的数据源
    const jg = jisuan_suyuan([{ kpi_mingcheng: '交付周期', bianhua_qian: 5, bianhua_hou: 8, yuan_yusuan: 5 }])
    assert.ok(jg.gongshi.includes('原始预算数值'))
    assert.ok(jg.gongshi.includes('变更后数值 − 变更前数值'))
  })
})

describe('TestZuoyong · 作用方向：偏好表 × 数值方向四象限全覆盖', () => {
  test('test_xiajiang_yuedi_shi_zhengxiang: 交付周期 8→5（下降、越低越好）→ 正向作用，影响率 −60%', () => {
    // 符号纪律：影响率负 = 数值下降；作用方向才是经营语义
    const jg = jisuan_suyuan([{ kpi_mingcheng: '交付周期', bianhua_qian: 8, bianhua_hou: 5, yuan_yusuan: 8 }])
    assert.equal(jg.xiang[0]!.yingxianglv_bps, -3750) // (5−8)/8 = −37.5%
    assert.equal(jg.xiang[0]!.zuoyong, '正向作用')
  })

  test('test_xiajiang_yuegao_shi_fuxiang: 产能 850→800（下降、越高越好）→ 负向作用', () => {
    const jg = jisuan_suyuan([{ kpi_mingcheng: '产能利用率', bianhua_qian: 850, bianhua_hou: 800, yuan_yusuan: 850 }])
    assert.equal(jg.xiang[0]!.zuoyong, '负向作用')
  })

  test('test_chiping_wu_zuoyong: 持平：数值方向持平、作用无作用、影响率 0', () => {
    const jg = jisuan_suyuan([{ kpi_mingcheng: '交付周期', bianhua_qian: 5, bianhua_hou: 5, yuan_yusuan: 5 }])
    assert.equal(jg.xiang[0]!.shuzhi_fangxiang, '持平')
    assert.equal(jg.xiang[0]!.zuoyong, '无作用')
    assert.equal(jg.xiang[0]!.yingxianglv_bps, 0)
  })
})

describe('TestQueshu · 缺数纪律：原始预算缺失/≤0 → 该行 null，不参与占比分母', () => {
  test('test_yuan_yusuan_None: yuan_yusuan None → 影响率/占比 null；TOP3 跳过该行', () => {
    const jg = jisuan_suyuan([{ kpi_mingcheng: '交付周期', bianhua_qian: 5, bianhua_hou: 8, yuan_yusuan: null }])
    assert.equal(jg.xiang[0]!.yingxianglv_bps, null)
    assert.equal(jg.xiang[0]!.zhanbi_bps, null)
    assert.deepEqual(jg.zhengxiang_top3, [])
    assert.deepEqual(jg.fuxiang_top3, [])
  })

  test('test_yuan_yusuan_ling_bu_jin_fenmu: yuan_yusuan = 0 → 该行 null；其余行正常且分母只含可算行', () => {
    const jg = jisuan_suyuan([
      { kpi_mingcheng: '交付周期', bianhua_qian: 5, bianhua_hou: 8, yuan_yusuan: 0 }, // 分母 0 → null
      { kpi_mingcheng: '产能利用率', bianhua_qian: 800, bianhua_hou: 850, yuan_yusuan: 800 }, // 影响率 625
    ])
    assert.equal(jg.xiang[0]!.yingxianglv_bps, null)
    assert.equal(jg.yingxiang_fenmu_bps, 625)
    // 唯一可算行独占 100%
    assert.equal(jg.xiang[1]!.zhanbi_bps, 10000)
  })

  test('test_quanbu_None: 全部行不可算 → 分母 0 → 占比全 null、TOP3 空', () => {
    // 除零纪律（与 kpi/积木同源）：分母 0 时不臆造占比，交人工
    const jg = jisuan_suyuan([{ kpi_mingcheng: '交付周期', bianhua_qian: 5, bianhua_hou: 8, yuan_yusuan: null }])
    assert.equal(jg.yingxiang_fenmu_bps, 0)
    assert.equal(jg.xiang[0]!.zhanbi_bps, null)
  })
})

describe('TestPaiming · TOP3 排名：降序、并列取输入顺序、超过三项截断', () => {
  test('test_binglie_qu_shuru_shunxu: 两个正向作用影响率相同 → 按输入顺序排名', () => {
    // 排序稳定性：Python sort 稳定 → 并列自动保输入顺序（模块文档约定）
    const jg = jisuan_suyuan([
      { kpi_mingcheng: '产能利用率', bianhua_qian: 100, bianhua_hou: 200, yuan_yusuan: 100 }, // +100% → 10000 正向
      { kpi_mingcheng: '业务完成进度', bianhua_qian: 100, bianhua_hou: 200, yuan_yusuan: 100 }, // 同影响率
    ])
    assert.deepEqual(jg.zhengxiang_top3, ['产能利用率', '业务完成进度'])
  })

  test('test_chaoguo_san_xiang_jieduan: 四个正向作用 → TOP3 只取前三（按 |影响率| 降序）', () => {
    const jg = jisuan_suyuan([
      { kpi_mingcheng: '产能利用率', bianhua_qian: 100, bianhua_hou: 110, yuan_yusuan: 100 }, // +10% → 1000
      { kpi_mingcheng: '业务完成进度', bianhua_qian: 100, bianhua_hou: 130, yuan_yusuan: 100 }, // +30% → 3000
      { kpi_mingcheng: '客户满意度', bianhua_qian: 100, bianhua_hou: 120, yuan_yusuan: 100 }, // +20% → 2000
      { kpi_mingcheng: '供应链履约率', bianhua_qian: 100, bianhua_hou: 140, yuan_yusuan: 100 }, // +40% → 4000
    ])
    assert.deepEqual(jg.zhengxiang_top3, ['供应链履约率', '业务完成进度', '客户满意度'])
  })
})

describe('TestJiaoyan · 输入校验与确定性', () => {
  test('test_weizhi_kpi_ming_jujue: KPI 名不在 15 项清单 → 整行拒绝（防脏名混入）', () => {
    // 溯源是结构化流程：KPI 名必须来自 KPI 库（15 项清单），不猜语义
    assert.throws(
      () => jisuan_suyuan([{ kpi_mingcheng: '随便指标', bianhua_qian: 1, bianhua_hou: 2, yuan_yusuan: 1 }]),
      SuyuanCuowu,
    )
  })

  test('test_chongfu_kpi_jujue: 同一 KPI 两行 → 拒绝（防双计）', () => {
    // 同一变更事件对同一 KPI 只允许一行——重复即数据问题
    assert.throws(
      () => jisuan_suyuan([
        { kpi_mingcheng: '交付周期', bianhua_qian: 5, bianhua_hou: 8, yuan_yusuan: 5 },
        { kpi_mingcheng: '交付周期', bianhua_qian: 6, bianhua_hou: 9, yuan_yusuan: 5 },
      ]),
      SuyuanCuowu,
    )
  })

  test('test_feifa_zhi_jujue: 负数 / 浮点 / 布尔 / 空列表 → 拒绝', () => {
    // bool 是 int 子类，须显式排除（与全项目校验纪律一致）；
    // TS 侧入参以 as any 包一层注入非法形态，断言抛 SuyuanCuowu
    for (const huai of [-1, 100.5, true]) {
      assert.throws(
        () => jisuan_suyuan([{ kpi_mingcheng: '交付周期', bianhua_qian: huai as unknown as number, bianhua_hou: 8, yuan_yusuan: 5 }]),
        SuyuanCuowu,
        `${huai} 应被拒绝`,
      )
    }
    assert.throws(() => jisuan_suyuan([]), SuyuanCuowu)
  })

  test('test_quedingxing: 确定性：同输入两次调用结果完全一致（dataclass 等值）', () => {
    // 纯函数要求：无 I/O、无全局状态 → 同输入必同输出
    const hang = liti_hang()
    assert.deepEqual(jisuan_suyuan(hang), jisuan_suyuan(hang))
  })
})
