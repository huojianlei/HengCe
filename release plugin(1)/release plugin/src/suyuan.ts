// ======================================================================
// 经营变更双维溯源 —— 方案B 步骤 6 的【KPI 变动影响量化】确定性核心（FR-12）
// ======================================================================
//
// 转写自 D:\AppProject\algo\suyuan.py（Python 版为唯一行为准绳；
// 拼音标识符逐字保留，期望值以 algo/tests/test_suyuan.py 为准，
// 对应验证区 tests/suyuan.test.ts，测试数字逐字对应）。
//
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
//     专有缩写可保留（KPI 等）。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs/textbook/finagent-算法核对文档-定稿.md v2.1 §8.3（定稿#10）：
//         KPI_Change_Rate =（变更后数值 − 变更前数值）÷ 原始预算数值 × 100%
//     docs/proposal-full-extract.txt 行 105~115（完整版 §2.4：分母=原始预算数值；
//         财务 9 + 非财务 6 全量覆盖；输出=影响幅度、正向/负向作用、影响占比）
//     docs/01-需求说明.md v2.0 §3 FR-12（P1）
//
// 模块定位：本模块量化【一个经营变更事件】对 15 项 KPI 的影响——输入是
//     "变更前 → 变更后"的 KPI 数值对照（结构化字段，来自变更登记与 KPI 库），
//     输出影响率/作用方向/影响占比/TOP3。这是纯计算层：变更事件的【语义判定】
//     （是不是结构变更）属 AI 层（loop_decision 注入接口），本模块只算数。
//
// 三个口径决策（实现口径，显式声明）：
//     ① 影响率单位 = 整数基点（1% = 100 基点），带符号——正 = 数值上升；
//     ② 作用方向 = 15 项 KPI 偏好表判定：'越高越好'（上升=正向作用）与
//        '越低越好'（上升=负向作用）；KPI 名不在 15 项清单 → 整行拒绝
//        （溯源是结构化流程，KPI 名必须来自 KPI 库，防脏名混入）；
//     ③ 影响占比分母 = Σ|各 KPI 净影响率|（影响量占比，正负分列——
//        与积木模块 D2 同款口径，占比合计恒 10000 基点）。
//
// 缺数纪律：原始预算基准缺失（null）或 ≤ 0 → 该行影响率/占比 null
//     （交人工，不臆造），该行不参与占比分母。
//
// TS 差异（转写裁决）：除法求比率（影响率/占比）的中间量可超 2^53 →
//     统一走公共库 int-math 的 dai_fuhao_bps / bili_bps（BigInt 半进位），
//     与 Python 原式逐式对应，禁止裸 `*` 后 Math.round。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     SuyuanHang          溯源行（KPI 名 + 变更前/后数值 + 原始预算基准）
//     SuyuanXiang         溯源项（影响率/数值方向/作用方向/影响占比）
//     SuyuanJieguo        溯源结果（逐项 + 正向/负向 TOP3 + 占比分母）
//     SuyuanCuowu         溯源错误（校验失败异常）
//     jisuan_suyuan       计算溯源（主函数）
//     yingxianglv_bps     影响率（基点，带符号——正=数值上升）
//     shuzhi_fangxiang    数值方向（上升/下降/持平）
//     zuoyong             作用方向（正向作用/负向作用/无作用）
//     zhanbi_bps          影响占比（基点，非负；分母 0 时 null）
//     zhengxiang_top3 / fuxiang_top3   正向/负向作用 TOP3（KPI 名列表）
//     yingxiang_fenmu_bps 影响占比分母（Σ|净影响率|）
//
// 与上下游的关系：
//     上游：kpi（15 项 KPI 数值）、data_ingest（经营变更登记——变更前/后
//           数值与原始预算基准的取数装配在端到端层做）；
//     下游：看板数据接口（溯源分析区：影响排名/正负向 TOP3）、整改数据底座。
//
// 建立：2026-08-23 ｜ TS 转写 2026-09-05
// ======================================================================

import { bili_bps, dai_fuhao_bps } from './int-math.ts'

// ======================================================================
// 常量区（数据值用中文——KPI 名、偏好、方向枚举）
// ======================================================================

/** 数值方向枚举：数值上升 */
export const FANGXIANG_SHANGSHENG = '上升'
/** 数值方向枚举：数值下降 */
export const FANGXIANG_XIAJIANG = '下降'
/** 数值方向枚举：数值持平 */
export const FANGXIANG_CHIPING = '持平'

