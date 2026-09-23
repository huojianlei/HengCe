// ======================================================================
// KPI 指标库 —— 方案B 步骤 1b 的【15 项指标计算】确定性核心（FR-11）
// ======================================================================
//
// 转写自 D:\AppProject\algo\kpi.py（Python 版为唯一行为准绳；
// 拼音标识符逐字保留，期望值以 algo/tests/test_kpi.py 为准，
// 对应验证区 tests/kpi.test.ts，测试数字逐字对应）。
//
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
//     专有缩写可保留（KPI、PBIT、BSC 等）。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs/textbook/finagent-算法核对文档-定稿.md v2.1 §8（15 项公式表，定稿#9/#10）
//     docs/textbook/06-kpi-dictionary.md（财务 9 项 + 非财务 6 项的公式/口径/来源）
//     docs/01-需求说明.md v2.0 §3 FR-11（P1；公式按定稿口径）
//     docs/proposal-full-extract.txt 行 105~112（财务 9 + 非财务 6 清单）
//
// 15 项清单（财务 9 + 非财务 6）：
//     财务：营收达成率 / 成本控制率 / 费用偏差率 / 毛利率 / 净利润率 /
//           销售利润率 / 资产周转率 / 资金周转率 / 采购成本变动率；
//     非财务：供应链履约率 / 产能利用率 / 交付周期 / 客户满意度 /
//           业务完成进度 / 异常事项数量。
//
// 单位与整数纪律（全系统统一）：
//     比率/达成率类输出【整数基点】（1% = 100 基点；100% = 10000 基点）；
//     周转率按"次"计——1 次 = 10000 基点（与比率统一，答辩口径在注释声明）；
//     交付周期输出【天】（整数）；异常事项数量输出【次】（整数）；
//     全部 half-up 整数舍入、零浮点；纯函数（无 I/O、无全局状态）。
//
// 缺数纪律（除零/缺数 → null，交人工——与全项目除零纪律一致）：
//     分子/分母任一缺失 → 该项 null；分母 ≤ 0 → 该项 null；
//     费用偏差率 / 采购成本变动率 分子可负（节约为负），输出保留符号。
//
// TS 差异（转写裁决）：金额×基点等中间量可超 2^53 → 除法求比率统一走公共库
//     int-math 的 bili_bps / dai_fuhao_bps / pingjun_half_up（BigInt 半进位），
//     与 Python 原式逐式对应，禁止裸 `*` 后 Math.round。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     KpiShuru            KPI 输入（15 项指标的显式取数字段，缺数填 null）
//     KpiJieguo           KPI 结果（15 项指标输出，bps/天/次，缺数 null）
//     KpiCuowu            KPI 错误（校验失败异常）
//     jisuan_kpi          计算 KPI（主函数）
//     yingshou_dachenglv_bps       营收达成率（基点，非负）
//     chengben_kongzhilv_bps       成本控制率（基点，非负）
//     feiyong_pianchalv_bps        费用偏差率（基点，可负——正=超支）
//     maolilv_bps / jinglirunlv_bps / xiaoshou_lirunlv_bps   毛利率/净利率/销售利润率
//     zichan_zhouzhuanlv_bps / zijin_zhouzhuanlv_bps         资产/资金周转率（1 次=10000 基点）
//     caigou_chengben_bian_donglv_bps  采购成本变动率（基点，可负）
//     gongyinglian_lvyuelv_bps     供应链履约率（基点）
//     channeng_liyonglv_bps        产能利用率（基点）
//     jiaofu_zhouqi_tian           交付周期（天）
//     kehu_manyilv_bps             客户满意度（基点）
//     yewu_jindu_bps               业务完成进度（基点）
//     yichang_shijian_shu          异常事项数量（次）
//
// 与上下游的关系：
//     上游：data_ingest（四类数据供数——取数装配在端到端层/看板数据接口做，
//           本模块是纯公式层，输入显式字段）；
//     下游：bsc（四维达成率取自本模块对应指标）、suyuan（变更溯源吃 15 项）、
//           看板数据接口（KPI 展示）。
//
// 建立：2026-08-23 ｜ TS 转写 2026-09-05
// ======================================================================

