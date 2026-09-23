// kpi（KPI 指标库）单元测试 —— 期望值全部手工验算写死（转写自 algo/tests/test_kpi.py）。
//
// 设计原则：
//     1. 回归基准 = 教材 06 章验算例 + 定稿 §8 全部 15 项公式逐项锁定；
//     2. 缺数纪律：分子/分母缺数或分母 ≤ 0 → null（交人工，不臆造）；
//     3. 单位纪律：比率/周转率 = 整数基点（1 次 = 10000 基点）；
//        交付周期 = 天；异常事项 = 次。
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { KpiCuowu, jisuan_kpi } from '../../plugins/fin-agent/src/kpi.ts'
import type { KpiShuru } from '../../plugins/fin-agent/src/kpi.ts'

/** 构造教材 06 章验算例输入（金额元 ×100 转分；计数为整数件）。 */
function jiaocai_shuru(): KpiShuru {
  return {
    shouru_shiji_fen: 15_000_000, shouru_yusuan_fen: 14_000_000,
    maoli_fen: 9_000_000, jingshui_fen: 3_000_000, pbit_fen: 4_500_000,
    ziben_zhanyong_fen: 7_500_000,
    liudong_zichan_qichu_fen: 5_000_000, liudong_zichan_qimo_fen: 6_000_000,
    liudong_fuzhai_qichu_fen: 2_000_000, liudong_fuzhai_qimo_fen: 2_500_000,
    feiyong_shiji_fen: 11_000_000, feiyong_yusuan_fen: 10_000_000,
    kekong_chengben_shiji_fen: 9_500_000, kekong_chengben_yusuan_fen: 10_000_000,
    caigou_benqi_fen: 10_800_000, caigou_shangqi_fen: 10_000_000,
    shiji_chanchu: 800, qianzai_channeng: 1000,
    dingdan_zongshu: 200, lvyue_dingdan_shu: 190,
    jiaofu_zhouqi_tian_shu: 6,
    manyi_keshu: 180, shoufang_keshu: 200,
    jihua_yewu_liang: 1000, wancheng_yewu_liang: 750,
    yichang_shijian_shu: 3,
  }
}

test('教材06章验算例·15项全量回归', () => {
  // 手算（比率=基点；周转率 1次=10000基点）：
  //   营收达成率 15M/14M=107.142857% → 10714；成本控制率 95% → 9500
  //   费用偏差率 +10% → 1000；毛利率 60% → 6000；净利率 20% → 2000
  //   销售利润率 30% → 3000；资产周转率 2次 → 20000
  //   资金周转率 平均营运资金=(3M+3.5M)/2=3.25M → 4.6154次 → 46154
  //   采购变动率 +8% → 800
  const jg = jisuan_kpi(jiaocai_shuru())
  assert.equal(jg.yingshou_dachenglv_bps, 10714)
  assert.equal(jg.chengben_kongzhilv_bps, 9500)
  assert.equal(jg.feiyong_pianchalv_bps, 1000)
  assert.equal(jg.maolilv_bps, 6000)
  assert.equal(jg.jinglirunlv_bps, 2000)
  assert.equal(jg.xiaoshou_lirunlv_bps, 3000)
  assert.equal(jg.zichan_zhouzhuanlv_bps, 20000)
  assert.equal(jg.zijin_zhouzhuanlv_bps, 46154)
  assert.equal(jg.caigou_chengben_bian_donglv_bps, 800)
  // 非财务：履约率 95% → 9500；产能 80% → 8000；交付 6 天；
  // 满意度 90% → 9000；进度 75% → 7500；异常 3 次
  assert.equal(jg.gongyinglian_lvyuelv_bps, 9500)
  assert.equal(jg.channeng_liyonglv_bps, 8000)
  assert.equal(jg.jiaofu_zhouqi_tian, 6)
  assert.equal(jg.kehu_manyilv_bps, 9000)
  assert.equal(jg.yewu_jindu_bps, 7500)
  assert.equal(jg.yichang_shijian_shu, 3)
})