/** 作用方向枚举：正向作用（对经营有利） */
export const ZUOYONG_ZHENGXIANG = '正向作用'
/** 作用方向枚举：负向作用（对经营不利） */
export const ZUOYONG_FUXIANG = '负向作用'
/** 作用方向枚举：无作用（数值持平） */
export const ZUOYONG_WU = '无作用'

/** 偏好一：越高越好（数值上升 = 正向作用） */
export const PIANHAO_YUEGAO = '越高越好'
/** 偏好二：越低越好（数值上升 = 负向作用） */
export const PIANHAO_YUEDI = '越低越好'

/** 15 项 KPI 偏好表（定稿 §8 清单；方向语义见模块头口径决策②）：
 *  成本控制率=实际÷预算，越低越好（成本控制得好 <100%）；
 *  费用偏差率/采购变动率越低越好；交付周期/异常事项数越低越好。 */
export const KPI_PIANHAO: Record<string, string> = {
  营收达成率: PIANHAO_YUEGAO,
  成本控制率: PIANHAO_YUEDI,
  费用偏差率: PIANHAO_YUEDI,
  毛利率: PIANHAO_YUEGAO,
  净利润率: PIANHAO_YUEGAO,
  销售利润率: PIANHAO_YUEGAO,
  资产周转率: PIANHAO_YUEGAO,
  资金周转率: PIANHAO_YUEGAO,
  采购成本变动率: PIANHAO_YUEDI,
  供应链履约率: PIANHAO_YUEGAO,
  产能利用率: PIANHAO_YUEGAO,
  交付周期: PIANHAO_YUEDI,
  客户满意度: PIANHAO_YUEGAO,
  业务完成进度: PIANHAO_YUEGAO,
  异常事项数量: PIANHAO_YUEDI,
}

/** 影响率计算公式（定稿 #10 口径文本——报告/溯源表逐行展示，T-29#4） */
export const GONGSHI = '影响率 =（变更后数值 − 变更前数值）÷ 原始预算数值 × 100%'
/** 单字段数值上限（分/件/天/次）——防脏数据的合理性校验 */
export const ZUIDA_ZHI = 9 * 10 ** 11

/** 溯源输入校验失败（KPI 名非法 / 字段非法 / 重复行）。
 *
 *  Python 继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）；
 *  TS 侧按插件约定统一 extends Error，中文报错文案与 Python 逐字一致。 */
export class SuyuanCuowu extends Error {}

// ======================================================================
// 数据结构区（Python frozen dataclass → readonly interface + 对象字面量）
// ======================================================================

/** 溯源行：一个 KPI 在变更事件前后的数值对照 + 原始预算基准。
 *
 *  字段说明：
 *      kpi_mingcheng: KPI 名（必须是 15 项清单之一——来自 KPI 库，防脏名）；
 *      bianhua_qian:  变更前数值（非负整数；单位随 KPI：分/件/天/次）；
 *      bianhua_hou:   变更后数值（非负整数）；
 *      yuan_yusuan:   原始预算基准（定稿 #10 的分母；非负整数；null = 缺数，
 *                     该行影响率无法计算 → null 交人工）。
 *      Python 字段默认 None → TS 侧可选（?:），缺省/显式 null 均视为缺数。 */
export interface SuyuanHang {
  readonly kpi_mingcheng: string
  readonly bianhua_qian: number
  readonly bianhua_hou: number
  readonly yuan_yusuan?: number | null
}

/** 溯源项：单 KPI 的影响量化结果。
 *
 *  字段说明：
 *      kpi_mingcheng:    KPI 名（回显）。
 *      yingxianglv_bps:  影响率（基点，带符号——正 = 数值上升；
 *                        原始预算缺失/≤0 时 null）。
 *      shuzhi_fangxiang: 数值方向（上升/下降/持平）。
 *      zuoyong:          作用方向（正向作用/负向作用/无作用——偏好表判定）。
 *      zhanbi_bps:       影响占比（基点，非负；分母 0 时 null）。 */
export interface SuyuanXiang {
  readonly kpi_mingcheng: string
  readonly yingxianglv_bps: number | null
  readonly shuzhi_fangxiang: string
  readonly zuoyong: string
  readonly zhanbi_bps: number | null
}