import { bili_bps, dai_fuhao_bps, pingjun_half_up } from './int-math.ts'

// ======================================================================
// 常量区
// ======================================================================

/** 单字段金额/计数上限（分/件/天/次）——防脏数据的合理性校验 */
export const ZUIDA_ZHI = 9 * 10 ** 11

/** KPI 输入校验失败（字段形态非法）。
 *
 *  Python 继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）；
 *  TS 侧按插件约定统一 extends Error，中文报错文案与 Python 逐字一致。 */
export class KpiCuowu extends Error {}

// ======================================================================
// 数据结构区（Python frozen dataclass → readonly interface + 对象字面量）
// ======================================================================

/** KPI 输入：15 项指标的显式取数字段（缺数填 null/缺省不传，不臆造）。
 *
 *  字段说明（单位：金额=整数分；计数=整数件/单/天/次）：
 *      shouru_shiji_fen / shouru_yusuan_fen        实际/预算 收入（不含税）
 *      kekong_chengben_shiji_fen / _yusuan_fen     实际/预算 可控成本
 *      feiyong_shiji_fen / feiyong_yusuan_fen      实际/预算 期间费用
 *      maoli_fen / jingshui_fen / pbit_fen         实际 毛利/税后净利/息税前利润
 *      ziben_zhanyong_fen                          平均资本占用（非流动负债+权益）
 *      liudong_zichan_qichu_fen / _qimo_fen        期初/期末 流动资产
 *      liudong_fuzhai_qichu_fen / _qimo_fen        期初/期末 流动负债
 *      caigou_benqi_fen / caigou_shangqi_fen       本期/上期 采购成本
 *      shiji_chanchu / qianzai_channeng            实际产出/潜在产能（件）
 *      dingdan_zongshu / lvyue_dingdan_shu         订单总数/按期足额交付订单数
 *      jiaofu_zhouqi_tian_shu                      平均下单→交付天数
 *      manyi_keshu / shoufang_keshu                满意客户数/受访客户数
 *      jihua_yewu_liang / wancheng_yewu_liang      计划业务量/已完成业务量
 *      yichang_shijian_shu                         异常事项数量（次）
 *
 *  Python dataclass 全字段默认 None → TS 侧全部可选（?:），缺省即缺数。
 */
export interface KpiShuru {
  // ---- 财务 9 项取数 ----
  readonly shouru_shiji_fen?: number | null
  readonly shouru_yusuan_fen?: number | null
  readonly kekong_chengben_shiji_fen?: number | null
  readonly kekong_chengben_yusuan_fen?: number | null
  readonly feiyong_shiji_fen?: number | null
  readonly feiyong_yusuan_fen?: number | null
  readonly maoli_fen?: number | null
  readonly jingshui_fen?: number | null
  readonly pbit_fen?: number | null
  readonly ziben_zhanyong_fen?: number | null
  readonly liudong_zichan_qichu_fen?: number | null
  readonly liudong_zichan_qimo_fen?: number | null
  readonly liudong_fuzhai_qichu_fen?: number | null
  readonly liudong_fuzhai_qimo_fen?: number | null
  readonly caigou_benqi_fen?: number | null
  readonly caigou_shangqi_fen?: number | null
  // ---- 非财务 6 项取数 ----
  readonly shiji_chanchu?: number | null
  readonly qianzai_channeng?: number | null
  readonly dingdan_zongshu?: number | null
  readonly lvyue_dingdan_shu?: number | null
  readonly jiaofu_zhouqi_tian_shu?: number | null
  readonly manyi_keshu?: number | null
  readonly shoufang_keshu?: number | null
  readonly jihua_yewu_liang?: number | null
  readonly wancheng_yewu_liang?: number | null
  readonly yichang_shijian_shu?: number | null
}