test('带符号指标·节约为负', () => {
  // 符号纪律：负 = 节约/下降（有利）；展示口径正 = 超支/上涨
  const jg = jisuan_kpi({
    feiyong_shiji_fen: 9_000_000, feiyong_yusuan_fen: 10_000_000,
    caigou_benqi_fen: 9_500_000, caigou_shangqi_fen: 10_000_000,
  })
  assert.equal(jg.feiyong_pianchalv_bps, -1000)          // 节约 10%
  assert.equal(jg.caigou_chengben_bian_donglv_bps, -500) // 下降 5%
})

test('缺数纪律·只给收入其余None', () => {
  // 缺数 ≠ 零（与 data_ingest 空值拒收口径同源），交人工补数
  const jg = jisuan_kpi({ shouru_shiji_fen: 15_000_000, shouru_yusuan_fen: 14_000_000 })
  assert.equal(jg.yingshou_dachenglv_bps, 10714)
  assert.equal(jg.maolilv_bps, null)
  assert.equal(jg.feiyong_pianchalv_bps, null)
  assert.equal(jg.yichang_shijian_shu, null)
})

test('分母为零→None', () => {
  // 预算收入 0 → 营收达成率 None；实际收入 0 → 毛利率分母 0 → None
  const jg = jisuan_kpi({ shouru_shiji_fen: 0, shouru_yusuan_fen: 0, maoli_fen: 50 })
  assert.equal(jg.yingshou_dachenglv_bps, null)
  assert.equal(jg.maolilv_bps, null)
})

test('平均营运资金≤0→资金周转率None', () => {
  const jg = jisuan_kpi({
    shouru_shiji_fen: 15_000_000,
    liudong_zichan_qichu_fen: 1_000_000, liudong_zichan_qimo_fen: 1_000_000,
    liudong_fuzhai_qichu_fen: 1_500_000, liudong_fuzhai_qimo_fen: 1_500_000,
  })
  assert.equal(jg.zijin_zhouzhuanlv_bps, null)
})

test('half-up·1/3→3333、2/3→6667', () => {
  // 1/3=3333.33 → 3333（不足半舍去）；2/3=6666.67 → 6667（过半进位）
  const jg = jisuan_kpi({ shouru_shiji_fen: 1, shouru_yusuan_fen: 3 })
  assert.equal(jg.yingshou_dachenglv_bps, 3333)
  const jg2 = jisuan_kpi({ shouru_shiji_fen: 2, shouru_yusuan_fen: 3 })
  assert.equal(jg2.yingshou_dachenglv_bps, 6667)
})

test('营运资金half-up·恰过半进位', () => {
  // 期初净 1,000,000、期末 2,000,001 → 和 3,000,001 → (3,000,001+1)//2 = 1,500,001
  const jg = jisuan_kpi({
    shouru_shiji_fen: 3_000_000,
    liudong_zichan_qichu_fen: 1_000_000, liudong_zichan_qimo_fen: 2_000_001,
    liudong_fuzhai_qichu_fen: 0, liudong_fuzhai_qimo_fen: 0,
  })
  // 3,000,000/1,500,001 = 2 次 → 20000 基点
  assert.equal(jg.zijin_zhouzhuanlv_bps, 20000)
})

test('非法值拒绝·负数/浮点/布尔/超上限', () => {
  for (const huai of [-1, 100.5, true, 9 * 10 ** 11 + 1]) {
    assert.throws(
      () => jisuan_kpi({ shouru_shiji_fen: huai } as unknown as KpiShuru),
      KpiCuowu,
      `${String(huai)} 应被拒绝`,
    )
  }
})

test('非KpiShuru输入拒绝', () => {
  assert.throws(() => jisuan_kpi('不是输入' as unknown as KpiShuru), KpiCuowu)
})

test('确定性·同输入两次全等', () => {
  const shuru = jiaocai_shuru()
  assert.deepStrictEqual(jisuan_kpi(shuru), jisuan_kpi(shuru))
})