/** 溯源结果：逐项影响 + 正负向 TOP3 + 占比分母（看板溯源区数据源）。
 *
 *  字段说明：
 *      xiang:               逐项结果（顺序 = 输入顺序）。
 *      zhengxiang_top3:     正向作用 KPI 名 TOP3（按 |影响率| 降序；并列取先）。
 *      fuxiang_top3:        负向作用 KPI 名 TOP3（同上）。
 *      yingxiang_fenmu_bps: 影响占比分母 = Σ|各 KPI 净影响率|（基点）。
 *      gongshi:             计算公式文本（T-29#4：报告新增【计算公式】列）；
 *                           Python 字段默认 GONGSHI → TS 侧由唯一构造点显式填入。 */
export interface SuyuanJieguo {
  readonly xiang: SuyuanXiang[]
  readonly zhengxiang_top3: string[]
  readonly fuxiang_top3: string[]
  readonly yingxiang_fenmu_bps: number
  readonly gongshi: string
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

/** 溯源行的 4 个字段名（鸭子类型检查用——与 SuyuanHang 接口逐字一致） */
const HANG_ZIDUAN_MING: readonly string[] = [
  'kpi_mingcheng',
  'bianhua_qian',
  'bianhua_hou',
  'yuan_yusuan',
]

/** isinstance(tiao, SuyuanHang) 的鸭子对应：普通对象（非数组）且自有键
 *  全部属于 4 个字段名、三个必填字段形态在场（yuan_yusuan 可缺省=缺数）。 */
function _shi_suyuan_hang(x: unknown): boolean {
  if (typeof x !== 'object' || x === null || Array.isArray(x)) return false
  const t = x as Record<string, unknown>
  if (!Object.keys(t).every((k) => HANG_ZIDUAN_MING.includes(k))) return false
  return typeof t.kpi_mingcheng === 'string'
    && t.bianhua_qian !== undefined
    && t.bianhua_hou !== undefined
}

/** 影响率（基点）=（变更后 − 变更前）÷ 原始预算 × 10000，half-up 带符号。
 *
 *  原始预算缺失或 ≤ 0 → null（缺数纪律，交人工）；
 *  Python 原式：(2×|差值|×10000 + 分母) // (2×分母)，符号随差值；
 *  TS 侧走公共库 dai_fuhao_bps（先取绝对值算 half-up 再补符号），逐式对应。 */
function _yingxianglv_bps(qian: number, hou: number, yuan: number | null): number | null {
  if (yuan === null || yuan <= 0) {
    return null
  }
  const chae = hou - qian
  return dai_fuhao_bps(chae, yuan)
}

/** 作用方向：数值方向 × 偏好表（15 项 KPI 的固定语义）。
 *
 *  持平（chae=0）→ '无作用'；偏好越高越好 → 上升=正向、下降=负向；
 *  偏好越低越好 → 上升=负向、下降=正向（偏好×方向四象限）。 */
function _zuoyong(kpi_mingcheng: string, chae: number): string {
  if (chae === 0) {
    return ZUOYONG_WU
  }
  const pianhao = KPI_PIANHAO[kpi_mingcheng]!
  if (pianhao === PIANHAO_YUEGAO) {
    return chae > 0 ? ZUOYONG_ZHENGXIANG : ZUOYONG_FUXIANG
  }
  return chae > 0 ? ZUOYONG_FUXIANG : ZUOYONG_ZHENGXIANG
}

/** 按作用方向取 TOP3：|影响率| 降序，并列取输入顺序靠前者。
 *
 *  影响率为 null 的项不参与排名（无法量化即无法排名，交人工）；
 *  JS 的 Array.prototype.sort 为稳定排序（ES2019 起），并列自动保输入顺序。 */
function _top3(xiang_lie: readonly SuyuanXiang[], zuoyong: string): string[] {
  const houxuan = xiang_lie
    .filter((x) => x.zuoyong === zuoyong && x.yingxianglv_bps !== null)
    .map((x) => [x.kpi_mingcheng, Math.abs(x.yingxianglv_bps as number)] as const)
  // 稳定排序：|影响率| 降序（并列自动保输入顺序）
  houxuan.sort((a, b) => b[1] - a[1])
  return houxuan.slice(0, 3).map((t) => t[0])
}

// ======================================================================
// 对外接口区（唯一的计算入口）
// ======================================================================

/** 经营变更双维溯源计算（方案B 步骤 6；纯函数）。
 *
 *  参数：shuru —— 变更事件逐 KPI 行（SuyuanHang 数组，须非空）。
 *
 *  返回：SuyuanJieguo（逐项影响率/方向/作用/占比 + 正负向 TOP3）。
 *
 *  处理顺序：
 *      ① 校验（行类型/KPI 名合法/字段形态/重复键）→ ② 影响率（half-up
 *      带符号）→ ③ 数值方向与作用方向（偏好表）→ ④ 占比（分母 = Σ|净
 *      影响率|，同积木 D2）→ ⑤ 正负向 TOP3。 */
export function jisuan_suyuan(shuru: readonly SuyuanHang[]): SuyuanJieguo {
  if (!Array.isArray(shuru) || shuru.length === 0) {
    throw new SuyuanCuowu('shuru 必须为非空列表（至少一行溯源输入）')
  }

  // ① 校验 + KPI 名去重键（同一 KPI 只允许一行，防双计）
  const yijian = new Set<string>()
  const jianyan_hou: SuyuanHang[] = []
  for (const tiao of shuru) {
    if (!_shi_suyuan_hang(tiao)) {
      throw new SuyuanCuowu(`输入含非法元素（须为 SuyuanHang）：${_repr(tiao)}`)
    }
    if (!(tiao.kpi_mingcheng in KPI_PIANHAO)) {
      throw new SuyuanCuowu(`KPI 名非法：${tiao.kpi_mingcheng}（必须是 15 项清单之一）`)
    }
    if (yijian.has(tiao.kpi_mingcheng)) {
      throw new SuyuanCuowu(`溯源行重复（KPI）：${tiao.kpi_mingcheng}——防双计`)
    }
    yijian.add(tiao.kpi_mingcheng)
    for (const [zhi, biaoshi] of [
      [tiao.bianhua_qian, 'bianhua_qian'],
      [tiao.bianhua_hou, 'bianhua_hou'],
    ] as const) {
      // bool 是 int 子类须显式排除——TS 的 typeof 校验天然覆盖（true 不是 number）
      if (typeof zhi !== 'number' || !Number.isInteger(zhi)) {
        throw new SuyuanCuowu(`${biaoshi} 必须为整数：${_repr(zhi)}`)
      }
      if (zhi < 0 || zhi > ZUIDA_ZHI) {
        throw new SuyuanCuowu(`${biaoshi} 必须在 [0, ${ZUIDA_ZHI}] 内：${zhi}`)
      }
    }
    // 原始预算基准：null 放行（缺数交人工），非缺省必须是非负整数
    const yuan = tiao.yuan_yusuan ?? null
    if (yuan !== null
      && (typeof yuan !== 'number' || !Number.isInteger(yuan)
        || yuan < 0 || yuan > ZUIDA_ZHI)) {
      throw new SuyuanCuowu(`yuan_yusuan 非法：${_repr(yuan)}`)
    }
    jianyan_hou.push(tiao)
  }

  // ② 影响率（带符号）+ ③ 数值方向与作用方向（偏好表）
  const xiang_lie: SuyuanXiang[] = []
  for (const tiao of jianyan_hou) {
    const chae = tiao.bianhua_hou - tiao.bianhua_qian
    const fangxiang = chae > 0
      ? FANGXIANG_SHANGSHENG
      : chae < 0 ? FANGXIANG_XIAJIANG : FANGXIANG_CHIPING
    xiang_lie.push({
      kpi_mingcheng: tiao.kpi_mingcheng,
      yingxianglv_bps: _yingxianglv_bps(tiao.bianhua_qian, tiao.bianhua_hou, tiao.yuan_yusuan ?? null),
      shuzhi_fangxiang: fangxiang,
      zuoyong: _zuoyong(tiao.kpi_mingcheng, chae),
      zhanbi_bps: null, // 分母算出后回填
    })
  }

  // ④ 占比分母 = Σ|各 KPI 净影响率|（影响量占比，正负分列——同积木 D2）
  const fenmu = xiang_lie.reduce(
    (he, x) => x.yingxianglv_bps !== null ? he + Math.abs(x.yingxianglv_bps) : he,
    0,
  )

  const _zhanbi = (lv: number | null): number | null => {
    if (lv === null || fenmu === 0) {
      return null
    }
    // Python 原式 (2×|占比分子|×10000 + 分母) // (2×分母)——走 bili_bps 逐式对应
    return bili_bps(Math.abs(lv), fenmu)
  }

  const xiang_huitian = xiang_lie.map((x) => ({
    ...x,
    zhanbi_bps: _zhanbi(x.yingxianglv_bps),
  }))

  // ⑤ 正负向 TOP3
  return {
    xiang: xiang_huitian,
    zhengxiang_top3: _top3(xiang_huitian, ZUOYONG_ZHENGXIANG),
    fuxiang_top3: _top3(xiang_huitian, ZUOYONG_FUXIANG),
    yingxiang_fenmu_bps: fenmu,
    gongshi: GONGSHI,
  }
}