/** KPI 输入的 26 个取数字段名（与 Python 校验循环的 (值, 字段名) 序列一致） */
const SHURU_ZIDUAN_MING: readonly string[] = [
  'shouru_shiji_fen',
  'shouru_yusuan_fen',
  'kekong_chengben_shiji_fen',
  'kekong_chengben_yusuan_fen',
  'feiyong_shiji_fen',
  'feiyong_yusuan_fen',
  'maoli_fen',
  'jingshui_fen',
  'pbit_fen',
  'ziben_zhanyong_fen',
  'liudong_zichan_qichu_fen',
  'liudong_zichan_qimo_fen',
  'liudong_fuzhai_qichu_fen',
  'liudong_fuzhai_qimo_fen',
  'caigou_benqi_fen',
  'caigou_shangqi_fen',
  'shiji_chanchu',
  'qianzai_channeng',
  'dingdan_zongshu',
  'lvyue_dingdan_shu',
  'jiaofu_zhouqi_tian_shu',
  'manyi_keshu',
  'shoufang_keshu',
  'jihua_yewu_liang',
  'wancheng_yewu_liang',
  'yichang_shijian_shu',
]

/** KPI 结果：15 项指标（缺数 null；单位见各字段注释）。
 *
 *  字段说明：
 *      比率/达成率/周转率类：整数基点（100% = 10000；1 次 = 10000）；
 *      费用偏差率 / 采购成本变动率：可负（负 = 节约）；
 *      交付周期：天；异常事项数量：次。
 */
export interface KpiJieguo {
  readonly yingshou_dachenglv_bps: number | null // 营收达成率
  readonly chengben_kongzhilv_bps: number | null // 成本控制率
  readonly feiyong_pianchalv_bps: number | null // 费用偏差率（可负）
  readonly maolilv_bps: number | null // 毛利率
  readonly jinglirunlv_bps: number | null // 净利润率
  readonly xiaoshou_lirunlv_bps: number | null // 销售利润率
  readonly zichan_zhouzhuanlv_bps: number | null // 资产周转率（次→基点）
  readonly zijin_zhouzhuanlv_bps: number | null // 资金周转率（次→基点）
  readonly caigou_chengben_bian_donglv_bps: number | null // 采购成本变动率（可负）
  readonly gongyinglian_lvyuelv_bps: number | null // 供应链履约率
  readonly channeng_liyonglv_bps: number | null // 产能利用率
  readonly jiaofu_zhouqi_tian: number | null // 交付周期（天）
  readonly kehu_manyilv_bps: number | null // 客户满意度
  readonly yewu_jindu_bps: number | null // 业务完成进度
  readonly yichang_shijian_shu: number | null // 异常事项数量（次）
}

// ======================================================================
// 内部工具函数区
// ======================================================================

/** Python f-string `{x!r}`（repr）的 TS 对应：字符串/对象走 JSON 化，
 *  布尔回显 True/False（Python bool repr），其余 String 化。仅用于报错文案。 */
function _repr(x: unknown): string {
  if (x === true) return 'True'
  if (x === false) return 'False'
  if (typeof x === 'string') return JSON.stringify(x)
  if (typeof x === 'object' && x !== null) return JSON.stringify(x)
  return String(x)
}

/** isinstance(shuru, KpiShuru) 的鸭子对应：对象（非数组）且自有键全部属于
 *  26 个取数字段（空对象 = KpiShuru() 全缺数，合法）。 */
function _shi_kpi_shuru(x: unknown): boolean {
  if (typeof x !== 'object' || x === null || Array.isArray(x)) return false
  return Object.keys(x).every((k) => SHURU_ZIDUAN_MING.includes(k))
}

/** 非负整数校验：null/缺省放行（缺数），非缺省必须是非负整数（排除 bool）。 */
function _jianyan_feifu(shuzhi: unknown, biaoshi: string): void {
  if (shuzhi == null) {
    return // None 放行（缺数交人工，不臆造）
  }
  // bool 是 int 子类须显式排除——TS 的 typeof 校验天然覆盖（true 不是 number）
  if (typeof shuzhi !== 'number' || !Number.isInteger(shuzhi)) {
    throw new KpiCuowu(`${biaoshi} 必须为整数或 None：${_repr(shuzhi)}`)
  }
  if (shuzhi < 0 || shuzhi > ZUIDA_ZHI) {
    throw new KpiCuowu(`${biaoshi} 必须在 [0, ${ZUIDA_ZHI}] 内：${shuzhi}`)
  }
}

/** 非负比率（基点）= 分子 ÷ 分母 × 10000，half-up 整数实现。
 *
 *  分子/分母任一缺数或分母 ≤ 0 → null（缺数纪律，交人工）；
 *  Python 原式 (2×分子×10000 + 分母) // (2×分母) 即 half-up，全程无浮点；
 *  TS 侧走公共库 bili_bps（BigInt 半进位），与 Python 逐式对应。 */
function _bili_bps(fenzi: number | null | undefined, fenmu: number | null | undefined): number | null {
  if (fenzi == null || fenmu == null || fenmu <= 0) {
    return null
  }
  return bili_bps(fenzi, fenmu)
}

/** 带符号偏差率（基点）= (分子−分母) ÷ 分母 × 10000，half-up。
 *
 *  用于费用偏差率/采购成本变动率：分子是实际（本期）、分母是预算（上期），
 *  正 = 超支/上涨（不利），负 = 节约/下降（有利）；符号保留。
 *  分母 ≤ 0 或任一缺数 → null（缺数纪律，交人工）。
 *  TS 侧走公共库 dai_fuhao_bps（先取绝对值算 half-up 再补符号）。 */
function _daifuhao_bps(fenzi: number | null | undefined, fenmu: number | null | undefined): number | null {
  if (fenzi == null || fenmu == null || fenmu <= 0) {
    return null
  }
  return dai_fuhao_bps(fenzi - fenmu, fenmu)
}

/** 平均营运资金 =（期初营运资金 + 期末营运资金）÷ 2，half-up。
 *
 *  营运资金 = 流动资产 − 流动负债（定稿 #9 口径：平均 =（期初+期末）÷2）。
 *  四个输入任一缺数 → null；half-up 整数实现（a+b+1)//2（a、b 为两个
 *  期末净营运资金，可为负——负数说明营运资金为负，交调用方按分母处理）。
 *  TS 侧走公共库 pingjun_half_up（负数向零舍入，与正数规则同构）。 */
function _pingjun_yunying_zijin(
  qichu_zichan: number | null | undefined,
  qimo_zichan: number | null | undefined,
  qichu_fuzhai: number | null | undefined,
  qimo_fuzhai: number | null | undefined,
): number | null {
  if (qichu_zichan == null || qimo_zichan == null || qichu_fuzhai == null || qimo_fuzhai == null) {
    return null
  }
  const qichu_jing = qichu_zichan - qichu_fuzhai // 期初营运资金（可为负）
  const qimo_jing = qimo_zichan - qimo_fuzhai // 期末营运资金（可为负）
  return pingjun_half_up(qichu_jing + qimo_jing) // half-up：负数向零舍入
}

// ======================================================================
// 对外接口区（唯一的计算入口）
// ======================================================================

/** 15 项 KPI 计算（方案B 步骤 1b；纯函数）。
 *
 *  参数：shuru —— KpiShuru（显式取数字段，缺数填 null/缺省不传）。
 *
 *  返回：KpiJieguo（15 项指标；缺数/分母 ≤ 0 → 对应项 null）。
 *
 *  处理顺序：
 *      ① 全字段形态校验 → ② 财务 9 项 → ③ 非财务 6 项 → ④ 组装输出。
 */
export function jisuan_kpi(shuru: KpiShuru): KpiJieguo {
  if (!_shi_kpi_shuru(shuru)) {
    throw new KpiCuowu(`输入必须是 KpiShuru：${_repr(shuru)}`)
  }

  // ① 全字段形态校验（null 放行——缺数交人工，不臆造）
  for (const biaoshi of SHURU_ZIDUAN_MING) {
    _jianyan_feifu((shuru as Record<string, unknown>)[biaoshi], biaoshi)
  }

  // ② 财务 9 项（公式见模块头；比率统一基点、half-up）
  // 1 营收达成率 = 实际收入 ÷ 预算收入
  const yingshou = _bili_bps(shuru.shouru_shiji_fen, shuru.shouru_yusuan_fen)
  // 2 成本控制率 = 实际可控成本 ÷ 预算可控成本
  const chengben_kongzhi = _bili_bps(shuru.kekong_chengben_shiji_fen, shuru.kekong_chengben_yusuan_fen)
  // 3 费用偏差率 =（实际 − 预算）÷ 预算（带符号）
  const feiyong_piancha = _daifuhao_bps(shuru.feiyong_shiji_fen, shuru.feiyong_yusuan_fen)
  // 4 毛利率 = 毛利 ÷ 收入
  const maolilv = _bili_bps(shuru.maoli_fen, shuru.shouru_shiji_fen)
  // 5 净利润率 = 税后净利 ÷ 收入
  const jinglirunlv = _bili_bps(shuru.jingshui_fen, shuru.shouru_shiji_fen)
  // 6 销售利润率 = PBIT ÷ 收入
  const xiaoshou_lirunlv = _bili_bps(shuru.pbit_fen, shuru.shouru_shiji_fen)
  // 7 资产周转率 = 收入 ÷ 平均资本占用（1 次 = 10000 基点）
  const zichan = _bili_bps(shuru.shouru_shiji_fen, shuru.ziben_zhanyong_fen)
  // 8 资金周转率 = 收入 ÷ 平均营运资金（定稿 #9 补：平均=（期初+期末）÷2）
  const pingjun_yingyun = _pingjun_yunying_zijin(
    shuru.liudong_zichan_qichu_fen,
    shuru.liudong_zichan_qimo_fen,
    shuru.liudong_fuzhai_qichu_fen,
    shuru.liudong_fuzhai_qimo_fen,
  )
  const zijin = _bili_bps(shuru.shouru_shiji_fen, pingjun_yingyun)
  // 9 采购成本变动率 =（本期 − 上期）÷ 上期（带符号）
  const caigou = _daifuhao_bps(shuru.caigou_benqi_fen, shuru.caigou_shangqi_fen)

  // ③ 非财务 6 项
  // 10 供应链履约率 = 按期足额交付订单数 ÷ 订单总数
  const gongyinglian = _bili_bps(shuru.lvyue_dingdan_shu, shuru.dingdan_zongshu)
  // 11 产能利用率 = 实际产出 ÷ 潜在产能
  const channeng = _bili_bps(shuru.shiji_chanchu, shuru.qianzai_channeng)
  // 12 交付周期 = 平均下单→交付天数（直接值，缺数 null）
  const jiaofu_zhouqi = shuru.jiaofu_zhouqi_tian_shu ?? null
  // 13 客户满意度 = 满意客户数 ÷ 受访客户数
  const kehu_manyi = _bili_bps(shuru.manyi_keshu, shuru.shoufang_keshu)
  // 14 业务完成进度 = 已完成业务量 ÷ 计划业务量
  const yewu_jindu = _bili_bps(shuru.wancheng_yewu_liang, shuru.jihua_yewu_liang)
  // 15 异常事项数量 = 期内异常事件计数（直接值）
  const yichang = shuru.yichang_shijian_shu ?? null

  // ④ 组装输出（字段顺序 = 15 项清单顺序）
  return {
    yingshou_dachenglv_bps: yingshou,
    chengben_kongzhilv_bps: chengben_kongzhi,
    feiyong_pianchalv_bps: feiyong_piancha,
    maolilv_bps: maolilv,
    jinglirunlv_bps: jinglirunlv,
    xiaoshou_lirunlv_bps: xiaoshou_lirunlv,
    zichan_zhouzhuanlv_bps: zichan,
    zijin_zhouzhuanlv_bps: zijin,
    caigou_chengben_bian_donglv_bps: caigou,
    gongyinglian_lvyuelv_bps: gongyinglian,
    channeng_liyonglv_bps: channeng,
    jiaofu_zhouqi_tian: jiaofu_zhouqi,
    kehu_manyilv_bps: kehu_manyi,
    yewu_jindu_bps: yewu_jindu,
    yichang_shijian_shu: yichang,
  }
}
